"""Frente A, parte 2: consenso como GATILHO de uma estrategia nova (ConsensoGatilho).

Regra declarada antes de rodar:
  votantes: Win, WinCincoMedias, WinDeslocamentoMatinal (familia T) e WinRetanguloEma34, WdoRetangulo (familia R).
  gatilho: na transicao em que, na linha t de votos.parquet (barra M1 FECHADA), ha >= 3 votos no mesmo lado
           com >= 1 de T e >= 1 de R (e a condicao nao valia na linha anterior do mesmo pregao).
  ordem: LIMITE no fechamento da barra t, enviada na abertura de t+1, prazo 3 min; enche quando o last toca o limite
         (compra: last <= limite), executa no preco do limite. Linhas t de 09:04 a 16:58 (ordem 09:05-16:59).
  1 posicao por vez; gatilho com ordem pendente/posicao aberta e' ignorado.
  saida: stop a mercado (last) e alvo em ordem-limite, em multiplos do ATR M5 (media simples 14 TR da ultima M5 fechada),
         arredondados a 5 pts; zera a mercado 17:50. 1 contrato. Grade stop {1,2,3} x alvo {1,2,3}. Janeiro: stop 2 / alvo 2.
"""
import os, sys
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__))
F0 = os.path.join(AQUI, '..', 'f0_fundacao')
BASE = os.path.abspath(os.path.join(AQUI, '..', '..'))
sys.path.insert(0, BASE); sys.path.insert(0, F0)
import dados as D
import port_win as PW
import saida as S

VOT = ['Win', 'WinCincoMedias', 'WinDeslocamentoMatinal', 'WinRetanguloEma34', 'WdoRetangulo']
KMIN = 3
TTL_MIN = 3
MULTS = [1, 2, 3]
CELLS = [(s, a) for s in MULTS for a in MULTS]
DEFAULT_CELL = (2, 2)
CAP0 = 1000.0
NSORT = 200
NPLAC = 40
RS_PONTO = D.RS_PONTO
DIA_MS = 86_400_000


def prepara():
    vt = pd.read_parquet(os.path.join(F0, 'votos.parquet'))
    m1 = D.m1()
    idx = vt.index
    V = np.stack([vt[f'{v}.voto'].to_numpy(float) for v in VOT], 1)
    close = m1.close.reindex(idx).to_numpy(float)
    m5 = PW._ohlc(m1, '5min')
    h, l, c = (m5[k].to_numpy(float) for k in ('high', 'low', 'close'))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = np.nan
    atr5 = pd.Series(tr).rolling(14).mean().to_numpy()
    fim5 = (m5.index + pd.Timedelta(minutes=5)).values
    k = np.searchsorted(fim5, (idx + pd.Timedelta(minutes=1)).values, 'right') - 1
    atr = np.where(k >= 0, atr5[np.clip(k, 0, None)], np.nan)
    dia = np.array(idx.date)
    mod = (idx.hour * 60 + idx.minute).to_numpy()
    ms = idx.values.astype('datetime64[ms]').astype(np.int64)
    return dict(idx=idx, V=V, close=close, atr=atr, dia=dia, mod=mod, ms=ms)


def episodios_placebo(V, dia, vi, rng):
    """Troca o lado do votante vi por um sorteado, UM sorteio por episodio (sequencia de mesmo voto nao nulo no pregao)."""
    v = V[:, vi].copy()
    new_run = np.r_[True, (v[1:] != v[:-1]) | (dia[1:] != dia[:-1])]
    rid = np.cumsum(new_run) - 1
    sign = rng.choice([-1.0, 1.0], rid.max() + 1)
    out = np.where(v != 0, sign[rid], 0.0)
    V2 = V.copy()
    V2[:, vi] = out
    return V2


def gatilhos(P, V=None):
    """-> (rows, lados) das transicoes de consenso."""
    V = P['V'] if V is None else V
    T = V[:, :3]; R = V[:, 3:]
    ok_t = (mod := P['mod']) >= 9 * 60 + 4
    janela = (mod >= 9 * 60 + 4) & (mod <= 16 * 60 + 58)
    rows, lados = [], []
    dia = P['dia']
    for lado in (1.0, -1.0):
        cond = ((V == lado).sum(1) >= KMIN) & ((T == lado).sum(1) >= 1) & ((R == lado).sum(1) >= 1)
        prev = np.r_[False, cond[:-1]] & np.r_[False, dia[1:] == dia[:-1]]
        tr = cond & ~prev & janela
        r = np.flatnonzero(tr)
        rows += list(r); lados += [lado] * len(r)
    o = np.argsort(rows, kind='stable')
    return np.array(rows, int)[o], np.array(lados, float)[o]


