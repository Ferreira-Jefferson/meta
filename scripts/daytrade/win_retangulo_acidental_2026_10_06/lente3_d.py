from lente3_b import *
from types import SimpleNamespace as NS
def spearmanr(a,b):
    a=pd.Series(np.asarray(a,float)); b=pd.Series(np.asarray(b,float)); r=a.rank().corr(b.rank())
    n=len(a); rg=np.random.default_rng(1); br=b.rank().values
    perm=np.array([a.rank().corr(pd.Series(rg.permutation(br))) for _ in range(2000)])
    return NS(statistic=r,pvalue=(np.abs(perm)>=abs(r)).mean())
def mannwhitneyu(x,y):
    x=np.asarray(x);y=np.asarray(y);rg=np.random.default_rng(2);z=np.concatenate([x,y]);d0=abs(x.mean()-y.mean())
    c=np.mean([abs((lambda p:p[:len(x)].mean()-p[len(x):].mean())(rg.permutation(z)))>=d0 for _ in range(5000)])
    return NS(pvalue=np.float64(c))
t=feats(run(Cfg(alvo_frac=None,stop_frac=None)))
t['lim_def']=np.floor(np.floor(t.meio/0.5+0.5)*0.5+0.5)
t['passa']=((t.lim_def/5-np.round(t.lim_def/5)).abs()<1e-9).astype(int)
print('item 3: braços corrigidos que o defeito aceitaria:',t.passa.sum(),'de',len(t),'(esperado ~20% se aleatório =',round(len(t)*.2,1),')')
print(t.groupby('passa').agg(n=('rs','size'),rs=('rs','sum'),rs_med=('rs','mean'),hora=('hora','mean'),larg=('larg','mean'),pts_lado=('pts','mean'),gap=('gap','mean'),volman=('vol_man','mean')).round(1))
print('mw p (rs passa vs recusa):',mannwhitneyu(t[t.passa==1].rs,t[t.passa==0].rs).pvalue.round(3))
print('meio mod 5 distribuição:',(t.meio%5).round(1).value_counts().to_dict())
print('\nitem 4: Spearman vs rs, n=',len(t)); S=t[t.mes>=9]; A=t[t.mes==8]
ntest=0
for f in ['larg','vol_man','gap','hora','dow','a_aber','a_vwap','a_e34','a_e200','lado']:
    r_all=spearmanr(t[f],t.rs); r_s=spearmanr(S[f],S.rs); r_a=spearmanr(A[f],A.rs); ntest+=1
    print(f'{f:8s} todos rho {r_all.statistic:+.2f} p {r_all.pvalue:.3f} | set rho {r_s.statistic:+.2f} p {r_s.pvalue:.3f} (n={len(S)}) | ago rho {r_a.statistic:+.2f} (n={len(A)})')
# gap abs, larg/vol_man ratio
S=S.assign(gabs=S.gap.abs(),lv=S.larg/S.vol_man); A=A.assign(gabs=A.gap.abs(),lv=A.larg/A.vol_man); t['gabs']=t.gap.abs(); t['lv']=t.larg/t.vol_man
for f in ['gabs','lv']:
    r=spearmanr(t[f],t.rs); rs_=spearmanr(S[f],S.rs); ra=spearmanr(A[f],A.rs); print(f'{f:8s} todos rho {r.statistic:+.2f} p {r.pvalue:.3f} | set {rs_.statistic:+.2f} p {rs_.pvalue:.3f} | ago {ra.statistic:+.2f}')
print('dow:',t.groupby('dow').rs.agg(['count','sum']).round(0).to_dict('index'))
# fade vs a_favor sinal por mês
print('a_aber por mês:'); print(t.groupby(['mes','a_aber']).rs.agg(['count','sum','mean']).round(0))
print('a_e200 por mês:'); print(t.groupby(['mes','a_e200']).rs.agg(['count','sum','mean']).round(0))
print('hora<11 vs >=11 por mês:'); t['cedo']=(t.hora<11).astype(int); print(t.groupby(['mes','cedo']).rs.agg(['count','sum','mean']).round(0))
t.to_csv('lente3_trades_corr.csv',index=False)
