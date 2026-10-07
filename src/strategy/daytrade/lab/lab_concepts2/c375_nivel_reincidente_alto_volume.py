"""Catálogo volume/microestrutura, item 76: NivelReincidenteDeAltoVolume.

Buckets de preço (arredondados por `no_tick` num grid mais largo) acumulam
volume de barras de volume elevado; um bucket com `min_toques` ou mais
toques vira nível defendido -- fade enquanto não for rompido com volume;
o rompimento com volume apaga o nível (para de defender).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class NivelReincidenteDeAltoVolume(IntradayStrategy):
    """Nível de preço reincidente em volume alto vira suporte/resistência
    defendida -- fade até ser rompida com volume, que apaga o nível."""

    name: str = "nivel_reincidente_alto_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 20
    k_volume: float = 1.5
    bucket_ticks: int = 5
    min_toques: int = 3
    tolerancia_teste_ticks: int = 2
    tolerancia_rompimento_ticks: int = 6
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _niveis: dict = field(default_factory=dict, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_vol)
        self._niveis = {}
        self._close_anterior = None

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
        vol_ma = sum(self._vols) / len(self._vols) if self._vols else None
        volume_alto = vol_ma is not None and bar.volume > self.k_volume * vol_ma
        bucket_size = self.bucket_ticks * self.tick_size
        tol_teste = self.tolerancia_teste_ticks * self.tick_size
        tol_rompe = self.tolerancia_rompimento_ticks * self.tick_size

        if not positions and self._close_anterior is not None:
            for nivel in list(self._niveis):
                info = self._niveis[nivel]
                if info["toques"] < self.min_toques:
                    continue
                perto = abs(bar.close - nivel) <= tol_teste
                if perto:
                    if self._close_anterior < nivel <= bar.close + tol_teste:
                        acao = self._ordem("short", nivel)
                        break
                    if self._close_anterior > nivel >= bar.close - tol_teste:
                        acao = self._ordem("long", nivel)
                        break
                elif volume_alto and abs(bar.close - nivel) > tol_rompe:
                    del self._niveis[nivel]

        if volume_alto:
            bucket = no_tick(bar.close, bucket_size)
            info = self._niveis.setdefault(bucket, {"toques": 0, "volume_total": 0.0})
            info["toques"] += 1
            info["volume_total"] += bar.volume

        self._vols.append(bar.volume)
        self._close_anterior = bar.close
        return acao
