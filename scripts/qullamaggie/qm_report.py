"""Lê resultado_<setup>.csv e imprime: top-N por lucro/DD no IS com OOS ao lado, correlação
IS x OOS de TODAS as células (anti-sorte), e a vizinhança da célula escolhida.

python scripts/qullamaggie/qm_report.py breakout [--min-trades 100] [--top 15]
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
KEYS_SKIP = {"grupo", "retorno", "liquido", "maxdd_pct", "maxdd_brl", "lucro_dd", "win", "breakeven",
             "trades", "r_medio", "r_ic", "final", "cagr"}


def br(x, nd=2):
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pivot(df):
    cells = [c for c in df.columns if c not in KEYS_SKIP]
    parts = []
    for g, d in df.groupby("grupo"):
        d = d.set_index(cells)[["retorno", "liquido", "maxdd_pct", "lucro_dd", "win", "breakeven",
                                "trades", "r_medio", "r_ic"]]
        d.columns = [f"{g}__{c}" for c in d.columns]
        parts.append(d)
    return pd.concat(parts, axis=1).reset_index(), cells


def linha(r, g):
    f = lambda k: r[f"{g}__{k}"]
    return (f"{br(f('retorno') * 100, 1):>9}% {br(f('liquido'), 0):>10} {br(f('maxdd_pct') * 100, 1):>6}% "
            f"{br(f('lucro_dd')):>6} {br(f('win') * 100, 1):>5}% (BE {br(f('breakeven') * 100, 1)}%) "
            f"{int(f('trades')):>5}  R {br(f('r_medio'), 2)}±{br(f('r_ic'), 2)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("setup")
    ap.add_argument("--min-trades", type=int, default=100)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    df = pd.read_csv(os.path.join(HERE, f"resultado_{a.setup}.csv"))
    pv, cells = pivot(df)
    n = len(pv)
    ok = pv[(pv["acoes_IS__trades"] >= a.min_trades) & (pv["acoes_OOS__trades"] >= 20)]
    print(f"{a.setup}: {n} células; {len(ok)} com >= {a.min_trades} trades no IS e >= 20 no OOS")
    print(f"IS positivas: {(pv['acoes_IS__liquido'] > 0).mean() * 100:.0f}%   "
          f"OOS positivas: {(pv['acoes_OOS__liquido'] > 0).mean() * 100:.0f}%")
    if len(ok) > 3:
        print(f"Spearman lucro/DD IS x OOS (todas as células válidas): "
              f"{ok['acoes_IS__lucro_dd'].rank().corr(ok['acoes_OOS__lucro_dd'].rank()):.2f}")
    top = ok.sort_values("acoes_IS__lucro_dd", ascending=False).head(a.top)
    print("\nTOP por lucro/DD no IS  (retorno | líquido R$ | MaxDD | lucro/DD | win% | trades | R médio ±IC95)")
    for _, r in top.iterrows():
        print("\n" + ", ".join(f"{c}={r[c]:g}" for c in cells))
        for g in ("acoes_IS", "acoes_OOS", "indice", "cripto"):
            print(f"  {g:10} {linha(r, g)}")
    if len(top):
        b = top.iloc[0]
        viz = ok.copy()
        diff = sum((viz[c] != b[c]).astype(int) for c in cells)
        v1 = viz[diff == 1]
        print(f"\nVizinhança da 1ª ({len(v1)} células a 1 parâmetro de distância):")
        print(f"  OOS positivas: {(v1['acoes_OOS__liquido'] > 0).mean() * 100:.0f}%   "
              f"OOS lucro/DD mediano: {v1['acoes_OOS__lucro_dd'].median():.2f}   "
              f"IS mediano: {v1['acoes_IS__lucro_dd'].median():.2f}")


if __name__ == "__main__":
    main()
