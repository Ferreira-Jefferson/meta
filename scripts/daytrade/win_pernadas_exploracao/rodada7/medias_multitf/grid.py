"""grid: celulas (config de evento + geometria), avaliacao e execucao paralela (max 4 workers)."""
import sys, os, time, pickle
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import core

REF_P = (9, 21, 50, "ema")
REF_CFG = dict(ltf=5, htf=15, h1=False, var="c", trend="strict", breach="fms", ref="m", x=0.5, P=REF_P)
REF_GEOM = dict(entry="cl", stop="x", N=15, Katr=1.0, K=5, ttl=10, otim=False)


def cfgkey(cfg):
    return tuple(sorted((k, v) for k, v in cfg.items()))


def mk(axis, value, cfg_over=None, geom_over=None):
    cfg = dict(REF_CFG); geom = dict(REF_GEOM)
    if cfg_over: cfg.update(cfg_over)
    if geom_over: geom.update(geom_over)
    return dict(axis=axis, value=value, cfg=cfg, geom=geom)


def all_cells():
    cells = [mk("ref", "ref")]
    P = lambda f=9, m=21, s=50, k="ema": dict(P=(f, m, s, k))
    for f in (5, 6, 7, 8, 9, 10, 11, 12, 13, 15): cells.append(mk("fast", f, P(f=f)))
    for m in (15, 17, 19, 21, 24, 28, 30, 34, 40): cells.append(mk("mid", m, P(m=m)))
    for s in (34, 40, 45, 50, 60, 72, 89, 100, 120): cells.append(mk("slow", s, P(s=s)))
    cells.append(mk("kind", "sma", P(k="sma")))
    for x in (0.0, 0.1, 0.25, 0.5, 1.0): cells.append(mk("x", x, dict(x=x)))
    for b in ("f", "fm", "fms"): cells.append(mk("breach", b, dict(breach=b)))
    for r in ("f", "m"): cells.append(mk("ref_touch", r, dict(ref=r)))
    for t in ("strict", "loose"): cells.append(mk("trend", t, dict(trend=t)))
    for v in ("c", "f"): cells.append(mk("var", v, dict(var=v)))
    cells.append(mk("triple", "M5/M15+H1", dict(h1=True)))
    for (l, h) in [(5, 15), (5, 30), (10, 30), (15, 60), (5, 60), (60, 0)]:
        cells.append(mk("par", f"{l}/{h}", dict(ltf=l, htf=h)))
    for ttl in (5, 10, 15): cells.append(mk("ttl", ttl, geom_over=dict(ttl=ttl)))
    for N in (5, 10, 15, 30): cells.append(mk("Nstop", N, geom_over=dict(N=N)))
    for K in (3, 5, 7.5, 10, "hh"): cells.append(mk("K", K, geom_over=dict(K=K)))
    for sk, kw in [("e50h", dict(stop="e50h")), ("x15", dict(stop="x", N=15)), ("atr1.0", dict(stop="atr", Katr=1.0)),
                   ("atr1.5", dict(stop="atr", Katr=1.5))]:
        cells.append(mk("stop", sk, geom_over=kw))
    for e in ("cl", "f", "m"): cells.append(mk("entry", e, geom_over=dict(entry=e)))
    cells.append(mk("otim", "otimista", geom_over=dict(otim=True)))
    for f in (5, 6, 7, 8, 9, 10, 11, 12, 13, 15):
        for m in (15, 17, 19, 21, 24, 28, 30, 34, 40):
            if f < m: cells.append(mk("heat", f"{f}/{m}", P(f=f, m=m)))
    for f in (5, 6, 7, 8, 9, 10, 11, 12, 13, 15):
        for m in (15, 17, 19, 21, 24, 28, 30, 34, 40):
            for s in (34, 40, 45, 50, 60, 72, 89, 100, 120):
                if f < m < s: cells.append(mk("joint", f"{f}/{m}/{s}", P(f=f, m=m, s=s)))
    return cells


def all_cells2():
    """Grade de nao-periodos (periodos fixos 9/21/50 EMA): par x ruptura x toque x tendencia x var x stop x alvo."""
    cells = []
    pares = [(5, 15), (5, 30), (10, 30), (15, 60), (5, 60)]
    stops = [("x5", dict(stop="x", N=5)), ("x15", dict(stop="x", N=15)), ("atr1.0", dict(stop="atr", Katr=1.0)),
             ("e50h", dict(stop="e50h"))]
    for (l, h) in pares:
        for b in ("f", "fm", "fms"):
            for x in (0.1, 0.25, 0.5, 1.0):
                for tr in ("strict", "loose"):
                    for v in ("c", "f"):
                        for sn, sg in stops:
                            for K in (3, 5, 7.5):
                                g = dict(K=K); g.update(sg)
                                cells.append(dict(axis="x2", value=f"{l}/{h}|{b}|{x}|{tr}|{v}|{sn}|K{K}",
                                                  cfg={**REF_CFG, **dict(ltf=l, htf=h, breach=b, x=x, trend=tr, var=v)},
                                                  geom={**REF_GEOM, **g}))
    return cells


