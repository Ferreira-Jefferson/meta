"""Catálogo termodinâmica/informação, item 33: SegundaLeiTermodinamica.

APROXIMAÇÃO: entropia de Shannon (binária, manual) da proporção de velas de
alta na sequência de direção do pregão inteiro, acumulada incrementalmente
(sem reset de janela). Quando satura perto do máximo (~1,0, desordem
máxima) espera reversão do último movimento; quando está baixa (ordem
emergindo, muitas velas do mesmo lado) segue a tendência.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class SegundaLeiTermodinamica(IntradayStrategy):
    """Entropia binária (Shannon) acumulada da sequência de direção das
    velas do pregão: satura -> fade do último movimento; baixa -> segue a
    tendência (direção majoritária acumulada)."""

    name: str = "segunda_lei_termodinamica"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    minimo_barras: int = 20
    limiar_saturacao: float = 0.98
    limiar_ordem: float = 0.6
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _n_alta: int = field(default=0, init=False, repr=False)
    _n_baixa: int = field(default=0, init=False, repr=False)
    _ultimo_sinal: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._n_alta = 0
        self._n_baixa = 0
        self._ultimo_sinal = 0

    @staticmethod
    def _entropia_binaria(p: float) -> float:
        if p <= 0.0 or p >= 1.0:
            return 0.0
        return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        total = self._n_alta + self._n_baixa

        if not positions and total >= self.minimo_barras and self._ultimo_sinal != 0:
            p_alta = self._n_alta / total
            entropia = self._entropia_binaria(p_alta)

            if entropia >= self.limiar_saturacao:
                lado_fade = "short" if self._ultimo_sinal > 0 else "long"
                if lado_fade == "short":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=lado_fade, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif entropia <= (1 - self.limiar_ordem) and abs(p_alta - 0.5) >= self.limiar_ordem / 2:
                lado_tendencia = "long" if p_alta > 0.5 else "short"
                if lado_tendencia == "long":
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=lado_tendencia, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        if bar.close > bar.open:
            self._n_alta += 1
            self._ultimo_sinal = 1
        elif bar.close < bar.open:
            self._n_baixa += 1
            self._ultimo_sinal = -1
        return acao
