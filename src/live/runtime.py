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
    2. expira recomendacao de saque vencida (virada de mes civil)
    3. politica de saque decide  -> recomendacao para D+1 (nunca executada
       pela maquina — so confirmacao humana move o caixa)
    4. estrategia decide          -> intencoes para D+1
    5. `bars_held += 1`

  ABERTURA de D+1 (`execute_session`)
    1. expira intencao atrasada (execute_on < hoje) — nunca executa velho
    2. expira recomendacao de saque vencida (virada de mes civil)
    3. saidas (rotacao, defensiva)
    4. recomendacao de saque por evento de liquidez, se alguma venda
       creditou caixa hoje — so registra + notifica, nunca executa
    5. entradas, dimensionadas pelo caixa (saque NUNCA e debitado aqui —
       recomendacao de saque e so notificacao, o dono saca direto na
       corretora se quiser; ver `reconcile_broker_cash`)

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
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from backtest.sizing import has_free_slot, initial_stop, plan_entry
# `LIVE_DB_PATH as DB_PATH`: o NOME do atributo de módulo permanece `DB_PATH`
# de propósito (FEAT-000, ver ACTION-PLAN — premissa 4) — `tests/test_dashboard_app.py`
# faz `monkeypatch.setattr(live_runtime, "DB_PATH", tmp)` e depende desse nome
# continuar existindo aqui. O VALOR, porém, passa a ser o banco separado da
# operação real (antes era o mesmo arquivo do backtest).
from core.config import BENCHMARK, LIVE_DB_PATH as DB_PATH, WATCHLIST, BacktestConfig
from core.market_features import enrich_features, snapshot_from_row
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

