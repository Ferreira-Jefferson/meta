"""Frente A, parte 1: consenso das OUTRAS estrategias como filtro das entradas existentes (saida original)."""
import os
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(AQUI, '..', 'f0_fundacao', 'eventos.parquet')
VOT = ['Win', 'WinCincoMedias', 'WinDeslocamentoMatinal', 'WinRetanguloEma34', 'WdoRetangulo']
FAM = {'Win': 'T', 'WinCincoMedias': 'T', 'WinDeslocamentoMatinal': 'T', 'WinRetanguloEma34': 'R', 'WdoRetangulo': 'R'}
VARS = ['k1', 'k2', 'k3', 'maj', 'fam_sem_contra', 'fam_a_favor', 'pond0.5', 'pond1.0', 'pond1.5']
DEFAULT = 'maj'
CAP0 = 1000.0
NSORT = 200


def carrega():
    e = pd.read_parquet(EV)
    e = e[e.estrategia.isin(VOT)].reset_index(drop=True)
    e['mes_ent'] = e.entrada.dt.month
    e['mes_sai'] = e.saida.dt.month
    V = np.stack([e[f'{v}.voto'].to_numpy(float) for v in VOT], 1)
    F = np.stack([e[f'{v}.forca'].to_numpy(float) for v in VOT], 1)
    old = e.voto_mesmo_dia.to_numpy() == 0
    V[old] = 0
    F[old] = 0
    return e, V, F


def mascaras(e, V, F):
    lado = e.lado.to_numpy(float)
    est = e.estrategia.to_numpy()
    idx = {v: i for i, v in enumerate(VOT)}
    own = np.zeros(V.shape, bool)
    fam_o = np.zeros(V.shape, bool)
    for i, x in enumerate(est):
        own[i, idx[x]] = True
        for v in VOT:
            if FAM[v] != FAM[x]:
                fam_o[i, idx[v]] = True
    oth = ~own
    S = V * lado[:, None]
    fav = ((S > 0) & oth).sum(1)
    con = ((S < 0) & oth).sum(1)
    ff = ((S > 0) & fam_o).sum(1)
    fc = ((S < 0) & fam_o).sum(1)
    pond = (S * F * oth).sum(1)
    return {'k1': fav >= 1, 'k2': fav >= 2, 'k3': fav >= 3, 'maj': fav > con,
            'fam_sem_contra': fc == 0, 'fam_a_favor': ff > fc,
            'pond0.5': pond >= .5, 'pond1.0': pond >= 1.0, 'pond1.5': pond >= 1.5}


def walk(rs_net, mes_ent, mes_sai, masks, default=DEFAULT):
    n = len(rs_net)
    keep = np.zeros(n, bool)
    esc = {}
    for m in range(1, 11):
        past = mes_sai < m
        best = default
        if past.any():
            sc = {v: rs_net[past & masks[v]].sum() for v in VARS}
            best = max(VARS, key=lambda v: (sc[v], -VARS.index(v)))
        esc[m] = best
        sel = mes_ent == m
        keep[sel] = masks[best][sel]
    return keep, esc


def curva(df, custo):
    a = df.sort_values(['saida', 'entrada'])
    res = a.rs.to_numpy() - custo
    bal = CAP0 + np.cumsum(res)
    if len(bal) == 0:
        return 0.0, 0.0, '', 0
    pk = np.maximum.accumulate(np.r_[CAP0, bal])[1:]
    dd = (pk - bal).max()
    q = np.flatnonzero(bal <= 0)
    qd = str(a.saida.iloc[q[0]].date()) if len(q) else ''
    return res.sum(), dd, qd, len(a)


def mensal(df, custo):
    r = df.rs - custo
    s = r.groupby(df.saida.dt.month).sum()
    return [float(s.get(m, 0.0)) for m in range(1, 11)]


