"""Conta topos/fundos (pivos locais, confirmados com defasagem de 2 barras) e
classifica a sequencia: 3 topos ascendentes + 3 fundos ascendentes (HH+HL) e'
regime direcional de ALTA; 3 topos descendentes + 3 fundos descendentes
(LH+LL) e' de BAIXA -- qualquer mistura nao opera (sem sequencia consistente).
Entra no rompimento do ultimo pivo na direcao confirmada.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada

#: defasagem (em barras) para confirmar um pivo -- precisa de `lag` barras
#: dos dois lados mais baixas/altas que o candidato, entao so' e' confirmado
#: `lag` barras DEPOIS dele (sem look-ahead: a confirmacao usa barras ja
#: fechadas, nunca a barra corrente).
_LAG_PIVO = 2


@dataclass
class ContagemTopoFundo(IntradayStrategy):
    name: str = "c504_contagem_topo_fundo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    pivos_exigidos: int = 3
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(120), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._armou_hoje = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def _pivos(self) -> tuple[list[float], list[float]]:
        highs = self._buffer.high().tolist()
        lows = self._buffer.low().tolist()
        n = len(highs)
        topos: list[float] = []
        fundos: list[float] = []
        for i in range(_LAG_PIVO, n - _LAG_PIVO):
            janela_h = highs[i - _LAG_PIVO:i + _LAG_PIVO + 1]
            if highs[i] == max(janela_h) and janela_h.count(highs[i]) == 1:
                topos.append(highs[i])
            janela_l = lows[i - _LAG_PIVO:i + _LAG_PIVO + 1]
            if lows[i] == min(janela_l) and janela_l.count(lows[i]) == 1:
                fundos.append(lows[i])
        return topos, fundos

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._buffer.push(bar)
        if positions or self._armou_hoje:
            return []
        if len(self._buffer) < 40:
            return []

        topos, fundos = self._pivos()
        k = self.pivos_exigidos
        if len(topos) < k or len(fundos) < k:
            return []

        ultimos_topos = topos[-k:]
        ultimos_fundos = fundos[-k:]
        ascendente = (all(ultimos_topos[i] < ultimos_topos[i + 1] for i in range(k - 1))
                      and all(ultimos_fundos[i] < ultimos_fundos[i + 1] for i in range(k - 1)))
        descendente = (all(ultimos_topos[i] > ultimos_topos[i + 1] for i in range(k - 1))
                       and all(ultimos_fundos[i] > ultimos_fundos[i + 1] for i in range(k - 1)))

        off = self.offset_ticks * self.tick_size
        if ascendente and bar.close > ultimos_topos[-1]:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "topo_fundo_hh_hl")]
        if descendente and bar.close < ultimos_fundos[-1]:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "topo_fundo_lh_ll")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
