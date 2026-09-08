"""Testes de `live/intraday_runtime.py::IntradayLiveRuntime` — o robo de day
trade operando ao vivo, em MODO SOMBRA.

Nenhum destes testes toca no terminal MT5 nem na corretora: o feed de barras
e' um dublê que devolve barras roteirizadas, e o broker e' um dublê que
EXPLODE se alguem tentar mandar ordem (e' assim que se prova que sombra e'
sombra de verdade).

O que esta em jogo, em ordem de importancia:
  1. sombra nunca chama a corretora e nunca debita o caixa do dono;
  2. `penetration_ticks` e `volume_no_nivel` sao gravados — e' a medicao que
     justifica a fase de sombra (a premissa de maker do robo nunca foi
     verificada contra o mercado real, ver a docstring do modulo testado);
  3. a posicao e' dimensionada pelo capital REAL do slot, nunca pelos
     R$20.000 do default do `IntradayBacktestConfig`;
  4. o despacho warm-start/frio segue a politica decidida em 2026-08-21
     (`pmam3_daytrade_champion` na memoria do projeto);
  5. um buraco NO PROCESSO (tempo sem rodar, nao eventos acumulados) nao
     executa decisao velha nem deixa posicao orfa.
"""
from __future__ import annotations

import re

from dataclasses import replace
from datetime import date, datetime, time, timezone

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.machine import IntradayBacktestConfig, IntradayTrade
from backtest.intraday.profiles import FUTURES_PROFILES
from core.config import slot_by_id
from core.live_models import AccountState, LivePosition, OrderSide, OrderStatus, OrderType
from core.models import IntradayExitReason
from journal import live_store as store
from live import clock as live_clock
from live import intraday_runtime as itr_mod
from live.intraday_runtime import MAX_GAP_SECONDS, IntradayLiveRuntime
from strategy.daytrade.base import Bar, Enter, EnterLimit, IntradayStrategy

# O slot de day trade e' DINAMICO desde 2026-08-22: o id carrega robo+ativo
# e, desde 2026-08-24, o modo de execucao (`dt-<robo>-<ativo>-<modo>`) -- o
# painel abre quantos o dono quiser. Nao existe mais um slot fixo chamado
# "daytrade".
SYMBOL = "PMAM3"
SLOT = slot_by_id("dt-gremah-pmam3-shadow")
# Slot de FUTURO para os testes do bug de caixa corrigido 2026-08-31 (preco
# de WIN@/WDO@ vem em PONTOS, nao em reais -- caixa/margem tem de usar
# `margin_per_contract_brl`, nunca `preco * quantidade`). "gremah" aqui e'
# so' o robo de teste (generico o bastante pra operar qualquer simbolo);
# nao precisa ser o robo real de producao do WIN@ (`copa_win`).
SLOT_WIN = slot_by_id("dt-gremah-win@-shadow")
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
    #: Os dois feeds de verdade declaram este campo (`MT5TickFeed` 0.0,
    #: `MT5BarFeed` 60.0) e desde 2026-09-08 o runtime LE ele para montar o
    #: teto de idade de barra (`_limite_de_atraso`). O dublê declara junto:
    #: 0.0 = "tick", que e' o que estes roteiros imitam (barra com o ts do
    #: instante em que o preco aconteceu).
    nominal_delay_seconds = 0.0

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
        return [b for b in self._semente if b.ts.date() == session and b.ts <= until_ts]


def _bar(hhmm: str, o, h, low, c) -> Bar:
    return Bar(ts=pd.Timestamp(f"2026-08-21 {hhmm}", tz="UTC"),
               open=float(o), high=float(h), low=float(low), close=float(c), volume=1_000.0)


def _config() -> IntradayBacktestConfig:
    return IntradayBacktestConfig(
        costs=IntradayCostModel(point_value_brl=1.0, tick_size=0.01,
                               fee_round_trip_brl=0.0, slippage_ticks=0.0),
        # `IntradayLiveRuntime` sempre sobrescreve com o capital real do slot
        # (ver `replace(config, initial_capital=...)` no construtor) -- este
        # valor nunca chega a valer para nenhum teste deste arquivo.
        initial_capital=0.0,
        # Mesma politica da producao (PMAM3 e' acao): o corte sai do
        # calendario, nao de um numero fixo. Em 21/08/2026 (horario de verao
        # dos EUA) isso da 19:54 UTC, que era o valor congelado — de proposito,
        # para o roteiro de barras destes testes continuar valendo.
        session_end_policy="b3_equities",
        target_fills_as_maker=True,
        default_quantity=1,
    )


def _config_futuro(margin_per_contract_brl: float) -> IntradayBacktestConfig:
    """`_config()` com margem de futuro ligada -- liga junto o teto por
    capital (`_cap_capital_atual`, `backtest/intraday/machine.py`), entao
    quem usa isto PRECISA passar `initial_capital=` bem acima da margem (ver
    docstring de `_runtime`), senao a entrada e' recusada por teto antes de
    virar caixa pra medir."""
    return replace(_config(), margin_per_contract_brl=margin_per_contract_brl)


def _runtime(tmp_path, barras, semente=None, execution_mode="shadow", feed=None,
             symbol=SYMBOL, slot=None, config=None, initial_capital=100.0,
             **strat_kwargs):
    """`semente` default = a PRIMEIRA barra de `barras` (a abertura do pregao).

    E' o caso realista de ligar dentro da janela de ancora fixa: o warm start
    recalibra com a abertura real e as barras seguintes chegam ao vivo. Sem
    isto, o robo cairia em comeco a frio e a marca de partida engoliria todas
    as barras do roteiro -- o teste passaria sem o robo ter operado nada.

    `feed`: dublê de feed proprio, para quem precisa de um comportamento que
    `_ScriptedBarFeed` nao tem (ex.: barra que so' aparece na SEGUNDA
    consulta ao terminal).

    `symbol`/`slot`/`config`/`initial_capital`: default = mesmo cenario de
    sempre (PMAM3, acao, sem margem). Os testes de FUTURO (WIN@/WDO@, bug de
    caixa corrigido 2026-08-31) passam `config=` com `margin_per_contract_brl`
    ligado -- e precisam de `initial_capital` bem acima do default, senao o
    proprio teto por capital (`_cabe_no_teto`) recusa a entrada antes de
    qualquer coisa virar caixa pra' medir."""
    from strategy.daytrade.lab.gremah import Gremah

    kwargs = dict(symbol=symbol, tick_size=0.01, profit_pct=0.01,
                  spacing_multiplier=2.0, stop_multiplier=20.0,
                  # Filtro de qualidade de entrada (2026-08-27) e' PADRAO
                  # `True` desde entao -- desligado aqui porque este roteiro
                  # de barras testa a mecanica ao vivo (fill, persistencia,
                  # journal), nao o filtro em si (ver `tests/test_gremah.py`
                  # para os testes dedicados a ele), e as barras sinteticas
                  # daqui entram logo na abertura (minutos_desde_abertura~0).
                  filtro_minutos_desde_abertura_min=None,
                  filtro_volume_toque_max=None)
    kwargs.update(strat_kwargs)
    if feed is None:
        feed = _ScriptedBarFeed(barras, barras[:1] if semente is None else semente)
    slot = slot or SLOT
    rt = IntradayLiveRuntime(
        slot=slot, strategy=Gremah(**kwargs), config=config or _config(),
        bar_feed=feed, broker=_ExplodingBroker(),
        db_path=tmp_path / "live_intraday.sqlite",
        execution_mode=execution_mode, initial_capital=initial_capital,
    )
    rt.ensure_account()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, slot.id)
        acc.cash = initial_capital
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
    monkeypatch.setattr(itr_mod.clock, "intraday_session", lambda *a, **k: SESSION)


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


# ---------- numero de rodada no diario (2026-08-24) -------------------------

def test_numero_de_ordem_e_o_mesmo_do_armar_ate_a_saida_e_avanca_na_proxima_rodada(
    tmp_path, pregao_aberto,
):
    """Pedido do dono: o diario tem de deixar claro qual `entrada`/`saida`
    pertence a qual `ordem posicionada`, mesmo com mais de uma rodada no mesmo
    pregao -- sem isto, so' dava pra saber "quem disparou" lendo o codigo
    (o que motivou a pergunta 3x numa mesma conversa). A 1a rodada tem de
    carimbar `#01` em posicionada/entrada/saida; a 2a tem de vir com `#02` do
    jeito, mesmo entrelacada no mesmo `run_once`.

    ROTEIRO ATUALIZADO em 2026-08-28. O de antes assumia que "a recarga
    seguinte e' do OUTRO lado (short)" -- alternancia pura, que
    `_next_side_to_arm` deixou de fazer em 2026-08-26 (memoria
    `gremah_repetir_ultimo_vencedor`: depois de um trade LUCRATIVO o robo
    REPETE o lado, e isso venceu em 9/9 simbolos). Como a #01 fecha no alvo,
    a #02 tambem e' long -- o teste ficou vermelho por dois dias medindo um
    comportamento que o robo nao tem mais. O que ele mede continua sendo o
    NUMERO da rodada, nao o lado."""
    # ROTEIRO COMPRIMIDO em 2026-09-08: as barras andam de 20 em 20s (nao
    # de minuto em minuto) e `now` fica logo depois da ultima. Motivo:
    # desde `MAX_ATRASO_PARA_ORDEM_SEGUNDOS`, barra mais velha que o teto
    # nao gera ORDEM NOVA -- e um roteiro de 6 minutos consumido num
    # `run_once` so' deixava a barra de abertura com 5+ min de idade. O
    # que este teste mede (sequencia de OHLC, numeracao, P&L) nao depende
    # do espacamento; a idade agora depende.
    barras = [
        _bar("13:00:00", 10.00, 10.00, 10.00, 10.00),  # abertura: arma a 1a (long)
        _bar("13:00:20", 10.00, 10.00, 9.79, 9.85),    # toca o nivel long (9.80)
        _bar("13:00:40", 9.85, 9.91, 9.85, 9.90),      # toca o alvo (9.90) -- fecha #01
        _bar("13:01:00", 9.90, 9.90, 9.79, 9.85),      # repete LONG e ja' preenche #02
        _bar("13:01:20", 9.85, 9.91, 9.85, 9.90),      # toca o alvo de novo -- fecha #02
        _bar("13:01:40", 9.90, 9.90, 9.90, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras)

    passos = rt.run_once(now=_agora("13:01:45"))

    passo = [p for p in passos if p.action == "daytrade"][0]
    assert passo.detail["entradas"] == 2 and passo.detail["saidas"] == 2

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in reversed(store.recent_events(conn, acc.id, limit=50))]

    # So' os 5 eventos de ORDEM, na ordem em que aconteceram -- o resto (aviso
    # de capital para outro ativo, sessao) nao carrega numero.
    de_ordem = [m for m in eventos if "#0" in m]
    # Formato pedido pelo dono em 2026-08-25 (ver `_lotes_txt` e
    # `_MOTIVO_SAIDA_TXT`): evento na frente, sem "SOMBRA", tamanho em lotes.
    # "100 lotes" aqui NAO e' erro: `_config()` deste arquivo usa
    # `default_quantity=1` (lote sintetico de 1 acao, pra caber no capital de
    # R$100 dos roteiros) -- em producao PMAM3 tem lote de 100, e a mesma
    # ordem sai como "1 lote". Quem prova a conversao com o lote real e'
    # `test_lotes_txt_*`.
    assert de_ordem == [
        "LONG #01 100 lotes PMAM3 @ 9.8000 (stop 7.8000 / alvo 9.9000)",
        "TARGET LONG #01 100 lotes PMAM3 @ 9.9000 - R$ +10.00",
        "LIMITE LONG #02 100 lotes PMAM3 @ 9.8000 (stop 7.8000 / alvo 9.9000)",
        "LONG #02 100 lotes PMAM3 @ 9.8000 (stop 7.8000 / alvo 9.9000)",
        "TARGET LONG #02 100 lotes PMAM3 @ 9.9000 - R$ +10.00",
        # o robo se rearma de novo com a ultima barra do roteiro -- rodada
        # #03, ainda sem fill: prova que o numero segue avancando (nao
        # empaca em #02) mesmo sem uma saida fechando-a antes do fim do teste.
        "LIMITE LONG #03 100 lotes PMAM3 @ 9.8000 (stop 7.8000 / alvo 9.9000)",
    ], de_ordem


def test_numero_de_ordem_sobrevive_a_restart_do_processo(tmp_path, pregao_aberto):
    """O numero de rodada precisa sobreviver a um restart no MEIO do pregao
    (`_SessionSnapshot.trade_seq`/`trade_num`, persistidos em
    `policy_state["intraday"]`, mesmo padrao de `ordens_postas`) -- senao um
    processo que cai e volta depois da rodada #03 recomecaria contando de
    #01, e duas rodadas DIFERENTES do mesmo dia apareceriam com o MESMO
    numero no diario, exatamente o problema que este numero existe pra
    resolver."""
    rt, _feed = _runtime(tmp_path, [_bar("13:00", 10.00, 10.00, 10.00, 10.00)])
    rt._snapshot.session = SESSION
    rt._snapshot.trade_seq = 3
    rt._snapshot.trade_num = None  # rodada #3 ja fechou, ninguem armado agora
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        rt._persist(conn, acc)

    # "reinicia o processo": runtime NOVO, mesmo banco -- sem nenhuma memoria
    # em Python do que o processo anterior tinha contado.
    rt_novo, _feed2 = _runtime(tmp_path, [_bar("13:00", 10.00, 10.00, 10.00, 10.00)])
    with store.live_journal(rt_novo.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
    rt_novo._restore(acc, SESSION)

    assert rt_novo._snapshot.trade_seq == 3
    assert rt_novo._numero_ordem_atual() == 4, (
        "a proxima rodada tem que continuar a contagem, nao reiniciar em #01"
    )


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
    # `cash_sombra` (saldo PARALELO, separado do caixa real) e' quem recebe o
    # resultado sombra como SALDO -- pedido do dono 2026-08-23 ("separe os
    # dois valores"), pra nunca arriscar o numero simulado vazar pro caixa
    # real quando a conta troca de sombra pra live.
    assert acc.cash_sombra == pytest.approx(100.0 + acc.policy_state["intraday"]["shadow_pnl_brl"])


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
    assert s["daytrade"]["caixa_sombra"] == pytest.approx(100.0 + s["daytrade"]["resultado_sombra"])
    assert s["daytrade"]["trades_na_sessao"] == 1
    assert s["daytrade"]["simbolo"] == "PMAM3"


# ---------- execucao REAL: a corretora e' a fonte de verdade do fill -------
#
# O ponto de todos os testes desta secao: em `execution_mode="live"` a barra
# DEIXA de decidir se a ordem preencheu. Uma barra que atravessa o nivel com
# a corretora reportando conta zerada = nao preencheu. Ver
# `live/intraday_execution.py`.

class _FakeMT5Broker:
    """Corretora falsa com o contrato que `MT5IntradayExecution` usa:
    `connect`, `place_pending`, `cancel`, `open_position`, `place`,
    `close_position`, `set_protection`, `account_risk_state`, `last_price`.

    `posicao` e' o que a corretora "tem" -- o teste escreve nela para simular
    o fill (ou a ausencia dele) sem depender de OHLC nenhum."""

    name = "fake_mt5"
    mode = "mt5"

    def __init__(self, conectado=True):
        self.conectado = conectado
        self.posicao = None
        self.pendentes_enviadas: list = []
        self.canceladas: list = []
        self.ordens_a_mercado: list = []
        self._ticket = 1000
        # `None` = nada de outro magic no papel; o teste escreve aqui pra
        # simular o retorno de `MT5Broker.foreign_activity()` de verdade
        # (ver `_check_atividade_estranha` em `intraday_runtime.py`).
        self.atividade_estranha = None
        # Gap (a): tickets recebidos em CADA chamada de `close_position` --
        # prova de que o fechamento sempre leva o ticket da posicao REAL,
        # nunca manda ordem "as cegas".
        self.close_tickets: list = []
        # Gap (c): chamadas de `set_protection`, na ordem -- cada item e'
        # `(ticket, side, stop, target)`.
        self.protecoes: list = []
        # `None` = sem resposta configurada (metodo ausente no double antigo
        # -- ver os testes que usam `del broker.set_protection`/etc para
        # simular um broker que nao suporta o gap ainda). Testes de gap (c)
        # setam isto para controlar sucesso/recusa.
        self.protecao_ok = True
        self.protecao_note = "protecao registrada"
        # Gap (e): estado de risco que `_check_freio_duro` le. `None` =
        # "nao deu pra perguntar" (mesma politica do broker real).
        self.risco = None
        # Gap (e)/(f): usado pelo freio duro para achar preco de referencia
        # quando `open_position()` ja nao tem mais posicao NENHUMA pra
        # marcar (o cenario comum: acabou de fechar) -- e' o preco usado
        # pra fechar A MERCADO quando ha posicao viva.
        self.ultimo_preco = 9.90
        # Gap (a)/(f): quando `True`, `close_position`/`place` (usados no
        # caminho de fechamento) SEMPRE recusam -- simula a recusa
        # persistente do incidente real (MG51).
        self.recusa_fechamento = False
        self.motivo_recusa_fechamento = "MT5 recusou a ordem (retcode=10006): [MG51] Para abrir novas posicoes"
        # Quando `True`, `position_state` responde "NAO CONSEGUI LER" em vez
        # de "nao ha posicao" -- os dois eram indistinguiveis antes de
        # 2026-08-28 (`open_position` devolvia `None` para ambos), e e' a
        # confusao que fazia um terminal fora do ar virar "conta zerada".
        self.leitura_falha = False
        # Ultimo par (sl, tp) que `set_protection` registrou -- so' para
        # inspecao nos testes de protecao.
        self.posicao_sl_tp = (0.0, 0.0)
        # `pending_orders()`: `None` = "nao consegui perguntar" (default, o
        # comportamento que todo teste anterior via, porque o metodo nao
        # existia). Lista = a corretora respondeu.
        self.pendentes_na_corretora = None
        # `margin_required()`: `None` = "nao sei" (nunca bloqueia). Numero =
        # margem em R$ POR CONTRATO/ACAO que a corretora exigiria.
        self.margem_por_contrato = None
        self.margens_perguntadas: list = []
        # Gap 1.15 (2026-09-03): `position_ticket` recebido em CADA chamada
        # de `place_pending`, na mesma ordem de `pendentes_enviadas` -- prova
        # de que a fatia de SAIDA (`place_exit_limit`) leva o ticket da
        # posicao real, e a de ENTRADA (`place_limit`) continua sem ele
        # (`None`, nunca fecha nada).
        self.pending_position_tickets: list = []

    def connect(self):
        return self.conectado

    def foreign_activity(self, ticker):
        return self.atividade_estranha

    def supports_automation(self):
        return True

    def cash_balance(self):
        raise AssertionError("o caixa do slot vem do ledger manual, nao da corretora")

    def poll(self, order):
        return order

    def place_pending(self, order, position_ticket=None):
        self._ticket += 1
        order.status = OrderStatus.SENT
        order.broker_ref = str(self._ticket)
        self.pendentes_enviadas.append(order)
        self.pending_position_tickets.append(position_ticket)
        return order

    def cancel(self, order):
        order.status = OrderStatus.CANCELLED
        self.canceladas.append(order)
        return order

    def open_position(self, ticker):
        return self.posicao

    def position_state(self, ticker):
        """Tri-estado do port (`Broker.position_state`): distingue "não há
        posição" de "não consegui perguntar". Um dublê lê estado em memória,
        então a consulta só falha quando o teste manda (`leitura_falha`)."""
        if self.leitura_falha:
            return {"ok": False, "position": None,
                    "note": "leitura de posicao falhou (simulado no teste)"}
        return {"ok": True, "position": self.posicao, "note": ""}

    def last_price(self, ticker):
        return self.ultimo_preco

    def _preenche_fechamento(self, order):
        if self.recusa_fechamento:
            order.status = OrderStatus.REJECTED
            order.note = self.motivo_recusa_fechamento
            return order
        self.ordens_a_mercado.append(order)
        order.status = OrderStatus.FILLED
        order.filled_qty = order.quantity
        order.avg_price = self.preco_de_saida
        order.broker_ref = "saida-9999"
        self.posicao = None
        return order

    def place(self, order):
        """Ordem a mercado (fechamento) -- preenche a `preco_de_saida`.

        So' e' o caminho usado quando o fechamento NAO leva ticket (ver
        `close_position` abaixo, que e' o caminho normal desde o gap (a))."""
        return self._preenche_fechamento(order)

    def close_position(self, order, position_ticket):
        """Fechamento DEDICADO (gap (a)) -- grava o ticket recebido em
        `close_tickets` antes de preencher exatamente como `place()`, pra
        os testes existentes (que checam `ordens_a_mercado`) continuarem
        valendo e os testes NOVOS (que checam `close_tickets`) confirmarem
        que o ticket chegou."""
        self.close_tickets.append(position_ticket)
        return self._preenche_fechamento(order)

    def set_protection(self, ticker, position_ticket, side, stop=None, target=None,
                       sl_atual=0.0, tp_atual=0.0):
        # `sl_atual`/`tp_atual`: o que a corretora tem REGISTRADO agora. O
        # broker real usa para nunca APAGAR o lado sem pedido nem AFROUXAR um
        # stop ja registrado (`MT5Broker._niveis_protecao`). Aqui o dublê so'
        # espelha o que seria registrado, preservando o lado sem pedido.
        self.protecoes.append((position_ticket, side, stop, target))
        sl = float(stop) if stop is not None else float(sl_atual or 0.0)
        tp = float(target) if target is not None else float(tp_atual or 0.0)
        if self.protecao_ok:
            self.posicao_sl_tp = (sl, tp)
        return {"ok": self.protecao_ok, "note": self.protecao_note, "sl": sl, "tp": tp}

    def account_risk_state(self):
        return self.risco

    def pending_orders(self, ticker):
        """O que a CORRETORA diz estar pendurado no magic deste robo.

        `None` (default) = "nao consegui perguntar", que e' o estado em que
        todos os testes anteriores a 2026-08-28 rodavam (o metodo nem existia
        no dublê). Um teste que queira a corretora RESPONDENDO escreve a
        lista em `pendentes_na_corretora` -- e' assim que se exercita a
        ADOCAO de ticket que este processo nunca soube que existia."""
        return self.pendentes_na_corretora

    def margin_required(self, ticker, side, quantity, price):
        """Margem que a corretora exigiria por esta ordem. `None` (default)
        = "nao sei", que por politica NUNCA bloqueia -- os testes que nao
        falam de margem seguem passando sem tocar em nada."""
        if self.margem_por_contrato is None:
            return None
        self.margens_perguntadas.append((side, quantity, price))
        return self.margem_por_contrato * float(quantity)

    preco_de_saida = 9.90


class _BrokerComHistorico(_FakeMT5Broker):
    """Estende `_FakeMT5Broker` com `order_history_state`/`deals_for_
    position` -- os dois metodos novos da reconciliacao por historico
    (gap medido ao vivo em 2026-09-04, slot
    `dt-wdo_grid_reload_maker-wdo@-live`: ordem preenche E fecha entre
    dois polls; ver `MT5IntradayExecution.resolve_orphaned_entry` e
    `_resolve_exit_from_history`).

    AUSENTES na classe base de proposito: nenhum teste anterior configura
    isto, e `getattr(broker, "order_history_state", None)` no codigo sob
    teste degrada para "nada a reconciliar" quando o metodo nao existe --
    entao a classe base continua provando que o comportamento ANTIGO
    (sem reconciliacao) nao muda para quem nao usa esta subclasse.

    Uma unica resposta CANNED para qualquer ticket/posicao consultado --
    estes testes so' tem UMA ordem/posicao viva por vez, entao nao ha
    necessidade de um dict indexado pelo ticket real (que so' e' conhecido
    DEPOIS do primeiro `run_once`, ja que o dublê gera o ticket sozinho)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Default = "nao consegui perguntar" (o mais conservador -- um
        # teste que esquecer de configurar isto nunca declara uma ordem
        # morta ou inventa um preco de saida por acidente).
        self.resposta_estado = {"ok": False, "state": None, "position_id": None,
                                "note": "nao configurado no teste"}
        self.resposta_deals = {"ok": False, "deals": None, "note": "nao configurado no teste"}
        self.consultas_historico: list = []
        self.consultas_deals: list = []

    def order_history_state(self, ticket):
        self.consultas_historico.append(str(ticket))
        return dict(self.resposta_estado)

    def deals_for_position(self, position_id):
        self.consultas_deals.append(position_id)
        return dict(self.resposta_deals)


def _runtime_live(tmp_path, barras, broker, semente=None, **strat_kwargs):
    from strategy.daytrade.lab.gremah import Gremah

    kwargs = dict(symbol=SYMBOL, tick_size=0.01, profit_pct=0.01,
                  spacing_multiplier=2.0, stop_multiplier=20.0,
                  # Estes testes exercitam a mecanica SIMPLES de entrada/saida
                  # ao vivo (preco/quantidade REAIS da corretora), nao a saida
                  # dividida -- `dividir_entrada` virou padrao `True` na
                  # `Gremah` 2026-08-23, e sem `exit_ttl_bars` declarado a
                  # execucao real recusa operar dividida (por desenho). Quem
                  # quiser testar a divisao de verdade passa
                  # `dividir_entrada=True, exit_ttl_bars=N` via `strat_kwargs`.
                  dividir_entrada=False,
                  # Filtro de qualidade de entrada (2026-08-27) e' PADRAO
                  # `True` desde entao -- MESMO MOTIVO de `_runtime` acima:
                  # este arquivo testa a mecanica ao vivo, nao o filtro.
                  filtro_minutos_desde_abertura_min=None,
                  filtro_volume_toque_max=None)
    kwargs.update(strat_kwargs)
    feed = _ScriptedBarFeed(barras, barras[:1] if semente is None else semente)
    rt = IntradayLiveRuntime(
        slot=SLOT, strategy=Gremah(**kwargs), config=_config(),
        bar_feed=feed, broker=broker,
        db_path=tmp_path / "live_intraday.sqlite",
        execution_mode="live", initial_capital=100.0,
    )
    rt.ensure_account()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = 100.0
        store.save_account(conn, acc)
    return rt, feed


def test_live_registra_ordem_limite_pendente_de_verdade_na_corretora(tmp_path, pregao_aberto):
    """O contrario do que valia ate 2026-08-22 (o modo real levantava
    `NotImplementedError`): a `EnterLimit` do robo vira uma ordem-limite
    PENDENTE no terminal, com nivel e quantidade dela -- nunca uma ordem a
    mercado, que pagaria o spread que este robo existe para capturar."""
    broker = _FakeMT5Broker()
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 10.00, 10.00),
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    rt.run_once(now=_agora("13:03:00"))

    assert len(broker.pendentes_enviadas) >= 1
    primeira = broker.pendentes_enviadas[0]
    assert primeira.order_type == OrderType.LIMIT
    assert primeira.limit_price == pytest.approx(9.80)  # 10.00 - 2 * 1% = 2 * 10 ticks
    assert primeira.side == OrderSide.BUY


def test_ordem_em_pe_mostra_o_ticket_de_verdade_da_corretora_em_modo_live(tmp_path, pregao_aberto):
    """2026-08-27, pedido do dono: ele queria o ticket REAL da corretora no
    lugar do numero de rodada interno (`#NN`), achando que o ticket nao dava
    pra recuperar. Da' -- `MT5Broker.place_pending` ja' grava em `broker_ref`
    (ver `_FakeMT5Broker.place_pending`), so' nunca tinha chegado ao painel.
    `#NN` continua existindo (round que sobrevive a reancoragem), o ticket e'
    ADICIONAL, nao substituto."""
    broker = _FakeMT5Broker()
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 10.00, 10.00),
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    rt.run_once(now=_agora("13:03:00"))

    ordem = rt.status()["daytrade"]["ordem_em_pe"]
    assert ordem is not None
    assert ordem["tickets"] == [broker.pendentes_enviadas[0].broker_ref]


def test_live_barra_atravessa_o_nivel_mas_corretora_nao_tem_posicao_nao_abre(tmp_path, pregao_aberto):
    """O coracao da mudanca. A barra desce MUITO abaixo do nivel da ordem --
    no backtest isso e' um fill garantido. Com a corretora reportando conta
    zerada (a ordem estava atras na fila), a maquina NAO pode abrir posicao:
    contar alvo e stop de algo que nao se tem levaria a mandar uma venda a
    descoberto."""
    broker = _FakeMT5Broker()
    broker.posicao = None  # a corretora nao executou nada
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.00, 9.20),   # atravessou 9.80 com folga
        _bar("13:02", 9.20, 9.30, 9.20, 9.25),
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    rt.run_once(now=_agora("13:04:00"))

    assert rt.machine.position is None
    assert broker.ordens_a_mercado == []  # nada a fechar, nada foi aberto
    s = rt.status()
    assert s["daytrade"]["trades_na_sessao"] == 0


def test_live_abre_posicao_com_preco_e_quantidade_REAIS_da_corretora(tmp_path, pregao_aberto):
    """Quando a corretora confirma, o que entra na maquina e' o preco medio
    DELA -- nao o nivel teorico da ordem. Aqui ela executou a 9,78 (melhor que
    o nivel de 9,80), e e' 9,78 que tem de virar o preco de entrada."""
    broker = _FakeMT5Broker()
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.86, 9.85, 9.85),
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)
    # a corretora passa a reportar posicao a partir da 2a barra
    broker.posicao = {"side": "long", "price": 9.78, "quantity": 1, "ticket": 77}

    rt.run_once(now=_agora("13:04:00"))

    assert rt.machine.position is not None
    assert rt.machine.position.entry_price == pytest.approx(9.78)
    assert rt.machine.position.quantity == 1


def test_live_fecha_a_mercado_e_usa_o_preco_executado_pela_corretora(tmp_path, pregao_aberto):
    """A saida por alvo sai A MERCADO em execucao real (uma limite poderia nao
    preencher e deixar a posicao contra o proprio stop), e o P&L usa o preco
    que a corretora executou -- 9,88, nao o nivel de alvo teorico."""
    broker = _FakeMT5Broker()
    broker.preco_de_saida = 9.88
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),   # confirma entrada
        _bar("13:02", 9.85, 9.95, 9.85, 9.90),     # toca o alvo (9.90)
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)
    broker.posicao = {"side": "long", "price": 9.80, "quantity": 1, "ticket": 77}

    rt.run_once(now=_agora("13:04:00"))

    assert len(broker.ordens_a_mercado) == 1
    saida = broker.ordens_a_mercado[0]
    assert saida.order_type == OrderType.MARKET
    assert saida.side == OrderSide.SELL
    # Gap (a), incidente 2026-08-28: o fechamento tem de levar o ticket da
    # posicao REAL (`broker.posicao["ticket"]` = 77) -- nunca uma ordem "as
    # cegas" sem dizer qual posicao esta sendo abatida.
    assert broker.close_tickets == [77]
    s = rt.status()
    assert s["daytrade"]["trades_na_sessao"] == 1
    # (9.88 - 9.80) * 1 acao = +0,08, debitado no CAIXA (nao em sombra)
    assert s["caixa"] == pytest.approx(100.08, abs=0.01)
    assert s["daytrade"]["resultado_sombra"] == pytest.approx(0.0)
    # `caixa_sombra` (saldo paralelo) fica INTOCADO em execucao real -- so'
    # `cash` recebe o P&L quando `execution_mode="live"`.
    assert s["daytrade"]["caixa_sombra"] == pytest.approx(100.0)


# ---------- gap (a)/(c), incidente 2026-08-28: corrida com a protecao ------