_TK = {}


def ticks(dia):
    if dia not in _TK:
        t, p = S._ticks(dia)
        _TK[dia] = (t, p)
    return _TK[dia]


def rodar(P, rows, lados, cellfn):
    """Simula sequencialmente. cellfn(mes)->(mult_stop, mult_alvo). -> DataFrame de operacoes."""
    out = []
    dia = P['dia']
    d_rows = dia[rows]
    hz = S._hz_ms('17:50')
    for d in pd.unique(d_rows):
        sel = np.flatnonzero(d_rows == d)
        t, p = ticks(d)
        d0 = P['ms'][rows[sel[0]]] // DIA_MS * DIA_MS
        iz = int(np.searchsorted(t, d0 + hz, 'left'))
        livre = -1
        for q in sel:
            r = rows[q]; lado = lados[q]
            T0 = int(P['ms'][r]) + 60000
            if T0 < livre:
                continue
            lim = P['close'][r]
            i0 = int(np.searchsorted(t, T0, 'left')); i1 = int(np.searchsorted(t, T0 + TTL_MIN * 60000, 'left'))
            seg = p[i0:i1]
            m = seg <= lim if lado > 0 else seg >= lim
            if len(seg) == 0 or not m.any():
                livre = T0 + TTL_MIN * 60000
                continue
            fi = i0 + int(np.argmax(m))
            mes = pd.Timestamp(T0, unit='ms').month
            ms_, ma_ = cellfn(mes)
            a = P['atr'][r]
            if not np.isfinite(a):
                livre = T0 + TTL_MIN * 60000; continue
            stop = max(5.0, round(ms_ * a / 5) * 5); alvo = max(5.0, round(ma_ * a / 5) * 5)
            ist = int(np.searchsorted(t, t[fi], 'right'))
            k, px, mot = S._um(t, p, ist, iz, int(lado), float(lim), stop, alvo, True)
            livre = int(t[k])
            pts = lado * (px - lim)
            out.append((int(t[fi]), int(t[k]), int(lado), float(lim), float(px), mot, pts, pts * RS_PONTO, mes))
    df = pd.DataFrame(out, columns=['te', 'ts', 'lado', 'preco_entrada', 'preco_saida', 'motivo', 'pontos', 'rs', 'mes_ent'])
    if len(df):
        df['entrada'] = pd.to_datetime(df.te, unit='ms'); df['saida'] = pd.to_datetime(df.ts, unit='ms')
        df['mes_sai'] = df.saida.dt.month
    return df


def walk(trs, default=DEFAULT_CELL, custo=2.0):
    esc = {}
    for m in range(1, 11):
        best = default
        sc = {}
        for c in CELLS:
            d = trs[c]
            sc[c] = (d[d.mes_sai < m].rs - custo).sum() if len(d) else 0.0
        if any(len(trs[c][trs[c].mes_sai < m]) for c in CELLS):
            best = max(CELLS, key=lambda c: (sc[c], -CELLS.index(c)))
        esc[m] = best
    return esc


def compoe(trs, esc):
    parts = [trs[esc[m]][trs[esc[m]].mes_ent == m] for m in range(1, 11)]
    parts = [x for x in parts if len(x)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(trs[CELLS[0]].columns))


def curva(df, custo):
    if len(df) == 0:
        return 0.0, 0.0, '', 0
    a = df.sort_values(['saida', 'entrada'])
    res = a.rs.to_numpy() - custo
    bal = CAP0 + np.cumsum(res)
    pk = np.maximum.accumulate(np.r_[CAP0, bal])[1:]
    q = np.flatnonzero(bal <= 0)
    return res.sum(), (pk - bal).max(), (str(a.saida.iloc[q[0]].date()) if len(q) else ''), len(a)


def mensal(df, custo):
    if len(df) == 0:
        return [0.0] * 10
    s = (df.rs - custo).groupby(df.saida.dt.month).sum()
    return [float(s.get(m, 0.0)) for m in range(1, 11)]


def grade(P, rows, lados):
    return {c: rodar(P, rows, lados, lambda m, c=c: c) for c in CELLS}


