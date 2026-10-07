"""Variance Ratio: var(retorno de 2 barras) / (2 x var(retorno de 1 barra)),
numa janela N. VR>1 indica persistencia (segue o retorno do ultimo candle);
VR<1 indica reversao (fade contra ele). E' o proxy mais simples de expoente
de Hurst que da' para calcular so' com numpy/pandas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class RazaoVarianciaHurst(IntradayStrategy):
    name: str = "c505_razao_variancia_hurst"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    limiar_persistencia: float = 1.1
    limiar_reversao: float = 0.9
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

        close = self._buffer.close().iloc[-self.janela - 2:]
        ret_1 = close.diff().dropna()
        ret_2 = close.diff(2).dropna()
        var_1 = ret_1.var()
        var_2 = ret_2.var()
        if not var_1 or var_1 <= 0:
            return []
        vr = var_2 / (2.0 * var_1)

        ultimo_delta = close.iloc[-1] - close.iloc[-2]
        if ultimo_delta == 0:
            return []
        off = self.offset_ticks * self.tick_size

        if vr >= self.limiar_persistencia:
            side = "long" if ultimo_delta > 0 else "short"
            limite = bar.close - off if side == "long" else bar.close + off
            self._armou_hoje = True
            return [self._ordem(side, limite, "variance_ratio_persistencia")]
        if vr <= self.limiar_reversao:
            side = "short" if ultimo_delta > 0 else "long"
            limite = bar.close + off if side == "short" else bar.close - off
            self._armou_hoje = True
            return [self._ordem(side, limite, "variance_ratio_reversao")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