def test_live_fechamento_quando_corretora_ja_fechou_por_protecao_nunca_aproxima_pelo_nivel_teorico(
    tmp_path, pregao_aberto,
):
    """Corrida legitima: a protecao SL/TP registrada na corretora (gap c) ja
    fechou a posicao alguns instantes antes deste passo. ATUALIZADO em
    2026-09-04 (segundo gap medido ao vivo no slot
    `dt-wdo_grid_reload_maker-wdo@-live`, ver LICOES_DE_PRODUCAO.md): a
    versao antiga deste metodo usava o nivel de stop/alvo como "a melhor
    aproximacao honesta" -- e um fechamento real medido ao vivo mostrou essa
    aproximacao ERRADA por R$9,50 num trade so' (deslize contra o robo que o
    nivel teorico nao capturava). `exit_market` NAO PODE MAIS aproximar por
    nivel teorico nem por ultimo preco negociado -- so' um deal CONFIRMADO
    no historico da corretora vale. Sem historico disponivel (este broker
    nao implementa `deals_for_position`, o dublê antigo), a saida certa e'
    RECUSAR e tentar de novo na proxima barra, com a posicao continuando
    aberta NA MAQUINA -- nunca um preco inventado. Ver
    `test_fechamento_sem_posicao_na_corretora_usa_deal_real_nunca_nivel_teorico`
    para o caminho em que o historico ESTA disponivel."""
    broker = _FakeMT5Broker()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, reason="teste_corrida_protecao")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 1}
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.position is not None

    # a protecao da corretora ja fechou a posicao ANTES desta barra chegar.
    broker.posicao = None
    feed._barras.append(_bar("13:03", 9.50, 9.50, 8.50, 8.90))  # rompe o stop (9.00)
    passos = rt.run_once(now=_agora("13:03:00"))

    passo = [p for p in passos if p.action == "daytrade_recusa_fechamento"]
    assert passo, "sem historico pra confirmar o deal real, recusa e tenta de novo -- nunca inventa"
    assert rt.machine.position is not None, "a posicao continua aberta NA MAQUINA"
    assert broker.ordens_a_mercado == [], "nenhuma ordem nova foi mandada"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        ordem = conn.execute(
            "SELECT * FROM live_orders WHERE account_id = ? AND side = 'sell' ORDER BY id",
            (acc.id,),
        ).fetchone()
    assert ordem is None, "nenhuma saida foi registrada -- nao ha' deal confirmado ainda"


def test_live_sem_conexao_com_o_terminal_nao_conclui_que_nao_preencheu(tmp_path, pregao_aberto):
    """"Nao consegui perguntar" nunca pode virar "nao preencheu" -- senao o
    robo re-armaria ordem sobre uma posicao que talvez exista. Tem de subir
    erro (o supervisor loga e tenta na proxima barra)."""
    from live.intraday_execution import BrokerExecutionError

    broker = _FakeMT5Broker(conectado=False)
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    with pytest.raises(BrokerExecutionError, match="sem conexao"):
        rt.run_once(now=_agora("13:03:00"))


def test_live_posicao_do_lado_errado_na_corretora_falha_alto(tmp_path, pregao_aberto):
    """Corretora reportando posicao VENDIDA enquanto a ordem vigiada era de
    compra significa que alguma coisa fora deste robo mexeu na conta. Adotar
    essa posicao como sua seria operar dinheiro de origem desconhecida."""
    from live.intraday_execution import BrokerExecutionError

    broker = _FakeMT5Broker()
    broker.posicao = {"side": "short", "price": 9.78, "quantity": 1, "ticket": 77}
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    with pytest.raises(BrokerExecutionError, match="reporta posicao short"):
        rt.run_once(now=_agora("13:03:00"))


def test_live_ordem_abandonada_pelo_robo_e_cancelada_no_terminal(tmp_path, pregao_aberto):
    """Uma ordem-limite que o robo re-ancorou nao pode continuar viva na
    corretora: ela preencheria horas depois, contra um preco que o robo ja
    descartou."""
    broker = _FakeMT5Broker()
    barras = [
        # ancora FIXA na abertura: ordem parada em 9.80, registrada no
        # terminal pelo warm start
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        # relogio ja passou de `fixed_anchor_until` (14:00) sem nunca tocar
        # 9.80 -- o robo abandona a fixa e re-ancora no preco atual
        _bar("14:30", 12.00, 12.00, 12.00, 12.00),
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker, semente=barras[:1])

    rt.run_once(now=_agora("13:04:00"))

    assert len(broker.pendentes_enviadas) == 2, "re-ancorou: registrou a nova"
    assert broker.pendentes_enviadas[0].limit_price == pytest.approx(9.80)
    assert broker.pendentes_enviadas[1].limit_price == pytest.approx(11.76)  # 12.00 - 2*12 ticks
    assert len(broker.canceladas) == 1, "a ordem substituida tem de sair do terminal"
    assert broker.canceladas[0].limit_price == pytest.approx(9.80)


# ---------- gap de restart do lado da ENTRADA (2026-08-23) -----------------
#
# Mesma familia de risco do lado da saida (ja fechado, ver `machine.restore`):
# `resting_limit`/`_resting_children_qty` nunca sao restaurados de proposito
# (a ordem e' uma DECISAO, redecidida do zero pelo warm start) -- mas o(s)
# TICKET(S) REAIS que um processo anterior mandou pra corretora nao desaparecem
# so' porque o processo morreu. Diferente da saida, aqui e' seguro RECONCILIAR
# sozinho (`pending_entry_refs`), porque uma ordem de compra parada sobrando
# e' risco baixo (nenhuma posicao fica exposta esperando ela).

def test_restart_dentro_da_janela_de_ancora_fixa_cancela_o_ticket_antigo_antes_de_arma_novo(
    tmp_path, pregao_aberto,
):
    """O PROCESSO inteiro reinicia (novo `IntradayLiveRuntime`, mesmo
    banco/corretora) ainda dentro da janela de ancora fixa, com uma ordem de
    entrada ja posicionada e SEM fill nenhum. O warm start do processo novo
    recalcula a decisao do zero (nao sabe do ticket antigo por conta propria)
    -- sem a correcao, mandaria uma SEGUNDA ordem de compra por cima da que o
    processo velho ja tinha no terminal."""
    broker = _FakeMT5Broker()
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime_live(tmp_path, barras, broker, semente=barras[:1])
    rt.run_once(now=_agora("13:00:30"))

    assert len(broker.pendentes_enviadas) == 1, "warm start armou a ordem fixa"
    ticket_antigo = broker.pendentes_enviadas[0].broker_ref
    assert broker.canceladas == []

    # "reinicia o processo": um `IntradayLiveRuntime` NOVO, mesmo slot/banco,
    # cujo `executor` (objeto novo) nao tem NENHUMA memoria do ticket que o
    # processo anterior mandou.
    from strategy.daytrade.lab.gremah import Gremah

    feed_novo = _ScriptedBarFeed(barras, barras[:1])
    rt_novo = IntradayLiveRuntime(
        slot=SLOT, strategy=Gremah(symbol=SYMBOL, tick_size=0.01, profit_pct=0.01,
                                   spacing_multiplier=2.0, stop_multiplier=20.0,
                                   dividir_entrada=False,
                                   filtro_minutos_desde_abertura_min=None,
                                   filtro_volume_toque_max=None),
        config=_config(), bar_feed=feed_novo, broker=broker,
        db_path=rt.db_path, execution_mode="live", initial_capital=100.0,
    )

    rt_novo.run_once(now=_agora("13:00:45"))  # ainda dentro da janela fixa

    assert len(broker.canceladas) == 1, "o ticket orfao do processo velho foi cancelado"
    assert broker.canceladas[0].broker_ref == ticket_antigo
    assert len(broker.pendentes_enviadas) == 2, "cancelou o velho e armou um novo"


def test_restart_fora_da_janela_de_ancora_fixa_tambem_cancela_o_ticket_antigo(
    tmp_path, pregao_aberto,
):
    """Mesmo risco, caminho DIFERENTE: o restart acontece DEPOIS de
    `fixed_anchor_until` (comeco a FRIO, sem warm start nenhum) -- a
    reconciliacao tem de acontecer na primeira decisao NOVA do robo
    (`_on_limit_placed`), nao so' no bloco de warm start."""
    broker = _FakeMT5Broker()
    barras_processo_velho = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime_live(tmp_path, barras_processo_velho, broker, semente=barras_processo_velho)
    rt.run_once(now=_agora("13:00:30"))
    ticket_antigo = broker.pendentes_enviadas[0].broker_ref

    from strategy.daytrade.lab.gremah import Gremah

    # processo novo, relogio ja' PASSOU de `fixed_anchor_until` (14:00) --
    # cai em comeco a frio, sem warm start. Comeco a frio NAO consome
    # NENHUMA barra ja fechada no instante em que liga (`closed_bars_since
    # (None)` devolve tudo o que ja existe no feed, e essas viram so' a marca
    # de partida, ver `_start_session`) -- precisa de uma barra chegando
    # DEPOIS desse instante pro robo ter algo pra de fato decidir, exatamente
    # como um feed ao vivo real.
    feed_novo = _ScriptedBarFeed([], [])
    rt_novo = IntradayLiveRuntime(
        slot=SLOT, strategy=Gremah(symbol=SYMBOL, tick_size=0.01, profit_pct=0.01,
                                   spacing_multiplier=2.0, stop_multiplier=20.0,
                                   dividir_entrada=False,
                                   filtro_minutos_desde_abertura_min=None,
                                   filtro_volume_toque_max=None),
        config=_config(), bar_feed=feed_novo, broker=broker,
        db_path=rt.db_path, execution_mode="live", initial_capital=100.0,
    )
    rt_novo.run_once(now=_agora("14:32:00"))  # cold start: so' calibra, nada pra consumir ainda

    feed_novo._barras.append(_bar("14:33", 12.00, 12.00, 12.00, 12.00))
    rt_novo.run_once(now=_agora("14:33:00"))  # 1a barra nova -- o robo decide e' AGORA

    assert len(broker.canceladas) == 1, "o ticket orfao do processo velho foi cancelado"
    assert broker.canceladas[0].broker_ref == ticket_antigo
    assert len(broker.pendentes_enviadas) == 2, "cancelou o velho e armou a nova ancora rolante"


# ---------- Fase 2 (2026-08-22): divisao de ordem de VERDADE na corretora --
#
# Ate aqui `EnterLimit.split_quantities`/`exit_split_unit` sempre foram
# tratados como um pedido so' em execucao real (a corretora recebia UMA
# ordem do tamanho total, ignorando a divisao que o robo pediu). Os testes
# abaixo cobrem o caminho novo: um filho REAL por fatia, preenchimento
# incremental detectado pelo CRESCIMENTO/ENCOLHIMENTO da posicao na
# corretora (nao mais por `bar.volume`), e a saida dividida com prazo
# limitado -> mercado (decisao do dono).
#
# Usam uma estrategia ROTEIRIZADA por indice de barra (em vez de `Gremah`)
# para controlar `EnterLimit` diretamente, sem a logica de ancora/calibracao
# do robo real atrapalhar o cenario.

class _ScriptedDaytrade(IntradayStrategy):
    """Sem `fixed_anchor_until`: sempre comeca a FRIO, entao a barra de
    indice 0 do script e' a PRIMEIRA barra que `run_once` realmente
    consome (nao uma semente de warm start)."""

    name = "scripted_dt"
    version = "1"

    def __init__(self, symbol: str, script: dict[int, list]):
        self.symbol = symbol
        self.tick_size = 0.01
        self.target_fills_as_maker = True
        self.script = script
        self._i = -1

    def on_bar(self, ts, bar, position, session_pnl_brl):
        self._i += 1
        return list(self.script.get(self._i, []))


def _runtime_live_scripted(tmp_path, broker, script: dict[int, list],
                           initial_capital: float = 100.0):
    """`initial_capital` e' o LEDGER DO PAINEL do slot -- o numero que o dono
    digitou. Desde 2026-09-08 e' ele (nunca o saldo do MT5) que decide ruina
    no freio duro e quanto o portao de margem tem para comprometer."""
    strat = _ScriptedDaytrade(SYMBOL, script)
    feed = _ScriptedBarFeed([], [])
    rt = IntradayLiveRuntime(
        slot=SLOT, strategy=strat, config=_config(),
        bar_feed=feed, broker=broker,
        db_path=tmp_path / "live_intraday.sqlite",
        execution_mode="live", initial_capital=float(initial_capital),
    )
    rt.ensure_account()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = float(initial_capital)
        store.save_account(conn, acc)
    return rt, feed


def test_live_entrada_dividida_manda_ordens_reais_e_faz_top_up_no_diario(tmp_path, pregao_aberto):
    """`EnterLimit.split_quantities` agora manda um FILHO REAL por elemento
    na corretora (antes ia tudo como uma ordem so'), e o preenchimento em
    BARRAS DIFERENTES (a corretora casando um filho de cada vez) tem de
    acumular numa UNICA posicao/Intent -- nao numa entrada fantasma por
    filho, que era o bug que sobreviveria se `_on_opened` nao soubesse
    distinguir TOP-UP de entrada nova."""
    broker = _FakeMT5Broker()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=2, split_quantities=(1, 1),
                       reason="teste_split")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))
    assert len(broker.pendentes_enviadas) == 2, "os DOIS filhos tem de ir para a corretora"
    assert {int(o.quantity) for o in broker.pendentes_enviadas} == {1}

    # 1o filho preenche
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 1}
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.position is not None
    assert rt.machine.position.quantity == 1
    assert rt.machine.position.entry_price == pytest.approx(10.00)

    # 2o filho preenche, em preco DIFERENTE -- prova a media ponderada
    broker.posicao = {"side": "long", "price": 10.05, "quantity": 2, "ticket": 1}
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))

    assert rt.machine.position.quantity == 2
    assert rt.machine.position.entry_price == pytest.approx(10.05)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        intents = store.all_intents(conn, acc.id)
        ordens = conn.execute(
            "SELECT * FROM live_orders WHERE account_id = ? ORDER BY id", (acc.id,)
        ).fetchall()
    assert len(intents) == 1, "um so' Intent para a entrada inteira, apesar de 2 fills"
    assert len(ordens) == 2, "uma Order por FILHO que preencheu, sob o mesmo Intent"
    assert all(o["intent_id"] == intents[0].id for o in ordens)
    pos = acc.positions["PMAM3"]
    assert pos.quantity == 2, "live_positions com a quantidade CUMULATIVA, nao a do ultimo filho"
    assert pos.entry_price == pytest.approx(10.05)


def test_live_saida_dividida_confirma_fatia_e_estoura_prazo_pro_resto_a_mercado(tmp_path, pregao_aberto):
    """Lado da SAIDA da Fase 2: o alvo dividido (`exit_split_unit`) vira
    ordem-limite REAL por fatia, com prazo (`exit_ttl_bars`) -- decisao do
    dono ('prazo limitado, depois mercado'). A 1a fatia confirma via a
    posicao ENCOLHENDO na corretora; a 2a nao preenche dentro do prazo e tem
    de fechar o QUE SOBRAR a MERCADO."""
    broker = _FakeMT5Broker()
    broker.preco_de_saida = 10.90
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=2,
                       exit_split_unit=1, exit_ttl_bars=2, reason="teste_exit_split")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    broker.posicao = {"side": "long", "price": 10.00, "quantity": 2, "ticket": 1}
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.position is not None and rt.machine.position.quantity == 2

    # toca o alvo (11.00) -- arma a 1a fatia (1 acao) como ordem-limite REAL
    feed._barras.append(_bar("13:03", 10.50, 11.05, 10.50, 11.00))
    rt.run_once(now=_agora("13:03:00"))
    assert rt.machine.position.quantity == 2, "so' ARMOU, nenhum fill confirmado ainda"
    fatias_saida = [o for o in broker.pendentes_enviadas
                    if o.order_type == OrderType.LIMIT and o.side == OrderSide.SELL]
    assert len(fatias_saida) == 1
    assert fatias_saida[0].quantity == 1
    assert fatias_saida[0].limit_price == pytest.approx(11.00)

    # a corretora confirma a 1a fatia (posicao encolhe de 2 para 1)
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 1}
    feed._barras.append(_bar("13:04", 11.00, 11.05, 10.95, 11.00))
    rt.run_once(now=_agora("13:04:00"))
    assert rt.machine.position is not None and rt.machine.position.quantity == 1, (
        "so' 1 fechou, o resto continua aberto"
    )

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
    assert acc.positions["PMAM3"].quantity == 1, "live_positions ATUALIZADA, nao apagada"
    # 100 (inicial) - 20 (2 acoes @ 10.00 debitadas na entrada) + 10 (capital
    # da fatia fechada, devolvido) + 1 (lucro da fatia, 11.00-10.00) = 91;
    # os outros 10 continuam comprometidos na acao que ainda esta aberta.
    assert acc.cash == pytest.approx(91.0), "capital da fatia devolvido + lucro (11.00-10.00)*1 creditado"

    # a 2a fatia arma (o preco continua no alvo) e NAO preenche por 2 barras
    feed._barras.append(_bar("13:05", 11.00, 11.05, 10.95, 11.00))
    rt.run_once(now=_agora("13:05:00"))
    assert rt.machine.position is not None and rt.machine.position.quantity == 1
    feed._barras.append(_bar("13:06", 11.00, 11.05, 10.95, 11.00))
    rt.run_once(now=_agora("13:06:00"))
    assert rt.machine.position is not None, "1a barra de espera -- ainda nao estourou o prazo"
    feed._barras.append(_bar("13:07", 11.00, 11.05, 10.95, 11.00))
    rt.run_once(now=_agora("13:07:00"))

    assert rt.machine.position is None, "estourou exit_ttl_bars=2 -- fechou o resto a mercado"
    assert broker.ordens_a_mercado, "o restante saiu por ordem A MERCADO, nao ficou esperando"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
    assert "PMAM3" not in acc.positions


def test_restart_com_fatia_de_saida_posicionada_em_execucao_real_falha_alto(tmp_path, pregao_aberto):
    """Gap de restart no meio de uma fatia posicionada (2026-08-23): o PROCESSO
    inteiro reinicia (novo `IntradayLiveRuntime`, mesmo banco) enquanto a 1a
    fatia da saida dividida ainda esta pendente na corretora, sem fill
    confirmado. O ticket dessa ordem vivia so' em memoria no processo velho --
    o processo novo tem de falhar alto em vez de arriscar rearmar uma segunda
    ordem de saida por cima da que pode ainda estar viva no book."""
    broker = _FakeMT5Broker()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=2,
                       exit_split_unit=1, exit_ttl_bars=2, reason="teste_restart")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    broker.posicao = {"side": "long", "price": 10.00, "quantity": 2, "ticket": 1}
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))

    # toca o alvo (11.00) -- arma a 1a fatia como ordem-limite REAL, ainda sem
    # fill nenhum confirmado.
    feed._barras.append(_bar("13:03", 10.50, 11.05, 10.50, 11.00))
    rt.run_once(now=_agora("13:03:00"))
    assert rt.machine.position.quantity == 2, "so' armou, nenhum fill confirmado ainda"

    # "reinicia o processo": um `IntradayLiveRuntime` NOVO, mesmo slot/banco,
    # sem nenhuma memoria do `pending_exit_order` que o processo velho tinha.
    rt_novo = IntradayLiveRuntime(
        slot=SLOT, strategy=_ScriptedDaytrade(SYMBOL, {}), config=_config(),
        bar_feed=_ScriptedBarFeed([], []), broker=broker,
        db_path=rt.db_path, execution_mode="live", initial_capital=100.0,
    )

    with pytest.raises(RuntimeError, match="FATIA DE SAIDA"):
        rt_novo.run_once(now=_agora("13:04:00"))


def test_live_saida_dividida_sem_prazo_falha_alto(tmp_path, pregao_aberto):
    """Sem `exit_ttl_bars` a posicao ficaria exposta indefinidamente
    esperando a fatia final -- exatamente o que a decisao do dono ('prazo
    limitado, depois mercado') existe para proibir. Falha alto em vez de
    arriscar isso com dinheiro real."""
    broker = _FakeMT5Broker()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, exit_split_unit=1,
                       reason="sem_prazo")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 1}
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))

    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    with pytest.raises(NotImplementedError, match="exit_ttl_bars"):
        rt.run_once(now=_agora("13:03:00"))


def test_sombra_continua_simulando_o_fill_pela_barra(tmp_path, pregao_aberto):
    """Regressao da fronteira: sombra NAO ganha ponte de execucao -- ela
    continua com o fill simulado pela barra, que e' justamente a premissa que
    a fase de sombra existe para comparar contra a realidade."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)

    assert rt.executor is None
    assert rt.machine.execution is None
    rt.run_once(now=_agora("13:03:00"))
    assert rt.machine.position is not None  # a barra decidiu, sem corretora


def test_capital_do_slot_dimensiona_a_posicao_e_nao_o_da_config_recebida(tmp_path, pregao_aberto):
    """REGRESSAO (2026-08-22): `IntradayBacktestConfig.initial_capital` tinha
    default de R$20.000 (removido -- ver a docstring do campo) e nenhum
    montador de runtime ao vivo o sobrescrevia — o `initial_capital` do slot
    so' ia para a CONTA. Resultado: a maquina chamava
    `on_capital_update(20_000 + realizado)` e o robo escolhia lotes contra um
    caixa que nao existe. O campo agora e' obrigatorio (nao ha mais como
    esquecer em silencio), mas o teste continua valendo: garante que
    `IntradayLiveRuntime` SEMPRE substitui o `initial_capital` da config
    recebida pelo capital real do slot, mesmo que a config chegue com outro
    numero (aqui, de proposito, um valor diferente de 100 -- ver `_config()`).

    Medido no pregao real da PMAM3 de 2026-08-21 (R$0,13-0,14): com os
    R$20.000 fantasmas o robo pediu 33.400 acoes e perdeu R$672 num unico
    trade — mais de 100x o proprio teto de perda diaria (R$5,20). Com o
    capital certo (R$100) pede 200 acoes."""
    from strategy.daytrade.lab.gremah import Gremah

    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    feed = _ScriptedBarFeed(barras, barras[:1])
    rt = IntradayLiveRuntime(
        slot=SLOT,
        strategy=Gremah(symbol=SYMBOL, tick_size=0.01, profit_pct=0.01,
                        spacing_multiplier=2.0, stop_multiplier=20.0,
                        filtro_minutos_desde_abertura_min=None, filtro_volume_toque_max=None),
        config=_config(),           # sai daqui com initial_capital=0.0, de proposito
        bar_feed=feed, broker=_ExplodingBroker(),
        db_path=tmp_path / "live_intraday.sqlite",
        execution_mode="shadow", initial_capital=100.0,
    )

    assert rt.config.initial_capital == pytest.approx(100.0)
    # E a MAQUINA tem de ver o mesmo numero: era passando o `config` cru para
    # ela (em vez de `self.config`) que o furo sobrevivia ao primeiro conserto.
    assert rt.machine.config.initial_capital == pytest.approx(100.0)

    rt.ensure_account()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = 100.0
        store.save_account(conn, acc)
    rt.run_once(now=_agora("13:03:00"))

    # caixa 100, lote a 10.00 = R$1.000: 1 + floor(100 / (4*1000)) = 1 lote.
    assert rt.machine.position.quantity == 100


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


def test_barra_sem_faixa_grava_penetracao_n_a_em_vez_de_zero(tmp_path, pregao_aberto):
    """E' o caso NORMAL do feed de tick: `open==high==low==close`, porque um
    negocio e' um evento atomico a um preco so'.

    Gravar 0.0 ali seria pior que nao medir — o painel e quem le o diario
    leriam "a premissa de maker e' fragil em 100% dos toques", quando na
    verdade a penetracao e' zero POR CONSTRUCAO e a pergunta nao cabe nesse
    formato de dado. Quem responde a pergunta de fila aqui e'
    `volume_no_nivel`."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        # degeneradas, como o tick a tick entrega: um preco por evento
        _bar("13:01", 9.90, 9.90, 9.90, 9.90),
        _bar("13:02", 9.80, 9.80, 9.80, 9.80),   # negocia exatamente no nivel
        _bar("13:03", 9.85, 9.85, 9.85, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)

    rt.run_once(now=_agora("13:04:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        intent = store.all_intents(conn, acc.id)[0]
    assert intent.payload["penetration_ticks"] is None
    assert intent.payload["volume_no_nivel"] > 0


def test_volume_no_nivel_conta_o_que_negociou_esperando_a_ordem(tmp_path, pregao_aberto):
    """A pergunta de fila, feita de um jeito que o tick responde: quantas
    acoes passaram pelo meu nivel contra quantas eu pedi.

    Menos volume no nivel do que a quantidade pedida significa que o
    preenchimento que o backtest assumiu era otimismo — a ordem podia estar
    atras na fila e nunca chegar a vez dela."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 9.90, 9.90, 9.90, 9.90),   # acima do nivel: nao conta
        _bar("13:02", 9.80, 9.80, 9.80, 9.80),   # no nivel: conta (1.000)
        _bar("13:03", 9.79, 9.79, 9.79, 9.79),   # abaixo: contaria, mas ja encheu
    ]
    rt, _feed = _runtime(tmp_path, barras)

    rt.run_once(now=_agora("13:05:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        intent = store.all_intents(conn, acc.id)[0]
    # so' a barra que negociou NO nivel entrou na conta — a de 9.90 nao.
    assert intent.payload["volume_no_nivel"] == pytest.approx(1_000.0)
    assert intent.payload["quantidade_pedida"] == 100


# ---------- short: quantidade negativa em live_positions ------------------

def test_short_grava_quantidade_negativa_na_posicao(tmp_path, pregao_aberto):
    """Short foi verificado no terminal real (2026-08-21). `live_positions.
    quantity` negativa marca o LADO da posicao (usado por `metadata["side"]`
    e pelo cartao "Posicoes abertas"), mas `market_value` e' sempre POSITIVO
    -- e' capital comprometido, nao credito de venda a descoberto (ver
    docstring de `LivePosition.market_value`, corrigido 2026-08-31: a versao
    anterior devolvia negativo aqui e abria todo short com prejuizo fantasma
    de 2x o custo em `equity()`, sem nenhum preco ter se mexido).

    `max_trades_per_side=1` (adicionado em 2026-08-28) e' o que forca o short
    a existir: o long fecha no ALVO, e desde 2026-08-26 o robo REPETE o lado
    depois de um trade lucrativo (memoria `gremah_repetir_ultimo_vencedor`)
    em vez de alternar. Com o lado long esgotado no teto, `_next_side_to_arm`
    volta a escolher short -- que e' o que este teste precisa medir. O
    roteiro antigo dependia da alternancia pura e ficou vermelho por dois
    dias sem que nada estivesse errado no codigo de producao."""
    # ROTEIRO COMPRIMIDO em 2026-09-08: as barras andam de 20 em 20s (nao
    # de minuto em minuto) e `now` fica logo depois da ultima. Motivo:
    # desde `MAX_ATRASO_PARA_ORDEM_SEGUNDOS`, barra mais velha que o teto
    # nao gera ORDEM NOVA -- e um roteiro de 6 minutos consumido num
    # `run_once` so' deixava a barra de abertura com 5+ min de idade. O
    # que este teste mede (sequencia de OHLC, numeracao, P&L) nao depende
    # do espacamento; a idade agora depende.
    barras = [
        _bar("13:00:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:00:20", 10.00, 10.00, 9.79, 9.85),   # long em 9.80
        _bar("13:00:40", 9.85, 9.91, 9.85, 9.90),     # alvo 9.90 -> fecha long
        # Com o long no teto, a recarga e' do OUTRO lado (short), ancorada na
        # abertura: 10.00 + 20 ticks de espacamento = 10.20. Esta barra
        # atravessa.
        _bar("13:01:00", 9.90, 10.21, 9.90, 10.15),
    ]
    rt, _feed = _runtime(tmp_path, barras, max_trades_per_side=1)

    rt.run_once(now=_agora("13:01:05"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
    pos = acc.positions.get("PMAM3")
    assert pos is not None
    assert pos.quantity < 0
    assert pos.metadata["side"] == "short"
    assert pos.market_value(10.00) == pytest.approx(abs(pos.quantity) * 10.00)


def test_market_value_de_short_e_positivo_igual_ao_de_long_mesmo_custo():
    """`market_value` mede CAPITAL COMPROMETIDO (o mesmo `custo` que
    `_custo_posicao`/`_on_opened` debitam do caixa), nunca credito de venda a
    descoberto -- por isso e' o MESMO numero em long e em short, futuro ou
    acao. Achado do dono 2026-08-31: antes da correcao, o short devolvia
    negativo aqui (cartao "Posicoes abertas" mostrando R$ -100,00 para uma
    posicao WIN@ recem-aberta, contra +R$100,00 no card "Posicoes · Short",
    que ja usava `_custo_posicao` e sempre esteve certo)."""
    long_futuro = LivePosition(
        ticker="WIN@", quantity=1, entry_date=date(2026, 8, 31),
        entry_price=180_015.0, capital_allocated=100.0, unit_value_brl=100.0,
    )
    short_futuro = LivePosition(
        ticker="WIN@", quantity=-1, entry_date=date(2026, 8, 31),
        entry_price=180_015.0, capital_allocated=100.0, unit_value_brl=100.0,
    )
    assert long_futuro.market_value(180_015.0) == pytest.approx(100.0)
    assert short_futuro.market_value(180_015.0) == pytest.approx(100.0)

    long_acao = LivePosition(
        ticker="PMAM3", quantity=100, entry_date=date(2026, 8, 31),
        entry_price=10.0, capital_allocated=1_000.0,
    )
    short_acao = LivePosition(
        ticker="PMAM3", quantity=-100, entry_date=date(2026, 8, 31),
        entry_price=10.0, capital_allocated=1_000.0,
    )
    assert long_acao.market_value(10.0) == pytest.approx(1_000.0)
    assert short_acao.market_value(10.0) == pytest.approx(1_000.0)


def test_abrir_short_nao_cria_prejuizo_fantasma_na_carteira():
    """`equity() = caixa + invested()` nao pode mudar so' por ABRIR uma
    posicao marcada na propria entrada (P&L nao realizado = 0, mesma
    convencao de `status()`) -- e' o invariante que o comentario de
    `_on_opened` promete: 'sem isto, equity() conta o mesmo dinheiro duas
    vezes'. Reproduz o caixa ja debitado pelo custo (como `_on_opened` faz
    em QUALQUER lado) e confirma que `invested()` devolve o custo de volta,
    nao o custo com o sinal invertido -- que teria criado um prejuizo
    fantasma de 2x o custo so' de abrir o short, sem nenhum preco se mexer."""
    custo = 100.0
    caixa_antes_de_abrir = 544.50
    acc = AccountState(
        name="dt-teste", mode="mt5", initial_capital=1_000.0,
        cash=caixa_antes_de_abrir - custo,
    )
    acc.positions["WIN@"] = LivePosition(
        ticker="WIN@", quantity=-1, entry_date=date(2026, 8, 31),
        entry_price=180_015.0, capital_allocated=custo, unit_value_brl=custo,
    )
    marks = {"WIN@": 180_015.0}
    assert acc.invested(marks) == pytest.approx(custo)
    assert acc.equity(marks) == pytest.approx(caixa_antes_de_abrir)


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
    # As buscas ao feed sao SEMPRE a cauda de sessoes ANTERIORES (janela de
    # volume rolante + janela de volatilidade diaria + janela de negocio
    # tipico diario, 2026-08-24) -- o warm start de HOJE nao acontece
    # (comeco a frio nunca tenta buscar a semente de HOJE).
    dias_vol = []
    dia = SESSION
    for _ in range(itr_mod._CAUDA_VOL_DIAS):
        dia = live_clock.previous_session(dia)
        dias_vol.append((dia, itr_mod._FIM_DE_PREGAO_QUALQUER))
    # `_seed_daily_aggregates` (2026-09-04, item 5.9 do LICOES_DE_PRODUCAO.md)
    # busca cada uma das `_CAUDA_VOL_DIAS` sessoes UMA SO' VEZ e calcula os
    # dois agregados (`barra_diaria` e `mediana_negocio_diario`) das MESMAS
    # barras -- antes buscava os mesmos dias 2x (um laco por agregado).
    esperado = [(date(2026, 8, 20), itr_mod._FIM_DE_PREGAO_QUALQUER)] + dias_vol
    assert feed.pedidos_de_semente == esperado


