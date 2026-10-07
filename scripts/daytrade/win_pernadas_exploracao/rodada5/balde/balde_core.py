"""Rodada 5 / balde: perder de colherinha, ganhar de balde. Simulador M1 vetorizado (so 2026).

Execucao: entrada = LIMITE no fechamento da vela-gatilho, valida por TTL barras; enche so se o preco
negociar 1 tick ALEM (conservador) ou se tocar (otimista). Alvo = limite (conservador: high >= alvo+5;
otimista: high >= alvo). Stop a mercado: -(S+5) ; custo 2 pts/op ; fim do pregao (17:50) = mercado (-5-2).
Mesma vela M1: stop vence alvo; na vela do preenchimento vale so o stop (alvo so a partir da seguinte).
Um trade por vez (ordem pendente tambem bloqueia). Sem pyramiding.
"""
from __future__ import annotations
import sys, bisect
import numpy as np, pandas as pd

CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada4/decisao")
import motor  # noqa

TTL = 5
TICK = 5.0
CUSTO = 2.0
DESL = 5.0
BIG = 10 ** 6
MIN_INI, MIN_FIM = 540, 1070          # 09:00 .. 17:50
SIG_INI, SIG_FIM = 550, 1050          # sinais 09:10 .. 17:30
NBLK = 19                              # blocos de 30 min a partir de 09:00 (09:00 .. 17:30)
STOPS = [50, 75, 100, 150, 200, 250]
ALVOS = [300, 400, 600, 750, 1000, 1500]
PARES = [(s, t) for s in STOPS for t in ALVOS if t >= 3 * s]
TRIGS = ["none", "h<11", "v2x", "onda", "h<11&v2x", "v2x&onda"]
DIRS = ["a_aleat", "b_perna", "c_vela", "d_contra"]


def load_days():
    d = pd.read_csv(CSV, sep="\t")
    d.columns = [c.strip("<>") for c in d.columns]
    d = d[d.DATE.str.startswith("2026")].copy()          # NUNCA 2025 ou antes
    hh = d.TIME.str.slice(0, 2).astype(int); mm = d.TIME.str.slice(3, 5).astype(int)
    d["m"] = hh * 60 + mm
    d = d[(d.m >= MIN_INI) & (d.m <= MIN_FIM)]
    days = []
    for date, g in d.groupby("DATE", sort=True):
        days.append(dict(date=date, month=int(date[5:7]), m=g.m.values.astype(int),
                         o=g.OPEN.values.astype(float), h=g.HIGH.values.astype(float),
                         l=g.LOW.values.astype(float), c=g.CLOSE.values.astype(float)))
    return days


def window_of(month):
    return "desc" if month <= 6 else ("conf" if month <= 8 else "ref")


def avg_range_prev(days, lookback=20, minprev=10):
    """Para cada dia: range medio M1 do mesmo minuto nos 20 pregoes anteriores (NaN se < 10 dias)."""
    nd = len(days); R = np.full((nd, MIN_FIM - MIN_INI + 1), np.nan)
    for i, d in enumerate(days):
        R[i, d["m"] - MIN_INI] = d["h"] - d["l"]
    out = []
    for i in range(nd):
        if i < minprev:
            out.append(None); continue
        with np.errstate(all="ignore"):
            a = np.nanmean(R[max(0, i - lookback):i], axis=0)
        out.append(a)
    return out


def shuffle_day(d, rng):
    """Embaralha as velas M1 dentro de blocos de 30 min (preserva horario, destroi ordem)."""
    o, h, l, c, m = d["o"], d["h"], d["l"], d["c"], d["m"]
    n = len(c)
    gap = np.empty(n); gap[0] = 0.0; gap[1:] = o[1:] - c[:-1]
    dh, dl, dc = h - o, l - o, c - o
    blk = (m - MIN_INI) // 30
    perm = np.arange(n)
    for b in np.unique(blk):
        ix = np.nonzero(blk == b)[0]
        perm[ix] = rng.permutation(ix)
    gap_s = gap[perm].copy()
    # a primeira vela de cada bloco herda o gap da vela que antes abria o bloco (preserva deslocamento do bloco)
    o2 = np.empty(n); c2 = np.empty(n)
    prev = o[0]
    for k in range(n):
        o2[k] = o[0] if k == 0 else prev + gap_s[k]
        prev = o2[k] + dc[perm[k]]
        c2[k] = prev
    h2 = o2 + dh[perm]; l2 = o2 + dl[perm]
    e = dict(d); e.update(o=o2, h=h2, l=l2, c=c2)
    return e


