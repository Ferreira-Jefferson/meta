"""Variacao D: SEM estimar pesos. Pontuacao = numero de respostas 'a favor' nas perguntas de tendencia/posicao (familia fixada a priori
pelo catalogo, antes de olhar resultados). So geometria, corte e K escolhidos no IS."""
import pickle, numpy as np, pandas as pd
from lib import *
from prep import GEOS
pd.set_option("display.width", 250)
fam = {r["id"]: r["fam"] for r in K.R}
TREND = [i for i in IDS if LADO[i] and (fam[i] in ("Tendência/momentum", "Posição no dia", "Existente D2", "Existente D3", "Existente D4", "Existente D5")
                                           or i in ("N24", "N16", "N17", "N19"))]
print("perguntas (", len(TREND), "):", TREND)
Z = {p: carrega(p) for p in PER}; RES = {p: pickle.load(open(f"res_{p}.pkl", "rb")) for p in PER}
def score(z):
    X = X_de(z); ix = [IDS.index(i) for i in TREND]; return X[:, :, ix].sum(2)
S = {p: score(Z[p]) for p in PER}; EL = {p: elegivel(Z[p]) for p in PER}
qI = pd.PeriodIndex(pd.to_datetime(Z["IS"]["_dia"].astype("datetime64[D]")), freq="Q").astype(str).to_numpy(); QS = sorted(set(qI))
rows = []
for g in GEOS:
    pts, te, ts = RES["IS"][g]
    for pc in (70, 80, 90, 95):
        cut = np.percentile(S["IS"][EL["IS"]].max(1), pc)
        for K_ in (1, 3, 99):
            sc = np.where(EL["IS"][:, None], S["IS"] + 0.0, np.nan)
            # desempate pelo lado com mais respostas; empate => sem entrada
            tie = S["IS"][:, 0] == S["IS"][:, 1]; sc = np.where(tie[:, None], np.nan, sc)
            tr = simula(sc, pts, te, ts, Z["IS"]["_dia"], cut, K_)
            if len(tr) < 100: continue
            qq = pd.Series(tr.pts.to_numpy()).groupby(qI[tr.i.to_numpy()]).sum().reindex(QS).fillna(0)
            rows.append(dict(geo=g, pc=pc, cut=cut, K=K_, ops=len(tr), tot=tr.pts.sum(), media_op=tr.pts.mean(), q_pos=(qq > 0).mean(), obj=qq.mean() - .5 * qq.std()))
T = pd.DataFrame(rows).sort_values("obj", ascending=False); print(T.head(8).round(1).to_string())
b = T.iloc[0]; g, cut, K_ = b.geo, b.cut, int(b.K)
print("\nESCOLHIDA no IS:", g, "corte", cut, "K", K_)
out = {}
for p in PER:
    z = Z[p]; pts, te, ts = RES[p][g]; tie = S[p][:, 0] == S[p][:, 1]
    sc = np.where(EL[p][:, None] & ~tie[:, None], S[p] + 0.0, np.nan); tr = simula(sc, pts, te, ts, z["_dia"], cut, K_)
    dias = pd.to_datetime(np.unique(z["_dia"]).astype("datetime64[D]")); pn = painel(tr, dias)
    tots, opsn = sorteio(pts, te, ts, z["_dia"], EL[p], len(tr), K_, np.random.default_rng(5))
    pn.update(nulo_media_R=tots.mean() * .4, nulo_p95_R=np.percentile(tots, 95) * .4, p_nulo=(np.sum(tots >= tr.pts.sum()) + 1) / 301, media_op_pts=tr.pts.mean())
    out[p] = pn
    q = pd.PeriodIndex(pd.to_datetime(z["_dia"].astype("datetime64[D]")), freq="Q").astype(str).to_numpy()
    print(p, "trimestres R$:", (pd.Series(tr.pts.to_numpy() * .4).groupby(q[tr.i.to_numpy()]).sum().round(0).astype(int)).to_dict())
print(pd.DataFrame(out).T.round(2).to_string())

# ---- vizinhanca (descritiva, NAO usada p/ escolher) e sobreposicao com a escada
import sys
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\topos_fundos")
import estrategia as ESC
print("\nVIZINHANCA (K=99), R$ 2 contratos [ops]:")
viz = {}
for g in GEOS:
    for pc in (70, 80, 90, 95):
        cut = np.percentile(S["IS"][EL["IS"]].max(1), pc); lin = {}
        for p in PER:
            pts, te, ts = RES[p][g]; tie = S[p][:, 0] == S[p][:, 1]
            sc = np.where(EL[p][:, None] & ~tie[:, None], S[p] + 0.0, np.nan); tr = simula(sc, pts, te, ts, Z[p]["_dia"], cut, 99)
            lin[p] = f"{tr.pts.sum()*.4:8.0f} [{len(tr)}]"
        viz[(g, pc)] = lin
print(pd.DataFrame(viz).T.to_string())
tr = None
for p in PER:
    z = Z[p]; pts, te, ts = RES[p][(1.5, 8)]; tie = S[p][:, 0] == S[p][:, 1]
    sc = np.where(EL[p][:, None] & ~tie[:, None], S[p] + 0.0, np.nan); tr = simula(sc, pts, te, ts, z["_dia"], 16.0, 99)
    e = ESC.rodar(p); sg = seg_idx(z["_dia"])
    g0 = np.array([sg[s] + t for s, t in zip(e.seg, e.t_ent)]); g1 = np.array([sg[s] + t for s, t in zip(e.seg, e.t_sai)]); l = np.where(e.lado.to_numpy() == 1, 0, 1)
    ov = sum(bool(((l == r.lado) & (g0 <= r.ts) & (g1 >= r.te)).any()) for r in tr.itertuples())
    print(p, "D ops", len(tr), "escada ops", len(e), "D sobrepostas com escada", ov)
