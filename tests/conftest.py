import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _assinatura(caminho: Path):
    """Impressão digital barata do arquivo: (mtime_ns, tamanho). `None` se não
    existe — quem não tem banco também não pode ter banco sujo."""
    try:
        st = caminho.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


@pytest.fixture(autouse=True)
def _banco_ao_vivo_intocado():
    """Nenhum teste pode escrever no banco de operação REAL (`db/live.sqlite`).

    Existe porque o vazamento já aconteceu DUAS vezes, das duas o mesmo jeito:
    uma fixture isola `journal.live_store.live_journal()` (o default da função)
    mas esquece de algum módulo que resolveu o caminho por conta própria — hoje
    `live.intraday_runtime.LIVE_DB_PATH`, que é um `from ... import` com bind
    estático e guardado no `__init__` do runtime, portanto imune ao patch do
    default. O resultado é uma conta fantasma com dinheiro dentro do banco que
    comanda o robô de verdade.

    Da primeira vez ficou meses escondido (o nome de slot usado no teste já
    existia no banco, e o `ON CONFLICT DO NOTHING` engolia a escrita em
    silêncio). Lembrar de patchar cada módulo novo em cada arquivo de teste não
    é uma defesa — isto é: falha o teste que sujou, no momento em que sujou.

    Comparar (mtime_ns, tamanho) pega qualquer escrita commitada; o SQLite
    atualiza os dois ao fechar a transação. Custo: um `stat()` por teste.
    """
    real = Path(__file__).resolve().parents[1] / "db" / "live.sqlite"
    antes = _assinatura(real)
    yield
    depois = _assinatura(real)
    if antes != depois:
        pytest.fail(
            f"este teste escreveu no banco de operação REAL ({real}).\n"
            "Alguma fixture não isolou tudo: além de "
            "`live_store.live_journal.__wrapped__.__defaults__`, é preciso "
            "patchar `live.runtime.DB_PATH` e `live.intraday_runtime."
            "LIVE_DB_PATH` (ambos são bind estático de módulo).\n"
            f"antes={antes} depois={depois}"
        )
