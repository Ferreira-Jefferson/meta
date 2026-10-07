"""Catálogo autômatos/ML/jogos, item 57: PerceptronUmaCamada.

Perceptron linear (numpy puro) treinado por mínimos quadrados
(`numpy.linalg.lstsq`) dentro de `initialize` sobre retornos defasados e
z-score de volume; entra na direção da saída quando |saída| excede uma
margem.
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

N_LAGS = 5
JANELA_VOL_Z = 20


@dataclass
class PerceptronUmaCamada(IntradayStrategy):
    """Perceptron linear em [retornos defasados, z-score de volume],
    pesos ajustados por mínimos quadrados sobre o histórico recebido em
    `initialize`; entra quando a saída ao vivo excede a margem."""

    name: str = "perceptron_uma_camada"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    margem: float = 0.0003
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _pesos: np.ndarray = field(default=None, init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=N_LAGS + 1), init=False, repr=False)
    _volumes: deque = field(default_factory=lambda: deque(maxlen=JANELA_VOL_Z), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        closes = bars["close"].to_numpy(dtype=float)
        vol_col = "real_volume" if "real_volume" in bars.columns else (
            "tick_volume" if "tick_volume" in bars.columns else None
        )
        volumes = bars[vol_col].to_numpy(dtype=float) if vol_col else np.ones_like(closes)

        retornos = np.diff(closes) / closes[:-1]
        n = len(retornos)
        self._pesos = np.zeros(N_LAGS + 1)
        if n <= N_LAGS + JANELA_VOL_Z + 10:
            return

        vol_serie = pd.Series(volumes[1:])
        vol_mm = vol_serie.rolling(JANELA_VOL_Z).mean()
        vol_dp = vol_serie.rolling(JANELA_VOL_Z).std()
        vol_z = ((vol_serie - vol_mm) / vol_dp.replace(0.0, np.nan)).to_numpy()

        linhas, alvo_y = [], []
        for i in range(N_LAGS + JANELA_VOL_Z, n - 1):
            lags = retornos[i - N_LAGS:i][::-1]
            z = vol_z[i]
            if np.any(np.isnan(lags)) or np.isnan(z):
                continue
            linhas.append(np.concatenate([lags, [z]]))
            alvo_y.append(retornos[i + 1])

        if len(linhas) < 10:
            return
        pesos, *_ = np.linalg.lstsq(np.array(linhas), np.array(alvo_y), rcond=None)
        self._pesos = pesos

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=N_LAGS + 1)
        self._volumes = deque(maxlen=JANELA_VOL_Z)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._volumes.append(bar.volume)

        if (not positions and self._pesos is not None
                and len(self._closes) == self._closes.maxlen
                and len(self._volumes) == self._volumes.maxlen):
            closes = np.array(self._closes)
            retornos_lag = (np.diff(closes) / closes[:-1])[::-1]
            vol_arr = np.array(self._volumes)
            vol_mm, vol_dp = vol_arr.mean(), vol_arr.std()
            z = (bar.volume - vol_mm) / vol_dp if vol_dp > 0 else 0.0
            features = np.concatenate([retornos_lag, [z]])
            saida = float(features @ self._pesos)

            if abs(saida) > self.margem:
                side = "long" if saida > 0 else "short"
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

        self._closes.append(bar.close)
        return acao
