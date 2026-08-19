"""Controle do processo supervisor (`scripts/run_live.py loop`) a partir do
dashboard — um botão "Iniciar"/"Parar" em vez de terminal.

Fica em `dashboard/` (orquestração) e nunca decide nada por conta própria:
só liga/desliga, como um processo, o MESMO `scripts/run_live.py` que já
existia — a decisão de compra/venda continua inteiramente dentro de
`live/runtime.py`. O estado do processo (PID, config, início) é persistido
em `db/live_process.json` para sobreviver a um restart do próprio dashboard
(o botão "Parar" precisa continuar funcionando mesmo se você fechar e
reabrir o navegador ou reiniciar o servidor do dashboard).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
_STATE_PATH = _ROOT / "db" / "live_process.json"
_LOG_PATH = _ROOT / "db" / "live_process.log"
_SCRIPT = _ROOT / "scripts" / "run_live.py"
_SECRETS_PATH = _ROOT / "db" / "live_secrets.json"

# Segundos entre o `Popen` do supervisor e a checagem de prova de vida
# (`start()`, ver docstring lá embaixo) — módulo-nível, monkeypatchável em
# teste (senão o teste esperaria de verdade). Um processo que vai falhar cedo
# (terminal MT5 ausente, credencial errada) normalmente já morreu bem antes
# disso; 2s é suficiente sem atrasar o clique "Iniciar" de forma perceptível.
_STARTUP_GRACE_SECONDS = 2.0

# Campos aceitos em `save_credentials`/exibidos no form. `_SECRET_FIELDS` sao
# os que NUNCA voltam para o HTML (nem mascarados) — so um booleano
# "configurado" via `credential_status()`; os demais (chat id, host, usuario
# etc.) nao sao segredo em si e podem ser reexibidos para o usuario conferir.
CREDENTIAL_FIELDS = (
    "telegram_bot_token", "telegram_chat_id",
    "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_to", "smtp_from", "smtp_tls",
    "mt5_login", "mt5_password", "mt5_server", "mt5_terminal_path",
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
    mode: str
    capital: float
    floor: Optional[float] = None
    daily_loss_limit: Optional[float] = None
    monthly_loss_limit: Optional[float] = None
    notify_min_level: str = "warn"
    # Obrigatório quando `mode == "mt5"` (sem valor universal — ver docstring
    # de `live/broker_mt5.py`); `create_account()`/`start()` recusam cedo se
    # vier `None` nesse modo, em vez de herdar o default `1.0` do argparse.
    mt5_shares_per_lot: Optional[float] = None


def _read_state() -> Optional[dict]:
    if not _STATE_PATH.exists():
        return None
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_state(state: Optional[dict]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if state is None:
        _STATE_PATH.unlink(missing_ok=True)
        return
    _STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _tail_log(max_chars: int = 2_000) -> str:
    """Últimos `max_chars` de `db/live_process.log` — usado para explicar
    POR QUE o processo morreu logo após subir (ver `start()`)."""
    if not _LOG_PATH.exists():
        return "(sem log — o processo morreu antes de escrever qualquer coisa)"
    try:
        text = _LOG_PATH.read_text(encoding="utf-8", errors="replace")
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


def status() -> Optional[dict]:
    """Estado do processo supervisor, ou `None` se nenhum está rodando.

    Autocorrige: se o arquivo aponta para um PID que já morreu (processo
    caiu, servidor reiniciou sem o serviço) sem ter passado por `stop()`,
    marca como parado em vez de dizer que está rodando quando não está —
    mas preserva a `config`, para `last_config()` continuar funcionando."""
    state = _read_state()
    if state is None or state.get("pid") is None:
        return None
    if not _pid_alive(state["pid"]):
        _write_state({**state, "pid": None, "started_at": None})
        return None
    return state


def last_config() -> Optional[dict]:
    """Última configuração usada (rodando ou não) — para pré-preencher o
    formulário de retomada sem o usuário digitar tudo de novo."""
    state = _read_state()
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

    cli = _load_cli()
    args = argparse.Namespace(
        mode=config.mode, capital=config.capital, floor=config.floor,
        feed="yfinance", notify_min_level=config.notify_min_level,
        daily_loss_limit=config.daily_loss_limit, monthly_loss_limit=config.monthly_loss_limit,
        mt5_magic=20260817, mt5_shares_per_lot=config.mt5_shares_per_lot, mt5_symbol_map=None,
    )
    rt = cli.build(args)
    return rt.ensure_account()


def start(config: ProcessConfig) -> dict:
    """Cria a conta se preciso e sobe `scripts/run_live.py loop` como
    processo próprio, sobrevivendo ao dashboard fechar.

    Prova de vida (correção pós-code-review, crítico nº1): grava PID/estado
    só DEPOIS de esperar `_STARTUP_GRACE_SECONDS` e confirmar que o processo
    ainda está de pé (`proc.poll() is None`). Sem isso, um processo que
    morre na hora (terminal MT5 fechado, credencial errada, `--mode`
    recusado) fazia o dashboard gravar PID normalmente e continuar
    mostrando "robô ativo" para sempre — o botão "Iniciar" mentindo sobre um
    processo morto."""
    if status() is not None:
        raise RuntimeError("já existe um robô rodando — pare antes de iniciar outro.")
    if config.mode == "mt5" and (config.mt5_shares_per_lot is None or config.mt5_shares_per_lot <= 0):
        raise RuntimeError(
            "modo mt5 exige o campo 'ações por lote' (mt5_shares_per_lot) — "
            "não há valor universal, confira o symbol_info do seu terminal MT5."
        )

    create_account(config)

    argv = [
        sys.executable, str(_SCRIPT),
        "--mode", config.mode, "--capital", str(config.capital),
        "--notify-min-level", config.notify_min_level,
    ]
    if config.floor is not None:
        argv += ["--floor", str(config.floor)]
    if config.daily_loss_limit is not None:
        argv += ["--daily-loss-limit", str(config.daily_loss_limit)]
    if config.monthly_loss_limit is not None:
        argv += ["--monthly-loss-limit", str(config.monthly_loss_limit)]
    if config.mode == "mt5":
        argv += ["--mt5-shares-per-lot", str(config.mt5_shares_per_lot)]
    argv += ["loop", "--seconds", "60"]

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = open(_LOG_PATH, "a", encoding="utf-8")
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
            f"últimas linhas do log:\n{_tail_log()}"
        )

    state = {
        "pid": proc.pid,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": asdict(config),
    }
    _write_state(state)
    return state


def stop() -> bool:
    """Encerra o processo supervisor, se houver um rodando. Não mexe na
    conta nem no disjuntor — só derruba o loop; retomar depois com
    `start()` continua exatamente de onde a conta estava, do banco.

    Mantém a `config` no arquivo de estado (só zera `pid`/`started_at`) para
    o formulário de retomada continuar pré-preenchido com piso/disjuntor
    depois de parar — só `create_account`/CLI podem apagar de vez."""
    state = _read_state()
    if state is None or state.get("pid") is None:
        return False
    pid = state["pid"]
    if _pid_alive(pid):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=10)
    _write_state({**state, "pid": None, "started_at": None})
    return True
