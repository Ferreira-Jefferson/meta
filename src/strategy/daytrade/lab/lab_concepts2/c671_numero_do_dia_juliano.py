"""Catálogo astronomia/tempo, item 72: NumeroDoDiaJuliano.

Número do dia juliano (aproximado via `date.toordinal()`, deslocado para
a convenção juliana) módulo primos pequenos (7, 11, 13); filtro
determinístico habilitando/desabilitando o pregão inteiro. Quando
habilitado, opera o rompimento do range de abertura.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

# Deslocamento padrão entre o ordinal proléptico gregoriano do Python
# (dia 1 = 0001-01-01) e o número do dia juliano astronômico (dia 0 =
# 4713 a.C.) -- aproximação suficiente para um filtro determinístico
# modulo primos pequenos, não para efemérides de precisão.
DESLOCAMENTO_JULIANO = 1721424.5


def numero_dia_juliano(data: pd.Timestamp) -> int:
    return int(data.toordinal() + DESLOCAMENTO_JULIANO)


@dataclass
class NumeroDoDiaJuliano(IntradayStrategy):
    """Pregão só fica habilitado quando o número do dia juliano é
    múltiplo de 7, 11 ou 13; nesses dias, opera o rompimento do range
    das primeiras `barras_abertura` barras."""

    name: str = "numero_do_dia_juliano"
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
        jdn = numero_dia_juliano(pd.Timestamp(session_date))
        self._habilitado = jdn % 7 == 0 or jdn % 11 == 0 or jdn % 13 == 0
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
