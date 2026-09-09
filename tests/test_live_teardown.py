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

from datetime import date, timedelta

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

    # LIQUIDO desde 2026-09-09, e liquido dos DOIS custos de uma saida a
    # mercado: taxa de bolsa (0,05% por perna sobre o nocional de cada uma) e
    # 1 tick de derrapagem, que entra no PRECO como no motor
    # (`machine._close_position` em sombra). O tick da acao e' R$0,01 -- num
    # papel de centavos ele domina o resultado, e era exatamente esse custo
    # que o popup escondia.
    #
    #   comprado: sai VENDENDO a 0,13 - 0,01 = 0,12 -> bruto (0,12-0,14)x100
    #             = -2,00; taxa 0,0005x100x(0,14+0,12) = 0,013 -> 0,01
    #   vendido:  sai COMPRANDO a 0,13 + 0,01 = 0,14 -> bruto 0,00;
    #             taxa 0,0005x100x(0,14+0,14) = 0,014 -> 0,01
    assert comprado.pl_estimado == -2.01
    assert vendido.pl_estimado == -0.01


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
    # LIQUIDO tambem no caminho REAL (2026-09-09): o caixa de verdade e' o
    # extrato da corretora (este modulo nunca o escreve), mas o numero da
    # tela e' o que o dono confere contra o extrato -- reportar bruto o faria
    # procurar uma diferenca que nao existe.
    #
    # E BRUTO DE DERRAPAGEM, ao contrario do caminho de sombra (2026-09-09):
    # `avg_price` (0,13) e' o preco que a corretora EXECUTOU -- a derrapagem
    # ja aconteceu e ja esta dentro dele. Cobrar mais 1 tick aqui daria -2,01
    # e o resumo da tela deixaria de bater com o extrato, que e' o oposto do
    # que este bloco existe para garantir. Ver
    # `test_a_derrapagem_e_cobrada_na_sombra_e_nao_no_real`.
    assert resultado.posicao_encerrada["pl"] == -1.01
    assert resultado.posicao_encerrada["price"] == 0.13
    assert resultado.posicao_encerrada["taxas"] == 0.01
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
            # Datas RELATIVAS a hoje (2026-09-09): com os literais que
            # estavam aqui (posição de 27/08, barra salva de 28/08) este
            # teste virou aprovado-por-coincidência assim que a recusa de
            # preço velho entrou -- a barra passou a ser recusada, a saída
            # caiu no preço de ENTRADA (0,14) e a derrapagem de 1 tick a
            # trouxe de volta a 0,13, exatamente o número que a asserção
            # esperava. Passava, e não testava mais nada do que diz testar.
            ticker="PMAM3", quantity=100, entry_date=date.today() - timedelta(days=1),
            entry_price=0.14, capital_allocated=14.0,
            metadata={"side": "long"}))

    def falha_se_chamado(_slot):
        pytest.fail("sombra não pode falar com corretora nenhuma")

    monkeypatch.setattr(live_teardown, "_broker_do_slot", falha_se_chamado)
    monkeypatch.setattr(live_teardown, "_processo_do_slot",
                        lambda _sid: (None, None))
    monkeypatch.setattr(
        "dashboard.robot_view._ultimo_preco",
        lambda _symbol: (0.13, (date.today() - timedelta(days=1)).isoformat()))

    resultado = live_teardown.remover(SLOT_SOMBRA, apagar_historico=True)

    # Marcado a 0,13, saída VENDE e paga 1 tick -> executa a 0,12: -R$2,00 de
    # bruto, R$0,01 de taxa de bolsa, R$1,00 de derrapagem (100 x R$0,01).
    assert resultado.posicao_encerrada["price"] == pytest.approx(0.12)
    assert {k: v for k, v in resultado.posicao_encerrada.items() if k != "price"} == {
        "quantity": 100, "side": "long", "pl": -2.01, "taxas": 0.01,
        "deslize": 1.0}
    assert resultado.conta_apagada and not _existe(SLOT_SOMBRA)
    assert "prejuízo" in resultado.resumo


def test_registro_com_posicao_que_a_corretora_NAO_tem_nao_prende_o_robo(diario, monkeypatch):
    """IMPASSE achado ao vivo em 2026-09-09, com o dono tentando remover o
    robô e o cartão voltando para a tela.

    O slot REAL tinha em `live_positions` um short de 1 WDO@ @ 5122,50 que o
    MT5 não tinha (nem posição, nem ordem pendente -- conferido no terminal).
    Os dois guards, cada um certo em separado, se travavam:

      * `inspecionar()` pergunta a posição à CORRETORA -- não há --, então
        `remover()` não tinha o que encerrar;
      * `delete_account`/`archive_account` recusam olhando o BANCO: "feche na
        corretora antes de remover o robô".

    A única instrução que a tela sabia dar era impossível de cumprir. Faltava
    alguém reconciliar quando as duas fontes discordam -- e a corretora é a
    fonte de verdade sobre o que EXISTE.

    O que este teste trava junto, e é o que torna a reconciliação segura: ela
    só vale com a consulta CONFIRMADA (`erro_corretora is None`). Corretora
    muda continua barrando tudo, pelo `impedimento` -- ver o teste vizinho."""
    _conta(SLOT_REAL)
    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, SLOT_REAL.id)
        live_store.upsert_position(conn, conta.id, LivePosition(
            ticker=SLOT_REAL.symbol, quantity=-1, entry_date=date(2026, 9, 9),
            entry_price=5122.5, capital_allocated=150.0,
            metadata={"side": "short"}))

    # Corretora responde, e responde "não tenho nada".
    _monta(monkeypatch, broker=_BrokerFalso(), processo=None)

    resultado = live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert resultado.conta_apagada and not _existe(SLOT_REAL), (
        "com a corretora confirmando que não há posição, a linha do banco é "
        "registro errado -- não pode prender o robô no painel para sempre"
    )
    assert any("corretora NÃO tem" in a for a in resultado.avisos), (
        "a divergência tem de aparecer para o dono, não sumir em silêncio"
    )
    # Não inventa negócio: não houve execução nenhuma para registrar.
    assert resultado.posicao_encerrada is None


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


