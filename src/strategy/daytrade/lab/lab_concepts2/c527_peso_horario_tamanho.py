"""Rompimento de range simples, mas o TAMANHO da posicao e' escalado por um
fator horario FIXO (maior na abertura/fechamento, menor no almoco) --
independente de qualquer outro sinal de mercado. O mecanismo desta estrategia
e' o CALENDARIO de tamanho, nao o gatilho.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, clamp_quantity, montar_entrada


@dataclass
class PesoHorarioTamanho(IntradayStrategy):
    name: str = "c527_peso_horario_tamanho"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    quantidade_base: int = 3
    teto_quantidade: int = 5
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._armou_hoje = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def _fator_horario(self, hora: int) -> float:
        """Peso FIXO por hora do dia (BRT): abertura e fechamento pesam mais,
        almoco pesa menos -- tabela declarada, nao calculada."""
        if 9 <= hora < 10:
            return 1.5   # abertura
        if 12 <= hora < 14:
            return 0.4   # almoco
        if 17 <= hora < 18:
            return 1.3   # fechamento
        return 1.0       # resto do pregao

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._buffer.push(bar)
        if positions or self._armou_hoje:
            return []
        if len(self._buffer) < self.janela_range + 1:
            return []

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size
        qty = clamp_quantity(self.quantidade_base * self._fator_horario(ts.hour),
                              minimo=1, teto=self.teto_quantidade)

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, qty, "peso_horario_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, qty, "peso_horario_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, qty: int, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=qty, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
