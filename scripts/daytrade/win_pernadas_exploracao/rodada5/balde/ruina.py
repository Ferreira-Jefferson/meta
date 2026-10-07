import sys,pickle; sys.path.insert(0,'.')
import numpy as np, balde_core as bc
from agg import streak_p95
motor=bc.motor
T=pickle.load(open('trades_celulas.pkl','rb'))
out={}
for nm,d in T.items():
    pn=d['pnl']; res=pn*0.2; nd=d['n_dias']; opd=len(pn)/nd
    n_ops=int(250*opd)
    row=dict(n=len(pn),opd=opd,mean_pts=pn.mean(),mean_brl=res.mean(),win=(pn>0).mean(),loss_med_brl=-res[res<0].mean(),worst=res.min(),
             streak_p95=streak_p95(1-(pn>0).mean(),n_ops,sims=1000))
    caps=[250,500,1000,2000,3000,5000,7500,10000,15000,20000,30000,50000]
    rr={}
    for c in caps:
        rr[c]=motor.ruina_mc(res,None,c,n_ops,n_caminhos=3000,seed=1)['p_ruina']
    row['ruina']=rr
    ok=[c for c in caps if rr[c]<=0.05]
    row['cap_5pct']=ok[0] if ok else None
    out[nm]=row
    print(nm,{k:(round(v,3) if isinstance(v,float) else v) for k,v in row.items() if k!='ruina'}); print('   ',{k:round(v,3) for k,v in rr.items()},flush=True)
pickle.dump(out,open('ruina_res.pkl','wb'))
