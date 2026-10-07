"""Item 73 do catalogo: bootstrap (reamostragem com reposicao, numpy puro,
1000+ reamostragens) dos retornos de uma janela para o intervalo de
confianca EMPIRICO da media.

Entra na direcao do retorno medio quando o IC bootstrap NAO contem zero;
sai quando o IC seguinte volta a conter zero.
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
class BootstrapIntervaloConfiancaRetornoMedio(IntradayStrategy):
    """IC bootstrap da media dos retornos numa janela movel."""

    name: str = "c472_bootstrap_ic_retorno_medio"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    n_reamostragens: int = 1000
    alfa: float = 0.05
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(442), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._retornos = deque(maxlen=self.janela)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._close_anterior is not None and self._close_anterior != 0:
            self._retornos.append((bar.close - self._close_anterior) / self._close_anterior)
        self._close_anterior = bar.close

        if len(self._retornos) < self.janela:
            return []
        ic_baixo, ic_alto = self._bootstrap_ic()
        contem_zero = ic_baixo <= 0.0 <= ic_alto

        if positions:
            if contem_zero:
                return [Exit(reason="ic_voltou_a_conter_zero")]
            return []

        if contem_zero:
            return []
        if ic_baixo > 0:
            return [self._ordem("long", bar.close, "ic_bootstrap_acima_de_zero")]
        return [self._ordem("short", bar.close, "ic_bootstrap_abaixo_de_zero")]

    def _bootstrap_ic(self) -> tuple[float, float]:
        arr = np.asarray(self._retornos, dtype=float)
        n = len(arr)
        indices = self._rng.integers(0, n, size=(self.n_reamostragens, n))
        medias = arr[indices].mean(axis=1)
        baixo = float(np.quantile(medias, self.alfa / 2))
        alto = float(np.quantile(medias, 1 - self.alfa / 2))
        return baixo, alto

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
