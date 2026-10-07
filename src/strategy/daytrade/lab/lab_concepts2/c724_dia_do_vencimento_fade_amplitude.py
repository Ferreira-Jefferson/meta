"""Catalogo calendario/sazonalidade, item 25: DiaDoVencimentoFadeAmplitude.

Conceito de CALENDARIO: no "dia de vencimento" (aproximacao -- ULTIMO
pregao do mes, `month_boundaries`, ver docstring de
`_common_calendario`), fade de qualquer rompimento do range do dia ACIMA
do range medio das ultimas N sessoes ANTERIORES (precomputado por dia em
`initialize`, media rolante calculada em `on_session_start` so' com dias
estritamente ANTERIORES -- sem look-ahead). Saida rapida por TEMPO
(15min, `Exit` incondicional), usando o `entry_ts` real da posicao.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    month_boundaries, montar_entrada, trading_dates,
)

_JANELA_HIST_DIAS = 10
_MINUTOS_SAIDA_RAPIDA = 15


@dataclass
class DiaDoVencimentoFadeAmplitude(IntradayStrategy):
    name: str = "dia_do_vencimento_fade_amplitude"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 20

    _todas_datas: list = field(default_factory=list, init=False, repr=False)
    _range_por_dia: dict = field(default_factory=dict, init=False, repr=False)
    _ultimos_do_mes: set = field(default_factory=set, init=False, repr=False)
    _e_vencimento: bool = field(default=False, init=False, repr=False)
    _range_medio_hist: float | None = field(default=None, init=False, repr=False)
    _abertura_dia: float | None = field(default=None, init=False, repr=False)
    _high_dia: float | None = field(default=None, init=False, repr=False)
    _low_dia: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        idx = pd.DatetimeIndex(bars.index)
        df = pd.DataFrame({"high": bars["high"].to_numpy(), "low": bars["low"].to_numpy()}, index=idx)
        ranges: dict = {}
        for d, grupo in df.groupby(idx.date):
            ranges[d] = float(grupo["high"].max() - grupo["low"].min())
        self._range_por_dia = ranges
        dates = trading_dates(bars)
        self._todas_datas = dates
        _, ultimos = month_boundaries(dates)
        self._ultimos_do_mes = ultimos

    def on_session_start(self, session_date) -> None:
        self._e_vencimento = session_date in self._ultimos_do_mes
        anteriores = [d for d in self._todas_datas if d < session_date]
        recentes = anteriores[-_JANELA_HIST_DIAS:]
        valores = [self._range_por_dia[d] for d in recentes if d in self._range_por_dia]
        self._range_medio_hist = (sum(valores) / len(valores)) if valores else None
        self._abertura_dia = None
        self._high_dia = None
        self._low_dia = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_vencimento:
            return []

        if self._abertura_dia is None:
            self._abertura_dia = bar.open
            self._high_dia, self._low_dia = bar.high, bar.low
        else:
            self._high_dia = max(self._high_dia, bar.high)
            self._low_dia = min(self._low_dia, bar.low)

        if positions:
            entry_ts = positions[0].entry_ts
            if (ts - entry_ts) >= pd.Timedelta(minutes=_MINUTOS_SAIDA_RAPIDA):
                return [Exit(reason=f"{self.name}_saida_rapida")]
            return []

        if self._entrou_hoje or self._range_medio_hist is None:
            return []

        range_hoje = self._high_dia - self._low_dia
        if range_hoje > self._range_medio_hist:
            self._entrou_hoje = True
            # fade: se o fechamento esta acima da abertura, o rompimento e'
            # para cima -- vende; senao, compra.
            side = "short" if bar.close > self._abertura_dia else "long"
            return [montar_entrada(
                side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
