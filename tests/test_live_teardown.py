"""Remover um robô sem deixar rastro vivo na corretora — `dashboard/
live_teardown.py`.

O que está em jogo, em ordem de gravidade se quebrar:

  1. **posição órfã invisível.** Apagar a conta com posição aberta no MT5 tira
     o robô da tela e deixa a exposição de pé. É o pior desfecho possível, e
     por isso a remoção ABORTA quando não consegue zerar a posição;
  2. **ordem que ressuscita.** Cancelar antes de matar o processo é inútil: o
     robô reancora a limite em segundos. A ordem das operações é regra, não
     estilo;
  3. **apagar às cegas.** Corretora que não respondeu não pode virar "não há
     nada pendurado" — só robô de sombra (que nunca envia ordem, por
     construção) pode ser removido sem falar com o MT5;
  4. **`magic` do vizinho.** A conta é NETTING e compartilhada: uma consulta
     sem o `magic` deste slot cancelaria ordem do outro robô.

Nada aqui toca corretora de verdade: o broker é um dublê, e o diário roda em
`tmp_path`.
"""
from __future__ import annotations

from datetime import date

import pytest

from core.config import daytrade_slot
from core.live_models import LivePosition, OrderStatus
from dashboard import live_teardown
from journal import live_store

SLOT_REAL = daytrade_slot("gremah", "PMAM3", "live")
SLOT_SOMBRA = daytrade_slot("gremah", "PMAM3", "shadow")


class _BrokerFalso:
    """Dublê do `MT5Broker` com o mínimo que `live_teardown` consome.

    `registro` guarda a ORDEM das chamadas — é o que prova que o processo
    morreu antes de a primeira ordem ser cancelada."""

    def __init__(self, *, ordens=None, posicao=None, preco=None,
                 conecta=True, fechamento=OrderStatus.FILLED, registro=None):
        self._ordens = ordens if ordens is not None else []
        self._posicao = posicao
        self._preco = preco
        self._conecta = conecta
        self._fechamento = fechamento
        self.registro = registro if registro is not None else []
        self.canceladas: list[str] = []
        self.fechou = None

    def connect(self):
        return self._conecta

    def pending_orders(self, ticker):
        return None if self._ordens is None else list(self._ordens)

    def open_position(self, ticker):
        return dict(self._posicao) if self._posicao else None

    def position_state(self, ticker):
        """Tri-estado do port (`Broker.position_state`). Um dublê lê estado em
        memória, então a consulta nunca falha: `ok=True` sempre. Quem precisa
        testar a falha de LEITURA usa `_BrokerLeituraFalha` abaixo."""
        return {"ok": True, "position": self.open_position(ticker), "note": ""}

    def last_price(self, ticker):
        return self._preco

    def cancel(self, order):
        self.registro.append(f"cancel:{order.broker_ref}")
        self.canceladas.append(order.broker_ref)
        order.status = OrderStatus.CANCELLED
        return order

    def place(self, order):
        self.registro.append(f"place:{order.side.value}:{order.quantity}")
        self.fechou = order
        order.status = self._fechamento
        if self._fechamento in (OrderStatus.FILLED, OrderStatus.PARTIAL):
            order.avg_price = self._preco
            order.filled_qty = order.quantity if self._fechamento == OrderStatus.FILLED \
                else order.quantity // 2
            # posição zerada de verdade: a releitura seguinte não a vê mais
            if self._fechamento == OrderStatus.FILLED:
                self._posicao = None
        else:
            order.note = "corretora recusou"
        return order


def _ordem(ticket="123456", side="compra", qtd=100, preco=0.13):
    return {"ticket": ticket, "side": side, "quantity": qtd,
            "price": preco, "symbol": "PMAM3"}


