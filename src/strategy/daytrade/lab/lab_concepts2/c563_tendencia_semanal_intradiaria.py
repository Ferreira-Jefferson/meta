"""Catálogo regime/adaptação, item 64: TendenciaSemanalIntradiaria.

Précompute (em `initialize`) o retorno diário agregado (fechamento −
abertura de cada pregão) e a soma móvel dos últimos `janela_dias` pregões
ANTERIORES (sem look-ahead: usa só dias estritamente antes de hoje) --
vira o viés de mais longo prazo que filtra o lado das entradas
intradiárias de hoje.
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
class TendenciaSemanalIntradiaria(IntradayStrategy):
    """Rompimento de range de N barras, filtrado pelo viés de
    `janela_dias` pregões ANTERIORES (retorno diário acumulado,
    précomputado em `initialize`) -- só entra no lado alinhado ao viés."""

    name: str = "tendencia_semanal_intradiaria"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_dias: int = 5
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
        retorno_diario = diario["fechamento"] - diario["abertura"]
        soma_movel = retorno_diario.rolling(window=self.janela_dias, min_periods=self.janela_dias).sum()
        vies_anterior = soma_movel.shift(1)
        self._vies_por_dia = {
            d: ("long" if v > 0 else ("short" if v < 0 else None))
            for d, v in vies_anterior.items() if pd.notna(v)
        }

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