# ---------- futuro: ponto não é real, e nocional não é caixa ----------------
#
# Achado ao vivo em 2026-09-09, na conta `dt-wdo_grid_reload_maker-wdo@-
# shadow`: encerrar um short de 1 WDO@ @ 5133,0 deixou `cash_sombra` em
# **-R$4.706,00**, partindo de R$375,00. A conta que produziu o número foi
# `375,00 + (5133,00 x -1) + 52,00`, e ela erra em três lugares ao mesmo
# tempo -- preço de saída de 12 dias atrás, lado aplicado duas vezes (a perda
# de 52 pontos virou "lucro"), ponto do mini-dólar contado como real (52
# pontos são R$520,00) e nocional devolvido no lugar da margem.
#
# Um teste por defeito, no símbolo em que eles aparecem, mais o caminho de
# AÇÃO que já funcionava -- é o que prova que a correção não trocou um erro
# por outro.

SLOT_WDO = daytrade_slot("wdo_grid_reload_maker", "WDO@", "shadow")


def _conta_com_posicao(slot, *, cash_sombra, quantity, entry_price,
                       capital_allocated, side, entry_date=None):
    """`entry_date` default HOJE, pelo mesmo motivo de `_sombra_sem_corretora`
    (ver lá): a recusa de preço velho compara a data da barra salva com a data
    de ABERTURA da posição, então um literal aqui daria a dois testes idênticos
    vereditos diferentes conforme o dia em que a suíte rodasse."""
    entry_date = entry_date or date.today()
    with live_store.live_journal() as conn:
        conta = live_store.ensure_account(
            conn, name=slot.id, mode="mt5", initial_capital=0.0,
            investment_robot=slot.robot_key, withdrawal_robot="",
            symbol=slot.symbol)
        conta.cash_sombra = cash_sombra
        live_store.save_account(conn, conta)
        live_store.upsert_position(conn, conta.id, LivePosition(
            ticker=slot.symbol, quantity=quantity, entry_date=entry_date,
            entry_price=entry_price, capital_allocated=capital_allocated,
            metadata={"side": side}))


def _caixa_sombra(slot) -> float:
    with live_store.live_journal() as conn:
        return round(live_store.load_account(conn, slot.id).cash_sombra, 2)


def _sombra_sem_corretora(monkeypatch, preco, data=None):
    """Robô de sombra: nenhum broker, nenhum processo, e o preço entrando
    pela retaguarda de parquet -- `preco_de_referencia` cai nela porque o
    `conftest` desliga a cotação do terminal na suíte inteira.

    `data` é a data da barra salva, e o default é HOJE de propósito: desde
    2026-09-09 uma barra velha demais é RECUSADA
    (`live_teardown._preco_velho_demais`), então uma data fixa no código faria
    todo teste desta seção mudar de veredito sozinho com a passagem do tempo
    -- a pior espécie de falha, porque ela aparece meses depois num commit que
    não tem nada a ver. Quem QUER medir a recusa passa a data explícita, e ela
    é sempre relativa a hoje (`date.today() - timedelta(...)`), nunca um
    literal."""
    monkeypatch.setattr(live_teardown, "_broker_do_slot",
                        lambda _slot: pytest.fail("sombra não fala com corretora"))
    monkeypatch.setattr(live_teardown, "_processo_do_slot", lambda _sid: (None, None))
    quando = data or date.today().isoformat()
    monkeypatch.setattr("dashboard.robot_view._ultimo_preco",
                        lambda _symbol: (preco, quando))


