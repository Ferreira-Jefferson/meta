"""Catálogo física, item 26: AtritoDesaceleracaoMomentum.

Analogia com atrito dinâmico: aplica decaimento exponencial ao score de
momentum a cada barra (score = score×decaimento + impulso_novo, onde
impulso_novo = close(t)-close(t-1)) — o "atrito" some parte do momentum
acumulado a cada passo, mesmo sem impulso novo contrário. Entra quando o
score decaído ainda excede um limiar (o movimento resistiu ao atrito).
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
class AtritoDesaceleracaoMomentum(IntradayStrategy):
    """Score de momentum com decaimento exponencial por barra ('atrito');
    entra quando o score decaído ainda excede o limiar rolling."""

    name: str = "atrito_desaceleracao_momentum"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    decaimento: float = 0.85
    percentil_limiar: float = 80.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _score: float = field(default=0.0, init=False, repr=False)
    _historico_abs: deque = field(default_factory=lambda: deque(maxlen=200), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._score = 0.0
        self._historico_abs = deque(maxlen=200)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if len(self._closes) == 2:
            impulso = bar.close - self._closes[-1]
            self._score = self._score * self.decaimento + impulso
            self._historico_abs.append(abs(self._score))

            if not positions and len(self._historico_abs) >= 20:
                import numpy as np
                limiar = float(np.percentile(self._historico_abs, self.percentil_limiar))
                if self._score > limiar:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif self._score < -limiar:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._closes.append(bar.close)
        return acao
