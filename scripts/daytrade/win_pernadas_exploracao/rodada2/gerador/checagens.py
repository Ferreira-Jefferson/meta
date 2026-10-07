import pandas as pd, numpy as np
rng = np.random.default_rng(7)
B = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/"


def load(f, lo, hi):
    out = []
    for c in pd.read_csv(B + f, sep="\t", chunksize=200000):
        c.columns = [x.strip("<>").lower() for x in c.columns]
        c = c[(c.date >= lo) & (c.date <= hi)]
        if len(c):
            out.append(c)
    d = pd.concat(out)
    d["ts"] = pd.to_datetime(d.date + " " + d.time, format="%Y.%m.%d %H:%M:%S")
    return d.set_index("ts")


w = load("WINV26_M1_202604151210_202610011824.csv", "2026.08.20", "2026.09.30")
d = load("WDO@D_M1_202109290900_202609291020.csv", "2026.09.01", "2026.09.30")
w["day"] = w.index.date
d["day"] = d.index.date
w["hm"] = w.index.hour * 60 + w.index.minute
days = sorted(set(w.day))
sep = [x for x in days if x.month == 9]
print("pregoes set", len(sep))
ncmp = 0


def spear(a, b):
    return pd.Series(a).rank().corr(pd.Series(b).rank())


# ---------- A
print("\n== A: corte 10:30 vs outros cortes (pre=84min, pos=30min)")


def cutstat(cut):
    pre = []; pos = []; rr = []
    for dy in sep:
        x = w[w.day == dy].set_index("hm")
        try:
            p0 = x.open.loc[cut - 84]; p1 = x.close.loc[cut - 1]; q1 = x.close.loc[cut + 29]
            rg = x.high - x.low
            ra = rg.loc[cut:cut + 14].mean(); rb = rg.loc[cut - 15:cut - 1].mean()
        except KeyError:
            continue
        pre.append(p1 - p0); pos.append(q1 - p1); rr.append(ra / rb)
    pre = np.array(pre); pos = np.array(pos)
    return len(pre), np.mean(np.sign(pre) == np.sign(pos)), spear(pre, pos), np.median(rr)


rows = [(c,) + cutstat(c) for c in range(9 * 60 + 90, 16 * 60 + 1, 5)]
t = pd.DataFrame(rows, columns=["cut", "n", "concord", "rho", "ratio_range"]).set_index("cut")
r = t.loc[630]
print("10:30:", r.to_dict())
print("outros cortes: concord mediana %.2f [p5 %.2f p95 %.2f]; rho med %.2f [%.2f %.2f]; ratio_range med %.2f [%.2f %.2f]" % (
    t.concord.median(), *t.concord.quantile([.05, .95]), t.rho.median(), *t.rho.quantile([.05, .95]),
    t.ratio_range.median(), *t.ratio_range.quantile([.05, .95])))
print("cortes com ratio_range maior que 10:30:", int((t.ratio_range > r.ratio_range).sum()), "de", len(t))
print("cortes com concord >= 10:30:", int((t.concord >= r.concord).sum()), "de", len(t))
ncmp += 3

# ---------- B
print("\n== B: razao de variancia e saltos")
w["r"] = w.close.diff()
w.loc[w.groupby("day").head(1).index, "r"] = np.nan
s = w[w.index.month == 9].copy()


def vr(df, k):
    v1 = df.r.var()
    g = df.groupby("day")
    rk = (g.close.shift(0) - g.close.shift(k)).dropna()
    return rk.var() / (k * v1)


for h0, h1 in [(9, 10), (10, 12), (12, 15), (15, 18)]:
    sub = s[(s.index.hour >= h0) & (s.index.hour < h1)]
    v5, v15 = vr(sub, 5), vr(sub, 15)
    nul = []
    for _ in range(100):
        z = sub.copy()
        z["r"] = z.groupby("day").r.transform(lambda a: rng.permutation(a.values))
        z["close"] = z.groupby("day").r.cumsum()
        nul.append(vr(z, 5))
    print(f"{h0}-{h1}h VR5={v5:.3f} VR15={v15:.3f} nulo VR5 {np.mean(nul):.3f} [{np.percentile(nul,2.5):.3f};{np.percentile(nul,97.5):.3f}]")
