"""Exige as tres MAs -- curta (M1 direto), media (M5 sintetica) e longa (M15
sintetica) -- na MESMA ordem para liberar a entrada: curta>media>longa (com
preco acima das tres) para compra, ou o espelho para venda. Qualquer
desalinhamento e' NEUTRO -- nao opera.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import sma
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada, resample_synthetic


@dataclass
class AlinhamentoMultiEscalaMa(IntradayStrategy):
    name: str = "c537_alinhamento_multiescala_ma"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_ma_curta: int = 9
    minutos_media: float = 5.0
    janela_ma_media: int = 8
    minutos_longa: float = 15.0
    janela_ma_longa: int = 8
    janela_range_m1: int = 20
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(400), init=False, repr=False)
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
        if len(self._buffer) < max(self.janela_ma_curta, self.janela_range_m1) + 1:
            return []

        close_m1 = self._buffer.close()
        ma_curta = sma(close_m1, self.janela_ma_curta).iloc[-1]
        if pd.isna(ma_curta):
            return []

        agg_m5 = resample_synthetic(self._buffer, self.minutos_media)
        agg_m15 = resample_synthetic(self._buffer, self.minutos_longa)
        if len(agg_m5) < self.janela_ma_media + 1 or len(agg_m15) < self.janela_ma_longa + 1:
            return []
        ma_media = sma(agg_m5["close"], self.janela_ma_media).iloc[-1]
        ma_longa = sma(agg_m15["close"], self.janela_ma_longa).iloc[-1]
        if pd.isna(ma_media) or pd.isna(ma_longa):
            return []

        preco = bar.close
        alinhado_alta = preco > ma_curta > ma_media > ma_longa
        alinhado_baixa = preco < ma_curta < ma_media < ma_longa
        if not (alinhado_alta or alinhado_baixa):
            return []  # desalinhado: neutro, nao opera

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range_m1 - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range_m1 - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if alinhado_alta and bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "alinhamento_multiescala_alta")]
        if alinhado_baixa and bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "alinhamento_multiescala_baixa")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
