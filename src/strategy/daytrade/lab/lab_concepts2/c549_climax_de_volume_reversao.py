"""Catálogo regime/adaptação, item 50: ClimaxDeVolumeReversao.

Barra com volume EXTREMO e range EXTREMO (ambos muito acima da média) é
tratada como clímax -- arma entrada CONTRA a direção dessa barra, a
executar no rompimento do extremo oposto ao fechamento dela.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    Side, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class ClimaxDeVolumeReversao(IntradayStrategy):
    """Detecta barra de clímax (volume e range muito acima da média) e arma
    entrada CONTRA a direção da barra de clímax, no rompimento do extremo
    oposto ao fechamento dela."""

    name: str = "climax_de_volume_reversao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_media: int = 20
    k_range: float = 2.0
    k_volume: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ranges: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _armado_lado: "Side | None" = field(default=None, init=False, repr=False)
    _armado_nivel: "float | None" = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ranges = deque(maxlen=self.janela_media)
        self._vols = deque(maxlen=self.janela_media)
        self._armado_lado = None
        self._armado_nivel = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low

        if not positions:
            if self._armado_lado == "long" and self._armado_nivel is not None and bar.close > self._armado_nivel:
                limite = no_tick(self._armado_nivel - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
                self._armado_lado = None
                self._armado_nivel = None
            elif self._armado_lado == "short" and self._armado_nivel is not None and bar.close < self._armado_nivel:
                limite = no_tick(self._armado_nivel + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
                self._armado_lado = None
                self._armado_nivel = None
            elif (len(self._ranges) == self._ranges.maxlen and rng > 0
                    and self._ranges and self._vols):
                range_ma = sum(self._ranges) / len(self._ranges)
                vol_ma = sum(self._vols) / len(self._vols)
                if rng > self.k_range * range_ma and bar.volume > self.k_volume * vol_ma:
                    if bar.close < bar.open:
                        # climax de venda -- reverte comprando no rompimento da maxima
                        self._armado_lado = "long"
                        self._armado_nivel = bar.high
                    elif bar.close > bar.open:
                        # climax de compra -- reverte vendendo no rompimento da minima
                        self._armado_lado = "short"
                        self._armado_nivel = bar.low

        self._ranges.append(rng)
        self._vols.append(bar.volume)
        return acao
