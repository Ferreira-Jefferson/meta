import numpy as np, pandas as pd, itertools, sys
FAM=sys.argv[1]
rng=np.random.default_rng(1)
ev=pd.read_csv("eventos.csv",parse_dates=["dia","ts_vela"]); f=pd.read_csv("features_m1.csv",index_col=0,parse_dates=True)
ev=ev[(ev.y.notna())&(ev.familia==FAM)].copy(); ev["leg_ate_E"]=ev.leg_ate_E.fillna(0); ev["r"]=np.where(ev.tf=="M5",ev.r_m5,ev.r_m15); ev["rh"]=np.where(ev.tf=="M5",ev.rh_m5,ev.rh_m15)
ev=ev.dropna(subset=["r","rh","hora","leg_ate_E"])
NCOMP=0
def wil(k,n):
    if n==0: return (np.nan,np.nan)
    p=k/n; z=1.96; d=1+z*z/n; c=(p+z*z/2/n)/d; h=z*np.sqrt(p*(1-p)/n+z*z/4/n/n)/d; return c-h,c+h
def boot_rate(d,B=1000):
    dias=d.dia.unique(); g={x:v.y.values for x,v in d.groupby("dia")}
    r=[]
    for _ in range(B):
        s=np.concatenate([g[x] for x in rng.choice(dias,len(dias))]); r.append(s.mean())
    return np.percentile(r,[2.5,97.5])
def auc(y,s):
    y=np.asarray(y);s=pd.Series(s).rank().values;n1=y.sum();n0=len(y)-n1
    return (s[y==1].sum()-n1*(n1+1)/2)/(n1*n0)
def logit_fit(X,y,l2=1.0,it=30):
    X1=np.c_[np.ones(len(X)),X]; b=np.zeros(X1.shape[1]); P=np.eye(len(b))*l2; P[0,0]=0
    for _ in range(it):
        p=1/(1+np.exp(-X1@b)); W=p*(1-p)+1e-9
        b=b+np.linalg.solve(X1.T@(X1*W[:,None])+P,X1.T@(y-p)-P@b)
    return b
def lodo(d,cols):
    X=d[cols].values.astype(float); y=d.y.values; out=np.zeros(len(d))
    for dia in d.dia.unique():
        te=(d.dia==dia).values; mu,sd=X[~te].mean(0),X[~te].std(0)+1e-9
        b=logit_fit((X[~te]-mu)/sd,y[~te]); out[te]=1/(1+np.exp(-(np.c_[np.ones(te.sum()),(X[te]-mu)/sd]@b)))
    ll=-np.mean(y*np.log(out)+(1-y)*np.log(1-out)); return auc(y,out),ll
ev["logleg"]=np.log(ev.leg_ate_E.clip(lower=50)); ev["logr"]=np.log(ev.r.clip(lower=.1)); ev["logrh"]=np.log(ev.rh.clip(lower=.1))
LEGB,LEGL,LEGT=(([0,1000,1500,2500,1e9],["<1000","1000-1500","1500-2500",">=2500"],1500) if FAM=="extremo" else ([0,300,750,1500,1e9],["<300","300-750","750-1500",">=1500"],750))
ev["h_bin"]=pd.cut(ev.hora,[0,10,11,13,24],right=False,labels=["<10","10-11","11-13",">=13"])
ev["r_bin"]=pd.cut(ev.r,[0,.9,1.2,99],right=False,labels=["<0.9","0.9-1.2",">=1.2"])
ev["l_bin"]=pd.cut(ev.leg_ate_E,LEGB,right=False,labels=LEGL)
ev["early"]=ev.hora<11; ev["volhi"]=ev.r>=1.2; ev["legbig"]=ev.leg_ate_E>=LEGT; ev["rhhi"]=ev.rh>=1.2
ev["rh_bin"]=pd.cut(ev.rh,[0,.9,1.2,99],right=False,labels=["<0.9","0.9-1.2",">=1.2"])
def tab(d,col):
    g=d.groupby(col,observed=True).y.agg(["size","sum"]); g["taxa"]=g["sum"]/g["size"]; return g
out=[]
def P(s=""): print(s); out.append(s)
P("## A. TAXA-BASE  P(750 | recuou X do extremo)  [IC95 bootstrap por dia]")
P("TF | X | n | chegaram | taxa | IC95"); 
for tf in("M5","M15"):
    for X in(150,250,375,500):
        d=ev[(ev.tf==tf)&(ev.X==X)]; lo,hi=boot_rate(d); P(f"{tf} | {X} | {len(d)} | {int(d.y.sum())} | {d.y.mean():.1%} | {lo:.1%}-{hi:.1%}")
