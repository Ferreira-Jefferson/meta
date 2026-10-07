from lente3_base import *
raw = pd.read_csv(sim.DADOS / sim.ARQ['WINV26'], sep='\t'); raw.columns=[c.strip('<>').lower() for c in raw.columns]
raw['ts']=pd.to_datetime(raw.date+' '+raw.time, format='%Y.%m.%d %H:%M:%S'); raw=raw.set_index('ts').sort_index()
raw['tp']=(raw.high+raw.low+raw.close)/3; raw['dia']=raw.index.date
raw['vwap']=(raw.tp*raw.tickvol).groupby(raw.dia).cumsum()/raw.tickvol.groupby(raw.dia).cumsum()
raw['ema34']=raw.close.ewm(span=34).mean(); raw['ema200']=raw.close.ewm(span=200).mean()
raw['aber']=raw.groupby('dia').open.transform('first')
prev=raw.groupby('dia').close.last().shift(1); 
def feats(t):
    t=t.copy()
    r=raw.loc[t.t_ent]
    for k,col in [('aber','aber'),('vwap','vwap'),('e34','ema34'),('e200','ema200')]:
        t['a_'+k]=(np.sign(t.ent.values-r[col].values)==t.lado.values).astype(int)
    t['hora']=t.t_ent.dt.hour+t.t_ent.dt.minute//30*0.5
    t['dow']=pd.to_datetime(t.dia).dt.dayofweek
    t['gap']=[ (raw[raw.dia==d].open.iloc[0]-prev[d]) for d in t.dia]
    t['vol_man']=[ (lambda g:(g.high.max()-g.low.min()))(raw[(raw.dia==d)].between_time('09:00','10:30')) for d in t.dia]
    return t
if __name__=='__main__':
    for nome,cfg in [('DEFEITO',Cfg(modo_defeito=True)),('CORR sem SL',Cfg(alvo_frac=None,stop_frac=None))]:
        t=feats(run(cfg)); print('\n=====',nome,len(t),'trades, R$',round(t.rs.sum()))
        print('(a) hora entrada'); print(t.groupby('hora').rs.agg(['count','sum']).round(0).T.to_string())
        print('(b) alinhado c/ ref (1=a favor do lado do preço)')
        for k in ['a_aber','a_vwap','a_e34','a_e200']:
            print(k, t.groupby(k).rs.agg(['count','sum','mean']).round(1).to_dict('index'))
        print('lado', t.groupby('lado').rs.agg(['count','sum']).round(0).to_dict('index'))
        print('(c) pts: mediana',t.pts.median(),'|pts| med',t.pts.abs().median(),'maior ganho',t.rs.max(),'maior perda',t.rs.min())
        dia=t.groupby('dia').rs.sum().sort_values(ascending=False)
        print('(d) dias',len(dia),'positivos',(dia>0).sum(),'top3',dia.head(3).round(0).tolist(),'soma top3',round(dia.head(3).sum()),'total',round(dia.sum()))
        r=dia.iloc[3:]; print('   sem top3: soma',round(r.sum()),'positivos',(r>0).sum(),'de',len(r))
        print('   sem top3 e sem 3 piores:',round(dia.iloc[3:-3].sum()))
        for m,g in t.groupby('mes'):
            dm=g.groupby('dia').rs.sum().sort_values(ascending=False); print('   mes',m,'total',round(dm.sum()),'positivos',(dm>0).sum(),'/',len(dm),'sem top2',round(dm.iloc[2:].sum()))
