import pandas as pd, numpy as np
exec(open("an.py").read().split("lines=[]")[0])
E=E[E.rise>=750].copy()
E["rb"]=pd.cut(E.rise,[749,1250,2000,1e9],labels=["750-1250","1250-2000",">2000"])
E["st"]=E.hg.astype(str)+"|"+E.rb.astype(str)
print("n por dir/X:",E.groupby(["sign","X"]).turn.agg(["size","sum","mean"]).round(3))
print(E[E.X==250].groupby(["sign","hg"]).turn.agg(["size","mean"]).round(2))
print(E[E.X==250].groupby(["sign","rb"]).turn.agg(["size","mean"]).round(2))
FE2=[f for f in FE if f not in("rise",)]
res=[]
for sign,nm in((1,"TOPO"),(-1,"FUNDO")):
  for X in (150,250,375,500):
    d=E[(E.sign==sign)&(E.X==X)]
    for f in FE2:
        if d[f].notna().sum()<50: continue
        res.append((nm,X,f,len(d),int(d.turn.sum()),auc(d[f].values.astype(float),d.turn.values),saucs(d,f,"hg"),saucs(d,f,"st")))
R=pd.DataFrame(res,columns=["dir","X","feat","n","nturn","auc","auc_h","auc_hr"]);R.to_pickle("auc2.pkl")
for X in (150,250,375,500):
    p=R[R.X==X].pivot(index="feat",columns="dir",values=["auc","auc_h","auc_hr"]).round(3)
    p["mx"]=(p["auc_hr"]-.5).abs().max(axis=1); print("X",X,"n",R[R.X==X][["dir","n","nturn"]].drop_duplicates().values.tolist());print(p.sort_values("mx",ascending=False).head(14))
