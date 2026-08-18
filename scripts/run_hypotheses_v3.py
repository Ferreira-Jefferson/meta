"""Segunda rodada de hipoteses - foco em superar R$150k com NegYrs<=1.

Insights da rodada 1:
- DipTop1Hysteresis (sem satelite) = R$155k mas NegYrs=3
- portfolio_hysteresis (REF) = R$136k, NegYrs=1
- Satelites custam ~R$19k de capital mas salvam 2 anos negativos

Novas hipoteses:
  H15 - satellite_pct=0% (= hysteresis puro via engine portfolio)
  H16 - satellite_pct=2% (satelite menor)
  H17 - satellite_pct=3% (satelite menor)
  H18 - Selic gate mais restritivo: threshold=0.003 (menos conservador)
  H19 - Selic gate mais liberal: threshold=0.008 (mais conservador)
  H20 - confirm_months=2 + dip_pct=0 (sempre entra, sem esperar dip)
  H21 - skip_recent=10 em vez de 21 (momentum mais recente)
  H22 - skip_recent=42 em vez de 21 (momentum menos recente)
  H23 - lookback=252 skip=21 + no_selic (sem gate Selic, testa impacto)
  H24 - hysteresis=0.05 + sat5pct (mais rotacoes)
  H25 - combinacao: sat2pct + confirm3 (satelite minimo, mais tempo)
  H26 - combinacao: sat0pct + hyst10% (sem satelite, mais rotacoes)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest, _Sat, RedistMode
from backtest.costs import apply_slippage, fees_for_leg
from backtest.engine import BacktestResult, _Position, _enrich, _snapshot, _positions_view
from backtest.metrics import cagr, calmar, max_drawdown, sharpe, sortino, trade_stats
from core.config import BacktestConfig, BENCHMARK
from core.models import ExitReason, Trade
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis
from strategy.h3_hysteresis import DipTop1Hysteresis
from strategy.base import AdjustStop, Enter, Exit

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)

REF_FULL = 134_403.0
REF_3Y   = 2_264.0


# ===========================================================================
# Classes customizadas
# ===========================================================================
class PortfolioHysteresisCustom(PortfolioHysteresis):
    name = "portfolio_hysteresis_custom"
    version = "1.0"
    def __init__(self, hysteresis=0.15, confirm_months=2, redist_mode="pool", **kwargs):
        super().__init__(confirm_months=confirm_months, redist_mode=redist_mode, **kwargs)
        self._hysteresis = hysteresis


class PortfolioHysteresisScoreWindow(PortfolioHysteresisCustom):
    name = "portfolio_hysteresis_score_window"
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


class PortfolioHysteresisDip(PortfolioHysteresisCustom):
    name = "portfolio_hysteresis_dip"
    version = "1.0"
    def __init__(self, dip_pct=0.01, **kwargs):
        super().__init__(**kwargs)
        self.dip_pct = dip_pct


class PortfolioHysteresisSelic(PortfolioHysteresisCustom):
    """Versao com threshold Selic configuravel."""
    name = "portfolio_hysteresis_selic"
    version = "1.0"
    def __init__(self, selic_threshold=0.005, **kwargs):
        super().__init__(**kwargs)
        self._custom_selic_threshold = selic_threshold
    def initialize(self, panels, ibov):
        from pathlib import Path as P
        # Recalcula selic_tightening com threshold customizado
        super().initialize(panels, ibov)
        p = P(self.selic_path)
        if p.exists():
            selic = pd.read_parquet(p)["valor"].reindex(ibov.index).ffill()
            dch = selic - selic.shift(self.selic_window)
            self._selic_tightening = (dch > self._custom_selic_threshold).fillna(False)
        else:
            self._selic_tightening = pd.Series(False, index=ibov.index)


class PortfolioHysteresisNoSelic(PortfolioHysteresisCustom):
    """Versao sem gate Selic (sempre investe)."""
    name = "portfolio_hysteresis_no_selic"
    version = "1.0"
    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        self._selic_tightening = pd.Series(False, index=ibov.index)


class PortfolioHysteresisNoDip(PortfolioHysteresisCustom):
    """Versao sem dip filter (entra imediatamente no rank-1)."""
    name = "portfolio_hysteresis_no_dip"
    version = "1.0"
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dip_pct = 0.0001  # praticamente sem filtro


def neg_years(eq):
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    return int((yearly["ret"] < 0).sum())


results = []

def run_and_report(label, strategy_full, strategy_3y, sat_pct=0.05, stop_pct=0.20, rmode="pool"):
    r_full = run_portfolio_backtest(universe, strategy_full, config, "2010-01-01", TODAY,
                                    satellite_pct=sat_pct, satellite_stop_pct=stop_pct, redist_mode=rmode)
    r_3y   = run_portfolio_backtest(universe, strategy_3y,  config, THREE_Y, TODAY,
                                    satellite_pct=sat_pct, satellite_stop_pct=stop_pct, redist_mode=rmode)
    m = r_full.metrics
    m3 = r_3y.metrics
    neg = neg_years(r_full.equity_curve)
    vs = m["final_capital"] - REF_FULL
    passed = m["final_capital"] > 150_000 and m["max_drawdown"] >= -0.3299 and neg <= 1
    status = "PASSOU" if passed else "FALHOU"
    print(f"\n{label}")
    print(f"  FULL: R${m['final_capital']:,.0f} / CAGR {m['cagr']*100:.2f}% / Sharpe {m['sharpe']:.2f} / MaxDD {m['max_drawdown']*100:.2f}% / NegYrs {neg}")
    print(f"  3Y:   R${m3['final_capital']:,.0f} / CAGR {m3['cagr']*100:.2f}%")
    print(f"  vs REF: {vs:+,.0f} ({vs/REF_FULL*100:+.1f}%) | {status}")
    results.append({
        "label": label, "final": m["final_capital"], "cagr": m["cagr"],
        "sharpe": m["sharpe"], "maxdd": m["max_drawdown"], "neg": neg,
        "final_3y": m3["final_capital"], "cagr_3y": m3["cagr"], "passed": passed
    })
    return r_full, r_3y


print("=" * 70)
print("RODADA 2 — hipoteses focadas em capital > R$150k")
print(f"REF atual: R${REF_FULL:,.0f}")
print("=" * 70)

# ===========================================================================
# H15 - satellite_pct=0% (equivale ao hysteresis puro via engine portfolio)
# ===========================================================================
print("\n[H15] satellite_pct=0% ...")
run_and_report("H15 -- sat0pct (hyst puro via portfolio engine)",
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    sat_pct=0.00, stop_pct=0.20)

# ===========================================================================
# H16 - satellite_pct=2%
# ===========================================================================
print("\n[H16] satellite_pct=2% ...")
run_and_report("H16 -- sat2pct+confirm2",
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    sat_pct=0.02, stop_pct=0.20)

# ===========================================================================
# H17 - satellite_pct=3%
# ===========================================================================
print("\n[H17] satellite_pct=3% ...")
run_and_report("H17 -- sat3pct+confirm2",
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    sat_pct=0.03, stop_pct=0.20)

# ===========================================================================
# H18 - Selic threshold=0.003 (menos conservador - entra mais vezes)
# ===========================================================================
print("\n[H18] Selic threshold=0.003 ...")
run_and_report("H18 -- selic_thr=0.003",
    PortfolioHysteresisSelic(selic_threshold=0.003, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisSelic(selic_threshold=0.003, hysteresis=0.15, confirm_months=2, redist_mode="pool"))

# ===========================================================================
# H19 - Selic threshold=0.008 (mais conservador - sai mais cedo)
# ===========================================================================
print("\n[H19] Selic threshold=0.008 ...")
run_and_report("H19 -- selic_thr=0.008",
    PortfolioHysteresisSelic(selic_threshold=0.008, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisSelic(selic_threshold=0.008, hysteresis=0.15, confirm_months=2, redist_mode="pool"))

# ===========================================================================
# H20 - sem dip filter (entra imediatamente)
# ===========================================================================
print("\n[H20] sem dip filter ...")
run_and_report("H20 -- no_dip_filter",
    PortfolioHysteresisNoDip(hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisNoDip(hysteresis=0.15, confirm_months=2, redist_mode="pool"))

# ===========================================================================
# H21 - skip_recent=10 (momentum mais recente - ignora menos dias)
# ===========================================================================
print("\n[H21] skip_recent=10 ...")
run_and_report("H21 -- skip10 (momentum recente)",
    PortfolioHysteresisScoreWindow(lookback=252, skip_recent=10, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisScoreWindow(lookback=252, skip_recent=10, hysteresis=0.15, confirm_months=2, redist_mode="pool"))

# ===========================================================================
# H22 - skip_recent=42 (ignora 2 meses recentes)
# ===========================================================================
print("\n[H22] skip_recent=42 ...")
run_and_report("H22 -- skip42 (ignora 2m recentes)",
    PortfolioHysteresisScoreWindow(lookback=252, skip_recent=42, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisScoreWindow(lookback=252, skip_recent=42, hysteresis=0.15, confirm_months=2, redist_mode="pool"))

# ===========================================================================
# H23 - sem Selic gate
# ===========================================================================
print("\n[H23] sem Selic gate ...")
run_and_report("H23 -- no_selic_gate",
    PortfolioHysteresisNoSelic(hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisNoSelic(hysteresis=0.15, confirm_months=2, redist_mode="pool"))

# ===========================================================================
# H24 - hysteresis=0.05 + sat5pct (rotacoes mais frequentes)
# ===========================================================================
print("\n[H24] hysteresis=5% ...")
run_and_report("H24 -- hyst5%+sat5pct",
    PortfolioHysteresisCustom(hysteresis=0.05, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisCustom(hysteresis=0.05, confirm_months=2, redist_mode="pool"))

# ===========================================================================
# H25 - sat2pct + confirm3 (satelite minimo, tempo de confirmacao maior)
# ===========================================================================
print("\n[H25] sat2pct+confirm3 ...")
run_and_report("H25 -- sat2pct+confirm3",
    PortfolioHysteresis(confirm_months=3, redist_mode="pool"),
    PortfolioHysteresis(confirm_months=3, redist_mode="pool"),
    sat_pct=0.02, stop_pct=0.20)

# ===========================================================================
# H26 - sat0pct + hyst=10% (sem satelite, mais rotacoes)
# ===========================================================================
print("\n[H26] sat0pct+hyst10% ...")
run_and_report("H26 -- sat0pct+hyst10%",
    PortfolioHysteresisCustom(hysteresis=0.10, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisCustom(hysteresis=0.10, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00, stop_pct=0.20)

# ===========================================================================
# H27 - sat0pct + hyst5% (sem satelite, muitas rotacoes)
# ===========================================================================
print("\n[H27] sat0pct+hyst5% ...")
run_and_report("H27 -- sat0pct+hyst5%",
    PortfolioHysteresisCustom(hysteresis=0.05, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisCustom(hysteresis=0.05, confirm_months=2, redist_mode="pool"),
    sat_pct=0.00, stop_pct=0.20)

# ===========================================================================
# H28 - no_dip + sat5pct + confirm2 (sem espera de dip mas com satelite)
# ===========================================================================
print("\n[H28] no_dip+sat5pct+confirm2 ...")
run_and_report("H28 -- no_dip+sat5pct+confirm2",
    PortfolioHysteresisNoDip(hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisNoDip(hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    sat_pct=0.05, stop_pct=0.20)

# ===========================================================================
# H29 - score 9-1 + sat5pct + confirm2 (window diferente)
# ===========================================================================
print("\n[H29] score9-1+sat5pct+confirm2 ...")
run_and_report("H29 -- score9-1+sat5pct+confirm2",
    PortfolioHysteresisScoreWindow(lookback=189, skip_recent=21, hysteresis=0.15, confirm_months=2, redist_mode="pool"),
    PortfolioHysteresisScoreWindow(lookback=189, skip_recent=21, hysteresis=0.15, confirm_months=2, redist_mode="pool"))

# ===========================================================================
# RANKING FINAL
# ===========================================================================
print("\n" + "=" * 70)
print("RANKING FINAL — RODADA 2 (por capital final FULL)")
print("=" * 70)
print(f"  {'#':3}  {'Label':40}  {'Final':>10}  {'CAGR':>7}  {'MaxDD':>7}  {'NegYrs':>7}  Status")
print(f"  {'-'*3}  {'-'*40}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}")
print(f"  REF  {'portfolio_hysteresis (REF)':40}  R${REF_FULL:>8,.0f}  {'34.33%':>7}  {'-32.99%':>7}  {'1':>7}  ---")

sorted_r = sorted(results, key=lambda x: x["final"], reverse=True)
for i, r in enumerate(sorted_r, 1):
    lbl = r["label"][:40]
    status = "PASSOU" if r["passed"] else "FALHOU"
    print(f"  {i:3}  {lbl:40}  R${r['final']:>8,.0f}  {r['cagr']*100:>6.2f}%  {r['maxdd']*100:>6.2f}%  {r['neg']:>7}  {status}")

winners = [r for r in results if r["passed"]]
print(f"\n{'='*70}")
if winners:
    print(f"PASSOU A META: {len(winners)} hipotese(s)")
    for w in sorted(winners, key=lambda x: x["final"], reverse=True):
        print(f"  {w['label']}: R${w['final']:,.0f}")
else:
    print("NENHUMA hipotese passou a meta completa.")
    top5 = sorted(results, key=lambda x: x["final"], reverse=True)[:5]
    print("Top-5 mais proximas:")
    for r in top5:
        gap = r["final"] - 150_000
        print(f"  {r['label']}: R${r['final']:,.0f} (gap={gap:+,.0f}, NegYrs={r['neg']})")
print("=" * 70)
