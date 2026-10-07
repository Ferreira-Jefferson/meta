"""Catálogo volume/microestrutura, item 7: AbsorcaoNaResistencia.

Espelho do item 6: `n_toques` barras tocando a mesma máxima (±tolerância),
volume crescente e range decrescente (absorção de compra no nível) — entra
vendido quando o range expande para baixo, rompendo a mínima recente.
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
class AbsorcaoNaResistencia(IntradayStrategy):
    """`n_toques` barras tocando a mesma máxima, volume crescente e range
    decrescente (absorção); entra vendido na expansão de range para
    baixo."""

    name: str = "absorcao_na_resistencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    n_toques: int = 3
    tolerancia_ticks: int = 2
    fator_expansao: float = 1.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _janela: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._janela = deque(maxlen=self.n_toques)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low
        tol = self.tolerancia_ticks * self.tick_size

        if not positions and len(self._janela) == self._janela.maxlen:
            highs = [b.high for b in self._janela]
            vols = [b.volume for b in self._janela]
            ranges = [b.high - b.low for b in self._janela]
            mesma_maxima = (max(highs) - min(highs)) <= tol
            vol_crescente = all(vols[i] < vols[i + 1] for i in range(len(vols) - 1))
            range_decrescente = all(ranges[i] > ranges[i + 1] for i in range(len(ranges) - 1))
            if mesma_maxima and vol_crescente and range_decrescente:
                fundo_recente = min(b.low for b in self._janela)
                if rng > self.fator_expansao * ranges[-1] and bar.close < fundo_recente:
                    nivel = bar.close
                    limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._janela.append(bar)
        return acao
