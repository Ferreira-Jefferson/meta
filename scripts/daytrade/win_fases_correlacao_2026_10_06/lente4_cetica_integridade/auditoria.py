"""Lente 4 - auditoria de dado e vieses mecanicos (WIN fases). Reprodutivel: python auditoria.py"""
import numpy as np, pandas as pd
from statistics import NormalDist
_N=NormalDist()
class stats:
    class norm:
        isf=staticmethod(lambda p:_N.inv_cdf(1-p))
        ppf=staticmethod(lambda p:_N.inv_cdf(p))
    @staticmethod
    def spearmanr(a,b):
        a=pd.Series(np.asarray(a)).rank().values; b=pd.Series(np.asarray(b)).rank().values
        r=np.corrcoef(a,b)[0,1]
        return r,float('nan')
    @staticmethod
    def kurtosis(s): return pd.Series(s).kurt()
    @staticmethod
    def kruskal(*g):
        # estatistica H com p por permutacao (5000)
        allv=np.concatenate(g); rk=pd.Series(allv).rank().values; sizes=[len(x) for x in g]; N=len(allv)
        def H(r):
            i=0;t=0
            for k in sizes: t+=r[i:i+k].sum()**2/k; i+=k
            return 12/(N*(N+1))*t-3*(N+1)
        h=H(rk); rr=np.random.default_rng(1); c=sum(H(rr.permutation(rk))>=h for _ in range(5000))
        return h,(c+1)/5001
rng = np.random.default_rng(42)
R = 'C:/Users/Jeffe/Documents/study/meta/'
d = pd.read_csv(R + 'data/win_fases_pregao_6m.csv', sep=';', encoding='utf-8-sig')
d['data'] = pd.to_datetime(d.data)
d = d.set_index('data')
d['gap'] = d.pre_preco_fechamento - d.pos_preco_fechamento.shift()
d['dpreg'] = d.pregao_preco_fechamento - d.pregao_preco_inicio
d['dpos'] = d.pos_preco_fechamento - d.pregao_preco_fechamento
d['rng'] = d.pregao_maxima - d.pregao_minima
for f in ['pre', 'pregao', 'pos']:
    d[f'{f}_vn'] = d[f'{f}_volume'] / d[f'{f}_negocios'].replace(0, np.nan)


def pct(s):
    return s / s.shift() - 1


def sp(a, b):
    m = a.notna() & b.notna()
    return stats.spearmanr(a[m], b[m])[0] if m.sum() > 5 else np.nan


out = []


def P(*a, end='\n'):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    out.append(s)


P('## A. Reversao a media mecanica de delta% (n dias =', len(d), ')')
P('serie | rho1 niveis (real) | rho1 delta% real | rho1 delta% sob embaralhamento: media [p2.5,p97.5] | rho(delta%_D, nivel_D-1) real | nulo media')
rows = []
for f in ['pre', 'pregao', 'pos']:
    for v in ['volume', 'negocios', 'vn']:
        c = f'{f}_{v}'
        lv = d[c].copy()
        if f == 'pre':
            lv = lv.replace(0, np.nan)
        dp = pct(lv)
        r_lv = sp(lv, lv.shift())
        r_dp = sp(dp, dp.shift())
        r_lvl = sp(dp, lv.shift())
        nul = []
        nul2 = []
        x = lv.values.copy()
        for _ in range(2000):
            y = pd.Series(rng.permutation(x), index=lv.index)
            q = pct(y)
            nul.append(sp(q, q.shift()))
            nul2.append(sp(q, y.shift()))
        nul = np.array(nul)
        nul2 = np.array(nul2)
        P(f'{c} | {r_lv:+.3f} | {r_dp:+.3f} | {nul.mean():+.3f} [{np.percentile(nul,2.5):+.3f},{np.percentile(nul,97.5):+.3f}] | {r_lvl:+.3f} | {nul2.mean():+.3f}')
        rows.append((c, r_lv, r_dp, nul.mean(), r_lvl, nul2.mean()))
pd.DataFrame(rows, columns=['serie', 'rho1_nivel', 'rho1_delta', 'rho1_delta_nulo', 'rho_delta_nivelD-1', 'nulo']).to_csv('A_reversao_mecanica.csv', index=False)

