"""Frente C: portfolio com teto de K contratos simultaneos. Le resultados/*.csv."""
import os, itertools, collections
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, '..', '..', 'resultados')
CAP0 = 1000.0
COSTS = [0.0, 2.0]
NSORT = 200
MESES = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out']
SETS = {
 '5 sem Win_c1': ['Win','WinCincoMedias','WinDeslocamentoMatinal','WinRetanguloEma34','WdoRetangulo'],
 '5 sem Win':    ['Win_c1','WinCincoMedias','WinDeslocamentoMatinal','WinRetanguloEma34','WdoRetangulo'],
 '4 sem WdoRet (Win)':   ['Win','WinCincoMedias','WinDeslocamentoMatinal','WinRetanguloEma34'],
 '4 sem WdoRet (Win_c1)':['Win_c1','WinCincoMedias','WinDeslocamentoMatinal','WinRetanguloEma34'],
}

def load():
    d = []
    for n in ['Win','Win_c1','WinCincoMedias','WinDeslocamentoMatinal','WinRetanguloEma34','WdoRetangulo']:
        d.append(pd.read_csv(os.path.join(RES, n + '.csv')))
    t = pd.concat(d, ignore_index=True)
    t['entrada'] = pd.to_datetime(t.entrada, format='mixed'); t['saida'] = pd.to_datetime(t.saida, format='mixed')
    t['mes_ent'] = t.entrada.dt.month; t['mes_sai'] = t.saida.dt.month
    return t

def ranking_wf(t, strats):
    """rank por mes de entrada: R$/op por estrategia nos meses ANTERIORES (0 = melhor prioridade)."""
    rk = {}
    for m in range(1, 11):
        past = t[(t.estrategia.isin(strats)) & (t.mes_sai < m)]
        s = past.groupby('estrategia').rs.mean() if len(past) else pd.Series(dtype=float)
        order = sorted(strats, key=lambda e: (-s.get(e, 0.0), e))
        rk[m] = {e: i for i, e in enumerate(order)}
    return rk

def accept(t, strats, K, prio, netting):
    x = t[t.estrategia.isin(strats)].copy()
    rk = ranking_wf(t, strats) if prio == 'ranking' else None
    x['p'] = [rk[m][e] if rk else 0 for m, e in zip(x.mes_ent, x.estrategia)]
    x = x.sort_values(['entrada', 'p'], kind='stable')
    openp, acc, cut, blk = [], [], 0, 0
    for idx, r in x.iterrows():
        openp = [o for o in openp if o[0] > r.entrada]
        if netting and any(o[1] != r.lado for o in openp):
            blk += 1; continue
        if len(openp) >= K:
            cut += 1; continue
        openp.append((r.saida, r.lado)); acc.append(idx)
    return acc, cut, blk

def maxdd(path):
    pk, dd = -1e18, 0.0
    for v in path:
        pk = max(pk, v); dd = max(dd, pk - v)
    return dd

def simula(t, acc, cost):
    a = t.loc[acc].sort_values(['saida', 'entrada']).copy()
    a['res'] = a.rs - cost
    bal = CAP0 + a.res.cumsum().values
    quebra = None
    if len(bal) and bal.min() <= 0:
        i = int(np.argmax(bal <= 0)); quebra = a.saida.iloc[i]
        a = a.iloc[:i + 1]; bal = bal[:i + 1]
    a['bal'] = bal
    ev = []
    for r in a.itertuples():
        ev.append((r.entrada, 0, r.res)); ev.append((r.saida, 1, r.res))
    ev.sort(key=lambda z: (z[0], -z[1]))
    closed, opn, worst = CAP0, 0.0, CAP0
    for _, kind, v in ev:
        if kind == 0: opn += v
        else: opn -= v; closed += v
        worst = min(worst, closed + opn)
    return a, quebra, worst

