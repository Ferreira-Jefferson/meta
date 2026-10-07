import pandas as pd, numpy as np
A=pd.read_pickle("ev_tick.pkl"); rng=np.random.default_rng(3)
for T,s in [(250,65),(500,125),(750,190)]:
  for k in (50,100,200,300):
    d=A[(A["T"]==T)&(A.s==s)&(A.g_fill==1)]
    e=d.g_mn_exc.values; w=(d.g_alvo.values==1)&(e<k); l=e>=k
    pts=np.where(w,d.d1.values-2,np.where(l,-(k+7),d.g_ult.values-2))
    g=pd.DataFrame({"dia":d.dia.values,"v":pts}).groupby("dia").v.agg(["sum","count"]).values
    ix=rng.integers(0,len(g),(2000,len(g))); ms=g[ix,0].sum(1)/g[ix,1].sum(1)
    print(T,s,k,len(d),f"acerto {w.mean()*100:.1f}% ruina {(k/(d.d1.values+k)).mean()*100:.1f}% pts/op {pts.mean():.1f} IC {np.percentile(ms,[2.5,97.5]).round(1)} dias {len(g)}")
