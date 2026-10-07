"""Item 65 do catalogo: APROXIMACAO simplificada de GARCH(1,1) -- NAO e'
MLE real. Atualizacao recursiva `var_t = a + b*ret_{t-1}^2 + c*var_{t-1}`
com a/b/c FIXOS (valores tipicos documentados abaixo, sem grid search).

Entra em reversao quando o retorno atual excede um multiplo da vol
condicional PREVISTA (excesso de movimento vs. o esperado); sai quando o
excesso desaparece.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class Garch11AproximadoVol(IntradayStrategy):
    """Variancia condicional por atualizacao recursiva tipo GARCH(1,1)."""

    name: str = "c464_garch11_aproximado_vol"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    #: parametros FIXOS, documentados -- nao e' MLE. `a` pequeno (piso de
    #: variancia), `b=0,1` (reacao ao choque recente), `c=0,85` (persistencia).
    a: float = 1e-8
    b: float = 0.10
    c: float = 0.85
    multiplo_excesso: float = 2.5
    minimo_amostras: int = 20
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _var: float = field(default=0.0, init=False, repr=False)
    _ret_anterior: float = field(default=0.0, init=False, repr=False)
    _n_bars: int = field(default=0, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._var = 0.0
        self._ret_anterior = 0.0
        self._n_bars = 0
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        ret = None
        if self._close_anterior is not None and self._close_anterior != 0:
            ret = (bar.close - self._close_anterior) / self._close_anterior
        self._close_anterior = bar.close

        self._var = self.a + self.b * (self._ret_anterior ** 2) + self.c * self._var
        self._n_bars += 1
        if ret is not None:
            self._ret_anterior = ret

        if self._n_bars < self.minimo_amostras or self._var <= 0 or ret is None:
            return []
        vol_prevista = float(np.sqrt(self._var))
        excesso = abs(ret) - self.multiplo_excesso * vol_prevista

        if positions:
            if excesso < 0:
                return [Exit(reason="excesso_de_vol_dissipou")]
            return []

        if excesso < 0:
            return []
        if ret > 0:
            return [self._ordem("short", bar.close, "excesso_vol_garch_alta")]
        return [self._ordem("long", bar.close, "excesso_vol_garch_baixa")]

    def _ordem(self, side: str, preco_ref: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(preco_ref, self.tick_size)
        stop = no_tick(limite - sinal * self.stop_ticks * self.tick_size, self.tick_size)
        alvo = no_tick(limite + sinal * self.alvo_ticks * self.tick_size, self.tick_size)
        return EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=reason,
        )
