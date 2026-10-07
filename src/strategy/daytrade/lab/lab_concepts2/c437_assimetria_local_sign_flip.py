"""AssimetriaLocalSignFlip -- entra na direcao oposta quando a assimetria troca de sinal.

Assimetria (skewness, formula manual: `mean(desvio^3)/std^3`) movel dos
retornos. Quando o SINAL da assimetria muda (positiva->negativa ou
vice-versa), entra na direcao OPOSTA a' NOVA assimetria -- assimetria
positiva nova indica cauda direita mais pesada (poucos retornos grandes
de alta puxando a distribuicao), o que a estrategia le' como sinal de
exaustao da alta e opera vendida; o simetrico para assimetria negativa
nova. Sai quando a assimetria flipa de sinal outra vez, ou pelo
stop/alvo.
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


def _skew(arr: np.ndarray) -> float | None:
    std = arr.std(ddof=0)
    if std <= 1e-12:
        return None
    desvio = arr - arr.mean()
    return float(np.mean(desvio ** 3) / std ** 3)


@dataclass
class AssimetriaLocalSignFlip(IntradayStrategy):
    """Entra na direcao oposta a nova assimetria quando ela troca de sinal."""

    name: str = "c437_assimetria_local_sign_flip"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    limiar_skew: float = 0.15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _sinal_anterior: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._sinal_anterior = 0

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
        skew = None
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)
            if len(self._retornos) == self.janela:
                skew = _skew(np.array(self._retornos))

        sinal_atual = self._sinal_anterior
        if skew is not None:
            if skew > self.limiar_skew:
                sinal_atual = 1
            elif skew < -self.limiar_skew:
                sinal_atual = -1

        cruzou = sinal_atual != 0 and sinal_atual != self._sinal_anterior and self._sinal_anterior != 0

        if positions:
            self._sinal_anterior = sinal_atual
            if cruzou:
                return [Exit(reason=f"{self.name}_assimetria_flipou")]
            return []

        primeira_deteccao = sinal_atual != 0 and self._sinal_anterior == 0
        mudou = sinal_atual != 0 and sinal_atual != self._sinal_anterior
        self._sinal_anterior = sinal_atual
        if not (primeira_deteccao or mudou):
            return []

        tick = self.tick_size
        if sinal_atual == 1:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("long", bar.close - self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
