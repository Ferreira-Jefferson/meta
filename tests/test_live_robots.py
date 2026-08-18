"""Testes do adaptador ao vivo (`live/robots.py`).

Usa uma `Strategy` sintetica (devolve uma lista fixa de acoes por chamada) e
uma `AccountState` montada a mao — sem depender de dado real de mercado. O
que se cobre aqui e SO a traducao Action/float -> Intent; a decisao em si e
testada em `tests/test_withdrawal.py` (politica) e nos testes de cada
estrategia (nao aqui).
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from backtest.withdrawal import FloorSkim, official_policy
from core.live_models import (
    AccountState,
    Intent,
    IntentKind,
    LivePosition,
    Quote,
    RobotContext,
    RobotRole,
)
from core.models import ExitReason
from live.robots import InvestmentRobot, LiveRobot, WithdrawalRobot, build_robots
from strategy.base import Action, AdjustStop, Enter, Exit, Strategy


# ---------- fixtures / helpers ---------------------------------------------

class _ScriptedStrategy(Strategy):
    """Estrategia sintetica: devolve uma lista fixa de acoes por chamada de
    `on_bar`, gravando os argumentos recebidos para o teste inspecionar."""

    name = "scripted"
    version = "1"

    def __init__(self, actions_by_call: list[list[Action]]):
        self._actions_by_call = list(actions_by_call)
        self.calls: list[tuple] = []
        self.initialized_with: tuple | None = None

    def initialize(self, panels, ibov) -> None:
        self.initialized_with = (panels, ibov)

    def on_bar(self, date, open_positions, cash_available):
        self.calls.append((date, dict(open_positions), cash_available))
        if self._actions_by_call:
            return self._actions_by_call.pop(0)
        return []


def _account(cash: float = 100_000.0, positions: dict | None = None) -> AccountState:
    return AccountState(
        name="conta-teste", mode="paper", initial_capital=100_000.0,
        cash=cash, positions=positions or {},
    )


def _ctx(
    session: date,
    positions: dict | None = None,
    cash: float = 100_000.0,
    marks: dict | None = None,
    quotes: dict | None = None,
) -> RobotContext:
    return RobotContext(
        session=session, panels={}, ibov=None,
        account=_account(cash=cash, positions=positions),
        marks=marks or {}, quotes=quotes or {},
    )


def _pos(ticker="PETR4", current_stop=None, kind="main", bars_held=0) -> LivePosition:
    return LivePosition(
        ticker=ticker, quantity=100, entry_date=date(2026, 1, 2), entry_price=30.0,
        capital_allocated=3_000.0, current_stop=current_stop, kind=kind,
        bars_held=bars_held,
    )


# ---------- InvestmentRobot: traducao de acoes ------------------------------

def test_prepare_delega_para_strategy_initialize():
    strat = _ScriptedStrategy([])
    robot = InvestmentRobot(strat)
    panels = {"PETR4": pd.DataFrame()}
    ibov = pd.DataFrame()
    robot.prepare(panels, ibov)
    assert strat.initialized_with == (panels, ibov)


def test_key_e_role_do_investment_robot():
    robot = InvestmentRobot(_ScriptedStrategy([]))
    assert robot.key == "scripted"
    assert robot.role == RobotRole.INVESTMENT


def test_enter_vira_intent_com_execute_on_correto():
    strat = _ScriptedStrategy([[Enter(ticker="PETR4", initial_stop=27.0, size_hint=0.5)]])
    robot = InvestmentRobot(strat)
    ctx = _ctx(session=date(2026, 8, 17))

    intents = robot.on_close(ctx, execute_on=date(2026, 8, 18))

    assert len(intents) == 1
    it = intents[0]
    assert it.kind == IntentKind.ENTER
    assert it.ticker == "PETR4"
    assert it.size_hint == pytest.approx(0.5)
    assert it.stop_price == pytest.approx(27.0)
    assert it.decided_on == date(2026, 8, 17)
    assert it.execute_on == date(2026, 8, 18)
    assert it.is_immediate is False


def test_exit_vira_intent_com_reason_e_execute_on_d_mais_1():
    strat = _ScriptedStrategy([[Exit(ticker="VALE3", reason=ExitReason.ROTATION_OUT)]])
    robot = InvestmentRobot(strat)
    ctx = _ctx(session=date(2026, 8, 17))

    intents = robot.on_close(ctx, execute_on=date(2026, 8, 18))

    assert len(intents) == 1
    it = intents[0]
    assert it.kind == IntentKind.EXIT
    assert it.ticker == "VALE3"
    assert it.reason == ExitReason.ROTATION_OUT.value
    assert it.execute_on == date(2026, 8, 18)
    assert it.is_immediate is False


def test_adjust_stop_e_imediato_execute_on_e_a_propria_sessao():
    strat = _ScriptedStrategy([[AdjustStop(ticker="WEGE3", new_stop=42.0)]])
    robot = InvestmentRobot(strat)
    ctx = _ctx(session=date(2026, 8, 17))

    intents = robot.on_close(ctx, execute_on=date(2026, 8, 20))

    assert len(intents) == 1
    it = intents[0]
    assert it.kind == IntentKind.ADJUST_STOP
    assert it.ticker == "WEGE3"
    assert it.stop_price == pytest.approx(42.0)
    assert it.execute_on == ctx.session   # nao espera D+1, custo zero
    assert it.is_immediate is True


def test_on_close_so_repassa_posicao_principal_para_a_strategy():
    """Robo oficial roda com satellite_pct=0.00: satelite nunca deveria existir
    na operacao ao vivo, mas o filtro fica explicito para o dia em que existir."""
    strat = _ScriptedStrategy([[]])
    robot = InvestmentRobot(strat)
    positions = {
        "PETR4": _pos(ticker="PETR4", current_stop=28.0, kind="main", bars_held=5),
        "VALE3": _pos(ticker="VALE3", current_stop=55.0, kind="satellite"),
    }
    ctx = _ctx(session=date(2026, 8, 17), positions=positions)

    robot.on_close(ctx, execute_on=date(2026, 8, 18))

    seen = strat.calls[0][1]
    assert set(seen.keys()) == {"PETR4"}
    assert seen["PETR4"].current_stop == pytest.approx(28.0)
    assert seen["PETR4"].bars_held == 5


# ---------- InvestmentRobot: stop intra-dia ---------------------------------

def test_on_intraday_nao_dispara_enquanto_preco_nao_cruza_o_stop():
    robot = InvestmentRobot(_ScriptedStrategy([]))
    positions = {"PETR4": _pos(current_stop=28.0)}
    quotes = {"PETR4": Quote(ticker="PETR4", price=28.5, ts=datetime(2026, 8, 17, 11, 0), source="test")}
    ctx = _ctx(session=date(2026, 8, 17), positions=positions, quotes=quotes)

    assert robot.on_intraday(ctx) == []


def test_on_intraday_dispara_stop_quando_preco_cruza():
    robot = InvestmentRobot(_ScriptedStrategy([]))
    positions = {"PETR4": _pos(current_stop=28.0)}
    quotes = {"PETR4": Quote(ticker="PETR4", price=27.9, ts=datetime(2026, 8, 17, 11, 0), source="test")}
    ctx = _ctx(session=date(2026, 8, 17), positions=positions, quotes=quotes)

    intents = robot.on_intraday(ctx)

    assert len(intents) == 1
    it = intents[0]
    assert it.kind == IntentKind.EXIT
    assert it.ticker == "PETR4"
    assert it.reason == "stop"
    assert it.execute_on == ctx.session
    assert it.is_immediate is True


def test_on_intraday_ignora_posicao_sem_stop_e_sem_cotacao():
    robot = InvestmentRobot(_ScriptedStrategy([]))
    positions = {
        "PETR4": _pos(ticker="PETR4", current_stop=None),   # sem stop
        "VALE3": _pos(ticker="VALE3", current_stop=50.0),   # sem cotacao no ctx
    }
    ctx = _ctx(session=date(2026, 8, 17), positions=positions, quotes={})

    assert robot.on_intraday(ctx) == []


# ---------- WithdrawalRobot --------------------------------------------------

def test_key_e_role_do_withdrawal_robot():
    policy = FloorSkim(pct=0.01, floor=40_000.0, day=1, min_amount=0.0)
    robot = WithdrawalRobot(policy)
    assert robot.key == f"withdrawal:{policy.label}"
    assert robot.role == RobotRole.WITHDRAWAL


def test_withdrawal_robot_emite_intent_com_o_valor_da_politica():
    policy = FloorSkim(pct=0.01, floor=40_000.0, day=1, min_amount=0.0)
    robot = WithdrawalRobot(policy)
    ctx = _ctx(session=date(2010, 1, 4), cash=100_000.0)

    intents = robot.on_close(ctx, execute_on=date(2010, 1, 5))

    assert len(intents) == 1
    it = intents[0]
    assert it.kind == IntentKind.WITHDRAW
    assert it.amount == pytest.approx(1_000.0)
    assert it.reason == policy.label
    assert it.execute_on == date(2010, 1, 5)
    assert it.decided_on == date(2010, 1, 4)


def test_withdrawal_robot_nao_emite_nada_quando_politica_devolve_zero():
    policy = FloorSkim(pct=0.01, floor=40_000.0, day=1, min_amount=0.0)
    robot = WithdrawalRobot(policy)
    ctx = _ctx(session=date(2010, 1, 4), cash=39_999.0)   # abaixo do piso

    assert robot.on_close(ctx, execute_on=date(2010, 1, 5)) == []


def test_on_liquidity_emite_intent_na_mesma_sessao():
    policy = FloorSkim(pct=0.01, floor=40_000.0, day=3, min_amount=0.0)
    robot = WithdrawalRobot(policy)
    ctx = _ctx(session=date(2010, 1, 4), cash=100_000.0)

    intents = robot.on_liquidity(ctx, reason="rotation_out")

    assert len(intents) == 1
    it = intents[0]
    assert it.kind == IntentKind.WITHDRAW
    assert it.amount == pytest.approx(1_000.0)
    assert it.execute_on == ctx.session   # caixa ja esta na mao, nao espera D+1
    assert it.decided_on == ctx.session


def test_on_executed_chega_na_politica():
    policy = FloorSkim(pct=0.01, floor=40_000.0, day=1, min_amount=1_000.0)
    robot = WithdrawalRobot(policy)
    ctx = _ctx(session=date(2010, 1, 4), cash=140_000.0)

    intents = robot.on_close(ctx, execute_on=date(2010, 1, 5))
    pedido = intents[0].amount   # 1.400 (1% de 140k)
    robot.on_executed(intents[0], 1_000.0)   # saiu menos do que o pedido

    assert policy._pool == pytest.approx(pedido - 1_000.0)


def test_state_restore_do_robot_delegam_para_a_politica():
    policy = FloorSkim(pct=0.01, floor=40_000.0, day=3, min_amount=0.0)
    robot = WithdrawalRobot(policy)
    ctx = _ctx(session=date(2010, 1, 4), cash=100_000.0)
    robot.on_close(ctx, execute_on=date(2010, 1, 5))

    snapshot = robot.state()
    assert snapshot == policy.state()

    fresh_policy = FloorSkim(pct=0.01, floor=40_000.0, day=3, min_amount=0.0)
    fresh_robot = WithdrawalRobot(fresh_policy)
    fresh_robot.restore(snapshot)

    assert fresh_policy._month == policy._month
    assert fresh_policy._sessions == policy._sessions


def test_official_policy_via_withdrawal_robot_paga_no_terceiro_pregao():
    """`official_policy()` com equity acima do piso de 55k."""
    policy = official_policy(initial_capital=1_000.0)
    robot = WithdrawalRobot(policy)

    robot.on_close(_ctx(session=date(2026, 8, 3), cash=100_000.0), execute_on=date(2026, 8, 4))
    robot.on_close(_ctx(session=date(2026, 8, 4), cash=100_000.0), execute_on=date(2026, 8, 5))
    intents = robot.on_close(_ctx(session=date(2026, 8, 5), cash=100_000.0), execute_on=date(2026, 8, 6))

    assert len(intents) == 1
    assert intents[0].amount > 0.0
    assert intents[0].reason == policy.label


# ---------- build_robots -----------------------------------------------------

def test_build_robots_monta_um_robo_por_papel():
    strat = _ScriptedStrategy([])
    policy = FloorSkim(pct=0.01, floor=40_000.0)

    robots = build_robots(strat, policy)

    assert set(robots.keys()) == {RobotRole.INVESTMENT, RobotRole.WITHDRAWAL}
    assert isinstance(robots[RobotRole.INVESTMENT], InvestmentRobot)
    assert isinstance(robots[RobotRole.WITHDRAWAL], WithdrawalRobot)
    assert robots[RobotRole.INVESTMENT].key == "scripted"
    assert robots[RobotRole.WITHDRAWAL].key == f"withdrawal:{policy.label}"


def test_live_robot_e_abstrata():
    with pytest.raises(TypeError):
        LiveRobot()
