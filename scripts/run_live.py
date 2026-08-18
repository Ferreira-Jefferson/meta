"""Linha de comando da operacao ao vivo.

    python scripts/run_live.py init --capital 50000 --mode manual
    python scripts/run_live.py status
    python scripts/run_live.py step                 # um passo do supervisor
    python scripts/run_live.py decide               # forca o fecho do pregao
    python scripts/run_live.py execute              # forca a execucao do dia
    python scripts/run_live.py tickets              # ordens a executar na mao
    python scripts/run_live.py confirm 12 300 41.85 # confirma fill manual
    python scripts/run_live.py reconcile            # aplica fills confirmados ao caixa/posicao
    python scripts/run_live.py unfreeze             # destrava o disjuntor de risco manualmente
    python scripts/run_live.py sacar 5000.00        # confirma recomendacao de saque pendente
    python scripts/run_live.py sacar 5000.00 --intent-id 42 --data 2026-08-18
    python scripts/run_live.py loop --seconds 60

`loop` so da passo dentro da janela de pregao B3 +/-1h (ver `live.clock.
in_active_window`) — fora dela (noite, fim de semana, feriado) fica
dormindo ate a janela abrir de novo, em vez de acordar a cada `--seconds`
so para constatar que nao ha nada a fazer.

Modos de corretora
------------------
  manual  `ManualBroker` — nao envia nada. Emite ticket legivel, voce executa na
          corretora e confirma com `confirm`. E o modo para comecar a operar de
          verdade sem depender de integracao.
  mt5     `MT5Broker` — fala com um terminal MetaTrader 5 JA ABERTO E LOGADO na
          MESMA maquina (pacote pip `MetaTrader5`, so funciona em Windows).
          ATENCAO: este adaptador nao foi validado contra um terminal MT5 real
          (sem ambiente disponivel para isso) — ver o aviso extenso no topo de
          `live/broker_mt5.py`. Teste primeiro com o MENOR lote possivel, em
          horario de pregao, observando o terminal ao vivo, antes de confiar
          nisto operando sem supervisao. `--mt5-shares-per-lot`/`--mt5-magic`/
          `--mt5-symbol-map` precisam ser conferidos contra o `symbol_info` do
          SEU terminal (a relacao acao/lote e o nome do simbolo variam por
          corretora — nao ha valor universal).

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

Disjuntor de risco (circuit breaker) — opcional, opt-in
--------------------------------------------------------
  --daily-loss-limit 0.05    -> congela ENTRADA nova se o patrimonio cair
                                 mais que 5% no dia. Reseta sozinho no dia
                                 seguinte (um dia ruim isolado nao deve capar
                                 o robo para sempre).
  --monthly-loss-limit 0.15  -> mesma ideia, base mensal. NAO reseta sozinho
                                 — precisa de 'unfreeze' explicito depois de
                                 um humano revisar. Perda mensal grande e
                                 tratada como sintoma de algo estruturalmente
                                 errado, nao como mau dia de mercado.
Passar qualquer um dos dois liga o disjuntor (o outro cai no default da
classe). Sem nenhum, o robo nunca veta entrada por conta propria.
Em NENHUM caso o disjuntor forca uma venda, mexe em stop ou trava saque —
so veta ABRIR posicao nova (ver `live/riskguard.py`).

O PISO DO SAQUE ACOMPANHA O APORTE. A politica oficial usa piso = 55x o capital
inicial (ver `backtest/withdrawal.py`). Com `--capital 50000` o piso vira
R$ 2.750.000 — o saque so comeca quando a carteira chegar la. Se a intencao e
outra (sacar desde ja, ou piso em valor absoluto), passe `--floor`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backtest.withdrawal import FloorSkim, official_policy
from core.config import WATCHLIST, BacktestConfig
from journal import live_store as store
from live.broker import ManualBroker
from live.feed import ParquetCloseFeed, YFinanceFeed
from live.notify import (
    CompositeNotifier,
    EmailNotifier,
    MinLevelNotifier,
    NullNotifier,
    TelegramNotifier,
)
from live.riskguard import CircuitBreaker
from live.runtime import LiveRuntime
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

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


def _build_risk_guard(daily_limit: float | None, monthly_limit: float | None) -> CircuitBreaker | None:
    if daily_limit is None and monthly_limit is None:
        return None
    kwargs = {}
    if daily_limit is not None:
        kwargs["daily_loss_pct"] = daily_limit
    if monthly_limit is not None:
        kwargs["monthly_loss_pct"] = monthly_limit
    return CircuitBreaker(**kwargs)


def build(args) -> LiveRuntime:
    feed = YFinanceFeed() if args.feed == "yfinance" else ParquetCloseFeed()
    if args.mode == "manual":
        broker = ManualBroker()
    elif args.mode == "mt5":
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
            f"--mode inválido ou ausente: {args.mode!r} — use 'manual' ou 'mt5' "
            "(ver core.live_models.BrokerMode)."
        )
    policy = (FloorSkim(floor=args.floor) if args.floor is not None
              else official_policy(initial_capital=args.capital))
    return LiveRuntime(
        account_name=ACCOUNT,
        strategy=DipTop1Portfolio(),
        policy=policy,
        feed=feed,
        broker=broker,
        config=BacktestConfig(initial_capital=args.capital, lot_size=1),
        tickers=WATCHLIST,
        notifier=_build_notifier(args.notify_min_level),
        risk_guard=_build_risk_guard(args.daily_loss_limit, args.monthly_loss_limit),
    )


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
    print(rt.execute_session(clock.next_session(clock.session_date())))


def cmd_reconcile(args) -> None:
    rt = build(args)
    print(rt.reconcile_pending_fills())


def cmd_sacar(args) -> None:
    """Confirma uma recomendacao de saque pendente -- o UNICO caminho que
    move dinheiro de verdade desde que o saque virou recomendacao (ver
    docstring de `live/runtime.py`). `--intent-id` existe pelo mesmo motivo
    do `confirm <order_id>` acima: um `sacar` repetido (cron, dedo no Enter)
    nao pode confirmar "o que estiver pendente" as cegas -- com mais de uma
    recomendacao pendente ao mesmo tempo (nao deveria acontecer, mas
    `LiveRuntime._expire_withdraw_advice` grita se acontecer), `confirm_
    withdrawal` recusa em vez de adivinhar a mais antiga."""
    rt = build(args)
    session = date.fromisoformat(args.data) if args.data else None
    report = rt.confirm_withdrawal(args.valor, session=session, intent_id=args.intent_id)
    print(report)
    if report.action != "withdraw_confirm":
        sys.exit(1)


def cmd_unfreeze(args) -> None:
    rt = build(args)
    if rt.risk_guard is None:
        print("nenhum disjuntor configurado nesta chamada (--daily-loss-limit/--monthly-loss-limit "
              "ausentes) — nada a destravar.")
        return
    rt.unfreeze()
    print("disjuntor destravado.")


def _require_manual_account(args) -> None:
    """Recusa (`SystemExit`) se a conta '{ACCOUNT}' não existir ou se o modo
    REAL dela não for `manual` — antes disso, `cmd_tickets`/`cmd_confirm`
    faziam `args.mode = "manual"` incondicionalmente, então uma conta em
    modo `mt5` (dinheiro real via corretora automática) rodava `tickets`/
    `confirm` como se fosse manual, sem nenhum aviso. Só depois de validar
    isso é que `args.mode` é fixado em `"manual"`, para `build()` funcionar."""
    with store.live_journal() as conn:
        acc = store.load_account(conn, ACCOUNT)
    if acc is None:
        raise SystemExit(f"conta '{ACCOUNT}' não existe — rode 'init' primeiro.")
    if acc.mode != "manual":
        raise SystemExit(
            f"conta '{ACCOUNT}' está em modo {acc.mode!r}, não 'manual' — "
            "'tickets'/'confirm' só fazem sentido para corretora manual "
            "(uma corretora automática, como mt5, preenche sozinha)."
        )
    args.mode = "manual"


def cmd_tickets(args) -> None:
    _require_manual_account(args)
    rt = build(args)
    with store.live_journal() as conn:
        acc = store.load_account(conn, ACCOUNT)
        if acc is None:
            print("conta inexistente — rode 'init' primeiro")
            return
        abertas = store.open_orders(conn, acc.id)
    if not abertas:
        print("nenhuma ordem pendente")
        return
    print(f"{len(abertas)} ordem(ns) a executar:\n")
    for o in abertas:
        print(f"  #{o.id}  {o.note or ''}")
        print(f"        confirmar: python scripts/run_live.py confirm {o.id} "
              f"<qtd> <preco_medio>")


def cmd_confirm(args) -> None:
    _require_manual_account(args)
    rt = build(args)
    with store.live_journal() as conn:
        acc = store.load_account(conn, ACCOUNT)
        abertas = {o.id: o for o in store.open_orders(conn, acc.id)}
        order = abertas.get(args.order_id)
        if order is None:
            print(f"ordem #{args.order_id} nao esta aberta")
            return
        rt.broker.confirm(order, args.quantity, args.price, args.fees)
        store.update_order(conn, order)
    print(f"ordem #{order.id} confirmada: {order.filled_qty} @ {order.avg_price} "
          f"({order.status.value})")
    print("rode 'python scripts/run_live.py step' (ou o loop) para aplicar o fill "
          "ao caixa/posicao da conta — e o que 'reconcile_pending_fills' faz.")


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
    p.add_argument("--mode", default=None, choices=("manual", "mt5"))
    p.add_argument("--capital", type=float, default=1_000.0)
    p.add_argument("--floor", type=float, default=None,
                   help="piso do saque em R$ absoluto (default: 55x o capital)")
    p.add_argument("--feed", default="parquet", choices=("parquet", "yfinance"))
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
                     ("reconcile", cmd_reconcile), ("unfreeze", cmd_unfreeze),
                     ("tickets", cmd_tickets)):
        sub.add_parser(nome).set_defaults(func=fn)

    c = sub.add_parser("confirm")
    c.add_argument("order_id", type=int)
    c.add_argument("quantity", type=int)
    c.add_argument("price", type=float)
    c.add_argument("fees", type=float, nargs="?", default=0.0)
    c.set_defaults(func=cmd_confirm)

    lp = sub.add_parser("loop")
    lp.add_argument("--seconds", type=int, default=60)
    lp.set_defaults(func=cmd_loop)

    s = sub.add_parser("sacar")
    s.add_argument("valor", type=float)
    s.add_argument("--intent-id", type=int, default=None,
                   help="confirma so esta recomendacao especifica -- obrigatorio "
                        "se houver mais de uma pendente ao mesmo tempo")
    s.add_argument("--data", default=None,
                   help="pregao de referencia (ISO, ex. 2026-08-18); default: hoje")
    s.set_defaults(func=cmd_sacar)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
