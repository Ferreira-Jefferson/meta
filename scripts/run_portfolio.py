"""Testa 4 variantes do PortfolioHysteresis (satelites acumulativos + saida por momentum).

Comparacao contra a referencia TOP-1 (DipTop1Satellite, satelite fixo 5% + stop).

Teste 1  redist=main     | confirm=1  | saida: vai para posicao principal
Teste 2  redist=pool     | confirm=1  | saida: vai para caixa geral
Teste 3  redist=best_sat | confirm=1  | saida: vai para o maior satelite atual
Teste 4  redist=pool     | confirm=2  | saida: caixa, mas sinal confirmado em 2 meses
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_satellite import run_satellite_backtest
from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.satellite import DipTop1Satellite
from strategy.portfolio_satellite import PortfolioHysteresis

TICKERS = ["WEGE3.SA", "BRAP4.SA", "RADL3.SA", "CSMG3.SA", "EMAE4.SA", "KEPL3.SA", "CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

VARIANTS = [
    ("REF Top-1 (sat stop)",  None,                         "satellite",  {"satellite_pct": 0.05, "satellite_stop_pct": 0.20}),
    ("T1 main (reforco)",     PortfolioHysteresis(),        "main",       {}),
    ("T2 pool (caixa geral)", PortfolioHysteresis(),        "pool",       {}),
    ("T3 best_sat (melhor)",  PortfolioHysteresis(),        "best_sat",   {}),
    ("T4 pool+confirm2",      PortfolioHysteresis(confirm_months=2), "pool", {}),
]


def metrics_line(result):
    m = result.metrics
    eq = result.equity_curve
    yearly = eq.resample("YE").agg(["first", "last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    return m["final_capital"], m["cagr"], m.get("sharpe", 0), m["max_drawdown"], neg


def run_one(label, strategy, mode, extra_kw, start, end, universe, config):
    t0 = time.perf_counter()
    if mode == "satellite":
        r = run_satellite_backtest(universe, DipTop1Satellite(), config, start=start, end=end, **extra_kw)
    else:
        r = run_portfolio_backtest(universe, strategy, config, start=start, end=end, redist_mode=mode)
    elapsed = time.perf_counter() - t0
    fc, cg, sh, dd, ng = metrics_line(r)
    return r, fc, cg, sh, dd, ng, elapsed


def run_window(start, end, window_label):
    universe = load_universe(tickers=TICKERS, include_benchmark=True)
    config = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)

    print(f"\n{'='*80}")
    print(f"  {window_label}  {start} -> {end}")
    print(f"{'='*80}")
    print(f"  {'Variante':25s}  {'Final':>10}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'NegYr':>6}  {'t':>5}")
    print(f"  {'-'*25}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}  {'-'*5}")

    results = {}
    for label, strategy, mode, extra_kw in VARIANTS:
        r, fc, cg, sh, dd, ng, el = run_one(label, strategy, mode, extra_kw, start, end, universe, config)
        results[label] = r
        print(f"  {label:25s}  R${fc:7.0f}  {cg*100:6.2f}%  {sh:7.2f}  {dd*100:6.2f}%  {ng:>6}  {el:4.1f}s")

    # Ano a ano
    print(f"\n  Ano a ano (* = negativo):")
    header = f"  {'Ano':4s}"
    for label, *_ in VARIANTS:
        header += f"  {label[:11]:>11}"
    print(header)

    yearly_data = {}
    for label, *_ in VARIANTS:
        r = results[label]
        yd = r.equity_curve.resample("YE").agg(["first", "last"])
        yd["ret"] = yd["last"] / yd["first"] - 1
        yearly_data[label] = yd

    all_years = sorted({y for yd in yearly_data.values() for y in yd.index})
    for yr in all_years:
        row = f"  {yr.year:4d}"
        for label, *_ in VARIANTS:
            yd = yearly_data[label]
            if yr in yd.index:
                rv = yd.loc[yr, "ret"]
                neg = "*" if rv < 0 else " "
                row += f"  {rv*100:+9.1f}%{neg}"
            else:
                row += f"  {'N/A':>11}"
        print(row)

    return results


results_full = run_window("2010-01-01", TODAY, "FULL")
results_3y   = run_window(THREE_Y, TODAY, "3Y")

print("\n\n  RESUMO FINAL")
print(f"  {'Variante':25s}  {'FULL Final':>11}  {'FULL CAGR':>10}  {'3Y Final':>9}  {'3Y CAGR':>8}")
print(f"  {'-'*25}  {'-'*11}  {'-'*10}  {'-'*9}  {'-'*8}")
for label, *_ in VARIANTS:
    mf = results_full[label].metrics
    m3 = results_3y[label].metrics
    print(f"  {label:25s}  R${mf['final_capital']:8.0f}  {mf['cagr']*100:9.2f}%  R${m3['final_capital']:6.0f}  {m3['cagr']*100:7.2f}%")
