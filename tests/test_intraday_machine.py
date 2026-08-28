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
    OrderRejected,
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


def test_rearme_no_mesmo_nivel_mantem_a_ordem_parada():
    """Rearme que recalcula EXATAMENTE o mesmo nivel NAO substitui a ordem.

    O rearme por tempo da familia `gremah` recalcula o nivel a partir da
    ancora rolante, e em ativo de centavos o arredondamento cai no mesmo
    lugar quase sempre. Ao vivo, emitir `LimitPlaced` ali viraria
    cancela+manda na corretora e a ordem voltaria para o FIM da fila do
    nivel — que e' exatamente o que impedia a PMAM3 real de preencher
    (11 substituicoes, zero fills, 2026-08-26)."""
    mesma = dict(side="long", limit_price=9.80, initial_target=9.90, initial_stop=9.00)
    strat = _Scripted({
        0: [EnterLimit(**mesma)],
        1: [EnterLimit(**mesma)],
    })
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    ev1 = m.on_closed_bar(_bar(1, 10.00, 10.05, 9.95, 10.00))

    assert [e for e in ev1 if isinstance(e, (LimitPlaced, LimitCancelled))] == []
    assert m.resting_limit is not None
    assert m.resting_limit.limit_price == pytest.approx(9.80)
    # e continua sendo uma ordem de verdade: a barra seguinte toca e preenche
    ev2 = m.on_closed_bar(_bar(2, 10.00, 10.00, 9.79, 9.85))
    assert [e.price for e in ev2 if isinstance(e, PositionOpened)] == [pytest.approx(9.80)]


def test_rearme_no_mesmo_nivel_adota_stop_e_alvo_novos():
    """Manter a ordem na fila nao e' congelar a decisao: stop, alvo e
    fatiamento de saida do objeto NOVO valem, porque nenhum deles existe na
    ordem pendente da corretora (que leva so lado/preco/quantidade)."""
    strat = _Scripted({
        0: [EnterLimit(side="long", limit_price=9.80, initial_target=9.90, initial_stop=9.00)],
        1: [EnterLimit(side="long", limit_price=9.80, initial_target=9.95, initial_stop=9.50)],
    })
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    ev1 = m.on_closed_bar(_bar(1, 10.00, 10.05, 9.95, 10.00))
    assert [e for e in ev1 if isinstance(e, (LimitPlaced, LimitCancelled))] == []

    ev2 = m.on_closed_bar(_bar(2, 10.00, 10.00, 9.79, 9.85))
    aberta = [e for e in ev2 if isinstance(e, PositionOpened)][0]
    assert aberta.target == pytest.approx(9.95)
    assert aberta.stop == pytest.approx(9.50)


def test_rearme_no_mesmo_nivel_nao_reinicia_a_espera_de_ttl():
    """A espera (`resting_limit_bars_waited`) mede uma ordem que nunca saiu
    do book. Zera-la a cada rearme faria `ttl_bars` nunca vencer para quem
    rearma no mesmo nivel — a ordem viveria para sempre."""
    mesma = dict(side="long", limit_price=9.80, ttl_bars=2)
    strat = _Scripted({0: [EnterLimit(**mesma)], 1: [EnterLimit(**mesma)],
                       2: [EnterLimit(**mesma)]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    m.on_closed_bar(_bar(1, 10.00, 10.05, 9.95, 10.00))   # espera 1
    ev2 = m.on_closed_bar(_bar(2, 10.00, 10.05, 9.95, 10.00))   # espera 2 -> vence

    cancelamentos = [e for e in ev2 if isinstance(e, LimitCancelled)]
    assert [e.reason for e in cancelamentos] == ["ttl"]


@pytest.mark.parametrize("diferente, campo", [
    (dict(side="short", limit_price=9.80), "lado"),
    (dict(side="long", limit_price=9.81), "nivel"),
    (dict(side="long", limit_price=9.80, quantity=2), "tamanho"),
])
def test_rearme_que_muda_a_ordem_na_corretora_continua_substituindo(diferente, campo):
    """A guarda so' vale para a ordem IDENTICA. Qualquer mudanca no que a
    corretora enxerga (lado, nivel ou tamanho) tem de virar cancela+manda,
    senao o robo ficaria com uma ordem que ele nao pediu mais."""
    strat = _Scripted({
        0: [EnterLimit(side="long", limit_price=9.80, quantity=1)],
        1: [EnterLimit(**diferente)],
    })
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    ev1 = m.on_closed_bar(_bar(1, 10.00, 10.05, 9.95, 10.00))

    postas = [e for e in ev1 if isinstance(e, LimitPlaced)]
    assert len(postas) == 1, campo
    assert postas[0].replaced is not None
    assert postas[0].replaced.limit_price == pytest.approx(9.80)


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
    de volume da barra mesmo quando o total nao caberia. Em modo SIMULADO
    (2026-08-24), cada filho que preenche vira uma posicao PROPRIA e
    independente -- nunca funde/tira media com uma ja aberta (pedido do
    dono, ver a docstring de `IntradaySessionMachine`)."""
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
    assert len(m.positions) == 2
    assert [p.quantity for p in m.positions] == [100, 100]
    assert m.resting_limit is not None  # ainda espera o 3o filho

    # barra seguinte com volume suficiente para o ultimo filho -- vira uma
    # TERCEIRA posicao independente, nao um top-up nas outras duas.
    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.85, 9.79, 9.80, 100.0))
    abertas2 = [e for e in ev2 if isinstance(e, PositionOpened)]
    assert len(abertas2) == 1
    assert len(m.positions) == 3
    assert [p.quantity for p in m.positions] == [100, 100, 100]
    assert all(p.entry_price == pytest.approx(9.80) for p in m.positions)
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


def test_posicoes_independentes_stop_de_uma_fecha_so_ela():
    """Pedido do dono (2026-08-24): se 2 lotes abrem 2 posicoes
    independentes, cada uma tem que ter O SEU PROPRIO stop -- o de uma nao
    pode fechar a outra junto. Simula 2 posicoes com stops DIFERENTES
    (mutando uma delas depois de aberta, como um trailing proprio faria)
    para provar que a maquina avalia e fecha cada `_Position` de forma
    independente."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=200,
                                      split_quantities=(100, 100),
                                      initial_stop=9.00, initial_target=9.90)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 200.0))  # os 2 filhos preenchem juntos
    assert len(m.positions) == 2
    assert all(p.current_stop == pytest.approx(9.00) for p in m.positions)

    # aperta o stop de SO' UMA das duas -- prova de que cada `_Position` tem
    # seu proprio campo, independente da outra.
    m.positions[0].current_stop = 9.70

    ev = m.on_closed_bar(_bar_vol(2, 9.85, 9.85, 9.60, 9.65, 999.0))  # toca 9.70 mas nao 9.00

    fechadas = [e for e in ev if isinstance(e, PositionClosed)]
    assert len(fechadas) == 1
    assert fechadas[0].trade.quantity == 100
    assert fechadas[0].trade.exit_reason == IntradayExitReason.STOP
    assert len(m.positions) == 1
    assert m.positions[0].current_stop == pytest.approx(9.00)  # a outra continua intacta
    assert m.positions[0].quantity == 100


