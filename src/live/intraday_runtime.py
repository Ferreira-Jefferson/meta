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
from typing import NamedTuple, Optional

import pandas as pd

from backtest.intraday.costs import fees_round_trip_brl
from backtest.intraday.machine import (
    EntradaAMercadoNaoSuportada,
    IntradayBacktestConfig,
    IntradaySessionMachine,
    IntradayTrade,
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
from core.models import IntradayExitReason
from journal import live_store as store
from live import clock
from live.bar_feed import MT5BarFeed
from live.intraday_execution import (BrokerExecutionError, MT5IntradayExecution,
                                     descarta_confirmados, orphan_refs)
from live.margin_lock import MargemTravada, acquire_margin_gate
from live.notify import NullNotifier
from live.runtime import StepReport
from strategy.daytrade.base import (
    Bar,
    EnterLimit,
    IntradayStrategy,
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


def _utc_time_para_brt(t: time) -> time:
    """HORA DO DIA em UTC -> hora do dia em Brasilia, pelo FUSO.

    Existe porque `SymbolProfile.session_end_time` e' UTC ("como todo perfil
    deste modulo", diz `profiles.py`) e o painel precisa mostrar Brasilia --
    ver `corte_flatten_brt`. Sem esta conversao o WDO@ aparecia como
    "FLATTEN 21:30 BRT" em vez de 18:30 (2026-09-08).

    Pelo fuso e nunca por um "-3h" fixo, mesma regra de `_hora_brt` e de
    `core/b3_session.py`: o Brasil nao tem horario de verao desde 2019, mas
    escrever a subtracao na mao e' como o projeto ja errou antes. A data
    usada e' irrelevante para o offset (nao ha DST), entao qualquer uma
    serve para converter uma hora-do-dia solta."""
    base = datetime.combine(date(2026, 1, 1), t, tzinfo=timezone.utc)
    return base.astimezone(SAO_PAULO).time()


MAX_GAP_SECONDS = 15 * 60.0

#: Quanto uma barra pode estar ATRASADA (segundos entre o `ts` dela e o
#: relogio de parede) e ainda assim poder virar ORDEM NOVA na corretora.
#: Somado ao atraso ESTRUTURAL do feed (`nominal_delay_seconds`) -- ver
#: `IntradayLiveRuntime._limite_de_atraso`.
#:
#: 2026-09-08, o pregao que pagou por isto (slot
#: `dt-wdo_grid_reload_maker-wdo@-live`, -R$116 no dia). O terminal MT5
#: parou de entregar tick NOVO de WDO@ por 44,8 min sem erro nenhum:
#: `closed_bars_since` devolveu lista VAZIA em 538 passos seguidos com a
#: marca d'agua congelada em 14:14:20.804, e no passo seguinte devolveu
#: 13.644 barras de uma vez. O estado da conta as 15:00:57 mostrava
#: `last_bar_ts=14:36:21` contra `last_poll_at=15:00:57` -- 24 min de
#: atraso -- e o loop `for bar in barras` tratou CADA barra velha como se
#: fosse agora: 45 ordens-limite REAIS posicionadas em precos de ate' 45
#: min atras. Uma limite num preco que ja' morreu chega ao book como
#: ordem AGRESSIVA (marketable) e preenche na hora no pior preco, com o
#: alvo -- calculado a partir do mesmo nivel morto -- ja' violado: a
#: sequencia real foi -R$5,50 por ida e volta, repetida ate' o freio de
#: perda do dia disparar.
#:
#: O freio que JA existia (`MAX_GAP_SECONDS`) nao pegou nada, e nao tinha
#: como: ele mede tempo sem RODAR (`_parado_ha_segundos`), e o processo
#: rodou o tempo todo, de 5 em 5 segundos. Quem estava velho era o DADO,
#: nao o processo. Este teto e' o que faltava -- mede a idade da BARRA.
#:
#: O numero (120s) e' folga larga sobre a entrega saudavel, MEDIDA no
#: mesmo terminal em 2026-09-08 -- sonda de 5 em 5s reproduzindo a chamada
#: exata do feed (`MT5TickFeed.closed_bars_since`) por 22 min de pregao,
#: 260 passos, 249 deles com barra: p50 = 0,14s, p99 = 4,17s, maximo
#: 4,27s, limitado pelo proprio passo de 5s do supervisor. 120s e' ~29x o
#: p99, entao um dia de feed lento nao cala o robo (que e' o modo de falha
#: do item 6.15 do `LICOES_DE_PRODUCAO.md`); e' curto o bastante para que
#: nada parecido com os 24-45 min de 08/09 passe.
MAX_ATRASO_PARA_ORDEM_SEGUNDOS = 120.0

#: Gap (f), incidente 2026-08-28: quantas recusas SEGUIDAS de fechamento
#: (`BrokerExecutionError` vindo de `MT5IntradayExecution.exit_market`) o
#: robo tenta sozinho, a cada passo, antes de acionar o freio duro
#: (`_SessionSnapshot.disaster_halt`) e parar de insistir na mesma
#: cadencia. O incidente real teve ~24 recusas seguidas (MG51, margem
#: esgotada) sem NENHUMA escalar alem de log repetido -- um numero pequeno
#: aqui e' deliberado: depois de algumas tentativas martelando a MESMA
#: causa estrutural (margem, book morto, autotrading desligado), continuar
#: batendo a cada 5s nao resolve nada sozinho, so' produz mais linha de
#: log. Zerado a cada fechamento que DA CERTO (ver `_on_closed`/
#: `_on_closed_partial`), entao uma falha isolada e transitoria nunca chega
#: perto do teto.
MAX_CLOSE_REFUSALS_BEFORE_HALT = 5

#: Fracao do capital do slot que este robo pode perder NUM PREGAO antes do
#: freio duro travar a sessao. Default de projeto, nao medicao -- o dono pode
#: sobrescrever por slot (`perda_maxima_dia_brl` no construtor).
#:
#: Por que ele existe: ate 2026-08-28 o UNICO freio ao vivo era `equity <=
#: 0` -- patrimonio ja negativo. Entre "esta indo mal" e "morreu" nao havia
#: nada. O `session_stop_brl` que ALGUMAS estrategias implementam nao cobre
#: isto por tres motivos: e' opcional por robo, olha so' P&L JA REALIZADO, e
#: so' impede entrada NOVA -- nunca limita quanto uma posicao ja aberta pode
#: perder. No incidente real a perda inteira (-R$295) estava NAO REALIZADA
#: por uma hora, com a corretora recusando o fechamento; nenhum stop de
#: sessao teria visto um centavo dela.
#:
#: Este freio olha o P&L do pregao MARCADO A MERCADO (realizado + aberto),
#: entao dispara com a posicao ainda de pe -- que e' o unico momento em que
#: disparar ainda serve pra alguma coisa.
FRACAO_PERDA_MAXIMA_DIA = 0.30

#: Quanta margem livre a conta precisa ter, como multiplo do que a ordem
#: exige, para o envio ser autorizado. E' o mesmo fator 2.0 que o projeto ja
#: usa como buffer de margem em todo dimensionamento
#: (`MARGIN_BUFFER_FUTUROS`/`capital_minimo_brl`, ver CLAUDE.md) -- aplicado
#: agora tambem no portao de ENVIO, contra a margem REAL da conta.
#:
#: O fator importa mais do que parece. No incidente, depois do 1o contrato a
#: margem livre era ~R$150 e o 2o contrato exigia R$150: com fator 1.0 o
#: envio passaria (150 >= 150) e a conta zerava do mesmo jeito. Com 2.0 ele
#: e' recusado (150 < 300). Um portao que so' impede o impossivel nao e'
#: portao -- ele tem de impedir o ULTIMO passo que ainda cabia.
MARGEM_LIVRE_MINIMA_FATOR = 2.0

#: Quantas leituras SEGUIDAS de `account_risk_state()` podem falhar antes de
#: o robo parar de operar. "Nao sei" isolado nunca e' motivo de freio (a
#: politica do arquivo inteiro), mas "nao sei" CONTINUADO e' outra coisa:
#: significa operar por tempo ilimitado sem nenhuma leitura de risco, com o
#: unico freio de ruina cego. O desenho antigo apostava que quem nao consegue
#: ler equity tambem vai falhar em mandar ordem -- razoavel, e nao garantido
#: por nada. A ~5s por passo, 20 leituras sao ~100s de terminal mudo.
MAX_LEITURAS_DE_RISCO_FALHAS = 20

#: DOIS TETOS, DOIS DESFECHOS -- ler os dois juntos, nunca um so'.
#:
#: Ate' 2026-09-08 existia um numero so' (`MAX_ENVIOS_POR_MINUTO = 30`) e
#: ele era um DISJUNTOR: ao ser atingido ligava `disaster_halt` e o robo
#: ficava mudo o pregao inteiro. Dois fatos do mesmo dia derrubaram esse
#: desenho.
#:
#: 1. O numero 30 foi calibrado no relogio ERRADO. Ate' o commit 75f6b48 o
#:    contador recebia `evento.ts` (tempo de TICK); a docstring dele ainda
#:    dizia "pior minuto 26 de 30", que era tempo de tick. No relogio de
#:    PAREDE -- o unico que a corretora tem -- o portao e' muito mais
#:    apertado, e aquele 26 nao descreve mais nada.
#: 2. A cadencia LEGITIMA ja passa de 30. Medicao IS/OOS de 2026-09-08
#:    (commit e8f88fe, config de producao T2/S16 + histerese): o pior
#:    minuto do OOS da' 42 envios, COM e SEM a histerese -- saturacao de
#:    `max_trades_per_side` (rearme pos-fill), nao laco. Ou seja: num
#:    pregao movimentado NORMAL o robo estourava o teto e se calava
#:    sozinho, que e' o modo de falha do item 6.15 do
#:    `LICOES_DE_PRODUCAO.md` (a janela censurada que parece edge negativo
#:    e e' so' o robo calado).
#:
#: A forma certa ja existia no proprio projeto e o dono apontou para ela:
#: o freio da estrategia (`WdoGridReloadMaker.reancora_min_segundos=10.0`,
#: no maximo 6 reprecificacoes por minuto) RECUSA a acao e segue vivo --
#: nunca derruba o robo. Este par de tetos copia esse comportamento e
#: guarda o disjuntor so' para patologia de verdade:
#:
#:   COTA_ENVIOS_POR_MINUTO    -> vazao. Recusa ESTE envio, o robo segue.
#:   MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO -> patologia. Liga `disaster_halt`.
#:
#: Sem o segundo nivel a correcao trocaria um modo de falha por outro: um
#: laco infinito de verdade viraria "robo rate-limited para sempre,
#: parecendo saudavel", e a falha que motivou o teto original (incidente
#: 2026-08-28, ~24 ordens marteladas em minutos sem nada contar) voltaria a
#: passar batida -- so' que em silencio.

#: TETO OPERACIONAL (vazao): quantas ordens de ENTRADA este robo pode
#: mandar de fato numa janela ROLANTE de 60s de relogio de PAREDE. Ao ser
#: atingido, o envio que estourou e' RECUSADO e a maquina esquece a ordem
#: (`machine.discard_resting_limit`, mesmo caminho da recusa por margem e
#: da barra velha) -- o robo continua vivo, continua fechando posicao e
#: rearma pelo criterio DELE na barra seguinte.
#:
#: 120 saiu de medicao, com a margem que o dono pediu ("uma boa margem de
#: seguranca pro robo nao cair por conta disso"). Distribuicao do PIOR
#: MINUTO POR PREGAO (`scripts/daytrade/
#: wdof1_cadencia_envios_distribuicao_2026_09_08.py`):
#:
#:   fonte                       n     p50   p90   p95   p99   max
#:   backtest IS (mercado)      72     12    19    20    22     23
#:   backtest OOS (mercado)     51     10    19    24    34     42
#:   ao vivo 08/09 (parede)      1      3    12    15    18     19
#:
#:   * Backtest = motor tick, IS/OOS congelado, config de producao T2/S16
#:     com histerese, base `WDO_A_f1` regenerada em 07/09, capital real
#:     R$375. E' o relogio de MERCADO, e mede a cadencia LEGITIMA: quantas
#:     ordens a estrategia decide mandar num minuto real. Nenhum dos 123
#:     pregoes passa de 50; UM (0,8%) passa de 30 -- o teto antigo.
#:   * Ao vivo = `db/live.sqlite`, conta 476 (slot SOMBRA de WDO@, pregao
#:     inteiro de 2026-09-08, 173 envios), janela rolante de 60s no
#:     carimbo de ESCRITA do diario, que e' relogio de parede. O slot REAL
#:     (conta 474) do mesmo dia da' max 64, mas aquele numero e' de um
#:     pregao com o feed cego e sem a histerese -- as duas causas ja
#:     corrigidas (`MAX_ATRASO_PARA_ORDEM_SEGUNDOS` e `reancora_min_ticks`).
#:
#:   120 e' ~2,9x o maior pior-minuto LEGITIMO ja observado (42), ~3,5x o
#:   p99 do OOS e ~6x o pior minuto de parede de um pregao inteiro ao vivo.
#:   * regime PATOLOGICO conhecido, para saber de que lado o numero cai:
#:     antes do freio `reancora_min_segundos` o mesmo robo fazia 1.020 a
#:     3.446 envios no pior minuto (tabela no docstring do modulo
#:     `strategy.daytrade.lab.wdo_grid_reload_maker`). 120 esta' uma ordem
#:     de grandeza abaixo disso e quase 3x acima do legitimo -- a faixa
#:     entre um e outro e' larga de proposito.
#: Carga real na corretora e' ~o dobro deste numero: toda substituicao
#: manda um cancelamento junto (`_aplica_cancelamento`, que NAO consome
#: cota -- ver `_check_cadencia_de_ordens`). 120 entradas/min ~ 240
#: requisicoes/min ~ 4/s, que nao e' rajada para terminal nenhum.
COTA_ENVIOS_POR_MINUTO = 120

#: TETO DE PATOLOGIA (disjuntor): quantas TENTATIVAS de arme -- incluindo
#: as que a cota acima ja recusou -- numa janela rolante de 60s de parede
#: antes de `disaster_halt`. Conta tentativa e nao envio de proposito: se
#: contasse envio, a cota o limitaria a 120 por construcao e o disjuntor
#: nunca dispararia, que e' exatamente o "robo rate-limited para sempre"
#: que este segundo nivel existe para impedir.
#:
#: 600 = 5x a cota, ~14x o pior minuto legitimo ja medido (42, OOS) e
#: ainda bem abaixo do piso do regime patologico medido (1.020 no pregao
#: mais leve dos cinco da tabela do robo). Em taxa: 10 armes por SEGUNDO,
#: sustentados por um minuto inteiro. Nenhuma estrategia deste repo decide
#: nisso -- `reancora_min_segundos` sozinho limita a 6/min por lado no
#: relogio de barra.
#:
#: RESIDUAL: um laco LENTO (um arme por passo do supervisor, ~12/min) nao
#: dispara nem a cota nem o disjuntor. Nao e' regressao -- o teto de 30
#: tambem nao pegava -- e tambem nao e' risco de corretora nessa taxa; o
#: que pega esse caso e' a contagem por lote no diario, nao um teto.
MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO = 600


class ExcessoDeCadencia(NamedTuple):
    """O que `_check_cadencia_de_ordens` devolve quando um dos dois tetos
    fecha. `patologia` e' a diferenca que importa: `False` recusa SO' este
    envio (o robo segue vivo), `True` liga o freio duro."""

    patologia: bool
    motivo: str
    envios: int
    tentativas: int


#: TEMPO DE VIDA DA POSICAO -- gravado no diario, NAO alarmado. Ler a
#: ressalva antes de usar este numero para qualquer decisao.
#:
#: Motivacao: no pregao de 2026-09-08 (`dt-wdo_grid_reload_maker-wdo@-live`)
#: 11 das 22 posicoes abriram e fecharam em MENOS DE 1 SEGUNDO segundo o
#: historico de deals da CORRETORA (58ms, 62ms, 64ms, 66ms, 100ms, 109ms,
#: 127ms, 288ms, 319ms, 342ms, 561ms) -- -R$40,50 dos -R$116,00 do prejuizo
#: (34,9%). Todas foram gravadas como `exit_reason="target"`, e nada no
#: diario as distinguia de um alvo de verdade: com elas o pregao mostra 31,8%
#: de acerto (7/22); sem elas, 54,5% (6/11).
#:
#: RESSALVA que impede o alarme automatico, e e' a MESMA licao do relogio que
#: `_check_cadencia_de_ordens` aprendeu no mesmo pregao: nenhum dos dois
#: relogios que este processo tem mede o que a frase acima mede.
#:   - `duracao_s` sai de `IntradayTrade.entry_ts/exit_ts`, que sao carimbos
#:     de TICK. Com a maquina 24 min atrasada, 58ms reais podem aparecer como
#:     dezenas de segundos de tick -- nao teria pego nenhum dos 10.
#:   - `duracao_parede_s` sai do relogio deste processo entre `_on_opened` e
#:     `_on_closed`. Quando os dois eventos caem no MESMO passo do supervisor
#:     (o caso comum na rajada, e SEMPRE no caminho de reconciliacao por
#:     historico) ele mede a latencia do nosso laco, nao a vida da posicao.
#: O unico relogio que responde a pergunta e' o da corretora (`time_msc` dos
#: deals). Desde 2026-09-08 ele ESTA plumbado: `_on_closed` grava
#: `duracao_corretora_ms` no evento de fechamento, vindo de
#: `MT5IntradayExecution.vida_da_posicao_ms`. Ele reclassificou o pregao
#: inteiro: sao 11 (nao 10) posicoes abaixo de 1 s -- a de 288 ms, que deu
#: +R$5,00, tambem e' round-trip -- e -R$40,50 dos -R$116,00 (34,9%). Contra
#: esses 11 casos, o relogio de TICK acha 4 e inventa 1 falso positivo, e o
#: de PAREDE acha 1; por isso os dois seguem sendo DIAGNOSTICO e nenhum dos
#: tres alarma sozinho -- o piso do que conta como round-trip e' decisao de
#: estrategia/dono, e alarme montado sobre relogio nao validado foi o erro
#: que `_check_cadencia_de_ordens` ja cometeu neste mesmo pregao. Quem alarma
#: sozinho hoje e' `deslize_vs_alvo_brl`, que nao depende de relogio nenhum e
#: pegaria as 22 saidas daquele pregao. Ver item 4.16 de
#: `LICOES_DE_PRODUCAO.md`.


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
    # ULTIMO resultado de `MT5Broker.foreign_activity()` -- so' para
    # detectar a TRANSICAO (nada -> algo, algo -> nada) e nao spammar o
    # diario a cada passo enquanto a atividade estranha persiste (ver
    # `_check_atividade_estranha`). Persistido para sobreviver a um
    # restart no meio do pregao sem re-logar o que ja tinha sido avisado.
    atividade_estranha: Optional[dict] = None
    # Freio duro (gap (e)/(f), incidente 2026-08-28): a conta chegou a
    # equity NEGATIVA (-R$298,60) com o processo CONTINUANDO a abrir e
    # fechar ordem, sem freio nenhum -- e as ~24 recusas seguidas de
    # fechamento (MG51) nunca escalaram alem de log repetido. `disaster_halt`
    # e' persistido (nao so' em memoria) DE PROPOSITO: um restart no meio do
    # freio nao pode "esquecer" que a sessao esta travada e voltar a tentar
    # abrir ordem nova sozinho. Dura o resto da SESSAO -- reseta sozinho no
    # proximo pregao (`_SessionSnapshot` novo), porque nao ha caminho
    # automatico de "equity voltou, libera de novo": isso e' decisao do
    # DONO (deposito, investigacao), nunca do robo (regra 6 do AGENTS.md).
    disaster_halt: bool = False
    disaster_reason: Optional[str] = None
    # Recusas de FECHAMENTO seguidas (zerado a cada fechamento que da certo,
    # ver `_registra_falha_de_fechamento`/`_on_closed`) -- e' o contador que
    # decide quando `disaster_halt` liga sozinho por gap (f).
    close_refusal_count: int = 0

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
            "atividade_estranha": self.atividade_estranha,
            "disaster_halt": self.disaster_halt,
            "disaster_reason": self.disaster_reason,
            "close_refusal_count": self.close_refusal_count,
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
            atividade_estranha=raw.get("atividade_estranha") or None,
            disaster_halt=bool(raw.get("disaster_halt") or False),
            disaster_reason=raw.get("disaster_reason") or None,
            close_refusal_count=int(raw.get("close_refusal_count") or 0),
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
        perda_maxima_dia_brl: Optional[float] = None,
        somente_leitura: bool = False,
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
        # Teto de perda do PREGAO, marcado a mercado (ver
        # `FRACAO_PERDA_MAXIMA_DIA` e `_check_freio_duro`). `None` = usa a
        # fracao default sobre o capital do slot; `0.0` (ou negativo)
        # DESLIGA o freio de perda -- o que so' faz sentido em teste, e
        # nunca em conta com dinheiro: o teto de ruina (`equity <= 0`)
        # continua valendo de qualquer jeito, mas ele so' age quando ja e'
        # tarde demais.
        if perda_maxima_dia_brl is None:
            perda_maxima_dia_brl = FRACAO_PERDA_MAXIMA_DIA * self.initial_capital
        self.perda_maxima_dia_brl = float(perda_maxima_dia_brl)
        self.bar_feed = bar_feed
        # Quantos passos SEGUIDOS o feed vem falhando a leitura do terminal.
        # So em memoria, e nao no snapshot, de proposito: e' propriedade da
        # SESSAO DE PROCESSO (um restart reconecta ao terminal e a contagem
        # tem de recomecar do zero), e persistir faria o robo voltar do
        # restart ja' gritando por uma cegueira que pode nao existir mais.
        # Ver `_vigia_leitura_do_feed`.
        self._falhas_de_leitura_seguidas = 0
        self.broker = broker
        self.notifier = notifier if notifier is not None else NullNotifier()
        self.execution_mode = execution_mode
        self.db_path = Path(db_path) if db_path is not None else LIVE_DB_PATH
        # So o modo REAL injeta a ponte de execucao na maquina. Em sombra ela
        # fica `None` e os fills seguem simulados pela barra -- que e'
        # exatamente o que o modo sombra existe para medir contra a realidade
        # (ver `penetration_ticks`). Ver `live/intraday_execution.py` para por
        # que a fonte de verdade tem de trocar quando ha dinheiro em jogo.
        #
        # `somente_leitura` e' o runtime do PAINEL (`live_service.
        # _build_intraday_runtime`), que reporta o modo de verdade -- inclusive
        # "live" -- mas nunca da um passo. Ele tambem nao pode segurar a ponte:
        # com `execution` setada, `IntradaySessionMachine.restore` FALHA ALTO ao
        # topar uma fatia de saida posicionada (o ticket dela so' vive em
        # memoria do processo do robo), e essa recusa -- correta para quem vai
        # voltar a operar -- derrubava a pagina `/operacao` INTEIRA em 500,
        # todos os slots junto, justamente quando o dono mais precisa ver o
        # painel para saber o que conferir no terminal. Uma pagina de leitura
        # nao tem o que fazer com uma ponte de ordens.
        self.somente_leitura = bool(somente_leitura)
        self.executor = (
            MT5IntradayExecution(broker, strategy.symbol)
            if execution_mode == "live" and not self.somente_leitura else None
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
        # Contagem do LOTE corrente de barras: quantos armes de entrada nao
        # foram ao book por barra velha, e o pior atraso visto. Zerados no
        # topo de cada `_consume` -- so' existem aqui para os dois pontos de
        # saida antecipada dele poderem journalizar a mesma contagem. Nao vao
        # para o snapshot de proposito: descrevem UM passo, nao o pregao.
        self._armes_de_barra_velha = 0
        self._atraso_max_barra_velha = 0.0
        self._ultima_barra_velha: Optional[pd.Timestamp] = None
        self._limite_atraso_do_lote = 0.0
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
        #: Versao do alarme acima escrita PARA O DONO LER NO PAINEL, com o
        #: quanto falta em reais. Ver `_check_capital`.
        self._capital_impedimento: Optional[str] = None
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
        # Ultimo resultado de `_ensure_protecao`, POR TICKET de posicao --
        # so' para nao repetir o alerta de "nao consegui proteger" a cada
        # passo enquanto a falha persiste (mesmo padrao de
        # `_autotrading_alarmado`). Em memoria, nao persistido: um restart
        # tenta de novo e alerta de novo se ainda estiver falhando, o que e'
        # o comportamento certo (nao ha motivo pra "lembrar" silencio de um
        # processo que nem existe mais).
        #
        # Por TICKET, e nao um flag so' do processo: era um booleano unico, e
        # bastava UMA falha para o robo ficar mudo sobre TODAS as posicoes
        # seguintes -- a posicao B falhava em proteger e ninguem era avisado,
        # porque a posicao A ja tinha gasto o unico alerta que existia.
        self._protecao_alarmada: set = set()
        # Ticket -> (stop_pedido, alvo_pedido, sl_registrado, tp_registrado)
        # do ultimo `set_protection` que a corretora ACEITOU. Existe para o
        # reforco nao virar um loop: a corretora pode registrar um nivel
        # DIFERENTE do pedido (distancia minima dela), e comparar o pedido
        # com o registrado daria divergencia eterna -- a cada barra o robo
        # reenviaria, e a cada reenvio o nivel seria recalculado contra o
        # preco NOVO, fazendo o stop "fugir" do preco conforme ele se
        # aproxima. Guardando o par, so' reenvia quando algo de fato mudou
        # (a maquina moveu o stop, ou a protecao sumiu da corretora).
        self._protecao_registrada: dict = {}
        # Tickets de posicao que a corretora reporta para o magic deste robo
        # e que a MAQUINA nao conhece -- avisados uma vez cada (ver
        # `_check_posicao_desconhecida`).
        self._posicao_desconhecida_avisada: set = set()
        # A corretora esta' de um lado e a maquina do outro? Enquanto isto for
        # True o freio duro NAO tenta fechar a posicao sozinho -- ver
        # `_tenta_zerar_por_freio_duro`. Nao e' persistido de proposito: um
        # processo novo re-descobre a divergencia no primeiro passo
        # (`_check_posicao_desconhecida` roda antes de consumir barra) e
        # levanta o flag de novo, entao persistir so' criaria um segundo
        # estado para sair de sincronia com o primeiro.
        self._lado_divergente: bool = False
        # Envios ja' recusados por margem da conta, para nao repetir a mesma
        # linha no diario a cada barra enquanto a conta segue apertada (ver
        # `_check_margem_da_conta`). So' em memoria: um processo novo alerta
        # de novo, que e' o certo.
        self._margem_alarmada: set = set()
        # Leituras SEGUIDAS de risco que falharam (ver
        # `MAX_LEITURAS_DE_RISCO_FALHAS`). Zerado a cada leitura que volta.
        self._risco_ilegivel_seguidas = 0
        # Pregao em que o dono ja foi avisado de que o MT5 reporta patrimonio
        # zerado/negativo enquanto o ledger do painel tem caixa (ver
        # `_avisa_saldo_mt5_dessincronizado`). Uma linha por pregao e por
        # processo: e' diagnostico, nao alarme.
        self._saldo_mt5_avisado_em: Optional[date] = None
        # Instantes (UTC) dos ultimos envios de ordem que de fato SAIRAM,
        # para a janela rolante de `COTA_ENVIOS_POR_MINUTO`. Em memoria: o
        # alvo e' um laco dentro de UM processo, e um restart ja quebra o
        # laco por construcao.
        self._envios_recentes: list = []
        # Instantes (UTC) de toda TENTATIVA de arme -- inclusive as que a
        # cota recusou -- para a janela rolante de
        # `MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO`. Lista separada por
        # necessidade: contar so' o que saiu deixaria o disjuntor preso
        # abaixo da cota para sempre.
        self._tentativas_recentes: list = []
        # Recusas por COTA neste lote de barras (zerado em `_consume`, uma
        # linha `warn` por lote em `_journaliza_recusas_por_cota`).
        self._recusas_por_cota = 0
        self._pico_de_envios_no_lote = 0
        # Alvo que a estrategia DECLAROU na entrada da posicao aberta agora.
        # Guardado aqui porque `PositionClosed` so' carrega o `IntradayTrade`
        # (preco de saida REAL) e o nivel pedido some junto com a posicao --
        # sem ele nao da' pra' medir deslize de saida nenhum, que e' o item
        # 4.8 e o que escondeu R$45,00 no pregao de 2026-09-08.
        self._alvo_declarado: Optional[float] = None
        # Relogio de PAREDE da abertura -- ver `DURACAO_MINIMA_DE_TRADE_S`
        # para o que este numero mede de verdade (e o que ele NAO mede).
        self._abertura_wall: Optional[datetime] = None

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
    def _ordens_por_lado(ordens_hoje: list[dict], margin_per_contract_brl: float | None = None) -> dict:
        """Compra/venda e preenchida/cancelada de hoje, por lado -- fonte do
        card "Ordens posicionadas" (pedido do dono, 2026-08-24). `None` na
        taxa de preenchimento de um lado = nenhuma ordem daquele lado teve
        desfecho hoje ainda (só tem posta pendente, ou nenhuma ordem).

        `valor_ordens_compra`/`valor_ordens_venda` somam o valor comprometido
        de cada ordem ARMADA -- MARGEM x quantidade quando
        `margin_per_contract_brl` vem preenchido (futuro), quantidade x preço
        quando não (ação; também o default nos testes que chamam este método
        sem conta, mantendo o comportamento de sempre). Achado do dono
        2026-08-31: preço de WIN@/WDO@ vem em PONTOS, não R$ -- sem a
        ramificação, 1 contrato virava um nocional de ~R$180 mil no card. É o
        número que o painel mostra como valor principal do card, com a
        CONTAGEM (`ordens_compra`/`ordens_venda`) virando texto secundário
        (pedido do dono, 2026-08-24: "deve aparecer os valores, e as
        quantidades abaixo"). Mesma população da contagem (armadas, não
        preenchidas), pra o número grande e o texto pequeno descreverem a
        mesma coisa.

        Reancoragem da MESMA rodada (`numero_ordem` repetido, o "(substitui)"
        do diário -- ver a docstring de `_on_limit_placed`) NÃO conta como
        ordem nova aqui (queixa do dono, 2026-08-27: o diário só tinha
        chegado em "#02" e o card já mostrava 4 ordens armadas, somando o
        nocional de TRÊS preços que a própria rodada já tinha abandonado).
        `numero_ordem` ausente (payload antigo, ou eventos sintéticos de
        teste sem o campo) preserva o comportamento de sempre -- cada linha
        conta como rodada própria, via uma chave de posição que nunca se
        repete."""
        contagem = {lado: {"armada": 0, "preenchida": 0, "cancelada": 0} for lado in ("long", "short")}
        valor_rodada = {"long": {}, "short": {}}
        for i, o in enumerate(ordens_hoje):
            lado = o["side"]
            if lado not in contagem:
                continue
            kind = o["kind"]
            if kind != "armada":
                contagem[lado][kind] += 1
                continue
            chave = o.get("numero_ordem")
            if chave is None:
                chave = ("sem-numero", i)
            if chave not in valor_rodada[lado]:
                contagem[lado]["armada"] += 1
            if o.get("quantity") is not None and o.get("price") is not None:
                # Última reancoragem VENCE (mesma rodada, preço novo) -- não
                # soma com a que ela substituiu.
                valor_rodada[lado][chave] = (
                    margin_per_contract_brl * o["quantity"] if margin_per_contract_brl is not None
                    else o["quantity"] * o["price"]
                )

        resultado = {
            "ordens_compra": contagem["long"]["armada"], "ordens_venda": contagem["short"]["armada"],
            "valor_ordens_compra": round(sum(valor_rodada["long"].values()), 2),
            "valor_ordens_venda": round(sum(valor_rodada["short"].values()), 2),
        }
        for lado, chave in (("long", "preenchida_compra_pct"), ("short", "preenchida_venda_pct")):
            desfechos = contagem[lado]["preenchida"] + contagem[lado]["cancelada"]
            resultado[chave] = (round(100 * contagem[lado]["preenchida"] / desfechos)
                                if desfechos else None)
        return resultado

    # ---------- log + alerta (mesma regra do lado diario) -----------------

    def _vigia_leitura_do_feed(self, conn, account) -> None:
        """Grava no diario quando o feed NAO CONSEGUE LER o terminal, e quando
        volta a conseguir. Nao decide nada — so' tira o silencio.

        Por que existe (2026-09-08, item 5.17 do `LICOES_DE_PRODUCAO.md`): o
        terminal parou de entregar tick NOVO de WDO@ por 44,8 minutos e
        `closed_bars_since` devolveu lista vazia em 538 passos seguidos, sem
        UMA linha em lugar nenhum. Lista vazia e' o caso normal de um papel
        parado, entao o proprio contrato do feed apagava o sintoma; a falha de
        LEITURA, que e' outra coisa, agora viaja por fora
        (`MT5TickFeed.falha_de_leitura`, ver `live/feed_health.py`).

        Uma linha por TRANSICAO, nunca uma por passo: a 5s por passo, um
        buraco de 45 min viraria 538 linhas iguais e o diario do dono ficaria
        ilegivel justamente no pregao que ele mais precisa ler. A contagem de
        passos entra na mensagem de recuperacao, que e' onde ela informa
        quanto tempo o robo ficou cego.

        Isto NAO e' o portao que impede a ordem velha — esse e'
        `MAX_ATRASO_PARA_ORDEM_SEGUNDOS`, e ele continua sendo a unica
        protecao. Aqui so' se registra, porque a causa do congelamento de
        2026-09-08 segue desconhecida e a proxima vez precisa deixar rastro.
        """
        falha = getattr(self.bar_feed, "falha_de_leitura", None)
        if falha:
            self._falhas_de_leitura_seguidas += 1
            if self._falhas_de_leitura_seguidas == 1:
                self._log(conn, account.id, "error",
                          f"feed nao conseguiu LER o terminal ({self.strategy.symbol}): {falha}"
                          " -- nao e' 'sem negocio novo', e' leitura falhada")
            return
        if self._falhas_de_leitura_seguidas:
            self._log(conn, account.id, "info",
                      f"feed voltou a ler o terminal ({self.strategy.symbol}) apos "
                      f"{self._falhas_de_leitura_seguidas} passo(s) de falha")
            self._falhas_de_leitura_seguidas = 0

    def _aplicar_piso_de_relogio(self, conn, account: AccountState, session: date,
                                 now: datetime) -> Optional[StepReport]:
        """PISO DE RELOGIO DE PAREDE (2026-09-15) -- achata a sessao mesmo
        que NENHUMA barra tenha chegado depois do corte de flatten.

        POR QUE ISTO EXISTE. Ate aqui a UNICA protecao contra posicao
        overnight era o bloco (2) de `IntradaySessionMachine.on_closed_bar`,
        que so' dispara quando uma BARRA chega com horario >= o corte. Um
        feed que para de entregar barra apaga esse unico caminho -- medido
        de verdade em 2026-09-14: `copa_win` em sombra (conta 545) parou de
        receber barra as 10:31 BRT com 1 WIN@ SHORT aberto; o corte das
        18:20 nunca teve barra para disparar, e o ledger da sombra ficou
        R$138,50 OTIMISTA (posicao que o backtest do mesmo dia fecha a
        187.390 continuou "aberta" ate o dia seguinte). Em 2026-09-15 a
        ULTIMA barra normal do dia (feed saudavel) chegou 32 minutos ANTES
        do corte -- nao ha piso hoje nem no caso saudavel.

        Chamado em TODO passo de `run_once`, com ou sem barra nova -- e' o
        ponto inteiro: amarrar isto a `barras` nao-vazio reproduziria
        exatamente o buraco que motivou a tarefa (o feed que morreu nunca
        entrega a barra que faria o gatilho por barra disparar).

        A DECISAO (se deve achatar agora, com que preco) mora inteira em
        `IntradaySessionMachine.force_flatten_by_wall_clock` -- `live/` nao
        decide nada (AGENTS.md), so' fornece o relogio (`now`, tz-aware
        UTC) e aplica os eventos que a maquina devolver, exatamente como
        `_consume`/`_handle_gap` ja fazem para os outros gatilhos. Devolve
        `None` quando a maquina nao achou motivo para achatar (cedo demais,
        sessao ja achatada, ou sessao nem comecou) -- o caminho comum, a
        cada passo, no pregao inteiro."""
        now_ts = pd.Timestamp(now)
        if now_ts.tzinfo is None:
            now_ts = now_ts.tz_localize("UTC")
        try:
            eventos = self.machine.force_flatten_by_wall_clock(now_ts)
        except BrokerExecutionError as erro:
            # MEDIO 7, mesma defesa em profundidade que `_handle_gap` aplica
            # ao MESMO `force_flatten` (`IntradaySessionMachine.
            # force_flatten` -- ver a docstring dela): journaliza AGORA
            # qualquer evento que ja tenha sido confirmado de verdade na
            # corretora antes da excecao, para uma excecao DEPOIS nao apagar
            # um fechamento que ja moveu dinheiro real. `bar` e' so'
            # repassado adiante (nao usado por `_on_closed`), entao um
            # preco de referencia 0.0 aqui e' inofensivo.
            self._aplica_eventos_parciais_antes_de_falhar(
                conn, account, erro, Bar(ts=now_ts, open=0.0, high=0.0, low=0.0, close=0.0, volume=0.0))
            # So' `FECHAMENTO_RECUSADO`/`AGUARDANDO_PROTECAO` sao esperados
            # (a corretora ainda nao confirmou, ou recusou e o robo tenta de
            # novo no proximo passo); qualquer outro `kind` e' divergencia
            # de dado e precisa propagar (mesmo tratamento que `_handle_gap`/
            # `_tenta_zerar_por_freio_duro` dao a `force_flatten`).
            if erro.kind not in self._KINDS_QUE_REAVALIAM:
                raise
            self._registra_espera_ou_falha(conn, account, session, erro)
            return None
        if not eventos:
            return None
        # So' chega aqui na PRIMEIRA vez que o piso dispara nesta sessao
        # (`force_flatten_by_wall_clock` e' idempotente por `self.flattened`
        # -- ver a docstring dela): o log abaixo e' exatamente 1 linha por
        # pregao, nunca 1 por passo.
        corte = self.machine.session_end_time_for(now_ts)
        corte_dt = datetime.combine(now_ts.date(), corte, tzinfo=timezone.utc)
        minutos_apos_corte = round((now_ts.to_pydatetime() - corte_dt).total_seconds() / 60.0, 1)
        feed_vivo = not bool(getattr(self.bar_feed, "falha_de_leitura", None))
        preco_ref = next(
            (evento.trade.exit_price for evento in eventos if isinstance(evento, PositionClosed)),
            0.0,
        )
        bar_sintetica = Bar(ts=now_ts, open=preco_ref, high=preco_ref, low=preco_ref,
                            close=preco_ref, volume=0.0)
        for evento in eventos:
            self._apply(conn, account, evento, bar_sintetica)
        # CHECKPOINT (MEDIO 7, mesmo motivo de `_handle_gap`/`_consume`):
        # torna duravel AGORA o que acabou de se mover de verdade na
        # corretora, antes de qualquer coisa depois deste ponto poder
        # levantar e o rollback apagar o que ja e' fato consumado.
        self._checkpoint(conn, account)
        self._drena_orfas_de_saida(conn, account, now_ts)
        self._log(conn, account.id, "error",
                  f"PISO DE RELOGIO DE PAREDE: achatou {self.strategy.symbol} "
                  f"{minutos_apos_corte:.1f} min apos o corte SEM nenhuma barra ter "
                  f"chegado (feed {'vivo' if feed_vivo else 'MORTO'}) -- preco de "
                  f"referencia = ultimo close conhecido",
                  {"sessao": session.isoformat(), "minutos_apos_corte": minutos_apos_corte,
                   "feed_vivo": feed_vivo, "eventos": len(eventos),
                   "preco_referencia": preco_ref})
        return StepReport("daytrade_piso_relogio", session,
                          detail={"minutos_apos_corte": minutos_apos_corte,
                                  "feed_vivo": feed_vivo})

    def _log(self, conn, account_id, level: str, message: str, payload: Optional[dict] = None) -> None:
        store.log_event(conn, account_id, level, "daytrade", message, payload)
        self.notifier.notify(level, "daytrade", message, payload)

    def _declara_fidelidade_de_execucao(self, conn, account: AccountState) -> None:
        """Declara, uma vez por pregao, QUAL premissa de preenchimento este
        robo esta usando ao vivo -- e grita quando ela nao foi calibrada.

        POR QUE ISTO EXISTE (2026-09-11). A tabela padrao do backtest carimba
        a premissa de fila em toda linha (`fila 438/489`, `fila 0/0`, `fila
        NAO CALIBRADA`) desde 2026-09-09, justamente porque uma linha sem
        carimbo e' indistinguivel de uma linha que ninguem sabe se esta certa.
        O caminho AO VIVO nao tinha nada disso: `src/live/` nao mencionava
        fidelidade em lugar nenhum, e a sombra rodava com `queue_ahead_qty=0`
        / `exit_queue_ahead_qty=0` -- "toda ordem-limite minha preenche quando
        o preco toca o nivel" -- sem dizer a ninguem.

        O simbolo que expoe isso hoje e' o WIN@: `backtest.intraday.
        fidelidade.FIDELIDADE` so' tem WDO@ (calibrado contra extrato real,
        Kaplan-Meier, 438/489), entao todo robo de WIN@ opera com fila ZERO e
        o dono nao tinha como saber ao ler o diario. E o custo de nao saber ja
        foi medido em outro simbolo: com fila zero o motor previa +R$3,82 por
        operacao num pregao do WDO F1 que deu -R$3,00 -- errava o SINAL.

        Nivel `warn` quando nao ha calibracao, `info` quando ha. Nao impede
        de operar: e' declaracao, nao portao. A decisao de rodar sem
        calibracao e' do dono, e ela continua sendo dele -- o que muda e' que
        agora ela e' TOMADA, e nao herdada de um default silencioso.

        Uma vez por pregao (roda dentro de `_start_session`), nunca por barra:
        aviso que repete a cada 5 segundos vira ruido, e ruido nao e' aviso."""
        cfg = self.config
        calibrada = bool(getattr(cfg.costs, "fidelidade_calibrada", False))
        fila_ent = float(getattr(cfg, "queue_ahead_qty", 0.0) or 0.0)
        fila_sai = float(getattr(cfg, "exit_queue_ahead_qty", 0.0) or 0.0)
        payload = {
            "symbol": self.strategy.symbol,
            "fidelidade_calibrada": calibrada,
            "queue_ahead_qty": fila_ent,
            "exit_queue_ahead_qty": fila_sai,
        }
        if calibrada:
            self._log(
                conn, account.id, "info",
                f"fila de execucao calibrada: entrada {fila_ent:.0f} / "
                f"saida {fila_sai:.0f} contratos",
                payload,
            )
            return
        self._log(
            conn, account.id, "warn",
            f"fila de execucao NAO CALIBRADA para {self.strategy.symbol} -- "
            "o motor assume que toda ordem-limite minha preenche quando o "
            "preco toca o nivel. Resultado desta sessao e' OBSERVACAO, nao "
            "previsao validada",
            payload,
        )

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
        # `LivePosition.unit_value_brl` nao e' persistido (`journal/` nao pode
        # saber o que e' futuro -- regra de camada, ver AGENTS.md): re-carimba
        # aqui, a CADA carga, com o mesmo valor que `_on_opened` teria gravado.
        # Sem isto, uma posicao de futuro sobrevivendo a um restart do
        # processo (`live_positions` no banco, `unit_value_brl` sempre `None`
        # ao voltar) reintroduz o bug de 2026-08-31 (preco em PONTOS lido como
        # R$) so' pro painel, ate' a proxima entrada regravar a posicao.
        margem = self.machine.config.margin_per_contract_brl
        for pos in account.positions.values():
            pos.unit_value_brl = margem
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
            # Niveis pretendidos, nao so' o preco de entrada (2026-09-03,
            # pedido do dono): uma ordem-limite pode ficar parada sem
            # preencher -- o dono quer poder posicionar a MERCADO por conta
            # propria nesse caso, e pra isso precisa ver stop/alvo no painel,
            # nao so' vasculhar o diario atras da linha que armou a ordem.
            "stop": order.initial_stop,
            "alvo": order.initial_target,
            # Uma ordem REAL por filho que ainda falta preencher (ver
            # `IntradaySessionMachine.resting_children`) -- e' o "y" do "x/y"
            # no cabecalho do cartao. Ordem nao dividida = 1.
            "ordens": len(filhos),
            # Em ACOES/CONTRATOS, nao em lotes -- mesma unidade de
            # `Order.quantity` (quem quer lotes divide por `default_quantity`).
            "quantidade": sum(filhos),
            # Ticket(s) DE VERDADE da corretora (2026-08-27, pedido do dono:
            # antes so' existia o numero de rodada `#NN`, que o dono confundiu
            # com "nao da' pra saber o ticket" -- da', `Order.broker_ref` ja'
            # vinha sendo gravado desde a Fase 2, so' nunca tinha chegado ao
            # painel). `None` em modo sombra (nunca manda ordem pra corretora,
            # entao `pending_entry_refs` fica sempre vazio) -- o painel decide
            # se mostra "ticket" ou nao a partir disto, nao de `execution_mode`.
            "tickets": list(self._snapshot.pending_entry_refs or []) or None,
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

    def _checkpoint(self, conn, account: AccountState) -> None:
        """Torna DURAVEL, AGORA, tudo que este PASSO ja escreveu no diario --
        sem esperar `run_once` terminar (MEDIO 7, auditoria adversarial
        2026-08-28: `db/live.sqlite:369-380` faz `run_once` inteiro rodar
        numa UNICA transacao, e QUALQUER excecao depois de um efeito
        colateral REAL confirmado -- ticket recebido em `place_limit`/
        `place_pending`, fill confirmado, protecao registrada -- desfazia
        (`rollback()`) o log/`Intent`/`Order`/`Fill`/`live_positions` que
        descreviam exatamente ISSO, mesmo com o dinheiro ja tendo se movido
        de verdade segundos antes na mesma chamada).

        Chamado logo apos cada ponto do arquivo onde a corretora ja
        CONFIRMOU algo (uma barra inteira consumida em `_consume`, a
        protecao SL/TP registrada em `_ensure_protecao`) -- nunca no MEIO de
        um desses efeitos, que teria de ser um commit dentro de
        `intraday_execution.py`, camada que nao tem (e nao deve ganhar,
        regra 1 do AGENTS.md) conexao de banco nenhuma.

        Por que `conn.commit()` NA PROPRIA conexao do passo, e nao uma
        segunda conexao ou um arquivo lateral: `db/live.sqlite` esta em WAL
        com `busy_timeout=5000` (ver `live_store._connect`) -- isso libera
        leitor+escritor concorrentes, NUNCA dois escritores. Uma segunda
        conexao tentando escrever aqui ficaria 5s bloqueada contra a
        transacao externa de `run_once` e entao levantaria "database is
        locked" -- dentro do caminho que acabou de mandar ordem real, ou
        seja, trocando um problema por um pior. O SQLite permite comitar no
        meio de uma conexao e continuar escrevendo numa transacao nova
        implicita -- e' exatamente a semantica que falta aqui: o que ja e'
        fato consumado na corretora fica gravado; uma excecao DEPOIS deste
        ponto desfaz so' o que vier depois.

        Chama `self._persist` primeiro (nunca so' `conn.commit()` cru): o
        ponto inteiro e' `pending_entry_refs`/`last_bar_ts`/o estado da
        MAQUINA sobreviverem no snapshot tambem -- e' o que um restart le em
        `_restore`. Comitar sem persistir deixaria o `Order`/`Fill` gravados
        mas o ticket pendente fora do `policy_state`, ainda invisivel para
        o processo que reiniciar."""
        self._persist(conn, account)
        conn.commit()

    def _sincroniza_espelho_da_posicao(self, conn, account: AccountState) -> None:
        """Copia para `live_positions` o que a MAQUINA ja mudou na posicao
        aberta durante este lote de barras -- `bars_held` e `current_stop`.

        Por que existe (achado 2026-09-09). `live_positions` e' o ESPELHO da
        posicao que o painel le (coluna "Barras" e coluna "Stop" de
        `partials/operacao_slot_live.html`, via `status()["posicoes"]`), mas
        ate' aqui ele so' era escrito em TRES momentos -- abertura
        (`_on_opened`, com `bars_held=0` fixo), fatia ADICIONAL de entrada
        (`_on_opened_top_up`) e fatia PARCIAL de saida
        (`_on_closed_partial`). Uma posicao simples (sem top-up e sem saida
        fatiada) nunca passa por nenhum dos dois ultimos, entao o espelho
        ficava congelado em `bars_held=0` pela vida inteira dela: no
        `dt-wdo_grid_reload_maker-wdo@-shadow` de 2026-09-09 a maquina
        contava 6.143 barras (negocios, `feed_kind="tick"`) e o painel
        mostrava 0. Mesmo problema no stop: `AdjustStop` move
        `pos.current_stop` na maquina (`machine.on_closed_bar`, secao de
        acoes) e o dono continuaria vendo na tela o stop da ENTRADA -- que
        e' informacao errada sobre risco, nao so' cosmetica.

        Uma escrita por LOTE de barras, nao por barra: num robo de tick sao
        ~4 barras por segundo, e o espelho e' TELA (ninguem decide nada com
        ele -- quem decide le `self.machine`, e quem sobrevive a um restart
        e' o snapshot em `policy_state`, ver `_persist`). Nao chama
        `_checkpoint`: o `conn.commit()` do fim do passo ja torna isto
        duravel, e comitar aqui nao protege efeito real nenhum (nao ha
        nenhum -- e' UPDATE de espelho).

        No-op quando nao ha posicao na maquina, quando o espelho ainda nao
        existe (a posicao abriu e fechou dentro do mesmo lote), e quando
        nada mudou."""
        pos_maquina = self.machine.position
        if pos_maquina is None:
            return
        espelho = account.positions.get(self.strategy.symbol)
        if espelho is None:
            return
        if (espelho.bars_held == pos_maquina.bars_held
                and espelho.current_stop == pos_maquina.current_stop):
            return
        espelho.bars_held = pos_maquina.bars_held
        espelho.current_stop = pos_maquina.current_stop
        store.upsert_position(conn, account.id, espelho)

    @staticmethod
    def _impedimento_de_hoje(account: AccountState, session: date) -> Optional[str]:
        """O motivo gravado em `policy_state["impedimento"]`, se for do
        pregao `session` -- senao `None`. Ver `_gravar_impedimento`."""
        gravado = (account.policy_state or {}).get("impedimento") or {}
        if gravado.get("pregao") != session.isoformat():
            return None
        return gravado.get("motivo") or None

    def _gravar_impedimento(self, conn, account: AccountState,
                           motivo: Optional[str], pregao: date) -> bool:
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
        reescrever a mesma linha o pregao inteiro so' castiga o disco.
        Devolve `True` quando de fato MUDOU -- e' o que permite a quem chama
        registrar o evento no diario UMA vez em vez de a cada 5 segundos."""
        estado = dict(account.policy_state or {})
        atual = estado.get("impedimento")
        novo = {"motivo": motivo, "pregao": pregao.isoformat()} if motivo else None
        if atual == novo:
            return False
        if novo is None:
            estado.pop("impedimento", None)
        else:
            estado["impedimento"] = novo
        account.policy_state = estado
        store.save_account(conn, account)
        return True

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

    def _consome(self, nome_do_hook: str) -> bool:
        """`True` so' se a ESTRATEGIA (nao a base) sobrescreve o hook
        `nome_do_hook` -- os tres hooks de seed (`seed_volume_window`/
        `seed_daily_volatility`/`seed_typical_trade_size`) sao NO-OP PURO em
        `IntradayStrategy` (so' docstring, sem corpo -- ver `strategy.
        daytrade.base`), entao alimentar um hook que ninguem sobrescreveu e'
        indistinguivel, pra' quem observa de fora, de nunca te-lo chamado.

        Existe pra' nao pagar a busca ao feed de um historico que vai ser
        jogado fora. Achado de 2026-09-04 (item 5.9 do LICOES_DE_PRODUCAO.md):
        `WdoGridReloadMaker`/`CopaWin` nao sobrescrevem NENHUM dos tres, e
        `_start_session` buscava as mesmas sessoes assim mesmo -- 31
        chamadas de `session_bars_until` por passo, ~14s cada contra o feed
        de TICK (~140.000 "barras" degeneradas por sessao de WDO), ~430s
        so' alimentando metodos vazios. `Gremah`, que sobrescreve os tres e
        le M1 (barato), continua recebendo tudo igual.

        Compara pela FUNCAO na CLASSE, nunca por `hasattr` ou por chamar e
        comparar o resultado: toda estrategia TEM o atributo (herdado da
        base), o que importa e' se foi SOBRESCRITO."""
        return (getattr(type(self.strategy), nome_do_hook)
                is not getattr(IntradayStrategy, nome_do_hook))

    def _seed_volume_window(self, session: date) -> None:
        """Busca a CAUDA do pregao anterior e repassa para
        `IntradayStrategy.seed_volume_window` -- so' um robo com teto de
        posicao por volume rolante (`Gremah`/`GremahTick`, ver
        `strategy.daytrade.base.RollingVolumeWindow`) usa isto; os outros
        NEM CHEGAM a disparar a busca (ver `_consome`, item 5.9 do
        LICOES_DE_PRODUCAO.md).

        Chamado a CADA `_start_session` (inclusive num restart no meio do
        pregao, mesmo espirito do warm start) -- refazer a busca e' uma
        chamada extra ao feed, nao um erro: `session_bars_until` nunca
        levanta excecao (lista vazia se o terminal falhar, ver
        `MT5BarFeed`/`MT5TickFeed`), entao o pior caso e' o robo operar sem
        cauda, igual a um pregao sem historico anterior disponivel."""
        if not self._consome("seed_volume_window"):
            return
        anterior = clock.previous_session(session)
        cauda = self.bar_feed.session_bars_until(anterior, _FIM_DE_PREGAO_QUALQUER)
        if cauda:
            corte = cauda[-1].ts - pd.Timedelta(minutes=_CAUDA_VOLUME_MINUTOS)
            cauda = [b for b in cauda if b.ts > corte]
        self.strategy.seed_volume_window(cauda)

    def _seed_daily_aggregates(self, session: date) -> None:
        """Busca as `_CAUDA_VOL_DIAS` sessoes ANTERIORES e repassa os dois
        agregados diarios que dependem dela -- `barra_diaria` (para
        `IntradayStrategy.seed_daily_volatility`, so' consultado por robo
        com alvo dimensionado por volatilidade, `strategy.daytrade.base.
        JanelaVolatilidadeDiaria`) e `mediana_negocio_diario` (para
        `seed_typical_trade_size`, so' consultado pelo teto de CAPACIDADE de
        caixa, `JanelaNegocioTipicoDiaria`). Os outros robos NEM CHEGAM a
        disparar a busca (ver `_consome`).

        Duas correcoes de 2026-09-04 (item 5.9 do LICOES_DE_PRODUCAO.md),
        as duas preservando o QUE cada hook recebe (nunca a ORDEM nem o
        CONTEUDO -- so' quando/quantas vezes o feed e' consultado):

        1. **Nao busca o que a estrategia nao consome.** Se NENHUM dos dois
           hooks foi sobrescrito (`WdoGridReloadMaker`/`CopaWin`), o laco
           inteiro e' pulado -- 15 buscas que alimentavam metodos vazios
           somem. Se so' um dos dois for consumido, o laco roda (a barra
           ja' esta em mao mesmo assim) mas so' chama o hook consumido.
        2. **Uma so' busca por sessao, nao duas.** Antes, dois lacos
           separados perguntavam as MESMAS `_CAUDA_VOL_DIAS` sessoes ao
           feed -- um pra' `barra_diaria`, outro pra' `mediana_negocio_
           diario` -- 30 chamadas para dois numeros vindos das MESMAS
           barras. As duas metricas NAO sao a mesma coisa em resolucao
           diferente (`mediana_negocio_diario` e' mediana do volume de
           CADA EVENTO -- tamanho de negocio em tick, volume por minuto em
           M1 -- enquanto `barra_diaria` agrega OHLCV inteiro), entao os
           dois continuam calculados separadamente; so' a BUSCA e' unica.

        Para `Gremah` (feed M1, barato) isto ja' bastava. Para o robo do
        incidente (feed de TICK, ~14s/sessao, ~140.000 "barras" por sessao
        de WDO) a correcao 1 e' quem importa: sem hook sobrescrito, o custo
        cai a zero, nao a metade.

        Chamado a CADA `_start_session`, mesmo espirito de
        `_seed_volume_window` -- `session_bars_until` nunca levanta
        excecao (lista vazia se o terminal falhar), entao o pior caso e' o
        robo operar sem a janela, igual a um pregao sem historico anterior
        disponivel. Ordem devolvida: mais antiga primeiro, igual
        `backtest.intraday.engine`."""
        usa_volatilidade = self._consome("seed_daily_volatility")
        usa_negocio_tipico = self._consome("seed_typical_trade_size")
        if not (usa_volatilidade or usa_negocio_tipico):
            return
        diarias: list[Bar] = []
        medianas: list[float] = []
        dia = session
        for _ in range(_CAUDA_VOL_DIAS):
            dia = clock.previous_session(dia)
            bars_do_dia = self.bar_feed.session_bars_until(dia, _FIM_DE_PREGAO_QUALQUER)
            if usa_volatilidade:
                diaria = barra_diaria(bars_do_dia)
                if diaria is not None:
                    diarias.append(diaria)
            if usa_negocio_tipico:
                mediana = mediana_negocio_diario(bars_do_dia)
                if mediana is not None:
                    medianas.append(mediana)
        diarias.reverse()
        medianas.reverse()
        if usa_volatilidade:
            self.strategy.seed_daily_volatility(diarias)
        if usa_negocio_tipico:
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
        self._declara_fidelidade_de_execucao(conn, account)

        restaurada = self._snapshot.session == session and bool(self._snapshot.machine)
        pnl_antes, flat_antes = self.machine.session_pnl, self.machine.flattened

        self._resincroniza_capital(conn, account, session)

        # ANTES de qualquer decisao nova: o que a corretora tem pendurado
        # deste robo e ninguem esta vigiando? Aqui `machine.resting_limit` e'
        # sempre `None` (restore() nao a repoe -- ver a docstring dela), entao
        # TODA ordem-limite viva no book e' orfa por definicao, inclusive uma
        # que este processo mandou e nunca chegou a persistir. Limpar antes de
        # decidir e' o que impede o warm start de somar uma segunda ordem por
        # cima da do processo anterior.
        self._reconcilia_ordens_de_entrada(conn, account, session, pd.Timestamp(now))

        self._seed_volume_window(session)
        self._seed_daily_aggregates(session)

        modo = "cold"
        semente = 0
        if self._needs_warm_start(now):
            seed_bars = self.bar_feed.session_bars_until(session, pd.Timestamp(now))
            if seed_bars:
                # Caixa corrente ANTES do warm start (2026-09-03, achado de
                # auditoria adversarial -- LICOES_DE_PRODUCAO.md item 3.14):
                # MESMA formula que `IntradaySessionMachine.step()` usa em
                # `on_capital_update` a cada barra real (`cfg.initial_capital
                # + self.realized_pnl`, machine.py). Os dois numeros ja estao
                # corretos aqui -- `_resincroniza_capital` (linha acima) ja
                # releu o ledger, e `_restore` (chamado antes de
                # `_start_session`) ja repos `realized_pnl` do snapshot
                # persistido. Sem passar isto para `warm_start_calibration`,
                # um robo que dimensiona por caixa (`_cash_atual_brl`)
                # recalibra com o caixa ainda em 0.0 e o teto por risco
                # colapsa em silencio pro piso de 1 contrato ate a proxima
                # barra ao vivo -- a direcao do erro e' conservadora
                # (subdimensiona, nunca superdimensiona), mas acontecia
                # SEMPRE, sem nenhum log distinguindo o caso.
                cash_brl = self.config.initial_capital + self.machine.realized_pnl
                if not (cash_brl > 0):
                    # Alarme, nao silencio (LICOES item 1.6): sem caixa
                    # valido aqui o dimensionamento por risco/margem fica
                    # preso no piso deliberado de 1 contrato
                    # (`max(1, teto)`, ver
                    # `WdoGridReloadMaker._quantidade_da_entrada`) ate a
                    # proxima atualizacao de capital -- e antes desta
                    # correcao isso acontecia sempre, para qualquer robo que
                    # dimensiona pelo caixa, sem nenhum log.
                    self._log(conn, account.id, "error",
                              f"warm start: caixa corrente invalido (R$ {cash_brl:.2f}) "
                              "-- dimensionamento por risco/margem fica preso em 1 "
                              "contrato ate uma atualizacao de capital valida",
                              {"cash_brl": cash_brl,
                               "initial_capital": self.config.initial_capital,
                               "realized_pnl": self.machine.realized_pnl})
                pending = warm_start_calibration(self.strategy, session, seed_bars,
                                                 cash_brl=cash_brl)
                # Quantidade PEDIDA pelo robo, antes do teto agregado --
                # so' para o log abaixo saber se `resume_session` precisou
                # encolher/descartar (ver o comentario apos a chamada).
                qtd_pedida = (sum(pending.children(self.config.default_quantity))
                             if isinstance(pending, EnterLimit) else None)
                pending = self.machine.resume_session(session, seed_pending=pending)
                # `resume_session` planta a ordem do warm start direto em
                # `resting_limit`, SEM passar por `LimitPlaced` (nao ha barra
                # sendo consumida). Em execucao real isso a deixaria vigiada
                # aqui dentro e inexistente na corretora: o robo esperaria por
                # um fill que nunca poderia acontecer, porque ninguem chegou a
                # registrar a ordem. Registrar aqui e' o que fecha esse buraco.
                #
                # `resume_session` agora tambem CAPA a quantidade pelo teto
                # agregado (`_cap_efetivo`) antes de plantar -- 2026-09-03,
                # item 3.7/3.14 do LICOES_DE_PRODUCAO.md: sem isso, um robo
                # com dimensionamento dinamico podia pedir mais contratos do
                # que o teto comporta (caixa real, mas `_lotes_por_realocacao`
                # nao sabe de margem/futuro), a ordem ficava plantada com o
                # tamanho PEDIDO, e o fill recusava ela por INTEIRO no
                # primeiro toque -- robo inerte com ordem morta no book, pior
                # do que o subdimensionamento conservador que 3.14 veio
                # substituir. Por isso `pending` e' REATRIBUIDO ao retorno de
                # `resume_session` (pode ser a MESMA ordem, uma copia com
                # `quantity` menor, ou `None` se nem 1 unidade coubesse) --
                # tudo daqui pra baixo (log, cancelamento de refs antigas,
                # checagem de margem, envio real) usa a ordem CAPADA, nunca a
                # pedida. `self.machine.resting_limit is pending` NAO e'
                # redundante com `isinstance(pending, EnterLimit)`:
                # `resume_session` RECUSA plantar a ordem quando ja existe
                # posicao aberta (`if self.positions: return None`, ver a
                # docstring dela -- plantar por cima deixaria a ordem orfa).
                # Sem esta checagem o runtime mandava a ordem REAL para a
                # corretora assim mesmo, com a maquina explicitamente NAO
                # vigiando ela: uma entrada extra, sobre uma posicao que ja
                # existe, que ninguem esperava nem contabilizava. Identidade
                # (`is`), nao igualdade -- o que interessa e' que a maquina
                # adotou ESTE objeto.
                if qtd_pedida is not None:
                    qtd_aceita = (sum(pending.children(self.config.default_quantity))
                                 if isinstance(pending, EnterLimit) else 0)
                    if qtd_aceita != qtd_pedida:
                        # Alarme, nao silencio (LICOES item 1.6): o teto
                        # agregado encolheu ou descartou a ordem que o robo
                        # pediu -- o dono precisa ver isto no diario, nao so'
                        # inferir pelo tamanho da ordem em pe.
                        #
                        # Mas `resume_session` devolve `None` por DOIS motivos
                        # diferentes, e atribuir os dois ao teto seria alarme
                        # com a causa errada -- mesma distincao que
                        # `MargemTravada` vs `_recusa_por_margem` faz mais
                        # abaixo. Com posicao aberta ela RECUSA plantar de
                        # proposito (plantar por cima deixaria a ordem orfa,
                        # ver a docstring dela): isso e' o desenho
                        # funcionando, nao um teto estourado, e um restart no
                        # meio do pregao SEGURANDO posicao e' justamente o
                        # cenario comum -- logar `error` "teto capou" ali
                        # encheria o diario de alarme falso no pior momento
                        # pra' o dono nao confiar no diario.
                        if self.machine.positions:
                            self._log(conn, account.id, "info",
                                      "warm start: ordem nao plantada porque ja existe "
                                      "posicao aberta (o robo re-arma pelo criterio dele "
                                      "depois de fechar) -- o teto agregado nao foi o motivo",
                                      {"qtd_pedida": qtd_pedida, "qtd_aceita": qtd_aceita,
                                       "motivo": "posicao_aberta"})
                        else:
                            self._log(conn, account.id, "error" if qtd_aceita == 0 else "warn",
                                      f"warm start: teto agregado capou a ordem de "
                                      f"{qtd_pedida} para {qtd_aceita} contrato(s)"
                                      + ("" if qtd_aceita else " -- nenhuma ordem plantada"),
                                      {"qtd_pedida": qtd_pedida, "qtd_aceita": qtd_aceita,
                                       "motivo": "teto_agregado"})
                if (self.executor is not None and isinstance(pending, EnterLimit)
                        and self.machine.resting_limit is pending):
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
                    # Mesmo portao de margem do envio por barra: o warm start
                    # tambem manda ordem REAL, e um restart nao e' motivo pra
                    # ele pular a conferencia que a barra faz.
                    #
                    # Trava de margem ENTRE PROCESSOS (2026-09-03, item 3.13
                    # do LICOES_DE_PRODUCAO.md) -- MESMO padrao aplicado em
                    # `_on_limit_placed` (ver a docstring dele: trava de
                    # ARQUIVO do SO porque cada slot e' um PROCESSO separado,
                    # timeout curto para nao prender um slot saudavel atras
                    # de um vizinho anormal). A secao critica (consultar
                    # margem + mandar ESTA ordem) fica inteira dentro de
                    # `acquire_margin_gate`, sem I/O de diario dentro -- o
                    # resultado (jornal, `pending_entry_refs`) e' aplicado so'
                    # DEPOIS de soltar a trava. Este e' o SEGUNDO ponto de
                    # envio do runtime (o primeiro, `_on_limit_placed`, e' a
                    # decisao por barra); ficou de fora da correcao original
                    # do item 3.13 so' porque esta regiao estava em edicao
                    # concorrente naquele momento -- mesma lacuna, mesmo
                    # fechamento, sem inventar padrao novo.
                    sem_margem: Optional[str] = None
                    enviadas = None
                    erro_envio: Optional[BrokerExecutionError] = None
                    erro_trava: Optional[MargemTravada] = None
                    try:
                        with acquire_margin_gate():
                            sem_margem = self._check_margem_da_conta(
                                pending.side,
                                sum(pending.children(self.config.default_quantity)),
                                pending.limit_price)
                            if sem_margem is None:
                                # Mesma recusa possivel do envio por barra,
                                # mesmo tratamento (ver `_recusa_de_envio`):
                                # `resume_session` acabou de plantar a ordem
                                # em `resting_limit`, e uma recusa aqui a
                                # deixaria vigiada sem existir no book.
                                try:
                                    enviadas = self.executor.place_limit(
                                        side=pending.side, limit_price=pending.limit_price,
                                        quantities=pending.children(self.config.default_quantity),
                                        ts=seed_bars[-1].ts,
                                        # Protecao ATOMICA -- ver `place_limit`.
                                        stop=pending.initial_stop,
                                        target=self._alvo_atomico(pending),
                                    )
                                except BrokerExecutionError as erro:
                                    erro_envio = erro
                    except MargemTravada as erro:
                        erro_trava = erro
                    if erro_trava is not None:
                        # Nao consegui verificar a margem com seguranca (outro
                        # processo segurava a trava alem do timeout) --
                        # tratado como consulta que FALHOU (item 1.6 do
                        # LICOES_DE_PRODUCAO.md: "nao sei" nunca autoriza),
                        # nunca como recusa por margem insuficiente de
                        # verdade (por isso NAO passa por `_recusa_por_margem`,
                        # que e' especifica desse outro caso). Mesmo desfecho
                        # de uma recusa da corretora: a maquina larga a
                        # `resting_limit` e o robo re-arma pelo proprio
                        # criterio no proximo ciclo.
                        self._recusa_de_envio(
                            conn, account, session, self._snapshot.trade_num,
                            BrokerExecutionError(
                                f"nao enviei: trava de margem entre processos ocupada -- {erro_trava}",
                                orphan_refs=[]))
                    elif sem_margem is not None:
                        # Mesmo desfecho de uma recusa da corretora: a maquina
                        # larga a `resting_limit` e o pregao segue normalmente
                        # (o robo re-arma pelo criterio dele quando a conta
                        # comportar). Nao ha ordem no book pra limpar.
                        self._recusa_por_margem(conn, account, session,
                                                self._snapshot.trade_num, sem_margem)
                    elif erro_envio is not None:
                        self._recusa_de_envio(conn, account, session,
                                              self._snapshot.trade_num, erro_envio)
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
                # Preco + stop/alvo na linha (2026-09-03, pedido do dono):
                # antes so' dizia "ordem em pe" sem nivel nenhum -- pra' saber
                # onde a ordem estava o dono tinha de ir atras do dado bruto.
                # Mesmo motivo do `_bracket_txt` em `_on_limit_placed`: e'
                # exatamente aqui, com a ordem plantada FORA do caminho normal
                # (ver a docstring desta funcao), que ela mais fica parada sem
                # preencher, e o dono pode preferir posicionar a mercado
                # sozinho se souber os precos.
                nivel_txt = (f" @ {pending.limit_price:.4f}"
                             f"{self._bracket_txt(pending.initial_stop, pending.initial_target)}"
                             if pending else "")
                self._log(conn, account.id, "info",
                          # "ordem em pe"/"sem ordem" em vez de "posicionada":
                          # depois da reescrita de 2026-08-25 quem POSICIONA e'
                          # a linha "LIMITE ...", e usar a palavra velha aqui
                          # faria parecer que o warm start armou uma ordem nova.
                          f"{session.isoformat()}: warm start, {len(seed_bars)} barra(s), "
                          f"{'ordem em pe' if pending else 'sem ordem'}{nivel_txt}",
                          {"barras": len(seed_bars), "modo": modo,
                           "limit_price": pending.limit_price if pending else None,
                           "stop": pending.initial_stop if pending else None,
                           "target": pending.initial_target if pending else None})
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

    def _fase_do_instrumento(self, now: datetime) -> SessionPhase:
        """A fase do pregao DESTE instrumento, nao a do pregao de acao.

        `clock.phase()` so' conhece o calendario de ACAO (10:00 as 17:00/
        17:55, deslocando com o horario de verao dos EUA) -- `core.
        b3_session` declara isso na propria docstring e avisa que FUTURO nao
        desloca. Enquanto este metodo nao existiu (ate' 2026-09-08) o robo de
        futuro era gateado pelo relogio da acao: ficava `idle` das 09:00 as
        10:00 e parava as 17:00, enquanto o backtest media 09:00..18:29.
        Eram 149 minutos, 26,2% do pregao, incluindo a primeira hora, que e'
        onde mora o pico de atividade do WDO@. Isso quebrava o invariante
        central do `AGENTS.md` -- `live/` nao decide nada, o backtest tem de
        descrever a producao.

        A janela vem do PERFIL do simbolo, que e' a mesma fonte que o
        backtest le'. Perfil sem `session_start_time` (toda acao) cai no
        `clock.phase()` de sempre, entao nada muda para o caminho de acao."""
        from backtest.intraday.profiles import profile_for

        try:
            perfil = profile_for(self.strategy.symbol)
        except Exception:  # noqa: BLE001 -- simbolo sem perfil: relogio de acao
            return clock.phase(now)
        abertura = getattr(perfil, "session_start_time", None)
        if abertura is None:
            return clock.phase(now)
        return clock.phase_em_janela(now, abertura, perfil.session_end_time)

    def run_once(self, now: Optional[datetime] = None) -> list[StepReport]:
        """Um passo. Seguro para chamar em loop, a qualquer hora — so age
        quando ha barra M1 nova FECHADA dentro de um pregao aberto."""
        if self.somente_leitura:
            # Runtime de painel nunca opera. Recusa aqui e nao la' na frente
            # porque ele nasce SEM ponte de execucao: deixado passar, um
            # runtime montado como "live" simularia os fills pela barra (o
            # caminho da sombra) enquanto a tela diz que ha dinheiro em jogo.
            raise RuntimeError(
                f"{self.account_name}: este IntradayLiveRuntime foi montado "
                "somente para LEITURA (painel) e nao pode dar passo de operacao "
                "-- quem opera e' o processo do supervisor (scripts/run_live.py)."
            )
        now = now or datetime.now(timezone.utc)
        fase = self._fase_do_instrumento(now)
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
                try:
                    self._restore(account, hoje)
                except RuntimeError as erro:
                    # `IntradaySessionMachine.restore` recusa reidratar uma
                    # FATIA DE SAIDA posicionada em execucao real -- o ticket
                    # dela nao sobrevive ao restart e so' a corretora sabe se
                    # a ordem ainda esta no book. A recusa esta certa (a
                    # alternativa e' mandar uma segunda saida por cima), mas
                    # ate' aqui ela subia como excecao: o supervisor imprimia
                    # no log do processo e o painel seguia verde escrito
                    # "operando", que e' exatamente a queixa de 25/08/2026
                    # que o IMPEDIMENTO existe para resolver. O robo continua
                    # parado -- so' passou a dizer por que, na tela onde o
                    # dono olha.
                    mudou = self._gravar_impedimento(
                        conn, account,
                        "fatia de saída órfã — confira a ordem-limite no MT5", hoje)
                    if mudou:
                        self._log(conn, account.id, "error", str(erro))
                    return [StepReport("daytrade_skip", hoje, phase=fase,
                                       detail={"motivo": "fatia de saida orfa",
                                               "erro": str(erro)})]
                if self._snapshot.disaster_halt:
                    # Freio duro persistido de uma sessao ANTERIOR do MESMO
                    # pregao (restart no meio do freio, gap g) -- nao faz
                    # `_start_session` (que inclui warm start, e warm start
                    # pode ARMAR ordem-limite nova): so' calibra o marcador
                    # e deixa o `_check_freio_duro` logo abaixo confirmar e
                    # tentar zerar o que sobrou.
                    self._calibrated_for = hoje
                else:
                    passos.append(self._start_session(conn, account, hoje, now))

            # So' avisa, nunca bloqueia -- ver a docstring de
            # `_check_atividade_estranha`. Roda a cada passo (nao 1x por
            # pregao como os portoes acima) porque uma ordem manual pode
            # acontecer a qualquer momento, nao so' no comeco do dia. DEPOIS
            # de `_restore` (nao antes): `_restore` troca `self._snapshot`
            # inteiro por um objeto novo -- gravar o resultado antes disso
            # seria escrito no snapshot errado, perdido no mesmo passo em
            # que foi decidido (bug real, pego pelo teste de deduplicacao).
            self._check_atividade_estranha(conn, account, hoje)

            # Protecao SL/TP + freio duro de equity/margem (gap c/e/f/g,
            # incidente 2026-08-28) -- SEMPRE, antes de qualquer barra nova
            # ser consumida: uma posicao aberta precisa estar protegida na
            # corretora e uma conta em risco de ruina nao pode abrir ordem
            # nova, mesmo que o resto do pregao esteja liberado.
            self._ensure_protecao(conn, account, hoje)
            # CHECKPOINT (MEDIO 7): se `_ensure_protecao` acabou de registrar
            # SL/TP na corretora (efeito colateral REAL), torna isso durAvel
            # AGORA -- antes de `_consume`/`_handle_gap` poderem levantar
            # `FALHA_ALTO` mais adiante neste MESMO passo e apagar, via
            # rollback, o log que descreve uma protecao que ja' esta' de pe'
            # na corretora de verdade. Ver `_checkpoint`.
            self._checkpoint(conn, account)
            # Simetrico do anterior: `_ensure_protecao` cuida da posicao que a
            # maquina CONHECE; este cuida da que ela NAO conhece e a corretora
            # tem. Sem ele ninguem perguntava a corretora "o que existe ai?"
            # a menos que a maquina ja acreditasse ter alguma coisa.
            self._check_posicao_desconhecida(conn, account, hoje)
            alarme_freio = self._check_freio_duro(conn, account, hoje)
            if alarme_freio is not None:
                self._gravar_impedimento(conn, account, f"freio duro: {alarme_freio}", hoje)
                self._persist(conn, account)
                return passos + [StepReport("daytrade_freio_duro", hoje, phase=fase,
                                            detail={"motivo": alarme_freio})]

            # Ha' quanto tempo este slot nao roda um passo. Lido ANTES de
            # carimbar o passo de agora, senao seria sempre zero.
            parado_ha = self._parado_ha_segundos(now)
            self._snapshot.last_poll_at = pd.Timestamp(now)

            barras = self.bar_feed.closed_bars_since(self._snapshot.last_bar_ts)
            self._vigia_leitura_do_feed(conn, account)
            if not barras:
                # PISO DE RELOGIO DE PAREDE (2026-09-15): sem barra nenhuma
                # este passo, o caminho por BARRA (`on_closed_bar`, bloco
                # (2)) nao tem como disparar -- e' exatamente o buraco que
                # deixou uma posicao real aberta o pregao inteiro em
                # 2026-09-14 (feed morreu as 10:31 BRT, corte das 18:20
                # nunca teve barra para achatar). Chamado AQUI, e nao so'
                # depois de `_consume`, porque este ramo pode NUNCA mais
                # sair dele pelo resto do pregao. Ver a docstring de
                # `_aplicar_piso_de_relogio`.
                passo_piso = self._aplicar_piso_de_relogio(conn, account, hoje, now)
                if passo_piso is not None:
                    passos.append(passo_piso)
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
                self._gravar_impedimento(
                    conn, account,
                    self._capital_impedimento or "caixa abaixo do mínimo do dia",
                    hoje)
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
                passos.append(self._consume(conn, account, hoje, barras, now))

            # PISO DE RELOGIO DE PAREDE, de novo -- backup para o caso mais
            # raro em que ESTA barras chegou (feed vivo), mas nenhuma delas
            # tem `ts` >= o corte, e o relogio de parede JA passou dele
            # (feed atrasado em relacao ao relogio real, sem atraso grande o
            # bastante para contar como buraco de `_handle_gap`). No caso
            # comum (feed em dia) `self.machine.flattened` ja esta' `True`
            # aqui -- ver a idempotencia na docstring de
            # `force_flatten_by_wall_clock` -- e esta chamada e' NO-OP.
            passo_piso = self._aplicar_piso_de_relogio(conn, account, hoje, now)
            if passo_piso is not None:
                passos.append(passo_piso)

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
        menor (ou zero).

        FUTURO (`self.strategy.is_futuro`) ramifica para MARGEM, nao preco
        (2026-08-28, bug real corrigido): `preco x default_quantity` e' o
        custo de COMPRAR o lote -- a conta certa so' para ACAO, onde nao ha
        alavancagem. Aplicada sem ramificar a um futuro (`default_quantity=1`
        no perfil), isso vira o valor NOCIONAL cheio de 1 contrato (~R$5.000+
        no WDO@), nao a margem (~R$150 WDO@/R$100 WIN@) que a corretora de
        fato reserva -- um robo com o caixa MINIMO REAL do instrumento
        (`strategy.daytrade.base.capital_minimo_brl`/`CAPITAL_MINIMO.md`,
        R$300 no WDO@) nunca cobriria o preco cheio e o alarme dispararia
        TODO pregao, todo dia, sem exceção. O piso dia-a-dia usa 1x a margem
        (nao `MARGIN_BUFFER_FUTUROS`, que so' se aplica na ENTRADA -- ver
        `dashboard.robot_view.capital_minimo_para` -- mesma relaxacao 2x
        entrada / 1x dia-a-dia que ja existe para acao).

        SOMBRA NUNCA E' BLOQUEADA POR CAIXA (pedido do dono, 2026-09-17): o
        piso de caixa protege dinheiro REAL de uma ordem que a corretora
        recusaria -- em sombra nao ha ordem nenhuma, e' so' um robo de teste
        medindo contra o dado real. Aplicar o mesmo piso ali nao evita
        nenhum prejuizo, so' impede o dono de rodar um teste com um caixa
        pequeno de proposito. `execution_mode="live"` continua com a regra
        inteira."""
        if self.execution_mode == "shadow":
            self._capital_checked_for = session
            self._capital_minimo_hoje = None
            self._capital_alarm = None
            self._capital_impedimento = None
            return None

        if self._capital_checked_for == session:
            return self._capital_alarm

        if getattr(self.strategy, "is_futuro", False):
            from backtest.intraday.profiles import profile_for

            margem = profile_for(self.strategy.symbol).margin_per_contract_brl
            minimo = (
                preco * self.config.default_quantity if margem is None
                else margem * self.config.default_quantity
            )
        else:
            minimo = preco * self.config.default_quantity
        self._capital_checked_for = session
        self._capital_minimo_hoje = minimo
        saldo = account.cash_for(self.execution_mode)

        if saldo >= minimo:
            self._capital_alarm = None
            self._capital_impedimento = None
            return None

        self._capital_alarm = (
            f"caixa R$ {saldo:.2f} nao cobre o minimo de R$ {minimo:.2f} "
            f"({self.strategy.symbol})"
        )
        # Texto do PAINEL (o log fica com o de cima, sem acento, como o resto
        # do arquivo). Diz o quanto FALTA e de onde sai o minimo -- "caixa
        # abaixo do minimo do dia", o texto anterior, obrigava o dono a abrir
        # o log do processo para descobrir de quanto era a diferenca. Foi a
        # queixa de 2026-09-08: PMAM3 subiu 175% em tres semanas, o piso do
        # lote passou de R$30 para R$33, e o painel so' dizia "impedido".
        self._capital_impedimento = self._texto_de_falta_de_caixa(saldo, minimo, preco)
        self._log(conn, account.id, "error",
                  f"nao vou operar: {self._capital_alarm}",
                  {"pregao": session.isoformat(), "caixa": round(saldo, 2),
                   "minimo": round(minimo, 2), "preco": preco,
                   "falta": round(minimo - saldo, 2),
                   "quantidade": self.config.default_quantity})
        return self._capital_alarm

    def _texto_de_falta_de_caixa(self, saldo: float, minimo: float,
                                 preco: float) -> str:
        """"faltam R$ 3,00 -- 100 PMAM3 a R$ 0,33 custam R$ 33,00 e o caixa
        tem R$ 30,00", em decimal BR (e' texto de tela).

        Diz a QUANTIDADE em vez de "1 lote" porque o tamanho do lote e' o que
        muda o numero, e escondê-lo atras da palavra "lote" e' o que fez o
        dono precisar abrir o log para entender de onde saia o minimo.

        Ramifica igual a `_check_capital`: em FUTURO o minimo e' margem por
        contrato, nao preco x lote, e citar o preco do contrato ali daria a
        entender que ele precisa do nocional inteiro no caixa."""
        def br(v: float) -> str:
            return f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

        sym = self.strategy.symbol
        qtd = self.config.default_quantity
        plural = qtd != 1
        if getattr(self.strategy, "is_futuro", False):
            origem = (f"{qtd} contrato{'s' if plural else ''} de {sym} "
                      f"exige{'m' if plural else ''} R$ {br(minimo)} de margem")
        else:
            origem = (f"{qtd} {sym} a R$ {br(preco)} "
                      f"custa{'m' if plural else ''} R$ {br(minimo)}")
        return (f"faltam R$ {br(minimo - saldo)} — {origem} e o caixa tem "
                f"R$ {br(saldo)}")

    def _check_atividade_estranha(self, conn, account: AccountState, session: date) -> None:
        """Ha' posicao/ordem de OUTRO `magic` neste papel agora? So' avisa
        -- nunca bloqueia o pregao nem soma esse volume ao que o robo
        controla (regra 6 do AGENTS.md: `live/` aplica regra declarada,
        nunca inventa a propria -- reagir de verdade a isso seria uma
        decisao de trading nova que nenhum backtest validou).

        So' roda em modo LIVE (`self.executor is not None` -- sombra nunca
        manda ordem pra corretora, entao nao ha "outro magic" pra' ver la).
        Loga por TRANSICAO, nao a cada passo: `_SessionSnapshot.
        atividade_estranha` guarda o ultimo resultado, e so' grava evento
        quando ele muda (nada -> algo: warn; algo -> nada: info) -- senao um
        passo a cada poucos segundos spammaria o diario inteiro enquanto a
        atividade persistir.

        Motivado pelo teste manual de 2026-08-27: comprei/vendi PMAM3 a
        mercado direto no terminal, com o robo real rodando no mesmo papel,
        e o diario nunca registrou nada -- `open_position()`/
        `pending_orders()` filtram por magic de proposito (ver as
        docstrings la), entao o robo ficava cego por completo pra' isso."""
        if self.executor is None:
            return
        ler = getattr(self.broker, "foreign_activity", None)
        if ler is None:
            return
        atual = ler(self.strategy.symbol)
        anterior = self._snapshot.atividade_estranha
        if atual == anterior:
            return
        self._snapshot.atividade_estranha = atual
        if atual is not None:
            self._log(conn, account.id, "warn",
                      f"ATIVIDADE ESTRANHA em {atual['symbol']}: "
                      f"{len(atual['itens'])} item(ns) de outro magic "
                      "(posicao/ordem que este robo nao controla)",
                      {"sessao": session.isoformat(), **atual})
        else:
            self._log(conn, account.id, "info",
                      "atividade estranha anterior nao aparece mais na corretora",
                      {"sessao": session.isoformat()})

    # ---------- protecao SL/TP na corretora (gap c/g, incidente 2026-08-28) -

    @staticmethod
    def _alvo_atomico(order) -> Optional[float]:
        """O alvo pode ser amarrado NA ORDEM (TP da corretora), ou a maquina
        tem de continuar dona dele?

        Devolve `initial_target` -- exceto quando a estrategia declarou
        `exit_split_unit`, e ai devolve `None`. Motivo, e nao e' preciosismo:
        com saida fatiada a maquina posiciona ordens-limite REAIS de
        fechamento, uma por fatia (`place_exit_limit`). Um TP da corretora no
        MESMO nivel fecharia a posicao INTEIRA ao mesmo tempo em que a limite
        de UMA fatia preenche -- e numa conta NETTING as duas somadas passam
        do tamanho da posicao e ABREM o lado contrario. Trocar uma posicao
        desprotegida por uma posicao invertida nao e' progresso.

        O STOP nao tem esse problema e vai sempre: fatia de saida so' existe
        no alvo, e um SL que feche tudo antes so' faz a maquina descobrir no
        passo seguinte que ja nao ha posicao -- caminho que `exit_market` ja
        trata. Sem `exit_split_unit` (o caso comum) o alvo tambem vai, e ai o
        TP da corretora e' ESTRITAMENTE melhor que o que existia: dispara no
        toque do nivel, que e' exatamente o que o backtest simula, em vez de
        so' no fechamento da barra M1 seguinte.

        Regra por CAMPO DECLARADO de `EnterLimit`, nunca por nome de robo --
        vale para qualquer estrategia, presente ou futura.

        Delega a `_alvo_registravel`, que e' onde a regra mora de verdade
        desde 2026-09-08: `_ensure_protecao` precisa da MESMA decisao sobre
        uma posicao ja aberta, e ate' entao ela nao a aplicava -- ver a
        docstring de la para o que isso custava."""
        return IntradayLiveRuntime._alvo_registravel(
            getattr(order, "exit_split_unit", None),
            getattr(order, "initial_target", None),
        )

    @staticmethod
    def _alvo_registravel(exit_split_unit, target) -> Optional[float]:
        """A REGRA, num lugar so': o alvo pode ficar amarrado na CORRETORA
        (TP), ou a maquina continua dona dele?

        Existe porque a regra vivia dentro de `_alvo_atomico`, que so' e'
        consultado no INSTANTE de armar a ordem. `_ensure_protecao` roda a
        cada passo sobre a posicao JA ABERTA e registrava
        `pos.current_target` incondicionalmente -- ou seja, o TP que
        `_alvo_atomico` tinha recusado de proposito entrava pela porta dos
        fundos no passo seguinte, desfazendo a protecao contra INVERSAO em
        conta NETTING que aquela recusa existe para dar (dois fechamentos do
        tamanho total: o TP da corretora fechando a posicao INTEIRA no mesmo
        nivel em que a limite de UMA fatia preenche, e a soma passa do
        tamanho da posicao e ABRE o lado contrario). Achado por auditoria em
        2026-09-08, junto com o item 1.23 de `LICOES_DE_PRODUCAO.md`, que e'
        o mesmo modo de falha pelo outro lado (protecao registrada + ordem a
        mercado por cima).

        Afeta quem declara `exit_split_unit` -- `gremah` (`dividir_entrada=
        True` por default, opera acao B3) e, desde 2026-09-08, tambem
        `wdo_grid_reload_maker` (`fatiar_saida_alvo=True` em producao, ver
        `strategy.daytrade.registry._KWARGS_PADRAO` -- troca o TP nativo
        que desliza SEMPRE por ordem-limite real no livro).

        `None` aqui NAO apaga um TP ja registrado: `_ensure_protecao` passa
        `tp_atual` junto para `set_protection`, e `MT5Broker._niveis_
        protecao` preserva o que a corretora tem (invariante 1 de la). O
        efeito e' "nao registre TP", nao "remova o TP"."""
        if exit_split_unit:
            return None
        return target

    def _ensure_protecao(self, conn, account: AccountState, session: date) -> None:
        """Garante que toda posicao aberta deste robo tem SL (e TP, quando a
        estrategia tiver alvo) REGISTRADO NA CORRETORA -- nunca so' na
        cabeca do processo.

        Motivado pelo incidente 2026-08-28 (slot `dt-wdo_grid_reload_maker-
        wdo@-live`): a posicao ficou com `sl=0.0, tp=0.0` na corretora por
        HORAS, atravessando 3 reinicios, porque o "stop" deste robo sempre
        foi logica do LOOP do processo (dispara ordem a mercado quando o
        nivel rompe) -- processo morto/reiniciado = posicao nua. Eu (o
        dono) precisei anexar SL/TP na mao pra estancar.

        Roda em TODO passo com posicao aberta -- nao so' na entrada -- de
        proposito: e' o que fecha o gap de RESTART (gap g). Um processo novo
        reidrata a posicao (`_restore`) mas o SL/TP da corretora vive na
        POSICAO, nao no processo -- confirmar de novo a cada passo e' uma
        leitura barata (`open_position`) e e' o que pega tanto o restart
        quanto qualquer outra forma da protecao ter sumido (ex.: humano
        mexendo no terminal).

        So' MODIFICA quando falta (0.0/None na corretora) ou diverge do que
        a maquina quer -- reenviar toda barra com o MESMO nivel so' gastaria
        requisicao a toa. `stop`/`target` sao SEMPRE os niveis que a MAQUINA
        ja decidiu (`_Position.current_stop`/`current_target`) -- nunca
        calculados aqui (regra 6 do AGENTS.md: `live/` nao decide).

        Numa conta NETTING so' existe UMA posicao consolidada por simbolo:
        com mais de uma `_Position` independente (sombra por lote, nunca em
        execucao real -- `self.executor is None` cobre isso, ver a docstring
        da classe) so' a primeira e' usada como referencia."""
        if self.executor is None or not self.machine.positions:
            return
        setter = getattr(self.broker, "set_protection", None)
        if setter is None:
            return
        real = self.broker.open_position(self.strategy.symbol)
        if real is None or real.get("ticket") is None:
            # Sem ticket nao da pra proteger. Nao e' um erro NOVO: se o
            # terminal estiver fora do ar ou a posicao nao bater, o resto do
            # passo (`_read_position`/`limit_fill`/`exit_market`) ja vai
            # detectar e falhar alto por conta propria.
            return
        ticket = real["ticket"]
        pos = self.machine.positions[0]
        if real.get("side") is not None and real["side"] != pos.side:
            # A corretora esta' de um lado e a maquina do outro: os niveis que
            # esta funcao mandaria sao os do lado ERRADO, e `TRADE_ACTION_SLTP`
            # e' order_send como qualquer outro -- vale a regra de que nada
            # sai enquanto os dois nao concordarem sobre lado e tamanho.
            #
            # Em 2026-09-09 isto mandou, a cada passo por ~3 minutos, o stop de
            # uma SHORT (5131,50) para uma posicao LONG com bid em 5124,00, e
            # colhia `retcode=10016` de volta. Ali a recusa da corretora salvou
            # -- mas so' porque o preco estava ABAIXO do nivel. Com o mercado
            # acima de 5131,50 o mesmo pedido seria ACEITO, e a posicao ficaria
            # com um "stop" que nao tem relacao nenhuma com a exposicao real.
            #
            # Nao alarma aqui: `_check_posicao_desconhecida` roda logo em
            # seguida NO MESMO PASSO, com o alarme especifico e o freio.
            return
        sl_atual = float(real.get("sl") or 0.0)
        tp_atual = float(real.get("tp") or 0.0)
        alvo_sl = pos.current_stop
        # MESMA regra de `_alvo_atomico` (ver `_alvo_registravel`): posicao
        # com saida FATIADA nao pode ganhar TP da corretora, senao ele fecha
        # a posicao inteira junto com a limite de uma fatia e, em NETTING,
        # inverte o lado. Antes de 2026-09-08 esta linha era
        # `alvo_tp = pos.current_target`, sem condicao nenhuma -- o TP que
        # `_alvo_atomico` recusava ao ARMAR voltava aqui no passo seguinte.
        alvo_tp = self._alvo_registravel(pos.exit_split_unit, pos.current_target)

        # Ja registrado com ESTE pedido e a corretora continua com os mesmos
        # niveis que ela mesma aceitou? Nada a fazer. Comparar o par
        # (pedido, registrado) em vez de "pedido == registrado" e' o que
        # impede o reenvio eterno quando a corretora ajusta o nivel pela
        # distancia minima dela -- ver `_protecao_registrada`.
        anterior = self._protecao_registrada.get(ticket)
        if anterior is not None:
            pedido_sl, pedido_tp, reg_sl, reg_tp = anterior
            mesmo_pedido = (pedido_sl == alvo_sl and pedido_tp == alvo_tp)
            mesmo_registro = (abs(reg_sl - sl_atual) <= 1e-6 and abs(reg_tp - tp_atual) <= 1e-6)
            if mesmo_pedido and mesmo_registro:
                self._protecao_alarmada.discard(ticket)
                return

        falta_sl = (alvo_sl is not None and abs(float(alvo_sl) - sl_atual) > 1e-6)
        falta_tp = (alvo_tp is not None and abs(float(alvo_tp) - tp_atual) > 1e-6)
        if not (falta_sl or falta_tp):
            self._protecao_alarmada.discard(ticket)
            self._protecao_registrada[ticket] = (alvo_sl, alvo_tp, sl_atual, tp_atual)
            return
        resultado = setter(self.strategy.symbol, ticket, pos.side,
                           stop=alvo_sl, target=alvo_tp,
                           # O que a corretora tem AGORA: sem isto um
                           # `target=None` mandaria `tp=0.0` e APAGARIA o alvo
                           # ja registrado, e um stop recalculado poderia
                           # afrouxar o que ja estava mais perto. Ver
                           # `MT5Broker._niveis_protecao`, invariantes 1 e 2.
                           sl_atual=sl_atual, tp_atual=tp_atual)
        if resultado.get("ok"):
            self._protecao_alarmada.discard(ticket)
            self._protecao_registrada[ticket] = (
                alvo_sl, alvo_tp,
                float(resultado.get("sl") or 0.0), float(resultado.get("tp") or 0.0),
            )
            self._log(conn, account.id, "info",
                      f"protecao registrada na corretora para {self.strategy.symbol}: "
                      f"{resultado.get('note', '')}",
                      {"sessao": session.isoformat(), "ticket": ticket,
                       "stop": alvo_sl, "target": alvo_tp})
        elif ticket not in self._protecao_alarmada:
            self._protecao_alarmada.add(ticket)
            self._log(conn, account.id, "error",
                      f"NAO CONSEGUI proteger a posicao de {self.strategy.symbol} na "
                      f"corretora (SL/TP ausente ou divergente): {resultado.get('note', '')} "
                      "-- tentando de novo a cada passo ate confirmar (ver incidente "
                      "2026-08-28: posicao ficou sem SL/TP por horas, atravessando 3 "
                      "reinicios)",
                      {"sessao": session.isoformat(), "ticket": ticket,
                       "stop": alvo_sl, "target": alvo_tp})

    def _tem_ordem_em_transito(self) -> bool:
        """Ha' alguma ordem REAL viva ou recem-preenchida que ainda explica
        uma divergencia entre o que a corretora tem e o que a maquina sabe?

        E' o filtro que separa "divergencia" de "atraso normal": entre a
        corretora preencher uma ordem-limite e a maquina rodar `limit_fill`
        na barra seguinte, a posicao existe la e nao aqui -- e isso e' o
        funcionamento correto, nao um problema. Mesma coisa do lado da saida
        (a posicao encolhe na corretora antes da maquina contabilizar) e das
        fatias de uma entrada dividida que ainda nao preencheram todas."""
        if self.executor is None:
            return False
        # `executor.pending_orders` NAO entra: ele guarda as `Order` do ultimo
        # grupo enviado e so' e' limpo por `cancel_limit` -- depois de um fill
        # normal ele continua cheio para sempre, e usa-lo aqui desligaria a
        # conferencia pelo resto do pregao. Quem de fato diz "ainda ha fill a
        # chegar" e' a maquina (`resting_limit`, zerado quando o ultimo filho
        # preenche) e os tickets que o cancelamento nao confirmou.
        return bool(
            self.machine.resting_limit is not None
            or self._snapshot.pending_entry_refs
            or self.executor.pending_exit_order is not None
            or self.executor.exit_orphan_refs
        )

    def _resincroniza_capital(self, conn, account: AccountState, session: date) -> None:
        """Repoe o capital do slot a partir do LEDGER, a cada pregao.

        `initial_capital` era lido UMA vez, na construcao do runtime, e nunca
        mais. Mas o processo `loop` roda continuo (nao reinicia todo dia) e o
        ledger e' editavel no painel a qualquer momento -- entao o dono podia
        sacar metade do caixa, corrigir o numero na tela, e o robo continuar
        dimensionando lote e teto de contratos contra o valor antigo, mais
        alto, barra a barra, ate alguem reiniciar o processo. O portao de
        inicio de pregao (`_check_capital`) ja lia o numero novo; quem
        decide QUANTO comprar, nao.

        `machine.config` junto, e nao so' `self.config`: sao objetos
        distintos depois do `replace` (dataclass frozen), e e' o da maquina
        que alimenta `on_capital_update` e `_cap_capital_atual` a cada barra.

        Segue `execution_mode` (`cash_for`) pelo mesmo motivo de
        `_check_capital`: sombra dimensiona contra `cash_sombra`, nunca
        contra o dinheiro real."""
        try:
            saldo = float(account.cash_for(self.execution_mode))
        except Exception:  # noqa: BLE001 - ledger ilegivel nunca derruba o robo
            return
        if abs(saldo - self.initial_capital) < 0.005:
            return
        antes = self.initial_capital
        self.initial_capital = saldo
        self.config = replace(self.config, initial_capital=saldo)
        self.machine.config = self.config
        # O teto de perda acompanha o capital -- a menos que o dono tenha
        # fixado um numero proprio no construtor, que nao pode ser
        # sobrescrito por um saque.
        if abs(self.perda_maxima_dia_brl
               - FRACAO_PERDA_MAXIMA_DIA * antes) < 0.005:
            self.perda_maxima_dia_brl = FRACAO_PERDA_MAXIMA_DIA * saldo
        self._log(conn, account.id, "info",
                  f"capital do slot: R$ {antes:.2f} -> R$ {saldo:.2f} "
                  "(lido do ledger no comeco do pregao)",
                  {"pregao": session.isoformat(), "antes": round(antes, 2),
                   "agora": round(saldo, 2)})

    def _check_cadencia_de_ordens(self, agora_wall) -> Optional[ExcessoDeCadencia]:
        """Envios demais numa janela de 60s de RELOGIO DE PAREDE? Devolve o
        `ExcessoDeCadencia`, ou `None` quando cabe.

        DOIS TETOS, DOIS DESFECHOS (2026-09-08) -- ver
        `COTA_ENVIOS_POR_MINUTO` e `MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO`
        para os numeros e a medicao que os escolheu:

        * `patologia=False` (cota de VAZAO estourada): recusa SO' este
          envio. O robo segue vivo, segue fechando posicao, segue lendo
          barra, e rearma pelo criterio DELE na barra seguinte. E' o mesmo
          comportamento do freio da propria estrategia
          (`reancora_min_segundos`, no maximo 6 reprecificacoes por minuto),
          que recusa a acao e segue -- foi o dono quem apontou a analogia:
          "por que nao limitamos esse envio da maneira que tratamos o 6 por
          minuto?".
        * `patologia=True` (teto de TENTATIVAS estourado): liga
          `disaster_halt`. Sobrou o disjuntor porque um laco infinito de
          verdade nao pode virar "robo rate-limited para sempre, parecendo
          saudavel" -- sem esse segundo nivel a falha que motivou o teto
          original (2026-08-28) volta a passar batida, so' que em silencio.

        Ate' 2026-09-08 havia um teto so' e ele ligava `disaster_halt`: o
        robo perdia o pregao INTEIRO por uma cadencia que a medicao do mesmo
        dia mostrou ser legitima (pior minuto do OOS = 42, contra teto 30).
        Robo calado e' o item 6.15 do `LICOES_DE_PRODUCAO.md`, e um teto que
        cala o robo num dia movimentado e' o item 6.15 embutido no codigo.

        O QUE PASSA E O QUE NAO PASSA. Este portao so' e' chamado de
        `_on_limit_placed`, isto e', so' vale para ENTRADA (`EnterLimit` ->
        `place_limit`). Nunca e' consultado por:
          * `_aplica_cancelamento` / `cancel_limit` / `cancel_stale_refs` --
            cancelar TIRA exposicao;
          * `exit_market` (alvo, stop, flatten, freio de perda do dia,
            `force_flatten` do gap) -- fechar TIRA exposicao;
          * `_ensure_protecao` (stop/alvo na corretora) -- proteger e'
            reduzir risco, nao aumenta-lo.
        A regra e' uma frase: **cota barra abrir, nunca barra sair.** Uma
        cota que atrasasse um fechamento transformaria um freio de execucao
        em risco de posicao aberta -- exatamente a inversao que o incidente
        de 2026-08-28 custou. Cancelamento tambem nao CONSOME cota, e por
        isso a carga real na corretora e' ~o dobro da cota (toda
        substituicao manda um cancelamento junto) -- contabilizado na
        escolha do numero.

        REGRA 6 do AGENTS.md (`live/` nao decide o que negociar). Recusar
        por cota de vazao e' higiene de EXECUCAO, nao decisao de
        estrategia: o robo nao e' avisado, nao muda de lado, nao muda de
        preco e nao muda de tamanho por causa disto -- ele reencontra o
        mesmo estado de "sem ordem parada" que uma recusa da corretora ou
        uma barra velha ja produziam, e redecide sozinho. O que `live/`
        recusa aqui e' EXECUTAR, na velocidade que a corretora aguenta, uma
        decisao que continua inteira da estrategia. Mesma familia da recusa
        por margem (`_check_margem_da_conta`) e da barra velha
        (`_descarta_arme_de_barra_velha`).

        `agora_wall` e' o relogio de PAREDE (`datetime.now(timezone.utc)` no
        ponto de chamada), NUNCA o carimbo da barra/tick que produziu a
        decisao -- e essa distincao e' a razao de este contador existir.

        Ate' 2026-09-08 o ponto de chamada passava `evento.ts` (tempo de
        TICK). Parece equivalente e nao e': um passo do supervisor processa
        TODO o atraso acumulado do feed de uma vez (ver a docstring de
        `_aplica_barras`: "`barras` pode trazer MAIS de uma barra fechada
        neste UNICO passo"), entao a maquina reproduz minutos de historico em
        milissegundos de parede, mandando uma ordem REAL por tick replicado.
        Medido no pregao de 2026-09-08 (slot `dt-wdo_grid_reload_maker-wdo@-
        live`, maquina 24 min atras do mercado -- `last_bar_ts` 14:36:21
        contra `last_poll_at` 15:00:57): 45 ordens-limite enviadas e
        canceladas em 13 SEGUNDOS de parede (09:00:09 -> 09:00:22 no
        terminal), perseguindo o preco de 5117,5 ate' 5107,0; 82 dos 124
        intervalos entre envios do pregao ficaram abaixo de 0,5s, contra 125
        ordens para 22 trades. Em tempo de TICK aquelas 45 estavam a
        `reancora_min_segundos=10.0` uma da outra -- o freio da estrategia
        achou que estava segurando, e este contador tambem: a janela de 60s
        media ~7,5 MINUTOS de tick, nunca chegou a 30, e nada disparou. Quem
        sofre o teto de envios e' a CORRETORA, e a corretora vive em tempo de
        parede; medir a protecao no outro relogio e' nao ter protecao.

        O freio da propria estrategia (`WdoGridReloadMaker.reancora_min_
        segundos`) continua e DEVE continuar em `bar.ts`: la' o carimbo do
        tick e' o unico que existe no backtest, e medir com dois relogios
        faria o numero calibrado nao descrever a producao. Sao papeis
        diferentes -- a estrategia limita a cadencia da DECISAO, este
        contador limita a cadencia do ENVIO. So' o segundo protege a
        corretora, e so' ele pode ler o relogio de parede sem quebrar a
        equivalencia backtest/producao (`live/` nao decide nada aqui: ele
        conta o que ja' foi decidido e para tudo quando a conta e' absurda).

        Nenhum contador existia: o unico teto de repeticao era o de RECUSAS
        DE FECHAMENTO (`MAX_CLOSE_REFUSALS_BEFORE_HALT`). Reancoragem de
        entrada nao tinha limite algum, e o loop do supervisor nao impoe
        cadencia minima entre envios -- entao um laco patologico (decisao
        que se repete, feed devolvendo a mesma barra, estrategia oscilando
        entre dois niveis) manda ordem a cada passo, indefinidamente, sem
        que nada perceba. E' o padrao que o incidente exibiu do lado do
        fechamento, e que do lado da entrada continuava aberto.

        Janela ROLANTE, nao contador de sessao: um teto por pregao ou e'
        alto demais pra pegar o laco, ou baixo demais e mata operacao
        legitima num dia movimentado. Ver `COTA_ENVIOS_POR_MINUTO`.

        RESIDUAL (2026-09-08) -- este contador PARA a rajada, nao a EVITA.
        Enquanto o freio da estrategia medir `bar.ts` (e tem de medir: e'
        regra de estrategia), um passo do supervisor que reprocessa fila
        atrasada continua podendo mandar ate' `COTA_ENVIOS_POR_MINUTO`
        ordens em segundos de parede antes de a cota fechar. O que MUDOU e'
        o preco disso: fechar a cota custa as ordens EXCEDENTES, nao mais o
        pregao inteiro. Duas outras defesas cobrem a mesma rajada por
        angulos diferentes -- o teto de idade de barra
        (`MAX_ATRASO_PARA_ORDEM_SEGUNDOS`, que barra o caso de 08/09 antes
        de chegar aqui: barra velha nao vira ordem) e a histerese de nivel
        (`WdoGridReloadMaker.reancora_min_ticks`, que no replay do mesmo
        pregao derruba o pior minuto de parede de 64 para 21).

        As duas saidas conhecidas, NENHUMA implementada -- ficam registradas
        para o dono decidir, porque as duas mexem em regra estrutural:
          (a) o motor/runtime passar a' estrategia um carimbo que em
              backtest e' o da barra e ao vivo e' o de parede. `live/` cuida
              de relogio (AGENTS.md, regra 6), entao ENTREGAR o numero nao e'
              decidir -- mas a decisao da estrategia deixa de ser funcao so'
              do OHLCV, e portar para MQL5 passa a exigir relogio la' dentro.
          (b) COALESCER, dentro de um mesmo passo do supervisor, as
              `LimitPlaced` que a propria maquina ja' superou: das N
              substituicoes de um lote so' a ULTIMA chega ao book. Parece
              deduplicacao, mas nao e' equivalente -- uma ordem intermediaria
              PODERIA ter preenchido antes de ser cancelada, entao suprimi-la
              muda o que a corretora pode executar, e isso e' `live/`
              decidindo. Precisa de aprovacao explicita, nao de julgamento
              de agente."""
        agora = pd.Timestamp(agora_wall)
        corte = agora - pd.Timedelta(seconds=60)
        # A TENTATIVA e' contada sempre, inclusive quando a cota a recusa --
        # e' o que permite ao disjuntor enxergar um laco que a cota esta'
        # segurando. Contar so' o que saiu prenderia o disjuntor abaixo da
        # cota para sempre, e o robo ficaria "rate-limited" a vida toda
        # parecendo saudavel.
        self._tentativas_recentes = [t for t in self._tentativas_recentes if t > corte]
        self._tentativas_recentes.append(agora)
        self._envios_recentes = [t for t in self._envios_recentes if t > corte]
        tentativas = len(self._tentativas_recentes)
        enviados = len(self._envios_recentes)
        if tentativas > MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO:
            return ExcessoDeCadencia(
                patologia=True,
                motivo=(f"{tentativas} tentativas de envio em 60s (teto "
                        f"{MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO}) -- isto e' "
                        f"laco, nao operacao"),
                envios=enviados, tentativas=tentativas)
        if enviados >= COTA_ENVIOS_POR_MINUTO:
            return ExcessoDeCadencia(
                patologia=False,
                motivo=(f"{enviados} envios de ordem em 60s (cota "
                        f"{COTA_ENVIOS_POR_MINUTO})"),
                envios=enviados, tentativas=tentativas)
        self._envios_recentes.append(agora)
        self._pico_de_envios_no_lote = max(self._pico_de_envios_no_lote,
                                           enviados + 1)
        return None

    def _check_margem_da_conta(self, side: str, quantidade: int,
                               price: float) -> Optional[str]:
        """A CONTA aguenta esta entrada? Devolve o motivo da recusa, ou
        `None` se pode enviar.

        Este e' o unico portao do sistema que ve a EXPOSICAO da conta como
        ela e'. Todos os outros tetos -- `_check_capital`, `_cabe_no_teto`,
        `_cap_capital_atual` -- sao calculados a partir de
        `config.initial_capital + realized_pnl`: numeros locais a UM
        processo, cegos para os OUTROS slots. Todo robo de day trade conecta
        no MESMO terminal, com o MESMO login: uma unica conta, uma unica
        margem fisica. Dois slots em simbolos diferentes (WDO@ e WIN@) com
        R$400 digitados em cada um comprometem margem contra uma conta que
        tem R$400 no total, e cada um passa no proprio teto sozinho -- e' o
        padrao do incidente 2026-08-28 (exposicao agregada nunca somada),
        so' que a soma que faltava e' entre PROCESSOS.

        **A conta e' feita com os dois numeros confiaveis, cada um da sua
        fonte** (correcao de 2026-09-08):

        - **Quanto ja esta comprometido**: `margin` da corretora -- margem
          das posicoes REAIS, de todos os slots e tambem do que o dono abriu
          na mao. Nao passa pelo saldo, entao nao herda a dessincronizacao
          do MT5.
        - **Quanto ha para comprometer**: o LEDGER DO PAINEL
          (`_caixa_operacional_brl`), nunca `margin_free`. `margin_free` e'
          `equity - margin`, e `equity` sai do saldo que a Rico nao
          sincroniza: em 2026-09-08 ele valia -R$3,60 numa conta com R$30
          digitados no painel, o que recusaria toda ordem para sempre, em
          silencio.

        A assimetria e' deliberada: cobra-se deste slot a margem da conta
        INTEIRA contra o caixa DELE. E' conservador de proposito -- e' a
        licao da exposicao agregada, e errar para o lado de recusar uma
        entrada e' barato perto de repetir 2026-08-28.

        "Nao sei" (`None` de qualquer das consultas) NAO bloqueia -- mesma
        politica do resto do arquivo. Quem nao consegue nem ler a conta ja
        vai falhar no envio, com erro mais especifico."""
        if self.executor is None:
            return None
        calc = getattr(self.broker, "margin_required", None)
        if calc is None:
            return None
        exigido = calc(self.strategy.symbol, side, int(quantidade), float(price))
        if exigido is None or exigido <= 0:
            return None
        ler = getattr(self.broker, "account_risk_state", None)
        estado = ler() if ler is not None else None
        if estado is None:
            return None
        comprometida = estado.get("margin")
        if comprometida is None:
            return None
        caixa = self._caixa_operacional_brl()
        if caixa is None:
            return None
        minimo = exigido * MARGEM_LIVRE_MINIMA_FATOR
        if float(comprometida) + minimo <= float(caixa):
            return None
        return (
            f"caixa do robo R$ {float(caixa):.2f} nao cobre a margem da conta: R$ "
            f"{float(comprometida):.2f} ja comprometidos mais R$ {minimo:.2f} desta "
            f"ordem (exige R$ {exigido:.2f} e o projeto pede "
            f"{MARGEM_LIVRE_MINIMA_FATOR:.0f}x de folga). A margem comprometida e' da "
            "conta COMPARTILHADA -- ja inclui o que os outros robos e o proprio dono "
            "tem aberto"
        )

    def _recusa_por_margem(self, conn, account: AccountState, sessao: date,
                           numero: Optional[int], motivo: str) -> None:
        """Desfaz a vigilancia de uma ordem que NAO foi enviada por falta de
        margem na conta -- mesmo desfecho de uma recusa da corretora, e pelo
        mesmo motivo (a maquina ja gravou `resting_limit` e ficaria esperando
        um fill impossivel). Nada foi ao book, entao nao ha ticket orfao."""
        self._recusa_de_envio(
            conn, account, sessao, numero,
            BrokerExecutionError(f"nao enviei: {motivo}", orphan_refs=[]))

    def _reconcilia_ordens_de_entrada(self, conn, account: AccountState,
                                      session: date, ts) -> None:
        """Pergunta a' CORRETORA quais ordens-limite deste robo estao vivas e
        cancela toda que a maquina nao esta vigiando.

        A corretora e' a unica memoria durAvel que este sistema tem de uma
        ordem enviada. Todo o resto -- `pending_entry_refs`, o snapshot, o
        diario -- so' vira linha durAvel no `_persist` do FIM do passo, e o
        envio acontece no MEIO dele. Entre um e outro ha uma janela em que a
        ordem existe no book e nao existe em lugar nenhum nosso: processo
        morto ali (kill, falta de luz, OOM) e o restart nao sabe do ticket,
        redecide do zero e pode mandar uma SEGUNDA ordem no mesmo nivel. E'
        o "2 contratos numa conta de 1" do incidente 2026-08-28, do lado da
        entrada. Nenhum arquivo nosso escrito "mais cedo" resolve isso de
        verdade -- a corretora ja sabe, basta perguntar.

        A regra e' uma so' e nao depende de estrategia nenhuma: **ordem de
        entrada que ninguem vigia tem de morrer.** "Vigiada" e' ter a
        `resting_limit` da maquina apontando pra ela; qualquer ticket fora
        disso preenche sozinho e abre posicao que nenhum robo pediu, sem
        stop na conta de ninguem e sem aparecer no painel.

        Chamada em dois pontos, ambos onde a maquina PROVADAMENTE nao vigia
        nada: no topo de `_start_session` (processo novo -- `restore()` nao
        repoe `resting_limit` de proposito, ela e' decisao redecidida a cada
        processo) e em `_handle_gap` depois do `force_flatten`. Com isso a
        reconciliacao deixa de ser efeito colateral de "a estrategia decidiu
        entrar de novo" -- que era o unico gatilho que existia, e que nunca
        dispara num mercado sem sinal.

        `pending_orders() is None` ("nao consegui perguntar") nao cancela
        nada e nao alarma: mesma politica do resto do arquivo. Mas tambem
        nao limpa `pending_entry_refs` -- o que nao foi confirmado morto
        continua sendo tratado como vivo."""
        if self.executor is None:
            return
        vigiados: set[str] = set()
        if self.machine.resting_limit is not None:
            vigiados = {str(r) for r in (self._snapshot.pending_entry_refs or [])}

        consulta = getattr(self.broker, "pending_orders", None)
        na_corretora = consulta(self.strategy.symbol) if consulta is not None else None
        if na_corretora is None:
            # Nao da' pra confirmar o que existe la'. Ainda assim cancela o
            # que ESTE processo tem registrado e nao vigia -- e' informacao
            # que ja temos, e nao usa-la seria escolher a ignorancia.
            soltos = [r for r in (self._snapshot.pending_entry_refs or [])
                      if str(r) not in vigiados]
            if soltos:
                self._aplica_cancelamento(
                    conn, account, self.executor.cancel_stale_refs(soltos, ts=ts))
            return

        tickets = [str(o.get("ticket")) for o in na_corretora if o.get("ticket")]
        # ADOCAO: ticket que a corretora tem e este processo nunca soube que
        # existia. E' exatamente o que a janela acima produz.
        desconhecidos = [t for t in tickets if t not in vigiados
                         and t not in {str(r) for r in (self._snapshot.pending_entry_refs or [])}]
        if desconhecidos:
            self._snapshot.pending_entry_refs = list(dict.fromkeys(
                (self._snapshot.pending_entry_refs or []) + desconhecidos))
            self._log(conn, account.id, "error",
                      f"ORDEM ORFA em {self.strategy.symbol}: a corretora tem "
                      f"{len(desconhecidos)} ordem(ns) pendente(s) no magic deste robo "
                      f"que este processo nao conhecia ({', '.join(desconhecidos)}). "
                      "Adotei e vou cancelar -- ordem que ninguem vigia preenche "
                      "sozinha (ver incidente 2026-08-28).",
                      {"sessao": session.isoformat(), "tickets": desconhecidos})

        orfaos = [t for t in tickets if t not in vigiados]
        # Registrado aqui e ja' fora do book (preencheu, expirou, foi
        # cancelado na mao): nao aparece em `tickets`, entao nao entra aqui.
        # Some sozinho quando `_aplica_cancelamento` confirmar -- ou fica,
        # se a corretora nao confirmar, que e' o comportamento certo.
        soltos = [r for r in (self._snapshot.pending_entry_refs or [])
                  if str(r) not in vigiados and str(r) not in set(orfaos)]
        alvo = orfaos + [str(r) for r in soltos]
        if not alvo:
            return
        self._aplica_cancelamento(
            conn, account, self.executor.cancel_stale_refs(alvo, ts=ts))

    def _check_posicao_desconhecida(self, conn, account: AccountState, session: date) -> None:
        """A corretora reporta exposicao com o magic DESTE robo que a maquina
        nao conhece -- ou nao conhece do TAMANHO certo? Alarme alto e freio.

        O buraco que isto fecha: NINGUEM perguntava a corretora o que existe
        a menos que a maquina ja acreditasse ter alguma coisa. Todas as
        leituras de posicao (`_ensure_protecao`, `limit_fill`, `exit_market`)
        so' acontecem dentro de um caminho que ja pressupoe posicao. Uma
        posicao que a maquina perdeu de vista -- restart que nao reidratou,
        fill que chegou depois do processo morrer -- ficava INVISIVEL: sem
        stop reforcado, sem aparecer no painel, sem entrar em nenhuma conta.

        Duas divergencias, nao uma. A segunda e' a forma exata do incidente
        de 2026-08-28: a maquina achava que tinha UM contrato e a corretora
        tinha DOIS (duas entradas independentes consolidadas pela conta
        NETTING). Ninguem comparava os dois numeros, entao o robo passou o
        pregao inteiro dimensionando stop, alvo e fechamento pela metade da
        exposicao que de fato existia.

        So' compara quando nao ha ordem em transito (`_tem_ordem_em_transito`)
        -- senao o atraso normal entre o fill na corretora e o `limit_fill`
        da maquina viraria alarme a cada entrada.

        Nao fecha sozinho de proposito. Fechar as cegas uma exposicao cuja
        origem ninguem entendeu troca um problema conhecido por um
        desconhecido, e nesta conta ja houve um fechamento recusado ~24
        vezes. O que ele faz e' o que da' para fazer com certeza: gritar no
        diario (nivel `error` notifica) e travar a abertura de ordem nova
        pelo resto da sessao, do mesmo jeito que o freio duro -- assim a
        exposicao para de crescer enquanto o dono decide.

        Roda so' em execucao REAL: em sombra nao existe corretora para
        divergir.

        **LADO e QUANTIDADE sao conferidos com criterios DIFERENTES, e essa
        assimetria e' o coracao deste metodo** (2026-09-09):

          * QUANTIDADE so' e' comparada quando nao ha ordem em transito --
            uma limite que preencheu na corretora e ainda nao passou pelo
            `limit_fill` da maquina explica um numero diferente, e alarmar
            nisso seria alarmar no funcionamento normal.
          * LADO e' comparado SEMPRE. Nenhuma ordem em transito explica a
            corretora estar do lado CONTRARIO ao da maquina: entre "vendido"
            e "comprado" nao ha atraso, ha erro. Um robo que acha que esta
            vendido enquanto a corretora o tem comprado calcula stop, alvo e
            fechamento todos ao contrario.

        Foi exatamente o que aconteceu, e o gate de transito era o que
        escondia: 2026-09-09 10:55:09 BRT, slot `dt-wdo_grid_reload_maker-
        wdo@-live`, conta real de R$375. A maquina tinha SHORT #04 1 @
        5123,50 (stop 5131,50); a corretora tinha LONG 2 @ 5122,50 com
        `sl=0.0 tp=0.0`. Como havia uma fatia de saida pendurada
        (`pending_exit_order`), `_tem_ordem_em_transito()` era True e este
        metodo voltava na primeira linha, a cada passo, durante ~3 minutos --
        sem nunca comparar nada. Nesse intervalo o `_ensure_protecao` tentava
        registrar o stop do SHORT (5131,50, ACIMA do mercado) numa posicao
        LONG e levava `retcode=10016 (Invalid stops)` de volta em todo passo,
        entao a posicao de 2 contratos ficou NUA ate' o dono zerar na mao.

        E o alarme de quantidade sozinho nao teria pego o pior caso, mesmo
        sem o gate: `_Position.quantity` e' MAGNITUDE (o sinal mora em
        `.side` -- ver `_on_closed`), entao maquina SHORT 1 contra corretora
        LONG 1 comparava `1 == 1` e passava como "tudo certo". A inversao
        perfeita, que e' o desfecho do incidente de 2026-08-28 e do item 1.4,
        era exatamente o caso INVISIVEL."""
        if self.executor is None:
            return
        estado = self.broker.position_state(self.strategy.symbol)
        if not estado.get("ok"):
            # "Nao consegui perguntar" nunca vira alarme -- mesma politica do
            # resto do arquivo. Quem precisa de certeza para operar ja falha
            # alto por conta propria (`_read_position`).
            return
        real = estado.get("position")
        qtd_real = int((real or {}).get("quantity") or 0)
        qtd_maquina = int(sum(p.quantity for p in self.machine.positions))

        # ---- LADO: sem gate de transito, e antes de tudo. ----
        lado_real = (real or {}).get("side") if qtd_real > 0 else None
        lado_maquina = self.machine.positions[0].side if self.machine.positions else None
        divergiu = (lado_real is not None and lado_maquina is not None
                    and lado_real != lado_maquina)
        # Baixa o flag assim que os dois voltam a concordar (inclusive quando um
        # dos lados fica FLAT). Sem isto ele ficaria levantado pelo resto da
        # VIDA DO PROCESSO -- e o processo `loop` roda continuo, atravessando
        # pregoes -- entao um freio duro de outro motivo, dias depois, se
        # recusaria a zerar uma posicao que ninguem mais disputa.
        if not divergiu:
            self._lado_divergente = False
        if divergiu:
            ticket = (real or {}).get("ticket")
            chave = f"lado:{ticket}:{lado_real}"
            if chave in self._posicao_desconhecida_avisada:
                return
            self._posicao_desconhecida_avisada.add(chave)
            motivo = (
                f"a corretora reporta {qtd_real} {self.strategy.symbol} {lado_real} "
                f"@ {(real or {}).get('price')} (ticket {ticket}, "
                f"sl={(real or {}).get('sl')} tp={(real or {}).get('tp')}) enquanto a "
                f"maquina se acha {lado_maquina} de {qtd_maquina} -- LADO INVERTIDO, "
                "stop e alvo desta posicao estao sendo calculados ao contrario"
            )
            self._snapshot.disaster_halt = True
            self._snapshot.disaster_reason = motivo
            self._lado_divergente = True
            self._log(conn, account.id, "error",
                      f"LADO DIVERGENTE em {self.strategy.symbol}: {motivo}. Parei de "
                      "abrir ordem nova. NAO vou fechar sozinho -- confira o terminal "
                      "e decida (ver incidente 2026-09-09).",
                      {"sessao": session.isoformat(), "ticket": ticket,
                       "lado_corretora": lado_real, "lado_maquina": lado_maquina,
                       "quantidade_corretora": qtd_real,
                       "quantidade_maquina": qtd_maquina})
            return

        # ---- TETO DE CAIXA: tambem sem gate de transito. ----
        #
        # Ordem do dono, 2026-09-09: "a trava nao deve deixar para sempre 1
        # contrato, e' so' para respeitar os limites de quando pode aumentar e
        # quando tem que diminuir a quantidade de contratos com base no valor
        # disponivel em caixa". `_cap_capital_atual()` ja faz a metade de
        # DENTRO -- e' recalculado a cada chamada sobre
        # `initial_capital + realized_pnl`, entao acompanha o caixa para cima e
        # para baixo. O que faltava era a metade de FORA: ninguem conferia o
        # teto contra o que a CORRETORA de fato tem.
        #
        # No incidente de 2026-09-09 o caixa era R$375 e
        # `contracts_from_capital_operacional(375, 150)` da' 1 -- a corretora
        # tinha 2. Nenhuma ordem em transito explica isso: a maquina nunca
        # MANDA alem do teto, entao exposicao acima dele nao pode estar "a
        # caminho", ela ja e' erro.
        #
        # `max(teto, qtd_maquina)` de proposito: uma posicao que a maquina
        # CONHECE nunca vira alarme aqui, mesmo que o teto tenha encolhido
        # depois de ela abrir (o dono re-sincronizar o caixa para baixo no
        # painel, por exemplo). Este teto e' limitador de exposicao NOVA, nao
        # de posicao ja aberta -- ver a docstring de `_cap_capital_atual`.
        teto = self.machine._cap_capital_atual()
        if teto is not None and qtd_real > max(int(teto), qtd_maquina):
            ticket = (real or {}).get("ticket")
            chave = f"teto:{ticket}:{qtd_real}"
            if chave in self._posicao_desconhecida_avisada:
                return
            self._posicao_desconhecida_avisada.add(chave)
            motivo = (
                f"a corretora reporta {qtd_real} {self.strategy.symbol} "
                f"{(real or {}).get('side')} (ticket {ticket}) -- acima do teto de "
                f"{int(teto)} que o caixa atual sustenta E acima dos {qtd_maquina} que "
                "a maquina conhece. Exposicao que o caixa NAO cobre"
            )
            self._snapshot.disaster_halt = True
            self._snapshot.disaster_reason = motivo
            self._log(conn, account.id, "error",
                      f"EXPOSICAO ACIMA DO CAIXA em {self.strategy.symbol}: {motivo}. "
                      "Parei de abrir ordem nova. NAO vou fechar sozinho -- confira o "
                      "terminal e decida (ver incidente 2026-09-09).",
                      {"sessao": session.isoformat(), "ticket": ticket,
                       "quantidade_corretora": qtd_real, "teto_por_caixa": int(teto),
                       "quantidade_maquina": qtd_maquina})
            return

        # ---- QUANTIDADE: so' quando nao ha fill legitimamente a caminho. ----
        if self._tem_ordem_em_transito():
            return
        if qtd_real == qtd_maquina:
            return
        if qtd_real == 0:
            # A maquina acha que tem e a corretora diz que nao ha nada. NAO e'
            # alarme daqui: a protecao SL/TP registrada na corretora fecha a
            # posicao sozinha por desenho, e `exit_market` ja trata esse
            # encontro na proxima barra. Alarmar aqui transformaria o
            # funcionamento correto do stop em incidente.
            return
        ticket = (real or {}).get("ticket")
        chave = f"{ticket}:{qtd_real}"
        if chave in self._posicao_desconhecida_avisada:
            return
        self._posicao_desconhecida_avisada.add(chave)
        motivo = (
            f"a corretora reporta {qtd_real} {self.strategy.symbol} "
            f"{(real or {}).get('side')} @ {(real or {}).get('price')} no magic deste "
            f"robo (ticket {ticket}, sl={(real or {}).get('sl')} "
            f"tp={(real or {}).get('tp')}), mas a maquina sabe de {qtd_maquina} -- "
            "exposicao FORA de controle"
        )
        self._snapshot.disaster_halt = True
        self._snapshot.disaster_reason = motivo
        self._log(conn, account.id, "error",
                  f"EXPOSICAO DIVERGENTE em {self.strategy.symbol}: {motivo}. Parei de "
                  "abrir ordem nova. NAO vou fechar sozinho -- confira o terminal e "
                  "decida (ver incidente 2026-08-28).",
                  {"sessao": session.isoformat(), "ticket": ticket,
                   "quantidade_corretora": qtd_real, "quantidade_maquina": qtd_maquina,
                   "lado": (real or {}).get("side")})

    # ---------- freio duro de caixa/margem (gap e/f, incidente 2026-08-28) --

    def _check_freio_duro(self, conn, account: AccountState, session: date) -> Optional[str]:
        """Este robo esta perdendo demais, ou o caixa dele acabou? Devolve
        o motivo do freio, ou `None` se pode operar normalmente.

        Motivado pelo incidente 2026-08-28: a conta chegou a equity NEGATIVA
        (-R$298,60) com o processo CONTINUANDO a tentar abrir e fechar
        ordem, sem nenhum freio -- o motor de BACKTEST ja tem `wiped_out_at`
        para isto, o lado ao vivo nao tinha nada equivalente.

        So' roda em execucao REAL (`self.executor is not None`): sombra
        nunca manda ordem, entao nao ha risco de conta real pra travar.

        Uma vez TRIPADO (`disaster_halt=True`, persistido -- ver
        `_SessionSnapshot`), fica tripado pelo resto da SESSAO: nao ha
        caminho automatico de "o caixa voltou, libera de novo" -- recuperar
        de patrimonio negativo (ou perto disso) e' decisao do DONO
        (deposito, investigacao), nunca do robo (regra 6 do AGENTS.md).
        Reseta sozinho no PROXIMO pregao (sessao nova = snapshot novo).

        **O caixa que decide e' o do PAINEL, nunca o do MT5** (correcao de
        2026-09-08, depois de este freio travar um robo intacto com base em
        equity -R$3,60 reportada pelo terminal numa conta com R$30,00
        digitados). Ver `_caixa_operacional_brl`.

        `None` (nao deu pra perguntar ao terminal) NUNCA vira alarme --
        mesma politica do resto do arquivo (`_check_autotrading` etc): "nao
        sei" nao e' motivo de freio, e quem nao consegue nem ler o terminal
        ja vai falhar em outro lugar com erro mais especifico."""
        if self.executor is None:
            return None
        if self._snapshot.disaster_halt:
            self._tenta_zerar_por_freio_duro(conn, account, session)
            return self._snapshot.disaster_reason

        # (1) TETO DE PERDA DO PREGAO, marcado a mercado. Vem ANTES do teste
        # de ruina de proposito: e' o freio que dispara enquanto ainda ha o
        # que salvar. O de baixo (caixa <= 0) so' constata o obito.
        perda = self._perda_do_pregao_brl()
        if (self.perda_maxima_dia_brl > 0 and perda is not None
                and perda >= self.perda_maxima_dia_brl):
            motivo = (
                f"perda de R$ {perda:.2f} no pregao (teto R$ "
                f"{self.perda_maxima_dia_brl:.2f}), marcada a mercado -- "
                "inclui a posicao ainda aberta"
            )
            self._snapshot.disaster_halt = True
            self._snapshot.disaster_reason = motivo
            self._log(conn, account.id, "error",
                      f"FREIO DE PERDA em {self.strategy.symbol}: {motivo}. Parando de "
                      "abrir ordem nova e tentando zerar o que estiver aberto. Nao "
                      "volta sozinho neste pregao.",
                      {"sessao": session.isoformat(), "perda_brl": round(perda, 2),
                       "teto_brl": round(self.perda_maxima_dia_brl, 2)})
            self._tenta_zerar_por_freio_duro(conn, account, session)
            return motivo

        # (2) RUINA -- ultimo recurso: o caixa deste robo acabou. Quem
        # responde e' o LEDGER DO PAINEL (`_caixa_operacional_brl`), nunca o
        # saldo do MT5 -- por isso este teste vem ANTES de falar com o
        # terminal, e continua valendo mesmo com o terminal mudo.
        caixa = self._caixa_operacional_brl()
        if caixa is not None and caixa <= 0.0:
            motivo = (
                f"caixa do robo R$ {caixa:.2f}, marcado a mercado (ledger do painel: "
                f"R$ {self.config.initial_capital:.2f} digitados, "
                f"{self.machine.realized_pnl:+.2f} realizados) -- robo em risco de ruina"
            )
            self._snapshot.disaster_halt = True
            self._snapshot.disaster_reason = motivo
            self._log(conn, account.id, "error",
                      f"FREIO DURO em {self.strategy.symbol}: {motivo}. Parando de abrir "
                      "ordem nova e tentando zerar o que estiver aberto. Nao volta "
                      "sozinho -- precisa de intervencao (ver incidente 2026-08-28).",
                      {"sessao": session.isoformat(), "caixa_brl": round(caixa, 2),
                       "capital_painel": float(self.config.initial_capital),
                       "realizado_brl": float(self.machine.realized_pnl or 0.0)})
            self._tenta_zerar_por_freio_duro(conn, account, session)
            return motivo

        # (3) TERMINAL MUDO. A leitura do MT5 nao decide mais ruina nenhuma
        # (ver acima); serve para dois fins: detectar que o terminal parou de
        # responder, e registrar no diario quando o saldo dele contradiz o
        # painel (`_avisa_saldo_mt5_dessincronizado`).
        ler = getattr(self.broker, "account_risk_state", None)
        if ler is None:
            return None
        estado = ler()
        if estado is None:
            # "Nao sei" isolado nao freia. "Nao sei" CONTINUADO freia: seguir
            # operando sem NENHUMA leitura de risco e' apostar que quem nao
            # le equity tambem nao consegue mandar ordem -- uma suposicao
            # razoavel que nada no codigo garante.
            self._risco_ilegivel_seguidas += 1
            if self._risco_ilegivel_seguidas < MAX_LEITURAS_DE_RISCO_FALHAS:
                return None
            motivo = (
                f"{self._risco_ilegivel_seguidas} leituras seguidas de "
                "equity/margem falharam -- estou operando sem enxergar o risco "
                "da conta"
            )
            self._snapshot.disaster_halt = True
            self._snapshot.disaster_reason = motivo
            self._log(conn, account.id, "error",
                      f"FREIO DURO em {self.strategy.symbol}: {motivo}. Parando de "
                      "abrir ordem nova e tentando zerar o que estiver aberto.",
                      {"sessao": session.isoformat(),
                       "leituras_falhas": self._risco_ilegivel_seguidas})
            self._tenta_zerar_por_freio_duro(conn, account, session)
            return motivo
        self._risco_ilegivel_seguidas = 0
        self._avisa_saldo_mt5_dessincronizado(conn, account, session, estado, caixa)
        return None

    def _perda_do_pregao_brl(self) -> Optional[float]:
        """Quanto ESTE robo perdeu hoje, marcado a mercado, em R$ positivos
        (0.0 ou negativo = nao esta perdendo). `None` = nao da' para dizer.

        Realizado (`machine.session_pnl`) MAIS o que esta aberto
        (`machine.unrealized_brl`). O segundo termo e' o ponto: no incidente
        de 2026-08-28 a perda inteira -- -R$295 -- ficou NAO REALIZADA por
        uma hora, enquanto a corretora recusava o fechamento. Um freio que
        so' olhasse P&L fechado nao teria visto um centavo dela ate ser
        tarde. E' tambem o que separa este numero do `session_stop_brl` que
        algumas estrategias tem: aquele e' opcional, por robo, so' realizado,
        e so' impede entrada NOVA.

        Sem posicao aberta nao precisa de preco nenhum. Com posicao aberta e
        sem cotacao, devolve `None` -- "nao sei" nunca vira "nao esta
        perdendo", mas tambem nao vira freio (mesma politica do arquivo)."""
        realizado = float(self.machine.session_pnl or 0.0)
        if not self.machine.positions:
            return -realizado
        ultimo = getattr(self.broker, "last_price", None)
        preco = ultimo(self.strategy.symbol) if ultimo is not None else None
        if preco is None:
            return None
        return -(realizado + self.machine.unrealized_brl(float(preco)))

    def _caixa_operacional_brl(self) -> Optional[float]:
        """Quanto este robo tem de caixa AGORA, marcado a mercado, em R$.
        `None` = nao da' para dizer (nunca "esta zerado").

        Conta: `config.initial_capital` -- o numero que o DONO digitou no
        painel, reposto a cada pregao por `_resincroniza_capital` -- mais o
        que a maquina ja realizou (`machine.realized_pnl`), mais o que a
        posicao aberta vale agora. E' exatamente a mesma conta que dimensiona
        lote e teto de contratos (`_cap_capital_atual`), entao freio, portao
        de margem e dimensionamento passam a olhar para o MESMO caixa.

        **Por que nao o saldo do MT5.** `account_info().balance/equity/
        margin_free` da conta Rico NAO acompanha o dinheiro real da corretora
        -- a propria corretora confirma que nao existe sincronizacao (ver
        CLAUDE.md, "Saldo do MT5 (Rico) nao e' confiavel como fonte de
        capital"). Em 2026-09-08 o terminal reportou equity -R$3,60 num slot
        cujo ledger tinha R$30,00 digitados, e o freio duro declarou "conta em
        risco de ruina" e travou o pregao de um robo intacto, na primeira
        barra, sem nenhuma ordem enviada. Numero de corretora que a propria
        corretora diz nao ser confiavel nao pode ser gatilho de nada -- so'
        de diagnostico (`_avisa_saldo_mt5_dessincronizado`).

        Com posicao aberta e sem cotacao devolve `None`: "nao sei" nunca vira
        "esta zerado", mesma politica do resto do arquivo."""
        caixa = float(self.config.initial_capital) + float(self.machine.realized_pnl or 0.0)
        if not self.machine.positions:
            return caixa
        ultimo = getattr(self.broker, "last_price", None)
        preco = ultimo(self.strategy.symbol) if ultimo is not None else None
        if preco is None:
            return None
        return caixa + float(self.machine.unrealized_brl(float(preco)))

    def _avisa_saldo_mt5_dessincronizado(self, conn, account: AccountState, session: date,
                                         estado: dict, caixa: Optional[float]) -> None:
        """UMA linha por pregao quando o terminal reporta patrimonio zerado
        ou negativo e o ledger do painel diz que ha caixa.

        Nao freia, nao recusa, nao dimensiona nada -- ver
        `_caixa_operacional_brl`. Existe por dois motivos: o dono ve a
        dessincronizacao no diario em vez de ela virar misterio, e a proxima
        pessoa (ou IA) que ler "o MT5 diz que a conta esta zerada" ja
        encontra escrito, no mesmo lugar, que isso NAO quer dizer que a conta
        esta zerada."""
        if self._saldo_mt5_avisado_em == session or caixa is None or caixa <= 0.0:
            return
        equity = estado.get("equity")
        margem_livre = estado.get("margin_free")
        if not [v for v in (equity, margem_livre) if v is not None and float(v) <= 0.0]:
            return
        self._saldo_mt5_avisado_em = session
        self._log(conn, account.id, "warn",
                  f"MT5 reporta patrimonio zerado/negativo em {self.strategy.symbol} "
                  f"(equity R$ {equity}, margem livre R$ {margem_livre}), mas o caixa "
                  f"deste robo no painel e' R$ {caixa:.2f} -- IGNORANDO o numero do "
                  "terminal: a Rico nao sincroniza o saldo com o MT5. Sigo operando "
                  "pelo ledger digitado no painel.",
                  {"sessao": session.isoformat(), "caixa_brl": round(caixa, 2),
                   "mt5_equity": equity, "mt5_margem_livre": margem_livre})

    def _tenta_zerar_por_freio_duro(self, conn, account: AccountState, session: date) -> None:
        """Tenta fechar A MERCADO o que estiver aberto, sob o freio duro.

        Usa `MT5Broker.last_price()` como referencia (nao uma barra fechada
        -- o freio pode disparar entre barras, e esperar a proxima so' pra
        ter um OHLC seria adiar de proposito o que precisa acontecer AGORA).
        Sem preco de referencia, so' desiste desta tentativa (tenta de novo
        no proximo passo, ~5s depois) -- mandar ordem as cegas, sem preco
        NENHUM, e' pior do que esperar.

        **Ordem viva conta tanto quanto posicao aberta.** Antes esta funcao
        saia na primeira linha quando `machine.positions` estava vazio -- e
        com isso o freio duro deixava intacta a ordem-limite PARADA no book.
        O robo entrava em "nao abro mais nada" com uma ordem que abre
        sozinha: bastava o preco tocar o nivel para nascer uma posicao nova,
        numa conta que o proprio robo acabou de declarar em risco de ruina, e
        com o robo agora cego (freio tripado = nao consome barra, nao
        redecide). `force_flatten` ja sabia fechar as duas coisas -- ninguem
        chegava a chama-lo."""
        tem_posicao = bool(self.machine.positions)
        tem_ordem = (
            self.machine.resting_limit is not None
            or bool(self._snapshot.pending_entry_refs)
            or (self.executor is not None and bool(self.executor.pending_orders))
        )
        if tem_posicao and self._lado_divergente:
            # LADO divergente: a maquina e a corretora discordam sobre estar
            # comprada ou vendida, e fechar "a posicao" nessa condicao e'
            # fechar as cegas -- em conta NETTING a ordem sai do tamanho e do
            # lado ERRADOS e o excedente nao vira zero, vira posicao invertida
            # (item 1.4). Foi o que o proprio executor recusou a fazer no
            # incidente de 2026-09-09, e ele estava certo: o log da conta real
            # termina com dezenas de `BrokerExecutionError` justamente porque
            # o freio insistia em zerar uma posicao cujo lado ele nao conhecia.
            #
            # ORDEM viva continua sendo cancelada abaixo, e essa parte nao tem
            # ambiguidade nenhuma: ordem que ninguem vigia preenche sozinha e
            # so' pode PIORAR a exposicao ja divergente.
            tem_posicao = False
            self._log(conn, account.id, "warn",
                      f"nao vou zerar {self.strategy.symbol} sozinho: a corretora e a "
                      "maquina discordam sobre o LADO da posicao. Cancelo o que estiver "
                      "no book e espero voce conferir o terminal.",
                      {"sessao": session.isoformat()})
        if not (tem_posicao or tem_ordem):
            return
        ultimo_preco = getattr(self.broker, "last_price", None)
        preco = ultimo_preco(self.strategy.symbol) if ultimo_preco is not None else None
        if preco is None and tem_posicao:
            self._log(conn, account.id, "error",
                      f"freio duro sem preco de referencia para zerar {self.strategy.symbol} "
                      "-- tento de novo no proximo passo", {"sessao": session.isoformat()})
            return
        if preco is None:
            # Sem posicao, so' ordem viva: cancelar nao precisa de preco
            # nenhum (`force_flatten` nao toca em `price` quando nao ha
            # posicao), e adiar o cancelamento por falta de cotacao deixaria
            # de pe exatamente a ordem que este freio existe para tirar.
            preco = 0.0
        agora = pd.Timestamp(datetime.now(timezone.utc))
        bar_sintetica = Bar(ts=agora, open=preco, high=preco, low=preco, close=preco, volume=0.0)
        if not tem_posicao and self._lado_divergente:
            # So' o cancelamento -- `force_flatten` fecharia a posicao que o
            # bloco acima acabou de decidir NAO fechar.
            if self.executor is not None and self._snapshot.pending_entry_refs:
                self._aplica_cancelamento(conn, account, self.executor.cancel_stale_refs(
                    self._snapshot.pending_entry_refs, ts=agora))
            self._drena_orfas_de_saida(conn, account, agora)
            return
        try:
            eventos = self.machine.force_flatten(agora, preco)
        except BrokerExecutionError as erro:
            # So' `FECHAMENTO_RECUSADO` e' capturado -- ver a docstring de
            # `_consume` para o motivo (uma divergencia de dado, `FALHA_
            # ALTO`, precisa propagar e travar o passo, nao virar retry
            # silencioso).
            if erro.kind not in self._KINDS_QUE_REAVALIAM:
                raise
            self._registra_espera_ou_falha(conn, account, session, erro)
            return
        for evento in eventos:
            self._apply(conn, account, evento, bar_sintetica)
        # `_on_limit_cancelled` cancela pelo que ESTE processo tem em memoria
        # (`executor.pending_orders`), que nasce vazio depois de um restart --
        # ai o unico registro do ticket vivo e' `pending_entry_refs`,
        # persistido. Sem esta varredura, um freio duro logo apos um restart
        # deixava no book exatamente a ordem que ele existe para tirar.
        if self.executor is not None and self._snapshot.pending_entry_refs:
            self._aplica_cancelamento(conn, account, self.executor.cancel_stale_refs(
                self._snapshot.pending_entry_refs, ts=agora))
        self._drena_orfas_de_saida(conn, account, agora)

    #: Os dois `kind` que a maquina pode levantar sem que o passo precise
    #: travar: a posicao continua aberta e a proxima barra reavalia. Ver
    #: `BrokerExecutionError` para o que cada um significa -- e por que
    #: `AGUARDANDO_PROTECAO` NAO pode contar como recusa.
    _KINDS_QUE_REAVALIAM = (
        BrokerExecutionError.FECHAMENTO_RECUSADO,
        BrokerExecutionError.AGUARDANDO_PROTECAO,
    )

    def _registra_espera_ou_falha(self, conn, account: AccountState, session: date,
                                  erro: BrokerExecutionError) -> None:
        """Despacha entre "estou esperando o nivel ser tocado" (normal) e "a
        corretora RECUSOU meu fechamento" (alarme).

        Existe desde 2026-09-08, quando alvo e stop passaram a ser fechados
        pela protecao registrada na corretora (`exit_por_protecao`). Antes,
        todo `BrokerExecutionError` capturado aqui era recusa -- e recusa
        conta para `MAX_CLOSE_REFUSALS_BEFORE_HALT`. Esperar o alvo ser
        tocado e' o funcionamento NORMAL e acontece a cada barra enquanto a
        posicao vive: contar isso como recusa travaria o robo em poucos
        segundos, transformando o comportamento correto em incidente (mesmo
        erro de categoria que `_check_atividade_estranha` evita)."""
        if erro.kind == BrokerExecutionError.AGUARDANDO_PROTECAO:
            # Zera a contagem de recusas: chegar aqui prova que o caminho de
            # saida esta' funcionando -- a posicao so' nao fechou porque o
            # nivel nao foi tocado. Sem log: seria uma linha por barra.
            self._snapshot.close_refusal_count = 0
            return
        self._registra_falha_de_fechamento(conn, account, session, erro)

    def _registra_falha_de_fechamento(self, conn, account: AccountState, session: date,
                                      erro: BrokerExecutionError) -> None:
        """Gap (f): a corretora recusou um fechamento -- SEMPRE vira evento
        no diario (com notificacao, ver `_log`), e depois de
        `MAX_CLOSE_REFUSALS_BEFORE_HALT` recusas SEGUIDAS aciona o freio
        duro.

        Motivado pelo incidente 2026-08-28: a corretora recusou ~24 vezes
        seguidas o fechamento do slot `dt-wdo_grid_reload_maker-wdo@-live`
        (MG51, margem esgotada) e NADA disso apareceu no diario nem
        alertou ninguem -- so' uma linha `[erro]` repetida no log bruto do
        processo, que ninguem olha em tempo real. Duas coisas fechadas
        aqui: visibilidade (toda recusa vira evento + notificacao, sempre)
        e limite (martelar a corretora a cada poucos segundos por horas nao
        resolve um problema estrutural de margem/protecao -- so' produz
        mais linha de log)."""
        self._snapshot.close_refusal_count += 1
        n = self._snapshot.close_refusal_count
        self._log(conn, account.id, "error",
                  f"RECUSA DE FECHAMENTO #{n} em {self.strategy.symbol}: {erro} -- "
                  "posicao continua ABERTA, tentando de novo",
                  {"sessao": session.isoformat(), "tentativa": n, "erro": str(erro)})
        if n >= MAX_CLOSE_REFUSALS_BEFORE_HALT and not self._snapshot.disaster_halt:
            motivo = (
                f"{n} recusas SEGUIDAS de fechamento em {self.strategy.symbol} (ultima: "
                f"{erro}) -- parando de bater na mesma cadencia; precisa de intervencao "
                "manual (conferir margem/SL-TP na corretora, ver incidente 2026-08-28)."
            )
            self._snapshot.disaster_halt = True
            self._snapshot.disaster_reason = motivo
            self._log(conn, account.id, "error", f"FREIO DURO: {motivo}",
                      {"sessao": session.isoformat()})

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
        posicao com o evento de preco MAIS RECENTE e recomeca a sessao dali.

        `force_flatten` pode levantar `BrokerExecutionError`. So' `kind=
        FECHAMENTO_RECUSADO` (fechamento recusado pela corretora, posicao
        continua exatamente como estava) e' capturada e registrada aqui em
        vez de propagar, pelo MESMO motivo de `_consume`: `store.
        live_journal` faz ROLLBACK em qualquer excecao, e deixar propagar
        apagaria o proprio alerta que este metodo acabou de gravar, alem de
        nunca persistir o avanco de `last_bar_ts` (ver a docstring do bloco
        equivalente em `_consume`). Qualquer outro `kind` (divergencia de
        dado) e' RE-LEVANTADO, o comportamento de sempre.

        MEDIO 7 (auditoria adversarial 2026-08-28): `force_flatten` roda
        UMA vez so' (nao um lote de barras como `_consume`), e' o UNICO
        efeito colateral real deste metodo, e nada depois dele (`_drena_
        orfas_de_saida`/`_reconcilia_ordens_de_entrada` sao ambos "nunca
        levanta", ver as docstrings deles) pode levantar hoje -- ou seja,
        este caminho JA' nao tinha o bug de `_consume` (uma barra real
        confirmada seguida de outra que falha alto no MESMO lote). O
        `self._checkpoint` logo abaixo existe mesmo assim, por consistencia
        e defesa em profundidade: se algum dia algo for inserido entre a
        aplicacao dos eventos e o fim deste metodo, o fechamento real ja'
        confirmado por `force_flatten` continua protegido contra rollback."""
        ultima = barras[-1]
        fechados = []
        try:
            eventos = self.machine.force_flatten(ultima.ts, ultima.close)
        except BrokerExecutionError as erro:
            # MEDIO 7 (risco residual, defesa em profundidade -- ver a
            # docstring de `force_flatten`: hoje `eventos` nunca chega
            # parcialmente preenchido aqui, porque execucao real nunca tem
            # mais de 1 posicao. Fica pelo MESMO motivo do `_checkpoint`
            # logo abaixo: se o invariante mudar um dia, este caminho ja
            # esta protegido sem precisar lembrar de voltar aqui).
            self._aplica_eventos_parciais_antes_de_falhar(conn, account, erro, ultima)
            if erro.kind not in self._KINDS_QUE_REAVALIAM:
                raise
            self._registra_espera_ou_falha(conn, account, session, erro)
            self._snapshot.last_bar_ts = ultima.ts
            return StepReport("daytrade_buraco_recusa_fechamento", session,
                              detail={"parado_segundos": round(parado_ha, 1),
                                      "erro": str(erro)})
        for evento in eventos:
            if isinstance(evento, PositionClosed):
                fechados.append(evento)
            self._apply(conn, account, evento, ultima)
        # CHECKPOINT (MEDIO 7): torna durAvel agora o que `force_flatten` ja'
        # confirmou de verdade na corretora, antes do resto deste metodo.
        self._checkpoint(conn, account)
        self._drena_orfas_de_saida(conn, account, ultima.ts)
        # `force_flatten` cancela a `resting_limit` EM MEMORIA -- se o buraco
        # coincidiu com um restart (o caso mais provavel de buraco real), a
        # memoria deste processo ja nasceu vazia e ele nao tem o que cancelar,
        # mesmo com um ticket REAL vivo no book. Quem sabe e' a corretora.
        self._reconcilia_ordens_de_entrada(conn, account, session, ultima.ts)
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

    def _reconcilia_entrada_orfa(self, conn, account: AccountState, bar: Bar) -> None:
        """A ordem-limite de entrada que a maquina esta vigiando
        (`resting_limit`) ja terminou o ciclo de vida inteiro na
        corretora, SEM que `MT5IntradayExecution.limit_fill` (crescimento
        de posicao) tivesse a chance de perceber? Chamado ANTES de
        `machine.on_closed_bar(bar)`, de proposito -- se resolver algo
        aqui, a chamada normal que vem depois ja roda com `resting_limit`
        livre e `positions` vazia, e a estrategia pode re-armar NESTA
        mesma barra.

        Caso medido ao vivo em 2026-09-04 (slot
        `dt-wdo_grid_reload_maker-wdo@-live`): ordem armada as 14:18:23,
        preenchida as 14:18:31, posicao fechada pelo alvo ATOMICO da
        propria corretora as 14:18:32 -- os DOIS dentro do MESMO intervalo
        de poll do supervisor (5s). `limit_fill` compara a quantidade da
        posicao ANTES contra AGORA; se as duas leituras caem nos dois
        extremos de um ciclo completo (0 -> N -> 0), o crescimento nunca
        aparece e a maquina ficaria vigiando um ticket que a corretora ja
        resolveu ha' minutos -- o robo trava pelo resto do pregao.

        So' consulta a corretora quando ha' algo para reconciliar
        (`resting_limit is not None`) -- nao adiciona custo aos passos em
        que o robo nao tem ordem pendente. Usa `self._snapshot.
        pending_entry_refs` (nao `self.executor.pending_orders`) porque e'
        a lista que SOBREVIVE a um restart no meio do pregao; `pending_
        orders` nasce vazia numa instancia nova de `MT5IntradayExecution`."""
        if self.executor is None or self.machine.resting_limit is None:
            return
        refs = list(self._snapshot.pending_entry_refs or [])
        if not refs:
            return
        resultado = self.executor.resolve_orphaned_entry(refs)
        if resultado is None or resultado["outcome"] == "already_open":
            # Ainda vivo, consulta falhou, ou preencheu mas continua aberto
            # -- nos dois ultimos casos o caminho normal (`limit_fill`, na
            # chamada de `on_closed_bar` que vem depois) resolve sozinho.
            return
        order = self.machine.resting_limit
        self.machine.discard_resting_limit()
        self._snapshot.pending_entry_refs = []
        self._volume_no_nivel = 0.0
        if resultado["outcome"] == "dead":
            numero = self._numero_ordem_atual()
            self._snapshot.ordens_abandonadas += 1
            qtd = sum(order.children(self.config.default_quantity))
            self._log(conn, account.id, "info",
                      f"CANCELA {order.side.upper()} #{numero:02d} "
                      f"{self._lotes_txt(qtd)} {self.strategy.symbol} "
                      f"@ {order.limit_price:.4f} (corretora confirmou: sem "
                      "preenchimento)",
                      {"numero_ordem": numero, "side": order.side, "tipo": "cancelada",
                       "quantity": qtd, "limit_price": order.limit_price,
                       "reason": "reconciliado_sem_fill",
                       "sessao": self._snapshot.session.isoformat()
                       if self._snapshot.session else None})
            self._snapshot.trade_num = None
            return
        # "round_trip": preencheu E fechou por inteiro entre dois polls --
        # ver `_aplica_entrada_e_saida_reconciliadas`.
        self._aplica_entrada_e_saida_reconciliadas(conn, account, order, bar, resultado)

    @staticmethod
    def _infere_motivo_saida(order: EnterLimit, exit_price: float, comment: str) -> IntradayExitReason:
        """Qual foi o motivo da saida (`IntradayExitReason`) de uma posicao
        reconciliada pelo historico? O MT5 marca o `comment` do deal de
        saida quando fecha por SL/TP proprio (`"[tp 5154.500]"`/
        `"[sl 5146.000]"`, formato observado ao vivo) -- confia nisso
        primeiro. Sem marca reconhecivel (ex.: fechamento a mercado por uma
        tentativa NOSSA, sem comentario da corretora), desempata pela
        distancia do preco real de saida a cada nivel que a PROPRIA ordem
        declarou -- nunca inventa um nivel que a estrategia nao pediu."""
        texto = (comment or "").lower()
        if "[tp" in texto or "target" in texto:
            return IntradayExitReason.TARGET
        if "[sl" in texto or "stop" in texto:
            return IntradayExitReason.STOP
        if order.initial_target is not None and order.initial_stop is not None:
            return (IntradayExitReason.TARGET
                    if abs(exit_price - order.initial_target) <= abs(exit_price - order.initial_stop)
                    else IntradayExitReason.STOP)
        if order.initial_target is not None:
            return IntradayExitReason.TARGET
        if order.initial_stop is not None:
            return IntradayExitReason.STOP
        return IntradayExitReason.FORCED_FLATTEN

    def _aplica_entrada_e_saida_reconciliadas(
        self, conn, account: AccountState, order: EnterLimit, bar: Bar, resultado: dict,
    ) -> None:
        """A ordem-limite de entrada que a maquina vigiava preencheu E
        fechou por inteiro entre dois polls -- ver `_reconcilia_entrada_
        orfa`. Registra os DOIS eventos (abertura e fechamento) com os
        numeros REAIS que `MT5IntradayExecution.resolve_orphaned_entry` leu
        do historico de deals da corretora (NUNCA o nivel teorico da
        ordem -- gap medido ao vivo em 2026-09-04: o alvo era 5154,5000 e o
        deal real saiu a 5154,0000, 1 tick de deslize CONTRA o robo;
        gravar o alvo teorico teria registrado ficcao no diario).

        Reusa `_on_opened`/`_on_closed` (via `_apply`) para o resto do
        bookkeeping ser IDENTICO ao caminho normal -- Intent/Order/Fill,
        `live_positions`, debito/credito de caixa, contagem de trades. A
        unica coisa que este caminho faz por conta propria e' o que
        normalmente aconteceria DENTRO de `IntradaySessionMachine.
        _close_position` (que aqui nunca e' chamado, porque a posicao
        nunca chega a entrar em `self.machine.positions` -- ja fechou
        antes de qualquer coisa precisar vigia-la): somar o P&L real a
        `machine.realized_pnl`/`machine.session_pnl`, que e' o numero que
        o proximo teto por capital (`_cap_capital_atual`) le."""
        qty = int(resultado["entry_qty"])
        entry_price = float(resultado["entry_price"])
        exit_price = float(resultado["exit_price"])
        exit_qty = int(resultado["exit_qty"])
        reason = self._infere_motivo_saida(order, exit_price, resultado.get("exit_comment", ""))
        self._log(conn, account.id, "warn",
                  f"RECONCILIADO {self.strategy.symbol}: ordem {order.side} @ "
                  f"{order.limit_price:.4f} preencheu E fechou entre duas consultas "
                  f"a corretora -- entrada @ {entry_price:.4f}, saida ({reason.value}) "
                  f"@ {exit_price:.4f}, lido do historico de deals da corretora.",
                  {"side": order.side, "entry_price": entry_price, "exit_price": exit_price,
                   "quantity": qty, "exit_reason": reason.value,
                   "sessao": self._snapshot.session.isoformat()
                   if self._snapshot.session else None})

        abertura = PositionOpened(
            ts=bar.ts, side=order.side, price=entry_price, quantity=qty,
            stop=order.initial_stop, target=order.initial_target,
            order_kind="limit", reason=order.reason, bar=bar,
        )
        self._apply(conn, account, abertura, bar)

        cfg = self.machine.config
        trade = IntradayTrade(
            symbol=self.strategy.symbol,
            strategy_name=self.strategy.name,
            strategy_version=self.strategy.version,
            side=order.side,
            entry_ts=bar.ts,
            entry_price=entry_price,
            exit_ts=bar.ts,
            exit_price=exit_price,
            quantity=min(qty, exit_qty) if exit_qty else qty,
            exit_reason=reason,
            point_value_brl=cfg.costs.point_value_brl,
            capital_base=cfg.initial_capital,
            fees_total=fees_round_trip_brl(qty, entry_price, exit_price, cfg.costs),
            slippage_total=abs(exit_price - (order.initial_target
                                             if reason == IntradayExitReason.TARGET
                                             else order.initial_stop or exit_price))
                          * qty * cfg.costs.point_value_brl,
        )
        pnl = trade.pnl_brl
        self.machine.session_pnl += pnl
        self.machine.realized_pnl += pnl
        self._apply(conn, account, PositionClosed(trade=trade, pnl_brl=pnl), bar)

    def _aplica_eventos_parciais_antes_de_falhar(
        self, conn, account: AccountState, erro: Exception, bar: Bar,
    ) -> tuple[int, int]:
        """Journaliza (e torna DURAVEL, `_checkpoint`) o que `on_closed_bar`/
        `force_flatten` ja tinham acumulado em `events` ANTES de levantar
        `erro` -- ver `.partial_events` na docstring nova de
        `IntradaySessionMachine.on_closed_bar`/`force_flatten`.

        Risco residual do MEDIO 7 (auditoria adversarial 2026-08-28): dentro
        de UMA UNICA chamada de `on_closed_bar`, um fechamento REAL
        confirmado (passo 1 -- ex.: uma fatia de `_resolve_live_split_exit`
        que fecha a posicao so' PARCIALMENTE, sem orfanizar `resting_limit`
        porque a posicao continua aberta -- e' o caso real: `gremah`/
        `gremah_tick` com `dividir_entrada=True` declaram `split_quantities`
        E `exit_split_unit` na MESMA `EnterLimit`) pode ser seguido, na
        MESMA barra, por uma tentativa de resolver o(s) filho(s) restantes
        de uma entrada dividida que levanta `FALHA_ALTO` -- ou por
        `EntradaAMercadoNaoSuportada` no passo (3), depois de um `Exit`
        real ja confirmado no mesmo passo. Sem isto, a excecao subindo
        apagava o evento JA CONFIRMADO na corretora junto com o resto,
        porque `on_closed_bar` so' devolve `events` no `return` normal --
        uma excecao pula direto para quem chamou, sem passar por la.

        NUNCA mexe em `last_bar_ts`: esta barra continua NAO confirmada por
        inteiro (e' por isso que a excecao segue subindo logo depois, no
        caso `FALHA_ALTO`/`EntradaAMercadoNaoSuportada`) -- o proximo passo
        tem de reprocessa-la do zero. Isso e' seguro porque `self.machine`
        (o MESMO objeto em memoria, nunca reconstruido entre passos) ja
        reflete a mutacao real que aconteceu -- posicao encolhida,
        `exit_resting_qty` zerada -- e uma nova tentativa so' vai
        RE-CONSULTAR a corretora a partir desse estado, nunca repetir a
        fatia que ja preencheu (mesmo design de retry que ja existia antes
        desta correcao: `MT5IntradayExecution.limit_fill`/`exit_fill` sao
        consultas de DELTA contra o que a corretora reporta agora, nao
        replay de uma decisao velha).

        Devolve `(abertas, fechadas)` -- mesma contagem que o loop principal
        de `_consume` usa para o `detalhe` do `StepReport`, para quem chama
        poder somar os eventos parciais aos da barra em curso."""
        parciais = list(getattr(erro, "partial_events", None) or [])
        abertas = fechadas = 0
        for evento in parciais:
            if isinstance(evento, PositionOpened):
                abertas += 1
            elif isinstance(evento, PositionClosed):
                fechadas += 1
            self._apply(conn, account, evento, bar)
        if parciais:
            self._checkpoint(conn, account)
        return abertas, fechadas

    def _limite_de_atraso(self) -> float:
        """Idade maxima (segundos) que uma barra pode ter e ainda virar ORDEM
        NOVA na corretora, NESTE feed.

        `MAX_ATRASO_PARA_ORDEM_SEGUNDOS` mais o atraso ESTRUTURAL do feed
        (`nominal_delay_seconds`), que nao e' atraso de nada -- e' o formato
        do dado. Um teto fixo mataria o feed M1 por construcao: uma barra M1
        so' pode ser lida DEPOIS de fechar, e o `ts` dela e' a ABERTURA do
        minuto (`live/bar_feed.py`), entao toda barra M1 chega com >=60s de
        idade num robo perfeitamente saudavel. Somando: 120s para o feed de
        tick (`nominal_delay_seconds=0`), 180s para o M1 (60+120)."""
        estrutural = float(getattr(self.bar_feed, "nominal_delay_seconds", 0.0) or 0.0)
        return estrutural + MAX_ATRASO_PARA_ORDEM_SEGUNDOS

    def _journaliza_armes_de_barra_velha(self, conn, account: AccountState,
                                         session: date) -> None:
        """UMA linha de diario por LOTE em que algum arme de entrada foi
        recusado por barra velha -- mesmo padrao do bloco de `descartadas`
        (barra de pregao anterior), como o dono pediu.

        Nivel `warn`, nao `info`, e isso e' a parte que importa: um robo que
        para de mandar ordem EM SILENCIO e' exatamente o modo de falha do
        item 6.15 do `LICOES_DE_PRODUCAO.md` (a janela censurada que parece
        edge negativo e e' so' o robo calado). Se o feed cegar de novo, o
        dono ve na hora -- com a contagem e o tamanho do atraso -- em vez de
        descobrir no fim do dia que "o robo nao operou hoje".

        Uma linha por LOTE e nao por ordem: no pregao de 2026-09-08 seriam 45
        linhas (e 45 notificacoes) para dizer a mesma coisa uma vez."""
        if not self._armes_de_barra_velha:
            return
        self._log(conn, account.id, "warn",
                  f"{self._armes_de_barra_velha} ordem(ns) de entrada NAO "
                  f"enviada(s): barra velha (atraso ate' "
                  f"{self._atraso_max_barra_velha / 60.0:.0f} min, teto "
                  f"{self._limite_atraso_do_lote:.0f}s) -- o preco daquela "
                  f"barra ja' morreu. Ultima barra velha: "
                  f"{_hora_brt(self._ultima_barra_velha)}. Alvo, stop e "
                  "fechamento continuam valendo normalmente.",
                  {"armes_barra_velha": self._armes_de_barra_velha,
                   "atraso_max_segundos": round(self._atraso_max_barra_velha, 1),
                   "limite_atraso_segundos": round(self._limite_atraso_do_lote, 1),
                   "sessao": session.isoformat()})

    def _journaliza_recusas_por_cota(self, conn, account: AccountState,
                                     session: date) -> None:
        """UMA linha de diario por LOTE em que a COTA DE VAZAO recusou algum
        envio de entrada -- mesmo padrao (e mesmo motivo) de
        `_journaliza_armes_de_barra_velha`.

        Nivel `warn`, e essa e' a parte que nao pode ser negociada: o
        `notify_min_level` dos slots e' `warn`, entao o dono ve a recusa na
        hora. Robo que para de mandar ordem EM SILENCIO e' o modo de falha
        do item 6.15 do `LICOES_DE_PRODUCAO.md` -- e uma cota que recusa
        calada seria justamente isso, com o agravante de o robo continuar
        "verde" no painel.

        Uma linha por LOTE e nao por ordem: a recusa por cota nasce
        exatamente do caso em que ha MUITAS ordens no mesmo passo, entao uma
        linha por ordem seria a rajada de novo, agora no diario."""
        if not self._recusas_por_cota:
            return
        self._log(conn, account.id, "warn",
                  f"{self._recusas_por_cota} ordem(ns) de entrada NAO "
                  f"enviada(s): cota de vazao de {COTA_ENVIOS_POR_MINUTO} "
                  f"envios/60s atingida (pico no lote: "
                  f"{self._pico_de_envios_no_lote}). O robo SEGUE operando "
                  "-- alvo, stop, cancelamento e fechamento nao passam pela "
                  "cota, e o rearme volta na barra seguinte.",
                  {"recusas_por_cota": self._recusas_por_cota,
                   "pico_envios_60s": self._pico_de_envios_no_lote,
                   "cota": COTA_ENVIOS_POR_MINUTO,
                   "sessao": session.isoformat()})

    def _detalha_recusas_por_cota(self, detalhe: dict) -> None:
        """Acrescenta a contagem ao `detail` do `StepReport` (log do
        supervisor). Separado do journal pelo mesmo motivo de
        `_detalha_armes_de_barra_velha`: os dois pontos de saida ANTECIPADA
        de `_consume` tambem precisam da contagem."""
        if self._recusas_por_cota:
            detalhe["recusas_por_cota"] = self._recusas_por_cota
            detalhe["pico_envios_60s"] = self._pico_de_envios_no_lote

    def _detalha_armes_de_barra_velha(self, detalhe: dict) -> None:
        """Acrescenta a contagem ao `detail` do `StepReport` (o que vai para o
        log do supervisor). Separado do journal acima porque os dois pontos
        de saida ANTECIPADA de `_consume` (`daytrade_recusa_fechamento`,
        `daytrade_robo_incompativel`) tambem precisam da contagem -- e o de
        recusa de fechamento e' justamente o tipo de passo que dominou o
        pregao de 2026-09-08."""
        if self._armes_de_barra_velha:
            detalhe["armes_barra_velha"] = self._armes_de_barra_velha
            detalhe["atraso_max_segundos"] = round(self._atraso_max_barra_velha, 1)

    def _consume(self, conn, account: AccountState, session: date, barras: list[Bar],
                 now: datetime) -> StepReport:
        """Alimenta as barras na maquina, EM ORDEM, e journaliza os eventos.

        Barra carimbada num pregao ANTERIOR e' descartada (quem declara a
        regra e' a maquina, `is_previous_session_bar` -- aqui so' se aplica,
        regra 6 do AGENTS.md): o feed entrega tudo com `ts > last_bar_ts`, e
        essa marca atravessa a virada do pregao, entao uma barra atrasada de
        ontem chega como primeira barra de hoje. A MARCA AVANCA mesmo assim
        -- nao consumir a deixaria voltar em todo passo, para sempre.

        O descarte cobre tambem `_acumula_volume_no_nivel`: volume de ontem
        contado no nivel de uma ordem de hoje mediria penetracao que nunca
        aconteceu (ver `_penetration_ticks`).

        `on_closed_bar` pode levantar `BrokerExecutionError`. So' a
        variante `kind=FECHAMENTO_RECUSADO` (a corretora recusou uma ordem
        de SAIDA, mas a posicao continua exatamente como a maquina ja
        sabia) e' capturada AQUI -- qualquer outra (`FALHA_ALTO`: lado
        errado na corretora, sem conexao pra confirmar nada -- uma
        DIVERGENCIA de dado, nao uma recusa de ordem) e' RE-LEVANTADA, o
        comportamento de sempre (falhar alto e deixar o supervisor tentar
        de novo do zero, sem journalizar nada no meio do caminho -- ver
        `docstring` de `BrokerExecutionError.kind`).

        Gap (f), incidente 2026-08-28: ate aqui a excecao (de QUALQUER
        `kind`) subia sem ser capturada, e `store.live_journal` faz
        ROLLBACK em qualquer excecao -- ou seja, qualquer `_log`/journal
        que este passo tivesse escrito ANTES da recusa desaparecia junto, e
        a marca de barra (`last_bar_ts`) nunca avancava. Isso fazia o
        supervisor reprocessar a MESMA barra a cada ~5s (o passo dele),
        martelando a corretora contra a MESMA decisao repetidas vezes -- e'
        o padrao observado no incidente real (~24 recusas seguidas em poucos
        minutos). Para `FECHAMENTO_RECUSADO`, a excecao agora e' capturada
        AQUI: `_registra_falha_de_fechamento` grava o alerta (que sobrevive
        porque a transacao COMMITA no fim de `run_once`) e a marca avanca
        ate esta barra -- a posicao continua aberta NA MAQUINA
        (`_close_position` so' muta estado DEPOIS do envio confirmar, ver a
        docstring dela), entao a PROXIMA barra reavalia a condicao de saida
        do zero contra o preco novo, que e' retry de verdade, nao martelo
        cego.

        MEDIO 7 (auditoria adversarial 2026-08-28), variante do MESMO gap
        (f) que sobrava depois da correcao acima: `barras` pode trazer MAIS
        de uma barra fechada neste UNICO passo (loop do supervisor atrasado
        -- o feed entrega tudo que fechou desde o ultimo poll, nao 1 barra
        por chamada). Ordem real confirmada na barra 1 (ticket recebido em
        `_on_limit_placed`, ou um fechamento em `_on_closed` -- `exit_market`
        ja' rodou DENTRO de `on_closed_bar`, ver `machine._close_position`)
        e' jornalizada AQUI (`_apply`), mas so' virava fato duravel no fim de
        `run_once` -- se a barra 2 do MESMO lote levantasse `FALHA_ALTO`
        (comportamento correto, ver acima), o rollback do passo inteiro
        apagava tambem o `Intent`/`Order`/`Fill`/`live_positions` da barra 1,
        que ja' era dinheiro de verdade movido. `self._checkpoint(conn,
        account)` no fim de CADA barra fecha isso: comita a conexao deste
        PASSO (nao uma segunda conexao, ver a docstring de `_checkpoint`)
        assim que uma barra termina de ser aplicada, entao uma `FALHA_ALTO`
        de uma barra POSTERIOR do mesmo lote so' desfaz o que essa propria
        barra tinha escrito -- nunca as anteriores, ja' comitadas. A barra
        que de fato levanta `FALHA_ALTO` continua sem jornalizar NADA dela
        mesma (comportamento inalterado, ver acima) -- o que muda e' so' o
        destino das barras que ja' tinham terminado de aplicar ANTES dela.

        BARRA VELHA NAO VIRA ORDEM (2026-09-08)
        ---------------------------------------
        O mesmo lote de "mais de uma barra fechada neste UNICO passo" do
        MEDIO 7 tem uma segunda cara, e essa custou -R$116 num pregao. Se o
        lote e' grande porque o feed CEGOU (o terminal parou de entregar
        tick de WDO@ por 44,8 min e depois devolveu 13.644 barras num passo
        so' -- ver `MAX_ATRASO_PARA_ORDEM_SEGUNDOS`), cada barra desse lote
        e' um preco que ja' morreu, e ate' aqui cada uma podia virar uma
        ordem-limite REAL na corretora. Foram 45 delas, contra precos de
        ate' 45 min atras.

        A regra agora: **barra mais velha que `_limite_de_atraso()` continua
        sendo CONSUMIDA pela maquina -- indicador, ancora, contador,
        posicao, tudo fica quente -- mas nao gera ORDEM NOVA de entrada.**
        E' evento por evento, nao "pula a barra":

        * `LimitPlaced` (arme de entrada) -> NAO vai ao book. Tratado como
          "nao enviei" pelo caminho que ja' existia para a recusa por
          margem (`_descarta_arme_de_barra_velha` ->
          `machine.discard_resting_limit`), entao a maquina nao fica
          vigiando um fill impossivel e a estrategia rearma pelo criterio
          DELA na barra seguinte.
        * `LimitCancelled`, `PositionOpened`, `PositionClosed` (alvo, stop,
          flatten, fatia reconciliada) -> PASSAM, sempre. Nao sao decisao
          nova: sao a maquina constatando um FATO. Engolir um fechamento
          porque a barra estava velha criaria posicao fantasma -- exposicao
          real que o robo acha que nao tem -- que e' pior do que o problema
          que este portao resolve. Vale tambem para as saidas REAIS: elas
          fecham a MERCADO, no preco de AGORA, nunca no da barra velha.

        Isto NAO e' `live/` decidindo o que negociar (regra 6 do
        `AGENTS.md`). A decisao continua inteira da estrategia, que roda
        exatamente como no backtest sobre exatamente as mesmas barras. O
        que `live/` recusa e' EXECUTAR uma decisao cujo insumo a propria
        maquina ja' sabe obsoleto -- mesma familia da regra 7 ("ao vivo,
        decisao atrasada nao executa"), so' que na escala de barra em vez
        de pregao. Nada disso existe em `backtest/intraday/`, e nao deve
        existir: la' `bar.ts` E' o tempo, nenhuma barra e' velha e o
        caminho novo nunca dispara. Backtest e producao continuam
        descrevendo o MESMO robo em todo pregao em que o feed funciona."""
        abertas = fechadas = descartadas = 0
        ultima_descartada = None
        limite_atraso = self._limite_de_atraso()
        agora = pd.Timestamp(now)
        self._armes_de_barra_velha = 0
        self._atraso_max_barra_velha = 0.0
        self._ultima_barra_velha = None
        self._limite_atraso_do_lote = limite_atraso
        # Cota de vazao: contadores por LOTE (a janela rolante de 60s em si
        # e' de PROCESSO, `_envios_recentes`/`_tentativas_recentes`, e nao
        # pode ser zerada aqui -- ela atravessa passos por construcao).
        self._recusas_por_cota = 0
        self._pico_de_envios_no_lote = 0
        for bar in barras:
            if self.machine.is_previous_session_bar(bar.ts):
                descartadas += 1
                ultima_descartada = bar.ts
                self._snapshot.last_bar_ts = bar.ts
                continue
            # Idade DESTA barra contra o relogio de parede -- ver a secao
            # "BARRA VELHA NAO VIRA ORDEM" na docstring. Medida por barra e
            # nao pelo lote inteiro de proposito: num lote de recuperacao as
            # primeiras barras estao velhas e as ultimas ja' nao estao, e o
            # robo tem de voltar a operar exatamente na primeira que chega
            # dentro do prazo -- sem esperar o proximo passo.
            atraso = (agora - bar.ts).total_seconds()
            barra_velha = atraso > limite_atraso
            if barra_velha:
                self._atraso_max_barra_velha = max(self._atraso_max_barra_velha, atraso)
                self._ultima_barra_velha = bar.ts
            self._acumula_volume_no_nivel(bar)
            self._reconcilia_entrada_orfa(conn, account, bar)
            try:
                eventos = self.machine.on_closed_bar(bar)
            except BrokerExecutionError as erro:
                # MEDIO 7 (risco residual): aplica AGORA o que esta MESMA
                # chamada de `on_closed_bar` ja tinha confirmado de verdade
                # antes de levantar -- ver `_aplica_eventos_parciais_antes_
                # de_falhar`. Para `FALHA_ALTO` (kind != FECHAMENTO_RECUSADO,
                # abaixo), isto tem de acontecer ANTES do `raise`: depois
                # dele nunca mais se chega aqui.
                p_abertas, p_fechadas = self._aplica_eventos_parciais_antes_de_falhar(
                    conn, account, erro, bar)
                if erro.kind not in self._KINDS_QUE_REAVALIAM:
                    raise
                self._snapshot.last_bar_ts = bar.ts
                self._registra_espera_ou_falha(conn, account, session, erro)
                detalhe = {"barras": len(barras), "entradas": abertas + p_abertas,
                          "saidas": fechadas + p_fechadas,
                          "modo": self.execution_mode, "erro": str(erro)}
                if descartadas:
                    detalhe["descartadas"] = descartadas
                self._detalha_armes_de_barra_velha(detalhe)
                self._detalha_recusas_por_cota(detalhe)
                self._journaliza_armes_de_barra_velha(conn, account, session)
                self._journaliza_recusas_por_cota(conn, account, session)
                return StepReport("daytrade_recusa_fechamento", session, detail=detalhe)
            except EntradaAMercadoNaoSuportada as erro:
                # A estrategia pediu `Enter` a mercado, que nao tem caminho
                # de execucao real. Isto NAO e' um erro transitorio: e' um
                # robo que nunca vai conseguir operar neste modo, e a barra
                # seguinte vai levantar de novo. Sem esta captura o passo
                # inteiro subia,
                # o journal fazia ROLLBACK, `last_bar_ts` nao avancava e o
                # supervisor reprocessava a MESMA barra a cada ~5s pelo
                # pregao inteiro -- muito log, nenhuma informacao, e nada no
                # painel dizendo por que o robo nao opera.
                #
                # Agnostico de estrategia de proposito: qualquer robo que
                # emita uma acao nao suportada para aqui do mesmo jeito.
                #
                # MEDIO 7 (risco residual): um `Exit` real ja confirmado no
                # passo (3) da MESMA barra, antes de um `Enter` a mercado
                # (reversao) sem suporte estourar esta excecao, nao pode
                # desaparecer -- mesmo `_aplica_eventos_parciais_antes_de_
                # falhar` de cima.
                p_abertas, p_fechadas = self._aplica_eventos_parciais_antes_de_falhar(
                    conn, account, erro, bar)
                motivo = (
                    f"a estrategia pediu uma acao que a execucao real nao "
                    f"suporta: {erro}"
                )
                self._snapshot.last_bar_ts = bar.ts
                self._snapshot.disaster_halt = True
                self._snapshot.disaster_reason = motivo
                self._log(conn, account.id, "error",
                          f"ROBO INCOMPATIVEL com execucao real em "
                          f"{self.strategy.symbol}: {motivo}. Parei -- este robo "
                          "precisa de entrada por ordem-limite (maker) para operar "
                          "com dinheiro de verdade.",
                          {"sessao": session.isoformat(), "erro": str(erro)})
                detalhe = {"barras": len(barras), "entradas": abertas + p_abertas,
                           "saidas": fechadas + p_fechadas, "modo": self.execution_mode,
                           "erro": str(erro)}
                self._detalha_armes_de_barra_velha(detalhe)
                self._detalha_recusas_por_cota(detalhe)
                self._journaliza_armes_de_barra_velha(conn, account, session)
                self._journaliza_recusas_por_cota(conn, account, session)
                return StepReport("daytrade_robo_incompativel", session, detail=detalhe)
            for evento in eventos:
                if isinstance(evento, PositionOpened):
                    abertas += 1
                elif isinstance(evento, PositionClosed):
                    fechadas += 1
                self._apply(conn, account, evento, bar, barra_velha=barra_velha)
            self._drena_orfas_de_saida(conn, account, bar.ts)
            self._snapshot.last_bar_ts = bar.ts
            # CHECKPOINT (MEDIO 7, ver a docstring acima): esta barra
            # terminou de aplicar -- torna durAvel AGORA o que ela
            # jornalizou, antes de a PROXIMA barra do lote poder levantar
            # `FALHA_ALTO` e desfazer so' o rollback dela.
            self._checkpoint(conn, account)
        if descartadas:
            # Uma linha por LOTE descartado, nao por barra: sao 1 ou 2 por
            # pregao no caso normal (a cauda de ontem), e o dono pediu que o
            # historico registre o que o robo faz -- inclusive o que ele
            # deliberadamente ignorou.
            self._log(conn, account.id, "info",
                      f"{descartadas} barra(s) de pregao anterior descartada(s) "
                      f"(ultima: {_hora_brt(ultima_descartada)})",
                      {"descartadas": descartadas, "sessao": session.isoformat()})
        self._sincroniza_espelho_da_posicao(conn, account)
        self._journaliza_armes_de_barra_velha(conn, account, session)
        self._journaliza_recusas_por_cota(conn, account, session)
        detalhe = {"barras": len(barras), "entradas": abertas, "saidas": fechadas,
                   "modo": self.execution_mode}
        if descartadas:
            detalhe["descartadas"] = descartadas
        self._detalha_armes_de_barra_velha(detalhe)
        self._detalha_recusas_por_cota(detalhe)
        return StepReport("daytrade", session, detail=detalhe)

    # ---------- journal + execucao ------------------------------------------

    def _apply(self, conn, account: AccountState, evento, bar: Bar,
               *, barra_velha: bool = False) -> None:
        """Despacha UM evento da maquina para o lado real/diario.

        `barra_velha` chega so' do loop de `_consume` (ver a secao "BARRA
        VELHA NAO VIRA ORDEM" na docstring dele) e muda o destino de UM
        unico tipo de evento, `LimitPlaced` -- exposicao NOVA, decidida
        contra um preco que ja' morreu. Todos os outros seguem o caminho de
        sempre por decisao explicita: `LimitCancelled`, `PositionOpened` e
        `PositionClosed` nao sao decisao, sao constatacao de fato, e
        suprimi-los produziria posicao fantasma. Os dois outros chamadores
        (`_handle_gap` e `_aplica_eventos_parciais_antes_de_falhar`) usam o
        default `False`: o primeiro so' aplica o que `force_flatten` gerou
        (fechamento, nunca arme), e o segundo aplica o que a corretora JA
        confirmou -- em nenhum dos dois existe ordem nova a barrar."""
        if isinstance(evento, LimitPlaced):
            self._on_limit_placed(conn, account, evento, barra_velha=barra_velha)
        elif isinstance(evento, LimitCancelled):
            self._on_limit_cancelled(conn, account, evento)
        elif isinstance(evento, PositionOpened):
            self._on_opened(conn, account, evento)
        elif isinstance(evento, PositionClosed):
            self._on_closed(conn, account, evento, bar)

    def _descarta_arme_de_barra_velha(self, conn, account: AccountState,
                                      evento: LimitPlaced) -> None:
        """A maquina armou uma entrada numa barra VELHA: nao vai ao book.

        Mesmo desfecho de `_recusa_por_margem` -- "a maquina ja' gravou
        `resting_limit` e ficaria esperando um fill impossivel" -- e pelo
        mesmo mecanismo (`machine.discard_resting_limit`, que esquece a
        ordem SEM emitir `LimitCancelled`, porque ela nunca chegou ao book).
        Sem esse esquecimento o robo ficaria vigiando para sempre um nivel
        que nao existe na corretora: silencio, que e' o modo de falha que
        este projeto ja' pagou (item 6.15 do `LICOES_DE_PRODUCAO.md`).

        O que NAO e' igual a uma recusa por margem: aqui nao ha' `_log` de
        `error` por ordem. No pregao de 2026-09-08 isto teria escrito 45
        linhas de erro (e 45 notificacoes) para dizer uma coisa so'. A
        contagem sai numa linha unica por lote, em
        `_journaliza_armes_de_barra_velha`. Pelo mesmo motivo o numero de
        rodada (`trade_num`) NAO avanca: queimar 45 numeros num arme que
        nunca existiu tornaria o diario do dia ilegivel.

        A ordem REAL que estava em pe' ANTES do lote velho, essa sim, tem de
        MORRER -- e por isso o cancelamento continua acontecendo aqui.
        Cancelar nao e' "mandar ordem contra preco morto": e' TIRAR
        exposicao que a maquina deixou de vigiar. Deixa-la viva seria pior
        do que o bug original -- um ticket que ninguem acompanha, exatamente
        o que `_reconcilia_ordens_de_entrada` existe para impedir. Depois do
        primeiro descarte a maquina nao vigia mais nada, entao os arme(s)
        seguintes do mesmo lote nao tem predecessor real e nao cancelam nada.
        """
        self._armes_de_barra_velha += 1
        if self.executor is not None:
            if evento.replaced is not None:
                self._aplica_cancelamento(
                    conn, account,
                    self.executor.cancel_limit(evento.ts, reason="superseded"))
            elif self._snapshot.pending_entry_refs:
                self._aplica_cancelamento(
                    conn, account,
                    self.executor.cancel_stale_refs(
                        self._snapshot.pending_entry_refs, ts=evento.ts))
        self.machine.discard_resting_limit()

    def _recusa_por_cota_de_envio(self, excesso: ExcessoDeCadencia) -> None:
        """A COTA DE VAZAO recusou este envio: nada vai ao book, e o robo
        segue vivo.

        Mesmo desfecho de `_recusa_por_margem` e de
        `_descarta_arme_de_barra_velha` -- a maquina ja gravou
        `resting_limit` e ficaria vigiando um fill impossivel, entao
        `machine.discard_resting_limit()` e' obrigatorio aqui. Nao e'
        detalhe: foi exatamente esse esquecimento que faltou na recusa de
        25/08/2026 e deixou o robo uma hora esperando uma ordem que nunca
        existiu na corretora (ver a docstring de
        `machine.discard_resting_limit`). Um SEGUNDO mecanismo para o mesmo
        problema seria pior que nenhum -- este e' o caminho unico.

        A ordem REAL que estava em pe' ANTES ja morreu: o cancelamento
        acontece no topo de `_on_limit_placed`, ANTES dos portoes. E' o que
        se quer -- cancelar TIRA exposicao e nunca e' barrado por cota (ver
        `_check_cadencia_de_ordens`). O robo termina o passo sem nada no
        book e sem nada sendo vigiado: estado consistente, do qual a
        estrategia rearma pelo criterio DELA.

        Sem `_log` por ordem, e sem queimar numero de rodada (`trade_num`),
        pelo mesmo motivo da barra velha: a recusa por cota nasce de um
        passo com MUITAS ordens, entao uma linha por ordem reproduziria a
        rajada dentro do diario. A contagem sai numa linha unica por lote,
        nivel `warn`, em `_journaliza_recusas_por_cota`."""
        self._recusas_por_cota += 1
        self._pico_de_envios_no_lote = max(self._pico_de_envios_no_lote,
                                           excesso.envios)
        self.machine.discard_resting_limit()

    def _on_limit_placed(self, conn, account: AccountState, evento: LimitPlaced,
                         *, barra_velha: bool = False) -> None:
        """Uma ordem-limite passou a ser vigiada.

        `barra_velha=True` (ver `_apply` e a secao "BARRA VELHA NAO VIRA
        ORDEM" em `_consume`) desvia TUDO daqui para
        `_descarta_arme_de_barra_velha`, antes de qualquer contador, numero
        de rodada, linha de diario ou envio: uma ordem decidida contra um
        preco de dezenas de minutos atras nao vira ordem nenhuma.

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
        if barra_velha:
            self._descarta_arme_de_barra_velha(conn, account, evento)
            return
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
        #
        # stop/alvo no PARENTESE (2026-09-03, pedido do dono): uma ordem-
        # limite pode ficar parada sem preencher por um bom tempo (ver o
        # caso do warm start abaixo) -- sem o nivel aqui, a UNICA forma de
        # saber onde o robo pretende proteger/realizar era esperar o fill.
        # Util pro dono decidir posicionar a MERCADO por conta propria se
        # achar que a limite nao vai preencher.
        self._log(conn, account.id, "info",
                  f"LIMITE {evento.order.side.upper()} #{numero:02d} "
                  f"{self._lotes_txt(qtd)} {self.strategy.symbol} "
                  f"@ {evento.order.limit_price:.4f}"
                  f"{self._bracket_txt(evento.order.initial_stop, evento.order.initial_target)}"
                  + (" (substitui)" if evento.replaced is not None else ""),
                  {"numero_ordem": numero, "side": evento.order.side, "quantity": qtd,
                   "tipo": "armada",
                   "limit_price": evento.order.limit_price,
                   "stop": evento.order.initial_stop,
                   "target": evento.order.initial_target,
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
        # A CONTA aguenta? Ultimo portao antes do book, e o unico que soma a
        # conta inteira (outros slots, posicao aberta do dono) -- ver
        # `_check_margem_da_conta`. Recusar uma entrada e' sempre melhor do
        # que abrir uma que a conta nao sustenta.
        #
        # Trava de margem ENTRE PROCESSOS (2026-09-03, item 3.13 do
        # LICOES_DE_PRODUCAO.md): todo slot de day trade compartilha a MESMA
        # margem fisica (mesmo login MT5), e ate aqui cada processo so'
        # conferia margem contra o PROPRIO estado -- dois processos podiam
        # ler a mesma `margin_free` otimista dentro da janela de latencia de
        # um envio e os dois mandarem ordem, reproduzindo o padrao do
        # incidente da Parte 0 (item 3.2) agora entre processos. A secao
        # critica (consultar margem + checar cadencia local + mandar ESTA
        # ordem) fica inteira dentro de `acquire_margin_gate` -- sem I/O de
        # diario, sem logica de estrategia -- e o resultado e' aplicado
        # (jornal, freio, snapshot) so' DEPOIS de soltar a trava, pra nao
        # segurar os outros slots por mais tempo que o necessario. Sem
        # `else` para `self.executor is None`: o `return` la' em cima (logo
        # apos o `_log` da linha LIMITE) ja garante que so' se chega aqui
        # com executor de verdade -- modo sombra nunca manda nada, entao
        # nunca entra na trava.
        sem_margem: Optional[str] = None
        excesso: Optional[ExcessoDeCadencia] = None
        enviadas = None
        erro_envio: Optional[BrokerExecutionError] = None
        erro_trava: Optional[MargemTravada] = None
        try:
            with acquire_margin_gate():
                sem_margem = self._check_margem_da_conta(
                    evento.order.side, qtd, evento.order.limit_price)
                if sem_margem is None:
                    # Laco de envio -- ver `_check_cadencia_de_ordens`. Vem
                    # DEPOIS da margem de proposito: gastar uma vaga da
                    # janela numa ordem que a conta nem comporta seria
                    # contar o que nao aconteceu. Fica dentro da trava
                    # porque e' checagem local em memoria (sem I/O) --
                    # solta-la so' para pega-la de volta duas linhas depois
                    # nao reduziria o tempo segurado.
                    # RELOGIO DE PAREDE, nao `evento.ts` -- ver a
                    # docstring de `_check_cadencia_de_ordens`
                    # (pregao de 2026-09-08: 45 envios em 13s de
                    # parede passaram batido porque o carimbo do
                    # tick dizia que eram 7,5 minutos).
                    excesso = self._check_cadencia_de_ordens(
                        datetime.now(timezone.utc))
                    if excesso is None:
                        # Um filho REAL por elemento de
                        # `EnterLimit.split_quantities` (ver a docstring de
                        # `EnterLimit.children` e a Fase 2 em
                        # `live/intraday_execution.py`) -- `[quantity]`
                        # quando a ordem nao veio dividida, o comportamento
                        # de sempre.
                        try:
                            enviadas = self.executor.place_limit(
                                side=evento.order.side,
                                limit_price=evento.order.limit_price,
                                quantities=evento.order.children(self.config.default_quantity),
                                ts=evento.ts,
                                # Protecao ATOMICA: o stop e o alvo que a
                                # estrategia declarou nesta `EnterLimit`
                                # viajam no MESMO request que registra a
                                # ordem na corretora, entao a posicao nasce
                                # protegida no instante do fill -- sem
                                # janela, sem depender deste processo estar
                                # vivo. `_ensure_protecao` continua rodando,
                                # agora como REDE (protecao que sumiu, stop
                                # movido depois), nao como o caminho
                                # principal. Ver `MT5Broker.place_pending`.
                                stop=evento.order.initial_stop,
                                target=self._alvo_atomico(evento.order),
                            )
                        except BrokerExecutionError as erro:
                            erro_envio = erro
        except MargemTravada as erro:
            erro_trava = erro
        if erro_trava is not None:
            # Nao consegui verificar a margem com seguranca (outro processo
            # segurava a trava alem do timeout) -- tratado como consulta que
            # FALHOU (item 1.6 do LICOES_DE_PRODUCAO.md: "nao sei" nunca
            # autoriza), nunca como recusa por margem insuficiente de
            # verdade (por isso NAO passa por `_margem_alarmada`/
            # `_recusa_por_margem`, que sao especificos desse outro caso).
            # Mesmo desfecho de uma recusa da corretora: desfaz a vigilancia
            # e o robo re-arma pelo proprio criterio no proximo ciclo.
            self._recusa_de_envio(
                conn, account, self._snapshot.session, numero,
                BrokerExecutionError(
                    f"nao enviei: trava de margem entre processos ocupada -- {erro_trava}",
                    orphan_refs=[]))
            return
        if sem_margem is not None:
            if sem_margem not in self._margem_alarmada:
                self._margem_alarmada.add(sem_margem)
            self._recusa_por_margem(conn, account, self._snapshot.session,
                                    numero, sem_margem)
            return
        if excesso is not None and excesso.patologia:
            # DISJUNTOR. So' este ramo derruba o robo -- ver os dois tetos em
            # `COTA_ENVIOS_POR_MINUTO`/`MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO`.
            self._snapshot.disaster_halt = True
            self._snapshot.disaster_reason = excesso.motivo
            self._log(conn, account.id, "error",
                      f"FREIO DE CADENCIA em {self.strategy.symbol}: "
                      f"{excesso.motivo}. Parei de mandar ordem.",
                      {"sessao": self._snapshot.session.isoformat(),
                       "numero_ordem": numero,
                       "tentativas_60s": excesso.tentativas,
                       "envios_60s": excesso.envios})
            self.machine.discard_resting_limit()
            return
        if excesso is not None:
            # VAZAO. Recusa SO' esta ordem e segue -- o robo continua vivo.
            self._recusa_por_cota_de_envio(excesso)
            return
        if erro_envio is not None:
            self._recusa_de_envio(conn, account, self._snapshot.session, numero, erro_envio)
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

    def _custo_posicao(self, price: float, quantity: int) -> float:
        """Quanto comprometer/liberar em CAIXA ao abrir/fechar `quantity`
        unidades a `price` -- mesma ramificacao MARGEM-vs-PRECO ja corrigida
        em `_check_capital` (2026-08-28), agora tambem aqui.

        `evento.price` de um futuro (WIN@/WDO@) vem em PONTOS do indice/dolar,
        nao em reais por unidade -- `preco x quantidade` da' o valor NOCIONAL
        cheio (~R$180.000 pra' 1 WIN@ a 180 mil pontos), nao o que a corretora
        de fato reserva (~R$100 WIN@/R$150 WDO@, a MARGEM). Sem ramificar, um
        robo de futuro debita/credita esse nocional inteiro do caixa numa
        entrada so', explicando um caixa como "-R$180.455,00" com 1 contrato
        aberto (achado do dono, 2026-08-31). `self.machine.config` e' a MESMA
        config que a maquina usa pra' gatear quantos contratos cabem
        (`_cabe_no_teto`/`_cap_capital_atual`), entao este numero nunca
        diverge do que o proprio motor considera "margem por contrato"."""
        margem = self.machine.config.margin_per_contract_brl
        return margem * quantity if margem is not None else price * quantity

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

        custo = self._custo_posicao(evento.price, evento.quantity)
        pos = LivePosition(
            ticker=self.strategy.symbol, quantity=assinado, entry_date=evento.ts.date(),
            entry_price=evento.price, capital_allocated=abs(custo),
            unit_value_brl=self.machine.config.margin_per_contract_brl,
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
        # `custo` ja' e' MARGEM para futuro, preco cheio para acao -- ver
        # `_custo_posicao`.
        if self.execution_mode == "shadow":
            account.cash_sombra -= custo
        else:
            account.cash -= custo

        # O nivel PEDIDO, para `_on_closed` poder comparar com o EXECUTADO
        # (item 4.8: 8 de 8 alvos nativos sairam pior que o nivel em
        # 2026-09-08, e nada media isso).
        self._alvo_declarado = evento.target
        self._abertura_wall = datetime.now(timezone.utc)

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
            capital_allocated=abs(self._custo_posicao(pos_total.entry_price, pos_total.quantity)),
            unit_value_brl=self.machine.config.margin_per_contract_brl,
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
        custo = self._custo_posicao(evento.price, evento.quantity)
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
        # Gap (f): um fechamento (total OU parcial, ver o desvio logo
        # abaixo) que DA CERTO zera a contagem de recusas seguidas -- ela
        # existe pra' pegar uma sequencia estrutural de recusa (margem,
        # protecao, autotrading), nao pra' penalizar para sempre um robo que
        # teve UMA recusa isolada e depois seguiu fechando normalmente.
        self._snapshot.close_refusal_count = 0
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

        # O stop VIGENTE no instante do fechamento -- lido ANTES de apagar a
        # posicao, porque ele nao esta' em `trade` (que so' carrega entrada e
        # saida) e a lista de posicoes do painel precisa dele na linha da
        # rodada. Nao e' o stop da ENTRADA: desde 2026-09-09 ele reancora no
        # fill REAL, entao o numero logado na entrada pode ja' nao ser o que
        # valia aqui.
        pos_fechada = account.positions.get(self.strategy.symbol)
        stop_no_fecho = None if pos_fechada is None else pos_fechada.current_stop
        store.delete_position(conn, account.id, self.strategy.symbol)
        account.positions.pop(self.strategy.symbol, None)
        self._open_intent_id = None
        self._snapshot.trades += 1

        # Devolve o capital que `_on_opened`/`_on_opened_top_up` debitaram
        # (`trade.entry_price` ja e' o preco medio da posicao inteira, o
        # MESMO usado em `capital_allocated` -- multiplicado pela quantidade
        # que fecha AQUI, e' exatamente o que foi comprometido por ela) mais
        # o resultado realizado. `_custo_posicao` ja' ramifica margem/preco
        # cheio -- tem de ser a MESMA formula usada para debitar, senao o
        # caixa nao fecha (sobra ou falta capital "fantasma" a cada trade).
        liberado = self._custo_posicao(trade.entry_price, trade.quantity)
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
        # `exit_detail="wall_clock_floor"` (2026-09-15, ver `IntradaySessionMachine.
        # force_flatten_by_wall_clock`) marca um FLATTEN sem barra nenhuma
        # depois do corte -- preco de execucao em sombra e' uma APROXIMACAO
        # (ultimo close conhecido), nao o fechamento real da barra. Sem isto
        # distinguido AQUI, na linha que fica no ledger para sempre, so' a
        # linha avulsa de `_aplicar_piso_de_relogio` (que nao entra na
        # tabela de trades) contaria a diferenca -- e o proximo agente que
        # ler o extrato veria "FLATTEN" igual a qualquer outro dia.
        if trade.exit_detail == "wall_clock_floor":
            motivo = f"{motivo} (PISO RELOGIO)"
        # TEMPO DE VIDA e DESLIZE CONTRA O NIVEL PEDIDO -- as duas medidas
        # que faltavam no diario em 2026-09-08 e sem as quais 10 round-trips
        # de menos de 1s e 8 alvos deslizados passaram como "target" normal.
        duracao_s = (trade.exit_ts - trade.entry_ts).total_seconds()
        duracao_parede_s = (
            None if self._abertura_wall is None
            else round((datetime.now(timezone.utc) - self._abertura_wall).total_seconds(), 3))
        self._abertura_wall = None
        # O relogio da CORRETORA (`time_msc` dos deals) -- o unico que mede a
        # vida da posicao sem a defasagem do feed nem o colapso do poll. So'
        # existe em execucao REAL; em sombra/backtest nao ha deal de
        # corretora e o campo fica `None`. Observacao pura, nunca decisao
        # (AGENTS.md regra 6) -- ver `MT5IntradayExecution.vida_da_posicao_ms`
        # para os numeros de 2026-09-08 que justificaram plumbar isto.
        duracao_corretora_ms = (
            None if self.executor is None else self.executor.vida_da_posicao_ms())
        alvo = self._alvo_declarado
        self._alvo_declarado = None
        deslize = None
        # SO' faz sentido contra uma saida por ALVO (2026-09-09). Ate' aqui a
        # conta rodava para QUALQUER motivo de saida, e como o campo se chama
        # "deslize" e vira `warn`, todo trade STOPADO acusava um deslize
        # gigante e falso: medido ao vivo neste dia, um short de entrada
        # 5107,50 / alvo 5106,50 fechou no stop a 5116,00 e o diario gritou
        # "DESLIZE DE SAIDA -- R$ +95,00", que e' so' a distancia normal entre
        # o stop e o alvo, nao execucao ruim.
        #
        # Nao e' ruido inofensivo: este alarme e' o UNICO jeito de descobrir
        # que o alvo fatiado estourou `exit_ttl_bars` e saiu a MERCADO (o
        # motor registra esse caso como `exit_reason=TARGET` do mesmo jeito --
        # ver `machine._resolve_live_split_exit`). Um alarme que dispara em
        # todo stop soterra exatamente o evento que ele existe para achar.
        #
        # O deslize do STOP e' outra medicao, contra o nivel do STOP, e tem
        # constante propria (`IntradayCostModel.slippage_ticks`) -- nao se
        # empilha com esta (ver a secao do deslize em CLAUDE.md).
        if alvo is not None and trade.exit_reason == IntradayExitReason.TARGET:
            faltou = ((alvo - trade.exit_price) if trade.side == "long"
                      else (trade.exit_price - alvo))
            deslize = round(faltou * trade.point_value_brl * trade.quantity, 4)
        self._log(conn, account.id, "info",
                  f"{motivo} {trade.side.upper()} #{numero:02d} "
                  f"{self._lotes_txt(trade.quantity)} {self.strategy.symbol} "
                  f"@ {trade.exit_price:.4f} - R$ {evento.pnl_brl:+.2f}",
                  {"numero_ordem": numero, "side": trade.side,
                   "exit_reason": trade.exit_reason.value,
                   "exit_detail": trade.exit_detail,
                   "pnl_brl": round(evento.pnl_brl, 4), "entry_price": trade.entry_price,
                   "exit_price": trade.exit_price, "execution_mode": self.execution_mode,
                   "assinado_saida": assinado_saida,
                   # QUANTIDADE que saiu e STOP vigente no fecho: sem os dois
                   # a lista de posicoes do painel nao consegue reconstruir a
                   # rodada (quanto fechou, contra que nivel) --
                   # `journal.live_store.daytrade_position_history`.
                   "quantity": trade.quantity, "stop": stop_no_fecho,
                   # Os campos que faltavam para o diario denunciar execucao
                   # ruim sozinho (2026-09-08) -- ver `DURACAO_MINIMA_DE_TRADE_S`
                   # e os itens 4.8/4.16. `duracao_corretora_ms` e' o unico dos
                   # tres relogios que mede a vida REAL da posicao; os outros
                   # dois ficam por serem os que existem tambem em sombra.
                   "duracao_s": duracao_s,
                   "duracao_parede_s": duracao_parede_s,
                   "duracao_corretora_ms": duracao_corretora_ms,
                   "alvo_declarado": alvo,
                   "deslize_vs_alvo_brl": deslize,
                   "sessao": self._snapshot.session.isoformat()})
        if deslize is not None and deslize > 0:
            self._log(conn, account.id, "warn",
                      f"DESLIZE DE SAIDA em {self.strategy.symbol}: alvo pedido "
                      f"{alvo:.4f}, executado {trade.exit_price:.4f} -- R$ "
                      f"{deslize:+.2f} a menos do que o nivel pagaria (item 4.8).",
                      {"sessao": self._snapshot.session.isoformat(),
                       "numero_ordem": numero, "alvo_declarado": alvo,
                       "exit_price": trade.exit_price,
                       "deslize_vs_alvo_brl": deslize})

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
            capital_allocated=abs(self._custo_posicao(pos_total.entry_price, pos_total.quantity)),
            unit_value_brl=self.machine.config.margin_per_contract_brl,
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
        liberado = self._custo_posicao(trade.entry_price, trade.quantity)
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
                   # Mesmos campos que `_on_closed` grava, pelo mesmo motivo
                   # (`daytrade_position_history`): uma rodada que sai FATIADA
                   # so' e' reconstruivel se cada fatia disser preco e
                   # quantidade dela. `quantidade_restante` continua sendo o
                   # que distingue fatia de fechamento final.
                   "quantity": trade.quantity, "entry_price": trade.entry_price,
                   "exit_price": trade.exit_price, "stop": pos_total.current_stop,
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
            # Historico de RODADAS (posicao aberta -> fechada), nao so' o que
            # esta' aberto agora: o cartao "Posicoes" do painel mostrava
            # `account.positions`, entao toda posicao que fechava sumia da
            # tela (queixa do dono, 2026-09-09). O teto e' o mesmo do "ver
            # mais" do cartao (`app.py::OPS_PAGINA_MAX`) -- reconstruir 500
            # rodadas de payload e' barato, mandar o pregao inteiro de um robo
            # de alta cadencia pro Jinja nao seria.
            historico = store.daytrade_position_history(conn, account.id, limit=500)

        resultado = self._resultado_dia_e_acumulado(saidas, session.isoformat(), account.initial_capital)
        ordens_stats = self._ordens_por_lado(ordens_hoje, self.machine.config.margin_per_contract_brl)

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

        # A rodada ainda ABERTA no historico E' a posicao de agora -- stop,
        # alvo e quantidade dela tem de sair da conta/maquina, nao do que o
        # diario registrou na ENTRADA: o stop reancora no fill real (commit
        # 2529e38) e o alvo pode ter sido reposicionado. Sem isto a MESMA
        # posicao apareceria com dois numeros diferentes em dois cartoes da
        # mesma tela, e o cartao errado seria o que o dono le' primeiro.
        # So' a mais recente e' candidata: uma rodada antiga sem saida no
        # diario (processo morto no meio) fica marcada aberta de proposito --
        # e' um fato do log, e apaga-lo esconderia justamente a anomalia.
        viva = account.positions.get(self.strategy.symbol)
        if viva is not None:
            if not any(r["aberta"] for r in historico):
                # Posicao aberta que o diario NAO explica: entrada gravada por
                # uma versao anterior, conta adotada da corretora, ou o evento
                # perdido num restart. A verdade do que esta' aberto e'
                # `live_positions`, nunca o log -- entao ela entra na lista
                # como rodada sem numero em vez de sumir da tela, que era o
                # sintoma exato que esta reforma existe pra corrigir.
                historico.insert(0, {
                    "sessao": viva.entry_date.isoformat(), "numero": None,
                    "lado": viva.metadata.get("side")
                            or ("long" if viva.quantity >= 0 else "short"),
                    "qtd": 0, "entrada": None, "alvo": viva.metadata.get("target"),
                    "stop": None, "saida": None, "motivo": None, "pnl_brl": None,
                    "duracao_s": None, "fatias": 0, "aberta": True, "valor": None,
                    "hora_entrada": None, "hora_saida": None,
                })
            for r in historico:
                if not r["aberta"]:
                    continue
                r["qtd"] = abs(viva.quantity)
                r["entrada"] = round(viva.entry_price, 4)
                r["stop"] = viva.current_stop
                # Capital COMPROMETIDO agora (margem no futuro, preco cheio na
                # acao) -- so' faz sentido enquanto a rodada esta' aberta: ao
                # fechar, `_on_closed` devolve tudo pro caixa. `market_value`
                # e' sempre POSITIVO, inclusive em short: `quantity` negativa
                # marca o lado, nao o sinal do valor (bug de 2026-08-31, um
                # short recem-aberto aparecia como "R$ -100,00" na tabela).
                r["valor"] = round(viva.market_value(viva.entry_price), 2)
                alvo_vivo = _unanime(p.current_target for p in posicoes)
                if alvo_vivo is not None:
                    r["alvo"] = alvo_vivo
                break
        return {
            "conta": account.name,
            "existe": True,
            "modo": account.mode,
            "kind": "intraday",
            "robo_investimento": account.investment_robot,
            "robo_saque": "",
            "pregao": session.isoformat(),
            # Fase DO INSTRUMENTO, nao a do pregao de acao (2026-09-08): com
            # `clock.phase()` cru o painel mostrava "fechado" das 09:00 as
            # 10:00 e a partir das 17:00 enquanto o robo de futuro estava
            # operando -- painel que contradiz o robo e' pior que painel
            # nenhum. Mesma funcao que gateia `run_once`, para os dois nao
            # poderem divergir.
            "fase": self._fase_do_instrumento(datetime.now(timezone.utc)).value,
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
            # Lista COMPLETA de rodadas (abertas e fechadas), da mais recente
            # pra tras -- ver `store.daytrade_position_history`. `posicoes`
            # acima continua sendo so' o que esta' aberto agora, porque e' de
            # onde saem "Investido a mercado" e `equity()`.
            "posicoes_historico": historico,
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
                # `_custo_posicao` ramifica margem/preço cheio (achado do
                # dono, 2026-08-31): sem isto, 1 contrato de WIN@/WDO@ (preço
                # em PONTOS, não R$) aparecia como um nocional de ~R$180 mil.
                "valor_posicoes_compra": round(
                    sum(self._custo_posicao(p.entry_price, p.quantity)
                        for p in posicoes if p.side == "long"), 2),
                "valor_posicoes_venda": round(
                    sum(self._custo_posicao(p.entry_price, p.quantity)
                        for p in posicoes if p.side == "short"), 2),
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
                # So' o ultimo persistido -- ao contrario de `ordem_em_pe`,
                # nao ha' como recalcular isto na hora sem consultar a
                # corretora de novo (`_check_atividade_estranha` so' roda
                # dentro de `run_once`, nunca aqui). `None` na maior parte
                # do tempo (nada de estranho pra' relatar).
                "atividade_estranha": self._snapshot.atividade_estranha,
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
                # 2019).
                #
                # 2026-09-08: o ramo "fixed" devolvia `session_end_time` CRU,
                # com o comentario de que ali o campo estaria "em hora local".
                # Nao esta -- `profiles.py` diz, no proprio `_futures_profile`,
                # "`session_end_time` em UTC, como todo perfil deste modulo".
                # O painel exibia entao "FLATTEN 21:30 BRT" para o WDO@, que e'
                # 18:30 em Brasilia: numero UTC com rotulo BRT, a MESMA familia
                # de erro que ja custou uma base de tick inteira neste projeto
                # (itens 5.x de LICOES_DE_PRODUCAO.md). Converte-se de verdade.
                # 2026-09-14: os dois ramos viravam UM so'. O de acao mostrava
                # `continuous_end` (o FIM DO PREGAO) enquanto o motor achatava
                # 1min antes, e o de futuro so' funcionava porque corte e fim
                # eram o mesmo numero -- o que era, ele proprio, o bug do item
                # 4.28. Agora o corte e' sempre ANTES do fim (folga de
                # `FOLGA_ACHATAMENTO_MINUTOS`), entao mostrar o fim do pregao no
                # campo "Flatten" seria mentir em ate' 5 minutos nos dois lados.
                # Fonte unica: o MESMO valor que o motor compara, so' convertido.
                "corte_flatten_brt": _utc_time_para_brt(
                    self.machine.session_end_time_for(pd.Timestamp(session))
                ).strftime("%H:%M"),
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
                # Freio duro (gap e/f, incidente 2026-08-28) -- estado
                # visivel pro painel sem tocar na corretora (lido do
                # snapshot persistido, mesmo padrao de `capital_alarme`).
                "freio_duro": self._snapshot.disaster_halt,
                "freio_duro_motivo": self._snapshot.disaster_reason,
                "recusas_fechamento_seguidas": self._snapshot.close_refusal_count,
            },
        }
