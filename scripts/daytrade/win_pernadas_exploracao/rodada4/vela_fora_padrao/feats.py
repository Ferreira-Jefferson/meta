import numpy as np
from lib import *
TFS=(1,5,15)
def sametime(dias,tf):
    """para cada dia: arrays (range_ratio_vs_prior, vol_ratio_vs_prior) por barra agregada"""
    ks=sorted(dias); tab={}
    for d in ks:
        a=agg(dias[d],tf)
        tab[d]=None if a is None else dict(slot=a['slot'],r=a['h']-a['l'],v=a['v'])
    out={}
    hist_r={};hist_v={}   # slot -> lista
    for d in ks:
        a=tab[d]
        if a is None: out[d]=None; continue
        rr=np.full(len(a['slot']),np.nan); vv=rr.copy()
        for j,s in enumerate(a['slot']):
            hr=hist_r.get(s,[])[-20:]; hv=hist_v.get(s,[])[-20:]
            if len(hr)>=8:
                rr[j]=a['r'][j]/max(np.median(hr),1e-9); vv[j]=a['v'][j]/max(np.median(hv),1e-9)
        out[d]=(rr,vv)
        for j,s in enumerate(a['slot']):
            hist_r.setdefault(s,[]).append(a['r'][j]); hist_v.setdefault(s,[]).append(a['v'][j])
    return out
def variantes_dia(x,st):
    """retorna dict nome -> (flag_agg, dir_agg(+1/-1/0), idx) por tf, mapeado p/ M1 abaixo"""
    res={}
    for tf in TFS:
        a=agg(x,tf)
        if a is None: continue
        o,h,l,c,v,tv,idx=a['o'],a['h'],a['l'],a['c'],a['v'],a['tv'],a['idx']
        n=len(o); rng=h-l; body=np.abs(c-o); sg=np.sign(c-o)
        T=f'M{tf}'
        def put(nm,flag,dr=None):
            f=np.nan_to_num(flag.astype(float),nan=0)>0 if flag.dtype!=bool else flag
            res[f'{nm}|{T}']=(f,sg if dr is None else dr,idx)
        R={k:rng/prevmean(rng,k) for k in (10,20,50)}
        V={k:v/prevmean(v,k) for k in (10,20,50)}
        S=(v/np.maximum(tv,1)); Sr=S/prevmean(S,20)
        for k in (10,20,50):
            for th in (2,3): put(f'tam k{k} >={th}x',R[k]>=th)
        rs,vs=st[tf][x['dia']] if st[tf].get(x['dia']) is not None else (np.full(n,np.nan),np.full(n,np.nan))
        # st alinha com agg completos: mesmas barras
        for th in (2,3): put(f'tam vs mesmo-horario >={th}x',rs>=th)
        for th in (2,3): put(f'vol k20 >={th}x',V[20]>=th); put(f'vol mesmo-horario >={th}x',vs>=th)
        put('negocio medio >=1.5x',Sr>=1.5); put('negocio medio <=0.67x',Sr<=0.67)
        put('tam>=2 & vol>=2',(R[20]>=2)&(V[20]>=2)); put('tam>=2 & vol<1',(R[20]>=2)&(V[20]<1))
        put('absorcao vol>=2 & tam<=1',(V[20]>=2)&(R[20]<=1),np.zeros(n)); put('absorcao vol>=2 & tam<=0.7',(V[20]>=2)&(R[20]<=0.7),np.zeros(n))
        put('marubozu corpo>=.8 & tam>=2',(R[20]>=2)&(body>=.8*rng)); put('pavio corpo<=.3 & tam>=2',(R[20]>=2)&(body<=.3*rng),np.zeros(n))
        big=R[20]>=2
        # 1a vela grande do dia / seguintes
        cnt=np.cumsum(big)
        put('tam>=2 1a do dia',big&(cnt==1)); put('tam>=2 2a em diante',big&(cnt>=2))
        # isolada vs saindo de lateralizacao
        r3=prevmean(rng,3); r17=np.full(n,np.nan)
        cs=np.r_[0,np.cumsum(rng)]
        for i in range(20,n): r17[i]=(cs[i-3]-cs[i-20])/17
        comp=r3<=0.8*r17
        put('tam>=2 apos compressao',big&comp); put('tam>=2 isolada(sem compressao)',big&~comp)
        # rompe maxima/minima das 10 anteriores
        hh=np.full(n,np.nan); ll=hh.copy()
        for i in range(10,n): hh[i]=h[i-10:i].max(); ll[i]=l[i-10:i].min()
        rup=c>hh; rdn=c<ll
        put('tam>=2 fecha alem de box10',big&(rup|rdn),np.where(rup,1,-1)); put('tam>=2 dentro de box10',big&~(rup|rdn))
        # compressao
        for k in (10,20,30):
            if tf!=1 and k>20: continue
            kk=k if tf==1 else max(3,k//tf*1)
            rk=np.full(n,np.nan); rp=rk.copy()
            for i in range(2*kk-1,n):
                rk[i]=h[i-kk+1:i+1].max()-l[i-kk+1:i+1].min(); rp[i]=h[i-2*kk+1:i-kk+1].max()-l[i-2*kk+1:i-kk+1].min()
            for th in (.5,.35): put(f'compressao k{kk} <={th}',(rk/rp)<=th,np.zeros(n))
        for m in (4,7):
            nr=np.zeros(n,bool)
            for i in range(m-1,n): nr[i]=rng[i]<=rng[i-m+1:i+1].min()
            put(f'NR{m}',nr,np.zeros(n))
        ins=np.zeros(n,bool); ins[1:]=(h[1:]<=h[:-1])&(l[1:]>=l[:-1]); put('inside bar',ins,np.zeros(n))
        ins2=ins.copy(); ins2[1:]&=ins[:-1]; put('2 inside bars',ins2,np.zeros(n))
        # aceleracao
        g3=np.zeros(n,bool); 
        for i in range(2,n): g3[i]=(sg[i]==sg[i-1]==sg[i-2]!=0) and rng[i]>rng[i-1]>rng[i-2]
        put('3 velas mesma cor, tam crescente',g3)
        a3=prevmean(rng,1)*0; r3m=(rng+np.r_[np.nan,rng[:-1]]+np.r_[np.nan,np.nan,rng[:-2]])/3
        pm=prevmean(rng,20); acc=np.full(n,np.nan); acc[3:]=r3m[3:]/pm[3:] if False else np.nan
        # media das 3 ultimas / media das 20 anteriores a elas
        for i in range(23,n): acc[i]=rng[i-2:i+1].mean()/rng[i-22:i-2].mean()
        put('aceleracao: media3/media20 >=1.5',acc>=1.5)
        c3=np.zeros(n,bool)
        for i in range(2,n): c3[i]=(sg[i]==sg[i-1]==sg[i-2]!=0)
        put('3 velas mesma cor',c3)
    # lateralizacao em M1: janela L com range<=cap
    h1,l1,c1=x['h'],x['l'],x['c']; n1=len(c1); idx1=np.arange(n1)
    for L in (20,30,45):
        bh=np.full(n1,np.nan); bl=bh.copy()
        for i in range(L,n1): bh[i]=h1[i-L:i].max(); bl[i]=l1[i-L:i].min()
        box=bh-bl
        for cap in (150,250):
            lat=box<=cap
            res[f'lateral M1 L{L} box<={cap}']=(lat,np.zeros(n1),idx1)
            ru=lat&(c1>bh); rd=lat&(c1<bl)
            res[f'rompe lateral M1 L{L} box<={cap}']=(ru|rd,np.where(ru,1,-1),idx1)
    return res