def test_alvo_maker_capado_com_2_posicoes_nao_dobra_o_orcamento_de_volume():
    """2 posicoes independentes de 1 lote cada, ambas mirando o MESMO alvo
    maker capado por volume -- o orcamento da barra e' UNICO e
    compartilhado (2026-08-24): se so' cabe 1 fatia no volume disponivel,
    so' 1 das duas fecha nesta barra, nunca as duas (cada uma checando
    `bar.volume` por conta propria dobraria a liquidez real)."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=200,
                                      split_quantities=(100, 100), initial_target=9.90)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 200.0))
    assert len(m.positions) == 2

    # toca o alvo com volume pra fechar SO' 1 das 2 fatias de 100.
    ev = m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 100.0))

    fechadas = [e for e in ev if isinstance(e, PositionClosed)]
    assert len(fechadas) == 1
    assert fechadas[0].trade.quantity == 100
    assert len(m.positions) == 1  # a outra continua aberta, sem volume pra ela nesta barra


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


# ---------- alvo dividido com PRAZO, simulado (`EnterLimit.exit_ttl_bars`,
# 2026-08-23) -- espelha `_resolve_live_split_exit` usando `bar.volume`/
# `bar.close` no lugar da corretora, para o backtest prever o que a execucao
# REAL vai fazer (mesma razao de a maquina ser compartilhada).

def test_alvo_dividido_com_prazo_nao_preenche_na_propria_barra_que_armou():
    """MESMO atraso estrutural da execucao real: a fatia arma no primeiro
    toque, mas so' pode preencher a partir da barra SEGUINTE (mandar a ordem
    e checar o fill dela na mesma respiracao nao existe nem na corretora de
    verdade)."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_target=9.90, exit_split_unit=100,
                                      exit_ttl_bars=5)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))  # fill em 9.80
    assert m.position.quantity == 300

    # 1o toque do alvo, com volume de sobra -- arma a fatia, mas NAO preenche
    # nesta mesma barra.
    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 100.0))
    assert [e for e in ev2 if isinstance(e, PositionClosed)] == []
    assert m.position.quantity == 300
    assert m.position.resting_exit_bars_waited == 0

    # barra SEGUINTE, tambem tocando o alvo com volume suficiente -- agora sim
    # preenche a fatia.
    ev3 = m.on_closed_bar(_bar_vol(3, 9.90, 9.95, 9.85, 9.90, 100.0))
    fechadas3 = [e for e in ev3 if isinstance(e, PositionClosed)]
    assert len(fechadas3) == 1
    assert fechadas3[0].trade.quantity == 100
    assert fechadas3[0].trade.exit_price == pytest.approx(9.90)
    assert m.position is not None
    assert m.position.quantity == 200
    assert m.position.resting_exit_bars_waited == 0


def test_alvo_dividido_com_prazo_estourado_fecha_so_a_fatia_a_mercado():
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_target=9.90, exit_split_unit=100,
                                      exit_ttl_bars=2)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))

    # 1o toque -- arma a fatia (nao conta prazo ainda, so' a partir da PROXIMA
    # barra que checa o fill dela).
    m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 100.0))
    assert m.position.resting_exit_bars_waited == 0
    assert m.position.quantity == 300

    # 1a checagem: toca de novo, mas SEM volume suficiente -- 1 barra de espera.
    ev3 = m.on_closed_bar(_bar_vol(3, 9.90, 9.95, 9.85, 9.90, 10.0))
    assert [e for e in ev3 if isinstance(e, PositionClosed)] == []
    assert m.position.resting_exit_bars_waited == 1
    assert m.position.quantity == 300

    # 2a checagem, ainda sem volume: estoura o prazo (exit_ttl_bars=2) --
    # fecha a MERCADO so' a FATIA travada (100), o resto da posicao (200)
    # continua aberto (2026-08-24: antes despejava a posicao INTEIRA aqui).
    ev4 = m.on_closed_bar(_bar_vol(4, 9.90, 9.90, 9.85, 9.88, 10.0))
    fechadas4 = [e for e in ev4 if isinstance(e, PositionClosed)]
    assert len(fechadas4) == 1
    assert fechadas4[0].trade.quantity == 100
    assert fechadas4[0].trade.exit_price == pytest.approx(9.88)  # bar.close, nao o nivel do alvo
    assert fechadas4[0].trade.exit_reason == IntradayExitReason.TARGET
    assert m.position is not None
    assert m.position.quantity == 200
    assert m.position.resting_exit_bars_waited == 0
    assert m.position.exit_resting_qty == 0


