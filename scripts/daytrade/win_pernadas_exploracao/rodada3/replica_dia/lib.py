"""Replicacao jan-ago/2026 das regras de dia do WIN (R01-R12, R20-R24). Definicoes congeladas.
Dados: WIN@D M1 (ajuste por diferenca), SOMENTE 2026 (+ fechamento de 30/12/2025 para o gap de 02/01)."""
import numpy as np, pandas as pd

CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
MESES = ["2026-%02d" % m for m in range(1, 10)]
CUTS = list(range(630, 961, 5))          # 10:30 .. 16:00 (67 cortes) em minutos do dia


# ------------------------------------------------------------------ dados
def carregar():
    """Le o CSV em fluxo; descarta tudo antes de 2025.12.30 sem parsear (so 30/12/2025 vira prev-close)."""
    linhas = []
    with open(CSV, "r", encoding="utf-8") as f:
        f.readline()
        for ln in f:
            d = ln[:10]
            if d < "2025.12.30" or d > "2026.09.30":
                continue
            linhas.append(ln.rstrip("\n").split("\t"))
    df = pd.DataFrame(linhas, columns=["date", "time", "open", "high", "low", "close", "tickvol", "vol", "spread"])
    for c in ["open", "high", "low", "close", "vol"]:
        df[c] = df[c].astype(float)
    df["mn"] = df.time.str[:2].astype(int) * 60 + df.time.str[3:5].astype(int)
    days, pc, excl = [], None, []
    for date, g in df.groupby("date", sort=True):
        g = g.sort_values("mn")
        if date == "2025.12.30":
            pc = g.close.iloc[-1]
            continue
        d = dict(date=date.replace(".", "-"), ym=date[:4] + "-" + date[5:7], mn=g.mn.values.astype(int),
                 o=g.open.values, h=g.high.values, l=g.low.values, c=g.close.values, v=g.vol.values, pc=pc)
        pc = g.close.iloc[-1]                      # o prev-close segue a cadeia mesmo de dia parcial
        if g.mn.iloc[0] > 550 or len(g) < 500:     # pregao parcial (abre tarde / poucas barras)
            excl.append((d["date"], int(g.mn.iloc[0]), len(g)))
            continue
        days.append(d)
    return days, excl


# ------------------------------------------------------------------ embaralhos
def shuf_bloco(d, rng, bloco=30):
    """Embaralha (forma, retorno) das velas dentro de blocos de 30 min; gaps entre velas ficam na posicao."""
    mn = d["mn"]; n = len(mn)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    g = np.empty(n); g[0] = 0.0; g[1:] = o[1:] - c[:-1]
    dh, dl, dc = h - o, l - o, c - o
    blk = (mn - 540) // bloco
    perm = np.arange(n)
    for b in np.unique(blk):
        ix = np.flatnonzero(blk == b)
        perm[ix] = rng.permutation(ix)
    dh, dl, dc = dh[perm], dl[perm], dc[perm]
    cc = o[0] + np.cumsum(g + dc)
    oo = np.empty(n); oo[0] = o[0]; oo[1:] = cc[:-1] + g[1:]
    r = dict(d); r.update(o=oo, h=oo + dh, l=oo + dl, c=cc)
    return r


def shuf_xdia(d, fontes, rng, bloco=30):
    """Cada bloco de 30 min do dia vem de um dia sorteado (mesmo horario): preserva o relogio de volatilidade,
    destroi a estrutura do dia. Parte do open real do dia."""
    P = d["o"][0]
    mn_l, o_l, h_l, l_l, c_l = [], [], [], [], []
    for b in range(0, 19):
        lo, hi = 540 + b * bloco, 540 + (b + 1) * bloco
        s = None
        for _ in range(8):
            s0 = fontes[rng.integers(len(fontes))]
            ix = np.flatnonzero((s0["mn"] >= lo) & (s0["mn"] < hi))
            if len(ix):
                s = s0; break
        if s is None:
            continue
        o0 = s["o"][ix[0]]
        mn_l.append(s["mn"][ix]); o_l.append(P + s["o"][ix] - o0); h_l.append(P + s["h"][ix] - o0)
        l_l.append(P + s["l"][ix] - o0); c_l.append(P + s["c"][ix] - o0)
        P = P + s["c"][ix[-1]] - o0
    r = dict(d)
    n = sum(len(x) for x in mn_l)
    r.update(mn=np.concatenate(mn_l), o=np.concatenate(o_l), h=np.concatenate(h_l), l=np.concatenate(l_l),
             c=np.concatenate(c_l), v=np.ones(n))
    return r


