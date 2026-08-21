"""Teste de integracao do supervisor (`live/runtime.py`).

Nao usa `data/raw` real nem a estrategia oficial: constroi um universo
sintetico em `tmp_path` e um robo de investimento SCRIPTADO (decide por data,
nao por preco) para isolar o que se quer provar aqui — a MECANICA do ambiente
(ordem das operacoes, idempotencia, anti-look-ahead, persistencia de estado) —
do comportamento de qualquer estrategia real. Esse comportamento ja e
validado pelo backtest; aqui o alvo e o encanamento.
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
from live.broker import Broker
from live.notify import NullNotifier
from live.riskguard import CircuitBreaker
from live.runtime import LiveRuntime
from strategy.base import AdjustStop, Enter, Exit
from strategy.buy_the_dip import BuyTheDip
from tests.doubles import PaperBroker, ReplayFeed, ScriptedStrategy, _RecordingNotifier

TICKER = "AAA.SA"


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
            mode="mt5", capital=10_000.0, strategy=None) -> LiveRuntime:
    assert mode == "mt5"  # unico modo que existe — parametro mantido so pra nao reescrever os call-sites
    feed = ReplayFeed()
    broker = PaperBroker(feed)
    # `strategy` explicito quando o teste precisa OBSERVAR a estrategia (contar
    # chamadas de `on_bar`); `None` mantem o default scriptado dos demais.
    return LiveRuntime(
        account_name="teste",
        strategy=strategy or ScriptedStrategy(script),
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

    # `MT5Broker` (nao `PaperBroker`): este teste e sobre a RESOLUCAO do
    # `db_path` default, nao sobre o tipo de broker — e `PaperBroker` (dublê,
    # `is_test_double = True`) e exatamente o caso que a guarda nova do passo
    # 10 (item 0.3 herdado) passa a recusar quando `db_path` resolve para
    # `DB_PATH` (ver `test_guarda_recusa_test_double_sobre_db_path_producao`
    # abaixo, que herda este cenario original como teste POSITIVO da guarda).
    # `MT5Broker()` sem mock: o construtor nao toca no pacote `MetaTrader5`
    # (import lazy, so dentro de metodo — ver `live/broker_mt5.py`), e nenhum
    # metodo que precisaria dele e chamado aqui.
    from live.broker_mt5 import MT5Broker

    feed = ReplayFeed()
    broker = MT5Broker()
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

    # (c) broker de PRODUCAO (MT5Broker, is_test_double=False default) sobre
    # o MESMO db_path -> aceito normalmente.
    from live.broker_mt5 import MT5Broker

    rt = LiveRuntime(
        account_name="teste_guarda", strategy=ScriptedStrategy({}),
        policy=FloorSkim(pct=0.5, floor=1e12), feed=feed, broker=MT5Broker(),
        config=BacktestConfig(initial_capital=1_000.0, lot_size=1),
        tickers=(TICKER,), db_path=fake_db_path,
    )
    assert rt.db_path == fake_db_path


# ---------- guarda: conta e broker divergentes nunca operam juntos ----------

def test_load_account_recusa_quando_broker_diverge_do_modo_da_conta(tmp_path, universe):
    """Passo 11(a): conta criada com um broker `mode="mt5"` (vocabulario real);
    um SEGUNDO `LiveRuntime`, sobre o MESMO banco/conta, mas com um broker cujo
    `.mode` foi forcado para um valor diferente do gravado (dublê de teste,
    `.mode` sobrescrito na instancia — nunca precisa ser um segundo modo REAL,
    so precisa divergir do que esta no banco) tem de recusar operar —
    `close_and_decide`/`status()` levantam `ValueError` em vez de aplicar
    decisao de um robo sobre uma conta que nao e a dele."""
    data_dir, days = universe
    d0 = days[0]
    db_path = tmp_path / "live.sqlite"

    real_feed = ReplayFeed()
    real_rt = LiveRuntime(
        account_name="teste_divergencia", strategy=ScriptedStrategy({}),
        policy=FloorSkim(pct=0.5, floor=1e12), feed=real_feed, broker=PaperBroker(real_feed),
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=db_path, data_dir=data_dir,
    )
    real_rt.ensure_account()

    divergent_feed = ReplayFeed()
    divergent_broker = PaperBroker(divergent_feed)
    divergent_broker.mode = "mt5-mas-errado"
    divergent_rt = LiveRuntime(
        account_name="teste_divergencia", strategy=ScriptedStrategy({}),
        policy=FloorSkim(pct=0.5, floor=1e12), feed=divergent_feed, broker=divergent_broker,
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=db_path, data_dir=data_dir,
    )

    with pytest.raises(ValueError):
        divergent_rt.close_and_decide(d0)
    with pytest.raises(ValueError):
        divergent_rt.status()


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


# ---------- fill assincrono/pendente (cobertura reduzida) -------------------
# `ManualBroker` (removido: modo manual descontinuado) deixava a ordem SENT
# sem fill ate um humano chamar `confirm()`, o que dava um jeito facil de
# testar "ordem pendente por varios ticks" — os dois testes de anti-duplicacao
# de ordem de venda que moravam aqui (`test_stop_intraday_nao_duplica_ordem_
# sob_corretora_manual`, `test_saida_de_fecho_nao_duplica_ordem_com_stop_ja_
# em_voo`) dependiam exatamente disso: forcar uma ordem SENT parada por 5
# ticks/1 fecho inteiro para provar que ela nao duplicava. O `MT5Broker` atual
# (`live/broker_mt5.py::_send`) resolve toda ordem de forma SINCRONA dentro de
# `place()` (fill ou rejeicao no mesmo `mt5.order_send()`, ver `poll()`: "nao
# ha nada assincrono para reprocessar aqui") — nao ha como reproduzir uma
# ordem parada em voo com o broker de producao real sem fabricar um
# comportamento que ele hoje nao tem. Dois testes removidos aqui e mais dois
# logo abaixo (mesma causa) — ver a nota antes de `test_saque_recomendado_
# nao_move_caixa_nem_gera_ordem`.


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

def test_withdrawal_recomendacao_nao_confirmada_estado_sobrevive_a_restart(tmp_path):
    """A politica de saque so decide (recomendacao) -- nunca confirma
    sozinha, nem espera confirmacao deste sistema (regra do dono,
    2026-08-19: quem saca de verdade e o dono, direto na corretora). O
    estado da politica (`_pool`, `_paid_month`, etc.) precisa sobreviver a
    uma instancia NOVA de `LiveRuntime` apontando para o mesmo banco —
    simula um restart do processo — mesmo sem nenhuma confirmacao.

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

    # Regra do dono (2026-08-19): a recomendacao NUNCA e confirmada por este
    # sistema -- se o dono sacar, e direto na corretora, sem nenhuma acao
    # aqui. O caixa continua intacto, e o estado da politica (_pool,
    # _paid_month) precisa sobreviver ao restart mesmo assim.
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert acc.cash == pytest.approx(10_000.0)

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
    # politica restaurada NAO re-recomenda o mes ja pago -- a UNICA
    # recomendacao pendente continua sendo a mesma de d0 (nunca confirmada,
    # nunca expirada: ainda no mesmo mes civil), nao uma segunda.
    assert len(pend2) == 1
    assert pend2[0].id == intent.id


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


