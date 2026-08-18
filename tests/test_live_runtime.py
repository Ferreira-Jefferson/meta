"""Teste de integracao do supervisor (`live/runtime.py`).

Nao usa `data/raw` real nem a estrategia oficial: constroi um universo
sintetico em `tmp_path` e um robo de investimento SCRIPTADO (decide por data,
nao por preco) para isolar o que se quer provar aqui — a MECANICA do ambiente
(ordem das operacoes, idempotencia, anti-look-ahead, persistencia de estado,
o fluxo de corretora manual) — do comportamento de qualquer estrategia real.
Esse comportamento ja e validado pelo backtest; aqui o alvo e o encanamento.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from backtest.withdrawal import FloorSkim
from core.config import BENCHMARK, BacktestConfig
from core.earnings_calendar import is_earnings_blackout
from core.live_models import IntentKind, IntentStatus, OrderStatus
from core.models import ExitReason
from journal import live_store as store
from live import clock
from live.broker import ManualBroker, PaperBroker
from live.feed import ReplayFeed
from live.notify import Notifier
from live.riskguard import CircuitBreaker
from live.runtime import LiveRuntime
from strategy.base import AdjustStop, Enter, Exit, Strategy
from strategy.buy_the_dip import BuyTheDip

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
            mode="paper", capital=10_000.0) -> LiveRuntime:
    feed = ReplayFeed()
    broker = ManualBroker() if mode == "manual" else PaperBroker(feed)
    return LiveRuntime(
        account_name="teste",
        strategy=ScriptedStrategy(script),
        policy=policy or FloorSkim(pct=0.5, floor=1e12),  # nunca saca por acidente
        feed=feed, broker=broker, config=BacktestConfig(initial_capital=capital, lot_size=1),
        tickers=(TICKER,), db_path=tmp_path / db_name, data_dir=days_dir,
    )


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
