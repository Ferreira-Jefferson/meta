"""Catálogo Elliott/Wolfe, item 51: OndaDeWolfeNaoLinear.

APROXIMAÇÃO: detecta 5 pivôs de swing alternados (fractal 3 barras, sem
exigir simetria/paralelismo do canal). Quando o 5º ponto rompe além da
linha de tendência 1-3 (extrapolada), entra na reversão com alvo na
projeção da linha 1-4 avaliada na barra atual.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class OndaDeWolfeNaoLinear(IntradayStrategy):
    """5 pivôs de swing alternados; quando o 5º rompe além da reta 1-3
    (extrapolada), entra na reversão com alvo projetado na reta 1-4."""

    name: str = "onda_de_wolfe_nao_linear"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    offset_ticks: int = 1
    stop_ticks_buffer: int = 6
    entrada_ttl_bars: int = 40

    _barra_index: int = field(default=0, init=False, repr=False)
    _buffer_highs: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _buffer_lows: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _buffer_idx: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _pivos: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _pivo_5_processado: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._barra_index = 0
        self._buffer_highs = deque(maxlen=3)
        self._buffer_lows = deque(maxlen=3)
        self._buffer_idx = deque(maxlen=3)
        self._pivos = deque(maxlen=5)
        self._pivo_5_processado = False

    def _registra_pivo(self) -> bool:
        if len(self._buffer_highs) < 3:
            return False
        h0, h1, h2 = self._buffer_highs
        l0, l1, l2 = self._buffer_lows
        idx1 = self._buffer_idx[1]
        if h1 > h0 and h1 > h2:
            tipo = "alta"
            preco = h1
        elif l1 < l0 and l1 < l2:
            tipo = "baixa"
            preco = l1
        else:
            return False

        if self._pivos and self._pivos[-1][2] == tipo:
            return False
        novo = len(self._pivos) < 5
        self._pivos.append((idx1, preco, tipo))
        if len(self._pivos) == 5:
            self._pivo_5_processado = False
        return novo and len(self._pivos) == 5

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._barra_index += 1

        self._buffer_highs.append(bar.high)
        self._buffer_lows.append(bar.low)
        self._buffer_idx.append(self._barra_index)
        completou_5 = self._registra_pivo()

        if (not positions and completou_5 and not self._pivo_5_processado
                and len(self._pivos) == 5):
            p1, p2, p3, p4, p5 = self._pivos
            tipos_ok = p1[2] != p2[2] and p2[2] != p3[2] and p3[2] != p4[2] and p4[2] != p5[2]
            if tipos_ok and p3[0] != p1[0] and p4[0] != p1[0]:
                slope13 = (p3[1] - p1[1]) / (p3[0] - p1[0])
                linha13_em_5 = p1[1] + slope13 * (p5[0] - p1[0])
                slope14 = (p4[1] - p1[1]) / (p4[0] - p1[0])
                projecao14 = p1[1] + slope14 * (self._barra_index - p1[0])

                buffer = self.stop_ticks_buffer * self.tick_size
                if p5[2] == "baixa" and p5[1] < linha13_em_5:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(p5[1] - buffer, self.tick_size)
                    alvo = no_tick(projecao14, self.tick_size)
                    if alvo - limite >= 4 * self.tick_size:
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                elif p5[2] == "alta" and p5[1] > linha13_em_5:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(p5[1] + buffer, self.tick_size)
                    alvo = no_tick(projecao14, self.tick_size)
                    if limite - alvo >= 4 * self.tick_size:
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                self._pivo_5_processado = True

        return acao
