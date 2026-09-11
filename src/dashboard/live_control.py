"""Controle dos processos supervisores (`scripts/run_live.py loop`) a partir
do dashboard — um botão "Iniciar"/"Parar" por SLOT, em vez de terminal.

Fica em `dashboard/` (orquestração) e nunca decide nada por conta própria:
só liga/desliga, como um processo, o MESMO `scripts/run_live.py` que já
existia — a decisão de compra/venda continua inteiramente dentro de
`live/runtime.py` (swing) ou `live/intraday_runtime.py` (day trade). O
estado dos processos (PID, config, início) é persistido em
`db/live_process.json` para sobreviver a um restart do próprio dashboard
(o botão "Parar" precisa continuar funcionando mesmo se você fechar e
reabrir o navegador ou reiniciar o servidor do dashboard).

UM PROCESSO POR SLOT (2026-08-21)
---------------------------------
Até esta data isto era um singleton: um PID, um log, e `start()` recusava
qualquer segundo robô. O dono passou a operar dois robôs ao mesmo tempo
(ver `core.config.SLOTS`), então o arquivo de estado virou v2:

    {"version": 2, "slots": {"<slot>": {"pid": ..., "started_at": ...,
                                        "config": {...}}}}

Um arquivo LEGADO (formato v1, chaves no topo) é adotado como o slot
`swing` na leitura — só para que um PID órfão de antes da mudança continue
sendo matável pelo botão "Parar", nunca para ressuscitar o formato antigo:
a primeira escrita já grava v2.

O log também passou a ser por slot (`db/live_process.<slot>.log`): dois
processos escrevendo no mesmo arquivo entrelaçariam linhas e
`_tail_log()` explicaria a morte de um robô com o log do outro.

`_start_lock` continua ÚNICO de propósito (não um lock por slot): os dois
slots compartilham o MESMO arquivo de estado, e locks separados correriam
no read-modify-write desse arquivo — o segundo `_write_state` sobrescreveria
o slot que o primeiro acabou de gravar.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
_STATE_PATH = _ROOT / "db" / "live_process.json"
_LOG_DIR = _ROOT / "db"
_SCRIPT = _ROOT / "scripts" / "run_live.py"
_SECRETS_PATH = _ROOT / "db" / "live_secrets.json"

# Slot que adota um arquivo de estado no formato v1 (pré-2026-08-21) e o log
# `db/live_process.log` antigo — era o único robô que existia, e era de swing.
_LEGACY_SLOT = "swing"


def _log_path(slot: str) -> Path:
    """`db/live_process.<slot>.log`. O slot legado mantém o nome antigo
    (`db/live_process.log`) para o log de uma operação já em curso não sumir
    da tela no dia da migração."""
    if slot == _LEGACY_SLOT:
        return _LOG_DIR / "live_process.log"
    return _LOG_DIR / f"live_process.{slot}.log"

# Segundos entre o `Popen` do supervisor e a checagem de prova de vida
# (`start()`, ver docstring lá embaixo) — módulo-nível, monkeypatchável em
# teste (senão o teste esperaria de verdade). Um processo que vai falhar cedo
# (terminal MT5 ausente, credencial errada) normalmente já morreu bem antes
# disso; 2s é suficiente sem atrasar o clique "Iniciar" de forma perceptível.
_STARTUP_GRACE_SECONDS = 2.0

# Serializa `start()` inteira (correção pós-code-review, crítico nº2): dois
# cliques em "Iniciar" quase simultâneos chegam por threads diferentes do
# `asyncio.to_thread` (dashboard roda single-process, sem `workers=N` — ver
# `scripts/run_dashboard.py`), e o guard `status() is not None` só enxerga um
# robô já iniciado DEPOIS que `_write_state` roda no fim da função. Sem lock,
# as duas threads passam pelo guard antes de qualquer uma escrever estado e
# ambas dão `Popen` — dois processos `run_live.py loop` órfãos, só o segundo
# rastreável. O lock precisa envolver do guard até `_write_state` (não só o
# `Popen`) para a segunda chamada necessariamente ver o estado já gravado.
_start_lock = threading.Lock()

# Campos aceitos em `save_credentials`/exibidos no form. `_SECRET_FIELDS` sao
# os que NUNCA voltam para o HTML (nem mascarados) — so um booleano
# "configurado" via `credential_status()`; os demais (chat id, host, usuario
# etc.) nao sao segredo em si e podem ser reexibidos para o usuario conferir.
CREDENTIAL_FIELDS = (
    "telegram_bot_token", "telegram_chat_id",
    "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_to", "smtp_from", "smtp_tls",
    "mt5_login", "mt5_password", "mt5_server", "mt5_terminal_path",
    # "Ações por lote" NAO e mais campo salvo aqui (decisao do dono,
    # 2026-08-20): e detectado sozinho a cada "Iniciar operacao" via
    # `detect_shares_per_lot()` (symbol_info do terminal MT5 conectado),
    # porque e um dado que o proprio terminal ja sabe -- pedir pro usuario
    # abrir o MT5 e conferir na mao era trabalho que o codigo podia fazer.
)
_SECRET_FIELDS = frozenset({"telegram_bot_token", "smtp_password", "mt5_password"})
_CHANNEL_FIELDS = {
    "telegram": ("telegram_bot_token", "telegram_chat_id"),
    "smtp": ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_to", "smtp_from", "smtp_tls"),
    "mt5": ("mt5_login", "mt5_password", "mt5_server", "mt5_terminal_path"),
}
_ENV_VAR_BY_FIELD = {
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN", "telegram_chat_id": "TELEGRAM_CHAT_ID",
    "smtp_host": "SMTP_HOST", "smtp_port": "SMTP_PORT", "smtp_user": "SMTP_USER",
    "smtp_password": "SMTP_PASSWORD", "smtp_to": "SMTP_TO", "smtp_from": "SMTP_FROM",
    "smtp_tls": "SMTP_TLS", "mt5_login": "MT5_LOGIN", "mt5_password": "MT5_PASSWORD",
    "mt5_server": "MT5_SERVER", "mt5_terminal_path": "MT5_TERMINAL_PATH",
}


_CLI_MODULE = None


def _load_cli():
    """Importa `scripts/run_live.py` como módulo — reusa o MESMO `build()`
    que a linha de comando usa para montar o `LiveRuntime`, para o clique do
    botão criar a conta exatamente como `run_live.py init` criaria (sem
    duplicar a lógica de qual broker/política/disjuntor montar).

    Memoizado num cache de módulo: `_resolve_risk_guard()` (usado por
    `live_service.get_status()`) passou a chamar isto em CADA poll HTMX de
    `/operacao/fragment` — sem memoizar, isso re-executaria `run_live.py`
    inteiro (todos os imports de topo, `sys.path.insert`) várias vezes por
    minuto numa página de leitura, custo e efeito colateral gratuitos.
    """
    global _CLI_MODULE
    if _CLI_MODULE is None:
        spec = importlib.util.spec_from_file_location("run_live_cli", _SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CLI_MODULE = module
    return _CLI_MODULE


@dataclass
class ProcessConfig:
    """Sem `floor`/`daily_loss_limit`/`monthly_loss_limit`: piso de saque e
    disjuntor de risco não são escolha de quem opera — o robô já sabe qual é
    o valor certo (`official_policy`/`CircuitBreaker` defaults), ver
    docstring de `scripts/run_live.py` seção "Disjuntor de risco".

    `strategy`: chave do robô (`strategy.registry` para swing, `strategy.
    daytrade` para day trade). Numa conta NOVA, quem chama resolve isso a
    partir do robô declarado do slot (`core.config.Slot.robot_key`); numa
    conta JÁ EXISTENTE, sempre `conta.investment_robot` -- nunca recalculado
    do ranking corrente, senão uma conta em operação trocaria de robô
    sozinha só porque o ranking mudou (decisão do dono, 2026-08-19: "nada
    automático" na troca).

    `slot`: vaga de operação (`core.config.SLOTS`) -- é o nome da conta E a
    chave do processo no arquivo de estado.

    `execution_mode`: `"shadow"` (default) journaliza tudo mas NUNCA chama a
    corretora; `"live"` envia ordem de verdade. Default sombra de propósito:
    ao vivo do day trade nunca rodou contra o mercado, e a premissa central
    do robô (ordem-limite preenche no nível tocado) só é verificável medindo
    -- ver `live/intraday_runtime.py`."""
    mode: str
    capital: float
    strategy: str
    slot: str = "swing"
    execution_mode: str = "shadow"
    notify_min_level: str = "warn"
    # Obrigatório sempre (sem valor universal — ver docstring de
    # `live/broker_mt5.py`); `create_account()`/`start()` recusam cedo se
    # vier `None`, em vez de herdar o default `1.0` do argparse.
    mt5_shares_per_lot: Optional[float] = None
    # Mesmo espírito de `mt5_shares_per_lot`: detectado sozinho a cada
    # "Iniciar operação" via `detect_fractional_symbol_map()` (consulta o
    # terminal MT5), nunca digitado pelo usuário. Diferente dele, `None`
    # aqui NÃO bloqueia `start()` -- degrada para o comportamento de sempre
    # (só lote padrão), então uma falha de detecção não impede quem só quer
    # operar lote cheio de continuar operando.
    #
    # SÓ os tickers que REALMENTE têm símbolo de mercado fracionário no
    # terminal (não é mais "ticker -> símbolo resolvido" para todo mundo,
    # ver `detect_fractional_symbol_map`) -- `MT5Broker` decide, a cada
    # ORDEM, se usa lote padrão (GRATUITO na Rico, 2026-08-21) ou
    # fracionário (R$1,90/ordem na Rico) com base na quantidade pedida;
    # este mapa só entra na conta quando o lote padrão não fecha.
    mt5_fractional_map: Optional[dict] = None
    # Mesmo espírito de `mt5_fractional_map`: detectado sozinho a cada
    # "Iniciar operação" via `detect_futures_symbol_map()` (consulta o
    # terminal MT5), nunca digitado pelo usuário -- e nunca bloqueia
    # `start()` (degrada para o sintoma de hoje, ordem de futuro recusada
    # pelo servidor, em vez de impedir quem só opera ação de continuar).
    #
    # Traduz ticker de futuro CONTÍNUO (`"WDO@"`, `"WIN@"` -- só dá cotação
    # no terminal) para o contrato REAL com vencimento em aberto AGORA
    # (padrão RAIZ+letra-do-mês+ano -- a letra/ano exatos dependem só de
    # QUANDO isto roda, nunca fixos aqui) -- é nele que o
    # servidor de fato aceita ordem; achado ao vivo em 2026-08-28 (slot do
    # WDO F1: "Trade disabled" ao mandar
    # ordem em `WDO@`). Como é redetectado a cada início, o contrato virado
    # na rolagem mensal/bimestral (WDO/WIN) é pego sozinho no próximo
    # "Iniciar operação" -- ninguém precisa editar código/config todo mês.
    mt5_symbol_map: Optional[dict] = None


def _read_all() -> dict:
    """Estado de TODOS os slots, normalizado para o formato v2. Um arquivo v1
    (formato singleton, pré-2026-08-21) é adotado como o slot legado — ver
    docstring do módulo."""
    if not _STATE_PATH.exists():
        return {"version": 2, "slots": {}}
    try:
        raw = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 2, "slots": {}}
    if isinstance(raw, dict) and raw.get("version") == 2:
        raw.setdefault("slots", {})
        return raw
    if isinstance(raw, dict) and ("pid" in raw or "config" in raw):
        return {"version": 2, "slots": {_LEGACY_SLOT: raw}}
    return {"version": 2, "slots": {}}


def _read_state(slot: str) -> Optional[dict]:
    return _read_all()["slots"].get(slot)


def _write_state(slot: str, state: Optional[dict]) -> None:
    """Grava (ou apaga) o estado de UM slot, preservando os outros. Chamado
    sempre de dentro de `_start_lock` nos caminhos concorrentes — ver
    docstring do lock.

    Escreve em ARQUIVO TEMPORÁRIO e troca com `os.replace` (achado
    2026-08-24: `write_text` direto no arquivo final deixa uma janela onde um
    leitor concorrente — outro poll HTMX, outra thread deste mesmo processo,
    já que o dashboard roda single-process — pode pegar o arquivo pela
    METADE. `_read_all` trata JSON inválido como "arquivo vazio"
    (`{"slots": {}}`), e uma escrita subsequente baseada nessa leitura vazia
    APAGA DE VEZ todo slot que não seja o que está sendo tocado agora — foi
    assim que `dt-gremah-pmam3-shadow` sumiu inteiro do arquivo (config
    incluída) sem nenhum `_write_state(slot, None)` ter sido chamado para
    ele. `os.replace`/`Path.replace` é atômico no mesmo sistema de arquivos
    (Windows e POSIX): quem lê vê o arquivo INTEIRO antigo ou o INTEIRO novo,
    nunca um caroço no meio."""
    todos = _read_all()
    if state is None:
        todos["slots"].pop(slot, None)
    else:
        todos["slots"][slot] = state
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _STATE_PATH.with_suffix(f"{_STATE_PATH.suffix}.tmp")
    tmp_path.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_STATE_PATH)


def esquecer(slot: str) -> None:
    """Apaga a linha DESTE slot em `db/live_process.json` — pid e config de
    retomada.

    Diferente de `stop()`, que zera só o `pid` de propósito (o formulário do
    cartão continua pré-preenchido depois de parar). Aqui é para quando o
    slot deixa de existir: a config guardada passa a descrever um robô que
    não tem mais para onde retomar, e ressuscitaria com capital velho se o
    dono recriasse o mesmo trio do zero.

    Os dois chamadores são os dois fins de linha de um robô
    (`dashboard.live_teardown.remover` apagando o histórico, e a criação "do
    zero" em cima de um arquivo descartado); nenhum deles precisa do lock
    porque o processo já morreu antes.
    """
    _write_state(slot, None)


def _tail_log(slot: str, max_chars: int = 2_000) -> str:
    """Últimos `max_chars` do log DESTE slot — usado para explicar POR QUE o
    processo morreu logo após subir (ver `start()`)."""
    path = _log_path(slot)
    if not path.exists():
        return "(sem log — o processo morreu antes de escrever qualquer coisa)"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(não foi possível ler o log)"
    return text[-max_chars:]


class _TasklistUnavailable(Exception):
    """`tasklist` não respondeu (ou estourou o timeout) — vivacidade
    INDETERMINADA, não confirmadamente morta. Ver `_pids_alive`."""


def _pid_alive(pid: int) -> bool:
    """Windows não tem um `os.kill(pid, 0)` confiável para checar
    vivacidade — consulta o `tasklist` do próprio sistema.

    Propaga `_TasklistUnavailable` em vez de engolir — ver a mudança de
    2026-08-24 na docstring de `_pids_alive` para o motivo."""
    return pid in _pids_alive([pid])


def _pids_alive(pids) -> set[int]:
    """Subconjunto de `pids` que ainda está de pé — UMA chamada de `tasklist`
    para todos.

    Era um `tasklist` POR pid. Com o slot fixo isso eram 2 subprocessos a cada
    poll de 20s; desde 2026-08-22 o dono abre quantos robôs de day trade
    quiser, e 10 robôs seriam 10 subprocessos a cada 20s numa página que só
    mostra status — custo puro, e num Windows carregado o `tasklist` chega a
    demorar. Um filtro `/FI` por PID não aceita lista, então pedimos a tabela
    toda em CSV e cruzamos aqui.

    Levanta `_TasklistUnavailable` se o `tasklist` não responder, em vez de
    devolver conjunto vazio (mudança 2026-08-24, achado ao vivo: um `tasklist`
    que falha por engasgo passageiro do Windows NÃO prova que os processos
    morreram, mas `status_all()` tratava "conjunto vazio" como "todo mundo
    morreu ao mesmo tempo" e reescrevia `db/live_process.json` apagando
    `pid`/`started_at` de TODOS os slots de uma vez — o painel passava a
    mostrar "parado" para robôs que continuavam rodando de verdade, e um
    clique em "Iniciar" ali subiria um SEGUNDO processo concorrente para a
    mesma conta. "Não sei" tem de significar "não decida agora, tente nas
    próxima leitura" — nunca "vivo" (senão o botão "Parar" nunca teria o que
    matar) nem "morto" (senão um engasgo isolado do `tasklist` derruba o
    estado de todo mundo). Quem chama decide o que fazer com a indeterminação
    — ver `status()`/`status_all()`."""
    pids = {int(p) for p in pids if p is not None}
    if not pids:
        return set()
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise _TasklistUnavailable(str(e)) from e
    vivos: set[int] = set()
    for linha in out.stdout.splitlines():
        campos = [c.strip('"') for c in linha.split('","')]
        if len(campos) < 2:
            continue
        try:
            pid = int(campos[1])
        except ValueError:
            continue
        if pid in pids:
            vivos.add(pid)
    return vivos


def status(slot: str, reconciliar: bool = False) -> Optional[dict]:
    """Estado do processo supervisor DESTE slot, ou `None` se não está
    rodando (nem, com `reconciliar=True`, adotável — ver abaixo).

    Autocorrige: se o arquivo aponta para um PID que já morreu (processo
    caiu, servidor reiniciou sem o serviço) sem ter passado por `stop()`,
    marca como parado em vez de dizer que está rodando quando não está —
    mas preserva a `config`, para `last_config()` continuar funcionando.

    `reconciliar=True` (achado 2026-08-31: reinício do dashboard deixa o
    `Popen` órfão vivo enquanto `db/live_process.json` fica sem o PID novo —
    os 7 slots de day trade, incluindo o robô REAL, ficaram "parados" no
    painel com o processo de pé por trás) pergunta ao SO
    (`_reconciliar_orfao`), antes de desistir, se existe mesmo assim
    exatamente um `run_live.py` deste slot rodando — e se sim, readota o PID
    em vez de deixar o cartão "parado para sempre".

    Default `False` DE PROPÓSITO: a varredura custa ~3s (`Get-CimInstance`
    enumera a máquina inteira, ver `_processos_do_sistema`), e este módulo
    tem um contrato antigo de que a CARGA da página `/operacao` nunca varre
    (`test_a_pagina_nao_varre_o_sistema_ao_carregar`) — só o POLL periódico
    de cada cartão (`app.operacao_fragment`) pode pagar esse custo. Chamar
    com `reconciliar=True` de um caminho de carga de página quebraria esse
    contrato.

    Se o `tasklist` não responder (`_TasklistUnavailable`), a vivacidade é
    INDETERMINADA agora — devolve o estado gravado tal como está, sem
    autocorrigir; a próxima chamada tenta de novo. Ver a docstring de
    `_pids_alive` para o incidente que motivou isto."""
    state = _read_state(slot)
    if state is None or state.get("pid") is None:
        return _reconciliar_orfao(slot) if reconciliar else None
    try:
        alive = _pid_alive(state["pid"])
    except _TasklistUnavailable:
        return state
    if not alive:
        _write_state(slot, {**state, "pid": None, "started_at": None})
        return _reconciliar_orfao(slot) if reconciliar else None
    return state


def status_all(slot_ids=None, reconciliar: bool = False) -> dict[str, Optional[dict]]:
    """`{slot_id: estado ou None}` para os slots pedidos (default: todos os que
    existem hoje, incluindo os de day trade criados pelo dono).

    Faz UMA varredura de processos para o conjunto inteiro (`_pids_alive`), em
    vez de um `tasklist` por slot: o painel repinta a cada 20s e a lista de
    slots agora é aberta. Autocorrige do mesmo jeito que `status()` — PID
    morto vira "parado" no arquivo de estado, preservando a `config`.

    Se o `tasklist` falhar (`_TasklistUnavailable`), NENHUM slot é
    autocorrigido nesta chamada — devolve o que está gravado, como se a
    varredura não tivesse acontecido. Antes disto, uma falha isolada do
    `tasklist` fazia `_pids_alive` devolver conjunto vazio, e este laço
    concluía "todo mundo morreu ao mesmo tempo": TODOS os slots eram
    marcados como parados numa penada só, mesmo com os processos reais
    (confirmados vivos por fora, via Get-Process) continuando a rodar —
    achado ao vivo 2026-08-24, PMAM3 e PMAM3-tick caindo juntos no painel no
    mesmo poll. Ver a docstring de `_pids_alive`.

    `reconciliar=True` (default `False`, mesmo motivo de `status()`: NENHUM
    caminho de carga de página pode pagar `Get-CimInstance` -- ver
    `test_a_pagina_nao_varre_o_sistema_ao_carregar`) reconcilia os slots que
    sobraram sem PID (arquivo nunca teve, ou acabou de perder um que já
    morreu) numa ÚNICA varredura extra para o lote inteiro -- não uma por
    slot, mesmo espírito de `_pids_alive` (uma chamada de sistema para N
    slots, não N chamadas): achado 2026-08-31, ver docstring de `status()`."""
    if slot_ids is None:
        from dashboard.slots import all_slots

        slot_ids = [slot.id for slot in all_slots()]
    estados = {sid: _read_state(sid) for sid in slot_ids}
    try:
        vivos = _pids_alive(
            est["pid"] for est in estados.values() if est and est.get("pid") is not None
        )
    except _TasklistUnavailable:
        return estados
    resultado: dict[str, Optional[dict]] = {}
    pendentes: list[str] = []
    for sid, est in estados.items():
        if est is None or est.get("pid") is None:
            pendentes.append(sid)
            continue
        if est["pid"] not in vivos:
            _write_state(sid, {**est, "pid": None, "started_at": None})
            pendentes.append(sid)
            continue
        resultado[sid] = est
    if pendentes and reconciliar:
        try:
            processos = listar_processos()
        except _TasklistUnavailable:
            processos = None
        for sid in pendentes:
            resultado[sid] = (
                _reconciliar_do_inventario(sid, processos) if processos is not None else None
            )
    elif pendentes:
        for sid in pendentes:
            resultado[sid] = None
    return resultado


def last_config(slot: str) -> Optional[dict]:
    """Última configuração usada neste slot (rodando ou não) — para
    pré-preencher o formulário de retomada sem o usuário digitar tudo de
    novo."""
    state = _read_state(slot)
    return state["config"] if state else None


# ---------- acesso e credenciais (corretora + canais de alerta) --------

def load_credentials() -> dict:
    """Tudo o que está salvo, SEM redação — uso interno (`_credentials_env`,
    `credential_status`). Nunca devolver isto direto para um template; ver
    `display_credentials()`."""
    if not _SECRETS_PATH.exists():
        return {}
    try:
        return json.loads(_SECRETS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def display_credentials() -> dict:
    """Versão segura para reexibir no form: tudo, menos `_SECRET_FIELDS`
    (token/senha) — esses só aparecem como "configurado" via
    `credential_status()`, nunca em texto puro numa página HTML."""
    return {k: v for k, v in load_credentials().items() if k not in _SECRET_FIELDS}


def credential_status() -> dict:
    """Quais dos 3 canais têm o mínimo necessário salvo — para o form marcar
    "configurado"/"não configurado" sem reexibir nenhum segredo."""
    creds = load_credentials()
    return {
        "telegram": bool(creds.get("telegram_bot_token") and creds.get("telegram_chat_id")),
        "smtp": bool(creds.get("smtp_host") and creds.get("smtp_user") and creds.get("smtp_password")),
        "mt5": bool(creds.get("mt5_login") and creds.get("mt5_password") and creds.get("mt5_server")),
    }


# `detect_broker_capital()` foi REMOVIDA em 2026-08-21 junto de
# `LiveRuntime.reconcile_broker_cash`. Ela lia o saldo real do terminal MT5
# para servir de capital inicial da conta ("sem capital digitado", decisão de
# 2026-08-19). Isso caiu por um achado ao vivo: o saldo que o terminal MT5
# reporta NÃO acompanha o da Rico (um depósito real não aparecia nem em
# `account_info()` nem em `history_deals_get()`, com o terminal conectado e
# `trade_allowed=True`). Com dois robôs disputando o mesmo saldo, um número
# atrasado deixaria de ser inconveniência e passaria a ser dois livros-caixa
# errados. O caixa de cada slot agora é um LEDGER MANUAL, digitado pelo dono
# no painel e mantido no banco (`live_accounts.cash`) -- ver
# `dashboard/app.py::operacao_caixa`.


def _broker_for_detection(magic: Optional[int] = None):
    """Um `MT5Broker` só para CONSULTA (`symbol_info`/saldo/posição), montado
    com as credenciais SALVAS (`load_credentials()`) e nunca via
    `os.environ`: diferente de `start()` (que injeta `_credentials_env()` no
    `env` do processo FILHO), uma chamada feita aqui roda no processo do
    DASHBOARD, que nunca recebe essas variáveis — daria `login=None` mesmo
    com as credenciais MT5 salvas corretamente.

    `magic` (default `None`, mantém o default da classe): necessário para
    `MT5Broker.position_state`, que numa conta NETTING compartilhada entre
    slots filtra a posição pelo `magic` do robô — sem passar o `magic` DESTE
    slot (`Slot.magic`), a consulta veria (ou deixaria de ver) a posição de
    OUTRO robô. Os demais chamadores (`detect_shares_per_lot` e primos)
    consultam `symbol_info`, não posição, e por isso nunca precisaram
    disto."""
    from live.broker_mt5 import MT5Broker

    creds = load_credentials()
    login = creds.get("mt5_login")
    kwargs = dict(
        login=int(login) if login else None,
        password=creds.get("mt5_password"),
        server=creds.get("mt5_server"),
        path=creds.get("mt5_terminal_path"),
    )
    if magic is not None:
        kwargs["magic"] = magic
    return MT5Broker(**kwargs)


def universe_for_slot(slot_id: str, robot_key: Optional[str] = None) -> tuple[str, ...]:
    """Símbolos/tickers que este slot precisa consultar no terminal, para o
    robô `robot_key` — ou o default do catálogo (`Slot.robot_key`) se
    omitido, útil quando quem chama ainda não sabe qual robô vai rodar (ex.:
    uma conta já existente cujo robô real está gravado nela, não no
    catálogo — ver chamadores).

    Slot `intraday` NEGOCIA UM ATIVO SÓ, e ele vem do próprio slot
    (`dt-<robô>-<ativo>`, desde 2026-08-22 — antes vinha do robô resolvido no
    registry, o que impedia dois `gremah` em papéis diferentes). Um slot
    intradiário sem símbolo (formato antigo) cai no default do robô, resolvido
    pelo registry PRÓPRIO de day trade (`strategy.daytrade.registry`) — que
    não passa pelo registry de swing, o qual nem conhece robôs de day trade
    (`IntradayStrategy` não herda de `Strategy`). Slot `daily` usa o universo
    do próprio robô via o MESMO `_universe_of()` de `run_live.py::build()`."""
    from core.config import WATCHLIST, slot_by_id

    slot = slot_by_id(slot_id)
    key = robot_key or slot.robot_key
    if slot.is_intraday:
        if slot.symbol:
            return (slot.symbol,)
        from strategy.daytrade.registry import get_daytrade_robot

        try:
            robo = get_daytrade_robot(key)
        except KeyError:
            return ()
        return (robo.symbol,)
    from strategy.registry import get_strategy

    cli = _load_cli()
    try:
        strategy_obj = get_strategy(key).factory()
    except KeyError:
        return tuple(WATCHLIST)
    return cli._universe_of(strategy_obj)


def detect_shares_per_lot(slot_id: str, robot_key: Optional[str] = None) -> Optional[float]:
    """Descobre quantas ações equivalem a 1.0 de volume no terminal MT5,
    consultando o `symbol_info` de cada papel do universo DESTE slot (robô
    `robot_key`, se informado — ver `universe_for_slot`) — o usuário nunca
    digita esse número (antes exigia abrir o MT5 e conferir na mão; ver
    `MT5Broker.detect_shares_per_lot`).

    Devolve `None` se a corretora não responder ou se os papéis não tiverem
    um `shares_per_lot` único no terminal — o chamador decide como bloquear
    nesse caso, nunca inventa um default."""
    tickers = universe_for_slot(slot_id, robot_key)
    if not tickers:
        return None
    return _broker_for_detection().detect_shares_per_lot(tickers)


def detect_fractional_symbol_map(
    slot_id: str, robot_key: Optional[str] = None
) -> Optional[dict[str, str]]:
    """Descobre, para o UNIVERSO do slot `slot_id` (robô `robot_key`, se
    informado), quais tickers REALMENTE têm símbolo de mercado fracionário
    no terminal MT5 conectado.

    Diferente de `MT5Broker.detect_fractional_symbol_map` (que devolve um
    mapa COMPLETO, com fallback pro símbolo de lote padrão quando não há
    fracionário — contrato já testado, mantido como está): esta função
    filtra esse mapa e devolve SÓ as entradas onde o fracionário de fato
    existe (`resolvido != símbolo base`). É esse mapa filtrado que
    `MT5Broker(fractional_map=...)` espera — um ticker AUSENTE aqui significa
    "sem fracionário pra este papel", não "usa o símbolo base" (ver
    `MT5Broker._resolve_execution`, que decide a cada ordem entre lote
    padrão — GRATUITO na Rico, 2026-08-21 — e fracionário — R$1,90/ordem —
    conforme a quantidade pedida fecha ou não o lote padrão).

    Universo vem de `universe_for_slot()` -- o MESMO `_universe_of()` que
    `run_live.py::build()` usa no slot de swing (robôs com universo largo,
    ex. por liquidez, precisam do mapa cobrindo todo o pool).

    Dia trade NUNCA usa o resultado desta função (pedido explícito do dono,
    2026-08-22, revertendo o uso anterior de PMAM3 -> PMAM3F): giro alto
    (`gremah.sizing_rules`) paga taxa de bolsa a cada round-trip, e uma ordem
    fracionária custaria R$1,90 fixos a mais por ordem na Rico -- uma
    quantidade que não fecha o lote padrão tem de ser REJEITADA, nunca
    reencaminhada ao mercado fracionário. `dashboard/app.py::operacao_iniciar`
    só chama esta função para slot `swing`; `scripts/run_live.py::build_intraday`
    ignora `--mt5-fractional-map` de propósito, mesmo se a flag vier setada.

    Devolve `None` se a corretora não responder ou se o slot não tiver
    universo -- `create_account()`/`start()` tratam isso como "sem
    fracionário pra nenhum ticker" (só lote padrão), nunca como erro fatal
    (ver docstring de `ProcessConfig.mt5_fractional_map`)."""
    tickers = universe_for_slot(slot_id, robot_key)
    if not tickers:
        return None
    broker = _broker_for_detection()
    mapa_completo = broker.detect_fractional_symbol_map(tickers)
    if mapa_completo is None:
        return None
    return {
        ticker: simbolo for ticker, simbolo in mapa_completo.items()
        if simbolo != broker.symbol_for(ticker)
    }


def detect_futures_symbol_map(
    slot_id: str, robot_key: Optional[str] = None
) -> Optional[dict[str, str]]:
    """Descobre, para o UNIVERSO do slot `slot_id` (robô `robot_key`, se
    informado), o CONTRATO REAL com vencimento em aberto de cada ticker de
    futuro contínuo (`"WDO@"`, `"WIN@"`) — ver
    `MT5Broker.detect_futures_symbol_map` para o mecanismo: desde
    2026-09-11, o CALENDÁRIO de rolagem da B3
    (`core.instruments.front_month_contract`) decide qual é o contrato
    corrente, com o critério antigo (maior volume recente entre os
    candidatos com `trade_mode` habilitado e book de dois lados) só como
    fallback para o caso raro de o contrato indicado pela data ainda não
    ter book agora.

    Chamada a cada clique em "Iniciar operação" (`dashboard/app.py`), igual
    `detect_shares_per_lot`/`detect_fractional_symbol_map` — é isso que faz o
    contrato virar sozinho na rolagem mensal/bimestral (WDO/WIN) sem ninguém
    editar código nem configuração: um robô reiniciado no mês seguinte já
    detecta o contrato novo.

    Mesmo filtro de `detect_fractional_symbol_map`: só entram no mapa os
    tickers onde a detecção resolveu para um símbolo DIFERENTE do default de
    `symbol_for()` — um ticker sem `"@"` (ação) nunca aparece aqui.

    Devolve `None` se a corretora não responder ou se o slot não tiver
    universo — `create_account()`/`start()` tratam isso como "sem mapa"
    (degrada para o sintoma de hoje, ordem recusada pelo servidor com
    `TRADE_DISABLED`), nunca como erro fatal que bloqueia o início (ver
    docstring de `ProcessConfig.mt5_symbol_map`)."""
    tickers = universe_for_slot(slot_id, robot_key)
    if not tickers:
        return None
    broker = _broker_for_detection()
    mapa_completo = broker.detect_futures_symbol_map(tickers)
    if mapa_completo is None:
        return None
    return {
        ticker: simbolo for ticker, simbolo in mapa_completo.items()
        if simbolo != broker.symbol_for(ticker)
    }


def save_credentials(updates: dict, clear: set[str] = frozenset()) -> None:
    """Mescla campos não vazios do form com o que já estava salvo — mudar só
    o Telegram não obriga a redigitar SMTP/MT5 (campo em branco = "mantém o
    que já tinha", nunca apaga). `clear` é o conjunto de canais
    ("telegram"/"smtp"/"mt5") com a caixa "remover" marcada — isso apaga
    todos os campos daquele canal, mesmo que o form também tenha mandado
    algo para ele (remoção explícita vence)."""
    creds = load_credentials()
    for field, value in updates.items():
        if field not in CREDENTIAL_FIELDS:
            continue
        if value is not None and str(value).strip() != "":
            creds[field] = value
    for channel in clear:
        for field in _CHANNEL_FIELDS.get(channel, ()):
            creds.pop(field, None)
    _SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SECRETS_PATH.write_text(json.dumps(creds, ensure_ascii=False, indent=2), encoding="utf-8")


def _credentials_env() -> dict:
    """Traduz o que está salvo para as MESMAS variáveis de ambiente que
    `scripts/run_live.py` já sabe ler (`_build_notifier`/`_mt5_credentials`)
    — nunca argv. Usado só para montar o `env` do processo FILHO em
    `start()`; não contamina o ambiente do próprio dashboard."""
    creds = load_credentials()
    return {
        _ENV_VAR_BY_FIELD[k]: str(v)
        for k, v in creds.items()
        if k in _ENV_VAR_BY_FIELD and v not in (None, "")
    }


def create_account(config: ProcessConfig):
    """Cria a conta (idempotente) pelo MESMO caminho de código de
    `run_live.py init` — o clique evita o terminal, não reimplementa a regra."""
    import argparse

    from core.config import slot_by_id

    slot = slot_by_id(config.slot)
    cli = _load_cli()
    args = argparse.Namespace(
        mode=config.mode, capital=config.capital, strategy=config.strategy, floor=None,
        slot=config.slot, execution_mode=config.execution_mode,
        feed="yfinance", notify_min_level=config.notify_min_level,
        daily_loss_limit=None, monthly_loss_limit=None,
        mt5_magic=slot.magic, mt5_shares_per_lot=config.mt5_shares_per_lot,
        mt5_symbol_map=json.dumps(config.mt5_symbol_map) if config.mt5_symbol_map else None,
        mt5_fractional_map=json.dumps(config.mt5_fractional_map) if config.mt5_fractional_map else None,
    )
    rt = cli.build(args)
    return rt.ensure_account()


class SlotSymbolCollisionError(RuntimeError):
    """Colisão de símbolo entre dois slots numa conta NETTING, ambos em modo
    `live` — ver `_assert_slots_disjuntos`. Carrega o suficiente pro painel
    oferecer "parar o outro robô" direto na tela do erro (pedido do dono,
    2026-08-25: o banner de texto lá em cima do painel "não fica no campo de
    visão e não dá pra associar" ao clique em Iniciar), em vez de só uma
    mensagem — `str(self)` continua a mesma frase de sempre, pros chamadores
    que só querem o texto (CLI, testes)."""

    def __init__(self, message, *, slot_id, slot_label, symbols, pode_parar,
                 motivo_bloqueio=None, colisoes=None):
        super().__init__(message)
        self.slot_id = slot_id
        self.slot_label = slot_label
        self.symbols = symbols
        self.pode_parar = pode_parar
        self.motivo_bloqueio = motivo_bloqueio
        # Lista com a MESMA forma (`slot_id`/`slot_label`/`symbols`/
        # `pode_parar`/`motivo_bloqueio`) de TODOS os slots colidentes, não só
        # o primeiro (achado numa conferência manual do dono, 2026-08-31: o
        # dono só descobria uma colisão por vez, uma tentativa de "Iniciar"
        # por colisão). Os atributos acima continuam apontando pro primeiro
        # -- preserva quem já lia `err.slot_id` etc. direto (CLI, testes,
        # o botão "Parar" do card, que só derruba um por clique mesmo).
        self.colisoes = colisoes if colisoes is not None else [{
            "slot_id": slot_id, "slot_label": slot_label, "symbols": symbols,
            "pode_parar": pode_parar, "motivo_bloqueio": motivo_bloqueio,
        }]


def _assert_slots_disjuntos(slot, robot_key: str, execution_mode: str = "live") -> None:
    """A conta da Rico é NETTING (`margin_mode=0`, verificado no terminal
    real em 2026-08-21): duas ordens REAIS no MESMO símbolo se FUNDEM numa
    posição única na corretora, independente de `magic`. Dois slots
    compartilhando símbolo transformariam os dois livros-caixa em ficção —
    um venderia a posição do outro sem saber. Checado aqui (e não só no
    catálogo) porque `SLOTS` é editável e o custo do erro é dinheiro real.

    Mode-aware (2026-08-24, pedido do dono): o risco é da ORDEM chegando na
    corretora, não do símbolo compartilhado em si — modo sombra nunca manda
    ordem, então dois robôs sombra (ou um sombra + um parado) no mesmo papel
    não fundem posição nenhuma. Só bloqueia quando ESTE slot vai subir em
    `execution_mode="live"` E o outro slot que compartilha o símbolo está
    RODANDO agora em `"live"` também — as duas condições precisam valer ao
    mesmo tempo para existir ordem real concorrente. Criar dois cartões no
    mesmo ativo para comparar robôs em sombra (ex.: gremah vs gremah_tick em
    PMAM3) deixou de ser bloqueado por isso; o gate real só aparece quando
    algum dos dois de fato tentar operar dinheiro.

    `robot_key` é o robô que ESTE slot está prestes a rodar — desde que o
    símbolo deixou de ser campo do slot (2026-08-21), a única forma de saber
    o que ele vai negociar é perguntar ao robô escolhido
    (`universe_for_slot`). O outro lado da comparação usa o robô JÁ GRAVADO
    na conta do outro slot, se existir (nunca o default do catálogo, que
    pode não ser o que a conta de fato opera) — ver `universe_for_slot`."""
    from dashboard.slots import all_slots
    from journal import live_store

    meu_universo = set(universe_for_slot(slot.id, robot_key))
    with live_store.live_journal() as conn:
        outros = [s for s in all_slots(conn) if s.id != slot.id]
        contas = {s.id: live_store.load_account(conn, s.id) for s in outros}
    # Junta TODAS as colisões antes de levantar (achado numa conferência
    # manual do dono, 2026-08-31, mesma classe do bug de
    # `_parar_processo_nao_rastreado` corrigido no mesmo dia: um `raise` no
    # primeiro achado do `for` escondia qualquer outra colisão -- o dono só
    # descobria a segunda numa NOVA tentativa de "Iniciar", depois de já ter
    # parado a primeira). A checagem de `magic` continua fail-fast: é erro de
    # CATÁLOGO (dois slots com o mesmo `magic`), não uma lista de robôs
    # concorrentes para o dono escolher entre -- não é a mesma pergunta.
    colisoes: list[dict] = []
    for outro in outros:
        if outro.magic == slot.magic:
            raise RuntimeError(
                f"slots {slot.id!r} e {outro.id!r} têm o mesmo `magic` "
                f"({slot.magic}) — as ordens dos dois robôs ficariam "
                "indistinguíveis na corretora. Nos slots de day trade o "
                "`magic` vem de `core.config.daytrade_magic` (crc32 do id); "
                "uma colisão aqui é rara mas possível, e a saída é renomear "
                "um dos slots (outro robô ou outro ativo)."
            )
        conta_outro = contas.get(outro.id)
        outro_robot_key = (conta_outro.investment_robot if conta_outro else None) or outro.robot_key
        colisao = meu_universo & set(universe_for_slot(outro.id, outro_robot_key))
        if not colisao:
            continue
        if execution_mode != "live":
            continue
        estado_outro = status(outro.id)
        outro_mode = (estado_outro or {}).get("config", {}).get("execution_mode", "live")
        if estado_outro is None or outro_mode != "live":
            continue
        # "Pode parar" direto do card de erro (pedido do dono, 2026-08-25):
        # só quando o OUTRO robô não tem nada em risco agora -- nem posição
        # aberta, nem ordem de entrada mandada e ainda não resolvida
        # (`pending_entry_refs`, ver `live/intraday_runtime.py`). Parar no
        # meio de qualquer um dos dois deixaria o robô órfão de vigilância
        # até o próximo `Iniciar` -- mesmo raciocínio de `stop()`, que também
        # nunca mexe na posição, só no processo supervisor.
        tem_posicao = bool(conta_outro.positions) if conta_outro else False
        pendentes = (
            (conta_outro.policy_state or {}).get("intraday", {}).get("pending_entry_refs")
            if conta_outro else None
        )
        pode_parar = not tem_posicao and not pendentes
        colisoes.append({
            "slot_id": outro.id, "slot_label": outro.label,
            "symbols": sorted(colisao), "pode_parar": pode_parar,
            "motivo_bloqueio": None if pode_parar else (
                "este robô tem ordens posicionadas ou abertas agora — aguarde a "
                "conclusão para poder encerrar a operação."
            ),
        })
    if not colisoes:
        return
    primeira = colisoes[0]
    outras = ", ".join(
        f"{c['slot_label']} ({', '.join(c['symbols'])})" for c in colisoes[1:]
    )
    raise SlotSymbolCollisionError(
        f"slots {slot.id!r} e {primeira['slot_id']!r} negociam o(s) mesmo(s) símbolo(s) "
        f"({', '.join(primeira['symbols'])}) numa conta NETTING, os dois em modo "
        "'live' — as posições se fundiriam numa só e os dois caixas "
        "passariam a mentir. Pare um dos dois, ou rode em modo sombra."
        + (f" Também colide com: {outras}." if outras else ""),
        slot_id=primeira["slot_id"], slot_label=primeira["slot_label"],
        symbols=primeira["symbols"], pode_parar=primeira["pode_parar"],
        motivo_bloqueio=primeira["motivo_bloqueio"],
        colisoes=colisoes,
    )


def available_cash(slot_id: str, execution_mode: str = "live") -> Optional[float]:
    """Caixa que o LEDGER MANUAL diz pertencer a este slot, ou `None` se a
    conta ainda não existe.

    Fonte de verdade deliberada: o número digitado no painel, no banco — NÃO
    `Broker.cash_balance()`. Ver o comentário no lugar de
    `detect_broker_capital()` (removida): o saldo do terminal MT5 atrasa em
    relação ao da Rico, e com dois robôs disputando a mesma conta um número
    atrasado viraria dois livros-caixa errados.

    `execution_mode`: qual dos dois saldos ler (`AccountState.cash_for`,
    pedido do dono 2026-08-23) -- default `"live"` preserva o comportamento
    de antes desta conta ganhar `cash_sombra` para todo chamador que não se
    importa com o modo (swing, por exemplo, nunca teve sombra)."""
    from journal import live_store

    try:
        with live_store.live_journal() as conn:
            conta = live_store.load_account(conn, slot_id)
    except (live_store.LegacyPaperAccountError, live_store.LegacyManualAccountError):
        return None
    return None if conta is None else round(conta.cash_for(execution_mode), 2)


def capital_em_posicao(conta) -> float:
    """R$ já comprometidos nas posições abertas desta conta — o que o caixa
    LIVRE deixou de mostrar porque virou posição.

    Existe para o portão de caixa somar `caixa + posição aberta` antes de
    comparar com o piso (ver `start()` e `dashboard.app.operacao_iniciar`):
    sem isso, reiniciar o processo só para continuar vigiando uma posição
    que já existe ficava bloqueado, porque a entrada debitou o caixa.

    `capital_allocated` é o número certo, e não `preço x quantidade`
    (2026-09-09): aquele é o valor NOCIONAL, e num futuro o nocional não é
    caixa nenhum — 1 contrato de WDO@ aberto contava ~R$5.100 de
    "comprometido" onde a corretora reservou R$150, inflando o portão em 34x
    e deixando passar um robô que o piso deveria barrar. `capital_allocated`
    é exatamente o que `IntradayLiveRuntime._on_opened` debitou do caixa
    (margem em futuro, preço cheio em ação), então as duas metades da soma
    voltam a falar da mesma moeda.

    Em MÓDULO: capital comprometido é comprometido nos dois lados, e
    `quantity` vem negativa numa vendida."""
    if conta is None:
        return 0.0
    return sum(
        abs(float(p.capital_allocated or 0.0)) or abs(int(p.quantity)) * float(p.entry_price)
        for p in conta.positions.values()
    )


#: Quanto tempo uma cotação lida do terminal vale antes de ser relida. O
#: painel repinta a cada poucos segundos e o piso de caixa aparece em vários
#: cartões ao mesmo tempo — sem o TTL, cada repintura abriria uma consulta por
#: símbolo no MT5. 30s é curto o bastante para o número acompanhar o pregão e
#: longo o bastante para o poll não pagar I/O de corretora.
_PRECO_TTL_SEGUNDOS = 30.0
_preco_cache: dict[str, tuple[float, Optional[float], str]] = {}
_preco_lock = threading.Lock()
#: UM `MT5Broker` reusado para todas as leituras de cotação do painel. A
#: ficha da `gremah` lista 9 ativos calibrados: com um broker novo por
#: símbolo, uma repintura chamaria `mt5.initialize()` nove vezes — que a
#: docstring de `MT5Broker.connect` desaconselha explicitamente ("chamar de
#: novo sem necessidade é, na prática de alguns terminais, um jeito de perder
#: estado de ordens em voo à toa"). Instância só de CONSULTA, sem `magic`:
#: nunca manda ordem. `connect()` é idempotente e retenta sozinho enquanto
#: `_connected` for `False`, então guardar a instância não congela um
#: terminal que ainda vai abrir.
_preco_broker = None


def _cotacao_do_terminal(symbol: str) -> Optional[float]:
    """Último preço negociado que o MT5 reporta, ou `None` se não deu.

    Função separada de propósito, e não inline em `preco_de_referencia`: é a
    ÚNICA porta de I/O de corretora naquele caminho, e é ela que
    `tests/conftest.py::_cotacao_do_terminal_desligada` desliga para a suíte
    inteira. Toda leitura de preço do painel cai no parquet nos testes, o que
    os mantém determinísticos (o preço de mercado muda a cada minuto) e sem
    tocar no terminal do dono enquanto ele opera.

    Nunca levanta: terminal fechado, credencial ausente ou símbolo
    desconhecido devolvem `None` e quem chama usa a retaguarda."""
    global _preco_broker
    try:
        with _preco_lock:
            if _preco_broker is None:
                _preco_broker = _broker_for_detection()
            broker = _preco_broker
        if not broker.connect():
            return None
        preco = broker.last_price(symbol)
        return float(preco) if preco else None
    except Exception:  # noqa: BLE001 -- terminal fechado/sem credencial: retaguarda
        return None


def preco_de_referencia(symbol: str) -> tuple[Optional[float], str]:
    """`(preço, origem)` do ativo AGORA — cotação ao vivo do terminal
    primeiro, parquet local como retaguarda. `(None, "")` se nenhum dos dois
    responder. `origem` é `"agora"` (veio do terminal) ou a data ISO da última
    barra salva (veio do parquet, e pode estar velha).

    **Por que existe (2026-09-08, achado com dinheiro real).** O piso de caixa
    de uma AÇÃO é `preço x 100 x 2`, então ele só vale o quanto o preço vale.
    O único preço que o painel conhecia era `market_data_intraday.storage.
    last_close` — o último minuto SALVO em parquet. Mas nada salva esse
    parquet sozinho: o robô ao vivo lê barra direto do terminal (`MT5Feed`),
    nunca escreve ali, e o download é script manual. Resultado medido: o
    parquet de PMAM3 estava parado em R$0,15 de 24/08 enquanto o papel
    negociava a R$0,33 — 15 dias e +120% de defasagem. O painel disse ao dono
    "mín. R$30", ele depositou R$30, e o robô então recusou TODO pregão contra
    o preço de verdade (`IntradayLiveRuntime._check_capital`, que lê o feed ao
    vivo e cobrava R$33). Painel e robô olhando preços diferentes é a mesma
    família de erro de `live/` decidir por conta própria: o número que o dono
    lê tem de ser o número que o robô aplica.

    Nunca levanta e nunca bloqueia por falta de terminal: sem MT5 (ou com o
    terminal fechado) cai no parquet e diz de onde veio, para quem desenha
    poder mostrar a idade em vez de fingir que o número é de agora."""
    from dashboard.robot_view import _ultimo_preco

    agora = time.monotonic()
    with _preco_lock:
        em_cache = _preco_cache.get(symbol)
        if em_cache is not None and (agora - em_cache[0]) < _PRECO_TTL_SEGUNDOS:
            return (em_cache[1], em_cache[2])

    preco = _cotacao_do_terminal(symbol)
    resultado = (float(preco), "agora") if preco else _ultimo_preco(symbol)
    with _preco_lock:
        _preco_cache[symbol] = (agora, resultado[0], resultado[1])
    return resultado


def _intraday_capital_minimo(robot_key: str, symbol: Optional[str] = None) -> Optional[float]:
    """Piso de caixa para operar HOJE — `capital_minimo_para`
    (`dashboard.robot_view`) de `symbol`, no preço de AGORA
    (`preco_de_referencia`: terminal primeiro, parquet como retaguarda).
    `symbol` omitido usa o ativo default do robô.

    Ramifica por `IntradayStrategy.is_futuro` (2026-08-28, corrige o mesmo
    bug que `capital_minimo_para` já resolveu para o form de "novo robô":
    aplicar `capital_minimo_brl` — fórmula de LOTE DE AÇÃO, `preço x 100 x
    2` — a um futuro dá um piso de ~R$1 milhão para WDO@/1 contrato, ou,
    faltando `_ultimo_preco` salvo pro símbolo, cai silenciosamente no piso
    genérico do slot (R$50) — os dois errados, nenhum é a margem real
    (R$150 WDO@/R$100 WIN@ x `MARGIN_BUFFER_FUTUROS`). Esta função vivia
    sozinha nesta cópia da regra desde antes de `capital_minimo_para`
    existir; ficou pra trás quando o form foi corrigido.

    `None` se o robô não existir no catálogo, o símbolo não tiver perfil
    (`backtest.intraday.profiles.PROFILES`) ou não houver preço salvo ainda
    (parquet ausente) — quem chama decide o degrade, nunca bloqueia por falta
    de dado que não é culpa do dono."""
    from backtest.intraday.profiles import PROFILES
    from dashboard.robot_view import capital_minimo_para
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.registry import get_daytrade_robot

    try:
        robo = get_daytrade_robot(robot_key)
    except KeyError:
        return None
    symbol = symbol or robo.symbol
    if getattr(robo, "is_futuro", False):
        # Futuro não consulta preço nenhum: o piso é margem por contrato, que
        # a corretora fixa (ver `capital_minimo_para`). Sair antes evita uma
        # ida ao terminal que não mudaria a resposta.
        return capital_minimo_para(True, symbol, None)
    perfil = PROFILES.get(symbol)
    if perfil is None:
        return None
    preco, _origem = preco_de_referencia(symbol)
    if preco is None:
        return None
    return capital_minimo_brl(preco, perfil.default_quantity)


def min_cash_for(slot, robot_key: Optional[str] = None) -> float:
    """Piso de caixa para iniciar operação neste slot (pedido do dono,
    2026-08-22, ao perceber que `Slot.min_cash_brl` continuava fixo depois de
    `capital_minimo_brl` existir por símbolo).

    Swing usa `Slot.min_cash_brl` — não há conceito de "lote" pro swing,
    então o piso genérico é o único que existe. Day trade usa
    `capital_minimo_brl` do robô que vai rodar de fato: `robot_key` explícito
    (conta já existente, ou robô escolhido no form) ou `slot.robot_key` (o
    sugerido pra conta nova, ainda sem robô fixado — é o que o `<select>` do
    template mostra pré-selecionado).

    Antes desta função, PMAM3 (mínimo real R$28) era bloqueada por um piso de
    R$50 mais rígido que o necessário, e CLSC4 (mínimo real R$30.390) passava
    o piso de R$50 pra só descobrir que faltava caixa no primeiro pregão,
    dentro do processo já rodando — os dois casos evaporam usando o piso do
    ROBÔ escolhido em vez de um número cego ao símbolo."""
    if not slot.is_intraday:
        return slot.min_cash_brl
    minimo = _intraday_capital_minimo(robot_key or slot.robot_key, slot.symbol or None)
    return slot.min_cash_brl if minimo is None else minimo


def origem_do_preco_do_piso(slot, robot_key: Optional[str] = None) -> str:
    """De onde veio o preço que gerou `min_cash_for` deste slot: `"agora"`
    (cotação do terminal), uma data ISO (parquet local, PODE estar velho) ou
    `""` quando o piso não depende de preço nenhum — swing (piso fixo do
    slot) e futuro (margem por contrato).

    Existe só para o painel poder mostrar a IDADE do número. Um piso de caixa
    é uma instrução de quanto depositar; sem dizer de quando é o preço, um
    parquet parado há 15 dias vira uma instrução errada com cara de certa —
    foi o que aconteceu em 2026-09-08 (`preco_de_referencia`). Barato: o
    preço já está no cache de `preco_de_referencia` quando `min_cash_for`
    rodou no mesmo request."""
    if not slot.is_intraday:
        return ""
    from strategy.daytrade.registry import get_daytrade_robot

    try:
        robo = get_daytrade_robot(robot_key or slot.robot_key)
    except KeyError:
        return ""
    if getattr(robo, "is_futuro", False):
        return ""
    symbol = slot.symbol or robo.symbol
    if not symbol:
        return ""
    return preco_de_referencia(symbol)[1]


def start(config: ProcessConfig) -> dict:
    """Cria a conta se preciso e sobe `scripts/run_live.py loop` como
    processo próprio DESTE SLOT, sobrevivendo ao dashboard fechar.

    Prova de vida (correção pós-code-review, crítico nº1): grava PID/estado
    só DEPOIS de esperar `_STARTUP_GRACE_SECONDS` e confirmar que o processo
    ainda está de pé (`proc.poll() is None`). Sem isso, um processo que
    morre na hora (terminal MT5 fechado, credencial errada, `--mode`
    recusado) fazia o dashboard gravar PID normalmente e continuar
    mostrando "robô ativo" para sempre — o botão "Iniciar" mentindo sobre um
    processo morto.

    Trava em `_start_lock` do começo ao fim (ver docstring do lock, crítico
    nº2): dois cliques quase simultâneos no MESMO slot não podem passar os
    dois pelo guard `status(slot) is not None` antes de qualquer um gravar
    estado. O lock é único (não por slot) porque o arquivo de estado é
    compartilhado — ver docstring do módulo.

    Varredura de órfão ANTES de subir (2026-08-27, crítico nº3, achado numa
    conferência manual do dono): o guard acima só enxerga o arquivo de
    estado. Se `stop()` mandou matar um PID e o `_matar_arvore` não pegou de
    verdade (processo já reparentado, `taskkill` engasgado) ele ainda assim
    zera `pid`/`started_at` (ver docstring de `stop()`) — o arquivo diz
    "parado" com um processo de verdade continuando vivo por trás. Sem esta
    varredura, o próximo `start()` deste slot só olhava o arquivo limpo e
    subia um SEGUNDO processo por cima do primeiro: dois `run_live.py loop`
    escrevendo na mesma conta e no mesmo log ao mesmo tempo (foi exatamente
    isto que aconteceu com `dt-gremah-pmam3-shadow` em 27/08 — órfão das
    09:26 sobrevivendo lado a lado com o processo das 12:12, rastreado).
    `_parar_processo_nao_rastreado` é o MESMO mecanismo que o botão "Parar"
    já usa pro caso "arquivo sem pid" — reusado aqui pra garantir sempre no
    máximo um processo por slot, não só quando alguém nota e clica em Parar.

    Piso de caixa (2026-08-21, refinado por robô em 2026-08-22): recusa se o
    ledger manual do slot tiver menos que `min_cash_for(slot, config.strategy)`
    — `Slot.min_cash_brl` pro swing, `capital_minimo_brl` do robô ESCOLHIDO
    pro day trade. Isto é checado AQUI, e não só no template, porque o botão
    desabilitado não cobre um POST repetido, um fragmento HTMX velho, nem a
    linha de comando."""
    from core.config import slot_by_id

    slot = slot_by_id(config.slot)
    with _start_lock:
        if status(config.slot) is not None:
            raise RuntimeError(
                f"o robô do slot '{slot.label}' já está rodando — pare antes de iniciar de novo."
            )
        # Sempre no máximo um processo por slot (ver docstring acima,
        # "Varredura de órfão"): mata qualquer `run_live.py` deste slot que o
        # arquivo de estado não conhece antes de subir um novo. Sem custo no
        # caso comum (retorna `False` na hora se não achar nada).
        _parar_processo_nao_rastreado(config.slot)
        if not config.strategy:
            raise RuntimeError(
                "nenhum robô de investimento selecionado — não há robô "
                "padrão (ver docstring de scripts/run_live.py, seção 'Robô "
                "de investimento')."
            )
        # Depende de `config.strategy` já resolvido (o robô decide o
        # universo/símbolo, ver docstring da função) — por isso checado
        # DEPOIS do guard acima, nunca antes.
        _assert_slots_disjuntos(slot, config.strategy, config.execution_mode)
        # CONTRATO REAL do futuro contínuo (`WDO@` -> `WDOV26`): sem ele o
        # servidor recusa TODA ordem de futuro (retcode 10017
        # `TRADE_DISABLED`, achado ao vivo em 2026-08-28). A detecção morava
        # SÓ no handler HTTP (`dashboard/app.py`), então qualquer outro
        # chamador de `start()` — script, restart automatizado, linha de
        # comando — subia o robô sem mapa e só descobriria na primeira ordem
        # real recusada. Em sombra passa despercebido (não manda ordem), que
        # é o que torna a armadilha pior: o slot parece saudável.
        #
        # Fica AQUI, e não só lá, porque é invariante de "subir o robô", não
        # de "clicar no botão". Só detecta quando o chamador não trouxe mapa
        # — o caminho do painel já traz, então nada muda para ele e a
        # consulta (lenta, vai ao terminal) não roda duas vezes.
        if config.mt5_symbol_map is None:
            detectado = detect_futures_symbol_map(config.slot, config.strategy)
            if detectado:
                config = replace(config, mt5_symbol_map=detectado)
        if config.mt5_shares_per_lot is None or config.mt5_shares_per_lot <= 0:
            raise RuntimeError(
                "modo mt5 exige 'ações por lote' (mt5_shares_per_lot) — não foi"
                "possível detectar automaticamente via detect_shares_per_lot() "
                "(terminal MT5 fechado/deslogado, ou símbolos da watchlist com "
                "contract_size diferente entre si)."
            )
        if config.execution_mode not in ("shadow", "live"):
            raise RuntimeError(
                f"execution_mode inválido: {config.execution_mode!r} — use "
                "'shadow' (journaliza sem enviar ordem) ou 'live'."
            )

        create_account(config)

        piso = min_cash_for(slot, config.strategy)
        # Swing NUNCA honra `execution_mode` (não tem conceito de sombra --
        # ver `dashboard.app.operacao_iniciar`, que já força "live" para ele
        # antes de chegar aqui) -- mas `start()` é chamado direto pela CLI e
        # pelos testes também, então não pode CONFIAR que `config.execution_
        # mode` já veio corrigido; refaz a mesma regra aqui.
        modo_do_gate = config.execution_mode if slot.is_intraday else "live"
        caixa = available_cash(config.slot, modo_do_gate)
        # Soma o capital JA' comprometido numa posicao aberta deste slot
        # (2026-08-24, mesmo dia da correcao que passou a debitar o custo da
        # entrada do caixa -- ver `live.intraday_runtime._on_opened`): sem
        # isto, reiniciar o processo para so' continuar vigiando uma posicao
        # que ja existe (restart no meio do pregao, deploy, etc.) ficava
        # bloqueado pelo piso, porque o caixa LIVRE caiu abaixo dele assim
        # que a entrada comecou a ser debitada -- mas o CAIXA + A POSICAO
        # continuam valendo o mesmo de antes.
        if slot.is_intraday:
            from journal import live_store
            with live_store.live_journal() as conn:
                conta = live_store.load_account(conn, config.slot)
            comprometido = capital_em_posicao(conta)
        else:
            comprometido = 0.0
        if caixa is None or (caixa + comprometido) < piso:
            rotulo_saldo = "sombra" if modo_do_gate == "shadow" else "real"
            raise RuntimeError(
                f"caixa {rotulo_saldo} do slot '{slot.label}' é R$ "
                f"{0.0 if caixa is None else caixa:.2f}"
                f"{f' (+ R$ {comprometido:.2f} ja em posicao aberta)' if comprometido else ''}"
                f", abaixo do mínimo de R$ {piso:.2f} para operar — informe o "
                "caixa destinado a este robô no painel antes de iniciar."
            )

        argv = [
            sys.executable, str(_SCRIPT),
            "--mode", config.mode, "--capital", str(config.capital),
            "--strategy", config.strategy,
            "--slot", config.slot,
            "--execution-mode", config.execution_mode,
            "--notify-min-level", config.notify_min_level,
        ]
        if config.mode == "mt5":
            argv += ["--mt5-shares-per-lot", str(config.mt5_shares_per_lot)]
            if config.mt5_symbol_map:
                argv += ["--mt5-symbol-map", json.dumps(config.mt5_symbol_map)]
            if config.mt5_fractional_map:
                argv += ["--mt5-fractional-map", json.dumps(config.mt5_fractional_map)]
        # Day trade decide barra a barra e o stop dele resolve em barra M1
        # fechada: um passo de 60s perderia a barra inteira. Swing mantém 60s
        # (a decisão dele é 1x por pregão; ver `scripts/run_live.py`).
        argv += ["loop", "--seconds", "5" if slot.is_intraday else "60"]

        log_path = _log_path(config.slot)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "a", encoding="utf-8")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        # Credenciais (Telegram/SMTP/MT5) só entram no ambiente do PROCESSO FILHO
        # — nunca em argv (fica visível em `ps`/histórico), nunca no ambiente do
        # próprio dashboard (persistem só em `db/live_secrets.json`).
        env = {**os.environ, **_credentials_env()}
        proc = subprocess.Popen(
            argv, cwd=str(_ROOT), stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=creationflags, env=env,
        )

        time.sleep(_STARTUP_GRACE_SECONDS)
        exit_code = proc.poll()
        if exit_code is not None:
            # Já saiu (qualquer código, inclusive 0 — sair na hora também é
            # falha de subida) — não grava estado nenhum, o clique tem de
            # mostrar o erro real em vez de "rodando".
            raise RuntimeError(
                f"o processo do robô saiu logo após iniciar (código {exit_code}) — "
                f"últimas linhas do log:\n{_tail_log(config.slot)}"
            )

        state = {
            "pid": proc.pid,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "config": asdict(config),
        }
        _write_state(config.slot, state)
        return state


def stop(slot: str) -> bool:
    """Encerra o processo supervisor DESTE slot, se houver um rodando. Não
    mexe na conta nem no disjuntor — só derruba o loop; retomar depois com
    `start()` continua exatamente de onde a conta estava, do banco. O outro
    slot não é afetado.

    Mantém a `config` no arquivo de estado (só zera `pid`/`started_at`) para
    o formulário de retomada continuar pré-preenchido depois de parar —
    só `create_account`/CLI podem apagar de vez.

    Um clique em "Parar" pede para MATAR, não para "matar só se eu
    confirmar que está vivo" — se `_pid_alive` não conseguir responder
    (`_TasklistUnavailable`), tenta o `taskkill` do mesmo jeito: matar um
    PID que já morreu é inofensivo (o comando só falha silenciosamente),
    enquanto PULAR o `taskkill` por indeterminação arrisca marcar "parado"
    no arquivo um processo que continua vivo de verdade.

    Sem PID no arquivo, o botão NÃO desiste: pergunta ao sistema operacional
    se existe um `run_live.py` deste slot rodando mesmo assim
    (`listar_processos`). Esse caso é real — processo subido pela CLI, ou
    arquivo de estado perdido/sobrescrito enquanto o robô continuava vivo —
    e antes disto ele só tinha uma saída, que era o Gerenciador de Tarefas:
    o painel mostrava "parado" para um robô que estava operando, e um clique
    em "Iniciar" ali subiria um SEGUNDO processo para a mesma conta."""
    state = _read_state(slot)
    if state is None or state.get("pid") is None:
        return _parar_processo_nao_rastreado(slot)
    pid = state["pid"]
    try:
        deve_matar = _pid_alive(pid)
    except _TasklistUnavailable:
        deve_matar = True
    if deve_matar:
        _matar_arvore(pid)
    _write_state(slot, {**state, "pid": None, "started_at": None})
    return True


# ---------- inventario de processos (inclusive os que ninguem rastreia) -----
#
# `status()`/`status_all()` respondem "o PID que EU anotei ainda esta vivo?".
# Isso deixa um ponto cego inteiro: processo que sobreviveu ao dashboard que o
# criou (achado 25/08/2026 -- o dono fechou o painel sem parar os robos e tres
# supervisores continuaram vivos, dormindo ate a abertura do dia seguinte),
# robo subido na mao pela CLI, e sobra de um `dev.bat` reiniciado. Nenhum
# deles aparece em `db/live_process.json`, e por isso nenhum botao do painel
# conseguia mata-los -- so' o Gerenciador de Tarefas.
#
# A varredura aqui pergunta ao SISTEMA OPERACIONAL quem esta rodando
# `run_live.py`, e nao ao nosso arquivo de estado. O arquivo vira o que ele
# deveria ser desde sempre: um indice do que o painel criou, nao a definicao
# do que existe.


@dataclass(frozen=True)
class ProcessoRobo:
    """Um supervisor `run_live.py` vivo nesta maquina.

    `rastreado` distingue o que o painel criou e ainda anota
    (`db/live_process.json`) do que ficou solto -- e' a diferenca entre "o
    botao Parar do cartao resolve" e "so' esta tela resolve"."""

    pid: int
    slot: Optional[str]
    execution_mode: Optional[str]
    rastreado: bool
    filhos: tuple[int, ...] = ()
    # Linha de comando crua -- usada só por `_config_from_commandline` para
    # readotar um processo cujo slot sumiu de `db/live_process.json` (ver
    # `_reconciliar_do_inventario`). Vazia por default para não quebrar quem
    # já constrói `ProcessoRobo` sem ela (testes existentes).
    linha_de_comando: str = ""

    @property
    def rotulo(self) -> str:
        """`dt-gremah_tick-pmam3-live` quando da' para saber; senao o PID."""
        return self.slot or f"pid {self.pid}"


def _argumento(linha: str, flag: str) -> Optional[str]:
    """Valor de `--flag valor` numa linha de comando. `None` se ausente."""
    partes = linha.split()
    alvo = f"--{flag}"
    for i, parte in enumerate(partes):
        if parte == alvo and i + 1 < len(partes):
            return partes[i + 1]
        if parte.startswith(f"{alvo}="):
            return parte.split("=", 1)[1]
    return None


def _config_from_commandline(processo: "ProcessoRobo") -> Optional[dict]:
    """Reconstroi um dict no formato de `asdict(ProcessConfig(...))` a partir
    da PROPRIA linha de comando do processo vivo -- usado quando o slot sumiu
    inteiro de `db/live_process.json` (achado 2026-08-31: reinicios do
    dashboard deixam o `Popen` orfao vivo e o arquivo de estado, gravado por
    um processo-pai que ja nao existe mais, sem nenhuma linha para o slot).

    So os campos SIMPLES (sem espaco/aspas no valor) sao recuperaveis assim;
    `mt5_symbol_map`/`mt5_fractional_map` ficam de fora de proposito -- sao
    autodetectados de novo a cada `start()` (ver docstring de `ProcessConfig`),
    entao o processo JA RODANDO nao depende deles estarem aqui; so o
    formulario de retomada os pediria de novo, e vai redetectar sozinho.

    `None` se a linha nao tiver os campos minimos -- quem chama nao adota no
    escuro."""
    linha = processo.linha_de_comando
    strategy = _argumento(linha, "strategy")
    mode = _argumento(linha, "mode")
    capital = _argumento(linha, "capital")
    if not strategy or not mode or not capital:
        return None
    mt5_shares = _argumento(linha, "mt5-shares-per-lot")
    return {
        "mode": mode,
        "capital": float(capital),
        "strategy": strategy,
        "slot": processo.slot,
        "execution_mode": processo.execution_mode or "shadow",
        "notify_min_level": _argumento(linha, "notify-min-level") or "warn",
        "mt5_shares_per_lot": float(mt5_shares) if mt5_shares else None,
        "mt5_fractional_map": None,
        "mt5_symbol_map": None,
    }


def _reconciliar_do_inventario(slot: str, processos: list["ProcessoRobo"]) -> Optional[dict]:
    """Quando `db/live_process.json` nao sabe de nenhum PID vivo para `slot`,
    pergunta ao INVENTARIO JA VARRIDO (`listar_processos()`, feito por quem
    chama -- nunca varre de novo aqui, ver `status_all()`) se existe mesmo
    assim, um `run_live.py --slot <slot>` de pe. Se sim, readota o PID em vez
    de deixar o cartao dizer "parado" para um robo que continua operando --
    e' a mesma classe de bug documentada na memoria do projeto
    (`supervisores_duplicados_painel_cego`, 2026-08-26; reincidiu em
    31/08/2026, desta vez nos 7 slots de day trade de uma vez, incluindo o
    robo REAL `dt-gremah-pmam3-live`).

    NUNCA decide entre dois candidatos: mais de um processo vivo pro mesmo
    slot e' sinal de incidente (duas instancias escrevendo a mesma conta), nao
    divergencia de painel -- nao adota nenhum, deixa "parado" (visivel,
    seguro) ate a tela "Processos de Robo" resolver na mao.

    Prefere a `config` que JA estava salva (preservada por `status()` ao
    zerar so' `pid`/`started_at`) a reconstruir da linha de comando -- so cai
    para `_config_from_commandline` quando o slot sumiu por inteiro do
    arquivo. `started_at` vira o momento da ADOCAO, nao o do `Popen` real
    (nao ha como saber sem consultar `CreationDate` do processo, e o unico
    uso deste campo e' exibir "rodando ha..." -- ver `app.hora_br`)."""
    candidatos = [p for p in processos if p.slot == slot]
    if len(candidatos) != 1:
        return None
    candidato = candidatos[0]
    config = (_read_state(slot) or {}).get("config") or _config_from_commandline(candidato)
    if config is None:
        return None
    state = {
        "pid": candidato.pid,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": config,
    }
    _write_state(slot, state)
    return state


def _reconciliar_orfao(slot: str) -> Optional[dict]:
    """Igual a `_reconciliar_do_inventario`, mas varre agora (`listar_
    processos()`) -- usada por `status()` (chamado slot a slot pelo poll de
    cada cartao) quando nao ha um inventario ja pronto pra reusar."""
    try:
        processos = listar_processos()
    except _TasklistUnavailable:
        return None
    return _reconciliar_do_inventario(slot, processos)


def _powershell() -> str:
    """Caminho absoluto do `powershell.exe`, com o nome nu como ultimo
    recurso. Nao da' para confiar no PATH: o dashboard pode subir por um
    atalho, por um servico ou por um shell (Git Bash, por exemplo) cujo PATH
    nao inclui o `System32` -- e ai a varredura morre com "arquivo nao
    encontrado" em vez de listar os robos que estao rodando."""
    raiz = os.environ.get("SystemRoot") or r"C:\Windows"
    caminho = Path(raiz) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(caminho) if caminho.is_file() else "powershell"


def _processos_do_sistema() -> list[tuple[int, int, str]]:
    """`(pid, ppid, linha_de_comando)` de todo processo desta maquina que
    esta rodando `scripts/run_live.py`.

    Windows sai pelo `Get-CimInstance` do PowerShell, e nao pelo `tasklist`
    usado no resto do modulo: `tasklist` nao mostra linha de comando, e sem
    ela nao da' para saber QUAL robo e' cada PID -- que e' justamente a
    pergunta desta tela. POSIX sai pelo `ps`, porque o servidor para onde
    isto vai nao tem PowerShell nem `taskkill`.

    Levanta `_TasklistUnavailable` (mesmo contrato do resto do modulo:
    "indeterminado", nunca "nao ha nada") se a consulta falhar."""
    if os.name == "nt":
        comando = [
            _powershell(), "-NoProfile", "-NonInteractive", "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
            "'*run_live*' } | Select-Object ProcessId,ParentProcessId,CommandLine "
            "| ConvertTo-Json -Compress",
        ]
    else:
        comando = ["ps", "-eo", "pid=,ppid=,args="]
    try:
        out = subprocess.run(comando, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        raise _TasklistUnavailable(str(e)) from e
    if out.returncode != 0 and not out.stdout.strip():
        raise _TasklistUnavailable(out.stderr.strip() or f"codigo {out.returncode}")

    achados: list[tuple[int, int, str]] = []
    if os.name == "nt":
        texto = out.stdout.strip()
        if not texto:
            return []
        try:
            dados = json.loads(texto)
        except json.JSONDecodeError as e:
            raise _TasklistUnavailable(f"resposta ilegivel do PowerShell: {e}") from e
        # `ConvertTo-Json` devolve um OBJETO quando ha um resultado so' e uma
        # LISTA quando ha varios -- tratar so' a lista perderia exatamente o
        # caso de "sobrou UM robo solto", o mais comum desta tela.
        if isinstance(dados, dict):
            dados = [dados]
        for item in dados:
            linha = item.get("CommandLine") or ""
            achados.append((int(item["ProcessId"]),
                            int(item.get("ParentProcessId") or 0), linha))
    else:
        for linha_bruta in out.stdout.splitlines():
            campos = linha_bruta.strip().split(None, 2)
            if len(campos) < 3:
                continue
            try:
                achados.append((int(campos[0]), int(campos[1]), campos[2]))
            except ValueError:
                continue
    # O filtro final e' aqui, e nao so' no comando: no Windows o proprio
    # PowerShell da varredura casa com o `-like` (a string esta no `-Command`
    # dele) e apareceria na lista como se fosse um robo.
    return [(pid, ppid, linha) for pid, ppid, linha in achados
            if "run_live.py" in linha and "Get-CimInstance" not in linha]


def _read_all_states() -> dict:
    """`{slot: estado}` cru do arquivo, sem conferir vivacidade -- ao
    contrario de `status_all()`, que autocorrige. Aqui a autocorrecao seria
    errada: esta tela existe para comparar o arquivo com a REALIDADE, e um
    leitor que ja arruma o arquivo antes esconde a divergencia que o dono
    precisa ver."""
    todos = _read_all()
    return {sid: est for sid, est in (todos.get("slots") or {}).items() if est}


def listar_processos() -> list[ProcessoRobo]:
    """Todo supervisor de robo vivo nesta maquina, rastreado ou nao.

    Um supervisor aparece DUAS vezes na varredura do Windows (o `python.exe`
    do venv e' um lancador que cria o interpretador de verdade como filho,
    com a mesma linha de comando). Mostrar os dois faria a tela listar seis
    linhas para tres robos e convidaria o dono a matar a metade errada,
    entao o filho e' dobrado dentro do pai (`filhos`) em vez de virar linha
    propria -- e quem mata o pai leva a arvore junto.

    Ordena por slot para a lista nao dancar entre dois refreshes."""
    achados = _processos_do_sistema()
    pids = {pid for pid, _ppid, _linha in achados}
    filhos_de: dict[int, list[int]] = {}
    for pid, ppid, _linha in achados:
        if ppid in pids:
            filhos_de.setdefault(ppid, []).append(pid)

    rastreados = {
        est["pid"]: sid
        for sid, est in _read_all_states().items()
        if est.get("pid") is not None
    }
    processos = []
    for pid, ppid, linha in achados:
        if ppid in pids:
            continue  # e' o interpretador filho de um supervisor ja listado
        processos.append(ProcessoRobo(
            pid=pid,
            slot=_argumento(linha, "slot") or rastreados.get(pid),
            execution_mode=_argumento(linha, "execution-mode"),
            rastreado=pid in rastreados,
            filhos=tuple(sorted(filhos_de.get(pid, ()))),
            linha_de_comando=linha,
        ))
    return sorted(processos, key=lambda p: (p.slot or "", p.pid))


def _matar_arvore(pid: int) -> None:
    """Encerra `pid` e a arvore dele. Nao levanta: matar um PID que ja morreu
    e' o resultado desejado, nao um erro."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=10)
        return
    import signal

    for sinal in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sinal)
        except OSError:
            return
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
        except OSError:
            return


def _parar_processo_nao_rastreado(slot: str) -> bool:
    """Mata TODOS os supervisores deste slot que o arquivo de estado não
    conhece. `False` se não havia nenhum (o caso normal de "já estava
    parado").

    Percorre a lista inteira em vez de parar no primeiro achado (bug
    encontrado numa conferência manual do dono, 2026-08-31: um `return True`
    antecipado deixava um SEGUNDO órfão do mesmo slot escapar da varredura
    sempre que mais de um estivesse vivo ao mesmo tempo — exatamente o
    cenário que esta função existe para fechar).

    Indeterminação vira `False`, e não exceção: quem chama é o botão "Parar",
    e derrubar a tela com erro porque a varredura engasgou seria pior que
    dizer "não havia o que parar" e deixar o dono clicar de novo."""
    try:
        processos = listar_processos()
    except _TasklistUnavailable:
        return False
    matou = False
    for processo in processos:
        if processo.slot == slot:
            _matar_arvore(processo.pid)
            for filho in processo.filhos:
                _matar_arvore(filho)
            matou = True
    return matou


def encerrar_processo(pid: int) -> ProcessoRobo:
    """Mata o supervisor `pid` (e a arvore dele) e devolve o que foi morto.

    RECUSA (`ValueError`) qualquer PID que a varredura nao reconheca como um
    `run_live.py` vivo. Isto nao e' zelo decorativo: o `pid` chega pela URL
    de um POST, e sem a conferencia o endpoint seria "mate qualquer processo
    desta maquina pelo numero", exposto em HTTP -- inclusive o proprio
    dashboard, o terminal MT5 ou o Windows.

    Tambem limpa o `pid` do arquivo de estado quando o processo era
    rastreado, para o cartao do robo nao continuar dizendo "rodando" depois
    de esta tela ter matado o processo dele."""
    alvos = {p.pid: p for p in listar_processos()}
    processo = alvos.get(int(pid))
    if processo is None:
        raise ValueError(
            f"o PID {pid} nao e (mais) um robo em execucao — a lista pode ter "
            "mudado desde que a tela foi carregada; recarregue e tente de novo."
        )
    _matar_arvore(processo.pid)
    for filho in processo.filhos:
        _matar_arvore(filho)
    if processo.rastreado:
        for sid, est in _read_all_states().items():
            if est.get("pid") == processo.pid:
                _write_state(sid, {**est, "pid": None, "started_at": None})
    return processo


def inventario_processos() -> tuple[list[ProcessoRobo], Optional[str]]:
    """`(processos, motivo)` — a mesma varredura de `listar_processos()`, mas
    que NUNCA levanta: uma varredura que engasgou vira `([], motivo)`.

    Existe para a tela (`/operacao/processos`): esta lista é o inventário de
    "o que está rodando de verdade nesta máquina", e derrubar a página com
    500 porque o PowerShell demorou seria trocar a informação que faltava por
    informação nenhuma. O motivo volta em texto para o painel poder dizer
    "não consegui varrer agora" em vez de "não há nada rodando" — as duas
    frases são opostas, e a segunda é a que faz o dono ir dormir com um robô
    solto.
    """
    try:
        return listar_processos(), None
    except _TasklistUnavailable as e:
        return [], str(e)


# ---------- watchdog de travamento (heartbeat) --------------------------
#
# `status()`/`status_all()` respondem "o PID existe no SO?" -- isso nao prova
# que o processo esta' PROGREDINDO. Achado ao vivo em 02/09/2026: os 7
# supervisores de day trade travaram (CPU acumulada parada, PID de pe' o
# tempo todo, `tasklist` os via' "rodando") por 21h+, um pregao inteiro
# perdido em silencio -- inclusive `dt-gremah-pmam3-live`, dinheiro real.
# Causa provavel: uma chamada do pacote `MetaTrader5` (IPC nativo, sem
# timeout) bloqueada para sempre quando a rede cai NO MEIO dela.
#
# `scripts/run_live.py::_loop_travado` toca `db/live_process.<slot>.heartbeat`
# (so' o mtime importa) a cada volta do laco, inclusive durante o sono fora
# do horario de pregao (fatiado em pedacos de ate' 60s -- ver
# `_HEARTBEAT_CHUNK_SECONDS` la'). Um heartbeat mais velho que o limiar, com
# o PID ainda vivo, e' o sinal de travamento: nada mais no sistema hoje
# diferencia isso de "operando normalmente".

#: Margem sobre o intervalo de passo do slot antes de considerar travado.
_HEARTBEAT_MARGIN = 6
#: Piso absoluto, mesmo para o swing (passo de 60s -- 6x isso seria só 6min).
#:
#: Era 180s (3min) na primeira versão -- ERRADO, achado ao vivo em
#: 02/09/2026 pouco depois de ligado: `wdo_grid_reload_maker` entrou num
#: laço de reinício a cada ~3min por HORAS (`live_events`, fonte "watchdog",
#: 14:35 a 16:19). Causa: sob conectividade degradada (medido `ping_last`
#: ~6,3s no terminal MT5 nesse mesmo dia, contra <500ms normal), o passo de
#: warm-start/catch-up de barras perdidas (o robô já tolera sozinho buracos
#: de 18-26min via `_parado_ha_segundos`, ver os eventos "buraco de N min
#: sem rodar") pode legitimamente passar de 180s numa ÚNICA chamada de
#: `run_once()` -- e o heartbeat só é tocado no TOPO do laço, uma vez por
#: iteração inteira. O watchdog matava o processo NO MEIO do catch-up, sempre
#: antes dele terminar, e cada reinício reiniciava o mesmo catch-up (mais
#: atrasado ainda) do zero -- um loop que só piora a si mesmo. 900s (15min)
#: dá folga confortável acima do que o próprio robô já tolera como gap
#: normal, e ainda detecta um travamento de verdade ~84x mais rápido que o
#: incidente original de 21h+.
_HEARTBEAT_FLOOR_SECONDS = 900.0
#: Quantas vezes o watchdog tenta reiniciar sozinho o MESMO slot dentro da
#: janela de cooldown antes de desistir e só alertar -- um travamento que
#: volta rápido demais depois de reiniciado é sintoma de problema estrutural
#: (terminal fechado, credencial errada, disco cheio), não de rede
#: instável, e reiniciar sem parar nesse caso só bate cabeça sozinho.
_MAX_AUTO_RESTARTS = 3

#: MESMO valor de `app.py::WATCHDOG_INTERVAL_SECONDS` (o laço de fundo só
#: verifica travamento 1x/min) -- duplicado aqui (não importado) pelo mesmo
#: motivo de `_heartbeat_path` acima: `app.py` já importa `dashboard.
#: live_control`, então importar `app` daqui de volta fecharia um ciclo.
_WATCHDOG_POLL_INTERVAL_SECONDS = 60.0

#: Duração do PIOR ciclo completo "trava -> detecta -> mata -> sobe" que o
#: cooldown precisa enxergar: `_HEARTBEAT_FLOOR_SECONDS` até o heartbeat
#: ficar velho o bastante para ser flagrado, mais até
#: `_WATCHDOG_POLL_INTERVAL_SECONDS` de atraso do laço de fundo (só verifica
#: 1x/min, pode achar o travamento quase um minuto depois de cruzar o piso),
#: mais a subida do processo novo (`_STARTUP_GRACE_SECONDS`, 2s -- desprezível
#: ao lado dos outros dois, por isso fora da soma). Confirmado ao vivo em
#: 04/09/2026 no slot `dt-wdo_grid_reload_maker-wdo@-shadow` (`live_events`,
#: `source='watchdog'`): reinícios às 13:28:53, 13:45:04 e 14:01:00 -- gaps
#: de 971s e 956s, batendo os ~960s previstos aqui (jitter de rede/disco
#: explica a diferença de ~1-2%).
_RESTART_CYCLE_SECONDS = _HEARTBEAT_FLOOR_SECONDS + _WATCHDOG_POLL_INTERVAL_SECONDS

#: Janela do cooldown de `_registrar_tentativa`. ERA `_COOLDOWN_WINDOW_
#: SECONDS = _HEARTBEAT_FLOOR_SECONDS` (900.0 solto, mesmo valor do piso) --
#: bug de DESENHO achado por auditoria em 04/09/2026 com o dado real citado
#: acima: o ciclo completo de detecção+reinício (~960s, `_RESTART_CYCLE_
#: SECONDS`) já é MAIOR que uma janela de 900s, então a tentativa anterior
#: sempre cai da lista (`agora - t < _COOLDOWN_WINDOW_SECONDS`) ANTES da
#: próxima tentativa ser registrada -- o contador nunca passa de 1,
#: `_MAX_AUTO_RESTARTS` nunca é atingido, e o watchdog reinicia o MESMO slot
#: PARA SEMPRE (exatamente o que `_MAX_AUTO_RESTARTS` existe para evitar; foi
#: isso que aconteceu 3x seguidas no slot acima, 13:28-14:01, sem o contador
#: nunca ver mais de 1 tentativa viva).
#:
#: A conta certa: se `_MAX_AUTO_RESTARTS` tentativas aconteceram nos piores
#: instantes possíveis -- 0, g, 2g, ..., (N-1)*g, cada uma exatamente quando
#: a anterior libera um novo ciclo -- a checagem que teria de flagrar a
#: (N+1)-ésima como "travou de novo rápido demais" roda em N*g (um ciclo
#: depois da última), e olha para trás até a 1ª tentativa (em t=0), a
#: `N*g` de distância. Ou seja, a janela precisa ser MAIOR que `N * g`, não
#: `(N-1) * g` -- usar só `N-1` deixa a 1ª tentativa cair da lista um
#: instante antes de a (N+1)-ésima checagem rodar, e o contador nunca fecha
#: em `N` (é exatamente essa fresta de 1 ciclo que fazia a janela antiga,
#: igual a 1 ciclo em vez de folgada, nunca acumular -- ver acima).
#: Multiplicar por `_MAX_AUTO_RESTARTS + 1` em vez do mínimo estrito
#: `_MAX_AUTO_RESTARTS` dá uma folga de um `_RESTART_CYCLE_SECONDS` inteiro
#: por cima -- tolera o ciclo real ser até ~33% mais longo que o modelo
#: (`(N+1)/N` para N=3) antes do cooldown parar de fechar em `N`, folga bem
#: acima do jitter medido ao vivo (~1-2%, ver `_RESTART_CYCLE_SECONDS`).
_COOLDOWN_WINDOW_SECONDS = (_MAX_AUTO_RESTARTS + 1) * _RESTART_CYCLE_SECONDS

#: `{slot_id: [timestamps unix dos restarts recentes]}` -- em memória,
#: reseta com o dashboard (aceitável: um restart do próprio dashboard já é
#: um ponto de corte natural para o cooldown, e persistir isto em disco só
#: para sobreviver a um restart do dashboard não paga o custo).
_restart_attempts: dict[str, list[float]] = {}


def _heartbeat_path(slot_id: str) -> Path:
    """MESMA fórmula de `scripts/run_live.py::_heartbeat_path` -- duplicada
    de propósito (não importada) para não criar uma dependência de
    `scripts/` sobre `dashboard/`; é uma convenção de path de 1 linha, o
    mesmo raciocínio de `_log_path` já não ser compartilhada com o CLI."""
    return _LOG_DIR / f"live_process.{slot_id}.heartbeat"


def _hang_threshold_seconds(slot) -> float:
    """Limiar de idade do heartbeat acima do qual o slot é considerado
    travado. Os números de passo (5s intraday / 60s swing) são os MESMOS que
    `start()` usa para montar `argv` (`loop --seconds ...`) -- não há um
    terceiro lugar hoje que os declare como constante compartilhada."""
    passo = 5.0 if slot.is_intraday else 60.0
    return max(_HEARTBEAT_FLOOR_SECONDS, _HEARTBEAT_MARGIN * passo)


def _heartbeat_age_seconds(slot_id: str) -> Optional[float]:
    """Segundos desde o último toque do heartbeat deste slot, ou `None` se o
    arquivo não existe -- o que é NORMAL logo após um `start()` (o processo
    filho ainda não deu a primeira volta do laço) e não deve ser lido como
    sinal de travamento."""
    try:
        return time.time() - _heartbeat_path(slot_id).stat().st_mtime
    except OSError:
        return None


def slots_travados(reconciliar: bool = True) -> list[str]:
    """Slots com PID vivo (`status_all`) mas heartbeat mais velho que
    `_hang_threshold_seconds` -- o sinal de travamento. Um slot sem PID
    (parado de propósito, ou nunca iniciado) nunca entra aqui: heartbeat
    velho de um processo que já não existe não é travamento, é o esperado."""
    from core.config import slot_by_id

    estados = status_all(reconciliar=reconciliar)
    travados = []
    for sid, est in estados.items():
        if est is None or est.get("pid") is None:
            continue
        idade = _heartbeat_age_seconds(sid)
        if idade is None:
            continue
        if idade > _hang_threshold_seconds(slot_by_id(sid)):
            travados.append(sid)
    return travados


def _registrar_tentativa(slot_id: str) -> bool:
    """Registra AGORA como uma tentativa de restart deste slot e devolve
    `True` se ainda está dentro do limite (`_MAX_AUTO_RESTARTS` na janela de
    `_COOLDOWN_WINDOW_SECONDS`) -- `False` se o watchdog deve desistir de
    reiniciar sozinho desta vez."""
    agora = time.time()
    tentativas = [t for t in _restart_attempts.get(slot_id, ())
                  if agora - t < _COOLDOWN_WINDOW_SECONDS]
    if len(tentativas) >= _MAX_AUTO_RESTARTS:
        _restart_attempts[slot_id] = tentativas
        return False
    tentativas.append(agora)
    _restart_attempts[slot_id] = tentativas
    return True


class PosicaoAbertaError(RuntimeError):
    """`reiniciar_travado` recusou reiniciar porque há posição aberta na
    corretora para este slot -- ou a consulta falhou e "não sei" foi tratado
    como "pode ter" (tri-estado, item 1.6 de LICOES_DE_PRODUCAO.md) -- e o
    chamador não passou `permitir_com_posicao_aberta=True`.

    Tipo próprio (em vez de `RuntimeError` genérico) para
    `verificar_e_recuperar_travamentos` distinguir isto de qualquer OUTRA
    falha de restart (piso de caixa, colisão de símbolo, processo que morre
    logo após subir) e alertar com mensagem específica, em vez de cair no
    "falhou" genérico."""


def _posicao_aberta_na_corretora(slot, robot_key: Optional[str]) -> tuple[Optional[bool], str]:
    """Pergunta à CORRETORA -- nunca ao diário nem a `policy_state`, os dois
    podem estar defasados (foi exatamente esse tipo de divergência que
    motivou o item 1.7 de LICOES_DE_PRODUCAO.md) -- se há posição aberta
    neste slot, para QUALQUER ticker do universo do robô `robot_key`
    (`universe_for_slot`; um slot de day trade tem um só ticker, swing pode
    ter vários).

    Tri-estado, devolvido como `(estado, motivo)`:
      - `(True, motivo)` -- há posição confirmada em pelo menos um ticker.
      - `(False, "")` -- perguntou a TODOS os tickers e nenhum tinha posição.
      - `(None, motivo)` -- pelo menos uma consulta FALHOU (terminal fora do
        ar, pacote MetaTrader5 indisponível, erro inesperado). Item 1.6:
        "não sei" NUNCA vira "não tem" -- o chamador trata `None` exatamente
        como `True` (não autoriza reiniciar sozinho).

    Filtra por `slot.magic` (via `_broker_for_detection(magic=...)`): a conta
    MT5 é NETTING e compartilhada entre slots, então sem o filtro certo esta
    função veria a posição de OUTRO robô como sua (ou vice-versa)."""
    try:
        tickers = universe_for_slot(slot.id, robot_key)
        if not tickers:
            return False, ""
        broker = _broker_for_detection(magic=slot.magic)
        for ticker in tickers:
            estado = broker.position_state(ticker)
            if not estado["ok"]:
                return None, (
                    f"não foi possível consultar a posição de {ticker!r} na "
                    f"corretora ({estado['note']})"
                )
            posicao = estado["position"]
            if posicao is not None:
                return True, (
                    f"posição aberta em {ticker!r} na corretora "
                    f"({posicao['side']}, qty={posicao['quantity']})"
                )
        return False, ""
    except Exception as exc:  # noqa: BLE001 -- qualquer falha inesperada aqui é "não sei", nunca "não tem" (item 1.6)
        return None, f"falha inesperada ao consultar posição na corretora: {exc}"


def reiniciar_travado(slot_id: str, *, permitir_com_posicao_aberta: bool = False) -> dict:
    """Mata o processo travado deste slot e sobe de novo, REDETECTANDO os
    parâmetros do terminal (mesmo caminho que `dashboard/app.py::
    operacao_iniciar` já faz para uma conta já existente) -- nunca reaproveita
    `mt5_symbol_map`/`mt5_fractional_map` salvos em `db/live_process.json`
    cegamente. Isso importa em especial para `mt5_symbol_map`: se o contrato
    de futuro (WDO/WIN) rolou durante a janela em que o slot ficou travado, o
    mapa salvo aponta pro contrato antigo e toda ordem seria recusada de novo
    pelo servidor (mesmo sintoma do achado de 2026-08-28, "Trade disabled").

    `capital` também é relido do ledger atual (`available_cash`), não do
    `capital` salvo -- o dono pode ter ajustado o caixa do slot enquanto ele
    estava travado.

    `permitir_com_posicao_aberta` (default `False`, achado ao vivo em
    04/09/2026): por padrão RECUSA reiniciar se há posição aberta na
    CORRETORA para este slot, ou se a consulta falhar (`_posicao_aberta_na_
    corretora`, tri-estado -- item 1.6). Motivo: a posição já tem stop/alvo
    REGISTRADOS na corretora (item 1.2 de LICOES_DE_PRODUCAO.md -- "proteção
    tem de morar na CORRETORA, não no laço do processo") e segue protegida
    com o processo morto; reiniciar dispara o protocolo de buraco do runtime
    (`IntradayLiveRuntime._start_session`/`force_flatten`), que pode ACHATAR
    a posição A MERCADO -- uma saída decidida pela INFRAESTRUTURA, não pelo
    mercado. Um robô travado com posição protegida é problema para o DONO
    decidir, não para a infra resolver sozinha. O caminho AUTOMÁTICO
    (`verificar_e_recuperar_travamentos`) nunca passa `True` aqui; só quem
    chama manualmente (painel/CLI), já tendo conferido a posição de verdade,
    pode pedir a passagem explícita.

    Levanta se não houver PID registrado (nada a reiniciar), se a conta não
    tiver `investment_robot` gravado (robô nunca escolhido -- não há como
    redetectar sozinho, precisa de 'Iniciar' manual no painel), ou
    `PosicaoAbertaError` se houver posição aberta (ou consulta falha) sem
    `permitir_com_posicao_aberta=True`. Estas três checagens rodam ANTES de
    matar o processo -- de propósito: uma checagem que vai recusar o restart
    não deve matar um supervisor que, travado ou não, continua sendo a única
    coisa viva vigiando o resto do estado local. Deixa qualquer outra falha
    de `start()` (piso de caixa, colisão de símbolo, processo que morre logo
    após subir) subir tal como está -- já carregam mensagem própria."""
    from core.config import slot_by_id
    from journal import live_store

    slot = slot_by_id(slot_id)
    estado = _read_state(slot_id)
    if estado is None or estado.get("pid") is None:
        raise RuntimeError(f"slot {slot_id!r} não está rodando -- nada a reiniciar.")

    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot_id)
    if conta is None or not conta.investment_robot:
        raise RuntimeError(
            f"slot {slot_id!r} travado mas sem conta/robô gravado -- não dá "
            "para redetectar sozinho, use 'Iniciar' manual no painel."
        )

    if not permitir_com_posicao_aberta:
        tem_posicao, motivo_posicao = _posicao_aberta_na_corretora(slot, conta.investment_robot)
        if tem_posicao is not False:  # True (tem) ou None (não sei) -- os dois bloqueiam, item 1.6
            raise PosicaoAbertaError(
                f"slot {slot_id!r} travado, mas NÃO reiniciado: "
                f"{motivo_posicao or 'não foi possível confirmar a ausência de posição na corretora'}. "
                "Proteção (stop/alvo) já mora na corretora e segue valendo com o processo morto -- "
                "reiniciar dispararia o protocolo de buraco do runtime, que pode achatar a posição a "
                "mercado por decisão da infraestrutura, não do mercado. Confira a posição de verdade e "
                "chame de novo com permitir_com_posicao_aberta=True se quiser reiniciar mesmo assim."
            )

    _matar_arvore(estado["pid"])
    # Achado ao vivo em 02/09/2026: ler o diário LOGO após um `taskkill /F`
    # às vezes esbarra em "disk I/O error" -- o processo morto ainda segura
    # por uma fração de segundo o mapeamento do WAL do SQLite (`journal_mode
    # =WAL`, ver `journal.live_store._connect`), e o SO ainda não liberou o
    # arquivo por completo. `taskkill` é assíncrono (devolve antes do
    # processo terminar de verdade); esta folga é a mesma ideia de
    # `_STARTUP_GRACE_SECONDS` em `start()`, só que do lado da MORTE em vez
    # da subida.
    time.sleep(0.5)
    # `start()` recusa de cara se `status(slot)` ainda apontar um PID
    # (mesmo guard de `stop()`) -- sem zerar aqui, o PID que acabou de ser
    # morto continuaria "rodando" no arquivo de estado e `start()` abaixo
    # se recusaria com "já está rodando".
    _write_state(slot_id, {**estado, "pid": None, "started_at": None})

    strategy_key = conta.investment_robot
    execution_mode = slot.execution_mode if slot.is_intraday else "live"
    capital = available_cash(slot_id, execution_mode) or 0.0
    shares = detect_shares_per_lot(slot_id, strategy_key)
    fractional = (detect_fractional_symbol_map(slot_id, strategy_key)
                  if not slot.is_intraday else None)
    symbol_map = (detect_futures_symbol_map(slot_id, strategy_key)
                  if slot.is_intraday else None)

    cfg = ProcessConfig(
        mode="mt5", capital=capital, strategy=strategy_key, slot=slot_id,
        execution_mode=execution_mode,
        notify_min_level=(estado.get("config") or {}).get("notify_min_level", "warn"),
        mt5_shares_per_lot=shares, mt5_fractional_map=fractional, mt5_symbol_map=symbol_map,
    )
    return start(cfg)


def verificar_e_recuperar_travamentos() -> list[dict]:
    """Orquestrador chamado periodicamente pelo laço de fundo do dashboard
    (`app.py::_watchdog_loop`): detecta slots travados (`slots_travados`),
    grava o achado em `live_events`, notifica pelo canal externo configurado
    e tenta reiniciar sozinho -- respeitando o cooldown (`_registrar_
    tentativa`), que desiste de tentar de novo depois de `_MAX_AUTO_RESTARTS`
    numa janela curta e só alerta pedindo intervenção manual.

    NUNCA reinicia um slot com posição aberta na corretora (achado do dono,
    04/09/2026): antes de gastar uma tentativa do cooldown, pergunta a
    `_posicao_aberta_na_corretora` -- se houver posição (ou a consulta
    falhar, tri-estado do item 1.6) grava o achado, notifica e DESISTE desta
    rodada sem contar como tentativa de restart (`acao="posicao_aberta"`),
    pedindo intervenção humana. Ver a docstring de `reiniciar_travado` para o
    raciocínio completo (proteção mora na corretora, achatar por decisão da
    infra é pior que ficar travado). Checado ANTES do cooldown de propósito:
    um slot travado com posição aberta por vários polos seguidos não é "3
    tentativas de restart falhando" (não é nem tentativa), é a MESMA causa
    -- contar como cooldown trocaria a mensagem certa ("posição aberta") por
    uma errada ("problema estrutural, desisti") depois de 3 polls.
    `reiniciar_travado` também checa isto por conta própria (defesa em
    profundidade para qualquer OUTRO chamador) -- a checagem aqui é só para
    não misturar as duas causas de desistência no relatório/mensagem.

    Devolve um relatório por slot travado (`slot`, `idade_heartbeat_s`,
    `acao`: "reiniciado"/"falhou"/"cooldown"/"posicao_aberta", detalhe) --
    usado só em teste e log do próprio laço de fundo; o dashboard não expõe
    isto em rota alguma hoje."""
    from core.config import slot_by_id
    from journal import live_store

    relatorio: list[dict] = []
    for slot_id in slots_travados():
        slot = slot_by_id(slot_id)
        idade = _heartbeat_age_seconds(slot_id) or 0.0
        estado = _read_state(slot_id) or {}
        notify_min_level = (estado.get("config") or {}).get("notify_min_level", "warn")
        notifier = _load_cli()._build_notifier(notify_min_level)

        with live_store.live_journal() as conn:
            conta = live_store.load_account(conn, slot_id)
            conta_id = conta.id if conta is not None else None
            msg = (f"slot {slot.label!r} travado -- heartbeat parado há "
                   f"{idade / 60:.1f}min com o processo ainda de pé (achado pelo "
                   "watchdog).")
            live_store.log_event(conn, conta_id, "error", "watchdog", msg,
                                 {"slot": slot_id, "idade_heartbeat_s": idade})
        notifier.notify("error", "watchdog", msg, {"slot": slot_id})

        robot_key = conta.investment_robot if conta is not None else None
        tem_posicao, motivo_posicao = _posicao_aberta_na_corretora(slot, robot_key)
        if tem_posicao is not False:  # True (tem) ou None (não sei) -- os dois bloqueiam, item 1.6
            msg_posicao = (
                f"slot {slot.label!r} travado, mas o watchdog NÃO vai reiniciar sozinho: "
                f"{motivo_posicao or 'não foi possível confirmar a ausência de posição na corretora'}. "
                "Proteção (stop/alvo) já mora na CORRETORA (item 1.2 de LICOES_DE_PRODUCAO.md) e "
                "segue valendo com o processo morto; reiniciar dispararia o protocolo de buraco do "
                "runtime, que pode ACHATAR a posição A MERCADO -- saída decidida pela infraestrutura, "
                "não pelo mercado. Precisa de intervenção humana: confira a posição e, se quiser "
                "reiniciar mesmo assim, use 'reiniciar_travado' com permitir_com_posicao_aberta=True."
            )
            with live_store.live_journal() as conn:
                live_store.log_event(conn, conta_id, "error", "watchdog", msg_posicao,
                                     {"slot": slot_id})
            notifier.notify("error", "watchdog", msg_posicao, {"slot": slot_id})
            relatorio.append({"slot": slot_id, "idade_heartbeat_s": idade,
                              "acao": "posicao_aberta", "detalhe": msg_posicao})
            continue

        if not _registrar_tentativa(slot_id):
            msg_desiste = (f"slot {slot.label!r} travou de novo rápido demais "
                           f"({_MAX_AUTO_RESTARTS}x em {_COOLDOWN_WINDOW_SECONDS/60:.0f}min) "
                           "-- watchdog desistiu de reiniciar sozinho, provável "
                           "problema estrutural (terminal fechado, credencial "
                           "errada). Precisa de intervenção manual.")
            with live_store.live_journal() as conn:
                live_store.log_event(conn, conta_id, "error", "watchdog", msg_desiste,
                                     {"slot": slot_id})
            notifier.notify("error", "watchdog", msg_desiste, {"slot": slot_id})
            relatorio.append({"slot": slot_id, "idade_heartbeat_s": idade,
                              "acao": "cooldown", "detalhe": msg_desiste})
            continue

        try:
            novo_estado = reiniciar_travado(slot_id)
        except Exception as e:  # noqa: BLE001 -- qualquer falha de restart é reportada, nunca propagada ao laço de fundo
            msg_falha = f"slot {slot.label!r}: watchdog tentou reiniciar e falhou -- {e}"
            with live_store.live_journal() as conn:
                live_store.log_event(conn, conta_id, "error", "watchdog", msg_falha,
                                     {"slot": slot_id})
            notifier.notify("error", "watchdog", msg_falha, {"slot": slot_id})
            relatorio.append({"slot": slot_id, "idade_heartbeat_s": idade,
                              "acao": "falhou", "detalhe": str(e)})
            continue

        msg_ok = (f"slot {slot.label!r} reiniciado automaticamente pelo watchdog "
                 f"(novo pid={novo_estado['pid']}).")
        with live_store.live_journal() as conn:
            live_store.log_event(conn, conta_id, "warn", "watchdog", msg_ok,
                                 {"slot": slot_id, "pid": novo_estado["pid"]})
        notifier.notify("warn", "watchdog", msg_ok, {"slot": slot_id})
        relatorio.append({"slot": slot_id, "idade_heartbeat_s": idade,
                          "acao": "reiniciado", "detalhe": msg_ok})
    return relatorio
