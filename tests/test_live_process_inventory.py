"""Inventário de processos de robô — `dashboard/live_control.listar_processos`
e o que depende dele.

Por que existe: até 25/08/2026 o painel só sabia responder "o PID que EU
anotei ainda está vivo?". O dono fechou o dashboard sem parar os robôs e três
supervisores continuaram rodando, dormindo até a abertura do dia seguinte —
invisíveis para todo botão da tela. A varredura aqui pergunta ao sistema
operacional quem está rodando `run_live.py`, e o arquivo de estado volta a ser
o que sempre deveria ter sido: um índice do que o painel criou, não a
definição do que existe.

Nenhum teste chama o sistema de verdade: `_processos_do_sistema` (o único
ponto que executa `powershell`/`ps`) e `_matar_arvore` entram por
monkeypatch. O que está sendo protegido é a INTERPRETAÇÃO da varredura, que é
onde mora o risco de matar o processo errado.
"""
from __future__ import annotations

import json

import pytest

from dashboard import live_control


_LINHA = ("C:\\meta\\.venv\\Scripts\\python.exe C:\\meta\\scripts\\run_live.py "
          "--mode mt5 --slot {slot} --execution-mode {modo} loop --seconds 5")


@pytest.fixture
def estado(tmp_path, monkeypatch):
    """Arquivo de estado isolado — nunca o `db/live_process.json` real."""
    caminho = tmp_path / "live_process.json"
    monkeypatch.setattr(live_control, "_STATE_PATH", caminho)
    return caminho


def _grava(caminho, **slots):
    caminho.write_text(json.dumps({
        "version": 2,
        "slots": {sid: {"pid": pid, "started_at": "2026-08-25T12:00:00+00:00",
                        "config": {"slot": sid}}
                  for sid, pid in slots.items()},
    }), encoding="utf-8")


def _varredura(monkeypatch, achados):
    monkeypatch.setattr(live_control, "_processos_do_sistema", lambda: achados)


def _mortos(monkeypatch) -> list[int]:
    mortos: list[int] = []
    monkeypatch.setattr(live_control, "_matar_arvore", mortos.append)
    return mortos


# ---------- leitura da linha de comando ------------------------------------

def test_argumento_le_as_duas_formas():
    linha = _LINHA.format(slot="dt-gremah-pmam3-live", modo="live")
    assert live_control._argumento(linha, "slot") == "dt-gremah-pmam3-live"
    assert live_control._argumento(linha, "execution-mode") == "live"
    assert live_control._argumento(linha.replace("--slot ", "--slot="), "slot") == \
        "dt-gremah-pmam3-live"
    assert live_control._argumento(linha, "inexistente") is None


def test_flag_sem_valor_no_fim_da_linha_nao_estoura():
    """`--slot` como último token acontece em linha truncada pelo SO."""
    assert live_control._argumento("python run_live.py --slot", "slot") is None


# ---------- interpretação da varredura -------------------------------------

def test_interpretador_filho_nao_vira_linha_propria(estado, monkeypatch):
    """No Windows o `python.exe` do venv é um lançador: ele cria o
    interpretador de verdade como FILHO, com a mesma linha de comando. Listar
    os dois faria a tela mostrar seis processos para três robôs — e convidaria
    o dono a matar a metade errada, deixando o supervisor vivo."""
    linha = _LINHA.format(slot="dt-gremah-pmam3-live", modo="live")
    _varredura(monkeypatch, [(5728, 21616, linha), (20980, 5728, linha)])
    _grava(estado, **{"dt-gremah-pmam3-live": 5728})

    processos = live_control.listar_processos()

    assert [p.pid for p in processos] == [5728]
    assert processos[0].filhos == (20980,)


