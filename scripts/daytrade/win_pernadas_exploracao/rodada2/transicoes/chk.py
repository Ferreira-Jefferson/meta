import numpy as np
from an import *
from lib import *
days=load()
R=collect([build(d) for d in days])
E=np.array(R["ev"],float)
rng=np.random.default_rng(1)
for X,col,D in ((250,6,750),(375,6,750),(500,6,750)):
    e=E[(E[:,3]==X)&(E[:,5]==2)&(E[:,col]>=0)]
    nd=len(np.unique(e[:,0])); nl=len(set(zip(e[:,0],e[:,1])))
    byday={d:e[e[:,0]==d][:,col] for d in np.unique(e[:,0])}
    ds=list(byday)
    bs=[]
    for _ in range(2000):
        pick=rng.choice(ds,len(ds)); v=np.concatenate([byday[d] for d in pick]); bs.append(v.mean())
    print(X,D,"13+ n",len(e),"dias",nd,"legs",nl,"P",e[:,col].mean().round(3),"IC dia-bootstrap",np.percentile(bs,[5,95]).round(3))
# null with 60min block, 13+ only
def f(seed,block):
    r=np.random.default_rng(seed)
    R=collect([build(d,shuffled_order(d,r,block)) for d in days]); E=np.array(R["ev"],float)
    out=[]
    for X in (250,375,500):
        e=E[(E[:,3]==X)&(E[:,5]==2)&(E[:,6]>=0)]; out.append(e[:,6].mean())
    return out
for block in (60,15):
    o=np.array([f(s,block) for s in range(60)])
    print("block",block,"nulo 13+ P(X->750) X=250,375,500:",o.mean(0).round(3),np.percentile(o,95,axis=0).round(3))
# leg hours: legs starting >=13 count, and sizes
import collections
T=np.array(R["trans"],float); m=T[(T[:,0]==750)]
print("pernadas 750 que comecam 13+ (seguinte):",(m[:,9]==2).sum(),"de",len(m))
