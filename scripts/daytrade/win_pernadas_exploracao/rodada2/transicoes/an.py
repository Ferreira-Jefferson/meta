import numpy as np, sys, pickle
from lib import *
from multiprocessing import Pool
EDG=[0,750,1000,1500,2500,1e9]
BL=["<750","750-1000","1000-1500","1500-2500",">=2500"]
HG=["<10:30","10:30-13","13+"]
def bn(x): return int(np.searchsorted(EDG,x,side="right")-1)
def hgrp(m): return 0 if m<630 else (1 if m<780 else 2)

def collect(paths):
    R=dict(trans=[],ev=[],sub=[])
    for di,(p,t,op) in enumerate(paths):
        for thr in (500,750):
            legs=zigzag(p,thr)
            comp=[x for x in legs if x[3] is not None]
            for k in range(len(comp)-1):
                s,e,d,c=comp[k]; s2,e2,d2,c2=comp[k+1]
                sz=abs(p[e]-p[s]); sz2=abs(p[e2]-p[s2])
                ext=0
                if k>=2:
                    e0=comp[k-2][1]; ext=1 if (p[e]-p[e0])*d>0 else -1
                sz0=abs(p[comp[k-1][1]]-p[comp[k-1][0]]) if k>=1 else np.nan
                tr=np.sign(p[e]-op)*d
                R["trans"].append((thr,di,k,d,sz,sz2,sz0,ext,tr,hgrp(t[s2]),hgrp(t[s])))
        legs=zigzag(p,750); n=len(p); prev=[]
        for li,(s,e,d,c) in enumerate(legs):
            end=c if c is not None else n-1
            q=p*d; Hrun=q[s]; fired={250:False,375:False,500:False}; cnt={250:0,375:0,500:0}
            for i in range(s+1,end+1):
                if q[i]>Hrun:
                    Hrun=q[i]; fired={250:False,375:False,500:False}; continue
                dd=Hrun-q[i]
                for X in (250,375,500):
                    if (not fired[X]) and dd>=X:
                        fired[X]=True
                        fut=q[i+1:]
                        up=np.where(fut>Hrun)[0]; ui=up[0] if len(up) else 10**9
                        res=[]
                        for D in (750,1000,1500):
                            dn=np.where(fut<=Hrun-D)[0]; dj=dn[0] if len(dn) else 10**9
                            res.append(1 if dj<ui else (0 if ui<10**9 else -1))
                        A=Hrun-q[s]
                        pm=np.mean(prev) if prev else np.nan
                        R["ev"].append((di,li,d,X,A,hgrp(t[i]),res[0],res[1],res[2],(Hrun*d-op*d)*d if False else (p[i]-op)*d,pm,cnt[X]))
                        cnt[X]+=1
            if c is not None: prev.append(abs(p[e]-p[s]))
        z=zigzag(p,250); piv=np.array([x[1] for x in z])
        for (s,e,d,c) in legs:
            if c is None: continue
            R["sub"].append((di,abs(p[e]-p[s]),int(((piv>s)&(piv<e)).sum()),hgrp(t[s])))
    return R

