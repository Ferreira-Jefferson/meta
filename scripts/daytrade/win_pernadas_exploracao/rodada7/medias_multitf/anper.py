import pickle, numpy as np, pandas as pd
pd.set_option('display.width',250); pd.set_option('display.max_rows',800)
real=pd.DataFrame(pickle.load(open('per_real.pkl','rb')))
nul=pickle.load(open('per_null.pkl','rb')); print('draws',len(nul))
M={}
for sd,rows in nul.items():
    for r in rows: M.setdefault((r['axis'],r['value']),[]).append(r['mean'])
real['nm']=[np.nanmean(M[(a,v)]) for a,v in zip(real.axis,real.value)]
real['ns']=[np.nanstd(M[(a,v)]) for a,v in zip(real.axis,real.value)]
real['z']=(real['mean']-real.nm)/real.ns
real.to_pickle('per_com_nulo.pkl')
for rid in real.axis.unique():
    r=real[real.axis==rid]
    print('=====',rid)
    for pre in ('fast','mid','slow'):
        s=r[r.value.str.startswith(pre)]
        print(pre,' '.join(f"{v[len(pre):]}:{m:+.0f}({n})" for v,m,n in zip(s.value,s['mean'],s.n)))
    g=r[r.value.str.startswith('P')&~r.value.str.startswith('P9/21/50x')]
    g=g[g.value.str.match(r'P\d+/\d+/\d+$')]
    print('grade 3x3x3: celulas',len(g),'positivas',(g['mean']>0).sum(),'media',round(g['mean'].mean(),1),'nulo',round(g.nm.mean(),1),'z medio',round(g.z.mean(),2),'min/max',round(g['mean'].min()),round(g['mean'].max()))
    sm=r[r.value=='sma']; print('sma',sm[['n','win','be','mean','z']].round(2).values.tolist())
