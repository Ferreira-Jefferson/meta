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

from datetime import date, datetime, time, timezone

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.machine import IntradayBacktestConfig
from core.config import slot_by_id
from core.live_models import OrderSide, OrderStatus, OrderType
from journal import live_store as store
from live import clock as live_clock
from live import intraday_runtime as itr_mod
from live.intraday_runtime import MAX_GAP_SECONDS, IntradayLiveRuntime
from strategy.daytrade.base import Bar, EnterLimit, IntradayStrategy

# O slot de day trade e' DINAMICO desde 2026-08-22: o id carrega robo+ativo
# (`dt-<robo>-<ativo>`) e o painel abre quantos o dono quiser. Nao existe mais
# um slot fixo chamado "daytrade".
SYMBOL = "PMAM3"
SLOT = slot_by_id("dt-gremah-pmam3")
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
    `connect`, `place_pending`, `cancel`, `open_position`, `place`.

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

    def connect(self):
        return self.conectado

    def supports_automation(self):
        return True

    def cash_balance(self):
        raise AssertionError("o caixa do slot vem do ledger manual, nao da corretora")

    def poll(self, order):
        return order

    def place_pending(self, order):
        self._ticket += 1
        order.status = OrderStatus.SENT
        order.broker_ref = str(self._ticket)
        self.pendentes_enviadas.append(order)
        return order

    def cancel(self, order):
        order.status = OrderStatus.CANCELLED
        self.canceladas.append(order)
        return order

    def open_position(self, ticker):
        return self.posicao

    def place(self, order):
        """Ordem a mercado (fechamento) -- preenche a `preco_de_saida`."""
        self.ordens_a_mercado.append(order)
        order.status = OrderStatus.FILLED
        order.filled_qty = order.quantity
        order.avg_price = self.preco_de_saida
        order.broker_ref = "saida-9999"
        self.posicao = None
        return order

    preco_de_saida = 9.90


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
                  dividir_entrada=False)
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
    s = rt.status()
    assert s["daytrade"]["trades_na_sessao"] == 1
    # (9.88 - 9.80) * 1 acao = +0,08, debitado no CAIXA (nao em sombra)
    assert s["caixa"] == pytest.approx(100.08, abs=0.01)
    assert s["daytrade"]["resultado_sombra"] == pytest.approx(0.0)
    # `caixa_sombra` (saldo paralelo) fica INTOCADO em execucao real -- so'
    # `cash` recebe o P&L quando `execution_mode="live"`.
    assert s["daytrade"]["caixa_sombra"] == pytest.approx(100.0)


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
    entrada ja armada e SEM fill nenhum. O warm start do processo novo
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
                                   dividir_entrada=False),
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
                                   dividir_entrada=False),
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


def _runtime_live_scripted(tmp_path, broker, script: dict[int, list]):
    strat = _ScriptedDaytrade(SYMBOL, script)
    feed = _ScriptedBarFeed([], [])
    rt = IntradayLiveRuntime(
        slot=SLOT, strategy=strat, config=_config(),
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
    assert acc.cash == pytest.approx(101.0), "lucro da fatia (11.00-10.00)*1 ja' creditado"

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


def test_restart_com_fatia_de_saida_armada_em_execucao_real_falha_alto(tmp_path, pregao_aberto):
    """Gap de restart no meio de uma fatia armada (2026-08-23): o PROCESSO
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
                        spacing_multiplier=2.0, stop_multiplier=20.0),
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
    # As buscas ao feed sao SEMPRE a cauda de sessoes ANTERIORES (janela de
    # volume rolante + janela de volatilidade diaria) -- o warm start de HOJE
    # nao acontece (comeco a frio nunca tenta buscar a semente de HOJE).
    dias_vol = []
    dia = SESSION
    for _ in range(itr_mod._CAUDA_VOL_DIAS):
        dia = live_clock.previous_session(dia)
        dias_vol.append((dia, itr_mod._FIM_DE_PREGAO_QUALQUER))
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


# ---------- caixa minimo do dia (2x o lote, reavaliado a cada pregao) -------

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
    """Regra do dono (2026-08-22): o piso e' 2x o custo do lote NO PRECO DE
    HOJE, e o robo tem de saber sozinho que nao cabe. Com `default_quantity=1`
    a R$10,00, o minimo e' R$20,00 -- R$10,00 em caixa nao pode operar."""
    barras = [
        _bar("13:00", 10.00, 10.00, 10.00, 10.00),
        _bar("13:01", 10.00, 10.00, 9.79, 9.85),
    ]
    rt, _feed = _runtime(tmp_path, barras)
    _set_cash(rt, 10.00)

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
    _set_cash(rt, 20.00)  # exatamente o minimo: 1 acao a R$10 x 2

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
    _set_cash(rt, 0.0)            # caixa real: nao cobriria o minimo de R$20
    _set_cash_sombra(rt, 20.00)   # saldo de sombra: cobre exatamente

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
    _set_cash(rt, 10.00)          # caixa real: nao cobre o minimo de R$20
    _set_cash_sombra(rt, 1_000.00)  # saldo de sombra: irrelevante em live

    with store.live_journal(rt.db_path) as conn:
        acc = store.load_account(conn, SLOT.id)
        alarme = rt._check_capital(conn, acc, SESSION, preco=10.00)

    assert alarme is not None
    assert "nao cobre o minimo" in alarme


def test_minimo_do_dia_sai_do_preco_e_da_quantidade_reais(tmp_path, pregao_aberto):
    """O piso nao e' um numero fixo em lugar nenhum: sai de
    `capital_minimo_brl(preco_de_hoje, quantidade_do_robo)`. Um papel que
    dobrou de preco exige o dobro de caixa no mesmo robo."""
    barras = [
        _bar("13:00", 40.00, 40.00, 40.00, 40.00),  # semente (warm start)
        _bar("13:01", 40.00, 40.00, 39.90, 40.00),  # a consumida: e o close DELA que vale
    ]
    rt, _feed = _runtime(tmp_path, barras)
    _set_cash(rt, 10.00)

    rt.run_once(now=_agora("13:02:30"))

    # 1 acao (default_quantity do harness) a R$40,00 -> lote R$40 -> piso R$80.
    # O preco vem do close da ULTIMA barra fechada -- o mais recente que existe.
    assert rt._capital_minimo_hoje == pytest.approx(80.0)
    assert "80.00" in rt._capital_alarm


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
    _set_cash(rt, 10.00)

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

    assert dt["capital_minimo_hoje"] == pytest.approx(20.0)
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
