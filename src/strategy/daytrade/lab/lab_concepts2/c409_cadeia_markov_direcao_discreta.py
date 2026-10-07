"""CadeiaMarkovDirecaoDiscreta -- cadeia de Markov de 1a ordem sobre direcao.

Discretiza cada barra em {baixa, neutra, alta} (contra um limiar de
ticks) e estima ONLINE a matriz de transicao de 1a ordem por contagem
simples (sem lib). Entra na direcao (alta/baixa) de maior probabilidade
condicional ao estado atual, quando essa probabilidade excede o acaso
(1/3) por uma margem -- ignora previsao de estado neutro. Sai apos N
barras (simplificacao do "ou quando a probabilidade cai abaixo do
limiar" do catalogo: recomputar a prob a cada barra tambem funcionaria,
mas o corte por tempo e' mais simples e documentado aqui como tal).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

# indices de estado: 0=baixa, 1=neutra, 2=alta
_BAIXA, _NEUTRA, _ALTA = 0, 1, 2


@dataclass
class CadeiaMarkovDirecaoDiscreta(IntradayStrategy):
    """Markov de 1a ordem sobre direcao discretizada da barra."""

    name: str = "c409_cadeia_markov_direcao_discreta"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    epsilon_ticks: float = 1.0
    min_observacoes: int = 30
    margem_sobre_acaso: float = 0.12
    saida_barras: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _contagens: np.ndarray = field(default_factory=lambda: np.zeros((3, 3)), init=False, repr=False)
    _estado_anterior: int | None = field(default=None, init=False, repr=False)
    _ultimo_close: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._contagens = np.zeros((3, 3))
        self._estado_anterior = None
        self._ultimo_close = None

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

    def _estado(self, bar: Bar) -> int | None:
        if self._ultimo_close is None:
            self._ultimo_close = bar.close
            return None
        delta = bar.close - self._ultimo_close
        self._ultimo_close = bar.close
        eps = self.epsilon_ticks * self.tick_size
        if delta > eps:
            return _ALTA
        if delta < -eps:
            return _BAIXA
        return _NEUTRA

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        estado_atual = self._estado(bar)
        if estado_atual is not None and self._estado_anterior is not None:
            self._contagens[self._estado_anterior, estado_atual] += 1.0
        if estado_atual is not None:
            self._estado_anterior = estado_atual

        if positions:
            pos = positions[0]
            if pos.bars_held >= self.saida_barras:
                return [Exit(reason=f"{self.name}_prazo")]
            return []

        if estado_atual is None:
            return []
        linha = self._contagens[estado_atual]
        total = linha.sum()
        if total < self.min_observacoes:
            return []
        probs = linha / total
        limiar = 1.0 / 3.0 + self.margem_sobre_acaso
        tick = self.tick_size
        if probs[_ALTA] >= limiar and probs[_ALTA] > probs[_BAIXA]:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if probs[_BAIXA] >= limiar and probs[_BAIXA] > probs[_ALTA]:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
