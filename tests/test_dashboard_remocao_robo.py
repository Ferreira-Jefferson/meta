"""O clique em "Remover robô" no painel — os DOIS passos.

Antes de 25/08/2026 isto era um `hx-confirm` do navegador seguido de uma
recusa ("pare a operação antes de remover"), e a recusa era honesta mas
inútil: quem clica em remover não quer que o robô continue rodando. Pior, o
que estivesse pendurado no MT5 sobrevivia à remoção e virava órfão invisível,
porque o cartão que mostrava aquilo acabava de sumir da tela.

O que estes testes protegem:

  1. o PRIMEIRO POST não muda nada — só mostra o diálogo. Um clique acidental
     em "Remover" não pode apagar conta nenhuma;
  2. o SEGUNDO POST (o de dentro do diálogo) executa, e a tela conta o que
     aconteceu em vez de prometer;
  3. slot fixo (swing) continua não removível.

A corretora nunca é tocada: `live_teardown` entra por monkeypatch.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard import app as dashboard_app
from dashboard import live_teardown
from journal import live_store

SLOT = "dt-gremah-pmam3-shadow"
SYMBOL = "PMAM3"


@pytest.fixture
def isolated_journal(tmp_path, monkeypatch):
    """Mesmo isolamento de `test_dashboard_daytrade_robot.py` — ver a
    docstring de lá para o `__wrapped__.__defaults__`."""
    from live import intraday_runtime
    from live import runtime as live_runtime

    from dashboard import live_control

    db_path = tmp_path / "live_journal.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db_path,))
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    monkeypatch.setattr(intraday_runtime, "LIVE_DB_PATH", db_path)
    # nenhum teste daqui pode tocar o `db/live_process.json` da máquina
    monkeypatch.setattr(live_control, "_STATE_PATH", tmp_path / "live_process.json")
    # nem `db/live_secrets.json` (lido por `credential_status()` em toda
    # renderização de `/operacao`)
    monkeypatch.setattr(live_control, "_SECRETS_PATH", tmp_path / "live_secrets.json")
    return db_path


@pytest.fixture
def client():
    return TestClient(dashboard_app.app)


def _conta(db_path, cash: float = 0.0):
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=SLOT, mode="mt5", initial_capital=100.0,
            investment_robot="gremah", withdrawal_robot="", symbol=SYMBOL)
        acc.cash = cash
        live_store.save_account(conn, acc)


def _existe(db_path) -> bool:
    with live_store.live_journal(db_path) as conn:
        return live_store.load_account(conn, SLOT) is not None


def _pendencias(**kwargs):
    base = dict(slot_id=SLOT, label="Gremah — PMAM3", symbol=SYMBOL, modo="shadow",
                processo_pid=5728, caixa=30.0, ordens=[])
    base.update(kwargs)
    return live_teardown.Pendencias(**base)


def test_primeiro_clique_so_mostra_o_dialogo(client, isolated_journal, monkeypatch):
    """Um clique acidental em "Remover" não pode apagar conta nenhuma."""
    _conta(isolated_journal, cash=30.0)
    monkeypatch.setattr(live_teardown, "inspecionar", lambda slot: _pendencias())
    monkeypatch.setattr(live_teardown, "remover",
                        lambda slot: pytest.fail("o primeiro POST não pode executar"))

    html = client.post(f"/operacao/{SLOT}/remover", data={}).text

    assert "<dialog" in html and "Remover Gremah" in html
    assert "O processo 5728 é encerrado" in html
    assert 'name="confirmar" value="1"' in html, \
        "o botão do diálogo é o que distingue os dois passos"
    assert _existe(isolated_journal)


def test_dialogo_lista_ordem_e_resultado_estimado(client, isolated_journal, monkeypatch):
    """A diferença entre "tem certeza?" e "isto é o que vai acontecer"."""
    _conta(isolated_journal)
    monkeypatch.setattr(live_teardown, "inspecionar", lambda slot: _pendencias(
        modo="live",
        ordens=[live_teardown.OrdemPendurada("123456", "compra", 100, 0.13, SYMBOL)],
        posicao={"side": "long", "price": 0.14, "quantity": 100},
        preco_atual=0.13))

    html = client.post(f"/operacao/{SLOT}/remover", data={}).text

    assert "#123456" in html and "0,13" in html
    assert "encerrada a mercado" in html
    # O popup mostra o número LÍQUIDO desde 2026-09-09, o mesmo que a remoção
    # vai creditar (antes ele prometia um resultado melhor que o cobrado), e
    # líquido dos DOIS custos de uma saída a mercado: 1 tick de derrapagem
    # (R$0,01 numa ação, a saída vende a R$0,12 -> R$2,00 de prejuízo bruto)
    # mais R$0,01 de taxa de bolsa do round-trip.
    assert "prejuízo de R$ 2,01" in html
    assert "1 tick de derrapagem" in html


def test_preco_recusado_explica_o_motivo_em_vez_de_dizer_que_nao_ha_preco(
        client, isolated_journal, monkeypatch):
    """"Não achei preço" e "achei e recusei" levam o dono a ações diferentes:
    no segundo caso abrir o MT5 e remover de novo dá um número de verdade. O
    diálogo dizia a mesma frase para os dois, e o dono confirmaria achando que
    o painel está cego."""
    _conta(isolated_journal)
    monkeypatch.setattr(live_teardown, "inspecionar", lambda slot: _pendencias(
        posicao={"side": "long", "price": 0.14, "quantity": 100},
        preco_atual=None,
        preco_recusado="a ultima barra salva e' de 2026-08-28, 12 dias atras "
                       "(o limite e' 5)"))

    html = client.post(f"/operacao/{SLOT}/remover", data={}).text

    assert "12 dias atras" in html
    assert "encerrada pelo próprio preço de entrada" in html
    assert "Não consegui ler o preço de agora" not in html


def test_corretora_muda_nao_oferece_o_botao_de_remover(client, isolated_journal, monkeypatch):
    """Robô real cuja corretora não respondeu: o diálogo vira explicação, sem
    ação — apagar às cegas é como se cria ordem órfã."""
    _conta(isolated_journal)
    monkeypatch.setattr(live_teardown, "inspecionar", lambda slot: _pendencias(
        modo="live", ordens=None, erro_corretora="terminal MT5 não respondeu"))

    html = client.post(f"/operacao/{SLOT}/remover", data={}).text

    assert "Não dá para remover agora" in html
    assert 'name="confirmar"' not in html


def test_segundo_clique_executa_e_conta_o_que_fez(client, isolated_journal, monkeypatch):
    _conta(isolated_journal, cash=30.0)
    chamadas = []

    def falso_remover(slot, apagar_historico=False):
        chamadas.append((slot.id, apagar_historico))
        resultado = live_teardown.ResultadoRemocao(slot_id=slot.id, label="Gremah — PMAM3")
        resultado.processo_encerrado = 5728
        resultado.ordens_canceladas = ["123456"]
        resultado.caixa_zerado = 30.0
        resultado.conta_apagada = True
        return resultado

    monkeypatch.setattr(live_teardown, "remover", falso_remover)

    html = client.post(f"/operacao/{SLOT}/remover",
                       data={"confirmar": "1", "historico": "apagar"}).text

    assert chamadas == [(SLOT, True)]
    assert "processo 5728 encerrado" in html
    assert "1 ordem(ns) cancelada(s)" in html


def test_o_radio_do_dialogo_e_quem_decide_o_historico(client, isolated_journal, monkeypatch):
    """O dono escolhe no diálogo entre guardar e apagar (2026-08-26), e a
    omissão cai no lado que dá para desfazer.

    Um POST sem o campo não é hipótese de laboratório: é o cliente antigo, o
    navegador sem JS e o `curl` do dono. Se ele apagasse, a escolha "guardar"
    seria uma promessa que só vale enquanto o formulário for exatamente este.
    """
    _conta(isolated_journal)
    vistos = []

    def falso_remover(slot, apagar_historico=False):
        vistos.append(apagar_historico)
        resultado = live_teardown.ResultadoRemocao(slot_id=slot.id, label="Gremah — PMAM3")
        resultado.conta_arquivada = not apagar_historico
        resultado.conta_apagada = apagar_historico
        return resultado

    monkeypatch.setattr(live_teardown, "remover", falso_remover)

    html = client.post(f"/operacao/{SLOT}/remover",
                       data={"confirmar": "1", "historico": "guardar"}).text
    client.post(f"/operacao/{SLOT}/remover", data={"confirmar": "1"})

    assert vistos == [False, False]
    assert "histórico guardado" in html


def test_aviso_do_que_nao_deu_certo_sobe_como_erro(client, isolated_journal, monkeypatch):
    """Aviso não é sucesso: uma ordem que a corretora não cancelou tem de
    aparecer no banner vermelho, não sumir no meio da frase verde."""
    _conta(isolated_journal)

    def falso_remover(slot, apagar_historico=False):
        resultado = live_teardown.ResultadoRemocao(slot_id=slot.id, label="Gremah — PMAM3")
        resultado.avisos = ["a ordem #123456 não foi cancelada: sem conexão"]
        return resultado

    monkeypatch.setattr(live_teardown, "remover", falso_remover)

    html = client.post(f"/operacao/{SLOT}/remover", data={"confirmar": "1"}).text

    assert "ops-alert" in html
    assert "não foi cancelada" in html
    assert "NÃO foi removido" in html


def test_impedimento_no_segundo_clique_vira_mensagem_e_nao_500(client, isolated_journal,
                                                               monkeypatch):
    """O mundo pode ter mudado entre o diálogo e o clique (o terminal caiu)."""
    _conta(isolated_journal)

    def recusa(slot, apagar_historico=False):
        raise ValueError("não consegui perguntar à corretora")

    monkeypatch.setattr(live_teardown, "remover", recusa)

    resposta = client.post(f"/operacao/{SLOT}/remover", data={"confirmar": "1"})

    assert resposta.status_code == 200
    assert "não consegui perguntar à corretora" in resposta.text
    assert _existe(isolated_journal)


def test_slot_fixo_continua_nao_removivel(client, isolated_journal, monkeypatch):
    """Swing não foi criado aqui — e nem chega a inspecionar corretora."""
    monkeypatch.setattr(live_teardown, "inspecionar",
                        lambda slot: pytest.fail("não devia nem inspecionar"))

    html = client.post("/operacao/swing/remover", data={}).text

    assert "é fixo" in html
