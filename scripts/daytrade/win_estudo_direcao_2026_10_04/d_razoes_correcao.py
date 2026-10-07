"""Estudo descritivo WIN: razoes impulso/correcao e estrutura fractal (zigue-zague 2 niveis).
Nulo: embaralhamento dos retornos M1 dentro do dia (mesmo ATR/limiares). Sem backtest de robo."""
import numpy as np, pandas as pd
from pathlib import Path
OUT = Path(__file__).parent
CSV = r"C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5\WIN@D_M1_202110010900_202610011717.csv"
NSEED = 5
CONFIGS = [(0.35, 0.07), (0.5, 0.10), (0.75, 0.15)]   # (k macro, k micro) x ATR14 diario de D-1
MAIN = (0.5, 0.10)
FIB = [0.382, 0.5, 0.618, 0.786]; HW = 0.025
BINS_R = [(0, .25), (.25, .38), (.38, .5), (.5, .62), (.62, .79), (.79, 1.0001)]
rng = np.random.default_rng(12345)


def zz(c, thr):
    """pivots confirmados: idx, preco, barra de confirmacao."""
    n = len(c); lo = hi = c[0]; lo_i = hi_i = 0; d = 0
    pi, pp, pc = [], [], []; ext = 0.0; ext_i = 0
    for i in range(1, n):
        x = c[i]
        if d == 0:
            if x > hi: hi, hi_i = x, i
            if x < lo: lo, lo_i = x, i
            if x - lo >= thr:
                pi.append(lo_i); pp.append(lo); pc.append(i); d = 1; ext, ext_i = x, i
            elif hi - x >= thr:
                pi.append(hi_i); pp.append(hi); pc.append(i); d = -1; ext, ext_i = x, i
        elif d == 1:
            if x > ext: ext, ext_i = x, i
            elif ext - x >= thr:
                pi.append(ext_i); pp.append(ext); pc.append(i); d = -1; ext, ext_i = x, i
        else:
            if x < ext: ext, ext_i = x, i
            elif x - ext >= thr:
                pi.append(ext_i); pp.append(ext); pc.append(i); d = 1; ext, ext_i = x, i
    return pi, pp, pc


def load():
    f = pd.read_csv(CSV, sep='\t')
    f.columns = ['d', 't', 'o', 'h', 'l', 'c', 'tv', 'v', 'sp']
    days = []
    for d, g in f.groupby('d', sort=True):
        if len(g) < 300: continue
        days.append(dict(date=d.replace('.', '-'), o=g.o.values, h=g.h.max(), l=g.l.min(), c=g.c.values))
    pc = None
    for x in days:
        x['tr'] = (x['h'] - x['l']) if pc is None else max(x['h'] - x['l'], abs(x['h'] - pc), abs(x['l'] - pc))
        pc = x['c'][-1]
    trs = np.array([x['tr'] for x in days])
    for i, x in enumerate(days):
        x['atr'] = trs[i - 14:i].mean() if i >= 14 else np.nan
        x['open'] = x['o'][0]
        x['win'] = 'IS' if x['date'] <= '2024-12-31' else 'OOS'
    return [x for x in days if not np.isnan(x['atr'])]


def shuffled(c, o0):
    d = np.diff(np.r_[o0, c]); rng.shuffle(d); return o0 + np.cumsum(d)


def forward(c, t, ext, org, s):
    """primeira barra apos t: supera extremo (1) ou perde origem (-1); 0 = nenhum no pregao."""
    seg = c[t + 1:]
    if len(seg) == 0: return 0
    a = np.nonzero(s * (seg - ext) > 0)[0]; b = np.nonzero(s * (seg - org) < 0)[0]
    ia = a[0] if len(a) else 10**9; ib = b[0] if len(b) else 10**9
    return 1 if ia < ib else (-1 if ib < ia else 0)


