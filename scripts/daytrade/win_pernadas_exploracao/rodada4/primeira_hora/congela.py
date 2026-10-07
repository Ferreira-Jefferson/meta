import pickle,json,numpy as np
from core_ph import grade
R=pickle.load(open('res_desc.pkl','rb'))
real=R[-1];nulls=[R[s] for s in R if s>=0]
G=grade()
vals={'W':['0900','0930','1000','NY'],'M':[150,250,350],'K':[5,10,15],'d':[0,50,100],'p':[5,10],'a':[100,150,200,300],'s':[150,250,400]}
def viz(cfg):
    out=[]
    for ax,key in enumerate('WMKdpas'):
        v=vals[key];i=v.index(cfg[ax])
        for j in (i-1,i+1):
            if 0<=j<len(v):
                c=list(cfg);c[ax]=v[j];out.append(tuple(c))
    return out
def ev(res,c,m=0):
    r=res[c][m];return r['ev'] if r and r['n']>=30 else np.nan
rows=[]
for c in G:
    r=real[c][0]
    if not r or r['n']<150: continue
    nb=[ev(real,v) for v in viz(c)];nb=[x for x in nb if x==x]
    rows.append((r['ev'],c,r,np.mean(nb),np.mean(np.array(nb)>0)))
rows.sort(key=lambda x:-x[0])
print('configs com n>=150:',len(rows),'de',len(G))
print('EV>0:',sum(1 for r in rows if r[0]>0),' IC95 inf>0:',sum(1 for r in rows if r[2]['lo']>0))
for e,c,r,nbm,nbp in rows[:15]:
    print(c,'n',r['n'],'fill %.2f'%r['fill'],'ac %.3f be %.3f ev %.1f [%.1f,%.1f] viz %.1f (%.0f%%+) otim %.1f'%(r['acerto'],r['be'],e,r['lo'],r['hi'],nbm,100*nbp,real[c][1]['ev']))
# nulo: max ev por shuffle e frac >0
mx=[];fr=[];mean=[]
for N in nulls:
    es=[N[c][0]['ev'] for c in G if N[c][0] and N[c][0]['n']>=150]
    mx.append(max(es));fr.append(np.mean(np.array(es)>0));mean.append(np.mean(es))
print('nulo max EV por embaralhamento',np.round(mx,1),'media',np.round(mean,1),'frac>0',np.round(fr,2))
print('real: media EV',np.mean([r[0] for r in rows]),'frac>0',np.mean([r[0]>0 for r in rows]))
# EV medio por fatores
import collections
for ax,key in enumerate('WMKdpas'):
    print(key,{v:round(np.mean([r[0] for r in rows if r[1][ax]==v]),1) for v in vals[key]})
sel=[]
for e,c,r,nbm,nbp in rows:
    if nbm>0 and nbp>=0.6 and r['lo']>-5 and len(sel)<4 and all(sum(a!=b for a,b in zip(c,s))>=2 for s in sel): sel.append(c)
print('congeladas',sel)
json.dump([list(c) for c in sel],open('congeladas.json','w'))
