"""Catálogo astronomia/tempo, item 69: RitmoCircadianoIntradia.

Divide o horário da barra em fases (abertura/almoço/fechamento) e aplica
limiares de momentum diferentes por fase -- mais apertados nos horários
de "pico" de alerta (abertura/fechamento), mais largos no "vale" do meio
do pregão (almoço).
"""
from __future__ import annotations

import datetime as dt
from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class RitmoCircadianoIntradia(IntradayStrategy):
    """Momentum de `janela` barras contra um limiar que varia por fase do
    pregão: apertado na abertura/fechamento (pico de alerta), largo no
    almoço (vale)."""

    name: str = "ritmo_circadiano_intradia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 10
    limiar_pico: float = 0.003
    limiar_vale: float = 0.008
    inicio_abertura: dt.time = dt.time(9, 0)
    fim_abertura: dt.time = dt.time(9, 45)
    inicio_almoco: dt.time = dt.time(12, 0)
    fim_almoco: dt.time = dt.time(13, 30)
    inicio_fechamento: dt.time = dt.time(17, 15)
    fim_sessao: dt.time = dt.time(18, 0)
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=11), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 1)

    def _limiar_da_fase(self, hora: dt.time) -> float | None:
        if self.inicio_abertura <= hora <= self.fim_abertura:
            return self.limiar_pico
        if self.inicio_almoco <= hora <= self.fim_almoco:
            return self.limiar_vale
        if self.inicio_fechamento <= hora <= self.fim_sessao:
            return self.limiar_pico
        return None  # fase neutra, sem limiar dedicado -- nao opera

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        limiar = self._limiar_da_fase(bar.ts.time())

        if (not positions and limiar is not None
                and len(self._closes) == self._closes.maxlen):
            momentum = (bar.close - self._closes[0]) / self._closes[0]
            if abs(momentum) > limiar:
                side = "long" if momentum > 0 else "short"
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

        self._closes.append(bar.close)
        return acao
