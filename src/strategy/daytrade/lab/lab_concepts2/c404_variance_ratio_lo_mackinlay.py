"""VarianceRatioLoMacKinlay -- razao de variancias 2 barras / 1 barra.

VR = var(retorno acumulado de 2 barras) / (2 x var(retorno de 1 barra)),
sobre uma janela movel de retornos -- substitui o teste formal de Lo &
MacKinlay (que usaria um p-valor assintotico) por um LIMIAR EMPIRICO
direto sobre o valor de VR, decisao do catalogo para este item.
VR<1 indica reversao (autocorrelacao negativa): entra CONTRA o retorno da
ultima barra. VR perto/acima de 1 nao tem edge -- so' nao abre posicao
nova; a saida usa stop/alvo fixos.
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
class VarianceRatioLoMacKinlay(IntradayStrategy):
    """Reversao quando a razao de variancias 2b/1b indica sobre-reversao."""

    name: str = "c404_variance_ratio_lo_mackinlay"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    limiar_vr: float = 0.80
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=61), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela + 1)

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

    def _variance_ratio(self) -> float | None:
        if len(self._retornos) < self.janela + 1:
            return None
        r = np.array(self._retornos)
        r2 = r[1:] + r[:-1]
        var1 = r.var(ddof=0)
        var2 = r2.var(ddof=0)
        if var1 <= 1e-14:
            return None
        return float(var2 / (2.0 * var1))

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        if positions:
            return []

        vr = self._variance_ratio()
        if vr is None or vr >= self.limiar_vr or not self._retornos:
            return []

        ultimo_retorno = self._retornos[-1]
        tick = self.tick_size
        if ultimo_retorno > 0:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if ultimo_retorno < 0:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
