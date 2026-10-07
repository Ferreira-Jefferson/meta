"""Catálogo estatística/sinal, item 78: MatrizAleatoriaAutovalor.

Monta uma pequena matriz de correlação (numpy) entre uma janela de
retornos e suas versões defasadas (auto-lag); acompanha o maior
autovalor (`numpy.linalg.eigvalsh`) contra um percentil histórico do
próprio autovalor (não Marchenko-Pastur formal); entra na direção da
tendência quando o autovalor excede o limite.
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

M_LAGS = 5
JANELA_RETORNOS = 40


@dataclass
class MatrizAleatoriaAutovalor(IntradayStrategy):
    """Matriz de correlação `M_LAGS x M_LAGS` entre colunas defasadas dos
    últimos `JANELA_RETORNOS` retornos; entra na direção da tendência
    (média dos retornos) quando o maior autovalor excede o percentil
    histórico dele mesmo."""

    name: str = "matriz_aleatoria_autovalor"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_percentil: int = 60
    percentil_limite: float = 0.85
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=JANELA_RETORNOS + 1), init=False, repr=False)
    _autovalores_hist: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._autovalores_hist.maxlen != self.janela_percentil:
            self._autovalores_hist = deque(self._autovalores_hist, maxlen=self.janela_percentil)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes.append(bar.close)

        if len(self._closes) == self._closes.maxlen:
            closes = np.array(self._closes)
            retornos = np.diff(closes) / closes[:-1]
            colunas = [retornos[M_LAGS - 1 - k: len(retornos) - k] for k in range(M_LAGS)]
            X = np.stack(colunas, axis=1)
            corr = np.corrcoef(X, rowvar=False)
            corr = np.nan_to_num(corr, nan=0.0)
            autovalor_max = float(np.linalg.eigvalsh(corr)[-1])

            if not positions and len(self._autovalores_hist) == self._autovalores_hist.maxlen:
                limite_percentil = float(np.quantile(np.array(self._autovalores_hist), self.percentil_limite))
                if autovalor_max > limite_percentil:
                    tendencia = retornos.mean()
                    if tendencia != 0:
                        side = "long" if tendencia > 0 else "short"
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

            self._autovalores_hist.append(autovalor_max)
        return acao
