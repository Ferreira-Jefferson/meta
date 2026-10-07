"""Catálogo Gann/Fibonacci, item 45: GapDeGemeosPrimos.

Detecta pivôs de swing (fractal de 3 barras) e mede o intervalo em barras
entre pivôs consecutivos. Quando os dois últimos intervalos formam um par
de primos-gêmeos (diferença constante 2, ex. 11-13, 17-19, 29-31, 41-43,
59-61), trata como timing harmônico para reversão do último swing.
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

_PARES_GEMEOS = {(11, 13), (17, 19), (29, 31), (41, 43), (59, 61)}


@dataclass
class GapDeGemeosPrimos(IntradayStrategy):
    """Pivôs de swing (fractal 3 barras); quando os dois últimos intervalos
    (em barras) entre pivôs consecutivos casam com um par de primos-gêmeos,
    entra na reversão do último swing."""

    name: str = "gap_de_gemeos_primos"
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
    _buffer_highs: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _buffer_lows: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _buffer_idx: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _pivos: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _intervalos: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._barra_index = 0
        self._buffer_highs = deque(maxlen=3)
        self._buffer_lows = deque(maxlen=3)
        self._buffer_idx = deque(maxlen=3)
        self._pivos = deque(maxlen=3)
        self._intervalos = deque(maxlen=2)

    def _registra_pivo_se_houver(self) -> None:
        if len(self._buffer_highs) < 3:
            return
        h0, h1, h2 = self._buffer_highs
        l0, l1, l2 = self._buffer_lows
        idx1 = self._buffer_idx[1]
        tipo = None
        preco = None
        if h1 > h0 and h1 > h2:
            tipo, preco = "alta", h1
        elif l1 < l0 and l1 < l2:
            tipo, preco = "baixa", l1

        if tipo is not None and (not self._pivos or self._pivos[-1][2] != tipo):
            if self._pivos:
                intervalo = idx1 - self._pivos[-1][0]
                self._intervalos.append(intervalo)
            self._pivos.append((idx1, preco, tipo))

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._barra_index += 1

        self._buffer_highs.append(bar.high)
        self._buffer_lows.append(bar.low)
        self._buffer_idx.append(self._barra_index)
        self._registra_pivo_se_houver()

        if not positions and len(self._intervalos) == 2 and self._pivos:
            par = tuple(sorted(self._intervalos))
            if par in _PARES_GEMEOS:
                ultimo_tipo = self._pivos[-1][2]
                lado = "short" if ultimo_tipo == "alta" else "long"
                if lado == "long":
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=lado, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        return acao
