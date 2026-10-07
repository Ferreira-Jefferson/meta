"""Catálogo caos/fractais, item 3: FractalDimensionBox.

APROXIMAÇÃO HEURÍSTICA de dimensão fractal por box-counting manual: cobre o
caminho (tempo normalizado × preço normalizado) da janela com grades de dois
tamanhos de célula e conta células ocupadas; D = log(N1/N2)/log(escala).
Não é o algoritmo de referência da literatura (sem múltiplas escalas nem
regressão robusta) — só uma medida simples de "quão rugoso" é o caminho.

Dimensão baixa (~1, caminho liso/direcional) segue o momentum no rompimento
da janela; dimensão alta (~perto de 2, rugoso) fica de fora (sem entrada).
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


def _contagem_boxes(x: np.ndarray, y: np.ndarray, n_celulas: int) -> int:
    if x.max() - x.min() < 1e-12 or y.max() - y.min() < 1e-12:
        return 1
    xi = np.clip(((x - x.min()) / (x.max() - x.min()) * n_celulas).astype(int), 0, n_celulas - 1)
    yi = np.clip(((y - y.min()) / (y.max() - y.min()) * n_celulas).astype(int), 0, n_celulas - 1)
    return len(set(zip(xi.tolist(), yi.tolist())))


@dataclass
class FractalDimensionBox(IntradayStrategy):
    """Dimensão fractal por box-counting simplificado do caminho de preço;
    baixa dimensão segue o rompimento, alta dimensão fica de fora."""

    name: str = "fractal_dimension_box"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    limiar_dimensao: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if not positions and len(self._closes) == self._closes.maxlen:
            precos = np.array(self._closes)
            tempo = np.arange(len(precos), dtype=float)
            n1, n2 = _contagem_boxes(tempo, precos, 8), _contagem_boxes(tempo, precos, 16)
            if n1 > 0 and n2 > n1:
                dimensao = float(np.log(n2 / n1) / np.log(2.0))
                range_high, range_low = precos.max(), precos.min()
                if dimensao < self.limiar_dimensao:
                    if bar.close > range_high:
                        limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif bar.close < range_low:
                        limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]

        self._closes.append(bar.close)
        return acao
