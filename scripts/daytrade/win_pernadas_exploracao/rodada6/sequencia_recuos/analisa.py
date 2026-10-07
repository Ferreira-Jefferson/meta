"""analisa.py -- tabelas. uso: analisa.py <per: desc|conf|set> <T> <div>
Imprime e grava out_txt/tabelas_{per}_T{T}_d{div}.txt"""
import sys, os
import numpy as np, pandas as pd
import lib
from lib import *

per = sys.argv[1]; T = int(sys.argv[2]); div = int(sys.argv[3])
BASE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE, "out_txt"), exist_ok=True)
f = open(os.path.join(BASE, "out_txt", f"tabelas_{per}_T{T}_d{div}.txt"), "w", encoding="utf-8")
(rec, trd), nulls = carrega(T, div, per)
NR = [n[0] for n in nulls]; NT = [n[1] for n in nulls]
m = T / div
cab = f"periodo={per} T={T} m={m:.0f} dias={rec.dia.nunique()} sorteios={len(nulls)}"
print(cab, flush=True); f.write(cab + "\n")


def fp(rec_, x):
    d = rec_[rec_.elig & rec_.res.isin(["S", "M"])].copy()
    if x is not None:
        d = d[d.depth >= x * d.A]
        d = d[x * d.A < T]
    d0 = m if x is None else x * d.A
    d["val"] = (d.res == "S").astype(float)
    d["nul"] = (T - d0) / T
    d["x"] = "conf" if x is None else f"{int(round(x*100))}%"
    return d


XS = [None, .23, .38, .50, .62, .79]
def fpall(R):
    return pd.concat([fp(R, x) for x in XS])


A = fpall(rec); AN = [fpall(n) for n in NR]
mostra(compara(A, AN, ["x"], "val", "nul"), "T1a  P(recuo supera o topo H antes de morrer | recuo ja atingiu x% de A)  [formula = (T-d)/T]", f)
mostra(compara(A, AN, ["x", "Abin"], "val", "nul", ic=False), "T1b  idem por tamanho do avanco A", f)
mostra(compara(A, AN, ["x", "hb"], "val", "nul", ic=False), "T1c  idem por horario (relogio)", f)
mostra(compara(A, AN, ["x", "hb_ny"], "val", "nul", ic=False), "T1d  idem por horario alinhado a abertura de NY", f)
mostra(compara(A, AN, ["x", "k"], "val", "nul", ic=False), "T5a  idem por ORDEM do recuo (entre elegiveis)", f)


def pr(trd_):
    d = trd_[(trd_.j == 1) & trd_.elig & trd_.first_ok.notna()].copy()
    d["val"] = d.first_ok
    d["nul"] = d.risk / d.r
    return d


P1 = pr(trd); P1N = [pr(n) for n in NT]
mostra(compara(P1, P1N, ["rb"], "val", "nul"), "T2a  P(supera de primeira) por profundidade do 1o fundo (% de A) [formula = risco/r]", f)
mostra(compara(P1, P1N, ["rb", "Abin"], "val", "nul", ic=False), "T2b  idem x A", f)
mostra(compara(P1, P1N, ["rb", "hb"], "val", "nul", ic=False), "T2c  idem x horario", f)
mostra(compara(P1, P1N, ["k"], "val", "nul"), "T5b  P(supera de primeira) por ORDEM do recuo", f)
mostra(compara(P1, P1N, ["k", "Abin"], "val", "nul", ic=False), "T5c  por ordem x A", f)
mostra(compara(P1, P1N, ["vsprev"], "val", "nul"), "T4a  P(supera de primeira): 1o fundo menor/maior que o recuo anterior", f)
mostra(compara(P1, P1N, ["vsprev", "Abin"], "val", "nul", ic=False), "T4b  idem x A", f)


def tent(R):
    d = R[R.elig & R.res.isin(["S", "M"])].copy()
    d["tc"] = np.where(d.att >= 4, "4+", d.att.astype(int).astype(str))
    d["todos"] = "todos"
    return d


D = tent(rec); DN = [tent(n) for n in NR]


def dist(D_, DN_, keys):
    rows = []
    for tc in ["1", "2", "3", "4+"]:
        for col, nm in (("S", "supera"), ("M", "morre")):
            D_["v"] = ((D_.tc == tc) & (D_.res == col)).astype(float)
            for x in DN_:
                x["v"] = ((x.tc == tc) & (x.res == col)).astype(float)
            c = compara(D_, DN_, keys, "v", ic=False, minn=1)
            c = c.reset_index(); c["tent"] = tc; c["fim"] = nm
            rows.append(c)
    r = pd.concat(rows)
    return r.set_index(keys + ["tent", "fim"])[["n", "real", "nulo", "sd", "z"]].sort_index()


