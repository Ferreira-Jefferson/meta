"""Item 58 do catalogo: banda de QUANTIL empirico (percentil 5/95 rolling,
`pandas.Series.rolling().quantile()`) em vez de desvio-padrao fixo.

Entra quando o preco rompe a banda de quantil empirico (reversao); sai no
retorno a' mediana da janela.
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
class RazaoSinalRuidoBollingerDistribucional(IntradayStrategy):
    """Bandas de quantil empirico (rolling) em vez de desvio-padrao fixo."""

    name: str = "c457_razao_sinal_ruido_bollinger_distribucional"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    quantil_baixo: float = 0.05
    quantil_alto: float = 0.95
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _closes: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) < self.janela:
            return []
        serie = pd.Series(self._closes)
        banda_baixa = float(serie.quantile(self.quantil_baixo))
        banda_alta = float(serie.quantile(self.quantil_alto))
        mediana = float(serie.median())

        if positions:
            pos = positions[0]
            if pos.side == "long" and bar.close >= mediana:
                return [Exit(reason="retornou_a_mediana")]
            if pos.side == "short" and bar.close <= mediana:
                return [Exit(reason="retornou_a_mediana")]
            return []

        if bar.close >= banda_alta:
            return [self._ordem("short", bar.close, "rompeu_banda_quantil_alta")]
        if bar.close <= banda_baixa:
            return [self._ordem("long", bar.close, "rompeu_banda_quantil_baixa")]
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
