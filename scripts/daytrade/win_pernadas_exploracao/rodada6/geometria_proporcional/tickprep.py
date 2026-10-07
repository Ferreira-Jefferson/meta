"""Converte ticks (mar-jun, so desc) em 'barras degeneradas' (um ponto por mudanca de preco), filtrando ticks fora da faixa do M1."""
import os, sys, numpy as np, pandas as pd, pickle
import geomlib as G
TD = "C:/Users/Jeffe/Documents/study/meta/data/cache_win_ticks/WIN@D/"
def tick_day(d):
    f = TD + d["date"].replace(".", "-") + ".pkl"
    if not os.path.exists(f): return None
    t = pd.read_pickle(f)
    t = t[t["last"] > 0]
    sec = t.time_msc.values // 1000
    mn = ((sec % 86400) // 60).astype(int)
    p = t["last"].values.astype(float)
    # alinha ao ajuste por diferenca do M1: offset do dia = mediana(close M1 - ultimo tick do minuto)
    ok0 = (mn >= G.MIN_INI) & (mn <= G.MIN_FIM)
    lastp = pd.Series(p[ok0]).groupby(mn[ok0]).last()
    cm = pd.Series(d["c"], index=d["m"])
    common = lastp.index.intersection(cm.index)
    off = float(np.median(cm[common].values - lastp[common].values)); off = round(off / 5) * 5
    p = p + off
    # faixa do M1 daquele minuto
    lo = np.full(1500, np.nan); hi = np.full(1500, np.nan)
    lo[d["m"]] = d["l"]; hi[d["m"]] = d["h"]
    ok = (mn >= G.MIN_INI) & (mn <= G.MIN_FIM) & (p >= lo[mn]) & (p <= hi[mn])
    frac = ok.mean() if len(ok) else 0
    p = p[ok]; mn = mn[ok]; sec = sec[ok]
    # barras de 1 segundo -> 4 pontos (abre, extremo que veio primeiro, outro extremo, fecha); descarta a ordem sub-segundo
    df = pd.DataFrame(dict(s=sec, p=p, i=np.arange(len(p))))
    g = df.groupby("s")
    fi = g.p.first(); la = g.p.last(); lo_ = g.p.min(); hi_ = g.p.max()
    ilo = df.loc[g.p.idxmin().values, "i"].values; ihi = df.loc[g.p.idxmax().values, "i"].values
    lo_first = ilo <= ihi
    x1 = np.where(lo_first, lo_.values, hi_.values); x2 = np.where(lo_first, hi_.values, lo_.values)
    P = np.column_stack([fi.values, x1, x2, la.values]).ravel()
    M = np.repeat(((fi.index.values % 86400) // 60).astype(int), 4)
    ch = np.concatenate([[True], P[1:] != P[:-1]])
    p = P[ch]; mn = M[ch]
    return dict(date=d["date"], warm=False, month=d["month"], m=mn, o=p, h=p, l=p, c=p, frac_ok=frac, off=off)
if __name__ == "__main__":
    days = G.load_days()
    out = {}
    for i, d in enumerate(days):
        if d["warm"] or not (3 <= d["month"] <= 6): continue
        td = tick_day(d)
        if td is None: print("sem tick", d["date"]); continue
        out[i] = td
        print(d["date"], len(td["c"]), "ok %.3f" % td["frac_ok"], flush=True)
    pickle.dump(out, open("ticks_desc.pkl", "wb"))
