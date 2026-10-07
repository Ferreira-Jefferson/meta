"""Identifica a barra de MENOR range (high-low) das ultimas 7 completas
(Narrow Range 7) e entra no rompimento dela na barra seguinte -- stop no
proprio extremo oposto da NR7 (o range dela e' a geometria, nao um numero
fixo).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class Nr7Rompimento(IntradayStrategy):
    name: str = "c528_nr7_rompimento"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_nr: int = 7
    alvo_multiplo: float = 2.0
    offset_ticks: int = 2
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(30), init=False, repr=False)
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
        if len(self._buffer) < self.janela_nr + 2:
            return []

        high, low = self._buffer.high(), self._buffer.low()
        # candidatas: as `janela_nr` barras ANTES desta (nunca a corrente)
        cand_hi = high.iloc[-self.janela_nr - 1:-1]
        cand_lo = low.iloc[-self.janela_nr - 1:-1]
        ranges = cand_hi - cand_lo
        pos_nr7 = int(ranges.to_numpy().argmin())
        nr7_hi = float(cand_hi.iloc[pos_nr7])
        nr7_lo = float(cand_lo.iloc[pos_nr7])
        stop_ticks_long = (nr7_hi - nr7_lo) / self.tick_size  # distancia ao extremo oposto
        off = self.offset_ticks * self.tick_size

        if bar.close > nr7_hi:
            limite = bar.close - off
            stop_ticks = (limite - nr7_lo) / self.tick_size
            alvo_ticks = stop_ticks * self.alvo_multiplo
            self._armou_hoje = True
            return [self._ordem("long", limite, stop_ticks, alvo_ticks, "nr7_rompe_cima")]
        if bar.close < nr7_lo:
            limite = bar.close + off
            stop_ticks = (nr7_hi - limite) / self.tick_size
            alvo_ticks = stop_ticks * self.alvo_multiplo
            self._armou_hoje = True
            return [self._ordem("short", limite, stop_ticks, alvo_ticks, "nr7_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, stop_ticks: float, alvo_ticks: float,
               reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=max(stop_ticks, 1.0),
            alvo_ticks=alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
