"""Catálogo caos/fractais, item 12: RenormalizationScaleInvariance.

APROXIMAÇÃO HEURÍSTICA de invariância de escala (grupo de renormalização):
compara o range (máximo−mínimo) agregado em janelas de 1, 5 e 25 barras
(via `pandas.resample`-like agregação por blocos); se as razões
range_5/range_1 e range_25/range_5 ficam próximas uma da outra (dentro de
tolerância relativa), o mercado está "auto-similar" e o robô segue a
continuação; quando a razão quebra (escalas divergem), entra em reversão.
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
class RenormalizationScaleInvariance(IntradayStrategy):
    """Compara range agregado em 1, 5 e 25 barras; razões próximas (escala
    invariante) seguem continuação, razões que divergem entram em
    reversão."""

    name: str = "renormalization_scale_invariance"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    tolerancia_relativa: float = 0.35
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=25), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=25), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=25)
        self._lows = deque(maxlen=25)
        self._closes = deque(maxlen=2)

    @staticmethod
    def _range_n(highs: list[float], lows: list[float], n: int) -> float:
        return max(highs[-n:]) - min(lows[-n:])

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if not positions and len(self._highs) == self._highs.maxlen:
            highs, lows = list(self._highs), list(self._lows)
            range_1 = self._range_n(highs, lows, 1)
            range_5 = self._range_n(highs, lows, 5)
            range_25 = self._range_n(highs, lows, 25)
            if range_1 > 1e-9 and range_5 > 1e-9:
                razao_1 = range_5 / range_1
                razao_2 = range_25 / range_5
                divergencia = abs(razao_1 - razao_2) / max(razao_1, razao_2)
                ultimo_retorno = self._closes[-1] - self._closes[-2] if len(self._closes) == 2 else 0.0
                if divergencia <= self.tolerancia_relativa:
                    if ultimo_retorno > 0:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif ultimo_retorno < 0:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                elif divergencia > 2 * self.tolerancia_relativa:
                    if ultimo_retorno > 0:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif ultimo_retorno < 0:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._closes.append(bar.close)
        return acao
