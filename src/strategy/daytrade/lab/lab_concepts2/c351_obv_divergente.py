"""Catálogo volume/microestrutura, item 52: OnBalanceVolumeDivergente.

Constrói um proxy de On-Balance-Volume (soma sinalizada de `bar.volume`
conforme o close sobe/desce) e compara a inclinação dele (via
`numpy.polyfit`) com a inclinação do preço na mesma janela -- divergência
de sinais = fade.
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
class OnBalanceVolumeDivergente(IntradayStrategy):
    """OBV-proxy divergente da inclinação do preço na mesma janela --
    fade na direção contrária ao preço."""

    name: str = "obv_divergente"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _obv: float = field(default=0.0, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _obv_hist: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _close_hist: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._obv = 0.0
        self._close_anterior = None
        self._obv_hist = deque(maxlen=self.janela)
        self._close_hist = deque(maxlen=self.janela)

    def _ordem(self, lado: str, nivel: float) -> list[IntradayAction]:
        if lado == "long":
            limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
        else:
            limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
        return [EnterLimit(
            side=lado, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._close_anterior is not None:
            if bar.close > self._close_anterior:
                self._obv += bar.volume
            elif bar.close < self._close_anterior:
                self._obv -= bar.volume

        self._obv_hist.append(self._obv)
        self._close_hist.append(bar.close)

        if not positions and len(self._obv_hist) == self._obv_hist.maxlen:
            x = np.arange(len(self._obv_hist), dtype=float)
            slope_obv = float(np.polyfit(x, np.array(self._obv_hist, dtype=float), 1)[0])
            slope_preco = float(np.polyfit(x, np.array(self._close_hist, dtype=float), 1)[0])
            if slope_preco > 0 and slope_obv < 0:
                acao = self._ordem("short", bar.close)
            elif slope_preco < 0 and slope_obv > 0:
                acao = self._ordem("long", bar.close)

        self._close_anterior = bar.close
        return acao
