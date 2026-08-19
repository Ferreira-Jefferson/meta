"""Teste de integracao do supervisor (`live/runtime.py`).

Nao usa `data/raw` real nem a estrategia oficial: constroi um universo
sintetico em `tmp_path` e um robo de investimento SCRIPTADO (decide por data,
nao por preco) para isolar o que se quer provar aqui — a MECANICA do ambiente
(ordem das operacoes, idempotencia, anti-look-ahead, persistencia de estado,
o fluxo de corretora manual) — do comportamento de qualquer estrategia real.
Esse comportamento ja e validado pelo backtest; aqui o alvo e o encanamento.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
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
from live.notify import NullNotifier, Notifier
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


def _pregao_e_pregao_do_mes_seguinte() -> tuple[date, date]:
    """Dois pregoes reais em meses civis DIFERENTES, derivados do calendario
    de `live.clock` -- nao um mes fixo hardcodado a mao: `d0` e o primeiro
    pregao da janela, `d1` e o primeiro pregao subsequente cujo (ano, mes) ja
    e outro. Usado pelos testes de expiracao mensal da recomendacao de
    saque, que precisam de duas sessoes em meses civis diferentes sem
    depender da data em que o teste roda."""
    dias = clock.sessions_between(date(2030, 1, 1), date(2030, 6, 1))
    d0 = dias[0]
    d1 = next(d for d in dias if (d.year, d.month) != (d0.year, d0.month))
    return d0, d1


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


# ---------- FEAT-004: stop nunca sobre dado velho, nunca duplica -----------

def test_stop_intraday_suprimido_sobre_cotacao_velha(tmp_path, universe):
    """Item 4.2: um stop cuja cotacao esta ATRASADA (acima de
    `max_quote_age`) nunca pode disparar — suprime (nao vende) e notifica
    como `error`, em vez de executar sobre dado que pode estar completamente
    errado."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    notifier = _RecordingNotifier()
    rt = _runtime(tmp_path, data_dir, script)
    rt.notifier = notifier
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    rt.close_and_decide(d0)
    rt.execute_session(d1)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    stop_price = acc.positions[TICKER].current_stop
    assert stop_price is not None

    # cotacao abaixo do stop, MAS velha (10.000s atras) -> nao pode disparar.
    old_ts = datetime.now(timezone.utc) - timedelta(seconds=10_000)
    rt.feed.set(TICKER, stop_price - 1.0, ts=old_ts)

    tick = rt.intraday_tick(d1)
    assert tick.detail["stops"] == 0

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert TICKER in acc.positions  # posicao NAO foi vendida

    eventos_error = [c for c in notifier.calls if c[0] == "error"]
    assert eventos_error, "stop sobre cotacao velha deveria notificar como error"


def test_stop_intraday_nao_duplica_ordem_sob_corretora_manual(tmp_path, universe):
    """Item 4.3: sob `ManualBroker`, a ordem de venda fica `SENT` sem
    confirmar — 5 chamadas SEGUIDAS de `intraday_tick` sobre o MESMO tick
    nao podem gerar 5 ordens de venda, so 1."""
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
        buy_order = store.open_orders(conn, acc.id)[0]
    rt.broker.confirm(buy_order, buy_order.quantity, 101.5, 1.0)
    with store.live_journal(rt.db_path) as conn:
        store.update_order(conn, buy_order)
    rt.reconcile_pending_fills(now=datetime.combine(d1, datetime.min.time()))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    stop_price = acc.positions[TICKER].current_stop
    assert stop_price is not None

    rt.feed.set(TICKER, stop_price - 1.0)
    for _ in range(5):
        rt.intraday_tick(d1)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        abertas = [o for o in store.open_orders(conn, acc.id) if o.side == OrderSide.SELL]
    assert len(abertas) == 1, "5 ticks geraram mais de 1 ordem de venda"
    assert TICKER in acc.positions  # posicao ainda aberta (fill nao confirmado)


def test_saida_de_fecho_nao_duplica_ordem_com_stop_ja_em_voo(tmp_path, universe):
    """Correcao SUBSTANTIVA do plan-reviewer (§6 item 1): um stop intra-dia
    de ONTEM ainda `SENT` (nao confirmado, posicao continua aberta) nao pode
    ser duplicado quando o robo decide sair de novo no FECHO seguinte por
    OUTRO motivo (aqui, rotacao scriptada) — a trava de `intraday_tick`
    (`exit_em_andamento`) so cobre repeticao do MESMO `on_intraday`; esta
    trava vive em `_sell` (chamado por `execute_session` E `intraday_tick`),
    que veta ANTES de `_place` quando ja existe ordem de venda aberta para o
    mesmo ticker."""
    data_dir, days = universe
    d0, d1, d2 = days[0], days[1], days[2]
    script = {
        pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)],
        pd.Timestamp(d1): [Exit(ticker=TICKER, reason=ExitReason.ROTATION_OUT)],
    }
    rt = _runtime(tmp_path, data_dir, script, mode="manual")
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    rt.close_and_decide(d0)
    rt.execute_session(d1)  # compra -- ManualBroker deixa SENT; confirma na mao
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        buy_order = store.open_orders(conn, acc.id)[0]
    rt.broker.confirm(buy_order, buy_order.quantity, 101.5, 1.0)
    with store.live_journal(rt.db_path) as conn:
        store.update_order(conn, buy_order)
    rt.reconcile_pending_fills(now=datetime.combine(d1, datetime.min.time()))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    stop_price = acc.positions[TICKER].current_stop
    assert stop_price is not None

    # stop dispara intra-dia em d1, sob ManualBroker: ordem SENT, sem
    # confirmar -- posicao continua aberta (premissa 4 do plano).
    rt.feed.set(TICKER, stop_price - 1.0)
    tick = rt.intraday_tick(d1)
    assert tick.detail["stops"] == 0  # ManualBroker nao preenche na hora

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        abertas_apos_stop = [o for o in store.open_orders(conn, acc.id) if o.side == OrderSide.SELL]
    assert len(abertas_apos_stop) == 1
    assert TICKER in acc.positions  # posicao AINDA aberta (fill nao confirmado)

    # fecho de d1: o robo decide EXIT de novo por OUTRO motivo (rotacao) --
    # ele nao enxerga ordem em voo, so `account.positions` (regra 6).
    rt.close_and_decide(d1)
    execu = rt.execute_session(d2)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        abertas_depois = [o for o in store.open_orders(conn, acc.id) if o.side == OrderSide.SELL]
    assert len(abertas_depois) == 1, "venda duplicada -- a 2a saida deveria ter sido recusada"
    assert execu.detail["rejeitadas"] >= 1


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

