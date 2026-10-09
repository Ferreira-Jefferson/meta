import numpy as np, pandas as pd, catalogo as K
from medir import load, sides
T = pd.read_pickle("resultado.pkl")
IDS = [r["id"] for r in K.R]; EXP = {r["id"]: r["exp"] for r in K.R}
Z = {p: load(p) for p in ("IS", "OOS", "virgem")}

def X(z, ids):
    """indicadores (n, 2, q) das respostas esperadas."""
    return np.stack([(z[i] == EXP[i]) for i in ids], 2).astype(np.float32)

def conjuntos():
    dirq = [i for i in IDS if T.loc[i, "lado"] and T.loc[i, "classe"] != "SEM AMOSTRA"]
    S = {}
    S["A BOA+FRACA (spec; seleção usa OOS)"] = [i for i in IDS if T.loc[i, "classe"] in ("BOA", "FRACA")]
    S["B p_IS<=0,10 (seleção só IS)"] = [i for i in dirq if T.loc[i, "p_IS"] <= 0.10]
    S["C banco atual C1-C8"] = [f"C{k}" for k in range(1, 9)]
    S["D todas as direcionais"] = dirq
    return S, dirq

def logit_ridge(Xm, y, lam=1000.0, it=30):
    w = np.zeros(Xm.shape[1]); b = 0.0
    for _ in range(it):
        eta = Xm @ w + b; p = 1 / (1 + np.exp(-eta)); g = p * (1 - p) + 1e-6
        r = y - p
        gw = Xm.T @ r - lam * w; gb = r.sum()
        H = (Xm * g[:, None]).T @ Xm + lam * np.eye(Xm.shape[1]); w = w + np.linalg.solve(H, gw); b = b + gb / g.sum()
    return w

def score(per, ids, w):
    z = Z[per]; return (X(z, ids) @ np.asarray(w, np.float32))  # (n, 2)

def pesos_logit(dirq):
    z = Z["IS"]; E = z["elig"]; Y = sides(z)
    Xm = X(z, dirq)[E].reshape(-1, len(dirq)).astype(np.float64); y = Y[E].reshape(-1)
    return logit_ridge(Xm, y)

def decis(per, S, ref=None, nb=10):
    z = Z[per]; E = z["elig"]; Y = sides(z)
    s = S[E].reshape(-1); y = Y[E].reshape(-1); dias = np.repeat(z["_dia"][E], 2)
    r = pd.Series(s).rank(method="first", pct=True).to_numpy(); dec = np.minimum((r * nb).astype(int), nb - 1)
    tab = pd.DataFrame(dict(dec=dec, y=y, s=s)).groupby("dec").agg(n=("y", "size"), acerto=("y", "mean"), s_med=("s", "mean"))
    # bootstrap por dia: topo - base
    ud = np.unique(dias); rng = np.random.default_rng(3); idx = {d: np.where(dias == d)[0] for d in ud}
    sp = []
    for _ in range(300):
        pick = rng.choice(ud, len(ud)); ii = np.concatenate([idx[d] for d in pick]); dd = dec[ii]; yy = y[ii]
        if (dd == nb - 1).sum() and (dd == 0).sum(): sp.append(yy[dd == nb - 1].mean() - yy[dd == 0].mean())
    rho = pd.Series(tab.index.to_numpy()).corr(pd.Series(tab.acerto.to_numpy()).rank(), method='pearson') if False else np.corrcoef(np.arange(nb), tab.acerto.rank().to_numpy())[0, 1]
    return tab, rho, np.percentile(sp, [2.5, 97.5])

if __name__ == "__main__":
    pd.set_option("display.width", 250)
    S, dirq = conjuntos()
    W = {}
    for nome, ids in S.items(): W[nome] = (ids, T.loc[ids, "peso"].to_numpy())
    wl = pesos_logit(dirq); W["L logística ridge (todas direcionais)"] = (dirq, wl)
    res = {}
    for nome, (ids, w) in W.items():
        print(f"\n=== {nome} | {len(ids)} perguntas")
        sI = score("IS", ids, w)
        for per in ("OOS", "virgem"):
            sc = score(per, ids, w); tab, rho, ic = decis(per, sc)
            thr = np.nanpercentile(sI[Z["IS"]["elig"]].reshape(-1), 90)
            E = Z[per]["elig"]; Y = sides(Z[per]); above = (sc >= thr) & E[:, None]
            dias = len(np.unique(Z[per]["_dia"][E]))
            print(f"-- {per}: Spearman decis {rho:.2f}; topo-base {100*(tab.acerto.iloc[-1]-tab.acerto.iloc[0]):.2f}pp IC95 [{100*ic[0]:.2f};{100*ic[1]:.2f}]; "
                  f"acerto por decil %: {' '.join(f'{100*x:.1f}' for x in tab.acerto)}")
            print(f"   corte IS decil-topo = {thr:.3f}: {100*above.sum()/(2*E.sum()):.1f}% das velas-lado, {above.sum()/dias:.2f} sinais/dia; acerto {100*Y[above].mean():.2f}% (n={above.sum()})")
            res[(nome, per)] = tab.acerto.to_numpy()
    pd.to_pickle(dict(W=W), "pesos_sets.pkl")
