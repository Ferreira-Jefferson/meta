"""Catálogo volume/microestrutura, item 21: ExpansaoSubitaDeRangeEVolume.

UMA barra com range E volume ambos > k× a média das `janela_media`
barras anteriores, SEM processo gradual (a barra imediatamente anterior
não já estava em expansão) — entra na direção dessa barra (continuação
do impulso súbito).
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
class ExpansaoSubitaDeRangeEVolume(IntradayStrategy):
    """Barra isolada com range e volume muito acima da média, sem
    expansão gradual precedente — entra na direção do impulso súbito."""

    name: str = "expansao_subita_range_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_media: int = 20
    k_range: float = 1.8
    k_volume: float = 1.8
    fator_barra_anterior_normal: float = 1.2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ranges: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _range_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ranges = deque(maxlen=self.janela_media)
        self._vols = deque(maxlen=self.janela_media)
        self._range_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low

        if not positions and len(self._ranges) == self._ranges.maxlen and self._vols:
            range_ma = sum(self._ranges) / len(self._ranges)
            vol_ma = sum(self._vols) / len(self._vols)
            barra_anterior_normal = (
                self._range_anterior is None
                or self._range_anterior < self.fator_barra_anterior_normal * range_ma
            )
            if (rng > self.k_range * range_ma and bar.volume > self.k_volume * vol_ma
                    and barra_anterior_normal and bar.close != bar.open):
                nivel = bar.close
                if bar.close > bar.open:
                    limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                else:
                    limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._ranges.append(rng)
        self._vols.append(bar.volume)
        self._range_anterior = rng
        return acao