# ---------- (continuacao da nota acima) mais dois testes removidos pelo mesmo
# motivo: `test_manual_broker_fill_so_aplica_apos_confirmacao` e
# `test_run_once_reconcilia_sozinho` fabricavam "ordem pendente, reconciliacao
# aplica depois" via `ManualBroker.confirm()`. A mecanica de
# `reconcile_pending_fills` em si (nao perder `policy_state` mesmo sem nada
# pendente) continua coberta por
# `test_reconcile_pending_fills_nao_apaga_estado_da_politica_de_saque` acima.


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


# ---------- recomendacao de saque: nunca confirmada por este sistema -------

def _runtime_com_recomendacao(tmp_path, data_dir, amount: float = 5_000.0, capital: float = 10_000.0):
    """Monta um `LiveRuntime` com uma recomendacao de saque PENDING ja
    gravada (via `close_and_decide` real, floor baixo o suficiente para
    pagar `amount` no fecho do 1o pregao)."""
    policy = FloorSkim(pct=amount / capital, floor=100.0, day=1, min_amount=0.0)
    days = _sessions(3)
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="mt5", capital=capital)
    rt.ensure_account()
    rt.close_and_decide(days[0])
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend) == 1
    return rt, pend[0], days


def test_recomendacao_de_saque_nunca_debita_caixa_sozinha(tmp_path, universe):
    """Regra do dono (2026-08-19): a recomendacao de saque e so notificacao
    -- nao existe mais nenhum caminho (CLI, dashboard, ou automatico) que
    debite `account.cash` por causa dela. O caixa so muda quando o dono
    informar o novo valor no painel (ledger manual, ver
    `dashboard/app.py::operacao_caixa`) ou quando uma ordem de fato
    executar."""
    data_dir, _days = universe
    rt, intent, _days_run = _runtime_com_recomendacao(tmp_path, data_dir, amount=5_000.0, capital=10_000.0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_withdraw_intents(conn, acc.id)
    assert acc.cash == pytest.approx(10_000.0)
    assert len(pend) == 1
    assert pend[0].id == intent.id


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
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="mt5", capital=10_000.0)
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
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="mt5", capital=10_000.0)
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
    rt = _runtime(tmp_path, data_dir, {}, policy=policy, mode="mt5", capital=10_000.0)
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


