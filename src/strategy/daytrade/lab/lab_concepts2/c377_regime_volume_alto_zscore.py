"""Catálogo volume/microestrutura, item 78: RegimeDeVolumeAltoPorZScore.

Z-score do volume da barra (média/desvio móveis) cruza acima de +2 -- ativa
por `k_barras_regime` barras um modo "seguir rompimento" (Donchian).
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
class RegimeDeVolumeAltoPorZScore(IntradayStrategy):
    """Z-score do volume acima de +2 ativa, por K barras, um modo de
    seguir o rompimento de uma janela Donchian curta."""

    name: str = "regime_volume_alto_zscore"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_zscore: int = 20
    z_gatilho: float = 2.0
    k_barras_regime: int = 10
    janela_range: int = 10
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _modo_restante: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_zscore)
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._modo_restante = 0

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
        if len(self._vols) == self._vols.maxlen:
            serie = pd.Series(self._vols)
            media = float(serie.mean())
            desvio = float(serie.std())
            if desvio > 0 and (bar.volume - media) / desvio > self.z_gatilho:
                self._modo_restante = self.k_barras_regime

        if (not positions and self._modo_restante > 0
                and len(self._highs) == self._highs.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                acao = self._ordem("long", range_high)
                self._modo_restante = 0
            elif bar.close < range_low:
                acao = self._ordem("short", range_low)
                self._modo_restante = 0

        if self._modo_restante > 0:
            self._modo_restante -= 1

        self._vols.append(bar.volume)
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
