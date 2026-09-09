"""Efeito da HISTERESE anti-pingue-pongue (`reancora_min_ticks` 1 -> 2) no
IS/OOS congelado da `WdoGridReloadMaker`, config EXATA de producao.

## O que motivou

Achado do dono no 1o pregao com o item 4.9 ao vivo (2026-09-08, slot
`dt-wdo_grid_reload_maker-wdo@-live`): 125 linhas `LIMITE` para 22 rodadas,
103 delas `(substitui)`. A rodada #21 emitiu 5105,0 -> 5105,5 -> 5105,0 ->
5105,5 -> 5106,5 no MESMO segundo de parede -- a ordem volta para um nivel
que ela mesma acabou de abandonar, e cada volta e' um cancela+reenvia real
que joga fora a fila ja' acumulada. Veredito: "substituiu 3 vezes para o
mesmo preco, mesmo stop e mesmo alvo, isso e' uso de recurso desnecessario,
neste caso nao deve substituir".

A correcao (ver `reancora_min_ticks` em `strategy.daytrade.lab.
wdo_grid_reload_maker`) e' de ESTRATEGIA, entao vale identica no backtest e
ao vivo -- e por isso pode e deve ser medida aqui. Este script responde a
UNICA pergunta que a decisao do dono nao responde sozinha: **o que a
histerese faz com o resultado?**

## O que este script NAO e'

Nao e' uma escolha de parametro. `reancora_min_ticks=2` foi decidido pelo
dono; `=1` entra so' como BASELINE (o comportamento de ate' 2026-09-08),
para a diferenca ficar visivel. Se a tabela mostrar que a histerese custa
resultado, isso vira informacao para o dono, nao motivo para reverter por
conta propria.

Nao mede `profit_ticks=1` (T1) -- proibido, ver a secao do deslize de TP em
`CLAUDE.md`. Producao e' T2/S16 e e' o que roda aqui.

## Colunas que importam alem da tabela padrao

`pior_janela_60s` e' a mesma grandeza que os tetos de envio de
`live.intraday_runtime` limitam ao vivo. Quando esta rodada foi feita havia
um teto so' (`MAX_ENVIOS_POR_MINUTO = 30`) e estourar NAO recusava so' a
ordem: ligava `disaster_halt` e parava o robo pelo resto do pregao -- foi
justamente o 42 medido aqui que motivou a troca de desenho, no mesmo dia,
para `COTA_ENVIOS_POR_MINUTO` (120, recusa a ordem excedente) mais
`MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO` (600, disjuntor).
`envios` e' o total de `EnterLimit` do periodo -- o desperdicio que o dono
apontou mora ai.

Base: `data/raw_ticks/WDO_A_f1.parquet` (regenerado 2026-09-07, cobertura de
minuto de pregao 100%), split IS/OOS CONGELADO, capital real R$375.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

SYMBOL = "WDO@"

#: Capital REAL do slot ao vivo -- R$375 = margem R$150 x buffer 2.0 x
#: reserva 1.25 (CLAUDE.md, "capital inicial nunca arbitrario").
CAPITAL_REAL_BRL = 375.0

#: Mesma lista de `wdof1_producao_is_oos_2026_09_07.py` -- todo parametro de
#: `WdoGridReloadMaker.__init__` (menos `self`), para clonar a instancia de
#: PRODUCAO via kwargs sobrescrevendo so' o que esta rodada varia.
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

EXTRAS = ("envios", "pior_janela_60s", "saida_alvo", "saida_stop",
          "pregoes_sem_trade", "qtd_max", "zerou", "caixa_min")

_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars_do_processo(janela: str) -> pd.DataFrame:
    if not _DF_CACHE:
        df = pd.read_parquet(CACHE)
        for j in ("IS", "OOS"):
            sub = df[df["janela"] == j]
            _DF_CACHE[j] = sub[["open", "high", "low", "close", "volume"]].sort_index()
    return _DF_CACHE[janela]


def _pior_janela_60s(envios_ts: list) -> int:
    """Pior contagem, numa janela ROLANTE de 60s, de `EnterLimit` emitidas --
    mesma grandeza que os tetos de envio do runtime limitam ao vivo (hoje
    `COTA_ENVIOS_POR_MINUTO`=120 e `MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO`=600;
    era `MAX_ENVIOS_POR_MINUTO`=30 quando esta rodada foi feita)."""
    if not envios_ts:
        return 0
    serie = pd.Series(1, index=pd.DatetimeIndex(sorted(envios_ts)))
    return int(serie.rolling("60s").sum().max())


def _roda_uma(spec: dict):
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado
    from strategy.daytrade.base import EnterLimit
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    class _ComContadorEnvios(WdoGridReloadMaker):
        """Mesma classe de producao -- so' registra o carimbo de toda
        `EnterLimit` emitida (armamento novo, reprecificacao ou rearme
        pos-recusa contam igual: cada uma e' um `place_limit` ao vivo)."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.envios_ts: list[pd.Timestamp] = []

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            actions = super().on_bar(ts, bar, positions, session_pnl_brl)
            for action in actions:
                if isinstance(action, EnterLimit):
                    self.envios_ts.append(pd.Timestamp(ts))
            return actions

    bars = _bars_do_processo(spec["janela"])

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    kwargs["reancora_min_ticks"] = spec["min_ticks"]
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
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(resultado.trades)
    contagem = Counter(t.exit_reason.value for t in trades)
    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "envios": str(len(strat.envios_ts)),
        "pior_janela_60s": str(_pior_janela_60s(strat.envios_ts)),
        "saida_alvo": str(contagem.get("target", 0)),
        "saida_stop": str(contagem.get("stop", 0)),
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "qtd_max": str(max((t.quantity for t in trades), default=0)),
        "zerou": ("NAO" if resultado.wiped_out_at is None
                  else str(resultado.wiped_out_at)),
        "caixa_min": f"{caixa_min:,.2f}".replace(",", "@").replace(".", ",").replace("@", "."),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, CAPITAL_REAL_BRL,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{spec['janela']}, {dt:5.1f}s] {linha(item, EXTRAS)}", flush=True)
    return spec["janela"], spec["rotulo"], item, buf.getvalue()


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_histerese] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    sys.path.insert(0, str(RAIZ / "src"))
    from strategy.daytrade.registry import get_daytrade_robot

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    print("[wdof1_histerese] kwargs de producao "
          "(get_daytrade_robot('wdo_grid_reload_maker')):")
    for campo in CAMPOS_KWARGS:
        print(f"    {campo} = {getattr(robo, campo)!r}")
    print(flush=True)

    specs = [
        dict(janela=janela, min_ticks=mt,
             rotulo=f"[{janela}] T2/S16 hist={mt}"
                    + (" (baseline ate 08/09)" if mt == 1 else " (producao nova)"))
        for janela in ("IS", "OOS")
        for mt in (1, 2)
    ]

    n_workers = max(1, min(len(specs), os.cpu_count() or 4))
    print(f"[wdof1_histerese] capital real R${CAPITAL_REAL_BRL:.2f}, "
          f"{len(specs)} tarefas, {n_workers} processos\n", flush=True)

    t0 = time.perf_counter()
    resultados: dict = {}
    concluidos = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            janela, rotulo, item, texto = future.result()
            resultados[(janela, rotulo)] = item
            concluidos += 1
            print(f"[{concluidos}/{len(specs)}] {texto}", end="", flush=True)
    print(f"\n[wdof1_histerese] motor: {time.perf_counter() - t0:.1f}s "
          f"em {n_workers} processos\n")

    from backtest.intraday.report import cabecalho, linha as linha_fmt

    for janela in ("IS", "OOS"):
        print(f"\n=== tabela {janela} ===")
        print(cabecalho(EXTRAS))
        for spec in specs:
            if spec["janela"] == janela:
                print(linha_fmt(resultados[(janela, spec["rotulo"])], EXTRAS))


if __name__ == "__main__":
    main()
