"""Catálogo estatística/sinal, item 76: TransformadaDeFourierCicloDominante.

`numpy.fft.fft` rolling dos retornos do close: extrai a frequência
dominante (excluindo a componente DC) e projeta a fase um passo à frente
para cronometrar o próximo fundo/topo esperado desse ciclo.
"""
from __future__ import annotations

import math
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
class TransformadaDeFourierCicloDominante(IntradayStrategy):
    """FFT rolling de `janela` retornos; identifica a frequência de maior
    magnitude (excluindo DC) e projeta o retorno do PRÓXIMO passo pela
    fase reconstruída dessa componente; entra na direção da projeção
    quando ela excede um limiar relativo à amplitude."""

    name: str = "transformada_de_fourier_ciclo_dominante"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 32
    fracao_amplitude_minima: float = 0.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=33), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._closes) == self._closes.maxlen:
            closes = np.array(self._closes)
            retornos = np.diff(closes) / closes[:-1]
            n = len(retornos)
            espectro = np.fft.fft(retornos)
            magnitudes = np.abs(espectro)
            # ignora a componente DC (indice 0) e a metade espelhada
            metade = n // 2
            k_dominante = int(np.argmax(magnitudes[1:metade])) + 1
            amplitude = magnitudes[k_dominante]
            fase = float(np.angle(espectro[k_dominante]))

            # projeta o proximo retorno avaliando a componente dominante
            # em n=janela: 2*pi*k*n/n = 2*pi*k, multiplo de 2*pi, entao o
            # termo se reduz a cos(fase).
            retorno_projetado = (2.0 * amplitude / n) * math.cos(fase)
            amplitude_media = magnitudes[1:metade].mean()

            if amplitude > 0 and abs(retorno_projetado) > self.fracao_amplitude_minima * (2.0 * amplitude_media / n):
                side = "long" if retorno_projetado > 0 else "short"
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
