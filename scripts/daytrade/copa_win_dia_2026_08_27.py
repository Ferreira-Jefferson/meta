"""copa_win (WIN@, M1) rodado SOMENTE no pregao de ontem (2026-08-27),
capital minimo real (R$200 = margem R$100 x buffer 2x). Mesmo padrao de
`wdo_grid_reload_maker_dia_2026_08_27.py`.

Dado M1 ja atualizado via `scripts/daytrade/backfill_m1.py --symbol WIN@`
(feito na rodada anterior, cobre ate hoje 2026-08-28).

Uso: `python -u scripts/daytrade/copa_win_dia_2026_08_27.py`
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
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import MARGIN_BUFFER_FUTUROS, contracts_from_capital  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

DIA = pd.Timestamp("2026-08-27", tz="UTC")
MARGEM_WIN_BRL = 100.0
ECONOMIA_WIN = (0.2, 1.0)  # fallback conhecido (copa_lab._ECONOMIA_CONHECIDA)


def main() -> None:
    bars = load_m1("WIN@")
    if bars.empty:
        raise SystemExit("[copa_win_dia] sem M1 local para WIN@ -- rode backfill_m1.py --symbol WIN@ primeiro.")
    bars = bars.sort_index()
    bars_dia = bars.loc[(bars.index >= DIA) & (bars.index < DIA + pd.Timedelta(days=1))]
    if bars_dia.empty:
        raise SystemExit(f"[copa_win_dia] nenhuma barra de WIN@ em {DIA.date()} -- dado nao chegou ainda?")

    print(f"[copa_win_dia] {DIA.date()}: {len(bars_dia)} barras M1, "
          f"{bars_dia.index.min()} -> {bars_dia.index.max()}")

    cash = MARGEM_WIN_BRL * MARGIN_BUFFER_FUTUROS
    profile = profile_for("WIN@")
    teto = contracts_from_capital(cash, MARGEM_WIN_BRL, hard_cap=profile.max_open_contracts)
    robo = get_daytrade_robot("copa_win")
    cfg = config_for(
        profile, trade_tick_value=ECONOMIA_WIN[0], trade_tick_size=ECONOMIA_WIN[1],
        initial_capital=cash, target_fills_as_maker=robo.target_fills_as_maker, max_open_contracts=teto,
    )
    resultado = run_intraday_backtest(bars_dia, robo, cfg)
    linha = linha_de_resultado(
        "copa_win", resultado, cash,
        extras={"simbolo": "WIN@", "capital ini": "R$" + num_br(cash, 0), "teto contratos": str(teto)},
    )

    print(f"\n=== copa_win -- pregao de {DIA.date()}, capital minimo real (R${num_br(cash,0)}) ===")
    print(tabela([linha], extras=("simbolo", "capital ini", "teto contratos")))


if __name__ == "__main__":
    main()
