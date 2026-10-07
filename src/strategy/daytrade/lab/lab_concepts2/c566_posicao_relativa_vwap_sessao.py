"""Catálogo regime/adaptação, item 67: PosicaoRelativaVWAPSessao.

VWAP da sessão (soma incremental de close×volume / soma de volume, sem
look-ahead, reiniciada em `on_session_start`). Acima do VWAP: só compra em
PULLBACK que toca o VWAP sem fechar abaixo dele. Abaixo do VWAP: só vende
em REPIQUE que toca o VWAP sem fechar acima dele.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class PosicaoRelativaVWAPSessao(IntradayStrategy):
    """VWAP incremental da sessão. Preço ACIMA do VWAP: compra em pullback
    que toca o VWAP e fecha acima. Preço ABAIXO do VWAP: vende em repique
    que toca o VWAP e fecha abaixo."""

    name: str = "posicao_relativa_vwap_sessao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _soma_pv: float = field(default=0.0, init=False, repr=False)
    _soma_v: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._soma_pv = 0.0
        self._soma_v = 0.0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and self._soma_v > 0:
            vwap = self._soma_pv / self._soma_v
            acima = bar.close > vwap
            abaixo = bar.close < vwap
            tocou = bar.low <= vwap <= bar.high

            if acima and tocou:
                limite = no_tick(vwap + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif abaixo and tocou:
                limite = no_tick(vwap - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._soma_pv += bar.close * bar.volume
        self._soma_v += bar.volume
        return acao
