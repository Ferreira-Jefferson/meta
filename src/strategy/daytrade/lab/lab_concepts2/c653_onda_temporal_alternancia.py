"""Catálogo Elliott/Wolfe, item 54: OndaTemporalAlternancia.

APROXIMAÇÃO do princípio de alternância: detecta pivôs de swing (fractal
3 barras) e classifica cada correção (perna B->C, contra o impulso A->B)
como "rápida/profunda" (retração >= 61,8% em duração <= metade do
impulso) ou "rasa/longa" (retração <= 38,2% em duração >= 1,5x o
impulso). Se a correção anterior foi rápida/profunda, uma correção atual
rasa/longa confirma a alternância e cronometra a entrada a favor da
continuação do impulso.
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

_LIMIAR_PROFUNDO = 0.618
_LIMIAR_RASO = 0.382
_FATOR_RAPIDO = 0.5
_FATOR_LONGO = 1.5


@dataclass
class OndaTemporalAlternancia(IntradayStrategy):
    """Classifica correções de swing (fractal 3 barras) em rápida/profunda
    ou rasa/longa por retração% e duração relativa ao impulso; alternância
    confirmada (profunda -> rasa) cronometra entrada a favor do impulso."""

    name: str = "onda_temporal_alternancia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _barra_index: int = field(default=0, init=False, repr=False)
    _buffer_highs: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _buffer_lows: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _buffer_idx: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _pivos_swing: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _classificacao_anterior: str | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._barra_index = 0
        self._buffer_highs = deque(maxlen=3)
        self._buffer_lows = deque(maxlen=3)
        self._buffer_idx = deque(maxlen=3)
        self._pivos_swing = deque(maxlen=3)
        self._classificacao_anterior = None

    def _classifica(self, a, b, c) -> str | None:
        impulso = b[1] - a[1]
        if impulso == 0:
            return None
        retracao = abs(c[1] - b[1]) / abs(impulso)
        dur_impulso = b[0] - a[0]
        dur_correcao = c[0] - b[0]
        if dur_impulso <= 0:
            return None
        if retracao >= _LIMIAR_PROFUNDO and dur_correcao <= _FATOR_RAPIDO * dur_impulso:
            return "profundo_rapido"
        if retracao <= _LIMIAR_RASO and dur_correcao >= _FATOR_LONGO * dur_impulso:
            return "raso_longo"
        return "neutro"

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._barra_index += 1

        self._buffer_highs.append(bar.high)
        self._buffer_lows.append(bar.low)
        self._buffer_idx.append(self._barra_index)

        novo_pivo = None
        if len(self._buffer_highs) == 3:
            h0, h1, h2 = self._buffer_highs
            l0, l1, l2 = self._buffer_lows
            idx1 = self._buffer_idx[1]
            if h1 > h0 and h1 > h2:
                novo_pivo = (idx1, h1)
            elif l1 < l0 and l1 < l2:
                novo_pivo = (idx1, l1)

        if novo_pivo is not None:
            self._pivos_swing.append(novo_pivo)

            if len(self._pivos_swing) == 3:
                a, b, c = self._pivos_swing
                classificacao_atual = self._classifica(a, b, c)

                if (not positions and classificacao_atual == "raso_longo"
                        and self._classificacao_anterior == "profundo_rapido"):
                    impulso_dir = 1 if (b[1] - a[1]) > 0 else -1
                    if impulso_dir > 0:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    else:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]

                if classificacao_atual is not None:
                    self._classificacao_anterior = classificacao_atual

        return acao
