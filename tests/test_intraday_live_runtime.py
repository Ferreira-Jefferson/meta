"""Testes de `live/intraday_runtime.py::IntradayLiveRuntime` — o robo de day
trade operando ao vivo, em MODO SOMBRA.

Nenhum destes testes toca no terminal MT5 nem na corretora: o feed de barras
e' um dublê que devolve barras roteirizadas, e o broker e' um dublê que
EXPLODE se alguem tentar mandar ordem (e' assim que se prova que sombra e'
sombra de verdade).

O que esta em jogo, em ordem de importancia:
  1. sombra nunca chama a corretora e nunca debita o caixa do dono;
  2. `penetration_ticks` e' gravado — e' a medicao que justifica a fase de
     sombra (a premissa de maker do robo nunca foi verificada contra o
     mercado real, ver a docstring do modulo testado);
  3. o despacho warm-start/frio segue a politica decidida em 2026-08-21
     (`pmam3_daytrade_champion` na memoria do projeto);
  4. um buraco de barras nao executa decisao velha nem deixa posicao orfa.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.machine import IntradayBacktestConfig
from core.config import slot_by_id
from journal import live_store as store
from live import clock as live_clock
from live import intraday_runtime as itr_mod
from live.intraday_runtime import MAX_GAP_BARS, IntradayLiveRuntime
from strategy.daytrade.base import Bar

SLOT = slot_by_id("daytrade")
# O simbolo e' propriedade do ROBO desde 2026-08-21 (`Slot` nao declara mais
# `symbol`) -- este e' o default da `Gremah` usada nestes testes.
SYMBOL = "PMAM3"
SESSION = date(2026, 8, 21)


class _ExplodingBroker:
    """Qualquer chamada de execucao aqui e' um bug: em modo sombra a corretora
    nunca deve ser tocada. `name`/`mode`/`supports_automation` sao lidos por
    `status()` (leitura pura) e por isso existem."""

    name = "explosivo"
    mode = "mt5"

    def supports_automation(self):
        return True

    def place(self, order):
        raise AssertionError("modo sombra NUNCA pode mandar ordem para a corretora")

    def poll(self, order):
        raise AssertionError("modo sombra NUNCA pode consultar ordem na corretora")

    def cash_balance(self):
        raise AssertionError("o caixa do slot vem do ledger manual, nao da corretora")


class _ScriptedBarFeed:
    """Entrega barras roteirizadas. `closed_bars_since` devolve o que ainda
    nao foi entregue; `session_bars_until` devolve as barras da semente
    declarada."""

    name = "fake_bars"

    def __init__(self, barras: list[Bar], semente: list[Bar] | None = None):
        self._barras = list(barras)
        self._semente = list(semente or [])
        self.pedidos_de_semente: list = []

    @property
    def offset_hours(self):
        return 3.0

    def closed_bars_since(self, after_ts=None):
        if after_ts is None:
            return list(self._barras)
        return [b for b in self._barras if b.ts > after_ts]

    def session_bars_until(self, session, until_ts):
        self.pedidos_de_semente.append((session, until_ts))
        return [b for b in self._semente if b.ts <= until_ts]


def _bar(hhmm: str, o, h, low, c) -> Bar:
    return Bar(ts=pd.Timestamp(f"2026-08-21 {hhmm}", tz="UTC"),
               open=float(o), high=float(h), low=float(low), close=float(c), volume=1_000.0)


def _config() -> IntradayBacktestConfig:
    return IntradayBacktestConfig(
        costs=IntradayCostModel(point_value_brl=1.0, tick_size=0.01,
                               fee_round_trip_brl=0.0, slippage_ticks=0.0),
        # Mesma politica da producao (PMAM3 e' acao): o corte sai do
        # calendario, nao de um numero fixo. Em 21/08/2026 (horario de verao
        # dos EUA) isso da 19:54 UTC, que era o valor congelado — de proposito,
        # para o roteiro de barras destes testes continuar valendo.
        session_end_policy="b3_equities",
        target_fills_as_maker=True,
        default_quantity=1,
    )


def _runtime(tmp_path, barras, semente=None, execution_mode="shadow", **strat_kwargs):
    """`semente` default = a PRIMEIRA barra de `barras` (a abertura do pregao).

    E' o caso realista de ligar dentro da janela de ancora fixa: o warm start
    recalibra com a abertura real e as barras seguintes chegam ao vivo. Sem
    isto, o robo cairia em comeco a frio e a marca de partida engoliria todas
    as barras do roteiro -- o teste passaria sem o robo ter operado nada."""
    from strategy.daytrade.lab.gremah import Gremah

    kwargs = dict(symbol=SYMBOL, tick_size=0.01, profit_pct=0.01,
                  spacing_multiplier=2.0, stop_multiplier=20.0)
    kwargs.update(strat_kwargs)
    feed = _ScriptedBarFeed(barras, barras[:1] if semente is None else semente)
    rt = IntradayLiveRuntime(
        slot=SLOT, strategy=Gremah(**kwargs), config=_config(),
        bar_feed=feed, broker=_ExplodingBroker(),
        db_path=tmp_path / "live_intraday.sqlite",
        execution_mode=execution_mode, initial_capital=100.0,
    )
    rt.ensure_account()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = 100.0
        store.save_account(conn, acc)
    return rt, feed


@pytest.fixture
def pregao_aberto(monkeypatch):
    """Fixa o relogio dentro da fase OPEN do pregao de `SESSION` — `run_once`
    so age nessa fase (e no leilao de fechamento)."""
    from core.live_models import SessionPhase

    monkeypatch.setattr(live_clock, "phase", lambda *a, **k: SessionPhase.OPEN)
    monkeypatch.setattr(live_clock, "is_trading_day", lambda d: True)
    monkeypatch.setattr(live_clock, "session_date", lambda *a, **k: SESSION)
    monkeypatch.setattr(itr_mod.clock, "phase", lambda *a, **k: SessionPhase.OPEN)
    monkeypatch.setattr(itr_mod.clock, "is_trading_day", lambda d: True)
    monkeypatch.setattr(itr_mod.clock, "session_date", lambda *a, **k: SESSION)


def _agora(hhmm: str) -> datetime:
    return datetime.fromisoformat(f"2026-08-21 {hhmm}").replace(tzinfo=timezone.utc)


# ---------- modo sombra: nada sai para a corretora, nada mexe no caixa -----

def test_sombra_journaliza_entrada_e_saida_sem_tocar_a_corretora(tmp_path, pregao_aberto):
    """O dublê de corretora explode em qualquer chamada de execucao — se este
    teste passa, sombra nao mandou nada."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),  # abertura: arma o grid
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),    # toca o nivel long (9.80)
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),      # toca o alvo (9.90)
        _bar("13:03", 9.90, 9.90, 9.90, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras)

    passos = rt.run_once(now=_agora("13:05:00"))

    passo = [p for p in passos if p.action == "daytrade"][0]
    assert passo.detail["entradas"] == 1
    assert passo.detail["saidas"] == 1
    assert passo.detail["modo"] == "shadow"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        intents = store.all_intents(conn, acc.id)
        ordens = conn.execute(
            "SELECT * FROM live_orders WHERE account_id = ? ORDER BY id", (acc.id,)
        ).fetchall()
    assert len(intents) == 1
    assert len(ordens) == 2                       # entrada + saida
    assert all(o["broker_ref"] is None for o in ordens)
    assert all("SHADOW" in (o["note"] or "") for o in ordens)


