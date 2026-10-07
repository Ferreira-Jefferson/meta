"""Base da frente N (estrategia nova) -- mesma interface de ../../dados.py, para os blocos DEV e VAL.

Fonte: WIN$N (preco CRU do contrato principal, grade de 5 pts conferida: 0 barras fora), baixado por baixa_dev.py,
2021-12-01 a 2025-09-30. NAO usar WIN@ deste terminal (barras ajustadas).
  - `m1()`: todas as M1 baixadas (dez/2021 serve so' de aquecimento de medias/ATR).
  - `dias(bloco)`: pregoes do bloco "DEV" (2022-01-03..2024-06-28) ou "VAL" (2024-07-01..2025-09-30).
  - `ticks(dia)`: SEMPRE sinteticos -- 4 ticks por M1 no padrao do Testador (abertura, extremo mais proximo,
    outro extremo, fechamento), igual a dados._sinteticos. Nao ha tick real nesse periodo.

Cuidados do dado (declarar em todo resultado):
  - WIN$N cru emenda contratos: na rolagem (bimestral) ha degrau de 2.000-4.000 pts entre o fechamento de D-1
    e a abertura de D. Indicador que atravessa dias (EMA longa, ATR com fechamento anterior) ve o degrau.
  - Horario do pregao muda: termina 17:54 em parte de 2022/2023 (Q2-Q3) e 18:24 no resto. Zeragem causal tem de
    usar um horario fixo que existe em todos os pregoes (ex.: 17:50), nunca "ultima barra do dia" (olha o futuro).
Regras de execucao do Testador: as mesmas de ../../dados.py (bid = ask = last; limite enche ao tocar, no preco do
limite; stop executa no last do tick que toca/atravessa).
"""
from datetime import date
from functools import lru_cache
from pathlib import Path
import sys
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[5]
DADOS = ROOT / "data" / "comparativo_win_2026"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dados import _sinteticos, ms, ts, TICK, RS_PONTO, CAPITAL, COLUNAS, trade  # noqa: E402,F401

BLOCOS = {"DEV": (date(2022, 1, 3), date(2024, 6, 28)), "VAL": (date(2024, 7, 1), date(2025, 9, 30))}


@lru_cache(maxsize=1)
def m1() -> pd.DataFrame:
    """M1 do WIN$N: index = abertura da barra (servidor); open/high/low/close/tick_volume/real_volume."""
    return pd.read_parquet(DADOS / "m1_WIN$N_2022_2025.parquet")


def dias(bloco: str = "DEV") -> list:
    ini, fim = BLOCOS[bloco]
    return sorted(d for d in set(m1().index.date) if ini <= d <= fim)


@lru_cache(maxsize=None)
def _por_dia():
    b = m1()
    return {d: g for d, g in b.groupby(b.index.date)}


def ticks(dia: date):
    """(t_ms, last, volume, real=False) sinteticos do pregao, 4 por M1."""
    t, p, v = _sinteticos(_por_dia()[dia])
    return t, p, v, False
