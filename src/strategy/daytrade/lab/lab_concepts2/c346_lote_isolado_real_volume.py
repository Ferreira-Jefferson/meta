"""Catálogo volume/microestrutura, item 47: LoteIsoladoDeRealVolume.

Précompute `real_volume` em `initialize` (distinto de `bar.volume`, que o
motor já normaliza real/tick). Uma barra cujo real_volume fica vários
desvios-padrão acima da média, dentro de uma consolidação de preço, dispara
entrada na direção do close em relação ao open dessa barra.
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
class LoteIsoladoDeRealVolume(IntradayStrategy):
    """Real_volume isolado (z-score alto) dentro de consolidação de preço
    -- entra na direção do close vs open da barra isolada."""

    name: str = "lote_isolado_real_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_rv: int = 20
    k_desvios: float = 3.0
    janela_consolidacao: int = 10
    limiar_consolidacao_ticks: int = 10
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _real_volume_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _rv_janela: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        self._real_volume_por_ts = bars["real_volume"].to_dict()

    def on_session_start(self, session_date) -> None:
        self._rv_janela = deque(maxlen=self.janela_rv)
        self._highs = deque(maxlen=self.janela_consolidacao)
        self._lows = deque(maxlen=self.janela_consolidacao)

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
        rv = self._real_volume_por_ts.get(ts, bar.volume)

        if (not positions and len(self._rv_janela) == self._rv_janela.maxlen
                and len(self._highs) == self._highs.maxlen):
            serie = pd.Series(self._rv_janela)
            media = float(serie.mean())
            desvio = float(serie.std())
            consolidado = (max(self._highs) - min(self._lows)) <= (
                self.limiar_consolidacao_ticks * self.tick_size
            )
            if desvio > 0 and consolidado and (rv - media) / desvio > self.k_desvios:
                if bar.close > bar.open:
                    acao = self._ordem("long", bar.close)
                elif bar.close < bar.open:
                    acao = self._ordem("short", bar.close)

        self._rv_janela.append(rv)
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
