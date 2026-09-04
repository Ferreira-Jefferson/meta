"""Seção 04 de `/operacao` — o inventário de processos e o botão que mata.

Pedido do dono em 26/08/2026: "pode acontecer de ter um processo morto que
eventualmente não está listado, ou não é um robô que eu consiga ver ... seria
interessante a /operacao sempre registrar todos os processos de robôs e ter
uma maneira de matar estes processos pela tela de operação".

O ponto cego que isto fecha: todo o resto do painel raciocina por CARTÃO, e
um supervisor sem cartão (robô removido com o processo vivo, robô subido pela
CLI, sobra de um dashboard fechado sem parar nada) não aparecia em lugar
nenhum da tela — a única saída era o Gerenciador de Tarefas.

`dashboard/live_control.py` já sabia varrer e matar
(`test_live_process_inventory.py` cobre a INTERPRETAÇÃO da varredura). Aqui o
que está sob teste é a TELA: quem ela chama, quando chama, como classifica o
que voltou, e o que ela faz com um clique em "Encerrar".

Nada aqui toca o sistema de verdade: `_processos_do_sistema` (o único ponto
que executa `powershell`/`ps`) e `_matar_arvore` entram por monkeypatch.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from core.config import daytrade_slot
from dashboard import app as dashboard_app
from dashboard import live_control
from journal import live_store

_LINHA = ("C:\\meta\\.venv\\Scripts\\python.exe C:\\meta\\scripts\\run_live.py "
          "--mode mt5 --slot {slot} --execution-mode {modo} loop --seconds 5")

COM_CARTAO = daytrade_slot("gremah", "PMAM3", "shadow")
SEM_CARTAO = daytrade_slot("outrorobo", "CSAN3", "live")


@pytest.fixture
def diario(tmp_path, monkeypatch):
    """Banco e arquivo de estado isolados — a tela lê os DOIS (o banco para
    saber quem tem cartão, o arquivo para saber quem o painel rastreia).

    `_SECRETS_PATH` entra junto: `client.get("/operacao")` renderiza a
    página inteira, inclusive a seção de credenciais (`credential_status()`
    lê `db/live_secrets.json`) — sem isolar, o teste dependeria do que está
    salvo de verdade na máquina."""
    db = tmp_path / "live_processos.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db,))
    monkeypatch.setattr(live_control, "_STATE_PATH", tmp_path / "live_process.json")
    monkeypatch.setattr(live_control, "_SECRETS_PATH", tmp_path / "live_secrets.json")
    return db


@pytest.fixture
def client():
    return TestClient(dashboard_app.app)


def _cria_cartao(slot=COM_CARTAO):
    """Uma conta — é ela, e não o arquivo de estado, que faz o cartão existir
    no painel (ver `dashboard/slots.py`)."""
    with live_store.live_journal() as conn:
        live_store.ensure_account(
            conn, name=slot.id, mode="mt5", initial_capital=100.0,
            investment_robot=slot.robot_key, withdrawal_robot="",
            symbol=slot.symbol)


def _rastreia(pid: int, slot=COM_CARTAO):
    live_control._write_state(slot.id, {
        "pid": pid, "started_at": "2026-08-26T12:00:00+00:00",
        "config": {"slot": slot.id}})


def _varredura(monkeypatch, *processos):
    """`processos` são `(pid, slot, modo)` — viram linhas de comando como as
    que o `Get-CimInstance` devolve."""
    achados = [(pid, 0, _LINHA.format(slot=slot, modo=modo))
               for pid, slot, modo in processos]
    monkeypatch.setattr(live_control, "_processos_do_sistema", lambda: achados)


def _mortos(monkeypatch) -> list[int]:
    mortos: list[int] = []
    monkeypatch.setattr(live_control, "_matar_arvore", mortos.append)
    return mortos


# ---------- quando a varredura acontece (e quando NÃO acontece) ------------

def test_a_pagina_nao_varre_o_sistema_ao_carregar(diario, client, monkeypatch):
    """A varredura custa ~3s (o `Get-CimInstance` enumera a máquina inteira) e
    o corpo de `/operacao` é remontado a cada clique da página — criar robô,
    salvar caixa, salvar credencial. Fosse feita junto, TODO clique pagaria
    esses segundos por uma resposta que ninguém pediu naquele clique.

    A seção nasce vazia e se preenche sozinha (`hx-trigger="load"`)."""
    monkeypatch.setattr(live_control, "_processos_do_sistema",
                        lambda: pytest.fail("a carga da página não pode varrer"))

    html = client.get("/operacao").text

    assert 'id="ops-processos"' in html
    assert 'hx-get="/operacao/processos"' in html
    assert "Varrendo os processos" in html


def test_varredura_classifica_rastreado_solto_e_sem_cartao(diario, client, monkeypatch):
    """As três situações que a tela precisa distinguir — e a do meio é a
    perigosa: cartão dizendo "parado" com o processo vivo. Um clique em
    "Iniciar" ali subiria um SEGUNDO supervisor para a mesma conta."""
    _cria_cartao()
    _cria_cartao(daytrade_slot("outrorobo", "PMAM3", "shadow"))
    _rastreia(111)
    _varredura(monkeypatch,
               (111, COM_CARTAO.id, "shadow"),                       # rastreado
               (222, "dt-outrorobo-pmam3-shadow", "shadow"),         # cartão, sem rastro
               (333, SEM_CARTAO.id, "live"))                         # órfão puro

    html = client.get("/operacao/processos").text

    assert "3 rodando" in html and "2 soltos" in html
    assert "rastreado pelo painel" in html
    assert 'diz "parado", mas o processo está vivo' in html
    assert "não há cartão para este robô" in html
    for pid in (111, 222, 333):
        assert f'hx-post="/operacao/processos/{pid}/encerrar"' in html


def test_varredura_que_engasgou_nao_vira_lista_vazia(diario, client, monkeypatch):
    """"Não consegui varrer" e "não há nada rodando" são frases OPOSTAS, e a
    segunda é a que faz o dono ir dormir com um robô solto operando."""
    def explode():
        raise live_control._TasklistUnavailable("powershell não respondeu")
    monkeypatch.setattr(live_control, "_processos_do_sistema", explode)

    html = client.get("/operacao/processos").text

    assert "Não consegui varrer" in html
    assert "Nenhum supervisor" not in html
    assert "não foi possível varrer" in html, "o cabeçalho recolhido também não pode mentir"


def test_sem_processo_nenhum_a_secao_diz_isso(diario, client, monkeypatch):
    _varredura(monkeypatch)

    html = client.get("/operacao/processos").text

    assert "Nenhum supervisor de robô rodando" in html
    assert "nenhum rodando" in html


# ---------- o botão que mata ----------------------------------------------

def test_encerrar_mata_o_processo_e_o_arquivo_para_de_apontar(diario, client, monkeypatch):
    """O caso que motivou a tela inteira: matar por PID um robô que o painel
    rastreava. Depois disso o arquivo de estado não pode continuar apontando
    para o PID morto — senão o cartão seguiria dizendo "operando"."""
    _cria_cartao()
    _rastreia(111)
    _varredura(monkeypatch, (111, COM_CARTAO.id, "shadow"))
    mortos = _mortos(monkeypatch)

    resp = client.post("/operacao/processos/111/encerrar")

    assert resp.status_code == 200
    assert mortos == [111]
    assert "encerrado" in resp.text
    estado = json.loads(live_control._STATE_PATH.read_text(encoding="utf-8"))
    assert estado["slots"][COM_CARTAO.id]["pid"] is None
    assert estado["slots"][COM_CARTAO.id]["config"], "a config de retomada fica"


def test_encerrar_sem_cartao_nenhum_funciona_igual(diario, client, monkeypatch):
    """O órfão puro é a razão de existir do botão: nenhum outro caminho da
    tela chega nele."""
    _varredura(monkeypatch, (333, SEM_CARTAO.id, "live"))
    mortos = _mortos(monkeypatch)

    resp = client.post("/operacao/processos/333/encerrar")

    assert mortos == [333]
    assert SEM_CARTAO.id in resp.text


def test_pid_desconhecido_e_recusado_sem_matar_nada(diario, client, monkeypatch):
    """O PID chega pela URL de um POST. Sem a conferência de
    `encerrar_processo`, isto seria "mate qualquer processo desta máquina pelo
    número", exposto em HTTP — o próprio dashboard, o terminal MT5, o Windows.

    E a recusa é MENSAGEM, não erro 500: o caso normal dela é benigno (o
    processo morreu sozinho entre a varredura e o clique)."""
    _varredura(monkeypatch, (111, COM_CARTAO.id, "shadow"))
    mortos = _mortos(monkeypatch)

    resp = client.post("/operacao/processos/4/encerrar")

    assert resp.status_code == 200
    assert mortos == []
    assert "nao e (mais) um robo em execucao" in resp.text


def test_a_resposta_do_botao_e_so_a_secao(diario, client, monkeypatch):
    """O botão fica no FIM da página. Trocar o `#ops-body` inteiro colocaria a
    confirmação num banner lá em cima, fora do campo de visão de quem acabou
    de clicar (mesma queixa do dono sobre o banner de colisão, 2026-08-25)."""
    _varredura(monkeypatch, (111, COM_CARTAO.id, "shadow"))
    _mortos(monkeypatch)

    corpo = client.post("/operacao/processos/111/encerrar").text

    assert 'id="ops-processos"' in corpo
    assert "Acesso e credenciais" not in corpo, "não é a página inteira"


# ---------- a degradação, no módulo ---------------------------------------

def test_inventario_devolve_o_motivo_em_vez_de_levantar(monkeypatch):
    def explode():
        raise live_control._TasklistUnavailable("timeout")
    monkeypatch.setattr(live_control, "_processos_do_sistema", explode)

    processos, erro = live_control.inventario_processos()

    assert processos == [] and "timeout" in erro


# ---------- reconciliação: só o poll do cartão pode varrer (2026-08-31) ----

def test_poll_do_cartao_readota_processo_orfao_vivo(diario, client, monkeypatch):
    """O caso relatado pelo dono: dashboard reiniciado deixa o `Popen` órfão
    vivo e o cartão diz "parado" para sempre. O poll periódico do cartão
    (`operacao_fragment`, NUNCA a carga de `/operacao` -- ver
    `test_a_pagina_nao_varre_o_sistema_ao_carregar`) é o único lugar que pode
    pagar o custo da varredura e fechar o ciclo sozinho."""
    _cria_cartao(COM_CARTAO)
    linha = (f"C:\\meta\\.venv\\Scripts\\python.exe C:\\meta\\scripts\\run_live.py "
             f"--mode mt5 --capital 30.0 --strategy {COM_CARTAO.robot_key} "
             f"--slot {COM_CARTAO.id} --execution-mode shadow loop --seconds 5")
    monkeypatch.setattr(live_control, "_processos_do_sistema", lambda: [(18816, 0, linha)])

    html = client.get(f"/operacao/{COM_CARTAO.id}/fragment").text

    assert "operando" in html
    assert live_control._read_state(COM_CARTAO.id)["pid"] == 18816
