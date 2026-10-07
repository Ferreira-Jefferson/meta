"""Volume caindo consistentemente (media recente abaixo da media mais antiga)
JUNTO com range comprimido (percentil baixo) caracteriza "secagem" -- o robo
so' entra no PRIMEIRO candle que rompe o range recente com volume ACIMA da
media recente (a secagem tem que ter ACABADO para operar).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class SecagemVolume(IntradayStrategy):
    name: str = "c531_secagem_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_recente: int = 10
    janela_antiga: int = 30
    janela_range: int = 20
    fator_secagem: float = 0.7      # volume recente precisa estar < 70% do antigo
    fator_volume_rompimento: float = 1.5  # volume do rompimento precisa ser > 1,5x a media recente
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
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
        minimo = max(self.janela_antiga, self.janela_range) + 1
        if len(self._buffer) < minimo:
            return []

        high, low, volume = self._buffer.high(), self._buffer.low(), self._buffer.volume()
        # medias de volume ATE a barra anterior (a corrente e' quem tem que
        # CONFIRMAR o rompimento com volume alto, nao contaminar a media)
        vol_recente = volume.iloc[-self.janela_recente - 1:-1].mean()
        vol_antiga = volume.iloc[-self.janela_antiga - 1:-1].mean()
        if not vol_antiga or vol_antiga <= 0:
            return []
        secando = (vol_recente / vol_antiga) < self.fator_secagem

        if positions or self._armou_hoje:
            return []
        if not secando:
            return []

        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        volume_confirma = bar.volume > self.fator_volume_rompimento * vol_recente
        if not volume_confirma:
            return []

        off = self.offset_ticks * self.tick_size
        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "secagem_rompe_cima_com_volume")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "secagem_rompe_baixo_com_volume")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
