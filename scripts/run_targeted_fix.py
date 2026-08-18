"""Hipoteses focadas em corrigir NegYrs=2011 e NegYrs=2023 do sat0% variant.

sat0% = R$157k com NegYrs=3 (2011:-0.2%, 2022:-4.9%, 2023:-1.4%)
REF   = R$136k com NegYrs=1 (apenas 2022:-4.9%)

Objetivo: encontrar variante com R$>150k e NegYrs<=1

Abordagens:
  H30 - stop_loss=0.05 (stop apertadissimo no principal, protege anos ruins)
  H31 - sat0% + selic_thr=0.004 (gate um pouco mais agressivo)
  H32 - sat1% + selic_thr=0.003 (gate mais agressivo com sat minimo)
  H33 - sat0% + dip_pct=0.02 (dip mais restritivo, entra menos)
  H34 - sat0% + hyst=0.25 (histerese mais alta, rotacoes muito menos freq)
  H35 - sat0% + hyst=0.30
  H36 - sat1% + hyst=0.20 (sat minimo + alta histerese)
  H37 - lookback=315 skip=21 (score de 15 meses) — captura momentum mais longo
  H38 - lookback=252 skip=21 + sat=1% + confirm3
  H39 - sat0% + selic_thr=0.004 + hyst=0.15
  H40 - sat0% + stop_loss=0.08 (stop intermediario)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis
from strategy.base import Enter, Exit

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

REF_FULL = 134_403.0
REF_3Y   = 2_264.0


class PortfolioHysteresisCustom(PortfolioHysteresis):
    name = "ph_custom"
    version = "1.0"
    def __init__(self, hysteresis=0.15, confirm_months=2, redist_mode="pool", **kwargs):
        super().__init__(confirm_months=confirm_months, redist_mode=redist_mode, **kwargs)
        self._hysteresis = hysteresis


class PH_Selic(PortfolioHysteresisCustom):
    name = "ph_selic"
    version = "1.0"
    def __init__(self, selic_threshold=0.005, **kwargs):
        super().__init__(**kwargs)
        self._custom_selic_threshold = selic_threshold
    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        from pathlib import Path as P
        p = P(self.selic_path)
        if p.exists():
            selic = pd.read_parquet(p)["valor"].reindex(ibov.index).ffill()
            dch = selic - selic.shift(self.selic_window)
            self._selic_tightening = (dch > self._custom_selic_threshold).fillna(False)


class PH_ScoreWindow(PortfolioHysteresisCustom):
    name = "ph_score_window"
    version = "1.0"
    def __init__(self, lookback=252, skip_recent=21, **kwargs):
        super().__init__(**kwargs)
        self._custom_lookback = lookback
        self._custom_skip = skip_recent
    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        for t, df in panels.items():
            c = df["close"]
            self._scores[t] = (c.shift(self._custom_skip) / c.shift(self._custom_lookback)) - 1.0


class PH_Dip(PortfolioHysteresisCustom):
    name = "ph_dip"
    version = "1.0"
    def __init__(self, dip_pct=0.01, **kwargs):
        super().__init__(**kwargs)
        self.dip_pct = dip_pct


universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
results  = []


def run_and_report(label, strategy, strategy_3y, sat_pct=0.00, stop_pct=0.20,
                   rmode="pool", cfg=None):
    if cfg is None:
        cfg = config
    r_full = run_portfolio_backtest(universe, strategy, cfg, "2010-01-01", TODAY,
                                    satellite_pct=sat_pct, satellite_stop_pct=stop_pct, redist_mode=rmode)
    r_3y   = run_portfolio_backtest(universe, strategy_3y, cfg, THREE_Y, TODAY,
                                    satellite_pct=sat_pct, satellite_stop_pct=stop_pct, redist_mode=rmode)
    m = r_full.metrics
    m3 = r_3y.metrics
    eq = r_full.equity_curve
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    neg_yrs = [yr.year for yr, row in yearly.iterrows() if row["ret"] < 0]
    vs = m["final_capital"] - REF_FULL
    passed = m["final_capital"] > 150_000 and m["max_drawdown"] >= -0.3299 and neg <= 1
    status = "PASSOU" if passed else "FALHOU"
    print(f"\n{label}")
    print(f"  FULL: R${m['final_capital']:,.0f} / CAGR {m['cagr']*100:.2f}% / Sharpe {m['sharpe']:.2f} / MaxDD {m['max_drawdown']*100:.2f}% / NegYrs {neg} {neg_yrs}")
    print(f"  3Y:   R${m3['final_capital']:,.0f} / CAGR {m3['cagr']*100:.2f}%")
    print(f"  vs REF: {vs:+,.0f} ({vs/REF_FULL*100:+.1f}%) | {status}")
    results.append({
        "label": label, "final": m["final_capital"], "cagr": m["cagr"],
        "sharpe": m["sharpe"], "maxdd": m["max_drawdown"], "neg": neg, "neg_yrs": neg_yrs,
        "final_3y": m3["final_capital"], "cagr_3y": m3["cagr"], "passed": passed
    })


print("=" * 75)
print("RODADA 3 — tentando corrigir NegYrs sem perder capital")
print(f"REF: R${REF_FULL:,.0f} / NegYrs=1 (2022)")
print(f"SAT0%: R$157,794 / NegYrs=3 (2011, 2022, 2023)")
print("=" * 75)

# H30 — stop=5%
print("\n[H30] sat0% + stop=5% ...")
cfg5 = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.05)
run_and_report("H30 -- sat0%+stop5%",
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    sat_pct=0.00, cfg=cfg5)

# H40 — stop=8%
print("\n[H40] sat0% + stop=8% ...")
cfg8 = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.08)
run_and_report("H40 -- sat0%+stop8%",
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    sat_pct=0.00, cfg=cfg8)

# H31 — sat0% + selic_thr=0.004
print("\n[H31] sat0% + selic_thr=0.004 ...")
run_and_report("H31 -- sat0%+selic004",
    PH_Selic(selic_threshold=0.004, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PH_Selic(selic_threshold=0.004, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# H32 — sat1% + selic_thr=0.003
print("\n[H32] sat1% + selic_thr=0.003 ...")
run_and_report("H32 -- sat1%+selic003",
    PH_Selic(selic_threshold=0.003, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PH_Selic(selic_threshold=0.003, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.01)

# H33 — sat0% + dip=2%
print("\n[H33] sat0% + dip_pct=2% ...")
run_and_report("H33 -- sat0%+dip2%",
    PH_Dip(dip_pct=0.02, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PH_Dip(dip_pct=0.02, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# H34 — sat0% + hyst=0.25
print("\n[H34] sat0% + hyst=25% ...")
run_and_report("H34 -- sat0%+hyst25%",
    PortfolioHysteresisCustom(hysteresis=0.25, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisCustom(hysteresis=0.25, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# H35 — sat0% + hyst=0.30
print("\n[H35] sat0% + hyst=30% ...")
run_and_report("H35 -- sat0%+hyst30%",
    PortfolioHysteresisCustom(hysteresis=0.30, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisCustom(hysteresis=0.30, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# H36 — sat1% + hyst=0.20
print("\n[H36] sat1% + hyst=20% ...")
run_and_report("H36 -- sat1%+hyst20%",
    PortfolioHysteresisCustom(hysteresis=0.20, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisCustom(hysteresis=0.20, confirm_months=2, redist_mode="pool"),
    sat_pct=0.01)

# H37 — lookback=315 (score 15 meses)
print("\n[H37] lookback=315 (score 15m) ...")
run_and_report("H37 -- lookback315 (15m score)",
    PH_ScoreWindow(lookback=315, skip_recent=21, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PH_ScoreWindow(lookback=315, skip_recent=21, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# H38 — sat1% + confirm3
print("\n[H38] sat1% + confirm3 ...")
run_and_report("H38 -- sat1%+confirm3",
    PortfolioHysteresis(confirm_months=3, redist_mode="pool"),
    PortfolioHysteresis(confirm_months=3, redist_mode="pool"),
    sat_pct=0.01)

# H39 — sat0% + selic_thr=0.004 + hyst=0.15
print("\n[H39] sat0% + selic004 + hyst15% ...")
run_and_report("H39 -- sat0%+selic004+hyst15%",
    PH_Selic(selic_threshold=0.004, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PH_Selic(selic_threshold=0.004, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# H41 — sat0% + dip=0.5% (menos restritivo que 1%)
print("\n[H41] sat0% + dip=0.5% ...")
run_and_report("H41 -- sat0%+dip0.5%",
    PH_Dip(dip_pct=0.005, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PH_Dip(dip_pct=0.005, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# H42 — sat0% + dip=0% (sem dip filter)
print("\n[H42] sat0% + no_dip ...")
run_and_report("H42 -- sat0%+no_dip",
    PH_Dip(dip_pct=0.0001, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PH_Dip(dip_pct=0.0001, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# H43 — sat=1% + hyst=0.15 + selic=0.004 (combinacao suave)
print("\n[H43] sat1%+hyst15%+selic004 ...")
run_and_report("H43 -- sat1%+hyst15%+selic004",
    PH_Selic(selic_threshold=0.004, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PH_Selic(selic_threshold=0.004, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.01)

# H44 — sat=2% + hyst=0.20 (mais histerese, menos satelite)
print("\n[H44] sat2%+hyst20% ...")
run_and_report("H44 -- sat2%+hyst20%",
    PortfolioHysteresisCustom(hysteresis=0.20, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisCustom(hysteresis=0.20, confirm_months=2, redist_mode="pool"),
    sat_pct=0.02)

# ===========================================================================
# RANKING FINAL
# ===========================================================================
print("\n" + "=" * 75)
print("RANKING — RODADA 3")
print("=" * 75)
print(f"  {'#':3}  {'Label':40}  {'Final':>10}  {'NegYrs':>7}  {'MaxDD':>7}  Status")
print(f"  {'-'*3}  {'-'*40}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*6}")
print(f"  REF  {'REF (sat5%+confirm2)':40}  R${REF_FULL:>8,.0f}  {'1':>7}  {'-32.99%':>7}  ---")

sorted_r = sorted(results, key=lambda x: x["final"], reverse=True)
for i, r in enumerate(sorted_r, 1):
    lbl = r["label"][:40]
    status = "PASSOU" if r["passed"] else "FALHOU"
    print(f"  {i:3}  {lbl:40}  R${r['final']:>8,.0f}  {r['neg']:>7}  {r['maxdd']*100:>6.2f}%  {status}")

winners = [r for r in results if r["passed"]]
print(f"\n{'='*75}")
if winners:
    print(f"PASSOU A META: {len(winners)} hipotese(s)")
    for w in sorted(winners, key=lambda x: x["final"], reverse=True):
        print(f"  {w['label']}: R${w['final']:,.0f}")
else:
    print("NENHUMA hipotese passou a meta completa.")
    top5 = sorted(results, key=lambda x: x["final"], reverse=True)[:5]
    for r in top5:
        gap = r["final"] - 150_000
        print(f"  {r['label']}: R${r['final']:,.0f} (gap={gap:+,.0f}, NegYrs={r['neg']}, {r['neg_yrs']})")
print("=" * 75)
