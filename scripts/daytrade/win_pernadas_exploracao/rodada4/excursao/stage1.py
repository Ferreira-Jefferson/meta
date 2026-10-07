import pickle, numpy as np, pandas as pd, exc, agg, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
WIN = {"desc": (1, 6), "conf": (7, 8), "set": (9, 9)}
def null_task(a):
    w, sim, vthr = a
    m0, m1 = WIN[w]
    _, _, df, R = exc.run_task((m0, m1, sim, 1))
    return w, sim, agg.agg(df, R, vthr), agg.quant_tab(df, vthr)
if __name__ == "__main__":
    NS = int(sys.argv[1])
    real = pickle.load(open("real_meses.pkl", "rb"))
    def win(m0, m1):
        df = pd.concat([real[m][0].assign(mes=m) for m in range(m0, m1 + 1)], ignore_index=True)
        R = np.concatenate([real[m][1] for m in range(m0, m1 + 1)])
        # day id unica
        df["dk"] = df.date
        return df, R
    wd = {k: win(*v) for k, v in WIN.items()}
    vthr = agg.speed_thr(wd["desc"][0]); print("vthr", vthr, flush=True)
    realagg = {k: (agg.agg(df, R, vthr), agg.quant_tab(df, vthr)) for k, (df, R) in wd.items()}
    pickle.dump((vthr, realagg), open("real_agg.pkl", "wb"))
    nul = {k: [] for k in WIN}; nq = {k: [] for k in WIN}
    tasks = [(w, s, vthr) for s in range(NS) for w in WIN]
    with ProcessPoolExecutor(4) as pool:
        fs = [pool.submit(null_task, t) for t in tasks]
        for f in as_completed(fs):
            w, s, A, Q = f.result(); nul[w].append(A.assign(sim=s)); nq[w].append(Q.assign(sim=s)); print("null", w, s, flush=True)
    pickle.dump({k: (pd.concat(nul[k]), pd.concat(nq[k])) for k in WIN}, open("null_agg.pkl", "wb"))
