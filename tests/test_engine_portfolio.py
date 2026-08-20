"""Testes diretos de `backtest/engine_portfolio.py` — o motor que decide os
numeros do backtest de referencia da campea (`portfolio_dip2_hw40`). Zero
teste direto existia antes desta feature.

Cobre: anti-look-ahead (D+1), o bug de assimetria Exit/Enter sobre dado
faltante (regra 4/7 do AGENTS.md), stop intrabar em gap down, a ORDEM das
operacoes na barra (stop libera caixa antes de qualquer entrada tentar
usa-lo), sizing com `size_hint=1.0`, saque simulado via `FloorSkim`,
`entries_filled` so contando entrada de fato preenchida, `r_multiple` usando
a constante documentada, e MFE/MAE usando so `close` (nunca high/low).
"""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.costs import apply_slippage, fees_for_leg
from backtest.engine_portfolio import run_portfolio_backtest
from backtest.sizing import plan_entry
from backtest.withdrawal import FloorSkim
from core.config import BENCHMARK, BacktestConfig
from core.models import ExitReason
from strategy.base import Enter, Exit, Strategy


class _StubStrategy(Strategy):
    """Estrategia sintetica: acoes fixas por data de DECISAO (close[D]),
    100% deterministica e alheia a qualquer logica de sinal — mesmo espirito
    do `_StubStrategy` de `tests/test_backtest_engine.py`, adaptado para
    aceitar varias acoes/varios tickers no mesmo dia."""

    name = "stub_portfolio"
    version = "0.1"

    def __init__(self, actions_by_date: dict | None = None):
        self._actions_by_date = {
            pd.Timestamp(k): list(v) for k, v in (actions_by_date or {}).items()
        }

    def initialize(self, panels, ibov):
        pass

    def on_bar(self, date, open_positions, cash_available):
        return list(self._actions_by_date.get(pd.Timestamp(date), []))


def _panel(dates, prices):
    """OHLCV simples: open==close==`prices`, high/low +-1%."""
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


def _ohlc(dates, opens, highs, lows, closes):
    """OHLCV com controle total por dia — usado quando open/close precisam
    divergir ou high/low precisam ser extremos deliberados."""
    return pd.DataFrame(
        {
            "open": opens, "high": highs, "low": lows, "close": closes,
            "adj_close": closes, "volume": [1_000_000] * len(dates),
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# (a) anti-look-ahead: close[D] -> open[D+1]
# ---------------------------------------------------------------------------

def test_anti_look_ahead_sinal_do_close_executa_no_open_do_dia_seguinte():
    dates = pd.bdate_range("2024-01-02", periods=10)
    prices = [10.0 + i for i in range(10)]
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(dates, [100_000.0] * 10),
    }
    strategy = _StubStrategy({
        dates[2]: [Enter(ticker="TEST.SA")],
        dates[7]: [Exit(ticker="TEST.SA", reason=ExitReason.CROSS_DOWN)],
    })
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert len(r.trades) == 1
    trade = r.trades[0]
    assert trade.entry_date == dates[3].date()
    assert trade.exit_date == dates[8].date()


# ---------------------------------------------------------------------------
# (b) Exit sem dado e descartado, nao executa tarde (regra 4/7)
# ---------------------------------------------------------------------------

def test_exit_sem_dado_e_descartado_nao_executa_tarde():
    dates = pd.bdate_range("2024-01-02", periods=10)
    prices = [50.0] * 10
    test_df = _panel(dates, prices).drop(dates[3])  # gap: TEST.SA nao prega em dates[3]
    other_df = _panel(dates, [20.0] * 10)  # mantem `today` no calendario do engine
    universe = {
        "TEST.SA": test_df,
        "OTHER.SA": other_df,
        BENCHMARK: _panel(dates, [100_000.0] * 10),
    }
    strategy = _StubStrategy({
        dates[1]: [Enter(ticker="TEST.SA")],                                   # -> executa dates[2]
        dates[2]: [Exit(ticker="TEST.SA", reason=ExitReason.ROTATION_OUT)],    # -> tentaria executar dates[3] (gap)
    })
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=2,
                             lot_size=1, stop_loss_pct=0.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert len(r.trades) == 1
    trade = r.trades[0]
    assert trade.ticker == "TEST.SA"
    # Exit descartado no gap (nao reenfileirado): so fecha no fechamento
    # forcado de fim de janela, nunca no dia em que o dado volta (dates[4]).
    assert trade.exit_reason == ExitReason.MANUAL
    assert trade.exit_date == dates[-1].date()


# ---------------------------------------------------------------------------
# (c) stop intrabar: exec = min(open, stop) num gap down
# ---------------------------------------------------------------------------

def test_stop_intrabar_executa_em_min_open_stop_no_gap_down():
    dates = pd.bdate_range("2024-01-02", periods=6)
    opens = [50.0, 50.0, 100.0, 70.0, 68.0, 68.0]
    highs = [51.0, 51.0, 101.0, 72.0, 69.0, 69.0]
    lows = [49.0, 49.0, 99.0, 65.0, 67.0, 67.0]
    closes = [50.0, 50.0, 100.0, 68.0, 68.0, 68.0]
    universe = {
        "TEST.SA": _ohlc(dates, opens, highs, lows, closes),
        BENCHMARK: _panel(dates, [100_000.0] * 6),
    }
    strategy = _StubStrategy({dates[1]: [Enter(ticker="TEST.SA")]})  # -> executa dates[2] open=100
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.10)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert len(r.trades) == 1
    trade = r.trades[0]
    entry_price = apply_slippage(100.0, "buy", config.costs)
    stop_price = entry_price * (1.0 - config.stop_loss_pct)
    # dates[3]: open=70 < stop (~90.14) -> exec_ref = min(open, stop) = open
    assert min(70.0, stop_price) == 70.0  # confirma que o cenario e de fato gap down
    expected_exit = apply_slippage(70.0, "sell", config.costs)
    assert trade.exit_reason == ExitReason.STOP
    assert trade.exit_date == dates[3].date()
    assert trade.exit_price == pytest.approx(expected_exit)


