"""N robôs de day trade no painel (2026-08-22): slots dinâmicos, a regra de
sugestão de capital, e a caixa de avisos.

O que cada bloco protege, em ordem de gravidade se quebrar:
  1. dois robôs nunca no mesmo ativo (conta NETTING: as posições se fundiriam
     na corretora e os dois caixas passariam a mentir);
  2. cada robô num processo/conta/caixa próprios, com `magic` distinto;
  3. o aviso de capital sai UMA vez por ativo e nunca mais;
  4. a regra de sugestão desconta o que o dono já aportou nos outros robôs.
"""
from __future__ import annotations

import pytest

from core.config import daytrade_magic, daytrade_slot, daytrade_slot_id, slot_by_id
from journal import live_store
from strategy.daytrade.enxame import Candidato, avaliar_sugestao
from strategy.daytrade.registry import get_daytrade_robot, symbols_for_robot


# ---------- identidade do slot (pura, sem banco) ---------------------------

def test_id_do_slot_carrega_robo_e_ativo():
    """O id É a identidade: `slot_by_id` reconstrói o slot sem consultar banco
    nenhum — é isso que deixa `run_live.py --slot dt-gremah-pmam3` subir como
    processo isolado, sem depender do dashboard estar de pé."""
    assert daytrade_slot_id("gremah", "PMAM3") == "dt-gremah-pmam3"

    slot = slot_by_id("dt-gremah-klbn4")
    assert (slot.robot_key, slot.symbol, slot.kind) == ("gremah", "KLBN4", "intraday")
    assert slot.is_intraday and slot.is_dynamic


def test_slot_estatico_nao_e_removivel():
    assert slot_by_id("swing").is_dynamic is False


def test_id_recusa_hifen_no_robo_ou_ativo():
    """O hífen é o separador — um valor que o contenha tornaria o id ambíguo
    para `slot_by_id` desmontar de volta."""
    with pytest.raises(ValueError, match="separador"):
        daytrade_slot_id("gre-mah", "PMAM3")
    with pytest.raises(ValueError, match="separador"):
        daytrade_slot_id("gremah", "PM-AM3")


def test_magic_e_estavel_e_distinto_por_slot():
    """Estável entre reinícios (senão o robô perde de vista as próprias ordens
    ao voltar) e distinto entre slots (senão dois robôs leem as ordens um do
    outro como suas)."""
    assert daytrade_magic("dt-gremah-pmam3") == daytrade_magic("dt-gremah-pmam3")
    magics = {daytrade_magic(daytrade_slot_id("gremah", s))
              for s in symbols_for_robot("gremah")}
    assert len(magics) == len(symbols_for_robot("gremah"))
    assert slot_by_id("swing").magic not in magics


def test_robo_instancia_no_ativo_do_slot_nao_no_default():
    """O ponto da mudança inteira: dois `gremah` em papéis diferentes."""
    assert get_daytrade_robot("gremah").symbol == "PMAM3"
    assert get_daytrade_robot("gremah", symbol="KLBN4").symbol == "KLBN4"


def test_robo_recusa_ativo_sem_calibracao_propria():
    """`profit_pct`/`stop_multiplier` não transferem entre símbolos — o robô
    falha alto em vez de herdar a calibração de outro papel."""
    with pytest.raises(ValueError, match="calibracao"):
        get_daytrade_robot("gremah", symbol="PETR4")


# ---------- a regra de sugestão (pura) -------------------------------------

def _cand(symbol="KLBN4", preco=1.00):
    return Candidato(symbol=symbol, preco_atual=preco)


def test_sugere_quando_o_caixa_cobre_o_candidato_e_o_proprio_minimo():
    # próprio a R$0,10 -> mínimo R$20; candidato a R$1,00 -> mínimo R$200.
    assert avaliar_sugestao(caixa_brl=219.99, preco_proprio=0.10,
                            candidatos=[_cand()]) is None
    sug = avaliar_sugestao(caixa_brl=220.0, preco_proprio=0.10, candidatos=[_cand()])
    assert sug is not None
    assert (sug.symbol, sug.required_brl) == ("KLBN4", 200.0)


def test_o_que_ja_foi_aportado_nos_outros_e_abatido():
    """O pedido do dono ("abater o dinheiro do que já foi aberto"): é o que
    faz a barra SUBIR a cada robô novo. Sem isso, o mesmo caixa aprovaria a
    fila inteira no mesmo dia."""
    assert avaliar_sugestao(caixa_brl=300.0, preco_proprio=0.10,
                            candidatos=[_cand()], ja_aportado_brl=0.0) is not None
    assert avaliar_sugestao(caixa_brl=300.0, preco_proprio=0.10,
                            candidatos=[_cand()], ja_aportado_brl=100.0) is None


def test_fila_estrita_nao_pula_para_o_que_caberia():
    """Comportamento medido e escolhido pelo dono (cenário C): o candidato caro
    à frente TRAVA as sugestões, mesmo havendo barato atrás. Não é beco — o
    painel deixa abrir qualquer ativo na mão."""
    caro, barato = _cand("CLSC4", 151.95), _cand("KLBN4", 1.00)
    assert avaliar_sugestao(caixa_brl=5_000.0, preco_proprio=0.10,
                            candidatos=[caro, barato]) is None


