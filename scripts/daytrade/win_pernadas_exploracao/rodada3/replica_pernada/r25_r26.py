import os, pickle
import numpy as np, pandas as pd
from core import *
HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(11)
w = ler(WIN); wd = ler(WDO)
def spearman(a, b):
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    return np.corrcoef(ra, rb)[0, 1]
# ------------------------------ R25
OUT = {"R25": {}, "R26": {}}
for tf, rule in (("M5", "5min"), ("M15", "15min")):
    rows = []   # mes, dia, tamanho, vrel
    r = w.resample(rule, label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"}).dropna()
    r["dia"] = r.index.normalize(); r["mes"] = r.index.month; r["slot"] = r.index.hour * 60 + r.index.minute
    r["vrel"] = r["vol"] / r.groupby(["mes", "slot"])["vol"].transform("mean")
    for dia, g in r.groupby("dia"):
        if len(g) < 20: continue
        p = caminho(g["open"].to_numpy(), g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy(), np.arange(len(g)))
        legs, _ = zigzag_eventos(p)
        vr = g["vrel"].to_numpy()
        for a, b, d, fe in legs:
            if not fe: continue
            c0 = a // 4 - 1
            if c0 < 0: continue
            rows.append((g["mes"].iloc[0], str(dia.date()), abs(p[b] - p[a]), vr[c0]))
    df = pd.DataFrame(rows, columns=["mes", "dia", "tam", "vrel"])
    for g in [f"{m:02d}" for m in range(1, 10)] + ["jan-ago"]:
        d = df[df.mes <= 8] if g == "jan-ago" else df[df.mes == int(g)]
        rho = spearman(d["tam"], d["vrel"])
        nul = np.array([spearman(rng.permutation(d["tam"].to_numpy()), d["vrel"]) for _ in range(300)])
        ds = d["dia"].unique(); gb = {k: v for k, v in d.groupby("dia")}
        bs = []
        if g == "jan-ago":
            for _ in range(300):
                sel = rng.choice(ds, len(ds)); x = pd.concat([gb[k] for k in sel]); bs.append(spearman(x["tam"], x["vrel"]))
        OUT["R25"][(tf, g)] = dict(rho=rho, n=len(d), nulo_sd=nul.std(), ic=(np.percentile(bs, 2.5), np.percentile(bs, 97.5)) if bs else None)
        print("R25", tf, g, "rho %.3f n %d nulo sd %.3f" % (rho, len(d), nul.std()), OUT["R25"][(tf, g)]["ic"], flush=True)
# ------------------------------ R26 lead-lag
j = pd.concat([w["close"].rename("w"), wd["close"].rename("d")], axis=1, join="inner")
j["dia"] = j.index.normalize(); j["mes"] = j.index.month
LAGS = [-3, -2, -1, 0, 1, 2, 3]
def corr_lags(g):
    # retornos M1 dentro do dia; lag k>0: WDO (t-k) vs WIN (t) => WDO lidera
    xs = {k: ([], []) for k in LAGS}
    for dia, x in g.groupby("dia"):
        rw = x["w"].diff().to_numpy()[1:]; rd = x["d"].diff().to_numpy()[1:]
        for k in LAGS:
            if k >= 0: a, b = rw[k:], rd[:len(rd) - k]
            else: a, b = rw[:k], rd[-k:]
            xs[k][0].append(a); xs[k][1].append(b)
    return {k: np.corrcoef(np.concatenate(xs[k][0]), np.concatenate(xs[k][1]))[0, 1] for k in LAGS}
for g in [f"{m:02d}" for m in range(1, 10)] + ["jan-ago"]:
    d = j[j.mes <= 8] if g == "jan-ago" else j[j.mes == int(g)]
    c = corr_lags(d); OUT["R26"][g] = dict(corr=c, dias=d["dia"].nunique())
    if g == "jan-ago":
        ds = d["dia"].unique(); gb = {k: v for k, v in d.groupby("dia")}; bs = []
        for _ in range(100):
            sel = rng.choice(ds, len(ds)); x = pd.concat([gb[k].assign(dia=pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)) for i, k in enumerate(sel)]); bs.append(corr_lags(x))
        OUT["R26"][g]["ic"] = {k: (np.percentile([b[k] for b in bs], 2.5), np.percentile([b[k] for b in bs], 97.5)) for k in LAGS}
    print("R26", g, {k: round(v, 3) for k, v in c.items()}, flush=True)
pickle.dump(OUT, open(os.path.join(HERE, "r25_r26.pkl"), "wb"))
