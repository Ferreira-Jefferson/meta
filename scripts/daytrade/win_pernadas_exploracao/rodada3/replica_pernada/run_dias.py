import os, sys, pickle, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from core import *
HERE = os.path.dirname(os.path.abspath(__file__))
NSIM = int(os.environ.get("NSIM", "100"))

def indicadores(w):
    c = w["close"]
    w = w.copy()
    w["ema9"] = c.ewm(span=9, adjust=False).mean(); w["ema21"] = c.ewm(span=21, adjust=False).mean()
    dl = c.diff(); up = dl.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); dn = (-dl).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    w["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    tp = (w["high"] + w["low"] + w["close"]) / 3
    dia = w.index.normalize()
    w["vwap"] = (tp * w["vol"]).groupby(dia).cumsum() / w["vol"].groupby(dia).cumsum()
    # ATR M5 (media do range das ultimas 5 velas M5 completas, dentro do dia), valor disponivel ao fim da vela
    atr = pd.Series(np.nan, index=w.index)
    for d, g in w.groupby(dia):
        r = g.resample("5min", label="left", closed="left").agg({"high": "max", "low": "min"}).dropna()
        a = (r["high"] - r["low"]).rolling(5, min_periods=1).mean(); a.index = a.index + pd.Timedelta("5min")
        u = a.reindex(a.index.union(g.index)).ffill().reindex(g.index)
        atr.loc[g.index] = u.values
    w["atr5"] = atr
    return w

def dia_task(args):
    data, nsim, flowd, flowr = args
    o, h, l, c, v, mn, dW = data["o"], data["h"], data["l"], data["c"], data["v"], data["mn"], data["dW"]
    rng = np.random.default_rng(abs(hash(data["date"])) % (2**32) if False else int(data["date"].replace("-", "")))
    out = {"date": data["date"], "nbars": len(mn)}
    ident = np.arange(len(mn))
    p = caminho(o, h, l, c, ident)
    L, ev = analisa_caminho(p, mn, np.cumsum(dW))
    # features dos eventos reais
    ind = data["ind"]; F = []
    flow = flowd
    for e in ev:
        X, d, A, i, Ei, si, y = e; d = int(d); b = int(i // 4); Eb = int(Ei // 4); sb = int(si // 4)
        if b < 1 or np.isnan(y): F.append([np.nan] * 13); continue
        atr = ind["atr5"][b-1]; cl = ind["close"][b-1]
        legv = v[sb:Eb+1].mean() + 1e-9
        rs = ind["rsi"]
        f = [-d * (ind["ema9"][b-1] - ind["ema21"][b-1]) / atr,
             d * (cl - ind["ema21"][b-1]) / atr,
             d * (rs[b-1] - 50),
             np.nanmax(d * rs[sb:Eb+1]) - d * rs[Eb],
             d * (p[int(Ei)] - ind["vwap"][b-1]) / atr,
             v[b-1] / legv,
             v[max(Eb-1, 0)] / legv,
             -d * (c[Eb] - o[Eb]) / max(h[Eb] - l[Eb], 1.0),
             ((h[Eb] - max(o[Eb], c[Eb])) if d == 1 else (min(o[Eb], c[Eb]) - l[Eb])) / max(h[Eb] - l[Eb], 1.0),
             A / (((Ei - si) / 4.0) + 1.0) ,
             np.nan, mn[b], np.nan]
        if flowr is not None:
            m0 = int(mn[sb]); m1 = int(mn[b-1])
            if m1 >= m0:
                bu = flowr[m0:m1+1, 0].sum(); se = flowr[m0:m1+1, 1].sum(); to = flowr[m0:m1+1, 2].sum()
                if to > 0: f[12] = d * (bu - se) / to
        if flow is not None:
            m0 = int(mn[sb]); m1 = int(mn[b-1])
            if m1 >= m0:
                bu = flow[m0:m1+1, 0].sum(); se = flow[m0:m1+1, 1].sum(); to = flow[m0:m1+1, 2].sum()
                if to > 0: f[10] = d * (bu - se) / to
        F.append(f + [ ])
    ev_f = np.hstack([ev, np.array(F, dtype=float).reshape(len(ev), -1)]) if len(ev) else np.zeros((0, 7 + 13))
    out["real"] = (L, ev_f)
    sims = []
    for s in range(nsim):
        order = ordem_embaralhada(mn, rng)
        ps = caminho(o, h, l, c, order)
        Ls, evs = analisa_caminho(ps, mn, np.cumsum(dW[order]))  # slots de tempo mantidos (perfil horario)
        sims.append((Ls[:, [0, 1, 2, 3, 4, 5, 6, 7, 8, 11]], evs[:, [0, 1, 2, 6]]))
    out["sims"] = sims
    return out

def monta():
    w = ler(WIN); w = indicadores(w)
    wd = ler(WDO)
    ret = wd["close"].diff()
    flowall = pickle.load(open(os.path.join(HERE, "flow_proxy.pkl"), "rb")); flowreal = pickle.load(open(os.path.join(HERE, "flow_real.pkl"), "rb"))
    dias = []
    for dia, g in w.groupby(w.index.normalize()):
        if len(g) < 100: continue
        ds = dia.strftime("%Y-%m-%d")
        mn = (g.index.hour * 60 + g.index.minute).to_numpy()
        dW = ret.reindex(g.index).fillna(0.0).to_numpy()
        ind = {k: g[k].to_numpy() for k in ("ema9", "ema21", "rsi", "vwap", "atr5", "close")}
        ind["atr5"] = np.where(np.isnan(ind["atr5"]), np.nanmean(ind["atr5"]), ind["atr5"])
        dias.append(dict(date=ds, o=g["open"].to_numpy(), h=g["high"].to_numpy(), l=g["low"].to_numpy(), c=g["close"].to_numpy(),
                         v=g["vol"].to_numpy(), mn=mn, dW=dW, ind=ind), )
    return dias, flowall, flowreal

if __name__ == "__main__":
    dias, flowall, flowreal = monta()
    print("dias", len(dias), "sims", NSIM, flush=True)
    res = []; t0 = time.time()
    with ProcessPoolExecutor(10) as ex:
        futs = [ex.submit(dia_task, (d, NSIM, flowall.get(d["date"]), flowreal.get(d["date"]))) for d in dias]
        for k, fu in enumerate(as_completed(futs)):
            r = fu.result(); res.append(r)
            print(r["date"], "barras", r["nbars"], "pernadas", len(r["real"][0]), "eventos", len(r["real"][1]), "t=%.0fs" % (time.time() - t0), flush=True)
    res.sort(key=lambda r: r["date"])
    pickle.dump(res, open(os.path.join(HERE, "res_dias.pkl"), "wb"))
