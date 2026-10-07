"""Passo 3: nulo embaralhado, interacao com filtros (cedo/vela), Kelly e ruina das celulas congeladas."""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada4/decisao")
import motor
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 400)

# ---- nulo
N = pd.read_csv("nulo_resultado.csv")
N["X"] = N.X.astype(str)
e = N[N.tag == "escala"]
def agg(df):
    return dict(res=df.res.sum(), wins=df.wins.sum(), soma=df.soma.sum(), n=df.n.sum())
lin = []
for seed, g in e.groupby("seed"):
    for per in ("desc", "conf", "ambos"):
        gp = g if per == "ambos" else g[g.per == per]
        base = gp[gp["mode"] == "none"]; bn = agg(base)
        for sc in SC if (SC := sorted(set(gp.scale) - {"-"})) else []:
            f = agg(gp[(gp.scale == sc) & (gp["mode"] == "favor")]); c = agg(gp[(gp.scale == sc) & (gp["mode"] == "contra")])
            lin.append(dict(seed=seed, per=per, escala=sc, ac_f=f["wins"] / max(f["res"], 1), ac_c=c["wins"] / max(c["res"], 1),
                            ac_0=bn["wins"] / max(bn["res"], 1), esp_f=f["soma"] / max(f["n"], 1), esp_c=c["soma"] / max(c["n"], 1),
                            esp_0=bn["soma"] / max(bn["n"], 1), n_f=f["n"], n_c=c["n"]))
L = pd.DataFrame(lin)
L["dif_pp"] = (L.ac_f - L.ac_c) * 100
L["f_vs_0_pp"] = (L.ac_f - L.ac_0) * 100
L["c_vs_0_pp"] = (L.ac_c - L.ac_0) * 100
real = L[L.seed == 0].set_index(["per", "escala"])
nul = L[L.seed > 0]
rows = []
for (per, sc), r in real.iterrows():
    z = nul[(nul.per == per) & (nul.escala == sc)]
    rows.append(dict(per=per, escala=sc, ac_favor=r.ac_f * 100, ac_contra=r.ac_c * 100, ac_nenhum=r.ac_0 * 100,
                     dif_pp=r.dif_pp, nulo_dif_media=z.dif_pp.mean(), nulo_dif_dp=z.dif_pp.std(),
                     p_dif=(z.dif_pp >= r.dif_pp).mean(), f_vs_0=r.f_vs_0_pp, nulo_f_vs_0=z.f_vs_0_pp.mean(), p_f0=(z.f_vs_0_pp >= r.f_vs_0_pp).mean(),
                     esp_favor=r.esp_f, esp_contra=r.esp_c, esp_nenhum=r.esp_0, nulo_esp_f=z.esp_f.mean(), nulo_esp_f_p95=z.esp_f.quantile(.95),
                     n_f=r.n_f, n_c=r.n_c))
Rn = pd.DataFrame(rows)
Rn.to_csv("nulo_vs_real.csv", index=False)
print(Rn.round(2).to_string())
print("\nNULO: n seeds", nul.seed.nunique())
# congeladas no nulo
c = N[N.tag == "congelada"]
rows = []
for (sc, filt, X, S, A, per), g in c.groupby(["scale", "filt", "X", "S", "A", "per"]):
    r = g[g.seed == 0].iloc[0]; z = g[g.seed > 0]
    ez = z.soma / z.n.clip(lower=1)
    rows.append(dict(regra=f"{sc}|{filt}|X{X}|S{S}|A{A}", per=per, n=r.n, esp_real=r.soma / max(r.n, 1), nulo_media=ez.mean(), nulo_p95=ez.quantile(.95), p=(ez >= r.soma / max(r.n, 1)).mean()))
print(pd.DataFrame(rows).round(2).to_string())
pd.DataFrame(rows).to_csv("nulo_congeladas.csv", index=False)
