"""Item 63 do catalogo: `numpy.fft.fft` numa janela movel de retornos para
achar a frequencia de maior potencia espectral, e a FASE do ciclo dominante
(angulo do componente complexo).

Entra na fase de subida do ciclo dominante (fase em (-pi/2, pi/2)); vendido
na fase de descida. Sai em horizonte fixo (o proprio periodo do ciclo).
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
class EspectralFourierCicloDominante(IntradayStrategy):
    """FFT de janela movel dos retornos -- fase do ciclo dominante."""

    name: str = "c462_espectral_fourier_ciclo_dominante"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 64
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=64), init=False, repr=False)
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
            pos = positions[0]
            periodo = self._periodo_dominante() or self.janela
            if pos.bars_held >= max(2, periodo // 2):
                return [Exit(reason="fim_do_ciclo_dominante")]
            return []

        if len(self._retornos) < self.janela:
            return []
        fase, periodo = self._ciclo_dominante()
        if fase is None:
            return []
        if -np.pi / 2 <= fase <= np.pi / 2:
            return [self._ordem("long", bar.close, f"fase_subida_periodo{periodo}")]
        return [self._ordem("short", bar.close, f"fase_descida_periodo{periodo}")]

    def _ciclo_dominante(self) -> tuple[float | None, int | None]:
        arr = np.asarray(self._retornos, dtype=float)
        n = len(arr)
        espectro = np.fft.fft(arr - arr.mean())
        potencia = np.abs(espectro[1:n // 2]) ** 2
        if potencia.size == 0:
            return None, None
        idx = int(np.argmax(potencia)) + 1
        fase = float(np.angle(espectro[idx]))
        periodo = max(2, int(round(n / idx)))
        return fase, periodo

    def _periodo_dominante(self) -> int | None:
        if len(self._retornos) < self.janela:
            return None
        _, periodo = self._ciclo_dominante()
        return periodo

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
