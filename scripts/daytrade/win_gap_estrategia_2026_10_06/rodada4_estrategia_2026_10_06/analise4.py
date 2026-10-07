# -*- coding: utf-8 -*-
"""Rodada 4: mapas stop x alvo, censura, platos, nulo de maximo da grade, metades e escolha pelo CRITERIO.md."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
R2 = AQUI.parent / "rodada2_2026_10_06"
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(R2))
import analise as AN  # noqa: E402  (rodada 2: modo_a / modo_b / tabelas)
import sizing as Z  # noqa: E402
import run4 as G  # noqa: E402

N_NULO, SEED = 20000, 20261006
FILLS = G.FILLS


def censurada(a):
    return bool(a["recus"] or a["min_eq"] < Z.MARGEM)


def vizinhos(si, n=10):
    return [j for j in (si - 2, si - 1, si + 1, si + 2) if 0 <= j < n]


def heat(M, fmt, titulo):
    df = pd.DataFrame(M, index=[f"S{s}" for s in G.STOPS], columns=G.ALVOS)
    return titulo + "\n" + df.to_string(float_format=fmt)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    res = pickle.load(open(AQUI / "out" / "dia_resultados.pkl", "rb"))
    dias = sorted(res)
    D = len(dias)
    grade = G.grade()
    ids = [g["id"] for g in grade]
    rng = np.random.default_rng(SEED)
    S = rng.integers(0, 2, size=(N_NULO, D)).astype(np.float32)
    out, A = {}, {}
    for fm in FILLS:
        B = {c: AN.modo_b(res, dias, c, fm) for c in ids}
        Rm = np.stack([B[c]["real"] for c in ids], 1).astype(np.float32)
        Am = np.stack([B[c]["alt"] for c in ids], 1).astype(np.float32)
        nulo = S @ Rm + (1 - S) @ Am
        obs = Rm.sum(0)
        mu, sd = nulo.mean(0), nulo.std(0) + 1e-9
        tobs = (obs - mu) / sd
        M = ((nulo - mu) / sd).max(1)
        p_cel = ((nulo >= obs[None, :]).sum(0) + 1) / (N_NULO + 1)
        p_adj = np.array([((M >= tobs[j]).sum() + 1) / (N_NULO + 1) for j in range(len(ids))])
        out[fm] = dict(B=B, Rm=Rm, Am=Am, obs=obs, mu=mu, sd=sd, tobs=tobs, p_cel=p_cel, p_adj=p_adj)
        A[fm] = {c: AN.modo_a(res, dias, c, fm) for c in ids}
    h1 = np.array([d <= pd.Timestamp("2026-06-30").date() for d in dias])
    idx = {c: j for j, c in enumerate(ids)}
    nS, nA = len(G.STOPS), len(G.ALVOS)

    def mat(fn):
        return np.array([[fn(idx[G.cel_id(s, a)]) for a in G.ALVOS] for s in G.STOPS], float)

    tq = out["toque"]; at = out["atrav+1t"]
    liqB = mat(lambda j: tq["obs"][j]); liqB2 = mat(lambda j: at["obs"][j])
    ntr = mat(lambda j: tq["B"][ids[j]]["fil"].sum())
    rtr = liqB / np.where(ntr > 0, ntr, np.nan)
    pcel = mat(lambda j: tq["p_cel"][j]); padj = mat(lambda j: tq["p_adj"][j])
    tobs = mat(lambda j: tq["tobs"][j])
    h1m = mat(lambda j: tq["Rm"][h1, j].sum()); h2m = mat(lambda j: tq["Rm"][~h1, j].sum())
    cens = np.array([[censurada(A["toque"][G.cel_id(s, a)]) or censurada(A["atrav+1t"][G.cel_id(s, a)]) for a in G.ALVOS] for s in G.STOPS])
    recus = mat(lambda j: A["toque"][ids[j]]["recus"]); mineq = mat(lambda j: A["toque"][ids[j]]["min_eq"])
    Aliq = mat(lambda j: A["toque"][ids[j]]["liquido"])

    print(f"IS 2026-04-06..10-05, {D} pregoes, entrada V2 r0, R$1.000 (2 contratos no B), nulo {N_NULO} sorteios; grade {len(ids)} celulas\n")
    print(heat(liqB, "{:,.0f}".format, "=== LIQUIDO B (R$, 2 contratos, fill toque) — linhas = stop, colunas = alvo ==="))
    print("\n" + heat(rtr, "{:,.0f}".format, "=== R$ POR TRADE (B, toque) ==="))
    print("\n" + heat(liqB2, "{:,.0f}".format, "=== LIQUIDO B, fill atrav+1t ==="))
    print("\n" + heat(Aliq, "{:,.0f}".format, "=== LIQUIDO A (conta continua R$1.000, toque) ==="))
    print("\n" + heat(pcel, "{:.3f}".format, "=== p do nulo de direcao aleatoria por celula (B, toque) ==="))
    print("\n" + heat(padj, "{:.3f}".format, "=== p AJUSTADO pelo maximo da grade de 110 celulas (t, B, toque) ==="))
    print("\n" + heat(h1m, "{:,.0f}".format, "=== LIQUIDO B abr-jun (56 pregoes) ==="))
    print("\n" + heat(h2m, "{:,.0f}".format, "=== LIQUIDO B jul-out (64 pregoes) ==="))
    print("\n=== CENSURA MODO A (R$1.000; 'C' = censurada em toque ou atrav+1t: ordens recusadas ou caixa minimo < R$100) ===")
    print(pd.DataFrame(np.where(cens, "C", "."), index=[f"S{s}" for s in G.STOPS], columns=G.ALVOS).to_string())
    print(f"celulas censuradas: {int(cens.sum())}/{cens.size}")
    print("\n" + heat(recus, "{:.0f}".format, "ordens recusadas por capital (A, toque)"))
    print("\n" + heat(mineq, "{:,.0f}".format, "caixa minimo A (toque, MtM aprox.)"))

    # plato
    print("\n=== PLATO por alvo (vizinhos = stops a +-1 e +-2; 'acima do nulo' = p da celula <= 0,05; positivo = liquido B > 0) ===")
    plato = {}
    rows = []
    for ai, a in enumerate(G.ALVOS):
        col = liqB[:, ai]
        for si, s in enumerate(G.STOPS):
            nb = vizinhos(si)
            med = float(np.median([col[j] for j in nb]))
            plato[(si, ai)] = dict(med=med, nb=nb, pico=col[si] > 1.5 * med if med > 0 else (col[si] > 0))
        pos = int((col > 0).sum()); acima = int(((col > 0) & (pcel[:, ai] <= 0.05)).sum())
        n700 = [1, 2, 3]  # 600,800 e vizinhos +-2 de 700 (indice 4): 500,600,800,900
        nb700 = vizinhos(4)
        rows.append(dict(alvo=a, stops_positivos=f"{pos}/10", stops_pos_e_acima_nulo=f"{acima}/10",
                         viz700_positivos=f"{sum(col[j] > 0 for j in nb700)}/4", viz700_acima_nulo=f"{sum((col[j] > 0) and (pcel[j, ai] <= 0.05) for j in nb700)}/4",
                         liq700=round(col[4]), mediana_viz700=round(plato[(4, ai)]['med']), razao_700_sobre_mediana=round(col[4] / plato[(4, ai)]['med'], 2) if plato[(4, ai)]['med'] else float('nan'),
                         pico700=bool(plato[(4, ai)]['pico'])))
    print(pd.DataFrame(rows).to_string(index=False))

    # selecao
    print("\n=== ESCOLHA (CRITERIO.md) ===")
    cand = []
    for ai, a in enumerate(G.ALVOS):
        for si, s in enumerate(G.STOPS):
            nb = vizinhos(si)
            j = idx[G.cel_id(s, a)]
            if len(nb) < 3:
                continue
            cid = ids[j]
            ok2 = (not censurada(A["toque"][cid])) and (not censurada(A["atrav+1t"][cid])) and \
                  np.mean([not (censurada(A["toque"][G.cel_id(G.STOPS[k], a)]) or censurada(A["atrav+1t"][G.cel_id(G.STOPS[k], a)])) for k in nb]) >= 0.8
            ok3 = liqB[si, ai] > 0 and liqB2[si, ai] > 0 and h1m[si, ai] > 0 and h2m[si, ai] > 0 and np.mean([liqB[k, ai] > 0 for k in nb]) >= 0.8
            ok4 = pcel[si, ai] <= 0.05
            med = plato[(si, ai)]["med"]
            ok5 = not plato[(si, ai)]["pico"]
            minv = min([liqB[k, ai] for k in nb] + [liqB[si, ai]])
            cand.append(dict(id=cid, ok_censura=ok2, ok_positivo=ok3, ok_p=ok4, ok_nao_pico=ok5, score=med, minimo=minv, liq=liqB[si, ai]))
    C = pd.DataFrame(cand)
    C["elegivel"] = C.ok_censura & C.ok_positivo & C.ok_p & C.ok_nao_pico
    print(f"candidatas com >= 3 vizinhos: {len(C)}; elegiveis: {int(C.elegivel.sum())}")
    print(C[C.elegivel].sort_values(["score", "minimo"], ascending=False).head(12).to_string(index=False, float_format=lambda x: f"{x:,.1f}"))
    print("\nreprovacoes por criterio (candidatas):", {k: int((~C[k]).sum()) for k in ("ok_censura", "ok_positivo", "ok_p", "ok_nao_pico")})
    escolha = None
    if C.elegivel.any():
        e = C[C.elegivel].sort_values(["score", "minimo"], ascending=False).iloc[0]
        escolha = e.id
        print("\nCELULA ESCOLHIDA:", escolha, "| pontuacao (mediana dos vizinhos) R$", round(e.score), "| liquido da celula R$", round(e.liq), "| minimo celula+vizinhos R$", round(e.minimo))
    else:
        print("\nNenhuma celula elegivel pelo criterio.")
    # nulo de maximo / metades resumo
    jb = int(np.argmax(tq["tobs"]))
    print(f"\n=== SELECAO NA GRADE === melhor t: {ids[jb]} t={tq['tobs'][jb]:.2f} p celula={tq['p_cel'][jb]:.4f} p ajustado={tq['p_adj'][jb]:.4f}; celulas com p<0,05: {(tq['p_cel']<0.05).sum()}/{len(ids)}; p ajustado<0,05: {(tq['p_adj']<0.05).sum()}")
    if escolha:
        j = idx[escolha]
        print(f"escolhida: t={tq['tobs'][j]:.2f} p celula={tq['p_cel'][j]:.4f} p ajustado={tq['p_adj'][j]:.4f}; abr-jun {tq['Rm'][h1, j].sum():,.0f} | jul-out {tq['Rm'][~h1, j].sum():,.0f}")
    tot1 = tq["Rm"][h1].sum(0); tot2 = tq["Rm"][~h1].sum(0)
    rk = lambda x: pd.Series(x).rank().to_numpy()
    print(f"metades: correlacao de postos entre as 110 celulas = {np.corrcoef(rk(tot1), rk(tot2))[0,1]:.2f}; positivas nas duas: {int(((tot1>0)&(tot2>0)).sum())}/{len(ids)}; so' numa: {int(((tot1>0)^(tot2>0)).sum())}; nenhuma: {int(((tot1<=0)&(tot2<=0)).sum())}")
    print("top 10 abr-jun:", [ids[j] for j in np.argsort(-tot1)[:10]]); print("top 10 jul-out:", [ids[j] for j in np.argsort(-tot2)[:10]])
    pickle.dump(dict(ids=ids, liqB=liqB, liqB2=liqB2, rtr=rtr, pcel=pcel, padj=padj, h1m=h1m, h2m=h2m, cens=cens, Aliq=Aliq, escolha=escolha, dias=dias,
                     plato={f"{k}": v for k, v in plato.items()}, C=C, tobs=tobs, ntr=ntr),
                open(AQUI / "out" / "analise4.pkl", "wb"))
    pickle.dump(dict(out=out, A=A, dias=dias, ids=ids), open(AQUI / "out" / "analise4_full.pkl", "wb"))
    json.dump(dict(escolha=escolha), open(AQUI / "out" / "escolha.json", "w"))


if __name__ == "__main__":
    main()
