"""Catálogo caos/fractais, item 8: CorrelationDimensionGrassberger.

APROXIMAÇÃO HEURÍSTICA da dimensão de correlação (Grassberger-Procaccia):
embedding de atraso (dim=3) dos retornos numa janela rolling; conta pares de
pontos com distância euclidiana abaixo de dois raios (epsilon1 < epsilon2,
frações do desvio-padrão dos pontos) e ajusta a inclinação log-log entre
os dois — sem scipy, sem múltiplas escalas, sem correção de viés. Terreno
já tocado neste projeto (`wdo_quantico_oscilador_refutado_2026_09_24.md`) —
reteste com mecanismo próprio. Dimensão baixa (poucos graus de liberdade,
caminho mais estruturado) segue a tendência recente.
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


def _correlation_sum(pontos: np.ndarray, raio: float) -> float:
    n = len(pontos)
    dif = pontos[:, None, :] - pontos[None, :, :]
    dist = np.sqrt((dif ** 2).sum(axis=2))
    iu = np.triu_indices(n, k=1)
    pares = dist[iu]
    if len(pares) == 0:
        return 0.0
    return float(np.mean(pares < raio))


@dataclass
class CorrelationDimensionGrassberger(IntradayStrategy):
    """Dimensão de correlação aproximada sobre embedding rolling de
    retornos; dimensão baixa segue a tendência recente."""

    name: str = "correlation_dimension_grassberger"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 26
    limiar_dimensao: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=29), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 3)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if not positions and len(self._closes) == self._closes.maxlen:
            precos = np.array(self._closes)
            retornos = np.diff(precos)
            pontos = np.column_stack([retornos[2:], retornos[1:-1], retornos[:-2]])
            desvio = pontos.std()
            if desvio > 1e-9:
                eps1, eps2 = 0.5 * desvio, 1.0 * desvio
                c1, c2 = _correlation_sum(pontos, eps1), _correlation_sum(pontos, eps2)
                if c1 > 1e-6 and c2 > c1:
                    dimensao = float(np.log(c2 / c1) / np.log(eps2 / eps1))
                    if dimensao < self.limiar_dimensao:
                        ultimo_retorno = precos[-1] - precos[-2]
                        if ultimo_retorno > 0:
                            limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side="long", limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]
                        elif ultimo_retorno < 0:
                            limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side="short", limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]

        self._closes.append(bar.close)
        return acao
