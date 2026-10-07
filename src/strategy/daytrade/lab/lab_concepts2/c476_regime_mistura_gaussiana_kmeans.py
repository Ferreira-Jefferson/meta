"""Item 77 do catalogo: APROXIMACAO de mistura de 2 gaussianas SEM EM
formal -- separa os retornos |ret| da janela em 2 grupos por um limiar
simples (mediana), recalcula media/variancia de cada grupo e reclassifica
por poucas iteracoes (k-means 1D simplificado, numpy puro).

Classifica a barra atual no componente mais proximo; barra no componente de
alta variancia (evento) opera REVERSAO, componente de baixa variancia
(regime calmo) nao opera.
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


def kmeans_1d_2grupos(x: np.ndarray, iteracoes: int = 5) -> tuple[float, float]:
    """K-means 1D simplificado com 2 centros, iniciado pela mediana."""
    mediana = float(np.median(x))
    centro_baixo = float(x[x <= mediana].mean()) if np.any(x <= mediana) else mediana
    centro_alto = float(x[x > mediana].mean()) if np.any(x > mediana) else mediana
    for _ in range(iteracoes):
        dist_baixo = np.abs(x - centro_baixo)
        dist_alto = np.abs(x - centro_alto)
        grupo_baixo = dist_baixo <= dist_alto
        if np.any(grupo_baixo):
            centro_baixo = float(x[grupo_baixo].mean())
        if np.any(~grupo_baixo):
            centro_alto = float(x[~grupo_baixo].mean())
    return min(centro_baixo, centro_alto), max(centro_baixo, centro_alto)


@dataclass
class RegimeMisturaGaussianaKmeans(IntradayStrategy):
    """Mistura de 2 gaussianas via k-means 1D sobre |retorno| -- reversao no evento."""

    name: str = "c476_regime_mistura_gaussiana_kmeans"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._retornos = deque(maxlen=self.janela)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        ret = None
        if self._close_anterior is not None and self._close_anterior != 0:
            ret = (bar.close - self._close_anterior) / self._close_anterior
            self._retornos.append(ret)
        self._close_anterior = bar.close

        if positions:
            componente_alto = self._componente_alto(ret) if ret is not None else None
            if componente_alto is False:
                return [Exit(reason="voltou_ao_regime_calmo")]
            return []

        if ret is None or len(self._retornos) < self.janela:
            return []
        componente_alto = self._componente_alto(ret)
        if not componente_alto:
            return []
        if ret > 0:
            return [self._ordem("short", bar.close, "evento_alta_reversao")]
        return [self._ordem("long", bar.close, "evento_baixa_reversao")]

    def _componente_alto(self, ret: float) -> bool:
        arr = np.abs(np.asarray(self._retornos, dtype=float))
        centro_baixo, centro_alto = kmeans_1d_2grupos(arr)
        dist_baixo = abs(abs(ret) - centro_baixo)
        dist_alto = abs(abs(ret) - centro_alto)
        return dist_alto <= dist_baixo

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
