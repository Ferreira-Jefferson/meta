import sys, numpy as np, pandas as pd, json, pickle
from eventos import FEATS
from lib_an import *
def detalhe(df,thr,dates,w):
    a,b=WIN[w]; dd=dates[df.day.values]
    sub=df[(dd>=a)&(dd<=b)]; days=np.unique(sub.day.values); ix={d:i for i,d in enumerate(days)}
    S=np.zeros((len(days),len(FEATS),2,len(OUTS))); N=np.zeros_like(S)
    for fi,f in enumerate(FEATS):
        lo,hi=thr[f]; s=sub[sub[f].notna()]
        for oi,o in enumerate(OUTS):
            t=s[s[o].notna()]
            res=(t[o]-t.groupby(["lv","hb"])[o].transform("mean")).values
            di=np.array([ix[d] for d in t.day.values])
            for si,m in enumerate((t[f].values<=lo,t[f].values>=hi)):
                np.add.at(S,(di[m],fi,si,oi),res[m]); np.add.at(N,(di[m],fi,si,oi),1)
    return days,S,N
def boot(S,N,nb=2000,seed=0):
    rng=np.random.default_rng(seed); nd=S.shape[0]; out=np.empty((nb,)+S.shape[1:])
    for i in range(nb):
        c=np.bincount(rng.integers(0,nd,nd),minlength=nd).astype(float)
        out[i]=np.tensordot(c,S,1)/np.maximum(np.tensordot(c,N,1),1e-9)
    return out
def tabela(w,real,nulo,df,thr,dates,boots=True):
    M,Nn=real[w]; arr=np.stack([r[1][w][0] for r in nulo]); mu=np.nanmean(arr,0); sd=np.nanstd(arr,0)
    exc=M-mu; z=exc/sd
    ci=None
    if boots:
        days,S,N=detalhe(df,thr,dates,w); bs=boot(S,N)-mu[None]; ci=(np.nanpercentile(bs,2.5,0),np.nanpercentile(bs,97.5,0),days,S,N)
    return exc,z,Nn,mu,sd,ci
def linhas(w,exc,z,Nn,ci):
    rows=[]
    for fi,f in enumerate(FEATS):
        for si,sd_ in enumerate(SIDES):
            for oi,o in enumerate(OUTS):
                r=dict(f=f,lado=sd_,o=o,n=int(Nn[fi,si,oi]),exc=exc[fi,si,oi],z=z[fi,si,oi])
                if ci is not None: r["lo"]=ci[0][fi,si,oi]; r["hi"]=ci[1][fi,si,oi]
                rows.append(r)
    return pd.DataFrame(rows)
if __name__=="__main__":
    etapa=sys.argv[1]
    df=pd.read_pickle("eventos_real.pkl"); dates=pickle.load(open("dates.pkl","rb")); thr=json.load(open("limiares.json"))
    real=pickle.load(open("stat_real.pkl","rb")); nulo=pickle.load(open("stat_nulo.pkl","rb"))
    if etapa=="desc":
        exc,z,Nn,mu,sd,ci=tabela("desc",real,nulo,df,thr,dates)
        T=linhas("desc",exc,z,Nn,ci)
        # metade 1 x metade 2 (sinal)
        days,S,N=ci[2],ci[3],ci[4]; h=len(days)//2
        def mm(sl): return np.tensordot(np.ones(len(days[sl])),S[sl],1)/np.maximum(np.tensordot(np.ones(len(days[sl])),N[sl],1),1e-9)
        m1=mm(slice(0,h)); m2=mm(slice(h,None))
        T["h1"]=[m1[FEATS.index(r.f),SIDES.index(r.lado),OUTS.index(r.o)]-mu[FEATS.index(r.f),SIDES.index(r.lado),OUTS.index(r.o)] for r in T.itertuples()]
        T["h2"]=[m2[FEATS.index(r.f),SIDES.index(r.lado),OUTS.index(r.o)]-mu[FEATS.index(r.f),SIDES.index(r.lado),OUTS.index(r.o)] for r in T.itertuples()]
        T["cand"]=(T.z.abs()>=2.5)&(T.n>=200)&(np.sign(T.lo)==np.sign(T.hi))&(np.sign(T.h1)==np.sign(T.exc))&(np.sign(T.h2)==np.sign(T.exc))
        T.to_csv("desc_tabela.csv",index=False); print("testes:",len(T)); print("|z|>=2:",(T.z.abs()>=2).sum(),"|z|>=2.5:",(T.z.abs()>=2.5).sum(),"cand:",T.cand.sum())
        print(T[T.z.abs()>=2.2].sort_values("z").round(3).to_string())
        c=T[T.cand][["f","lado","o"]].to_dict("records"); json.dump(c,open("regras_congeladas.json","w"),indent=1)
    else:
        cong=json.load(open("regras_congeladas.json")); rows=[]
        for w in ("conf","set"):
            exc,z,Nn,mu,sd,ci=tabela(w,real,nulo,df,thr,dates)
            T=linhas(w,exc,z,Nn,ci); T["w"]=w; T.to_csv(f"{w}_tabela.csv",index=False)
            for c in cong:
                r=T[(T.f==c["f"])&(T.lado==c["lado"])&(T.o==c["o"])].iloc[0].to_dict(); rows.append(r)
            print(w,"|z|>=2 em todas as 144:",(T.z.abs()>=2).sum())
        print(pd.DataFrame(rows).round(3).to_string())
