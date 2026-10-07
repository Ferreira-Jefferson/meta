"""Precomputa o percentil ROLANTE do spread (coluna crua do historico, so'
disponivel em `initialize`) numa janela de N barras. Spread acima do percentil
historico desliga a entrada (execucao fica cara demais); abaixo libera o
rompimento de range normal. `Bar` (o que `on_bar` recebe) NAO tem spread --
por isso o precalculo mora em `initialize` e e' consultado por timestamp.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class SpreadRegimeExecucao(IntradayStrategy):
    name: str = "c519_spread_regime_execucao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_percentil: int = 500
    percentil_maximo: float = 70.0
    janela_range: int = 20
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)
    _spread_percentil: dict = field(default_factory=dict, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if "spread" not in bars.columns:
            self._spread_percentil = {}
            return
        spread = bars["spread"].astype(float)
        minimo = max(20, self.janela_percentil // 4)
        percentil = spread.rolling(self.janela_percentil, min_periods=minimo).rank(pct=True) * 100.0
        self._spread_percentil = percentil.to_dict()

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
        if len(self._buffer) < self.janela_range + 1:
            return []

        percentil = self._spread_percentil.get(ts)
        if percentil is None or pd.isna(percentil) or percentil > self.percentil_maximo:
            return []  # spread caro demais, ou fora do historico calibrado -- nao opera

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "spread_barato_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "spread_barato_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
