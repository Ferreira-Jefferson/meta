"""Catálogo regime/adaptação, item 70: RegimeDeContinuacaoAposPullback.

Tendência confirmada pela inclinação de uma MA longa; espera um pullback
de `pullback_ticks` contra a tendência e entra na RETOMADA (novo extremo a
favor da tendência depois do pullback).
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
class RegimeDeContinuacaoAposPullback(IntradayStrategy):
    """MA longa inclinada define a tendência; espera pullback de
    `pullback_ticks` contra a tendência e entra na retomada (novo extremo a
    favor da tendência depois do pullback)."""

    name: str = "regime_de_continuacao_apos_pullback"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_ma: int = 20
    pullback_ticks: int = 6
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes_ma: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _ma_anterior: "float | None" = field(default=None, init=False, repr=False)
    _tendencia: "str | None" = field(default=None, init=False, repr=False)
    _extremo: "float | None" = field(default=None, init=False, repr=False)
    _pullback_ativo: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes_ma = deque(maxlen=self.janela_ma)
        self._ma_anterior = None
        self._tendencia = None
        self._extremo = None
        self._pullback_ativo = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_ma.append(bar.close)

        if len(self._closes_ma) == self._closes_ma.maxlen:
            ma_atual = sum(self._closes_ma) / len(self._closes_ma)
            if self._ma_anterior is not None:
                nova_tendencia = "alta" if ma_atual > self._ma_anterior else (
                    "baixa" if ma_atual < self._ma_anterior else self._tendencia
                )
                if nova_tendencia != self._tendencia:
                    self._tendencia = nova_tendencia
                    self._extremo = bar.close
                    self._pullback_ativo = False
            self._ma_anterior = ma_atual

        pullback_preco = self.pullback_ticks * self.tick_size

        if not positions and self._tendencia is not None and self._extremo is not None:
            if self._tendencia == "alta":
                if not self._pullback_ativo:
                    self._extremo = max(self._extremo, bar.close)
                    if (self._extremo - bar.close) >= pullback_preco:
                        self._pullback_ativo = True
                elif bar.close > self._extremo:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                    self._extremo = bar.close
                    self._pullback_ativo = False
            elif self._tendencia == "baixa":
                if not self._pullback_ativo:
                    self._extremo = min(self._extremo, bar.close)
                    if (bar.close - self._extremo) >= pullback_preco:
                        self._pullback_ativo = True
                elif bar.close < self._extremo:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                    self._extremo = bar.close
                    self._pullback_ativo = False

        return acao
