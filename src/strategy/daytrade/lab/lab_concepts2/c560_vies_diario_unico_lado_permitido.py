"""Catálogo regime/adaptação, item 61: ViesDiarioUnicoLadoPermitido.

Rompimento de range de N barras; o retorno acumulado da sessão (close
atual − abertura do pregão) define, na PRIMEIRA vez que ultrapassa um
limiar mínimo, o único lado permitido pelo resto do pregão -- não inverte
mais depois de travado.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    Side, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class ViesDiarioUnicoLadoPermitido(IntradayStrategy):
    """Rompimento de range de N barras. Retorno acumulado da sessão (close
    − abertura) trava, na primeira vez que ultrapassa `limiar_ticks`, o
    único lado permitido pelo resto do pregão."""

    name: str = "vies_diario_unico_lado_permitido"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    limiar_ticks: int = 8
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _abertura: "float | None" = field(default=None, init=False, repr=False)
    _lado_permitido: "Side | None" = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._abertura = None
        self._lado_permitido = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._abertura is None:
            self._abertura = bar.open

        if self._lado_permitido is None:
            retorno = bar.close - self._abertura
            limiar_preco = self.limiar_ticks * self.tick_size
            if retorno >= limiar_preco:
                self._lado_permitido = "long"
            elif retorno <= -limiar_preco:
                self._lado_permitido = "short"

        if positions:
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if self._lado_permitido is not None and len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if self._lado_permitido == "long" and bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif self._lado_permitido == "short" and bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
