"""Testes da politica de saque (`backtest/withdrawal.py`).

Cobre `FloorSkim` — a politica escolhida — e a analitica do overlay. As
politicas alternativas foram medidas e descartadas em 2026-08-17; os numeros
ficaram no registro de decisao no topo de `withdrawal.py`.
"""
import json

import pandas as pd
import pytest

from backtest.withdrawal import (
    OFFICIAL_FLOOR_MULTIPLE,
    OFFICIAL_MIN_AMOUNT,
    OFFICIAL_PCT,
    FloorSkim,
    WithdrawalEvent,
    external_cash_curve,
    official_policy,
    reinvested_equity_curve,
)


def _d(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


def _plain(**kw) -> FloorSkim:
    """FloorSkim sem o minimo, para testar a mecanica base isoladamente."""
    kw.setdefault("pct", 0.01)
    kw.setdefault("floor", 40_000.0)
    kw.setdefault("day", 1)
    kw.setdefault("min_amount", 0.0)
    return FloorSkim(**kw)


# ---------- piso -----------------------------------------------------------

def test_nao_saca_abaixo_do_piso():
    p = _plain()
    assert p.on_close(_d("2010-01-04"), 39_999.0) == 0.0
    assert p.on_close(_d("2010-02-01"), 40_000.0) == 0.0
    assert p.on_close(_d("2010-03-01"), 50_000.0) == pytest.approx(500.0)


def test_nunca_derruba_a_carteira_abaixo_do_piso():
    """Saque limitado a (equity - piso), mesmo que o pct pedisse mais."""
    p = _plain(pct=0.10)
    assert p.on_close(_d("2010-01-04"), 41_000.0) == pytest.approx(1_000.0)


def test_respeita_o_cap_de_isencao_de_ir():
    p = _plain(pct=0.50, cap=20_000.0)
    assert p.on_close(_d("2010-01-04"), 200_000.0) == pytest.approx(20_000.0)


# ---------- cadencia -------------------------------------------------------

def test_uma_vez_por_mes_no_dia_escolhido():
    p = _plain(day=3)
    assert p.on_close(_d("2010-01-04"), 100_000.0) == 0.0       # 1o pregao
    assert p.on_close(_d("2010-01-05"), 100_000.0) == 0.0       # 2o
    assert p.on_close(_d("2010-01-06"), 100_000.0) == pytest.approx(1_000.0)  # 3o
    assert p.on_close(_d("2010-01-07"), 100_000.0) == 0.0       # nao repete
    # mes novo, conta reinicia
    assert p.on_close(_d("2010-02-01"), 100_000.0) == 0.0
    assert p.on_close(_d("2010-02-02"), 100_000.0) == 0.0
    assert p.on_close(_d("2010-02-03"), 100_000.0) == pytest.approx(1_000.0)


def test_evento_de_liquidez_antecipa_e_nao_duplica():
    """Qualquer venda serve (caixa em mao) e consome o saque do mes."""
    p = _plain(day=3)
    p.on_close(_d("2010-01-04"), 100_000.0)
    assert p.on_liquidity_event(_d("2010-01-05"), 100_000.0, "stop") == pytest.approx(1_000.0)
    # ja pagou em janeiro: nem o 3o pregao nem outra venda sacam de novo
    assert p.on_close(_d("2010-01-06"), 100_000.0) == 0.0
    assert p.on_liquidity_event(_d("2010-01-07"), 100_000.0, "rotation_out") == 0.0
    assert p.on_close(_d("2010-02-01"), 100_000.0) == 0.0
    assert p.on_close(_d("2010-02-02"), 100_000.0) == 0.0
    assert p.on_close(_d("2010-02-03"), 100_000.0) == pytest.approx(1_000.0)


# ---------- minimo com fila ------------------------------------------------

def test_minimo_acumula_ate_bater_o_valor():
    """Parcela abaixo do minimo nao se perde: entra na fila e sai somada."""
    # 0,5% de 100k = R$500/mes; minimo R$1.000 -> paga a cada 2 meses
    p = FloorSkim(pct=0.005, floor=40_000.0, day=1, min_amount=1_000.0)
    assert p.on_close(_d("2010-01-04"), 100_000.0) == 0.0          # fila: 500
    pago = p.on_close(_d("2010-02-01"), 100_000.0)                  # fila: 1000
    assert pago == pytest.approx(1_000.0)
    p.on_executed(_d("2010-02-02"), pago)
    assert p.on_close(_d("2010-03-01"), 100_000.0) == 0.0          # fila: 500
    assert p.on_close(_d("2010-04-01"), 100_000.0) == pytest.approx(1_000.0)


def test_minimo_nao_acumula_duas_vezes_no_mesmo_mes():
    """A parcela do mes entra na fila uma unica vez, mesmo com venda no meio."""
    p = FloorSkim(pct=0.005, floor=40_000.0, day=1, min_amount=1_000.0)
    p.on_close(_d("2010-01-04"), 100_000.0)                         # acumula 500
    # venda no mesmo mes: tenta pagar, mas a fila (500) nao bate o minimo
    assert p.on_liquidity_event(_d("2010-01-05"), 100_000.0, "rotation_out") == 0.0
    assert p._pool == pytest.approx(500.0)                          # nao acumulou 2x


def test_shortfall_volta_para_a_fila():
    p = FloorSkim(pct=0.01, floor=40_000.0, day=1, min_amount=1_000.0)
    pedido = p.on_close(_d("2010-01-04"), 140_000.0)
    assert pedido == pytest.approx(1_400.0)
    p.on_executed(_d("2010-01-05"), 1_000.0)                        # saiu menos
    assert p._pool == pytest.approx(400.0)                          # resto voltou


def test_sem_minimo_paga_a_parcela_cheia_todo_mes():
    p = _plain()
    assert p.on_close(_d("2010-01-04"), 100_000.0) == pytest.approx(1_000.0)
    assert p.on_close(_d("2010-02-01"), 100_000.0) == pytest.approx(1_000.0)


# ---------- guarda de drawdown (opcional) ---------------------------------

def test_dd_guard_pausa_em_capital_ferido():
    p = _plain(dd_guard=0.15)
    assert p.on_close(_d("2010-01-04"), 100_000.0) == pytest.approx(1_000.0)  # topo
    assert p.on_close(_d("2010-02-01"), 80_000.0) == 0.0    # -20% do topo: pausa
    assert p.on_close(_d("2010-03-01"), 90_000.0) == pytest.approx(900.0)  # -10%: volta


# ---------- configuracao oficial ------------------------------------------

def test_official_policy_usa_a_configuracao_registrada():
    p = official_policy(initial_capital=1_000.0)
    assert p.pct == pytest.approx(OFFICIAL_PCT)
    assert p.floor == pytest.approx(OFFICIAL_FLOOR_MULTIPLE * 1_000.0)
    assert p.min_amount == pytest.approx(OFFICIAL_MIN_AMOUNT)
    assert p.dd_guard is None


def test_official_policy_escala_o_piso_com_o_capital():
    """O piso e multiplo do aporte, nao um valor absoluto."""
    assert official_policy(1_000.0).floor == pytest.approx(55_000.0)
    assert official_policy(10_000.0).floor == pytest.approx(550_000.0)


def test_official_policy_devolve_instancia_nova():
    """Politica guarda estado — reusar instancia entre runs contamina o resultado."""
    a, b = official_policy(), official_policy()
    assert a is not b
    a.on_close(_d("2010-01-04"), 100_000.0)
    a.on_close(_d("2010-01-05"), 100_000.0)
    a.on_close(_d("2010-01-06"), 100_000.0)
    assert a._pool != b._pool or a._paid_month != b._paid_month


# ---------- analitica ------------------------------------------------------

def test_external_cash_curve_rende_selic():
    idx = pd.DatetimeIndex(["2010-01-04", "2010-01-05", "2010-01-06"])
    events = [WithdrawalEvent(date=idx[0], requested=100.0, executed=100.0, equity_before=1000.0)]
    rate = pd.Series([0.05, 0.05, 0.05], index=idx)  # 0,05% ao dia
    curve = external_cash_curve(events, idx, daily_rate_pct=rate)
    assert curve.iloc[0] == pytest.approx(100.0)          # deposito no dia
    assert curve.iloc[1] == pytest.approx(100.0 * 1.0005)
    assert curve.iloc[2] == pytest.approx(100.0 * 1.0005**2)


def test_external_cash_curve_sem_juros_apenas_soma():
    idx = pd.DatetimeIndex(["2010-01-04", "2010-01-05"])
    events = [
        WithdrawalEvent(date=idx[0], requested=10.0, executed=10.0, equity_before=100.0),
        WithdrawalEvent(date=idx[1], requested=5.0, executed=5.0, equity_before=90.0),
    ]
    curve = external_cash_curve(events, idx)
    assert list(curve) == [10.0, 15.0]


def test_reinvested_curve_neutraliza_o_saque():
    """Carteira 100 -> 110, saca 10 (fica 100) -> 110. TWR = 100 -> 110 -> 121."""
    idx = pd.DatetimeIndex(["2010-01-04", "2010-01-05", "2010-01-06"])
    eq = pd.Series([100.0, 100.0, 110.0], index=idx)
    events = [WithdrawalEvent(date=idx[1], requested=10.0, executed=10.0, equity_before=110.0)]
    twr = reinvested_equity_curve(eq, events)
    assert twr.iloc[1] == pytest.approx(110.0)
    assert twr.iloc[2] == pytest.approx(121.0)


def test_withdrawal_event_shortfall():
    e = WithdrawalEvent(date=_d("2010-01-04"), requested=1_000.0, executed=800.0,
                        equity_before=100_000.0)
    assert e.shortfall == pytest.approx(200.0)


# ---------- persistencia de estado (restart ao vivo) -----------------------

def test_state_round_trip_via_json_preserva_comportamento():
    """`state()` -> JSON -> `restore()` numa instancia nova reproduz o comportamento."""
    p = _plain(day=3)
    p.on_close(_d("2010-01-04"), 100_000.0)   # sessao 1
    p.on_close(_d("2010-01-05"), 100_000.0)   # sessao 2
    p.on_close(_d("2010-01-06"), 100_000.0)   # sessao 3 -> paga

    snapshot = json.loads(json.dumps(p.state()))
    fresh = _plain(day=3)
    fresh.restore(snapshot)

    # a partir daqui as duas instancias tem de andar juntas
    assert fresh.on_close(_d("2010-01-07"), 100_000.0) == p.on_close(_d("2010-01-07"), 100_000.0)
    assert fresh.on_close(_d("2010-02-01"), 100_000.0) == p.on_close(_d("2010-02-01"), 100_000.0)
    assert fresh.on_close(_d("2010-02-02"), 100_000.0) == p.on_close(_d("2010-02-02"), 100_000.0)
    assert fresh.on_close(_d("2010-02-03"), 100_000.0) == p.on_close(_d("2010-02-03"), 100_000.0)


def test_restore_normaliza_lista_em_tupla_da_cadencia():
    """Sem a normalizacao lista->tupla em `restore`, o saque do dia 3 nunca aconteceria.

    JSON devolve `_month` como lista, nao tupla. Se `restore` nao converter de
    volta, `month != self._month` fica sempre True (lista nunca `==` tupla), o
    contador de pregoes do mes reinicia a cada chamada, e a cadencia "3o
    pregao do mes" nunca bate.
    """
    p = _plain(day=3)
    p.on_close(_d("2010-01-04"), 100_000.0)   # sessao 1
    p.on_close(_d("2010-01-05"), 100_000.0)   # sessao 2

    state = json.loads(json.dumps(p.state()))
    assert isinstance(state["_month"], list)  # JSON perdeu o tipo tupla

    fresh = _plain(day=3)
    fresh.restore(state)
    assert isinstance(fresh._month, tuple)    # restore normalizou de volta
    assert fresh._month == (2010, 1)

    pago = fresh.on_close(_d("2010-01-06"), 100_000.0)   # sessao 3 -> paga
    assert pago == pytest.approx(1_000.0)


def test_restart_produz_a_mesma_sequencia_de_saques_que_um_processo_continuo():
    """Uma politica que reinicia no meio do caminho tem de sacar exatamente
    como uma que nunca reiniciou — restaurar estado e transparente."""
    baseline = _plain(day=3, pct=0.01)
    restarted = _plain(day=3, pct=0.01)

    dates = pd.bdate_range("2010-01-04", periods=40)
    baseline_amounts = []
    restarted_amounts = []
    for i, d in enumerate(dates):
        equity = 100_000.0 + i * 500.0
        baseline_amounts.append(baseline.on_close(d, equity))
        if i == 7:
            # "restart": serializa o estado acumulado, descarta a instancia,
            # cria uma nova do zero e reidrata antes de continuar decidindo.
            snap = json.loads(json.dumps(restarted.state()))
            restarted = _plain(day=3, pct=0.01)
            restarted.restore(snap)
        restarted_amounts.append(restarted.on_close(d, equity))

    assert restarted_amounts == pytest.approx(baseline_amounts)
