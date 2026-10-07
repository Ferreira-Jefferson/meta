import pandas as pd, numpy as np
exec(open("an.py").read().split("lines=[]")[0])
E=E[E.rise>=750].copy()
d=E[(E.X==250)]
print("MEDIANAS turn vs cont (X=250), pooled dirs")
rows=[]
for f in ["rise","dur","speed","leg_delta","vwapdist","rec_vrel","rec_nrel","rec_avgsz_rel","pre1_vrel","pre5_avgsz_rel","rsi_d","recsec","dropspeed","minopen","atr"]:
    a=d[d.turn==1][f].dropna();b=d[d.turn==0][f].dropna()
    rows.append((f,len(a),a.median(),a.quantile(.25),a.quantile(.75),len(b),b.median(),b.quantile(.25),b.quantile(.75)))
print(pd.DataFrame(rows,columns=["f","n_t","med_t","q1","q3","n_c","med_c","q1","q3"]).round(3).to_string())
print("cross states X=250 P(turn):")
for f in ["cross9_d","cross921_d","below21_d","cross9_chg","vwapcross"]:
    print(f,d.groupby(["sign",f]).turn.agg(["size","mean"]).round(2).to_dict("index"))
# terciles within hg
def terc(d,f):
    d=d.copy(); d["t"]=d.groupby("hg")[f].transform(lambda s: pd.qcut(s.rank(method="first"),3,labels=False) if len(s)>=6 else np.nan); return d.groupby(["sign","t"]).turn.agg(["size","mean"]).round(2)
for X in (250,500):
  for f in ["leg_delta","vwapdist","rec_vrel","rsi_d","rise"]:
    print("X",X,f);print(terc(E[E.X==X],f).unstack(0))
# tempo ate confirmar 750 para viradas
t=E[(E.turn==1)&(E.X==250)]; print("recsec das viradas X250 (s)",t.recsec.describe().round(0).to_dict())
# fundo vs topo mesmas taxas por hora
print(E[E.X==500].groupby(["hg","sign"]).turn.agg(["size","mean"]).round(2).unstack())
# multiplos topos intermediarios por perna
tot=E[(E.X==250)].groupby(["day","sign"]).turn.agg(["size","sum"]);print("eventos/dia-dir mediana",tot["size"].median())
