"""Utilitarios do estudo de rotacao. Nada existente e editado. Roda de qualquer pasta."""
import sys, json, pickle
from pathlib import Path
import numpy as np
import pandas as pd

ER = Path(__file__).resolve().parent
RAIZ = ER.parent
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo4")); sys.path.insert(0, str(RAIZ / "ciclo3"))
import base, robo, cfg4, robo_v4
from cfg4 import av, an

EF = av.eficiencia_todos()          # ef do dia inteiro (so para ROTULO/estrato; nunca como entrada causal)
FR2 = an.FR2


def dias90():
    du = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in du["ciclo0"]["dias"]]
    for c in ("ciclo1", "ciclo2", "ciclo3", "ciclo4"):
        out += [(x["dia"], "c" + c[-1]) for x in du[c]["dias"]]
    assert len(out) == 90
    return out


D90 = dias90(); DIAS = [d for d, _ in D90]; CIC = np.array([c for _, c in D90])
M40 = np.isin(CIC, ["c3", "c4"])
def estrato3(ef): return "rot" if ef < 0.15 else ("int" if ef < 0.25 else "dir")
EST3 = np.array([estrato3(EF[d]) for d in DIAS])
EST2 = np.array(["dir" if EF[d] >= 0.25 else "nd" for d in DIAS])


def repond(v, mask=None):
    m = np.ones(len(v), bool) if mask is None else mask
    return sum(f * (v[m & (EST2 == e)].mean() if (m & (EST2 == e)).any() else 0.0) for e, f in FR2.items())


def lodo_min(v, vb):
    ds = []
    for i in range(len(v)):
        m = np.ones(len(v), bool); m[i] = False
        ds.append(repond(v, m) - repond(vb, m))
    return min(ds), DIAS[int(np.argmin(ds))]


def linha(v, vb):
    d = v - vb; lm, ld = lodo_min(v, vb)
    return dict(total=float(v.sum()), rep=float(repond(v)), d_rep=float(repond(v) - repond(vb)),
                d_nd=float(d[EST2 == "nd"].mean()), d_dir=float(d[EST2 == "dir"].mean()),
                d_40=float(d[M40].sum()), d_40_dia=float(d[M40].mean()), d_tot=float(d.sum()),
                pior=int((d < -0.5).sum()), melhor=int((d > 0.5).sum()), pior_dia=float(v.min()),
                lodo_min=float(lm), lodo_dia=ld, neg=int((v < 0).sum()))


# ---------------------------------------------------------------- estimativas causais do regime (so ctx ate t)
def feats(ctx):
    """Tudo calculado so com dados ate ctx.t (velas M15 fechadas e M1 < t)."""
    h = ctx.hoje; o0 = float(h.open.iloc[0]); c = float(h.close.iloc[-1])
    rng = float((h.high - h.low).sum())
    hi = float(h.high.max()); lo = float(h.low.min())
    f = {}
    f["ef_parc"] = abs(c - o0) / rng if rng > 0 else 0.0                      # baixo => rotacao
    f["amp_atrd"] = (hi - lo) / ctx.atrd if ctx.atrd > 0 else np.nan          # baixo => rotacao
    d = ctx.m1[ctx.m1.index.normalize() == h.index[0].normalize()]
    tp = (d.high + d.low + d.close) / 3; vol = d.real_volume.replace(0, np.nan).fillna(1.0)
    vw = (tp * vol).cumsum() / vol.cumsum()
    sg = np.sign((d.close - vw).values); sg = sg[sg != 0]
    f["cruz_vwap"] = int((np.diff(sg) != 0).sum()) if len(sg) > 1 else 0      # alto => rotacao
    hh, ll = h.high.values, h.low.values
    if len(h) > 1:
        ov = [max(0.0, min(hh[i], hh[i-1]) - max(ll[i], ll[i-1])) / (max(hh[i], hh[i-1]) - min(ll[i], ll[i-1]) + 1e-9) for i in range(1, len(h))]
        f["sobrep"] = float(np.mean(ov))                                      # alto => rotacao
    else: f["sobrep"] = np.nan
    pos = (c - lo) / (hi - lo) if hi > lo else 0.5
    f["meio_faixa"] = min(pos, 1 - pos)                                       # alto (perto do meio) => rotacao
    pc = float(ctx.diario.close.iloc[-1]) if len(ctx.diario) else o0
    f["gap_atrd"] = abs(o0 - pc) / ctx.atrd if ctx.atrd > 0 else np.nan       # baixo => rotacao
    f["desloc_atr15"] = abs(c - o0) / ctx.atr15 if ctx.atr15 > 0 else np.nan  # baixo => rotacao
    return f


# orientacao DECLARADA ANTES de medir: +1 = valor alto indica rotacao; -1 = valor baixo indica rotacao
SINAL = dict(ef_parc=-1, amp_atrd=-1, cruz_vwap=+1, sobrep=+1, meio_faixa=+1, gap_atrd=-1, desloc_atr15=-1)
