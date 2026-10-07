"""Frente B, parte 1 e 3: entra ou nao pela probabilidade de acerto (walk-forward mensal), com a ordem de chegada (ideia 5) como feature.
Saidas: filtro_res.pkl (para o resultado.md), imprime tudo.  Uso: python run_filtro.py"""
import pickle
import numpy as np
import pandas as pd
from comum import *

rng = np.random.default_rng(7)
e = chegada(carrega())
D = monta(e)
y = e.y.to_numpy(); mes = e.mes.to_numpy(); est = e.estrategia.to_numpy()
rs = e.rs.to_numpy(); rsl = rs - CUSTO; saida = e.t_saida_ms.to_numpy()
peso_sel = (est != "Win_c1")          # Win_c1 e' a gemea do Win: nao entra na escolha do limiar
rsl_sel = np.where(peso_sel, rsl, 0.0)
MODELOS = ("tabela", "logit", "nota")

print("eventos", len(e), "| classes de chegada:", e.cheg.value_counts().sort_index().to_dict(), flush=True)

# ---- ideia 5 descritiva (nao escolhe nada): R$/op por classe e estrategia, metade 1 (jan-mai) e metade 2 (jun-out)
d5 = []
for s in ESTR:
    for c, nm in enumerate(["1a", "2a_lucro", "2a_prej", "contra"]):
        for h, (a, b) in enumerate([(1, 5), (6, 10)]):
            x = e[(e.estrategia == s) & (e.cheg == c) & (e.mes >= a) & (e.mes <= b)]
            d5.append(dict(estrategia=s, classe=nm, metade=h + 1, n=len(x), rs_op=x.rs.mean() if len(x) else np.nan, win=x.y.mean() if len(x) else np.nan))
d5 = pd.DataFrame(d5)
print(d5.pivot_table(index=["estrategia", "classe"], columns="metade", values=["n", "rs_op"]).round(1).to_string(), flush=True)

# ---- previsoes fora da amostra
P = previsoes_oos(D, y, MODELOS)
sel_oos = (mes >= 2) & peso_sel
aucs = {}; calib = {}
for k in MODELOS:
    p = P[k]
    aucs[k] = dict(geral=auc(y[sel_oos], p[sel_oos]))
    for s in CART:
        ss = sel_oos & (est == s)
        aucs[k][s] = auc(y[ss], p[ss])
    q = pd.qcut(pd.Series(p[sel_oos]).rank(method="first"), 5, labels=False)
    c = pd.DataFrame(dict(p=p[sel_oos], y=y[sel_oos], q=q.to_numpy())).groupby("q").agg(prevista=("p", "mean"), realizada=("y", "mean"), n=("y", "size"))
    calib[k] = c
    print(f"[{k}] AUC OOS geral {aucs[k]['geral']:.3f} | por estrategia " + " ".join(f"{s[:8]}={aucs[k][s]:.3f}" for s in CART), flush=True)
    print(c.round(3).to_string(), flush=True)

# ---- filtro walk-forward + controles
def metrica(keep):
    out = {}
    for s in ESTR + ["CART"]:
        m = (est == s) if s != "CART" else np.isin(est, CART)
        k = keep & m
        liq0 = rs[k].sum(); liq2 = rsl[k].sum()
        out[s] = (liq0, liq2, k.sum())
    return out

grupos = [idx for _, idx in pd.DataFrame(dict(m=mes, s=est)).groupby(["m", "s"]).indices.items()]
base = metrica(np.ones(len(e), bool))
res = {}
for k in MODELOS:
    keep, info = mantidos(mes, P[k], rsl_sel)
    res[k] = dict(keep=keep, info=info, met=metrica(keep))
    fr = 1 - keep[peso_sel & (mes >= MES_MIN_FILTRO)].mean()
    # sorteio
    sr = np.array([metrica(sorteio(grupos, keep, rng))["CART"][1] for _ in range(200)])
    sr_s = {s: np.array([0.0]) for s in ESTR}
    res[k]["sorteio_cart"] = sr
    res[k]["pct_cart"] = (sr < res[k]["met"]["CART"][1]).mean() * 100
    print(f"[{k}] limiares por mes (f): " + " ".join(f"m{m}:{f:.1f}" for m, f, t in info), flush=True)
    print(f"[{k}] CART sem filtro R$2 {base['CART'][1]:.0f} | filtro {res[k]['met']['CART'][1]:.0f} (n {res[k]['met']['CART'][2]}) | sorteio p50 {np.median(sr):.0f} p5 {np.percentile(sr,5):.0f} p95 {np.percentile(sr,95):.0f} | percentil {res[k]['pct_cart']:.0f}", flush=True)

# placebo: rotulos embaralhados dentro do mes
PL = {k: [] for k in MODELOS}
for r in range(200):
    yp = y.copy()
    for m in range(1, 11):
        ix = np.flatnonzero(mes == m); yp[ix] = y[rng.permutation(ix)]
    Pp = previsoes_oos(D, yp, MODELOS)
    for k in MODELOS:
        kp, _ = mantidos(mes, Pp[k], rsl_sel)
        PL[k].append(metrica(kp)["CART"][1])
    if r % 50 == 49:
        print("placebo", r + 1, flush=True)
for k in MODELOS:
    a = np.array(PL[k]); res[k]["placebo"] = a
    res[k]["pct_placebo"] = (a < res[k]["met"]["CART"][1]).mean() * 100
    print(f"[{k}] placebo p50 {np.median(a):.0f} p95 {np.percentile(a,95):.0f} | real {res[k]['met']['CART'][1]:.0f} no percentil {res[k]['pct_placebo']:.0f}", flush=True)

pickle.dump(dict(e=e, P=P, aucs=aucs, calib=calib, res=res, base=base, d5=d5), open(AQ / "filtro_res.pkl", "wb"))
print("pronto", flush=True)
