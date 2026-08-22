"""Operacao ao vivo de um robo de DAY TRADE — o par intradiario de
`live/runtime.py`.

Mesma divisao de trabalho da camada diaria e a MESMA regra 6 do AGENTS.md:
nenhuma decisao nasce aqui. Quem decide e' `IntradayStrategy.on_bar`, e quem
resolve stop/alvo/toque de ordem-limite e' o motor compartilhado
`backtest/intraday/machine.py::IntradaySessionMachine` — o MESMO objeto que
o backtest roda. Este arquivo cuida de: pegar barra fechada do terminal,
calibrar o robo quando o processo liga no meio do pregao, journalizar, e (so
em modo `live`) mandar ordem.

Por que uma classe nova em vez de reusar `LiveRuntime`
------------------------------------------------------
`LiveRuntime` e' construido em torno de "uma decisao por pregao, executada
na abertura do pregao seguinte" (`Intent.execute_on`, expiracao de intencao
atrasada, `close_and_decide`/`execute_session`). Day trade nao tem D+1: a
decisao da barra `t` executa na barra `t+1`, no mesmo dia, dezenas de vezes,
e nunca carrega posicao overnight. Espremer as duas cadencias na mesma classe
faria `execute_on` significar duas coisas diferentes.

Modo sombra (`execution_mode="shadow"`, o DEFAULT)
--------------------------------------------------
A corretora NUNCA e' chamada. Tudo o mais acontece igual: barra real, robo
real, maquina real, `Intent`/`Order`/`Fill` gravados no diario com
`note="SHADOW ..."` e `broker_ref=None`. O caixa do slot NAO e' debitado — o
numero que o dono digitou continua sendo o numero dele; o P&L sombra acumula
em `policy_state["intraday"]["shadow_pnl_brl"]`.

Isto nao e' so prudencia: e' a MEDICAO que falta. O robo pressupoe que uma
ordem-limite parada no nivel X preenche quando o preco TOCA X (maker, sem
pagar o spread) — premissa que nenhum backtest pode validar sem livro de
ofertas. Por isso cada entrada em sombra grava `penetration_ticks`: quantos
ticks a barra ATRAVESSOU o nivel. Se os toques penetram 0-1 tick, a premissa
e' fragil (a ordem podia estar atras na fila e nunca executar); se as barras
atravessam varios ticks, uma ordem parada quase certamente preenche. Sem
esse campo, rodar em sombra nao responde a pergunta que motivou o modo.

Divergencia honesta declarada
-----------------------------
Stop e alvo aqui resolvem em barra M1 FECHADA, entao o robo reage ate 60s
depois do que o backtest intrabar assume. Nao ha correcao possivel do lado
do robo (um stop por tick seria uma REGRA DIFERENTE da validada, o que a
regra 6 proibe) — a correcao real e' SL/TP no lado da corretora, trabalho
separado. Ate la, isto e' um custo conhecido, nao uma surpresa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from backtest.intraday.machine import (
    IntradayBacktestConfig,
    IntradaySessionMachine,
    LimitCancelled,
    LimitPlaced,
    PositionClosed,
    PositionOpened,
)
from core.config import LIVE_DB_PATH, Slot
from core.live_models import (
    AccountState,
    Fill,
    Intent,
    IntentKind,
    IntentStatus,
    LivePosition,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    RobotRole,
    SessionPhase,
)
from journal import live_store as store
from live import clock
from live.bar_feed import MT5BarFeed
from live.notify import NullNotifier
from live.runtime import StepReport
from strategy.daytrade.base import Bar, warm_start_calibration

#: Acima disto, um buraco de barras nao e' "o processo demorou um pouco" — e'
#: o processo tendo ficado fora do ar. Reprocessar 200 barras de uma vez faria
#: o robo tomar 200 decisoes contra precos que ja passaram; achatar e recomecar
#: e' a leitura honesta. Casa em espirito com `Strategy.on_missed_bars` do lado
#: diario (ver `missed_session_policy_2026_08_20` na memoria do projeto): o
#: buraco nunca e' ignorado, e a decisao velha nunca e' executada.
MAX_GAP_BARS = 15

_SHADOW_NOTE = "SHADOW — nao enviada ao MT5"


@dataclass
class _SessionSnapshot:
    """O que sobrevive a um restart do processo, dentro de
    `policy_state["intraday"]`."""

    session: Optional[date] = None
    last_bar_ts: Optional[pd.Timestamp] = None
    shadow_pnl_brl: float = 0.0
    trades: int = 0
    # Ordens-limite postas e abandonadas sem preencher nesta sessao. A razao
    # entre postas e preenchidas (`trades`) e' o sinal de prioridade de fila
    # que o modo sombra existe para medir — contadas, e nao narradas em
    # `live_events`, para nao afogar o diario operacional (ver
    # `_on_limit_placed`).
    ordens_postas: int = 0
    ordens_abandonadas: int = 0
    machine: dict = None  # `IntradaySessionMachine.state()`

    def to_dict(self) -> dict:
        return {
            "session": self.session.isoformat() if self.session else None,
            "last_bar_ts": self.last_bar_ts.isoformat() if self.last_bar_ts is not None else None,
            "shadow_pnl_brl": round(self.shadow_pnl_brl, 4),
            "trades": self.trades,
            "ordens_postas": self.ordens_postas,
            "ordens_abandonadas": self.ordens_abandonadas,
            "machine": self.machine or {},
        }

    @classmethod
    def from_dict(cls, raw: Optional[dict]) -> "_SessionSnapshot":
        raw = raw or {}
        sess = raw.get("session")
        last = raw.get("last_bar_ts")
        return cls(
            session=date.fromisoformat(sess) if sess else None,
            last_bar_ts=pd.Timestamp(last) if last else None,
            shadow_pnl_brl=float(raw.get("shadow_pnl_brl") or 0.0),
            trades=int(raw.get("trades") or 0),
            ordens_postas=int(raw.get("ordens_postas") or 0),
            ordens_abandonadas=int(raw.get("ordens_abandonadas") or 0),
            machine=raw.get("machine") or {},
        )


class IntradayLiveRuntime:
    """Ambiente de operacao ao vivo de UM slot intradiario.

    `execution_mode`: `"shadow"` (default — journaliza, nunca chama a
    corretora) ou `"live"`. Ver a secao "Modo sombra" na docstring do modulo.
    """

    def __init__(
        self,
        slot: Slot,
        strategy,
        config: IntradayBacktestConfig,
        bar_feed: MT5BarFeed,
        broker,
        db_path=None,
        notifier=None,
        execution_mode: str = "shadow",
        initial_capital: float = 0.0,
        clock_feed=None,
    ) -> None:
        if execution_mode not in ("shadow", "live"):
            raise ValueError(
                f"execution_mode invalido: {execution_mode!r} — use 'shadow' ou 'live'."
            )
        # Confere o relogio do servidor MT5 uma vez por pregao (ver
        # `_check_clock`). `None` = sem conferencia — aceitavel em teste, onde o
        # feed de barras e' sintetico e nao existe relogio de servidor.
        self.clock_feed = clock_feed
        self._clock_checked_for: Optional[date] = None
        self.slot = slot
        self.account_name = slot.id
        self.strategy = strategy
        self.config = config
        self.bar_feed = bar_feed
        self.broker = broker
        self.notifier = notifier if notifier is not None else NullNotifier()
        self.execution_mode = execution_mode
        self.initial_capital = float(initial_capital)
        self.db_path = Path(db_path) if db_path is not None else LIVE_DB_PATH
        self.machine = IntradaySessionMachine(strategy, config)
        self._snapshot = _SessionSnapshot()
        # `Intent` da entrada corrente — o `Order`/`Fill` do fechamento
        # penduram na MESMA intencao, para o diario responder "por que abriu
        # e por que fechou" numa linha so, como no lado diario.
        self._open_intent_id: Optional[int] = None
        # Pregao para o qual ESTE PROCESSO ja calibrou a estrategia. Nao e' o
        # mesmo que `machine.session_date` (que vem do banco e sobrevive a um
        # restart): o estado interno do robo — `open_price`, ticks do dia — NAO
        # e' persistido de proposito (ver `IntradaySessionMachine.state`), e um
        # processo recem-subido no meio do pregao precisa reconstrui-lo do dado
        # real. Sem este campo, um restart continuaria a sessao com a maquina
        # certa e o robo descalibrado, em silencio.
        self._calibrated_for: Optional[date] = None

    # ---------- log + alerta (mesma regra do lado diario) -----------------

    def _log(self, conn, account_id, level: str, message: str, payload: Optional[dict] = None) -> None:
        store.log_event(conn, account_id, level, "daytrade", message, payload)
        self.notifier.notify(level, "daytrade", message, payload)

    # ---------- conta ------------------------------------------------------

    def ensure_account(self) -> AccountState:
        with store.live_journal(self.db_path) as conn:
            acc = store.ensure_account(
                conn, name=self.account_name, mode=self.broker.mode,
                initial_capital=self.initial_capital,
                investment_robot=self.strategy.name,
                # Day trade nao tem overlay de saque: a posicao morre no fim
                # do pregao, entao nao existe patrimonio investido de onde
                # skimar. Gravar "" (e nao o robo de saque do swing) e'
                # deliberado -- o painel mostra a verdade.
                withdrawal_robot="",
            )
        return acc

    def _load_account(self, conn) -> Optional[AccountState]:
        account = store.load_account(conn, self.account_name)
        if account is None:
            return None
        if account.mode != self.broker.mode:
            raise ValueError(
                f"conta '{self.account_name}' esta em modo {account.mode!r}, mas este "
                f"IntradayLiveRuntime foi instanciado com um broker de modo "
                f"{self.broker.mode!r} — uma conta e um broker divergentes nunca "
                "podem operar juntos."
            )
        return account

    # ---------- estado da sessao -------------------------------------------

    def _restore(self, account: AccountState, session: date) -> None:
        """Reidrata o snapshot da sessao. Snapshot de OUTRO pregao e'
        descartado: day trade nao carrega nada para o dia seguinte, entao um
        estado de ontem nao e' estado, e' lixo."""
        snap = _SessionSnapshot.from_dict((account.policy_state or {}).get("intraday"))
        if snap.session != session:
            snap = _SessionSnapshot(session=session)
        self._snapshot = snap
        self.machine.restore(snap.machine or {})

    def _persist(self, conn, account: AccountState) -> None:
        self._snapshot.machine = self.machine.state()
        estado = dict(account.policy_state or {})
        estado["intraday"] = self._snapshot.to_dict()
        account.policy_state = estado
        store.save_account(conn, account)

    # ---------- calibracao ao ligar no meio do pregao ---------------------

    @property
    def _fixed_anchor_until(self) -> Optional[time]:
        """Lido da INSTANCIA da estrategia, nunca hardcoded: o corte
        fixo->rolante e' parametro do robo (`Gremah.fixed_anchor_until`), e
        um robo sem esse conceito simplesmente nao tem janela fixa."""
        valor = getattr(self.strategy, "fixed_anchor_until", None)
        return valor if isinstance(valor, time) else None

    def _needs_warm_start(self, now: datetime) -> bool:
        """So faz warm start se ainda SOBRA janela de ancora fixa.

        Esta e' a politica de despacho decidida em 2026-08-21 (ver
        `pmam3_daytrade_champion` na memoria do projeto): ligar depois de
        `fixed_anchor_until` e fazer warm start carregava uma ordem fixa ja
        obsoleta, e a obsolescencia so era detectavel DENTRO de `on_bar` —
        uma barra inteira de defasagem, que a dependencia de caminho
        amplificava. Nao fazer warm start nesse caso faz o robo se comportar
        como ancora rolante pura desde agora, que e' exatamente o certo."""
        corte = self._fixed_anchor_until
        if corte is None:
            return False
        return now.astimezone(timezone.utc).time() < corte

    def _start_session(self, conn, account: AccountState, session: date, now: datetime) -> StepReport:
        """Calibra o robo para este pregao e (re)abre a sessao na maquina.

        Chamado uma vez por PROCESSO por pregao — inclusive depois de um
        restart no meio do pregao, porque o estado interno do robo nao e'
        persistido (ver `_calibrated_for`). Quando ha snapshot restaurado do
        MESMO pregao, o P&L da sessao e o flag de flatten sao devolvidos por
        cima do reset: o stop agregado de sessao do robo (`session_stop_brl`)
        le esse numero, e zera-lo num restart daria ao robo uma folga de
        risco que ele nao tem."""
        restaurada = self._snapshot.session == session and bool(self._snapshot.machine)
        pnl_antes, flat_antes = self.machine.session_pnl, self.machine.flattened

        modo = "cold"
        semente = 0
        if self._needs_warm_start(now):
            seed_bars = self.bar_feed.session_bars_until(session, pd.Timestamp(now))
            if seed_bars:
                pending = warm_start_calibration(self.strategy, session, seed_bars)
                self.machine.resume_session(session, seed_pending=pending)
                modo, semente = "warm_start", len(seed_bars)
                self._snapshot.session = session
                self._snapshot.last_bar_ts = seed_bars[-1].ts
                self._log(conn, account.id, "info",
                          f"sessao {session.isoformat()} calibrada com {len(seed_bars)} barra(s) "
                          "reais desde a abertura (warm start, nenhum trade fabricado); "
                          f"ordem em pe apos a calibracao: {'sim' if pending else 'nao'}",
                          {"barras": len(seed_bars), "modo": modo})
        if modo == "cold":
            self.machine.begin_session(session)
            if not restaurada:
                self._snapshot = _SessionSnapshot(session=session)
            # Comeco a frio NAO consome as barras que ja passaram (o robo
            # nao as viu, e ele proprio abre mao da janela de ancora fixa
            # nesse caso) — a operacao comeca na PROXIMA barra fechada.
            if self._snapshot.last_bar_ts is None:
                ja_fechadas = self.bar_feed.closed_bars_since(None)
                if ja_fechadas:
                    self._snapshot.last_bar_ts = ja_fechadas[-1].ts
            self._log(conn, account.id, "info",
                      f"sessao {session.isoformat()} iniciada a frio (sem warm start) — "
                      "o robo opera com ancora recalculada do preco atual a partir da "
                      "proxima barra fechada.",
                      {"modo": modo})

        if restaurada:
            self.machine.session_pnl = pnl_antes
            self.machine.flattened = flat_antes
        self._calibrated_for = session
        return StepReport("daytrade_sessao", session,
                          detail={"inicio": modo, "barras_semente": semente,
                                  "restaurada": restaurada})

    # ---------- passo -------------------------------------------------------

    def run_once(self, now: Optional[datetime] = None) -> list[StepReport]:
        """Um passo. Seguro para chamar em loop, a qualquer hora — so age
        quando ha barra M1 nova FECHADA dentro de um pregao aberto."""
        now = now or datetime.now(timezone.utc)
        fase = clock.phase(now)
        hoje = clock.session_date(now)
        passos: list[StepReport] = []

        if not clock.is_trading_day(hoje) or fase not in (SessionPhase.OPEN, SessionPhase.CLOSING_AUCTION):
            return [StepReport("idle", hoje, phase=fase)]

        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return [StepReport("daytrade_skip", hoje, detail={"motivo": "conta inexistente"})]

            alarme = self._check_clock(conn, account, hoje)
            if alarme is not None:
                return [StepReport("daytrade_skip", hoje, phase=fase,
                                   detail={"motivo": "relogio do servidor", "alarme": alarme})]

            if self._calibrated_for != hoje:
                self._restore(account, hoje)
                passos.append(self._start_session(conn, account, hoje, now))

            barras = self.bar_feed.closed_bars_since(self._snapshot.last_bar_ts)
            if not barras:
                self._persist(conn, account)
                return passos + [StepReport("daytrade_espera", hoje, phase=fase,
                                            detail={"ultima_barra": str(self._snapshot.last_bar_ts)})]

            if len(barras) > MAX_GAP_BARS:
                passos.append(self._handle_gap(conn, account, hoje, barras))
            else:
                passos.append(self._consume(conn, account, hoje, barras))

            self._persist(conn, account)
        return passos

    def _check_clock(self, conn, account: AccountState, session: date) -> Optional[str]:
        """Confere o relogio do servidor MT5 contra o papel liquido de
        referencia e devolve o motivo do alarme (ou `None` se esta coerente).

        Por que ISTO impede de operar, em vez de virar um aviso: todo horario
        que este robo usa — o corte de flatten, a troca de ancora fixa para
        rolante, o proprio "esta barra ja fechou" — e' uma comparacao contra o
        relogio do servidor. Errar o fuso em 1h nao gera excecao nenhuma: gera
        um robo executando a fase errada do dia inteiro, e o extrato so conta
        isso depois. Preferimos um pregao sem operar a um pregao operando com
        o relogio errado.

        Uma vez por pregao, nao a cada barra: e' uma leitura extra de tick, e o
        fuso do servidor nao muda no meio do dia. Um alarme ja levantado NAO
        e' re-testado — some so no proximo pregao (ou reiniciando o processo),
        porque insistir num relogio que ja se provou errado e' exatamente o
        comportamento que queremos evitar.
        """
        if self.clock_feed is None:
            return None
        if self._clock_checked_for == session:
            return self.clock_feed.server_clock_alarm
        alarme = self.clock_feed.verify_server_clock()
        self._clock_checked_for = session
        if alarme is not None:
            self._log(conn, account.id, "error",
                      f"nao vou operar: {alarme}", {"pregao": session.isoformat()})
        return alarme

    def _handle_gap(self, conn, account: AccountState, session: date, barras: list[Bar]) -> StepReport:
        """Buraco grande: o processo ficou fora do ar. Nao reprocessa (isso
        seria tomar decisoes velhas contra precos que ja passaram) — achata a
        posicao com a barra MAIS RECENTE e recomeca a sessao dali."""
        ultima = barras[-1]
        fechados = []
        for evento in self.machine.force_flatten(ultima.ts, ultima.close):
            if isinstance(evento, PositionClosed):
                fechados.append(evento)
            self._apply(conn, account, evento, ultima)
        self._log(conn, account.id, "error",
                  f"buraco de {len(barras)} barras M1 no pregao {session.isoformat()} — "
                  "o processo ficou fora do ar. Nao reprocessei o buraco (decisao velha "
                  "nunca executa, regra 7 do AGENTS.md); "
                  f"{'posicao achatada e ' if fechados else ''}sessao reiniciada na barra "
                  f"{ultima.ts.isoformat()}.",
                  {"barras": len(barras), "achatou": bool(fechados)})
        self._snapshot.last_bar_ts = ultima.ts
        # O buraco nao encerra o pregao — so a nossa participacao nele ate
        # aqui. Reabre o flatten e obriga uma RECALIBRACAO no proximo passo
        # (`_calibrated_for = None`): se ainda houver janela de ancora fixa, o
        # robo tem de ser recalibrado do dado real, senao ele adotaria a
        # abertura errada (a primeira barra que vir depois do buraco) e
        # rodaria o resto do dia deslocado. O acumulado da sessao (P&L, trades,
        # resultado sombra) sobrevive: e' o mesmo pregao.
        self.machine.flattened = False
        self._calibrated_for = None
        return StepReport("daytrade_buraco", session,
                          detail={"barras": len(barras), "achatou": bool(fechados)})

    def _consume(self, conn, account: AccountState, session: date, barras: list[Bar]) -> StepReport:
        """Alimenta as barras na maquina, EM ORDEM, e journaliza os eventos."""
        abertas = fechadas = 0
        for bar in barras:
            for evento in self.machine.on_closed_bar(bar):
                if isinstance(evento, PositionOpened):
                    abertas += 1
                elif isinstance(evento, PositionClosed):
                    fechadas += 1
                self._apply(conn, account, evento, bar)
            self._snapshot.last_bar_ts = bar.ts
        return StepReport("daytrade", session,
                          detail={"barras": len(barras), "entradas": abertas, "saidas": fechadas,
                                  "modo": self.execution_mode})

    # ---------- journal + execucao ------------------------------------------

    def _apply(self, conn, account: AccountState, evento, bar: Bar) -> None:
        if isinstance(evento, LimitPlaced):
            self._on_limit_placed(conn, account, evento)
        elif isinstance(evento, LimitCancelled):
            self._on_limit_cancelled(conn, account, evento)
        elif isinstance(evento, PositionOpened):
            self._on_opened(conn, account, evento)
        elif isinstance(evento, PositionClosed):
            self._on_closed(conn, account, evento, bar)

    def _on_limit_placed(self, conn, account: AccountState, evento: LimitPlaced) -> None:
        """Uma ordem-limite passou a ser vigiada.

        NAO grava evento no diario de proposito: o robo re-ancora a ordem a
        cada recarga e a cada `rolling_reanchor_after_bars`, entao uma linha
        por ordem posta afogaria `live_events` (e o painel "Eventos recentes",
        que mostra 10) em ruido — enterrando exatamente os eventos que exigem
        acao. O que interessa e' CONTADO (`ordens_postas`/
        `ordens_abandonadas`, visiveis em `status()`, e a razao
        postas/preenchidas e' o proprio sinal de prioridade de fila) e a ordem
        CORRENTE aparece em `status()["daytrade"]["ordem_em_pe"]`. O que
        preenche, sim, gera `Intent`/`Order`/`Fill` (ver `_on_opened`)."""
        self._snapshot.ordens_postas += 1
        if self.execution_mode == "live":
            raise NotImplementedError(
                "envio de ordem-limite pendente ao MT5 ainda nao implementado "
                "(`MT5Broker._send` so faz TRADE_ACTION_DEAL, ordem a mercado) — "
                "este slot so pode rodar em execution_mode='shadow' por enquanto. "
                "Degradar para ordem a mercado seria OUTRA estrategia: o robo "
                "pagaria o spread que ele existe para capturar."
            )

    def _on_limit_cancelled(self, conn, account: AccountState, evento: LimitCancelled) -> None:
        """Mesma razao de `_on_limit_placed` para nao gravar evento: e'
        contado, nao narrado."""
        self._snapshot.ordens_abandonadas += 1

    @staticmethod
    def _penetration_ticks(evento: PositionOpened, tick_size: float) -> Optional[float]:
        """Quantos ticks a barra ATRAVESSOU o nivel da ordem-limite.

        E' a medicao que valida (ou refuta) a premissa de maker do robo — ver
        a secao "Modo sombra" na docstring do modulo. `None` para entrada a
        mercado: nao ha nivel para penetrar."""
        if evento.order_kind != "limit" or not tick_size:
            return None
        bar = evento.bar
        bruto = (evento.price - bar.low) if evento.side == "long" else (bar.high - evento.price)
        return round(bruto / tick_size, 3)

    def _on_opened(self, conn, account: AccountState, evento: PositionOpened) -> None:
        """Grava `Intent` + `Order` + `Fill` da ENTRADA e reflete a posicao em
        `live_positions` — para o painel mostrar a mesma coisa que o painel do
        swing mostra, sem um caminho de leitura paralelo.

        Short grava `quantity` NEGATIVA. O schema aceita (nao ha CHECK de
        sinal) e a marcacao a mercado sai correta sem nenhuma mudanca:
        `market_value = price * quantity` fica negativo, que e' exatamente o
        que uma posicao vendida vale."""
        tick = float(getattr(self.strategy, "tick_size", 0.0) or 0.0)
        penetration = self._penetration_ticks(evento, tick)
        assinado = evento.quantity if evento.side == "long" else -evento.quantity

        intent = Intent(
            robot=self.strategy.name,
            role=RobotRole.INVESTMENT,
            kind=IntentKind.ENTER,
            decided_on=evento.ts.date(),
            # Day trade nao tem D+1: a decisao da barra `t` vale na barra
            # `t+1` do MESMO pregao. `execute_on == decided_on` diz isso
            # explicitamente, em vez de fingir uma sessao seguinte.
            execute_on=evento.ts.date(),
            ticker=self.strategy.symbol,
            reason=evento.reason,
            stop_price=evento.stop,
            status=IntentStatus.EXECUTING,
            payload={
                # Declara a CADENCIA: sem isto, `live_store.record_intent`
                # rejeita `execute_on == decided_on` como look-ahead (e esta
                # certo em rejeitar, para a cadencia diaria). Ver
                # `Intent.is_immediate`.
                "cadence": Intent.INTRADAY_CADENCE,
                "side": evento.side,
                "order_kind": evento.order_kind,
                "target": evento.target,
                "bar_ts": evento.ts.isoformat(),
                "bar_ohlc": [evento.bar.open, evento.bar.high, evento.bar.low, evento.bar.close],
                "bar_volume": evento.bar.volume,
                "penetration_ticks": penetration,
                "execution_mode": self.execution_mode,
            },
        )
        intent_id = store.record_intent(conn, account.id, intent)
        self._open_intent_id = intent_id

        order = Order(
            ticker=self.strategy.symbol,
            side=OrderSide.BUY if evento.side == "long" else OrderSide.SELL,
            quantity=evento.quantity,
            order_type=OrderType.LIMIT if evento.order_kind == "limit" else OrderType.MARKET,
            limit_price=evento.price if evento.order_kind == "limit" else None,
            status=OrderStatus.FILLED,
            filled_qty=evento.quantity,
            avg_price=evento.price,
            broker_ref=None,
            intent_id=intent_id,
            sent_at=evento.ts.to_pydatetime(),
            note=_SHADOW_NOTE if self.execution_mode == "shadow" else "entrada day trade",
        )
        order_id = store.record_order(conn, account.id, order)
        store.record_fill(conn, Fill(order_id=order_id, quantity=evento.quantity,
                                     price=evento.price, ts=evento.ts.to_pydatetime()))
        store.set_intent_status(conn, intent_id, IntentStatus.DONE)

        pos = LivePosition(
            ticker=self.strategy.symbol, quantity=assinado, entry_date=evento.ts.date(),
            entry_price=evento.price, capital_allocated=abs(evento.price * evento.quantity),
            current_stop=evento.stop, max_price_seen=evento.price, min_price_seen=evento.price,
            bars_held=0, metadata={"side": evento.side, "target": evento.target,
                                   "penetration_ticks": penetration,
                                   "execution_mode": self.execution_mode},
        )
        store.upsert_position(conn, account.id, pos)
        account.positions[pos.ticker] = pos

        self._log(conn, account.id, "info",
                  f"{'SOMBRA: ' if self.execution_mode == 'shadow' else ''}entrada "
                  f"{evento.side} {evento.quantity} {self.strategy.symbol} @ {evento.price:.4f} "
                  f"({evento.order_kind}; penetracao "
                  f"{'n/a' if penetration is None else f'{penetration:.2f} tick(s)'})",
                  {"side": evento.side, "price": evento.price, "quantity": evento.quantity,
                   "penetration_ticks": penetration, "execution_mode": self.execution_mode})

    def _on_closed(self, conn, account: AccountState, evento: PositionClosed, bar: Bar) -> None:
        """Grava a saida e move o P&L para onde ele PODE ir.

        Em sombra o caixa NAO e' tocado: o ledger manual e' o numero que o
        dono digitou, e sujar isso com lucro/prejuizo imaginario destruiria a
        unica fonte de verdade de caixa que temos (ver
        `dashboard/app.py::operacao_caixa`). O resultado sombra acumula em
        `policy_state`, separado, e aparece no painel como tal."""
        trade = evento.trade
        assinado_saida = trade.quantity if trade.side == "short" else -trade.quantity

        order = Order(
            ticker=self.strategy.symbol,
            side=OrderSide.SELL if trade.side == "long" else OrderSide.BUY,
            quantity=trade.quantity,
            # Alvo e' saida planejada (ordem-limite no nivel); stop, flatten e
            # sinal sao saidas por urgencia — vao a mercado. Mesma distincao
            # de `IntradayBacktestConfig.target_fills_as_maker`.
            order_type=(OrderType.LIMIT if trade.exit_reason.value == "target" else OrderType.MARKET),
            limit_price=trade.exit_price if trade.exit_reason.value == "target" else None,
            status=OrderStatus.FILLED,
            filled_qty=trade.quantity,
            avg_price=trade.exit_price,
            fees=trade.fees_total,
            slippage=trade.slippage_total,
            broker_ref=None,
            intent_id=self._open_intent_id,
            sent_at=trade.exit_ts.to_pydatetime(),
            note=(_SHADOW_NOTE if self.execution_mode == "shadow"
                  else f"saida day trade ({trade.exit_reason.value})"),
        )
        order_id = store.record_order(conn, account.id, order)
        store.record_fill(conn, Fill(order_id=order_id, quantity=trade.quantity,
                                     price=trade.exit_price, fees=trade.fees_total,
                                     ts=trade.exit_ts.to_pydatetime()))

        store.delete_position(conn, account.id, self.strategy.symbol)
        account.positions.pop(self.strategy.symbol, None)
        self._open_intent_id = None
        self._snapshot.trades += 1

        if self.execution_mode == "shadow":
            self._snapshot.shadow_pnl_brl += evento.pnl_brl
        else:
            account.cash += evento.pnl_brl

        self._log(conn, account.id, "info",
                  f"{'SOMBRA: ' if self.execution_mode == 'shadow' else ''}saida "
                  f"{trade.side} {trade.quantity} {self.strategy.symbol} @ {trade.exit_price:.4f} "
                  f"({trade.exit_reason.value}) — resultado R$ {evento.pnl_brl:+.2f}",
                  {"exit_reason": trade.exit_reason.value, "pnl_brl": round(evento.pnl_brl, 4),
                   "entry_price": trade.entry_price, "exit_price": trade.exit_price,
                   "execution_mode": self.execution_mode,
                   "assinado_saida": assinado_saida})

    # ---------- painel -------------------------------------------------------

    def status(self) -> dict:
        """Mesmo formato de `LiveRuntime.status()` — o template de `/operacao`
        le as duas fontes pelas mesmas chaves. Campos que so o day trade tem
        (sombra, penetracao) entram em `daytrade`, sem colidir."""
        session = clock.session_date()
        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return {"conta": self.account_name, "existe": False}
            self._restore(account, session)
            eventos = store.recent_events(conn, account.id, limit=10)

        pos = self.machine.position
        marks = {self.strategy.symbol: pos.entry_price} if pos is not None else {}
        return {
            "conta": account.name,
            "existe": True,
            "modo": account.mode,
            "kind": "intraday",
            "robo_investimento": account.investment_robot,
            "robo_saque": "",
            "pregao": session.isoformat(),
            "fase": clock.phase().value,
            "decisao_pendente": [],
            "notificador": type(self.notifier).__name__,
            "feed": {"nome": self.bar_feed.name, "tempo_real": True,
                     "atraso_s": 60.0},
            "corretora": {"nome": self.broker.name, "modo": self.broker.mode,
                          "automatica": self.broker.supports_automation()},
            "disjuntor": None,
            "caixa": round(account.cash, 2),
            "investido": round(account.invested(marks), 2),
            "carteira": round(account.equity(marks), 2),
            "caixa_externo": round(account.external_cash, 2),
            "patrimonio": round(account.patrimonio(marks), 2),
            "sacado_total": round(account.withdrawn_total, 2),
            "posicoes": [
                {"ticker": p.ticker, "qtd": p.quantity, "entrada": round(p.entry_price, 4),
                 "stop": round(p.current_stop, 4) if p.current_stop else None,
                 "barras": p.bars_held,
                 "valor": round(p.market_value(marks.get(p.ticker, p.entry_price)), 2)}
                for p in account.positions.values()
            ],
            "intencoes_pendentes": [],
            "eventos": eventos,
            "daytrade": {
                "execution_mode": self.execution_mode,
                "simbolo": self.strategy.symbol,
                "sessao": self._snapshot.session.isoformat() if self._snapshot.session else None,
                "ultima_barra": (self._snapshot.last_bar_ts.isoformat()
                                 if self._snapshot.last_bar_ts is not None else None),
                "trades_na_sessao": self._snapshot.trades,
                "ordens_postas": self._snapshot.ordens_postas,
                "ordens_abandonadas": self._snapshot.ordens_abandonadas,
                "resultado_sombra": round(self._snapshot.shadow_pnl_brl, 2),
                "resultado_sessao": round(self.machine.session_pnl, 2),
                "posicao_aberta": None if pos is None else {
                    "lado": pos.side, "qtd": pos.quantity,
                    "entrada": round(pos.entry_price, 4),
                    "alvo": pos.current_target, "stop": pos.current_stop,
                },
                "ordem_em_pe": None if self.machine.resting_limit is None else {
                    "lado": self.machine.resting_limit.side,
                    "preco": self.machine.resting_limit.limit_price,
                },
                # O offset nao e' mais "calibrado ou presumido": ele e'
                # declarado a partir do fuso medido do servidor. O que o painel
                # precisa mostrar agora e' se a CONFERENCIA acusou divergencia
                # — `None` = nada provado errado.
                "offset_horas": self.bar_feed.offset_hours,
                "corte_flatten_utc": self.machine.session_end_time_for(
                    pd.Timestamp(session)
                ).isoformat(),
                "relogio_alarme": (self.clock_feed.server_clock_alarm
                                   if self.clock_feed is not None else None),
            },
        }
