from __future__ import annotations

import pytest

from backtest.intraday.costs import (
    PMAM3_EXCHANGE_FEE_PCT_PER_LEG,
    IntradayCostModel,
    apply_intraday_slippage,
    fees_round_trip_brl,
    gross_pnl_brl,
)


def test_from_symbol_info_deriva_valor_do_ponto():
    # tick_size=5 pontos, tick_value=R$1,00 -> ponto = R$0,20 (relacao generica
    # do terminal MT5, valida para qualquer simbolo -- nao especifica de PMAM3).
    model = IntradayCostModel.from_symbol_info(trade_tick_value=1.0, trade_tick_size=5.0, fee_round_trip_brl=1.5)
    assert model.point_value_brl == pytest.approx(0.2)


def test_apply_intraday_slippage_direcao():
    model = IntradayCostModel(point_value_brl=0.2, tick_size=5.0, fee_round_trip_brl=1.5, slippage_ticks=1.0)
    assert apply_intraday_slippage(100_000.0, "buy", model) == pytest.approx(100_005.0)
    assert apply_intraday_slippage(100_000.0, "sell", model) == pytest.approx(99_995.0)


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
    model = IntradayCostModel(point_value_brl=0.2, tick_size=5.0, fee_round_trip_brl=1.5)
    pnl = gross_pnl_brl(entry, exit_, quantity=1, side=side, model=model)
    assert (pnl > 0) == (esperado_sinal > 0)
    assert pnl == pytest.approx(100.0 * 0.2 * esperado_sinal)


def test_fees_round_trip_escala_com_quantidade():
    model = IntradayCostModel(point_value_brl=0.2, tick_size=5.0, fee_round_trip_brl=1.5)
    assert fees_round_trip_brl(1, entry_price=100.0, exit_price=101.0, model=model) == pytest.approx(1.5)
    assert fees_round_trip_brl(3, entry_price=100.0, exit_price=101.0, model=model) == pytest.approx(4.5)


def test_fees_round_trip_taxa_de_bolsa_percentual_por_perna():
    model = IntradayCostModel(point_value_brl=1.0, tick_size=0.01, fee_round_trip_brl=0.0, exchange_fee_pct_per_leg=0.001)
    # 100 acoes, entrada a 1.00 (notional R$100), saida a 1.10 (notional R$110)
    # taxa = 0.001 * 100 * (1.00 + 1.10) = 0.21
    fees = fees_round_trip_brl(100, entry_price=1.00, exit_price=1.10, model=model)
    assert fees == pytest.approx(0.21)


def test_taxa_pmam3_e_2x_a_taxa_real_pesquisada():
    from backtest.intraday.costs import B3_DAY_TRADE_FEE_PCT_PER_LEG
    assert PMAM3_EXCHANGE_FEE_PCT_PER_LEG == pytest.approx(B3_DAY_TRADE_FEE_PCT_PER_LEG * 2.0)


def test_from_symbol_info_repassa_taxa_de_bolsa():
    model = IntradayCostModel.from_symbol_info(
        trade_tick_value=0.01, trade_tick_size=0.01, fee_round_trip_brl=0.0,
        exchange_fee_pct_per_leg=PMAM3_EXCHANGE_FEE_PCT_PER_LEG,
    )
    assert model.exchange_fee_pct_per_leg == pytest.approx(PMAM3_EXCHANGE_FEE_PCT_PER_LEG)
