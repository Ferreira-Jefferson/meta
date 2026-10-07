"""Catalogo calendario/sazonalidade, item 29: PrimeiraQuinzenaAberturaBreakout.

Conceito de CALENDARIO combinado: quinzena (`ts.day <= 15`, regra direta
sobre a data) E janela de abertura (09:00-09:30, fixa). O MESMO gatilho
de rompimento da faixa de abertura opera com mecanismo OPOSTO nas duas
metades do mes -- primeira quinzena segue o rompimento (breakout),
segunda quinzena FADE o mesmo rompimento -- tudo na mesma classe, so'
mudando o sinal pela data.
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import montar_entrada

_FIM_FAIXA_ABERTURA = time(9, 30)


@dataclass
class PrimeiraQuinzenaAberturaBreakout(IntradayStrategy):
    name: str = "primeira_quinzena_abertura_breakout"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _primeira_quinzena: bool = field(default=True, init=False, repr=False)
    _faixa_high: float | None = field(default=None, init=False, repr=False)
    _faixa_low: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._primeira_quinzena = session_date.day <= 15
        self._faixa_high = None
        self._faixa_low = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if ts.time() < _FIM_FAIXA_ABERTURA:
            if self._faixa_high is None:
                self._faixa_high, self._faixa_low = bar.high, bar.low
            else:
                self._faixa_high = max(self._faixa_high, bar.high)
                self._faixa_low = min(self._faixa_low, bar.low)
            return []

        if positions or self._entrou_hoje or self._faixa_high is None:
            return []

        rompeu_cima = bar.close > self._faixa_high
        rompeu_baixo = bar.close < self._faixa_low
        if not rompeu_cima and not rompeu_baixo:
            return []

        if self._primeira_quinzena:
            side = "long" if rompeu_cima else "short"  # segue o rompimento
        else:
            side = "short" if rompeu_cima else "long"  # FADE o mesmo rompimento

        self._entrou_hoje = True
        return [montar_entrada(
            side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
            ttl_bars=self.entrada_ttl_bars, reason=self.name,
        )]
