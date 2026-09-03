"""Trava de exclusividade ENTRE PROCESSOS para o par "consultar margem
livre -> enviar ordem" (`LICOES_DE_PRODUCAO.md`, item 3.13).

Por que existe
---------------
Cada slot de day trade roda como um processo do SO separado
(`subprocess.Popen`, ver `dashboard/live_control.py`), mas todos logam no
MESMO terminal MT5 -- uma unica margem FISICA. `IntradayLiveRuntime.
_check_margem_da_conta` le `margin_free` fresco a cada chamada, sem cache
(de proposito: e' o unico numero que ja desconta o que os outros slots e o
proprio dono tem aberto na mao). Isso resolve o problema DENTRO de um
processo, mas nao entre processos: nada impedia dois processos de lerem a
MESMA margem livre otimista, cada um passar no proprio teto, e os dois
mandarem ordem -- comprometendo mais margem do que a conta tem. E' o padrao
exato do incidente da Parte 0 (item 3.2, "duas entradas independentes
passaram, cada uma sozinha, contra uma conta que comportava uma"), so' que
a soma que falta agora e' entre PROCESSOS, nao entre ordens do mesmo laco.

Por que trava de ARQUIVO do SO, e nao um mutex/semaforo Python
----------------------------------------------------------------
`threading.Lock` so' serializa THREADS dentro de UM processo -- cada slot e'
um PROCESSO do SO diferente, entao um lock em memoria de um processo e'
invisivel para os outros. A trava tem de ser imposta pelo SO (mesmo
raciocinio de `live/slot_lock.py`, que resolve o mesmo tipo de problema para
"dois processos no mesmo slot").

A trava de arquivo do SO (`msvcrt.locking` no Windows, `fcntl.flock` em
qualquer outro lugar) tem uma propriedade que resolve de graca o requisito
"a prova de processo morto": ela e' mantida pelo KERNEL contra o file
descriptor do processo, entao morre JUNTO com o processo -- Ctrl+C, kill,
falta de luz, BSOD, tanto faz. Nao existe "trava orfa" para limpar nem PID
para checar vivacidade (a mesma razao documentada em `slot_lock.py`).

Ainda assim `acquire_margin_gate` usa TIMEOUT na aquisicao: um processo
VIVO pode segurar a trava por mais tempo que o esperado (`order_send` lento,
terminal engasgado). Sem timeout, os outros slots ficariam bloqueados
indefinidamente -- e um robo bloqueado com posicao aberta e' o pior cenario
possivel (ver LICOES_DE_PRODUCAO.md, "robo inerte com posicao aberta").
Estourar o timeout levanta `MargemTravada`; o chamador tem de tratar isso
como uma consulta que FALHOU (mesma politica de "nao sei" de
`_check_margem_da_conta` e do item 1.6 do registro de producao: "nao sei"
nunca autoriza uma acao), nunca como liberacao para mandar a ordem sem
checar margem.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

_ROOT = Path(__file__).resolve().parents[2]

#: Ao lado do estado compartilhado do live (`db/live.sqlite`, `db/locks/`)
#: -- todo slot de day trade le/escreve o MESMO banco `live.sqlite`, entao e'
#: o lugar natural para o arquivo que representa a margem fisica UNICA que
#: todos compartilham (um so' login MT5 hoje; se um dia houver mais de um
#: login, o `lock_path` explicito de `acquire_margin_gate` e' o gancho para
#: um arquivo por login).
DEFAULT_LOCK_PATH = _ROOT / "db" / "locks" / "margem_mt5.lock"

#: Quanto tempo esperar pela trava antes de desistir. A secao critica real
#: (consultar `margin_free` + mandar 1 ordem) e' da ordem de dezenas ou
#: poucas centenas de ms -- round-trip ate o terminal MT5. Alguns segundos ja
#: cobrem folga generosa (terminal lento, GC, agendamento do SO) sem prender
#: um slot saudavel atras de um vizinho anormal por tempo longo o bastante
#: para importar ao dono.
DEFAULT_TIMEOUT_SECONDS = 5.0

#: Intervalo entre tentativas dentro da janela de timeout: rapido o
#: suficiente para nao desperdicar timeout em sono parado, devagar o
#: suficiente para nao virar busy-wait custoso.
_POLL_SECONDS = 0.05


class MargemTravada(RuntimeError):
    """Nao foi possivel obter a trava de margem dentro do timeout.

    Isto NAO significa "a conta esta sem margem" -- significa "nao consegui
    verificar com seguranca porque outro processo estava na secao critica
    ha mais tempo que o esperado". O chamador trata como consulta que
    falhou (item 1.6 do LICOES_DE_PRODUCAO.md): nunca envia a ordem sem
    checar, e nunca grava isto no diario como se fosse recusa por margem de
    verdade -- sao duas informacoes diferentes para o dono."""


def _tenta_travar(fd: int) -> bool:
    """`True` se conseguiu a trava exclusiva NAO BLOQUEANTE sobre `fd`."""
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
def acquire_margin_gate(
    lock_path: Optional[Path] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Segura a exclusividade da CONTA (margem fisica compartilhada por todos
    os slots) enquanto o bloco roda.

    Use em volta de SO' "consultar margem -> mandar a ordem" -- nada de
    logica de estrategia, espera de preenchimento ou I/O de banco dentro do
    bloco (ver docstring do modulo): quanto mais curta a secao critica,
    menos tempo os outros slots ficam esperando.

    Levanta `MargemTravada` se nao conseguir a trava dentro de `timeout`
    segundos -- ver a docstring da excecao para o tratamento esperado."""
    caminho = Path(lock_path) if lock_path is not None else DEFAULT_LOCK_PATH
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        # 1 byte e' o bastante: `msvcrt.locking` trava uma REGIAO, e o
        # arquivo precisa ter esse byte para a regiao existir (mesma tecnica
        # de `slot_lock.py`).
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        prazo = time.monotonic() + max(0.0, timeout)
        while not _tenta_travar(fd):
            if time.monotonic() >= prazo:
                raise MargemTravada(
                    f"nao consegui a trava de margem ({caminho}) em "
                    f"{timeout:.1f}s -- outro processo esta na secao critica "
                    "ha mais tempo que o esperado."
                )
            time.sleep(_POLL_SECONDS)
        yield
    finally:
        _destrava(fd)
        os.close(fd)
