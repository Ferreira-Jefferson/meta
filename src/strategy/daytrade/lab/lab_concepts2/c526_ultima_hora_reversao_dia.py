"""Na ultima hora do pregao, se o dia ja' teve uma tendencia FORTE (retorno
acumulado desde a abertura acima de um limiar), procura uma reversao PARCIAL
(fade contra o movimento do dia) em vez de seguir -- dia que andou muito tende
a devolver parte do caminho perto do fechamento.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class UltimaHoraReversaoDia(IntradayStrategy):
    name: str = "c526_ultima_hora_reversao_dia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_ultima_hora_minutos: float = 60.0
    fim_pregao_horas: float = 18.0
    movimento_minimo_ticks: float = 40.0
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 15  # reversao parcial, alvo curto -- ainda acima do piso
    entrada_ttl_bars: int = 20
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
        if minutos_ate_fechar > self.janela_ultima_hora_minutos or minutos_ate_fechar <= 0:
            return []

        movimento_ticks = (bar.close - self._open_price) / self.tick_size
        if abs(movimento_ticks) < self.movimento_minimo_ticks:
            return []  # dia sem tendencia forte -- nao ha' o que reverter

        off = self.offset_ticks * self.tick_size
        # fade CONTRA o movimento do dia
        side = "short" if movimento_ticks > 0 else "long"
        limite = bar.close + off if side == "short" else bar.close - off
        self._armou_hoje = True
        return [self._ordem(side, limite, "ultima_hora_reversao_parcial")]

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
