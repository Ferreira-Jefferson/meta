"""Catálogo volume/microestrutura, item 63: VolumeAcumuladoAcimaDoRitmoSazonal.

Compara o volume acumulado da sessão até a barra `check_idx` (contada
desde a abertura -- em base tick isso NÃO é tempo fixo, calibrar) com a
média histórica (Welford incremental, só sessões ANTERIORES, pura e sem
I/O) do volume acumulado naquele mesmo ponto. Rodando acima do ritmo,
opera a favor da tendência do dia (close vs. abertura da sessão).
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
class VolumeAcumuladoAcimaDoRitmoSazonal(IntradayStrategy):
    """Volume acumulado da sessão, no minuto de checagem, acima da média
    histórica naquele mesmo ponto -- opera a favor da tendência do dia."""

    name: str = "volume_acumulado_acima_ritmo_sazonal"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    check_idx: int = 30
    fator_acima: float = 1.2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _idx: int = field(default=0, init=False, repr=False)
    _cum_vol: float = field(default=0.0, init=False, repr=False)
    _open_sessao: float | None = field(default=None, init=False, repr=False)
    _n_dias: int = field(default=0, init=False, repr=False)
    _media_check: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._idx = 0
        self._cum_vol = 0.0
        self._open_sessao = None

    def _ordem(self, lado: str, nivel: float) -> list[IntradayAction]:
        if lado == "long":
            limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
        else:
            limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
        return [EnterLimit(
            side=lado, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        idx = self._idx
        self._idx += 1
        if idx == 0:
            self._open_sessao = bar.open
        self._cum_vol += bar.volume

        if idx == self.check_idx:
            media_hist = self._media_check if self._n_dias > 0 else None
            if not positions and media_hist is not None and self._open_sessao is not None:
                if self._cum_vol > self.fator_acima * media_hist:
                    tendencia_alta = bar.close > self._open_sessao
                    acao = self._ordem("long" if tendencia_alta else "short", bar.close)
            self._n_dias += 1
            self._media_check += (self._cum_vol - self._media_check) / self._n_dias

        return acao