def test_seed_volume_window_busca_e_repassa_a_cauda_do_pregao_anterior(tmp_path, pregao_aberto):
    """Fim a fim: a cauda do pregao ANTERIOR (2026-08-20) chega no robo via
    `seed_volume_window` ANTES da primeira barra de hoje, e influencia o
    teto de posicao da entrada -- pedido literal do dono ('na abertura ele
    considera tambem as ultimas barras do dia anterior'), nao um numero
    congelado no minimo de 1 lote por falta de historico."""
    def _bar_on(date_str, hhmm, o, h, low, c, volume):
        return Bar(ts=pd.Timestamp(f"{date_str} {hhmm}", tz="UTC"),
                   open=float(o), high=float(h), low=float(low), close=float(c), volume=float(volume))

    # 30 barras de 10.000 acoes = 300.000 no total, ultimas 30min do pregao
    # anterior (que fecha as 19:54 UTC nesse roteiro).
    cauda_ontem = [_bar_on("2026-08-20", f"19:{25 + m:02d}", 10.0, 10.0, 10.0, 10.0, 10_000.0)
                   for m in range(30)]
    rt, feed = _runtime(tmp_path, barras=[], semente=cauda_ontem,
                        fixed_anchor_until=time(14, 0),
                        realocacao_teto_pct_volume_minuto=0.10, realocacao_limiar_caixa=0.0001)

    # 1a chamada: comeco a FRIO (depois do corte de ancora fixa, sem semente
    # de HOJE) -- so' estabelece a sessao e ja busca a cauda do pregao
    # anterior. Deliberadamente NAO uso warm start aqui: `on_capital_update`
    # nunca e' chamado durante o replay do warm start (ver o comentario em
    # `Gremah.__init__`), entao o caixa ficaria zerado e o teto de CAIXA
    # (nao o de volume que quero medir) travaria o lote em 1 de qualquer jeito.
    rt.run_once(now=_agora("15:01:00"))
    assert (date(2026, 8, 20), itr_mod._FIM_DE_PREGAO_QUALQUER) in feed.pedidos_de_semente

    # a barra "ao vivo" chega DEPOIS, pelo caminho normal (`on_capital_update`
    # de verdade) -- e' aqui que o teto de volume (com a cauda ja' carregada)
    # decide o tamanho da PRIMEIRA entrada do dia.
    feed._barras.append(_bar_on("2026-08-21", "15:01", 10.00, 10.00, 10.00, 10.00, 0.0))
    rt.run_once(now=_agora("15:02:00"))

    # media = 300.000 da cauda / 30 = 10.000 acoes/min; teto 10% = 1.000
    # acoes = 10 lotes -- nao o minimo de 1 lote que "sem cauda" produziria.
    assert rt.machine.resting_limit is not None
    assert rt.machine.resting_limit.quantity == 1_000


def test_seed_daily_volatility_busca_e_repassa_o_range_diario_do_pregao_anterior(tmp_path, pregao_aberto):
    """Fim a fim: o range diario (high-low) do pregao ANTERIOR chega no robo
    via `seed_daily_volatility` ANTES da primeira barra de hoje -- mesmo
    canal ja' validado para `seed_volume_window` acima
    (`test_seed_volume_window_busca_e_repassa_a_cauda_do_pregao_anterior`),
    agora alimentando `JanelaVolatilidadeDiaria` em vez do teto de volume."""
    def _bar_on(date_str, hhmm, o, h, low, c, volume):
        return Bar(ts=pd.Timestamp(f"{date_str} {hhmm}", tz="UTC"),
                   open=float(o), high=float(h), low=float(low), close=float(c), volume=float(volume))

    dia_anterior = [
        _bar_on("2026-08-20", "13:00", 10.0, 10.5, 9.8, 10.2, 1_000.0),
        _bar_on("2026-08-20", "13:01", 10.2, 11.0, 9.5, 10.9, 1_000.0),
    ]
    rt, feed = _runtime(tmp_path, barras=[], semente=dia_anterior,
                        fixed_anchor_until=time(14, 0),
                        alvo_por_volatilidade=True, alvo_vol_mult=0.5)

    rt.run_once(now=_agora("15:01:00"))

    # range diario agregado das 2 barras acima: high=11.0, low=9.5 -> 1.5.
    # Unica sessao com dado dentre as `_CAUDA_VOL_DIAS` buscadas (as outras
    # `session_bars_until` devolvem lista vazia, `barra_diaria([])` e' None
    # e nao entra na janela) -- mediana de 1 valor so' e' o proprio valor.
    assert rt.strategy._janela_vol.range_mediano() == pytest.approx(1.5)


# ---------- item 5.9 do LICOES_DE_PRODUCAO (2026-09-04): nao busca o que a
# estrategia nao consome, e busca cada sessao consumida UMA SO VEZ --------

def test_robo_sem_hooks_de_seed_sobrescritos_nao_busca_historico_nenhum(tmp_path, pregao_aberto):
    """`WdoGridReloadMaker`/`CopaWin` (os dois robos do incidente de
    2026-09-04) nao sobrescrevem NENHUM dos tres hooks de seed
    (`seed_volume_window`/`seed_daily_volatility`/`seed_typical_trade_size`
    -- default no-op puro em `IntradayStrategy`) e nao tem
    `fixed_anchor_until` (entao tambem nao fazem warm start). ANTES desta
    correcao, `_start_session` buscava as MESMAS 31 sessoes do feed so'
    para alimentar metodos vazios -- 1 (janela de volume) + 15
    (`seed_daily_volatility`) + 15 (`seed_typical_trade_size`), NENHUMA
    aproveitada. Contra o feed de TICK real (~14s/sessao, ~140.000
    "barras" degeneradas por sessao de WDO) isso sozinho e' o essencial dos
    ~430s que derrubaram os dois slots `wdo_grid_reload_maker` pelo
    watchdog de heartbeat. DEPOIS: zero buscas."""
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker

    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    slot = slot_by_id("dt-wdo_grid_reload_maker-wdo@-shadow")
    feed = _ScriptedBarFeed([_bar("13:01", 5_100.0, 5_100.0, 5_100.0, 5_100.0)], semente=[])
    rt = IntradayLiveRuntime(
        slot=slot, strategy=strat, config=_config(), bar_feed=feed,
        broker=_ExplodingBroker(), db_path=tmp_path / "live_intraday.sqlite",
        execution_mode="shadow", initial_capital=100_000.0,
    )
    rt.ensure_account()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, slot.id)
        acc.cash = 100_000.0
        store.save_account(conn, acc)

    rt.run_once(now=_agora("13:02:00"))

    assert feed.pedidos_de_semente == [], (
        "sem hook de seed sobrescrito e sem fixed_anchor_until, NENHUMA "
        "busca de historico deveria acontecer ao feed -- eram 31 antes "
        "desta correcao"
    )


def test_seed_daily_aggregates_busca_cada_sessao_consumida_uma_so_vez_ordem_e_valores_batem(
    tmp_path, pregao_aberto,
):
    """`Gremah` sobrescreve os TRES hooks (feed M1, barato) -- prova que a
    fusao dos dois lacos que antes buscavam as MESMAS `_CAUDA_VOL_DIAS`
    sessoes duas vezes (um para `barra_diaria`, outro para
    `mediana_negocio_diario`) nao mudou UMA VIRGULA do que a estrategia
    recebe: mesma ORDEM (mais antiga primeiro) e mesmos VALORES -- so' que
    buscando cada sessao ao feed 1x em vez de 2x."""
    def _bar_on(date_str, hhmm, o, h, low, c, volume):
        return Bar(ts=pd.Timestamp(f"{date_str} {hhmm}", tz="UTC"),
                   open=float(o), high=float(h), low=float(low), close=float(c), volume=float(volume))

    # 2 sessoes ANTERIORES com dado; as outras 13 dentro de
    # `_CAUDA_VOL_DIAS` ficam vazias (`barra_diaria`/`mediana_negocio_
    # diario` de `[]` sao `None` e nao entram na janela -- mesmo
    # comportamento de antes da correcao).
    dia_2_atras = [
        _bar_on("2026-08-19", "13:00", 5.0, 5.2, 4.8, 5.1, 50.0),
        _bar_on("2026-08-19", "13:01", 5.1, 5.3, 4.9, 5.2, 150.0),
    ]
    dia_1_atras = [
        _bar_on("2026-08-20", "13:00", 10.0, 10.5, 9.8, 10.2, 100.0),
        _bar_on("2026-08-20", "13:01", 10.2, 11.0, 9.5, 10.9, 500.0),
        _bar_on("2026-08-20", "13:02", 10.9, 10.9, 10.9, 10.9, 300.0),
    ]
    semente = dia_2_atras + dia_1_atras
    rt, feed = _runtime(tmp_path, barras=[], semente=semente,
                        fixed_anchor_until=time(14, 0),
                        alvo_por_volatilidade=True, alvo_vol_mult=0.5,
                        capacidade_janela_dias=2)  # janela=2 pra' os 2 dias caberem

    from strategy.daytrade.lab.gremah import Gremah
    recebido: dict = {}
    original_vol = Gremah.seed_daily_volatility
    original_tip = Gremah.seed_typical_trade_size

    def _spy_vol(self, previous_daily_bars):
        recebido["daily_bars"] = list(previous_daily_bars)
        return original_vol(self, previous_daily_bars)

    def _spy_tip(self, previous_daily_medians):
        recebido["medians"] = list(previous_daily_medians)
        return original_tip(self, previous_daily_medians)

    Gremah.seed_daily_volatility = _spy_vol
    Gremah.seed_typical_trade_size = _spy_tip
    try:
        rt.run_once(now=_agora("15:01:00"))
    finally:
        Gremah.seed_daily_volatility = original_vol
        Gremah.seed_typical_trade_size = original_tip

    # UMA busca por sessao consumida: 1 (janela de volume) +
    # `_CAUDA_VOL_DIAS` (o laco fundido) -- nunca 1 + 2*`_CAUDA_VOL_DIAS`
    # (31 chamadas antes desta correcao, 16 depois).
    assert len(feed.pedidos_de_semente) == 1 + itr_mod._CAUDA_VOL_DIAS

    # ORDEM: mais antiga primeiro nos dois hooks, igual antes da fusao.
    assert [b.ts.date() for b in recebido["daily_bars"]] == [date(2026, 8, 19), date(2026, 8, 20)]

    # VALORES: a barra diaria agregada de cada sessao, exatamente como
    # `barra_diaria` calcularia isolado (nao uma media/mistura das duas).
    b19, b20 = recebido["daily_bars"]
    assert (b19.high, b19.low) == pytest.approx((5.3, 4.8))
    assert (b20.high, b20.low) == pytest.approx((11.0, 9.5))
    # `mediana_negocio_diario` de CADA sessao (mediana do volume de cada
    # evento DENTRO do dia -- mediana(50,150) -> 100.0; mediana(100,500,300)
    # -> 300.0), na MESMA ordem -- nao a mesma metrica de `barra_diaria`
    # numa resolucao diferente.
    assert recebido["medians"] == [pytest.approx(100.0), pytest.approx(300.0)]

    # fim a fim: o agregado que a estrategia efetivamente usa bate com o
    # calculo manual (mediana de [0.5, 1.5] = 1.0; mediana de [100, 300] =
    # 200.0 -- os dois com os 2 dias dentro da janela).
    assert rt.strategy._janela_vol.range_mediano() == pytest.approx(1.0)
    assert rt.strategy._janela_negocio_tipico.tipico_mediano() == pytest.approx(200.0)


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

    # 28 minutos entre um passo e outro (13:02 -> 13:30), bem acima de
    # `MAX_GAP_SECONDS`. O que dispara o buraco e' esse tempo SEM RODAR, nao a
    # quantidade de barras que se acumulou — ver a constante.
    feed._barras = barras + [
        _bar(f"13:{m:02d}", 9.50, 9.52, 9.48, 9.50) for m in range(2, 30)
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


def test_rajada_de_eventos_em_segundos_NAO_e_buraco(tmp_path, pregao_aberto):
    """O detector mede tempo SEM RODAR, nao quantidade de eventos.

    E' o caso que o feed de tick torna rotina: dezenas de negocios podem sair
    em segundos (`gremah_tick` recebe um evento por negocio, nao um por
    minuto). Contando eventos, como era ate 2026-08-22, cada rajada normal
    seria lida como "o processo ficou fora do ar" — o robo achataria a posicao
    e reiniciaria a sessao no meio de um pregao perfeitamente saudavel."""
    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, feed = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))
    rt.run_once(now=_agora("13:00:30"))

    # 40 eventos de preco (mais que o antigo teto de 15) chegando dentro de
    # 40 segundos — muito abaixo dos 15 minutos de `MAX_GAP_SECONDS`.
    base = pd.Timestamp("2026-08-21 13:00:30", tz="UTC")
    feed._barras = [
        Bar(ts=base + pd.Timedelta(seconds=s),
            open=9.50, high=9.50, low=9.50, close=9.50, volume=100.0)
        for s in range(1, 41)
    ]
    passos = rt.run_once(now=_agora("13:01:20"))

    assert [p.action for p in passos if p.action == "daytrade_buraco"] == []
    consumo = [p for p in passos if p.action == "daytrade"][0]
    assert consumo.detail["barras"] == 40


def test_buraco_recalibra_no_passo_seguinte(tmp_path, pregao_aberto):
    """Depois de achatar, o pregao CONTINUA: o robo tem de ser recalibrado
    (ainda ha janela fixa) em vez de adotar como abertura a primeira barra
    que vir depois do buraco."""
    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, feed = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))
    rt.run_once(now=_agora("13:01:00"))

    feed._barras = [_bar(f"13:{m:02d}", 9.50, 9.52, 9.48, 9.50)
                    for m in range(1, 18)]
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
    monkeypatch.setattr(itr_mod.clock, "intraday_session", lambda *a, **k: SESSION)

    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime(tmp_path, barras)

    passos = rt.run_once(now=_agora("21:00:00"))

    assert [p.action for p in passos] == ["idle"]


def test_dia_sem_pregao_nao_faz_nada(tmp_path, monkeypatch):
    from core.live_models import SessionPhase

    monkeypatch.setattr(itr_mod.clock, "phase", lambda *a, **k: SessionPhase.OPEN)
    monkeypatch.setattr(itr_mod.clock, "is_trading_day", lambda d: False)
    monkeypatch.setattr(itr_mod.clock, "intraday_session", lambda *a, **k: SESSION)

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
                                   fixed_anchor_until=time(14, 0),
                                   filtro_minutos_desde_abertura_min=None,
                                   filtro_volume_toque_max=None),
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
    # Sombra nunca manda ordem pra corretora -- sem ticket de verdade pra
    # mostrar (ver test_ordem_em_pe_mostra_o_ticket_de_verdade_da_corretora_em_modo_live).
    assert s["daytrade"]["ordem_em_pe"]["tickets"] is None


def test_painel_ve_a_ordem_em_pe_num_runtime_de_leitura_novo(tmp_path, pregao_aberto):
    """`/operacao` NAO reusa o runtime do robo: monta um de LEITURA novo a cada
    poll (`dashboard/live_service.py::_build_intraday_runtime`), com a maquina
    zerada. E `IntradaySessionMachine.state()` nao persiste `resting_limit` de
    proposito (e' uma DECISAO, redecidida pelo warm start).

    O resultado, ao vivo em 26/08/2026: a ordem #01 estava em pe no terminal
    (tres linhas "LIMITE LONG #01 ... (substitui)" no diario) e o cabecalho do
    cartao dizia "0/0" -- `ordem_em_pe` era SEMPRE `None` no painel, entao o
    contador de posicionadas nunca saia de zero e o "em pe @ preco" do card
    Ordens nunca aparecia. Ver `_SessionSnapshot.ordem_em_pe`."""
    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))
    rt.run_once(now=_agora("13:01:00"))

    # instancia NOVA sobre o MESMO banco -- o que o painel faz
    painel, _f = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))
    ordem = painel.status()["daytrade"]["ordem_em_pe"]

    assert ordem is not None, "painel perdeu a ordem-limite em pe"
    assert ordem["lado"] == "long"
    assert ordem["preco"] == pytest.approx(9.80)
    # Uma ordem REAL por lote que falta preencher -- e' o "y" do "x/y".
    assert ordem["ordens"] == 1
    # `quantidade` e' em ACOES (1 lote = 100 acoes neste papel), nao em lotes --
    # mesma unidade de `Order.quantity`.
    assert ordem["quantidade"] == 100


def test_painel_conta_posicoes_independentes_sem_estourar(tmp_path, pregao_aberto):
    """Sombra abre uma posicao INDEPENDENTE por lote preenchido (2026-08-24).
    `status()` usava `machine.position`, o atalho de 1 posicao, que levanta
    `RuntimeError` com duas -- `/operacao` inteiro virava erro no pregao em que
    o robo dividiu a entrada e pegou dois lotes. E a contagem do cartao vinha
    de `account.positions`, um dicionario POR TICKER: numa conta de day trade
    (um simbolo so') ela era sempre 0 ou 1, dissesse a verdade ou nao."""
    semente = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))
    rt.run_once(now=_agora("13:01:00"))
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        estado = dict(acc.policy_state)
        estado["intraday"]["machine"]["positions"] = [
            {"side": "long", "entry_ts": "2026-08-21T13:02:00+00:00",
             "entry_price": 9.80, "quantity": 1, "current_stop": 9.60,
             "current_target": 9.90, "bars_held": 1, "metadata": {}},
            {"side": "long", "entry_ts": "2026-08-21T13:03:00+00:00",
             "entry_price": 9.60, "quantity": 1, "current_stop": 9.40,
             "current_target": 9.90, "bars_held": 1, "metadata": {}},
        ]
        acc.policy_state = estado
        store.save_account(conn, acc)

    painel, _f = _runtime(tmp_path, barras=[], semente=semente, fixed_anchor_until=time(14, 0))
    dt = painel.status()["daytrade"]

    assert dt["posicoes_compra"] == 2
    assert dt["posicoes_venda"] == 0
    assert dt["valor_posicoes_compra"] == pytest.approx(19.40)
    # Agregado: quantidade somada, entrada media ponderada.
    assert dt["posicao_aberta"]["qtd"] == 2
    assert dt["posicao_aberta"]["posicoes"] == 2
    assert dt["posicao_aberta"]["entrada"] == pytest.approx(9.70)
    # Alvo igual nas duas -> sai; stop diferente -> `None`, e nao o da primeira.
    assert dt["posicao_aberta"]["alvo"] == pytest.approx(9.90)
    assert dt["posicao_aberta"]["stop"] is None


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


# ---------- caixa minimo do dia (1x o lote, reavaliado a cada pregao) -------

def _set_cash(rt, valor: float) -> None:
    """Mexe nos DOIS saldos (2026-08-23, ver `AccountState.cash_for`): estes
    testes cobrem o gate de caixa-do-dia em si, não a separação sombra/real
    -- mantendo `cash_sombra` igual a `cash` eles continuam válidos
    independente de qual dos dois `_check_capital` está lendo para o
    `execution_mode` da fixture (`_runtime()` default `"shadow"`)."""
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = valor
        acc.cash_sombra = valor
        store.save_account(conn, acc)


def test_caixa_abaixo_do_minimo_do_dia_nao_opera(tmp_path, pregao_aberto):
    """Regra do dono (2026-08-24): depois de iniciado, o piso do dia e' so' o
    custo do lote NO PRECO DE HOJE (o 2x fica so' na barreira de entrada, ver
    `live_control.start`). Com `default_quantity=1` a R$10,00, o minimo e'
    R$10,00 -- R$5,00 em caixa nao pode operar."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    _set_cash(rt, 5.00)

    passos = rt.run_once(now=_agora("13:02:30"))

    skip = [p for p in passos if p.action == "daytrade_skip"]
    assert skip, f"deveria recusar por caixa; passos={[p.action for p in passos]}"
    assert skip[0].detail["motivo"] == "caixa abaixo do minimo"
    # e nao operou de verdade: nenhuma posicao, nenhum trade
    assert rt.machine.position is None
    assert rt._snapshot.trades == 0


def test_caixa_suficiente_opera_normalmente(tmp_path, pregao_aberto):
    """Contraprova do teste acima -- mesmo roteiro, so' o caixa muda."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    _set_cash(rt, 10.00)  # exatamente o minimo: 1 acao a R$10

    passos = rt.run_once(now=_agora("13:02:30"))

    assert not any(p.action == "daytrade_skip" for p in passos)


def _set_cash_sombra(rt, valor: float) -> None:
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash_sombra = valor
        store.save_account(conn, acc)


def test_gate_de_caixa_em_sombra_le_cash_sombra_nao_cash(tmp_path, pregao_aberto):
    """O ponto central do pedido do dono (2026-08-23): rodando em
    `execution_mode="shadow"`, o gate diario (`_check_capital`) tem de olhar
    `cash_sombra`, nao `cash` -- um robo de teste em sombra com pouco caixa
    REAL (ou zero) mas saldo de sombra suficiente tem de continuar operando.

    Chama `_check_capital` DIRETO (nao `run_once`): `_start_session` decide o
    grid de entrada a partir so' da semente (preco atual, sem precisar de
    toque ainda) e, em `execution_mode="live"`, mandaria a ordem pra
    corretora ANTES deste gate ser consultado -- um detalhe de sequencia de
    `run_once` alheio ao que este teste cobre, e que faria a contraprova
    (`test_gate_de_caixa_em_live_le_cash_nao_cash_sombra`) esbarrar num
    dublê de corretora que so' entende sombra."""
    rt, _feed = _runtime(tmp_path, [_bar("13:00", 10.00, 10.00, 10.00, 10.00)],
                        execution_mode="shadow")
    _set_cash(rt, 0.0)            # caixa real: nao cobriria o minimo de R$10
    _set_cash_sombra(rt, 10.00)   # saldo de sombra: cobre exatamente

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        alarme = rt._check_capital(conn, acc, SESSION, preco=10.00)

    assert alarme is None


def test_gate_de_caixa_em_live_le_cash_nao_cash_sombra(tmp_path, pregao_aberto):
    """Contraprova: em `execution_mode="live"`, o mesmo gate continua sendo o
    caixa REAL -- um saldo de sombra generoso nao pode liberar dinheiro de
    verdade que nao existe."""
    rt, _feed = _runtime(tmp_path, [_bar("13:00", 10.00, 10.00, 10.00, 10.00)],
                        execution_mode="live")
    _set_cash(rt, 5.00)           # caixa real: nao cobre o minimo de R$10
    _set_cash_sombra(rt, 1_000.00)  # saldo de sombra: irrelevante em live

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        alarme = rt._check_capital(conn, acc, SESSION, preco=10.00)

    assert alarme is not None
    assert "nao cobre o minimo" in alarme


def test_minimo_do_dia_sai_do_preco_e_da_quantidade_reais(tmp_path, pregao_aberto):
    """O piso nao e' um numero fixo em lugar nenhum: sai de `preco_de_hoje x
    quantidade_do_robo`. Um papel que dobrou de preco exige o dobro de caixa
    no mesmo robo."""
    barras = [
        _bar("13:00", 40.00, 40.00, 40.00, 40.00),  # semente (warm start)
        _bar("13:01", 40.00, 40.00, 39.90, 40.00),  # a consumida: e o close DELA que vale
    ]
    rt, _feed = _runtime(tmp_path, barras)
    _set_cash(rt, 10.00)

    rt.run_once(now=_agora("13:02:30"))

    # 1 acao (default_quantity do harness) a R$40,00 -> piso R$40.
    # O preco vem do close da ULTIMA barra fechada -- o mais recente que existe.
    assert rt._capital_minimo_hoje == pytest.approx(40.0)
    assert "40.00" in rt._capital_alarm


def test_caixa_e_conferido_uma_vez_por_pregao_nao_a_cada_barra(tmp_path, pregao_aberto):
    """O numero so muda de pregao para pregao. Reavaliar a cada barra
    encheria `live_events` com o mesmo alarme centenas de vezes por dia e
    enterraria os eventos que exigem acao."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.90, 9.80, 9.88),
    ]
    rt, feed = _runtime(tmp_path, barras)
    _set_cash(rt, 5.00)

    rt.run_once(now=_agora("13:02:30"))
    rt.run_once(now=_agora("13:03:30"))
    rt.run_once(now=_agora("13:04:30"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = store.recent_events(conn, acc.id, limit=50)
    alarmes = [e for e in eventos if "nao cobre o minimo" in str(e)]
    assert len(alarmes) == 1, f"alarme de caixa repetido {len(alarmes)}x no diario"


def test_sem_caixa_mas_com_posicao_aberta_ainda_roda_para_poder_fechar(tmp_path, pregao_aberto):
    """Um robo sem caixa ainda precisa conseguir FECHAR o que ja esta na rua.
    Travar aqui deixaria a posicao orfa ate o flatten -- mesmo principio do
    piso de R$50 no `live_control.start()`, que tambem so barra a PARTIDA."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),  # semente: arma o grid
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),    # toca o nivel long (9.80): ABRE
        # alvo fica em 9.90 -- os candles seguintes NAO podem alcanca-lo, senao
        # a posicao fecha e o cenario deste teste deixa de existir.
        _bar("13:02", 9.85, 9.88, 9.82, 9.86),
        _bar("13:03", 9.86, 9.88, 9.83, 9.87),      # sobra para o 2o run_once
    ]
    rt, _feed = _runtime(tmp_path, barras)
    rt.run_once(now=_agora("13:02:30"))
    assert rt.machine.position is not None, "cenario invalido: nao abriu posicao"

    # o caixa despenca e o piso e' reavaliado (novo pregao / novo processo)
    _set_cash(rt, 0.01)
    rt._capital_checked_for = None

    passos = rt.run_once(now=_agora("13:03:30"))

    assert not any(p.action == "daytrade_skip" for p in passos), (
        "com posicao aberta o robo tem de continuar rodando para conseguir sair"
    )


def test_status_mostra_o_minimo_do_dia_e_o_alarme(tmp_path, pregao_aberto):
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),  # semente
        _bar("13:01", 10.00, 10.00, 9.95, 10.00),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    _set_cash(rt, 5.00)
    rt.run_once(now=_agora("13:02:30"))

    dt = rt.status()["daytrade"]

    assert dt["capital_minimo_hoje"] == pytest.approx(10.0)
    assert "nao cobre o minimo" in dt["capital_alarme"]


# ---------- aviso de capital para um ativo novo (enxame, 2026-08-22) --------

def _com_preco_de_candidato(monkeypatch, preco: float | None):
    """`last_close` do proximo da fila. `None` = sem parquet salvo."""
    monkeypatch.setattr(
        "market_data_intraday.storage.last_close",
        lambda symbol, *a, **k: (preco, "2026-08-21") if preco else (None, ""),
    )


def test_avisa_uma_vez_quando_o_caixa_banca_um_ativo_novo(tmp_path, pregao_aberto, monkeypatch):
    """O robo em operacao sinaliza que da' para o dono abrir um robo novo. E'
    so' um AVISO: nada e' aberto, nada e' aportado, o caixa dele nao muda.

    Uma vez por ativo, e nao a cada barra: a condicao continua verdadeira em
    todas as barras seguintes, e sem a deduplicacao a caixa de mensagens
    viraria log de spam."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 10.00, 10.00),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    # `_config()` usa `default_quantity=1` (lote de 1 acao) nestes testes:
    # proprio a R$10 -> minimo R$20; candidato (KLBN4) a R$1 -> minimo R$2.
    # Barra: caixa >= 2 + 20.
    _com_preco_de_candidato(monkeypatch, 1.00)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = 30.0
        store.save_account(conn, acc)

    rt.run_once(now=_agora("13:05:00"))

    with store.live_journal(rt.db_path) as conn:
        avisos = store.capital_signals(conn)
        caixa_depois = store.load_account(conn, SLOT.id).cash
    assert [(a["robot"], a["suggested_symbol"]) for a in avisos] == [("gremah", "KLBN4")]
    assert avisos[0]["required_brl"] == pytest.approx(2.0)
    # O aviso nao move dinheiro nenhum.
    assert caixa_depois == pytest.approx(30.0)

    # Pregao seguinte, mesma condicao ainda verdadeira: nao duplica.
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        rt._signal_checked_for = None
        rt._avaliar_sugestao_de_capital(conn, acc, date(2026, 8, 24), 10.00)
        assert len(store.capital_signals(conn)) == 1


def test_nao_avisa_quando_o_caixa_nao_cobre_os_dois_minimos(tmp_path, pregao_aberto, monkeypatch):
    """Precisa cobrir o minimo do candidato E continuar cobrindo o proprio —
    avisar sem isso empurraria o dono a esvaziar o robo que ja opera."""
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00),
              _bar("13:01", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime(tmp_path, barras)
    _com_preco_de_candidato(monkeypatch, 1.00)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = 21.99   # falta R$0,01 para os R$22 (ver o teste acima)
        store.save_account(conn, acc)

    rt.run_once(now=_agora("13:05:00"))

    with store.live_journal(rt.db_path) as conn:
        assert store.capital_signals(conn) == []


def test_falha_ao_avaliar_sugestao_nunca_derruba_o_robo(tmp_path, pregao_aberto, monkeypatch):
    """Um aviso e' conveniencia. Parquet ilegivel, simbolo sem calibracao ou
    registry fora do ar nao podem parar um robo que esta operando dinheiro."""
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00),
              _bar("13:01", 10.00, 10.00, 9.79, 9.85)]
    rt, _feed = _runtime(tmp_path, barras)

    def _explode(*a, **k):
        raise RuntimeError("parquet ilegivel")

    monkeypatch.setattr("market_data_intraday.storage.last_close", _explode)

    passos = rt.run_once(now=_agora("13:05:00"))

    assert [p for p in passos if p.action == "daytrade"]  # o robo operou normalmente
    with store.live_journal(rt.db_path) as conn:
        assert store.capital_signals(conn) == []
        avisos_log = [r["message"] for r in conn.execute(
            "SELECT message FROM live_events WHERE level = 'warn'")]
    assert any("sugestao de capital" in m for m in avisos_log)


# ---------- cards do painel: ganhos/perdas, CAGR/DD, acerto por lado (2026-08-24) ----------

def test_resultado_dia_e_acumulado_separa_hoje_do_historico():
    saidas = [
        {"date": "2026-08-21", "round": 1, "side": "long", "pnl_brl": 20.0},
        {"date": "2026-08-21", "round": 2, "side": "long", "pnl_brl": -8.0},
        {"date": "2026-08-24", "round": 1, "side": "long", "pnl_brl": 10.0},
        # rodada dividida em 2 fatias -- soma antes de contar ganho/perda
        {"date": "2026-08-24", "round": 2, "side": "short", "pnl_brl": -5.0},
        {"date": "2026-08-24", "round": 2, "side": "short", "pnl_brl": -3.0},
    ]
    r = IntradayLiveRuntime._resultado_dia_e_acumulado(saidas, "2026-08-24", 1000.0)

    assert r["ganhos_dia"] == 10.0
    assert r["perdas_dia"] == 8.0
    assert r["lucro_acumulado"] == 30.0
    assert r["prejuizo_acumulado"] == 16.0
    # do dia: +10, depois -5 (pico 10 -> 5), depois -3 (5 -> 2) = DD -8 sobre pico 10
    assert r["retorno_dia_pct"] == 0.2
    assert r["dd_dia_pct"] == -0.8
    # acumulado: +20, -8 (DD -8), +10 (pico 22), -5, -3 (22 -> 14, DD -8)
    assert r["retorno_acumulado_pct"] == 1.4
    assert r["dd_acumulado_pct"] == -0.8


def test_acerto_por_lado_e_por_rodada_nao_por_fatia():
    """A rodada #02 fecha em 2 fatias (-5 e -3): precisa contar como UMA
    derrota de venda, nao duas."""
    saidas = [
        {"date": "2026-08-24", "round": 1, "side": "long", "pnl_brl": 10.0},
        {"date": "2026-08-24", "round": 2, "side": "short", "pnl_brl": -5.0},
        {"date": "2026-08-24", "round": 2, "side": "short", "pnl_brl": -3.0},
        {"date": "2026-08-21", "round": 1, "side": "long", "pnl_brl": 20.0},
        {"date": "2026-08-21", "round": 2, "side": "long", "pnl_brl": -8.0},
    ]
    r = IntradayLiveRuntime._resultado_dia_e_acumulado(saidas, "2026-08-24", 1000.0)

    assert r["acerto_compra_pct"] == 67  # 2 de 3 rodadas de compra ganharam
    assert r["acerto_venda_pct"] == 0    # a unica rodada de venda perdeu


def test_acerto_por_lado_sem_historico_e_none():
    r = IntradayLiveRuntime._resultado_dia_e_acumulado([], "2026-08-24", 1000.0)
    assert r["acerto_compra_pct"] is None
    assert r["acerto_venda_pct"] is None


def test_ordens_por_lado_conta_armada_preenchida_e_cancelada():
    ordens = [
        {"side": "long", "kind": "armada", "quantity": 100, "price": 10.0},
        {"side": "long", "kind": "preenchida", "quantity": 100, "price": 10.0},
        {"side": "short", "kind": "armada", "quantity": 100, "price": 20.0},
        {"side": "short", "kind": "cancelada", "quantity": 100, "price": 20.0},
        {"side": "short", "kind": "armada", "quantity": 50, "price": 21.0},
    ]
    r = IntradayLiveRuntime._ordens_por_lado(ordens)

    assert r["ordens_compra"] == 1
    assert r["ordens_venda"] == 2
    assert r["preenchida_compra_pct"] == 100
    assert r["preenchida_venda_pct"] == 0
    # nocional das ARMADAS, mesma populacao da contagem acima -- nao soma a
    # preenchida/cancelada, que sao a MESMA rodada contada de outro jeito.
    assert r["valor_ordens_compra"] == 1000.0  # 100 x 10.0
    assert r["valor_ordens_venda"] == 3050.0   # 100 x 20.0 + 50 x 21.0


def test_ordens_por_lado_sem_desfecho_ainda_e_none():
    r = IntradayLiveRuntime._ordens_por_lado([{"side": "long", "kind": "armada"}])
    assert r["preenchida_compra_pct"] is None
    assert r["preenchida_venda_pct"] is None
    # evento sem quantity/price (ex.: payload antigo) nao contribui pro
    # valor, mas tambem nao quebra a soma.
    assert r["valor_ordens_compra"] == 0.0
    assert r["valor_ordens_venda"] == 0.0


def test_ordens_por_lado_nao_conta_reancoragem_da_mesma_rodada_como_ordem_nova():
    """Queixa do dono, 2026-08-27: o diario so' tinha chegado em "#02" mas o
    card "Ordens" mostrava 4 -- cada "(substitui)" (mesma rodada, preco novo,
    ver `_on_limit_placed`) vinha somando +1 e o nocional do preco
    abandonado, em vez de so' atualizar a rodada existente."""
    ordens = [
        {"side": "long", "kind": "armada", "quantity": 100, "price": 10.0, "numero_ordem": 1},
        {"side": "long", "kind": "armada", "quantity": 100, "price": 11.0, "numero_ordem": 1},  # substitui #01
        {"side": "long", "kind": "armada", "quantity": 100, "price": 9.0, "numero_ordem": 2},   # rodada NOVA
    ]
    r = IntradayLiveRuntime._ordens_por_lado(ordens)

    assert r["ordens_compra"] == 2                   # #01 (uma vez so') + #02
    # nocional: ULTIMO preco de #01 (11.0, nao 10.0) + preco de #02 -- nunca
    # soma as duas reancoragens da mesma rodada.
    assert r["valor_ordens_compra"] == 100 * 11.0 + 100 * 9.0

    # sem `numero_ordem` (payload antigo) cada linha continua contando
    # sozinha, exatamente como antes desta mudanca.
    legado = [
        {"side": "short", "kind": "armada", "quantity": 50, "price": 20.0},
        {"side": "short", "kind": "armada", "quantity": 50, "price": 21.0},
    ]
    r2 = IntradayLiveRuntime._ordens_por_lado(legado)
    assert r2["ordens_venda"] == 2
    assert r2["valor_ordens_venda"] == 50 * 20.0 + 50 * 21.0


