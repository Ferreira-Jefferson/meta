"""Catalogo calendario/sazonalidade, item 10: PrimeiroDiaDoMesGapTrade.

Conceito de CALENDARIO: no PRIMEIRO pregao do mes, entra na direcao do gap
de abertura vs o fechamento do MES ANTERIOR (`month_last_close`,
precomputado em `initialize`); saida em alvo fixo ou EOD (motor flatten).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    month_boundaries, month_last_close, montar_entrada, trading_dates,
)


@dataclass
class PrimeiroDiaDoMesGapTrade(IntradayStrategy):
    name: str = "primeiro_dia_do_mes_gap_trade"
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
    _fechamentos_mes: dict = field(default_factory=dict, init=False, repr=False)
    _e_primeiro_dia: bool = field(default=False, init=False, repr=False)
    _fechamento_mes_anterior: float | None = field(default=None, init=False, repr=False)
    _processada: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        primeiros, _ = month_boundaries(trading_dates(bars))
        self._primeiros_do_mes = primeiros
        self._fechamentos_mes = month_last_close(bars)

    def on_session_start(self, session_date) -> None:
        self._processada = False
        self._e_primeiro_dia = session_date in self._primeiros_do_mes
        if not self._e_primeiro_dia:
            self._fechamento_mes_anterior = None
            return
        ano_ant, mes_ant = (session_date.year, session_date.month - 1)
        if mes_ant == 0:
            ano_ant, mes_ant = session_date.year - 1, 12
        self._fechamento_mes_anterior = self._fechamentos_mes.get((ano_ant, mes_ant))

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_primeiro_dia or self._processada:
            return []
        self._processada = True
        if positions or self._fechamento_mes_anterior is None:
            return []
        gap = bar.open - self._fechamento_mes_anterior
        if abs(gap) < self.tick_size:
            return []
        side = "long" if gap > 0 else "short"
        return [montar_entrada(
            side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
            ttl_bars=self.entrada_ttl_bars, reason=self.name,
        )]
