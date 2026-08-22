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
from dataclasses import asdict, dataclass
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
    docstring do lock."""
    todos = _read_all()
    if state is None:
        todos["slots"].pop(slot, None)
    else:
        todos["slots"][slot] = state
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _pid_alive(pid: int) -> bool:
    """Windows não tem um `os.kill(pid, 0)` confiável para checar
    vivacidade — consulta o `tasklist` do próprio sistema."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return str(pid) in out.stdout


def status(slot: str) -> Optional[dict]:
    """Estado do processo supervisor DESTE slot, ou `None` se não está rodando.

    Autocorrige: se o arquivo aponta para um PID que já morreu (processo
    caiu, servidor reiniciou sem o serviço) sem ter passado por `stop()`,
    marca como parado em vez de dizer que está rodando quando não está —
    mas preserva a `config`, para `last_config()` continuar funcionando."""
    state = _read_state(slot)
    if state is None or state.get("pid") is None:
        return None
    if not _pid_alive(state["pid"]):
        _write_state(slot, {**state, "pid": None, "started_at": None})
        return None
    return state


def status_all() -> dict[str, Optional[dict]]:
    """`{slot_id: status(slot_id)}` para TODO slot do catálogo — o painel
    precisa dos dois cartões de uma vez, e chamar `status()` em laço no
    template esconderia o custo do `tasklist` por slot."""
    from core.config import SLOTS

    return {slot.id: status(slot.id) for slot in SLOTS}


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


def _broker_for_detection():
    """Um `MT5Broker` só para CONSULTA (`symbol_info`/saldo), montado com as
    credenciais SALVAS (`load_credentials()`) e nunca via `os.environ`:
    diferente de `start()` (que injeta `_credentials_env()` no `env` do
    processo FILHO), uma chamada feita aqui roda no processo do DASHBOARD,
    que nunca recebe essas variáveis — daria `login=None` mesmo com as
    credenciais MT5 salvas corretamente."""
    from live.broker_mt5 import MT5Broker

    creds = load_credentials()
    login = creds.get("mt5_login")
    return MT5Broker(
        login=int(login) if login else None,
        password=creds.get("mt5_password"),
        server=creds.get("mt5_server"),
        path=creds.get("mt5_terminal_path"),
    )


def universe_for_slot(slot_id: str, robot_key: Optional[str] = None) -> tuple[str, ...]:
    """Símbolos/tickers que este slot precisa consultar no terminal, para o
    robô `robot_key` — ou o default do catálogo (`Slot.robot_key`) se
    omitido, útil quando quem chama ainda não sabe qual robô vai rodar (ex.:
    uma conta já existente cujo robô real está gravado nela, não no
    catálogo — ver chamadores).

    Slot `intraday` resolve pelo registry PRÓPRIO de day trade
    (`strategy.daytrade.registry`) — não passa pelo registry de swing, que
    nem conhece robôs de day trade (`IntradayStrategy` não herda de
    `Strategy`, ver `strategy/daytrade/base.py`). O ativo é propriedade do
    ROBÔ (`robo.symbol`), não do slot — `core.config.Slot` não declara
    símbolo desde 2026-08-21. Slot `daily` usa o universo do próprio robô via
    o MESMO `_universe_of()` de `run_live.py::build()`."""
    from core.config import WATCHLIST, slot_by_id

    slot = slot_by_id(slot_id)
    key = robot_key or slot.robot_key
    if slot.is_intraday:
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
        mt5_magic=slot.magic, mt5_shares_per_lot=config.mt5_shares_per_lot, mt5_symbol_map=None,
        mt5_fractional_map=json.dumps(config.mt5_fractional_map) if config.mt5_fractional_map else None,
    )
    rt = cli.build(args)
    return rt.ensure_account()


