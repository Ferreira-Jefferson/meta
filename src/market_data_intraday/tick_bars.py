"""Converte tick a tick (`tick_storage.load_ticks`) para o formato `Bar`
(open/high/low/close/volume) que `backtest.intraday.engine` ja sabe
processar -- sem mudar uma linha do motor.

Um negocio e' um evento ATOMICO a um preco so', entao a "barra" degenera
para um ponto: `open=high=low=close=last`. Isso e' estritamente MAIS
PRECISO que agregar em OHLC de verdade (M1, M5, ...), nao uma perda de
informacao -- o motor decide toque de nivel via `bar.low <= nivel <=
bar.high`; com `high == low == last`, so' preenche se ALGUEM REALMENTE
negociou exatamente naquele preco, em vez de assumir que o preco "passou
por dentro" da faixa da barra."""
from __future__ import annotations

import pandas as pd


def ticks_to_degenerate_bars(ticks: pd.DataFrame) -> pd.DataFrame:
    """`ticks`: DataFrame de `tick_storage.load_ticks` (colunas bid/ask/
    last/volume/volume_real/flags, index = timestamp do negocio). Devolve
    um DataFrame open/high/low/close/volume, uma linha por tick."""
    volume = ticks["volume_real"].where(ticks["volume_real"] > 0, ticks["volume"])
    return pd.DataFrame({
        "open": ticks["last"],
        "high": ticks["last"],
        "low": ticks["last"],
        "close": ticks["last"],
        "volume": volume,
    }, index=ticks.index)
