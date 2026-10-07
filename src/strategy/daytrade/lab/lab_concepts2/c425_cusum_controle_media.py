"""CUSUMControleMedia -- soma cumulativa (CUSUM) de desvios da media dos retornos.

CUSUM de duas caudas classico (controle estatistico de processo):
`S+ = max(0, S+ + r - k)`, `S- = max(0, S- - r - k)`, com folga `k` e
barreira de decisao `h` escalados pelo desvio-padrao rolante dos
retornos. Cruzar a barreira detecta uma MUDANCA de media -- entra na
DIRECAO do desvio (momentum: um S+ que estoura indica deslocamento para
cima) e zera a soma correspondente. Sai quando aquela MESMA soma volta a
zerar sozinha (o deslocamento se dissipou) ou pelo stop/alvo.
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


@dataclass
class CUSUMControleMedia(IntradayStrategy):
    """CUSUM de duas caudas sobre os retornos; entra no cruzamento da barreira."""

    name: str = "c425_cusum_controle_media"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_std: int = 40
    k_folga_desvios: float = 0.5
    h_barreira_desvios: float = 5.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _s_pos: float = field(default=0.0, init=False, repr=False)
    _s_neg: float = field(default=0.0, init=False, repr=False)
    _lado_ativo: str | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela_std)
        self._s_pos = 0.0
        self._s_neg = 0.0
        self._lado_ativo = None

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
        r = None
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        std = None
        if len(self._retornos) == self.janela_std:
            std = float(np.std(self._retornos, ddof=0))

        cruzou_pos = cruzou_neg = False
        if r is not None and std is not None and std > 1e-12:
            k = self.k_folga_desvios * std
            h = self.h_barreira_desvios * std
            self._s_pos = max(0.0, self._s_pos + r - k)
            self._s_neg = max(0.0, self._s_neg - r - k)
            if self._s_pos > h:
                cruzou_pos = True
                self._s_pos = 0.0
            if self._s_neg > h:
                cruzou_neg = True
                self._s_neg = 0.0

        if positions:
            if self._lado_ativo == "pos" and self._s_pos == 0.0:
                self._lado_ativo = None
                return [Exit(reason=f"{self.name}_dissipou")]
            if self._lado_ativo == "neg" and self._s_neg == 0.0:
                self._lado_ativo = None
                return [Exit(reason=f"{self.name}_dissipou")]
            return []

        tick = self.tick_size
        if cruzou_pos:
            self._lado_ativo = "pos"
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if cruzou_neg:
            self._lado_ativo = "neg"
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