def zigzag_dir(o, h, l, c, thr=750.0):
    n = len(c); out = np.zeros(n, int)
    dirn = 0; mn = np.inf; mx = -np.inf; ext = 0.0
    for i in range(n):
        pts = (l[i], h[i]) if c[i] >= o[i] else (h[i], l[i])
        for p in pts:
            if dirn == 0:
                mn = min(mn, p); mx = max(mx, p)
                if p - mn >= thr and p == mx:
                    dirn = 1; ext = p
                elif mx - p >= thr and p == mn:
                    dirn = -1; ext = p
            elif dirn == 1:
                ext = max(ext, p)
                if ext - p >= thr:
                    dirn = -1; ext = p
            else:
                ext = min(ext, p)
                if p - ext >= thr:
                    dirn = 1; ext = p
        out[i] = dirn
    return out


def first_idx(B):
    a = B.argmax(1)
    ok = B[np.arange(B.shape[0]), a]
    return np.where(ok, a, BIG)


def sim_dir(lo, hi, c, variants, otim, tec_ext):
    """Simula todas as variantes para uma direcao (coords transformadas: para venda lo=-hi, hi=-lo, c=-c).
    tec_ext[N] = distancia (pts) do preco de entrada ate o extremo das N ultimas velas (+5), por linha."""
    n = len(c); idx = np.arange(n)
    beyond_e = 0.0 if otim else TICK
    beyond_t = 0.0 if otim else TICK
    # preenchimento
    f = np.full(n, -1)
    for o in range(TTL, 0, -1):
        k = idx + o
        ok = k < n
        kk = np.minimum(k, n - 1)
        cond = ok & ((lo[kk] - c) <= -beyond_e)
        f = np.where(cond, k, f)
    filled = f >= 0
    fe = np.where(filled, f, BIG)
    col = idx[None, :]
    rl = lo[None, :] - c[:, None]
    rh = hi[None, :] - c[:, None]
    rlm = np.where(col >= fe[:, None], rl, np.inf)
    rhm = np.where(col > fe[:, None], rh, -np.inf)
    eod_rel = c[-1] - c - DESL - CUSTO
    res = {}
    cache_ts = {}; cache_tt = {}; cache_ta = {}; cache_tb = {}
    for key, (S, T, kind, arm) in variants.items():
        # S,T: vetores por linha (ou escalares); kind 'F','BE','P'; arm = nivel de armar (vetor) ou None
        Sv = np.broadcast_to(np.asarray(S, float), (n,)).copy()
        Tv = np.broadcast_to(np.asarray(T, float), (n,)).copy()
        valid = np.isfinite(Sv) & np.isfinite(Tv)
        Ss = np.where(valid, Sv, 1e9)
        ck = ("s", key[1] if kind == "F" else tuple(Ss[:3]) + (Ss.sum(),))
        ts = first_idx(rlm <= -Ss[:, None])
        tt = first_idx(rhm >= (Tv + beyond_t)[:, None])
        stopm = valid & filled & (ts <= tt) & (ts < BIG)
        targm = valid & filled & (tt < ts)
        if kind == "F":
            pnl = np.where(stopm, -(Sv + DESL + CUSTO), np.where(targm, Tv - CUSTO, eod_rel))
            code = np.where(stopm, 0, np.where(targm, 1, 2))
            exitk = np.where(stopm, ts, np.where(targm, tt, n - 1))
        else:
            Xa = np.broadcast_to(np.asarray(arm, float), (n,)) + (beyond_t if kind == "P" else 0.0)
            ta = first_idx(rhm >= Xa[:, None])
            loss1 = (ts <= ta) & (ts < BIG)
            armed = (ta < BIG) & ~loss1
            ta_e = np.where(armed & valid & filled, ta, BIG)
            rla = np.where(col > ta_e[:, None], rl, np.inf)
            tb = first_idx(rla <= 0.0)
            tg = armed & (tt < tb)
            be = armed & ~tg & (tb < BIG)
            half = 0.5 * (Tv / 2 - CUSTO) if kind == "P" else 0.0
            frac = 0.5 if kind == "P" else 1.0
            full_t = Tv - CUSTO if kind == "BE" else half + frac * (Tv - CUSTO)
            full_be = (-(DESL + CUSTO)) if kind == "BE" else half + frac * (-(DESL + CUSTO))
            full_eod_armed = eod_rel if kind == "BE" else half + frac * eod_rel
            stop1 = valid & filled & loss1
            pnl = np.where(stop1, -(Sv + DESL + CUSTO),
                  np.where(valid & filled & tg, full_t,
                  np.where(valid & filled & be, full_be,
                  np.where(valid & filled & armed, full_eod_armed, eod_rel))))
            code = np.where(stop1, 0, np.where(tg, 1, np.where(be, 3, 2)))
            exitk = np.where(stop1, ts, np.where(tg, tt, np.where(be, tb, n - 1)))
        res[key] = (valid & filled, valid, exitk, pnl, code)
    return f, filled, res


