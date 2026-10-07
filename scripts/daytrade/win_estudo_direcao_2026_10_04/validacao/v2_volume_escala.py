"""V2 - Validacao: "o passado prevê ESCALA (volatilidade), nao direcao".

CRITERIO DE VALIDADO (escrito ANTES de rodar; nao muda depois)
Todos os coeficientes sao de OLS em log(range_D/ATR14) (ou log do range semanal/mensal), com IC95 por bootstrap
de blocos (dia; semana quando o alvo e' diario dentro de semana). "Passa" = IC exclui 0 no sinal esperado (positivo).
Anos = 2022..2026 (5 anos). OOS 2025+ ja foi visto; a validacao vem de anos separados, WDO e controles.

H_VOL (volume relativo D-1 -> escala de D, incremental aos controles):
  (a) WIN amostra toda: coef de log(relvol20) > 0 com IC exclui 0 E ganho de R2 >= 0,005 sobre os controles
      (log ATR14 implicito no denominador, log range D-1/ATR, |gap D|/ATR, |ret D-1|/ATR, dia da semana);
  (b) ano a ano WIN: sinal positivo em >=4/5 anos E IC exclui 0 em >=3/5;
  (c) WDO: coef >0 com IC exclui 0 (amostra toda);
  (d) utilidade: razao media(range/ATR) tercil alto / baixo de relvol >= 1,10 no WIN e no WDO.
  VALIDADO = (a)(b)(c)(d) todas. INCONCLUSIVO = (a) passa e exatamente uma entre (b)(c)(d) falha. NAO VALIDADO = resto.
H_NORM: normalizacao 20d vs 60d vs z-score60: as tres dao coef>0 com IC excluindo 0 no WIN (VALIDADO se sim; senao NAO).
H_UTIL: relvol previsor de tamanho "melhor" que |gap|/ATR e range D-1/ATR se razao alto/baixo for maior que a de ambos (informativo).
H_SEMANA: log range semana W-1 -> log range semana W, controlando log ATR14 no inicio de W: coef>0 IC exclui 0 em WIN e WDO
  E sinal positivo em >=3/5 anos no WIN -> VALIDADO; so WIN toda a amostra -> INCONCLUSIVO; senao NAO.
  Idem para os dias de W (log rn_D ~ range W-1/ATR, controles diarios).
H_MES: log range mes M-1 -> M controlando log ATR14 no inicio do mes: coef>0 IC exclui 0 em WIN e WDO -> VALIDADO;
  em um so -> INCONCLUSIVO; senao NAO (n~60 meses: poder baixo, declarado).
H_NR: NR7 (e NR4) em D-1 -> expansao de D: coef de NR (dummy) em log(rn_D) com controles >0, IC exclui 0 no WIN toda amostra,
  positivo em >=4/5 anos, e WDO coef>0 IC exclui 0 -> VALIDADO; (a) passa e falha uma -> INCONCLUSIVO; senao NAO.
"""
import numpy as np, pandas as pd, sys, warnings
warnings.filterwarnings('ignore')
D = r'C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5'
OUT = r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_estudo_direcao_2026_10_04\validacao'
NB = 1000
rng_ = np.random.default_rng(11)


def f(x, n=3):
    return '' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.{n}f}'.replace('.', ',')


def load(fn):
    d = pd.read_csv(f'{D}\\{fn}', sep='\t')
    d.columns = ['date', 'time', 'o', 'h', 'l', 'c', 'tv', 'v', 'sp']
    d['date'] = pd.to_datetime(d['date'].str.replace('.', '-'))
    g = d.groupby('date')
    df = pd.DataFrame({'O': g.o.first(), 'H': g.h.max(), 'L': g.l.min(), 'C': g.c.last(), 'vol': g.tv.sum(), 'n': g.size()})
    df = df[df.n >= 500].copy()
    df['rng'] = df.H - df.L
    df['atr'] = df.rng.rolling(14).mean().shift(1)
    df['rn'] = df.rng / df.atr
    df['lrn'] = np.log(df.rn)
    df['gap'] = (df.O - df.C.shift(1)).abs() / df.atr
    df['pret'] = (df.C - df.O).abs().shift(1) / df.atr
    df['prn'] = df.rn.shift(1)
    df['lprn'] = np.log(df.prn)
    for k in (20, 60):
        m = df.vol.rolling(k).mean().shift(2)
        df[f'lrv{k}'] = np.log(df.vol.shift(1) / m)
    s = df.vol.rolling(60).std().shift(2)
    df['z60'] = (df.vol.shift(1) - df.vol.rolling(60).mean().shift(2)) / s
    for w in range(4):
        df[f'wd{w}'] = (df.index.dayofweek == w).astype(float)
    rr = df.rng
    df['nr7'] = (rr == rr.rolling(7).min()).shift(1).astype(float)
    df['nr4'] = (rr == rr.rolling(4).min()).shift(1).astype(float)
    df['year'] = df.index.year
    df['week'] = df.index.to_period('W')
    df['month'] = df.index.to_period('M')
    return df


