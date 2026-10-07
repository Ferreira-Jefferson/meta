"""core -- encaixe de medias entre tempos graficos (WIN, so 2026; nov-dez/2025 so aquece).

Decisao no FECHAMENTO do minuto i (ultimo M1 fechado); ordem so a partir de i+1.
Orientacao: tudo e calculado para COMPRA (sinal s=+1); a venda e o espelho (precos negados).
Execucao: limite com prazo (ttl min), conservador = so enche se negociar 1 tick (5 pts) alem; stop a mercado
(+5 pts); alvo limite (conservador: high >= alvo+5); custo 2 pts; mesma vela: stop vence; na vela do
preenchimento so vale o stop. Um trade por vez (ordem pendente bloqueia ate expirar). Fim do pregao = mercado.
"""
from __future__ import annotations
import numpy as np, pandas as pd

CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
TICK, CUSTO, DESL = 5.0, 2.0, 5.0
MIN0 = 540
WARM_FROM = "2025.11.01"           # aquecimento: nada antes disso e lido; nada de nov-dez vira resultado
BIG = 10 ** 9


def load_raw():
    out = []
    for ch in pd.read_csv(CSV, sep="\t", chunksize=250000):
        ch.columns = [c.strip("<>") for c in ch.columns]
        ch = ch[ch.DATE >= WARM_FROM]
        if len(ch):
            out.append(ch[["DATE", "TIME", "OPEN", "HIGH", "LOW", "CLOSE"]])
    d = pd.concat(out, ignore_index=True)
    d["m"] = d.TIME.str.slice(0, 2).astype(int) * 60 + d.TIME.str.slice(3, 5).astype(int)
    d = d[(d.m >= 540) & (d.m <= 1075)].reset_index(drop=True)
    return d


