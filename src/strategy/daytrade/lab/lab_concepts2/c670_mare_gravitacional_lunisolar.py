"""Catálogo astronomia/tempo, item 71: MareGravitacionalLuniSolar.

Combina fase lunar (#67) e declinação solar (#68), ambas aritmética de
calendário pura, num índice composto de "força de maré" determinístico
da data. Dias de maré alta (índice grande em módulo) operam rompimento
de range; dias de maré baixa operam fade nos extremos do range.
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

MES_SINODICO_DIAS = 29.530588
LUA_NOVA_REFERENCIA_ORDINAL = pd.Timestamp("2000-01-06").toordinal()


def _fase_lunar(data: pd.Timestamp) -> float:
    dias = data.toordinal() - LUA_NOVA_REFERENCIA_ORDINAL
    return (dias % MES_SINODICO_DIAS) / MES_SINODICO_DIAS


def _declinacao_solar_graus(data: pd.Timestamp) -> float:
    return 23.44 * math.sin(2 * math.pi * (284 + data.dayofyear) / 365.0)


def indice_mare(data: pd.Timestamp, peso_lua: float = 0.6, peso_sol: float = 0.4) -> float:
    """Índice de "maré" em [-1, 1]: soma ponderada de um componente lunar
    (`sin(2*pi*fase)`, força máxima em lua nova/cheia) e um componente
    solar (declinação normalizada)."""
    componente_lunar = math.sin(2 * math.pi * _fase_lunar(data))
    componente_solar = _declinacao_solar_graus(data) / 23.44
    return peso_lua * componente_lunar + peso_sol * componente_solar


@dataclass
class MareGravitacionalLuniSolar(IntradayStrategy):
    """Índice de maré (fase lunar + declinação solar) decide o REGIME do
    dia: |índice| acima do limiar = maré alta, opera rompimento do range
    de abertura; abaixo = maré baixa, opera fade nos extremos dele."""

    name: str = "mare_gravitacional_lunisolar"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    limiar_mare_alta: float = 0.5
    barras_abertura: int = 15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _regime: str = field(default="alta", init=False, repr=False)
    _range_high: float | None = field(default=None, init=False, repr=False)
    _range_low: float | None = field(default=None, init=False, repr=False)
    _n_barras: int = field(default=0, init=False, repr=False)
    _armado: bool = field(default=True, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        indice = indice_mare(pd.Timestamp(session_date))
        self._regime = "alta" if abs(indice) > self.limiar_mare_alta else "baixa"
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
            side = None
            if self._regime == "alta":
                if bar.close > self._range_high:
                    side = "long"
                elif bar.close < self._range_low:
                    side = "short"
            else:
                if bar.close >= self._range_high:
                    side = "short"  # fade do extremo superior
                elif bar.close <= self._range_low:
                    side = "long"   # fade do extremo inferior

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
