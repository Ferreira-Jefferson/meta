"""Catalogo calendario/sazonalidade, item 27: QuartaAlmocoBreakoutExclusivo.

Conceito de CALENDARIO combinado: janela de almoco (12:00-13:30, fixa)
E dia-da-semana quarta-feira (`ts.dayofweek == 2`) -- so' entra quando as
DUAS condicoes valem no mesmo pregao. Rompimento da mini-faixa formada no
proprio intervalo de almoco (mesmo mecanismo de
`AlmocoBreakoutSilencioso`), alvo 1x a faixa.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    FIM_ALMOCO, INICIO_ALMOCO, montar_entrada,
)

_QUARTA_FEIRA = 2


@dataclass
class QuartaAlmocoBreakoutExclusivo(IntradayStrategy):
    name: str = "quarta_almoco_breakout_exclusivo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 10
    entrada_ttl_bars: int = 30

    _e_quarta: bool = field(default=False, init=False, repr=False)
    _faixa_high: float | None = field(default=None, init=False, repr=False)
    _faixa_low: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._e_quarta = session_date.weekday() == _QUARTA_FEIRA
        self._faixa_high = None
        self._faixa_low = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_quarta or ts.time() < INICIO_ALMOCO or ts.time() >= FIM_ALMOCO:
            return []

        acao: list[IntradayAction] = []
        if self._faixa_high is None:
            self._faixa_high, self._faixa_low = bar.high, bar.low
            return acao

        if not positions and not self._entrou_hoje:
            largura = self._faixa_high - self._faixa_low
            alvo_ticks = largura / self.tick_size if largura > 0 else 0.0
            if bar.close > self._faixa_high:
                acao = [montar_entrada(
                    side="long", limit_price=bar.close, stop_ticks=self.stop_ticks,
                    alvo_ticks=alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
                self._entrou_hoje = True
            elif bar.close < self._faixa_low:
                acao = [montar_entrada(
                    side="short", limit_price=bar.close, stop_ticks=self.stop_ticks,
                    alvo_ticks=alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
                self._entrou_hoje = True

        self._faixa_high = max(self._faixa_high, bar.high)
        self._faixa_low = min(self._faixa_low, bar.low)
        return acao