def mes_stats(a):
    rows = []
    for m in range(1, 11):
        b = a[a.saida.dt.month == m]
        if len(b):
            base = a.bal[a.saida.dt.month < m]
            start = base.iloc[-1] if len(base) else CAP0
            path = np.concatenate([[start], b.bal.values])
            rows.append(dict(mes=MESES[m-1], ops=len(b), acerto=(b.res > 0).mean()*100, liq=b.res.sum(),
                             maxdd=maxdd(path), menor=b.bal.min()))
        else:
            rows.append(dict(mes=MESES[m-1], ops=0, acerto=np.nan, liq=0.0, maxdd=0.0, menor=np.nan))
    n = len(a)
    path = np.concatenate([[CAP0], a.bal.values])
    rows.append(dict(mes='total', ops=n, acerto=(a.res > 0).mean()*100 if n else np.nan, liq=a.res.sum() if n else 0.0,
                     maxdd=maxdd(path), menor=a.bal.min() if n else CAP0))
    return rows

def controle(t, strats, n_rem, cost, rng):
    full = t[t.estrategia.isin(strats)].sort_values(['saida', 'entrada'])
    res = full.rs.values - cost
    n = len(res); out_net, out_dd = [], []
    for _ in range(NSORT):
        keep = np.ones(n, bool); keep[rng.choice(n, n_rem, replace=False)] = False
        r = res[keep]
        out_net.append(r.sum()); out_dd.append(maxdd(np.concatenate([[CAP0], CAP0 + r.cumsum()])))
    return np.array(out_net), np.array(out_dd)

