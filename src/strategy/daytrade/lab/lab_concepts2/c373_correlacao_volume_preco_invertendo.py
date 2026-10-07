"""Catálogo volume/microestrutura, item 74: CorrelacaoVolumePrecoInvertendoNaJanela.

Correlação móvel (`numpy.corrcoef`, limiar empírico -- sem teste formal)
entre volume e |variação de preço| numa janela passa de positiva para
negativa; na transição, faz fade no extremo recente mais próximo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class CorrelacaoVolumePrecoInvertendoNaJanela(IntradayStrategy):
    """Correlação móvel volume x |Δpreço| vira de positiva para negativa
    -- fade no extremo recente mais próximo do fechamento."""

    name: str = "correlacao_volume_preco_invertendo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    limiar_positivo: float = 0.3
    limiar_negativo: float = 0.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _abs_delta: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _corr_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela)
        self._abs_delta = deque(maxlen=self.janela)
        self._highs = deque(maxlen=self.janela)
        self._lows = deque(maxlen=self.janela)
        self._close_anterior = None
        self._corr_anterior = None

    def _ordem(self, lado: str, nivel: float) -> list[IntradayAction]:
        if lado == "long":
            limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
        else:
            limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
        return [EnterLimit(
            side=lado, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        delta_abs = abs(bar.close - self._close_anterior) if self._close_anterior is not None else 0.0
        self._vols.append(bar.volume)
        self._abs_delta.append(delta_abs)

        corr_atual = None
        if len(self._vols) == self._vols.maxlen:
            v = np.array(self._vols, dtype=float)
            d = np.array(self._abs_delta, dtype=float)
            if v.std() > 0 and d.std() > 0:
                corr_atual = float(np.corrcoef(v, d)[0, 1])

        if (not positions and corr_atual is not None and self._corr_anterior is not None
                and len(self._highs) == self._highs.maxlen):
            inverteu = self._corr_anterior > self.limiar_positivo and corr_atual < self.limiar_negativo
            if inverteu:
                topo = max(self._highs)
                fundo = min(self._lows)
                if (topo - bar.close) < (bar.close - fundo):
                    acao = self._ordem("short", topo)
                else:
                    acao = self._ordem("long", fundo)

        if corr_atual is not None:
            self._corr_anterior = corr_atual
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._close_anterior = bar.close
        return acao
