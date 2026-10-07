"""Catálogo autômatos/ML/jogos, item 61: CadeiaDeMarkovEstados.

Discretiza o retorno de cada barra em 5 estados por quantis de uma
janela histórica rolante (alta forte/fraca, neutro, baixa fraca/forte);
mantém matriz de transição empírica 5x5 e entra quando o estado seguinte
mais provável é um extremo com probabilidade acima do limiar.
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

N_ESTADOS = 5  # 0=baixa forte, 1=baixa fraca, 2=neutro, 3=alta fraca, 4=alta forte


@dataclass
class CadeiaDeMarkovEstados(IntradayStrategy):
    """5 estados de retorno por quantis de uma janela rolante; matriz de
    transição 5x5 empírica atualizada barra a barra; entra quando o
    estado seguinte mais provável é extremo e supera o limiar."""

    name: str = "cadeia_de_markov_estados"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_quantis: int = 200
    min_amostras_transicao: int = 20
    limiar_probabilidade: float = 0.35
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _retornos_hist: deque = field(default_factory=lambda: deque(maxlen=200), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _estado_anterior: int | None = field(default=None, init=False, repr=False)
    _contagens: np.ndarray = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._contagens is None:
            self._contagens = np.zeros((N_ESTADOS, N_ESTADOS))
        if self._retornos_hist.maxlen != self.janela_quantis:
            self._retornos_hist = deque(self._retornos_hist, maxlen=self.janela_quantis)
        self._close_anterior = None
        self._estado_anterior = None

    def _classificar(self, retorno: float) -> int:
        q20, q40, q60, q80 = np.quantile(np.array(self._retornos_hist), [0.2, 0.4, 0.6, 0.8])
        if retorno <= q20:
            return 0
        if retorno <= q40:
            return 1
        if retorno <= q60:
            return 2
        if retorno <= q80:
            return 3
        return 4

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._contagens is None:
            self._contagens = np.zeros((N_ESTADOS, N_ESTADOS))

        if self._close_anterior is not None:
            retorno = (bar.close - self._close_anterior) / self._close_anterior

            if len(self._retornos_hist) >= self.min_amostras_transicao:
                estado_atual = self._classificar(retorno)
                if self._estado_anterior is not None:
                    self._contagens[self._estado_anterior, estado_atual] += 1

                if not positions:
                    linha = self._contagens[estado_atual]
                    total = linha.sum()
                    if total >= self.min_amostras_transicao:
                        probs = linha / total
                        melhor = int(np.argmax(probs))
                        if melhor in (0, 4) and probs[melhor] > self.limiar_probabilidade:
                            side = "short" if melhor == 0 else "long"
                            if side == "long":
                                limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                            else:
                                limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side=side, limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]

                self._estado_anterior = estado_atual

            self._retornos_hist.append(retorno)

        self._close_anterior = bar.close
        return acao
