"""Catálogo regime/adaptação, item 76: RegimeDeDirecaoAlternadaForcada.

Précompute (em `initialize`) o retorno diário agregado; uma sequência de
`n_dias_sequencia` pregões CONSECUTIVOS fechando na mesma direção (sem
look-ahead: só considera dias estritamente antes de hoje) assume viés de
REVERSÃO estatística para o pregão seguinte.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    Side, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class RegimeDeDirecaoAlternadaForcada(IntradayStrategy):
    """Rompimento de range de N barras, filtrado pelo viés de reversão:
    após `n_dias_sequencia` pregões consecutivos fechando na mesma
    direção (précomputado em `initialize`), assume viés OPOSTO para o
    pregão de hoje."""

    name: str = "regime_de_direcao_alternada_forcada"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    n_dias_sequencia: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vies_por_dia: dict = field(default_factory=dict, init=False, repr=False)
    _vies_hoje: "Side | None" = field(default=None, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        diario = bars.groupby(bars.index.date).agg(
            abertura=("open", "first"), fechamento=("close", "last"),
        )
        diario = diario.sort_index()
        retorno_diario = diario["fechamento"] - diario["abertura"]
        sinais = [1 if v > 0 else (-1 if v < 0 else 0) for v in retorno_diario]
        datas = list(diario.index)
        vies_por_dia: dict = {}
        for i, data in enumerate(datas):
            if i < self.n_dias_sequencia:
                vies_por_dia[data] = None
                continue
            janela = sinais[i - self.n_dias_sequencia:i]
            if len(set(janela)) == 1 and janela[0] != 0:
                vies_por_dia[data] = "short" if janela[0] > 0 else "long"
            else:
                vies_por_dia[data] = None
        self._vies_por_dia = vies_por_dia

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._vies_hoje = self._vies_por_dia.get(session_date)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if positions:
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if self._vies_hoje is not None and len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if self._vies_hoje == "long" and bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif self._vies_hoje == "short" and bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
