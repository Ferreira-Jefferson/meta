"""Remuneracao do caixa parado — o default nao pode mudar nada, o opt-in tem que render.

AGENTS.md: "alteracao no engine -> teste anti-look-ahead deve permanecer verde".
Aqui o risco especifico e outro e igualmente caro: `cash_yield_path` nasceu
desligado porque o diario tem 16 anos de runs gravadas com caixa a 0%. Se o
default vazar ligado por descuido, todo capital final ja persistido passa a
significar outra coisa sem que nenhum teste reclame.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.costs import cash_yield_series
from backtest.engine import run_backtest
from core.config import BENCHMARK, BacktestConfig
from strategy.base import Strategy

IDX = pd.bdate_range("2020-01-01", periods=250)


def _panel(price: float) -> pd.DataFrame:
    s = pd.Series(float(price), index=IDX)
    return pd.DataFrame({"open": s, "high": s, "low": s, "close": s,
                         "volume": pd.Series(1e6, index=IDX)})


class _NeverTrades(Strategy):
    """Robo que nunca compra — todo o capital fica parado o backtest inteiro."""

    name = "never_trades"
    version = "1.0"
    candidate = False

    def on_bar(self, date, open_positions, cash_available):
        return []


def _run(cash_yield_path, capital=1000.0):
    universe = {"AAAA3.SA": _panel(10.0), BENCHMARK: _panel(100.0)}
    cfg = BacktestConfig(initial_capital=capital, lot_size=1,
                         cash_yield_path=cash_yield_path)
    return run_backtest(universe, _NeverTrades(), cfg,
                        start=str(IDX[0].date()), end=str(IDX[-1].date()))


def test_default_deixa_o_caixa_parado_a_zero():
    """Sem `cash_yield_path`, R$ 1.000 sem operar continuam R$ 1.000."""
    r = _run(None)
    assert r.metrics["final_capital"] == pytest.approx(1000.0)


def test_caixa_rende_quando_a_serie_e_apontada(tmp_path):
    """0,04%/dia por 250 pregoes = ~10,5% — o robo nao operou nenhuma vez."""
    p = tmp_path / "selic.parquet"
    pd.DataFrame({"valor": 0.04}, index=IDX).to_parquet(p)  # 0,04% ao DIA
    r = _run(str(p))
    esperado = 1000.0 * (1.0004 ** len(IDX))
    assert r.metrics["final_capital"] == pytest.approx(esperado, rel=1e-6)


def test_serie_ausente_nao_quebra_o_backtest():
    """Caminho inexistente vira 'sem remuneracao', nao excecao no meio de uma run."""
    assert cash_yield_series("nao/existe.parquet", IDX) is None
    assert _run("nao/existe.parquet").metrics["final_capital"] == pytest.approx(1000.0)


def test_percentual_ao_dia_e_nao_ao_ano(tmp_path):
    """A convencao do parquet do BCB e %/dia. Ler como %/ano erraria por ~252x.

    Guarda contra a confusao mais provavel deste arquivo: 0,04 no parquet e
    0,04% ao dia (~10% a.a.), nao 0,04% ao ano.
    """
    p = tmp_path / "selic.parquet"
    pd.DataFrame({"valor": 0.04}, index=IDX).to_parquet(p)
    taxa = cash_yield_series(str(p), IDX)
    assert taxa.iloc[0] == pytest.approx(0.0004)
    assert (1 + taxa.iloc[0]) ** 252 - 1 == pytest.approx(0.106, abs=0.005)
