import os, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
res = pickle.load(open(os.path.join(HERE, "res_dias.pkl"), "rb"))
ND = len(res); NS = len(res[0]["sims"])
meses = np.array([int(r["date"][5:7]) for r in res])
XS = (150, 250, 375, 500)
NOMES = ["pnum", "pden", "cn", "csx", "csy", "csxx", "csyy", "csxy"] + [f"{k}{X}" for X in XS for k in ("n", "d")] + \
        ["nleg", "ncorr", "dias", "maxcorr", "oppn", "oppd", "nclosed"]

def vec(L, ev, real):
    """L: legs [dir,size,dur,speed,maxcorr,ncorr,slot,closed,opp,first]; ev: matriz com colunas X,d,A,y (sims) ou real (y na col 6)."""
    v = np.zeros(len(NOMES))
    cl = L[L[:, 7] == 1]
    sz = cl[:, 1]
    if len(sz) >= 2:
        a, b = sz[:-1], sz[1:]
        # pares consecutivos (todas as pernadas fechadas consecutivas do dia sao sequenciais)
        v[0] = (b >= a).sum(); v[1] = len(a)
        la, lb = np.log(a), np.log(b)
        v[2:8] = [len(a), la.sum(), lb.sum(), (la*la).sum(), (lb*lb).sum(), (la*lb).sum()]
    if real: X, y = ev[:, 0], ev[:, 6]
    else: X, y = ev[:, 0], ev[:, 3]
    for j, x in enumerate(XS):
        m = (X == x) & ~np.isnan(y)
        v[8+2*j] = y[m].sum(); v[9+2*j] = m.sum()
    v[16] = len(L); v[17] = np.nansum(cl[:, 5]); v[18] = 1; v[19] = np.nansum(cl[:, 4])
    o = cl[:, 8]; o = o[~np.isnan(o)]
    v[20] = o.sum(); v[21] = len(o); v[22] = len(cl)
    return v

REALCOLS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 11]
Vreal = np.array([vec(r["real"][0][:, REALCOLS], r["real"][1][:, :7], True) for r in res])
Vsim = np.array([[vec(s[0], s[1], False) for s in r["sims"]] for r in res])   # dia, sim, k

def stats(V):
    g = dict(zip(NOMES, V))
    out = {}
    out["R13"] = g["pnum"] / g["pden"] if g["pden"] else np.nan
    n = g["cn"]
    if n > 2:
        cov = g["csxy"]/n - g["csx"]/n*g["csy"]/n
        out["R16"] = cov / np.sqrt(max(g["csxx"]/n-(g["csx"]/n)**2, 1e-12) * max(g["csyy"]/n-(g["csy"]/n)**2, 1e-12))
    else: out["R16"] = np.nan
    for X in XS: out[f"R14_{X}"] = g[f"n{X}"] / g[f"d{X}"] if g[f"d{X}"] else np.nan
    out["legs_dia"] = g["nleg"] / g["dias"]
    out["corr_perna"] = g["ncorr"] / g["nclosed"] if g["nclosed"] else np.nan
    out["R26_opp"] = g["oppn"] / g["oppd"] if g["oppd"] else np.nan
    out["n_R13"] = g["pden"]; out["n_R14_250"] = g["d250"]; out["n_R26"] = g["oppd"]
    return out

GRUPOS = {f"{m:02d}": (meses == m) for m in range(1, 10)}
GRUPOS["jan-ago"] = (meses <= 8)
rng = np.random.default_rng(1)
SAIDA = {}
CHAVES = ["R13", "R16", "R14_150", "R14_250", "R14_375", "R14_500", "legs_dia", "corr_perna", "R26_opp"]
for gname, mask in GRUPOS.items():
    idx = np.where(mask)[0]
    real = stats(Vreal[idx].sum(0))
    sims = [stats(Vsim[idx, s].sum(0)) for s in range(NS)]
    # bootstrap de dias
    bs = []
    for b in range(1000):
        sel = rng.choice(idx, len(idx))
        bs.append(stats(Vreal[sel].sum(0)))
    d = {"dias": len(idx)}
    for k in CHAVES:
        sv = np.array([s[k] for s in sims]); bv = np.array([s[k] for s in bs])
        d[k] = dict(real=real[k], nulo=np.nanmean(sv), p5=np.nanpercentile(sv, 5), p95=np.nanpercentile(sv, 95), sd=np.nanstd(sv),
                    ic=(np.nanpercentile(bv, 2.5), np.nanpercentile(bv, 97.5)))
    d["n"] = {k: real[k] for k in ("n_R13", "n_R14_250", "n_R26")}
    SAIDA[gname] = d
pickle.dump(SAIDA, open(os.path.join(HERE, "agg.pkl"), "wb"))
for k in CHAVES:
    print("==", k)
    for g, d in SAIDA.items():
        x = d[k]; print(g, "dias", d["dias"], "real %.3f nulo %.3f [%.3f;%.3f] z %.1f IC [%.3f;%.3f]" % (x["real"], x["nulo"], x["p5"], x["p95"], (x["real"]-x["nulo"])/x["sd"] if x["sd"] else 0, *x["ic"]), "n", {a: int(b) for a, b in d["n"].items()})
