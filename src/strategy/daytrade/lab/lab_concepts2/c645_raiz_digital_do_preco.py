"""Catálogo Gann/geometria sagrada, item 46: RaizDigitalDoPreco.

Raiz digital (soma repetida de dígitos — aritmética simples, sem lib) do
preço em centavos. Entra quando a raiz digital transiciona para 9 e o
preço está perto (tolerância em ticks) de um extremo de swing recente
(máxima/mínima das últimas N barras).
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
class RaizDigitalDoPreco(IntradayStrategy):
    """Raiz digital (soma repetida de dígitos) do preço em centavos; quando
    ela transiciona para 9 perto de um extremo de swing recente, entra em
    reversão (fade) do extremo."""

    name: str = "raiz_digital_do_preco"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_extremo: int = 15
    tolerancia_ticks: int = 4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)
    _raiz_anterior: int | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_extremo)
        self._lows = deque(maxlen=self.janela_extremo)
        self._raiz_anterior = None

    @staticmethod
    def _raiz_digital(n: int) -> int:
        n = abs(n)
        if n == 0:
            return 0
        return 1 + (n - 1) % 9

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        centavos = round(bar.close * 100)
        raiz = self._raiz_digital(centavos)

        if (not positions and self._raiz_anterior is not None and self._raiz_anterior != 9
                and raiz == 9 and len(self._highs) == self._highs.maxlen):
            maxima = max(self._highs)
            minima = min(self._lows)
            tol = self.tolerancia_ticks * self.tick_size
            if abs(bar.close - maxima) <= tol:
                limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif abs(bar.close - minima) <= tol:
                limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._raiz_anterior = raiz
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
