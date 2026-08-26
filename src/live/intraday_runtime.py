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
from core import b3_session
from core.b3_session import SAO_PAULO
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
from live.intraday_execution import (BrokerExecutionError, MT5IntradayExecution,
                                     descarta_confirmados, orphan_refs)
from live.notify import NullNotifier
from live.runtime import StepReport
from strategy.daytrade.base import (
    Bar,
    EnterLimit,
    barra_diaria,
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
def _hora_brt(ts) -> str:
    """Carimbo de BARRA (UTC) como `HH:MM` de Brasilia, pra colar no texto.

    Carimbo escrito DENTRO da mensagem congela: diferente do `ts` da coluna,
    que a tela converte na hora de mostrar (`dashboard/app.py::hora_br`),
    ninguem converte isto depois. Como o dono le o console no relogio dele
    (pedido de 2026-08-25), sai em Brasilia ja' daqui -- pelo FUSO, nunca por
    um "-3h" fixo, mesma regra de `core/b3_session.py`.

    So' a hora: a linha inteira ja' vem com a data no prefixo do console.
    """
    ts = pd.Timestamp(ts)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
    return ts.tz_convert(SAO_PAULO).strftime("%H:%M")


MAX_GAP_SECONDS = 15 * 60.0


def _unanime(valores):
    """O valor que TODOS os itens compartilham, ou `None` se divergem (ou se
    algum e' `None`, ou se nao ha item nenhum).

    Existe para o painel poder agregar N posicoes independentes num cartao so'
    sem mentir: stop e alvo sao por POSICAO desde 2026-08-24, e mostrar o da
    primeira como se fosse o da carteira esconderia as outras."""
    vistos = set()
    for v in valores:
        if v is None:
            return None
        vistos.add(v)
        if len(vistos) > 1:
            return None
    return vistos.pop() if vistos else None

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
    # Numero de RODADA (posicionada -> [top-up(s)] -> saida) para o diario poder
    # ser lido como historico de UMA ordem, e nao uma sopa de linhas soltas
    # (pedido do dono, 2026-08-24, depois de perguntar 3x "quem disparou
    # essas ordens?" so' lendo o log). `trade_seq` so' AVANCA (nunca volta
    # dentro do mesmo pregao); `trade_num` e' o numero EM USO agora --
    # atribuido na 1a `LimitPlaced` de uma rodada nova (`evento.replaced is
    # None`) e mantido pelas re-ancoragens da MESMA rodada (`replaced` aponta
    # pra' ordem anterior -- ainda a mesma tentativa de entrada). Limpo
    # (`None`) so' quando a posicao fecha de vez (`_on_closed`, nao a
    # parcial), para a PROXIMA rodada pegar numero novo. Persistido (mesmo
    # padrao de `ordens_postas`) para sobreviver a um restart no meio do
    # pregao sem repetir um numero ja usado.
    trade_seq: int = 0
    trade_num: Optional[int] = None
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
    # ESPELHO, so' para o PAINEL, da ordem-limite de ENTRADA que a maquina
    # vigia agora (`resting_limit` + os filhos que faltam preencher).
    #
    # `IntradaySessionMachine.state()` NAO persiste `resting_limit` de
    # proposito: ela e' uma DECISAO do robo, redecidida pelo warm start a cada
    # processo novo (ver `IntradaySessionMachine.restore`). Mas `/operacao`
    # monta um runtime de LEITURA NOVO a cada poll
    # (`dashboard/live_service.py::_build_intraday_runtime`), e a maquina desse
    # runtime nasce sem ordem nenhuma -- entao
    # `status()["daytrade"]["ordem_em_pe"]` era SEMPRE `None` no painel: o
    # contador "preenchidas/posicionadas" do cabecalho do cartao ficava travado
    # em "x/0" e o "em pe @ preco" do card Ordens nunca aparecia, com a ordem
    # viva no terminal (queixa do dono, 2026-08-26: "substituiu mas continua
    # sendo a ordem #01, deveria estar 0/1").
    #
    # Escrito por `_persist` a partir da maquina e NUNCA lido de volta por ela:
    # e' dado de tela, nao de decisao -- o invariante de `restore()` (o robo
    # redecide a ordem, nao herda a de um snapshot velho) fica intacto.
    ordem_em_pe: Optional[dict] = None

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
            "trade_seq": self.trade_seq,
            "trade_num": self.trade_num,
            "machine": self.machine or {},
            "pending_entry_refs": list(self.pending_entry_refs or []),
            "ordem_em_pe": self.ordem_em_pe,
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
            trade_seq=int(raw.get("trade_seq") or 0),
            trade_num=(int(raw["trade_num"]) if raw.get("trade_num") is not None else None),
            machine=raw.get("machine") or {},
            pending_entry_refs=list(raw.get("pending_entry_refs") or []),
            ordem_em_pe=raw.get("ordem_em_pe") or None,
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
        # Ticket de saida ja' avisado no diario -- o retry acontece a
        # cada barra, o aviso nao (ver `_drena_orfas_de_saida`).
        self._orfas_de_saida_avisadas: set[str] = set()
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
        # Botao AutoTrading do terminal (ver `_check_autotrading`). Guarda o
        # pregao em que ele ja foi visto LIGADO -- depois disso a conferencia
        # para, e quem cobre uma mudanca no meio do pregao e' a recusa da
        # propria corretora (`_recusa_de_envio`).
        self._autotrading_ok_for: Optional[date] = None
        self._autotrading_alarmado = False

    def _numero_ordem_atual(self) -> int:
        """Numero de rodada em uso agora -- ver o campo `trade_num` em
        `_SessionSnapshot`. So' atribui um numero NOVO aqui de propósito
        (fallback): o caminho normal e' `_on_limit_placed` atribuir na
        arma; isto so' cobre a semente do warm start, que planta a ordem
        direto em `resting_limit` sem passar por `LimitPlaced` (ver a
        docstring de `_start_session`), entao pode preencher sem NUNCA ter
        passado por la'."""
        if self._snapshot.trade_num is None:
            self._snapshot.trade_seq += 1
            self._snapshot.trade_num = self._snapshot.trade_seq
        return self._snapshot.trade_num

    @staticmethod
    def _bracket_txt(stop: Optional[float], target: Optional[float]) -> str:
        """" (stop X / alvo Y)" pra' colar na entrada -- pedido do dono
        (2026-08-24): saber JA' NA ENTRADA em que preco ela seria estopada,
        sem esperar a saida pra' descobrir. `None` num dos dois (robo sem
        alvo, por exemplo) so' omite aquela metade; os dois `None` omite o
        parentese inteiro."""
        partes = []
        if stop is not None:
            partes.append(f"stop {stop:.4f}")
        if target is not None:
            partes.append(f"alvo {target:.4f}")
        return f" ({' / '.join(partes)})" if partes else ""

    #: Motivo de saida da maquina (`IntradayExitReason`) -> a PALAVRA que abre
    #: a linha do diario. `.get(v, v.upper())` cobre um motivo novo sem
    #: quebrar o log. "FLATTEN" e' o termo que o proprio sistema ja usa pro
    #: corte de fim de pregao (`corte_flatten_brt`, `session_end_policy`).
    _MOTIVO_SAIDA_TXT = {
        "stop": "STOP",
        "target": "TARGET",
        "forced_flatten": "FLATTEN",
        "manual": "MANUAL",
        "signal": "SINAL",
    }

    def _lotes_txt(self, quantidade: int) -> str:
        """Quantidade em LOTES, do jeito que o dono pensa a ordem.

        Pedido dele (2026-08-25): "tirar o 100 e tratar como lotes" -- o
        tamanho do lote e' constante do papel (`config.default_quantity`: 100
        acoes na B3, 1 contrato no futuro), entao repetir "100" em toda linha
        so' gasta espaco e ainda obriga a dividir de cabeca pra saber quantas
        ordens sao.

        Quantidade que NAO fecha um numero inteiro de lotes volta em acoes, sem
        arredondar: e' o caso do fracionario (ver `detect_fractional_symbol_map`),
        e dizer "1 lote" pra 37 acoes seria mentir sobre o tamanho da ordem.
        """
        lote = self.config.default_quantity
        if lote > 0 and quantidade % lote == 0:
            n = quantidade // lote
            return f"{n} lote" if n == 1 else f"{n} lotes"
        return f"{quantidade} ações" if quantidade != 1 else "1 ação"

    @staticmethod
    def _resultado_dia_e_acumulado(saidas: list[dict], hoje: str, capital_inicial: float) -> dict:
        """Ganhos/perdas e retorno/DD do dia e desde o início da conta, a
        partir do histórico de saídas de `store.daytrade_exit_events`
        (`_on_closed`/`_on_closed_partial`) -- pedido do dono, 2026-08-24
        (painel de `/operacao` "com informação repetida e pouco valor").

        "Ret./DD" aqui é RETORNO simples (pnl / capital inicial), não
        anualizado: já vimos essa distorção em janela curta (ver memória
        `feedback_cagr_short_window`) e um robô de um símbolo só, rodando há
        dias ou semanas, é sempre janela curta. DD é o pico-a-vale da curva
        de pnl ACUMULADO (soma de todas as saídas, uma fatia dividida conta
        cada pedaço -- o total bate igual), não uma curva de equity com
        marcação a mercado (o robô normalmente flatten no fim do pregão,
        então realizado é o que importa).

        `capital_inicial` é `account.initial_capital`, DECLARADO na criação
        da conta e nunca mais tocado -- tentei somar toda correção manual de
        caixa como se fosse aporte (2026-08-24), mas o dono apontou o furo:
        ele também usa o campo "Caixa" pra CORRIGIR/realocar, não só pra
        aportar, então cada correção sujaria o denominador do retorno. Sem
        forma confiável de distinguir aporte de correção sem pedir a
        intenção na hora (fora de escopo por ora), voltar ao valor fixo é
        mais HONESTO: puxa o resultado de uma conta com `initial_capital`
        desatualizado, mas não inventa precisão que os dados não têm.

        Acerto por lado é por RODADA (`date`, `round`), não por linha: uma
        saída dividida em fatias não pode virar 2 "trades" no cômputo de
        vitória/derrota -- soma-se o pnl das fatias da mesma rodada primeiro,
        só então classifica ganho/perda pelo total."""
        rodadas: dict[tuple[str, int], dict] = {}
        for s in saidas:
            chave = (s["date"], s["round"])
            r = rodadas.setdefault(chave, {"pnl": 0.0, "side": None})
            r["pnl"] += s["pnl_brl"]
            if s["side"]:
                r["side"] = s["side"]

        ganhos_dia = sum(s["pnl_brl"] for s in saidas if s["date"] == hoje and s["pnl_brl"] > 0)
        perdas_dia = -sum(s["pnl_brl"] for s in saidas if s["date"] == hoje and s["pnl_brl"] < 0)
        lucro_acumulado = sum(s["pnl_brl"] for s in saidas if s["pnl_brl"] > 0)
        prejuizo_acumulado = -sum(s["pnl_brl"] for s in saidas if s["pnl_brl"] < 0)

        cum = cum_dia = pico = pico_dia = 0.0
        dd = dd_dia = 0.0
        for s in saidas:
            cum += s["pnl_brl"]
            pico = max(pico, cum)
            dd = min(dd, cum - pico)
            if s["date"] == hoje:
                cum_dia += s["pnl_brl"]
                pico_dia = max(pico_dia, cum_dia)
                dd_dia = min(dd_dia, cum_dia - pico_dia)

        base = capital_inicial or 1.0
        acerto_por_lado = {}
        for lado in ("long", "short"):
            rodadas_lado = [r for r in rodadas.values() if r["side"] == lado]
            acerto_por_lado[lado] = (
                round(100 * sum(1 for r in rodadas_lado if r["pnl"] > 0) / len(rodadas_lado))
                if rodadas_lado else None
            )

        fator_dia_label, fator_dia_valor = IntradayLiveRuntime._fator_lucro_prejuizo(ganhos_dia, perdas_dia)
        fator_acum_label, fator_acum_valor = IntradayLiveRuntime._fator_lucro_prejuizo(
            lucro_acumulado, prejuizo_acumulado
        )

        return {
            # Nome mantido `aportes_totais` no dict (não `capital_inicial`)
            # porque o card "Caixa" do painel usa esta chave pra' mostrar
            # "quanto entrou vs quanto veio de retorno" -- o VALOR agora é
            # só `account.initial_capital`, sem soma de correções.
            "aportes_totais": round(capital_inicial, 2),
            "ganhos_dia": round(ganhos_dia, 2),
            "perdas_dia": round(perdas_dia, 2),
            "retorno_dia_pct": round(100 * cum_dia / base, 2),
            "dd_dia_pct": round(100 * dd_dia / base, 2),
            "fator_dia_label": fator_dia_label,
            "fator_dia_valor": fator_dia_valor,
            "lucro_acumulado": round(lucro_acumulado, 2),
            "prejuizo_acumulado": round(prejuizo_acumulado, 2),
            "retorno_acumulado_pct": round(100 * cum / base, 2),
            "dd_acumulado_pct": round(100 * dd / base, 2),
            "fator_acumulado_label": fator_acum_label,
            "fator_acumulado_valor": fator_acum_valor,
            "acerto_compra_pct": acerto_por_lado["long"],
            "acerto_venda_pct": acerto_por_lado["short"],
        }

    @staticmethod
    def _fator_lucro_prejuizo(lucro: float, prejuizo: float) -> tuple[str, float | None]:
        """Card que substituiu "Ret./DD" (pedido do dono, 2026-08-25): não é
        retorno sobre capital, é o LADO QUE DOMINA dividido pelo outro lado
        -- lucro/prejuízo quando o lado vencedor é o lucro, invertido quando é
        o prejuízo, pra o número sair sempre >= 1 e o rótulo dizer quem
        venceu. `None` significa "o outro lado é zero" -- infinito de
        verdade, exibido como "∞" pelo template, não um retorno percentual
        (ex.: lucro R$5,92, prejuízo R$0 não é "592%", é lucro puro sem
        nenhuma perda pra dividir)."""
        if lucro == 0 and prejuizo == 0:
            return "Fator de lucro", 0.0
        if lucro >= prejuizo:
            return "Fator de lucro", round(lucro / prejuizo, 2) if prejuizo > 0 else None
        return "Fator de prejuízo", round(prejuizo / lucro, 2) if lucro > 0 else None

    @staticmethod
    def _ordens_por_lado(ordens_hoje: list[dict]) -> dict:
        """Compra/venda e preenchida/cancelada de hoje, por lado -- fonte do
        card "Ordens posicionadas" (pedido do dono, 2026-08-24). `None` na
        taxa de preenchimento de um lado = nenhuma ordem daquele lado teve
        desfecho hoje ainda (só tem posta pendente, ou nenhuma ordem).

        `valor_ordens_compra`/`valor_ordens_venda` somam o NOCIONAL
        (quantidade x preço) das ordens ARMADAS de cada lado -- é o número
        que o painel mostra como valor principal do card, com a CONTAGEM
        (`ordens_compra`/`ordens_venda`) virando texto secundário (pedido do
        dono, 2026-08-24: "deve aparecer os valores, e as quantidades
        abaixo"). Mesma população da contagem (armadas, não preenchidas),
        pra o número grande e o texto pequeno descreverem a mesma coisa."""
        contagem = {lado: {"armada": 0, "preenchida": 0, "cancelada": 0} for lado in ("long", "short")}
        valor_armada = {"long": 0.0, "short": 0.0}
        for o in ordens_hoje:
            lado = o["side"]
            if lado not in contagem:
                continue
            contagem[lado][o["kind"]] += 1
            if o["kind"] == "armada" and o.get("quantity") is not None and o.get("price") is not None:
                valor_armada[lado] += o["quantity"] * o["price"]

        resultado = {
            "ordens_compra": contagem["long"]["armada"], "ordens_venda": contagem["short"]["armada"],
            "valor_ordens_compra": round(valor_armada["long"], 2),
            "valor_ordens_venda": round(valor_armada["short"], 2),
        }
        for lado, chave in (("long", "preenchida_compra_pct"), ("short", "preenchida_venda_pct")):
            desfechos = contagem[lado]["preenchida"] + contagem[lado]["cancelada"]
            resultado[chave] = (round(100 * contagem[lado]["preenchida"] / desfechos)
                                if desfechos else None)
        return resultado

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

    def _espelho_da_ordem_em_pe(self) -> Optional[dict]:
        """A ordem-limite de ENTRADA vigiada agora, no formato que o painel le
        -- `None` quando nao ha nenhuma. Ver `_SessionSnapshot.ordem_em_pe`
        para por que isto e' persistido separado de `machine.state()`."""
        order = self.machine.resting_limit
        filhos = self.machine.resting_children
        if order is None or not filhos:
            return None
        return {
            "lado": order.side,
            "preco": order.limit_price,
            # Uma ordem REAL por filho que ainda falta preencher (ver
            # `IntradaySessionMachine.resting_children`) -- e' o "y" do "x/y"
            # no cabecalho do cartao. Ordem nao dividida = 1.
            "ordens": len(filhos),
            # Em ACOES/CONTRATOS, nao em lotes -- mesma unidade de
            # `Order.quantity` (quem quer lotes divide por `default_quantity`).
            "quantidade": sum(filhos),
        }

    def _persist(self, conn, account: AccountState) -> None:
        self._snapshot.machine = self.machine.state()
        # Recalculado da maquina a CADA persistencia, nunca incrementado a mao:
        # e' o que dispensa bookkeeping nos 6 sites que largam `resting_limit`
        # (flatten, ttl, superseded, ultimo filho preenchido, `discard_
        # resting_limit`, recusa de envio) -- nenhum deles precisa saber que
        # este espelho existe.
        self._snapshot.ordem_em_pe = self._espelho_da_ordem_em_pe()
        estado = dict(account.policy_state or {})
        estado["intraday"] = self._snapshot.to_dict()
        account.policy_state = estado
        store.save_account(conn, account)

    @staticmethod
    def _impedimento_de_hoje(account: AccountState, session: date) -> Optional[str]:
        """O motivo gravado em `policy_state["impedimento"]`, se for do
        pregao `session` -- senao `None`. Ver `_gravar_impedimento`."""
        gravado = (account.policy_state or {}).get("impedimento") or {}
        if gravado.get("pregao") != session.isoformat():
            return None
        return gravado.get("motivo") or None

    def _gravar_impedimento(self, conn, account: AccountState,
                           motivo: Optional[str], pregao: date) -> None:
        """Grava (ou apaga) o IMPEDIMENTO corrente -- o motivo pelo qual este
        robo nao esta operando agora, apesar de o processo estar de pe.

        Mora em `policy_state["impedimento"]`, IRMAO de `["intraday"]` e sem
        tocar nele de proposito: esta funcao e' chamada em pontos de
        `run_once` que rodam ANTES de `_start_session`, quando
        `self._snapshot` ainda pode ser o do pregao ANTERIOR -- passar por
        `_persist` ali gravaria o snapshot velho por cima do bom.

        Existe porque o painel nao pode perguntar ao terminal: `live_service.
        _build_intraday_runtime` monta um runtime de LEITURA e
        `status()` tem proibicao explicita de disparar I/O na corretora. Sem
        isto, um pregao recusado (relogio, AutoTrading, caixa) so' aparecia
        no log do processo, enquanto o cartao seguia verde escrito
        "operando" -- foi a queixa do dono em 25/08/2026.

        So' escreve quando MUDA: o supervisor passa aqui a cada 5s, e
        reescrever a mesma linha o pregao inteiro so' castiga o disco."""
        estado = dict(account.policy_state or {})
        atual = estado.get("impedimento")
        novo = {"motivo": motivo, "pregao": pregao.isoformat()} if motivo else None
        if atual == novo:
            return
        if novo is None:
            estado.pop("impedimento", None)
        else:
            estado["impedimento"] = novo
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
        um robo com esse teto (`GremahTick` desde 2026-08-24, `Gremah`
        tambem desde 2026-08-24) usa isto; os outros recebem uma lista que
        nunca consultam (default no-op na base). Reusa `_CAUDA_VOL_DIAS`
        sessoes de folga (generoso sobre o
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
                        # Restart no meio do pregao com uma ordem ja' posicionada:
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
                        self._aplica_cancelamento(conn, account, self.executor.cancel_stale_refs(
                            self._snapshot.pending_entry_refs, ts=seed_bars[-1].ts,
                        ))
                    # Mesma recusa possivel do envio por barra, mesmo
                    # tratamento (ver `_recusa_de_envio`): `resume_session`
                    # acabou de plantar a ordem em `resting_limit`, e uma
                    # recusa aqui a deixaria vigiada sem existir no book.
                    try:
                        enviadas = self.executor.place_limit(
                            side=pending.side, limit_price=pending.limit_price,
                            quantities=pending.children(self.config.default_quantity),
                            ts=seed_bars[-1].ts,
                        )
                    except BrokerExecutionError as erro:
                        self._recusa_de_envio(conn, account, session,
                                              self._snapshot.trade_num, erro)
                    else:
                        # SOMA, nao substitui: um ticket que o cancelamento
                        # acima nao confirmou morto continua precisando de
                        # vigilancia (`_aplica_cancelamento`).
                        self._snapshot.pending_entry_refs = list(dict.fromkeys(
                            (self._snapshot.pending_entry_refs or [])
                            + [o.broker_ref for o in enviadas if o.broker_ref]
                        ))
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
                          # "ordem em pe"/"sem ordem" em vez de "posicionada":
                          # depois da reescrita de 2026-08-25 quem POSICIONA e'
                          # a linha "LIMITE ...", e usar a palavra velha aqui
                          # faria parecer que o warm start armou uma ordem nova.
                          f"{session.isoformat()}: warm start, {len(seed_bars)} barra(s), "
                          f"{'ordem em pe' if pending else 'sem ordem'}",
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
                      f"{session.isoformat()}: sessao a frio, ancora rolante",
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
        hoje = clock.intraday_session(now)
        passos: list[StepReport] = []

        if not clock.is_trading_day(hoje) or fase not in (SessionPhase.OPEN, SessionPhase.CLOSING_AUCTION):
            return [StepReport("idle", hoje, phase=fase)]

        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return [StepReport("daytrade_skip", hoje, detail={"motivo": "conta inexistente"})]

            # Os tres portoes abaixo (relogio, AutoTrading, caixa) recusam o
            # pregao. Cada recusa carimba o IMPEDIMENTO na conta e cada
            # liberacao o apaga -- e' o unico caminho pelo qual o painel fica
            # sabendo (ver `_gravar_impedimento`).
            alarme = self._check_clock(conn, account, hoje)
            if alarme is not None:
                self._gravar_impedimento(conn, account, "relógio do servidor MT5", hoje)
                return [StepReport("daytrade_skip", hoje, phase=fase,
                                   detail={"motivo": "relogio do servidor", "alarme": alarme})]

            alarme_auto = self._check_autotrading(conn, account, hoje)
            if alarme_auto is not None:
                self._gravar_impedimento(conn, account, "AutoTrading do terminal desligado", hoje)
                return [StepReport("daytrade_skip", hoje, phase=fase,
                                   detail={"motivo": "autotrading desligado",
                                           "alarme": alarme_auto})]

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
            # `positions` (a lista), nao o atalho `machine.position`: ele
            # levanta com mais de uma posicao aberta, e sombra abre uma por
            # lote desde 2026-08-24 -- o robo morreria aqui justamente no
            # pregao em que pegou dois lotes E o caixa caiu abaixo do minimo.
            if alarme_capital is not None and not self.machine.positions:
                # Sem posicao aberta: nao comeca. Avanca `last_bar_ts` de
                # proposito -- ficar sem consumir faria o robo, quando o caixa
                # enfim cobrisse o minimo, receber de uma vez todo o dado que
                # passou enquanto ele estava barrado, e decidir contra precos
                # que ja foram.
                self._snapshot.last_bar_ts = barras[-1].ts
                self._gravar_impedimento(conn, account, "caixa abaixo do mínimo do dia", hoje)
                self._persist(conn, account)
                return passos + [StepReport("daytrade_skip", hoje, phase=fase,
                                            detail={"motivo": "caixa abaixo do minimo",
                                                    "alarme": alarme_capital})]

            # Chegou aqui = nenhum portao barrou: o robo esta operando de
            # verdade, entao um impedimento anterior (o botao que o dono
            # ligou no meio do pregao, o caixa que ele completou) deixa de
            # valer AGORA, nao no proximo pregao.
            self._gravar_impedimento(conn, account, None, hoje)
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

    def _check_autotrading(self, conn, account: AccountState,
                           session: date) -> Optional[str]:
        """O botao AutoTrading do terminal esta ligado? Devolve o motivo do
        alarme, ou `None` se pode operar.

        Existe por causa de 25/08/2026: o terminal subiu com o AutoTrading
        DESLIGADO e a primeira ordem do pregao do slot
        `dt-gremah_tick-pmam3-live` morreu com `retcode=10027 AutoTrading
        disabled by client`. Sem esta conferencia, a unica pista era um
        `[erro]` no log do processo -- o painel mostrava "OPERANDO", verde.
        Melhor recusar o pregao com o motivo na cara do que fingir que opera.

        Por que o robo nao LIGA sozinho: nao da'. A API do MetaTrader5 so'
        LE (`terminal_info().trade_allowed`) -- ver `MT5Broker.
        autotrading_allowed` para os dois contornos medidos e por que os dois
        foram descartados.

        So' checa ate' passar UMA vez no pregao, e nao a cada barra do dia:
        o custo de errar aqui e' um pregao inteiro perdido no comeco, que e'
        o caso real; uma mudanca DEPOIS disso aparece sozinha, na recusa da
        proxima ordem (`_recusa_de_envio`), agora que ela e' journalizada em
        vez de derrubar o passo. Enquanto barrado, continua conferindo a cada
        passo de proposito -- ligar o botao no meio do pregao (foi o que o
        dono fez naquele dia, as ~14h) libera a operacao dali em diante, sem
        precisar reiniciar nada.

        Modo sombra nao passa por aqui (`self.executor is None`): sombra nao
        manda ordem nenhuma, entao o botao do terminal nao muda nada para
        ela.

        "Nao deu para saber" (`None`, terminal fora do ar) NAO vira alarme:
        quem nao consegue nem ler o terminal ja vai falhar no dado e na
        ordem, com erro proprio e mais especifico."""
        if self.executor is None or self._autotrading_ok_for == session:
            return None
        ler = getattr(self.broker, "autotrading_allowed", None)
        if ler is None:
            return None
        permitido = ler()
        if permitido is None:
            return None
        if permitido:
            if self._autotrading_alarmado:
                self._autotrading_alarmado = False
                self._log(conn, account.id, "info",
                          "AutoTrading do terminal LIGADO -- operacao liberada",
                          {"pregao": session.isoformat()})
            self._autotrading_ok_for = session
            return None
        alarme = ("AutoTrading do terminal MT5 esta DESLIGADO -- o terminal "
                  "recusaria toda ordem (retcode=10027). Ligue no botao "
                  "'Algo Trading' (Ctrl+E) do terminal; a operacao comeca "
                  "sozinha no passo seguinte.")
        if not self._autotrading_alarmado:
            self._autotrading_alarmado = True
            self._log(conn, account.id, "error", f"nao vou operar: {alarme}",
                      {"pregao": session.isoformat()})
        return alarme

    def _check_capital(
        self, conn, account: AccountState, session: date, preco: float
    ) -> Optional[str]:
        """O caixa deste slot cobre o lote de hoje? Devolve o motivo, ou
        `None` se cobre.

        O minimo aqui e' o custo de 1 lote no preco de HOJE (`preco x
        default_quantity`) -- NAO o piso de `strategy.daytrade.base.
        capital_minimo_brl` (2x o lote), que e' a barreira de ENTRADA
        (`live_control.start()`/`operacao_iniciar`), verificada uma unica vez
        para deixar o robo subir. Depois de subir, o robo so precisa
        conseguir COMPRAR o lote de hoje -- exigir 2x de novo, todo pregao,
        barrava o robo em qualquer dia em que o preco subisse o bastante para
        o caixa sobrando nao cobrir mais a folga (pedido do dono, 2026-08-24:
        "a regra do caixa minimo pra operar deve ser aplicado somente para
        iniciar a operacao").

        Uma vez por PREGAO, nao a cada barra: o numero so muda quando o preco
        de referencia do dia muda, e reavaliar a cada minuto sujaria o diario
        com o mesmo evento centenas de vezes. Mas tambem nao da' para decidir
        uma vez e congelar — CSAN3 saiu de R$7,62 para R$3,64 em 11 meses, e
        PMAM3 caiu 90%: um piso congelado estaria errado nos dois sentidos,
        ora barrando um robo que cabe, ora liberando um que nao cabe mais.

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

        minimo = preco * self.config.default_quantity
        self._capital_checked_for = session
        self._capital_minimo_hoje = minimo
        saldo = account.cash_for(self.execution_mode)

        if saldo >= minimo:
            self._capital_alarm = None
            return None

        self._capital_alarm = (
            f"caixa R$ {saldo:.2f} nao cobre o minimo de R$ {minimo:.2f} "
            f"({self.strategy.symbol})"
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
                    # Só o que decide a ação: quanto sobra e quanto o papel
                    # exige. De onde vem o "livre" (descontado o aportado nos
                    # outros robos) e o caixa bruto ficam no payload -- linha de
                    # diário é para ler de relance, não para explicar a conta.
                    f"da' para abrir {self.strategy.name} em {sugestao.symbol}: "
                    f"R$ {sugestao.disponivel_brl:.2f} livres, exige "
                    f"R$ {sugestao.required_brl:.2f}",
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
        self._drena_orfas_de_saida(conn, account, ultima.ts)
        self._log(conn, account.id, "error",
                  f"buraco de {parado_ha / 60.0:.0f} min sem rodar; {len(barras)} "
                  f"barra(s) puladas"
                  f"{' · posicao achatada' if fechados else ''}; retomado em "
                  f"{_hora_brt(ultima.ts)}",
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
        # Mesmo motivo de `run_once`: `positions`, nao o atalho de 1 posicao.
        # Aqui o caso e' a entrada DIVIDIDA -- filhos ainda em pe com outros ja
        # preenchidos e' exatamente "ordem em pe + N posicoes abertas".
        if order is None or self.machine.positions:
            return
        tocou = (bar.low <= order.limit_price if order.side == "long"
                 else bar.high >= order.limit_price)
        if tocou:
            self._volume_no_nivel += bar.volume

    def _consume(self, conn, account: AccountState, session: date, barras: list[Bar]) -> StepReport:
        """Alimenta as barras na maquina, EM ORDEM, e journaliza os eventos.

        Barra carimbada num pregao ANTERIOR e' descartada (quem declara a
        regra e' a maquina, `is_previous_session_bar` -- aqui so' se aplica,
        regra 6 do AGENTS.md): o feed entrega tudo com `ts > last_bar_ts`, e
        essa marca atravessa a virada do pregao, entao uma barra atrasada de
        ontem chega como primeira barra de hoje. A MARCA AVANCA mesmo assim
        -- nao consumir a deixaria voltar em todo passo, para sempre.

        O descarte cobre tambem `_acumula_volume_no_nivel`: volume de ontem
        contado no nivel de uma ordem de hoje mediria penetracao que nunca
        aconteceu (ver `_penetration_ticks`)."""
        abertas = fechadas = descartadas = 0
        ultima_descartada = None
        for bar in barras:
            if self.machine.is_previous_session_bar(bar.ts):
                descartadas += 1
                ultima_descartada = bar.ts
                self._snapshot.last_bar_ts = bar.ts
                continue
            self._acumula_volume_no_nivel(bar)
            for evento in self.machine.on_closed_bar(bar):
                if isinstance(evento, PositionOpened):
                    abertas += 1
                elif isinstance(evento, PositionClosed):
                    fechadas += 1
                self._apply(conn, account, evento, bar)
            self._drena_orfas_de_saida(conn, account, bar.ts)
            self._snapshot.last_bar_ts = bar.ts
        if descartadas:
            # Uma linha por LOTE descartado, nao por barra: sao 1 ou 2 por
            # pregao no caso normal (a cauda de ontem), e o dono pediu que o
            # historico registre o que o robo faz -- inclusive o que ele
            # deliberadamente ignorou.
            self._log(conn, account.id, "info",
                      f"{descartadas} barra(s) de pregao anterior descartada(s) "
                      f"(ultima: {_hora_brt(ultima_descartada)})",
                      {"descartadas": descartadas, "sessao": session.isoformat()})
        detalhe = {"barras": len(barras), "entradas": abertas, "saidas": fechadas,
                   "modo": self.execution_mode}
        if descartadas:
            detalhe["descartadas"] = descartadas
        return StepReport("daytrade", session, detail=detalhe)

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

        Grava no diario (2026-08-24, pedido do dono: "quero que o histórico
        registre qualquer evento feito pelo robô", depois de eu explicar um
        rearme so' por dedução de código porque nada disso ficava escrito) --
        antes disto so' era CONTADO (`ordens_postas`/`ordens_abandonadas`,
        ainda visiveis em `status()`, com a mesma razao postas/preenchidas de
        prioridade de fila), e a ordem CORRENTE continua tambem em
        `status()["daytrade"]["ordem_em_pe"]`. O que preenche gera
        `Intent`/`Order`/`Fill` a parte (ver `_on_opened`).

        O numero (`#NN`, ver `_SessionSnapshot.trade_num`) so' AVANCA aqui
        numa arma de VERDADE nova (`evento.replaced is None`) -- uma
        substituicao por reancoragem (`replaced` aponta pra' ordem anterior)
        continua a MESMA rodada, entao mantem o numero: e' o que deixa
        "ordem #03 posicionada" e a eventual "entrada #03"/"saida #03" serem
        reconheciveis como o MESMO evento no diario, mesmo com outras
        rodadas entrelacadas no meio (pedido do dono, 2026-08-24).

        `trade_num is None` MESMO com `replaced is not None` acontece quando
        a ordem substituida foi plantada pelo warm start direto em
        `resting_limit` (ver a docstring de `_start_session`) -- nunca
        passou por aqui, entao nunca ganhou numero. Trata como rodada nova
        do ponto de vista do diario: e' a primeira vez que esta rodada
        aparece nele."""
        self._snapshot.ordens_postas += 1
        if evento.replaced is None or self._snapshot.trade_num is None:
            self._snapshot.trade_seq += 1
            self._snapshot.trade_num = self._snapshot.trade_seq
        numero = self._snapshot.trade_num
        qtd = sum(evento.order.children(self.config.default_quantity))
        # Formato do diario (2026-08-25, pedido do dono): o EVENTO abre a
        # linha, depois lado, rodada, tamanho em lotes, papel e preco. "LIMITE"
        # em vez de so' "SHORT #02 ..." porque a linha da ordem ARMADA e a da
        # entrada que PREENCHEU sairiam identicas fora o parentese de stop/alvo
        # -- e robo sem alvo nem parentese tem. `tipo` no payload e' o que o
        # card "Ordens" le (ver `live_store.daytrade_order_events_on`), entao o
        # texto ficou livre pra mudar sem quebrar o painel.
        self._log(conn, account.id, "info",
                  f"LIMITE {evento.order.side.upper()} #{numero:02d} "
                  f"{self._lotes_txt(qtd)} {self.strategy.symbol} "
                  f"@ {evento.order.limit_price:.4f}"
                  + (" (substitui)" if evento.replaced is not None else ""),
                  {"numero_ordem": numero, "side": evento.order.side, "quantity": qtd,
                   "tipo": "armada",
                   "limit_price": evento.order.limit_price,
                   "substitui_anterior": evento.replaced is not None,
                   "sessao": self._snapshot.session.isoformat()})
        if self.executor is None:
            return
        # A maquina SUBSTITUI a ordem vigiada em vez de acumular: se havia uma
        # anterior (`evento.replaced`), ela tem de sair do terminal primeiro,
        # senao sobram duas pendentes vivas na corretora e a segunda a
        # preencher abriria uma posicao que o robo nunca pediu.
        if evento.replaced is not None:
            self._aplica_cancelamento(
                conn, account,
                self.executor.cancel_limit(evento.ts, reason="superseded"))
        elif self._snapshot.pending_entry_refs:
            # `evento.replaced` so' enxerga uma ordem anterior que ESTA
            # maquina colocou -- uma decisao "nova" (`replaced is None`) do
            # ponto de vista dela pode ainda assim ter tickets REAIS sobrando
            # de um PROCESSO ANTERIOR (restart no meio do pregao com uma
            # ordem posicionada, ver `pending_entry_refs`). `self.executor` aqui e'
            # sempre uma instancia NOVA (`pending_orders` nasce vazio), entao
            # `cancel_limit` nao teria o que cancelar -- cancela pelo
            # `broker_ref` persistido em vez disso.
            self._aplica_cancelamento(
                conn, account,
                self.executor.cancel_stale_refs(
                    self._snapshot.pending_entry_refs, ts=evento.ts))
        # Um filho REAL por elemento de `EnterLimit.split_quantities` (ver a
        # docstring de `EnterLimit.children` e a Fase 2 em
        # `live/intraday_execution.py`) -- `[quantity]` quando a ordem nao
        # veio dividida, o comportamento de sempre.
        try:
            enviadas = self.executor.place_limit(
                side=evento.order.side,
                limit_price=evento.order.limit_price,
                quantities=evento.order.children(self.config.default_quantity),
                ts=evento.ts,
            )
        except BrokerExecutionError as erro:
            self._recusa_de_envio(conn, account, self._snapshot.session, numero, erro)
            return
        # SOMA, nao substitui: ver `_aplica_cancelamento`.
        self._snapshot.pending_entry_refs = list(dict.fromkeys(
            (self._snapshot.pending_entry_refs or [])
            + [o.broker_ref for o in enviadas if o.broker_ref]
        ))

    def _drena_orfas_de_saida(self, conn, account: AccountState, ts) -> None:
        """Fatia de SAIDA cujo cancelamento a corretora nao confirmou.

        A maquina cancela a limite de saida e fecha a mercado no mesmo passo
        (`machine.py`, 4 sites). Um cancelamento nao confirmado deixa as duas
        ordens vivas pela mesma posicao, e em conta NETTING a limite orfa
        preenchendo depois do flatten INVERTE a posicao -- lado aberto que
        ninguem pediu, sem stop e sem alvo.

        Tenta de novo a cada barra (`cancel_stale_refs` cancela por ticket) e
        so' para quando a corretora confirmar. Avisa uma vez por ticket para
        nao encher o diario a cada barra de um terminal fora do ar."""
        if self.executor is None or not self.executor.exit_orphan_refs:
            return
        refs = list(dict.fromkeys(self.executor.exit_orphan_refs))
        novos = [r for r in refs if r not in self._orfas_de_saida_avisadas]
        if novos:
            self._orfas_de_saida_avisadas.update(novos)
            self._log(conn, account.id, "warn",
                      f"ORFA saida {self.strategy.symbol} ticket "
                      f"{', '.join(novos)} (cancelamento nao confirmado)",
                      {"tickets": novos, "lado": "saida",
                       "sessao": self._snapshot.session.isoformat()
                       if self._snapshot.session else None})
        self.executor.exit_orphan_refs = orphan_refs(
            self.executor.cancel_stale_refs(refs, ts=ts))

    def _aplica_cancelamento(self, conn, account: AccountState, canceladas) -> None:
        """Guarda em `pending_entry_refs` o ticket que o cancelamento NAO
        confirmou morto, e conta no diario quando isso acontece.

        `MT5Broker.cancel` nao levanta quando falha (terminal fechado,
        conexao caida, retcode inesperado): devolve a ordem com o motivo na
        nota e o status intocado. Todo este arquivo descartava esse retorno e
        zerava a lista logo em seguida -- uma ordem-limite podia seguir VIVA
        no book com o robo tendo esquecido o ticket, sem linha no diario e
        com o botao de parar liberado. Ficar na lista e' o que faz a proxima
        `EnterLimit` tentar cancelar de novo (`cancel_stale_refs`) e o que
        sobrevive a um restart, ja que ela e' persistida no `policy_state`."""
        sobraram = descarta_confirmados(
            self._snapshot.pending_entry_refs or [], canceladas)
        self._snapshot.pending_entry_refs = sobraram
        if sobraram:
            self._log(conn, account.id, "warn",
                      f"ORFA {self.strategy.symbol} ticket "
                      f"{', '.join(sobraram)} (cancelamento nao confirmado)",
                      {"tickets": sobraram,
                       "sessao": self._snapshot.session.isoformat()
                       if self._snapshot.session else None})

    def _recusa_de_envio(self, conn, account: AccountState, sessao: date,
                         numero: Optional[int], erro: BrokerExecutionError) -> None:
        """A corretora RECUSOU a entrada: desfaz a vigilancia e conta o
        acontecido no diario (nivel `error`, logo tambem notifica).

        Nao re-levanta a excecao de proposito. Deixa-la subir aborta o passo
        inteiro, e a transacao do diario volta atras junto -- foi assim que a
        recusa de 25/08/2026 (`AutoTrading disabled by client`, slot
        `dt-gremah_tick-pmam3-live`) sumiu do historico da tela e so' sobrou
        no log do supervisor. Pior: `IntradaySessionMachine.resting_limit` ja
        estava gravado, entao o robo passou a hora seguinte vigiando um fill
        que nao podia acontecer. `place_limit` garante que nada ficou no book
        (cancela as fatias ja enviadas antes de levantar), entao esquecer a
        ordem e' a leitura HONESTA do estado, nao um chute otimista.

        O robo nao e' avisado da recusa, e isso e' deliberado (regra 6 do
        AGENTS.md): re-armar agora seria uma decisao que `live/` estaria
        tomando sozinha, e que nenhum backtest reproduz (recusa de corretora
        nao existe la'). Ele re-arma pelo proprio criterio -- e a proxima
        `EnterLimit` vira rodada NOVA no diario (`replaced is None`, porque a
        maquina nao vigia mais nada), nao uma "substituicao" de uma ordem que
        nunca existiu."""
        # `numero is None`: a ordem foi plantada pelo warm start direto em
        # `resting_limit` e nunca passou por `_on_limit_placed`, entao nunca
        # ganhou numero de rodada (mesmo caso descrito la').
        rotulo = f"#{numero:02d}" if numero else "warm start"
        self.machine.discard_resting_limit()
        # `place_limit` tenta desfazer as fatias ja enviadas antes de levantar,
        # mas o cancelamento tambem pode nao ser confirmado -- esses tickets
        # vem em `erro.orphan_refs` e NAO podem ser esquecidos aqui.
        self._snapshot.pending_entry_refs = list(dict.fromkeys(erro.orphan_refs))
        self._log(conn, account.id, "error",
                  f"RECUSADA {rotulo}: {erro}",
                  {"numero_ordem": numero, "erro": str(erro),
                   "sessao": sessao.isoformat()})

    #: Traducao do `LimitCancelled.reason` da maquina (backtest/intraday/
    #: machine.py) para o texto que aparece no diario -- ver `_on_limit_
    #: cancelled`. `.get(..., evento.reason)` cobre um motivo novo que a
    #: maquina venha a emitir sem quebrar o log (mostra o motivo cru em vez
    #: de "None").
    _MOTIVO_CANCELAMENTO_PT = {
        "flatten": "fim do pregão",
        "ttl": "esperou demais sem tocar",
        "superseded": "substituída por nova decisão",
        "position_closed": "posição fechada",
    }

    def _on_limit_cancelled(self, conn, account: AccountState, evento: LimitCancelled) -> None:
        """Uma ordem-limite vigiada deixou de valer sem preencher.

        Grava no diario -- mesmo pedido do dono de `_on_limit_placed` (ver a
        docstring la').

        Em execucao real, cancelar de verdade no terminal e' obrigatorio: a
        ordem que o robo abandonou continuaria viva na corretora e poderia
        preencher horas depois, contra um preco que o robo ja descartou."""
        self._snapshot.ordens_abandonadas += 1
        numero = self._numero_ordem_atual()
        motivo = self._MOTIVO_CANCELAMENTO_PT.get(evento.reason, evento.reason)
        qtd = sum(evento.order.children(self.config.default_quantity))
        self._log(conn, account.id, "info",
                  f"CANCELA {evento.order.side.upper()} #{numero:02d} "
                  f"{self._lotes_txt(qtd)} {self.strategy.symbol} "
                  f"@ {evento.order.limit_price:.4f} ({motivo})",
                  {"numero_ordem": numero, "side": evento.order.side,
                   "tipo": "cancelada", "quantity": qtd,
                   "limit_price": evento.order.limit_price, "reason": evento.reason,
                   "sessao": self._snapshot.session.isoformat()})
        # A medicao de fila e' POR ORDEM: o que negociou no nivel da ordem
        # abandonada nao diz nada sobre o nivel da proxima, que e' outro preco.
        self._volume_no_nivel = 0.0
        if self.executor is not None:
            # A maquina cancelou o `resting_limit` que este ticket rastreava,
            # mas quem resolve o ticket e' a CORRETORA, nao a maquina: so' sai
            # da vigilancia o que ela confirmou morto (`_aplica_cancelamento`).
            self._aplica_cancelamento(
                conn, account,
                self.executor.cancel_limit(evento.ts, reason=evento.reason))
        else:
            # Modo sombra: nao ha ticket real nenhum para reconciliar.
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

        # Compromete o capital da entrada -- sem isto, `AccountState.equity()`
        # (`caixa + invested()`, usada pelo painel para "Carteira") conta o
        # mesmo dinheiro duas vezes: uma no caixa (nunca debitado) e outra no
        # valor a mercado da posicao aberta. Espelha `live/runtime.py` (linha
        # `account.cash -= custo` no swing), que ja faz este debito na
        # entrada; aqui faltava. Devolvido em `_on_closed`/`_on_closed_partial`.
        custo = evento.price * evento.quantity
        if self.execution_mode == "shadow":
            account.cash_sombra -= custo
        else:
            account.cash -= custo

        numero = self._numero_ordem_atual()
        # Sem "SOMBRA" na frente (pedido do dono, 2026-08-25): o modo e' fixo
        # no SLOT e ja aparece na etiqueta do cartao ("real"/"simulacao", ver
        # `operacao_body.html`) -- um console so' tem linha de um modo, entao
        # repetir a palavra em toda linha era ruido. `execution_mode` continua
        # no payload, que e' de onde a auditoria le.
        self._log(conn, account.id, "info",
                  f"{evento.side.upper()} #{numero:02d} "
                  f"{self._lotes_txt(evento.quantity)} {self.strategy.symbol} "
                  f"@ {evento.price:.4f}{self._bracket_txt(evento.stop, evento.target)}",
                  {"numero_ordem": numero, "side": evento.side, "price": evento.price,
                   "tipo": "preenchida",
                   "quantity": evento.quantity, "stop": evento.stop, "target": evento.target,
                   "penetration_ticks": penetration, "volume_no_nivel": volume_no_nivel,
                   "execution_mode": self.execution_mode,
                   "sessao": self._snapshot.session.isoformat()})

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

        # Mesmo debito de `_on_opened` (ver comentario la') -- so' desta
        # FATIA nova, nao da posicao inteira (a fatia anterior ja foi
        # debitada quando ela mesma preencheu).
        custo = evento.price * evento.quantity
        if self.execution_mode == "shadow":
            account.cash_sombra -= custo
        else:
            account.cash -= custo

        numero = self._numero_ordem_atual()
        self._log(conn, account.id, "info",
                  f"TOP-UP {evento.side.upper()} #{numero:02d} "
                  f"+{self._lotes_txt(evento.quantity)} {self.strategy.symbol} "
                  f"@ {evento.price:.4f} (total {self._lotes_txt(pos_total.quantity)})"
                  f"{self._bracket_txt(pos_total.current_stop, pos_total.current_target)}",
                  {"numero_ordem": numero, "side": evento.side, "price": evento.price,
                   "tipo": "preenchida",
                   "quantity": evento.quantity, "quantidade_total": pos_total.quantity,
                   "preco_medio_total": pos_total.entry_price,
                   "stop": pos_total.current_stop, "target": pos_total.current_target,
                   "execution_mode": self.execution_mode,
                   "sessao": self._snapshot.session.isoformat()})

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

        # Devolve o capital que `_on_opened`/`_on_opened_top_up` debitaram
        # (`trade.entry_price` ja e' o preco medio da posicao inteira, o
        # MESMO usado em `capital_allocated` -- multiplicado pela quantidade
        # que fecha AQUI, e' exatamente o que foi comprometido por ela) mais
        # o resultado realizado.
        liberado = trade.entry_price * trade.quantity
        if self.execution_mode == "shadow":
            self._snapshot.shadow_pnl_brl += evento.pnl_brl
            account.cash_sombra += liberado + evento.pnl_brl
        else:
            account.cash += liberado + evento.pnl_brl

        numero = self._numero_ordem_atual()
        # Rodada TERMINADA -- a proxima entrada (nova `LimitPlaced` com
        # `replaced=None`, ou uma nova semente de warm start) tem de pegar
        # numero NOVO, nao continuar contando pra esta que acabou de fechar.
        self._snapshot.trade_num = None
        # O MOTIVO abre a linha (STOP/TARGET/FLATTEN...): e' o que o dono
        # procura quando varre o console atras de por que a rodada morreu --
        # antes ficava enterrado num parentese no fim da linha.
        motivo = self._MOTIVO_SAIDA_TXT.get(trade.exit_reason.value,
                                            trade.exit_reason.value.upper())
        self._log(conn, account.id, "info",
                  f"{motivo} {trade.side.upper()} #{numero:02d} "
                  f"{self._lotes_txt(trade.quantity)} {self.strategy.symbol} "
                  f"@ {trade.exit_price:.4f} - R$ {evento.pnl_brl:+.2f}",
                  {"numero_ordem": numero, "side": trade.side,
                   "exit_reason": trade.exit_reason.value,
                   "pnl_brl": round(evento.pnl_brl, 4), "entry_price": trade.entry_price,
                   "exit_price": trade.exit_price, "execution_mode": self.execution_mode,
                   "assinado_saida": assinado_saida,
                   "sessao": self._snapshot.session.isoformat()})

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
        # Mesma devolucao de `_on_closed` (ver comentario la'), so' da FATIA
        # que fechou aqui -- o resto continua comprometido, a posicao segue
        # aberta com `pos_total.quantity` restante.
        liberado = trade.entry_price * trade.quantity
        if self.execution_mode == "shadow":
            self._snapshot.shadow_pnl_brl += evento.pnl_brl
            account.cash_sombra += liberado + evento.pnl_brl
        else:
            account.cash += liberado + evento.pnl_brl

        numero = self._numero_ordem_atual()
        motivo = self._MOTIVO_SAIDA_TXT.get(trade.exit_reason.value,
                                            trade.exit_reason.value.upper())
        self._log(conn, account.id, "info",
                  f"{motivo} {trade.side.upper()} #{numero:02d} "
                  f"{self._lotes_txt(trade.quantity)} {self.strategy.symbol} "
                  f"@ {trade.exit_price:.4f} - R$ {evento.pnl_brl:+.2f} "
                  f"(resta {self._lotes_txt(pos_total.quantity)})",
                  {"numero_ordem": numero, "side": trade.side,
                   "exit_reason": trade.exit_reason.value,
                   "pnl_brl": round(evento.pnl_brl, 4), "quantidade_restante": pos_total.quantity,
                   "execution_mode": self.execution_mode,
                   "sessao": self._snapshot.session.isoformat()})

    # ---------- painel -------------------------------------------------------

    def status(self, full: bool = False, limit: int = 1000) -> dict:
        """Mesmo formato de `LiveRuntime.status()` — o template de `/operacao`
        le as duas fontes pelas mesmas chaves. Campos que so o day trade tem
        (sombra, penetracao) entram em `daytrade`, sem colidir.

        Eventos: por padrao so o pregao ATUAL (`day=session.isoformat()`),
        nunca paginado -- o console tem scroll proprio (`.console` em
        pages.css), entao nao ha "ver mais" para o dono clicar nem risco de
        acumular historico de dias antigos no cartao. `full=True` (botao
        "Diario Completo" do painel) troca isso por TODO o historico da
        conta (`day=None`) -- ai' `limit` vira a PRIMEIRA pagina do scroll
        infinito (`app.py::OPS_EVENTOS_PAGINA_INICIAL`), nao mais um teto de
        seguranca de 1000: sob pedido do dono, o clique carrega pouco e
        rapido, e o restante do historico vem sob demanda conforme rola
        (`app.py::operacao_eventos_mais_antigos`).
        """
        session = clock.intraday_session()
        with store.live_journal(self.db_path) as conn:
            account = self._load_account(conn)
            if account is None:
                return {"conta": self.account_name, "existe": False}
            self._restore(account, session)
            eventos = store.recent_events(conn, account.id, limit=limit,
                                          day=None if full else session.isoformat())
            saidas = store.daytrade_exit_events(conn, account.id)
            ordens_hoje = store.daytrade_order_events_on(conn, account.id, session.isoformat())

        resultado = self._resultado_dia_e_acumulado(saidas, session.isoformat(), account.initial_capital)
        ordens_stats = self._ordens_por_lado(ordens_hoje)

        # `self.machine.positions` (a LISTA), nunca o atalho `machine.position`:
        # em sombra cada lote preenchido virou uma posicao INDEPENDENTE desde
        # 2026-08-24, e o atalho levanta `RuntimeError` com mais de uma -- o
        # painel inteiro virava erro 500 justamente no pregao em que o robo
        # dividiu a entrada e pegou dois lotes (`dividir_entrada` e' padrao
        # `True` nos dois robos desde 2026-08-23). Em execucao REAL a lista tem
        # no maximo um elemento (a maquina funde os fills num agregado, ver a
        # docstring da classe), entao nada muda desse lado.
        posicoes = list(self.machine.positions)
        qtd_total = sum(p.quantity for p in posicoes)
        # Preco de marcacao = entrada MEDIA PONDERADA das posicoes abertas. Com
        # uma posicao e' identico ao que era antes; com N e' o unico numero que
        # nao inventa preco -- `status()` tem proibicao de tocar na corretora,
        # entao marcar na entrada (P&L nao realizado = 0) e' deliberado.
        entrada_media = (
            sum(p.entry_price * p.quantity for p in posicoes) / qtd_total
            if qtd_total else 0.0
        )
        marks = {self.strategy.symbol: entrada_media} if posicoes else {}
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
            "eventos": eventos,
            "eventos_full": full,
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
                # Contagem de POSICOES INDEPENDENTES por lado, tirada da
                # maquina -- nao de `account.positions`, que e' um dicionario
                # POR TICKER: uma conta de day trade tem um simbolo so, entao
                # ali a contagem era sempre 0 ou 1, dissesse a verdade ou nao.
                # Dois lotes abertos em sombra apareciam como "1 posicao"
                # (queixa do dono, 2026-08-26). O valor em R$ (`account`,
                # capital alocado) continuava certo -- e' agregado por
                # construcao; aqui ele e' recalculado da mesma fonte da
                # contagem so' para os dois numeros do card nunca divergirem.
                "posicoes_compra": sum(1 for p in posicoes if p.side == "long"),
                "posicoes_venda": sum(1 for p in posicoes if p.side == "short"),
                # Valor em R$ (capital alocado na entrada) das posições
                # abertas de cada lado -- número principal do card
                # "Posições" do painel, com a CONTAGEM acima virando texto
                # secundário (mesmo pedido de `_ordens_por_lado`, 2026-08-24).
                "valor_posicoes_compra": round(
                    sum(p.entry_price * p.quantity for p in posicoes if p.side == "long"), 2),
                "valor_posicoes_venda": round(
                    sum(p.entry_price * p.quantity for p in posicoes if p.side == "short"), 2),
                **resultado,
                **ordens_stats,
                # AGREGADO das posicoes abertas (era a posicao unica). `alvo`/
                # `stop` saem so' quando TODAS concordam: cada posicao
                # independente tem stop proprio desde 2026-08-24, e publicar o
                # da primeira como se fosse o da carteira seria esconder as
                # outras -- `None` diz "nao ha um numero so", que e' a verdade.
                "posicao_aberta": None if not posicoes else {
                    "lado": posicoes[0].side, "qtd": qtd_total,
                    "entrada": round(entrada_media, 4),
                    "alvo": _unanime(p.current_target for p in posicoes),
                    "stop": _unanime(p.current_stop for p in posicoes),
                    # Quantas posicoes INDEPENDENTES compoem o agregado acima
                    # (1 em execucao real, que funde tudo; N em sombra, uma por
                    # lote preenchido).
                    "posicoes": len(posicoes),
                },
                # A maquina primeiro (processo do robo: sempre fresca), o
                # espelho persistido depois (painel: a maquina do runtime de
                # LEITURA nasce vazia -- ver `_SessionSnapshot.ordem_em_pe`).
                "ordem_em_pe": self._espelho_da_ordem_em_pe() or self._snapshot.ordem_em_pe,
                # O offset nao e' mais "calibrado ou presumido": ele e'
                # declarado a partir do fuso medido do servidor. O que o painel
                # precisa mostrar agora e' se a CONFERENCIA acusou divergencia
                # — `None` = nada provado errado.
                "offset_horas": self.bar_feed.offset_hours,
                "corte_flatten_utc": self.machine.session_end_time_for(
                    pd.Timestamp(session)
                ).isoformat(),
                # BRT de verdade (painel, pedido do dono, 2026-08-24) -- NAO e'
                # so subtrair 3h de `corte_flatten_utc`: aquele e' o ROTULO da
                # ultima barra M1 (fica 1min atras do fechamento de verdade, ver
                # `b3_session.closing_bar_minute_utc`). `continuous_end` da' o
                # instante real do fim do pregao continuo, ja em Brasilia (sem
                # fuso para converter -- o Brasil nao tem horario de verao desde
                # 2019). So' vale com a politica "b3_equities"; a "fixed" (testes
                # sinteticos) ja guarda `session_end_time` direto em hora local.
                "corte_flatten_brt": (
                    b3_session.continuous_end(session).strftime("%H:%M")
                    if self.config.session_end_policy == "b3_equities"
                    else self.config.session_end_time.strftime("%H:%M")
                ),
                "relogio_alarme": (self.clock_feed.server_clock_alarm
                                   if self.clock_feed is not None else None),
                # Piso de caixa DE HOJE (ver `_check_capital`). `None` = ainda
                # nao conferido neste pregao (processo recem-subido, ou fora do
                # horario) -- nao e' "sem piso".
                "capital_minimo_hoje": (round(self._capital_minimo_hoje, 2)
                                        if self._capital_minimo_hoje is not None else None),
                "capital_alarme": self._capital_alarm,
                # Por que o robo NAO esta operando agora, mesmo com o
                # processo de pe -- gravado pelo processo do robo (ver
                # `_gravar_impedimento`), lido aqui sem tocar na corretora.
                # So' vale para o pregao de HOJE: um impedimento de ontem que
                # ficou gravado (processo morto antes de resolver) nao pode
                # pintar de vermelho um pregao que nem comecou.
                "impedimento": self._impedimento_de_hoje(account, session),
            },
        }