CELLFN = {"1": all_cells, "2": all_cells2}


_D = None
_cache = {}


def get_data(seed=None):
    return core.Data(core.load_raw(), shuffle_seed=seed)


def init_worker(seed):
    global _D, _cache
    _D = get_data(seed); _cache = {}


def events_for(D, cfg):
    k = cfgkey(cfg)
    if k in _cache: return _cache[k]
    out = {s: core.gen_events(D, cfg, s) for s in (1, -1)}
    _cache[k] = out
    return out


def feats(D, cfg, idx, t):
    a = D.tf(cfg["htf"]).acc(D, cfg["var"], idx, cfg["P"], t)
    a15 = D.tf(15).acc(D, "c", idx, cfg["P"], t)["atr"]
    return a, a15


def run_trades(D, cfg, geom, which="ENC", win=1, tside="same", collect=False, evs=None):
    evs = evs or events_for(D, cfg)
    rows = []; nsig = nfill = ninv = 0
    for s in (1, -1):
        idx = evs[s][which]
        idx = idx[(D.win[idx] == win)] if isinstance(win, int) else idx[np.isin(D.win[idx], win)]
        if len(idx) == 0: continue
        t = s if tside == "same" else -s
        a, a15 = feats(D, cfg, idx, t)
        r = core.sim_events(D, idx, t, a, a15, geom, collect_exc=collect)
        rw = r["rows"]
        rows.append(np.hstack([rw, np.full((len(rw), 1), float(t))])); nsig += r["nsig"]; nfill += r["nfill"]; ninv += r["ninv"]
    rr = np.vstack(rows) if rows else np.zeros((0, 7))
    return rr, nsig, nfill, ninv


def eval_cell(D, cell, win=1, boot=True):
    cfg, geom = cell["cfg"], cell["geom"]
    rr, nsig, nfill, ninv = run_trades(D, cfg, geom, "ENC", win)
    st = core.stats_from(rr)
    nd = len(np.unique(D.day[(D.win == win)]))
    ci = core.boot_days(rr, 400) if (boot and len(rr) > 5) else (np.nan, np.nan)
    evs = events_for(D, cfg)
    pv = []; nu = []
    for s in (1, -1):
        idx = evs[s]["ENC"]; idx = idx[D.win[idx] == win]
        if len(idx):
            r, n = core.pvolta(D, cfg["htf"], cfg["var"], cfg["P"], s, idx)
            pv.append(r); nu.append(n)
    pv = np.concatenate(pv) if pv else np.array([]); nu = np.concatenate(nu) if nu else np.array([])
    nev = len(pv)
    return dict(axis=cell["axis"], value=cell["value"], n=st["n"], nsig=nsig, nfill=nfill, ninv=ninv, nev=nev, ndays=nd,
                win=st["win"], be=st["be"], mean=st["mean"], t=st["t"], payoff=st["payoff"], maxloss=st["maxloss"],
                ci_lo=ci[0], ci_hi=ci[1], per_day=st["n"] / nd,
                pv=(pv == 1).mean() if nev else np.nan, pf=(pv == -1).mean() if nev else np.nan,
                pn=(pv == 0).mean() if nev else np.nan, pnull=np.nanmean(nu) if nev else np.nan)


def task_chunk(args):
    cells, win, boot = args
    return [eval_cell(_D, c, win, boot) for c in cells]


def task_null(args):
    seed, cells, win = args
    global _cache
    D = get_data(seed); _cache = {}
    return seed, [eval_cell(D, c, win, False) for c in cells]


def run_real(win=1, boot=True, nworkers=4, which="1"):
    cells = CELLFN[which]()
    chunks = [cells[i::nworkers * 3] for i in range(nworkers * 3)]
    out = []
    with ProcessPoolExecutor(nworkers, initializer=init_worker, initargs=(None,)) as ex:
        futs = [ex.submit(task_chunk, (ch, win, boot)) for ch in chunks]
        for f in as_completed(futs):
            out += f.result()
            print("chunk ok", len(out), flush=True)
    return out


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "real_desc":
        t0 = time.time()
        res = run_real(1)
        pickle.dump(res, open("res_desc.pkl", "wb"))
        print("done", time.time() - t0, len(res), flush=True)
    elif mode == "real_desc2":
        t0 = time.time()
        res = run_real(1, False, 4, "2")
        pickle.dump(res, open("res_desc2.pkl", "wb"))
        print("done", time.time() - t0, len(res), flush=True)
    elif mode in ("null", "null2"):
        n0, n1 = int(sys.argv[2]), int(sys.argv[3])
        which = "2" if mode == "null2" else "1"
        cells = CELLFN[which](); done = {}
        with ProcessPoolExecutor(4) as ex:
            futs = [ex.submit(task_null, (sd, cells, 1)) for sd in range(n0, n1)]
            for f in as_completed(futs):
                sd, r = f.result(); done[sd] = r
                pickle.dump(done, open(f"null{which}_{n0}_{n1}.pkl", "wb"))
                print("null draw", sd, len(done), flush=True)
