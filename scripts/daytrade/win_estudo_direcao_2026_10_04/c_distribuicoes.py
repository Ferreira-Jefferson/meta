import pandas as pd, numpy as np
rows=[]
for tag in ("01","02","03"):
    D=pd.read_csv(f"c_dias_k{tag}.csv",sep=";",decimal=",",parse_dates=["dia"])
    for w,m in (("IS",D.dia<="2024-12-31"),("OOS",D.dia>="2025-01-01")):
        d=D[m]
        for nm,sel in (("real",d.rep==-1),("nulo",d.rep>=0)):
            x=d[sel]
            for var in ("n_legs","cross"):
                cap=26 if var=="n_legs" else 6
                if tag=="02" and var=="n_legs": cap=14
                if tag=="03" and var=="n_legs": cap=9
                v=x[var].clip(upper=cap)
                f=v.value_counts(normalize=True).sort_index()
                for kv,p in f.items(): rows.append(dict(k_atr=int(tag)/10,janela=w,serie=nm,var=var,valor=kv,teto=cap,freq=p))
R=pd.DataFrame(rows); R.to_csv("c_distribuicoes.csv",sep=";",decimal=",",index=False)
for tag in (0.1,0.2,0.3):
  for var in ("n_legs","cross"):
    t=R[(R.k_atr==tag)&(R["var"]==var)].pivot_table(index="valor",columns=["janela","serie"],values="freq").fillna(0)
    print(tag,var);print((t*100).round(1).to_string())
d=pd.read_csv("c_dias_k02.csv",sep=";",decimal=",",parse_dates=["dia"]);d=d[d.rep==-1]
print(len(d),d.nb.describe().round(0).to_dict())
