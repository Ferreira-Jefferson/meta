"""Catálogo física, item 15: RessonanciaHarmonicaCiclos.

APROXIMAÇÃO HEURÍSTICA de ressonância harmônica: detecta o "ciclo dominante"
como o lag (2..janela/2) com maior autocorrelação positiva dos retornos
numa janela rolling; mantém uma fase (barras desde o último cruzamento de
zero de close-EMA) e entra quando a fase se alinha com a metade do ciclo
dominante (fase ≈ ciclo/2, onde se espera o próximo topo/fundo).
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


def _lag_dominante(retornos: np.ndarray, lag_max: int) -> int | None:
    melhor_lag, melhor_valor = None, 0.0
    n = len(retornos)
    media = retornos.mean()
    var = ((retornos - media) ** 2).sum()
    if var < 1e-12:
        return None
    for lag in range(2, lag_max + 1):
        if lag >= n:
            break
        cov = ((retornos[:-lag] - media) * (retornos[lag:] - media)).sum()
        autocorr = cov / var
        if autocorr > melhor_valor:
            melhor_valor, melhor_lag = autocorr, lag
    return melhor_lag


@dataclass
class RessonanciaHarmonicaCiclos(IntradayStrategy):
    """Ciclo dominante via pico de autocorrelação dos retornos; entra
    quando a fase (barras desde o último cruzamento close-EMA) chega em
    metade do ciclo, na direção contrária ao movimento corrente (topo/fundo
    esperado)."""

    name: str = "ressonancia_harmonica_ciclos"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    lag_max: int = 20
    periodo_ema: int = 9
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _ema: float | None = field(default=None, init=False, repr=False)
    _sinal_ema_anterior: int = field(default=0, init=False, repr=False)
    _fase: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)
        self._ema = None
        self._sinal_ema_anterior = 0
        self._fase = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        alpha = 2.0 / (self.periodo_ema + 1)
        self._ema = bar.close if self._ema is None else alpha * bar.close + (1 - alpha) * self._ema
        sinal_ema = 1 if bar.close > self._ema else (-1 if bar.close < self._ema else self._sinal_ema_anterior)

        if self._sinal_ema_anterior != 0 and sinal_ema != self._sinal_ema_anterior:
            self._fase = 0
        else:
            self._fase += 1
        self._sinal_ema_anterior = sinal_ema

        if not positions and len(self._closes) == self._closes.maxlen:
            retornos = np.diff(np.array(self._closes))
            lag = _lag_dominante(retornos, self.lag_max)
            if lag is not None and lag >= 2:
                alvo_fase = lag // 2
                if self._fase == alvo_fase:
                    if sinal_ema > 0:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    else:
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
