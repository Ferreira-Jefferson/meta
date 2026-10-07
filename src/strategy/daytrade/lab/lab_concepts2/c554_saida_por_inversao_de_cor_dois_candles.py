"""Catálogo regime/adaptação, item 55: SaidaPorInversaoDeCorDoisCandles.

Rompimento de range de N barras como gatilho de entrada; mantém a posição
aberta enquanto os candles seguem a favor, e sai (`Exit`) depois de 2
candles SEGUIDOS contra a posição, desde que o lucro já cubra o piso de
4 ticks.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9
PISO_TICKS_GARANTIDO = 4


@dataclass
class SaidaPorInversaoDeCorDoisCandles(IntradayStrategy):
    """Rompimento de range de N barras. Sai (`Exit`) após `candles_contra_max`
    candles seguidos de cor CONTRÁRIA à posição, desde que o lucro já esteja
    acima do piso de 4 ticks."""

    name: str = "saida_por_inversao_de_cor_dois_candles"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    candles_contra_max: int = 2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _candles_contra: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._candles_contra = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if positions:
            pos = positions[0]
            candle_alta = bar.close > bar.open
            candle_baixa = bar.close < bar.open
            contra = (pos.side == "long" and candle_baixa) or (pos.side == "short" and candle_alta)
            self._candles_contra = self._candles_contra + 1 if contra else 0

            piso_preco = self.tick_size * PISO_TICKS_GARANTIDO
            lucro = (bar.close - pos.entry_price) if pos.side == "long" else (pos.entry_price - bar.close)
            if self._candles_contra >= self.candles_contra_max and lucro >= piso_preco:
                self._candles_contra = 0
                self._highs.append(bar.high)
                self._lows.append(bar.low)
                return [Exit(reason=self.name)]

            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        self._candles_contra = 0
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
