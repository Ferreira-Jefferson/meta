"""Catálogo termodinâmica/informação, item 36: PressaoOsmoticaVolume.

APROXIMAÇÃO: desequilíbrio acumulado de volume entre velas de alta e de
baixa (volume "de compra" menos volume "de venda", proxy pelo sinal da
vela) em torno do range das últimas N barras. Entra no rompimento do
range quando o desequilíbrio acumulado excede um limiar (pressão osmótica
suficiente para atravessar a "membrana").
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
class PressaoOsmoticaVolume(IntradayStrategy):
    """Acumula desequilíbrio de volume (compra - venda, proxy pelo sinal da
    vela) numa janela; entra no rompimento do range da janela quando o
    desequilíbrio acumulado excede um limiar."""

    name: str = "pressao_osmotica_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    limiar_desequilibrio_norm: float = 0.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _volumes_liquidos: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela)
        self._lows = deque(maxlen=self.janela)
        self._volumes_liquidos = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            vol_total = sum(abs(v) for v in self._volumes_liquidos)
            desequilibrio_norm = (sum(self._volumes_liquidos) / vol_total) if vol_total > 0 else 0.0

            if bar.close > range_high and desequilibrio_norm > self.limiar_desequilibrio_norm:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low and desequilibrio_norm < -self.limiar_desequilibrio_norm:
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
        volume_liquido = bar.volume if bar.close > bar.open else (-bar.volume if bar.close < bar.open else 0.0)
        self._volumes_liquidos.append(volume_liquido)
        return acao
