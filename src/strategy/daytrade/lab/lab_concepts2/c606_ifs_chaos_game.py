"""Catálogo caos/fractais, item 7: IFSChaosGame.

APROXIMAÇÃO HEURÍSTICA do "chaos game" de sistemas de funções iteradas:
define um "ponto atrator" como a média dos últimos N pivôs (topos/fundos de
3 barras), e projeta o próximo preço como o ponto médio entre o close atual
e esse atrator (a regra de meio-caminho do chaos-game real, aplicada uma
vez, não iterativamente). Entra quando o preço real se aproxima do preço
projetado, na direção do atrator.
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
class IFSChaosGame(IntradayStrategy):
    """Atrator = média dos últimos pivôs; projeção = ponto médio entre close
    e atrator; entra quando o preço real se aproxima da projeção."""

    name: str = "ifs_chaos_game"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    n_pivos: int = 6
    tolerancia_ticks: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _barras: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _pivos: deque = field(default_factory=lambda: deque(maxlen=6), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._barras = deque(maxlen=3)
        self._pivos = deque(maxlen=self.n_pivos)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._barras.append(bar)
        if len(self._barras) == 3:
            b0, b1, b2 = self._barras
            if b1.high > b0.high and b1.high > b2.high:
                self._pivos.append(b1.high)
            elif b1.low < b0.low and b1.low < b2.low:
                self._pivos.append(b1.low)

        if not positions and len(self._pivos) == self._pivos.maxlen:
            atrator = sum(self._pivos) / len(self._pivos)
            projecao = (bar.close + atrator) / 2.0
            tolerancia = self.tolerancia_ticks * self.tick_size
            if abs(bar.close - projecao) <= tolerancia:
                if atrator > bar.close:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif atrator < bar.close:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
        return acao
