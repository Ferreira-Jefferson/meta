"""Composicao de velas (cor/corpo/volume) em M1/M5/M15 -> direcao da proxima pernada. Somente 2026."""
import numpy as np, pandas as pd
WIN = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
G = 540  # grade 09:00-18:00 em minutos

def ler():
    d = pd.read_csv(WIN, sep="\t")
    d.columns = [c.strip("<>").lower() for c in d.columns]
    d = d[(d["date"] >= "2026.01.01") & (d["date"] <= "2026.09.30")].copy()
    d["ts"] = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")
    d["mn"] = d.ts.dt.hour * 60 + d.ts.dt.minute - 540
    days = {}
    for k, g in d.groupby(d.ts.dt.date):
        g = g[(g.mn >= 0) & (g.mn < G)]
        if len(g) < 200: continue
        days[str(k)] = (g.mn.values.astype(int), g.open.values, g.high.values, g.low.values, g.close.values, g.vol.values.astype(float))
    return days

def embaralha(day, rng):
    mn, o, h, l, c, v = day
    blk = mn // 30; out = np.arange(len(mn))
    for b in np.unique(blk):
        idx = np.where(blk == b)[0]; out[idx] = rng.permutation(idx)
    dh, dl, dc = (h - o)[out], (l - o)[out], (c - o)[out]
    cl = o[0] + np.cumsum(dc); op = np.concatenate([[o[0]], cl[:-1]])
    return mn, op, op + dh, op + dl, cl, v[out]

def grade(mn, o, h, l, c, v, tf):
    """candles do timeframe tf (min) numa grade completa; vazias = valid False."""
    nb = G // tf; b = mn // tf
    O = np.zeros(nb); H = np.full(nb, -np.inf); L = np.full(nb, np.inf); C = np.zeros(nb); V = np.zeros(nb); ok = np.zeros(nb, bool)
    first = {}
    for i in range(len(mn)):
        j = b[i]
        if not ok[j]: O[j] = o[i]; ok[j] = True
        C[j] = c[i]; H[j] = max(H[j], h[i]); L[j] = min(L[j], l[i]); V[j] += v[i]
    H[~ok] = 0; L[~ok] = 0
    return O, H, L, C, V, ok

def cs(x): return np.concatenate([[0.0], np.cumsum(x)])

def feats_tf(O, H, L, C, V, ok, js, k):
    """6 features na janela de k candles terminando em cada j de js (candle completo)."""
    body = np.where(ok, C - O, 0.0); rng = np.where(ok, H - L, 0.0)
    sg = np.sign(body); up = (sg > 0).astype(float); dn = (sg < 0).astype(float)
    cpos = np.where(rng > 0, (C - L) / np.where(rng > 0, rng, 1) - 0.5, 0.0)
    a, b = js - k + 1, js + 1
    def w(x): s = cs(x); return s[b] - s[a]
    nv = w(ok.astype(float))
    with np.errstate(all="ignore"):
        f = {"frac": (w(up) - w(dn)) / nv, "corpo": w(body) / w(np.abs(body)), "vol": w(V * sg) / w(V),
             "cpos": w(cpos) / nv, "sal": w(body) / w(rng)}
        Cf = pd.Series(np.where(ok, C, np.nan)).ffill().values
        Of = pd.Series(np.where(ok, O, np.nan)).bfill().values
        f["net"] = (Cf[js] - Of[a]) / w(rng)
    for key in f: f[key] = np.where(a >= 0, f[key], np.nan)
    return f

WIN_SPEC = {1: (10, 20, 30, 60), 5: (6, 12, 24), 15: (4, 8)}
KEYS = ["frac", "corpo", "vol", "cpos", "sal", "net"]