def test_status_traz_ganhos_perdas_cagr_dd_e_acerto_por_lado_de_ponta_a_ponta(
    tmp_path, pregao_aberto,
):
    """Mesmo roteiro do teste de numeracao (2 rodadas fechadas com lucro, uma
    3a so' posicionada) -- aqui o alvo e' `status()` de ponta a ponta:
    `live_store.daytrade_exit_events`/`daytrade_order_events_on` lendo os
    EVENTOS DE VERDADE gravados no sqlite (nao dados de teste inventados),
    provando que o `tipo` que o painel classifica e' o mesmo que o runtime
    realmente grava no payload. Era um filtro por TEXTO da mensagem ate'
    2026-08-25 -- ver `test_card_de_ordens_nao_depende_do_texto_da_mensagem`,
    que e' o teste que guarda essa fronteira agora."""
    # ROTEIRO COMPRIMIDO em 2026-09-08: as barras andam de 20 em 20s (nao
    # de minuto em minuto) e `now` fica logo depois da ultima. Motivo:
    # desde `MAX_ATRASO_PARA_ORDEM_SEGUNDOS`, barra mais velha que o teto
    # nao gera ORDEM NOVA -- e um roteiro de 6 minutos consumido num
    # `run_once` so' deixava a barra de abertura com 5+ min de idade. O
    # que este teste mede (sequencia de OHLC, numeracao, P&L) nao depende
    # do espacamento; a idade agora depende.
    barras = [
        _bar("13:00:00", 10.00, 10.00, 10.00, 10.00),  # abertura: posiciona a 1a (long)
        _bar("13:00:20", 10.00, 10.00, 9.79, 9.85),    # toca o nivel long (9.80)
        _bar("13:00:40", 9.85, 9.91, 9.85, 9.90),      # toca o alvo (9.90) -- fecha #01 (+10)
        _bar("13:01:00", 9.90, 9.90, 9.79, 9.85),      # repete LONG (ganhou) e preenche #02
        _bar("13:01:20", 9.85, 9.91, 9.85, 9.90),      # toca o alvo de novo -- fecha #02 (+10)
        _bar("13:01:40", 9.90, 9.90, 9.90, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    rt.run_once(now=_agora("13:01:45"))

    s = rt.status()["daytrade"]

    assert s["ganhos_dia"] == 20.0
    assert s["perdas_dia"] == 0.0
    assert s["lucro_acumulado"] == 20.0
    assert s["prejuizo_acumulado"] == 0.0
    # capital inicial de teste = R$100 (ver `_runtime`); +20 e' 20% de retorno
    assert s["retorno_dia_pct"] == 20.0
    assert s["dd_dia_pct"] == 0.0
    assert s["retorno_acumulado_pct"] == 20.0
    assert s["dd_acumulado_pct"] == 0.0
    assert s["acerto_compra_pct"] == 100  # as duas rodadas (long) ganharam
    # Sem NENHUMA rodada vendida no roteiro, a taxa e' `None` ("nao houve"),
    # nunca 0 ("houve e errou todas") -- distincao que o painel mostra com
    # texto diferente. As duas rodadas sao long porque o robo REPETE o lado
    # depois de um trade lucrativo desde 2026-08-26 (memoria
    # `gremah_repetir_ultimo_vencedor`); o roteiro antigo assumia alternancia
    # pura e ficou vermelho medindo um comportamento aposentado.
    assert s["acerto_venda_pct"] is None

    # #01 nasce do WARM START (planta direto em `resting_limit`, sem passar
    # por `_on_limit_placed` -- nunca loga "posicionada", ver a docstring de
    # `_numero_ordem_atual`), entao so' #02 e #03 contam como ARMADAS aqui.
    # `_on_opened` grava "entrada" independente da origem da ordem, entao o
    # preenchimento de #01 ainda entra no numerador/denominador da taxa de
    # preenchimento de compra (so' nao no de armadas).
    assert s["ordens_compra"] == 2   # #02 e #03 -- #01 foi warm start
    assert s["ordens_venda"] == 0
    assert s["preenchida_compra_pct"] == 100  # as duas entradas preencheram
    assert s["preenchida_venda_pct"] is None
    # nocional das armadas -- nao precisa do valor exato aqui (isso ja' e'
    # coberto por `test_ordens_por_lado_conta_armada_preenchida_e_cancelada`).
    assert s["valor_ordens_compra"] > 0
    assert s["valor_ordens_venda"] == 0

    # sem posicao aberta no fim do roteiro (so' uma ordem #03 pendente)
    assert s["posicoes_compra"] == 0
    assert s["posicoes_venda"] == 0
    assert s["valor_posicoes_compra"] == 0.0
    assert s["valor_posicoes_venda"] == 0.0


def test_valor_posicoes_reflete_capital_alocado_da_posicao_aberta(tmp_path, pregao_aberto):
    """`valor_posicoes_compra`/`valor_posicoes_venda` (pedido do dono,
    2026-08-24: "deve aparecer os valores, e as quantidades abaixo") tem de
    bater com o capital de verdade alocado na posicao aberta, nao so'
    contar 1 posicao como o card mostrava antes."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),  # abertura: posiciona (long)
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),    # toca o nivel long (9.80) -- entra, ainda aberta
    ]
    rt, _feed = _runtime(tmp_path, barras)
    rt.run_once(now=_agora("13:02:00"))

    full = rt.status()
    s = full["daytrade"]

    assert s["posicoes_compra"] == 1
    assert s["posicoes_venda"] == 0
    assert full["posicoes"][0]["qtd"] > 0
    esperado = full["posicoes"][0]["qtd"] * full["posicoes"][0]["entrada"]
    assert s["valor_posicoes_compra"] == pytest.approx(esperado)
    assert s["valor_posicoes_venda"] == 0.0


# ---------- bug de caixa de FUTURO corrigido 2026-08-31 ---------------------
# WIN@/WDO@ cotam em PONTOS, nao em reais -- o caixa ao vivo (abertura,
# top-up, fechamento total/parcial, e os cards "Posicoes"/"Ordens" do
# painel) debitava/creditava `preco * quantidade`, tratando o preco como se
# fosse dinheiro. Achado do dono: WIN@ vendido a ~137.000 pontos aparecia
# como -R$180.455,00 de caixa com 1 UNICO contrato aberto. `IntradayTrade.
# pnl_brl` (o resultado fechado) sempre usou o `point_value_brl` certo e
# nunca teve esse bug -- o que faltava era `_custo_posicao` (o que MOVE
# caixa/margem na abertura e no fechamento) usar `margin_per_contract_brl`
# em vez do preco. Exemplos abaixo conferidos com o dono antes de virar
# teste (2026-08-31).

@pytest.mark.parametrize("side,entrada,saida,esperado,rotulo", [
    ("long", 137_000.0, 137_000.0, 0.0, "compra empate"),
    ("long", 137_000.0, 136_500.0, -100.0, "compra prejuizo (caiu 500 pts)"),
    ("long", 137_000.0, 137_500.0, 100.0, "compra lucro (subiu 500 pts)"),
    ("short", 137_000.0, 137_000.0, 0.0, "venda empate"),
    ("short", 137_000.0, 137_500.0, -100.0, "venda prejuizo (subiu 500 pts contra)"),
    ("short", 137_000.0, 136_500.0, 100.0, "venda lucro (caiu 500 pts a favor)"),
])
def test_pnl_win_usa_valor_do_ponto_no_sinal_certo_por_lado(side, entrada, saida, esperado, rotulo):
    """WIN@ = R$0,20/ponto (`FUTURES_PROFILES["WIN@"]`, confirmado em
    `test_intraday_profiles.py::
    test_override_de_tick_corrige_a_grade_de_preco_sem_mexer_no_valor_do_ponto`).
    O sinal da VENDA e' so' indicativo visual (`entrada - saida`, em vez de
    `saida - entrada` da compra) -- o R$ final e' sempre pela DIRECAO do
    movimento, nunca confundido com o preco de entrada."""
    trade = IntradayTrade(
        symbol="WIN@", strategy_name="teste", strategy_version="1",
        side=side, entry_ts=pd.Timestamp("2026-08-31 10:00", tz="UTC"),
        entry_price=entrada, exit_ts=pd.Timestamp("2026-08-31 10:05", tz="UTC"),
        exit_price=saida, quantity=1, exit_reason=IntradayExitReason.TARGET,
        point_value_brl=0.20, capital_base=100.0,
    )
    assert trade.pnl_brl == pytest.approx(esperado), rotulo


def test_pnl_wdo_usa_valor_do_ponto_de_dez_reais():
    """WDO@ = R$10,00/ponto -- mesmo caso "venda lucro" da tabela conferida
    com o dono, so' pra provar que a formula generaliza pro outro futuro."""
    trade = IntradayTrade(
        symbol="WDO@", strategy_name="teste", strategy_version="1",
        side="short", entry_ts=pd.Timestamp("2026-08-31 10:00", tz="UTC"),
        entry_price=5_450.0, exit_ts=pd.Timestamp("2026-08-31 10:05", tz="UTC"),
        exit_price=5_440.0, quantity=1, exit_reason=IntradayExitReason.TARGET,
        point_value_brl=10.0, capital_base=150.0,
    )
    assert trade.pnl_brl == pytest.approx(100.0)


def test_custo_posicao_de_futuro_usa_a_margem_nao_o_preco_em_pontos(tmp_path):
    """Caso EXATO do achado do dono: WIN@ a ~137.000 pontos nao pode
    comprometer R$137.000 de caixa -- so' a margem por contrato."""
    margem = FUTURES_PROFILES["WIN@"].margin_per_contract_brl
    rt, _feed = _runtime(
        tmp_path, barras=[], symbol="WIN@", slot=SLOT_WIN,
        config=_config_futuro(margem), initial_capital=1_000.0,
        # WIN@ nao tem calibracao de capacidade de caixa (so' acoes tem, ver
        # `_CAPACIDADE_BY_SYMBOL` em `gremah.py`) -- override explicito
        # necessario so' pra' construir a estrategia, sem efeito no que este
        # teste mede.
        capacidade_negocio_mult=1.0, capacidade_fracao=0.10,
        # `shares_per_lot=1`: WIN@/WDO@ operam em CONTRATOS, nao em lotes de
        # 100 acoes (`LOTE_PADRAO_B3`, o default de `Gremah` -- ver
        # `scripts/daytrade/cripto_comum.py` pro mesmo ajuste em outro
        # instrumento nao-lote-de-100). "gremah" so' serve de dublê de
        # estrategia aqui; a granularidade certa e' o que importa.
        shares_per_lot=1,
    )
    assert rt._custo_posicao(137_000.0, 1) == pytest.approx(margem)
    assert rt._custo_posicao(137_000.0, 2) == pytest.approx(margem * 2)


def test_custo_posicao_de_futuro_wdo_usa_a_margem_de_150(tmp_path):
    margem = FUTURES_PROFILES["WDO@"].margin_per_contract_brl
    rt, _feed = _runtime(
        tmp_path, barras=[], symbol="WDO@", slot=slot_by_id("dt-gremah-wdo@-shadow"),
        config=_config_futuro(margem), initial_capital=1_000.0,
        capacidade_negocio_mult=1.0, capacidade_fracao=0.10,
        # `shares_per_lot=1`: WIN@/WDO@ operam em CONTRATOS, nao em lotes de
        # 100 acoes (`LOTE_PADRAO_B3`, o default de `Gremah` -- ver
        # `scripts/daytrade/cripto_comum.py` pro mesmo ajuste em outro
        # instrumento nao-lote-de-100). "gremah" so' serve de dublê de
        # estrategia aqui; a granularidade certa e' o que importa.
        shares_per_lot=1,
    )
    assert rt._custo_posicao(5_450.0, 1) == pytest.approx(margem)


def test_custo_posicao_de_acao_continua_usando_preco_vezes_quantidade(tmp_path):
    """Regressao inversa: sem margem configurada (toda ACAO, `_config()`
    default), o fallback tem de continuar sendo o preco cheio -- e' o
    caminho que todo o resto deste arquivo ja' depende."""
    rt, _feed = _runtime(tmp_path, barras=[])
    assert rt._custo_posicao(10.0, 100) == pytest.approx(1_000.0)


def test_valor_posicoes_de_futuro_mostra_margem_nao_preco_em_pontos(tmp_path, pregao_aberto):
    """Reproducao do achado do dono, 2026-08-31: WIN@ VENDIDO (short) a
    137.000 pontos aparecia no painel como R$137.000,00 em vez de R$100,00
    de margem. Mesma tecnica de injecao de estado de
    `test_painel_conta_posicoes_independentes_sem_estourar`: escreve a
    posicao direto em `policy_state` e le com um runtime de LEITURA novo --
    e' assim que o painel (`dashboard/live_service.py`) sempre le, nunca
    reusando o processo do robo."""
    margem = FUTURES_PROFILES["WIN@"].margin_per_contract_brl
    config = _config_futuro(margem)
    semente = [_bar("13:00", 137_000.0, 137_000.0, 137_000.0, 137_000.0)]
    rt, _feed = _runtime(
        tmp_path, barras=[], semente=semente, symbol="WIN@", slot=SLOT_WIN,
        config=config, initial_capital=1_000.0, fixed_anchor_until=time(14, 0),
        capacidade_negocio_mult=1.0, capacidade_fracao=0.10,
        # `shares_per_lot=1`: WIN@/WDO@ operam em CONTRATOS, nao em lotes de
        # 100 acoes (`LOTE_PADRAO_B3`, o default de `Gremah` -- ver
        # `scripts/daytrade/cripto_comum.py` pro mesmo ajuste em outro
        # instrumento nao-lote-de-100). "gremah" so' serve de dublê de
        # estrategia aqui; a granularidade certa e' o que importa.
        shares_per_lot=1,
    )
    rt.run_once(now=_agora("13:01:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT_WIN.id)
        estado = dict(acc.policy_state)
        estado["intraday"]["machine"]["positions"] = [
            {"side": "short", "entry_ts": "2026-08-31T13:02:00+00:00",
             "entry_price": 137_000.0, "quantity": 1, "current_stop": 138_000.0,
             "current_target": 136_000.0, "bars_held": 1, "metadata": {}},
        ]
        acc.policy_state = estado
        store.save_account(conn, acc)

    painel, _f = _runtime(
        tmp_path, barras=[], semente=semente, symbol="WIN@", slot=SLOT_WIN,
        config=config, initial_capital=1_000.0, fixed_anchor_until=time(14, 0),
        capacidade_negocio_mult=1.0, capacidade_fracao=0.10,
        # `shares_per_lot=1`: WIN@/WDO@ operam em CONTRATOS, nao em lotes de
        # 100 acoes (`LOTE_PADRAO_B3`, o default de `Gremah` -- ver
        # `scripts/daytrade/cripto_comum.py` pro mesmo ajuste em outro
        # instrumento nao-lote-de-100). "gremah" so' serve de dublê de
        # estrategia aqui; a granularidade certa e' o que importa.
        shares_per_lot=1,
    )
    dt = painel.status()["daytrade"]

    assert dt["posicoes_venda"] == 1
    assert dt["valor_posicoes_venda"] == pytest.approx(margem)      # R$100,00
    assert dt["valor_posicoes_venda"] != pytest.approx(137_000.0)   # o bug antigo
    assert dt["valor_posicoes_compra"] == 0.0


def test_caixa_de_futuro_bloqueia_margem_na_abertura_nao_o_preco(tmp_path, pregao_aberto):
    """Mesmo roteiro de barras de
    `test_valor_posicoes_reflete_capital_alocado_da_posicao_aberta` (preco
    de teste ~10,00 -- nao precisa parecer WIN@ de verdade pra provar isto,
    o unico ingrediente novo aqui e' `margin_per_contract_brl` na config).
    Com margem ligada, abrir a posicao debita a MARGEM do caixa sombra,
    nunca `preco * quantidade`."""
    margem = 100.0
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime(
        tmp_path, barras, symbol="WIN@", slot=SLOT_WIN,
        config=_config_futuro(margem), initial_capital=1_000.0,
        capacidade_negocio_mult=1.0, capacidade_fracao=0.10,
        # `shares_per_lot=1`: WIN@/WDO@ operam em CONTRATOS, nao em lotes de
        # 100 acoes (`LOTE_PADRAO_B3`, o default de `Gremah` -- ver
        # `scripts/daytrade/cripto_comum.py` pro mesmo ajuste em outro
        # instrumento nao-lote-de-100). "gremah" so' serve de dublê de
        # estrategia aqui; a granularidade certa e' o que importa.
        shares_per_lot=1,
    )
    rt.run_once(now=_agora("13:02:00"))

    full = rt.status()
    qtd = full["posicoes"][0]["qtd"]
    assert qtd > 0
    assert full["daytrade"]["valor_posicoes_compra"] == pytest.approx(margem * qtd)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT_WIN.id)
    # o bug antigo debitaria preco*quantidade (~9,80 x qtd) -- caixa quase
    # intacto, nao a margem de verdade.
    assert acc.cash_sombra == pytest.approx(1_000.0 - margem * qtd)


def test_caixa_de_futuro_libera_margem_mais_pnl_ao_fechar(tmp_path, pregao_aberto):
    """Roteiro de `test_status_traz_ganhos_perdas_cagr_dd_e_acerto_por_lado_
    de_ponta_a_ponta` (2 rodadas fechadas, +10 cada) com margem de futuro
    ligada: cada fechamento tem de devolver a MARGEM que a abertura reteve,
    mais o pnl -- nunca `preco * quantidade` mais pnl, que sobraria ou
    faltaria caixa fantasma a cada trade (ver o comentario em `_on_closed`
    sobre `liberado` ter de usar a MESMA formula do debito)."""
    margem = 100.0
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),
        _bar("13:03", 9.90, 9.90, 9.79, 9.85),
        _bar("13:04", 9.85, 9.91, 9.85, 9.90),
        _bar("13:05", 9.90, 9.90, 9.90, 9.90),
    ]
    rt, _feed = _runtime(
        tmp_path, barras, symbol="WIN@", slot=SLOT_WIN,
        config=_config_futuro(margem), initial_capital=1_000.0,
        capacidade_negocio_mult=1.0, capacidade_fracao=0.10,
        # `shares_per_lot=1`: WIN@/WDO@ operam em CONTRATOS, nao em lotes de
        # 100 acoes (`LOTE_PADRAO_B3`, o default de `Gremah` -- ver
        # `scripts/daytrade/cripto_comum.py` pro mesmo ajuste em outro
        # instrumento nao-lote-de-100). "gremah" so' serve de dublê de
        # estrategia aqui; a granularidade certa e' o que importa.
        shares_per_lot=1,
    )
    rt.run_once(now=_agora("13:07:00"))

    s = rt.status()["daytrade"]
    # Nao trava o QUANTO (`shares_per_lot=1` muda a quantidade que `Gremah`
    # escolhe sozinha vs. o teste de acao que empresta este roteiro) -- so' a
    # PROPRIEDADE que interessa aqui: o roteiro so' tem rodadas vencedoras, e
    # a margem tem de voltar INTEIRA em cada uma, sobrando so' o pnl.
    liquido = s["ganhos_dia"] - s["perdas_dia"]
    assert liquido > 0
    assert s["posicoes_compra"] == 0  # so' a ordem #03 ficou POSICIONADA, sem preencher

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT_WIN.id)
    # a margem sempre volta inteira -- so' o pnl fica. O bug antigo deixaria
    # sobra/falta de caixa fantasma aqui (preco != margem a cada abre/fecha).
    assert acc.cash_sombra == pytest.approx(1_000.0 + liquido)


def test_retorno_usa_initial_capital_fixo_ignora_correcoes_manuais_de_caixa(tmp_path, pregao_aberto):
    """DECISÃO REVERTIDA no mesmo dia (2026-08-24): cheguei a somar toda
    correção manual de caixa (`live_events` "definido manualmente") como se
    fosse aporte, pra fugir de `initial_capital=0` virando "592% de
    retorno" numa conta real. O dono apontou o furo: ele também usa o campo
    "Caixa" pra CORRIGIR/realocar, não só pra aportar -- então cada
    correção sujaria o denominador. Sem como distinguir aporte de correção
    sem perguntar a intenção na hora (fora de escopo por ora), a base
    voltou a ser só `account.initial_capital`, declarado na criação da
    conta e nunca mais tocado -- mesmo que isso deixe uma conta antiga com
    `initial_capital` desatualizado sem correção automática."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),  # fecha #01 (+10)
        _bar("13:03", 9.90, 9.90, 9.90, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.initial_capital = 50.0
        store.save_account(conn, acc)
        # correção manual de R$100 no meio do caminho -- NÃO pode mudar o
        # denominador do retorno (é exatamente o cenário que motivou reverter).
        store.log_event(
            conn, acc.id, "info", "operacao",
            "caixa sombra do slot 'x' definido manualmente: 50.00 -> 150.00 (diferença R$ 100.00)",
            {"diferenca": 100.0, "slot": SLOT.id, "sombra": True},
        )

    rt.run_once(now=_agora("13:05:00"))
    s = rt.status()["daytrade"]

    assert s["aportes_totais"] == 50.0  # so' o initial_capital, a correcao de 100 foi ignorada
    assert s["retorno_acumulado_pct"] == 20.0  # 10 / 50 * 100


def test_eventos_gravados_antes_do_campo_sessao_existir_ainda_contam_no_dia(tmp_path):
    """ACHADO AO VIVO no dia do deploy (2026-08-24): o robô real vinha
    rodando desde a abertura com o código ANTERIOR a este -- sem `sessao`
    no payload e com a palavra "armada" (virou "posicionada" no mesmo
    deploy). Depois de reiniciar com o código novo, "Ganhos do dia" mostrou
    R$0,00 com um trade fechado 2 minutos antes: o evento de hoje, sem
    `sessao`, não batia com `hoje` e sumia da soma do dia (ainda contava no
    acumulado, que não filtra data -- por isso o sintoma era só no card do
    dia). `daytrade_exit_events`/`daytrade_order_events_on` têm de cair
    para `ts[:10]` quando `sessao` não existe, e reconhecer "armada" como
    o mesmo evento de "posicionada"."""
    with store.live_journal(tmp_path / "live.sqlite") as conn:
        cur = conn.execute(
            "INSERT INTO live_accounts (name, mode, initial_capital, cash, symbol) "
            "VALUES ('conta-antiga', 'mt5', 100.0, 100.0, 'PMAM3')"
        )
        acc_id = cur.lastrowid
        hoje = "2026-08-24"
        # ordem + saida gravadas pelo codigo ANTIGO: sem "sessao", "armada"
        conn.execute(
            "INSERT INTO live_events (account_id, ts, level, source, message, payload) "
            "VALUES (?, ?, 'info', 'daytrade', ?, ?)",
            (acc_id, f"{hoje} 10:00:00", "ordem #01 armada: long 100 PMAM3 @ 9.8000",
             '{"numero_ordem": 1, "side": "long", "quantity": 100, "limit_price": 9.8}'),
        )
        conn.execute(
            "INSERT INTO live_events (account_id, ts, level, source, message, payload) "
            "VALUES (?, ?, 'info', 'daytrade', ?, ?)",
            (acc_id, f"{hoje} 10:05:00", "SOMBRA saida #01 long 100 PMAM3 @ 9.9000 (target) R$ +10.00",
             '{"numero_ordem": 1, "side": "long", "pnl_brl": 10.0}'),
        )

        saidas = store.daytrade_exit_events(conn, acc_id)
        ordens = store.daytrade_order_events_on(conn, acc_id, hoje)

    assert saidas == [{"date": hoje, "round": 1, "side": "long", "pnl_brl": 10.0}]
    # so' a "armada" -- nao gravei uma "entrada"
    assert ordens == [{"side": "long", "kind": "armada", "quantity": 100, "price": 9.8,
                        "numero_ordem": 1}]

    r = IntradayLiveRuntime._resultado_dia_e_acumulado(saidas, hoje, 100.0)
    assert r["ganhos_dia"] == 10.0  # nao pode sumir so' por faltar "sessao"


def test_saida_sem_numero_de_rodada_ainda_conta_no_ganho(tmp_path):
    """REGRESSAO achada ao vivo (2026-08-24, poucos minutos depois do
    deploy): a numeração de rodada (`numero_ordem`) é MAIS NOVA que o
    próprio `pnl_brl` no payload -- todo trade fechado ANTES da numeração
    existir tem `pnl_brl` mas NÃO tem `numero_ordem`. A versão anterior de
    `daytrade_exit_events` exigia os dois campos presentes, então esses
    trades desapareciam de "Ganhos do dia" (e do acumulado) inteiro --
    `policy_state["intraday"]["shadow_pnl_brl"]` (a soma de verdade, nunca
    lida do log) mostrava R$5,92 no dia; o painel mostrava R$1,97, só os 2
    trades fechados DEPOIS da numeração existir. `round` tem que cair para
    um valor SINTÉTICO (não pode ser `None` nem um número fixo -- duas
    linhas assim juntas por engano contariam como fatias da MESMA rodada)."""
    with store.live_journal(tmp_path / "live.sqlite") as conn:
        cur = conn.execute(
            "INSERT INTO live_accounts (name, mode, initial_capital, cash, symbol) "
            "VALUES ('conta-sem-numero', 'mt5', 100.0, 100.0, 'PMAM3')"
        )
        acc_id = cur.lastrowid
        hoje = "2026-08-24"
        # 3 saidas SEM numero_ordem (pre-deploy da numeracao), sem side --
        # so' `exit_reason`/`pnl_brl`/etc, exatamente como o robo real gravou.
        for i, pnl in enumerate((1.985, 0.9845, 0.9845)):
            conn.execute(
                "INSERT INTO live_events (account_id, ts, level, source, message, payload) "
                "VALUES (?, ?, 'info', 'daytrade', 'SOMBRA: saida long 100 PMAM3 (target)', ?)",
                (acc_id, f"{hoje} 1{i}:00:00",
                 f'{{"exit_reason": "target", "pnl_brl": {pnl}, "execution_mode": "shadow"}}'),
            )
        saidas = store.daytrade_exit_events(conn, acc_id)

    assert len(saidas) == 3
    assert all(s["date"] == hoje for s in saidas)
    assert len({s["round"] for s in saidas}) == 3  # 3 rodadas DISTINTAS, nunca fundidas

    r = IntradayLiveRuntime._resultado_dia_e_acumulado(saidas, hoje, 100.0)
    assert r["ganhos_dia"] == pytest.approx(3.95, abs=0.01)  # 1.985 + 0.9845*2


# ---------- barra atrasada do pregao anterior (2026-08-25) ------------------

class _FeedComBarraAtrasadaDeOntem:
    """Reproduz o terminal MT5 em 2026-08-25 no slot `dt-gremah-pmam3-shadow`:
    quando o robo subiu, a ultima barra fechada era `ontem 19:53`; na consulta
    SEGUINTE apareceu tambem `ontem 19:54` -- a barra do corte de flatten da
    B3, atrasada, entregue junto com as primeiras de hoje (o feed so' sabe
    filtrar por `ts > after_ts`, e essa marca atravessa a virada do pregao).

    Sem semente (`session_bars_until` vazio) para forcar o comeco A FRIO, que
    e' o caso real: o robo ligou antes da abertura."""

    name = "fake_bars_atrasada"

    def __init__(self, ontem_visivel: Bar, ontem_atrasada: Bar, hoje: list[Bar]):
        self._ontem_visivel = ontem_visivel
        self._ontem_atrasada = ontem_atrasada
        self._hoje = list(hoje)
        self.consultas = 0

    @property
    def offset_hours(self):
        return 3.0

    def closed_bars_since(self, after_ts=None):
        self.consultas += 1
        disponiveis = [self._ontem_visivel]
        if self.consultas > 1:
            disponiveis = [self._ontem_visivel, self._ontem_atrasada, *self._hoje]
        if after_ts is None:
            return list(disponiveis)
        return [b for b in disponiveis if b.ts > after_ts]

    def session_bars_until(self, session, until_ts):
        return []


def _bar_de_ontem(hhmm: str, preco: float) -> Bar:
    return Bar(ts=pd.Timestamp(f"2026-08-20 {hhmm}", tz="UTC"),
               open=preco, high=preco, low=preco, close=preco, volume=1_000.0)


