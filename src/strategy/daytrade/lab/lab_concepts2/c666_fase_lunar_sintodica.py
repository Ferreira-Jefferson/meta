"""Catálogo astronomia/tempo, item 67: FaseLunarSintodica.

Fase lunar por aritmética de calendário pura (dias desde a lua nova de
referência 2000-01-06, módulo o mês sinódico 29,530588 dias) a partir da
data da sessão; usa como viés lento de direção, combinado com o
rompimento do range de abertura do próprio pregão como gatilho.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

MES_SINODICO_DIAS = 29.530588
LUA_NOVA_REFERENCIA_ORDINAL = pd.Timestamp("2000-01-06").toordinal()


def fase_lunar(data: pd.Timestamp) -> float:
    """Fração [0, 1) do ciclo sinódico decorrida desde a lua nova de
    referência -- 0 = lua nova, ~0,5 = lua cheia."""
    dias = data.toordinal() - LUA_NOVA_REFERENCIA_ORDINAL
    return (dias % MES_SINODICO_DIAS) / MES_SINODICO_DIAS


@dataclass
class FaseLunarSintodica(IntradayStrategy):
    """Viés de direção pela metade do ciclo lunar (crescente = long,
    minguante = short); só opera no rompimento do range das primeiras
    `barras_abertura` barras do pregão, na direção do viés."""

    name: str = "fase_lunar_sintodica"
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

    _bias: str = field(default="long", init=False, repr=False)
    _range_high: float | None = field(default=None, init=False, repr=False)
    _range_low: float | None = field(default=None, init=False, repr=False)
    _n_barras: int = field(default=0, init=False, repr=False)
    _armado: bool = field(default=True, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        fase = fase_lunar(pd.Timestamp(session_date))
        self._bias = "long" if fase < 0.5 else "short"
        self._range_high = None
        self._range_low = None
        self._n_barras = 0
        self._armado = True

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._n_barras += 1

        if self._n_barras <= self.barras_abertura:
            self._range_high = bar.high if self._range_high is None else max(self._range_high, bar.high)
            self._range_low = bar.low if self._range_low is None else min(self._range_low, bar.low)
            return acao

        if (not positions and self._armado
                and self._range_high is not None and self._range_low is not None):
            rompeu_alta = bar.close > self._range_high
            rompeu_baixa = bar.close < self._range_low
            if (self._bias == "long" and rompeu_alta) or (self._bias == "short" and rompeu_baixa):
                side = self._bias
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
