import pickle, numpy as np, pandas as pd, exc, agg, cand
vthr, ra = pickle.load(open("real_agg.pkl","rb")); nu = pickle.load(open("null_agg.pkl","rb"))
LV=[f"{int(r*100)}%" for r in exc.LEVELS]; AB=["150-250","250-400","400-750","750-2000"]
out=[]
def quant(w):
    q=ra[w][1]; n=nu[w][1].groupby(["lv","ab","h","kind"])[["q25","q50","q75","q90"]].mean().add_suffix("_nulo")
    return q.set_index(["lv","ab","h","kind"]).join(n).reset_index()
for w in ("desc","conf"):
    q=quant(w); q.to_csv(f"quantis_{w}.csv",index=False)
    out.append(f"\n### Quantis MFE/MAE ({w}) - pts a partir do ponto do recuo; real (nulo entre parenteses)\n")
    for h in ("60","E"):
        out.append(f"\nHorizonte {'60 min' if h=='60' else 'ate o fim do pregao'}\n")
        out.append("| A | r | n | MFE p25 | MFE p50 | MFE p75 | MFE p90 | MAE p25 | MAE p50 | MAE p75 | MAE p90 |\n|---|---|---|---|---|---|---|---|---|---|---|")
        for ab in range(4):
            for lv in (1,3,4,5):
                a=q[(q.lv==lv)&(q.ab==ab)&(q.h==h)&(q.kind=="mfe")]; b=q[(q.lv==lv)&(q.ab==ab)&(q.h==h)&(q.kind=="mae")]
                if a.empty or b.empty: continue
                a=a.iloc[0]; b=b.iloc[0]
                f=lambda r,k: f"{r[k]:.0f} ({r[k+'_nulo']:.0f})"
                out.append(f"| {AB[ab]} | {LV[lv]} | {int(a.n)} | "+" | ".join(f(a,k) for k in ("q25","q50","q75","q90"))+" | "+" | ".join(f(b,k) for k in ("q25","q50","q75","q90"))+" |")
# multiplos de A (real)
d,R=cand.W["desc"]; 
d=d.copy(); 
out.append("\n### MFE/A e MAE/A medianos, real (desc), horizonte 60 min e fim do pregao\n\n| A | r | MFE60/A | MAE60/A | MFEfim/A | MAEfim/A | P(MFEfim>=A) | P(MAEfim>=A) |\n|---|---|---|---|---|---|---|---|")
for ab in range(4):
    for lv in (1,3,4,5):
        g=d[(d.ab==ab)&(d.lv==lv)]
        out.append(f"| {AB[ab]} | {LV[lv]} | {np.nanmedian(g.mfe60/g.A):.2f} | {np.nanmedian(g.mae60/g.A):.2f} | {np.nanmedian(g.mfeE/g.A):.2f} | {np.nanmedian(g.maeE/g.A):.2f} | {(g.mfeE>=g.A).mean():.2f} | {(g.maeE>=g.A).mean():.2f} |")
open("tabelas_quantis.md","w",encoding="utf-8").write("\n".join(out)); print("\n".join(out)[:9000])
