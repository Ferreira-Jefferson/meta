from lente3_b import *
rng=np.random.default_rng(7)
# preços por dia
days={}
for d,g in D.groupby(D.index.date):
    mm=(g.index.hour*60+g.index.minute).to_numpy()
    iz=np.flatnonzero(mm>=18*60+20)
    ex=g.open.iloc[iz[0]] if len(iz) else g.close.iloc[-1]
    days[d]=(g,mm,ex)
print('dias na base',len(days))
N=5000
def pct(real,dist): return (dist<real).mean()*100, (dist<=real).mean()*100
res={}
for nome,cfg in [('DEFEITO',Cfg(modo_defeito=True)),('CORR sem SL',Cfg(alvo_frac=None,stop_frac=None))]:
    t=run(cfg); real=t.rs.sum(); pts=t.pts.values
    # (i) sorteio de direção
    s=rng.choice([-1,1],size=(N,len(t)))
    d1=(s*np.abs(pts)*0+s*(pts*t.lado.values))  # pts já tem lado; bruto = pts*lado
    d1=((s*(pts*t.lado.values))*0.2-CUSTO).sum(1)
    # (ii-a) mesmo horário, direção sorteada (entrada = open da barra do t_ent)
    br=[];
    for _,r in t.iterrows():
        g,mm,ex=days[r.dia]; br.append(ex-g.open.loc[r.t_ent])
    br=np.array(br); d2=((s*br)*0.2-CUSTO).sum(1)
    # (ii-b) horário aleatório 10:00-17:00 + direção aleatória, mesmo nº de dias
    ds=[r.dia for _,r in t.iterrows()]
    d3=np.zeros(N)
    for k in range(N):
        tot=0
        for dd in ds:
            g,mm,ex=days[dd]; idx=np.flatnonzero((mm>=600)&(mm<=17*60))
            i=rng.choice(idx); tot+=rng.choice([-1,1])*(ex-g.open.iloc[i])*0.2-CUSTO
        d3[k]=tot
    # (ii-c) mesmo horário, direção a favor/contra: determinístico (fade) - reportado como tal
    print(f'\n{nome}: real R$ {real:.0f}')
    for lab,dist in [('(i) dir sorteada, mesmas entradas',d1),('(ii-a) mesmo horário, dir sorteada',d2),('(ii-b) horário e dir sorteados',d3)]:
        a,b=pct(real,dist); print(f'  {lab}: média {dist.mean():.0f} sd {dist.std():.0f} p5/p95 {np.percentile(dist,5):.0f}/{np.percentile(dist,95):.0f} percentil real {a:.1f}-{b:.1f}')
    # dentro de agosto/setembro separado
    for m in (8,9):
        tm=t[t.mes==m]; sm=rng.choice([-1,1],size=(N,len(tm)))
        dm=((sm*(tm.pts.values*tm.lado.values))*0.2-CUSTO).sum(1); print(f'  mes {m}: real {tm.rs.sum():.0f}, percentil (i) {pct(tm.rs.sum(),dm)[0]:.1f}')
# (iii) regra simples sem retângulo
print('\n(iii) regra sem retangulo, H de 11:00 a 16:00, 1 trade/dia, segura até 18:20, R$2/op')
rows=[]
for ref in ('aber','vwap'):
    for H in range(11*60,16*60+1,30):
        for modo in ('a_favor','fade'):
            tot={8:0,9:0,10:0};n=0;pos=0
            for d,(g,mm,ex) in days.items():
                i=np.flatnonzero(mm==H)
                if not len(i) or i[0]==0: continue
                i=i[0]; px=g.open.iloc[i]
                prev=g.iloc[:i]
                r0=g.open.iloc[0] if ref=='aber' else (((prev.high+prev.low+prev.close)/3*raw.loc[prev.index,'tickvol']).sum()/raw.loc[prev.index,'tickvol'].sum())
                if px==r0: continue
                lado=np.sign(px-r0)*(1 if modo=='a_favor' else -1)
                v=lado*(ex-px)*0.2-CUSTO; tot[d.month]+=v; n+=1
            rows.append((ref,f'{H//60}:{H%60:02d}',modo,n,round(tot[8]),round(tot[9]),round(tot[8]+tot[9]+tot[10])))
R=pd.DataFrame(rows,columns=['ref','H','modo','n','ago','set','total'])
print(R.pivot_table(index='H',columns=['ref','modo'],values='total').to_string())
print('\nset apenas:'); print(R.pivot_table(index='H',columns=['ref','modo'],values='set').to_string())
print('\nago apenas:'); print(R.pivot_table(index='H',columns=['ref','modo'],values='ago').to_string())
print('combos testados',len(R),'; positivos set e ago:',((R['set']>0)&(R.ago>0)).sum())