def test_processo_que_o_arquivo_nao_conhece_aparece_como_nao_rastreado(estado, monkeypatch):
    """O caso que motivou tudo: robô vivo que nenhum botão do painel alcança."""
    _varredura(monkeypatch, [
        (5728, 1, _LINHA.format(slot="dt-gremah-pmam3-shadow", modo="shadow")),
        (777, 1, _LINHA.format(slot="dt-gremah_tick-pmam3-live", modo="live")),
    ])
    _grava(estado, **{"dt-gremah-pmam3-shadow": 5728})

    por_slot = {p.slot: p for p in live_control.listar_processos()}

    assert por_slot["dt-gremah-pmam3-shadow"].rastreado is True
    assert por_slot["dt-gremah_tick-pmam3-live"].rastreado is False
    assert por_slot["dt-gremah_tick-pmam3-live"].execution_mode == "live"


def test_lista_ordenada_por_slot(estado, monkeypatch):
    """Ordem estável entre dois refreshes — uma lista que dança embaralha o
    alvo do clique."""
    _varredura(monkeypatch, [
        (300, 1, _LINHA.format(slot="dt-z-pmam3-live", modo="live")),
        (100, 1, _LINHA.format(slot="dt-a-klbn4-live", modo="live")),
    ])
    assert [p.slot for p in live_control.listar_processos()] == [
        "dt-a-klbn4-live", "dt-z-pmam3-live"]


# ---------- encerrar --------------------------------------------------------

def test_encerrar_mata_a_arvore_e_limpa_o_arquivo(estado, monkeypatch):
    linha = _LINHA.format(slot="dt-gremah-pmam3-live", modo="live")
    _varredura(monkeypatch, [(5728, 1, linha), (20980, 5728, linha)])
    _grava(estado, **{"dt-gremah-pmam3-live": 5728})
    mortos = _mortos(monkeypatch)

    processo = live_control.encerrar_processo(5728)

    assert processo.slot == "dt-gremah-pmam3-live"
    assert mortos == [5728, 20980]
    # o cartão não pode continuar dizendo "rodando" depois disto
    assert live_control._read_state("dt-gremah-pmam3-live")["pid"] is None
    # ...mas a config fica, para o formulário de retomada continuar preenchido
    assert live_control._read_state("dt-gremah-pmam3-live")["config"]["slot"] == \
        "dt-gremah-pmam3-live"


def test_encerrar_recusa_pid_que_nao_e_robo(estado, monkeypatch):
    """O PID chega pela URL de um POST. Sem esta recusa o endpoint seria
    "mate qualquer processo desta máquina pelo número", exposto em HTTP —
    inclusive o próprio dashboard e o terminal MT5."""
    _varredura(monkeypatch, [(5728, 1, _LINHA.format(slot="dt-a-pmam3-live", modo="live"))])
    mortos = _mortos(monkeypatch)

    with pytest.raises(ValueError, match="nao e"):
        live_control.encerrar_processo(4)

    assert mortos == []


# ---------- "Parar" alcança o que o arquivo não conhece ---------------------

def test_parar_cai_na_varredura_quando_o_arquivo_nao_tem_pid(estado, monkeypatch):
    """Sem isto, o painel mostra "parado" para um robô que está operando — e
    um clique em "Iniciar" ali subiria um SEGUNDO processo para a mesma
    conta."""
    linha = _LINHA.format(slot="dt-gremah-pmam3-live", modo="live")
    _varredura(monkeypatch, [(5728, 1, linha), (20980, 5728, linha)])
    mortos = _mortos(monkeypatch)

    assert live_control.stop("dt-gremah-pmam3-live") is True
    assert mortos == [5728, 20980]


def test_parar_sem_processo_nenhum_devolve_falso(estado, monkeypatch):
    _varredura(monkeypatch, [])
    assert live_control.stop("dt-gremah-pmam3-live") is False


def test_varredura_indeterminada_nao_derruba_o_botao_parar(estado, monkeypatch):
    """Varredura que engasga vira "não havia o que parar", não erro na tela:
    o dono clica de novo. Derrubar a página seria pior."""
    def explode():
        raise live_control._TasklistUnavailable("powershell nao respondeu")

    monkeypatch.setattr(live_control, "_processos_do_sistema", explode)
    assert live_control.stop("dt-gremah-pmam3-live") is False
