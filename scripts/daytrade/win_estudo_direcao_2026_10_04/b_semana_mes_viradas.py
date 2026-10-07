# Estudo descritivo WIN: semana, mes, alinhamento, viradas. Sem backtest de robo.
import numpy as np, pandas as pd, math, os
D = os.path.dirname(os.path.abspath(__file__))
F = r'C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5\WIN@D_M1_202110010900_202610011717.csv'
m1 = pd.read_csv(F, sep='\t'); m1.columns = ['date','time','o','h','l','c','tv','v','sp']
m1['date'] = pd.to_datetime(m1['date'], format='%Y.%m.%d')
g = m1.groupby('date')
d = pd.DataFrame({'o':g.o.first(),'h':g.h.max(),'l':g.l.min(),'c':g.c.last(),'v':g.v.sum(),'n':g.size(),'t1':g.time.last()})
d = d[(d.n>=300)&(d.t1>='17:50:00')]   # descarta dia parcial final (2026-10-01 so ate 17:17)
d['up'] = (d.c>d.o).astype(int); d['ret'] = d.c-d.o
pc = d.c.shift(); d['tr'] = np.maximum(d.h-d.l, np.maximum((d.h-pc).abs(),(d.l-pc).abs()))
d['atr'] = d.tr.rolling(14).mean().shift(1)     # ATR14 conhecido antes de D
d['win'] = np.where(d.index<='2024-12-31','IS','OOS')
iso = d.index.isocalendar(); d['wk'] = iso.year.astype(str)+'-'+iso.week.astype(str).str.zfill(2); d['mo']=d.index.to_period('M').astype(str)
d['dow'] = d.index.dayofweek
def wilson(k,n):
    if n==0: return (np.nan,np.nan)
    p=k/n; z=1.96; den=1+z*z/n; c=(p+z*z/(2*n))/den; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (c-h,c+h)
def pz(k,n,p0):
    if n==0: return np.nan
    z=(k/n-p0)/math.sqrt(p0*(1-p0)/n); return math.erfc(abs(z)/math.sqrt(2))
base = {w:d[d.win==w].up.mean() for w in ['IS','OOS']}
rows=[]; ntests={'IS':0,'OOS':0}; nsig={'IS':0,'OOS':0}
def rate(achado, w, mask, y, retx=None, atr=None):
    mask = mask & (d.win==w)
    k=int(y[mask].sum()); n=int(mask.sum()); lo,hi=wilson(k,n); p0=base[w]
    p=pz(k,n,p0) if n>5 else np.nan
    ntests[w]+=1; nsig[w]+= int(p<0.05) if p==p else 0
    rows.append(dict(achado=achado,janela=w,n=n,taxa=k/n if n else np.nan,ic_lo=lo,ic_hi=hi,nulo=p0,p=p,
        ret_pts=retx[mask].mean() if n else np.nan,
        ret_atr=(retx[mask]/atr[mask]).mean() if n else np.nan))
# ---------- SEMANAS ----------
W = d.groupby('wk').agg(o=('o','first'),c=('c','last'),h=('h','max'),l=('l','min'),d0=('o',lambda s:s.index[0]),nd=('o','size'))
W['up']=(W.c>W.o).astype(int); W['win']=np.where(W.d0<='2024-12-31','IS','OOS')
W['prev_up']=W.up.shift()
wbase={w:W[W.win==w].up.mean() for w in ['IS','OOS']}
wk_rows=[]
for w in ['IS','OOS']:
    s=W[W.win==w].dropna(subset=['prev_up'])
    for pv in [1,0]:
        sub=s[s.prev_up==pv]; k=int(sub.up.sum()); n=len(sub); lo,hi=wilson(k,n)
        wk_rows.append(dict(achado='sem W alta | sem W-1 '+('alta' if pv else 'baixa'),janela=w,n=n,taxa=k/n,ic_lo=lo,ic_hi=hi,nulo=wbase[w],p=pz(k,n,wbase[w])))
d = d.join(W[['prev_up']].rename(columns={'prev_up':'wk_prev_up'}), on='wk')
d['is_first_of_week'] = d.wk!=d.wk.shift()
for w in ['IS','OOS']:
    for pv in [1,0]:
        lab='alta' if pv else 'baixa'
        rate('dia D alta | sem W-1 '+lab+' (todos dias)',w,(d.wk_prev_up==pv),d.up,d.ret,d.atr)
        rate('1o dia da semana alta | sem W-1 '+lab,w,(d.wk_prev_up==pv)&d.is_first_of_week,d.up,d.ret,d.atr)
dn=['seg','ter','qua','qui','sex']
for w in ['IS','OOS']:
    for k in range(5):
        rate('taxa alta '+dn[k],w,(d.dow==k),d.up,d.ret,d.atr)
        for pv in [1,0]:
            rate('taxa alta '+dn[k]+' | sem W-1 '+('alta' if pv else 'baixa'),w,(d.dow==k)&(d.wk_prev_up==pv),d.up,d.ret,d.atr)