def test_sombra_vendida_em_futuro_nao_debita_o_nocional_do_caixa(diario, monkeypatch):
    """O caso REAL de 2026-09-09, número por número.

    Short de 1 WDO@ @ 5133,0 (`quantity=-1`, margem de R$150,00 presa na
    entrada), caixa de sombra em R$375,00, saída a 5185,0. São 52 pontos
    CONTRA, e 1 ponto do mini-dólar vale R$10,00:

        375,00 (caixa) + 150,00 (margem devolvida) - 525,50 (perda) = -0,50

    A perda tem tres parcelas, e as duas ultimas sao o que a rota da remocao
    NAO cobrava (2026-09-09): 52 pontos de mercado (R$520,00), 1 tick de
    derrapagem da saida a mercado (0,5 pt x R$10,00 = R$5,00, cobrado no
    PRECO como no motor -- a vendida sai COMPRANDO a 5185,5) e R$0,50 de
    corretagem do round-trip. O caminho normal
    (`IntradayLiveRuntime._on_closed`, sobre um preco que a maquina ja
    deslizou) paga os tres; a remocao pagava zero -- duas rotas para o mesmo
    evento com contabilidade diferente, e a da remocao era a mais generosa.

    O caixa fica NEGATIVO em R$0,50, e isso e' resultado, nao bug: a posicao
    perdeu mais do que a conta tinha. Creditar R$4,50 ali seria a mesma
    familia de erro do item 5.19 em escala menor -- caixa inflado nao chama
    atencao de ninguem e vira tamanho de posicao no pregao seguinte.

    O código antigo devolvia o NOCIONAL com o sinal da quantidade e chamava a
    perda de lucro, fechando em -R$4.706,00 -- caixa de sombra negativo em
    quase 13x o capital do robô."""
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short")
    _sombra_sem_corretora(monkeypatch, 5185.0)

    resultado = live_teardown.remover(SLOT_WDO)

    assert _caixa_sombra(SLOT_WDO) == -0.50
    assert _caixa_sombra(SLOT_WDO) != -4706.00
    assert resultado.posicao_encerrada == {
        "quantity": 1, "side": "short", "price": 5185.5, "pl": -525.50,
        "taxas": 0.50, "deslize": 5.0}
    assert "prejuízo" in resultado.resumo
    # O resumo NOMEIA o custo: sem isso o dono confere contra o extrato e
    # acha que faltou dinheiro. E nomeia os DOIS -- dizer só "R$0,50 de
    # custo" ao lado de um prejuízo em que R$5,00 vieram do tick é a mesma
    # omissão, um nível abaixo.
    assert "já com R$ 5.50 de custo" in resultado.resumo
    assert "R$ 0.50 de taxa e R$ 5.00 de derrapagem" in resultado.resumo


def test_sombra_comprada_em_futuro_nao_infla_o_caixa(diario, monkeypatch):
    """O mesmo defeito pelo lado que NÃO chama atenção.

    Comprada de 1 WDO@ @ 5133,0 marcada a 5185,0: a saída VENDE, e 1 tick de
    derrapagem a leva a 5184,5 -- 51,5 pontos A FAVOR = +R$515,00. A margem
    de R$150,00 volta:

        375,00 + 150,00 + 515,00 - 0,50 (corretagem) = 1.039,50

    O código antigo creditava o nocional inteiro (`5133,00 x 1`) mais R$52,00
    e fechava em R$5.560,00 -- R$5.133,00 de dinheiro simulado que nunca saiu
    do caixa aparecendo como resultado do robô. Um caixa NEGATIVO alguém
    estranha; um caixa 14x maior o robô passa a usar para dimensionar."""
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=1,
                       entry_price=5133.0, capital_allocated=150.0, side="long")
    _sombra_sem_corretora(monkeypatch, 5185.0)

    resultado = live_teardown.remover(SLOT_WDO)

    assert _caixa_sombra(SLOT_WDO) == 1039.50
    assert resultado.posicao_encerrada["pl"] == 514.50


def test_sombra_em_acao_continua_pagando_preco_cheio(diario, monkeypatch):
    """A correção não pode trocar o erro do futuro por um erro na ação.

    Em AÇÃO o preço JÁ é em reais por ação (1 ponto = R$1,00) e o capital
    preso é o lote cheio -- 100 PMAM3 a R$0,14 são R$14,00 de verdade. A
    marcação é R$0,13, a saída VENDE e paga 1 tick (R$0,01) -> executa a
    R$0,12, o que dá -R$2,00 sobre 100 ações:

        30,00 + 14,00 - 2,00 - 0,01 (taxa de bolsa) = 41,99

    Num papel de centavos o tick é o custo DOMINANTE (R$1,00 contra R$0,01 de
    emolumento) -- é o que torna a família gremah sub-tick, e é justamente o
    que a remoção escondia ao marcar pelo preço de tela."""
    slot = daytrade_slot("gremah", "PMAM3", "shadow")
    _conta_com_posicao(slot, cash_sombra=30.0, quantity=100,
                       entry_price=0.14, capital_allocated=14.0, side="long")
    _sombra_sem_corretora(monkeypatch, 0.13)

    resultado = live_teardown.remover(slot)

    assert _caixa_sombra(slot) == 41.99
    # `price` sai de `0,13 - 0,01` em ponto flutuante e vale
    # 0,12000000000000001 -- comparado com `approx` de propósito: arredondar o
    # preço executado aqui seria mais uma diferença entre esta rota e o motor,
    # que também não arredonda a saída de `apply_intraday_slippage`.
    assert resultado.posicao_encerrada["price"] == pytest.approx(0.12)
    assert {k: v for k, v in resultado.posicao_encerrada.items() if k != "price"} == {
        "quantity": 100, "side": "long", "pl": -2.01, "taxas": 0.01,
        "deslize": 1.0}


