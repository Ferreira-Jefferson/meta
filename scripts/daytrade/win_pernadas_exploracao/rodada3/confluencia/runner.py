import sys, pickle, time, numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import lib

def job(mode, seed, cfg):
    df = lib.load(cfg["load_end"])
    rng = np.random.default_rng(seed)
    if mode == "shuf":
        df = lib.shuffle_blocks(df, rng)
    L = lib.build_levels(df)
    if cfg.get("only"):
        L = {k: v for k, v in L.items() if k in cfg["only"]}
    res, plat, drift = lib.fwd_outcomes(df)
    conds = {D: lib.event_conditions(df, D) for D in cfg["Ds"]}
    out = lib.collect(df, L, res, plat, drift, conds, cfg["Ns"], cfg["split"], cfg["win"],
                      shift_rng=rng if mode == "shift" else None)
    return mode, seed, out

def run_all(cfg, nshift, nshuf, path):
    jobs = [("obs", 0)] + [("shift", 1000 + i) for i in range(nshift)] + [("shuf", 2000 + i) for i in range(nshuf)]
    results = {"obs": None, "shift": [], "shuf": []}
    t0 = time.time()
    with ProcessPoolExecutor(4) as ex:
        futs = [ex.submit(job, m, s, cfg) for m, s in jobs]
        for f in as_completed(futs):
            m, s, out = f.result()
            if m == "obs": results["obs"] = out
            else: results[m].append(out)
            print(f"{m} {s} pronto {time.time()-t0:.0f}s", flush=True)
    pickle.dump((cfg, results), open(path, "wb"))
