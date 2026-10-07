"""Catálogo autômatos/ML/jogos, item 58: LogicaFuzzyIndicadores.

Fuzzifica momentum (retorno de N barras) e volume (z-score) em graus de
pertinência triangulares fraco/médio/forte; combina via regras fuzzy
(min para AND) e defuzzifica por centróide de singletons; entra quando o
score cruza o limiar.
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


def _pertinencia_triangular(x: float, a: float, b: float, c: float) -> float:
    """Pertinência triangular padrão, pico em `b`, zero fora de [a, c]."""
    if x <= a or x >= c:
        return 0.0
    if x == b:
        return 1.0
    if x < b:
        return (x - a) / (b - a)
    return (c - x) / (c - b)


@dataclass
class LogicaFuzzyIndicadores(IntradayStrategy):
    """Momentum e volume fuzzificados (fraco/médio/forte) combinados por
    regras Mamdani simplificadas (min); score defuzzificado por centróide
    de singletons decide a entrada."""

    name: str = "logica_fuzzy_indicadores"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_momentum: int = 10
    janela_vol_z: int = 20
    limiar_score: float = 0.35
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=11), init=False, repr=False)
    _volumes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_momentum + 1)
        self._volumes = deque(maxlen=self.janela_vol_z)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._volumes.append(bar.volume)

        if (not positions and len(self._closes) == self._closes.maxlen
                and len(self._volumes) == self._volumes.maxlen):
            momentum = (bar.close - self._closes[0]) / self._closes[0]
            vol_arr = list(self._volumes)
            vol_mm = sum(vol_arr) / len(vol_arr)
            vol_dp = (sum((v - vol_mm) ** 2 for v in vol_arr) / len(vol_arr)) ** 0.5
            vol_z = (bar.volume - vol_mm) / vol_dp if vol_dp > 0 else 0.0

            escala_mom = 0.01
            mom_forte_pos = _pertinencia_triangular(momentum, 0.0, escala_mom, 2 * escala_mom)
            mom_forte_neg = _pertinencia_triangular(momentum, -2 * escala_mom, -escala_mom, 0.0)
            mom_fraco = _pertinencia_triangular(momentum, -escala_mom, 0.0, escala_mom)
            vol_forte = _pertinencia_triangular(vol_z, 0.5, 2.0, 4.0)

            peso_alto = min(mom_forte_pos, vol_forte)
            peso_baixo = min(mom_forte_neg, vol_forte)
            peso_neutro = mom_fraco
            soma_pesos = peso_alto + peso_baixo + peso_neutro
            score = (peso_alto - peso_baixo) / soma_pesos if soma_pesos > 0 else 0.0

            if abs(score) > self.limiar_score:
                side = "long" if score > 0 else "short"
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

        self._closes.append(bar.close)
        return acao
