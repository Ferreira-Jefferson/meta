"""Item 78 do catalogo: ajusta uma regressao linear LOCAL (`numpy.polyfit`,
preco vs tempo) em duas metades da janela separadamente; a DIFERENCA de
coeficientes angulares (nao um teste CUSUM formal) sinaliza quebra
estrutural.

Liga reversao a' NOVA tendencia so' apos a diferenca exceder um limiar
empirico; sai na quebra seguinte (ou horizonte fixo).
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
class CusumEstabilidadeRegressao(IntradayStrategy):
    """Diferenca de inclinacao entre metades da janela -- quebra estrutural."""

    name: str = "c477_cusum_estabilidade_regressao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    limiar_diferenca_ticks: float = 0.3
    barras_saida: int = 15
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _closes: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if positions:
            pos = positions[0]
            if pos.bars_held >= self.barras_saida:
                return [Exit(reason="horizonte_fixo_atingido")]
            return []

        if len(self._closes) < self.janela:
            return []
        y = np.asarray(self._closes, dtype=float)
        meio = len(y) // 2
        x1 = np.arange(meio, dtype=float)
        x2 = np.arange(len(y) - meio, dtype=float)
        inclinacao1, _ = np.polyfit(x1, y[:meio], 1)
        inclinacao2, _ = np.polyfit(x2, y[meio:], 1)
        diferenca_ticks = (inclinacao2 - inclinacao1) / self.tick_size

        if abs(diferenca_ticks) < self.limiar_diferenca_ticks:
            return []
        if inclinacao2 > 0:
            return [self._ordem("long", bar.close, f"quebra_estrutural_diff{diferenca_ticks:.2f}")]
        return [self._ordem("short", bar.close, f"quebra_estrutural_diff{diferenca_ticks:.2f}")]

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
