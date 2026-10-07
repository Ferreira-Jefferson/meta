"""Catálogo volume/microestrutura, item 41: AbsorcaoDeVendaNoFundo.

Barra de volume alto e corpo pequeno perto da mínima recente das últimas
`janela_fundo` barras, fechando acima do ponto médio da própria barra --
leitura de absorção (agressão vendedora encontrando comprador que segura o
preço) -- entra comprado.
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
class AbsorcaoDeVendaNoFundo(IntradayStrategy):
    """Volume alto + corpo pequeno perto da mínima recente + fechamento
    acima do ponto médio da barra = absorção de venda. Entra comprado."""

    name: str = "absorcao_venda_fundo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_fundo: int = 20
    janela_vol: int = 20
    k_volume: float = 1.8
    corpo_max_ticks: int = 3
    tolerancia_fundo_ticks: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._lows = deque(maxlen=self.janela_fundo)
        self._vols = deque(maxlen=self.janela_vol)

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
        if (not positions and len(self._lows) == self._lows.maxlen
                and len(self._vols) == self._vols.maxlen):
            minima_recente = min(self._lows)
            vol_ma = sum(self._vols) / len(self._vols)
            corpo = abs(bar.close - bar.open)
            ponto_medio = (bar.high + bar.low) / 2.0
            perto_do_fundo = bar.low <= minima_recente + self.tolerancia_fundo_ticks * self.tick_size
            if (bar.volume > self.k_volume * vol_ma
                    and corpo <= self.corpo_max_ticks * self.tick_size
                    and perto_do_fundo
                    and bar.close > ponto_medio):
                acao = self._ordem("long", bar.close)

        self._lows.append(bar.low)
        self._vols.append(bar.volume)
        return acao
