"""Catálogo termodinâmica/informação, item 31: EntropiaTermicaRetornos.

APROXIMAÇÃO: entropia de Shannon (manual, sem lib) da distribuição dos
retornos da janela, binados em faixas de largura igual. Entropia baixa
(poucos bins concentram a massa) = regime "ordenado" -> entra a favor da
tendência (SMA); entropia alta (quase uniforme) = desordem, fica de fora.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class EntropiaTermicaRetornos(IntradayStrategy):
    """Entra a favor da tendência (close vs SMA) quando a entropia de Shannon
    dos retornos binados da janela está baixa (regime ordenado)."""

    name: str = "entropia_termica_retornos"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    trend_janela: int = 20
    n_bins: int = 5
    limiar_entropia_norm: float = 0.6
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=31), init=False, repr=False)
    _closes_trend: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 1)
        self._closes_trend = deque(maxlen=self.trend_janela)

    def _entropia_normalizada(self, retornos: list[float]) -> float | None:
        if len(retornos) < self.n_bins:
            return None
        r_min, r_max = min(retornos), max(retornos)
        if r_max <= r_min:
            return 0.0
        largura = (r_max - r_min) / self.n_bins
        contagem = [0] * self.n_bins
        for r in retornos:
            idx = int((r - r_min) / largura)
            idx = min(idx, self.n_bins - 1)
            contagem[idx] += 1
        n = len(retornos)
        entropia = 0.0
        for c in contagem:
            if c > 0:
                p = c / n
                entropia -= p * math.log2(p)
        return entropia / math.log2(self.n_bins)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if (not positions and len(self._closes) == self._closes.maxlen
                and len(self._closes_trend) == self._closes_trend.maxlen):
            retornos = [b - a for a, b in zip(self._closes, list(self._closes)[1:])]
            entropia_norm = self._entropia_normalizada(retornos)
            if entropia_norm is not None and entropia_norm < self.limiar_entropia_norm:
                sma = sum(self._closes_trend) / len(self._closes_trend)
                if bar.close > sma:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif bar.close < sma:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._closes.append(bar.close)
        self._closes_trend.append(bar.close)
        return acao
