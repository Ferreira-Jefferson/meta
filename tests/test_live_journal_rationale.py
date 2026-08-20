"""O diario responde "por que?" — motivo da entrada + contexto de mercado.

Antes desta feature o diario ao vivo sabia explicar toda VENDA (`ExitReason`)
e nenhuma COMPRA (`Intent.reason` ficava vazio nas entradas), e o contexto de
sinal (MM/IFR/ATR/regime do IBOV) so era gravado pelo backtest. Os testes
aqui cobrem as tres pecas dessa correcao:

  1. `strategy/` produz o motivo e os numeros (`Enter.reason`/`metadata`);
  2. `live/runtime.py` grava os dois junto da intencao, ancorados no pregao
     que DECIDIU (nunca no ultimo pregao do painel);
  3. `journal/` persiste o contexto em colunas identicas as do backtest, para
     que comparar operacao real com simulacao seja uma query, nao um projeto.

O eixo mais importante e o de FALHA: registro nunca pode derrubar decisao.
Varios testes abaixo provocam erro na parte de anotacao e exigem que a
intencao continue gravada.
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import date

import pandas as pd
import pytest

from backtest.withdrawal import FloorSkim
from core.config import BENCHMARK, BacktestConfig
from core.live_models import Intent, IntentKind, RobotRole
from core.market_features import enrich_features, snapshot_from_row
from core.models import ExitReason, MarketSnapshot
from journal import live_store as store
from live import clock
from live.robots import _payload_safe
from live.runtime import LiveRuntime
from strategy.base import Enter, OpenPosition
from strategy.buy_the_dip import BuyTheDip
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio
from tests.doubles import PaperBroker, ReplayFeed, ScriptedStrategy, _RecordingNotifier

TICKER = "AAA.SA"


# ---------------------------------------------------------------------------
# 1. a estrategia diz POR QUE entrou
# ---------------------------------------------------------------------------

def _rig_dip(strategy, dates, scores, dist, month_end):
    """Injeta os indicadores pre-calculados que `on_bar` consulta, sem passar
    por `initialize()` — mesma tecnica de `tests/test_strategy_champion.py`."""
    strategy._scores = scores
    strategy._dist_from_high = dist
    strategy._month_end = month_end
    strategy._blackout = pd.Series(False, index=dates)
    strategy._selic_tightening = pd.Series(False, index=dates)


def test_entrada_do_buy_the_dip_registra_regra_e_numeros():
    d = pd.Timestamp("2030-01-31")
    s = BuyTheDip(top_n=2, dip_pct=0.02)
    _rig_dip(
        s, [d],
        scores={"AAA.SA": pd.Series([0.9], index=[d]),
                "BBB.SA": pd.Series([0.5], index=[d]),
                "CCC.SA": pd.Series([0.1], index=[d])},
        dist={"AAA.SA": pd.Series([-0.05], index=[d]),
              "BBB.SA": pd.Series([-0.03], index=[d]),
              "CCC.SA": pd.Series([-0.9], index=[d])},
        month_end=pd.Series([True], index=[d]),
    )
    entradas = [a for a in s.on_bar(d, {}, 10_000.0) if isinstance(a, Enter)]

    assert {e.ticker for e in entradas} == {"AAA.SA", "BBB.SA"}
    for e in entradas:
        assert e.reason == "dip_rank"

    top1 = next(e for e in entradas if e.ticker == "AAA.SA")
    # O "por que" completo: qual regra, em que posicao do ranking, com que
    # score, quao abaixo da maxima, e contra qual limiar.
    assert top1.metadata["rank"] == 1
    assert top1.metadata["top_n"] == 2
    assert top1.metadata["momentum_score"] == pytest.approx(0.9)
    assert top1.metadata["dist_from_high"] == pytest.approx(-0.05)
    assert top1.metadata["dip_threshold"] == pytest.approx(-0.02)
    assert top1.metadata["trigger"] == "month_end"
    # CCC nao entrou (fora do top-2), mas o rank de BBB tem de refletir a
    # ordem real do ranking, nao a ordem de iteracao do dict.
    assert next(e for e in entradas if e.ticker == "BBB.SA").metadata["rank"] == 2


def test_entrada_limpa_e_entrada_por_rotacao_tem_motivos_diferentes():
    """A distincao importa no diario: uma compra que substituiu outra posicao
    responde a uma pergunta diferente de uma compra feita com caixa parado."""
    d = pd.Timestamp("2030-01-31")

    limpa = DipTop1Portfolio(dip_pct=0.02)
    _rig_dip(limpa, [d],
             scores={"AAA.SA": pd.Series([0.9], index=[d])},
             dist={"AAA.SA": pd.Series([-0.05], index=[d])},
             month_end=pd.Series([True], index=[d]))
    e1 = next(a for a in limpa.on_bar(d, {}, 10_000.0) if isinstance(a, Enter))
    assert e1.reason == "dip_rank1"
    assert e1.metadata["rotated_from"] is None

    girou = DipTop1Portfolio(dip_pct=0.02)
    # `_hysteresis` vem de uma constante de modulo (`h3_hysteresis.HYSTERESIS`),
    # nao de kwarg do construtor — fixado aqui para o teste nao depender do
    # valor calibrado da campea.
    girou._hysteresis = 0.10
    _rig_dip(girou, [d],
             scores={"AAA.SA": pd.Series([0.9], index=[d]),
                     "OLD.SA": pd.Series([0.1], index=[d])},
             dist={"AAA.SA": pd.Series([-0.05], index=[d])},
             month_end=pd.Series([True], index=[d]))
    posicao = {"OLD.SA": OpenPosition(ticker="OLD.SA", entry_date=d, entry_price=10.0,
                                      quantity=100, current_stop=None, bars_held=5)}
    acoes = girou.on_bar(d, posicao, 0.0)
    e2 = next(a for a in acoes if isinstance(a, Enter))
    assert e2.reason == "dip_rank1_rotation"
    assert e2.metadata["rotated_from"] == "OLD.SA"
    # A folga com que a histerese foi vencida — o numero que explica por que a
    # rotacao foi considerada justificada e nao ruido.
    assert e2.metadata["hysteresis_margin"] is not None
    assert e2.metadata["hysteresis"] == pytest.approx(0.10)


def test_registro_do_motivo_nao_altera_a_decisao():
    """Guarda contra o risco real da mudanca: acrescentar `reason`/`metadata`
    a `Enter` nao pode ter mudado QUAIS entradas o robo faz. Mesmo cenario com
    e sem dip suficiente — o gate continua sendo o gate."""
    d = pd.Timestamp("2030-01-31")
    for dist_valor, entra in ((-0.05, True), (-0.01, False)):
        s = DipTop1Portfolio(dip_pct=0.02)
        _rig_dip(s, [d],
                 scores={"AAA.SA": pd.Series([0.9], index=[d])},
                 dist={"AAA.SA": pd.Series([dist_valor], index=[d])},
                 month_end=pd.Series([True], index=[d]))
        entradas = [a for a in s.on_bar(d, {}, 10_000.0) if isinstance(a, Enter)]
        assert bool(entradas) is entra


# ---------------------------------------------------------------------------
# 2. `_payload_safe`: registro nunca derruba decisao
# ---------------------------------------------------------------------------

def test_payload_safe_serializa_escalares_de_numpy_preservando_o_tipo():
    import numpy as np

    p = _payload_safe({
        "f": np.float64(1.5), "i": np.int64(3), "b": np.bool_(True),
        "s": "dip_rank", "n": None,
    })
    # O ponto e sobreviver ao `json.dumps` de `record_intent`...
    assert json.loads(json.dumps(p)) == {
        "f": 1.5, "i": 3, "b": True, "s": "dip_rank", "n": None,
    }
    # ...sem achatar booleano em numero, que viraria ruido de auditoria.
    assert p["b"] is True
    assert isinstance(p["i"], int) and not isinstance(p["i"], bool)


def test_payload_safe_troca_nan_e_infinito_por_none():
    """NaN/inf sao JSON invalido em parser estrito. "Sem valor" e None."""
    p = _payload_safe({"nan": float("nan"), "inf": float("inf")})
    assert p == {"nan": None, "inf": None}
    assert json.loads(json.dumps(p)) == {"nan": None, "inf": None}


def test_payload_safe_nao_quebra_com_objeto_exotico():
    class Estranho:
        def __repr__(self):
            return "<estranho>"

    p = _payload_safe({"x": Estranho()})
    assert p == {"x": "<estranho>"}
    json.dumps(p)  # nao levanta


def test_payload_safe_com_metadata_vazio_ou_none():
    assert _payload_safe(None) == {}
    assert _payload_safe({}) == {}


# ---------------------------------------------------------------------------
# 3. persistencia: colunas identicas as do backtest
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return tmp_path / "live.sqlite"


def _conta(conn):
    return store.ensure_account(conn, name="c", mode="mt5", initial_capital=1000.0,
                                investment_robot="r", withdrawal_robot="w")


def _snap(**over) -> MarketSnapshot:
    base = dict(
        close=50.0, volume=1e6, volume_vs_avg20=1.2, mm20=49.0, mm50=48.0,
        mm200=45.0, mm50_over_mm200_pct=0.0667, days_since_cross=12,
        ifr14=55.0, atr14=1.3, historical_vol_30d=0.28,
        distance_from_52w_high_pct=-0.05, distance_from_52w_low_pct=0.40,
        ibov_close=120_000.0, ibov_mm200=110_000.0, ibov_above_mm200=True,
        ibov_trend_strength=0.0909, correlation_with_ibov_60d=0.65,
    )
    base.update(over)
    return MarketSnapshot(**base)


def _intent(kind=IntentKind.ENTER, **over) -> Intent:
    campos = dict(robot="r", role=RobotRole.INVESTMENT, kind=kind,
                  decided_on=date(2030, 1, 10), execute_on=date(2030, 1, 11),
                  ticker=TICKER)
    campos.update(over)
    return Intent(**campos)


def test_colunas_do_snapshot_acompanham_o_dataclass():
    """Guarda da regra 3 do AGENTS.md ("sempre que uma nova feature aparecer
    no snapshot, adicione coluna"). `_SNAPSHOT_COLUMNS` alimenta o INSERT pela
    POSICAO, entao um campo novo em `MarketSnapshot` que nao seja adicionado
    la desalinha valor e coluna EM SILENCIO — grava IFR no lugar do ATR sem
    erro nenhum. Este teste transforma esse silencio numa falha."""
    campos = tuple(f.name for f in dataclasses.fields(MarketSnapshot))
    assert campos == store._SNAPSHOT_COLUMNS


def test_colunas_da_tabela_ao_vivo_espelham_as_do_backtest(db):
    """O objetivo INTEIRO da tabela e comparar real com simulado na mesma
    query. Se as colunas divergirem, a comparacao para de existir."""
    with store.live_journal(db) as conn:
        vivo = {r["name"] for r in conn.execute(
            "PRAGMA table_info(live_signal_snapshots)")}

    # `signal_snapshots` mora no schema de backtest; cria num banco a parte.
    outro = db.parent / "backtest.sqlite"
    c2 = sqlite3.connect(outro)
    c2.executescript(store.SCHEMA_PATH.read_text(encoding="utf-8"))
    backtest = {r[1] for r in c2.execute("PRAGMA table_info(signal_snapshots)")}
    c2.close()

    # `trade_id` (backtest) <-> `intent_id`+`ticker` (ao vivo) sao as ancoras
    # de cada lado; o resto — todo o conteudo de mercado — tem de ser igual.
    assert (backtest - {"id", "trade_id"}) == (vivo - {"id", "intent_id", "ticker"})


def test_snapshot_gravado_volta_com_os_mesmos_valores(db):
    with store.live_journal(db) as conn:
        acc = _conta(conn)
        iid = store.record_intent(conn, acc.id, _intent(reason="dip_rank"))
        store.record_intent_snapshot(conn, iid, "entry", TICKER, _snap())

        lido = store.intent_snapshot(conn, iid)
        assert lido["moment"] == "entry"
        assert lido["ticker"] == TICKER
        assert lido["ifr14"] == pytest.approx(55.0)
        assert lido["days_since_cross"] == 12
        assert lido["ibov_above_mm200"] == 1
        assert lido["distance_from_52w_high_pct"] == pytest.approx(-0.05)


def test_regravar_o_mesmo_momento_sobrescreve_sem_duplicar(db):
    """Reentrancia do runtime (retry de sessao interrompida) descreve o MESMO
    pregao — sobrescrever e correto, duplicar linha no diario nao e."""
    with store.live_journal(db) as conn:
        acc = _conta(conn)
        iid = store.record_intent(conn, acc.id, _intent())
        store.record_intent_snapshot(conn, iid, "entry", TICKER, _snap(ifr14=10.0))
        store.record_intent_snapshot(conn, iid, "entry", TICKER, _snap(ifr14=90.0))

        n = conn.execute("SELECT COUNT(*) c FROM live_signal_snapshots").fetchone()["c"]
        assert n == 1
        assert store.intent_snapshot(conn, iid)["ifr14"] == pytest.approx(90.0)


def test_entrada_e_saida_da_mesma_intencao_convivem(db):
    with store.live_journal(db) as conn:
        acc = _conta(conn)
        iid = store.record_intent(conn, acc.id, _intent())
        store.record_intent_snapshot(conn, iid, "entry", TICKER, _snap(ifr14=30.0))
        store.record_intent_snapshot(conn, iid, "exit", TICKER, _snap(ifr14=70.0))

        assert store.intent_snapshot(conn, iid, "entry")["ifr14"] == pytest.approx(30.0)
        assert store.intent_snapshot(conn, iid, "exit")["ifr14"] == pytest.approx(70.0)


def test_moment_invalido_e_recusado(db):
    with store.live_journal(db) as conn:
        acc = _conta(conn)
        iid = store.record_intent(conn, acc.id, _intent())
        with pytest.raises(ValueError, match="moment invalido"):
            store.record_intent_snapshot(conn, iid, "meio", TICKER, _snap())


def test_apagar_a_conta_leva_o_snapshot_junto(db):
    """`ON DELETE CASCADE` via `live_intents` — snapshot orfao e lixo."""
    with store.live_journal(db) as conn:
        acc = _conta(conn)
        iid = store.record_intent(conn, acc.id, _intent())
        store.record_intent_snapshot(conn, iid, "entry", TICKER, _snap())

        conn.execute("DELETE FROM live_accounts WHERE id = ?", (acc.id,))
        n = conn.execute("SELECT COUNT(*) c FROM live_signal_snapshots").fetchone()["c"]
        assert n == 0


def test_intent_snapshots_devolve_mapa_por_intencao(db):
    with store.live_journal(db) as conn:
        acc = _conta(conn)
        ids = []
        for dia, ifr in ((10, 20.0), (11, 60.0)):
            iid = store.record_intent(conn, acc.id, _intent(
                decided_on=date(2030, 1, dia), execute_on=date(2030, 1, dia + 1)))
            store.record_intent_snapshot(conn, iid, "entry", TICKER, _snap(ifr14=ifr))
            ids.append(iid)

        mapa = store.intent_snapshots(conn, acc.id)
        assert set(mapa) == set(ids)
        assert mapa[ids[1]]["ifr14"] == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# 4. runtime: grava contexto ancorado no pregao que DECIDIU
# ---------------------------------------------------------------------------

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
def universo(tmp_path):
    """Precos CRESCENTES de proposito: com preco constante, MM20/MM50 ficam
    identicas e o snapshot nao distingue um pregao do outro — o teste de
    ancoragem em `decided_on` nao provaria nada."""
    dias = clock.sessions_between(date(2030, 1, 1), date(2030, 4, 1))[:10]
    closes = [100.0 + 3.0 * i for i in range(len(dias))]
    _write_parquet(tmp_path, TICKER, dias, closes)
    _write_parquet(tmp_path, BENCHMARK, dias,
                   [50_000.0 + 100.0 * i for i in range(len(dias))])
    return tmp_path, dias, closes


def _runtime(tmp_path, data_dir) -> LiveRuntime:
    return _runtime_com_script(tmp_path, data_dir, {})


def _runtime_com_script(tmp_path, data_dir, script) -> LiveRuntime:
    feed = ReplayFeed()
    return LiveRuntime(
        account_name="teste", strategy=ScriptedStrategy(script),
        policy=FloorSkim(pct=0.5, floor=1e12),
        feed=feed, broker=PaperBroker(feed),
        config=BacktestConfig(initial_capital=10_000.0, lot_size=1),
        tickers=(TICKER,), db_path=tmp_path / "live.sqlite", data_dir=data_dir,
    )


def test_entrada_ao_vivo_grava_motivo_numeros_e_contexto(universo, tmp_path):
    data_dir, dias, closes = universo
    decisao = dias[7]
    rt = _runtime_com_script(tmp_path, data_dir, {
        pd.Timestamp(decisao): [Enter(ticker=TICKER, size_hint=1.0,
                                      reason="dip_rank1",
                                      metadata={"rank": 1, "dist_from_high": -0.04})],
    })
    rt.ensure_account()
    rt.close_and_decide(decisao)

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        intents = [i for i in store.all_intents(conn, conta.id)
                   if i.kind == IntentKind.ENTER]
        assert len(intents) == 1
        i = intents[0]
        # o "por que" da regra...
        assert i.reason == "dip_rank1"
        assert i.payload == {"rank": 1, "dist_from_high": -0.04}
        # ...e o contexto de mercado que o robo estava vendo.
        snap = store.intent_snapshot(conn, i.id, "entry")
        assert snap is not None
        assert snap["ticker"] == TICKER
        assert snap["close"] == pytest.approx(closes[7])


def test_snapshot_vem_do_pregao_da_decisao_nao_do_ultimo_do_painel(universo, tmp_path):
    """Anti-look-ahead do registro. O painel do runtime vai ate `session`, mas
    a gravacao acontece depois e o processo pode ter cruzado a virada do
    pregao. Ancorar em `iloc[-1]` gravaria um contexto que o robo nao viu.

    Prova direta: grava-se a MAO uma intencao com `decided_on` num pregao
    ANTIGO, com o painel do runtime ja carregado ate um pregao posterior. O
    `close` gravado tem de ser o do dia antigo.
    """
    data_dir, dias, closes = universo
    antigo, hoje = dias[5], dias[8]
    rt = _runtime(tmp_path, data_dir)
    rt.ensure_account()
    rt._load(hoje)          # painel ate dias[8]
    assert rt._panels[TICKER].index[-1] == pd.Timestamp(hoje)

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        iid = rt._record_intent(conn, conta, _intent(
            decided_on=antigo, execute_on=dias[6], reason="dip_rank1"))
        snap = store.intent_snapshot(conn, iid, "entry")

    assert snap["close"] == pytest.approx(closes[5])
    assert snap["close"] != pytest.approx(closes[8])


def test_saida_ao_vivo_grava_contexto_com_moment_exit(universo, tmp_path):
    data_dir, dias, _ = universo
    rt = _runtime(tmp_path, data_dir)
    rt.ensure_account()
    rt._load(dias[6])

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        iid = rt._record_intent(conn, conta, _intent(
            kind=IntentKind.EXIT, decided_on=dias[6], execute_on=dias[7],
            reason=ExitReason.ROTATION_OUT.value))

        assert store.intent_snapshot(conn, iid, "exit") is not None
        assert store.intent_snapshot(conn, iid, "entry") is None


@pytest.mark.parametrize("kind,extra", [
    (IntentKind.ADJUST_STOP, {"stop_price": 90.0}),
    (IntentKind.WITHDRAW, {"amount": 500.0, "ticker": None}),
])
def test_ajuste_de_stop_e_saque_nao_geram_snapshot(universo, tmp_path, kind, extra):
    """Nenhum dos dois e "contexto de sinal": `ADJUST_STOP` nao movimenta
    dinheiro e `WITHDRAW` nao e sobre um papel."""
    data_dir, dias, _ = universo
    rt = _runtime(tmp_path, data_dir)
    rt.ensure_account()
    rt._load(dias[6])

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        iid = rt._record_intent(conn, conta, _intent(
            kind=kind, decided_on=dias[6], execute_on=dias[6], **extra))

        assert store.intent_snapshot(conn, iid) is None
        # ...mas a intencao em si foi gravada.
        assert conn.execute("SELECT COUNT(*) c FROM live_intents").fetchone()["c"] == 1


def test_falha_ao_anotar_contexto_nao_perde_a_intencao(universo, tmp_path, monkeypatch):
    """O invariante mais importante da feature: anotacao e subordinada a
    decisao. Se a gravacao do snapshot explodir, a intencao continua no diario
    e o erro vira evento — nunca excecao subindo pelo runtime."""
    data_dir, dias, _ = universo
    rt = _runtime(tmp_path, data_dir)
    rt.ensure_account()
    rt._load(dias[6])

    def explode(*a, **k):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(store, "record_intent_snapshot", explode)

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        iid = rt._record_intent(conn, conta, _intent(
            decided_on=dias[6], execute_on=dias[7], reason="dip_rank1"))

        assert iid is not None
        assert conn.execute("SELECT COUNT(*) c FROM live_intents").fetchone()["c"] == 1
        assert store.intent_snapshot(conn, iid) is None
        eventos = [e for e in store.recent_events(conn, conta.id, limit=50)
                   if e["source"] == "diario"]
        assert eventos, "a falha de anotacao tem de ficar registrada"
        assert "disco cheio" in eventos[0]["message"]


def test_falha_ao_anotar_contexto_nao_notifica_o_dono(universo, tmp_path, monkeypatch):
    """Alerta que chega sem exigir acao treina o dono a ignorar os alertas que
    exigem. Snapshot faltando fica no diario, nao no Telegram."""
    data_dir, dias, _ = universo
    rt = _runtime(tmp_path, data_dir)
    rt.notifier = _RecordingNotifier()
    rt.ensure_account()
    rt._load(dias[6])

    def explode(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(store, "record_intent_snapshot", explode)

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        rt._record_intent(conn, conta, _intent(
            decided_on=dias[6], execute_on=dias[7]))

    assert rt.notifier.calls == []


def test_ticker_fora_do_painel_nao_derruba_a_gravacao(universo, tmp_path):
    data_dir, dias, _ = universo
    rt = _runtime(tmp_path, data_dir)
    rt.ensure_account()
    rt._load(dias[6])

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        iid = rt._record_intent(conn, conta, _intent(
            decided_on=dias[6], execute_on=dias[7], ticker="NAOEXISTE.SA"))
        assert iid is not None
        assert store.intent_snapshot(conn, iid) is None


def test_pregao_ausente_no_painel_registra_evento_e_mantem_a_intencao(universo, tmp_path):
    data_dir, dias, _ = universo
    rt = _runtime(tmp_path, data_dir)
    rt.ensure_account()
    rt._load(dias[6])

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        # 2029: fora do painel inteiro.
        iid = rt._record_intent(conn, conta, _intent(
            decided_on=date(2029, 6, 1), execute_on=date(2029, 6, 4)))

        assert store.intent_snapshot(conn, iid) is None
        msgs = [e["message"] for e in store.recent_events(conn, conta.id, limit=50)
                if e["source"] == "diario"]
        assert any("nao esta no painel" in m for m in msgs)


def test_cache_de_painel_enriquecido_e_invalidado_ao_remontar(universo, tmp_path):
    """Sem a invalidacao, o snapshot descreveria dado que o robo nao recebeu."""
    data_dir, dias, _ = universo
    rt = _runtime(tmp_path, data_dir)
    rt._load(dias[6])
    assert rt._enriched(TICKER) is not None
    assert TICKER in rt._enriched_cache

    rt._prepared_through = None      # forca a remontagem
    rt._load(dias[8])
    assert rt._enriched_cache == {}


# ---------------------------------------------------------------------------
# 5. o motivo da extracao: live e backtest calculam pelo MESMO codigo
# ---------------------------------------------------------------------------

def test_engine_de_backtest_usa_o_modulo_compartilhado():
    """Se o backtest voltar a ter calculo proprio, a comparacao entre o
    snapshot real e o simulado deixa de significar algo — e a divergencia
    aparece como numeros PARECIDOS, nao como erro."""
    from backtest import engine

    assert engine._enrich is enrich_features
    assert engine._snapshot is snapshot_from_row


def test_snapshot_ao_vivo_bate_com_o_do_backtest_no_mesmo_dado(universo, tmp_path):
    """O teste que justifica a feature inteira: mesmo painel, mesmo pregao,
    numeros identicos nas duas camadas."""
    data_dir, dias, _ = universo
    rt = _runtime(tmp_path, data_dir)
    rt.ensure_account()
    rt._load(dias[8])

    esperado = snapshot_from_row(
        enrich_features(rt._panels[TICKER], rt._ibov).loc[pd.Timestamp(dias[8])]
    )

    with store.live_journal(tmp_path / "live.sqlite") as conn:
        conta = store.load_account(conn, "teste")
        iid = rt._record_intent(conn, conta, _intent(
            decided_on=dias[8], execute_on=clock.next_session(dias[8])))
        gravado = store.intent_snapshot(conn, iid, "entry")

    for campo in store._SNAPSHOT_COLUMNS:
        alvo = getattr(esperado, campo)
        if isinstance(alvo, bool):
            assert bool(gravado[campo]) == alvo, campo
        else:
            assert gravado[campo] == pytest.approx(alvo), campo

# ---------------------------------------------------------------------------
# 6. dashboard: o "por que" chega na tela
# ---------------------------------------------------------------------------

def test_num_br_formata_no_padrao_brasileiro():
    """O padrao `.replace(",", ".")` usado no resto dos templates corrompe
    valor COM decimal ("1,234.56" -> "1.234.56", dois pontos). `num_br` troca
    os dois separadores de uma vez."""
    from dashboard.app import num_br

    assert num_br(1234.56) == "1.234,56"
    assert num_br(48.74) == "48,74"
    assert num_br(131_450.0, 0) == "131.450"
    assert num_br(0.2841, None) == "0,2841"     # sem casas fixas: corta zeros
    assert num_br(None) == "—"
    assert num_br("RADL3.SA") == "RADL3.SA"     # payload de gatilho tem string
    assert num_br(True) == "sim"


def test_motivo_legivel_cai_no_codigo_quando_nao_ha_traducao():
    """Robo novo aparece com o codigo dele, sem inventar frase."""
    from dashboard.app import motivo_legivel

    assert motivo_legivel("dip_rank1_rotation") != "dip_rank1_rotation"
    assert motivo_legivel("robo_futuro_xyz") == "robo_futuro_xyz"
    assert motivo_legivel("") == ""


@pytest.fixture
def dash(tmp_path, monkeypatch):
    """Cliente do dashboard apontado para um banco isolado — mesma tecnica da
    fixture `isolated_journal` de `tests/test_dashboard_app.py`."""
    from fastapi.testclient import TestClient

    from dashboard import app as dashboard_app
    from dashboard import live_service
    from live import runtime as live_runtime

    db_path = tmp_path / "live_journal.sqlite"
    monkeypatch.setattr(store.live_journal.__wrapped__, "__defaults__", (db_path,))
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    return TestClient(dashboard_app.app), db_path, live_service.ACCOUNT_NAME


def test_historico_mostra_frase_codigo_e_contexto(dash):
    client, db_path, nome = dash
    with store.live_journal(db_path) as conn:
        acc = store.ensure_account(conn, name=nome, mode="mt5",
                                   initial_capital=10_000.0,
                                   investment_robot="portfolio_dip2_hw40",
                                   withdrawal_robot="official_policy")
        iid = store.record_intent(conn, acc.id, _intent(
            ticker="WEGE3.SA", reason="dip_rank1_rotation",
            payload={"rank": 1, "rotated_from": "RADL3.SA"}))
        store.record_intent_snapshot(conn, iid, "entry", "WEGE3.SA",
                                     _snap(close=48.74))

    html = client.get("/operacao/historico").text

    # frase legivel para ler rapido...
    assert "assumiu o lugar da posição anterior" in html
    # ...e o codigo cru, que e o dado que uma query vai procurar
    assert "dip_rank1_rotation" in html
    # gatilho (numeros da regra) e mercado (contexto do papel)
    assert "Gatilho" in html
    assert "rotated from" in html
    assert "RADL3.SA" in html
    assert "IFR14" in html
    assert f'id="ctx-{iid}"' in html
    # numero no padrao brasileiro, nao "48.74"
    assert "48,74" in html


def test_historico_nao_oferece_por_que_sem_racional_gravado(dash):
    """Decisao legada (sem payload nem snapshot) nao ganha botao — oferecer um
    "por que" que abre vazio e pior que nao oferecer."""
    client, db_path, nome = dash
    with store.live_journal(db_path) as conn:
        acc = store.ensure_account(conn, name=nome, mode="mt5",
                                   initial_capital=10_000.0,
                                   investment_robot="portfolio_dip2_hw40",
                                   withdrawal_robot="official_policy")
        store.record_intent(conn, acc.id, _intent(ticker="BRAP4.SA"))

    html = client.get("/operacao/historico").text
    assert "BRAP4" in html
    # `ctx-toggle` sozinho nao serve: a string tambem aparece no JS do toggle,
    # que a pagina sempre carrega. O que nao pode existir e o BOTAO.
    assert 'class="ctx-toggle"' not in html
    assert "aria-controls=" not in html


def test_historico_sem_conta_continua_respondendo(dash):
    """A pagina nunca cria conta — regra do endpoint. So nao pode quebrar."""
    client, _, _ = dash
    r = client.get("/operacao/historico")
    assert r.status_code == 200
