"""Fase 1 da v3: que perguntas v2 sao redundantes / mudam a decisao / associam ao resultado. Usa os logs sessoes_v2 (A e B, treino+validacao = 40 dias).
Descritivo (nao escolhe nada pelo resultado da validacao): a selecao final e declarada em perguntas_v3.md."""
from __future__ import annotations
import glob, json, sys
from pathlib import Path
import numpy as np, pandas as pd
AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
import perguntas_v2 as pv

MQ = [d["id"] for d in pv.M]
TIPO = {d["id"]: d["tipo"] for d in pv.M}
CATS = {d["id"]: list(d["crit"]) for d in pv.M if d["tipo"] == "choice"}


def feats(m):
    r = {}
    for q in MQ:
        v = m.get(q)
        if v is None:
            return None
        if TIPO[q] == "noul":
            r[q] = float(v)
        elif TIPO[q] == "score":
            r[q] = float(v["s"])
        else:
            for c in CATS[q]:
                r[f"{q}:{c}"] = float(v["p"].get(c, 0.0))
    return r


def carrega():
    rows, trades = [], []
    for g in ("A_treino", "A_validacao"):
        for f in sorted(glob.glob(str(AQUI / "sessoes_v2" / g / "2*.json"))):
            s = json.load(open(f, encoding="utf-8"))
            for p in s["pontos"]:
                m = p["jev"].get("m")
                ft = feats(m) if m else None
                if ft is None:
                    continue
                pa = m["acao"]["p"]
                ft.update(data=s["data"], k=p["k"], grupo=g, lado=pa.get("comprar", 0) - pa.get("vender", 0), fora=pa.get("fora", 0),
                          pos=bool(p["jev"].get("g")))
                rows.append(ft)
            for t in s["trades"]:
                trades.append(dict(data=s["data"], grupo=g, k_ent=t["k_ent"], lado=1 if t["lado"] == "compra" else -1, brl=t["brl"], n=t["n"],
                                   motivo=t["motivo"]))
    return pd.DataFrame(rows), pd.DataFrame(trades)


