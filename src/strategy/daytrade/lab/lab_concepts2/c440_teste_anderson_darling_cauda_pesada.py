"""TesteAndersonDarlingCaudaPesada -- substituto informal do teste de Anderson-Darling.

SUBSTITUICAO DECLARADA (catalogo pede para pular o teste formal, que
exige tabela critica): usa a razao entre o percentil 99 e o percentil 90
dos retornos ABSOLUTOS numa janela movel -- um proxy simples de "peso de
cauda" (quanto mais a cauda extrema se destaca do corpo da distribuicao,
maior a razao) -- comparada a um LIMIAR EMPIRICO, o percentil 90 da
propria historia rolante dessa razao. Razao anormalmente alta indica
cauda pesada -- entra em REVERSAO contra a direcao da ultima barra
extrema. Sai apos N barras (`bars_held`) ou pelo stop/alvo.
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
class TesteAndersonDarlingCaudaPesada(IntradayStrategy):
    """Razao p99/p90 dos retornos absolutos (proxy de peso de cauda) vs limiar empirico."""

    name: str = "c440_teste_anderson_darling_cauda_pesada"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    janela_historico_razao: int = 30
    percentil_gatilho: float = 90.0
    saida_barras: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _historico_razao: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._historico_razao = deque(maxlen=self.janela_historico_razao)

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
        razao = None
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)
            if len(self._retornos) == self.janela:
                abs_r = np.abs(np.array(self._retornos))
                p90 = np.percentile(abs_r, 90)
                p99 = np.percentile(abs_r, 99)
                if p90 > 1e-12:
                    razao = float(p99 / p90)
                    self._historico_razao.append(razao)

        if positions:
            pos = positions[0]
            if pos.bars_held >= self.saida_barras:
                return [Exit(reason=f"{self.name}_prazo")]
            return []

        if razao is None or len(self._historico_razao) < 10 or not self._retornos:
            return []
        limiar = np.percentile(np.array(self._historico_razao), self.percentil_gatilho)
        if razao < limiar:
            return []

        ultimo = self._retornos[-1]
        if ultimo == 0:
            return []
        tick = self.tick_size
        if ultimo > 0:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("long", bar.close - self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
