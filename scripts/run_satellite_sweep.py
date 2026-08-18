"""Grade de parametros satellite_pct x satellite_stop_pct."""
import sys, time, itertools
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_satellite import run_satellite_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.h3_hysteresis import DipTop1Hysteresis

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

SAT_PCTS  = [0.05, 0.10, 0.15, 0.20]
STOP_PCTS = [0.10, 0.20, 0.30, 0.40]

universe = load_universe(tickers=TICKERS, include_benchmark=True)

def run(sat_pct, stop_pct, start, end):
    config = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
    r = run_satellite_backtest(universe, DipTop1Hysteresis(), config, start=start, end=end,
                               satellite_pct=sat_pct, satellite_stop_pct=stop_pct)
    m = r.metrics
    eq = r.equity_curve
    yr = eq.resample("YE").agg(["first","last"])
    yr["ret"] = yr["last"]/yr["first"] - 1
    neg = int((yr["ret"] < 0).sum())
    return m["final_capital"], m["cagr"], m.get("sharpe",0), m["max_drawdown"], neg

REF_FULL = 155364.47  # padrao sem satelite
REF_3Y   = 2267.62

print("\n=== SWEEP FULL ===")
print(f"  {'sat%':>5}  {'stop%':>5}  {'Final':>10}  {'vs ref':>7}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'NegYr':>6}")
print(f"  {'-'*5}  {'-'*5}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}")

rows = []
for sp, stp in itertools.product(SAT_PCTS, STOP_PCTS):
    f, c, sh, dd, n = run(sp, stp, "2010-01-01", TODAY)
    delta = (f / REF_FULL - 1) * 100
    rows.append((sp, stp, f, c, sh, dd, n, delta))
    print(f"  {sp*100:4.0f}%  {stp*100:4.0f}%  R${f:8.2f}  {delta:+6.1f}%  {c*100:6.2f}%  {sh:7.2f}  {dd*100:6.2f}%  {n:>6}")

# Melhor por NegYr=1 e maior capital
best_1neg = sorted([r for r in rows if r[6] <= 1], key=lambda x: -x[2])
print(f"\n  Melhor com NegYr <= 1 (por capital FULL):")
for r in best_1neg[:5]:
    print(f"    sat={r[0]*100:.0f}% stop={r[1]*100:.0f}%  R${r[2]:8.2f}  CAGR {r[3]*100:.2f}%  Sharpe {r[4]:.2f}  NegYr {r[6]}")

print("\n=== SWEEP 3Y ===")
print(f"  {'sat%':>5}  {'stop%':>5}  {'Final':>9}  {'vs ref':>7}  {'CAGR':>7}  {'NegYr':>6}")
print(f"  {'-'*5}  {'-'*5}  {'-'*9}  {'-'*7}  {'-'*7}  {'-'*6}")
for sp, stp, *_ in rows:
    f3, c3, sh3, dd3, n3 = run(sp, stp, THREE_Y, TODAY)
    d3 = (f3 / REF_3Y - 1) * 100
    print(f"  {sp*100:4.0f}%  {stp*100:4.0f}%  R${f3:7.2f}  {d3:+6.1f}%  {c3*100:6.2f}%  {n3:>6}")
