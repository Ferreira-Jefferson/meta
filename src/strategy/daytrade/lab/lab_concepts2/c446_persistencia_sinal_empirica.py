"""Item 47 do catalogo: P(barra seguinte na mesma direcao | k barras
seguidas na mesma direcao), estimada por CONTAGEM historica simples (sem
cadeia de Markov formal), construida ONLINE bar a bar (sem look-ahead: a
tabela so' e' atualizada depois que o resultado da barra e' conhecido).

Entra na direcao da sequencia quando essa probabilidade condicional supera
50% + margem; sai ao primeiro fechamento contrario.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class PersistenciaSinalEmpirica(IntradayStrategy):
    """P(continua|k barras seguidas), tabela empirica construida online."""

    name: str = "c446_persistencia_sinal_empirica"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    k_maximo: int = 10
    minimo_amostras: int = 20
    margem: float = 0.05
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _continua: dict = field(default_factory=lambda: defaultdict(int), init=False, repr=False)
    _total: dict = field(default_factory=lambda: defaultdict(int), init=False, repr=False)
    _run_lado: int = field(default=0, init=False, repr=False)
    _run_len: int = field(default=0, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        # a tabela empirica persiste entre sessoes (aprendizado acumulado);
        # so' o estado de RUN corrente do dia zera.
        self._run_lado = 0
        self._run_len = 0
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._close_anterior is None:
            self._close_anterior = bar.close
            return []
        lado_hoje = 1 if bar.close > self._close_anterior else (-1 if bar.close < self._close_anterior else 0)
        self._close_anterior = bar.close

        k_anterior = min(self._run_len, self.k_maximo)
        if lado_hoje != 0 and self._run_lado != 0:
            if lado_hoje == self._run_lado and k_anterior >= 1:
                self._continua[k_anterior] += 1
                self._total[k_anterior] += 1
            elif k_anterior >= 1:
                self._total[k_anterior] += 1

        if lado_hoje == 0:
            pass
        elif lado_hoje == self._run_lado:
            self._run_len += 1
        else:
            self._run_lado = lado_hoje
            self._run_len = 1

        if positions:
            pos = positions[0]
            if pos.side == "long" and lado_hoje < 0:
                return [Exit(reason="fechamento_contrario")]
            if pos.side == "short" and lado_hoje > 0:
                return [Exit(reason="fechamento_contrario")]
            return []

        k = min(self._run_len, self.k_maximo)
        if k < 2 or self._run_lado == 0:
            return []
        total = self._total.get(k, 0)
        if total < self.minimo_amostras:
            return []
        prob = self._continua[k] / total
        if prob >= 0.5 + self.margem:
            side = "long" if self._run_lado > 0 else "short"
            return [self._ordem(side, bar.close, f"persistencia_k{k}_p{prob:.2f}")]
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
