"""Conta ha' quantas barras nao se faz uma nova maxima/minima de N periodos
(`core.indicators.days_since_last_true` aplicada a um evento por-barra, nao
por-dia -- o nome da funcao e' generico o bastante). Contagem alta = mais
tempo comprimido -- reduz o alvo (piso de 4 ticks) e aumenta a sensibilidade
do rompimento (offset menor).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import days_since_last_true, rolling_high, rolling_low
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class ContagemBarrasSemNovaMaxima(IntradayStrategy):
    name: str = "c533_contagem_barras_sem_nova_maxima"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_referencia: int = 20
    contagem_alta: int = 15
    alvo_ticks_base: int = 30
    offset_ticks_base: int = 3
    stop_ticks: int = 20
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
        if len(self._buffer) < self.janela_referencia + 2:
            return []

        high, low = self._buffer.high(), self._buffer.low()
        topo_rolante = rolling_high(high, self.janela_referencia).shift(1)
        fundo_rolante = rolling_low(low, self.janela_referencia).shift(1)
        nova_maxima = high > topo_rolante
        nova_minima = low < fundo_rolante
        contagem_max = int(days_since_last_true(nova_maxima).iloc[-1])
        contagem_min = int(days_since_last_true(nova_minima).iloc[-1])
        contagem = min(c for c in (contagem_max, contagem_min) if c >= 0) \
            if (contagem_max >= 0 or contagem_min >= 0) else -1

        if positions or self._armou_hoje:
            return []
        if contagem < 0:
            return []

        comprimido = contagem >= self.contagem_alta
        # quanto mais comprimido, menor o offset (mais sensivel) e menor o
        # alvo (piso de 4 ticks aplicado dentro de `montar_entrada`)
        fator = min(1.0, contagem / max(1, self.contagem_alta))
        offset_ticks = max(1, round(self.offset_ticks_base * (1.0 - 0.5 * fator)))
        alvo_ticks = self.alvo_ticks_base * (1.0 - 0.5 * fator) if comprimido else self.alvo_ticks_base
        off = offset_ticks * self.tick_size

        faixa_hi = high.iloc[-self.janela_referencia - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_referencia - 1:-1].min()

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, alvo_ticks, "compressao_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, alvo_ticks, "compressao_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, alvo_ticks: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
