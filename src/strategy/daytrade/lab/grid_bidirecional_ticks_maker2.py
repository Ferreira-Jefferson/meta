"""Grid bidirecional MAKER v2 (2026-08-21) — evolucao de
`grid_bidirecional_ticks_maker.py`: alem da ENTRADA via `EnterLimit`
(sem slippage), o ALVO de saida agora tambem e' `initial_target` no
proprio `EnterLimit`, deixado para o motor fechar automaticamente via
`IntradayBacktestConfig(target_fills_as_maker=True)` -- ou seja, o alvo
tambem e' uma ordem-limite (maker), nao mais um `Exit` a mercado.

Por que uma v2 e nao editar o arquivo v1: o v1 ja teve seus numeros
reportados (entrada maker + saida a mercado); esta v2 isola o efeito de
tambem tornar a SAIDA de lucro maker, para comparar as tres versoes
(mercado/mercado original, maker/mercado v1, maker/maker v2) sem
confundir qual mudanca produziu qual ganho.

O stop AGREGADO de sessao continua sendo um `Exit` a mercado -- essa
saida e' por PROTECAO (o dia foi mal), nao por realizacao de lucro
planejada, e continua precisando de garantia de execucao. So a saida de
lucro (que o proprio robo escolhe o nivel, sem pressa) fica maker.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
)


@dataclass
class _GridLevel:
    side: str  # "long" ou "short"
    price: float
    filled: bool = False


@dataclass
class _SessionState:
    open_price: float | None = None
    levels: list[_GridLevel] = field(default_factory=list)
    grid_built: bool = False
    session_halted: bool = False
    pending_level: "_GridLevel | None" = None


class GridBidirecionalTicksMaker2(IntradayStrategy):
    """Grid bidirecional MAKER v2: entrada E saida de lucro via
    ordem-limite (o motor precisa de `target_fills_as_maker=True` para o
    alvo de fato nao pagar slippage); stop agregado de sessao continua a
    mercado."""

    name = "grid_bidirecional_ticks_maker2"
    version = "0.1"
    # A saida por alvo deste robo e uma ordem-limite parada no nivel: e o
    # centro do desenho (capturar o spread em vez de paga-lo), nao um
    # detalhe de modelagem. Ver `IntradayStrategy.target_fills_as_maker`.
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "PMAM3",
        tick_size: float = 0.01,
        legs_per_side: int = 3,
        level_spacing_ticks: int = 2,
        band_ticks: int = 10,
        profit_ticks: int = 1,
        session_stop_brl: float = 30.0,
        quantity: int | None = None,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        self.legs_per_side = legs_per_side
        self.level_spacing_ticks = level_spacing_ticks
        self.band_ticks = band_ticks
        self.profit_ticks = profit_ticks
        self.session_stop_brl = abs(session_stop_brl)
        self.quantity = quantity

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def _build_grid(self, open_price: float) -> list[_GridLevel]:
        levels: list[_GridLevel] = []
        band = self.band_ticks * self.tick_size
        for i in range(1, self.legs_per_side + 1):
            offset = i * self.level_spacing_ticks * self.tick_size
            if offset > band:
                break
            long_price = round(open_price - offset, 2)
            short_price = round(open_price + offset, 2)
            levels.append(_GridLevel(side="long", price=long_price))
            levels.append(_GridLevel(side="short", price=short_price))
        return levels

    def _next_pending_level(self) -> _GridLevel | None:
        for level in self._state.levels:
            if not level.filled:
                return level
        return None

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        position: IntradayOpenPosition | None,
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []

        if state.open_price is None:
            state.open_price = bar.open
            state.levels = self._build_grid(bar.open)
            state.grid_built = True

        if not state.session_halted and session_pnl_brl <= -self.session_stop_brl:
            state.session_halted = True
            if position is not None:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if position is not None:
            # Confirma o nivel que preencheu (a EnterLimit rastreada). O
            # ALVO ja foi definido no `initial_target` da propria
            # `EnterLimit` -- o motor fecha automaticamente quando tocado,
            # nao precisamos gerenciar isso aqui.
            if state.pending_level is not None:
                state.pending_level.filled = True
                state.pending_level = None
            return []

        if state.pending_level is not None:
            return actions  # ja ha ordem pendente rastreando o proximo nivel

        next_level = self._next_pending_level()
        if next_level is None:
            return actions

        state.pending_level = next_level
        target = (
            next_level.price + self.profit_ticks * self.tick_size
            if next_level.side == "long"
            else next_level.price - self.profit_ticks * self.tick_size
        )
        return [EnterLimit(
            side=next_level.side,
            limit_price=next_level.price,
            initial_target=target,
            quantity=self.quantity,
            metadata={"grid_level_price": next_level.price},
            reason="grid_maker2_toque_" + next_level.side,
        )]