def test_barra_atrasada_de_ontem_nao_achata_o_pregao_de_hoje(tmp_path, pregao_aberto):
    """BUG DE PRODUCAO 2026-08-25 (`dt-gremah-pmam3-shadow`, PMAM3): a barra
    `2026-08-24 19:54` chegou como PRIMEIRA barra do dia. O corte de flatten
    compara so' a HORA, e 19:54 e' exatamente o corte da B3 naquele dia --
    `flattened=True` as 13:01, robo mudo nas 322 barras seguintes, ZERO ordem
    no pregao inteiro e nenhum erro no diario. O robo do slot vizinho
    (`gremah_tick`, mesmo ativo, mesmo modo) operou 7 vezes no mesmo dia: nao
    era restricao de "um ativo por robo", era esta barra."""
    # ROTEIRO COMPRIMIDO em 2026-09-08: as barras andam de 20 em 20s (nao
    # de minuto em minuto) e `now` fica logo depois da ultima. Motivo:
    # desde `MAX_ATRASO_PARA_ORDEM_SEGUNDOS`, barra mais velha que o teto
    # nao gera ORDEM NOVA -- e um roteiro de 6 minutos consumido num
    # `run_once` so' deixava a barra de abertura com 5+ min de idade. O
    # que este teste mede (sequencia de OHLC, numeracao, P&L) nao depende
    # do espacamento; a idade agora depende.
    hoje = [
        _bar("13:00:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:00:20", 10.00, 10.00, 9.79, 9.85),   # toca o nivel long (9.80)
        _bar("13:00:40", 9.85, 9.91, 9.85, 9.90),     # toca o alvo (9.90)
    ]
    feed = _FeedComBarraAtrasadaDeOntem(
        ontem_visivel=_bar_de_ontem("19:53", 10.00),
        ontem_atrasada=_bar_de_ontem("19:54", 10.00),   # o corte da B3 em 20/08
        hoje=hoje,
    )
    rt, _f = _runtime(tmp_path, hoje, feed=feed)

    passos = rt.run_once(now=_agora("13:00:45"))

    passo = [p for p in passos if p.action == "daytrade"][0]
    assert passo.detail["descartadas"] == 1
    assert rt.machine.flattened is False          # o pregao NAO foi achatado
    assert passo.detail["entradas"] == 1          # e o robo operou de verdade
    assert passo.detail["saidas"] == 1
    # a marca AVANCA sobre a barra descartada -- senao ela voltaria em todo
    # passo, para sempre
    assert rt._snapshot.last_bar_ts == hoje[-1].ts

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [dict(r) for r in conn.execute(
            "SELECT message FROM live_events WHERE account_id = ? ORDER BY id", (acc.id,)
        )]
    assert any("pregao anterior descartada" in e["message"] for e in eventos)
    assert any("LIMITE LONG #01" in e["message"] for e in eventos)


# ---------- recusa da corretora no envio da entrada (2026-08-25) ------------

class _BrokerQueRecusa(_FakeMT5Broker):
    """Recusa as `recusas` primeiras ordens-limite e aceita da'i em diante --
    e' o terminal com o AutoTrading desligado sendo ligado no meio do pregao,
    que foi o caso real de 25/08/2026."""

    def __init__(self, recusas: int = 1):
        super().__init__()
        self.recusas = recusas
        self.recusadas: list = []

    def place_pending(self, order, position_ticket=None):
        if self.recusas > 0:
            self.recusas -= 1
            order.status = OrderStatus.REJECTED
            order.note = ("MT5 recusou a ordem-limite pendente (retcode=10027): "
                          "AutoTrading disabled by client")
            self.recusadas.append(order)
            return order
        return super().place_pending(order, position_ticket=position_ticket)


def test_ordem_recusada_nao_deixa_ordem_fantasma_vigiada(tmp_path, pregao_aberto):
    """BUG DE PRODUCAO 2026-08-25 (`dt-gremah_tick-pmam3-live`): a corretora
    recusou a primeira ordem do dia (`AutoTrading disabled by client`) e a
    excecao subiu ate o supervisor. Duas consequencias, as duas erradas:

      1. a transacao do diario voltou atras -- a recusa nao aparecia no
         historico da tela, so' no log do processo;
      2. `machine.resting_limit` ja estava gravado ANTES do envio, entao o
         robo passou de 13:02 as 14:00 vigiando um fill impossivel, e a
         ordem seguinte entrou no diario como "(substitui)" de uma ordem que
         nunca existiu no book.
    """
    broker = _BrokerQueRecusa(recusas=1)
    rt, feed = _runtime_live(
        tmp_path, [_bar("13:05", 10.00, 10.00, 10.00, 10.00)], broker,
        # ancora rolante desde o inicio (sem warm start, ver
        # `_needs_warm_start`) e re-arme a cada barra: e' o que faz a barra
        # seguinte tentar de novo dentro do mesmo teste
        fixed_anchor_until=time(13, 0), rolling_reanchor_after_bars=1,
    )

    rt.run_once(now=_agora("13:05:30"))            # comeco a frio: so' marca
    feed._barras.append(_bar("13:06", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:06:30"))            # arma -> RECUSADA
    assert len(broker.recusadas) == 1
    assert rt.machine.resting_limit is None        # nada de ordem fantasma
    assert rt._snapshot.pending_entry_refs == []

    # o robo re-arma pelo criterio DELE (a recusa nao o avisa de nada, ver
    # `_recusa_de_envio`): com `rolling_reanchor_after_bars=1`, uma barra
    # esperando e a seguinte declara a ordem obsoleta
    feed._barras.append(_bar("13:07", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:07:30"))
    feed._barras.append(_bar("13:08", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:08:30"))            # arma de novo -> aceita
    assert len(broker.pendentes_enviadas) == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [(r["level"], r["message"]) for r in conn.execute(
            "SELECT level, message FROM live_events WHERE account_id = ? ORDER BY id",
            (acc.id,))]

    recusas = [(lvl, m) for lvl, m in eventos if "RECUSADA" in m]
    assert len(recusas) == 1                       # sobreviveu ao passo (nao houve rollback)
    assert recusas[0][0] == "error"
    assert "AutoTrading disabled by client" in recusas[0][1]  # o motivo da corretora
    # a ordem seguinte e' rodada NOVA, nao "substitui" a que nunca existiu
    postas = [m for _lvl, m in eventos if m.startswith("LIMITE ")]
    assert len(postas) == 2
    assert "substitui" not in postas[1]
    assert "#02" in postas[1]


def test_recusa_da_ordem_do_warm_start_tambem_nao_deixa_fantasma(tmp_path, pregao_aberto):
    """Mesmo buraco no OUTRO ponto de envio: a ordem que `warm_start_
    calibration` planta direto em `resting_limit` (robo ligado no meio do
    pregao). Ela nao tem numero de rodada -- o diario a chama pelo nome."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 10.00, 10.00),
    ]
    broker = _BrokerQueRecusa(recusas=99)          # recusa tudo
    rt, _feed = _runtime_live(tmp_path, barras, broker, semente=barras[:1])

    rt.run_once(now=_agora("13:02:00"))            # nao levanta

    assert rt.machine.resting_limit is None
    assert rt._snapshot.pending_entry_refs == []
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [r["message"] for r in conn.execute(
            "SELECT message FROM live_events WHERE account_id = ? ORDER BY id", (acc.id,))]
    assert any("RECUSADA warm start" in m for m in eventos)


# ---------- botao AutoTrading do terminal (2026-08-25) ---------------------

class _BrokerComAutoTrading(_FakeMT5Broker):
    """Dublê que sabe responder pelo botao AutoTrading do terminal, como o
    `MT5Broker` real. `ligado` e' escrito pelo teste."""

    def __init__(self, ligado: bool):
        super().__init__()
        self.ligado = ligado
        self.leituras = 0

    def autotrading_allowed(self):
        self.leituras += 1
        return self.ligado


def test_autotrading_desligado_recusa_o_pregao_em_vez_de_perder_a_ordem(
    tmp_path, pregao_aberto,
):
    """25/08/2026: o terminal subiu com o AutoTrading desligado e a primeira
    ordem do dia morreu com `retcode=10027`. O painel continuou verde,
    "OPERANDO" -- a unica pista era um `[erro]` no log do processo. Agora o
    pregao e' recusado com o motivo no diario, ANTES de tentar operar."""
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00),
              _bar("13:01", 10.00, 10.00, 9.79, 9.85)]
    broker = _BrokerComAutoTrading(ligado=False)
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    passos = rt.run_once(now=_agora("13:02:00"))

    assert [p.action for p in passos] == ["daytrade_skip"]
    assert passos[0].detail["motivo"] == "autotrading desligado"
    assert broker.pendentes_enviadas == []          # nada foi tentado
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [(r["level"], r["message"]) for r in conn.execute(
            "SELECT level, message FROM live_events WHERE account_id = ? ORDER BY id",
            (acc.id,))]
    alarmes = [(lvl, m) for lvl, m in eventos if "AutoTrading" in m]
    assert len(alarmes) == 1                        # uma vez, nao a cada passo
    assert alarmes[0][0] == "error"

    # segundo passo com o botao ainda desligado: continua barrado e NAO
    # repete o alarme no diario
    rt.run_once(now=_agora("13:02:05"))
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        assert len([r for r in conn.execute(
            "SELECT message FROM live_events WHERE account_id = ?", (acc.id,))
            if "AutoTrading" in r["message"]]) == 1


def test_ligar_o_autotrading_no_meio_do_pregao_libera_a_operacao(tmp_path, pregao_aberto):
    """Foi o que o dono fez naquele dia (~14h): ligou o botao com o processo
    ja rodando. Nao pode exigir reinicio -- o pregao segue do ponto em que
    esta."""
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    broker = _BrokerComAutoTrading(ligado=False)
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    assert [p.action for p in rt.run_once(now=_agora("13:01:00"))] == ["daytrade_skip"]

    broker.ligado = True
    passos = rt.run_once(now=_agora("13:01:30"))

    assert "daytrade_skip" not in [p.action for p in passos]
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [r["message"] for r in conn.execute(
            "SELECT message FROM live_events WHERE account_id = ? ORDER BY id", (acc.id,))]
    assert any("AutoTrading do terminal LIGADO" in m for m in eventos)

    # depois de passar, para de conferir (o custo de errar aqui e' o COMECO do
    # pregao; mudanca depois disso aparece na recusa da propria corretora)
    leituras = broker.leituras
    rt.run_once(now=_agora("13:02:00"))
    assert broker.leituras == leituras


def test_sombra_nao_depende_do_botao_autotrading(tmp_path, pregao_aberto):
    """Sombra nao manda ordem nenhuma para a corretora, entao o botao do
    terminal nao muda nada para ela -- barrar aqui seria inventar um
    impedimento que nao existe."""
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00),
              _bar("13:01", 10.00, 10.00, 9.79, 9.85),
              _bar("13:02", 9.85, 9.91, 9.85, 9.90)]
    rt, _feed = _runtime(tmp_path, barras)          # execution_mode="shadow"

    passos = rt.run_once(now=_agora("13:05:00"))

    passo = [p for p in passos if p.action == "daytrade"][0]
    assert passo.detail["entradas"] == 1


# ---------- impedimento visivel no painel (2026-08-25) ---------------------

def test_pregao_recusado_grava_impedimento_e_o_painel_o_enxerga(tmp_path, pregao_aberto):
    """O painel monta um runtime de LEITURA e `status()` tem proibicao de
    disparar I/O na corretora (ver `live_service._build_intraday_runtime`) --
    entao a unica forma de ele saber que o robo NAO esta operando e' o
    processo do robo gravar o motivo na conta. Sem isto o cartao ficava verde
    escrito "operando" com o robo barrado o pregao inteiro."""
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00),
              _bar("13:01", 10.00, 10.00, 9.79, 9.85)]
    broker = _BrokerComAutoTrading(ligado=False)
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    rt.run_once(now=_agora("13:02:00"))
    assert rt.status()["daytrade"]["impedimento"] == "AutoTrading do terminal desligado"

    # ligou o botao: o impedimento cai no MESMO pregao, nao no proximo
    broker.ligado = True
    rt.run_once(now=_agora("13:02:30"))
    assert rt.status()["daytrade"]["impedimento"] is None


def test_impedimento_de_outro_pregao_nao_pinta_o_dia_de_hoje(tmp_path, pregao_aberto):
    """Impedimento gravado e nunca resolvido (processo morto antes) nao pode
    sobreviver a virada do pregao: o dia seguinte comeca limpo."""
    rt, _feed = _runtime_live(tmp_path, [_bar("13:00", 10.0, 10.0, 10.0, 10.0)],
                              _BrokerComAutoTrading(ligado=False))
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        rt._gravar_impedimento(conn, acc, "caixa abaixo do mínimo do dia",
                               date(2026, 8, 20))
        acc_recarregada = store.load_account(conn, SLOT.id)

    assert rt._impedimento_de_hoje(acc_recarregada, date(2026, 8, 20)) is not None
    assert rt._impedimento_de_hoje(acc_recarregada, SESSION) is None


def test_impedimento_nao_reescreve_a_conta_a_cada_passo(tmp_path, pregao_aberto, monkeypatch):
    """O supervisor passa aqui a cada 5s. Reescrever a mesma linha o pregao
    inteiro so' castiga o disco -- so' grava quando MUDA."""
    rt, _feed = _runtime_live(tmp_path, [_bar("13:00", 10.0, 10.0, 10.0, 10.0)],
                              _BrokerComAutoTrading(ligado=False))
    gravacoes = []
    original = itr_mod.store.save_account
    monkeypatch.setattr(itr_mod.store, "save_account",
                        lambda conn, acc: (gravacoes.append(acc.name), original(conn, acc))[1])

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        rt._gravar_impedimento(conn, acc, "motivo qualquer", SESSION)
        assert len(gravacoes) == 1
        rt._gravar_impedimento(conn, acc, "motivo qualquer", SESSION)   # igual: no-op
        assert len(gravacoes) == 1
        rt._gravar_impedimento(conn, acc, None, SESSION)                # mudou: grava
        assert len(gravacoes) == 2


# ---------- formato da linha do diario (2026-08-25) ------------------------
def test_lotes_txt_usa_o_lote_do_papel_e_nao_arredonda_fracionario(tmp_path, pregao_aberto):
    """A linha do diario fala em LOTES, nao em acoes (pedido do dono,
    2026-08-25: "tirar o 100 e tratar como lotes").

    O lote e' do PAPEL (`config.default_quantity`), nao um 100 fixo: acao da
    B3 tem lote de 100, futuro tem lote de 1 contrato, e os dois passam por
    aqui. Quantidade que nao fecha lote inteiro (fracionario) volta em acoes
    -- arredondar para "1 lote" mentiria sobre o tamanho da ordem, que e'
    exatamente o numero que o dono confere contra a corretora."""
    rt, _feed = _runtime(tmp_path, [_bar("13:00", 10.00, 10.00, 10.00, 10.00)])

    rt.config = replace(rt.config, default_quantity=100)   # acao da B3
    assert rt._lotes_txt(100) == "1 lote"
    assert rt._lotes_txt(300) == "3 lotes"
    assert rt._lotes_txt(37) == "37 ações"                 # fracionario
    assert rt._lotes_txt(1) == "1 ação"

    rt.config = replace(rt.config, default_quantity=1)     # futuro: 1 contrato
    assert rt._lotes_txt(1) == "1 lote"
    assert rt._lotes_txt(3) == "3 lotes"


def test_card_de_ordens_nao_depende_do_texto_da_mensagem(tmp_path, pregao_aberto):
    """O card "Ordens posicionadas" classifica pelo `tipo` do PAYLOAD.

    Ate' 2026-08-25 ele classificava procurando "posicionada"/"entrada"/
    "cancelada" DENTRO da frase que a tela mostra. O dono pediu o texto
    reescrito no mesmo dia (evento na frente, sem "SOMBRA", em lotes) -- e um
    filtro amarrado ao texto quebraria em silencio: sem teste vermelho, o card
    so' ficaria vazio no painel. Este teste fixa a fronteira: as mensagens de
    verdade NAO contem mais nenhuma das palavras antigas, e mesmo assim o card
    conta as ordens."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),   # preenche a entrada long
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),     # alvo: fecha a rodada
        _bar("13:03", 9.90, 10.21, 9.90, 10.15),   # arma a proxima (short)
    ]
    rt, _feed = _runtime(tmp_path, barras)
    rt.run_once(now=_agora("13:04:00"))

    hoje = rt._snapshot.session.isoformat()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        mensagens = [r["message"] for r in conn.execute(
            "SELECT message FROM live_events WHERE account_id = ? AND source = 'daytrade'",
            (acc.id,))]
        ordens = store.daytrade_order_events_on(conn, acc.id, hoje)

    # o vocabulario velho sumiu do texto -- inclusive "SOMBRA", que o dono
    # mandou tirar por ser fixo do slot (ja aparece na etiqueta do cartao)
    assert mensagens, "o roteiro tem de gravar evento de day trade"
    # (a linha de resumo da sessao -- "warm start, 1 barra(s), ordem
    # posicionada" -- nao e' evento de ORDEM: nao tem `side` no payload e o
    # card nunca a leu. Por isso as agulhas sao as do formato ANTIGO de ordem,
    # com os dois-pontos, nao a palavra solta.)
    for antiga in ("posicionada:", "armada:", "SOMBRA", "entrada #", "saida #"):
        assert not any(antiga in m for m in mensagens), (antiga, mensagens)

    # ...e o card continua classificando, agora pelo payload
    assert ordens, mensagens
    assert {o["kind"] for o in ordens} <= {"armada", "preenchida", "cancelada"}
    assert any(o["kind"] == "armada" for o in ordens), ordens
    assert any(o["kind"] == "preenchida" for o in ordens), ordens


# ---------- ticket orfao: cancelamento nao confirmado (2026-08-26) ---------

class _BrokerQueNaoCancela(_FakeMT5Broker):
    """`cancel` FALHA em silencio, como o MT5 de verdade falha.

    `MT5Broker.cancel` nao levanta em nenhum dos seus caminhos de erro
    (pacote ausente, `connect()` falso, excecao no `order_send`, retcode
    que nao e' `DONE`): devolve a `Order` com o motivo na nota e o status
    INTOCADO. Este duble reproduz exatamente isso -- e' o terminal fechado
    ou a conexao caindo entre o envio e o cancelamento."""

    def cancel(self, order):
        order.note = "falha ao conectar para cancelar (last_error=-10004)"
        self.canceladas.append(order)
        return order                                   # status segue SENT


def test_rollback_frustrado_devolve_o_ticket_que_pode_seguir_vivo(tmp_path):
    """`place_limit` promete que nada fica posicionado pela metade, mas quem
    cumpre a promessa e' a CORRETORA -- e ela pode nao cumprir.

    Se a 2a fatia e' recusada, a 1a ja esta no book e o cancelamento dela
    falha, existe uma ordem-limite VIVA que ninguem pediu. Antes de
    2026-08-26 o retorno de `cancel` era descartado: o ticket sumia do
    processo, nao entrava no diario e nao ficava em `pending_entry_refs`.
    So' o terminal do MT5 sabia."""
    from live.intraday_execution import BrokerExecutionError, MT5IntradayExecution

    broker = _BrokerQueNaoCancela()
    execucao = MT5IntradayExecution(broker=broker, symbol=SYMBOL)

    # a 1a fatia entra (ticket 1001), a 2a e' recusada -> rollback da 1a
    original = broker.place_pending

    def place_pending(order):
        if len(broker.pendentes_enviadas) >= 1:
            order.status = OrderStatus.REJECTED
            order.note = "AutoTrading disabled by client"
            return order
        return original(order)

    broker.place_pending = place_pending

    with pytest.raises(BrokerExecutionError) as exc:
        execucao.place_limit(side="long", limit_price=9.80,
                             quantities=[100, 100], ts=pd.Timestamp("2026-08-26 13:00"))

    # o ticket da fatia que ficou no book VOLTA para quem chamou
    assert exc.value.orphan_refs == ["1001"], exc.value.orphan_refs
    # ...e a linha do diario avisa (rollback frustrado E' noticia)
    assert "pode seguir vivo" in str(exc.value)
    assert "1001" in str(exc.value)


def test_rollback_que_deu_certo_nao_polui_a_linha_do_diario(tmp_path):
    """Contraparte do teste acima: rollback que funcionou nao vira texto.

    O dono pediu linha curta (2026-08-25) e o rollback bem-sucedido e' o
    caso NORMAL -- caso normal nao e' noticia. So' a falha entra."""
    from live.intraday_execution import BrokerExecutionError, MT5IntradayExecution

    broker = _FakeMT5Broker()                          # `cancel` marca CANCELLED
    execucao = MT5IntradayExecution(broker=broker, symbol=SYMBOL)
    original = broker.place_pending

    def place_pending(order):
        if len(broker.pendentes_enviadas) >= 1:
            order.status = OrderStatus.REJECTED
            order.note = "AutoTrading disabled by client"
            return order
        return original(order)

    broker.place_pending = place_pending

    with pytest.raises(BrokerExecutionError) as exc:
        execucao.place_limit(side="long", limit_price=9.80,
                             quantities=[100, 100], ts=pd.Timestamp("2026-08-26 13:00"))

    assert exc.value.orphan_refs == []
    assert "pode seguir vivo" not in str(exc.value)
    assert str(exc.value).endswith("AutoTrading disabled by client")


def test_ordem_substituida_que_nao_cancelou_continua_vigiada(tmp_path, pregao_aberto):
    """Substituir a ordem cancela a anterior -- se o cancelamento NAO for
    confirmado, o ticket antigo nao pode ser esquecido.

    Este e' o caminho mais perigoso porque e' ROTINEIRO, nao excepcional:
    toda vez que a ancora rola, a ordem anterior e' substituida. O codigo
    descartava o retorno de `cancel_limit` e logo em seguida SOBRESCREVIA
    `pending_entry_refs` com o ticket novo -- duas ordens vivas no book e o
    robo lembrando de uma so'. `pending_entry_refs` e' persistida e e' o que
    faz a proxima `EnterLimit` tentar cancelar de novo, alem de segurar o
    botao de parar em `dashboard/live_control.py`."""
    broker = _BrokerQueNaoCancela()
    rt, feed = _runtime_live(
        tmp_path, [_bar("13:05", 10.00, 10.00, 10.00, 10.00)], broker,
        fixed_anchor_until=time(13, 0), rolling_reanchor_after_bars=1,
    )

    rt.run_once(now=_agora("13:05:30"))
    feed._barras.append(_bar("13:06", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:06:30"))            # arma a 1a (ticket 1001)
    assert rt._snapshot.pending_entry_refs == ["1001"]

    feed._barras.append(_bar("13:07", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:07:30"))
    feed._barras.append(_bar("13:08", 10.10, 10.30, 10.10, 10.25))
    rt.run_once(now=_agora("13:08:30"))            # re-ancora: substitui

    assert len(broker.canceladas) >= 1, "deveria ter tentado cancelar a anterior"
    # o ticket velho (cancelamento nao confirmado) segue na vigilancia, JUNTO
    # com o novo -- nao no lugar dele
    assert "1001" in rt._snapshot.pending_entry_refs, rt._snapshot.pending_entry_refs
    assert len(rt._snapshot.pending_entry_refs) >= 2, rt._snapshot.pending_entry_refs

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [(r["level"], r["message"]) for r in conn.execute(
            "SELECT level, message FROM live_events WHERE account_id = ? ORDER BY id",
            (acc.id,))]

    orfas = [(lvl, m) for lvl, m in eventos if m.startswith("ORFA ")]
    assert orfas, [m for _l, m in eventos]
    assert orfas[0][0] == "warn"
    assert "1001" in orfas[0][1]


def test_status_nao_conta_ancora_rolante_como_ordem_nova(tmp_path, pregao_aberto):
    """Ponta a ponta do bug relatado pelo dono em 27/08/2026: no painel
    real, o diario mostrava so' a rodada #02 (a #01 nunca preencheu e foi
    reancorada) e o card "Ordens" contava 4, somando o nocional de tres
    precos ja abandonados pela propria reancoragem. Mesmo roteiro de
    `test_ordem_substituida_que_nao_cancelou_continua_vigiada` (ancora rola
    a cada barra), mas lendo `status()` -- o caminho de VERDADE que
    `daytrade_order_events_on` alimenta -- em vez de inspecionar a maquina."""
    # Barras planas mas com o FECHAMENTO subindo a cada uma (10.00 -> 10.05
    # -> 10.10): a ancora rola pra um nivel NOVO a cada barra (a guarda de
    # "mesmo nivel" -- `_reancoragem_no_mesmo_nivel`, commit 672bd5e -- so'
    # suprime o rearme quando o nivel recalculado da' EXATAMENTE no mesmo
    # lugar, o que barras totalmente planas produziriam). Nenhuma barra toca
    # o proprio nivel (sempre ~2% abaixo do fechamento dela), entao nunca
    # preenche -- so' reancora.
    broker = _FakeMT5Broker()
    rt, feed = _runtime_live(
        tmp_path, [_bar("13:05", 10.00, 10.00, 10.00, 10.00)], broker,
        fixed_anchor_until=time(13, 0), rolling_reanchor_after_bars=1,
    )

    rt.run_once(now=_agora("13:05:30"))            # comeco a frio: so' marca
    feed._barras.append(_bar("13:06", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:06:30"))            # arma #01 @ ~9.80
    feed._barras.append(_bar("13:07", 10.05, 10.05, 10.05, 10.05))
    rt.run_once(now=_agora("13:07:30"))            # ainda esperando o rearme
    feed._barras.append(_bar("13:08", 10.10, 10.10, 10.10, 10.10))
    rt.run_once(now=_agora("13:08:30"))            # reancora #01 @ ~9.90 (substitui)
    feed._barras.append(_bar("13:09", 10.20, 10.20, 10.20, 10.20))
    rt.run_once(now=_agora("13:09:30"))            # ainda esperando o rearme
    feed._barras.append(_bar("13:10", 10.30, 10.30, 10.30, 10.30))
    rt.run_once(now=_agora("13:10:30"))            # reancora #01 de novo (substitui)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [r["message"] for r in conn.execute(
            "SELECT message FROM live_events WHERE account_id = ? ORDER BY id",
            (acc.id,))]
    postas = [m for m in eventos if m.startswith("LIMITE ")]
    assert len(postas) == 3, postas          # armou 1a vez + reancorou 2x
    assert all("#01" in m for m in postas)   # nunca virou #02: mesma rodada

    s = rt.status()["daytrade"]
    ordem = s["ordem_em_pe"]
    assert ordem is not None
    lado = ordem["lado"]
    contagem_chave = "ordens_compra" if lado == "long" else "ordens_venda"
    valor_chave = "valor_ordens_compra" if lado == "long" else "valor_ordens_venda"

    assert s[contagem_chave] == 1, "reancoragem da mesma rodada nao e' ordem nova"
    # nocional so' da ULTIMA reancoragem (a que ainda esta' em pe), nunca a
    # soma dos tres precos que a propria rodada ja abandonou.
    assert s[valor_chave] == pytest.approx(ordem["quantidade"] * ordem["preco"])


def test_fatia_de_saida_que_nao_cancelou_nao_e_esquecida(tmp_path):
    """A limite de SAIDA que a corretora nao confirmou cancelada segue
    vigiada -- e o robo tenta de novo.

    Nos 4 sites de `machine.py` a fatia-limite de saida e' cancelada e a
    posicao e' fechada A MERCADO no mesmo passo. Um cancelamento que falha
    em silencio deixa as DUAS ordens vivas pela mesma posicao (e' o que o
    comentario de `machine.py:898` diz querer evitar), e numa conta NETTING
    a limite orfa preenchendo DEPOIS do flatten INVERTE a posicao: um lado
    aberto que ninguem pediu, sem stop, sem alvo e sem logica de saida.

    Antes de 2026-08-26 `cancel_exit_limit` descartava o retorno de
    `cancel`, entao esse ticket sumia do processo sem deixar rastro."""
    from live.intraday_execution import MT5IntradayExecution

    broker = _BrokerQueNaoCancela()
    execucao = MT5IntradayExecution(broker=broker, symbol=SYMBOL)
    ts = pd.Timestamp("2026-08-26 13:00")

    execucao.place_exit_limit(position_side="long", quantity=100,
                              limit_price=10.20, current_position_qty=100,
                              ts=ts)
    ticket = execucao.pending_exit_order.broker_ref

    execucao.cancel_exit_limit(ts, reason="flatten")

    # o ticket que pode seguir vivo no book fica registrado
    assert execucao.exit_orphan_refs == [ticket], execucao.exit_orphan_refs

    # ...e quando a corretora confirma, ele sai da lista
    broker_ok = _FakeMT5Broker()
    execucao2 = MT5IntradayExecution(broker=broker_ok, symbol=SYMBOL)
    execucao2.place_exit_limit(position_side="long", quantity=100,
                               limit_price=10.20, current_position_qty=100,
                               ts=ts)
    execucao2.cancel_exit_limit(ts, reason="flatten")
    assert execucao2.exit_orphan_refs == []


# ---------- gap 1.15 (2026-09-03): ticket na fatia PENDENTE de saida -------
#
# A correcao do campo `position` depois do incidente MG51 (item 1.1) so'
# cobriu fechamento a MERCADO (`exit_market`/`close_position`). A fatia de
# SAIDA por alvo (`place_exit_limit`, usada por `gremah`/`gremah_tick` sempre
# que `dividir_entrada=True`, o default) nunca levava o ticket -- estes
# testes provam que agora leva, e que a ausencia de ticket (consulta falhou,
# posicao sumiu, lado divergente) nunca bloqueia o envio, so' devolve ao
# comportamento de ANTES do gap existir.

def test_place_exit_limit_leva_o_ticket_da_posicao_real(tmp_path):
    """A fatia de SAIDA por alvo agora identifica qual posicao esta
    fechando -- a mesma amarracao que o fechamento a MERCADO ja tinha desde
    o item 1.1, fechada aqui do lado da ordem-limite PENDENTE."""
    from live.intraday_execution import MT5IntradayExecution

    broker = _FakeMT5Broker()
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 100,
                      "ticket": 4242, "sl": 0.0, "tp": 0.0}
    execucao = MT5IntradayExecution(broker=broker, symbol=SYMBOL)
    ts = pd.Timestamp("2026-09-03 13:00")

    execucao.place_exit_limit(position_side="long", quantity=100,
                              limit_price=10.20, current_position_qty=100, ts=ts)

    assert broker.pending_position_tickets == [4242]


def test_place_limit_de_entrada_nunca_leva_ticket_de_posicao(tmp_path):
    """A ordem-limite de ENTRADA nao fecha nada -- so' a fatia de SAIDA
    (`place_exit_limit`) leva `position_ticket`. Guarda de regressao: o gap
    1.15 nao pode vazar o campo para o caminho de abertura."""
    from live.intraday_execution import MT5IntradayExecution

    broker = _FakeMT5Broker()
    execucao = MT5IntradayExecution(broker=broker, symbol=SYMBOL)

    execucao.place_limit(side="long", limit_price=9.80, quantities=[100],
                         ts=pd.Timestamp("2026-09-03 13:00"))

    assert broker.pending_position_tickets == [None]


def test_place_exit_limit_sem_conseguir_ler_posicao_segue_sem_ticket(tmp_path):
    """Consulta de posicao que falha (terminal fora do ar, etc.) NUNCA pode
    bloquear o envio da ordem de fechamento -- so' devolve o metodo ao
    comportamento de ANTES do gap 1.15 existir: sem `"position"` no
    request. Quem decide se a divergencia e' grave e' `exit_fill`/
    `_read_position` (chamados por quem PRECISA de resposta confiavel),
    nunca este atalho de enriquecimento do request."""
    from live.intraday_execution import MT5IntradayExecution

    broker = _FakeMT5Broker()
    broker.leitura_falha = True
    execucao = MT5IntradayExecution(broker=broker, symbol=SYMBOL)
    ts = pd.Timestamp("2026-09-03 13:00")

    enviada = execucao.place_exit_limit(position_side="long", quantity=100,
                                        limit_price=10.20, current_position_qty=100, ts=ts)

    assert enviada.status == OrderStatus.SENT
    assert broker.pending_position_tickets == [None]


def test_place_exit_limit_com_lado_divergente_segue_sem_ticket(tmp_path):
    """A corretora reporta uma posicao SHORT enquanto a fatia de saida e' de
    uma posicao LONG (leitura atrasada/corrida) -- nao inventa um ticket que
    pode ser de OUTRA posicao. Segue sem `position_ticket`, o mesmo
    comportamento seguro de antes do gap 1.15."""
    from live.intraday_execution import MT5IntradayExecution

    broker = _FakeMT5Broker()
    broker.posicao = {"side": "short", "price": 10.00, "quantity": 100,
                      "ticket": 999, "sl": 0.0, "tp": 0.0}
    execucao = MT5IntradayExecution(broker=broker, symbol=SYMBOL)
    ts = pd.Timestamp("2026-09-03 13:00")

    execucao.place_exit_limit(position_side="long", quantity=100,
                              limit_price=10.20, current_position_qty=100, ts=ts)

    assert broker.pending_position_tickets == [None]


# ---------- atividade estranha: robo real vs. ordem manual (2026-08-27) ----
#
# Motivado pelo teste ao vivo do dono: comprou/vendeu PMAM3 a mercado direto
# no terminal, com o robo real (`dt-gremah_tick-pmam3-live`) rodando no mesmo
# papel, e o diario nunca registrou nada -- `open_position()`/
# `pending_orders()` filtram por magic de proposito (conta NETTING
# compartilhada entre slots), entao o robo ficava cego por completo. So'
# AVISA (nunca soma esse volume ao que o robo controla -- regra 6 do
# AGENTS.md, `live/` nunca inventa decisao propria).

def _diario_niveis_e_mensagens(rt):
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        return [(r["level"], r["message"]) for r in conn.execute(
            "SELECT level, message FROM live_events WHERE account_id = ? ORDER BY id",
            (acc.id,))]


def test_atividade_estranha_loga_alerta_uma_vez_so(tmp_path, pregao_aberto):
    """Detectada, ela e' avisada -- mas so' UMA VEZ, nao a cada passo
    enquanto persiste (senao spammaria o diario a cada poucos segundos)."""
    broker = _FakeMT5Broker()
    broker.atividade_estranha = {
        "symbol": "PMAM3",
        "itens": [{"tipo": "posicao", "magic": 0, "quantity": 100}],
    }
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, feed = _runtime_live(tmp_path, barras, broker)

    rt.run_once(now=_agora("13:01:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))

    avisos = [(lvl, m) for lvl, m in _diario_niveis_e_mensagens(rt)
              if "ATIVIDADE ESTRANHA" in m]
    assert len(avisos) == 1, avisos
    assert avisos[0][0] == "warn"


def test_atividade_estranha_nao_muda_a_posicao_que_o_robo_controla(tmp_path, pregao_aberto):
    """O alerta e' so' isso -- alerta. Nunca soma o volume estranho a
    `posicoes_compra`/`ordens_compra` nem a nada que o robo use pra decidir."""
    broker = _FakeMT5Broker()
    broker.atividade_estranha = {
        "symbol": "PMAM3",
        "itens": [{"tipo": "posicao", "magic": 0, "quantity": 100}],
    }
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, _feed = _runtime_live(tmp_path, barras, broker)

    rt.run_once(now=_agora("13:01:00"))

    s = rt.status()["daytrade"]
    assert s["posicoes_compra"] == 0
    assert s["posicoes_venda"] == 0
    assert s["atividade_estranha"] == broker.atividade_estranha


def test_atividade_estranha_loga_info_quando_some(tmp_path, pregao_aberto):
    """Some da corretora -> uma linha INFO avisando que acabou, tambem uma
    vez so' (nao fica alternando aviso/all-clear a cada passo)."""
    broker = _FakeMT5Broker()
    broker.atividade_estranha = {
        "symbol": "PMAM3",
        "itens": [{"tipo": "ordem", "magic": 0, "quantity": 100}],
    }
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, feed = _runtime_live(tmp_path, barras, broker)
    rt.run_once(now=_agora("13:01:00"))

    broker.atividade_estranha = None
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))

    eventos = _diario_niveis_e_mensagens(rt)
    infos = [(lvl, m) for lvl, m in eventos if "nao aparece mais" in m]
    assert len(infos) == 1, eventos
    assert infos[0][0] == "info"
    assert rt.status()["daytrade"]["atividade_estranha"] is None


def test_atividade_estranha_none_nao_loga_nada(tmp_path, pregao_aberto):
    """Caso comum (nada de estranho, sempre): nenhuma linha no diario."""
    broker = _FakeMT5Broker()
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00)]
    rt, feed = _runtime_live(tmp_path, barras, broker)

    rt.run_once(now=_agora("13:01:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))

    eventos = _diario_niveis_e_mensagens(rt)
    assert not any("ATIVIDADE ESTRANHA" in m or "nao aparece mais" in m
                   for _lvl, m in eventos)


# ---------- gap (c)/(g), incidente 2026-08-28: protecao SL/TP na corretora -
#
# A posicao real ficou com `sl=0.0, tp=0.0` na corretora por HORAS,
# atravessando 3 reinicios do processo -- o "stop" deste robo sempre foi
# logica do LOOP (dispara ordem a mercado quando o nivel rompe), nunca uma
# ordem-stop registrada. `_ensure_protecao` fecha isso.

def _abre_posicao_scriptada(tmp_path, broker, *, stop=9.00, target=11.00, quantity=1):
    """Monta um runtime `_ScriptedDaytrade` com UMA entrada (`initial_stop`/
    `initial_target` conhecidos) e a leva ate a posicao CONFIRMADA aberta --
    setup comum aos testes de protecao/freio duro/recusa de fechamento
    abaixo. Devolve `(rt, feed)` com a posicao ja aberta e vigiada."""
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=stop,
                       initial_target=target, quantity=quantity, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    broker.posicao = {"side": "long", "price": 10.00, "quantity": quantity, "ticket": 1,
                      "sl": 0.0, "tp": 0.0}
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.position is not None
    return rt, feed


def test_live_entrada_registra_protecao_sl_tp_na_corretora(tmp_path, pregao_aberto):
    """Assim que a posicao abre, o PROXIMO passo tem de registrar SL/TP na
    corretora -- os mesmos niveis que a maquina ja decidiu (`initial_stop`/
    `initial_target`), nunca um valor calculado por `live/`."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)

    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))

    assert broker.protecoes, "protecao tem de ser registrada com a posicao ja aberta"
    ticket, side, stop, target = broker.protecoes[-1]
    assert ticket == 1
    assert side == "long"
    assert stop == pytest.approx(9.00)
    assert target == pytest.approx(11.00)
    assert rt.status()["daytrade"]  # so' garante que status() nao quebra com protecao pendente


def test_live_protecao_nao_reenvia_quando_ja_esta_correta(tmp_path, pregao_aberto):
    """Depois de registrada e confirmada (a corretora agora REPORTA os
    niveis certos), o proximo passo NAO reenvia -- reenviar toda barra so'
    gastaria requisicao a toa."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)

    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))
    assert len(broker.protecoes) == 1

    broker.posicao = {**broker.posicao, "sl": 9.00, "tp": 11.00}
    feed._barras.append(_bar("13:04", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:04:00"))

    assert len(broker.protecoes) == 1, "ja estava certo -- nao reenviou"


def test_live_protecao_reenviada_apos_restart_quando_corretora_perdeu_sl_tp(
    tmp_path, pregao_aberto,
):
    """Gap (g): um PROCESSO NOVO (restart), com a corretora reportando
    `sl=0/tp=0` de novo (o cenario do incidente: protecao perdida por fora),
    reconcilia sozinho no PRIMEIRO passo -- sem precisar de nenhuma memoria
    do processo anterior, so' comparando o que a maquina quer contra o que a
    corretora tem agora."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))
    assert len(broker.protecoes) == 1

    # "reinicia o processo": runtime NOVO, mesmo banco/broker; a corretora
    # esta com sl=0/tp=0 de novo (posicao NUA, o sintoma do incidente real).
    broker.posicao = {**broker.posicao, "sl": 0.0, "tp": 0.0}
    rt_novo = IntradayLiveRuntime(
        slot=SLOT, strategy=_ScriptedDaytrade(SYMBOL, {}), config=_config(),
        bar_feed=_ScriptedBarFeed([], []), broker=broker,
        db_path=rt.db_path, execution_mode="live", initial_capital=100.0,
    )
    rt_novo.run_once(now=_agora("13:04:00"))

    assert len(broker.protecoes) == 2, "reconciliou sozinho no primeiro passo pos-restart"
    ticket, side, stop, target = broker.protecoes[-1]
    assert stop == pytest.approx(9.00) and target == pytest.approx(11.00)


# ---------- gap (e), incidente 2026-08-28: freio duro de equity/margem -----
#
# A conta chegou a equity NEGATIVA (-R$298,60) com o processo CONTINUANDO a
# tentar abrir/fechar ordem, sem freio nenhum.

def test_live_freio_duro_caixa_do_painel_zerado_bloqueia_e_tenta_zerar(tmp_path, pregao_aberto):
    """Ruina = o CAIXA DO PAINEL acabou (o que o dono digitou + o realizado +
    a posicao marcada a mercado), nunca o saldo do MT5 -- ver
    `_caixa_operacional_brl`."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)

    # O slot tem R$100 digitados; o robo ja realizou -R$100. O teto de perda
    # do PREGAO nao pega este caso (ele olha `session_pnl`, que segue zerado)
    # -- e' o freio de ruina que tem de pegar.
    rt.machine.realized_pnl = -100.0
    broker.ultimo_preco = 9.50
    passos = rt.run_once(now=_agora("13:03:00"))

    assert rt._snapshot.disaster_halt is True
    assert "ruina" in (rt._snapshot.disaster_reason or "")
    assert rt.machine.position is None, "tentou zerar e conseguiu (broker aceita o fechamento)"
    assert any(p.action == "daytrade_freio_duro" for p in passos), passos

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert any("FREIO DURO" in m for m in eventos), eventos
    assert rt.status()["daytrade"]["freio_duro"] is True


def test_live_freio_duro_persiste_no_proximo_passo_sem_reabrir(tmp_path, pregao_aberto):
    """Uma vez tripado, o freio dura o resto da SESSAO -- o proximo passo
    continua barrado, mesmo com barra nova chegando, mesmo que a posicao ja
    tenha sido zerada."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)
    rt.machine.realized_pnl = -100.0
    rt.run_once(now=_agora("13:03:00"))
    assert rt._snapshot.disaster_halt is True

    feed._barras.append(_bar("13:04", 10.00, 10.00, 10.00, 10.00))
    passos = rt.run_once(now=_agora("13:04:00"))

    assert passos[-1].action == "daytrade_freio_duro"
    assert rt.machine.position is None


def test_live_freio_duro_nao_dispara_com_caixa_positivo(tmp_path, pregao_aberto):
    """Regressao do caminho feliz: caixa do painel positivo nao aciona nada."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)

    broker.risco = {"equity": 500.0, "margin_free": 200.0, "margin": 0.0}
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))

    assert rt._snapshot.disaster_halt is False
    assert rt.machine.position is not None


def test_live_freio_duro_ignora_saldo_negativo_do_MT5_com_caixa_no_painel(
    tmp_path, pregao_aberto
):
    """REGRESSAO (2026-09-08, PMAM3): o terminal reportou `equity -3,60 /
    margem livre -3,60` num slot com R$30,00 digitados no painel, e o freio
    duro travou o pregao inteiro de um robo intacto -- 2a barra do dia,
    nenhuma ordem enviada, "conta em risco de ruina".

    O saldo do MT5 da Rico NAO acompanha o dinheiro real da corretora (a
    propria corretora confirma que nao ha sincronizacao) -- ver CLAUDE.md.
    Ele nao pode travar nada: vira UMA linha de aviso no diario e o robo
    segue operando pelo ledger do painel."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)

    broker.risco = {"equity": -3.60, "margin_free": -3.60, "balance": -3.60,
                    "margin": 0.0}
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))
    feed._barras.append(_bar("13:04", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:04:00"))

    assert rt._snapshot.disaster_halt is False, (
        "saldo do MT5 nao pode travar robo nenhum -- o caixa e' o do painel"
    )
    assert rt.machine.position is not None

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert not any("FREIO DURO" in m for m in eventos), eventos
    avisos = [m for m in eventos if "IGNORANDO o numero do terminal" in m]
    assert len(avisos) == 1, ("o aviso e' UMA linha por pregao, nao uma por "
                              f"barra: {eventos}")


def test_live_sombra_ignora_freio_duro(tmp_path, pregao_aberto):
    """Sombra nunca manda ordem pra corretora -- `_check_freio_duro` nao tem
    o que travar la (o dublê `_ExplodingBroker` nem tem `account_risk_state`,
    e mesmo que tivesse, `self.executor is None` corta antes)."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.91, 9.85, 9.90),
    ]
    rt, _feed = _runtime(tmp_path, barras)

    passos = rt.run_once(now=_agora("13:05:00"))

    assert not any(p.action == "daytrade_freio_duro" for p in passos)
    assert rt._snapshot.disaster_halt is False


# ---------- gap (f), incidente 2026-08-28: recusa de fechamento escala -----
#
# A corretora recusou ~24 vezes seguidas o fechamento (MG51, margem
# esgotada) e nada disso apareceu no diario nem alertou ninguem -- so' uma
# linha `[erro]` repetida no log bruto do processo.

def test_live_recusa_de_fechamento_repetida_escala_para_freio_duro(tmp_path, pregao_aberto):
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)

    broker.recusa_fechamento = True
    for i, hhmm in enumerate(["13:03", "13:04", "13:05", "13:06", "13:07"], start=1):
        feed._barras.append(_bar(hhmm, 8.00, 8.00, 8.00, 8.00))  # bem abaixo do stop (9.00)
        rt.run_once(now=_agora(f"{hhmm}:00"))
        assert rt._snapshot.close_refusal_count == i, (i, rt._snapshot.close_refusal_count)

    assert rt._snapshot.disaster_halt is True
    assert rt.machine.position is not None, "a corretora nunca confirmou o fechamento"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    recusas = [m for m in eventos if m.startswith("RECUSA DE FECHAMENTO")]
    assert len(recusas) == 5, eventos
    assert any("FREIO DURO" in m for m in eventos), eventos
    assert rt.status()["daytrade"]["recusas_fechamento_seguidas"] == 5