# ---------------------------------------------------------------------------
# (d) ordem das operacoes na barra: stop libera caixa ANTES da entrada usar
# ---------------------------------------------------------------------------

def test_ordem_das_operacoes_na_barra():
    dates = pd.bdate_range("2024-01-02", periods=6)
    a_opens = [50.0, 50.0, 100.0, 95.0, 95.0, 95.0]
    a_highs = [51.0, 51.0, 101.0, 96.0, 96.0, 96.0]
    a_lows = [49.0, 49.0, 99.0, 80.0, 80.0, 80.0]
    a_closes = [50.0, 50.0, 100.0, 90.0, 90.0, 90.0]
    b_prices = [10.0] * 6
    universe = {
        "A.SA": _ohlc(dates, a_opens, a_highs, a_lows, a_closes),
        "B.SA": _panel(dates, b_prices),
        BENCHMARK: _panel(dates, [100_000.0] * 6),
    }
    strategy = _StubStrategy({
        dates[1]: [Enter(ticker="A.SA")],                              # -> executa dates[2] open=100
        dates[2]: [Enter(ticker="B.SA", size_hint=1.0)],                # -> executa dates[3] (mesmo dia do stop de A)
    })
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.10)

    plan_a = plan_entry(100_000.0, 100.0, None, config)
    cash_after_a_entry = 100_000.0 - plan_a.cost
    stop_price = plan_a.exec_price * (1.0 - config.stop_loss_pct)
    exec_ref_stop = min(95.0, stop_price)
    exec_price_stop = apply_slippage(exec_ref_stop, "sell", config.costs)
    gross_stop = exec_price_stop * plan_a.quantity
    fees_stop = fees_for_leg(gross_stop, config.costs)
    cash_after_stop = cash_after_a_entry + (gross_stop - fees_stop)

    plan_b_correct_order = plan_entry(cash_after_stop, 10.0, 1.0, config)
    plan_b_wrong_order = plan_entry(cash_after_a_entry, 10.0, 1.0, config)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    b_trade = next(t for t in r.trades if t.ticker == "B.SA")
    assert b_trade.quantity == plan_b_correct_order.quantity
    # Falsificacao: se o stop rodasse DEPOIS das entradas, B teria sido
    # dimensionado pelo caixa PRE-stop (menor) — as duas quantidades tem de
    # divergir para este teste provar algo.
    assert plan_b_correct_order.quantity > plan_b_wrong_order.quantity


# ---------------------------------------------------------------------------
# (e) size_hint=1.0 usa caixa total, nunca dividido por slots livres
# ---------------------------------------------------------------------------

def test_sizing_com_size_hint_1_0_usa_caixa_total_nao_dividido_por_slots():
    dates = pd.bdate_range("2024-01-02", periods=4)
    universe = {
        "TEST.SA": _panel(dates, [100.0] * 4),
        BENCHMARK: _panel(dates, [100_000.0] * 4),
    }
    strategy = _StubStrategy({dates[0]: [Enter(ticker="TEST.SA", size_hint=1.0)]})
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=5,
                             lot_size=1, stop_loss_pct=0.0)

    expected_full = plan_entry(100_000.0, 100.0, 1.0, config).quantity
    expected_divided_by_slots = plan_entry(100_000.0 / 5, 100.0, 1.0, config).quantity

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert len(r.trades) == 1
    assert r.trades[0].quantity == expected_full
    assert expected_full > expected_divided_by_slots


