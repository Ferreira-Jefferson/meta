"""Rodada 5 / tendencia: dados, features de tendencia (causais), simulador de pullback com limite."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada4/decisao")
from motor import dst_eua

CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
TICK, CUSTO, DESL = 5.0, 2.0, 5.0
ENTRY_LO, ENTRY_HI = 9 * 60 + 15, 16 * 60 + 30
TTL = 10
SCALES = ["d_ma10", "d_ma20", "d_slope", "d_seq", "d_wkprev", "d_wkcur", "i_open", "i_vwap",
          "i_leg", "i_m15", "i_h1", "conc3", "conc5"]


def carrega():
    """Le o CSV mantendo SO dez/2025 (aquecimento de indicador) a set/2026. Nada antes de 2025.12.01 e' usado."""
    ch = []
    for c in pd.read_csv(CSV, sep="\t", chunksize=200000):
        c.columns = ["d", "t", "o", "h", "l", "c", "tv", "v", "sp"]
        c = c[(c.d >= "2025.12.01") & (c.d < "2026.10.01")]
        ch.append(c)
    d = pd.concat(ch, ignore_index=True)
    d["date"] = pd.to_datetime(d.d, format="%Y.%m.%d")
    d["min"] = d.t.str[:2].astype(int) * 60 + d.t.str[3:5].astype(int)
    n = d.groupby("d")["d"].transform("size")
    d = d[n > 400].reset_index(drop=True)
    return d


def zigzag(d, thr=750.0):
    st = np.zeros(len(d), np.int8)
    o, h, l, c, day = d.o.values, d.h.values, d.l.values, d.c.values, d.d.values
    state = 0; ehi = elo = None; prev = None
    for i in range(len(d)):
        if day[i] != prev:
            prev = day[i]; state = 0; ehi = h[i]; elo = l[i]
        pts = (l[i], h[i]) if c[i] >= o[i] else (h[i], l[i])
        for p in pts:
            if state == 0:
                ehi = max(ehi, p); elo = min(elo, p)
                if p - elo >= thr and p >= ehi:
                    state = 1; ehi = p
                elif ehi - p >= thr and p <= elo:
                    state = -1; elo = p
            elif state == 1:
                ehi = max(ehi, p)
                if ehi - p >= thr:
                    state = -1; elo = p
            else:
                elo = min(elo, p)
                if p - elo >= thr:
                    state = 1; ehi = p
        st[i] = state
    return st


