"""Geometria proporcional assimetrica (WIN, so 2026; dez/2025 so aquece a base de volatilidade).

Eventos em TEMPO REAL (nenhum extremo futuro): zigzag de T pts sobre o caminho da vela, perna em curso,
topo provisorio E (maximo corrente da perna), inicio P da perna, avanco A = E-P. Tudo em "quadro" orientado
(perna de alta = +1; perna de baixa espelhada por sinal).

Familias
  E1  limite em E - r*A (r 38/50/62), stop = s*(E-entrada), alvo = E + (m-1)*(E-entrada)  [m=1: topo; 1,27; 1,62]
  E2  fundo provisorio confirmado (repique >= k% do recuo desde a minima corrente), limite no reteste a j% do repique,
      stop {min-1tk, min-3tk, entrada-0,5*(entrada-min), min}, alvo = E + (m-1)*(E-min)
  E3  limite como E1, stop tecnico = extremo das ultimas N velas M1 (conhecido na hora de armar) - 1tk, alvo = k*stop
Execucao: limite com prazo TTL minutos, enche so se o preco negociar 1 tick alem (conservador) ou ao toque (otimista);
alvo = limite (conservador: exige +1 tick alem); stop a mercado +5 pts; custo 2 pts; fim 17:50 a mercado.
Mesma vela: stop vence alvo; na vela do preenchimento so vale o stop. Ordem cancelada se a vela faz maxima > E.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
TICK = 5.0; CUSTO = 2.0; DESL = 5.0; TTL_MIN = 10
MIN_INI, MIN_FIM = 540, 1070
ARM_INI, ARM_FIM = 550, 1030
TS = (250, 500, 750)
RS = (0.38, 0.50, 0.62)
SS = (0.1, 1 / 7, 0.2, 1 / 3)
MS = (1.0, 1.27, 1.62)
KS = (0.25, 0.38, 0.50)
JS = (0.50, 0.62, 0.79)
STOPMODES = ("tk1", "tk3", "d05", "d10")
NS = (5, 10, 15)
KALVO = (5.0, 7.5, 10.0)
MIN_STOP = 15.0
MAX_STOP = 500.0


def tk(x):
    return np.round(np.asarray(x, float) / TICK) * TICK


# ------------------------------------------------------------------ dados
def load_days():
    keep = []
    with open(CSV, encoding="utf-8") as f:
        hdr = f.readline()
        for ln in f:
            if ln.startswith("2026.") or ln.startswith("2025.12."):
                keep.append(ln)
    import io
    d = pd.read_csv(io.StringIO(hdr + "".join(keep)), sep="\t")
    d.columns = [c.strip("<>") for c in d.columns]
    d["m"] = d.TIME.str.slice(0, 2).astype(int) * 60 + d.TIME.str.slice(3, 5).astype(int)
    d = d[(d.m >= MIN_INI) & (d.m <= MIN_FIM)]
    days = []
    for date, g in d.groupby("DATE", sort=True):
        if len(g) < 60:
            continue
        mo = int(date[5:7]); yr = int(date[:4])
        days.append(dict(date=date, warm=(yr == 2025), month=mo, m=g.m.values.astype(int),
                         o=g.OPEN.values.astype(float), h=g.HIGH.values.astype(float),
                         l=g.LOW.values.astype(float), c=g.CLOSE.values.astype(float)))
    return days


def avg_range_prev(days, lookback=20, minprev=10):
    nd = len(days); R = np.full((nd, MIN_FIM - MIN_INI + 1), np.nan)
    for i, d in enumerate(days):
        R[i, d["m"] - MIN_INI] = d["h"] - d["l"]
    out = []
    for i in range(nd):
        if i < minprev:
            out.append(None); continue
        with np.errstate(all="ignore"):
            out.append(np.nanmean(R[max(0, i - lookback):i], axis=0))
    return out


def shuffle_day(d, rng):
    o, h, l, c, m = d["o"], d["h"], d["l"], d["c"], d["m"]
    n = len(c)
    gap = np.empty(n); gap[0] = 0.0; gap[1:] = o[1:] - c[:-1]
    dh, dl, dc = h - o, l - o, c - o
    blk = (m - MIN_INI) // 30
    perm = np.arange(n)
    for b in np.unique(blk):
        ix = np.nonzero(blk == b)[0]
        perm[ix] = rng.permutation(ix)
    gap_s = gap[perm]
    o2 = np.empty(n); c2 = np.empty(n); prev = o[0]
    for k in range(n):
        o2[k] = o[0] if k == 0 else prev + gap_s[k]
        prev = o2[k] + dc[perm[k]]
        c2[k] = prev
    e = dict(d); e.update(o=o2, h=o2 + dh[perm], l=o2 + dl[perm], c=c2)
    return e


def vol_flags(d, ar):
    """v2x: alguma das ultimas 10 velas (ate a de armar) com faixa >= 2x a do mesmo minuto nos 20 pregoes anteriores.
    onda: faixa das ultimas 30 velas >= 1,5x o esperado. Sem base (primeiros pregoes) -> False."""
    n = len(d["c"])
    if ar is None:
        return np.zeros(n, bool), np.zeros(n, bool)
    m = d["m"]; rg = d["h"] - d["l"]; a = ar[m - MIN_INI]
    with np.errstate(all="ignore"):
        ratio = rg / a
    b = np.isfinite(ratio) & (ratio >= 2.0)
    cs = np.concatenate([[0], np.cumsum(b.astype(int))])
    idx = np.arange(n)
    v2x = (cs[idx + 1] - cs[np.maximum(0, idx - 9)]) > 0
    cr = np.concatenate([[0.0], np.cumsum(np.nan_to_num(rg))])
    ca = np.concatenate([[0.0], np.cumsum(np.nan_to_num(a))])
    lo = np.maximum(0, idx - 29)
    with np.errstate(all="ignore"):
        w = (cr[idx + 1] - cr[lo]) / (ca[idx + 1] - ca[lo])
    onda = (idx >= 14) & np.isfinite(w) & (w >= 1.5)
    return v2x, onda


# ------------------------------------------------------------------ zigzag causal
class ZZ:
    def __init__(self, T):
        self.T = T; self.dir = 0; self.mn = np.inf; self.mx = -np.inf
        self.E = 0.0; self.P = 0.0; self.flips = 0

    def step(self, p):
        T = self.T
        if self.dir == 0:
            self.mn = min(self.mn, p); self.mx = max(self.mx, p)
            if p - self.mn >= T and p == self.mx:
                self.dir = 1; self.E = p; self.P = self.mn; self.flips += 1
            elif self.mx - p >= T and p == self.mn:
                self.dir = -1; self.E = p; self.P = self.mx; self.flips += 1
        elif self.dir == 1:
            if p > self.E:
                self.E = p
            elif self.E - p >= T:
                self.P = self.E; self.dir = -1; self.E = p; self.flips += 1
        else:
            if p < self.E:
                self.E = p
            elif p - self.E >= T:
                self.P = self.E; self.dir = 1; self.E = p; self.flips += 1


def path_pts(o, h, l, c, i):
    return (l[i], h[i]) if c[i] >= o[i] else (h[i], l[i])


def dir750_series(d):
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    z = ZZ(750.0); out = np.zeros(len(c), int)
    for i in range(len(c)):
        for p in path_pts(o, h, l, c, i):
            z.step(p)
        out[i] = z.dir
    return out


def gen_events(d, T, d750):
    """Eventos E1 (armar apos inicio do recuo) e E2 (k=0,1,2) para a escala T. Lista de dicts (quadro orientado em sg)."""
    o, h, l, c, m = d["o"], d["h"], d["l"], d["c"], d["m"]
    n = len(c)
    z = ZZ(float(T))
    ev1 = []; ev2 = [[], [], []]
    sg_prev = 0; flips_prev = -1
    E = None; Ebar = -1; armed1 = False; narm = 0
    mmin = np.inf; mbar = -1; Hb = -np.inf; armed2 = [False] * 3
    for i in range(n):
        for p in path_pts(o, h, l, c, i):
            z.step(p)
        if z.dir == 0:
            continue
        sg = z.dir
        if z.flips != flips_prev:                     # perna nova
            flips_prev = z.flips; narm = 0; E = None
        if sg > 0:
            fh, fl, fc = h[i], l[i], c[i]
        else:
            fh, fl, fc = -l[i], -h[i], -c[i]
        Ez = sg * z.E; Pz = sg * z.P
        if E is None or Ez != E:                       # novo topo provisorio
            E = Ez; Ebar = i; armed1 = False
            mmin = np.inf; mbar = -1; Hb = -np.inf; armed2 = [False] * 3
            continue
        # i > Ebar, mesmo topo
        if fl < mmin:
            mmin = fl; mbar = i; Hb = -np.inf
        else:
            Hb = max(Hb, fh)
        A = E - Pz
        inwin = ARM_INI <= m[i] <= ARM_FIM
        if (not armed1) and fc < E - TICK:
            armed1 = True; narm += 1
            if inwin and A >= T:
                ev1.append(dict(a=i, sg=sg, E=E, A=A, P=Pz, ord=narm, tr=_tr(d750[i], sg), cl=fc))
        if mbar >= 0 and Hb > -np.inf and inwin:
            rec = E - mmin
            if rec >= max(0.25 * A, 50.0) and rec < T - TICK:
                for kk, kv in enumerate(KS):
                    if not armed2[kk] and Hb - mmin >= kv * rec:
                        armed2[kk] = True
                        ev2[kk].append(dict(a=i, sg=sg, E=E, A=A, P=Pz, ord=max(narm, 1), tr=_tr(d750[i], sg),
                                            cl=fc, mn=mmin, Hb=Hb))
    return ev1, ev2


def _tr(d750i, sg):
    return 0 if d750i == 0 else (1 if d750i == sg else -1)


# ------------------------------------------------------------------ simulacao de uma ordem
def run_trade(LO, HI, CL, m, a, level, sd, tp, Eref, cons, ref_cancel_lo=None):
    """Retorna (preencheu, barra_saida, pnl, codigo) (codigo 0 stop, 1 alvo, 2 fim).
    Se nao preencheu: barra_saida = fim da validade (bloqueio)."""
    n = len(LO)
    bey = TICK if cons else 0.0
    wend = int(np.searchsorted(m, m[a] + TTL_MIN, side="right")) - 1
    wend = min(wend, n - 1)
    if wend <= a:
        return False, a + 1, 0.0, -1
    hseg = HI[a + 1:wend + 1] > Eref
    cb = wend if not hseg.any() else a + 1 + int(hseg.argmax())
    lseg = LO[a + 1:cb + 1] <= level - bey
    if not lseg.any():
        return False, wend, 0.0, -1
    f = a + 1 + int(lseg.argmax())
    sp = level - sd
    if LO[f] <= sp:
        return True, f, -(sd + DESL + CUSTO), 0
    if f + 1 >= n:
        return True, f, CL[-1] - level - DESL - CUSTO, 2
    rmin = np.minimum.accumulate(LO[f + 1:])
    rmax = np.maximum.accumulate(HI[f + 1:])
    return _resolve(rmin, rmax, f, level, sd, tp, bey, CL)


def _resolve(rmin, rmax, f, level, sd, tp, bey, CL):
    n1 = len(rmin)
    sp = level - sd
    ist = int(np.searchsorted(-rmin, -sp, side="left"))
    itg = int(np.searchsorted(rmax, tp + bey, side="left"))
    if ist < n1 and ist <= itg:
        return True, f + 1 + ist, -(sd + DESL + CUSTO), 0
    if itg < n1:
        return True, f + 1 + itg, (tp - level) - CUSTO, 1
    return True, f + n1, CL[-1] - level - DESL - CUSTO, 2
