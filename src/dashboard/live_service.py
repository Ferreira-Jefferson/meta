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
from live.broker import ManualBroker, PaperBroker
from live.feed import ParquetCloseFeed
from live.runtime import LiveRuntime
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

ACCOUNT_NAME = "principal"
DEFAULT_CAPITAL = 1_000.0


def _account_mode() -> str | None:
    """Leitura rápida só do modo — para montar o runtime de status com o
    broker CERTO (ver `_build_runtime`). Sem isso, o painel sempre relataria
    'paper' mesmo para uma conta real em MT5."""
    with store.live_journal() as conn:
        acc = store.load_account(conn, ACCOUNT_NAME)
    return acc.mode if acc else None


def _build_runtime(mode: str = "paper") -> LiveRuntime:
    """A página é um painel de LEITURA — `status()` nunca envia ordem
    nenhuma, então o broker aqui não precisa (nem deve) estar conectado a
    nada de verdade. Mas o TIPO do broker precisa bater com o modo real da
    conta (`account.mode`), senão o badge "corretora" mentiria para uma
    conta mt5/manual dizendo "paper"."""
    from backtest.withdrawal import official_policy
    from core.config import BacktestConfig, WATCHLIST

    feed = ParquetCloseFeed()
    if mode == "manual":
        broker = ManualBroker()
    elif mode == "mt5":
        from live.broker_mt5 import MT5Broker  # import tardio: nao conecta ao construir
        broker = MT5Broker()
    else:
        broker = PaperBroker(feed)
    return LiveRuntime(
        account_name=ACCOUNT_NAME,
        strategy=DipTop1Portfolio(),
        policy=official_policy(DEFAULT_CAPITAL),
        feed=feed,
        broker=broker,
        config=BacktestConfig(initial_capital=DEFAULT_CAPITAL, lot_size=1),
        tickers=WATCHLIST,
    )


def get_status() -> dict:
    """Status da conta de operação, ou `{"existe": False}` se ainda não criada."""
    mode = _account_mode() or "paper"
    return _build_runtime(mode).status()