mostra(dist(D, DN, ["todos"]), "T3  n de tentativas e desfecho (fracao de TODOS os recuos elegiveis resolvidos)", f)
mostra(dist(D, DN, ["hb"]), "T3b  idem por horario", f)
mostra(dist(D, DN, ["k"]), "T3c  idem por ordem", f)


def seqtab(R):
    S_ = R[R.elig & (R.res == "S")].copy()
    S_["rA"] = S_.depth / S_.A
    S_["dur"] = S_.tfim - S_.tH
    return S_


S = seqtab(rec); SN = [seqtab(x) for x in NR]


def resumo(S_):
    return S_.groupby("k").agg(n=("depth", "count"), r_pts=("depth", "mean"), r_med=("depth", "median"), rA_med=("rA", "median"), dur_min=("dur", "median"))


tn = pd.concat([resumo(x) for x in SN]).groupby(level=0).mean()
mostra(resumo(S).join(tn, rsuffix="_nulo"), "T6  recuos COMPLETOS por ordem: profundidade (pts), % de A, duracao (min)  [real | nulo]", f)


def pares(R):
    S_ = R[R.elig & (R.res == "S")].copy().sort_values(["dia", "sgn", "ep", "k_total"])
    g = S_.groupby(["dia", "sgn", "ep"], sort=False)
    S_["nx_depth"] = g["depth"].shift(-1)
    S_["nx_k"] = g["k_total"].shift(-1)
    S_["nx_A"] = g["A"].shift(-1)
    S_["nx_tH"] = g["tH"].shift(-1)
    S_ = S_[S_.nx_k == S_.k_total + 1].copy()
    S_["val"] = (S_.nx_depth < S_.depth).astype(float)
    S_["nul"] = 0.5
    S_["ratio"] = S_.nx_depth / S_.depth
    S_["gap_min"] = S_.nx_tH - S_.tfim
    return S_


Q = pares(rec); QN = [pares(n) for n in NR]
mostra(compara(Q, QN, ["k"], "val", "nul"), "T7a  P(recuo k+1 < recuo k) (ambos completos, mesma pernada)", f)
mostra(compara(Q, QN, ["k", "Abin"], "val", "nul", ic=False), "T7b  idem x A", f)
mostra(compara(Q, QN, ["k", "hb"], "val", "nul", ic=False), "T7c  idem x horario", f)
Q["v"] = Q.ratio
for x in QN: x["v"] = x.ratio
mostra(compara(Q, QN, ["k"], "v", ic=False), "T7d  razao media recuo(k+1)/recuo(k)", f)
Q["v"] = Q.gap_min
for x in QN: x["v"] = x.gap_min
mostra(compara(Q, QN, ["k"], "v", ic=False), "T7e  tempo (min) entre o fim do recuo k (novo topo) e o inicio do k+1", f)


def corr_estrat(Q_):
    zs, ws, ns = [], [], []
    for _, g in Q_.groupby(["Abin", "hb"]):
        if len(g) < 12:
            continue
        r = g.depth.rank().corr(g.nx_depth.rank())
        if np.isnan(r):
            continue
        r = min(max(r, -.999), .999)
        zs.append(np.arctanh(r) * (len(g) - 3)); ws.append(len(g) - 3); ns.append(len(g))
    if not ws:
        return np.nan, 0
    return np.tanh(sum(zs) / sum(ws)), sum(ns)


rows = []
for k in ["1", "2", "3", "4+"]:
    r, n = corr_estrat(Q[Q.k == k])
    rn = [corr_estrat(x[x.k == k])[0] for x in QN]
    rows.append(dict(k=f"r{k} x proximo", n=n, rho_real=r, rho_nulo=np.nanmean(rn), sd_nulo=np.nanstd(rn), z=(r - np.nanmean(rn)) / np.nanstd(rn)))
mostra(pd.DataFrame(rows).set_index("k"), "T7f  correlacao de posto (Spearman) entre recuo k e k+1, estratificada por A x horario", f)


