"""Catálogo volume/microestrutura, item 62: FalhaDeRompimentoPorBaixoVolume.

Espelho de `c360_quebra_estrutura_validada_volume.py`: preço perfura o
nível de swing (máxima/mínima) mas com volume abaixo da média -- trata
como rompimento falso e faz fade de volta para dentro do range.
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
class FalhaDeRompimentoPorBaixoVolume(IntradayStrategy):
    """Perfuração de swing high/low com volume abaixo da média -- trata
    como rompimento falso, fade de volta para dentro do range."""

    name: str = "falha_rompimento_baixo_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_pivo: int = 2
    lookback_barras: int = 30
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _janela_high: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _janela_low: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _swing_high: float | None = field(default=None, init=False, repr=False)
    _swing_low: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        janela = 2 * self.janela_pivo + 1
        self._janela_high = deque(maxlen=janela)
        self._janela_low = deque(maxlen=janela)
        self._vols = deque(maxlen=self.lookback_barras)
        self._swing_high = None
        self._swing_low = None

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
        self._janela_high.append(bar.high)
        self._janela_low.append(bar.low)

        if len(self._janela_high) == self._janela_high.maxlen:
            centro_high = self._janela_high[self.janela_pivo]
            centro_low = self._janela_low[self.janela_pivo]
            if centro_high == max(self._janela_high):
                self._swing_high = centro_high
            if centro_low == min(self._janela_low):
                self._swing_low = centro_low

        if (not positions and len(self._vols) == self._vols.maxlen
                and (self._swing_high is not None or self._swing_low is not None)):
            vol_ma = sum(self._vols) / len(self._vols)
            perfurou_alta = (
                self._swing_high is not None and bar.high > self._swing_high
                and bar.close < self._swing_high and bar.volume < vol_ma
            )
            perfurou_baixa = (
                self._swing_low is not None and bar.low < self._swing_low
                and bar.close > self._swing_low and bar.volume < vol_ma
            )
            if perfurou_alta:
                acao = self._ordem("short", bar.close)
                self._swing_high = None
            elif perfurou_baixa:
                acao = self._ordem("long", bar.close)
                self._swing_low = None

        self._vols.append(bar.volume)
        return acao