def test_sombra_nao_debita_o_caixa_do_dono(tmp_path, pregao_aberto):
    """O caixa e' o numero que o dono digitou (ledger manual). Sujar isso com
    lucro/prejuizo imaginario destruiria a unica fonte de verdade de caixa
    que existe."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),
        _bar("13:03", 9.90, 9.90, 9.90, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras)

    rt.run_once(now=_agora("13:05:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
    assert acc.cash == pytest.approx(100.0)                     # intacto
    assert acc.policy_state["intraday"]["shadow_pnl_brl"] > 0    # o resultado foi para ca


def test_sombra_reporta_o_resultado_no_status_sem_misturar_com_o_caixa(tmp_path, pregao_aberto):
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),
        _bar("13:03", 9.90, 9.90, 9.90, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    rt.run_once(now=_agora("13:05:00"))

    s = rt.status()

    assert s["existe"] is True
    assert s["kind"] == "intraday"
    assert s["caixa"] == pytest.approx(100.0)
    assert s["daytrade"]["execution_mode"] == "shadow"
    assert s["daytrade"]["resultado_sombra"] > 0
    assert s["daytrade"]["trades_na_sessao"] == 1
    assert s["daytrade"]["simbolo"] == "PMAM3"


def test_modo_live_recusa_ordem_limite_pendente_ainda_nao_implementada(tmp_path, pregao_aberto):
    """`MT5Broker._send` so faz `TRADE_ACTION_DEAL` (a mercado). Enquanto a
    ordem pendente nao existir de verdade, `execution_mode="live"` tem de
    FALHAR alto em vez de silenciosamente virar uma ordem a mercado — que
    pagaria o spread e seria uma estrategia diferente da validada."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),   # fill em 9.80
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),     # alvo -> fecha e RECARREGA
    ]
    rt, _feed = _runtime(tmp_path, barras, execution_mode="live")

    with pytest.raises(NotImplementedError, match="ordem-limite pendente"):
        rt.run_once(now=_agora("13:04:00"))


