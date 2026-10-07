"""AnaliseFlutuacaoDestendenciada (DFA) -- expoente de Hurst por flutuacao destendenciada.

DFA classico implementado a mao: integra a serie de retornos demeaned
(perfil acumulado), divide em janelas nao sobrepostas de varias escalas
`s`, remove a tendencia local por regressao linear (`numpy.polyfit`) em
cada janela, mede a flutuacao RMS residual `F(s)` por escala, e ajusta
`log F(s)` contra `log s` -- a inclinacao e' o expoente `alpha`.
`alpha<0,5` indica regime de REVERSAO (entra contra a ultima barra);
`alpha>0,5` indica regime de TENDENCIA (entra a favor da ultima barra).
Sai pelo stop/alvo fixos.
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


def _dfa_alpha(retornos: np.ndarray, escalas=_ESCALAS_PADRAO) -> float | None:
    y = np.cumsum(retornos - retornos.mean())
    n = len(y)
    log_s, log_f = [], []
    for s in escalas:
        if s < 4 or s > n // 2:
            continue
        n_janelas = n // s
        if n_janelas < 2:
            continue
        f2 = []
        for w in range(n_janelas):
            seg = y[w * s:(w + 1) * s]
            x = np.arange(s)
            coef = np.polyfit(x, seg, 1)
            resid = seg - np.polyval(coef, x)
            f2.append(np.mean(resid ** 2))
        f_s = np.sqrt(np.mean(f2))
        if f_s > 0:
            log_s.append(np.log(s))
            log_f.append(np.log(f_s))
    if len(log_s) < 3:
        return None
    slope, _intercepto = np.polyfit(log_s, log_f, 1)
    return float(slope)


@dataclass
class AnaliseFlutuacaoDestendenciadaDFA(IntradayStrategy):
    """Regime de tendencia/reversao pelo expoente DFA dos retornos."""

    name: str = "c422_analise_flutuacao_destendenciada_dfa"
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

        alpha = _dfa_alpha(np.array(self._retornos))
        if alpha is None:
            return []
        ultimo = self._retornos[-1]
        if ultimo == 0:
            return []
        tick = self.tick_size
        if alpha < 0.5 - self.margem_regime:
            vai_subir = ultimo < 0
        elif alpha > 0.5 + self.margem_regime:
            vai_subir = ultimo > 0
        else:
            return []
        if vai_subir:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
