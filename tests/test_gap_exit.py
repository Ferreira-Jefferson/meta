"""Gatilho de queda SUBITA (`BacktestConfig.gap_exit_pct`).

Por que existe
--------------
Ate 2026-08-20 o robo tinha apenas DOIS gatilhos que olhavam para o proprio
ativo: o stop FIXO de `stop_loss_pct` abaixo do preco de ENTRADA (que nunca
sobe) e a rotacao por momentum (so no fim do mes). Nao havia nada que
detectasse "este papel desabou de repente".

O buraco concreto que isto cobre: um papel que SUBIU bastante desde a entrada
pode cair 25% num unico pregao e ainda ficar ACIMA do stop — e ai o robo nao
faz nada ate o rebalance de fim de mes. Ver
`test_gap_dispara_no_caso_em_que_o_stop_jamais_dispararia`, que e a razao de
existir da feature.

Medido contra desastres reais (`scripts/run_disaster_forced_entry.py`):
HAPV3 2025-11-13 abriu -31,2% e caiu mais -25,6% no pregao; DASA3 2021-04-07
abriu -45,6%; IRBR3 2020-03-04 abriu -24,6%; ENEV3 2015-02-13 abriu -40,5%.

DESLIGADO por default (`gap_exit_pct=None`) de proposito: o robo do podio
(`liquid_dual10`) foi medido e promovido SEM este gatilho.
"""
from __future__ import annotations

import pandas as pd

from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BENCHMARK, BacktestConfig
from core.models import ExitReason
from strategy.base import Enter, Strategy


class _EntraUmaVez(Strategy):
    """Compra `ticker` na data dada e nunca mais decide nada."""

    name = "stub_gap"
    version = "0.1"

    def __init__(self, quando: pd.Timestamp, ticker: str = "TEST.SA"):
        self._quando = pd.Timestamp(quando)
        self._ticker = ticker

    def initialize(self, panels, ibov):
        pass

    def on_bar(self, date, open_positions, cash_available):
        if pd.Timestamp(date) == self._quando:
            return [Enter(ticker=self._ticker)]
        return []


def _ohlc(dates, opens, closes):
    """OHLCV com high/low derivados dos extremos do proprio dia.

    high/low englobam open e close para o cenario nao depender de um extremo
    arbitrario — o gatilho de gap olha SO o `open` e o stop olha o `low`,
    entao deixa-los coerentes evita um teste passar por acidente.
    """
    return pd.DataFrame(
        {
            "open": opens,
            "high": [max(o, c) * 1.001 for o, c in zip(opens, closes)],
            "low": [min(o, c) * 0.999 for o, c in zip(opens, closes)],
            "close": closes,
            "adj_close": closes,
            "volume": [1_000_000] * len(dates),
        },
        index=dates,
    )


def _rodar(universe, dates, quando_entra, **cfg_kwargs):
    base = dict(initial_capital=100_000.0, max_concurrent_positions=1,
                lot_size=1, stop_loss_pct=0.15)
    base.update(cfg_kwargs)
    return run_portfolio_backtest(
        universe, _EntraUmaVez(quando_entra), BacktestConfig(**base),
        start=dates[0].strftime("%Y-%m-%d"), end=dates[-1].strftime("%Y-%m-%d"),
        satellite_pct=0.0, redist_mode="pool")


# ---------------------------------------------------------------------------
# o default nao pode mudar NADA — este e o teste mais importante do arquivo
# ---------------------------------------------------------------------------

def test_desligado_por_default_e_identico_ao_comportamento_anterior():
    """`gap_exit_pct=None` tem de produzir exatamente o mesmo resultado.

    O cenario tem um gap de -20% que DISPARARIA o gatilho se ele estivesse
    ligado — se o default vazasse, este teste quebra.
    """
    dates = pd.bdate_range("2024-01-02", periods=8)
    precos = [100.0, 100.0, 100.0, 100.0, 80.0, 80.0, 80.0, 80.0]
    universe = {"TEST.SA": _ohlc(dates, precos, precos),
                BENCHMARK: _ohlc(dates, [1000.0] * 8, [1000.0] * 8)}

    sem_campo = _rodar(universe, dates, dates[1])
    com_none = _rodar(universe, dates, dates[1], gap_exit_pct=None)

    pd.testing.assert_series_equal(sem_campo.equity_curve, com_none.equity_curve)
    assert len(sem_campo.trades) == len(com_none.trades)
    for a, b in zip(sem_campo.trades, com_none.trades):
        assert (a.ticker, a.exit_date, a.exit_price) == (b.ticker, b.exit_date, b.exit_price)


