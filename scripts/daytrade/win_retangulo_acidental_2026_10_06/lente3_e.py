from lente3_b import *
rng=np.random.default_rng(3)
rows=[]
for d,g in D.groupby(D.index.date):
    mm=(g.index.hour*60+g.index.minute).to_numpy()
    iz=np.flatnonzero(mm>=1100); ex=g.open.iloc[iz[0]]
    for H in (11*60, 11*60+30, 14*60):
        i=np.flatnonzero(mm==H)[0]; px=g.open.iloc[i]
        rows.append(dict(dia=d,H=H,px=px,aber=g.open.iloc[0],ex=ex,mov=ex-px,sgn=np.sign(px-g.open.iloc[0]),manha=px-g.open.iloc[0]))
R=pd.DataFrame(rows)
for H,g in R.groupby('H'):
    fade=-g.sgn*g.mov*0.2-CUSTO; fade=fade[g.sgn!=0]
    print(f'H={H//60}:{H%60:02d} n={len(g)} fade total {fade.sum():.0f} dias+ {(fade>0).sum()}/{len(fade)}  sempre-long {(g.mov*0.2-CUSTO).sum():.0f} sempre-short {(-g.mov*0.2-CUSTO).sum():.0f}')
    f=np.sort(fade.values)[::-1]; print('   top3',f[:3].round(0),' sem top3',round(f[3:].sum()),' dias+ sem top3',(f[3:]>0).sum(),'/',len(f)-3)
    mv=(g.mov*0.2).values; sg=g.sgn.values
    dist=np.array([(rng.choice([-1,1],len(mv))*mv).sum()-CUSTO*len(mv) for _ in range(5000)])
    print('   percentil do fade vs direção sorteada',(dist<fade.sum()).mean()*100, ' (permutar o sinal manha entre dias:)',end=' ')
    pm=np.array([(-rng.permutation(sg)*mv).sum()-CUSTO*len(mv) for _ in range(5000)]); print((pm<fade.sum()).mean()*100)
    for m in (8,9): 
        gm=g[pd.to_datetime(g.dia).dt.month==m]; print('   mes',m,round((-gm.sgn*gm.mov*0.2-CUSTO).sum()),'dias+',((-gm.sgn*gm.mov*0.2-CUSTO)>0).sum(),'/',len(gm))
    print('   corr(manha, mov)',round(np.corrcoef(g.manha,g.mov)[0,1],2),' mov médio pts',round(g.mov.mean(),0))
# rectângulo corrigido: dias onde fade 11h e retângulo coincidem
