"""Catalogo calendario/sazonalidade, item 6: FechamentoRushVolume.

Conceito de CALENDARIO: os ultimos 15min do pregao (17:45-18:00, janela
FIXA) sao o "rush de fechamento". So' entra se o volume acumulado da
janela de HOJE exceder a media das ultimas 5 janelas equivalentes de
pregoes ANTERIORES (historico precomputado em `initialize`, a partir de
`tick_volume` -- a mesma coluna que origina `Bar.volume`), na direcao do
movimento desde o inicio da janela.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    INICIO_RUSH_FECHAMENTO, montar_entrada, trading_dates,
)


@dataclass
class FechamentoRushVolume(IntradayStrategy):
    name: str = "fechamento_rush_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_dias_historico: int = 5
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 12

    _todas_datas: list = field(default_factory=list, init=False, repr=False)
    _volume_janela_por_dia: dict = field(default_factory=dict, init=False, repr=False)
    _media_hist: float | None = field(default=None, init=False, repr=False)
    _vol_acumulado_hoje: float = field(default=0.0, init=False, repr=False)
    _preco_inicio_janela: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        self._todas_datas = trading_dates(bars)
        vol_por_dia: dict = {}
        if "tick_volume" in bars.columns:
            idx = pd.DatetimeIndex(bars.index)
            for ts, v in zip(idx, bars["tick_volume"]):
                if ts.time() >= INICIO_RUSH_FECHAMENTO:
                    d = ts.date()
                    vol_por_dia[d] = vol_por_dia.get(d, 0.0) + float(v)
        self._volume_janela_por_dia = vol_por_dia

    def on_session_start(self, session_date) -> None:
        self._vol_acumulado_hoje = 0.0
        self._preco_inicio_janela = None
        self._entrou_hoje = False
        anteriores = [d for d in self._todas_datas if d < session_date]
        recentes = anteriores[-self.janela_dias_historico:]
        valores = [self._volume_janela_por_dia[d] for d in recentes if d in self._volume_janela_por_dia]
        self._media_hist = (sum(valores) / len(valores)) if valores else None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if ts.time() < INICIO_RUSH_FECHAMENTO:
            return []

        if self._preco_inicio_janela is None:
            self._preco_inicio_janela = bar.open

        self._vol_acumulado_hoje += bar.volume

        if (not positions and not self._entrou_hoje and self._media_hist is not None
                and self._vol_acumulado_hoje > self._media_hist):
            movimento = bar.close - self._preco_inicio_janela
            if movimento != 0:
                self._entrou_hoje = True
                side = "long" if movimento > 0 else "short"
                return [montar_entrada(
                    side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
                    alvo_ticks=self.alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
        return []