P('\n## A2. Delta pos(D) vs gap(D+1): termo comum call_D (mecanico negativo)')
x = d.dpos
y = d.gap.shift(-1)
g10 = d.gap.drop(pd.Timestamp('2026-10-05'))
P('Spearman real', round(sp(x, y), 3), ' Pearson', round(x.corr(y), 3), ' desvio dpos', round(x.std(), 1), ' desvio gap', round(d.gap.std(), 1), ' desvio gap sem 10-05', round(g10.std(), 1))
P('corr mecanico esperado se o resto do gap fosse independente = -sd(dpos)/sd(gap)=', round(-x.std() / d.gap.std(), 3), '; sem 10-05:', round(-x.std() / g10.std(), 3))
P('call-fechamento: media', round(d.dpos.mean(), 1), 'sd', round(d.dpos.std(), 1), 'pts; |media|', round(d.dpos.abs().mean(), 1))

P('\n## B. volume x amplitude (por construcao)')
for a, b in [('pregao_volume', 'rng'), ('pregao_negocios', 'rng'), ('pregao_volume', 'pregao_negocios')]:
    P(a, 'x', b, 'Spearman', round(sp(d[a], d[b]), 3))
ad = d.dpreg.abs()
P('pregao_volume x |dpreg| Spearman', round(sp(d.pregao_volume, ad), 3))
rk = d[['pregao_volume', 'rng', 'pregao_negocios']].rank()


def res(y, x):
    b = np.polyfit(x, y, 1)
    return y - np.polyval(b, x)


P('volume x range | negocios (parcial em ranks)', round(np.corrcoef(res(rk.pregao_volume, rk.pregao_negocios), res(rk.rng, rk.pregao_negocios))[0, 1], 3))
P('dvol%(pregao)_D x rng_D', round(sp(pct(d.pregao_volume), d.rng), 3), ' | dvol%_D x |dpreg|_D', round(sp(pct(d.pregao_volume), ad), 3))
P('amplitude_D x volume_D-1 (operavel, sem termo comum)', round(sp(d.rng, d.pregao_volume.shift()), 3), '| amplitude_D x amplitude_D-1', round(sp(d.rng, d.rng.shift()), 3))

P('\n## C. razao de razoes - dvn% e outliers')
dv = pct(d.pregao_volume)
dn = pct(d.pregao_negocios)
dvn = pct(d.pregao_vn)
P('Spearman dV%xdN%', round(sp(dv, dn), 3), ' dV%xdVN%', round(sp(dv, dvn), 3), ' dN%xdVN%', round(sp(dn, dvn), 3))
for nm, s in [('dV% pregao', dv), ('dN% pregao', dn), ('dVN% pregao', dvn), ('dV% pre', pct(d.pre_volume.replace(0, np.nan))), ('dN% pre', pct(d.pre_negocios.replace(0, np.nan))), ('dVN% pre', pct(d.pre_vn)), ('dV% pos', pct(d.pos_volume)), ('dVN% pos', pct(d.pos_vn))]:
    s = s.dropna()
    z = (s - s.mean()) / s.std()
    P(f'{nm}: n={len(s)} media {s.mean()*100:.1f}% sd {s.std()*100:.1f}% curtose {stats.kurtosis(s):.1f} max {s.max()*100:.0f}% min {s.min()*100:.0f}% |z|max {z.abs().max():.1f} ({z.abs().idxmax().date()})')
P('Pearson vs Spearman (dVN%_pos x dV%_pos): ', round(pct(d.pos_vn).corr(pct(d.pos_volume)), 3), round(sp(pct(d.pos_vn), pct(d.pos_volume)), 3))
P('Pearson vs Spearman (dV%_pre x dV%_pregao): ', round(pct(d.pre_volume).corr(pct(d.pregao_volume)), 3), round(sp(pct(d.pre_volume), pct(d.pregao_volume)), 3))

P('\n## D. calendario')
dw = d.assign(dow=d.index.dayofweek)
P('pregao_volume medio (mi) por dow:', dw.groupby('dow').pregao_volume.mean().div(1e6).round(2).to_dict(), ' Kruskal p=', round(stats.kruskal(*[g.pregao_volume.values for _, g in dw.groupby('dow')])[1], 4))
P('amplitude media por dow:', dw.groupby('dow').rng.mean().round(0).to_dict(), ' Kruskal p=', round(stats.kruskal(*[g.rng.values for _, g in dw.groupby('dow')])[1], 4))
P('|gap| mediano por dow:', dw.groupby('dow').gap.apply(lambda s: s.abs().median()).round(0).to_dict())
P('delta% vol pregao medio por dow (%):', dw.assign(x=pct(d.pregao_volume)).groupby('dow').x.mean().mul(100).round(1).to_dict())
rolls = ['2026-04-15', '2026-06-17', '2026-08-12']
for r in rolls:
    i = d.index.get_loc(pd.Timestamp(r))
    w = d.pregao_volume.iloc[i - 2:i + 3] / 1e6
    P('volume pregao (mi) D-2..D+2 de', r, [round(v, 1) for v in w], ' dV%(D)=', round(pct(d.pregao_volume).iloc[i] * 100, 1))
