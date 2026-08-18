"""Roda um backtest e persiste tudo no diário."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backtest.engine import run_backtest
from core.config import BacktestConfig
from journal.enrichment import enrich
from journal.writer import append_equity, create_run, finalize_run, insert_trade, journal
from market_data.loader import load_universe
from strategy.bollinger_squeeze_breakout import BollingerSqueezeBreakout
from strategy.buy_the_dip import BuyTheDip
from strategy.buy_the_dip_1pct import BuyTheDip1pct
from strategy.buy_the_dip_5pct import BuyTheDip5pct
from strategy.channel_regression_reentry import ChannelRegressionReentry
from strategy.donchian_breakout import DonchianBreakout
from strategy.ema_ribbon_momentum import EmaRibbonMomentum
from strategy.hybrid_cadence_by_vol import HybridCadenceByVol
from strategy.ma_slope_filter import MaSlopeFilter

STRATEGIES = {
    "buy_the_dip_5pct": BuyTheDip5pct,
    "buy_the_dip": BuyTheDip,
    "buy_the_dip_1pct": BuyTheDip1pct,
    "hybrid_cadence_by_vol": HybridCadenceByVol,
    "donchian_breakout": DonchianBreakout,
    "ma_slope_filter": MaSlopeFilter,
    "bollinger_squeeze_breakout": BollingerSqueezeBreakout,
    "ema_ribbon_momentum": EmaRibbonMomentum,
    "channel_regression_reentry": ChannelRegressionReentry,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", default="buy_the_dip_5pct", choices=list(STRATEGIES))
    p.add_argument("--start", required=True, help="YYYY-MM-DD ou YYYY")
    p.add_argument("--end", required=True, help="YYYY-MM-DD ou YYYY")
    p.add_argument("--capital", type=float, default=1_000.0)
    p.add_argument("--lot-size", type=int, default=1)
    return p.parse_args()


def _normalize_date(s: str, is_end: bool) -> str:
    if len(s) == 4:
        return f"{s}-12-31" if is_end else f"{s}-01-01"
    return s


def main() -> None:
    args = parse_args()
    start = _normalize_date(args.start, is_end=False)
    end = _normalize_date(args.end, is_end=True)

    universe = load_universe()
    strategy = STRATEGIES[args.strategy]()
    config = BacktestConfig(initial_capital=args.capital, lot_size=args.lot_size)

    print(f"Rodando {strategy.name} v{strategy.version} de {start} a {end}...")
    result = run_backtest(universe, strategy, config, start=start, end=end)

    with journal() as conn:
        run_id = create_run(
            conn,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            period_start=start,
            period_end=end,
            initial_capital=config.initial_capital,
        )
        for trade in result.trades:
            trade.tags = enrich(trade)
            insert_trade(conn, run_id, trade)
        bench = result.benchmark_curve.reindex(result.equity_curve.index).ffill()
        equity_points = [
            (d.strftime("%Y-%m-%d"), float(e), float(bench.get(d)) if d in bench.index else None)
            for d, e in result.equity_curve.items()
        ]
        append_equity(conn, run_id, equity_points)
        finalize_run(conn, run_id, result.metrics)

    m = result.metrics
    print(
        f"\nRun #{run_id} concluída. trades={m['trades_count']} "
        f"CAGR={m['cagr']:.2%} Sharpe={m['sharpe']:.2f} "
        f"MaxDD={m['max_drawdown']:.2%} vs IBOV CAGR={m['benchmark_cagr']:.2%}"
    )


if __name__ == "__main__":
    main()
