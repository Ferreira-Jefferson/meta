"""Catalogo calendario/sazonalidade, item 19: SemanaComFeriadoCautela.

Conceito de CALENDARIO: sinaliza a semana (ano ISO, semana ISO) que
CONTEM um gap de calendario no meio -- a vespera OU o pos-feriado
(`calendar_gaps`, precomputado em `initialize`) sempre cai dentro da
semana em que faltou um dia util, entao a uniao das duas datas identifica
a semana inteira. Nessa semana: reduz `quantity` pela metade e usa so' a
janela de abertura (ignora a tarde), `Exit` antecipado as 16:00.
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    calendar_gaps, clamp_quantity, montar_entrada, trading_dates,
)

_FIM_FAIXA_ABERTURA = time(9, 30)
_CORTE_ENTRADAS = time(12, 0)
_FLATTEN_ANTECIPADO = time(16, 0)


@dataclass
class SemanaComFeriadoCautela(IntradayStrategy):
    name: str = "semana_com_feriado_cautela"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    quantity_base: int = 2
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _semanas_com_feriado: set = field(default_factory=set, init=False, repr=False)
    _semana_cautela: bool = field(default=False, init=False, repr=False)
    _faixa_high: float | None = field(default=None, init=False, repr=False)
    _faixa_low: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        dates = trading_dates(bars)
        vesperas, pos_feriado = calendar_gaps(dates)
        semanas = set()
        for d in vesperas | pos_feriado:
            iso = d.isocalendar()
            semanas.add((iso[0], iso[1]))
        self._semanas_com_feriado = semanas

    def on_session_start(self, session_date) -> None:
        iso = session_date.isocalendar()
        self._semana_cautela = (iso[0], iso[1]) in self._semanas_com_feriado
        self._faixa_high = None
        self._faixa_low = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._semana_cautela:
            return []

        if ts.time() >= _FLATTEN_ANTECIPADO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_1600")]
            return []

        if ts.time() < _FIM_FAIXA_ABERTURA:
            if self._faixa_high is None:
                self._faixa_high, self._faixa_low = bar.high, bar.low
            else:
                self._faixa_high = max(self._faixa_high, bar.high)
                self._faixa_low = min(self._faixa_low, bar.low)
            return []

        # so' novas entradas na janela da manha (ignora a tarde)
        if ts.time() >= _CORTE_ENTRADAS or positions or self._entrou_hoje or self._faixa_high is None:
            return []

        quantidade = clamp_quantity(self.quantity_base / 2, minimo=1, teto=self.quantity_base)
        if bar.close > self._faixa_high:
            self._entrou_hoje = True
            return [montar_entrada(
                side="long", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=quantidade,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        if bar.close < self._faixa_low:
            self._entrou_hoje = True
            return [montar_entrada(
                side="short", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=quantidade,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
