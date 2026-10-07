"""Catálogo Gann/geometria sagrada, item 49: VesicaPiscisSobreposicao.

APROXIMAÇÃO: trata o range da PRIMEIRA janela de `janela_circulo` barras
do pregão e o range da janela ROLANTE das últimas `janela_circulo` barras
como dois "círculos" (em vez de duas sessões inteiras, para não depender
de casar datas entre sessões — mesmo espírito, escala intrapregão). A
interseção dos dois ranges define a banda de "valor justo" (vesica
piscis); entra em fade nas bordas da banda.
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
class VesicaPiscisSobreposicao(IntradayStrategy):
    """Interseção entre o range da primeira janela do pregão e o range da
    janela rolante atual (os dois "círculos") define uma banda de valor
    justo; entra em fade nas bordas da banda."""

    name: str = "vesica_piscis_sobreposicao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_circulo: int = 20
    tolerancia_ticks: int = 2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _barra_index: int = field(default=0, init=False, repr=False)
    _circulo1_high: float | None = field(default=None, init=False, repr=False)
    _circulo1_low: float | None = field(default=None, init=False, repr=False)
    _janela_rolante: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._barra_index = 0
        self._circulo1_high = None
        self._circulo1_low = None
        self._janela_rolante = deque(maxlen=self.janela_circulo)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._barra_index += 1

        if self._barra_index <= self.janela_circulo:
            self._circulo1_high = bar.high if self._circulo1_high is None else max(self._circulo1_high, bar.high)
            self._circulo1_low = bar.low if self._circulo1_low is None else min(self._circulo1_low, bar.low)

        if (not positions and len(self._janela_rolante) == self._janela_rolante.maxlen
                and self._circulo1_high is not None and self._circulo1_low is not None):
            highs2 = [h for h, _ in self._janela_rolante]
            lows2 = [l for _, l in self._janela_rolante]
            circulo2_high, circulo2_low = max(highs2), min(lows2)

            banda_alta = min(self._circulo1_high, circulo2_high)
            banda_baixa = max(self._circulo1_low, circulo2_low)
            tol = self.tolerancia_ticks * self.tick_size

            if banda_alta > banda_baixa:
                if abs(bar.close - banda_alta) <= tol:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif abs(bar.close - banda_baixa) <= tol:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._janela_rolante.append((bar.high, bar.low))
        return acao
