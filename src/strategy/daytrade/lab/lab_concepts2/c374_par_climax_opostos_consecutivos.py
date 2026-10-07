"""Catálogo volume/microestrutura, item 75: ParDeClimaxOpostosConsecutivos.

Barra de volume muito alto numa direção seguida imediatamente por outra de
volume muito alto na direção OPOSTA, que reverte o fechamento da primeira
para além do open dela -- entra na direção da segunda barra.
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
class ParDeClimaxOpostosConsecutivos(IntradayStrategy):
    """Duas barras de climax consecutivas em direções opostas, a segunda
    revertendo a primeira -- entra na direção da segunda barra."""

    name: str = "par_climax_opostos_consecutivos"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 20
    k_volume: float = 1.8
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _anterior: dict | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_vol)
        self._anterior = None

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
        climax_atual = vol_ma is not None and bar.volume > self.k_volume * vol_ma
        direcao_atual = 1 if bar.close > bar.open else (-1 if bar.close < bar.open else 0)

        if (not positions and self._anterior is not None and self._anterior["climax"]
                and climax_atual and direcao_atual != 0 and self._anterior["direcao"] != 0
                and direcao_atual != self._anterior["direcao"]):
            reverteu = (
                bar.close < self._anterior["open"] if self._anterior["direcao"] > 0
                else bar.close > self._anterior["open"]
            )
            if reverteu:
                acao = self._ordem("long" if direcao_atual > 0 else "short", bar.close)

        self._anterior = {"climax": climax_atual, "direcao": direcao_atual, "open": bar.open}
        self._vols.append(bar.volume)
        return acao
