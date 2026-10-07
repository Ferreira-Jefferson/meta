"""Grade de celulas: tendencia x modo (favor/contra/nenhum) x filtro x geometria. Descoberta jan-jun, confirmacao jul-ago, ref set."""
import sys, pickle, time, itertools, json
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from base import *

PER = {"desc": ("2026.01.01", "2026.06.30"), "conf": ("2026.07.01", "2026.08.31"), "set": ("2026.09.01", "2026.09.30")}
XS = [150, 300, "mm"]
STOPS = [75, 100, 150, 200]
ALVOS = [600, 750, 1000]
_G = {}


def init(path="prep.pkl", data=None):
    P = data if data is not None else pickle.load(open(path, "rb"))
    d = P["d"]
    G = dict(P=P)
    G["o"], G["h"], G["l"], G["c"], G["mn"] = (d[k].values for k in ("o", "h", "l", "c", "min"))
    G["hh"] = np.empty(len(d)); G["ll"] = np.empty(len(d))
    for a, b in P["sl"]:
        G["hh"][a:b] = np.maximum.accumulate(G["h"][a:b]); G["ll"][a:b] = np.minimum.accumulate(G["l"][a:b])
    G["ema"] = ema_arr(G["c"], 60)
    G["days"] = np.array(P["days"])
    G["dayidx"] = np.arange(len(P["days"]))
    _G.clear(); _G.update(G)


def trades(scale, mode, filt, X, stop, alvo, cons):
    """-> (dia, pnl, tipo) arrays e ordens por dia."""
    G = _G; P = G["P"]
    allow = P["FL"][filt]
    runs = []
    if mode == "none":
        runs = [np.ones(len(G["c"]), np.int8), -np.ones(len(G["c"]), np.int8)]
    else:
        s = P["F"][scale]
        runs = [s if mode == "favor" else (-s).astype(np.int8)]
    dia, pnl, tip = [], [], []
    ordens = np.zeros(len(P["days"]))
    for s_all in runs:
        for di, (a, b) in enumerate(P["sl"]):
            if G["days"][di] < "2026.01.01":
                continue
            tr, no = sim_dia(G["h"][a:b], G["l"][a:b], G["c"][a:b], G["mn"][a:b], s_all[a:b], G["hh"][a:b], G["ll"][a:b],
                             G["ema"][a:b], allow[a:b], None if X == "mm" else X, stop, alvo, cons)
            ordens[di] += no
            for (j, p, k) in tr:
                dia.append(di); pnl.append(p); tip.append(k)
    return np.array(dia, int), np.array(pnl, float), np.array(tip, int), ordens


def metricas(dia, pnl, tip, ordens, d0, d1, stop, alvo, nboot=1000, seed=1):
    G = _G
    dm = (G["days"] >= d0) & (G["days"] <= d1)
    didx = np.flatnonzero(dm)
    m = np.isin(dia, didx)
    p, k, dd = pnl[m], tip[m], dia[m]
    n = len(p)
    out = dict(n=n, dias=len(didx), ordens=float(ordens[didx].sum()))
    if n == 0:
        return out
    res = k != 2
    nr = int(res.sum())
    w = k == 1
    out["fill"] = n / out["ordens"] if out["ordens"] else np.nan
    out["acerto"] = float(w.sum() / nr) if nr else np.nan
    gm = p[w].mean() if w.any() else 0.0
    lm = -p[k == 0].mean() if (k == 0).any() else 0.0
    out["be_emp"] = lm / (gm + lm) if gm + lm else np.nan
    out["nulo"] = stop / (alvo + stop)
    out["esp"] = float(p.mean())
    S = np.bincount(np.searchsorted(didx, dd), weights=p, minlength=len(didx))
    N = np.bincount(np.searchsorted(didx, dd), minlength=len(didx)).astype(float)
    rng = np.random.default_rng(seed)
    ix = rng.integers(0, len(didx), (nboot, len(didx)))
    bm = S[ix].sum(1) / np.maximum(N[ix].sum(1), 1)
    out["lo"], out["hi"] = float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))
    out["brl"] = out["esp"] * 0.2
    mes = np.array([G["days"][x][:7] for x in dd])
    out["mpos"] = float(np.mean([p[mes == u].sum() > 0 for u in np.unique(mes)]))
    seq = best = 0
    for x in p:
        if x < 0:
            seq += 1; best = max(best, seq)
        else:
            seq = 0
    out["seqperd"] = best
    out["ops_dia"] = n / len(didx)
    out["unres"] = float((k == 2).mean())
    return out


def celula(spec):
    scale, mode, filt, X, stop, alvo = spec
    rows = []
    for cons in (True, False):
        dia, pnl, tip, ordens = trades(scale, mode, filt, X, stop, alvo, cons)
        for per, (a, b) in PER.items():
            r = metricas(dia, pnl, tip, ordens, a, b, stop, alvo)
            r.update(scale=scale, mode=mode, filt=filt, X=str(X), stop=stop, alvo=alvo, conv="cons" if cons else "otim", per=per)
            rows.append(r)
    return rows


def lote(specs, path):
    init(path)
    out = []
    for sp in specs:
        out.extend(celula(sp))
    return out


def grade():
    specs = []
    geoms = list(itertools.product(XS, STOPS, ALVOS))
    for sc in SCALES:
        for mode in ("favor", "contra"):
            for (X, S, A) in geoms:
                specs.append((sc, mode, "todos", X, S, A))
    for (X, S, A) in geoms:
        specs.append(("-", "none", "todos", X, S, A))
    # filtros (liga) so em geometrias de referencia
    ref = list(itertools.product(XS, [100, 150], [750, 1000]))
    for filt in ("cedo", "vela"):
        for sc in SCALES:
            for mode in ("favor", "contra"):
                for (X, S, A) in ref:
                    specs.append((sc, mode, filt, X, S, A))
        for (X, S, A) in ref:
            specs.append(("-", "none", filt, X, S, A))
    return specs


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "time":
        init()
        t = time.time()
        r = celula(("i_open", "favor", "todos", 150, 100, 750))
        print(time.time() - t)
        for x in r:
            print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()})
        sys.exit()
    specs = grade()
    print(len(specs), "celulas", flush=True)
    chunks = [specs[i::48] for i in range(48)]
    rows = []
    t0 = time.time()
    with ProcessPoolExecutor(4) as ex:
        futs = [ex.submit(lote, ch, "prep.pkl") for ch in chunks]
        for f in as_completed(futs):
            rows.extend(f.result())
            print(len(rows) // 6, "celulas prontas", round(time.time() - t0), "s", flush=True)
    pd.DataFrame(rows).to_csv("grade_resultado.csv", index=False)
