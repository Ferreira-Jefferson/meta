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


# ---------- reconciliação: cartão "parado" com processo vivo (2026-08-31) --
#
# Achado ao vivo: reinício do dashboard (uvicorn --reload, ou um `dev.bat`
# reiniciado) deixa o `Popen` órfão vivo enquanto `db/live_process.json` fica
# sem o PID novo -- os 7 slots de day trade da máquina, incluindo o robô REAL
# (`dt-gremah-pmam3-live`), ficaram "parados" no painel com o processo de pé
# por trás. `status(..., reconciliar=True)`/`status_all(..., reconciliar=True)`
# agora readotam em vez de desistir -- ver `_reconciliar_do_inventario`/
# `_reconciliar_orfao`. `reconciliar` é OPT-IN (default `False`) porque a
# varredura custa ~3s e a carga da página `/operacao` tem contrato de nunca
# pagar esse custo (`test_a_pagina_nao_varre_o_sistema_ao_carregar`) -- só o
# poll periódico do cartão (`app.operacao_fragment`) liga a reconciliação.

def test_status_sem_reconciliar_nao_varre_e_continua_parado(estado, monkeypatch):
    """O default tem de se comportar EXATAMENTE como antes desta mudança --
    é o caminho que a carga de `/operacao` usa."""
    monkeypatch.setattr(live_control, "_processos_do_sistema",
                        lambda: pytest.fail("reconciliar=False não pode varrer"))
    live_control._write_state("dt-gremah-pmam3-live", {
        "pid": None, "started_at": None,
        "config": {"slot": "dt-gremah-pmam3-live", "strategy": "gremah"},
    })

    assert live_control.status("dt-gremah-pmam3-live") is None
    assert live_control.status_all(["dt-gremah-pmam3-live"])["dt-gremah-pmam3-live"] is None


def test_status_readota_processo_orfao_preservando_a_config_existente(estado, monkeypatch):
    """Caso mais comum: o arquivo perdeu só o `pid` (config sobrevive, é o
    que `status_all()` já preservava antes) -- reconciliação usa a config
    JÁ SALVA, nunca reconstrói à toa quando não precisa."""
    linha = _LINHA.format(slot="dt-gremah-pmam3-live", modo="live")
    _varredura(monkeypatch, [(18816, 1, linha)])
    live_control._write_state("dt-gremah-pmam3-live", {
        "pid": None, "started_at": None,
        "config": {"slot": "dt-gremah-pmam3-live", "strategy": "gremah"},
    })

    estado_lido = live_control.status("dt-gremah-pmam3-live", reconciliar=True)

    assert estado_lido is not None
    assert estado_lido["pid"] == 18816
    assert estado_lido["config"]["strategy"] == "gremah"
    assert live_control._read_state("dt-gremah-pmam3-live")["pid"] == 18816


def test_status_readota_reconstruindo_config_da_linha_de_comando(estado, monkeypatch):
    """Caso mais severo, também real em 31/08/2026: o slot sumiu POR INTEIRO
    do arquivo (4 dos 7 ficaram assim), não só o `pid` -- a config vem da
    PRÓPRIA linha de comando do processo vivo."""
    linha = ("C:\\meta\\.venv\\Scripts\\python.exe C:\\meta\\scripts\\run_live.py "
             "--mode mt5 --capital 800.07 --strategy gremah_tick "
             "--slot dt-gremah_tick-klbn3-shadow --execution-mode shadow "
             "--notify-min-level warn --mt5-shares-per-lot 1.0 loop --seconds 5")
    _varredura(monkeypatch, [(21200, 1, linha)])

    estado_lido = live_control.status("dt-gremah_tick-klbn3-shadow", reconciliar=True)

    assert estado_lido["pid"] == 21200
    assert estado_lido["config"] == {
        "mode": "mt5", "capital": 800.07, "strategy": "gremah_tick",
        "slot": "dt-gremah_tick-klbn3-shadow", "execution_mode": "shadow",
        "notify_min_level": "warn", "mt5_shares_per_lot": 1.0,
        "mt5_fractional_map": None, "mt5_symbol_map": None,
    }


def test_status_nao_adota_quando_dois_processos_reivindicam_o_mesmo_slot(estado, monkeypatch):
    """Dois processos vivos pro mesmo slot é sinal de INCIDENTE (duas
    instâncias escrevendo a mesma conta -- ver a memória
    `supervisores_duplicados_painel_cego`), não divergência de painel: nunca
    escolhe um dos dois sozinho, deixa "parado" até resolução manual."""
    linha = _LINHA.format(slot="dt-gremah-pmam3-live", modo="live")
    _varredura(monkeypatch, [(111, 1, linha), (222, 1, linha)])

    assert live_control.status("dt-gremah-pmam3-live", reconciliar=True) is None
    assert live_control._read_state("dt-gremah-pmam3-live") is None


def test_status_sem_candidato_nenhum_continua_parado(estado, monkeypatch):
    _varredura(monkeypatch, [])
    assert live_control.status("dt-gremah-pmam3-live", reconciliar=True) is None


def test_status_all_reconcilia_o_lote_inteiro_com_uma_unica_varredura(estado, monkeypatch):
    """Mesmo espírito de `_pids_alive`: uma varredura pro LOTE de slots
    pendentes, nunca uma por slot -- `status_all()` é chamado pela tela que
    lista todos os robôs de uma vez."""
    chamadas: list[int] = []

    def _varre():
        chamadas.append(1)
        return [
            (111, 1, _LINHA.format(slot="dt-a-shadow", modo="shadow")),
            (222, 1, _LINHA.format(slot="dt-b-shadow", modo="shadow")),
        ]

    monkeypatch.setattr(live_control, "_processos_do_sistema", _varre)
    live_control._write_state("dt-a-shadow",
                               {"pid": None, "started_at": None, "config": {"slot": "dt-a-shadow"}})
    live_control._write_state("dt-b-shadow",
                               {"pid": None, "started_at": None, "config": {"slot": "dt-b-shadow"}})

    resultado = live_control.status_all(["dt-a-shadow", "dt-b-shadow"], reconciliar=True)

    assert resultado["dt-a-shadow"]["pid"] == 111
    assert resultado["dt-b-shadow"]["pid"] == 222
    assert len(chamadas) == 1
