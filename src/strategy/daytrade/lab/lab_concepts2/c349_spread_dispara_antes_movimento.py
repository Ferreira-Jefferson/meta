"""Catálogo volume/microestrutura, item 50: SpreadDisparaAntesDoMovimento.

Précompute `spread` em `initialize` (não existe em `Bar`). Spread acima da
banda normal (z-score, sem teste formal) bloqueia entradas por
`k_barras_bloqueio` barras -- o gatilho base é um rompimento Donchian
simples, que fica desativado enquanto o bloqueio estiver ativo.
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
class SpreadDisparaAntesDoMovimento(IntradayStrategy):
    """Spread disparado (z-score alto) bloqueia entradas por K barras --
    filtro aplicado sobre um gatilho de rompimento Donchian simples."""

    name: str = "spread_dispara_antes_movimento"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_spread: int = 20
    k_desvios_spread: float = 2.0
    k_barras_bloqueio: int = 5
    janela_range: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _spread_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _spreads: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _bloqueio_restante: int = field(default=0, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        self._spread_por_ts = bars["spread"].to_dict()

    def on_session_start(self, session_date) -> None:
        self._spreads = deque(maxlen=self.janela_spread)
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._bloqueio_restante = 0

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
        spread = self._spread_por_ts.get(ts, 0.0)

        if len(self._spreads) == self._spreads.maxlen:
            serie = pd.Series(self._spreads)
            media = float(serie.mean())
            desvio = float(serie.std())
            if desvio > 0 and (spread - media) / desvio > self.k_desvios_spread:
                self._bloqueio_restante = self.k_barras_bloqueio

        if (not positions and self._bloqueio_restante <= 0
                and len(self._highs) == self._highs.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                acao = self._ordem("long", range_high)
            elif bar.close < range_low:
                acao = self._ordem("short", range_low)

        if self._bloqueio_restante > 0:
            self._bloqueio_restante -= 1

        self._spreads.append(spread)
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
