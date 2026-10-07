"""DiferenciacaoFracionariaEstacionaria -- reversao sobre a serie fracdiff.

Aplica diferenciacao fracionaria de ordem fixa `d` (pesos binomiais
generalizados, `w_0=1`, `w_k=w_{k-1}*(d-k+1)/k`, janela de pesos
truncada -- 100% numpy, sem lib) ao preco, produzindo uma serie mais
proxima de estacionaria que preserva mais memoria de longo prazo que a
diferenca inteira (`d=1`). Opera REVERSAO sobre essa serie: entra contra
desvios extremos (z-score da propria fracdiff contra sua media/desvio
rolante); sai no retorno a media (z cruza zero) ou pelo stop/alvo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def _pesos_fracdiff(d: float, tamanho: int) -> np.ndarray:
    pesos = [1.0]
    for k in range(1, tamanho):
        pesos.append(pesos[-1] * (d - k + 1) / k)
    return np.array(pesos)


@dataclass
class DiferenciacaoFracionariaEstacionaria(IntradayStrategy):
    """Reversao a media sobre a serie de precos diferenciada fracionariamente."""

    name: str = "c421_diferenciacao_fracionaria_estacionaria"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    d_ordem: float = 0.4
    janela_pesos: int = 50
    janela_zscore: int = 40
    limiar_z: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _pesos: np.ndarray = field(default=None, init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=50), init=False, repr=False)
    _fracdiff: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)

    def __post_init__(self) -> None:
        self._pesos = _pesos_fracdiff(self.d_ordem, self.janela_pesos)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_pesos)
        self._fracdiff = deque(maxlen=self.janela_zscore)

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

        z = None
        if len(self._closes) == self.janela_pesos:
            # precos do mais recente para o mais antigo, pareados com os pesos
            precos = np.array(list(reversed(self._closes)))
            valor = float(np.dot(self._pesos, precos))
            self._fracdiff.append(valor)
            if len(self._fracdiff) == self.janela_zscore:
                arr = np.array(self._fracdiff)
                std = arr.std(ddof=0)
                if std > 1e-9:
                    z = float((arr[-1] - arr.mean()) / std)

        if positions:
            if z is not None:
                pos = positions[0]
                if pos.side == "short" and z <= 0.0:
                    return [Exit(reason=f"{self.name}_zero_cross")]
                if pos.side == "long" and z >= 0.0:
                    return [Exit(reason=f"{self.name}_zero_cross")]
            return []

        if z is None:
            return []
        tick = self.tick_size
        if z >= self.limiar_z:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if z <= -self.limiar_z:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
