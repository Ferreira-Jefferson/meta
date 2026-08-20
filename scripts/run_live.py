"""Linha de comando da operacao ao vivo.

    python scripts/run_live.py init --capital 50000 --mode mt5 \
        --strategy portfolio_dip2_hw40 --mt5-shares-per-lot 1
    python scripts/run_live.py status
    python scripts/run_live.py step                 # um passo do supervisor
    python scripts/run_live.py decide               # forca o fecho do pregao
    python scripts/run_live.py execute              # forca a execucao do dia
    python scripts/run_live.py reconcile            # aplica fills confirmados ao caixa/posicao
    python scripts/run_live.py unfreeze             # destrava o disjuntor de risco manualmente
    python scripts/run_live.py loop --seconds 60

`loop` so da passo dentro da janela de pregao B3 +/-1h (ver `live.clock.
in_active_window`) — fora dela (noite, fim de semana, feriado) fica
dormindo ate a janela abrir de novo, em vez de acordar a cada `--seconds`
so para constatar que nao ha nada a fazer.

Cotacao (--feed)
----------------
Operacao real (`--mode mt5`) recusa `--feed parquet` (dado de fechamento de
D-1, ou mais velho): stop e entrada intra-dia nao podem decidir sobre dado
desse jeito velho. Default `yfinance` (~15min de atraso conhecido, ver
`live/feed.py::YFinanceFeed`); `mt5` le o tick do MESMO terminal MT5 do
broker (ver aviso sobre o fuso do relogio do servidor em
`live/feed.py::MT5Feed`).

Modo de corretora
-----------------
  mt5     `MT5Broker` — fala com um terminal MetaTrader 5 JA ABERTO E LOGADO na
          MESMA maquina (pacote pip `MetaTrader5`, so funciona em Windows).
          O robo decide E executa sozinho, sem confirmacao humana em nenhum
          momento. ATENCAO: este adaptador nao foi validado contra um terminal
          MT5 real (sem ambiente disponivel para isso) — ver o aviso extenso
          no topo de `live/broker_mt5.py`. Teste primeiro com o MENOR lote
          possivel, em horario de pregao, observando o terminal ao vivo, antes
          de confiar nisto operando sem supervisao. `--mt5-shares-per-lot`/
          `--mt5-magic`/`--mt5-symbol-map` precisam ser conferidos contra o
          `symbol_info` do SEU terminal (a relacao acao/lote e o nome do
          simbolo variam por corretora — nao ha valor universal).

Alertas externos (opcionais, por variavel de ambiente — nunca em texto puro
na linha de comando, que fica visivel no historico do shell e na lista de
processos)
------------------------------------------------------------------------
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID   -> liga um canal Telegram
  SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_TO [/ SMTP_FROM] [/ SMTP_TLS=0]
                                           -> liga um canal de e-mail
Os dois podem estar configurados ao mesmo tempo (vira um por canal). Sem
nenhum configurado, o sistema so grava em `live_events` (visivel no
dashboard) e nao tenta sair pela rede. `--notify-min-level` controla o que
sai pelo canal externo (o diario sempre grava tudo, sem filtro).

Login MT5 (opcional, tambem por variavel de ambiente)
------------------------------------------------------
  MT5_LOGIN / MT5_PASSWORD / MT5_SERVER [/ MT5_TERMINAL_PATH]
Sem essas variaveis, `--mode mt5` so anexa a um terminal MT5 que um humano ja
abriu e logou na mesma maquina. Com elas, `MT5Broker.connect()` pede pro
proprio terminal fazer o login sozinho — necessario para operar sem depender
de alguem manter o terminal logado (ex.: o `loop` rodando como servico em
segundo plano, disparado pelo botao "Iniciar" do dashboard).

Disjuntor de risco (circuit breaker) — SEMPRE ligado, nao e escolha do usuario
-------------------------------------------------------------------------------
O disjuntor nao e parametro de estrategia (nao foi otimizado por backtest) nem
capital: e trava operacional de risco, parte do proprio robo. Por isso roda
SEMPRE, com os defaults de `live/riskguard.py::CircuitBreaker` (5% dia / 15%
mes) quando nada e passado — nunca desligado por omissao, e o dashboard nunca
expoe `--daily-loss-limit`/`--monthly-loss-limit` como campo editavel (decisao
do dono, 2026-08-19: nao cabe a quem opera mudar um numero que o robo ja sabe
qual e o certo pra ele).
  --daily-loss-limit 0.05    -> congela ENTRADA nova se o patrimonio cair
                                 mais que 5% no dia. Reseta sozinho no dia
                                 seguinte (um dia ruim isolado nao deve capar
                                 o robo para sempre).
  --monthly-loss-limit 0.15  -> mesma ideia, base mensal. NAO reseta sozinho
                                 — precisa de 'unfreeze' explicito depois de
                                 um humano revisar. Perda mensal grande e
                                 tratada como sintoma de algo estruturalmente
                                 errado, nao como mau dia de mercado.
Estas duas flags de linha de comando continuam existindo só para uso
manual/teste fora do dashboard (override explícito de quem roda o CLI direto).
Em NENHUM caso o disjuntor forca uma venda, mexe em stop ou trava saque —
so veta ABRIR posicao nova (ver `live/riskguard.py`).

O PISO DO SAQUE ACOMPANHA O APORTE. A politica oficial usa piso = 55x o capital
inicial (ver `backtest/withdrawal.py`). Com `--capital 50000` o piso vira
R$ 2.750.000 — o saque so comeca quando a carteira chegar la. Se a intencao e
outra (sacar desde ja, ou piso em valor absoluto), passe `--floor`.

Robo de investimento (--strategy) — sem default, escolha explicita sempre
---------------------------------------------------------------------------
Nao ha robo hardcoded: `--strategy` recebe a CHAVE de um robo do registry
(`strategy.registry.list_strategies()` / pagina `/estrategias`) e o
runtime resolve via `strategy.registry.get_strategy(chave).factory()`. O
dashboard resolve isso sozinho (top-3 da janela FULL na criacao da conta,
`live_accounts.investment_robot` da conta ja existente ao retomar — nunca
troca de robo sozinho numa conta ja em operacao). Quem usa este CLI direto
numa conta JA EXISTENTE precisa passar a MESMA chave usada na criacao —
`status` mostra o `investment_robot` gravado; uma chave diferente aqui e a
conta ja existente diverge silenciosamente (ver `LiveRuntime.
_restore_robot_state`, que descarta o estado do robo antigo sem avisar).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backtest.withdrawal import FloorSkim, official_policy
from core.config import WATCHLIST, BacktestConfig
from live.feed import MT5Feed, YFinanceFeed
from live.notify import (
    CompositeNotifier,
    EmailNotifier,
    MinLevelNotifier,
    NullNotifier,
    TelegramNotifier,
)
from live.riskguard import CircuitBreaker
from live.runtime import LiveRuntime
from strategy.registry import get_strategy

ACCOUNT = "principal"


def _build_notifier(min_level: str) -> object:
    """Le credenciais de VARIAVEL DE AMBIENTE (nunca de argv — argv fica
    visivel em `ps`/historico do shell). Compoe quantos canais estiverem
    configurados; nenhum configurado cai em `NullNotifier` (so diario,
    sem tentar rede)."""
    canais = []
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        canais.append(TelegramNotifier(token, chat))
    host, user, pw, to = (os.environ.get(k) for k in
                          ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_TO"))
    if host and user and pw and to:
        port = int(os.environ.get("SMTP_PORT", "587"))
        use_tls = os.environ.get("SMTP_TLS", "1") != "0"
        canais.append(EmailNotifier(host, port, user, pw, to,
                                    from_addr=os.environ.get("SMTP_FROM"), use_tls=use_tls))
    if not canais:
        return NullNotifier()
    return MinLevelNotifier(CompositeNotifier(canais), min_level=min_level)


def _mt5_credentials() -> dict:
    """Le login/senha/servidor do terminal MT5 de VARIAVEL DE AMBIENTE — mesmo
    motivo do `_build_notifier` acima: nunca em argv, que fica visivel em
    `ps`/historico do shell. Sem elas, `MT5Broker.connect()` so anexa a um
    terminal ja aberto e logado por um humano (ver docstring de `connect()`
    em `live/broker_mt5.py`)."""
    login = os.environ.get("MT5_LOGIN")
    return dict(
        login=int(login) if login else None,
        password=os.environ.get("MT5_PASSWORD"),
        server=os.environ.get("MT5_SERVER"),
        path=os.environ.get("MT5_TERMINAL_PATH"),
    )


def _build_risk_guard(daily_limit: float | None, monthly_limit: float | None) -> CircuitBreaker:
    """SEMPRE devolve um disjuntor ativo — nao e opt-in (ver docstring do
    modulo, secao "Disjuntor de risco"). `None` em qualquer um dos dois cai
    no default da propria classe (5% dia / 15% mes), nunca em "sem trava"."""
    kwargs = {}
    if daily_limit is not None:
        kwargs["daily_loss_pct"] = daily_limit
    if monthly_limit is not None:
        kwargs["monthly_loss_pct"] = monthly_limit
    return CircuitBreaker(**kwargs)


def build(args) -> LiveRuntime:
    # Sem robo default (regra do dono, 2026-08-19): quem cria a conta escolhe
    # a chave explicitamente -- nao ha estrategia hardcoded que sirva de
    # fallback silencioso, ver docstring do modulo, secao "Robo de
    # investimento".
    if not args.strategy:
        raise ValueError(
            "--strategy é obrigatório — não há robô padrão. Veja as chaves "
            "disponíveis em strategy.registry.list_strategies() (ex.: "
            "'portfolio_dip2_hw40') ou na página /estrategias do dashboard."
        )
    try:
        strategy_obj = get_strategy(args.strategy).factory()
    except KeyError as e:
        raise ValueError(str(e)) from e

    if args.mode == "mt5":
        if args.mt5_shares_per_lot is None or args.mt5_shares_per_lot <= 0:
            raise ValueError(
                "--mt5-shares-per-lot é obrigatório no modo mt5 — confira o "
                "symbol_info do SEU terminal MT5 antes de operar (não há "
                "valor universal, ver docstring de live/broker_mt5.py)."
            )
        from live.broker_mt5 import MT5Broker  # import tardio: so quando de fato usado
        symbol_map = json.loads(args.mt5_symbol_map) if args.mt5_symbol_map else None
        broker = MT5Broker(magic=args.mt5_magic, shares_per_lot=args.mt5_shares_per_lot,
                           symbol_map=symbol_map, **_mt5_credentials())
    else:
        raise ValueError(
            f"--mode inválido ou ausente: {args.mode!r} — use 'mt5' "
            "(ver core.live_models.BrokerMode)."
        )
    # Operacao REAL (dinheiro de verdade) nunca pode ver so o fecho de ontem
    # o dia inteiro -- `--feed parquet` e recusado aqui, nunca um fallback
    # silencioso (FEAT-004, item 4.1).
    if args.feed == "parquet":
        raise ValueError(
            f"--feed parquet não é aceito em operação real (--mode {args.mode!r}): "
            "dado de fechamento de D-1 (ou mais velho) nunca deveria decidir stop "
            "nem entrada intra-dia com dinheiro de verdade. Use --feed yfinance "
            "(~15min de atraso, default) ou --feed mt5 (mesmo terminal do broker, "
            "sem atraso conhecido — ver docstring de live/feed.py::MT5Feed)."
        )
    if args.feed == "mt5":
        symbol_map = json.loads(args.mt5_symbol_map) if args.mt5_symbol_map else None
        feed = MT5Feed(symbol_map=symbol_map, **_mt5_credentials())
    else:
        feed = YFinanceFeed()
    policy = (FloorSkim(floor=args.floor) if args.floor is not None
              else official_policy(initial_capital=args.capital))
    return LiveRuntime(
        account_name=ACCOUNT,
        strategy=strategy_obj,
        policy=policy,
        feed=feed,
        broker=broker,
        config=BacktestConfig(initial_capital=args.capital, lot_size=1),
        tickers=_universe_of(strategy_obj),
        notifier=_build_notifier(args.notify_min_level),
        risk_guard=_build_risk_guard(args.daily_loss_limit, args.monthly_loss_limit),
    )


def _universe_of(strategy_obj) -> tuple[str, ...]:
    """De quais tickers este robo precisa de cotacao.

    `WATCHLIST` deixou de servir como universo unico em 2026-08-20, quando o
    campeao passou a ser `liquid_champion`: ele escolhe o universo por liquidez
    na data, dentro de um pool de 63 papeis, e nenhum dos sete da WATCHLIST e
    garantido. Alimentar esse robo so com a WATCHLIST nao daria erro nenhum —
    ele simplesmente decidiria com 7 dos 63 candidatos e operaria uma
    estrategia que nunca foi testada, em silencio. Por isso o universo vem do
    proprio robo (`Strategy.universe_tickers`) e a WATCHLIST fica so como
    fallback para os robos antigos que nao declaram nada.
    """
    return tuple(getattr(strategy_obj, "universe_tickers", None) or WATCHLIST)


def cmd_init(args) -> None:
    rt = build(args)
    acc = rt.ensure_account()
    print(f"conta '{acc.name}' pronta — modo {acc.mode}, capital R$ {acc.initial_capital:,.2f}"
          .replace(",", "."))
    print(f"  robo de investimento: {acc.investment_robot}")
    print(f"  robo de saque:        {acc.withdrawal_robot}")
    if args.floor is None:
        print(f"  piso do saque:        R$ {55 * args.capital:,.2f} (55x o aporte)"
              .replace(",", "."))
    if rt.risk_guard is not None:
        print(f"  disjuntor:            diario {rt.risk_guard.daily_loss_pct:.1%} / "
              f"mensal {rt.risk_guard.monthly_loss_pct:.1%}")
    if isinstance(rt.notifier, NullNotifier):
        print("  alerta externo:       nenhum configurado (so diario/dashboard)")
    else:
        print("  alerta externo:       ativo (Telegram e/ou e-mail conforme variaveis de ambiente)")


def cmd_status(args) -> None:
    rt = build(args)
    print(json.dumps(rt.status(), indent=2, ensure_ascii=False, default=str))


def cmd_step(args) -> None:
    rt = build(args)
    for passo in rt.run_once():
        print(passo)


def cmd_decide(args) -> None:
    rt = build(args)
    from live import clock
    print(rt.close_and_decide(clock.session_date()))


def cmd_execute(args) -> None:
    rt = build(args)
    from live import clock
    from core.live_models import SessionPhase

    fase = clock.phase()
    if fase != SessionPhase.OPEN:
        print(f"'execute' recusado fora da fase OPEN (fase atual: {fase.value}) — "
              "rodar fora do pregao executaria as intencoes de D+1 contra as "
              "cotacoes de D (a sessao errada); espere o pregao abrir ou use "
              "'decide'/'step' conforme a fase.")
        sys.exit(1)
    print(rt.execute_session(clock.next_session(clock.session_date())))


def cmd_reconcile(args) -> None:
    rt = build(args)
    print(rt.reconcile_pending_fills())


def cmd_unfreeze(args) -> None:
    rt = build(args)
    if rt.risk_guard is None:
        print("nenhum disjuntor configurado nesta chamada (--daily-loss-limit/--monthly-loss-limit "
              "ausentes) — nada a destravar.")
        return
    rt.unfreeze()
    print("disjuntor destravado.")


def cmd_loop(args) -> None:
    from live import clock

    rt = build(args)
    print(f"supervisor ativo — passo a cada {args.seconds}s, so na janela de "
          f"pregao B3 +/-1h (fora dela, dorme ate a janela abrir de novo; "
          f"sem passo nenhum a noite ou no fim de semana). Ctrl+C para parar.")
    while True:
        try:
            espera = clock.seconds_until_active_window()
            if espera > 0:
                print(f"[fora do horario de pregao] proximo passo em {espera / 3600:.1f}h", flush=True)
                time.sleep(espera)
                continue
            for passo in rt.run_once():
                print(passo, flush=True)
        except KeyboardInterrupt:
            print("\nencerrado")
            return
        except ValueError as e:
            # Correcao pos-code-review (item 6, hipotese-agente): ValueError
            # aqui e a guarda de conta/broker divergente (`LiveRuntime.
            # _load_account`) ou de modo invalido -- um bug ESTRUTURAL que
            # nao se resolve sozinho no proximo passo. Deixar isso cair no
            # `except Exception` generico abaixo faria o loop dormir e
            # tentar de novo para sempre, com o processo vivo e o painel
            # mostrando "ativo" enquanto nada e decidido. Encerra o processo
            # (exit != 0) em vez de retry silencioso infinito -- so um
            # humano pode corrigir conta x broker divergentes.
            print(f"[erro fatal] {type(e).__name__}: {e}", flush=True)
            rt.notifier.notify("error", "loop", f"FATAL: {type(e).__name__}: {e}")
            sys.exit(1)
        except Exception as e:  # noqa: BLE001
            # Um erro num passo nao pode matar o supervisor: amanha ha outro
            # pregao. O evento fica no diario para diagnostico. Notifica
            # tambem, se configurado — um erro silencioso num servidor sem
            # ninguem olhando e o pior cenario que isto tenta evitar.
            print(f"[erro] {type(e).__name__}: {e}", flush=True)
            rt.notifier.notify("error", "loop", f"{type(e).__name__}: {e}")
        time.sleep(args.seconds)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", default="mt5", choices=("mt5",))
    p.add_argument("--capital", type=float, default=1_000.0)
    p.add_argument("--strategy", default=None,
                   help="chave do robo (strategy.registry.list_strategies()) -- "
                        "obrigatorio, sem default (ver docstring, secao "
                        "'Robo de investimento')")
    p.add_argument("--floor", type=float, default=None,
                   help="piso do saque em R$ absoluto (default: 55x o capital)")
    p.add_argument("--feed", default="yfinance", choices=("parquet", "yfinance", "mt5"))
    p.add_argument("--notify-min-level", default="warn", choices=("debug", "info", "warn", "error"),
                   help="nivel minimo que sai pelo canal externo (Telegram/e-mail); "
                        "o diario sempre grava tudo, sem filtro")
    p.add_argument("--daily-loss-limit", type=float, default=None,
                   help="ex.: 0.05 = congela entrada nova se o patrimonio cair 5%% no dia")
    p.add_argument("--monthly-loss-limit", type=float, default=None,
                   help="ex.: 0.15 = mesma ideia, base mensal — precisa de 'unfreeze' manual")
    p.add_argument("--mt5-magic", type=int, default=20260817)
    p.add_argument("--mt5-shares-per-lot", type=float, default=None,
                   help="obrigatorio no modo mt5 — confira em symbol_info do SEU "
                        "terminal MT5 antes de operar, nao ha valor universal")
    p.add_argument("--mt5-symbol-map", default=None,
                   help='JSON, ex.: \'{"WEGE3.SA": "WEGE3F"}\'')
    sub = p.add_subparsers(dest="cmd", required=True)

    for nome, fn in (("init", cmd_init), ("status", cmd_status), ("step", cmd_step),
                     ("decide", cmd_decide), ("execute", cmd_execute),
                     ("reconcile", cmd_reconcile), ("unfreeze", cmd_unfreeze)):
        sub.add_parser(nome).set_defaults(func=fn)

    lp = sub.add_parser("loop")
    lp.add_argument("--seconds", type=int, default=60)
    lp.set_defaults(func=cmd_loop)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
