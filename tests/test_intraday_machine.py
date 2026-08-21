"""Testes de `backtest/intraday/machine.py::IntradaySessionMachine` — o
contrato NOVO que a extracao criou (eventos, `resume_session`,
`state()`/`restore()`, `force_flatten`).

O que a extracao NAO mudou ja esta coberto por `tests/test_intraday_engine.py`
(e pelos testes de cada robo), que passam sem edicao nenhuma: essa e a prova
de que o comportamento por barra foi preservado. Aqui so o que a maquina
passou a expor para a operacao ao vivo (`live/intraday_runtime.py`) consumir.
"""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.machine import (
    IntradayBacktestConfig,
    IntradaySessionMachine,
    LimitCancelled,
    LimitPlaced,
    PositionClosed,
    PositionOpened,
)
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, Enter, EnterLimit, Exit, IntradayStrategy


def _bar(minute: int, o, h, low, c) -> Bar:
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC") + pd.Timedelta(minutes=minute)
    return Bar(ts=ts, open=float(o), high=float(h), low=float(low), close=float(c), volume=0.0)


def _config(**over) -> IntradayBacktestConfig:
    base = dict(
        costs=IntradayCostModel(point_value_brl=1.0, tick_size=0.01,
                               fee_round_trip_brl=0.0, slippage_ticks=0.0),
        session_end_time=time(23, 59),
        target_fills_as_maker=True,
        default_quantity=1,
    )
    base.update(over)
    return IntradayBacktestConfig(**base)


class _Scripted(IntradayStrategy):
    """Devolve acoes por indice de barra. `session_starts` conta quantas vezes
    `on_session_start` foi chamado — e' o que distingue `begin_session` de
    `resume_session`."""

    name = "scripted"
    version = "1"
    symbol = "TEST"

    def __init__(self, script: dict[int, list]):
        self.script = script
        self.session_starts = 0
        self._i = -1

    def on_session_start(self, session_date) -> None:
        self.session_starts += 1
        self._i = -1

    def on_bar(self, ts, bar, position, session_pnl_brl):
        self._i += 1
        return list(self.script.get(self._i, []))


# ---------- eventos --------------------------------------------------------

