"""Lente 5: call de D-1 + leilao de D (combinados) -> pregao de D. Reprodutivel: python lente5.py"""
import numpy as np, pandas as pd
from pathlib import Path
R = Path(__file__).resolve().parents[4]; OUT = Path(__file__).parent
rng = np.random.default_rng(11); NPERM = 10000
rk = lambda a: pd.Series(a).rank().values
d = pd.read_csv(R/'data/win_fases_pregao_6m.csv', sep=';', encoding='utf-8-sig'); d['data'] = pd.to_datetime(d.data)
m1 = pd.read_parquet(R/'data/comparativo_win_2026/m1_WIN$N.parquet')
m5 = m1.resample('5min', closed='left', label='left').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()

# ---- variaveis D-1 / D (tudo conhecido ao fim do leilao de D) ----
d['callprev'] = d.pos_preco_fechamento.shift(); d['fechprev'] = d.pregao_preco_fechamento.shift()
d['pos_vol_prev'] = d.pos_volume.shift(); d['pos_neg_prev'] = d.pos_negocios.shift()
d['pre_p'] = d.pre_preco_fechamento.where(d.pre_volume > 0)
d['mov_call'] = d.callprev - d.fechprev            # ultimo continuo D-1 -> call D-1
d['gap'] = d.pre_p - d.callprev                    # gap oficial
d['tot'] = d.pre_p - d.fechprev                    # movimento total
d['amp'] = d.pregao_maxima - d.pregao_minima
d['amp20'] = d.amp.shift().rolling(20, min_periods=10).mean()
for c in ['mov_call','gap','tot']: d[c+'_n'] = d[c]/d.amp20
d['abs_mov'] = d.mov_call.abs(); d['abs_gap'] = d.gap.abs(); d['abs_tot'] = d.tot.abs()
d['lograzao_gap_mov'] = np.log((d.abs_gap+25)/(d.abs_mov+25))   # |gap| vs |call| (suavizado, 25 pts)
pv = d.pre_volume.where(d.pre_volume > 0); d['pre_vol'] = pv
d['comb_vol'] = d.pos_vol_prev + pv
d['lograzao_vol'] = np.log(pv/d.pos_vol_prev)
d['pos_rel20'] = d.pos_vol_prev/d.pos_volume.shift(1).rolling(20, min_periods=10).median()  # mediana so de dias <= D-2
d['pre_rel20'] = pv/pv.shift().rolling(20, min_periods=10).median()
d['ambos_acima'] = ((d.pos_rel20 > 1) & (d.pre_rel20 > 1)).astype(float).where(d.pos_rel20.notna() & d.pre_rel20.notna())
d['sinal_call'] = np.sign(d.mov_call); d['sinal_gap'] = np.sign(d.gap)
d['concorda'] = (d.sinal_call*d.sinal_gap).where((d.sinal_call != 0) & (d.sinal_gap != 0))  # +1 mesmo sentido, -1 gap desfaz call
PRED = ['mov_call','gap','tot','mov_call_n','gap_n','tot_n','abs_mov','abs_gap','abs_tot','lograzao_gap_mov',
        'pos_vol_prev','pre_vol','comb_vol','lograzao_vol','pos_rel20','pre_rel20','ambos_acima','concorda']

# ---- alvos no pregao de D ----
d['var'] = d.pregao_preco_fechamento - d.pregao_preco_inicio; d['dir'] = np.sign(d['var']); d['absvar'] = d['var'].abs()
d['pr_vol'] = d.pregao_volume; d['pr_neg'] = d.pregao_negocios
rows = []
for i, r in d.iterrows():
    dia = pd.Timestamp(r.data.date()); day = m5.loc[str(r.data.date())]
    day = day[day.index < dia + pd.Timedelta(hours=18, minutes=20)]
    o = {}
    for k in (1,3,6,12): o[f'm5_{k}'] = day.close.iloc[k-1]-r.pregao_preco_inicio if len(day) >= k else np.nan
    for nm, lvl in (('toca_call', r.callprev), ('toca_fech', r.fechprev)):
        if pd.notna(r.pre_p) and pd.notna(lvl) and r.pregao_preco_inicio != lvl:
            up = lvl > r.pregao_preco_inicio   # nivel acima da abertura -> precisa subir
            o[nm] = float((day.high >= lvl).any() if up else (day.low <= lvl).any())
        else: o[nm] = np.nan
    rows.append(o)
