"""Nos ultimos N minutos do pregao, momentum PURO na direcao do movimento
liquido do dia (close atual vs abertura da sessao) -- ignora qualquer sinal
de curto prazo, so' pergunta "o dia subiu ou desceu" e segue.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class JanelaFechamentoMomentum(IntradayStrategy):
    name: str = "c522_janela_fechamento_momentum"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_final_minutos: float = 30.0
    #: fim nominal do pregao regular do WDO@ (BRT) -- so' delimita a janela,
    #: o achatamento de fim de pregao continua sendo o motor quem decide.
    fim_pregao_horas: float = 18.0
    movimento_minimo_ticks: float = 4.0
    offset_ticks: int = 2
    stop_ticks: int = 15
    alvo_ticks: int = 20
    entrada_ttl_bars: int = 15
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(30), init=False, repr=False)
    _open_price: float | None = field(default=None, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._open_price = None
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
        if self._open_price is None:
            self._open_price = bar.open

        if positions or self._armou_hoje:
            return []

        minutos_ate_fechar = (self.fim_pregao_horas * 60.0) - (ts.hour * 60.0 + ts.minute)
        if minutos_ate_fechar > self.janela_final_minutos or minutos_ate_fechar <= 0:
            return []  # so' opera dentro da janela final

        movimento_ticks = (bar.close - self._open_price) / self.tick_size
        if abs(movimento_ticks) < self.movimento_minimo_ticks:
            return []

        off = self.offset_ticks * self.tick_size
        side = "long" if movimento_ticks > 0 else "short"
        limite = bar.close - off if side == "long" else bar.close + off
        self._armou_hoje = True
        return [self._ordem(side, limite, "fechamento_momentum_do_dia")]

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
