import numpy as np, pandas as pd, catalogo as K, time
N0 = 400  # encolhimento: w * n/(n+N0)
NPERM = 2000

def load(per):
    z = np.load(f"calc_{per}.npz"); return {k: z[k] for k in z.files}

def sides(z):
    y = z["y"]; return np.stack([y, 1 - y], 1)  # compra, venda

def grid(z):
    dia = z["_dia"]; mins = z["_mins"]; E = z["elig"]
    ud, di = np.unique(dia, return_inverse=True)
    col = (mins - 570) // 15
    gi = np.where(E, di * 30 + col, -1)
    return len(ud), gi

def stats(z, ids=None):
    E = z["elig"]; Y = sides(z); out = {}
    nE = E.sum() * 2
    for r in K.R:
        a = z[r["id"]]; M = (a == r["exp"]) & E[:, None]; D = (a >= 0) & E[:, None]
        n = int(M.sum()); nd = int(D.sum())
        base = Y[D].mean() if nd else np.nan
        acc = Y[M].mean() if n else np.nan
        out[r["id"]] = dict(n=n, freq=n / nE, acerto=acc, base=base, lift=(acc - base) if n else np.nan)
    return pd.DataFrame(out).T

def perm_p(z, nperm=NPERM, seed=1):
    E = z["elig"]; nd, gi = grid(z); K_ = nd * 30
    Yg = np.full(K_, np.nan); ok = gi >= 0; Yg[gi[ok]] = z["y"][ok]; Yg = Yg.reshape(nd, 30)
    ids = [r["id"] for r in K.R]; nq = len(ids)
    Qb = np.zeros((nq, K_), np.float32); Qs = np.zeros((nq, K_), np.float32); Db = np.zeros((nq, K_), np.float32); Ds = np.zeros((nq, K_), np.float32)
    for q, r in enumerate(K.R):
        a = z[r["id"]]
        Qb[q, gi[ok]] = (a[ok, 0] == r["exp"]); Qs[q, gi[ok]] = (a[ok, 1] == r["exp"])
        Db[q, gi[ok]] = (a[ok, 0] >= 0); Ds[q, gi[ok]] = (a[ok, 1] >= 0)
    Q2, D2 = Qb + Qs, Db + Ds
    rng = np.random.default_rng(seed)
    def stat(perm):  # perm: (c, nd) -> (nq, c)
        Yp = Yg[perm].reshape(len(perm), K_).T
        W = (~np.isnan(Yp)).astype(np.float32); Yv = np.nan_to_num(Yp).astype(np.float32); WY = W * Yv; WY1 = W - WY
        ne = Q2 @ W; nde = D2 @ W
        se = Qb @ WY + Qs @ WY1; sd = Db @ WY + Ds @ WY1
        with np.errstate(all="ignore"): return se / ne - sd / nde
    obs = stat(np.arange(nd)[None, :])[:, 0]
    cnt = np.zeros(nq); tot = 0
    for _ in range(nperm // 250):
        perm = np.stack([rng.permutation(nd) for _ in range(250)])
        s = stat(perm); cnt += (np.abs(s) >= np.abs(obs)[:, None] - 1e-12).sum(1); tot += 250
    p = (cnt + 1) / (tot + 1); p[np.isnan(obs)] = 1.0
    return pd.Series(p, ids), pd.Series(obs, ids)

def bh(p, q=0.10):
    p = p.copy(); m = len(p); o = p.sort_values(); k = (o.values <= q * (np.arange(1, m + 1) / m)); 
    if not k.any(): return pd.Series(False, p.index)
    kmax = np.where(k)[0].max(); thr = o.values[kmax]; return p <= thr

def pesos(st):
    b = st.base.astype(float); n = st.n.astype(float); p = (n * st.acerto.astype(float).fillna(0.5) + 20 * b) / (n + 20)
    w = (np.log(p / (1 - p)) - np.log(b / (1 - b))) * n / (n + N0)
    return w.fillna(0.0)

if __name__ == "__main__":
    t = time.time()
    Z = {p: load(p) for p in ("IS", "OOS", "virgem")}
    ST = {p: stats(Z[p]) for p in Z}
    PP = {}
    for p in ("IS", "OOS", "virgem"):
        PP[p] = perm_p(Z[p]); print(p, "perm", round(time.time() - t), "s", flush=True)
    meta = pd.DataFrame([{k: r[k] for k in ("id", "origem", "texto", "fam", "regua", "tipo", "esperada", "fonte", "lado")} for r in K.R]).set_index("id")
    T = meta.copy()
    for p in ("IS", "OOS", "virgem"):
        T[f"n_{p}"] = ST[p].n; T[f"freq_{p}"] = ST[p].freq; T[f"acerto_{p}"] = ST[p].acerto; T[f"lift_{p}"] = ST[p].lift; T[f"p_{p}"] = PP[p][0]
    T["base_IS"] = ST["IS"].base; T["base_OOS"] = ST["OOS"].base
    T["peso"] = pesos(ST["IS"])
    T["bh_OOS"] = bh(T.p_OOS); T["bh_IS"] = bh(T.p_IS)
    def cls(r):
        li, lo = r.lift_IS, r.lift_OOS
        if r.n_OOS < 30 or r.n_IS < 30 or np.isnan(li) or np.isnan(lo): return "SEM AMOSTRA"
        if max(abs(li), abs(lo)) < 0.01: return "INERTE"
        if np.sign(li) != np.sign(lo): return "INSTÁVEL"
        return "BOA" if r.bh_OOS else "FRACA"
    T["classe"] = T.apply(cls, axis=1)
    T.to_pickle("resultado.pkl"); T.to_csv("resultado.csv", encoding="utf-8-sig")
    print(T.classe.value_counts()); print(round(time.time() - t), "s")