def test_withdrawal_flui_e_estado_sobrevive_a_restart(tmp_path):
    """A politica de saque decide (recomendacao), a confirmacao humana move
    o dinheiro, e o estado da politica (`_pool`, `_paid_month`, etc.)
    sobrevive a uma instancia NOVA de `LiveRuntime` apontando para o mesmo
    banco — simula um restart do processo.

    Datas FIXADAS pelo proprio teste (defeito apontado no Lote 5 do plano
    original): em vez de confiar que `days[2]` do calendario sintetico caia
    no mesmo mes civil de `days[0]`/`days[1]` (as vezes nao caia, e a
    asserção da garantia real ficava condicional/pulada), filtra os pregoes
    reais para um bloco garantidamente dentro do MESMO mes civil."""
    dias_candidatos = clock.sessions_between(date(2030, 1, 1), date(2030, 6, 1))
    mesmo_mes = [d for d in dias_candidatos
                 if (d.year, d.month) == (dias_candidatos[0].year, dias_candidatos[0].month)]
    assert len(mesmo_mes) >= 3  # premissa do teste: mes com pregoes suficientes
    d0, d1, d2 = mesmo_mes[0], mesmo_mes[1], mesmo_mes[2]

    data_dir = tmp_path / "dados"
    data_dir.mkdir()
    _write_parquet(data_dir, TICKER, dias_candidatos[:20], [100.0] * 20)
    _write_parquet(data_dir, BENCHMARK, dias_candidatos[:20], [50_000.0] * 20)

    # piso baixo: qualquer capital > 100 ja recomenda sacar 50% no fecho de d0.
    policy = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, capital=10_000.0)
    rt.ensure_account()

    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend) == 1
    intent = pend[0]
    assert intent.amount == pytest.approx(5_000.0)  # 50% de 10.000

    # confirmacao humana move o dinheiro -- nunca execute_session/_withdraw.
    report = rt.confirm_withdrawal(5_000.0, session=d1, intent_id=intent.id)
    assert report.action == "withdraw_confirm"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        saques = store.withdrawals(conn, acc.id)
    assert acc.external_cash == pytest.approx(5_000.0)
    assert acc.withdrawn_total == pytest.approx(5_000.0)
    assert acc.cash == pytest.approx(5_000.0)
    assert len(saques) == 1

    # "restart": nova instancia de LiveRuntime, nova FloorSkim (estado zerado
    # em memoria), mesmo banco. Sem reidratar, a politica achara que "hoje" e
    # o primeiro pregao que ela ve e recomendaria sacar de novo, nao
    # respeitando o mes ja pago em d0 (mesma tupla ano/mes).
    policy2 = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt2 = _runtime(tmp_path, data_dir, {}, policy=policy2, capital=10_000.0)
    r = rt2.close_and_decide(d2)
    assert r.action == "decide"
    with store.live_journal(rt2.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend2 = store.pending_withdraw_intents(conn, acc.id)
    # d2 e mesmo mes civil de d0/d1 por construcao (nao condicional): a
    # politica restaurada NAO re-recomenda o mes ja pago.
    assert pend2 == []


# ---------- reconcile_pending_fills nao pode apagar o estado da politica --

def test_reconcile_pending_fills_nao_apaga_estado_da_politica_de_saque(tmp_path, universe):
    """Passo 5 (RED antes de GREEN, hipotese nº1 do plan-reviewer):
    `reconcile_pending_fills` grava `account.policy_state = self._robot_state()`
    no fim do metodo, FORA do laco de intents EXECUTING -- roda mesmo sem
    nenhuma intent pendente. Sem restaurar o estado da politica ANTES (mesmo
    padrao ja documentado em `unfreeze()`), um `LiveRuntime` NOVO (processo
    recem-iniciado, como um `step` de cron ou um restart) sobrescreve
    `policy_state["withdrawal"]` com uma `FloorSkim` VIRGEM -- apagando
    `_paid_month`/`_pool` gravados por uma decisao anterior."""
    data_dir, days = universe
    d0 = days[0]
    policy = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, capital=10_000.0)
    rt.ensure_account()

    # Decide um saque em d0 (fecho) -- isso grava `_paid_month`/`_pool` nao
    # triviais no `policy_state` persistido (via `_robot_state()`).
    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    estado_gravado = acc.policy_state["withdrawal"]
    assert estado_gravado.get("_paid_month") is not None  # premissa do teste

    # "processo novo": LiveRuntime recem-instanciado, FloorSkim em memoria
    # ainda VIRGEM (nunca viu o `_paid_month` gravado acima). Nenhuma intent
    # EXECUTING existe -- o cenario e so "reconciliar" sem nada pendente,
    # como um `step` de cron faria apos um restart.
    policy2 = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt2 = _runtime(tmp_path, data_dir, {}, policy=policy2, capital=10_000.0)

    rt2.reconcile_pending_fills()

    with store.live_journal(rt2.db_path) as conn:
        acc2 = store.load_account(conn, "teste")
    assert acc2.policy_state["withdrawal"] == estado_gravado


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


def test_saque_recomendado_nao_move_caixa_nem_gera_ordem(tmp_path, universe):
    """Passo 8 (RED antes de GREEN): uma recomendacao de saque (kind=WITHDRAW,
    PENDING, gerada por `close_and_decide`) NUNCA mais e executada por
    `execute_session` -- nem debita caixa, nem gera `Order`, mesmo quando
    precisaria liquidar posicao para cobrir o valor pedido (o comportamento
    antigo liquidava a posicao sozinho e movia o caixa)."""
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
    decide = rt.close_and_decide(d0)
    assert decide.action == "decide"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend) == 1  # a politica recomendou o saque

    execu = rt.execute_session(d1)
    assert execu.detail.get("recomendacoes_saque", 0) == 0  # essa e a programada (D+1), nao a de liquidez

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        abertas = store.open_orders(conn, acc.id)
        pend_depois = store.pending_withdraw_intents(conn, acc.id)
    assert acc.cash == pytest.approx(1_000.0)          # caixa intocado
    assert TICKER in acc.positions
    assert acc.positions[TICKER].quantity == 90        # posicao intocada
    assert abertas == []                                # nenhuma ordem gerada
    assert len(pend_depois) == 1                        # recomendacao continua PENDING


