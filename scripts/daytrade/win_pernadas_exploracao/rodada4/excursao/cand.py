import pickle, numpy as np, pandas as pd, exc, agg
vthr, _ = pickle.load(open("real_agg.pkl","rb"))
real = pickle.load(open("real_meses.pkl","rb"))
NG=exc.NG
WIN={"desc":(1,6),"conf":(7,8),"set":(9,9)}
def win(w):
    m0,m1=WIN[w]
    df=pd.concat([real[m][0] for m in range(m0,m1+1)],ignore_index=True); R=np.concatenate([real[m][1] for m in range(m0,m1+1)])
    return agg.feats(df,vthr),R
W={w:win(w) for w in WIN}
def mask(d,cell):
    m=np.ones(len(d),bool)
    for kv in cell.split("|"):
        k,v=kv.split("="); m&=(d[k].values==int(v))
    return m
def col(fill,side,g): return fill*2*NG+side*NG+g
def stats(w,cell,side,g,fill=0,B=2000,seed=1):
    d,R=W[w]; m=mask(d,cell); x=R[m,col(fill,side,g)]; days=d.date.values[m]
    ok=~np.isnan(x); xs=x[ok]; dy=days[ok]
    if len(xs)<20: return dict(nf=len(xs),exp=np.nan,lo=np.nan,hi=np.nan,win=np.nan,be=np.nan,ndays=0,fr=np.nan)
    u,inv=np.unique(dy,return_inverse=True)
    S=np.bincount(inv,xs); N=np.bincount(inv)
    rng=np.random.default_rng(seed); idx=rng.integers(0,len(u),(B,len(u)))
    bs=S[idx].sum(1)/N[idx].sum(1)
    pos=xs[xs>0]; neg=xs[xs<=0]
    gm=pos.mean() if len(pos) else 0; lm=-neg.mean() if len(neg) else 0
    return dict(nf=len(xs),exp=xs.mean(),lo=np.quantile(bs,.025),hi=np.quantile(bs,.975),win=(xs>0).mean(),be=lm/(gm+lm) if gm+lm else np.nan,ndays=len(u),fr=ok.mean())
def gname(g):
    t=exc.GEOMS[g]; return f"{t[1]}/{t[2]} pts" if t[0]=="p" else f"{t[1]}A/{t[2]}A"
def neighbors(g):
    t=exc.GEOMS[g]; fam=[i for i,u in enumerate(exc.GEOMS) if u[0]==t[0]]
    Ts=sorted({exc.GEOMS[i][1] for i in fam}); Ss=sorted({exc.GEOMS[i][2] for i in fam})
    out=[]
    for dt in (-1,0,1):
        for ds in (-1,0,1):
            if dt==ds==0: continue
            ti=Ts.index(t[1])+dt; si=Ss.index(t[2])+ds
            if 0<=ti<len(Ts) and 0<=si<len(Ss):
                out.append([i for i in fam if exc.GEOMS[i][1]==Ts[ti] and exc.GEOMS[i][2]==Ss[si]][0])
    return out
def rneighbors(cell):
    parts=dict(kv.split("=") for kv in cell.split("|"))
    if "lv" not in parts: return []
    out=[]
    for dl in (-1,1):
        l=int(parts["lv"])+dl
        if 0<=l<7:
            p=dict(parts); p["lv"]=str(l); out.append("|".join(f"{k}={v}" for k,v in p.items()))
    return out
if __name__=="__main__":
    K=["spec","cell","fill","side","geom"]
    d=pd.read_pickle("tab_desc.pkl")
    x=d[(d.fill==0)&(d.nf>=150)&(d.exp>0)&(d.z>=2)].sort_values("z",ascending=False)
    print("candidatos (regra desc: exp>0, z>=2, nf>=150):",len(x))
    rows=[]
    for _,r in x.iterrows():
        sd=stats("desc",r.cell,int(r.side),int(r.geom))
        ng=[stats("desc",r.cell,int(r.side),g)["exp"] for g in neighbors(int(r.geom))]
        nr=[stats("desc",c2,int(r.side),int(r.geom))["exp"] for c2 in rneighbors(r.cell)]
        pl_g=np.mean([v>0 for v in ng]); pl_r=np.mean([v>0 for v in nr]) if nr else np.nan
        rows.append((r.spec,r.cell,int(r.side),gname(int(r.geom)),sd["nf"],sd["ndays"],round(sd["fr"],2),round(sd["exp"],1),round(sd["lo"],1),round(sd["hi"],1),round(r["mean"],1),round(r.z,2),round(sd["win"],3),round(sd["be"],3),round(pl_g,2),round(pl_r,2) if nr else np.nan))
    t=pd.DataFrame(rows,columns="spec cell side geom nf dias fill% exp lo95 hi95 nulo z win be plato_geom plato_r".split())
    pd.set_option("display.width",250); print(t.to_string()); t.to_csv("candidatos_desc.csv",index=False)
    # confirmacao e set
    rows=[]
    for _,r in x.iterrows():
        for w in ("conf","set"):
            sd=stats(w,r.cell,int(r.side),int(r.geom))
            rows.append((r.spec,r.cell,int(r.side),gname(int(r.geom)),w,sd["nf"],sd["ndays"],round(sd["exp"],1),round(sd["lo"],1),round(sd["hi"],1),round(sd["win"],3),round(sd["be"],3)))
    t2=pd.DataFrame(rows,columns="spec cell side geom janela nf dias exp lo95 hi95 win be".split()); print(t2.to_string()); t2.to_csv("candidatos_conf.csv",index=False)
