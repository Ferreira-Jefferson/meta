"""Catálogo Gann/geometria sagrada, item 39: QuadradoDeNove.

APROXIMAÇÃO do Gann Square of Nine: mapeia preço num ângulo de espiral via
`sqrt(preco)*360 mod 360`. Compara o ângulo do preço atual ao ângulo do
pivô de abertura da sessão; quando a diferença se alinha (tolerância em
graus) a um ângulo cardeal/diagonal (0/45/90/.../315), entra no sentido do
rompimento do pivô.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

_ANGULOS_CARDEAIS = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0, 360.0]


@dataclass
class QuadradoDeNove(IntradayStrategy):
    """Ângulo de Gann Square of Nine (`sqrt(preco)*360 mod 360`) do preço
    atual relativo ao pivô de abertura; alinhamento com ângulo cardeal
    dentro da tolerância + rompimento do pivô dispara entrada."""

    name: str = "quadrado_de_nove"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    tolerancia_graus: float = 3.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _pivo_abertura: float | None = field(default=None, init=False, repr=False)
    _angulo_pivo: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._pivo_abertura = None
        self._angulo_pivo = None

    @staticmethod
    def _angulo_de_preco(preco: float) -> float:
        if preco <= 0:
            return 0.0
        return (math.sqrt(preco) * 360.0) % 360.0

    def _alinhado_a_cardeal(self, diff: float) -> bool:
        diff = diff % 360.0
        for cardeal in _ANGULOS_CARDEAIS:
            if abs(diff - cardeal) <= self.tolerancia_graus:
                return True
        return False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if self._pivo_abertura is None:
            self._pivo_abertura = bar.open
            self._angulo_pivo = self._angulo_de_preco(bar.open)
            return acao

        if not positions and self._angulo_pivo is not None:
            angulo_atual = self._angulo_de_preco(bar.close)
            diff = angulo_atual - self._angulo_pivo
            if self._alinhado_a_cardeal(diff):
                if bar.close > self._pivo_abertura:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif bar.close < self._pivo_abertura:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        return acao
