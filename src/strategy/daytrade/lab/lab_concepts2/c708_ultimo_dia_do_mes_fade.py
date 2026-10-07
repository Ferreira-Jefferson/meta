"""Catalogo calendario/sazonalidade, item 9: UltimoDiaDoMesFade.

Conceito de CALENDARIO: no ULTIMO pregao do mes (`month_boundaries`,
precomputado em `initialize`), fade de qualquer movimento > N ticks nos
ultimos 60 minutos; `Exit` no fechamento.
"""
from __future__ import annotations

from collections import deque
from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    month_boundaries, montar_entrada, trading_dates,
)

_JANELA_MINUTOS = 60
_FLATTEN_FECHAMENTO = time(17, 50)


@dataclass
class UltimoDiaDoMesFade(IntradayStrategy):
    name: str = "ultimo_dia_do_mes_fade"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    limiar_ticks: float = 20.0
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 20

    _ultimos_do_mes: set = field(default_factory=set, init=False, repr=False)
    _e_ultimo_dia: bool = field(default=False, init=False, repr=False)
    _buffer: deque = field(default_factory=deque, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        _, ultimos = month_boundaries(trading_dates(bars))
        self._ultimos_do_mes = ultimos

    def on_session_start(self, session_date) -> None:
        self._e_ultimo_dia = session_date in self._ultimos_do_mes
        self._buffer = deque()
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_ultimo_dia:
            return []

        if ts.time() >= _FLATTEN_FECHAMENTO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_eod")]
            return []

        self._buffer.append((ts, bar.close))
        limite = ts - pd.Timedelta(minutes=_JANELA_MINUTOS)
        while self._buffer and self._buffer[0][0] <= limite:
            self._buffer.popleft()

        if not positions and not self._entrou_hoje and len(self._buffer) >= _JANELA_MINUTOS:
            referencia = self._buffer[0][1]
            mov_ticks = (bar.close - referencia) / self.tick_size
            if abs(mov_ticks) >= self.limiar_ticks:
                self._entrou_hoje = True
                side = "short" if mov_ticks > 0 else "long"
                return [montar_entrada(
                    side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
                    alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
        return []
