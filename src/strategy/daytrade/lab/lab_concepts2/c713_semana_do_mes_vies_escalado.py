"""Catalogo calendario/sazonalidade, item 14: SemanaDoMesVieEscalado.

Conceito de CALENDARIO: divide o mes em semanas via `(dia-1)//7`
(`week_of_month`) -- vies comprado na semana 0 (dias 1-7), neutro nas
semanas 1-2 (dias 8-21), vendido na semana 3+ (dias 22+). O gatilho e' o
rompimento de uma mini-faixa de abertura (09:00-09:15), FILTRADO pelo
vies da semana -- so' opera no lado que o vies permite.
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    montar_entrada, week_of_month,
)

_FIM_MINI_FAIXA = time(9, 15)


@dataclass
class SemanaDoMesVieEscalado(IntradayStrategy):
    name: str = "semana_do_mes_vies_escalado"
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

    _vies: Literal["long", "short"] | None = field(default=None, init=False, repr=False)
    _faixa_high: float | None = field(default=None, init=False, repr=False)
    _faixa_low: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        semana = week_of_month(session_date.day)
        if semana == 0:
            self._vies = "long"
        elif semana >= 3:
            self._vies = "short"
        else:
            self._vies = None
        self._faixa_high = None
        self._faixa_low = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if ts.time() < _FIM_MINI_FAIXA:
            if self._faixa_high is None:
                self._faixa_high, self._faixa_low = bar.high, bar.low
            else:
                self._faixa_high = max(self._faixa_high, bar.high)
                self._faixa_low = min(self._faixa_low, bar.low)
            return []

        if self._vies is None or positions or self._entrou_hoje or self._faixa_high is None:
            return []

        if self._vies == "long" and bar.close > self._faixa_high:
            self._entrou_hoje = True
            return [montar_entrada(
                side="long", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        if self._vies == "short" and bar.close < self._faixa_low:
            self._entrou_hoje = True
            return [montar_entrada(
                side="short", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
