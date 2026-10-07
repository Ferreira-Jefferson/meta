"""Quando o M1 (momentum de curtissimo prazo) diverge da tendencia sintetica
de M15 -- o M1 anda contra o M15 -- classifica isso como CORRECAO dentro da
tendencia maior, e opera FADE do movimento de M1 (a favor do M15, contra o
que o M1 acabou de fazer). Sem divergencia, nao opera -- o conceito e' so'
sobre a correcao, nao sobre seguir tendencia direto.
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
class DivergenciaEscalas(IntradayStrategy):
    name: str = "c538_divergencia_escalas"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    minutos_m15: float = 15.0
    janela_ma_m15: int = 10
    janela_momentum_m1: int = 5
    offset_ticks: int = 1
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 30
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
        if len(self._buffer) < self.janela_momentum_m1 + 1:
            return []

        agg = resample_synthetic(self._buffer, self.minutos_m15)
        if len(agg) < self.janela_ma_m15 + 1:
            return []
        ma_m15 = sma(agg["close"], self.janela_ma_m15)
        if pd.isna(ma_m15.iloc[-1]):
            return []
        m15_alta = agg["close"].iloc[-1] > ma_m15.iloc[-1]

        close_m1 = self._buffer.close()
        momentum_m1 = close_m1.iloc[-1] - close_m1.iloc[-1 - self.janela_momentum_m1]
        if momentum_m1 == 0:
            return []
        m1_caindo = momentum_m1 < 0

        divergiu = (m15_alta and m1_caindo) or (not m15_alta and not m1_caindo)
        if not divergiu:
            return []  # M1 e M15 concordam -- nao e' correcao, e' continuidade

        off = self.offset_ticks * self.tick_size
        # fade do M1: entra a favor do M15
        if m15_alta:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "divergencia_fade_m1_favor_m15_alta")]
        self._armou_hoje = True
        return [self._ordem("short", bar.close + off, "divergencia_fade_m1_favor_m15_baixa")]

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
