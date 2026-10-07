from base import *
import pickle
def rk(s): return pd.Series(np.asarray(s)).rank()
def sp(a,b): return rk(a).corr(rk(b))
def binom_p(k,n):
    from math import comb
    pr=[comb(n,i)/2**n for i in range(n+1)]; return sum(p for p in pr if p<=pr[k]+1e-12)
F=pd.read_pickle("feat.pkl")
# 1) WDO vs WIN morning
f=F[F["T"]=="10:30"].dropna(subset=["wdo"])
print("corr rank WDO ret vs WIN ret_open (09:00-10:30):",round(sp(f.wdo,f.ret_open),2),"n",len(f))
# 2) morning efficiency vs rest of day
f=F[F["T"]=="10:30"].copy()
f["eff_m"]=f.ret_open.abs()/f.orn
f["eff_d"]=f.daydir.abs()/f.rng_day
f["eff_rest"]=f.rem.abs()/f.rem_abs_rng
print("rho eff manha vs eff dia",round(sp(f.eff_m,f.eff_d),2),"vs eff resto",round(sp(f.eff_m,f.eff_rest),2))
print("rho |ret_open| vs |rem|",round(sp(f.ret_open.abs(),f.rem.abs()),2),"; rho orn vs rem_abs_rng",round(sp(f.orn,f.rem_abs_rng),2))
# reversal size: rem * -sign(ret_open)
f["rev"]=-np.sign(f.ret_open)*f.rem
print("restante contra a manha: mediana",f.rev.median(),"q25/q75",f.rev.quantile([.25,.75]).tolist(),"dias contra",(f.rev>0).sum(),"/21; |ret_open| mediana",f.ret_open.abs().median())
print("corr rank ret_open vs rem",round(sp(f.ret_open,f.rem),2), "slope", round(np.polyfit(f.ret_open,f.rem,1)[0],2))
# devolucao do move da manha ate o fechamento: rem/ret_open
f["frac"]=f.rem/f.ret_open
big=f[f.ret_open.abs()>=f.ret_open.abs().median()]
print("manha grande (>=mediana) n",len(big),"contra",(big.rev>0).sum(),"rem/ret mediana",big.frac.median(), "| manha pequena n",len(f)-len(big),"contra",(f.loc[~f.index.isin(big.index)].rev>0).sum())
# 3) leg-level: direction vs running VWAP and vs open, causal
res=pickle.load(open("legs.pkl","rb"))
cum={}
for d in days:
    w=win[win.d==d].copy(); tp=(w.high+w.low+w.close)/3
    w["vwap"]=(tp*w.vol).cumsum()/w.vol.cumsum(); cum[d]=w
def state(l):
    w=cum[l.d]; a=w[w.index<=l.t0]
    px=l.p0
    if len(a)==0: a=w.iloc[:1]
    return px-a.vwap.iloc[-1], px-w.open.iloc[0], px-prevclose[l.d]
H1=res["H1"]
# H1 confirm time
def confirm(l):
    w=win[(win.index>l.t1)&(win.d==l.d)]
    if l.dir==1: hit=w[w.low<=l.p1-750]
    else: hit=w[w.high>=l.p1+750]
    return hit.index[0] if len(hit) else pd.NaT
H1=H1.copy(); H1["conf"]=[confirm(l) for _,l in H1.iterrows()]
print("\n-- por perna (n por TF; pernas dependentes dentro do dia; IC por dia nao feito)")
out={}
for tf in ["M5","M15"]:
    x=res[tf].copy(); x=x[x.k>0]
    st=[state(l) for _,l in x.iterrows()]
    x["dv"],x["do"],x["dp"]=zip(*st)
    x["size"]=(x.p1-x.p0).abs(); x["dur"]=(x.t1-x.t0).dt.total_seconds()/60+1
    x["h"]=x.t0.dt.hour+x.t0.dt.minute/60
    x["blk"]=pd.cut(x.h,[0,10.5,12,24],labels=["<10:30","10:30-12",">12"],right=False)
    # perna na direcao do VWAP (reversao ao vwap) = sign(-dv)==dir
    for nm in ["dv","do","dp"]:
        x["tow_"+nm]=(np.sign(-x[nm])==x.dir)
        s=x[x[nm]!=0]
        k=s["tow_"+nm].sum(); n=len(s)
        print(f"{tf} perna parte de preco acima/abaixo ({nm}) e vai em direcao a ele: {k}/{n} = {k/n:.0%}", " por bloco:",{b:f"{int(s[s.blk==b]['tow_'+nm].sum())}/{(s.blk==b).sum()}" for b in ["<10:30","10:30-12",">12"]})
    # |dv| tercil: size toward vs away
    x["dvabs"]=x.dv.abs(); x["tert"]=pd.qcut(x.dvabs,3,labels=["perto","meio","longe"])
    print(x.groupby(["tert","tow_dv"])["size"].agg(["count","median"]).unstack().round(0).to_string())
    # H1 context
    ctx=[]
    for _,l in x.iterrows():
        h=H1[(H1.d==l.d)&(H1.conf<=l.t0)]
        ctx.append(h.dir.iloc[-1] if len(h) else 0)
    x["h1"]=ctx
    s=x[x.h1!=0]; s=s.assign(fav=(s.dir==s.h1))
    print(f"{tf} perna a favor da perna H1 confirmada: {s.fav.sum()}/{len(s)} ; size med fav {s[s.fav]['size'].median()} contra {s[~s.fav]['size'].median()} ; dur fav {s[s.fav].dur.median()} contra {s[~s.fav].dur.median()}")
    for b in ["<10:30","10:30-12",">12"]:
        t=s[s.blk==b]
        print(f"   {b}: fav {t.fav.sum()}/{len(t)} size fav {t[t.fav]['size'].median()} contra {t[~t.fav]['size'].median()}")
    out[tf]=x
pickle.dump(out,open("legs_ctx.pkl","wb"))
