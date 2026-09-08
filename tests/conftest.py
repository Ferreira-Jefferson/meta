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


@pytest.fixture(autouse=True)
def _travas_de_slot_isoladas(tmp_path_factory, monkeypatch):
    """Nenhum teste pega trava de slot na pasta REAL (`db/locks/`).

    `scripts/run_live.py::cmd_loop` abre `lock_slot(slot.id)` — a trava de
    SO que impede dois processos no mesmo slot. Os testes de CLI chamam
    `cmd_loop` de verdade, com `slot="swing"`, então sem isto eles pegam
    `db/locks/swing.lock`: o MESMO arquivo que o robô de produção usa.
    Duas consequências, as duas observadas:

    1. Dois workers do xdist rodando dois testes de `cmd_loop` ao mesmo
       tempo disputam o arquivo único e um leva `SlotEmUso` — falha
       intermitente que passa quando rodada sozinha (foi assim que
       apareceu, em 1 de 3 rodadas da suíte).
    2. Pior que a falha do teste: enquanto a suíte segura `swing.lock`, um
       robô REAL tentando subir naquele slot é recusado. A suíte não pode
       ter poder de veto sobre a operação.

    Isolar por prevenção, não por detecção: o guard abaixo
    (`_banco_ao_vivo_intocado`) falha DEPOIS que o teste sujou, e aqui dá
    para simplesmente tornar a pasta real inalcançável de dentro do
    processo de teste. Detecção continuaria fraca de qualquer forma —
    tomar uma trava já existente não muda mtime nem tamanho do arquivo,
    então o caso pior (teste segurando a trava do robô de verdade) passaria
    despercebido por uma assinatura de arquivo.

    `tests/test_slot_lock.py` não é afetado: todo teste de lá já passa
    `lock_dir=tmp_path` explícito, inclusive o subprocesso."""
    from live import slot_lock

    monkeypatch.setattr(slot_lock, "LOCK_DIR", tmp_path_factory.mktemp("locks"))


@pytest.fixture(autouse=True)
def _cotacao_do_terminal_desligada(monkeypatch):
    """Nenhum teste pergunta o preço ao terminal MT5 do dono.

    `dashboard.live_control.preco_de_referencia` (2026-09-08) passou a ler a
    cotação AO VIVO antes de cair no parquet, porque o piso de caixa de uma
    ação é `preço x 100 x 2` e o parquet pode estar dias atrasado. Ótimo em
    produção, veneno na suíte, por três motivos:

    1. **Não-determinismo.** O preço muda a cada minuto. Um teste que afirma
       "mín. R$30 para PMAM3" passaria de manhã e falharia à tarde.
    2. **I/O de corretora dentro do teste.** A ficha da `gremah` lista 9
       ativos; renderizá-la abriria 9 consultas no terminal que está operando
       dinheiro real ao lado. Mesmo espírito de `_travas_de_slot_isoladas`
       acima: a suíte não pode competir com a operação.
    3. **Cache de módulo vazando entre testes.** `_preco_cache` é global e
       tem TTL de 30s — sem limpar, o preço lido num teste apareceria no
       seguinte, e sob `--dist load` a ordem de coleta não é a de execução.
       Isso é exatamente a dependência de ordem que o `AGENTS.md` proíbe.

    Desligar aqui devolve o comportamento anterior (parquet, fixo no repo) a
    TODO teste que não peça outra coisa. Um teste que queira exercitar o
    caminho ao vivo repatcha `_cotacao_do_terminal` com o valor que quiser --
    é a única porta de I/O daquele caminho, de propósito."""
    from dashboard import live_control

    monkeypatch.setattr(live_control, "_cotacao_do_terminal", lambda symbol: None)
    live_control._preco_cache.clear()
    yield
    live_control._preco_cache.clear()

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
