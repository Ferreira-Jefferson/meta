"""Remover um robô SEM perder o que ele viveu — e decidir depois.

Pedido do dono em 26/08/2026, olhando o Resumo Financeiro de um robô cujo
processo já tinha morrido: "eu sei que tem um processo morto, mas eu não
quero perder as informações do que estou rodando". Até então remover era
sempre `delete_account`, e o `ON DELETE CASCADE` levava diário, trades e
caixa junto — não havia meio-termo entre "o cartão fica na tela para sempre"
e "some tudo".

O meio-termo tem duas pontas, e este arquivo cobre as duas:

  1. na REMOÇÃO, o dono escolhe entre guardar e apagar. Guardar é o padrão
     porque é o único dos dois que dá para desfazer;
  2. na CRIAÇÃO, recriar o mesmo trio (robô, ativo, modo) oferece restaurar o
     que foi guardado. Desmarcar a caixa é o "quero do zero", e aí o arquivo
     é descartado sem segunda pergunta — pedido explícito do dono.

O que estes testes protegem, além do caminho feliz:

  * **ativo preso.** Arquivar tira o cartão da tela; se a conta continuasse
    contando como vaga ocupada, o ativo ficaria bloqueado sem nenhum lugar
    onde o dono pudesse ver o motivo;
  * **restauro parcial.** Restaurar o diário mas não o caixa (ou vice-versa)
    seria pior que não restaurar: o dono confiaria num número montado pela
    metade;
  * **"do zero" que não é do zero.** Descartar e recriar tem de deixar a
    conta ZERADA, inclusive a config de retomada em `db/live_process.json` —
    senão o robô novo ressuscita com o capital do antigo.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.config import daytrade_slot
from dashboard import app as dashboard_app
from dashboard import live_control, live_teardown
from journal import live_store

SYMBOL = "PMAM3"
SLOT = daytrade_slot("gremah", SYMBOL, "shadow")


@pytest.fixture
def diario(tmp_path, monkeypatch):
    """Diário e arquivo de estado isolados — ver `test_live_teardown.py::
    diario` para o porquê do `__wrapped__.__defaults__` e do `_STATE_PATH`."""
    from live import intraday_runtime
    from live import runtime as live_runtime

    db = tmp_path / "live_arquivo.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db,))
    monkeypatch.setattr(live_runtime, "DB_PATH", db)
    monkeypatch.setattr(intraday_runtime, "LIVE_DB_PATH", db)
    monkeypatch.setattr(live_control, "_STATE_PATH", tmp_path / "live_process.json")
    return db


@pytest.fixture
def client():
    return TestClient(dashboard_app.app)


def _conta(cash: float = 0.0, nome: str = SLOT.id, robo: str = "gremah"):
    with live_store.live_journal() as conn:
        conta = live_store.ensure_account(
            conn, name=nome, mode="mt5", initial_capital=100.0,
            investment_robot=robo, withdrawal_robot="", symbol=SYMBOL)
        conta.cash = cash
        conta.cash_sombra = cash
        live_store.save_account(conn, conta)
        return conta.id


def _sem_corretora(monkeypatch, processo=None):
    """Remoção sem broker nenhum: sombra não consulta a corretora (invariante
    do sistema), e o inventário de processos do SO não pode ser varrido dentro
    de um teste."""
    monkeypatch.setattr(live_teardown, "_broker_do_slot",
                        lambda _s: pytest.fail("sombra não abre conexão"))
    monkeypatch.setattr(live_teardown, "_processo_do_slot", lambda _sid: (processo, None))


# ---------- o arquivo, no store --------------------------------------------

def test_arquivar_tira_do_painel_e_nao_apaga_nada(diario):
    """A diferença inteira entre arquivar e apagar: a conta continua lá."""
    _conta(cash=35.92)

    with live_store.live_journal() as conn:
        assert live_store.archive_account(conn, SLOT.id) is True

        assert live_store.accounts_with_symbol(conn) == [], "o cartão sai da tela"
        guardada = live_store.load_account(conn, SLOT.id)
        assert guardada is not None and guardada.archived_at
        assert guardada.cash == 35.92, "o caixa é parte do que foi guardado"


def test_ativo_arquivado_volta_a_ficar_livre_na_hora(diario):
    """Arquivo NÃO é vaga ocupada. Se contasse, o cartão sumiria da tela e o
    ativo continuaria bloqueado — sem lugar nenhum onde ler o motivo."""
    _conta()

    from dashboard import slots as slots_mod

    with live_store.live_journal() as conn:
        live_store.archive_account(conn, SLOT.id)
        assert slots_mod.symbols_in_use(conn) == {}


def test_arquivar_recusa_com_posicao_aberta(diario):
    """Mesmo guarda de `delete_account`, e pelo mesmo motivo: arquivar tira o
    cartão da tela, e posição viva no MT5 sem cartão que a mostre é órfã
    invisível."""
    from core.live_models import LivePosition

    conta_id = _conta()
    with live_store.live_journal() as conn:
        live_store.upsert_position(conn, conta_id, LivePosition(
            ticker=SYMBOL, quantity=100, entry_date=date(2026, 8, 26),
            entry_price=0.14, capital_allocated=14.0))

        with pytest.raises(ValueError, match="posição"):
            live_store.archive_account(conn, SLOT.id)
        assert live_store.load_account(conn, SLOT.id).archived_at is None


def test_descartar_so_vale_para_conta_arquivada(diario):
    """`purge_account` ignora o guarda de caixa de propósito — e é por isso
    que ele não pode alcançar uma conta VIVA. Uma conta na tela com dinheiro
    alocado só sai por `delete_account`, que confere."""
    _conta(cash=30.0)

    with live_store.live_journal() as conn:
        with pytest.raises(ValueError, match="não está arquivada"):
            live_store.purge_account(conn, SLOT.id)

        live_store.archive_account(conn, SLOT.id)
        assert live_store.purge_account(conn, SLOT.id) is True
        assert live_store.load_account(conn, SLOT.id) is None


def test_restaurar_conta_viva_e_no_op(diario):
    """Conta que não foi a lugar nenhum não é "restaurada" — devolver algo
    aqui faria o painel anunciar um restauro que não aconteceu."""
    _conta()
    with live_store.live_journal() as conn:
        assert live_store.restore_account(conn, SLOT.id) is None


# ---------- a escolha na remoção -------------------------------------------

def test_remover_guardando_mantem_conta_caixa_e_config(diario, monkeypatch):
    """O padrão (pedido do dono): o robô sai do painel, o dinheiro do ledger
    e a config de retomada continuam guardados com ele.

    A config importa tanto quanto o diário: sem ela, restaurar devolveria o
    histórico mas mandaria o dono redigitar capital e `shares_per_lot`."""
    _conta(cash=35.92)
    live_control._write_state(SLOT.id, {"pid": None, "config": {"capital": 35.92}})
    _sem_corretora(monkeypatch)

    resultado = live_teardown.remover(SLOT)

    assert resultado.conta_arquivada and not resultado.conta_apagada
    assert resultado.removido, "sair do painel é sair do painel, pelos dois caminhos"
    assert resultado.caixa_zerado is None, "guardar não é zerar"
    assert "histórico guardado" in resultado.resumo
    with live_store.live_journal() as conn:
        assert live_store.accounts_with_symbol(conn) == []
        assert live_store.load_account(conn, SLOT.id).cash == 35.92
    assert live_control.last_config(SLOT.id) == {"capital": 35.92}


def test_remover_apagando_leva_tudo_junto(diario, monkeypatch):
    """O caminho antigo, agora explícito: some a conta E a linha do arquivo
    de estado — a config de retomada de um robô que não existe mais só teria
    como voltar ressuscitando capital velho num robô novo."""
    _conta(cash=30.0)
    live_control._write_state(SLOT.id, {"pid": None, "config": {"capital": 30.0}})
    _sem_corretora(monkeypatch)

    resultado = live_teardown.remover(SLOT, apagar_historico=True)

    assert resultado.conta_apagada and not resultado.conta_arquivada
    assert resultado.caixa_zerado == 30.0
    with live_store.live_journal() as conn:
        assert live_store.load_account(conn, SLOT.id) is None
    assert live_control.last_config(SLOT.id) is None


# ---------- a outra ponta: criar em cima do arquivo ------------------------

def test_criar_restaurando_traz_caixa_e_conta_de_volta(diario, client, monkeypatch):
    """O ciclo inteiro, do jeito que o dono faz na tela: remover guardando,
    criar de novo com a caixa marcada."""
    _conta(cash=35.92)
    _sem_corretora(monkeypatch)
    live_teardown.remover(SLOT)

    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": SYMBOL,
                             "execution_mode": "shadow", "restaurar": "1"})

    assert resp.status_code == 200, resp.text
    assert "restaurado" in resp.text
    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, SLOT.id)
        assert conta.archived_at is None, "voltou pro painel"
        assert conta.cash_sombra == 35.92, "restauro pela metade seria pior que nenhum"
        assert [c.name for c in live_store.accounts_with_symbol(conn)] == [SLOT.id]


def test_criar_do_zero_descarta_o_arquivo_sem_perguntar(diario, client, monkeypatch):
    """Caixa desmarcada JÁ é a resposta (pedido do dono: "sem confirmação nem
    nada"). E "do zero" tem de ser do zero mesmo: caixa zerado e a config de
    retomada antiga fora do caminho."""
    _conta(cash=35.92)
    live_control._write_state(SLOT.id, {"pid": None, "config": {"capital": 35.92}})
    _sem_corretora(monkeypatch)
    live_teardown.remover(SLOT)

    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": SYMBOL,
                             "execution_mode": "shadow"})

    assert resp.status_code == 200, resp.text
    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, SLOT.id)
        assert conta.archived_at is None
        assert conta.cash == 0.0 and conta.cash_sombra == 0.0
        assert conta.initial_capital == 0.0, "conta nova nasce zerada"
    assert live_control.last_config(SLOT.id) is None, \
        "config velha ressuscitaria o capital do robô que o dono acabou de descartar"


def test_conta_viva_continua_recusando_criacao_duplicada(diario, client):
    """REGRESSÃO do jeito errado de implementar isto: se o handler tratasse
    QUALQUER conta existente como arquivo, recriar um robô vivo o
    "restauraria" em silêncio em vez de recusar — e o dono acharia que criou
    um cartão novo."""
    _conta(cash=10.0)

    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": SYMBOL,
                             "execution_mode": "shadow", "restaurar": "1"})

    assert "já existe" in resp.text
    with live_store.live_journal() as conn:
        assert live_store.load_account(conn, SLOT.id).cash == 10.0


def test_form_marca_o_modo_que_tem_arquivo(diario, client, monkeypatch):
    """O `<option>` carrega em que MODOS aquele par (robô, ativo) tem
    histórico guardado — é o que faz a caixa "restaurar" aparecer só onde há
    o que restaurar (`atualizaRestauro` em `static/js/operacao.js`).

    Eixo diferente de `data-modos-usados`: arquivo não ocupa o ativo, então a
    opção NÃO pode ficar desabilitada por causa dele."""
    _conta()
    _sem_corretora(monkeypatch)
    live_teardown.remover(SLOT)

    html = client.get("/operacao").text

    assert 'data-modos-arquivados="shadow"' in html
    linha = next(l for l in html.splitlines() if "data-modos-arquivados" in l)
    assert "data-modos-usados" not in linha, "arquivo não ocupa a vaga"
