"""Rompimento simples do range de N barras, com alvo e stop recalculados a
CADA entrada como multiplos do ATR(N) CORRENTE (nao um numero fixo) -- o
mecanismo e' a geometria dinamica, nao o gatilho.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import atr
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class AlvoStopAtrDinamico(IntradayStrategy):
    name: str = "c510_alvo_stop_atr_dinamico"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_atr: int = 14
    janela_range: int = 20
    k_stop_atr: float = 1.5
    k_alvo_atr: float = 2.5
    offset_ticks: int = 2
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(100), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

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
        if positions or self._armou_hoje:
            return []
        minimo = max(self.janela_atr, self.janela_range) + 1
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        atr_atual = atr(high, low, close, self.janela_atr).iloc[-1]
        if pd.isna(atr_atual) or atr_atual <= 0:
            return []

        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        stop_ticks = (atr_atual * self.k_stop_atr) / self.tick_size
        alvo_ticks = (atr_atual * self.k_alvo_atr) / self.tick_size

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, stop_ticks, alvo_ticks,
                                "atr_dinamico_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, stop_ticks, alvo_ticks,
                                "atr_dinamico_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, stop_ticks: float, alvo_ticks: float,
               reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=stop_ticks,
            alvo_ticks=alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
