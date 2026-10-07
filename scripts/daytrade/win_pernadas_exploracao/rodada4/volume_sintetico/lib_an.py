import numpy as np, pandas as pd, json
from eventos import FEATS
OUTS=["NH","P20","MFE30","MAE30","E_g1","E_g2"]
WIN={"desc":("2026.01.01","2026.06.30"),"conf":("2026.07.01","2026.08.31"),"set":("2026.09.01","2026.09.30")}
SIDES=["baixo","alto"]
def day_dates(days): return np.array([d["date"] for d in days])
def stat_vector(df,thr,dates,wins=WIN):
    """retorna dict[(win)] -> arrays media-residual[F,2,O], n[F,2,O]"""
    out={}
    dd=dates[df.day.values]
    for w,(a,b) in wins.items():
        sub=df[(dd>=a)&(dd<=b)]
        M=np.full((len(FEATS),2,len(OUTS)),np.nan); Nn=np.zeros((len(FEATS),2,len(OUTS)))
        for fi,f in enumerate(FEATS):
            lo,hi=thr[f]
            s=sub[sub[f].notna()]
            for oi,o in enumerate(OUTS):
                t=s[s[o].notna()]
                if len(t)==0: continue
                res=t[o]-t.groupby(["lv","hb"])[o].transform("mean")
                for si,m in enumerate((t[f]<=lo,t[f]>=hi)):
                    if m.sum()>0: M[fi,si,oi]=res[m].mean(); Nn[fi,si,oi]=m.sum()
        out[w]=(M,Nn)
    return out
def terciles(df):
    return {f:[float(df[f].quantile(1/3)),float(df[f].quantile(2/3))] for f in FEATS}
