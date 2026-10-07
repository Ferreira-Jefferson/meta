import pickle, numpy as np, pandas as pd
def carrega():
    r=pickle.load(open('real.pkl','rb'))
    return r
def wmask(months,w):
    mo=np.array(months)
    return {'desc':mo<=6,'conf':(mo>=7)&(mo<=8),'ref':mo>=9}[w]
def metricas(F,mask):
    """F (nd,nseq,11) -> dict of arrays por seq para os dias de mask."""
    X=F[mask]
    nord=X[:,:,0].sum(0); nf=X[:,:,1].sum(0); s=X[:,:,2].sum(0)
    with np.errstate(all='ignore'):
        mean=s/nf
        resid=X[:,:,2]-mean[None,:]*X[:,:,1]
        se=np.sqrt((resid**2).sum(0))/nf
        t=mean/se
        nwin=X[:,:,4].sum(0); ntg=X[:,:,5].sum(0)
        gm=X[:,:,6].sum(0)/nwin; lm=X[:,:,7].sum(0)/(nf-nwin)
        be=lm/(gm+lm)
        # corrida maxima de perdas atravessando dias
        best=np.zeros(F.shape[1]); cur=np.zeros(F.shape[1])
        for d in range(X.shape[0]):
            n=X[d,:,1]; lead=X[d,:,8]; trail=X[d,:,9]; mr=X[d,:,10]
            allp=(n>0)&(lead==n)
            has=n>0
            c2=np.where(allp,cur+n,np.where(has,trail,cur))
            b2=np.where(allp,c2,np.where(has,np.maximum(np.maximum(best,cur+lead),mr),best))
            best=np.maximum(best,b2); cur=c2
        nd_days=X.shape[0]
        # meses positivos
    return dict(nord=nord,nf=nf,fill=nf/np.maximum(nord,1),mean=mean,se=se,t=t,win=nwin/nf,tg=ntg/nf,be=be,gm=gm,lm=lm,
                opsdia=nf/nd_days,streak=best,sumpts=s,ndias=nd_days)
def meses_pos(F,months,w,idx):
    mo=np.array(months); m=wmask(months,w)
    ms=sorted(set(mo[m]))
    out=[]
    for k in ms:
        sel=mo==k
        out.append(F[sel][:,idx,2].sum())
    out=np.array(out); return (out>0).mean(), len(ms)
def boot_ci(F,months,w,idx,B=2000,seed=1):
    m=wmask(months,w); X=F[m][:,idx,:]
    nd=X.shape[0]; rng=np.random.default_rng(seed)
    W=rng.multinomial(nd,np.ones(nd)/nd,size=B).astype(float)
    mean=(W@X[:,2])/(W@X[:,1])
    return np.percentile(mean,[2.5,97.5])
def streak_p95(p_loss,n,sims=2000,seed=0):
    rng=np.random.default_rng(seed)
    L=rng.random((sims,int(n)))<p_loss
    best=np.zeros(sims,int); cur=np.zeros(sims,int)
    for k in range(L.shape[1]):
        cur=np.where(L[:,k],cur+1,0); best=np.maximum(best,cur)
    return float(np.percentile(best,95))
