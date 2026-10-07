"""Catalogo calendario/sazonalidade, item 21: UltimoPregaoDoAnoCautela.

Conceito de CALENDARIO: 30-31/dez (`ts.month == 12 and ts.day >= 30`,
regra direta sobre a data, sem precomputo). Liquidez fina nesses pregoes
-- so' fade de excursoes grandes desde a abertura, alvo pequeno (piso 4
ticks), `Exit` no fechamento (reforca a regra de nunca manter posicao
alem do proprio dia, que o motor ja garante).
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import montar_entrada

_FLATTEN_FECHAMENTO = time(17, 50)


@dataclass
class UltimoPregaoDoAnoCautela(IntradayStrategy):
    name: str = "ultimo_pregao_do_ano_cautela"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    limiar_ticks: float = 15.0
    stop_ticks: int = 12
    alvo_ticks_reduzido: int = 4
    entrada_ttl_bars: int = 30

    _e_fim_de_ano: bool = field(default=False, init=False, repr=False)
    _abertura: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._e_fim_de_ano = session_date.month == 12 and session_date.day >= 30
        self._abertura = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_fim_de_ano:
            return []

        if self._abertura is None:
            self._abertura = bar.open

        if ts.time() >= _FLATTEN_FECHAMENTO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_eod")]
            return []

        if positions or self._entrou_hoje:
            return []

        excursao_ticks = (bar.close - self._abertura) / self.tick_size
        if abs(excursao_ticks) >= self.limiar_ticks:
            self._entrou_hoje = True
            side = "short" if excursao_ticks > 0 else "long"
            return [montar_entrada(
                side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks_reduzido, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
