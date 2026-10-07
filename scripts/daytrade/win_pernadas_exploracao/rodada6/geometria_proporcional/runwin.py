"""Roda uma janela (real + sorteios do nulo) em paralelo (max 4 workers). Uso: runwin.py <janela> <n_nulos> [so_nulo_de_celulas.json]
janela: desc (jan-jun) | conf (jul-ago) | set (set). So a janela pedida e' aberta."""
import sys, os, time, pickle
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import geomlib as G, stage as st
HERE = os.path.dirname(os.path.abspath(__file__))
MONTHS = dict(desc=(1, 6), conf=(7, 8), set=(9, 9))
_G = {}

def _init():
    days = G.load_days(); _G["days"] = days; _G["ars"] = G.avg_range_prev(days)

def _win(w):
    a, b = MONTHS[w]
    return [i for i, d in enumerate(_G["days"]) if not d["warm"] and a <= d["month"] <= b]

def unit(args):
    w, seed = args
    t0 = time.time()
    days = _G["days"]; win = _win(w)
    if seed >= 0:
        rng = np.random.default_rng(seed)
        use = list(days)
        for di in win:
            use[di] = G.shuffle_day(days[di], rng)
    else:
        use = days
    built = st.build(use, _G["ars"], win)
    cols, rows = st.grid_stats(built, win)
    if seed < 0:
        pickle.dump((win, built, [days[i]["date"] for i in win]), open(os.path.join(HERE, f"built_{w}.pkl"), "wb"))
    arr = np.array([(r[0], st.FAMS.index(r[1]), r[2], r[3], r[5], r[9], r[10]) for r in rows], np.float32)
    return seed, arr, time.time() - t0

if __name__ == "__main__":
    w = sys.argv[1]; nn = int(sys.argv[2])
    out = {}
    with ProcessPoolExecutor(4, initializer=_init) as ex:
        futs = [ex.submit(unit, (w, s)) for s in [-1] + list(range(1, nn + 1))]
        for f in as_completed(futs):
            seed, arr, dt = f.result()
            out[seed] = arr
            nv = arr[arr[:, 4] >= 40]
            print(f"[{w}] seed {seed} celulas {len(arr)} n>=40 {len(nv)} maxt {np.nanmax(nv[:,6]) if len(nv) else float('nan'):.2f} ({dt:.0f}s)", flush=True)
            pickle.dump(out, open(os.path.join(HERE, f"grid_{w}.pkl"), "wb"))
    print("fim", flush=True)
