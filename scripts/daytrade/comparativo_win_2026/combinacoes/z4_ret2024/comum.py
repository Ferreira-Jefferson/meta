# -*- coding: utf-8 -*-
"""Leitura das operacoes do Z4 e tabela por ano (R$2/op, recomeca R$1.000 a cada ano, sem parar por saldo)."""
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
CUSTO = 2.0
ANOS = ["2022", "2023", "2024", "2025", "2026"]


def carrega(nome="base", sempos=False):
    suf = "_sempos" if sempos else ""
    # 2022-25: o M1 termina 18:24, nao ha tick pos-pregao -> a versao sem 18:30 e' identica (conferido na base)
    df = pd.concat([pd.read_csv(AQUI / "trades" / f"{nome}_2022_2025.csv"), pd.read_csv(AQUI / "trades" / f"{nome}_2026{suf}.csv")], ignore_index=True)
    df["ano"] = df.saida.str[:4]
    df["mes"] = df.saida.str[:7]
    df["liq"] = df.rs - CUSTO
    df["ganhou"] = df.liq > 0
    return df


def por_ano(df):
    rows = []
    for a in ANOS:
        g = df[df.ano == a]
        eq = g.liq.cumsum()
        menor = 1000 + min(0.0, eq.min()) if len(g) else 1000.0
        rows.append(dict(ano=a, ops=len(g), liquido=round(g.liq.sum(), 2), acerto=round(g.ganhou.mean() * 100, 1) if len(g) else np.nan,
                         saldo_min=round(menor, 2), quebra=menor <= 0))
    return pd.DataFrame(rows)


def md(df, index=True):
    """DataFrame -> tabela markdown (sem depender de tabulate)."""
    d = df.reset_index() if index else df
    lin = ["| " + " | ".join(map(str, d.columns)) + " |", "|" + "---|" * len(d.columns)]
    for r in d.itertuples(index=False):
        lin.append("| " + " | ".join(f"{x:,.2f}" if isinstance(x, float) else str(x) for x in r) + " |")
    return "\n".join(lin)
