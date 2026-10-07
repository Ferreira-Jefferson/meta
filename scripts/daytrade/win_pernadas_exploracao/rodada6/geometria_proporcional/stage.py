"""Construcao de eventos/trades e tabela de celulas (geometria x filtros)."""
from __future__ import annotations
import itertools
import numpy as np
import geomlib as G
import simfam as S

FAMS = ["E1", "E2a", "E2b", "E2c", "E3"]          # E2a/b/c = k 25/38/50
FAM_SIM = {"E1": "E1", "E2a": "E2", "E2b": "E2", "E2c": "E2", "E3": "E3"}
FILTS = list(itertools.product((0, 1), (-1, 0, 1, 2), (0, 1, 2), (0, 1, 2)))   # trend, hora, vol, ordem
FILT_NAMES = dict(trend={0: "qualquer", 1: "a favor"}, hora={-1: "todas", 0: "<11h", 1: "11-13h", 2: ">=13h"},
                  vol={0: "-", 1: "v2x", 2: "onda"}, ordem={0: "todos", 1: "1o recuo", 2: "2o+"})


def hbin(minute):
    return 0 if minute < 660 else (1 if minute < 780 else 2)


def build(days_use, ars, win, flags=None):
    """win: lista de indices globais de dias (2026). Retorna dict famkey/T -> (evs, res, taken)."""
    ev_lists = {(T, f): [] for T in G.TS for f in FAMS}
    for di in win:
        d = days_use[di]
        d750 = G.dir750_series(d)
        v2x, onda = flags[di] if flags is not None else G.vol_flags(d, ars[di])
        for T in G.TS:
            e1, e2 = G.gen_events(d, T, d750)
            for kk, lst in enumerate(([e1] + e2)):
                pass
            def tag(e):
                e["di"] = di; e["T"] = T
                e["hb"] = hbin(d["m"][e["a"]]); e["v2x"] = bool(v2x[e["a"]]); e["onda"] = bool(onda[e["a"]])
                return e
            ev_lists[(T, "E1")] += [tag(e) for e in e1]
            ev_lists[(T, "E3")] += [tag(dict(e)) for e in e1]
            for kk, nm in enumerate(("E2a", "E2b", "E2c")):
                ev_lists[(T, nm)] += [tag(e) for e in e2[kk]]
    out = {}
    for (T, f), evs in ev_lists.items():
        if not evs:
            out[(T, f)] = (evs, None, None); continue
        res = S.sim_family(days_use, evs, FAM_SIM[f])
        taken = S.take_mask([e["di"] for e in evs], [e["a"] for e in evs], res)
        out[(T, f)] = (evs, res, taken)
    return out


def filter_masks(evs):
    tr = np.array([e["tr"] for e in evs]); hb = np.array([e["hb"] for e in evs])
    v2 = np.array([e["v2x"] for e in evs]); on = np.array([e["onda"] for e in evs])
    od = np.array([e["ord"] for e in evs])
    FM = np.zeros((len(FILTS), len(evs)), bool)
    for k, (t, h, v, o) in enumerate(FILTS):
        m = np.ones(len(evs), bool)
        if t == 1: m &= (tr == 1)
        if h >= 0: m &= (hb == h)
        if v == 1: m &= v2
        if v == 2: m &= on
        if o == 1: m &= (od == 1)
        if o == 2: m &= (od >= 2)
        FM[k] = m
    return FM


def grid_stats(built, win, mode=0):
    """Tabela de celulas (conservador mode=0). Retorna dict de arrays + lista de chaves."""
    loc = {di: k for k, di in enumerate(win)}
    ND = len(win)
    rows = []
    for (T, f), (evs, res, taken) in built.items():
        if res is None:
            continue
        fam = S.GEOMS[FAM_SIM[f]]
        Dm = np.zeros((len(evs), ND), np.float32)
        Dm[np.arange(len(evs)), [loc[e["di"]] for e in evs]] = 1
        FM = filter_masks(evs).astype(np.float32)           # (F, Nev)
        for g in range(len(fam)):
            tk_ = taken[:, g, mode]
            if not tk_.any():
                continue
            fl = res["filled"][:, g, mode] & tk_
            pn = np.where(fl, res["pnl"][:, g, mode], 0.0).astype(np.float32)
            Wf = fl.astype(np.float32); Wo = tk_.astype(np.float32)
            Wwin = (fl & (res["pnl"][:, g, mode] > 0)).astype(np.float32)
            Wls = np.where(fl & (res["pnl"][:, g, mode] < 0), -res["pnl"][:, g, mode], 0.0).astype(np.float32)
            Sd = Dm.T @ (FM.T * pn[:, None])               # (ND, F)
            Nd = Dm.T @ (FM.T * Wf[:, None])
            No = (FM * Wo[None, :]).sum(1)
            Nw = (FM * Wwin[None, :]).sum(1)
            Ls = (FM * Wls[None, :]).sum(1)
            Ntot = Nd.sum(0); Stot = Sd.sum(0)
            with np.errstate(all="ignore"):
                mean = Stot / Ntot
                resid = Sd - mean[None, :] * Nd
                se = np.sqrt(ND / max(ND - 1, 1) * (resid ** 2).sum(0)) / Ntot
                t = mean / se
            for k in range(len(FILTS)):
                if Ntot[k] <= 0:
                    continue
                rows.append((T, f, g, k, No[k], Ntot[k], Stot[k], Nw[k], Ls[k], mean[k], t[k]))
    cols = ["T", "fam", "g", "filt", "nord", "n", "sum", "nwin", "lsum", "mean", "t"]
    return cols, rows