# ------------------------------------------------------------------ caminhos / zigzag
def reamostra(d, k):
    mn = d["mn"]; b = mn // k
    ini = np.r_[0, np.flatnonzero(np.diff(b)) + 1]
    fim = np.r_[ini[1:], len(mn)] - 1
    o = d["o"][ini]; c = d["c"][fim]
    h = np.maximum.reduceat(d["h"], ini); l = np.minimum.reduceat(d["l"], ini)
    return o, h, l, c, (b[ini] * k)


def caminho(o, h, l, c, t, com_open_close=False):
    up = c >= o
    e1 = np.where(up, l, h); e2 = np.where(up, h, l)
    if com_open_close:
        p = np.stack([o, e1, e2, c], 1).ravel(); tt = np.repeat(t, 4)
    else:
        p = np.stack([e1, e2], 1).ravel(); tt = np.repeat(t, 2)
    return p, tt


def zigzag(p, thr):
    n = len(p); lo = hi = 0; d = 0
    for i in range(n):
        if p[i] > p[hi]: hi = i
        if p[i] < p[lo]: lo = i
        if p[i] - p[lo] >= thr: d = 1; start = lo; ext = i; break
        if p[hi] - p[i] >= thr: d = -1; start = hi; ext = i; break
    if d == 0: return []
    legs = []
    for i in range(ext + 1, n):
        if d == 1:
            if p[i] > p[ext]: ext = i
            elif p[ext] - p[i] >= thr:
                legs.append((start, ext, 1, i)); start = ext; d = -1; ext = i
        else:
            if p[i] < p[ext]: ext = i
            elif p[i] - p[ext] >= thr:
                legs.append((start, ext, -1, i)); start = ext; d = 1; ext = i
    legs.append((start, ext, d, None))
    return legs


class ZZ:
    """Zigzag causal de limiar T (kit_pernadas._ZZ), so o necessario para o 'balanco'."""
    def __init__(s, T):
        s.T = T; s.dir = 0; s.hi = s.lo = None; s.piv = None; s.n_piv = 0; s.E = None

    def passo(s, t, p):
        T = s.T
        if s.dir == 0:
            if s.hi is None:
                s.hi = s.lo = p; s.E = p; return
            if p > s.hi: s.hi = p
            if p < s.lo: s.lo = p
            if p >= s.lo + T: s.piv = s.lo; s.dir = 1; s.E = p; s.n_piv = 1
            elif p <= s.hi - T: s.piv = s.hi; s.dir = -1; s.E = p; s.n_piv = 1
            return
        if s.dir == 1:
            if p > s.E: s.E = p
            elif p <= s.E - T: s.piv = s.E; s.dir = -1; s.E = p; s.n_piv += 1
        else:
            if p < s.E: s.E = p
            elif p >= s.E + T: s.piv = s.E; s.dir = 1; s.E = p; s.n_piv += 1


# ------------------------------------------------------------------ campos por dia: familia "caminho"
def balanco(p, t, X=250, Tmin=100.0, T=750.0):
    """Eventos 'ja andou X do ultimo pivo (zigzag 100)', 1x por pivo; y=1 se chega a 750 do pivo antes de
    recuar 100 do extremo (kit_pernadas.eventos_balanco + rotular). Retorna lista (mn_do_ponto, y)."""
    zz = ZZ(Tmin); feitos = False; chave = None; out = []
    for k in range(len(p)):
        zz.passo(t[k], p[k])
        if zz.dir == 0: continue
        ch = (zz.piv, zz.n_piv)
        if ch != chave: feitos = False; chave = ch
        if feitos or abs(p[k] - zz.piv) < X: continue
        feitos = True
        y = np.nan; ext = p[k]
        for q in p[k + 1:]:
            ext = max(ext, q) if zz.dir == 1 else min(ext, q)
            if abs(ext - zz.piv) >= T: y = 1; break
            if abs(ext - q) >= Tmin: y = 0; break
        out.append((t[k], y))
    return out