def ols(y, X):
    X1 = np.column_stack([np.ones(len(y)), X])
    b = np.linalg.lstsq(X1, y, rcond=None)[0]
    r = y - X1 @ b
    r2 = 1 - (r ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return b, r2


def inc(d, base, extra, y='lrn', cluster=None, nb=NB):
    """coef de `extra`, IC95 bootstrap por bloco, delta R2."""
    cols = base + [extra] + [y] + ([cluster] if cluster else [])
    d = d.dropna(subset=cols)
    if len(d) < 15:
        return None
    Y = d[y].values
    Xb = d[base].values if base else np.zeros((len(d), 0))
    Xf = np.column_stack([Xb, d[extra].values])
    b, r2f = ols(Y, Xf)
    _, r2b = ols(Y, Xb)
    coef = b[-1]
    if cluster is None:
        groups = [np.array([i]) for i in range(len(d))]
    else:
        codes = pd.factorize(d[cluster])[0]
        groups = [np.where(codes == k)[0] for k in range(codes.max() + 1)]
    G = len(groups)
    bs = []
    for _ in range(nb):
        pick = rng_.integers(0, G, G)
        idx = np.concatenate([groups[k] for k in pick])
        try:
            bs.append(np.linalg.lstsq(np.column_stack([np.ones(len(idx)), Xf[idx]]), Y[idx], rcond=None)[0][-1])
        except Exception:
            pass
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(n=len(d), coef=coef, lo=lo, hi=hi, dR2=r2f - r2b, R2f=r2f, R2b=r2b, ok=lo > 0)


rows = []


def add(h, ativo, jan, r, extra=''):
    if r is None:
        return
    rows.append(dict(hip=h, ativo=ativo, janela=jan, n=r['n'], coef=f(r['coef']), ic_lo=f(r['lo']), ic_hi=f(r['hi']),
                     dR2=f(r['dR2'], 4), R2_com=f(r['R2f'], 4), R2_base=f(r['R2b'], 4), passa='sim' if r['ok'] else 'nao', obs=extra))
    print(h, ativo, jan, r['n'], f(r['coef']), f(r['lo']), f(r['hi']), f(r['dR2'], 4), 'PASSA' if r['ok'] else '-', flush=True)


CTRL = ['lprn', 'gap', 'pret', 'wd0', 'wd1', 'wd2', 'wd3']
data = {'WIN': load('WIN@D_M1_202110010900_202610011717.csv'), 'WDO': load('WDO@D_M1_202109290900_202609291020.csv')}
tert = []
sp = []
for a, df in data.items():
    print('====', a, len(df), flush=True)
    add('1 vol20 incremental', a, 'toda', inc(df, CTRL, 'lrv20'))
    add('1b vol20 sem controles', a, 'toda', inc(df, [], 'lrv20'))
    for c in ['lprn', 'gap', 'pret']:
        add(f'1c vol20 controlando so {c}', a, 'toda', inc(df, [c], 'lrv20'))
    add('2 vol60', a, 'toda', inc(df, CTRL, 'lrv60'))
    add('2 z60', a, 'toda', inc(df, CTRL, 'z60'))
    t = np.arange(len(df))
    lv = np.log(df.vol.values)
    sp.append(dict(ativo=a, trend_logvol_ano=f(np.polyfit(t, lv, 1)[0] * 252),
                   corr_lrv20_tempo=f(np.corrcoef(t[60:], df.lrv20.values[60:])[0, 1]),
                   corr_lrv60_tempo=f(np.corrcoef(t[60:], df.lrv60.values[60:])[0, 1])))
    print(a, 'tendencia', sp[-1], flush=True)
    for y in range(2022, 2027):
        add('3 vol20 ano', a, str(y), inc(df[df.year == y], CTRL, 'lrv20', nb=500))
    d4 = df.dropna(subset=['lrv20', 'gap', 'prn', 'rn'])
    for nome, col in [('relvol D-1', 'lrv20'), ('|gap|/ATR', 'gap'), ('range D-1/ATR', 'prn')]:
        q = d4[col].quantile([1 / 3, 2 / 3]).values
        tt = pd.cut(d4[col], [-np.inf, q[0], q[1], np.inf], labels=['baixo', 'medio', 'alto'])
        g = d4.groupby(tt).rn.agg(['mean', 'median', 'count'])
        rho = d4[col].rank().corr(d4.rn.rank())
        ra = []
        for y in range(2022, 2027):
            dy = d4[d4.year == y]
            ty = pd.cut(dy[col], [-np.inf, q[0], q[1], np.inf], labels=['b', 'm', 'a'])
            m = dy.groupby(ty).rn.mean()
            ra.append(m['a'] / m['b'])
        tert.append(dict(ativo=a, preditor=nome, media_baixo=f(g['mean']['baixo']), media_medio=f(g['mean']['medio']),
                         media_alto=f(g['mean']['alto']), mediana_baixo=f(g['median']['baixo']), mediana_alto=f(g['median']['alto']),
                         razao_alto_baixo=f(g['mean']['alto'] / g['mean']['baixo']), spearman=f(rho),
                         razao_por_ano_22_26=' / '.join(f(x, 2) for x in ra)))
        print(a, nome, tert[-1], flush=True)
    for nr in ('nr7', 'nr4'):
        dn = df.dropna(subset=['lrn', nr])
        print(a, nr, 'n NR', int(dn[nr].sum()), 'media rn NR/nao', f(dn[dn[nr] == 1].rn.mean()), f(dn[dn[nr] == 0].rn.mean()), flush=True)
        add(f'6 {nr} bruto', a, 'toda', inc(df, [], nr))
        add(f'6 {nr} controlado', a, 'toda', inc(df, CTRL, nr))
        for y in range(2022, 2027):
            add(f'6 {nr} controlado ano', a, str(y), inc(df[df.year == y], CTRL, nr, nb=500))
    for per, lab in (('week', 'sem'), ('month', 'mes')):
        g = df.groupby(per)
        P = pd.DataFrame({'H': g.H.max(), 'L': g.L.min(), 'nd': g.size(), 'atr0': g.atr.first(), 'year': g.year.first(),
                          'mrng': g.rng.mean(), 'rv': g.apply(lambda x: (x.C - x.O).std())})
        P = P[P.nd >= (3 if per == 'week' else 15)].copy()
        P['lr'] = np.log(P.H - P.L)
        P['latr'] = np.log(P.atr0)
        P['lprev'] = P.lr.shift(1)
        P['lmprev'] = np.log(P.mrng).shift(1)
        P['lrvprev'] = np.log(P.rv).shift(1)
        P['lnd'] = np.log(P.nd)
        P = P[P.lprev.notna()]
        P.index = P.index.astype(str)
        for ex, nm in (('lprev', 'log range periodo anterior'), ('lmprev', 'log media range diario periodo anterior'),
                       ('lrvprev', 'log desvio retorno diario periodo anterior')):
            add(f'5 {lab} {nm}', a, 'toda', inc(P, ['latr', 'lnd'], ex, y='lr'))
        if per == 'week':
            for y in range(2022, 2027):
                add('5 sem log range W-1 ano', a, str(y), inc(P[P.year == y], ['latr', 'lnd'], 'lprev', y='lr', nb=500))
            dd = df.copy()
            dd['wk'] = dd.week.astype(str)
            dd['lprev'] = dd.wk.map(P.lprev)
            dd['wrel'] = dd.lprev - np.log(dd.atr)
            add('5 dias de W: range W-1/ATR', a, 'toda', inc(dd, CTRL, 'wrel', cluster='wk'))
            for y in range(2022, 2027):
                add('5 dias de W ano', a, str(y), inc(dd[dd.year == y], CTRL, 'wrel', cluster='wk', nb=500))
        else:
            h = len(P) // 2
            add('5 mes log range M-1 (1a metade)', a, 'metade1', inc(P.iloc[:h], ['latr', 'lnd'], 'lprev', y='lr', nb=500))
            add('5 mes log range M-1 (2a metade)', a, 'metade2', inc(P.iloc[h:], ['latr', 'lnd'], 'lprev', y='lr', nb=500))

pd.DataFrame(rows).to_csv(f'{OUT}\\v2_regressoes.csv', sep=';', index=False)
pd.DataFrame(tert).to_csv(f'{OUT}\\v2_tercis.csv', sep=';', index=False)
pd.DataFrame(sp).to_csv(f'{OUT}\\v2_tendencia_volume.csv', sep=';', index=False)
print('ok')
