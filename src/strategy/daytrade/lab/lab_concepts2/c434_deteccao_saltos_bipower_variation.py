"""DeteccaoSaltosBipowerVariation -- reversao apos salto detectado por Bipower Variation.

Bipower Variation (`BV = (pi/2) * soma(|r_t|*|r_{t-1}|)`, formula
fechada, sem lib) estima a variancia integrada ROBUSTA a saltos; a
diferenca contra a variancia realizada simples (`RV = soma(r_t^2)`)
isola o componente de SALTO, `J = max(RV-BV, 0)`. Quando `J` excede um
limiar empirico (percentil da propria historia rolante) E a ultima
barra teve retorno anormalmente grande frente a BV, um salto foi
detectado -- entra em REVERSAO contra a direcao do salto (aposta em
retracao parcial). Sai apos N barras (`bars_held`) ou pelo stop/alvo.
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


@dataclass
class DeteccaoSaltosBipowerVariation(IntradayStrategy):
    """Reversao contra saltos detectados via Bipower Variation vs variancia realizada."""

    name: str = "c434_deteccao_saltos_bipower_variation"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    k_salto: float = 3.0
    janela_historico_j: int = 30
    percentil_gatilho: float = 90.0
    saida_barras: int = 15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _historico_j: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._historico_j = deque(maxlen=self.janela_historico_j)

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
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        if positions:
            pos = positions[0]
            if pos.bars_held >= self.saida_barras:
                return [Exit(reason=f"{self.name}_prazo")]
            return []

        if len(self._retornos) < self.janela:
            return []
        r = np.array(self._retornos)
        rv = float(np.sum(r ** 2))
        bv = float((np.pi / 2.0) * np.sum(np.abs(r[1:]) * np.abs(r[:-1])))
        j = max(rv - bv, 0.0)
        self._historico_j.append(j)
        if len(self._historico_j) < 10:
            return []
        limiar_j = np.percentile(np.array(self._historico_j), self.percentil_gatilho)

        n = len(r)
        vol_bv = np.sqrt(bv / n) if n > 0 else 0.0
        ultimo = r[-1]
        salto_detectado = j >= limiar_j and vol_bv > 1e-12 and abs(ultimo) > self.k_salto * vol_bv
        if not salto_detectado:
            return []

        tick = self.tick_size
        if ultimo > 0:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("long", bar.close - self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