def test_sombra_vendida_em_acao_devolve_capital_em_vez_de_debitar(diario, monkeypatch):
    """Vendida em AÇÃO tem `quantity=-100` igual à de futuro: o nocional com
    sinal DEBITAVA R$14,00 de um caixa que deveria receber os R$14,00 de
    volta. Marcada a R$0,13, a saída COMPRA e paga 1 tick -> executa de volta
    a R$0,14, resultado bruto ZERO; sobra R$0,01 de taxa de bolsa:
    30 + 14 - 0,01 = 43,99. O tick comeu o ganho inteiro, e é o que a conta
    antiga não mostrava."""
    slot = daytrade_slot("gremah", "PMAM3", "shadow")
    _conta_com_posicao(slot, cash_sombra=30.0, quantity=-100,
                       entry_price=0.14, capital_allocated=14.0, side="short")
    _sombra_sem_corretora(monkeypatch, 0.13)

    live_teardown.remover(slot)

    assert _caixa_sombra(slot) == 43.99


def test_preco_de_saida_prefere_a_cotacao_de_agora_ao_parquet_velho(diario, monkeypatch):
    """O primeiro dos três defeitos, sozinho.

    `_ultimo_preco("WDO@")` devolvia 5185,0 de 28/08 no dia 09/09 -- 12 dias
    de defasagem -- enquanto o mini-dólar negociava a ~5133. Encerrar contra
    aquele número não é estimativa: é marcar a posição em outra quinzena.
    Com a cotação do terminal disponível é ela que vale, e aqui ela é o
    próprio preço de entrada: a marcação dá resultado zero, e o que sobra é o
    custo da saída a mercado -- 1 tick (R$5,00, a vendida sai comprando a
    5133,5) e R$0,50 de corretagem. Caixa = 375 + 150 - 5,50."""
    from dashboard import live_control

    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short")
    _sombra_sem_corretora(monkeypatch, 5185.0,
                          data=(date.today() - timedelta(days=12)).isoformat())
    monkeypatch.setattr(live_control, "_cotacao_do_terminal", lambda _s: 5133.0)

    resultado = live_teardown.remover(SLOT_WDO)

    assert resultado.posicao_encerrada["price"] == 5133.5
    assert _caixa_sombra(SLOT_WDO) == 519.50
    assert not any("NÃO é a cotação de agora" in a for a in resultado.avisos)
    assert not any("NÃO usei o preço salvo" in a for a in resultado.avisos)


def test_sem_preco_nenhum_a_remocao_nao_trava(diario, monkeypatch):
    """A tolerância que o módulo tinha e não podia perder ao trocar a fonte
    do preço: sem terminal E sem parquet, a posição sai pelo próprio preço de
    entrada (marcação sem resultado) em vez de a remoção parar no meio.

    O que entra no caixa é só o custo CONHECIDO da saída -- 1 tick (R$5,00) e
    R$0,50 de corretagem: o preço é que não se sabe, o pedágio de fechar a
    mercado se sabe."""
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short")
    _sombra_sem_corretora(monkeypatch, None)

    resultado = live_teardown.remover(SLOT_WDO)

    assert resultado.posicao_encerrada == {
        "quantity": 1, "side": "short", "price": 5133.5, "pl": -5.50,
        "taxas": 0.50, "deslize": 5.0}
    assert _caixa_sombra(SLOT_WDO) == 519.50
    assert resultado.removido
    # Não travar não é o mesmo que ficar calado: "resultado zero" aqui
    # significa "não sei", e o dono precisa ler isso.
    assert any("não consegui preço nenhum" in a for a in resultado.avisos)


def test_valor_do_ponto_desconhecido_nao_chuta_resultado(diario, monkeypatch):
    """Futuro cujo valor do ponto não se descobre (catálogo mudou desde que a
    conta foi criada): o capital preso volta -- esse número é certo --, mas o
    RESULTADO não entra no caixa. Chutar 1,0 erraria por 10x num WDO@, e o
    dono precisa saber que o número não foi apurado."""
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short")
    _sombra_sem_corretora(monkeypatch, 5185.0)
    monkeypatch.setattr(live_teardown, "_valor_do_ponto_brl",
                        lambda _symbol: None)

    resultado = live_teardown.remover(SLOT_WDO)

    assert _caixa_sombra(SLOT_WDO) == 525.00          # só a margem devolvida
    assert resultado.posicao_encerrada["pl"] is None
    assert any("não sei quanto vale 1 ponto" in a for a in resultado.avisos)
    assert resultado.removido, "não apurar o resultado não pode travar a remoção"


def test_capital_comprometido_sem_capital_allocated_usa_a_margem():
    """Linha antiga, gravada antes de `capital_allocated` existir. A
    retaguarda ramifica igual: margem em futuro, preço cheio em ação --
    nunca o nocional do contrato."""
    futuro = LivePosition(ticker="WDO@", quantity=-2, entry_date=date(2026, 9, 9),
                          entry_price=5133.0, capital_allocated=0.0)
    acao = LivePosition(ticker="PMAM3", quantity=-100, entry_date=date(2026, 9, 9),
                        entry_price=0.14, capital_allocated=0.0)

    assert live_teardown._capital_comprometido(futuro, "WDO@") == 300.0
    assert live_teardown._capital_comprometido(acao, "PMAM3") == pytest.approx(14.0)