def _assert_slots_disjuntos(slot, robot_key: str) -> None:
    """A conta da Rico é NETTING (`margin_mode=0`, verificado no terminal
    real em 2026-08-21): duas ordens no MESMO símbolo se FUNDEM numa posição
    única na corretora, independente de `magic`. Dois slots compartilhando
    símbolo transformariam os dois livros-caixa em ficção — um venderia a
    posição do outro sem saber. Checado aqui (e não só no catálogo) porque
    `SLOTS` é editável e o custo do erro é dinheiro real.

    `robot_key` é o robô que ESTE slot está prestes a rodar — desde que o
    símbolo deixou de ser campo do slot (2026-08-21), a única forma de saber
    o que ele vai negociar é perguntar ao robô escolhido
    (`universe_for_slot`). O outro lado da comparação usa o robô JÁ GRAVADO
    na conta do outro slot, se existir (nunca o default do catálogo, que
    pode não ser o que a conta de fato opera) — ver `universe_for_slot`."""
    from core.config import SLOTS
    from journal import live_store

    meu_universo = set(universe_for_slot(slot.id, robot_key))
    for outro in SLOTS:
        if outro.id == slot.id:
            continue
        if outro.magic == slot.magic:
            raise RuntimeError(
                f"slots {slot.id!r} e {outro.id!r} declaram o mesmo `magic` "
                f"({slot.magic}) — as ordens dos dois robôs ficariam "
                "indistinguíveis na corretora. Corrija `core.config.SLOTS`."
            )
        with live_store.live_journal() as conn:
            conta_outro = live_store.load_account(conn, outro.id)
        outro_robot_key = (conta_outro.investment_robot if conta_outro else None) or outro.robot_key
        colisao = meu_universo & set(universe_for_slot(outro.id, outro_robot_key))
        if colisao:
            raise RuntimeError(
                f"slots {slot.id!r} e {outro.id!r} negociam o(s) mesmo(s) símbolo(s) "
                f"({', '.join(sorted(colisao))}) numa conta NETTING — as posições se "
                "fundiriam numa só e os dois caixas passariam a mentir."
            )


def available_cash(slot_id: str) -> Optional[float]:
    """Caixa que o LEDGER MANUAL diz pertencer a este slot, ou `None` se a
    conta ainda não existe.

    Fonte de verdade deliberada: o número digitado no painel, no banco — NÃO
    `Broker.cash_balance()`. Ver o comentário no lugar de
    `detect_broker_capital()` (removida): o saldo do terminal MT5 atrasa em
    relação ao da Rico, e com dois robôs disputando a mesma conta um número
    atrasado viraria dois livros-caixa errados."""
    from journal import live_store

    try:
        with live_store.live_journal() as conn:
            conta = live_store.load_account(conn, slot_id)
    except (live_store.LegacyPaperAccountError, live_store.LegacyManualAccountError):
        return None
    return None if conta is None else round(conta.cash, 2)


def _intraday_capital_minimo(robot_key: str) -> Optional[float]:
    """Piso de caixa para operar HOJE o robô `robot_key` — `capital_minimo_brl`
    (`strategy.daytrade.base`) do símbolo dele, no último preço salvo
    localmente. `None` se o robô não existir no catálogo, o símbolo não tiver
    perfil (`backtest.intraday.profiles.PROFILES`) ou não houver preço salvo
    ainda (parquet ausente) — quem chama decide o degrade, nunca bloqueia por
    falta de dado que não é culpa do dono."""
    from backtest.intraday.profiles import PROFILES
    from dashboard.robot_view import _ultimo_preco
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.registry import get_daytrade_robot

    try:
        robo = get_daytrade_robot(robot_key)
    except KeyError:
        return None
    perfil = PROFILES.get(robo.symbol)
    if perfil is None:
        return None
    preco, _data = _ultimo_preco(robo.symbol)
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
    minimo = _intraday_capital_minimo(robot_key or slot.robot_key)
    return slot.min_cash_brl if minimo is None else minimo


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
        if not config.strategy:
            raise RuntimeError(
                "nenhum robô de investimento selecionado — não há robô "
                "padrão (ver docstring de scripts/run_live.py, seção 'Robô "
                "de investimento')."
            )
        # Depende de `config.strategy` já resolvido (o robô decide o
        # universo/símbolo, ver docstring da função) — por isso checado
        # DEPOIS do guard acima, nunca antes.
        _assert_slots_disjuntos(slot, config.strategy)
        if config.mt5_shares_per_lot is None or config.mt5_shares_per_lot <= 0:
            raise RuntimeError(
                "modo mt5 exige 'ações por lote' (mt5_shares_per_lot) — não foi "
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
        caixa = available_cash(config.slot)
        if caixa is None or caixa < piso:
            raise RuntimeError(
                f"caixa do slot '{slot.label}' é R$ {0.0 if caixa is None else caixa:.2f}, "
                f"abaixo do mínimo de R$ {piso:.2f} para operar — "
                "informe o caixa destinado a este robô no painel antes de iniciar."
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
    só `create_account`/CLI podem apagar de vez."""
    state = _read_state(slot)
    if state is None or state.get("pid") is None:
        return False
    pid = state["pid"]
    if _pid_alive(pid):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=10)
    _write_state(slot, {**state, "pid": None, "started_at": None})
    return True
