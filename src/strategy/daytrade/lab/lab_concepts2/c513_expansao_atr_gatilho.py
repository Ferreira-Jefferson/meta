"""So' entra quando o ATR(N) CRESCEU X% em relacao a M barras atras (expansao
de volatilidade CONFIRMADA), na direcao do movimento que gerou essa expansao
(close atual vs close de M barras atras). Expansao sem confirmacao (ATR
estavel ou em queda) nao dispara nada.
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
class ExpansaoAtrGatilho(IntradayStrategy):
    name: str = "c513_expansao_atr_gatilho"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_atr: int = 14
    barras_atras: int = 10
    expansao_minima_pct: float = 0.30  # ATR precisa estar 30% acima do de M barras atras
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
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
        minimo = self.janela_atr + self.barras_atras + 1
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        serie_atr = atr(high, low, close, self.janela_atr)
        atr_agora = serie_atr.iloc[-1]
        atr_antes = serie_atr.iloc[-1 - self.barras_atras]
        if pd.isna(atr_agora) or pd.isna(atr_antes) or atr_antes <= 0:
            return []

        expansao = (atr_agora - atr_antes) / atr_antes
        if expansao < self.expansao_minima_pct:
            return []

        movimento = close.iloc[-1] - close.iloc[-1 - self.barras_atras]
        if movimento == 0:
            return []
        off = self.offset_ticks * self.tick_size
        side = "long" if movimento > 0 else "short"
        limite = bar.close - off if side == "long" else bar.close + off
        self._armou_hoje = True
        return [self._ordem(side, limite, "expansao_atr_confirmada")]

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
