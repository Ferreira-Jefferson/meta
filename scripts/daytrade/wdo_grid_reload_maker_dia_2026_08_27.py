"""wdo_grid_reload_maker (WDO@, tick) rodado SOMENTE no pregao de ontem
(2026-08-27), capital minimo real (R$300 = margem R$150 x buffer 2x).

Dado tick baixado do MT5 na hora (`scripts/daytrade/backfill_ticks.py
--symbol WDO@`, feito antes deste script) -- caminho CANONICO (`market_data_
intraday.tick_storage.load_ticks("WDO@")`), nao o cache manual da frente F1
usado nas rodadas anteriores.

Uso: `python -u scripts/daytrade/wdo_grid_reload_maker_dia_2026_08_27.py`
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
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.base import MARGIN_BUFFER_FUTUROS, contracts_from_capital  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

DIA = pd.Timestamp("2026-08-27", tz="UTC")
MARGEM_WDO_BRL = 150.0
ECONOMIA_WDO = (0.01, 0.001)  # fallback conhecido (copa_lab._ECONOMIA_CONHECIDA)


def main() -> None:
    ticks = load_ticks("WDO@")
    if ticks.empty:
        raise SystemExit("[wdo_dia] sem tick local para WDO@ -- rode backfill_ticks.py --symbol WDO@ primeiro.")
    bars = ticks_to_degenerate_bars(ticks.sort_index())
    bars_dia = bars.loc[(bars.index >= DIA) & (bars.index < DIA + pd.Timedelta(days=1))]
    if bars_dia.empty:
        raise SystemExit(f"[wdo_dia] nenhum tick de WDO@ em {DIA.date()} -- dado nao chegou ainda no terminal?")

    print(f"[wdo_dia] {DIA.date()}: {len(bars_dia)} ticks, "
          f"{bars_dia.index.min()} -> {bars_dia.index.max()}")

    cash = MARGEM_WDO_BRL * MARGIN_BUFFER_FUTUROS
    profile = profile_for("WDO@")
    teto = contracts_from_capital(cash, MARGEM_WDO_BRL, hard_cap=profile.max_open_contracts)
    robo = get_daytrade_robot("wdo_grid_reload_maker")
    cfg = config_for(
        profile, trade_tick_value=ECONOMIA_WDO[0], trade_tick_size=ECONOMIA_WDO[1],
        initial_capital=cash, max_open_contracts=teto,
        target_fills_as_maker=robo.target_fills_as_maker,
    )
    resultado = run_intraday_backtest(bars_dia, robo, cfg)
    linha = linha_de_resultado(
        "wdo_grid_reload_maker", resultado, cash,
        extras={"simbolo": "WDO@", "capital ini": "R$" + num_br(cash, 0), "teto contratos": str(teto)},
    )

    print(f"\n=== wdo_grid_reload_maker -- pregao de {DIA.date()}, capital minimo real (R${num_br(cash,0)}) ===")
    print(tabela([linha], extras=("simbolo", "capital ini", "teto contratos")))


if __name__ == "__main__":
    main()