ncmp += 8
s["ar"] = s.r.abs()
med = s.groupby(s.index.hour).ar.transform("median")
s["thr"] = s.ar / med
for k in (3, 6):
    ev = s[(s.thr >= k) & (s.index.hour >= 10)]
    cont = []; dd = []
    for ts, row in ev.iterrows():
        x = s[(s.day == row.day) & (s.index > ts)].head(5)
        if len(x) < 5:
            continue
        cont.append(np.sign(row.r) * (x.close.iloc[-1] - row.close)); dd.append(row.day)
    cont = np.array(cont); dd = np.array(dd)
    ud = np.unique(dd); bm = []
    for _ in range(1000):
        pick = rng.choice(ud, len(ud))
        bm.append(np.mean(np.concatenate([cont[dd == u] for u in pick])))
    print(f"salto >={k}x mediana da hora: n={len(cont)}, dias={len(ud)}, continuacao 5min media {cont.mean():.1f} pts, mediana {np.median(cont):.1f}, %cont {np.mean(cont>0)*100:.0f}, IC dias [{np.percentile(bm,2.5):.1f};{np.percentile(bm,97.5):.1f}], salto medio {ev.ar.mean():.0f}")
ncmp += 2

# ---------- C
print("\n== C: vol em aglomerados (bins 15min, sazonalidade removida) + WDO lider de vol")


def binrange(df):
    df = df.copy(); df["bin"] = df.index.floor("15min")
    g = df.groupby("bin").agg(h=("high", "max"), l=("low", "min")); g["rg"] = g.h - g.l
    return g.rg


def norm(sr):
    df = sr.to_frame("rg"); df["day"] = df.index.date; df["tod"] = df.index.hour * 60 + df.index.minute
    df["lr"] = np.log(df.rg.replace(0, np.nan)); df["z"] = df.lr - df.groupby("tod").lr.transform("mean")
    return df


nw = norm(binrange(s)); nd = norm(binrange(d[d.index.month == 9]))


def lagcorr(nw, nd):
    m = nw.join(nd[["z"]], rsuffix="_d", how="inner").dropna()
    m = m[(m.tod >= 540) & (m.tod < 1050)].sort_index()
    m["z_next"] = m.groupby("day").z.shift(-1); m["zd"] = m.z_d
    q = m.dropna()
    own = q.z.corr(q.z_next); wd = q.zd.corr(q.z_next)
    a = np.c_[np.ones(len(q)), q.z]
    rn = q.z_next - a @ np.linalg.lstsq(a, q.z_next, rcond=None)[0]
    rd = q.zd - a @ np.linalg.lstsq(a, q.zd, rcond=None)[0]
    return len(q), own, wd, rn.corr(rd)


obs = lagcorr(nw, nd)
nul = []
for _ in range(300):
    a = nw.copy(); b = nd.copy()
    for X in (a, b):
        X["z"] = X.groupby("tod").z.transform(lambda v: rng.permutation(v.values))
    nul.append(lagcorr(a, b)[1:])
nul = np.array(nul)
print(f"n bins={obs[0]}: corr(z_t,z_t+1) WIN={obs[1]:.3f} [nulo {np.percentile(nul[:,0],2.5):.3f};{np.percentile(nul[:,0],97.5):.3f}]; corr(WDO_t,WIN_t+1)={obs[2]:.3f} [nulo {np.percentile(nul[:,1],2.5):.3f};{np.percentile(nul[:,1],97.5):.3f}]; parcial={obs[3]:.3f} [nulo {np.percentile(nul[:,2],2.5):.3f};{np.percentile(nul[:,2],97.5):.3f}]")
dr = s.groupby("day").agg(h=("high", "max"), l=("low", "min")); dr["rg"] = dr.h - dr.l
print("range diario lag1 rho:", round(spear(dr.rg.values[:-1], dr.rg.values[1:]), 3), "n", len(dr) - 1)
ncmp += 4

