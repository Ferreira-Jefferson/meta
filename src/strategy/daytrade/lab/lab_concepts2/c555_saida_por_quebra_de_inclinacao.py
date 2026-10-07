"""Catálogo regime/adaptação, item 56: SaidaPorQuebraDeInclinacao.

Rompimento de range de N barras como gatilho de entrada; sai (`Exit`)
quando a inclinação de uma média móvel curta muda de sinal CONTRA a
posição, condicionado ao lucro já cobrir o piso de 4 ticks.
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
class SaidaPorQuebraDeInclinacao(IntradayStrategy):
    """Rompimento de range de N barras. Sai (`Exit`) quando a inclinação de
    uma MA de `janela_ma` barras vira CONTRA a posição, desde que o lucro
    já esteja acima do piso de 4 ticks."""

    name: str = "saida_por_quebra_de_inclinacao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_ma: int = 5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_ma: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _ma_anterior: "float | None" = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._closes_ma = deque(maxlen=self.janela_ma)
        self._ma_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_ma.append(bar.close)
        ma_atual = (
            sum(self._closes_ma) / len(self._closes_ma)
            if len(self._closes_ma) == self._closes_ma.maxlen else None
        )

        if positions:
            pos = positions[0]
            piso_preco = self.tick_size * PISO_TICKS_GARANTIDO
            lucro = (bar.close - pos.entry_price) if pos.side == "long" else (pos.entry_price - bar.close)
            saiu = False
            if ma_atual is not None and self._ma_anterior is not None and lucro >= piso_preco:
                inclinacao = ma_atual - self._ma_anterior
                virou_contra = (
                    (pos.side == "long" and inclinacao < 0)
                    or (pos.side == "short" and inclinacao > 0)
                )
                if virou_contra:
                    saiu = True
            self._ma_anterior = ma_atual if ma_atual is not None else self._ma_anterior
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            if saiu:
                return [Exit(reason=self.name)]
            return acao

        self._ma_anterior = ma_atual if ma_atual is not None else self._ma_anterior
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
