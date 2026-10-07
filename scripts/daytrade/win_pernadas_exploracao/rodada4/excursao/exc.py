"""Mapa de excursoes (MFE/MAE) apos recuo + simulacao de alvo/stop. WIN 2026."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada3/recuo_tamanho")
from lib import load_days, build, shuffled_order
LEVELS = [0.10, 0.20, 0.30, 0.38, 0.50, 0.62, 0.78]
AMIN, AMAX = 150.0, 2000.0
TICK = 5.0; CUSTO = 2.0; SLIP = 5.0; TTL_MIN = 5
HOR = [15, 30, 60]
# geometrias: pts fixos e multiplos de A
GP = [(T, S) for T in (75, 150, 300, 600) for S in (75, 150, 300, 600)]
GA = [(tm, sm) for tm in (0.25, 0.5, 1.0) for sm in (0.3, 0.6, 1.0)]
GEOMS = [("p", T, S) for T, S in GP] + [("a", tm, sm) for tm, sm in GA]
NG = len(GEOMS)

def r5(x): return max(25.0, round(x / TICK) * TICK)

def sim_long(s, t, i_t, lev, geoms_ts, cons):
    """compra limite em lev, fill nos pontos s[0:] (apos o evento) dentro do TTL.
    retorna array (NG,) net pts (nan = nao encheu)."""
    out = np.full(len(geoms_ts), np.nan, dtype=np.float32)
    thr = lev - (TICK if cons else 0.0)
    m = np.searchsorted(t, i_t + TTL_MIN, side="right")  # pontos dentro do prazo
    if m <= 0: return out
    hit = np.flatnonzero(s[:m] <= thr)
    if hit.size == 0: return out
    j = hit[0]; e = lev
    sa = s[j + 1:]
    if sa.size == 0:
        out[:] = -CUSTO; return out
    rm = np.maximum.accumulate(sa); rn = -np.minimum.accumulate(sa)
    last = sa[-1] - e - CUSTO
    for g, (T, S) in enumerate(geoms_ts):
        it = np.searchsorted(rm, e + T + (TICK if cons else 0.0), side="left")
        is_ = np.searchsorted(rn, -(e - S), side="left")
        if it >= sa.size and is_ >= sa.size: out[g] = last
        elif is_ <= it: out[g] = -S - SLIP - CUSTO
        else: out[g] = T - CUSTO
    return out

def events_up(p, t):
    n = len(p); ev = []
    L = H = p[0]; iH = 0; trig = [False] * len(LEVELS); nord = 0
    for i in range(1, n):
        x = p[i]
        if x <= L:
            L = H = x; iH = i; trig = [False] * len(LEVELS); nord = 0; continue
        if x > H:
            if trig[1]: nord += 1
            H = x; iH = i; trig = [False] * len(LEVELS); continue
        A = H - L
        if A < AMIN or A > AMAX: continue
        dd = H - x
        for k, r in enumerate(LEVELS):
            if not trig[k] and dd >= r * A:
                trig[k] = True
                ev.append((i, k, A, H - r * A, t[i] - t[iH], nord + 1))
    return ev

def day_events(p, t):
    rows = []; res = []
    for sgn in (1.0, -1.0):
        pp = p * sgn
        for (i, k, A, lev, dt, od) in events_up(pp, t):
            if len(pp) - i < 8: continue
            s = pp[i + 1:]; ts = t[i + 1:]; x = pp[i]
            ex = []
            for W in HOR:
                if t[-1] - t[i] < W: ex += [np.nan, np.nan]; continue
                m = np.searchsorted(ts, t[i] + W, side="right")
                if m == 0: ex += [np.nan, np.nan]; continue
                ex += [max(0.0, s[:m].max() - x), max(0.0, x - s[:m].min())]
            ex += [max(0.0, s.max() - x), max(0.0, x - s.min())]
            geoms_ts = []
            for g in GEOMS:
                geoms_ts.append((float(g[1]), float(g[2])) if g[0] == "p" else (r5(g[1] * A), r5(g[2] * A)))
            blocks = []
            # a favor (compra no recuo): long no frame up; contra: short = long no frame negado
            for cons in (True, False):
                a = sim_long(s, ts, t[i], lev, geoms_ts, cons)
                b = sim_long(-s, ts, t[i], -lev, geoms_ts, cons)
                blocks += [a, b]
            # ordem: [cons_fav, cons_con, opt_fav, opt_con]
            rows.append((k, A, t[i], od, max(1.0, dt), x - 0, *ex))
            res.append(np.concatenate(blocks))
    return rows, res

COLS = ["lv", "A", "hm", "ord", "dur", "x"] + [f"{a}{w}" for w in HOR + ["E"] for a in ("mfe", "mae")]

def run_task(args):
    """args=(m0,m1,sim,seed): sim=-1 real."""
    m0, m1, sim, seed = args
    days = load_days(m0, m1)
    rng = np.random.default_rng(seed * 100003 + sim + 7) if sim >= 0 else None
    R = []; Rr = []; D = []
    for di, day in enumerate(days):
        order = shuffled_order(day, rng) if sim >= 0 else None
        p, t = build(day, order)
        rows, res = day_events(p, t)
        R += rows; Rr += res; D += [di] * len(rows)
    df = pd.DataFrame(R, columns=COLS)
    df["day"] = D; df["date"] = [days[d]["date"] for d in D]
    return sim, (m0, m1), df, (np.array(Rr, dtype=np.float32) if Rr else np.zeros((0, 4 * NG), np.float32))