def extremo500(p, t, X=500, D=750):
    """transicoes/an.py: zigzag 750 no caminho M1 (4 pontos/vela); recuo de X do maximo corrente da perna;
    y=1 se o recuo chega a D antes de nova maxima. So A>=750 (alta acumulada). Retorna (mn, y)."""
    out = []
    legs = zigzag(p, 750); n = len(p)
    for (s, e, d, c) in legs:
        end = c if c is not None else n - 1
        q = p * d; H = q[s]; fired = False
        for i in range(s + 1, end + 1):
            if q[i] > H: H = q[i]; fired = False; continue
            if fired or H - q[i] < X: continue
            fired = True
            if H - q[s] < 750: continue
            fut = q[i + 1:]
            up = np.flatnonzero(fut > H); ui = up[0] if len(up) else 10 ** 9
            dn = np.flatnonzero(fut <= H - D); dj = dn[0] if len(dn) else 10 ** 9
            y = 1 if dj < ui else (0 if ui < 10 ** 9 else -1)
            if y >= 0: out.append((t[i], y))
    return out


def legs_m5(d):
    """R23: pernadas zigzag 750 em M5. Retorna lista (mn_inicio, tamanho, dur_min, n_correcoes)."""
    o, h, l, c, t = reamostra(d, 5)
    p, tt = caminho(o, h, l, c, t)
    out = []
    for (s, e, dr, cf) in zigzag(p, 750):
        size = abs(p[e] - p[s]); dur = max(tt[e] - tt[s], 5)
        q = p[s:e + 1] * dr; E = q[0]; ncorr = 0; em = False
        for x in q[1:]:
            if x > E:
                if em: ncorr += 1; em = False
                E = x
            elif E - x >= 5: em = True
        out.append((int(tt[s]), float(size), float(dur), ncorr))
    return out


def campos_caminho(d):
    mn = d["mn"]
    o5, h5, l5, c5, t5 = reamostra(d, 5)
    p5, tt5 = caminho(o5, h5, l5, c5, t5)
    ev = balanco(p5, tt5)
    on = [(1 if y == 1 else 0) for (m, y) in ev if m < 660 and y == y]
    of = [(1 if y == 1 else 0) for (m, y) in ev if m >= 660 and y == y]
    ate = [(1 if y == 1 else 0) for (m, y) in ev if m < 780 and y == y]
    tar = [(1 if y == 1 else 0) for (m, y) in ev if m >= 780 and y == y]
    f = {}
    f["r01_on"] = (sum(on), len(on)); f["r01_off"] = (sum(of), len(of))
    f["r02"] = (sum(on), sum(on) + sum(of), int((mn < 660).sum()), len(mn))
    f["r03_tarde"] = (sum(tar), len(tar)); f["r03_ate13"] = (sum(ate), len(ate))
    p1, t1 = caminho(d["o"], d["h"], d["l"], d["c"], mn, com_open_close=True)
    e4 = extremo500(p1, t1)
    a = [y for (m, y) in e4 if m >= 780]; b = [y for (m, y) in e4 if m < 780]
    f["r04_tarde"] = (sum(a), len(a)); f["r04_manha"] = (sum(b), len(b))
    # R11: extremos do dia nas 2 primeiras pernadas H1
    oh, hh, lh, ch, th = reamostra(d, 60)
    ph, _ = caminho(oh, hh, lh, ch, th)
    legs = zigzag(ph, 750)
    fim2 = legs[1][1] if len(legs) >= 2 else len(ph)
    imax, imin = int(np.argmax(ph)), int(np.argmin(ph))
    f["r11"] = (int(imax <= fim2 or imin <= fim2), int(imax <= fim2 and imin <= fim2))
    f["r12"] = (int(mn[np.argmax(d["h"])]), int(mn[np.argmin(d["l"])]))
    f["r23"] = legs_m5(d)
    return f


