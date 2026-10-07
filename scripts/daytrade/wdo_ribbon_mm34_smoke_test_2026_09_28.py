"""Smoke test da WdoRibbonMm34 (ribbon de 4 MMs a 34 periodos -- SMA/EMA/
SMMA/LWMA -- entrada na vela que fecha sem tocar nenhuma das quatro,
stop colado na media mais proxima do preco, arrastado a cada
fechamento). So' confirma que a estrategia roda de ponta a ponta no
motor de backtest intraday e imprime a tabela padrao -- nao e' validacao
estatistica (sem IS/OOS, sem IC, sem veredito).

Uso: python -u scripts/daytrade/wdo_ribbon_mm34_smoke_test_2026_09_28.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.wdo_ribbon_mm34 import WdoRibbonMm34  # noqa: E402

SYMBOL = "WDO@"
ECONOMIA_WDO = (0.01, 0.001)
CAPITAL_TESTE_BRL = 375.0
MIN_BARRAS_POR_PREGAO = 400


def _normalizar_volume(bars: pd.DataFrame) -> pd.DataFrame:
    bars = bars.copy()
    real = bars["real_volume"] if "real_volume" in bars.columns else pd.Series(0.0, index=bars.index)
    tick = bars["tick_volume"] if "tick_volume" in bars.columns else pd.Series(0.0, index=bars.index)
    bars["volume"] = real.where(real > 0, tick)
    return bars


def _filtrar_pregoes_completos(bars: pd.DataFrame) -> pd.DataFrame:
    contagem = bars.groupby(bars.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    return bars[[d in completos for d in bars.index.date]]


def main() -> None:
    bars = load_m1(SYMBOL)
    if bars.empty:
        raise SystemExit(f"sem dado M1 salvo para {SYMBOL!r}.")
    bars = _normalizar_volume(bars)
    bars = _filtrar_pregoes_completos(bars)
    if bars.empty:
        raise SystemExit("sem pregao completo.")
    pregoes = sorted(set(bars.index.date))
    print(f"[wdo_ribbon_mm34 smoke test] {SYMBOL} {pregoes[0]}..{pregoes[-1]} ({len(pregoes)} pregoes)")
    print(f"capital R${num_br(CAPITAL_TESTE_BRL, 0)}\n", flush=True)

    profile = profile_for(SYMBOL)
    strat = WdoRibbonMm34(symbol=SYMBOL, tick_size=profile.price_tick_size)
    cfg = config_for(
        profile,
        trade_tick_value=ECONOMIA_WDO[0],
        trade_tick_size=ECONOMIA_WDO[1],
        initial_capital=CAPITAL_TESTE_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        enforce_capital_cap=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    item = linha_de_resultado("wdo_ribbon_mm34", resultado, CAPITAL_TESTE_BRL)
    print(cabecalho())
    print(linha(item))


if __name__ == "__main__":
    main()
