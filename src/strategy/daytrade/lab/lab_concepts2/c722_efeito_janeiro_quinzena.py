"""Catalogo calendario/sazonalidade, item 23: EfeitoJaneiroQuinzena.

Conceito de CALENDARIO: primeiras duas semanas de janeiro
(`ts.month == 1 and ts.day <= 14`, regra direta sobre a data). Vies
comprado sistematico em pullback ate a media movel da sessao; desliga
(nao entra mais) apos o dia 14, mesmo mecanismo de
`PrimeiraQuinzenaVieDeCompra` mas restrito a JANEIRO.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import montar_entrada


@dataclass
class EfeitoJaneiroQuinzena(IntradayStrategy):
    name: str = "efeito_janeiro_quinzena"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_ma: int = 20
    pullback_ticks: float = 6.0
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30

    _ativo: bool = field(default=False, init=False, repr=False)
    _closes: deque = field(default_factory=deque, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ativo = session_date.month == 1 and session_date.day <= 14
        self._closes = deque(maxlen=self.janela_ma)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._ativo and not positions and len(self._closes) == self._closes.maxlen:
            media = sum(self._closes) / len(self._closes)
            if bar.close < media - self.pullback_ticks * self.tick_size:
                acao = [montar_entrada(
                    side="long", limit_price=bar.close, stop_ticks=self.stop_ticks,
                    alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
        self._closes.append(bar.close)
        return acao