class Data:
    def __init__(self, raw: pd.DataFrame, shuffle_seed=None):
        self.date = raw.DATE.values
        self.m = raw.m.values.astype(int)
        o = raw.OPEN.values.astype(float); h = raw.HIGH.values.astype(float)
        l = raw.LOW.values.astype(float); c = raw.CLOSE.values.astype(float)
        self.day = pd.factorize(self.date)[0]
        if shuffle_seed is not None:
            o, h, l, c = self._shuffle(o, h, l, c, shuffle_seed)
        self.o, self.h, self.l, self.c = o, h, l, c
        self.N = len(c)
        month = np.array([int(x[5:7]) for x in self.date]); year = np.array([int(x[:4]) for x in self.date])
        self.win = np.where(year < 2026, 0, np.where(month <= 6, 1, np.where(month <= 8, 2, 3)))
        # fim do dia (exclusivo)
        chg = np.flatnonzero(np.r_[True, self.day[1:] != self.day[:-1]])
        ends = np.r_[chg[1:], self.N]
        self.dend = np.repeat(ends, np.diff(np.r_[chg, self.N]))
        self.dstart = np.repeat(chg, np.diff(np.r_[chg, self.N]))
        self.SG = {1: (l, h, c), -1: (-h, -l, -c)}
        self._tf = {}
        self._pre = {}
        self._filters()

    # ---- nulo: blocos de 30 min embaralhados e reencadeados, so em 2026
    def _shuffle(self, o, h, l, c, seed):
        rng = np.random.default_rng(seed)
        o, h, l, c = o.copy(), h.copy(), l.copy(), c.copy()
        for d in np.unique(self.day):
            ix = np.flatnonzero(self.day == d)
            if not self.date[ix[0]].startswith("2026"):
                continue
            oo, hh, ll, cc, m = o[ix], h[ix], l[ix], c[ix], self.m[ix]
            n = len(ix)
            gap = np.empty(n); gap[0] = 0.0; gap[1:] = oo[1:] - cc[:-1]
            dh, dl, dc = hh - oo, ll - oo, cc - oo
            blk = (m - MIN0) // 30
            perm = np.arange(n)
            for b in np.unique(blk):
                jx = np.flatnonzero(blk == b)
                perm[jx] = rng.permutation(jx)
            gs = gap[perm]
            o2 = np.empty(n); c2 = np.empty(n); prev = oo[0]
            for k in range(n):
                o2[k] = oo[0] if k == 0 else prev + gs[k]
                prev = o2[k] + dc[perm[k]]
                c2[k] = prev
            o[ix] = o2; c[ix] = c2; h[ix] = o2 + dh[perm]; l[ix] = o2 + dl[perm]
        return o, h, l, c

    def _filters(self):
        # v2x: range M1 >= 2x a media do mesmo minuto nos 20 pregoes anteriores (qualquer das 3 ultimas velas)
        nd = self.day.max() + 1
        R = np.full((nd, 540), np.nan)
        for i in range(self.N):
            R[self.day[i], self.m[i] - MIN0] = self.h[i] - self.l[i]
        avg = np.full((nd, 540), np.nan)
        for d in range(10, nd):
            with np.errstate(all="ignore"):
                avg[d] = np.nanmean(R[max(0, d - 20):d], axis=0)
        ratio = (self.h - self.l) / avg[self.day, np.clip(self.m - MIN0, 0, 539)]
        v = np.isfinite(ratio) & (ratio >= 2.0)
        v3 = v.copy(); v3[1:] |= v[:-1]; v3[2:] |= v[:-2]
        self.v2x = v3
        # zigzag 750 (caminho da vela), por pregao, estado ao fim do minuto
        zz = np.zeros(self.N, int)
        for d in range(nd):
            ix = np.flatnonzero(self.day == d)
            dirn = 0; mn = np.inf; mx = -np.inf; ext = 0.0
            for i in ix:
                pts = (self.l[i], self.h[i]) if self.c[i] >= self.o[i] else (self.h[i], self.l[i])
                for p in pts:
                    if dirn == 0:
                        mn = min(mn, p); mx = max(mx, p)
                        if p - mn >= 750 and p == mx: dirn = 1; ext = p
                        elif mx - p >= 750 and p == mn: dirn = -1; ext = p
                    elif dirn == 1:
                        ext = max(ext, p)
                        if ext - p >= 750: dirn = -1; ext = p
                    else:
                        ext = min(ext, p)
                        if p - ext >= 750: dirn = 1; ext = p
                zz[i] = dirn
        self.zz = zz

    def tf(self, k):
        if k not in self._tf:
            self._tf[k] = TF(self, k)
        return self._tf[k]


