"""Catálogo volume/microestrutura, item 23: SpreadEstreitoComVolumeAlto.

Espelho do item 22: gatilho é o mesmo rompimento de range; o filtro
libera preferencialmente a entrada quando o spread está perto do MÍNIMO
da janela recente E o volume está acima da média — a janela "boa" para
operar.
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
class SpreadEstreitoComVolumeAlto(IntradayStrategy):
    """Rompimento de range de N barras, permitido só quando o spread está
    perto do mínimo da janela recente e o volume está acima da média."""

    name: str = "spread_estreito_volume_alto"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_spread: int = 20
    janela_vol: int = 20
    faixa_proximidade_minimo: float = 0.2
    k_volume: float = 1.2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _spread_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _spreads: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if "spread" in bars.columns:
            self._spread_por_ts = {ts: float(v) for ts, v in bars["spread"].items()}
        else:
            self._spread_por_ts = {}

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._spreads = deque(maxlen=self.janela_spread)
        self._vols = deque(maxlen=self.janela_vol)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        spread_atual = self._spread_por_ts.get(ts)

        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._spreads) == self._spreads.maxlen and self._vols
                and spread_atual is not None):
            range_high = max(self._highs)
            range_low = min(self._lows)
            spread_min = min(self._spreads)
            spread_max = max(self._spreads)
            vol_ma = sum(self._vols) / len(self._vols)
            faixa = spread_max - spread_min
            spread_bom = (faixa <= 0) or (
                (spread_atual - spread_min) <= self.faixa_proximidade_minimo * faixa
            )
            volume_bom = bar.volume > self.k_volume * vol_ma

            if spread_bom and volume_bom:
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
        if spread_atual is not None:
            self._spreads.append(spread_atual)
        self._vols.append(bar.volume)
        return acao