def test_alvo_dividido_com_prazo_estourado_fatia_nova_arma_e_fecha_independente():
    """Depois do despejo PARCIAL (so' a fatia travada), a posicao restante
    continua com o mesmo alvo/stop -- uma nova fatia arma no proximo toque
    e tem seu PROPRIO prazo do zero, independente do que aconteceu com a
    fatia anterior."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_target=9.90, exit_split_unit=100,
                                      exit_ttl_bars=2)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))
    m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 100.0))  # arma
    m.on_closed_bar(_bar_vol(3, 9.90, 9.95, 9.85, 9.90, 10.0))  # espera, sem volume
    ev4 = m.on_closed_bar(_bar_vol(4, 9.90, 9.90, 9.85, 9.88, 10.0))  # estoura, despeja a fatia
    assert [e for e in ev4 if isinstance(e, PositionClosed)][0].trade.quantity == 100
    assert m.position.quantity == 200

    # novo toque do alvo -- arma uma fatia NOVA, prazo do zero.
    m.on_closed_bar(_bar_vol(5, 9.85, 9.95, 9.85, 9.90, 100.0))
    assert m.position.resting_exit_bars_waited == 0
    assert m.position.exit_resting_qty == 100

    ev6 = m.on_closed_bar(_bar_vol(6, 9.90, 9.95, 9.85, 9.90, 100.0))  # preenche
    fechadas6 = [e for e in ev6 if isinstance(e, PositionClosed)]
    assert len(fechadas6) == 1
    assert fechadas6[0].trade.quantity == 100
    assert m.position is not None
    assert m.position.quantity == 100


def test_alvo_dividido_com_prazo_conta_barras_mesmo_sem_tocar_o_alvo():
    """O prazo conta em TODA barra desde que a fatia armou, tocando ou nao --
    espelha a ordem real, que fica no book esperando independente do preco
    da barra seguinte ter chegado perto dela de novo."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_target=9.90, exit_split_unit=100,
                                      exit_ttl_bars=2)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))
    m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 100.0))  # arma
    assert m.position.resting_exit_bars_waited == 0

    # preco foge do alvo (nem toca) -- 1a checagem ja conta prazo mesmo assim.
    ev3 = m.on_closed_bar(_bar_vol(3, 9.85, 9.85, 9.70, 9.75, 999.0))
    assert [e for e in ev3 if isinstance(e, PositionClosed)] == []
    assert m.position.resting_exit_bars_waited == 1

    # 2a checagem sem tocar: estoura o prazo (exit_ttl_bars=2) -- fecha so' a
    # fatia (100), o resto (200) continua aberto.
    ev4 = m.on_closed_bar(_bar_vol(4, 9.75, 9.75, 9.60, 9.65, 999.0))
    fechadas4 = [e for e in ev4 if isinstance(e, PositionClosed)]
    assert len(fechadas4) == 1
    assert fechadas4[0].trade.quantity == 100
    assert fechadas4[0].trade.exit_price == pytest.approx(9.65)
    assert m.position is not None
    assert m.position.quantity == 200


def test_alvo_dividido_com_prazo_stop_fecha_tudo_e_zera_o_prazo():
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_stop=9.00, initial_target=9.90,
                                      exit_split_unit=100, exit_ttl_bars=5)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))
    m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 100.0))  # arma a fatia
    ev3 = m.on_closed_bar(_bar_vol(3, 9.90, 9.95, 9.85, 9.90, 10.0))  # checa, sem volume
    assert [e for e in ev3 if isinstance(e, PositionClosed)] == []
    assert m.position.resting_exit_bars_waited == 1

    ev = m.on_closed_bar(_bar_vol(4, 9.85, 9.85, 8.50, 8.60, 1.0))  # despenca abaixo do stop

    fechadas = [e for e in ev if isinstance(e, PositionClosed)]
    assert len(fechadas) == 1
    assert fechadas[0].trade.quantity == 300
    assert fechadas[0].trade.exit_reason == IntradayExitReason.STOP
    assert m.position is None


