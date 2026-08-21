from __future__ import annotations

import pytest

from backtest.intraday.costs import FuturesCostModel, apply_futures_slippage, fees_round_trip_brl, gross_pnl_brl


def test_from_symbol_info_deriva_valor_do_ponto():
    # WIN real: trade_tick_size=5 pontos, trade_tick_value=R$1,00 -> ponto = R$0,20
    model = FuturesCostModel.from_symbol_info(trade_tick_value=1.0, trade_tick_size=5.0, fee_round_trip_brl=1.5)
    assert model.point_value_brl == pytest.approx(0.2)


def test_apply_futures_slippage_direcao():
    model = FuturesCostModel(point_value_brl=0.2, tick_size=5.0, fee_round_trip_brl=1.5, slippage_ticks=1.0)
    assert apply_futures_slippage(100_000.0, "buy", model) == pytest.approx(100_005.0)
    assert apply_futures_slippage(100_000.0, "sell", model) == pytest.approx(99_995.0)


@pytest.mark.parametrize(
    "side,entry,exit_,esperado_sinal",
    [
        ("long", 100_000.0, 100_100.0, 1),   # comprou, subiu -> ganho
        ("long", 100_000.0, 99_900.0, -1),   # comprou, caiu -> perda
        ("short", 100_000.0, 99_900.0, 1),   # vendeu, caiu -> ganho
        ("short", 100_000.0, 100_100.0, -1), # vendeu, subiu -> perda
    ],
)
def test_gross_pnl_brl_sinal_correto(side, entry, exit_, esperado_sinal):
    model = FuturesCostModel(point_value_brl=0.2, tick_size=5.0, fee_round_trip_brl=1.5)
    pnl = gross_pnl_brl(entry, exit_, quantity=1, side=side, model=model)
    assert (pnl > 0) == (esperado_sinal > 0)
    assert pnl == pytest.approx(100.0 * 0.2 * esperado_sinal)


def test_fees_round_trip_escala_com_quantidade():
    model = FuturesCostModel(point_value_brl=0.2, tick_size=5.0, fee_round_trip_brl=1.5)
    assert fees_round_trip_brl(1, model) == pytest.approx(1.5)
    assert fees_round_trip_brl(3, model) == pytest.approx(4.5)
