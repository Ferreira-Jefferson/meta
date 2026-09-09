"""Distribuicao do PIOR MINUTO de envios de ordem da `WdoGridReloadMaker`,
por pregao, no IS/OOS congelado -- a medicao que faltava para calibrar
`live.intraday_runtime.MAX_ENVIOS_POR_MINUTO`.

## Por que existe

O teto de 30 envios/60s foi calibrado contando tempo de TICK (commit
75f6b48 corrigiu o contador para RELOGIO DE PAREDE e deixou a ressalva
escrita: "o 'pior minuto 26 de 30' da docstring nao o descreve mais").
Pior: ao estourar, ele nao recusa a ordem -- liga `disaster_halt` e cala o
robo pelo pregao inteiro. Um teto errado nesse desenho custa o dia.

O commit e8f88fe ja tinha mostrado o numero que obriga a re-medir: o pior
minuto do OOS da' 42 envios COM e SEM a histerese -- saturacao de
`max_trades_per_side`, nao laco. Este script tira dai a DISTRIBUICAO por
pregao (p50/p95/p99/max), que e' o que permite escolher um teto com margem
em vez de escolher pelo maximo de uma amostra.

Nao mede `profit_ticks=1` (T1) -- proibido, ver `CLAUDE.md`. Config EXATA
de producao (`get_daytrade_robot`), base `WDO_A_f1.parquet` regenerada em
2026-09-07, capital real R$375.

## Resultado da rodada de 2026-09-08 (motor: 2.466s IS / 737s OOS)

    fonte                   n     p50   p90   p95   p99   max
    IS  (72 pregoes)       72      12    19    20    22     23
    OOS (51 pregoes)       51      10    19    24    34     42
    IS+OOS                123      11    19    22    25     42

Pregoes que estourariam um teto de 30 (o teto ANTIGO): 1 de 123 (0,8%),
todos no OOS. De 50 para cima: ZERO. Com isso os dois numeros novos:

    COTA_ENVIOS_POR_MINUTO             = 120  (~2,9x o max, ~3,5x o p99 OOS)
    MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO = 600  (5x a cota, ~14x o max)

Contraparte de PAREDE, do pregao real de 2026-09-08 (`db/live.sqlite`,
janela rolante de 60s sobre `live_events.ts`, que e' hora de ESCRITA):
conta 476 (SOMBRA, pregao inteiro, 173 envios) da' p50 3 / p95 15 / max 19;
conta 474 (REAL, 125 envios) da' max 64 -- mas aquele e' um pregao com o
feed cego e sem histerese, as duas causas ja corrigidas no mesmo dia
(`MAX_ATRASO_PARA_ORDEM_SEGUNDOS` e `reancora_min_ticks`).

## Que relogio isto mede

Tempo de BARRA (== tempo de mercado). No backtest e' o unico relogio que
existe, e ele descreve a cadencia LEGITIMA de um feed saudavel: quantas
ordens a estrategia decide mandar num minuto real de mercado. E' esse o
numero que o teto operacional nao pode cortar. O outro regime -- rajada de
parede, quando o supervisor reprocessa fila atrasada -- so' existe ao vivo
e sai do replay do pregao real (`db/live.sqlite`).
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"
SAIDA = RAIZ / "scripts" / "daytrade" / "wdof1_cadencia_envios_2026_09_08.csv"

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0

CAMPOS_KWARGS = (
    "symbol", "tick_size", "level_spacing_ticks", "profit_ticks", "stop_ticks",
    "reanchor_mode", "reancora_min_segundos", "reancora_min_ticks",
    "max_trades_per_side", "session_stop_brl", "quantity",
    "margin_per_contract_brl", "margin_buffer", "hard_cap_contratos",
    "risco_pct_por_trade", "point_value_brl",
    "defesa_ativa", "defesa_gatilho_stop_pct", "defesa_alvo_proximidade_pct",
    "trailing_ativo", "trailing_recuo_ticks",
    "gate_atividade_ativo", "gate_volume_min", "gate_janela_segundos",
)

_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars_do_processo(janela: str) -> pd.DataFrame:
    if not _DF_CACHE:
        df = pd.read_parquet(CACHE)
        for j in ("IS", "OOS"):
            sub = df[df["janela"] == j]
            _DF_CACHE[j] = sub[["open", "high", "low", "close", "volume"]].sort_index()
    return _DF_CACHE[janela]


def _roda_uma(janela: str):
    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.base import EnterLimit
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    class _ComContadorEnvios(WdoGridReloadMaker):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.envios_ts: list = []

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            actions = super().on_bar(ts, bar, positions, session_pnl_brl)
            for action in actions:
                if isinstance(action, EnterLimit):
                    self.envios_ts.append(pd.Timestamp(ts))
            return actions

    bars = _bars_do_processo(janela)
    robo = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo, campo) for campo in CAMPOS_KWARGS}
    strat = _ComContadorEnvios(**kwargs)

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    t0 = time.perf_counter()
    run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    envios = pd.DatetimeIndex(sorted(strat.envios_ts))
    pregoes_da_base = sorted(set(bars.index.date))
    linhas = []
    for dia in pregoes_da_base:
        do_dia = envios[envios.date == dia]
        if len(do_dia) == 0:
            linhas.append({"janela": janela, "pregao": str(dia), "envios": 0,
                           "pior_60s": 0})
            continue
        serie = pd.Series(1, index=do_dia)
        linhas.append({"janela": janela, "pregao": str(dia),
                       "envios": int(len(do_dia)),
                       "pior_60s": int(serie.rolling("60s").sum().max())})
    print(f"[{janela}, {dt:5.1f}s] {len(envios)} envios em "
          f"{len(pregoes_da_base)} pregoes", flush=True)
    return pd.DataFrame(linhas)


def _percentis(serie: pd.Series, rotulo: str) -> str:
    return (f"{rotulo:<28} n={len(serie):>4}  p50={serie.quantile(.50):>6.1f}  "
            f"p90={serie.quantile(.90):>6.1f}  p95={serie.quantile(.95):>6.1f}  "
            f"p99={serie.quantile(.99):>6.1f}  max={serie.max():>6.0f}")


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(f"[cadencia] cache ausente: {CACHE}")
    partes = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_roda_uma, j): j for j in ("IS", "OOS")}
        for future in as_completed(futures):
            partes.append(future.result())
    df = pd.concat(partes, ignore_index=True).sort_values(["janela", "pregao"])
    df.to_csv(SAIDA, index=False)
    print(f"\n[cadencia] CSV: {SAIDA}\n")

    for janela in ("IS", "OOS"):
        sub = df[df["janela"] == janela]
        com_envio = sub[sub["envios"] > 0]
        print(f"=== {janela} ({len(sub)} pregoes, {len(com_envio)} com envio) ===")
        print(_percentis(sub["pior_60s"], "pior minuto/pregao (todos)"))
        if len(com_envio):
            print(_percentis(com_envio["pior_60s"], "pior minuto/pregao (c/ envio)"))
        for teto in (30, 40, 50, 60, 80, 100, 120, 150, 200):
            n = int((sub["pior_60s"] > teto).sum())
            print(f"    pregoes que estourariam teto {teto:>3}: {n:>4} "
                  f"({100.0 * n / max(1, len(sub)):5.1f}%)")
        print()
    todos = df["pior_60s"]
    print("=== IS+OOS ===")
    print(_percentis(todos, "pior minuto/pregao"))


if __name__ == "__main__":
    main()
