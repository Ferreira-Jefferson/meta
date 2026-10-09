"""Avaliacao paralela (ProcessPoolExecutor, submit/as_completed) das configuracoes do ciclo 4 nos 70 dias, com cache em disco.
Metrica = a do ciclo 3 (Emenda 1): reponderado = 3,8% direcional (ef>=0,25) + 96,2% nao-direcional (fracoes exatas de ef_todos)."""
import sys, pickle, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
C4 = Path(__file__).resolve().parent
sys.path.insert(0, str(C4))
import cfg4
from cfg4 import av, an

CACHE = C4 / "cache4.pkl"
D70 = cfg4.dias70()
DIAS = [d for d, _ in D70]
CIC = np.array([c for _, c in D70])
EF = av.eficiencia_todos()
EST = np.array(["dir" if EF[d] >= 0.25 else "nd" for d in DIAS])
FR2 = an.FR2
M3 = CIC == "c3"; M012 = ~M3


def _um(a):
    ids, dia = a
    return ids, dia, cfg4.resultado_dia(dia, cfg4.monta(list(ids)))


def avalia(configs, workers=6, verbose=True, dias=DIAS):
    cache = pickle.load(open(CACHE, "rb")) if CACHE.exists() else {}
    ks = list(dict.fromkeys(cfg4.chave(c) for c in configs))
    falta = [(k, d) for k in ks for d in dias if (k, d) not in cache]
    if falta:
        pend = {k: sum(1 for kk, _ in falta if kk == k) for k in ks}
        with ProcessPoolExecutor(workers) as ex:
            fut = [ex.submit(_um, a) for a in falta]
            for f in as_completed(fut):
                k, d, r = f.result(); cache[(k, d)] = r
                pend[k] -= 1
                if verbose and pend[k] == 0: print(f"  pronto: {'+'.join(k) or 'v3'}", flush=True)
        pickle.dump(cache, open(CACHE, "wb"))
    return {k: {d: cache[(k, d)] for d in dias} for k in ks}


def vec(res): return np.array([res[d]["brl"] for d in DIAS])


def repond(v, mask=None):
    m = np.ones(len(v), bool) if mask is None else mask
    return sum(f * (v[m & (EST == e)].mean() if (m & (EST == e)).any() else 0.0) for e, f in FR2.items())


def lodo_min(v, vb):
    ds = []
    for i in range(len(v)):
        m = np.ones(len(v), bool); m[i] = False
        ds.append(repond(v, m) - repond(vb, m))
    return min(ds), DIAS[int(np.argmin(ds))]


def linha(v, vb):
    d = v - vb
    lm, ld = lodo_min(v, vb)
    return dict(total=float(v.sum()), rep=float(repond(v)), d_rep=float(repond(v) - repond(vb)),
                d_dir=float(d[EST == "dir"].mean()), d_nd=float(d[EST == "nd"].mean()),
                d012=float(d[M012].sum()), d3=float(d[M3].sum()), d_tot=float(d.sum()),
                pior=int((d < -0.5).sum()), melhor=int((d > 0.5).sum()), pior_dia=float(v.min()),
                lodo_min=float(lm), lodo_dia=ld, dir_mean=float(v[EST == "dir"].mean()), nd_mean=float(v[EST == "nd"].mean()))
