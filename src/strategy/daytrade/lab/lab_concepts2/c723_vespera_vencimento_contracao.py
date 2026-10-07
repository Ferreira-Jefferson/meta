"""Catalogo calendario/sazonalidade, item 24: VesperaVencimentoContracao.

Conceito de CALENDARIO: dia util ANTERIOR ao "vencimento" -- o WDO@ e' o
simbolo CONTINUO, entao vencimento real do contrato-mes nao aparece na
serie; aproxima-se o "dia de vencimento" pelo ULTIMO pregao do mes
(documentado em `_common_calendario.month_boundaries`) e a "vespera" pelo
PENULTIMO pregao do mes (`nth_business_day_of_month_from_end(dates, 2)`).
So' opera dentro da faixa de abertura (09:00-09:30), alvo reduzido (piso
4 ticks), sem overnight (`Exit` no fechamento).
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    montar_entrada, nth_business_day_of_month_from_end, trading_dates,
)

_FIM_FAIXA_ABERTURA = time(9, 30)
_FLATTEN_FECHAMENTO = time(17, 50)


@dataclass
class VesperaVencimentoContracao(IntradayStrategy):
    name: str = "vespera_vencimento_contracao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 12
    alvo_ticks_reduzido: int = 4
    entrada_ttl_bars: int = 40

    _vesperas_vencimento: set = field(default_factory=set, init=False, repr=False)
    _e_vespera: bool = field(default=False, init=False, repr=False)
    _faixa_high: float | None = field(default=None, init=False, repr=False)
    _faixa_low: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        self._vesperas_vencimento = nth_business_day_of_month_from_end(trading_dates(bars), 2)

    def on_session_start(self, session_date) -> None:
        self._e_vespera = session_date in self._vesperas_vencimento
        self._faixa_high = None
        self._faixa_low = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_vespera:
            return []

        if ts.time() >= _FLATTEN_FECHAMENTO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_sem_overnight")]
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
                alvo_ticks=self.alvo_ticks_reduzido, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        if bar.close < self._faixa_low:
            self._entrou_hoje = True
            return [montar_entrada(
                side="short", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks_reduzido, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