def tri(R):
    S_ = R[R.elig & (R.res == "S")].copy().sort_values(["dia", "sgn", "ep", "k_total"])
    g = S_.groupby(["dia", "sgn", "ep"], sort=False)
    S_["d2"] = g["depth"].shift(-1); S_["d3"] = g["depth"].shift(-2)
    S_["k2"] = g["k_total"].shift(-1); S_["k3"] = g["k_total"].shift(-2)
    S_ = S_[(S_.k2 == S_.k_total + 1) & (S_.k3 == S_.k_total + 2)].copy()
    S_["pad"] = np.where((S_.d2 < S_.depth) & (S_.d3 < S_.d2), "decrescente", np.where((S_.d2 > S_.depth) & (S_.d3 > S_.d2), "crescente", "misto"))
    return S_


TR = tri(rec); TRN = [tri(n) for n in NR]
cnt = pd.DataFrame({"n": TR.groupby("pad").size()}); cnt["frac"] = cnt.n / cnt.n.sum()
fr = pd.concat([x.groupby("pad").size() / len(x) for x in TRN], axis=1)
tt = cnt.join(fr.mean(axis=1).rename("frac_nulo")).join(fr.std(axis=1).rename("sd_nulo"))
tt["z"] = (tt.frac - tt.frac_nulo) / tt.sd_nulo
mostra(tt, "T7g  trios consecutivos (r1,r2,r3 completos): padrao  [formula RW iid: crescente 1/6, decrescente 1/6]", f)


def prox(R):
    d = R[R.elig & R.res.isin(["S", "M"]) & R.r_prev.notna() & R.r_prev2.notna()].copy()
    d["padprev"] = np.where(d.r_prev < d.r_prev2, "anteriores encolhendo", "anteriores crescendo")
    d["val"] = (d.res == "S").astype(float)
    d["nul"] = (T - m) / T
    d["alc_T"] = d.alcance / T
    return d


PX = prox(rec); PXN = [prox(n) for n in NR]
mostra(compara(PX, PXN, ["padprev"], "val", "nul"), "T4c  P(recuo supera) conforme os 2 recuos ANTERIORES encolheram ou cresceram", f)
mostra(compara(PX, PXN, ["padprev", "Abin"], "val", "nul", ic=False), "T4d  idem x A", f)
mostra(compara(PX, PXN, ["padprev", "hb"], "val", "nul", ic=False), "T4e  idem x horario", f)
mostra(compara(PX, PXN, ["padprev"], "alc_T", ic=False), "T4f  alcance restante (em T) a partir do topo do recuo, conforme padrao anterior", f)

AL = rec[rec.elig & (rec.causa_fim != "fim")].copy(); AL["alc_T"] = AL.alcance / T
ALN = [n[n.elig & (n.causa_fim != "fim")].assign(alc_T=lambda d: d.alcance / T) for n in NR]
mostra(compara(AL, ALN, ["k"], "alc_T", ic=False), "T5d  alcance (em T) a partir do topo do recuo, por ordem (pernadas ja terminadas)", f)
mostra(compara(AL, ALN, ["k", "hb"], "alc_T", ic=False), "T5e  idem x horario", f)


def geo(trd_, K):
    d = trd_[trd_.elig].copy()
    ganho = d.mfe >= K
    d["win"] = ganho.astype(float)
    d["R"] = np.where(ganho, K, np.where(d.stop == 1, -1.0, np.minimum(d.fimR, K)))
    d["nul"] = 1 / (K + 1)
    return d


for K in (3, 5, 10):
    G = geo(trd, K); GN = [geo(n, K) for n in NT]
    mostra(compara(G, GN, ["k"], "win", "nul"), f"T8-{K}a  P(alvo {K}R antes do stop em L) por ORDEM do recuo  [formula 1/(K+1)]", f)
    mostra(compara(G, GN, ["k"], "R", ic=False), f"T8-{K}a2  expectativa em R", f)
    mostra(compara(G, GN, ["hb"], "win", "nul", ic=False), f"T8-{K}b  por horario", f)
    mostra(compara(G, GN, ["vsprev"], "win", "nul", ic=False), f"T8-{K}c  1o fundo menor/maior que o recuo anterior", f)
    mostra(compara(G, GN, ["rb"], "win", "nul", ic=False), f"T8-{K}d  por profundidade (% de A)", f)
    mostra(compara(G, GN, ["Abin"], "win", "nul", ic=False), f"T8-{K}e  por A", f)
    mostra(compara(G[G.j == 1], [g_[g_.j == 1] for g_ in GN], ["k"], "win", "nul", ic=False), f"T8-{K}f  so 1a tentativa (j=1), por ordem", f)

txt = "CONTAGEM celulas=" + str(lib.CONT)
print(txt, flush=True)
f.write(txt + "\n"); f.close()
