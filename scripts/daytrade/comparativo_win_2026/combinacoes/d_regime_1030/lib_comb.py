"""Utilitarios comuns das frentes D e F: carga dos trades, metricas (mes jan-out, caixa R$1.000, quebra), percentil."""
from __future__ import annotations
import os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
COMB = os.path.abspath(os.path.join(HERE, '..'))
RES = os.path.abspath(os.path.join(COMB, '..', 'resultados'))
F0 = os.path.join(COMB, 'f0_fundacao')
ESTR = ['Win', 'WinCincoMedias', 'WinDeslocamentoMatinal', 'WinRetanguloEma34', 'WdoRetangulo']  # 5 sem Win_c1
TEND = ['Win', 'WinCincoMedias', 'WinDeslocamentoMatinal']
RET = ['WinRetanguloEma34', 'WdoRetangulo']
FAM = {**{e: 'T' for e in TEND}, **{e: 'R' for e in RET}}
MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out']
CAP0 = 1000.0
CUSTOS = [0.0, 2.0]
NSORT = 200


def carrega() -> pd.DataFrame:
    fs = [pd.read_csv(os.path.join(RES, e + '.csv')) for e in ESTR]
    t = pd.concat(fs, ignore_index=True)
    t['entrada'] = pd.to_datetime(t.entrada, format='mixed')
    t['saida'] = pd.to_datetime(t.saida, format='mixed')
    t['mes'] = t.saida.dt.month
    t['dia'] = t.entrada.dt.normalize()
    t['hmin'] = t.entrada.dt.hour * 60 + t.entrada.dt.minute
    return t.sort_values(['entrada', 'estrategia'], kind='stable').reset_index(drop=True)


def caixa(x: pd.DataFrame, custo: float):
    """(liquido, maxDD, menor saldo, quebrou) com caixa corrido por ordem de saida; quebra = saldo <= 0."""
    if len(x) == 0:
        return 0.0, 0.0, CAP0, False
    a = x.sort_values(['saida', 'entrada'], kind='stable')
    bal = CAP0 + np.cumsum(a.rs.values - custo)
    pk = np.maximum.accumulate(np.r_[CAP0, bal])[1:]
    return float(bal[-1] - CAP0), float((pk - bal).max()), float(bal.min()), bool(bal.min() <= 0)


def liquido(x, custo):
    return float(x.rs.sum() - custo * len(x))


def tabela_mensal(x: pd.DataFrame, custo: float) -> pd.DataFrame:
    """linhas = estrategias + soma, colunas = jan..out + total (liquido)."""
    rows = {}
    for e in ESTR:
        s = x[x.estrategia == e]
        rows[e] = [s[s.mes == m].rs.sum() - custo * (s.mes == m).sum() for m in range(1, 11)]
    rows['SOMA'] = [x[x.mes == m].rs.sum() - custo * (x.mes == m).sum() for m in range(1, 11)]
    df = pd.DataFrame(rows, index=MESES).T
    df['total'] = df.sum(axis=1)
    df['ops'] = [int((x.estrategia == e).sum()) for e in ESTR] + [len(x)]
    return df


def f0(v, d=0):
    return f'{v:,.{d}f}'.replace(',', '.') if d == 0 else f'{v:,.{d}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def md_tabela(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ['| estrategia | ' + ' | '.join(cols) + ' |', '|' + '---|' * (len(cols) + 1)]
    for i, r in df.iterrows():
        out.append(f'| {i} | ' + ' | '.join(f0(r[c]) for c in cols) + ' |')
    return '\n'.join(out)


def pct(valor: float, dist) -> float:
    d = np.asarray(dist, float)
    return 100.0 * (np.mean(d < valor) + 0.5 * np.mean(d == valor))
