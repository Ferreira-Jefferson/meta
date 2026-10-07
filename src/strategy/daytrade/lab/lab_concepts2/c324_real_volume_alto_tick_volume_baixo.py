"""Catálogo volume/microestrutura, item 25: RealVolumeAltoTickVolumeBaixo.

Espelho do item 24: poucos negócios GRANDES (real_volume alto por
negócio, tick_volume baixo, razão tick/real BAIXA) — presença
institucional — segue a direção do fechamento da barra (trend-follow).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class RealVolumeAltoTickVolumeBaixo(IntradayStrategy):
    """Razão tick_volume/real_volume baixa (poucos negócios grandes,
    presença institucional) — segue a direção do fechamento da barra."""

    name: str = "real_volume_alto_tick_volume_baixo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_razao: int = 20
    fator_razao_baixa: float = 0.7
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _tick_vol_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _real_vol_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _razoes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if "tick_volume" in bars.columns and "real_volume" in bars.columns:
            self._tick_vol_por_ts = {ts: float(v) for ts, v in bars["tick_volume"].items()}
            self._real_vol_por_ts = {ts: float(v) for ts, v in bars["real_volume"].items()}
        else:
            self._tick_vol_por_ts = {}
            self._real_vol_por_ts = {}

    def on_session_start(self, session_date) -> None:
        self._razoes = deque(maxlen=self.janela_razao)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        tv = self._tick_vol_por_ts.get(ts)
        rv = self._real_vol_por_ts.get(ts)
        razao = (tv / rv) if (tv is not None and rv and rv > 0) else None

        if (not positions and razao is not None and bar.close != bar.open
                and len(self._razoes) == self._razoes.maxlen):
            razao_ma = sum(self._razoes) / len(self._razoes)
            if razao < self.fator_razao_baixa * razao_ma:
                nivel = bar.close
                if bar.close > bar.open:
                    limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                else:
                    limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        if razao is not None:
            self._razoes.append(razao)
        return acao
