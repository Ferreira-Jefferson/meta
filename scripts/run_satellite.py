"""Compara dip_top1_hysteresis: engine padrao vs engine satelite (10%/20%)."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine import run_backtest
from backtest.engine_satellite import run_satellite_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.h3_hysteresis import DipTop1Hysteresis

TICKERS = ["WEGE3.SA", "BRAP4.SA", "RADL3.SA", "CSMG3.SA", "EMAE4.SA", "KEPL3.SA", "CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")


def metrics_line(result):
    m = result.metrics
    eq = result.equity_curve
    yearly = eq.resample("YE").agg(["first", "last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    return m["final_capital"], m["cagr"], m.get("sharpe", 0), m["max_drawdown"], neg, m.get("trades_count", 0)


def run_both(start, end, label):
    universe = load_universe(tickers=TICKERS, include_benchmark=True)
    config = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)

    t0 = time.perf_counter()
    r_std = run_backtest(universe, DipTop1Hysteresis(), config, start=start, end=end)
    t1 = time.perf_counter()
    r_sat = run_satellite_backtest(universe, DipTop1Hysteresis(), config, start=start, end=end,
                                   satellite_pct=0.10, satellite_stop_pct=0.20)
    t2 = time.perf_counter()

    f_std, c_std, sh_std, dd_std, n_std, tr_std = metrics_line(r_std)
    f_sat, c_sat, sh_sat, dd_sat, n_sat, tr_sat = metrics_line(r_sat)

    print(f"\n{'='*65}")
    print(f"  {label}  {start} -> {end}")
    print(f"{'='*65}")
    print(f"  {'':20s}  {'Final':>10}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'NegYr':>6}  {'Trades':>7}")
    print(f"  {'-'*20}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}  {'-'*7}")
    print(f"  {'Padrao (100%->novo)':20s}  R${f_std:8.2f}  {c_std*100:6.2f}%  {sh_std:7.2f}  {dd_std*100:6.2f}%  {n_std:>6}  {tr_std:>7}  ({t1-t0:.1f}s)")
    print(f"  {'Satelite (90%+10%)':20s}  R${f_sat:8.2f}  {c_sat*100:6.2f}%  {sh_sat:7.2f}  {dd_sat*100:6.2f}%  {n_sat:>6}  {tr_sat:>7}  ({t2-t1:.1f}s)")

    delta = f_sat - f_std
    sinal = "+" if delta >= 0 else ""
    print(f"\n  Delta satelite vs padrao: {sinal}R${delta:.2f}  ({sinal}{(f_sat/f_std-1)*100:.1f}%)")

    # Ano a ano
    print(f"\n  Ano a ano:")
    print(f"  {'Ano':4s}  {'Padrao':>9}  {'Satelite':>9}  {'Delta':>7}")
    y_std = r_std.equity_curve.resample("YE").agg(["first","last"])
    y_std["ret"] = y_std["last"]/y_std["first"] - 1
    y_sat = r_sat.equity_curve.resample("YE").agg(["first","last"])
    y_sat["ret"] = y_sat["last"]/y_sat["first"] - 1
    for yr in sorted(set(y_std.index) | set(y_sat.index)):
        rs = y_std.loc[yr,"ret"] if yr in y_std.index else float("nan")
        rv = y_sat.loc[yr,"ret"] if yr in y_sat.index else float("nan")
        d  = rv - rs if not (pd.isna(rs) or pd.isna(rv)) else float("nan")
        ns = "*" if not pd.isna(rs) and rs < 0 else " "
        nv = "*" if not pd.isna(rv) and rv < 0 else " "
        rss = f"{rs*100:+.1f}%{ns}" if not pd.isna(rs) else "  N/A  "
        rvs = f"{rv*100:+.1f}%{nv}" if not pd.isna(rv) else "  N/A  "
        ds  = f"{d*100:+.1f}%"  if not pd.isna(d)  else "  N/A "
        print(f"  {yr.year}  {rss:>9}  {rvs:>9}  {ds:>7}")

    return r_std, r_sat


run_both("2010-01-01", TODAY, "FULL")
run_both(THREE_Y, TODAY, "3Y")