def test_recomendacao_de_saque_por_liquidez_e_gravada_sem_matar_o_supervisor(tmp_path, universe):
    """Passo 8 (RED antes de GREEN, achado nº2 do plan-reviewer): uma venda
    credita caixa na mesma barra e o evento de liquidez da politica devolve
    valor > 0 -- `execute_session` tem de gravar a recomendacao (kind=WITHDRAW,
    execute_on == decided_on) e retornar normalmente, sem `ValueError` de
    look-ahead e sem executar nada (o caixa creditado pela venda fica
    intacto, a espera de confirmacao humana)."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    # day=2 (nunca bate com a 1a sessao do mes que o teste ve): garante que
    # `on_close` nao paga sozinho, isolando o evento de liquidez como a UNICA
    # fonte da recomendacao neste teste.
    policy = FloorSkim(pct=0.9, floor=100.0, day=2, min_amount=0.0)
    script = {pd.Timestamp(d0): [Exit(ticker=TICKER, reason=ExitReason.ROTATION_OUT)]}
    rt = _runtime(tmp_path, data_dir, script, policy=policy, mode="mt5", capital=10_000.0)
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
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend) == 0  # day=2 nao bateu -- nenhuma recomendacao programada

    execu = rt.execute_session(d1)  # nao pode levantar ValueError
    assert execu.detail["saidas"] == 1
    assert execu.detail.get("recomendacoes_saque", 0) == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend_saque = store.pending_withdraw_intents(conn, acc.id)
    assert TICKER not in acc.positions       # venda aplicada normalmente
    assert acc.cash > 1_000.0                # caixa creditado pela venda, saque NAO debitou nada
    assert len(pend_saque) == 1
    assert pend_saque[0].execute_on == d1    # mesma barra, nao D+1
    assert pend_saque[0].decided_on == d1


# ---------- confirmacao humana do saque (confirm_withdrawal) ---------------

def _runtime_com_recomendacao(tmp_path, data_dir, amount: float = 5_000.0, capital: float = 10_000.0):
    """Monta um `LiveRuntime` com uma recomendacao de saque PENDING ja
    gravada (via `close_and_decide` real, floor baixo o suficiente para
    pagar `amount` no fecho do 1o pregao)."""
    policy = FloorSkim(pct=amount / capital, floor=100.0, day=1, min_amount=0.0)
    days = _sessions(3)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="manual", capital=capital)
    rt.ensure_account()
    rt.close_and_decide(days[0])
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend) == 1
    return rt, pend[0], days


def test_confirm_withdrawal_debita_caixa_credita_externo_e_fecha_intent(tmp_path, universe):
    data_dir, _days = universe
    rt, intent, days = _runtime_com_recomendacao(tmp_path, data_dir, amount=5_000.0, capital=10_000.0)

    report = rt.confirm_withdrawal(4_800.0, session=days[1])
    assert report.action == "withdraw_confirm"
    assert report.detail["intent_id"] == intent.id
    assert report.detail["recomendado"] == pytest.approx(5_000.0)
    assert report.detail["confirmado"] == pytest.approx(4_800.0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        saques = store.withdrawals(conn, acc.id)
        pend_depois = store.pending_withdraw_intents(conn, acc.id)
    assert acc.cash == pytest.approx(10_000.0 - 4_800.0)
    assert acc.external_cash == pytest.approx(4_800.0)
    assert acc.withdrawn_total == pytest.approx(4_800.0)
    assert pend_depois == []
    assert len(saques) == 1
    assert saques[0]["requested"] == pytest.approx(5_000.0)
    assert saques[0]["executed"] == pytest.approx(4_800.0)


def test_confirm_withdrawal_sem_recomendacao_pendente_rejeita_sem_mexer_no_caixa(tmp_path, universe):
    data_dir, days = universe
    rt = _runtime(tmp_path, data_dir, {}, mode="manual", capital=10_000.0)
    rt.ensure_account()

    report = rt.confirm_withdrawal(1_000.0, session=days[0])
    assert report.action == "withdraw_reject"
    assert "recomendação" in report.detail["motivo"] or "pendente" in report.detail["motivo"]

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert acc.cash == pytest.approx(10_000.0)


def test_confirm_withdrawal_duas_vezes_debita_uma_so_vez(tmp_path, universe):
    """RED antes de GREEN (hipotese nº5 do plan-reviewer): a mesma
    recomendacao confirmada duas vezes NUNCA debita duas vezes -- a 2a
    chamada tem de perder a corrida do `claim_intent` e devolver
    `withdraw_reject`, com o caixa identico ao que a 1a chamada deixou."""
    data_dir, _days = universe
    rt, intent, days = _runtime_com_recomendacao(tmp_path, data_dir, amount=5_000.0, capital=10_000.0)

    r1 = rt.confirm_withdrawal(5_000.0, session=days[1], intent_id=intent.id)
    assert r1.action == "withdraw_confirm"
    with store.live_journal(rt.db_path) as conn:
        acc_apos_1 = store.load_account(conn, "teste")
    cash_apos_1 = acc_apos_1.cash

    r2 = rt.confirm_withdrawal(5_000.0, session=days[1], intent_id=intent.id)
    assert r2.action == "withdraw_reject"

    with store.live_journal(rt.db_path) as conn:
        acc_apos_2 = store.load_account(conn, "teste")
    assert acc_apos_2.cash == pytest.approx(cash_apos_1)  # nao debitou de novo


def test_confirm_withdrawal_valor_menor_devolve_falta_a_fila_e_maior_nao_devolve(tmp_path, universe):
    data_dir, _days = universe
    rt, intent, days = _runtime_com_recomendacao(tmp_path, data_dir, amount=5_000.0, capital=10_000.0)
    pool_antes = rt.withdrawal.policy._pool

    rt.confirm_withdrawal(3_000.0, session=days[1], intent_id=intent.id)
    assert rt.withdrawal.policy._pool == pytest.approx(pool_antes + 2_000.0)  # falta volta a fila

    # nova recomendacao/rodada independente para o caso "confirma mais que o pedido"
    rt2, intent2, days2 = _runtime_com_recomendacao(tmp_path / "outro", data_dir, amount=5_000.0, capital=10_000.0)
    pool_antes2 = rt2.withdrawal.policy._pool
    rt2.confirm_withdrawal(6_000.0, session=days2[1], intent_id=intent2.id)
    assert rt2.withdrawal.policy._pool == pytest.approx(pool_antes2)  # nao devolve nada


def test_confirm_withdrawal_funciona_com_disjuntor_acionado(tmp_path, universe):
    """`CircuitBreaker` so veta ENTER (premissa 17) -- confirmar saque nao e
    afetado mesmo com o disjuntor congelado."""
    data_dir, _days = universe
    rt, intent, days = _runtime_com_recomendacao(tmp_path, data_dir, amount=5_000.0, capital=10_000.0)
    guard = CircuitBreaker(daily_loss_pct=0.01, monthly_loss_pct=0.01)
    guard.observe(days[1], 100_000.0)
    guard.observe(days[1], 90_000.0)
    assert guard.is_frozen
    rt.risk_guard = guard

    report = rt.confirm_withdrawal(5_000.0, session=days[1], intent_id=intent.id)
    assert report.action == "withdraw_confirm"


def test_confirm_withdrawal_acima_do_caixa_debita_mesmo_assim_e_avisa(tmp_path, universe):
    """Decisao do usuario (§5 do plano): sem clamp, sem rejeicao -- o caixa
    fica negativo e um evento `warn` e gravado; `reconcile_broker_cash` e
    quem aponta a divergencia real depois, nao esta confirmacao."""
    data_dir, _days = universe
    rt, intent, days = _runtime_com_recomendacao(tmp_path, data_dir, amount=5_000.0, capital=10_000.0)

    report = rt.confirm_withdrawal(50_000.0, session=days[1], intent_id=intent.id)
    assert report.action == "withdraw_confirm"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos = store.recent_events(conn, acc.id)
    assert acc.cash < 0
    assert any(e["level"] == "warn" and "negativ" in e["message"] for e in eventos)


# ---------- expiracao mensal da recomendacao de saque -----------------------

def test_saque_expira_na_virada_do_mes_e_devolve_valor_a_fila(tmp_path):
    """Recomendacao PENDING decidida no fecho do mes 1, nunca confirmada: um
    pregao de abertura ja no mes civil seguinte (`execute_session`, que roda
    `_expire_withdraw_advice` antes de qualquer venda/compra -- ver passo 8
    do plano) expira a recomendacao e devolve o valor para a fila da
    politica -- tanto no objeto em memoria (`rt.withdrawal.policy`) quanto
    no `policy_state` persistido no BANCO (nao so o objeto Python)."""
    d0, d1 = _pregao_e_pregao_do_mes_seguinte()
    dias_dado = clock.sessions_between(date(2030, 1, 1), date(2030, 6, 1))

    data_dir = tmp_path / "dados"
    data_dir.mkdir()
    _write_parquet(data_dir, TICKER, dias_dado, [100.0] * len(dias_dado))
    _write_parquet(data_dir, BENCHMARK, dias_dado, [50_000.0] * len(dias_dado))

    policy = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="manual", capital=10_000.0)
    rt.ensure_account()

    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend) == 1
    intent = pend[0]
    assert intent.amount == pytest.approx(5_000.0)

    execu = rt.execute_session(d1)
    assert execu.detail["saques_expirados"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc_depois = store.load_account(conn, "teste")
        pend_depois = store.pending_withdraw_intents(conn, acc_depois.id)
    assert pend_depois == []  # expirou, nao ficou pendente

    withdrawal_state = acc_depois.policy_state["withdrawal"]
    assert withdrawal_state["_pool"] == pytest.approx(5_000.0)      # valor voltou pra fila
    assert withdrawal_state["_requested"] == pytest.approx(0.0)


def test_recomendacao_de_saque_gera_evento_warn_notificado(tmp_path, universe):
    """A decisao de uma recomendacao de saque (`close_and_decide`, primeira
    vez que ela e decidida) tem de notificar de verdade -- antes desta
    feature a decisao gravava o evento mas nao chamava o notificador."""
    data_dir, days = universe
    d0 = days[0]
    notifier = _RecordingNotifier()
    policy = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="manual", capital=10_000.0)
    rt.notifier = notifier
    rt.ensure_account()

    result = rt.close_and_decide(d0)
    assert result.action == "decide"

    saque_calls = [c for c in notifier.calls if c[1] == "saque"]
    assert len(saque_calls) == 1
    level, source, message, payload = saque_calls[0]
    assert level == "warn"
    assert payload is not None
    assert payload.get("valor") == pytest.approx(5_000.0)


def test_confirm_withdrawal_expira_recomendacao_vencida_e_persiste_policy_state(tmp_path):
    """Reproducao exata da issue 1 do code-review: uma recomendacao PENDING
    do mes 1, nunca confirmada; tentar confirma-la ja no mes civil seguinte
    expira a recomendacao POR DENTRO de `confirm_withdrawal`
    (`_expire_withdraw_advice` roda antes de escolher a recomendacao, logo
    `pendentes` fica vazia e a chamada rejeita). O FURO era: o evento/return
    diziam "valor volta pra fila", mas sem persistir `account.policy_state`
    antes do `return StepReport(\"withdraw_reject\", ...)`, o BANCO ficava
    com o `_requested` antigo -- o dinheiro sumia da fila em silencio."""
    d0, d1 = _pregao_e_pregao_do_mes_seguinte()
    dias_dado = clock.sessions_between(date(2030, 1, 1), date(2030, 6, 1))

    data_dir = tmp_path / "dados"
    data_dir.mkdir()
    _write_parquet(data_dir, TICKER, dias_dado, [100.0] * len(dias_dado))
    _write_parquet(data_dir, BENCHMARK, dias_dado, [50_000.0] * len(dias_dado))

    policy = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="manual", capital=10_000.0)
    rt.ensure_account()

    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend) == 1
    intent = pend[0]
    assert intent.amount == pytest.approx(5_000.0)

    report = rt.confirm_withdrawal(5_000.0, session=d1, intent_id=intent.id)
    assert report.action == "withdraw_reject"  # a recomendacao ja tinha vencido

    with store.live_journal(rt.db_path) as conn:
        acc_depois = store.load_account(conn, "teste")
        intents_depois = store.pending_withdraw_intents(conn, acc_depois.id)
    assert intents_depois == []

    # Sem a correcao, o banco ficaria com `_requested == 5000.0` (o valor
    # antigo) e `_pool == 0.0` -- exatamente o furo apontado pelo revisor.
    withdrawal_state = acc_depois.policy_state["withdrawal"]
    assert withdrawal_state["_requested"] == pytest.approx(0.0)
    assert withdrawal_state["_pool"] == pytest.approx(5_000.0)


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


# ---------- status(): recomendacao de saque visivel o mes inteiro ----------

def test_status_mostra_recomendacao_de_saque_pendente_varios_dias_depois(tmp_path, universe):
    """Passo 11: uma recomendacao de saque decidida ha varios dias continua
    aparecendo em `status()["intencoes_pendentes"]` (ao contrario de
    ENTER/EXIT, que so aparecem no pregao seguinte) -- e cada item traz `id`
    nao-nulo, necessario para a UI vincular a confirmacao a uma recomendacao
    especifica."""
    data_dir, days = universe
    d0 = days[0]
    policy = FloorSkim(pct=0.5, floor=100.0, day=1, min_amount=0.0)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="manual", capital=10_000.0)
    rt.ensure_account()
    rt.close_and_decide(d0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend) == 1
    intent_id = pend[0].id

    # "muitos dias depois": status() sem nenhum pregao adicional decidido,
    # so avancando o relogio real (session_date usa datetime.now por
    # default) -- a recomendacao continua PENDING no banco independente da
    # data de "hoje" do sistema, entao ja e suficiente checar que ela
    # aparece mesmo sem ser "o pregao seguinte a decisao".
    status = rt.status()
    saques_no_status = [i for i in status["intencoes_pendentes"] if i["tipo"] == "withdraw"]
    assert len(saques_no_status) == 1
    assert saques_no_status[0]["id"] == intent_id
    assert saques_no_status[0]["id"] is not None


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


def test_reconcile_broker_cash_nunca_credita_so_avisa_pra_mais_ou_pra_menos(tmp_path, universe):
    """Achado nº2 da revisao original: `reconcile_broker_cash` e um detector
    PURO -- diferenca POSITIVA (saldo real 500 acima do esperado) NUNCA mais
    credita `account.cash` sozinha (antes disso inflava o patrimonio a cada
    saque confirmado direto na corretora MT5, sem ninguem ter aportado nada).
    So loga `warn`; `live_deposits` continua vazia; chamar de novo com o
    MESMO saldo real e idempotente (novo evento, mesmo nao-efeito)."""
    data_dir, days = universe
    broker = _FakeCashBroker(10_500.0)
    rt = _cash_runtime(tmp_path, data_dir, broker)
    rt.ensure_account()

    report = rt.reconcile_broker_cash(now=datetime(2026, 8, 18, 9, 0))
    assert report.action == "reconcile_cash"
    assert report.detail["diferenca"] == pytest.approx(500.0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (acc.id,)
        ).fetchall()
        eventos = store.recent_events(conn, acc.id)
    assert acc.cash == pytest.approx(10_000.0)  # NUNCA creditado sozinho
    assert rows == []
    assert any(e["level"] == "warn" for e in eventos)

    report2 = rt.reconcile_broker_cash(now=datetime(2026, 8, 18, 9, 1))
    assert report2.action == "reconcile_cash"
    assert report2.detail["diferenca"] == pytest.approx(500.0)  # continua avisando

    with store.live_journal(rt.db_path) as conn:
        acc2 = store.load_account(conn, "teste")
        rows2 = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (acc2.id,)
        ).fetchall()
    assert acc2.cash == pytest.approx(10_000.0)
    assert rows2 == []


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
    `reconcile_broker_cash` — o unico jeito da divergencia de caixa ser
    detectada sem alguem rodar o passo na mao. Deteccao NUNCA credita
    sozinha: `acc.cash` continua o mesmo, so o evento de aviso e gerado."""
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
        p.action == "reconcile_cash" and p.detail.get("diferenca") == pytest.approx(300.0)
        for p in passos
    )

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert acc.cash == pytest.approx(10_000.0)  # nao creditado sozinho


