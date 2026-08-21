"""Testes do motor intrabar (`backtest/intraday/engine.py`): execucao na
abertura da PROXIMA barra (anti-look-ahead), stop/target tocado dentro da
barra (com e sem gap), resolucao de barra ambigua, flatten forcado no fim
da sessao (e descarte de pendencia), multiplos trades por sessao, nao
carregar posicao entre sessoes, lado short, e o contrato explicito com
`backtest.metrics.trade_stats`."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import FuturesCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from backtest.metrics import trade_stats
from core.models import IntradayExitReason
from strategy.daytrade.base import Enter, Exit, IntradayStrategy


class _StubIntradayStrategy(IntradayStrategy):
    name = "stub_intraday"
    version = "0.1"

    def __init__(self, actions_by_ts: dict[pd.Timestamp, list] | None = None):
        self.actions_by_ts = actions_by_ts or {}

    def on_bar(self, ts, bar, position, session_pnl_brl):
        return self.actions_by_ts.get(ts, [])


def _mk_bars(session_date: str, rows: list[tuple[float, float, float, float]],
             start: str = "09:00", freq: str = "1min") -> pd.DataFrame:
    idx = pd.date_range(f"{session_date} {start}", periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["tick_volume"] = 10
    return df


def _config(**overrides) -> IntradayBacktestConfig:
    costs = FuturesCostModel(point_value_brl=1.0, tick_size=1.0, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    defaults = dict(costs=costs, initial_capital=10_000.0, default_quantity=1, session_end_time=time(23, 59))
    defaults.update(overrides)
    return IntradayBacktestConfig(**defaults)


def test_entrada_executa_na_abertura_da_proxima_barra():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (105, 106, 104, 105),
        (110, 111, 109, 110),
        (112, 113, 111, 112),
        (112, 113, 111, 112),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[1]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(105.0)  # aberto na barra 1, nao na 0
    assert trade.exit_price == pytest.approx(110.0)   # aberto na barra 2, nao na 1
    assert trade.exit_reason == IntradayExitReason.SIGNAL
    assert trade.pnl_brl > 0


def test_stop_dispara_no_nivel_quando_a_barra_nao_abre_alem_dele():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 100, 94, 97),   # low=94 toca stop=95, open=100 nao gapeou alem dele
        (97, 98, 96, 97),
        (97, 98, 96, 97),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long", initial_stop=95.0)]})
    result = run_intraday_backtest(bars, strat, _config())

    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(95.0)
    assert trade.exit_reason == IntradayExitReason.STOP


def test_stop_dispara_no_open_quando_a_barra_abre_alem_dele_gap():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (90, 91, 88, 89),   # gap para baixo, abre JA alem do stop=95
        (89, 90, 88, 89),
        (89, 90, 88, 89),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long", initial_stop=95.0)]})
    result = run_intraday_backtest(bars, strat, _config())

    trade = result.trades[0]
    assert trade.exit_price == pytest.approx(90.0)
    assert trade.exit_reason == IntradayExitReason.STOP


def test_target_dispara_no_nivel_quando_a_barra_nao_abre_alem_dele():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 112, 99, 105),  # high=112 toca target=110, open=100 nao gapeou alem dele
        (105, 106, 104, 105),
        (105, 106, 104, 105),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long", initial_stop=50.0, initial_target=110.0)]})
    result = run_intraday_backtest(bars, strat, _config())

    trade = result.trades[0]
    assert trade.exit_price == pytest.approx(110.0)
    assert trade.exit_reason == IntradayExitReason.TARGET


@pytest.mark.parametrize(
    "resolution,expected_reason,expected_price",
    [
        ("stop_first", IntradayExitReason.STOP, 95.0),
        ("target_first", IntradayExitReason.TARGET, 105.0),
    ],
)
def test_barra_ambigua_resolvida_pela_config(resolution, expected_reason, expected_price):
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 106, 94, 100),  # toca stop=95 E target=105 na MESMA barra
        (100, 101, 99, 100),
        (100, 101, 99, 100),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long", initial_stop=95.0, initial_target=105.0)]})
    result = run_intraday_backtest(bars, strat, _config(ambiguous_bar_resolution=resolution))

    trade = result.trades[0]
    assert trade.exit_reason == expected_reason
    assert trade.exit_price == pytest.approx(expected_price)


def test_flatten_forcado_por_horario_fecha_posicao_e_descarta_pendencia():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),  # 09:00 idx0: Enter
        (100, 101, 99, 100),  # 09:01: executa Enter no open; sem acao nova
        (100, 101, 99, 100),  # 09:02: decide Exit (pendente p/ 09:03 -- a barra de corte)
        (100, 101, 99, 90),   # 09:03: cutoff bate AQUI -> flatten no CLOSE, pendencia descartada
        (100, 101, 99, 100),  # 09:04
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[2]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config(session_end_time=time(9, 3)))

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == IntradayExitReason.FORCED_FLATTEN
    assert trade.exit_ts == bars.index[3]
    assert trade.exit_price == pytest.approx(90.0)  # close da barra de corte, nao o open


def test_multiplas_entradas_e_saidas_na_mesma_sessao_geram_trades_independentes():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (105, 106, 104, 105),
        (110, 111, 109, 110),
        (108, 109, 107, 108),
        (115, 116, 114, 115),
        (115, 116, 114, 115),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[1]: [Exit()],
        bars.index[2]: [Enter(side="long")],
        bars.index[3]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 2
    assert result.trades[0].entry_price == pytest.approx(105.0)
    assert result.trades[0].exit_price == pytest.approx(110.0)
    assert result.trades[1].entry_price == pytest.approx(108.0)
    assert result.trades[1].exit_price == pytest.approx(115.0)
    assert all(t.exit_reason == IntradayExitReason.SIGNAL for t in result.trades)


def test_flatten_forcado_nao_carrega_posicao_para_a_proxima_sessao():
    bars_a = _mk_bars("2026-01-05", [(100, 101, 99, 100)] * 3)
    bars_b = _mk_bars("2026-01-06", [(200, 201, 199, 200)] * 3)
    bars = pd.concat([bars_a, bars_b])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long")]})

    vistas: dict[pd.Timestamp, object] = {}
    original_on_bar = strat.on_bar

    def _spy(ts, bar, position, session_pnl_brl):
        vistas[ts] = position
        return original_on_bar(ts, bar, position, session_pnl_brl)

    strat.on_bar = _spy

    result = run_intraday_backtest(bars, strat, _config())

    flatten_trades = [t for t in result.trades if t.exit_reason == IntradayExitReason.FORCED_FLATTEN]
    assert len(flatten_trades) == 1
    assert flatten_trades[0].exit_ts.date() == bars_a.index[-1].date()
    assert vistas[bars_b.index[0]] is None


def test_lado_short_stop_acima_target_abaixo():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),  # entrada short no open=100
        (95, 96, 90, 92),     # low=90 toca target=93, open=95 nao gapeou alem dele
        (92, 93, 91, 92),
        (92, 93, 91, 92),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="short", initial_stop=110.0, initial_target=93.0)]})
    result = run_intraday_backtest(bars, strat, _config())

    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(93.0)
    assert trade.exit_reason == IntradayExitReason.TARGET
    assert trade.pnl_brl > 0  # vendeu a 100, recomprou a 93


def test_metrics_reaproveita_trade_stats_sem_modificacao():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (105, 106, 104, 105),  # trade1: lucro (100 -> 105)
        (105, 106, 104, 105),
        (95, 96, 94, 95),      # trade2: perda (105 -> 95)
        (95, 96, 94, 95),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[1]: [Exit()],
        bars.index[2]: [Enter(side="long")],
        bars.index[3]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config())

    expected = trade_stats([t.pnl_pct for t in result.trades])
    assert result.metrics["win_rate"] == pytest.approx(expected["win_rate"])
    assert result.metrics["profit_factor"] == pytest.approx(expected["profit_factor"])
    assert result.metrics["n_trades"] == 2