d = pd.concat([d, pd.DataFrame(rows, index=d.index)], axis=1)
d['cont_tot'] = np.sign(d.tot)*d['var']     # >0: pregao continua o movimento total
TARG = ['var','dir','absvar','amp','pr_vol','pr_neg','m5_1','m5_3','m5_6','m5_12','toca_call','toca_fech','cont_tot']

FLAG = pd.to_datetime(['2026-04-15','2026-06-17','2026-08-12','2026-07-31','2026-09-24','2026-09-25','2026-08-03'])
# 09-25 (D-1 = 09-24 com ticks faltando) e 08-03 (D-1 = pregao parcial 07-31) saem por precaucao: D-1 contaminado
d['half'] = np.where(d.data < '2026-07-01','H1','H2')
BASES = {'sem_flags_com_1005': d[~d.data.isin(FLAG)], 'sem_flags_sem_1005': d[~d.data.isin(FLAG) & (d.data != '2026-10-05')]}

def prm(x, y):
    ok = x.notna() & y.notna(); x = x[ok].values; y = y[ok].values
    if len(x) < 20 or x.std() == 0 or y.std() == 0: return np.nan, np.nan, len(x)
    rx = rk(x); ry = rk(y); rho = np.corrcoef(rx, ry)[0,1]
    ryz = (ry-ry.mean())/ry.std(); rxz = (rx-rx.mean())/rx.std()
    P = np.array([rng.permutation(ryz) for _ in range(NPERM)]); sim = P@rxz/len(x)
    return rho, (np.sum(np.abs(sim) >= abs(rho)-1e-12)+1)/(NPERM+1), len(x)
def rho_only(x, y):
    ok = x.notna() & y.notna()
    if ok.sum() < 15: return np.nan
    return np.corrcoef(rk(x[ok]), rk(y[ok]))[0,1]
def bh(p):
    p = np.array(p, float); q = np.full(len(p), np.nan); ok = ~np.isnan(p); pp = p[ok]; o = np.argsort(pp); n = len(pp)
    qq = pp[o]*n/np.arange(1, n+1); qq = np.minimum.accumulate(qq[::-1])[::-1]; tmp = np.empty(n); tmp[o] = np.minimum(qq,1); q[ok] = tmp; return q

allres = []
for bn, b in BASES.items():
    res = []
    for p in PRED:
        for t in TARG:
            rho, pp, n = prm(b[p], b[t])
            h1 = rho_only(b.loc[b.half=='H1', p], b.loc[b.half=='H1', t]); h2 = rho_only(b.loc[b.half=='H2', p], b.loc[b.half=='H2', t])
            res.append(dict(base=bn, pred=p, alvo=t, n=n, rho=rho, p_perm=pp, rho_H1=h1, rho_H2=h2))
    r = pd.DataFrame(res); r['q_BH'] = bh(r.p_perm); r['estavel'] = np.sign(r.rho_H1) == np.sign(r.rho_H2)
    allres.append(r)
res = pd.concat(allres); res.to_csv(OUT/'correlacoes.csv', index=False)
for bn in BASES:
    r = res[res.base == bn]
    print(f'\n== {bn}: {len(r)} testes; p<0.05: {(r.p_perm<0.05).sum()} (esperado {0.05*len(r):.0f}); q<0.05: {(r.q_BH<0.05).sum()}; q<0.10: {(r.q_BH<0.10).sum()}; |rho|>=0.30: {(r.rho.abs()>=0.30).sum()}')
    print(r.sort_values('p_perm').head(15).round(4).to_string(index=False))

# ---- 4 grupos por sinal (call D-1 x gap D) ----
def perm_groups(b, col, lab, n=NPERM):
    ok = b[col].notna() & b[lab].notna(); y = b.loc[ok, col].values.astype(float); g = b.loc[ok, lab].values
    def stat(g_): return sum(((y[g_ == k].mean()-y.mean())**2)*np.sum(g_ == k) for k in np.unique(g_))
    s = stat(g); sim = np.array([stat(rng.permutation(g)) for _ in range(n)]); return (np.sum(sim >= s)+1)/(n+1)
