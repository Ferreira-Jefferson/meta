"""Catálogo regime/adaptação, item 78: RegimeDeGapIntrabarraDeSpread.

Précompute (em `initialize`) o spread por barra; a variação barra-a-barra
dele (proxy de estresse de execução) é acompanhada incrementalmente --
alargamento súbito (acima de `k_estresse` vezes a variação média) muda o
regime para "somente reduzir risco": fecha posições abertas (`Exit`) e
não abre novas enquanto durar.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class RegimeDeGapIntrabarraDeSpread(IntradayStrategy):
    """Rompimento de range de N barras. Précompute o spread por barra;
    variação barra-a-barra dele acima de `k_estresse` × a variação média
    móvel liga o regime "somente reduzir risco" (fecha posições, não abre
    novas) enquanto durar."""

    name: str = "regime_de_gap_intrabarra_de_spread"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_variacao: int = 20
    k_estresse: float = 3.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _spread_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _spread_anterior: "float | None" = field(default=None, init=False, repr=False)
    _variacoes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if "spread" in bars.columns:
            self._spread_por_ts = {ts: float(v) for ts, v in bars["spread"].items()}
        else:
            self._spread_por_ts = {}

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._spread_anterior = None
        self._variacoes = deque(maxlen=self.janela_variacao)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        spread_atual = self._spread_por_ts.get(ts)
        estresse = False
        if spread_atual is not None:
            if self._spread_anterior is not None:
                variacao = abs(spread_atual - self._spread_anterior)
                if len(self._variacoes) == self._variacoes.maxlen:
                    media_variacao = sum(self._variacoes) / len(self._variacoes)
                    if media_variacao > 0 and variacao > self.k_estresse * media_variacao:
                        estresse = True
                self._variacoes.append(variacao)
            self._spread_anterior = spread_atual

        if positions:
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            if estresse:
                return [Exit(reason=self.name)]
            return acao

        if not estresse and len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
