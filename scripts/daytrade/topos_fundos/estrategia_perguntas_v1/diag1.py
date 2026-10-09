"""Diagnosticos: (1) walk-forward (so passado) dentro do IS; (2) ranking do modelo por decil no OOS/virgem; (3) estabilidade dos pesos IS x OOS."""
import pickle, numpy as np, pandas as pd
from lib import *
import cv as CV
pd.set_option("display.width", 250)
g = (1.0, 8); mo = "ridge_rep_3000"
Z = {p: carrega(p) for p in PER}; RES = {p: pickle.load(open(f"res_{p}.pkl", "rb"))[g] for p in PER}
X = {p: X_de(Z[p]) for p in PER}; EL = {p: elegivel(Z[p]) for p in PER}
zi = Z["IS"]; pts_i = RES["IS"][0]
qtr = CV.qtr; QS = CV.QS

def treina(mask_rows, Xp, pts, el):
    r = [(mask_rows & el & np.isfinite(pts[:, s])) for s in (0, 1)]
    return Ridge(3000, True).fit(np.concatenate([Xp[r[0], 0], Xp[r[1], 1]]), np.concatenate([pts[r[0], 0], pts[r[1], 1]]))

# (1) walk-forward expanding, a partir do 6o trimestre
sc = np.full((len(qtr), 2), np.nan)
for k, q in enumerate(QS):
    if k < 6: continue
    m = treina(np.isin(qtr, QS[:k]), X["IS"], pts_i, EL["IS"]); ix = np.where((qtr == q) & EL["IS"])[0]
    for s in (0, 1): sc[ix, s] = m.predict(X["IS"][ix, s])
oof = pickle.load(open("cv_oof.pkl", "rb"))[(g, "perg", mo)]
cut = float(np.nanpercentile(np.where(EL["IS"], oof.max(1), np.nan), 80))
pts, te, ts = RES["IS"]
ok = qtr >= QS[6]
for nome, s_ in (("walk-forward (so passado)", sc), ("leave-one-quarter-out (mesmo periodo)", np.where(ok[:, None], oof, np.nan))):
    tr = simula(s_, pts, te, ts, zi["_dia"], cut, 99)
    qq = pd.Series(tr.pts.to_numpy() * .4).groupby(qtr[tr.i.to_numpy()]).sum()
    print(nome, "ops", len(tr), "R$", round(tr.pts.sum() * .4), "trimestres+ %d/%d" % ((qq > 0).sum(), len(qq)), "media/op pts", round(tr.pts.mean(), 1))
print("(trimestres avaliados:", QS[6], "a", QS[-1], ")")

# (2) decis de score previsto vs realizado (media pts/contrato por candidato preenchido), modelo final no IS
mfin = treina(np.ones(len(qtr), bool), X["IS"], pts_i, EL["IS"])
for p in ("OOS", "virgem"):
    ix = np.where(EL[p])[0]; rows = []
    for s in (0, 1):
        pr = mfin.predict(X[p][ix, s]); re = RES[p][0][ix, s]; rows.append(pd.DataFrame(dict(pr=pr, re=re)))
    d = pd.concat(rows).dropna(); d["dec"] = pd.qcut(d.pr, 10, labels=False)
    print(p, "corr(prev, real) =", round(d.pr.corr(d.re), 3), "  por decil (média real pts/contrato):", d.groupby("dec").re.mean().round(1).tolist())
# IS fora-da-amostra
ix = np.where(EL["IS"])[0]; d = pd.DataFrame(dict(pr=np.concatenate([oof[ix, 0], oof[ix, 1]]), re=np.concatenate([pts_i[ix, 0], pts_i[ix, 1]]))).dropna()
d["dec"] = pd.qcut(d.pr, 10, labels=False); print("IS (OOF) corr =", round(d.pr.corr(d.re), 3), " por decil:", d.groupby("dec").re.mean().round(1).tolist())

# (3) estabilidade dos pesos: ridge reps por periodo (IS inteiro x OOS x virgem) -> correlacao dos pesos brutos
W = {}
for p in PER:
    m = treina(np.ones(len(EL[p]), bool), X[p], RES[p][0], EL[p]); w = pd.Series(0.0, index=IDS); w.loc[[IDS[j] for j in m.cols]] = m.w / m.sd; W[p] = w
M = pd.DataFrame(W); print("corr de Spearman dos pesos (modelo treinado em cada periodo):"); print(M.corr(method="spearman").round(2).to_string())
print("mesmos 15 maiores do IS, pesos por periodo:"); print(M.loc[M.IS.abs().sort_values(ascending=False).index[:15]].round(1).to_string())
