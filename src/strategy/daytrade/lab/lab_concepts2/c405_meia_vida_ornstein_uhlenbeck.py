"""MeiaVidaOrnsteinUhlenbeck -- reversao a media com meia-vida estimada.

Ajusta um processo Ornstein-Uhlenbeck discreto ao preco (regressao
`delta_t = a + b*preco_{t-1}` via numpy.polyfit numa janela movel) e
deriva a meia-vida de reversao `ln(2)/theta`, `theta=-b`. So opera quando
`b<0` (regime efetivamente mean-reverting) e a meia-vida cai dentro de um
horizonte operavel; entra na direcao do nivel de longo prazo `mu=-a/b`
quando o preco se afasta dele; o alvo mira `mu`; a saida tambem usa tempo
(numero de barras >= meia-vida arredondada, via `bars_held`) alem do
stop/alvo fixos.
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
class MeiaVidaOrnsteinUhlenbeck(IntradayStrategy):
    """Reversao a media com alvo = nivel de longo prazo do OU ajustado."""

    name: str = "c405_meia_vida_ornstein_uhlenbeck"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 80
    meia_vida_max_barras: float = 60.0
    desvio_minimo_ticks: float = 6.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks_min: int = 4
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=81), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 1)

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

    def _ajustar(self):
        if len(self._closes) < self.janela + 1:
            return None
        p = np.array(self._closes)
        nivel = p[:-1]
        delta = p[1:] - p[:-1]
        try:
            b, a = np.polyfit(nivel, delta, 1)
        except Exception:
            return None
        theta = -b
        if theta <= 1e-9 or abs(b) <= 1e-12:
            return None
        meia_vida = np.log(2.0) / theta
        if not (0 < meia_vida <= self.meia_vida_max_barras):
            return None
        mu = -a / b
        return float(mu), float(meia_vida)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)

        if positions:
            pos = positions[0]
            if pos.bars_held >= self.meia_vida_max_barras:
                return [Exit(reason=f"{self.name}_meia_vida_estourada")]
            return []

        ajuste = self._ajustar()
        if ajuste is None:
            return []
        mu, _meia_vida = ajuste
        tick = self.tick_size
        desvio = bar.close - mu
        if abs(desvio) < self.desvio_minimo_ticks * tick:
            return []

        alvo_dist = max(abs(desvio), self.alvo_ticks_min * tick)
        if desvio > 0:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, alvo_dist)
        return self._entrada("long", bar.close - self.offset_ticks * tick,
                              self.stop_ticks * tick, alvo_dist)
