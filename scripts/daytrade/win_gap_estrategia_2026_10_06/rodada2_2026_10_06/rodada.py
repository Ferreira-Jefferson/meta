# -*- coding: utf-8 -*-
"""Roda a grade (100 celulas) em TODOS os pregoes elegiveis, em paralelo POR PREGAO (cada worker carrega
os ticks de um dia, simula todas as celulas nele e devolve so' resumos). Streaming: um print por dia."""
from __future__ import annotations

import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ctx as C  # noqa: E402
import regras as R  # noqa: E402
import sim as S  # noqa: E402
import ticks_prep as TP  # noqa: E402

QS = (1, 2, 3, 4, 5)
FILLS = ("toque", "atrav+1t")
_G = {}


def _init():
    if "bj" not in _G:
        bj, dj, ctx = C.constroi()
        _G.update(bj=bj, ctx=ctx, grade=R.grade())


def resumo(tr: S.Trade | None) -> dict | None:
    if tr is None:
        return None
    return dict(pnl=tr.pnl, legs=[(g.qty, g.reason, g.exit_t, g.exit_price) for g in tr.legs], worst=tr.pior_pts,
                fill_t=tr.fill_t, entry=tr.entry_price, qty=tr.qty, sai_fill=tr.sai_na_barra_do_fill, mae=tr.mae_pts,
                side=tr.side)


def processa_dia(dia) -> dict:
    _init()
    c = _G["ctx"][dia]
    b = C.barras_do_dia(_G["bj"], dia)
    t, p = TP.carrega(dia)
    d = S.DiaTicks(t=t, p=p, bst=b["st"], bo=b["o"], bh=b["h"], bl=b["l"], bc=b["c"])
    t_sinal = int(b["st"][0] + S.M5)
    out = {}
    for cel in _G["grade"]:
        ent, ex = cel["ent"], cel["ex"]
        s_real = R.gatilho(c, ent)
        if s_real == 0:
            out[cel["id"]] = None
            continue
        lim_real = R.limite(c, s_real, ent["recuo"])
        if R.saida_de(c, s_real, lim_real, ex, s_real, lim_real) is None:
            out[cel["id"]] = None
            continue
        r = dict(side=s_real, fills={})
        for fm in FILLS:
            real = {}
            for q in QS:
                sa = R.saida_de(c, s_real, lim_real, ex, s_real, lim_real)
                real[q] = resumo(S.simula_tick(d, s_real, lim_real, sa, q, fm, t_sinal))
            s_alt = -s_real
            lim_alt = R.limite(c, s_alt, ent["recuo"])
            sa = R.saida_de(c, s_alt, lim_alt, ex, s_real, lim_real)
            alt = resumo(S.simula_tick(d, s_alt, lim_alt, sa, 2, fm, t_sinal))
            r["fills"][fm] = dict(real=real, alt2=alt)
        out[cel["id"]] = r
    return dict(dia=dia, cel=out, t_sinal=t_sinal)


def main():
    _init()
    dias = sorted(_G["ctx"])
    res = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=5) as ex:
        fut = {ex.submit(processa_dia, d): d for d in dias}
        for f in as_completed(fut):
            r = f.result(); res[r["dia"]] = r
            n_trig = sum(v is not None for v in r["cel"].values())
            print(f"[{len(res)}/{len(dias)} {time.time()-t0:.0f}s] {r['dia']} celulas com ordem: {n_trig}", flush=True)
    pickle.dump(res, open(AQUI / "out" / "dia_resultados.pkl", "wb"))


if __name__ == "__main__":
    (AQUI / "out").mkdir(exist_ok=True)
    main()
