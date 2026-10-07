"""Estudo WIN: hipoteses expandidas sobre memoria de curto prazo. Descritivo."""
import numpy as np, pandas as pd, math, sys, warnings
warnings.filterwarnings('ignore')


class _S: pass


def _pn(z): return math.erfc(abs(z) / math.sqrt(2))


class _R:
    def __init__(s, p): s.pvalue = p


def _binom(k, n, p0):
    if n == 0: return _R(1.0)
    z = max(abs(k - n * p0) - 0.5, 0) / math.sqrt(n * p0 * (1 - p0)); return _R(_pn(z))


def _spear(a, b):
    r = pd.Series(np.asarray(a)).rank().corr(pd.Series(np.asarray(b)).rank()); n = len(a)
    return r, _pn(r * math.sqrt((n - 2) / (1 - r * r)))


def _tind(a, b, equal_var=False):
    t = (a.mean() - b.mean()) / math.sqrt(a.var() / len(a) + b.var() / len(b)); return t, _pn(t)


def _trel(a, b):
    d = a - b; t = d.mean() / (d.std() / math.sqrt(len(d))); return t, _pn(t)


stats = _S(); stats.binomtest = _binom; stats.spearmanr = _spear; stats.ttest_ind = _tind; stats.ttest_rel = _trel
D = r'C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5'
OUT = r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_estudo_direcao_2026_10_04'
rng = np.random.default_rng(7)


def load(f):
    d = pd.read_csv(f'{D}\\{f}', sep='\t')
    d.columns = ['date', 'time', 'o', 'h', 'l', 'c', 'tv', 'v', 'sp']
    return d


def days(d, minbars=500):
    out = []
    for dt, g in d.groupby('date', sort=True):
        if len(g) < minbars:
            continue
        t = g['time'].values
        o, h, l, c, tv = (g[k].values.astype(float) for k in ['o', 'h', 'l', 'c', 'tv'])
        i10 = np.searchsorted(t, '10:00:00') - 1
        tp = (h + l + c) / 3
        out.append(dict(date=pd.Timestamp(dt.replace('.', '-')), O=o[0], H=h.max(), L=l.min(), C=c[-1],
                        vol=tv.sum(), c1h=c[i10], ih=int(h.argmax()), il=int(l.argmin()), i10=i10,
                        vwap=(tp * tv).sum() / max(tv.sum(), 1), last30=c[-1] - c[-31],
                        o_=o, h_=h, l_=l, c_=c, n=len(g)))
    return out


win = days(load('WIN@D_M1_202110010900_202610011717.csv'))
wdo = days(load('WDO@D_M1_202109290900_202609291020.csv'))
strip = lambda L: pd.DataFrame([{k: v for k, v in x.items() if not k.endswith('_')} for x in L]).set_index('date')
df = strip(win)
wd = strip(wdo)
df['rng'] = df.H - df.L
df['ret'] = df.C - df.O
df['atr'] = df.rng.rolling(14).mean().shift(1)
df['rn'] = df.rng / df.atr
df['rt'] = df.ret / df.atr
df['gap'] = (df.O - df.C.shift(1)) / df.atr
df['h1'] = (df.c1h - df.O) / df.atr
df['rest'] = (df.C - df.c1h) / df.atr
df['prev_rt'] = df.rt.shift(1)
df['prev_rn'] = df.rn.shift(1)
df['prev_last30'] = (df.last30 / df.atr).shift(1)
df['relvol'] = (df.vol / df.vol.rolling(20).mean().shift(1)).shift(1)
df['IS'] = df.index <= '2024-12-31'
wd['rt'] = (wd.C - wd.O) / (wd.H - wd.L).rolling(14).mean().shift(1)
df['wdo_prev'] = wd.rt.shift(1).reindex(df.index)
df['wdo_same'] = wd.rt.reindex(df.index)
# wdo_prev: dia anterior do WDO (pela serie do WDO), alinhado por data de WIN
df = df.dropna(subset=['atr', 'prev_rt', 'relvol'])
print('dias', len(df), 'IS', df.IS.sum(), 'OOS', (~df.IS).sum(), flush=True)

