"""Catálogo regime/adaptação, item 69: RegimeDeReversaoParaMedia.

Z-score do close contra a MA de `janela_media` períodos (mean/std móveis,
incrementais); entra CONTRA o desvio quando `|z| > limiar_z`, mas só
quando o detector de regime (Efficiency Ratio) indica LATERAL.
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


def _efficiency_ratio(closes: list[float]) -> float:
    if len(closes) < 2:
        return 0.0
    numerador = abs(closes[-1] - closes[0])
    denominador = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return numerador / denominador if denominador > 0 else 0.0


@dataclass
class RegimeDeReversaoParaMedia(IntradayStrategy):
    """Z-score do close vs MA de `janela_media` barras; entra contra o
    desvio quando `|z| > limiar_z`, só em regime LATERAL (ER < `limiar_er`)."""

    name: str = "regime_de_reversao_para_media"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_media: int = 20
    janela_regime: int = 14
    limiar_er: float = 0.3
    limiar_z: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes_media: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_regime: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes_media = deque(maxlen=self.janela_media)
        self._closes_regime = deque(maxlen=self.janela_regime + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_media.append(bar.close)
        self._closes_regime.append(bar.close)
        regime_lateral = _efficiency_ratio(list(self._closes_regime)) < self.limiar_er

        if (not positions and regime_lateral
                and len(self._closes_media) == self._closes_media.maxlen):
            media = sum(self._closes_media) / len(self._closes_media)
            variancia = sum((c - media) ** 2 for c in self._closes_media) / len(self._closes_media)
            desvio = variancia ** 0.5
            if desvio > 0:
                z = (bar.close - media) / desvio
                if z > self.limiar_z:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif z < -self.limiar_z:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        return acao
