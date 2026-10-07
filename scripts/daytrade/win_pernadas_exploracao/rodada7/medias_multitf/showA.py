import pickle, numpy as np, pandas as pd
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
o=pickle.load(open('finalA.pkl','rb'))
rows=[]
for (rid,w),e in o['central'].items():
    f=o['fam'][(rid,w)]
    fp=sum(1 for x in f if x['mean']>0); nn=sum(x['n'] for x in f); wm=sum((x['mean'] if np.isfinite(x['mean']) else 0)*x['n'] for x in f)/max(nn,1)
    rows.append(dict(regra=rid,jan=w,n=e['n'],dia=round(e['per_day'],2),acerto=round(e['win'],3),be=round(e['be'],3),esp=round(e['mean'],1),ic_lo=round(e['ci_lo'],0),ic_hi=round(e['ci_hi'],0),payoff=round(e['payoff'],2),seq=e['maxloss'],fam_pos=f"{fp}/12",fam_esp=round(wm,1),pv=round(e['pv'],3),pf=round(e['pf'],3),pnull=round(e['pnull'],3)))
print(pd.DataFrame(rows).sort_values(['jan','regra']).to_string(index=False))