res={}
for tf in("M5","M15"):
  for X in(250,375):
    d=ev[(ev.tf==tf)&(ev.X==X)].reset_index(drop=True)
    P(f"\n## B. {tf} X={X}  n={len(d)} sucessos={int(d.y.sum())} dias={d.dia.nunique()}")
    P("Spearman entre sinais: hora~r %.2f | hora~leg %.2f | r~leg %.2f"%(d.hora.rank().corr(d.r.rank()),d.hora.rank().corr(d.leg_ate_E.rank()),d.r.rank().corr(d.leg_ate_E.rank())))
    for c in("h_bin","r_bin","rh_bin","l_bin"):
        t=tab(d,c); P(f"{c}: "+" ; ".join(f"{i}: {r['taxa']:.0%} (n={int(r['size'])})" for i,r in t.iterrows())); NCOMP+=len(t)
    # 2x2x2
    for VOL,vn in(("volhi","r bruto>=1.2"),("rhhi","rh (sem relogio)>=1.2")):
        P(f"Celulas hora<11 / {vn} / leg>={LEGT} : taxa (n)")
        cell={}
        for a,b,c in itertools.product([True,False],[True,False],[True,False]):
            s=d[(d.early==a)&(d[VOL]==b)&(d.legbig==c)]; cell[(a,b,c)]=(s.y.sum(),len(s))
            P(f"  early={int(a)} vol={int(b)} legbig={int(c)} : {s.y.mean() if len(s) else np.nan:.0%} (n={len(s)})")
        # efeito de cada sinal dentro dos estratos dos outros dois (diferenca ponderada)
        for nome,ix in(("hora<11",0),(vn,1),(f"leg>={LEGT}",2)):
            num=den=0;ws=0;dif=0
            for o in itertools.product([True,False],repeat=2):
                k1=[None]*3;k0=[None]*3; j=0
                for i in range(3):
                    if i==ix: k1[i]=True;k0[i]=False
                    else: k1[i]=k0[i]=o[j]; j+=1
                (y1,n1),(y0,n0)=cell[tuple(k1)],cell[tuple(k0)]
                if n1>=5 and n0>=5: w=n1*n0/(n1+n0); dif+=w*(y1/n1-y0/n0); ws+=w
            marg=d[d[["early",VOL,"legbig"][ix]]].y.mean()-d[~d[["early",VOL,"legbig"][ix]]].y.mean()
            P(f"  efeito {nome}: marginal {marg:+.0%} -> dentro dos estratos dos outros dois {(dif/ws if ws else float('nan')):+.0%}"); NCOMP+=1
    P("Logistica leave-one-day-out (AUC, logloss; base logloss %.3f):"%(-np.mean(d.y*np.log(d.y.mean())+(1-d.y)*np.log(1-d.y.mean()))))
    for nome,cols in(("hora",["hora"]),("vol(r)",["logr"]),("rh",["logrh"]),("leg",["logleg"]),("hora+vol",["hora","logr"]),("hora+rh",["hora","logrh"]),("hora+leg",["hora","logleg"]),("vol+leg",["logr","logleg"]),("rh+leg",["logrh","logleg"]),("hora+vol+leg",["hora","logr","logleg"]),("hora+rh+leg",["hora","logrh","logleg"]),("hora+vol+rh+leg",["hora","logr","logrh","logleg"])):
          a,l=lodo(d,cols); P(f"  {nome:14s} AUC {a:.3f}  logloss {l:.3f}"); NCOMP+=1
    C4=["hora","logr","logrh","logleg"]
    b=logit_fit(((d[C4]-d[C4].mean())/d[C4].std()).values,d.y.values)
    P("  coef padronizados (hora, log r, log rh, log leg): %s"%np.round(b[1:],2))
# ---------- C. chave
P("\n## C. CHAVE (X=250). tempo ligado = fracao dos minutos de pregao; captura = fracao dos eventos que viram pernada com chave ON")
fm=f.dropna(subset=["r_m5","r_m15","rh_m5","rh_m15"])
for tf in("M5","M15"):
    d=ev[(ev.tf==tf)&(ev.X==250)]; rc="r_"+tf.lower(); tot=d.y.sum()
    P(f"\n### {tf}: eventos={len(d)} pernadas={int(tot)} taxa-base={d.y.mean():.1%}")
    def row(nome,on_m,on_e):
        te=on_m.mean(); cap=d.y[on_e].sum()/tot; pon=d.y[on_e].mean() if on_e.sum() else np.nan; pof=d.y[~on_e].mean() if (~on_e).sum() else np.nan
        P(f"| {nome} | {te:.0%} | {cap:.0%} | {cap/te:.2f} | {pon:.0%} (n={on_e.sum()}) | {pof:.0%} (n={(~on_e).sum()}) |")
        return te,cap
    P("| chave | tempo ligado | pernadas capturadas | lift (captura/tempo) | P(pernada) ON | P(pernada) OFF |"); P("|---|---|---|---|---|---|")
    for H in(9.5,10,10.5,11,12,13,14,15):
        row(f"hora<{H}",fm.hora<H,d.hora<H); NCOMP+=1
    for R in(.8,1.0,1.2,1.4,1.6,2.0):
        row(f"r>={R}",fm[rc]>=R,d.r>=R); NCOMP+=1
    for R in(.9,1.0,1.1,1.2,1.4,1.6):
        row(f"rh>={R} (sem relogio)",fm["rh_"+tf.lower()]>=R,d.rh>=R); NCOMP+=1
    P("OR (hora<H ou r>=R) -- grade completa; fronteira = maior captura para cada tempo ligado")
    pts=[]
    for H in(9.5,10,10.5,11,12,13):
        for R in(1.0,1.2,1.4,1.6,2.0,3.0):
            te,cap=row(f"OR hora<{H} | r>={R}",(fm.hora<H)|(fm[rc]>=R),(d.hora<H)|(d.r>=R)); pts.append((te,cap,H,R,"OR")); NCOMP+=1
    for H in(9.5,10,10.5,11,12,13):
        for R in(1.0,1.2,1.4):
            row(f"OR hora<{H} | rh>={R}",(fm.hora<H)|(fm["rh_"+tf.lower()]>=R),(d.hora<H)|(d.rh>=R)); NCOMP+=1
    for H in(11,13,15):
        for R in(1.0,1.2,1.4):
            te,cap=row(f"AND hora<{H} & r>={R}",(fm.hora<H)&(fm[rc]>=R),(d.hora<H)&(d.r>=R)); NCOMP+=1
P(f"\nNCOMP (celulas/modelos/chaves avaliados, sem contar bootstrap): {NCOMP}")
open("saida_analise_%s.txt"%FAM,"w",encoding="utf-8").write("\n".join(out))
