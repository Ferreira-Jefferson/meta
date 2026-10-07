import numpy as np, itertools
import stage as st, simfam as S, geomlib as G

DIMS = {"E1": (3, 4, 3), "E2a": (3, 4, 3), "E2b": (3, 4, 3), "E2c": (3, 4, 3), "E3": (3, 3, 3)}

def g_decode(f, g):
    a, b, c = DIMS[f]
    return (g // (b * c), (g // c) % b, g % c)

def g_encode(f, ix):
    a, b, c = DIMS[f]
    return ix[0] * b * c + ix[1] * c + ix[2]

def g_label(f, g):
    par = S.GEOMS[st.FAM_SIM[f]][g]
    if f == "E1":
        r, s, m = par; return f"E1 r={r:.0%} s=1/{round(1/s)} alvo={m}x"
    if f.startswith("E2"):
        j, sm, m = par; k = {"E2a": 25, "E2b": 38, "E2c": 50}[f]
        return f"E2 k={k}% j={j:.0%} stop={sm} alvo={m}x"
    r, N, k = par; return f"E3 r={r:.0%} N={N} alvo={k}xstop"

def filt_label(k):
    t, h, v, o = st.FILTS[k]
    N = st.FILT_NAMES
    return f"{N['trend'][t]}/{N['hora'][h]}/{N['vol'][v]}/{N['ordem'][o]}"

def cell_trades(built, win, T, f, g, k, mode):
    evs, res, taken = built[(T, f)]
    loc = {di: i for i, di in enumerate(win)}
    FM = st.filter_masks(evs)[k]
    tk_ = taken[:, g, mode] & FM
    fl = tk_ & res["filled"][:, g, mode]
    idx = np.nonzero(fl)[0]
    return dict(day=np.array([loc[evs[i]["di"]] for i in idx], int), pnl=res["pnl"][idx, g, mode].astype(float),
                code=res["code"][idx, g, mode], sd=res["sd"][idx, g].astype(float), tpd=res["tpd"][idx, g].astype(float),
                a=np.array([evs[i]["a"] for i in idx]), n_orders=int(tk_.sum()))

def stats(tr, nd, W):
    pn = tr["pnl"]; n = len(pn)
    if n == 0: return None
    D = tr["day"]
    Sd = np.bincount(D, weights=pn, minlength=nd); Nd = np.bincount(D, minlength=nd).astype(float)
    mean = pn.mean()
    boots = (W @ Sd) / np.maximum(W @ Nd, 1e-9)
    ok = (W @ Nd) > 0
    boots = boots[ok]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    wins = pn[pn > 0]; los = -pn[pn < 0]
    gm = wins.mean() if len(wins) else 0.0; lm = los.mean() if len(los) else 0.0
    be = lm / (gm + lm) if gm + lm > 0 else np.nan
    p0 = tr["sd"] / (tr["sd"] + tr["tpd"])
    null_exp = float((p0 * (tr["tpd"] - G.CUSTO) - (1 - p0) * (tr["sd"] + G.DESL + G.CUSTO)).mean())
    # streak
    loss = (pn < 0).astype(int)
    mx = cur = 0
    for x in loss:
        cur = cur + 1 if x else 0
        mx = max(mx, cur)
    resid = Sd - mean * Nd
    se = np.sqrt(nd / max(nd - 1, 1) * (resid ** 2).sum()) / n
    return dict(n=n, n_orders=tr["n_orders"], fill=n / max(tr["n_orders"], 1), acerto=len(wins) / n, be=be,
                mean=float(mean), lo=float(lo), hi=float(hi), t=float(mean / se) if se > 0 else np.nan,
                maxstreak=mx, opd=n / nd, p0=float(p0.mean()), null_exp=null_exp,
                payoff_real=(gm / lm if lm > 0 else np.nan), payoff_nom=float((tr["tpd"] / tr["sd"]).mean()),
                liquido_pts=float(pn.sum()), sd_med=float(np.median(tr["sd"])), stop_pct=float((tr["code"] == 0).mean()))

def boot_W(nd, B=2000, seed=7):
    rng = np.random.default_rng(seed)
    W = np.zeros((B, nd))
    for b in range(B):
        W[b] = np.bincount(rng.integers(0, nd, nd), minlength=nd)
    return W
