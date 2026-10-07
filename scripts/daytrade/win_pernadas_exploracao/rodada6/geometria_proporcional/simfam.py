"""Simulacao por familia (E1/E2/E3) e agregacao em celulas. Ver geomlib.py para as definicoes."""
from __future__ import annotations
import itertools
import numpy as np
import geomlib as G
from geomlib import TICK, CUSTO, DESL, tk

GEOMS = {}
GEOMS["E1"] = [(r, s, mm) for r in G.RS for s in G.SS for mm in G.MS]
GEOMS["E2"] = [(j, sm, mm) for j in G.JS for sm in G.STOPMODES for mm in G.MS]
GEOMS["E3"] = [(r, N, k) for r in G.RS for N in G.NS for k in G.KALVO]


def frames(d):
    return {1: (d["l"], d["h"], d["c"]), -1: (-d["h"], -d["l"], -d["c"])}


def fill_idx(LO, HI, m, a, level, Eref, bey, lowcancel=None):
    n = len(LO)
    wend = min(int(np.searchsorted(m, m[a] + G.TTL_MIN, side="right")) - 1, n - 1)
    if wend <= a:
        return -1, a + 1
    hseg = HI[a + 1:wend + 1] > Eref
    cb = wend if not hseg.any() else a + 1 + int(hseg.argmax())
    if lowcancel is not None:
        lc = LO[a + 1:cb + 1] <= lowcancel
        if lc.any():
            cb = a + 1 + int(lc.argmax())
    lseg = LO[a + 1:cb + 1] <= level - bey
    if not lseg.any():
        return -1, wend
    return a + 1 + int(lseg.argmax()), wend


def resolve(LO, HI, CL, f, level, sd, tp, bey):
    n = len(LO)
    if LO[f] <= level - sd:
        return f, -(sd + DESL + CUSTO), 0
    if f + 1 >= n:
        return f, CL[-1] - level - DESL - CUSTO, 2
    return None


def sim_family(days, evs, fam):
    """evs: lista de dicts (com 'di' e, para E2, 'mn','Hb'). Retorna dict de arrays (Nev,G,2) + meta (Nev)."""
    geoms = GEOMS[fam]; NG = len(geoms)
    Nev = len(evs)
    valid = np.zeros((Nev, NG, 2), bool)
    filled = np.zeros((Nev, NG, 2), bool)
    xbar = np.zeros((Nev, NG, 2), np.int32)
    pnl = np.zeros((Nev, NG, 2), np.float32)
    code = np.full((Nev, NG, 2), -1, np.int8)
    sdv = np.zeros((Nev, NG), np.float32); tpd = np.zeros((Nev, NG), np.float32)
    fcache = {}
    for ie, ev in enumerate(evs):
        d = days[ev["di"]]
        key = ev["di"]
        if key not in fcache:
            fcache = {key: frames(d)}
        LO, HI, CL = fcache[key][ev["sg"]]
        m = d["m"]; a = ev["a"]; E = ev["E"]; A = ev["A"]
        cl = CL[a]
        cache = {}
        for g, par in enumerate(geoms):
            if fam == "E1":
                r, s, mm = par
                level = float(tk(E - r * A))
                if not (level < cl and level > E - ev["T"] + TICK):
                    continue
                rec = E - level
                sd = float(tk(s * rec)); tp = float(tk(E + (mm - 1) * rec))
                lowc = None
            elif fam == "E2":
                j, sm, mm = par
                mn, Hb = ev["mn"], ev["Hb"]
                level = float(tk(Hb - j * (Hb - mn)))
                if not (level < cl and level > mn):
                    continue
                if sm == "tk1": sd = level - (mn - TICK)
                elif sm == "tk3": sd = level - (mn - 3 * TICK)
                elif sm == "d05": sd = float(tk(0.5 * (level - mn)))
                else: sd = level - mn
                tp = float(tk(E + (mm - 1) * (E - mn)))
                lowc = mn - TICK
            else:
                r, N, k = par
                level = float(tk(E - r * A))
                if not (level < cl and level > E - ev["T"] + TICK):
                    continue
                lowN = LO[int(np.searchsorted(m, m[a] - N + 1, side='left')):a + 1].min()
                sd = level - (lowN - TICK)
                tp = float(tk(level + k * sd))
                lowc = None
            if not (G.MIN_STOP <= sd <= G.MAX_STOP and tp > level and (tp - level) >= 2.95 * sd):
                continue
            sdv[ie, g] = sd; tpd[ie, g] = tp - level
            for mi, cons in enumerate((True, False)):
                bey = TICK if cons else 0.0
                ck = (level, mi, lowc)
                if ck not in cache:
                    f, wend = fill_idx(LO, HI, m, a, level, E, bey, lowc)
                    if f >= 0 and f + 1 < len(LO):
                        rmin = np.minimum.accumulate(LO[f + 1:]); rmax = np.maximum.accumulate(HI[f + 1:])
                    else:
                        rmin = rmax = None
                    cache[ck] = (f, wend, rmin, rmax)
                f, wend, rmin, rmax = cache[ck]
                valid[ie, g, mi] = True
                if f < 0:
                    xbar[ie, g, mi] = wend
                    continue
                filled[ie, g, mi] = True
                if LO[f] <= level - sd:
                    xbar[ie, g, mi] = f; pnl[ie, g, mi] = -(sd + DESL + CUSTO); code[ie, g, mi] = 0
                    continue
                if rmin is None:
                    xbar[ie, g, mi] = f; pnl[ie, g, mi] = CL[-1] - level - DESL - CUSTO; code[ie, g, mi] = 2
                    continue
                n1 = len(rmin)
                ist = int(np.searchsorted(-rmin, -(level - sd), side="left"))
                itg = int(np.searchsorted(rmax, tp + bey, side="left"))
                if ist < n1 and ist <= itg:
                    xbar[ie, g, mi] = f + 1 + ist; pnl[ie, g, mi] = -(sd + DESL + CUSTO); code[ie, g, mi] = 0
                elif itg < n1:
                    xbar[ie, g, mi] = f + 1 + itg; pnl[ie, g, mi] = (tp - level) - CUSTO; code[ie, g, mi] = 1
                else:
                    xbar[ie, g, mi] = f + n1; pnl[ie, g, mi] = CL[-1] - level - DESL - CUSTO; code[ie, g, mi] = 2
    return dict(valid=valid, filled=filled, xbar=xbar, pnl=pnl, code=code, sd=sdv, tpd=tpd)


def take_mask(evs_di, evs_a, res):
    """Bloqueio sequencial: um trade (ou ordem pendente) por vez por dia e por celula-geometria.
    Eventos assumidos em ordem (dia, barra de armar)."""
    valid, filled, xbar = res["valid"], res["filled"], res["xbar"]
    Nev, NG, _ = valid.shape
    taken = np.zeros_like(valid)
    di = np.asarray(evs_di); a = np.asarray(evs_a)
    for g in range(NG):
        for mi in range(2):
            blocked = -1; cur = -1
            v = valid[:, g, mi]; xb = xbar[:, g, mi]
            idx = np.nonzero(v)[0]
            for ie in idx:
                if di[ie] != cur:
                    cur = di[ie]; blocked = -1
                if a[ie] > blocked:
                    taken[ie, g, mi] = True
                    blocked = xb[ie]
    return taken
