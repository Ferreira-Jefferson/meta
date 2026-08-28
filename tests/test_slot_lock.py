"""Trava de exclusividade por slot (`live/slot_lock.py`).

Auditoria adversarial de 2026-08-28: toda a guarda contra processo duplicado
morava em `dashboard/live_control.start()` e so' rodava quando alguem clicava
"Iniciar" no painel. A CLI direta e o servico NSSM -- o caminho que o proprio
`DEPLOY.md` documenta -- passavam livres.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from live.slot_lock import SlotEmUso, lock_slot

SRC = str(Path(__file__).resolve().parents[1] / "src")


def test_segundo_lock_no_mesmo_slot_e_recusado(tmp_path):
    with lock_slot("dt-gremah-pmam3-live", lock_dir=tmp_path):
        with pytest.raises(SlotEmUso, match="ja ha um processo"):
            with lock_slot("dt-gremah-pmam3-live", lock_dir=tmp_path):
                pass


def test_slots_diferentes_nao_se_atrapalham(tmp_path):
    """O dono opera varios robos ao mesmo tempo -- a trava e' por SLOT, e
    travar um nao pode impedir os outros de subir."""
    with lock_slot("dt-gremah-pmam3-live", lock_dir=tmp_path):
        with lock_slot("dt-copa_win-win@-live", lock_dir=tmp_path):
            pass


def test_a_trava_e_liberada_ao_sair_do_bloco(tmp_path):
    with lock_slot("dt-gremah-pmam3-live", lock_dir=tmp_path):
        pass
    with lock_slot("dt-gremah-pmam3-live", lock_dir=tmp_path):
        pass


def test_a_trava_morre_com_o_processo_sem_deixar_lixo(tmp_path):
    """O ponto de ser trava de SO e nao arquivo com PID: um processo que
    morre de qualquer jeito (kill, falta de luz) NAO deixa trava velha.

    Um arquivo com PID precisaria de vivacidade para distinguir "em uso" de
    "lixo de processo morto" -- no Windows isso e' um `tasklist`, que ja se
    sabe engasgar e cuja falha e' ambigua."""
    filho = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {SRC!r})
            from live.slot_lock import lock_slot
            ctx = lock_slot("dt-gremah-pmam3-live", lock_dir={str(tmp_path)!r})
            ctx.__enter__()          # entra e NUNCA sai -- morre travado
            print("travado")
        """)],
        capture_output=True, text=True, timeout=60,
    )
    assert "travado" in filho.stdout, filho.stderr

    # O filho morreu segurando a trava. O SO ja a devolveu.
    with lock_slot("dt-gremah-pmam3-live", lock_dir=tmp_path):
        pass


def test_slot_id_nunca_escapa_da_pasta_de_travas(tmp_path):
    """`slot_id` vira nome de ARQUIVO. Um id com barra ou `..` nao pode
    escrever fora da pasta de travas."""
    with lock_slot("../../fora/dt-x", lock_dir=tmp_path) as caminho:
        # O `.` continua permitido (nome de arquivo comum tem ponto); o que
        # nao pode e' o SEPARADOR sobreviver -- e' ele que faz o caminho
        # subir de pasta.
        assert "/" not in caminho.name and "\\" not in caminho.name
        assert caminho.resolve().parent == tmp_path.resolve()
