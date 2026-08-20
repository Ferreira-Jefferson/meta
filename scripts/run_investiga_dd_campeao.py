"""Qual janela e qual data produziu o pior DD (-58,86%) do campeao no cofre?"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
from backtest.metrics import max_drawdown
from backtest.runner import run as run_bt
from core.config import BacktestConfig, BENCHMARK
from strategy.liquid_champion import LiquidChampion
from swing_lab.measure import wide_pool
import importlib
rvv = importlib.import_module("run_vault_verdict")

class CampeaoLargoVault(LiquidChampion):
    name = "campeao_largo_vault"; candidate = False
    universe_tickers = tuple(wide_pool())

P = rvv.vault_panels()
cfg = BacktestConfig(initial_capital=rvv.INITIAL, lot_size=1, cash_yield_path=rvv.SELIC_V)

pior_dd, pior_janela, pior_eq = 0.0, None, None
for s in rvv.VAULT_WINDOWS:
    e = min(s + pd.DateOffset(years=rvv.ANOS), pd.Timestamp("2009-12-31"))
    r = run_bt(P, CampeaoLargoVault(), cfg, start=str(s.date()), end=str(e.date()))
    if len(r.equity_curve) < 250: continue
    dd = max_drawdown(r.equity_curve)
    if dd < pior_dd:
        pior_dd, pior_janela, pior_eq, pior_r = dd, s, r.equity_curve, r

print(f"pior janela: inicio {pior_janela.date()}  DD={pior_dd:+.2%}")
eq = pior_eq
peak = eq.cummax()
drawdown = eq/peak - 1.0
data_fundo = drawdown.idxmin()
data_pico_antes = eq.loc[:data_fundo].idxmax()
print(f"pico anterior: {data_pico_antes.date()} (equity {eq.loc[data_pico_antes]:.0f})")
print(f"fundo:         {data_fundo.date()} (equity {eq.loc[data_fundo]:.0f})")
print()

ibov = P[BENCHMARK]["close"]
ibov_j = ibov.loc[str(data_pico_antes.date()):str(data_fundo.date())]
if len(ibov_j) > 1:
    var_ibov = ibov_j.iloc[-1]/ibov_j.iloc[0] - 1.0
    print(f"IBOV no mesmo intervalo ({data_pico_antes.date()} -> {data_fundo.date()}): {var_ibov:+.2%}")

# quais posicoes estavam abertas no fundo, e o pnl acumulado delas ate ali
abertas = [t for t in pior_r.trades if pd.Timestamp(t.entry_date) <= data_fundo
           and (t.exit_date is None or pd.Timestamp(t.exit_date) >= data_fundo)]
print(f"\nposicoes abertas no fundo do DD: {len(abertas)}")
for t in abertas[:15]:
    print(f"  {t.ticker:<12} entrada {t.entry_date}  qty {t.quantity}")

# trades fechados DENTRO da janela de queda, com maior perda
fechados_na_queda = [t for t in pior_r.trades
                     if t.exit_date and data_pico_antes <= pd.Timestamp(t.exit_date) <= data_fundo]
fechados_na_queda.sort(key=lambda t: t.pnl_brl)
print(f"\n10 maiores perdas realizadas na queda ({len(fechados_na_queda)} trades fecharam no periodo):")
for t in fechados_na_queda[:10]:
    print(f"  {t.ticker:<12} entrada {t.entry_date}  saida {t.exit_date}  pnl {t.pnl_brl:>10.2f}")
