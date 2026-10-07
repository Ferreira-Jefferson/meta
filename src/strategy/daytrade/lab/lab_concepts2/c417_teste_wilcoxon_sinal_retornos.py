"""TesteWilcoxonSinalRetornos -- substituto informal do teste de postos de Wilcoxon.

SUBSTITUICAO DECLARADA (catalogo pede para pular o teste formal, que
exige a distribuicao de Wilcoxon): em vez da estatistica de postos
sinalizados, usa a MEDIANA dos retornos da janela comparada a zero,
escalada pelo erro-padrao aproximado (`std/sqrt(n)`) -- um "t-like"
score robusto sobre a mediana em vez da media. |score| grande indica
retorno tipico consistentemente diferente de zero -- entra na direcao do
sinal da mediana (momentum). Sai pelo stop/alvo fixos.
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
class TesteWilcoxonSinalRetornos(IntradayStrategy):
    """Mediana dos retornos vs zero, escalada pelo erro-padrao -- substitui Wilcoxon."""

    name: str = "c417_teste_wilcoxon_sinal_retornos"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    limiar_score: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)

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
            return []

        if len(self._retornos) < self.janela:
            return []
        arr = np.array(self._retornos)
        mediana = float(np.median(arr))
        std = arr.std(ddof=0)
        if std <= 1e-12:
            return []
        score = mediana / (std / np.sqrt(len(arr)))
        if abs(score) < self.limiar_score:
            return []

        tick = self.tick_size
        if score > 0:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
