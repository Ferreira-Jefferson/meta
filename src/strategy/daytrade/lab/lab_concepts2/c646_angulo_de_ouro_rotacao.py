"""Catálogo Gann/geometria sagrada, item 47: AnguloDeOuroRotacao.

APROXIMAÇÃO: espiral de Vogel (fórmula fechada) usando o ângulo de ouro
(137,5°) — `raio_k = c*sqrt(k)`, `angulo_k = k*137,5° mod 360`, projetada
num eixo de preço (`nivel_k = abertura + raio_k*cos(angulo_k)`) a partir da
abertura do pregão. Entra quando o preço revisita um nível gerado pela
espiral (tolerância em ticks), no sentido da rejeição.
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

_ANGULO_OURO_GRAUS = 137.5
_N_NIVEIS = 40


@dataclass
class AnguloDeOuroRotacao(IntradayStrategy):
    """Gera níveis de preço por uma espiral de Vogel (ângulo de ouro
    137,5°) a partir da abertura do pregão; entra na rejeição quando o
    preço revisita um desses níveis dentro da tolerância."""

    name: str = "angulo_de_ouro_rotacao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    raio_base_ticks: float = 4.0
    tolerancia_ticks: int = 2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _niveis: list[float] = field(default_factory=list, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._niveis = []

    def _gera_niveis(self, abertura: float) -> list[float]:
        niveis = []
        for k in range(1, _N_NIVEIS + 1):
            raio = self.raio_base_ticks * math.sqrt(k) * self.tick_size
            angulo_rad = math.radians((k * _ANGULO_OURO_GRAUS) % 360.0)
            niveis.append(abertura + raio * math.cos(angulo_rad))
        return niveis

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not self._niveis:
            self._niveis = self._gera_niveis(bar.open)
            return acao

        if not positions:
            tol = self.tolerancia_ticks * self.tick_size
            for nivel in self._niveis:
                if bar.low - tol <= nivel <= bar.high + tol:
                    if bar.close > nivel:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(min(nivel, limite) - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif bar.close < nivel:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(max(nivel, limite) + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    break

        return acao
