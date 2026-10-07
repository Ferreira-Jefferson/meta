"""Catalogo calendario/sazonalidade, item 16: VesperaFeriadoContracao.

Conceito de CALENDARIO: dia util ANTERIOR a um gap de calendario
(`calendar_gaps`, precomputado em `initialize` -- feriado detectado via
>=1 dia util sem pregao entre duas datas de pregao consecutivas, sem
tabela externa). So' mean-reversion (fade do rompimento da faixa de
abertura), alvo reduzido (piso 4 ticks), sem posicao overnight (`Exit` no
fechamento -- reforca o que o motor ja garante).
"""
from __future__ import annotations

from datetime import time
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    calendar_gaps, montar_entrada, trading_dates,
)

_FIM_FAIXA_ABERTURA = time(9, 30)
_FLATTEN_FECHAMENTO = time(17, 50)


@dataclass
class VesperaFeriadoContracao(IntradayStrategy):
    name: str = "vespera_feriado_contracao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    stop_ticks: int = 12
    alvo_ticks_reduzido: int = 4
    entrada_ttl_bars: int = 40

    _vesperas: set = field(default_factory=set, init=False, repr=False)
    _e_vespera: bool = field(default=False, init=False, repr=False)
    _faixa_high: float | None = field(default=None, init=False, repr=False)
    _faixa_low: float | None = field(default=None, init=False, repr=False)
    _entrou_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        vesperas, _ = calendar_gaps(trading_dates(bars))
        self._vesperas = vesperas

    def on_session_start(self, session_date) -> None:
        self._e_vespera = session_date in self._vesperas
        self._faixa_high = None
        self._faixa_low = None
        self._entrou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._e_vespera:
            return []

        if ts.time() >= _FLATTEN_FECHAMENTO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_sem_overnight")]
            return []

        if ts.time() < _FIM_FAIXA_ABERTURA:
            if self._faixa_high is None:
                self._faixa_high, self._faixa_low = bar.high, bar.low
            else:
                self._faixa_high = max(self._faixa_high, bar.high)
                self._faixa_low = min(self._faixa_low, bar.low)
            return []

        if positions or self._entrou_hoje or self._faixa_high is None:
            return []

        # FADE do rompimento (mean-reversion), nao segue
        if bar.close > self._faixa_high:
            self._entrou_hoje = True
            return [montar_entrada(
                side="short", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks_reduzido, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        if bar.close < self._faixa_low:
            self._entrou_hoje = True
            return [montar_entrada(
                side="long", limit_price=bar.close, stop_ticks=self.stop_ticks,
                alvo_ticks=self.alvo_ticks_reduzido, tick_size=self.tick_size, quantity=1,
                ttl_bars=self.entrada_ttl_bars, reason=self.name,
            )]
        return []
