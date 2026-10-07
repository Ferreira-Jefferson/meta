import pickle, numpy as np, pandas as pd
import core
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
B=pickle.load(open('finalB.pkl','rb')); C=pickle.load(open('finalC.pkl','rb')); A=pickle.load(open('finalA.pkl','rb'))
rows=[]
for rid in [f"R{i}" for i in range(1,11)]:
    for w in (1,2,3):
        rec=dict(regra=rid,jan=w)
        for nm in ('m1','tk'):
            r=B.get((rid,'x0.5|K5|9/21/50ema|ttl10',w,nm),np.zeros((0,6)))
            s=core.stats_from(r); rec[nm+'_n']=s['n']; rec[nm+'_acerto']=round(s['win'],3) if s['n'] else np.nan; rec[nm+'_esp']=round(s['mean'],1) if s['n'] else np.nan
            # familia
            fr=[B.get((rid,f"x{x}|K{K}|9/21/50ema|ttl10",w,nm),np.zeros((0,6))) for x in (0.1,0.25,0.5,1.0) for K in (3,5,7.5)]
            tot=sum(len(x) for x in fr); pnl=sum(x[:,2].sum() for x in fr)
            rec[nm+'_fam']=round(pnl/tot,1) if tot else np.nan
            rec[nm+'_famPos']=sum(1 for x in fr if len(x) and x[:,2].mean()>0)
        ns=[C[s][(rid,w)]['mean'] for s in C]; rec['nulo']=round(np.nanmean(ns),1); rec['nulo_sd']=round(np.nanstd(ns),1)
        e=A['central'][(rid,w)]['mean']; rec['z_M1']=round((e-np.nanmean(ns))/np.nanstd(ns),2)
        rec['p_nulo']=round(np.mean(np.array(ns)>=e),3)
        rows.append(rec)
d=pd.DataFrame(rows); print(d.to_string(index=False)); d.to_pickle('tabB.pkl')
# agregado ticks: todas as regras, janela
for w in (1,2,3):
    for nm in ('m1','tk'):
        r=np.vstack([B.get((rid,'x0.5|K5|9/21/50ema|ttl10',w,nm),np.zeros((0,6))) for rid in [f"R{i}" for i in range(1,10)]])
        s=core.stats_from(r); print(w,nm,'R1-R9 central pooled n',s['n'],'esp',round(s['mean'],1),'acerto',round(s['win'],3))
