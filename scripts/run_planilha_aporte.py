"""Planilha final: TOP-1 da busca de swing vs campeao atual vs IBOV, com
aporte real (R$100 inicial + R$100/mes), fracionado (lot_size=1), periodo
completo 2010-01-01 -> hoje (a mesma janela FULL que o projeto usa em todo
lugar, ver run_portfolio.py/run_satellite.py).

TOP-1: IliquidezGrupoComRiscoOrcado — a unica candidata que sobreviveu ao
cofre (ver conversa). Medida com o motor NOVO `swing_lab/engine_aporte.py`
porque o motor principal (`backtest/engine.py`) nao tem aporte mensal para
`Strategy` simples.

CAMPEAO: `LiquidChampion`, universo de producao real (`data/raw/`, nao o pool
largo usado so para comparacao na busca de swing). Aporte mensal JA existe
nativamente no motor dele (`engine_portfolio.py`) — nao precisou de wrapper.

IBOV: aporte mensal comprando o indice direto, sem estrategia — calculo
fechado, sem motor.

CAGR e MaxDD reportados sobre a curva de COTA (`cagr_unit`/`max_drawdown_unit`),
nao sobre o patrimonio bruto — com aporte mensal, o patrimonio bruto sempre
sobe por dinheiro novo entrando, e usar CAGR/DD dele mediria fluxo de caixa,
nao desempenho (ver docstring de `backtest/engine_portfolio.py`).

Uso: .venv/Scripts/python.exe scripts/run_planilha_aporte.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import pandas as pd

from backtest.engine_portfolio import run_portfolio_backtest
from backtest.metrics import cagr, max_drawdown
from core.config import BENCHMARK, BacktestConfig
from market_data.loader import load_universe
from strategy.lab.sintese.hip_02 import IliquidezGrupoComRiscoOrcado
from strategy.liquid_champion import LiquidChampion
from strategy.liquid_sleeve import POOL
from swing_lab.engine_aporte import run_backtest_com_aporte
from swing_lab.measure import panels as swing_panels

FULL_START, FULL_END = "2010-01-01", "2026-08-19"
CAPITAL_INICIAL, APORTE_MES = 100.0, 100.0


def anos_negativos(unit_curve: pd.Series) -> tuple[int, int]:
    """Conta anos-calendario com retorno negativo NA COTA (nao no patrimonio)."""
    anual = unit_curve.resample("YE").last()
    ret = anual.pct_change().dropna()
    if len(anual) >= 1:
        primeiro_ano_ret = anual.iloc[0] / unit_curve.iloc[0] - 1.0
        ret = pd.concat([pd.Series([primeiro_ano_ret]), ret])
    return int((ret < 0).sum()), int(len(ret))


def resultado(nome: str, r, capital_inicial: float, aporte_mes: float) -> dict:
    uc = r.unit_curve if r.unit_curve is not None and len(r.unit_curve) else r.equity_curve
    neg, total_anos = anos_negativos(uc)
    return {
        "nome": nome,
        "valor_final": float(r.equity_curve.iloc[-1]),
        "aportado_total": float(r.metrics.get("contributed_total", 0.0)) + capital_inicial,
        "cagr_cota": float(r.metrics.get("cagr_unit", r.metrics.get("cagr"))),
        "dd_cota": float(r.metrics.get("max_drawdown_unit", r.metrics.get("max_drawdown"))),
        "anos_negativos": neg, "anos_total": total_anos,
    }


print("1/3 — TOP-1 (IliquidezGrupoComRiscoOrcado), motor com aporte, pool largo fracionado...")
cfg_swing = BacktestConfig(initial_capital=CAPITAL_INICIAL, monthly_contribution=APORTE_MES,
                           lot_size=1, cash_yield_path=str(ROOT / "data/wide_e/selic.parquet"))
r_top1 = run_backtest_com_aporte(swing_panels(), IliquidezGrupoComRiscoOrcado(), cfg_swing,
                                 FULL_START, FULL_END)
print(f"   final R$ {r_top1.equity_curve.iloc[-1]:,.2f}  cagr_cota {r_top1.metrics['cagr_unit']:+.2%}")

print("2/3 — CAMPEAO (LiquidChampion), universo real data/raw, motor nativo com aporte...")
universo = load_universe(list(POOL))
cfg_champ = BacktestConfig(initial_capital=CAPITAL_INICIAL, monthly_contribution=APORTE_MES,
                           lot_size=1, cash_yield_path=None)
r_champ = run_portfolio_backtest(universo, LiquidChampion(), cfg_champ, FULL_START, FULL_END)
print(f"   final R$ {r_champ.equity_curve.iloc[-1]:,.2f}  cagr_cota {r_champ.metrics['cagr_unit']:+.2%}")

print("3/3 — IBOV, aporte mensal direto no indice (sem estrategia, sem motor)...")
ibov = swing_panels()[BENCHMARK]["close"].loc[FULL_START:FULL_END].dropna()
cotas = CAPITAL_INICIAL / ibov.asof(ibov.index[0])
valor_serie = {}
mes_atual = None
for d in ibov.index:
    if mes_atual is None or (d.year, d.month) != mes_atual:
        if mes_atual is not None:
            cotas += APORTE_MES / ibov.loc[d]
        mes_atual = (d.year, d.month)
    valor_serie[d] = cotas * ibov.loc[d]
ibov_valor = pd.Series(valor_serie)
n_meses = (ibov.index[-1].year - ibov.index[0].year) * 12 + (ibov.index[-1].month - ibov.index[0].month)
aportado_ibov = CAPITAL_INICIAL + APORTE_MES * n_meses
neg_ibov, tot_ibov = anos_negativos(ibov)  # cota = preco do indice, sem efeito de aporte
print(f"   final R$ {ibov_valor.iloc[-1]:,.2f}  cagr(preco) {cagr(ibov):+.2%}")

linhas = [
    resultado("TOP-1 (IliquidezGrupoComRiscoOrcado)", r_top1, CAPITAL_INICIAL, APORTE_MES),
    resultado("Campeao atual (LiquidChampion)", r_champ, CAPITAL_INICIAL, APORTE_MES),
    {"nome": "IBOV (so indice, sem estrategia)", "valor_final": float(ibov_valor.iloc[-1]),
     "aportado_total": aportado_ibov, "cagr_cota": float(cagr(ibov)),
     "dd_cota": float(max_drawdown(ibov)), "anos_negativos": neg_ibov, "anos_total": tot_ibov},
]

print(f"\n{'='*110}")
print(f"PERIODO: {FULL_START} a {FULL_END}  |  capital inicial R${CAPITAL_INICIAL:.0f}  |  aporte R${APORTE_MES:.0f}/mes  |  fracionado (lot_size=1)")
print(f"{'='*110}")
print(f"{'':<38}{'aportado':>12}{'valor final':>14}{'CAGR (cota)':>13}{'MaxDD (cota)':>13}{'anos negativos':>16}")
for l in linhas:
    anos_str = f"{l['anos_negativos']}/{l['anos_total']}"
    print(f"{l['nome']:<38}R$ {l['aportado_total']:>8,.0f}  R$ {l['valor_final']:>10,.0f}"
          f"{l['cagr_cota']:>13.2%}{l['dd_cota']:>13.2%}{anos_str:>16}")

Path("scripts/swing_lab/planilha_aporte.json").write_text(
    json.dumps(linhas, indent=2, ensure_ascii=False), encoding="utf-8")
print("\ngravado em scripts/swing_lab/planilha_aporte.json")
