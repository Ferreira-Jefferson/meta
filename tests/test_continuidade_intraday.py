"""Cenario sintetico para `ContinuidadeIntraday` (regra de trade da
sub-hipotese 2, CONTINUIDADE INTRADIARIA): decide a cada fronteira de barra
reamostrada (`bar_minutes`), Exit-entao-Enter para trocar de lado, mantem a
posicao quando o lado desejado nao muda."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.lab.continuidade_intraday import ContinuidadeIntraday


def _mk_bars(session_date: str, closes: list[float], start: str = "09:00") -> pd.DataFrame:
    idx = pd.date_range(f"{session_date} {start}", periods=len(closes), freq="1min", tz="UTC")
    rows = [(c, c + 0.5, c - 0.5, c) for c in closes]
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["tick_volume"] = 10
    return df


def _config() -> IntradayBacktestConfig:
    costs = IntradayCostModel(point_value_brl=1.0, tick_size=1.0, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    return IntradayBacktestConfig(costs=costs, initial_capital=100_000.0, default_quantity=1,
                                   session_end_time=time(23, 59))


def test_bar_minutes_invalido_levanta_erro():
    with pytest.raises(ValueError):
        ContinuidadeIntraday(symbol="STUB3", bar_minutes=0)


def test_sem_janela_anterior_nao_opera():
    # so' 1 fronteira (minuto 0) em toda a sessao -- nunca ha' retorno de
    # janela ANTERIOR pra comparar, entao nunca ha' sinal.
    bars = _mk_bars("2026-01-05", [100, 100, 100, 100])
    strat = ContinuidadeIntraday(symbol="STUB3", bar_minutes=5, direction="reversal")
    result = run_intraday_backtest(bars, strat, _config())
    assert result.trades == []


def test_reversal_entra_no_lado_oposto_da_janela_que_fechou():
    # fronteira em t=0 (minuto 0, so' registra a referencia). fronteira em
    # t=5 (minuto 5): retorno = 105-100 = +5 -> bruto "long" -> reversal
    # entra "short". Entrada so' executa na ABERTURA da barra SEGUINTE (t=6).
    closes = [100, 100, 100, 100, 100, 105, 105, 105]
    bars = _mk_bars("2026-01-05", closes)
    strat = ContinuidadeIntraday(symbol="STUB3", bar_minutes=5, direction="reversal")
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.entry_price == pytest.approx(105.0)  # open da barra t=6
    assert trade.exit_reason == IntradayExitReason.FORCED_FLATTEN


def test_continuation_entra_no_mesmo_lado_da_janela_que_fechou():
    closes = [100, 100, 100, 100, 100, 105, 105, 105]
    bars = _mk_bars("2026-01-05", closes)
    strat = ContinuidadeIntraday(symbol="STUB3", bar_minutes=5, direction="continuation")
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 1
    assert result.trades[0].side == "long"


def test_mantem_posicao_quando_lado_desejado_nao_muda_na_proxima_fronteira():
    # t=0 -> 100 (referencia). t=5 -> 105 (bruto long, reversal desejado
    # short, entra na abertura de t=6). t=10 -> 110 (retorno da janela
    # 5..10 = +5, de novo bruto long -> reversal desejado short = MESMO
    # lado ja aberto) -- nenhuma acao nova, a MESMA posicao continua.
    closes = [100] * 5 + [105] * 5 + [110, 110, 110]
    bars = _mk_bars("2026-01-05", closes)
    strat = ContinuidadeIntraday(symbol="STUB3", bar_minutes=5, direction="reversal")
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 1  # uma unica posicao, nunca fechada e reaberta
    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.entry_price == pytest.approx(105.0)  # abertura de t=6, nao mudou em t=11


def test_troca_de_lado_fecha_e_reabre_em_duas_barras():
    # t=0 -> 100 (ref). t=5 -> 105 (bruto long -> reversal short, entra
    # t=6). t=10 -> 95 (retorno da janela 5..10 = 95-105=-10 -> bruto short
    # -> reversal LONG, diferente do lado aberto -- Exit devolvido em t=10,
    # executa na abertura de t=11; o proprio on_bar de t=11 ja ve a posicao
    # flat e devolve Enter, que executa na abertura de t=12).
    closes = [100] * 5 + [105] * 5 + [95] * 5
    bars = _mk_bars("2026-01-05", closes)
    strat = ContinuidadeIntraday(symbol="STUB3", bar_minutes=5, direction="reversal")
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 2
    primeiro, segundo = result.trades
    assert primeiro.side == "short"
    assert primeiro.entry_price == pytest.approx(105.0)   # abertura t=6
    assert primeiro.exit_price == pytest.approx(95.0)     # abertura t=11
    assert primeiro.exit_reason == IntradayExitReason.SIGNAL
    assert segundo.side == "long"
    assert segundo.entry_price == pytest.approx(95.0)     # abertura t=12
    assert segundo.exit_reason == IntradayExitReason.FORCED_FLATTEN


def test_retorno_zero_na_fronteira_fecha_posicao_e_fica_flat():
    # t=0 -> 100 (ref). t=5 -> 105 (entra short em t=6). t=10 -> 105 de
    # novo (retorno da janela 5..10 = 0 -> sinal indefinido -> desejado
    # None, diferente do lado aberto -- Exit em t=10, fecha na abertura de
    # t=11). Sem sinal novo, nao reabre.
    closes = [100] * 5 + [105] * 5 + [105] * 5
    bars = _mk_bars("2026-01-05", closes)
    strat = ContinuidadeIntraday(symbol="STUB3", bar_minutes=5, direction="reversal")
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.exit_price == pytest.approx(105.0)  # abertura t=11
    assert trade.exit_reason == IntradayExitReason.SIGNAL


def test_sinal_nao_atravessa_fronteira_de_sessao():
    # a fronteira com sinal (minuto 5) e' a ULTIMA barra do dia 1 -- o motor
    # faz flatten forcado ANTES de chamar `on_bar` na ultima barra de uma
    # sessao (`backtest.intraday.machine`, passo "(2) flatten forcado" roda
    # antes do passo "(5) decisao do robo"), entao o sinal nem chega a ser
    # CALCULADO no dia 1. Dia 2 tem que comecar sem NENHUMA referencia --
    # `on_session_start` zera `_last_boundary_close`/`_desired_side` de
    # qualquer forma, mesmo que o dia 1 tivesse deixado algo pendente.
    dia1 = _mk_bars("2026-01-05", [100] * 5 + [105])
    dia2 = _mk_bars("2026-01-06", [200, 200, 200, 200, 200, 210, 210, 210])
    bars = pd.concat([dia1, dia2])
    strat = ContinuidadeIntraday(symbol="STUB3", bar_minutes=5, direction="reversal")
    result = run_intraday_backtest(bars, strat, _config())

    # so' o dia 2 gera trade (retorno 210-200=+10 -> reversal short, entra
    # na abertura da barra seguinte).
    assert len(result.trades) == 1
    assert result.trades[0].side == "short"
    assert pd.Timestamp(result.trades[0].entry_ts).date() == pd.Timestamp("2026-01-06").date()
