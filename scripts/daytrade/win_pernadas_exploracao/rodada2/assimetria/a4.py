from base import *
rows=[]
for d in days:
    w=win[win.d==d].copy(); tp=(w.high+w.low+w.close)/3
    w["vwap"]=(tp*w.vol).cumsum()/w.vol.cumsum(); o=w.open.iloc[0]
    for hh in np.arange(9.5,16.01,0.25):
        t=pd.Timestamp(f"{d} {int(hh):02d}:{int(round((hh%1)*60)):02d}:00")
        a=w[w.index<t]; 
        if len(a)<5: continue
        px=a.close.iloc[-1]
        for H in [30,60]:
            b=w[(w.index>=t)&(w.index<t+pd.Timedelta(minutes=H))]
            if len(b)<H-3: continue
            rows.append(dict(d=d,h=hh,H=H,dv=px-a.vwap.iloc[-1],do=px-o,dp=px-prevclose[d],fwd=b.close.iloc[-1]-px))
G=pd.DataFrame(rows); G["blk"]=pd.cut(G.h,[0,10.5,12.5,24],labels=["<10:30","10:30-12:30",">12:30"],right=False)
for H in [30,60]:
    g=G[G.H==H]
    for nm in ["dv","do","dp"]:
        for thr in [0,500]:
            s=g[g[nm].abs()>thr]
            contra=(np.sign(s[nm])!=np.sign(s.fwd))
            pb={b:f"{contra[s.blk==b].mean():.0%} (n{(s.blk==b).sum()})" for b in ["<10:30","10:30-12:30",">12:30"]}
            # media da reversao em pontos
            rev=(-np.sign(s[nm])*s.fwd)
            # por dia: media de contra por dia -> dias com >50%
            pdv=contra.groupby(s.d).mean()
            print(f"H{H} {nm} |x|>{thr}: n={len(s)} contra {contra.mean():.1%} | pts rev mediana {rev.median():.0f} media {rev.mean():.0f} | dias com maioria contra {(pdv>0.5).sum()}/{len(pdv)} | {pb}")
G.to_pickle("grid.pkl")
