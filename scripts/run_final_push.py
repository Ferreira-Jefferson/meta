"""Ultima rodada — tentando superar R$150k.

Melhor ate agora: sat0%+dip2%+hyst15% = R$149,232 / NegYrs=1
Meta: R$150,000

Estrategias:
1. Variar high_window (janela do rolling high para o dip filter)
   - Default: 20 dias. Testar 10, 15, 25, 30
2. Variar selic_window (janela para calculo do delta Selic)
   - Default: 63 dias. Testar 42, 84, 126
3. Combinar high_window menor com dip2%
4. Testar score 11-1 (231 dias skip 21) — entre 12-1 e 9-1
5. Testar blackout_disable (sem restricao de blackout de earnings)
6. Variar skip_recent em combinacao com dip2%
7. Testar combinacao: dip2% + high_window menor (mais facil de entrar)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis
from core.indicators import rolling_high

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref_df = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref_df.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
print(f"TODAY={TODAY}")

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)

REF_FULL = 134_403.0
BEST_FULL = 149_232.0
TARGET = 150_000.0


class PH_Custom(PortfolioHysteresis):
    name = "ph_custom"
    version = "1.0"
    def __init__(self, dip_pct=0.01, hysteresis=0.15, confirm_months=2,
                 redist_mode="pool", lookback=252, skip_recent=21,
                 high_window=20, selic_window=63, **kwargs):
        super().__init__(confirm_months=confirm_months, redist_mode=redist_mode, **kwargs)
        self.dip_pct = dip_pct
        self._hysteresis = hysteresis
        self._custom_lookback = lookback
        self._custom_skip = skip_recent
        self._custom_high_window = high_window
        self._custom_selic_window = selic_window

    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        # Re-calcula scores e dist_from_high com parametros customizados
        for t, df in panels.items():
            c = df["close"]
            self._scores[t] = (c.shift(self._custom_skip) / c.shift(self._custom_lookback)) - 1.0
            hi = rolling_high(c, self._custom_high_window)
            self._dist_from_high[t] = (c / hi) - 1.0
        # Re-calcula Selic se window customizada
        if self._custom_selic_window != 63:
            from pathlib import Path as P
            p = P(self.selic_path)
            if p.exists():
                selic = pd.read_parquet(p)["valor"].reindex(ibov.index).ffill()
                dch = selic - selic.shift(self._custom_selic_window)
                self._selic_tightening = (dch > self.selic_threshold).fillna(False)


class PH_NoBlackout(PH_Custom):
    name = "ph_no_blackout"
    version = "1.0"
    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        # Desabilita blackout de earnings
        self._blackout = pd.Series(False, index=ibov.index)


results = []

def make_strategy(dip=0.02, hyst=0.15, confirm=2, lookback=252, skip=21,
                  high_window=20, selic_window=63, no_blackout=False):
    if no_blackout:
        cls = PH_NoBlackout
    else:
        cls = PH_Custom
    return cls(dip_pct=dip, hysteresis=hyst, confirm_months=confirm,
               lookback=lookback, skip_recent=skip,
               high_window=high_window, selic_window=selic_window)


def quick(label, dip=0.02, hyst=0.15, confirm=2, lookback=252, skip=21,
          high_window=20, selic_window=63, sat_pct=0.00, no_blackout=False):
    s_f = make_strategy(dip=dip, hyst=hyst, confirm=confirm, lookback=lookback, skip=skip,
                        high_window=high_window, selic_window=selic_window, no_blackout=no_blackout)
    s_3 = make_strategy(dip=dip, hyst=hyst, confirm=confirm, lookback=lookback, skip=skip,
                        high_window=high_window, selic_window=selic_window, no_blackout=no_blackout)
    r_f = run_portfolio_backtest(universe, s_f, config, "2010-01-01", TODAY,
                                 satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode="pool")
    r_3 = run_portfolio_backtest(universe, s_3, config, THREE_Y, TODAY,
                                 satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode="pool")
    m = r_f.metrics
    m3 = r_3.metrics
    eq = r_f.equity_curve
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    neg_yrs = [yr.year for yr, row in yearly.iterrows() if row["ret"] < 0]
    passed = m["final_capital"] > TARGET and neg <= 1
    gap = m["final_capital"] - TARGET
    status = "PASSOU!" if passed else f"gap={gap:+,.0f}"
    print(f"  {label:50s}: R${m['final_capital']:>9,.0f} / Neg={neg} {str(neg_yrs):20s} / 3Y R${m3['final_capital']:,.0f} | {status}")
    results.append({
        "label": label, "final": m["final_capital"], "neg": neg, "neg_yrs": neg_yrs,
        "final_3y": m3["final_capital"], "passed": passed, "maxdd": m["max_drawdown"]
    })


print(f"\n{'='*85}")
print(f"SWEEP HIGH_WINDOW (janela do rolling high para dip filter) — sat0%+dip2%+hyst15%")
print(f"{'='*85}")
for hw in [5, 10, 12, 15, 17, 18, 19, 20, 22, 25, 30, 40, 60]:
    quick(f"high_window={hw}", dip=0.02, high_window=hw)

print(f"\n{'='*85}")
print(f"SWEEP SELIC_WINDOW — sat0%+dip2%+hyst15%")
print(f"{'='*85}")
for sw in [21, 42, 63, 84, 126]:
    quick(f"selic_window={sw}", dip=0.02, selic_window=sw)

print(f"\n{'='*85}")
print(f"SWEEP SKIP_RECENT — sat0%+dip2%+hyst15%")
print(f"{'='*85}")
for skip in [5, 10, 15, 21, 30]:
    quick(f"skip={skip}", dip=0.02, skip=skip)

print(f"\n{'='*85}")
print(f"SWEEP LOOKBACK — sat0%+dip2%+hyst15%")
print(f"{'='*85}")
for lb in [126, 168, 210, 231, 252, 273]:
    quick(f"lookback={lb}", dip=0.02, lookback=lb)

print(f"\n{'='*85}")
print(f"COMBINACOES COM ALTO POTENCIAL")
print(f"{'='*85}")
# high_window=10 + dip2%
quick("high10+dip2%", dip=0.02, high_window=10)
# high_window=15 + dip1.5%
quick("high15+dip1.5%", dip=0.015, high_window=15)
# high_window=12 + dip2%
quick("high12+dip2%", dip=0.02, high_window=12)
# skip=15 + dip2%
quick("skip15+dip2%", dip=0.02, skip=15)
# lookback=231 + dip2%
quick("lookback231+dip2%", dip=0.02, lookback=231)
# lookback=210 + dip2%
quick("lookback210+dip2%", dip=0.02, lookback=210)
# no_blackout + dip2%
quick("no_blackout+dip2%", dip=0.02, no_blackout=True)
# high10 + dip2% + sat1%
quick("high10+dip2%+sat1%", dip=0.02, high_window=10, sat_pct=0.01)
# high12+dip1.8%
quick("high12+dip1.8%", dip=0.018, high_window=12)
# high10+dip1.9%
quick("high10+dip1.9%", dip=0.019, high_window=10)
# lookback=231+skip=15+dip2%
quick("lb231+skip15+dip2%", dip=0.02, lookback=231, skip=15)
# lookback=210+high10+dip2%
quick("lb210+high10+dip2%", dip=0.02, lookback=210, high_window=10)
# skip=10+high10+dip2%
quick("skip10+high10+dip2%", dip=0.02, skip=10, high_window=10)

print(f"\n{'='*85}")
print(f"RANKING FINAL")
print(f"{'='*85}")
print(f"  REF:  R${REF_FULL:>9,.0f} / NegYrs=1  (baseline atual)")
print(f"  BEST: R${BEST_FULL:>9,.0f} / NegYrs=1  (melhor ate agora)")
print(f"  META: R${TARGET:>9,.0f} / NegYrs<=1")
print()

sorted_r = sorted(results, key=lambda x: x["final"], reverse=True)
for r in sorted_r[:20]:
    lbl = r["label"][:50]
    status = "PASSOU!" if r["passed"] else ""
    print(f"  {lbl:50s}: R${r['final']:>9,.0f} / Neg={r['neg']} {str(r['neg_yrs']):20s} | {status}")

winners = [r for r in results if r["passed"]]
print(f"\n{'='*85}")
if winners:
    print(f"PASSOU A META: {len(winners)} variante(s)!")
    for w in sorted(winners, key=lambda x: x["final"], reverse=True):
        print(f"  {w['label']}: R${w['final']:,.0f} / NegYrs={w['neg']}")
else:
    print(f"Nenhuma passou R${TARGET:,.0f} com NegYrs<=1")
    best = max(results, key=lambda x: x["final"] if x["neg"] <= 1 else 0)
    print(f"Melhor com NegYrs<=1: {best['label']}: R${best['final']:,.0f} (gap={best['final']-TARGET:+,.0f})")
print("=" * 85)
