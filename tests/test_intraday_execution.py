"""Testes de `live/intraday_execution.py::MT5IntradayExecution` -- foco na
reconciliacao por historico da corretora (gap medido ao vivo em 2026-09-04,
slot `dt-wdo_grid_reload_maker-wdo@-live`): uma ordem-limite de entrada pode
preencher E fechar dentro do MESMO intervalo de poll do supervisor, e uma
tentativa de fechamento pode parecer recusada mas ter executado de verdade.
`limit_fill`/`exit_market` sozinhos so' enxergam o que a leitura de posicao
mostra AGORA -- estes testes exercitam os dois metodos que consultam o
HISTORICO quando essa leitura sozinha nao basta: `resolve_orphaned_entry`
(lado da entrada) e `_resolve_exit_from_history` (lado da saida).

Broker falso minimo (duck-typed, sem passar pelo pacote `MetaTrader5` --
ver `tests/test_live_broker_mt5.py` para os testes que exercitam a TRADUCAO
de/para o pacote real): so' precisa responder `order_history_state`/
`deals_for_position` do jeito tri-estado que os dois metodos exigem.
"""
from __future__ import annotations

import pytest

from live.intraday_execution import MT5IntradayExecution


class _FakeBroker:
    """`estados`: ticket (str) -> resposta de `order_history_state`.
    `deals`: position_id -> resposta de `deals_for_position`. Ticket/
    position_id ausente do dict devolve "nao configurado" (`ok=False`) --
    o mesmo default conservador de `_BrokerComHistorico` em
    `tests/test_intraday_live_runtime.py`, para nenhum teste esquecer de
    configurar e acabar provando um cenario que nao pretendia."""

    def __init__(self, estados=None, deals=None):
        self.estados = estados or {}
        self.deals = deals or {}
        self.consultas_estado: list = []
        self.consultas_deals: list = []

    def order_history_state(self, ticket):
        self.consultas_estado.append(str(ticket))
        return self.estados.get(str(ticket), {"ok": False, "state": None,
                                               "position_id": None, "note": "nao configurado"})

    def deals_for_position(self, position_id):
        self.consultas_deals.append(position_id)
        return self.deals.get(position_id, {"ok": False, "deals": None, "note": "nao configurado"})


def _entrada(price, quantity, time=100, comment=""):
    return {"entry": 0, "price": price, "quantity": quantity, "profit": 0.0,
            "commission": 0.0, "swap": 0.0, "fee": 0.0, "time": time, "comment": comment}


def _saida(price, quantity, time=200, comment=""):
    return {"entry": 1, "price": price, "quantity": quantity, "profit": 0.0,
            "commission": 0.0, "swap": 0.0, "fee": 0.0, "time": time, "comment": comment}


# ---------- resolve_orphaned_entry --------------------------------------

def test_sem_tickets_nao_consulta_nada():
    execu = MT5IntradayExecution(broker=_FakeBroker(), symbol="PMAM3")
    assert execu.resolve_orphaned_entry([]) is None
    assert execu.resolve_orphaned_entry([None, ""]) is None


