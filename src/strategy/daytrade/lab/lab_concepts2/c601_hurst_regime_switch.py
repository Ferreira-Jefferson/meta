"""Catálogo caos/fractais, item 2: HurstRegimeSwitch.

APROXIMAÇÃO HEURÍSTICA do expoente de Hurst — R/S manual (rescaled range)
sobre sub-janelas de tamanhos crescentes dentro da janela rolling, ajuste
log-log por mínimos quadrados (`np.polyfit`), sem qualquer correção de viés
da literatura formal. Terreno já tocado neste projeto em outras categorias
(ver notas de osciladores exóticos) — reteste com mecanismo próprio.

H > 0,55: entra a favor do rompimento (tendência persistente). H < 0,45:
entra contra (fade, reversão à média). Sai (Exit) quando H cruza de volta
por 0,5 com posição aberta.
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


def _hurst_rs(serie: np.ndarray) -> float | None:
    tamanhos = [n for n in (8, 16, 32) if n <= len(serie) // 2]
    if len(tamanhos) < 2:
        return None
    log_n, log_rs = [], []
    for n in tamanhos:
        n_blocos = len(serie) // n
        rs_vals = []
        for i in range(n_blocos):
            bloco = serie[i * n:(i + 1) * n]
            media = bloco.mean()
            desvios = np.cumsum(bloco - media)
            r = desvios.max() - desvios.min()
            s = bloco.std()
            if s > 1e-12:
                rs_vals.append(r / s)
        if rs_vals:
            log_n.append(np.log(n))
            log_rs.append(np.log(np.mean(rs_vals)))
    if len(log_n) < 2:
        return None
    inclinacao, _ = np.polyfit(log_n, log_rs, 1)
    return float(inclinacao)


@dataclass
class HurstRegimeSwitch(IntradayStrategy):
    """Expoente de Hurst rolling por R/S manual; H alto segue rompimento,
    H baixo faz fade, saída quando H recruza 0,5."""

    name: str = "hurst_regime_switch"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 64
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _retornos: deque = field(default_factory=lambda: deque(maxlen=64), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=64), init=False, repr=False)
    _h_estado: float = field(default=0.5, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._retornos = deque(maxlen=self.janela)
        self._closes = deque(maxlen=2)
        self._h_estado = 0.5

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if len(self._closes) == 2:
            self._retornos.append(self._closes[-1] - self._closes[-2])

        if len(self._retornos) == self._retornos.maxlen:
            h = _hurst_rs(np.array(self._retornos))
            if h is not None:
                h_anterior = self._h_estado
                self._h_estado = h
                if positions:
                    cruzou = (h_anterior - 0.5) * (h - 0.5) < 0
                    if cruzou:
                        acao = [Exit(reason=self.name)]
                else:
                    tendencia_alta = bar.close > self._closes[-1] if self._closes else False
                    if h > 0.55:
                        lado_long = tendencia_alta
                    elif h < 0.45:
                        lado_long = not tendencia_alta
                    else:
                        lado_long = None
                    if lado_long is True:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif lado_long is False:
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
