"""Utilitários de calendário de pregão.

Funções puras para estratégias que dependem de datas específicas — como
rebalance mensal em robôs de momentum.
"""
from __future__ import annotations

import pandas as pd


def is_month_end(index: pd.DatetimeIndex) -> pd.Series:
    """True no último pregão útil de cada mês do índice recebido.

    Convenção: "último pregão do mês" = a última data do índice cujo
    mês/ano é distinto do da próxima data. Trabalha com o calendário real
    de pregões (ex.: se 31/12 é feriado, o dia 30/12 é o "month end").
    """
    if len(index) == 0:
        return pd.Series([], index=index, dtype=bool)
    ym = pd.Series(index.to_period("M").astype(str), index=index)
    next_ym = ym.shift(-1)
    is_last = (ym != next_ym) & next_ym.notna()
    return is_last
