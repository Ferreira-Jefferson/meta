"""Validação do universo ótimo de 7 tickers vs TOP-3 atual."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine import run_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.h3_hysteresis import DipTop1Hysteresis

INITIAL = 1000.0

TOP7  = ["WEGE3.SA", "BRAP4.SA", "RADL3.SA", "CSMG3.SA", "EMAE4.SA", "KEPL3.SA", "CXSE3.SA"]
TOP3  = ["WEGE3.SA", "RADL3.SA", "VALE3.SA"]

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")


def run(tickers, start, end):
    universe = load_universe(tickers=tickers, include_benchmark=True)
    config = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
    result = run_backtest(universe, DipTop1Hysteresis(), config, start=start, end=end)
    return result


def yearly_table(result):
    eq = result.equity_curve
    yearly = eq.resample("YE").agg(["first", "last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    return yearly


def print_metrics(label, result):
    m = result.metrics
    eq = result.equity_curve
    yearly = yearly_table(result)
    neg = int((yearly["ret"] < 0).sum())
    print(f"  {label}")
    print(f"    Capital final : R${m['final_capital']:,.2f}")
    print(f"    CAGR          : {m['cagr']*100:.2f}%")
    print(f"    Sharpe        : {m.get('sharpe',0):.2f}")
    print(f"    MaxDD         : {m['max_drawdown']*100:.2f}%")
    print(f"    Anos negativos: {neg}")
    print(f"    Trades        : {m.get('trades_count',0)}")


# ── FULL ────────────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  FULL  2010-01-01 -> {TODAY}")
print(f"{'='*65}")

t0 = time.perf_counter()
r7_full = run(TOP7, "2010-01-01", TODAY)
print_metrics("TOP-7 (novo)", r7_full)
print()

t1 = time.perf_counter()
r3_full = run(TOP3, "2010-01-01", TODAY)
print_metrics("TOP-3 (atual)", r3_full)
print(f"\n  (rodou em {time.perf_counter()-t0:.1f}s)")

# ── 3Y ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  3Y  {THREE_Y} -> {TODAY}")
print(f"{'='*65}")

r7_3y = run(TOP7, THREE_Y, TODAY)
print_metrics("TOP-7 (novo)", r7_3y)
print()

r3_3y = run(TOP3, THREE_Y, TODAY)
print_metrics("TOP-3 (atual)", r3_3y)

# ── Ano a ano ────────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  ANO A ANO — FULL (dip_top1_hysteresis)")
print(f"{'='*65}")
print(f"  {'Ano':4s}  {'TOP-7':>9}  {'TOP-3':>9}  {'Delta':>7}  {'Vencedor'}")
print(f"  {'-'*4}  {'-'*9}  {'-'*9}  {'-'*7}  {'-'*10}")

y7 = yearly_table(r7_full)
y3 = yearly_table(r3_full)

all_years = sorted(set(y7.index) | set(y3.index))
for yr in all_years:
    r7 = y7.loc[yr, "ret"] if yr in y7.index else float("nan")
    r3 = y3.loc[yr, "ret"] if yr in y3.index else float("nan")
    delta = r7 - r3 if not (pd.isna(r7) or pd.isna(r3)) else float("nan")
    winner = "TOP-7" if delta > 0 else ("TOP-3" if delta < 0 else "EMPATE")
    neg7 = "*" if not pd.isna(r7) and r7 < 0 else " "
    neg3 = "*" if not pd.isna(r3) and r3 < 0 else " "
    r7s = f"{r7*100:+.1f}%{neg7}" if not pd.isna(r7) else "  N/A  "
    r3s = f"{r3*100:+.1f}%{neg3}" if not pd.isna(r3) else "  N/A  "
    ds  = f"{delta*100:+.1f}%" if not pd.isna(delta) else "  N/A "
    print(f"  {yr.year}  {r7s:>9}  {r3s:>9}  {ds:>7}  {winner}")

print(f"\n  (* = ano negativo)")

# ── Solo de cada ticker no TOP-7 ─────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  CONTRIBUIÇÃO SOLO — cada ticker no TOP-7 (FULL)")
print(f"{'='*65}")
print(f"  {'Ticker':10s}  {'Final':>10}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'NegYr':>6}")
print(f"  {'-'*10}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}")
for t in TOP7:
    rs = run([t], "2010-01-01", TODAY)
    m = rs.metrics
    eq = rs.equity_curve
    yr = eq.resample("YE").agg(["first","last"])
    yr["ret"] = yr["last"]/yr["first"] - 1
    neg = int((yr["ret"]<0).sum())
    print(f"  {t.replace('.SA',''):10s}  R${m['final_capital']:8.2f}  {m['cagr']*100:6.2f}%  {m.get('sharpe',0):7.2f}  {m['max_drawdown']*100:6.2f}%  {neg:>6}")
