"""Catálogo regime/adaptação, item 74: StopProporcionalAoRangeDaAberturaInicial.

O range das primeiras `barras_abertura` barras do pregão é medido uma vez
(congelado) e vira `multiplo_stop × range_abertura` -- o STOP de toda
entrada do pregão, sem recalcular depois.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class StopProporcionalAoRangeDaAberturaInicial(IntradayStrategy):
    """Rompimento de range de N barras. O stop de TODA entrada do pregão é
    `multiplo_stop × range` das primeiras `barras_abertura` barras --
    medido uma vez e congelado para o resto da sessão."""

    name: str = "stop_proporcional_ao_range_da_abertura_inicial"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    barras_abertura: int = 15
    multiplo_stop: float = 1.0
    offset_ticks: int = 1
    alvo_ticks: int = 8
    stop_ticks_fallback: int = 16
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _barras_vistas: int = field(default=0, init=False, repr=False)
    _alta_abertura: "float | None" = field(default=None, init=False, repr=False)
    _baixa_abertura: "float | None" = field(default=None, init=False, repr=False)
    _stop_congelado: "float | None" = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._barras_vistas = 0
        self._alta_abertura = None
        self._baixa_abertura = None
        self._stop_congelado = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if self._stop_congelado is None:
            self._barras_vistas += 1
            self._alta_abertura = bar.high if self._alta_abertura is None else max(self._alta_abertura, bar.high)
            self._baixa_abertura = bar.low if self._baixa_abertura is None else min(self._baixa_abertura, bar.low)
            if self._barras_vistas >= self.barras_abertura:
                range_abertura = self._alta_abertura - self._baixa_abertura
                self._stop_congelado = max(
                    self.multiplo_stop * range_abertura,
                    self.stop_ticks_fallback * self.tick_size,
                )

        if positions:
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        stop_distancia = (
            self._stop_congelado if self._stop_congelado is not None
            else (self.stop_ticks_fallback * self.tick_size)
        )
        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - stop_distancia, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + stop_distancia, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
