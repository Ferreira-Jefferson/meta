"""Lente 6: cada fase contra a fase imediatamente anterior. Reprodutivel: python lente6.py"""
import numpy as np, pandas as pd
rankdata = lambda a: pd.Series(np.asarray(a, float)).rank().values
from pathlib import Path
R = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
rng = np.random.default_rng(11)
NP = 10000
d = pd.read_csv(R/'data/win_fases_pregao_6m.csv', sep=';', encoding='utf-8-sig')
d['data'] = pd.to_datetime(d.data)
m1 = pd.read_parquet(R/'data/comparativo_win_2026/m1_WIN$N.parquet')
m5 = m1.resample('5min', closed='left', label='left').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
n = len(d)
T = pd.Timestamp
EXC = [T('2026-07-31'), T('2026-09-24')]                     # saem de tudo
ROL = [T('2026-04-15'), T('2026-06-17'), T('2026-08-12')]    # saem de preco do pre


def lg(x):
    x = x.astype(float)
    return np.log(x.where(x > 0))


bad = d.data.isin(EXC)
L = {'pre': {'v': lg(d.pre_volume), 'n': lg(d.pre_negocios)},
     'pr': {'v': lg(d.pregao_volume), 'n': lg(d.pregao_negocios)},
     'pos': {'v': lg(d.pos_volume), 'n': lg(d.pos_negocios)}}
for k in L:
    L[k]['vn'] = L[k]['v'] - L[k]['n']
    for m in L[k]:
        L[k][m] = L[k][m].where(~bad)
leil = d.pre_preco_fechamento.where(~bad)
call = d.pos_preco_fechamento
fech = d.pregao_preco_fechamento
leil_p = leil.where(~d.data.isin(ROL))
V = pd.DataFrame(index=d.index)
V['A_dp'] = leil_p - call.shift().where(~d.data.shift().isin(EXC))
for m in ('v', 'n', 'vn'):
    V['A_' + m] = L['pre'][m] - L['pos'][m].shift()
V['B0_dp'] = (fech - leil_p).where(~bad)
V['C0_dp'] = (call - fech).where(~bad)
for m in ('v', 'n', 'vn'):
    V['B0_' + m] = L['pr'][m] - L['pre'][m]
    V['C0_' + m] = L['pos'][m] - L['pr'][m]
for c in list(V.columns):
    if c.startswith(('B0_', 'C0_')):
        V[c.replace('0_', '1_')] = V[c].shift()
OPER = ['A_dp', 'A_v', 'A_n', 'A_vn', 'B1_dp', 'B1_v', 'B1_n', 'B1_vn', 'C1_dp', 'C1_v', 'C1_n', 'C1_vn']
CONT = ['B0_dp', 'B0_v', 'B0_n', 'B0_vn', 'C0_dp', 'C0_v', 'C0_n', 'C0_vn']
d['var'] = fech - d.pregao_preco_inicio
Y = pd.DataFrame({'var': d['var'], 'dir': np.sign(d['var']), 'absvar': d['var'].abs(),
                  'amp': d.pregao_maxima - d.pregao_minima, 'pr_vol': d.pregao_volume, 'pr_neg': d.pregao_negocios})
for k in (1, 3, 6, 12):
    vals = []
    for i, r in d.iterrows():
        day = m5.loc[str(r.data.date())]
        day = day[day.index < T(r.data.date()) + pd.Timedelta(hours=18, minutes=20)]
        vals.append(day.close.iloc[k - 1] - r.pregao_preco_inicio if len(day) >= k else np.nan)
    Y['m5_%d' % k] = vals
Y = Y.astype(float).mask(bad, np.nan)
half = np.where(d.data < '2026-07-01', 'H1', 'H2')
no105 = ~(d.data == T('2026-10-05')).values


def rho(x, y):
    return np.corrcoef(rankdata(x), rankdata(y))[0, 1]


def test(x, y, msk, nulo_den=None):
    ok = msk & ~np.isnan(x) & ~np.isnan(y)
    xs, ys = x[ok], y[ok]
    if len(xs) < 20 or xs.std() == 0 or ys.std() == 0:
        return None
    rx, ry = rankdata(xs), rankdata(ys)
    r0 = np.corrcoef(rx, ry)[0, 1]
    P = np.array([rng.permutation(len(ry)) for _ in range(NP)])
    rp = ((rx - rx.mean()) * (ry[P] - ry.mean())).sum(1) / (len(rx) * rx.std() * ry.std())
    p1 = (np.abs(rp) >= abs(r0) - 1e-12).mean()
    sh = [rho(xs, np.roll(ys, s)) for s in range(5, len(ys) - 5)]
    p2 = (np.abs(sh) >= abs(r0) - 1e-12).mean()
    p3 = np.nan
    if nulo_den is not None:
        num, den = nulo_den
        nn, dd = num[ok], den[ok]
        if not (np.isnan(nn).any() or np.isnan(dd).any()):
            rr = [rho(nn - np.roll(dd, s), ys) for s in range(5, len(dd) - 5)]
            p3 = (np.abs(rr) >= abs(r0) - 1e-12).mean()
    h = []
    for hh in ('H1', 'H2'):
        k = (half[ok] == hh)
        h.append(rho(xs[k], ys[k]) if k.sum() > 15 else np.nan)
    return dict(n=len(xs), rho=r0, p_perm=p1, p_bloco=p2, p_razao=p3, rho_H1=h[0], rho_H2=h[1],
                estavel=bool(np.sign(h[0]) == np.sign(h[1]) == np.sign(r0)))


