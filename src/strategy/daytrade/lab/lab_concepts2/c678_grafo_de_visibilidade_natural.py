"""Catálogo estatística/sinal, item 79: GrafoDeVisibilidadeNatural.

Grafo de visibilidade natural sobre os últimos N closes: a barra `i` "vê"
a barra `j` (i<j) se nenhuma barra entre elas bloqueia a linha reta entre
seus valores. O grau de conexão da barra mais recente (quantas barras
anteriores ela enxerga) mede importância estrutural; entra quando o grau
dispara na direção do rompimento do range da janela.
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


def grau_visibilidade_ultima_barra(valores: np.ndarray) -> int:
    """Quantas barras anteriores a ÚLTIMA barra de `valores` enxerga, pela
    condição clássica de visibilidade natural (Lacasa et al.): `i` vê `j`
    (`i<j`) se, para toda barra `k` entre elas,
    `valores[k] < valores[j] + (valores[i]-valores[j])*(j-k)/(j-i)`."""
    n = len(valores)
    j = n - 1
    grau = 0
    for i in range(j):
        bloqueado = False
        for k in range(i + 1, j):
            limite = valores[j] + (valores[i] - valores[j]) * (j - k) / (j - i)
            if valores[k] >= limite:
                bloqueado = True
                break
        if not bloqueado:
            grau += 1
    return grau


@dataclass
class GrafoDeVisibilidadeNatural(IntradayStrategy):
    """Grau de visibilidade da última barra dentro de uma janela de N
    closes; entra na direção do rompimento do range da janela quando o
    grau supera a própria mediana histórica por um fator."""

    name: str = "grafo_de_visibilidade_natural"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 15
    janela_grau_hist: int = 30
    fator_grau: float = 1.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)
    _graus_hist: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._closes.maxlen != self.janela:
            self._closes = deque(maxlen=self.janela)
            self._highs = deque(maxlen=self.janela)
            self._lows = deque(maxlen=self.janela)
        if self._graus_hist.maxlen != self.janela_grau_hist:
            self._graus_hist = deque(maxlen=self.janela_grau_hist)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes.append(bar.close)
        self._highs.append(bar.high)
        self._lows.append(bar.low)

        if len(self._closes) == self._closes.maxlen:
            grau = grau_visibilidade_ultima_barra(np.array(self._closes))

            if not positions and len(self._graus_hist) == self._graus_hist.maxlen:
                mediana = sorted(self._graus_hist)[len(self._graus_hist) // 2]
                if mediana > 0 and grau > mediana * self.fator_grau:
                    range_high = max(list(self._highs)[:-1])
                    range_low = min(list(self._lows)[:-1])
                    side = None
                    if bar.close > range_high:
                        side = "long"
                    elif bar.close < range_low:
                        side = "short"
                    if side is not None:
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

            self._graus_hist.append(grau)
        return acao