# ---------------------------------------------------------------------------
# (f) saque simulado (FloorSkim): decide no close, executa no open seguinte
# ---------------------------------------------------------------------------

def test_saque_simulado_executado_no_open_seguinte_com_taxas():
    dates = pd.bdate_range("2024-01-02", periods=5)
    universe = {
        "TEST.SA": _panel(dates, [100.0] * 5),
        BENCHMARK: _panel(dates, [100_000.0] * 5),
    }
    strategy = _StubStrategy({dates[0]: [Enter(ticker="TEST.SA", size_hint=1.0)]})
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0)
    # day=3: dispara no 3o pregao do mes (dates[2], indice 2) — a posicao ja
    # esta aberta (entrada executou em dates[1]), forcando liquidacao parcial
    # para levantar o caixa do saque (gera fees_paid > 0 de verdade).
    policy = FloorSkim(pct=0.5, floor=0.0, day=3, cap=1e12, min_amount=0.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool",
                                withdrawal_policy=policy)

    assert len(r.withdrawals) == 1
    w = r.withdrawals[0]
    # Decidido no close de dates[2] -> executado no open de dates[3].
    assert w.date == dates[3]
    assert w.requested > 0.0
    assert w.executed == pytest.approx(w.requested, rel=0.02)
    assert w.fees_paid > 0.0, "saque exigiu liquidar parte da posicao — deve ter taxas"
    assert len(w.liquidated) == 1
    assert w.liquidated[0][0] == "TEST.SA"
    assert r.metrics["withdrawals_count"] == 1
    assert r.metrics["withdrawn_total"] == pytest.approx(w.executed)


# ---------------------------------------------------------------------------
# (g) entries_filled so conta entrada REALMENTE preenchida
# ---------------------------------------------------------------------------

def test_entries_filled_so_conta_entrada_realmente_preenchida():
    dates = pd.bdate_range("2024-01-02", periods=3)
    universe = {
        "A.SA": _panel(dates, [995.0] * 3),
        "B.SA": _panel(dates, [50.0] * 3),
        BENCHMARK: _panel(dates, [100_000.0] * 3),
    }
    # A consome quase todo o caixa (size_hint=1.0, R$1.000 iniciais) —
    # sobra pouco demais para B comprar nem 1 lote (lot_size=1, B a R$50).
    strategy = _StubStrategy({
        dates[0]: [
            Enter(ticker="A.SA", size_hint=1.0),
            Enter(ticker="B.SA", size_hint=1.0),
        ],
    })
    config = BacktestConfig(initial_capital=1_000.0, max_concurrent_positions=2,
                             lot_size=1, stop_loss_pct=0.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool",
                                entry_fill_mode="debug")

    m = r.metrics
    assert m["entries_attempted"] == 2
    assert m["entries_filled"] == 1
    assert m["entries_skipped"] == 1


# ---------------------------------------------------------------------------
# (h) r_multiple usa a constante documentada, coerente com BacktestConfig
# ---------------------------------------------------------------------------

def test_r_multiple_usa_constante_documentada_e_bate_com_config():
    from datetime import date as _date

    from core.models import Trade, _DEFAULT_RISK_PCT  # existe so apos o fix do Passo 4

    assert _DEFAULT_RISK_PCT == BacktestConfig().stop_loss_pct

    trade = Trade(
        ticker="X.SA", strategy_name="s", strategy_version="1",
        entry_date=_date(2024, 1, 2), entry_price=100.0, quantity=10,
        capital_allocated=1_000.0, exit_date=_date(2024, 2, 2), exit_price=120.0,
        exit_reason=ExitReason.MANUAL,
    )
    risk_per_share = 100.0 * _DEFAULT_RISK_PCT
    expected_r = (120.0 - 100.0) / risk_per_share
    assert trade.r_multiple == pytest.approx(expected_r)


# ---------------------------------------------------------------------------
# (i) MFE/MAE usa apenas close, nunca high/low
# ---------------------------------------------------------------------------

def test_mfe_mae_usa_apenas_close_nunca_high_low():
    dates = pd.bdate_range("2024-01-02", periods=5)
    opens = [50.0, 100.0, 100.0, 110.0, 95.0]
    highs = [51.0, 101.0, 1000.0, 1.0, 96.0]     # dia 2/3: high/low absurdos
    lows = [49.0, 99.0, 1.0, 0.5, 94.0]
    closes = [50.0, 100.0, 110.0, 90.0, 95.0]
    universe = {
        "TEST.SA": _ohlc(dates, opens, highs, lows, closes),
        BENCHMARK: _panel(dates, [100_000.0] * 5),
    }
    strategy = _StubStrategy({
        dates[0]: [Enter(ticker="TEST.SA")],                                # -> executa dates[1] open=100
        dates[3]: [Exit(ticker="TEST.SA", reason=ExitReason.CROSS_DOWN)],   # -> executa dates[4]
    })
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0)  # stop=0: high/low extremos nao podem disparar stop

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert len(r.trades) == 1
    trade = r.trades[0]
    entry_price = apply_slippage(100.0, "buy", config.costs)
    # Enquanto aberta (dates[1]..dates[4]), o close visto foi 100/110/90/95 —
    # maximo 110, minimo 90 (NUNCA os high/low de 1000/1/0.5 dos dias 2 e 3).
    expected_mfe = (110.0 - entry_price) / entry_price
    expected_mae = (90.0 - entry_price) / entry_price
    assert trade.max_favorable_excursion == pytest.approx(expected_mfe)
    assert trade.max_adverse_excursion == pytest.approx(expected_mae)


