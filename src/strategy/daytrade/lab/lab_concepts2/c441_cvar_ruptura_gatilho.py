"""Item 42 do catalogo: CVaR (Expected Shortfall) empirico movel como gatilho.

CVaR = media dos piores `quantil` dos retornos numa janela movel; VaR e' so'
o percentil simples da mesma janela. Entra em reversao quando o retorno da
barra rompe o nivel de CVaR (do lado alto ou baixo); sai quando o retorno
volta a cruzar o VaR (menos extremo) do mesmo lado.
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
class CVaRRupturaGatilho(IntradayStrategy):
    """CVaR/VaR empiricos moveis dos retornos como gatilho de reversao."""

    name: str = "c441_cvar_ruptura_gatilho"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    quantil: float = 0.1
    minimo_amostras: int = 20
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._retornos = deque(maxlen=self.janela)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        ret = None
        if self._close_anterior is not None and self._close_anterior != 0:
            ret = (bar.close - self._close_anterior) / self._close_anterior
        self._close_anterior = bar.close
        if ret is not None:
            self._retornos.append(ret)

        if len(self._retornos) < self.minimo_amostras:
            return []
        _, var_low, _, var_high = self._niveis()

        if positions:
            if ret is None:
                return []
            pos = positions[0]
            if pos.side == "long" and ret >= var_low:
                return [Exit(reason="retorno_acima_do_var")]
            if pos.side == "short" and ret <= var_high:
                return [Exit(reason="retorno_abaixo_do_var")]
            return []

        if ret is None:
            return []
        cvar_low, _, cvar_high, _ = self._niveis()
        if ret <= cvar_low:
            return [self._ordem("long", bar.close, "cvar_ruptura_baixa")]
        if ret >= cvar_high:
            return [self._ordem("short", bar.close, "cvar_ruptura_alta")]
        return []

    def _niveis(self) -> tuple[float, float, float, float]:
        arr = np.sort(np.asarray(self._retornos, dtype=float))
        n = len(arr)
        k = max(1, int(n * self.quantil))
        cvar_low = float(arr[:k].mean())
        var_low = float(arr[k - 1])
        cvar_high = float(arr[-k:].mean())
        var_high = float(arr[-k])
        return cvar_low, var_low, cvar_high, var_high

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
