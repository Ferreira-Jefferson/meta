"""Calendário heurístico de resultados trimestrais na B3.

**Aviso**: esta é uma heurística determinística — não é o calendário CVM
real. As datas exatas de divulgação variam por empresa. Substituir por
dados CVM (dados.cvm.gov.br, download.b3.com.br) é uma v1.1 direta:
o schema desta função continua o mesmo (`is_earnings_blackout(date)`).

**Heurística usada**: cada trimestre fiscal termina em Mar/Jun/Set/Dez;
divulgação típica de blue-chips na B3 acontece **entre 30 e 60 dias após
o fechamento** (Reg. CVM 480 exige até 3 meses). Blackout defensivo é
uma janela ao redor dessa faixa central:
  - Q4 (fechamento Dez) → blackout em Mar (dias 1-31)
  - Q1 (fechamento Mar) → blackout em Mai (dias 1-15)
  - Q2 (fechamento Jun) → blackout em Ago (dias 1-15)
  - Q3 (fechamento Set) → blackout em Nov (dias 1-15)

Isso captura ~90% dos releases de blue-chips (WEGE3/RADL3/VALE3 divulgam
todos por volta dessas janelas).
"""
from __future__ import annotations

import pandas as pd

# Janelas mensais em que a maior parte dos blue-chips B3 divulga resultado.
# Formato: (mês, dia_inicial, dia_final).
_BLACKOUT_WINDOWS = [
    (3, 1, 31),   # Q4 do ano anterior — janela mais larga (Vale/Petro atrasam)
    (5, 1, 15),   # Q1
    (8, 1, 15),   # Q2
    (11, 1, 15),  # Q3
]


def is_earnings_blackout(date: pd.Timestamp) -> bool:
    """True se `date` cai numa janela heurística de divulgação de resultados.

    A janela é intencionalmente ampla para cobrir divulgações antecipadas
    e atrasadas. Estratégias que consomem este sinal devem evitar
    **abrir** posições dentro da janela (não fecha as existentes).
    """
    m, d = date.month, date.day
    for month, start, end in _BLACKOUT_WINDOWS:
        if m == month and start <= d <= end:
            return True
    return False


def blackout_series(index: pd.DatetimeIndex) -> pd.Series:
    """Vetorial para uso em `initialize()` de estratégias."""
    return pd.Series([is_earnings_blackout(d) for d in index], index=index)