def test_pl_estimado_de_uma_vendida_do_banco_aparece_no_popup():
    """O número que o dono lê ANTES de confirmar. Com `quantity` negativa (é
    assim que uma vendida é gravada) o `qtd <= 0` de antes devolvia `None` e
    a tela apagava a linha do resultado -- no lado em que ela mais importa.
    Sem o valor do ponto, mostraria R$52,00 no lugar de R$520,00."""
    vendida = live_teardown.Pendencias(
        slot_id="x", label="X", symbol="WDO@", modo="shadow", processo_pid=None,
        caixa=375.0, posicao={"side": "short", "price": 5133.0, "quantity": -1},
        preco_atual=5185.0)

    # A vendida sai COMPRANDO: 5185,0 + 1 tick (0,5 pt) = 5185,5, ou seja
    # -525,00 brutos, menos R$0,50 de corretagem do round-trip de 1 contrato
    # (`FUTURES_FEE_ROUND_TRIP_BRL`) -- os mesmos dois custos que o motor
    # cobra em `_on_closed`.
    assert vendida.pl_estimado == -525.50


def test_capital_em_posicao_nao_conta_nocional_de_futuro(diario):
    """Portão de caixa (`live_control.start` / `operacao_iniciar`): o que está
    comprometido num contrato de WDO@ é a MARGEM de R$150,00, não os ~R$5.100
    de nocional. Contar o nocional inflava o portão em 34x e deixava passar
    robô que o piso deveria barrar."""
    from dashboard import live_control

    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short")
    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, SLOT_WDO.id)

    assert live_control.capital_em_posicao(conta) == 150.0
    assert live_control.capital_em_posicao(None) == 0.0


# ---------- o valor do ponto é do INSTRUMENTO, não do robô ------------------
#
# Até 2026-09-09 este módulo lia `point_value_brl` do ROBÔ do slot
# (`registry._KWARGS_PADRAO`). Lugar errado por duas razões que aparecem
# juntas: dois robôs no mesmo símbolo têm obrigatoriamente o mesmo valor de
# ponto, e um robô de futuro NOVO que esquecesse o parâmetro fazia a remoção
# responder "não sei quanto vale 1 ponto" e deixar de apurar o resultado.

def test_valor_do_ponto_vem_do_perfil_do_instrumento():
    assert live_teardown._valor_do_ponto_brl("WDO@") == 10.0
    assert live_teardown._valor_do_ponto_brl("WIN@") == 0.20
    assert live_teardown._valor_do_ponto_brl("PMAM3") == 1.0
    # Símbolo sem perfil nenhum só pode ser ação (futuro sem perfil não é
    # sequer iniciável pelo painel): 1 ponto = R$1,00.
    assert live_teardown._valor_do_ponto_brl("ABEV3") == 1.0


