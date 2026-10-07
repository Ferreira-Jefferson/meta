"""Catálogo caos/fractais, item 1: LyapunovAproximado.

APROXIMAÇÃO HEURÍSTICA, não o expoente de Lyapunov formal da literatura de
caos (não há embedding + busca de vizinho mais próximo com reconstrução de
Takens aqui — só uma razão causal log(|retorno_t|/|retorno_t-1|) suavizada
como proxy de "as perturbações estão amplificando (positivo) ou amortecendo
(negativo)"). Terreno já tocado e refutado neste projeto como osciladores
exóticos (`wdo_quantico_oscilador_refutado_2026_09_24.md`) — implementado de
novo aqui com mecanismo próprio, honestamente rotulado como reteste.

Entra na direção do último retorno quando a média rolling do log-razão cruza
de negativo para positivo; sai (Exit) quando volta a cruzar para negativo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class LyapunovAproximado(IntradayStrategy):
    """Proxy causal de divergência de trajetórias vizinhas (razão log entre
    retornos consecutivos, suavizada); cruza de negativo (estável) para
    positivo (caótico) dispara entrada na direção do último retorno."""

    name: str = "lyapunov_aproximado"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 10
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=32), init=False, repr=False)
    _lyap_estado: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 2)
        self._lyap_estado = 0.0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if len(self._closes) >= self.janela + 1:
            closes = np.array(self._closes)
            retornos = np.diff(closes)
            retornos = retornos[np.abs(retornos) > 1e-9]
            if len(retornos) >= 2:
                razoes = np.log(np.abs(retornos[1:]) / np.abs(retornos[:-1]))
                lyap_novo = float(np.mean(razoes))
                estado_anterior = self._lyap_estado
                self._lyap_estado = lyap_novo
                if positions:
                    if estado_anterior >= 0 and lyap_novo < 0:
                        acao = [Exit(reason=self.name)]
                elif estado_anterior < 0 <= lyap_novo:
                    ultimo_retorno = closes[-1] - closes[-2]
                    if ultimo_retorno > 0:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif ultimo_retorno < 0:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]

        self._closes.append(bar.close)
        return acao
