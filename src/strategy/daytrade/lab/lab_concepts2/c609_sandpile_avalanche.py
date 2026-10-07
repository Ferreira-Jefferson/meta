"""Catálogo caos/fractais, item 10: SandpileAvalanche.

APROXIMAÇÃO HEURÍSTICA do modelo de pilha de areia auto-organizada
criticamente: conta barras consecutivas na mesma direção como "grãos"
empilhados; quando o contador excede um limiar crítico (percentil rolling
das sequências passadas), entende que a "avalanche" está madura e faz fade
do movimento — sem qualquer dinâmica de propagação real do modelo formal.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class SandpileAvalanche(IntradayStrategy):
    """Contador de barras consecutivas na mesma direção ("grãos"); faz fade
    quando ultrapassa o limiar crítico rolling (percentil das sequências
    passadas)."""

    name: str = "sandpile_avalanche"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_sequencias: int = 30
    percentil_critico: float = 85.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _direcao_atual: int = field(default=0, init=False, repr=False)
    _contador: int = field(default=0, init=False, repr=False)
    _sequencias: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._direcao_atual = 0
        self._contador = 0
        self._sequencias = deque(maxlen=self.janela_sequencias)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if len(self._closes) == 2:
            retorno = bar.close - self._closes[-1]
            direcao = 1 if retorno > 0 else (-1 if retorno < 0 else 0)
            if direcao != 0 and direcao == self._direcao_atual:
                self._contador += 1
            elif direcao != 0:
                if self._direcao_atual != 0:
                    self._sequencias.append(self._contador)
                self._direcao_atual = direcao
                self._contador = 1

            if not positions and len(self._sequencias) >= 10 and self._contador >= 2:
                limiar = float(np.percentile(self._sequencias, self.percentil_critico))
                if self._contador >= max(2.0, limiar):
                    if self._direcao_atual > 0:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif self._direcao_atual < 0:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]

        self._closes.append(bar.close)
        return acao
