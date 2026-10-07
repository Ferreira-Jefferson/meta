"""Conta INSIDE BARS consecutivas (cada barra nova contida no range da
anterior). A partir de 2+ seguidas, entra no rompimento da faixa comprimida
resultante -- a ultima (e mais estreita) barra da sequencia.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class InsideBarSequencial(IntradayStrategy):
    name: str = "c529_inside_bar_sequencial"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    minimo_inside: int = 2
    alvo_multiplo: float = 2.0
    offset_ticks: int = 2
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(30), init=False, repr=False)
    _contagem_inside: int = field(default=0, init=False, repr=False)
    _faixa_hi: float | None = field(default=None, init=False, repr=False)
    _faixa_lo: float | None = field(default=None, init=False, repr=False)
    _prev_high: float | None = field(default=None, init=False, repr=False)
    _prev_low: float | None = field(default=None, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._contagem_inside = 0
        self._faixa_hi = None
        self._faixa_lo = None
        self._prev_high = None
        self._prev_low = None
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

        # 1) checa rompimento com o estado ACUMULADO ate' a barra anterior
        #    (a barra corrente nunca contamina a faixa que ela mesma rompe)
        if (not positions and not self._armou_hoje
                and self._contagem_inside >= self.minimo_inside
                and self._faixa_hi is not None and self._faixa_lo is not None):
            off = self.offset_ticks * self.tick_size
            stop_ticks = (self._faixa_hi - self._faixa_lo) / self.tick_size
            alvo_ticks = stop_ticks * self.alvo_multiplo
            if bar.close > self._faixa_hi:
                self._armou_hoje = True
                acao = [self._ordem("long", bar.close - off, stop_ticks, alvo_ticks,
                                    "inside_bar_rompe_cima")]
                self._atualizar_sequencia(bar)
                return acao
            if bar.close < self._faixa_lo:
                self._armou_hoje = True
                acao = [self._ordem("short", bar.close + off, stop_ticks, alvo_ticks,
                                    "inside_bar_rompe_baixo")]
                self._atualizar_sequencia(bar)
                return acao

        self._atualizar_sequencia(bar)
        return []

    def _atualizar_sequencia(self, bar: Bar) -> None:
        """Atualiza a contagem de inside bars USANDO a barra corrente contra
        a barra ANTERIOR -- chamado uma vez por barra, depois de qualquer
        decisao de entrada ja' ter usado o estado antigo."""
        if self._prev_high is not None and bar.high <= self._prev_high and bar.low >= self._prev_low:
            self._contagem_inside += 1
        else:
            self._contagem_inside = 0
        # a faixa comprimida e' sempre a barra mais recente (por construcao,
        # ela esta' contida em todas as anteriores da sequencia)
        self._faixa_hi = bar.high
        self._faixa_lo = bar.low
        self._prev_high = bar.high
        self._prev_low = bar.low

    def _ordem(self, side: str, limite: float, stop_ticks: float, alvo_ticks: float,
               reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=max(stop_ticks, 1.0),
            alvo_ticks=alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
