import sys; sys.path.insert(0,'.')
from agg import *
r=carrega(); names=r['names']; months=r['months']
F=r[False]['F']; Fo=r[True]['F']
md=metricas(F,wmask(months,'desc'))
mo=metricas(Fo,wmask(months,'desc'))
df=pd.DataFrame(dict(key=[str(n[0]) for n in names],kind=[n[0][0] for n in names],trig=[n[1] for n in names],dir=[n[2] for n in names],
  nf=md['nf'],fill=md['fill'],win=md['win'],be=md['be'],mean=md['mean'],t=md['t'],opsdia=md['opsdia'],streak=md['streak'],mean_otim=mo['mean'],t_otim=mo['t'],win_otim=mo['win']))
df.to_pickle('desc_cells.pkl')
print(len(df),'celulas; n>=150:',(df.nf>=150).sum())
print(df.groupby('kind').agg(n=('t','size'),pos=('mean',lambda x:(x>0).mean()),t3=('t',lambda x:(x>=3).sum()),mean=('mean','mean')))
print(df.groupby('dir').agg(pos=('mean',lambda x:(x>0).mean()),mean=('mean','mean'),t3=('t',lambda x:(x>=3).sum())))
print(df.groupby('trig').agg(pos=('mean',lambda x:(x>0).mean()),mean=('mean','mean'),t3=('t',lambda x:(x>=3).sum())))
print(df[df.nf>=150].sort_values('t',ascending=False).head(25).to_string())
