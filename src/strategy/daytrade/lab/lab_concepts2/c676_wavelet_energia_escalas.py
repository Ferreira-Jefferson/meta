"""Catálogo estatística/sinal, item 77: WaveletEnergiaEscalas.

Decomposição simplificada tipo wavelet via diferença de médias móveis em
escalas diádicas (MA2-MA4, MA4-MA8, MA8-MA16); energia (variância) por
escala numa janela rolante; entra na direção do detalhe de escala mais
FINA quando a energia de alta frequência dispara em relação à de baixa.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def _media(valores) -> float:
    return sum(valores) / len(valores)


@dataclass
class WaveletEnergiaEscalas(IntradayStrategy):
    """Detalhes `d1=MA2-MA4`, `d2=MA4-MA8`, `d3=MA8-MA16` do close;
    energia = variância rolante de cada detalhe; entra na direção de
    `d1` quando `var(d1)/var(d3) > k_energia`."""

    name: str = "wavelet_energia_escalas"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_energia: int = 20
    k_energia: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=16), init=False, repr=False)
    _d1_hist: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _d3_hist: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=16)
        if self._d1_hist.maxlen != self.janela_energia:
            self._d1_hist = deque(maxlen=self.janela_energia)
            self._d3_hist = deque(maxlen=self.janela_energia)

    @staticmethod
    def _variancia(valores) -> float:
        m = _media(valores)
        return sum((v - m) ** 2 for v in valores) / len(valores)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes.append(bar.close)

        if len(self._closes) == self._closes.maxlen:
            c = list(self._closes)
            ma2 = _media(c[-2:])
            ma4 = _media(c[-4:])
            ma8 = _media(c[-8:])
            ma16 = _media(c[-16:])
            d1 = ma2 - ma4
            d3 = ma8 - ma16
            self._d1_hist.append(d1)
            self._d3_hist.append(d3)

            if (not positions and len(self._d1_hist) == self._d1_hist.maxlen
                    and len(self._d3_hist) == self._d3_hist.maxlen):
                var_d1 = self._variancia(self._d1_hist)
                var_d3 = self._variancia(self._d3_hist)
                if var_d3 > 0 and var_d1 / var_d3 > self.k_energia and d1 != 0:
                    side = "long" if d1 > 0 else "short"
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
        return acao