def main():
    P = prepara()
    rows, lados = gatilhos(P)
    print('gatilhos:', len(rows), 'long', int((lados > 0).sum()), 'short', int((lados < 0).sum()), flush=True)
    trs = grade(P, rows, lados)
    for c in CELLS:
        d = trs[c]
        print('celula stop/alvo ATR', c, 'ops', len(d), 'liq0', round(d.rs.sum(), 1), 'liq2', round((d.rs - 2).sum(), 1), flush=True)
    esc = walk(trs)
    print('escolhas', esc, flush=True)
    wf = compoe(trs, esc)
    rng = np.random.default_rng(20261007)
    # controle: mesmos gatilhos (data/hora), lado sorteado, mesma celula do mes
    c0 = np.zeros(NSORT); c2 = np.zeros(NSORT)
    for i in range(NSORT):
        ld = rng.choice([-1.0, 1.0], len(rows))
        d = rodar(P, rows, ld, lambda m: esc[m])
        c0[i] = d.rs.sum(); c2[i] = (d.rs - 2).sum()
        if i % 50 == 0: print('controle', i, flush=True)
    real0, real2 = wf.rs.sum(), (wf.rs - 2).sum()
    pct0 = (c0 < real0).mean() * 100; pct2 = (c2 < real2).mean() * 100
    print('wf liq0', real0, 'liq2', real2, 'ops', len(wf), 'pct controle', pct0, pct2, flush=True)
    # placebo de votante
    pl = []
    for vi, v in enumerate(VOT):
        a0, a2 = [], []
        for i in range(NPLAC):
            V2 = episodios_placebo(P['V'], P['dia'], vi, rng)
            r2, l2 = gatilhos(P, V2)
            t2 = grade(P, r2, l2)
            e2 = walk(t2)
            w2 = compoe(t2, e2)
            a0.append(w2.rs.sum()); a2.append((w2.rs - 2).sum())
        a0, a2 = np.array(a0), np.array(a2)
        pl.append(dict(votante_trocado=v, real_liq0=round(real0, 1), placebo_media0=round(a0.mean(), 1), placebo_p5_p95_0=f'{np.percentile(a0, 5):.0f}..{np.percentile(a0, 95):.0f}',
                       pct_real0=round((a0 < real0).mean() * 100, 1), real_liq2=round(real2, 1), placebo_media2=round(a2.mean(), 1),
                       placebo_p5_p95_2=f'{np.percentile(a2, 5):.0f}..{np.percentile(a2, 95):.0f}', pct_real2=round((a2 < real2).mean() * 100, 1)))
        print('placebo', pl[-1], flush=True)
    pd.DataFrame(pl).to_csv(os.path.join(AQUI, 'resultado_placebo_gatilho.csv'), index=False)
    # saidas
    cel_rows = [dict(stop_atr=c[0], alvo_atr=c[1], ops=len(trs[c]), liq0=round(trs[c].rs.sum(), 1), liq2=round((trs[c].rs - 2).sum(), 1),
                     acerto=round((trs[c].rs > 0).mean() * 100, 1) if len(trs[c]) else 0) for c in CELLS]
    pd.DataFrame(cel_rows).to_csv(os.path.join(AQUI, 'resultado_gatilho_celulas.csv'), index=False)
    res = []
    for custo in (0.0, 2.0):
        lq, dd, qd, n = curva(wf, custo)
        dr = c0 if custo == 0 else c2
        res.append(dict(custo=custo, ops=n, liquido=round(lq, 1), maxDD=round(dd, 1), quebra=qd,
                        acerto=round(((wf.rs - custo) > 0).mean() * 100, 1) if n else 0,
                        pct_vs_controle_lado_sorteado=round((dr < lq).mean() * 100, 1), controle_mediana=round(float(np.median(dr)), 1),
                        **{f'm{m}': round(v, 1) for m, v in zip(range(1, 11), mensal(wf, custo))}))
    pd.DataFrame(res).to_csv(os.path.join(AQUI, 'resultado_gatilho_wf.csv'), index=False)
    pd.DataFrame([dict(mes=m, stop_atr=c[0], alvo_atr=c[1]) for m, c in esc.items()]).to_csv(os.path.join(AQUI, 'escolhas_walkforward_gatilho.csv'), index=False)
    out = pd.DataFrame(dict(estrategia='ConsensoGatilho', entrada=wf.entrada, saida=wf.saida, lado=wf.lado, qtd=1.0,
                            preco_entrada=wf.preco_entrada, preco_saida=wf.preco_saida, motivo=wf.motivo, pontos=wf.pontos, rs=wf.rs))
    out.sort_values('entrada').to_csv(os.path.join(AQUI, 'trades', 'A2_gatilho_walkforward.csv'), index=False)
    print(pd.DataFrame(res).T, flush=True)
    print('celulas parte 2:', len(CELLS), flush=True)


if __name__ == '__main__':
    main()
