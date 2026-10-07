"""Catálogo física, item 14: EnergiaPotencialCompressao.

Analogia com energia potencial elástica: durante consolidação, "energia
armazenada" = (range_máximo_da_janela − range_atual_recente)² — quanto mais
comprimido o range recente frente ao histórico, mais energia acumulada.
Entra no rompimento do range com stop/alvo escalados pela energia
armazenada (mais energia => geometria mais larga).
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
class EnergiaPotencialCompressao(IntradayStrategy):
    """Energia potencial = (range máximo da janela − range recente)²
    durante consolidação; rompimento com geometria escalada pela energia
    armazenada."""

    name: str = "energia_potencial_compressao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    janela_recente: int = 5
    offset_ticks: int = 1
    stop_ticks_base: int = 12
    alvo_ticks_base: int = 6
    escala_energia_ticks: float = 0.02
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela)
        self._lows = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if not positions and len(self._highs) == self._highs.maxlen:
            highs, lows = list(self._highs), list(self._lows)
            range_max = max(highs) - min(lows)
            range_recente = max(highs[-self.janela_recente:]) - min(lows[-self.janela_recente:])
            energia = max(range_max - range_recente, 0.0) ** 2
            extra_ticks = min(energia * self.escala_energia_ticks, 40.0)
            range_high, range_low = max(highs), min(lows)

            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - (self.stop_ticks_base + extra_ticks) * self.tick_size, self.tick_size)
                alvo = no_tick(limite + (self.alvo_ticks_base + extra_ticks) * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + (self.stop_ticks_base + extra_ticks) * self.tick_size, self.tick_size)
                alvo = no_tick(limite - (self.alvo_ticks_base + extra_ticks) * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
