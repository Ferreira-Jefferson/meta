"""Frente D: regime diario das 10:30 (voto do WinDeslocamentoMatinal na barra da decisao). 4 celulas pre-registradas no TODO."""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lib_comb import *

H1030 = 10 * 60 + 30
DEC = {}
rng = np.random.default_rng(20261006)
CELULAS = ['d1', 'd2', 'd3', 'd4']


def regimes() -> pd.Series:
    v = pd.read_parquet(os.path.join(F0, 'votos.parquet'))['WinDeslocamentoMatinal.voto']
    out = {}; DEC.clear()
    for dia, s in v.groupby(v.index.normalize()):
        alvo = s.index[0] + pd.Timedelta(minutes=89)   # barra da decisao: 90 M1 ja fechadas (vale de alvo+1min)
        k = s.index.searchsorted(alvo)
        out[dia] = int(s.iloc[k]) if k < len(s) else 0
        DEC[dia] = alvo + pd.Timedelta(minutes=1)
    return pd.Series(out)


def remove(t: pd.DataFrame, cel: str, reg: pd.Series) -> np.ndarray:
    """True = entrada removida pela celula `cel` dado o regime diario `reg` (indexado por dia)."""
    r = t.dia.map(reg).fillna(0).astype(int).values
    tarde = (t.entrada.values >= t.dia.map(DEC).values)
    tend = t.estrategia.isin(['Win', 'WinCincoMedias']).values  # Deslocamento isento: e' a fonte do regime
    ret = t.estrategia.isin(RET).values
    contra = (r != 0) & (r != t.lado.values)
    rem = np.zeros(len(t), bool)
    if cel in ('d1', 'd4'):
        rem |= tarde & tend & contra
    if cel == 'd2':
        rem |= tarde & tend & (contra | (r == 0))
    if cel in ('d3', 'd4'):
        rem |= tarde & ret & (r != 0)
    return rem


def afetadas(cel):
    return (['Win', 'WinCincoMedias'] if cel in ('d1', 'd2', 'd4') else []) + (RET if cel in ('d3', 'd4') else [])


def aleatorio(t, cel, n_rem):
    """Sorteia DIAS (regime e' diario) e remove as entradas pos-10:30 das afetadas ate' chegar perto de n_rem."""
    el = t[(t.entrada >= t.dia.map(DEC)) & t.estrategia.isin(afetadas(cel))]
    cont = el.groupby('dia').size()
    dias = cont.index.values.copy(); rng.shuffle(dias)
    cum = np.cumsum(cont.loc[dias].values)
    k = int(np.searchsorted(cum, n_rem))
    if k >= len(dias): k = len(dias) - 1
    if k > 0 and abs(cum[k - 1] - n_rem) < abs(cum[k] - n_rem): k -= 1
    ds = set(dias[:k + 1])
    return t.index.isin(el.index[el.dia.isin(ds)])


def md_res(res):
    cols = list(res.columns)
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    for _, r in res.iterrows():
        out.append('| ' + ' | '.join(('-' if (isinstance(r[c], float) and np.isnan(r[c])) else str(r[c])) for c in cols) + ' |')
    return '\n'.join(out)


