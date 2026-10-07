"""Catalogo calendario/sazonalidade, item 26: PosVencimentoNormalizacao.

Conceito de CALENDARIO: primeiro pregao do mes seguinte ao "vencimento"
aproximado -- que e' exatamente o PRIMEIRO pregao do mes
(`month_boundaries`, precomputado em `initialize`, mesma data de
`ViradaDeMesCompra`/`Venda`, mas aqui o mecanismo e' rompimento de
abertura PADRAO com STOP MAIS LARGO que o normal, so' por este 1 dia --
a hipotese e' que a rolagem de vencimento produz ruido extra que um stop
normal (16 ticks) cortaria cedo demais).
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    month_boundaries, montar_entrada, trading_dates,
)

_FIM_FAIXA_ABERTURA = time(9, 30)


@dataclass
class PosVencimentoNormalizacao(IntradayStrategy):
    name: str = "pos_vencimento_normalizacao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks_largo: int = 28  # normal desta familia seria 16
    alvo_ticks: int = 14
    entrada_ttl_bars: int = 40

    _primeiros_do_mes: set = field(default_factory=set, init=False, repr=False)
    _e_pos_vencimento: bool = field(default=False, init=False, repr=False)
    _faixa_high: float | None = field(default=None, init=False, repr=False)
    _faixa_low: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        primeiros, _ = month_boundaries(trading_dates(bars))
        self._primeiros_do_mes = primeiros

    def on_session_start(self, session_date) -> None:
        self._e_pos_vencimento = session_date in self._primeiros_do_mes
        self._faixa_high = None
        self._faixa_low = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_pos_vencimento:
            return []

        if ts.time() < _FIM_FAIXA_ABERTURA:
            if self._faixa_high is None:
                self._faixa_high, self._faixa_low = bar.high, bar.low
            else:
                self._faixa_high = max(self._faixa_high, bar.high)
                self._faixa_low = min(self._faixa_low, bar.low)
            return []

        if positions or self._entrou_hoje or self._faixa_high is None:
            return []

        if bar.close > self._faixa_high:
            self._entrou_hoje = True
            return [montar_entrada(
                side="long", limit_price=bar.close, stop_ticks=self.stop_ticks_largo,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        if bar.close < self._faixa_low:
            self._entrou_hoje = True
            return [montar_entrada(
                side="short", limit_price=bar.close, stop_ticks=self.stop_ticks_largo,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
