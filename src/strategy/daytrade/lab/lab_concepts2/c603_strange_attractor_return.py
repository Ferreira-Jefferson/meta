"""Catálogo caos/fractais, item 4: StrangeAttractorReturn.

APROXIMAÇÃO HEURÍSTICA de "atrator estranho": embedding (ret[t], ret[t-1],
ret[t-2]) tratado como nuvem de pontos; dois centróides simples (bacia
positiva = média dos pontos com ret[t]>0, bacia negativa = média dos pontos
com ret[t]<0), calculados rolling — não é clustering k-means de verdade,
só a média condicional ao sinal, que já serve de "bacia" para o teste.

Entra quando o ponto atual troca de bacia mais próxima rumo à bacia de
tendência (ex.: estava mais perto da bacia negativa e passa a estar mais
perto da positiva) — segue a direção da bacia de destino.
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


@dataclass
class StrangeAttractorReturn(IntradayStrategy):
    """Nuvem de pontos (ret_t, ret_t-1, ret_t-2) com duas bacias (centróides
    condicionais ao sinal); entra na direção da bacia quando o ponto migra
    de uma bacia para a outra."""

    name: str = "strange_attractor_return"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=42), init=False, repr=False)
    _bacia_anterior: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 3)
        self._bacia_anterior = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if not positions and len(self._closes) == self._closes.maxlen:
            precos = np.array(self._closes)
            retornos = np.diff(precos)
            pontos = np.column_stack([retornos[2:], retornos[1:-1], retornos[:-2]])
            positivos = pontos[pontos[:, 0] > 0]
            negativos = pontos[pontos[:, 0] < 0]
            if len(positivos) >= 3 and len(negativos) >= 3:
                centro_pos = positivos.mean(axis=0)
                centro_neg = negativos.mean(axis=0)
                ponto_atual = pontos[-1]
                dist_pos = np.linalg.norm(ponto_atual - centro_pos)
                dist_neg = np.linalg.norm(ponto_atual - centro_neg)
                bacia_atual = 1 if dist_pos < dist_neg else -1
                if self._bacia_anterior == -1 and bacia_atual == 1:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif self._bacia_anterior == 1 and bacia_atual == -1:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                self._bacia_anterior = bacia_atual

        self._closes.append(bar.close)
        return acao
