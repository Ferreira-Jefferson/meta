"""Catálogo volume/microestrutura, item 42: PressaoSemAvancoDePreco.

Volume crescente por `janela_seq` barras consecutivas enquanto o close fica
lateralizado (range apertado); entra na primeira barra que rompe essa
lateralização com volume de confirmação acima da média.
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
class PressaoSemAvancoDePreco(IntradayStrategy):
    """Volume subindo barra a barra sem o preço lateralizado se mover;
    entra no rompimento da lateralização com volume de confirmação."""

    name: str = "pressao_sem_avanco"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_seq: int = 4
    limiar_lateral_ticks: int = 6
    k_volume_confirmacao: float = 1.2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_seq)
        self._closes = deque(maxlen=self.janela_seq)

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
        if (not positions and len(self._vols) == self._vols.maxlen
                and len(self._closes) == self._closes.maxlen):
            vols = list(self._vols)
            volume_crescente = all(vols[i] < vols[i + 1] for i in range(len(vols) - 1))
            faixa_alta = max(self._closes)
            faixa_baixa = min(self._closes)
            lateralizado = (faixa_alta - faixa_baixa) <= self.limiar_lateral_ticks * self.tick_size
            vol_ma = sum(vols) / len(vols)
            if volume_crescente and lateralizado and bar.volume > self.k_volume_confirmacao * vol_ma:
                if bar.close > faixa_alta:
                    acao = self._ordem("long", faixa_alta)
                elif bar.close < faixa_baixa:
                    acao = self._ordem("short", faixa_baixa)

        self._vols.append(bar.volume)
        self._closes.append(bar.close)
        return acao