@pytest.fixture
def diario(tmp_path, monkeypatch):
    """Diário ao vivo isolado — o default de `live_journal` é resolvido na
    DEFINIÇÃO da geradora, então o jeito de trocá-lo é o `__defaults__` da
    função original (mesmo padrão de `tests/test_dashboard_app.py`).

    `_STATE_PATH` entra junto porque `remover()` apaga a linha do slot em
    `db/live_process.json` no fim — sem o patch, a suíte escreveria no
    arquivo de estado REAL da máquina (e dois workers do xdist brigariam
    pelo mesmo `.tmp`, que foi como isto apareceu)."""
    from dashboard import live_control

    db = tmp_path / "live_teardown.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db,))
    monkeypatch.setattr(live_control, "_STATE_PATH", tmp_path / "live_process.json")
    # `client.get("/operacao")` (usado pelos testes de criação/restauro
    # abaixo) renderiza a seção de credenciais também (`credential_status()`
    # lê `db/live_secrets.json`) — isolado pelo mesmo motivo do `_STATE_PATH`.
    monkeypatch.setattr(live_control, "_SECRETS_PATH", tmp_path / "live_secrets.json")
    return db


def _conta(slot, cash=0.0):
    with live_store.live_journal() as conn:
        conta = live_store.ensure_account(
            conn, name=slot.id, mode="mt5", initial_capital=100.0,
            investment_robot="gremah", withdrawal_robot="", symbol=slot.symbol)
        conta.cash = cash
        live_store.save_account(conn, conta)


def _existe(slot) -> bool:
    with live_store.live_journal() as conn:
        return live_store.load_account(conn, slot.id) is not None


def _monta(monkeypatch, *, broker=None, processo=None, erro_processo=None):
    monkeypatch.setattr(live_teardown, "_broker_do_slot", lambda _slot: broker)
    monkeypatch.setattr(live_teardown, "_processo_do_slot",
                        lambda _sid: (processo, erro_processo))


class _Processo:
    def __init__(self, pid=5728, modo="live"):
        self.pid = pid
        self.execution_mode = modo
        self.slot = None
        self.filhos = ()


# ---------- o número que aparece no popop ----------------------------------

def test_pl_estimado_nas_duas_pontas():
    """O número que o dono lê antes de confirmar. Errar o sinal no short
    mostraria lucro onde há prejuízo."""
    comprado = live_teardown.Pendencias(
        slot_id="x", label="X", symbol="PMAM3", modo="live", processo_pid=None,
        caixa=0.0, posicao={"side": "long", "price": 0.14, "quantity": 100},
        preco_atual=0.13)
    vendido = live_teardown.Pendencias(
        slot_id="x", label="X", symbol="PMAM3", modo="live", processo_pid=None,
        caixa=0.0, posicao={"side": "short", "price": 0.14, "quantity": 100},
        preco_atual=0.13)

    assert comprado.pl_estimado == -1.0
    assert vendido.pl_estimado == 1.0


def test_sem_preco_o_pl_e_none_e_nao_zero():
    """Zero diria "dá na mesma"; `None` diz "não sei" — e a tela tem texto
    diferente para cada um."""
    pend = live_teardown.Pendencias(
        slot_id="x", label="X", symbol="PMAM3", modo="live", processo_pid=None,
        caixa=0.0, posicao={"side": "long", "price": 0.14, "quantity": 100})
    assert pend.pl_estimado is None


# ---------- inspeção --------------------------------------------------------

def test_sombra_nao_consulta_a_corretora(diario, monkeypatch):
    """Robô de sombra nunca teve `executor` — perguntar custaria uma conexão
    para receber, por construção, lista vazia."""
    _conta(SLOT_SOMBRA, cash=35.92)

    def nao_deve_montar(_slot):
        pytest.fail("sombra não pode abrir conexão com a corretora")

    monkeypatch.setattr(live_teardown, "_broker_do_slot", nao_deve_montar)
    monkeypatch.setattr(live_teardown, "_processo_do_slot",
                        lambda _sid: (_Processo(modo="shadow"), None))

    pend = live_teardown.inspecionar(SLOT_SOMBRA)

    assert pend.e_sombra and pend.ordens == [] and pend.impedimento is None
    # `caixa` é o saldo do MODO (sombra lê `cash_sombra`, semeado com
    # `initial_capital`); os 35,92 gravados em `cash` viram `caixa_real` --
    # ver `test_o_caixa_do_dialogo_e_o_que_o_dono_ve_no_cartao`.
    assert pend.caixa == 100.0 and pend.caixa_real == 35.92
    assert pend.tem_o_que_desfazer is True


