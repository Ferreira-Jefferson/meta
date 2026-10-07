import numpy as np, pandas as pd, io
CSV="C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
LEVELS=[0.10,0.20,0.30,0.38,0.50,0.62,0.78]
AMIN=150
def load_days(m0,m1):
    """so linhas de 2026, meses m0..m1 inclusive"""
    keep=[];hdr=None
    with open(CSV,encoding="utf-8") as f:
        hdr=f.readline()
        for ln in f:
            if ln.startswith("2026."):
                m=int(ln[5:7])
                if m0<=m<=m1: keep.append(ln)
    d=pd.read_csv(io.StringIO(hdr+"".join(keep)),sep="\t")
    d.columns=[c.strip("<>").lower() for c in d.columns]
    d["mn"]=d["time"].str[:2].astype(int)*60+d["time"].str[3:5].astype(int)
    days=[]
    for dt,g in d.groupby("date"):
        g=g.sort_values("mn")
        if len(g)<60: continue
        days.append(dict(date=dt,mn=g.mn.values,o=g.open.values,h=g.high.values,l=g.low.values,c=g.close.values))
    return days
def build(day,order=None):
    o,h,l,c=day["o"],day["h"],day["l"],day["c"]
    mn=day["mn"]; n=len(mn)
    if order is None: order=np.arange(n)
    dh=(h-o)[order];dl=(l-o)[order];dc=(c-o)[order];up=(c>=o)[order]
    p=np.empty(4*n);t=np.repeat(mn,4);cur=o[0]
    for k in range(n):
        if up[k]: s=(cur,cur+dl[k],cur+dh[k],cur+dc[k])
        else: s=(cur,cur+dh[k],cur+dl[k],cur+dc[k])
        p[4*k:4*k+4]=s; cur=cur+dc[k]
    return p,t
def shuffled_order(day,rng,block=30):
    mn=day["mn"]; blk=(mn-540)//block
    out=np.arange(len(mn))
    for b in np.unique(blk):
        idx=np.where(blk==b)[0]; out[idx]=rng.permutation(idx)
    return out
def events_dir(p,t):
    """sinal ja orientado: movimento de ALTA. retorna lista de eventos"""
    ev=[];n=len(p)
    L=p[0];H=p[0];iH=0;newH=True;trig=[False]*len(LEVELS);nord=0;ord20=False
    for i in range(1,n):
        x=p[i]
        if x<=L:
            L=x;H=x;iH=i;trig=[False]*len(LEVELS);nord=0;ord20=False;continue
        if x>H:
            if trig[1]: nord+=1
            H=x;iH=i;trig=[False]*len(LEVELS);continue
        A=H-L
        if A<AMIN: continue
        dd=H-x
        for k,r in enumerate(LEVELS):
            if not trig[k] and dd>=r*A:
                trig[k]=True
                ev.append((i,k,A,H,L,iH,nord+1))
    out=[]
    for (i,k,A,H,L,iH,od) in ev:
        s=p[i+1:]
        a=np.flatnonzero(s>H); tH=a[0] if a.size else 10**9
        b=np.flatnonzero(s<=L); tL=b[0] if b.size else 10**9
        res=[]
        for mult in (1.0,1.5,2.0):
            tg=L+mult*A if mult>1 else None
            if mult==1.0:
                tt=tH
            else:
                c=np.flatnonzero(s>=tg); tt=c[0] if c.size else 10**9
            if tt==10**9 and tL==10**9: res.append(np.nan)
            else: res.append(1.0 if tt<tL else 0.0)
        # tempo ate resolver (barras)
        out.append((k,A,t[i],od,(i-iH)//4,res[0],res[1],res[2]))
    return out
def events_day(p,t):
    return events_dir(p,t)+events_dir(-p,t)
COLS=["lv","A","hh","ord","dur","NH","P15","P20"]
def events_all(days,rng=None):
    rows=[]
    for di,day in enumerate(days):
        order=None if rng is None else shuffled_order(day,rng)
        p,t=build(day,order)
        for e in events_day(p,t): rows.append((di,)+e)
    return pd.DataFrame(rows,columns=["day"]+COLS)
