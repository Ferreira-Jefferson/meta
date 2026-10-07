"""Distancia do close a uma MA longa, medida em ATRs: quando o sinal da
distancia fica CONSTANTE por M barras seguidas (regime persistente), o robo
segue a tendencia e vai aumentando o tamanho (pyramid, teto 3 contratos);
quando o sinal oscila ao redor de zero (regime lateral), faz fade a cada
desvio grande.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from core.indicators import atr, sma
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, clamp_quantity, montar_entrada


@dataclass
class DistanciaMediaRegime(IntradayStrategy):
    name: str = "c509_distancia_media_regime"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_ma_longa: int = 60
    janela_atr: int = 14
    janela_persistencia: int = 10
    limiar_desvio_fade: float = 1.5
    teto_pyramid: int = 3
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(150), init=False, repr=False)
    _sinais_dist: deque = field(
        default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._sinais_dist = deque(maxlen=self.janela_persistencia)

    def on_session_start(self, session_date) -> None:
        self._armou_hoje = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._buffer.push(bar)
        minimo = self.janela_ma_longa + self.janela_atr
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        ma_longa = sma(close, self.janela_ma_longa).iloc[-1]
        atr_atual = atr(high, low, close, self.janela_atr).iloc[-1]
        if pd.isna(ma_longa) or pd.isna(atr_atual) or atr_atual <= 0:
            return []

        dist_atr = (bar.close - ma_longa) / atr_atual
        sinal = 1 if dist_atr > 0 else (-1 if dist_atr < 0 else 0)
        self._sinais_dist.append(sinal)

        if positions or self._armou_hoje:
            return []
        if len(self._sinais_dist) < self._sinais_dist.maxlen:
            return []

        off = self.offset_ticks * self.tick_size
        persistente_alta = all(s > 0 for s in self._sinais_dist)
        persistente_baixa = all(s < 0 for s in self._sinais_dist)

        if persistente_alta or persistente_baixa:
            # tendencia persistente: segue, com pyramid proporcional ao
            # desvio corrente (quanto mais esticado, mais unidades)
            qty = clamp_quantity(1 + abs(dist_atr) / 2.0, minimo=1, teto=self.teto_pyramid)
            side = "long" if persistente_alta else "short"
            limite = bar.close - off if side == "long" else bar.close + off
            self._armou_hoje = True
            return [self._ordem(side, limite, qty, "distancia_media_persistente_segue")]

        # oscilando ao redor de zero: fade a cada desvio grande
        if abs(dist_atr) >= self.limiar_desvio_fade:
            side = "short" if dist_atr > 0 else "long"
            limite = bar.close + off if side == "short" else bar.close - off
            self._armou_hoje = True
            return [self._ordem(side, limite, 1, "distancia_media_oscilante_fade")]
        return []

    def _ordem(self, side: str, limite: float, qty: int, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=qty, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
