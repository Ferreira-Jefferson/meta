"""Lente 1: o leilao de abertura de D impacta o pregao de D? Reprodutivel: python lente1.py"""
import numpy as np, pandas as pd
rankdata = lambda a: pd.Series(a).rank().values
from pathlib import Path
R = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
rng = np.random.default_rng(7)
NPERM = 10000
d = pd.read_csv(R/'data/win_fases_pregao_6m.csv', sep=';', encoding='utf-8-sig')
d['data'] = pd.to_datetime(d.data)
m1 = pd.read_parquet(R/'data/comparativo_win_2026/m1_WIN$N.parquet')
m5 = m1.resample('5min', closed='left', label='left').agg(
    {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()

# ---- preditores (conhecidos ao fim do leilao de D) ----
d['callprev'] = d.pos_preco_fechamento.shift()
d['gap'] = d.pre_preco_fechamento - d.callprev
d['amp'] = d.pregao_maxima - d.pregao_minima
d['amp_med20'] = d.amp.shift().rolling(20, min_periods=10).mean()   # so passado
d['gap_n'] = d.gap / d.amp_med20
d['absgap'] = d.gap.abs(); d['absgap_n'] = d.gap_n.abs()
d['pre_vol'] = d.pre_volume.where(d.pre_volume > 0)
d['pre_neg'] = d.pre_negocios.where(d.pre_negocios > 0)
d['vol_por_neg'] = d.pre_vol / d.pre_neg
pv = d.pre_vol
d['d_vol'] = pv/pv.shift()-1
d['d_neg'] = d.pre_neg/d.pre_neg.shift()-1
d['d_vpn'] = d.vol_por_neg/d.vol_por_neg.shift()-1
d['vol_rel20'] = pv / pv.shift().rolling(20, min_periods=10).median()
t = pd.to_timedelta(d.pre_hora_leilao)
d['hora_s'] = (t - pd.Timedelta(hours=9)).dt.total_seconds()      # atraso apos 09:00
PRED = ['gap', 'gap_n', 'absgap', 'absgap_n', 'pre_vol', 'pre_neg', 'vol_por_neg', 'd_vol', 'd_neg', 'd_vpn', 'vol_rel20', 'hora_s']

# ---- alvos no pregao de D ----
d['var'] = d.pregao_preco_fechamento - d.pregao_preco_inicio
d['dir'] = np.sign(d['var'])
d['absvar'] = d['var'].abs()
d['pr_vol'] = d.pregao_volume
d['pr_neg'] = d.pregao_negocios
rows = []
for i, r in d.iterrows():
    dia = pd.Timestamp(r.data.date())
    day = m5.loc[str(r.data.date())]
    day = day[day.index < dia + pd.Timedelta(hours=18, minutes=20)]  # sem barra do call
    o = {}
    base = r.pregao_preco_inicio
    for k in (1, 3, 6, 12):
        o[f'm5_{k}'] = day.close.iloc[k-1] - base if len(day) >= k else np.nan
    g = r.gap
    if pd.notna(g) and g != 0:
        hit = (day.low <= r.callprev) if g > 0 else (day.high >= r.callprev)
        o['gap_fechou'] = float(hit.any())
        o['gap_min_fecha'] = (hit.idxmax() - dia - pd.Timedelta(hours=9)).total_seconds()/60 if hit.any() else np.nan
        o['gap_fechou_1h'] = float(hit[day.index < dia + pd.Timedelta(hours=10)].any())
    else:
        o['gap_fechou'] = o['gap_min_fecha'] = o['gap_fechou_1h'] = np.nan
    th = dia + pd.Timedelta(hours=10)
    hmax = day.index[day.high >= r.pregao_maxima]
    hmin = day.index[day.low <= r.pregao_minima]
    o['max_1h'] = float(len(hmax) > 0 and hmax[0] < th)
    o['min_1h'] = float(len(hmin) > 0 and hmin[0] < th)
    o['extremo_1h'] = float(o['max_1h'] or o['min_1h'])
    rows.append(o)
d = pd.concat([d, pd.DataFrame(rows, index=d.index)], axis=1)
d['gap_dir_x_var'] = np.sign(d.gap) * d['var']      # >0 = dia continua o gap
TARG = ['var', 'dir', 'absvar', 'amp', 'pr_vol', 'pr_neg', 'm5_1', 'm5_3', 'm5_6', 'm5_12',
        'gap_fechou', 'gap_min_fecha', 'max_1h', 'min_1h', 'extremo_1h', 'gap_dir_x_var']

PROB = pd.to_datetime(['2026-07-31', '2026-09-24', '2026-10-05', '2026-04-15', '2026-06-17', '2026-08-12'])
d['limpo'] = ~d.data.isin(PROB)
d['half'] = np.where(d.data < '2026-07-01', 'H1', 'H2')


def perm_rho(x, y, n=NPERM):
    ok = x.notna() & y.notna()
    x = x[ok].values
    y = y[ok].values
    if len(x) < 10 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan, len(x)
    rx = rankdata(x)
    ry = rankdata(y)
    rx_c = (rx-rx.mean())/rx.std()
    ry_c = (ry-ry.mean())/ry.std()
    rho = float(rx_c @ ry_c / len(x))
    P = np.array([rng.permutation(ry_c) for _ in range(n)])
    null = P @ rx_c / len(x)
    p = (np.sum(np.abs(null) >= abs(rho)-1e-12)+1)/(n+1)
    return rho, p, len(x)


def bh(p):
    p = np.asarray(p, float)
    q = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    pp = p[ok]
    o = np.argsort(pp)
    n = len(pp)
    qq = pp[o]*n/np.arange(1, n+1)
    qq = np.minimum.accumulate(qq[::-1])[::-1]
    r = np.empty(n)
    r[o] = np.minimum(qq, 1)
    q[ok] = r
    return q


def run(sub, label):
    res = []
    for pr in PRED:
        for tg in TARG:
            rho, p, n = perm_rho(sub[pr], sub[tg])
            h = {}
            for hh in ('H1', 'H2'):
                s = sub[sub.half == hh]
                h[hh] = perm_rho(s[pr], s[tg], 500)[0]
            res.append(dict(amostra=label, pred=pr, alvo=tg, n=n, rho=rho, p_perm=p, rho_H1=h['H1'], rho_H2=h['H2']))
    r = pd.DataFrame(res)
    r['q_BH'] = bh(r.p_perm.values)
    r['estavel'] = (np.sign(r.rho_H1) == np.sign(r.rho_H2)) & (np.sign(r.rho) == np.sign(r.rho_H1))
    return r


full = run(d, 'completa')
clean = run(d[d.limpo], 'limpa')
pd.concat([full, clean]).to_csv(OUT/'correlacoes.csv', index=False, sep=';', decimal=',')

CT = ('var', 'absvar', 'amp', 'pr_vol', 'pr_neg', 'm5_1', 'm5_6', 'gap_fechou', 'gap_min_fecha', 'extremo_1h', 'gap_dir_x_var')


def cond(sub, col, cut, name):
    s = sub[sub[col].notna()].copy()
    s['g'] = np.where(s[col] >= (s[col].median() if cut == 'med' else cut), 'alto', 'baixo')
    out = []
    for tg in CT:
        for g, x in s.groupby('g'):
            v = x[tg].dropna()
            out.append(dict(split=name, grupo=g, alvo=tg, n=len(v), media=v.mean(), mediana=v.median()))
        a = s[s.g == 'alto'][tg].dropna()
        b = s[s.g == 'baixo'][tg].dropna()
        if len(a) > 3 and len(b) > 3:
            obs = a.mean()-b.mean()
            allv = np.concatenate([a, b])
            cnt = 0
            for _ in range(5000):
                pm = rng.permutation(allv)
                cnt += abs(pm[:len(a)].mean()-pm[len(a):].mean()) >= abs(obs)-1e-9
            out.append(dict(split=name, grupo='dif(alto-baixo)', alvo=tg, n=len(a)+len(b), media=obs, mediana=(cnt+1)/5001))
    return out


cl = []
for lab, sub in (('completa', d), ('limpa', d[d.limpo])):
    for col, name in (('absgap', '|gap| pts'), ('absgap_n', '|gap|/amp20'), ('pre_vol', 'vol leilao'),
                      ('vol_rel20', 'vol leilao/mediana20'), ('pre_neg', 'neg leilao'), ('vol_por_neg', 'vol/negocio'),
                      ('hora_s', 'hora cruz (s apos 09:00) >= mediana')):
        for r in cond(sub, col, 'med', name):
            r['amostra'] = lab
            cl.append(r)
    for r in cond(sub, 'hora_s', 90, 'atraso >=90s'):
        r['amostra'] = lab
        cl.append(r)
    for r in cond(sub, 'gap', 0, 'gap>=0 (alto) vs <0'):
        r['amostra'] = lab
        cl.append(r)
cl = pd.DataFrame(cl)
cl.to_csv(OUT/'condicionais.csv', index=False, sep=';', decimal=',')

s = d[d.limpo & d.gap_n.notna()].copy()
s['faixa'] = pd.qcut(s.absgap_n, 3, labels=['pequeno', 'medio', 'grande'])
gf = s.groupby('faixa', observed=True).agg(n=('gap', 'size'), gap_pts_med=('absgap', 'median'), fechou=('gap_fechou', 'mean'),
                                           min_med=('gap_min_fecha', 'median'), fechou_1h=('gap_fechou_1h', 'mean'),
                                           cont_gap=('gap_dir_x_var', lambda x: (x > 0).mean()),
                                           var_x_gap_med=('gap_dir_x_var', 'mean')).reset_index()
gf.to_csv(OUT/'gap_fechado_por_faixa.csv', index=False, sep=';', decimal=',')

hh = d.groupby(d.pre_hora_leilao.str[:5]).agg(n=('data', 'size'), absgap_med=('absgap', 'median'), amp_med=('amp', 'median'),
                                              var_abs_med=('absvar', 'median'), pre_vol_med=('pre_vol', 'median'),
                                              pre_neg_med=('pre_neg', 'median')).reset_index()
hh.to_csv(OUT/'hora_cruzamento.csv', index=False, sep=';', decimal=',')
d.to_csv(OUT/'dataset_lente1.csv', index=False, sep=';', decimal=',')

pd.set_option('display.width', 250)
pd.set_option('display.max_rows', 500)
for lab, r in (('completa', full), ('limpa', clean)):
    print(f'== {lab}: testes={len(r)} p<0.05={int((r.p_perm < .05).sum())} q<0.10={int((r.q_BH < .10).sum())} q<0.05={int((r.q_BH < .05).sum())}')
    print(r.sort_values('p_perm').head(20).round(4).to_string())
print(gf.round(3).to_string())
print(hh.round(1).to_string())
print(cl[(cl.amostra == 'limpa') & (cl.grupo == 'dif(alto-baixo)')].round(3).to_string())
