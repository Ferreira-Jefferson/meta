"""Catálogo volume/microestrutura, item 70: RazaoVolumePorTamanhoDePavio.

Razão entre o tamanho combinado dos pavios (mecha) e o corpo da barra.
Volume alto + pavios grandes dos dois lados (indecisão) -- fade contra a
tendência recente; volume alto + corpo dominante (baixa razão pavio/corpo)
-- continuação na direção da própria barra. Dois gatilhos, uma classe.
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
class RazaoVolumePorTamanhoDePavio(IntradayStrategy):
    """Volume alto com pavios grandes (indecisão) -- fade contra a
    tendência; volume alto com corpo dominante -- continuação."""

    name: str = "razao_volume_tamanho_pavio"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 20
    janela_trend: int = 10
    k_volume: float = 1.5
    limiar_pavio_grande: float = 2.0
    limiar_corpo_dominante: float = 0.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_vol)
        self._closes = deque(maxlen=self.janela_trend)

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
        eps = 1e-9
        corpo = abs(bar.close - bar.open)
        pavio_superior = bar.high - max(bar.open, bar.close)
        pavio_inferior = min(bar.open, bar.close) - bar.low
        ratio_pavio = (pavio_superior + pavio_inferior) / (corpo + eps)

        if (not positions and len(self._vols) == self._vols.maxlen
                and len(self._closes) == self._closes.maxlen):
            vol_ma = sum(self._vols) / len(self._vols)
            volume_alto = bar.volume > self.k_volume * vol_ma
            if volume_alto and ratio_pavio > self.limiar_pavio_grande:
                tendencia_alta = bar.close > self._closes[0]
                acao = self._ordem("short" if tendencia_alta else "long", bar.close)
            elif volume_alto and ratio_pavio < self.limiar_corpo_dominante:
                if bar.close > bar.open:
                    acao = self._ordem("long", bar.close)
                elif bar.close < bar.open:
                    acao = self._ordem("short", bar.close)

        self._vols.append(bar.volume)
        self._closes.append(bar.close)
        return acao
