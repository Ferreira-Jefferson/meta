"""TesteSequenciasWaldWolfowitz -- runs-test sobre o sinal dos retornos.

Conta o numero de runs (trocas de sinal) na sequencia de sinais dos
retornos numa janela movel e compara ao numero ESPERADO sob
aleatoriedade -- `E[runs]` e `Var[runs]` tem formula fechada em funcao de
`n+`/`n-` (sem precisar de `scipy.stats`), e o z-score resultante e'
comparado a um limiar direto (aproximacao normal, sem tabela critica
formal). POUCOS runs (z muito negativo) indica persistencia -- segue a
tendencia (direcao da ultima barra). MUITOS runs (z alto) indica
alternancia excessiva -- opera reversao (contra a ultima barra).
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


def _runs_zscore(sinais: np.ndarray) -> float | None:
    n_mais = int(np.sum(sinais > 0))
    n_menos = int(np.sum(sinais < 0))
    n = n_mais + n_menos
    if n_mais == 0 or n_menos == 0 or n < 4:
        return None
    runs = 1
    validos = sinais[sinais != 0]
    for i in range(1, len(validos)):
        if validos[i] != validos[i - 1]:
            runs += 1
    e_runs = 1.0 + (2.0 * n_mais * n_menos) / n
    var_runs = (2.0 * n_mais * n_menos * (2.0 * n_mais * n_menos - n)) / (n * n * (n - 1))
    if var_runs <= 1e-9:
        return None
    return float((runs - e_runs) / np.sqrt(var_runs))


@dataclass
class TesteSequenciasWaldWolfowitz(IntradayStrategy):
    """Runs-test sobre o sinal dos retornos: poucos runs segue, muitos reverte."""

    name: str = "c415_teste_sequencias_wald_wolfowitz"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    limiar_z: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _sinais: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._sinais = deque(maxlen=self.janela)

    def _entrada(self, side: str, limite: float, stop_dist: float, alvo_dist: float) -> list[IntradayAction]:
        tick = self.tick_size
        limite = no_tick(limite, tick)
        if side == "long":
            stop = no_tick(limite - stop_dist, tick)
            alvo = no_tick(limite + alvo_dist, tick)
        else:
            stop = no_tick(limite + stop_dist, tick)
            alvo = no_tick(limite - alvo_dist, tick)
        return [EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            delta = self._closes[-1] - self._closes[-2]
            self._sinais.append(1 if delta > 0 else (-1 if delta < 0 else 0))

        if positions:
            return []

        if len(self._sinais) < self.janela:
            return []
        z = _runs_zscore(np.array(self._sinais))
        if z is None or self._sinais[-1] == 0:
            return []

        ultimo = self._sinais[-1]
        tick = self.tick_size
        if z <= -self.limiar_z:
            # poucos runs -> persistencia -> segue a ultima barra
            if ultimo > 0:
                return self._entrada("long", bar.close - self.offset_ticks * tick,
                                      self.stop_ticks * tick, self.alvo_ticks * tick)
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if z >= self.limiar_z:
            # muitos runs -> alternancia excessiva -> opera contra a ultima barra
            if ultimo > 0:
                return self._entrada("short", bar.close + self.offset_ticks * tick,
                                      self.stop_ticks * tick, self.alvo_ticks * tick)
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
