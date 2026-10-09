import sys, json
sys.path.insert(0, '.')
import numpy as np
import av, cfg3

EF = av.eficiencia_todos()
N = len(EF)
FR3 = {k: sum(av.estrato(e) == k for e in EF.values()) / N for k in ("bom", "int", "ruim")}
FR2 = {"dir": FR3["bom"], "nd": FR3["int"] + FR3["ruim"]}
D50 = cfg3.dias50()
DIAS = [d for d, _ in D50]
CIC = np.array([c for _, c in D50])
EST3 = np.array([av.estrato(EF[d]) for d in DIAS])
EST2 = np.where(EST3 == "bom", "dir", "nd")
M01 = np.isin(CIC, ["c0", "c1"]); M2 = CIC == "c2"


def vec(res):
    return np.array([res[d]["brl"] for d in DIAS])


def repond(v, mask=None):
    """R$/dia reponderado (2 estratos); mask = dias excluidos (False)."""
    m = np.ones(len(v), bool) if mask is None else mask
    out = 0.0
    for e, f in FR2.items():
        sel = m & (EST2 == e)
        out += f * (v[sel].mean() if sel.any() else 0.0)
    return out


def repond3(v):
    return sum(f * v[EST3 == e].mean() for e, f in FR3.items())


def lodo_min(v, vb):
    """minimo/maximo do delta reponderado deixando cada dia de fora"""
    ds = []
    for i in range(len(v)):
        m = np.ones(len(v), bool); m[i] = False
        ds.append(repond(v, m) - repond(vb, m))
    return min(ds), max(ds), DIAS[int(np.argmin(ds))]


def linha(v, vb):
    d = v - vb
    return dict(
        total=v.sum(), rep=repond(v), d_rep=repond(v) - repond(vb), rep3=repond3(v),
        dir=v[EST2 == "dir"].mean(), nd=v[EST2 == "nd"].mean(), ruim=v[EST3 == "ruim"].mean(), int=v[EST3 == "int"].mean(),
        d_dir=d[EST2 == "dir"].mean(), d_nd=d[EST2 == "nd"].mean(), d_ruim=d[EST3 == "ruim"].mean(),
        d01=d[M01].sum(), d2=d[M2].sum(), pior=int((d < -0.5).sum()), melhor=int((d > 0.5).sum()),
        pior_dia=v.min(), lodo=lodo_min(v, vb))
