"""Analisa quais anos sao negativos nas hipoteses chave e busca combinacoes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis
from strategy.h3_hysteresis import DipTop1Hysteresis

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)

REF_FULL = 134_403.0


class PortfolioHysteresisCustom(PortfolioHysteresis):
    name = "ph_custom"
    version = "1.0"
    def __init__(self, hysteresis=0.15, confirm_months=2, redist_mode="pool", **kwargs):
        super().__init__(confirm_months=confirm_months, redist_mode=redist_mode, **kwargs)
        self._hysteresis = hysteresis


def analyze(label, strategy, sat_pct=0.05, stop_pct=0.20, rmode="pool"):
    r = run_portfolio_backtest(universe, strategy, config, "2010-01-01", TODAY,
                               satellite_pct=sat_pct, satellite_stop_pct=stop_pct, redist_mode=rmode)
    eq = r.equity_curve
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    final = r.metrics["final_capital"]
    print(f"\n{label}: R${final:,.0f} / NegYrs={neg}")
    for yr, row in yearly.iterrows():
        mark = " <-- NEGATIVO" if row["ret"] < 0 else ""
        print(f"  {yr.year}: {row['ret']*100:+.1f}%{mark}")
    return r


# ============================================================
# Comparacao dos anos negativos
# ============================================================
print("=" * 70)
print("ANALISE DE ANOS NEGATIVOS — quais anos afetam NegYrs")
print("=" * 70)

# REF (portfolio_hysteresis)
r_ref = analyze("REF (pool+confirm2, sat5%)",
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    sat_pct=0.05)

# H15 (sem satelite = DipTop1Hysteresis via portfolio engine)
r_h15 = analyze("H15 (sat0%, DipTop1Hysteresis equiv)",
    PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    sat_pct=0.00)

# Agora testo variantes para tentar reduzir NegYrs do H15
# Observando: se os NegYrs negativos do H15 sao 2011/2022/2023,
# precisamos saber se a Selic gate protege esses anos e o que diferencia REF

# Teste: sat0% mas com confirm_months=1 (saida mais rapida de satelite - irrelevante aqui)
r_h15b = analyze("H15b (sat0%, confirm1)",
    PortfolioHysteresis(confirm_months=1, redist_mode="pool"),
    sat_pct=0.00)

# Teste: sat0% + selic threshold mais baixo (proteção adicional)
# Verificamos se os NegYrs caem com mais conservadorismo no Selic

print("\n" + "=" * 70)
print("DIAGNOSTICO: Os 3 NegYrs do H15 (sat0%) sao os mesmos do TOP-3 (DipTop1Hysteresis)?")
print("DipTop1Hysteresis tem R$155,364 e 3 NegYrs.")
print("H15 via portfolio engine com sat0% replica exatamente DipTop1Hysteresis.")
print()

# Vamos entender melhor os anos negativos do REF
# REF tem NegYrs=1, H15 tem NegYrs=3
# A diferenca e que o satelite suaviza quedas nos anos negativos

# Hipotese nova: sat0% mas com STOP MAIS APERTADO (-10% em vez de -15%)
# O stop pode prevenir alguns anos negativos

from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BacktestConfig

config_10 = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.10)
config_15 = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
config_20 = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.20)

r_stop10 = run_portfolio_backtest(universe, PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    config_10, "2010-01-01", TODAY, satellite_pct=0.00, satellite_stop_pct=0.20, redist_mode="pool")
r_stop20 = run_portfolio_backtest(universe, PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
    config_20, "2010-01-01", TODAY, satellite_pct=0.00, satellite_stop_pct=0.20, redist_mode="pool")

for lbl, r in [("sat0% stop10%", r_stop10), ("sat0% stop20%", r_stop20)]:
    eq = r.equity_curve
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    print(f"\n{lbl}: R${r.metrics['final_capital']:,.0f} / NegYrs={neg}")
    for yr, row in yearly.iterrows():
        mark = " <--" if row["ret"] < 0 else ""
        print(f"  {yr.year}: {row['ret']*100:+.1f}%{mark}")

# Agora: e se combinamos sat1% com confirm2 — satelite pequenissimo mas existente
print("\n" + "=" * 70)
print("SWEEP: satellite_pct de 0% a 5% (todos com confirm2)")
print("=" * 70)

for sp in [0.00, 0.01, 0.02, 0.03, 0.04, 0.05]:
    r = run_portfolio_backtest(universe, PortfolioHysteresis(confirm_months=2, redist_mode="pool"),
        config, "2010-01-01", TODAY, satellite_pct=sp, satellite_stop_pct=0.20, redist_mode="pool")
    eq = r.equity_curve
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    final = r.metrics["final_capital"]
    neg_yrs = [yr.year for yr, row in yearly.iterrows() if row["ret"] < 0]
    print(f"  sat={sp*100:.0f}%: R${final:,.0f} / NegYrs={neg} / neg_years={neg_yrs}")

print()