def test_resultado_apurado_mesmo_com_robo_fora_do_catalogo(diario, monkeypatch):
    """Uma conta criada por um robô que depois saiu do registry (ou um robô
    de futuro novo que esqueceu o parâmetro) continua tendo o resultado
    apurado: o INSTRUMENTO não mudou. Antes disto, o `get_daytrade_robot`
    aqui dentro levantava `KeyError`, o valor do ponto virava `None` e a
    remoção creditava só a margem, avisando "não sei quanto vale 1 ponto"."""
    slot = daytrade_slot("robo_extinto", "WDO@", "shadow")
    _conta_com_posicao(slot, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short")
    _sombra_sem_corretora(monkeypatch, 5185.0)

    resultado = live_teardown.remover(slot)

    assert resultado.posicao_encerrada["pl"] == -525.50
    assert not any("não sei quanto vale 1 ponto" in a for a in resultado.avisos)


# ---------- o custo é o MESMO do fechamento normal --------------------------

def test_custo_da_remocao_e_identico_ao_que_o_motor_cobra_no_fechamento():
    """A rota de remoção creditava BRUTO enquanto `IntradayLiveRuntime.
    _on_closed` credita líquido (`IntradayTrade.pnl_brl` subtrai
    `fees_total`). Duas rotas para o mesmo evento com contabilidade
    diferente. Aqui as duas contas são comparadas número a número: a do
    módulo, montada sem terminal a partir do perfil, contra a que o motor
    monta via `config_for` com a economia lida do MT5."""
    from backtest.intraday.costs import fees_round_trip_brl
    from backtest.intraday.profiles import config_for, profile_for

    casos = [
        ("WDO@", 1, 5133.0, 5185.0, dict(trade_tick_value=0.01, trade_tick_size=0.001,
                                         initial_capital=375.0)),
        ("WIN@", 2, 141_000.0, 141_250.0, dict(trade_tick_value=0.2, trade_tick_size=1.0,
                                               initial_capital=1000.0)),
        ("PMAM3", 100, 0.14, 0.13, dict(trade_tick_value=0.01, trade_tick_size=0.01,
                                        preco_atual=0.14)),
    ]
    for symbol, qtd, entrada, saida, economia in casos:
        do_motor = fees_round_trip_brl(
            qtd, entrada, saida, config_for(profile_for(symbol), **economia).costs)
        assert live_teardown._custos_de_saida(symbol, qtd, entrada, saida) == \
            pytest.approx(round(do_motor, 2)), symbol


def test_custos_de_saida_de_simbolo_sem_perfil_e_none_e_nao_zero():
    """`None` = "não sei o que este instrumento cobra"; zero afirmaria que
    ele é de graça. Quem chama trata `None` como zero de propósito (não pode
    travar a remoção), mas a diferença precisa existir na função."""
    assert live_teardown._custos_de_saida("XPTO99", 1, 10.0, 11.0) is None


# ---------- o I/O de preço no clique de remover -----------------------------

def _conta_preco(monkeypatch) -> list[str]:
    """Registra cada ida ao `preco_de_referencia` -- é o I/O que a correção
    de 2026-09-09 introduziu num caminho que era 100% offline."""
    from dashboard import live_control

    chamadas: list[str] = []
    real = live_control.preco_de_referencia

    def espiao(symbol):
        chamadas.append(symbol)
        return real(symbol)

    monkeypatch.setattr(live_control, "preco_de_referencia", espiao)
    return chamadas


def test_sem_posicao_aberta_a_remocao_de_sombra_nao_consulta_preco(diario, monkeypatch):
    """O limite que torna o I/O novo aceitável: sem posição não há o que
    marcar a mercado, então a consulta não mudaria nada -- e por isso não
    acontece. É o caso da esmagadora maioria das remoções."""
    _conta(SLOT_SOMBRA, cash=0.0)
    chamadas = _conta_preco(monkeypatch)
    monkeypatch.setattr(live_teardown, "_broker_do_slot",
                        lambda _slot: pytest.fail("sombra não fala com corretora"))
    monkeypatch.setattr(live_teardown, "_processo_do_slot", lambda _sid: (None, None))

    live_teardown.remover(SLOT_SOMBRA, apagar_historico=True)

    assert chamadas == [], (
        "remover um robô de sombra SEM posição aberta tem de continuar 100% "
        f"offline -- consultou preço {len(chamadas)}x")


def test_com_posicao_aberta_o_preco_e_consultado_e_o_custo_e_conhecido(diario, monkeypatch):
    """A contrapartida, medida em vez de suposta: com posição aberta o preço
    é pedido, e o custo do clique é conhecido (o cache de 30s de
    `preco_de_referencia` faz a segunda chamada não ir ao terminal). Se algum
    dia este número crescer, o teste mostra."""
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short")
    _sombra_sem_corretora(monkeypatch, 5185.0)
    chamadas = _conta_preco(monkeypatch)

    live_teardown.remover(SLOT_WDO)

    assert chamadas == ["WDO@", "WDO@"], (
        "uma por `inspecionar()` e uma pela releitura de `_encerrar_posicao_"
        "sombra()` -- a segunda é acerto do cache de 30s do painel")


def test_preco_de_parquet_recente_vira_aviso_em_vez_de_silencio(diario, monkeypatch):
    """Defeito nº 3 do item 5.19, fechado pelo outro lado: quando o terminal
    não responde, a retaguarda de parquet pode ter dias de defasagem. Dentro
    do limite de idade a barra ainda VALE (é melhor estimativa do que nada),
    mas o dono não pode descobrir sozinho que o número que entrou no caixa é
    de outro dia."""
    ontem = (date.today() - timedelta(days=1)).isoformat()
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short",
                       entry_date=date.today() - timedelta(days=1))
    _sombra_sem_corretora(monkeypatch, 5185.0, data=ontem)

    resultado = live_teardown.remover(SLOT_WDO)

    assert any("NÃO é a cotação de agora" in a and ontem in a
               for a in resultado.avisos), resultado.avisos
    # Aviso, não recusa: o preço FOI usado (a perda de 52 pontos entrou).
    assert resultado.posicao_encerrada["pl"] == -525.50
    assert resultado.removido


# ---------- preço velho DEMAIS é recusado, não só avisado -------------------
#
# Risco nº 4 deixado em aberto pela correção de 2026-09-09: a rotina caía no
# parquet, que já esteve **12 dias velho** (metade do bug original), e apenas
# AVISAVA. Aviso é tarde: ele conta ao dono que o caixa recebeu um número de
# outra quinzena DEPOIS de o número estar lá, e ninguém desfaz um crédito
# lendo um aviso.
#
# A saída não é travar a remoção -- travar é o outro modo de falha (robô
# preso no painel, ativo bloqueado, por causa de um MT5 que o dono pode nem
# conseguir abrir). É recusar o PREÇO e cair no caminho que o módulo já tinha
# para "não veio preço nenhum": encerra pelo próprio preço de entrada, credita
# só o custo conhecido da saída, e diz por quê.

def test_barra_anterior_a_propria_posicao_e_recusada(diario, monkeypatch):
    """O critério que não tem constante para discutir, e a forma exata do caso
    real (barra de 28/08 marcando uma posição aberta em 09/09): não existe
    preço de SAÍDA anterior à ENTRADA. Não é uma marcação velha, é uma
    impossibilidade lógica.

    Encerra pelo preço de entrada: caixa = 375 + 150 - 5,00 (1 tick) - 0,50
    (corretagem) = 519,50. Sem a recusa seriam -R$0,50 (52 pontos de um
    movimento que esta posição nunca viveu)."""
    hoje = date.today()
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short",
                       entry_date=hoje)
    _sombra_sem_corretora(monkeypatch, 5185.0,
                          data=(hoje - timedelta(days=1)).isoformat())

    resultado = live_teardown.remover(SLOT_WDO)

    assert _caixa_sombra(SLOT_WDO) == 519.50
    assert resultado.posicao_encerrada["pl"] == -5.50
    assert any("NÃO usei o preço salvo" in a and "ANTERIOR a abertura" in a
               for a in resultado.avisos), resultado.avisos
    # Recusar o PREÇO nunca pode virar recusar a REMOÇÃO -- o robô preso no
    # painel é o outro modo de falha, e é o que o dono clicou para evitar.
    assert resultado.removido


