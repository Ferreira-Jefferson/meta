"""resumo.py <per> : tabela de autossemelhanca (9 configs T x m) com metricas-chave real x nulo (chain) [+ raw p/ T750 d5]."""
import sys
import numpy as np, pandas as pd
from lib import *

per = sys.argv[1]
rows = []
for T in (250, 500, 750):
    for div in (5, 4, 8):
        (rec, trd), nulls = carrega(T, div, per)
        NR = [n[0] for n in nulls]; NT = [n[1] for n in nulls]
        m = T / div

        def met(R, Tr):
            out = {}
            e = R[R.elig & R.res.isin(["S", "M"])]
            out["P(S|conf)"] = (e.res == "S").mean()
            j1 = Tr[(Tr.j == 1) & Tr.elig & Tr.first_ok.notna()]
            out["P(1a)"] = j1.first_ok.mean()
            out["P(1a)_k1"] = j1[j1.k == "1"].first_ok.mean()
            out["P(1a)_k4+"] = j1[j1.k == "4+"].first_ok.mean()
            S_ = R[R.elig & (R.res == "S")].sort_values(["dia", "sgn", "ep", "k_total"])
            g = S_.groupby(["dia", "sgn", "ep"], sort=False)
            S_ = S_.assign(nxd=g["depth"].shift(-1), nxk=g["k_total"].shift(-1))
            S_ = S_[S_.nxk == S_.k_total + 1]
            out["P(r2<r1)"] = (S_[S_.k == "1"].nxd < S_[S_.k == "1"].depth).mean()
            out["P(r(k+1)<r(k)) todos"] = (S_.nxd < S_.depth).mean()
            tr = Tr[Tr.elig & (Tr.j == 1)]
            for K in (3, 5, 10):
                out[f"P({K}R)"] = (tr.mfe >= K).mean()
            out["n_rec_eleg"] = len(e)
            return out
        r = met(rec, trd)
        mn = pd.DataFrame([met(a, b) for a, b in zip(NR, NT)])
        for k, v in r.items():
            if k == "n_rec_eleg":
                continue
            rows.append(dict(T=T, m=int(m), metrica=k, real=v, nulo=mn[k].mean(), sd=mn[k].std(), z=(v - mn[k].mean()) / mn[k].std()))
        rows.append(dict(T=T, m=int(m), metrica="n_rec_eleg", real=r["n_rec_eleg"], nulo=mn["n_rec_eleg"].mean(), sd=mn["n_rec_eleg"].std(), z=np.nan))
        print(T, div, "ok", flush=True)
df = pd.DataFrame(rows)
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 500)
out = df.pivot_table(index="metrica", columns=["T", "m"], values=["real", "nulo", "z"])
txt = df.round(3).to_string()
print(txt)
open(f"out_txt/resumo_{per}.txt", "w", encoding="utf-8").write(txt)