def test_live_recusa_de_fechamento_isolada_nao_trava_e_zera_apos_sucesso(tmp_path, pregao_aberto):
    """UMA recusa isolada nao aciona o freio duro, e some da contagem assim
    que um fechamento subsequente da certo."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)

    broker.recusa_fechamento = True
    feed._barras.append(_bar("13:03", 8.00, 8.00, 8.00, 8.00))
    rt.run_once(now=_agora("13:03:00"))
    assert rt._snapshot.close_refusal_count == 1
    assert rt._snapshot.disaster_halt is False

    broker.recusa_fechamento = False
    feed._barras.append(_bar("13:04", 8.00, 8.00, 8.00, 8.00))
    rt.run_once(now=_agora("13:04:00"))

    assert rt.machine.position is None, "fechou com sucesso na 2a tentativa"
    assert rt._snapshot.close_refusal_count == 0, "zerado apos fechamento bem-sucedido"


# ---------- gaps fechados na auditoria adversarial de 2026-08-28 ------------
#
# Cada teste abaixo guarda UMA lacuna que a auditoria confirmou -- todas do
# tipo "o dinheiro some sem ninguem perceber", nenhuma especifica de uma
# estrategia: elas moram em `live/` e valem para qualquer robo que rode ali.

def test_protecao_atomica_viaja_no_proprio_request_da_ordem(tmp_path, pregao_aberto):
    """O caminho ATOMICO: o stop e o alvo que a estrategia declarou na
    `EnterLimit` chegam a corretora AMARRADOS na propria ordem-limite, nao
    num segundo request depois do fill. Enquanto era um segundo request,
    existia uma janela com a posicao viva e NUA -- segundos no caso bom,
    HORAS quando o processo morria dentro dela (incidente 2026-08-28)."""
    broker = _FakeMT5Broker()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    assert broker.pendentes_enviadas, "a ordem tem de ir para a corretora"
    enviada = broker.pendentes_enviadas[-1]
    assert enviada.stop_price == pytest.approx(9.00)
    assert enviada.target_price == pytest.approx(11.00)


def test_alvo_NAO_e_atomico_quando_a_saida_e_fatiada(tmp_path, pregao_aberto):
    """Com `exit_split_unit` a maquina posiciona ordens-limite REAIS de
    fechamento, uma por fatia. Um TP da corretora no mesmo nivel fecharia a
    posicao INTEIRA junto com a fatia -- e em conta NETTING a soma passa do
    tamanho da posicao e ABRE o lado contrario. O stop continua indo."""
    broker = _FakeMT5Broker()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=2, exit_split_unit=1,
                       exit_ttl_bars=3, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    enviada = broker.pendentes_enviadas[-1]
    assert enviada.stop_price == pytest.approx(9.00), "o stop vai sempre"
    assert enviada.target_price is None, "o alvo fica com a maquina, nao com a corretora"


def test_warm_start_NAO_manda_ordem_que_a_maquina_recusou_vigiar(tmp_path, pregao_aberto):
    """`resume_session` RECUSA plantar a ordem do warm start quando ja ha
    posicao aberta (plantar por cima a deixaria orfa). O runtime mandava a
    ordem REAL para a corretora assim mesmo -- uma entrada extra, sobre uma
    posicao que ja existe, que a maquina explicitamente nao vigia."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)
    enviadas_antes = len(broker.pendentes_enviadas)

    # Forca um novo `_start_session` com a posicao ja aberta e restaurada --
    # e' o restart no meio do pregao com posicao viva.
    rt._calibrated_for = None
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))

    assert len(broker.pendentes_enviadas) == enviadas_antes, (
        "nenhuma ordem nova pode sair enquanto a maquina se recusa a vigiar uma")


def test_warm_start_com_posicao_aberta_nao_culpa_o_teto_agregado(tmp_path, pregao_aberto):
    """`resume_session` devolve `None` por DOIS motivos -- teto agregado sem
    espaco, e posicao ja aberta (que ela recusa plantar por cima de proposito).
    O diario tem de dizer QUAL dos dois: restart no meio do pregao segurando
    posicao e' o cenario comum, e alarmar `error` "teto capou" ali ensina o
    dono a desconfiar do diario justamente onde ele mais precisa confiar."""
    broker = _FakeMT5Broker()
    rt0, _feed0 = _abre_posicao_scriptada(tmp_path, broker)
    assert rt0.machine.positions, "arranjo: a posicao tem de existir e ficar persistida"

    # Processo NOVO no MESMO slot/banco -- e' o restart no meio do pregao de
    # verdade, nao um `_calibrated_for = None` na mesma instancia: o snapshot
    # persistido e' quem devolve a posicao (`_restore`), e `semente=` e' quem
    # liga o warm start (sem ela o pregao entra como "sessao a frio" e nao
    # passa nem perto do trecho sob teste).
    barras = [_bar("13:00", 10.00, 10.00, 10.00, 10.00),
              _bar("13:01", 10.00, 10.00, 9.79, 9.85)]
    rt, _feed = _runtime_live(tmp_path, barras, broker, semente=barras[:1])
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.positions, "o restart tem de reencontrar a posicao do snapshot"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [(e["level"], e["message"])
                   for e in store.recent_events(conn, acc.id, limit=80)]
    # Positiva PRIMEIRO: sem isto o teste passaria de graca em qualquer
    # cenario que nem chegue no trecho (foi o que aconteceu na primeira
    # versao dele, que caia em "sessao a frio").
    assert [m for _n, m in eventos if "posicao aberta" in m], (
        f"o trecho sob teste nao foi exercitado -- teste vazio: {eventos}")
    assert not [m for nivel, m in eventos
                if "teto agregado" in m and nivel in ("warn", "error")], (
        f"posicao aberta nao e' teto estourado -- alarme com a causa errada: {eventos}")


def test_freio_duro_cancela_ordem_parada_mesmo_SEM_posicao(tmp_path, pregao_aberto):
    """O freio duro saia na primeira linha quando nao havia posicao -- e
    deixava intacta a ordem-limite PARADA no book. O robo entrava em "nao
    abro mais nada" com uma ordem que abre sozinha, numa conta que ele mesmo
    acabou de declarar em risco de ruina, e ja cego (freio tripado = nao
    consome barra, nao redecide)."""
    broker = _FakeMT5Broker()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))
    assert broker.pendentes_enviadas, "ordem parada no book"
    assert rt.machine.position is None, "sem posicao -- so' a ordem"

    rt.machine.realized_pnl = -100.0   # caixa do painel (R$100 digitados) a zero
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))

    assert rt._snapshot.disaster_halt is True
    assert broker.canceladas, "o freio duro tem de tirar a ordem do book"


def test_exposicao_maior_na_corretora_do_que_na_maquina_trava_e_avisa(tmp_path, pregao_aberto):
    """A forma exata do incidente 2026-08-28: a maquina achava que tinha UM
    contrato e a corretora tinha DOIS (duas entradas independentes
    consolidadas pela conta NETTING). Ninguem comparava os dois numeros."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker, quantity=1)

    broker.posicao = {"side": "long", "price": 10.00, "quantity": 2, "ticket": 1,
                      "sl": 9.00, "tp": 11.00}
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))

    assert rt._snapshot.disaster_halt is True
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert any("EXPOSICAO DIVERGENTE" in m for m in eventos), eventos


def test_falha_de_LEITURA_da_posicao_nunca_vira_posicao_fechada(tmp_path, pregao_aberto):
    """`open_position` devolvia `None` tanto para "nao ha posicao" quanto
    para "nao consegui perguntar". No caminho de fechamento isso registrava
    uma saida INVENTADA para uma posicao que continuava aberta -- e deixava a
    maquina sem posicao, o que desarma o freio duro."""
    from live.intraday_execution import BrokerExecutionError

    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)

    broker.leitura_falha = True
    feed._barras.append(_bar("13:03", 8.00, 8.00, 8.00, 8.00))  # rompe o stop
    with pytest.raises(BrokerExecutionError, match="nao consegui LER"):
        rt.run_once(now=_agora("13:03:00"))

    assert rt.machine.position is not None, "a posicao NAO pode sumir por falha de leitura"


def test_fechamento_nunca_manda_mais_do_que_a_corretora_reporta(tmp_path, pregao_aberto):
    """A maquina so' decrementa a quantidade DEPOIS que `exit_market` volta
    com sucesso. Num fechamento que preencheu pela metade, a tentativa
    seguinte mandava o tamanho INTEIRO contra a posicao que sobrou -- e em
    conta NETTING uma ordem maior que a posicao nao "fecha demais", ela
    INVERTE o lado."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker, quantity=2)

    # A corretora encolheu a posicao (fechamento parcial fora do controle da
    # maquina, ou fatia que preencheu), mas a maquina ainda acha que tem 2.
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 1,
                      "sl": 9.00, "tp": 11.00}
    feed._barras.append(_bar("13:03", 8.00, 8.00, 8.00, 8.00))  # rompe o stop
    rt.run_once(now=_agora("13:03:00"))

    a_mercado = [o for o in broker.ordens_a_mercado]
    assert a_mercado, "tem de tentar fechar"
    assert a_mercado[-1].quantity == 1, (
        "o fechamento e' capado pelo que a corretora reporta, nunca pelo total antigo")



# ---------- 2026-08-28, 2a rodada: os CRITICOS que ficaram da auditoria -----
#
# A 1a rodada fechou 13 lacunas e eu reportei "sobraram ~10 de severidade
# menor". Estava errado: das que sobraram, TRES eram CRITICO. Estes testes
# travam as tres.


def test_ordem_que_a_maquina_nao_vigia_e_cancelada_no_comeco_da_sessao(
    tmp_path, pregao_aberto,
):
    """A corretora tem uma ordem-limite deste robo que ESTE processo nunca
    soube que existia -- e ela morre.

    E' a janela entre `place_limit` (a ordem sai de verdade) e o `_persist`
    do fim do passo (o ticket vira linha duravel). Processo morto ali e o
    restart redecide do zero, sem saber do ticket: duas ordens vivas no
    mesmo nivel, "2 contratos numa conta de 1" pelo lado da entrada.

    Nenhum arquivo escrito "mais cedo" conserta isso de verdade -- a
    corretora ja sabe. Basta perguntar, e e' o que passou a ser feito no
    topo de `_start_session`."""
    broker = _FakeMT5Broker()
    # O processo anterior mandou a ordem e morreu antes de persistir: o
    # snapshot deste processo nasce SEM `pending_entry_refs`, mas a corretora
    # tem o ticket pendurado.
    broker.pendentes_na_corretora = [
        {"ticket": "77701", "side": "long", "quantity": 1, "price": 10.00,
         "symbol": SYMBOL},
    ]
    rt, feed = _runtime_live_scripted(tmp_path, broker, {})
    assert not rt._snapshot.pending_entry_refs, "premissa: este processo nao conhece o ticket"

    rt.run_once(now=_agora("13:00:00"))

    assert [o.broker_ref for o in broker.canceladas] == ["77701"], (
        "ordem de entrada que ninguem vigia tem de morrer -- ela preenche sozinha"
    )
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert any("ORDEM ORFA" in m for m in eventos), eventos


def test_reconciliacao_nao_toca_na_ordem_que_a_maquina_esta_vigiando(
    tmp_path, pregao_aberto,
):
    """O contrapeso do teste acima: a ordem que a maquina ESTA vigiando
    continua viva. Um cancelamento cego aqui deixaria o robo incapaz de
    entrar -- ele armaria e a reconciliacao derrubaria, todo passo."""
    broker = _FakeMT5Broker()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))
    ticket = broker.pendentes_enviadas[0].broker_ref
    assert rt.machine.resting_limit is not None, "premissa: a maquina vigia a ordem"

    # A corretora agora RESPONDE, e responde com o ticket que a maquina vigia.
    broker.pendentes_na_corretora = [
        {"ticket": ticket, "side": "long", "quantity": 1, "price": 10.00,
         "symbol": SYMBOL},
    ]
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))

    assert not broker.canceladas, "a ordem vigiada nao pode ser cancelada"


def test_entrada_e_recusada_quando_a_margem_da_CONTA_nao_cobre(tmp_path, pregao_aberto):
    """O teto de contratos e' calculado sobre `initial_capital + realized_pnl`
    -- numeros locais a UM processo, cegos para os OUTROS slots (mesma conta
    MT5, mesma margem fisica) e para a perda ainda ABERTA.

    A margem JA COMPROMETIDA na corretora nao e' cega para nenhum dos dois:
    sai das posicoes reais de todos os slots. O portao soma ela ao que esta
    ordem exige e compara com o caixa do painel (nunca com `margin_free`, que
    herda o saldo dessincronizado do MT5)."""
    broker = _FakeMT5Broker()
    broker.margem_por_contrato = 150.0          # WDO, margem de tabela
    # A conta ja tem 1 contrato aberto (R$150 de margem) -- exatamente o
    # estado do incidente quando o 2o contrato foi enviado.
    broker.risco = {"equity": 300.0, "margin_free": 150.0, "balance": 300.0,
                    "margin": 150.0}
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script, initial_capital=300.0)
    rt.run_once(now=_agora("13:00:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    # Caixa R$300, R$150 ja comprometidos, ordem exige R$150 e o projeto pede
    # 2x de folga: 150 + 300 > 300 -> recusa. E' EXATAMENTE o 2o contrato do
    # incidente: com fator 1.0 (150 + 150 = 300) ele passaria.
    assert not broker.pendentes_enviadas, "a ordem nao pode ir para o book"
    assert rt.machine.resting_limit is None, (
        "a maquina nao pode ficar vigiando um fill que nunca vai acontecer"
    )
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert any("nao cobre a margem da conta" in m for m in eventos), eventos


def test_entrada_passa_quando_a_conta_tem_a_folga_pedida(tmp_path, pregao_aberto):
    """Contrapeso: com folga suficiente o portao nao atrapalha nada."""
    broker = _FakeMT5Broker()
    broker.margem_por_contrato = 150.0
    broker.risco = {"equity": 900.0, "margin_free": 400.0, "balance": 900.0,
                    "margin": 0.0}
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script, initial_capital=900.0)
    rt.run_once(now=_agora("13:00:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    assert len(broker.pendentes_enviadas) == 1
    assert broker.margens_perguntadas == [("long", 1, 10.00)]


def test_margem_desconhecida_nunca_bloqueia(tmp_path, pregao_aberto):
    """'Nao sei' nao e' motivo de freio -- mesma politica do resto do
    arquivo. Um terminal que nao responde a `order_calc_margin` nao pode
    deixar o robo inerte em silencio; quem nao consegue ler a conta ja vai
    falhar no envio, com erro mais especifico."""
    broker = _FakeMT5Broker()
    broker.margem_por_contrato = None           # a corretora nao respondeu
    broker.risco = {"equity": 1.0, "margin_free": 0.5, "balance": 1.0}
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    assert len(broker.pendentes_enviadas) == 1


def test_trava_de_margem_entre_processos_indisponivel_recusa_sem_mandar(
    tmp_path, pregao_aberto, monkeypatch
):
    """Corrida entre PROCESSOS (LICOES_DE_PRODUCAO.md item 3.13): a secao
    critica "consultar margem -> mandar ordem" agora e' protegida por
    `live.margin_lock.acquire_margin_gate`, que serializa TODOS os slots
    (mesmo login MT5, mesma margem fisica). Se a trava nao pode ser obtida
    a tempo (`MargemTravada`), o portao trata isso como uma consulta que
    FALHOU -- mesma politica de "nao sei" do resto do arquivo -- NUNCA como
    liberacao para mandar a ordem sem checar, e NUNCA grava como se fosse
    uma recusa por margem insuficiente de verdade (informacao diferente
    para o dono: uma e' "a conta nao aguenta", a outra e' "nao consegui
    nem perguntar"). A mecanica real de exclusao entre processos do SO
    (dois processos de verdade, timeout, trava que morre com o processo)
    e' provada em `tests/test_margin_lock.py`; aqui so' se prova que
    `_on_limit_placed` reage certo quando a trava recusa."""
    class _TravaOcupada:
        def __enter__(self):
            raise itr_mod.MargemTravada(
                "teste: trava ocupada por outro processo")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(itr_mod, "acquire_margin_gate",
                        lambda *a, **k: _TravaOcupada())

    broker = _FakeMT5Broker()
    broker.margem_por_contrato = 150.0
    # Margem de sobra -- se o portao chegasse a checar, passaria. A recusa
    # tem de vir da trava, nao da margem.
    broker.risco = {"equity": 900.0, "margin_free": 400.0, "balance": 900.0}
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=1, reason="teste")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))

    assert not broker.pendentes_enviadas, "nao pode mandar sem checar margem"
    assert rt.machine.resting_limit is None, (
        "mesmo desfecho de uma recusa da corretora: a maquina nao pode "
        "ficar vigiando um fill que nunca vai acontecer"
    )
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert any("trava de margem" in m for m in eventos), eventos
    # Nao pode ser confundida com a recusa por margem insuficiente de
    # verdade (`_recusa_por_margem`/`_check_margem_da_conta`) -- e' outra
    # causa e o dono precisa distinguir uma da outra no diario.
    assert not any("nao cobre a margem da conta" in m for m in eventos), eventos


def test_freio_de_perda_dispara_com_a_posicao_ainda_ABERTA(tmp_path, pregao_aberto):
    """O unico freio que existia era `equity <= 0` -- patrimonio ja negativo.
    Entre "esta indo mal" e "morreu" nao havia nada.

    No incidente real a perda inteira (-R$295) ficou NAO REALIZADA por uma
    hora, com a corretora recusando o fechamento: nenhum stop de sessao (que
    olha so' P&L fechado) teria visto um centavo dela. Este freio marca a
    mercado, entao dispara com a posicao de pe -- o unico momento em que
    disparar ainda serve pra alguma coisa."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker, stop=1.00, target=11.00,
                                       quantity=10)
    rt.perda_maxima_dia_brl = 30.0
    assert rt.machine.position is not None
    # Equity/margem SAUDAVEIS: quem tem de disparar e' o teto de perda, nao
    # o teste de ruina -- senao o teste provaria a coisa errada.
    broker.risco = {"equity": 5000.0, "margin_free": 5000.0, "balance": 5000.0}

    # 10 acoes compradas a 10,00 valendo 6,00 = -R$40 marcados a mercado.
    broker.ultimo_preco = 6.00
    feed._barras.append(_bar("13:03", 6.00, 6.00, 6.00, 6.00))
    rt.run_once(now=_agora("13:03:00"))

    assert rt._snapshot.disaster_halt is True
    assert "perda de R$" in (rt._snapshot.disaster_reason or "")
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert any("FREIO DE PERDA" in m for m in eventos), eventos


def test_freio_de_perda_nao_dispara_dentro_do_teto(tmp_path, pregao_aberto):
    """Contrapeso: uma perda normal, dentro do teto, nao pode travar o
    pregao. Um freio que dispara cedo demais e' tao ruim quanto um que nao
    dispara -- ele so' seria desligado."""
    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker, stop=1.00, target=11.00,
                                       quantity=10)
    rt.perda_maxima_dia_brl = 30.0
    broker.risco = {"equity": 5000.0, "margin_free": 5000.0, "balance": 5000.0}

    broker.ultimo_preco = 9.00   # -R$10, dentro do teto de R$30
    feed._barras.append(_bar("13:03", 9.00, 9.00, 9.00, 9.00))
    rt.run_once(now=_agora("13:03:00"))

    assert rt._snapshot.disaster_halt is False


