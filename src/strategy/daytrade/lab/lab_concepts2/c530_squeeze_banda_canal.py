"""Squeeze: Banda de Bollinger CONTIDA dentro do Canal de Keltner (via ATR,
sem lib). Enquanto contida, o robo so' observa; no primeiro fechamento em que
a banda deixa de estar contida (o squeeze "solta"), entra na direcao do
rompimento.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import atr, bollinger_bands, ema
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class SqueezeBandaCanal(IntradayStrategy):
    name: str = "c530_squeeze_banda_canal"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    k_bollinger: float = 2.0
    k_keltner_atr: float = 1.5
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 35
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(80), init=False, repr=False)
    _squeeze_ligado_antes: bool = field(default=False, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._squeeze_ligado_antes = False
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
        if len(self._buffer) < self.janela + 1:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        upper_b, mid_b, lower_b = bollinger_bands(close, self.janela, self.k_bollinger)
        mid_k = ema(close, self.janela)
        atr_atual = atr(high, low, close, self.janela)
        upper_k = mid_k + self.k_keltner_atr * atr_atual
        lower_k = mid_k - self.k_keltner_atr * atr_atual

        if pd.isna(upper_b.iloc[-1]) or pd.isna(upper_k.iloc[-1]):
            return []

        squeeze_ligado_estava = self._squeeze_ligado_antes
        squeeze_agora = bool(upper_b.iloc[-1] < upper_k.iloc[-1] and lower_b.iloc[-1] > lower_k.iloc[-1])
        self._squeeze_ligado_antes = squeeze_agora

        if positions or self._armou_hoje:
            return []
        if not (squeeze_ligado_estava and not squeeze_agora):
            return []  # so' dispara na TRANSICAO ligado->desligado

        off = self.offset_ticks * self.tick_size
        if bar.close > upper_b.iloc[-1]:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "squeeze_solta_cima")]
        if bar.close < lower_b.iloc[-1]:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "squeeze_solta_baixo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
