import numpy as np, pandas as pd, pickle
real = pd.read_pickle("real.pkl"); sims = pickle.load(open("sims.pkl", "rb"))
for t in [real] + list(sims.values()):
    t["mes"] = t.dia.str[5:7].astype(int)
    t["u30"] = np.where(t._r30.notna(), (t._r30 > 0).astype(float), np.nan)
    t["u60"] = np.where(t._r60.notna(), (t._r60 > 0).astype(float), np.nan)
    t["h250"] = t._h250; t["h750"] = t._h750
OUT = ["u30", "u60", "h250", "h750"]
FEATS = [c for c in real.columns if not c.startswith("_") and c not in ("mn", "bucket", "dia", "mes") + tuple(OUT)]
CONDS = ["all", "lat", "non"]
def cmask(t, c): return np.ones(len(t), bool) if c == "all" else (t._lat == 1).values if c == "lat" else (t._lat == 0).values
DISC = lambda t: t[t.mes <= 6]; CONF = lambda t: t[(t.mes >= 7) & (t.mes <= 8)]; SET = lambda t: t[t.mes == 9]
# cortes congelados (q20/q80 por feature x cond x faixa horaria) da descoberta real
cut = {}
d0 = DISC(real)
for f in FEATS:
    for c in CONDS:
        m = cmask(d0, c)
        for b in range(3):
            x = d0[f].values[m & (d0.bucket.values == b)]; x = x[~np.isnan(x)]
            cut[(f, c, b)] = (np.quantile(x, .2), np.quantile(x, .8)) if len(x) > 50 else (np.nan, np.nan)
def stat(t, ret_n=False):
    R = np.full((len(FEATS), 3, len(OUT)), np.nan); N = np.zeros((len(FEATS), 3, 2)); PT = np.full((len(FEATS), 3, len(OUT), 2), np.nan)
    B = t.bucket.values; Y = np.stack([t[o].values for o in OUT], 1)
    for i, f in enumerate(FEATS):
        x = t[f].values
        for j, c in enumerate(CONDS):
            m = cmask(t, c) & ~np.isnan(x)
            if f.startswith("p_"): top = m & (x > 0); bot = m & (x < 0)
            else:
                lo = np.array([cut[(f, c, b)][0] for b in range(3)])[B]; hi = np.array([cut[(f, c, b)][1] for b in range(3)])[B]
                top = m & (x >= hi) & (x > lo); bot = m & (x <= lo) & (x < hi)
            N[i, j] = (top.sum(), bot.sum())
            for k in range(len(OUT)):
                yt, yb = Y[top, k], Y[bot, k]; yt = yt[~np.isnan(yt)]; yb = yb[~np.isnan(yb)]
                if len(yt) >= 30 and len(yb) >= 30:
                    PT[i, j, k] = (yt.mean(), yb.mean()); R[i, j, k] = yt.mean() - yb.mean()
    return R, N, PT
def rows(per):
    r, n, pt = stat(per(real)); nul = np.stack([stat(per(s))[0] for s in sims.values()])
    return r, n, pt, nul
res = {}
for nm, per in (("disc", DISC), ("conf", CONF), ("set", SET)):
    res[nm] = rows(per); print(nm, flush=True)
pickle.dump((FEATS, CONDS, OUT, cut, res), open("res.pkl", "wb"))
# tabela de descoberta
r, n, pt, nul = res["disc"]; mu = np.nanmean(nul, 0); sd = np.nanstd(nul, 0)
z = (r - mu) / sd
rec = []
for i, f in enumerate(FEATS):
    for j, c in enumerate(CONDS):
        for k, o in enumerate(OUT):
            if not np.isnan(z[i, j, k]):
                p = (np.sum(np.abs(nul[:, i, j, k] - mu[i, j, k]) >= abs(r[i, j, k] - mu[i, j, k])) + 1) / (len(nul) + 1)
                rec.append((f, c, o, int(n[i, j, 0]), int(n[i, j, 1]), pt[i, j, k, 0], pt[i, j, k, 1], r[i, j, k], mu[i, j, k], sd[i, j, k], z[i, j, k], p))
df = pd.DataFrame(rec, columns="feat cond out ntop nbot Ptop Pbot D nulD nulSD z p".split())
df.to_csv("descoberta.csv", index=False)
print("testes", len(df), "|z|>2:", (df.z.abs() > 2).sum(), ">3:", (df.z.abs() > 3).sum(), "esperado>2", .0455 * len(df))
print(df.reindex(df.z.abs().sort_values(ascending=False).index).head(40).round(3).to_string())