def test_state_restore_preserva_fatia_de_saida_posicionada_em_sombra():
    """Gap de restart no meio de uma fatia posicionada (2026-08-23): em modo
    SIMULADO (`execution is None`, backtest/sombra) nao ha' ordem real para
    perder o rastro -- restaurar `exit_resting_qty`/`resting_exit_bars_waited`
    e' o bastante para o prazo continuar contando de onde parou."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      initial_target=9.90, exit_split_unit=100,
                                      exit_ttl_bars=2)]})
    m = IntradaySessionMachine(strat, _config(limit_fill_capped_by_volume=True,
                                              target_fills_as_maker=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))
    m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 300.0))
    m.on_closed_bar(_bar_vol(2, 9.85, 9.95, 9.85, 9.90, 100.0))  # arma a fatia
    ev3 = m.on_closed_bar(_bar_vol(3, 9.90, 9.95, 9.85, 9.90, 10.0))  # 1a checagem, sem volume
    assert [e for e in ev3 if isinstance(e, PositionClosed)] == []
    assert m.position.exit_resting_qty == 100
    assert m.position.resting_exit_bars_waited == 1

    snapshot = m.state()
    outra = IntradaySessionMachine(_Scripted({}), _config(limit_fill_capped_by_volume=True,
                                                           target_fills_as_maker=True))
    outra.restore(snapshot)

    assert outra.position is not None and outra.position.quantity == 300
    assert outra.position.exit_resting_qty == 100
    assert outra.position.resting_exit_bars_waited == 1

    # so' falta 1 barra de espera (exit_ttl_bars=2, ja usou 1 antes do
    # restart) -- estoura o prazo e fecha so' a fatia a mercado (100), sem
    # reiniciar a contagem do zero.
    ev4 = outra.on_closed_bar(_bar_vol(4, 9.90, 9.90, 9.85, 9.88, 10.0))
    fechadas4 = [e for e in ev4 if isinstance(e, PositionClosed)]
    assert len(fechadas4) == 1
    assert fechadas4[0].trade.quantity == 100
    assert outra.position is not None
    assert outra.position.quantity == 200


def test_restore_com_fatia_de_saida_posicionada_em_execucao_real_falha_alto():
    """O mesmo restart em execucao REAL nao pode resumir silenciosamente: o
    ticket da ordem-limite de saida vive so' em `MT5IntradayExecution`
    (nunca persistido), entao um processo novo nao tem como saber se ela
    ainda esta viva no book. Resumir do mesmo jeito arriscaria uma SEGUNDA
    ordem de saida por cima -- falha alto em vez disso (ver `restore()`)."""
    snapshot = {
        "session_date": "2026-01-05", "session_pnl": 0.0, "realized_pnl": 0.0,
        "flattened": False,
        "position": {
            "side": "long", "entry_ts": "2026-01-05T13:01:00", "entry_price": 9.80,
            "quantity": 300, "current_stop": None, "current_target": 9.90,
            "bars_held": 3, "metadata": {}, "exit_split_unit": 100, "exit_ttl_bars": 2,
            "exit_resting_qty": 100, "exit_resting_bars_waited": 1,
        },
    }
    m = IntradaySessionMachine(_Scripted({}), _config(), execution=object())

    with pytest.raises(RuntimeError, match="FATIA DE SAIDA"):
        m.restore(snapshot)


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


# ---------- barra de pregao anterior ---------------------------------------

def test_barra_de_pregao_anterior_e_descartada_sem_achatar_a_sessao():
    """Achado 2026-08-25 (`dt-gremah-pmam3-shadow`): o feed ao vivo entrega
    tudo com `ts > last_bar_ts`, e essa marca atravessa a virada do pregao.
    Uma barra atrasada de ONTEM, dentro da janela do corte de flatten, chegou
    como PRIMEIRA barra de hoje. Como o corte compara so' a HORA
    (`ts.time() >= session_end_time_for(ts)`), ele disparou as 13:01 e
    `flattened=True` calou o robo nas 322 barras seguintes -- zero ordem no
    dia inteiro, sem erro nenhum no diario."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80,
                                      initial_target=9.90, initial_stop=9.00)]})
    m = IntradaySessionMachine(strat, _config(session_end_time=time(19, 54)))
    m.begin_session(pd.Timestamp("2026-01-05").date())

    tarde_de_ontem = Bar(ts=pd.Timestamp("2026-01-02 19:54", tz="UTC"),
                         open=10.0, high=10.0, low=10.0, close=10.0, volume=0.0)
    assert m.on_closed_bar(tarde_de_ontem) == []
    assert m.flattened is False
    # descartada de verdade: o robo nem foi consultado sobre ela
    assert strat.session_starts == 1

    # a primeira barra de HOJE decide normalmente
    ev = m.on_closed_bar(_bar(0, 10.00, 10.00, 10.00, 10.00))
    assert [type(e) for e in ev] == [LimitPlaced]


def test_is_previous_session_bar_so_olha_para_tras():
    """Barra de pregao FUTURO nao e' descartada: ao vivo ela nao existe (a
    maquina e' reaberta no pregao de hoje antes de qualquer consumo) e
    inventar comportamento para ela seria regra nova sem caso real."""
    m = IntradaySessionMachine(_Scripted({}), _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())

    assert m.is_previous_session_bar(pd.Timestamp("2026-01-02 19:54", tz="UTC")) is True
    assert m.is_previous_session_bar(pd.Timestamp("2026-01-05 13:00", tz="UTC")) is False
    assert m.is_previous_session_bar(pd.Timestamp("2026-01-06 13:00", tz="UTC")) is False


def test_sem_sessao_aberta_nenhuma_barra_e_considerada_atrasada():
    """`session_date is None` (maquina recem-construida, antes de
    `begin_session`) nao pode virar descarte silencioso de tudo."""
    m = IntradaySessionMachine(_Scripted({}), _config())
    assert m.is_previous_session_bar(pd.Timestamp("2026-01-02 19:54", tz="UTC")) is False


# ---------- teto de contratos simultaneos (max_open_contracts) -------------
# Ambiente de COMPETICAO (Copa BTG): margem simulada como infinita, sem saldo
# ficticio nenhum -- o unico limitador de tamanho e' quantos contratos ficam
# abertos ao mesmo tempo. Ver `IntradayBacktestConfig.max_open_contracts`.

