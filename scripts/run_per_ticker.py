"""Qual ticker performa melhor sozinho no dip_top1_hysteresis?"""
import sys, time
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd
from backtest.engine import run_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.h3_hysteresis import DipTop1Hysteresis

TICKERS = ["WEGE3.SA", "BRAP4.SA", "RADL3.SA", "CSMG3.SA", "EMAE4.SA", "KEPL3.SA", "CXSE3.SA"]
INITIAL = 1000.0

def run(tickers, start, end):
    universe = load_universe(tickers=tickers, include_benchmark=True)
    config = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
    result = run_backtest(universe, DipTop1Hysteresis(), config, start=start, end=end)
    m = result.metrics
    eq = result.equity_curve
    yearly = eq.resample("YE").agg(["first", "last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    return {
        "final": float(m["final_capital"]),
        "cagr":  float(m["cagr"]),
        "sharpe": float(m.get("sharpe", 0)),
        "max_dd": float(m["max_drawdown"]),
        "neg_yrs": neg,
        "trades": int(m.get("trades_count", 0)),
    }

# usa o último dia com dados disponíveis (pode ser ontem se mercado não abriu)
_ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
today = _ref.index[-1].strftime("%Y-%m-%d")
three_y = (pd.Timestamp(today) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

for wname, wstart, wend in [("FULL", "2010-01-01", today), ("3Y", three_y, today)]:
    print(f"\n=== {wname}  {wstart} -> {wend} ===")
    print(f"  {'Ticker':12s}  {'Final':>10}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'NegYr':>6}  {'Trades':>7}")
    print(f"  {'-'*12}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}  {'-'*7}")
    rows = []
    for t in TICKERS:
        t0 = time.perf_counter()
        r = run([t], wstart, wend)
        r["ticker"] = t.replace(".SA","")
        dt = time.perf_counter() - t0
        rows.append(r)
        print(f"  {r['ticker']:12s}  R${r['final']:8.2f}  {r['cagr']*100:6.2f}%  {r['sharpe']:7.2f}  {r['max_dd']*100:6.2f}%  {r['neg_yrs']:>6}  {r['trades']:>7}  ({dt:.1f}s)")
    # combos para comparação
    for combo_name, combo in [
        ("[TOP-3 antigo]", ["WEGE3.SA", "RADL3.SA", "VALE3.SA"]),
        ("[TOP-7 juntos]", TICKERS),
    ]:
        t0 = time.perf_counter()
        r = run(combo, wstart, wend)
        dt = time.perf_counter() - t0
        print(f"  {combo_name:12s}  R${r['final']:8.2f}  {r['cagr']*100:6.2f}%  {r['sharpe']:7.2f}  {r['max_dd']*100:6.2f}%  {r['neg_yrs']:>6}  {r['trades']:>7}  ({dt:.1f}s)")