def main():
    t = carrega(); reg = regimes()
    print(f'dias {len(reg)}: compra {int((reg==1).sum())} venda {int((reg==-1).sum())} sem sinal {int((reg==0).sum())}', flush=True)
    base = {c: (liquido(t, c), *caixa(t, c)) for c in CUSTOS}
    linhas = []; mens = {}
    r = t.dia.map(reg).fillna(0).astype(int)
    tarde = t.entrada >= t.dia.map(DEC)
    estado = np.where(r == 0, 'sem sinal', np.where(r == t.lado, 'a favor', 'contra'))
    desc = t[tarde].assign(estado=estado[tarde.values]).groupby(['estrategia', 'estado']).rs.agg(['size', 'mean', 'sum'])
    for cel in CELULAS:
        rem = remove(t, cel, reg)
        k = t[~rem]; nrem = int(rem.sum())
        sort = [[], []]; plac = [[], []]; perm = [[], []]
        for _ in range(NSORT):
            kk = t[~aleatorio(t, cel, nrem)]
            fl = reg.copy(); com = fl.index[fl != 0]
            fl.loc[com] = fl.loc[com].values * rng.choice([-1, 1], len(com))
            k1 = t[~remove(t, cel, fl)]
            pp = reg.copy(); pp[:] = rng.permutation(reg.values)
            k2 = t[~remove(t, cel, pp)]
            for i, c in enumerate(CUSTOS):
                sort[i].append(liquido(kk, c)); plac[i].append(liquido(k1, c)); perm[i].append(liquido(k2, c))
        for i, c in enumerate(CUSTOS):
            liq = liquido(k, c); _, dd, mn, qb = caixa(k, c)
            linhas.append(dict(celula=cel, custo=c, ops=len(k), removidas=nrem, liquido=round(liq), maxDD=round(dd),
                               lucro_DD=round(liq / dd, 2) if dd else float('nan'), menor_saldo=round(mn), quebrou='sim' if qb else 'nao',
                               delta_vs_soma=round(liq - base[c][0]), pct_sorteio_dias=round(pct(liq, sort[i]), 1),
                               pct_placebo_lado=(round(pct(liq, plac[i]), 1) if cel != 'd3' else float('nan')),
                               pct_perm_dias=round(pct(liq, perm[i]), 1)))
            mens[(cel, c)] = tabela_mensal(k, c)
            print(linhas[-1], flush=True)
        if cel in ('d1', 'd4'):
            k.to_csv(os.path.join(AQUI, 'trades', f'{cel}.csv'), index=False,
                     columns=['estrategia', 'entrada', 'saida', 'lado', 'qtd', 'preco_entrada', 'preco_saida', 'motivo', 'pontos', 'rs'])
    res = pd.DataFrame(linhas); res.to_csv(os.path.join(AQUI, 'resultado.csv'), index=False)
    isol = {e: [liquido(t[t.estrategia == e], c) for c in CUSTOS] for e in ESTR}
    o = ['# Frente D: estado das 10:30 do Deslocamento como regime diario\n']
    o.append('Base: resultados/*.csv, WIN 02/01-05/10/2026, 5 estrategias (sem Win_c1; Win_c1 ~ Win), 1 contrato, R$1.000 corrido, quebra = saldo <= 0. **Celulas olhadas: 4** (d1-d4), cada uma com custo 0 e R$2/op.\n')
    o.append('**Sem parametros, sem walk-forward:** as regras foram escritas no TODO antes de rodar e nao ha nada a ajustar. Isto NAO e validacao fora da amostra: as 5 estrategias base foram escolhidas olhando 2026.\n')
    o.append(f'Regime = voto do WinDeslocamentoMatinal na barra da decisao (1a M1 do dia + 89 min, ~10:29-10:33 conforme a abertura, vale 1 min depois; "depois das 10:30" = entrada >= essa hora de decisao do dia). Dias: {int((reg==1).sum())} compra, {int((reg==-1).sum())} venda, {int((reg==0).sum())} sem sinal. Entradas antes das 10:30 nao sao afetadas. O Deslocamento fica isento (e a fonte do regime). Operacoes removidas, saidas das demais inalteradas (aproximacao: nao refaz a trajetoria da estrategia sem a entrada).\n')
    o.append('d1: tendencia (Win, Cinco) pos-10:30 so a favor do sinal, sem sinal vale tudo. d2: igual, mas sem sinal a tendencia nao opera. d3: retangulo (RetEma34, WdoRet) pos-10:30 so em dia sem sinal. d4 = d1 + d3.\n')
    o.append('## Referencias\n')
    o.append('| item | liquido s/custo | liquido R$2/op |\n|---|---|---|')
    for e in ESTR: o.append(f'| {e} isolada | {f0(isol[e][0])} | {f0(isol[e][1])} |')
    o.append(f'| **soma sem filtro (5 sem Win_c1, {len(t)} ops)** | {f0(base[0.0][0])} (DD {f0(base[0.0][2])}) | {f0(base[2.0][0])} (DD {f0(base[2.0][2])}) |')
    o.append('| melhor isolada: WinCincoMedias | 8.859 | 8.243 |\n')
    o.append('## Resumo (total jan-out)\n')
    o.append('`pct_sorteio_dias` = percentil do liquido contra 200 sorteios de DIAS que removem o mesmo numero de entradas pos-10:30 das mesmas estrategias; `pct_placebo_lado` = contra 200 sorteios com o lado do sinal de cada dia trocado ao acaso (d3 nao usa lado); `pct_perm_dias` = contra 200 permutacoes do estado (compra/venda/sem sinal) entre os dias. Percentil alto = a regra faz melhor que o acaso.\n')
    o.append(md_res(res))
    o.append('\n## Contexto: R$/op das entradas pos-10:30 por estado (so descritivo, nao escolheu nada)\n')
    o.append('| estrategia | estado | n | R$/op | R$ total |\n|---|---|---|---|---|')
    for (e, s), rr in desc.iterrows(): o.append(f'| {e} | {s} | {int(rr["size"])} | {f0(rr["mean"],2)} | {f0(rr["sum"])} |')
    o.append('\n## Tabelas mensais (liquido R$; por data de saida)\n')
    o.append('### Soma sem filtro\n\n**sem custo**\n\n' + md_tabela(tabela_mensal(t, 0.0)) + '\n\n**R$2/op**\n\n' + md_tabela(tabela_mensal(t, 2.0)))
    for cel in CELULAS:
        for c in CUSTOS:
            q = res[(res.celula == cel) & (res.custo == c)].iloc[0]
            o.append(f'\n### {cel} - {"sem custo" if c == 0 else "R$2/op"} (quebra: {q.quebrou}; menor saldo R$ {f0(q.menor_saldo)})\n\n' + md_tabela(mens[(cel, c)]))
    open(os.path.join(AQUI, 'resultado.md'), 'w', encoding='utf-8').write('\n'.join(o) + '\n')


if __name__ == '__main__':
    main()
