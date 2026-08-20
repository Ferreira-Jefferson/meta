"""V6 tem calibracao ou foi um limiar arbitrario? Medindo o campeao no cofre.

Pergunta do usuario: exigir top5_share_max < 1.00 em TODAS as 36 janelas pode
estar rejeitando a mecanica normal deste mercado (poucos trades grandes
sustentando o lucro), nao um sinal de sobreajuste — ESPECIALMENTE porque este
mesmo projeto ja mediu que diluir concentracao no campeao PIORA o resultado
(`champion_concentration_fixes_refuted_2026_08_18.md`).

Este script mede a MESMA metrica, do MESMO jeito (so trade fechado, ver
`_top5_share` em swing_lab/measure.py), no campeao atual, nas MESMAS 36 janelas
do cofre — para ter uma referencia objetiva em vez de um limiar assumido.

Uso: .venv/Scripts/python.exe scripts/run_v6_referencia.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import pandas as pd

from backtest.metrics import max_drawdown
from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion
from swing_lab.measure import wide_pool

sys.path.insert(0, str(ROOT / "scripts" / "swing_lab"))
import importlib
rvv = importlib.import_module("run_vault_verdict")


class CampeaoLargoVault(LiquidChampion):
    name = "campeao_largo_vault"
    candidate = False
    universe_tickers = tuple(wide_pool())


def top5_share(trades) -> float:
    pnls = sorted((float(t.pnl_brl) for t in trades if t.exit_price is not None), reverse=True)
    if not pnls:
        return float("nan")
    total = sum(pnls)
    if total <= 0:
        return float("inf")
    return float(sum(pnls[:5]) / total)


P = rvv.vault_panels()
cfg = BacktestConfig(initial_capital=rvv.INITIAL, lot_size=1, cash_yield_path=rvv.SELIC_V)

linhas = []
for s in rvv.VAULT_WINDOWS:
    e = min(s + pd.DateOffset(years=rvv.ANOS), pd.Timestamp("2009-12-31"))
    r = run_bt(P, CampeaoLargoVault(), cfg, start=str(s.date()), end=str(e.date()))
    if len(r.equity_curve) < 250:
        continue
    ts = top5_share(r.trades)
    anos = (r.equity_curve.index[-1] - r.equity_curve.index[0]).days / 365.25
    tot = r.equity_curve.iloc[-1] / r.equity_curve.iloc[0]
    cagr = float(tot ** (1.0 / anos) - 1.0) if anos > 0 and tot > 0 else -1.0
    linhas.append({"start": str(s.date()), "top5_share": ts, "n_trades": len(r.trades), "cagr": cagr})

vals = [x["top5_share"] for x in linhas if np.isfinite(x["top5_share"])]
print(f"CAMPEAO (pool largo) no cofre, {len(linhas)} janelas:")
print(f"  top5_share:  mediana {np.median(vals):.2f}  min {min(vals):.2f}  max {max(vals):.2f}")
print(f"  janelas com top5_share >= 1.00: {sum(1 for v in vals if v >= 1.0)} de {len(vals)}")
print(f"  CAGR mediano: {np.median([x['cagr'] for x in linhas]):+.2%}")
print()
print("por janela (so as com top5_share >= 1.00):")
for x in linhas:
    if np.isfinite(x["top5_share"]) and x["top5_share"] >= 1.0:
        print(f"  {x['start']}  top5_share={x['top5_share']:.2f}  trades={x['n_trades']}  cagr={x['cagr']:+.2%}")
