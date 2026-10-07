"""FuncaoAutocorrelacaoMultiLagPACF -- opera o lag de maior autocorrelacao simples.

Calcula a autocorrelacao SIMPLES (nao a parcial formal -- aproximada por
correlacao direta, `numpy.corrcoef`) dos retornos ate o lag `k_max` numa
janela movel, e usa o lag de maior |correlacao| como "periodo operado":
corr positiva no lag escolhido segue a direcao da ultima barra
(momentum); corr negativa opera contra ela (reversao). Sai quando a
correlacao daquele MESMO lag, recomputada a cada barra, cai abaixo da
metade do valor de pico observado na entrada -- ou pelo stop/alvo.
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


def _melhor_lag(arr: np.ndarray, k_max: int) -> tuple[int, float] | None:
    melhor_lag, melhor_corr = None, 0.0
    for lag in range(1, k_max + 1):
        if len(arr) <= lag + 5:
            break
        a, b = arr[:-lag], arr[lag:]
        if a.std(ddof=0) <= 1e-12 or b.std(ddof=0) <= 1e-12:
            continue
        corr = float(np.corrcoef(a, b)[0, 1])
        if abs(corr) > abs(melhor_corr):
            melhor_lag, melhor_corr = lag, corr
    if melhor_lag is None:
        return None
    return melhor_lag, melhor_corr


@dataclass
class FuncaoAutocorrelacaoMultiLagPACF(IntradayStrategy):
    """Opera o lag de maior autocorrelacao simples dentro de uma janela."""

    name: str = "c419_funcao_autocorrelacao_multilag_pacf"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    k_max: int = 10
    limiar_corr: float = 0.20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _lag_entrada: int | None = field(default=None, init=False, repr=False)
    _pico_corr_entrada: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._lag_entrada = None
        self._pico_corr_entrada = 0.0

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

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        if positions:
            if self._lag_entrada is not None and len(self._retornos) >= self.janela:
                arr = np.array(self._retornos)
                if len(arr) > self._lag_entrada + 5:
                    a, b = arr[:-self._lag_entrada], arr[self._lag_entrada:]
                    if a.std(ddof=0) > 1e-12 and b.std(ddof=0) > 1e-12:
                        corr_agora = abs(float(np.corrcoef(a, b)[0, 1]))
                        if corr_agora < 0.5 * self._pico_corr_entrada:
                            return [Exit(reason=f"{self.name}_correlacao_esfriou")]
            return []

        if len(self._retornos) < self.janela:
            return []
        resultado = _melhor_lag(np.array(self._retornos), self.k_max)
        if resultado is None:
            return []
        lag, corr = resultado
        if abs(corr) < self.limiar_corr or not self._retornos:
            return []

        ultimo = self._retornos[-1]
        if ultimo == 0:
            return []
        segue = corr > 0
        vai_subir = (ultimo > 0) == segue
        self._lag_entrada = lag
        self._pico_corr_entrada = abs(corr)
        tick = self.tick_size
        if vai_subir:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
