"""Catálogo volume/microestrutura, item 66: AssimetriaDeVolumeAltaXBaixa.

Soma o volume das barras de alta (close>open) contra o das barras de
baixa numa janela móvel; quando a razão entre os dois lados passa de um
limiar, entra na direção do lado dominante.
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
class AssimetriaDeVolumeAltaXBaixa(IntradayStrategy):
    """Razão do volume de barras de alta contra o de barras de baixa numa
    janela -- entra na direção do lado dominante quando passa o limiar."""

    name: str = "assimetria_volume_alta_baixa"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    razao_limiar: float = 1.8
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _pares: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._pares = deque(maxlen=self.janela)

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
        if not positions and len(self._pares) == self._pares.maxlen:
            vol_alta = sum(v for cor, v in self._pares if cor > 0)
            vol_baixa = sum(v for cor, v in self._pares if cor < 0)
            eps = 1e-9
            if vol_alta / (vol_baixa + eps) > self.razao_limiar:
                acao = self._ordem("long", bar.close)
            elif vol_baixa / (vol_alta + eps) > self.razao_limiar:
                acao = self._ordem("short", bar.close)

        cor = 1 if bar.close > bar.open else (-1 if bar.close < bar.open else 0)
        self._pares.append((cor, bar.volume))
        return acao
