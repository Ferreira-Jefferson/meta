"""Cenario sintetico para `ContinuidadeDiaria` (regra de trade da
sub-hipotese 1, CONTINUIDADE DIARIA): decisao unica por pregao na PRIMEIRA
barra, mantida ate o flatten forcado -- sem stop, sem alvo, sem saida
antecipada."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.lab.continuidade_daily import ContinuidadeDiaria


def _mk_bars(session_date: str, rows: list[tuple[float, float, float, float]],
             start: str = "09:00", freq: str = "1min") -> pd.DataFrame:
    idx = pd.date_range(f"{session_date} {start}", periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["tick_volume"] = 10
    return df


def _config() -> IntradayBacktestConfig:
    costs = IntradayCostModel(point_value_brl=1.0, tick_size=1.0, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    return IntradayBacktestConfig(costs=costs, initial_capital=100_000.0, default_quantity=1,
                                   session_end_time=time(23, 59))


#: Fecho de cada sessao: dia1=100, dia2=110 (+10 -> dia3 "up"), dia3=90
#: (-20 -> dia4 "down"), dia4=92. So' a partir do 3o pregao ha' historico
#: suficiente (2 fechamentos anteriores) para um sinal existir.
def _quatro_sessoes() -> pd.DataFrame:
    dia1 = _mk_bars("2026-01-05", [(100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100)])
    dia2 = _mk_bars("2026-01-06", [(100, 111, 99, 110), (110, 111, 109, 110), (110, 111, 109, 110)])
    dia3 = _mk_bars("2026-01-07", [(110, 111, 89, 90), (90, 91, 89, 90), (90, 91, 89, 90)])
    dia4 = _mk_bars("2026-01-08", [(90, 95, 85, 92), (92, 93, 91, 92), (92, 93, 91, 92)])
    return pd.concat([dia1, dia2, dia3, dia4])


def test_sem_historico_suficiente_nao_opera_nos_dois_primeiros_pregoes():
    bars = _quatro_sessoes()
    strat = ContinuidadeDiaria(symbol="STUB3", direction="continuation")
    result = run_intraday_backtest(bars, strat, _config())

    datas_com_trade = {pd.Timestamp(t.entry_ts).date() for t in result.trades}
    assert pd.Timestamp("2026-01-05").date() not in datas_com_trade
    assert pd.Timestamp("2026-01-06").date() not in datas_com_trade


def test_continuation_entra_no_mesmo_lado_do_dia_anterior():
    bars = _quatro_sessoes()
    strat = ContinuidadeDiaria(symbol="STUB3", direction="continuation")
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 2  # so' dia3 e dia4 tem sinal
    dia3, dia4 = result.trades
    assert dia3.side == "long"   # dia2(110) > dia1(100) -> continua pra cima
    assert dia4.side == "short"  # dia3(90) < dia2(110) -> continua pra baixo


def test_reversal_entra_no_lado_oposto_do_dia_anterior():
    bars = _quatro_sessoes()
    strat = ContinuidadeDiaria(symbol="STUB3", direction="reversal")
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 2
    dia3, dia4 = result.trades
    assert dia3.side == "short"  # oposto de continuation
    assert dia4.side == "long"


def test_entrada_executa_na_abertura_da_segunda_barra_da_sessao_nunca_na_primeira():
    # anti-look-ahead: a decisao e' tomada olhando a barra 0 (na verdade nem
    # precisa dela -- o sinal ja' vem pronto de `seed_daily_volatility`), mas
    # so' pode EXECUTAR na abertura da barra SEGUINTE, nunca na mesma barra.
    bars = _quatro_sessoes()
    strat = ContinuidadeDiaria(symbol="STUB3", direction="continuation")
    result = run_intraday_backtest(bars, strat, _config())

    dia3 = result.trades[0]
    # dia3: 2a barra tem open=90 (1a barra, onde a decisao foi tomada, tem open=110)
    assert dia3.entry_price == pytest.approx(90.0)


def test_posicao_e_fechada_por_flatten_forcado_no_fim_da_sessao_sem_stop_nem_alvo():
    bars = _quatro_sessoes()
    strat = ContinuidadeDiaria(symbol="STUB3", direction="continuation")
    result = run_intraday_backtest(bars, strat, _config())

    for trade in result.trades:
        assert trade.exit_reason == IntradayExitReason.FORCED_FLATTEN
        # a saida cai na MESMA sessao da entrada -- day trade nunca carrega
        # posicao (regra do motor, nao da estrategia)
        assert pd.Timestamp(trade.exit_ts).date() == pd.Timestamp(trade.entry_ts).date()


def test_nunca_mais_de_uma_entrada_por_sessao():
    bars = _quatro_sessoes()
    strat = ContinuidadeDiaria(symbol="STUB3", direction="continuation")
    result = run_intraday_backtest(bars, strat, _config())

    contagem_por_dia = {}
    for t in result.trades:
        d = pd.Timestamp(t.entry_ts).date()
        contagem_por_dia[d] = contagem_por_dia.get(d, 0) + 1
    assert all(n == 1 for n in contagem_por_dia.values())


def test_retorno_diario_exatamente_zero_fica_de_fora_do_pregao():
    # dia2 fecha IGUAL ao dia1 -- sinal indefinido, dia3 nao opera.
    dia1 = _mk_bars("2026-01-05", [(100, 101, 99, 100), (100, 101, 99, 100)])
    dia2 = _mk_bars("2026-01-06", [(100, 101, 99, 100), (100, 101, 99, 100)])
    dia3 = _mk_bars("2026-01-07", [(100, 101, 99, 100), (100, 101, 99, 100)])
    bars = pd.concat([dia1, dia2, dia3])

    strat = ContinuidadeDiaria(symbol="STUB3", direction="continuation")
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 0
