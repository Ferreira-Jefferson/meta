"""Catalogo calendario/sazonalidade, item 4: UltimaHoraReversao.

Conceito de CALENDARIO: 17:00-18:00 e' a janela FIXA de ultima hora no
catalogo. Fade do movimento LIQUIDO acumulado do dia (close atual vs
abertura da sessao) quando excede um limiar; `Exit` forcado no fechamento
(17:55).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    FECHAMENTO_FORCADO, INICIO_ULTIMA_HORA, montar_entrada,
)


@dataclass
class UltimaHoraReversao(IntradayStrategy):
    name: str = "ultima_hora_reversao"
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

    _abertura: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._abertura = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._abertura is None:
            self._abertura = bar.open

        if ts.time() >= FECHAMENTO_FORCADO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_1755")]
            return []

        if ts.time() < INICIO_ULTIMA_HORA:
            return []

        if positions:
            return []

        mov_ticks = (bar.close - self._abertura) / self.tick_size
        if abs(mov_ticks) >= self.limiar_ticks:
            side = "short" if mov_ticks > 0 else "long"
            return [montar_entrada(
                side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