# ---------- FEAT-003: Strategy.state()/restore() e lista branca ------------

def test_strategy_state_e_lista_branca_json_segura():
    """Passo 1/2 (RED antes de GREEN): `Strategy.state()`/`restore()` sao
    genericos sobre `_stateful_keys` (lista branca), NUNCA `vars(self)` cru
    -- `BuyTheDip` guarda `_scores`/`_dist_from_high` (`dict[str, pd.Series]`),
    que quebrariam `json.dumps`. `restore()` tambem coage o tipo pelo default
    da classe (achado C2): uma string `"false"` persistida vira `bool False`,
    nao a string truthy."""
    strat = BuyTheDip()
    snapshot = strat.state()
    assert snapshot == {"_pending_rebalance": False}
    json.dumps(snapshot)  # nao pode levantar -- so o essencial esta na lista branca

    strat2 = BuyTheDip()
    strat2.restore({"_pending_rebalance": True})
    assert strat2._pending_rebalance is True

    # achado C2: coercao de tipo pelo default -- "false" e truthy em Python.
    strat3 = BuyTheDip()
    strat3.restore({"_pending_rebalance": "false"})
    assert strat3._pending_rebalance is False

    # chave fora da lista branca e ignorada silenciosamente.
    strat4 = BuyTheDip()
    strat4.restore({"_scores": {"AAA.SA": [1, 2, 3]}})
    assert strat4._scores == {}


