"""Item 75 do catalogo: compara a ACURACIA PREDITIVA (contagem simples, sem
teste de razao de verossimilhanca formal) de um modelo de Markov ORDEM 1
(estado = direcao da barra anterior) contra um modelo ORDEM 0 (so' a
frequencia marginal), construidos ONLINE.

So' liga o uso da cadeia de Markov como sinal quando a ordem 1 supera a
ordem 0 empiricamente na janela -- serve de FILTRO estrutural.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class MarkovOrdem1VsOrdem0(IntradayStrategy):
    """Acuracia preditiva Markov ordem-1 vs ordem-0, construida online."""

    name: str = "c474_markov_ordem1_vs_ordem0"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    minimo_amostras: int = 40
    margem_acuracia: float = 0.02
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _transicao: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)), init=False, repr=False)
    _marginal: dict = field(default_factory=lambda: defaultdict(int), init=False, repr=False)
    _acertos_ordem1: int = field(default=0, init=False, repr=False)
    _acertos_ordem0: int = field(default=0, init=False, repr=False)
    _total: int = field(default=0, init=False, repr=False)
    _estado_anterior: int = field(default=0, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        # a tabela empirica persiste entre sessoes; so' o close/estado do
        # dia (referencia pra' calcular o proximo retorno) zera.
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

        if lado_hoje != 0 and self._estado_anterior != 0:
            # avalia a predicao que CADA modelo teria feito antes de saber o resultado
            pred_ordem1 = self._predicao_ordem1(self._estado_anterior)
            pred_ordem0 = self._predicao_ordem0()
            if pred_ordem1 is not None:
                self._total += 1
                if pred_ordem1 == lado_hoje:
                    self._acertos_ordem1 += 1
                if pred_ordem0 is not None and pred_ordem0 == lado_hoje:
                    self._acertos_ordem0 += 1
            self._transicao[self._estado_anterior][lado_hoje] += 1
            self._marginal[lado_hoje] += 1

        if lado_hoje != 0:
            self._estado_anterior = lado_hoje

        if positions:
            pos = positions[0]
            if pos.side == "long" and lado_hoje < 0:
                return [Exit(reason="fechamento_contrario")]
            if pos.side == "short" and lado_hoje > 0:
                return [Exit(reason="fechamento_contrario")]
            return []

        if self._total < self.minimo_amostras:
            return []
        acc1 = self._acertos_ordem1 / self._total
        acc0 = self._acertos_ordem0 / self._total if self._total else 0.0
        if acc1 <= acc0 + self.margem_acuracia:
            return []
        predicao = self._predicao_ordem1(self._estado_anterior)
        if predicao is None:
            return []
        side = "long" if predicao > 0 else "short"
        return [self._ordem(side, bar.close, f"markov1_acc{acc1:.2f}_vs_ordem0_{acc0:.2f}")]

    def _predicao_ordem1(self, estado: int) -> int | None:
        contagens = self._transicao.get(estado)
        if not contagens:
            return None
        return max(contagens, key=contagens.get)

    def _predicao_ordem0(self) -> int | None:
        if not self._marginal:
            return None
        return max(self._marginal, key=self._marginal.get)

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
