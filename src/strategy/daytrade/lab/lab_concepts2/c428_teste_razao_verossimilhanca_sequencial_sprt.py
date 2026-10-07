"""TesteRazaoVerossimilhancaSequencial (SPRT) -- SPRT simplificado sobre a media.

Acumula log-verossimilhanca de duas hipoteses gaussianas simples (media
`+mu0` vs media `-mu0`, variancia comum estimada por janela movel) barra
a barra: incremento `= (2*mu0/sigma^2) * r_t` (a forma fechada do LLR
para gaussianas com medias simetricas). Cruza a fronteira de decisao
(`+-fronteira`, fixa, ex. 2,0) -> entra na direcao da hipotese vencedora
e reseta a soma. Sai quando a soma cruza a fronteira OPOSTA (reversao
forte da evidencia) enquanto a posicao ainda esta aberta, ou pelo
stop/alvo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class TesteRazaoVerossimilhancaSequencialSPRT(IntradayStrategy):
    """SPRT simplificado: acumula LLR de media positiva vs negativa e decide."""

    name: str = "c428_teste_razao_verossimilhanca_sequencial_sprt"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_std: int = 40
    mu0: float = 0.0005
    fronteira: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _llr: float = field(default=0.0, init=False, repr=False)
    _lado_posicao: str | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela_std)
        self._llr = 0.0
        self._lado_posicao = None

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
        self._closes.append(bar.close)
        cruzou_pos = cruzou_neg = False
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)
            if len(self._retornos) == self.janela_std:
                sigma2 = float(np.var(self._retornos, ddof=0))
                if sigma2 > 1e-14:
                    self._llr += (2.0 * self.mu0 / sigma2) * r
                    if self._llr >= self.fronteira:
                        cruzou_pos = True
                        self._llr = 0.0
                    elif self._llr <= -self.fronteira:
                        cruzou_neg = True
                        self._llr = 0.0

        if positions:
            if self._lado_posicao == "long" and cruzou_neg:
                self._lado_posicao = None
                return [Exit(reason=f"{self.name}_evidencia_reverteu")]
            if self._lado_posicao == "short" and cruzou_pos:
                self._lado_posicao = None
                return [Exit(reason=f"{self.name}_evidencia_reverteu")]
            return []

        tick = self.tick_size
        if cruzou_pos:
            self._lado_posicao = "long"
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if cruzou_neg:
            self._lado_posicao = "short"
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
