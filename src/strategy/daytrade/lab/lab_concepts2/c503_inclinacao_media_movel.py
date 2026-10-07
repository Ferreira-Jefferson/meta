"""Slope de uma MA(N) normalizado pelo preco (diferenca entre a MA de agora e
a MA de `lookback` barras atras, dividida pelo preco): |slope| acima do limiar
segue a direcao do slope; achatado faz fade nas bordas do range recente.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import sma
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class InclinacaoMediaMovel(IntradayStrategy):
    name: str = "c503_inclinacao_media_movel"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_ma: int = 20
    lookback_slope: int = 5
    limiar_slope: float = 0.0008  # 0,08% do preco entre `lookback_slope` barras
    janela_range: int = 20
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(80), init=False, repr=False)
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
        minimo = self.janela_ma + self.lookback_slope + 1
        if len(self._buffer) < minimo:
            return []

        close = self._buffer.close()
        ma = sma(close, self.janela_ma)
        ma_agora = ma.iloc[-1]
        ma_antes = ma.iloc[-1 - self.lookback_slope]
        if pd.isna(ma_agora) or pd.isna(ma_antes) or ma_antes == 0:
            return []
        slope = (ma_agora - ma_antes) / ma_antes
        off = self.offset_ticks * self.tick_size

        if abs(slope) >= self.limiar_slope:
            side = "long" if slope > 0 else "short"
            limite = bar.close - off if side == "long" else bar.close + off
            self._armou_hoje = True
            return [self._ordem(side, limite, "slope_ma_segue")]

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        if bar.close >= faixa_hi:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "slope_ma_achatado_fade_topo")]
        if bar.close <= faixa_lo:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "slope_ma_achatado_fade_fundo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
