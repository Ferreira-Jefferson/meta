"""Largura do canal de Donchian (maxima - minima de N barras) em TICKS: quando
esta ESTREITA (percentil baixo do proprio historico) o robo so' observa,
esperando compressao romper; quando esta LARGA (percentil alto) segue o
rompimento mais recente do canal.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, percentile_rank


@dataclass
class DonchianLarguraRegime(IntradayStrategy):
    name: str = "c508_donchian_largura_regime"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_canal: int = 20
    #: so' opera com o canal LARGO (percentil >= isto do proprio historico
    #: de largura) -- abaixo disso e' compressao, e o robo so' observa ate'
    #: o proprio rompimento levar o percentil para cima.
    percentil_largo: float = 75.0
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(100), init=False, repr=False)
    _historico_largura_ticks: deque = field(
        default_factory=lambda: deque(maxlen=250), init=False, repr=False)
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
        if len(self._buffer) < self.janela_canal + 1:
            return []

        high, low = self._buffer.high(), self._buffer.low()
        # canal calculado ATE a barra anterior, para o proprio rompimento
        # nao contaminar a largura que decide se ele vale ou nao
        canal_hi = high.iloc[-self.janela_canal - 1:-1].max()
        canal_lo = low.iloc[-self.janela_canal - 1:-1].min()
        largura_ticks = (canal_hi - canal_lo) / self.tick_size

        percentil = percentile_rank(self._historico_largura_ticks, largura_ticks)
        self._historico_largura_ticks.append(largura_ticks)

        if positions or self._armou_hoje:
            return []
        if len(self._historico_largura_ticks) < 20:
            return []

        off = self.offset_ticks * self.tick_size
        if percentil >= self.percentil_largo:
            if bar.close > canal_hi:
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, "donchian_largo_segue_cima")]
            if bar.close < canal_lo:
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, "donchian_largo_segue_baixo")]
        # canal estreito (compressao): so' observa, nao opera ate' o proprio
        # rompimento fazer o percentil subir na proxima barra
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