def bh(p):
    p = np.asarray(p, float)
    o = np.argsort(p)
    q = np.empty_like(p)
    m = len(p)
    q[o] = np.minimum.accumulate((p[o] * m / (np.arange(m) + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def den_num(c):
    g, m = c.split('_')
    if m == 'dp':
        return None
    if g == 'A':
        return L['pre'][m].values, L['pos'][m].shift().values
    a, b = {'B1': ('pr', 'pre'), 'C1': ('pos', 'pr')}[g]
    return L[a][m].shift().values, L[b][m].shift().values


rows = []
for samp, base in (('com_10-05', np.ones(n, bool)), ('sem_10-05', no105)):
    for c in OPER + CONT:
        for t in Y.columns:
            if c in OPER:
                nd = den_num(c)
            elif not c.endswith('_dp'):
                g, m = c.split('_')
                a, b = ('pr', 'pre') if g == 'B0' else ('pos', 'pr')
                nd = (L[a][m].values, L[b][m].values)
            else:
                nd = None
            r = test(V[c].values, Y[t].values, base, nd)
            if r:
                rows.append(dict(amostra=samp, rotulo='operavel' if c in OPER else 'contemporaneo', pred=c, alvo=t, **r))
res = pd.DataFrame(rows)
res['p_cons'] = res[['p_perm', 'p_bloco', 'p_razao']].max(axis=1, skipna=True)
for (samp, rot), g in res.groupby(['amostra', 'rotulo']):
    res.loc[g.index, 'q_perm'] = bh(g.p_perm)
    res.loc[g.index, 'q_cons'] = bh(g.p_cons)
res.to_csv(OUT / 'correlacoes.csv', index=False, float_format='%.4f')
print(res.groupby(['amostra', 'rotulo']).agg(testes=('rho', 'size'), p05=('p_perm', lambda s: (s < .05).sum()),
                                              q05=('q_perm', lambda s: (s < .05).sum()), qcons10=('q_cons', lambda s: (s < .10).sum())))
cols = ['amostra', 'pred', 'alvo', 'n', 'rho', 'p_perm', 'p_bloco', 'p_razao', 'q_perm', 'q_cons', 'rho_H1', 'rho_H2', 'estavel']
print(res[res.rotulo == 'operavel'].sort_values('p_perm').head(25)[cols].to_string())
print(res[res.rotulo == 'contemporaneo'].sort_values('p_perm').head(15)[cols].to_string())


# (b) cadeia
def pairs(a, b, c):
    B = b - a
    C = c - b
    A = np.r_[np.nan, a[1:] - c[:-1]]
    An = np.r_[A[1:], np.nan]
    Bn = np.r_[B[1:], np.nan]
    return {'B->C (mesmo dia)': (B, C), 'C->A (pos X -> pre X+1)': (C, An), 'A->B (pre X+1 -> pregao X+1)': (An, Bn)}


out = []
for m in ('v', 'n', 'vn'):
    pre, pr, pos = (L[k][m].values for k in ('pre', 'pr', 'pos'))
    real = pairs(pre, pr, pos)
    nul = {k: [] for k in real}
    for _ in range(3000):
        s1, s2, s3 = rng.integers(5, n - 5, 3)
        for k, (x, y) in pairs(np.roll(pre, s1), np.roll(pr, s2), np.roll(pos, s3)).items():
            ok = ~np.isnan(x) & ~np.isnan(y)
            nul[k].append(rho(x[ok], y[ok]) if ok.sum() > 20 else np.nan)
    for k, (x, y) in real.items():
        ok = ~np.isnan(x) & ~np.isnan(y)
        r0 = rho(x[ok], y[ok])
        nv = np.array(nul[k])
        nv = nv[~np.isnan(nv)]
        out.append(dict(variavel=m, par=k, n=ok.sum(), rho=r0, nulo_med=nv.mean(), nulo_lo=np.percentile(nv, 2.5),
                        nulo_hi=np.percentile(nv, 97.5), p_nulo=(np.abs(nv - nv.mean()) >= abs(r0 - nv.mean())).mean(),
                        rho_menos_nulo=r0 - nv.mean()))
ch = pd.DataFrame(out)
ch.to_csv(OUT / 'cadeia.csv', index=False, float_format='%.4f')
print(ch.to_string())
pc = []
dpB, dpC, gap = V.B0_dp.values, V.C0_dp.values, V.A_dp.values
gn = np.r_[gap[1:], np.nan]
for k, (x, y) in {'B->C': (dpB, dpC), 'C->A(gap seguinte)': (dpC, gn), 'A->B (gap D+1 -> pregao D+1)': (gn, np.r_[dpB[1:], np.nan])}.items():
    ok = ~np.isnan(x) & ~np.isnan(y)
    r0 = rho(x[ok], y[ok])
    nv = [rho(x[ok], np.roll(y[ok], s)) for s in range(5, ok.sum() - 5)]
    pc.append(dict(par=k, n=ok.sum(), rho=r0, p_shift=(np.abs(nv) >= abs(r0)).mean()))
pc = pd.DataFrame(pc)
pc.to_csv(OUT / 'cadeia_preco.csv', index=False, float_format='%.4f')
print(pc)

# (c) razao x componentes: beta do numerador e do denominador (regressao em ranks), para os 3 estagios operaveis
z = lambda a: (a - a.mean()) / a.std()
cc = []
for g, (a, b) in {'A': ('pre', 'pos'), 'B1': ('pr', 'pre'), 'C1': ('pos', 'pr')}.items():
    for m, nm in (('v', 'vol'), ('n', 'neg'), ('vn', 'vn')):
        if g == 'A':
            num, den = L[a][m].values, L[b][m].shift().values
        else:
            num, den = L[a][m].shift().values, L[b][m].shift().values
        for t in Y.columns:
            y = Y[t].values
            ok = ~np.isnan(num) & ~np.isnan(den) & ~np.isnan(y)
            k = ok.sum()
            rn, rd, ry = rankdata(num[ok]), rankdata(den[ok]), rankdata(y[ok])
            b0 = np.linalg.lstsq(np.c_[np.ones(k), z(rn), z(rd)], z(ry), rcond=None)[0]
            res_ = {}
            for idx, nmc in ((1, 'num'), (2, 'den')):
                bs = []
                for _ in range(2000):
                    cols_ = [z(rn), z(rd)]
                    cols_[idx - 1] = cols_[idx - 1][rng.permutation(k)]
                    bs.append(np.linalg.lstsq(np.c_[np.ones(k), *cols_], z(ry), rcond=None)[0][idx])
                bsh = []
                for s_ in range(5, k - 5):
                    cols_ = [z(rn), z(rd)]
                    cols_[idx - 1] = np.roll(cols_[idx - 1], s_)
                    bsh.append(np.linalg.lstsq(np.c_[np.ones(k), *cols_], z(ry), rcond=None)[0][idx])
                res_[nmc] = max((np.abs(bs) >= abs(b0[idx])).mean(), (np.abs(bsh) >= abs(b0[idx])).mean())
            cc.append(dict(estagio=g, var=nm, alvo=t, n=k, rho_razao=rho(num[ok] - den[ok], y[ok]), rho_num=rho(num[ok], y[ok]),
                           rho_den=rho(den[ok], y[ok]), beta_num=b0[1], beta_den=b0[2], p_num=res_['num'], p_den=res_['den']))
cc = pd.DataFrame(cc)
cc['q_num'] = bh(cc.p_num)
cc['q_den'] = bh(cc.p_den)
cc.to_csv(OUT / 'razao_vs_nivel.csv', index=False, float_format='%.4f')
print(cc.to_string())

# (d) vn relativo: tercis
dd_ = []
for c in ('A_vn', 'B1_vn', 'C1_vn'):
    x = V[c].values
    for t in ('var', 'absvar', 'amp', 'pr_vol'):
        y = Y[t].values
        ok = ~np.isnan(x) & ~np.isnan(y)
        xs, ys = x[ok], y[ok]
        lo, hi = np.percentile(xs, [33.3, 66.7])
        a, bb = ys[xs <= lo], ys[xs >= hi]
        diff = bb.mean() - a.mean()
        nv = []
        for _ in range(5000):
            yy = ys[rng.permutation(len(ys))]
            nv.append(yy[xs >= hi].mean() - yy[xs <= lo].mean())
        dd_.append(dict(pred=c, alvo=t, n_baixo=len(a), n_alto=len(bb), media_baixo=a.mean(), media_alto=bb.mean(), dif=diff,
                        p=(np.abs(nv) >= abs(diff)).mean(), sd_alvo=ys.std()))
dd_ = pd.DataFrame(dd_)
dd_.to_csv(OUT / 'vn_tercis.csv', index=False, float_format='%.3f')
print(dd_.to_string())
