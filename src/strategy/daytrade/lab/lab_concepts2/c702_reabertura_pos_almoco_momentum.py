"""Catalogo calendario/sazonalidade, item 3: ReaberturaPosAlmocoMomentum.

Conceito de CALENDARIO: 13:30-14:00 e' a janela FIXA de reabertura pos-
almoco no catalogo. Entra na direcao do primeiro impulso de 5min apos o
fim do horario de almoco (13:30 -> 13:35), uma vez por pregao.
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
    FIM_ALMOCO, FIM_REABERTURA_ALMOCO, montar_entrada,
)

_FIM_IMPULSO = time(13, 35)


@dataclass
class ReaberturaPosAlmocoMomentum(IntradayStrategy):
    name: str = "reabertura_pos_almoco_momentum"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 25

    _preco_1330: float | None = field(default=None, init=False, repr=False)
    _direcao: Literal["long", "short"] | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._preco_1330 = None
        self._direcao = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if ts.time() < FIM_ALMOCO or ts.time() >= FIM_REABERTURA_ALMOCO:
            return []

        if self._preco_1330 is None:
            self._preco_1330 = bar.close
            return []

        if self._direcao is None:
            if ts.time() >= _FIM_IMPULSO:
                impulso = bar.close - self._preco_1330
                if impulso != 0:
                    self._direcao = "long" if impulso > 0 else "short"
            return []

        if not positions and not self._entrou_hoje:
            self._entrou_hoje = True
            return [montar_entrada(
                side=self._direcao, limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
