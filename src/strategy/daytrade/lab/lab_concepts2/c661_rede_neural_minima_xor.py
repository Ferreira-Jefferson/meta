"""Catálogo autômatos/ML/jogos, item 62: RedeNeuralMinimaXOR.

Rede minimalista 2-2-1 (numpy puro, sem lib de ML) treinada por
gradiente descendente manual em `initialize` sobre o padrão não-linear
"2 retornos defasados binarizados prevendo o sinal do retorno seguinte";
entra na ativação de saída.
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


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class RedeNeuralMinimaXOR(IntradayStrategy):
    """Rede 2 entradas -> 2 ocultas -> 1 saída, numpy puro, treinada por
    gradiente descendente manual em `initialize` sobre 2 sinais de
    retorno defasados; entra quando a ativação de saída ultrapassa os
    limiares."""

    name: str = "rede_neural_minima_xor"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    epocas: int = 300
    taxa_aprendizado: float = 0.5
    limiar_alto: float = 0.6
    limiar_baixo: float = 0.4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _w1: np.ndarray = field(default=None, init=False, repr=False)
    _b1: np.ndarray = field(default=None, init=False, repr=False)
    _w2: np.ndarray = field(default=None, init=False, repr=False)
    _b2: float = field(default=0.0, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _sinais_lag: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        closes = bars["close"].to_numpy(dtype=float)
        retornos = np.diff(closes)
        sinais = np.where(retornos > 0, 1.0, -1.0)
        n = len(sinais)

        self._w1 = np.zeros((2, 2))
        self._b1 = np.zeros(2)
        self._w2 = np.zeros(2)
        self._b2 = 0.0
        if n < 20:
            return

        X = np.stack([sinais[:-2], sinais[1:-1]], axis=1)
        y = (sinais[2:] > 0).astype(float)

        rng = np.random.default_rng(42)
        w1 = rng.normal(0, 0.5, size=(2, 2))
        b1 = np.zeros(2)
        w2 = rng.normal(0, 0.5, size=2)
        b2 = 0.0
        m = len(y)

        for _ in range(self.epocas):
            z1 = X @ w1 + b1
            a1 = _sigmoid(z1)
            z2 = a1 @ w2 + b2
            a2 = _sigmoid(z2)

            erro = a2 - y
            grad_z2 = erro * a2 * (1 - a2)
            grad_w2 = a1.T @ grad_z2 / m
            grad_b2 = grad_z2.mean()

            grad_a1 = np.outer(grad_z2, w2)
            grad_z1 = grad_a1 * a1 * (1 - a1)
            grad_w1 = X.T @ grad_z1 / m
            grad_b1 = grad_z1.mean(axis=0)

            w2 -= self.taxa_aprendizado * grad_w2
            b2 -= self.taxa_aprendizado * grad_b2
            w1 -= self.taxa_aprendizado * grad_w1
            b1 -= self.taxa_aprendizado * grad_b1

        self._w1, self._b1, self._w2, self._b2 = w1, b1, w2, float(b2)

    def on_session_start(self, session_date) -> None:
        self._close_anterior = None
        self._sinais_lag = deque(maxlen=2)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if (not positions and self._w1 is not None
                and len(self._sinais_lag) == self._sinais_lag.maxlen):
            x = np.array(self._sinais_lag)  # [lag2, lag1], mais antigo primeiro
            a1 = _sigmoid(x @ self._w1 + self._b1)
            saida = float(_sigmoid(a1 @ self._w2 + self._b2))

            side = None
            if saida > self.limiar_alto:
                side = "long"
            elif saida < self.limiar_baixo:
                side = "short"

            if side is not None:
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
            ret = bar.close - self._close_anterior
            self._sinais_lag.append(1.0 if ret > 0 else -1.0)
        self._close_anterior = bar.close
        return acao
