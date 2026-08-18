"""O ambiente: acopla os robos ao mercado real, executa e registra.

O que este modulo E
-------------------
Um supervisor. Ele nao decide nada sobre o mercado — ele mantem dado fresco,
sabe em que ponto do pregao esta, entrega o estado real aos robos, transforma a
decisao deles em ordem, confere o que a corretora devolveu, atualiza o estado e
grava tudo. Toda regra de mercado esta em `strategy/` e em
`backtest/withdrawal.py` (regra 6 do AGENTS.md).

A ordem das operacoes nao e livre
---------------------------------
Ela e copiada de `backtest/engine_portfolio.py`, barra por barra, porque
qualquer troca de ordem muda o resultado e faria a operacao divergir do
backtest que a validou:

  FECHO de D (`close_and_decide`)
    1. marca o equity com o close de D
    2. politica de saque decide  -> intencao para D+1
    3. estrategia decide          -> intencoes para D+1
    4. `bars_held += 1`

  ABERTURA de D+1 (`execute_session`)
    1. expira intencao atrasada (execute_on < hoje) — nunca executa velho
    2. saque programado no fecho de ontem
    3. saidas (rotacao, defensiva)
    4. saque por evento de liquidez, se alguma venda creditou caixa hoje
    5. entradas, dimensionadas pelo caixa JA descontado do saque

  DURANTE o pregao (`intraday_tick`)
    stop: no backtest dispara quando `low[D] <= stop`, porque o engine ve a
    barra fechada. Ao vivo dispara no preco observado — ver a nota sobre atraso
    de feed em `live/robots.py`. Essa e a unica diferenca estrutural entre
    backtest e operacao, e ela e de EXECUCAO, nao de estrategia.

Relogio agenda, dado decide
---------------------------
Nenhuma decisao e liberada por hora de relogio. `close_and_decide` so roda
quando o dado do pregao esta efetivamente no disco (`data_is_ready`). O relogio
da maquina erra fuso, nao conhece feriado novo e nao sabe de pregao estendido; o
parquet, se tem a barra, tem a barra.

Idempotencia
------------
Todo passo pode ser chamado de novo sem estragar nada — e requisito, nao luxo:
um supervisor que roda a cada minuto vai repetir passos, e um restart no meio do
dia tem de conseguir continuar. `execute_session` e idempotente porque intencao
executada sai de PENDING; `close_and_decide` e idempotente porque checa se ja
existe marcacao de equity para o pregao.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional, Sequence

import pandas as pd

from backtest.sizing import has_free_slot, initial_stop, liquidation_quantity, plan_entry
# `LIVE_DB_PATH as DB_PATH`: o NOME do atributo de módulo permanece `DB_PATH`
# de propósito (FEAT-000, ver ACTION-PLAN — premissa 4) — `tests/test_dashboard_app.py`
# faz `monkeypatch.setattr(live_runtime, "DB_PATH", tmp)` e depende desse nome
# continuar existindo aqui. O VALOR, porém, passa a ser o banco separado da
# operação real (antes era o mesmo arquivo do backtest).
from core.config import BENCHMARK, LIVE_DB_PATH as DB_PATH, WATCHLIST, BacktestConfig
from core.live_models import (
    AccountState,
    Intent,
    IntentKind,
    IntentStatus,
    LivePosition,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    RobotContext,
    SessionPhase,
)
from journal import live_store as store
from live import clock
from live.broker import Broker
from live.feed import QuoteFeed, staleness_report
from live.notify import NullNotifier, Notifier
from live.riskguard import CircuitBreaker
from live.robots import InvestmentRobot, LiveRobot, WithdrawalRobot
from market_data.download import download_all
from market_data.loader import load_universe

# Idade maxima tolerada de uma cotacao para a checagem de stop intra-dia. Acima
# disso o runtime ainda registra o preco, mas avisa: um stop avaliado sobre dado
# velho dispara no lugar errado, e isso tem de aparecer no log operacional e nao
# so no extrato.
DEFAULT_MAX_QUOTE_AGE = 300.0

# Intervalo minimo entre sincronizacoes automaticas de dado (ver `_sync_due`).
# Casa com `MARKET_REFRESH_SECONDS` do dashboard (`dashboard/app.py`) — mesma
# fonte, mesma cadencia razoavel, dois consumidores independentes.
DEFAULT_SYNC_INTERVAL_SECONDS = 60 * 60.0

# Diferenca minima (R$) entre o saldo real da corretora e `AccountState.cash`
# para valer como deposito/discrepancia (ver `reconcile_broker_cash`). Um
# real de folga e o suficiente para nunca reagir a ruido de centavos (juros
# de um dia, arredondamento de corretagem) sem deixar passar nenhum aporte
# de verdade — aportes reais sao, na pratica, sempre ordens de grandeza
# maiores que isso.
_DEPOSIT_TOLERANCE = 1.0


@dataclass
class StepReport:
    """O que um passo do supervisor fez. Serve para log, dashboard e teste."""

    action: str
    session: Optional[date] = None
    phase: Optional[SessionPhase] = None
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        extra = " ".join(f"{k}={v}" for k, v in self.detail.items())
        return f"[{self.action}] {self.session or ''} {extra}".strip()


class LiveRuntime:
    """Ambiente de operacao de uma conta.

    Uma conta = um robo de investimento + um robo de saque + uma corretora. Se
    algum dia houver duas contas (uma em paper, uma real), sao duas instancias
    desta classe apontando para o mesmo banco com `account_name` diferente — nao
    ha estado global.
    """

    def __init__(
        self,
        account_name: str,
        strategy,
        policy,
        feed: QuoteFeed,
        broker: Broker,
        config: BacktestConfig,
        tickers: Sequence[str] = WATCHLIST,
        db_path=None,
        data_dir=None,
        max_quote_age: float = DEFAULT_MAX_QUOTE_AGE,
        sync_interval_seconds: float = DEFAULT_SYNC_INTERVAL_SECONDS,
        notifier: Optional[Notifier] = None,
        risk_guard: Optional[CircuitBreaker] = None,
    ) -> None:
        self.account_name = account_name
        self.feed = feed
        self.broker = broker
        self.config = config
        self.tickers = tuple(tickers)
        # `NullNotifier` default: alerta externo e opt-in (ver `live/notify.py`)
        # — sem token/credencial configurada, o sistema so grava em
        # `live_events` (o dashboard sempre mostra tudo), sem tentar sair
        # pela rede. `risk_guard` default None: sem trava configurada, o
        # runtime nunca veta entrada por conta propria — quem quer a
        # protecao a liga explicitamente (ver `scripts/run_live.py`).
        self.notifier: Notifier = notifier if notifier is not None else NullNotifier()
        self.risk_guard = risk_guard
        # `None` cai no diario oficial do projeto — resolvido aqui, nao em
        # `journal.live_store` (que so aceita PATH concreto), para o
        # construtor aceitar "usa o padrao" sem cada chamador ter que
        # importar `core.config.DB_PATH` por conta propria.
        self.db_path = db_path if db_path is not None else DB_PATH
        # Injetavel para teste (universo sintetico em tmp_path) sem tocar em
        # `data/raw` real. `None` preserva o default de `market_data.loader`
        # (DATA_DIR) em producao.
        self.data_dir = data_dir
        self.max_quote_age = float(max_quote_age)
        self.sync_interval_seconds = float(sync_interval_seconds)
        self._last_sync_at: Optional[datetime] = None

        self.investment: LiveRobot = InvestmentRobot(strategy)
        self.withdrawal: LiveRobot = WithdrawalRobot(policy)
        self._panels: dict[str, pd.DataFrame] = {}
        self._ibov: Optional[pd.DataFrame] = None
        self._prepared_through: Optional[date] = None

    # ---------- log + alerta (sempre juntos) -------------------------------

    def _log(self, conn, account_id: Optional[int], level: str, source: str,
             message: str, payload: Optional[dict] = None) -> None:
        """Grava no diario E notifica externamente, sempre os dois juntos.

        Um so ponto de chamada para as duas coisas — sem isso, seria facil
        adicionar um evento novo em algum lugar do runtime e esquecer de
        notificar (ou vice-versa), e as duas trilhas divergiriam silenciosamente.
        `notify()` nunca lanca (contrato de `Notifier`), entao chamar sempre
        aqui e seguro mesmo sem nenhum canal configurado (`NullNotifier`).
        """
        store.log_event(conn, account_id, level, source, message, payload)
        self.notifier.notify(level, source, message, payload)

    # ---------- estado dos robos (persistencia aninhada) --------------------

    def _restore_robot_state(self, policy_state: dict) -> None:
        """Reidrata a politica de saque e o circuit breaker a partir do
        `policy_state` da conta (JSON aninhado: `{"withdrawal": ..., "risk_guard": ...}`).

        Aninhado (em vez de gravar so o estado da politica direto, como era
        antes do circuit breaker existir) porque agora sao DOIS objetos com
        estado proprio dividindo a mesma coluna — sem o aninhamento, um
        sobrescreveria o outro."""
        if not policy_state:
            return
        self.withdrawal.restore(policy_state.get("withdrawal") or {})
        if self.risk_guard is not None:
            self.risk_guard.restore(policy_state.get("risk_guard") or {})

    def _robot_state(self) -> dict:
        """Inverso de `_restore_robot_state` — o que persistir em `policy_state`."""
        return {
            "withdrawal": self.withdrawal.state(),
            "risk_guard": self.risk_guard.state() if self.risk_guard is not None else {},
        }

    # ---------- infraestrutura de dado ------------------------------------

    def sync_data(self) -> StepReport:
        """Baixa OHLCV + macro. Delegado a `market_data` — o merge que preserva
        pregao perdido pelo provedor e a checagem de qualidade estao la.

        Chamada direta (linha de comando, cron externo) sempre baixa — quem
        pediu explicitamente sabe o que quer. O throttle e so em `run_once`
        (ver `_sync_due`), que e o caminho automatico chamado em loop.
        """
        written = download_all()
        return StepReport("sync_data", detail={"arquivos": len(written)})

    def _sync_due(self, now: datetime) -> bool:
        """Passou `sync_interval_seconds` desde a ultima sincronizacao automatica?

        Sem isso, `run_once` chamado a cada minuto (ver `scripts/run_live.py
        loop`) bateria em `download_all()` — yfinance + BCB, para o universo
        inteiro — a cada minuto, o dia inteiro de POST_CLOSE. O dado diario
        nao muda nesse ritmo; o throttle so existe para nao martelar a fonte
        externa por nada (a mesma preocupacao que ja existe no dashboard, ver
        `MARKET_REFRESH_SECONDS`/`MACRO_REFRESH_SECONDS` em `dashboard/app.py`).
        """
        if self._last_sync_at is None:
            return True
        return (now - self._last_sync_at).total_seconds() >= self.sync_interval_seconds

    def _load_universe(self) -> dict[str, pd.DataFrame]:
        """`load_universe`, honrando `self.data_dir` quando injetado (teste)."""
        if self.data_dir is not None:
            return load_universe(list(self.tickers), out_dir=self.data_dir)
        return load_universe(list(self.tickers))

    def _load(self, session: date, universe: Optional[dict[str, pd.DataFrame]] = None) -> None:
        """Carrega os paineis truncados em `session` e prepara os robos.

        A truncagem e a protecao contra barra em formacao: os indicadores do robo
        sao causais, entao ver o futuro nao mudaria o passado, mas o dado de HOJE
        pode estar parcial (o provedor publica intra-dia). Cortar em `session`
        garante que o robo decide sobre pregao fechado, que e o que ele viu em
        todo o backtest.

        `universe` injetavel para quem ja leu o parquet neste passo (ex.:
        `close_and_decide`, que precisa ler antes para checar `data_is_ready`)
        nao pagar a leitura de disco duas vezes.

        Furo real corrigido aqui: `core.calendar.is_month_end` decide "isto e
        fim de mes" comparando a data com a data SEGUINTE no indice (`shift(-1)`).
        No backtest isso nunca falha porque `run_portfolio_backtest` passa a
        `strategy.initialize()` o historico INTEIRO do parquet (nao truncado em
        `end` — so o loop de decisao e restrito a janela). Ao vivo, `session` E
        a ultima data que existe (nao ha amanha ainda), entao sem ajuste
        `is_month_end` nunca consegue confirmar que `session` e o ultimo pregao
        do mes — o robo simplesmente nunca decidiria nada num robo cujo sinal
        so age em fim de mes (ver `strategy/buy_the_dip.py`). A correcao NAO e
        inventar um preco do dia seguinte (isso seria look-ahead de verdade) —
        e extender so o INDICE do ibov com o proximo pregao real, que vem do
        CALENDARIO da B3 (`live.clock.next_session`, conhecido de antemao,
        sem precisar de nenhum dado de mercado), com valores NaN. `on_bar()`
        nunca e chamado com essa data extra — ela existe só para funcoes de
        indicador baseadas em "index shape" (como `is_month_end`) conseguirem
        fazer a mesma comparacao que fariam com o historico completo.
        """
        if self._prepared_through == session and self._panels:
            return
        universe = universe if universe is not None else self._load_universe()
        cut = pd.Timestamp(session)
        ibov_ate_hoje = universe[BENCHMARK].loc[lambda d: d.index <= cut]
        proximo_pregao = pd.Timestamp(clock.next_session(session))
        placeholder = pd.DataFrame(
            {col: [float("nan")] for col in ibov_ate_hoje.columns},
            index=pd.DatetimeIndex([proximo_pregao]),
        )
        self._ibov = pd.concat([ibov_ate_hoje, placeholder])
        self._panels = {
            t: df.loc[lambda d: d.index <= cut]
            for t, df in universe.items()
            if t != BENCHMARK
        }
        self.investment.prepare(self._panels, self._ibov)
        self.withdrawal.prepare(self._panels, self._ibov)
        self._prepared_through = session

    def data_is_ready(self, session: date) -> tuple[bool, list[str]]:
        """Todo ticker tem barra fechada em `session`? Devolve os que faltam.

        E este check — nao o relogio — que libera a decisao do dia.
        """
        return self._data_is_ready(session, self._load_universe())

    @staticmethod
    def _data_is_ready(session: date, universe: dict[str, pd.DataFrame]) -> tuple[bool, list[str]]:
        cut = pd.Timestamp(session)
        faltando = [t for t, df in universe.items() if cut not in df.index]
        return (not faltando), faltando

    def _marks(self, session: date) -> dict[str, float]:
        """Ultimo close conhecido por ticker, para marcar a carteira.

        Usa o ultimo close DISPONIVEL, nao exige o de `session`: um gap de um dia
        num ticker nao pode fazer a posicao sumir do equity e inventar um
        drawdown que nao existiu (mesma protecao do engine)."""
        marks: dict[str, float] = {}
        for t, df in self._panels.items():
            s = df["close"].dropna()
            if len(s):
                marks[t] = float(s.iloc[-1])
        return marks

    # ---------- contexto e estado -----------------------------------------

    def _context(self, session: date, account: AccountState,
                 phase: SessionPhase, quotes: Optional[dict] = None) -> RobotContext:
        return RobotContext(
            session=session, panels=self._panels, ibov=self._ibov,
            account=account, marks=self._marks(session), phase=phase,
            quotes=quotes or {},
        )

    def ensure_account(self) -> AccountState:
        with store.live_journal(self.db_path) as conn:
            acc = store.ensure_account(
                conn, name=self.account_name, mode=self.broker.mode,
                initial_capital=self.config.initial_capital,
                investment_robot=self.investment.key,
                withdrawal_robot=self.withdrawal.key,
            )
        self._restore_robot_state(acc.policy_state)
        return acc

    def unfreeze(self) -> None:
        """Reset manual do disjuntor de risco — humano revisou, pode operar de novo.

        So existe se `risk_guard` foi configurado; sem trava ligada, nao ha o
        que destravar. Persiste imediatamente (nao espera o proximo
        `close_and_decide`), porque o proposito e liberar a operacao o quanto
        antes depois da revisao, nao no proximo fecho.

        RESTAURA o estado antes de mexer nele: esta chamada normalmente vem de
        um processo NOVO (linha de comando), cujo `self.withdrawal`/
        `self.risk_guard` em memoria ainda nao viram o que esta gravado no
        banco. Persistir sem restaurar primeiro sobrescreveria o estado real
        da politica de saque (fila do minimo, mes ja pago) com um objeto
        recem-construido e vazio — perderia dado de producao por engano.
        """
        if self.risk_guard is None:
            return
        with store.live_journal(self.db_path) as conn:
            account = store.load_account(conn, self.account_name)
            if account is None:
                return
            self._restore_robot_state(account.policy_state)
            self.risk_guard.unfreeze()
            account.policy_state = self._robot_state()
            store.save_account(conn, account)
            self._log(conn, account.id, "info", "riskguard", "disjuntor destravado manualmente")

    # ---------- fecho: os robos decidem -----------------------------------

    def close_and_decide(self, session: date) -> StepReport:
        """Marca a carteira no fecho de `session` e colhe as decisoes dos robos.

        Ordem identica ao engine: equity -> saque -> estrategia -> bars_held.
        A politica de saque decide ANTES da estrategia porque no engine ela ve o
        equity do fecho antes de qualquer acao nova ser enfileirada; trocar a
        ordem mudaria o valor sacado.
        """
        universe = self._load_universe()
        ready, faltando = self._data_is_ready(session, universe)
        if not ready:
            return StepReport("decide_skip", session,
                              detail={"motivo": "dado incompleto", "faltando": ",".join(faltando)})
        self._load(session, universe)

        with store.live_journal(self.db_path) as conn:
            account = store.load_account(conn, self.account_name)
            if account is None:
                return StepReport("decide_skip", session, detail={"motivo": "conta inexistente"})
            if any(d == session.isoformat() for d, _e, _p in store.equity_series(conn, account.id)):
                return StepReport("decide_skip", session, detail={"motivo": "ja decidido"})
            self._restore_robot_state(account.policy_state)

            marks = self._marks(session)
            equity = account.equity(marks)
            patrimonio = account.patrimonio(marks)
            store.record_equity(conn, account.id, session, account.cash,
                                account.invested(marks), equity, account.external_cash)

            # Circuit breaker: observa o patrimonio do fecho ANTES de colher
            # decisoes, para o veto (se houver) valer para as intencoes que
            # vao ser geradas agora — nao para as do fecho anterior, que ja
            # foram gravadas.
            if self.risk_guard is not None:
                self.risk_guard.observe(session, patrimonio)

            execute_on = clock.next_session(session)
            ctx = self._context(session, account, SessionPhase.POST_CLOSE)
            intents: list[Intent] = []
            intents += self.withdrawal.on_close(ctx, execute_on)
            novas_entradas = self.investment.on_close(ctx, execute_on)

            if self.risk_guard is not None and self.risk_guard.is_frozen:
                # So VETA abertura de posicao nova — sair, mover stop e sacar
                # continuam liberados (ver docstring de `CircuitBreaker`: a
                # trava e sobre AUMENTAR exposicao, nunca sobre reduzir).
                bloqueadas = [i for i in novas_entradas if i.kind == IntentKind.ENTER]
                if bloqueadas:
                    self._log(conn, account.id, "warn", "riskguard",
                             f"{len(bloqueadas)} entrada(s) vetada(s): {self.risk_guard.reason}",
                             {"tickers": [i.ticker for i in bloqueadas]})
                novas_entradas = [i for i in novas_entradas if i.kind != IntentKind.ENTER]
            intents += novas_entradas

            gravadas, aplicadas = 0, 0
            for intent in intents:
                if intent.kind == IntentKind.ADJUST_STOP:
                    # Custo zero, efeito imediato — igual ao engine. E o stop
                    # nunca desce: essa guarda e do engine, entao tem de existir
                    # aqui tambem, senao um robo com bug afrouxaria o risco real.
                    pos = account.positions.get(intent.ticker or "")
                    if pos and intent.stop_price is not None and (
                        pos.current_stop is None or intent.stop_price > pos.current_stop
                    ):
                        pos.current_stop = float(intent.stop_price)
                        store.upsert_position(conn, account.id, pos)
                        aplicadas += 1
                    intent.status = IntentStatus.DONE
                store.record_intent(conn, account.id, intent)
                gravadas += 1

            for pos in account.positions.values():
                pos.bars_held += 1
                store.upsert_position(conn, account.id, pos)

            account.policy_state = self._robot_state()
            store.save_account(conn, account)
            self._log(conn, account.id, "info", "runtime",
                            f"fecho {session}: equity {equity:.2f}, {gravadas} intencoes")

        return StepReport("decide", session, detail={
            "equity": round(equity, 2), "intencoes": gravadas, "stops_movidos": aplicadas,
        })

    # ---------- abertura: o ambiente executa ------------------------------

    def execute_session(self, session: date) -> StepReport:
        """Executa as intencoes que valem para `session`, na ordem do engine.

        `_sell`/`_buy`/`_withdraw` devolvem um de tres resultados, nao um bool:
        `'done'` (aplicado), `'rejected'` (nao vai acontecer) e `'pending'`
        (ordem no ar, aguardando confirmacao — corretora manual ou limitada
        que ainda nao bateu o preco). `'pending'` NAO e rejeicao: a intencao
        vira `EXECUTING` e e resolvida depois por `reconcile_pending_fills`,
        sem ser re-tentada nem expirada por atraso.
        """
        self._load(clock.previous_session(session))
        quotes = self.feed.quotes(self.tickers)
        done = {"expiradas": 0, "saques": 0, "saidas": 0, "entradas": 0,
               "rejeitadas": 0, "aguardando": 0}

        with store.live_journal(self.db_path) as conn:
            account = store.load_account(conn, self.account_name)
            if account is None:
                return StepReport("execute_skip", session, detail={"motivo": "conta inexistente"})
            self._restore_robot_state(account.policy_state)

            # 1. Intencao atrasada nunca executa (regra 7 do AGENTS.md).
            for velha in store.stale_intents(conn, account.id, session):
                store.set_intent_status(conn, velha.id, IntentStatus.EXPIRED)
                self._log(conn, account.id, "warn", "runtime",
                                f"intencao {velha.id} expirada: valia em {velha.execute_on}, "
                                f"hoje e {session}")
                done["expiradas"] += 1

            pend = store.pending_intents(conn, account.id, session)
            saques = [i for i in pend if i.kind == IntentKind.WITHDRAW]
            saidas = [i for i in pend if i.kind == IntentKind.EXIT]
            entradas = [i for i in pend if i.kind == IntentKind.ENTER]

            # 2. Saque programado — sai antes das compras para a entrada ser
            #    dimensionada pelo caixa ja descontado.
            for intent in saques:
                r = self._withdraw(conn, account, session, intent, quotes)
                done["saques" if r == "done" else "rejeitadas" if r == "rejected" else "aguardando"] += 1

            # 3. Saidas.
            motivo_liquidez: Optional[str] = None
            for intent in saidas:
                r = self._sell(conn, account, session, intent, quotes)
                if r == "done":
                    done["saidas"] += 1
                    motivo_liquidez = intent.reason or motivo_liquidez
                elif r == "pending":
                    done["aguardando"] += 1
                else:
                    done["rejeitadas"] += 1

            # 4. Saque por evento de liquidez: alguma venda creditou caixa agora,
            #    o dinheiro esta na mao e o saque nao paga liquidacao extra.
            if motivo_liquidez:
                ctx = self._context(session, account, SessionPhase.OPEN, quotes)
                for intent in self.withdrawal.on_liquidity(ctx, motivo_liquidez):
                    store.record_intent(conn, account.id, intent)
                    r = self._withdraw(conn, account, session, intent, quotes)
                    done["saques" if r == "done" else "rejeitadas" if r == "rejected" else "aguardando"] += 1

            # 5. Entradas.
            for intent in entradas:
                r = self._buy(conn, account, session, intent, quotes)
                done["entradas" if r == "done" else "rejeitadas" if r == "rejected" else "aguardando"] += 1

            account.policy_state = self._robot_state()
            store.save_account(conn, account)

        return StepReport("execute", session, detail=done)

    # ---------- primitivas de execucao ------------------------------------

    def _place(self, conn, account: AccountState, intent: Optional[Intent],
               ticker: str, side: OrderSide, quantity: int,
               order_type: OrderType = OrderType.MARKET, note: str = "") -> Order:
        """Cria, persiste, envia e re-persiste uma ordem.

        Grava ANTES de enviar de proposito: se o processo morrer entre o envio e
        a confirmacao, a ordem existe no diario com status `NEW`/`SENT` e da para
        reconciliar. O contrario — enviar e depois gravar — perde ordem no ar,
        que e o pior estado possivel para uma conta real.
        """
        order = Order(ticker=ticker, side=side, quantity=quantity,
                      order_type=order_type, intent_id=intent.id if intent else None,
                      note=note)
        store.record_order(conn, account.id, order)
        self.broker.place(order)
        store.update_order(conn, order)
        return order

    def _sell(self, conn, account: AccountState, session: date,
              intent: Intent, quotes: dict) -> str:
        """Devolve `'done'` / `'rejected'` / `'pending'` — ver `execute_session`."""
        pos = account.positions.get(intent.ticker or "")
        if pos is None:
            store.set_intent_status(conn, intent.id, IntentStatus.CANCELLED)
            self._log(conn, account.id, "warn", "runtime",
                            f"saida de {intent.ticker} sem posicao — intencao cancelada")
            return "rejected"
        order = self._place(conn, account, intent, pos.ticker, OrderSide.SELL,
                            pos.quantity, note=f"saida: {intent.reason}")
        return self._resolve_sell(conn, account, intent, pos, order)

    def _resolve_sell(self, conn, account: AccountState, intent: Intent,
                      pos: LivePosition, order: Order) -> str:
        """Aplica o fill de uma venda ao estado da conta, se ja houver fill.

        Compartilhado entre `_sell` (execucao no dia) e
        `reconcile_pending_fills` (confirmacao chegou depois) — o efeito sobre
        caixa/posicao e o MESMO nos dois casos, so muda quando ele acontece.
        """
        if order.status in (OrderStatus.REJECTED, OrderStatus.CANCELLED):
            store.set_intent_status(conn, intent.id, IntentStatus.REJECTED)
            return "rejected"
        if order.filled_qty <= 0:
            # Ordem viva, sem fill ainda (corretora manual aguardando humano,
            # ou limitada que nao bateu preco). NAO e rejeicao: a intencao
            # fica EXECUTING para `reconcile_pending_fills` retomar depois,
            # sem ser re-tentada como PENDING nem expirada por atraso.
            store.set_intent_status(conn, intent.id, IntentStatus.EXECUTING)
            self._log(conn, account.id, "info", "runtime",
                            f"saida de {pos.ticker} aguardando confirmacao (ordem #{order.id})")
            return "pending"

        liquido = (order.avg_price or 0.0) * order.filled_qty - order.fees
        account.cash += liquido
        if order.filled_qty >= pos.quantity:
            store.delete_position(conn, account.id, pos.ticker, pos.kind)
            account.positions.pop(pos.ticker, None)
        else:
            fora = order.filled_qty / pos.quantity
            pos.quantity -= order.filled_qty
            pos.capital_allocated *= (1.0 - fora)
            store.upsert_position(conn, account.id, pos)
        store.set_intent_status(conn, intent.id, IntentStatus.DONE)
        return "done"

    def _buy(self, conn, account: AccountState, session: date,
             intent: Intent, quotes: dict) -> str:
        """Devolve `'done'` / `'rejected'` / `'pending'` — ver `execute_session`."""
        # Defesa em profundidade: `close_and_decide` ja filtra ENTER quando o
        # disjuntor esta acionado, mas a intencao pode ter sido gravada ANTES
        # do disjuntor disparar (ex.: perda intra-dia entre a decisao de ontem
        # e a execucao de hoje). Checar de novo aqui garante que uma entrada
        # nunca sai enquanto a trava estiver ligada, custe o que custar.
        if self.risk_guard is not None and self.risk_guard.is_frozen:
            store.set_intent_status(conn, intent.id, IntentStatus.CANCELLED)
            self._log(conn, account.id, "warn", "riskguard",
                     f"entrada em {intent.ticker} vetada na execucao: {self.risk_guard.reason}")
            return "rejected"
        if not has_free_slot(len(account.positions), self.config):
            store.set_intent_status(conn, intent.id, IntentStatus.CANCELLED)
            self._log(conn, account.id, "warn", "runtime",
                            f"entrada em {intent.ticker} descartada: teto de "
                            f"{self.config.max_concurrent_positions} posicoes")
            return "rejected"
        quote = quotes.get(intent.ticker or "")
        if quote is None:
            store.set_intent_status(conn, intent.id, IntentStatus.REJECTED)
            self._log(conn, account.id, "error", "runtime",
                            f"entrada em {intent.ticker} sem cotacao — nao executada")
            return "rejected"

        # Mesma mecanica de dimensionamento do backtest (`backtest/sizing.py`).
        # Diferenca honesta: o backtest usa o open[D+1] como referencia; aqui a
        # referencia e o preco do momento do envio. Quanto mais perto da
        # abertura o supervisor rodar, menor a diferenca.
        plan = plan_entry(account.cash, quote.price, intent.size_hint, self.config)
        if not plan.is_feasible:
            store.set_intent_status(conn, intent.id, IntentStatus.CANCELLED)
            self._log(conn, account.id, "warn", "runtime",
                            f"entrada em {intent.ticker} inviavel: caixa "
                            f"{account.cash:.2f} nao cobre um lote")
            return "rejected"

        order = self._place(conn, account, intent, intent.ticker, OrderSide.BUY,
                            plan.quantity, note="entrada")
        return self._resolve_buy(conn, account, intent, order, session,
                                 fallback_price=plan.exec_price)

    def _resolve_buy(self, conn, account: AccountState, intent: Intent, order: Order,
                     entry_date: date, fallback_price: float) -> str:
        """Aplica o fill de uma compra ao estado da conta, se ja houver fill.

        `fallback_price`/`entry_date` cobrem o caso raro de `order.avg_price`
        vir vazio (nao deveria acontecer num fill real, mas o dado nao pode
        travar a contabilidade se vier faltando).
        """
        if order.status in (OrderStatus.REJECTED, OrderStatus.CANCELLED):
            store.set_intent_status(conn, intent.id, IntentStatus.REJECTED)
            return "rejected"
        if order.filled_qty <= 0:
            store.set_intent_status(conn, intent.id, IntentStatus.EXECUTING)
            self._log(conn, account.id, "info", "runtime",
                            f"entrada em {intent.ticker} aguardando confirmacao (ordem #{order.id})")
            return "pending"

        preco = order.avg_price or fallback_price
        custo = preco * order.filled_qty + order.fees
        account.cash -= custo
        pos = LivePosition(
            ticker=intent.ticker, quantity=order.filled_qty, entry_date=entry_date,
            entry_price=preco, capital_allocated=custo,
            current_stop=initial_stop(preco, intent.stop_price, self.config),
            fees_paid=order.fees, slippage_paid=order.slippage,
            max_price_seen=preco, min_price_seen=preco, bars_held=0,
        )
        store.upsert_position(conn, account.id, pos)
        account.positions[pos.ticker] = pos
        store.set_intent_status(conn, intent.id, IntentStatus.DONE)
        return "done"

    def _withdraw(self, conn, account: AccountState, session: date,
                  intent: Intent, quotes: dict) -> str:
        """Retira caixa do sistema: caixa primeiro, depois liquida a maior posicao.

        Espelha `_execute_withdrawal` do engine, incluindo o detalhe que custa
        dinheiro: quando o caixa nao cobre, vender para sacar paga corretagem e
        slippage normais. Se nem liquidando der, registra o `shortfall` em vez de
        inventar caixa — e a politica devolve a diferenca para a fila.

        Sob corretora AUTOMATICA (paper/MT5) o fill e sincrono: a liquidacao
        acontece toda dentro desta chamada, igual sempre foi. Sob corretora
        MANUAL, `place()` nunca preenche na hora — quem confirma e um humano,
        depois, via `ManualBroker.confirm()` + `reconcile_pending_fills`. Este
        metodo entao delega ao mesmo `_withdraw_manual_step` que a
        reconciliacao usa: manda UMA perna de liquidacao, deixa a intencao
        `EXECUTING` (nao `CANCELLED`) e devolve `'pending'`. Quando aquela
        perna confirmar, `reconcile_pending_fills` credita o fill e chama
        `_withdraw_manual_step` de novo — que decide se falta mais uma perna
        ou se ja da para fechar o saque. Ver docstring de `_withdraw_manual_step`
        para o raciocinio completo (inclusive por que so uma perna por vez).
        """
        want = float(intent.amount or 0.0)
        if want <= 0:
            store.set_intent_status(conn, intent.id, IntentStatus.CANCELLED)
            return "rejected"

        marks = {t: (quotes[t].price if t in quotes else m)
                 for t, m in self._marks(session).items()}
        equity_before = account.equity(marks)
        falta = want - account.cash

        if falta > 0 and account.positions:
            if not self.broker.supports_automation():
                price_ref = {t: q.price for t, q in quotes.items()}
                return self._withdraw_manual_step(conn, account, session, intent,
                                                   price_ref, equity_before)
            por_valor = sorted(account.positions.values(),
                               key=lambda p: p.market_value(marks.get(p.ticker, p.entry_price)),
                               reverse=True)
            for pos in por_valor:
                if falta <= 1e-9:
                    break
                quote = quotes.get(pos.ticker)
                if quote is None:
                    continue
                qty = liquidation_quantity(falta, quote.price, pos.quantity, self.config)
                if qty <= 0:
                    continue
                order = self._place(conn, account, intent, pos.ticker, OrderSide.SELL,
                                    qty, note="liquidacao para saque")
                if order.filled_qty <= 0:
                    continue
                liquido = self._apply_liquidation_fill(conn, account, pos, order)
                falta -= liquido

        return self._finish_withdrawal(conn, account, session, intent, want, equity_before)

    def _apply_liquidation_fill(self, conn, account: AccountState,
                                pos: LivePosition, order: Order) -> float:
        """Credita ao caixa o fill de UMA venda de liquidacao para saque e
        ajusta/remove a posicao. Devolve o liquido creditado.

        Compartilhado entre o laco sincrono de `_withdraw` (corretora
        automatica, fill na hora) e `reconcile_pending_fills` (fill de uma
        perna manual confirmado depois) — o efeito sobre caixa/posicao e o
        MESMO nos dois casos, so muda QUANDO ele acontece (mesma razao de
        `_resolve_sell` ser compartilhado entre `_sell` e a reconciliacao)."""
        liquido = (order.avg_price or 0.0) * order.filled_qty - order.fees
        account.cash += liquido
        if order.filled_qty >= pos.quantity:
            store.delete_position(conn, account.id, pos.ticker, pos.kind)
            account.positions.pop(pos.ticker, None)
        else:
            fora = order.filled_qty / pos.quantity
            pos.quantity -= order.filled_qty
            pos.capital_allocated *= (1.0 - fora)
            store.upsert_position(conn, account.id, pos)
        return liquido

    def _withdraw_manual_step(self, conn, account: AccountState, session: date,
                              intent: Intent, price_ref: dict[str, float],
                              equity_before: float) -> str:
        """Um passo (uma perna) da liquidacao de saque sob corretora MANUAL.

        Por que so UMA perna por vez, em vez de calcular de saida todas as
        vendas necessarias e mandar todas como ticket: confirmar um fill
        manual e um HUMANO indo na corretora de verdade depois — mandar N
        ordens de uma vez seria pedir para ele vender N posicoes so porque a
        conta fechou assim ANTES de saber se a primeira ja bastou (o preco
        real pode vir melhor ou pior que a cotacao de referencia). Enviar uma
        de cada vez e mais devagar mas nunca pede confirmacao de venda que
        pode nao ser necessaria.

        Fluxo: acha a maior posicao com preco de referencia disponivel, manda
        UMA ordem de venda dimensionada para o que falta, grava `equity_before`
        no `payload` da intent (unico jeito de o valor sobreviver entre esta
        chamada — ao executar a saida — e a chamada futura de
        `reconcile_pending_fills`, que pode acontecer dias depois, num
        processo novo) e deixa a intencao `EXECUTING`. Quando chamado de novo
        (pela reconciliacao, apos um fill ja creditado ao caixa) recalcula
        `falta` do zero a partir do caixa ATUAL — se ja cobre, fecha; senao
        busca a proxima posicao. Termina fechando com o que houver (mesmo
        aquem do pedido, shortfall registrado por `_finish_withdrawal`) se
        nao sobrar posicao vendavel (sem preco de referencia ou sem lote).
        """
        want = float(intent.amount or 0.0)
        falta = want - account.cash
        if falta <= 1e-9 or not account.positions:
            return self._finish_withdrawal(conn, account, session, intent, want, equity_before)

        por_valor = sorted(account.positions.values(),
                           key=lambda p: p.market_value(price_ref.get(p.ticker, p.entry_price)),
                           reverse=True)
        for pos in por_valor:
            price = price_ref.get(pos.ticker)
            if price is None:
                continue
            qty = liquidation_quantity(falta, price, pos.quantity, self.config)
            if qty <= 0:
                continue
            order = self._place(conn, account, intent, pos.ticker, OrderSide.SELL,
                                qty, note="liquidacao para saque")
            store.set_intent_payload(conn, intent.id, {"equity_before": equity_before})
            if order.filled_qty <= 0:
                store.set_intent_status(conn, intent.id, IntentStatus.EXECUTING)
                self._log(conn, account.id, "info", "runtime",
                                f"saque de {want:.2f} precisa liquidar posicao e a corretora "
                                f"e manual — venda de {qty} {pos.ticker} enviada "
                                f"(ordem #{order.id}), aguardando confirmacao")
                return "pending"
            # Defensivo: o `ManualBroker` de hoje nunca fecha na hora (so um
            # humano confirma depois), mas se algum dia existir uma variante
            # que as vezes preenche sincrono, o fluxo tem que continuar
            # tentando cobrir `falta` em vez de parar cedo demais.
            self._apply_liquidation_fill(conn, account, pos, order)
            return self._withdraw_manual_step(conn, account, session, intent,
                                              price_ref, equity_before)

        # Nenhuma posicao restante tem preco de referencia ou lote vendavel
        # agora: mesma filosofia do caminho automatico (que tambem so pula
        # tickers sem cotacao e fecha com o caixa que conseguiu reunir) — nao
        # e um erro, fecha com o que ha, mesmo que fique aquem do pedido.
        return self._finish_withdrawal(conn, account, session, intent, want, equity_before)

    def _finish_withdrawal(self, conn, account: AccountState, session: date,
                           intent: Intent, want: float, equity_before: float) -> str:
        """Fecha a intencao de saque: move o caixa disponivel (ate `want`) para
        caixa externo e registra a auditoria.

        `taxas`/`liquidado` vem das ORDENS da intencao (`orders_for_intent`),
        nao de um acumulador em memoria passado de chamada em chamada — uma
        liquidacao manual pode se estender por varias rodadas de
        `reconcile_pending_fills`, em processos diferentes; reconstruir da
        fonte e mais robusto do que carregar estado entre elas. Usada tanto
        pelo caminho sincrono (`_withdraw`, tudo numa chamada so) quanto pelo
        fim de uma liquidacao manual resolvida por `_withdraw_manual_step` —
        os dois caminhos terminam na MESMA contabilidade, so em momentos
        diferentes.
        """
        ordens = store.orders_for_intent(conn, intent.id)
        preenchidas = [o for o in ordens if o.filled_qty > 0]
        taxas = float(sum(o.fees for o in preenchidas))
        liquidado = [[o.ticker, o.filled_qty, o.avg_price] for o in preenchidas]

        executado = max(0.0, min(want, account.cash))
        account.cash -= executado
        account.external_cash += executado
        account.withdrawn_total += executado
        store.record_withdrawal(conn, account.id, session, want, executado,
                                equity_before, taxas, liquidado)
        # A politica precisa saber quanto SAIU de fato: se saiu menos, a
        # diferenca volta para a fila do minimo em vez de desaparecer.
        self.withdrawal.on_executed(intent, executado)
        store.set_intent_status(conn, intent.id, IntentStatus.DONE)
        if executado < want:
            self._log(conn, account.id, "warn", "runtime",
                            f"saque parcial: pedido {want:.2f}, saiu {executado:.2f}")
        return "done" if executado > 0 else "rejected"

    # ---------- reconciliacao (fills que chegaram depois) ------------------

    def reconcile_pending_fills(self, now: Optional[datetime] = None) -> StepReport:
        """Aplica ao estado da conta qualquer ordem `EXECUTING` que se resolveu.

        Existe por causa da corretora MANUAL: `place()` la nao preenche nada —
        so um humano sabe o preco real, via `ManualBroker.confirm()`, chamado
        de outro processo (`scripts/run_live.py confirm`) em outro momento. Sem
        este passo, o fill confirmado ficaria escrito na `Order` mas NUNCA
        chegaria a `AccountState` (caixa, posicao) — dinheiro perdido no
        diario. Seguro chamar a qualquer momento: so existe intencao
        `EXECUTING` quando ha mesmo algo pendente.

        ENTER/EXIT geram exatamente um `Order` por `Intent`, entao olhar so o
        ultimo (`orders[-1]`) basta. WITHDRAW e diferente: uma liquidacao sob
        corretora manual pode precisar de VARIAS pernas (uma posicao nao
        cobre o saque inteiro), enviadas uma de cada vez por
        `_withdraw_manual_step` — `orders[-1]` ainda e a perna relevante (a
        mais recente), mas resolver o fill dela nao fecha a intencao sozinho:
        credita o caixa e chama `_withdraw_manual_step` de novo, que decide
        se falta mais uma perna (manda outra ordem, intent continua
        `EXECUTING`) ou se ja da para fechar (`_finish_withdrawal`, intent
        vira `DONE`).
        """
        now = now or datetime.now(timezone.utc)
        aplicadas = 0
        with store.live_journal(self.db_path) as conn:
            account = store.load_account(conn, self.account_name)
            if account is None:
                return StepReport("reconcile_skip", detail={"motivo": "conta inexistente"})
            for intent in store.intents_by_status(conn, account.id, IntentStatus.EXECUTING):
                orders = store.orders_for_intent(conn, intent.id)
                if not orders:
                    continue
                order = orders[-1]
                self.broker.poll(order)
                store.update_order(conn, order)
                if order.filled_qty <= 0 and not order.is_terminal:
                    continue  # ainda aguardando confirmacao

                if intent.kind == IntentKind.EXIT:
                    pos = account.positions.get(intent.ticker or "")
                    resultado = (self._resolve_sell(conn, account, intent, pos, order)
                                if pos is not None else "rejected")
                elif intent.kind == IntentKind.ENTER:
                    resultado = self._resolve_buy(conn, account, intent, order,
                                                  now.date(), order.avg_price or 0.0)
                elif intent.kind == IntentKind.WITHDRAW:
                    if order.filled_qty > 0:
                        pos = account.positions.get(order.ticker)
                        if pos is not None:
                            self._apply_liquidation_fill(conn, account, pos, order)
                    # `clock.session_date(now)` ja devolve o ultimo pregao
                    # FECHADO (ver docstring da funcao) — igual `status()`,
                    # carrega ate ele mesmo (nao ate o anterior: nao ha "dia
                    # ainda em curso" aqui como em `execute_session`, so o
                    # ultimo fecho disponivel para servir de preco de
                    # referencia da proxima perna, se houver).
                    ref_session = clock.session_date(now)
                    self._load(ref_session)
                    price_ref = self._marks(ref_session)
                    equity_before = (intent.payload or {}).get("equity_before")
                    if equity_before is None:
                        # Nao deveria faltar (gravado por `_withdraw_manual_step`
                        # antes da primeira perna) — cai para o equity atual em
                        # vez de travar a reconciliacao se o payload sumir.
                        equity_before = account.equity(price_ref)
                    resultado = self._withdraw_manual_step(conn, account, now.date(), intent,
                                                           price_ref, equity_before)
                else:
                    resultado = "rejected"
                    store.set_intent_status(conn, intent.id, IntentStatus.REJECTED)
                if resultado == "done":
                    aplicadas += 1
            account.policy_state = self._robot_state()
            store.save_account(conn, account)
        return StepReport("reconcile", detail={"aplicadas": aplicadas})

    # ---------- deposito externo (aporte) -----------------------------------

    def _apply_deposit(self, conn, account: AccountState, session: date,
                       amount: float, origin: str, note: str = "") -> None:
        """Credita um deposito externo ao caixa da conta e registra a
        auditoria — o nucleo compartilhado pelos dois caminhos de aporte:
        `reconcile_broker_cash` (deteccao automatica via MT5) chama isto
        direto; o botao manual do dashboard (`/operacao/aportar`, ver
        `dashboard/app.py`) replica os MESMOS tres passos (soma ao caixa,
        salva conta, grava `live_deposits`) sem passar por aqui, porque
        instanciar um `LiveRuntime` inteiro (estrategia/feed/corretora) so
        para somar um valor ao caixa seria peso desnecessario para uma
        rota que nao decide nada. `store.record_deposit` e o formato de
        dado compartilhado de verdade entre os dois caminhos.

        Loga e notifica no mesmo ponto (via `self._log`) — o botao manual
        nao precisa disso (e um clique explicito do proprio dono, ele ja
        sabe que aconteceu), so o caminho automatico, que roda sozinho sem
        ninguem olhando.
        """
        account.cash += amount
        store.save_account(conn, account)
        store.record_deposit(conn, account.id, session, amount, origin, note)
        self._log(conn, account.id, "info", "runtime",
                        f"deposito detectado: +R$ {amount:.2f} ({origin})",
                        {"origin": origin, "valor": round(amount, 2)})

    def reconcile_broker_cash(self, now: Optional[datetime] = None) -> StepReport:
        """Compara o saldo real da corretora (`Broker.cash_balance()`) contra
        `AccountState.cash` uma vez antes da abertura, para detectar um
        aporte feito fora deste sistema (o dono depositou direto na
        corretora). Ver `_apply_deposit` para o credito em si.

        So age quando a corretora sabe responder isso: `cash_balance()`
        default e `None` (Paper/Manual, sem conta real para comparar) e este
        metodo vira no-op silencioso — sem log, senao spamaria `live_events`
        todo santo dia, para toda conta paper/manual, com um evento que nao
        diz nada de novo.

        Diferenca NEGATIVA (saldo real abaixo do esperado) NUNCA ajusta caixa
        sozinho — pode ser uma taxa que o sistema nao conhece ou uma venda
        manual direto na corretora, e o escopo pedido e so sobre deposito
        que FAZ a conta crescer. So loga como aviso, para o dono investigar.
        """
        real_balance = self.broker.cash_balance()
        if real_balance is None:
            return StepReport("reconcile_cash_skip", detail={"motivo": "corretora sem saldo externo"})

        now = now or datetime.now(timezone.utc)
        session = now.date()
        with store.live_journal(self.db_path) as conn:
            account = store.load_account(conn, self.account_name)
            if account is None:
                return StepReport("reconcile_cash_skip", detail={"motivo": "conta inexistente"})

            diff = real_balance - account.cash
            if diff > _DEPOSIT_TOLERANCE:
                note = f"saldo real {real_balance:.2f} vs caixa esperado {account.cash:.2f}"
                self._apply_deposit(conn, account, session, diff,
                                    origin="mt5_reconciliation", note=note)
                return StepReport("reconcile_cash", detail={"deposito": round(diff, 2)})
            if diff < -_DEPOSIT_TOLERANCE:
                self._log(conn, account.id, "warn", "runtime",
                                f"caixa da corretora (R$ {real_balance:.2f}) abaixo do "
                                f"esperado (R$ {account.cash:.2f}) — diferenca nao "
                                "explicada, nenhum ajuste automatico",
                                {"diferenca": round(diff, 2)})
                return StepReport("reconcile_cash", detail={"diferenca": round(diff, 2)})
            return StepReport("reconcile_cash", detail={"diferenca": round(diff, 2)})

    # ---------- intra-dia --------------------------------------------------

    def intraday_tick(self, session: date, now: Optional[datetime] = None) -> StepReport:
        """Acompanha preco e dispara stop. Nao toma nenhuma decisao propria."""
        now = now or datetime.now(timezone.utc)
        quotes = self.feed.quotes(self.tickers)
        velhas = staleness_report(quotes, now, self.max_quote_age)

        with store.live_journal(self.db_path) as conn:
            account = store.load_account(conn, self.account_name)
            if account is None:
                return StepReport("intraday_skip", session, detail={"motivo": "conta inexistente"})

            if velhas:
                # Nao aborta: registra. Um stop sobre dado atrasado dispara no
                # lugar errado, e isso tem de estar no log operacional para o
                # trade ser explicavel depois — nao descoberto no extrato.
                self._log(conn, account.id, "warn", "feed",
                                f"cotacao atrasada ({self.feed.name}): " +
                                ", ".join(f"{t} {int(a)}s" for t, a in velhas.items()))

            for pos in account.positions.values():
                q = quotes.get(pos.ticker)
                if q is None:
                    continue
                pos.max_price_seen = max(pos.max_price_seen or q.price, q.price)
                pos.min_price_seen = min(pos.min_price_seen or q.price, q.price)
                store.upsert_position(conn, account.id, pos)

            ctx = self._context(session, account, SessionPhase.OPEN, quotes)
            disparados = 0
            for intent in self.investment.on_intraday(ctx):
                store.record_intent(conn, account.id, intent)
                if self._sell(conn, account, session, intent, quotes) == "done":
                    disparados += 1
                    self._log(conn, account.id, "warn", "runtime",
                                    f"stop disparado em {intent.ticker} "
                                    f"(feed {self.feed.name}, atraso {self.feed.delay_seconds:.0f}s)")
            store.save_account(conn, account)

        return StepReport("intraday", session, phase=SessionPhase.OPEN,
                          detail={"stops": disparados, "cotacoes": len(quotes),
                                  "atrasadas": len(velhas)})

    # ---------- supervisao -------------------------------------------------

    def run_once(self, now: Optional[datetime] = None) -> list[StepReport]:
        """Um passo do supervisor. Seguro para chamar em loop, a qualquer hora."""
        now = now or datetime.now(timezone.utc)
        fase = clock.phase(now)
        hoje = now.date()
        passos: list[StepReport] = []

        # Reconciliar primeiro, em toda fase: uma confirmacao manual pode ter
        # chegado a qualquer momento (fora do horario de pregao inclusive), e
        # aplicar o fill ao caixa/posicao nao depende de estar no pregao.
        reconciliado = self.reconcile_pending_fills(now)
        if reconciliado.detail.get("aplicadas"):
            passos.append(reconciliado)

        if fase == SessionPhase.OPEN:
            if clock.is_trading_day(hoje):
                passos.append(self.execute_session(hoje))
                passos.append(self.intraday_tick(hoje, now))
        elif fase in (SessionPhase.AFTER_HOURS, SessionPhase.POST_CLOSE):
            if clock.is_trading_day(hoje):
                if self._sync_due(now):
                    passos.append(self.sync_data())
                    self._last_sync_at = now
                passos.append(self.close_and_decide(hoje))
        elif fase == SessionPhase.PRE_OPEN:
            if clock.is_trading_day(hoje):
                passos.append(self.reconcile_broker_cash(now))
        else:
            passos.append(StepReport("idle", clock.session_date(now), phase=fase))
        return passos

    def status(self) -> dict:
        """Retrato da conta para o dashboard e para a linha de comando.

        Checa a EXISTENCIA da conta antes de carregar qualquer dado: sem
        conta nao ha nada util a mostrar, e carregar o universo inteiro
        (`_load`) so para descobrir isso e caro — pago por engano em todo
        poll de uma pagina que ainda mostraria "nao configurado".
        """
        session = clock.session_date()
        with store.live_journal(self.db_path) as conn:
            account = store.load_account(conn, self.account_name)
            if account is None:
                return {"conta": self.account_name, "existe": False}

        self._load(session)
        marks = self._marks(session)
        # Popula `feed.delay_seconds` com uma leitura real antes de reportar —
        # `ParquetCloseFeed` comeca em 0.0 ate a primeira chamada de `quotes`
        # (ver docstring da classe), e reportar isso sem ter perguntado nada
        # ao feed passaria uma falsa sensacao de frescor.
        self.feed.quotes(self.tickers)
        with store.live_journal(self.db_path) as conn:
            account = store.load_account(conn, self.account_name)
            if account is None:
                return {"conta": self.account_name, "existe": False}
            self._restore_robot_state(account.policy_state)
            pend = store.pending_intents(conn, account.id, clock.next_session(session))
            eventos = store.recent_events(conn, account.id, limit=10)
        return {
            "conta": account.name,
            "existe": True,
            "modo": account.mode,
            "robo_investimento": account.investment_robot,
            "robo_saque": account.withdrawal_robot,
            "pregao": session.isoformat(),
            "fase": clock.phase().value,
            "feed": {"nome": self.feed.name, "tempo_real": self.feed.is_realtime,
                     "atraso_s": self.feed.delay_seconds},
            "corretora": {"nome": self.broker.name, "modo": self.broker.mode,
                          "automatica": self.broker.supports_automation()},
            "disjuntor": ({"acionado": self.risk_guard.is_frozen, "motivo": self.risk_guard.reason}
                         if self.risk_guard is not None else None),
            "caixa": round(account.cash, 2),
            "investido": round(account.invested(marks), 2),
            "carteira": round(account.equity(marks), 2),
            "caixa_externo": round(account.external_cash, 2),
            "patrimonio": round(account.patrimonio(marks), 2),
            "sacado_total": round(account.withdrawn_total, 2),
            "posicoes": [
                {"ticker": p.ticker, "qtd": p.quantity, "entrada": round(p.entry_price, 2),
                 "stop": round(p.current_stop, 2) if p.current_stop else None,
                 "barras": p.bars_held,
                 "valor": round(p.market_value(marks.get(p.ticker, p.entry_price)), 2)}
                for p in account.positions.values()
            ],
            "intencoes_pendentes": [
                {"robo": i.robot, "tipo": i.kind.value, "ticker": i.ticker,
                 "motivo": i.reason, "valor": i.amount, "executa_em": i.execute_on.isoformat()}
                for i in pend
            ],
            "eventos": eventos,
        }