def test_barra_velha_demais_e_recusada_mesmo_com_a_posicao_igualmente_velha(
        diario, monkeypatch):
    """O caso que o critério da entrada não pega: robô morto há semanas, em
    que a posição e o parquet envelheceram JUNTOS (a barra é posterior à
    entrada, então nada é logicamente impossível -- só velho). Aqui entra o
    limite de idade em dias corridos."""
    hoje = date.today()
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short",
                       entry_date=hoje - timedelta(days=30))
    _sombra_sem_corretora(monkeypatch, 5185.0,
                          data=(hoje - timedelta(days=29)).isoformat())

    resultado = live_teardown.remover(SLOT_WDO)

    assert _caixa_sombra(SLOT_WDO) == 519.50
    assert any("NÃO usei o preço salvo" in a and "29 dias atras" in a
               for a in resultado.avisos), resultado.avisos
    assert resultado.removido


def test_o_popup_recusa_o_mesmo_preco_que_a_remocao_vai_recusar(diario, monkeypatch):
    """As duas pontas do mesmo evento (a família de bug 5.7/5.19, aqui no eixo
    do PREÇO). Sem isto o diálogo estimava "prejuízo de R$525,50" por uma
    barra que a remoção ia jogar fora um segundo depois, creditando outra
    coisa -- e o dono confirmaria com base num número que nunca existiu."""
    hoje = date.today()
    _conta_com_posicao(SLOT_WDO, cash_sombra=375.0, quantity=-1,
                       entry_price=5133.0, capital_allocated=150.0, side="short",
                       entry_date=hoje)
    _sombra_sem_corretora(monkeypatch, 5185.0,
                          data=(hoje - timedelta(days=1)).isoformat())

    pend = live_teardown.inspecionar(SLOT_WDO)

    assert pend.preco_atual is None and pend.pl_estimado is None
    # "Não achei preço" e "achei e não sirvo dele" são coisas diferentes, e a
    # tela tem texto diferente para cada uma.
    assert pend.preco_recusado and "ANTERIOR a abertura" in pend.preco_recusado


@pytest.mark.parametrize("origem, entrada, esperado_recusa", [
    ("agora", date(2026, 9, 9), False),          # cotação do terminal: sempre serve
    ("", date(2026, 9, 9), False),               # não veio preço: nada a julgar
    ("lixo", date(2026, 9, 9), False),           # data ilegível não autoriza recusar
    ("2026-09-09", date(2026, 9, 9), False),     # mesma sessão
    ("2026-09-08", date(2026, 9, 9), True),      # anterior à entrada
    ("2026-09-04", date(2026, 9, 1), False),     # 5 dias: no limite, ainda vale
    ("2026-09-03", date(2026, 9, 1), True),      # 6 dias: fora
])
def test_a_regra_de_idade_do_preco_em_tabela(origem, entrada, esperado_recusa):
    """A regra isolada, com o `hoje` fixo -- é o único jeito de fixar a
    fronteira de 5 dias sem que o teste mude de veredito com o calendário."""
    motivo = live_teardown._preco_velho_demais(
        origem, entrada, hoje=date(2026, 9, 9))
    assert (motivo is not None) is esperado_recusa, motivo


# ---------- a derrapagem: quem paga é quem NÃO executou ---------------------
#
# Risco nº 3 deixado em aberto pela correção de 2026-09-09. O argumento de
# quem deixou assim era que aqui "não há execução nenhuma, e piorar o preço em
# 1 tick inventaria um fill que ninguém observou". A metade certa desse
# argumento vale para a rota REAL, que era justamente a que não precisava
# dela; para a rota de SOMBRA ele se inverte -- não cobrar o tick não é
# "deixar de inventar um fill", é inventar um fill PERFEITO, ao preço de tela,
# que é a única coisa que a corretora garantidamente não faz.
#
# Quem já tinha decidido isto é o motor: `machine._close_position` desliza o
# preço e SÓ o substitui pelo da corretora quando existe execução real. Ou
# seja, fechar a mesma posição em sombra pelo caminho normal já pagava o tick,
# e remover o robô era a única rota que não pagava.

def test_a_derrapagem_e_cobrada_na_sombra_e_nao_no_real(diario, monkeypatch):
    """As duas rotas, lado a lado, sobre a MESMA posição e o MESMO preço.

    Sombra: 0,13 é uma marcação, a saída vende e executa a 0,12 -> -R$2,00 de
    bruto. Real: 0,13 é o `avg_price` que a corretora devolveu, a derrapagem
    já está dentro dele -> -R$1,00 de bruto. Cobrar nos dois seria contar o
    mesmo custo duas vezes num deles; não cobrar em nenhum (o estado até
    2026-09-09) era o caso em que a sombra rendia mais que o motor."""
    slot_sombra = daytrade_slot("gremah", "PMAM3", "shadow")
    _conta_com_posicao(slot_sombra, cash_sombra=30.0, quantity=100,
                       entry_price=0.14, capital_allocated=14.0, side="long")
    _sombra_sem_corretora(monkeypatch, 0.13)
    da_sombra = live_teardown.remover(slot_sombra)

    _conta(SLOT_REAL, cash=30.0)
    broker = _BrokerFalso(ordens=[], posicao={"side": "long", "price": 0.14,
                                              "quantity": 100}, preco=0.13)
    _monta(monkeypatch, broker=broker)
    do_real = live_teardown.remover(SLOT_REAL, apagar_historico=True)

    assert da_sombra.posicao_encerrada["price"] == pytest.approx(0.12), \
        "sombra não observou fill nenhum: o preço tem de ser MODELADO"
    assert do_real.posicao_encerrada["price"] == 0.13, \
        "real observou o fill: piorá-lo cobraria o mesmo tick duas vezes"
    assert da_sombra.posicao_encerrada["pl"] == -2.01
    assert do_real.posicao_encerrada["pl"] == -1.01


