"""Catálogo Gann/geometria sagrada, item 50: EscalaMusicalIntervalos.

Detecta pivôs de swing (fractal 3 barras) e mapeia a razão de preço entre
os dois últimos pivôs a intervalos musicais (oitava 2:1, quinta 3:2,
quarta 4:3, e seus inversos). Razão "consonante" (perto de um intervalo
conhecido) prevê continuação no sentido do último swing; razão
"dissonante" (longe de todos) gera fade.
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

_INTERVALOS_CONSONANTES = [2.0, 1.5, 1.3333, 1.0, 0.75, 0.6667, 0.5]
_TOLERANCIA_CONSONANTE = 0.03
_TOLERANCIA_DISSONANTE = 0.12


@dataclass
class EscalaMusicalIntervalos(IntradayStrategy):
    """Razão de preço entre os dois últimos pivôs de swing mapeada a
    intervalos musicais: razão consonante prevê continuação do swing,
    dissonante (longe de qualquer intervalo) gera fade."""

    name: str = "escala_musical_intervalos"
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

    _buffer_highs: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _buffer_lows: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _pivos: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._buffer_highs = deque(maxlen=3)
        self._buffer_lows = deque(maxlen=3)
        self._pivos = deque(maxlen=2)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._buffer_highs.append(bar.high)
        self._buffer_lows.append(bar.low)

        if len(self._buffer_highs) == 3:
            h0, h1, h2 = self._buffer_highs
            l0, l1, l2 = self._buffer_lows
            if h1 > h0 and h1 > h2:
                self._pivos.append(h1)
            elif l1 < l0 and l1 < l2:
                self._pivos.append(l1)

        if not positions and len(self._pivos) == 2 and self._pivos[0] > 0:
            razao = self._pivos[1] / self._pivos[0]
            distancias = [abs(razao - alvo) for alvo in _INTERVALOS_CONSONANTES]
            dist_min = min(distancias)
            tendencia_alta = self._pivos[1] > self._pivos[0]

            if dist_min <= _TOLERANCIA_CONSONANTE:
                lado = "long" if tendencia_alta else "short"
            elif dist_min >= _TOLERANCIA_DISSONANTE:
                lado = "short" if tendencia_alta else "long"
            else:
                lado = None

            if lado == "long":
                limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif lado == "short":
                limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        return acao
