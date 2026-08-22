"""Teste do wrapper `InvertedStrategy` com cenario sintetico (AGENTS.md: toda
regra de entrada/saida em `strategy/` -> teste com cenario sintetico)."""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.daytrade.base import Bar, Enter, Exit, IntradayOpenPosition, IntradayStrategy
from strategy.daytrade.inverted import InvertedStrategy


def _bar(ts):
    return Bar(ts=ts, open=100, high=101, low=99, close=100, volume=10)


class _FakeInner(IntradayStrategy):
    name = "fake_inner"
    version = "1.0"
    symbol = "PMAM3"

    def __init__(self):
        self.seen_positions: list[IntradayOpenPosition | None] = []
        self.calls = 0

    def initialize(self, bars):
        self.initialized_with = bars

    def on_bar(self, ts, bar, position, session_pnl_brl):
        self.seen_positions.append(position)
        self.calls += 1
        if self.calls == 1:
            return [Enter(side="long", initial_stop=90.0, initial_target=110.0, reason="fake_entry")]
        return [Exit(reason="fake_exit")]


def test_enter_e_invertido_com_stop_e_target_trocados():
    inner = _FakeInner()
    strat = InvertedStrategy(inner)
    ts = pd.Timestamp("2026-01-05 09:00", tz="UTC")

    actions = strat.on_bar(ts, _bar(ts), position=None, session_pnl_brl=0.0)

    assert len(actions) == 1
    enter = actions[0]
    assert enter.side == "short"
    assert enter.initial_stop == 110.0
    assert enter.initial_target == 90.0
    assert enter.reason == "inverted:fake_entry"


def test_exit_passa_direto_sem_alteracao():
    inner = _FakeInner()
    strat = InvertedStrategy(inner)
    ts = pd.Timestamp("2026-01-05 09:00", tz="UTC")
    strat.on_bar(ts, _bar(ts), position=None, session_pnl_brl=0.0)  # consome a 1a chamada (Enter)

    actions = strat.on_bar(ts, _bar(ts), position=None, session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], Exit)
    assert actions[0].reason == "fake_exit"


def test_posicao_sombra_espelha_lado_e_stop_target_para_o_inner():
    inner = _FakeInner()
    strat = InvertedStrategy(inner)
    ts = pd.Timestamp("2026-01-05 09:00", tz="UTC")

    real_position = IntradayOpenPosition(
        side="short", entry_ts=ts, entry_price=100.0, quantity=100,
        current_stop=110.0, current_target=90.0, bars_held=3,
    )
    strat.on_bar(ts, _bar(ts), position=real_position, session_pnl_brl=0.0)

    shadow = inner.seen_positions[0]
    assert shadow.side == "long"
    assert shadow.current_stop == 90.0
    assert shadow.current_target == 110.0


def test_nome_e_prefixado_e_symbol_herdado():
    inner = _FakeInner()
    strat = InvertedStrategy(inner)
    assert strat.name == "inverted_fake_inner"
    assert strat.symbol == "PMAM3"
