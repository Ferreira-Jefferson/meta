"""Rodada pedida pelo dono (2026-08-28): as 4 estrategias do PODIO de day
trade (`strategy.daytrade.registry._ROBOTS`, na ordem oficial), cada uma com
o CAPITAL INICIAL MINIMO REAL do seu instrumento (tabela do `CLAUDE.md`:
acao = `preco_atual x 100 x 2`; futuro = `margem x 2` -- WIN@ R$200, WDO@
R$300), todas na MESMA janela -- os ULTIMOS 3 MESES de dado local salvo
(2026-05-28 .. hoje).

NAO e' rodada de calibracao/comparacao de parametro (aquilo pediria o split
IS/OOS congelado, ver a memoria `frozen_split_scope_2026_08_21`: medir um
numero ja decidido pode usar a base toda) -- e' "como cada robo do podio
esta performando AGORA, com o robo e o capital que realmente iriam pra
producao hoje".

Fonte de dado por robo (nenhuma chama o terminal MT5 -- tudo local):
  - `wdo_grid_reload_maker` (WDO@, TICK): `data/raw_ticks/WDO_A_f1.parquet`
    -- cache manual da frente F1 (2026-08-27), ja em OHLCV degenerado,
    cobre 2026-02-27..2026-08-25 (mais que os 3 meses pedidos). O caminho
    CANONICO de `tick_storage.load_ticks("WDO@")` apontaria para
    `WDO_A_.parquet`, que nao existe -- este cache tem nome proprio da
    frente de pesquisa que o gerou.
  - `copa_win` (WIN@, M1): `market_data_intraday.storage.load_m1("WIN@")`.
  - `gremah_tick` (PMAM3, TICK): `tick_storage.load_ticks("PMAM3")` +
    `tick_bars.ticks_to_degenerate_bars`.
  - `gremah` (PMAM3, M1): `load_m1("PMAM3")`.

Economia (trade_tick_value/trade_tick_size) sai de fallback conhecido
(WIN@/WDO@, mesmo numero de `copa_lab._ECONOMIA_CONHECIDA`) ou do cache
`data/_economics_cache.json` (PMAM3) -- nenhum dos dois precisa do MT5
aberto.

Uso: `python -u scripts/daytrade/podio_ultimos_3_meses_2026_08_28.py`
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.base import (  # noqa: E402
    MARGIN_BUFFER_FUTUROS,
    capital_minimo_brl,
    contracts_from_capital,
)
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

#: 3 meses antes de hoje (2026-08-28) -- mesma janela para os 4 robos.
JANELA_INICIO = pd.Timestamp("2026-05-28", tz="UTC")

#: Cache manual da frente F1 (ver docstring do modulo) -- unico dado TICK do
#: WDO@ salvo localmente; fora do caminho canonico de `tick_storage`.
WDO_TICK_CACHE = ROOT / "data" / "raw_ticks" / "WDO_A_f1.parquet"

#: Fallback de economia dos futuros (identico a `copa_lab._ECONOMIA_CONHECIDA`)
#: -- os dois numeros sao propriedade do CONTRATO (nao cotacao), medidos, e
#: existem para o script rodar sem o terminal MT5 aberto.
ECONOMIA_WIN = (0.2, 1.0)
ECONOMIA_WDO = (0.01, 0.001)

MARGEM_WIN_BRL = 100.0
MARGEM_WDO_BRL = 150.0

#: Pedido do dono (rodada seguinte, mesmo dia): rodar de novo com MAIS
#: R$100 de capital inicial em CADA robo, por cima do minimo real de cada
#: instrumento -- WDO@ R$300->R$400, WIN@ R$200->R$300, PMAM3 R$30->R$130.
#: Nos futuros isso NAO muda o teto de contratos (`contracts_from_capital`
#: continua dando 1 nos dois -- precisaria dobrar a margem*buffer para
#: liberar o 2o contrato); em PMAM3 o efeito e' real: o portao `enforce_
#: capital_minimo` compara contra o preco de ABERTURA de CADA pregao, e o
#: preco de referencia usado (o fechamento mais recente, R$0,15) e' o MENOR
#: da janela -- com R$100 a mais o portao passa a cobrir pregoes com preco
#: de abertura ate R$0,65 (contra R$0,15 antes), destravando dias que a
#: rodada anterior pulou.
EXTRA_CAPITAL_BRL = 100.0


def _bars_m1(symbol: str) -> pd.DataFrame:
    df = load_m1(symbol)
    if df.empty:
        raise SystemExit(f"[podio_3m] sem dado M1 local para {symbol!r}.")
    df = df.sort_index()
    return df.loc[df.index >= JANELA_INICIO]


def _bars_tick_pmam3() -> pd.DataFrame:
    ticks = load_ticks("PMAM3")
    if ticks.empty:
        raise SystemExit("[podio_3m] sem tick local para PMAM3.")
    bars = ticks_to_degenerate_bars(ticks.sort_index())
    return bars.loc[bars.index >= JANELA_INICIO]


def _bars_tick_wdo() -> pd.DataFrame:
    if not WDO_TICK_CACHE.exists():
        raise SystemExit(
            f"[podio_3m] cache tick do WDO@ nao encontrado em {WDO_TICK_CACHE} -- "
            "rode `scripts/daytrade/wdof1_tick_cache_2026_08_27.py` primeiro."
        )
    df = pd.read_parquet(WDO_TICK_CACHE).sort_index()
    df = df.loc[df.index >= JANELA_INICIO]
    return df[["open", "high", "low", "close", "volume"]]


def _janela_str(bars: pd.DataFrame) -> str:
    pregoes = len(set(bars.index.date))
    if bars.empty:
        return "SEM BARRAS na janela"
    return f"{len(bars)} barras, {pregoes} pregoes, {bars.index.min()} -> {bars.index.max()}"


def main() -> None:
    print(f"[podio_3m] janela: {JANELA_INICIO.date()} -> hoje (2026-08-28), dado local disponivel ate onde existir")
    linhas = []

    # ------------------------------------------------------------------
    # 1) wdo_grid_reload_maker (WDO@, tick) -- TOP-1 do podio
    # ------------------------------------------------------------------
    bars = _bars_tick_wdo()
    print(f"\n[podio_3m] wdo_grid_reload_maker (WDO@, tick): {_janela_str(bars)}")
    cash = MARGEM_WDO_BRL * MARGIN_BUFFER_FUTUROS + EXTRA_CAPITAL_BRL
    profile = profile_for("WDO@")
    teto = contracts_from_capital(cash, MARGEM_WDO_BRL, hard_cap=profile.max_open_contracts)
    robo = get_daytrade_robot("wdo_grid_reload_maker")
    cfg = config_for(
        profile, trade_tick_value=ECONOMIA_WDO[0], trade_tick_size=ECONOMIA_WDO[1],
        initial_capital=cash, max_open_contracts=teto,
        target_fills_as_maker=robo.target_fills_as_maker,
    )
    resultado = run_intraday_backtest(bars, robo, cfg)
    linhas.append(linha_de_resultado(
        "wdo_grid_reload_maker", resultado, cash,
        extras={"simbolo": "WDO@", "capital ini": "R$" + num_br(cash, 0), "teto contratos": str(teto)},
    ))

    # ------------------------------------------------------------------
    # 2) copa_win (WIN@, M1) -- TOP-2 do podio
    # ------------------------------------------------------------------
    bars = _bars_m1("WIN@")
    print(f"\n[podio_3m] copa_win (WIN@, M1): {_janela_str(bars)}")
    cash = MARGEM_WIN_BRL * MARGIN_BUFFER_FUTUROS + EXTRA_CAPITAL_BRL
    profile = profile_for("WIN@")
    teto = contracts_from_capital(cash, MARGEM_WIN_BRL, hard_cap=profile.max_open_contracts)
    robo = get_daytrade_robot("copa_win")
    cfg = config_for(
        profile, trade_tick_value=ECONOMIA_WIN[0], trade_tick_size=ECONOMIA_WIN[1],
        initial_capital=cash, target_fills_as_maker=robo.target_fills_as_maker, max_open_contracts=teto,
    )
    resultado = run_intraday_backtest(bars, robo, cfg)
    linhas.append(linha_de_resultado(
        "copa_win", resultado, cash,
        extras={"simbolo": "WIN@", "capital ini": "R$" + num_br(cash, 0), "teto contratos": str(teto)},
    ))

    # ------------------------------------------------------------------
    # 3) gremah_tick (PMAM3, tick) -- TOP-3 do podio
    # ------------------------------------------------------------------
    bars_tick = _bars_tick_pmam3()
    bars_m1_pmam3 = _bars_m1("PMAM3")  # so' para ler o preco de referencia
    preco = float(bars_m1_pmam3.iloc[-1]["close"])
    print(f"\n[podio_3m] gremah_tick (PMAM3, tick): {_janela_str(bars_tick)} | preco ref R${num_br(preco)}")
    cash = capital_minimo_brl(preco) + EXTRA_CAPITAL_BRL
    profile = profile_for("PMAM3")
    robo = get_daytrade_robot("gremah_tick")
    cfg = config_for(
        profile, trade_tick_value=0.01, trade_tick_size=0.01,
        target_fills_as_maker=robo.target_fills_as_maker, initial_capital=cash,
    )
    # Regra real do ao vivo (`live/intraday_runtime.py::_check_capital`,
    # pedido do dono 2026-08-24): o piso de 2x so' vale para a sessao em que
    # o robo consegue COMECAR -- dali em diante, cada pregao seguinte so'
    # precisa cobrir 1x o lote do dia, nao 2x de novo. Ver `IntradayBacktest
    # Config.capital_minimo_so_na_entrada` (motor, 2026-08-28).
    cfg = dataclasses.replace(cfg, capital_minimo_so_na_entrada=True)
    resultado = run_intraday_backtest(bars_tick, robo, cfg)
    linhas.append(linha_de_resultado(
        "gremah_tick", resultado, cash,
        extras={"simbolo": "PMAM3", "capital ini": "R$" + num_br(cash, 0), "preco ref": num_br(preco)},
    ))

    # ------------------------------------------------------------------
    # 4) gremah (PMAM3, M1) -- TOP-4 do podio
    # ------------------------------------------------------------------
    print(f"\n[podio_3m] gremah (PMAM3, M1): {_janela_str(bars_m1_pmam3)} | preco ref R${num_br(preco)}")
    robo = get_daytrade_robot("gremah")
    cfg = config_for(
        profile, trade_tick_value=0.01, trade_tick_size=0.01,
        target_fills_as_maker=robo.target_fills_as_maker, initial_capital=cash,
    )
    cfg = dataclasses.replace(cfg, capital_minimo_so_na_entrada=True)
    resultado = run_intraday_backtest(bars_m1_pmam3, robo, cfg)
    linhas.append(linha_de_resultado(
        "gremah", resultado, cash,
        extras={"simbolo": "PMAM3", "capital ini": "R$" + num_br(cash, 0), "preco ref": num_br(preco)},
    ))

    print(f"\n\n=== PODIO DE DAY TRADE -- ultimos 3 meses ({JANELA_INICIO.date()} -> hoje), capital minimo real ===")
    print(tabela(linhas, extras=("simbolo", "capital ini", "teto contratos", "preco ref")))


if __name__ == "__main__":
    main()
