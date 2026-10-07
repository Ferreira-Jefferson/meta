"""Catálogo termodinâmica/informação, item 37: DensidadeDeProbabilidadeGaussKurtosis.

APROXIMAÇÃO: assimetria (skew) e curtose rolling dos retornos, fórmulas
manuais (momentos centrais / desvio-padrão, sem lib). Entra quando a
assimetria inverte de sinal (cruzamento de zero); zera posição em aberto
quando a curtose dispara (cauda gorda, risco de evento).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class DensidadeDeProbabilidadeGaussKurtosis(IntradayStrategy):
    """Assimetria e curtose rolling (manuais) dos retornos: entra quando a
    assimetria inverte de sinal, na direção do novo sinal; sai a mercado se
    a curtose disparar acima do limiar com posição aberta."""

    name: str = "densidade_probabilidade_gauss_kurtosis"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    limiar_curtose: float = 5.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=31), init=False, repr=False)
    _skew_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 1)
        self._skew_anterior = None

    @staticmethod
    def _skew_kurtosis(retornos: list[float]) -> tuple[float, float]:
        n = len(retornos)
        media = sum(retornos) / n
        desvios = [r - media for r in retornos]
        m2 = sum(d ** 2 for d in desvios) / n
        m3 = sum(d ** 3 for d in desvios) / n
        m4 = sum(d ** 4 for d in desvios) / n
        std = m2 ** 0.5
        if std == 0:
            return 0.0, 0.0
        skew = m3 / (std ** 3)
        kurt = m4 / (std ** 4)
        return skew, kurt

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if len(self._closes) == self._closes.maxlen:
            retornos = [b - a for a, b in zip(self._closes, list(self._closes)[1:])]
            skew, kurt = self._skew_kurtosis(retornos)

            if positions and kurt >= self.limiar_curtose:
                acao = [Exit(reason=f"{self.name}_curtose_alta")]
            elif not positions and self._skew_anterior is not None:
                inverteu_para_positivo = self._skew_anterior <= 0 < skew
                inverteu_para_negativo = self._skew_anterior >= 0 > skew
                if inverteu_para_positivo:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif inverteu_para_negativo:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
            self._skew_anterior = skew

        self._closes.append(bar.close)
        return acao
