"""Agrega o M1 recebido em candles SINTETICOS de 15 minutos (resample puro
pandas, sem feed proprio). A direcao da MA em M15 filtra o LADO: so' compra
em alta de M15, so' vende em baixa. A entrada fina (o gatilho) continua em
M1 -- rompimento do range recente.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import sma
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, resample_synthetic


@dataclass
class FiltroM15SobreM1(IntradayStrategy):
    name: str = "c535_filtro_m15_sobre_m1"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    minutos_m15: float = 15.0
    janela_ma_m15: int = 10
    janela_range_m1: int = 20
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(400), init=False, repr=False)
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
        if len(self._buffer) < self.janela_range_m1 + 1:
            return []

        agg = resample_synthetic(self._buffer, self.minutos_m15)
        if len(agg) < self.janela_ma_m15 + 1:
            return []
        ma_m15 = sma(agg["close"], self.janela_ma_m15)
        if pd.isna(ma_m15.iloc[-1]):
            return []
        tendencia_alta_m15 = agg["close"].iloc[-1] > ma_m15.iloc[-1]

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range_m1 - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range_m1 - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if tendencia_alta_m15 and bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "m15_alta_m1_rompe_cima")]
        if not tendencia_alta_m15 and bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "m15_baixa_m1_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
