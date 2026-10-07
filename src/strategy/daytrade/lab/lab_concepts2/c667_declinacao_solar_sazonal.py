"""Catálogo astronomia/tempo, item 68: DeclinacaoSolarSazonal.

Ângulo de declinação solar pela fórmula fechada padrão
(`23,44 * sin(2*pi*(284+dia_do_ano)/365)`) a partir do dia do ano da
sessão; usa o SINAL como viés de direção lento e a MAGNITUDE (normalizada)
para escalar o alvo/stop, condicionado a um gatilho de rompimento do
range de abertura do mesmo dia.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def declinacao_solar_graus(data: pd.Timestamp) -> float:
    """Fórmula fechada padrão de declinação solar em graus."""
    dia_do_ano = data.dayofyear
    return 23.44 * math.sin(2 * math.pi * (284 + dia_do_ano) / 365.0)


@dataclass
class DeclinacaoSolarSazonal(IntradayStrategy):
    """Viés de direção pelo sinal da declinação solar do dia; magnitude
    (fração de 23,44°) escala o alvo/stop entre `stop_ticks_min` e
    `stop_ticks_max`; opera no rompimento do range de abertura na
    direção do viés."""

    name: str = "declinacao_solar_sazonal"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    barras_abertura: int = 15
    offset_ticks: int = 1
    stop_ticks_min: int = 10
    stop_ticks_max: int = 20
    alvo_ticks_min: int = 6
    alvo_ticks_max: int = 12
    entrada_ttl_bars: int = 40

    _bias: str = field(default="long", init=False, repr=False)
    _magnitude: float = field(default=0.0, init=False, repr=False)
    _range_high: float | None = field(default=None, init=False, repr=False)
    _range_low: float | None = field(default=None, init=False, repr=False)
    _n_barras: int = field(default=0, init=False, repr=False)
    _armado: bool = field(default=True, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        declinacao = declinacao_solar_graus(pd.Timestamp(session_date))
        self._bias = "long" if declinacao >= 0 else "short"
        self._magnitude = min(1.0, abs(declinacao) / 23.44)
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
                stop_ticks = round(self.stop_ticks_min + self._magnitude * (self.stop_ticks_max - self.stop_ticks_min))
                alvo_ticks = round(self.alvo_ticks_min + self._magnitude * (self.alvo_ticks_max - self.alvo_ticks_min))
                alvo_ticks = max(4, alvo_ticks)
                side = self._bias
                if side == "long":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=side, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
                self._armado = False
        return acao
