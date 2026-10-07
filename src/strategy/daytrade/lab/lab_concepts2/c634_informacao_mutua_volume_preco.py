"""Catálogo termodinâmica/informação, item 35: InformacaoMutuaVolumePreco.

APROXIMAÇÃO: informação mútua rolling (manual, sem lib) entre o bin de
volume da barra t (alto/baixo vs mediana da janela) e o sinal do retorno
da barra t+1, discretizados em 2x2. Quando a informação mútua da janela
está alta, um spike de volume na barra atual habilita entrada na direção
que historicamente dominou o par (volume alto, retorno seguinte).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class InformacaoMutuaVolumePreco(IntradayStrategy):
    """Informação mútua (bits, manual) entre bin de volume e sinal do
    retorno seguinte numa janela rolling; em regime de alta informação
    mútua, um spike de volume dispara entrada na direção historicamente
    dominante do par."""

    name: str = "informacao_mutua_volume_preco"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    limiar_mi_bits: float = 0.05
    fator_spike: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _pares: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _vol_pendente: float | None = field(default=None, init=False, repr=False)
    _close_pendente: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela)
        self._pares = deque(maxlen=self.janela)
        self._vol_pendente = None
        self._close_pendente = None

    @staticmethod
    def _entropia(probs: list[float]) -> float:
        return -sum(p * math.log2(p) for p in probs if p > 0)

    def _informacao_mutua(self, mediana_vol: float) -> tuple[float, dict]:
        pares = list(self._pares)
        n = len(pares)
        contagem_conjunta: dict[tuple[int, int], int] = {}
        contagem_vol = {0: 0, 1: 0}
        contagem_ret = {0: 0, 1: 0}
        for vol_bin, ret_bin in pares:
            contagem_conjunta[(vol_bin, ret_bin)] = contagem_conjunta.get((vol_bin, ret_bin), 0) + 1
            contagem_vol[vol_bin] += 1
            contagem_ret[ret_bin] += 1

        h_vol = self._entropia([c / n for c in contagem_vol.values()])
        h_ret = self._entropia([c / n for c in contagem_ret.values()])
        h_conjunta = self._entropia([c / n for c in contagem_conjunta.values()])
        mi = h_vol + h_ret - h_conjunta
        return mi, contagem_conjunta

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if self._vol_pendente is not None and self._close_pendente is not None:
            mediana = sorted(self._vols)[len(self._vols) // 2] if self._vols else self._vol_pendente
            vol_bin = 1 if self._vol_pendente > mediana else 0
            ret_bin = 1 if bar.close > self._close_pendente else 0
            self._pares.append((vol_bin, ret_bin))

        if not positions and len(self._pares) == self._pares.maxlen and self._vols:
            mediana = sorted(self._vols)[len(self._vols) // 2]
            mi, conjunta = self._informacao_mutua(mediana)
            spike = bar.volume > self.fator_spike * (sum(self._vols) / len(self._vols))
            if mi >= self.limiar_mi_bits and spike:
                n_alto_up = conjunta.get((1, 1), 0)
                n_alto_down = conjunta.get((1, 0), 0)
                if n_alto_up != n_alto_down:
                    lado = "long" if n_alto_up > n_alto_down else "short"
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

        self._vols.append(bar.volume)
        self._vol_pendente = bar.volume
        self._close_pendente = bar.close
        return acao
