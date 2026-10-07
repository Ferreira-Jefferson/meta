import sys, pickle, json, numpy as np
NS=(15,30,60)
def carrega(per):
    R=pickle.load(open(f'cache_{per}.pkl','rb')); ks=sorted(R)
    names=sorted(R[ks[0]][0]); 
    allnames=set()
    for d in ks: allnames|=set(R[d][0])
    return R,ks,sorted(allnames)
def prep(R,ks,N):
    trl=[];day=[];slot=[];va=[];an=[];wu=[];wd=[];mu=[];md=[];tm=[]
    for q,d in enumerate(ks):
        o,fw,sl=R[d]; valid,a,u,dn,mfu,mfd=fw[N]; n=len(sl); trl.append(fw['tr'])
        tmin=540+np.arange(n)*0  # placeholder
        day.append(np.full(n,q)); slot.append(sl); va.append(valid); an.append(a); wu.append(u); wd.append(dn); mu.append(mfu); md.append(mfd)
    cat=lambda L:np.concatenate(L)
    tr=cat(trl); slc=cat(slot); key=np.zeros(len(tr),int)
    for s in np.unique(slc):
        m=(slc==s)&~np.isnan(tr)
        if m.sum()<8: key[slc==s]=s*4; continue
        q=np.quantile(tr[m],[.25,.5,.75]); qq=np.digitize(np.nan_to_num(tr[slc==s],nan=q[0]),q); key[slc==s]=s*4+qq
    return dict(key=key,day=cat(day),slot=cat(slot),valid=cat(va),any=cat(an).astype(float),wu=cat(wu).astype(float),wd=cat(wd).astype(float),mu=cat(mu),md=cat(md))
def flags(R,ks,nm):
    F=[];D=[]
    for d in ks:
        o=R[d][0]; n=len(R[d][2])
        if nm in o: F.append(o[nm][0]); D.append(o[nm][1])
        else: F.append(np.zeros(n,bool)); D.append(np.zeros(n))
    return np.concatenate(F),np.concatenate(D)
def zrob(day,m,mu,flag,nd):
    """razao: delta=sum(m-mu)/k; erro cluster por dia"""
    k=flag.sum()
    if k==0: return np.nan,np.nan,0
    dd=np.bincount(day[flag],weights=(m-mu)[flag],minlength=nd); kk=np.bincount(day[flag],minlength=nd)
    delta=dd.sum()/k; e=dd-delta*kk
    se=np.sqrt((e**2).sum())/k
    return delta,(delta/se if se>0 else np.nan),k
def avalia_um(P,F,D,nd):
    base=P['valid']; 
    sl=P['slot']; ns=sl.max()+1
    def mus(m):
        s=np.bincount(sl[base],weights=m[base],minlength=ns); c=np.bincount(sl[base],minlength=ns)
        return (s/np.maximum(c,1))[sl]
    muany=mus(P['any']); mudir=mus((P['wu']+P['wd'])/2)
    def mus2(m):
        k=P['key']; s=np.bincount(k[base],weights=m[base],minlength=k.max()+1); c=np.bincount(k[base],minlength=k.max()+1)
        return (s/np.maximum(c,1))[k]
    muany2=mus2(P['any']); mudir2=mus2((P['wu']+P['wd'])/2)
    fl=F&base
    out={}
    if fl.sum()<30: return None
    delta,z,k=zrob(P['day'],P['any'],muany,fl,nd)
    out.update(n=int(k),ndias=int(len(np.unique(P['day'][fl]))),nind=int(len(np.unique(P['day'][fl]*100+sl[fl]))),
        p_any=float(P['any'][fl].mean()),b_any=float(muany[fl].mean()),z_any=float(z))
    d2,z2,_=zrob(P['day'],P['any'],muany2,fl,nd); out.update(b_any2=float(muany2[fl].mean()),z_any2=float(z2))
    dirf=fl&(D!=0)
    if dirf.sum()>=30:
        same=np.where(D>0,P['wu'],P['wd']); contra=np.where(D>0,P['wd'],P['wu'])
        mfs=np.where(D>0,P['mu'],P['md'])
        for nm,m in (('same',same),('contra',contra)):
            delta,z,k=zrob(P['day'],m,mudir,dirf,nd)
            out[f'p_{nm}']=float(m[dirf].mean()); out[f'z_{nm}']=float(z)
        out['b_dir']=float(mudir[dirf].mean()); out['n_dir']=int(dirf.sum()); out['b_dir2']=float(mudir2[dirf].mean())
        for nm,m in (('same',same),('contra',contra)):
            out[f'z2_{nm}']=float(zrob(P['day'],m,mudir2,dirf,nd)[1])
        # mfe medio a favor antes de 250 contra vs base
        out['mfe_same']=float(mfs[dirf].mean())
        mfb=((P['mu']+P['md'])/2); s=np.bincount(sl[base],weights=mfb[base],minlength=ns)/np.maximum(np.bincount(sl[base],minlength=ns),1)
        out['mfe_base']=float(s[sl][dirf].mean())
    return out
def roda(per,names=None):
    R,ks,allnames=carrega(per); nd=len(ks); names=names or allnames
    rows=[]
    for N in NS:
        P=prep(R,ks,N)
        for nm in names:
            F,D=flags(R,ks,nm); r=avalia_um(P,F,D,nd)
            if r: r.update(var=nm,N=N); rows.append(r)
    return rows
if __name__=='__main__':
    per=sys.argv[1]; rows=roda(per); json.dump(rows,open(f'res_{per}.json','w'))
    print(len(rows),'linhas')
