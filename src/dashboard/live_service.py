"""Composição para a página `/operacao`: monta o runtime de LEITURA e traduz
`LiveRuntime.status()` para o template.

Fica em `dashboard/` (camada de orquestração, ver AGENTS.md) porque precisa
importar `live/`, `backtest/withdrawal.py` e `strategy/` ao mesmo tempo —
exatamente o que uma feature isolada não pode fazer.

`get_status()` NUNCA cria a conta por conta própria (decisão financeira não
é side-effect de GET) — mas a partir de 2026-08-17 o dashboard ganhou um
botão "Iniciar operação" (ver `live_control.py`) que cria a conta como
efeito EXPLÍCITO de um clique, no lugar de pedir para o usuário abrir um
terminal e rodar `scripts/run_live.py init`.
"""
from __future__ import annotations

from journal import live_store as store
from live.feed import ParquetCloseFeed
from live.runtime import LiveRuntime
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

ACCOUNT_NAME = "principal"
DEFAULT_CAPITAL = 1_000.0


def _build_runtime(mode: str, capital: float) -> LiveRuntime:
    """A página é um painel de LEITURA — `status()` nunca envia ordem
    nenhuma, então o broker aqui não precisa (nem deve) estar conectado a
    nada de verdade. Mas o TIPO do broker precisa bater com o modo REAL da
    conta (`account.mode`) e `capital` precisa ser o `initial_capital` REAL
    dela — nunca `DEFAULT_CAPITAL` (que é só o default do FORMULÁRIO de
    conta nova em `app.py`, uso legítimo e diferente disto): usar o default
    aqui vazava capital/piso de simulação para uma conta real (crítico 1.7).
    Dispatch explícito, sem default de `mode` — o `else: PaperBroker` de
    antes era metade do bug (fallback silencioso para simulação)."""
    from backtest.withdrawal import official_policy
    from core.config import BacktestConfig, WATCHLIST

    feed = ParquetCloseFeed()
    if mode == "mt5":
        from live.broker_mt5 import MT5Broker  # import tardio: nao conecta ao construir
        broker = MT5Broker()
    else:
        raise ValueError(f"modo de corretora desconhecido: {mode!r}")
    return LiveRuntime(
        account_name=ACCOUNT_NAME,
        strategy=DipTop1Portfolio(),
        policy=official_policy(capital),
        feed=feed,
        broker=broker,
        config=BacktestConfig(initial_capital=capital, lot_size=1),
        tickers=WATCHLIST,
        risk_guard=_resolve_risk_guard(),
    )


def _resolve_risk_guard():
    """Reconstrói o `CircuitBreaker` da última config salva do processo
    supervisor (`live_control.last_config()`), reusando
    `run_live.py::_build_risk_guard` (via `live_control._load_cli()`,
    memoizado — ver docstring de `_load_cli`) em vez de duplicar a lógica de
    qual limite vira qual disjuntor. Sem isso, `status()` sempre reportava
    `disjuntor: None` mesmo com um disjuntor configurado e rodando de
    verdade (crítico 1.7)."""
    from dashboard import live_control

    config = live_control.last_config()
    if not config:
        return None
    cli = live_control._load_cli()
    return cli._build_risk_guard(
        config.get("daily_loss_limit"), config.get("monthly_loss_limit")
    )


def get_status() -> dict:
    """Status da conta de operação, ou `{"conta": ACCOUNT_NAME, "existe":
    False}` se ainda não criada — mesma forma que `LiveRuntime.status()` já
    devolve nesse caso (o template lê `s.existe`, mas manter a chave `conta`
    evita os dois caminhos divergirem de contrato)."""
    with store.live_journal() as conn:
        account = store.load_account(conn, ACCOUNT_NAME)
    if account is None:
        return {"conta": ACCOUNT_NAME, "existe": False}
    return _build_runtime(account.mode, account.initial_capital).status()
