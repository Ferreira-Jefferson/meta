import pandas as pd, numpy as np
R="C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/"
def load(f,lo,hi):
    d=pd.read_csv(R+f,sep="\t"); d.columns=[c.strip("<>").lower() for c in d.columns]
    d["ts"]=pd.to_datetime(d["date"]+" "+d["time"],format="%Y.%m.%d %H:%M:%S"); d=d.set_index("ts")
    return d[(d.index>=lo)&(d.index<hi)]
win_all=load("WINV26_M1_202604151210_202610011824.csv","2026-08-20","2026-10-01")
win=win_all[win_all.index>="2026-09-01"].copy()
wdo=load("WDO@D_M1_202109290900_202609291020.csv","2026-09-01","2026-09-30")
win["d"]=win.index.date; wdo["d"]=wdo.index.date
days=sorted(win.d.unique())
prevclose={}
prev=win_all[win_all.index<"2026-09-01"].close.iloc[-1]
for d in days:
    prevclose[d]=prev; prev=win[win.d==d].close.iloc[-1]
def rs(df,rule):
    r=df.resample(rule,label="left",closed="left").agg({"open":"first","high":"max","low":"min","close":"last","vol":"sum"}).dropna()
    r["d"]=r.index.date; return r
def zigzag(bars,thr=750):
    """bars: df of one day. returns list of legs dict(dir,start_i,end_i,p0,p1,t0,t1). path: up bar low->high, down bar high->low"""
    pts=[]
    for ts,r in bars.iterrows():
        if r.close>=r.open: pts+= [(ts,r.low),(ts,r.high)]
        else: pts+= [(ts,r.high),(ts,r.low)]
    legs=[]; 
    # standard zigzag
    ext_i=0; ext_p=pts[0][1]; d=0; piv_i=0; piv_p=pts[0][1]
    hi_i=lo_i=0; hi=lo=pts[0][1]
    pivots=[]; direction=0
    for i,(ts,p) in enumerate(pts):
        if direction==0:
            if p>hi: hi,hi_i=p,i
            if p<lo: lo,lo_i=p,i
            if hi-lo>=thr:
                if hi_i>lo_i: pivots.append((lo_i,lo)); direction=1; cur_i,cur=hi_i,hi
                else: pivots.append((hi_i,hi)); direction=-1; cur_i,cur=lo_i,lo
                if direction==1 and p>cur: cur_i,cur=i,p
                if direction==-1 and p<cur: cur_i,cur=i,p
        elif direction==1:
            if p>cur: cur_i,cur=i,p
            elif cur-p>=thr: pivots.append((cur_i,cur)); direction=-1; cur_i,cur=i,p
        else:
            if p<cur: cur_i,cur=i,p
            elif p-cur>=thr: pivots.append((cur_i,cur)); direction=1; cur_i,cur=i,p
    if direction!=0: pivots.append((cur_i,cur))  # open leg end
    out=[]
    for k in range(len(pivots)-1):
        (i0,p0),(i1,p1)=pivots[k],pivots[k+1]
        out.append(dict(dir=1 if p1>p0 else -1,p0=p0,p1=p1,t0=pts[i0][0],t1=pts[i1][0],closed=(k<len(pivots)-2)))
    return out