# ---------- FEAT-004: execucao notificada, alerta de caixa, PARCIAL --------

class _FakeExpensiveFillBroker(Broker):
    """Preenche a quantidade PEDIDA, mas a um preco muito acima do que foi
    usado por `plan_entry` para dimensionar -- simula um fill real muito
    pior que o planejado (gap, latencia). `place`/`poll` sao os unicos
    metodos usados; nenhuma regra de negocio mora aqui (regra 6)."""

    name = "fake_expensive"
    mode = "mt5"

    def __init__(self, avg_price: float) -> None:
        self._avg_price = avg_price

    def place(self, order):
        order.status = OrderStatus.FILLED
        order.filled_qty = order.quantity
        order.avg_price = self._avg_price
        order.fees = 0.0
        return order

    def poll(self, order):
        return order


def test_fill_com_custo_acima_do_caixa_dispara_alerta_sem_desfazer(tmp_path, universe):
    """4.4a: um fill mais caro que o planejado (gap, gordura de `plan_entry`
    que so reserva ~0,22%) nao pode passar em silencio -- alerta `error`,
    SEM desfazer o fill (ja aconteceu de verdade na corretora)."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    notifier = _RecordingNotifier()
    rt = _runtime(tmp_path, data_dir, script, capital=10_000.0)
    rt.notifier = notifier
    rt.feed.set(TICKER, 100.0)
    rt.broker = _FakeExpensiveFillBroker(avg_price=100.0 * 100)  # 100x o preco planejado
    rt.ensure_account()

    rt.close_and_decide(d0)
    execu = rt.execute_session(d1)
    assert execu.detail["entradas"] == 1  # fill aconteceu, nao foi rejeitado

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    assert TICKER in acc.positions          # fill real NAO e desfeito
    assert acc.cash < 0                     # estourou o caixa disponivel

    eventos_error = [c for c in notifier.calls if c[0] == "error"]
    assert eventos_error, "fill acima do caixa disponivel deveria disparar alerta error"
    assert any("caixa" in c[2].lower() or "custo" in c[2].lower() for c in eventos_error)


def test_entrada_e_saida_executadas_notificam(tmp_path, universe):
    """4.4d: entrada e saida executadas com sucesso geram notificacao --
    os dois momentos mais importantes do dia com dinheiro real nao podem
    ficar mudos (so no diario, sem alertar ninguem)."""
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

    entradas_info = [c for c in notifier.calls
                     if c[0] == "info" and "entrada" in c[2].lower()]
    assert entradas_info, "entrada executada deveria notificar"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
    stop_price = acc.positions[TICKER].current_stop
    assert stop_price is not None
    rt.feed.set(TICKER, stop_price - 1.0)
    rt.intraday_tick(d1)

    saidas_info = [c for c in notifier.calls
                   if c[0] == "info" and "saida" in c[2].lower()]
    assert saidas_info, "saida executada deveria notificar"


def test_fill_parcial_notifica_como_parcial_com_quantidade_restante(tmp_path, universe, monkeypatch):
    """Correcao SUBSTANTIVA do plan-reviewer (§6 item 3): fill PARCIAL nao
    pode notificar como se fosse fill TOTAL -- esconderia exatamente a
    informacao que o item 4.4b desta feature passou a detectar corretamente
    (`PARTIAL` vs `FILLED`).

    Reescrito para `MT5Broker` mockado (mesmo padrao de
    `tests/test_live_broker_mt5.py`) depois que o modo manual foi
    descontinuado: `ManualBroker.confirm()`, que fabricava o fill parcial
    antes, nao existe mais. Diferente do cenario manual (fill parcial so
    aparecia depois de `reconcile_pending_fills`), o `MT5Broker` resolve o
    fill parcial de forma SINCRONA dentro do proprio `execute_session` (ver
    `live/broker_mt5.py::_send`, linha do `order.status = ... PARTIAL`) -- o
    fake `order_send` abaixo devolve metade do volume pedido para forcar
    exatamente esse caminho."""
    import sys
    import types

    from live.broker_mt5 import MT5Broker

    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    notifier = _RecordingNotifier()

    feed = ReplayFeed()
    feed.set(TICKER, 100.0)
    broker = MT5Broker(shares_per_lot=1.0)
    rt = LiveRuntime(
        account_name="teste", strategy=ScriptedStrategy(script),
        policy=FloorSkim(pct=0.5, floor=1e12), feed=feed, broker=broker,
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt.notifier = notifier
    rt.ensure_account()
    rt.close_and_decide(d0)

    fake_mt5 = types.ModuleType("MetaTrader5")
    fake_mt5.TRADE_ACTION_DEAL = 1
    fake_mt5.ORDER_TYPE_BUY = 2
    fake_mt5.ORDER_TYPE_SELL = 3
    fake_mt5.ORDER_TIME_GTC = 4
    fake_mt5.ORDER_FILLING_IOC = 5
    fake_mt5.TRADE_RETCODE_DONE = 6
    fake_mt5.initialize = lambda **kw: True
    fake_mt5.last_error = lambda: (0, "sem erro")
    fake_mt5.symbol_select = lambda symbol, enable=True: True
    fake_mt5.symbol_info = lambda symbol: types.SimpleNamespace(
        volume_min=1.0, volume_max=1_000_000.0, volume_step=1.0,
    )
    fake_mt5.symbol_info_tick = lambda symbol: types.SimpleNamespace(bid=99.9, ask=100.1)
    fake_mt5.history_deals_get = lambda ticket=None: []

    def order_send(request):
        pedido = request["volume"]
        preenchido = max(1.0, pedido // 2)  # fill parcial: metade do pedido
        return types.SimpleNamespace(
            retcode=fake_mt5.TRADE_RETCODE_DONE, price=100.1,
            volume=preenchido, deal=1, order=1, comment="ok",
        )
    fake_mt5.order_send = order_send
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    execu = rt.execute_session(d1)
    assert execu.detail["entradas"] == 1  # MT5 resolve sincrono: fill (parcial) ja e "done"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        order = store.open_orders(conn, acc.id)[0]
    assert order.status == OrderStatus.PARTIAL
    assert order.quantity > order.filled_qty > 0  # premissa do teste: fill genuinamente parcial

    parciais = [c for c in notifier.calls if c[0] == "info" and "PARCIAL" in c[2]]
    assert parciais, "fill parcial deveria notificar como PARCIAL, nao como fill total"
    restante = order.quantity - order.filled_qty
    assert str(restante) in parciais[0][2], "quantidade restante (leaves_qty) deveria aparecer na notificacao"


# ---------- ledger manual de caixa: nao ha sync com a corretora ------------

def test_run_once_no_pre_open_nao_mexe_no_caixa(tmp_path, universe):
    """`reconcile_broker_cash` foi REMOVIDO em 2026-08-21 (ver a secao "ledger
    manual de caixa" em `live/runtime.py`): o saldo do terminal MT5 nao
    acompanha o da Rico, e com dois robos cada um tem o SEU caixa. O caixa
    passou a ser o numero que o dono informa no painel, e `run_once` no
    PRE_OPEN nao pode sobrescreve-lo por baixo dele -- nem para cima, nem
    para baixo, nem gravando auditoria fantasma."""
    data_dir, days = universe
    d0 = days[0]
    feed = ReplayFeed()
    rt = LiveRuntime(
        account_name="teste", strategy=ScriptedStrategy({}), policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=PaperBroker(feed),
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt.ensure_account()
    rt.sync_data = lambda: None  # sem rede no teste, so por precaucao

    open_dt = datetime.combine(d0, clock.session_open(d0))
    pre_open_now = open_dt - timedelta(minutes=5)
    assert clock.phase(pre_open_now) == SessionPhase.PRE_OPEN  # premissa do teste

    passos = rt.run_once(now=pre_open_now)

    assert [p.action for p in passos] == ["idle"]
    assert not hasattr(rt, "reconcile_broker_cash")
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (acc.id,)
        ).fetchall()
    assert acc.cash == pytest.approx(10_000.0)
    assert rows == []


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


def test_execute_session_chamada_duas_vezes_e_idempotente(tmp_path, universe):
    """Mesma sessao, `execute_session` chamado duas vezes seguidas: a
    segunda chamada nao gera ordem nem fill duplicado -- a intencao ja saiu
    de PENDING na primeira chamada."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script)  # mode="mt5" default -> PaperBroker preenche na hora
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    rt.close_and_decide(d0)
    with store.live_journal(rt.db_path) as conn:
        acc0 = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc0.id, d1)
    assert len(pend) == 1
    intent_id = pend[0].id

    r1 = rt.execute_session(d1)
    assert r1.detail["entradas"] == 1

    r2 = rt.execute_session(d1)
    assert r2.detail["entradas"] == 0
    assert r2.detail["rejeitadas"] == 0
    assert r2.detail["aguardando"] == 0

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        ordens = store.orders_for_intent(conn, intent_id)
    assert len(ordens) == 1, "segunda chamada nao deveria ter criado uma 2a ordem"
    assert TICKER in acc.positions
    assert acc.positions[TICKER].quantity == ordens[0].filled_qty


