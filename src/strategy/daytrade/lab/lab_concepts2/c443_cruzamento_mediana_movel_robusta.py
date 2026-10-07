"""Item 44 do catalogo: mediana movel (nao media) como referencia central.

Opera o CRUZAMENTO do preco com a mediana movel -- entra na direcao do
cruzamento (seguimento de tendencia); sai no cruzamento reverso.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class CruzamentoMedianaMovelRobusta(IntradayStrategy):
    """Cruzamento do preco com a mediana movel -- seguimento de tendencia."""

    name: str = "c443_cruzamento_mediana_movel_robusta"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _rel_anterior: int | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)
        self._rel_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) < self.janela:
            return []
        mediana = float(np.median(self._closes))
        rel = 1 if bar.close > mediana else (-1 if bar.close < mediana else 0)
        anterior = self._rel_anterior
        self._rel_anterior = rel

        if positions:
            pos = positions[0]
            if pos.side == "long" and rel < 0:
                return [Exit(reason="cruzou_abaixo_da_mediana")]
            if pos.side == "short" and rel > 0:
                return [Exit(reason="cruzou_acima_da_mediana")]
            return []

        if anterior is None or rel == 0:
            return []
        if anterior <= 0 and rel > 0:
            return [self._ordem("long", bar.close, "cruzou_acima_da_mediana")]
        if anterior >= 0 and rel < 0:
            return [self._ordem("short", bar.close, "cruzou_abaixo_da_mediana")]
        return []

    def _ordem(self, side: str, preco_ref: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(preco_ref, self.tick_size)
        stop = no_tick(limite - sinal * self.stop_ticks * self.tick_size, self.tick_size)
        alvo = no_tick(limite + sinal * self.alvo_ticks * self.tick_size, self.tick_size)
        return EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=reason,
        )