# ---------- MESES ----------
M = d.groupby('mo').agg(o=('o','first'),c=('c','last'),d0=('o',lambda s:s.index[0]))
M['up']=(M.c>M.o).astype(int); M['prev_up']=M.up.shift(); M['win']=np.where(M.d0<='2024-12-31','IS','OOS')
mbase={w:M[M.win==w].up.mean() for w in ['IS','OOS']}
mo_rows=[]
for w in ['IS','OOS']:
    s=M[M.win==w].dropna(subset=['prev_up'])
    for pv in [1,0]:
        sub=s[s.prev_up==pv]; k=int(sub.up.sum()); n=len(sub); lo,hi=wilson(k,n)
        mo_rows.append(dict(achado='mes M alta | mes M-1 '+('alta' if pv else 'baixa'),janela=w,n=n,taxa=k/n,ic_lo=lo,ic_hi=hi,nulo=mbase[w],p=pz(k,n,mbase[w])))
d = d.join(M[['prev_up']].rename(columns={'prev_up':'mo_prev_up'}), on='mo')
Wm=W.copy(); Wm['mo']=Wm.d0.dt.to_period('M').astype(str); Wm=Wm.join(M[['prev_up']].rename(columns={'prev_up':'mp'}),on='mo')
for w in ['IS','OOS']:
    for pv in [1,0]:
        lab='alta' if pv else 'baixa'
        rate('dia D alta | mes M-1 '+lab,w,(d.mo_prev_up==pv),d.up,d.ret,d.atr)
        s=Wm[(Wm.win==w)&(Wm.mp==pv)]; k=int(s.up.sum()); n=len(s); lo,hi=wilson(k,n)
        mo_rows.append(dict(achado='semana alta | mes M-1 '+lab,janela=w,n=n,taxa=k/n,ic_lo=lo,ic_hi=hi,nulo=wbase[w],p=pz(k,n,wbase[w])))
# ---------- ALINHAMENTO ----------
d['d1']=np.sign(d.ret.shift())
wk_open=d.groupby('wk').o.transform('first'); mo_open=d.groupby('mo').o.transform('first')
# semana/mes ate D-1: open do periodo de D-1 -> close de D-1 (se D abre periodo novo, e' o periodo completo anterior)
d['w1']=np.sign((d.c-wk_open).shift()); d['m1']=np.sign((d.c-mo_open).shift())
d['ma5']=np.sign(d.c.shift()-d.c.rolling(5).mean().shift()); d['ma20']=np.sign(d.c.shift()-d.c.rolling(20).mean().shift())
for w in ['IS','OOS']:
    rate('alinhado dia+sem+mes: 3 alta',w,(d.d1>0)&(d.w1>0)&(d.m1>0),d.up,d.ret,d.atr)
    rate('alinhado dia+sem+mes: 3 baixa',w,(d.d1<0)&(d.w1<0)&(d.m1<0),d.up,d.ret,d.atr)
    rate('preco>SMA5 e SMA20 (D-1)',w,(d.ma5>0)&(d.ma20>0),d.up,d.ret,d.atr)
    rate('preco<SMA5 e SMA20 (D-1)',w,(d.ma5<0)&(d.ma20<0),d.up,d.ret,d.atr)
    for a,b,cc in [(1,1,-1),(1,-1,1),(-1,1,1),(-1,-1,1),(-1,1,-1),(1,-1,-1)]:
        mk=(d.d1==a)&(d.w1==b)&(d.m1==cc)
        rate('dia'+('+' if a>0 else '-')+' sem'+('+' if b>0 else '-')+' mes'+('+' if cc>0 else '-'),w,mk,d.up,d.ret,d.atr)
    for nm in ['d1','w1','m1','ma5','ma20']:
        for sg,lab in [(1,'alta'),(-1,'baixa')]:
            rate('isolado '+nm+' '+lab,w,(d[nm]==sg),d.up,d.ret,d.atr)
