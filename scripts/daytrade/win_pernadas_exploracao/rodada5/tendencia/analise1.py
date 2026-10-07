"""Passo 1 (so DESCOBERTA): agregados favor x contra x nenhum, e congelamento das regras. Nao imprime confirmacao."""
import json
import numpy as np, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 400)
R = pd.read_csv("grade_resultado.csv")
D = R[(R.per == "desc")]
key = ["X", "stop", "alvo", "filt", "conv"]
# 1) efeito da tendencia na assertividade (todos, cons e otim): favor - contra e vs nenhum
out = []
for conv in ("cons", "otim"):
    d = D[(D.conv == conv) & (D.filt == "todos")]
    none = d[d["mode"] == "none"].set_index(key)
    for sc in sorted(d.scale.unique()):
        if sc == "-":
            continue
        f = d[(d.scale == sc) & (d["mode"] == "favor")].set_index(key)
        c = d[(d.scale == sc) & (d["mode"] == "contra")].set_index(key)
        j = f.join(c, lsuffix="_f", rsuffix="_c").join(none[["acerto", "esp", "n"]].rename(columns=lambda x: x + "_0"))
        out.append(dict(conv=conv, escala=sc,
                        acerto_favor=j.acerto_f.mean(), acerto_contra=j.acerto_c.mean(), acerto_nenhum=j.acerto_0.mean(),
                        dif_pp=(j.acerto_f - j.acerto_c).mean() * 100,
                        favor_gt_contra=(j.acerto_f > j.acerto_c).mean(),
                        esp_favor=j.esp_f.mean(), esp_contra=j.esp_c.mean(), esp_nenhum=j.esp_0.mean(),
                        n_favor=j.n_f.mean(), n_contra=j.n_c.mean(), n_nenhum=j.n_0.mean(),
                        pct_cel_favor_esp_pos=(j.esp_f > 0).mean(), pct_cel_contra_esp_pos=(j.esp_c > 0).mean()))
A = pd.DataFrame(out)
A.to_csv("agregado_desc.csv", index=False)
print(A.round(3).to_string())
# 2) congelamento: favor, cons, filt todos/cedo/vela; criterio: esp > 0 e limite inferior do IC > 0 em desc, n >= 150
c = D[(D.conv == "cons") & (D["mode"] == "favor") & (D.n >= 150)].copy()
pos = c[(c.lo > 0)].sort_values("esp", ascending=False)
print("\nCELULAS favor/cons com IC inferior > 0 na descoberta:", len(pos), "de", len(c))
print(pos.head(15)[["scale", "filt", "X", "stop", "alvo", "n", "acerto", "be_emp", "esp", "lo", "hi", "mpos"]].round(3).to_string())
top = c.sort_values("esp", ascending=False).head(12)
print("\nTOP 12 por esperanca (favor/cons):")
print(top[["scale", "filt", "X", "stop", "alvo", "n", "acerto", "be_emp", "esp", "lo", "hi", "mpos"]].round(3).to_string())
# regra de congelamento: top 8 por esperanca com lo>0 se houver, senao top 8 por esperanca
sel = (pos if len(pos) >= 8 else top).head(8)
fro = [dict(scale=r.scale, mode="favor", filt=r.filt, X=str(r.X), stop=int(r.stop), alvo=int(r.alvo)) for r in sel.itertuples()]
# referencia do dono: 100/750 por escala (favor, todos, X=150) tambem congelada para a confirmacao
json.dump(dict(criterio="favor/cons, n>=150, ordenado por esperanca na DESCOBERTA (jan-jun); lo>0 se >=8 celulas, senao top 8",
               celulas=fro), open("congelado_ANTES_da_confirmacao.json", "w"), indent=1)
print("\nfrozen ->", len(fro))