# ---------------------------------------------------------------------------
# (j) `stop_fill`: hipotese de EXECUCAO do stop, nao regra de decisao
# ---------------------------------------------------------------------------

def _cenario_stop(fill: str):
    """Mesma posicao, mesmo nivel de stop, tres hipoteses de saida.

    Barra de saida desenhada para SEPARAR as tres: `low` perfura bem abaixo do
    stop e o `close` RECUPERA para acima dele. Assim cada arm tem um desfecho
    distinto e nenhum teste passa por coincidencia numerica.
    """
    dates = pd.bdate_range("2024-01-02", periods=5)
    #                       entra em dates[2] no open=100; stop = 90 (10%)
    opens = [50.0, 50.0, 100.0, 99.0, 95.0]
    highs = [51.0, 51.0, 101.0, 99.5, 96.0]
    lows = [49.0, 49.0, 99.0, 80.0, 94.0]   # dates[3]: perfura ate 80
    closes = [50.0, 50.0, 100.0, 95.0, 95.0]  # dates[3]: fecha em 95, ACIMA do stop
    universe = {
        "TEST.SA": _ohlc(dates, opens, highs, lows, closes),
        BENCHMARK: _panel(dates, [100_000.0] * 5),
    }
    strategy = _StubStrategy({dates[1]: [Enter(ticker="TEST.SA")]})
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                            lot_size=1, stop_loss_pct=0.10, stop_fill=fill)
    r = run_portfolio_backtest(universe, strategy, config,
                               start=dates[0].strftime("%Y-%m-%d"),
                               end=dates[-1].strftime("%Y-%m-%d"),
                               satellite_pct=0.0, redist_mode="pool")
    return r, config, dates


def test_stop_fill_default_e_o_comportamento_historico_do_diario():
    """`stop_or_open` e o default e tem de continuar sendo o que sempre foi:
    dispara na perfuracao da minima e preenche no NIVEL do stop (o open de
    dates[3] e 99, acima do stop de 90, entao `min(open, stop)` = stop).

    Se este teste mudar de valor, todo o diario gravado passa a descrever
    outra coisa — e por isso que o knob existe com default, em vez de o
    comportamento ser trocado.
    """
    r, config, dates = _cenario_stop("stop_or_open")
    entry = apply_slippage(100.0, "buy", config.costs)
    stop = entry * (1.0 - config.stop_loss_pct)
    assert len(r.trades) == 1
    assert r.trades[0].exit_reason == ExitReason.STOP
    assert r.trades[0].exit_date == dates[3].date()
    assert r.trades[0].exit_price == pytest.approx(apply_slippage(stop, "sell", config.costs))


def test_stop_fill_low_sai_na_minima_o_piso_de_qualquer_feed_atrasado():
    """Limite inferior de um feed intradiario com atraso: ninguem sai pior que
    a minima do dia. Mesmo gatilho, preco pior — e a conta de quanto a
    hipotese otimista do diario vale em dinheiro."""
    r, config, dates = _cenario_stop("low")
    assert len(r.trades) == 1
    assert r.trades[0].exit_reason == ExitReason.STOP
    assert r.trades[0].exit_price == pytest.approx(apply_slippage(80.0, "sell", config.costs))


def test_stop_fill_close_pode_NAO_disparar_quando_o_dia_recupera():
    """O achado que faz este arm valer a pena: um feed que so ve o fechamento
    nao enxerga a perfuracao. Em dates[3] a minima foi 80 (bem abaixo do stop
    de 90) mas o fechamento voltou para 95 — o `ParquetCloseFeed` nunca veria
    preco abaixo do stop, e a posicao FICA.

    Ou seja: a divergencia entre backtest e operacao real nao e so "sai
    pior". As vezes e "nao sai", o que pode terminar melhor ou pior. Por isso
    o arm `close` pode aparecer ACIMA do REF na medicao sem ser boa noticia.
    """
    r, _config, _dates = _cenario_stop("close")
    assert not [t for t in r.trades if t.exit_reason == ExitReason.STOP], (
        "feed de fechamento nao deveria ter visto a perfuracao intradiaria")