grp_out = []
for bn, b in BASES.items():
    b = b.copy()
    okg = b.sinal_call.notna() & b.sinal_gap.notna() & (b.sinal_call != 0) & (b.sinal_gap != 0)
    b['grupo'] = pd.Series(np.where(okg, 'call' + np.where(b.sinal_call > 0, '+', '-') + '/gap' + np.where(b.sinal_gap > 0, '+', '-'), None), index=b.index)
    b['alta'] = (b['var'] > 0).astype(float).where(b['var'].notna())
    print(f'\n== 4 grupos [{bn}] ==')
    t = b.dropna(subset=['grupo']).groupby('grupo').agg(n=('var','size'), var_media=('var','mean'), var_mediana=('var','median'), pct_alta=('alta','mean'),
        amp_media=('amp','mean'), m5_1=('m5_1','mean'), m5_3=('m5_3','mean'), m5_6=('m5_6','mean'), m5_12=('m5_12','mean'),
        toca_call=('toca_call','mean'), toca_fech=('toca_fech','mean'), mov_call_med=('mov_call','median'), gap_med=('gap','median'))
    print(t.round(2).to_string())
    for c in ['var','alta','amp','m5_3','m5_12','toca_call']:
        print(f'  p perm (variancia entre grupos) {c}: {perm_groups(b, c, "grupo"):.4f}')
    t['base'] = bn; grp_out.append(t.reset_index())
    b['conc'] = pd.Series(np.where(b.concorda > 0, 'mesmo_sentido', np.where(b.concorda < 0, 'gap_desfaz_call', None)), index=b.index)
    t2 = b.dropna(subset=['conc']).groupby('conc').agg(n=('var','size'), var_media=('var','mean'), pct_alta=('alta','mean'), amp_media=('amp','mean'),
        absvar=('absvar','mean'), toca_call=('toca_call','mean'), toca_fech=('toca_fech','mean'), cont_tot=('cont_tot','mean'), cont_tot_med=('cont_tot','median'))
    print(t2.round(2).to_string())
    for c in ['var','amp','absvar','cont_tot','toca_call']: print(f'  p perm conc {c}: {perm_groups(b, c, "conc"):.4f}')
    print('  sinal(tot)==sinal(gap):', round((np.sign(b.tot) == np.sign(b.gap))[b.tot.notna()].mean(), 3), ' n=', b.tot.notna().sum(),
          '| rho gap x tot:', round(rho_only(b.gap, b.tot), 3), '| dias em que sinal difere:', int(((np.sign(b.tot) != np.sign(b.gap)) & b.tot.notna()).sum()))
    b['tercil_rel'] = pd.qcut(b.lograzao_gap_mov, 3, labels=['gap<<call','meio','gap>>call'])
    t3 = b.groupby('tercil_rel', observed=True).agg(n=('var','size'), var_media=('var','mean'), amp=('amp','mean'), toca_call=('toca_call','mean'), toca_fech=('toca_fech','mean'))
    print(t3.round(2).to_string())
    b['vol_g'] = pd.Series(np.where(b.ambos_acima == 1, 'ambos_acima', np.where(b.ambos_acima == 0, 'outros', None)), index=b.index)
    t4 = b.dropna(subset=['vol_g']).groupby('vol_g').agg(n=('var','size'), absvar=('absvar','mean'), amp=('amp','mean'), pr_vol=('pr_vol','mean'), var_media=('var','mean'))
    print(t4.round(0).to_string())
    for c in ['amp','absvar','pr_vol']: print(f'  p perm vol_g {c}: {perm_groups(b, c, "vol_g"):.4f}')
    t5 = b.dropna(subset=['grupo']).groupby(['grupo','half']).agg(n=('var','size'), var_media=('var','mean'), pct_alta=('alta','mean')).round(2)
    print(t5.to_string())
pd.concat(grp_out).to_csv(OUT/'grupos4.csv', index=False)
d.to_csv(OUT/'dataset_lente5.csv', index=False)
print('\nn bases:', len(BASES['sem_flags_com_1005']), len(BASES['sem_flags_sem_1005']))
print('dp var:', round(BASES['sem_flags_sem_1005']['var'].std()), ' mediana amp:', BASES['sem_flags_sem_1005'].amp.median())
