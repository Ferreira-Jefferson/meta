"""Reabre a escolha do numero de sleeves — ela foi feita com o caixa a 0%.

Por que reabrir
---------------
`k = 5` saiu de uma varredura de oito valores nas cinco janelas de ajuste. Duas
coisas mudaram DEPOIS dessa varredura:

  1. O engine passou a remunerar caixa parado (`cash_yield_series`). O viés
     antigo nao era neutro em k: quanto mais sleeves, mais tempo com algum
     sleeve descoberto, mais caixa parado — e caixa parado era cobrado 0%. A
     varredura penalizava sistematicamente o k alto.
  2. A regra de universo virou banda de rank continua, que rotaciona diferente.

Entao a escolha de k foi feita num mundo que nao existe mais. Este script refaz
so ela, com a regra de universo do campeao e o caixa remunerado.

Como ler
--------
O que legitima um k nao e ele ganhar — e a metrica de risco ser MONOTONA nele.
Se o MaxDD melhora de 3 para 5 para 7 e piora em 10, isso e uma curva; se pula
para todo lado, e ruido e a escolha nao tem base. Mesmo criterio que aposentou
`refresh_months`.

Custo operacional, que o backtest nao cobra: com lote minimo de 100 acoes na
Clear (~R$ 4.900 num papel de R$ 49), cada sleeve precisa de capital proprio
para caber num lote. k=5 exige ~R$ 25 mil; k=10 exige ~R$ 50 mil. Um k melhor
no backtest pode ser inoperavel na conta real — ver
`memory/mt5_terminal_clear_config.md`.

Uso: .venv/Scripts/python.exe scripts/run_champion_k.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from run_sleeve_validation import full_panels
from safety_lab import panel

from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from strategy.liquid_champion import LiquidChampion

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
KS = (2, 3, 4, 5, 7, 10)
WINDOWS = [
    ("2014-01-01", "2018-12-31"),
    ("2016-01-01", "2020-12-31"),
    ("2018-01-01", "2022-12-31"),
    ("2020-01-01", "2024-12-31"),
    ("2021-08-19", "2026-08-19"),
]


def medir(k, u, start, end) -> dict:
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC)
    bot = LiquidChampion(sleeve_count=k)
    r = run_bt(u, bot, cfg, start=start, end=end)
    eq = r.equity_curve
    return {"cagr": float(r.metrics["cagr"]), "dd": float(r.metrics["max_drawdown"]),
            "w12": float((eq / eq.shift(252) - 1).min()), "trades": len(r.trades)}


def monotona(vals) -> str:
    d = np.diff(vals)
    if all(x >= -1e-9 for x in d):
        return "sobe"
    if all(x <= 1e-9 for x in d):
        return "desce"
    return "NAO"


def main() -> None:
    u = full_panels()
    ib = []
    for s, e in WINDOWS:
        c = panel(BENCHMARK)["close"].loc[s:e].dropna()
        anos = (c.index[-1] - c.index[0]).days / 365.25
        ib.append(float((c.iloc[-1] / c.iloc[0]) ** (1 / anos) - 1))

    hdr = (f"{'k':>3s} " + "".join(f"{s[2:7]:>8s}" for s, _ in WINDOWS) +
           f" | {'med':>7s} {'pior':>7s} {'DDpior':>7s} {'12m':>7s} {'trd':>4s}")
    print("\nNUMERO DE SLEEVES — banda 20/30, caixa na Selic, 5 janelas de ajuste")
    print(f"{'=' * len(hdr)}\n{hdr}\n{'-' * len(hdr)}")
    print(f"{'IBOV':>3s} " + "".join(f"{g * 100:7.1f}%" for g in ib) +
          f" | {np.median(ib) * 100:6.1f}% {min(ib) * 100:6.1f}%")

    tab = {}
    for k in KS:
        rows = [medir(k, u, s, e) for s, e in WINDOWS]
        g = [m["cagr"] for m in rows]
        tab[k] = {"med": float(np.median(g)), "pior": min(g),
                  "dd": min(m["dd"] for m in rows), "w12": min(m["w12"] for m in rows),
                  "trd": int(np.median([m["trades"] for m in rows]))}
        print(f"{k:3d} " + "".join(f"{x * 100:7.1f}%" for x in g) +
              f" | {tab[k]['med'] * 100:6.1f}% {tab[k]['pior'] * 100:6.1f}% "
              f"{tab[k]['dd'] * 100:6.1f}% {tab[k]['w12'] * 100:6.1f}% {tab[k]['trd']:4d}",
              flush=True)

    print("\nmonotonicidade em k (o que legitima a escolha):")
    for campo, rotulo in (("pior", "pior janela"), ("w12", "pior 12m"),
                          ("dd", "MaxDD"), ("med", "CAGR mediano")):
        vals = [tab[k][campo] for k in KS]
        print(f"  {rotulo:14s} {monotona(vals):5s}  " +
              "  ".join(f"k{k}={v * 100:.1f}%" for k, v in zip(KS, vals)))


if __name__ == "__main__":
    main()
