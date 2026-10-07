"""Oposto do gatilho de EXPANSAO: so' entra com o ATR(N) em QUEDA consistente
(contracao) em relacao a M barras atras -- fade dentro do range recente, com
alvo reduzido proporcionalmente a contracao (nunca abaixo do piso de 4 ticks).
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
class ContracaoAtrGatilho(IntradayStrategy):
    name: str = "c514_contracao_atr_gatilho"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_atr: int = 14
    janela_range: int = 20
    barras_atras: int = 10
    contracao_minima_pct: float = 0.20  # ATR precisa estar 20% ABAIXO do de M barras atras
    alvo_ticks_base: int = 30
    stop_ticks: int = 20
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
        minimo = max(self.janela_atr + self.barras_atras, self.janela_range) + 1
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        serie_atr = atr(high, low, close, self.janela_atr)
        atr_agora = serie_atr.iloc[-1]
        atr_antes = serie_atr.iloc[-1 - self.barras_atras]
        if pd.isna(atr_agora) or pd.isna(atr_antes) or atr_antes <= 0:
            return []

        contracao = (atr_antes - atr_agora) / atr_antes
        if contracao < self.contracao_minima_pct:
            return []

        faixa_hi = high.iloc[-self.janela_range:].max()
        faixa_lo = low.iloc[-self.janela_range:].min()
        off = self.offset_ticks * self.tick_size
        # alvo encolhe na mesma proporcao da contracao (piso de 4 ticks
        # aplicado dentro de `montar_entrada`)
        alvo_ticks = self.alvo_ticks_base * (1.0 - contracao)

        if bar.close >= faixa_hi:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, alvo_ticks, "contracao_atr_fade_topo")]
        if bar.close <= faixa_lo:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, alvo_ticks, "contracao_atr_fade_fundo")]
        return []

    def _ordem(self, side: str, limite: float, alvo_ticks: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
