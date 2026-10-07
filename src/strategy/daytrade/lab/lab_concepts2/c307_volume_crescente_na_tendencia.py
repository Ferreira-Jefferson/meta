"""Catálogo volume/microestrutura, item 8: VolumeCrescenteNaTendencia.

`n_barras` seguidas na MESMA direção (todas de alta ou todas de baixa),
cada uma com volume maior que a anterior — usado como confirmação de
força da tendência; entra no rompimento do extremo da última barra da
sequência.
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
class VolumeCrescenteNaTendencia(IntradayStrategy):
    """`n_barras` na mesma direção com volume crescente barra a barra —
    confirmação de força; entra no rompimento do extremo da última barra
    da sequência, a favor da tendência."""

    name: str = "volume_crescente_na_tendencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    n_barras: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _janela: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._janela = deque(maxlen=self.n_barras)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._janela) == self._janela.maxlen:
            todas_alta = all(b.close > b.open for b in self._janela)
            todas_baixa = all(b.close < b.open for b in self._janela)
            vols = [b.volume for b in self._janela]
            vol_crescente = all(vols[i] < vols[i + 1] for i in range(len(vols) - 1))
            ultima = self._janela[-1]
            if vol_crescente and todas_alta and bar.close > ultima.high:
                limite = no_tick(ultima.high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif vol_crescente and todas_baixa and bar.close < ultima.low:
                limite = no_tick(ultima.low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._janela.append(bar)
        return acao