def _bar_vol(minute: int, o, h, low, c, volume: float) -> Bar:
    b = _bar(minute, o, h, low, c)
    return Bar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close, volume=volume)


def test_sem_teto_declarado_o_comportamento_e_o_de_sempre():
    """`None` (default) tem de ser indistinguivel do motor antes desta
    feature -- e' o caminho que TODA acao usa."""
    strat = _Scripted({0: [Enter(side="long", quantity=500, reason="grande")]})
    m = IntradaySessionMachine(strat, _config())
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.0, 10.0, 10.0, 10.0))
    eventos = m.on_closed_bar(_bar(1, 10.0, 10.0, 10.0, 10.0))
    assert [type(e) for e in eventos] == [PositionOpened]
    assert m.open_contracts == 500
    assert m.ordens_recusadas_por_teto == 0
    assert m.ordens_aceitas == 1


def test_entrada_a_mercado_acima_do_teto_e_recusada_por_inteiro_nao_truncada():
    """Truncar para 3 esconderia, dentro de um P&L de aparencia saudavel, uma
    estrategia que so' funciona porque o motor apertou o tamanho dela em
    silencio."""
    strat = _Scripted({0: [Enter(side="long", quantity=5, reason="acima_do_teto")]})
    m = IntradaySessionMachine(strat, _config(max_open_contracts=3))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.0, 10.0, 10.0, 10.0))
    eventos = m.on_closed_bar(_bar(1, 10.0, 10.0, 10.0, 10.0))

    recusas = [e for e in eventos if isinstance(e, OrderRejected)]
    assert len(recusas) == 1
    assert recusas[0].quantity == 5 and recusas[0].cap == 3
    assert recusas[0].open_contracts == 0
    assert recusas[0].reason == "max_open_contracts"
    assert not [e for e in eventos if isinstance(e, PositionOpened)]
    assert m.open_contracts == 0            # nenhum contrato entrou, nem 3
    assert m.ordens_recusadas_por_teto == 1
    assert m.ordens_aceitas == 0


def test_entrada_a_mercado_exatamente_no_teto_passa():
    strat = _Scripted({0: [Enter(side="long", quantity=3, reason="no_teto")]})
    m = IntradaySessionMachine(strat, _config(max_open_contracts=3))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.0, 10.0, 10.0, 10.0))
    eventos = m.on_closed_bar(_bar(1, 10.0, 10.0, 10.0, 10.0))
    assert [type(e) for e in eventos] == [PositionOpened]
    assert m.open_contracts == 3
    assert m.ordens_recusadas_por_teto == 0


def test_filho_de_ordem_dividida_que_estoura_o_teto_e_recusado_e_descartado():
    """3 filhos de 1 contrato com teto 2: dois entram, o terceiro e' recusado
    E DESCARTADO. Deixa-lo parado o faria ser re-tentado a cada barra,
    inflando o contador com a MESMA ordem em vez de medir quantas ordens
    distintas o teto barrou."""
    ordem = EnterLimit(side="long", limit_price=9.80, initial_stop=9.00,
                       initial_target=99.0, quantity=3, split_quantities=(1, 1, 1),
                       reason="dividida")
    strat = _Scripted({0: [ordem]})
    m = IntradaySessionMachine(strat, _config(max_open_contracts=2,
                                              limit_fill_capped_by_volume=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.0, 10.0, 10.0, 10.0, volume=1_000.0))
    eventos = m.on_closed_bar(_bar_vol(1, 10.0, 10.0, 9.50, 9.90, volume=1_000.0))

    abertas = [e for e in eventos if isinstance(e, PositionOpened)]
    recusas = [e for e in eventos if isinstance(e, OrderRejected)]
    assert len(abertas) == 2 and len(recusas) == 1
    assert recusas[0].order_kind == "limit" and recusas[0].open_contracts == 2
    assert m.open_contracts == 2
    assert m.ordens_aceitas == 2 and m.ordens_recusadas_por_teto == 1

    # o filho recusado nao volta a ser tentado na barra seguinte
    eventos2 = m.on_closed_bar(_bar_vol(2, 9.90, 10.0, 9.50, 9.90, volume=1_000.0))
    assert not [e for e in eventos2 if isinstance(e, OrderRejected)]
    assert m.ordens_recusadas_por_teto == 1


def test_teto_libera_de_novo_quando_a_posicao_fecha():
    """O teto e' de contratos SIMULTANEOS, nao um orcamento do pregao: fechar
    devolve a vaga."""
    strat = _Scripted({0: [Enter(side="long", quantity=2, reason="entra")],
                       2: [Exit(reason="sai")]})
    m = IntradaySessionMachine(strat, _config(max_open_contracts=2))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.0, 10.0, 10.0, 10.0))
    m.on_closed_bar(_bar(1, 10.0, 10.0, 10.0, 10.0))
    assert m.open_contracts == 2
    m.on_closed_bar(_bar(2, 10.0, 10.0, 10.0, 10.0))
    m.on_closed_bar(_bar(3, 10.0, 10.0, 10.0, 10.0))
    assert m.open_contracts == 0