# ---------- FEAT-003: item 3.2 -- estado da estrategia sobrevive a restart -

def _pregao_fim_de_mes_em_blackout() -> date:
    """Espelha `_pregao_fim_de_mes_limpo()`, mas para o cenario OPOSTO: um
    fim de mes que CAI dentro do blackout de resultados e cujo pregao
    seguinte esta FORA do blackout -- a terceira clausula e obrigatoria
    (premissa 7): o robo so EXECUTA a rotacao adiada num pregao fora de
    blackout; sem ela o teste veria um segundo adiamento, nao uma execucao,
    e viraria falso-negativo silencioso."""
    d = date(2028, 1, 2)
    for _ in range(800):
        nxt = clock.next_session(d)
        if nxt.month != d.month and is_earnings_blackout(d) and not is_earnings_blackout(nxt):
            return d
        d = nxt
    raise AssertionError("nao achou fim de mes em blackout em 800 pregoes -- calendario mudou?")


def _painel_dip_para(tmp_path, ultimo_dia: date, tickers_extra: tuple[str, ...] = ("BBB.SA",)):
    """Painel sintetico com dip claro em AAA.SA (favorito do ranking top_n=1
    de `BuyTheDip`) cobrindo `ultimo_dia`. Mesma receita de
    `test_fim_de_mes_dispara_no_ultimo_dia_disponivel`."""
    dias = pd.bdate_range(end=pd.Timestamp(ultimo_dia), periods=301)
    n = len(dias)
    aaa = [100.0 + i * 0.7 for i in range(n)]
    peak = aaa[n - 11]
    for i in range(n - 10, n):
        aaa[i] = peak * 0.93
    data_dir = tmp_path / "dados"
    data_dir.mkdir(exist_ok=True)
    _write_parquet(data_dir, "AAA.SA", [d.date() for d in dias], aaa)
    for extra in tickers_extra:
        _write_parquet(data_dir, extra, [d.date() for d in dias], [50.0] * n)
    _write_parquet(data_dir, BENCHMARK, [d.date() for d in dias], [50_000.0] * n)
    return data_dir


