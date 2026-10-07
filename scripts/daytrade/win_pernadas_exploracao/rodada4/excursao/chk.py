import pandas as pd, numpy as np
pd.set_option("display.width",250)
for w in ("desc","conf"):
    t=pd.read_pickle(f"tab_{w}.pkl"); t=t[(t.spec=="A")&(t.fill==0)]
    t["fam"]=np.where(t.geom<16,"pts","A")
    print(w); print(t.groupby(["side","cell","fam"]).agg(exc=("exc","mean"),exp=("exp","mean"),nul=("mean","mean")).unstack([0,2]).round(1))
