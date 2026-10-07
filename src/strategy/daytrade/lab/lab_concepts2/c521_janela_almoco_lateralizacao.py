"""Regime dedicado ao horario de almoco (12:00-13:30 BRT): so' faz FADE dentro
de uma faixa estreita (nunca rompimento), com alvo no piso de 4 ticks --
liquidez baixa nesse horario nao sustenta alvo grande nem segue tendencia.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class JanelaAlmocoLateralizacao(IntradayStrategy):
    name: str = "c521_janela_almoco_lateralizacao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    hora_inicio: dt.time = dt.time(12, 0)
    hora_fim: dt.time = dt.time(13, 30)
    janela_faixa: int = 15
    faixa_maxima_ticks: float = 15.0  # so' opera se a faixa recente for ESTREITA
    offset_ticks: int = 1
    stop_ticks: int = 8
    alvo_ticks: int = 4  # piso literal do catalogo
    entrada_ttl_bars: int = 20
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(30), init=False, repr=False)
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
        hora = ts.time()
        if not (self.hora_inicio <= hora <= self.hora_fim):
            return []  # fora do almoco: regime nao existe aqui
        if len(self._buffer) < self.janela_faixa + 1:
            return []

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_faixa - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_faixa - 1:-1].min()
        faixa_ticks = (faixa_hi - faixa_lo) / self.tick_size
        if faixa_ticks > self.faixa_maxima_ticks:
            return []  # nao esta' lateralizado o bastante -- nao e' o regime

        off = self.offset_ticks * self.tick_size
        # nunca rompimento: so' fade quando toca a borda da faixa estreita
        if bar.close >= faixa_hi:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "almoco_fade_topo_faixa")]
        if bar.close <= faixa_lo:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "almoco_fade_fundo_faixa")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