def test_a_sombra_cobra_o_MESMO_tick_que_o_motor_cobraria(diario, monkeypatch):
    """A afirmação que sustenta a decisão, medida em vez de suposta: o preço
    de execução que a remoção modela é o MESMO que `machine._close_position`
    produziria em sombra para a mesma saída a mercado -- `apply_intraday_
    slippage` sobre o modelo do símbolo, com o `slippage_ticks` do motor.

    Sem esta amarração, um dia alguém muda `IntradayCostModel.slippage_ticks`
    e as duas rotas voltam a divergir em silêncio, que é a família de bug
    5.7/5.19 vista pelo lado do custo."""
    from dataclasses import replace

    from backtest.intraday.costs import IntradayCostModel, apply_intraday_slippage
    from backtest.intraday.profiles import cost_model_from_profile, profile_for

    casos = [("WDO@", 5185.0, "short", "buy"), ("WDO@", 5185.0, "long", "sell"),
             ("WIN@", 141_000.0, "short", "buy"), ("PMAM3", 0.13, "long", "sell")]
    for symbol, marcado, lado, lado_da_ordem in casos:
        modelo = replace(cost_model_from_profile(profile_for(symbol)),
                         slippage_ticks=IntradayCostModel.slippage_ticks)
        assert live_teardown._preco_de_execucao_a_mercado(symbol, marcado, lado) == \
            pytest.approx(apply_intraday_slippage(marcado, lado_da_ordem, modelo)), \
            f"{symbol}/{lado}"


def test_simbolo_sem_perfil_nao_chuta_o_tick():
    """Sem perfil não há passo de preço, e chutar erraria por 50x entre uma
    ação (R$0,01) e um WDO@ (0,5 pt). Devolver a marcação intacta é a mesma
    escolha que `_custos_de_saida` faz com `None`: não afirmar o que não se
    sabe."""
    assert live_teardown._preco_de_execucao_a_mercado("XPTO99", 10.0, "long") == 10.0


# ---------- o valor do ponto não pode chegar por parâmetro ------------------

def test_o_valor_do_ponto_do_popup_sai_do_SIMBOLO_e_nao_de_quem_construiu():
    """Risco nº 5. `pl_estimado` fazia uma conta com DUAS fontes: o
    multiplicador vinha de um campo do dataclass (default 1,0) e as taxas, do
    perfil resolvido por `symbol`. Um chamador que passasse os dois
    incoerentes recebia um número MISTO -- pontos contados como reais no
    bruto, tarifa de contrato de futuro no desconto --, que é o modo de falha
    do item 5.19 pelo lado da entrada.

    Com a propriedade derivada, a incoerência deixa de ser possível em vez de
    depender de disciplina: não há mais parâmetro para digitar errado."""
    import dataclasses

    campos = {f.name for f in dataclasses.fields(live_teardown.Pendencias)}
    assert "valor_do_ponto" not in campos, \
        "enquanto for CAMPO, alguém pode passá-lo em desacordo com o símbolo"

    with pytest.raises(TypeError):
        live_teardown.Pendencias(
            slot_id="x", label="X", symbol="WDO@", modo="shadow",
            processo_pid=None, caixa=0.0, valor_do_ponto=1.0)

    wdo = live_teardown.Pendencias(
        slot_id="x", label="X", symbol="WDO@", modo="shadow", processo_pid=None,
        caixa=0.0)
    acao = live_teardown.Pendencias(
        slot_id="x", label="X", symbol="PMAM3", modo="shadow", processo_pid=None,
        caixa=0.0)

    assert wdo.valor_do_ponto == 10.0 and acao.valor_do_ponto == 1.0


def test_multiplicador_e_tarifa_do_popup_saem_do_MESMO_perfil():
    """A propriedade que a correção compra, dita como invariante: as duas
    pontas da conta de `pl_estimado` -- o multiplicador de ponto e a tarifa --
    leem o mesmo `profile_for(symbol)`. Trocar o símbolo move as duas juntas;
    não há combinação de argumentos que mova só uma."""
    from backtest.intraday.profiles import profile_for

    for symbol in ("WDO@", "WIN@", "PMAM3"):
        pend = live_teardown.Pendencias(
            slot_id="x", label="X", symbol=symbol, modo="shadow",
            processo_pid=None, caixa=0.0)
        perfil = profile_for(symbol)
        assert pend.valor_do_ponto == pytest.approx(float(perfil.point_value_brl))
        # a tarifa da MESMA conta vem do MESMO perfil
        assert live_teardown._custos_de_saida(symbol, 1, 100.0, 100.0) == \
            pytest.approx(round(perfil.fee_round_trip_brl
                                + perfil.exchange_fee_pct_per_leg * 200.0, 2))
