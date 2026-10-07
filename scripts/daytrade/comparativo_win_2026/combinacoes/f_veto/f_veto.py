"""Frente F: veto cruzado por posicao REAL contraria de outra estrategia. Celulas: f1, f2, f3 (pre-registradas no TODO)."""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, '..', 'd_regime_1030'))
sys.path.insert(0, os.path.join(AQUI, '..', '..'))
from lib_comb import *
import dados as D

rng = np.random.default_rng(20261007)
CELULAS = ['f1', 'f2', 'f3']
MIN = pd.Timedelta(minutes=1)


def prepara():
    t = carrega()
    ev = pd.read_parquet(os.path.join(F0, 'eventos.parquet'))
    ev['entrada'] = pd.to_datetime(ev.entrada)
    t = t.merge(ev[['estrategia', 'entrada', 'linha_voto'] + [f'{e}.posicao' for e in ESTR]], on=['estrategia', 'entrada'], how='left')
    assert t.linha_voto.notna().all() and len(t) == 1421
    m1c = D.m1().close
    t['close_linha'] = m1c.reindex(pd.DatetimeIndex(t.linha_voto)).values   # close da ultima M1 fechada
    # pares (x, y): trade y de OUTRA estrategia aberto na linha de x (entrada_y < linha+1min <= saida_y)
    ent = t.entrada.values; sai = t.saida.values; est = t.estrategia.values
    T = (pd.DatetimeIndex(t.linha_voto) + MIN).values
    xi, yi = [], []
    for i in range(len(t)):
        m = (ent < T[i]) & (sai >= T[i]) & (est != est[i])
        for j in np.flatnonzero(m): xi.append(i); yi.append(j)
    xi = np.array(xi); yi = np.array(yi)
    # confere com .posicao da F0
    chk = 0; tot = 0
    for e in ESTR:
        pos = np.zeros(len(t))
        sel = xi[est[yi] == e]; pos[sel] = t.lado.values[yi[est[yi] == e]]
        ref = t[f'{e}.posicao'].fillna(0).values.copy()
        ref[est == e] = 0
        chk += int((pos != ref).sum()); tot += len(t)
    print(f'pares (x,y) = {len(xi)}; divergencias vs .posicao da F0: {chk}', flush=True)
    return t, xi, yi, chk


def veto(t, xi, yi, cel, lado_y=None, so_pares=None):
    """bool[n]: entrada vetada. lado_y = lados (por trade) usados para as posicoes vetadoras (placebo troca)."""
    ly = t.lado.values if lado_y is None else lado_y
    lx = t.lado.values[xi]
    fam = np.array([FAM[e] for e in t.estrategia.values])
    ok = ly[yi] == -lx
    if cel == 'f1':
        ok &= fam[xi] != fam[yi]
    if cel == 'f3':
        ok &= (ly[yi] * (t.close_linha.values[xi] - t.preco_entrada.values[yi])) > 0
    v = np.zeros(len(t), bool); v[xi[ok]] = True
    return v