# ---------- teto de contratos por CAPITAL (2026-08-28, incidente REAL) -----
# `wdo_grid_reload_maker` (WDO@, capital real R$300) zerou a conta ao vivo:
# duas entradas INDEPENDENTES do grid (mesmo magic, 5s de diferenca) abriram
# 2 contratos simultaneos numa conta NETTING que so' tinha margem para 1. O
# UNICO teto agregado que a config real carregava era `max_open_contracts=5`
# (o numero REGULATORIO da Copa BTG) -- sem nenhuma relacao com o caixa real.
# `IntradayBacktestConfig.margin_per_contract_brl` fecha esse buraco: um teto
# recalculado a CADA checagem contra `initial_capital + realized_pnl`, com a
# reserva de `strategy.daytrade.base.RESERVA_CAIXA_SEGURANCA` ja aplicada
# (`contracts_from_capital_com_reserva`). Ver tambem
# `tests/test_daytrade_base.py::test_reserva_reproduz_exatamente_o_
# incidente_wdo_r300` para o numero cru da formula.

def test_sem_margin_per_contract_brl_o_teto_por_capital_nao_existe():
    """`None` (default) tem de ser indistinguivel do motor antes desta
    feature -- caixa minusculo nao bloqueia NADA sem o campo setado (so'
    `max_open_contracts`, se algum, continua valendo)."""
    strat = _Scripted({0: [Enter(side="long", quantity=500, reason="grande")]})
    m = IntradaySessionMachine(strat, _config(initial_capital=1.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.0, 10.0, 10.0, 10.0))
    eventos = m.on_closed_bar(_bar(1, 10.0, 10.0, 10.0, 10.0))
    assert [type(e) for e in eventos] == [PositionOpened]
    assert m.open_contracts == 500
    assert m.ordens_recusadas_por_capital == 0


def test_reproduz_o_incidente_segundo_filho_independente_e_recusado_por_capital():
    """Reproducao direta do incidente: uma ordem-limite dividida em 2 filhos
    de 1 contrato cada (`EnterLimit.split_quantities`, o mesmo mecanismo de
    'posicoes independentes por lote' que abriu os 2 deals reais) contra um
    caixa que so' sustenta 1 contrato COM a reserva (R$400, margem R$150,
    buffer 2.0 x reserva 1.25 = 375/contrato -> 1 contrato). O PRIMEIRO filho
    abre posicao; o SEGUNDO e' RECUSADO por capital -- nunca vira uma segunda
    posicao real, ao contrario do que aconteceu ao vivo em 2026-08-28."""
    ordem = EnterLimit(side="long", limit_price=9.80, initial_stop=9.00,
                       initial_target=99.0, quantity=2, split_quantities=(1, 1),
                       reason="grid_dividido")
    strat = _Scripted({0: [ordem]})
    m = IntradaySessionMachine(strat, _config(
        initial_capital=400.0, margin_per_contract_brl=150.0,
        limit_fill_capped_by_volume=True,
    ))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.0, 10.0, 10.0, 10.0, volume=1_000.0))
    eventos = m.on_closed_bar(_bar_vol(1, 10.0, 10.0, 9.50, 9.90, volume=1_000.0))

    abertas = [e for e in eventos if isinstance(e, PositionOpened)]
    recusas = [e for e in eventos if isinstance(e, OrderRejected)]
    assert len(abertas) == 1 and len(recusas) == 1
    assert recusas[0].reason == "capital_insuficiente"
    assert recusas[0].order_kind == "limit"
    assert recusas[0].cap == 1
    assert m.open_contracts == 1  # NUNCA 2 -- exatamente o que faltou no incidente real
    assert m.ordens_recusadas_por_capital == 1
    assert m.ordens_recusadas_por_teto == 0  # causa diferente, contador diferente

    # o filho recusado nao volta a ser tentado na barra seguinte (mesmo
    # comportamento do teto estatico, ver `test_filho_de_ordem_dividida_que_
    # estoura_o_teto_e_recusado_e_descartado`).
    eventos2 = m.on_closed_bar(_bar_vol(2, 9.90, 10.0, 9.50, 9.90, volume=1_000.0))
    assert not [e for e in eventos2 if isinstance(e, OrderRejected)]
    assert m.ordens_recusadas_por_capital == 1


def test_entrada_a_mercado_acima_do_capital_e_recusada_por_capital():
    """Mesma garantia do teste acima, pelo caminho de `Enter` a mercado
    (`_entrar_a_mercado`) em vez de `EnterLimit` dividida -- o teto por
    capital vale para QUALQUER caminho de abertura, nao so' o do grid."""
    strat = _Scripted({0: [Enter(side="long", quantity=3, reason="grande_demais")]})
    m = IntradaySessionMachine(strat, _config(initial_capital=400.0, margin_per_contract_brl=150.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.0, 10.0, 10.0, 10.0))
    eventos = m.on_closed_bar(_bar(1, 10.0, 10.0, 10.0, 10.0))

    recusas = [e for e in eventos if isinstance(e, OrderRejected)]
    assert len(recusas) == 1
    assert recusas[0].reason == "capital_insuficiente"
    assert recusas[0].quantity == 3 and recusas[0].cap == 1
    assert m.open_contracts == 0
    assert m.ordens_recusadas_por_capital == 1


def test_capital_e_teto_estatico_juntos_usa_o_menor_dos_dois():
    """`max_open_contracts` (regulatorio, ex.: 5 no WDO@) e `margin_per_
    contract_brl` (caixa real) podem coexistir -- o efetivo e' sempre o
    MENOR dos dois, nunca so' um. Aqui o teto por capital (1, caixa R$400)
    e' o mais apertado; num caixa gigante o teto ESTATICO (regulatorio)
    voltaria a ser o mais apertado (ja coberto por `test_config_for_teto_
    por_capital_nunca_passa_do_teto_oficial_do_perfil` no nivel de
    `config_for`)."""
    strat = _Scripted({0: [Enter(side="long", quantity=2, reason="entra")]})
    m = IntradaySessionMachine(strat, _config(
        initial_capital=400.0, margin_per_contract_brl=150.0, max_open_contracts=5,
    ))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.0, 10.0, 10.0, 10.0))
    eventos = m.on_closed_bar(_bar(1, 10.0, 10.0, 10.0, 10.0))

    recusas = [e for e in eventos if isinstance(e, OrderRejected)]
    assert len(recusas) == 1
    assert recusas[0].reason == "capital_insuficiente"  # o teto de 5 nunca chega a amarrar
    assert recusas[0].cap == 1


