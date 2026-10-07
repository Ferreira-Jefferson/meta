"""Catálogo volume/microestrutura, item 80: DivergenciaEntreTickVolumeEPrecoNaTendencia.

Précompute `tick_volume` em `initialize` (contagem de negócios, distinto do
`bar.volume`/`real_volume`). Entra a favor de uma sequência de barras
direcionais; enquanto a posição está aberta, sai antes da exaustão quando
o tick_volume sobe (inclinação positiva) e o range por barra cai
(inclinação negativa) na mesma janela -- usa contagem de negócios em vez
de volume financeiro.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class DivergenciaEntreTickVolumeEPrecoNaTendencia(IntradayStrategy):
    """Entra a favor de uma sequência de barras direcionais; sai antes da
    exaustão quando tick_volume sobe e o range por barra cai."""

    name: str = "divergencia_tick_volume_preco_tendencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_seq: int = 4
    janela_exaustao: int = 10
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _tick_volume_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _cores: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)
    _tick_vols: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _ranges: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        self._tick_volume_por_ts = bars["tick_volume"].to_dict()

    def on_session_start(self, session_date) -> None:
        self._cores = deque(maxlen=self.janela_seq)
        self._tick_vols = deque(maxlen=self.janela_exaustao)
        self._ranges = deque(maxlen=self.janela_exaustao)

    def _ordem(self, lado: str, nivel: float) -> list[IntradayAction]:
        if lado == "long":
            limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
        else:
            limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
        return [EnterLimit(
            side=lado, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        tick_vol = self._tick_volume_por_ts.get(ts, 0.0)
        self._tick_vols.append(tick_vol)
        self._ranges.append(bar.high - bar.low)

        if positions:
            if len(self._tick_vols) == self._tick_vols.maxlen:
                x = np.arange(len(self._tick_vols), dtype=float)
                slope_tv = float(np.polyfit(x, np.array(self._tick_vols, dtype=float), 1)[0])
                slope_range = float(np.polyfit(x, np.array(self._ranges, dtype=float), 1)[0])
                if slope_tv > 0 and slope_range < 0:
                    acao = [Exit(reason=self.name)]
        elif len(self._cores) == self._cores.maxlen:
            cores = list(self._cores)
            if len(set(cores)) == 1 and cores[0] != 0:
                acao = self._ordem("long" if cores[0] > 0 else "short", bar.close)

        cor = 1 if bar.close > bar.open else (-1 if bar.close < bar.open else 0)
        self._cores.append(cor)
        return acao