def _falha_snapshot(conn, account_id: Optional[int], intent_id: int, msg: str) -> None:
    """Registra falha de SNAPSHOT no diario — e nao notifica, de proposito.

    Excecao consciente a `Runtime._log` (que grava e notifica sempre juntos,
    ver a docstring dele): aqui a decisao do robo e a ordem na corretora
    seguiram normais, e o que falhou foi so a anotacao do contexto. Mandar
    isso para o Telegram do dono trataria um problema de qualidade de diario
    como incidente operacional — e alerta que chega sem exigir acao e
    exatamente o que faz o dono parar de ler os alertas que exigem. Fica no
    `live_events` (nivel `warn`), onde uma auditoria encontra, e onde uma
    ocorrencia repetida aparece como padrao em vez de como 40 notificacoes.
    """
    store.log_event(conn, account_id, "warn", "diario", msg, {"intent_id": intent_id})


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
        # Item 0.3 herdado de FEAT-000 (só possível agora que `PaperBroker`
        # saiu de produção, FEAT-001): um broker de TESTE nunca pode operar
        # sobre o banco de produção. Comparação por caminho RESOLVIDO (nunca
        # `==` cru) — senão bastaria passar o mesmo arquivo como string
        # relativa para driblar a guarda (mesmo precedente de
        # `scripts/run_live_sim.py::_ensure_disposable_sim_db`). `DB_PATH` é
        # lido do MÓDULO em tempo de chamada (não capturado em import-time),
        # porque o monkeypatch de teste depende disso.
        if getattr(broker, "is_test_double", False):
            # `DB_PATH` é lido como nome de MÓDULO (não capturado antes) —
            # mesmo mecanismo de `self.db_path` acima — para o monkeypatch de
            # teste (`monkeypatch.setattr(live_runtime, "DB_PATH", tmp)`) valer.
            producao = Path(DB_PATH).resolve()
            if Path(self.db_path).resolve() == producao:
                raise ValueError(
                    f"broker de teste ({type(broker).__name__}, is_test_double=True) "
                    f"não pode operar sobre o banco de produção ({producao}) — "
                    "aponte para um banco descartável (tmp_path/simulação)."
                )
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
        # ticker -> painel enriquecido com indicadores, para o snapshot de
        # contexto gravado junto de cada intencao (ver `_record_intent`).
        # Invalidado sempre que os paineis sao remontados, logo abaixo.
        self._enriched_cache: dict[str, Optional[pd.DataFrame]] = {}
        # Marcador de dedupe do skip por dado incompleto (achado E2,
        # FEAT-003): guarda o ultimo `{"session": ..., "faltando": [...]}`
        # notificado, para `close_and_decide` nao repetir o mesmo alerta a
        # cada chamada de `run_once` (a cada minuto). Persistido em
        # `policy_state["skip_avisado"]` para sobreviver a um restart.
        self._skip_avisado: Optional[dict] = None
        # Dedupe do warn "disjuntor nao observou o tick: sem base do fecho
        # anterior" (mitigacao obrigatoria do passo 8, ver ACTION-PLAN §5):
        # sem isso, um mes inteiro sem `close_and_decide` bem-sucedido faria
        # `intraday_tick` logar/notificar esse warn A CADA CHAMADA de
        # `run_once` (a cada minuto) -- reintroduziria o achado E2 por outra
        # porta. So em memoria (nao persistido): o pior caso de um restart
        # no meio do dia e um warn extra, nao uma inundacao.
        self._risk_sem_base_avisado: Optional[date] = None
        # Aviso "conta de dinheiro real sem canal de notificacao" (achado
        # E7): uma vez por PROCESSO (nao persistido, nao por sessao) --
        # senao repetiria em todo `close_and_decide` de uma conta mt5 sem
        # `notifier` configurado.
        self._null_notifier_warned: bool = False

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
        """Reidrata a politica de saque, o circuit breaker e a estrategia de
        investimento a partir do `policy_state` da conta (JSON aninhado:
        `{"withdrawal": ..., "risk_guard": ..., "investment": {"robot": ...,
        "state": ...}, "skip_avisado": ...}`).

        Aninhado (em vez de gravar so o estado da politica direto, como era
        antes do circuit breaker existir) porque agora sao objetos
        DIFERENTES com estado proprio dividindo a mesma coluna — sem o
        aninhamento, um sobrescreveria o outro.

        O bloco `"investment"` (FEAT-003, item 3.2) carrega o CARIMBO do
        robo que gravou aquele estado (`self.investment.key`, achado C4) —
        se divergir do robo atual, o estado e DESCARTADO silenciosamente
        (nao ha `conn` aqui para logar, e o caminho e so leitura): sem o
        carimbo, trocar de estrategia (ou reapontar a conta por engano)
        importaria o `_pending_rebalance` de um robo completamente
        diferente."""
        if not policy_state:
            return
        self.withdrawal.restore(policy_state.get("withdrawal") or {})
        if self.risk_guard is not None:
            self.risk_guard.restore(policy_state.get("risk_guard") or {})
        bloco = policy_state.get("investment") or {}
        robo_gravado = bloco.get("robot")
        if robo_gravado is None or robo_gravado == self.investment.key:
            self.investment.restore(bloco.get("state") or {})
        self._skip_avisado = policy_state.get("skip_avisado")

    def _robot_state(self) -> dict:
        """Inverso de `_restore_robot_state` — o que persistir em `policy_state`."""
        return {
            "withdrawal": self.withdrawal.state(),
            "risk_guard": self.risk_guard.state() if self.risk_guard is not None else {},
            "investment": {"robot": self.investment.key, "state": self.investment.state()},
            "skip_avisado": self._skip_avisado,
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
        # Painel novo => indicadores recalculados. Limpar aqui (e nao
        # deixar expirar por conta) e o que garante que o snapshot gravado
        # descreve o MESMO dado que o robo acabou de receber em `prepare`.
        self._enriched_cache = {}
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

    # ---------- snapshot de contexto (o "por que") ------------------------

    def _enriched(self, ticker: str):
        """Painel do ticker com as colunas de indicador, com cache por sessao.

        O cache existe porque uma sessao grava varias intencoes e mais de uma
        pode ser do mesmo ticker (saida + entrada numa rotacao): enriquecer
        200+ pregoes duas vezes para gravar a mesma leitura e desperdicio puro.
        Invalidado em `_refresh_panels` — dado novo, painel novo.
        """
        if ticker in self._enriched_cache:
            return self._enriched_cache[ticker]
        df = self._panels.get(ticker)
        if df is None or self._ibov is None or df.empty:
            self._enriched_cache[ticker] = None
            return None
        try:
            out = enrich_features(df, self._ibov)
        except Exception:
            # Registro nunca derruba decisao: um painel malformado (coluna
            # faltando, indice torto) faz o snapshot faltar, nao a intencao.
            out = None
        self._enriched_cache[ticker] = out
        return out

    def _record_intent(self, conn, account: AccountState, intent: Intent) -> int:
        """Grava a intencao E o contexto de mercado que a motivou.

        Ponto UNICO de gravacao de intencao do runtime, de proposito: os tres
        caminhos que decidem (fecho, entrada intra-dia e stop intra-dia)
        passam por aqui, entao nao existe caminho que registre uma decisao sem
        registrar o que o robo estava vendo quando a tomou. Antes disto o
        diario respondia "o que foi feito" e "por que VENDEU", mas nao "por
        que COMPROU este papel neste dia" — ver `live_signal_snapshots` no
        schema.

        Anti-look-ahead: o snapshot e lido da linha de `intent.decided_on` (o
        fecho que gerou a decisao), NUNCA da ultima linha do painel. Se o
        painel ja avancou (a gravacao acontece depois, e o processo pode ter
        cruzado a virada do pregao), pegar `iloc[-1]` gravaria um contexto que
        o robo nao viu — uma mentira de auditoria exatamente do tipo que a
        regra 4 do AGENTS.md proibe. Sem a linha exata, o snapshot fica de
        fora e a intencao e gravada mesmo assim.
        """
        intent_id = store.record_intent(conn, account.id, intent)
        momento = {IntentKind.ENTER: "entry", IntentKind.EXIT: "exit"}.get(intent.kind)
        if momento is None or not intent.ticker:
            # ADJUST_STOP nao move dinheiro e WITHDRAW nao e sobre um papel —
            # nenhum dos dois tem "contexto de sinal" a registrar.
            return intent_id
        e = self._enriched(intent.ticker)
        if e is None:
            return intent_id
        try:
            idx = pd.Timestamp(intent.decided_on)
            if idx not in e.index:
                _falha_snapshot(
                    conn, account.id, intent_id,
                    f"sem snapshot de contexto para {intent.ticker}: pregao "
                    f"{intent.decided_on.isoformat()} nao esta no painel")
                return intent_id
            snap = snapshot_from_row(e.loc[idx])
            store.record_intent_snapshot(conn, intent_id, momento, intent.ticker, snap)
        except Exception as exc:
            # Mesma regra do `except` de `_enriched`, com registro: perder o
            # snapshot e ruim, perder a intencao e inaceitavel.
            _falha_snapshot(conn, account.id, intent_id,
                            f"falha ao gravar snapshot de {intent.ticker}: {exc}")
        return intent_id

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

    def _load_account(self, conn) -> Optional[AccountState]:
        """`store.load_account`, mas recusando operar quando o modo real da
        conta diverge do modo do broker instanciado neste `LiveRuntime`.

        Devolve `None` quando a conta não existe (preserva o skip limpo que
        os 8 call-sites abaixo dependem: "conta inexistente" não é erro, é
        estado inicial) — só levanta `ValueError` quando a conta EXISTE e o
        modo dela é diferente de `self.broker.mode` (duas instâncias de
        `LiveRuntime`, brokers diferentes, mesmo banco/conta — nunca podem
        operar juntas)."""
        account = store.load_account(conn, self.account_name)
        if account is None:
            return None
        if account.mode != self.broker.mode:
            raise ValueError(
                f"conta '{self.account_name}' está em modo {account.mode!r}, "
                f"mas este LiveRuntime foi instanciado com um broker de modo "
                f"{self.broker.mode!r} — uma conta e um broker divergentes "
                "nunca podem operar juntos."
            )
        return account

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

        RE-ANCORA as bases do disjuntor no patrimonio corrente (item F2,
        FEAT-003): sem isso, com o disjuntor agora observado a cada minuto
        (`intraday_tick`), o PROXIMO tick recalcularia a MESMA perda contra
        a MESMA base antiga e recongelaria em segundos — o botao de panico
        viraria inoperante durante o pregao. O calculo do patrimonio
        corrente (paineis + cotacao intra-dia) e melhor-esforco: se painel
        ou feed falharem, destrava sem re-ancorar (comportamento antigo) e
        avisa que a trava pode voltar no proximo tick, em vez de abortar o
        destravamento inteiro por uma falha de leitura de dado.

        ATENCAO a duas datas DIFERENTES aqui (correcao pos-review, tentativa
        1): `sessao_dado = clock.session_date()` serve SO para carregar/marcar
        dados (`_load`, `_intraday_marks`) — na fase OPEN do pregao ela
        devolve o pregao ANTERIOR, por design do clock. Ja o argumento de
        `risk_guard.unfreeze(hoje, ...)` usa `hoje = datetime.now(timezone.utc).date()`,
        a MESMA expressao que `run_once` usa para chamar `intraday_tick(hoje, ...)`.
        Se as duas datas fossem a mesma (`sessao_dado` para as duas coisas), o
        disjuntor seria re-ancorado no dia ANTERIOR; no tick seguinte,
        `_observe_risk` veria "dia novo" (hoje != dia ancorado) e re-ancoraria
        sozinho no patrimonio do fecho anterior — que le como perda grande
        contra o patrimonio real de hoje, recongelando em menos de um minuto.
        Ou seja: exatamente o bug que este metodo existe para consertar.
        """
        if self.risk_guard is None:
            return
        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return
            self._restore_robot_state(account.policy_state)
            sessao_dado = clock.session_date()
            hoje = datetime.now(timezone.utc).date()
            try:
                self._load(sessao_dado)
                quotes = self.feed.quotes(self.tickers)
                stale = staleness_report(quotes, datetime.now(timezone.utc), self.max_quote_age)
                marks = self._intraday_marks(sessao_dado, quotes, stale=stale)
                patrimonio = account.patrimonio(marks)
                self.risk_guard.unfreeze(hoje, patrimonio)
            except Exception as exc:
                self.risk_guard.unfreeze()
                self._log(conn, account.id, "warn", "riskguard",
                                f"destravado sem re-ancorar: {exc} — a trava pode "
                                "voltar no proximo tick")
            account.policy_state = self._robot_state()
            store.save_account(conn, account)
            self._log(conn, account.id, "info", "riskguard", "disjuntor destravado manualmente")

    # ---------- disjuntor: base do dia -------------------------------------

    def _previous_close_patrimonio(self, conn, account_id: int, session: date) -> Optional[float]:
        """Patrimonio do FECHO ANTERIOR a `session` — a base de comparacao
        correta do disjuntor diario (item 3.1: usar o patrimonio do proprio
        `session` como base faz a perda do dia ser sempre 0%, porque a base
        e fixada no mesmo `observe()` que a compara).

        So aceita a linha se a data for EXATAMENTE `clock.previous_session(session)`
        e o valor for `> 0` (achados A2/A4): uma linha de dias atras (processo
        fora do ar, ou pregoes pulados por dado incompleto) transformaria
        deriva normal em "perda do dia"; uma base `<= 0` faria
        `CircuitBreaker.observe` pular a avaliacao de perda NAS DUAS travas
        em silencio (`riskguard.py`, guarda `_daily_ref_equity > 0`)."""
        anterior = clock.previous_session(session)
        row = store.last_equity(conn, account_id, anterior.isoformat())
        if row is None:
            return None
        data, _equity, patrimonio = row
        if data != anterior.isoformat() or patrimonio <= 0:
            return None
        return float(patrimonio)

    def _intraday_marks(self, session: date, quotes: dict, stale=()) -> dict[str, float]:
        """`_marks(session)` sobrescrito pela cotacao intra-dia, descartando
        as cotacoes que `staleness_report` ja apontou como velhas (achado B2):
        uma cotacao velha/absurda nao pode alimentar o disjuntor mensal, que
        exige revisao humana para destravar."""
        marks = dict(self._marks(session))
        velhas = set(stale)
        marks.update({t: q.price for t, q in quotes.items() if t not in velhas})
        return marks

    def _observe_risk(self, conn, account: AccountState, session: date,
                      patrimonio: float, *, may_anchor: bool) -> None:
        """Alimenta `risk_guard.observe()` com a base correta (achados 3.1,
        A2, A4, F1).

        `may_anchor=True` (caminho de FECHO, `close_and_decide`): se houver
        uma base confiavel do fecho anterior, observa ela PRIMEIRO (fixa/
        confirma a base do dia/mes) e so depois o patrimonio corrente — as
        duas chamadas no mesmo dia sao seguras porque a segunda so compara
        contra a base ja fixada pela primeira (ver `CircuitBreaker.observe`).
        Sem base confiavel, cai no comportamento antigo (observa so o
        patrimonio corrente — nao ideal, mas nao desliga a trava).

        `may_anchor=False` (caminho INTRA-DIA, `intraday_tick`): NUNCA cria
        a âncora do dia/mes a partir de uma leitura intra-dia (achado F1) —
        `run_once` roda OPEN antes de POST_CLOSE, entao no 1o pregao de um
        mes novo um tick poderia ser o PRIMEIRO `observe()` do mes; se a base
        nao for confiavel aqui, o tick simplesmente NAO observa (fica sem
        proteção intra-dia neste dia especifico, mas nunca ancora errado o
        mes inteiro)."""
        if self.risk_guard is None:
            return
        base = self._previous_close_patrimonio(conn, account.id, session)
        if base is not None:
            self.risk_guard.observe(session, base)
            self.risk_guard.observe(session, patrimonio)
        elif may_anchor:
            self.risk_guard.observe(session, patrimonio)
            self._log(conn, account.id, "warn", "riskguard",
                            "disjuntor sem base do fecho anterior — usando patrimonio do dia")
        elif self._risk_sem_base_avisado != session:
            # dedupe por sessao (mitigacao obrigatoria, ver ACTION-PLAN §5,
            # "riscos ATIVOS" do passo 8) -- sem isso, um mes inteiro sem
            # `close_and_decide` bem-sucedido inundaria o canal de alerta a
            # cada tick, reintroduzindo o achado E2 por outra porta.
            self._risk_sem_base_avisado = session
            self._log(conn, account.id, "warn", "riskguard",
                            "disjuntor nao observou o tick: sem base do fecho anterior")

    # ---------- fecho: os robos decidem -----------------------------------

    def close_and_decide(self, session: date) -> StepReport:
        """Marca a carteira no fecho de `session` e colhe as decisoes dos robos.

        Ordem identica ao engine: equity -> expira saque vencido -> saque ->
        estrategia -> bars_held. A expiracao roda ANTES de `withdrawal.on_close`
        de proposito (ver `_expire_withdraw_advice`): nenhuma recomendacao nova
        pode ser decidida enquanto uma vencida do mes anterior ainda estiver
        `PENDING`. A politica de saque decide ANTES da estrategia porque no
        engine ela ve o equity do fecho antes de qualquer acao nova ser
        enfileirada; trocar a ordem mudaria o valor sacado.

        Ordem das GUARDAS (achado E3, FEAT-003): idempotencia ("ja decidido")
        roda ANTES de `data_is_ready`. Sem essa inversao, o gap-flapping
        conhecido do yfinance (o parquet perde retroativamente a barra do
        dia entre um download e outro) geraria um `error` de "rotacao pode
        ter sido PERDIDA" para uma sessao que JA foi decidida com sucesso,
        so porque o dado sumiu DEPOIS.

        Essa guarda de entrada e um `SELECT`, e portanto uma OTIMIZACAO, nao
        uma garantia: entre ler e gravar cabe um segundo processo (nao existe
        guarda de instancia unica no projeto). A garantia e a reserva atomica
        `store.claim_session` mais abaixo, que substituiu o `record_equity`
        deste caminho — quem perde a corrida abandona a decisao em vez de
        mandar a mesma rotacao de novo para a corretora.

        Skip por dado incompleto (item 3.3): grava evento + notifica, com
        DEDUPE por `(sessao, faltantes)` persistido em `policy_state` (achado
        E2) — sem isso, `run_once` chamado a cada minuto inundaria o canal de
        alerta. Escala para `error` quando o pregao pulado for o ULTIMO do
        mes (`clock.next_session(session).month != session.month`): nesse
        caso a rotacao nao e adiada, e PERDIDA. Este `error` so ESCALA o
        NIVEL da notificacao (achado E1) — `run_once` continua chamando
        `reconcile_pending_fills`, `execute_session`, `intraday_tick` e a
        confirmacao de saque normalmente, nunca aborta por causa dele.
        """
        universe = self._load_universe()

        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return StepReport("decide_skip", session, detail={"motivo": "conta inexistente"})

            self._restore_robot_state(account.policy_state)

            # E7: aviso UNICO por processo se a conta e de dinheiro real
            # (mt5) e nao ha canal de notificacao configurado -- sem isso, o
            # alerta mais importante do lote sairia so para um log que
            # ninguem le.
            if (account.mode == "mt5" and isinstance(self.notifier, NullNotifier)
                    and not self._null_notifier_warned):
                self._null_notifier_warned = True
                self._log(conn, account.id, "warn", "runtime",
                                "conta de dinheiro real sem canal de notificacao configurado "
                                "— alertas so ficam no diario")

            # E3: idempotencia ANTES do dado -- ver docstring.
            ja_decidida = store.last_equity(conn, account.id, session.isoformat())
            if ja_decidida is not None and ja_decidida[0] == session.isoformat():
                return StepReport("decide_skip", session, detail={"motivo": "ja decidido"})

            ready, faltando = self._data_is_ready(session, universe)
            if not ready:
                fim_de_mes = clock.next_session(session).month != session.month
                nivel = "error" if fim_de_mes else "warn"
                marcador = {"session": session.isoformat(), "faltando": sorted(faltando)}
                if self._skip_avisado != marcador:
                    msg = f"dado incompleto para {session}: faltando {', '.join(sorted(faltando))}"
                    if fim_de_mes:
                        msg += " — FIM DE MES: a rotacao pode ter sido PERDIDA, nao so adiada"
                    self._log(conn, account.id, nivel, "runtime", msg, marcador)
                    self._skip_avisado = marcador
                    # so persiste quando o marcador de fato MUDOU (correcao
                    # pos-review, tentativa 1): sem esta guarda, o skip
                    # deduplicado ainda gravava no SQLite a cada minuto
                    # enquanto o dado estivesse faltando, sem necessidade --
                    # o dedupe em memoria/banco ja cobre a mensagem, so falta
                    # nao reescrever o mesmo estado repetidamente.
                    account.policy_state = self._robot_state()
                    store.save_account(conn, account)
                return StepReport("decide_skip", session, detail={
                    "motivo": "dado incompleto", "faltando": ",".join(faltando),
                    "fim_de_mes": fim_de_mes,
                })

            self._load(session, universe)

            saques_expirados = self._expire_withdraw_advice(conn, account, session)

            marks = self._marks(session)
            equity = account.equity(marks)
            patrimonio = account.patrimonio(marks)
            # Marcacao do fecho e RESERVA do direito de decidir, numa unica
            # operacao atomica (ver `store.claim_session`). Perder a corrida
            # aqui significa que um SEGUNDO processo decidiu este pregao entre
            # o `SELECT` de "ja decidido" la em cima e esta linha — sem esta
            # guarda, os dois gerariam a mesma rotacao e a corretora receberia
            # a ordem duas vezes. O que `_expire_withdraw_advice` ja gravou
            # acima pode ficar: expirar recomendacao vencida e idempotente e
            # protegido pelo proprio `claim_intent`.
            if not store.claim_session(conn, account.id, session, account.cash,
                                       account.invested(marks), equity,
                                       account.external_cash):
                self._log(conn, account.id, "warn", "runtime",
                          f"outro processo decidiu {session} durante esta chamada — "
                          "decisao abandonada para nao duplicar ordem. Dois "
                          "supervisores no mesmo banco?",
                          {"session": session.isoformat()})
                return StepReport("decide_skip", session,
                                  detail={"motivo": "ja decidido (corrida)"})

            # Pregao que passou SEM decisao nenhuma (processo fora do ar no
            # fecho, maquina desligada, servico morto). O risco aqui e o
            # OPOSTO de decidir duas vezes: a decisao daquele fecho nao
            # atrasa, ela se PERDE — e se o pregao perdido era o ultimo do
            # mes, perde-se a rotacao inteira, porque `BuyTheDip` so olha
            # `is_month_end`. `status()` ja mostra a lista no painel (achado
            # E4), mas painel e passivo: quem esta com a maquina fora do ar
            # nao esta olhando o painel. Aqui o buraco EMPURRA um aviso.
            #
            # Nao ha retomada automatica de proposito: executar hoje uma
            # rotacao decidida num fecho antigo e mudanca de comportamento de
            # dinheiro (regra 7 do AGENTS.md manda a intencao velha expirar,
            # nunca executar tarde), e essa e decisao do dono, nao deste
            # commit. O que se corrige aqui e o silencio.
            if ja_decidida is not None:
                perdidos: list[date] = []
                d = clock.next_session(date.fromisoformat(ja_decidida[0]))
                while d < session and len(perdidos) < 30:
                    perdidos.append(d)
                    d = clock.next_session(d)
                if perdidos:
                    virada = [x for x in perdidos
                              if clock.next_session(x).month != x.month]
                    msg = (f"{len(perdidos)} pregao(oes) sem decisao antes de {session}: "
                           f"{perdidos[0]} a {perdidos[-1]}")
                    if virada:
                        msg += (f" — inclui fim de mes ({', '.join(str(x) for x in virada)}): "
                                "a rotacao daquele mes nao foi adiada, foi PERDIDA")
                    self._log(conn, account.id, "error" if virada else "warn", "runtime", msg,
                              {"perdidos": [x.isoformat() for x in perdidos],
                               "fim_de_mes": [x.isoformat() for x in virada]})

            # Circuit breaker: observa o patrimonio do fecho ANTES de colher
            # decisoes, para o veto (se houver) valer para as intencoes que
            # vao ser geradas agora — nao para as do fecho anterior, que ja
            # foram gravadas. `may_anchor=True`: este e o caminho de FECHO, o
            # unico que pode criar a ancora do dia/mes (achado F1).
            self._observe_risk(conn, account, session, patrimonio, may_anchor=True)

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
                self._record_intent(conn, account, intent)
                gravadas += 1
                if intent.kind == IntentKind.WITHDRAW:
                    # Saque nunca mais e executado pela maquina — so registrado
                    # e notificado. `warn` porque `--notify-min-level` default
                    # e `warn` (ver docstring de `scripts/run_live.py`).
                    self._log(conn, account.id, "warn", "saque",
                                    f"recomendacao de saque: R$ {intent.amount:.2f} "
                                    f"({intent.reason}) — saque direto na corretora, "
                                    "se e quando quiser: este sistema so notifica",
                                    {"intent_id": intent.id, "valor": intent.amount})

            for pos in account.positions.values():
                pos.bars_held += 1
                store.upsert_position(conn, account.id, pos)

            # A sessao decidiu com sucesso -- o marcador de dedupe do skip
            # nao pode calar o PROXIMO skip (de uma sessao futura).
            self._skip_avisado = None
            account.policy_state = self._robot_state()
            store.save_account(conn, account)
            self._log(conn, account.id, "info", "runtime",
                            f"fecho {session}: equity {equity:.2f}, {gravadas} intencoes")

        return StepReport("decide", session, detail={
            "equity": round(equity, 2), "intencoes": gravadas, "stops_movidos": aplicadas,
            "saques_expirados": saques_expirados,
        })

    # ---------- abertura: o ambiente executa ------------------------------

    def execute_session(self, session: date) -> StepReport:
        """Executa as intencoes que valem para `session`, na ordem do engine.

        `_sell`/`_buy` devolvem um de tres resultados, nao um bool: `'done'`
        (aplicado), `'rejected'` (nao vai acontecer) e `'pending'` (ordem no
        ar, sem fill ainda — MT5 pode devolver fill de forma assincrona, ou
        uma ordem limitada que ainda nao bateu o preco). `'pending'` NAO e
        rejeicao: a intencao vira
        `EXECUTING` e e resolvida depois por `reconcile_pending_fills`, sem
        ser re-tentada nem expirada por atraso.

        Saque NUNCA e executado aqui, nem em lugar nenhum do sistema. Uma
        intent `WITHDRAW` (programada no fecho anterior, ou gerada agora por
        evento de liquidez) so vira RECOMENDACAO: gravada + notificada. Se o
        dono quiser sacar de verdade, ele acessa a corretora diretamente —
        a recomendacao so expira na virada do mes (`_expire_withdraw_advice`),
        nunca e "confirmada" por este sistema.
        """
        self._load(clock.previous_session(session))
        quotes = self.feed.quotes(self.tickers)
        done = {"expiradas": 0, "saques_expirados": 0, "recomendacoes_saque": 0,
               "saidas": 0, "entradas": 0, "rejeitadas": 0, "aguardando": 0}

        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return StepReport("execute_skip", session, detail={"motivo": "conta inexistente"})
            self._restore_robot_state(account.policy_state)

            # 1. Intencao atrasada nunca executa (regra 7 do AGENTS.md).
            #    `stale_intents` ja exclui WITHDRAW (nao expira por dia).
            for velha in store.stale_intents(conn, account.id, session):
                store.set_intent_status(conn, velha.id, IntentStatus.EXPIRED)
                self._log(conn, account.id, "warn", "runtime",
                                f"intencao {velha.id} expirada: valia em {velha.execute_on}, "
                                f"hoje e {session}")
                done["expiradas"] += 1

            # 2. Expira recomendacao de saque vencida (virada de mes civil)
            #    ANTES de qualquer venda — impede que uma recomendacao nova
            #    por evento de liquidez (passo 4 abaixo) coexista PENDING com
            #    uma vencida do mes anterior (ver `_expire_withdraw_advice`).
            done["saques_expirados"] = self._expire_withdraw_advice(conn, account, session)

            pend = store.pending_intents(conn, account.id, session)
            saidas = [i for i in pend if i.kind == IntentKind.EXIT]
            entradas = [i for i in pend if i.kind == IntentKind.ENTER]
            # Intents WITHDRAW programadas (`execute_on == session`, decididas
            # no fecho anterior) aparecem em `pend` mas NAO sao processadas
            # aqui de proposito — continuam PENDING, visiveis em `status()`
            # via `pending_withdraw_intents`, ate confirmacao humana ou
            # expiracao mensal.

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

            # 4. Recomendacao de saque por evento de liquidez: alguma venda
            #    creditou caixa agora — so REGISTRA a recomendacao e notifica,
            #    nunca executa (`Intent.is_immediate` cobre este caso:
            #    execute_on == decided_on == session, ver core.live_models).
            if motivo_liquidez:
                ctx = self._context(session, account, SessionPhase.OPEN, quotes)
                for intent in self.withdrawal.on_liquidity(ctx, motivo_liquidez):
                    self._record_intent(conn, account, intent)
                    self._log(conn, account.id, "warn", "saque",
                                    f"recomendacao de saque: R$ {intent.amount:.2f} "
                                    f"({intent.reason}) — saque direto na corretora, "
                                    "se e quando quiser: este sistema so notifica",
                                    {"intent_id": intent.id, "valor": intent.amount})
                    done["recomendacoes_saque"] += 1

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
        # FEAT-004, item 4.3 (correcao SUBSTANTIVA do plan-reviewer, §6 item
        # 1): segunda trava, mais geral que a de `intraday_tick` acima —
        # cobre o caminho CRUZADO em que um stop intra-dia de ONTEM ainda
        # esta `SENT`/nao confirmado (posicao continua em `account.
        # positions`, ver `_resolve_sell`) e o robo decide sair de novo HOJE
        # por OUTRO motivo (rotacao, fim de mes) — o robo nao enxerga ordem
        # em voo, so posicao (regra 6), entao pode legitimamente decidir sair
        # de novo. `_sell` e chamado tanto por `execute_session` quanto por
        # `intraday_tick`: colocar a trava aqui fecha os dois caminhos com
        # uma unica checagem, em vez de duplicar nos dois call-sites.
        ja_em_voo = next(
            (o for o in store.open_orders(conn, account.id)
             if o.ticker == pos.ticker and o.side == OrderSide.SELL),
            None,
        )
        if ja_em_voo is not None:
            store.set_intent_status(conn, intent.id, IntentStatus.CANCELLED)
            self._log(conn, account.id, "warn", "runtime",
                            f"saida de {pos.ticker} descartada: ja existe ordem "
                            f"aberta #{ja_em_voo.id} para o mesmo papel — venda "
                            "nao duplicada")
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
            # Ordem viva, sem fill ainda (MT5 pode confirmar de forma
            # assincrona, ou ordem limitada que nao bateu preco). NAO e
            # rejeicao: a intencao fica EXECUTING para
            # `reconcile_pending_fills` retomar depois, sem ser re-tentada
            # como PENDING nem expirada por atraso.
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
        # 4.4d: saida executada com sucesso e notificada -- distingue PARCIAL
        # de TOTAL (§6 item 3 do plan-reviewer): sem isso, um fill parcial
        # (alcancavel via MT5Broker) ficaria identico a um fill total na
        # notificacao, escondendo que falta agir sobre o restante
        # (`order.leaves_qty`).
        if order.status == OrderStatus.PARTIAL:
            self._log(conn, account.id, "info", "runtime",
                            f"SAIDA PARCIAL de {pos.ticker}: {order.filled_qty} de "
                            f"{order.quantity} @ {order.avg_price or 0.0:.4f} "
                            f"(falta {order.leaves_qty})",
                            {"ticker": pos.ticker, "filled_qty": order.filled_qty,
                             "quantity": order.quantity, "leaves_qty": order.leaves_qty})
        else:
            self._log(conn, account.id, "info", "runtime",
                            f"saida executada: {pos.ticker} {order.filled_qty} "
                            f"@ {order.avg_price or 0.0:.4f}",
                            {"ticker": pos.ticker, "filled_qty": order.filled_qty})
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
        if custo > account.cash:
            # 4.4a: um fill mais caro que o planejado (gap, gordura de
            # `plan_entry` que reserva so ~0,22%) nao pode passar em
            # silencio -- alerta, mas NAO impede nem desfaz o fill: a
            # execucao ja aconteceu de verdade na corretora.
            self._log(conn, account.id, "error", "runtime",
                            f"entrada em {intent.ticker} custou R$ {custo:.2f}, acima "
                            f"do caixa disponivel (R$ {account.cash:.2f})",
                            {"custo": round(custo, 2), "caixa": round(account.cash, 2)})
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
        # 4.4d: entrada executada com sucesso e notificada -- distingue
        # PARCIAL de TOTAL (§6 item 3), mesmo motivo de `_resolve_sell`.
        if order.status == OrderStatus.PARTIAL:
            self._log(conn, account.id, "info", "runtime",
                            f"ENTRADA PARCIAL em {intent.ticker}: {order.filled_qty} de "
                            f"{order.quantity} @ {preco:.4f} (falta {order.leaves_qty})",
                            {"ticker": intent.ticker, "filled_qty": order.filled_qty,
                             "quantity": order.quantity, "leaves_qty": order.leaves_qty})
        else:
            self._log(conn, account.id, "info", "runtime",
                            f"entrada executada: {intent.ticker} {order.filled_qty} @ {preco:.4f}",
                            {"ticker": intent.ticker, "filled_qty": order.filled_qty})
        return "done"

    # ---------- saque: recomendacao, expiracao, confirmacao humana ---------

    def _expire_withdraw_advice(self, conn, account: AccountState, session: date) -> int:
        """Expira recomendacoes de saque cuja virada de mes civil ja passou.

        Recomendacao de saque NAO expira por dia (`stale_intents` exclui
        `kind='withdraw'` de proposito, ver `journal.live_store`) -- ela fica
        visivel/confirmavel o mes inteiro. O que a torna invalida e o mes
        civil da decisao (`decided_on`) ser DIFERENTE do mes civil de
        `session`: chegou um mes novo, a politica ja teria decidido outra
        parcela, a recomendacao antiga nao vale mais.

        Chamado no INICIO de `close_and_decide` e no INICIO de
        `execute_session` (antes de qualquer venda/compra) -- as duas vezes
        que uma decisao de liquidez pode estar prestes a acontecer. Motivo:
        `run_once` roda `execute_session` (OPEN) ANTES de
        `close_and_decide` (POST_CLOSE), entao no 1o pregao de um mes novo uma
        recomendacao por evento de liquidez pode nascer ANTES de a do mes
        anterior ser expirada -- se isso acontecesse, haveria DUAS intents
        WITHDRAW `PENDING` ao mesmo tempo.

        `FloorSkim._requested` e um escalar GLOBAL da politica (nao por-intent,
        ver `backtest/withdrawal.py`): `on_executed` faz `falta = _requested -
        executed` e zera. Duas recomendacoes pendentes corromperiam essa
        conta. A garantia que este helper oferece NAO e mexer em `_pool` na
        mao (isso seria regra de decisao vivendo em `live/`, proibido pela
        regra 6 do AGENTS.md) -- e so a ORDEM: nenhuma recomendacao nova e
        decidida enquanto uma vencida ainda estiver `PENDING`. Se, ainda
        assim, mais de uma `PENDING` for encontrada aqui, e invariante
        quebrada: loga `error` (nao deveria acontecer nunca) em vez de passar
        batido.

        PERSISTE sempre que de fato expirar alguma coisa (mesmo padrao de
        `unfreeze()`: restaura -> muta -> persiste): `on_executed(intent,
        0.0)` muta a politica SO em memoria (`self.withdrawal`); sem gravar
        `account.policy_state`/`store.save_account` aqui dentro, um chamador
        que retorna logo em seguida perderia o valor devolvido a fila em
        silencio -- o evento diria "volta pra fila" mas o banco continuaria
        com o `_requested` antigo. Nao depende de cada chamador lembrar de
        persistir: e o proprio helper que garante isso sempre que muda o
        estado da politica.

        Devolve quantas recomendacoes expirou.
        """
        pendentes = store.pending_withdraw_intents(conn, account.id)
        if len(pendentes) > 1:
            self._log(conn, account.id, "error", "saque",
                            f"{len(pendentes)} recomendacoes de saque PENDING ao mesmo "
                            "tempo -- invariante quebrada",
                            {"intent_ids": [i.id for i in pendentes]})

        expiradas = 0
        for intent in pendentes:
            if (intent.decided_on.year, intent.decided_on.month) == (session.year, session.month):
                continue
            if not store.claim_intent(conn, intent.id, IntentStatus.PENDING, IntentStatus.EXPIRED):
                continue  # outro processo ja tratou esta recomendacao
            self.withdrawal.on_executed(intent, 0.0)
            self._log(conn, account.id, "warn", "saque",
                            f"recomendacao de saque de R$ {intent.amount:.2f} (decidida em "
                            f"{intent.decided_on}) expirou sem confirmacao -- valor volta "
                            "para a fila da politica",
                            {"intent_id": intent.id, "valor": intent.amount})
            expiradas += 1

        if expiradas:
            account.policy_state = self._robot_state()
            store.save_account(conn, account)
        return expiradas

    # ---------- reconciliacao (fills que chegaram depois) ------------------

    def reconcile_pending_fills(self, now: Optional[datetime] = None) -> StepReport:
        """Aplica ao estado da conta qualquer ordem `EXECUTING` que se resolveu.

        Existe porque MT5 pode devolver fill de forma assincrona: `place()`
        pode retornar sem fill (ordem so aceita, nao executada), e o fill
        real so aparece depois via `poll()`, chamado de outro momento deste
        mesmo processo ou de um restart. Sem este passo, o fill confirmado
        ficaria escrito na `Order` mas NUNCA chegaria a `AccountState`
        (caixa, posicao) — dinheiro perdido no diario. Seguro chamar a
        qualquer momento: so existe intencao `EXECUTING` quando ha mesmo
        algo pendente.

        ENTER/EXIT geram exatamente um `Order` por `Intent`, entao olhar so o
        ultimo (`orders[-1]`) basta. WITHDRAW nao aparece mais aqui: desde que
        o saque virou recomendacao (nunca executada pela maquina, nem por
        este sistema), nenhuma intent WITHDRAW chega a `EXECUTING` — ver
        `execute_session`.

        Restaura o estado dos robos (`_restore_robot_state`) ANTES do laco,
        replicando o padrao ja documentado em `unfreeze()`: esta chamada pode
        vir de um processo NOVO (cron, restart do supervisor), cujo
        `self.withdrawal`/`self.risk_guard` em memoria ainda nao viram o que
        esta gravado no banco. Sem isso, a linha `account.policy_state =
        self._robot_state()` no fim do metodo (fora do laco — roda mesmo sem
        nenhuma intent EXECUTING) gravaria uma politica de saque VIRGEM por
        cima do estado real, apagando `_paid_month`/`_pool`/`_requested` e
        fazendo a politica recomendar o mesmo mes de novo.
        """
        now = now or datetime.now(timezone.utc)
        aplicadas = 0
        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return StepReport("reconcile_skip", detail={"motivo": "conta inexistente"})
            self._restore_robot_state(account.policy_state)
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
                else:
                    resultado = "rejected"
                    store.set_intent_status(conn, intent.id, IntentStatus.REJECTED)
                if resultado == "done":
                    aplicadas += 1
            account.policy_state = self._robot_state()
            store.save_account(conn, account)
        return StepReport("reconcile", detail={"aplicadas": aplicadas})

    # ---------- deposito externo (aporte) -----------------------------------

    def reconcile_broker_cash(self, now: Optional[datetime] = None) -> StepReport:
        """Sincroniza `AccountState.cash` com o saldo real da corretora
        (`Broker.cash_balance()`) uma vez por dia, antes da abertura, NAS
        DUAS DIREÇÕES.

        Regra do dono (2026-08-19): sem capital digitado, sem botão manual
        de aporte/saque (removidos — ver `git log` desta mudança) — o robô
        detecta capital novo sozinho e aloca na próxima decisão; um saque
        feito pelo dono direto na corretora não exige nenhuma ação nossa.
        Como consequência, `account.cash` deixa de ser um ledger
        independente e vira sempre um SNAPSHOT do que a corretora diz que
        existe de caixa livre — não há mais nenhum outro código que
        credite/debite esse campo fora daqui e da execução de ordens
        (`_buy`/venda), então sincronizar sempre é seguro por definição: só
        existe UM livro-caixa agora.

        Antes desta mudança, esta função era um DETECTOR PURO (nunca
        creditava/debitava, só avisava) — porque uma versão ainda mais
        antiga (commit `c0ef1e7`) creditava diferenças positivas automática
        e incondicionalmente, o que inflava o patrimônio quando um saque de
        verdade acontecia na corretora fora do conhecimento do sistema (ver
        `confirm_withdrawal`, removido). Essa classe de bug dependia de
        DOIS livros-caixa que podiam divergir (o ledger interno, mutado só
        por transações que o sistema conhecia, e o saldo real). Sem um
        segundo livro paralelo, não existe mais "para onde divergir errado"
        — encolher também é uma sincronização legítima agora, não mais um
        sinal a ignorar.

        So age quando a corretora sabe responder isso: `cash_balance()`
        default e `None` (sem conta real para comparar) — mantém o último
        `account.cash` conhecido e avisa, nunca zera nem trava o robô.
        """
        real_balance = self.broker.cash_balance()
        now = now or datetime.now(timezone.utc)
        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return StepReport("reconcile_cash_skip", detail={"motivo": "conta inexistente"})

            if real_balance is None:
                self._log(conn, account.id, "warn", "runtime",
                                "não foi possível ler o saldo da corretora na sincronização "
                                f"diária -- mantendo o último caixa conhecido (R$ {account.cash:.2f}); "
                                "confirme que o terminal MT5 está aberto e logado.",
                                {})
                return StepReport("reconcile_cash_skip", detail={"motivo": "corretora sem saldo externo"})

            diff = real_balance - account.cash
            if abs(diff) <= _DEPOSIT_TOLERANCE:
                return StepReport("reconcile_cash", detail={"diferenca": round(diff, 2)})

            anterior = account.cash
            account.cash = real_balance
            store.save_account(conn, account)
            store.record_deposit(conn, account.id, now.date(), round(diff, 2),
                                  origin="mt5_auto_sync",
                                  note=f"caixa anterior {anterior:.2f} -> real {real_balance:.2f}")

            if diff > 0:
                # Capital novo (aporte externo do dono, direto na
                # corretora): info, não precisa acordar ninguém -- é a
                # operação normal esperada por este design; a próxima
                # decisão de fecho (`close_and_decide`) já aloca sozinha,
                # já que o robô atual usa size_hint=1.0 (100% do caixa) na
                # entrada.
                self._log(conn, account.id, "info", "runtime",
                                f"capital novo detectado na corretora: +R$ {diff:.2f} "
                                f"(caixa {anterior:.2f} -> {real_balance:.2f}) -- será "
                                "considerado na próxima decisão de alocação.",
                                {"diferenca": round(diff, 2)})
            else:
                # Saldo encolheu: pode ser um saque que o dono fez direto
                # na corretora (esperado, não é erro) ou uma taxa/ajuste
                # inesperado -- não dá para distinguir os dois casos
                # daqui, então avisa sempre para o dono revisar o extrato
                # se a causa não for óbvia.
                self._log(conn, account.id, "warn", "runtime",
                                f"caixa da corretora encolheu: R$ {diff:.2f} "
                                f"(caixa {anterior:.2f} -> {real_balance:.2f}) -- confirme "
                                "se foi um saque seu direto na corretora ou revise o extrato.",
                                {"diferenca": round(diff, 2)})

            return StepReport("reconcile_cash", detail={"diferenca": round(diff, 2)})

    # ---------- intra-dia --------------------------------------------------

    def intraday_tick(self, session: date, now: Optional[datetime] = None) -> StepReport:
        """Acompanha preco, dispara stop e observa o disjuntor de risco.

        FEAT-003 (item 3.1, achado B1): antes desta feature, este metodo nao
        chamava `risk_guard.observe()` — um crash intra-dia que se
        recuperasse ate o fecho nunca era visto pelo disjuntor. Carrega os
        paineis (`_load`) ANTES de observar: sem isso, `self._panels` fica
        vazio num processo recem-reiniciado, `_marks()` devolve `{}`, e
        `AccountState.invested` cai no fallback `marks.get(t, p.entry_price)`
        — toda posicao aberta valeria o preco de ENTRADA, lendo como perda
        instantanea e travando o disjuntor por engano (e essa trava
        fantasma seria PERSISTIDA por este mesmo metodo). Falha de painel
        NUNCA pode derrubar o processamento de stop (que so depende de
        `quotes`) — por isso o `try/except` isolado abaixo.

        `may_anchor=False`: um tick NUNCA cria a ancora do dia/mes sozinho
        (achado F1) — so `close_and_decide` pode.

        Divergencia HONESTA com o backtest, documentada aqui (achado B4): a
        protecao intra-dia so cobre entradas ainda NAO processadas neste
        ciclo de `run_once` — `execute_session` roda antes de
        `intraday_tick` na fase OPEN, entao uma entrada ja executada hoje
        nao e desfeita, e uma ordem `Enter` ja em voo nao e cancelada quando
        a trava fecha (mesmo comportamento de `_buy`, que so veta ANTES do
        envio).
        """
        now = now or datetime.now(timezone.utc)
        quotes = self.feed.quotes(self.tickers)
        velhas = staleness_report(quotes, now, self.max_quote_age)

        paineis_ok = True
        paineis_erro: Exception | None = None
        try:
            self._load(clock.previous_session(session))
        except Exception as exc:
            paineis_ok = False
            paineis_erro = exc

        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return StepReport("intraday_skip", session, detail={"motivo": "conta inexistente"})
            self._restore_robot_state(account.policy_state)

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
            # FEAT-004, item 4.3: saida ja em voo (PENDING/EXECUTING) para o
            # mesmo ticker nao pode ser re-emitida so por este MESMO
            # `on_intraday` repetir na chamada seguinte de `intraday_tick` —
            # calculado ANTES do laco, contra o que ja esta no diario.
            exit_em_andamento = {
                i.ticker
                for i in (
                    store.intents_by_status(conn, account.id, IntentStatus.PENDING)
                    + store.intents_by_status(conn, account.id, IntentStatus.EXECUTING)
                )
                if i.kind == IntentKind.EXIT
            }
            for intent in self.investment.on_intraday(ctx):
                if intent.ticker in velhas:
                    # 4.2: stop nunca dispara sobre cotacao declaradamente
                    # velha — suprime (nao grava, nao envia) e escala pra
                    # `error` (mais grave que o `warn` acima, que so avisa
                    # sobre a cotacao velha; aqui uma DECISAO real foi
                    # descartada por causa dela).
                    self._log(conn, account.id, "error", "feed",
                                    f"stop de {intent.ticker} suprimido: cotacao "
                                    f"atrasada {int(velhas[intent.ticker])}s "
                                    f"(feed {self.feed.name}) -- nao executa sobre dado velho")
                    continue
                if intent.ticker in exit_em_andamento:
                    # ja existe uma saida em voo para este ticker (gravada
                    # numa chamada anterior de `intraday_tick`) — nao
                    # reemite. Ver tambem a trava em `_sell`, que cobre o
                    # caminho cruzado (saida decidida no FECHO enquanto este
                    # stop ainda esta em voo).
                    continue
                self._record_intent(conn, account, intent)
                if self._sell(conn, account, session, intent, quotes) == "done":
                    disparados += 1
                    self._log(conn, account.id, "warn", "runtime",
                                    f"stop disparado em {intent.ticker} "
                                    f"(feed {self.feed.name}, atraso {self.feed.delay_seconds:.0f}s)")

            if paineis_ok:
                marks = self._intraday_marks(session, quotes, stale=velhas)
                self._observe_risk(conn, account, session, account.patrimonio(marks),
                                   may_anchor=False)
            else:
                self._log(conn, account.id, "warn", "riskguard",
                                f"disjuntor nao observou o tick: paineis indisponiveis: {paineis_erro}")

            account.policy_state = self._robot_state()
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

        # Reconciliar primeiro, em toda fase: uma confirmacao assincrona do
        # MT5 pode ter chegado a qualquer momento (fora do horario de pregao
        # inclusive), e aplicar o fill ao caixa/posicao nao depende de estar
        # no pregao.
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
            account = self._load_account(conn)
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
            account = self._load_account(conn)
            if account is None:
                return {"conta": self.account_name, "existe": False}
            self._restore_robot_state(account.policy_state)
            # Recomendacao de saque NAO entra em `pending_intents` (que so olha
            # a `execute_on` do proximo pregao) -- ela fica visivel o mes
            # inteiro, ver `store.pending_withdraw_intents`. Exclui WITHDRAW
            # daqui para nao listar a mesma recomendacao duas vezes.
            pend = [i for i in store.pending_intents(conn, account.id, clock.next_session(session))
                    if i.kind != IntentKind.WITHDRAW]
            pend_saque = store.pending_withdraw_intents(conn, account.id)
            eventos = store.recent_events(conn, account.id, limit=10)

            # Todos os pregoes sem decisao (achado E4) — nao so `session`: um
            # pregao pulado (skip por dado incompleto, processo fora do ar)
            # ficaria visivel por menos de 24h se so a referencia atual fosse
            # mostrada. Teto de 30: conta nova/processo fora do ar por meses
            # nao pode gerar uma lista sem fim.
            ultima = store.last_equity(conn, account.id, session.isoformat())
            if ultima is None:
                pendentes = [session.isoformat()]
            else:
                pendentes = []
                d = clock.next_session(date.fromisoformat(ultima[0]))
                while d <= session and len(pendentes) < 30:
                    pendentes.append(d.isoformat())
                    d = clock.next_session(d)
        return {
            "conta": account.name,
            "existe": True,
            "modo": account.mode,
            "robo_investimento": account.investment_robot,
            "robo_saque": account.withdrawal_robot,
            "pregao": session.isoformat(),
            "fase": clock.phase().value,
            "decisao_pendente": pendentes,
            "notificador": type(self.notifier).__name__,
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
                {"id": i.id, "robo": i.robot, "tipo": i.kind.value, "ticker": i.ticker,
                 "motivo": i.reason, "valor": i.amount, "executa_em": i.execute_on.isoformat()}
                for i in (pend + pend_saque)
            ],
            "eventos": eventos,
        }
