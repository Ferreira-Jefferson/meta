"""CurtoseLocalPicoAntecipaReversao -- pico de curtose antecipa reversao.

Curtose em excesso (formula manual: `mean(desvio^4)/std^4 - 3`) movel
dos retornos, comparada a sua propria linha de base historica (media
rolante). Um PICO de curtose acima do limiar (cauda mais pesada que o
normal recente -- geralmente causado por 1-2 retornos extremos isolados)
antecipa reversao: entra contra a ultima barra, assumindo que a
distribuicao volta a normalizar. Sai quando a curtose retorna ao nivel
basal, ou pelo stop/alvo.
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


def _kurtose_excesso(arr: np.ndarray) -> float | None:
    std = arr.std(ddof=0)
    if std <= 1e-12:
        return None
    desvio = arr - arr.mean()
    return float(np.mean(desvio ** 4) / std ** 4 - 3.0)


@dataclass
class CurtoseLocalPicoAntecipaReversao(IntradayStrategy):
    """Reversao quando a curtose local pica acima da linha de base historica."""

    name: str = "c438_curtose_local_pico_antecipa_reversao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    janela_historico: int = 30
    limiar_desvios: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _historico_kurt: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._historico_kurt = deque(maxlen=self.janela_historico)

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
        kurt = None
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)
            if len(self._retornos) == self.janela:
                kurt = _kurtose_excesso(np.array(self._retornos))
        if kurt is not None:
            self._historico_kurt.append(kurt)

        baseline = None
        if len(self._historico_kurt) >= 10:
            baseline = float(np.mean(self._historico_kurt))

        if positions:
            if kurt is not None and baseline is not None and kurt <= baseline:
                return [Exit(reason=f"{self.name}_curtose_normalizou")]
            return []

        if kurt is None or baseline is None or len(self._historico_kurt) < 10 or not self._retornos:
            return []
        std_hist = float(np.std(self._historico_kurt, ddof=0))
        if std_hist <= 1e-9 or kurt < baseline + self.limiar_desvios * std_hist:
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