def trig_masks(d, avgr):
    n = len(d["c"]); m = d["m"]
    rng_ = d["h"] - d["l"]
    sigok = (m >= SIG_INI) & (m <= SIG_FIM) & (np.arange(n) + TTL + 1 < n)
    out = {"none": sigok.copy(), "h<11": sigok & (m < 660)}
    if avgr is None:
        for k in TRIGS[2:]:
            out[k] = np.zeros(n, bool)
        return out, None
    ar = avgr[m - MIN_INI]
    ratio = rng_ / ar
    v2x = sigok & np.isfinite(ratio) & (ratio >= 2.0)
    cs = np.concatenate([[0.0], np.cumsum(np.nan_to_num(rng_))])
    ca = np.concatenate([[0.0], np.cumsum(np.nan_to_num(ar))])
    idx = np.arange(n); lo_i = np.maximum(0, idx - 29)
    sr = cs[idx + 1] - cs[lo_i]; sa = ca[idx + 1] - ca[lo_i]
    with np.errstate(all="ignore"):
        w = sr / sa
    onda = sigok & (idx >= 14) & np.isfinite(w) & (w >= 1.5)
    out["v2x"] = v2x; out["onda"] = onda
    out["h<11&v2x"] = v2x & (m < 660); out["v2x&onda"] = v2x & onda
    return out, ar


COLL = []


