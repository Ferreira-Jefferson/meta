"""Grid RELOAD maker (2026-08-21) — evolucao de
`grid_bidirecional_ticks_maker2.py` com duas ideias novas, motivadas
pelo que ja foi aprendido com ele:

1. RECARREGA o mesmo nivel. O v2 tem N niveis fixos por lado e cada um
   dispara UMA vez por sessao (depois de preenchido, nunca mais). Mas o
   proprio v2 so funciona porque a PMAM3 da repiques pequenos e
   frequentes (nao tendencia -- a versao que apostou em tendencia
   quebrou a conta, ver `grid_maker_assimetrico.py`, apagado). Se o
   repique se repete, o MESMO nivel de recuo pode ser tocado varias
   vezes no mesmo pregao -- esta versao reabre uma ordem-limite no
   MESMO nivel assim que a posicao anterior fecha (por alvo OU por
   stop), em vez de avancar pra um nivel mais distante que talvez nunca
   seja tocado.
2. STOP LARGO de protecao por posicao (`stop_ticks`, default 20 -- bem
   mais largo que o alvo de 1 tick, pra nao competir com a taxa de
   acerto). O v2 nao tinha stop nenhum por posicao: uma entrada que
   nunca voltasse ao alvo so fechava no flatten forcado do fim do
   pregao, com perda potencialmente grande e sem limite. Esta versao
   fecha (a mercado, paga slippage -- protecao precisa de garantia)
   qualquer posicao que andar `stop_ticks` contra a entrada, cortando a
   cauda de risco antes do fim do dia.

Contagem de niveis por sessao: `max_trades_per_side` limita quantas
vezes CADA lado (long/short) pode recarregar no mesmo pregao -- sem
isso, um dia excepcionalmente ruidoso poderia gerar entradas demais e
testar um regime de frequencia que nao foi o que passou no v2.
"""
from __future__ import annotations

from dataclasses import dataclass

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
    pending_side: str | None = None  # lado da EnterLimit pendente (ainda nao preenchida), ou None
    open_side: str | None = None  # lado da posicao CONFIRMADA aberta agora, ou None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None  # qual lado acabou de fechar (pra decidir o proximo a recarregar)


class GridReloadMaker(IntradayStrategy):
    """Grid maker com recarga do mesmo nivel apos cada fechamento (alvo
    ou stop largo), em vez de avancar por uma lista fixa de niveis."""

    name = "grid_reload_maker"
    version = "0.1"
    # A saida por alvo deste robo e uma ordem-limite parada no nivel: e o
    # centro do desenho (capturar o spread em vez de paga-lo), nao um
    # detalhe de modelagem. Ver `IntradayStrategy.target_fills_as_maker`.
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "PMAM3",
        tick_size: float = 0.01,
        level_spacing_ticks: int = 3,
        profit_ticks: int = 1,
        stop_ticks: int | None = 20,
        max_trades_per_side: int = 15,
        session_stop_brl: float = 30.0,
        quantity: int | None = None,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        self.level_spacing_ticks = level_spacing_ticks
        self.profit_ticks = profit_ticks
        self.stop_ticks = stop_ticks
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = abs(session_stop_brl)
        self.quantity = quantity

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def _level_price(self, side: str) -> float:
        offset = self.level_spacing_ticks * self.tick_size
        return round(self._state.open_price - offset, 2) if side == "long" else round(self._state.open_price + offset, 2)

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
        # Alterna comecando pelo lado que NAO acabou de fechar (evita
        # reemitir de imediato o mesmo lado que estava presenca, mas
        # ambos os lados sao rearmados de forma independente -- so
        # existe UMA ordem pendente por vez, dado o motor permitir so
        # uma posicao aberta simultaneamente).
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

        if not state.session_halted and session_pnl_brl <= -self.session_stop_brl:
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if positions:
            # Confirma o preenchimento da EnterLimit pendente (a
            # entrada), se for o caso -- so acontece na PRIMEIRA chamada
            # com posicao aberta apos a ordem ter sido emitida.
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
            return []  # alvo e stop ja sao geridos pelo motor (initial_target/initial_stop)

        # Sem posicao. Se `open_side` ainda estava marcado, a posicao que
        # existia na chamada anterior fechou entre uma chamada e outra
        # (via alvo ou stop, geridos pelo motor sem passar por uma acao
        # explicita da estrategia) -- registra qual lado foi, pra decidir
        # o proximo a recarregar.
        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        if state.pending_side is not None:
            return actions  # ja ha ordem-limite pendente (entrada ainda nao preenchida), so espera

        next_side = self._next_side_to_arm()
        if next_side is None:
            return actions  # os dois lados esgotaram max_trades_per_side nesta sessao

        state.pending_side = next_side
        level_price = self._level_price(next_side)
        return [EnterLimit(
            side=next_side,
            limit_price=level_price,
            initial_target=self._target_price(next_side, level_price),
            initial_stop=self._stop_price(next_side, level_price),
            quantity=self.quantity,
            reason="grid_reload_" + next_side,
        )]
