"""Eventos 'avanco A seguido de recuo r' + participacao sintetica no avanco e no recuo + desfechos.
Decisao no FECHAMENTO da vela M1 em que o recuo >= r*A (sem olhar adiante). Desfechos a partir dali.
Caminho dentro da vela: alta min->max, baixa max->min (convencao do projeto).  Participacao da vela alocada
nos 3 trechos do caminho proporcionalmente ao comprimento (mesmo codigo no real e no nulo embaralhado)."""
import numpy as np, pandas as pd
LEVELS=(0.38,0.50,0.62); AMIN=150; TICK=5; SLIP=5; COST=2; TTL=20
GEOM=((200,200),(400,200))
COLS=["lv","A","hb","mnd","dur_ret","T_adv","T_ret",
 "N1","N2","V2","E1","E2","S1","S2","D1","D2","D3","P1","P2","okrel","oktick",
 "NH","P20","MFE15","MAE15","MFE30","MAE30","MFE60","MAE60","fill","E_g1","E_g2","ret_real"]
FEATS=["N1","N2","V2","E1","E2","S1","S2","P1","P2","D1","D2","D3"]
TICKFEATS={"D1","D2","D3"}

def prep_days(c):
    days=[]
    for dt,g in c.groupby("date",sort=True):
        if len(g)<60: continue
        g=g.sort_values("mn")
        days.append(dict(date=dt,mn=g.mn.values,o=g.open.values,h=g.high.values,l=g.low.values,c=g.close.values,
            N=g.tickvol_rel.values,V=g.vol_rel.values,vol=g.vol.values.astype(float),dt=g.dt.values,dsgn=g.dsgn.values,
            okrel=(~np.isnan(g.tickvol_rel.values))&(~np.isnan(g.vol_rel.values)),oktick=~np.isnan(g.dt.values)))
    return days

def shuffled_order(day,rng,block=30):
    mn=day["mn"]; blk=(mn-540)//block; out=np.arange(len(mn))
    for b in np.unique(blk):
        idx=np.where(blk==b)[0]; out[idx]=rng.permutation(idx)
    return out

def build(day,order):
    o,h,l,c=day["o"],day["h"],day["l"],day["c"]; mn=day["mn"]; n=len(mn)
    dh=(h-o)[order];dl=(l-o)[order];dc=(c-o)[order];up=(c>=o)[order]
    p=np.empty(4*n);cur=o[0]
    for k in range(n):
        if up[k]: p[4*k:4*k+4]=(cur,cur+dl[k],cur+dh[k],cur+dc[k])
        else: p[4*k:4*k+4]=(cur,cur+dh[k],cur+dl[k],cur+dc[k])
        cur+=dc[k]
    return p

def cums(day,order,p):
    n=len(order); p4=p.reshape(n,4); L3=np.abs(np.diff(p4,axis=1)); tot=L3.sum(1,keepdims=True)
    sh=np.where(tot>0,L3/np.where(tot>0,tot,1.0),1/3)
    S=np.zeros((n,4)); S[:,:3]=sh
    def seg(v): return (S*np.nan_to_num(v[order])[:,None]).ravel()
    ok_rel=day["okrel"][order]; ok_tk=day["oktick"][order]
    arr=dict(T=S.ravel(),N=seg(day["N"]),V=seg(day["V"]),Vr=seg(day["vol"]),D=seg(day["dt"]),P=seg(day["dsgn"]),
             bR=(S*(~ok_rel)[:,None]).ravel(),bT=(S*(~ok_tk)[:,None]).ravel())
    return {k:np.concatenate([[0.0],np.cumsum(v)]) for k,v in arr.items()}

def _win(C,a,b,sg):
    return {k:(C[k][b]-C[k][a])*(sg if k in("D","P") else 1) for k in C}