def test_execution_mode_invalido_recusa_no_construtor():
    with pytest.raises(ValueError, match="execution_mode"):
        IntradayLiveRuntime(slot=SLOT, strategy=object(), config=_config(),
                            bar_feed=_ScriptedBarFeed([]), broker=_ExplodingBroker(),
                            execution_mode="talvez")


# ---------- penetration_ticks: a medicao que justifica a fase de sombra ----

def test_entrada_maker_grava_penetration_ticks_e_o_ohlc_da_barra(tmp_path, pregao_aberto):
    """Sem este campo, rodar em sombra nao responde a pergunta que motivou o
    modo: se os toques penetram 0-1 tick, a premissa de maker e' fragil (a
    ordem podia estar atras na fila); se as barras atravessam varios ticks,
    uma ordem parada quase certamente preenche."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.75, 9.85),   # atravessa 9.80 em 5 ticks
        _bar("13:02", 9.85, 9.86, 9.85, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)

    rt.run_once(now=_agora("13:04:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        intent = store.all_intents(conn, acc.id)[0]
    assert intent.payload["penetration_ticks"] == pytest.approx(5.0)
    assert intent.payload["order_kind"] == "limit"
    assert intent.payload["bar_ohlc"] == [10.00, 10.00, 9.75, 9.85]
    assert intent.payload["bar_volume"] == pytest.approx(1_000.0)
    assert intent.payload["execution_mode"] == "shadow"


def test_penetracao_de_um_tick_e_registrada_como_um_tick(tmp_path, pregao_aberto):
    """O caso fragil: a barra so raspou o nivel. Tem de aparecer como 1 tick,
    nao ser arredondado para "preencheu tranquilo"."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),   # 9.80 - 9.79 = 1 tick
        _bar("13:02", 9.85, 9.86, 9.85, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    rt.run_once(now=_agora("13:04:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        intent = store.all_intents(conn, acc.id)[0]
    assert intent.payload["penetration_ticks"] == pytest.approx(1.0)


# ---------- short: quantidade negativa em live_positions ------------------

def test_short_grava_quantidade_negativa_na_posicao(tmp_path, pregao_aberto):
    """Short foi verificado no terminal real (2026-08-21). `live_positions.
    quantity` negativa faz a marcacao a mercado sair correta sem nenhuma
    mudanca de schema: `market_value = price * quantity` fica negativo, que e'
    exatamente o que uma posicao vendida vale."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),   # long em 9.80
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),     # alvo 9.90 -> fecha long
        # A recarga seguinte e' do OUTRO lado (short), ancorada na abertura:
        # 10.00 + 20 ticks de espacamento = 10.20. Esta barra atravessa.
        _bar("13:03", 9.90, 10.21, 9.90, 10.15),
    ]
    rt, _feed = _runtime(tmp_path, barras)

    rt.run_once(now=_agora("13:05:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
    pos = acc.positions.get("PMAM3")
    assert pos is not None
    assert pos.quantity < 0
    assert pos.metadata["side"] == "short"
    assert pos.market_value(10.00) < 0


# ---------- despacho warm-start / frio (politica de 2026-08-21) -----------

def test_liga_antes_do_corte_faz_warm_start_com_as_barras_reais(tmp_path, pregao_aberto):
    """Ligar dentro da janela de ancora FIXA exige recalibrar com as barras
    reais desde a abertura — senao o robo adotaria como "abertura" a primeira
    barra que vir e ficaria deslocado o dia inteiro."""
    semente = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.05, 10.00, 10.05),
    ]
    barras = [_bar("13:02", 10.05, 10.05, 9.79, 9.85)]
    rt, feed = _runtime(tmp_path, barras, semente=semente,
                        fixed_anchor_until=time(14, 0))

    passos = rt.run_once(now=_agora("13:03:00"))

    sessao = [p for p in passos if p.action == "daytrade_sessao"][0]
    assert sessao.detail["inicio"] == "warm_start"
    assert sessao.detail["barras_semente"] == 2
    assert feed.pedidos_de_semente  # o historico foi de fato buscado
    # A ordem calibrada com a abertura REAL (10.00) e' 9.80, e a barra ao vivo
    # a toca -- se tivesse calibrado com 10.05, o nivel seria outro.
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        intents = store.all_intents(conn, acc.id)
    assert len(intents) == 1
    assert intents[0].payload["bar_ts"].startswith("2026-08-21T13:02")


def test_warm_start_nao_fabrica_trade_das_barras_da_semente(tmp_path, pregao_aberto):
    """O replay e' SO calibracao. Nenhum trade das barras que o robo nao
    operou pode aparecer no diario nem no resultado."""
    # A semente tem uma barra que TOCARIA o nivel 9.80 se fosse operada.
    semente = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.70, 9.75),
        _bar("13:02", 9.75, 9.95, 9.75, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras=[], semente=semente,
                         fixed_anchor_until=time(14, 0))

    rt.run_once(now=_agora("13:03:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        intents = store.all_intents(conn, acc.id)
    assert intents == []
    assert acc.policy_state["intraday"]["shadow_pnl_brl"] == pytest.approx(0.0)
    assert acc.policy_state["intraday"]["trades"] == 0


def test_liga_depois_do_corte_comeca_a_frio_sem_buscar_semente(tmp_path, pregao_aberto):
    """Politica decidida em 2026-08-21 (a virada que promoveu o campeao): se
    nao sobra janela de ancora fixa, NAO fazer warm start. Carregar uma ordem
    fixa ja obsoleta custava uma barra inteira de defasagem, porque a
    obsolescencia so era detectavel DENTRO de `on_bar`."""
    barras = [
        _bar("15:00", 9.00, 9.00, 9.00, 9.00),
        _bar("15:01", 9.00, 9.00, 8.90, 8.95),
    ]
    rt, feed = _runtime(tmp_path, barras, semente=[_bar("13:00", 10.0, 10.0, 10.0, 10.0)],
                        fixed_anchor_until=time(14, 0))

    passos = rt.run_once(now=_agora("15:02:00"))

    sessao = [p for p in passos if p.action == "daytrade_sessao"][0]
    assert sessao.detail["inicio"] == "cold"
    assert feed.pedidos_de_semente == []  # nem tentou buscar o historico


def test_comeco_a_frio_nao_consome_as_barras_que_ja_passaram(tmp_path, pregao_aberto):
    """Comecar a frio significa "opero da proxima barra em diante". Engolir as
    240 barras que o terminal devolve por padrao faria o robo tomar 240
    decisoes contra precos que ja passaram."""
    barras = [_bar(f"15:{m:02d}", 9.00, 9.02, 8.98, 9.00) for m in range(0, 20)]
    rt, _feed = _runtime(tmp_path, barras, fixed_anchor_until=time(14, 0))

    passos = rt.run_once(now=_agora("15:25:00"))

    assert [p.action for p in passos if p.action == "daytrade_buraco"] == []
    # nada foi consumido nesta primeira chamada: a ultima barra fechada virou
    # a marca de partida.
    assert [p.action for p in passos if p.action == "daytrade"] == []


# ---------- buraco de barras: nunca executa decisao velha -----------------

def test_buraco_grande_achata_e_nao_reprocessa(tmp_path, pregao_aberto):
    """Regra 7 do AGENTS.md, versao intradiaria: decisao velha nao executa, e
    o buraco tambem nao e' ignorado — a posicao e' achatada no preco mais
    recente e a sessao recomeca dali."""
    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    # 1a chamada: entra. 2a chamada: um buraco enorme.
    barras = [
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),  # fill em 9.80
    ]
    rt, feed = _runtime(tmp_path, barras, semente=semente, fixed_anchor_until=time(14, 0))
    rt.run_once(now=_agora("13:02:00"))
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
    assert "PMAM3" in acc.positions  # posicao aberta antes do buraco

    feed._barras = barras + [
        _bar(f"13:{m:02d}", 9.50, 9.52, 9.48, 9.50) for m in range(2, 2 + MAX_GAP_BARS + 2)
    ]
    passos = rt.run_once(now=_agora("13:30:00"))

    buraco = [p for p in passos if p.action == "daytrade_buraco"]
    assert len(buraco) == 1
    assert buraco[0].detail["achatou"] is True
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = store.recent_events(conn, acc.id)
    assert "PMAM3" not in acc.positions
    assert any(e["level"] == "error" and "buraco" in e["message"] for e in eventos)


def test_buraco_recalibra_no_passo_seguinte(tmp_path, pregao_aberto):
    """Depois de achatar, o pregao CONTINUA: o robo tem de ser recalibrado
    (ainda ha janela fixa) em vez de adotar como abertura a primeira barra
    que vir depois do buraco."""
    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, feed = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))
    rt.run_once(now=_agora("13:01:00"))

    feed._barras = [_bar(f"13:{m:02d}", 9.50, 9.52, 9.48, 9.50)
                    for m in range(1, 1 + MAX_GAP_BARS + 2)]
    rt.run_once(now=_agora("13:25:00"))

    feed._barras = feed._barras + [_bar("13:26", 9.50, 9.52, 9.48, 9.50)]
    feed._semente = semente + [_bar(f"13:{m:02d}", 9.50, 9.52, 9.48, 9.50) for m in range(1, 26)]
    passos = rt.run_once(now=_agora("13:27:00"))

    sessao = [p for p in passos if p.action == "daytrade_sessao"]
    assert len(sessao) == 1
    assert sessao[0].detail["inicio"] == "warm_start"


# ---------- fora de hora / sem conta -------------------------------------

def test_fora_da_fase_open_nao_le_barra_nenhuma(tmp_path, monkeypatch):
    from core.live_models import SessionPhase

    monkeypatch.setattr(itr_mod.clock, "phase", lambda *a, **k: SessionPhase.POST_CLOSE)
    monkeypatch.setattr(itr_mod.clock, "is_trading_day", lambda d: True)
    monkeypatch.setattr(itr_mod.clock, "session_date", lambda *a, **k: SESSION)

    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime(tmp_path, barras)

    passos = rt.run_once(now=_agora("21:00:00"))

    assert [p.action for p in passos] == ["idle"]


def test_dia_sem_pregao_nao_faz_nada(tmp_path, monkeypatch):
    from core.live_models import SessionPhase

    monkeypatch.setattr(itr_mod.clock, "phase", lambda *a, **k: SessionPhase.OPEN)
    monkeypatch.setattr(itr_mod.clock, "is_trading_day", lambda d: False)
    monkeypatch.setattr(itr_mod.clock, "session_date", lambda *a, **k: SESSION)

    rt, _feed = _runtime(tmp_path, [_bar("13:00", 10.0, 10.0, 10.0, 10.0)])

    assert [p.action for p in rt.run_once(now=_agora("13:05:00"))] == ["idle"]


def test_sem_conta_nao_opera_e_reporta_skip(tmp_path, pregao_aberto):
    from strategy.daytrade.lab.gremah import Gremah

    rt = IntradayLiveRuntime(
        slot=SLOT, strategy=Gremah(symbol=SYMBOL), config=_config(),
        bar_feed=_ScriptedBarFeed([_bar("13:00", 10.0, 10.0, 10.0, 10.0)]),
        broker=_ExplodingBroker(), db_path=tmp_path / "vazio.sqlite",
    )

    passos = rt.run_once(now=_agora("13:05:00"))

    assert [p.action for p in passos] == ["daytrade_skip"]
    assert rt.status() == {"conta": SLOT.id, "existe": False}


def test_broker_de_modo_divergente_e_erro_fatal(tmp_path, pregao_aberto):
    """Mesma guarda do lado diario: uma conta e um broker de modos diferentes
    nunca podem operar juntos."""
    from strategy.daytrade.lab.gremah import Gremah

    rt, _feed = _runtime(tmp_path, [])

    class _OutroModo(_ExplodingBroker):
        mode = "outro"

    rt2 = IntradayLiveRuntime(
        slot=SLOT, strategy=Gremah(symbol=SYMBOL), config=_config(),
        bar_feed=_ScriptedBarFeed([]), broker=_OutroModo(), db_path=rt.db_path,
    )
    with pytest.raises(ValueError, match="divergentes"):
        rt2.run_once(now=_agora("13:05:00"))


# ---------- persistencia entre passos e entre processos -------------------

def test_estado_da_sessao_sobrevive_a_um_processo_novo(tmp_path, pregao_aberto):
    """Ao vivo o processo pode reiniciar no meio do pregao: sem persistir a
    posicao, o robo esqueceria que esta comprado e abriria outra."""
    from strategy.daytrade.lab.gremah import Gremah

    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    barras = [_bar("13:01", 10.00, 10.00, 9.79, 9.85)]  # fill em 9.80
    rt, _feed = _runtime(tmp_path, barras, semente=semente, fixed_anchor_until=time(14, 0))
    rt.run_once(now=_agora("13:02:00"))

    # processo NOVO, mesmo banco
    rt2 = IntradayLiveRuntime(
        slot=SLOT, strategy=Gremah(symbol=SYMBOL, tick_size=0.01, profit_pct=0.01,
                                   fixed_anchor_until=time(14, 0)),
        config=_config(),
        bar_feed=_ScriptedBarFeed(barras, semente), broker=_ExplodingBroker(),
        db_path=rt.db_path, initial_capital=100.0,
    )
    rt2.run_once(now=_agora("13:03:00"))

    assert rt2.machine.position is not None
    assert rt2.machine.position.entry_price == pytest.approx(9.80)
    s = rt2.status()
    assert s["daytrade"]["posicao_aberta"]["entrada"] == pytest.approx(9.80)


def test_estado_de_outro_pregao_e_descartado(tmp_path, pregao_aberto):
    """Day trade nao carrega nada para o dia seguinte — um estado de ontem nao
    e' estado, e' lixo."""
    rt, _feed = _runtime(tmp_path, [])
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.policy_state = {"intraday": {
            "session": "2026-08-20", "last_bar_ts": "2026-08-20T19:00:00+00:00",
            "shadow_pnl_brl": 999.0, "trades": 7,
            "machine": {"session_date": "2026-08-20", "position": {
                "side": "long", "entry_ts": "2026-08-20T14:00:00+00:00",
                "entry_price": 1.0, "quantity": 1, "current_stop": None,
                "current_target": None, "bars_held": 3, "metadata": {}}},
        }}
        store.save_account(conn, acc)

    rt.run_once(now=_agora("13:05:00"))

    assert rt.machine.position is None
    assert rt._snapshot.session == SESSION
    assert rt._snapshot.shadow_pnl_brl == pytest.approx(0.0)


def test_sem_barra_nova_apenas_espera(tmp_path, pregao_aberto):
    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))

    passos = rt.run_once(now=_agora("13:01:00"))

    assert any(p.action == "daytrade_espera" for p in passos)


def test_status_reporta_fuso_corte_e_ordem_em_pe(tmp_path, pregao_aberto):
    """Um offset de servidor errado nao produz erro nenhum — produz o robo
    rodando a fase errada em silencio. O painel tem de mostrar o fuso em uso, o
    minuto em que vai achatar (que MUDA com o horario de verao dos EUA) e se a
    conferencia do relogio acusou algo."""
    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))
    rt.run_once(now=_agora("13:01:00"))

    s = rt.status()

    assert s["daytrade"]["offset_horas"] == pytest.approx(3.0)
    assert s["daytrade"]["relogio_alarme"] is None
    # SESSION cai em 21/08/2026, dentro do horario de verao dos EUA
    assert s["daytrade"]["corte_flatten_utc"] == "19:54:00"
    assert s["daytrade"]["ordem_em_pe"]["lado"] == "long"
    assert s["daytrade"]["ordem_em_pe"]["preco"] == pytest.approx(9.80)


# ---------- conferencia do relogio do servidor -----------------------------

class _FakeClockFeed:
    """Dublê de `MT5Feed` no papel de CONFERENTE do relogio. Conta as
    conferencias para provar que ela roda uma vez por pregao, e nao por barra
    (cada conferencia e' uma leitura de tick a mais no terminal)."""

    def __init__(self, alarme=None):
        self._alarme = alarme
        self.conferencias = 0

    @property
    def server_clock_alarm(self):
        return self._alarme

    def verify_server_clock(self, reference_ticker=None):
        self.conferencias += 1
        return self._alarme


def test_relogio_do_servidor_divergente_impede_operar(tmp_path, pregao_aberto):
    """Todo horario que este robo usa — corte de flatten, troca de ancora
    fixa/rolante, "esta barra ja fechou" — e' comparacao contra o relogio do
    servidor. Errar o fuso em 1h nao levanta excecao: faz o robo executar a
    fase errada o dia inteiro. Preferimos um pregao sem operar."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),  # tocaria o nivel long
    ]
    rt, _feed = _runtime(tmp_path, barras)
    rt.clock_feed = _FakeClockFeed(alarme="tick de PETR4.SA esta 60min velho")

    passos = rt.run_once(now=_agora("13:02:30"))

    assert [p.action for p in passos] == ["daytrade_skip"]
    assert passos[0].detail["motivo"] == "relogio do servidor"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = store.recent_events(conn, acc.id, limit=10)
    assert any(e["level"] == "error" and "nao vou operar" in e["message"] for e in eventos)


def test_relogio_conferido_uma_vez_por_pregao(tmp_path, pregao_aberto):
    """O fuso do servidor nao muda no meio do dia, e cada conferencia custa uma
    leitura de tick — entao ela roda uma vez, nao a cada barra."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    conferente = _FakeClockFeed(alarme=None)
    rt.clock_feed = conferente

    rt.run_once(now=_agora("13:02:30"))
    rt.run_once(now=_agora("13:03:30"))
    rt.run_once(now=_agora("13:04:30"))

    assert conferente.conferencias == 1


def test_sem_conferente_o_runtime_opera_normal(tmp_path, pregao_aberto):
    """`clock_feed=None` (o caso de teste, com feed de barras sintetico) nao
    pode bloquear: nao existe relogio de servidor para conferir."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    assert rt.clock_feed is None

    passos = rt.run_once(now=_agora("13:02:30"))

    assert not any(p.action == "daytrade_skip" for p in passos)


def test_conta_de_day_trade_nao_tem_robo_de_saque(tmp_path, pregao_aberto):
    """Day trade nao tem overlay de saque: a posicao morre no fim do pregao,
    entao nao existe patrimonio investido de onde skimar. O painel mostra a
    verdade em vez de herdar o robo de saque do swing."""
    rt, _feed = _runtime(tmp_path, [])

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
    assert acc.withdrawal_robot == ""
    assert acc.investment_robot == "gremah"
