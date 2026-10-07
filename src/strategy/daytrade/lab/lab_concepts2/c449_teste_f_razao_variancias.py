"""Item 50 do catalogo: razao de variancias entre duas sub-janelas
consecutivas (metade recente vs metade anterior), comparada a um LIMIAR
EMPIRICO -- nao teste F formal com p-valor (pedido explicito do escopo:
pular a formalizacao e usar so' aritmetica de razao).

Liga reversao pos-choque de volatilidade quando a razao e' extrema (a
metade recente ficou muito mais ou muito menos volatil que a anterior);
sai quando a razao normaliza.
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
class TesteFRazaoVariancias(IntradayStrategy):
    """Razao de variancias entre sub-janelas -- choque de vol como gatilho."""

    name: str = "c449_teste_f_razao_variancias"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    razao_alta: float = 2.0
    razao_baixa: float = 0.5
    razao_normal_inf: float = 0.7
    razao_normal_sup: float = 1.4
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
        ret = None
        if self._close_anterior is not None and self._close_anterior != 0:
            ret = (bar.close - self._close_anterior) / self._close_anterior
            self._retornos.append(ret)
        self._close_anterior = bar.close

        razao = self._razao()
        if positions:
            if razao is not None and self.razao_normal_inf <= razao <= self.razao_normal_sup:
                return [Exit(reason="razao_normalizou")]
            return []

        if razao is None or ret is None:
            return []
        extremo = razao >= self.razao_alta or razao <= self.razao_baixa
        if not extremo:
            return []
        # fade do movimento mais recente (reversao pos-choque de vol)
        if ret > 0:
            return [self._ordem("short", bar.close, f"choque_vol_razao{razao:.2f}")]
        if ret < 0:
            return [self._ordem("long", bar.close, f"choque_vol_razao{razao:.2f}")]
        return []

    def _razao(self) -> float | None:
        if len(self._retornos) < self.janela:
            return None
        arr = np.asarray(self._retornos, dtype=float)
        meio = len(arr) // 2
        var_antiga = float(arr[:meio].var())
        var_recente = float(arr[meio:].var())
        if var_antiga <= 0:
            return None
        return var_recente / var_antiga

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