# ------------------------------------------------------------------ campos por dia: familia "outras"
def grade(d, H=60):
    mn = d["mn"]; o0 = d["o"][0]; pc = d["pc"]
    tp = (d["h"] + d["l"] + d["c"]) / 3; cv = np.cumsum(d["v"]); vw = np.cumsum(tp * d["v"]) / cv
    res = {"dv": [0] * 6, "do": [0] * 6, "dp": [0] * 6}  # (k,n) x early,in,late
    for tmin in range(570, 961, 15):
        i = np.searchsorted(mn, tmin)          # barras antes de t
        if i < 5: continue
        j = np.searchsorted(mn, tmin + H)
        if j - i < H - 3: continue
        px = d["c"][i - 1]; fwd = d["c"][j - 1] - px
        bl = 0 if tmin < 630 else (1 if tmin < 750 else 2)
        for nm, x in (("dv", px - vw[i - 1]), ("do", px - o0), ("dp", px - pc)):
            if abs(x) > 500:
                res[nm][2 * bl + 1] += 1
                if np.sign(x) != np.sign(fwd): res[nm][2 * bl] += 1
    return res


def campos_outras(d):
    mn = d["mn"]; o0 = d["o"][0]; pc = d["pc"]; fin = d["c"][-1]
    f = {}
    # R05 (a2.py): T=10:30; vwap ponderada por close*vol
    i = np.searchsorted(mn, 630); px = d["c"][i - 1]
    vw = (d["c"][:i] * d["v"][:i]).sum() / d["v"][:i].sum()
    sc = np.sign(px - o0) + np.sign(px - vw) + np.sign(px - pc)
    rem = fin - px
    if abs(sc) == 3:
        f["r05"] = (int(np.sign(sc) != np.sign(rem)), 1, float(np.sign(sc) * rem))
    else:
        f["r05"] = (0, 0, np.nan)
    f["r05_dir"] = (int(np.sign(px - o0) * rem < 0), 1)
    f["grade"] = grade(d)
    gap = o0 - pc
    if gap != 0:
        fill = (d["l"].min() <= pc) if gap > 0 else (d["h"].max() >= pc)
        mir = (d["h"].max() >= o0 + gap) if gap > 0 else (d["l"].min() <= o0 + gap)
        f["r09"] = (int(fill), int(mir), 1)
        f["r10"] = (int((fin - o0) * gap < 0), int((fin - pc) * gap < 0), 1)
    else:
        f["r09"] = (0, 0, 0); f["r10"] = (0, 0, 0)
    # R20 (blocos de 15 min, 37 por dia)
    L = np.full(37, np.nan)
    b = (mn - 540) // 15
    for k in np.unique(b):
        if k < 37:
            m = b == k
            L[k] = np.log(d["h"][m].max() - d["l"][m].min() + 1e-9)
    f["r20"] = L
    # R21 (minutos 10h-17h sem 10:30-10:32): razao faixa/media da hora
    rng = np.full(1200, np.nan); rng[mn] = d["h"] - d["l"]
    rows = []
    for hr in range(10, 17):
        x = rng[hr * 60:(hr + 1) * 60].copy()
        if hr == 10: x[30:33] = np.nan
        rows.append(x / np.nanmean(x))
    f["r21"] = np.array(rows)
    # R22: retornos M1 (cadeia dos closes)
    r1 = np.empty(len(mn)); r1[0] = d["c"][0] - d["o"][0]; r1[1:] = np.diff(d["c"])
    f["r22_r"] = r1
    f["r22_ok"] = janelas5(mn)
    f["r22_in"] = (mn >= 540) & (mn < 600)
    # R24: razao amplitude e volume 15 min depois / 15 antes, para cada corte
    vol = np.full(1200, np.nan); vol[mn] = d["v"]
    A = np.empty(len(CUTS)); V = np.empty(len(CUTS))
    for k, c in enumerate(CUTS):
        A[k] = np.nanmean(rng[c:c + 15]) / np.nanmean(rng[c - 15:c])
        V[k] = np.nanmean(vol[c:c + 15]) / np.nanmean(vol[c - 15:c])
    f["r24"] = np.stack([A, V])
    return f


def janelas5(mn):
    """posicoes k tais que as 5 velas k..k+4 estao na janela 09:00-10:00 e consecutivas no tempo"""
    ok = np.zeros(len(mn), bool)
    for k in range(len(mn) - 4):
        if mn[k] >= 540 and mn[k + 4] < 600 and mn[k + 4] - mn[k] == 4: ok[k] = True
    return ok
