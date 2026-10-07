# -*- coding: utf-8 -*-
"""Linhas da tabela padrao (`backtest/intraday/report.py`) para os dois modos de medicao."""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pandas as pd

import runner  # noqa: F401  (poe src/ no sys.path)
from backtest.intraday.report import LinhaResultado, linha_de_resultado, num_br, tabela  # noqa: E402

EXTRAS = ("modo", "fill", "sinais", "sem fill%", "atraso min", "BE emp%", "p nulo", "caixa min", "sem trade")


def nome(spec: dict) -> str:
    """Nome curto (<=30): variante|recuo|stop|alvo|(filtro volume)|(gap min)."""
    a = "-" if spec.get("alvo_pts") is None else f"{int(spec['alvo_pts'])}"
    n = f"{spec['variante']} r{int(spec.get('recuo_pts', 0))} s{int(spec['stop_pts'])} a{a}"
    if spec["variante"] == "V3":
        n += " " + ("skip" if spec["vol_modo"] == "skip" else f"a{int(spec['alvo_pequeno_pts'])}")
    if spec.get("gap_min_pts"):
        n += f" g{int(spec['gap_min_pts'])}"
    return n


def linha_a(res: dict, spec: dict, p_nulo: float | None = None) -> LinhaResultado:
    """Modo A: conta continua com R$250 (a morte de caixa aparece)."""
    L = res["_linha"]
    nf = 100.0 * res["sem_fill"] / res["ordens"] if res["ordens"] else float("nan")
    extras = {
        "modo": "conta", "fill": res["fill"], "sinais": str(res["ordens"]),
        "sem fill%": num_br(nf, 1), "atraso min": num_br(res["atraso_med"], 1),
        "BE emp%": num_br(res["be"], 1), "p nulo": "—" if p_nulo is None else num_br(p_nulo, 3),
        "caixa min": num_br(res["eq_min"], 2), "sem trade": f"{res['sem_trade']}/{res['pregoes']}",
    }
    aviso = L.aviso
    if res["recusadas"]:
        aviso = (aviso + f" CENSURADO recusou {res['recusadas']} ordens").strip()
    return dataclasses.replace(L, variante=nome(spec), extras=extras, aviso=aviso)


def linha_b(r: dict, spec: dict, fill: str, rotulo: str = "pregao") -> LinhaResultado:
    """Modo B: cada pregao com R$250 novos (sem arrasto de caixa). Capital nocional: as colunas que
    dependem de saldo ficam em branco."""
    pnl = r["pnl_dia"]
    idx = r["dias_sessao"]
    eq = pd.Series([250.0 + sum(v for d, v in pnl.items() if d <= x) for x in idx],
                   index=pd.to_datetime(idx))
    res = SimpleNamespace(trades=r["trades"], equity_curve=eq, metrics={}, wiped_out_at=None,
                          sessoes_puladas_por_capital=[], deslize_alvo_ticks=1.0,
                          fila_entrada_qty=0.0, fila_saida_qty=0.0, fila_calibrada=False)
    L = linha_de_resultado(nome(spec), res, runner.CAPITAL, capital_nocional=True)
    extras = {
        "modo": rotulo, "fill": fill, "sinais": str(r["dias_gatilho"]),
        "sem fill%": num_br(r["taxa_sem_fill"], 1), "atraso min": num_br(r["atraso_med"], 1),
        "BE emp%": num_br(r["be"], 1), "p nulo": num_br(r["p_nulo"], 3),
        "caixa min": "—", "sem trade": f"{r['sem_trade']}/{r['pregoes']}",
    }
    return dataclasses.replace(L, extras=extras)
