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
ofertas. Cada entrada em sombra grava DOIS numeros para atacar essa pergunta,
porque nenhum dos dois serve nas duas granularidades:

  - `penetration_ticks`: quantos ticks a barra ATRAVESSOU o nivel. Toques de
    0-1 tick indicam premissa fragil (a ordem podia estar atras na fila e
    nunca executar); barras que atravessam varios ticks quase certamente
    preencheriam uma ordem parada. So' faz sentido com feed M1 — uma barra
    precisa TER faixa para atravessar alguma coisa. Com feed de tick sai
    `None` (ver `_penetration_ticks`): um negocio e' um preco so', a
    penetracao seria zero em 100% dos casos por construcao, e gravar esse zero
    leria como "premissa sempre fragil" quando a pergunta e' que nao cabe.

  - `volume_no_nivel`: quantas acoes NEGOCIARAM no nivel (ou alem dele)
    enquanto a ordem estava em pe, ate' o fill inclusive, contra a quantidade
    que o robo pediu (`quantidade_pedida`, gravada junto). E' a mesma pergunta
    de fila feita de um jeito que o tick responde e o M1 tambem: se 40.000
    acoes passaram pelo meu nivel e eu queria 200, a fila quase certamente
    chegou em mim; se passaram 200 e eu queria 200, o preenchimento que o
    backtest assumiu era otimismo.

Sem esses campos, rodar em sombra nao responde a pergunta que motivou o modo.

Duas granularidades, o MESMO runtime
------------------------------------
`bar_feed` pode ser `live/bar_feed.py::MT5BarFeed` (barra M1 fechada) ou
`live/tick_feed.py::MT5TickFeed` (negocio a negocio) — os dois tem a mesma
interface, e quem escolhe e' o proprio robo, via `IntradayStrategy.feed_kind`
(montado em `live/intraday_feed.py::feed_for`). Nada aqui pergunta qual dos
dois esta lendo: a unidade e' sempre "um evento de preco ja' consumado", e o
motor (`IntradaySessionMachine`) e' resolution-agnostic por construcao.

O que MUDA de verdade entre os dois nao esta neste arquivo, esta na
divergencia abaixo.

Divergencia honesta declarada — e o que o tick apaga dela
----------------------------------------------------------
Com feed M1, stop e alvo resolvem em barra FECHADA: o robo reage ate 60s
depois do que o backtest intrabar assume. Nao ha correcao possivel do lado do
robo (um stop por tick seria uma REGRA DIFERENTE da validada, o que a regra 6
proibe) — a correcao real e' SL/TP no lado da corretora, trabalho separado.

Com feed de TICK essa divergencia especifica desaparece: o robo reavalia stop
e alvo a cada negocio, que e' a mesma granularidade em que o backtest de tick
o validou. Some tambem a ambiguidade "stop e alvo tocados na mesma barra"
(`IntradayBacktestConfig.ambiguous_bar_resolution`), porque um negocio tem um
preco so'. O que NAO some, e continua sendo custo conhecido nos dois casos: o
passo do supervisor (5s) e a premissa de maker, que e' justamente o que
`penetration_ticks` existe para medir.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
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
from live.intraday_execution import MT5IntradayExecution
from live.notify import NullNotifier
from live.runtime import StepReport
from strategy.daytrade.base import (
    Bar,
    EnterLimit,
    barra_diaria,
    capital_minimo_brl,
    mediana_negocio_diario,
    warm_start_calibration,
)

#: Acima disto sem RODAR um passo, nao e' "o processo demorou um pouco" — e' o
#: processo tendo ficado fora do ar. Reprocessar 15 minutos de eventos de uma
#: vez faria o robo tomar dezenas de decisoes contra precos que ja passaram;
#: achatar e recomecar e' a leitura honesta. Casa em espirito com
#: `Strategy.on_missed_bars` do lado diario (ver
#: `missed_session_policy_2026_08_20` na memoria do projeto): o buraco nunca e'
#: ignorado, e a decisao velha nunca e' executada.
#:
#: E' tempo SEM RODAR, e nao quantidade de eventos acumulados — a diferenca
#: importa desde que existe feed de tick. Em M1 os dois mediam a mesma coisa
#: (chega 1 barra por minuto, entao 15 barras == 15 minutos fora do ar). Em
#: tick nao: um papel iliquido pode passar horas sem um unico negocio com o
#: processo perfeitamente vivo, e uma rajada de 50 negocios em 10 segundos e'
#: pregao normal. Contar eventos declararia buraco nos dois casos errados.
MAX_GAP_SECONDS = 15 * 60.0

_SHADOW_NOTE = "SHADOW — nao enviada ao MT5"

#: Sentinela de "fim do pregao" para pedir a SESSAO INTEIRA anterior via
#: `bar_feed.session_bars_until(previous_session, ate)` -- o metodo ja
#: recorta pelo `session` pedido (ver `MT5BarFeed`/`MT5TickFeed`), entao um
#: `ate` bem no futuro so' garante nao cortar a cauda real do pregao
#: anterior antes da hora.
_FIM_DE_PREGAO_QUALQUER = pd.Timestamp("2999-01-01", tz="UTC")

#: Folga sobre a janela rolante default do robo (30min,
#: `strategy.daytrade.base.RollingVolumeWindow`) para decidir quanto da
#: sessao anterior pedir ao feed antes de repassar a `seed_volume_window` --
#: generico o bastante para qualquer janela configurada sem pedir o pregao
#: anterior inteiro.
_CAUDA_VOLUME_MINUTOS = 90.0

#: Quantas sessoes anteriores buscar do feed para `seed_daily_volatility` --
#: generoso sobre a janela default do robo (`vol_janela_dias=10`,
#: `strategy.daytrade.lab.gremah.Gremah`/`gremah_tick.GremahTick`), mesmo
#: espirito de `_CAUDA_VOLUME_MINUTOS` acima: nao pede o historico inteiro,
#: so' o bastante pra cobrir qualquer janela configurada.
_CAUDA_VOL_DIAS = 15


