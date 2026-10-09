import json
import numpy as np, pandas as pd
exec(open("analise.py", encoding="utf-8").read().split("# teto por dia")[0].replace("print(", "(lambda *a, **k: None)("))
ops = ops.copy()
est = pd.DataFrame(list(ops.est)); est.index = ops.index
ops = pd.concat([ops.drop(columns="est"), est], axis=1)
ops["dia_lado_pos"] = np.where(ops.causa == "posicao_aberta", np.where(ops.pos_lado == ops.lado, "mesmo_lado(piramida)", "lado_oposto"), ops.causa)
ops["sub"] = ops.causa
m = ops.causa == "posicao_aberta"
ops.loc[m, "sub"] = "posicao_" + np.where(ops[m].pos_lado == ops[m].lado, "mesmo_lado", "lado_oposto") + np.where(ops[m].pos_enchida, "_enchida", "_pendente")
print("=== por causa (dedupe regra+lado+45min) ===")
def tab(d, by):
    return d.groupby(by).agg(n=("brl", "size"), ganh=("brl", lambda s: (s > 0).sum()), perd=("brl", lambda s: (s < 0).sum()), zero=("brl", lambda s: (s == 0).sum()),
                             na_mesa=("brl", lambda s: s[s > 0].sum()), evitou=("brl", lambda s: s[s < 0].sum()), liquido=("brl", "sum")).round(0)
print(tab(ops, "sub").to_string())
print(tab(ops, "causa").to_string(), "\nTOTAL", round(ops.brl.sum()))
# bruto sem dedupe (para comparar com 6057 / 2270)
raw = df.copy(); raw["ciclo"] = raw.ciclo
for c in (1, 2):
    rr = raw[(raw.causa == "veto") & (raw.ciclo == c)]
    print("sem dedupe veto ciclo", c, len(rr), round(rr.brl.sum()), "| dedupe", len(ops[(ops.causa == "veto") & (ops.ciclo == c)]), round(ops[(ops.causa == "veto") & (ops.ciclo == c)].brl.sum()))
print("veto vende_rompimento_stop_curto  bruto:", len(raw[raw.vetos.map(lambda v: any("vende_rompimento_stop_curto" in x for x in v)) & (raw.causa == "veto")]),
      round(raw[raw.vetos.map(lambda v: any("vende_rompimento_stop_curto" in x for x in v)) & (raw.causa == "veto")].brl.sum()))
sc = ops[(ops.causa == "veto") & ops.vetos.map(lambda v: any("vende_rompimento_stop_curto" in x for x in v))]
print("   dedupe:", len(sc), round(sc.brl.sum()), "dias:", sc.dia.nunique())
# separacao
feats = ["ef_dia", "ef_manha", "desloc", "vol_rec", "vol_rel", "hora", "dist_vwap", "perna", "dir_dia"]
def auc(x, y):  # P(x_gan > x_perd)
    a = x[y > 0].dropna().values; b = x[y < 0].dropna().values
    if len(a) < 3 or len(b) < 3: return np.nan
    r = pd.Series(np.concatenate([a, b])).rank().values
    return (r[:len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b))
def sep(d, nome):
    d = d[d.brl != 0]
    print(f"\n--- {nome}: n={len(d)} ganh={int((d.brl>0).sum())} perd={int((d.brl<0).sum())} liq={round(d.brl.sum())}")
    rows = []
    for f in feats:
        g = d[d.brl > 0][f]; p = d[d.brl < 0][f]
        q = pd.qcut(d[f], 3, labels=False, duplicates="drop")
        tq = d.groupby(q).brl.agg(["size", "sum", lambda s: (s > 0).mean()]).round(2)
        rows.append(dict(f=f, med_gan=round(g.median(), 2), med_perd=round(p.median(), 2), AUC=round(auc(d[f], d.brl), 2),
                         tercis_liq=" | ".join(f"{int(r['sum'])}({r['<lambda_0>']:.0%})" for _, r in tq.iterrows())))
    print(pd.DataFrame(rows).to_string(index=False))
sep(ops[ops.causa == "veto"], "VETO")
sep(ops[ops.causa == "posicao_aberta"], "POSICAO ABERTA")
sep(ops[(ops.causa == "posicao_aberta") & (ops.pos_lado == ops.lado)], "POSICAO mesmo lado")
sep(ops[ops.causa == "dois_lados"], "DOIS LADOS")
sep(ops[ops.causa.isin(["veto", "posicao_aberta", "dois_lados", "teto_ops"])], "TODAS BLOQUEADAS")
# separacao por ciclo 0+1 -> 2 : AUC estavel?
for nome, d in (("VETO", ops[ops.causa == "veto"]),):
    for cs in ([0, 1], [2]):
        dd = d[d.ciclo.isin(cs)]
        print(nome, cs, {f: round(auc(dd[f], dd.brl), 2) for f in feats})
# lado
print(tab(ops[ops.causa == "veto"], "lado").to_string())
print(tab(ops, "tipo").to_string())
ops.to_pickle("ops.pkl")
