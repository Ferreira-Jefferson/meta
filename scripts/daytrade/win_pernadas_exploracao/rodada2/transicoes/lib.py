import numpy as np, pandas as pd
CSV="C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WINV26_M1_202604151210_202610011824.csv"
def load():
    d=pd.read_csv(CSV,sep="\t")
    d.columns=[c.strip("<>").lower() for c in d.columns]
    d=d[d["date"].str.startswith("2026.09")].copy()
    d["mn"]=d["time"].str[:2].astype(int)*60+d["time"].str[3:5].astype(int)
    days=[]
    for dt,g in d.groupby("date"):
        g=g.sort_values("mn")
        days.append(dict(date=dt,mn=g.mn.values,o=g.open.values,h=g.high.values,l=g.low.values,c=g.close.values))
    return days
def rel(day):
    o,h,l,c=day["o"],day["h"],day["l"],day["c"]
    return np.c_[h-o,l-o,c-o,(c>=o).astype(float)]  # shape rel to open
def build(day,order=None):
    """chain bars (open=prev close except 1st); returns p, t(min), dayopen"""
    r=rel(day); mn=day["mn"]
    if order is None: order=np.arange(len(mn))
    p=[];t=[];cur=day["o"][0]
    for k,i in enumerate(order):
        dh,dl,dc,up=r[i]
        o=cur
        if up: seq=[o,o+dl,o+dh,o+dc]
        else: seq=[o,o+dh,o+dl,o+dc]
        p+=seq; t+=[mn[k]]*4   # time slot = position k (bar slot), preserves hour profile
        cur=o+dc
    return np.array(p),np.array(t),day["o"][0]
def shuffled_order(day,rng,block=30):
    mn=day["mn"]; blk=(mn-540)//block
    order=np.arange(len(mn)); out=order.copy()
    for b in np.unique(blk):
        idx=np.where(blk==b)[0]; out[idx]=rng.permutation(idx)
    return out
def zigzag(p,thr):
    n=len(p); lo=hi=0; d=0
    for i in range(n):
        if p[i]>p[hi]:hi=i
        if p[i]<p[lo]:lo=i
        if p[i]-p[lo]>=thr: d=1;start=lo;ext=i;break
        if p[hi]-p[i]>=thr: d=-1;start=hi;ext=i;break
    if d==0: return []
    legs=[]
    for i in range(ext+1,n):
        if d==1:
            if p[i]>p[ext]: ext=i
            elif p[ext]-p[i]>=thr:
                legs.append((start,ext,1,i)); start=ext; d=-1; ext=i
        else:
            if p[i]<p[ext]: ext=i
            elif p[i]-p[ext]>=thr:
                legs.append((start,ext,-1,i)); start=ext; d=1; ext=i
    legs.append((start,ext,d,None))
    return legs
