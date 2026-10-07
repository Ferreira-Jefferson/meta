import pickle, numpy as np, pandas as pd
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
r=pd.DataFrame(pickle.load(open('res_desc2.pkl','rb')))
p=r.value.str.split('|',expand=True); p.columns=['par','breach','x','trend','var','stop','K']
r=pd.concat([r,p],axis=1)
r=r[r.n>=1]
print(len(r),(r.n>=60).sum())
ok=r[r.n>=60]
print('t>=2:',(ok.t>=2).sum(),'t>=1.5',(ok.t>=1.5).sum(),'mean>0',(ok['mean']>0).sum(), 'de', len(ok))
for c in ['par','breach','x','trend','var','stop','K']:
    g=ok.groupby(c).agg(cel=('n','size'),n_med=('n','median'),esp_media=('mean','mean'),esp_med=('mean','median'),pos=('mean',lambda s:(s>0).mean()),win=('win','mean'),be=('be','mean'))
    print(g.round(3))
print(ok.sort_values('t',ascending=False).head(25)[['value','n','win','be','mean','t','ci_lo','ci_hi','pv','pf']].round(3).to_string(index=False))
