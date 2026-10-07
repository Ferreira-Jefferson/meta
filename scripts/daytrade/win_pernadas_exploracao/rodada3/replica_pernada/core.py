"""Replicacao R13-R19,R25,R26 + base. Zigzag 750 sobre caminho da vela (alta min->max, baixa max->min), 4 pontos/vela encadeada.
Nulo: velas M1 embaralhadas dentro de blocos de 30 min de cada pregao (mesma permutacao aplicada ao WDO no R26)."""
import numpy as np, pandas as pd
WIN = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
WDO = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WDO@D_M1_202109290900_202609291020.csv"
T = 750.0
XS = (150, 250, 375, 500)

def ler(path, ini="2026-01-01", fim="2026-09-30"):
    d = pd.read_csv(path, sep="\t")
    d.columns = [c.strip("<>").lower() for c in d.columns]
    d = d[(d["date"] >= ini.replace("-", ".")) & (d["date"] <= fim.replace("-", "."))].copy()  # so 2026
    d["ts"] = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")
    return d.set_index("ts")[["open", "high", "low", "close", "vol"]].astype(float)

def caminho(o, h, l, c, order):
    """4 pontos por vela, encadeado (abre no fechamento anterior), barras na ordem `order`."""
    n = len(order); p = np.empty(4 * n); cur = o[0]
    for k in range(n):
        i = order[k]
        dh, dl, dc = h[i] - o[i], l[i] - o[i], c[i] - o[i]
        if c[i] >= o[i]: a, b = dl, dh
        else: a, b = dh, dl
        p[4*k] = cur; p[4*k+1] = cur + a; p[4*k+2] = cur + b; p[4*k+3] = cur + dc
        cur += dc
    return p

def ordem_embaralhada(mn, rng, bloco=30):
    blk = (mn - 540) // bloco
    out = np.arange(len(mn))
    for b in np.unique(blk):
        idx = np.where(blk == b)[0]; out[idx] = rng.permutation(idx)
    return out

def zigzag_eventos(p, thr=T, xs=XS):
    """Retorna legs(lista de (start_i, ext_i, dir, fechada)) e eventos
    (X, dir, A, i_evento, ext_i, start_i, y). Estado so com o passado; y olha o futuro."""
    n = len(p); legs = []; ev = []
    d = 0; hi = lo = p[0]; hi_i = lo_i = 0
    E = 0.0; E_i = 0; st_i = 0; pend = []; done = set()
    for i in range(1, n):
        x = p[i]
        if d == 0:
            if x > hi: hi, hi_i = x, i
            if x < lo: lo, lo_i = x, i
            if x >= lo + thr: d = 1; st_i = lo_i; E = x; E_i = i; done = set(); pend = []
            elif x <= hi - thr: d = -1; st_i = hi_i; E = x; E_i = i; done = set(); pend = []
            continue
        if d == 1:
            if x > E:
                for e in pend: e[6] = 0
                pend = []; E = x; E_i = i; done = set()
            elif E - x >= thr:
                for e in pend: e[6] = 1
                pend = []
                legs.append((st_i, E_i, 1, 1)); st_i = E_i; d = -1; E = x; E_i = i; done = set(); continue
        else:
            if x < E:
                for e in pend: e[6] = 0
                pend = []; E = x; E_i = i; done = set()
            elif x - E >= thr:
                for e in pend: e[6] = 1
                pend = []
                legs.append((st_i, E_i, -1, 1)); st_i = E_i; d = 1; E = x; E_i = i; done = set(); continue
        rec = abs(E - x)
        if rec > 0:
            A = abs(E - p[st_i])
            if A >= thr:
                for X in xs:
                    if X not in done and rec >= X:
                        done.add(X)
                        e = [X, d, A, i, E_i, st_i, np.nan]; ev.append(e); pend.append(e)
    legs.append((st_i, E_i, d, 0)) if d != 0 else None
    return legs, ev

def metricas_perna(p, st_i, E_i):
    seg = p[st_i:E_i + 1]
    s = seg[0]
    adv = np.abs(seg - s)
    sg = 1 if seg[-1] >= s else -1
    run = np.maximum.accumulate(sg * (seg - s))     # avanco corrente
    dd = run - sg * (seg - s)
    maxcorr = float(dd.max())
    # contagem de correcoes: recuo >= max(50, 30% do avanco corrente) do extremo corrente; 1 por extremo
    nc = 0; armed = True; best = 0.0
    for r, q in zip(run, sg * (seg - s)):
        if r > best: best = r; armed = True
        if armed and r > 0 and (r - q) >= max(50.0, 0.3 * r):
            nc += 1; armed = False
    return maxcorr, nc

def analisa_caminho(p, mn, dW_perm_cum):
    """legs (array) e eventos (array) de um caminho. mn = minuto do dia por vela (slot). dW_perm_cum = cumsum dos retornos WDO por vela (ou None)."""
    legs, ev = zigzag_eventos(p)
    L = []
    for k, (a, b, d, fe) in enumerate(legs):
        size = abs(p[b] - p[a]); dur = max((b - a) / 4.0, 1.0)
        mc, nc = (np.nan, np.nan)
        if fe: mc, nc = metricas_perna(p, a, b)
        opp = np.nan
        if dW_perm_cum is not None and fe:
            disp = dW_perm_cum[b // 4] - dW_perm_cum[a // 4]
            opp = np.nan if disp == 0 else float(np.sign(disp) != d)
        L.append((d, size, dur, size / dur, mc, nc, mn[min(a // 4, len(mn)-1)], fe, opp, a, b, k == 0))
    return np.array(L, dtype=float).reshape(-1, 12), np.array(ev, dtype=float).reshape(-1, 7)
