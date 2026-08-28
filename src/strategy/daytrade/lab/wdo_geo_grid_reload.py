"""Grid RELOAD maker para FUTURO (2026-08-26, Frente F4-wdo-geometria-sessao)
-- generalizacao de `grid_reload_maker.GridReloadMaker` (que e' de ACAO, tick
de centavos, level_price arredondado em 2 casas) para o tick de PONTOS do
WDO@/WIN@, mais um eixo novo: `n_levels`, o numero de DISTANCIAS que cada
lado roda em RODIZIO.

Por que uma classe nova e nao reusar `GridReloadMaker` direto: (1) o
arredondamento `round(preco, 2)` do v1 e' arbitrario para futuro -- WDO
negocia em passos de 0,5 ponto, nao centavos, e a instancia de acao nunca
precisou levar o `tick_size` a serio nesse ponto porque toda acao tem 2 casas
mesmo; (2) o v1 so' conhece 1 distancia por lado (`level_spacing_ticks` fixo).
Este arquivo generaliza para `n_levels` distancias, para poder medir se um
grid mais "fundo" (mais niveis por lado) ajuda ou so' produz mais trades no
mesmo edge -- pergunta 3 da missao desta frente.

LIMITE ESTRUTURAL HONESTO: `IntradaySessionMachine` (src/backtest/intraday/
machine.py) guarda UMA UNICA ordem-limite pendente por vez
(`self.resting_limit`, singular, nao lista) -- verificado lendo o motor antes
de escrever isto. Isso significa que este robo, como o v1, NUNCA tem duas
ordens penduradas ao mesmo tempo; o que `n_levels` testa e' RODIZIO de
distancia (a proxima recarga usa a distancia SEGUINTE da lista, nao sempre a
mesma), nao niveis simultaneos de verdade. Editar `machine.py` para suportar
`resting_limit` como lista esta' fora do escopo desta frente (arquivo
compartilhado, dono e' a Frente F0) -- o rodizio e' o proxy mais honesto
disponivel dentro da infra atual. Ver o relatorio da rodada para a
comparacao rodizio-vs-nivel-unico e a ressalva.

Mecanica herdada do v1 (grid_reload_maker.py), sem mudanca:
- entrada e' `EnterLimit` (maker, sem slippage); alvo tambem e' ordem-limite
  no proprio `EnterLimit.initial_target` (`target_fills_as_maker=True` na
  config faz o motor fechar sem slippage); stop e' protecao a MERCADO
  (`initial_stop`), paga slippage por ser saida de urgencia.
- so' um lado fica com ordem pendente por vez; ao fechar (alvo OU stop), o
  robo alterna para o OUTRO lado tentar primeiro (mesmo espirito
  anti-vies-de-tendencia do v1).
- `max_trades_per_side` conta reloads TOTAIS do lado (somando todas as
  distancias), nao por distancia -- e' o mesmo teto de sessao do v1,
  generalizado.
- `session_stop_brl=None` desliga o stop agregado de sessao (default, ao
  contrario do v1): esta frente mede GEOMETRIA por trade, nao politica de
  risco agregada -- misturar as duas confundiria qual efeito produziu qual
  numero. Quem quiser o overlay de risco passa um valor explicito.
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
class _SessionState:
    open_price: float | None = None
    session_halted: bool = False
    pending_side: str | None = None
    pending_level_idx: int | None = None
    open_side: str | None = None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None
    next_level_idx: dict = field(default_factory=lambda: {"long": 0, "short": 0})


class WdoGeoGridReload(IntradayStrategy):
    """Grid maker com recarga (alvo ou stop largo fecha, o robo rearma) e
    ate `n_levels` distancias em rodizio por lado. `n_levels=1` reproduz
    exatamente a mecanica de `GridReloadMaker` (uma unica distancia,
    recarregada sempre no mesmo lugar), so' que com tick de PONTOS."""

    name = "wdo_geo_grid_reload"
    version = "0.1"
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "WDO@",
        tick_size: float = 0.5,
        level_spacing_ticks: int = 16,
        profit_ticks: int = 1,
        stop_ticks: int | None = 16,
        n_levels: int = 1,
        max_trades_per_side: int = 999,
        session_stop_brl: float | None = None,
        quantity: int | None = None,
    ):
        if n_levels < 1:
            raise ValueError("n_levels precisa ser >= 1")
        self.symbol = symbol
        self.tick_size = tick_size
        self.level_spacing_ticks = level_spacing_ticks
        self.profit_ticks = profit_ticks
        self.stop_ticks = stop_ticks
        self.n_levels = n_levels
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = None if session_stop_brl is None else abs(session_stop_brl)
        self.quantity = quantity

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def _level_price(self, side: str, level_idx: int) -> float:
        offset = (level_idx + 1) * self.level_spacing_ticks * self.tick_size
        base = self._state.open_price
        return base - offset if side == "long" else base + offset

    def _target_price(self, side: str, level_price: float) -> float:
        offset = self.profit_ticks * self.tick_size
        return level_price + offset if side == "long" else level_price - offset

    def _stop_price(self, side: str, level_price: float) -> float | None:
        if self.stop_ticks is None:
            return None
        offset = self.stop_ticks * self.tick_size
        return level_price - offset if side == "long" else level_price + offset

    def _fills_of(self, side: str) -> int:
        return self._state.long_fills if side == "long" else self._state.short_fills

    def _next_side_to_arm(self) -> str | None:
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)
        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []

        if state.open_price is None:
            state.open_price = bar.open

        if (
            self.session_stop_brl is not None
            and not state.session_halted
            and session_pnl_brl <= -self.session_stop_brl
        ):
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if positions:
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
                state.pending_level_idx = None
            return []

        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        if state.pending_side is not None:
            return actions

        next_side = self._next_side_to_arm()
        if next_side is None:
            return actions

        level_idx = state.next_level_idx[next_side]
        state.next_level_idx[next_side] = (level_idx + 1) % self.n_levels

        state.pending_side = next_side
        state.pending_level_idx = level_idx
        level_price = self._level_price(next_side, level_idx)
        return [EnterLimit(
            side=next_side,
            limit_price=level_price,
            initial_target=self._target_price(next_side, level_price),
            initial_stop=self._stop_price(next_side, level_price),
            quantity=self.quantity,
            reason=f"wdo_geo_grid_reload_{next_side}_L{level_idx}",
        )]
