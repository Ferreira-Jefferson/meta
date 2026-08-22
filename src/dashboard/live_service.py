"""Composição para a página `/operacao`: monta o runtime de LEITURA de cada
SLOT e traduz `status()` para o template.

Fica em `dashboard/` (camada de orquestração, ver AGENTS.md) porque precisa
importar `live/`, `backtest/withdrawal.py` e `strategy/` ao mesmo tempo —
exatamente o que uma feature isolada não pode fazer.

`get_status()` NUNCA cria a conta por conta própria (decisão financeira não
é side-effect de GET) — mas a partir de 2026-08-17 o dashboard ganhou um
botão "Iniciar operação" (ver `live_control.py`) que cria a conta como
efeito EXPLÍCITO de um clique, no lugar de pedir para o usuário abrir um
terminal e rodar `scripts/run_live.py init`.

DOIS SLOTS (2026-08-21)
-----------------------
O painel deixou de ter uma conta só ("principal") e passou a ter uma por
slot (`core.config.SLOTS`), cada uma com o seu caixa. O despacho é por
`slot.kind` e acontece ANTES de tocar no registry de swing: `get_strategy
("gremah")` levantaria `KeyError` (o scan de `strategy.discovery` exige
`issubclass(obj, Strategy)` e nem varre o pacote `daytrade`), e isso viraria
um 500 em `/operacao` só por existir um cartão de day trade na tela.
"""
from __future__ import annotations

from core.config import Slot, ordered_slots, slot_by_id
from journal import live_store as store
from live.feed import ParquetCloseFeed
from live.runtime import LiveRuntime
from strategy.registry import get_strategy

# Slot cujo caixa/robô o painel mostra quando nenhum é pedido. Substituiu a
# constante `ACCOUNT_NAME = "principal"`: o nome da conta passou a ser o id do
# slot (ver `core.config.SLOTS`).
DEFAULT_SLOT = ordered_slots()[0].id


def _build_daily_runtime(slot: Slot, mode: str, capital: float, robot: str | None) -> LiveRuntime:
    """A página é um painel de LEITURA — `status()` nunca envia ordem
    nenhuma, então o broker aqui não precisa (nem deve) estar conectado a
    nada de verdade. Mas o TIPO do broker precisa bater com o modo REAL da
    conta (`account.mode`) e `capital` precisa ser o `initial_capital` REAL
    dela, lido do banco — nunca um valor inventado aqui: usar um default
    vazaria capital/piso de simulação para uma conta real (crítico 1.7).
    Dispatch explícito, sem default de `mode` — o `else: PaperBroker` de
    antes era metade do bug (fallback silencioso para simulação)."""
    from backtest.withdrawal import official_policy
    from core.config import BacktestConfig, WATCHLIST

    # O robo vem da CONTA (`live_accounts.investment_robot`), nao de um import
    # fixo. Ate 2026-08-20 este arquivo instanciava `DipTop1Portfolio()` direto:
    # com um so robo operavel isso passava despercebido, mas o campeao virou
    # `liquid_champion` e o painel passaria a mostrar as posicoes-alvo de OUTRO
    # robo, com outro universo, como se fossem as da conta. Um painel de leitura
    # que mente e pior que um painel que falta.
    strategy_obj = get_strategy(robot).factory() if robot else None
    if strategy_obj is None:
        raise ValueError(
            "conta sem `investment_robot` gravado — nao da para montar o painel "
            "sem saber qual robo ela opera"
        )

    feed = ParquetCloseFeed()
    if mode == "mt5":
        from live.broker_mt5 import MT5Broker  # import tardio: nao conecta ao construir
        broker = MT5Broker(magic=slot.magic)
    else:
        raise ValueError(f"modo de corretora desconhecido: {mode!r}")
    return LiveRuntime(
        account_name=slot.id,
        strategy=strategy_obj,
        policy=official_policy(capital),
        feed=feed,
        broker=broker,
        config=BacktestConfig(initial_capital=capital, lot_size=1),
        tickers=tuple(getattr(strategy_obj, "universe_tickers", None) or WATCHLIST),
        risk_guard=_resolve_risk_guard(slot.id),
    )