def process_series(days, kM, km, null):
    ev, legs, dd = [], [], []
    for di, x in enumerate(days):
        c = shuffled(x['c'], x['open']) if null else x['c'].astype(float)
        thrM, thrm = kM * x['atr'], km * x['atr']
        for lvl, thr in (('macro', thrM), ('micro', thrm)):
            pi, pp, pc = zz(c, thr)
            for k in range(1, len(pp) - 1):
                imp = abs(pp[k] - pp[k - 1]); cor = abs(pp[k + 1] - pp[k]); r = cor / imp
                s = 1 if pp[k] > pp[k - 1] else -1
                oc = forward(c, pc[k + 1], pp[k], pp[k - 1], s) if r <= 1 else np.nan
                ev.append((di, x['win'], lvl, r, oc))
            if lvl == 'macro':
                piM, ppM, pcM = pi, pp, pc
        for k in range(len(ppM) - 1):
            a, b = piM[k], piM[k + 1]
            seg = c[a:b + 1]; s = 1 if ppM[k + 1] > ppM[k] else -1
            size = abs(ppM[k + 1] - ppM[k])
            run = np.maximum.accumulate(seg) - seg if s == 1 else seg - np.minimum.accumulate(seg)
            _, mpp, _ = zz(seg, thrm)
            nimp = ncor = 0; rr = []
            for j in range(len(mpp) - 1):
                if (mpp[j + 1] > mpp[j]) == (s == 1): nimp += 1
                else:
                    ncor += 1
                    if j >= 1: rr.append(abs(mpp[j + 1] - mpp[j]) / abs(mpp[j] - mpp[j - 1]))
            legs.append((di, x['win'], s, size / x['open'] * 100, size / x['atr'], nimp, ncor,
                         run.max() / size, np.mean(rr) if rr else np.nan, len(seg)))
        pi, pp, pc = zz(c, thrM)
        sgn = np.sign(c[-1] - x['open'])
        lg = [pp[k + 1] - pp[k] for k in range(len(pp) - 1)]
        if len(pp): lg.append(c[-1] - pp[-1])
        lg = np.array(lg); path_m1 = np.abs(np.diff(np.r_[x['open'], c])).sum()
        if len(lg) and sgn != 0:
            fav = np.abs(lg[np.sign(lg) == sgn]).sum(); con = np.abs(lg[np.sign(lg) != sgn]).sum()
        else:
            fav = con = np.nan
        dd.append((di, x['win'], x['date'], c[-1] - x['open'], abs(c[-1] - x['open']) / path_m1,
                   abs(c[-1] - x['open']) / max(np.abs(lg).sum(), 1e-9) if len(lg) else np.nan,
                   fav / con if con and con > 0 else np.nan, len(lg)))
    E = pd.DataFrame(ev, columns=['day', 'win', 'lvl', 'r', 'oc'])
    L = pd.DataFrame(legs, columns=['day', 'win', 'dir', 'size_pct', 'size_atr', 'n_imp', 'n_cor', 'maxdd_frac', 'micro_r_mean', 'n_bars'])
    D = pd.DataFrame(dd, columns=['day', 'win', 'date', 'ret_pts', 'eff_m1', 'eff_zz', 'razao_fav_con', 'n_pernadas'])
    return E, L, D


def share_boot(day, num, den, nb=300):
    g = pd.DataFrame({'day': day, 'n': np.asarray(num, float), 'd': np.asarray(den, float)}).groupby('day').sum()
    n, d = g.n.values, g.d.values
    if d.sum() == 0: return np.nan, np.nan, 0
    idx = rng.integers(0, len(g), (nb, len(g)))
    bs = n[idx].sum(1) / np.maximum(d[idx].sum(1), 1e-9)
    return n.sum() / d.sum(), bs.std(), int(d.sum())


def ks(a, b):
    a = np.sort(a[a <= 2]); b = np.sort(b[b <= 2]); g = np.union1d(a, b)
    return np.abs(np.searchsorted(a, g, 'right') / len(a) - np.searchsorted(b, g, 'right') / len(b)).max()


