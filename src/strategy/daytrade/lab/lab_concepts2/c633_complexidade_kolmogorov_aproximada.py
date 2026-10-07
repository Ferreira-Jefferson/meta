"""Catálogo termodinâmica/informação, item 34: ComplexidadeKolmogorovAproximada.

APROXIMAÇÃO: complexidade de Kolmogorov não é computável; aproxima-se pela
COMPRESSIBILIDADE — tamanho do run-length encoding (RLE, implementado à
mão) da sequência binária de direção das últimas N velas. Poucos "runs"
(sequência repetitiva, baixa complexidade) dispara entrada de continuação
no sentido do run atual.
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
class ComplexidadeKolmogorovAproximada(IntradayStrategy):
    """Complexidade aproximada = nº de runs do RLE da sequência binária de
    direção / tamanho da janela. Baixa complexidade (poucos runs) dispara
    entrada de continuação no sentido do run corrente."""

    name: str = "complexidade_kolmogorov_aproximada"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    limiar_complexidade_norm: float = 0.35
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _direcoes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._direcoes = deque(maxlen=self.janela)

    @staticmethod
    def _n_runs(seq: list[int]) -> int:
        if not seq:
            return 0
        runs = 1
        for a, b in zip(seq, seq[1:]):
            if a != b:
                runs += 1
        return runs

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._direcoes) == self._direcoes.maxlen:
            seq = list(self._direcoes)
            runs = self._n_runs(seq)
            complexidade_norm = runs / len(seq)
            if complexidade_norm < self.limiar_complexidade_norm and seq[-1] != 0:
                lado = "long" if seq[-1] > 0 else "short"
                if lado == "long":
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=lado, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        if bar.close > bar.open:
            self._direcoes.append(1)
        elif bar.close < bar.open:
            self._direcoes.append(-1)
        else:
            self._direcoes.append(0)
        return acao
