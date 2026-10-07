"""Catálogo volume/microestrutura, item 19: RangeLargoComVolumeBaixo.

Barra de range AMPLO (> k× média) mas volume ABAIXO da média (movimento
sem participação real, provável ruído/gap de liquidez) — fade no retorno
à média móvel de `janela_media` fechamentos.
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
class RangeLargoComVolumeBaixo(IntradayStrategy):
    """Range amplo com volume abaixo da média (movimento sem
    participação) — fade em direção à média móvel recente de
    fechamentos."""

    name: str = "range_largo_volume_baixo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_media: int = 20
    k_range: float = 1.5
    fator_volume_baixo: float = 0.7
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ranges: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ranges = deque(maxlen=self.janela_media)
        self._vols = deque(maxlen=self.janela_media)
        self._closes = deque(maxlen=self.janela_media)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low

        if (not positions and len(self._ranges) == self._ranges.maxlen
                and self._vols and self._closes):
            range_ma = sum(self._ranges) / len(self._ranges)
            vol_ma = sum(self._vols) / len(self._vols)
            media_close = sum(self._closes) / len(self._closes)
            if rng > self.k_range * range_ma and bar.volume < self.fator_volume_baixo * vol_ma:
                if bar.close > media_close:
                    nivel = bar.close
                    limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif bar.close < media_close:
                    nivel = bar.close
                    limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._ranges.append(rng)
        self._vols.append(bar.volume)
        self._closes.append(bar.close)
        return acao
