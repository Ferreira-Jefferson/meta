"""Confirmacao completa dos vencedores finais.

Vencedores da rodada final:
- high_window=22: R$158,780 / NegYrs=1
- high_window=25: R$158,780 / NegYrs=1
- high_window=30: R$158,780 / NegYrs=1
- high_window=40: R$170,821 / NegYrs=1
- high_window=60: R$170,821 / NegYrs=1

Parâmetros: sat0% + dip2% + hyst15% + lookback252 + skip21 + selic63
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest
from backtest.metrics import cagr, max_drawdown, sharpe
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis
from core.indicators import rolling_high

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref_df = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref_df.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
print(f"TODAY={TODAY}, THREE_Y={THREE_Y}")

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)

REF_FULL = 134_403.0
REF_3Y   = 2_264.0


class PH_HighWindow(PortfolioHysteresis):
    """PortfolioHysteresis com high_window e dip_pct configuráveis."""
    name = "ph_high_window"
    version = "1.0"

    def __init__(self, dip_pct=0.02, high_window=20, hysteresis=0.15,
                 confirm_months=2, redist_mode="pool", **kwargs):
        super().__init__(confirm_months=confirm_months, redist_mode=redist_mode, **kwargs)
        self.dip_pct = dip_pct
        self._hysteresis = hysteresis
        self._custom_high_window = high_window

    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        # Re-calcula dist_from_high com high_window customizado
        for t, df in panels.items():
            c = df["close"]
            hi = rolling_high(c, self._custom_high_window)
            self._dist_from_high[t] = (c / hi) - 1.0


def full_report(label, hw, sat_pct=0.00, dip=0.02, hyst=0.15, confirm=2):
    s_f = PH_HighWindow(dip_pct=dip, high_window=hw, hysteresis=hyst, confirm_months=confirm)
    s_3 = PH_HighWindow(dip_pct=dip, high_window=hw, hysteresis=hyst, confirm_months=confirm)
    r_full = run_portfolio_backtest(universe, s_f, config, "2010-01-01", TODAY,
                                    satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode="pool")
    r_3y   = run_portfolio_backtest(universe, s_3, config, THREE_Y, TODAY,
                                    satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode="pool")
    m = r_full.metrics
    m3 = r_3y.metrics
    eq = r_full.equity_curve
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    neg_yrs = [yr.year for yr, row in yearly.iterrows() if row["ret"] < 0]
    passed = m["final_capital"] > 150_000 and neg <= 1
    vs = m["final_capital"] - REF_FULL
    status = "PASSOU" if passed else "FALHOU"

    print(f"\n{'='*70}")
    print(f"RESULTADO: {label}")
    print(f"{'='*70}")
    print(f"  FULL: R${m['final_capital']:,.0f} / CAGR {m['cagr']*100:.2f}% / Sharpe {m['sharpe']:.2f} / MaxDD {m['max_drawdown']*100:.2f}% / NegYrs {neg}")
    print(f"  3Y:   R${m3['final_capital']:,.0f} / CAGR {m3['cagr']*100:.2f}% / Sharpe {m3['sharpe']:.2f}")
    print(f"  vs REF: {vs:+,.0f} ({vs/REF_FULL*100:+.1f}%)")
    print(f"  Anos negativos: {neg_yrs}")
    print(f"  STATUS: {status}")
    print()
    print("  Ano a ano:")
    for yr, row in yearly.iterrows():
        mark = " <-- NEGATIVO" if row["ret"] < 0 else ""
        print(f"    {yr.year}: {row['ret']*100:+.1f}%{mark}")
    return r_full, r_3y


print("=" * 70)
print("CONFIRMACAO COMPLETA DOS VENCEDORES FINAIS")
print(f"REF: R${REF_FULL:,.0f} / NegYrs=1")
print("=" * 70)

# REF para comparacao
s_r = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
s_r3 = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
r_ref_f = run_portfolio_backtest(universe, s_r, config, "2010-01-01", TODAY,
                                  satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
r_ref_3 = run_portfolio_backtest(universe, s_r3, config, THREE_Y, TODAY,
                                  satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
eq_ref = r_ref_f.equity_curve
yr_ref = eq_ref.resample("YE").agg(["first","last"])
yr_ref["ret"] = yr_ref["last"]/yr_ref["first"]-1
print(f"\nREF confirmado: R${r_ref_f.metrics['final_capital']:,.0f} / NegYrs={int((yr_ref['ret']<0).sum())}")

# Candidatos vencedores
full_report("W1 — sat0%+dip2%+hyst15%+hw22", hw=22)
full_report("W2 — sat0%+dip2%+hyst15%+hw30", hw=30)
full_report("W3 — sat0%+dip2%+hyst15%+hw40", hw=40)
full_report("W4 — sat0%+dip2%+hyst15%+hw60", hw=60)

# Teste do melhor com satelite mínimo para comparação
full_report("W5 — sat1%+dip2%+hyst15%+hw40", hw=40, sat_pct=0.01)
full_report("W6 — sat5%+dip2%+hyst15%+hw40", hw=40, sat_pct=0.05)

# Candidato mais conservador (menor risco)
print("\n" + "=" * 70)
print("SWEEP FINO hw=22 a hw=40 para encontrar o melhor ponto")
print("=" * 70)
for hw in [21, 22, 23, 24, 25, 26, 27, 28, 30, 35, 40, 45, 50]:
    s_f = PH_HighWindow(dip_pct=0.02, high_window=hw, hysteresis=0.15, confirm_months=2)
    s_3 = PH_HighWindow(dip_pct=0.02, high_window=hw, hysteresis=0.15, confirm_months=2)
    r_f = run_portfolio_backtest(universe, s_f, config, "2010-01-01", TODAY,
                                  satellite_pct=0.00, satellite_stop_pct=0.20, redist_mode="pool")
    r_3 = run_portfolio_backtest(universe, s_3, config, THREE_Y, TODAY,
                                  satellite_pct=0.00, satellite_stop_pct=0.20, redist_mode="pool")
    eq = r_f.equity_curve
    yr = eq.resample("YE").agg(["first","last"])
    yr["ret"] = yr["last"]/yr["first"]-1
    neg = int((yr["ret"]<0).sum())
    neg_yrs = [y.year for y, row in yr.iterrows() if row["ret"] < 0]
    passed = r_f.metrics["final_capital"] > 150_000 and neg <= 1
    mark = " <-- PASSOU!" if passed else ""
    print(f"  hw={hw:3d}: R${r_f.metrics['final_capital']:>9,.0f} / NegYrs={neg} {str(neg_yrs):20s} / 3Y R${r_3.metrics['final_capital']:>6,.0f}{mark}")
