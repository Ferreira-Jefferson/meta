"""Item 80 do catalogo: VWAP acumulado da PROPRIA sessao (close x volume,
acumulado em `on_bar`), com o spread preco-VWAP testado via limiar EMPIRICO
(nao teste de cointegracao formal).

Entra quando o spread esta fora da faixa (aposta em reversao ao VWAP); sai
no retorno do spread a' zero.
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
class CointegracaoPrecoVwapSessao(IntradayStrategy):
    """Spread preco-VWAP da propria sessao -- reversao por limiar empirico."""

    name: str = "c479_cointegracao_preco_vwap_sessao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_desvio: int = 60
    minimo_amostras: int = 20
    z_entrada: float = 2.0
    z_saida: float = 0.3
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _cum_pv: float = field(default=0.0, init=False, repr=False)
    _cum_v: float = field(default=0.0, init=False, repr=False)
    _spreads: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._cum_pv = 0.0
        self._cum_v = 0.0
        self._spreads = deque(maxlen=self.janela_desvio)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        volume_efetivo = bar.volume if bar.volume > 0 else 1.0
        self._cum_pv += bar.close * volume_efetivo
        self._cum_v += volume_efetivo
        vwap = self._cum_pv / self._cum_v if self._cum_v > 0 else bar.close
        spread = bar.close - vwap
        self._spreads.append(spread)

        if len(self._spreads) < self.minimo_amostras:
            return []
        arr = np.asarray(self._spreads, dtype=float)
        desvio = float(arr.std())
        z = spread / desvio if desvio > 0 else 0.0

        if positions:
            if abs(z) <= self.z_saida:
                return [Exit(reason="spread_voltou_ao_vwap")]
            return []

        if z >= self.z_entrada:
            return [self._ordem("short", bar.close, f"preco_acima_vwap_z{z:.2f}")]
        if z <= -self.z_entrada:
            return [self._ordem("long", bar.close, f"preco_abaixo_vwap_z{z:.2f}")]
        return []

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
