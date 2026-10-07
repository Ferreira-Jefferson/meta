"""Catálogo autômatos/ML/jogos, item 65: PredadorPresaLotkaVolterra.

Modela momentum de preço (predador) e volume (presa) como osciladores
acoplados: em `initialize`, mede por correlação cruzada o LAG histórico
em que o volume tende a surgir após um pico de momentum (exaustão);
ao vivo, cronometra a entrada nesse mesmo lag após detectar exaustão e
o surgimento de volume.
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

LAG_MAX = 10
JANELA_MOMENTUM = 5


@dataclass
class PredadorPresaLotkaVolterra(IntradayStrategy):
    """`initialize` mede o lag de máxima correlação cruzada entre
    |momentum| e volume; ao vivo, um pico de |momentum| seguido de
    exaustão (queda) arma uma janela de `lag` barras esperando o
    surgimento de volume -- ao surgir, entra na REVERSÃO do momentum
    exaurido."""

    name: str = "predador_presa_lotka_volterra"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol_ma: int = 20
    k_volume: float = 1.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _lag: int = field(default=3, init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=JANELA_MOMENTUM + 2), init=False, repr=False)
    _momentums: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _volumes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _direcao_exaustao: int = field(default=0, init=False, repr=False)
    _contador_espera: int = field(default=0, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        closes = bars["close"].to_numpy(dtype=float)
        vol_col = "real_volume" if "real_volume" in bars.columns else (
            "tick_volume" if "tick_volume" in bars.columns else None
        )
        volumes = bars[vol_col].to_numpy(dtype=float) if vol_col else np.ones_like(closes)

        if len(closes) <= JANELA_MOMENTUM + LAG_MAX + 5:
            self._lag = 3
            return

        momentum = np.abs(closes[JANELA_MOMENTUM:] - closes[:-JANELA_MOMENTUM])
        vol_alinhado = volumes[JANELA_MOMENTUM:]
        n = min(len(momentum), len(vol_alinhado))
        momentum, vol_alinhado = momentum[:n], vol_alinhado[:n]

        momentum = momentum - momentum.mean()
        vol_c = vol_alinhado - vol_alinhado.mean()

        melhor_lag, melhor_corr = 1, -np.inf
        for lag in range(1, LAG_MAX + 1):
            if n - lag <= 10:
                continue
            corr = float(np.corrcoef(momentum[:-lag], vol_c[lag:])[0, 1])
            if not np.isnan(corr) and corr > melhor_corr:
                melhor_corr, melhor_lag = corr, lag
        self._lag = melhor_lag

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=JANELA_MOMENTUM + 2)
        self._momentums = deque(maxlen=3)
        self._volumes = deque(maxlen=self.janela_vol_ma)
        self._direcao_exaustao = 0
        self._contador_espera = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        # janela de espera por volume apos exaustao detectada
        if not positions and self._contador_espera > 0 and len(self._volumes) == self._volumes.maxlen:
            vol_ma = sum(self._volumes) / len(self._volumes)
            if bar.volume > self.k_volume * vol_ma:
                side = "short" if self._direcao_exaustao > 0 else "long"
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
                self._contador_espera = 0
            else:
                self._contador_espera -= 1

        self._closes.append(bar.close)
        if len(self._closes) == self._closes.maxlen:
            closes = list(self._closes)
            momentum = closes[-1] - closes[0]
            self._momentums.append(momentum)
            if len(self._momentums) == self._momentums.maxlen and self._contador_espera == 0:
                m0, m1, m2 = self._momentums
                # exaustao: |momentum| cresceu e depois caiu (pico no meio)
                if abs(m1) > abs(m0) and abs(m1) > abs(m2) and abs(m1) > 0:
                    self._direcao_exaustao = 1 if m1 > 0 else -1
                    self._contador_espera = self._lag

        self._volumes.append(bar.volume)
        return acao
