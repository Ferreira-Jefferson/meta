"""Catálogo astronomia/tempo, item 70: CicloDeManchasSolaresPseudo.

Contador determinístico de pseudo-ciclo de 11 anos (dias desde uma data
de referência, módulo `11 * 365,25`) -- puramente aritmética de
calendário, sem qualquer dado real de atividade solar. Usado como flag
de viés lento (metade "ativa" do ciclo habilita o robô) combinado a um
gatilho intradiário de rompimento de range.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

CICLO_DIAS = 11 * 365.25
DATA_REFERENCIA_ORDINAL = pd.Timestamp("1755-03-01").toordinal()  # início convencional do ciclo 1


def fase_ciclo_pseudo(data: pd.Timestamp) -> float:
    """Fração [0, 1) do pseudo-ciclo de 11 anos decorrida desde a
    referência."""
    dias = data.toordinal() - DATA_REFERENCIA_ORDINAL
    return (dias % CICLO_DIAS) / CICLO_DIAS


@dataclass
class CicloDeManchasSolaresPseudo(IntradayStrategy):
    """Habilita o robô só na primeira metade do pseudo-ciclo de 11 anos;
    quando habilitado, opera o rompimento do range de abertura do
    pregão."""

    name: str = "ciclo_de_manchas_solares_pseudo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    barras_abertura: int = 15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _habilitado: bool = field(default=False, init=False, repr=False)
    _range_high: float | None = field(default=None, init=False, repr=False)
    _range_low: float | None = field(default=None, init=False, repr=False)
    _n_barras: int = field(default=0, init=False, repr=False)
    _armado: bool = field(default=True, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._habilitado = fase_ciclo_pseudo(pd.Timestamp(session_date)) < 0.5
        self._range_high = None
        self._range_low = None
        self._n_barras = 0
        self._armado = True

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if not self._habilitado:
            return acao

        self._n_barras += 1
        if self._n_barras <= self.barras_abertura:
            self._range_high = bar.high if self._range_high is None else max(self._range_high, bar.high)
            self._range_low = bar.low if self._range_low is None else min(self._range_low, bar.low)
            return acao

        if (not positions and self._armado
                and self._range_high is not None and self._range_low is not None):
            side = None
            if bar.close > self._range_high:
                side = "long"
            elif bar.close < self._range_low:
                side = "short"
            if side is not None:
                if side == "long":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=side, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
                self._armado = False
        return acao
