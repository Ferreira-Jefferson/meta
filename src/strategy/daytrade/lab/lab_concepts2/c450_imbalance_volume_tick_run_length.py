"""Item 51 do catalogo: run-length da sequencia de barras com volume ACIMA
ou ABAIXO da mediana movel (nao a direcao do preco).

Um run persistente de volume ALTO sinaliza acumulacao; entra na direcao do
PRECO durante o run quando esse run termina (exaustao). Sai N barras depois
(via `IntradayOpenPosition.bars_held`).
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
class ImbalanceVolumeTickRunLength(IntradayStrategy):
    """Run-length de volume alto/baixo -- exaustao do run dispara entrada."""

    name: str = "c450_imbalance_volume_tick_run_length"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    run_minimo: int = 5
    barras_saida: int = 10
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _volumes: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _run_alto_len: int = field(default=0, init=False, repr=False)
    _close_no_inicio_do_run: float | None = field(default=None, init=False, repr=False)
    _close_atual: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._volumes = deque(maxlen=self.janela)
        self._run_alto_len = 0
        self._close_no_inicio_do_run = None
        self._close_atual = 0.0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._close_atual = bar.close
        if positions:
            pos = positions[0]
            if pos.bars_held >= self.barras_saida:
                return [Exit(reason="prazo_de_saida_atingido")]
            return []

        if len(self._volumes) < self.janela:
            self._volumes.append(bar.volume)
            return []
        mediana_vol = float(np.median(self._volumes))
        acima = bar.volume > mediana_vol
        self._volumes.append(bar.volume)

        run_terminou = self._run_alto_len >= self.run_minimo and not acima
        if acima:
            if self._run_alto_len == 0:
                self._close_no_inicio_do_run = self._close_atual
            self._run_alto_len += 1
            return []

        if run_terminou and self._close_no_inicio_do_run is not None:
            direcao = 1 if bar.close > self._close_no_inicio_do_run else -1
            self._run_alto_len = 0
            self._close_no_inicio_do_run = None
            if direcao > 0:
                return [self._ordem("long", bar.close, "exaustao_run_volume_alto")]
            return [self._ordem("short", bar.close, "exaustao_run_volume_alto")]

        self._run_alto_len = 0
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
