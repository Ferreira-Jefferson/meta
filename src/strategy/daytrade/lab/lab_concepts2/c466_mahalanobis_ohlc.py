"""Item 67 do catalogo: distancia de Mahalanobis multivariada sobre o vetor
3D (retorno do corpo, retorno da sombra superior, retorno da sombra
inferior) de cada candle, com matriz de covariancia rolling e
`numpy.linalg.pinv` (numpy puro, permitido).

Entra em reversao (fade do corpo do candle) quando a distancia excede um
limiar EMPIRICO (nao qui-quadrado formal); sai no retorno a' regiao central.
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
class MahalanobisOhlc(IntradayStrategy):
    """Distancia de Mahalanobis do vetor (corpo, sombra sup, sombra inf)."""

    name: str = "c466_mahalanobis_ohlc"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    distancia_entrada: float = 3.0
    distancia_saida: float = 1.0
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _vetores: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vetores = deque(maxlen=self.janela)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        base = self._close_anterior or bar.open or bar.close
        self._close_anterior = bar.close
        if base == 0:
            return []
        corpo = (bar.close - bar.open) / base
        sombra_sup = (bar.high - max(bar.open, bar.close)) / base
        sombra_inf = (min(bar.open, bar.close) - bar.low) / base
        vetor = np.array([corpo, sombra_sup, sombra_inf], dtype=float)
        self._vetores.append(vetor)

        if len(self._vetores) < self.janela:
            return []
        distancia = self._mahalanobis(vetor)

        if positions:
            if distancia is not None and distancia <= self.distancia_saida:
                return [Exit(reason="mahalanobis_normalizou")]
            return []

        if distancia is None or distancia < self.distancia_entrada:
            return []
        if corpo >= 0:
            return [self._ordem("short", bar.close, f"mahalanobis_extremo_{distancia:.2f}")]
        return [self._ordem("long", bar.close, f"mahalanobis_extremo_{distancia:.2f}")]

    def _mahalanobis(self, vetor: np.ndarray) -> float | None:
        matriz = np.asarray(self._vetores, dtype=float)
        media = matriz.mean(axis=0)
        cov = np.cov(matriz, rowvar=False)
        try:
            inv_cov = np.linalg.pinv(cov)
        except np.linalg.LinAlgError:
            return None
        delta = vetor - media
        d2 = float(delta @ inv_cov @ delta)
        if d2 < 0:
            return None
        return float(np.sqrt(d2))

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
