"""Catálogo regime/adaptação, item 77: FiltroDeConsistenciaDeCorDeCandle.

Proporção de candles de alta vs baixa nas últimas `janela_cor` barras;
proporção muito enviesada (>= `limiar_proporcao`) é tratada como tendência
por EXAUSTÃO -- opera A FAVOR da cor dominante, mas com alvo reduzido
(nunca abaixo do piso de 4 ticks).
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
PISO_TICKS_GARANTIDO = 4


@dataclass
class FiltroDeConsistenciaDeCorDeCandle(IntradayStrategy):
    """Proporção de candles de alta/baixa nas últimas `janela_cor` barras;
    proporção >= `limiar_proporcao` opera a favor da cor dominante, com
    alvo reduzido a `alvo_reduzido_ticks` (nunca abaixo do piso de 4
    ticks)."""

    name: str = "filtro_de_consistencia_de_cor_de_candle"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_cor: int = 10
    limiar_proporcao: float = 0.8
    alvo_reduzido_ticks: int = 4
    offset_ticks: int = 1
    stop_ticks: int = 16
    entrada_ttl_bars: int = 40

    _cores: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._cores = deque(maxlen=self.janela_cor)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._cores) == self._cores.maxlen:
            prop_alta = sum(1 for c in self._cores if c) / len(self._cores)
            prop_baixa = 1.0 - prop_alta
            alvo_ticks = max(self.alvo_reduzido_ticks, PISO_TICKS_GARANTIDO)
            if prop_alta >= self.limiar_proporcao and bar.close > bar.open:
                limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif prop_baixa >= self.limiar_proporcao and bar.close < bar.open:
                limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._cores.append(bar.close > bar.open)
        return acao
