"""Catálogo astronomia/tempo, item 74: RelogioDeOuroIntradiario.

Divide o total de minutos do pregão por φ (1,618...) para marcar um
"momento áureo" diário; só aceita o PRIMEIRO sinal de entrada do dia que
ocorrer dentro de `janela_minutos` desse momento -- ignora todos os
outros, mesmo que válidos.
"""
from __future__ import annotations

import datetime as dt
from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

PHI = 1.6180339887


@dataclass
class RelogioDeOuroIntradiario(IntradayStrategy):
    """Sinal = cruzamento de momentum de `janela` barras; só é aceito se
    ocorrer dentro de `janela_minutos_aceite` do "momento áureo"
    (abertura + duração da sessão / φ), e só o PRIMEIRO do dia."""

    name: str = "relogio_de_ouro_intradiario"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    inicio_sessao: dt.time = dt.time(9, 0)
    fim_sessao: dt.time = dt.time(18, 0)
    janela_minutos_aceite: float = 10.0
    janela_momentum: int = 10
    limiar_momentum: float = 0.003
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _momento_aureo: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _ja_operou_hoje: bool = field(default=False, init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=11), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        data = pd.Timestamp(session_date).normalize()
        abertura = data + pd.Timedelta(hours=self.inicio_sessao.hour, minutes=self.inicio_sessao.minute)
        fechamento = data + pd.Timedelta(hours=self.fim_sessao.hour, minutes=self.fim_sessao.minute)
        duracao_min = (fechamento - abertura).total_seconds() / 60.0
        self._momento_aureo = abertura + pd.Timedelta(minutes=duracao_min / PHI)
        self._ja_operou_hoje = False
        self._closes = deque(maxlen=self.janela_momentum + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        dentro_da_janela = (self._momento_aureo is not None
                             and abs((bar.ts - self._momento_aureo).total_seconds()) / 60.0
                             <= self.janela_minutos_aceite)

        if (not positions and not self._ja_operou_hoje and dentro_da_janela
                and len(self._closes) == self._closes.maxlen):
            momentum = (bar.close - self._closes[0]) / self._closes[0]
            if abs(momentum) > self.limiar_momentum:
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
                self._ja_operou_hoje = True

        self._closes.append(bar.close)
        return acao