def test_sem_preco_do_candidato_a_fila_espera():
    assert avaliar_sugestao(caixa_brl=99_999.0, preco_proprio=0.10,
                            candidatos=[_cand(preco=0.0)]) is None
    assert avaliar_sugestao(caixa_brl=99_999.0, preco_proprio=0.0,
                            candidatos=[_cand()]) is None


# ---------- avisos de capital: dedup e "feito" -----------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "live.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (path,))
    return path


def _conta(db, name="dt-gremah-pmam3", symbol="PMAM3", cash=0.0):
    with live_store.live_journal(db) as conn:
        acc = live_store.ensure_account(
            conn, name=name, mode="mt5", initial_capital=cash,
            investment_robot="gremah", withdrawal_robot="", symbol=symbol)
        return acc.id


def test_aviso_e_gravado_uma_vez_por_ativo(db):
    """O robô vê centenas de barras por dia e a condição continua verdadeira
    em todas — sem a deduplicação do banco, a caixa de mensagens viraria log
    de spam e o "marcar como feito" não significaria nada."""
    account_id = _conta(db)
    with live_store.live_journal(db) as conn:
        assert live_store.record_capital_signal(
            conn, account_id, "gremah", "KLBN4", 900.0, 700.0) is True
        assert live_store.record_capital_signal(
            conn, account_id, "gremah", "KLBN4", 950.0, 700.0) is False
        assert live_store.record_capital_signal(
            conn, account_id, "gremah", "CSAN3", 950.0, 720.0) is True
        assert len(live_store.capital_signals(conn)) == 2


def test_marcar_como_feito_e_idempotente_e_nao_ressuscita(db):
    account_id = _conta(db)
    with live_store.live_journal(db) as conn:
        live_store.record_capital_signal(conn, account_id, "gremah", "KLBN4", 900.0, 700.0)
        aviso = live_store.capital_signals(conn)[0]

        assert live_store.acknowledge_capital_signal(conn, aviso["id"]) is True
        assert live_store.acknowledge_capital_signal(conn, aviso["id"]) is False
        assert live_store.capital_signals(conn, pending_only=True) == []

        # "já cuidei disso" vale para sempre naquele ativo: um novo pregão não
        # pode reabrir o aviso.
        live_store.record_capital_signal(conn, account_id, "gremah", "KLBN4", 999.0, 700.0)
        assert live_store.capital_signals(conn, pending_only=True) == []


# ---------- contas de day trade: listagem e remoção ------------------------

def test_accounts_with_symbol_ignora_o_swing(db):
    _conta(db)
    with live_store.live_journal(db) as conn:
        live_store.ensure_account(conn, name="swing", mode="mt5", initial_capital=0.0,
                                  investment_robot="liqflop", withdrawal_robot="")
        assert [c.name for c in live_store.accounts_with_symbol(conn)] == ["dt-gremah-pmam3"]


def test_conta_nunca_troca_de_ativo(db):
    """Uma conta criada para PMAM3 sendo reaberta para KLBN4 herdaria posições,
    caixa e histórico do papel errado."""
    _conta(db)
    with live_store.live_journal(db) as conn:
        with pytest.raises(ValueError, match="nunca troca de papel"):
            live_store.ensure_account(
                conn, name="dt-gremah-pmam3", mode="mt5", initial_capital=0.0,
                investment_robot="gremah", withdrawal_robot="", symbol="KLBN4")


def test_remover_conta_com_caixa_e_recusado(db):
    """Apagar a linha não devolve dinheiro nem fecha posição — zerar o caixa é
    decisão do dono, feita antes."""
    _conta(db, cash=100.0)
    with live_store.live_journal(db) as conn:
        with pytest.raises(ValueError, match="caixa"):
            live_store.delete_account(conn, "dt-gremah-pmam3")

        conta = live_store.load_account(conn, "dt-gremah-pmam3")
        conta.cash = 0.0
        live_store.save_account(conn, conta)
        assert live_store.delete_account(conn, "dt-gremah-pmam3") is True
        assert live_store.accounts_with_symbol(conn) == []


def test_save_account_persiste_robo_capital_e_ativo(db):
    """Bug corrigido em 2026-08-22: os três só eram gravados no INSERT de
    `ensure_account` (que é `ON CONFLICT DO NOTHING`), então uma conta criada
    primeiro como linha de caixa nunca ganhava `investment_robot` — e o painel
    a reportava como inexistente enquanto ela operava."""
    with live_store.live_journal(db) as conn:
        acc = live_store.ensure_account(conn, name="dt-gremah-pmam3", mode="mt5",
                                        initial_capital=0.0, investment_robot="",
                                        withdrawal_robot="")
        acc.investment_robot = "gremah"
        acc.symbol = "PMAM3"
        acc.initial_capital = 250.0
        live_store.save_account(conn, acc)

    with live_store.live_journal(db) as conn:
        relido = live_store.load_account(conn, "dt-gremah-pmam3")
        assert (relido.investment_robot, relido.symbol, relido.initial_capital) == (
            "gremah", "PMAM3", 250.0)