def test_entrada_inviavel_por_caixa_insuficiente_notifica(tmp_path, universe):
    """Intent de ENTER com caixa menor que 1 lote: confirma o evento
    `warn`/"nao cobre um lote" gravado em `_buy` (`runtime.py`), hoje sem
    nenhuma asserção cobrindo essa mensagem especifica."""
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    rt = _runtime(tmp_path, data_dir, script, capital=1.0)  # caixa nao cobre nem 1 acao a R$100
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    rt.close_and_decide(d0)
    result = rt.execute_session(d1)

    assert result.detail["entradas"] == 0
    assert result.detail["rejeitadas"] == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos = store.recent_events(conn, acc.id)
    assert TICKER not in acc.positions
    assert any(
        e["level"] == "warn" and "nao cobre um lote" in e["message"]
        for e in eventos
    )


def test_saque_multiplo_pendente_simultaneo_loga_invariante_quebrada(tmp_path, universe):
    """Corrompe `live_intents` manualmente para ter 2 intents WITHDRAW
    PENDING ao mesmo tempo -- invariante que `_expire_withdraw_advice` nunca
    deveria encontrar (ver docstring do metodo em `runtime.py`), mas se
    encontrar, loga `error`/"invariante quebrada" em vez de passar batido."""
    from core.live_models import Intent, IntentKind, RobotRole

    data_dir, _all_days = universe
    rt, _intent, days = _runtime_com_recomendacao(tmp_path, data_dir, amount=5_000.0, capital=10_000.0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        intruso = Intent(
            robot="withdrawal", role=RobotRole.WITHDRAWAL, kind=IntentKind.WITHDRAW,
            decided_on=days[0], execute_on=days[1], amount=1_000.0,
            reason="corrompido_teste",
        )
        store.record_intent(conn, acc.id, intruso)
        pend_antes = store.pending_withdraw_intents(conn, acc.id)
    assert len(pend_antes) == 2  # premissa do teste: invariante ja quebrada

    rt.execute_session(days[1])

    with store.live_journal(rt.db_path) as conn:
        acc2 = store.load_account(conn, "teste")
        eventos = store.recent_events(conn, acc2.id)
    assert any(
        e["level"] == "error" and "invariante quebrada" in e["message"]
        for e in eventos
    )


# ---------- uma decisao por barra diaria, nunca por tick -------------------

class _ContandoDecisoes(ScriptedStrategy):
    """`ScriptedStrategy` que GRAVA cada chamada de `on_bar`.

    Existe porque `test_close_and_decide_e_idempotente` prova o EFEITO (nao
    duplica intencao nem equity) mas nao prova a CAUSA: que a estrategia foi
    consultada uma vez so. Sao coisas diferentes — uma reordenacao das guardas
    de `close_and_decide` (o achado E3 ja aconteceu uma vez) poderia voltar a
    chamar `on_bar` varias vezes no mesmo pregao e ainda passar naquele teste,
    porque a gravacao no diario seria barrada depois. Estrategia com estado
    mutavel (`BuyTheDip._pending_rebalance`) sendo consultada N vezes por dia
    nao e o robo que o backtest mediu.
    """

    name = "contando_decisoes"

    def __init__(self, script: dict) -> None:
        super().__init__(script)
        self.chamadas: list[pd.Timestamp] = []

    def on_bar(self, on_date, open_positions, cash_available):
        self.chamadas.append(pd.Timestamp(on_date))
        return super().on_bar(on_date, open_positions, cash_available)


def test_estrategia_e_consultada_uma_vez_por_pregao_nunca_por_cotacao(tmp_path, universe):
    """O medo tratado aqui: ao vivo o preco muda o tempo todo, e o supervisor
    roda em loop. A estrategia tem de continuar vendo o mundo como no
    backtest — UMA chamada de `on_bar` por barra diaria, no fecho.

    Prova tres coisas de uma vez:
      1. `close_and_decide` repetido no mesmo pregao consulta a estrategia
         uma vez (as chamadas seguintes param na guarda de idempotencia,
         ANTES de `on_bar`);
      2. `intraday_tick` nunca consulta a estrategia, quantas cotacoes novas
         cheguem — o caminho intra-dia so le `LivePosition.current_stop`
         (`InvestmentRobot.on_intraday`), nao chama `on_bar`;
      3. um pregao novo produz exatamente UMA chamada nova.
    """
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}
    bot = _ContandoDecisoes(script)
    rt = _runtime(tmp_path, data_dir, {}, strategy=bot)
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    for _ in range(5):
        rt.close_and_decide(d0)
    assert bot.chamadas == [pd.Timestamp(d0)], (
        f"estrategia consultada {len(bot.chamadas)}x no mesmo pregao")

    rt.execute_session(d1)

    # 40 cotacoes novas no mesmo pregao, subindo e caindo: o "grafico mexendo"
    for i in range(40):
        rt.feed.set(TICKER, 100.0 + (i % 7) - 3)
        rt.intraday_tick(d1)
    assert bot.chamadas == [pd.Timestamp(d0)], (
        "cotacao nova nao pode disparar decisao de estrategia")

    rt.close_and_decide(d1)
    assert bot.chamadas == [pd.Timestamp(d0), pd.Timestamp(d1)]