def test_cap_por_capital_e_recalculado_a_cada_checagem_nao_e_uma_foto():
    """Diferente da abordagem estatica anterior (`config_for(cash_brl=...,
    margin_per_contract_brl=...)`, uma foto tirada 1x), o teto por capital do
    MOTOR reage ao `realized_pnl` -- um lucro fechado que aumenta o caixa
    libera espaco para MAIS contratos na proxima checagem, dentro da MESMA
    run, sem precisar reconstruir a config."""
    strat = _Scripted({
        0: [Enter(side="long", quantity=1, reason="entra_1")],
        2: [Exit(reason="realiza_lucro")],
        4: [Enter(side="long", quantity=2, reason="entra_2_maior")],
    })
    # R$400 sustenta 1 contrato (com reserva); apos realizar um lucro grande
    # o caixa cresce o bastante para sustentar 2.
    m = IntradaySessionMachine(strat, _config(initial_capital=400.0, margin_per_contract_brl=150.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.0, 10.0, 10.0, 10.0))
    m.on_closed_bar(_bar(1, 10.0, 10.0, 10.0, 10.0))       # abre 1 contrato @ 10.0
    assert m.open_contracts == 1
    m.on_closed_bar(_bar(2, 10.0, 10.0, 10.0, 10.0))
    m.on_closed_bar(_bar(3, 1_000.0, 1_000.0, 1_000.0, 1_000.0))  # fecha com lucro enorme @ 1000.0
    assert m.open_contracts == 0
    # lucro de (1000-10) x 1 contrato = 990 -- caixa novo (400+990=1390) sustenta
    # 3 contratos com a reserva (1390 / (150 x 2.5) = 3.7 -> 3), bem alem do
    # que os R$400 originais sustentavam (1).
    assert m.realized_pnl > 350.0  # 350 e' o minimo para o 2o contrato virar possivel

    m.on_closed_bar(_bar(4, 10.0, 10.0, 10.0, 10.0))
    eventos = m.on_closed_bar(_bar(5, 10.0, 10.0, 10.0, 10.0))  # pede 2 contratos agora
    assert [type(e) for e in eventos] == [PositionOpened]
    assert m.open_contracts == 2  # o caixa novo sustenta -- nao ficou preso no numero antigo
    assert m.ordens_recusadas_por_capital == 0


# ---------- modelo de fila (Q_frente) no preenchimento ---------------------
# `IntradayBacktestConfig.queue_ahead_qty` (2026-08-27, Fase A do modelo de
# fila -- ver a docstring do campo em `machine.py`). Cobre as quatro
# garantias pedidas: fila zerada reproduz o toque-preenche-tudo de sempre;
# Q_frente grande nunca preenche; rearme que MUDA de nivel reseta o
# acumulado (perdeu a fila de verdade); rearme no MESMO nivel (guarda
# `_reancoragem_no_mesmo_nivel`, commit `672bd5e`) NAO reseta.

