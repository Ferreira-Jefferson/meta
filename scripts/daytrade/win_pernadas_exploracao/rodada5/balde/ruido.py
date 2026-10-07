import sys; sys.path.insert(0,'.')
from agg import *
from balde_core import PARES,TRIGS,DIRS
r=carrega(); B=r[False]['B']; months=r['months']
m=(np.array(months)<=8)
def bidx(S,T,trig,dr): return PARES.index((S,T))*24+TRIGS.index(trig)*4+DIRS.index(dr)
def tab(S,T,trig,dr,win=m):
    X=B[win][:,bidx(S,T,trig,dr)].sum(0)  # (19,7)
    rows=[]
    for b in range(19):
        nsig,nf,sm,nw,ns,n1,n5=X[b]
        if nf<30: continue
        rows.append(dict(bloco=f"{9+b//2:02d}:{30*(b%2):02d}",n=int(nf),stop_pct=100*ns/nf,stop_ate1bar=100*n1/nf,stop_ate5bar=100*n5/nf,alvo_pct=100*nw/nf,nulo_alvo=100*S/(S+T),mean=sm/nf))
    return pd.DataFrame(rows)
if __name__=="__main__":
    for (S,T) in [(100,750),(50,400),(150,1000),(250,1500)]:
        print(S,T); print(tab(S,T,'none','a_aleat').round(1).to_string(index=False))
