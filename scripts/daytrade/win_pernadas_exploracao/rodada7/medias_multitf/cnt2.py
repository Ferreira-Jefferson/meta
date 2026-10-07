import pickle, numpy as np, pandas as pd
nul=pickle.load(open('null2_0_40.pkl','rb'))
real=pd.DataFrame(pickle.load(open('res_desc2.pkl','rb')))
for th in (1.5,2.0):
    c=[sum(1 for r in rows if r['n']>=60 and r['t']>=th) for rows in nul.values()]
    print(th,'real',int(((real.n>=60)&(real.t>=th)).sum()),'de',int((real.n>=60).sum()),'nulo medio',np.mean(c),'max',max(c))
c=[np.mean([r['mean']>0 for r in rows if r['n']>=60]) for rows in nul.values()]
print('fracao positiva real',(real[real.n>=60]['mean']>0).mean(),'nulo',np.mean(c))
c=[np.nanmean([r['mean'] for r in rows if r['n']>=60]) for rows in nul.values()]
print('media real',real[real.n>=60]['mean'].mean(),'nulo',np.mean(c))
