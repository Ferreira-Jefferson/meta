"""Catálogo catástrofe/criticalidade, item 85: EfeitoBorboletaMicroPerturbacao.

Dentro de um regime já calmo (mediana de range baixa), detecta uma barra
outlier com range ANDA MAIS baixo que o normal do próprio regime calmo
(z-score do range muito negativo) -- uma micro-perturbação. Trata a
direção dessa barra como semente de um movimento posterior
desproporcional: entra com alvo LARGO e stop normal.
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
class EfeitoBorboletaMicroPerturbacao(IntradayStrategy):
    """Regime calmo = mediana de range da janela abaixo de
    `calmo_ticks_max` ticks; dentro dele, uma barra com z-score de range
    abaixo de `-limiar_z` (bem menor que o já pequeno range do regime) é
    a micro-perturbação semente; entra na direção dela com alvo largo."""

    name: str = "efeito_borboleta_micro_perturbacao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    calmo_ticks_max: float = 3.0
    limiar_z: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 8
    alvo_ticks: int = 24
    entrada_ttl_bars: int = 40

    _ranges: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._ranges.maxlen != self.janela:
            self._ranges = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng_atual = bar.high - bar.low

        if not positions and len(self._ranges) == self._ranges.maxlen:
            ranges = list(self._ranges)
            mediana = sorted(ranges)[len(ranges) // 2]
            regime_calmo = mediana <= self.calmo_ticks_max * self.tick_size

            if regime_calmo:
                media = sum(ranges) / len(ranges)
                dp = (sum((r - media) ** 2 for r in ranges) / len(ranges)) ** 0.5
                z = (rng_atual - media) / dp if dp > 0 else 0.0
                if z < -self.limiar_z:
                    side = "long" if bar.close >= bar.open else "short"
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

        self._ranges.append(rng_atual)
        return acao
