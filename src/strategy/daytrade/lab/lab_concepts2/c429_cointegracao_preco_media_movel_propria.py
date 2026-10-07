"""CointegracaoPrecoMediaMovelPropria -- reversao sobre o residuo preco x MA propria.

Regressao simples (`numpy.polyfit`) do preco contra sua PROPRIA media
movel de longo prazo, numa janela rolante -- testa a "estacionariedade"
do residuo por um LIMIAR EMPIRICO (z-score do residuo contra seu proprio
desvio-padrao na janela) em vez de um teste ADF formal. Entra CONTRA o
residuo quando ele esta fora da faixa (preco esticado em relacao a
propria tendencia de media); sai no retorno do residuo a zero, ou pelo
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
class CointegracaoPrecoMediaMovelPropria(IntradayStrategy):
    """Reversao sobre o residuo da regressao preco x propria media movel."""

    name: str = "c429_cointegracao_preco_media_movel_propria"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_regressao: int = 80
    janela_media_movel: int = 20
    limiar_z: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=100), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_regressao + self.janela_media_movel)

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

    def _z_residuo(self) -> float | None:
        if len(self._closes) < self.janela_regressao + self.janela_media_movel:
            return None
        s = pd.Series(self._closes)
        ma = s.rolling(self.janela_media_movel).mean()
        validos = ma.dropna()
        if len(validos) < self.janela_regressao:
            return None
        x = validos.values[-self.janela_regressao:]
        y = s.loc[validos.index].values[-self.janela_regressao:]
        try:
            slope, intercepto = np.polyfit(x, y, 1)
        except Exception:
            return None
        residuos = y - (slope * x + intercepto)
        std = residuos.std(ddof=0)
        if std <= 1e-9:
            return None
        return float(residuos[-1] / std)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        z = self._z_residuo()

        if positions:
            if z is not None:
                pos = positions[0]
                if pos.side == "short" and z <= 0.0:
                    return [Exit(reason=f"{self.name}_zero_cross")]
                if pos.side == "long" and z >= 0.0:
                    return [Exit(reason=f"{self.name}_zero_cross")]
            return []

        if z is None:
            return []
        tick = self.tick_size
        if z >= self.limiar_z:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if z <= -self.limiar_z:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