def stats(R):
    S={}
    T=np.array(R["trans"],dtype=float)
    for thr in (500,750):
        M=T[T[:,0]==thr]
        for first in ("all","no1st"):
            m=M if first=="all" else M[M[:,2]>=1]
            for b in range(5):
                mb=m[[bn(x)==b for x in m[:,4]]]
                if len(mb)==0: continue
                pre=f"T{thr}|{first}|prev{BL[b]}|"
                for s in (750,1000,1500,2000):
                    if s>thr: S[pre+f"next>={s}"]=((mb[:,5]>=s).mean(),len(mb))
                S[pre+"next>=prev(rompe inicio)"]=((mb[:,5]>=mb[:,4]).mean(),len(mb))
                S[pre+"ratio_med"]=(np.median(mb[:,5]/mb[:,4]),len(mb))
                S[pre+"next_med"]=(np.median(mb[:,5]),len(mb))
            S[f"T{thr}|{first}|ALL|next_med"]=(np.median(m[:,5]),len(m))
            S[f"T{thr}|{first}|ALL|ratio_med"]=(np.median(m[:,5]/m[:,4]),len(m))
            S[f"T{thr}|{first}|ALL|next>=prev"]=((m[:,5]>=m[:,4]).mean(),len(m))
            for s in (1000,1500,2000):
                if s>thr: S[f"T{thr}|{first}|ALL|next>={s}"]=((m[:,5]>=s).mean(),len(m))
        m=M[M[:,2]>=1]
        ls1=np.log(m[:,4]); ls2=np.log(m[:,5])
        S[f"T{thr}|corr_log|n vs n+1"]=(np.corrcoef(ls1,ls2)[0,1],len(m))
        r2=ls2.copy(); r1=ls1.copy()
        for g in range(3):
            k=m[:,9]==g
            if k.sum()>2: r2[k]-=ls2[k].mean(); r1[k]-=ls1[k].mean()
        S[f"T{thr}|corr_log_ctl_hora|n vs n+1"]=(np.corrcoef(r1,r2)[0,1],len(m))
        mm=m[m[:,2]>=2]
        S[f"T{thr}|corr_log|n-1 vs n+1"]=(np.corrcoef(np.log(mm[:,6]),np.log(mm[:,5]))[0,1],len(mm))
        for e,name in ((1,"estendeu(topo/fundo alem do anterior)"),(-1,"nao_estendeu")):
            me=m[m[:,7]==e]
            if len(me)>3:
                S[f"T{thr}|{name}|next>=prev"]=((me[:,5]>=me[:,4]).mean(),len(me))
                S[f"T{thr}|{name}|ratio_med"]=(np.median(me[:,5]/me[:,4]),len(me))
                S[f"T{thr}|{name}|next_med"]=(np.median(me[:,5]),len(me))
        for e,name in ((1,"termina_longe_da_abertura(+deriva)"),(-1,"termina_perto/lado_oposto")):
            me=m[m[:,8]==e]
            if len(me)>3:
                S[f"T{thr}|{name}|ratio_med"]=(np.median(me[:,5]/me[:,4]),len(me))
                S[f"T{thr}|{name}|next>=prev"]=((me[:,5]>=me[:,4]).mean(),len(me))
                S[f"T{thr}|{name}|next_med"]=(np.median(me[:,5]),len(me))
    E=np.array(R["ev"],dtype=float)
    def pr(m,col):
        m=m[m[:,col]>=0]
        return (m[:,col].mean() if len(m) else np.nan, len(m))
    for X in (250,375,500):
        e=E[E[:,3]==X]
        for D,col in ((750,6),(1000,7),(1500,8)):
            if D<=X: continue
            pre=f"E{X}->{D}|"
            S[pre+"ALL"]=pr(e,col)
            for g in range(3): S[pre+f"hora {HG[g]}"]=pr(e[e[:,5]==g],col)
            for lo,hi in [(0,500),(500,750),(750,1000),(1000,1500),(1500,1e9)]:
                S[pre+f"A {lo}-{hi:.0f}"]=pr(e[(e[:,4]>=lo)&(e[:,4]<hi)],col)
            for kk in (0,1,2):
                S[pre+f"tentativa {kk+1 if kk<2 else '3+'}"]=pr(e[e[:,11]==kk] if kk<2 else e[e[:,11]>=2],col)
            for dd,nm in ((1,"topo de alta"),(-1,"fundo de baixa")): S[pre+nm]=pr(e[e[:,2]==dd],col)
            S[pre+"leg com deriva do dia"]=pr(e[e[:,9]>0],col); S[pre+"leg contra deriva"]=pr(e[e[:,9]<=0],col)
            rr=e[~np.isnan(e[:,10])]; rat=rr[:,4]/rr[:,10]
            S[pre+"A/mediaPrev<0.8"]=pr(rr[rat<0.8],col); S[pre+"A/mediaPrev 0.8-1.25"]=pr(rr[(rat>=0.8)&(rat<1.25)],col); S[pre+"A/mediaPrev>=1.25"]=pr(rr[rat>=1.25],col)
    Sb=np.array(R["sub"],dtype=float)
    for b in range(5):
        m=Sb[[bn(x)==b for x in Sb[:,1]]]
        if len(m): S[f"SUB|leg {BL[b]}|n pivos250 dentro (media)"]=(m[:,2].mean(),len(m))
    S["SUB|ALL|media"]=(Sb[:,2].mean(),len(Sb)); S["SUB|ALL|pct0"]=((Sb[:,2]==0).mean(),len(Sb))
    return S

def one(seed):
    rng=np.random.default_rng(seed)
    days=load()
    return stats(collect([build(d,shuffled_order(d,rng)) for d in days]))
if __name__=="__main__":
    days=load()
    real=stats(collect([build(d) for d in days]))
    NS=int(sys.argv[1]) if len(sys.argv)>1 else 60
    with Pool(4) as pl: nulls=pl.map(one,range(NS))
    pickle.dump((real,nulls),open("res.pkl","wb"))
    print("done",len(real),NS)
