"""Catálogo física, item 25: EmpuxoDeArquimedes.

Analogia com empuxo/flutuação: o preço "flutua" no nível onde o volume
acumulado abaixo se equilibra com o volume acumulado acima (mediana
ponderada por volume da janela). Fade de movimentos que se afastam desse
ponto de equilíbrio, na direção de volta a ele.
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


def _mediana_ponderada(precos: np.ndarray, volumes: np.ndarray) -> float:
    ordem = np.argsort(precos)
    precos_o, vol_o = precos[ordem], volumes[ordem]
    acumulado = np.cumsum(vol_o)
    alvo = acumulado[-1] / 2.0
    idx = int(np.searchsorted(acumulado, alvo))
    idx = min(idx, len(precos_o) - 1)
    return float(precos_o[idx])


@dataclass
class EmpuxoDeArquimedes(IntradayStrategy):
    """Ponto de equilíbrio = mediana ponderada por volume da janela; fade
    de movimentos que se afastam desse ponto, na direção de volta a ele."""

    name: str = "empuxo_de_arquimedes"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    distancia_minima_ticks: float = 6.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)
        self._vols = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if not positions and len(self._closes) == self._closes.maxlen:
            precos = np.array(self._closes)
            volumes = np.maximum(np.array(self._vols), 1e-6)
            equilibrio = _mediana_ponderada(precos, volumes)
            distancia = bar.close - equilibrio
            distancia_minima = self.distancia_minima_ticks * self.tick_size
            if distancia > distancia_minima:
                limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(equilibrio, self.tick_size)
                if limite - alvo >= 4 * self.tick_size:
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
            elif distancia < -distancia_minima:
                limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(equilibrio, self.tick_size)
                if alvo - limite >= 4 * self.tick_size:
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._closes.append(bar.close)
        self._vols.append(bar.volume)
        return acao