def test_perda_sem_cotacao_com_posicao_aberta_e_nao_sei_nao_zero(tmp_path, pregao_aberto):
    """Sem preco para marcar a posicao aberta, a perda e' DESCONHECIDA --
    nunca "nao esta perdendo". Devolver 0.0 aqui faria o freio dormir
    exatamente quando o terminal esta instavel."""
    broker = _FakeMT5Broker()
    rt, _feed = _abre_posicao_scriptada(tmp_path, broker, quantity=1)
    broker.ultimo_preco = None

    assert rt._perda_do_pregao_brl() is None


def test_teto_de_perda_default_e_fracao_do_capital_do_slot(tmp_path, pregao_aberto):
    """O default e' decisao de projeto, nao medicao -- mas tem de ser
    derivado do capital do slot, nunca um numero fixo que ignora o tamanho
    da conta."""
    from live.intraday_runtime import FRACAO_PERDA_MAXIMA_DIA

    broker = _FakeMT5Broker()
    rt, _feed = _runtime_live_scripted(tmp_path, broker, {})
    assert rt.perda_maxima_dia_brl == pytest.approx(
        FRACAO_PERDA_MAXIMA_DIA * rt.initial_capital)


def test_leitura_de_risco_que_falha_SEMPRE_acaba_freando(tmp_path, pregao_aberto):
    """"Nao sei" isolado nunca freia -- essa e' a politica do arquivo. Mas
    "nao sei" CONTINUADO significa operar sem enxergar o risco da conta por
    tempo ilimitado, apostando que quem nao le equity tambem nao consegue
    mandar ordem. Nada no codigo garante essa aposta."""
    from live.intraday_runtime import MAX_LEITURAS_DE_RISCO_FALHAS

    broker = _FakeMT5Broker()
    broker.risco = None                     # o terminal nao responde, nunca
    rt, feed = _runtime_live_scripted(tmp_path, broker, {})
    rt.run_once(now=_agora("13:00:00"))
    assert rt._snapshot.disaster_halt is False, "uma falha isolada nao freia"

    for i in range(MAX_LEITURAS_DE_RISCO_FALHAS + 2):
        feed._barras.append(_bar(f"13:{10 + i:02d}", 10.00, 10.00, 10.00, 10.00))
        rt.run_once(now=_agora(f"13:{10 + i:02d}:00"))

    assert rt._snapshot.disaster_halt is True
    assert "leituras seguidas" in (rt._snapshot.disaster_reason or "")


def test_uma_leitura_boa_zera_o_contador_de_falhas(tmp_path, pregao_aberto):
    """Falha transitoria nao pode acumular pra sempre -- senao um terminal
    que pisca a cada meia hora acabaria freando um pregao inteiro sadio."""
    from live.intraday_runtime import MAX_LEITURAS_DE_RISCO_FALHAS

    broker = _FakeMT5Broker()
    broker.risco = None
    rt, feed = _runtime_live_scripted(tmp_path, broker, {})
    for i in range(MAX_LEITURAS_DE_RISCO_FALHAS - 1):
        feed._barras.append(_bar(f"13:{10 + i:02d}", 10.00, 10.00, 10.00, 10.00))
        rt.run_once(now=_agora(f"13:{10 + i:02d}:00"))
    assert rt._risco_ilegivel_seguidas == MAX_LEITURAS_DE_RISCO_FALHAS - 1

    broker.risco = {"equity": 500.0, "margin_free": 500.0, "balance": 500.0}
    feed._barras.append(_bar("13:59", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:59:00"))

    assert rt._risco_ilegivel_seguidas == 0
    assert rt._snapshot.disaster_halt is False


def test_cadencia_de_ordens_tem_teto_por_minuto(tmp_path, pregao_aberto):
    """Nenhum contador de envio existia: o unico teto de repeticao era o de
    RECUSAS DE FECHAMENTO. Um laco do lado da ENTRADA martelava a corretora
    indefinidamente sem nada perceber -- o mesmo padrao que o incidente
    exibiu do lado do fechamento (~24 tentativas em minutos)."""
    from live.intraday_runtime import MAX_ENVIOS_POR_MINUTO

    broker = _FakeMT5Broker()
    rt, _feed = _runtime_live_scripted(tmp_path, broker, {})
    ts = _agora("13:00:00")
    for _ in range(MAX_ENVIOS_POR_MINUTO):
        assert rt._check_cadencia_de_ordens(ts) is None
    assert rt._check_cadencia_de_ordens(ts) is not None, "o teto tem de morder"


def test_janela_de_cadencia_e_ROLANTE_nao_contador_de_sessao(tmp_path, pregao_aberto):
    """Um teto por PREGAO ou e' alto demais pra pegar o laco, ou baixo
    demais e mata operacao legitima num dia movimentado. Passados 60s, a
    janela esvazia."""
    from live.intraday_runtime import MAX_ENVIOS_POR_MINUTO

    broker = _FakeMT5Broker()
    rt, _feed = _runtime_live_scripted(tmp_path, broker, {})
    for _ in range(MAX_ENVIOS_POR_MINUTO):
        rt._check_cadencia_de_ordens(_agora("13:00:00"))
    assert rt._check_cadencia_de_ordens(_agora("13:00:30")) is not None

    assert rt._check_cadencia_de_ordens(_agora("13:01:30")) is None, (
        "passado um minuto, a janela esvaziou"
    )


def test_capital_do_slot_e_relido_do_ledger_a_cada_pregao(tmp_path, pregao_aberto):
    """`initial_capital` era lido UMA vez, na construcao do runtime, e nunca
    mais -- mas o processo `loop` roda continuo e o ledger e' editavel no
    painel. O dono podia sacar metade e o robo seguir dimensionando lote e
    teto de contratos contra o numero antigo ate alguem reiniciar."""
    broker = _FakeMT5Broker()
    rt, feed = _runtime_live_scripted(tmp_path, broker, {})
    rt.run_once(now=_agora("13:00:00"))
    assert rt.initial_capital == pytest.approx(100.0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = 40.0                      # o dono sacou e corrigiu o ledger
        store.save_account(conn, acc)

    rt._calibrated_for = None                # proximo pregao / recalibracao
    feed._barras.append(_bar("13:05", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:05:00"))

    assert rt.initial_capital == pytest.approx(40.0)
    assert rt.config.initial_capital == pytest.approx(40.0)
    assert rt.machine.config.initial_capital == pytest.approx(40.0), (
        "quem dimensiona barra a barra e' a config da MAQUINA, nao a do runtime"
    )


def test_teto_de_perda_acompanha_o_capital_quando_e_o_default(tmp_path, pregao_aberto):
    """Se o teto veio da fracao default, ele segue o capital. Um numero que
    o dono fixou no construtor NAO pode ser sobrescrito por um saque."""
    from live.intraday_runtime import FRACAO_PERDA_MAXIMA_DIA

    broker = _FakeMT5Broker()
    rt, feed = _runtime_live_scripted(tmp_path, broker, {})
    rt.run_once(now=_agora("13:00:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = 40.0
        store.save_account(conn, acc)
    rt._calibrated_for = None
    feed._barras.append(_bar("13:05", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:05:00"))

    assert rt.perda_maxima_dia_brl == pytest.approx(FRACAO_PERDA_MAXIMA_DIA * 40.0)


def test_teto_de_perda_fixado_pelo_dono_nao_e_sobrescrito(tmp_path, pregao_aberto):
    broker = _FakeMT5Broker()
    strat = _ScriptedDaytrade(SYMBOL, {})
    feed = _ScriptedBarFeed([], [])
    rt = IntradayLiveRuntime(
        slot=SLOT, strategy=strat, config=_config(), bar_feed=feed, broker=broker,
        db_path=tmp_path / "live_intraday.sqlite", execution_mode="live",
        initial_capital=100.0, perda_maxima_dia_brl=7.0,
    )
    rt.ensure_account()
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        acc.cash = 40.0
        store.save_account(conn, acc)
    rt.run_once(now=_agora("13:00:00"))

    assert rt.initial_capital == pytest.approx(40.0), "o capital acompanha o ledger"
    assert rt.perda_maxima_dia_brl == pytest.approx(7.0), "o teto do dono, nao"


def test_acao_nao_suportada_pela_execucao_real_para_o_robo_uma_vez(tmp_path, pregao_aberto):
    """Uma estrategia que emite `Enter` a mercado nao consegue operar em
    execucao real (`_entrar_a_mercado` levanta `NotImplementedError`) -- e
    isso NAO e' transitorio: a barra seguinte levanta de novo.

    Antes, a excecao subia sem captura: o journal fazia ROLLBACK, a marca de
    barra nunca avancava, e o supervisor reprocessava a MESMA barra a cada
    ~5s pelo pregao inteiro. Muito log, nenhuma informacao, e nada no painel
    dizendo por que o robo nao opera. A `CopaWin` -- TOP-2 do podio,
    selecionavel no painel -- tem `entrada_maker=False` como DEFAULT.

    Agnostico de estrategia: a captura e' da acao nao suportada, nao de um
    nome de robo."""
    broker = _FakeMT5Broker()
    script = {
        0: [Enter(side="long", quantity=1, initial_stop=9.00,
                  initial_target=11.00, reason="a mercado")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))

    # `Enter` vira `machine.pending` na barra em que a estrategia decide e
    # so' e' EXECUTADO na seguinte (anti-look-ahead: decide em close[t],
    # executa em open[t+1]) -- por isso duas barras.
    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    passos = rt.run_once(now=_agora("13:02:00"))

    assert any(p.action == "daytrade_robo_incompativel" for p in passos), passos
    assert rt._snapshot.disaster_halt is True
    assert not broker.ordens_a_mercado, "nada pode ter ido para a corretora"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert any("ROBO INCOMPATIVEL" in m for m in eventos), eventos

    # A marca de barra AVANCOU: o passo seguinte nao reprocessa a mesma barra.
    assert rt._snapshot.last_bar_ts is not None


# ---------- MEDIO 7, auditoria adversarial 2026-08-28: checkpoint por barra -
#
# `run_once` roda inteiro dentro de UMA transacao SQLite (`store.
# live_journal`). Ate aqui, qualquer excecao levantada DEPOIS de um efeito
# colateral externo CONFIRMADO (ticket recebido em `place_limit`/
# `place_pending`, fill confirmado, protecao SL/TP registrada) desfazia --
# via `conn.rollback()` -- o registro de algo que ja tinha acontecido de
# verdade na corretora, segundos antes, na MESMA chamada: o dinheiro ja
# tinha se movido e o diario fingia que nao. Ver `IntradayLiveRuntime.
# _checkpoint` e a docstring de `_consume`.

def test_falha_alto_em_barra_posterior_do_lote_nao_apaga_fill_real_confirmado_em_barra_anterior(
    tmp_path, pregao_aberto,
):
    """O cenario exato da auditoria: o supervisor entrega DUAS barras num
    UNICO `run_once` (loop atrasado -- o feed devolve tudo que fechou desde
    o ultimo poll, nao 1 barra por chamada). A 1a barra do lote confirma o
    fill REAL do 1o filho de uma entrada dividida -- dinheiro ja moveu,
    `_on_opened` grava `Intent`/`Order`/`Fill`/`live_positions`. A 2a barra
    do MESMO lote levanta `FALHA_ALTO` ao checar o 2o filho (terminal "cai"
    no meio do lote). SEM o checkpoint por barra em `_consume`, o
    `rollback()` de `store.live_journal` apagaria TAMBEM o fill da 1a
    barra -- o diario fingiria que a entrada nunca aconteceu."""
    from live.intraday_execution import BrokerExecutionError

    class _BrokerLeituraFalhaAPartirDe(_FakeMT5Broker):
        """`position_state` conta as leituras e falha (kind default =
        `FALHA_ALTO`, ver `MT5IntradayExecution._read_position`) a partir
        da chamada de numero `falha_a_partir_de` (1-based) -- o CONTADOR e'
        resetado pelo proprio teste logo antes do passo sob exame, para
        isolar so' as leituras que importam para o cenario (chamadas de
        guarda de passos ANTERIORES, ex. `_check_posicao_desconhecida` na
        calibracao, nao contam)."""

        def __init__(self):
            super().__init__()
            self.leituras = 0
            self.falha_a_partir_de = None

        def position_state(self, ticker):
            self.leituras += 1
            if self.falha_a_partir_de is not None and self.leituras >= self.falha_a_partir_de:
                return {"ok": False, "position": None,
                        "note": "terminal caiu no meio do lote (simulado no teste)"}
            return super().position_state(ticker)

    broker = _BrokerLeituraFalhaAPartirDe()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=2, split_quantities=(1, 1),
                       reason="teste_medio7")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))  # calibracao, feed ainda vazio

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))  # decide e manda os 2 filhos reais
    assert len(broker.pendentes_enviadas) == 2

    # o 1o filho JA preencheu de verdade na corretora, antes deste passo.
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 1}

    # o supervisor atrasa: DUAS barras chegam JUNTAS no MESMO passo.
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    broker.leituras = 0
    broker.falha_a_partir_de = 2  # a leitura da barra 13:02 confirma; a da 13:03 "cai"

    with pytest.raises(BrokerExecutionError):
        rt.run_once(now=_agora("13:04:00"))

    # o fill REAL confirmado na barra 13:02 tem de ter sobrevivido -- mesmo
    # com a barra 13:03 do MESMO lote tendo falhado alto logo depois.
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        ordens = conn.execute(
            "SELECT * FROM live_orders WHERE account_id = ? ORDER BY id", (acc.id,)
        ).fetchall()
        posicoes = conn.execute(
            "SELECT * FROM live_positions WHERE account_id = ?", (acc.id,)
        ).fetchall()
        intents = store.all_intents(conn, acc.id)
        snap = (acc.policy_state or {}).get("intraday") or {}

    assert len(ordens) == 1, "o fill da 1a barra do lote nao pode desaparecer no rollback"
    assert ordens[0]["filled_qty"] == 1
    assert ordens[0]["status"] == "filled"
    assert len(posicoes) == 1
    assert posicoes[0]["quantity"] == pytest.approx(1.0), "so' o filho que preencheu de verdade"
    assert len(intents) == 1
    # o checkpoint tambem torna duravel `last_bar_ts`/o snapshot da maquina
    # -- o que um RESTART leria em `_restore` se o processo morresse aqui.
    assert snap.get("last_bar_ts", "").startswith("2026-08-21T13:02")
    assert rt.machine.position is not None, "em memoria o robo continua sabendo do fill"
    assert rt.machine.position.quantity == 1


def test_protecao_registrada_sobrevive_a_falha_alto_no_mesmo_passo(tmp_path, pregao_aberto):
    """Segundo ponto da auditoria: `_ensure_protecao` roda ANTES de
    `_consume` em `run_once` e registra SL/TP REAL na corretora. Se a barra
    nova do MESMO passo falhar alto (aqui: o STOP acabou de romper e a
    LEITURA de posicao para fechar "cai" -- terminal fora do ar no meio do
    passo), o registro de protecao -- que ja e' fato consumado na
    corretora -- nao pode sumir do diario."""
    from live.intraday_execution import BrokerExecutionError

    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)
    assert broker.protecoes == [], "protecao ainda nao registrada no setup"

    # a barra rompe o stop (9.00): `_ensure_protecao` registra a protecao
    # ANTES de `_consume` tentar fechar, e so' DEPOIS a LEITURA para fechar
    # cai.
    broker.leitura_falha = True
    feed._barras.append(_bar("13:03", 8.00, 8.00, 8.00, 8.00))

    with pytest.raises(BrokerExecutionError):
        rt.run_once(now=_agora("13:03:00"))

    assert broker.protecoes, "a corretora recebeu o pedido de protecao"
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in store.recent_events(conn, acc.id, limit=50)]
    assert any("protecao registrada" in m for m in eventos), eventos


def test_falha_alto_sem_acao_real_antes_nao_deixa_rastro_nenhum(tmp_path, pregao_aberto):
    """Contrapeso dos dois testes acima: quando NADA de real acontece ainda
    NESTE passo antes da `FALHA_ALTO` (a corretora ja "caiu" antes mesmo da
    primeira acao do passo terminar), o rollback continua COMPLETO --
    exatamente o comportamento de sempre. O checkpoint por barra em
    `_consume`/`_ensure_protecao` nao inventa durabilidade onde nao ha nada
    real para proteger."""
    from live.intraday_execution import BrokerExecutionError

    broker = _FakeMT5Broker()
    rt, feed = _abre_posicao_scriptada(tmp_path, broker)
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:03:00"))
    assert len(broker.protecoes) == 1, "setup: protecao ja registrada num passo ANTERIOR"
    # a corretora agora REPORTA os niveis certos -- sem isto, o passo
    # seguinte reenviaria a protecao de novo (ver `test_live_protecao_nao_
    # reenvia_quando_ja_esta_correta`), o que sujaria a comparacao "nada de
    # novo aconteceu neste passo" que este teste faz.
    broker.posicao = {**broker.posicao, "sl": 9.00, "tp": 11.00}

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        n_ordens_antes = conn.execute(
            "SELECT COUNT(*) AS n FROM live_orders WHERE account_id = ?", (acc.id,)
        ).fetchone()["n"]
        n_eventos_antes = conn.execute(
            "SELECT COUNT(*) AS n FROM live_events WHERE account_id = ?", (acc.id,)
        ).fetchone()["n"]

    # a corretora "cai" ANTES de qualquer coisa nova acontecer neste passo,
    # e a barra rompe o stop -- a primeira acao real que este passo
    # tentaria e' exatamente a que falha.
    broker.leitura_falha = True
    feed._barras.append(_bar("13:04", 8.00, 8.00, 8.00, 8.00))  # rompe o stop (9.00)

    with pytest.raises(BrokerExecutionError):
        rt.run_once(now=_agora("13:04:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        n_ordens_depois = conn.execute(
            "SELECT COUNT(*) AS n FROM live_orders WHERE account_id = ?", (acc.id,)
        ).fetchone()["n"]
        n_eventos_depois = conn.execute(
            "SELECT COUNT(*) AS n FROM live_events WHERE account_id = ?", (acc.id,)
        ).fetchone()["n"]

    assert n_ordens_depois == n_ordens_antes, "nada novo -- nada de real aconteceu neste passo"
    assert n_eventos_depois == n_eventos_antes, "nem o log deste passo sobrevive -- nada a proteger"


# ---------- risco residual do MEDIO 7, auditoria adversarial 2026-08-28 ----
#
# Os 3 testes acima cobrem o gap ENTRE barras do mesmo lote. O que sobrava
# (reportado pelo agente que fechou o MEDIO 7): dentro de UMA UNICA chamada
# de `on_closed_bar`, um fechamento REAL confirmado no passo (1) pode ser
# seguido, na MESMA barra, por uma tentativa de resolver o filho restante de
# uma entrada dividida que levanta `FALHA_ALTO` -- cenario que so' existe
# quando a MESMA `EnterLimit` declara `split_quantities` (entrada dividida)
# E `exit_split_unit` (saida dividida) simultaneamente, exatamente o que
# `gremah`/`gremah_tick` fazem em producao com `dividir_entrada=True`. Ver
# `IntradaySessionMachine.on_closed_bar`/`_on_closed_bar_core` e
# `IntradayLiveRuntime._aplica_eventos_parciais_antes_de_falhar`.

def test_falha_alto_no_filho_de_entrada_nao_apaga_fatia_de_saida_ja_confirmada_na_mesma_barra(
    tmp_path, pregao_aberto,
):
    """O cenario exato do risco residual: uma entrada dividida em 3 filhos
    (`split_quantities=(1, 1, 1)`) tem 2 preenchidos e 1 ainda pendente --
    `resting_limit` continua vigiando esse filho. A posicao (2 acoes) TAMBEM
    tem saida dividida (`exit_split_unit=1`): o alvo arma uma fatia de 1
    numa barra, e na barra SEGUINTE essa fatia CONFIRMA (a posicao encolhe
    de 2 para 1 na corretora -- dinheiro ja moveu) -- mas como so' fechou
    PARCIALMENTE, a posicao continua aberta e `resting_limit` NAO e'
    orfanizado. Na MESMA barra, a checagem do filho de entrada que falta
    "cai" (`FALHA_ALTO`). Sem o fix, a excecao subindo apagava tambem a
    fatia JA CONFIRMADA."""
    from live.intraday_execution import BrokerExecutionError

    class _BrokerFatiaConfirmaDepoisFalha(_FakeMT5Broker):
        """1a leitura de posicao dentro do passo sob exame CONFIRMA a fatia
        de saida (posicao ja encolhida -- dinheiro ja moveu); a leitura
        SEGUINTE (checagem do filho de entrada que falta) "cai" -- simula o
        terminal ficando indisponivel no MEIO da barra, entre as duas
        consultas. Mesmo padrao de `_BrokerLeituraFalhaAPartirDe` (ver o
        teste do MEDIO 7 original acima), so' que aqui as DUAS leituras
        acontecem dentro da MESMA chamada de `on_closed_bar`, nao em barras
        diferentes."""

        def __init__(self):
            super().__init__()
            self.leituras = 0
            self.falha_a_partir_de = None

        def position_state(self, ticker):
            self.leituras += 1
            if self.falha_a_partir_de is not None and self.leituras >= self.falha_a_partir_de:
                return {"ok": False, "position": None,
                        "note": "terminal caiu no meio da barra (simulado no teste)"}
            return super().position_state(ticker)

    broker = _BrokerFatiaConfirmaDepoisFalha()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=3, split_quantities=(1, 1, 1),
                       exit_split_unit=1, exit_ttl_bars=5, reason="teste_medio7_residual")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))  # calibracao, feed ainda vazio

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))  # decide -- 3 filhos reais de entrada enviados
    assert len(broker.pendentes_enviadas) == 3

    # 2 dos 3 filhos preenchem de verdade -- 1 continua pendente.
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 2, "ticket": 1}
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.position is not None and rt.machine.position.quantity == 2
    assert rt.machine.resting_limit is not None, "o 3o filho continua vigiado"

    # o preco toca o alvo (11.00): arma a 1a fatia de saida (1 acao) como
    # ordem-limite REAL na corretora.
    feed._barras.append(_bar("13:03", 10.50, 11.50, 10.40, 11.00))
    rt.run_once(now=_agora("13:03:00"))
    assert rt.machine.position.quantity == 2, "so' ARMOU -- nenhum fill confirmado ainda"
    assert rt.machine.position.exit_resting_qty == 1

    # a barra critica: a fatia de saida CONFIRMA (posicao encolhe de 2 para
    # 1 na corretora) -- mas so' PARCIALMENTE, entao `resting_limit` (o
    # filho de entrada que falta) nao e' orfanizado. A leitura SEGUINTE,
    # dentro da MESMA barra, "cai".
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 1}
    broker.leituras = 0
    broker.falha_a_partir_de = 2  # 1a leitura (a fatia) confirma; a 2a (o filho) cai
    feed._barras.append(_bar("13:04", 11.00, 11.20, 10.90, 11.00))

    with pytest.raises(BrokerExecutionError):
        rt.run_once(now=_agora("13:04:00"))

    # em memoria, a maquina ja' sabe da fatia -- e' fato consumado na
    # corretora, independente do journal.
    assert rt.machine.position is not None, "so' 1 fatia fechou -- a posicao continua aberta"
    assert rt.machine.position.quantity == 1
    assert rt.machine.resting_limit is not None, "o filho que falta continua vigiado"

    # o PONTO do teste: a fatia JA CONFIRMADA tem de ter sobrevivido no
    # diario, apesar do rollback do resto do passo.
    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        posicoes = conn.execute(
            "SELECT * FROM live_positions WHERE account_id = ?", (acc.id,)
        ).fetchall()
        ordens_saida = conn.execute(
            "SELECT * FROM live_orders WHERE account_id = ? AND side = 'sell' ORDER BY id",
            (acc.id,),
        ).fetchall()
        snap = (acc.policy_state or {}).get("intraday") or {}

    assert len(posicoes) == 1
    assert posicoes[0]["quantity"] == pytest.approx(1.0), (
        "a fatia fechada tem de ter sido debitada da posicao no diario"
    )
    assert len(ordens_saida) == 1, "a Order da fatia de saida confirmada nao pode desaparecer"
    assert ordens_saida[0]["filled_qty"] == pytest.approx(1.0)
    # o checkpoint tambem torna duravel o estado da MAQUINA (quantidade
    # encolhida) -- o que um RESTART leria em `_restore`.
    posicoes_maquina = snap.get("machine", {}).get("positions") or []
    assert len(posicoes_maquina) == 1
    assert posicoes_maquina[0]["quantity"] == pytest.approx(1.0)


