"""Catalogo calendario/sazonalidade, item 22: PrimeiroPregaoDoAnoMomentum.

Conceito de CALENDARIO: primeiro pregao de janeiro (mudanca de `ts.year`
no indice de `bars`, via `year_boundaries`, precomputado em
`initialize`). Entra na direcao do movimento liquido de DEZEMBRO do ano
anterior (`december_return_by_year`, tambem precomputado); `Exit` no
fechamento.
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    december_return_by_year, montar_entrada, trading_dates, year_boundaries,
)

_FLATTEN_FECHAMENTO = time(17, 50)


@dataclass
class PrimeiroPregaoDoAnoMomentum(IntradayStrategy):
    name: str = "primeiro_pregao_do_ano_momentum"
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

    _primeiros_do_ano: set = field(default_factory=set, init=False, repr=False)
    _retorno_dez_por_ano: dict = field(default_factory=dict, init=False, repr=False)
    _e_primeiro_do_ano: bool = field(default=False, init=False, repr=False)
    _retorno_dez: float | None = field(default=None, init=False, repr=False)
    _processada: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        primeiros, _ = year_boundaries(trading_dates(bars))
        self._primeiros_do_ano = primeiros
        self._retorno_dez_por_ano = december_return_by_year(bars)

    def on_session_start(self, session_date) -> None:
        self._e_primeiro_do_ano = session_date in self._primeiros_do_ano
        self._processada = False
        self._retorno_dez = (
            self._retorno_dez_por_ano.get(session_date.year - 1)
            if self._e_primeiro_do_ano else None
        )

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_primeiro_do_ano:
            return []

        if not self._processada:
            self._processada = True
            if not positions and self._retorno_dez not in (None, 0.0):
                side = "long" if self._retorno_dez > 0 else "short"
                return [montar_entrada(
                    side=side, limit_price=bar.open, stop_ticks=self.stop_ticks,
                    alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
            return []

        if ts.time() >= _FLATTEN_FECHAMENTO and positions:
            return [Exit(reason=f"{self.name}_flatten_eod")]
        return []
