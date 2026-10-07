"""Catálogo caos/fractais, item 11: PercolationCluster.

APROXIMAÇÃO HEURÍSTICA de percolação: binariza cada barra em alta/baixa e
mede o comprimento do cluster conectado atual (sequência corrente na mesma
direção) contra o comprimento esperado do maior cluster de um passeio
aleatório equivalente (`~log2(n)` barras de janela, aproximação simples de
runs de moeda justa) — não é a teoria de percolação em rede/grade real.

Quando o cluster observado excede estatisticamente o esperado, entra em
reversão (o movimento "correu demais" para ser passeio aleatório).
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


@dataclass
class PercolationCluster(IntradayStrategy):
    """Cluster conectado (sequência direcional atual) contra o esperado de
    um passeio aleatório equivalente (log2 da janela); excesso estatístico
    dispara reversão."""

    name: str = "percolation_cluster"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    fator_excesso: float = 1.6
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _direcao_atual: int = field(default=0, init=False, repr=False)
    _contador: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._direcao_atual = 0
        self._contador = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if len(self._closes) == 2:
            retorno = bar.close - self._closes[-1]
            direcao = 1 if retorno > 0 else (-1 if retorno < 0 else 0)
            if direcao != 0 and direcao == self._direcao_atual:
                self._contador += 1
            elif direcao != 0:
                self._direcao_atual = direcao
                self._contador = 1

            esperado = float(np.log2(max(self.janela, 2)))
            if not positions and self._contador >= self.fator_excesso * esperado:
                if self._direcao_atual > 0:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif self._direcao_atual < 0:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._closes.append(bar.close)
        return acao