def main():
    t, xi, yi, div = prepara()
    base = {c: (liquido(t, c), *caixa(t, c)) for c in CUSTOS}
    est = t.estrategia.values
    linhas = []; mens = {}
    for cel in CELULAS:
        v = veto(t, xi, yi, cel)
        k = t[~v]; nrem = int(v.sum())
        porest = {e: int((v & (est == e)).sum()) for e in ESTR}
        print(cel, 'vetadas', nrem, porest, flush=True)
        sort = [[], []]; plac = [[], []]
        idx_e = {e: np.flatnonzero(est == e) for e in ESTR}
        for _ in range(NSORT):
            m = np.zeros(len(t), bool)
            for e in ESTR:
                if porest[e]: m[rng.choice(idx_e[e], porest[e], replace=False)] = True
            kk = t[~m]
            # placebo: cada posicao vetadora ganha um lado sorteado
            ly = rng.choice([-1, 1], len(t))
            k1 = t[~veto(t, xi, yi, cel, lado_y=ly)]
            for i, c in enumerate(CUSTOS): sort[i].append(liquido(kk, c)); plac[i].append(liquido(k1, c))
        # fracao vetada media no placebo (informa se o placebo e comparavel)
        fr = np.mean([veto(t, xi, yi, cel, lado_y=rng.choice([-1, 1], len(t))).sum() for _ in range(50)])
        for i, c in enumerate(CUSTOS):
            liq = liquido(k, c); _, dd, mn, qb = caixa(k, c)
            linhas.append(dict(celula=cel, custo=c, ops=len(k), vetadas=nrem, liquido=round(liq), maxDD=round(dd),
                               lucro_DD=round(liq / dd, 2) if dd else float('nan'), menor_saldo=round(mn), quebrou='sim' if qb else 'nao',
                               delta_vs_soma=round(liq - base[c][0]), liq_vetadas=round(liquido(t[v], c)),
                               pct_sorteio=round(pct(liq, sort[i]), 1), pct_placebo_lado=round(pct(liq, plac[i]), 1), vetadas_no_placebo=round(fr)))
            mens[(cel, c)] = tabela_mensal(k, c)
            print(linhas[-1], flush=True)
        if cel in ('f1', 'f2'):
            cols = ['estrategia', 'entrada', 'saida', 'lado', 'qtd', 'preco_entrada', 'preco_saida', 'motivo', 'pontos', 'rs']
            k.to_csv(os.path.join(AQUI, 'trades', f'{cel}.csv'), index=False, columns=cols)
            t[v].to_csv(os.path.join(AQUI, 'trades', f'{cel}_vetadas.csv'), index=False, columns=cols)
        # metades do ano (criterio de encerramento da proposta 4)
        a = t[~v & (t.mes <= 5)].rs.sum() - t[(t.mes <= 5)].rs.sum(); b = t[~v & (t.mes >= 6)].rs.sum() - t[(t.mes >= 6)].rs.sum()
        print(f'  delta s/custo jan-mai {a:.0f} | jun-out {b:.0f}', flush=True)
        linhas[-1]['_h1'] = round(a); linhas[-1]['_h2'] = round(b); linhas[-2]['_h1'] = round(a); linhas[-2]['_h2'] = round(b)
    res = pd.DataFrame(linhas)
    res.rename(columns={'_h1': 'delta_jan_mai_s_custo', '_h2': 'delta_jun_out_s_custo'}).to_csv(os.path.join(AQUI, 'resultado.csv'), index=False)
    isol = {e: [liquido(t[t.estrategia == e], c) for c in CUSTOS] for e in ESTR}
    o = ['# Frente F: veto cruzado por posicao real contraria\n']
    o.append('Base: resultados/*.csv, WIN 02/01-05/10/2026, 5 estrategias (sem Win_c1; Win_c1 ~ Win), 1 contrato, R$1.000 corrido, quebra = saldo <= 0. **Celulas olhadas: 3** (f1, f2, f3), cada uma com custo 0 e R$2/op.\n')
    o.append('Regra: uma entrada de X e bloqueada se, na ultima M1 fechada antes dela, outra estrategia tem posicao REAL aberta do lado contrario (entrada < linha+1min <= saida; confere com `.posicao` da F0: ' + str(div) + ' divergencias). f1: so a outra familia (tendencia = Win, Cinco, Desloc; retangulo = RetEma34, WdoRet). f2: qualquer outra (NETTING). f3: como f2, mas so se a contraria esta no lucro pelo close da ultima M1 fechada.\n')
    o.append('**Sem parametros, sem walk-forward** (as 3 celulas foram escritas antes). NAO e validacao fora da amostra: as bases foram escolhidas olhando 2026. As posicoes vetadoras vem do replay original (uma entrada vetada continua contando como posicao para vetar as outras: aproximacao); as saidas das demais ficam inalteradas.\n')
    o.append('## Referencias\n')
    o.append('| item | liquido s/custo | liquido R$2/op |\n|---|---|---|')
    for e in ESTR: o.append(f'| {e} isolada | {f0(isol[e][0])} | {f0(isol[e][1])} |')
    o.append(f'| **soma sem filtro (5 sem Win_c1, {len(t)} ops)** | {f0(base[0.0][0])} (DD {f0(base[0.0][2])}) | {f0(base[2.0][0])} (DD {f0(base[2.0][2])}) |')
    o.append('| melhor isolada: WinCincoMedias | 8.859 | 8.243 |\n')
    o.append('## Resumo (total jan-out)\n')
    o.append('`liq_vetadas` = o que as entradas vetadas teriam rendido (negativo = o veto acertou). `pct_sorteio` = percentil do liquido contra 200 sorteios que descartam ao acaso o mesmo numero de entradas por estrategia. `pct_placebo_lado` = contra 200 sorteios em que o lado de cada posicao vetadora e trocado ao acaso (`vetadas_no_placebo` = media de vetos desse placebo, ~metade das reais para f2 se os lados fossem independentes). Percentil alto = o veto faz melhor que o acaso.\n')
    cols = [c for c in res.columns if not c.startswith('_')]
    o.append('| ' + ' | '.join(cols) + ' |\n|' + '---|' * len(cols))
    for _, r in res.iterrows(): o.append('| ' + ' | '.join(str(r[c]) for c in cols) + ' |')
    o.append('\n## Estabilidade entre metades (delta do veto sem custo contra a soma sem filtro)\n')
    o.append('| celula | jan-mai | jun-out |\n|---|---|---|')
    for cel in CELULAS:
        r = res[(res.celula == cel) & (res.custo == 0.0)].iloc[0]; o.append(f'| {cel} | {r["_h1"]} | {r["_h2"]} |')
    o.append('\n## Vetadas por estrategia\n')
    o.append('| celula | ' + ' | '.join(ESTR) + ' |\n|' + '---|' * (len(ESTR) + 1))
    for cel in CELULAS:
        v = veto(t, xi, yi, cel); o.append(f'| {cel} | ' + ' | '.join(str(int((v & (est == e)).sum())) for e in ESTR) + ' |')
    o.append('\n## Tabelas mensais (liquido R$; por data de saida)\n')
    o.append('### Soma sem filtro\n\n**sem custo**\n\n' + md_tabela(tabela_mensal(t, 0.0)) + '\n\n**R$2/op**\n\n' + md_tabela(tabela_mensal(t, 2.0)))
    for cel in CELULAS:
        for c in CUSTOS:
            q = res[(res.celula == cel) & (res.custo == c)].iloc[0]
            o.append(f'\n### {cel} - {"sem custo" if c == 0 else "R$2/op"} (quebra: {q.quebrou}; menor saldo R$ {f0(q.menor_saldo)})\n\n' + md_tabela(mens[(cel, c)]))
    open(os.path.join(AQUI, 'resultado.md'), 'w', encoding='utf-8').write('\n'.join(o) + '\n')


if __name__ == '__main__':
    main()