def test_pending_rebalance_de_marco_sobrevive_a_restart_do_processo(tmp_path):
    """Passo 4 (RED antes de GREEN, item 3.2 do plano original): um restart
    do processo durante o blackout de marco nao pode apagar o adiamento
    (`_pending_rebalance`) da campeã -- hoje `InvestmentRobot.state()`
    devolve `{}` sempre, entao a rotacao adiada se perde em silencio, e o
    mes inteiro de marco nunca roda a rotacao que deveria ter sido adiada
    para abril."""
    session = _pregao_fim_de_mes_em_blackout()
    proximo = clock.next_session(session)
    data_dir = _painel_dip_para(tmp_path, proximo)

    def _nova_estrategia():
        return BuyTheDip(top_n=1, dip_pct=0.03, high_window=20,
                         selic_path=str(tmp_path / "selic_inexistente.parquet"))

    feed1 = ReplayFeed()
    rt1 = LiveRuntime(
        account_name="teste", strategy=_nova_estrategia(), policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed1, broker=PaperBroker(feed1), config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=("AAA.SA", "BBB.SA"), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt1.ensure_account()

    result1 = rt1.close_and_decide(session)
    assert result1.action == "decide"
    assert result1.detail["intencoes"] == 0, "fim de mes em blackout deveria ADIAR, nao decidir"

    # "restart": processo NOVO, BuyTheDip NOVA (_pending_rebalance=False por
    # construcao), mesmo banco.
    feed2 = ReplayFeed()
    rt2 = LiveRuntime(
        account_name="teste", strategy=_nova_estrategia(), policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed2, broker=PaperBroker(feed2), config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=("AAA.SA", "BBB.SA"), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )

    result2 = rt2.close_and_decide(proximo)
    assert result2.action == "decide"
    assert result2.detail["intencoes"] >= 1, (
        "_pending_rebalance nao sobreviveu ao restart -- rotacao de marco perdida"
    )


def test_estado_de_outro_robo_e_descartado_no_restore(tmp_path, universe):
    """Passo 4 (RED antes de GREEN, achado C4): `policy_state["investment"]`
    tem de carregar a CHAVE do robo (`self.investment.key`). Se o `robot`
    gravado divergir do robo atual, o estado NAO pode ser herdado -- senao
    uma troca de estrategia (ou uma conta reapontada por engano) importaria
    o `_pending_rebalance` de um robo completamente diferente."""
    data_dir, days = universe
    strat = BuyTheDip()   # key == "buy_the_dip" -- tem `_pending_rebalance` de verdade
    feed = ReplayFeed()
    rt = LiveRuntime(
        account_name="teste", strategy=strat, policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=PaperBroker(feed), config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt.ensure_account()

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        acc.policy_state = {
            **acc.policy_state,
            "investment": {"robot": "outro_robo_completamente_diferente",
                          "state": {"_pending_rebalance": True}},
        }
        store.save_account(conn, acc)
        acc_recarregada = store.load_account(conn, "teste")

    rt._restore_robot_state(acc_recarregada.policy_state)

    assert strat._pending_rebalance is False, (
        "estado de outro robo foi herdado -- carimbo da chave nao esta sendo checado"
    )


# ---------- FEAT-003: item 3.1 -- disjuntor diario usa a base certa --------

def test_disjuntor_diario_usa_patrimonio_do_fecho_anterior_como_base(tmp_path, universe):
    """Passo 8 (RED antes de GREEN, achado/item 3.1 do plano original): antes
    da correcao, `close_and_decide` observava o disjuntor com o patrimonio do
    PROPRIO dia sendo decidido -- a base do dia so e fixada no primeiro
    `observe()`, com o MESMO valor passado nessa chamada, entao a perda
    calculada e sempre 0% nesse (unico) contato do dia. A correcao usa o
    patrimonio do FECHO ANTERIOR como base de comparacao."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d1): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script, capital=10_000.0)
    rt.ensure_account()

    r0 = rt.close_and_decide(d0)
    assert r0.action == "decide"
    assert r0.detail["equity"] == pytest.approx(10_000.0)

    # simula perda REAL entre os dois fechos (crash intra-dia nao observado
    # ainda, ou qualquer outro efeito que consuma caixa) -- grava direto no
    # banco, fora do fluxo normal do supervisor.
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        acc.cash = 5_000.0   # metade do patrimonio evaporou
        store.save_account(conn, acc)

    guard = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.99)
    rt.risk_guard = guard

    result = rt.close_and_decide(d1)
    assert result.action == "decide"
    assert guard.is_frozen is True, (
        "disjuntor deveria ter usado o patrimonio do FECHO ANTERIOR (10.000) "
        "como base, nao o do proprio dia (5.000) -- perda de -50% > limite de 5%"
    )
    assert result.detail["intencoes"] == 0, "ENTER deveria ter sido vetado pelo disjuntor"


def test_disjuntor_recusa_base_do_fecho_anterior_velha_ou_zerada(tmp_path, universe):
    """Passo 8(a) (RED antes de GREEN, achados A2/A4): `_previous_close_patrimonio`
    so aceita a linha do fecho IMEDIATAMENTE anterior (`clock.previous_session`),
    e so se o valor for `> 0`. Sem o limite de idade, uma base de dias atras
    transformaria deriva normal em "perda do dia"; sem o piso `> 0`, uma base
    zerada desligaria as DUAS travas em silencio (`CircuitBreaker.observe` so
    avalia perda quando a base e `> 0`)."""
    data_dir, days = universe
    d0 = days[0]
    d5 = days[5]
    rt = _runtime(tmp_path, data_dir, {}, capital=10_000.0)
    rt.ensure_account()

    with store.live_journal(rt.db_path) as conn:
        account = store.load_account(conn, "teste")

        # (a) linha de 5 pregoes atras -- velha demais para servir de base
        # do fecho ANTERIOR de d5 (que e `clock.previous_session(d5)`, nao d0).
        store.record_equity(conn, account.id, d0, cash=10_000.0, invested=0.0,
                            equity=10_000.0, external_cash=0.0)
        base_a = rt._previous_close_patrimonio(conn, account.id, d5)
        assert base_a is None, "base velha (5 pregoes atras) deveria ser recusada"

        # (b) linha do fecho IMEDIATAMENTE anterior, mas patrimonio = 0.0.
        anterior = clock.previous_session(d5)
        store.record_equity(conn, account.id, anterior, cash=0.0, invested=0.0,
                            equity=0.0, external_cash=0.0)
        base_b = rt._previous_close_patrimonio(conn, account.id, d5)
        assert base_b is None, "base zerada deveria ser recusada (desligaria as duas travas)"

        # controle: mesma data, valor > 0 -> aceita.
        store.record_equity(conn, account.id, anterior, cash=8_000.0, invested=0.0,
                            equity=8_000.0, external_cash=0.0)
        base_ok = rt._previous_close_patrimonio(conn, account.id, d5)
        assert base_ok == pytest.approx(8_000.0)


# ---------- FEAT-003: item 3.1 -- disjuntor intra-dia ----------------------

def test_disjuntor_dispara_em_crash_intradia_e_estado_sobrevive_a_restart(tmp_path, universe):
    """Passo 9 (RED antes de GREEN, item 3.1 e achado B1): `intraday_tick`
    hoje NAO chama `observe()` -- um crash intra-dia que se recupera ate o
    fecho nunca e visto pelo disjuntor. E o congelamento acionado por
    `intraday_tick` tem de PERSISTIR: um `LiveRuntime` novo (restart) que
    restaura o estado ve o disjuntor travado."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    rt = _runtime(tmp_path, data_dir, {}, capital=10_000.0)
    guard = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.99)
    rt.risk_guard = guard
    rt.ensure_account()

    r0 = rt.close_and_decide(d0)
    assert r0.action == "decide"
    assert guard.is_frozen is False   # premissa

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        acc.cash = 5_000.0    # "crash" intra-dia: metade do patrimonio evapora
        store.save_account(conn, acc)

    rt.intraday_tick(d1)
    assert guard.is_frozen is True, "intraday_tick deveria ter observado o disjuntor e travado"

    # a mutacao tem de sobreviver a um restart do processo: rt2 e um
    # LiveRuntime NOVO, CircuitBreaker NOVO em memoria, mesmo banco.
    # `reconcile_pending_fills` (metodo publico) ja restaura o estado dos
    # robos antes de rodar.
    rt2 = _runtime(tmp_path, data_dir, {}, capital=10_000.0)
    rt2.risk_guard = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.99)
    rt2.reconcile_pending_fills()
    assert rt2.risk_guard.is_frozen is True, "congelamento de intraday_tick nao persistiu"


