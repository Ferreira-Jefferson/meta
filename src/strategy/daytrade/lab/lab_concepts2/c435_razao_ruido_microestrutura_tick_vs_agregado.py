"""RazaoRuidoMicroestruturaTickVsAgregado -- ruido de microestrutura via razao de variancias.

Compara a variancia dos retornos BARRA-A-BARRA com a variancia dos
retornos agregados em blocos de `k` barras, dividida por `k` (se nao
houvesse ruido de microestrutura as duas seriam iguais, pela aditividade
da variancia sob independencia). Razao ALTA indica que o ruido de curto
prazo domina sobre o componente "real" de mais baixa frequencia -- opera
reversao (contra a ultima barra). Sai quando a razao cai de volta abaixo
de um limiar mais baixo, ou pelo stop/alvo.
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
class RazaoRuidoMicroestruturaTickVsAgregado(IntradayStrategy):
    """Reversao quando a variancia barra-a-barra domina sobre a agregada em blocos."""

    name: str = "c435_razao_ruido_microestrutura_tick_vs_agregado"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 50
    k_bloco: int = 5
    limiar_entrada: float = 1.5
    limiar_saida: float = 1.15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=50), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)

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

    def _razao(self) -> float | None:
        if len(self._retornos) < self.janela:
            return None
        arr = np.array(self._retornos)
        n_blocos = self.janela // self.k_bloco
        if n_blocos < 2:
            return None
        blocos = arr[:n_blocos * self.k_bloco].reshape(n_blocos, self.k_bloco).sum(axis=1)
        var_bloco = blocos.var(ddof=0)
        if var_bloco <= 1e-14:
            return None
        var_barra = arr.var(ddof=0)
        return float(var_barra / (var_bloco / self.k_bloco))

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        razao = self._razao()

        if positions:
            if razao is not None and razao <= self.limiar_saida:
                return [Exit(reason=f"{self.name}_ruido_normalizou")]
            return []

        if razao is None or razao < self.limiar_entrada or not self._retornos:
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
