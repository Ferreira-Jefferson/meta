"""Catálogo volume/microestrutura, item 43: ClimaxReversoDeGap.

Abertura em gap com volume elevado (vs. média histórica de volume de
abertura, acumulada dia a dia) na direção do gap, mas a própria barra de
abertura fecha cruzando de volta o preço de abertura -- fade do gap.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class ClimaxReversoDeGap(IntradayStrategy):
    """Gap de abertura com volume alto que reverte dentro da própria barra
    de abertura (fecha cruzando de volta o open) -- fade do gap."""

    name: str = "climax_reverso_gap"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    gap_min_ticks: int = 4
    k_volume_abertura: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _fechamento_anterior: float | None = field(default=None, init=False, repr=False)
    _primeira_barra: bool = field(default=True, init=False, repr=False)
    _n_dias: int = field(default=0, init=False, repr=False)
    _media_vol_abertura: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._primeira_barra = True

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
        if self._primeira_barra:
            self._primeira_barra = False
            media_historica = self._media_vol_abertura if self._n_dias > 0 else None
            if (not positions and self._fechamento_anterior is not None
                    and media_historica is not None):
                gap = bar.open - self._fechamento_anterior
                gap_ok = abs(gap) >= self.gap_min_ticks * self.tick_size
                volume_alto = bar.volume > self.k_volume_abertura * media_historica
                if gap_ok and volume_alto:
                    if gap > 0 and bar.close < bar.open:
                        acao = self._ordem("short", bar.close)
                    elif gap < 0 and bar.close > bar.open:
                        acao = self._ordem("long", bar.close)
            self._n_dias += 1
            self._media_vol_abertura += (bar.volume - self._media_vol_abertura) / self._n_dias

        self._fechamento_anterior = bar.close
        return acao
