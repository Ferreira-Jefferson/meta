import pandas as pd, numpy as np, io
def rankdata(a): return pd.Series(a).rank().values
def spearmanr(a, b): return (np.corrcoef(rankdata(a), rankdata(b))[0, 1],)
rng = np.random.default_rng(7)
NP = 5000
R = 'C:/Users/Jeffe/Documents/study/meta/'
d = pd.read_csv(R + 'data/win_fases_pregao_6m.csv', sep=';', encoding='utf-8-sig', parse_dates=['data']).set_index('data')
m = pd.read_parquet(R + 'data/comparativo_win_2026/m1_WIN$N.parquet')
t = m.index.time
m = m[(t >= pd.Timestamp('09:00').time()) & (t < pd.Timestamp('18:25').time())]
m5 = m.resample('5min', label='left', closed='left').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
m5['d'] = m5.index.normalize()
g = m5.groupby('d')

X = pd.DataFrame(index=d.index)
X['ret'] = d.pregao_preco_fechamento - d.pregao_preco_inicio
X['rng'] = d.pregao_maxima - d.pregao_minima
X['vol'] = np.log(d.pregao_volume)
X['neg'] = np.log(d.pregao_negocios)
X['vpn'] = d.pregao_volume / d.pregao_negocios
X['callvar'] = d.pos_preco_fechamento - d.pregao_preco_fechamento
X['callpct'] = X.callvar / d.pregao_preco_fechamento * 100
X['callvol'] = np.log(d.pos_volume)
X['closepos'] = (d.pregao_preco_fechamento - d.pregao_minima) / (d.pregao_maxima - d.pregao_minima)
l30 = []; l60 = []; f = {n: [] for n in (1, 3, 6, 12)}
for dt in d.index:
    if dt not in g.groups:
        l30.append(np.nan); l60.append(np.nan)
        for n in f: f[n].append(np.nan)
        continue
    b = g.get_group(dt); c = b.close
    pc_ = d.pregao_preco_fechamento[dt]
    def at(hhmm):
        k = pd.Timestamp(str(dt.date()) + ' ' + hhmm)
        return c[k] if k in c.index else np.nan
    l30.append(pc_ - at('17:50'))   # fecho do pregao (CSV) - close da barra M5 que fecha 17:55
    l60.append(pc_ - at('17:20'))
    first09 = b.index[0].hour == 9 and b.index[0].minute == 0
    for n in f: f[n].append(c.iloc[n - 1] - d.pregao_preco_inicio[dt] if len(c) >= n and first09 else np.nan)
X['l30'] = l30; X['l60'] = l60
T = pd.DataFrame(index=d.index)
T['gap'] = d.pre_preco_fechamento - d.pos_preco_fechamento.shift(1)
T['gap_pregopen'] = d.pregao_preco_inicio - d.pos_preco_fechamento.shift(1)
T['ret'] = X.ret; T['dir'] = np.sign(X.ret); T['rng'] = X.rng; T['vol'] = X.vol
for n in f: T[f'm5_{n}'] = f[n]
P = X[['ret', 'rng', 'vol', 'neg', 'vpn', 'callvar', 'callpct', 'callvol', 'closepos', 'l30', 'l60']].shift(1).add_prefix('d1_')

bad_all = {'2026-07-31', '2026-09-24', '2026-10-05'}
roll = ['2026-04-15', '2026-04-16', '2026-06-17', '2026-06-18', '2026-08-12', '2026-08-13']
gp = T.gap.abs().sort_values(ascending=False)
out = io.StringIO()
def W(s=''):
    print(s); out.write(s + '\n')
W('# Lente 2 - dia anterior (D-1) -> pregao de D\n')
W('Maiores |gap| (call D-1 -> leilao D): ' + ', '.join(f'{k.date()}:{v:.0f}' for k, v in gp.head(6).items()))

GAPT = ('gap', 'gap_pregopen')
ROLL = ['2026-04-15', '2026-06-17', '2026-08-12']
def mask(excl, gap=False):
    drop = set()
    base = ['2026-07-31', '2026-09-24'] + (['2026-10-05'] if excl else [])
    for s_ in base:
        tt = pd.Timestamp(s_); drop.add(tt)
        i = d.index.get_indexer([tt])[0]
        if i + 1 < len(d): drop.add(d.index[i + 1])
    if gap:
        for s_ in ROLL: drop.add(pd.Timestamp(s_))
    return ~d.index.isin(list(drop))

def perm(x, y):
    perm.last_circ = np.nan
    ok = ~(np.isnan(x) | np.isnan(y)); x = x[ok]; y = y[ok]
    if len(x) < 20 or np.std(x) == 0 or np.std(y) == 0: return np.nan, np.nan, len(x)
    rx = rankdata(x); ry = rankdata(y); r = np.corrcoef(rx, ry)[0, 1]
    n = len(x); zx = (rx - rx.mean()) / rx.std(); zy = (ry - ry.mean()) / ry.std()
    idx = np.argsort(rng.random((NP, n)), axis=1)
    ps = (zy[idx] @ zx) / n
    p1 = (1 + (np.abs(ps) >= abs(r)).sum()) / (NP + 1)
    sh = np.array([np.dot(np.roll(zy, k), zx) / n for k in range(1, n)])
    p2 = (1 + (np.abs(sh) >= abs(r)).sum()) / n
    perm.last_circ = p2
    return r, p1, n

