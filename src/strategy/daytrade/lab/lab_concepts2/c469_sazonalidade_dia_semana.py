"""Item 70 do catalogo: mesma familia do item 69 (`c468`), testando o DIA DA
SEMANA em vez do minuto do pregao.

ATENCAO -- adjacente a `wdo_win_filtro_dia_horario_refutado_2026_09_04.md`
(ja refutado como FILTRO na memoria do projeto). Implementado mesmo assim,
por pedido explicito do catalogo; docstring honesta sobre a sobreposicao.

Entra na direcao do vies daquele dia da semana (limiar empirico), uma vez
por pregao, ao abrir; sai ao fim do pregao (o achatamento forcado do motor
cuida disso -- este robo nao fecha antes por si so').
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class SazonalidadeDiaSemana(IntradayStrategy):
    """Vies de retorno diario por dia-da-semana, precomputado do historico."""

    name: str = "c469_sazonalidade_dia_semana"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    estatistica_minima: float = 1.5
    minimo_amostras: int = 15
    stop_ticks: int = 16
    alvo_ticks: int = 12
    entrada_ttl_bars: int = 60
    quantity: int = 1

    _vies_por_dia_semana: dict = field(default_factory=dict, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)
    _dia_semana_hoje: int = field(default=-1, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        diario = bars["close"].resample("1D").last().dropna()
        abertura = bars["close"].resample("1D").first().dropna()
        retorno_diario = (diario / abertura - 1.0).dropna()
        dia_semana = retorno_diario.index.dayofweek
        df = pd.DataFrame({"retorno": retorno_diario.values, "dow": dia_semana})
        vies: dict[int, tuple[float, float]] = {}
        for chave, grupo in df.groupby("dow"):
            n = len(grupo)
            if n < self.minimo_amostras:
                continue
            media = float(grupo["retorno"].mean())
            desvio = float(grupo["retorno"].std())
            if desvio <= 0:
                continue
            estatistica = media / (desvio / np.sqrt(n))
            vies[int(chave)] = (media, estatistica)
        self._vies_por_dia_semana = vies

    def on_session_start(self, session_date) -> None:
        self._armou_hoje = False
        self._dia_semana_hoje = pd.Timestamp(session_date).dayofweek

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if positions or self._armou_hoje:
            return []
        entrada = self._vies_por_dia_semana.get(self._dia_semana_hoje)
        if entrada is None:
            return []
        media, estatistica = entrada
        if abs(estatistica) < self.estatistica_minima:
            return []
        self._armou_hoje = True
        if media > 0:
            return [self._ordem("long", bar.close, f"vies_dia_semana_{self._dia_semana_hoje}")]
        return [self._ordem("short", bar.close, f"vies_dia_semana_{self._dia_semana_hoje}")]

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
