from base import *
import math
# per-day features at T in 10:00,10:30,11:00 ; target: sign of (close_final - price at T), and of day dir
def binom_p(k,n):  # two-sided vs 0.5
    from math import comb
    pr=[comb(n,i)/2**n for i in range(n+1)]; return sum(p for p in pr if p<=pr[k]+1e-12)
rows=[]
for d in days:
    w=win[win.d==d]; o=w.open.iloc[0]; pc=prevclose[d]; fin=w.close.iloc[-1]
    wd=wdo[wdo.d==d]
    for T in ["10:00","10:30","11:00"]:
        t=pd.Timestamp(f"{d} {T}:00")
        a=w[w.index<t]; 
        if len(a)==0: continue
        px=a.close.iloc[-1]
        tp=(a.close*a.vol).sum()/a.vol.sum()  # vwap approx (close-weighted)
        wa=wd[wd.index<t]
        wdo_ret=wa.close.iloc[-1]-wa.open.iloc[0] if len(wa)>5 else np.nan
        # day rng so far
        rows.append(dict(d=d,T=T,gap=o-pc,ret_open=px-o,vs_pc=px-pc,vs_vwap=px-tp,wdo=wdo_ret,
          first30=a[a.index<pd.Timestamp(f"{d} 09:30:00")].close.iloc[-1]-o,
          orn=a.high.max()-a.low.min(),
          pos=(px-a.low.min())/(a.high.max()-a.low.min()+1e-9),
          rem=fin-px, daydir=fin-o, rng_day=w.high.max()-w.low.min(), fin_vs_o=fin-o,
          rem_abs_rng=(w[w.index>=t].high.max()-w[w.index>=t].low.min())))
F=pd.DataFrame(rows); F.to_pickle("feat.pkl")
print("n dias",F.d.nunique(),"comparacoes: feature x T")
feats=["gap","ret_open","vs_pc","vs_vwap","wdo","first30"]
for T in ["10:00","10:30","11:00"]:
    f=F[F["T"]==T]
    print("\n== T",T)
    # classify whole day: trend up/down/lateral: |fin-o|/rng_day
    for ft in feats:
        s=f.dropna(subset=[ft]); s=s[s[ft]!=0]
        k=((np.sign(s[ft])==np.sign(s.rem))).sum(); n=len(s)
        k2=((np.sign(s[ft])==np.sign(s.daydir))).sum()
        rho=pd.Series(s[ft].values).rank().corr(pd.Series(s.rem.values).rank())
        print(f"{ft:9s} n={n} mesmo sinal que restante-do-dia {k}/{n} (p={binom_p(k,n):.2f}) | que dia todo {k2}/{n} | rho {rho:.2f}")
    # remaining-move size when feature agrees
# day character
F2=F[F["T"]=="10:30"].copy()
F2["eff"]=F2.daydir.abs()/F2.rng_day
print("\neficiencia do dia (|fecha-abre|/range): mediana",F2.eff.median(),"quartis",F2.eff.quantile([.25,.75]).tolist())
print("dias tendencia (eff>=0.5):",(F2.eff>=.5).sum(),"alta",((F2.eff>=.5)&(F2.daydir>0)).sum(),"baixa",((F2.eff>=.5)&(F2.daydir<0)).sum(),"lateral (<0.25)",(F2.eff<.25).sum())
print(F2[["d","gap","ret_open","vs_vwap","wdo","daydir","rng_day","eff","rem"]].round(0).to_string())
# a regime score: consensus of sign of ret_open, vs_vwap, vs_pc at T; relation to remaining move
for T in ["10:00","10:30","11:00"]:
    f=F[F["T"]==T].copy()
    f["score"]=np.sign(f.ret_open)+np.sign(f.vs_vwap)+np.sign(f.vs_pc)
    f["agree"]=f.score.abs()==3
    g=f[f.agree]; k=(np.sign(g.score)==np.sign(g.rem)).sum()
    print(T,"consenso 3/3 n",len(g),"restante na direcao",k,"med rem a favor",np.median(np.sign(g.score)*g.rem) if len(g) else None, "| nao consenso n",(~f.agree).sum(),"med rem |.|",f[~f.agree].rem.abs().median(),"consenso |rem|",g.rem.abs().median() if len(g) else None)
