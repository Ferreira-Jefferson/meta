import pickle, numpy as np, pandas as pd, exc
vthr, ra = pickle.load(open("real_agg.pkl","rb")); nu = pickle.load(open("null_agg.pkl","rb"))
KEY=["spec","cell","fill","side","geom"]
def table(w):
    r=ra[w][0].set_index(KEY); n=nu[w][0]
    n=n.assign(e=n.s/n.nf.replace(0,np.nan)); g=n.groupby(KEY).e.agg(["mean","std"])
    nn=n.groupby(KEY).nf.mean()
    t=r.join(g).join(nn.rename("nf_null"))
    t["exp"]=t.s/t.nf.replace(0,np.nan); t["fr"]=t.nf/t.n
    t["exc"]=t.exp-t["mean"]; t["z"]=t.exc/t["std"]
    t["win"]=t.w/t.nf; 
    t["gm"]=t.sw/t.w.replace(0,np.nan); t["lm"]=-t.sl/(t.nf-t.w).replace(0,np.nan); t["be"]=t.lm/(t.gm+t.lm)
    return t.reset_index()
if __name__=="__main__":
    d=table("desc"); d.to_pickle("tab_desc.pkl"); table("conf").to_pickle("tab_conf.pkl"); table("set").to_pickle("tab_set.pkl")
    x=d[(d.fill==0)&(d.nf>=150)]
    print("testes (cons, nf>=150):",len(x), "cells", x.groupby(["spec","cell"]).ngroups)
    print("exp>0:",(x.exp>0).sum(),"z>3:",(x.z>3).sum(),"exp>0&z>2:",((x.exp>0)&(x.z>2)).sum(), "z<-3:",(x.z<-3).sum())
    print(x.exp.describe())
    print(x.sort_values("z",ascending=False).head(25)[["spec","cell","side","geom","n","nf","fr","exp","mean","std","z","win","be"]].to_string())
    a=d[(d.spec=="all")&(d.fill==0)]
    print(a[["side","geom","nf","fr","exp","mean","z","win","be"]].to_string())
