"""Catálogo volume/microestrutura, item 37: VolumeAbaixoDaMediaSazonalDoMinuto.

FILTRO + gatilho próprio (mesmo formato dos itens 22/23): `initialize`
précomputa a média histórica de volume por MINUTO-DO-DIA (perfil
sazonal, a partir de todo o histórico recebido) usando a mesma
normalização do motor (`real_volume` se >0, senão `tick_volume`). Gatilho
é o rompimento do range de `janela_range` barras; BLOQUEADO quando o
volume da barra está abaixo do normal sazonal daquele minuto — liberado
quando está acima.
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


def _volume_normalizado(row) -> float:
    real = float(row.get("real_volume", 0.0) or 0.0)
    if real > 0:
        return real
    return float(row.get("tick_volume", 0.0) or 0.0)


@dataclass
class VolumeAbaixoDaMediaSazonalDoMinuto(IntradayStrategy):
    """Rompimento de range de N barras, bloqueado quando o volume da
    barra está abaixo da média histórica sazonal para aquele minuto do
    dia."""

    name: str = "volume_abaixo_media_sazonal_minuto"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    fator_normal_minimo: float = 0.8
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _perfil_sazonal: dict = field(default_factory=dict, init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if bars.empty:
            self._perfil_sazonal = {}
            return
        volumes = bars.apply(_volume_normalizado, axis=1)
        chave_minuto = pd.Series(
            [(t.hour, t.minute) for t in bars.index], index=bars.index,
        )
        self._perfil_sazonal = volumes.groupby(chave_minuto).mean().to_dict()

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        chave = (ts.hour, ts.minute)
        media_sazonal = self._perfil_sazonal.get(chave)

        if (not positions and len(self._highs) == self._highs.maxlen
                and media_sazonal is not None and media_sazonal > 0):
            volume_normal = bar.volume >= self.fator_normal_minimo * media_sazonal
            if volume_normal:
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
