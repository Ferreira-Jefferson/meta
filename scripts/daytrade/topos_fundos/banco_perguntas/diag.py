import io, contextlib, numpy as np, pandas as pd
with contextlib.redirect_stdout(io.StringIO()):
    from passo4 import *
from medir import load
T = soma.T; Z = soma.Z
print("\n##### (c1) os pesos se repetem fora? (lift por pergunta direcional, n>=100 no IS e OOS)")
d = T[(T.lado) & (T.n_IS >= 100) & (T.n_OOS >= 100)]
for a, b_ in (("IS", "OOS"), ("IS", "virgem")):
    dd = d[(d[f"n_{b_}"] >= 30)]
    print(f"{a} x {b_}: n={len(dd)} perguntas; correlação dos lifts {dd[f'lift_{a}'].corr(dd[f'lift_{b_}']):.2f}; mesmo sinal em {(np.sign(dd[f'lift_{a}'])==np.sign(dd[f'lift_{b_}'])).mean()*100:.0f}% (acaso = 50%); |lift| médio {a}={dd[f'lift_{a}'].abs().mean()*100:.2f}pp {b_}={dd[f'lift_{b_}'].abs().mean()*100:.2f}pp")
big = d[d.lift_IS.abs() >= 0.01]
print(f"só as com |lift IS| >= 1pp (n={len(big)}): sinal igual no OOS em {(np.sign(big.lift_IS)==np.sign(big.lift_OOS)).mean()*100:.0f}%; no virgem em {(np.sign(big.lift_IS)==np.sign(big.lift_virgem)).mean()*100:.0f}%")

print("\n##### (c2) redundância: pares mais correlacionados entre as respostas (OOS, velas-lado; conjunto D)")
z = Z["OOS"]; E = z["elig"]; ids = [i for i in soma.IDS if T.loc[i, "lado"] and T.loc[i, "classe"] != "SEM AMOSTRA"]
M = soma.X(z, ids)[E].reshape(-1, len(ids)); C = np.corrcoef(M.T); iu = np.triu_indices(len(ids), 1)
pares = sorted(zip(C[iu], np.array(ids)[iu[0]], np.array(ids)[iu[1]]), key=lambda x: -abs(x[0]) if x[0] == x[0] else 0)
print("top 12 |phi|:", "; ".join(f"{a}-{b_} {c:+.2f}" for c, a, b_ in pares[:12]))
ab = np.abs(C[iu]); print(f"pares com |phi|>0,5: {(ab>0.5).sum()} de {len(ab)}; >0,3: {(ab>0.3).sum()}")
idsA, wA = W[SETS["A"]]; MA = soma.X(z, idsA)[E].reshape(-1, len(idsA)); print(f"conjunto A: dp da soma = {np.std(MA@wA):.3f}; dp se as perguntas fossem independentes = {np.sqrt((MA.var(0)*wA**2).sum()):.3f}")

print("\n##### (c3) o alvo +-1 ATR representa o que a escada ganha?")
for p in ("IS", "OOS"):
    b, dias, raw, s = PR[p]; tr = operacao.operar(s, dias, stop.inicial_v41, stop.estrutura)
    y = soma.Z[p]["y"]; yy = np.where(tr.lado.to_numpy() == 1, y[tr.pos.to_numpy()], 1 - y[tr.pos.to_numpy()])
    x = tr.pts.to_numpy() * .2; srt = np.sort(x)[::-1]; k = max(1, int(round(.1 * len(x))))
    print(f"{p}: {len(tr)} ops; acerto do alvo ±1ATR nos sinais da escada = {np.nanmean(yy)*100:.1f}%; acerto real da operação = {(x>0).mean()*100:.1f}%; "
          f"R$/op médio = {x.mean():.0f}, mediana = {np.median(x):.0f}; top 10% das ops ({k}) = {srt[:k].sum()/x.sum()*100:.0f}% do lucro total; R$/op quando alvo+ = {np.nanmean(x[yy==1]):.0f}, alvo- = {np.nanmean(x[yy==0]):.0f}")
    print(f"    ganho médio {x[x>0].mean():.0f} x perda média {x[x<0].mean():.0f}; MFE médio (pts) {tr.mfe.mean():.0f} vs ATR M15 médio no sinal {np.nanmean(b.atr.to_numpy()[tr.pos.to_numpy()]):.0f}")

print("\n##### (c4) medida alternativa: resultado da própria operação (todos os sinais brutos da escada, cada um sozinho)")
ALT = {}
for p in ("IS", "OOS", "virgem"):
    b, dias, raw, s = PR[p]; z = Z[p]; pts = np.full(len(raw), np.nan)
    for k in range(len(raw)):
        r = operacao.operar(raw.iloc[[k]], dias, stop.inicial_v41, stop.estrutura)
        if len(r): pts[k] = r.pts.iloc[0] * .2
    side = np.where(raw.lado.to_numpy() == 1, 0, 1); pos = raw.pos.to_numpy()
    ALT[p] = (raw, pts, {i: (z[i][pos, side]) for i in soma.IDS})
    print(p, f"sinais brutos {len(raw)}, com operação {np.isfinite(pts).sum()}, R$/op médio {np.nanmean(pts):.1f}", flush=True)
