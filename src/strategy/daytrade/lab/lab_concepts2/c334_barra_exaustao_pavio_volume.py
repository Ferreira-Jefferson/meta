"""Catálogo volume/microestrutura, item 35: BarraDeExaustaoComPabiloEVolume.

Dentro de tendência (SMA de `janela_trend` fechamentos), barra com pavio
LONGO contra a direção da tendência (rejeição) e volume acima da média —
entra na direção do pavio (reversão): tendência de alta com pavio
superior longo vira venda; tendência de baixa com pavio inferior longo
vira compra.
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
class BarraDeExaustaoComPabiloEVolume(IntradayStrategy):
    """Pavio longo contra a tendência com volume acima da média — entra
    na direção do pavio (reversão)."""

    name: str = "barra_exaustao_pavio_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_trend: int = 20
    janela_vol: int = 20
    k_volume: float = 1.3
    fator_pavio_corpo: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_trend)
        self._vols = deque(maxlen=self.janela_vol)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        corpo = abs(bar.close - bar.open)
        pavio_superior = bar.high - max(bar.close, bar.open)
        pavio_inferior = min(bar.close, bar.open) - bar.low

        if (not positions and len(self._closes) == self._closes.maxlen
                and len(self._vols) == self._vols.maxlen and corpo > 0):
            vol_ma = sum(self._vols) / len(self._vols)
            volume_ok = bar.volume > self.k_volume * vol_ma
            tendencia_alta = bar.close > self._closes[0]
            tendencia_baixa = bar.close < self._closes[0]

            if (tendencia_alta and volume_ok
                    and pavio_superior > self.fator_pavio_corpo * corpo):
                nivel = bar.close
                limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif (tendencia_baixa and volume_ok
                    and pavio_inferior > self.fator_pavio_corpo * corpo):
                nivel = bar.close
                limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._closes.append(bar.close)
        self._vols.append(bar.volume)
        return acao
