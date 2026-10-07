"""Choppiness Index (100*log10(soma(TR,N)/(max-min,N))/log10(N)) arbitra entre
as duas familias que convivem no mesmo robo: acima de 61,8 desliga a familia de
TENDENCIA (rompimento do range), abaixo de 38,2 desliga a familia de REVERSAO
(fade nas bordas) -- na faixa do meio as duas ficam ligadas e o sinal que
aparecer primeiro decide.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class ChoppinessGate(IntradayStrategy):
    name: str = "c502_choppiness_gate"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 14
    limiar_desliga_tendencia: float = 61.8
    limiar_desliga_reversao: float = 38.2
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._armou_hoje = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def _choppiness(self) -> float | None:
        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low, (high - prev_close).abs(), (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        janela_tr = tr.iloc[-self.janela:]
        janela_hi = high.iloc[-self.janela:]
        janela_lo = low.iloc[-self.janela:]
        amplitude = janela_hi.max() - janela_lo.min()
        if amplitude <= 0 or self.janela <= 1:
            return None
        ci = 100.0 * math.log10(janela_tr.sum() / amplitude) / math.log10(self.janela)
        return ci

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._buffer.push(bar)
        if positions or self._armou_hoje:
            return []
        if len(self._buffer) < self.janela + 1:
            return []

        ci = self._choppiness()
        if ci is None:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        faixa_hi = high.iloc[-self.janela - 1:-1].max()
        faixa_lo = low.iloc[-self.janela - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        tendencia_ligada = ci <= self.limiar_desliga_tendencia
        reversao_ligada = ci >= self.limiar_desliga_reversao

        if tendencia_ligada:
            if bar.close > faixa_hi:
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, "choppiness_tendencia_alta")]
            if bar.close < faixa_lo:
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, "choppiness_tendencia_baixa")]
        if reversao_ligada:
            if bar.close >= faixa_hi:
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, "choppiness_fade_topo")]
            if bar.close <= faixa_lo:
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, "choppiness_fade_fundo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
