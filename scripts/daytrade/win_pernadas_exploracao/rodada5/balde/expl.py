import sys; sys.path.insert(0,'.')
from agg import *
r=carrega(); names=r['names']; months=r['months']; F=r[False]['F']
M={w:metricas(F,wmask(months,w)) for w in ('desc','conf','ref')}
df=pd.DataFrame(dict(key=[str(n[0]) for n in names],kind=[n[0][0] for n in names],trig=[n[1] for n in names],dir=[n[2] for n in names]))
for w in M:
    df['n_'+w]=M[w]['nf']; df['m_'+w]=M[w]['mean']; df['t_'+w]=M[w]['t']
tc=df[df.kind=='TC']
print(tc[(tc.n_desc>=100)].sort_values('t_desc',ascending=False).head(14).round(2).to_string())
print(tc.groupby('trig')[['m_desc','m_conf','m_ref']].mean().round(1))
print(df.groupby('kind')[['m_desc','m_conf','m_ref']].mean().round(1))
# efeito da gestao: media por par (S,T) F vs BE1 vs BE2 vs P
import re
def par(k):
    x=eval(k); return (x[1],x[2]) if x[0] in('F','BE','P') else None
df['par']=df.key.map(par); g=df[df.kind.isin(['F','BE','P'])].copy()
g['kk']=g.key.map(lambda k: eval(k)[0]+(str(eval(k)[3]) if eval(k)[0]=='BE' else ''))
print(g.groupby('kk')[['m_desc','m_conf','m_ref']].mean().round(1))
# media por dir x trig  (F)
f=df[df.kind=='F']
print(f.pivot_table(index='trig',columns='dir',values=['m_desc','m_conf','m_ref'],aggfunc='mean').round(1).to_string())
