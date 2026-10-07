"""Confluencia multi-timeframe: barreiras M15/H1 x queda/alta M5 no WIN (2026 apenas).
Tudo causal: nivel em t usa so' barras completas ate o fechamento de t."""
import numpy as np, pandas as pd, io, warnings
warnings.filterwarnings("ignore")
CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
HORIZ = 60
PAIRS = [(150, 150), (250, 250), (400, 250)]
METRICS = ["B150", "B250", "B400", "S150", "S250", "S400", "PL", "DR"]
NB = 4  # buckets de hora
BUCKET_NAMES = ["09:30-10:30", "10:30-12:00", "12:00-14:00", "14:00-16:50"]


def load(end_date):
    """Le so' linhas de 2026 (filtro textual; nada anterior e' parseado)."""
    lines = []
    with open(CSV, "r") as f:
        f.readline()
        for ln in f:
            if ln.startswith("2026."):
                if ln[:10] > end_date:
                    break
                lines.append(ln)
    df = pd.read_csv(io.StringIO("".join(lines)), sep="\t", header=None,
                     names=["date", "time", "o", "h", "l", "c", "tv", "v", "sp"])
    df["ts"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df = df[(df.ts.dt.hour * 60 + df.ts.dt.minute >= 540) & (df.ts.dt.hour * 60 + df.ts.dt.minute < 1075)]
    df = df.reset_index(drop=True)[["ts", "o", "h", "l", "c", "tv"]]
    df["day"] = df.ts.dt.strftime("%Y-%m-%d")
    return df


def shuffle_blocks(df, rng):
    d = df.copy()
    mod = d.ts.dt.hour * 60 + d.ts.dt.minute
    grp = (d.day + "_" + (mod // 30).astype(str)).values
    idx = np.arange(len(d))
    perm = idx.copy()
    # permuta dentro de cada grupo (grupos contiguos)
    starts = np.r_[0, np.flatnonzero(grp[1:] != grp[:-1]) + 1, len(d)]
    for a, b in zip(starts[:-1], starts[1:]):
        perm[a:b] = a + rng.permutation(b - a)
    o, h, l, c, tv = (d[k].values[perm] for k in ["o", "h", "l", "c", "tv"])
    dc = c - o
    day = d.day.values
    open0 = d.groupby("day")["o"].transform("first").values
    newc = open0 + pd.Series(dc).groupby(day).cumsum().values
    newo = np.r_[0, newc[:-1]]
    first = np.r_[True, day[1:] != day[:-1]]
    newo[first] = open0[first]
    d["o"], d["c"] = newo, newc
    d["h"], d["l"] = newo + (h - o), newo + (l - o)
    d["tv"] = tv
    return d


def expand(arr, ends, m1end):
    idx = np.searchsorted(ends, m1end, side="right") - 1
    out = np.full((len(m1end),) + arr.shape[1:], np.nan)
    ok = idx >= 0
    out[ok] = arr[idx[ok]]
    return out


def resamp(df, rule):
    r = df.set_index("ts").resample(rule, label="left", closed="left").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last", "tv": "sum"}).dropna()
    r["end"] = r.index + pd.Timedelta(rule)
    return r


def pivots(r, k, nlast=4):
    h, l = r.h.values, r.l.values
    n = len(r)
    ev = []
    for i in range(k, n - k):
        if h[i] == h[i - k:i + k + 1].max():
            ev.append((i + k, i, h[i], 1))
        if l[i] == l[i - k:i + k + 1].min():
            ev.append((i + k, i, l[i], -1))
    ev.sort()
    out = np.full((n, nlast), np.nan)
    last = []
    j = 0
    lastH = lastL = None
    fib = {}
    seqH = np.full((n, 2), np.nan)  # (nivel, idx) ultima pivot high
    seqL = np.full((n, 2), np.nan)
    for c in range(n):
        while j < len(ev) and ev[j][0] <= c:
            last.append(ev[j][2])
            last = last[-nlast:]
            if ev[j][3] == 1:
                lastH = (ev[j][2], ev[j][1])
            else:
                lastL = (ev[j][2], ev[j][1])
            j += 1
        out[c, :len(last)] = last[::-1]
        if lastH is not None:
            seqH[c] = lastH
        if lastL is not None:
            seqL[c] = lastL
    return out, seqH, seqL


def fibs(seqH, seqL, rs=(0.382, 0.5, 0.618)):
    res = {}
    for r in rs:
        lv = np.full(len(seqH), np.nan)
        ok = ~np.isnan(seqH[:, 0]) & ~np.isnan(seqL[:, 0])
        up = ok & (seqH[:, 1] > seqL[:, 1])
        dn = ok & (seqL[:, 1] > seqH[:, 1])
        rng_ = seqH[:, 0] - seqL[:, 0]
        lv[up] = seqH[up, 0] - r * rng_[up]
        lv[dn] = seqL[dn, 0] + r * rng_[dn]
        res[r] = lv[:, None]
    return res


def build_levels(df):
    n = len(df)
    m1end = (df.ts + pd.Timedelta("1min")).values
    close, high, low, opn, tv = (df[k].values for k in ["c", "h", "l", "o", "tv"])
    L = {}
    m15, h1, m5 = resamp(df, "15min"), resamp(df, "60min"), resamp(df, "5min")
    e15, e60, e5 = m15.end.values, h1.end.values, m5.end.values
    for k in (2, 3):
        p, sH, sL = pivots(m15, k)
        L[f"piv15_k{k}"] = expand(p, e15, m1end)
    for k in (2, 3):
        p, sH, sL = pivots(h1, k)
        L[f"pivH1_k{k}"] = expand(p, e60, m1end)
        if k == 2:
            for r, lv in fibs(sH, sL).items():
                L[f"fibH1_{int(r*1000)}"] = expand(lv, e60, m1end)
    # medias
    L["m15_ema21"] = expand(m15.c.ewm(span=21, adjust=False).mean().values[:, None], e15, m1end)
    L["m15_ema50"] = expand(m15.c.ewm(span=50, adjust=False).mean().values[:, None], e15, m1end)
    L["m15_sma200"] = expand(m15.c.rolling(200).mean().values[:, None], e15, m1end)
    L["h1_ema20"] = expand(h1.c.ewm(span=20, adjust=False).mean().values[:, None], e60, m1end)
    L["h1_ema50"] = expand(h1.c.ewm(span=50, adjust=False).mean().values[:, None], e60, m1end)
    L["h1_sma100"] = expand(h1.c.rolling(100).mean().values[:, None], e60, m1end)
    # dia
    day = df.day.values
    g = df.groupby("day")
    cmx = g["h"].cummax().groupby(df.day).shift(1).values
    cmn = g["l"].cummin().groupby(df.day).shift(1).values
    L["dayHL"] = np.c_[cmx, cmn]
    dd = pd.DataFrame({"day": day, "h": high, "l": low, "c": close, "o": opn})
    agg = dd.groupby("day").agg(H=("h", "max"), Lo=("l", "min"), C=("c", "last"), O=("o", "first"))
    prev = agg.shift(1)
    pm = df[["day"]].join(prev, on="day")
    L["prevHLC"] = pm[["H", "Lo", "C"]].values
    dopen = df.groupby("day")["o"].transform("first").values
    L["open"] = dopen[:, None]
    mod = (df.ts.dt.hour * 60 + df.ts.dt.minute).values
    for name, lim in (("or30", 570), ("or60", 600)):
        inor = mod < lim
        orh = pd.Series(np.where(inor, high, np.nan)).groupby(day).transform("max").values
        orl = pd.Series(np.where(inor, low, np.nan)).groupby(day).transform("min").values
        v = np.c_[orh, orl]
        v[inor] = np.nan
        L[name] = v
    # vwap
    tp = (high + low + close) / 3
    cv = pd.Series(tv * 1.0).groupby(day).cumsum().values
    cpv = pd.Series(tv * tp).groupby(day).cumsum().values
    cp2 = pd.Series(tv * tp * tp).groupby(day).cumsum().values
    vw = cpv / cv
    sd = np.sqrt(np.maximum(cp2 / cv - vw * vw, 0))
    L["vwap"] = vw[:, None]
    L["vwap_b1"] = np.c_[vw + sd, vw - sd]
    L["vwap_b2"] = np.c_[vw + 2 * sd, vw - 2 * sd]
    # perfil de volume do dia ate t
    poc = np.full(n, np.nan); val = poc.copy(); vah = poc.copy(); prevpoc = poc.copy()
    starts = np.r_[0, np.flatnonzero(day[1:] != day[:-1]) + 1, n]
    ppoc = np.nan
    BIN = 25.0
    for a, b in zip(starts[:-1], starts[1:]):
        ref = opn[a] - 5000
        hist = np.zeros(400)
        for t in range(a, b):
            bi = int(np.clip((tp[t] - ref) / BIN, 0, 399))
            hist[bi] += tv[t]
            poc[t] = ref + (hist.argmax() + 0.5) * BIN
            cs = np.cumsum(hist)
            tot = cs[-1]
            val[t] = ref + (np.searchsorted(cs, 0.15 * tot) + 0.5) * BIN
            vah[t] = ref + (np.searchsorted(cs, 0.85 * tot) + 0.5) * BIN
            prevpoc[t] = ppoc
        ppoc = poc[b - 1]
    L["poc"] = poc[:, None]
    L["val_vah"] = np.c_[val, vah]
    L["prevpoc"] = prevpoc[:, None]
    # niveis tocados varias vezes (extremos de barras M5, bins de 100 pts, no dia)
    tl = np.full(len(m5), np.nan)
    m5day = m5.index.strftime("%Y-%m-%d").values
    m5h, m5l = m5.h.values, m5.l.values
    cur = None
    for i in range(len(m5)):
        if m5day[i] != cur:
            cur = m5day[i]
            cnt = {}
        for x in (m5h[i], m5l[i]):
            bkt = int(x // 100)
            cnt[bkt] = cnt.get(bkt, 0) + 1
        bb = max(cnt, key=cnt.get)
        if cnt[bb] >= 3:
            tl[i] = bb * 100 + 50
    L["touch"] = expand(tl[:, None], e5, m1end)
    # retorno percentual
    pc = prev["C"].reindex(day).values
    for p in (0.005, 0.01, 0.015, 0.02):
        L[f"pctOpen_{p*100:g}"] = np.c_[dopen * (1 + p), dopen * (1 - p)]
        L[f"pctPC_{p*100:g}"] = np.c_[pc * (1 + p), pc * (1 - p)]
    return L


def fwd_outcomes(df):
    """Para cada t: primeiro-a-tocar (Y,Z) subindo (UF) e descendo (DF), plato, deriva 60."""
    n = len(df)
    o, h, l, c = (df[k].values for k in ["o", "h", "l", "c"])
    day = pd.factorize(df.day.values)[0]
    pad = HORIZ + 2
    def sh(a, j, fill):
        out = np.full(n, fill, dtype=float)
        if j < n:
            out[:n - j] = a[j:]
        return out
    p0 = c
    res = {}
    for (Y, Z) in PAIRS:
        res[("UF", Y, Z)] = np.zeros(n, dtype=np.int8)
        res[("DF", Y, Z)] = np.zeros(n, dtype=np.int8)
    rmax = np.full(n, -np.inf); rmin = np.full(n, np.inf)
    drift = np.full(n, np.nan)
    for j in range(1, HORIZ + 1):
        valid = sh(day, j, -1) == day
        hi, lo, op, cl = sh(h, j, np.nan), sh(l, j, np.nan), sh(o, j, np.nan), sh(c, j, np.nan)
        upbar = cl >= op
        if j <= 20:
            rmax = np.where(valid, np.maximum(rmax, hi), rmax)
            rmin = np.where(valid, np.minimum(rmin, lo), rmin)
        if j == HORIZ:
            drift = np.where(valid, cl - p0, np.nan)
        for (Y, Z) in PAIRS:
            r = res[("UF", Y, Z)]
            upT, dnS = hi >= p0 + Y, lo <= p0 - Z
            # barra de alta: baixa antes; barra de baixa: alta antes
            new = np.where(upbar, np.where(dnS, -1, np.where(upT, 1, 0)),
                           np.where(upT, 1, np.where(dnS, -1, 0)))
            m = (r == 0) & valid
            r[m] = new[m]
            r = res[("DF", Y, Z)]
            dnT, upS = lo <= p0 - Y, hi >= p0 + Z
            new = np.where(upbar, np.where(dnT, 1, np.where(upS, -1, 0)),
                           np.where(upS, -1, np.where(dnT, 1, 0)))
            m = (r == 0) & valid
            r[m] = new[m]
    plat = ((rmax - rmin) <= 400).astype(float)
    plat[~np.isfinite(rmax - rmin)] = np.nan
    return res, plat, drift


def event_conditions(df, D):
    day = df.day
    rm = df.groupby("day")["h"].rolling(60, min_periods=1).max().reset_index(level=0, drop=True).sort_index().values
    rn = df.groupby("day")["l"].rolling(60, min_periods=1).min().reset_index(level=0, drop=True).sort_index().values
    c = df.c.values
    c15 = pd.Series(c).groupby(day.values).shift(15).values
    dn = ((rm - c) >= D) & (c < c15)
    up = ((c - rn) >= D) & (c > c15)
    mod = (df.ts.dt.hour * 60 + df.ts.dt.minute).values
    tm = (mod >= 570) & (mod <= 1010)
    return dn & tm, up & tm, mod


def detect(close, Lm, cond, dirn, N, cool=30):
    dist = (close[:, None] - Lm) if dirn > 0 else (Lm - close[:, None])
    inz = (dist >= 0) & (dist <= N)
    pd_ = np.vstack([np.full((1, dist.shape[1]), np.nan), dist[:-1]])
    enter = inz & (pd_ > N)
    ev = np.flatnonzero(enter.any(1) & cond)
    keep, last = [], -10**9
    for t in ev:
        if t - last >= cool:
            keep.append(t); last = t
    return np.array(keep, dtype=int)


def bucket_of(mod):
    return np.select([mod < 630, mod < 720, mod < 840], [0, 1, 2], 3)


def collect(df, L, res, plat, drift, conds, Ns, split_ts, win, shift_rng=None, shift_amp=1500):
    """Retorna dict (fam,N,D) -> array (2 periodos, NB, 1+len(METRICS)) de somas.
    win=(ini,fim) strings de data inclusive para os eventos."""
    close = df.c.values
    day = df.day.values
    inwin = (day >= win[0]) & (day <= win[1])
    per = (day >= split_ts).astype(int)
    out = {}
    mod = (df.ts.dt.hour * 60 + df.ts.dt.minute).values
    bk = bucket_of(mod)
    dayid = pd.factorize(day)[0]
    if shift_rng is not None:
        delta = shift_rng.uniform(-shift_amp, shift_amp, dayid.max() + 1)[dayid]
    mets = {}
    for (Y, Z), nm in zip(PAIRS, ["150", "250", "400"]):
        mets[("UF", nm)] = res[("UF", Y, Z)]; mets[("DF", nm)] = res[("DF", Y, Z)]
    for fam, Lm in L.items():
        if shift_rng is not None:
            Lm = Lm + delta[:, None]
        for D, (cdn, cup, _) in conds.items():
            for N in Ns:
                evs = []
                for dirn, cond in ((1, cdn), (-1, cup)):
                    t = detect(close, Lm, cond & inwin, dirn, N)
                    evs.append((dirn, t))
                S = np.zeros((2, NB, 1 + len(METRICS)))
                for dirn, t in evs:
                    if len(t) == 0:
                        continue
                    key = "UF" if dirn > 0 else "DF"
                    cols = [(mets[(key, nm)][t] == 1).astype(float) for nm in ["150", "250", "400"]]
                    cols += [(mets[(key, nm)][t] == -1).astype(float) for nm in ["150", "250", "400"]]
                    cols += [plat[t], -dirn * drift[t] * -1 if False else (dirn * drift[t])]
                    M = np.c_[np.ones(len(t)), np.array(cols).T]
                    # DR: deriva na direcao do repique (suporte: subir positivo)
                    ok = ~np.isnan(M).any(1)
                    M, tt = M[ok], t[ok]
                    for p in (0, 1):
                        for b in range(NB):
                            m = (per[tt] == p) & (bk[tt] == b)
                            if m.any():
                                S[p, b] += M[m].sum(0)
                out[(fam, N, D)] = S
    return out