rows = []


def wil(k, n):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n; z = 1.96; den = 1 + z * z / n
    c = (p + z * z / 2 / n) / den
    hw = z * math.sqrt(p * (1 - p) / n + z * z / 4 / n / n) / den
    return c - hw, c + hw


def fmt(x, d=3):
    return 'nan' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.{d}f}'.replace('.', ',')


def add(h, tipo, w, n, medida, valor, nulo, ic, p):
    rows.append(dict(hipotese=h, tipo=tipo, janela=w, n=n, medida=medida, valor=fmt(valor), nulo=fmt(nulo),
                     ic95=ic, p=fmt(p, 4), sig=bool(p < 0.05), _v=valor - nulo))


def sgn_row(h, tipo, w, xs, ys, lbl, nulo_ref=None):
    ok = (xs != 0) & (ys != 0) & xs.notna() & ys.notna()
    xs = xs[ok]; ys = ys[ok]; n = len(xs); k = int((xs == ys).sum())
    px = (xs > 0).mean(); py = (ys > 0).mean()
    nulo = px * py + (1 - px) * (1 - py) if nulo_ref is None else nulo_ref
    lo, hi = wil(k, n)
    add(h, tipo, w, n, lbl, k / n, nulo, f'[{fmt(lo)};{fmt(hi)}]', stats.binomtest(k, n, nulo).pvalue)


def hit(h, tipo, x, y, lbl, mask=None):
    for w, m in (('IS', df.IS), ('OOS', ~df.IS)):
        if mask is not None:
            m = m & mask
        sgn_row(h, tipo, w, np.sign(x[m]), np.sign(y[m]), lbl)


def corr(h, tipo, x, y, lbl):
    for w, m in (('IS', df.IS), ('OOS', ~df.IS)):
        a = x[m]; b = y[m]; ok = a.notna() & b.notna(); a = a[ok]; b = b[ok]; n = len(a)
        r, p = stats.spearmanr(a, b)
        se = 1 / math.sqrt(n - 3); z = np.arctanh(r)
        add(h, tipo, w, n, lbl, r, 0.0, f'[{fmt(np.tanh(z - 1.96 * se))};{fmt(np.tanh(z + 1.96 * se))}]', p)


def meandiff(h, tipo, mask, y, lbl):
    for w, m in (('IS', df.IS), ('OOS', ~df.IS)):
        a = y[m & mask].dropna(); b = y[m & ~mask].dropna()
        d = a.mean() - b.mean(); se = math.sqrt(a.var() / len(a) + b.var() / len(b))
        t, p = stats.ttest_ind(a, b, equal_var=False)
        add(h, tipo, w, len(a), lbl, a.mean(), b.mean(), f'dif [{fmt(d - 1.96 * se)};{fmt(d + 1.96 * se)}]', p)


