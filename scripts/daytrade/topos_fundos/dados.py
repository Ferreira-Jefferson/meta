"""Dados do WIN: M1 sem leilões (bases auditadas) -> barras M15 do pregão, com contrato e ATR.

Cada período é montado sozinho (médias começam no início dele), como em toda a pesquisa.
"""
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]
PERIODOS = {  # nome: (arquivo M1 auditado, início, fim exclusivo)
    "IS": ("data/win_sem_leiloes/m1_WIN$N_2022_2025.parquet", "2022-01-01", "2025-10-01"),
    "OOS": ("data/win_sem_leiloes/m1_WIN$N.parquet", "2025-10-01", "2026-10-06"),
    "virgem": ("data/win_sem_leiloes/m1_WIN$N_2021_virgem.parquet", "2021-10-08", "2022-01-01"),
}
ATR_N = 14


def vencimentos():
    """Vencimentos do WIN: quarta-feira mais próxima do dia 15 dos meses pares."""
    v = []
    for y in range(2021, 2027):
        for m in (2, 4, 6, 8, 10, 12):
            d15 = date(y, m, 15)
            dif = 2 - d15.weekday()
            if dif > 3: dif -= 7
            if dif < -3: dif += 7
            v.append(pd.Timestamp(d15 + timedelta(days=dif)))
    return np.array(v, dtype="datetime64[ns]")


def atr(b):
    """ATR(14) conhecido ANTES da barra (shift 1), contínuo dentro do contrato; 1º TR do pregão = máxima - mínima."""
    pc = b.close.shift(1).where(b.dia == b.dia.shift(1))
    tr = pd.concat([b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1).max(axis=1)
    return tr.groupby(b.contrato).transform(lambda s: s.rolling(ATR_N, min_periods=5).mean().shift(1))


def m15(periodo):
    arq, ini, fim = PERIODOS[periodo]
    m1 = pd.read_parquet(RAIZ / arq)
    m1 = m1[(m1.index >= ini) & (m1.index < fim)]
    b = m1.resample("15min").agg(dict(open="first", high="max", low="min", close="last", real_volume="sum")).dropna()
    b["dia"] = b.index.normalize()
    b["contrato"] = np.searchsorted(vencimentos(), b.dia.values, side="right")
    b["atr"] = atr(b)
    return b
