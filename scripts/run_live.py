"""Linha de comando da operacao ao vivo.

    python scripts/run_live.py --slot swing init --capital 50000 --mode mt5 \
        --strategy liqflop --mt5-shares-per-lot 1
    python scripts/run_live.py --slot swing status
    python scripts/run_live.py --slot swing step    # um passo do supervisor
    python scripts/run_live.py --slot swing decide  # forca o fecho do pregao
    python scripts/run_live.py --slot swing execute # forca a execucao do dia
    python scripts/run_live.py --slot swing reconcile  # aplica fills confirmados ao caixa/posicao
    python scripts/run_live.py --slot swing unfreeze   # destrava o disjuntor manualmente
    python scripts/run_live.py --slot swing loop --seconds 60

    python scripts/run_live.py --slot daytrade --strategy gremah \
        --mt5-shares-per-lot 1 loop --seconds 5

Slots (--slot) — obrigatorio, sem default
------------------------------------------
Cada slot e' UMA vaga de operacao: uma conta, um caixa, um processo, um robo
(ver `core.config.SLOTS`). `daytrade` roda um `IntradayStrategy` via
`live/intraday_runtime.py` (decide barra a barra, nunca carrega posicao
overnight); `swing` roda um `Strategy` diario via `live/runtime.py` (decide
1x por pregao, executa no pregao seguinte). Sem default de proposito, mesmo
precedente de `--strategy`: um fallback silencioso aqui operaria dinheiro
real na vaga errada.

`decide`/`execute`/`unfreeze` sao subcomandos do ciclo DIARIO e recusam um
slot intradiario explicitamente — nao ha "fecho do pregao" a forcar num robo
que decide a cada minuto.

Modo de execucao (--execution-mode)
------------------------------------
`shadow` (default) journaliza tudo — intencao, ordem, fill, resultado — mas
NUNCA chama a corretora, e nao debita o caixa. `live` envia ordem de verdade.
Hoje so o slot de day trade honra esta flag (o de swing sempre envia): ela
existe porque a premissa central do robo de day trade (ordem-limite preenche
quando o preco toca o nivel, sem pagar o spread) nunca foi medida contra o
mercado real — ver `live/intraday_runtime.py`.

`loop` so da passo dentro da janela de pregao B3 +/-1h (ver `live.clock.
in_active_window`) — fora dela (noite, fim de semana, feriado) fica
dormindo ate a janela abrir de novo, em vez de acordar a cada `--seconds`
so para constatar que nao ha nada a fazer.

Frequencia do passo (--seconds)
-------------------------------
Default 5s. O numero nao e chute: foi MEDIDO contra o terminal real da Clear
em 2026-08-20, pregao aberto, os 7 tickers da watchlist, 60 leituras seguidas.

  custo  : 0,8ms por leitura dos 7 tickers (p95 1,8ms, max 1,9ms). A uma
           leitura por segundo isso ocupa 0,08% do processo — custo nao e
           argumento para espacar o passo. O terminal nao degradou nem
           enfileirou nas 60 chamadas.
  ganho  : o preco muda a cada 2,3s (CSMG3) a 5,4s (KEPL3) nos papeis
           liquidos. EMAE4 nao mudou NENHUMA vez em 60s — papel iliquido nao
           melhora com frequencia nenhuma, e a defesa dele nao e o stop.

Ou seja: a 60s o supervisor perdia ate ~22 mudancas de preco entre duas
olhadas. Isso importa porque o stop intra-dia (`live/robots.py::on_intraday`)
so ve o preco que o feed entregou NAQUELE instante — nao existe "a barra
inteira" como no backtest. Num tombo como o de HAPV3 em 2025-11-13, que caiu
25% DEPOIS da abertura, 60s e tempo de sobra para sair muito abaixo do stop.

Abaixo de ~2s nao ha ganho: o feed nao atualiza mais rapido, e a leitura extra
so reve o mesmo tick. 5s pega quase todo o ganho e deixa margem para o
terminal ficar mais lento com mais papeis ou hardware pior.

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
          momento. ATENCAO: validado em 2026-08-21 contra o terminal real da
          Rico (conexao, symbol_info, resolucao de volume e `order_check` —
          validacao SEM executar ordem real, ver memoria de sessao) — mas
          nenhum `order_send` de verdade foi enviado ainda. Teste primeiro
          com o MENOR lote possivel, em horario de pregao, observando o
          terminal ao vivo, antes de confiar nisto operando sem supervisao.
          `--mt5-shares-per-lot`/`--mt5-symbol-map` precisam ser conferidos
          contra o `symbol_info` do SEU terminal (a relacao acao/lote e o nome
          do simbolo variam por corretora — nao ha valor universal). O
          `magic` das ordens NAO e' flag: vem do slot (`core.config.Slot.
          magic`), porque a conta e' NETTING e e' o unico jeito de distinguir
          as ordens de um robo das do outro — deixar isso digitavel permitiria
          dois robos carimbarem igual. `--mt5-fractional-map` e diferente: so os tickers com
          mercado fracionario de fato, pro broker escolher lote padrao
          (GRATUITO na Rico) ou fracionario (paga por ordem) sozinho a cada
          entrada, conforme a quantidade pedida. So vale pro slot `swing` --
          `build_intraday` IGNORA esta flag de proposito (pedido explicito do
          dono, 2026-08-22): day trade nunca pode cair no mercado fracionario,
          nem como fallback, dado o giro alto da familia gremah.

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

`MT5_TERMINAL_PATH` (caminho do `terminal64.exe`) tambem e o que permite o
sistema ABRIR o terminal ja com o AutoTrading ligado — `run_live.py terminal`,
e automaticamente antes do primeiro passo de um `loop` em modo REAL. Sem ela,
o terminal aberto por um humano continua funcionando normalmente; o que se
perde e so a abertura automatica. Ver `live/mt5_terminal.py` para por que isso
passa pelo arquivo de config e nao por um "liga o botao" (o de 25/08/2026: um
pregao inteiro perdido com o AutoTrading desligado na abertura).

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
Nao ha robo hardcoded, nos dois slots. Slot `swing`: `--strategy` recebe a
CHAVE de um robo do registry de swing (`strategy.registry.list_strategies()`
/ pagina `/estrategias`), resolvido via
`strategy.registry.get_strategy(chave).factory()`. Slot `daytrade`: a chave
vem do registry PROPRIO de day trade (`strategy.daytrade.registry.
list_daytrade_robots()` — ver docstring de la para o motivo de nao ser o mesmo
registry, e o comentario sobre `_ROBOTS` em `strategy/daytrade/registry.py`
para o podio DECLARADO atual, que muda por decisao do dono e nao deve ser
hardcoded aqui). A GRANULARIDADE do dado tambem vem do robo (`feed_kind`): o mesmo
comando sobe um robo de barra M1 ou um de negocio a negocio sem nenhuma flag a
mais, porque quem monta o feed le a declaracao dele
(`live/intraday_feed.py::feed_for`). O SIMBOLO negociado e' propriedade do
ROBO escolhido (`IntradayStrategy.symbol`), nao do slot: `core.config.Slot`
nao declara simbolo desde 2026-08-21, exatamente para permitir registrar um
segundo robo de day trade operando outro ativo sem tocar no catalogo.

Nos dois casos o dashboard resolve isso sozinho (catalogo/top-3 na criacao da
conta, `live_accounts.investment_robot` da conta ja existente ao retomar —
nunca troca de robo sozinho numa conta ja em operacao). Quem usa este CLI
direto numa conta JA EXISTENTE precisa passar a MESMA chave usada na
criacao — `status` mostra o `investment_robot` gravado; uma chave diferente
aqui e a conta ja existente diverge silenciosamente (ver `LiveRuntime.
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
from core.config import SLOTS, WATCHLIST, BacktestConfig, slot_by_id
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


def _resolve_slot(args):
    """Slot pedido, ou erro. Sem default (ver docstring do modulo)."""
    if not getattr(args, "slot", None):
        raise ValueError(
            "--slot é obrigatório — não há vaga padrão. Use 'swing' (diário) "
            "ou um slot de day trade no formato 'dt-<robô>-<ativo>-<modo>' "
            "(ex.: 'dt-gremah-pmam3-shadow'). Ver core.config.slot_by_id."
        )
    try:
        return slot_by_id(args.slot)
    except KeyError as e:
        raise ValueError(str(e)) from e


def build_intraday(args):
    """Monta o `IntradayLiveRuntime` do slot de day trade.

    O símbolo vem do SLOT (`dt-<robô>-<ativo>`, ver
    `core.config.daytrade_slot`) desde 2026-08-22, quando o painel passou a
    abrir N robôs de day trade — um por ativo, cada um num processo próprio.
    Antes disso o ativo era propriedade do robô resolvido no registry, o que
    tornava impossível rodar dois `gremah` em papéis diferentes.

    Um slot SEM símbolo (id fora do formato dinâmico) cai no default da
    classe: mantém funcionando qualquer invocação antiga da linha de comando,
    sem inventar um ativo."""
    from backtest.intraday.profiles import config_for, profile_for
    from live.intraday_feed import feed_for
    from live.intraday_runtime import IntradayLiveRuntime
    from market_data_intraday.mt5_source import symbol_economics
    from strategy.daytrade.registry import get_daytrade_robot

    slot = _resolve_slot(args)
    try:
        strategy_obj = get_daytrade_robot(args.strategy or slot.robot_key,
                                          symbol=slot.symbol or None)
    except KeyError as e:
        raise ValueError(str(e)) from e
    except ValueError as e:
        # `Gremah.__init__` recusa símbolo sem calibração própria. Reempacota
        # com o slot no texto: o operador precisa saber QUAL robô morreu, não
        # só que "algum" símbolo não tem calibração.
        raise ValueError(f"slot {slot.id!r}: {e}") from e
    symbol = strategy_obj.symbol
    if args.mode != "mt5":
        raise ValueError(f"--mode inválido ou ausente: {args.mode!r} — use 'mt5'.")
    if args.mt5_shares_per_lot is None or args.mt5_shares_per_lot <= 0:
        raise ValueError(
            "--mt5-shares-per-lot é obrigatório no modo mt5 — confira o "
            "symbol_info do SEU terminal MT5 antes de operar."
        )
    try:
        profile = profile_for(symbol)
    except KeyError as e:
        raise ValueError(
            f"símbolo {symbol!r} do robô {strategy_obj.name!r} não tem perfil econômico "
            f"declarado em backtest.intraday.profiles.PROFILES/FUTURES_PROFILES — sem "
            "custo, corte de flatten e lote de referência não há como operar honestamente."
        ) from e

    from live.broker_mt5 import MT5Broker  # import tardio: so quando de fato usado

    credenciais = _mt5_credentials()
    # `symbol_map` traduz o ticker do robo (`WDO@`, `WIN@` -- continuo, so'
    # cotacao) pro contrato REAL com vencimento em aberto (ex. `"WDOU26"`) --
    # sem ele, toda ordem de futuro no dia trade e' recusada pelo servidor
    # (retcode 10017 `TRADE_DISABLED`, achado ao vivo em 2026-08-28). Vem
    # detectado sozinho a cada "Iniciar operacao"
    # (`dashboard/live_control.py::detect_futures_symbol_map`), nunca digitado
    # a mao -- mesmo padrao de `build_daily`, que ja fazia isto (este caminho
    # so' nao fazia ainda porque nenhum robo de futuro tinha ido a producao).
    symbol_map = json.loads(args.mt5_symbol_map) if args.mt5_symbol_map else None
    # Day trade NUNCA conhece mercado fracionario -- nem `--mt5-fractional-map`
    # (pedido explicito do dono, 2026-08-22). `args.mt5_fractional_map` e'
    # ignorado de proposito aqui, mesmo se alguem passar a flag na linha de
    # comando: o `MT5Broker` deste slot nasce SEM `fractional_map`, entao
    # `_resolve_execution` (broker_mt5.py) nunca tem pra onde cair -- uma
    # quantidade que nao fecha o lote padrao e' REJEITADA, nunca reencaminhada
    # a um simbolo "F". Giro alto (`gremah.sizing_rules`) paga taxa de bolsa a
    # cada round-trip; uma ordem fracionaria custaria R$1,90 fixos a mais por
    # ordem na Rico, o que inviabilizaria o robo.
    broker = MT5Broker(magic=slot.magic, shares_per_lot=args.mt5_shares_per_lot,
                       symbol_map=symbol_map, **credenciais)

    # A economia do contrato vem do TERMINAL (tick size/value reais), nunca
    # hardcoded — mesma filosofia de `MT5Feed` autocalibrar o fuso.
    econ = symbol_economics(symbol, **credenciais)
    if econ is None:
        raise ValueError(
            f"não consegui ler symbol_economics de {symbol!r} no terminal MT5 — "
            "confirme que o terminal está aberto e logado, e que o símbolo está "
            "visível no Market Watch."
        )

    # O fuso do servidor MT5 e' DECLARADO e medido (`core.b3_session`), nao
    # inferido — a inferencia antiga adotou +4.0h onde o certo era +3.0h, e no
    # day trade um offset errado troca a fase do robo e o minuto do flatten em
    # silencio. O `MT5Feed` entra aqui como CONFERENTE do relogio, contra o
    # papel liquido de referencia: se ele acusar, o runtime nao opera (ver
    # `IntradayLiveRuntime`), em vez de reescrever o offset por conta propria.
    clock_feed = MT5Feed(**credenciais)
    # BARRA M1 ou NEGOCIO A NEGOCIO conforme o robo declara em `feed_kind` —
    # nunca uma escolha deste chamador (ver `live/intraday_feed.py`).
    bar_feed = feed_for(strategy_obj, **credenciais)
    return IntradayLiveRuntime(
        slot=slot,
        strategy=strategy_obj,
        # `target_fills_as_maker` vem da ESTRATEGIA, nao deste chamador: era
        # `True` aqui e `False` no CLI de backtest, ou seja, o robo que opera e
        # o robo validado tinham modelo de custo diferente.
        config=config_for(profile, trade_tick_value=econ.trade_tick_value,
                          trade_tick_size=econ.trade_tick_size,
                          target_fills_as_maker=strategy_obj.target_fills_as_maker,
                          initial_capital=args.capital),
        bar_feed=bar_feed,
        broker=broker,
        notifier=_build_notifier(args.notify_min_level),
        execution_mode=args.execution_mode,
        initial_capital=args.capital,
        clock_feed=clock_feed,
    )


def build(args):
    """Runtime do slot pedido — `IntradayLiveRuntime` ou `LiveRuntime`."""
    slot = _resolve_slot(args)
    if slot.is_intraday:
        return build_intraday(args)
    return build_daily(args)


def build_daily(args) -> LiveRuntime:
    slot = _resolve_slot(args)
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
        fractional_map = json.loads(args.mt5_fractional_map) if args.mt5_fractional_map else None
        broker = MT5Broker(magic=slot.magic, shares_per_lot=args.mt5_shares_per_lot,
                           symbol_map=symbol_map, fractional_map=fractional_map,
                           **_mt5_credentials())
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
        account_name=slot.id,
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


def _require_daily(args, subcomando: str):
    """Recusa um subcomando do ciclo DIARIO num slot intradiario.

    `decide`/`execute`/`unfreeze` sao sobre "fechar o pregao e decidir para o
    seguinte" e sobre o disjuntor de risco diario — nada disso existe num robo
    que decide a cada barra e nunca carrega posicao overnight. Recusar
    explicitamente e' melhor que um `AttributeError` cru vindo de um runtime
    que nao tem o metodo."""
    slot = _resolve_slot(args)
    if slot.is_intraday:
        print(f"'{subcomando}' não se aplica ao slot {slot.id!r} (day trade): não há "
              "fecho de pregão a forçar nem disjuntor diário num robô que decide "
              "barra a barra. Use 'step'/'loop'/'status'.")
        sys.exit(1)
    return slot


def cmd_init(args) -> None:
    rt = build(args)
    acc = rt.ensure_account()
    print(f"conta '{acc.name}' pronta — modo {acc.mode}, capital R$ {acc.initial_capital:,.2f}"
          .replace(",", "."))
    print(f"  robo de investimento: {acc.investment_robot}")
    print(f"  robo de saque:        {acc.withdrawal_robot or '(nenhum — day trade não tem overlay de saque)'}")
    if getattr(rt, "execution_mode", None) is not None:
        print(f"  modo de execucao:     {rt.execution_mode}"
              + (" (journaliza, NAO envia ordem)" if rt.execution_mode == "shadow" else ""))
    if _resolve_slot(args).is_intraday:
        if isinstance(rt.notifier, NullNotifier):
            print("  alerta externo:       nenhum configurado (so diario/dashboard)")
        else:
            print("  alerta externo:       ativo (Telegram e/ou e-mail)")
        return
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
    _require_daily(args, "decide")
    rt = build(args)
    from live import clock
    print(rt.close_and_decide(clock.session_date()))


def cmd_execute(args) -> None:
    _require_daily(args, "execute")
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
    _require_daily(args, "reconcile")
    rt = build(args)
    print(rt.reconcile_pending_fills())


def cmd_unfreeze(args) -> None:
    _require_daily(args, "unfreeze")
    rt = build(args)
    if rt.risk_guard is None:
        print("nenhum disjuntor configurado nesta chamada (--daily-loss-limit/--monthly-loss-limit "
              "ausentes) — nada a destravar.")
        return
    rt.unfreeze()
    print("disjuntor destravado.")


def _preparar_terminal(rt) -> None:
    """Antes do primeiro passo em modo REAL: terminal aberto e AutoTrading
    ligado, ou o motivo impresso e notificado.

    Chamado so' aqui, e nao dentro do runtime, por causa da regra 6 do
    AGENTS.md: abrir programa e mexer em arquivo de config do terminal e'
    trabalho de ORQUESTRACAO, nao de quem decide operacao. O runtime so'
    confere e recusa (`_check_autotrading`).

    NAO aborta o supervisor quando falha: o dono pode ligar o botao com o
    processo ja de pe (foi o que aconteceu em 25/08/2026, ~14h) e o proximo
    passo libera a operacao sozinho. Matar o processo aqui trocaria um
    problema de 1 segundo por um "e agora tenho de subir o robo de novo"."""
    from live.mt5_terminal import garantir_terminal_com_autotrading

    resultado = garantir_terminal_com_autotrading(os.environ.get("MT5_TERMINAL_PATH"))
    if resultado.ok:
        print(f"terminal MT5 pronto com AutoTrading ligado ({resultado.acao}).", flush=True)
        return
    print(f"[atencao] {resultado.motivo}", flush=True)
    rt.notifier.notify("error", "terminal", resultado.motivo)


def cmd_terminal(args) -> None:
    """Sobe o terminal MT5 com o AutoTrading ligado (ou diz o que falta).

    Existe como comando proprio para o dono poder rodar antes da abertura,
    sem subir robo nenhum -- e para o painel poder chamar o MESMO caminho de
    codigo no dia em que quiser um botao para isso."""
    from live.mt5_terminal import garantir_terminal_com_autotrading

    resultado = garantir_terminal_com_autotrading(os.environ.get("MT5_TERMINAL_PATH"))
    print(f"{resultado.acao}: {resultado.motivo or 'terminal pronto, AutoTrading ligado.'}")
    if not resultado.ok:
        sys.exit(1)


def cmd_loop(args) -> None:
    from live import clock
    from live.slot_lock import SlotEmUso, lock_slot

    slot = _resolve_slot(args)
    # Exclusividade por slot ANTES de montar qualquer coisa -- a guarda de
    # processo duplicado so' existia no botao do painel (`live_control.
    # start()`), e este caminho (CLI direta, servico NSSM) passava livre.
    # Dois processos no mesmo slot compartilham o `magic` e enxergam a ordem
    # e a posicao do outro como suas. Ver `live/slot_lock.py`.
    try:
        with lock_slot(slot.id):
            _loop_travado(args, slot)
    except SlotEmUso as e:
        print(f"[erro fatal] {e}", flush=True)
        sys.exit(1)


#: Caminho do heartbeat DESTE slot -- tocado (mtime) a cada volta do laço
#: abaixo, inclusive durante o sono fora do horario de pregao (ver
#: `_HEARTBEAT_CHUNK_SECONDS`). E' o unico jeito de quem esta' de FORA deste
#: processo (o watchdog em `dashboard/live_control.py`) distinguir "vivo e
#: andando" de "vivo e travado" -- um PID que existe no SO nao prova nada
#: disso (achado ao vivo em 02/09/2026: os 7 supervisores de day trade
#: ficaram travados por 21h+ com CPU acumulada parada, PID de pe' o tempo
#: todo, `tasklist`/`Get-CimInstance` os via' "rodando" o tempo inteiro).
#: Formula local (nao importa de `dashboard/`) de proposito: este script roda
#: standalone via CLI/servico NSSM, sem depender do modulo do dashboard para
#: uma convencao de path de 1 linha -- mesmo espirito de `_log_path` em
#: `dashboard/live_control.py`, que tambem nao e' compartilhada para ca.
def _heartbeat_path(slot_id: str) -> Path:
    return Path(__file__).resolve().parents[1] / "db" / f"live_process.{slot_id}.heartbeat"


def _touch_heartbeat(slot_id: str) -> None:
    """Best-effort: um erro ao tocar o heartbeat (disco cheio, permissao) nao
    pode derrubar o supervisor -- o pior caso e' o watchdog achar que este
    slot travou quando na verdade so' o heartbeat que falhou, o que so' custa
    um restart a mais, nunca um robo cego sem ninguem reiniciando."""
    try:
        _heartbeat_path(slot_id).touch()
    except OSError:
        pass


#: Teto de quanto tempo o laco pode dormir de uma vez so' fora do horario de
#: pregao. Antes disto era um `time.sleep(espera)` unico que podia passar de
#: 12h (visto ao vivo: "proximo passo em 12.2h") -- o heartbeat ficava mudo
#: o mesmo tanto de tempo que um travamento de verdade ficaria, e o watchdog
#: nao tinha como distinguir os dois casos. Fatiar em pedacos de ate 60s e
#: tocar o heartbeat entre cada um mantem o sinal "vivo" fresco mesmo
#: dormindo de proposito a noite inteira ou o fim de semana inteiro.
_HEARTBEAT_CHUNK_SECONDS = 60.0


def _loop_travado(args, slot) -> None:
    """O laco do supervisor, ja com a exclusividade do slot garantida."""
    from live import clock

    rt = build(args)
    print(f"supervisor do slot '{slot.id}' ativo — passo a cada {args.seconds}s, so na "
          f"janela de pregao B3 +/-1h (fora dela, dorme ate a janela abrir de novo; "
          f"sem passo nenhum a noite ou no fim de semana). Ctrl+C para parar.")
    if getattr(rt, "execution_mode", None) == "shadow":
        print("MODO SOMBRA: tudo e' journalizado, NENHUMA ordem vai para a corretora.",
              flush=True)
    else:
        _preparar_terminal(rt)
    while True:
        # Tocado ANTES de qualquer coisa nesta volta -- inclusive antes do
        # passo que pode travar (`rt.run_once()`, chamada MT5 sem timeout
        # nativo). Se esta volta travar ali dentro, o heartbeat ja foi
        # tocado no INICIO dela e nao e' tocado de novo: e' exatamente esse
        # "parou de andar" que o watchdog externo mede.
        _touch_heartbeat(slot.id)
        try:
            espera = clock.seconds_until_active_window()
            if espera > 0:
                print(f"[fora do horario de pregao] proximo passo em {espera / 3600:.1f}h", flush=True)
                restante = espera
                while restante > 0:
                    dorme = min(restante, _HEARTBEAT_CHUNK_SECONDS)
                    time.sleep(dorme)
                    restante -= dorme
                    _touch_heartbeat(slot.id)
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
    # SEM `choices`: os slots de day trade sao DINAMICOS (`dt-<robo>-<ativo>`,
    # criados pelo dono no painel) e nao existem em `SLOTS`. Um `choices` fixo
    # recusaria todo robo de day trade antes de `_resolve_slot` poder explicar
    # o que ha de errado. Quem valida e' `core.config.slot_by_id`, que conhece
    # os dois formatos e devolve mensagem util.
    p.add_argument("--slot", default=None,
                   help="vaga de operacao -- obrigatorio, sem default. Estaticos: "
                        f"{', '.join(s.id for s in SLOTS)}. Day trade: "
                        "dt-<robo>-<ativo> (ex.: dt-gremah-pmam3)")
    p.add_argument("--execution-mode", default="shadow", choices=("shadow", "live"),
                   help="'shadow' journaliza sem enviar ordem (default); 'live' envia "
                        "de verdade. So o slot de day trade honra esta flag hoje")
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
    p.add_argument("--mt5-shares-per-lot", type=float, default=None,
                   help="obrigatorio no modo mt5 — confira em symbol_info do SEU "
                        "terminal MT5 antes de operar, nao ha valor universal")
    p.add_argument("--mt5-symbol-map", default=None,
                   help='JSON, ex.: \'{"WEGE3.SA": "WEGE3F"}\' -- override do nome de '
                        'simbolo cadastrado na corretora (feed E broker); nao confundir '
                        'com --mt5-fractional-map')
    p.add_argument("--mt5-fractional-map", default=None,
                   help='JSON, ex.: \'{"WEGE3.SA": "WEGE3F"}\' -- SO os tickers com '
                        'simbolo de mercado fracionario no terminal (broker escolhe, a '
                        'cada ordem, lote padrao ou fracionario conforme a quantidade '
                        'pedida — ver docstring de live/broker_mt5.py)')
    sub = p.add_subparsers(dest="cmd", required=True)

    for nome, fn in (("init", cmd_init), ("status", cmd_status), ("step", cmd_step),
                     ("decide", cmd_decide), ("execute", cmd_execute),
                     ("reconcile", cmd_reconcile), ("unfreeze", cmd_unfreeze),
                     ("terminal", cmd_terminal)):
        sub.add_parser(nome).set_defaults(func=fn)

    lp = sub.add_parser("loop")
    # 5s, e nao 60s: MEDIDO contra o terminal real da Clear em 2026-08-20, com
    # o pregao aberto e os 7 tickers da watchlist (ver o bloco "Frequencia do
    # passo" na docstring do modulo). Uma leitura custa 0,8ms (p95 1,8ms), e o
    # preco muda a cada 2,3-5,4s nos papeis liquidos: a 60s o supervisor perdia
    # ate ~22 mudancas de preco entre duas olhadas, o que num tombo intra-dia
    # (HAPV3 caiu 25% DEPOIS de abrir) e tempo de sobra para o preco andar
    # muito antes de o stop ser visto. Abaixo de ~2s nao ha ganho: o feed nao
    # atualiza mais rapido que isso e a leitura extra so reve o mesmo tick.
    lp.add_argument("--seconds", type=int, default=5)
    lp.set_defaults(func=cmd_loop)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