def test_falha_alto_no_filho_de_entrada_sem_fatia_confirmada_antes_nao_deixa_rastro_extra(
    tmp_path, pregao_aberto,
):
    """Contrapeso: quando a leitura que falha e' a PRIMEIRA desta barra (nada
    de real aconteceu ainda antes dela), `_aplica_eventos_parciais_antes_de_
    falhar` nao inventa nenhum journal novo -- mesmo espirito de
    `test_falha_alto_sem_acao_real_antes_nao_deixa_rastro_nenhum`, agora para
    o caminho de entrada dividida."""
    from live.intraday_execution import BrokerExecutionError

    class _BrokerFalhaImediata(_FakeMT5Broker):
        def __init__(self):
            super().__init__()
            self.leituras = 0
            self.falha_a_partir_de = None

        def position_state(self, ticker):
            self.leituras += 1
            if self.falha_a_partir_de is not None and self.leituras >= self.falha_a_partir_de:
                return {"ok": False, "position": None,
                        "note": "terminal caiu (simulado no teste)"}
            return super().position_state(ticker)

    broker = _BrokerFalhaImediata()
    script = {
        0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                       initial_target=11.00, quantity=2, split_quantities=(1, 1),
                       reason="teste_medio7_residual_sem_fatia")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))

    feed._barras.append(_bar("13:01", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))
    assert len(broker.pendentes_enviadas) == 2

    # so' 1 dos 2 filhos preenche -- o outro continua pendente.
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 1}
    feed._barras.append(_bar("13:02", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.position is not None and rt.machine.position.quantity == 1

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        n_ordens_antes = conn.execute(
            "SELECT COUNT(*) AS n FROM live_orders WHERE account_id = ?", (acc.id,)
        ).fetchone()["n"]

    # sem posicao de saida dividida nesta entrada -- o passo (1) desta barra
    # nao toca em nada real (stop/alvo nao tocam), entao a UNICA leitura da
    # barra e' a do filho de entrada, que falha na PRIMEIRA tentativa.
    broker.leituras = 0
    broker.falha_a_partir_de = 1
    feed._barras.append(_bar("13:03", 10.00, 10.00, 10.00, 10.00))

    with pytest.raises(BrokerExecutionError):
        rt.run_once(now=_agora("13:03:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        n_ordens_depois = conn.execute(
            "SELECT COUNT(*) AS n FROM live_orders WHERE account_id = ?", (acc.id,)
        ).fetchone()["n"]
    assert n_ordens_depois == n_ordens_antes, "nada novo -- nada de real aconteceu neste passo"
    assert rt.machine.position is not None and rt.machine.position.quantity == 1
    assert rt.machine.position is not None, "a posicao continua aberta -- corretora recusou a leitura"


# ---------- reconciliacao por historico (gap medido ao vivo 2026-09-04) ----
#
# Slot `dt-wdo_grid_reload_maker-wdo@-live`, R$375 reais: a ordem-limite de
# entrada preencheu as 14:18:31 e a posicao fechou pelo alvo ATOMICO da
# propria corretora as 14:18:32 -- os DOIS dentro do MESMO intervalo de poll
# do supervisor (5s). `positions_get` nunca mostrou a posicao aberta em
# NENHUM poll: a deteccao por crescimento (`limit_fill`, 0 -> N -> 0 entre
# duas leituras) nunca tem chance de perceber, e sem a reconciliacao por
# historico o robo ficaria vigiando pra sempre um ticket que a corretora ja
# resolveu.

def test_entrada_preencheu_e_fechou_entre_dois_polls_e_reconciliada_pelo_historico(
    tmp_path, pregao_aberto,
):
    """Caso exato medido ao vivo: preenche @ 9,80, fecha pelo alvo com 1 tick
    de deslize CONTRA o robo (9,89 em vez do teorico 9,90) -- o diario tem
    de gravar o preco do DEAL, nunca o nivel teorico da ordem, e a maquina
    tem de ficar livre para re-armar."""
    broker = _BrokerComHistorico()
    script = {
        0: [EnterLimit(side="long", limit_price=9.80, initial_stop=7.80,
                       initial_target=9.90, quantity=1, reason="teste_round_trip")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))  # feed vazio -- so' abre a sessao

    feed._barras.append(_bar("13:01", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:01:00"))  # consome a barra 0 do script -- arma a ordem
    assert len(broker.pendentes_enviadas) == 1
    ticket = broker.pendentes_enviadas[0].broker_ref
    assert rt.machine.resting_limit is not None

    # A corretora NUNCA mostra posicao aberta -- o ciclo inteiro (fill +
    # fechamento pelo alvo) aconteceu ENTRE dois polls.
    broker.posicao = None
    broker.resposta_estado = {"ok": True, "state": "filled", "position_id": 909, "note": ""}
    broker.resposta_deals = {"ok": True, "deals": [
        {"entry": 0, "price": 9.80, "quantity": 1, "profit": 0.0, "commission": 0.0,
         "swap": 0.0, "fee": 0.0, "time": 100, "comment": ""},
        {"entry": 1, "price": 9.89, "quantity": 1, "profit": 0.09, "commission": 0.0,
         "swap": 0.0, "fee": 0.0, "time": 101, "comment": "[tp 9.9000]"},
    ], "note": ""}

    feed._barras.append(_bar("13:02", 9.85, 9.85, 9.85, 9.85))
    rt.run_once(now=_agora("13:02:00"))

    assert ticket in broker.consultas_historico
    assert 909 in broker.consultas_deals
    assert rt.machine.resting_limit is None, "livre para re-armar"
    assert rt.machine.position is None
    assert rt.machine.realized_pnl == pytest.approx(0.09)
    assert rt._snapshot.trades == 1
    assert rt._snapshot.pending_entry_refs == []

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in reversed(store.recent_events(conn, acc.id, limit=50))]
    de_ordem = [m for m in eventos if "#0" in m]
    assert de_ordem == [
        "LIMITE LONG #01 1 lote PMAM3 @ 9.8000 (stop 7.8000 / alvo 9.9000)",
        "LONG #01 1 lote PMAM3 @ 9.8000 (stop 7.8000 / alvo 9.9000)",
        "TARGET LONG #01 1 lote PMAM3 @ 9.8900 - R$ +0.09",
    ]


def test_entrada_cancelada_sem_fill_e_reconciliada_libera_pra_rearmar(tmp_path, pregao_aberto):
    """A corretora confirma (pelo historico) que a ordem morreu SEM
    preencher nada -- nenhum trade pode ser inventado, e a maquina tem de
    ficar livre para o robo re-armar na MESMA barra."""
    broker = _BrokerComHistorico()
    script = {
        0: [EnterLimit(side="long", limit_price=9.80, initial_stop=7.80,
                       initial_target=9.90, quantity=1, reason="primeira")],
        1: [EnterLimit(side="long", limit_price=9.75, initial_stop=7.75,
                       initial_target=9.85, quantity=1, reason="segunda")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))  # feed vazio -- so' abre a sessao

    feed._barras.append(_bar("13:01", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:01:00"))  # consome a barra 0 do script -- arma a ordem
    ticket = broker.pendentes_enviadas[0].broker_ref
    assert rt.machine.resting_limit is not None

    broker.posicao = None
    broker.resposta_estado = {"ok": True, "state": "canceled", "position_id": None, "note": ""}

    feed._barras.append(_bar("13:02", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:02:00"))

    assert ticket in broker.consultas_historico
    assert broker.consultas_deals == [], "sem position_id, nao ha' o que procurar nos deals"
    assert rt._snapshot.trades == 0
    assert rt.machine.realized_pnl == pytest.approx(0.0)
    # Re-armou NA MESMA barra, com a ordem NOVA do script -- prova que a
    # maquina nao ficou parada esperando um ticket que a corretora ja tinha
    # resolvido.
    assert rt.machine.resting_limit is not None
    assert rt.machine.resting_limit.limit_price == pytest.approx(9.75)
    assert len(broker.pendentes_enviadas) == 2

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in reversed(store.recent_events(conn, acc.id, limit=50))]
    assert any("CANCELA" in m and "sem preenchimento" in m for m in eventos)


def test_consulta_de_historico_falhou_mantem_vigilancia_sem_inventar_desfecho(
    tmp_path, pregao_aberto,
):
    """'Nao sei' (consulta que falhou) NUNCA pode virar 'morreu' nem
    'preencheu' -- item 1.6 de LICOES_DE_PRODUCAO.md. A ordem continua
    vigiada, sem nenhum trade inventado."""
    broker = _BrokerComHistorico()
    script = {
        0: [EnterLimit(side="long", limit_price=9.80, initial_stop=7.80,
                       initial_target=9.90, quantity=1, reason="primeira")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))  # feed vazio -- so' abre a sessao

    feed._barras.append(_bar("13:01", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:01:00"))  # consome a barra 0 do script -- arma a ordem
    ticket = broker.pendentes_enviadas[0].broker_ref

    broker.posicao = None
    broker.resposta_estado = {"ok": False, "state": None, "position_id": None,
                              "note": "terminal fora do ar (simulado)"}

    feed._barras.append(_bar("13:02", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:02:00"))

    assert ticket in broker.consultas_historico
    assert rt.machine.resting_limit is not None, "continua vigiando -- 'nao sei' nunca autoriza"
    assert rt._snapshot.pending_entry_refs == [ticket]
    assert rt._snapshot.trades == 0


def test_fechamento_sem_posicao_na_corretora_usa_deal_real_nunca_nivel_teorico(
    tmp_path, pregao_aberto,
):
    """Segundo gap medido ao vivo no MESMO slot, 2026-09-04: uma tentativa de
    fechamento pareceu recusada (`retcode=DONE` sem `price`/`deal`) mas na
    verdade executou -- a corretora reporta 'sem posicao' na consulta
    seguinte, e o historico mostra o deal REAL de saida (9,85) num preco
    PIOR que o alvo teorico (9,90, +R$0,10 se gravado por engano). O robo
    tem de gravar o preco do DEAL (+R$0,05), nunca o nivel teorico."""
    broker = _BrokerComHistorico()
    script = {
        0: [EnterLimit(side="long", limit_price=9.80, initial_stop=7.80,
                       initial_target=9.90, quantity=1, reason="primeira")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))  # feed vazio -- so' abre a sessao

    feed._barras.append(_bar("13:01", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:01:00"))  # consome a barra 0 do script -- arma a ordem

    # Fill normal -- deteccao por crescimento de posicao, caminho de sempre.
    broker.posicao = {"side": "long", "price": 9.80, "quantity": 1, "ticket": 501}
    feed._barras.append(_bar("13:02", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.position is not None
    assert rt.machine.position.entry_price == pytest.approx(9.80)

    # A posicao ja NAO existe mais na corretora quando a maquina decide
    # fechar (fechada por uma tentativa anterior "ambigua" que na verdade
    # executou, ou pela propria protecao SL/TP atomica) -- o historico
    # confirma o deal REAL, num preco PIOR que o alvo teorico.
    broker.posicao = None
    broker.resposta_deals = {"ok": True, "deals": [
        {"entry": 1, "price": 9.85, "quantity": 1, "profit": 0.05, "commission": 0.0,
         "swap": 0.0, "fee": 0.0, "time": 200, "comment": "meta-live"},
    ], "note": ""}

    feed._barras.append(_bar("13:03", 9.80, 9.91, 9.80, 9.90))  # toca o alvo teorico (9.90)
    rt.run_once(now=_agora("13:03:00"))

    assert 501 in broker.consultas_deals
    assert rt.machine.position is None
    assert rt.machine.realized_pnl == pytest.approx(0.05)
    assert broker.close_tickets == [], "nunca chegou a MANDAR fechamento -- so' leu o historico"

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [e["message"] for e in reversed(store.recent_events(conn, acc.id, limit=50))]
    de_ordem = [m for m in eventos if "#0" in m]
    assert de_ordem[-1] == "TARGET LONG #01 1 lote PMAM3 @ 9.8500 - R$ +0.05"


def test_fechamento_sem_posicao_e_sem_deal_no_historico_ainda_nao_confirma_nada(
    tmp_path, pregao_aberto,
):
    """Sem deal de saida no historico (ainda nao replicou, ou a consulta
    falhou), o fechamento NUNCA aproxima pelo nivel teorico nem pelo ultimo
    preco negociado -- levanta e tenta de novo, com a posicao continuando
    aberta NA MAQUINA."""
    broker = _BrokerComHistorico()
    script = {
        0: [EnterLimit(side="long", limit_price=9.80, initial_stop=7.80,
                       initial_target=9.90, quantity=1, reason="primeira")],
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))  # feed vazio -- so' abre a sessao

    feed._barras.append(_bar("13:01", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:01:00"))  # consome a barra 0 do script -- arma a ordem

    broker.posicao = {"side": "long", "price": 9.80, "quantity": 1, "ticket": 501}
    feed._barras.append(_bar("13:02", 9.80, 9.80, 9.80, 9.80))
    rt.run_once(now=_agora("13:02:00"))
    assert rt.machine.position is not None

    broker.posicao = None
    broker.resposta_deals = {"ok": True, "deals": [], "note": ""}  # historico ainda nao tem nada

    feed._barras.append(_bar("13:03", 9.80, 9.91, 9.80, 9.90))
    passos = rt.run_once(now=_agora("13:03:00"))

    passo = [p for p in passos if p.action == "daytrade_recusa_fechamento"]
    assert passo, "recusa de fechamento -- posicao continua aberta, tenta de novo depois"
    assert rt.machine.position is not None, "a maquina NAO pode ter fechado sem deal confirmado"
    assert rt.machine.realized_pnl == pytest.approx(0.0)


# ---------- o impedimento diz o NUMERO (2026-09-08) -------------------------

def test_impedimento_por_caixa_diz_quanto_falta_e_de_onde_vem_o_minimo(
    tmp_path, pregao_aberto
):
    """Queixa do dono, 2026-09-08: PMAM3 subiu 175% em tres semanas, o custo
    do lote passou de R$30 para R$33, e o painel so' dizia "impedido" com o
    texto fixo "caixa abaixo do minimo do dia" -- para descobrir que faltavam
    R$3,00 era preciso abrir o log do processo.

    O texto e' de TELA (decimal BR) e tem de carregar as tres coisas que
    respondem "e agora?": quanto falta, de onde sai o minimo, e quanto ha."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    _set_cash(rt, 7.50)

    rt.run_once(now=_agora("13:02:30"))

    # O gate cobra o preco da ULTIMA barra fechada (9,85), nao o da primeira.
    impedimento = rt.status()["daytrade"]["impedimento"]
    assert impedimento is not None
    assert "faltam R$ 2,35" in impedimento, impedimento
    assert "a R$ 9,85" in impedimento, impedimento   # de onde sai o minimo
    assert "R$ 7,50" in impedimento, impedimento     # o caixa
    assert SYMBOL in impedimento, impedimento


def test_impedimento_por_caixa_some_quando_o_dono_completa_o_caixa(
    tmp_path, pregao_aberto
):
    """O piso do dia nao e' sentenca: reposto o caixa, o robo volta no MESMO
    pregao (mesma regra ja provada para o AutoTrading em
    `test_pregao_recusado_grava_impedimento_e_o_painel_o_enxerga`)."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, feed = _runtime(tmp_path, barras)
    _set_cash(rt, 7.50)
    rt.run_once(now=_agora("13:02:30"))
    assert rt.status()["daytrade"]["impedimento"] is not None

    _set_cash(rt, 500.00)
    rt._capital_checked_for = None  # novo pregao/reavaliacao: releia o caixa
    feed._barras.append(_bar("13:02", 9.85, 9.90, 9.85, 9.88))
    rt.run_once(now=_agora("13:03:00"))

    assert rt.status()["daytrade"]["impedimento"] is None


def test_texto_de_falta_de_caixa_em_FUTURO_fala_de_margem_nao_de_lote(
    tmp_path, pregao_aberto
):
    """Futuro nao tem "lote de 100 a R$ X": o minimo e' MARGEM por contrato.
    Citar preco x lote ali daria a entender que o robo precisa do nocional
    inteiro no caixa -- o bug de ~R$1 milhao que `capital_minimo_para` ja
    documenta, so' que escrito na tela do dono."""
    rt, _feed = _runtime(tmp_path, [_bar("13:00", 10.00, 10.00, 10.00, 10.00)])
    rt.strategy.is_futuro = True

    texto = rt._texto_de_falta_de_caixa(saldo=120.0, minimo=150.0, preco=5112.5)

    assert "faltam R$ 30,00" in texto, texto
    assert "margem" in texto, texto
    assert "5.112,50" not in texto, f"nao pode citar o preco do contrato: {texto}"


def test_cadencia_conta_RELOGIO_DE_PAREDE_nao_carimbo_do_tick(tmp_path, pregao_aberto):
    """O contador de envios tem de morder quando a CORRETORA leva a rajada,
    e a corretora vive no relogio de parede.

    Regressao do pregao real de 2026-09-08 (slot `dt-wdo_grid_reload_maker-
    wdo@-live`): um passo do supervisor processa TODO o atraso acumulado do
    feed de uma vez (ver `_aplica_barras`), e a maquina estava 24 min atras
    do mercado. Ela reproduziu minutos de historico em milissegundos de
    parede, mandando uma ordem REAL por tick replicado -- 45 ordens em 13
    SEGUNDOS reais, 125 ordens para 22 trades. Nada disparou porque o
    contador recebia `evento.ts`: em tempo de TICK aqueles envios estavam
    minutos um do outro, entao a janela de 60s nunca acumulava 30.

    Aqui o lote inteiro chega num unico `run_once`, com carimbos de tick a
    1 minuto de distancia -- espacamento em que a versao antiga NUNCA
    acumulava dois envios na mesma janela e deixava passar todos."""
    from live.intraday_runtime import MAX_ENVIOS_POR_MINUTO

    envios = MAX_ENVIOS_POR_MINUTO + 5
    broker = _FakeMT5Broker()
    script = {
        i: [EnterLimit(side="long", limit_price=10.00 + i * 0.01,
                       initial_stop=9.00, initial_target=11.00, quantity=1,
                       reason="rajada")]
        for i in range(envios)
    }
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:00:00"))   # passo de abertura da sessao

    # O ATRASO: todo o lote chega de uma vez, como quando o supervisor volta
    # de um buraco (2026-09-08: "buraco de 35 min sem rodar; 14704 barras
    # puladas"). Carimbos a 1 min de distancia -- espacamento em que a versao
    # antiga nunca acumulava dois envios na mesma janela de 60s.
    for i in range(envios):
        feed._barras.append(_bar(f"13:{i:02d}", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:01:00"))
    assert len(broker.pendentes_enviadas) <= MAX_ENVIOS_POR_MINUTO, (
        f"a corretora recebeu {len(broker.pendentes_enviadas)} ordens num unico "
        f"passo de parede -- o teto de {MAX_ENVIOS_POR_MINUTO}/60s tem de morder "
        "mesmo quando os carimbos de tick estao minutos um do outro"
    )
    assert rt._snapshot.disaster_halt is True, (
        "estourar o teto de envios e' laco, nao operacao: tem de parar o robo"
    )


def test_diario_mede_TEMPO_DE_VIDA_e_DESLIZE_da_saida(tmp_path, pregao_aberto):
    """Reproduz o que o diario nao sabia dizer em 2026-09-08.

    Naquele pregao, 10 das 22 posicoes do WDO abriram e fecharam em menos de
    1 segundo (58ms a 561ms), cada uma perdendo 1 tick, e 8 alvos nativos
    executaram PIOR que o nivel pedido. Todas as 22 sairam no diario com
    `exit_reason="target"` e mais nada -- sem duracao, sem o nivel pedido.
    Nem o painel nem o dono tinham como ver que "alvo" ali significava
    round-trip de execucao: o que separa os dois nao e' o motivo declarado,
    e' o TEMPO DE VIDA e o preco contra o NIVEL.

    Aqui a barra TOCA o alvo (9,90) mas a corretora executa o fechamento a
    mercado a 9,88 -- o caso real, em que a saida rotulada "target" nao paga
    o nivel."""
    import json

    broker = _FakeMT5Broker()
    broker.preco_de_saida = 9.88
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),   # confirma entrada
        _bar("13:02", 9.85, 9.95, 9.85, 9.90),     # toca o alvo (9.90)
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)
    broker.posicao = {"side": "long", "price": 9.80, "quantity": 1, "ticket": 77}

    rt.run_once(now=_agora("13:04:00"))

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        linhas = list(conn.execute(
            "SELECT level, message, payload FROM live_events "
            "WHERE account_id = ? ORDER BY id", (acc.id,)))

    saidas = [json.loads(p) for _l, _m, p in linhas
              if p and '"exit_reason"' in p]
    assert saidas, "nenhuma saida foi jornalizada"
    saida = saidas[-1]
    assert saida["exit_reason"] == "target"
    assert "duracao_s" in saida, (
        "sem o TEMPO DE VIDA no diario, round-trip de execucao e alvo de "
        "verdade sao indistinguiveis -- foi o que escondeu R$40,00 em 2026-09-08"
    )
    assert saida["alvo_declarado"] == pytest.approx(9.90), (
        "o nivel PEDIDO tem de sobreviver ate' o fechamento; sem ele nao ha "
        "como medir deslize de saida (item 4.8)"
    )
    # alvo 9,90 executado a 9,88, point_value 1,0, 1 lote
    assert saida["deslize_vs_alvo_brl"] == pytest.approx(0.02), (
        "o diario tem de registrar o quanto o nivel deixou de pagar, nao so' "
        "o pnl (item 4.8)"
    )
    avisos = [m for l, m, _p in linhas if l == "warn"]
    assert any("DESLIZE DE SAIDA" in m for m in avisos), (
        "alvo que nao paga o nivel tem de VIRAR alarme, nao so' campo no "
        "payload -- foi o silencio que deixou 8 de 8 passarem em 2026-09-08"
    )


def test_alvo_e_fechado_pela_PROTECAO_da_corretora_nunca_a_mercado(tmp_path, pregao_aberto):
    """Ordem do dono, 2026-09-08: "deve posicionar o target e o stop assim que
    abre a posicao, nao e' para sair a mercado, a posicao deve ser fechada ou
    quando bate no alvo, ou quando bate no stop".

    Ate' este dia o motor mandava fechamento A MERCADO tambem no alvo. O custo
    e' estrutural, nao residual: venda a mercado executa no BID e o spread do
    WDO e' 1 tick, entao um alvo de 2 ticks entregava no MAXIMO metade -- e
    entregava -1 tick sempre que o preco nao tinha andado. No pregao de
    2026-09-08, 14 dos 23 contratos fecharam assim, e a distribuicao realizada
    (+R$5 x7 / R$0 x3 / -R$5 x11) nao tinha relacao nenhuma com a geometria
    configurada (+R$10 / -R$80): era so' onde estava o bid.

    Aqui a corretora TEM o TP registrado. A barra toca o alvo, a maquina
    decide sair -- e nao pode sair NADA para a corretora."""
    broker = _FakeMT5Broker()
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),   # confirma entrada
        _bar("13:02", 9.85, 9.95, 9.85, 9.90),     # toca o alvo (9.90)
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)
    # A corretora reporta a posicao COM protecao registrada -- e' o que
    # `place_pending` anexa no mesmo request da entrada (`_alvo_atomico`).
    broker.posicao = {"side": "long", "price": 9.80, "quantity": 1, "ticket": 77,
                      "sl": 7.80, "tp": 9.90}

    rt.run_once(now=_agora("13:04:00"))

    assert broker.ordens_a_mercado == [], (
        "o alvo tem de ser fechado pelo TP registrado na corretora -- mandar "
        "ordem a mercado por cima paga o spread e entrega menos que o nivel"
    )
    assert broker.close_tickets == [], "nenhum fechamento pode ter sido enviado"
    assert rt.machine.position is not None, (
        "enquanto a corretora nao executar o TP, a posicao continua aberta na "
        "maquina -- a proxima barra reavalia"
    )
    assert rt._snapshot.close_refusal_count == 0, (
        "esperar o nivel ser tocado e' o funcionamento NORMAL; contar como "
        "recusa travaria o robo em poucos segundos"
    )
    assert rt._snapshot.disaster_halt is False


def test_posicao_SEM_protecao_registrada_ainda_fecha_a_mercado(tmp_path, pregao_aberto):
    """A regra acima nao pode abrir o buraco do incidente de 2026-08-28, em que
    a posicao ficou com `sl=0.0, tp=0.0` na corretora por HORAS.

    Se o nivel nao esta' registrado, esperar por ele deixaria a posicao NUA
    para sempre. Sem protecao, fecha a mercado: preco pior, mas fechado."""
    broker = _FakeMT5Broker()
    broker.preco_de_saida = 9.88
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
        _bar("13:02", 9.85, 9.95, 9.85, 9.90),
    ]
    rt, _feed = _runtime_live(tmp_path, barras, broker)
    broker.posicao = {"side": "long", "price": 9.80, "quantity": 1, "ticket": 77,
                      "sl": 0.0, "tp": 0.0}   # desprotegida

    rt.run_once(now=_agora("13:04:00"))

    assert len(broker.ordens_a_mercado) == 1, (
        "sem nivel registrado na corretora nao ha o que esperar -- tem de fechar"
    )
    assert rt.machine.position is None


# ---------- barra velha nao vira ordem (2026-09-08) -------------------------
#
# O pregao que pagou por esta secao: slot `dt-wdo_grid_reload_maker-wdo@-live`,
# -R$116 em 08/09/2026. O terminal MT5 parou de entregar tick NOVO de WDO@ por
# 44,8 min sem erro nenhum (`closed_bars_since` devolveu lista VAZIA em 538
# passos seguidos, marca d'agua congelada em 14:14:20.804) e no passo seguinte
# devolveu 13.644 barras de uma vez. O estado da conta as 15:00:57 mostrava
# `last_bar_ts=14:36:21` contra `last_poll_at=15:00:57` -- 24 min de atraso --
# e o loop de `_consume` tratou CADA barra velha como se fosse agora: 45
# ordens-limite REAIS em precos de ate' 45 min atras. Uma limite num preco
# morto chega ao book como ordem AGRESSIVA e preenche na hora no pior preco.
#
# O freio que ja' existia (`MAX_GAP_SECONDS`) nao tinha como pegar: ele mede
# tempo sem RODAR, e o processo rodou de 5 em 5s o tempo todo. Quem estava
# velho era o DADO. Ver `MAX_ATRASO_PARA_ORDEM_SEGUNDOS`.


def test_barra_velha_NAO_vira_ordem_real_na_corretora(tmp_path, pregao_aberto):
    """O caso do incidente, reduzido ao osso: a maquina arma sobre uma barra
    de 30 min atras. A ordem NAO pode sair para a corretora.

    Prova tambem os dois efeitos colaterais obrigatorios: a maquina nao pode
    ficar VIGIANDO um nivel que nao existe no book (isso calaria o robo pelo
    resto do pregao, o modo de falha do item 6.15 do `LICOES_DE_PRODUCAO.md`),
    e o descarte tem de aparecer no diario com CONTAGEM -- em `warn`, para o
    dono ver na hora que o robo parou de mandar ordem, em vez de descobrir no
    fim do dia."""
    broker = _FakeMT5Broker()
    script = {0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.00,
                             initial_target=11.00, quantity=1,
                             reason="teste_barra_velha")]}
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    # 1o passo com o feed VAZIO so' para abrir a sessao a frio -- senao
    # `_start_session` consome a 1a barra do roteiro antes de `_consume` ver
    # ela (mesmo padrao dos outros testes com `_runtime_live_scripted`).
    rt.run_once(now=_agora("13:29:55"))

    # O passo que consome vem 5s depois do anterior -- o processo NAO ficou
    # parado (`MAX_GAP_SECONDS` nao dispara, como no incidente real, em que o
    # supervisor rodou de 5 em 5s o tempo todo). Quem esta' velho e' o DADO.
    feed._barras.append(_bar("13:00", 10.00, 10.00, 10.00, 10.00))
    passos = rt.run_once(now=_agora("13:30:00"))   # 1.800s de atraso

    assert broker.pendentes_enviadas == [], (
        "barra de 30 min atras virou ordem REAL na corretora -- e' exatamente "
        "o que custou R$116 em 08/09/2026"
    )
    assert rt.machine.resting_limit is None, (
        "a maquina ficou vigiando um nivel que nunca chegou ao book: o robo "
        "esperaria para sempre um fill impossivel"
    )

    passo = [p for p in passos if p.action == "daytrade"][0]
    assert passo.detail["armes_barra_velha"] == 1
    assert passo.detail["atraso_max_segundos"] == pytest.approx(1800.0)

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [dict(r) for r in conn.execute(
            "SELECT level, message, payload FROM live_events WHERE account_id = ?",
            (acc.id,))]
    avisos = [e for e in eventos if "barra velha" in e["message"]]
    assert len(avisos) == 1, "uma linha por LOTE, nunca uma por ordem descartada"
    assert avisos[0]["level"] == "warn"
    assert "1 ordem(ns) de entrada NAO enviada(s)" in avisos[0]["message"]
    assert '"armes_barra_velha": 1' in avisos[0]["payload"]


def test_barra_RECENTE_do_mesmo_lote_continua_virando_ordem(tmp_path, pregao_aberto):
    """A contraprova, e a razao de o criterio ser POR BARRA e nao por lote: no
    MESMO lote de recuperacao as primeiras barras estao velhas e a ultima ja'
    nao esta'. O robo tem de voltar a operar na primeira que chega dentro do
    prazo -- no preco de AGORA -- sem esperar o proximo passo.

    Sem isto o portao viraria a doenca que ele cura: robo mudo em silencio."""
    broker = _FakeMT5Broker()
    arme = lambda preco: EnterLimit(  # noqa: E731
        side="long", limit_price=preco, initial_stop=preco - 1.0,
        initial_target=preco + 1.0, quantity=1, reason="teste_barra_velha")
    script = {0: [arme(10.00)], 1: [arme(10.10)], 2: [arme(10.20)]}
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("13:29:55"))     # abre a sessao a frio, sem barra

    feed._barras.extend([
        _bar("13:00:00", 10.00, 10.00, 10.00, 10.00),   # 1.800s -> velha
        _bar("13:20:00", 10.10, 10.10, 10.10, 10.10),   #   600s -> velha
        _bar("13:29:55", 10.20, 10.20, 10.20, 10.20),   #     5s -> ATUAL
    ])
    passos = rt.run_once(now=_agora("13:30:00"))

    assert len(broker.pendentes_enviadas) == 1, (
        "so' a barra ATUAL pode virar ordem -- as duas velhas nao, a recente sim"
    )
    assert float(broker.pendentes_enviadas[0].limit_price) == pytest.approx(10.20)
    passo = [p for p in passos if p.action == "daytrade"][0]
    assert passo.detail["armes_barra_velha"] == 2
    assert rt.machine.resting_limit is not None


def test_barra_velha_NAO_engole_fechamento_de_posicao(tmp_path, pregao_aberto):
    """O outro lado da regra, e o que ela nao pode quebrar: o portao vale so'
    para EXPOSICAO NOVA. Stop, alvo, cancelamento e fechamento passam sempre.

    Motivo: nao sao decisao nova, sao a maquina constatando um FATO. Engolir
    um fechamento porque a barra estava velha deixaria posicao FANTASMA --
    exposicao real que o robo acha que nao tem -- que e' pior do que o
    problema original. O fechamento sai a MERCADO, no preco de AGORA, nunca
    no da barra velha."""
    broker = _FakeMT5Broker()
    broker.preco_de_saida = 9.30
    script = {0: [EnterLimit(side="long", limit_price=10.00, initial_stop=9.50,
                             initial_target=11.00, quantity=1,
                             reason="teste_barra_velha")]}
    rt, feed = _runtime_live_scripted(tmp_path, broker, script)
    rt.run_once(now=_agora("12:59:55"))     # abre a sessao a frio, sem barra

    # (1) arma e preenche com barras FRESCAS -- ha' posicao real de verdade.
    feed._barras.append(_bar("13:00:00", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:00:00"))
    assert len(broker.pendentes_enviadas) == 1
    broker.posicao = {"side": "long", "price": 10.00, "quantity": 1, "ticket": 42,
                      "sl": 0.0, "tp": 0.0}
    feed._barras.append(_bar("13:00:10", 10.00, 10.00, 10.00, 10.00))
    rt.run_once(now=_agora("13:00:10"))
    assert rt.machine.position is not None

    # (2) o stop e' tocado numa barra de 30 min atras. TEM de fechar.
    enviadas_antes = len(broker.pendentes_enviadas)
    rt.run_once(now=_agora("13:05:00"))    # passo vazio: mantem a cadencia
    rt.run_once(now=_agora("13:10:00"))
    feed._barras.append(_bar("13:00:20", 10.00, 10.00, 9.40, 9.45))
    passos = rt.run_once(now=_agora("13:10:05"))   # barra de ~10 min atras

    assert rt.machine.position is None, (
        "fechamento suprimido por barra velha = posicao fantasma na corretora"
    )
    passo = [p for p in passos if p.action == "daytrade"][0]
    assert passo.detail["saidas"] == 1
    assert len(broker.ordens_a_mercado) == 1, "o stop fecha a MERCADO, no preco de agora"
    assert len(broker.pendentes_enviadas) == enviadas_antes, (
        "o rearme sobre a MESMA barra velha nao pode ir ao book"
    )


def test_limite_de_atraso_soma_o_atraso_ESTRUTURAL_do_feed(tmp_path, pregao_aberto):
    """O teto nao pode ser um numero fixo: mataria o feed M1 por construcao.

    Uma barra M1 so' e' legivel DEPOIS de fechar e o `ts` dela e' a ABERTURA
    do minuto (`live/bar_feed.py`), entao toda barra M1 chega com >=60s de
    idade num robo perfeitamente saudavel. `nominal_delay_seconds` do feed
    entra somando -- 120s no feed de tick, 180s no M1."""
    broker = _FakeMT5Broker()
    rt, feed = _runtime_live_scripted(tmp_path, broker, {})

    assert feed.nominal_delay_seconds == 0.0
    assert rt._limite_de_atraso() == pytest.approx(itr_mod.MAX_ATRASO_PARA_ORDEM_SEGUNDOS)

    feed.nominal_delay_seconds = 60.0            # como o `MT5BarFeed` declara
    assert rt._limite_de_atraso() == pytest.approx(
        60.0 + itr_mod.MAX_ATRASO_PARA_ORDEM_SEGUNDOS)


# ---------- feed CEGO deixa rastro no diario (incidente 2026-09-08) ---------

class _FeedQueNaoConsegueLer:
    """Reproduz o terminal MT5 de 2026-09-08 no slot
    `dt-wdo_grid_reload_maker-wdo@-live`: `closed_bars_since` devolve lista
    VAZIA passo apos passo, mas por FALHA de leitura, nao por falta de
    negocio. `falha_de_leitura` e' o unico jeito de distinguir os dois --
    ver `live/feed_health.py`.

    `cego` e' uma lista de bool, uma entrada por passo."""

    name = "fake_bars_cego"
    nominal_delay_seconds = 0.0

    def __init__(self, cego: list[bool], semente: list[Bar] | None = None):
        self._cego = list(cego)
        self._semente = list(semente or [])
        self.passos = 0
        #: quantas leituras deste dube' de fato devolveram FALHA -- o teste
        #: compara a contagem da mensagem de recuperacao com esta, em vez de
        #: com o numero de `run_once`: nem todo passo do runtime chega a
        #: consultar o feed (a fase, o freio e o warm start podem sair antes).
        self.cegos = 0
        self.falha_de_leitura = None

    @property
    def offset_hours(self):
        return 3.0

    def closed_bars_since(self, after_ts=None):
        i = self.passos
        self.passos += 1
        esta_cego = self._cego[i] if i < len(self._cego) else False
        self.falha_de_leitura = (
            "WDO@: copy_ticks_range devolveu None (last_error=(-4, 'Terminal: Not found'))"
            if esta_cego else None
        )
        self.cegos += int(esta_cego)
        return []

    def session_bars_until(self, session, until_ts):
        return list(self._semente)


def test_feed_cego_grava_uma_linha_no_diario_e_outra_ao_voltar(tmp_path, pregao_aberto):
    """2026-09-08: 538 passos seguidos de lista vazia, marca d'agua congelada
    em 14:14:20.804, e NENHUMA linha em lugar nenhum -- 44,8 min de cegueira
    do terminal indistinguiveis de um papel parado (item 5.17 do
    `LICOES_DE_PRODUCAO.md`). Isto nao impede a ordem velha (quem faz isso e'
    `MAX_ATRASO_PARA_ORDEM_SEGUNDOS`); so' tira o silencio, para a proxima vez
    deixar rastro."""
    barras = [_bar("13:00:00", 10, 10, 10, 10)]
    feed = _FeedQueNaoConsegueLer([True, True, True, False], semente=barras)
    rt, _ = _runtime(tmp_path, barras, feed=feed)

    for _ in range(4):
        rt.run_once()
    assert feed.cegos >= 2  # o roteiro de fato cegou o robo

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [(r[0], r[1]) for r in conn.execute(
            "SELECT level, message FROM live_events WHERE account_id = ? ORDER BY id",
            (acc.id,))]

    falhas = [m for lv, m in eventos if "nao conseguiu LER" in m]
    voltas = [m for lv, m in eventos if "voltou a ler" in m]
    # UMA linha por transicao, nunca uma por passo: a 5s/passo, 45 min de
    # cegueira viraria 538 linhas iguais e o diario ficaria ilegivel
    # justamente no pregao que o dono mais precisa ler.
    assert len(falhas) == 1, falhas
    assert "leitura falhada" in falhas[0]
    assert [lv for lv, m in eventos if "nao conseguiu LER" in m] == ["error"]
    assert len(voltas) == 1
    # A contagem e' de passos do LACO PRINCIPAL, e o robo tambem le o feed no
    # comeco a frio (`closed_bars_since(None)`, outro ponto de chamada): por
    # isso ela pode ser menor que `feed.cegos`, nunca maior nem zero.
    n = int(re.search(r"apos (\d+) passo", voltas[0]).group(1))
    assert 1 <= n <= feed.cegos


def test_feed_vazio_SEM_falha_nao_gera_alarme(tmp_path, pregao_aberto):
    """A outra metade da fronteira: papel sem negocio novo devolve vazio o dia
    inteiro e isso e' NORMAL. Se alarmasse aqui, o alarme viraria ruido e o
    dono pararia de ler -- que e' como o sintoma de 08/09 volta a passar
    despercebido."""
    barras = [_bar("13:00:00", 10, 10, 10, 10)]
    feed = _FeedQueNaoConsegueLer([False, False, False], semente=barras)
    rt, _ = _runtime(tmp_path, barras, feed=feed)

    for _ in range(3):
        rt.run_once()

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        eventos = [r[0] for r in conn.execute(
            "SELECT message FROM live_events WHERE account_id = ? ORDER BY id", (acc.id,))]

    assert not any("nao conseguiu LER" in m or "voltou a ler" in m for m in eventos)
