"""Largura de Banda de Bollinger (propria, sem lib) normalizada pelo preco,
comparada ao HISTORICO recente dela mesma (percentil): percentil alto (banda
esticada) segue o rompimento fora da banda; percentil baixo (banda apertada)
faz fade DENTRO da banda, apostando na volta ao centro.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from core.indicators import bollinger_bands
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, percentile_rank


@dataclass
class BandaLargacaoRegime(IntradayStrategy):
    name: str = "c507_banda_largura_regime"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_banda: int = 20
    k_desvios: float = 2.0
    janela_percentil: int = 60
    percentil_alto: float = 80.0
    percentil_baixo: float = 20.0
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(100), init=False, repr=False)
    _historico_largura: deque = field(
        default_factory=lambda: deque(maxlen=250), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

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
        if len(self._buffer) < self.janela_banda + 1:
            return []

        close = self._buffer.close()
        upper, mid, lower = bollinger_bands(close, self.janela_banda, self.k_desvios)
        if pd.isna(upper.iloc[-1]) or mid.iloc[-1] == 0:
            return []
        largura = (upper.iloc[-1] - lower.iloc[-1]) / mid.iloc[-1]

        percentil = percentile_rank(self._historico_largura, largura)
        self._historico_largura.append(largura)

        if positions or self._armou_hoje:
            return []
        if len(self._historico_largura) < self.janela_percentil // 2:
            return []

        off = self.offset_ticks * self.tick_size
        if percentil >= self.percentil_alto:
            if bar.close > upper.iloc[-1]:
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, "banda_larga_rompe_cima")]
            if bar.close < lower.iloc[-1]:
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, "banda_larga_rompe_baixo")]
        elif percentil <= self.percentil_baixo:
            if bar.close >= upper.iloc[-1]:
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, "banda_estreita_fade_topo")]
            if bar.close <= lower.iloc[-1]:
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, "banda_estreita_fade_fundo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
