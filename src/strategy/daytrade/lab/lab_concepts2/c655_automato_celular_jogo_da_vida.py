"""Catálogo autômatos/ML/jogos, item 56: AutomatoCelularJogoDaVida.

Quantiza os últimos 3 candles em estados (grande-alta / pequena /
grande-baixa) e aplica uma regra de nascimento/morte tipo Jogo da Vida
simplificada: vizinhança "viva" e concorde continua a tendência,
vizinhança viva porém discordante ("morta" no sentido de padrão quebrado)
sinaliza reversão.
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
class AutomatoCelularJogoDaVida(IntradayStrategy):
    """3 últimas velas viram células vivas (corpo grande, direcional) ou
    mortas (corpo pequeno). Todas vivas e concordes = tendência continua;
    vivas mas discordantes = reversão da última vela."""

    name: str = "automato_celular_jogo_da_vida"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_corpo: int = 20
    fator_corpo_grande: float = 1.1
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _corpos: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _celulas: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._corpos.maxlen != self.janela_corpo:
            self._corpos = deque(self._corpos, maxlen=self.janela_corpo)
        self._celulas = deque(maxlen=3)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        corpo = bar.close - bar.open
        corpo_abs = abs(corpo)

        if not positions and len(self._celulas) == self._celulas.maxlen:
            estados = list(self._celulas)
            vivas = [e for e in estados if e != 0]
            side = None
            if len(vivas) == len(estados) and len(vivas) >= 2 and all(v == vivas[0] for v in vivas):
                side = "long" if vivas[0] > 0 else "short"
            elif len(vivas) >= 2 and len(set(vivas)) > 1:
                side = "short" if estados[-1] > 0 else "long"

            if side is not None:
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

        # Classifica a barra ATUAL usando a mediana das barras ANTERIORES
        # (nunca inclui o próprio corpo desta barra -- sem look-ahead).
        estado_atual = 0
        if len(self._corpos) == self._corpos.maxlen:
            mediana_corpo = sorted(self._corpos)[len(self._corpos) // 2]
            if corpo_abs > mediana_corpo * self.fator_corpo_grande:
                estado_atual = 1 if corpo > 0 else -1
        self._celulas.append(estado_atual)
        self._corpos.append(corpo_abs)
        return acao
