"""ExpoenteHurstRS -- expoente de Hurst pelo range reescalado (R/S) classico.

R/S classico implementado a mao: para varias escalas `n`, divide a
serie de retornos em blocos nao sobrepostos de comprimento `n`, calcula
o range reescalado `R/S` de cada bloco (`R` = amplitude da soma
acumulada demeaned, `S` = desvio-padrao do bloco) e tira a media entre
blocos; ajusta `log(R/S)` contra `log(n)` -- a inclinacao e' o expoente
de Hurst `H`. `H<0,5` indica REVERSAO (entra contra a ultima barra);
`H>0,5` indica TENDENCIA (entra a favor). Sai pelo stop/alvo fixos.
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

_ESCALAS_PADRAO = (10, 20, 25, 50)


def _hurst_rs(retornos: np.ndarray, escalas=_ESCALAS_PADRAO) -> float | None:
    n_total = len(retornos)
    log_n, log_rs = [], []
    for n in escalas:
        if n < 4 or n > n_total // 2:
            continue
        n_blocos = n_total // n
        if n_blocos < 2:
            continue
        rs_vals = []
        for c in range(n_blocos):
            seg = retornos[c * n:(c + 1) * n]
            y = np.cumsum(seg - seg.mean())
            r = y.max() - y.min()
            s = seg.std(ddof=0)
            if s > 1e-12:
                rs_vals.append(r / s)
        if not rs_vals:
            continue
        log_n.append(np.log(n))
        log_rs.append(np.log(np.mean(rs_vals)))
    if len(log_n) < 3:
        return None
    slope, _intercepto = np.polyfit(log_n, log_rs, 1)
    return float(slope)


@dataclass
class ExpoenteHurstRS(IntradayStrategy):
    """Regime de tendencia/reversao pelo expoente de Hurst (R/S) dos retornos."""

    name: str = "c423_expoente_hurst_rs"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 100
    margem_regime: float = 0.05
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=100), init=False, repr=False)

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

        h = _hurst_rs(np.array(self._retornos))
        if h is None:
            return []
        ultimo = self._retornos[-1]
        if ultimo == 0:
            return []
        tick = self.tick_size
        if h < 0.5 - self.margem_regime:
            vai_subir = ultimo < 0
        elif h > 0.5 + self.margem_regime:
            vai_subir = ultimo > 0
        else:
            return []
        if vai_subir:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