def bh(p):
    p = np.array(p); o = np.argsort(p); q = np.empty(len(p)); pr = 1
    for k, i in enumerate(o[::-1]):
        rank = len(p) - k; pr = min(pr, p[i] * len(p) / rank); q[i] = pr
    return q

half = len(d) // 2
def run(excl, label):
    res = []
    for pc in P.columns:
        for tc in T.columns:
            x = P[pc].values.astype(float); y = T[tc].values.astype(float)
            mk = mask(excl, tc in GAPT or pc == 'd1_call_to_open_gap')
            sel = mk & ~np.isnan(x) & ~np.isnan(y)
            r, p, n = perm(x[sel], y[sel])
            h1 = sel.copy(); h1[half:] = False; h2 = sel.copy(); h2[:half] = False
            r1 = spearmanr(x[h1], y[h1])[0] if h1.sum() > 15 else np.nan
            r2 = spearmanr(x[h2], y[h2])[0] if h2.sum() > 15 else np.nan
            res.append(dict(pred=pc, alvo=tc, n=n, rho=r, p=p, p_circ=perm.last_circ, rho_h1=r1, rho_h2=r2))
    R_ = pd.DataFrame(res).dropna(subset=['p']); R_['pmax'] = R_[['p', 'p_circ']].max(axis=1); R_['q'] = bh(R_.p.values); R_['q_cons'] = bh(R_.pmax.values)
    R_['estavel'] = (np.sign(R_.rho_h1) == np.sign(R_.rho_h2)) & (R_[['rho_h1', 'rho_h2']].abs().min(axis=1) > 0.1)
    W(f'\n## Preditores D-1 x alvos de D ({label}); testes={len(R_)}; p<0.05 bruto={int((R_.p < .05).sum())} (acaso ~{len(R_) * .05:.0f}); q<0.10={int((R_.q < .1).sum())}; q_cons(max p embaralhado/circular)<0.10={int((R_.q_cons < .1).sum())}')
    W(R_.sort_values('p').head(15).round(3).to_string(index=False))
run(False, 'com 10-05'); run(True, 'sem 10-05')

W('\n## Linha de base: autocorrelacao do pregao (lag 1-5, permutacao, todos os dias)')
AC = []
for c in ['ret', 'rng', 'vol', 'neg']:
    s = X[c].values.astype(float)
    for L in range(1, 6):
        r, p, n = perm(s[:-L], s[L:]); AC.append(dict(serie=c, lag=L, n=n, rho=r, p=p))
A = pd.DataFrame(AC); A['q'] = bh(A.p.values); W(A.round(3).to_string(index=False))

def resid(y, x):
    b = np.polyfit(x, y, 1); return y - np.polyval(b, x)
rk = lambda s: rankdata(s)
W('\n## Efeito do call de D-1 controlando persistencia (rank parcial; sem dias problematicos)')
for pc, tc, ctrl in [('d1_callvol', 'vol', 'd1_vol'), ('d1_callvol', 'rng', 'd1_rng'), ('d1_vol', 'vol', None),
                     ('d1_callvar', 'gap', 'd1_ret'), ('d1_callpct', 'm5_6', 'd1_ret'), ('d1_callvar', 'ret', 'd1_ret')]:
    x = P[pc].values.astype(float); y = T[tc].values.astype(float); mk = mask(True, tc in GAPT)
    if ctrl:
        z = P[ctrl].values.astype(float); ok = mk & ~(np.isnan(x) | np.isnan(y) | np.isnan(z))
        xr = resid(rk(x[ok]), rk(z[ok])); yr = resid(rk(y[ok]), rk(z[ok])); r, p, n = perm(xr, yr)
    else:
        ok = mk & ~(np.isnan(x) | np.isnan(y)); r, p, n = perm(x[ok], y[ok])
    W(f'- {pc} -> {tc} | ctrl {ctrl}: n={n} rho={r:.3f} p={p:.4f}')

W('\n## Cadeia: continua ou reverte? (sem dias problematicos; pontos)')
Lk = [('pregao D-1 -> call D-1 [contemp.]', X.ret, X.callvar),
      ('call D-1 -> gap D (leilao)', X.callvar.shift(1), T.gap),
      ('pregao D-1 -> gap D', X.ret.shift(1), T.gap),
      ('gap D -> pregao D', T.gap, X.ret),
      ('call D-1 -> pregao D', X.callvar.shift(1), X.ret),
      ('pregao D-1 -> pregao D', X.ret.shift(1), X.ret)]
rows2 = []
for nm, a, b in Lk:
    a = a.values.astype(float); b = b.values.astype(float); mk = mask(True, 'gap' in nm)
    ok = mk & ~(np.isnan(a) | np.isnan(b)) & (a != 0) & (b != 0)
    cont = (np.sign(a[ok]) == np.sign(b[ok])).mean(); r, p, n = perm(a[ok], b[ok])
    rows2.append(dict(elo=nm, n=n, pct_continua=round(cont * 100, 1), rho=round(r, 3), p_perm=round(p, 4),
                      media_b_se_a_pos=round(b[ok][a[ok] > 0].mean(), 1), media_b_se_a_neg=round(b[ok][a[ok] < 0].mean(), 1)))
W(pd.DataFrame(rows2).to_string(index=False))
W('\n(R$ por contrato = pontos x 0,20)')
open(R + 'scripts/daytrade/win_fases_correlacao_2026_10_06/lente2_dia_anterior/RESULTADO.md', 'w', encoding='utf-8').write(out.getvalue())
