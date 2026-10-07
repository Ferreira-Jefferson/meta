"""Catálogo física, item 19: PenduloPeriodoCiclos.

Analogia com pêndulo periódico: mede o período de oscilação do preço ao
redor da EMA (barras entre cruzamentos de zero de close−EMA, média rolling
dos últimos períodos observados) como período T. Cronometra a partir do
último cruzamento e entra na projeção T/2 (o fundo/topo esperado do swing
seguinte), na direção contrária ao lado atual da EMA.
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


@dataclass
class PenduloPeriodoCiclos(IntradayStrategy):
    """Período T de oscilação close-EMA (média rolling de ciclos passados);
    entra cronometrado na projeção T/2 do cruzamento mais recente."""

    name: str = "pendulo_periodo_ciclos"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    periodo_ema: int = 9
    n_periodos_media: int = 6
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ema: float | None = field(default=None, init=False, repr=False)
    _sinal_anterior: int = field(default=0, init=False, repr=False)
    _fase: int = field(default=0, init=False, repr=False)
    _periodos: deque = field(default_factory=lambda: deque(maxlen=6), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ema = None
        self._sinal_anterior = 0
        self._fase = 0
        self._periodos = deque(maxlen=self.n_periodos_media)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        alpha = 2.0 / (self.periodo_ema + 1)
        self._ema = bar.close if self._ema is None else alpha * bar.close + (1 - alpha) * self._ema
        sinal = 1 if bar.close > self._ema else (-1 if bar.close < self._ema else self._sinal_anterior)

        if self._sinal_anterior != 0 and sinal != self._sinal_anterior:
            if self._fase > 0:
                self._periodos.append(self._fase * 2)
            self._fase = 0
        else:
            self._fase += 1
        self._sinal_anterior = sinal

        if not positions and len(self._periodos) >= 3:
            periodo_t = sum(self._periodos) / len(self._periodos)
            metade = round(periodo_t / 2)
            if metade >= 1 and self._fase == metade:
                if sinal > 0:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                else:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
        return acao