# ---------- VIRADAS (dia) ----------
d['s1']=np.sign(d.ret.shift(1)); d['s2']=np.sign(d.ret.shift(2))
seq=(d.s1==d.s2)&(d.s1!=0)
d['virada']=np.where(seq,(np.sign(d.ret)==-d.s1).astype(float),np.nan)
rng=(d.h-d.l).replace(0,np.nan)
clv=((d.c-d.l)-(d.h-d.c))/rng
body=(d.c-d.o).abs()/rng
up_sh=(d.h-np.maximum(d.o,d.c))/rng; lo_sh=(np.minimum(d.o,d.c)-d.l)/rng
gap=(d.o-d.c.shift())
wk_h=d.groupby('wk').h.cummax(); wk_l=d.groupby('wk').l.cummin()
m1=m1.merge(d[['h','l']].shift(1).rename(columns={'h':'ph','l':'pl'}),left_on='date',right_index=True,how='left')
tup=(m1.h>=m1.ph).groupby(m1.date).sum().reindex(d.index); tdn=(m1.l<=m1.pl).groupby(m1.date).sum().reindex(d.index)
s1=d.s1
f2=pd.DataFrame(index=d.index)   # cada feature = valor do dia D-1, orientado pela direcao da sequencia (s1)
f2['range/ATR']=(rng/d.atr).shift(1)
f2['CLV (+ = fecha no extremo a favor da seq)']=clv.shift(1)*s1
f2['volume rel 20d']=(d.v/d.v.rolling(20).mean().shift(1)).shift(1)
f2['gap/ATR (+ = a favor da seq)']=(gap/d.atr).shift(1)*s1
f2['corpo/range']=body.shift(1)
f2['sombra do lado da seq (rejeicao)']=np.where(s1>0,up_sh.shift(1),lo_sh.shift(1))
f2['sombra do lado oposto']=np.where(s1>0,lo_sh.shift(1),up_sh.shift(1))
f2['dist extremo semana (dir seq)/ATR']=np.where(s1>0,((wk_h-d.c)/d.atr).shift(1),((d.c-wk_l)/d.atr).shift(1))
f2['testes M1 do extremo de D-2 (dir seq)']=np.where(s1>0,tup.shift(1),tdn.shift(1))
f2['virada']=d.virada; f2['win']=d.win
f2=f2.replace([np.inf,-np.inf],np.nan).dropna()
def auc(x,y):
    r=pd.Series(x).rank().values; n1=int(y.sum()); n0=len(y)-n1
    return (r[y==1].sum()-n1*(n1+1)/2)/(n1*n0)
rng_=np.random.default_rng(1)
def auc_tab(df,feats,w):
    s=df[df.win==w]; y=s.virada.values.astype(int); out=[]
    for c in feats:
        x=s[c].values; a=auc(x,y); bs=[]
        for _ in range(300):
            i=rng_.integers(0,len(y),len(y))
            if y[i].sum() in (0,len(y)): continue
            bs.append(auc(x[i],y[i]))
        pm=np.array([auc(x,rng_.permutation(y)) for _ in range(500)])
        out.append(dict(janela=w,feature=c,n=len(y),n_virada=int(y.sum()),taxa_virada=y.mean(),media_virada=x[y==1].mean(),media_cont=x[y==0].mean(),
            dif=x[y==1].mean()-x[y==0].mean(),AUC=a,auc_lo=np.percentile(bs,2.5),auc_hi=np.percentile(bs,97.5),p_perm=(np.sum(np.abs(pm-.5)>=abs(a-.5))+1)/501))
    return out
fc=[c for c in f2.columns if c not in('virada','win')]
VR=pd.DataFrame(auc_tab(f2,fc,'IS')+auc_tab(f2,fc,'OOS'))
# ---------- VIRADAS (semana): sinal da semana W != sinal de W-1; features da W-1 ----------
Wr=(W.h-W.l); Watr=d.groupby('wk').atr.first(); wv=d.groupby('wk').v.sum()
Wf=pd.DataFrame(index=W.index)
Wf['range/ATR14']=(Wr/Watr).shift(1)
Wf['CLV sem (+ = a favor da dir W-1)']=(((W.c-W.l)-(W.h-W.c))/Wr).shift(1)*np.where(W.up.shift(1)==1,1,-1)
Wf['corpo/range']=((W.c-W.o).abs()/Wr).shift(1)
Wf['volume rel 4sem']=(wv/wv.rolling(4).mean().shift(1)).shift(1)
Wf['virada']=(W.up!=W.up.shift()).astype(int); Wf['win']=W.win
Wf=Wf.replace([np.inf,-np.inf],np.nan).dropna()
fw=[c for c in Wf.columns if c not in('virada','win')]
WV=pd.DataFrame(auc_tab(Wf,fw,'IS')+auc_tab(Wf,fw,'OOS'))
# ---------- saidas ----------
R=pd.DataFrame(rows)
R.to_csv(os.path.join(D,'b_taxas_dia.csv'),sep=';',decimal=',',index=False)
SM=pd.DataFrame(wk_rows+mo_rows); SM.to_csv(os.path.join(D,'b_semana_mes.csv'),sep=';',decimal=',',index=False)
VR.to_csv(os.path.join(D,'b_viradas_dia_auc.csv'),sep=';',decimal=',',index=False)
WV.to_csv(os.path.join(D,'b_viradas_semana_auc.csv'),sep=';',decimal=',',index=False)
print('dias',len(d),'IS',(d.win=='IS').sum(),'OOS',(d.win=='OOS').sum(),'base',base,'wbase',wbase,'mbase',mbase)
print('semanas',W.win.value_counts().to_dict(),'meses',M.win.value_counts().to_dict())
print('testes',ntests,'p<.05',nsig)
pd.set_option('display.width',250,'display.max_rows',300,'display.max_columns',30)
print(R.round(3).to_string()); print(SM.round(3).to_string())
print(VR.round(3).to_string()); print(WV.round(3).to_string())
print(f2.groupby('win').virada.agg(['mean','size']))
