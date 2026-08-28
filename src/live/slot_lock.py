"""Trava de exclusividade por SLOT, imposta pelo SISTEMA OPERACIONAL.

Por que existe (auditoria adversarial de 2026-08-28): toda a guarda contra
processo duplicado morava em `dashboard/live_control.start()` -- lock de
thread mais varredura de PID orfao, e que so' roda quando alguem clica
"Iniciar" no painel. `python scripts/run_live.py --slot ... loop` chamado
direto (linha de comando, ou um servico NSSM apontando pro mesmo slot, o
cenario que o proprio `DEPLOY.md` descreve) nao passa por nenhuma delas.

O estrago de dois processos no MESMO slot nao e' teorico: eles compartilham
o `magic`, entao `open_position()`/`pending_orders()` de cada um enxergam o
que o OUTRO fez como se fosse deles. `_check_atividade_estranha` nunca
aponta nada, porque o magic bate. Cada um decide sozinho sobre a MESMA
posicao NETTING, e cada um passa no proprio teto de capital -- que e' o
padrao do incidente de 2026-08-28, com a soma faltando entre PROCESSOS.

**Por que trava de SO e nao arquivo com PID.** Um arquivo com PID precisa
de vivacidade pra distinguir "outro processo esta rodando" de "sobrou lixo
de um processo morto" -- no Windows isso e' um `tasklist`, que ja se sabe
engasgar (ver `dashboard.live_control._pids_alive`) e cuja falha e'
ambigua. A trava do SO nao tem esse problema: ela morre COM o processo, seja
qual for a causa (Ctrl+C, kill, falta de luz, BSOD). Nao existe trava velha.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_ROOT = Path(__file__).resolve().parents[2]
LOCK_DIR = _ROOT / "db" / "locks"


class SlotEmUso(RuntimeError):
    """Ja ha um processo vivo operando este slot."""


def _caminho(slot_id: str) -> Path:
    # `slot_id` vem de `core.config.slot_by_id` e ja e' um identificador
    # (`dt-<robo>-<ativo>-<modo>`), mas isto e' nome de ARQUIVO: qualquer
    # caractere fora do conjunto seguro vira `_` para nunca escapar de
    # `LOCK_DIR`.
    seguro = "".join(c if (c.isalnum() or c in "-_.@") else "_" for c in slot_id)
    return LOCK_DIR / f"{seguro}.lock"


def _tenta_travar(fd: int) -> bool:
    """`True` se conseguiu a trava exclusiva NAO BLOQUEANTE."""
    try:
        import msvcrt  # Windows -- o unico SO onde a operacao real roda
    except ImportError:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _destrava(fd: int) -> None:
    try:
        import msvcrt
    except ImportError:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        return
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


@contextmanager
def lock_slot(slot_id: str, lock_dir: Path | None = None) -> Iterator[Path]:
    """Segura a exclusividade do slot enquanto o bloco roda.

    Levanta `SlotEmUso` se outro processo ja a tem -- e' o desfecho certo:
    recusar subir e' sempre melhor que dois robos decidindo sobre a mesma
    posicao. Nao existe "forcar": quem quer trocar de processo para o que
    esta rodando primeiro."""
    pasta = Path(lock_dir) if lock_dir is not None else LOCK_DIR
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / _caminho(slot_id).name
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        # 1 byte e' o bastante: `msvcrt.locking` trava uma REGIAO, e o
        # arquivo precisa ter esse byte para a regiao existir.
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        if not _tenta_travar(fd):
            raise SlotEmUso(
                f"ja ha um processo operando o slot '{slot_id}' nesta maquina "
                f"(trava {caminho}). Dois processos no mesmo slot compartilham o "
                "magic da corretora: cada um enxerga a ordem e a posicao do outro "
                "como suas, e cada um passa no proprio teto de capital. Pare o "
                "que esta rodando antes de subir outro."
            )
        # O CONTEUDO do arquivo nao significa nada de proposito -- quem
        # responde "esta em uso?" e' a trava do SO, nao um PID escrito aqui.
        # Um PID gravado seria exatamente a fonte de ambiguidade que esta
        # trava existe para eliminar.
        yield caminho
    finally:
        _destrava(fd)
        os.close(fd)