def test_o_caixa_do_dialogo_e_o_que_o_dono_ve_no_cartao(diario, monkeypatch):
    """Num robô de SOMBRA o cartão mostra `cash_sombra`, não `cash` — e o
    diálogo tem de nomear o mesmo número, senão o dono decide sobre um valor
    que nunca viu na tela.

    Não é hipótese: em 26/08/2026 o banco real tinha `dt-gremah-pmam3-shadow`
    com cash=20,00 e cash_sombra=35,92, e era 35,92 que aparecia no painel.
    O ledger real continua exposto à parte (`caixa_real`), porque é ele que a
    remoção zera antes de apagar a conta."""
    with live_store.live_journal() as conn:
        conta = live_store.ensure_account(
            conn, name=SLOT_SOMBRA.id, mode="mt5", initial_capital=0.0,
            investment_robot="gremah", withdrawal_robot="", symbol="PMAM3")
        conta.cash, conta.cash_sombra = 20.0, 35.92
        live_store.save_account(conn, conta)
    monkeypatch.setattr(live_teardown, "_processo_do_slot",
                        lambda _sid: (_Processo(modo="shadow"), None))

    pend = live_teardown.inspecionar(SLOT_SOMBRA)

    assert pend.caixa == 35.92
    assert pend.caixa_real == 20.0


def test_corretora_muda_impede_remover_robo_real(diario, monkeypatch):
    """"Não consegui perguntar" NÃO pode virar "não há nada pendurado"."""
    _conta(SLOT_REAL)
    _monta(monkeypatch, broker=_BrokerFalso(conecta=False))

    pend = live_teardown.inspecionar(SLOT_REAL)

    assert pend.ordens is None
    assert pend.consultou_corretora is False
    assert "modo real" in pend.impedimento


def test_remover_recusa_sem_tocar_em_nada_quando_ha_impedimento(diario, monkeypatch):
    _conta(SLOT_REAL, cash=30.0)
    _monta(monkeypatch, broker=_BrokerFalso(conecta=False), processo=_Processo())
    monkeypatch.setattr(live_teardown, "_broker_do_slot", lambda _s: _BrokerFalso(conecta=False))

    with pytest.raises(ValueError, match="modo real"):
        live_teardown.remover(SLOT_REAL)

    assert _existe(SLOT_REAL), "a conta não pode ser apagada num caminho recusado"


# ---------- remoção ---------------------------------------------------------

def test_mata_o_processo_ANTES_de_cancelar_ordem(diario, monkeypatch):
    """Ordem das operações é regra: com o supervisor vivo, cancelar a limite
    é inútil — ele reancora outra em segundos."""
    _conta(SLOT_REAL, cash=30.0)
    registro: list[str] = []
    broker = _BrokerFalso(ordens=[_ordem()], registro=registro)
    _monta(monkeypatch, broker=broker, processo=_Processo(pid=5728))

    from dashboard import live_control

    monkeypatch.setattr(live_control, "encerrar_processo",
                        lambda pid: registro.append(f"kill:{pid}"))
    monkeypatch.setattr(live_control, "stop", lambda slot: True)

    resultado = live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert registro == ["kill:5728", "cancel:123456"]
    assert resultado.ordens_canceladas == ["123456"]
    assert resultado.conta_apagada and not _existe(SLOT_REAL)


def test_encerra_posicao_a_mercado_e_reporta_o_resultado(diario, monkeypatch):
    _conta(SLOT_REAL, cash=30.0)
    broker = _BrokerFalso(ordens=[], posicao={"side": "long", "price": 0.14,
                                              "quantity": 100}, preco=0.13)
    _monta(monkeypatch, broker=broker)

    resultado = live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert broker.fechou.side.value == "sell" and broker.fechou.quantity == 100
    assert resultado.posicao_encerrada["pl"] == -1.0
    assert resultado.caixa_zerado == 30.0
    assert resultado.conta_apagada and not _existe(SLOT_REAL)
    assert "prejuízo" in resultado.resumo


