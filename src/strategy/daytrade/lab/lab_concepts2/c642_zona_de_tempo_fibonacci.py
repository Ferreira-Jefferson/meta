"""Catálogo Gann/Fibonacci, item 43: ZonaDeTempoFibonacci.

Zonas de tempo de Fibonacci: contagem de barras desde a abertura em
números de Fibonacci (hardcoded). Entradas só são consideradas nesses
marcos temporais, combinadas com um gatilho de preço simples (rompimento
da máxima/mínima da barra anterior).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

_MARCOS_FIBONACCI = {1, 2, 3, 5, 8, 13, 21, 34, 55, 89}


@dataclass
class ZonaDeTempoFibonacci(IntradayStrategy):
    """Só considera entradas quando a contagem de barras desde a abertura
    da sessão é um marco de Fibonacci; gatilho de preço = rompimento da
    máxima/mínima da barra anterior."""

    name: str = "zona_de_tempo_fibonacci"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _barra_index: int = field(default=0, init=False, repr=False)
    _high_anterior: float | None = field(default=None, init=False, repr=False)
    _low_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._barra_index = 0
        self._high_anterior = None
        self._low_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._barra_index += 1

        if (not positions and self._barra_index in _MARCOS_FIBONACCI
                and self._high_anterior is not None and self._low_anterior is not None):
            if bar.close > self._high_anterior:
                limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < self._low_anterior:
                limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._high_anterior = bar.high
        self._low_anterior = bar.low
        return acao
