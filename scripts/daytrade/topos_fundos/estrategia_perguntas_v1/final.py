"""Avaliacao final: congela config escolhida no IS (CV), treina no IS inteiro, aplica ao OOS e virgem."""
import pickle, sys, numpy as np, pandas as pd
from lib import *
from prep import GEOS
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\topos_fundos")
import estrategia as ESC
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)

CFG = {  # escolhidas no IS (cv.py): A = melhor objetivo; B/C = 2o e 3o desenho (geometria/modelo/conjunto de perguntas diferentes)
    "A ridge_rep3000 g(1,8) K99": dict(geo=(1.0, 8), fs="perg", modelo="ridge_rep_3000", pc=80, K=99),
    "B ridge_rep300+hora g(1,4) K1": dict(geo=(1.0, 4), fs="perg+hora", modelo="ridge_rep_300", pc=70, K=1),
    "C boost20 g(1.5,8) K1": dict(geo=(1.5, 8), fs="perg", modelo="boost_20", pc=80, K=1),
}
import cv as CV
Z = {p: carrega(p) for p in PER}; RES = {p: pickle.load(open(f"res_{p}.pkl", "rb")) for p in PER}
OOF = pickle.load(open("cv_oof.pkl", "rb")); T = pd.read_pickle("cv_tabela.pkl")


def Xfs(z, fs):
    X = X_de(z); m = z["_mins"]
    if fs == "perg": return X
    h = np.stack([(m >= 960), (m < 630), (m >= 840) & (m < 960)], 1).astype(np.float32)
    return np.concatenate([X, np.repeat(h[:, None, :], 2, 1)], 2)


def trimestres(tr, z, contratos=2):
    q = pd.PeriodIndex(pd.to_datetime(z["_dia"].astype("datetime64[D]")), freq="Q").astype(str).to_numpy()
    allq = sorted(set(q))
    if len(tr) == 0: return pd.Series(0.0, index=allq)
    return pd.Series(tr.pts.to_numpy() * contratos * 0.2).groupby(q[tr.i.to_numpy()]).sum().reindex(allq).fillna(0)


def sobreposicao(tr, per, z):
    e = ESC.rodar(per); sg = seg_idx(z["_dia"])
    e = e.assign(g0=[sg[s] + t for s, t in zip(e.seg, e.t_ent)], g1=[sg[s] + t for s, t in zip(e.seg, e.t_sai)],
                 l=np.where(e.lado == 1, 0, 1))
    n_ov = 0
    for r in tr.itertuples():
        m = e[(e.l == r.lado) & (e.g0 <= r.ts) & (e.g1 >= r.te)]
        n_ov += len(m) > 0
    return len(e), n_ov


def main():
    out = {}; rng = np.random.default_rng(11)
    for nome, c in CFG.items():
        g, fs, mo, pc, K_ = c["geo"], c["fs"], c["modelo"], c["pc"], c["K"]
        print("=" * 30, nome, flush=True)
        oofsc = OOF[(g, fs, mo)]; el = elegivel(Z["IS"])
        cut = float(np.nanpercentile(np.where(el, oofsc.max(1), np.nan), pc))
        # modelo final no IS inteiro
        pts_is = RES["IS"][g][0]; Xi = Xfs(Z["IS"], fs)
        r0 = [(el & np.isfinite(pts_is[:, s])) for s in (0, 1)]
        Xtr = np.concatenate([Xi[r0[0], 0], Xi[r0[1], 1]]); ytr = np.concatenate([pts_is[r0[0], 0], pts_is[r0[1], 1]])
        mod = CV.MODELOS[mo]().fit(Xtr, ytr)
        if mo.startswith("ridge"):
            nomes = IDS + (["h>=16h", "h<10:30", "h14-16"] if fs != "perg" else [])
            w = pd.Series(mod.w / mod.sd, index=[nomes[j] for j in mod.cols]).sort_values(key=abs, ascending=False)
            print("pesos (pts por contrato por resposta 'sim', top 20 de %d) intercepto %.1f:" % (len(w), mod.b0)); print(w.head(20).round(1).to_string())
            out[nome + "_pesos"] = w
        if mo.startswith("boost"):
            nomes = IDS
            for cur in mod.trees[:6]:
                print([(nomes[a[0]] + "=" + str(a[1]) + ("&" + nomes[b[0]] + "=" + str(b[1]) if b else ""), round(v, 1)) for a, b, v in cur])
        linhas = {}; trs = {}; qtab = {}
        for p in PER:
            z = Z[p]; pts, te, ts = RES[p][g]; elp = elegivel(z)
            if p == "IS": sc = oofsc
            else:
                Xp = Xfs(z, fs); sc = np.full((len(elp), 2), np.nan)
                for s in (0, 1):
                    ix = np.where(elp)[0]; sc[ix, s] = mod.predict(Xp[ix, s])
            tr = simula(sc, pts, te, ts, z["_dia"], cut, K_); trs[p] = tr
            dias_todos = pd.to_datetime(np.unique(z["_dia"]).astype("datetime64[D]"))
            pn = painel(tr, dias_todos)
            tots, opsn = sorteio(pts, te, ts, z["_dia"], elp, len(tr), K_, rng)
            tot_pts = tr.pts.sum()
            pn.update(nulo_media_R=tots.mean() * .4, nulo_p95_R=np.percentile(tots, 95) * .4, p_nulo=(np.sum(tots >= tot_pts) + 1) / (len(tots) + 1),
                      nulo_ops=opsn.mean(), media_op_pts=tr.pts.mean() if len(tr) else np.nan)
            nesc, nov = sobreposicao(tr, p, z); pn.update(escada_ops=nesc, minhas_sobrepostas=nov)
            linhas[p] = pn; qtab[p] = trimestres(tr, z)
        print("corte (pts previstos/contrato):", round(cut, 1))
        T1 = pd.DataFrame(linhas).T; print(T1.round(2).to_string())
        for p in PER: print(p, "trimestres R$:", qtab[p].round(0).astype(int).to_dict())
        out[nome] = (T1, qtab, trs, cut)
        # variante mao 1/2 (2 contratos se score >= p95 do OOF)
        cut2 = float(np.nanpercentile(np.where(el, oofsc.max(1), np.nan), 95)); mm = {}
        for p in PER:
            tr = trs[p].copy(); k = np.where(tr.sc >= cut2, 2, 1)
            x = tr.pts.to_numpy() * k * .2; mm[p] = dict(ops=len(tr), total_R=x.sum(), pior_queda_R=(np.maximum.accumulate(np.cumsum(x)) - np.cumsum(x)).max(),
                                                         frac_2c=(k == 2).mean())
        print("mão 1/2 (2 contratos se >= p95):"); print(pd.DataFrame(mm).T.round(2).to_string())
    pickle.dump(out, open("final_out.pkl", "wb"))


if __name__ == "__main__":
    main()
