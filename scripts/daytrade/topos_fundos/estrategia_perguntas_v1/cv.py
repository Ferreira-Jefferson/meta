"""Validacao cruzada leave-one-quarter-out DENTRO do IS: escolhe geometria, modelo, complexidade, corte e K. Nao toca OOS/virgem."""
import pickle, itertools, numpy as np, pandas as pd
from lib import *
from prep import GEOS

z = carrega("IS"); R = pickle.load(open("res_IS.pkl", "rb"))
X = X_de(z); n = len(X); el = elegivel(z); dia = z["_dia"]; mins = z["_mins"]
hora = np.stack([(mins >= 960), (mins < 630), (mins >= 840) & (mins < 960)], 1).astype(np.float32)
XF = {"perg": X, "perg+hora": np.concatenate([X, np.repeat(hora[:, None, :], 2, 1)], 2)}
qtr = pd.PeriodIndex(pd.to_datetime(dia.astype("datetime64[D]")), freq="Q").astype(str).to_numpy()
QS = sorted(set(qtr))
MODELOS = {"ridge_all_300": lambda: Ridge(300), "ridge_all_3000": lambda: Ridge(3000), "ridge_all_30000": lambda: Ridge(30000),
           "ridge_rep_300": lambda: Ridge(300, True), "ridge_rep_3000": lambda: Ridge(3000, True),
           "boost_20": lambda: Boost(20), "boost_50": lambda: Boost(50)}


def oof(Xf, pts, modelo):
    sc = np.full((n, 2), np.nan)
    for q in QS:
        te_m = qtr == q
        tr_m = ~te_m
        rows = [(tr_m & el & np.isfinite(pts[:, s])) for s in (0, 1)]
        Xtr = np.concatenate([Xf[rows[0], 0], Xf[rows[1], 1]]); ytr = np.concatenate([pts[rows[0], 0], pts[rows[1], 1]])
        m = MODELOS[modelo]().fit(Xtr, ytr)
        for s in (0, 1):
            idx = np.where(te_m & el)[0]; sc[idx, s] = m.predict(Xf[idx, s])
    return sc


def avalia(sc, pts, te, ts, cut, K):
    tr = simula(sc, pts, te, ts, dia, cut, K)
    if len(tr) < 100: return None
    qq = pd.Series(tr.pts.to_numpy()).groupby(qtr[tr.i.to_numpy()]).sum().reindex(QS).fillna(0)
    return dict(ops=len(tr), tot=tr.pts.sum(), media_op=tr.pts.mean(), q_mean=qq.mean(), q_sd=qq.std(), q_pos=(qq > 0).mean(),
                obj=qq.mean() - 0.5 * qq.std())


if __name__ == "__main__":
    linhas = []; OOF = {}
    for g in GEOS:
        pts, te, ts = R[g]
        for fs, Xf in XF.items():
            for mo in MODELOS:
                sc = oof(Xf, pts, mo); OOF[(g, fs, mo)] = sc
                best = np.where(el, sc.max(1), np.nan)
                for pc in (50, 70, 80, 90, 95, 98):
                    cut = np.nanpercentile(best, pc)
                    for K_ in (1, 2, 3, 99):
                        r = avalia(sc, pts, te, ts, cut, K_)
                        if r: linhas.append(dict(geo=g, fs=fs, modelo=mo, pc=pc, cut=cut, K=K_, **r))
                print(g, fs, mo, "ok", flush=True)
    T = pd.DataFrame(linhas); T.to_pickle("cv_tabela.pkl"); pickle.dump(OOF, open("cv_oof.pkl", "wb"))
    pd.set_option("display.width", 250)
    print(T.sort_values("obj", ascending=False).head(25).round(1).to_string())
    print("\nmelhor por modelo:"); print(T.loc[T.groupby("modelo").obj.idxmax()].round(1).to_string())
    print("\nmelhor por geo:"); print(T.loc[T.groupby("geo").obj.idxmax()].round(1).to_string())
