"""Catálogo volume/microestrutura, item 17: ReversaoDeFechamentoNoExtremoOposto.

Barra de range largo (> k× média) e volume alto (> k× média) cujo close
termina no extremo OPOSTO ao open (abriu perto da máxima e fechou perto
da mínima, ou vice-versa) — entra na direção IMPLICADA pelo fechamento
(fechou embaixo = venda continuando a reversão para baixo; fechou em
cima = compra).
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
class ReversaoDeFechamentoNoExtremoOposto(IntradayStrategy):
    """Barra de range e volume excepcionais com abertura e fechamento em
    extremos opostos — entra na direção do fechamento (continuação da
    reversão intrabarra)."""

    name: str = "reversao_fechamento_extremo_oposto"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_media: int = 20
    k_range: float = 1.5
    k_volume: float = 1.5
    faixa_extremo: float = 0.25
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ranges: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ranges = deque(maxlen=self.janela_media)
        self._vols = deque(maxlen=self.janela_media)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low

        if (not positions and rng > 0
                and len(self._ranges) == self._ranges.maxlen and self._vols):
            range_ma = sum(self._ranges) / len(self._ranges)
            vol_ma = sum(self._vols) / len(self._vols)
            if rng > self.k_range * range_ma and bar.volume > self.k_volume * vol_ma:
                abriu_perto_maxima = (bar.high - bar.open) <= self.faixa_extremo * rng
                abriu_perto_minima = (bar.open - bar.low) <= self.faixa_extremo * rng
                fechou_perto_minima = (bar.close - bar.low) <= self.faixa_extremo * rng
                fechou_perto_maxima = (bar.high - bar.close) <= self.faixa_extremo * rng

                if abriu_perto_maxima and fechou_perto_minima:
                    nivel = bar.close
                    limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif abriu_perto_minima and fechou_perto_maxima:
                    nivel = bar.close
                    limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._ranges.append(rng)
        self._vols.append(bar.volume)
        return acao