def main():
    days = load(); print('dias', len(days), flush=True)
    res = {}
    for cfg in CONFIGS:
        res[cfg] = []
        for s in range(NSEED + 1):
            E, L, D = process_series(days, cfg[0], cfg[1], null=(s > 0))
            for t in (E, L, D): t['serie'] = s
            res[cfg].append((E, L, D)); print('cfg', cfg, 'serie', s, 'eventos', len(E), flush=True)
    hist_rows, fib_rows, pred_rows, leg_rows, day_rows, ss_rows = [], [], [], [], [], []
    for cfg, lst in res.items():
        E = pd.concat([a for a, _, _ in lst]); L = pd.concat([b for _, b, _ in lst]); D = pd.concat([c for _, _, c in lst])
        tag = f'{cfg[0]}/{cfg[1]}'
        for win in ('IS', 'OOS'):
            for lvl in ('macro', 'micro'):
                e = E[(E.win == win) & (E.lvl == lvl)]
                real = e[e.serie == 0]; nul = e[e.serie > 0]
                edges = np.r_[np.arange(0, 2.0001, 0.05), 99]
                hr = np.histogram(real.r, edges)[0] / max(len(real), 1)
                hn = np.array([np.histogram(nul[nul.serie == s].r, edges)[0] / max((nul.serie == s).sum(), 1) for s in range(1, NSEED + 1)])
                for i in range(len(edges) - 1):
                    hist_rows.append((tag, win, lvl, edges[i], edges[i + 1], hr[i], hn[:, i].mean(), hn[:, i].std(), len(real)))
                for fb in FIB:
                    inb = lambda t: ((t.r >= fb - HW) & (t.r < fb + HW))
                    sr, se_r, n_r = share_boot(real.day.values, inb(real).values, np.ones(len(real)))
                    sn = np.array([inb(nul[nul.serie == s]).mean() for s in range(1, NSEED + 1)])
                    z = (sr - sn.mean()) / np.hypot(se_r, sn.std() + 1e-12)
                    fib_rows.append((tag, win, lvl, fb, n_r, sr, se_r, sn.mean(), sn.std(), sr / sn.mean(), z))
                for (lo, hi) in BINS_R:
                    f = lambda t: t[(t.r >= lo) & (t.r < hi) & t.oc.notna()]
                    fr = f(real); fn = f(nul)
                    if len(fr) < 5: continue
                    pa_r, se_r, nd_r = share_boot(fr.day.values, (fr.oc == 1).values, (fr.oc != 0).values)
                    pn = np.array([((q.oc == 1).sum() / max((q.oc != 0).sum(), 1)) for q in (fn[fn.serie == s] for s in range(1, NSEED + 1))])
                    z = (pa_r - pn.mean()) / np.hypot(se_r, pn.std() + 1e-12)
                    pred_rows.append((tag, win, lvl, f'{lo:.2f}-{min(hi, 1):.2f}', len(fr), nd_r, pa_r, se_r, pn.mean(), pn.std(),
                                      pa_r - pn.mean(), z, (fr.oc == 0).mean(), (fn.oc == 0).mean()))
            l = L[L.win == win]
            for s, nm in ((0, 'real'), (-1, 'nulo')):
                q = l[l.serie == 0] if s == 0 else l[l.serie > 0]
                leg_rows.append((tag, win, nm, len(q) / (1 if s == 0 else NSEED), q.size_pct.mean(), q.size_pct.std(), q.size_atr.mean(), q.size_atr.std(),
                                 q.n_imp.mean(), q.n_cor.mean(), q.maxdd_frac.mean(), q.maxdd_frac.median(), q.maxdd_frac.std(), q.micro_r_mean.mean()))
            d = D[D.win == win]
            for s, nm in ((0, 'real'), (-1, 'nulo')):
                q = d[d.serie == 0] if s == 0 else d[d.serie > 0]
                day_rows.append((tag, win, nm, len(q) / (1 if s == 0 else NSEED), q.eff_m1.mean(), q.eff_m1.std(), q.eff_zz.mean(),
                                 q.razao_fav_con.median(), q.razao_fav_con.mean()))
            e = E[E.win == win]
            kr = ks(e[(e.serie == 0) & (e.lvl == 'macro')].r.values, e[(e.serie == 0) & (e.lvl == 'micro')].r.values)
            kn = [ks(e[(e.serie == s) & (e.lvl == 'macro')].r.values, e[(e.serie == s) & (e.lvl == 'micro')].r.values) for s in range(1, NSEED + 1)]
            ss_rows.append((tag, win, kr, np.mean(kn), np.std(kn)))

    def P(rows, cols, name):
        pd.DataFrame(rows, columns=cols).to_csv(OUT / f'd_razoes_correcao_{name}.csv', sep=';', decimal=',', index=False, float_format='%.4f')
    P(hist_rows, ['cfg', 'janela', 'nivel', 'bin_lo', 'bin_hi', 'frac_real', 'frac_nulo_media', 'frac_nulo_dp', 'n_real'], 'hist_razoes')
    P(fib_rows, ['cfg', 'janela', 'nivel', 'fib', 'n_real', 'share_real', 'ep_real', 'share_nulo', 'dp_nulo', 'real_sobre_nulo', 'z'], 'fib_bandas')
    P(pred_rows, ['cfg', 'janela', 'nivel', 'bin_razao', 'n_eventos', 'n_decididos', 'P_supera_real', 'ep_real', 'P_supera_nulo', 'dp_nulo', 'dif', 'z',
                  'frac_indecisa_real', 'frac_indecisa_nulo'], 'predicao')
    P(leg_rows, ['cfg', 'janela', 'serie', 'n_pernadas', 'size_pct_med', 'size_pct_dp', 'size_atr_med', 'size_atr_dp', 'n_micro_imp', 'n_micro_cor',
                 'maxdd_frac_med', 'maxdd_frac_mediana', 'maxdd_frac_dp', 'razao_micro_media'], 'pernadas')
    P(day_rows, ['cfg', 'janela', 'serie', 'n_dias', 'eff_m1_med', 'eff_m1_dp', 'eff_zz_med', 'razao_fav_con_mediana', 'razao_fav_con_media'], 'dia')
    P(ss_rows, ['cfg', 'janela', 'KS_macro_vs_micro_real', 'KS_nulo_media', 'KS_nulo_dp'], 'autossimilaridade')

    # item 5: D-1 -> D (config principal, serie real; nulo por permutacao)
    d5 = []
    allD = res[MAIN][0][2].reset_index(drop=True)
    allD['eff_prev'] = allD.eff_m1.shift(1); allD['effzz_prev'] = allD.eff_zz.shift(1); allD['ret_prev'] = allD.ret_pts.shift(1)
    for win in ('IS', 'OOS'):
        q = allD[allD.win == win].dropna(subset=['eff_prev', 'ret_prev'])
        for col, tgt in (('eff_prev', 'eff_m1'), ('effzz_prev', 'eff_zz')):
            qq = q.dropna(subset=[col, tgt]); rho = qq[col].rank().corr(qq[tgt].rank())
            rk = qq[tgt].rank().values
            perm = [pd.Series(rng.permutation(qq[col].values)).rank().corr(pd.Series(rk)) for _ in range(1000)]
            d5.append((win, f'spearman {col}->{tgt}', len(qq), rho, np.mean(perm), np.std(perm), (np.abs(perm) >= abs(rho)).mean()))
        # eficiencia como preditora de direcao: continuidade do sinal por tercil de eficiencia de D-1
        q = q.assign(cont=(np.sign(q.ret_pts) == np.sign(q.ret_prev)).astype(float))
        t = pd.qcut(q.eff_prev, 3, labels=False)
        for k in (0, 1, 2):
            x = q[t == k]; m = x.cont.mean()
            perm = np.array([rng.permutation(q.cont.values)[:len(x)].mean() for _ in range(1000)])
            d5.append((win, f'P(mesmo sinal de D-1) tercil eff_D-1={k}', len(x), m, perm.mean(), perm.std(), (np.abs(perm - perm.mean()) >= abs(m - perm.mean())).mean()))
        d5.append((win, 'P(mesmo sinal de D-1) todos', len(q), q.cont.mean(), 0.5, np.sqrt(.25 / len(q)), np.nan))
    pd.DataFrame(d5, columns=['janela', 'estatistica', 'n', 'real', 'nulo_perm_media', 'nulo_perm_dp', 'p_perm']).to_csv(
        OUT / 'd_razoes_correcao_dia_previsao.csv', sep=';', decimal=',', index=False, float_format='%.4f')
    print('OK', flush=True)


if __name__ == '__main__':
    main()
