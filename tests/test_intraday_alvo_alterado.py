"""Duas lacunas do contrato motor<->estrategia, fechadas em 2026-09-10 ao
portar a ORB (`strategy.daytrade.lab.wdo_orb`) para producao.

1. A ordem-limite de ENTRADA que morre por PRAZO nao avisava ninguem.
   `on_order_rejected` so' dispara na recusa por teto/capital; o cancelamento
   por `ttl_bars` emitia `LimitCancelled(reason="ttl")` para o DIARIO e
   seguia. Um robo que guarda "ja' armei hoje" fora de `positions` ficava
   mudo pelo resto do pregao -- 14 dos 72 pregoes do IS da ORB,
   +R$1.236,00 contra +R$1.649,00.

2. `AdjustTarget` nao alcancava a ordem-limite de SAIDA ja' parada. O alvo da
   posicao mudava na hora, o backtest passava a medir o nivel novo -- e a
   ordem REAL continuava no preco velho, porque quem a posicionou foi o bloco
   `target_hit`, uma vez so'. O robo ao vivo esperava um alvo que o robo
   medido ja' tinha abandonado.

A segunda tem duas metades que precisam andar juntas, e por isso ha' um teste
para cada: na execucao REAL a ordem e' cancelada e remandada; no SIMULADO a
fatia tem de perder a fila ja' consumida do nivel velho, senao o backtest
mede um robo mais rapido do que a corretora executa.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.machine import (
    IntradayBacktestConfig,
    IntradaySessionMachine,
    LimitCancelled,
)
from strategy.daytrade.base import AdjustTarget, Bar, EnterLimit, IntradayStrategy

LIMITE, ALVO_VELHO, ALVO_NOVO, STOP = 10.00, 10.10, 10.04, 9.90


def _bar(minute: int, o, h, low, c, volume: float = 999.0) -> Bar:
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC") + pd.Timedelta(minutes=minute)
    return Bar(ts=ts, open=float(o), high=float(h), low=float(low),
               close=float(c), volume=float(volume))


def _config(**over) -> IntradayBacktestConfig:
    base = dict(
        costs=IntradayCostModel(point_value_brl=1.0, tick_size=0.01,
                                fee_round_trip_brl=0.0, slippage_ticks=1.0),
        initial_capital=1_000.0,  # mecanica, nao economia
        session_end_time=time(23, 59),
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
        default_quantity=1,
    )
    base.update(over)
    return IntradayBacktestConfig(**base)


class _Roteirizada(IntradayStrategy):
    """Devolve as acoes do roteiro (por indice de barra) e anota os avisos que
    o motor manda de volta -- e' justamente o caminho de volta que estes
    testes medem."""

    name = "roteirizada"
    version = "1"
    symbol = "TEST"

    def __init__(self, roteiro: dict[int, list]):
        self.roteiro = roteiro
        self._i = -1
        self.expiradas: list[pd.Timestamp] = []
        self.recusadas: list[pd.Timestamp] = []

    def on_session_start(self, session_date) -> None:
        self._i = -1

    def on_order_expired(self, ts) -> None:
        self.expiradas.append(ts)

    def on_order_rejected(self, ts) -> None:
        self.recusadas.append(ts)

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        self._i += 1
        return self.roteiro.get(self._i, [])


class _ExecucaoFake:
    """O minimo de `MT5IntradayExecution` que `_resolve_live_split_exit` usa,
    gravando COM QUE PRECO cada fatia de saida foi posicionada."""

    def __init__(self):
        self.precos_posicionados: list[float] = []
        self.cancelamentos: list[str] = []
        self.exit_fill_resposta: dict | None = None

    def limit_fill(self, order, bar):
        if bar.low <= order.limit_price <= bar.high:
            return {"price": order.limit_price, "quantity": order.quantity or 1}
        return None

    def exit_fill(self, side, bar):
        return self.exit_fill_resposta

    def place_exit_limit(self, **kwargs):
        self.precos_posicionados.append(kwargs["limit_price"])

    def cancel_exit_limit(self, ts, reason):
        self.cancelamentos.append(reason)
        return None  # `None` = nada pendente / cancelamento sem ressalva

    def exit_market(self, position, ts, reason):
        return {"price": float(position.entry_price)}


# ---------- (1) a ordem de entrada que morre por PRAZO ----------------------

def test_ordem_de_entrada_que_estoura_o_prazo_avisa_a_estrategia():
    """O aviso de volta e' a diferenca entre um robo que rearma e um robo
    CEGO. O motor ja' cancelava a ordem certinho e emitia `LimitCancelled`;
    o que faltava era a estrategia ficar sabendo.

    Criterio: mesma barra do `LimitCancelled(reason="ttl")`, mesmo `ts`."""
    strat = _Roteirizada({0: [EnterLimit(side="long", limit_price=9.00,
                                         initial_target=ALVO_VELHO,
                                         initial_stop=STOP, ttl_bars=2)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))   # posiciona
    m.on_closed_bar(_bar(1, 10.00, 10.00, 9.95, 10.00))    # nao toca: espera 1
    assert strat.expiradas == [], "o prazo ainda nao estourou"

    evs = m.on_closed_bar(_bar(2, 10.00, 10.00, 9.95, 10.00))  # espera 2 = ttl

    cancelamentos = [e for e in evs if isinstance(e, LimitCancelled)]
    assert [e.reason for e in cancelamentos] == ["ttl"]
    assert strat.expiradas == [cancelamentos[0].ts]
    assert strat.recusadas == [], (
        "morte por prazo NAO e' recusa por teto -- sao dois hooks porque sao "
        "duas causas, e um robo pode querer reagir diferente a cada uma"
    )


def test_hook_de_prazo_tem_default_no_op_para_nao_quebrar_robo_antigo():
    """`on_order_expired` nasceu depois de todo robo do podio. Nenhum deles
    sobrescreve, e o motor chama em todo estouro de prazo -- se o default nao
    fosse no-op, ligar `ttl_bars` em qualquer robo existente viraria
    `AttributeError` em producao."""
    class _Surda(IntradayStrategy):
        """Nao sobrescreve hook nenhum -- como todo robo do podio."""

        name, version, symbol = "surda", "1", "TEST"

        def __init__(self):
            self._i = -1

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            self._i += 1
            if self._i == 0:
                return [EnterLimit(side="long", limit_price=9.00,
                                   initial_stop=STOP, ttl_bars=1)]
            return []

    m = IntradaySessionMachine(_Surda(), _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    evs = m.on_closed_bar(_bar(1, 10.00, 10.00, 9.95, 10.00))

    assert [e.reason for e in evs if isinstance(e, LimitCancelled)] == ["ttl"]


# ---------- (2a) o alvo mudou: EXECUCAO REAL --------------------------------

def _maquina_com_fatia_armada(execucao, roteiro) -> IntradaySessionMachine:
    """Barra 0 posiciona a entrada, barra 1 preenche, barra 2 toca o alvo
    VELHO e arma a fatia de saida no book."""
    roteiro = dict(roteiro)
    roteiro[0] = [EnterLimit(side="long", limit_price=LIMITE,
                             initial_target=ALVO_VELHO, initial_stop=STOP,
                             exit_split_unit=1, exit_ttl_bars=99)]
    strat = _Roteirizada(roteiro)
    m = IntradaySessionMachine(strat, _config(), execution=execucao)
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.20, 10.20, 10.20, 10.20))
    m.on_closed_bar(_bar(1, 10.05, 10.05, 9.99, 10.01))
    assert len(m.positions) == 1, "a entrada tinha de ter preenchido"
    m.on_closed_bar(_bar(2, 10.01, ALVO_VELHO, 10.00, 10.05))
    assert execucao.precos_posicionados == [ALVO_VELHO]
    return m


def test_alvo_alterado_cancela_a_fatia_real_e_remanda_no_nivel_novo():
    """Este e' o teste que separa "o backtest mudou de alvo" de "a corretora
    mudou de alvo". Sem ele o robo ao vivo fica esperando, para sempre, um
    preco que a estrategia ja' abandonou -- e a posicao so' sai no
    achatamento de fim de pregao, a MERCADO, que e' exatamente o custo que
    este desenho de execucao existe para nao pagar."""
    execucao = _ExecucaoFake()
    # barra 3: o robo desiste do alvo velho e pede o preco corrente.
    m = _maquina_com_fatia_armada(execucao, {3: [AdjustTarget(ALVO_NOVO)]})

    m.on_closed_bar(_bar(3, 10.05, 10.06, 10.02, 10.04))
    assert m.positions[0].current_target == ALVO_NOVO, "o alvo muda na hora"

    # barra 4: o motor ve a divergencia, cancela e remanda no nivel novo.
    m.on_closed_bar(_bar(4, 10.04, ALVO_NOVO, 10.02, 10.04))

    assert execucao.cancelamentos == ["alvo_alterado"]
    assert execucao.precos_posicionados == [ALVO_VELHO, ALVO_NOVO]
    assert m.positions[0].exit_resting_price == ALVO_NOVO


def test_alvo_inalterado_nao_remanda_nada():
    """A contrapartida do teste acima, e a que protege a fila: cancelar e
    remandar uma limite joga fora toda a espera ja acumulada no nivel. Se o
    robo nao mudou o alvo, a ordem tem de ficar exatamente onde esta."""
    execucao = _ExecucaoFake()
    m = _maquina_com_fatia_armada(execucao, {})

    m.on_closed_bar(_bar(3, 10.05, 10.06, 10.02, 10.04))
    m.on_closed_bar(_bar(4, 10.04, 10.06, 10.02, 10.04))

    assert execucao.cancelamentos == []
    assert execucao.precos_posicionados == [ALVO_VELHO]


# ---------- (2b) o alvo mudou: SIMULADO, e a fila -------------------------

def test_no_simulado_o_alvo_novo_comeca_com_a_fila_do_nivel_CHEIA():
    """Uma ordem-limite parada num preco nao vira outro preco sozinha: ela e'
    cancelada e outra e' mandada, e a nova entra no FIM da fila daquele nivel.

    Sem isto o backtest herdava a fila ja' consumida do alvo VELHO para
    preencher no alvo NOVO -- mediria um robo mais rapido do que o que a
    corretora executa, que e' a familia de erro inteira que
    `backtest/intraday/fidelidade.py` existe para fechar."""
    strat = _Roteirizada({
        0: [EnterLimit(side="long", limit_price=LIMITE, initial_target=ALVO_VELHO,
                       initial_stop=STOP, exit_split_unit=1, exit_ttl_bars=99)],
        4: [AdjustTarget(ALVO_NOVO)],
    })
    m = IntradaySessionMachine(strat, _config(exit_queue_ahead_qty=100.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.20, 10.20, 10.20, 10.20, volume=0.0))
    m.on_closed_bar(_bar(1, 10.05, 10.05, 9.99, 10.01, volume=50.0))
    assert len(m.positions) == 1

    # barra 2: toca o alvo velho e ARMA a fatia -- fila cheia, sem consumo
    # ainda (o atraso estrutural de 1 barra vale para a fila tambem).
    m.on_closed_bar(_bar(2, 10.01, ALVO_VELHO, 10.00, 10.05, volume=40.0))
    pos = m.positions[0]
    assert pos.exit_resting_qty == 1
    assert pos.exit_queue_ahead_remaining == 100.0

    # barra 3: toca de novo -- 40 negociados NO NIVEL comem 40 da fila.
    m.on_closed_bar(_bar(3, 10.05, ALVO_VELHO, 10.02, 10.05, volume=40.0))
    assert pos.exit_queue_ahead_remaining == 60.0, "a fila do nivel velho andou"

    # barra 4: o robo pede o alvo novo (aplicado no fim desta barra).
    m.on_closed_bar(_bar(4, 10.05, 10.06, 10.02, 10.04, volume=10.0))
    assert pos.current_target == ALVO_NOVO

    # barra 5: fatia rearmada no nivel NOVO -- fila cheia de novo, nao 60.
    m.on_closed_bar(_bar(5, 10.04, ALVO_NOVO, 10.02, 10.04, volume=10.0))
    assert pos.exit_resting_price == ALVO_NOVO
    assert pos.exit_queue_ahead_remaining == 100.0, (
        "a ordem no nivel NOVO entra no FIM daquela fila -- herdar os 60 ja "
        "consumidos no nivel velho seria medir um robo que a corretora nao "
        "executa"
    )
