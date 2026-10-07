"""Catálogo autômatos/ML/jogos, item 66: AlgoritmoGeneticoPadraoVencedor.

Evolui (numpy puro, sem lib de GA) uma pequena população de genomas --
sequências quantizadas de direção de `k` velas -- avaliados pelo retorno
futuro médio histórico que cada padrão precedeu, dentro de `initialize`.
Ao vivo, entra quando a sequência corrente casa com o genoma de maior
aptidão.
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

K_GENOMA = 4
POPULACAO = 12
GERACOES = 15


def _fitness(genoma: np.ndarray, direcoes: np.ndarray, retornos_fwd: np.ndarray) -> float:
    """Retorno futuro médio nas ocorrências históricas EXATAS do padrão."""
    n = len(genoma)
    janelas = np.lib.stride_tricks.sliding_window_view(direcoes, n)
    casadas = np.all(janelas == genoma, axis=1)
    if not casadas.any():
        return 0.0
    idx = np.nonzero(casadas)[0] + n - 1
    idx = idx[idx < len(retornos_fwd)]
    if len(idx) == 0:
        return 0.0
    return float(np.abs(retornos_fwd[idx]).mean() * np.sign(retornos_fwd[idx].mean()))


@dataclass
class AlgoritmoGeneticoPadraoVencedor(IntradayStrategy):
    """População de genomas (sequências de direção de `K_GENOMA` velas)
    evoluída por mutação/crossover simples em `initialize`, avaliada pelo
    retorno futuro médio histórico; entra quando a sequência ao vivo
    casa com o genoma vencedor."""

    name: str = "algoritmo_genetico_padrao_vencedor"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _genoma_vencedor: tuple = field(default=(), init=False, repr=False)
    _genoma_dir: int = field(default=0, init=False, repr=False)
    _direcoes: deque = field(default_factory=lambda: deque(maxlen=K_GENOMA), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        closes = bars["close"].to_numpy(dtype=float)
        if len(closes) < 100:
            return
        retornos = np.diff(closes) / closes[:-1]
        direcoes = np.where(retornos > 0, 1, -1).astype(int)
        retornos_fwd = np.concatenate([retornos[1:], [0.0]])

        rng = np.random.default_rng(7)
        populacao = [rng.choice([-1, 1], size=K_GENOMA) for _ in range(POPULACAO)]

        for _ in range(GERACOES):
            aptidoes = np.array([_fitness(g, direcoes, retornos_fwd) for g in populacao])
            ordem = np.argsort(aptidoes)[::-1]
            populacao = [populacao[i] for i in ordem]
            aptidoes = aptidoes[ordem]

            sobreviventes = populacao[:POPULACAO // 2]
            filhos = []
            for i in range(len(sobreviventes) - 1):
                corte = rng.integers(1, K_GENOMA)
                filho = np.concatenate([sobreviventes[i][:corte], sobreviventes[i + 1][corte:]])
                if rng.random() < 0.2:
                    pos = rng.integers(0, K_GENOMA)
                    filho[pos] *= -1
                filhos.append(filho)
            while len(sobreviventes) + len(filhos) < POPULACAO:
                filhos.append(rng.choice([-1, 1], size=K_GENOMA))
            populacao = sobreviventes + filhos

        aptidoes = np.array([_fitness(g, direcoes, retornos_fwd) for g in populacao])
        melhor = int(np.argmax(np.abs(aptidoes)))
        self._genoma_vencedor = tuple(int(v) for v in populacao[melhor])
        self._genoma_dir = 1 if aptidoes[melhor] > 0 else -1

    def on_session_start(self, session_date) -> None:
        self._direcoes = deque(maxlen=K_GENOMA)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if (not positions and self._genoma_vencedor
                and len(self._direcoes) == self._direcoes.maxlen
                and tuple(self._direcoes) == self._genoma_vencedor):
            side = "long" if self._genoma_dir > 0 else "short"
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

        if self._close_anterior is not None:
            self._direcoes.append(1 if bar.close > self._close_anterior else -1)
        self._close_anterior = bar.close
        return acao
