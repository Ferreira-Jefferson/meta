"""GREMAH = abreviacao de "Grid REload MAker Hybrid" (2026-08-21).

Combina os dois desenhos anteriores num robo so'. Ancora FIXA na abertura
(como a geracao anterior, ticks%) enquanto o pregao ainda esta "fresco"
(antes de `fixed_anchor_until`, por padrao 14:00 UTC / ~11h Brasilia); a
partir dai, muda para ancora ROLANTE (recalculada a cada recarga a partir
do preco ATUAL) para o resto da sessao -- nao precisa mais saber onde foi
a abertura a partir desse ponto.

Motivado por um achado empirico direto (2026-08-21, in-sample real,
PMAM3): mesmo com a abertura corretamente calibrada
(`warm_start_calibration`), o grid ancorado na abertura degrada de
+R$747,10 (comecando as 13:00 UTC, a abertura real) para -R$1.000,50
(comecando as 18:00 UTC) no MESMO periodo de dados -- o preco deriva da
abertura conforme o dia avanca e os niveis fixos ficam cada vez mais
"fora do dinheiro" (raramente tocados, e quando tocados o contexto de
preco ja' e' outro). Um grid de ancora rolante pura NAO degrada dessa
forma (fica estavel entre R$305 e R$615 em qualquer horario testado), mas
comecando EXATAMENTE na abertura perde para o fixo (R$514 vs R$747) --
abre mao do edge especifico de reversao-ao-redor-da-abertura que parece
so' existir nas primeiras horas do pregao.

Este hibrido tenta capturar os dois: o edge forte e especifico do inicio
do pregao (fixo) sem herdar a degradacao do fim do pregao (rolante).
`fixed_anchor_until` (14:00 UTC por padrao) NAO foi re-otimizado -- e' so'
o ponto medio observavel entre "13:00 ainda positivo" e "15:00 ja'
negativo" na tabela que motivou este desenho; validar/varrer esse corte e'
trabalho futuro, nao presumir que 14:00 e' o otimo.

Uso correto (decidido pelo CALLER, nao pela classe): so' fazer
`warm_start_calibration` (buscar a abertura real via historico) se a hora
de inicio for ANTES de `fixed_anchor_until` -- se nao sobra janela fixa
real, pular o warm-start e deixar o robo rodar cru desde agora (ele ja se
comporta como puro modo rolante nesse caso). Ver
`strategy/daytrade/base.py::warm_start_calibration` e a memoria do
campeao de day trade PMAM3 para o historico completo da investigacao."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

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
    pending_mode: str | None = None  # "fixed" ou "rolling" -- modo em que a ordem pendente foi armada
    pending_bars_waited: int = 0
    open_side: str | None = None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None
    spacing_ticks_today: int = 1
    profit_ticks_today: int = 1
    stop_ticks_today: int | None = None


class Gremah(IntradayStrategy):
    """Ancora fixa na abertura ate' `fixed_anchor_until`; ancora rolante
    (preco atual, recalculada a cada recarga) depois disso."""

    name = "gremah"
    version = "0.1"
    # A saida por alvo deste robo e uma ordem-limite parada no nivel: e o
    # centro do desenho (capturar o spread em vez de paga-lo), nao um
    # detalhe de modelagem. Ver `IntradayStrategy.target_fills_as_maker`.
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "PMAM3",
        tick_size: float = 0.01,
        profit_pct: float = 0.0042,
        spacing_multiplier: float = 2.0,
        stop_multiplier: float = 20.0,
        max_trades_per_side: int = 15,
        session_stop_brl: float = 30.0,
        quantity: int | None = None,
        fixed_anchor_until: time = time(14, 0),
        rolling_reanchor_after_bars: int = 30,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        self.profit_pct = profit_pct
        self.spacing_multiplier = spacing_multiplier
        self.stop_multiplier = stop_multiplier
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = abs(session_stop_brl)
        self.quantity = quantity
        self.fixed_anchor_until = fixed_anchor_until
        # uma ordem ROLANTE parada esperando por muitas barras acumula o
        # MESMO problema que motivou abandonar a ordem fixa na troca de
        # fase: seu preco de ancora (o preco de QUANDO foi armada) vai
        # ficando cada vez mais desatualizado frente ao preco ATUAL.
        # Achado empirico (2026-08-21): sem isso, uma ordem herdada do
        # warm-start (armada perto do fim da fase fixa, nunca tocada) fica
        # parada com ancora velha por horas ate' o robo comecar a operar
        # de verdade num horario atrasado -- o hibrido ficava pior que a
        # rolling pura em todo horario de entrada atrasada.
        self.rolling_reanchor_after_bars = rolling_reanchor_after_bars

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def _ticks_from_pct(self, price: float, pct: float) -> int:
        return max(1, round(price * pct / self.tick_size))

    def _arm_fixed_session_params(self) -> None:
        price = self._state.open_price
        self._state.profit_ticks_today = self._ticks_from_pct(price, self.profit_pct)
        self._state.spacing_ticks_today = self._ticks_from_pct(price, self.profit_pct * self.spacing_multiplier)
        self._state.stop_ticks_today = self._ticks_from_pct(price, self.profit_pct * self.stop_multiplier)

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

    def _build_entry(self, side: str, anchor: float, spacing_ticks: int, profit_ticks: int, stop_ticks: int | None) -> EnterLimit:
        spacing_off = spacing_ticks * self.tick_size
        level_price = round(anchor - spacing_off, 2) if side == "long" else round(anchor + spacing_off, 2)
        profit_off = profit_ticks * self.tick_size
        target_price = level_price + profit_off if side == "long" else level_price - profit_off
        stop_price = None
        if stop_ticks is not None:
            stop_off = stop_ticks * self.tick_size
            stop_price = level_price - stop_off if side == "long" else level_price + stop_off
        return EnterLimit(
            side=side,
            limit_price=level_price,
            initial_target=target_price,
            initial_stop=stop_price,
            quantity=self.quantity,
            reason="gremah_" + side,
        )

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        position: IntradayOpenPosition | None,
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []
        is_fixed_phase = ts.time() < self.fixed_anchor_until

        if is_fixed_phase and state.open_price is None:
            state.open_price = bar.open
            self._arm_fixed_session_params()

        if not state.session_halted and session_pnl_brl <= -self.session_stop_brl:
            state.session_halted = True
            if position is not None:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if position is not None:
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
                state.pending_bars_waited = 0
            return []

        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        # ordem pendente parada ficou obsoleta de 1 de 2 jeitos: (a) foi
        # armada na fase FIXA e o relogio ja passou pra fase ROLANTE --
        # nivel so' fazia sentido perto da abertura; (b) foi armada em
        # modo ROLANTE mas ja' esperou tempo demais sem tocar -- seu
        # preco de ancora (de QUANDO foi armada) ja' ficou velho frente
        # ao preco atual. Nos dois casos: abandona (o motor substitui a
        # resting_limit pela nova `EnterLimit` devolvida abaixo) e
        # re-arma no modo/preco atual, mesmo lado.
        stale_fixed_order = state.pending_side is not None and state.pending_mode == "fixed" and not is_fixed_phase
        stale_rolling_order = (
            state.pending_side is not None and state.pending_mode == "rolling"
            and state.pending_bars_waited >= self.rolling_reanchor_after_bars
        )
        stale_order = stale_fixed_order or stale_rolling_order
        if state.pending_side is not None and not stale_order:
            state.pending_bars_waited += 1
            return actions

        next_side = state.pending_side if stale_order else self._next_side_to_arm()
        if next_side is None:
            return actions

        state.pending_side = next_side
        state.pending_bars_waited = 0
        state.pending_mode = "fixed" if is_fixed_phase else "rolling"
        if is_fixed_phase:
            entry = self._build_entry(
                next_side, state.open_price,
                state.spacing_ticks_today, state.profit_ticks_today, state.stop_ticks_today,
            )
        else:
            anchor = bar.close
            profit_ticks = self._ticks_from_pct(anchor, self.profit_pct)
            spacing_ticks = self._ticks_from_pct(anchor, self.profit_pct * self.spacing_multiplier)
            stop_ticks = self._ticks_from_pct(anchor, self.profit_pct * self.stop_multiplier)
            entry = self._build_entry(next_side, anchor, spacing_ticks, profit_ticks, stop_ticks)
        return [entry]
