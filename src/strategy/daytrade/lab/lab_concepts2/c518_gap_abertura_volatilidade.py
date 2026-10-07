"""Classifica o GAP de abertura (fechamento de ontem vs abertura de hoje) em
ticks. Gap grande muda o regime do dia: stop e alvo saem AMPLIADOS nas
primeiras N barras da sessao (mais espaco para a volatilidade extra do gap);
gap pequeno usa a geometria normal. Gatilho: rompimento do range desde a
abertura.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class GapAberturaVolatilidade(IntradayStrategy):
    name: str = "c518_gap_abertura_volatilidade"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_regime_minutos: float = 30.0
    limiar_gap_ticks: float = 20.0
    stop_normal_ticks: int = 20
    alvo_normal_ticks: int = 30
    fator_ampliacao_gap: float = 1.75
    offset_ticks: int = 2
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
    _open_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _range_hi: float | None = field(default=None, init=False, repr=False)
    _range_lo: float | None = field(default=None, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)
    #: ultimo close visto (atualizado em TODA barra) -- em `on_session_start`
    #: vira o fechamento de ONTEM antes de ser sobrescrito por hoje.
    _ultimo_close_visto: float | None = field(default=None, init=False, repr=False)
    _fechamento_ontem: float | None = field(default=None, init=False, repr=False)
    _gap_ticks: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._fechamento_ontem = self._ultimo_close_visto
        self._open_ts = None
        self._range_hi = None
        self._range_lo = None
        self._armou_hoje = False
        self._gap_ticks = 0.0

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._buffer.push(bar)
        primeira_barra_do_dia = self._open_ts is None
        if primeira_barra_do_dia:
            self._open_ts = ts
            if self._fechamento_ontem is not None:
                self._gap_ticks = (bar.open - self._fechamento_ontem) / self.tick_size
            self._range_hi = bar.high
            self._range_lo = bar.low
            self._ultimo_close_visto = bar.close
            return []  # primeira barra so' semeia o range, nunca rompe a si mesma

        self._ultimo_close_visto = bar.close
        # range ANTES desta barra -- a barra corrente nunca pode "romper"
        # um range que ja' inclui ela mesma
        range_hi_antes = self._range_hi
        range_lo_antes = self._range_lo
        self._range_hi = max(self._range_hi, bar.high)
        self._range_lo = min(self._range_lo, bar.low)

        if positions or self._armou_hoje:
            return []

        dentro_janela_gap = (ts - self._open_ts) < pd.Timedelta(minutes=self.janela_regime_minutos)
        regime_gap = dentro_janela_gap and abs(self._gap_ticks) >= self.limiar_gap_ticks

        stop_ticks = self.stop_normal_ticks
        alvo_ticks = self.alvo_normal_ticks
        if regime_gap:
            stop_ticks *= self.fator_ampliacao_gap
            alvo_ticks *= self.fator_ampliacao_gap

        off = self.offset_ticks * self.tick_size
        if bar.close > range_hi_antes:
            self._armou_hoje = True
            reason = "gap_regime_amplo_cima" if regime_gap else "gap_regime_normal_cima"
            return [self._ordem("long", bar.close - off, stop_ticks, alvo_ticks, reason)]
        if bar.close < range_lo_antes:
            self._armou_hoje = True
            reason = "gap_regime_amplo_baixo" if regime_gap else "gap_regime_normal_baixo"
            return [self._ordem("short", bar.close + off, stop_ticks, alvo_ticks, reason)]
        return []

    def _ordem(self, side: str, limite: float, stop_ticks: float, alvo_ticks: float,
               reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=stop_ticks,
            alvo_ticks=alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
