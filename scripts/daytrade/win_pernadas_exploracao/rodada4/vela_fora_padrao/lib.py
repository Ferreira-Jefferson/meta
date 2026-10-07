import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv
CSV='C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv'
LEG=750.0; ADV=250.0
def carrega():
    d=pd.read_csv(CSV,sep='\t'); d=d[d['<DATE>'].str.startswith('2026')]
    d['dia']=d['<DATE>'].str.replace('.','-',regex=False)
    d['min']=d['<TIME>'].str[:2].astype(int)*60+d['<TIME>'].str[3:5].astype(int)
    out={}
    for dia,g in d.groupby('dia'):
        g=g.sort_values('min')
        out[dia]=dict(t=g['min'].values,o=g['<OPEN>'].values,h=g['<HIGH>'].values,l=g['<LOW>'].values,c=g['<CLOSE>'].values,v=g['<VOL>'].values.astype(float),tv=g['<TICKVOL>'].values.astype(float))
    return out
def forward(x,N):
    """para cada vela i: any750, win_up, win_dn (750 antes de 250 contra, empate=adverso), mfe_up/dn antes de 250 contra. NaN se janela incompleta"""
    h,l,c,n=x['h'],x['l'],x['c'],len(x['c'])
    valid=np.zeros(n,bool); valid[:max(n-N,0)]=True
    pad=N
    H=np.r_[h[1:],np.full(pad,-1e18)]; L=np.r_[l[1:],np.full(pad,1e18)]
    Hw=swv(H,N)[:n]; Lw=swv(L,N)[:n]
    up=np.maximum.accumulate(Hw,axis=1)-c[:,None]; dn=c[:,None]-np.minimum.accumulate(Lw,axis=1)
    # adverso instantaneo por barra (usa extremos acumulados): primeira barra em que dn>=ADV / up>=ADV
    def first(m):
        a=m.argmax(axis=1); a[~m.any(axis=1)]=N+5; return a
    ku=first(up>=LEG); kd=first(dn>=LEG)
    au=first(up>=ADV); ad=first(dn>=ADV)
    win_up=(ku<N)&(ku<ad); win_dn=(kd<N)&(kd<au)
    any750=(up[:,-1]>=LEG)|(dn[:,-1]>=LEG)
    # mfe a favor antes de 250 contra (ate barra do adverso exclusive, ou ate N)
    kk=np.arange(N)[None,:]
    mfe_up=np.where(kk<np.minimum(ad,N)[:,None],up,-1).max(axis=1); mfe_up=np.maximum(mfe_up,0)
    mfe_dn=np.where(kk<np.minimum(au,N)[:,None],dn,-1).max(axis=1); mfe_dn=np.maximum(mfe_dn,0)
    return valid,any750,win_up,win_dn,mfe_up,mfe_dn
def agg(x,tf):
    """barras agregadas de tf minutos; idx = indice M1 do ultimo minuto; so grupos completos"""
    t=x['t']; g=(t-540)//tf; n=len(t)
    # grupos completos: minutos consecutivos
    starts=np.r_[0,np.where(np.diff(g)!=0)[0]+1]; ends=np.r_[starts[1:],n]
    keep=[(s,e) for s,e in zip(starts,ends) if e-s==tf]
    if not keep: return None
    o=np.array([x['o'][s] for s,e in keep]); c=np.array([x['c'][e-1] for s,e in keep])
    h=np.array([x['h'][s:e].max() for s,e in keep]); l=np.array([x['l'][s:e].min() for s,e in keep])
    v=np.array([x['v'][s:e].sum() for s,e in keep]); tv=np.array([x['tv'][s:e].sum() for s,e in keep])
    return dict(o=o,h=h,l=l,c=c,v=v,tv=tv,idx=np.array([e-1 for s,e in keep]),slot=np.array([(t[s]-540)//tf for s,e in keep]))
def prevmean(a,k):
    """media das k anteriores (exclui atual); NaN se i<k"""
    cs=np.r_[0,np.cumsum(a)]; n=len(a); r=np.full(n,np.nan)
    if n>k: r[k:]=(cs[k:n]-cs[0:n-k])/k
    return r
