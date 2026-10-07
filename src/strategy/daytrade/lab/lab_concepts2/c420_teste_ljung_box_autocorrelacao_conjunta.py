"""TesteLjungBoxAutocorrelacaoConjunta -- substituto informal do teste de Ljung-Box.

SUBSTITUICAO DECLARADA (catalogo pede para pular o p-valor qui-quadrado
formal): usa a soma das autocorrelacoes ao quadrado ate o lag `k_max`
como estatistica informal (a mesma soma que alimentaria o Ljung-Box,
sem a normalizacao nem a comparacao a uma tabela critica), comparada a
um LIMIAR EMPIRICO -- o percentil 90 da PROPRIA historia rolante dessa
estatistica. Quando a estatistica atual excede o limiar (autocorrelacao
conjunta anormalmente alta), usa o sinal da autocorrelacao de lag 1 para
decidir a direcao: positiva segue a ultima barra, negativa opera contra
ela. Sai pelo stop/alvo fixos.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def _soma_autocorr_quadrado(arr: np.ndarray, k_max: int) -> tuple[float, float] | None:
    soma = 0.0
    corr_lag1 = None
    algum = False
    for lag in range(1, k_max + 1):
        if len(arr) <= lag + 5:
            break
        a, b = arr[:-lag], arr[lag:]
        if a.std(ddof=0) <= 1e-12 or b.std(ddof=0) <= 1e-12:
            continue
        corr = float(np.corrcoef(a, b)[0, 1])
        soma += corr * corr
        algum = True
        if lag == 1:
            corr_lag1 = corr
    if not algum or corr_lag1 is None:
        return None
    return soma, corr_lag1


@dataclass
class TesteLjungBoxAutocorrelacaoConjunta(IntradayStrategy):
    """Soma de autocorrelacoes ao quadrado (proxy de Ljung-Box) vs limiar empirico."""

    name: str = "c420_teste_ljung_box_autocorrelacao_conjunta"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    k_max: int = 8
    janela_historico_stat: int = 40
    percentil_gatilho: float = 90.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _historico_stat: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._historico_stat = deque(maxlen=self.janela_historico_stat)

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

        resultado = None
        if len(self._retornos) == self.janela:
            resultado = _soma_autocorr_quadrado(np.array(self._retornos), self.k_max)
            if resultado is not None:
                self._historico_stat.append(resultado[0])

        if positions:
            return []

        if resultado is None or len(self._historico_stat) < 10:
            return []
        stat, corr_lag1 = resultado
        limiar = np.percentile(np.array(self._historico_stat), self.percentil_gatilho)
        if stat < limiar:
            return []

        ultimo = self._retornos[-1]
        if ultimo == 0:
            return []
        segue = corr_lag1 > 0
        vai_subir = (ultimo > 0) == segue
        tick = self.tick_size
        if vai_subir:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
