"""Catálogo física, item 24: TensaoSuperficialNivel.

Analogia com tensão superficial: um nível (topo/fundo recente) age como
membrana que resiste a ser rompida — conta quantos "toques" (barras cujo
high/low chega perto do nível sem fechar além dele) ocorreram sem ruptura.
Só entra no rompimento depois que o contador de toques excede um limiar E
há surto de volume na barra de ruptura (energia suficiente para "romper a
membrana").
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
class TensaoSuperficialNivel(IntradayStrategy):
    """Nível age como membrana; conta toques sem romper e só entra no
    rompimento após limiar de toques E surto de volume."""

    name: str = "tensao_superficial_nivel"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_nivel: int = 30
    proximidade_ticks: float = 2.0
    toques_minimos: int = 3
    janela_vol: int = 20
    k_volume: float = 1.4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_nivel)
        self._lows = deque(maxlen=self.janela_nivel)
        self._vols = deque(maxlen=self.janela_vol)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._vols) == self._vols.maxlen):
            nivel_topo = max(self._highs)
            nivel_fundo = min(self._lows)
            proximidade = self.proximidade_ticks * self.tick_size
            toques_topo = sum(1 for h in self._highs if abs(h - nivel_topo) <= proximidade)
            toques_fundo = sum(1 for l in self._lows if abs(l - nivel_fundo) <= proximidade)
            vol_media = sum(self._vols) / len(self._vols)
            surto_volume = bar.volume > self.k_volume * vol_media

            if bar.close > nivel_topo and toques_topo >= self.toques_minimos and surto_volume:
                limite = no_tick(nivel_topo - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < nivel_fundo and toques_fundo >= self.toques_minimos and surto_volume:
                limite = no_tick(nivel_fundo + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._vols.append(bar.volume)
        return acao
