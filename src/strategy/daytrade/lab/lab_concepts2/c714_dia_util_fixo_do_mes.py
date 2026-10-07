"""Catalogo calendario/sazonalidade, item 15: DiaUtilFixoDoMes.

Conceito de CALENDARIO: opera so' nos indices FIXOS de dia util do mes --
1o, 10o e 20o pregao (`nth_business_day_of_month`, precomputado em
`initialize` a partir do indice real de `bars`). Nesses dias, rompimento
da faixa de abertura (09:00-09:30); ignora os demais dias do mes.
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    montar_entrada, nth_business_day_of_month, trading_dates,
)

_FIM_FAIXA_ABERTURA = time(9, 30)


@dataclass
class DiaUtilFixoDoMes(IntradayStrategy):
    name: str = "dia_util_fixo_do_mes"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _dias_fixos: set = field(default_factory=set, init=False, repr=False)
    _e_dia_fixo: bool = field(default=False, init=False, repr=False)
    _faixa_high: float | None = field(default=None, init=False, repr=False)
    _faixa_low: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        dates = trading_dates(bars)
        self._dias_fixos = (
            nth_business_day_of_month(dates, 1)
            | nth_business_day_of_month(dates, 10)
            | nth_business_day_of_month(dates, 20)
        )

    def on_session_start(self, session_date) -> None:
        self._e_dia_fixo = session_date in self._dias_fixos
        self._faixa_high = None
        self._faixa_low = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_dia_fixo:
            return []

        if ts.time() < _FIM_FAIXA_ABERTURA:
            if self._faixa_high is None:
                self._faixa_high, self._faixa_low = bar.high, bar.low
            else:
                self._faixa_high = max(self._faixa_high, bar.high)
                self._faixa_low = min(self._faixa_low, bar.low)
            return []

        if positions or self._entrou_hoje or self._faixa_high is None:
            return []

        if bar.close > self._faixa_high:
            self._entrou_hoje = True
            return [montar_entrada(
                side="long", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        if bar.close < self._faixa_low:
            self._entrou_hoje = True
            return [montar_entrada(
                side="short", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
