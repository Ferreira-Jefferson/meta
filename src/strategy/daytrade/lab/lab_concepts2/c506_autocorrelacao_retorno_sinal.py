"""Autocorrelacao lag-1 dos retornos (np.corrcoef) numa janela movel: positiva
segue o ultimo candle (retornos tendem a se repetir); negativa entra contra
ele (retornos tendem a se cancelar).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class AutocorrelacaoRetornoSinal(IntradayStrategy):
    name: str = "c506_autocorrelacao_retorno_sinal"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    limiar_autocorr: float = 0.15
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
        if len(self._buffer) < self.janela + 2:
            return []

        close = self._buffer.close().iloc[-self.janela - 1:]
        ret = close.diff().dropna().to_numpy()
        if len(ret) < 3 or ret[:-1].std() == 0 or ret[1:].std() == 0:
            return []
        autocorr = np.corrcoef(ret[:-1], ret[1:])[0, 1]
        if pd.isna(autocorr):
            return []

        ultimo_delta = ret[-1]
        if ultimo_delta == 0:
            return []
        off = self.offset_ticks * self.tick_size

        if autocorr >= self.limiar_autocorr:
            side = "long" if ultimo_delta > 0 else "short"
            limite = bar.close - off if side == "long" else bar.close + off
            self._armou_hoje = True
            return [self._ordem(side, limite, "autocorr_positiva_segue")]
        if autocorr <= -self.limiar_autocorr:
            side = "short" if ultimo_delta > 0 else "long"
            limite = bar.close + off if side == "short" else bar.close - off
            self._armou_hoje = True
            return [self._ordem(side, limite, "autocorr_negativa_reverte")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
