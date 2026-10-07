"""Item 59 do catalogo: APROXIMACAO de regressao quantilica -- NAO e' uma
regressao quantilica formal. Ajusta uma reta por minimos quadrados
(`numpy.polyfit`) sobre a janela e desloca a banda pelos PERCENTIS dos
residuos (nao pelos quantis condicionais de verdade).

Entra na reversao quando o preco rompe a banda deslocada; sai no retorno a'
linha central (a reta ajustada).
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
class RegressaoQuantilicaBandas(IntradayStrategy):
    """Reta por MQ + banda pelos percentis dos residuos (aproximacao)."""

    name: str = "c458_regressao_quantilica_bandas"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    percentil_banda: float = 0.9
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _closes: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) < self.janela:
            return []
        y = np.asarray(self._closes, dtype=float)
        x = np.arange(len(y), dtype=float)
        inclinacao, intercepto = np.polyfit(x, y, 1)
        linha = inclinacao * x + intercepto
        residuos = np.abs(y - linha)
        deslocamento = float(np.quantile(residuos, self.percentil_banda))
        linha_atual = float(linha[-1])
        banda_alta = linha_atual + deslocamento
        banda_baixa = linha_atual - deslocamento

        if positions:
            pos = positions[0]
            if pos.side == "long" and bar.close >= linha_atual:
                return [Exit(reason="retornou_a_linha_central")]
            if pos.side == "short" and bar.close <= linha_atual:
                return [Exit(reason="retornou_a_linha_central")]
            return []

        if bar.close >= banda_alta:
            return [self._ordem("short", bar.close, "rompeu_banda_regressao_alta")]
        if bar.close <= banda_baixa:
            return [self._ordem("long", bar.close, "rompeu_banda_regressao_baixa")]
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
