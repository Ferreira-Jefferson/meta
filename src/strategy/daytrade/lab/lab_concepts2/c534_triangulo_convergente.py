"""Topos DESCENDENTES + fundos ASCENDENTES simultaneos (pivos locais,
confirmados com defasagem) caracterizam um TRIANGULO convergente -- opera o
rompimento de QUALQUER um dos dois lados da faixa que ainda resta entre eles.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada

_LAG_PIVO = 2


@dataclass
class TrianguloConvergente(IntradayStrategy):
    name: str = "c534_triangulo_convergente"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    pivos_exigidos: int = 2
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
        topos_descendo = all(ultimos_topos[i] > ultimos_topos[i + 1] for i in range(k - 1))
        fundos_subindo = all(ultimos_fundos[i] < ultimos_fundos[i + 1] for i in range(k - 1))
        if not (topos_descendo and fundos_subindo):
            return []  # nao e' convergencia -- os dois lados tem de fechar juntos

        teto = ultimos_topos[-1]
        piso = ultimos_fundos[-1]
        if piso >= teto:
            return []  # ja convergiu (ou dado ruim) -- nao ha' faixa para romper

        off = self.offset_ticks * self.tick_size
        if bar.close > teto:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "triangulo_rompe_topo")]
        if bar.close < piso:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "triangulo_rompe_fundo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