def test_limit_placed_e_position_opened_descrevem_a_entrada_maker():
    """A operacao ao vivo precisa saber DUAS coisas distintas: que ordem foi
    posta (para mandar/mostrar a pendente) e que ela preencheu (para
    journalizar o fill). Um evento so nao distingue as duas."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80,
                                      initial_target=9.90, initial_stop=9.00,
                                      reason="teste_long")]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    ev0 = m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    assert [type(e) for e in ev0] == [LimitPlaced]
    assert ev0[0].order.limit_price == pytest.approx(9.80)
    assert ev0[0].replaced is None

    # a barra seguinte TOCA o nivel -> preenche exatamente nele (maker)
    ev1 = m.on_closed_bar(_bar(1, 10.00, 10.00, 9.79, 9.85))
    abertas = [e for e in ev1 if isinstance(e, PositionOpened)]
    assert len(abertas) == 1
    assert abertas[0].order_kind == "limit"
    assert abertas[0].price == pytest.approx(9.80)
    assert abertas[0].side == "long"
    assert abertas[0].reason == "teste_long"
    # a barra do fill viaja no evento -- e' dela que sai a medicao de
    # penetracao do nivel no modo sombra (ver `live/intraday_runtime.py`).
    assert abertas[0].bar.low == pytest.approx(9.79)


def test_position_closed_carrega_o_trade_completo():
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80,
                                      initial_target=9.90, initial_stop=9.00)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    m.on_closed_bar(_bar(1, 10.00, 10.00, 9.79, 9.85))   # fill em 9.80
    ev = m.on_closed_bar(_bar(2, 9.85, 9.91, 9.85, 9.90))  # toca o alvo 9.90

    fechadas = [e for e in ev if isinstance(e, PositionClosed)]
    assert len(fechadas) == 1
    trade = fechadas[0].trade
    assert trade.entry_price == pytest.approx(9.80)
    assert trade.exit_price == pytest.approx(9.90)
    assert trade.exit_reason == IntradayExitReason.TARGET
    assert fechadas[0].pnl_brl == pytest.approx(0.10)
    assert m.realized_pnl == pytest.approx(0.10)
    assert m.session_pnl == pytest.approx(0.10)


def test_ordem_limite_substituida_viaja_em_limit_placed_replaced():
    """Uma `EnterLimit` nova SUBSTITUI a pendente (nao acumula). Ao vivo isso
    e' "cancela a antiga, manda a nova" na corretora — e as duas metades vem
    no MESMO evento (`LimitPlaced.replaced`), nao em dois, para nao existir
    ordem de aplicacao ambigua entre cancelar e mandar."""
    strat = _Scripted({
        0: [EnterLimit(side="long", limit_price=9.80)],
        1: [EnterLimit(side="long", limit_price=9.70)],
    })
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    ev1 = m.on_closed_bar(_bar(1, 10.00, 10.05, 9.95, 10.00))

    postas = [e for e in ev1 if isinstance(e, LimitPlaced)]
    assert postas[0].order.limit_price == pytest.approx(9.70)
    assert postas[0].replaced.limit_price == pytest.approx(9.80)
    assert [e for e in ev1 if isinstance(e, LimitCancelled)] == []
    assert m.resting_limit.limit_price == pytest.approx(9.70)


def test_ttl_expirado_emite_cancelamento_por_ttl():
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.00, ttl_bars=1)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    ev1 = m.on_closed_bar(_bar(1, 10.00, 10.05, 9.95, 10.00))  # nao toca 9.00

    assert [e.reason for e in ev1 if isinstance(e, LimitCancelled)] == ["ttl"]
    assert m.resting_limit is None


def test_flatten_no_corte_de_horario_cancela_a_ordem_em_pe():
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.00)]})
    m = IntradaySessionMachine(strat, _config(session_end_time=time(13, 2)))
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    ev = m.on_closed_bar(_bar(2, 10.00, 10.00, 10.00, 10.00))  # 13:02 -> corte

    assert [e.reason for e in ev if isinstance(e, LimitCancelled)] == ["flatten"]
    assert m.flattened is True


def test_entrada_a_mercado_supera_e_cancela_a_ordem_limite_pendente():
    strat = _Scripted({
        0: [EnterLimit(side="long", limit_price=9.00)],
        1: [Enter(side="long", initial_target=10.50, initial_stop=9.50)],
    })
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    # O `Enter` e' decidido no fim da barra 1 -- e' ali que a ordem-limite
    # pendente e' abandonada, nao na barra em que o `Enter` executa.
    ev1 = m.on_closed_bar(_bar(1, 10.00, 10.02, 9.98, 10.00))
    ev2 = m.on_closed_bar(_bar(2, 10.01, 10.03, 9.99, 10.02))

    assert [c.reason for c in ev1 if isinstance(c, LimitCancelled)] == ["superseded"]
    abertas = [e for e in ev2 if isinstance(e, PositionOpened)]
    assert abertas[0].order_kind == "market"
    assert abertas[0].price == pytest.approx(10.01)  # abertura da barra


def test_short_produz_position_opened_com_lado_short():
    """Short foi verificado no terminal real (2026-08-21, `order_check` de
    `SELL_LIMIT` pendente em PMAM3F -> retcode 0). A maquina tem de reportar
    o lado, senao a operacao ao vivo nao sabe o sinal da quantidade."""
    strat = _Scripted({0: [EnterLimit(side="short", limit_price=10.20,
                                      initial_target=10.10, initial_stop=11.00)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    ev1 = m.on_closed_bar(_bar(1, 10.00, 10.21, 10.00, 10.15))

    abertas = [e for e in ev1 if isinstance(e, PositionOpened)]
    assert abertas[0].side == "short"
    assert abertas[0].price == pytest.approx(10.20)


# ---------- begin_session vs resume_session --------------------------------

def test_begin_session_avisa_o_robo_resume_session_nao():
    """`resume_session` existe para o caso em que o robo JA foi calibrado por
    fora (`warm_start_calibration`): chamar `on_session_start` de novo
    apagaria a calibracao que acabou de ser montada."""
    strat = _Scripted({})
    m = IntradaySessionMachine(strat, _config())

    m.begin_session(pd.Timestamp("2026-01-05").date())
    assert strat.session_starts == 1

    m.resume_session(pd.Timestamp("2026-01-05").date())
    assert strat.session_starts == 1  # nao subiu


def test_resume_session_com_seed_pending_vigia_a_ordem_desde_a_primeira_barra():
    """Sem isto, a ordem que o robo deixou em pe no replay seria descartada e
    o robo precisaria de uma barra EXTRA so para redecidir o mesmo -- uma
    barra de defasagem que a dependencia de caminho amplifica."""
    strat = _Scripted({})  # nao decide nada: a ordem tem de vir do seed
    m = IntradaySessionMachine(strat, _config())
    m.resume_session(pd.Timestamp("2026-01-05").date(),
                     seed_pending=EnterLimit(side="long", limit_price=9.80,
                                             initial_target=9.90))

    ev = m.on_closed_bar(_bar(0, 10.00, 10.00, 9.79, 9.85))

    abertas = [e for e in ev if isinstance(e, PositionOpened)]
    assert len(abertas) == 1
    assert abertas[0].price == pytest.approx(9.80)


def test_resume_session_sem_seed_nao_cancela_ordem_ja_vigiada():
    """Reconectar no meio do pregao nao pode cancelar o que ja estava de pe."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    assert m.resting_limit is not None

    m.resume_session(pd.Timestamp("2026-01-05").date(), seed_pending=None)

    assert m.resting_limit is not None


