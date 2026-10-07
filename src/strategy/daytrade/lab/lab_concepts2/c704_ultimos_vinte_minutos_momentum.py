"""Catalogo calendario/sazonalidade, item 5: UltimosVinteMinutosMomentum.

Conceito de CALENDARIO: 17:20-17:40 e' a janela de REFERENCIA e 17:40-18:00
a janela de CONTINUACAO, ambas fixas no catalogo. Continuacao do movimento
dos 20min anteriores (17:20-17:40); `Exit` forcado no fechamento do
pregao.
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    CORTE_ULTIMOS_20MIN, INICIO_COMPARACAO_20MIN, montar_entrada,
)

_FLATTEN_FECHAMENTO = time(17, 58)


@dataclass
class UltimosVinteMinutosMomentum(IntradayStrategy):
    name: str = "ultimos_vinte_minutos_momentum"
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

    _preco_1720: float | None = field(default=None, init=False, repr=False)
    _preco_1740: float | None = field(default=None, init=False, repr=False)
    _direcao: Literal["long", "short"] | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._preco_1720 = None
        self._preco_1740 = None
        self._direcao = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if ts.time() >= _FLATTEN_FECHAMENTO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_fechamento")]
            return []

        if self._preco_1720 is None and ts.time() >= INICIO_COMPARACAO_20MIN:
            self._preco_1720 = bar.close

        if (self._preco_1740 is None and ts.time() >= CORTE_ULTIMOS_20MIN
                and self._preco_1720 is not None):
            self._preco_1740 = bar.close
            movimento = self._preco_1740 - self._preco_1720
            if movimento != 0:
                self._direcao = "long" if movimento > 0 else "short"

        if (self._direcao is not None and not positions and not self._entrou_hoje
                and ts.time() >= CORTE_ULTIMOS_20MIN):
            self._entrou_hoje = True
            return [montar_entrada(
                side=self._direcao, limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
