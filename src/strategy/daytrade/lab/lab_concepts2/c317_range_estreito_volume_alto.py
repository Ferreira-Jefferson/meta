"""Catálogo volume/microestrutura, item 18: RangeEstreitoComVolumeAlto.

Barra com range ABAIXO da média mas volume ACIMA da média (compressão com
esforço real por trás) — arma os dois extremos dessa barra como níveis de
straddle; a PRIMEIRA borda que o preço romper nas barras seguintes
dispara a entrada nessa direção (a outra é descartada).
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
class RangeEstreitoComVolumeAlto(IntradayStrategy):
    """Range estreito com volume alto (compressão sob esforço); arma
    straddle nos dois extremos da barra, entra na direção da PRIMEIRA
    borda rompida."""

    name: str = "range_estreito_volume_alto"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_media: int = 20
    fator_range_max: float = 0.7
    k_volume: float = 1.3
    armado_ttl_bars: int = 10
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ranges: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _armado: dict | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ranges = deque(maxlen=self.janela_media)
        self._vols = deque(maxlen=self.janela_media)
        self._armado = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low

        if not positions:
            if self._armado is not None:
                self._armado["idade"] += 1
                if bar.close > self._armado["topo"]:
                    nivel = self._armado["topo"]
                    limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                    self._armado = None
                elif bar.close < self._armado["fundo"]:
                    nivel = self._armado["fundo"]
                    limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                    self._armado = None
                elif self._armado["idade"] > self.armado_ttl_bars:
                    self._armado = None

            if self._armado is None and rng > 0 and len(self._ranges) == self._ranges.maxlen and self._vols:
                range_ma = sum(self._ranges) / len(self._ranges)
                vol_ma = sum(self._vols) / len(self._vols)
                if rng < self.fator_range_max * range_ma and bar.volume > self.k_volume * vol_ma:
                    self._armado = {"topo": bar.high, "fundo": bar.low, "idade": 0}

        self._ranges.append(rng)
        self._vols.append(bar.volume)
        return acao
