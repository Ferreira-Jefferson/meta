"""Catálogo caos/fractais, item 5: BifurcacaoCascata.

APROXIMAÇÃO HEURÍSTICA da cascata de bifurcações de Feigenbaum: mede a razão
entre amplitudes de swings sucessivos (topo-fundo-topo via pivôs locais
simples de 3 barras) e testa se ela se aproxima da constante de Feigenbaum
(~4,669) — sem qualquer ligação formal ao mapa que gera a constante, só
usando o número como "zona de instabilidade" candidata a virada de regime.

Quando a razão de swings recentes fica perto de 4,669 junto de um pivô
(topo ou fundo), entra em reversão (fade do movimento que formou o pivô).
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
FEIGENBAUM = 4.669201609


@dataclass
class BifurcacaoCascata(IntradayStrategy):
    """Razão entre amplitudes de swings sucessivos; perto da constante de
    Feigenbaum num pivô, entra em reversão."""

    name: str = "bifurcacao_cascata"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    tolerancia_relativa: float = 0.35
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _barras: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _swings: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)
    _ultimo_pivo_preco: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._barras = deque(maxlen=3)
        self._swings = deque(maxlen=4)
        self._ultimo_pivo_preco = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._barras.append(bar)
        if len(self._barras) == 3 and not positions:
            b0, b1, b2 = self._barras
            pivo_topo = b1.high > b0.high and b1.high > b2.high
            pivo_fundo = b1.low < b0.low and b1.low < b2.low
            preco_pivo = None
            if pivo_topo:
                preco_pivo = b1.high
            elif pivo_fundo:
                preco_pivo = b1.low
            if preco_pivo is not None:
                if self._ultimo_pivo_preco is not None:
                    self._swings.append(abs(preco_pivo - self._ultimo_pivo_preco))
                self._ultimo_pivo_preco = preco_pivo

                if len(self._swings) >= 2 and self._swings[-2] > 1e-9:
                    razao = self._swings[-1] / self._swings[-2]
                    if abs(razao - FEIGENBAUM) <= self.tolerancia_relativa * FEIGENBAUM:
                        if pivo_topo:
                            limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side="short", limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]
                        else:
                            limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side="long", limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]
        return acao
