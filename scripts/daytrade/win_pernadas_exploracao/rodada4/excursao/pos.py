import pandas as pd, numpy as np
K=["spec","cell","fill","side","geom"]
d=pd.read_pickle("tab_desc.pkl"); c=pd.read_pickle("tab_conf.pkl").set_index(K); s=pd.read_pickle("tab_set.pkl").set_index(K)
x=d[(d.fill==0)&(d.nf>=150)&(d.exp>0)].copy()
x=x.join(c[["nf","exp","win","be"]].add_prefix("c_"),on=K).join(s[["nf","exp"]].add_prefix("s_"),on=K)
pd.set_option("display.width",250)
print(x.sort_values("exp",ascending=False)[["spec","cell","side","geom","nf","exp","mean","z","win","be","c_nf","c_exp","s_nf","s_exp"]].to_string())
