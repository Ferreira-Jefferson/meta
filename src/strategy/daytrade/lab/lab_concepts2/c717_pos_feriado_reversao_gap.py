"""Catalogo calendario/sazonalidade, item 18: PosFeriadoReversaoGap.

Espelho de `PosFeriadoGap` (item 17): mesma deteccao de primeiro pregao
apos gap de calendario, mas FADE do gap em vez de seguir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    calendar_gaps, montar_entrada, trading_dates,
)


@dataclass
class PosFeriadoReversaoGap(IntradayStrategy):
    name: str = "pos_feriado_reversao_gap"
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

    _pos_feriado: set = field(default_factory=set, init=False, repr=False)
    _e_pos_feriado: bool = field(default=False, init=False, repr=False)
    _processada: bool = field(default=False, init=False, repr=False)
    _fechamento_hoje: float | None = field(default=None, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        _, pos_feriado = calendar_gaps(trading_dates(bars))
        self._pos_feriado = pos_feriado

    def on_session_start(self, session_date) -> None:
        self._e_pos_feriado = session_date in self._pos_feriado
        self._processada = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._e_pos_feriado and not self._processada:
            self._processada = True
            if not positions and self._fechamento_hoje is not None:
                gap = bar.open - self._fechamento_hoje
                if abs(gap) >= self.tick_size:
                    side = "short" if gap > 0 else "long"  # fade, sinal invertido
                    acao = [montar_entrada(
                        side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
                        alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                        ttl_bars=self.entrada_ttl_bars, reason=self.name,
                    )]
        self._fechamento_hoje = bar.close
        return acao