def test_run_once_em_loop_no_pregao_nao_consulta_a_estrategia(tmp_path, universe):
    """Mesma invariante pelo caminho REAL do supervisor: `run_once` chamado
    repetidamente durante o pregao (fase OPEN) faz `execute_session` +
    `intraday_tick` e nada mais. A decisao so nasce na fase de fecho.

    Este e o teste que fecha o buraco de operacao: um supervisor em loop de
    um minuto chama `run_once` ~400 vezes por pregao.
    """
    from datetime import time as _time

    data_dir, days = universe
    d1 = days[1]
    bot = _ContandoDecisoes({})
    rt = _runtime(tmp_path, data_dir, {}, strategy=bot)
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    meio_do_pregao = datetime.combine(d1, _time(14, 0), tzinfo=clock.SAO_PAULO)
    assert clock.phase(meio_do_pregao) == SessionPhase.OPEN

    for i in range(30):
        rt.feed.set(TICKER, 100.0 + (i % 5))
        rt.run_once(meio_do_pregao + timedelta(minutes=i))

    assert bot.chamadas == [], "fase OPEN nao pode consultar a estrategia"


def test_dois_supervisores_no_mesmo_banco_nao_decidem_o_mesmo_pregao_duas_vezes(
        tmp_path, universe, monkeypatch):
    """Nao ha guarda de instancia unica no projeto — nenhum pidfile, nenhum
    lock de arquivo — e dois processos no mesmo banco sao plausiveis (o painel
    e `scripts/run_live.py`, ou um restart que nao matou o anterior). O
    `SELECT` de "ja decidido" no inicio de `close_and_decide` nao resolve
    isso: entre ler e gravar existe uma janela.

    O teste reproduz exatamente essa janela. O supervisor B decide e commita;
    o supervisor A entra com a leitura JA DESATUALIZADA (que e o que ele teria
    lido se tivesse comecado antes do commit de B, simulado aqui zerando o
    `last_equity`) e chega ate a gravacao. A reserva atomica
    (`store.claim_session`) e o que impede a segunda decisao — sem ela, a
    MESMA rotacao iria para a corretora duas vezes, com dinheiro de verdade.
    """
    data_dir, days = universe
    d0, d1 = days[0], days[1]
    script = {pd.Timestamp(d0): [Enter(ticker=TICKER, initial_stop=None, size_hint=None)]}

    a = _runtime(tmp_path, data_dir, script, db_name="compartilhado.sqlite")
    b = _runtime(tmp_path, data_dir, script, db_name="compartilhado.sqlite")
    a.feed.set(TICKER, 100.0)
    b.feed.set(TICKER, 100.0)
    a.ensure_account()

    assert b.close_and_decide(d0).action == "decide"

    # A leitura de A ficou para tras: e o estado que ele teria visto se tivesse
    # aberto a transacao antes de B commitar.
    monkeypatch.setattr(store, "last_equity", lambda *_a, **_k: None)
    r = a.close_and_decide(d0)
    monkeypatch.undo()

    assert r.action == "decide_skip"
    assert r.detail["motivo"] == "ja decidido (corrida)"

    with store.live_journal(a.db_path) as conn:
        acc = store.load_account(conn, "teste")
        pend = store.pending_intents(conn, acc.id, d1)
        serie = store.equity_series(conn, acc.id)
        eventos = store.recent_events(conn, acc.id, limit=50)
    assert len(pend) == 1, "a mesma rotacao nao pode ser enfileirada duas vezes"
    assert len(serie) == 1
    assert any("outro processo decidiu" in e["message"] for e in eventos), (
        "a corrida tem de ficar VISIVEL no diario — e sintoma de dois supervisores")