def test_begin_session_limpa_a_ordem_vigiada():
    """Sessao NOVA e' outro dia: nada de ontem sobrevive (day trade nunca
    carrega posicao nem ordem overnight)."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))

    m.begin_session(pd.Timestamp("2026-01-06").date())

    assert m.resting_limit is None
    assert m.session_pnl == pytest.approx(0.0)


# ---------- state()/restore(): sobreviver a um restart do processo ----------

def test_state_restore_preserva_posicao_aberta_e_pnl():
    """Ao vivo o processo pode reiniciar no meio do pregao. Sem persistir a
    posicao, o robo esqueceria que esta comprado e abriria outra."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80,
                                      initial_target=9.90, initial_stop=9.00)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    m.on_closed_bar(_bar(1, 10.00, 10.00, 9.79, 9.85))  # fill
    assert m.position is not None

    snapshot = m.state()

    outra = IntradaySessionMachine(_Scripted({}), _config())
    outra.restore(snapshot)

    assert outra.position is not None
    assert outra.position.side == "long"
    assert outra.position.entry_price == pytest.approx(9.80)
    assert outra.position.entry_ts == m.position.entry_ts
    assert outra.session_date == m.session_date
    assert outra.realized_pnl == pytest.approx(m.realized_pnl)


def test_state_nao_persiste_a_ordem_vigiada():
    """A ordem em pe e' uma DECISAO do robo, e o robo e' recalibrado do dado
    real ao voltar (`warm_start_calibration`) -- restaurar um nivel velho de
    snapshot seria pior que redecidir."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))

    outra = IntradaySessionMachine(_Scripted({}), _config())
    outra.restore(m.state())

    assert outra.resting_limit is None


def test_state_de_maquina_sem_posicao_restaura_vazia():
    m = IntradaySessionMachine(_Scripted({}), _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    outra = IntradaySessionMachine(_Scripted({}), _config())
    outra.restore(m.state())

    assert outra.position is None
    assert outra.session_date == pd.Timestamp("2026-01-05").date()


def test_restore_de_dict_vazio_nao_mexe_em_nada():
    m = IntradaySessionMachine(_Scripted({}), _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.restore({})
    assert m.session_date == pd.Timestamp("2026-01-05").date()


# ---------- force_flatten: buraco de barras ao vivo ------------------------

def test_force_flatten_fecha_posicao_no_preco_dado_e_cancela_ordem():
    """Usado quando o processo volta depois de um buraco grande de barras:
    reprocessar o buraco seria executar decisao velha (regra 7 do AGENTS.md),
    e ignora-lo deixaria posicao orfa."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80,
                                      initial_target=9.90, initial_stop=9.00)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    m.on_closed_bar(_bar(1, 10.00, 10.00, 9.79, 9.85))  # fill em 9.80

    ev = m.force_flatten(pd.Timestamp("2026-01-05 15:00", tz="UTC"), 9.50)

    fechadas = [e for e in ev if isinstance(e, PositionClosed)]
    assert len(fechadas) == 1
    assert fechadas[0].trade.exit_reason == IntradayExitReason.FORCED_FLATTEN
    assert fechadas[0].trade.exit_price == pytest.approx(9.50)
    assert m.position is None
    assert m.resting_limit is None
    assert m.flattened is True


def test_force_flatten_sem_posicao_nao_inventa_trade():
    m = IntradaySessionMachine(_Scripted({}), _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    ev = m.force_flatten(pd.Timestamp("2026-01-05 15:00", tz="UTC"), 9.50)

    assert [e for e in ev if isinstance(e, PositionClosed)] == []
    assert m.realized_pnl == pytest.approx(0.0)


# ---------- marcacao a mercado --------------------------------------------

def test_unrealized_brl_reflete_o_lado_da_posicao():
    strat = _Scripted({0: [EnterLimit(side="short", limit_price=10.20)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    m.on_closed_bar(_bar(1, 10.00, 10.21, 10.00, 10.15))  # short em 10.20

    # vendido a 10.20, preco caiu para 10.00 -> lucro de 0.20
    assert m.unrealized_brl(10.00) == pytest.approx(0.20)
    assert m.unrealized_brl(10.40) == pytest.approx(-0.20)


def test_unrealized_brl_sem_posicao_e_zero():
    m = IntradaySessionMachine(_Scripted({}), _config())
    assert m.unrealized_brl(10.0) == pytest.approx(0.0)


def test_exit_por_sinal_do_robo_vira_position_closed_signal():
    strat = _Scripted({
        0: [EnterLimit(side="long", limit_price=9.80)],
        2: [Exit(reason="chega")],
    })
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    m.on_closed_bar(_bar(1, 10.00, 10.00, 9.79, 9.85))  # fill
    m.on_closed_bar(_bar(2, 9.85, 9.88, 9.82, 9.86))    # robo pede saida
    ev = m.on_closed_bar(_bar(3, 9.86, 9.87, 9.84, 9.85))

    fechadas = [e for e in ev if isinstance(e, PositionClosed)]
    assert fechadas[0].trade.exit_reason == IntradayExitReason.SIGNAL
    assert fechadas[0].trade.exit_price == pytest.approx(9.86)  # abertura da barra
