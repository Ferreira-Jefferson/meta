"""Catálogo caos/fractais, item 6: LogisticMapMomentum.

APROXIMAÇÃO HEURÍSTICA: ajusta os retornos normalizados recentes (min-max
para [0,1]) a um passo do mapa logístico x_{n+1} = r·x_n·(1-x_n), estimando
`r` por regressão linear simples de x_{n+1} contra x_n·(1-x_n) — não é
ajuste não-linear real do mapa, só uma projeção linear que devolve um `r`
aproximado. Região de `r` alto (>~3,57, zona caótica de referência) dispara
rompimento de volatilidade com stop largo.
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
class LogisticMapMomentum(IntradayStrategy):
    """Estima `r` de um mapa logístico local via regressão sobre retornos
    normalizados; `r` na zona caótica dispara rompimento com stop largo."""

    name: str = "logistic_map_momentum"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    r_limiar: float = 3.57
    offset_ticks: int = 1
    stop_ticks: int = 24
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=31), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if not positions and len(self._closes) == self._closes.maxlen:
            precos = np.array(self._closes)
            retornos = np.diff(precos)
            rmin, rmax = retornos.min(), retornos.max()
            if rmax - rmin > 1e-9:
                x = (retornos - rmin) / (rmax - rmin)
                x = np.clip(x, 1e-6, 1 - 1e-6)
                x_n, x_n1 = x[:-1], x[1:]
                denom = x_n * (1 - x_n)
                mascara = denom > 1e-6
                if mascara.sum() >= 5:
                    r_est = float(np.sum(x_n1[mascara] * denom[mascara]) / np.sum(denom[mascara] ** 2))
                    if r_est > self.r_limiar:
                        ultimo_retorno = precos[-1] - precos[-2]
                        if ultimo_retorno > 0:
                            limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side="long", limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]
                        elif ultimo_retorno < 0:
                            limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side="short", limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]

        self._closes.append(bar.close)
        return acao
