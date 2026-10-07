"""RazaoVolatilidadeCurtaLonga -- reversao quando a vol de curto prazo infla.

Razao entre a volatilidade realizada (desvio-padrao dos retornos) de uma
janela CURTA e uma janela LONGA. Razao muito acima de 1 indica um surto
de volatilidade recente relativo ao regime normal -- opera reversao
(contra a ultima barra), apostando que o surto e' transitorio. Sai
quando a razao volta perto de 1 (normalizou), ou pelo stop/alvo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class RazaoVolatilidadeCurtaLonga(IntradayStrategy):
    """Reversao quando a razao vol curta/longa infla acima do normal."""

    name: str = "c432_razao_volatilidade_curta_longa"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_curta: int = 10
    janela_longa: int = 50
    limiar_entrada: float = 1.4
    limiar_saida: float = 1.1
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=50), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela_longa)

    def _entrada(self, side: str, limite: float, stop_dist: float, alvo_dist: float) -> list[IntradayAction]:
        tick = self.tick_size
        limite = no_tick(limite, tick)
        if side == "long":
            stop = no_tick(limite - stop_dist, tick)
            alvo = no_tick(limite + alvo_dist, tick)
        else:
            stop = no_tick(limite + stop_dist, tick)
            alvo = no_tick(limite - alvo_dist, tick)
        return [EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def _razao(self) -> float | None:
        if len(self._retornos) < self.janela_longa:
            return None
        arr = np.array(self._retornos)
        vol_curta = arr[-self.janela_curta:].std(ddof=0)
        vol_longa = arr.std(ddof=0)
        if vol_longa <= 1e-12:
            return None
        return float(vol_curta / vol_longa)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        razao = self._razao()

        if positions:
            if razao is not None and razao < self.limiar_saida:
                return [Exit(reason=f"{self.name}_normalizou")]
            return []

        if razao is None or razao < self.limiar_entrada or not self._retornos:
            return []
        ultimo = self._retornos[-1]
        if ultimo == 0:
            return []
        tick = self.tick_size
        if ultimo > 0:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("long", bar.close - self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