# ---------- D
print("\n== D: eventos de relogio por minuto da hora")
s["rg"] = s.high - s.low
s["rel"] = s.rg / s.groupby([s.day, s.index.hour]).rg.transform("mean")
s["mm"] = s.index.minute
x = s[(s.index.hour >= 10) & (s.index.hour <= 17) & ~((s.hm >= 630) & (s.hm <= 632))]
prof = x.groupby("mm").rel.mean()
print("rel range medio :00 %.2f  :30 %.2f  :01 %.2f  :31 %.2f ; demais %.2f" % (
    prof[0], prof[30], prof[1], prof[31], prof.drop([0, 30, 1, 31]).mean()))
mx = []
for _ in range(200):
    p = x.groupby([x.day, x.index.hour]).rel.transform(lambda v: rng.permutation(v.values))
    mx.append(p.groupby(x.mm).mean().max())
p95 = np.percentile(mx, 95)
print("maior minuto %.2f (mm=%d); max do nulo p95 %.2f; minutos acima: %s" % (prof.max(), prof.idxmax(), p95, list(prof[prof > p95].index)))
print("top5:", prof.sort_values(ascending=False).head(5).round(2).to_dict())
for hh in range(10, 18):
    xx = x[x.index.hour == hh]
    print(hh, "h :00 rel %.2f; :30 rel %.2f" % (xx[xx.mm == 0].rel.mean(), xx[xx.mm == 30].rel.mean()), end=" | ")
print()
ncmp += 61

# ---------- E
print("\n== E: manha->tarde e gap x extremos")
rows = []
allr = w.groupby("day").agg(h=("high", "max"), l=("low", "min")); allr["rg"] = allr.h - allr.l
for i, dy in enumerate(days):
    x = w[w.day == dy]
    if dy.month == 9 and i > 0:
        pc = w[w.day == days[i - 1]].close.iloc[-1]; gap = x.open.iloc[0] - pc
        atr = allr.rg.iloc[max(0, i - 5):i].mean()
        hl = x.high.max() - x.low.min(); h1030 = x[x.hm < 630]
        fr = (h1030.high.max() - h1030.low.min()) / hl
        mt = x[x.hm < 630].close.iloc[-1] - x.open.iloc[0]
        st = x[x.hm >= 630].close.iloc[-1] - x[x.hm < 630].close.iloc[-1]
        tm = x.high.idxmax().hour * 60 + x.high.idxmax().minute
        tl = x.low.idxmin().hour * 60 + x.low.idxmin().minute
        rows.append(dict(day=dy, gap=gap, gapatr=abs(gap) / atr, fr=fr, mt=mt, st=st, hl=hl / atr, ext_late=max(tm, tl)))
e = pd.DataFrame(rows)
print("n", len(e))


def permp(a, b, n=5000):
    o = spear(a, b); c = 0
    for _ in range(n):
        if abs(spear(a, rng.permutation(b))) >= abs(o):
            c += 1
    return o, (c + 1) / (n + 1)


for nm, a, b in [("|gap|/ATR x fracao do range feita ate 10:30", e.gapatr, e.fr),
                 ("|gap|/ATR x range do dia/ATR", e.gapatr, e.hl),
                 ("|gap|/ATR x horario do ultimo extremo", e.gapatr, e.ext_late),
                 ("ret manha (09-10:30) x ret resto do dia", e.mt, e.st),
                 ("gap com sinal x ret resto do dia", e.gap, e.st),
                 ("|ret manha| x |ret resto|", e.mt.abs(), e.st.abs())]:
    o, p = permp(a.values, b.values)
    print(f"{nm}: rho={o:.2f} p_perm={p:.3f}")
print("manha e resto com sinal oposto:", int((np.sign(e.mt) != np.sign(e.st)).sum()), "de", len(e))
big = e.gapatr >= e.gapatr.median()
print("gap/ATR alto: fracao ate 10:30 med %.2f vs baixo %.2f; range/ATR %.2f vs %.2f; ultimo extremo %.0f vs %.0f (min do dia)" % (
    e.fr[big].median(), e.fr[~big].median(), e.hl[big].median(), e.hl[~big].median(), e.ext_late[big].median(), e.ext_late[~big].median()))
ncmp += 7
print("\nTOTAL comparacoes aprox:", ncmp)
