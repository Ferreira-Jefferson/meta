"""Item 45 do catalogo: desvio entre media movel e mediana movel da MESMA
janela.

Entra na direcao que REDUZ essa divergencia (aposta em convergencia -- se a
media esta acima da mediana, aposta que o preco recua; se abaixo, aposta que
sobe); sai quando a divergencia fecha.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class DivergenciaMedianaVsMedia(IntradayStrategy):
    """Divergencia media-mediana da mesma janela -- aposta em convergencia."""

    name: str = "c444_divergencia_mediana_vs_media"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    divergencia_entrada_ticks: float = 2.0
    divergencia_saida_ticks: float = 0.5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) < self.janela:
            return []
        arr = np.asarray(self._closes, dtype=float)
        divergencia_ticks = (float(arr.mean()) - float(np.median(arr))) / self.tick_size

        if positions:
            if abs(divergencia_ticks) <= self.divergencia_saida_ticks:
                return [Exit(reason="divergencia_fechou")]
            return []

        if divergencia_ticks >= self.divergencia_entrada_ticks:
            # media puxada para cima da mediana -> aposta em recuo
            return [self._ordem("short", bar.close, "media_acima_mediana")]
        if divergencia_ticks <= -self.divergencia_entrada_ticks:
            return [self._ordem("long", bar.close, "media_abaixo_mediana")]
        return []

    def _ordem(self, side: str, preco_ref: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(preco_ref, self.tick_size)
        stop = no_tick(limite - sinal * self.stop_ticks * self.tick_size, self.tick_size)
        alvo = no_tick(limite + sinal * self.alvo_ticks * self.tick_size, self.tick_size)
        return EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=reason,
        )
