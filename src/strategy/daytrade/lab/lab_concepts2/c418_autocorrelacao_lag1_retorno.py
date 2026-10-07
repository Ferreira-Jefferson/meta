"""AutocorrelacaoLag1Retorno -- segue ou reverte conforme a autocorrelacao de 1a ordem.

Autocorrelacao de 1a ordem dos retornos (`numpy.corrcoef` entre a serie e
sua propria defasagem em 1) numa janela movel. Autocorrelacao POSITIVA
acima do limiar segue a direcao da ultima barra (momentum); NEGATIVA
abaixo do limiar opera contra ela (reversao). Sai pelo stop/alvo fixos.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class AutocorrelacaoLag1Retorno(IntradayStrategy):
    """Momentum ou reversao conforme o sinal da autocorrelacao lag-1."""

    name: str = "c418_autocorrelacao_lag1_retorno"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    limiar_corr: float = 0.15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=41), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela + 1)

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

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        if positions:
            return []

        if len(self._retornos) < self.janela + 1:
            return []
        arr = np.array(self._retornos)
        a, b = arr[:-1], arr[1:]
        if a.std(ddof=0) <= 1e-12 or b.std(ddof=0) <= 1e-12:
            return []
        corr = float(np.corrcoef(a, b)[0, 1])
        if abs(corr) < self.limiar_corr:
            return []

        ultimo = arr[-1]
        if ultimo == 0:
            return []
        segue = corr > 0
        tick = self.tick_size
        vai_subir = (ultimo > 0) == segue
        if vai_subir:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
