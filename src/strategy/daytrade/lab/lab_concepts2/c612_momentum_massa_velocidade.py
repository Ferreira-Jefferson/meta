"""Catálogo física, item 13: MomentumMassaVelocidade.

Analogia literal com momentum físico p=m·v: "massa"=volume da barra,
"velocidade"=close(t)-close(t-1); acumula p em N barras. Entra quando o
momentum acumulado cruza um limiar (em qualquer direção), sai (Exit) na
inversão de sinal do momentum acumulado.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class MomentumMassaVelocidade(IntradayStrategy):
    """Momentum físico p=massa(volume)×velocidade(delta close) acumulado em
    N barras; entra quando cruza limiar, sai na inversão de sinal."""

    name: str = "momentum_massa_velocidade"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 10
    limiar_percentil: float = 80.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _momentos: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _historico_abs: deque = field(default_factory=lambda: deque(maxlen=200), init=False, repr=False)
    _momentum_estado: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._momentos = deque(maxlen=self.janela)
        self._historico_abs = deque(maxlen=200)
        self._momentum_estado = 0.0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if len(self._closes) == 2:
            velocidade = bar.close - self._closes[-1]
            self._momentos.append(bar.volume * velocidade)

        if len(self._momentos) == self._momentos.maxlen:
            momentum_novo = sum(self._momentos)
            self._historico_abs.append(abs(momentum_novo))
            estado_anterior = self._momentum_estado
            self._momentum_estado = momentum_novo

            if positions:
                if estado_anterior != 0 and momentum_novo != 0 and (
                    (estado_anterior > 0) != (momentum_novo > 0)
                ):
                    acao = [Exit(reason=self.name)]
            elif len(self._historico_abs) >= 20:
                import numpy as np
                limiar = float(np.percentile(self._historico_abs, self.limiar_percentil))
                if momentum_novo > limiar:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif momentum_novo < -limiar:
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
