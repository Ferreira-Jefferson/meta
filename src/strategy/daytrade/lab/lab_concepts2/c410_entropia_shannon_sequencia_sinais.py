"""EntropiaShannonSequenciaSinais -- entropia de Shannon da sequencia alta/baixa.

Classifica cada barra em alta/baixa (fecha acima ou abaixo do fechamento
anterior) e mede a entropia de Shannon (formula manual, log2 das
proporcoes) da sequencia numa janela movel. Entropia BAIXA indica um
padrao dominante -- entra na direcao majoritaria da janela. Entropia
ALTA (perto do maximo de 1 bit) indica sequencia proxima de moeda justa
-- evita entrar. Sai quando a entropia volta a subir acima do limiar
(o padrao deixou de dominar) ou pelo stop/alvo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def _entropia_binaria(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-(p * np.log2(p) + (1 - p) * np.log2(1 - p)))


@dataclass
class EntropiaShannonSequenciaSinais(IntradayStrategy):
    """Entropia de Shannon da sequencia binaria alta/baixa das barras."""

    name: str = "c410_entropia_shannon_sequencia_sinais"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    limiar_entropia: float = 0.75
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _sinais: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _ultimo_close: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._sinais = deque(maxlen=self.janela)
        self._ultimo_close = None

    def _entrada(self, side: str, limite: float, stop_dist: float, alvo_dist: float) -> list[IntradayAction]:
        tick = self.tick_size
        limite = no_tick(limite, tick)
        if side == "long":
            stop = no_tick(limite - stop_dist, tick)
            alvo = no_tick(limite + alvo_dist, tick)
        else:
            stop = no_tick(limite + stop_dist, tick)
            alvo = no_tick(limite - alvo_dist, tick)
        return [EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._ultimo_close is not None:
            self._sinais.append(1 if bar.close >= self._ultimo_close else 0)
        self._ultimo_close = bar.close

        entropia = None
        if len(self._sinais) == self.janela:
            p_up = sum(self._sinais) / len(self._sinais)
            entropia = _entropia_binaria(p_up)

        if positions:
            if entropia is not None and entropia >= self.limiar_entropia:
                return [Exit(reason=f"{self.name}_entropia_subiu")]
            return []

        if entropia is None or entropia >= self.limiar_entropia:
            return []
        p_up = sum(self._sinais) / len(self._sinais)
        tick = self.tick_size
        if p_up > 0.5:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if p_up < 0.5:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
