"""Item 46 do catalogo: frequencia de cruzamento do preco com a mediana
movel nas ultimas N barras.

Frequencia BAIXA = tendencia instalada (segue o lado atual); frequencia ALTA
= range (opera reversao a partir dos extremos da propria janela). Sai
quando a frequencia volta ao normal.
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
class FrequenciaCruzamentoQuantil(IntradayStrategy):
    """Frequencia de cruzamento da mediana movel -- tendencia vs. range."""

    name: str = "c445_frequencia_cruzamento_quantil"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    freq_baixa: int = 3
    freq_alta: int = 10
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _closes: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _lados: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)
        self._lados = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) < self.janela:
            return []
        arr = np.asarray(self._closes, dtype=float)
        mediana = float(np.median(arr))
        lado = 1 if bar.close > mediana else (-1 if bar.close < mediana else 0)
        self._lados.append(lado)
        lados_arr = np.asarray(self._lados)
        freq = int(np.sum(np.diff(lados_arr) != 0))

        if positions:
            if self.freq_baixa < freq < self.freq_alta:
                return [Exit(reason="frequencia_normalizou")]
            return []

        if freq <= self.freq_baixa:
            # tendencia instalada: segue o lado atual
            if lado > 0:
                return [self._ordem("long", bar.close, "tendencia_freq_baixa")]
            if lado < 0:
                return [self._ordem("short", bar.close, "tendencia_freq_baixa")]
            return []

        if freq >= self.freq_alta:
            # range: fade do extremo da janela
            topo, fundo = float(arr.max()), float(arr.min())
            if bar.close >= topo:
                return [self._ordem("short", bar.close, "range_fade_topo")]
            if bar.close <= fundo:
                return [self._ordem("long", bar.close, "range_fade_fundo")]
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
