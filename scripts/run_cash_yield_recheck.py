"""Reexamina os vereditos "filtro defensivo nao compensa" agora que o caixa rende.

O que estava errado
-------------------
`run_safety_walkforward.py` reprovou onze variantes defensivas — trava de
tendencia, quarentena apos stop, stop largo, sem stop, dip 5%, universo top-40 e
a pilha inteira — todas por destruirem retorno. Mas o engine remunerava o caixa
a 0% (ver `backtest.costs.cash_yield_series`), e uma variante defensiva e, por
definicao, uma variante que fica mais tempo em caixa. O campeao passa 24% do
tempo parado; o `liquid_flow5`, 32%. Com Selic media de 9,48% a.a. no periodo, o
julgamento foi feito cobrando zero de um dinheiro que renderia — e o vies cai
inteiro em cima do lado defensivo da balanca.

Pior que isso: o gate de Selic manda o robo para o caixa exatamente quando a
Selic esta SUBINDO. O momento em que a defesa mais custava no backtest e o
momento em que ela mais renderia na vida real.

Este script roda as mesmas variantes nas cinco janelas fechadas de cinco anos,
com o caixa a 0% e com o caixa na Selic, e mostra quem muda de lado.

Numeros BRUTOS (sem IR) nos dois lados de proposito: o juro de caixa tambem e
tributado (15% a 22,5% na renda fixa, conforme o prazo) e nao da para separar
com honestidade quanto do capital final veio de juro e quanto veio de trade
depois que um realimenta o outro via dimensionamento. Entao a coluna "com Selic"
e um TETO, nao uma previsao — e o que interessa aqui e se o veredito vira, nao a
segunda casa decimal.

Uso: .venv/Scripts/python.exe scripts/run_cash_yield_recheck.py
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from run_safety_walkforward import VARIANTS
from safety_lab import INITIAL, combined_equity, liquid_universe, metrics, panel

from core.config import BENCHMARK

WINDOWS = [
    ("2014-01-01", "2018-12-31"),
    ("2016-01-01", "2020-12-31"),
    ("2018-01-01", "2022-12-31"),
    ("2020-01-01", "2024-12-31"),
    ("2021-08-19", "2026-08-19"),
]
SELIC = "data/raw/selic.parquet"


def with_yield(variant, path):
    return replace(variant, config=replace(variant.config, cash_yield_path=path))


def summarize(variant, unis, path) -> dict:
    rows = []
    for s, e in WINDOWS:
        n = 40 if variant.universe_n == 40 else 20
        eq, trades = combined_equity(with_yield(variant, path), unis[(s, n)], s, e)
        rows.append(metrics(eq, trades))
    cagrs = [m["cagr"] for m in rows]
    return {
        "med": float(np.median(cagrs)),
        "pior": min(cagrs),
        "dd": min(m["max_dd"] for m in rows),
        "w12": min(m["worst_12m"] for m in rows),
        "neg": sum(1 for c in cagrs if c < 0),
    }


def ibov_stats() -> dict:
    cagrs, dds, w12 = [], [], []
    for s, e in WINDOWS:
        c = panel(BENCHMARK)["close"].loc[s:e].dropna()
        yrs = (c.index[-1] - c.index[0]).days / 365.25
        cagrs.append(float((c.iloc[-1] / c.iloc[0]) ** (1 / yrs) - 1))
        dds.append(float((c / c.cummax() - 1).min()))
        w12.append(float((c / c.shift(252) - 1).min()))
    return {"med": float(np.median(cagrs)), "pior": min(cagrs),
            "dd": min(dds), "w12": min(w12), "neg": sum(1 for c in cagrs if c < 0)}


def gates(r: dict, ib_med: float) -> dict:
    return {"G1": r["pior"] > 0, "G2": r["dd"] > -0.45,
            "G3": r["med"] >= ib_med, "G5": r["w12"] > -0.35}


def main() -> None:
    print("\nCAIXA A 0% x CAIXA NA SELIC — as variantes defensivas mudam de veredito?")
    print("5 janelas fechadas de 5 anos | universo point-in-time por liquidez | CAGR BRUTO\n")

    unis = {}
    for s, _ in WINDOWS:
        for n in (20, 40):
            unis[(s, n)] = liquid_universe(s, n)

    ib = ibov_stats()
    print(f"IBOV: CAGR mediano {ib['med']*100:.2f}% | pior {ib['pior']*100:.2f}% | "
          f"MaxDD {ib['dd']*100:.1f}% | pior 12m {ib['w12']*100:.1f}%\n")

    hdr = (f"{'variante':26s} {'CAGRmed 0%':>11s} {'CAGRmed Selic':>14s} {'delta':>7s} "
           f"{'pior 0%':>8s} {'pior Selic':>11s} {'neg':>5s} {'portoes 0%':>12s} {'portoes Selic':>15s}")
    print(hdr)
    print("-" * len(hdr))

    flips = []
    for v in VARIANTS:
        a = summarize(v, unis, None)
        b = summarize(v, unis, SELIC)
        ga, gb = gates(a, ib["med"]), gates(b, ib["med"])
        fa = ",".join(k for k, ok in ga.items() if not ok) or "PASSA"
        fb = ",".join(k for k, ok in gb.items() if not ok) or "PASSA"
        if fa != fb:
            flips.append((v.key, fa, fb))
        print(f"{v.key:26s} {a['med']*100:10.2f}% {b['med']*100:13.2f}% "
              f"{(b['med']-a['med'])*100:+6.2f} {a['pior']*100:7.2f}% {b['pior']*100:10.2f}% "
              f"{a['neg']}->{b['neg']:<3d} {fa:>12s} {fb:>15s}", flush=True)

    print("\nMUDANCAS DE VEREDITO")
    if not flips:
        print("  nenhuma — a conclusao 'filtro defensivo nao compensa' sobrevive ao caixa remunerado.")
    for key, fa, fb in flips:
        print(f"  {key:26s} {fa} -> {fb}")


if __name__ == "__main__":
    main()