rows = []
for i in soma.IDS:
    if not T.loc[i, "lado"]: continue
    rr = {"id": i}
    for p in ("IS", "OOS", "virgem"):
        raw, pts, A = ALT[p]; m = (A[i] == soma.EXP[i]) & np.isfinite(pts); o = (A[i] != soma.EXP[i]) & (A[i] >= 0) & np.isfinite(pts)
        rr[f"n_{p}"] = int(m.sum())
        if m.sum() >= 15 and o.sum() >= 15:
            dif = pts[m].mean() - pts[o].mean(); se = np.sqrt(pts[m].var(ddof=1) / m.sum() + pts[o].var(ddof=1) / o.sum()); rr[f"dif_{p}"] = dif; rr[f"t_{p}"] = dif / se
    rows.append(rr)
AL = pd.DataFrame(rows).set_index("id"); AL["lift_alvo_IS"] = T.lift_IS[AL.index] * 100
ok = AL.dropna(subset=["dif_IS", "dif_OOS"])
print(f"perguntas com amostra >=15: {len(ok)}; sinal igual IS/OOS na medida R$/op: {(np.sign(ok.dif_IS)==np.sign(ok.dif_OOS)).mean()*100:.0f}%; |t|>=2 no IS: {(ok.t_IS.abs()>=2).sum()}; destas, repetem sinal no OOS: {((ok.t_IS.abs()>=2)&(np.sign(ok.dif_IS)==np.sign(ok.dif_OOS))).sum()}")
print("concordância com o alvo ±1ATR: corr(lift alvo IS, dif R$/op IS) =", round(ok.lift_alvo_IS.corr(ok.dif_IS), 2))
print(ok.sort_values("t_IS", key=abs, ascending=False).head(12)[["n_IS", "dif_IS", "t_IS", "dif_OOS", "t_OOS", "dif_virgem", "lift_alvo_IS"]].round(1).to_string())
AL.to_pickle("alt_pts.pkl")
for k in ("A", "B", "L"):
    out = []
    for p in ("IS", "OOS", "virgem"):
        raw, pts, A = ALT[p]; s = Sc[k][p][raw.pos.to_numpy(), np.where(raw.lado.to_numpy() == 1, 0, 1)]; m = np.isfinite(pts)
        q = pd.qcut(pd.Series(s[m]).rank(method="first"), 4, labels=False).to_numpy()
        out.append(f"{p}: corr {np.corrcoef(s[m], pts[m])[0,1]:+.3f}; R$/op quartis Q1..Q4 = " + " ".join(f"{pts[m][q==j].mean():.0f}" for j in range(4)))
    print(f"[{k}]", " | ".join(out))

print("\n##### (c5) é só hora/lado/regime? topo-decil (corte IS) no OOS")
for k in ("A", "B"):
    thr = np.percentile(Sc[k]["IS"][Z["IS"]["elig"]].reshape(-1), 90)
    z = Z["OOS"]; E = z["elig"]; Y = sides(z); S = Sc[k]["OOS"]; top = (S >= thr) & E[:, None]
    mins = z["_mins"]; hb = np.digitize(mins, [660, 810, 960]); hn = ["09:30-11", "11-13:30", "13:30-16", "16+"]
    cut = np.nanpercentile(Z["IS"]["_ad"][Z["IS"]["elig"]], [33.3, 66.7]); rg = np.digitize(z["_ad"], cut)
    lines = []
    for nome, lab, nm in (("hora", [(hb == j) for j in range(4)], hn), ("regime ATRd", [(rg == j) for j in range(3)], ["vol baixa", "média", "alta"])):
        cells = []
        for j, mk in enumerate(lab):
            mm = mk[:, None] & top; bm = (mk & E)[:, None] & np.ones((1, 2), bool)
            cells.append(f"{nm[j]}: topo {Y[mm].mean()*100:.1f}% (n={mm.sum()}) / todas {Y[bm].mean()*100:.1f}%")
        lines.append(nome + " -> " + "; ".join(cells))
    ml = []
    for j, nm in ((0, "compra"), (1, "venda")):
        mm = np.zeros_like(top); mm[:, j] = top[:, j]; ml.append(f"{nm}: topo {Y[mm].mean()*100:.1f}% (n={mm.sum()})")
    sem = pd.Series(pd.to_datetime(z["_dia"], unit="D")).dt.to_period("Q").astype(str).to_numpy()
    ql = []
    for qn in np.unique(sem):
        mm = (sem == qn)[:, None] & top
        if mm.sum() >= 30: ql.append(f"{qn} {Y[mm].mean()*100:.0f}% ({mm.sum()})")
    print(f"[{k}] " + " | ".join(lines) + " | " + "; ".join(ml) + " | por trimestre: " + ", ".join(ql))

print("\n##### nulo da mão 2/1 aleatória (escada, 300 sorteios): total/queda/recup/FL/sharpe/pior mês, média [p5;p95]")
for p in PER:
    b, dias, raw, s = PR[p]; base = operacao.operar(s, dias, stop.inicial_v41, stop.estrutura); rng = np.random.default_rng(5)
    R_ = []
    for _ in range(300):
        t2 = base.copy(); t2["pts"] = np.where(rng.random(len(t2)) < .5, t2.pts, t2.pts * .5); d_ = painel(t2, b); R_.append([d_["total_R"], d_["pior_queda_R"], d_["recup"], d_["fl"], d_["sharpe"], d_["pior_mes_R"]])
    R_ = np.array(R_); print(p, "; ".join(f"{np.nanmean(R_[:,j]):.2f} [{np.nanpercentile(R_[:,j],5):.2f};{np.nanpercentile(R_[:,j],95):.2f}]" for j in range(6)))