def tabela_dia(day, bound_thr=(250, 750)):
    mn, o, h, l, c, v = day
    gs = {tf: grade(mn, o, h, l, c, v, tf) for tf in (1, 5, 15)}
    # amostras: fim de M15, 09:30..16:45
    samp = np.array([m for m in range(29, 466, 15)])  # minuto-da-grade do fim do candle M1 (09:29 + ...): 09:30 e' fim do candle 09:29
    samp = np.array([m for m in range(14, 466, 15) if m >= 29])
    cols = {}
    for tf, ks in WIN_SPEC.items():
        js = samp // tf
        for k in ks:
            f = feats_tf(*gs[tf], js, k)
            for key in KEYS: cols[f"{key}_{tf}m_{k}"] = f[key]
    F = lambda n: cols[n]
    cols["x_1m60_15m4"] = F("frac_1m_60") - F("frac_15m_4")
    cols["x_1m30_5m6"] = F("frac_1m_30") - F("frac_5m_6")
    cols["x_5m12_15m4"] = F("frac_5m_12") - F("frac_15m_4")
    cols["xc_1m60_15m4"] = F("corpo_1m_60") - F("corpo_15m_4")
    # picos: vol/range de M1 que nao aparece em M5 (e vice-versa); sinal = cor da vela do pico
    O1, H1, L1, C1, V1, ok1 = gs[1]; O5, H5, L5, C5, V5, ok5 = gs[5]
    sp = {n: np.zeros(len(samp)) for n in ("p_m1vol", "p_m5vol", "p_m1rng", "p_m5rng")}
    R1 = np.where(ok1, H1 - L1, 0.0); R5 = np.where(ok5, H5 - L5, 0.0)
    for q, m in enumerate(samp):
        if m < 60: continue
        w1 = slice(m - 29, m + 1); b5 = m // 5
        # M1 pico nos ultimos 5 min vs mediana dos 30 min anteriores
        for nm, A1, A5 in (("vol", V1, V5), ("rng", R1, R5)):
            med1 = np.median(A1[m - 34:m - 4][ok1[m - 34:m - 4]]) if ok1[m - 34:m - 4].any() else np.nan
            j = m - 4 + int(np.argmax(A1[m - 4:m + 1])); r1 = A1[j] / med1 if med1 > 0 else 0
            sg1 = np.sign(C1[j] - O1[j])
            med5 = np.median(A5[b5 - 12:b5][ok5[b5 - 12:b5]]) if ok5[b5 - 12:b5].any() and b5 >= 12 else np.nan
            r5 = A5[b5] / med5 if med5 > 0 else 0
            sg5 = np.sign(C5[b5] - O5[b5])
            if r1 > 4 and r5 < 1.5: sp[f"p_m1{nm}"][q] = sg1
            if r5 > 2.5 and r1 < 4: sp[f"p_m5{nm}"][q] = sg5
    cols.update(sp)
    # lateral: |net60| / range60 baixo
    hh = np.array([h[(mn > m - 60) & (mn <= m)].max() if ((mn > m - 60) & (mn <= m)).any() else np.nan for m in samp])
    ll = np.array([l[(mn > m - 60) & (mn <= m)].min() if ((mn > m - 60) & (mn <= m)).any() else np.nan for m in samp])
    Cf = pd.Series(np.where(ok1, C1, np.nan)).ffill().values
    net60 = np.abs(Cf[samp] - Cf[np.maximum(samp - 60, 0)]) / (hh - ll)
    cols["_lat"] = np.where(samp >= 60, (net60 < 0.25).astype(float), np.nan)
    # resultados (prox. 30/60 min; primeira barreira +-250/750)
    P = Cf[samp]
    def ret(dm):
        t = np.minimum(samp + dm, G - 1)
        r = Cf[t] - P; return np.where(samp + dm < 440, r, np.nan)  # exige horario ate 17:20
    cols["_r30"] = ret(30); cols["_r60"] = ret(60)
    for X in bound_thr:
        out = np.full(len(samp), np.nan)
        for q, m in enumerate(samp):
            fm = mn > m
            if not fm.any(): continue
            hu = np.where(h[fm] - P[q] >= X)[0]; hd = np.where(P[q] - l[fm] <= -X + 0)[0]
            hd = np.where(P[q] - l[fm] >= X)[0]
            iu = hu[0] if len(hu) else 10**9; idn = hd[0] if len(hd) else 10**9
            if iu == idn: continue
            out[q] = 1.0 if iu < idn else 0.0
        cols[f"_h{X}"] = out
    t = pd.DataFrame(cols); t["mn"] = samp
    t["bucket"] = np.where(samp < 120, 0, np.where(samp < 300, 1, 2))
    return t

def tudo(days, sim=None, seed=0):
    rng = np.random.default_rng(seed * 100003 + 7) if sim is not None else None
    ts = []
    for dstr, day in days.items():
        d = embaralha(day, rng) if sim is not None else day
        t = tabela_dia(d); t["dia"] = dstr; ts.append(t)
    return pd.concat(ts, ignore_index=True)
