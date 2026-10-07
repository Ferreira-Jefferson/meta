"""RunLengthSinaisConsecutivos -- reversao quando o run-length bate um recorde.

Mede o comprimento (run-length) corrente de barras fechando na MESMA
direcao e compara contra a distribuicao empirica historica de
run-lengths ja completados nesta sessao (percentil 95, `numpy.percentile`
sem lib de teste formal). Quando o run atual excede esse percentil,
entra CONTRA o movimento (reversao). Sai no primeiro fechamento que
RETOMA a direcao original do run (o sinal de reversao falhou cedo -- sai
antes do stop), ou pelo stop/alvo normais.
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
class RunLengthSinaisConsecutivos(IntradayStrategy):
    """Reversao contra runs de fechamentos consecutivos na mesma direcao."""

    name: str = "c414_run_length_sinais_consecutivos"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    percentil_gatilho: float = 95.0
    min_runs_historico: int = 15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ultimo_close: float | None = field(default=None, init=False, repr=False)
    _direcao_atual: int = field(default=0, init=False, repr=False)
    _run_len: int = field(default=0, init=False, repr=False)
    _historico_runs: deque = field(default_factory=lambda: deque(maxlen=200), init=False, repr=False)
    _direcao_run_ativo: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ultimo_close = None
        self._direcao_atual = 0
        self._run_len = 0
        self._historico_runs = deque(maxlen=200)
        self._direcao_run_ativo = 0

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
        direcao_barra = 0
        if self._ultimo_close is not None:
            if bar.close > self._ultimo_close:
                direcao_barra = 1
            elif bar.close < self._ultimo_close:
                direcao_barra = -1
        self._ultimo_close = bar.close

        if direcao_barra != 0:
            if direcao_barra == self._direcao_atual:
                self._run_len += 1
            else:
                if self._direcao_atual != 0 and self._run_len > 0:
                    self._historico_runs.append(self._run_len)
                self._direcao_atual = direcao_barra
                self._run_len = 1

        if positions:
            pos = positions[0]
            if direcao_barra != 0 and direcao_barra == self._direcao_run_ativo:
                return [Exit(reason=f"{self.name}_tendencia_retomou")]
            return []

        if len(self._historico_runs) < self.min_runs_historico or self._direcao_atual == 0:
            return []
        limite_percentil = np.percentile(np.array(self._historico_runs), self.percentil_gatilho)
        if self._run_len <= limite_percentil:
            return []

        self._direcao_run_ativo = self._direcao_atual
        tick = self.tick_size
        if self._direcao_atual == 1:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("long", bar.close - self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
