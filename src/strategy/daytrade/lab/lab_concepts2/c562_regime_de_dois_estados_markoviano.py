"""Catálogo regime/adaptação, item 63: RegimeDeDoisEstadosMarkoviano.

Rompimento de range de N barras; estado "alta"/"baixa" definido pelo sinal
do retorno acumulado das últimas `janela_estado` barras, com HISTERESE:
só troca de estado depois de `m_confirmacao` barras seguidas confirmando o
novo sinal (contador simples, sem cadeia de Markov formal).
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
class RegimeDeDoisEstadosMarkoviano(IntradayStrategy):
    """Rompimento de range de N barras, filtrado por um estado "alta"/
    "baixa" (sinal do retorno acumulado de `janela_estado` barras) com
    histerese de `m_confirmacao` barras antes de trocar de estado."""

    name: str = "regime_de_dois_estados_markoviano"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_estado: int = 20
    m_confirmacao: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_estado: deque = field(default_factory=lambda: deque(maxlen=21), init=False, repr=False)
    _estado: str = field(default="alta", init=False, repr=False)
    _contador_candidato: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._closes_estado = deque(maxlen=self.janela_estado + 1)
        self._estado = "alta"
        self._contador_candidato = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_estado.append(bar.close)

        if len(self._closes_estado) == self._closes_estado.maxlen:
            retorno = self._closes_estado[-1] - self._closes_estado[0]
            candidato = "alta" if retorno > 0 else ("baixa" if retorno < 0 else self._estado)
            if candidato != self._estado:
                self._contador_candidato += 1
                if self._contador_candidato >= self.m_confirmacao:
                    self._estado = candidato
                    self._contador_candidato = 0
            else:
                self._contador_candidato = 0

        if positions:
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if self._estado == "alta" and bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif self._estado == "baixa" and bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
