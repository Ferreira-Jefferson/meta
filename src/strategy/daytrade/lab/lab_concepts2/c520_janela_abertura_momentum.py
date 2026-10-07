"""So' opera nos primeiros N minutos do pregao (`ts.time()`): geometria
dedicada, momentum puro -- rompimento da barra anterior na direcao do
movimento. Fora da janela, nunca entra -- e' o regime que define a janela,
nao o sinal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class JanelaAberturaMomentum(IntradayStrategy):
    name: str = "c520_janela_abertura_momentum"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_minutos: float = 20.0
    offset_ticks: int = 2
    stop_ticks: int = 15
    alvo_ticks: int = 25
    entrada_ttl_bars: int = 20
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(30), init=False, repr=False)
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

        if positions or self._armou_hoje:
            return []
        if (ts - self._open_ts) >= pd.Timedelta(minutes=self.janela_minutos):
            return []  # fora da janela: regime nao permite operar
        if len(self._buffer) < 2:
            return []

        close = self._buffer.close()
        delta = close.iloc[-1] - close.iloc[-2]
        if delta == 0:
            return []
        off = self.offset_ticks * self.tick_size
        side = "long" if delta > 0 else "short"
        limite = bar.close - off if side == "long" else bar.close + off
        self._armou_hoje = True
        return [self._ordem(side, limite, "janela_abertura_momentum")]

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
