"""Desvio-padrao do proprio ATR (a "vol da vol") numa janela: picos indicam
regime INSTAVEL -- acima do limiar de pausa o robo nao opera; na zona
intermediaria opera com METADE do tamanho; so' no regime normal opera cheio.
Gatilho: rompimento de range simples.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import atr
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class VolatilidadeVolatilidade(IntradayStrategy):
    name: str = "c517_volatilidade_volatilidade"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_atr: int = 14
    janela_vol_da_vol: int = 30
    janela_range: int = 20
    limiar_pausa: float = 2.0     # em ticks de desvio-padrao do ATR
    limiar_meio_size: float = 1.0
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity_base: int = 2

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
        if positions or self._armou_hoje:
            return []
        minimo = self.janela_atr + self.janela_vol_da_vol
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        serie_atr = atr(high, low, close, self.janela_atr)
        vol_da_vol_ticks = serie_atr.iloc[-self.janela_vol_da_vol:].std() / self.tick_size
        if pd.isna(vol_da_vol_ticks):
            return []

        if vol_da_vol_ticks >= self.limiar_pausa:
            return []  # regime instavel demais: pausa

        qty = (self.quantity_base // 2 if vol_da_vol_ticks >= self.limiar_meio_size
               else self.quantity_base)
        qty = max(1, qty)

        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, qty, "vol_da_vol_normal_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, qty, "vol_da_vol_normal_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, qty: int, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=qty, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
