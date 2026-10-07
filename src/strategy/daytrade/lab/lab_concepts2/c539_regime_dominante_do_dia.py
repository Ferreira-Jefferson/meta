"""Mantem o candle DIARIO sintetico da sessao corrente, calculado
INCREMENTALMENTE barra a barra (open da 1a barra, high/low acumulados, close
= ultimo preco visto) -- o vies direcional do dia (`close > open` = alta) so'
pode TROCAR DE LADO uma unica vez por sessao; depois disso fica travado ate' o
fim do pregao, mesmo que o candle sintetico volte a inverter.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class RegimeDominanteDoDia(IntradayStrategy):
    name: str = "c539_regime_dominante_do_dia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    trocas_maximas: int = 1
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
    _open_sessao: float | None = field(default=None, init=False, repr=False)
    _vies_atual: bool | None = field(default=None, init=False, repr=False)  # True=alta
    _trocas: int = field(default=0, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._open_sessao = None
        self._vies_atual = None
        self._trocas = 0
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
        if self._open_sessao is None:
            self._open_sessao = bar.open

        if bar.close != self._open_sessao:
            proposto = bar.close > self._open_sessao
            if self._vies_atual is None:
                self._vies_atual = proposto
            elif proposto != self._vies_atual:
                if self._trocas < self.trocas_maximas:
                    self._trocas += 1
                    self._vies_atual = proposto
                # senao: vies TRAVADO, ignora a proposta

        if positions or self._armou_hoje or self._vies_atual is None:
            return []
        if len(self._buffer) < self.janela_range + 1:
            return []

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if self._vies_atual and bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "vies_dominante_alta_rompe")]
        if not self._vies_atual and bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "vies_dominante_baixa_rompe")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
