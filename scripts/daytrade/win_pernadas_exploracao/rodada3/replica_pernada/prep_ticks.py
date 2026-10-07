"""Pre-passo: agrega ticks por minuto -> flow_proxy.pkl (WIN@D continuo, regra do tick: o cache nao traz lado) e
flow_real.pkl (WINV26, flags 32/64 reais; so liquido a partir de ~12/08). 3 processos no max."""
import glob, os, pickle, sys
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
BASE = "C:/Users/Jeffe/Documents/study/meta/data/cache_win_ticks/"
HERE = os.path.dirname(os.path.abspath(__file__))

def um(args):
    path, modo = args
    df = pd.read_pickle(path)
    fl = df["flags"].to_numpy().astype(np.int64); vol = df["volume"].to_numpy().astype(float)
    m = ((fl & 8) > 0) & (vol > 0)
    t = df["time_msc"].to_numpy()[m]; v = vol[m]; f = fl[m]; p = df["last"].to_numpy()[m]
    del df
    mod = ((t // 1000) % 86400) // 60          # time_msc = BRT em epoch ms (sem converter fuso)
    if modo == "real":
        buy = ((f & 32) > 0) & ((f & 64) == 0); sell = ((f & 64) > 0) & ((f & 32) == 0)
    else:
        dp = np.sign(np.diff(p, prepend=p[0]))
        tr = pd.Series(dp).replace(0, np.nan).ffill().fillna(0).to_numpy()
        buy = tr > 0; sell = tr < 0
    a = np.zeros((1440, 3))
    np.add.at(a[:, 0], mod[buy], v[buy]); np.add.at(a[:, 1], mod[sell], v[sell]); np.add.at(a[:, 2], mod, v)
    return os.path.basename(path)[:10], modo, a, int(mod.min()) if len(mod) else -1

if __name__ == "__main__":
    jobs = [(f, "proxy") for f in sorted(glob.glob(BASE + "WIN@D/2026-*.pkl"))] + \
           [(f, "real") for f in sorted(glob.glob(BASE + "WINV26/2026-*.pkl")) if os.path.basename(f)[:10] >= "2026-08-12"]
    res = {"proxy": {}, "real": {}}
    with ProcessPoolExecutor(3) as ex:
        futs = [ex.submit(um, j) for j in jobs]
        for fu in as_completed(futs):
            d, modo, a, first = fu.result(); res[modo][d] = a
            print(modo, d, "primeiro %02d:%02d" % (first // 60, first % 60), flush=True)
    pickle.dump(res["proxy"], open(os.path.join(HERE, "flow_proxy.pkl"), "wb"))
    pickle.dump(res["real"], open(os.path.join(HERE, "flow_real.pkl"), "wb"))
