"""O DECIL do range realizado (high-low) da barra corrente, dentro de uma
janela historica rolante, escala o STOP: decil baixo (range tipico pequeno)
usa o piso de 4 ticks; decil alto (range tipico grande) usa um stop
proporcionalmente maior. Gatilho: rompimento da barra anterior.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, percentile_rank


@dataclass
class RangeRealizadoDecil(IntradayStrategy):
    name: str = "c516_range_realizado_decil"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_historico: int = 200
    stop_max_ticks: int = 30
    alvo_multiplo: float = 1.5
    offset_ticks: int = 2
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
    _historico_range: deque = field(
        default_factory=lambda: deque(maxlen=200), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._historico_range = deque(maxlen=self.janela_historico)

    def on_session_start(self, session_date) -> None:
        self._armou_hoje = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._buffer.push(bar)
        range_atual = bar.high - bar.low
        decil = percentile_rank(self._historico_range, range_atual) / 10.0
        self._historico_range.append(range_atual)

        if positions or self._armou_hoje:
            return []
        if len(self._historico_range) < 20 or len(self._buffer) < 2:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        barra_anterior_hi = high.iloc[-2]
        barra_anterior_lo = low.iloc[-2]
        off = self.offset_ticks * self.tick_size

        stop_ticks = max(4, round(decil / 10.0 * self.stop_max_ticks))
        alvo_ticks = stop_ticks * self.alvo_multiplo

        if bar.close > barra_anterior_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, stop_ticks, alvo_ticks,
                                "range_decil_rompe_cima")]
        if bar.close < barra_anterior_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, stop_ticks, alvo_ticks,
                                "range_decil_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, stop_ticks: float, alvo_ticks: float,
               reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=stop_ticks,
            alvo_ticks=alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
