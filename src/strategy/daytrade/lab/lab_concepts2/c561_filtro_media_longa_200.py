"""Catálogo regime/adaptação, item 62: FiltroMediaLonga200.

Rompimento de range de N barras; filtro estrutural pela SMA de
`janela_sma` (~200) barras, précomputada em `initialize`: acima da SMA na
PRIMEIRA barra da sessão em que ela está disponível = só compra pelo resto
do pregão; abaixo = só vende. Não inverte no mesmo pregão.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from core.indicators import sma
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    Side, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class FiltroMediaLonga200(IntradayStrategy):
    """Rompimento de range de N barras. Filtro estrutural pela SMA de
    `janela_sma` barras: lado travado na primeira barra da sessão em que a
    SMA está disponível, sem inversão dentro do mesmo pregão."""

    name: str = "filtro_media_longa_200"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_sma: int = 200
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _sma_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _lado_dia: "Side | None" = field(default=None, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        serie_sma = sma(bars["close"], window=self.janela_sma)
        self._sma_por_ts = {ts: float(v) for ts, v in serie_sma.items() if pd.notna(v)}

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._lado_dia = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._lado_dia is None:
            sma_valor = self._sma_por_ts.get(ts)
            if sma_valor is not None:
                self._lado_dia = "long" if bar.close > sma_valor else "short"

        if positions:
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if self._lado_dia is not None and len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if self._lado_dia == "long" and bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif self._lado_dia == "short" and bar.close < range_low:
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
