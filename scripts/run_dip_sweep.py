"""Sweep fino em dip_pct e combinacoes para superar R$150k com NegYrs<=1 e MaxDD<=-33%.

H33 (sat0%+dip2%) = R$149,232 / NegYrs=1 / MaxDD=-35.12% — MUITO PROXIMO mas MaxDD falha
REF              = R$134,403 / NegYrs=1 / MaxDD=-32.99%

Hipoteses:
- Sweep dip_pct de 1.5% a 3.0%
- Combinacoes com satelite pequeno para reduzir MaxDD sem perder muito capital
- Combinacoes com histerese diferente
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

REF_FULL = 134_403.0


class PH_Dip(PortfolioHysteresis):
    name = "ph_dip"
    version = "1.0"
    def __init__(self, dip_pct=0.01, hysteresis=0.15, confirm_months=2, redist_mode="pool", **kwargs):
        super().__init__(confirm_months=confirm_months, redist_mode=redist_mode, **kwargs)
        self.dip_pct = dip_pct
        self._hysteresis = hysteresis


universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
results  = []


def run_quick(label, strategy, sat_pct=0.00):
    r = run_portfolio_backtest(universe, strategy, config, "2010-01-01", TODAY,
                               satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode="pool")
    r3 = run_portfolio_backtest(universe, PH_Dip(dip_pct=strategy.dip_pct, hysteresis=strategy._hysteresis,
                                                  confirm_months=strategy.signal_confirm_months),
                                config, THREE_Y, TODAY,
                                satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode="pool")
    m = r.metrics
    m3 = r3.metrics
    eq = r.equity_curve
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    neg_yrs = [yr.year for yr, row in yearly.iterrows() if row["ret"] < 0]
    vs = m["final_capital"] - REF_FULL
    passed = m["final_capital"] > 150_000 and m["max_drawdown"] >= -0.3299 and neg <= 1
    status = "PASSOU" if passed else "FALHOU"
    print(f"  {label:45s}: R${m['final_capital']:>8,.0f} / NegYrs={neg} {str(neg_yrs):15s} / MaxDD={m['max_drawdown']*100:.2f}% / 3Y R${m3['final_capital']:,.0f} | {status}")
    results.append({
        "label": label, "final": m["final_capital"], "cagr": m["cagr"],
        "sharpe": m["sharpe"], "maxdd": m["max_drawdown"], "neg": neg, "neg_yrs": neg_yrs,
        "final_3y": m3["final_capital"], "cagr_3y": m3["cagr"], "passed": passed
    })


print("=" * 80)
print("SWEEP DIP_PCT — sat0% com dip variavel")
print("=" * 80)
for dip in [0.015, 0.017, 0.018, 0.019, 0.020, 0.021, 0.022, 0.025, 0.030]:
    s = PH_Dip(dip_pct=dip, hysteresis=0.15, confirm_months=2)
    run_quick(f"sat0%+dip{dip*100:.1f}%+hyst15%", s, sat_pct=0.00)

print("\n" + "=" * 80)
print("SWEEP DIP_PCT — sat1% com dip variavel")
print("=" * 80)
for dip in [0.015, 0.018, 0.020, 0.022, 0.025, 0.030]:
    s = PH_Dip(dip_pct=dip, hysteresis=0.15, confirm_months=2)
    run_quick(f"sat1%+dip{dip*100:.1f}%+hyst15%", s, sat_pct=0.01)

print("\n" + "=" * 80)
print("SWEEP HISTERESE — sat0% + dip2% com histerese variavel")
print("=" * 80)
for hyst in [0.05, 0.08, 0.10, 0.12, 0.15, 0.17, 0.18, 0.20]:
    s = PH_Dip(dip_pct=0.020, hysteresis=hyst, confirm_months=2)
    run_quick(f"sat0%+dip2%+hyst{hyst*100:.0f}%", s, sat_pct=0.00)

print("\n" + "=" * 80)
print("COMBINACOES PROMISSORAS")
print("=" * 80)
# sat0% + dip2.5% + hyst15% (mais dip, menos entradas)
s = PH_Dip(dip_pct=0.025, hysteresis=0.15, confirm_months=2)
run_quick("sat0%+dip2.5%+hyst15%+confirm2", s, sat_pct=0.00)

# sat0% + dip2% + confirm3 (mais tempo no satellite, mas sat=0% entao irrelevante)
s = PH_Dip(dip_pct=0.020, hysteresis=0.15, confirm_months=3)
run_quick("sat0%+dip2%+hyst15%+confirm3", s, sat_pct=0.00)

# sat0% + dip2% + hyst=0.12 (um pouco mais rotacoes)
s = PH_Dip(dip_pct=0.020, hysteresis=0.12, confirm_months=2)
run_quick("sat0%+dip2%+hyst12%+confirm2", s, sat_pct=0.00)

# sat0% + dip1.8% + hyst=0.15
s = PH_Dip(dip_pct=0.018, hysteresis=0.15, confirm_months=2)
run_quick("sat0%+dip1.8%+hyst15%+confirm2", s, sat_pct=0.00)

# sat0.5% + dip2% + hyst15%  — teste de sat intermediario
class PH_Dip_Sat(PortfolioHysteresis):
    name = "ph_dip_sat"
    version = "1.0"
    def __init__(self, dip_pct=0.02, hysteresis=0.15, confirm_months=2, **kwargs):
        super().__init__(confirm_months=confirm_months, **kwargs)
        self.dip_pct = dip_pct
        self._hysteresis = hysteresis

for sp in [0.005, 0.01, 0.015, 0.02]:
    s = PH_Dip(dip_pct=0.020, hysteresis=0.15, confirm_months=2)
    run_quick(f"sat{sp*100:.1f}%+dip2%+hyst15%", s, sat_pct=sp)

# ===========================================================================
# RANKING FINAL
# ===========================================================================
print("\n" + "=" * 80)
print("RANKING — SWEEP DIP")
print("=" * 80)
print(f"  {'#':3}  {'Label':45}  {'Final':>10}  {'NegYrs':>7}  {'MaxDD':>8}  {'3Y':>8}  Status")
print(f"  {'-'*3}  {'-'*45}  {'-'*10}  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*6}")
print(f"  REF  {'REF (sat5%+dip1%+hyst15%)':45}  R${REF_FULL:>8,.0f}  {'1':>7}  {'-32.99%':>8}  {'R$2,264':>8}  ---")

sorted_r = sorted(results, key=lambda x: x["final"], reverse=True)
for i, r in enumerate(sorted_r, 1):
    lbl = r["label"][:45]
    status = "PASSOU" if r["passed"] else "FALHOU"
    print(f"  {i:3}  {lbl:45}  R${r['final']:>8,.0f}  {r['neg']:>7}  {r['maxdd']*100:>7.2f}%  R${r['final_3y']:>5,.0f}  {status}")

winners = [r for r in results if r["passed"]]
print(f"\n{'='*80}")
if winners:
    print(f"PASSOU A META: {len(winners)} hipotese(s)")
    for w in sorted(winners, key=lambda x: x["final"], reverse=True):
        print(f"  {w['label']}: R${w['final']:,.0f} / NegYrs={w['neg']} / MaxDD={w['maxdd']*100:.2f}%")
else:
    print("NENHUMA hipotese passou a meta completa.")
    top5 = sorted(results, key=lambda x: x["final"], reverse=True)[:5]
    for r in top5:
        gap = r["final"] - 150_000
        dd_gap = r["maxdd"] * 100 - (-32.99)
        print(f"  {r['label']}: R${r['final']:,.0f} (capital_gap={gap:+,.0f}, NegYrs={r['neg']}, DD_gap={dd_gap:+.2f}%)")
print("=" * 80)
