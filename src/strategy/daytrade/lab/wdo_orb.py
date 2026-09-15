"""ORB (Opening Range Breakout) do WDO@, no desenho de execucao FECHADO.

Rompimento da faixa dos primeiros `range_minutos` do pregao, ATE' DUAS
operacoes por pregao no default (a original, mais 1 fade do rompimento
oposto -- ver `fade_rompimento_oposto` e `max_fades_por_dia`, que aceita um
teto maior se algum dia isso for decidido de novo com medicao ao lado),
geometria tirada do proprio tamanho da faixa, com o stop travado em no
maximo 30 ticks (ver `stop_max_ticks`).
Todo o resto e' execucao -- e neste robo a execucao NAO e' detalhe: ela
responde por praticamente todo o resultado.

O numero, medido no IS congelado (72 pregoes, capital real R$375, fila
438/489 de `fidelidade.py`, entrada e alvo por ordem-limite):

    ==================================================================
    desenho                       trades  win%    BE emp   R$/op  liquido
    ------------------------------------------------------------------
    corte de tempo a MERCADO          58  51,72%  45,10%  +15,71  +911,00
    corte por ordem-LIMITE            58  56,90%  48,09%  +21,31  +1.236,00
    + aviso de ordem morta por prazo  72  56,94%  47,74%  +22,90  +1.649,00
    ==================================================================

+81% de liquido SEM tocar em um unico parametro de estrategia -- mesma
faixa, mesmo offset, mesmo alvo, mesmo stop. O que mudou foi (1) parar de
fechar a mercado quando o relogio bate e (2) o robo passar a SABER que a
ordem de entrada dele morreu. Ver `saida_limite_minutos` e
`on_order_expired`.

O QUE ESTE ROBO NAO E' (2026-09-10 -- SUPERADO em 2026-09-11, ver abaixo): o
veredito estatistico do robo SEM o fade era INDEFINIDO. Win 56,94% com IC95%
[45,4 ; 67,7] contra breakeven empirico de 47,74% -- o breakeven caia DENTRO
do intervalo.

O FADE DO ROMPIMENTO OPOSTO (2026-09-11, ver `fade_rompimento_oposto`) e' o
que mudou isso. Depois que a operacao do dia fecha, um rompimento da faixa
ORIGINAL para o lado CONTRARIO ao primeiro dispara uma SEGUNDA entrada,
apostando na volta pra dentro da faixa -- dia com dois rompimentos opostos
e' dia indeciso, e dia indeciso volta ao meio. Medido no IS (72 pregoes): o
fade sozinho adiciona 31 operacoes, win 67,74%, R$/op +38,53 -- melhor que o
robo original (+22,90) -- e leva o robo INTEIRO (103 operacoes) a IC95%
[50,5 ; 69,1] contra breakeven 48,58%: **primeira vez que o limite inferior
passa acima do breakeven.** CONFIRMADO no OOS (51 pregoes, teste as cegas,
nunca visto antes de 2026-09-11): as 28 operacoes que o fade adiciona la'
deram win 67,86%, R$/op +34,50, liquido +966,00 -- mesma direcao do IS, sem
nenhum ajuste entre as duas medicoes.

O TETO DO FADE SUBIU DE 1 PARA 3 (2026-09-11, ver `max_fades_por_dia`).
Medido nas duas janelas: teto 3 fica em 1o lugar nas duas (IS +3.055,50 e
OOS +839,00, contra +2.843,50 e +385,50 do teto 1). Soltar o teto de vez e'
PIOR que os dois (+2.399,50 no IS) -- o ganho nao e' "mais operacoes", e' um
teto especifico. A explicacao por ordem da chamada NAO e' estavel entre as
janelas e nao deve ser usada como justificativa; ver a nota do campo.

O QUE O OOS DIZ SOBRE A BASE -- e e' desconfortavel: **o rompimento da faixa
de abertura, sozinho, PERDE dinheiro na janela cega.** Base no OOS: 51
operacoes, win 47,06%, R$/op -11,38, liquido -580,50. No mesmo OOS os fades
dao +1.419,50 (61 operacoes, win 62,30%). Ou seja: fora da amostra, este nao
e' um robo de rompimento com um complemento de reversao -- e' um robo de
REVERSAO carregando um rompimento que nao se sustentou. O IS diz o contrario
(base +1.649,00), e e' justamente por isso que o OOS existe. Quem for mexer
na base tem de saber que esta' mexendo na perna fraca, nao na forte.

RISCO DE CAPITAL, achado no MESMO teste OOS: a caminhada REAL de caixa (a
sequencia cronologica de fato, nao a simulacao por-dia que reseta o
capital) travou com R$375 logo na 1a semana e meia da janela -- 6 de 79
operacoes chegaram a acontecer, caixa minimo R$117,00, e as outras 73
nunca teriam ocorrido de verdade. So' sobreviveu a janela OOS INTEIRA com
capital de R$500, e mesmo assim tocando um minimo de R$153,50 -- so' R$3,50
acima da margem de R$150. **R$375 (o piso de PARTIDA oficial do WDO@,
CLAUDE.md) nao e' capital suficiente para esta geometria sobreviver ao azar
COMUM, nao so' ao raro.** Ele esta em producao por decisao do dono, com 1
contrato, e o que decide e' o extrato -- nao esta tabela. Ver
LICOES_DE_PRODUCAO.md.

O TETO VOLTOU A 1 E O STOP FICOU MAIS CURTO (2026-09-11, ver `max_fades_por_
dia` e `stop_max_ticks`) -- o dono pediu explicitamente uma versao "ganhadora
mesmo que pouco, mas constante" depois de viver ao vivo o pior streak ja'
registrado nesta base (4 semanas seguidas negativas, ver a memoria do
projeto). Medido nos 123 pregoes (IS+OOS), 5 combinacoes de
`max_fades_por_dia` x `stop_max_ticks`:

    teto      stop    R$/op    liquido      trava (embaralhado, R$375)
    3         40      +14,92   +3.894,50    53,5%   <- o que rodava ate' aqui
    1         40      +17,74   +3.229,00    53,3%
    2         40      +16,55   +3.790,50    53,5%
    3         30      +14,19   +3.704,50    55,2%
    1         30      +18,18   +3.309,00    52,4%   <- NOVO default

`teto1+stop30` tem o MELHOR R$/operacao das 5 (nao o maior liquido -- esse
continua sendo o teto3, que tem mais trades) e a MENOR trava. A diferenca de
trava entre as 5 e' pequena (52,4% a 55,2% -- ver a nota honesta abaixo), mas
foi a UNICA alavanca testada que melhorou nas duas metricas ao mesmo tempo
sem piorar a terceira.

**Confirmado num caso real, fora do backtest:** simulando os 2 ultimos
pregoes de verdade antes desta promocao (2026-09-10 e 11), com caixa real
contínuo partindo de R$375, a geometria ANTIGA (teto3/stop40) fechava o
periodo em **CAIXA NEGATIVO (-R$2,50)** -- no mundo real isso e' um chamado
de margem. A geometria NOVA (teto1/stop30) fechava em **+R$68,00**, positiva.
Mesmos 2 pregoes, mesmo preco, so' a geometria mudou.

**A ressalva que nao pode sumir:** a trava (probabilidade de o caixa de
R$375 recusar operacao em algum ponto, embaralhando as mesmas operacoes
10.000 vezes) fica entre 52% e 55% em TODAS as 5 combinacoes -- reduzir o
teto do fade ou o teto do stop NAO resolve o travamento, so' o adia um
degrau. Isso e' estrutural a operar com R$375 e 1 contrato fixo, nao um
parametro de estrategia. Ver LICOES_DE_PRODUCAO.md e a memoria do projeto
`wdo_orb_teto1_stop30_producao_2026_09_11`.

O ALVO BAIXOU DE 2,0x PARA 1,5x O STOP (2026-09-14, ver `alvo_multiplo`).
Veio de uma investigacao que comecou pelo lado oposto: o dono achou que as 4
semanas de 17/08 a 11/09 mostravam "uma tendencia longa de perdas e outra de
ganhos" e queria saber quando cada uma comeca. Teste de sequencias
(Wald-Wolfowitz) sobre as 28 operacoes: 15 blocos observados contra 14,36
esperados por acaso, z=+0,26. NAO ha tendencia para prever -- as sequencias
longas que a vista percebe sao o que o acaso produz em 28 lances.

O que a mesma coleta mostrou, e virou esta mudanca: o alvo pedido era 53 ticks
em media, o vencedor andava 26 (MFE mediana) e so' 10,7% das operacoes
chegavam ao alvo -- 46,4% saiam pelo corte de relogio, com R$/op 8x menor.

Medido em 134 pregoes (IS 72 + OOS_LIMPO 43 + as 19 recentes), capital R$375
REPOSTO por pregao, `scripts/daytrade/wdo_orb_geometria_is_oos_2026_09_14.py`:

    multiplo   R$/op IS   R$/op OOS   pregoes+ IS   pregoes+ OOS
    1,0x         8,82        9,58        48,6          50,0
    1,25x       18,67        8,80        58,3          64,3
    1,5x        22,95       11,14        55,6          61,9   <- NOVO default
    2,0x        24,60        9,66        54,2          57,1   <- era isto
    2,5x        23,29       10,52        52,8          57,1

E CONFIRMADO por bootstrap emparelhado por PREGAO (5.000 reamostragens,
`wdo_orb_t15_robustez_2026_09_14.py`), que e' o teste que separa o achado do
sorteio:

    R$/op maior em          40,9% das reamostragens  (mediana -0,58)
    mais pregoes positivos: 95,0%                    (mediana +2,63pp)

**A leitura honesta: o 1,5x NAO ganha mais dinheiro.** Ganha com mais
frequencia, pelo mesmo dinheiro. Foi promovido porque e' exatamente o criterio
que o dono declarou -- "melhor ganhar pouco, mas ganhar sempre, do que ganhar
muito e devolver por mercado" -- e porque e' o UNICO eixo que sobreviveu ao
bootstrap em toda a rodada de 2026-09-14. No walk-forward mensal ele fez 3
vitorias, 4 empates e ZERO derrotas em pregoes positivos.

O que NAO passou nessa mesma rodada, para nao ser retentado sem motivo novo:
cortar o fade (ele e' a perna FORTE: +41,60/op no IS e +44,50 no OOS, contra
+17,28 e -8,60 do rompimento); filtrar a entrada por agitacao de mercado
(1 confirmacao em 8, com o sinal INVERTIDO nas janelas grandes); qualquer
preditor medido no instante do sinal (0 de 15 variaveis passam Benjamini-
Hochberg no IS, e nenhuma chega nem a p<0,05 sem correcao); operar so' vendido
(o fade short, a melhor perna, so' existe DEPOIS de um rompimento long --
cortar o long custa R$1.098,50); encurtar o stop (sign-flip perfeito: piora
monotonicamente no IS, melhora monotonicamente no OOS); e a COMBINACAO
alvo 1,5x + teto de stop 25, que fica pior que as duas partes isoladas
(19,7% no bootstrap de R$/op, contra 40,9% do alvo sozinho).

LIMITE DESTA PROMOCAO: o 1,5x foi escolhido OLHANDO o IS e o OOS, entao as
duas janelas foram gastas na escolha e nao existe validacao cega dela. O que
ele tem e' nao inverter de sinal em janela nenhuma e sobreviver ao
reembaralhamento -- o piso para merecer uma janela cega, que so' o tempo da'.

O DESENHO DE EXECUCAO (ordem do dono, 2026-09-10 -- ver CLAUDE.md):

  * entrada por `EnterLimit` PARADA no livro, nunca `Enter` a mercado. Num
    rompimento que nao volta, o trade simplesmente nao acontece: 19,4% dos
    pregoes do IS passam em branco por isso, e essa taxa e' o numero que
    decide se o setup sobrevive ao desenho real;
  * a ordem de entrada TEM prazo (`entrada_ttl_bars`). Sem prazo ela espera
    o pregao inteiro e preenche horas depois do sinal -- medido 269,7 min
    num robo irmao, e os fills atrasados foram os piores resultados;
  * alvo por ordem-limite REAL fatiada (`exit_split_unit=1`), SEM prazo
    (`EXIT_TTL_BARS_SEM_PRAZO`), nunca `tp` nativo -- o nativo e' gatilho
    varrido a mercado e come 57,9% do bruto (n=11, 10 contra 0 a favor);
  * `anchor_exits_at_fill=True`: stop e alvo ancoram no preco REALMENTE
    obtido. Aqui a flag vale de verdade, porque e' lida no caminho de
    preenchimento de `EnterLimit` (era no-op para `Enter`, item 4.23);
  * stop a MERCADO -- excecao unica. Protecao nao espera fila.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    AdjustTarget, Bar, EnterLimit, Exit, IntradayAction,
    IntradayOpenPosition, IntradayStrategy,
)

#: Prazo da fatia de saida por ALVO: sem prazo. NUNCA `None` -- `None` no
#: motor significa "comportamento antigo, sem fatia com prazo", e em execucao
#: REAL `machine._resolve_live_split_exit` levanta `NotImplementedError`.
#: Mesma constante/mesmo motivo de `wdo_grid_reload_maker.EXIT_TTL_BARS_SEM_
#: PRAZO` (ordem do dono, 2026-09-09): a limite do alvo fica parada ate' o
#: mercado PAGAR, e nunca sai a mercado por impaciencia.
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class WdoOrb(IntradayStrategy):
    """Rompimento da faixa de abertura do mini-dolar, ate' 2 operacoes por pregao"""

    name: str = "wdo_orb"
    version: str = "1.1.0"
    symbol: str = "WDO@"
    #: o alvo e' ordem-limite REAL parada no livro, nao `tp` nativo.
    target_fills_as_maker: bool = True
    #: vale de verdade aqui: a flag e' lida no caminho de `EnterLimit`.
    anchor_exits_at_fill: bool = True
    #: medido em base de TICK. Ver `entrada_ttl_bars` para o que isso faz com
    #: qualquer parametro contado em BARRAS.
    feed_kind: str = "tick"
    is_futuro: bool = True

    tick_size: float = 0.5
    #: faixa de abertura: os primeiros N minutos do pregao.
    range_minutos: float = 15.0
    #: O stop sai do TAMANHO DA FAIXA (1 tick de faixa = 1 tick de stop),
    #: limitado entre os dois. Distribuicao medida da faixa nos 72 pregoes do
    #: IS, em ticks: p0 13 · p25 23 · p50 35 · p75 42,5 · p95 64,5 · p100 93.
    #:
    #: TETO BAIXOU DE 40 PARA 30 EM 2026-09-11. Com 40, o piso mordia em
    #: 13,9% dos pregoes, o teto em 31,9%, e 54,2% passava livre. Com 30 o
    #: teto passa a morder em **61,1%** dos pregoes (mais da metade -- o p50
    #: da faixa ja' e' 35, acima do novo teto) e so' 25,0% passa livre --
    #: NAO e' um ajuste fino, e' uma mudanca estrutural da geometria, feita
    #: de olhos abertos: o stop mais curto perde um pouco de win% (o motivo:
    #: mais pregoes tem o stop artificialmente apertado por baixo do que o
    #: range pediria, entao levam stop com mais frequencia por puro ruido),
    #: mas foi a troca que deu o melhor R$/operacao (+18,18 contra +14,92 do
    #: teto 40) das 5 combinacoes medidas -- ver a nota no topo do modulo.
    #:
    #: ATENCAO, risco conhecido e NAO mitigado: mesmo com o teto em 30, um
    #: stop cheio (R$150,00 num contrato) partindo do caixa de partida
    #: (R$375) deixa R$225; DOIS seguidos ainda podem derrubar o caixa perto
    #: ou abaixo da margem. Baixar ou subir este numero muda a estrategia
    #: medida, entao e' decisao do dono, nao default silencioso -- e NUNCA
    #: baixe a ponto do alvo (`alvo_multiplo` vezes isto) chegar perto de 1
    #: tick (ver a proibicao do T1 em CLAUDE.md, vale para este robo tambem).
    stop_min_ticks: int = 20
    stop_max_ticks: int = 30
    #: alvo = stop x isto. BAIXOU DE 2,0 PARA 1,5 EM 2026-09-14 -- ver a nota
    #: no topo do modulo para a medicao completa. Em uma linha: o 1,5x nao
    #: ganha mais DINHEIRO (R$/op fica igual, mediana -0,58 no bootstrap), ele
    #: ganha com mais FREQUENCIA -- 95,0% das reamostragens tem mais pregoes
    #: positivos, e ele e' >= ao 2,0x em 6 de 6 comparacoes pareadas de stop.
    #: E' o criterio do dono ("ganhar pouco e ganhar sempre") aplicado ao unico
    #: eixo que sobreviveu a rodada inteira de 2026-09-14.
    #:
    #: NAO baixe mais sem medir: 1,25x e 1,0x pioram o R$/op no OOS (8,80 e
    #: 9,58 contra 11,14 do 1,5x), e o alvo tem de ficar longe de 1 tick (a
    #: proibicao do T1 em CLAUDE.md vale aqui).
    #:
    #: Geometria FIXA (`stop_ticks_fixo`/`alvo_ticks_fixo`) ja' foi chamada de
    #: "refutada de forma monotonica" nesta docstring, com S10/T20 a +R$0,88/op
    #: e S20/T40 a +R$2,34 contra +R$15,71 da faixa adaptativa. Aquilo foi
    #: medido em OUTRO desenho de execucao (corte a mercado, sem fade, fila
    #: antiga). Remedidas em 2026-09-14 no desenho vigente: S20/T40 da' +18,14
    #: (IS) e +9,81 (OOS); S10/T20 da' -1,99 (IS) e +13,94 (OOS). Nenhuma vira
    #: candidata -- S10/T20 inverte de sinal entre as janelas -- mas
    #: "monotonicamente refutada" deixou de descrever os numeros.
    alvo_multiplo: float = 1.5
    quantity: int = 1

    #: Fecha a posicao a MERCADO N minutos depois da entrada. E' o desenho
    #: ANTIGO -- deixado aqui so' para reproduzir a linha de base da tabela do
    #: topo. Em producao fica `None`: fechar a mercado paga `slippage_ticks`
    #: (1,0t = R$5,00 no WDO@) e esse corte era 67% das saidas do robo.
    exit_minutos: float | None = None
    #: O CORTE DO RELOGIO, versao maker: N minutos depois da entrada, move o
    #: alvo para o preco CORRENTE (`AdjustTarget`) e espera a ordem-limite
    #: preencher, em vez de atravessar o livro. A limite fica NO preco, nao
    #: alem dele -- e' ordem parada de verdade, nao ordem a mercado
    #: disfarcada: arma uma fatia nova e espera a fila daquele nivel.
    #:
    #: Sozinha, esta troca levou o deslize pago de R$265,00 para R$70,00 nos
    #: 72 pregoes e o R$/op de +15,71 para +21,31. De um ganho de +R$5,60/op,
    #: R$3,36 sao mecanicamente o deslize que deixou de ser pago; o resto e'
    #: o preco melhor de quem sai por limite.
    #:
    #: O que se ARRISCA: se a limite nao preencher, a posicao fica aberta ate'
    #: o achatamento de fim de pregao (que volta a ser a mercado). Aos 60 min
    #: a entrada ja' aconteceu entre 09:16 e 09:58 BRT (mediana 09:22), entao
    #: sobra pregao de sobra -- mas e' exposicao que o corte a mercado nao
    #: tinha.
    saida_limite_minutos: float | None = 60.0

    #: 0 = limite NO nivel do rompimento; N = N ticks ATRAS (esperando
    #: pullback). Mais offset = preco melhor para quem preenche e mais pregao
    #: em branco. Medido no IS: 2t deixa 19,4% dos pregoes sem trade e da'
    #: +15,71/op; 5t deixa 45,8% e da' -1,01/op. 2 e' o unico valor vivo.
    offset_ticks: int = 2
    #: Prazo da ordem de ENTRADA parada no livro, EM BARRAS.
    #:
    #: EM BASE DE TICK, BARRA NAO E' TEMPO (CLAUDE.md): a base mede mediana de
    #: 336 barras/minuto, p25 190 e p75 586 -- 5000 barras sao ~15 min na
    #: mediana, ~8,5 min num minuto agitado e ~26 min num minuto parado. O
    #: numero que vale reportar e' o atraso REALIZADO, e ele foi medido: p50
    #: 0,2 min · p90 2,3 min · max 8,6 min, com 19,4% dos pregoes sem
    #: preenchimento nenhum. O prazo curto (~5 min) foi medido junto e e' pior:
    #: 29,2% sem trade e +11,66/op.
    entrada_ttl_bars: int | None = 5000

    #: GEOMETRIA FIXA em ticks absolutos -- quando setados, ignoram a faixa.
    #: REFUTADA (ver `alvo_multiplo`), existe so' para reproduzir a medicao.
    #: A alcancabilidade do alvo e' em ticks ABSOLUTOS, nunca no multiplo:
    #: S40 x 2,0 pede 80 ticks (40 pontos, o movimento do WDO@ do dia inteiro
    #: em 60 min); S10 x 2,0 pede 20 ticks.
    #:
    #: NUNCA `alvo_ticks_fixo=1` (nem `alvo_multiplo` baixo o bastante pra
    #: `_geometria()` devolver alvo perto de 1 tick) -- e' a mesma proibicao
    #: do T1 no WDO F1 (CLAUDE.md, ordem do dono 2026-09-08), e vale AQUI
    #: tambem: mesmo o alvo sendo ordem-limite real (`target_fills_as_maker
    #: =True`, nao `tp` nativo), 1 tick e' o nivel mais disputado do livro --
    #: a calibracao de fila real (`fidelidade.py`, 438/489) ja mostra que ate'
    #: alvo NORMAL pena pra preencher. Nao meça, nem como candidato.
    stop_ticks_fixo: int | None = None
    alvo_ticks_fixo: int | None = None

    #: depois que a operacao do dia FECHA (preencheu e saiu, por qualquer
    #: motivo -- stop, alvo ou relogio), um rompimento da faixa ORIGINAL
    #: para o lado OPOSTO ao primeiro do dia dispara uma segunda entrada,
    #: apostando na volta pra dentro da faixa. Uma unica vez por pregao,
    #: no maximo (nunca mais de 2 operacoes no dia). Ver a docstring da
    #: classe para os numeros de IS e OOS.
    fade_rompimento_oposto: bool = True

    #: quantas vezes o fade pode disparar num mesmo pregao. Era 1 (fixo, sem
    #: parametro) ate' 2026-09-11; subiu pra 3 no mesmo dia; VOLTOU a 1 ainda
    #: no mesmo dia, depois de medir consistencia (ver a nota no topo do
    #: modulo) -- as tres decisoes tem a medicao ao lado, nenhuma foi
    #: silenciosa.
    #:
    #: O teto 3 tinha sido escolhido pelo RANKING AGREGADO (unica coisa que
    #: as duas janelas concordavam):
    #:
    #:     teto        IS          OOS
    #:     1       +2.843,50    +385,50     <- default ATUAL (de novo)
    #:     2       +2.695,50    +830,00
    #:     3       +3.055,50    +839,00     <- rodou em producao ate' aqui
    #:     ilim.   +2.399,50    (nao medido)
    #:
    #: NAO acredite na explicacao por ordem da chamada: ela NAO e' estavel.
    #: No IS o 2o fade da' -133,50 e o 3o +460,00; no OOS o 2o da' +506,50 e o
    #: 3o so' +9,00. As duas janelas discordam sobre QUAL fade paga -- os
    #: baldes tem n de 12 a 40, pequeno demais para resolver atribuicao por
    #: ordem. So' o agregado tem n suficiente para decidir o TOTAL.
    #:
    #: Mas o teto 3 tambem sobe o risco de ruina: medido no capital real
    #: (R$375, embaralhando as operacoes 10.000 vezes), teto 3 trava em
    #: 53,5% dos sorteios contra 53,3% do teto 1 -- e o teto 1 combinado com
    #: `stop_max_ticks=30` (o default atual) trava so' 52,4%, com R$/operacao
    #: MELHOR (+18,18 contra +14,92 do teto3/stop40). Voltar pra 1 e' o dono
    #: escolhendo "pouco mas constante" sobre "mais liquido total, mais
    #: risco de sequencia ruim" -- ver a nota no topo do modulo pra tabela
    #: completa das 5 combinacoes medidas.
    #:
    #: Lacuna conhecida: o 4o fade so' foi medido no IS (-496,00, NEGATIVA).
    max_fades_por_dia: int = 1

    _open_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _range_hi: float | None = field(default=None, init=False, repr=False)
    _range_lo: float | None = field(default=None, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)
    _limite_posto: bool = field(default=False, init=False, repr=False)
    _preencheu_hoje: bool = field(default=False, init=False, repr=False)
    #: lado do PRIMEIRO rompimento do dia -- o fade so' dispara no lado
    #: contrario a este.
    _lado_primeiro: str | None = field(default=None, init=False, repr=False)
    #: quantos fades ja' dispararam hoje -- o teto e' `max_fades_por_dia`.
    _fades_no_dia: int = field(default=0, init=False, repr=False)
    #: tinha posicao na barra anterior? -- so' existe para detectar a
    #: transicao "tinha e agora nao tem mais" (a posicao original fechou),
    #: o gatilho que libera o fade.
    _tinha_posicao: bool = field(default=False, init=False, repr=False)

    # ---------------- ficha do painel (`dashboard/robot_view.py`) ----------

    tagline: str = (
        "Rompe a faixa dos 15 primeiros minutos do mini-dolar, ate' 2x por dia"
    )

    plain_summary: tuple[str, ...] = (
        "Nos primeiros 15 minutos do pregao o robo so' OLHA: anota o ponto "
        "mais alto e o mais baixo que o mini-dolar negociou. Essa e' a faixa "
        "de abertura.",
        "Quando o preco sai dessa faixa, ele deixa uma ordem 2 ticks ATRAS do "
        "rompimento e espera o preco voltar para peg -- se nao voltar, o dia "
        "passa sem operacao (acontece em 1 de cada 5 pregoes).",
        "Depois que essa operacao fecha, se o preco romper a faixa para o "
        "lado OPOSTO ao primeiro rompimento, ele entra de novo apostando "
        "que o dia volta ao meio. So' uma vez -- no maximo 2 operacoes por "
        "pregao (escolha por consistencia: um teto maior da' mais liquido "
        "total, mas trava o caixa com mais frequencia).",
        "Uma hora depois de entrar, se nem o alvo nem o stop tiverem sido "
        "atingidos, ele desiste da meta e passa a pedir o preco do momento -- "
        "por ordem parada, nunca a mercado.",
    )

    plain_example: tuple[str, ...] = (
        "09:00 as 09:15 -- o dolar anda entre 5.100,0 e 5.117,5. Faixa de 35 "
        "ticks, mas o TETO morde: stop trava em 30 ticks, alvo 60 ticks.",
        "09:22 -- rompe para cima. O robo deixa uma ordem de compra a "
        "5.116,5 (2 ticks abaixo do rompimento) e espera.",
        "09:23 -- o preco recua, encosta na ordem e ela preenche. Stop a "
        "5.101,5; alvo, como ordem parada no livro, a 5.146,5.",
        "10:23 -- ninguem pagou o alvo e o stop nao foi tocado. O robo troca "
        "o alvo pelo preco de agora e sai na primeira contraparte.",
    )

    watched_signals: tuple[str, ...] = (
        "Maxima e minima dos primeiros 15 minutos do pregao (a faixa).",
        "Fechamento de cada negocio, para saber se saiu da faixa.",
        "Relogio desde o preenchimento da entrada (o corte de 1 hora).",
    )

    entry_rules: tuple[str, ...] = (
        "Entra comprado se o preco fechar ACIMA da faixa; vendido se fechar "
        "ABAIXO.",
        "Nunca a mercado: ordem-limite parada 2 ticks atras do rompimento.",
        "A ordem tem prazo. Morreu sem preencher, o robo rearma no rompimento "
        "seguinte do mesmo dia -- mas so' enquanto nenhuma operacao aconteceu.",
        "Depois da 1a operacao fechar, um rompimento pro lado OPOSTO ao "
        "primeiro do dia abre uma entrada nova (o fade), sempre pro mesmo "
        "lado e na mesma faixa. So' uma vez -- no maximo 2 por dia.",
    )

    exit_rules: tuple[str, ...] = (
        "Stop a MERCADO, do tamanho da faixa de abertura (entre 20 e 30 "
        "ticks). E' a unica saida a mercado do robo.",
        "Alvo = 2x o stop, como ordem-limite REAL parada no livro, fatiada e "
        "sem prazo -- espera o mercado pagar.",
        "1 hora depois da entrada, o alvo e' trocado pelo preco corrente: sai "
        "por ordem parada, nao a mercado.",
        "Nunca vira o dia: o que sobrar e' fechado no achatamento de fim de "
        "pregao.",
    )

    sizing_rules: tuple[str, ...] = (
        "1 contrato, fixo. Nao escala com o caixa.",
        "Caixa de partida OFICIAL R$375,00 (margem R$150 x folga 2,0 x "
        "reserva 1,25) -- mas o teste as cegas (OOS) travou com esse valor "
        "na 1a semana e meia. So' atravessou a janela inteira com R$500,00, "
        "e mesmo assim raspando (minimo tocado R$153,50).",
        "Um stop cheio (30 ticks) custa R$150,00: dois seguidos param o robo "
        "por falta de margem. Reduzir o teto do stop ajuda pouco -- a chance "
        "de travar o caixa (medida embaralhando as operacoes) fica perto de "
        "52-55% em qualquer combinacao de teto de fade/stop testada.",
    )

    # ---------------- ciclo ------------------------------------------------

    def on_session_start(self, session_date) -> None:
        self._open_ts = None
        self._range_hi = None
        self._range_lo = None
        self._armou_hoje = False
        self._limite_posto = False
        self._preencheu_hoje = False
        self._lado_primeiro = None
        self._fades_no_dia = 0
        self._tinha_posicao = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        """Recusa por teto/capital: a ordem morreu, o arme de hoje some."""
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        """Prazo estourado: idem -- e e' o caminho que MAIS acontece.

        Este metodo e' a correcao de um robo CEGO, nao uma otimizacao. Ate'
        2026-09-10 o motor cancelava a ordem por prazo sem avisar ninguem
        (so' `on_order_rejected` existia, e ele so' dispara na recusa por
        teto): `_armou_hoje` ficava ligado para sempre e o robo passava o
        resto do pregao em silencio achando que tinha ordem no livro. Em 14
        dos 72 pregoes do IS -- +R$1.236,00 contra +R$1.649,00.

        E os 14 pregoes recuperados NAO eram lixo: win 57,1% e +R$29,50/op,
        acima da media do proprio robo. Nao havia selecao adversa escondida
        ali; havia so' silencio.

        Nao e' rearme depois de um TRADE: `_preencheu_hoje` continua
        garantindo uma operacao por pregao. Isto so' devolve a visao.
        """
        self._armou_hoje = False

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._open_ts is None:
            self._open_ts = ts

        # --- a posicao original acabou de fechar? --------------------------
        # `_armou_hoje` so' e' zerado por `on_order_expired`/`on_order_
        # rejected` (eventos de ORDEM) -- nada zerava por evento de POSICAO
        # ate' aqui, entao depois de um fill o campo ficava True pro resto
        # do pregao e o fade nunca era alcancado. Libera o arme aqui, sem
        # tocar `_preencheu_hoje` (ele continua garantindo que o lado
        # ORIGINAL nao repete -- so' o fade tem licenca de operar de novo).
        if self._tinha_posicao and not positions:
            self._tinha_posicao = False
            if self.fade_rompimento_oposto:
                self._armou_hoje = False
                self._limite_posto = False
        if positions:
            self._tinha_posicao = True

        # --- (1) os primeiros minutos: so' olha e mede a faixa -------------
        if (ts - self._open_ts) < pd.Timedelta(minutes=self.range_minutos):
            self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
            self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
            return []

        # --- (2) posicao aberta: so' o relogio decide alguma coisa ---------
        if positions:
            self._preencheu_hoje = True
            pos = positions[0]
            if self.exit_minutos is not None:
                if (ts - pos.entry_ts) >= pd.Timedelta(minutes=self.exit_minutos):
                    return [Exit(reason="tempo_maximo")]
            if self.saida_limite_minutos is not None and not self._limite_posto:
                if (ts - pos.entry_ts) >= pd.Timedelta(minutes=self.saida_limite_minutos):
                    self._limite_posto = True
                    # NO preco corrente, nao alem dele: nao atravessa o livro,
                    # entao e' ordem parada de verdade. O motor cancela a fatia
                    # que estava no alvo antigo e arma outra no nivel novo --
                    # com fila CHEIA, que e' o que a corretora faz.
                    return [AdjustTarget(float(bar.close))]
            return []
        self._limite_posto = False

        # --- (3) sem posicao: arma (ou nao) a entrada ----------------------
        if self._armou_hoje:
            return []
        if self._range_hi is None or self._range_lo is None:
            return []

        if not self._preencheu_hoje:
            stop_ticks, alvo_ticks = self._geometria()
            off = self.offset_ticks * self.tick_size

            if bar.close > self._range_hi:
                # comprado: a limite fica ABAIXO do rompimento (espera o recuo)
                limite = bar.close - off
                self._armou_hoje = True
                self._lado_primeiro = "long"
                return [self._ordem("long", limite, stop_ticks, alvo_ticks,
                                    "orb_rompimento_alta")]
            if bar.close < self._range_lo:
                # vendido: a limite fica ACIMA do rompimento
                limite = bar.close + off
                self._armou_hoje = True
                self._lado_primeiro = "short"
                return [self._ordem("short", limite, stop_ticks, alvo_ticks,
                                    "orb_rompimento_baixa")]
            return []

        # --- (4) o FADE: operacao do dia ja fechou, rompimento CONTRARIO ---
        # ao primeiro do dia. Mesma faixa (nunca refeita), mesma formula de
        # geometria e sempre o MESMO lado (oposto ao primeiro rompimento) --
        # ate' `max_fades_por_dia` vezes por pregao.
        if (self.fade_rompimento_oposto
                and self._fades_no_dia < self.max_fades_por_dia
                and self._lado_primeiro is not None):
            stop_ticks, alvo_ticks = self._geometria()
            off = self.offset_ticks * self.tick_size
            if self._lado_primeiro == "long" and bar.close < self._range_lo:
                self._fades_no_dia += 1
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, stop_ticks,
                                    alvo_ticks, "orb_fade_volta_a_faixa")]
            if self._lado_primeiro == "short" and bar.close > self._range_hi:
                self._fades_no_dia += 1
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, stop_ticks,
                                    alvo_ticks, "orb_fade_volta_a_faixa")]
        return []

    # ---------------- auxiliares (puros) -----------------------------------

    def _geometria(self) -> tuple[int, int]:
        """`(stop_ticks, alvo_ticks)` desta entrada -- da faixa, ou fixos."""
        if self.stop_ticks_fixo is not None:
            stop_ticks = self.stop_ticks_fixo
        else:
            assert self._range_hi is not None and self._range_lo is not None
            range_ticks = (self._range_hi - self._range_lo) / self.tick_size
            stop_ticks = max(self.stop_min_ticks,
                             min(self.stop_max_ticks, round(range_ticks)))
        alvo_ticks = (self.alvo_ticks_fixo if self.alvo_ticks_fixo is not None
                      else round(stop_ticks * self.alvo_multiplo))
        return int(stop_ticks), int(alvo_ticks)

    def _ordem(self, side, limite: float, stop_ticks: int, alvo_ticks: int,
               reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        return EnterLimit(
            side=side,
            limit_price=limite,
            initial_stop=limite - sinal * stop_ticks * self.tick_size,
            initial_target=limite + sinal * alvo_ticks * self.tick_size,
            quantity=self.quantity,
            ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason=reason,
        )