def _build_intraday_runtime(slot: Slot, capital: float, execution_mode: str, robot: str | None):
    """Runtime de LEITURA do slot de day trade.

    O robô vem da CONTA (`live_accounts.investment_robot`), não de um import
    fixo — mesmo motivo de `_build_daily_runtime`: um painel que sempre
    mostra `Gremah` mentiria se a conta tivesse escolhido outro robô
    registrado. O símbolo, por sua vez, vem do ROBÔ (`robo.symbol`), não do
    slot — `core.config.Slot` não declara símbolo desde 2026-08-21.

    Não conecta em nada: o `MT5BarFeed` nunca é lido por `status()` — o painel
    só reporta o fuso em uso, não busca barra. Também não passa `clock_feed`:
    conferir o relógio do servidor exige ler tick, e uma página de status não
    pode disparar I/O na corretora. Custo do perfil vem de `PROFILES` com tick
    0.01 nominal, porque `status()` não calcula P&L de trade nenhum; quem
    calcula é o processo do robô, que lê o tick real do terminal (ver
    `scripts/run_live.py::build_intraday`)."""
    from backtest.intraday.profiles import PROFILES, config_for
    from live.bar_feed import MT5BarFeed
    from live.broker_mt5 import MT5Broker  # import tardio: nao conecta ao construir
    from live.intraday_runtime import IntradayLiveRuntime
    from strategy.daytrade.registry import get_daytrade_robot

    if not robot:
        raise ValueError(
            "conta sem `investment_robot` gravado — nao da para montar o painel "
            "sem saber qual robo ela opera"
        )
    robo = get_daytrade_robot(robot)
    profile = PROFILES[robo.symbol]
    return IntradayLiveRuntime(
        slot=slot,
        strategy=robo,
        config=config_for(profile, trade_tick_value=0.01, trade_tick_size=0.01,
                          target_fills_as_maker=robo.target_fills_as_maker),
        bar_feed=MT5BarFeed(robo.symbol),
        broker=MT5Broker(magic=slot.magic),
        execution_mode=execution_mode,
        initial_capital=capital,
    )


def _resolve_risk_guard(slot_id: str):
    """Reconstrói o `CircuitBreaker` da última config salva do processo
    supervisor DESTE slot (`live_control.last_config(slot)`), reusando
    `run_live.py::_build_risk_guard` (via `live_control._load_cli()`,
    memoizado — ver docstring de `_load_cli`) em vez de duplicar a lógica de
    qual limite vira qual disjuntor. Sem isso, `status()` sempre reportava
    `disjuntor: None` mesmo com um disjuntor configurado e rodando de
    verdade (crítico 1.7)."""
    from dashboard import live_control

    config = live_control.last_config(slot_id)
    if not config:
        return None
    cli = live_control._load_cli()
    return cli._build_risk_guard(
        config.get("daily_loss_limit"), config.get("monthly_loss_limit")
    )


def get_status(slot_id: str = DEFAULT_SLOT) -> dict:
    """Status da conta deste slot, ou `{"conta": <slot>, "existe": False}` se
    ainda não criada — mesma forma que `LiveRuntime.status()` já devolve
    nesse caso (o template lê `s.existe`, mas manter a chave `conta` evita os
    dois caminhos divergirem de contrato)."""
    from dashboard import live_control

    slot = slot_by_id(slot_id)
    with store.live_journal() as conn:
        account = store.load_account(conn, slot.id)
    # Conta sem `investment_robot` é uma linha só CONTÁBIL: `POST
    # /operacao/{slot}/caixa` a cria para guardar o caixa digitado antes de
    # qualquer robô ser escolhido (ver `app.py::operacao_caixa`). Para o
    # painel isso é "ainda não em operação" — montar um runtime de leitura sem
    # saber qual robô a conta opera daria um painel que mente.
    if account is None or not account.investment_robot:
        return {"conta": slot.id, "existe": False, "kind": slot.kind}
    if slot.is_intraday:
        cfg = live_control.last_config(slot.id) or {}
        return _build_intraday_runtime(
            slot, account.initial_capital, cfg.get("execution_mode") or "shadow",
            account.investment_robot,
        ).status()
    return _build_daily_runtime(
        slot, account.mode, account.initial_capital, account.investment_robot
    ).status()
