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
        initial_capital=1_000.0,  # so' mecanica de eventos aqui, valor sem significado economico
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


# ---------- preenchimento capado por volume (FOK) e ordens divididas ------
# (2026-08-22, pedido do dono: uma ordem parada grande demais pode nao ser
# CASADA de verdade mesmo com o preco tendo tocado o nivel -- o motor
# assumia preenchimento 100% garantido no toque, otimismo que a B3 real nao
# sustenta (o RLP, que aumenta a liquidez disponivel num preco, so' interage
# com ordem A MERCADO, nunca com ordem parada). Ver `IntradayBacktestConfig.
# limit_fill_capped_by_volume`.)

def _bar_vol(minute: int, o, h, low, c, volume: float) -> Bar:
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC") + pd.Timedelta(minutes=minute)
    return Bar(ts=ts, open=float(o), high=float(h), low=float(low), close=float(c), volume=float(volume))


def test_entrada_nao_capada_preenche_mesmo_com_volume_baixo():
    """Default (`limit_fill_capped_by_volume=False`): comportamento ANTIGO
    intacto -- tocar preenche 100%, independente do volume da barra."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=500)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    ev = m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 10.0))  # so' 10 acoes de volume
    abertas = [e for e in ev if isinstance(e, PositionOpened)]
    assert len(abertas) == 1
    assert abertas[0].quantity == 500


def test_entrada_capada_por_volume_nao_preenche_sem_volume_suficiente():
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=500)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    # toca o nivel, mas so' 100 acoes negociaram nesta barra -- FOK: nao preenche.
    ev1 = m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 100.0))
    assert [e for e in ev1 if isinstance(e, PositionOpened)] == []
    assert m.position is None
    assert m.resting_limit is not None  # continua parada, esperando

    # barra seguinte com volume suficiente -- preenche de verdade.
    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.85, 9.79, 9.80, 500.0))
    abertas = [e for e in ev2 if isinstance(e, PositionOpened)]
    assert len(abertas) == 1
    assert abertas[0].quantity == 500


def test_ordem_dividida_preenche_filhos_conforme_o_volume_permite():
    """A divisao (`EnterLimit.split_quantities`) e' o que aumenta a chance
    de PELO MENOS parte da ordem casar: pedacos menores cabem no orcamento
    de volume da barra mesmo quando o total nao caberia."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      split_quantities=(100, 100, 100))]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    # toca o nivel com 250 de volume -- cabem 2 filhos de 100 (200), o 3o
    # (mais 100) nao cabe no orcamento restante (50).
    ev1 = m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 250.0))
    abertas1 = [e for e in ev1 if isinstance(e, PositionOpened)]
    assert len(abertas1) == 2
    assert m.position is not None
    assert m.position.quantity == 200
    assert m.resting_limit is not None  # ainda espera o 3o filho

    # barra seguinte com volume suficiente para o ultimo filho -- TOP-UP na
    # MESMA posicao (preco medio ponderado), nao abre uma segunda.
    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.85, 9.79, 9.80, 100.0))
    abertas2 = [e for e in ev2 if isinstance(e, PositionOpened)]
    assert len(abertas2) == 1
    assert m.position.quantity == 300
    assert m.position.entry_price == pytest.approx(9.80)
    assert m.resting_limit is None  # grupo todo preenchido


def test_grupo_dividido_orfao_e_cancelado_quando_a_posicao_fecha_por_stop():
    """Se o stop fecha a posicao ANTES de todos os filhos preencherem, o que
    sobrou do grupo tem que ser cancelado -- continuar tentando abriria uma
    posicao NOVA e desconectada da que acabou de fechar."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_stop=9.00,
                                      split_quantities=(100, 100, 100))]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 100.0))  # so' 1 filho preenche
    assert m.position.quantity == 100
    assert m.resting_limit is not None

    ev = m.on_closed_bar(_bar_vol(2, 9.85, 9.85, 8.50, 8.60, 999.0))  # despenca abaixo do stop

    canceladas = [e for e in ev if isinstance(e, LimitCancelled)]
    assert len(canceladas) == 1
    assert canceladas[0].reason == "position_closed"
    assert m.resting_limit is None
    assert m.position is None


def test_alvo_maker_capado_nao_fecha_sem_volume_suficiente_e_fecha_depois():
    """A MESMA logica de FOK vale para o ALVO quando ele e' maker
    (`target_fills_as_maker=True`) -- e' o lado que o RLP tambem nao
    alcanca. O stop continua sem cap (protecao/urgencia, ver o proximo
    teste)."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=500,
                                      initial_target=9.90)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 500.0))  # fill em 9.80
    assert m.position is not None

    # preco toca o alvo, mas so' 50 acoes negociaram -- nao fecha (FOK).
    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 50.0))
    assert [e for e in ev2 if isinstance(e, PositionClosed)] == []
    assert m.position is not None

    # barra seguinte com volume suficiente -- fecha no alvo, sem slippage.
    ev3 = m.on_closed_bar(_bar_vol(3, 9.90, 9.95, 9.85, 9.90, 500.0))
    fechadas = [e for e in ev3 if isinstance(e, PositionClosed)]
    assert len(fechadas) == 1
    assert fechadas[0].trade.exit_price == pytest.approx(9.90)
    assert fechadas[0].trade.exit_reason == IntradayExitReason.TARGET