# ---------------------------------------------------------------------------
# o gatilho em si
# ---------------------------------------------------------------------------

def test_gap_de_20_por_cento_dispara_saida_no_open_do_dia():
    dates = pd.bdate_range("2024-01-02", periods=8)
    precos = [100.0, 100.0, 100.0, 100.0, 80.0, 80.0, 80.0, 80.0]
    universe = {"TEST.SA": _ohlc(dates, precos, precos),
                BENCHMARK: _ohlc(dates, [1000.0] * 8, [1000.0] * 8)}

    r = _rodar(universe, dates, dates[1], gap_exit_pct=0.15)

    assert len(r.trades) == 1
    t = r.trades[0]
    assert t.exit_date == dates[4].date(), "tem de sair NO dia do gap, nao depois"
    assert t.exit_price < 80.0 * 1.001, "saida no open do dia do gap, menos slippage"


def test_gap_dispara_no_caso_em_que_o_stop_jamais_dispararia():
    """A RAZAO DE EXISTIR da feature.

    Entra a 100 (stop fica em 85 e nunca sobe), o papel sobe ate 200 e entao
    abre a 150 — queda de -25% contra o fecho de ontem. O stop em 85 esta
    longissimo: sem o gatilho a posicao sobrevive e so seria reavaliada no
    fim do mes. Com o gatilho, sai no mesmo pregao, ainda com lucro.
    """
    dates = pd.bdate_range("2024-01-02", periods=8)
    opens = [100.0, 100.0, 100.0, 150.0, 200.0, 150.0, 150.0, 150.0]
    closes = [100.0, 100.0, 150.0, 200.0, 200.0, 150.0, 150.0, 150.0]
    universe = {"TEST.SA": _ohlc(dates, opens, closes),
                BENCHMARK: _ohlc(dates, [1000.0] * 8, [1000.0] * 8)}

    sem = _rodar(universe, dates, dates[1])
    com = _rodar(universe, dates, dates[1], gap_exit_pct=0.15)

    assert all(t.exit_date != dates[5].date() for t in sem.trades), (
        "sem o gatilho o stop de 85 nunca e tocado — a posicao tem de sobreviver")
    assert len(com.trades) == 1
    t = com.trades[0]
    assert t.exit_date == dates[5].date()
    assert t.exit_price > 100.0, "sai com LUCRO: protege ganho que o stop deixaria evaporar"


def test_gap_menor_que_o_limiar_nao_dispara():
    dates = pd.bdate_range("2024-01-02", periods=8)
    precos = [100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 90.0, 90.0]   # -10%
    universe = {"TEST.SA": _ohlc(dates, precos, precos),
                BENCHMARK: _ohlc(dates, [1000.0] * 8, [1000.0] * 8)}

    r = _rodar(universe, dates, dates[1], gap_exit_pct=0.15)

    assert all(t.exit_date != dates[4].date() for t in r.trades), (
        "-10% esta dentro da tolerancia de 15% — nao pode disparar")


def test_no_dia_em_que_gap_e_stop_valeriam_vende_uma_vez_so_e_pelo_gap():
    """Gap de -30%: o stop (85) tambem seria furado. Uma venda so, no open."""
    dates = pd.bdate_range("2024-01-02", periods=8)
    precos = [100.0, 100.0, 100.0, 100.0, 70.0, 70.0, 70.0, 70.0]
    universe = {"TEST.SA": _ohlc(dates, precos, precos),
                BENCHMARK: _ohlc(dates, [1000.0] * 8, [1000.0] * 8)}

    r = _rodar(universe, dates, dates[1], gap_exit_pct=0.15)

    assert len(r.trades) == 1, "dupla venda: gap e stop fecharam a mesma posicao"
    t = r.trades[0]
    assert t.exit_reason == ExitReason.STOP
    assert abs(t.exit_price - 70.0) < 70.0 * 0.01, (
        "preco de saida tem de ser o do GAP (open=70), nao o nivel do stop (85)")


def test_primeiro_pregao_sem_fechamento_anterior_nao_quebra():
    """Sem fecho de ontem nao ha referencia — nao dispara e nao levanta erro."""
    dates = pd.bdate_range("2024-01-02", periods=5)
    opens = [50.0, 100.0, 100.0, 100.0, 100.0]
    closes = [100.0, 100.0, 100.0, 100.0, 100.0]
    universe = {"TEST.SA": _ohlc(dates, opens, closes),
                BENCHMARK: _ohlc(dates, [1000.0] * 5, [1000.0] * 5)}

    r = _rodar(universe, dates, dates[1], gap_exit_pct=0.15)

    assert r.equity_curve is not None and len(r.equity_curve) == 5
