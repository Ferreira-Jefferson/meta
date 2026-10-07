"""Rompimento simples de range, mas o TAMANHO da posicao e' escalado pelo
INVERSO do ATR normalizado (volatility targeting): ATR alto reduz o numero de
contratos, ATR baixo aumenta -- dentro do teto 1-5. O gatilho e' generico; o
mecanismo desta estrategia e' o SIZING.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from core.indicators import atr
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, clamp_quantity, montar_entrada


@dataclass
class TamanhoPosicaoInversoAtr(IntradayStrategy):
    name: str = "c511_tamanho_posicao_inverso_atr"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_atr: int = 14
    janela_range: int = 20
    #: ATR "de referencia" (mediana historica) -- acima disto reduz o
    #: tamanho, abaixo aumenta. `ratio = atr_referencia / atr_atual`.
    janela_referencia: int = 100
    teto_quantidade: int = 5
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(150), init=False, repr=False)
    _historico_atr: deque = field(
        default_factory=lambda: deque(maxlen=200), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._historico_atr = deque(maxlen=self.janela_referencia)

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
        minimo = max(self.janela_atr, self.janela_range) + 1
        if len(self._buffer) < minimo:
            return []

        high, low, close = self._buffer.high(), self._buffer.low(), self._buffer.close()
        atr_atual = atr(high, low, close, self.janela_atr).iloc[-1]
        if pd.isna(atr_atual) or atr_atual <= 0:
            return []
        self._historico_atr.append(atr_atual)

        if positions or self._armou_hoje:
            return []
        if len(self._historico_atr) < 20:
            return []

        atr_referencia = pd.Series(self._historico_atr).median()
        ratio = atr_referencia / atr_atual if atr_atual > 0 else 1.0
        qty = clamp_quantity(ratio, minimo=1, teto=self.teto_quantidade)

        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, qty, "inverso_atr_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, qty, "inverso_atr_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, qty: int, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=qty, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