hol = ['2026-04-22', '2026-05-04', '2026-06-05', '2026-09-08']
P('dias pos-feriado: gap', d.loc[hol, 'gap'].tolist(), ' pregao_volume(mi)', (d.loc[hol, 'pregao_volume'] / 1e6).round(1).tolist(), ' (media geral', round(d.pregao_volume.mean() / 1e6, 1), ')')
exr = [pd.Timestamp(x) for x in rolls + ['2026-10-05']]
P('gap (pts) media/sd todos', round(d.gap.mean(), 0), round(d.gap.std(), 0), '| sem rolagens+10-05', round(d.gap.drop(exr).mean(), 0), round(d.gap.drop(exr).std(), 0))
ex = [pd.Timestamp(x) for x in rolls + ['2026-10-05', '2026-07-31', '2026-09-24']]
dd = d.drop(ex)
P('Spearman gap x dpreg (todos) ', round(sp(d.gap, d.dpreg), 3), '| sem rolagens+10-05+07-31+09-24:', round(sp(dd.gap, dd.dpreg), 3), 'n=', len(dd))
P('Pearson gap x dpreg todos', round(d.gap.corr(d.dpreg), 3), ' sem:', round(dd.gap.corr(dd.dpreg), 3))


def _pv(a, b):
    # p aprox. do Spearman: z de Fisher com var (1+r^2/2)/(n-3)
    r = stats.spearmanr(a, b)[0]
    z = np.arctanh(r) / np.sqrt((1 + r * r / 2) / (len(a) - 3))
    return 2 * (1 - _N.cdf(abs(z)))


def mde(n, alpha, power=.8):
    za = stats.norm.isf(alpha / 2)
    zb = stats.norm.ppf(power)
    r = .0
    for _ in range(50):
        r = np.tanh((za + zb) * np.sqrt((1 + r * r / 2) / (n - 3)))
    return r


P('\n## E. poder (Spearman; Fisher z com var (1+rho^2/2)/(n-3))')
for n in [126, 63, 100]:
    P(f'n={n}: |rho| min p/ 80% poder  alpha=.05: {mde(n,.05):.3f} | alpha=.05/100 (limiar do 1o rank do BH com 100 testes): {mde(n,.0005):.3f} | alpha=.05/20: {mde(n,.0025):.3f} | alpha=.01: {mde(n,.01):.3f}')
P('rho minimo p/ p=0.05 em n=126:', round(np.tanh(1.96 / np.sqrt(123)), 3), '| n=63:', round(np.tanh(1.96 / np.sqrt(60)), 3), '| p=5e-4 n=126:', round(np.tanh(stats.norm.isf(2.5e-4) / np.sqrt(123)), 3))
for rho in [.15, .20, .25, .30, .35]:
    for n in [126, 63]:
        cnt = 0
        cnt2 = 0
        N = 2000
        for _ in range(N):
            z = rng.standard_normal((n, 2))
            yy = rho * z[:, 0] + np.sqrt(1 - rho ** 2) * z[:, 1]
            p = _pv(z[:, 0], yy)
            cnt += p < .05
            cnt2 += p < 5e-4
        P(f'poder MC rho={rho} n={n}: alpha .05 -> {cnt/N:.2f}; alpha 5e-4 -> {cnt2/N:.2f}')
P('P(>=1 falso positivo em 100 testes nulos a .05)=', round(1 - .95 ** 100, 3))
P('autocorr lag1 niveis (volume pregao, amplitude, |gap|):', round(sp(d.pregao_volume, d.pregao_volume.shift()), 2), round(sp(d.rng, d.rng.shift()), 2), round(sp(d.gap.abs(), d.gap.abs().shift()), 2))
open('auditoria_stdout.txt', 'w', encoding='utf-8').write('\n'.join(out))
