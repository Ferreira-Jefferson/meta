"""Catálogo volume/microestrutura, item 9: VolumeDecrescenteNaTendencia.

Tendência em curso (SMA de `janela_trend` fechamentos) mas volume caindo
barra a barra por `n_barras` — tratado como exaustão: arma reversão
CONTRA a tendência, disparando quando o preço rompe o extremo oposto da
janela de exaustão.
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
class VolumeDecrescenteNaTendencia(IntradayStrategy):
    """Tendência em curso com volume caindo `n_barras` seguidas —
    exaustão: entra CONTRA a tendência no rompimento do extremo oposto da
    janela de exaustão."""

    name: str = "volume_decrescente_na_tendencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_trend: int = 20
    n_barras: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _janela: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_trend)
        self._janela = deque(maxlen=self.n_barras)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if (not positions and len(self._closes) == self._closes.maxlen
                and len(self._janela) == self._janela.maxlen):
            tendencia_alta = bar.close > self._closes[0]
            tendencia_baixa = bar.close < self._closes[0]
            vols = [b.volume for b in self._janela]
            vol_decrescente = all(vols[i] > vols[i + 1] for i in range(len(vols) - 1))
            fundo_janela = min(b.low for b in self._janela)
            topo_janela = max(b.high for b in self._janela)
            if vol_decrescente and tendencia_alta and bar.close < fundo_janela:
                limite = no_tick(fundo_janela + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif vol_decrescente and tendencia_baixa and bar.close > topo_janela:
                limite = no_tick(topo_janela - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._closes.append(bar.close)
        self._janela.append(bar)
        return acao
