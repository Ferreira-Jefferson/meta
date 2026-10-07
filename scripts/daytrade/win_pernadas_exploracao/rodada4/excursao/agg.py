import numpy as np, pandas as pd, exc
NG = exc.NG
ABANDS = [150, 250, 400, 750, 2001]
SPECS = {
 "all": [], "r": ["lv"], "A": ["ab"], "hora": ["hb"], "vel": ["vb"], "ord": ["od"],
 "rA": ["lv", "ab"], "rH": ["lv", "hb"], "rV": ["lv", "vb"], "AV": ["ab", "vb"], "AH": ["ab", "hb"], "rO": ["lv", "od"],
}
def feats(df, vthr):
    d = df.copy()
    d["ab"] = np.digitize(d.A, ABANDS[1:-1])
    d["hb"] = np.digitize(d.hm, [660, 780])
    sp = np.array(exc.LEVELS)[d.lv] * d.A / d.dur
    d["vb"] = np.digitize(sp, vthr)
    d["od"] = np.minimum(d.ord, 3) - 1
    d["all"] = 0
    return d
def speed_thr(df):
    sp = np.array(exc.LEVELS)[df.lv] * df.A / df.dur
    return np.quantile(sp, [1/3, 2/3])
def agg(df, R, vthr):
    """retorna DataFrame longo: spec,cell,fill,side,geom,n,nf,s,w,sw,sl"""
    d = feats(df, vthr)
    M = (~np.isnan(R)).astype(np.float32); Rz = np.nan_to_num(R, nan=0.0)
    Wc = (R > 0).astype(np.float32); Ws = np.where(R > 0, R, 0.0); Ls = np.where(R <= 0, R, 0.0)
    out = []
    for sp, keys in SPECS.items():
        kk = keys if keys else ["all"]
        gid = d.groupby(kk).ngroup().values
        ng = gid.max() + 1
        cells = d.groupby(kk).size().index
        cnt = np.bincount(gid, minlength=ng)
        def gs(X):
            o = np.zeros((ng, X.shape[1]))
            np.add.at(o, gid, X); return o
        nf, s, w, sw, sl = gs(M), gs(Rz), gs(Wc), gs(Ws), gs(Ls)
        for ci in range(ng):
            c = cells[ci]; c = c if isinstance(c, tuple) else (c,)
            cell = "|".join(f"{a}={b}" for a, b in zip(kk, c))
            for col in range(4 * NG):
                fi, rem = divmod(col, 2 * NG); side, g = divmod(rem, NG)
                out.append((sp, cell, fi, side, g, cnt[ci], nf[ci, col], s[ci, col], w[ci, col], sw[ci, col], sl[ci, col]))
    return pd.DataFrame(out, columns=["spec", "cell", "fill", "side", "geom", "n", "nf", "s", "w", "sw", "sl"])
def quant_tab(df, vthr):
    d = feats(df, vthr); rows = []
    qs = [.25, .5, .75, .9]
    for (lv, ab), g in d.groupby(["lv", "ab"]):
        for h in ["15", "30", "60", "E"]:
            for kind in ("mfe", "mae"):
                x = g[f"{kind}{h}"].dropna().values
                if len(x) == 0: continue
                rows.append((lv, ab, h, kind, len(x), *np.quantile(x, qs)))
    return pd.DataFrame(rows, columns=["lv", "ab", "h", "kind", "n", "q25", "q50", "q75", "q90"])