def test_posicao_que_nao_fecha_ABORTA_a_remocao(diario, monkeypatch):
    """O pior desfecho possível seria apagar a conta aqui: o robô sai da tela
    e a exposição continua viva no MT5."""
    _conta(SLOT_REAL, cash=30.0)
    broker = _BrokerFalso(ordens=[_ordem()],
                          posicao={"side": "long", "price": 0.14, "quantity": 100},
                          preco=0.13, fechamento=OrderStatus.REJECTED)
    _monta(monkeypatch, broker=broker)

    resultado = live_teardown.remover(SLOT_REAL)

    assert resultado.conta_apagada is False
    assert _existe(SLOT_REAL), "o cartão tem de continuar na tela"
    assert resultado.ordens_canceladas == ["123456"], \
        "cancelar ordem é progresso no sentido seguro, e não é desfeito pelo aborto"
    assert any("NÃO foi apagada" in a for a in resultado.avisos)
    assert "NÃO foi removido" in resultado.resumo


def test_caixa_e_zerado_para_o_delete_account_nao_recusar(diario, monkeypatch):
    """`live_store.delete_account` recusa conta com caixa — o guarda continua
    de pé, e a remoção confirmada é quem zera antes (decisão do dono,
    2026-08-25: o popup já avisa que vai zerar)."""
    _conta(SLOT_REAL, cash=30.0)
    _monta(monkeypatch, broker=_BrokerFalso())

    resultado = live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert resultado.caixa_zerado == 30.0
    assert not _existe(SLOT_REAL)


def test_sombra_com_posicao_simulada_e_removivel(diario, monkeypatch):
    """Achado em 2026-08-28: `dt-gremah-pmam3-shadow` tinha uma posição
    simulada aberta desde o dia anterior (processo já morto) e a remoção
    recusava com "feche na corretora antes" -- mensagem sem sentido pra um
    robô que nunca chegou perto de uma corretora. `delete_account` continua
    recusando conta com `positions`, e é certo que continue (protege o robô
    REAL); a correção é `remover()` encerrar a posição simulada sozinho antes
    de chegar lá, sem tocar em broker nenhum."""
    with live_store.live_journal() as conn:
        conta = live_store.ensure_account(
            conn, name=SLOT_SOMBRA.id, mode="mt5", initial_capital=0.0,
            investment_robot="gremah", withdrawal_robot="", symbol="PMAM3")
        conta.cash_sombra = 30.0
        live_store.save_account(conn, conta)
        live_store.upsert_position(conn, conta.id, LivePosition(
            ticker="PMAM3", quantity=100, entry_date=date(2026, 8, 27),
            entry_price=0.14, capital_allocated=14.0,
            metadata={"side": "long"}))

    def falha_se_chamado(_slot):
        pytest.fail("sombra não pode falar com corretora nenhuma")

    monkeypatch.setattr(live_teardown, "_broker_do_slot", falha_se_chamado)
    monkeypatch.setattr(live_teardown, "_processo_do_slot",
                        lambda _sid: (None, None))
    monkeypatch.setattr("dashboard.robot_view._ultimo_preco",
                        lambda _symbol: (0.13, "2026-08-28"))

    resultado = live_teardown.remover(SLOT_SOMBRA, apagar_historico=True)

    assert resultado.posicao_encerrada == {
        "quantity": 100, "side": "long", "price": 0.13, "pl": -1.0}
    assert resultado.conta_apagada and not _existe(SLOT_SOMBRA)
    assert "prejuízo" in resultado.resumo


def test_processo_que_morreu_sozinho_nao_e_falha(diario, monkeypatch):
    """Entre a inspeção e o clique o processo pode ter caído. O objetivo
    ("não está mais rodando") já está cumprido."""
    _conta(SLOT_REAL)
    _monta(monkeypatch, broker=_BrokerFalso(), processo=_Processo(pid=999))

    from dashboard import live_control

    def some(pid):
        raise ValueError("não é mais um robô em execução")

    monkeypatch.setattr(live_control, "encerrar_processo", some)
    monkeypatch.setattr(live_control, "stop", lambda slot: False)

    resultado = live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert resultado.processo_encerrado is None
    assert any("já não estava" in a for a in resultado.avisos)
    assert resultado.conta_apagada


