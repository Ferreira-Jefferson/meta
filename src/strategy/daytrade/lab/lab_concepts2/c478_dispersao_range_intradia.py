"""Item 79 do catalogo: z-score do RANGE (high-low) da barra contra a
distribuicao historica de ranges numa janela movel.

Entra em reversao quando uma barra de range EXTREMO e' seguida de
fechamento perto de um extremo do proprio range (fecha perto da maxima
depois de um range grande => fade pra baixo; perto da minima => fade pra
cima). Sai no primeiro fechamento que reverte a barra extrema.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class DispersaoRangeIntradia(IntradayStrategy):
    """Z-score do range da barra -- reversao apos range extremo com fechamento no extremo."""

    name: str = "c478_dispersao_range_intradia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    z_entrada: float = 2.0
    posicao_no_range_extrema: float = 0.8
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _ranges: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _close_extremo_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ranges = deque(maxlen=self.janela)
        self._close_extremo_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        range_barra = bar.high - bar.low
        if positions:
            pos = positions[0]
            if pos.side == "long" and bar.close < (self._close_extremo_anterior or bar.close):
                return [Exit(reason="reverteu_a_barra_extrema")]
            if pos.side == "short" and bar.close > (self._close_extremo_anterior or bar.close):
                return [Exit(reason="reverteu_a_barra_extrema")]
            self._ranges.append(range_barra)
            return []

        if len(self._ranges) < self.janela:
            self._ranges.append(range_barra)
            return []
        arr = np.asarray(self._ranges, dtype=float)
        desvio = float(arr.std())
        z = (range_barra - float(arr.mean())) / desvio if desvio > 0 else 0.0
        self._ranges.append(range_barra)

        if z < self.z_entrada or range_barra <= 0:
            return []
        posicao_no_range = (bar.close - bar.low) / range_barra
        self._close_extremo_anterior = bar.close
        if posicao_no_range >= self.posicao_no_range_extrema:
            return [self._ordem("short", bar.close, f"range_extremo_fechou_topo_z{z:.2f}")]
        if posicao_no_range <= (1 - self.posicao_no_range_extrema):
            return [self._ordem("long", bar.close, f"range_extremo_fechou_fundo_z{z:.2f}")]
        return []

    def _ordem(self, side: str, preco_ref: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(preco_ref, self.tick_size)
        stop = no_tick(limite - sinal * self.stop_ticks * self.tick_size, self.tick_size)
        alvo = no_tick(limite + sinal * self.alvo_ticks * self.tick_size, self.tick_size)
        return EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=reason,
        )