def test_ticket_ainda_pendente_fica_como_esta():
    broker = _FakeBroker(estados={"1001": {"ok": True, "state": "pending",
                                           "position_id": None, "note": ""}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001"]) is None
    assert broker.consultas_estado == ["1001"]
    assert broker.consultas_deals == [], "ainda pendente -- nao ha' motivo pra olhar deals"


def test_consulta_de_estado_falhou_fica_como_esta_nunca_declara_morta():
    broker = _FakeBroker(estados={"1001": {"ok": False, "state": None,
                                           "position_id": None, "note": "terminal fora do ar"}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001"]) is None


def test_cancelada_sem_position_id_e_sem_nenhum_deal_e_morta():
    broker = _FakeBroker(estados={"1001": {"ok": True, "state": "canceled",
                                           "position_id": None, "note": ""}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    resultado = execu.resolve_orphaned_entry(["1001"])

    assert resultado == {"outcome": "dead"}
    assert broker.consultas_deals == [], "sem position_id, nao ha' posicao pra procurar"


def test_expirada_e_morta_mesma_regra_que_cancelada():
    broker = _FakeBroker(estados={"1001": {"ok": True, "state": "expired",
                                           "position_id": None, "note": ""}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001"]) == {"outcome": "dead"}


def test_filled_mas_deal_ainda_nao_chegou_no_historico_fica_como_esta():
    """O proprio registro da ordem diz "preencheu" (`state="filled"`), mas
    `deals_for_position` ainda nao mostra o deal de entrada -- atraso de
    replicacao, nao ausencia. NUNCA declara "dead" so' porque os deals
    ainda nao chegaram."""
    broker = _FakeBroker(
        estados={"1001": {"ok": True, "state": "filled", "position_id": 909, "note": ""}},
        deals={909: {"ok": True, "deals": [], "note": ""}},
    )
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001"]) is None
    assert broker.consultas_deals == [909]


def test_consulta_de_deals_falhou_fica_como_esta():
    broker = _FakeBroker(
        estados={"1001": {"ok": True, "state": "filled", "position_id": 909, "note": ""}},
        deals={909: {"ok": False, "deals": None, "note": "terminal fora do ar"}},
    )
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001"]) is None


def test_preencheu_e_continua_aberto_devolve_already_open():
    """So' o deal de ENTRADA existe -- a posicao continua aberta na
    corretora (ou so' fechou parcialmente). O caminho normal
    (`limit_fill`, crescimento de posicao) descobre isso sozinho; este
    metodo nao antecipa nada."""
    broker = _FakeBroker(
        estados={"1001": {"ok": True, "state": "filled", "position_id": 909, "note": ""}},
        deals={909: {"ok": True, "deals": [_entrada(9.80, 1)], "note": ""}},
    )
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001"]) == {"outcome": "already_open"}


def test_saida_parcial_nao_fecha_tudo_ainda_e_already_open():
    broker = _FakeBroker(
        estados={"1001": {"ok": True, "state": "filled", "position_id": 909, "note": ""}},
        deals={909: {"ok": True, "deals": [
            _entrada(9.80, 2), _saida(9.85, 1),  # so' 1 dos 2 fechou
        ], "note": ""}},
    )
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001"]) == {"outcome": "already_open"}


def test_round_trip_devolve_precos_reais_nunca_o_nivel_teorico():
    """Caso exato medido ao vivo: preenche @ 9,80, fecha pelo alvo com 1
    tick de deslize CONTRA o robo (9,89, nao o teorico 9,90)."""
    broker = _FakeBroker(
        estados={"1001": {"ok": True, "state": "filled", "position_id": 909, "note": ""}},
        deals={909: {"ok": True, "deals": [
            _entrada(9.80, 1, time=100),
            _saida(9.89, 1, time=101, comment="[tp 9.9000]"),
        ], "note": ""}},
    )
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    resultado = execu.resolve_orphaned_entry(["1001"])

    assert resultado == {
        "outcome": "round_trip",
        "entry_price": 9.80, "entry_qty": 1,
        "exit_price": 9.89, "exit_qty": 1,
        "exit_comment": "[tp 9.9000]",
    }


def test_round_trip_com_multiplos_deals_de_entrada_usa_media_ponderada():
    """Entrada fatiada (2 deals de entrada em precos diferentes) -- o
    preco reconciliado tem de ser a media PONDERADA pela quantidade de
    cada fatia, igual ao que a leitura de posicao normal (`limit_fill`)
    ja faz via `open_position`."""
    broker = _FakeBroker(
        estados={"1001": {"ok": True, "state": "filled", "position_id": 909, "note": ""}},
        deals={909: {"ok": True, "deals": [
            _entrada(9.80, 1, time=100),
            _entrada(9.90, 1, time=101),
            _saida(10.00, 2, time=102),
        ], "note": ""}},
    )
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    resultado = execu.resolve_orphaned_entry(["1001"])

    assert resultado["entry_price"] == pytest.approx(9.85)  # (9.80*1 + 9.90*1) / 2
    assert resultado["entry_qty"] == 2
    assert resultado["exit_price"] == 10.00
    assert resultado["exit_qty"] == 2


def test_round_trip_pega_o_deal_de_saida_mais_recente_quando_ha_mais_de_um():
    broker = _FakeBroker(
        estados={"1001": {"ok": True, "state": "filled", "position_id": 909, "note": ""}},
        deals={909: {"ok": True, "deals": [
            _entrada(9.80, 1, time=100),
            _saida(9.85, 1, time=150, comment="parcial-velha"),
            _saida(9.89, 1, time=200, comment="[tp 9.9000]"),
        ], "note": ""}},
    )
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    resultado = execu.resolve_orphaned_entry(["1001"])

    # exit_price agregado (media ponderada das DUAS saidas, 1+1=2 unidades)
    assert resultado["exit_qty"] == 2
    assert resultado["exit_comment"] == "[tp 9.9000]", "comentario vem do deal mais RECENTE"


def test_qualquer_filho_ainda_pendente_bloqueia_tudo_para_ordem_dividida():
    """Entrada dividida (2 filhos): um ja terminou (preencheu) mas o outro
    continua no book -- nao pode reconciliar nada ainda, a ordem inteira
    continua vigiada."""
    broker = _FakeBroker(estados={
        "1001": {"ok": True, "state": "filled", "position_id": 909, "note": ""},
        "1002": {"ok": True, "state": "pending", "position_id": None, "note": ""},
    })
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001", "1002"]) is None
    assert broker.consultas_deals == [], "nao chega a olhar deals com um filho ainda vivo"


def test_broker_sem_os_metodos_novos_nao_reconcilia_nada():
    """Dublê antigo (sem `order_history_state`/`deals_for_position`, ex.:
    `PaperBroker` de teste) -- `resolve_orphaned_entry` degrada para "nada
    a reconciliar" em vez de levantar `AttributeError`."""
    class _BrokerAntigo:
        pass

    execu = MT5IntradayExecution(broker=_BrokerAntigo(), symbol="PMAM3")

    assert execu.resolve_orphaned_entry(["1001"]) is None


# ---------- _resolve_exit_from_history ----------------------------------

def test_resolve_exit_from_history_sem_last_entry_ref_devolve_none():
    execu = MT5IntradayExecution(broker=_FakeBroker(), symbol="PMAM3")
    execu.last_entry_ref = None

    assert execu._resolve_exit_from_history() is None


def test_resolve_exit_from_history_sem_deal_de_saida_devolve_none():
    broker = _FakeBroker(deals={501: {"ok": True, "deals": [_entrada(9.80, 1)], "note": ""}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")
    execu.last_entry_ref = 501

    assert execu._resolve_exit_from_history() is None


def test_resolve_exit_from_history_consulta_falhou_devolve_none():
    broker = _FakeBroker(deals={501: {"ok": False, "deals": None, "note": "falhou"}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")
    execu.last_entry_ref = 501

    assert execu._resolve_exit_from_history() is None


def test_resolve_exit_from_history_devolve_preco_real_do_deal():
    """O caso exato do segundo gap medido ao vivo: fechamento que pareceu
    recusado mas executou de verdade, a um preco PIOR que o alvo teorico."""
    broker = _FakeBroker(deals={501: {"ok": True, "deals": [
        _saida(9.85, 1, time=200, comment="meta-live"),
    ], "note": ""}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")
    execu.last_entry_ref = 501

    resultado = execu._resolve_exit_from_history()

    assert resultado == {"price": 9.85, "order": None}
    assert broker.consultas_deals == [501]


def test_resolve_exit_from_history_pega_o_deal_mais_recente():
    broker = _FakeBroker(deals={501: {"ok": True, "deals": [
        _saida(9.80, 1, time=150),
        _saida(9.85, 1, time=200),
    ], "note": ""}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")
    execu.last_entry_ref = 501

    assert execu._resolve_exit_from_history()["price"] == 9.85


def test_resolve_exit_from_history_preco_zero_e_tratado_como_nao_confirmado():
    broker = _FakeBroker(deals={501: {"ok": True, "deals": [
        _saida(0.0, 1, time=200),
    ], "note": ""}})
    execu = MT5IntradayExecution(broker=broker, symbol="PMAM3")
    execu.last_entry_ref = 501

    assert execu._resolve_exit_from_history() is None


def test_resolve_exit_from_history_broker_sem_o_metodo_devolve_none():
    class _BrokerAntigo:
        pass

    execu = MT5IntradayExecution(broker=_BrokerAntigo(), symbol="PMAM3")
    execu.last_entry_ref = 501

    assert execu._resolve_exit_from_history() is None
