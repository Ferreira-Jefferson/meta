"""Catálogo Elliott/Wolfe, item 52: FractalElliottMicro.

APROXIMAÇÃO: padrão micro de onda de Elliott via string de sinais dos
retornos das últimas 3 barras — impulso, impulso, correção (`+,+,-` ou
`-,-,+`). Ao detectar a correção fechando o padrão, entra no sentido do
impulso original, antecipando o início da presumida onda 3.
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
class FractalElliottMicro(IntradayStrategy):
    """Detecta o micro-padrão impulso+impulso+correção (`+,+,-` ou `-,-,+`)
    nos sinais dos retornos das últimas 3 barras; entra a favor do impulso
    original no fecho da correção, antecipando a onda 3."""

    name: str = "fractal_elliott_micro"
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

    _sinais: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._sinais = deque(maxlen=3)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if self._close_anterior is not None:
            retorno = bar.close - self._close_anterior
            sinal = 1 if retorno > 0 else (-1 if retorno < 0 else 0)
            self._sinais.append(sinal)

            if not positions and len(self._sinais) == 3:
                s0, s1, s2 = self._sinais
                if s0 == 1 and s1 == 1 and s2 == -1:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif s0 == -1 and s1 == -1 and s2 == 1:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._close_anterior = bar.close
        return acao
