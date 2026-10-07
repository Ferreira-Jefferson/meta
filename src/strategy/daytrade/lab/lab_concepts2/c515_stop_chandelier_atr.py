"""Rompimento simples de range para entrar; enquanto a posicao esta' aberta, o
STOP e' um Chandelier: maxima (ou minima) das ultimas N barras +/- K*ATR,
recalculado a cada barra e enviado como `AdjustStop` -- o motor so' aceita se
for MAIS protetor, entao o nivel so' anda a favor do trade, nunca contra.
Alvo fixo, respeitando o piso de 4 ticks.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import atr
from strategy.daytrade.base import (
    AdjustStop, Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, no_tick


@dataclass
class StopChandelierAtr(IntradayStrategy):
    name: str = "c515_stop_chandelier_atr"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_atr: int = 14
    janela_chandelier: int = 20
    janela_range_entrada: int = 20
    k_atr_stop: float = 3.0
    stop_inicial_ticks: int = 20
    alvo_ticks: int = 40
    offset_ticks: int = 2
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(100), init=False, repr=False)
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
        minimo = max(self.janela_atr, self.janela_chandelier, self.janela_range_entrada) + 1
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        atr_atual = atr(high, low, close, self.janela_atr).iloc[-1]

        if positions:
            if pd.isna(atr_atual) or atr_atual <= 0:
                return []
            pos = positions[0]
            if pos.side == "long":
                topo = high.iloc[-self.janela_chandelier:].max()
                novo_stop = no_tick(topo - self.k_atr_stop * atr_atual, self.tick_size)
                if pos.current_stop is None or novo_stop > pos.current_stop:
                    return [AdjustStop(novo_stop)]
            else:
                fundo = low.iloc[-self.janela_chandelier:].min()
                novo_stop = no_tick(fundo + self.k_atr_stop * atr_atual, self.tick_size)
                if pos.current_stop is None or novo_stop < pos.current_stop:
                    return [AdjustStop(novo_stop)]
            return []

        if self._armou_hoje:
            return []

        faixa_hi = high.iloc[-self.janela_range_entrada - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range_entrada - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "chandelier_entra_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "chandelier_entra_baixo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_inicial_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
