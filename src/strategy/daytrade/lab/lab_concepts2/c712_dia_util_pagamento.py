"""Catalogo calendario/sazonalidade, item 13: DiaUtilPagamento.

Conceito de CALENDARIO: opera ao redor do 5o dia UTIL do mes
(`nth_business_day_of_month(dates, 5)`, precomputado em `initialize` a
partir do indice real de `bars`) -- data tradicionalmente associada a
pagamento de salario/beneficio no Brasil. Compra em qualquer recuo
intradiario nesse dia; `Exit` no fechamento.
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
    montar_entrada, nth_business_day_of_month, trading_dates,
)

_FLATTEN_FECHAMENTO = time(17, 50)


@dataclass
class DiaUtilPagamento(IntradayStrategy):
    name: str = "dia_util_pagamento"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    n_dia_util: int = 5
    janela_ma: int = 20
    recuo_ticks: float = 6.0
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30

    _dias_pagamento: set = field(default_factory=set, init=False, repr=False)
    _e_dia_pagamento: bool = field(default=False, init=False, repr=False)
    _closes: deque = field(default_factory=deque, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        self._dias_pagamento = nth_business_day_of_month(trading_dates(bars), self.n_dia_util)

    def on_session_start(self, session_date) -> None:
        self._e_dia_pagamento = session_date in self._dias_pagamento
        self._closes = deque(maxlen=self.janela_ma)
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_dia_pagamento:
            return []

        if ts.time() >= _FLATTEN_FECHAMENTO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_eod")]
            return []

        acao: list[IntradayAction] = []
        if (not positions and not self._entrou_hoje
                and len(self._closes) == self._closes.maxlen):
            media = sum(self._closes) / len(self._closes)
            if bar.close < media - self.recuo_ticks * self.tick_size:
                self._entrou_hoje = True
                acao = [montar_entrada(
                    side="long", limit_price=bar.close, stop_ticks=self.stop_ticks,
                    alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
        self._closes.append(bar.close)
        return acao
