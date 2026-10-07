import pandas as pd, numpy as np, sys, glob, os
from concurrent.futures import ProcessPoolExecutor, as_completed
R="C:/Users/Jeffe/Documents/study/meta/"
T=750; XS=[150,250,375,500]
def m1():
    d=pd.read_csv(R+"data/wdo-mt5/WINV26_M1_202604151210_202610011824.csv",sep="\t")
    d.columns=[c.strip("<>").lower() for c in d.columns]
    d["ts"]=pd.to_datetime(d["date"]+" "+d["time"],format="%Y.%m.%d %H:%M:%S")
    d=d.set_index("ts")[["open","high","low","close","vol"]].astype(float)
    d=d[d.index>="2026-08-15"]
    c=d.close
    d["day"]=d.index.date
    d["ema9"]=c.ewm(span=9,adjust=False).mean(); d["ema21"]=c.ewm(span=21,adjust=False).mean()
    dl=c.diff(); up=dl.clip(lower=0).ewm(alpha=1/14,adjust=False).mean(); dn=(-dl).clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    d["rsi"]=100-100/(1+up/dn)
    tr=(d.high-d.low)
    d["atr5m"]=tr.rolling(70).mean()*np.sqrt(5)  # aprox. amplitude M5
    tp=(d.high+d.low+d.close)/3
    d["vwap"]=(tp*d.vol).groupby(d.day).cumsum()/d.vol.groupby(d.day).cumsum()
    d["ma50"]=c.rolling(50).mean()
    return d
def zz(p):
    piv=[]  # (idx,price,type 'L'/'H', confirm idx)
    hi=lo=p[0];hi_i=lo_i=0;dr=0
    for i in range(1,len(p)):
        x=p[i]
        if dr==0:
            if x>hi:hi=x;hi_i=i
            if x<lo:lo=x;lo_i=i
            if x-lo>=T: piv.append((lo_i,lo,'L',i));dr=1;ext=x;ei=i
            elif hi-x>=T: piv.append((hi_i,hi,'H',i));dr=-1;ext=x;ei=i
        elif dr==1:
            if x>ext:ext=x;ei=i
            elif ext-x>=T: piv.append((ei,ext,'H',i));dr=-1;ext=x;ei=i
        else:
            if x<ext:ext=x;ei=i
            elif x-ext>=T: piv.append((ei,ext,'L',i));dr=1;ext=x;ei=i
    return piv