def test_intraday_tick_carrega_paineis_antes_de_observar_o_disjuntor(tmp_path, universe):
    """Passo 9(a) (RED antes de GREEN, achado B1): `intraday_tick` chamado
    isoladamente (sem `execute_session` antes -- processo recem-reiniciado)
    tem de carregar os paineis (`_load`) ANTES de observar o disjuntor. Sem
    isso, `self._panels` fica vazio, `_marks()` devolve `{}`, e
    `AccountState.invested` cai no fallback `marks.get(t, p.entry_price)` --
    uma posicao em LUCRO passaria a valer o preco de ENTRADA, lendo como
    perda instantanea e travando o disjuntor por engano (e agora essa trava
    fantasma seria PERSISTIDA)."""
    data_dir, days = universe   # AAA.SA fecha a 100.0 em todos os 8 pregoes
    d0, d1 = days[0], days[1]

    rt = _runtime(tmp_path, data_dir, {}, capital=10_000.0)
    rt.ensure_account()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        acc.cash = 1_000.0
        pos = LivePosition(ticker=TICKER, quantity=90, entry_date=d0, entry_price=50.0,
                           capital_allocated=4_500.0, current_stop=None,
                           max_price_seen=100.0, min_price_seen=100.0)
        store.upsert_position(conn, acc.id, pos)
        # base do fecho anterior: patrimonio real com a posicao marcada a
        # mercado (100.0) = 1.000 (cash) + 90*100 (posicao) = 10.000.
        store.record_equity(conn, acc.id, d0, cash=1_000.0, invested=9_000.0,
                            equity=10_000.0, external_cash=0.0)
        store.save_account(conn, acc)

    # runtime NOVO (processo recem-reiniciado): nunca chamou `_load`/
    # `execute_session`. NENHUMA cotacao intra-dia definida para o ticker --
    # forca `_intraday_marks` a depender de `_marks()` (que precisa de
    # `self._panels` carregado).
    feed2 = ReplayFeed()
    rt2 = LiveRuntime(
        account_name="teste", strategy=ScriptedStrategy({}), policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed2, broker=PaperBroker(feed2), config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=rt.db_path, data_dir=data_dir,
    )
    rt2.risk_guard = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.99)

    rt2.intraday_tick(d1)

    assert rt2.risk_guard.is_frozen is False, (
        "posicao em lucro foi lida como perda -- paineis nao foram carregados "
        "antes de observar o disjuntor"
    )


def test_unfreeze_durante_o_pregao_nao_recongela_no_tick_seguinte(tmp_path, universe, monkeypatch):
    """Passo 6/7/9 (RED antes de GREEN, item F2): sem re-ancorar as bases no
    momento do destravamento, o TICK SEGUINTE recalcula a mesma perda contra
    a mesma base antiga e recongela em segundos -- o botao de panico
    documentado vira inoperante durante o pregao."""
    from live import clock as live_clock
    from live import runtime as live_runtime
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    # Reproduz a fase OPEN de verdade: `clock.session_date()` devolve o
    # pregao ANTERIOR (`d0`, ja que `d0 == clock.previous_session(d1)` por
    # `_sessions` gerar dias consecutivos) -- e' assim que o sistema ja
    # funciona hoje durante o pregao, nao e' bug novo. `unfreeze()` usa
    # `session_date()` so' para CARREGAR dados (`_load`/`_intraday_marks`);
    # ja `intraday_tick(d1, ...)` abaixo usa a data de HOJE (`d1`), a mesma
    # divergencia D-1 x D que `run_once` produz de verdade. Monkeypatchar
    # `session_date` para devolver `d1` (o MESMO pregao passado a
    # `intraday_tick`) apagaria essa divergencia e o teste passaria mesmo
    # com o codigo quebrado -- exatamente o furo que este teste existe para
    # pegar.
    monkeypatch.setattr(live_clock, "session_date", lambda *a, **k: d0)

    # `unfreeze()` ancora o argumento de `risk_guard.unfreeze(...)` em
    # `datetime.now(timezone.utc).date()` -- a MESMA expressao que
    # `run_once` usa para decidir a `session` passada a `intraday_tick`.
    # Trava o "agora" real do processo em `d1` (o dia em que o tick roda),
    # separado de `session_date()` acima (travado em `d0`, o ultimo pregao
    # FECHADO): sem isso o teste mediria a re-ancoragem contra a data real
    # do sistema rodando a suite (nunca `d1`), e a asserçao final falharia
    # por um motivo estranho ao bug (dessincronia de calendario do teste,
    # nao o F2 que este teste existe para pegar).
    class _RelogioRealEmD1:
        @staticmethod
        def now(tz=None):
            return datetime(d1.year, d1.month, d1.day, 12, 0, tzinfo=tz)

    monkeypatch.setattr(live_runtime, "datetime", _RelogioRealEmD1)

    rt = _runtime(tmp_path, data_dir, {}, capital=10_000.0)
    guard = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.99)
    rt.risk_guard = guard
    rt.ensure_account()

    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        acc.cash = 5_000.0   # crash: metade do patrimonio evapora
        store.save_account(conn, acc)

    rt.intraday_tick(d1)
    assert guard.is_frozen is True   # premissa do teste

    rt.unfreeze()   # humano revisou -- patrimonio ainda deprimido (5.000)
    assert guard.is_frozen is False   # premissa: destravou

    rt.intraday_tick(d1)   # tick seguinte, MESMO patrimonio deprimido
    assert guard.is_frozen is False, (
        "unfreeze() nao re-ancorou -- o tick seguinte recongelou contra a mesma base antiga"
    )


# ---------- FEAT-003: item 3.3 -- skip por dado incompleto e visivel -------

def _universe_com_lacuna(tmp_path, dias_completos, ticker_incompleto: str, dia_faltando: date):
    """Painel onde `ticker_incompleto` NAO tem barra em `dia_faltando` --
    fura `data_is_ready` de proposito, para exercitar o skip."""
    data_dir = tmp_path / "dados"
    data_dir.mkdir(exist_ok=True)
    outro = "AAA.SA" if ticker_incompleto != "AAA.SA" else "BBB.SA"
    _write_parquet(data_dir, outro, dias_completos, [100.0] * len(dias_completos))
    dias_incompleto = [d for d in dias_completos if d != dia_faltando]
    _write_parquet(data_dir, ticker_incompleto, dias_incompleto, [50.0] * len(dias_incompleto))
    _write_parquet(data_dir, BENCHMARK, dias_completos, [50_000.0] * len(dias_completos))
    return data_dir


