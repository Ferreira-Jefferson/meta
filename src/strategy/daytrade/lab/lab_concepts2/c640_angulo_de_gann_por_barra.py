"""Catálogo Gann/geometria sagrada, item 41: AnguloDeGannPorBarra.

APROXIMAÇÃO: mede a inclinação realizada (ticks de preço por barra) do
movimento das últimas N barras e compara ao ângulo canônico 1x1 (1
tick/barra, calibrável). Esticado demais (acima do canônico) -> fade;
abaixo do canônico (tendência fraca) -> evita; perto do canônico ->
segue a tendência.
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
class AnguloDeGannPorBarra(IntradayStrategy):
    """Compara a inclinação realizada (ticks/barra) das últimas N barras ao
    ângulo canônico 1x1: perto dele segue a tendência, muito acima faz
    fade (esticado), muito abaixo evita (tendência fraca)."""

    name: str = "angulo_de_gann_por_barra"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 10
    calibracao_ticks_por_barra: float = 1.0
    fator_esticado: float = 2.0
    fator_fraco: float = 0.4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=11), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._closes) == self._closes.maxlen:
            variacao_ticks = (self._closes[-1] - self._closes[0]) / self.tick_size
            inclinacao_ticks_por_barra = variacao_ticks / self.janela
            razao = abs(inclinacao_ticks_por_barra) / self.calibracao_ticks_por_barra

            if self.fator_fraco <= razao <= self.fator_esticado:
                lado = "long" if inclinacao_ticks_por_barra > 0 else "short"
                if lado == "long":
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=lado, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif razao > self.fator_esticado:
                lado_fade = "short" if inclinacao_ticks_por_barra > 0 else "long"
                if lado_fade == "short":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=lado_fade, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            # razao < fator_fraco: tendencia fraca demais, evita (sem acao)

        self._closes.append(bar.close)
        return acao
