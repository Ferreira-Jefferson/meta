"""Catálogo volume/microestrutura, item 40: AbsorcaoDeCompraNoTopo.

Barra de volume alto (> k× a média) e corpo PEQUENO relativo ao range,
perto da máxima recente de `janela_topo` barras, mas fechando ABAIXO do
ponto médio da própria barra (a compra que empurrou o preço até o topo
foi absorvida por venda, sem conseguir sustentar o fechamento) — entra
vendido no rompimento da mínima dessa barra.
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
class AbsorcaoDeCompraNoTopo(IntradayStrategy):
    """Volume alto, corpo pequeno perto da máxima recente, fechando
    abaixo do ponto médio da barra — arma venda no rompimento da mínima
    dessa barra."""

    name: str = "absorcao_compra_no_topo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_topo: int = 20
    janela_vol: int = 20
    k_volume: float = 1.5
    fator_corpo_maximo: float = 0.35
    proximidade_topo_ticks: int = 4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _armado_nivel: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_topo)
        self._vols = deque(maxlen=self.janela_vol)
        self._armado_nivel = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low
        proximidade = self.proximidade_topo_ticks * self.tick_size

        if not positions:
            if self._armado_nivel is not None and bar.close < self._armado_nivel:
                limite = no_tick(self._armado_nivel + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
                self._armado_nivel = None
            elif (rng > 0 and len(self._highs) == self._highs.maxlen and self._vols):
                topo_recente = max(self._highs)
                vol_ma = sum(self._vols) / len(self._vols)
                corpo = abs(bar.close - bar.open)
                ponto_medio = bar.low + 0.5 * rng
                perto_do_topo = (topo_recente - bar.high) <= proximidade
                if (bar.volume > self.k_volume * vol_ma and corpo <= self.fator_corpo_maximo * rng
                        and perto_do_topo and bar.close < ponto_medio):
                    self._armado_nivel = bar.low

        self._highs.append(bar.high)
        self._vols.append(bar.volume)
        return acao
