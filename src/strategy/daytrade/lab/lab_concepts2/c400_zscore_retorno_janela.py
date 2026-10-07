"""ZScoreRetornoJanela -- reversao a media via z-score do retorno log.

Padroniza o retorno log de cada barra contra media/desvio de uma janela
movel de retornos passados. |z| extremo indica retorno anormal, e a
estrategia aposta na reversao: entra CONTRA o sinal (retorno alto ->
short, retorno baixo -> long). Sai quando o z-score cruza zero (reversao
completa) ou pelo stop/alvo fixos, o que vier primeiro.
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
class ZScoreRetornoJanela(IntradayStrategy):
    """Reversao a media via z-score do retorno log de 1 barra."""

    name: str = "c400_zscore_retorno_janela"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    limiar_z: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)

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

    def _z(self) -> float | None:
        if len(self._retornos) < self.janela:
            return None
        arr = np.array(self._retornos)
        std = arr.std(ddof=0)
        if std <= 1e-12:
            return None
        return float((arr[-1] - arr.mean()) / std)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        z = self._z()

        if positions:
            if z is not None:
                pos = positions[0]
                if pos.side == "short" and z <= 0.0:
                    return [Exit(reason=f"{self.name}_zero_cross")]
                if pos.side == "long" and z >= 0.0:
                    return [Exit(reason=f"{self.name}_zero_cross")]
            return []

        if z is None:
            return []
        tick = self.tick_size
        if z >= self.limiar_z:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if z <= -self.limiar_z:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
