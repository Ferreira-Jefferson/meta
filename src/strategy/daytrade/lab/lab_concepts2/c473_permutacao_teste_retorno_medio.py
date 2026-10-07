"""Item 74 do catalogo: teste de permutacao (embaralha SINAIS dos retornos,
recalcula a media muitas vezes, numpy puro) para o p-valor EMPIRICO do
retorno medio, sem suposicao parametrica.

Entra quando o p-valor de permutacao e' baixo (<0,1); sai quando deixa de
ser.
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
class PermutacaoTesteRetornoMedio(IntradayStrategy):
    """P-valor empirico por permutacao de sinais dos retornos."""

    name: str = "c473_permutacao_teste_retorno_medio"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    n_permutacoes: int = 1000
    p_entrada: float = 0.1
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(443), init=False, repr=False)

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
        p_valor, media = self._p_valor_permutacao()

        if positions:
            if p_valor >= self.p_entrada:
                return [Exit(reason="permutacao_perdeu_significancia")]
            return []

        if p_valor >= self.p_entrada:
            return []
        if media > 0:
            return [self._ordem("long", bar.close, f"permutacao_p{p_valor:.3f}")]
        return [self._ordem("short", bar.close, f"permutacao_p{p_valor:.3f}")]

    def _p_valor_permutacao(self) -> tuple[float, float]:
        arr = np.abs(np.asarray(self._retornos, dtype=float))
        media_observada = float(np.mean(self._retornos))
        sinais_aleatorios = self._rng.choice([-1.0, 1.0], size=(self.n_permutacoes, len(arr)))
        medias_perm = (sinais_aleatorios * arr).mean(axis=1)
        p_valor = float(np.mean(np.abs(medias_perm) >= abs(media_observada)))
        return p_valor, media_observada

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
