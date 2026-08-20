"""Estresse de capital pequeno — R$100 em vez de R$1.000, nas mesmas 47 janelas.

O que este script NAO testa (e por que)
----------------------------------------
O capital real do usuario e R$100/MES, comecando do ZERO — aporte recorrente,
nao capital estatico. O mecanismo de aporte mensal (`monthly_contribution`,
curva de cota) so esta implementado em `backtest/engine_portfolio.py`, usado
pela classe `PortfolioHysteresis` (o campeao de sleeves). As 122 hipoteses e as
2 sinteses desta busca sao `Strategy` simples, que passam por
`backtest/engine.py::run_backtest`, e esse arquivo NAO tem a logica de aporte.
Este projeto tem uma regra de nao editar arquivo existente do motor numa sessao
concorrente — entao portar o mecanismo de aporte para ca e trabalho separado,
declarado como pendente, nao feito aqui por atalho.

O que este script MEDE
-----------------------
O efeito de GRANULARIDADE: com lot_size=1 (fracionario), a quantidade ainda e
`int(orcamento // preco)` — divisao inteira. Com orcamento de R$1.000 dividido
entre 3-5 posicoes (R$200-330 cada), o resto descartado e pequeno. Com R$100
dividido do mesmo jeito (R$20-33 cada) e preco mediano de R$14,42, o resto
descartado pode ser 10-40% da fatia, ou a posicao ser pulada inteira se o preco
> a fatia. Isso e testavel SEM mudar o motor: basta iniciar com capital menor.

Interpretacao: se o CAGR mediano e o pior DD nao mudam muito entre R$1.000 e
R$100, a estrategia tolera bem o inicio raso. Se degradam, o portao de capital
real e mais severo do que apenas "acessibilidade de preco por acao".

Uso: .venv/Scripts/python.exe scripts/run_capital_pequeno.py
"""
from __future__ import annotations

import importlib
import json
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
from swing_lab.measure import (
    ANOS, E2_WINDOWS, FULL_END, SELIC_E, _exposure, panels,
)

ALVOS = [
    ("strategy.lab.iliquidez.hip_06", "Hip06IliquidezRelativaAoGrupo", "iliquidez"),
    ("strategy.lab.preco_qualidade.hip_10", "LongHorizonRiskAdjustedReturn", "preco_qualidade"),
    ("strategy.lab.trend_ts.hip_04", "MacroGatedBreakout", "trend_ts"),
    ("strategy.lab.iliquidez.hip_03", "Hip03ExcluiTopoLiquidez", "iliquidez"),
    ("strategy.lab.risk_targeting.hip_05", "RiskCappedWithStop", "risk_targeting"),
    ("strategy.lab.sintese.hip_01", "IliquidezGrupoComQualidade5A", "sintese"),
    ("strategy.lab.sintese.hip_02", "IliquidezGrupoComRiscoOrcado", "sintese"),
]


def _metricas(eq: pd.Series) -> dict | None:
    if len(eq) < 250:
        return None
    anos = (eq.index[-1] - eq.index[0]).days / 365.25
    tot = eq.iloc[-1] / eq.iloc[0]
    return {"cagr": float(tot ** (1.0 / anos) - 1.0) if anos > 0 and tot > 0 else -1.0,
            "dd": float(max_drawdown(eq))}


def roda(cls_factory, capital: float) -> dict:
    cfg = BacktestConfig(initial_capital=capital, lot_size=1, cash_yield_path=SELIC_E)
    p = panels()
    linhas, expos = [], []
    for s in E2_WINDOWS:
        e = min(s + pd.DateOffset(years=ANOS), pd.Timestamp(FULL_END))
        r = run_bt(p, cls_factory(), cfg, start=str(s.date()), end=str(e.date()))
        m = _metricas(r.equity_curve)
        if m:
            linhas.append(m)
            expos.append(_exposure(r))
    if not linhas:
        return {}
    return {"median_cagr": float(np.median([x["cagr"] for x in linhas])),
            "worst_dd": float(min(x["dd"] for x in linhas)),
            "median_exposure": float(np.nanmedian(expos)), "n": len(linhas)}


def main() -> None:
    print(f"{'classe':<32}{'CAGR@1000':>10}{'CAGR@100':>10}{'delta':>8}"
          f"{'DD@1000':>9}{'DD@100':>9}{'expos@100':>10}")
    print("-" * 88)
    saida = []
    for modulo, classe, familia in ALVOS:
        cls = getattr(importlib.import_module(modulo), classe)
        r1000 = roda(lambda: cls(), 1000.0)
        r100 = roda(lambda: cls(), 100.0)
        if not r1000 or not r100:
            print(f"{classe[:31]:<32}  sem dado suficiente")
            continue
        delta = r100["median_cagr"] - r1000["median_cagr"]
        print(f"{classe[:31]:<32}{r1000['median_cagr']:>10.2%}{r100['median_cagr']:>10.2%}"
              f"{delta:>+8.2%}{r1000['worst_dd']:>9.2%}{r100['worst_dd']:>9.2%}"
              f"{r100['median_exposure']:>10.2f}")
        saida.append({"classe": classe, "familia": familia,
                      "r1000": r1000, "r100": r100, "delta_cagr": delta})
    Path("scripts/swing_lab/capital_pequeno.json").write_text(
        json.dumps(saida, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nNao testa aporte mensal recorrente (motor nao suporta para Strategy simples).")
    print("Testa so o efeito de granularidade de comecar com pouco capital.")


if __name__ == "__main__":
    main()
