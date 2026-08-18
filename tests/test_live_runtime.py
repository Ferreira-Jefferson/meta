"""Teste de integracao do supervisor (`live/runtime.py`).

Nao usa `data/raw` real nem a estrategia oficial: constroi um universo
sintetico em `tmp_path` e um robo de investimento SCRIPTADO (decide por data,
nao por preco) para isolar o que se quer provar aqui — a MECANICA do ambiente
(ordem das operacoes, idempotencia, anti-look-ahead, persistencia de estado,
o fluxo de corretora manual) — do comportamento de qualquer estrategia real.
Esse comportamento ja e validado pelo backtest; aqui o alvo e o encanamento.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import pytest

from backtest.withdrawal import FloorSkim
from core.config import BENCHMARK, BacktestConfig
from core.earnings_calendar import is_earnings_blackout
from core.live_models import (
    IntentKind,
    IntentStatus,
    LivePosition,
    OrderSide,
    OrderStatus,
    SessionPhase,
)
from core.models import ExitReason
from journal import live_store as store
from live import clock
from live.broker import Broker, ManualBroker
from live.notify import Notifier
from live.riskguard import CircuitBreaker
from live.runtime import LiveRuntime
from strategy.base import AdjustStop, Enter, Exit, Strategy
from strategy.buy_the_dip import BuyTheDip
from tests.doubles import PaperBroker, ReplayFeed

TICKER = "AAA.SA"


class ScriptedStrategy(Strategy):
    """Estrategia sintetica: as acoes de cada dia vem de um dicionario fixo,
    indexado pela data de DECISAO (o `ctx.session` do fecho), nao pelo preco.
    Deixa o teste 100% deterministico e alheio a qualquer logica de sinal."""

    name = "scripted_test_robot"
    version = "test"

    def __init__(self, script: dict) -> None:
        self.script = script

    def on_bar(self, on_date, open_positions, cash_available):
        return list(self.script.get(pd.Timestamp(on_date), []))


def _sessions(n: int) -> list[date]:
    """`n` pregoes reais consecutivos (usa o calendario de `live.clock`, sem
    hardcodar quais datas do calendario civil sao feriado)."""
    days = clock.sessions_between(date(2030, 1, 1), date(2030, 4, 1))
    assert len(days) >= n
    return days[:n]


def _write_parquet(data_dir, ticker: str, days: list[date], closes: list[float]) -> None:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in days])
    df = pd.DataFrame({
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes,
        "volume": [1_000_000.0] * len(closes),
    }, index=idx)
    safe = ticker.replace("^", "_").replace(".", "_")
    df.to_parquet(data_dir / f"{safe}.parquet")


@pytest.fixture
def universe(tmp_path):
    """8 pregoes reais, AAA.SA + benchmark, com um preco de fecho por dia."""
    days = _sessions(8)
    closes = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    _write_parquet(tmp_path, TICKER, days, closes)
    _write_parquet(tmp_path, BENCHMARK, days, [50_000.0] * len(days))
    return tmp_path, days


def _runtime(tmp_path, days_dir, script, policy=None, db_name="live.sqlite",
            mode="mt5", capital=10_000.0) -> LiveRuntime:
    feed = ReplayFeed()
    broker = ManualBroker() if mode == "manual" else PaperBroker(feed)
    return LiveRuntime(
        account_name="teste",
        strategy=ScriptedStrategy(script),
        policy=policy or FloorSkim(pct=0.5, floor=1e12),  # nunca saca por acidente
        feed=feed, broker=broker, config=BacktestConfig(initial_capital=capital, lot_size=1),
        tickers=(TICKER,), db_path=tmp_path / db_name, data_dir=days_dir,
    )


# ---------- separação física do banco ao vivo (FEAT-000) -------------------

def test_db_path_default_e_live_db_path(tmp_path, monkeypatch):
    """P3 — sem isso, `runtime.py` continuaria importando `DB_PATH` de
    backtest e toda a operação real seguiria gravando no banco compartilhado.

    Correção pós-code-review (E3): a asserção original comparava
    `rt.db_path` contra o caminho REAL de produção (`core.config.LIVE_DB_PATH`)
    ao instanciar um `LiveRuntime` de verdade com `db_path=None` — o teste
    passava, mas o `LiveRuntime` nunca chegava a abrir aquele arquivo (nada
    aqui chama `ensure_account`/`close_and_decide`), então o risco era baixo;
    ainda assim, um teste que referencia o caminho real de produção é frágil
    por princípio (basta alguém adicionar uma chamada que abre a conexão
    para o teste tocar `db/live.sqlite` de verdade). Agora o `DB_PATH` do
    módulo é monkeypatchado para um arquivo em `tmp_path` (mesma convenção de
    `tests/test_dashboard_app.py:46`) ANTES de instanciar o `LiveRuntime`, e
    a comparação usa esse valor — nunca o caminho real."""
    from core.config import LIVE_DB_PATH
    from live import runtime as live_runtime

    # Prova a ligação (import `LIVE_DB_PATH as DB_PATH` em runtime.py) ANTES
    # do monkeypatch, sem instanciar nenhum LiveRuntime apontando pro caminho
    # real.
    assert live_runtime.DB_PATH is LIVE_DB_PATH

    fake_db_path = tmp_path / "live_test.sqlite"
    monkeypatch.setattr(live_runtime, "DB_PATH", fake_db_path)

    # `ManualBroker` (nao `PaperBroker`): este teste e sobre a RESOLUCAO do
    # `db_path` default, nao sobre o tipo de broker — e `PaperBroker` (dublê,
    # `is_test_double = True`) e exatamente o caso que a guarda nova do passo
    # 10 (item 0.3 herdado) passa a recusar quando `db_path` resolve para
    # `DB_PATH` (ver `test_guarda_recusa_test_double_sobre_db_path_producao`
    # abaixo, que herda este cenario original como teste POSITIVO da guarda).
    feed = ReplayFeed()
    broker = ManualBroker()
    rt = LiveRuntime(
        account_name="teste_db_path_default",
        strategy=ScriptedStrategy({}),
        policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=broker,
        config=BacktestConfig(initial_capital=1_000.0, lot_size=1),
        tickers=(TICKER,), db_path=None,
    )
    assert rt.db_path == fake_db_path


# ---------- guarda 0.3 (herdada de FEAT-000): dublê nunca opera sobre o banco
# de producao -----------------------------------------------------------------

def test_guarda_recusa_test_double_sobre_db_path_producao(tmp_path, monkeypatch):
    """Item 0.3 herdado: um broker `is_test_double=True` (ex.: `PaperBroker`)
    nunca pode instanciar um `LiveRuntime` que resolve para o mesmo arquivo de
    `DB_PATH` (o banco de producao) — mesmo se o caminho vier escrito
    diferente (string relativa/absoluta), porque a comparacao e por caminho
    RESOLVIDO, nunca por igualdade crua."""
    from live import runtime as live_runtime

    fake_db_path = tmp_path / "live_producao.sqlite"
    monkeypatch.setattr(live_runtime, "DB_PATH", fake_db_path)

    feed = ReplayFeed()

    # (a) db_path=None cai no DB_PATH monkeypatchado -> recusado.
    with pytest.raises(ValueError):
        LiveRuntime(
            account_name="teste_guarda", strategy=ScriptedStrategy({}),
            policy=FloorSkim(pct=0.5, floor=1e12), feed=feed, broker=PaperBroker(feed),
            config=BacktestConfig(initial_capital=1_000.0, lot_size=1),
            tickers=(TICKER,), db_path=None,
        )

    # (b) mesmo caminho, so que como STRING relativa equivalente -> recusado
    # tambem (prova que a comparacao e por caminho resolvido, nao por
    # igualdade crua de objeto/string).
    import os
    relative_equivalent = os.path.relpath(fake_db_path, start=tmp_path)
    with pytest.raises(ValueError):
        LiveRuntime(
            account_name="teste_guarda", strategy=ScriptedStrategy({}),
            policy=FloorSkim(pct=0.5, floor=1e12), feed=feed, broker=PaperBroker(feed),
            config=BacktestConfig(initial_capital=1_000.0, lot_size=1),
            tickers=(TICKER,), db_path=str(tmp_path / relative_equivalent),
        )

    # (c) broker de PRODUCAO (ManualBroker, is_test_double=False default) sobre
    # o MESMO db_path -> aceito normalmente.
    rt = LiveRuntime(
        account_name="teste_guarda", strategy=ScriptedStrategy({}),
        policy=FloorSkim(pct=0.5, floor=1e12), feed=feed, broker=ManualBroker(),
        config=BacktestConfig(initial_capital=1_000.0, lot_size=1),
        tickers=(TICKER,), db_path=fake_db_path,
    )
    assert rt.db_path == fake_db_path


# ---------- guarda: conta e broker divergentes nunca operam juntos ----------

def test_load_account_recusa_quando_broker_diverge_do_modo_da_conta(tmp_path, universe):
    """Passo 11(a): conta criada com `ManualBroker` (`mode="manual"`); um
    SEGUNDO `LiveRuntime`, sobre o MESMO banco/conta, mas com um broker de
    modo diferente (`PaperBroker`, `mode="mt5"`) tem de recusar operar —
    `close_and_decide`/`status()` levantam `ValueError` em vez de aplicar
    decisao de um robo sobre uma conta que nao e a dele."""
    data_dir, days = universe
    d0 = days[0]
    db_path = tmp_path / "live.sqlite"

    manual_rt = LiveRuntime(
        account_name="teste_divergencia", strategy=ScriptedStrategy({}),
        policy=FloorSkim(pct=0.5, floor=1e12), feed=ReplayFeed(), broker=ManualBroker(),
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=db_path, data_dir=data_dir,
    )
    manual_rt.ensure_account()

    mt5_feed = ReplayFeed()
    mt5_rt = LiveRuntime(
        account_name="teste_divergencia", strategy=ScriptedStrategy({}),
        policy=FloorSkim(pct=0.5, floor=1e12), feed=mt5_feed, broker=PaperBroker(mt5_feed),
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=db_path, data_dir=data_dir,
    )

    with pytest.raises(ValueError):
        mt5_rt.close_and_decide(d0)
    with pytest.raises(ValueError):
        mt5_rt.status()


def test_load_account_ausente_continua_sendo_skip_nao_excecao(tmp_path, universe):
    """Passo 11(b): sobre banco vazio (conta nunca criada), `status()` continua
    devolvendo `{"existe": False}` — a guarda de divergencia NAO pode
    transformar "conta ausente" em excecao, senao os 8 call-sites que dependem
    do ramo `if account is None` (skip limpo) quebrariam."""
    data_dir, days = universe
    db_path = tmp_path / "live_vazio.sqlite"
    feed = ReplayFeed()
    rt = LiveRuntime(
        account_name="conta_nunca_criada", strategy=ScriptedStrategy({}),
        policy=FloorSkim(pct=0.5, floor=1e12), feed=feed, broker=PaperBroker(feed),
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=db_path, data_dir=data_dir,
    )
    status = rt.status()
    assert status == {"conta": "conta_nunca_criada", "existe": False}


# ---------- ciclo completo: decide -> executa -> stop intra-dia ------------

def test_enter_execute_and_intraday_stop(tmp_path, universe):
    data_dir, days = universe
    d0, d1, d2 = days[0], days[1], days[2]

    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script)
    rt.feed.set(TICKER, 100.0)  # preco de execucao da entrada, em d1
    rt.ensure_account()

    decide = rt.close_and_decide(d0)
    assert decide.action == "decide"
    assert decide.detail["intencoes"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc.id, d1)
    assert len(pend) == 1
    intent = pend[0]
    assert intent.decided_on == d0 and intent.execute_on == d1  # D+1, nunca D

    execu = rt.execute_session(d1)
    assert execu.detail["entradas"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert TICKER in acc.positions
    pos = acc.positions[TICKER]
    assert pos.quantity > 0
    assert pos.entry_price > 100.0  # slippage de compra sobe o preco de execucao
    assert acc.cash < 10_000.0

    # stop intra-dia: preco cai abaixo do stop default (15% de config) -> vende
    # na hora, sem esperar o fecho. `now` fica no default (relogio real) para
    # casar com o `ts` que o `ReplayFeed` atribui a cotacao (tambem relogio
    # real, ambos aware em UTC) — nao ha razao de negocio para simular uma
    # data historica aqui, so o preco importa.
    stop_price = pos.current_stop
    assert stop_price is not None
    rt.feed.set(TICKER, stop_price - 1.0)
    tick = rt.intraday_tick(d1)
    assert tick.detail["stops"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert TICKER not in acc.positions
    assert acc.cash > 0


def test_adjust_stop_e_imediato_nao_espera_dplus1(tmp_path, universe):
    """AdjustStop e custo zero: aplica no MESMO fecho, nao no dia seguinte."""
    data_dir, days = universe
    d0 = days[0]
    script = {pd.Timestamp(d0): [AdjustStop(ticker=TICKER, new_stop=42.0)]}
    rt = _runtime(tmp_path, data_dir, script)
    rt.ensure_account()

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        from core.live_models import LivePosition
        acc.positions[TICKER] = LivePosition(
            ticker=TICKER, quantity=100, entry_date=d0, entry_price=50.0,
            capital_allocated=5000.0, current_stop=40.0,
        )
        store.upsert_position(conn, acc.id, acc.positions[TICKER])

    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert acc.positions[TICKER].current_stop == 42.0  # ja moveu, sem D+1


# ---------- idempotencia e anti-look-ahead ---------------------------------

def test_close_and_decide_e_idempotente(tmp_path, universe):
    """Chamar duas vezes para o mesmo pregao nao duplica intencao nem equity."""
    data_dir, days = universe
    d0 = days[0]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script)
    rt.ensure_account()

    r1 = rt.close_and_decide(d0)
    r2 = rt.close_and_decide(d0)
    assert r1.action == "decide"
    assert r2.action == "decide_skip"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc.id, days[1])
        serie = store.equity_series(conn, acc.id)
    assert len(pend) == 1  # nao duplicou
    assert len(serie) == 1  # uma so marcacao de equity para d0


def test_intencao_atrasada_expira_em_vez_de_executar(tmp_path, universe):
    """Se `execute_session` so roda dias depois (maquina fora do ar), a
    intencao velha EXPIRA — nunca executa tarde (regra 7 do AGENTS.md)."""
    data_dir, days = universe
    d0, d1, d3 = days[0], days[1], days[3]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script)
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    rt.close_and_decide(d0)  # decide entrada para d1
    # "maquina caiu": so retoma em d3, bem depois de d1
    result = rt.execute_session(d3)
    assert result.detail["expiradas"] == 1
    assert result.detail["entradas"] == 0

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert TICKER not in acc.positions  # nao comprou tarde
    assert acc.cash == pytest.approx(10_000.0)


# ---------- saque: emissao, execucao, persistencia entre restarts ---------

def test_withdrawal_flui_e_estado_sobrevive_a_restart(tmp_path, universe):
    """A politica de saque decide, o runtime executa, e o estado dela
    (`_pool`, `_paid_month`, etc.) sobrevive a uma instancia NOVA de
    `LiveRuntime` apontando para o mesmo banco — simula um restart do processo."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    # piso baixo: qualquer capital > 100 ja saca 50% no fecho de d0.
    policy = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    script: dict = {}  # nenhuma acao do robo de investimento — so testa saque
    rt = _runtime(tmp_path, data_dir, script, policy=policy, capital=10_000.0)
    rt.ensure_account()

    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc.id, d1)
    assert len(pend) == 1
    assert pend[0].amount == pytest.approx(5_000.0)  # 50% de 10.000

    rt.execute_session(d1)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        saques = store.withdrawals(conn, acc.id)
    assert acc.external_cash == pytest.approx(5_000.0)
    assert acc.withdrawn_total == pytest.approx(5_000.0)
    assert acc.cash == pytest.approx(5_000.0)
    assert len(saques) == 1

    # "restart": nova instancia de LiveRuntime, nova FloorSkim (estado zerado
    # em memoria), mesmo banco. Sem reidratar, a politica achara que "hoje" e
    # o primeiro pregao que ela ve e tentara sacar nao respeitando o mes ja
    # pago em d0 (mesma tupla ano/mes).
    policy2 = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt2 = _runtime(tmp_path, data_dir, script, policy=policy2, capital=10_000.0)
    d2 = days[2]
    r = rt2.close_and_decide(d2)
    assert r.action == "decide"
    with store.live_journal(rt2.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend2 = store.pending_intents(conn, acc.id, days[3])
    # so verifica a garantia real quando d2 cai no mesmo mes civil de d0/d1
    # (nao garantido pelo calendario sintetico de pregoes): o que importa e
    # a politica restaurada NAO re-pagar o mes ja pago.
    if d2.year == d0.year and d2.month == d0.month:
        assert len(pend2) == 0


# ---------- corretora manual: ordem fica no ar, confirmacao aplica depois -

def test_manual_broker_fill_so_aplica_apos_confirmacao(tmp_path, universe):
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script, mode="manual")
    rt.feed.set(TICKER, 100.0)  # cotacao usada so p/ dimensionar o ticket manual
    rt.ensure_account()

    rt.close_and_decide(d0)
    execu = rt.execute_session(d1)
    # ManualBroker nao preenche na hora: a entrada fica pendente, NAO rejeitada.
    assert execu.detail["entradas"] == 0
    assert execu.detail["rejeitadas"] == 0
    assert execu.detail["aguardando"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        executando = store.intents_by_status(conn, acc.id, IntentStatus.EXECUTING)
        abertas = store.open_orders(conn, acc.id)
    assert TICKER not in acc.positions       # efeito NAO aplicado ainda
    assert acc.cash == pytest.approx(10_000.0)
    assert len(executando) == 1
    assert len(abertas) == 1
    order = abertas[0]
    assert order.status == OrderStatus.SENT
    assert "AAA.SA" in order.note           # ticket legivel

    # humano confirma na corretora, fora do processo do supervisor
    rt.broker.confirm(order, filled_qty=order.quantity, avg_price=101.5, fees=3.0)
    with store.live_journal(rt.db_path) as conn:
        store.update_order(conn, order)

    reconcile = rt.reconcile_pending_fills(now=datetime.combine(d1, datetime.min.time()))
    assert reconcile.detail["aplicadas"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert TICKER in acc.positions
    assert acc.positions[TICKER].entry_price == pytest.approx(101.5)
    assert acc.cash == pytest.approx(10_000.0 - (101.5 * order.quantity + 3.0))


def test_run_once_reconcilia_sozinho(tmp_path, universe):
    """`run_once` chama a reconciliacao em toda fase — uma confirmacao manual
    que chegou fora do horario de pregao ainda assim e aplicada."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script, mode="manual")
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()
    rt.close_and_decide(d0)
    rt.execute_session(d1)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        order = store.open_orders(conn, acc.id)[0]
    rt.broker.confirm(order, order.quantity, 99.0, 1.0)
    with store.live_journal(rt.db_path) as conn:
        store.update_order(conn, order)

    # fora do pregao (POST_CLOSE bem depois do after-market) -> `run_once`
    # tambem chamaria `sync_data()` (rede real, `market_data.download`) nessa
    # fase; sem rede no teste, so interessa que a RECONCILIACAO acontece
    # independente da fase — stub o sync para nao tocar rede nem `data/raw`.
    rt.sync_data = lambda: None
    fechado = datetime.combine(d1, datetime.min.time().replace(hour=20))
    passos = rt.run_once(now=fechado)
    assert any(p and p.action == "reconcile" and p.detail.get("aplicadas") == 1 for p in passos)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert TICKER in acc.positions


# ---------- saque que precisa liquidar posicao sob corretora manual --------

def test_saque_manual_liquidacao_fica_pendente_e_completa_apos_confirmacao(tmp_path, universe):
    """Caixa nao cobre o saque, corretora e manual: a liquidacao vira UMA
    ordem de venda pendente (nao um cancelamento) e o saque so fecha quando
    o humano confirma o fill, via `reconcile_pending_fills` — o mesmo
    contrato que ja vale para ENTER/EXIT (`test_manual_broker_fill_so_...`)."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    # piso baixo: pede 90% do equity de 10.000 = 9.000, e o caixa tem so 1.000.
    policy = FloorSkim(pct=0.9, floor=100.0, day=1, min_amount=0.0)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="manual", capital=10_000.0)
    rt.ensure_account()

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        acc.cash = 1_000.0
        pos = LivePosition(ticker=TICKER, quantity=90, entry_date=d0, entry_price=100.0,
                           capital_allocated=9_000.0, current_stop=50.0,
                           max_price_seen=100.0, min_price_seen=100.0)
        store.upsert_position(conn, acc.id, pos)
        store.save_account(conn, acc)

    rt.feed.set(TICKER, 100.0)
    decide = rt.close_and_decide(d0)
    assert decide.action == "decide"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc.id, d1)
    assert len(pend) == 1
    intent = pend[0]
    assert intent.amount == pytest.approx(9_000.0)  # 90% de 10.000 de equity

    execu = rt.execute_session(d1)
    assert execu.detail["saques"] == 0
    assert execu.detail["rejeitadas"] == 0
    assert execu.detail["aguardando"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        executando = store.intents_by_status(conn, acc.id, IntentStatus.EXECUTING)
        abertas = store.open_orders(conn, acc.id)
    assert TICKER in acc.positions            # nada vendido de fato ainda
    assert acc.cash == pytest.approx(1_000.0)  # efeito NAO aplicado
    assert acc.external_cash == pytest.approx(0.0)
    assert len(executando) == 1
    assert executando[0].id == intent.id
    assert executando[0].kind == IntentKind.WITHDRAW
    assert len(abertas) == 1
    order = abertas[0]
    assert order.side == OrderSide.SELL
    assert order.ticker == TICKER
    assert order.status == OrderStatus.SENT

    # humano confirma a venda na corretora, fora do processo do supervisor
    rt.broker.confirm(order, filled_qty=order.quantity, avg_price=100.0, fees=5.0)
    with store.live_journal(rt.db_path) as conn:
        store.update_order(conn, order)

    now = datetime.combine(d1, datetime.min.time().replace(hour=20))
    reconcile = rt.reconcile_pending_fills(now=now)
    assert reconcile.detail["aplicadas"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        executando_depois = store.intents_by_status(conn, acc.id, IntentStatus.EXECUTING)
        done = store.intents_by_status(conn, acc.id, IntentStatus.DONE)
        saques = store.withdrawals(conn, acc.id)
    assert not executando_depois
    assert any(i.id == intent.id for i in done)
    assert acc.external_cash == pytest.approx(9_000.0)
    assert acc.withdrawn_total == pytest.approx(9_000.0)
    # cash final: 1.000 (caixa original) + liquido da venda (100*qtd - 5) - 9.000 sacado
    liquido = 100.0 * order.filled_qty - 5.0
    assert acc.cash == pytest.approx(1_000.0 + liquido - 9_000.0)
    assert len(saques) == 1
    assert saques[0]["liquidated"] == [[TICKER, order.filled_qty, 100.0]]
    assert rt.withdrawal.policy._requested == 0.0  # on_executed rodou e zerou


def test_saque_manual_liquidacao_em_duas_pernas(tmp_path):
    """Uma posicao so nao cobre o saque: a segunda perna so e enviada DEPOIS
    que a primeira confirma (opcao (a) do gap — nunca manda duas ordens de
    uma vez para um humano que ainda nao olhou a primeira)."""
    days = _sessions(8)
    _write_parquet(tmp_path, TICKER, days, [100.0] * len(days))
    _write_parquet(tmp_path, "BBB.SA", days, [50.0] * len(days))
    _write_parquet(tmp_path, BENCHMARK, days, [50_000.0] * len(days))
    d0, d1 = days[0], days[1]

    policy = FloorSkim(pct=1.0, floor=0.0, day=1, min_amount=0.0)  # saca tudo
    feed = ReplayFeed()
    broker = ManualBroker()
    rt = LiveRuntime(
        account_name="teste", strategy=ScriptedStrategy({}), policy=policy,
        feed=feed, broker=broker, config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER, "BBB.SA"), db_path=tmp_path / "live.sqlite", data_dir=tmp_path,
    )
    rt.ensure_account()

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        acc.cash = 0.0
        pos_a = LivePosition(ticker=TICKER, quantity=60, entry_date=d0, entry_price=100.0,
                             capital_allocated=6_000.0, current_stop=50.0,
                             max_price_seen=100.0, min_price_seen=100.0)
        pos_b = LivePosition(ticker="BBB.SA", quantity=80, entry_date=d0, entry_price=50.0,
                             capital_allocated=4_000.0, current_stop=25.0,
                             max_price_seen=50.0, min_price_seen=50.0)
        store.upsert_position(conn, acc.id, pos_a)
        store.upsert_position(conn, acc.id, pos_b)
        store.save_account(conn, acc)

    rt.feed.set(TICKER, 100.0)
    rt.feed.set("BBB.SA", 50.0)
    decide = rt.close_and_decide(d0)
    assert decide.action == "decide"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc.id, d1)
    assert len(pend) == 1
    intent = pend[0]
    assert intent.amount == pytest.approx(10_000.0)  # 100% do equity (0 + 6.000 + 4.000)

    execu = rt.execute_session(d1)
    assert execu.detail["aguardando"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        abertas = store.open_orders(conn, acc.id)
    assert len(abertas) == 1  # so UMA ordem enviada, nunca as duas de saida
    first = abertas[0]
    assert first.ticker == TICKER  # maior posicao (6.000 > 4.000) primeiro
    assert first.quantity == 60    # 6.000 sozinho nao cobre 10.000: vende tudo

    rt.broker.confirm(first, filled_qty=first.quantity, avg_price=100.0, fees=0.0)
    with store.live_journal(rt.db_path) as conn:
        store.update_order(conn, first)

    now = datetime.combine(d1, datetime.min.time().replace(hour=20))
    reconcile1 = rt.reconcile_pending_fills(now=now)
    assert reconcile1.detail["aplicadas"] == 0  # 1a perna resolvida, saque ainda no ar

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        executando = store.intents_by_status(conn, acc.id, IntentStatus.EXECUTING)
        abertas2 = store.open_orders(conn, acc.id)
    assert TICKER not in acc.positions        # AAA liquidada por completo
    assert acc.cash == pytest.approx(6_000.0)  # creditado, mas saque nao fechou
    assert acc.external_cash == pytest.approx(0.0)
    assert len(executando) == 1 and executando[0].id == intent.id
    assert len(abertas2) == 1  # a 2a perna so foi enviada AGORA, apos a 1a confirmar
    second = abertas2[0]
    assert second.ticker == "BBB.SA"
    assert second.quantity == 80  # 4.000 restantes nao cobrem os 4.000 que faltam sem custo zero

    rt.broker.confirm(second, filled_qty=second.quantity, avg_price=50.0, fees=0.0)
    with store.live_journal(rt.db_path) as conn:
        store.update_order(conn, second)

    reconcile2 = rt.reconcile_pending_fills(now=now)
    assert reconcile2.detail["aplicadas"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        executando_depois = store.intents_by_status(conn, acc.id, IntentStatus.EXECUTING)
        saques = store.withdrawals(conn, acc.id)
    assert not executando_depois
    assert "BBB.SA" not in acc.positions
    assert acc.cash == pytest.approx(0.0)
    assert acc.external_cash == pytest.approx(10_000.0)
    assert acc.withdrawn_total == pytest.approx(10_000.0)
    assert len(saques) == 1
    assert saques[0]["liquidated"] == [[TICKER, 60, 100.0], ["BBB.SA", 80, 50.0]]


def test_saque_automatico_com_liquidacao_permanece_sincrono(tmp_path, universe):
    """Regressao: sob corretora automatica (paper/MT5) a liquidacao continua
    acontecendo TODA dentro do mesmo `execute_session` — sem passar por
    `EXECUTING`/`reconcile_pending_fills` — exatamente como antes desta
    mudanca (que so afeta o caminho MANUAL)."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    policy = FloorSkim(pct=0.9, floor=100.0, day=1, min_amount=0.0)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="mt5", capital=10_000.0)
    rt.ensure_account()

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        acc.cash = 1_000.0
        pos = LivePosition(ticker=TICKER, quantity=90, entry_date=d0, entry_price=100.0,
                           capital_allocated=9_000.0, current_stop=50.0,
                           max_price_seen=100.0, min_price_seen=100.0)
        store.upsert_position(conn, acc.id, pos)
        store.save_account(conn, acc)

    rt.feed.set(TICKER, 100.0)
    rt.close_and_decide(d0)
    execu = rt.execute_session(d1)
    assert execu.detail["saques"] == 1
    assert execu.detail["aguardando"] == 0

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        executando = store.intents_by_status(conn, acc.id, IntentStatus.EXECUTING)
        saques = store.withdrawals(conn, acc.id)
    assert not executando  # resolvido na hora, nunca fica pendente
    assert TICKER in acc.positions       # so vendeu o suficiente, nao tudo
    assert acc.positions[TICKER].quantity < 90
    assert acc.external_cash == pytest.approx(9_000.0)
    assert acc.withdrawn_total == pytest.approx(9_000.0)
    assert len(saques) == 1
    assert len(saques[0]["liquidated"]) == 1
    assert saques[0]["liquidated"][0][0] == TICKER


# ---------- regressao: fim-de-mes tem que disparar no ULTIMO dia truncado -

def _pregao_fim_de_mes_limpo() -> date:
    """Acha um pregao real (fora de janela de blackout de resultados) cujo
    PROXIMO pregao real cai num mes diferente — a condicao exata que
    `core.calendar.is_month_end` precisa enxergar. Busca a partir de um ano
    fixo e futuro para o teste ser deterministico entre execucoes."""
    d = date(2028, 1, 2)
    for _ in range(800):
        nxt = clock.next_session(d)
        if nxt.month != d.month and not is_earnings_blackout(d):
            return d
        d = nxt
    raise AssertionError("nao achou fim de mes limpo em 800 pregoes — calendario mudou?")


def test_fim_de_mes_dispara_no_ultimo_dia_disponivel(tmp_path):
    """Furo real corrigido em `LiveRuntime._load`: `core.calendar.is_month_end`
    decide "isto e fim de mes" comparando com a data SEGUINTE no indice. Um
    painel truncado exatamente em `session` (a realidade ao vivo — nao ha
    amanha ainda) nunca conseguia confirmar isso, entao um robo cujo sinal so
    age em fim de mes (`strategy.buy_the_dip.BuyTheDip`, usado por toda a
    familia dip/hysteresis/portfolio) NUNCA decidia nada ao vivo. Descoberto
    rodando `scripts/run_live_sim.py` contra dado historico real e comparando
    com o backtest oficial da mesma janela (0 entradas no simulador contra 1
    no backtest). Este teste prova a correcao com a estrategia REAL, nao uma
    scriptada, para nao voltar a quebrar silenciosamente."""
    session = _pregao_fim_de_mes_limpo()
    dias = pd.bdate_range(end=pd.Timestamp(session), periods=300)
    assert dias[-1] == pd.Timestamp(session)

    n = len(dias)
    # AAA sobe firme por quase todo o periodo (momentum 12-1 forte e positivo),
    # depois cai ~7% nos ultimos 10 pregoes antes de `session` — dip claro,
    # acima do `dip_pct` default (3%) de BuyTheDip.
    aaa = [100.0 + i * 0.7 for i in range(n)]
    peak = aaa[n - 11]
    for i in range(n - 10, n):
        aaa[i] = peak * 0.93
    # BBB fica parado: momentum ~0, nunca supera AAA no ranking (top_n=1).
    bbb = [50.0] * n

    data_dir = tmp_path / "dados"
    data_dir.mkdir()
    _write_parquet(data_dir, "AAA.SA", [d.date() for d in dias], aaa)
    _write_parquet(data_dir, "BBB.SA", [d.date() for d in dias], bbb)
    _write_parquet(data_dir, BENCHMARK, [d.date() for d in dias], [50_000.0] * n)

    strategy = BuyTheDip(top_n=1, dip_pct=0.03, high_window=20,
                        selic_path=str(tmp_path / "selic_inexistente.parquet"))
    feed = ReplayFeed()
    rt = LiveRuntime(
        account_name="teste", strategy=strategy, policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=PaperBroker(feed), config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=("AAA.SA", "BBB.SA"), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt.ensure_account()

    result = rt.close_and_decide(session)
    assert result.action == "decide"
    assert result.detail["intencoes"] >= 1, "fim de mes nao foi detectado — o furo voltou"

    execute_on = clock.next_session(session)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc.id, execute_on)
    entradas = [i for i in pend if i.kind == IntentKind.ENTER]
    assert any(i.ticker == "AAA.SA" for i in entradas), (
        f"esperava ENTER em AAA.SA para {execute_on}, intencoes gravadas: {pend}"
    )


# ---------- integracao: disjuntor de risco e notificador -------------------

class _RecordingNotifier(Notifier):
    """Fake em memoria — grava toda chamada para o teste inspecionar."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def notify(self, level, source, message, payload=None) -> None:
        self.calls.append((level, source, message, payload))


def test_disjuntor_veta_entrada_nova_mas_nao_saida(tmp_path, universe):
    """CircuitBreaker acionado: `close_and_decide` filtra ENTER do robo de
    investimento — reduzir risco nunca e bloqueado (ver docstring de
    `CircuitBreaker`), so abrir posicao nova."""
    data_dir, days = universe
    d0 = days[0]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    guard = CircuitBreaker(daily_loss_pct=0.01, monthly_loss_pct=0.01)
    notifier = _RecordingNotifier()
    rt = _runtime(tmp_path, data_dir, script)
    rt.risk_guard = guard
    rt.notifier = notifier
    rt.ensure_account()

    # Forca o disjuntor a acionar: observa uma perda diaria grande antes de decidir.
    guard.observe(d0, 100_000.0)
    guard.observe(d0, 90_000.0)  # mesmo dia, perda de 10% > limite de 1%
    assert guard.is_frozen

    result = rt.close_and_decide(d0)
    assert result.action == "decide"
    assert result.detail["intencoes"] == 0, "ENTER deveria ter sido vetado pelo disjuntor"
    assert any(c[1] == "riskguard" for c in notifier.calls), "disjuntor deveria notificar o veto"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc.id, days[1])
    assert not any(i.kind == IntentKind.ENTER for i in pend)


def test_disjuntor_bloqueia_entrada_tambem_na_execucao(tmp_path, universe):
    """Defesa em profundidade: mesmo se uma ENTER ja gravada (antes do
    disjuntor acionar) chegar em `execute_session`, ela e cancelada, nao
    executada."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script)
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    rt.close_and_decide(d0)  # disjuntor ainda livre: intencao ENTER gravada normalmente
    guard = CircuitBreaker(daily_loss_pct=0.01, monthly_loss_pct=0.01)
    guard.observe(d1, 100_000.0)
    guard.observe(d1, 90_000.0)
    assert guard.is_frozen
    rt.risk_guard = guard

    result = rt.execute_session(d1)
    assert result.detail["entradas"] == 0
    assert result.detail["rejeitadas"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert TICKER not in acc.positions


def test_notifier_dispara_junto_com_o_log_do_fecho(tmp_path, universe):
    """`_log` grava em `live_events` E chama o notifier no mesmo ponto —
    nao ha como um evento existir num lugar sem existir no outro."""
    data_dir, days = universe
    d0 = days[0]
    notifier = _RecordingNotifier()
    rt = _runtime(tmp_path, data_dir, {})
    rt.notifier = notifier
    rt.ensure_account()

    rt.close_and_decide(d0)

    assert len(notifier.calls) >= 1
    assert any("fecho" in c[2] for c in notifier.calls)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos = store.recent_events(conn, acc.id)
    assert len(eventos) >= 1


# ---------- deposito externo (aporte) ---------------------------------------

class _FakeCashBroker(Broker):
    """Broker minimo, so para exercitar `reconcile_broker_cash` — `place`/
    `poll` nunca sao chamados nestes testes (nenhum deles executa ordem)."""

    name = "fakecash"
    mode = "mt5"

    def __init__(self, cash: Optional[float]) -> None:
        self._cash = cash

    def place(self, order):
        raise NotImplementedError

    def poll(self, order):
        raise NotImplementedError

    def cash_balance(self) -> Optional[float]:
        return self._cash


def _cash_runtime(tmp_path, data_dir, broker, capital=10_000.0) -> LiveRuntime:
    return LiveRuntime(
        account_name="teste", strategy=ScriptedStrategy({}), policy=FloorSkim(pct=0.5, floor=1e12),
        feed=ReplayFeed(), broker=broker, config=BacktestConfig(initial_capital=capital, lot_size=1),
        tickers=(TICKER,), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )


def test_reconcile_broker_cash_credita_deposito_e_e_idempotente(tmp_path, universe):
    """Saldo real 500 acima do esperado -> credita exatamente 500, grava UMA
    linha em `live_deposits`; chamar de novo com o MESMO saldo real (agora
    que o caixa ja alcancou ele) nao credita de novo nem duplica a linha."""
    data_dir, days = universe
    broker = _FakeCashBroker(10_500.0)
    rt = _cash_runtime(tmp_path, data_dir, broker)
    rt.ensure_account()

    report = rt.reconcile_broker_cash(now=datetime(2026, 8, 18, 9, 0))
    assert report.action == "reconcile_cash"
    assert report.detail["deposito"] == pytest.approx(500.0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (acc.id,)
        ).fetchall()
    assert acc.cash == pytest.approx(10_500.0)
    assert len(rows) == 1
    assert rows[0]["origin"] == "mt5_reconciliation"
    assert rows[0]["amount"] == pytest.approx(500.0)

    report2 = rt.reconcile_broker_cash(now=datetime(2026, 8, 18, 9, 1))
    assert report2.action == "reconcile_cash"
    assert report2.detail.get("deposito") is None  # diff ~0 agora: no-op

    with store.live_journal(rt.db_path) as conn:
        acc2 = store.load_account(conn, "teste")
        rows2 = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (acc2.id,)
        ).fetchall()
    assert acc2.cash == pytest.approx(10_500.0)
    assert len(rows2) == 1  # nao duplicou


def test_reconcile_broker_cash_sem_saldo_externo_e_no_op_silencioso(tmp_path, universe):
    """`PaperBroker` nao sobrescreve `cash_balance` -> herda o `None` do
    default de `Broker`: skip limpo, sem log (senao spamaria todo dia)."""
    data_dir, days = universe
    feed = ReplayFeed()
    rt = LiveRuntime(
        account_name="teste", strategy=ScriptedStrategy({}), policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=PaperBroker(feed), config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt.ensure_account()

    report = rt.reconcile_broker_cash()
    assert report.action == "reconcile_cash_skip"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (acc.id,)
        ).fetchall()
        eventos = store.recent_events(conn, acc.id)
    assert acc.cash == pytest.approx(10_000.0)
    assert rows == []
    assert eventos == []


def test_reconcile_broker_cash_encolhimento_nao_ajusta_so_avisa(tmp_path, universe):
    """Saldo real ABAIXO do esperado: fora do escopo pedido (so deposito que
    faz a conta crescer) — nao mexe no caixa, so loga um aviso."""
    data_dir, days = universe
    broker = _FakeCashBroker(9_950.0)  # 50 a menos que o esperado
    rt = _cash_runtime(tmp_path, data_dir, broker)
    rt.ensure_account()

    report = rt.reconcile_broker_cash()
    assert report.action == "reconcile_cash"
    assert report.detail["diferenca"] == pytest.approx(-50.0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (acc.id,)
        ).fetchall()
        eventos = store.recent_events(conn, acc.id)
    assert acc.cash == pytest.approx(10_000.0)  # nao ajustou sozinho
    assert rows == []
    assert any(e["level"] == "warn" for e in eventos)


def test_run_once_aciona_reconcile_broker_cash_no_pre_open(tmp_path, universe):
    """`run_once` chamado dentro do PRE_OPEN de um dia de pregao invoca
    `reconcile_broker_cash` — o unico jeito do aporte automatico acontecer
    sem alguem rodar o passo na mao."""
    data_dir, days = universe
    d0 = days[0]
    broker = _FakeCashBroker(10_300.0)
    rt = _cash_runtime(tmp_path, data_dir, broker)
    rt.ensure_account()
    rt.sync_data = lambda: None  # sem rede no teste, so por precaucao

    open_dt = datetime.combine(d0, clock.session_open(d0))
    pre_open_now = open_dt - timedelta(minutes=5)
    assert clock.phase(pre_open_now) == SessionPhase.PRE_OPEN  # premissa do teste

    passos = rt.run_once(now=pre_open_now)
    assert any(
        p.action == "reconcile_cash" and p.detail.get("deposito") == pytest.approx(300.0)
        for p in passos
    )

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert acc.cash == pytest.approx(10_300.0)
