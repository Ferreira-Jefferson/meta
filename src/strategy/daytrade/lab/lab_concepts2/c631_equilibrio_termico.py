"""Catálogo termodinâmica/informação, item 32: EquilibrioTermico.

APROXIMAÇÃO: "temperatura" = desvio-padrão rolling dos retornos. Entra em
reversão à média quando a temperatura, depois de um pico recente, esfria
rapidamente de volta perto da média histórica dela (o "sistema" volta ao
equilíbrio térmico).
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
class EquilibrioTermico(IntradayStrategy):
    """Mede a "temperatura" (desvio-padrão rolling dos retornos); quando ela
    esfria rápido de um pico recente de volta perto da média histórica,
    entra em reversão à média (fade do último movimento)."""

    name: str = "equilibrio_termico"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_temp: int = 10
    janela_historico_temp: int = 60
    janela_pico: int = 15
    fator_pico: float = 1.5
    fator_esfriamento: float = 1.1
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=11), init=False, repr=False)
    _temperaturas: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_temp + 1)
        self._temperaturas = deque(maxlen=self.janela_historico_temp)

    @staticmethod
    def _desvio_padrao(valores: list[float]) -> float:
        n = len(valores)
        media = sum(valores) / n
        var = sum((v - media) ** 2 for v in valores) / n
        return var ** 0.5

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if len(self._closes) == self._closes.maxlen:
            retornos = [b - a for a, b in zip(self._closes, list(self._closes)[1:])]
            temperatura = self._desvio_padrao(retornos)
            self._temperaturas.append(temperatura)

            if (not positions and len(self._temperaturas) >= self.janela_pico + 2):
                hist = list(self._temperaturas)
                media_hist = sum(hist) / len(hist)
                pico_recente = max(hist[-self.janela_pico:-1])
                esfriou = (pico_recente > self.fator_pico * media_hist
                           and temperatura < self.fator_esfriamento * media_hist
                           and temperatura < pico_recente)
                if esfriou:
                    sma = sum(self._closes) / len(self._closes)
                    if bar.close > sma:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif bar.close < sma:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]

        self._closes.append(bar.close)
        return acao