def test_pregao_sem_decisao_empurra_alerta_e_escala_no_fim_de_mes(tmp_path, universe):
    """O risco OPOSTO ao da decisao dupla: a maquina fora do ar no fecho.

    A decisao daquele pregao nao atrasa — ela se perde, porque `BuyTheDip` so
    rebalanceia quando `is_month_end` e verdade naquele dia. `status()` ja
    listava os pregoes sem decisao, mas painel e passivo: quem esta com a
    maquina fora do ar nao esta olhando o painel. Aqui o buraco empurra aviso,
    e escala para `error` quando um dos pregoes perdidos era virada de mes.

    Nao ha retomada automatica — isso e mudanca de comportamento de dinheiro
    (regra 7: intencao velha expira, nunca executa tarde) e nao esta neste
    caminho de proposito.
    """
    data_dir, _ = universe
    # janela real que ATRAVESSA a virada de mes, para o alerta ter o que escalar
    dias = clock.sessions_between(date(2030, 1, 1), date(2030, 4, 1))
    d0 = dias[0]
    fim_de_mes = next(d for d in dias if clock.next_session(d).month != d.month)
    depois = clock.next_session(clock.next_session(fim_de_mes))
    _write_parquet(data_dir, TICKER, dias, [100.0] * len(dias))
    _write_parquet(data_dir, BENCHMARK, dias, [50_000.0] * len(dias))

    rt = _runtime(tmp_path, data_dir, {})
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    assert rt.close_and_decide(d0).action == "decide"
    # processo fora do ar entre d0 e `depois` — inclusive no fim de mes
    assert rt.close_and_decide(depois).action == "decide"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos = store.recent_events(conn, acc.id, limit=50)
    alerta = [e for e in eventos if "sem decisao" in e["message"]]
    assert alerta, "pregao perdido nao pode passar em silencio"
    assert alerta[0]["level"] == "error", "virada de mes tem de escalar"
    assert "PERDIDA" in alerta[0]["message"]
    assert fim_de_mes.isoformat() in alerta[0]["payload"]["fim_de_mes"]


