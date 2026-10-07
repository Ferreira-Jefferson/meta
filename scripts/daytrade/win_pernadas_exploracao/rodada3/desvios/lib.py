import pandas as pd, numpy as np, json, itertools, sys
CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
YS = [250, 500, 750]
OUTS = [f"up1st{y}" for y in YS] + ["novaMax", "novaMin", "fechaAcima", "ret60Up"]


def load(d0, d1):
    df = pd.read_csv(CSV, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df = df[(df.date >= d0) & (df.date <= d1)]
    return {d: g.reset_index(drop=True) for d, g in df.groupby("date")}


def zig_states(O, H, L, C, thr=750):
    n = len(O)
    st = [None] * n
    dir = 0
    hi = lo = None
    ext = None
    piv = None
    npiv = 0
    k = 0
    hik = lok = 0
    for i in range(n):
        pts = (L[i], H[i]) if C[i] >= O[i] else (H[i], L[i])
        for p in pts:
            if hi is None:
                hi = lo = p
                hik = lok = k
            if dir == 0:
                if p > hi:
                    hi = p
                    hik = k
                if p < lo:
                    lo = p
                    lok = k
                if hi - lo >= thr:
                    if lok < hik:
                        piv = lo; dir = 1; ext = hi
                    else:
                        piv = hi; dir = -1; ext = lo
                    npiv = 1
            elif dir == 1:
                if p > ext:
                    ext = p
                elif ext - p >= thr:
                    piv = ext; dir = -1; ext = p; npiv += 1
            else:
                if p < ext:
                    ext = p
                elif p - ext >= thr:
                    piv = ext; dir = 1; ext = p; npiv += 1
            k += 1
        c = C[i]
        if dir == 0:
            st[i] = (0, 0.0, 0.0, 0)
        else:
            st[i] = (dir, abs(ext - piv), abs(ext - c), npiv)
    return st


def bins(x, edges, labels):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    for e, l in zip(edges, labels):
        if x < e:
            return l
    return labels[-1]


def events(days, volmed=None):
    rows = []
    keys = sorted(days)
    prev = None
    for d in keys:
        g = days[d]
        if prev is None:
            prev = g.close.iloc[-1]
            continue  # sem fechamento anterior dentro de 2026
        t = g.time.values
        O = g.open.values; H = g.high.values; L = g.low.values; C = g.close.values
        V = g.tickvol.values.astype(float)
        n = len(g); rng = H - L
        cumv = np.cumsum(V)
        vw = np.cumsum((H + L + C) / 3 * V) / np.maximum(cumv, 1)
        hh = np.maximum.accumulate(H); ll = np.minimum.accumulate(L)
        zs = zig_states(O, H, L, C)
        wd = pd.Timestamp(d.replace('.', '-')).dayofweek
        gap = O[0] - prev
        for i in range(30, n - 1):
            hm = t[i]; mm = int(hm[3:5]); hr = int(hm[:2])
            if mm % 5 != 4:
                continue
            mins = hr * 60 + mm + 1
            if mins < 9 * 60 + 30 or mins > 16 * 60 + 30:
                continue
            c = C[i]
            atr60 = rng[max(0, i - 59):i + 1].mean(); atr30 = rng[i - 29:i + 1].mean()
            r = {}
            r["dia"] = d; r["slot"] = mins // 30
            r["bloco"] = bins(mins, [10 * 60 + 30, 12 * 60, 13 * 60 + 30, 15 * 60], ["09:30-10:30", "10:30-12:00", "12:00-13:30", "13:30-15:00", "15:00-16:30"])
            r["dAbertura"] = bins(c - O[0], [-750, -300, 300, 750], ["<=-750", "-750:-300", "-300:300", "300:750", ">=750"])
            r["dFechAnt"] = bins(c - prev, [-750, -300, 300, 750], ["<=-750", "-750:-300", "-300:300", "300:750", ">=750"])
            r["gap"] = bins(gap, [-300, 300], ["gap<-300", "gap_neutro", "gap>300"])
            r["dVWAPatr"] = bins((c - vw[i]) / (3 * atr60), [-1.5, -0.5, 0.5, 1.5], ["<-1.5", "-1.5:-0.5", "-0.5:0.5", "0.5:1.5", ">1.5"]) if atr60 > 0 else None
            r["volRel"] = None
            if volmed is not None:
                m = volmed.get(mins // 15)
                if m:
                    r["volRel"] = bins(atr30 / m, [0.8, 1.25], ["vol<0.8", "vol_normal", "vol>1.25"])
            rg = hh[i] - ll[i]
            r["posRange"] = bins((c - ll[i]) / rg, [0.2, 0.8], ["pos<0.2", "pos_meio", "pos>0.8"]) if rg > 0 else None
            r["dMaxDia"] = bins(hh[i] - c, [250, 750], ["<250da_max", "250:750da_max", ">750da_max"])
            r["dMinDia"] = bins(c - ll[i], [250, 750], ["<250da_min", "250:750da_min", ">750da_min"])
            z = zs[i]
            r["zDir"] = ["z_sem_perna", "z_alta", "z_baixa"][0 if z[0] == 0 else (1 if z[0] == 1 else 2)]
            r["zProg"] = "z_sem" if z[0] == 0 else bins(z[1], [1250, 2000], ["z_prog750:1250", "z_prog1250:2000", "z_prog>2000"])
            r["zRecuo"] = "z_sem" if z[0] == 0 else bins(z[2], [150, 400], ["zrec<150", "zrec150:400", "zrec>400"])
            r["nPernadas"] = bins(z[3], [1, 2, 3], ["0pern", "1pern", "2pern", "3+pern"])
            r["diaSem"] = ["seg", "ter", "qua", "qui", "sex"][wd]
            r["mom30"] = bins(c - C[i - 30], [-300, -100, 100, 300], ["m30<=-300", "m30-300:-100", "m30_neutro", "m30100:300", "m30>=300"])
            fut_h = H[i + 1:]; fut_l = L[i + 1:]; fut_o = O[i + 1:]; fut_c = C[i + 1:]
            for y in YS:
                up = c + y; dn = c - y
                hu = np.nonzero(fut_h >= up)[0]; hd = np.nonzero(fut_l <= dn)[0]
                a = hu[0] if len(hu) else 10 ** 9
                b = hd[0] if len(hd) else 10 ** 9
                if a == 10 ** 9 and b == 10 ** 9:
                    r[f"up1st{y}"] = np.nan
                elif a < b:
                    r[f"up1st{y}"] = 1.0
                elif b < a:
                    r[f"up1st{y}"] = 0.0
                else:
                    r[f"up1st{y}"] = 1.0 if fut_c[a] < fut_o[a] else 0.0
            r["novaMax"] = float(fut_h.max() >= hh[i] + 250) if hh[i] - c <= 500 else np.nan; r["novaMin"] = float(fut_l.min() <= ll[i] - 250) if c - ll[i] <= 500 else np.nan
            r["fechaAcima"] = float(C[-1] > c) if C[-1] != c else np.nan
            j = i + 60
            r["ret60Up"] = float(C[j] > c) if j < n and C[j] != c else np.nan
            rows.append(r)
        prev = C[-1]
    return pd.DataFrame(rows)


DESC = ["bloco", "dAbertura", "dFechAnt", "gap", "dVWAPatr", "volRel", "posRange", "dMaxDia", "dMinDia", "zDir", "zProg", "zRecuo", "nPernadas", "diaSem", "mom30"]


def cellmasks(ev, pairs=True):
    cells = {}
    for d in DESC:
        for v in ev[d].dropna().unique():
            cells[((d, v),)] = (ev[d] == v).values
    if pairs:
        for d1, d2 in itertools.combinations(DESC, 2):
            for v1 in ev[d1].dropna().unique():
                m1 = (ev[d1] == v1).values
                for v2 in ev[d2].dropna().unique():
                    cells[((d1, v1), (d2, v2))] = m1 & (ev[d2] == v2).values
    return cells


def stats_cell(ev, m, out, base, dayidx, W, nd):
    y = ev[out].values; b = base[out].values
    ok = m & ~np.isnan(y)
    n = int(ok.sum())
    if n == 0:
        return None
    dx = np.bincount(dayidx[ok], weights=y[ok], minlength=nd)
    db = np.bincount(dayidx[ok], weights=b[ok], minlength=nd)
    dn = np.bincount(dayidx[ok], minlength=nd)
    N = W @ dn
    with np.errstate(all='ignore'):
        diff = (W @ dx - W @ db) / N
    return n, int((dn > 0).sum()), y[ok].mean(), b[ok].mean(), np.nanpercentile(diff, 0.25), np.nanpercentile(diff, 99.75)


def basecols(ev):
    base = pd.DataFrame(index=ev.index)
    for o in OUTS:
        base[o] = ev.groupby("slot")[o].transform("mean")
    return base


def key_str(key):
    return " & ".join(f"{a}={b}" for a, b in key)
