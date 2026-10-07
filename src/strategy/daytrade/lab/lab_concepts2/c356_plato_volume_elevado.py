"""Catálogo volume/microestrutura, item 57: PlatoDeVolumeElevado.

Volume sobe e se estabiliza (baixa variação relativa) num patamar acima da
referência de longo prazo -- mantém posição na tendência com stop móvel
enquanto o platô durar, sai quando o platô se rompe para baixo (volume
volta a cair abaixo do patamar).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    AdjustStop, Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class PlatoDeVolumeElevado(IntradayStrategy):
    """Volume elevado e estável (platô) na direção da tendência -- entra
    ao formar o platô, trela o stop enquanto durar, sai quando cai."""

    name: str = "plato_volume_elevado"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_plato: int = 8
    janela_base: int = 40
    k_plato: float = 1.3
    variacao_relativa_max: float = 0.35
    trail_ticks: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=8), init=False, repr=False)
    _vols_base: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _em_plato: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_plato)
        self._vols_base = deque(maxlen=self.janela_base)
        self._closes = deque(maxlen=self.janela_base)
        self._em_plato = False

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
        plato_agora = False
        if (len(self._vols) == self._vols.maxlen
                and len(self._vols_base) == self._vols_base.maxlen):
            serie_plato = pd.Series(self._vols)
            media_plato = float(serie_plato.mean())
            media_base = float(pd.Series(self._vols_base).mean())
            variacao_relativa = (
                float(serie_plato.std()) / media_plato if media_plato > 0 else 1e9
            )
            plato_agora = (
                media_base > 0 and media_plato > self.k_plato * media_base
                and variacao_relativa < self.variacao_relativa_max
            )

        if positions:
            if self._em_plato and not plato_agora:
                acao = [Exit(reason=self.name)]
            elif self._em_plato and positions[0].current_stop is not None:
                pos = positions[0]
                if pos.side == "long":
                    novo_stop = no_tick(bar.close - self.trail_ticks * self.tick_size, self.tick_size)
                    if novo_stop > pos.current_stop:
                        acao = [AdjustStop(new_stop=novo_stop)]
                else:
                    novo_stop = no_tick(bar.close + self.trail_ticks * self.tick_size, self.tick_size)
                    if novo_stop < pos.current_stop:
                        acao = [AdjustStop(new_stop=novo_stop)]
        elif plato_agora and not self._em_plato and len(self._closes) == self._closes.maxlen:
            tendencia_alta = bar.close > self._closes[0]
            acao = self._ordem("long" if tendencia_alta else "short", bar.close)

        self._em_plato = plato_agora
        self._vols.append(bar.volume)
        self._vols_base.append(bar.volume)
        self._closes.append(bar.close)
        return acao