@dataclass
class _SessionSnapshot:
    """O que sobrevive a um restart do processo, dentro de
    `policy_state["intraday"]`."""

    session: Optional[date] = None
    last_bar_ts: Optional[pd.Timestamp] = None
    #: Quando este slot rodou um passo pela ultima vez dentro do pregao. E' a
    #: base do detector de buraco (`MAX_GAP_SECONDS`) — persistido, e nao so'
    #: em memoria, porque o caso que ele existe para pegar e' justamente o
    #: processo que morreu e voltou.
    last_poll_at: Optional[pd.Timestamp] = None
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
    # Tickets REAIS (`Order.broker_ref`) da(s) ordem-limite de ENTRADA que
    # `resting_limit`/`_resting_children_qty` da maquina vigiam AGORA --
    # espelho, do lado da entrada, do mesmo gap de restart ja fechado do lado
    # da saida (ver `IntradaySessionMachine.restore`). Diferente da saida,
    # aqui a correcao NAO precisa falhar alto: uma ordem de COMPRA parada que
    # sobrou de um processo anterior e' risco baixo (nao ha posicao exposta
    # esperando ela), entao da para RECONCILIAR sozinho -- cancelar o(s)
    # ticket(s) direto pelo `broker_ref` persistido, sem depender do estado em
    # memoria de `MT5IntradayExecution` (que nasce vazio a cada processo
    # novo). So' e' zerado nos pontos onde a resolucao e' CONFIRMADA
    # (`_on_limit_cancelled`, ou `_on_opened` quando o ultimo filho preenche e
    # `resting_limit` vira `None`) -- nunca so' porque `resting_limit` esta
    # `None` num instante qualquer, que tambem e' verdade logo apos um
    # restart ANTES de o robo decidir de novo, e limpar cedo demais perderia
    # o rastro do ticket que ainda precisa ser cancelado. Consultado em
    # `_start_session` (warm start) e `_on_limit_placed` (decisao nova).
    pending_entry_refs: list = None

    def to_dict(self) -> dict:
        return {
            "session": self.session.isoformat() if self.session else None,
            "last_bar_ts": self.last_bar_ts.isoformat() if self.last_bar_ts is not None else None,
            "last_poll_at": (self.last_poll_at.isoformat()
                             if self.last_poll_at is not None else None),
            "shadow_pnl_brl": round(self.shadow_pnl_brl, 4),
            "trades": self.trades,
            "ordens_postas": self.ordens_postas,
            "ordens_abandonadas": self.ordens_abandonadas,
            "machine": self.machine or {},
            "pending_entry_refs": list(self.pending_entry_refs or []),
        }

    @classmethod
    def from_dict(cls, raw: Optional[dict]) -> "_SessionSnapshot":
        raw = raw or {}
        sess = raw.get("session")
        last = raw.get("last_bar_ts")
        poll = raw.get("last_poll_at")
        return cls(
            session=date.fromisoformat(sess) if sess else None,
            last_bar_ts=pd.Timestamp(last) if last else None,
            last_poll_at=pd.Timestamp(poll) if poll else None,
            shadow_pnl_brl=float(raw.get("shadow_pnl_brl") or 0.0),
            trades=int(raw.get("trades") or 0),
            ordens_postas=int(raw.get("ordens_postas") or 0),
            ordens_abandonadas=int(raw.get("ordens_abandonadas") or 0),
            machine=raw.get("machine") or {},
            pending_entry_refs=list(raw.get("pending_entry_refs") or []),
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
        # O CAPITAL DECLARADO DO SLOT ENTRA NA CONFIG, e nao so' na conta.
        #
        # `IntradayBacktestConfig.initial_capital` tem default de R$20.000, e a
        # maquina o usa em dois lugares que decidem dinheiro de verdade: e' o
        # numero que chega em `IntradayStrategy.on_capital_update` (o caixa que
        # a `gremah`/`gremah_tick` usam para escolher QUANTOS LOTES pedir) e a
        # `capital_base` de cada trade gravado. Ate 2026-08-22 nenhum montador
        # de runtime ao vivo o sobrescrevia: o robo dimensionava contra
        # R$20.000 imaginarios enquanto o dono tinha R$100 no ledger. Na PMAM3
        # a R$0,13 isso e' a diferenca entre 2 lotes e 385 — uma perda de 1
        # tick vira R$385 em vez de R$2, e estoura o teto de perda diaria
        # (R$5,20) num unico trade, no primeiro trade.
        #
        # `replace` porque o dataclass e' frozen: a config continua imutavel,
        # so' nasce com o numero certo.
        self.initial_capital = float(initial_capital)
        self.config = replace(config, initial_capital=self.initial_capital)
        self.bar_feed = bar_feed
        self.broker = broker
        self.notifier = notifier if notifier is not None else NullNotifier()
        self.execution_mode = execution_mode
        self.db_path = Path(db_path) if db_path is not None else LIVE_DB_PATH
        # So o modo REAL injeta a ponte de execucao na maquina. Em sombra ela
        # fica `None` e os fills seguem simulados pela barra -- que e'
        # exatamente o que o modo sombra existe para medir contra a realidade
        # (ver `penetration_ticks`). Ver `live/intraday_execution.py` para por
        # que a fonte de verdade tem de trocar quando ha dinheiro em jogo.
        self.executor = (
            MT5IntradayExecution(broker, strategy.symbol)
            if execution_mode == "live" else None
        )
        # `self.config`, nunca o `config` recebido: e' a versao com o capital
        # real do slot (ver o bloco acima). Passar o argumento cru aqui era
        # justamente o que mantinha a maquina dimensionando contra R$20.000.
        self.machine = IntradaySessionMachine(strategy, self.config, execution=self.executor)
        self._snapshot = _SessionSnapshot()
        # Acoes negociadas no nivel da ordem-limite que esta em pe AGORA (ver
        # `_acumula_volume_no_nivel`). So em memoria, e nao no snapshot: e' a
        # medicao de UMA ordem, e uma ordem nao sobrevive a um restart do
        # processo — a maquina volta com a `resting_limit` restaurada, mas o
        # que negociou nela enquanto o processo estava morto ninguem viu.
        # Persistir um numero parcial daria a impressao de uma medicao
        # completa.
        self._volume_no_nivel = 0.0
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
        # Conferencia de caixa, 1x por pregao (ver `_check_capital`). O minimo
        # depende do PRECO do dia, entao nao da' para decidir isto uma vez e
        # esquecer -- e tambem nao vale reavaliar a cada barra, porque o
        # numero so muda de pregao para pregao.
        self._capital_checked_for: Optional[date] = None
        self._capital_alarm: Optional[str] = None
        self._capital_minimo_hoje: Optional[float] = None
        # Aviso de capital disponivel (`_avaliar_sugestao_de_capital`), tambem
        # 1x por pregao e pelo mesmo motivo: a regra depende do preco do dia.
        # A deduplicacao POR ATIVO e' do banco (`UNIQUE` em
        # `live_capital_signals`); este campo so evita reavaliar a regra e
        # reler parquet a cada barra.
        self._signal_checked_for: Optional[date] = None

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
                # O ATIVO faz parte da identidade da conta de day trade (uma
                # conta por par robo+ativo, desde 2026-08-22): e' o que permite
                # ao painel saber quais papeis ja estao alocados e ao proprio
                # robo nao sugerir um que ja roda. `ensure_account` recusa se a
                # conta ja existir com OUTRO simbolo.
                symbol=self.strategy.symbol,
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

    def _seed_volume_window(self, session: date) -> None:
        """Busca a CAUDA do pregao anterior e repassa para
        `IntradayStrategy.seed_volume_window` -- so' um robo com teto de
        posicao por volume rolante (`Gremah`/`GremahTick`, ver
        `strategy.daytrade.base.RollingVolumeWindow`) usa isto; os outros
        recebem uma lista que nunca consultam (default no-op na base).

        Chamado a CADA `_start_session` (inclusive num restart no meio do
        pregao, mesmo espirito do warm start) -- refazer a busca e' uma
        chamada extra ao feed, nao um erro: `session_bars_until` nunca
        levanta excecao (lista vazia se o terminal falhar, ver
        `MT5BarFeed`/`MT5TickFeed`), entao o pior caso e' o robo operar sem
        cauda, igual a um pregao sem historico anterior disponivel."""
        anterior = clock.previous_session(session)
        cauda = self.bar_feed.session_bars_until(anterior, _FIM_DE_PREGAO_QUALQUER)
        if cauda:
            corte = cauda[-1].ts - pd.Timedelta(minutes=_CAUDA_VOLUME_MINUTOS)
            cauda = [b for b in cauda if b.ts > corte]
        self.strategy.seed_volume_window(cauda)

    def _seed_daily_volatility(self, session: date) -> None:
        """Busca as `_CAUDA_VOL_DIAS` sessoes ANTERIORES, agrega cada uma
        numa barra diaria (`strategy.daytrade.base.barra_diaria`) e repassa
        para `IntradayStrategy.seed_daily_volatility` -- so' um robo com
        alvo dimensionado por volatilidade (`Gremah`/`GremahTick`, ver
        `strategy.daytrade.base.JanelaVolatilidadeDiaria`) usa isto; os
        outros recebem uma lista que nunca consultam (default no-op na
        base).

        Chamado a CADA `_start_session`, mesmo espirito de
        `_seed_volume_window` -- `session_bars_until` nunca levanta
        excecao (lista vazia se o terminal falhar), entao o pior caso e' o
        robo operar sem a janela, igual a um pregao sem historico
        anterior disponivel. Ordem devolvida: mais antiga primeiro, igual
        `backtest.intraday.engine`."""
        diarias: list[Bar] = []
        dia = session
        for _ in range(_CAUDA_VOL_DIAS):
            dia = clock.previous_session(dia)
            bars_do_dia = self.bar_feed.session_bars_until(dia, _FIM_DE_PREGAO_QUALQUER)
            diaria = barra_diaria(bars_do_dia)
            if diaria is not None:
                diarias.append(diaria)
        diarias.reverse()
        self.strategy.seed_daily_volatility(diarias)

    def _seed_typical_trade_size(self, session: date) -> None:
        """Mesmo espirito/janela de `_seed_daily_volatility` acima, so' que
        para o teto de CAPACIDADE de caixa (`strategy.daytrade.base.
        JanelaNegocioTipicoDiaria`) em vez do alvo por volatilidade -- so'
        um robo com esse teto (`GremahTick`, 2026-08-24) usa isto; os
        outros recebem uma lista que nunca consultam (default no-op na
        base). Reusa `_CAUDA_VOL_DIAS` sessoes de folga (generoso sobre o
        default `janela_dias=1` do robo) e o mesmo feed ja' buscado por
        `_seed_daily_volatility` -- so' agrega diferente (mediana de
        evento, nao OHLCV)."""
        medianas: list[float] = []
        dia = session
        for _ in range(_CAUDA_VOL_DIAS):
            dia = clock.previous_session(dia)
            bars_do_dia = self.bar_feed.session_bars_until(dia, _FIM_DE_PREGAO_QUALQUER)
            mediana = mediana_negocio_diario(bars_do_dia)
            if mediana is not None:
                medianas.append(mediana)
        medianas.reverse()
        self.strategy.seed_typical_trade_size(medianas)

    def _start_session(self, conn, account: AccountState, session: date, now: datetime) -> StepReport:
        """Calibra o robo para este pregao e (re)abre a sessao na maquina.

        Chamado uma vez por PROCESSO por pregao — inclusive depois de um
        restart no meio do pregao, porque o estado interno do robo nao e'
        persistido (ver `_calibrated_for`). Quando ha snapshot restaurado do
        MESMO pregao, o P&L da sessao e o flag de flatten sao devolvidos por
        cima do reset: o stop agregado de sessao do robo (`session_stop_pct_capital`,
        em `strategy.daytrade.lab.gremah.Gremah`) le esse numero, e zera-lo
        num restart daria ao robo uma folga de risco que ele nao tem."""
        restaurada = self._snapshot.session == session and bool(self._snapshot.machine)
        pnl_antes, flat_antes = self.machine.session_pnl, self.machine.flattened

        self._seed_volume_window(session)
        self._seed_daily_volatility(session)
        self._seed_typical_trade_size(session)

        modo = "cold"
        semente = 0
        if self._needs_warm_start(now):
            seed_bars = self.bar_feed.session_bars_until(session, pd.Timestamp(now))
            if seed_bars:
                pending = warm_start_calibration(self.strategy, session, seed_bars)
                self.machine.resume_session(session, seed_pending=pending)
                # `resume_session` planta a ordem do warm start direto em
                # `resting_limit`, SEM passar por `LimitPlaced` (nao ha barra
                # sendo consumida). Em execucao real isso a deixaria vigiada
                # aqui dentro e inexistente na corretora: o robo esperaria por
                # um fill que nunca poderia acontecer, porque ninguem chegou a
                # registrar a ordem. Registrar aqui e' o que fecha esse buraco.
                if self.executor is not None and isinstance(pending, EnterLimit):
                    if self._snapshot.pending_entry_refs:
                        # Restart no meio do pregao com uma ordem ja' armada:
                        # `warm_start_calibration` acabou de RECALCULAR a
                        # decisao do zero a partir do dado real, mas o(s)
                        # ticket(s) que o processo ANTERIOR mandou pra
                        # corretora (persistidos em `pending_entry_refs`) nao
                        # somem sozinhos so' porque este processo nao lembra
                        # deles. Sem cancelar primeiro, a linha abaixo mandaria
                        # uma SEGUNDA ordem de compra por cima -- risco baixo
                        # (nenhuma posicao fica exposta esperando ela, ver
                        # docstring de `pending_entry_refs`), mas ainda uma
                        # entrada em dobro se as duas preencherem.
                        self.executor.cancel_stale_refs(
                            self._snapshot.pending_entry_refs, ts=seed_bars[-1].ts,
                        )
                        self._snapshot.pending_entry_refs = []
                    enviadas = self.executor.place_limit(
                        side=pending.side, limit_price=pending.limit_price,
                        quantities=pending.children(self.config.default_quantity),
                        ts=seed_bars[-1].ts,
                    )
                    self._snapshot.pending_entry_refs = [o.broker_ref for o in enviadas if o.broker_ref]
                modo, semente = "warm_start", len(seed_bars)
                self._snapshot.session = session
                # NUNCA anda pra tras: num restart (`restaurada=True`) o
                # snapshot ja pode ter avancado alem do fim da semente de
                # HOJE (`session_bars_until` busca de novo, do zero, e pode
                # devolver menos barra que o processo anterior ja tinha
                # consumido de verdade). Sobrescrever incondicionalmente
                # fazia o robo REPROCESSAR uma barra ja consumida na
                # proxima chamada de `run_once` -- contra uma posicao ja
                # REAL (restaurada por `_restore`, chamado ANTES desta
                # funcao), fechando-a por engano (achado 2026-08-22, ao
                # ligar `resume_session` a ignorar semente sobre posicao ja
                # restaurada -- sem aquele fix este bug ficava mascarado
                # por um SEGUNDO bug que reabria a posicao na mesma barra).
                marco = seed_bars[-1].ts
                if restaurada and self._snapshot.last_bar_ts is not None:
                    marco = max(marco, self._snapshot.last_bar_ts)
                self._snapshot.last_bar_ts = marco
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

            # Ha' quanto tempo este slot nao roda um passo. Lido ANTES de
            # carimbar o passo de agora, senao seria sempre zero.
            parado_ha = self._parado_ha_segundos(now)
            self._snapshot.last_poll_at = pd.Timestamp(now)

            barras = self.bar_feed.closed_bars_since(self._snapshot.last_bar_ts)
            if not barras:
                self._persist(conn, account)
                return passos + [StepReport("daytrade_espera", hoje, phase=fase,
                                            detail={"ultima_barra": str(self._snapshot.last_bar_ts)})]

            # Caixa suficiente para o lote de hoje? So aqui, e nao antes, porque
            # o minimo depende do PRECO e a primeira barra fechada e' a primeira
            # coisa que da esse preco de forma confiavel.
            alarme_capital = self._check_capital(conn, account, hoje, barras[-1].close)
            # Aviso de capital para um ativo NOVO — avaliado antes do desvio
            # abaixo de proposito: e' informacao para o dono, e nao deve sumir
            # justamente no pregao em que o robo nao vai operar.
            self._avaliar_sugestao_de_capital(conn, account, hoje, barras[-1].close)
            if alarme_capital is not None and self.machine.position is None:
                # Sem posicao aberta: nao comeca. Avanca `last_bar_ts` de
                # proposito -- ficar sem consumir faria o robo, quando o caixa
                # enfim cobrisse o minimo, receber de uma vez todo o dado que
                # passou enquanto ele estava barrado, e decidir contra precos
                # que ja foram.
                self._snapshot.last_bar_ts = barras[-1].ts
                self._persist(conn, account)
                return passos + [StepReport("daytrade_skip", hoje, phase=fase,
                                            detail={"motivo": "caixa abaixo do minimo",
                                                    "alarme": alarme_capital})]

            if parado_ha is not None and parado_ha > MAX_GAP_SECONDS:
                passos.append(self._handle_gap(conn, account, hoje, barras, parado_ha))
            else:
                passos.append(self._consume(conn, account, hoje, barras))

            self._persist(conn, account)
        return passos

    def _parado_ha_segundos(self, now: datetime) -> Optional[float]:
        """Segundos desde o ultimo passo deste slot NESTE pregao, ou `None` se
        e' o primeiro (nada a comparar — um pregao que comeca nao e' um
        buraco). Ver `MAX_GAP_SECONDS` para por que a medida e' tempo sem
        rodar, e nao eventos acumulados."""
        anterior = self._snapshot.last_poll_at
        if anterior is None:
            return None
        return (pd.Timestamp(now) - anterior).total_seconds()

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

    def _check_capital(
        self, conn, account: AccountState, session: date, preco: float
    ) -> Optional[str]:
        """O caixa deste slot cobre o lote de hoje? Devolve o motivo, ou
        `None` se cobre.

        O minimo e' `strategy.daytrade.base.capital_minimo_brl` — 2x o custo de
        1 lote no preco de HOJE. Nao e' regra inventada aqui (AGENTS.md #6
        proibiria): `live/` so consulta a funcao que a familia intradiaria
        declara, a MESMA que a ficha do robo exibe e que dimensionou o capital
        de todo backtest da tabela de calibracao.

        Uma vez por PREGAO, nao a cada barra: o numero so muda quando o preco
        de referencia do dia muda, e reavaliar a cada minuto sujaria o diario
        com o mesmo evento centenas de vezes. Mas tambem nao da' para decidir
        uma vez e congelar — CSAN3 saiu de R$7,62 para R$3,64 em 11 meses
        (minimo de R$1.524 para R$728), e PMAM3 caiu 90%: um piso congelado
        estaria errado nos dois sentidos, ora barrando um robo que cabe, ora
        liberando um que nao cabe mais.

        Quem chama decide o que fazer com o alarme. A politica em `run_once`
        e': sem posicao aberta, nao comeca o pregao; COM posicao aberta (o
        processo subiu no meio do dia e restaurou o snapshot), deixa rodar --
        um robo sem caixa ainda precisa conseguir FECHAR o que ja esta na rua,
        e travar aqui deixaria a posicao orfa ate o flatten.

        O saldo conferido e' `account.cash_for(self.execution_mode)` (pedido
        do dono, 2026-08-23): um robo em `execution_mode="shadow"` dimensiona
        e opera contra `cash_sombra`, nunca `cash` -- sem isto, o piso de
        inicio (`live_control.start()`, tambem mode-aware) deixava o robo
        SUBIR usando o saldo de sombra, so' para este gate recusar toda barra
        do dia seguinte comparando contra o caixa real, que pode ser bem
        menor (ou zero)."""
        if self._capital_checked_for == session:
            return self._capital_alarm

        minimo = capital_minimo_brl(preco, self.config.default_quantity)
        self._capital_checked_for = session
        self._capital_minimo_hoje = minimo
        saldo = account.cash_for(self.execution_mode)

        if saldo >= minimo:
            self._capital_alarm = None
            return None

        self._capital_alarm = (
            f"caixa de R$ {saldo:.2f} nao cobre o minimo de R$ {minimo:.2f} "
            f"para operar {self.strategy.symbol} hoje ({self.config.default_quantity} "
            f"acoes a R$ {preco:.4f} = R$ {preco * self.config.default_quantity:.2f} "
            f"por lote, e o piso e' o dobro do lote)"
        )
        self._log(conn, account.id, "error",
                  f"nao vou operar: {self._capital_alarm}",
                  {"pregao": session.isoformat(), "caixa": round(saldo, 2),
                   "minimo": round(minimo, 2), "preco": preco,
                   "quantidade": self.config.default_quantity})
        return self._capital_alarm

    def _avaliar_sugestao_de_capital(
        self, conn, account: AccountState, session: date, preco: float
    ) -> None:
        """Uma vez por pregao: este robo ja juntou caixa que banque um robo
        NOVO em outro ativo? Se sim, grava o aviso para o dono ver no painel.

        NAO abre robo, nao move dinheiro, nao aporta nada. A regra e' de
        `strategy.daytrade.enxame.avaliar_sugestao` (regra 6 do AGENTS.md —
        `live/` aplica regra declarada, nunca inventa a propria); aqui so se
        junta o que ela precisa saber do MUNDO: quais ativos ja estao
        alocados, quanto o dono ja aportou nos outros robos, e o preco de hoje
        do proximo da fila.

        O caixa usado e' o `account.cash` REAL (o ledger que o dono digitou,
        mais o que o robo realizou em modo `live`) — nunca o P&L de sombra.
        Em modo sombra o robo nao ganhou dinheiro nenhum, e sugerir um aporte
        novo com base em lucro imaginario seria pedir dinheiro de verdade
        contra resultado que nao existe.

        Nunca levanta: um aviso e' conveniencia, e nenhuma falha aqui
        (parquet ausente, simbolo sem calibracao, robo fora do registry) pode
        derrubar o robo que esta operando dinheiro.
        """
        if self._signal_checked_for == session:
            return
        self._signal_checked_for = session
        try:
            from market_data_intraday.storage import last_close
            from strategy.daytrade.enxame import Candidato, avaliar_sugestao
            from strategy.daytrade.registry import symbols_for_robot

            outras = [a for a in store.accounts_with_symbol(conn)
                      if a.name != self.account_name]
            ocupados = {a.symbol for a in outras if a.symbol}
            ocupados.add(self.strategy.symbol)
            fila = [s for s in symbols_for_robot(self.strategy.name) if s not in ocupados]
            if not fila:
                return
            # So o PRIMEIRO da fila e' consultado: a fila e' estrita e nunca
            # pula (ver `strategy.daytrade.enxame`). Isso tambem mantem o custo
            # em UMA leitura de parquet por pregao.
            preco_candidato, _data = last_close(fila[0])
            sugestao = avaliar_sugestao(
                caixa_brl=account.cash,
                preco_proprio=preco,
                candidatos=[Candidato(symbol=fila[0], preco_atual=preco_candidato or 0.0,
                                      shares_per_lot=self.config.default_quantity)],
                # O que o dono JA pos do bolso nos outros robos. E' o
                # abatimento que faz a barra subir a cada robo novo — sem ele,
                # o mesmo caixa aprovaria a fila inteira de uma vez.
                ja_aportado_brl=sum(a.initial_capital for a in outras),
                shares_per_lot=self.config.default_quantity,
            )
            if sugestao is None:
                return
            novo = store.record_capital_signal(
                conn, account_id=account.id, robot=self.strategy.name,
                suggested_symbol=sugestao.symbol,
                cash_brl=sugestao.cash_brl, required_brl=sugestao.required_brl,
            )
            if novo:
                self._log(
                    conn, account.id, "info",
                    f"da' para abrir {self.strategy.name} em {sugestao.symbol}: "
                    f"caixa R$ {sugestao.cash_brl:.2f} (R$ {sugestao.disponivel_brl:.2f} "
                    f"livres, ja descontado o que voce aportou nos outros robos) "
                    f"cobre os R$ {sugestao.required_brl:.2f} que {sugestao.symbol} exige "
                    f"e o minimo de {self.strategy.symbol}.",
                    {"pregao": session.isoformat(), "sugestao": sugestao.symbol,
                     "necessario": round(sugestao.required_brl, 2),
                     "disponivel": round(sugestao.disponivel_brl, 2)},
                )
        except Exception as e:  # noqa: BLE001 — ver docstring: aviso nunca derruba robo
            self._log(conn, account.id, "warn",
                      f"nao consegui avaliar sugestao de capital: {e}",
                      {"pregao": session.isoformat()})

    def _handle_gap(self, conn, account: AccountState, session: date,
                    barras: list[Bar], parado_ha: float) -> StepReport:
        """Buraco grande: o processo ficou fora do ar. Nao reprocessa (isso
        seria tomar decisoes velhas contra precos que ja passaram) — achata a
        posicao com o evento de preco MAIS RECENTE e recomeca a sessao dali."""
        ultima = barras[-1]
        fechados = []
        for evento in self.machine.force_flatten(ultima.ts, ultima.close):
            if isinstance(evento, PositionClosed):
                fechados.append(evento)
            self._apply(conn, account, evento, ultima)
        self._log(conn, account.id, "error",
                  f"buraco de {parado_ha / 60.0:.0f} minuto(s) sem rodar no pregao "
                  f"{session.isoformat()} — o processo ficou fora do ar. Nao "
                  f"reprocessei os {len(barras)} evento(s) acumulados (decisao velha "
                  "nunca executa, regra 7 do AGENTS.md); "
                  f"{'posicao achatada e ' if fechados else ''}sessao reiniciada em "
                  f"{ultima.ts.isoformat()}.",
                  {"parado_segundos": round(parado_ha, 1), "eventos": len(barras),
                   "achatou": bool(fechados)})
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
                          detail={"parado_segundos": round(parado_ha, 1),
                                  "eventos": len(barras), "achatou": bool(fechados)})

    def _acumula_volume_no_nivel(self, bar: Bar) -> None:
        """Soma o volume negociado NO NIVEL (ou alem dele) da ordem-limite que
        esta em pe agora. Chamado ANTES de a maquina consumir a barra — depois
        dela, a ordem pode ja' ter virado posicao e o volume que a preencheu
        ficaria de fora.

        Ver `_penetration_ticks` para o motivo de esta medicao existir."""
        order = self.machine.resting_limit
        if order is None or self.machine.position is not None:
            return
        tocou = (bar.low <= order.limit_price if order.side == "long"
                 else bar.high >= order.limit_price)
        if tocou:
            self._volume_no_nivel += bar.volume

    def _consume(self, conn, account: AccountState, session: date, barras: list[Bar]) -> StepReport:
        """Alimenta as barras na maquina, EM ORDEM, e journaliza os eventos."""
        abertas = fechadas = 0
        for bar in barras:
            self._acumula_volume_no_nivel(bar)
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
        if self.executor is None:
            return
        # A maquina SUBSTITUI a ordem vigiada em vez de acumular: se havia uma
        # anterior (`evento.replaced`), ela tem de sair do terminal primeiro,
        # senao sobram duas pendentes vivas na corretora e a segunda a
        # preencher abriria uma posicao que o robo nunca pediu.
        if evento.replaced is not None:
            self.executor.cancel_limit(evento.ts, reason="superseded")
        elif self._snapshot.pending_entry_refs:
            # `evento.replaced` so' enxerga uma ordem anterior que ESTA
            # maquina colocou -- uma decisao "nova" (`replaced is None`) do
            # ponto de vista dela pode ainda assim ter tickets REAIS sobrando
            # de um PROCESSO ANTERIOR (restart no meio do pregao com uma
            # ordem armada, ver `pending_entry_refs`). `self.executor` aqui e'
            # sempre uma instancia NOVA (`pending_orders` nasce vazio), entao
            # `cancel_limit` nao teria o que cancelar -- cancela pelo
            # `broker_ref` persistido em vez disso.
            self.executor.cancel_stale_refs(self._snapshot.pending_entry_refs, ts=evento.ts)
            self._snapshot.pending_entry_refs = []
        # Um filho REAL por elemento de `EnterLimit.split_quantities` (ver a
        # docstring de `EnterLimit.children` e a Fase 2 em
        # `live/intraday_execution.py`) -- `[quantity]` quando a ordem nao
        # veio dividida, o comportamento de sempre.
        enviadas = self.executor.place_limit(
            side=evento.order.side,
            limit_price=evento.order.limit_price,
            quantities=evento.order.children(self.config.default_quantity),
            ts=evento.ts,
        )
        self._snapshot.pending_entry_refs = [o.broker_ref for o in enviadas if o.broker_ref]

    def _on_limit_cancelled(self, conn, account: AccountState, evento: LimitCancelled) -> None:
        """Mesma razao de `_on_limit_placed` para nao gravar evento: e'
        contado, nao narrado.

        Em execucao real, cancelar de verdade no terminal e' obrigatorio: a
        ordem que o robo abandonou continuaria viva na corretora e poderia
        preencher horas depois, contra um preco que o robo ja descartou."""
        self._snapshot.ordens_abandonadas += 1
        # A medicao de fila e' POR ORDEM: o que negociou no nivel da ordem
        # abandonada nao diz nada sobre o nivel da proxima, que e' outro preco.
        self._volume_no_nivel = 0.0
        if self.executor is not None:
            self.executor.cancel_limit(evento.ts, reason=evento.reason)
        # Resolucao CONFIRMADA (ver `pending_entry_refs`): a maquina acabou de
        # cancelar o resting_limit que este ticket rastreava, entao nao ha
        # mais nada real pra reconciliar num restart futuro.
        self._snapshot.pending_entry_refs = []

    @staticmethod
    def _penetration_ticks(evento: PositionOpened, tick_size: float) -> Optional[float]:
        """Quantos ticks a barra ATRAVESSOU o nivel da ordem-limite.

        E' a medicao que valida (ou refuta) a premissa de maker do robo — ver
        a secao "Modo sombra" na docstring do modulo. `None` para entrada a
        mercado (nao ha nivel para penetrar) e para barra SEM FAIXA.

        Barra sem faixa (`high == low`) e' o caso normal de um feed de tick: um
        negocio e' um evento atomico a um preco so', entao a penetracao e'
        SEMPRE zero por construcao. Gravar 0.0 ali seria pior que nao medir —
        leria como "a premissa e' fragil, em 100% dos toques" quando na verdade
        a pergunta nao cabe nesse formato de dado. Quem responde a pergunta de
        fila em tick e' `volume_no_nivel` (ver `_acumula_volume_no_nivel`)."""
        if evento.order_kind != "limit" or not tick_size:
            return None
        bar = evento.bar
        if bar.high == bar.low:
            return None
        bruto = (evento.price - bar.low) if evento.side == "long" else (bar.high - evento.price)
        return round(bruto / tick_size, 3)

    def _on_opened(self, conn, account: AccountState, evento: PositionOpened) -> None:
        """Grava `Intent` + `Order` + `Fill` da ENTRADA e reflete a posicao em
        `live_positions` — para o painel mostrar a mesma coisa que o painel do
        swing mostra, sem um caminho de leitura paralelo.

        `self._open_intent_id` ja setado significa que a posicao JA EXISTIA
        quando este fill chegou -- um FILHO adicional de `EnterLimit.
        split_quantities` preenchendo numa barra seguinte (TOP-UP, ver
        `_on_opened_top_up`), nao uma entrada nova. Sem este desvio, cada
        filho geraria sua PROPRIA `Intent`/`Order`/`LivePosition` com o preco
        e a quantidade so' DELE (nao os cumulativos que a maquina ja
        calculou) -- o diario mostraria varias "entradas" fantasma e
        `live_positions` ficaria com o ultimo fill sobrescrevendo os
        anteriores em vez da posicao inteira.

        Short grava `quantity` NEGATIVA. O schema aceita (nao ha CHECK de
        sinal) e a marcacao a mercado sai correta sem nenhuma mudanca:
        `market_value = price * quantity` fica negativo, que e' exatamente o
        que uma posicao vendida vale."""
        if self.machine.resting_limit is None:
            # Resolucao CONFIRMADA (ver `pending_entry_refs`): este fill foi o
            # ULTIMO filho (ordem nao dividida, ou o fim de uma dividida) --
            # nao sobra ticket nenhum pra reconciliar num restart futuro. Se
            # ainda houver filho esperando (`resting_limit` continua setado),
            # os tickets continuam validos, nao mexe.
            self._snapshot.pending_entry_refs = []
        if self._open_intent_id is not None:
            self._on_opened_top_up(conn, account, evento)
            return
        tick = float(getattr(self.strategy, "tick_size", 0.0) or 0.0)
        penetration = self._penetration_ticks(evento, tick)
        # Acoes negociadas NO NIVEL enquanto a ordem esperava, ate o fill
        # inclusive. Zerado agora: a proxima ordem comeca a contar do zero.
        volume_no_nivel = round(self._volume_no_nivel, 2)
        self._volume_no_nivel = 0.0
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
                "volume_no_nivel": volume_no_nivel,
                "quantidade_pedida": evento.quantity,
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
            # Em sombra nao ha ticket nenhum (nada foi enviado); em execucao
            # real e' o ticket da ordem-limite que virou esta posicao, para a
            # linha do diario poder ser cruzada com o extrato da corretora.
            broker_ref=None if self.executor is None else self.executor.last_entry_ref,
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
                                   "volume_no_nivel": volume_no_nivel,
                                   "execution_mode": self.execution_mode},
        )
        store.upsert_position(conn, account.id, pos)
        account.positions[pos.ticker] = pos

        self._log(conn, account.id, "info",
                  f"{'SOMBRA: ' if self.execution_mode == 'shadow' else ''}entrada "
                  f"{evento.side} {evento.quantity} {self.strategy.symbol} @ {evento.price:.4f} "
                  f"({evento.order_kind}; penetracao "
                  f"{'n/a' if penetration is None else f'{penetration:.2f} tick(s)'}; "
                  f"{volume_no_nivel:.0f} acoes negociadas no nivel contra as "
                  f"{evento.quantity} que eu pedi)",
                  {"side": evento.side, "price": evento.price, "quantity": evento.quantity,
                   "penetration_ticks": penetration, "volume_no_nivel": volume_no_nivel,
                   "execution_mode": self.execution_mode})

    def _on_opened_top_up(self, conn, account: AccountState, evento: PositionOpened) -> None:
        """Um filho ADICIONAL de `EnterLimit.split_quantities` preencheu com a
        posicao ja aberta -- grava mais um `Order`/`Fill` sob a MESMA
        `Intent` (uma Intent pode gerar N Orders, ver a docstring de
        `core.live_models.Intent`) e ATUALIZA `live_positions` com o preco
        medio/quantidade CUMULATIVOS que `self.machine.position` ja
        recalculou (nao os desta fatia isolada, que sozinhos nao
        representam a posicao)."""
        pos_total = self.machine.position
        assert pos_total is not None  # top-up so' acontece com a posicao ainda aberta
        self._volume_no_nivel = 0.0  # a proxima medicao comeca do zero

        order = Order(
            ticker=self.strategy.symbol,
            side=OrderSide.BUY if evento.side == "long" else OrderSide.SELL,
            quantity=evento.quantity,
            order_type=OrderType.LIMIT if evento.order_kind == "limit" else OrderType.MARKET,
            limit_price=evento.price if evento.order_kind == "limit" else None,
            status=OrderStatus.FILLED,
            filled_qty=evento.quantity,
            avg_price=evento.price,
            broker_ref=None if self.executor is None else self.executor.last_entry_ref,
            intent_id=self._open_intent_id,
            sent_at=evento.ts.to_pydatetime(),
            note=(_SHADOW_NOTE if self.execution_mode == "shadow"
                  else "fatia adicional de entrada day trade"),
        )
        order_id = store.record_order(conn, account.id, order)
        store.record_fill(conn, Fill(order_id=order_id, quantity=evento.quantity,
                                     price=evento.price, ts=evento.ts.to_pydatetime()))

        existente = account.positions.get(self.strategy.symbol)
        assinado = pos_total.quantity if evento.side == "long" else -pos_total.quantity
        pos = LivePosition(
            ticker=self.strategy.symbol, quantity=assinado,
            entry_date=(existente.entry_date if existente is not None else evento.ts.date()),
            entry_price=pos_total.entry_price,
            capital_allocated=abs(pos_total.entry_price * pos_total.quantity),
            current_stop=pos_total.current_stop,
            max_price_seen=(existente.max_price_seen if existente is not None else pos_total.entry_price),
            min_price_seen=(existente.min_price_seen if existente is not None else pos_total.entry_price),
            bars_held=pos_total.bars_held,
            metadata={"side": evento.side, "target": pos_total.current_target,
                     "execution_mode": self.execution_mode},
        )
        store.upsert_position(conn, account.id, pos)
        account.positions[pos.ticker] = pos

        self._log(conn, account.id, "info",
                  f"{'SOMBRA: ' if self.execution_mode == 'shadow' else ''}TOP-UP de entrada "
                  f"{evento.side} +{evento.quantity} {self.strategy.symbol} @ {evento.price:.4f} "
                  f"(posicao agora {pos_total.quantity} @ {pos_total.entry_price:.4f})",
                  {"side": evento.side, "price": evento.price, "quantity": evento.quantity,
                   "quantidade_total": pos_total.quantity, "preco_medio_total": pos_total.entry_price,
                   "execution_mode": self.execution_mode})

    def _on_closed(self, conn, account: AccountState, evento: PositionClosed, bar: Bar) -> None:
        """Grava a saida e move o P&L para onde ele PODE ir.

        `self.machine.position` ja reflete o estado APOS este evento (ver
        `IntradaySessionMachine.on_closed_bar`, que so devolve a lista de
        eventos completa no final): ainda `not None` significa que so' uma
        FATIA fechou (`EnterLimit.exit_split_unit`) e a posicao continua
        aberta com o restante -- desvia para `_on_closed_partial`, que
        ATUALIZA em vez de apagar `live_positions`.

        Em sombra o caixa NAO e' tocado: o ledger manual e' o numero que o
        dono digitou, e sujar isso com lucro/prejuizo imaginario destruiria a
        unica fonte de verdade de caixa que temos (ver
        `dashboard/app.py::operacao_caixa`). O resultado sombra acumula em
        `policy_state`, separado, e aparece no painel como tal."""
        if self.machine.position is not None:
            self._on_closed_partial(conn, account, evento)
            return
        trade = evento.trade
        assinado_saida = trade.quantity if trade.side == "short" else -trade.quantity
        # Em execucao real TODA saida NAO dividida sai a mercado (ver
        # `IntradaySessionMachine._close_position`): uma saida por alvo que
        # dependesse de nova ordem-limite poderia nao preencher e deixar a
        # posicao aberta contra o proprio stop. Em sombra o alvo continua
        # sendo registrado como LIMIT, que e' a premissa que o backtest usa e
        # que a corrida em sombra existe para comparar.
        saida_real = self.executor.last_exit_order if self.executor is not None else None
        # A ULTIMA fatia de uma saida dividida pode ter fechado por um fill
        # de ordem-limite CONFIRMADO (nao por `exit_market`) -- `last_exit_order`
        # fica stale nesse caso; `pending_exit_order` (ainda referenciando o
        # ticket que acabou de preencher, ver `MT5IntradayExecution.exit_fill`)
        # e' o fallback que preserva o `broker_ref` de verdade.
        saida_limite = (self.executor.pending_exit_order
                        if self.executor is not None and saida_real is None else None)
        alvo_maker = trade.exit_reason.value == "target" and saida_real is None

        order = Order(
            ticker=self.strategy.symbol,
            side=OrderSide.SELL if trade.side == "long" else OrderSide.BUY,
            quantity=trade.quantity,
            order_type=OrderType.LIMIT if alvo_maker else OrderType.MARKET,
            limit_price=trade.exit_price if alvo_maker else None,
            status=OrderStatus.FILLED,
            filled_qty=trade.quantity,
            avg_price=trade.exit_price,
            fees=trade.fees_total,
            slippage=trade.slippage_total,
            broker_ref=(saida_real.broker_ref if saida_real is not None
                       else (saida_limite.broker_ref if saida_limite is not None else None)),
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
            account.cash_sombra += evento.pnl_brl
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

    def _on_closed_partial(self, conn, account: AccountState, evento: PositionClosed) -> None:
        """Uma FATIA da posicao fechou (saida dividida, `EnterLimit.
        exit_split_unit`), mas a posicao continua aberta com o restante --
        ver `IntradaySessionMachine._resolve_live_split_exit` (execucao real)
        ou o caminho simulado equivalente guiado por `bar.volume`.

        Grava `Order`/`Fill` sob a MESMA `Intent` (fatiamento, ver a
        docstring de `core.live_models.Intent`) e ATUALIZA (nao apaga)
        `live_positions` com a quantidade que sobrou -- apagar aqui
        destruiria o registro de uma posicao que ainda existe de verdade."""
        trade = evento.trade
        pos_total = self.machine.position
        assert pos_total is not None

        order = Order(
            ticker=self.strategy.symbol,
            side=OrderSide.SELL if trade.side == "long" else OrderSide.BUY,
            quantity=trade.quantity,
            order_type=OrderType.LIMIT,  # so' fatia dividida chega aqui, sempre maker
            limit_price=trade.exit_price,
            status=OrderStatus.FILLED,
            filled_qty=trade.quantity,
            avg_price=trade.exit_price,
            fees=trade.fees_total,
            slippage=trade.slippage_total,
            broker_ref=(None if self.executor is None or self.executor.pending_exit_order is None
                       else self.executor.pending_exit_order.broker_ref),
            intent_id=self._open_intent_id,
            sent_at=trade.exit_ts.to_pydatetime(),
            note=(_SHADOW_NOTE if self.execution_mode == "shadow"
                  else f"fatia de saida day trade ({trade.exit_reason.value})"),
        )
        order_id = store.record_order(conn, account.id, order)
        store.record_fill(conn, Fill(order_id=order_id, quantity=trade.quantity,
                                     price=trade.exit_price, fees=trade.fees_total,
                                     ts=trade.exit_ts.to_pydatetime()))

        existente = account.positions.get(self.strategy.symbol)
        assinado = pos_total.quantity if pos_total.side == "long" else -pos_total.quantity
        pos = LivePosition(
            ticker=self.strategy.symbol, quantity=assinado,
            entry_date=(existente.entry_date if existente is not None else pos_total.entry_ts.date()),
            entry_price=pos_total.entry_price,
            capital_allocated=abs(pos_total.entry_price * pos_total.quantity),
            current_stop=pos_total.current_stop,
            max_price_seen=(existente.max_price_seen if existente is not None else pos_total.entry_price),
            min_price_seen=(existente.min_price_seen if existente is not None else pos_total.entry_price),
            bars_held=pos_total.bars_held,
            metadata=(dict(existente.metadata) if existente is not None else {"side": pos_total.side}),
        )
        store.upsert_position(conn, account.id, pos)
        account.positions[pos.ticker] = pos

        self._snapshot.trades += 1
        if self.execution_mode == "shadow":
            self._snapshot.shadow_pnl_brl += evento.pnl_brl
            account.cash_sombra += evento.pnl_brl
        else:
            account.cash += evento.pnl_brl

        self._log(conn, account.id, "info",
                  f"{'SOMBRA: ' if self.execution_mode == 'shadow' else ''}fatia de saida "
                  f"{trade.side} {trade.quantity} {self.strategy.symbol} @ {trade.exit_price:.4f} "
                  f"({trade.exit_reason.value}) — resultado R$ {evento.pnl_brl:+.2f}; restam "
                  f"{pos_total.quantity} acoes na posicao",
                  {"exit_reason": trade.exit_reason.value, "pnl_brl": round(evento.pnl_brl, 4),
                   "quantidade_restante": pos_total.quantity,
                   "execution_mode": self.execution_mode})

    # ---------- painel -------------------------------------------------------

    def status(self, eventos_limit: int = 10) -> dict:
        """Mesmo formato de `LiveRuntime.status()` — o template de `/operacao`
        le as duas fontes pelas mesmas chaves. Campos que so o day trade tem
        (sombra, penetracao) entram em `daytrade`, sem colidir.

        `eventos_limit` e' o "ver mais" do painel. Busca UM a mais do que vai
        exibir: e' assim que a tela sabe se ainda ha historico atras sem
        precisar de um `COUNT(*)` numa tabela que so cresce.
        """
        session = clock.session_date()
        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return {"conta": self.account_name, "existe": False}
            self._restore(account, session)
            eventos = store.recent_events(conn, account.id, limit=eventos_limit + 1)

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
            # `atraso_s` vem do FEED, nao de um 60.0 fixo: era verdade so' para
            # M1 (a barra so' pode ser lida depois de fechar). Um feed de tick
            # entrega o negocio assim que ele sai, e anunciar 60s ali faria o
            # painel esconder justamente a vantagem que o robo de tick tem.
            "feed": {"nome": self.bar_feed.name, "tempo_real": True,
                     "atraso_s": getattr(self.bar_feed, "nominal_delay_seconds", 60.0)},
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
            "eventos": eventos[:eventos_limit],
            "eventos_ha_mais": len(eventos) > eventos_limit,
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
                # Saldo sombra ACUMULADO entre pregões (`AccountState.
                # cash_sombra`) -- diferente de `resultado_sombra` acima, que
                # zera a cada sessao nova. Nunca deriva de/alimenta `caixa`
                # (dinheiro real), mesmo com a conta em execution_mode="live".
                "caixa_sombra": round(account.cash_sombra, 2),
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
                # Piso de caixa DE HOJE (ver `_check_capital`). `None` = ainda
                # nao conferido neste pregao (processo recem-subido, ou fora do
                # horario) -- nao e' "sem piso".
                "capital_minimo_hoje": (round(self._capital_minimo_hoje, 2)
                                        if self._capital_minimo_hoje is not None else None),
                "capital_alarme": self._capital_alarm,
            },
        }
