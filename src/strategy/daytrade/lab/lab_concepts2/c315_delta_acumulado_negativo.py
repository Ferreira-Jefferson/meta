"""Catálogo volume/microestrutura, item 16: DeltaAproximadoAcumuladoNegativo.

Espelho do item 15: mesmo delta aproximado acumulado em janela; quando a
soma cruza de >=0 para <0, entra vendido.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def _delta_barra(bar: Bar) -> float:
    rng = bar.high - bar.low
    if rng <= 0:
        return 0.0
    compra = (bar.close - bar.low) / rng * bar.volume
    venda = (bar.high - bar.close) / rng * bar.volume
    return compra - venda


@dataclass
class DeltaAproximadoAcumuladoNegativo(IntradayStrategy):
    """Delta aproximado acumulado em janela; cruzamento de >=0 para <0
    dispara venda."""

    name: str = "delta_acumulado_negativo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_delta: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _deltas: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._deltas = deque(maxlen=self.janela_delta)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        soma_antes = sum(self._deltas) if self._deltas else 0.0

        self._deltas.append(_delta_barra(bar))
        soma_atual = sum(self._deltas)

        if not positions and soma_antes >= 0 and soma_atual < 0:
            nivel = bar.close
            limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
            acao = [EnterLimit(
                side="short", limit_price=limite, initial_stop=stop,
                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
            )]

        return acao