# ---------- gaps fechados na auditoria adversarial de 2026-08-28 ------------

class _BrokerComTicket(_BrokerFalso):
    """Igual ao `_BrokerFalso`, mas com o caminho DEDICADO de fechamento
    (`close_position`), que é o que o `MT5Broker` de produção tem."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fechou_com_ticket = None

    def close_position(self, order, position_ticket):
        self.fechou_com_ticket = position_ticket
        return self.place(order)


def test_fechamento_na_remocao_usa_close_position_com_o_ticket(diario, monkeypatch):
    """Mesmo bug MG51 do incidente 2026-08-28, em OUTRO ponto: sem o campo
    `position` no request, o motor de risco da corretora trata a ordem como
    ABERTURA nova e recusa quando a margem está esgotada. Aqui dói mais — é o
    momento em que o dono está tentando sair de tudo."""
    _conta(SLOT_REAL, cash=30.0)
    broker = _BrokerComTicket(ordens=[], preco=0.13,
                              posicao={"side": "long", "price": 0.14,
                                       "quantity": 100, "ticket": 4242})
    _monta(monkeypatch, broker=broker)

    live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert broker.fechou_com_ticket == 4242


def test_ordem_que_NAO_cancelou_impede_apagar_a_conta(diario, monkeypatch):
    """Premissa corrigida: "ordem pendurada não tem risco de mercado enquanto
    não preenche" é exatamente ao contrário. Uma limite viva no book preenche
    sozinha e abre posição real — apagar a conta aqui deixa essa posição
    nascendo sem robô, sem stop, sem diário e sem linha no painel."""
    _conta(SLOT_REAL, cash=30.0)

    class _NaoCancela(_BrokerFalso):
        def cancel(self, order):
            order.note = "a corretora recusou e a ordem CONTINUA VIVA no terminal"
            return order          # status intocado: NÃO terminal

    broker = _NaoCancela(ordens=[_ordem()])
    _monta(monkeypatch, broker=broker)

    resultado = live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert resultado.conta_apagada is False
    assert _existe(SLOT_REAL), "o cartão tem de continuar na tela"
    assert any("NÃO foi cancelada" in a for a in resultado.avisos), resultado.avisos


def test_leitura_de_posicao_que_falha_impede_apagar_a_conta(diario, monkeypatch):
    """"Não consegui ler" nunca vira "não há posição". `inspecionar` lia com
    `open_position`, que achata os dois casos no mesmo `None` — um terminal
    fora do ar era indistinguível de conta zerada, e a remoção seguia em
    frente deixando a posição real órfã no MT5 (a falha nº 1 da lista no topo
    deste arquivo)."""
    _conta(SLOT_REAL, cash=30.0)

    class _LeituraFalha(_BrokerFalso):
        def position_state(self, ticker):
            return {"ok": False, "position": None, "note": "terminal fora do ar"}

    _monta(monkeypatch, broker=_LeituraFalha(ordens=[]))

    with pytest.raises(ValueError, match="leitura da posição"):
        live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert _existe(SLOT_REAL), "sem ter tocado em nada"


def test_limpar_na_corretora_com_ordem_viva_nao_declara_limpo(diario, monkeypatch):
    """Teste direto de `_limpar_na_corretora`, que é quem decide se a conta
    PODE ser apagada. `pending_orders() is None` é "não consegui perguntar",
    não "não há nenhuma" — sem saber o que existe não dá para afirmar que a
    corretora ficou limpa."""

    class _SemLista(_BrokerFalso):
        def pending_orders(self, ticker):
            return None

    resultado = live_teardown.ResultadoRemocao(slot_id=SLOT_REAL.id, label="X")
    _monta(monkeypatch, broker=_SemLista(ordens=[]))

    assert live_teardown._limpar_na_corretora(SLOT_REAL, resultado) is False
    assert any("não respondeu a lista" in a for a in resultado.avisos)
