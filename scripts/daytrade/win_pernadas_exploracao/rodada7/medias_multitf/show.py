import pickle, pandas as pd, numpy as np
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
r=pd.DataFrame(pickle.load(open('res_desc.pkl','rb')))
cols=['axis','value','n','win','be','mean','t','ci_lo','ci_hi','nev','pv','pf','pnull']
for ax in ['ref','fast','mid','slow','kind','x','breach','ref_touch','trend','var','triple','par','ttl','Nstop','K','stop','entry','otim']:
    print(r[r.axis==ax][cols].round(3).to_string(index=False))
j=r[r.axis=='joint']; print(len(j), (j.t>2).sum(), (j['mean']>0).sum(), j['mean'].describe())
print(j.sort_values('t',ascending=False).head(15)[cols].round(3).to_string(index=False))
