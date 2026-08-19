"""Testes diretos da campea: `DipTop1Portfolio` (`portfolio_dip2_hw40`).

Cadeia real: `BuyTheDip` -> `DipTop1Hysteresis` -> `PortfolioHysteresis` ->
`DipTop1Portfolio`. O `on_bar` REALMENTE usado e o de `DipTop1Hysteresis` —
nem `PortfolioHysteresis` nem `DipTop1Portfolio` o sobrescrevem. A campea tem
`satellite_pct=0.00`: satelites nunca se formam para ela, entao a logica de
satelite de `PortfolioHysteresis` fica fora de escopo aqui.

Duas camadas de teste, deliberadamente separadas:
- (a) testa a FORMULA do score de momentum 12-1, rodando `initialize()`
  sobre precos sinteticos reais.
- (b)-(i) testam a LOGICA DE DECISAO de `on_bar` dado um `_scores`/
  `_dist_from_high`/`_month_end`/`_blackout`/`_selic_tightening` conhecidos,
  atribuidos direto na instancia — isola a decisao do calculo do indicador
  (ja coberto por (a)). Mesmo espirito da injecao manual de
  `_selic_tightening` usada no teste (f).
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.models import ExitReason
from strategy.base import Enter, Exit, OpenPosition
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio


def _panel(dates, prices):
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "adj_close": prices,
            "volume": [1_000_000] * len(prices),
        },
        index=dates,
    )


def _open_position(ticker, entry_price=10.0, quantity=100):
    return {
        ticker: OpenPosition(
            ticker=ticker, entry_date=pd.Timestamp("2024-01-02"),
            entry_price=entry_price, quantity=quantity,
            current_stop=None, bars_held=10,
        )
    }


def _rig(strategy, dates, *, scores=None, dist=None, month_end=None,
         blackout=None, selic=None):
    """Injeta estado interno direto (sem rodar `initialize()` sobre precos
    reais) para isolar a decisao de `on_bar` do calculo do indicador."""
    strategy._scores = scores or {}
    strategy._dist_from_high = dist or {}
    strategy._month_end = month_end if month_end is not None else pd.Series(False, index=dates)
    strategy._blackout = blackout if blackout is not None else pd.Series(False, index=dates)
    strategy._selic_tightening = selic if selic is not None else pd.Series(False, index=dates)
    return strategy


# ---------------------------------------------------------------------------
# (a) formula do score — via initialize() real sobre precos sinteticos
# ---------------------------------------------------------------------------

def test_momentum_12_1_ranqueia_por_variacao_shift21_menos_shift252():
    dates = pd.bdate_range("2024-01-02", periods=300)
    prices_a = [float(i) + 10.0 for i in range(300)]  # rampa ascendente
    prices_b = [10.0] * 300  # flat — score sempre 0
    panels = {"AAA.SA": _panel(dates, prices_a), "BBB.SA": _panel(dates, prices_b)}
    ibov = _panel(dates, [100_000.0] * 300)

    strategy = DipTop1Portfolio()
    strategy.initialize(panels, ibov)

    idx = 280
    check_date = dates[idx]
    # shift(21) -> posicao idx-21; shift(252) -> posicao idx-252 (calculo
    # independente do codigo de producao, direto na lista de precos crua)
    price_near = prices_a[idx - 21]
    price_far = prices_a[idx - 252]
    expected_score_a = price_near / price_far - 1.0

    assert strategy._scores["AAA.SA"].loc[check_date] == pytest.approx(expected_score_a)
    assert strategy._scores["BBB.SA"].loc[check_date] == pytest.approx(0.0)
    assert strategy._scores["AAA.SA"].loc[check_date] > strategy._scores["BBB.SA"].loc[check_date]


# ---------------------------------------------------------------------------
# (b)-(d) histerese de 15%
# ---------------------------------------------------------------------------

def test_hysteresis_nao_rotaciona_abaixo_do_limiar_15pct():
    date = pd.Timestamp("2024-03-29")
    strategy = DipTop1Portfolio()
    _rig(
        strategy, [date],
        scores={
            "HELD.SA": pd.Series([1.0], index=[date]),
            "NEW.SA": pd.Series([1.10], index=[date]),  # < 1.0*1.15 = 1.15
        },
        month_end=pd.Series([True], index=[date]),
    )

    actions = strategy.on_bar(date, _open_position("HELD.SA"), 10_000.0)

    assert actions == []


def test_hysteresis_rotaciona_quando_bate_o_limiar():
    date = pd.Timestamp("2024-03-29")
    strategy = DipTop1Portfolio()
    _rig(
        strategy, [date],
        scores={
            "HELD.SA": pd.Series([1.0], index=[date]),
            "NEW.SA": pd.Series([1.20], index=[date]),  # >= 1.0*1.15 = 1.15
        },
        month_end=pd.Series([True], index=[date]),
    )

    actions = strategy.on_bar(date, _open_position("HELD.SA"), 10_000.0)

    assert actions == [Exit(ticker="HELD.SA", reason=ExitReason.ROTATION_OUT)]


def test_hysteresis_score_negativo_do_held_usa_formula_alternativa():
    """held_score <= 0 usa `held_score + abs(held_score)*hysteresis`
    (`h3_hysteresis.py:62`), NAO `held_score*(1+hysteresis)` (formula do
    ramo positivo). Valores escolhidos para DIVERGIR entre as duas formulas:
    threshold correto = -0.5 + 0.5*0.15 = -0.425 (bloqueia, -0.44 < -0.425);
    threshold da formula errada = -0.5*1.15 = -0.575 (rotacionaria,
    -0.44 >= -0.575) — se o ramo alternativo quebrar e usar a formula do
    ramo positivo, este teste vira rotacao em vez de bloqueio."""
    date = pd.Timestamp("2024-03-29")
    strategy = DipTop1Portfolio()
    _rig(
        strategy, [date],
        scores={
            "HELD.SA": pd.Series([-0.5], index=[date]),
            "NEW.SA": pd.Series([-0.44], index=[date]),
        },
        month_end=pd.Series([True], index=[date]),
    )

    actions = strategy.on_bar(date, _open_position("HELD.SA"), 10_000.0)

    assert actions == []


# ---------------------------------------------------------------------------
# (e) gate de dip 2% / janela 40 pregoes
# ---------------------------------------------------------------------------

def test_dip_gate_2pct_sobre_maxima_40_bloqueia_entrada_sem_dip():
    date = pd.Timestamp("2024-03-29")

    sem_dip = DipTop1Portfolio()
    _rig(
        sem_dip, [date],
        scores={"NEW.SA": pd.Series([0.5], index=[date])},
        dist={"NEW.SA": pd.Series([-0.01], index=[date])},  # 1% < 2% exigido
        month_end=pd.Series([True], index=[date]),
    )
    assert sem_dip.on_bar(date, {}, 10_000.0) == []

    com_dip = DipTop1Portfolio()
    _rig(
        com_dip, [date],
        scores={"NEW.SA": pd.Series([0.5], index=[date])},
        dist={"NEW.SA": pd.Series([-0.03], index=[date])},  # 3% >= 2%
        month_end=pd.Series([True], index=[date]),
    )
    actions = com_dip.on_bar(date, {}, 10_000.0)
    assert actions == [Enter(ticker="NEW.SA", size_hint=1.0)]


# ---------------------------------------------------------------------------
# (f) gate de aperto de Selic — saida defensiva total
# ---------------------------------------------------------------------------

def test_selic_tightening_dispara_saida_defensiva_para_todas_posicoes():
    date = pd.Timestamp("2024-03-29")
    strategy = DipTop1Portfolio()
    _rig(
        strategy, [date],
        month_end=pd.Series([True], index=[date]),
        selic=pd.Series([True], index=[date]),
    )
    open_positions = {**_open_position("A.SA"), **_open_position("B.SA")}

    actions = strategy.on_bar(date, open_positions, 10_000.0)

    assert {a.ticker for a in actions} == {"A.SA", "B.SA"}
    assert all(isinstance(a, Exit) and a.reason == ExitReason.IBOV_DEFENSIVE for a in actions)
    assert strategy._pending_rebalance is False


# ---------------------------------------------------------------------------
# (g) blackout adia o rebalance, executa no proximo pregao limpo
# ---------------------------------------------------------------------------

def test_blackout_adia_rebalance_e_executa_no_primeiro_pregao_limpo():
    d1 = pd.Timestamp("2024-05-06")  # month-end simulado, dentro do blackout
    d2 = pd.Timestamp("2024-05-07")  # dia seguinte, fora do blackout
    dates = [d1, d2]
    strategy = DipTop1Portfolio()
    _rig(
        strategy, dates,
        scores={"NEW.SA": pd.Series([0.5, 0.5], index=dates)},
        dist={"NEW.SA": pd.Series([-0.03, -0.03], index=dates)},
        month_end=pd.Series([True, False], index=dates),
        blackout=pd.Series([True, False], index=dates),
    )

    actions1 = strategy.on_bar(d1, {}, 10_000.0)
    assert actions1 == []
    assert strategy._pending_rebalance is True

    actions2 = strategy.on_bar(d2, {}, 10_000.0)
    assert strategy._pending_rebalance is False
    assert actions2 == [Enter(ticker="NEW.SA", size_hint=1.0)]


# ---------------------------------------------------------------------------
# (h) state()/restore() de _pending_rebalance
# ---------------------------------------------------------------------------

def test_state_e_restore_do_pending_rebalance():
    strategy = DipTop1Portfolio()
    strategy._pending_rebalance = True
    assert strategy.state() == {"_pending_rebalance": True}

    fresh = DipTop1Portfolio()
    assert fresh._pending_rebalance is False
    fresh.restore({"_pending_rebalance": "true"})
    assert fresh._pending_rebalance is True


# ---------------------------------------------------------------------------
# (i) rotaciona mas nao entra quando o novo rank-1 nao tem dip
# ---------------------------------------------------------------------------

def test_rotaciona_e_nao_entra_quando_novo_rank1_sem_dip():
    date = pd.Timestamp("2024-03-29")
    strategy = DipTop1Portfolio()
    _rig(
        strategy, [date],
        scores={
            "HELD.SA": pd.Series([0.10], index=[date]),
            "NEW.SA": pd.Series([0.20], index=[date]),  # >= 0.10*1.15 = 0.115
        },
        dist={"NEW.SA": pd.Series([-0.01], index=[date])},  # sem dip (< 2%)
        month_end=pd.Series([True], index=[date]),
    )

    actions = strategy.on_bar(date, _open_position("HELD.SA"), 10_000.0)

    assert actions == [Exit(ticker="HELD.SA", reason=ExitReason.ROTATION_OUT)]
