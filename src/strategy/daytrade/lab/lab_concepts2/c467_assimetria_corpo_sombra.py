"""Item 68 do catalogo: razao (assinada) corpo/sombra de cada candle,
testada via z-score contra a propria distribuicao historica rolling (nao
teste formal).

Entra na direcao da assimetria DOMINANTE quando o z e' extremo; sai quando
normaliza.
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
class AssimetriaCorpoSombra(IntradayStrategy):
    """Z-score da razao assinada corpo/sombra do candle."""

    name: str = "c467_assimetria_corpo_sombra"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    z_entrada: float = 2.0
    z_saida: float = 0.5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _razoes: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._razoes = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        corpo = bar.close - bar.open
        sombra_total = (bar.high - bar.low) - abs(corpo) + 1e-9
        razao = corpo / sombra_total
        self._razoes.append(razao)
        if len(self._razoes) < self.janela:
            return []
        arr = np.asarray(self._razoes, dtype=float)
        desvio = float(arr.std())
        z = float((razao - arr.mean()) / desvio) if desvio > 0 else 0.0

        if positions:
            if abs(z) <= self.z_saida:
                return [Exit(reason="assimetria_normalizou")]
            return []

        if z >= self.z_entrada:
            return [self._ordem("long", bar.close, f"assimetria_dominante_alta_z{z:.2f}")]
        if z <= -self.z_entrada:
            return [self._ordem("short", bar.close, f"assimetria_dominante_baixa_z{z:.2f}")]
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