def main():
    e, V, F = carrega()
    mk = mascaras(e, V, F)
    rs2 = e.rs.to_numpy() - 2.0
    me, ms = e.mes_ent.to_numpy(), e.mes_sai.to_numpy()
    rng = np.random.default_rng(20261006)
    cel = 0
    keeps = {}
    for x in VOT:
        s = (e.estrategia == x).to_numpy()
        sub = {v: mk[v][s] for v in VARS}
        k, esc = walk(rs2[s], me[s], ms[s], sub)
        kk = np.zeros(len(e), bool)
        kk[np.flatnonzero(s)[k]] = True
        keeps[x] = (kk, esc)
        cel += len(VARS)
    s5 = np.ones(len(e), bool)
    k, esc = walk(rs2, me, ms, mk)
    keeps['conjunto_comum'] = (k, esc)
    cel += len(VARS)
    kind = np.zeros(len(e), bool)
    for x in VOT:
        kind |= keeps[x][0]
    keeps['conjunto_individual'] = (kind, None)
    ref = []
    for nome, sel in [(x, (e.estrategia == x).to_numpy()) for x in VOT] + [('conjunto', s5)]:
        for v in ['sem_filtro'] + VARS:
            m = np.ones(len(e), bool) if v == 'sem_filtro' else mk[v]
            d = e[sel & m]
            l0 = curva(d, 0.0)
            l2 = curva(d, 2.0)
            ref.append(dict(escopo=nome, variante=v, ops=len(d), liq0=round(l0[0], 1), liq2=round(l2[0], 1), dd2=round(l2[1], 1)))
    pd.DataFrame(ref).to_csv(os.path.join(AQUI, 'resultado_variantes_fixas.csv'), index=False)

    resumo, mens = [], []
    for nome in VOT + ['conjunto_comum', 'conjunto_individual']:
        kk = keeps[nome][0]
        conj = nome.startswith('conjunto')
        sel = s5 if conj else (e.estrategia == nome).to_numpy()
        base = e[sel]
        filt = e[sel & kk]
        cnt = {x: int(((e.estrategia == x) & ~kk).sum()) for x in (VOT if conj else [nome])}
        ixs = {x: np.flatnonzero((e.estrategia == x).to_numpy()) for x in cnt}
        d0 = np.zeros(NSORT)
        d2 = np.zeros(NSORT)
        ddw = np.zeros(NSORT)
        for d in range(NSORT):
            parts = []
            for x, c in cnt.items():
                ix = ixs[x]
                drop = rng.choice(ix, c, replace=False) if c else []
                parts.append(np.setdiff1d(ix, drop))
            dd_ = e.iloc[np.concatenate(parts)]
            d0[d] = curva(dd_, 0.0)[0]
            r2 = curva(dd_, 2.0)
            d2[d] = r2[0]
            ddw[d] = r2[1]
        for custo in (0.0, 2.0):
            lq, dd, qd, n = curva(filt, custo)
            lb, ddb, qdb, nb = curva(base, custo)
            dr = d0 if custo == 0 else d2
            resumo.append(dict(escopo=nome, custo=custo, ops=n, liquido=round(lq, 1), maxDD=round(dd, 1), quebra=qd,
                               ops_sem_filtro=nb, liquido_sem_filtro=round(lb, 1), maxDD_sem_filtro=round(ddb, 1),
                               pct_liquido_vs_sorteio=round((dr < lq).mean() * 100 + (dr == lq).mean() * 50, 1),
                               sorteio_mediana=round(float(np.median(dr)), 1),
                               pct_DD_menor_que_sorteio=round((ddw > dd).mean() * 100, 1) if custo == 2 else np.nan))
            mens.append(dict(escopo=nome, custo=custo, **{f'm{m}': round(v, 1) for m, v in zip(range(1, 11), mensal(filt, custo))}))
        print(nome, resumo[-2]['liquido'], resumo[-1]['liquido'], 'base', resumo[-2]['liquido_sem_filtro'], resumo[-1]['liquido_sem_filtro'],
              'pct', resumo[-2]['pct_liquido_vs_sorteio'], resumo[-1]['pct_liquido_vs_sorteio'], flush=True)
    pd.DataFrame(resumo).to_csv(os.path.join(AQUI, 'resultado_resumo.csv'), index=False)
    pd.DataFrame(mens).to_csv(os.path.join(AQUI, 'resultado_mensal_filtro.csv'), index=False)
    rows = []
    for nome in VOT + ['conjunto_comum']:
        for m, v in keeps[nome][1].items():
            rows.append(dict(escopo=nome, mes=m, variante=v))
    pd.DataFrame(rows).to_csv(os.path.join(AQUI, 'escolhas_walkforward_filtro.csv'), index=False)
    cols = ['estrategia', 'entrada', 'saida', 'lado', 'preco_entrada', 'preco_saida', 'motivo', 'pontos', 'rs']
    e[keeps['conjunto_comum'][0]][cols].to_csv(os.path.join(AQUI, 'trades', 'A1_filtro_conjunto_comum.csv'), index=False)
    e[keeps['conjunto_individual'][0]][cols].to_csv(os.path.join(AQUI, 'trades', 'A1_filtro_conjunto_individual.csv'), index=False)

    pl = []
    realk = keeps['conjunto_comum'][0]
    real = {0: curva(e[realk], 0)[0], 2: curva(e[realk], 2)[0]}
    for vi, v in enumerate(VOT):
        r0, r2 = [], []
        act = V[:, vi] != 0
        for d in range(NSORT):
            V2 = V.copy()
            V2[act, vi] = rng.choice([-1.0, 1.0], act.sum())
            m2 = mascaras(e, V2, F)
            k2, _ = walk(rs2, me, ms, m2)
            r0.append(curva(e[k2], 0)[0])
            r2.append(curva(e[k2], 2)[0])
        r0, r2 = np.array(r0), np.array(r2)
        pl.append(dict(votante_trocado=v, real_liq0=round(real[0], 1), placebo_media0=round(r0.mean(), 1),
                       placebo_p5_p95_0=f'{np.percentile(r0, 5):.0f}..{np.percentile(r0, 95):.0f}', pct_real0=round((r0 < real[0]).mean() * 100, 1),
                       real_liq2=round(real[2], 1), placebo_media2=round(r2.mean(), 1),
                       placebo_p5_p95_2=f'{np.percentile(r2, 5):.0f}..{np.percentile(r2, 95):.0f}', pct_real2=round((r2 < real[2]).mean() * 100, 1)))
        print('placebo', pl[-1], flush=True)
    pd.DataFrame(pl).to_csv(os.path.join(AQUI, 'resultado_placebo_filtro.csv'), index=False)
    print('celulas parte 1 (variantes x escopos walk-forward):', cel, '| tabela fixa:', 6 * len(VARS), flush=True)


if __name__ == '__main__':
    main()
