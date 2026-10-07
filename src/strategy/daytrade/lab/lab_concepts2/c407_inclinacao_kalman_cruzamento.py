"""InclinacaoKalmanCruzamento -- momentum via inclinacao de um Kalman nivel+tendencia.

Filtro de Kalman 2D (estado = [nivel, inclinacao], transicao
`nivel_t = nivel_{t-1} + inclinacao_{t-1}`, `inclinacao_t = inclinacao_{t-1}`,
ruidos de processo/medicao `Q`/`R` constantes, ganho recursivo padrao).
O sinal e' o CRUZAMENTO de sinal da inclinacao filtrada: entra na
direcao da nova inclinacao quando ela muda de sinal; sai quando ela
cruza de novo para o lado oposto.
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


@dataclass
class InclinacaoKalmanCruzamento(IntradayStrategy):
    """Segue a inclinacao de um Kalman nivel+tendencia quando ela troca de sinal."""

    name: str = "c407_inclinacao_kalman_cruzamento"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    q_nivel: float = 0.01
    q_inclinacao: float = 0.001
    r_medicao: float = 1.0
    inclinacao_minima_ticks: float = 0.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _x: np.ndarray | None = field(default=None, init=False, repr=False)
    _p: np.ndarray | None = field(default=None, init=False, repr=False)
    _sinal_anterior: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._x = None
        self._p = None
        self._sinal_anterior = 0

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

    def _atualizar(self, preco: float) -> float | None:
        f = np.array([[1.0, 1.0], [0.0, 1.0]])
        q = np.array([[self.q_nivel, 0.0], [0.0, self.q_inclinacao]])
        h = np.array([1.0, 0.0])
        r = self.r_medicao
        if self._x is None:
            self._x = np.array([preco, 0.0])
            self._p = np.eye(2) * r
            return None
        x_pred = f @ self._x
        p_pred = f @ self._p @ f.T + q
        inovacao = preco - float(h @ x_pred)
        s = float(h @ p_pred @ h) + r
        k = (p_pred @ h) / s
        self._x = x_pred + k * inovacao
        self._p = (np.eye(2) - np.outer(k, h)) @ p_pred
        return float(self._x[1])

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        inclinacao = self._atualizar(bar.close)
        tick = self.tick_size
        limiar = self.inclinacao_minima_ticks * tick

        if inclinacao is None:
            return []
        if inclinacao > limiar:
            sinal_atual = 1
        elif inclinacao < -limiar:
            sinal_atual = -1
        else:
            sinal_atual = self._sinal_anterior

        if positions:
            pos = positions[0]
            saiu = (
                (pos.side == "long" and sinal_atual == -1)
                or (pos.side == "short" and sinal_atual == 1)
            )
            self._sinal_anterior = sinal_atual
            if saiu:
                return [Exit(reason=f"{self.name}_cruzamento_oposto")]
            return []

        cruzou = sinal_atual != 0 and sinal_atual != self._sinal_anterior
        self._sinal_anterior = sinal_atual
        if not cruzou:
            return []

        if sinal_atual == 1:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
