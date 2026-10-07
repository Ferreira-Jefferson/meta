"""Item 69 do catalogo: retorno medio por MINUTO-DO-PREGAO, precomputado em
`initialize` sobre o historico inteiro (agrupado por `HH:MM` do timestamp),
usando o DESVIO padronizado (media/erro-padrao) em vez de p-valor formal
como criterio de significancia.

Entra na janela de horario com vies historico, na direcao historica; sai
apos um numero fixo de barras (a janela do minuto).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class SazonalidadeIntrapregaoMinuto(IntradayStrategy):
    """Vies de retorno por minuto-do-pregao, precomputado do historico."""

    name: str = "c468_sazonalidade_intrapregao_minuto"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    estatistica_minima: float = 1.5
    minimo_amostras: int = 30
    barras_saida: int = 5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _vies_por_minuto: dict = field(default_factory=dict, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        retorno = bars["close"].pct_change()
        minuto = bars.index.strftime("%H:%M")
        df = pd.DataFrame({"retorno": retorno.values, "minuto": minuto}).dropna()
        vies: dict[str, tuple[float, float]] = {}
        for chave, grupo in df.groupby("minuto"):
            n = len(grupo)
            if n < self.minimo_amostras:
                continue
            media = float(grupo["retorno"].mean())
            desvio = float(grupo["retorno"].std())
            if desvio <= 0:
                continue
            estatistica = media / (desvio / np.sqrt(n))
            vies[chave] = (media, estatistica)
        self._vies_por_minuto = vies

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if positions:
            pos = positions[0]
            if pos.bars_held >= self.barras_saida:
                return [Exit(reason="fim_da_janela_de_horario")]
            return []

        chave = ts.strftime("%H:%M")
        entrada = self._vies_por_minuto.get(chave)
        if entrada is None:
            return []
        media, estatistica = entrada
        if abs(estatistica) < self.estatistica_minima:
            return []
        if media > 0:
            return [self._ordem("long", bar.close, f"vies_horario_{chave}")]
        return [self._ordem("short", bar.close, f"vies_horario_{chave}")]

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
