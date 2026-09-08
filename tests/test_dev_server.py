"""A limpeza do `dev.bat` virou Python para poder rodar no Ctrl+C -- e para
poder ser testada.

Contexto (2026-09-08): `--kill-robots` e a liberacao da porta 8000 moravam
DEPOIS da linha do uvicorn no `dev.bat`. Ctrl+C num `.bat` faz o cmd
perguntar "Deseja finalizar o arquivo em lotes (S/N)?" e responder "S" mata o
script ali -- entao a flag quase nunca disparava. O dono passou a flag, deu
Ctrl+C, respondeu "S", e os tres robos continuaram vivos. Ver a docstring de
`scripts/dev_server.py`.

O que da' pra' travar em teste e' a leitura do `netstat` (em batch era um
`for /f "tokens=5"`, inexercitavel). Matar processo e esperar o uvicorn sair
nao entram aqui de proposito: o teste passaria a depender do que esta rodando
na maquina, e a suite roda em paralelo com robos reais ao vivo."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "dev_server", Path(__file__).resolve().parent.parent / "scripts" / "dev_server.py")
dev_server = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("dev_server", dev_server)
_SPEC.loader.exec_module(dev_server)


NETSTAT = """
Conexoes ativas

  Proto  Endereco local         Endereco externo       Estado           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1234
  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       34024
  TCP    127.0.0.1:8000         127.0.0.1:59122        ESTABLISHED     34024
  TCP    127.0.0.1:8770         0.0.0.0:0              LISTENING       23104
  TCP    192.168.0.10:8000      0.0.0.0:0              LISTENING       9999
"""


def test_acha_o_pid_que_escuta_a_porta():
    assert dev_server.dono_da_porta_em(NETSTAT, 8000) == "34024"
    assert dev_server.dono_da_porta_em(NETSTAT, 8770) == "23104"


def test_porta_livre_devolve_none():
    assert dev_server.dono_da_porta_em(NETSTAT, 9001) is None


def test_ignora_conexao_estabelecida_e_outra_interface():
    """So' LISTENING em 127.0.0.1 conta.

    A conexao ESTABLISHED na mesma porta e' um cliente, nao o dono do socket;
    e o 192.168.0.10:8000 e' outra interface -- matar o PID dela seria matar
    um processo que nao tem nada a ver com o dashboard. Casar `:8000` solto
    (o que um `in linha` ingenuo faria) pegaria os dois."""
    so_ruido = "\n".join(
        l for l in NETSTAT.splitlines() if "127.0.0.1:8000         0.0.0.0:0" not in l)
    assert dev_server.dono_da_porta_em(so_ruido, 8000) is None


@pytest.mark.parametrize("saida", ["", "\n", "Conexoes ativas\n"])
def test_saida_vazia_ou_sem_tabela_nao_explode(saida):
    """`netstat` pode falhar ou vir vazio -- isto roda no caminho de
    encerramento, onde levantar excecao mataria a limpeza pela metade."""
    assert dev_server.dono_da_porta_em(saida, 8000) is None
