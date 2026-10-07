import pandas as pd, numpy as np
pd.set_option("display.width",250); pd.set_option("display.max_columns",50)
E=pd.read_pickle("eventos.pkl"); E["hg"]=np.where(E.hour<=10,"09-10",np.where(E.hour<=12,"11-12",np.where(E.hour<=14,"13-14","15+")))
FE=["rise","rise_atr","dur","speed","prevleg","minopen","leg_delta","leg_avgsz","leg_vrate","pre5_delta","pre5_vrel","pre5_avgsz_rel","pre5_nrel","pre1_vrel","pre1_delta","div_delta","rec_delta","rec_vrel","rec_nrel","rec_avgsz_rel","rec_vabs","recsec","dropspeed","rsi_top","rsi_d","vwapdist","ema_spread","ma50dist","cross9_d","cross921_d","below21_d","cross9_chg","vwapcross","wick_top","body_top","atr"]
def auc(x,y):
    m=~np.isnan(x); x=x[m];y=y[m]
    if y.sum()==0 or y.sum()==len(y): return np.nan
    r=pd.Series(x).rank().values; n1=y.sum(); n0=len(y)-n1
    return (r[y==1].sum()-n1*(n1+1)/2)/(n1*n0)
def saucs(d,f,strat="hg"):
    num=den=0
    for g,s in d.groupby(strat):
        x=s[f].values.astype(float);y=s.turn.values
        m=~np.isnan(x);x=x[m];y=y[m]
        n1=y.sum();n0=len(y)-n1
        if n1<3 or n0<3: continue
        a=auc(x,y); num+=a*n1*n0; den+=n1*n0
    return num/den if den else np.nan
rng=np.random.default_rng(1)
days=E.day.unique()
def boot(d,f,fn,B=200):
    r=[]
    for _ in range(B):
        ch=rng.choice(days,len(days)); s=pd.concat([d[d.day==c] for c in ch]); r.append(fn(s,f))
    return np.nanstd(r)
lines=[]
res=[]
for sign,nm in((1,"TOPO"),(-1,"FUNDO")):
  for X in (150,250,375,500):
    d=E[(E.sign==sign)&(E.X==X)]
    print(nm,X,"n",len(d),"turn",d.turn.sum(),f"{d.turn.mean():.3f}", "por hora:",d.groupby("hg").turn.agg(["size","mean"]).round(2).to_dict("index"),flush=True)
    for f in FE:
        if d[f].notna().sum()<50: continue
        a=auc(d[f].values.astype(float),d.turn.values); sa=saucs(d,f)
        res.append((nm,X,f,len(d),int(d.turn.sum()),a,sa))
R=pd.DataFrame(res,columns=["dir","X","feat","n","nturn","auc","auc_hora"])
R.to_pickle("auc.pkl")
for X in (250,500):
    p=R[R.X==X].pivot(index="feat",columns="dir",values=["auc","auc_hora"]).round(3)
    p["max"]=(p["auc_hora"]-.5).abs().max(axis=1); print("X",X);print(p.sort_values("max",ascending=False).head(18))
