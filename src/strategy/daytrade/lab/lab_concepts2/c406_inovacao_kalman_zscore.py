"""InovacaoKalmanZScore -- reversao via inovacao padronizada de um Kalman 1D.

Um filtro de Kalman escalar (nivel = passeio aleatorio, ruidos de
processo `Q` e de medicao `R` fixos) estima o "preco justo"; a INOVACAO
(observado - previsto) e' padronizada pelo desvio-padrao das inovacoes
recentes. |z| extremo indica desvio anormal do justo -- entra CONTRA;
sai quando o z volta a cruzar zero, ou pelo stop/alvo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class InovacaoKalmanZScore(IntradayStrategy):
    """Kalman 1D de nivel; entra contra inovacoes extremas padronizadas."""

    name: str = "c406_inovacao_kalman_zscore"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    q_processo: float = 0.02
    r_medicao: float = 1.0
    janela_inovacoes: int = 40
    limiar_z: float = 2.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _x: float | None = field(default=None, init=False, repr=False)
    _p: float = field(default=1.0, init=False, repr=False)
    _inovacoes: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._x = None
        self._p = 1.0
        self._inovacoes = deque(maxlen=self.janela_inovacoes)

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
        if self._x is None:
            self._x = preco
            self._p = self.r_medicao
            return None
        p_pred = self._p + self.q_processo
        inovacao = preco - self._x
        k = p_pred / (p_pred + self.r_medicao)
        self._x = self._x + k * inovacao
        self._p = (1.0 - k) * p_pred
        self._inovacoes.append(inovacao)
        if len(self._inovacoes) < self.janela_inovacoes:
            return None
        arr = np.array(self._inovacoes)
        std = arr.std(ddof=0)
        if std <= 1e-9:
            return None
        return float(inovacao / std)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        z = self._atualizar(bar.close)

        if positions:
            if z is not None:
                pos = positions[0]
                if pos.side == "short" and z <= 0.0:
                    return [Exit(reason=f"{self.name}_zero_cross")]
                if pos.side == "long" and z >= 0.0:
                    return [Exit(reason=f"{self.name}_zero_cross")]
            return []

        if z is None:
            return []
        tick = self.tick_size
        if z >= self.limiar_z:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if z <= -self.limiar_z:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
