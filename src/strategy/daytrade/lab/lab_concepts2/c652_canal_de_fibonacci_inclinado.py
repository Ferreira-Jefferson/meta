"""Catálogo Elliott/Wolfe, item 53: CanalDeFibonacciInclinado.

Canal de regressão linear (`numpy.polyfit`) dos closes da janela, com
bandas em razão de Fibonacci (0,618/1,0/1,618 × desvio-padrão dos
resíduos) em torno da reta. Fade na primeira vez que o preço sai da banda
1,618; reentra na continuação (a favor da inclinação) se o desvio
continuar crescendo além dela.
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
class CanalDeFibonacciInclinado(IntradayStrategy):
    """Canal de regressão (polyfit) dos closes com bandas de Fibonacci
    (0,618/1,0/1,618 × desvio dos resíduos): fade na primeira saída da
    banda 1,618, continuação se o desvio continuar crescendo além dela."""

    name: str = "canal_de_fibonacci_inclinado"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _estava_fora_banda: bool = field(default=False, init=False, repr=False)
    _desvio_anterior_abs: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)
        self._estava_fora_banda = False
        self._desvio_anterior_abs = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes.append(bar.close)

        if not positions and len(self._closes) == self._closes.maxlen:
            y = np.array(self._closes, dtype=float)
            x = np.arange(len(y), dtype=float)
            inclinacao, intercepto = np.polyfit(x, y, 1)
            ajustado = inclinacao * x + intercepto
            residuos = y - ajustado
            resid_std = float(residuos.std())

            if resid_std > 0:
                desvio_atual = float(y[-1] - ajustado[-1])
                banda_1618 = 1.618 * resid_std
                fora_agora = abs(desvio_atual) > banda_1618

                if fora_agora and not self._estava_fora_banda:
                    lado = "short" if desvio_atual > 0 else "long"
                    if lado == "short":
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    else:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side=lado, limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif (fora_agora and self._estava_fora_banda and self._desvio_anterior_abs is not None
                        and abs(desvio_atual) > self._desvio_anterior_abs):
                    lado = "long" if inclinacao > 0 else "short"
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

                self._estava_fora_banda = fora_agora
                self._desvio_anterior_abs = abs(desvio_atual)

        return acao
