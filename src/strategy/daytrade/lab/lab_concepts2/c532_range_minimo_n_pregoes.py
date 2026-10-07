"""Compara o range do pregao CORRENTE (acumulado ate' agora) com a media dos
ultimos N pregoes ANTERIORES (precomputada em `initialize`, sem look-ahead --
a media de cada dia usa so' dias estritamente anteriores). No menor percentil
(dia comprimido de verdade), opera SO' o rompimento da propria maxima/minima
do pregao -- fora desse regime nao ha' sinal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class RangeMinimoNPregoes(IntradayStrategy):
    name: str = "c532_range_minimo_n_pregoes"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_dias: int = 20
    limiar_ratio_comprimido: float = 0.5
    minutos_minimos_de_pregao: float = 30.0
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(30), init=False, repr=False)
    _media_range_por_dia: dict = field(default_factory=dict, init=False, repr=False)
    _open_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _sessao_hi: float | None = field(default=None, init=False, repr=False)
    _sessao_lo: float | None = field(default=None, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if bars.empty:
            self._media_range_por_dia = {}
            return
        datas = bars.index.date
        diario = bars.groupby(datas).agg(high=("high", "max"), low=("low", "min"))
        diario["range"] = diario["high"] - diario["low"]
        # shift(1): a media de um dia usa SO' os N dias ANTERIORES a ele --
        # olhar o proprio dia seria look-ahead.
        media = diario["range"].rolling(self.janela_dias, min_periods=5).mean().shift(1)
        self._media_range_por_dia = media.to_dict()

    def on_session_start(self, session_date) -> None:
        self._open_ts = None
        self._sessao_hi = None
        self._sessao_lo = None
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
        if self._open_ts is None:
            self._open_ts = ts

        # checa rompimento com os extremos ANTES desta barra
        sessao_hi_antes = self._sessao_hi
        sessao_lo_antes = self._sessao_lo
        self._sessao_hi = bar.high if self._sessao_hi is None else max(self._sessao_hi, bar.high)
        self._sessao_lo = bar.low if self._sessao_lo is None else min(self._sessao_lo, bar.low)

        if positions or self._armou_hoje:
            return []
        if (ts - self._open_ts) < pd.Timedelta(minutes=self.minutos_minimos_de_pregao):
            return []
        if sessao_hi_antes is None or sessao_lo_antes is None:
            return []

        media_historica = self._media_range_por_dia.get(ts.date())
        if media_historica is None or pd.isna(media_historica) or media_historica <= 0:
            return []

        range_ate_agora = sessao_hi_antes - sessao_lo_antes
        ratio = range_ate_agora / media_historica
        if ratio > self.limiar_ratio_comprimido:
            return []  # dia nao esta' comprimido o bastante -- regime nao se aplica

        off = self.offset_ticks * self.tick_size
        if bar.close > sessao_hi_antes:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "dia_comprimido_rompe_maxima")]
        if bar.close < sessao_lo_antes:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "dia_comprimido_rompe_minima")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