def test_sequencia_normal_de_pregoes_nao_gera_alerta_de_pregao_perdido(tmp_path, universe):
    """Contraprova do teste acima: dois pregoes consecutivos decididos em
    sequencia nao podem gerar aviso nenhum — senao o alerta viraria ruido
    diario e seria ignorado justamente no dia em que importa."""
    data_dir, days = universe
    rt = _runtime(tmp_path, data_dir, {})
    rt.feed.set(TICKER, 100.0)
    rt.ensure_account()

    rt.close_and_decide(days[0])
    rt.close_and_decide(days[1])

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos = store.recent_events(conn, acc.id, limit=50)
    assert not [e for e in eventos if "sem decisao" in e["message"]]


def _fim_de_mes_fora_de_blackout() -> tuple[date, date, date]:
    """(pregao anterior, fim de mes, pregao de retorno) — nenhum em blackout.

    Precisa dos tres livres de blackout de resultados: se o fim de mes caisse
    em blackout, o adiamento viria do blackout e nao da maquina fora do ar, e
    o teste provaria outra coisa. Se o retorno caisse em blackout, a rotacao
    devida continuaria adiada e o teste falharia por motivo errado.
    """
    dias = clock.sessions_between(date(2030, 1, 1), date(2030, 12, 20))
    for i, d in enumerate(dias[1:-2], start=1):
        if clock.next_session(d).month == d.month:
            continue
        anterior, retorno = dias[i - 1], dias[i + 2]
        if any(is_earnings_blackout(pd.Timestamp(x)) for x in (anterior, d, retorno)):
            continue
        return anterior, d, retorno
    raise AssertionError("sem fim de mes fora de blackout no calendario de 2030")