def ridge_cv(X, y, grp, lam=1.0):
    """R2 por validacao cruzada leave-day-out (autocorrelacao dentro do dia)."""
    datas = np.unique(grp)
    pred = np.zeros(len(y))
    for d in datas:
        te = grp == d
        Xt, yt = X[~te], y[~te]
        mu, sd = Xt.mean(0), Xt.std(0) + 1e-9
        A = (Xt - mu) / sd
        w = np.linalg.solve(A.T @ A + lam * len(yt) * 0.01 * np.eye(A.shape[1]), A.T @ (yt - yt.mean()))
        pred[te] = ((X[te] - mu) / sd) @ w + yt.mean()
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def main():
    df, tr = carrega()
    print(f"{len(df)} velas com resposta, {df.data.nunique()} dias, {len(tr)} trades")
    fc = [c for c in df.columns if c.split(":")[0] in MQ]
    grp = df.data.values
    out = {}
    for alvo in ("lado", "fora"):
        y = df[alvo].values
        X = df[fc].values
        full = ridge_cv(X, y, grp)
        res = {}
        for q in MQ:
            cols = [i for i, c in enumerate(fc) if c.split(":")[0] != q]
            res[q] = full - ridge_cv(X[:, cols], y, grp)       # perda de R2 ao tirar a pergunta
        out[alvo] = dict(r2_full=full, perda_drop_one=res)
        print(f"\nalvo = {alvo}: R2 (leave-day-out) com as 17 = {full:.3f}")
        for q, v in sorted(res.items(), key=lambda x: -x[1]):
            print(f"  tirar {q:<22} perda R2 {v:+.3f}")
        # selecao progressiva (greedy forward) so p/ descrever quanto das 17 basta
        sel, rest, hist = [], list(MQ), []
        for _ in range(len(MQ)):
            best = None
            for q in rest:
                cols = [i for i, c in enumerate(fc) if c.split(":")[0] in sel + [q]]
                r = ridge_cv(X[:, cols], y, grp)
                if best is None or r > best[1]:
                    best = (q, r)
            sel.append(best[0]); rest.remove(best[0]); hist.append((best[0], best[1]))
        out[alvo]["forward"] = hist
        print("  progressiva:", " > ".join(f"{q}({r:.2f})" for q, r in hist[:10]))
    # redundancia: resumo escalar por pergunta (direcional = P(alta)-P(baixa) quando existe)
    sc = pd.DataFrame(index=df.index)
    DIR = {"v2_dia_tipo": ("alta_dirigida", "baixa_dirigida"), "v2_estrutura": ("alta", "baixa"), "v2_h1": ("alta", "baixa"),
           "v2_preco_vs_ref": ("acima_de_ambos", "abaixo_de_ambos"), "v2_rompe_ontem": ("acima_com_volume", "abaixo_com_volume"),
           "v2_rompe_dia": ("rompeu_alta_com_volume", "rompeu_baixa_com_volume"), "v2_swing_rompido": ("acima_do_topo", "abaixo_do_fundo"),
           "v2_pullback": ("retomada_alta", "retomada_baixa"), "v2_extremo_novo": ("renovou_maxima", "renovou_minima")}
    for q in MQ:
        if q in DIR:
            sc[q] = df[f"{q}:{DIR[q][0]}"] - df[f"{q}:{DIR[q][1]}"]
        elif TIPO[q] == "choice":
            c0 = CATS[q][1] if q == "v2_gap" else CATS[q][-1]
            sc[q] = df[f"{q}:{CATS[q][0]}"] if q != "v2_seguimento" else df[f"{q}:seguiu"]
        else:
            sc[q] = df[q]
    cor = sc.rank().corr()
    print("\npares com |Spearman| >= 0,6 (resumo escalar por pergunta; direcionais = P(alta)-P(baixa)):")
    pares = []
    for i, a in enumerate(MQ):
        for b in MQ[i + 1:]:
            if abs(cor.loc[a, b]) >= 0.6:
                pares.append((a, b, float(cor.loc[a, b])))
    for a, b, c in sorted(pares, key=lambda x: -abs(x[2])):
        print(f"  {a:<22} {b:<22} {c:+.2f}")
    out["pares"] = pares
    out["corr_lado_resumo"] = {q: float(sc[q].rank().corr(df["lado"].rank())) for q in MQ}
    out["corr_fora_resumo"] = {q: float(sc[q].rank().corr(df["fora"].rank())) for q in MQ}
    print("\ncorrelacao do resumo da pergunta com lado (P(comprar)-P(vender)) e com fora:")
    for q in MQ:
        print(f"  {q:<22} lado {out['corr_lado_resumo'][q]:+.2f}  fora {out['corr_fora_resumo'][q]:+.2f}")
    # associacao com o resultado do trade: alinhamento da pergunta direcional com o lado do trade, na vela da decisao
    ents = []
    for _, t in tr.iterrows():
        d = df[(df.data == t.data) & (df.k < t.k_ent)]
        d = d[~d.pos]
        if d.empty:
            continue
        r = d.iloc[-1]
        e = dict(brl=t.brl / t.n, lado=t.lado, grupo=t.grupo)
        for q in MQ:
            e[q] = float(sc.loc[r.name, q]) * (t.lado if q in DIR else 1)
        ents.append(e)
    E = pd.DataFrame(ents)
    print(f"\nassociacao com o R$/contrato do trade ({len(E)} entradas; direcionais multiplicadas pelo lado do trade: + = a favor):")
    assoc = {}
    for q in MQ:
        c = float(E[q].rank().corr(E.brl.rank()))
        assoc[q] = c
        print(f"  {q:<22} rho {c:+.2f}")
    out["assoc_resultado"] = assoc
    out["n_entradas"] = len(E)
    (AQUI / "v3" / "analise_perguntas.json").write_text(json.dumps(out, ensure_ascii=False, default=float, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
