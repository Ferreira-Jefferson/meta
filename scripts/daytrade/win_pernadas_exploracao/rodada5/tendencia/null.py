"""Nulo: velas M1 embaralhadas em blocos de 30 min dentro de cada pregao (mesmo codigo: features recalculadas).
seed 0 = dados reais. Metrica por escala: acerto/esperanca favor x contra, e as 8 regras congeladas."""
import sys, json, pickle, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import run
from base import *

GEOMS = [(X, S, 750) for X in (150, 300, "mm") for S in (100, 150)]
FRO = json.load(open("congelado_ANTES_da_confirmacao.json"))["celulas"]
PERS = {"desc": ("2026.01.01", "2026.06.30"), "conf": ("2026.07.01", "2026.08.31")}


def embaralha(d, seed):
    rng = np.random.default_rng(seed)
    d = d.copy()
    blk = (d["d"].astype(str) + "_" + (d["min"] // 30).astype(str)).values
    idx = np.arange(len(d))
    new = idx.copy()
    # grupos contiguos
    ch = np.flatnonzero(blk[1:] != blk[:-1]) + 1
    st = np.concatenate([[0], ch]); en = np.concatenate([ch, [len(d)]])
    for a, b in zip(st, en):
        new[a:b] = a + rng.permutation(b - a)
    for c in ("o", "h", "l", "c", "tv", "v"):
        d[c] = d[c].values[new]
    # coerencia minima: h/l ja pertencem a propria barra permutada
    return d


def um(seed):
    d = carrega()
    if seed:
        d = embaralha(d, seed)
    F, _ = features(d); FL = filtros(d)
    P = dict(d=d[["d", "o", "h", "l", "c", "min"]].reset_index(drop=True), F=F, FL=FL, sl=dias_slices(d), days=list(d.d.unique()))
    run.init(data=P)
    rows = []
    def reg(tag, scale, mode, filt, X, S, A):
        dia, pnl, tip, ordens = run.trades(scale, mode, filt, X, S, A, True)
        for per, (a, b) in PERS.items():
            r = run.metricas(dia, pnl, tip, ordens, a, b, S, A, nboot=10)
            n = r.get("n", 0)
            wins = round(r.get("acerto", 0) * (n - r.get("unres", 0) * n)) if n else 0
            rows.append(dict(seed=seed, tag=tag, scale=scale, mode=mode, filt=filt, X=str(X), S=S, A=A, per=per, n=n,
                             res=n - round(r.get("unres", 0) * n) if n else 0, wins=wins, soma=r.get("esp", 0) * n))
    for sc in SCALES:
        for mode in ("favor", "contra"):
            for X, S, A in GEOMS:
                reg("escala", sc, mode, "todos", X, S, A)
    for X, S, A in GEOMS:
        reg("escala", "-", "none", "todos", X, S, A)
    for f in FRO:
        reg("congelada", f["scale"], f["mode"], f["filt"], f["X"] if f["X"] == "mm" else int(f["X"]), f["stop"], f["alvo"])
    return rows


if __name__ == "__main__":
    ns = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    rows = []
    t0 = time.time()
    with ProcessPoolExecutor(4) as ex:
        fs = [ex.submit(um, s) for s in range(0, ns + 1)]
        for f in as_completed(fs):
            r = f.result(); rows.extend(r)
            print("seed", r[0]["seed"], "ok", round(time.time() - t0), "s", flush=True)
    pd.DataFrame(rows).to_csv("nulo_resultado.csv", index=False)
