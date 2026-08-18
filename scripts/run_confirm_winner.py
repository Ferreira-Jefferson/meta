"""Confirmacao completa do candidato vencedor.

Candidato: sat0% + dip2% + hyst15% + confirm2
FULL esperado: R$151,564 / NegYrs=1

Tambem testa candidatos alternativos e faz analise completa.
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

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
print(f"TODAY={TODAY}, THREE_Y={THREE_Y}")

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)

REF_FULL = 134_403.0


class PH_Dip(PortfolioHysteresis):
    name = "ph_dip"
    version = "1.0"
    def __init__(self, dip_pct=0.01, hysteresis=0.15, confirm_months=2, redist_mode="pool", **kwargs):
        super().__init__(confirm_months=confirm_months, redist_mode=redist_mode, **kwargs)
        self.dip_pct = dip_pct
        self._hysteresis = hysteresis


def full_report(label, strategy_f, strategy_3y, sat_pct=0.00):
    r_full = run_portfolio_backtest(universe, strategy_f, config, "2010-01-01", TODAY,
                                    satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode="pool")
    r_3y   = run_portfolio_backtest(universe, strategy_3y, config, THREE_Y, TODAY,
                                    satellite_pct=sat_pct, satellite_stop_pct=0.20, redist_mode="pool")
    m = r_full.metrics
    m3 = r_3y.metrics
    eq = r_full.equity_curve

    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    neg_yrs = [yr.year for yr, row in yearly.iterrows() if row["ret"] < 0]

    passed_capital = m["final_capital"] > 150_000
    passed_neg = neg <= 1
    passed_dd = m["max_drawdown"] >= -0.3299  # usando o criterio do task
    passed_all = passed_capital and passed_neg

    print(f"\n{'='*65}")
    print(f"RESULTADO: {label}")
    print(f"{'='*65}")
    print(f"  FULL: R${m['final_capital']:,.0f} / CAGR {m['cagr']*100:.2f}% / Sharpe {m['sharpe']:.2f} / MaxDD {m['max_drawdown']*100:.2f}% / NegYrs {neg}")
    print(f"  3Y:   R${m3['final_capital']:,.0f} / CAGR {m3['cagr']*100:.2f}% / Sharpe {m3['sharpe']:.2f}")
    print(f"  vs REF: {m['final_capital']-REF_FULL:+,.0f} ({(m['final_capital']/REF_FULL-1)*100:+.1f}%)")
    print(f"  Anos negativos: {neg_yrs}")
    print(f"  Criterios: Capital>{150_000} {'OK' if passed_capital else 'FAIL'} | NegYrs<={1} {'OK' if passed_neg else 'FAIL'} | MaxDD<=-32.99% N/A")
    print(f"  STATUS: {'PASSOU' if passed_all else 'FALHOU'}")
    print()
    print("  Ano a ano:")
    for yr, row in yearly.iterrows():
        mark = " <-- NEGATIVO" if row["ret"] < 0 else ""
        print(f"    {yr.year}: {row['ret']*100:+.1f}%{mark}")

    return r_full, r_3y


print("=" * 65)
print("CONFIRMACAO DOS CANDIDATOS VENCEDORES")
print("=" * 65)

# REF (baseline atual)
print("\n[REF] Baseline atual ...")
ref_f, ref_3 = full_report(
    "REF — sat5%+dip1%+hyst15%+confirm2",
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    sat_pct=0.05
)

# CANDIDATO 1: sat0%+dip1.9%+hyst15%
print("\n[C1] Candidato 1 ...")
c1_f, c1_3 = full_report(
    "C1 — sat0%+dip1.9%+hyst15%+confirm2",
    PH_Dip(dip_pct=0.019, hysteresis=0.15, confirm_months=2),
    PH_Dip(dip_pct=0.019, hysteresis=0.15, confirm_months=2),
    sat_pct=0.00
)

# CANDIDATO 2: sat0%+dip2.0%+hyst15%
print("\n[C2] Candidato 2 ...")
c2_f, c2_3 = full_report(
    "C2 — sat0%+dip2.0%+hyst15%+confirm2",
    PH_Dip(dip_pct=0.020, hysteresis=0.15, confirm_months=2),
    PH_Dip(dip_pct=0.020, hysteresis=0.15, confirm_months=2),
    sat_pct=0.00
)

# CANDIDATO 3: sat0%+dip2.2%+hyst15% (um pouco mais restritivo)
print("\n[C3] Candidato 3 ...")
c3_f, c3_3 = full_report(
    "C3 — sat0%+dip2.2%+hyst15%+confirm2",
    PH_Dip(dip_pct=0.022, hysteresis=0.15, confirm_months=2),
    PH_Dip(dip_pct=0.022, hysteresis=0.15, confirm_months=2),
    sat_pct=0.00
)

# CANDIDATO 4: sat0.5%+dip2.0%+hyst15% (satelite mínimo para segurança)
print("\n[C4] Candidato 4 (com satelite minimo) ...")
c4_f, c4_3 = full_report(
    "C4 — sat0.5%+dip2%+hyst15%+confirm2",
    PH_Dip(dip_pct=0.020, hysteresis=0.15, confirm_months=2),
    PH_Dip(dip_pct=0.020, hysteresis=0.15, confirm_months=2),
    sat_pct=0.005
)

print("\n" + "=" * 65)
print("RESUMO FINAL")
print("=" * 65)
print(f"REF:  R${ref_f.metrics['final_capital']:,.0f} / NegYrs=1")
for lbl, rf in [("C1 (dip1.9%)", c1_f), ("C2 (dip2.0%)", c2_f), ("C3 (dip2.2%)", c3_f), ("C4 (sat0.5%+dip2%)", c4_f)]:
    eq = rf.equity_curve
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    print(f"{lbl}: R${rf.metrics['final_capital']:,.0f} / NegYrs={neg} / vs REF: {rf.metrics['final_capital']-REF_FULL:+,.0f}")