class TF:
    def __init__(self, D: Data, k):
        self.k = k
        N = D.N
        key = D.day * 1000 + ((D.m - MIN0) // k if k else 0)
        st = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
        nb = len(st)
        en = np.r_[st[1:] - 1, N - 1]
        self.st, self.en, self.nb = st, en, nb
        self.cb = np.repeat(np.arange(nb), np.diff(np.r_[st, N]))
        self.bo = D.o[st]; self.bc = D.c[en]
        self.bh = np.maximum.reduceat(D.h, st); self.bl = np.minimum.reduceat(D.l, st)
        self.bday = D.day[st]
        self.isend = np.zeros(N, bool)
        if k:
            self.isend[en] = True
        s = pd.Series(D.l).groupby(self.cb)
        self.lowf = s.cummin().values
        self.highf = pd.Series(D.h).groupby(self.cb).cummax().values
        pc = np.r_[self.bc[0], self.bc[:-1]]
        tr = np.maximum(self.bh - self.bl, np.maximum(abs(self.bh - pc), abs(self.bl - pc)))
        self.atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
        self.rmh = pd.Series(self.bh).rolling(12, min_periods=1).max().values
        self.rml = pd.Series(self.bl).rolling(12, min_periods=1).min().values
        self.cs = np.r_[0.0, np.cumsum(self.bc)]
        self._ma = {}

    def ma(self, kind, p):
        key = (kind, p)
        if key not in self._ma:
            s = pd.Series(self.bc)
            self._ma[key] = (s.ewm(span=p, adjust=False).mean().values if kind == "ema"
                             else s.rolling(p).mean().values)
        return self._ma[key]

    def acc(self, D, var, idx, P, s):
        """Estado do TF nos minutos idx, ja na orientacao s. P=(pf,pm,ps,kind). var 'c' fechada | 'f' formando."""
        pf, pm, ps, kind = P
        idx = np.asarray(idx, int)
        cbi = self.cb[idx]
        if var == "c":
            lc = np.where(self.isend[idx], cbi, cbi - 1)
            lc = np.maximum(lc, 1)
            sel = lambda a: a[lc]
            ef, em, es = sel(self.ma(kind, pf)), sel(self.ma(kind, pm)), sel(self.ma(kind, ps))
            emp = self.ma(kind, pm)[lc - 1]
            px = self.bc[lc]
            low2 = np.minimum(self.bl[lc], self.bl[lc - 1])
            atr = self.atr[lc]; hhi = self.rmh[lc]; llo = self.rml[lc]
        else:
            p = np.maximum(cbi - 1, 1)
            ci = D.c[idx]
            def fm(per):
                M = self.ma(kind, per)
                if kind == "ema":
                    a = 2.0 / (per + 1)
                    return a * ci + (1 - a) * M[p]
                # SMA formando: soma das (per-1) barras fechadas ate p + preco atual
                lo = p + 1 - (per - 1)
                ok = lo >= 0
                sm = self.cs[p + 1] - self.cs[np.maximum(lo, 0)]
                return np.where(ok, (sm + ci) / per, np.nan)
            ef, em, es = fm(pf), fm(pm), fm(ps)
            emp = self.ma(kind, pm)[p]
            px = ci
            low2 = np.minimum(self.lowf[idx], self.bl[p])
            atr = self.atr[p]
            hhi = np.maximum(self.highf[idx], self.rmh[p]); llo = np.minimum(self.lowf[idx], self.rml[p])
        if s == 1:
            return dict(ef=ef, em=em, es=es, emp=emp, px=px, low2=low2, atr=atr, hhi=hhi)
        return dict(ef=-ef, em=-em, es=-es, emp=-emp, px=-px,
                    low2=-self._high2(D, var, idx, cbi),
                    atr=atr, hhi=-llo)

    def _high2(self, D, var, idx, cbi):
        if var == "c":
            lc = np.maximum(np.where(self.isend[idx], cbi, cbi - 1), 1)
            return np.maximum(self.bh[lc], self.bh[lc - 1])
        p = np.maximum(cbi - 1, 1)
        return np.maximum(self.highf[idx], self.bh[p])


# --------------------------------------------------------------------- eventos
def breach_edges(D, ltf, P, s, mode):
    L = D.tf(ltf)
    pf, pm, ps, kind = P
    ef, em, es = L.ma(kind, pf), L.ma(kind, pm), L.ma(kind, ps)
    br = (s * (L.bc - ef) < 0)
    if mode in ("fm", "fms"): br &= (s * (L.bc - em) < 0)
    if mode == "fms": br &= (s * (L.bc - es) < 0)
    for a in (ef, em, es):
        pass
    valid = np.isfinite(ef) & np.isfinite(em) & np.isfinite(es)
    br &= valid
    prev = np.r_[False, br[:-1]]
    edge = br & ~prev
    idx = L.en[edge]
    mm = D.m[idx]
    ok = (mm >= 570) & (mm <= 1020) & (D.win[idx] > 0)
    return idx[ok]


def core_mask(a, trend):
    stack = (a["ef"] > a["em"]) & (a["em"] > a["es"])
    slope = a["em"] > a["emp"]
    return (stack & slope) if trend == "strict" else slope


def gen_events(D, cfg, s):
    """cfg: ltf, htf, h1(bool: exige H1 alinhado tambem), var, trend, breach, ref('f'|'m'), x, P. Devolve dict de idx."""
    P = cfg["P"]
    ev = breach_edges(D, cfg["ltf"], P, s, cfg["breach"])
    if len(ev) == 0:
        z = np.array([], int)
        return dict(ENC=z, A1=z, A2=z, B=z, ALL=z)
    H = D.tf(cfg["htf"])
    a = H.acc(D, cfg["var"], ev, P, s)
    core = core_mask(a, cfg["trend"])
    ok_px = a["px"] >= a["es"]
    refv = a["ef"] if cfg["ref"] == "f" else a["em"]
    touch = a["low2"] <= refv + cfg["x"] * a["atr"]
    enc = core & ok_px & touch
    if cfg.get("h1"):
        a3 = D.tf(60).acc(D, cfg["var"], ev, P, s)
        enc &= core_mask(a3, cfg["trend"]) & (a3["px"] >= a3["es"])
    ao = H.acc(D, cfg["var"], ev, P, -s)
    core_o = core_mask(ao, cfg["trend"])
    fin = np.isfinite(a["es"]) & np.isfinite(a["atr"])
    return dict(ENC=ev[enc & fin], A1=ev[~core & ~core_o & fin], A2=ev[core_o & fin],
                B=ev[core_mask(a, "loose") & ~ok_px & fin], ALL=ev[fin])


# --------------------------------------------------------------------- simulacao
def floor5(x):
    return np.floor(x / TICK) * TICK


def sim_events(D, idx, t, feat, atr15, geom, collect_exc=False):
    """idx: minutos-sinal (ordenados) ; t: lado do trade (+1 compra / -1 venda); feat: acc(htf) na orientacao t
    nos idx (ef, em, es, hhi); atr15: ATR M15 fechado nos idx. geom: entry('cl'|'f'|'m'), stop('e50h'|'x'|'atr'),
    N|K_atr, K (alvo em x stop) ou 'hh', ttl, otim. Devolve dict de arrays por trade preenchido + contagens."""
    LO, HI, CL = D.SG[t]
    ttl = geom["ttl"]; otim = geom["otim"]
    beyond = 0.0 if otim else TICK
    entry = geom["entry"]; sk = geom["stop"]; K = geom["K"]
    busy = -1
    rows = []
    nsig = 0; nfill = 0; ninv = 0
    for n in range(len(idx)):
        i = int(idx[n])
        if i < busy:
            continue
        dend = int(D.dend[i])
        if i + ttl + 2 >= dend:
            continue
        nsig += 1
        c = CL[i]
        if entry == "cl": Lp = floor5(c)
        elif entry == "f": Lp = floor5(min(c, feat["ef"][n]))
        else: Lp = floor5(min(c, feat["em"][n]))
        seg = LO[i + 1:i + 1 + ttl]
        hit = np.flatnonzero(seg <= Lp - beyond)
        if len(hit) == 0:
            busy = i + ttl
            continue
        j = i + 1 + int(hit[0])
        if sk == "e50h":
            Sp = floor5(feat["es"][n]) - TICK; S = Lp - Sp
        elif sk == "x":
            Sp = LO[max(0, i - geom["N"] + 1):i + 1].min() - TICK; S = Lp - Sp
        else:
            a = atr15[n]
            if not np.isfinite(a): busy = i + 1; continue
            S = max(50.0, np.round(geom["Katr"] * a / TICK) * TICK); Sp = Lp - S
        if not (50 <= S <= 500):
            ninv += 1; busy = i + 1
            continue
        if K == "hh":
            Tt = floor5(feat["hhi"][n]) - Lp
            if Tt < 3 * S:
                ninv += 1; busy = i + 1; continue
        else:
            Tt = np.round(K * S / TICK) * TICK
        nfill += 1
        cm = np.minimum.accumulate(LO[j:dend])
        ts = int(np.searchsorted(-cm, -Sp, side="left"))
        cx = np.maximum.accumulate(HI[j + 1:dend])
        tt = int(np.searchsorted(cx, Lp + Tt + beyond, side="left"))
        ts_abs = j + ts if ts < len(cm) else BIG
        tt_abs = j + 1 + tt if tt < len(cx) else BIG
        if ts_abs <= tt_abs and ts_abs < BIG:
            pnl = -(S + DESL + CUSTO); ex = ts_abs; code = 0
        elif tt_abs < BIG:
            pnl = Tt - CUSTO; ex = tt_abs; code = 1
        else:
            pnl = CL[dend - 1] - Lp - DESL - CUSTO; ex = dend - 1; code = 2
        busy = ex
        row = [D.day[i], i, pnl, code, S, Tt]
        if collect_exc:
            for W in (30, 60):
                e = min(dend, j + W)
                row += [HI[j:e].max() - Lp, Lp - LO[j:e].min()]
        rows.append(row)
    return dict(rows=np.array(rows, float) if rows else np.zeros((0, 6 if not collect_exc else 10)),
                nsig=nsig, nfill=nfill, ninv=ninv)


def stats_from(rows, ndays=None, nsig=None):
    """rows: [day, i, pnl, code, S, T,...]. Devolve dict de metricas."""
    if len(rows) == 0:
        return dict(n=0, win=np.nan, mean=np.nan, t=np.nan, be=np.nan, payoff=np.nan, sd=np.nan, maxloss=0,
                    gw=np.nan, gl=np.nan)
    p = rows[:, 2]
    n = len(p); w = p > 0
    gw = p[w].mean() if w.any() else 0.0
    gl = -p[~w].mean() if (~w).any() else 0.0
    be = gl / (gw + gl) if (gw + gl) > 0 else np.nan
    sd = p.std(ddof=1) if n > 1 else np.nan
    # sequencia max de perdas
    run = mx = 0
    for v in p:
        run = run + 1 if v <= 0 else 0
        mx = max(mx, run)
    return dict(n=n, win=w.mean(), mean=p.mean(), sd=sd, t=(p.mean() / (sd / np.sqrt(n))) if sd and sd > 0 else np.nan,
                be=be, payoff=(gw / gl if gl > 0 else np.nan), maxloss=mx, gw=gw, gl=gl)


def boot_days(rows, nb=2000, seed=0):
    """IC95 da esperanca por bootstrap de DIAS."""
    if len(rows) == 0:
        return (np.nan, np.nan)
    days = rows[:, 0].astype(int)
    u, inv = np.unique(days, return_inverse=True)
    sm = np.bincount(inv, weights=rows[:, 2]); ct = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    k = len(u)
    pick = rng.integers(0, k, size=(nb, k))
    m = sm[pick].sum(1) / ct[pick].sum(1)
    return (np.percentile(m, 2.5), np.percentile(m, 97.5))


# --------------------------------------------------------------------- pvolta
def pvolta(D, htf, var, P, s, idx):
    """Pergunta do dono: apos o sinal, o preco faz nova maxima do TF maior (maxima das ultimas 12 barras) antes de
    uma barra do TF maior FECHAR abaixo da EMA lenta? Devolve (win, lose, none, nulo_ruina) arrays por evento."""
    H = D.tf(htf)
    a = H.acc(D, var, idx, P, s)
    HI = D.SG[s][1]; CLs = D.SG[s][2]
    kind = P[3]
    ms = H.ma(kind, P[2])
    cbar = H.bc
    # falha por barra fechada
    ff = np.zeros(D.N, bool)
    if H.k:
        cond = (s * (cbar - ms) < 0)
        ff[H.en] = cond
    res = np.zeros(len(idx), int); nul = np.zeros(len(idx))
    for n, i in enumerate(idx):
        i = int(i); dend = int(D.dend[i])
        hh = a["hhi"][n]; es = a["es"][n]; px = a["px"][n]
        up = hh - px; dn = px - es
        nul[n] = dn / (up + dn) if (up + dn) > 0 and np.isfinite(up + dn) else np.nan
        hi = np.flatnonzero(HI[i + 1:dend] >= hh)
        h0 = hi[0] if len(hi) else BIG
        if H.k:
            f = np.flatnonzero(ff[i + 1:dend]); f0 = f[0] if len(f) else BIG
        else:
            f = np.flatnonzero(CLs[i + 1:dend] < es); f0 = f[0] if len(f) else BIG
        res[n] = 1 if h0 < f0 else (-1 if f0 < BIG and f0 <= h0 else 0)
        if h0 == f0 == BIG: res[n] = 0
        elif h0 < f0: res[n] = 1
        elif f0 <= h0: res[n] = -1
    return res, nul