def feats(C,p,iL,iH,d,sg):
    A=_win(C,iL,iH,sg); R=_win(C,iH,d,sg)
    Ta,Tr=A["T"],R["T"]
    if Ta<0.25 or Tr<0.25: return None
    okrel=(A["bR"]+R["bR"])<1e-9; oktick=okrel and (A["bT"]+R["bT"])<1e-9
    nan=np.nan
    pa=abs(p[iH]-p[iL]); pr=abs(p[iH]-p[d])
    if not okrel: return Ta,Tr,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,0,0
    Ni_a=A["N"]/Ta; Ni_r=R["N"]/Tr; Vi_a=A["V"]/Ta; Vi_r=R["V"]/Tr
    N1=Ni_r; N2=Ni_r/Ni_a if Ni_a>0 else nan; V2=Vi_r/Vi_a if Vi_a>0 else nan
    ea=A["V"]/pa; er=R["V"]/pr; E1=er; E2=er/ea if ea>0 else nan
    ta=A["V"]/A["N"] if A["N"]>0 else nan; tr_=R["V"]/R["N"] if R["N"]>0 else nan
    S1=tr_; S2=tr_/ta if (ta and ta>0) else nan
    P1=R["P"]/R["Vr"] if R["Vr"]>0 else nan; Pa=A["P"]/A["Vr"] if A["Vr"]>0 else nan; P2=P1-Pa
    if oktick:
        D1=R["D"]/R["Vr"] if R["Vr"]>0 else nan; Da=A["D"]/A["Vr"] if A["Vr"]>0 else nan; D2=D1-Da
        D3=(A["D"]+R["D"])/(A["Vr"]+R["Vr"])
    else: D1=D2=D3=nan
    return Ta,Tr,N1,N2,V2,E1,E2,S1,S2,D1,D2,D3,P1,P2,1,int(oktick)

def outcomes(p,d,H,L,A,n_end):
    x=p[d]; s=p[d+1:]
    a=np.flatnonzero(s>H); tH=a[0] if a.size else 10**9
    b=np.flatnonzero(s<=L); tL=b[0] if b.size else 10**9
    nh=np.nan if (tH==10**9 and tL==10**9) else float(tH<tL)
    tg=L+2*A; c=np.flatnonzero(s>=tg); t2=c[0] if c.size else 10**9
    p2=np.nan if (t2==10**9 and tL==10**9) else float(t2<tL)
    out=[nh,p2]
    for W in (15,30,60):
        seg=s[:4*W]
        if len(seg)<4*W: out+= [np.nan,np.nan]
        else: out+=[seg.max()-x, x-seg.min()]
    # execucao: limite em x, enche se negociar 1 tick alem
    fe=np.flatnonzero(s[:TTL]<=x-TICK)
    if fe.size==0: return out+[0.0,0.0,0.0]
    j0=fe[0]; w=s[j0:j0+240]
    if len(w)<240: end_pt=w[-1]; trunc=True
    else: end_pt=w[-1]
    res=[1.0]
    for T,S in GEOM:
        ht=np.flatnonzero(w>=x+T+TICK); hs=np.flatnonzero(w<=x-S)
        it=ht[0] if ht.size else 10**9; is_=hs[0] if hs.size else 10**9
        if it==10**9 and is_==10**9: r=end_pt-x-SLIP-COST
        elif is_<=it: r=-S-SLIP-COST
        else: r=T-COST
        res.append(r)
    return out+res

def day_events(day,order=None):
    n=len(day["mn"])
    if order is None: order=np.arange(n)
    p0=build(day,order); C=cums(day,order,p0); mn=day["mn"]; rows=[]
    for sg in (1,-1):
        p=p0*sg
        N=len(p); L=H=p[0]; iL=iH=0; trig=[False]*3
        for k in range(n):
            for i in range(4*k+ (1 if k==0 else 0),4*k+4):
                x=p[i]
                if x<=L: L=H=x; iL=iH=i; trig=[False]*3
                elif x>H: H=x; iH=i; trig=[False]*3
            d=4*k+3; x=p[d]; A=H-L
            if A<AMIN or x<=L or H<=x: continue
            dd=H-x
            for q,r in enumerate(LEVELS):
                if trig[q] or dd<r*A: continue
                trig[q]=True
                f=feats(C,p,iL,iH,d,sg)
                if f is None: continue
                o=outcomes(p,d,H,L,A,N)
                m=mn[k]; hb=0 if m<660 else (1 if m<780 else 2)
                rows.append((q,A,hb,m,(d-iH)/4.0)+f+tuple(o)+(dd/A,))
    return rows

def events_table(days,seed=None):
    rng=None if seed is None else np.random.default_rng(seed)
    out=[]
    for di,day in enumerate(days):
        order=None if rng is None else shuffled_order(day,rng)
        for r in day_events(day,order): out.append((di,)+r)
    return pd.DataFrame(out,columns=["day"]+COLS)
