import pickle, warnings, pandas as pd, numpy as np
warnings.filterwarnings("ignore")
import grid, rules
D = grid.get_data(); grid._cache = {}
out = []
for fam in rules.FAMS:
    for c in rules.period_cells(fam):
        for w in (2, 3):
            e = grid.eval_cell(D, c, w, False); e['w'] = w; out.append(e)
pickle.dump(out, open('perconf.pkl', 'wb'))
r = pd.DataFrame(out)
g = r[r.value.str.match(r'P\d+/\d+/\d+$')]
print(g.groupby(['axis', 'w']).agg(cel=('n', 'size'), pos=('mean', lambda s: (s > 0).sum()), esp=('mean', 'mean'), n=('n', 'median')).round(1).to_string())
