"""Item 64 do catalogo: SUBSTITUI o teste de razao de verossimilhanca
formal (sem p-valor) -- compara a log-verossimilhanca gaussiana de
"variancia CONSTANTE" na janela vs "DUAS FASES" (metades separadas),
calculada diretamente, e usa a DIFERENCA (nao um p-valor) contra um limiar
empirico.

Diferenca grande = mudanca de regime detectada -> opera na direcao do sinal
da SEGUNDA metade (a fase nova). Sai em horizonte fixo.
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


def _log_verossimilhanca_normal(x: np.ndarray, var: float) -> float:
    if var <= 0:
        return -np.inf
    n = len(x)
    return float(-0.5 * n * np.log(2 * np.pi * var) - 0.5 * np.sum(x ** 2) / var)


@dataclass
class VerossimilhancaMudancaVariancia(IntradayStrategy):
    """Diferenca de log-verossimilhanca (1 fase vs 2 fases) da variancia."""

    name: str = "c463_verossimilhanca_mudanca_variancia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    limiar_diferenca: float = 3.0
    barras_saida: int = 15
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

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

        if positions:
            pos = positions[0]
            if pos.bars_held >= self.barras_saida:
                return [Exit(reason="horizonte_fixo_atingido")]
            return []

        if len(self._retornos) < self.janela:
            return []
        arr = np.asarray(self._retornos, dtype=float)
        meio = len(arr) // 2
        primeira, segunda = arr[:meio], arr[meio:]

        var_unica = float(arr.var())
        ll_unica = _log_verossimilhanca_normal(arr - arr.mean(), var_unica)
        ll_duas = (
            _log_verossimilhanca_normal(primeira - primeira.mean(), float(primeira.var()))
            + _log_verossimilhanca_normal(segunda - segunda.mean(), float(segunda.var()))
        )
        diferenca = ll_duas - ll_unica
        if diferenca < self.limiar_diferenca:
            return []
        sinal_nova_fase = float(segunda.mean())
        if sinal_nova_fase > 0:
            return [self._ordem("long", bar.close, f"mudanca_regime_diff{diferenca:.1f}")]
        if sinal_nova_fase < 0:
            return [self._ordem("short", bar.close, f"mudanca_regime_diff{diferenca:.1f}")]
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