def main():
    t = load()
    rng = np.random.default_rng(42)
    cells = []; trades_store = {}
    for (sname, strats), K, prio, netting in itertools.product(SETS.items(), [1, 2, 3], ['chegada', 'ranking'], [False, True]):
        acc, cut, blk = accept(t, strats, K, prio, netting)
        nfull = int(t.estrategia.isin(strats).sum())
        for cost in COSTS:
            a, quebra, worst = simula(t, acc, cost)
            ms = mes_stats(a)
            tot = ms[-1]
            ctl_net, ctl_dd = controle(t, strats, nfull - len(acc), cost, rng)
            pct_net = (ctl_net <= tot['liq']).mean() * 100
            pct_dd = (ctl_dd >= tot['maxdd']).mean() * 100
            cells.append(dict(conjunto=sname, K=K, prio=prio, netting='NETTING' if netting else 'independente', custo=cost,
                              ops=tot['ops'], acerto=tot['acerto'], liquido=tot['liq'], maxdd=tot['maxdd'],
                              lucro_dd=tot['liq'] / tot['maxdd'] if tot['maxdd'] else np.nan, menor_saldo=tot['menor'],
                              pior_intradia=worst, quebrou='SIM ' + str(quebra)[:10] if quebra is not None else 'nao',
                              cortes_teto=cut, bloq_netting=blk, ctl_media=ctl_net.mean(), pct_liq=pct_net, pct_dd=pct_dd,
                              meses=ms))
            trades_store[(sname, K, prio, netting, cost)] = a
            print(f"{sname:24s} K={K} {prio:8s} {'NET' if netting else 'ind'} c={cost:.0f}  ops={tot['ops']:4d} liq={tot['liq']:9.0f} dd={tot['maxdd']:7.0f} cut={cut:4d} blk={blk:4d} pct={pct_net:5.1f} quebra={quebra}", flush=True)
    ref = {}
    for cost in COSTS:
        ref[cost] = {e: (g.rs - cost).sum() for e, g in t.groupby('estrategia')}
    sem_teto = {}
    for sname, strats in SETS.items():
        for cost in COSTS:
            full = t[t.estrategia.isin(strats)].sort_values('saida'); r = full.rs.values - cost
            sem_teto[(sname, cost)] = (r.sum(), maxdd(np.concatenate([[CAP0], CAP0 + r.cumsum()])), len(r))
    wf = []
    for sname, netting, cost in itertools.product(SETS, ['independente', 'NETTING'], COSTS):
        cand = [c for c in cells if c['conjunto'] == sname and c['netting'] == netting and c['custo'] == cost]
        tot, esc = 0.0, []
        for m in range(1, 11):
            if m == 1:
                ch = next(c for c in cand if c['K'] == 2 and c['prio'] == 'chegada')
            else:
                def score(c):
                    ml = c['meses'][:m-1]; l = sum(x['liq'] for x in ml)
                    dd = max(x['maxdd'] for x in ml)
                    return l / dd if dd else l
                ch = max(cand, key=score)
            tot += ch['meses'][m-1]['liq']; esc.append(f"K{ch['K']}{'c' if ch['prio']=='chegada' else 'r'}")
        wf.append(dict(conjunto=sname, netting=netting, custo=cost, liquido_wf=tot, escolhas=' '.join(esc)))
        print('WF', sname, netting, cost, round(tot), ' '.join(esc), flush=True)
    flat = [{k: v for k, v in c.items() if k != 'meses'} for c in cells]
    pd.DataFrame(flat).to_csv(os.path.join(HERE, 'resultado.csv'), index=False, float_format='%.2f')
    mrows = []
    for c in cells:
        for r in c['meses']:
            mrows.append(dict(conjunto=c['conjunto'], K=c['K'], prio=c['prio'], netting=c['netting'], custo=c['custo'], **r))
    pd.DataFrame(mrows).to_csv(os.path.join(HERE, 'resultado_mensal.csv'), index=False, float_format='%.2f')
    reps = {'K2_chegada_indep_5semWinc1': ('5 sem Win_c1', 2, 'chegada', False, 0.0),
            'K3_chegada_NETTING_5semWinc1': ('5 sem Win_c1', 3, 'chegada', True, 0.0),
            'K2_chegada_indep_4semWdoRet_Win': ('4 sem WdoRet (Win)', 2, 'chegada', False, 0.0)}
    os.makedirs(os.path.join(HERE, 'trades'), exist_ok=True)
    for nm, key in reps.items():
        a = trades_store[key]
        a[['estrategia','entrada','saida','lado','qtd','preco_entrada','preco_saida','motivo','pontos','rs']].to_csv(
            os.path.join(HERE, 'trades', nm + '.csv'), index=False)
    escreve_md(cells, wf, ref, sem_teto, len(cells) // 2)

def fmt(x, d=0):
    if x is None or (isinstance(x, float) and np.isnan(x)): return '-'
    return f"{x:,.{d}f}".replace(',', '_').replace('.', ',').replace('_', '.')

def escreve_md(cells, wf, ref, sem_teto, ncel):
    L = []
    L.append('# Frente C: portfolio com teto de K contratos simultaneos\n')
    L.append(f'Base: resultados/*.csv, WIN 02/01-05/10/2026, 1 contrato por estrategia, conta R$1.000. **Celulas olhadas: {ncel}** (4 conjuntos x K{{1,2,3}} x prioridade{{chegada, ranking}} x {{independente, NETTING}}), cada uma com custo 0 e R$2/op. A escolha walk-forward abaixo so recombina essas celulas.\n')
    L.append('**Premissas.** (1) A saida de cada estrategia e a gravada no CSV; uma entrada cortada some. (2) Teto: entrada so aceita se posicoes abertas (de qualquer estrategia) < K; saida no mesmo minuto libera a vaga. (3) NETTING: entrada contraria a posicao aberta de outra estrategia e BLOQUEADA (coluna bloq.), contada a parte do corte por teto; a ordem de checagem e netting primeiro, teto depois. (4) Prioridade so atua em empate de minuto de entrada; "chegada" = ordem estavel do CSV, "ranking" = R$/op dos meses anteriores (walk-forward; jan sem historico = ordem alfabetica). Como estrategias raramente entram no mesmo minuto, as duas prioridades diferem pouco. (5) Caixa corrido por ordem de saida, quebra = saldo <= 0 (portfolio para). A margem do WIN nao e checada (R$1.000 cobre 3 contratos). (6) Pior saldo intradia = saldo fechado + resultado final das operacoes abertas, no pior instante (aproximacao). (7) O teto de 10% do saldo do Deslocamento usa o saldo da propria estrategia, nao o caixa comum: desvio declarado, nao recalculado. (8) Bases escolhidas olhando 2026: o walk-forward protege so a camada de combinacao.\n')
    L.append('## Referencias\n')
    L.append('| item | liquido s/custo | liquido R$2/op |\n|---|---|---|')
    for e in ref[0.0]:
        L.append(f"| {e} isolada | {fmt(ref[0.0][e])} | {fmt(ref[2.0][e])} |")
    for s in SETS:
        a, b = sem_teto[(s, 0.0)], sem_teto[(s, 2.0)]
        L.append(f"| soma sem teto: {s} ({a[2]} ops) | {fmt(a[0])} (DD {fmt(a[1])}) | {fmt(b[0])} (DD {fmt(b[1])}) |")
    L.append('\nMelhor isolada: WinCincoMedias.\n')
    L.append('## Resumo das celulas (total jan-out)\n')
    L.append('`pct liq` = percentil do liquido da celula entre 200 sorteios que removem ao acaso a mesma quantidade de entradas (cortes + bloqueios); `pct DD` = % dos sorteios com maior queda que a celula (alto = celula protege mais que o acaso).\n')
    L.append('| conjunto | K | prio | visao | custo | ops | acerto% | liquido | maxDD | lucro/DD | menor saldo | pior intradia | quebrou | cortes teto | bloq netting | pct liq | pct DD |\n|' + '---|' * 17)
    for c in cells:
        L.append(f"| {c['conjunto']} | {c['K']} | {c['prio']} | {c['netting']} | {fmt(c['custo'])} | {c['ops']} | {fmt(c['acerto'],1)} | {fmt(c['liquido'])} | {fmt(c['maxdd'])} | {fmt(c['lucro_dd'],2)} | {fmt(c['menor_saldo'])} | {fmt(c['pior_intradia'])} | {c['quebrou']} | {c['cortes_teto']} | {c['bloq_netting']} | {fmt(c['pct_liq'],1)} | {fmt(c['pct_dd'],1)} |")
    L.append('\n## Escolha walk-forward da celula (K, prioridade) so com meses anteriores\n')
    L.append('Em cada mes vale a celula (K x prioridade, dentro do conjunto/visao) com maior liquido acumulado / pior queda mensal dos meses anteriores; jan = K2 chegada. c = chegada, r = ranking.\n')
    L.append('| conjunto | visao | custo | liquido walk-forward | escolhas jan..out |\n|---|---|---|---|---|')
    for w in wf:
        L.append(f"| {w['conjunto']} | {w['netting']} | {fmt(w['custo'])} | {fmt(w['liquido_wf'])} | {w['escolhas']} |")
    L.append('\n## Tabelas mensais por celula\n')
    byk = collections.OrderedDict()
    for c in cells:
        byk.setdefault((c['conjunto'], c['K'], c['prio'], c['netting']), {})[c['custo']] = c
    for (s, K, p, n), d in byk.items():
        c0, c2 = d[0.0], d[2.0]
        L.append(f"\n### {s} | K={K} | {p} | {n} (cortes teto {c0['cortes_teto']}, bloq netting {c0['bloq_netting']})\n")
        L.append('| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |\n|---|---|---|---|---|---|---|---|---|')
        for a, b in zip(c0['meses'], c2['meses']):
            L.append(f"| {a['mes']} | {a['ops']} | {fmt(a['acerto'],1)} | {fmt(a['liq'])} | {fmt(a['maxdd'])} | {fmt(a['menor'])} | {fmt(b['liq'])} | {fmt(b['maxdd'])} | {fmt(b['menor'])} |")
        L.append(f"\nQuebrou: s/custo {c0['quebrou']}; R$2 {c2['quebrou']}.")
    open(os.path.join(HERE, 'resultado.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')

if __name__ == '__main__':
    main()
