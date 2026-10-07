"""Catálogo volume/microestrutura, item 34: TresBarrasDeVolumeCrescenteMesmaDirecao.

Três barras SEGUIDAS na mesma direção (todas de alta ou todas de baixa),
cada uma com volume maior que a anterior — entra no FECHAMENTO da
terceira barra (a barra corrente, quando ela completa a sequência),
diferente do item 8 que espera rompimento de um extremo em barra
posterior.
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


@dataclass
class TresBarrasDeVolumeCrescenteMesmaDirecao(IntradayStrategy):
    """Três barras seguidas na mesma direção com volume crescente barra a
    barra — entra no fechamento da terceira barra (a corrente)."""

    name: str = "tres_barras_volume_crescente"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _duas_anteriores: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._duas_anteriores = deque(maxlen=2)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._duas_anteriores) == 2:
            b1, b2 = self._duas_anteriores[0], self._duas_anteriores[1]
            todas_alta = b1.close > b1.open and b2.close > b2.open and bar.close > bar.open
            todas_baixa = b1.close < b1.open and b2.close < b2.open and bar.close < bar.open
            vol_crescente = b1.volume < b2.volume < bar.volume
            if vol_crescente and todas_alta:
                nivel = bar.close
                limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif vol_crescente and todas_baixa:
                nivel = bar.close
                limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._duas_anteriores.append(bar)
        return acao
