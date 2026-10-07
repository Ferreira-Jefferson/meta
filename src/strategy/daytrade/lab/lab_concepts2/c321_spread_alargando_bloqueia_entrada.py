"""Catálogo volume/microestrutura, item 22: SpreadAlargandoBloqueiaEntrada.

FILTRO + gatilho próprio (formato pedido explicitamente pelo catálogo):
gatilho é o rompimento do range de `janela_range` barras; o filtro
BLOQUEIA novas entradas quando o spread (précomputado em `initialize` a
partir da coluna crua `spread`) está ACIMA da própria média móvel recente
— suspende até normalizar.
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
class SpreadAlargandoBloqueiaEntrada(IntradayStrategy):
    """Rompimento de range de N barras, bloqueado enquanto o spread
    corrente está acima da própria média móvel recente."""

    name: str = "spread_alargando_bloqueia_entrada"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_spread: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _spread_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _spreads: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if "spread" in bars.columns:
            self._spread_por_ts = {ts: float(v) for ts, v in bars["spread"].items()}
        else:
            self._spread_por_ts = {}

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._spreads = deque(maxlen=self.janela_spread)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        spread_atual = self._spread_por_ts.get(ts)

        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._spreads) == self._spreads.maxlen and spread_atual is not None):
            range_high = max(self._highs)
            range_low = min(self._lows)
            spread_ma = sum(self._spreads) / len(self._spreads)
            spread_ok = spread_atual <= spread_ma

            if spread_ok:
                if bar.close > range_high:
                    limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif bar.close < range_low:
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
        if spread_atual is not None:
            self._spreads.append(spread_atual)
        return acao
