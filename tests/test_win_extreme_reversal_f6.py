"""Teste da hipotese win_extreme_reversal_f6 com cenario sintetico (AGENTS.md:
toda regra de entrada/saida em `strategy/` -> teste com cenario sintetico).

Cobre: aquecimento do lookback (sem sinal antes de `k_bars+1` fechamentos),
gatilho por limiar (nada abaixo, dispara igual ou acima), direcao FADE vs
CONTINUATION, cooldown apos fechamento, integracao com o motor (entra a
mercado, sai por alvo e por stop), e o freio de sessao opcional."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar
from strategy.daytrade.lab.win_extreme_reversal_f6 import WinExtremeReversalF6


def _bar(ts, o, h, l, c):
    return Bar(ts=ts, open=o, high=h, low=l, close=c, volume=10)


def _run_closes(strat, closes, start=pd.Timestamp("2026-01-05 13:00", tz="UTC")):
    """Alimenta uma sequencia de fechamentos (bar degenerada open=high=low=close)
    e devolve a lista de listas de acoes, uma por barra."""
    out = []
    for i, c in enumerate(closes):
        ts = start + pd.Timedelta(minutes=i)
        out.append(strat.on_bar(ts, _bar(ts, c, c, c, c), positions=[], session_pnl_brl=0.0))
    return out


def test_sem_sinal_enquanto_o_lookback_nao_aquece():
    strat = WinExtremeReversalF6(tick_size=5.0, k_bars=5, threshold_ticks=10.0)
    strat.on_session_start(None)
    # so' 5 fechamentos (precisa de k_bars+1=6 para o primeiro burst existir),
    # mesmo com um salto grande dentro deles.
    closes = [100000, 100000, 100000, 100000, 100500]
    actions = _run_closes(strat, closes)
    assert all(a == [] for a in actions)


def test_dispara_no_limiar_fade_inverte_o_lado_do_movimento():
    tick = 5.0
    strat = WinExtremeReversalF6(tick_size=tick, k_bars=3, threshold_ticks=10.0,
                                  stop_ticks=15.0, target_ticks=20.0, mode="fade")
    strat.on_session_start(None)
    # k_bars=3: burst = close[t] - close[t-3]. Sobe exatamente 10 ticks (50 pts).
    closes = [100000, 100000, 100000, 100050]
    actions = _run_closes(strat, closes)
    assert actions[:3] == [[], [], []]
    assert len(actions[3]) == 1
    enter = actions[3][0]
    assert enter.side == "short"  # subiu -> fade vende
    assert enter.initial_stop == pytest.approx(100050 + 15 * tick)
    assert enter.initial_target == pytest.approx(100050 - 20 * tick)


def test_abaixo_do_limiar_nao_dispara():
    tick = 5.0
    strat = WinExtremeReversalF6(tick_size=tick, k_bars=3, threshold_ticks=10.0)
    strat.on_session_start(None)
    closes = [100000, 100000, 100000, 100045]  # 9 ticks, abaixo do limiar de 10
    actions = _run_closes(strat, closes)
    assert all(a == [] for a in actions)


def test_mode_continuation_segue_o_mesmo_lado_do_movimento():
    tick = 5.0
    strat = WinExtremeReversalF6(tick_size=tick, k_bars=3, threshold_ticks=10.0, mode="continuation")
    strat.on_session_start(None)
    closes = [100000, 100000, 100000, 100050]  # subiu
    actions = _run_closes(strat, closes)
    enter = actions[3][0]
    assert enter.side == "long"  # subiu -> continuation compra


def test_movimento_de_queda_fade_compra():
    tick = 5.0
    strat = WinExtremeReversalF6(tick_size=tick, k_bars=3, threshold_ticks=10.0, mode="fade")
    strat.on_session_start(None)
    closes = [100000, 100000, 100000, 99950]  # caiu 10 ticks
    actions = _run_closes(strat, closes)
    enter = actions[3][0]
    assert enter.side == "long"


def test_reseta_estado_entre_sessoes():
    strat = WinExtremeReversalF6(tick_size=5.0, k_bars=3, threshold_ticks=10.0)
    strat.on_session_start(None)
    _run_closes(strat, [100000, 100000, 100000, 100050])
    assert len(strat._state.closes) == 4

    strat.on_session_start(None)  # nova sessao
    assert len(strat._state.closes) == 0
    assert strat._state.in_position is False
    assert strat._state.cooldown_left == 0


def test_integracao_entra_a_mercado_e_sai_pelo_alvo():
    tick = 5.0
    rows = [
        (100000, 100000, 100000, 100000),
        (100000, 100000, 100000, 100000),
        (100000, 100000, 100000, 100000),
        (100000, 100050, 99990, 100050),   # fecha com burst de +10 ticks -> decide short p/ proxima abertura
        (100050, 100060, 100000, 100040),  # executa a entrada no open=100050 (short)
        (99950, 99960, 99900, 99950),      # toca alvo (100050 - 20*5=99950)
        (99950, 99950, 99950, 99950),
    ]
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    bars = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    bars["tick_volume"] = 10

    strat = WinExtremeReversalF6(tick_size=tick, k_bars=3, threshold_ticks=10.0,
                                  stop_ticks=15.0, target_ticks=20.0, mode="fade")
    costs = IntradayCostModel(point_value_brl=0.2, tick_size=tick, fee_round_trip_brl=0.5, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000_000.0, session_end_time=time(23, 59))

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.entry_price == pytest.approx(100050.0)
    assert trade.exit_reason == IntradayExitReason.TARGET
    assert trade.exit_price == pytest.approx(99950.0)


def test_integracao_sai_pelo_stop():
    tick = 5.0
    rows = [
        (100000, 100000, 100000, 100000),
        (100000, 100000, 100000, 100000),
        (100000, 100000, 100000, 100000),
        (100000, 100050, 99990, 100050),   # burst +10 ticks -> decide short
        (100050, 100060, 100000, 100040),  # entra short no open=100050
        (100050, 100130, 100040, 100130),  # sobe 16 ticks (>15) -> stop
    ]
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    bars = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    bars["tick_volume"] = 10

    strat = WinExtremeReversalF6(tick_size=tick, k_bars=3, threshold_ticks=10.0,
                                  stop_ticks=15.0, target_ticks=20.0, mode="fade")
    costs = IntradayCostModel(point_value_brl=0.2, tick_size=tick, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000_000.0, session_end_time=time(23, 59))

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.STOP


def test_cooldown_impede_reentrada_imediata_apos_fechamento():
    tick = 5.0
    strat = WinExtremeReversalF6(tick_size=tick, k_bars=3, threshold_ticks=10.0,
                                  stop_ticks=15.0, target_ticks=20.0, mode="fade",
                                  cooldown_bars=5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")

    # dispara o primeiro sinal
    for i, c in enumerate([100000, 100000, 100000, 100050]):
        strat.on_bar(ts + pd.Timedelta(minutes=i), _bar(ts, c, c, c, c), positions=[], session_pnl_brl=0.0)

    # simula fechamento da posicao: uma chamada com posicao aberta, depois flat
    from strategy.daytrade.base import IntradayOpenPosition
    pos = IntradayOpenPosition(side="short", entry_ts=ts, entry_price=100050.0, quantity=1,
                                current_stop=100125.0, current_target=99950.0, bars_held=1)
    strat.on_bar(ts + pd.Timedelta(minutes=4), _bar(ts, 100040, 100040, 100040, 100040),
                 positions=[pos], session_pnl_brl=0.0)

    # primeira barra flat depois do fechamento: novo burst grande, mas em cooldown
    closes_pos_fechamento = [100040, 100540, 100540, 100540, 100540, 100540, 100540, 100540]
    actions = []
    for i, c in enumerate(closes_pos_fechamento):
        t = ts + pd.Timedelta(minutes=5 + i)
        actions.append(strat.on_bar(t, _bar(t, c, c, c, c), positions=[], session_pnl_brl=0.0))

    # nenhuma acao durante o cooldown (5 barras), mesmo com burst valido
    assert all(a == [] for a in actions[:5])


def test_session_stop_brl_default_none_nao_interrompe():
    strat = WinExtremeReversalF6(tick_size=5.0, k_bars=3, threshold_ticks=10.0)
    strat.on_session_start(None)
    closes = [100000, 100000, 100000, 100050]
    actions = _run_closes_with_pnl(strat, closes, session_pnl_brl=-999999.0)
    assert len(actions[3]) == 1


def test_session_stop_brl_explicito_interrompe_novo_gatilho():
    strat = WinExtremeReversalF6(tick_size=5.0, k_bars=3, threshold_ticks=10.0,
                                  session_stop_brl=100.0)
    strat.on_session_start(None)
    closes = [100000, 100000, 100000, 100050]
    actions = _run_closes_with_pnl(strat, closes, session_pnl_brl=-150.0)
    assert actions[3] == []


def _run_closes_with_pnl(strat, closes, session_pnl_brl, start=pd.Timestamp("2026-01-05 13:00", tz="UTC")):
    out = []
    for i, c in enumerate(closes):
        ts = start + pd.Timedelta(minutes=i)
        out.append(strat.on_bar(ts, _bar(ts, c, c, c, c), positions=[], session_pnl_brl=session_pnl_brl))
    return out
