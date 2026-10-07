"""Nulo 2 (permutacao de rotulos de tendencia): precos reais; o sinal de tendencia de cada pregao e' trocado pelo de
outro pregao sorteado (mesmo minuto). Se a tendencia nao informa nada, favor-contra ~ 0. perm 0 = real."""
import sys, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import run
from base import *

SC = ["i_leg", "i_open", "i_vwap", "i_m15", "i_h1", "d_ma20", "d_wkprev", "conc3", "conc5"]
GEOMS = [(150, 100, 750), ("mm", 150, 750)]
PERS = {"desc": ("2026.01.01", "2026.06.30"), "conf": ("2026.07.01", "2026.08.31")}


def sim_s(s_all, X, S, A, mask_days):
    G = run._G; P = G["P"]
    dia, pnl, tip = [], [], []
    for di, (a, b) in enumerate(P["sl"]):
        if not mask_days[di]:
            continue
        tr, no = sim_dia(G["h"][a:b], G["l"][a:b], G["c"][a:b], G["mn"][a:b], s_all[a:b], G["hh"][a:b], G["ll"][a:b],
                         G["ema"][a:b], P["FL"]["todos"][a:b], None if X == "mm" else X, S, A, True)
        for (j, p, k) in tr:
            dia.append(di); pnl.append(p); tip.append(k)
    return np.array(dia), np.array(pnl), np.array(tip)


def um(perm):
    run.init()
    G = run._G; P = G["P"]
    days = G["days"]; nd = len(days)
    ok = days >= "2026.01.01"
    idx26 = np.flatnonzero(ok)
    rng = np.random.default_rng(perm)
    rows = []
    for sc in SC:
        s0 = P["F"][sc]
        if perm == 0:
            s = s0
        else:
            s = s0.copy()
            donor = rng.permutation(idx26)
            for di, dj in zip(idx26, donor):
                a, b = P["sl"][di]; c, d = P["sl"][dj]
                k = np.minimum(np.arange(b - a), d - c - 1)
                s[a:b] = s0[c:d][k]
        for (X, S, A) in GEOMS:
            for mode, ss in (("favor", s), ("contra", (-s).astype(np.int8))):
                dia, pnl, tip = sim_s(ss, X, S, A, ok)
                for per, (a, b) in PERS.items():
                    m = (days[dia] >= a) & (days[dia] <= b)
                    k = tip[m]; r = k != 2
                    rows.append(dict(perm=perm, scale=sc, geom=f"{X}/{S}/{A}", mode=mode, per=per, n=int(m.sum()), res=int(r.sum()),
                                     wins=int((k == 1).sum()), soma=float(pnl[m].sum())))
    return rows


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    rows = []; t0 = time.time()
    with ProcessPoolExecutor(4) as ex:
        fs = [ex.submit(um, p) for p in range(0, n + 1)]
        for f in as_completed(fs):
            r = f.result(); rows.extend(r); print("perm", r[0]["perm"], round(time.time() - t0), "s", flush=True)
    pd.DataFrame(rows).to_csv("nulo2_resultado.csv", index=False)
