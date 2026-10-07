"""Catálogo regime/adaptação, item 53: TrailingPercentualATR.

Rompimento de range de N barras como gatilho de entrada; depois que o
lucro atinge o piso de 4 ticks, o stop passa a ser arrastado a `k_atr` ×
ATR (précomputado em `initialize`) atrás do preço -- só aperta, nunca
afrouxa (regra do motor para `AdjustStop`).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from core.indicators import atr as atr_indicator
from strategy.daytrade.base import (
    AdjustStop, Bar, EnterLimit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9
PISO_TICKS_GARANTIDO = 4


@dataclass
class TrailingPercentualATR(IntradayStrategy):
    """Rompimento de range de N barras. Trailing stop a `k_atr` × ATR(
    `janela_atr`) atrás do preço, ativado só depois que o lucro cobre o
    piso de `PISO_TICKS_GARANTIDO` ticks -- nunca afrouxa o stop."""

    name: str = "trailing_percentual_atr"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_atr: int = 14
    k_atr: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _atr_por_ts: dict = field(default_factory=dict, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        serie_atr = atr_indicator(bars["high"], bars["low"], bars["close"], window=self.janela_atr)
        self._atr_por_ts = {ts: float(v) for ts, v in serie_atr.items() if pd.notna(v)}

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if positions:
            valor_atr = self._atr_por_ts.get(ts)
            piso_preco = self.tick_size * PISO_TICKS_GARANTIDO
            if valor_atr is not None and valor_atr > 0:
                for pos in positions:
                    if pos.side == "long":
                        lucro = bar.close - pos.entry_price
                        if lucro >= piso_preco:
                            candidato = no_tick(bar.close - self.k_atr * valor_atr, self.tick_size)
                            if pos.current_stop is None or candidato > pos.current_stop:
                                acao.append(AdjustStop(new_stop=candidato))
                    else:
                        lucro = pos.entry_price - bar.close
                        if lucro >= piso_preco:
                            candidato = no_tick(bar.close + self.k_atr * valor_atr, self.tick_size)
                            if pos.current_stop is None or candidato < pos.current_stop:
                                acao.append(AdjustStop(new_stop=candidato))
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
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
