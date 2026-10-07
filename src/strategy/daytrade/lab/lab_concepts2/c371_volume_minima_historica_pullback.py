"""Catálogo volume/microestrutura, item 72: VolumeEmMinimaHistoricaNoPullback.

Dentro de uma correção contra a tendência (um down-tick em tendência de
alta, ou up-tick em tendência de baixa), a barra que registra o menor
volume da janela móvel dispara entrada a favor da tendência principal.
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
class VolumeEmMinimaHistoricaNoPullback(IntradayStrategy):
    """Pullback contra a tendência com a barra de menor volume da janela
    -- entra a favor da tendência principal."""

    name: str = "volume_minima_historica_pullback"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_trend: int = 20
    janela_vol: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_trend)
        self._vols = deque(maxlen=self.janela_vol)
        self._close_anterior = None

    def _ordem(self, lado: str, nivel: float) -> list[IntradayAction]:
        if lado == "long":
            limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
        else:
            limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
        return [EnterLimit(
            side=lado, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if (not positions and len(self._closes) == self._closes.maxlen
                and len(self._vols) == self._vols.maxlen and self._close_anterior is not None):
            tendencia_alta = bar.close > self._closes[0]
            tendencia_baixa = bar.close < self._closes[0]
            nova_minima_volume = bar.volume < min(self._vols)
            if tendencia_alta and bar.close < self._close_anterior and nova_minima_volume:
                acao = self._ordem("long", bar.close)
            elif tendencia_baixa and bar.close > self._close_anterior and nova_minima_volume:
                acao = self._ordem("short", bar.close)

        self._closes.append(bar.close)
        self._vols.append(bar.volume)
        self._close_anterior = bar.close
        return acao
