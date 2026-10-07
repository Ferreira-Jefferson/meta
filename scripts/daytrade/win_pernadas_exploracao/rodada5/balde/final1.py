import sys, json, pickle; sys.path.insert(0,'.')
from agg import *
from balde_core import PARES,TRIGS,DIRS
r=carrega(); names=r['names']; months=r['months']
F=r[False]['F']; Fo=r[True]['F']
nu=pickle.load(open('nulo.pkl','rb')); NF=nu['F']; K=NF.shape[0]; nnames=nu['names']
assert [str(n) for n in nnames]==[str(n) for n in names[:len(nnames)]]
W={w:wmask(months,w) for w in ('desc','conf','ref')}
M={w:metricas(F,W[w]) for w in W}; Mo={w:metricas(Fo,W[w]) for w in W}
nF=len(nnames)
# nulo por janela
def met_nulo(w):
    out=[]
    for k in range(K):
        out.append(metricas(NF[k].astype(float),W[w]))
    return out
NU={w:met_nulo(w) for w in W}
res={}
for w in W:
    mean=np.array([x['mean'][:nF] for x in NU[w]]); t=np.array([x['t'][:nF] for x in NU[w]])
    res[w]=dict(mean=mean,t=t)
kinds=np.array([n[0][0] for n in names]); trig=np.array([n[1] for n in names]); dr=np.array([n[2] for n in names])
print('== nulo vs real (cels F, media por janela) ==')
for w in W:
    m_real=M[w]['mean'][:nF]; m_nulo=np.nanmean(res[w]['mean'],axis=0)
    print(w,'real media',np.nanmean(m_real).round(2),'nulo media',np.nanmean(m_nulo).round(2),'frac real>0',(m_real>0).mean().round(3),'frac nulo>0',(res[w]['mean']>0).mean().round(3),
          'max t real',np.nanmax(M[w]['t'][:nF]).round(2),'max t nulo (mediana, p95 das reps)',np.nanpercentile(np.nanmax(res[w]['t'],axis=1),[50,95]).round(2))
# z por celula (real vs distribuicao nula)
def z_cell(w,i):
    x=res[w]['mean'][:,i]; return (M[w]['mean'][i]-np.nanmean(x))/np.nanstd(x,ddof=1)
# quantas celulas F com t>=2 em desc: real vs nulo
for thr in (2.0,2.5,3.0):
    print('t>=',thr,'desc real',int((M['desc']['t'][:nF]>=thr).sum()),'nulo medio por rep',(res['desc']['t']>=thr).sum(1).mean().round(2))
pickle.dump(dict(res=res),open('nulo_res.pkl','wb'))
