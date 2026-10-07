"""Catálogo catástrofe/criticalidade, item 81: TeoriaDaCatastrofeCuspide.

Modela o preço como uma superfície de catástrofe cúspide com duas
variáveis de controle -- momentum e compressão de volatilidade; a
trajetória (produto das duas) cruzando uma "linha de dobra" (limiar
empírico, calibrado pelo próprio histórico rolante) prevê um salto
súbito na direção do momentum.
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
class TeoriaDaCatastrofeCuspide(IntradayStrategy):
    """`momentum` = retorno de `janela_momentum` barras; `compressao` =
    inverso do desvio-padrão rolante de retornos (alto quando o mercado
    está "espremido"); `trajetoria = momentum * compressao` cruzando a
    "linha de dobra" (percentil histórico do módulo dela mesma) dispara
    entrada na direção do momentum."""

    name: str = "teoria_da_catastrofe_cuspide"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_momentum: int = 10
    janela_volatilidade: int = 20
    janela_linha_dobra: int = 40
    percentil_linha_dobra: float = 0.85
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=11), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _trajetorias_hist: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_momentum + 1)
        if self._retornos.maxlen != self.janela_volatilidade:
            self._retornos = deque(maxlen=self.janela_volatilidade)
        if self._trajetorias_hist.maxlen != self.janela_linha_dobra:
            self._trajetorias_hist = deque(maxlen=self.janela_linha_dobra)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes.append(bar.close)
        if self._close_anterior is not None:
            self._retornos.append((bar.close - self._close_anterior) / self._close_anterior)
        self._close_anterior = bar.close

        if (len(self._closes) == self._closes.maxlen
                and len(self._retornos) == self._retornos.maxlen):
            momentum = (bar.close - self._closes[0]) / self._closes[0]
            media_ret = sum(self._retornos) / len(self._retornos)
            dp_ret = (sum((r - media_ret) ** 2 for r in self._retornos) / len(self._retornos)) ** 0.5
            compressao = 1.0 / dp_ret if dp_ret > 0 else 0.0
            trajetoria = momentum * compressao

            if not positions and len(self._trajetorias_hist) == self._trajetorias_hist.maxlen:
                modulos = sorted(abs(t) for t in self._trajetorias_hist)
                idx = min(len(modulos) - 1, int(self.percentil_linha_dobra * len(modulos)))
                linha_dobra = modulos[idx]
                if linha_dobra > 0 and abs(trajetoria) > linha_dobra and momentum != 0:
                    side = "long" if momentum > 0 else "short"
                    if side == "long":
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    else:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side=side, limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

            self._trajetorias_hist.append(trajetoria)
        return acao
