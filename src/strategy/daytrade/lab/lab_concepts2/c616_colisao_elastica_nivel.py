"""Catálogo física, item 17: ColisaoElasticaNivel.

Analogia com colisão elástica: ao se aproximar de um topo/fundo prévio (o
"obstáculo") com velocidade V (delta de preço das últimas `janela_vel`
barras), espera-se reflexão de velocidade oposta. Entra contra-tendência
dimensionado pela velocidade de chegada (geometria mais larga quanto maior
V), stop além do nível (o "obstáculo" que a reflexão não deveria atravessar).
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
class ColisaoElasticaNivel(IntradayStrategy):
    """Ao aproximar de nível prévio com velocidade V, espera reflexão;
    entra contra-tendência dimensionado por V, stop além do nível."""

    name: str = "colisao_elastica_nivel"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_nivel: int = 30
    janela_velocidade: int = 3
    proximidade_ticks: float = 3.0
    offset_ticks: int = 1
    stop_extra_ticks: int = 6
    escala_alvo_por_velocidade: float = 2.0
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_nivel)
        self._lows = deque(maxlen=self.janela_nivel)
        self._closes = deque(maxlen=self.janela_velocidade + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._closes) == self._closes.maxlen):
            nivel_topo = max(self._highs)
            nivel_fundo = min(self._lows)
            velocidade = self._closes[-1] - self._closes[0]
            proximidade = self.proximidade_ticks * self.tick_size
            extra_ticks = min(abs(velocidade) / self.tick_size * self.escala_alvo_por_velocidade, 30.0)

            if abs(bar.close - nivel_topo) <= proximidade and velocidade > 0:
                limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(nivel_topo + self.stop_extra_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - (8 + extra_ticks) * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif abs(bar.close - nivel_fundo) <= proximidade and velocidade < 0:
                limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(nivel_fundo - self.stop_extra_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + (8 + extra_ticks) * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._closes.append(bar.close)
        return acao
