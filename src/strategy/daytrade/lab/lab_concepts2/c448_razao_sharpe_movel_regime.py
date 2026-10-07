"""Item 49 do catalogo: Sharpe ratio movel (retorno medio/desvio-padrao,
janela curta) como filtro de qualidade de tendencia.

Entra seguindo a direcao SO' quando o Sharpe movel excede um limiar (evita
operar perto de zero); sai quando cai abaixo do limiar.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class RazaoSharpeMovelRegime(IntradayStrategy):
    """Sharpe ratio movel como filtro de qualidade de tendencia."""

    name: str = "c448_razao_sharpe_movel_regime"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    limiar: float = 0.3
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._retornos = deque(maxlen=self.janela)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._close_anterior is not None and self._close_anterior != 0:
            self._retornos.append((bar.close - self._close_anterior) / self._close_anterior)
        self._close_anterior = bar.close

        sharpe = self._sharpe()
        if positions:
            if sharpe is None:
                return []
            pos = positions[0]
            if pos.side == "long" and sharpe < self.limiar:
                return [Exit(reason="sharpe_perdeu_forca")]
            if pos.side == "short" and sharpe > -self.limiar:
                return [Exit(reason="sharpe_perdeu_forca")]
            return []

        if sharpe is None:
            return []
        if sharpe >= self.limiar:
            return [self._ordem("long", bar.close, "sharpe_movel_positivo")]
        if sharpe <= -self.limiar:
            return [self._ordem("short", bar.close, "sharpe_movel_negativo")]
        return []

    def _sharpe(self) -> float | None:
        if len(self._retornos) < self.janela:
            return None
        arr = np.asarray(self._retornos, dtype=float)
        desvio = float(arr.std())
        if desvio <= 0:
            return None
        return float(arr.mean() / desvio)

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
