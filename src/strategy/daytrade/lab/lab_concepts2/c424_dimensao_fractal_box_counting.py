"""DimensaoFractalBoxCounting -- dimensao fractal do preco por contagem de caixas.

Box-counting manual sobre a serie de precos normalizada (eixo tempo e
eixo preco escalados para `[0,1]`): para varias escalas `eps`, conta
quantas celulas de uma grade `1/eps x 1/eps` contem pelo menos um ponto
da serie, e ajusta `log(N)` contra `log(1/eps)` -- a inclinacao e' a
dimensao fractal `D`. Dimensao ALTA (serie preenche mais o plano, mais
irregular) indica REVERSAO (entra contra a ultima barra); dimensao BAIXA
(mais lisa/direcional) indica TENDENCIA (entra a favor). Sai pelo
stop/alvo fixos.
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

_EPSILONS_PADRAO = (0.02, 0.05, 0.10, 0.20)


def _dimensao_box_counting(precos: np.ndarray, epsilons=_EPSILONS_PADRAO) -> float | None:
    n = len(precos)
    if n < 10:
        return None
    pmin, pmax = precos.min(), precos.max()
    if pmax - pmin <= 1e-9:
        return None
    idx = np.arange(n) / (n - 1)
    y = (precos - pmin) / (pmax - pmin)
    log_eps, log_n = [], []
    for eps in epsilons:
        n_grade = max(1, int(round(1.0 / eps)))
        ix = np.minimum((idx * n_grade).astype(int), n_grade - 1)
        iy = np.minimum((y * n_grade).astype(int), n_grade - 1)
        n_ocupadas = len(set(zip(ix.tolist(), iy.tolist())))
        if n_ocupadas > 0:
            log_eps.append(np.log(1.0 / eps))
            log_n.append(np.log(n_ocupadas))
    if len(log_eps) < 3:
        return None
    slope, _intercepto = np.polyfit(log_eps, log_n, 1)
    return float(slope)


@dataclass
class DimensaoFractalBoxCounting(IntradayStrategy):
    """Regime de tendencia/reversao pela dimensao fractal (box-counting) do preco."""

    name: str = "c424_dimensao_fractal_box_counting"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    limiar_alto: float = 1.55
    limiar_baixo: float = 1.20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)

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
        ultimo_close = self._closes[-1] if self._closes else None
        self._closes.append(bar.close)

        if positions:
            return []
        if len(self._closes) < self.janela or ultimo_close is None:
            return []

        d = _dimensao_box_counting(np.array(self._closes))
        if d is None:
            return []
        ultimo_retorno = bar.close - ultimo_close
        if ultimo_retorno == 0:
            return []
        tick = self.tick_size
        if d >= self.limiar_alto:
            vai_subir = ultimo_retorno < 0
        elif d <= self.limiar_baixo:
            vai_subir = ultimo_retorno > 0
        else:
            return []
        if vai_subir:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("short", bar.close + self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
