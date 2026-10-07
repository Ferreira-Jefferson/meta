import pickle, glob, sys, numpy as np, pandas as pd
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 600)
import grid

real = pd.DataFrame(pickle.load(open('res_desc.pkl', 'rb')))
cells = grid.all_cells()
# res_desc vem fora de ordem: reordena pelas chaves (axis, value) -- joint/heat tem valor unico por eixo
key = lambda a, v: f"{a}|{v}"
real['key'] = [key(a, v) for a, v in zip(real.axis, real.value)]
real = real.drop_duplicates('key').set_index('key')
nul = pickle.load(open(sys.argv[1] if len(sys.argv) > 1 else 'null_0_60.pkl', 'rb'))
draws = sorted(nul)
print('sorteios do nulo:', len(draws))
M = {}; T = {}
for sd in draws:
    d = {key(r['axis'], r['value']): r for r in nul[sd]}
    for k, r in d.items():
        M.setdefault(k, []).append(r['mean']); T.setdefault(k, []).append(r['t'])
nm = pd.DataFrame({k: v for k, v in M.items()}).T
nt = pd.DataFrame({k: v for k, v in T.items()}).T
real['nul_mean'] = nm.mean(1); real['nul_sd'] = nm.std(1)
real['z'] = (real['mean'] - real.nul_mean) / real.nul_sd
# p empirico por celula (t real >= t nulo)
real['p_t'] = [(nt.loc[k].values >= real.loc[k, 't']).mean() if np.isfinite(real.loc[k, 't']) else np.nan for k in real.index]
ok = real.n >= 30
for th in (1.5, 2.0, 2.5):
    cnt_real = int(((real.t >= th) & ok).sum())
    cnt_null = [((nt[c] >= th) & ok.reindex(nt.index)).sum() for c in nt.columns]
    print(f't>={th}: reais {cnt_real} de {int(ok.sum())} celulas (n>=30); no nulo em media {np.mean(cnt_null):.1f} (max {np.max(cnt_null)})')
# por eixo
cols = ['axis', 'value', 'n', 'win', 'be', 'mean', 'nul_mean', 'nul_sd', 'z', 't', 'p_t', 'ci_lo', 'ci_hi']
for ax in ['fast', 'mid', 'slow', 'kind', 'x', 'breach', 'ref_touch', 'trend', 'var', 'triple', 'par', 'Nstop', 'K', 'stop', 'entry', 'otim']:
    print(real[real.axis == ax][cols].round(3).to_string(index=False))
j = real[real.axis == 'joint'].copy()
print('joint', len(j), 'media real', j['mean'].mean(), 'nulo medio', j.nul_mean.mean(), 'celulas t>=2', (j.t >= 2).sum())
real.to_pickle('real_com_nulo.pkl')
