"""Teste de `backtest.metrics.period_return`/`calmar` -- o fallback que evita
anualizar (elevar a `1/anos`) quando o periodo e' curto demais pra isso fazer
sentido (ver a docstring de `period_return` para o motivo: um OOS de
semanas/meses anualizado AMPLIFICA o retorno em vez de estima-lo).
`cagr()` em si fica intocada -- e' o que o ranking diario/portfolio usa em
janelas de anos de verdade, onde anualizar e' a conta certa."""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.metrics import cagr, calmar, max_drawdown, period_return


def _equity(dias: int, multiplicador: float) -> pd.Series:
    idx = pd.date_range("2026-01-01", periods=2, freq=f"{dias}D")
    return pd.Series([100.0, 100.0 * multiplicador], index=idx)


def test_period_return_anualiza_normalmente_com_pelo_menos_um_ano():
    equity = _equity(400, 1.5)  # ~1.1 anos, retorno total de 50%
    assert period_return(equity) == pytest.approx(cagr(equity))
    assert period_return(equity) > 0.30  # anualizado > que o retorno bruto do periodo


def test_period_return_nao_anualiza_periodo_curto():
    """67 dias (~0,18 anos), retorno total de 3x -- anualizar daria
    39.805% (3**(1/0.1834)-1). `period_return` devolve so' o retorno do
    periodo (2.0 = +200%), sem amplificar."""
    equity = _equity(67, 3.0)
    assert period_return(equity) == pytest.approx(2.0)
    assert cagr(equity) > 300  # a versao anualizada e' a distorcao que isto evita


def test_period_return_respeita_o_limiar_customizado():
    equity = _equity(200, 2.0)  # ~0,55 anos
    assert period_return(equity, min_years_to_annualize=0.5) == pytest.approx(cagr(equity))
    assert period_return(equity, min_years_to_annualize=1.0) == pytest.approx(1.0)  # +100%, nao anualizado


def test_calmar_default_usa_cagr_puro_sem_ressalva():
    """Comportamento antigo intacto -- e' o que o ranking diario/portfolio
    usa (`backtest/engine.py`, `engine_portfolio.py`, `engine_satellite.py`),
    em janelas de anos onde anualizar e' a conta certa."""
    idx = pd.date_range("2026-01-01", periods=400, freq="1D")
    equity = pd.Series([100.0] + [90.0] * 198 + [150.0] * 201, index=idx)  # MaxDD -10%
    assert calmar(equity) == pytest.approx(cagr(equity) / abs(max_drawdown(equity)))


def test_calmar_com_limiar_troca_o_numerador_para_period_return():
    """Mesmo formato de curva (queda + recuperacao), mas periodo CURTO
    (67 dias) -- com `min_years_to_annualize=1.0`, o numerador tem que ser
    `period_return` (nao amplificado), nao `cagr` (que explodiria)."""
    idx = pd.date_range("2026-01-01", periods=67, freq="1D")
    equity = pd.Series([100.0] + [80.0] * 32 + [200.0] * 34, index=idx)  # MaxDD -20%, retorno total 2x

    esperado = period_return(equity, min_years_to_annualize=1.0) / abs(max_drawdown(equity))
    assert calmar(equity, min_years_to_annualize=1.0) == pytest.approx(esperado)
    # confirma que NAO e' o calmar antigo (que usaria cagr, muito maior)
    assert calmar(equity, min_years_to_annualize=1.0) != pytest.approx(calmar(equity))
