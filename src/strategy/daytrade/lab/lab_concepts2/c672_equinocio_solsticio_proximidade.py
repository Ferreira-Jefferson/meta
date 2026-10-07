"""Catálogo astronomia/tempo, item 73: EquinocioSolsticioProximidade.

Distância em dias até o equinócio/solstício mais próximo (datas
aproximadas hardcoded) escala a LARGURA do stop/alvo -- mais larga perto
dos solstícios, mais apertada perto dos equinócios, respeitando o piso de
4 ticks no alvo. Gatilho de entrada é o rompimento do range de abertura.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

# (mes, dia) aproximados -- suficiente para um filtro determinístico, não
# para efemérides de precisão.
_DATAS_MARCO = [(3, 20), (6, 21), (9, 23), (12, 21)]
_EH_SOLSTICIO = [False, True, False, True]


def distancia_dias_e_eh_solsticio(data: pd.Timestamp) -> tuple[int, bool]:
    """Menor distância em dias até um equinócio/solstício (considerando
    também as marcas do ano anterior/seguinte, para cobrir a virada do
    ano), e se a mais próxima é solstício (True) ou equinócio (False)."""
    candidatas = []
    for ano in (data.year - 1, data.year, data.year + 1):
        for (mes, dia), eh_solsticio in zip(_DATAS_MARCO, _EH_SOLSTICIO):
            marca = pd.Timestamp(year=ano, month=mes, day=dia)
            candidatas.append((abs((data - marca).days), eh_solsticio))
    return min(candidatas, key=lambda par: par[0])


@dataclass
class EquinocioSolsticioProximidade(IntradayStrategy):
    """Rompimento do range de abertura; a distância até o
    equinócio/solstício mais próximo escala o stop/alvo entre os pisos
    (perto de equinócio) e os tetos (perto de solstício), respeitando o
    piso absoluto de 4 ticks no alvo."""

    name: str = "equinocio_solsticio_proximidade"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    barras_abertura: int = 15
    janela_meia_estacao_dias: float = 45.0
    offset_ticks: int = 1
    stop_ticks_min: int = 8
    stop_ticks_max: int = 20
    alvo_ticks_min: int = 4
    alvo_ticks_max: int = 12
    entrada_ttl_bars: int = 40

    _proximidade: float = field(default=0.0, init=False, repr=False)
    _range_high: float | None = field(default=None, init=False, repr=False)
    _range_low: float | None = field(default=None, init=False, repr=False)
    _n_barras: int = field(default=0, init=False, repr=False)
    _armado: bool = field(default=True, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        dist, eh_solsticio = distancia_dias_e_eh_solsticio(pd.Timestamp(session_date))
        proximidade = max(0.0, 1.0 - dist / self.janela_meia_estacao_dias)
        # positivo = perto de solsticio (larga); negativo = perto de equinocio (apertada)
        self._proximidade = proximidade if eh_solsticio else -proximidade
        self._range_high = None
        self._range_low = None
        self._n_barras = 0
        self._armado = True

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._n_barras += 1

        if self._n_barras <= self.barras_abertura:
            self._range_high = bar.high if self._range_high is None else max(self._range_high, bar.high)
            self._range_low = bar.low if self._range_low is None else min(self._range_low, bar.low)
            return acao

        if (not positions and self._armado
                and self._range_high is not None and self._range_low is not None):
            side = None
            if bar.close > self._range_high:
                side = "long"
            elif bar.close < self._range_low:
                side = "short"
            if side is not None:
                # fracao [0,1]: 1 = maximo de "largura" (perto de solsticio)
                fracao = (self._proximidade + 1.0) / 2.0
                stop_ticks = round(self.stop_ticks_min + fracao * (self.stop_ticks_max - self.stop_ticks_min))
                alvo_ticks = max(4, round(self.alvo_ticks_min + fracao * (self.alvo_ticks_max - self.alvo_ticks_min)))
                if side == "long":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=side, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
                self._armado = False
        return acao
