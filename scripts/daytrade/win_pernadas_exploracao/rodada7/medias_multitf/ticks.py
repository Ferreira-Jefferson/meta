"""Sensibilidade com ticks (data/cache_win_ticks/WIN@D): mesmos sinais e niveis (do M1), caminho por tick.
O nivel dos ticks difere do M1 por uma constante por dia (ajuste da serie): corrigida pela mediana de (ultimo - fechamento M1)."""
import os, numpy as np, pandas as pd
import core
from core import floor5, TICK, DESL, CUSTO, BIG

TDIR = "C:/Users/Jeffe/Documents/study/meta/data/cache_win_ticks/WIN@D/"
_cache = {}


def load_day(D, di):
    """Devolve (tms, px) com precos no nivel do M1, ou None."""
    if di in _cache: return _cache[di]
    ix = np.flatnonzero(D.day == di)
    date = D.date[ix[0]].replace(".", "-")
    fn = TDIR + date + ".pkl"
    if not os.path.exists(fn):
        _cache.clear(); _cache[di] = None; return None
    tk = pd.read_pickle(fn)
    tk = tk[tk["last"] > 0]
    ms = (tk.time_msc.values % 86400000).astype(np.int64)
    px = tk["last"].values.astype(float)
    mn = ms // 60000
    g = pd.DataFrame({"mn": mn, "px": px}).groupby("mn").px.last()
    mm = pd.Series(D.c[ix], index=D.m[ix])
    j = pd.concat([g, mm], axis=1, join="inner")
    off = float(np.median(j.iloc[:, 0] - j.iloc[:, 1]))
    _cache.clear(); _cache[di] = (ms, px - off, off)
    return _cache[di]


def sim_ticks(D, idx, t, feat, atr15, geom):
    ttl = geom["ttl"]; otim = geom["otim"]; beyond = 0.0 if otim else TICK
    LO, HI, CL = D.SG[t]
    entry = geom["entry"]; sk = geom["stop"]; K = geom["K"]
    busy = -1; rows = []; nskip = 0
    for n in range(len(idx)):
        i = int(idx[n])
        if i < busy: continue
        dend = int(D.dend[i]); dst = int(D.dstart[i])
        if i + ttl + 2 >= dend: continue
        tk = load_day(D, int(D.day[i]))
        if tk is None:
            nskip += 1; continue
        ms, px, _ = tk
        if t == -1: px = -px
        c = CL[i]
        Lp = floor5(c) if entry == "cl" else floor5(min(c, feat["ef" if entry == "f" else "em"][n]))
        if sk == "e50h":
            Sp = floor5(feat["es"][n]) - TICK; S = Lp - Sp
        elif sk == "x":
            Sp = LO[max(0, i - geom["N"] + 1):i + 1].min() - TICK; S = Lp - Sp
        else:
            a = atr15[n]
            if not np.isfinite(a): busy = i + 1; continue
            S = max(50.0, np.round(geom["Katr"] * a / TICK) * TICK); Sp = Lp - S
        if not (50 <= S <= 500): busy = i + 1; continue
        if K == "hh":
            Tt = floor5(feat["hhi"][n]) - Lp
            if Tt < 3 * S: busy = i + 1; continue
        else:
            Tt = np.round(K * S / TICK) * TICK
        m0 = int(D.m[i])
        a0 = np.searchsorted(ms, (m0 + 1) * 60000, "left"); a1 = np.searchsorted(ms, (m0 + ttl + 1) * 60000, "left")
        hit = np.flatnonzero(px[a0:a1] <= Lp - beyond)
        if len(hit) == 0:
            busy = i + ttl; continue
        jf = a0 + int(hit[0])
        lastm = int(D.m[dend - 1])
        aend = np.searchsorted(ms, (lastm + 1) * 60000, "left")
        seg = px[jf + 1:aend]
        s_i = np.flatnonzero(seg <= Sp); t_i = np.flatnonzero(seg >= Lp + Tt + beyond)
        s0 = s_i[0] if len(s_i) else BIG; t0 = t_i[0] if len(t_i) else BIG
        if s0 < BIG and s0 <= t0:
            pnl = -(S + DESL + CUSTO); ext = jf + 1 + s0; code = 0
        elif t0 < BIG:
            pnl = Tt - CUSTO; ext = jf + 1 + t0; code = 1
        else:
            pnl = seg[-1] - Lp - DESL - CUSTO if len(seg) else -DESL - CUSTO; ext = aend - 1; code = 2
        exm = int(ms[min(ext, len(ms) - 1)] // 60000)
        busy = dst + int(np.searchsorted(D.m[dst:dend], exm, "right")) - 1
        busy = max(busy, i)
        rows.append([D.day[i], i, pnl, code, S, Tt])
    return np.array(rows, float) if rows else np.zeros((0, 6)), nskip
