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


_DB_ROOT = Path(__file__).resolve().parents[1] / "db"

# Caminho -> dica de qual patch falta, para a mensagem de falha apontar
# direto pro que esquecer causa (em vez de só dizer "algo vazou").
_CAMINHOS_REAIS_PROIBIDOS = {
    _DB_ROOT / "live.sqlite": (
        "Alguma fixture não isolou tudo: além de "
        "`live_store.live_journal.__wrapped__.__defaults__`, é preciso "
        "patchar `live.runtime.DB_PATH` e `live.intraday_runtime."
        "LIVE_DB_PATH` (ambos são bind estático de módulo)."
    ),
    # Achado em auditoria (2026-08-28): `dashboard.live_control.status_all()`
    # AUTOCORRIGE o arquivo (zera `pid`/`started_at`) quando encontra um PID
    # que já morreu — então basta uma rota de `/operacao` rodar sem o patch de
    # `_STATE_PATH` (ex.: `TestClient(app).get("/operacao")` sem passar por
    # `isolated_journal`/`diario`) para ela reescrever o arquivo de estado
    # REAL do dono. Foi assim que dois testes (`test_dashboard_app.py::
    # test_operacao_mostra_os_cartoes_na_ordem_pedida` e o equivalente em
    # `test_dashboard_daytrade_robot.py`) piscavam conforme os robôs reais do
    # dono estivessem rodando ou não na máquina no momento do teste.
    _DB_ROOT / "live_process.json": (
        "Alguma fixture não isolou `dashboard.live_control._STATE_PATH` — "
        "toda rota/teste que chama `live_control.status()`/`status_all()`/"
        "`start()`/`stop()`/`_write_state()` precisa de "
        "`monkeypatch.setattr(live_control, \"_STATE_PATH\", tmp_path / "
        "\"live_process.json\")`. Ver `tests/test_dashboard_app.py::"
        "isolated_journal` para o padrão."
    ),
}


@pytest.fixture(autouse=True)
def _banco_ao_vivo_intocado():
    """Nenhum teste pode escrever em arquivo de estado de operação REAL
    (`db/live.sqlite`, `db/live_process.json`, ... — ver
    `_CAMINHOS_REAIS_PROIBIDOS`).

    Existe porque o vazamento já aconteceu mais de uma vez, sempre do mesmo
    jeito: uma fixture isola o caminho principal (`journal.live_store.
    live_journal()`, o default da função) mas esquece de algum módulo que
    resolveu OUTRO caminho por conta própria — `live.intraday_runtime.
    LIVE_DB_PATH` da primeira vez (bind estático, imune ao patch do
    default), `dashboard.live_control._STATE_PATH` da segunda (uma rota de
    `/operacao` chamada sem isolar, que autocorrige `db/live_process.json`
    de verdade quando acha um PID morto — ver o comentário no dicionário
    acima). O resultado, nos dois casos, é o mesmo: estado fantasma
    escrito por cima do que comanda o robô de verdade.

    Da primeira vez ficou meses escondido (o nome de slot usado no teste já
    existia no banco, e o `ON CONFLICT DO NOTHING` engolia a escrita em
    silêncio). Lembrar de patchar cada módulo novo em cada arquivo de teste não
    é uma defesa — isto é: falha o teste que sujou, no momento em que sujou.

    Comparar (mtime_ns, tamanho) pega qualquer escrita commitada; o SQLite
    atualiza os dois ao fechar a transação, e `_write_state()` troca o
    arquivo inteiro via `os.replace` (nunca edita em lugar), então qualquer
    reescrita também atualiza os dois. Custo: um `stat()` por caminho, por
    teste — não pega leitura pura (ver docstring do módulo para o que uma
    leitura sozinha ainda pode custar: conteúdo dependente do ambiente,
    não corrupção).

    O guard vê a ASSINATURA do arquivo, não quem a mudou — e o dashboard
    (`live_control.status_all()` autocorrigindo um PID morto) escreve nos
    mesmos caminhos, de outro processo, enquanto a suíte roda. Por isso a
    mensagem de falha pergunta QUEM escreveu antes de acusar o teste:
    diagnosticar como bug de código uma suíte suja por robô ao vivo já
    custou tempo real aqui (2026-08-26: 2 falhas e 41 erros que eram
    todos falsos). O `db/live.sqlite` quase nunca dá esse falso positivo
    porque em WAL a escrita vai para o `-wal` e o arquivo principal só
    muda no checkpoint; `db/live_process.json` não tem esse amortecedor.
    """
    antes = {caminho: _assinatura(caminho) for caminho in _CAMINHOS_REAIS_PROIBIDOS}
    yield
    for caminho, dica in _CAMINHOS_REAIS_PROIBIDOS.items():
        depois = _assinatura(caminho)
        if antes[caminho] != depois:
            pytest.fail(
                f"o arquivo de estado de operação REAL ({caminho}) mudou "
                "durante este teste.\n"
                f"{dica}\n"
                "ANTES de tratar como bug do teste: um dashboard ou robô ao "
                "vivo rodando nesta máquina escreve nestes mesmos caminhos, "
                "de outro processo. Se o teste isola tudo e a mudança veio "
                "de fora, a suíte está contaminada pelo ambiente, não pelo "
                "código — pare os processos reais e rode de novo antes de "
                "mudar qualquer coisa.\n"
                f"antes={antes[caminho]} depois={depois}"
            )
