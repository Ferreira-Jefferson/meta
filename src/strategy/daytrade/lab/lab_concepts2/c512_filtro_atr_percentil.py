"""Rompimento de range simples, mas so' entra quando o ATR(N) esta' entre os
percentis 30-70 do proprio historico ROLANTE: volatilidade extrema (baixa OU
alta demais) trava a entrada -- o filtro E' o mecanismo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from core.indicators import atr
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, percentile_rank


@dataclass
class FiltroAtrPercentil(IntradayStrategy):
    name: str = "c512_filtro_atr_percentil"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_atr: int = 14
    janela_range: int = 20
    janela_historico: int = 200
    percentil_min: float = 30.0
    percentil_max: float = 70.0
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(150), init=False, repr=False)
    _historico_atr: deque = field(
        default_factory=lambda: deque(maxlen=200), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._historico_atr = deque(maxlen=self.janela_historico)

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
        minimo = max(self.janela_atr, self.janela_range) + 1
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        atr_atual = atr(high, low, close, self.janela_atr).iloc[-1]
        if pd.isna(atr_atual):
            return []

        percentil = percentile_rank(self._historico_atr, atr_atual)
        self._historico_atr.append(atr_atual)

        if positions or self._armou_hoje:
            return []
        if len(self._historico_atr) < 20:
            return []
        if not (self.percentil_min <= percentil <= self.percentil_max):
            return []

        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "atr_percentil_ok_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "atr_percentil_ok_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