def test_fim_de_mes_perdido_pela_maquina_fora_do_ar_e_reavaliado_no_retorno(tmp_path):
    """A politica escolhida: ao voltar, o robo REANALISA — nao executa o velho.

    Cenario: o processo estava fora do ar exatamente no fecho do ultimo pregao
    do mes, o unico dia em que a familia dip rebalanceia. Sem tratamento, o mes
    inteiro passa sem rotacao e nada disso aparece.

    O ambiente conta o buraco (`on_missed_bars`) e a ESTRATEGIA decide o que
    ele significa: `BuyTheDip` marca a rotacao como devida e, no pregao de
    retorno, recalcula momentum, distancia da maxima e gate de Selic com o dado
    DAQUELE pregao. Nada decidido no fecho antigo e executado — a regra 7
    continua valendo, porque a decisao que sai daqui e nova.
    """
    anterior, fim_de_mes, retorno = _fim_de_mes_fora_de_blackout()
    data_dir = _painel_dip_para(tmp_path, retorno)
    feed = ReplayFeed()
    rt = LiveRuntime(
        account_name="teste",
        strategy=BuyTheDip(top_n=1, dip_pct=0.03, high_window=20,
                           selic_path=str(tmp_path / "selic_inexistente.parquet")),
        policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=PaperBroker(feed),
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=("AAA.SA", "BBB.SA"), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt.ensure_account()

    assert rt.close_and_decide(anterior).detail["intencoes"] == 0, (
        "dia comum antes do fim de mes nao deveria decidir nada")

    # maquina fora do ar no fecho do fim de mes e no pregao seguinte
    r = rt.close_and_decide(retorno)
    assert r.action == "decide"
    assert r.detail["intencoes"] >= 1, (
        "fim de mes perdido nao foi reavaliado no retorno — mes sem rotacao")

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, "teste")
        eventos = store.recent_events(conn, acc.id, limit=50)
        intencoes = store.pending_intents(conn, acc.id, clock.next_session(retorno))
    assert any(e["level"] == "error" and "PERDIDA" in e["message"] for e in eventos)
    # a decisao e de HOJE: `execute_on` e o pregao seguinte ao RETORNO, nunca
    # o pregao seguinte ao fim de mes perdido.
    assert all(i.decided_on == retorno for i in intencoes)
    assert all(i.execute_on == clock.next_session(retorno) for i in intencoes)


def test_pregao_comum_perdido_nao_faz_o_robo_rebalancear_fora_de_hora(tmp_path):
    """Contraprova: pregao perdido que NAO era fim de mes nao deve nada.

    Sem isto, "reavaliar no retorno" viraria "rebalancear em qualquer dia em
    que o processo tenha piscado" — o robo passaria a ter cadencia de uptime
    da maquina em vez de cadencia mensal, e nenhum backtest descreveria isso.
    """
    dias = clock.sessions_between(date(2030, 2, 4), date(2030, 2, 20))
    comuns = [d for d in dias if clock.next_session(d).month == d.month
              and not is_earnings_blackout(pd.Timestamp(d))]
    d0, retorno = comuns[0], comuns[3]
    data_dir = _painel_dip_para(tmp_path, retorno)
    feed = ReplayFeed()
    rt = LiveRuntime(
        account_name="teste",
        strategy=BuyTheDip(top_n=1, dip_pct=0.03, high_window=20,
                           selic_path=str(tmp_path / "selic_inexistente.parquet")),
        policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=PaperBroker(feed),
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=("AAA.SA", "BBB.SA"), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )
    rt.ensure_account()

    rt.close_and_decide(d0)
    r = rt.close_and_decide(retorno)
    assert r.detail["intencoes"] == 0, "pregao comum perdido nao autoriza rotacao"
