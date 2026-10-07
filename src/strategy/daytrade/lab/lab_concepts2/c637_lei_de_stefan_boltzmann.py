"""Catálogo termodinâmica/informação, item 38: LeiDeStefanBoltzmann.

APROXIMAÇÃO: analogia energia_radiada ∝ volatilidade⁴ (lei de Stefan-
Boltzmann, T⁴). Compara a medida quártica rolling (desvio-padrão dos
retornos elevado à 4ª potência) contra a medida linear (desvio-padrão);
quando a razão dispara desproporcionalmente acima do normal histórico,
espera reversão rápida à média (fade do último movimento).
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
class LeiDeStefanBoltzmann(IntradayStrategy):
    """"Energia radiada" ∝ volatilidade⁴; quando a razão quártica/linear da
    janela dispara acima da média histórica dela, entra em reversão à
    média (fade do último movimento)."""

    name: str = "lei_de_stefan_boltzmann"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 15
    janela_historico_razao: int = 60
    fator_disparo: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=16), init=False, repr=False)
    _razoes: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_vol + 1)
        self._razoes = deque(maxlen=self.janela_historico_razao)

    @staticmethod
    def _desvio_padrao(valores: list[float]) -> float:
        n = len(valores)
        media = sum(valores) / n
        var = sum((v - media) ** 2 for v in valores) / n
        return var ** 0.5

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if len(self._closes) == self._closes.maxlen:
            retornos = [b - a for a, b in zip(self._closes, list(self._closes)[1:])]
            vol_linear = self._desvio_padrao(retornos)
            energia_radiada = vol_linear ** 4
            razao = energia_radiada / vol_linear if vol_linear > 0 else 0.0
            self._razoes.append(razao)

            if not positions and len(self._razoes) >= 10:
                media_razao = sum(self._razoes) / len(self._razoes)
                if media_razao > 0 and razao > self.fator_disparo * media_razao:
                    ultimo_retorno = retornos[-1] if retornos else 0.0
                    lado = "short" if ultimo_retorno > 0 else "long"
                    if lado == "short":
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    else:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side=lado, limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._closes.append(bar.close)
        return acao
