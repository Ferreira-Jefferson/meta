import os, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
res = pickle.load(open(os.path.join(HERE, "res_dias.pkl"), "rb"))
rng = np.random.default_rng(7)
dias = [r["date"] for r in res]; meses = np.array([int(d[5:7]) for d in dias])
GR = {f"{m:02d}": meses == m for m in range(1, 10)}; GR["jan-ago"] = meses <= 8
# ---------------- R17
def legs_group(idx):
    out = []
    for i in idx:
        L = res[i]["real"][0]
        L = L[(L[:, 7] == 1) & (L[:, 11] == 0)]   # fechadas, sem a 1a do dia
        out.append(L)
    return out
def r17(idx):
    Ls = legs_group(idx); L = np.vstack(Ls)
    ev = np.vstack([res[i]["real"][1] for i in idx]); ev = ev[(ev[:, 0] == 250) & ~np.isnan(ev[:, 6])]
    u, d = L[L[:, 0] == 1], L[L[:, 0] == -1]
    f = lambda a, c: np.median(a[:, c])
    return dict(n=(len(u), len(d)), tam=(f(u, 1), f(d, 1)), vel=(f(u, 3), f(d, 3)), corr=(f(u, 4), f(d, 4)), ncorr=(u[:, 5].mean(), d[:, 5].mean()),
                vira=(ev[ev[:, 1] == 1][:, 6].mean(), ev[ev[:, 1] == -1][:, 6].mean()), nev=((ev[:, 1] == 1).sum(), (ev[:, 1] == -1).sum()))
R17 = {}
for g, m in GR.items():
    idx = np.where(m)[0]; r = r17(idx)
    # bootstrap de dias da razao alta/baixa
    rs = {k: [] for k in ("tam", "vel", "corr", "vira")}
    for b in range(500):
        s = r17(rng.choice(idx, len(idx)))
        for k in rs: rs[k].append(s[k][0] / s[k][1] if k != "vira" else s[k][0] - s[k][1])
    r["ic"] = {k: (np.percentile(v, 2.5), np.percentile(v, 97.5)) for k, v in rs.items()}
    R17[g] = r
    print("R17", g, {k: (round(v[0], 2), round(v[1], 2)) for k, v in r.items() if k in ("tam", "vel", "corr", "ncorr", "vira")}, "IC razao", {k: (round(a, 2), round(b, 2)) for k, (a, b) in r["ic"].items()}, r["n"], r["nev"], flush=True)
pickle.dump(R17, open(os.path.join(HERE, "r17.pkl"), "wb"))
# ---------------- AUC (R15, R18, R19)
FEAT = ["ema_cruz", "ema_dist", "rsi", "rsi_div", "vwap_dist", "vol_ult", "vol_pre", "corpo", "pavio", "vel", "fluxo", "fluxo_real"]
def tabela_eventos(idx, X):
    rows = []
    for i in idx:
        ev = res[i]["real"][1]
        m = (ev[:, 0] == X) & ~np.isnan(ev[:, 6])
        e = ev[m]
        for r in e:
            rows.append([i, r[2], r[6], r[18]] + list(r[7:18]) + [r[19]])
    return np.array(rows).reshape(-1, 4 + len(FEAT))
def strata(A, mn):
    hb = np.where(mn < 630, 0, np.where(mn < 780, 1, 2)); ab = np.where(A < 1250, 0, np.where(A < 2000, 1, 2))
    return hb * 3 + ab
def auc_est(x, y, st, perms=0, rng=None):
    ok = ~np.isnan(x); x, y, st = x[ok], y[ok], st[ok]
    if y.sum() < 5 or (1 - y).sum() < 5: return np.nan, np.nan, len(x)
    # ranks por estrato
    groups = []
    for s in np.unique(st):
        m = st == s; xs, ys = x[m], y[m]
        n1 = ys.sum(); n0 = len(ys) - n1
        if n1 == 0 or n0 == 0: continue
        r = pd.Series(xs).rank().to_numpy()
        groups.append((r, ys, n1, n0))
    def calc(lab):
        U = 0; P = 0
        for (r, ys, n1, n0), yy in zip(groups, lab):
            U += r[yy == 1].sum() - n1 * (n1 + 1) / 2; P += n1 * n0
        return U / P
    a = calc([g[1] for g in groups])
    p = np.nan
    if perms:
        null = np.array([calc([rng.permutation(g[1]) for g in groups]) for _ in range(perms)])
        p = 2 * min((null >= a).mean(), (null <= a).mean())
    return a, p, len(x)
AUC = {}
for X in (250, 500):
    for g, m in GR.items():
        idx = np.where(m)[0]; T = tabela_eventos(idx, X)
        st = strata(T[:, 1], T[:, 3]); y = T[:, 2]
        for k, nm in enumerate(FEAT):
            a, p, n = auc_est(T[:, 4 + k], y, st, perms=200 if g in ("jan-ago", "09") else 0, rng=rng)
            AUC[(X, g, nm)] = (a, p, n)
    # bootstrap de dias para jan-ago
    idx = np.where(GR["jan-ago"])[0]
    for k, nm in enumerate(FEAT):
        bs = []
        for b in range(150):
            sel = rng.choice(idx, len(idx)); T = tabela_eventos(sel, X)
            bs.append(auc_est(T[:, 4 + k], T[:, 2], strata(T[:, 1], T[:, 3]))[0])
        a, p, n = AUC[(X, "jan-ago", nm)]
        AUC[(X, "jan-ago", nm)] = (a, p, n, np.nanpercentile(bs, 2.5), np.nanpercentile(bs, 97.5))
        print("AUC X", X, nm, "jan-ago a=%.3f p=%.3f n=%d IC[%.3f;%.3f]" % (a, p, n, *AUC[(X, "jan-ago", nm)][3:]), "| set a=%.3f p=%.3f" % AUC[(X, "09", nm)][:2], flush=True)
pickle.dump(AUC, open(os.path.join(HERE, "auc.pkl"), "wb"))
# R19 extra: P(vira | dist VWAP > 1.5 ATR) e medianas
R19 = {}
for X in (250, 500):
    for g, m in GR.items():
        idx = np.where(m)[0]; T = tabela_eventos(idx, X); v = T[:, 4 + FEAT.index("vwap_dist")]; y = T[:, 2]
        ok = ~np.isnan(v)
        hi = ok & (v > 1.5); lo = ok & (v <= 1.5)
        R19[(X, g)] = dict(p_hi=y[hi].mean() if hi.sum() else np.nan, n_hi=int(hi.sum()), p_lo=y[lo].mean(), n_lo=int(lo.sum()),
                           med_vira=np.median(v[ok & (y == 1)]), med_segue=np.median(v[ok & (y == 0)]))
        print("R19", X, g, {k: round(float(x), 3) for k, x in R19[(X, g)].items()})
pickle.dump(R19, open(os.path.join(HERE, "r19.pkl"), "wb"))
