"""EntropiaPermutacaoOrdinal -- entropia de padroes ordinais de Bandt-Pompe.

Converte janelas de `k` barras consecutivas em padroes ORDINAIS (a
permutacao de rank relativo dos `k` valores, `k!` possibilidades) e mede
a entropia de Shannon (manual) da distribuicao desses padroes numa
janela movel de observacoes. Entropia BAIXA indica um padrao ordinal
dominante -- se o padrao mais frequente for monotono crescente, entra
comprado; se monotono decrescente, entra vendido; qualquer outro padrao
dominante nao gera sinal (a estrategia so opera as duas formas mais
"acionaveis" da permutacao). Sai pelo stop/alvo fixos.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class EntropiaPermutacaoOrdinal(IntradayStrategy):
    """Entropia de padroes ordinais (Bandt-Pompe) sobre janelas de k barras."""

    name: str = "c413_entropia_permutacao_ordinal"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    k_padrao: int = 3
    janela_padroes: int = 30
    min_observacoes: int = 20
    limiar_entropia_bits: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _padroes: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.k_padrao)
        self._padroes = deque(maxlen=self.janela_padroes)

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
        if len(self._closes) == self.k_padrao:
            padrao = tuple(np.argsort(np.array(self._closes)))
            self._padroes.append(padrao)

        if positions:
            return []

        if len(self._padroes) < self.min_observacoes:
            return []
        contagem = Counter(self._padroes)
        total = len(self._padroes)
        entropia = -sum((c / total) * np.log2(c / total) for c in contagem.values())
        if entropia >= self.limiar_entropia_bits:
            return []

        padrao_dominante, _freq = contagem.most_common(1)[0]
        crescente = tuple(range(self.k_padrao))
        decrescente = tuple(range(self.k_padrao - 1, -1, -1))
        tick = self.tick_size
        if padrao_dominante == crescente:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if padrao_dominante == decrescente:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
