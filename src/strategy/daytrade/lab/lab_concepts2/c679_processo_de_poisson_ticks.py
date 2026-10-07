"""Catálogo estatística/sinal, item 80: ProcessoDePoissonTicks.

Modela a chegada de volume por barra como processo de Poisson: estima a
taxa λ por uma média móvel rolante; entra quando o volume observado
excede o limite de confiança implicado por λ (aproximação normal de
Poisson, `λ + z*sqrt(λ)`, sem scipy) na direção do sinal da própria
barra.
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
class ProcessoDePoissonTicks(IntradayStrategy):
    """`λ` = média móvel de volume das últimas `janela_lambda` barras;
    entra na direção da própria barra quando `bar.volume` excede
    `λ + z_confianca*sqrt(λ)` (aproximação normal de um processo de
    Poisson)."""

    name: str = "processo_de_poisson_ticks"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_lambda: int = 20
    z_confianca: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _volumes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._volumes.maxlen != self.janela_lambda:
            self._volumes = deque(self._volumes, maxlen=self.janela_lambda)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._volumes) == self._volumes.maxlen:
            lam = sum(self._volumes) / len(self._volumes)
            limite_confianca = lam + self.z_confianca * (lam ** 0.5)
            if lam > 0 and bar.volume > limite_confianca and bar.close != bar.open:
                side = "long" if bar.close > bar.open else "short"
                if side == "long":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=side, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._volumes.append(bar.volume)
        return acao
