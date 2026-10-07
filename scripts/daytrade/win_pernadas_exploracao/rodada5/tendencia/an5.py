import numpy as np, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
N = pd.read_csv("nulo2_resultado.csv")
rows = []
for per in ("desc", "conf", "ambos"):
    g0 = N if per == "ambos" else N[N.per == per]
    for sc, gs in g0.groupby("scale"):
        out = {}
        for perm, gp in gs.groupby("perm"):
            f = gp[gp["mode"] == "favor"]; c = gp[gp["mode"] == "contra"]
            af = f.wins.sum() / f.res.sum() * 100; ac = c.wins.sum() / c.res.sum() * 100
            out[perm] = (af - ac, af, ac, f.soma.sum() / f.n.sum(), c.soma.sum() / c.n.sum(), f.n.sum(), c.n.sum())
        r = out[0]; z = np.array([v for k, v in out.items() if k > 0])
        rows.append(dict(per=per, escala=sc, ac_favor=r[1], ac_contra=r[2], dif_pp=r[0], nulo_dif=z[:, 0].mean(), nulo_dp=z[:, 0].std(),
                         p_dif=(z[:, 0] >= r[0]).mean(), esp_f=r[3], nulo_esp_f=z[:, 3].mean(), p_esp=(z[:, 3] >= r[3]).mean(),
                         esp_c=r[4], n_f=r[5], n_c=r[6]))
T = pd.DataFrame(rows); T.to_csv("nulo2_vs_real.csv", index=False)
print(T.round(2).to_string())
