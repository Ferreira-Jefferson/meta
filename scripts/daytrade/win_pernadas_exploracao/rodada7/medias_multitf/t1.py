import time, grid, core, warnings
warnings.filterwarnings("ignore")
D = grid.get_data(); grid._cache = {}
cells = grid.all_cells(); print(len(cells))
t = time.time()
for c in cells[:3] + [c for c in cells if c['axis'] in ('par', 'kind', 'K')]:
    r = grid.eval_cell(D, c, 1, True)
    print(r['axis'], r['value'], {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k in ('n', 'nsig', 'nfill', 'ninv', 'nev', 'win', 'be', 'mean', 't', 'pv', 'pf', 'pnull', 'ci_lo', 'ci_hi')}, round(time.time() - t, 1), flush=True)
