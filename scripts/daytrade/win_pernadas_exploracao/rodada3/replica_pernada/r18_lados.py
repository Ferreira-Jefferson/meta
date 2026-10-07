import pickle, numpy as np, pandas as pd
exec(open("agg2.py").read().split("# ---------------- R17")[0])
exec("def strata(A, mn):\n    hb = np.where(mn < 630, 0, np.where(mn < 780, 1, 2)); ab = np.where(A < 1250, 0, np.where(A < 2000, 1, 2))\n    return hb * 3 + ab")
src = open("agg2.py").read(); s = src.index("def auc_est"); e = src.index("AUC = {}")
exec(src[s:e])
for X in (250, 500):
    for g in ("jan-ago", "09"):
        idx = np.where(GR[g])[0]; rows = []
        for i in idx:
            ev = res[i]["real"][1]; m = (ev[:, 0] == X) & ~np.isnan(ev[:, 6])
            for r in ev[m]: rows.append((r[1], r[2], r[6], r[18], r[17]))
        T = np.array(rows)
        for d, nm in ((1, "topo"), (-1, "fundo")):
            t = T[T[:, 0] == d]
            a, p, n = auc_est(t[:, 4], t[:, 2], strata(t[:, 1], t[:, 3]), perms=200, rng=rng)
            print("R18 lado", X, g, nm, "AUC %.3f p %.2f n %d" % (a, p, n), flush=True)
print(T[:5], np.nanstd(T[:,4]))
