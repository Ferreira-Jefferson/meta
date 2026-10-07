"""Catalogo calendario/sazonalidade, item 28: ViradaDeMesUltimaHora.

Conceito de CALENDARIO combinado: virada de mes (ULTIMO pregao do mes,
`month_boundaries`, precomputado em `initialize`) E janela de ultima hora
(17:00-18:00, fixa) -- so' entra na ultima hora do ultimo pregao do mes,
na direcao do movimento acumulado do dia (close atual vs abertura da
sessao); `Exit` no fechamento.
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    INICIO_ULTIMA_HORA, month_boundaries, montar_entrada, trading_dates,
)

_FECHAMENTO_FORCADO = time(17, 55)


@dataclass
class ViradaDeMesUltimaHora(IntradayStrategy):
    name: str = "virada_de_mes_ultima_hora"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 15

    _ultimos_do_mes: set = field(default_factory=set, init=False, repr=False)
    _e_ultimo_dia: bool = field(default=False, init=False, repr=False)
    _abertura: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        _, ultimos = month_boundaries(trading_dates(bars))
        self._ultimos_do_mes = ultimos

    def on_session_start(self, session_date) -> None:
        self._e_ultimo_dia = session_date in self._ultimos_do_mes
        self._abertura = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_ultimo_dia:
            return []

        if self._abertura is None:
            self._abertura = bar.open

        if ts.time() >= _FECHAMENTO_FORCADO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_eod")]
            return []

        if (ts.time() >= INICIO_ULTIMA_HORA and not positions and not self._entrou_hoje):
            movimento = bar.close - self._abertura
            if movimento != 0:
                self._entrou_hoje = True
                side = "long" if movimento > 0 else "short"
                return [montar_entrada(
                    side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
                    alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
        return []
