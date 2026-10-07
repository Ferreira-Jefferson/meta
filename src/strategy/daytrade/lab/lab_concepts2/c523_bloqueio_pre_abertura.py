"""Nos primeiros M minutos pos-abertura, NAO entra em nada -- regime de
"aguardar formacao" (o mercado ainda esta' descobrindo preco). Depois da
janela de bloqueio, opera um rompimento de range simples, so' para o
mecanismo ter alguma coisa que produza trade fora do bloqueio.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class BloqueioPreAbertura(IntradayStrategy):
    name: str = "c523_bloqueio_pre_abertura"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    minutos_bloqueio: float = 10.0
    janela_range: int = 20
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
    _open_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._open_ts = None
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
        if self._open_ts is None:
            self._open_ts = ts

        if (ts - self._open_ts) < pd.Timedelta(minutes=self.minutos_bloqueio):
            return []  # bloqueio: o robo nem OLHA sinal aqui

        if positions or self._armou_hoje:
            return []
        if len(self._buffer) < self.janela_range + 1:
            return []

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "pos_bloqueio_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "pos_bloqueio_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
