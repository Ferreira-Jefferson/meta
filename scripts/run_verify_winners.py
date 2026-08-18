"""Verifica os vencedores encontrados pelo agente com metodo limpo (kwargs nativos)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
ref_df = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref_df.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=1000.0, lot_size=1, stop_loss_pct=0.15)

REF_CAPITAL = 134_403.0
REF_NEGYRS  = 1
REF_DD      = -0.3299


def make(confirm=2, redist="pool", dip=0.01, hw=20):
    return PortfolioHysteresis(confirm_months=confirm, redist_mode=redist,
                               dip_pct=dip, high_window=hw)


def report(label, sat_pct, confirm=2, redist="pool", dip=0.01, hw=20):
    s1 = make(confirm, redist, dip, hw)
    s2 = make(confirm, redist, dip, hw)
    rf = run_portfolio_backtest(universe, s1, config, "2010-01-01", TODAY,
                                satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode=redist)
    r3 = run_portfolio_backtest(universe, s2, config, THREE_Y, TODAY,
                                satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode=redist)
    mf, m3 = rf.metrics, r3.metrics
    eq = rf.equity_curve
    yr = eq.resample("YE").agg(["first","last"])
    yr["ret"] = yr["last"]/yr["first"]-1
    neg = int((yr["ret"]<0).sum())
    neg_yrs = [y.year for y, row in yr.iterrows() if row["ret"]<0]

    beats_capital = mf["final_capital"] > 150_000
    beats_negyrs  = neg <= REF_NEGYRS
    beats_dd      = mf["max_drawdown"] >= REF_DD
    passed = beats_capital and beats_negyrs and beats_dd
    status = "PASSOU" if passed else "FALHOU"

    print(f"\n  {'='*65}")
    print(f"  {label}")
    print(f"  {'='*65}")
    print(f"  FULL: R${mf['final_capital']:>9,.0f} / CAGR {mf['cagr']*100:.2f}% / Sharpe {mf['sharpe']:.2f} / MaxDD {mf['max_drawdown']*100:.2f}% / NegYrs {neg} {neg_yrs}")
    print(f"  3Y:   R${m3['final_capital']:>9,.0f} / CAGR {m3['cagr']*100:.2f}% / Sharpe {m3['sharpe']:.2f}")
    delta = mf["final_capital"] - REF_CAPITAL
    print(f"  vs REF: {delta:+,.0f} ({delta/REF_CAPITAL*100:+.1f}%) | capital>150k:{beats_capital} | NegYrs<={REF_NEGYRS}:{beats_negyrs} | DD>={REF_DD*100:.1f}%:{beats_dd}")
    print(f"  STATUS: {status}")
    return mf["final_capital"], neg, mf["max_drawdown"], passed


print("Verificacao dos vencedores — 2026-08-15")
print(f"REF: R${REF_CAPITAL:,.0f} / NegYrs={REF_NEGYRS} / MaxDD={REF_DD*100:.1f}%\n")

results = []
CASES = [
    ("REF (sat5%+dip1%+hw20)",             0.05, dict(dip=0.01, hw=20)),
    ("W3  (sat0%+dip2%+hw40)",             0.00, dict(dip=0.02, hw=40)),
    ("W3s (sat5%+dip2%+hw40)",             0.05, dict(dip=0.02, hw=40)),
    ("W-hw21 (sat0%+dip2%+hw21)",          0.00, dict(dip=0.02, hw=21)),
    ("W-hw30 (sat0%+dip2%+hw30)",          0.00, dict(dip=0.02, hw=30)),
    ("W-hw60 (sat0%+dip2%+hw60)",          0.00, dict(dip=0.02, hw=60)),
]

for label, sat, kw in CASES:
    fc, ng, dd, ok = report(label, sat, **kw)
    results.append((label, fc, ng, dd, ok))

print(f"\n\n  RESUMO")
print(f"  {'Variante':30s}  {'Final':>10}  {'NegYrs':>6}  {'MaxDD':>7}  {'Status':>6}")
print(f"  {'-'*30}  {'-'*10}  {'-'*6}  {'-'*7}  {'-'*6}")
for label, fc, ng, dd, ok in results:
    st = "PASSOU" if ok else "falhou"
    print(f"  {label:30s}  R${fc:>8,.0f}  {ng:>6}  {dd*100:>6.1f}%  {st}")
