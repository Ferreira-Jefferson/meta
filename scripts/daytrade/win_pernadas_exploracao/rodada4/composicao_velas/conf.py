import pickle, numpy as np, pandas as pd
FEATS, CONDS, OUT, cut, res = pickle.load(open("res.pkl", "rb"))
fr = pd.read_csv("regras_congeladas.csv")
rows = []
for _, r in fr.iterrows():
    i, j, k = FEATS.index(r.feat), CONDS.index(r.cond), OUT.index(r.out)
    d = {"regra": f"{r.feat}|{r.cond}|{r.out}", "disc_D": r.D, "disc_z": r.z, "disc_z0": r.D / r.nulSD}
    for nm in ("conf", "set"):
        rr, n, pt, nul = res[nm]; sd = np.nanstd(nul[:, i, j, k]); mu = np.nanmean(nul[:, i, j, k])
        d[nm + "_Ptop"], d[nm + "_Pbot"] = pt[i, j, k]; d[nm + "_n"] = f"{int(n[i,j,0])}/{int(n[i,j,1])}"
        d[nm + "_D"] = rr[i, j, k]; d[nm + "_z"] = (rr[i, j, k] - mu) / sd; d[nm + "_z0"] = rr[i, j, k] / sd
    rows.append(d)
o = pd.DataFrame(rows); o.to_csv("confirmacao.csv", index=False)
print(o.round(3).to_string())
print("confirma (conf_D>0 e conf_z0>1.65):", ((o.conf_D > 0) & (o.conf_z0 > 1.65)).sum(), "sinal igual:", (o.conf_D > 0).sum(), "de", len(o))
# todos os 696: sinal D disc vs conf
FE, CO, OU, cut, res2 = FEATS, CONDS, OUT, cut, res
rd, rc = res["disc"][0], res["conf"][0]
m = ~np.isnan(rd) & ~np.isnan(rc); print("corr D disc x conf (todos):", np.corrcoef(rd[m], rc[m])[0, 1], "n", m.sum())
