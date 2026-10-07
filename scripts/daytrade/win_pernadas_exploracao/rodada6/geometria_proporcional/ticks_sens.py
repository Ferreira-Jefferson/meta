"""Sensibilidade com ticks (mar-jun, desc): mesmas celulas congeladas + stop curto, M1 x ticks lado a lado, mesmos dias."""
import sys, os, json, pickle, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import geomlib as G, stage as st, detail as D, simfam as S
HERE = os.path.dirname(os.path.abspath(__file__))
_G = {}
def _init():
    days = G.load_days(); _G["days"] = days; _G["ars"] = G.avg_range_prev(days)
    _G["ticks"] = pickle.load(open(os.path.join(HERE, "ticks_desc.pkl"), "rb"))
    _G["fr"] = json.load(open(os.path.join(HERE, "congelado_ANTES_da_confirmacao.json")))["celulas"]

def unit(chunk):
    days = _G["days"]; ars = _G["ars"]; tks = _G["ticks"]
    use = list(days); flags = {}
    for di in chunk:
        td = tks[di]; d = days[di]
        v, o = G.vol_flags(d, ars[di])
        mm = {int(m): i for i, m in enumerate(d["m"])}
        prev = np.array([mm.get(int(x) - 1, -1) for x in td["m"]])
        flags[di] = (np.where(prev >= 0, v[np.maximum(prev, 0)], False), np.where(prev >= 0, o[np.maximum(prev, 0)], False))
        use[di] = td
    built = st.build(use, ars, chunk, flags)
    out = {"cells": {}, "agg": {}}
    for c in _G["fr"]:
        for mode in (0, 1):
            tr = D.cell_trades(built, chunk, c["T"], c["fam"], c["g"], c["filt"], mode)
            tr["day"] = np.array([chunk[i] for i in tr["day"]], int)
            out["cells"][(c["T"], c["fam"], c["g"], c["filt"], mode)] = tr
    # stop curto: E1 s=1/10 e E3 N=5, sem filtro (filt 0), conservador
    for (T, f), (evs, res, taken) in built.items():
        if res is None: continue
        for g, par in enumerate(S.GEOMS[st.FAM_SIM[f]]):
            curto = (f == "E1" and abs(par[1] - 0.1) < 1e-9) or (f == "E3" and par[1] == 5)
            if not curto: continue
            tr = D.cell_trades(built, chunk, T, f, g, 0, 0)
            out["agg"][(T, f, g)] = (len(tr["pnl"]), float(tr["pnl"].sum()), int((tr["pnl"] > 0).sum()))
    return out

def m1_side(win):
    win0, built, dates = pickle.load(open(os.path.join(HERE, "built_desc.pkl"), "rb"))
    loc = {di: i for i, di in enumerate(win0)}
    res = {"cells": {}, "agg": {}}
    fr = json.load(open(os.path.join(HERE, "congelado_ANTES_da_confirmacao.json")))["celulas"]
    wset = set(win)
    for c in fr:
        for mode in (0, 1):
            tr = D.cell_trades(built, win0, c["T"], c["fam"], c["g"], c["filt"], mode)
            keep = np.array([win0[i] in wset for i in tr["day"]], bool)
            tr["day"] = np.array([win0[i] for i in tr["day"]], int)[keep]; tr["pnl"] = tr["pnl"][keep]
            res["cells"][(c["T"], c["fam"], c["g"], c["filt"], mode)] = tr
    for (T, f), (evs, r, taken) in built.items():
        if r is None: continue
        for g, par in enumerate(S.GEOMS[st.FAM_SIM[f]]):
            curto = (f == "E1" and abs(par[1] - 0.1) < 1e-9) or (f == "E3" and par[1] == 5)
            if not curto: continue
            tr = D.cell_trades(built, win0, T, f, g, 0, 0)
            keep = np.array([win0[i] in wset for i in tr["day"]], bool)
            p = tr["pnl"][keep]
            res["agg"][(T, f, g)] = (len(p), float(p.sum()), int((p > 0).sum()))
    return res

if __name__ == "__main__":
    tks = pickle.load(open(os.path.join(HERE, "ticks_desc.pkl"), "rb"))
    win = sorted(tks.keys()); print(len(win), "dias com tick", flush=True)
    chunks = [win[i::6] for i in range(6)]
    cells = {}; agg = {}
    with ProcessPoolExecutor(3, initializer=_init) as ex:
        for f in as_completed([ex.submit(unit, c) for c in chunks]):
            o = f.result(); print("chunk ok", flush=True)
            for k, v in o["cells"].items():
                if k not in cells: cells[k] = {kk: vv for kk, vv in v.items()}
                else:
                    for kk in ("day", "pnl", "code", "sd", "tpd", "a"): cells[k][kk] = np.concatenate([cells[k][kk], v[kk]])
                    cells[k]["n_orders"] += v["n_orders"]
            for k, v in o["agg"].items():
                a = agg.get(k, (0, 0.0, 0)); agg[k] = (a[0] + v[0], a[1] + v[1], a[2] + v[2])
    m1 = m1_side(win)
    pickle.dump(dict(win=win, tick=dict(cells=cells, agg=agg), m1=m1), open(os.path.join(HERE, "ticks_sens.pkl"), "wb"))
    print("fim", flush=True)
