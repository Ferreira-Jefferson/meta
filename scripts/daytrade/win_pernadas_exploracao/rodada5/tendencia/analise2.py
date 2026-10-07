"""Passo 2: confirmacao (jul-ago) das regras congeladas + agregado da tendencia na confirmacao."""
import json
import numpy as np, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 400)
R = pd.read_csv("grade_resultado.csv")
R["X"] = R.X.astype(str)
fro = json.load(open("congelado_ANTES_da_confirmacao.json"))["celulas"]
cols = ["n", "fill", "acerto", "be_emp", "esp", "lo", "hi", "brl", "mpos", "seqperd", "ops_dia", "unres"]
rows = []
for f in fro:
    m = (R.scale == f["scale"]) & (R["mode"] == f["mode"]) & (R.filt == f["filt"]) & (R.X == f["X"]) & (R.stop == f["stop"]) & (R.alvo == f["alvo"])
    for conv in ("cons", "otim"):
        r = {"regra": f"{f['scale']}|{f['filt']}|X{f['X']}|S{f['stop']}|A{f['alvo']}", "conv": conv}
        for per in ("desc", "conf", "set"):
            x = R[m & (R.conv == conv) & (R.per == per)].iloc[0]
            for c in ("n", "acerto", "be_emp", "esp", "lo", "hi", "mpos"):
                r[f"{c}_{per}"] = x[c]
        rows.append(r)
T = pd.DataFrame(rows)
print(T[T.conv == "cons"].round(3).to_string())
print(T[T.conv == "otim"][["regra", "n_desc", "esp_desc", "n_conf", "esp_conf", "esp_set"]].round(2).to_string())
T.to_csv("congeladas_desc_conf.csv", index=False)

# agregado de tendencia por periodo (cons, filt todos)
key = ["X", "stop", "alvo"]
out = []
for per in ("desc", "conf", "set"):
    d = R[(R.per == per) & (R.conv == "cons") & (R.filt == "todos")]
    none = d[d["mode"] == "none"].set_index(key)
    for sc in sorted(set(d.scale) - {"-"}):
        f = d[(d.scale == sc) & (d["mode"] == "favor")].set_index(key)
        c = d[(d.scale == sc) & (d["mode"] == "contra")].set_index(key)
        j = f.join(c, lsuffix="_f", rsuffix="_c")
        nulo = f.nulo.mean()
        wf = (j.acerto_f * j.n_f).sum() / j.n_f.sum(); wc = (j.acerto_c * j.n_c).sum() / j.n_c.sum()
        out.append(dict(per=per, escala=sc, nulo=nulo, acerto_favor=j.acerto_f.mean(), acerto_contra=j.acerto_c.mean(),
                        acerto_nenhum=none.acerto.mean(), dif_pp=(j.acerto_f - j.acerto_c).mean() * 100,
                        favor_gt_contra=(j.acerto_f > j.acerto_c).mean(),
                        esp_favor=j.esp_f.mean(), esp_contra=j.esp_c.mean(), esp_nenhum=none.esp.mean(),
                        n_favor=j.n_f.mean(), n_contra=j.n_c.mean()))
A = pd.DataFrame(out)
A.to_csv("agregado_por_periodo.csv", index=False)
for per in ("desc", "conf", "set"):
    print("\n==", per)
    print(A[A.per == per].drop(columns="per").round(3).to_string())
