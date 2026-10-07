import numpy as np, pandas as pd, itertools, datetime as dt
CSV='C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv'
CUSTO=2.0; SLIP=5.0; TICK=5.0; HOLD=30

def carrega():
    d=pd.read_csv(CSV,sep='\t'); d=d[d['<DATE>'].str.startswith('2026')]
    d['dia']=d['<DATE>'].str.replace('.','-',regex=False)
    d['min']=d['<TIME>'].str[:2].astype(int)*60+d['<TIME>'].str[3:5].astype(int)
    out={}
    for dia,g in d.groupby('dia'):
        out[dia]=dict(t=g['min'].values,o=g['<OPEN>'].values,h=g['<HIGH>'].values,l=g['<LOW>'].values,c=g['<CLOSE>'].values)
    return out

def dst_us(dia):
    return '2026-03-08'<=dia<'2026-11-01'

def janela(nome,dia):
    if nome=='0900':return 540,570
    if nome=='0930':return 570,600
    if nome=='1000':return 600,630
    ny=630 if dst_us(dia) else 690
    return ny,ny+30   # 'NY'

def embaralha(dias,rng,bloco=30):
    out={}
    for dia,x in dias.items():
        n=len(x['t']);o,h,l,c=x['o'],x['h'],x['l'],x['c']
        # velas como deltas relativos a close anterior: preserva forma, embaralha dentro do bloco
        prev=np.r_[o[0],c[:-1]]
        do,dh,dl,dc=o-prev,h-prev,l-prev,c-prev
        idx=np.arange(n);blk=(x['t']-540)//bloco
        perm=idx.copy()
        for b in np.unique(blk):
            ii=np.where(blk==b)[0];perm[ii]=rng.permutation(ii)
        do,dh,dl,dc=do[perm],dh[perm],dl[perm],dc[perm]
        nc=o[0]+np.cumsum(dc+0)  # encadeia: cada vela abre no fechamento anterior
        # reconstruir: vela k abre em P_{k-1}; P_k=P_{k-1}+(dc_k - 0)
        P=np.empty(n);p=o[0]
        no=np.empty(n);nh=np.empty(n);nl=np.empty(n)
        for k in range(n):
            no[k]=p;nh[k]=p+(dh[k]-do[k]);nl[k]=p+(dl[k]-do[k]);p=p+(dc[k]-do[k]);P[k]=p
        out[dia]=dict(t=x['t'],o=no,h=nh,l=nl,c=P)
    return out

def sim_dia(x,dia,win,M,K,d,prazo,alvo,stop):
    """retorna lista de (pnl_cons,pnl_otim,atraso) por ordem enviada; pnl None se nao encheu"""
    t,o,h,l,c=x['t'],x['o'],x['h'],x['l'],x['c'];n=len(t)
    ws,we=janela(win,dia)
    res=[];i=K
    while i<n-2:
        if t[i]<ws or t[i]>=we: 
            i+=1;continue
        if t[i]-t[i-K]!=K: i+=1;continue
        mv=c[i]-c[i-K]
        if abs(mv)<M: i+=1;continue
        side=-1 if mv>0 else 1  # -1 vende (fade de alta)
        L=c[i]+(d if mv>0 else -d)
        r=[None,None,None];fim=i+prazo
        for mode in (0,1):
            fill=None
            for j in range(i+1,min(i+1+prazo,n)):
                if side==-1: ok=h[j]>=L+(TICK if mode==0 else 0)
                else: ok=l[j]<=L-(TICK if mode==0 else 0)
                if ok: fill=j;break
            if fill is None: continue
            S=L-side*stop;T=L+side*alvo
            pnl=None;ex=None
            # barra do fill: so o stop conta
            hit=(h[fill]>=S) if side==-1 else (l[fill]<=S)
            if hit: pnl=-stop-SLIP-CUSTO;ex=fill
            else:
                last=min(fill+HOLD,n-1)
                for k in range(fill+1,last+1):
                    hs=(h[k]>=S) if side==-1 else (l[k]<=S)
                    if hs: pnl=-stop-SLIP-CUSTO;ex=k;break
                    tg=(l[k]<=T-(TICK if mode==0 else 0)) if side==-1 else (h[k]>=T+(TICK if mode==0 else 0))
                    if tg: pnl=alvo-CUSTO;ex=k;break
                if pnl is None:
                    pnl=side*(c[last]-L)*(-1)*(-1) if False else (L-c[last] if side==-1 else c[last]-L);pnl=pnl-SLIP-CUSTO;ex=last
            r[mode]=(pnl,ex,fill-i)
        res.append(r)
        # proximo gatilho: depois do fim da ordem/posicao (modo conservador manda)
        i=(r[0][1]+1) if r[0] is not None else fim
    return res

def config_run(dias,lista_dias,cfg):
    win,M,K,d,prazo,alvo,stop=cfg
    per_dia=[]
    for dia in lista_dias:
        rs=sim_dia(dias[dia],dia,win,M,K,d,prazo,alvo,stop)
        per_dia.append(rs)
    return per_dia

def resume(per_dia,mode,rng=None,nb=400):
    pn=[];sd=np.zeros(len(per_dia));cn=np.zeros(len(per_dia));nord=0;atr=[]
    for q,rs in enumerate(per_dia):
        for r in rs:
            nord+=1
            if r[mode] is not None:
                pn.append(r[mode][0]);sd[q]+=r[mode][0];cn[q]+=1;atr.append(r[mode][2])
    pn=np.array(pn);n=len(pn)
    if n==0: return None
    g=pn[pn>0];p=pn[pn<=0]
    gm=g.mean() if len(g) else 0;pm=-p.mean() if len(p) else 0
    be=pm/(gm+pm) if gm+pm>0 else np.nan
    ev=pn.mean()
    ci=(np.nan,np.nan)
    if rng is not None:
        nd=len(per_dia);bs=[]
        for _ in range(nb):
            ix=rng.integers(0,nd,nd);cc=cn[ix].sum()
            if cc>0: bs.append(sd[ix].sum()/cc)
        ci=tuple(np.percentile(bs,[2.5,97.5]))
    ativos=cn>0
    # pior sequencia de perdas
    seq=0;worst=0
    for v in pn:
        if v<=0: seq+=1;worst=max(worst,seq)
        else: seq=0
    return dict(n=n,ordens=nord,fill=n/nord,acerto=len(g)/n,ganho=gm,perda=pm,be=be,ev=ev,lo=ci[0],hi=ci[1],
                dias_pos=(sd[ativos]>0).mean(),worst=worst,atraso=float(np.mean(atr)))

def grade():
    return list(itertools.product(['0900','0930','1000','NY'],[150,250,350],[5,10,15],[0,50,100],[5,10],[100,150,200,300],[150,250,400]))
