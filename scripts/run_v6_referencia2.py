"""Complemento: DD do campeao nas mesmas 36 janelas, para fechar a comparacao."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np, pandas as pd
from backtest.metrics import max_drawdown
from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion
from swing_lab.measure import wide_pool
import importlib
rvv = importlib.import_module("run_vault_verdict")

class CampeaoLargoVault(LiquidChampion):
    name = "campeao_largo_vault"; candidate = False
    universe_tickers = tuple(wide_pool())

P = rvv.vault_panels()
cfg = BacktestConfig(initial_capital=rvv.INITIAL, lot_size=1, cash_yield_path=rvv.SELIC_V)
linhas = []
for s in rvv.VAULT_WINDOWS:
    e = min(s + pd.DateOffset(years=rvv.ANOS), pd.Timestamp("2009-12-31"))
    r = run_bt(P, CampeaoLargoVault(), cfg, start=str(s.date()), end=str(e.date()))
    if len(r.equity_curve) < 250: continue
    eq = r.equity_curve
    anos = (eq.index[-1]-eq.index[0]).days/365.25
    tot = eq.iloc[-1]/eq.iloc[0]
    cagr = float(tot**(1.0/anos)-1.0) if anos>0 and tot>0 else -1.0
    w12 = float((eq/eq.shift(252)-1.0).min())
    linhas.append({"cagr": cagr, "dd": float(max_drawdown(eq)), "w12": w12})
print(f"CAMPEAO no cofre ({len(linhas)} janelas):")
print(f"  CAGR mediano {np.median([x['cagr'] for x in linhas]):+.2%}")
print(f"  pior DD      {min(x['dd'] for x in linhas):+.2%}")
print(f"  pior 12m     {min(x['w12'] for x in linhas):+.2%}")
