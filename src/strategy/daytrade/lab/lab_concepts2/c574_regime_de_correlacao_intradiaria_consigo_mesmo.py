"""Catálogo regime/adaptação, item 75: RegimeDeCorrelacaoIntradiariaConsigoMesmo.

Autocorrelação móvel (numpy.corrcoef) entre o retorno do minuto atual e o
de `lag` minutos atrás; regime de "ciclo" confirmado quando a correlação
fica consistentemente alta por `m_confirmacao` barras -- a entrada
antecipa REPETIÇÃO do retorno observado `lag` barras atrás.
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
class RegimeDeCorrelacaoIntradiariaConsigoMesmo(IntradayStrategy):
    """Autocorrelação móvel entre o retorno atual e o de `lag` barras
    atrás; regime de "ciclo" confirmado por `m_confirmacao` barras
    consecutivas de correlação >= `limiar_correlacao` antecipa a
    REPETIÇÃO do retorno de `lag` barras atrás."""

    name: str = "regime_de_correlacao_intradiaria_consigo_mesmo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    lag: int = 5
    janela_correlacao: int = 30
    limiar_correlacao: float = 0.3
    m_confirmacao: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _contagem_ciclo: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_correlacao + self.lag + 1)
        self._contagem_ciclo = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes.append(bar.close)

        if len(self._closes) == self._closes.maxlen:
            valores = np.array(self._closes, dtype=float)
            retornos = np.diff(valores)
            serie_atual = retornos[self.lag:]
            serie_defasada = retornos[:-self.lag]
            if len(serie_atual) >= 2 and np.std(serie_atual) > 0 and np.std(serie_defasada) > 0:
                correlacao = float(np.corrcoef(serie_atual, serie_defasada)[0, 1])
            else:
                correlacao = 0.0

            if correlacao >= self.limiar_correlacao:
                self._contagem_ciclo += 1
            else:
                self._contagem_ciclo = 0

            if not positions and self._contagem_ciclo >= self.m_confirmacao:
                retorno_defasado = float(retornos[-self.lag])
                if retorno_defasado > 0:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif retorno_defasado < 0:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        return acao
