import pickle, sys, numpy as np, pandas as pd
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500)


def prep(rows):
    r = pd.DataFrame(rows)
    p = r.value.str.split('|', expand=True); p.columns = ['par', 'breach', 'x', 'trend', 'var', 'stop', 'K']
    r = pd.concat([r, p], axis=1)
    r['fam'] = r.par + '|' + r.breach + '|' + r.trend + '|' + r['var'] + '|' + r.stop
    return r.set_index('value')


def fam_stats(r):
    r = r.copy(); r['pnl'] = r['mean'].fillna(0) * r.n
    g = r.groupby('fam')
    out = pd.DataFrame(dict(cel=g.size(), pos=g['mean'].apply(lambda s: (s > 0).sum()), n=g.n.sum(),
                            wmean=g.pnl.sum() / g.n.sum(), nmin=g.n.min()))
    return out


real = prep(pickle.load(open('res_desc2.pkl', 'rb')))
F = fam_stats(real)
nul = pickle.load(open(sys.argv[1], 'rb'))
draws = sorted(nul)
print('sorteios nulo2:', len(draws))
Fn = []; zc = {}
for sd in draws:
    rn = prep(nul[sd]); Fn.append(fam_stats(rn))
    for v, m in rn['mean'].items(): zc.setdefault(v, []).append(m)
zm = pd.DataFrame(zc).T
real['nul_mean'] = zm.mean(1); real['nul_sd'] = zm.std(1); real['z'] = (real['mean'] - real.nul_mean) / real.nul_sd
F['nul_wmean'] = pd.concat([f.wmean for f in Fn], axis=1).mean(1)
F['pass'] = (F.pos >= 10) & (F.wmean > 0) & (F.nmin >= 30)
cnt_null = [int(((f.pos >= 10) & (f.wmean > 0) & (f.nmin >= 30)).sum()) for f in Fn]
print(f'familias (12 celulas x,K) que passam [>=10/12 positivas, media ponderada>0, n>=30 em todas]: reais {int(F["pass"].sum())} de {len(F)}; nulo em media {np.mean(cnt_null):.1f} (min {min(cnt_null)}, max {max(cnt_null)})')
for th in (10, 11, 12):
    c = [int(((f.pos >= th) & (f.wmean > 0) & (f.nmin >= 30)).sum()) for f in Fn]
    print(f'  >= {th}/12: reais {int(((F.pos >= th) & (F.wmean > 0) & (F.nmin >= 30)).sum())}; nulo {np.mean(c):.1f} (max {max(c)})')
# p da familia: fracao de sorteios do nulo com wmean >= real, na mesma familia
WN = pd.concat([f.wmean for f in Fn], axis=1)
F['p_fam'] = [(WN.loc[k].values >= F.loc[k, 'wmean']).mean() for k in F.index]
F['z_fam'] = (F.wmean - WN.mean(1)) / WN.std(1)
print(F[F['pass']].sort_values('z_fam', ascending=False).round(2).to_string())
F.to_pickle('fam.pkl'); real.to_pickle('real2_com_nulo.pkl')
# nulo das 240 familias: quantas familias com p_fam<=0.05 sob o proprio nulo (leave-one-out aproximado)
print('familias com p_fam<=0.05 (real):', int((F.p_fam <= 0.05).sum()), 'de', len(F), '; esperado por acaso ~', round(0.05 * len(F), 1))