def test_queue_ahead_qty_zero_reproduz_o_toque_preenche_tudo():
    """Default (`queue_ahead_qty=0.0`, e passado explicito aqui): NENHUMA
    mudanca de comportamento -- toca, preenche por inteiro, mesma barra,
    mesmo com volume irrisorio (a fila esta' desligada, entao nem existe)."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300)]})
    m = IntradaySessionMachine(strat, _config(queue_ahead_qty=0.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    ev = m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 1.0))  # so' 1 acao negociou
    abertas = [e for e in ev if isinstance(e, PositionOpened)]
    assert len(abertas) == 1
    assert abertas[0].quantity == 300


def test_fila_grande_nunca_preenche_mesmo_tocando_varias_vezes():
    """Q_frente maior que TODO volume negociado no nivel em 20 barras: a
    ordem nunca chega na frente da fila -- nunca preenche, nao importa
    quantas barras toquem."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=100)]})
    m = IntradaySessionMachine(strat, _config(queue_ahead_qty=1_000_000.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    for minuto in range(1, 21):
        ev = m.on_closed_bar(_bar_vol(minuto, 9.80, 9.80, 9.80, 9.80, 500.0))  # toca toda barra
        assert [e for e in ev if isinstance(e, PositionOpened)] == []
    assert m.position is None
    assert m.resting_limit is not None  # ainda parada, esperando a fila zerar


def test_fila_consome_volume_e_preenche_o_excedente_depois_de_zerar():
    """Q_frente=200: a primeira barra que toca so' tem 150 de volume -- vai
    tudo para a fila, nada sobra, nao preenche. A segunda tem 100: 50 zeram
    a fila e o resto do orcamento preenche a ordem inteira (sem cap por
    volume -- MESMA logica otimista de sempre, so' que depois de pagar o
    pedagio da fila, nao antes)."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300)]})
    m = IntradaySessionMachine(strat, _config(queue_ahead_qty=200.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    ev1 = m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 150.0))
    assert [e for e in ev1 if isinstance(e, PositionOpened)] == []
    assert m.resting_limit is not None

    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.85, 9.79, 9.80, 100.0))
    abertas = [e for e in ev2 if isinstance(e, PositionOpened)]
    assert len(abertas) == 1
    assert abertas[0].quantity == 300
    assert abertas[0].price == pytest.approx(9.80)


def test_fila_com_cap_por_volume_preenche_so_o_excedente_por_filho():
    """Q_frente=200 + `limit_fill_capped_by_volume=True` + ordem dividida em
    filhos de 100: a barra que zera a fila com 250 de volume so' tem 50 de
    excedente -- nenhum filho de 100 cabe (FOK por pedaco, mesma regra de
    sempre). A barra seguinte, com a fila JA zerada, usa o orcamento por
    inteiro e cabe 1 filho."""
    strat = _Scripted({0: [EnterLimit(side="long", limit_price=9.80, quantity=300,
                                      split_quantities=(100, 100, 100))]})
    m = IntradaySessionMachine(
        strat, _config(queue_ahead_qty=200.0, limit_fill_capped_by_volume=True))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    ev1 = m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 250.0))
    assert [e for e in ev1 if isinstance(e, PositionOpened)] == []
    assert m.resting_limit is not None

    ev2 = m.on_closed_bar(_bar_vol(2, 9.85, 9.85, 9.79, 9.80, 100.0))
    abertas2 = [e for e in ev2 if isinstance(e, PositionOpened)]
    assert len(abertas2) == 1
    assert abertas2[0].quantity == 100


def test_rearme_no_mesmo_nivel_nao_reseta_a_fila_ja_cortada():
    """Rearme que recalcula o MESMO nivel (guarda `_reancoragem_no_mesmo_
    nivel`, commit `672bd5e`) NAO devolve a ordem para o fim da fila: o
    volume ja cortado antes desta decisao continua contando."""
    mesma = dict(side="long", limit_price=9.80, quantity=300)
    strat = _Scripted({
        0: [EnterLimit(**mesma)],
        2: [EnterLimit(**mesma)],  # rearme no MESMO nivel, decidido na barra 2
    })
    m = IntradaySessionMachine(strat, _config(queue_ahead_qty=200.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    # corta 150 dos 200 -- sobram 50, nao preenche.
    ev1 = m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 150.0))
    assert [e for e in ev1 if isinstance(e, PositionOpened)] == []

    # rearme no MESMO nivel: nem LimitPlaced nem LimitCancelled saem (guarda
    # ativa), e esta barra nao tem volume nenhum tocando o nivel.
    ev2 = m.on_closed_bar(_bar_vol(2, 10.00, 10.05, 9.95, 10.00, 0.0))
    assert [e for e in ev2 if isinstance(e, (LimitPlaced, LimitCancelled))] == []
    assert [e for e in ev2 if isinstance(e, PositionOpened)] == []

    # so' faltam 50 para zerar a fila -- 50 de volume bastam, PROVANDO que os
    # 150 ja cortados na barra 1 nao foram perdidos no rearme da barra 2.
    ev3 = m.on_closed_bar(_bar_vol(3, 10.00, 10.00, 9.79, 9.80, 50.0))
    abertas = [e for e in ev3 if isinstance(e, PositionOpened)]
    assert len(abertas) == 1
    assert abertas[0].quantity == 300


def test_rearme_que_muda_de_nivel_reseta_a_fila():
    """O oposto do teste acima: um rearme que troca de NIVEL de verdade
    (cancela+manda de verdade na corretora) perde a fila -- volta para
    `queue_ahead_qty` inteiro no nivel novo."""
    strat = _Scripted({
        0: [EnterLimit(side="long", limit_price=9.80, quantity=300)],
        2: [EnterLimit(side="long", limit_price=9.70, quantity=300)],  # nivel NOVO
    })
    m = IntradaySessionMachine(strat, _config(queue_ahead_qty=200.0))
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar_vol(0, 10.00, 10.00, 10.00, 10.00, 0.0))

    # corta 150 da fila do nivel 9.80 (sobram 50) -- nao preenche.
    ev1 = m.on_closed_bar(_bar_vol(1, 10.00, 10.00, 9.79, 9.85, 150.0))
    assert [e for e in ev1 if isinstance(e, PositionOpened)] == []

    # barra 2: rearma num nivel DIFERENTE -- cancela+manda de verdade
    # (LimitPlaced com `replaced` setado, nao a guarda do mesmo nivel).
    ev2 = m.on_closed_bar(_bar_vol(2, 10.00, 10.05, 9.95, 10.00, 0.0))
    postas = [e for e in ev2 if isinstance(e, LimitPlaced)]
    assert len(postas) == 1
    assert postas[0].replaced is not None

    # se a fila NAO tivesse resetado, so' faltariam 50 dos 200 originais e
    # este volume bastaria. Com o reset, 50 nao e' suficiente -- prova que
    # o nivel novo comecou do zero.
    ev3 = m.on_closed_bar(_bar_vol(3, 9.70, 9.70, 9.69, 9.70, 50.0))
    assert [e for e in ev3 if isinstance(e, PositionOpened)] == []
    assert m.resting_limit is not None

    # completando os 200 do nivel novo (150 aqui, ja tinha cortado 50 acima)
    # preenche por inteiro no NIVEL NOVO.
    ev4 = m.on_closed_bar(_bar_vol(4, 9.70, 9.70, 9.69, 9.70, 150.0))
    abertas = [e for e in ev4 if isinstance(e, PositionOpened)]
    assert len(abertas) == 1
    assert abertas[0].quantity == 300
    assert abertas[0].price == pytest.approx(9.70)
