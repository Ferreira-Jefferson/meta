"""EstimadorParkinsonVsCloseClose -- razao entre vol de Parkinson (H/L) e close-a-close.

Parkinson e' um estimador de variancia baseado no range HIGH/LOW da
barra (formula fechada `(1/(4 ln 2)) * ln(high/low)^2`, sem lib) --
captura movimento INTRABARRA que o close-a-close ignora. Uma razao muito
fora de 1 entre as duas medidas de variancia (na mesma janela) indica
ruido de microestrutura dominando (range grande com fechamento estavel,
ou o oposto) -- opera reversao (contra a ultima barra). Sai quando a
razao normaliza de volta perto de 1, ou pelo stop/alvo.
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

_FATOR_PARKINSON = 1.0 / (4.0 * np.log(2.0))


@dataclass
class EstimadorParkinsonVsCloseClose(IntradayStrategy):
    """Reversao quando a razao vol Parkinson / vol close-close foge de 1."""

    name: str = "c433_estimador_parkinson_vs_close_close"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    limiar_razao: float = 1.6
    limiar_saida: float = 1.2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _park_contrib: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._park_contrib = deque(maxlen=self.janela)

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

    def _razao(self) -> float | None:
        if len(self._retornos) < self.janela or len(self._park_contrib) < self.janela:
            return None
        cc_var = float(np.var(self._retornos, ddof=0))
        park_var = float(np.mean(self._park_contrib))
        if cc_var <= 1e-14:
            return None
        return park_var / cc_var

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)
        if bar.low > 0 and bar.high > 0:
            self._park_contrib.append(_FATOR_PARKINSON * (np.log(bar.high / bar.low)) ** 2)

        razao = self._razao()

        if positions:
            if razao is not None and 1.0 / self.limiar_saida <= razao <= self.limiar_saida:
                return [Exit(reason=f"{self.name}_normalizou")]
            return []

        if razao is None or not self._retornos:
            return []
        extremo = razao >= self.limiar_razao or razao <= (1.0 / self.limiar_razao)
        if not extremo:
            return []
        ultimo = self._retornos[-1]
        if ultimo == 0:
            return []
        tick = self.tick_size
        if ultimo > 0:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("long", bar.close - self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
