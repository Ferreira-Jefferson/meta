"""Item 43 do catalogo: soma cumulativa de retornos desde a abertura,
padronizada pela escala esperada de um passeio aleatorio (sigma * sqrt(t)).

Entra CONTRA o desvio quando o z do acumulado e' extremo (aposta em reversao
a media); sai quando volta a faixa esperada (|z| pequeno).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class CumulativoDriftZScore(IntradayStrategy):
    """Z-score do drift acumulado da sessao contra a escala de passeio aleatorio."""

    name: str = "c442_cumulativo_drift_zscore"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    minimo_amostras: int = 15
    z_entrada: float = 2.0
    z_saida: float = 0.5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(), init=False, repr=False)
    _cum: float = field(default=0.0, init=False, repr=False)
    _n_bars: int = field(default=0, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._retornos = deque()
        self._cum = 0.0
        self._n_bars = 0
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        ret = None
        if self._close_anterior is not None and self._close_anterior != 0:
            ret = (bar.close - self._close_anterior) / self._close_anterior
        self._close_anterior = bar.close
        if ret is not None:
            self._retornos.append(ret)
            self._cum += ret
            self._n_bars += 1

        z = self._z()
        if positions:
            if z is None:
                return []
            pos = positions[0]
            if pos.side == "long" and z >= -self.z_saida:
                return [Exit(reason="drift_normalizou")]
            if pos.side == "short" and z <= self.z_saida:
                return [Exit(reason="drift_normalizou")]
            return []

        if z is None:
            return []
        if z <= -self.z_entrada:
            return [self._ordem("long", bar.close, "drift_extremo_baixo")]
        if z >= self.z_entrada:
            return [self._ordem("short", bar.close, "drift_extremo_alto")]
        return []

    def _z(self) -> float | None:
        if self._n_bars < self.minimo_amostras or len(self._retornos) < self.minimo_amostras:
            return None
        sigma = float(np.std(np.asarray(self._retornos, dtype=float)))
        if sigma <= 0:
            return None
        escala = sigma * np.sqrt(self._n_bars)
        if escala <= 0:
            return None
        return float(self._cum / escala)

    def _ordem(self, side: str, preco_ref: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(preco_ref, self.tick_size)
        stop = no_tick(limite - sinal * self.stop_ticks * self.tick_size, self.tick_size)
        alvo = no_tick(limite + sinal * self.alvo_ticks * self.tick_size, self.tick_size)
        return EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=reason,
        )
