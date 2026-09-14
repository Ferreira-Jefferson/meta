"""Uma sessao IPC por PROCESSO, nao uma por leitura.

Regressao de 2026-09-14: os cinco slots ao vivo gravaram, em 4 episodios do
mesmo pregao, `feed nao conseguiu LER o terminal: connect: ... last_error=
(-6, 'Terminal: Authorization failed')` -- todos na mesma janela de segundos,
enquanto o `MT5Broker` e o `MT5Feed` dos MESMOS processos nao reclamavam de
nada. A diferenca era exatamente esta: os dois ultimos chamam
`mt5.initialize()` uma vez; o feed intradiario chamava a cada busca, e com
credenciais isso repede autorizacao ao servidor da corretora.

Sem terminal MT5 real -- `MetaTrader5` FALSO, mesma tecnica de
`tests/test_market_data_intraday.py`.
"""
from __future__ import annotations

import types

import pytest

from market_data_intraday import mt5_connection


@pytest.fixture(autouse=True)
def _sessao_limpa():
    """Cada teste comeca sem sessao. Em producao a invalidacao e' automatica
    (o cache guarda o MODULO, e um fake novo ja' invalida), mas os testes
    daqui reusam o mesmo fake de proposito."""
    mt5_connection.esquecer_sessao()
    yield
    mt5_connection.esquecer_sessao()


def _fake(initialize_ok=True, terminal_vivo=True):
    mod = types.ModuleType("MetaTrader5")
    mod.chamadas = []

    def initialize(**kwargs):
        mod.chamadas.append(kwargs)
        ok = initialize_ok() if callable(initialize_ok) else initialize_ok
        return ok

    mod.initialize = initialize
    mod.terminal_info = lambda: (
        object() if (terminal_vivo() if callable(terminal_vivo) else terminal_vivo) else None
    )
    return mod


CREDENCIAIS = dict(login=11724331, password="x", server="Rico-PRD", path=r"C:\mt5\terminal64.exe")


def test_segunda_leitura_nao_repede_autorizacao():
    """O CORACAO do bug: com a sessao de pe, `initialize()` nao e' chamado de
    novo. Era 1 autorizacao a cada 5s por slot, 5 slots, o pregao inteiro."""
    mod = _fake()

    for _ in range(50):
        assert mt5_connection.conectar(mod, **CREDENCIAIS) is True

    assert len(mod.chamadas) == 1
    assert mod.chamadas[0] == {"path": CREDENCIAIS["path"], "login": CREDENCIAIS["login"],
                               "password": "x", "server": "Rico-PRD"}


def test_sessao_cacheada_sobrevive_a_um_initialize_que_passaria_a_falhar():
    """Exatamente o episodio real: o terminal passa a recusar autorizacao
    (`-6`) mas a sessao IPC continua viva. O feed NAO pode declarar cegueira
    por causa de uma pergunta que ele nao precisava fazer."""
    autoriza = {"ok": True}
    mod = _fake(initialize_ok=lambda: autoriza["ok"])

    assert mt5_connection.conectar(mod, **CREDENCIAIS) is True
    autoriza["ok"] = False

    assert mt5_connection.conectar(mod, **CREDENCIAIS) is True
    assert len(mod.chamadas) == 1


def test_ipc_caido_reconecta():
    """Cachear nao pode virar cegueira permanente: `terminal_info() -> None`
    e' sessao morta, e ai `initialize()` tem de rodar de novo."""
    vivo = {"v": True}
    mod = _fake(terminal_vivo=lambda: vivo["v"])

    assert mt5_connection.conectar(mod, **CREDENCIAIS) is True
    vivo["v"] = False
    assert mt5_connection.conectar(mod, **CREDENCIAIS) is True

    assert len(mod.chamadas) == 2


def test_credenciais_diferentes_invalidam_o_cache():
    mod = _fake()

    assert mt5_connection.conectar(mod, **CREDENCIAIS) is True
    assert mt5_connection.conectar(mod, **{**CREDENCIAIS, "login": 999}) is True

    assert len(mod.chamadas) == 2


def test_terminal_info_ausente_nao_quebra():
    """Modulo limitado (fake antigo, ambiente estranho): assume sessao viva em
    vez de estourar `AttributeError` dentro do feed ao vivo."""
    mod = _fake()
    del mod.terminal_info

    assert mt5_connection.conectar(mod, **CREDENCIAIS) is True
    assert mt5_connection.conectar(mod, **CREDENCIAIS) is True
    assert len(mod.chamadas) == 1


def test_retenta_antes_de_desistir_e_para_no_primeiro_sucesso():
    """`-6` no nascimento da sessao costuma durar menos que um passo do
    supervisor (5s). Retentar 0,35s depois evita o alarme sem atrasar nada no
    caminho feliz."""
    respostas = iter([False, True])
    esperas = []
    mod = _fake(initialize_ok=lambda: next(respostas))

    assert mt5_connection.conectar(mod, sleep_fn=esperas.append, **CREDENCIAIS) is True

    assert len(mod.chamadas) == 2
    assert esperas == [mt5_connection.ESPERA_ENTRE_TENTATIVAS_S]


def test_desiste_depois_do_teto_e_nao_guarda_sessao():
    esperas = []
    mod = _fake(initialize_ok=False)

    assert mt5_connection.conectar(mod, sleep_fn=esperas.append, **CREDENCIAIS) is False

    assert len(mod.chamadas) == mt5_connection.TENTATIVAS_DE_CONEXAO
    assert len(esperas) == mt5_connection.TENTATIVAS_DE_CONEXAO - 1
    # Falhou = nao ha sessao para cachear; a proxima leitura tenta de novo.
    assert mt5_connection.conectar(mod, sleep_fn=esperas.append, **CREDENCIAIS) is False
    assert len(mod.chamadas) == 2 * mt5_connection.TENTATIVAS_DE_CONEXAO


def test_excecao_no_initialize_vira_false_nao_propaga():
    """Contrato dos dois feeds: lista vazia, NUNCA excecao (ver
    `live/feed_health.py`)."""
    mod = _fake()
    mod.initialize = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("terminal sumiu"))

    assert mt5_connection.conectar(mod, sleep_fn=lambda s: None, **CREDENCIAIS) is False


def test_sem_credenciais_so_anexa_ao_terminal_aberto():
    mod = _fake()

    assert mt5_connection.conectar(mod) is True

    assert mod.chamadas == [{}]


def test_modulo_diferente_invalida_o_cache():
    """Isolamento entre testes (e entre fakes) sai de graca do cache guardar o
    MODULO: um `sys.modules["MetaTrader5"]` trocado nunca herda a sessao do
    anterior."""
    a, b = _fake(), _fake()

    assert mt5_connection.conectar(a, **CREDENCIAIS) is True
    assert mt5_connection.conectar(b, **CREDENCIAIS) is True

    assert len(a.chamadas) == 1
    assert len(b.chamadas) == 1
