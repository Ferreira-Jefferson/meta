"""TesteSinalBinomialViesDirecional -- proporcao de altas vs 0,5 por z-score.

Proporcao de barras de alta numa janela curta comparada a 0,5 via
aproximacao NORMAL do binomial (`z = (p-0,5)/sqrt(0,25/n)`, sem
`scipy.stats.binom`). |z| grande indica vies direcional na janela --
entra na direcao do vies. Sai apos N barras (via `bars_held`) ou pelo
stop/alvo, o que vier primeiro.
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
class TesteSinalBinomialViesDirecional(IntradayStrategy):
    """Entra na direcao do vies quando a proporcao de altas foge de 0,5."""

    name: str = "c416_teste_sinal_binomial_vies_direcional"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    limiar_z: float = 1.8
    saida_barras: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ultimo_close: float | None = field(default=None, init=False, repr=False)
    _sinais: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ultimo_close = None
        self._sinais = deque(maxlen=self.janela)

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
        if self._ultimo_close is not None:
            self._sinais.append(1 if bar.close >= self._ultimo_close else 0)
        self._ultimo_close = bar.close

        if positions:
            pos = positions[0]
            if pos.bars_held >= self.saida_barras:
                return [Exit(reason=f"{self.name}_prazo")]
            return []

        if len(self._sinais) < self.janela:
            return []
        n = len(self._sinais)
        p = sum(self._sinais) / n
        erro_padrao = np.sqrt(0.25 / n)
        z = (p - 0.5) / erro_padrao
        if abs(z) < self.limiar_z:
            return []

        tick = self.tick_size
        if z > 0:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
