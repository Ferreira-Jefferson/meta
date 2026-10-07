"""Catálogo volume/microestrutura, item 20: CompressaoSequencialDeRangeEVolume.

`n_barras` seguidas com range E volume decrescendo SIMULTANEAMENTE
(coiling gradual, distinto do item 18 que é uma barra só) — entra no
rompimento da faixa formada por essas barras, na direção do rompimento.
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
class CompressaoSequencialDeRangeEVolume(IntradayStrategy):
    """`n_barras` com range e volume decrescendo simultaneamente
    (compressão gradual) — entra no rompimento da faixa formada por
    essas barras."""

    name: str = "compressao_sequencial_range_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    n_barras: int = 4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _janela: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._janela = deque(maxlen=self.n_barras)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._janela) == self._janela.maxlen:
            ranges = [b.high - b.low for b in self._janela]
            vols = [b.volume for b in self._janela]
            range_decrescente = all(ranges[i] > ranges[i + 1] for i in range(len(ranges) - 1))
            vol_decrescente = all(vols[i] > vols[i + 1] for i in range(len(vols) - 1))
            if range_decrescente and vol_decrescente:
                topo = max(b.high for b in self._janela)
                fundo = min(b.low for b in self._janela)
                if bar.close > topo:
                    limite = no_tick(topo - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif bar.close < fundo:
                    limite = no_tick(fundo + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._janela.append(bar)
        return acao
