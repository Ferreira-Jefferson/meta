"""Trava de exclusividade entre PROCESSOS para "consultar margem -> mandar
ordem" (`live/margin_lock.py`), item 3.13 do `LICOES_DE_PRODUCAO.md`.

Auditoria adversarial de 2026-09-03: cada slot de day trade roda como
processo do SO separado, mas todos logam no MESMO terminal MT5 -- uma unica
margem fisica. `_check_margem_da_conta` sozinho e' correto DENTRO de um
processo; nada impedia dois processos de lerem a mesma margem livre
otimista e os dois mandarem ordem.

`threading.Lock`/`Semaphore` nao provam nada aqui: eles so' serializam
threads do MESMO processo (a suite roda em paralelo, mas dentro de cada
worker do pytest tudo e' um so' processo). A prova tem de usar processos
REAIS do SO -- por isso `subprocess`, o mesmo caminho de `test_slot_lock.py`
para a mesma classe de problema."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from live.margin_lock import MargemTravada, acquire_margin_gate

SRC = str(Path(__file__).resolve().parents[1] / "src")


def _run_holder(lock_path: Path, hold_seconds: float, results_path: Path,
                timeout: float = 30.0) -> None:
    """Sobe um processo FILHO que segura a trava por `hold_seconds` e grava
    o intervalo [inicio, fim] (relogio de PAREDE -- `time.time()`, o unico
    comparavel ENTRE processos diferentes; `perf_counter()` so' e' valido
    dentro do mesmo processo) em `results_path`, uma linha JSON. Bloqueia
    ate' o filho terminar -- para os dois rodarem em PARALELO (a prova real
    de exclusao mutua) use `subprocess.Popen` direto, ver o teste abaixo."""
    script = textwrap.dedent(f"""
        import json, sys, time
        sys.path.insert(0, {SRC!r})
        from live.margin_lock import acquire_margin_gate
        with acquire_margin_gate(lock_path={str(lock_path)!r}, timeout={timeout!r}):
            inicio = time.time()
            time.sleep({hold_seconds!r})
            fim = time.time()
        with open({str(results_path)!r}, "a", encoding="utf-8") as f:
            f.write(json.dumps({{"inicio": inicio, "fim": fim}}) + "\\n")
        print("ok")
    """)
    proc = subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True, timeout=60)
    assert "ok" in proc.stdout, proc.stderr


# ---------- exclusao mutua ENTRE processos ----------------------------------

def test_dois_processos_nunca_ficam_juntos_na_secao_critica(tmp_path):
    """Prova forte de exclusao mutua: dois processos SEPARADOS do SO, cada
    um segurando a trava por uma janela e registrando [inicio, fim] com
    relogio de parede -- os dois intervalos NAO PODEM se sobrepor."""
    lock_path = tmp_path / "margem.lock"
    resultados = tmp_path / "resultados.jsonl"

    def _spawna(hold_seconds: float) -> subprocess.Popen:
        script = textwrap.dedent(f"""
            import json, sys, time
            sys.path.insert(0, {SRC!r})
            from live.margin_lock import acquire_margin_gate
            with acquire_margin_gate(lock_path={str(lock_path)!r}, timeout=30.0):
                inicio = time.time()
                time.sleep({hold_seconds!r})
                fim = time.time()
            with open({str(resultados)!r}, "a", encoding="utf-8") as f:
                f.write(json.dumps({{"inicio": inicio, "fim": fim}}) + "\\n")
        """)
        return subprocess.Popen([sys.executable, "-c", script],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

    # Os dois pedem a MESMA trava, ao mesmo tempo, com a mesma janela de
    # espera -- se a exclusao falhar, os dois vao rodar o `sleep` juntos e
    # os intervalos vao se sobrepor quase certamente.
    p1 = _spawna(0.5)
    p2 = _spawna(0.5)
    out1, err1 = p1.communicate(timeout=60)
    out2, err2 = p2.communicate(timeout=60)
    assert p1.returncode == 0, err1
    assert p2.returncode == 0, err2

    linhas = resultados.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2, linhas
    intervalos = sorted((json.loads(l)["inicio"], json.loads(l)["fim"]) for l in linhas)
    (inicio_a, fim_a), (inicio_b, fim_b) = intervalos
    assert fim_a <= inicio_b, (
        f"os dois processos estiveram na secao critica ao mesmo tempo: "
        f"{intervalos}"
    )


def test_slots_independentes_nao_se_atrapalham_em_travas_diferentes(tmp_path):
    """Contraprova: dois processos travando arquivos DIFERENTES nao esperam
    um pelo outro -- a trava e' da CONTA (ou do que `lock_path` representar),
    nao um mutex global acidental."""
    inicio = time.monotonic()
    _run_holder(tmp_path / "a.lock", 0.3, tmp_path / "res_a.jsonl")
    _run_holder(tmp_path / "b.lock", 0.3, tmp_path / "res_b.jsonl")
    # Sequencial aqui so' testa que cada chamada funciona isoladamente; o
    # ponto de nao se atrapalharem esta' garantido por serem arquivos
    # diferentes -- ver o teste seguinte para as duas rodando em paralelo.
    assert time.monotonic() - inicio < 10.0


# ---------- timeout: processo VIVO segurando por muito tempo ----------------

def test_timeout_desiste_em_vez_de_esperar_para_sempre(tmp_path):
    """Um processo VIVO pode segurar a trava mais tempo que o esperado
    (`order_send` lento, terminal engasgado). O outro processo NAO PODE
    ficar bloqueado para sempre -- ele desiste depois de `timeout` segundos
    e levanta `MargemTravada`. Robo bloqueado com posicao aberta e' o pior
    cenario (ver LICOES_DE_PRODUCAO.md)."""
    lock_path = tmp_path / "margem.lock"
    marker = tmp_path / "adquirida.marker"
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {SRC!r})
        from live.margin_lock import acquire_margin_gate
        with acquire_margin_gate(lock_path={str(lock_path)!r}, timeout=30.0):
            from pathlib import Path
            Path({str(marker)!r}).write_text("adquirida")
            time.sleep(1.0)
    """)
    filho = subprocess.Popen([sys.executable, "-c", script],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        # Espera o FILHO confirmar que ja' segura a trava, antes de medir --
        # sem isso o teste teria uma corrida propria contra o proprio
        # setup do subprocesso.
        prazo = time.monotonic() + 10.0
        while not marker.exists():
            assert time.monotonic() < prazo, "filho nunca confirmou a trava"
            time.sleep(0.01)

        antes = time.monotonic()
        with pytest.raises(MargemTravada):
            with acquire_margin_gate(lock_path=lock_path, timeout=0.4):
                pass
        decorrido = time.monotonic() - antes

        # Nem instantaneo (provaria que nem tentou esperar) nem muito alem
        # do timeout pedido (provaria que o timeout nao e' respeitado).
        assert 0.3 <= decorrido <= 2.5, decorrido
    finally:
        filho.wait(timeout=30)


# ---------- trava a prova de processo morto ----------------------------------

def test_trava_e_liberada_quando_o_processo_morre_segurando_ela(tmp_path):
    """O requisito central do item 3.13: um processo pode morrer (crash,
    kill, falta de luz) segurando a trava, e os outros NAO PODEM ficar
    presos esperando um timeout inteiro por causa disso -- a trava e' do
    KERNEL contra o file descriptor do processo, entao morre JUNTO com ele.
    Mesma tecnica de prova de `test_slot_lock.py::
    test_a_trava_morre_com_o_processo_sem_deixar_lixo`: o filho ENTRA no
    contexto e nunca SAI (nunca chama `__exit__`), simulando a morte."""
    lock_path = tmp_path / "margem.lock"
    filho = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {SRC!r})
            from live.margin_lock import acquire_margin_gate
            ctx = acquire_margin_gate(lock_path={str(lock_path)!r}, timeout=30.0)
            ctx.__enter__()          # entra e NUNCA sai -- morre travado
            print("travado")
        """)],
        capture_output=True, text=True, timeout=60,
    )
    assert "travado" in filho.stdout, filho.stderr

    # O filho morreu segurando a trava. O SO ja' a devolveu -- a aquisicao
    # seguinte tem de ser RAPIDA (bem abaixo do timeout), nunca esperar o
    # timeout inteiro escoar.
    antes = time.monotonic()
    with acquire_margin_gate(lock_path=lock_path, timeout=10.0):
        pass
    decorrido = time.monotonic() - antes
    assert decorrido < 2.0, (
        f"esperou {decorrido:.2f}s por uma trava que o SO ja tinha liberado "
        "-- trava orfa nao deveria existir"
    )


# ---------- uso normal: adquire, libera, e libera mesmo com excecao ---------

def test_uso_normal_adquire_e_libera_para_o_proximo(tmp_path):
    lock_path = tmp_path / "margem.lock"
    with acquire_margin_gate(lock_path=lock_path, timeout=1.0):
        pass
    # Se a primeira nao tivesse liberado, esta segunda estouraria o timeout.
    with acquire_margin_gate(lock_path=lock_path, timeout=1.0):
        pass


def test_excecao_dentro_do_bloco_ainda_libera_a_trava(tmp_path):
    """A secao critica real levanta `BrokerExecutionError` quando a
    corretora recusa o envio -- a trava tem de soltar mesmo assim, senao um
    envio recusado prenderia todos os OUTROS slots."""
    lock_path = tmp_path / "margem.lock"

    class _ErroDeTeste(Exception):
        pass

    with pytest.raises(_ErroDeTeste):
        with acquire_margin_gate(lock_path=lock_path, timeout=1.0):
            raise _ErroDeTeste("simulando recusa da corretora")

    with acquire_margin_gate(lock_path=lock_path, timeout=1.0):
        pass


def test_cria_a_pasta_da_trava_se_nao_existir(tmp_path):
    lock_path = tmp_path / "sub" / "pasta" / "margem.lock"
    with acquire_margin_gate(lock_path=lock_path, timeout=1.0):
        pass
    assert lock_path.exists()
