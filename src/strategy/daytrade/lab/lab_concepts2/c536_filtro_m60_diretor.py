"""Agrega o M1 em candles sinteticos de 60 minutos (M60). O regime de mais
longo prazo funciona como filtro BINARIO liga/desliga de lado: candle M60
mais recente de alta libera so' compra; de baixa libera so' venda. Diferente
do filtro M15 (media movel): aqui e' so' a COR do ultimo candle fechado, o
proxy mais simples de direcao de longo prazo. Entrada fina em M1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, resample_synthetic


@dataclass
class FiltroM60Diretor(IntradayStrategy):
    name: str = "c536_filtro_m60_diretor"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    minutos_m60: float = 60.0
    janela_range_m1: int = 20
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(500), init=False, repr=False)
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

        agg = resample_synthetic(self._buffer, self.minutos_m60)
        if len(agg) < 1:
            return []
        ultimo = agg.iloc[-1]
        if ultimo["close"] == ultimo["open"]:
            return []  # candle neutro: regime nao decide nada
        diretor_alta = ultimo["close"] > ultimo["open"]

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range_m1 - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range_m1 - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if diretor_alta and bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "m60_diretor_alta_rompe_cima")]
        if not diretor_alta and bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "m60_diretor_baixa_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
