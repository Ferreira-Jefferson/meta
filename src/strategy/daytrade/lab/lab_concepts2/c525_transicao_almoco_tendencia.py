"""Ao sair do horario de almoco, se a faixa formada durante o almoco foi
ESTREITA (mercado realmente parado, nao so' devagar), o primeiro rompimento
dessa faixa depois do almoco e' operado como INICIO da tendencia da tarde.
Almoco largo nao produz sinal nenhum -- a faixa nao era compressao de verdade.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class TransicaoAlmocoTendencia(IntradayStrategy):
    name: str = "c525_transicao_almoco_tendencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    hora_inicio_almoco: dt.time = dt.time(12, 0)
    hora_fim_almoco: dt.time = dt.time(13, 30)
    faixa_maxima_ticks: float = 15.0
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 35
    entrada_ttl_bars: int = 60
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(30), init=False, repr=False)
    _almoco_hi: float | None = field(default=None, init=False, repr=False)
    _almoco_lo: float | None = field(default=None, init=False, repr=False)
    _almoco_valido: bool | None = field(default=None, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._almoco_hi = None
        self._almoco_lo = None
        self._almoco_valido = None
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
        hora = ts.time()

        if self.hora_inicio_almoco <= hora <= self.hora_fim_almoco:
            self._almoco_hi = bar.high if self._almoco_hi is None else max(self._almoco_hi, bar.high)
            self._almoco_lo = bar.low if self._almoco_lo is None else min(self._almoco_lo, bar.low)
            return []

        if hora <= self.hora_fim_almoco:
            return []  # ainda nao chegou ao almoco hoje

        if self._almoco_valido is None:
            if self._almoco_hi is None or self._almoco_lo is None:
                self._almoco_valido = False
            else:
                faixa_ticks = (self._almoco_hi - self._almoco_lo) / self.tick_size
                self._almoco_valido = faixa_ticks <= self.faixa_maxima_ticks

        if positions or self._armou_hoje or not self._almoco_valido:
            return []

        off = self.offset_ticks * self.tick_size
        if bar.close > self._almoco_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "transicao_almoco_tendencia_alta")]
        if bar.close < self._almoco_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "transicao_almoco_tendencia_baixa")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
