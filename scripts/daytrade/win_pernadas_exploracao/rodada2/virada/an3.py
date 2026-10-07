import pandas as pd, numpy as np
exec(open("an.py").read().split("lines=[]")[0])
E=E[E.rise>=750].copy()
E["rb"]=pd.cut(E.rise,[749,1250,2000,1e9],labels=["a","b","c"]); E["st"]=E.hg.astype(str)+"|"+E.rb.astype(str)
FOC=["leg_delta","vwapdist","rec_vrel","rec_nrel","rsi_d","rsi_top","cross921_d","below21_d","cross9_chg","vwapcross","pre1_vrel","pre5_avgsz_rel","div_delta","minopen","dur","speed","rise_atr","prevleg","body_top","wick_top","pre5_delta","rec_delta","rec_avgsz_rel","dropspeed","recsec","atr"]
def perm(d,f,B=300):
    obs=saucs(d,f,"st"); x=d[f].values.astype(float)
    null=[]
    for _ in range(B):
        dd=d.copy(); dd["turn"]=d.groupby("st").turn.transform(lambda s: rng.permutation(s.values)); null.append(saucs(dd,f,"st"))
    null=np.array(null); return obs,(np.abs(null-.5)>=abs(obs-.5)).mean(),null.std()
out=[]
for X in (250,500):
  for f in FOC:
    row=[X,f]
    for nm,sg in(("TOPO",1),("FUNDO",-1),("POOL",0)):
        d=E[(E.X==X)] if sg==0 else E[(E.X==X)&(E.sign==sg)]
        if d[f].notna().sum()<60: row+= [np.nan,np.nan,np.nan];continue
        if sg==0: d=d.assign(st=d.st+"|"+d.sign.astype(str))
        o,p,sd=perm(d,f,200); row+=[o,p,sd]
    out.append(row); print(row,flush=True)
O=pd.DataFrame(out,columns=["X","feat","auc_top","p_top","sd_top","auc_fun","p_fun","sd_fun","auc_pool","p_pool","sd_pool"]);O.to_pickle("foc.pkl")
print(O.round(3).to_string())