def sinal_ema_slope(d, minutos, span=20):
    key = d.d + "_" + ((d["min"] - 540) // minutos).astype(str)
    last = ~key.duplicated(keep="last")
    cl = d.c[last]
    ema = cl.ewm(span=span, adjust=False).mean()
    sg = np.sign(ema - ema.shift(2)).fillna(0)
    out = pd.Series(np.nan, index=d.index)
    out[sg.index] = sg.values
    return out.ffill().fillna(0).values.astype(np.int8)


def features(d):
    """dict nome -> int8 {-1,0,1} conhecido no FECHAMENTO de cada barra M1."""
    days = d.d.unique()
    di = pd.Series(range(len(days)), index=days)
    didx = d.d.map(di).values
    g = d.groupby("d", sort=False)
    dclose = g.c.last().values; dopen = g.o.first().values
    dser = pd.Series(dclose)
    F = {}
    prevc = np.concatenate([[np.nan], dclose[:-1]])
    for k in (10, 20):
        sma = dser.rolling(k).mean().values
        smap = np.concatenate([[np.nan], sma[:-1]])
        F[f"d_ma{k}"] = np.sign(prevc - smap)[didx]
        if k == 10:
            sl = smap - np.concatenate([[np.nan] * 3, smap[:-3]])
            F["d_slope"] = np.sign(sl)[didx]
    c1 = prevc; c2 = np.concatenate([[np.nan] * 2, dclose[:-2]])
    c3 = np.concatenate([[np.nan] * 3, dclose[:-3]])
    seq = np.where((c1 > c2) & (c2 > c3), 1.0, np.where((c1 < c2) & (c2 < c3), -1.0, 0.0))
    seq[np.isnan(c3)] = 0
    F["d_seq"] = seq[didx]
    dts = pd.to_datetime(days, format="%Y.%m.%d")
    iso = dts.isocalendar()
    wk = (iso.year * 100 + iso.week).values
    wser = pd.DataFrame({"wk": wk, "o": dopen, "c": dclose})
    wo = wser.groupby("wk").o.first(); wc = wser.groupby("wk").c.last()
    wkeys = list(wo.index)
    prevwk = {wkeys[i]: (np.sign(wc.iloc[i - 1] - wo.iloc[i - 1]) if i > 0 else 0.0) for i in range(len(wkeys))}
    F["d_wkprev"] = np.array([prevwk[w] for w in wk])[didx]
    wk_open_day = np.array([wo[w] for w in wk])[didx]
    F["d_wkcur"] = np.sign(d.c.values - wk_open_day)
    dayopen = d.o.groupby(d.d).transform("first").values
    F["i_open"] = np.sign(d.c.values - dayopen)
    tp = (d.h + d.l + d.c) / 3 * d.v
    vw = tp.groupby(d.d).cumsum() / d.v.groupby(d.d).cumsum()
    F["i_vwap"] = np.sign(d.c.values - vw.values)
    F["i_leg"] = zigzag(d)
    F["i_m15"] = sinal_ema_slope(d, 15)
    F["i_h1"] = sinal_ema_slope(d, 60)
    F = {k: np.nan_to_num(np.asarray(v, float)).astype(np.int8) for k, v in F.items()}
    s3 = np.stack([F["d_ma20"], F["i_open"], F["i_vwap"]])
    F["conc3"] = np.where((s3 == s3[0]).all(0), s3[0], 0).astype(np.int8)
    s5 = np.stack([F["d_ma20"], F["i_open"], F["i_vwap"], F["i_m15"], F["i_h1"]])
    F["conc5"] = np.where((s5 == s5[0]).all(0), s5[0], 0).astype(np.int8)
    return F, didx


def filtros(d):
    """cedo: antes das 11:00 (12:00 fora do horario de verao dos EUA, R28). vela: alguma M1 com range >= 2x a media
    do mesmo minuto nos 20 pregoes anteriores, nos ultimos 15 min."""
    dst = d.date.dt.date.map(dst_eua).values
    lim = np.where(dst, 11 * 60, 12 * 60)
    cedo = d["min"].values < lim
    rg = (d.h - d.l)
    mm = rg.groupby(d["min"]).transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
    big = (rg >= 2 * mm).fillna(False).values.astype(float)
    vela = pd.Series(big).groupby(d.d.values).transform(lambda s: s.rolling(15, min_periods=1).max()).values > 0
    return {"todos": np.ones(len(d), bool), "cedo": cedo, "vela": vela}


def dias_slices(d):
    days = d.d.values
    ch = np.flatnonzero(days[1:] != days[:-1]) + 1
    st = np.concatenate([[0], ch]); en = np.concatenate([ch, [len(d)]])
    return list(zip(st, en))


def ema_arr(c, span=60):
    return pd.Series(c).ewm(span=span, adjust=False).mean().values


def sim_dia(h, l, c, mn, s, hh, ll, ema, allow, X, stop, alvo, cons):
    """Um pregao. -> (lista (barra_entrada, pnl, tipo), n_ordens). tipo 1 ganho, 0 perda, 2 nao resolveu.
    X: pts de recuo do extremo do dia, ou None = media (EMA60 M1). Entrada e alvo por limite (cons: precisa
    passar 1 tick alem), stop a mercado com deslize, empate na barra = stop."""
    n = len(c); tr = []; orders = 0
    off = TICK if cons else 0.0
    i = 0
    ref_l = ref_s = None   # uma tentativa por novo extremo: depois de uma operacao, so rearma com extremo novo
    while i < n - 2 and mn[i] < ENTRY_LO:
        i += 1
    while i < n - 2:
        if mn[i] > ENTRY_HI:
            break
        d = s[i]
        if d == 0 or not allow[i]:
            i += 1; continue
        if (d > 0 and ref_l is not None and hh[i] <= ref_l) or (d < 0 and ref_s is not None and ll[i] >= ref_s):
            i += 1; continue
        if d > 0:
            L = min((hh[i] - X) if X is not None else ema[i], c[i] - TICK)
        else:
            L = max((ll[i] + X) if X is not None else ema[i], c[i] + TICK)
        L = round(L / TICK) * TICK
        orders += 1
        end = min(i + TTL, n - 1)
        bad = np.flatnonzero(s[i + 1:end + 1] != d)
        if len(bad):
            end = i + 1 + int(bad[0])
        if d > 0:
            hit = np.flatnonzero(l[i + 1:end + 1] <= L - off)
        else:
            hit = np.flatnonzero(h[i + 1:end + 1] >= L + off)
        if not len(hit):
            i = end if end > i else i + 1
            continue
        j = i + 1 + int(hit[0])
        if d > 0:
            ref_l = hh[i]
        else:
            ref_s = ll[i]
        if d > 0:
            S, T = L - stop, L + alvo
            si = np.flatnonzero(l[j:] <= S); ti = np.flatnonzero(h[j:] >= T + off)
        else:
            S, T = L + stop, L - alvo
            si = np.flatnonzero(h[j:] >= S); ti = np.flatnonzero(l[j:] <= T - off)
        sx = si[0] if len(si) else 10**9; tx = ti[0] if len(ti) else 10**9
        if sx == 10**9 and tx == 10**9:
            tr.append((j, d * (c[-1] - L) - CUSTO, 2)); break
        if sx <= tx:
            tr.append((j, -(stop + DESL + CUSTO), 0)); i = j + sx
        else:
            tr.append((j, alvo - CUSTO, 1)); i = j + tx
    return tr, orders
