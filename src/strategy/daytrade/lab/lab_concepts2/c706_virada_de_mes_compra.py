"""Catalogo calendario/sazonalidade, item 7: ViradaDeMesCompra.

Conceito de CALENDARIO puro: detecta o PRIMEIRO pregao do mes (mudanca de
`ts.month` no indice de `bars`, precomputado em `initialize` via
`month_boundaries`). Compra na abertura do primeiro dia novo, `Exit` no
fechamento do mesmo dia.
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    month_boundaries, montar_entrada, trading_dates,
)

_FLATTEN_FECHAMENTO = time(17, 50)


@dataclass
class ViradaDeMesCompra(IntradayStrategy):
    name: str = "virada_de_mes_compra"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30

    _primeiros_do_mes: set = field(default_factory=set, init=False, repr=False)
    _e_primeiro_dia: bool = field(default=False, init=False, repr=False)
    _processada: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        primeiros, _ = month_boundaries(trading_dates(bars))
        self._primeiros_do_mes = primeiros

    def on_session_start(self, session_date) -> None:
        self._e_primeiro_dia = session_date in self._primeiros_do_mes
        self._processada = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_primeiro_dia:
            return []

        if not self._processada:
            self._processada = True
            if not positions:
                return [montar_entrada(
                    side="long", limit_price=bar.open, stop_ticks=self.stop_ticks,
                    alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
            return []

        if ts.time() >= _FLATTEN_FECHAMENTO and positions:
            return [Exit(reason=f"{self.name}_flatten_eod")]
        return []