def run_day(task):
    """task: dict(di, d, avgr, otim, shuffle_seed or None, full(bool), blocks(bool))."""
    d = task["d"]
    if task["shuffle_seed"] is not None:
        d = shuffle_day(d, np.random.default_rng(task["shuffle_seed"]))
    avgr = task["avgr"]; otim = task["otim"]; full = task["full"]
    o, h, l, c, m = d["o"], d["h"], d["l"], d["c"], d["m"]
    n = len(c)
    tm, ar = trig_masks(d, avgr)
    zz = zigzag_dir(o, h, l, c)
    candle = np.sign(c - o).astype(int)
    coin = np.where(np.random.default_rng(1000 + task["di"]).random(n) < 0.5, 1, -1)
    dirs = {"a_aleat": coin, "b_perna": zz, "c_vela": candle, "d_contra": -candle}
    # variantes
    variants = {}
    for (s, t) in PARES:
        variants[("F", s, t)] = (s, t, "F", None)
    if full:
        for (s, t) in PARES:
            variants[("BE", s, t, 1)] = (s, t, "BE", s)
            variants[("BE", s, t, 2)] = (s, t, "BE", 2 * s)
            variants[("P", s, t)] = (s, t, "P", t / 2.0)
    # vol-prop (stop = k*range medio do minuto, janela das proximas TTL velas)
    extra_rows = {}
    if full:
        idx = np.arange(n)
        ar_f = np.full(n, np.nan)
        for i in range(n if ar is not None else 0):
            seg = ar[i + 1:i + 1 + TTL]
            ar_f[i] = np.nanmean(seg) if len(seg) and np.isfinite(seg).any() else np.nan
        for kk in (0.3, 0.5):
            S = np.clip(np.round(kk * ar_f / 5) * 5, 50, 400)
            for R in (4, 7.5):
                variants[("V", kk, R)] = (S, S * R, "F", None)
    # stop tecnico (extremo das N ultimas velas, so se 50<=S<=400)
    tecs = {}
    if full:
        for N in (5, 15):
            lowN = pd.Series(l).rolling(N, min_periods=N).min().values
            highN = pd.Series(h).rolling(N, min_periods=N).max().values
            tecs[N] = (c - lowN + TICK, highN - c + TICK)   # long, short
    resdir = {}
    for sign in (1, -1):
        v = dict(variants)
        if full:
            for N in (5, 15):
                Sg = tecs[N][0] if sign == 1 else tecs[N][1]
                Sg = np.where((Sg >= 50) & (Sg <= 400), Sg, np.nan)
                for R in (4, 7.5):
                    v[("TC", N, R)] = (Sg, Sg * R, "F", None)
        if sign == 1:
            f, filled, r = sim_dir(l, h, c, v, otim, None)
        else:
            f, filled, r = sim_dir(-h, -l, -c, v, otim, None)
        resdir[sign] = (f, r)
    keys = list(resdir[1][1].keys())
    nseq = len(keys) * len(TRIGS) * len(DIRS)
    F = np.zeros((nseq, 11))
    blk_keys = [k for k in keys if k[0] == "F"]
    B = np.zeros((len(blk_keys) * len(TRIGS) * len(DIRS), NBLK, 7)) if task["blocks"] else None
    bidx = (m - MIN_INI) // 30
    sq = 0; bq = 0
    seqnames = []
    for key in keys:
        fL, rL = resdir[1][0], resdir[1][1][key]
        fS, rS = resdir[-1][0], resdir[-1][1][key]
        for tg in TRIGS:
            for dn in DIRS:
                seqnames.append((key, tg, dn))
                dd = dirs[dn]
                rows = np.nonzero(tm[tg] & (dd != 0))[0]
                if len(rows) == 0:
                    sq += 1
                    if B is not None and key[0] == "F": bq += 1
                    continue
                ds = dd[rows]
                lg = ds > 0
                vld = np.where(lg, rL[1][rows], rS[1][rows])
                fil = np.where(lg, rL[0][rows], rS[0][rows])
                ex = np.where(lg, rL[2][rows], rS[2][rows])
                pn = np.where(lg, rL[3][rows], rS[3][rows])
                cd = np.where(lg, rL[4][rows], rS[4][rows])
                ff = np.where(lg, fL[rows], fS[rows])
                keep = vld
                rows = rows[keep]; fil = fil[keep]; ex = ex[keep]; pn = pn[keep]; cd = cd[keep]; ff = ff[keep]
                rl_ = rows.tolist(); exl = ex.tolist(); fill_l = fil.tolist()
                picks = []; j = 0; nr = len(rl_)
                while j < nr:
                    picks.append(j)
                    i = rl_[j]
                    nxt = exl[j] if fill_l[j] else i + TTL
                    j = bisect.bisect_left(rl_, nxt, j + 1)
                if not picks:
                    sq += 1
                    if B is not None and key[0] == "F": bq += 1
                    continue
                pk = np.array(picks)
                if task.get("collect") == (key, tg, dn):
                    COLL.append((task["di"], rows[pk], fil[pk], pn[pk], cd[pk], ex[pk] - ff[pk]))
                F[sq, 0] = len(pk)
                fm = fil[pk]
                pp = pn[pk][fm]
                nf = len(pp)
                F[sq, 1] = nf
                if nf:
                    F[sq, 2] = pp.sum(); F[sq, 3] = (pp ** 2).sum(); F[sq, 4] = (pp > 0).sum()
                    F[sq, 5] = (cd[pk][fm] == 1).sum()
                    F[sq, 6] = pp[pp > 0].sum(); F[sq, 7] = -pp[pp < 0].sum()
                    loss = pp < 0
                    # corridas de perda
                    if loss.all():
                        F[sq, 8] = nf; F[sq, 9] = nf; F[sq, 10] = nf
                    else:
                        first_win = int(np.argmax(~loss)); last_win = nf - 1 - int(np.argmax(~loss[::-1]))
                        F[sq, 8] = first_win; F[sq, 9] = nf - 1 - last_win
                        # max run
                        padded = np.concatenate([[0], loss.astype(int), [0]])
                        dif = np.diff(padded)
                        st = np.nonzero(dif == 1)[0]; en = np.nonzero(dif == -1)[0]
                        F[sq, 10] = (en - st).max() if len(st) else 0
                if B is not None and key[0] == "F":
                    rr = rows[pk]; bb = bidx[rr]
                    fl = fm
                    pa = pn[pk]; ca_ = cd[pk]; dur = ex[pk] - ff[pk]
                    for b in np.unique(bb):
                        mk = bb == b
                        B[bq, b, 0] += mk.sum()
                        mf = mk & fl
                        B[bq, b, 1] += mf.sum()
                        B[bq, b, 2] += pa[mf].sum()
                        B[bq, b, 3] += (pa[mf] > 0).sum()
                        sm = mf & (ca_ == 0)
                        B[bq, b, 4] += sm.sum()
                        B[bq, b, 5] += (sm & (dur <= 1)).sum()
                        B[bq, b, 6] += (sm & (dur <= 5)).sum()
                sq += 1
                if B is not None and key[0] == "F": bq += 1
    return task["di"], seqnames, F, B