# H1 primeira hora -> resto do dia
hit('H1 sinal 1a hora -> sinal resto do dia', 'DIRECAO', df.h1, df.rest, 'P(concorda)')
corr('H1b 1a hora (ATR) -> resto (ATR)', 'DIRECAO', df.h1, df.rest, 'spearman')
conc = np.sign(df.h1) == np.sign(df.prev_rt)
hit('H1c 1a hora CONCORDA com D-1 -> resto continua', 'DIRECAO', df.h1, df.rest, 'P(concorda)', mask=conc)
hit('H1c 1a hora DISCORDA de D-1 -> resto continua', 'DIRECAO', df.h1, df.rest, 'P(concorda)', mask=~conc)
# H2 NR7/NR4
rg = df.rng
nr7 = (rg.rolling(7).min() == rg).shift(1).fillna(False).astype(bool)
meandiff('H2 NR7(D-1) -> range(D)/ATR (nulo=nao-NR7)', 'VOLATILIDADE', nr7, df.rn, 'media rn')
nr4 = (rg.rolling(4).min() == rg).shift(1).fillna(False).astype(bool)
meandiff('H2b NR4(D-1) -> range(D)/ATR (nulo=nao-NR4)', 'VOLATILIDADE', nr4, df.rn, 'media rn')
# H3 persistencia
corr('H3 range(D-1)/ATR -> range(D)/ATR', 'VOLATILIDADE', df.prev_rn, df.rn, 'spearman')
corr('H3b |gap|/ATR -> range(D)/ATR', 'VOLATILIDADE', df.gap.abs(), df.rn, 'spearman')
# H4 ultimos 30 min
hit('H4a ult.30min D-1 -> sinal do gap D', 'DIRECAO', df.prev_last30, df.gap, 'P(concorda)')
hit('H4b ult.30min D-1 -> sinal 1a hora D', 'DIRECAO', df.prev_last30, df.h1, 'P(concorda)')
hit('H4c ult.30min D-1 -> sinal dia D', 'DIRECAO', df.prev_last30, df.rt, 'P(concorda)')
# H6 horario do extremo
lo1 = df.il <= df.i10
hi1 = df.ih <= df.i10
for nm, msk, alvo, lb in (('minima do dia na 1a hora', lo1, df.ret > 0, 'alta'), ('maxima do dia na 1a hora', hi1, df.ret < 0, 'baixa')):
    for w, m in (('IS', df.IS), ('OOS', ~df.IS)):
        s = msk[m]; y = alvo[m]; k = int(y[s].sum()); n = int(s.sum()); nulo = y.mean()
        lo, hi = wil(k, n)
        add(f'H6 {nm} -> P({lb} no dia)', 'DIRECAO', w, n, 'P', k / n, nulo, f'[{fmt(lo)};{fmt(hi)}]', stats.binomtest(k, n, nulo).pvalue)
# H7 WDO
sub = df.dropna(subset=['wdo_prev', 'wdo_same'])
for h, xc, lb in (('H7a WDO(D-1) -> WIN(D) defasada (esperado: discordar)', 'wdo_prev', 'P(concorda)'),
                  ('H7b WDO(D) vs WIN(D) mesmo dia (referencia)', 'wdo_same', 'P(concorda)')):
    for w, m in (('IS', sub.IS), ('OOS', ~sub.IS)):
        s = sub[m]
        sgn_row(h, 'DIRECAO', w, np.sign(s[xc]), np.sign(s.rt), lb)
# H8 pos-dia extremo (retorno em ATR do range 14d)
for thr in (1.0, 1.5):
    msk = df.prev_rt.abs() > thr
    for w, m in (('IS', df.IS), ('OOS', ~df.IS)):
        base = df[m]
        nulo = (np.sign(base.rt) == np.sign(base.prev_rt)).mean()
        s = df[m & msk]
        sgn_row(f'H8 pos-dia |ret|>{thr}ATR -> D tem mesmo sinal (nulo=todos os dias)', 'DIRECAO', w, np.sign(s.prev_rt), np.sign(s.rt), 'P(mesmo sinal)', nulo_ref=nulo)
cum5 = df.rt[::-1].rolling(5).sum()[::-1]  # soma D..D+4
msk = df.prev_rt.abs() > 1.0
for w, m in (('IS', df.IS), ('OOS', ~df.IS)):
    ok = cum5.notna()
    base = df[m & ok]
    nulo = (np.sign(cum5[base.index]) == np.sign(base.prev_rt)).mean()
    s = df[m & ok & msk]
    sgn_row('H8b pos-dia |ret|>1ATR -> 5 dias seguintes (D..D+4) mesmo sinal', 'DIRECAO', w, np.sign(s.prev_rt), np.sign(cum5[s.index]), 'P(mesmo sinal)', nulo_ref=nulo)
# H9 volume relativo D-1
corr('H9a volume rel D-1 -> range D/ATR', 'VOLATILIDADE', df.relvol, df.rn, 'spearman')
q = df.relvol.quantile([1 / 3, 2 / 3]).values
for nm, msk in (('vol D-1 alto (tercil sup)', df.relvol >= q[1]), ('vol D-1 baixo (tercil inf)', df.relvol <= q[0])):
    for w, m in (('IS', df.IS), ('OOS', ~df.IS)):
        base = df[m]
        nulo = (np.sign(base.rt) == np.sign(base.prev_rt)).mean()
        s = df[m & msk]
        sgn_row(f'H9b {nm} -> D segue sinal de D-1 (nulo=todos)', 'DIRECAO', w, np.sign(s.prev_rt), np.sign(s.rt), 'P(mesmo sinal)', nulo_ref=nulo)
