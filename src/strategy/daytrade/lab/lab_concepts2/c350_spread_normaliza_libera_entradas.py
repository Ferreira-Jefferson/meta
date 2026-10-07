"""Catálogo volume/microestrutura, item 51: SpreadNormalizaLiberaEntradas.

Précompute `spread` em `initialize`. O retorno do spread da faixa elevada
para a faixa normal (transição, não o nível em si) LIBERA a entrada por
UMA barra -- combinado com o mesmo gatilho de rompimento Donchian de
`c349_spread_dispara_antes_movimento.py`.
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
class SpreadNormalizaLiberaEntradas(IntradayStrategy):
    """Spread volta da faixa elevada para a normal (transição) libera, só
    nesta barra, um gatilho de rompimento Donchian."""

    name: str = "spread_normaliza_libera_entradas"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_spread: int = 20
    k_desvios_spread: float = 2.0
    janela_range: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _spread_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _spreads: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _elevado_anterior: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        self._spread_por_ts = bars["spread"].to_dict()

    def on_session_start(self, session_date) -> None:
        self._spreads = deque(maxlen=self.janela_spread)
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._elevado_anterior = False

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
        elevado_atual = False

        if len(self._spreads) == self._spreads.maxlen:
            serie = pd.Series(self._spreads)
            media = float(serie.mean())
            desvio = float(serie.std())
            if desvio > 0:
                elevado_atual = (spread - media) / desvio > self.k_desvios_spread

            liberado_agora = self._elevado_anterior and not elevado_atual
            if (not positions and liberado_agora
                    and len(self._highs) == self._highs.maxlen):
                range_high = max(self._highs)
                range_low = min(self._lows)
                if bar.close > range_high:
                    acao = self._ordem("long", range_high)
                elif bar.close < range_low:
                    acao = self._ordem("short", range_low)

        self._elevado_anterior = elevado_atual
        self._spreads.append(spread)
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
