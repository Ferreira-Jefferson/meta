"""Catálogo volume/microestrutura, item 2: PullbackComSecaDeVolume.

Dentro de tendência (SMA de `janela_trend` fechamentos), uma correção
contra a tendência com volume abaixo da média das `janela_vol` últimas
barras arma a entrada; quando o preço retoma a direção original (fecha
além do extremo pré-correção) a entrada dispara a favor da tendência.
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
class PullbackComSecaDeVolume(IntradayStrategy):
    """Compra pullback seco em tendência de alta (venda em tendência de
    baixa): correção com volume abaixo da média, entra quando o preço
    retoma a direção original da tendência."""

    name: str = "pullback_seca_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_trend: int = 20
    janela_vol: int = 20
    fator_seca: float = 0.7
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _pre_pullback_extremo: float | None = field(default=None, init=False, repr=False)
    _pullback_lado: str | None = field(default=None, init=False, repr=False)
    _ultimo_extremo_tendencia: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_trend)
        self._vols = deque(maxlen=self.janela_vol)
        self._pre_pullback_extremo = None
        self._pullback_lado = None
        self._ultimo_extremo_tendencia = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        vol_ma = sum(self._vols) / len(self._vols) if self._vols else None

        if not positions and len(self._closes) == self._closes.maxlen and vol_ma:
            tendencia_alta = bar.close > self._closes[0]
            tendencia_baixa = bar.close < self._closes[0]
            bar_seca = bar.volume < self.fator_seca * vol_ma

            if tendencia_alta:
                if bar.close < bar.open and bar_seca:
                    self._pullback_lado = "long"
                    self._pre_pullback_extremo = bar.low
                elif self._pullback_lado == "long" and self._pre_pullback_extremo is not None:
                    if bar.close > max(self._closes):
                        nivel = bar.close
                        limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                        self._pullback_lado = None
            elif tendencia_baixa:
                if bar.close > bar.open and bar_seca:
                    self._pullback_lado = "short"
                    self._pre_pullback_extremo = bar.high
                elif self._pullback_lado == "short" and self._pre_pullback_extremo is not None:
                    if bar.close < min(self._closes):
                        nivel = bar.close
                        limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                        self._pullback_lado = None
            else:
                self._pullback_lado = None

        self._closes.append(bar.close)
        self._vols.append(bar.volume)
        return acao