def test_stop_nunca_e_capado_por_volume_mesmo_com_cap_ligado():
    """Saida por protecao nunca espera contraparte -- so' o alvo (saida
    'com calma') e a entrada tem cap."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=500,
                                      initial_stop=9.00)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 500.0))

    ev = m.on_closed_bar(_bar_vol(2, 9.85, 9.85, 8.50, 8.60, 1.0))  # stop, volume baixissimo

    fechadas = [e for e in ev if isinstance(e, PositionClosed)]
    assert len(fechadas) == 1
    assert fechadas[0].trade.exit_reason == IntradayExitReason.STOP


# ---------- alvo dividido em fatias (`EnterLimit.exit_split_unit`) ---------
# (2026-08-22, pedido do dono: o MESMO problema que a entrada tinha -- exigir
# o volume da posicao INTEIRA de uma vez -- tambem vale para o alvo, que so'
# fechava tudo-ou-nada. `exit_split_unit` deixa o alvo fechar fatia por
# fatia, conforme o volume de cada barra permitir.)

def test_alvo_dividido_fecha_fatias_conforme_o_volume_permite():
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_target=9.90, exit_split_unit=100)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))  # fill em 9.80
    assert m.position.quantity == 300

    # toca o alvo com 250 de volume -- cabem 2 fatias de 100 (200), a
    # 3a nao cabe no orcamento restante (50). Posicao continua aberta com
    # o RESTO (100), nao fecha tudo nem nada.
    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 250.0))
    fechadas2 = [e for e in ev2 if isinstance(e, PositionClosed)]
    assert len(fechadas2) == 1
    assert fechadas2[0].trade.quantity == 200
    assert fechadas2[0].trade.exit_price == pytest.approx(9.90)
    assert m.position is not None
    assert m.position.quantity == 100

    # barra seguinte fecha a ultima fatia -- SEGUNDO trade, so' com o resto.
    ev3 = m.on_closed_bar(_bar_vol(3, 9.90, 9.95, 9.85, 9.90, 100.0))
    fechadas3 = [e for e in ev3 if isinstance(e, PositionClosed)]
    assert len(fechadas3) == 1
    assert fechadas3[0].trade.quantity == 100
    assert m.position is None


def test_alvo_dividido_sem_volume_nenhuma_fatia_fecha():
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_target=9.90, exit_split_unit=100)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))

    # toca o alvo, mas 50 de volume nao cobre nem 1 fatia de 100.
    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 50.0))

    assert [e for e in ev2 if isinstance(e, PositionClosed)] == []
    assert m.position.quantity == 300


def test_alvo_dividido_stop_fecha_o_resto_inteiro_de_uma_vez():
    """Depois de uma fatia do alvo ja ter fechado, se o STOP dispara ele
    fecha o que SOBROU da posicao de uma vez so' -- stop nunca e' dividido,
    e' saida por protecao/urgencia."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_stop=9.00, initial_target=9.90,
                                      exit_split_unit=100)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))
    m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 100.0))  # fecha 1 fatia (100), resta 200
    assert m.position.quantity == 200

    ev = m.on_closed_bar(_bar_vol(3, 9.85, 9.85, 8.50, 8.60, 1.0))  # despenca, volume baixissimo

    fechadas = [e for e in ev if isinstance(e, PositionClosed)]
    assert len(fechadas) == 1
    assert fechadas[0].trade.quantity == 200
    assert fechadas[0].trade.exit_reason == IntradayExitReason.STOP
    assert m.position is None


def test_resume_session_ignora_seed_pending_se_ja_existe_posicao_restaurada():
    """`restore()` (ex.: apos um restart do processo) pode repor uma posicao
    REAL antes de `resume_session` rodar (ver `live/intraday_runtime.py::
    _restore`, chamado ANTES de `_start_session`) -- plantar por cima uma
    ordem recalculada pelo replay do warm start (que nunca sabe de posicao
    nenhuma, `warm_start_calibration` sempre chama com `position=None`)
    deixaria essa ordem orfa assim que a posicao restaurada fechasse.
    Achado 2026-08-22: sem este guard, um restart no meio do pregao podia
    fechar e REABRIR a posicao restaurada na mesma barra por engano."""
    strat = _Scripted({})
    m = IntradaySessionMachine(strat, _config())
    m.restore({
        "session_date": "2026-01-05", "session_pnl": 0.0, "realized_pnl": 0.0,
        "flattened": False,
        "position": {"side": "long", "entry_ts": "2026-01-05T13:01:00+00:00",
                     "entry_price": 9.80, "quantity": 100, "current_stop": 9.00,
                     "current_target": 9.90, "bars_held": 1, "metadata": {}},
    })
    assert m.position is not None

    m.resume_session(pd.Timestamp("2026-01-05").date(),
                     seed_pending=EnterLimit(side="long", limit_price=5.00))

    assert m.resting_limit is None  # a ordem recalculada NAO foi plantada
    assert m.position.entry_price == pytest.approx(9.80)  # posicao restaurada intacta
