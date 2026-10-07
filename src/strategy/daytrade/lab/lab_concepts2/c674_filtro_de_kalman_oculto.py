"""Catálogo estatística/sinal, item 75: FiltroDeKalmanOculto.

Filtro de Kalman 1D à mão (modelo de velocidade constante: estado
[nível, velocidade]) sobre o close; entra quando o close bruto cruza a
estimativa filtrada com resíduo (inovação) excedendo seu próprio
desvio-padrão rolling.
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


@dataclass
class FiltroDeKalmanOculto(IntradayStrategy):
    """Kalman 1D manual (velocidade constante) sobre o close; entra na
    direção do cruzamento quando a inovação (close bruto - estimativa)
    excede seu próprio desvio-padrão rolling."""

    name: str = "filtro_de_kalman_oculto"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    variancia_processo: float = 0.01
    variancia_medida: float = 1.0
    janela_residuo: int = 20
    limiar_desvios: float = 1.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _estado: np.ndarray = field(default=None, init=False, repr=False)
    _covariancia: np.ndarray = field(default=None, init=False, repr=False)
    _residuos: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _inicializado: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._estado = None
        self._covariancia = None
        self._residuos = deque(maxlen=self.janela_residuo)
        self._inicializado = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not self._inicializado:
            self._estado = np.array([bar.close, 0.0])
            self._covariancia = np.eye(2) * 10.0
            self._inicializado = True
            return acao

        # ---- predicao (modelo de velocidade constante, dt=1 barra) ----
        F = np.array([[1.0, 1.0], [0.0, 1.0]])
        Q = np.array([[self.variancia_processo, 0.0], [0.0, self.variancia_processo]])
        estado_pred = F @ self._estado
        cov_pred = F @ self._covariancia @ F.T + Q

        # ---- atualizacao com a observacao (close) ----
        H = np.array([[1.0, 0.0]])
        R = self.variancia_medida
        inovacao = bar.close - float(estado_pred[0])
        S = float((H @ cov_pred @ H.T).item()) + R
        K = (cov_pred @ H.T).flatten() / S
        estado_novo = estado_pred + K * inovacao
        cov_novo = (np.eye(2) - np.outer(K, H.flatten())) @ cov_pred

        if not positions and len(self._residuos) == self._residuos.maxlen:
            residuos = list(self._residuos)
            media = sum(residuos) / len(residuos)
            dp = (sum((r - media) ** 2 for r in residuos) / len(residuos)) ** 0.5
            if dp > 0 and abs(inovacao) > self.limiar_desvios * dp:
                side = "long" if inovacao > 0 else "short"
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

        self._residuos.append(inovacao)
        self._estado = estado_novo
        self._covariancia = cov_novo
        return acao