def run(f,M):
    day=os.path.basename(f)[:-4]
    df=pd.read_pickle(f)
    fl=df["flags"].values; ok=((fl&8)>0)&(df.volume.values>0)
    df=df[ok]; fl=df["flags"].values
    t=df.time_msc.values.astype(np.int64); p=df["last"].values.astype(float); v=df.volume.values.astype(float)
    b=((fl&32)>0)&((fl&64)==0); s=((fl&64)>0)&((fl&32)==0)
    z=np.zeros(1)
    cv=np.concatenate([z,np.cumsum(v)]); cb=np.concatenate([z,np.cumsum(v*b)]); cs=np.concatenate([z,np.cumsum(v*s)]); cn=np.concatenate([z,np.arange(1,len(v)+1)])
    W=lambda c,a,bb:c[bb+1]-c[a]
    piv=zz(p)
    ts=pd.to_datetime(t,unit="ms")
    mm=M[M.day==pd.Timestamp(day).date()]
    mi_=M.index
    out=[]
    for sign in (1,-1):
        q=p*sign
        # legs
        prevleg=None
        for k in range(len(piv)-1):
            l=piv[k]; h=piv[k+1]
            if (l[2]=='L')!=(sign==1): continue
            li,hi_,ci=l[0],h[0],h[3]
            seg=q[li:ci+1]
            cm=np.maximum.accumulate(seg)
            new=np.concatenate([[True],seg[1:]>cm[:-1]])
            mi=np.maximum.accumulate(np.where(new,np.arange(len(seg)),0))
            pl=piv[k-1] if k>=1 else None
            pleg=abs(l[1]-piv[k-1][1]) if k>=1 else np.nan
            for X in XS:
                idx=np.flatnonzero((cm-seg)>=X)
                if len(idx)==0: continue
                u,fi=np.unique(mi[idx],return_index=True)
                for mloc,j in zip(u,idx[fi]):
                    m=li+mloc; d=li+j
                    rise=cm[mloc]-seg[0]
                    if rise<500: continue
                    turn=int(m==hi_)
                    r=dict(day=day,sign=sign,X=X,turn=turn,m=m,d=d,rise=rise,prevleg=pleg)
                    tm=ts[m];td=ts[d]; r["hour"]=tm.hour; r["minopen"]=(tm-tm.normalize()).total_seconds()/60-540
                    dur=(t[m]-t[li])/60000; r["dur"]=dur; r["speed"]=rise/max(dur,.5)
                    rs=(t[d]-t[m])/1000; r["recsec"]=rs; r["dropspeed"]=X/max(rs,1)
                    # janelas
                    def agg(a,bb):
                        V=W(cv,a,bb);B=W(cb,a,bb);S=W(cs,a,bb);N=W(cn,a,bb);return V,B,S,N
                    Vl,Bl,Sl,Nl=agg(li,m); 
                    r["leg_delta"]=sign*(Bl-Sl)/max(Vl,1)
                    r["leg_avgsz"]=Vl/max(Nl,1); r["leg_vrate"]=Vl/max(dur,.5); r["leg_nrate"]=Nl/max(dur,.5)
                    a5=np.searchsorted(t,t[m]-5*60000); V5,B5,S5,N5=agg(a5,m)
                    r["pre5_delta"]=sign*(B5-S5)/max(V5,1); r["pre5_vrel"]=(V5/5)/(r["leg_vrate"]+1e-9); r["pre5_avgsz_rel"]=(V5/max(N5,1))/r["leg_avgsz"]
                    r["pre5_nrel"]=(N5/5)/(r["leg_nrate"]+1e-9)
                    a1=np.searchsorted(t,t[m]-60000); V1,B1,S1,N1=agg(a1,m); r["pre1_vrel"]=V1/(r["leg_vrate"]+1e-9); r["pre1_delta"]=sign*(B1-S1)/max(V1,1)
                    # divergencia: delta do ultimo terco x primeiro
                    n3=(m-li)//3
                    if n3>50:
                        _,Ba,Sa,_=agg(li,li+n3); Va=agg(li,li+n3)[0]; _,Bc,Sc,_=agg(m-n3,m); Vc=agg(m-n3,m)[0]
                        r["div_delta"]=sign*((Bc-Sc)/max(Vc,1)-(Ba-Sa)/max(Va,1))
                    Vr,Br,Sr,Nr=agg(m,d); rsec=max(rs,1)/60
                    r["rec_delta"]=-sign*(Br-Sr)/max(Vr,1)   # + = agressao a favor da virada
                    r["rec_vrel"]=(Vr/rsec)/(r["leg_vrate"]+1e-9); r["rec_nrel"]=(Nr/rsec)/(r["leg_nrate"]+1e-9); r["rec_avgsz_rel"]=(Vr/max(Nr,1))/r["leg_avgsz"]
                    r["rec_vabs"]=Vr
                    # indicadores
                    bt=tm.floor("min")-pd.Timedelta(minutes=1); bd=td.floor("min")-pd.Timedelta(minutes=1)
                    if bt in mi_ and bd in mi_:
                        A=M.loc[bt]; D=M.loc[bd]; atr=A.atr5m
                        r["rise_atr"]=rise/atr
                        r["rsi_top"]=sign*(A.rsi-50)+50
                        r["vwapdist"]=sign*(A.close-A.vwap)/atr
                        r["ema_spread"]=sign*(A.ema9-A.ema21)/atr
                        r["ma50dist"]=sign*(A.close-A.ma50)/atr
                        r["cross9_d"]=int(sign*(D.close-D.ema9)<0); r["cross921_d"]=int(sign*(D.ema9-D.ema21)<0); r["below21_d"]=int(sign*(D.close-D.ema21)<0)
                        r["cross9_chg"]=int(sign*(A.close-A.ema9)>0 and sign*(D.close-D.ema9)<0)
                        r["rsi_d"]=sign*(D.rsi-50)+50
                        r["vwapcross"]=int(sign*(A.close-A.vwap)>0 and sign*(D.close-D.vwap)<0)
                        r["atr"]=atr
                    mt=tm.floor("min")
                    if td.floor("min")>mt and mt in mi_:
                        B_=M.loc[mt]; rg=max(B_.high-B_.low,1)
                        r["wick_top"]=(B_.high-max(B_.open,B_.close))/rg if sign==1 else (min(B_.open,B_.close)-B_.low)/rg
                        r["body_top"]=sign*(B_.close-B_.open)/rg
                    out.append(r)
    return pd.DataFrame(out)
if __name__=="__main__":
    M=m1()
    fs=sorted(glob.glob(R+"data/cache_win_ticks/WINV26/2026-09-*.pkl"))
    res=[]
    with ProcessPoolExecutor(3) as ex:
        fu={ex.submit(run,f,M):f for f in fs}
        for x in as_completed(fu):
            d=x.result(); res.append(d); print(os.path.basename(fu[x]),len(d),flush=True)
    pd.concat(res).to_pickle("eventos.pkl")
