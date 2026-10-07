import pickle, numpy as np, pandas as pd
FEATS, CONDS, OUT, cut, res = pickle.load(open("res.pkl", "rb"))
t = pd.read_pickle("real.pkl"); t["mes"] = t.dia.str[5:7].astype(int)
t["u30"] = np.where(t._r30.notna(), (t._r30 > 0) * 1.0, np.nan); t["u60"] = np.where(t._r60.notna(), (t._r60 > 0) * 1.0, np.nan)
t["h250"] = t._h250; t["h750"] = t._h750
rng = np.random.default_rng(1)
def sel(f, c="all"):
    x = t[f].values; B = t.bucket.values
    lo = np.array([cut[(f, c, b)][0] for b in range(3)])[B]; hi = np.array([cut[(f, c, b)][1] for b in range(3)])[B]
    return (x >= hi) & (x > lo), (x <= lo) & (x < hi)
for f in ["net_1m_10", "sal_1m_10", "cpos_1m_10"]:
    top, bot = sel(f); print("==", f)
    for o in ["h250", "u30", "u60", "h750"]:
        out = []
        for per, m in (("disc", t.mes <= 6), ("conf", (t.mes >= 7) & (t.mes <= 8)), ("set", t.mes == 9)):
            a = t.loc[top & m.values, o].dropna(); b = t.loc[bot & m.values, o].dropna()
            out.append(f"{per} {a.mean():.3f}/{b.mean():.3f} D={a.mean()-b.mean():+.3f} n={len(a)}/{len(b)}")
        print(o, " | ".join(out))
    d = t[(top | bot)].copy(); d["s"] = np.where(top[(top | bot)], 1, -1)
    print("mes D h250:", {m: round(g[g.s == 1].h250.mean() - g[g.s == -1].h250.mean(), 3) for m, g in d.groupby("mes")})
    print("faixa D h250:", {b: round(g[g.s == 1].h250.mean() - g[g.s == -1].h250.mean(), 3) for b, g in d.groupby("bucket")})
    r = d.assign(sr=d.s * d._r60).groupby("mes")["sr"].mean().round(1).to_dict(); print("pts r60 a favor (long top, short bot) por mes:", r)
    # bootstrap por dia jan-ago
    dd = d[d.mes <= 8]; days = dd.dia.unique(); bs = []
    g = {k: v for k, v in dd.groupby("dia")}
    for _ in range(1000):
        pick = rng.choice(days, len(days)); x = pd.concat([g[k] for k in pick])
        bs.append(x[x.s == 1].h250.mean() - x[x.s == -1].h250.mean())
    print("D h250 jan-ago IC95 dias:", np.round(np.nanpercentile(bs, [2.5, 50, 97.5]), 3))
    # simples: sinal do feature
    x = t[f].values
    for o in ["h250", "u60"]:
        print("sinal", o, "jan-ago D=", round(t.loc[(x > 0) & (t.mes <= 8), o].mean() - t.loc[(x < 0) & (t.mes <= 8), o].mean(), 3))
# correlacao entre TFs de contagem de cores
pf = t[t.mes <= 8]
print(pf[["frac_1m_30", "frac_5m_6", "frac_1m_60", "frac_15m_4", "frac_5m_12"]].corr().round(2))
print(pf[["corpo_1m_30", "corpo_5m_6", "corpo_1m_60", "corpo_15m_4"]].corr().round(2))
# divergencia: M1 frac_60>0.1 e M15 frac_4 <0 etc
for nm, a, b in (("x_1m60_15m4", "frac_1m_60", "frac_15m_4"),):
    m1 = pf[a]; m2 = pf[b]
    for lab, msk in (("M1 alta/M15 baixa", (m1 > 0.05) & (m2 < 0)), ("M1 baixa/M15 alta", (m1 < -0.05) & (m2 > 0)), ("concorda alta", (m1 > .05) & (m2 > 0)), ("concorda baixa", (m1 < -.05) & (m2 < 0))):
        print(lab, int(msk.sum()), "P(u60)=", round(pf.loc[msk, "_r60"].gt(0).mean(), 3) if False else round((pf.loc[msk, "_r60"].dropna() > 0).mean(), 3), "P(h250 up)=", round(pf.loc[msk, "_h250"].mean(), 3))
print("base P(up60)", round((pf._r60.dropna() > 0).mean(), 3), "P(h250)", round(pf._h250.mean(), 3))
