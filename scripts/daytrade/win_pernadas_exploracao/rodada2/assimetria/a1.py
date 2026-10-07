from base import *
import pickle
res=pickle.load(open("legs.pkl","rb"))
rng=np.random.default_rng(1)
def enrich(x):
    x=x.copy(); x["size"]=(x.p1-x.p0).abs()
    x["dur"]=(x.t1-x.t0).dt.total_seconds()/60+1
    x["spd"]=x["size"]/x.dur
    adv=[];vol=[]
    for _,l in x.iterrows():
        m=win[(win.index>=l.t0)&(win.index<=l.t1)]
        if len(m)==0: adv.append(np.nan);vol.append(np.nan);continue
        if l.dir==1: a=(m.high.cummax()-m.low).max()  # approx max drawdown from running high
        else: a=(m.high-m.low.cummin()).max()
        # proper max adverse retracement
        c=m.close.values; 
        if l.dir==1: a=(np.maximum.accumulate(c)-c).max()
        else: a=(c-np.minimum.accumulate(c)).max()
        adv.append(a); vol.append(m.vol.sum()/len(m))
    x["adv"]=adv;x["adv_rel"]=x.adv/x["size"];x["vpm"]=vol
    x["h"]=x.t0.dt.hour+x.t0.dt.minute/60
    x["blk"]=pd.cut(x.h,[0,10.5,12,24],labels=["<10:30","10:30-12",">12"],right=False)
    return x
def bootdiff(x,col,n=2000):
    days_=x.d.unique(); 
    def f(sub): 
        a=sub[sub.dir==1][col].median(); b=sub[sub.dir==-1][col].median(); return a-b
    obs=f(x); bs=[]
    g={d:x[x.d==d] for d in days_}
    for _ in range(n):
        pick=rng.choice(len(days_),len(days_)); s=pd.concat([g[days_[i]] for i in pick]); bs.append(f(s))
    return obs,np.nanpercentile(bs,[5,95])
out=[]
for tf in ["M5","M15","H1"]:
    x=enrich(res[tf]); x=x[x.closed&(x.k>0)]
    print("\n==",tf,"n",len(x),"alta",(x.dir==1).sum(),"baixa",(x.dir==-1).sum())
    for col in ["size","dur","spd","adv","adv_rel","vpm"]:
        up=x[x.dir==1][col];dn=x[x.dir==-1][col]
        o,ci=bootdiff(x,col)
        print(f"{col:8s} alta med {up.median():9.1f} (q25 {up.quantile(.25):.1f} q75 {up.quantile(.75):.1f})  baixa med {dn.median():9.1f} (q25 {dn.quantile(.25):.1f} q75 {dn.quantile(.75):.1f})  dif {o:.1f} IC90 dia-boot [{ci[0]:.1f},{ci[1]:.1f}]")
    # by block
    for b in ["<10:30","10:30-12",">12"]:
        s=x[x.blk==b]
        print(" blk",b,"n alta",(s.dir==1).sum(),"baixa",(s.dir==-1).sum(),"size med",s[s.dir==1]["size"].median(),s[s.dir==-1]["size"].median(),"spd",round(s[s.dir==1].spd.median(),1),round(s[s.dir==-1].spd.median(),1),"adv_rel",round(s[s.dir==1].adv_rel.median(),3),round(s[s.dir==-1].adv_rel.median(),3))
    # cumulative: sum of points up vs down, per day
    pd_=x.groupby(["d","dir"])["size"].sum().unstack().fillna(0)
    print(" pontos/dia alta",pd_[1].median(),"baixa",pd_[-1].median(), " dias com mais pts de baixa:",(pd_[-1]>pd_[1]).sum(),"/",len(pd_))
    # fraction of time in up legs / avg dur
    # speed: down faster?
    pairs=x.groupby("d").apply(lambda g: pd.Series({"su":g[g.dir==1].spd.median(),"sd":g[g.dir==-1].spd.median()})).dropna()
    print(" por dia: baixa mais rapida em",(pairs.sd>pairs.su).sum(),"de",len(pairs))
    if tf=="M15": x.to_pickle("m15_enr.pkl")
    if tf=="H1": x.to_pickle("h1_enr.pkl")
    if tf=="M5": x.to_pickle("m5_enr.pkl")