def test_skip_por_dado_incompleto_notifica_uma_vez_e_escala_no_fim_de_mes(tmp_path):
    """Passo 10 (RED antes de GREEN, achado E2, item 3.3): o skip por dado
    incompleto hoje NAO grava evento nem notifica -- se o pregao pulado for
    o ultimo do mes, a rotacao nao e adiada, e PERDIDA, em silencio. A
    correcao grava + notifica, com DEDUPE por (sessao, faltantes) -- uma
    vez, nao a cada chamada -- e escala para `error` em fim de mes."""
    dias = _sessions(10)
    d0 = dias[0]
    data_dir = _universe_com_lacuna(tmp_path, dias, "BBB.SA", d0)
    notifier = _RecordingNotifier()
    feed = ReplayFeed()
    rt = LiveRuntime(
        account_name="teste", strategy=ScriptedStrategy({}), policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=PaperBroker(feed), config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=("AAA.SA", "BBB.SA"), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt.notifier = notifier
    rt.ensure_account()

    # (a) pregao comum: hoje NENHUM evento e gravado e o notifier NAO e
    # chamado -- depois da correcao, 1 evento warn + 1 notificacao.
    r1 = rt.close_and_decide(d0)
    assert r1.action == "decide_skip"
    assert r1.detail["motivo"] == "dado incompleto"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos = [e for e in store.recent_events(conn, acc.id) if e["source"] == "runtime"]
    assert len(eventos) == 1
    assert eventos[0]["level"] == "warn"
    assert len(notifier.calls) == 1

    # (b) 3 chamadas SEGUIDAS do MESMO pregao -> continua 1 evento, 1 notificacao.
    rt.close_and_decide(d0)
    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos2 = [e for e in store.recent_events(conn, acc.id) if e["source"] == "runtime"]
    assert len(eventos2) == 1
    assert len(notifier.calls) == 1

    # gap-flapping: a lista de faltantes MUDA (BBB.SA passa a ter o dado,
    # AAA.SA perde) -- dispara um evento NOVO, o marcador (sessao, faltantes)
    # e diferente do anterior.
    _write_parquet(data_dir, "BBB.SA", dias, [50.0] * len(dias))
    aaa_sem_d0 = [d for d in dias if d != d0]
    _write_parquet(data_dir, "AAA.SA", aaa_sem_d0, [100.0] * len(aaa_sem_d0))
    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos3 = [e for e in store.recent_events(conn, acc.id) if e["source"] == "runtime"]
    assert len(eventos3) == 2
    assert len(notifier.calls) == 2

    # (c) fim de mes com dado incompleto -> nivel error, nao warn.
    d_fim = _pregao_fim_de_mes_limpo()
    dias_fim = [d.date() for d in pd.bdate_range(end=pd.Timestamp(d_fim), periods=5)]
    data_dir2 = tmp_path / "dados_fim"
    data_dir2.mkdir()
    _write_parquet(data_dir2, "AAA.SA", dias_fim, [100.0] * len(dias_fim))
    dias_fim_bbb = [d for d in dias_fim if d != d_fim]
    _write_parquet(data_dir2, "BBB.SA", dias_fim_bbb, [50.0] * len(dias_fim_bbb))
    _write_parquet(data_dir2, BENCHMARK, dias_fim, [50_000.0] * len(dias_fim))

    notifier2 = _RecordingNotifier()
    feed2 = ReplayFeed()
    rt2 = LiveRuntime(
        account_name="teste2", strategy=ScriptedStrategy({}), policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed2, broker=PaperBroker(feed2), config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=("AAA.SA", "BBB.SA"), db_path=tmp_path / "live2.sqlite", data_dir=data_dir2,
    )
    rt2.notifier = notifier2
    rt2.ensure_account()

    result_fim = rt2.close_and_decide(d_fim)
    assert result_fim.action == "decide_skip"
    assert result_fim.detail.get("fim_de_mes") is True
    with store.live_journal(rt2.db_path) as conn:
        acc2 = store.load_account(conn, "teste2")
        eventos_fim = [e for e in store.recent_events(conn, acc2.id) if e["source"] == "runtime"]
    assert len(eventos_fim) == 1
    assert eventos_fim[0]["level"] == "error"


def test_skip_por_dado_incompleto_nao_dispara_apos_sessao_ja_decidida(tmp_path, universe):
    """Passo 10 (RED antes de GREEN, achado E3): a checagem de idempotencia
    ("ja decidido") tem de rodar ANTES de `data_is_ready`. Sem essa ordem, o
    gap-flapping conhecido do yfinance (o parquet perde retroativamente a
    barra do dia entre um download e outro) dispararia um `error` de
    "rotacao pode ter sido PERDIDA" para uma rotacao que JA aconteceu com
    sucesso, so porque o dado sumiu DEPOIS."""
    data_dir, days = universe
    d0 = days[0]
    notifier = _RecordingNotifier()
    rt = _runtime(tmp_path, data_dir, {}, capital=10_000.0)
    rt.notifier = notifier
    rt.ensure_account()

    r1 = rt.close_and_decide(d0)
    assert r1.action == "decide"

    # gap-flapping: a barra de d0 some do parquet DEPOIS de ja ter sido
    # decidida com sucesso.
    _write_parquet(data_dir, TICKER, days[1:], [100.0] * (len(days) - 1))

    r2 = rt.close_and_decide(d0)
    assert r2.detail["motivo"] == "ja decidido"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos = [e for e in store.recent_events(conn, acc.id)
                  if e["level"] in ("warn", "error") and e["source"] == "runtime"]
    assert eventos == []


# ---------- FEAT-003: status() expoe pregoes pendentes e o notificador ----

def test_status_lista_todos_os_pregoes_sem_decisao_e_o_notificador(tmp_path, universe, monkeypatch):
    """Passo 11 (RED antes de GREEN, achado E4/E7): `status()` hoje so mostra
    o pregao de REFERENCIA (a sessao atual), nao a lista de TODOS os pregoes
    sem decisao -- um pregao perdido ficaria visivel por menos de 24h. Passa
    a expor `decisao_pendente` (lista completa) e `notificador` (canal em
    uso, achado E7)."""
    from live import clock as live_clock
    data_dir, days = universe
    d0, d1, d2 = days[0], days[1], days[2]
    rt = _runtime(tmp_path, data_dir, {}, capital=10_000.0)
    rt.ensure_account()

    monkeypatch.setattr(live_clock, "session_date", lambda *a, **k: d0)
    status0 = rt.status()
    assert status0["decisao_pendente"] == [d0.isoformat()]
    assert status0["notificador"] == "NullNotifier"

    rt.close_and_decide(d0)
    status1 = rt.status()
    assert status1["decisao_pendente"] == []

    # d1 e d2 pulados (nunca decididos) -- `session_date` agora aponta para
    # d2: hoje so d2 apareceria (visivel por menos de 24h); a lista completa
    # tem que trazer os DOIS.
    monkeypatch.setattr(live_clock, "session_date", lambda *a, **k: d2)
    status2 = rt.status()
    assert status2["decisao_pendente"] == [d1.isoformat(), d2.isoformat()]