# H5 niveis de D-1 vs espelho
pos = {x['date']: i for i, x in enumerate(win)}
res = {n: {'IS': [], 'OOS': []} for n in ['maxima', 'minima', 'fechamento', 'ponto medio', 'VWAP']}
for d in df.index:
    i = pos[d]
    if i == 0:
        continue
    p = win[i - 1]; x = win[i]; atr = df.atr[d]
    lv = {'maxima': p['H'], 'minima': p['L'], 'fechamento': p['C'], 'ponto medio': (p['H'] + p['L']) / 2, 'VWAP': p['vwap']}
    for nm, L in lv.items():
        dist = L - x['O']
        if abs(dist) < 0.05 * atr or abs(dist) > 3 * atr:
            continue

        def touch(Lv):
            up = Lv > x['O']
            hits = np.nonzero(x['h_'] >= Lv)[0] if up else np.nonzero(x['l_'] <= Lv)[0]
            if len(hits) == 0:
                return 0, np.nan
            t = hits[0]; e = min(t + 30, len(x['c_']) - 1)
            return 1, (-1 if up else 1) * (x['c_'][e] - Lv) / atr
        a, ra = touch(L); b, rb = touch(x['O'] - dist)
        res[nm]['IS' if df.IS[d] else 'OOS'].append((a, b, ra, rb))
for nm, dd in res.items():
    for w in ('IS', 'OOS'):
        arr = np.array(dd[w]); n = len(arr); a = arr[:, 0]; b = arr[:, 1]
        n10 = int(((a == 1) & (b == 0)).sum()); n01 = int(((a == 0) & (b == 1)).sum())
        p = stats.binomtest(n10, n10 + n01, 0.5).pvalue if n10 + n01 > 0 else 1
        se = math.sqrt(n10 + n01) / n
        dif = a.mean() - b.mean()
        add(f'H5 nivel D-1 {nm}: P(tocar em D) vs espelho', 'NIVEIS', w, n, 'P(toque) real', a.mean(), b.mean(), f'dif [{fmt(dif - 1.96 * se)};{fmt(dif + 1.96 * se)}]', p)
        both = (a == 1) & (b == 1)
        if both.sum() > 20:
            ra = arr[both, 2]; rb = arr[both, 3]; t, pp = stats.ttest_rel(ra, rb)
            d_ = ra - rb; se = d_.std() / math.sqrt(len(d_))
            add(f'H5r nivel D-1 {nm}: rejeicao 30min pos-toque (ATR) vs espelho', 'NIVEIS', w, int(both.sum()), 'rejeicao media', ra.mean(), rb.mean(), f'dif [{fmt(d_.mean() - 1.96 * se)};{fmt(d_.mean() + 1.96 * se)}]', pp)

R = pd.DataFrame(rows)


def sv(g):
    return len(g) == 2 and bool(g.sig.all()) and (np.sign(g._v) == np.sign(g._v.iloc[0])).all()


S = R.groupby('hipotese').apply(sv).rename('sobrevive')
R = R.merge(S, left_on='hipotese', right_index=True).drop(columns='_v')
R.to_csv(f'{OUT}\\e_hipoteses_expandidas.csv', sep=';', index=False, encoding='utf-8-sig')
pd.set_option('display.width', 250, 'display.max_colwidth', 75, 'display.max_rows', 500)
print(R[['hipotese', 'janela', 'n', 'valor', 'nulo', 'ic95', 'p', 'sobrevive']].to_string(index=False))
print('p-valores:', len(R), ' hipoteses:', R.hipotese.nunique(), ' esperado por acaso (5%):', round(len(R) * .05, 1), ' sig:', int(R.sig.sum()))
