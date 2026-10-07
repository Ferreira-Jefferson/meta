"""ADX construido na mao (+DM/-DM/TR, Wilder) classifica o regime: ADX>25 segue
o rompimento do range recente; ADX<20 faz fade nas bordas da banda recente.
Entre os dois, nao opera -- a zona de transicao nao tem regime definido.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, wilder_adx


@dataclass
class AdxInternoRegime(IntradayStrategy):
    name: str = "c500_adx_interno_regime"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    periodo_adx: int = 14
    limiar_tendencia: float = 25.0
    limiar_lateral: float = 20.0
    janela_range: int = 20
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(120), init=False, repr=False)
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
        minimo = self.periodo_adx * 3 + self.janela_range
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        _, _, adx = wilder_adx(high, low, close, self.periodo_adx)
        adx_atual = adx.iloc[-1]
        if pd.isna(adx_atual):
            return []

        off = self.offset_ticks * self.tick_size
        if adx_atual > self.limiar_tendencia:
            # tendencia: segue o rompimento do range das ultimas N barras
            faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
            faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
            if bar.close > faixa_hi:
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, "adx_tendencia_alta")]
            if bar.close < faixa_lo:
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, "adx_tendencia_baixa")]
            return []
        if adx_atual < self.limiar_lateral:
            # lateral: fade nas bordas da banda recente (mesmo range serve
            # de banda quando ninguem confirma tendencia)
            faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
            faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
            if bar.close >= faixa_hi:
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, "adx_fade_topo_banda")]
            if bar.close <= faixa_lo:
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, "adx_fade_fundo_banda")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
