# -*- coding: utf-8 -*-
"""Rodada 4: grade stop x alvo (110 celulas) com entrada V2 r0 fixa; simulador a tick da rodada 2; paralelo por pregao."""
from __future__ import annotations

import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

AQUI = Path(__file__).resolve().parent
R2 = AQUI.parent / "rodada2_2026_10_06"
sys.path.insert(0, str(R2))
import ctx as C  # noqa: E402
import regras as R  # noqa: E402
import sim as S  # noqa: E402
import ticks_prep as TP  # noqa: E402

STOPS = [300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500]
ALVOS = ["none", "T500", "T1000", "T1500", "T2000", "1R", "1.5R", "2R", "3R", "P50@1R", "BE1R"]
ENT = dict(id="V2 r0", fam="V2", recuo=0.0)
QS = (1, 2, 3, 4, 5)
FILLS = ("toque", "atrav+1t")
_G = {}


def cel_id(s, a):
    return f"S{s} | {a}"


def ex_de(s, a):
    ex = dict(id=cel_id(s, a), fam=a, stop=("pts", s), target=None, trail=None, be=None, partial=None, tstop=None)
    if a.startswith("T"):
        ex["target"] = ("pts", float(a[1:]))
    elif a in ("1R", "1.5R", "2R", "3R"):
        ex["target"] = ("rr", float(a[:-1]))
    elif a == "P50@1R":
        ex["target"] = ("rr", 1.0); ex["partial"] = 0.5
    elif a == "BE1R":
        ex["be"] = float(s)
    return ex


def grade():
    return [dict(id=cel_id(s, a), s=s, a=a, ent=ENT, ex=ex_de(s, a)) for a in ALVOS for s in STOPS]


def _init():
    if "bj" not in _G:
        bj, dj, ctx = C.constroi()
        _G.update(bj=bj, ctx=ctx, grade=grade())


def resumo(tr):
    if tr is None:
        return None
    return dict(pnl=tr.pnl, legs=[(g.qty, g.reason, g.exit_t, g.exit_price) for g in tr.legs], worst=tr.pior_pts,
                fill_t=tr.fill_t, entry=tr.entry_price, qty=tr.qty, sai_fill=tr.sai_na_barra_do_fill, mae=tr.mae_pts, side=tr.side)


def processa_dia(dia):
    _init()
    c = _G["ctx"][dia]
    b = C.barras_do_dia(_G["bj"], dia)
    t, p = TP.carrega(dia)
    d = S.DiaTicks(t=t, p=p, bst=b["st"], bo=b["o"], bh=b["h"], bl=b["l"], bc=b["c"])
    t_sinal = int(b["st"][0] + S.M5)
    s_real = R.gatilho(c, ENT)
    out = {}
    if s_real == 0:
        return dict(dia=dia, cel={g["id"]: None for g in _G["grade"]}, t_sinal=t_sinal)
    lim = R.limite(c, s_real, ENT["recuo"])
    for g in _G["grade"]:
        sa = R.saida_de(c, s_real, lim, g["ex"], s_real, lim)
        r = dict(side=s_real, fills={})
        for fm in FILLS:
            real = {q: resumo(S.simula_tick(d, s_real, lim, sa, q, fm, t_sinal)) for q in QS}
            lim_a = R.limite(c, -s_real, ENT["recuo"])
            sa_a = R.saida_de(c, -s_real, lim_a, g["ex"], s_real, lim)
            alt = resumo(S.simula_tick(d, -s_real, lim_a, sa_a, 2, fm, t_sinal))
            r["fills"][fm] = dict(real=real, alt2=alt)
        out[g["id"]] = r
    return dict(dia=dia, cel=out, t_sinal=t_sinal)


def main():
    _init()
    dias = sorted(_G["ctx"])
    res = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=5) as ex:
        fut = {ex.submit(processa_dia, d): d for d in dias}
        for f in as_completed(fut):
            r = f.result()
            res[r["dia"]] = r
            print(f"[{len(res)}/{len(dias)} {time.time() - t0:.0f}s] {r['dia']}", flush=True)
    pickle.dump(res, open(AQUI / "out" / "dia_resultados.pkl", "wb"))


if __name__ == "__main__":
    main()
