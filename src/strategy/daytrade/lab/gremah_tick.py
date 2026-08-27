"""GREMAH_TICK -- porte da `Gremah` (`strategy/daytrade/lab/gremah.py`) para
rodar tick a tick (trade ticks reais, ver `market_data_intraday/
mt5_ticks_source.py`) em vez de barra M1. EXPLORATORIO (2026-08-22), pedido
do dono para ver o comportamento do desenho na menor granularidade que o MT5
oferece -- nao substitui a `Gremah` original, e' um robo PROPRIO (AGENTS.md:
uma estrategia por arquivo).

O DESENHO e' o mesmo: grade de niveis ao redor do preco, ancora FIXA (preco
de abertura) ate `fixed_anchor_until`, ROLANTE (preco do momento) depois;
ordem-limite parada esperando o preco vir ate ela (maker); repete o lado do
ultimo trade fechado se ele ganhou, troca se perdeu (alternancia so' na 1a
decisao do pregao -- ver `_next_side_to_arm`, mudanca 2026-08-27, antes
alternava sempre); teto de perda diaria; tamanho de posicao crescendo com o
caixa acumulado. O
motor (`backtest.intraday.machine`) nao muda uma linha -- ele so' conhece
`Bar` (ts/open/high/low/close/volume) e decide toque via
`bar.low <= nivel <= bar.high`. Um tick vira `Bar` com
`open=high=low=close=preco_negociado` (ver `ticks_to_bars` em
`scripts/daytrade/run_backtest_ticks.py`): um negocio e' um evento atomico, a
um preco so', entao o "range" da barra degenera para um ponto -- e isso e'
estritamente MAIS PRECISO que M1, nao uma aproximacao: no M1 duas coisas
(stop e alvo) podem ter tocado na mesma barra sem saber qual foi primeiro
(`IntradayBacktestConfig.ambiguous_bar_resolution` existe so' por causa
disso); com tick, so' um preco acontece por vez, entao essa ambiguidade
desaparece por construcao.

DOIS parametros da `Gremah` original sao contados em BARRAS, o que so' faz
sentido quando toda barra dura o MESMO tempo (1 minuto). Tick nao tem
cadencia fixa -- pode vir 1 negocio em 3 segundos ou nenhum em 3 horas (medido
2026-08-22 na PMAM3, papel ilíquido). Os dois foram RECONTADOS em tempo de
parede:

  1. `rolling_reanchor_after_bars` (30 barras M1 = 30 min) virou
     `rolling_reanchor_after_seconds` -- compara `ts` do tick atual contra o
     `ts` de quando a ordem foi posicionada, em vez de contar quantas vezes
     `on_bar` rodou.
  2. O teto de posicao (`RollingVolumeWindow`, `strategy/daytrade/base.py`)
     e' resolution-agnostic por construcao: soma volume por EVENTO (tick ou
     barra) dentro de uma janela de TEMPO (30 minutos por default), nao de
     contagem de eventos -- um tick e' so' um evento menor que uma barra
     M1, a formula nao muda. E' a MESMA classe que a `Gremah` M1 usa desde
     2026-08-22 (ver a docstring dela para o motivo da media movel
     substituir o antigo teto congelado no primeiro minuto).

O QUE NAO MUDOU, porque a formula ja e' resolution-independent: `profit_pct`/
`stop_multiplier` continuam sendo PERCENTUAL do preco de ancora, convertido
para ticks (`_ticks_from_pct`); `max_trades_per_side` continua sendo
CONTAGEM DE TRADES (nao de barras); o teto de perda diaria continua sendo
fracao de `capital_minimo_brl`, verificado a cada evento (agora por tick, o
que so' torna o stop MAIS responsivo, nunca menos).

CALIBRACAO: `_CALIBRATION_BY_SYMBOL_TICK` abaixo comeca com os MESMOS numeros
de `gremah._CALIBRATION_BY_SYMBOL` -- ponto de partida, NAO validacao. Esses
pares foram medidos bar a bar de 1 minuto; tick muda quantos fills acontecem
por dia e QUANDO (um nivel que uma barra M1 "tocaria" sem preencher de
verdade dentro do minuto agora so' preenche se um negocio real bateu nele).
Antes de tratar um resultado tick como decisao, repetir os MESMOS 4 passos
de medicao da `gremah.py` (regime de preco, varredura fina IS, confirmacao
OOS) com dado de tick -- herdar o numero do M1 sem medir de novo e' o
EXATO erro que aquele arquivo documenta ter sido cometido e corrigido antes.

PMAM3, BMGB4, KLBN3, LPSB3, DASA3, KLBN4, PCAR3, CSAN3 e GRND3 ja
passaram pelos 4 passos EM TICK -- ver `TICK_CONFIRMED_SYMBOLS`. CLSC4
tambem esta' na lista, mas por um caminho diferente: confirmada em OOS,
NAO pelos 4 passos completos (amostra pequena demais no IS pra
diferenciar qualquer parametro) -- ver o paragrafo dela mais abaixo.

PMAM3 foi medida 2x, a unica com historico de duas rodadas:

  1a medicao (2026-08-22, capital de teste R$100 fixo): a varredura IS
  sugeriu pares "melhores" que 0,32%/10x (ex.: 0,25%/15x), mas a confirmacao
  OOS mostrou 0,25%/15x e 0,32%/10x produzindo o MESMO resultado exato (337
  trades, R$1.074,63) -- ao preco de PMAM3 (~R$0,13-0,15), varios
  percentuais diferentes arredondam pro MESMO numero de ticks
  (`_ticks_from_pct`), entao a "melhora" da varredura era em boa parte
  ilusao de arredondamento. Conclusao daquela rodada: manter 0,32%/10x.

  2a medicao (2026-08-23, caixa REAL -- pedido do dono, "sempre rode com o
  caixa minimo para cada ativo"): com `capital_minimo_brl` em vez de R$100
  fixo, o IS mostrou 0,32%/20x (MESMO alvo, stop MAIOR) batendo o par
  antigo de forma nao-trivial (R$739,93 vs R$671,03 no IS), e a confirmacao
  OOS (2026-06-15..2026-08-21) CONFIRMOU: R$325,76 vs R$310,41 (+4,9%),
  MaxDD tambem menor (-11,7% vs -12,0%). Substitui o par de 2026-08-22 --
  o caixa de teste fixo mascarava esta melhora, mesmo motivo documentado em
  `gremah._VOLATILITY_OVERRIDE_BY_SYMBOL` para a KLBN4 em M1.

BMGB4 e KLBN3 (2026-08-23, mesma rodada -- IS+OOS, percentual E
volatilidade, caixa real): o mesmo par percentual 0,15%/10x bateu o
herdado do M1 nos dois, IS e OOS (BMGB4 +0,4% no OOS; KLBN3 +8,9% no OOS,
custando um pouco mais de MaxDD: -1,3%->-1,9%) -- ver a tabela abaixo.

LPSB3 (mesma rodada): candidato de volatilidade (k=0,05/s=30) venceu no IS
mas PIOROU no OOS (-0,4%); o par herdado do M1 fica, agora CONFIRMADO em
vez de so' herdado (a medicao testou e o par antigo se manteve).

DASA3, KLBN4 e PCAR3 (2026-08-23, mesma rodada de caixa real -- a
varredura completa de 10 simbolos tinha sido cancelada por tempo antes
disso, ver o paragrafo seguinte; estes 3 foram medidos numa rodada
separada, so' com eles): DASA3 0,15%/20x bateu o herdado 0,21%/10x no IS
(R$1.138,38 vs R$923,52) e CONFIRMOU no OOS (R$884,86 vs R$851,73, +3,9%,
MaxDD tambem menor). KLBN4 0,15%/5x bateu 0,21%/5x no IS (R$3.056,52 vs
R$1.548,23, quase o dobro) e CONFIRMOU no OOS (R$1.296,51 vs R$1.178,42,
+10,0%) -- o maior ganho OOS de toda a rodada de recalibracao tick.
PCAR3 0,20%/8x bateu 0,21%/10x no IS (R$986,27 vs R$943,30) mas EMPATOU
byte-a-byte no OOS (R$334,65 nos dois, 19 trades, 49 dias pulados nos
dois) -- ao preco da PCAR3 no periodo OOS (~R$1,60) os dois pares
arredondam para o mesmo numero de ticks, mesma ilusao de arredondamento
que a 1a medicao da PMAM3 documentou. Par herdado fica, agora CONFIRMADO
em vez de so' herdado.

  Investigacao extra da PCAR3 (2026-08-23, pedido do dono desconfiando do
  MaxDD): numa janela BEM mais longa (2025-12-16..2026-06-12, ainda dentro
  do IS, so' um corte de data comum pra comparar com outros simbolos), o
  par herdado (0,21%/10x) mostrou MaxDD de -17,6% -- pior que TODOS os
  candidatos testados naquela janela, inclusive em capital final. O
  melhor da janela longa (0,15%/8x, R$1.343,82 vs R$1.129,40, MaxDD
  -10,3% vs -17,6%) foi retestado no OOS CONGELADO de verdade e PIOROU
  (-7,8%, MaxDD -5,9%) -- nao generalizou. Confirma que o OOS curto da
  PCAR3 (so' 19 trades) nao tem poder estatistico pra distinguir
  candidatos, mas tambem confirma que otimizar numa janela maior sem
  reconfirmar no OOS de verdade teria trocado um problema por outro.
  Dono decidiu manter o par herdado (0,21%/10x) -- nao adotar 0,15%/8x.

CSAN3 (2026-08-23, varredura rodou so' nos ultimos 500 mil negocios do
IS -- 2,86 milhoes no total e' pesado demais pra grade inteira em tempo
razoavel, ver `scripts/daytrade/sweep_gremah_tick.py --tail-ticks`):
0,15%/5x bateu o herdado 0,21%/20x no IS (R$1.222,17 vs R$1.164,58) E no
OOS (R$1.245,29 vs R$969,17, +28,5%, MaxDD tambem menor: -1,2% vs
-2,2%), com o dobro de trades -- sem ilusao de arredondamento, a maior
melhora confirmada da rodada.

GRND3 (2026-08-23, varredura completa -- so' 755 mil negocios, nao
precisou de corte): candidato de volatilidade B k=0,05/s=8 bateu o
percentual herdado do M1 (0,21%/5x) no IS (R$2.623,63 vs R$1.437,30,
quase o dobro) E no OOS (+30,9%, MaxDD tambem menor: -0,8% vs -2,0%) --
ver `_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK`. Primeiro simbolo confirmado
em tick com par de volatilidade, nao percentual; o par quase coincide
com o que a `Gremah` M1 ja usa para este simbolo (k=0,05/s=10), boa
confirmacao cruzada entre os dois motores.

CLSC4 (2026-08-23, testada com o parametro dos outros 9 confirmados, nao
com varredura propria): no IS (8.028 negocios, 2025-05-12..2026-06-12) TODOS
os candidatos deram so' 2-4 trades -- amostra pequena demais pra
diferenciar qualquer parametro, o herdado (0,42%/10x) empata com o da
LPSB3 e vence o resto por acaso, nao por medicao. No OOS (2026-06-15..
2026-08-21, preco subiu de R$83,58 pra R$137,19) o quadro muda: o par da
PCAR3 (0,21%/10x) da 27 trades contra so' 1 do herdado, e capital final
maior (R$28.238,79 vs R$27.369,35). Dono decidiu adotar 0,21%/10x vendo
essa diferenca -- e' uma escolha a partir do OOS SEM confirmacao previa
no IS (o inverso do protocolo normal: aqui foi o holdout que
diferenciou, nao o treino). Dono pediu para marcar como CONFIRMADA EM
OOS mesmo assim (2026-08-23) -- esta' em `TICK_CONFIRMED_SYMBOLS`, mas
por um caminho diferente dos outros 9: decisao explicita do dono a
partir do OOS, nao medicao pelos 4 passos completos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from statistics import median

import math

import pandas as pd

from strategy.daytrade.base import (
    LOTE_PADRAO_B3,
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    JanelaNegocioTipicoDiaria,
    JanelaVolatilidadeDiaria,
    RollingVolumeWindow,
    capital_minimo_brl,
)

#: Mesmo default de `gremah.VOL_JANELA_DIAS_PADRAO` -- ver a docstring la para
#: o motivo (nao repetida aqui).
VOL_JANELA_DIAS_PADRAO = 10

#: Mesmos defaults de `gremah.py` -- ver as constantes homonimas la para a
#: justificativa completa de cada numero (nao repetida aqui).
SESSION_STOP_FRACAO_PADRAO = 0.20
REALOCACAO_LIMIAR_CAIXA_PADRAO = 4.0
REALOCACAO_TETO_PCT_VOLUME_MINUTO_PADRAO = 0.10
#: Janela (minutos) da media movel de volume que alimenta o teto acima --
#: MESMO mecanismo da `Gremah` M1 (`strategy.daytrade.base.
#: RollingVolumeWindow`), reavaliado a CADA sinal de entrada. Ate 2026-08-22
#: este robo usava uma janela de acumulo unica (60s) desde a abertura,
#: congelada assim que fechasse -- substituido no mesmo dia (pedido do dono,
#: mesma mudanca aplicada na `Gremah`) por uma media MOVEL, que tambem
#: completa com a cauda do pregao ANTERIOR enquanto a sessao de hoje ainda
#: nao acumulou a janela inteira sozinha. Ver a constante homonima em
#: `gremah.py` para a medicao (so' feita em M1) que decidiu 1min em vez de
#: 30min -- o pedido original (2026-08-22) cobria os DOIS robos, entao o
#: mesmo valor foi aplicado aqui sem remedir em tick.
REALOCACAO_JANELA_MINUTOS_PADRAO = 1.0
#: Equivalente em tempo dos "30 barras M1" que `Gremah.rolling_reanchor_
#: after_bars` usa por default (30 minutos).
ROLLING_REANCHOR_SEGUNDOS_PADRAO = 30.0 * 60.0

#: Teto de pedacos que `dividir_entrada=True` cria para UMA entrada -- cada
#: pedaco e' 1 LOTE fixo (2026-08-24, ver `_dividir_pecas`), entao este teto
#: e' o numero MAXIMO de ordens reais mandadas de uma vez pra corretora, nao
#: mais um controle de tamanho de pedaco. Acima do teto, o ultimo pedaco
#: absorve o excedente (deixa de ser 1 lote) -- os primeiros
#: `dividir_max_pecas - 1` pedacos continuam identicos independente de
#: quantos lotes o teto de capacidade recomendar no total (prefixo estavel,
#: pedido do dono 2026-08-24: "os mesmos que sao pegos em 118 deveria ser
#: pegos independente do capital disponivel"). So' tem efeito com
#: `IntradayBacktestConfig.limit_fill_capped_by_volume=True` -- sem o cap, o
#: motor preenche tudo de uma vez de qualquer jeito (ver
#: `IntradaySessionMachine._resolve_limit_fills`), entao dividir a ordem nao
#: muda nada. `dividir_entrada` virou padrao `True` 2026-08-23 (pedido do
#: dono, depois de medir IS/OOS -- ver a memoria `dividir_entrada_is_oos_
#: 2026_08_23` do projeto: inverte de sinal entre IS e OOS na GremahTick,
#: mas o dono decidiu ligar mesmo assim -- "no teste e tudo lindo, por isso
#: temos o OOS, pra chegar mais proximo da verdade"). Subiu de 8 para 50 em
#: 2026-08-24 junto com a mudanca de pedaco fixo (medido em
#: `entrada_lote_unico.py`, variante E3) -- acima disso o numero de ordens
#: reais simultaneas vira um problema operacional na corretora, nao so' de
#: simulacao.
DIVIDIR_MAX_PECAS_PADRAO = 50

#: Barras (1 negocio real cada, aqui -- NAO 1 minuto, ver `Gremah.
#: EXIT_TTL_BARS_PADRAO`) que uma fatia de SAIDA espera antes de virar ordem
#: a mercado pelo restante (`EnterLimit.exit_ttl_bars`) -- so' tem efeito com
#: `dividir_entrada=True`. Decidido 2026-08-23 apos varrer 1..10 em PMAM3
#: (IS+OOS, Gremah E GremahTick -- ver a memoria `exit_ttl_bars_decisao_
#: 2026_08_23` do projeto): ttl curto (1-3) e' estruturalmente pior em quase
#: toda metrica, 8 e' o melhor ou quase melhor ponto nas duas janelas (MaxDD
#: -6,68%/-12,00%, os mais baixos ou quase da faixa toda), e ir alem de 8 nao
#: e' monotonico. MESMA constante e mesmo motivo de `DIVIDIR_MAX_PECAS_PADRAO`
#: acima.
EXIT_TTL_BARS_PADRAO = 8

#: Teto de CAPACIDADE de caixa -- diferente do teto de PREENCHIMENTO
#: (`REALOCACAO_TETO_PCT_VOLUME_MINUTO_PADRAO`, que limita o tamanho de UMA
#: entrada pelo fluxo do INSTANTE). Este limita o CAIXA que a formula de
#: realocacao enxerga, pra caixa acima da capacidade nao virar posicao maior
#: nenhuma -- so' fica parado, disponivel pra saque sem perder lucro.
#:
#: Achado 2026-08-24 medindo a PMAM3: sem este teto, mais caixa PIORA o
#: resultado acima de ~R$2.500 (a formula de realocacao manda usar mais
#: lotes do que a liquidez do papel sustenta -- ordem maior nao acha
#: contraparte, perde o timing fino que tinha pequena) -- em R$50 mil o robo
#: perdia R$8.527 no OOS. Com o teto, R$20 mil/R$50 mil/R$200 mil dao o
#: MESMO resultado (+R$91 no OOS) -- caixa extra fica comprovadamente
#: inerte, em vez de destruir capital.
#:
#: `CAPACIDADE_NEGOCIO_MULT_PADRAO=4.0`: o teto de posicao (em negocios
#: tipicos) usado tanto no preenchimento quanto na capacidade -- varrido
#: contra 3/4/6/8/16 na PMAM3, 4 foi o unico que preserva lucro estavel
#: (nao decrescente) em vez de colapsar acima de R$20 mil.
#:
#: `CAPACIDADE_FRACAO_PADRAO=0.5`: fracao da capacidade deduzida que o robo
#: de fato usa -- varrido 30/50/80/100% no OOS, 50% teve o melhor platô
#: (+R$265 vs +R$91 a 100%) com MaxDD mais baixo. Trade-off real: fracao
#: menor reduz ainda mais o lucro dentro da faixa boa mas encolhe o
#: MaxDD -- nao e' so' upside.
#:
#: REMEDIDO 2026-08-24 (pedido do dono, depois de achar 1.0/0.10 na `Gremah`
#: M1 -- ver la' se o mesmo valia aqui): grade ampla em IS (mult 0.10..24.0 x
#: fracao 0.01..2.00, PMAM3, dois niveis de caixa). Ao contrario da M1, o
#: gradiente em TICK vai no sentido OPOSTO -- valores MAIORES venceram no IS,
#: com "campeao" aparente em 10.0/1.5 (capital final maior, mas MaxDD ~4x
#: pior que o atual: -1,52% vs -0,35% em R$50 mil). Na confirmacao OOS (1
#: passada) esse "campeao" NAO se sustentou: o atual (4.0/0.5) venceu os
#: candidatos maiores tanto em capital final quanto em MaxDD nos dois niveis
#: de caixa (R$50.327,11/-0,23% contra R$49.596,51/-1,89% do 10.0/1.5) --
#: dominio total, nao trade-off. Ou seja: 4.0/0.5 nao e' so' o ponto de
#: partida generico portado da formula antiga -- e' o melhor valor
#: encontrado numa varredura de verdade (IS + confirmacao OOS) nesta janela.
#:
#: `CAPACIDADE_JANELA_DIAS_PADRAO=1`: a ANCORA de capacidade e' a mediana de
#: negocio da sessao ANTERIOR (nao a janela intradia de
#: `REALOCACAO_JANELA_MINUTOS_PADRAO`, que oscila e por isso vazava o teto
#: -- ver `strategy.daytrade.base.JanelaNegocioTipicoDiaria`). So' 1 dia de
#: folga foi o que se mediu; uma janela maior suaviza mais ao custo de
#: reagir mais devagar a uma mudanca real de patamar de liquidez -- nao
#: medido.
#:
#: ATE' 2026-08-24 isto era MEDIDO SO' NA PMAM3, so' no motor TICK -- nao
#: remedido nos outros 9 simbolos de `TICK_CONFIRMED_SYMBOLS` nem na
#: `Gremah` M1 (que usa seu proprio par, `1.0`/`0.10`, medido e adotado
#: separadamente -- os dois motores NAO convergem pro mesmo numero, e a
#: remedicao acima confirma que nao e' por falta de tentar). Mecanismo
#: aplicado a todos por ser estrutural (a formula de realocacao antiga tinha
#: o mesmo defeito em qualquer simbolo iliquido), mas os NUMEROS (4.0/0.5/1)
#: so' tinham medicao de verdade na PMAM3 -- nos outros 9 simbolos eram
#: apenas ponto de partida, mesma ressalva de `profit_pct`/`stop_multiplier`
#: antes deles virarem tabela por simbolo.
#:
#: 2026-08-25, OS OUTROS 9 SIMBOLOS -- pedido do dono: "isto tambem precisa
#: virar tabela por simbolo, igual profit_pct/stop_multiplier". Medido nos
#: 10 simbolos (mesmo protocolo de sempre: varredura no IS -> 1 passada de
#: confirmacao OOS, so' adota o valor novo se ele bater ou empatar o atual;
#: se piorar, MANTEM o atual) -- resultado completo em `_CAPACIDADE_BY_
#: SYMBOL_TICK` logo abaixo.
#:
#: RIGOR DA MEDICAO, HONESTO -- esta rodada foi mais RASA que a da `Gremah`
#: M1 (`gremah.CAPACIDADE_NEGOCIO_MULT_PADRAO`, ver a docstring dela): so' 5
#: valores FIXOS de referencia testados (1.0/0.125, 2.0/0.25, 4.0/0.5 -- o
#: atual, no centro --, 8.0/1.0, 16.0/2.0), os mesmos 5 rodados no IS e
#: depois no OOS (sem busca nova no holdout, entao nao contaminou), caixa de
#: teste R$50.000, SEM rodada de extensao de borda. Ou seja: pode existir um
#: valor ainda melhor fora desses 5 pontos nos simbolos onde um extremo
#: (8.0/1.0 ou 16.0/2.0) venceu -- isso NAO foi verificado aqui, ao
#: contrario da M1, que testou justamente esse cenario (extensao de borda)
#: e nao achou nada melhor nos 4 casos aplicaveis.
#:
#: RESULTADO POR SIMBOLO (capital de teste R$50.000; "TROCA" = valor novo
#: bateu o atual 4.0/0.5 no OOS; "MANTEM" = valor novo empatou ou piorou):
#:   PMAM3   4.0  / 0.5   -- e' o proprio atual (medicao original acima)
#:   KLBN4   16.0 / 2.0   TROCA -- OOS R$51.482,90 -> R$53.715,86 (+R$2.232,96)
#:   GRND3   16.0 / 2.0   TROCA -- OOS R$50.759,93 -> R$52.504,73 (+R$1.744,80)
#:   CSAN3   8.0  / 1.0   TROCA -- OOS R$51.237,73 -> R$52.711,31 (+R$1.473,58
#:           -- IS cortado pros ultimos 500 mil negocios por volume, mesmo
#:           corte ja usado nesse simbolo pra profit_pct/stop_multiplier)
#:   PCAR3   2.0  / 0.25  TROCA -- OOS R$50.250,53 -> R$50.322,86   (+R$72,33,
#:           margem modesta)
#:   KLBN3   8.0  / 1.0   TROCA -- OOS R$50.354,60 -> R$50.407,74   (+R$53,14,
#:           margem modesta)
#:   BMGB4   16.0 / 2.0   TROCA -- OOS R$50.175,62 -> R$50.289,72  (+R$114,10,
#:           margem modesta)
#:   DASA3   MANTEM 4.0/0.5 -- melhor alternativa (1.0/0.125) rendeu
#:           R$50.369,15 no OOS contra R$50.366,49 do atual (+R$2,66) --
#:           margem e' ruido, nao vale trocar
#:   LPSB3   MANTEM 4.0/0.5 -- melhor alternativa (2.0/0.25) rendeu
#:           R$50.183,29 no OOS, PIOR que o atual (R$50.194,03, -R$10,75)
#:   CLSC4   MANTEM 4.0/0.5 -- as 5 alternativas empataram byte-a-byte no
#:           OOS (R$49.577,44 em todas) -- nenhum sinal, nao ha' o que trocar
#:
#: As duas constantes abaixo DEIXAM de ser o default de todo mundo a partir
#: de 2026-08-25 -- viram so' o VALOR DE REFERENCIA da PMAM3, preservadas
#: porque ainda descrevem essa medicao e porque alguns testes leem essas
#: constantes diretamente. Quem decide o numero de cada simbolo agora e'
#: `_CAPACIDADE_BY_SYMBOL_TICK` (par de dataclass `_SymbolCapacidadeTick`,
#: mesmo padrao de `_CALIBRATION_BY_SYMBOL_TICK` abaixo) -- `GremahTick.
#: __init__` falha alto (`ValueError`) se o simbolo pedido nao estiver la,
#: mesma escolha e mesmo motivo da `Gremah` M1 (ver a docstring dela).
CAPACIDADE_NEGOCIO_MULT_PADRAO = 4.0
CAPACIDADE_FRACAO_PADRAO = 0.5
CAPACIDADE_JANELA_DIAS_PADRAO = 1

#: Quantos eventos a janela INTRADIA (`RollingVolumeWindow.volumes_por_
#: evento`) precisa ter antes do teto de PREENCHIMENTO confiar na mediana
#: deles -- achado testando a mudanca acima (2026-08-24): com 1 SO' evento
#: na janela, a mediana E' aquele evento, entao um unico negocio de bloco
#: isolado (ex.: 93 mil acoes, nada mais na janela) infla o teto direto pro
#: tamanho do bloco -- pior que o problema que a mediana resolve (a MEDIA
#: tambem e' refem de um bloco, mas pelo menos DILUI ele pelo tamanho
#: nominal da janela; com poucos eventos a mediana nao dilui nada). Abaixo
#: deste minimo, cai no fallback antigo (media/minuto) -- que so' entao volta
#: a ser o mais conservador dos dois. Numero pequeno de proposito: so'
#: protege o caso degenerado de 1-2 eventos, sem enfraquecer a mediana onde
#: ela ja funciona bem (a PMAM3 real, mesmo pouco liquida, tem dezenas de
#: eventos numa janela de 30min na maior parte do pregao).
CAPACIDADE_MIN_EVENTOS_PADRAO = 5


@dataclass(frozen=True)
class _SymbolCapacidadeTick:
    mult: float
    fracao: float


# Capacidade de caixa POR SIMBOLO, medida 2026-08-25 (ver a docstring de
# `CAPACIDADE_NEGOCIO_MULT_PADRAO` acima para o protocolo, o resultado por
# simbolo e o aviso de rigor -- esta rodada usou so' 5 pontos fixos de
# referencia, mais RASA que o grid completo da `Gremah` M1). PMAM3 e' o
# mesmo par de referencia medido 2026-08-24 (a unica medicao com grade mais
# ampla desta familia, ver o modulo `gremah.py`); os outros 9 sao o
# resultado dos 5 pontos + confirmacao OOS deste motor, TROCADOS so' quando
# bateram ou empataram o antigo default global (4.0/0.5). DASA3/LPSB3/CLSC4
# mantem 4.0/0.5 DE PROPOSITO (margem de ruido, alternativa pior, e empate
# total entre os 5 pontos -- respectivamente -- nao "nao medido").
_CAPACIDADE_BY_SYMBOL_TICK: dict[str, _SymbolCapacidadeTick] = {
    "PMAM3": _SymbolCapacidadeTick(mult=4.0, fracao=0.5),
    "KLBN4": _SymbolCapacidadeTick(mult=16.0, fracao=2.0),
    "GRND3": _SymbolCapacidadeTick(mult=16.0, fracao=2.0),
    "CSAN3": _SymbolCapacidadeTick(mult=8.0, fracao=1.0),
    "PCAR3": _SymbolCapacidadeTick(mult=2.0, fracao=0.25),
    "KLBN3": _SymbolCapacidadeTick(mult=8.0, fracao=1.0),
    "BMGB4": _SymbolCapacidadeTick(mult=16.0, fracao=2.0),
    "DASA3": _SymbolCapacidadeTick(mult=4.0, fracao=0.5),
    "LPSB3": _SymbolCapacidadeTick(mult=4.0, fracao=0.5),
}


@dataclass(frozen=True)
class _SymbolCalibrationTick:
    profit_pct: float
    stop_multiplier: float


# PONTO DE PARTIDA copiado de `gremah._CALIBRATION_BY_SYMBOL` (medido em M1,
# 2026-08-21/22) -- ver o AVISO no topo do modulo. Nao adicionar simbolo aqui
# sem repetir a medicao propria em tick.
_CALIBRATION_BY_SYMBOL_TICK: dict[str, _SymbolCalibrationTick] = {
    # CONFIRMADO em tick, unico da tabela -- medido 2x (2026-08-22 e
    # 2026-08-23, ver o aviso no topo do modulo). stop_multiplier=20.0
    # (nao 10.0) desde 2026-08-23: caixa de teste real revelou uma melhora
    # que o caixa fixo de R$100 mascarava (+4,9% no OOS).
    "PMAM3": _SymbolCalibrationTick(profit_pct=0.0032, stop_multiplier=20.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,15/5x bateu o par herdado do M1
    # (0,21%/5x) no IS (R$3.056,52 vs R$1.548,23, quase o dobro) E no OOS
    # (+10,0%) -- o maior ganho OOS da rodada.
    "KLBN4": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=5.0),
    # CONFIRMADO em tick 2026-08-23 -- varredura fina rodou so' nos ultimos
    # 500 mil negocios do IS (tick da CSAN3 tem 2,86 milhoes, pesado demais
    # pra grade inteira em tempo razoavel -- ver `sweep_gremah_tick.py
    # --tail-ticks`). % 0,15/5x bateu o par herdado do M1 (0,21%/20x) no IS
    # (R$1.222,17 vs R$1.164,58) E no OOS (R$1.245,29 vs R$969,17, +28,5%,
    # MaxDD tambem menor: -1,2% vs -2,2%) -- a maior melhora confirmada da
    # rodada, sem ilusao de arredondamento (o dobro de trades, 1266 vs 618).
    "CSAN3": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=5.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,15/20x bateu o par herdado do M1
    # (0,21%/10x) no IS (R$1.138,38 vs R$923,52) E no OOS (+3,9%).
    "DASA3": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=20.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,20/8x bateu 0,21%/10x no IS, mas
    # EMPATOU byte-a-byte no OOS (arredondamento de tick no preco da PCAR3
    # no periodo). Par herdado fica, agora com medicao propria.
    "PCAR3": _SymbolCalibrationTick(profit_pct=0.0021, stop_multiplier=10.0),
    # CONFIRMADA EM OOS (2026-08-23) -- mas NAO pelos 4 passos completos: o
    # IS tem so' 2-4 trades em qualquer parametro (amostra pequena demais
    # pra diferenciar nada ali). O dono adotou 0,21%/10x (par da PCAR3) ao
    # ver 27 trades no OOS contra so' 1 do herdado (0,42%/10x) e capital
    # final maior (R$28.238,79 vs R$27.369,35) -- decisao explicita a
    # partir do OOS, sem confirmacao IS previa (o inverso do protocolo
    # normal). Decisao do dono, registrada como tal.
    # CONFIRMADO em tick 2026-08-23 -- % 0,15/10x bateu o par herdado do M1
    # (0,21%/5x) no IS (R$3.098,47 vs R$1.825,77) E no OOS (+8,9%).
    "KLBN3": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=10.0),
    # Par percentual FALLBACK, so' usado se `_VOLATILITY_OVERRIDE_BY_SYMBOL_
    # TICK` nao tiver dado (primeiro pregao do historico, ou feed falhou) --
    # o par CONFIRMADO de verdade da GRND3 e' o de volatilidade, abaixo.
    "GRND3": _SymbolCalibrationTick(profit_pct=0.0021, stop_multiplier=5.0),
    # CONFIRMADO em tick 2026-08-23 -- candidato de volatilidade (k=0,05/
    # s=30) venceu no IS mas PIOROU no OOS (-0,4%); o par herdado do M1
    # (0,42%/20x) e' quem fica, agora com medicao propria em vez de so'
    # herdado.
    "LPSB3": _SymbolCalibrationTick(profit_pct=0.0042, stop_multiplier=20.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,15/10x bateu o par herdado do M1
    # (0,21%/20x) no IS (R$2.075,40 vs R$1.352,59) E no OOS (+0,4%).
    "BMGB4": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=10.0),
}

#: Mesmo mecanismo/motivo de `gremah._VOLATILITY_OVERRIDE_BY_SYMBOL` (mesma
#: classe): simbolo aqui liga `alvo_por_volatilidade` AUTOMATICAMENTE em
#: `GremahTick.__init__`, so' se o chamador nao decidiu nada por conta
#: propria. `_CALIBRATION_BY_SYMBOL_TICK` acima vira FALLBACK pra estes.
#:
#: GRND3 (2026-08-23) -- unico da tabela ate' agora: B k=0,05/s=8 bateu o
#: percentual herdado do M1 (0,21%/5x) no IS (R$2.623,63 vs R$1.437,30) E
#: no OOS (R$1.198,59 vs R$915,94, +30,9%, MaxDD tambem menor: -0,8% vs
#: -2,0%) -- quase o MESMO par (k=0,05/s=10) que a `Gremah` M1 ja usa pra
#: este simbolo (`gremah._VOLATILITY_OVERRIDE_BY_SYMBOL["GRND3"]`), boa
#: confirmacao cruzada entre os dois motores.
_GEOMETRIA_TICKS_BY_SYMBOL_TICK: dict[str, tuple[int, int, int]] = {
    # GEOMETRIA EM TICKS confirmada no OOS: (alvo, espacamento, stop) inteiros,
    # substituindo os tres de uma vez sem passar por `profit_pct` -- ver a
    # tabela homonima em `gremah.py` para o motivo (alvo e stop saem do MESMO
    # parametro no caminho percentual, entao mexer num arrasta o outro).
    #
    # BMGB4, 2026-08-26: IS R$ 1.636,80 x 1.310,14 (+24,9%); OOS R$ 36,22 x
    # 24,13 (+50,1%). RESSALVA: as duas pontas pularam 40 dos 50 pregoes do OOS
    # por caixa, entao a amostra sao ~10 pregoes efetivos (76 x 137 trades).
    # Direcao consistente com o IS, amostra pequena.
    "BMGB4": (1, 1, 8),
}

#: A PMAM3 NAO entra aqui: o candidato dela (T1 E1 S2) venceu o IS por +9,4% e
#: REPROVOU no OOS por -5,6% (2026-08-26). Reprovado no OOS e' descarte, sem
#: segunda tentativa. E a geometria 1 tick contra 1 tick que ela arma hoje, que
#: parecia degenerada, entrega 77,7% de acerto e ganha -- ver
#: `scripts/daytrade/confirm_oos_ticks.py`.
_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK: dict[str, tuple[float, float]] = {
    "GRND3": (0.05, 8.0),
}

#: Dos 10 acima, quais passaram pelos 4 passos EM TICK (regime de preco ->
#: varredura fina IS -> confirmacao OOS). A tabela inteira continua servindo
#: de PONTO DE PARTIDA para varrer um simbolo novo (`scripts/daytrade/
#: sweep_gremah_tick.py` precisa instanciar o robo para medi-lo); esta tupla
#: e' o que o PAINEL oferece para operar. A distincao e' o ponto todo:
#: herdar um numero medido em M1 e liga-lo em dinheiro real e' o erro que
#: `gremah.py` documenta ter cometido e corrigido antes.
#:
#: A CLSC4 saiu do conjunto calibrado em 2026-08-26 (decisao do dono). Medido:
#: ela imprime preco em 18,4 barras M1 por pregao contra 217-427 dos outros
#: nove, e o piso de 2 lotes de `capital_minimo_brl` cobra R$15.130 de caixa
#: contra R$658-810 deles. Na varredura de geometria em ticks foi o UNICO
#: simbolo negativo em todas as 48 celulas, nos dois motores -- com 1 trade
#: (M1) e 4 (tick) no historico inteiro, nao ha amostra que sustente nada.
#: Nao era calibracao errada: nao ha giro para um robo maker ali.
TICK_CONFIRMED_SYMBOLS: tuple[str, ...] = (
    "PMAM3", "BMGB4", "KLBN3", "LPSB3", "DASA3", "KLBN4", "PCAR3", "CSAN3",
    "GRND3",
)


@dataclass(frozen=True)
class SymbolSetup:
    """Um ativo calibrado EM TICK, como a ficha do robo o mostra. Espelha
    `gremah.SymbolSetup` (mesma forma, lida pelo mesmo `dashboard/
    robot_view.py`) -- separado porque os numeros sao de outra medicao.

    `alvo_por_volatilidade`/`alvo_vol_mult`/`stop_vol_mult` (2026-08-23):
    mesmo motivo de `gremah.SymbolSetup` -- quando ligado (GRND3, ver
    `_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK`), `profit_pct`/`stop_multiplier`
    acima viram FALLBACK, nao o que decide o alvo no dia a dia."""

    symbol: str
    profit_pct: float
    stop_multiplier: float
    alvo_por_volatilidade: bool = False
    alvo_vol_mult: float | None = None
    stop_vol_mult: float | None = None


def calibrated_setups() -> tuple[SymbolSetup, ...]:
    """Os ativos que este robo pode OPERAR hoje -- so' os confirmados em tick.

    Hoje bate com `_CALIBRATION_BY_SYMBOL_TICK` (os 10 simbolos estao em
    `TICK_CONFIRMED_SYMBOLS`), mas a distincao continua existindo por
    desenho: um simbolo novo, sem medicao propria em tick, NAO deveria
    aparecer aqui -- ver o aviso no topo do modulo sobre herdar numero de
    outra granularidade sem medir de novo. Quem le esta funcao e' o
    painel (`strategy.daytrade.registry.symbols_for_robot` -> formulario
    de robo novo).

    Constroi uma instancia REAL de `GremahTick` por simbolo e le os
    atributos JA' RESOLVIDOS dela -- mesmo motivo de `gremah.
    calibrated_setups()`: ler `_CALIBRATION_BY_SYMBOL_TICK` direto mostraria
    o percentual da GRND3 como se ainda fosse ele quem decide, quando quem
    decide e' `_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK`.
    """
    setups = []
    for symbol in TICK_CONFIRMED_SYMBOLS:
        robo = GremahTick(symbol=symbol)
        setups.append(SymbolSetup(
            symbol=symbol, profit_pct=robo.profit_pct, stop_multiplier=robo.stop_multiplier,
            alvo_por_volatilidade=robo.alvo_por_volatilidade,
            alvo_vol_mult=robo.alvo_vol_mult, stop_vol_mult=robo.stop_vol_mult,
        ))
    return tuple(setups)


@dataclass
class _SessionState:
    open_price: float | None = None
    session_halted: bool = False
    pending_side: str | None = None
    pending_mode: str | None = None  # "fixed" ou "rolling"
    pending_since_ts: pd.Timestamp | None = None
    open_side: str | None = None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None
    # `last_trade_won`/`entry_session_pnl_brl` (2026-08-27): suportam a
    # politica de lado "repete o vencedor" de `_next_side_to_arm` -- ver a
    # docstring dela para o mecanismo. `entry_session_pnl_brl` e' o
    # `session_pnl_brl` no instante em que a posicao foi aberta (1a fatia,
    # se `dividir_entrada=True`); `last_trade_won` compara esse snapshot
    # contra o `session_pnl_brl` no instante em que ela fechou por completo
    # (ultima fatia) -- mede o round-trip INTEIRO, nao uma fatia isolada.
    # Os dois resetam a cada sessao (mesmo motivo de `last_closed_side`):
    # a alternancia continua valendo na 1a decisao de CADA pregao.
    last_trade_won: bool | None = None
    entry_session_pnl_brl: float = 0.0
    spacing_ticks_today: int = 1
    profit_ticks_today: int = 1
    stop_ticks_today: int | None = None
    session_stop_armed: bool = False
    session_stop_brl_hoje: float = 0.0
    session_start_ts: pd.Timestamp | None = None


class GremahTick(IntradayStrategy):
    """Porte tick a tick da `Gremah` -- ver docstring do modulo para o que
    mudou (2 parametros recontados em tempo de parede) e o que ficou
    identico (formula de niveis, teto de perda, dimensionamento por caixa)."""

    name = "gremah_tick"
    version = "0.1"
    target_fills_as_maker = True
    #: Negocio a negocio, nunca M1 -- e' a granularidade em que ele foi medido
    #: e a unica em que os dois parametros de TEMPO dele fazem sentido. Quem
    #: monta o feed ao vivo le isto (`live/intraday_feed.py::feed_for`).
    feed_kind = "tick"

    # FICHA TECNICA -- documentacao, nunca decisao (mesma convencao da
    # `gremah`, ver o bloco equivalente la). Escrita conferindo cada numero
    # contra a INSTANCIA default, nao contra a docstring.
    tagline = (
        "A mesma Grid REload MAker Hybrid da gremah, mas enxergando negocio a "
        "negocio em vez de resumo de minuto. O desenho nao mudou; o que mudou e' "
        "que ela ve cada preco que de fato aconteceu, na ordem em que aconteceu — "
        "e por isso o stop dela sai no negocio, nao no fim do minuto."
    )
    plain_summary = (
        "Ela faz exatamente o que a gremah faz: deixa uma ordem de compra parada um "
        "pouco abaixo do preco, e quando o mercado desce ate' la, compra e ja' pendura "
        "a venda um pouco acima. O lucro de cada ida e volta e' de centavos, e o ganho "
        "vem da repeticao.",
        "A diferenca e' o que ela recebe do mercado. A gremah ve um resumo por minuto: "
        "abriu tanto, maximo tanto, minimo tanto, fechou tanto. Esta ve cada negocio "
        "fechado, um por um, com o preco e o horario de cada um.",
        "Isso resolve uma ambiguidade que o resumo de minuto tem por construcao: se "
        "dentro do mesmo minuto o preco encostou no stop E no alvo, o resumo nao diz "
        "qual veio primeiro, e o backtest tem de chutar (ele chuta o pior caso). "
        "Negocio a negocio nao ha o que chutar — cada negocio tem um preco so'.",
        "Ao vivo isso vale um minuto de reacao. A gremah so' pode conferir stop e alvo "
        "quando o minuto acaba; esta confere a cada negocio que chega.",
        "O preco disso e' quanto ela foi medida. So' a PMAM3 passou pela medicao "
        "completa em negocio a negocio; os outros nove ativos da gremah continuam "
        "medidos so' em minuto, e por isso nao aparecem na lista dela. Pedir um ativo "
        "fora da lista faz o robo se recusar a ligar.",
    )
    plain_example = (
        "PMAM3 abre a R$ 0,14. O alvo de 0,32% do preco nao chega a um centavo, entao "
        "vira o minimo negociavel: 1 centavo. Ate' aqui, identico a' gremah.",
        "Ela deixa a compra parada a R$ 0,13. Enquanto ninguem negociar nesse preco, "
        "nada acontece.",
        "A diferenca aparece agora: a ordem so' e' considerada tocada quando um negocio "
        "de verdade sai a R$ 0,13. No resumo de minuto bastaria a MINIMA do minuto ter "
        "encostado ali — o que pode ter sido um unico negocio de outra pessoa, na "
        "frente da fila.",
        "Comprada, ela pendura a venda a R$ 0,14 e o stop mais abaixo. Se o preco cair "
        "ate' o stop, a saida e' decidida no negocio que furou o nivel, nao no "
        "fechamento do minuto em que ele furou.",
        "Uma ordem parada que espera 30 minutos sem ser tocada e' cancelada e refeita "
        "no preco do momento — na gremah essa espera e' contada em 30 barras, aqui em "
        "30 minutos de relogio, porque negocio nao chega em cadencia fixa.",
    )
    watched_signals = (
        "O preco de cada negocio fechado no ativo, na ordem em que sai.",
        "O preco de abertura do dia, que ancora os niveis das primeiras horas.",
        "O relogio do pregao — e' ele que decide se a ancora e' a abertura ou o preco "
        "do momento.",
        "O tempo de relogio desde que a ordem parada foi posicionada (30 minutos), e nao "
        "quantos negocios passaram desde entao.",
        "O volume do ultimo minuto FECHADO, somado negocio a negocio, para o teto de "
        "tamanho da PROXIMA entrada.",
        "O resultado acumulado do dia contra o limite de prejuizo do ativo (20% do "
        "caixa minimo dele).",
    )
    entry_rules = (
        "Uma ordem parada por vez, um pouco abaixo do preco de referencia para comprar "
        "(ou acima, para vender a descoberto) — nunca persegue o preco.",
        "So' conta como tocada quando um negocio SAI naquele preco. E' a regra mais "
        "estrita que a de minuto, onde bastava a faixa do minuto conter o nivel.",
        "Entrada, alvo e stop saem de um percentual do preco de referencia arredondado "
        "para centavos inteiros. Em acao de centavos esse arredondamento manda: varios "
        "percentuais diferentes viram o mesmo 1 centavo.",
        "Ate' as 11h de Brasilia a referencia e' a abertura do dia; depois, o preco do "
        "momento. Mesmo corte da gremah, e pelo mesmo motivo — nao foi reotimizado.",
        "Depois de fechar um trade, repete o MESMO lado se ele deu lucro; troca de lado "
        "se deu prejuizo. So' insiste no mesmo lado alem disso quando o outro bateu o "
        "teto de 15 operacoes. Na primeira operacao do pregao, sem trade anterior no "
        "dia, alterna a partir do ultimo lado fechado no pregao anterior.",
        "Ordem parada ha' 30 minutos sem ser tocada e' cancelada e refeita no preco "
        "atual. Tempo de relogio, nao contagem de negocios: num papel iliquido podem "
        "passar horas sem negocio nenhum, e contar eventos deixaria a ordem velha "
        "parada indefinidamente.",
    )
    exit_rules = (
        "Vende com ordem parada no alvo, tambem sem perseguir o preco.",
        "Se o preco vai contra, o stop fecha a posicao — avaliado a cada negocio, nao "
        "no fim do minuto.",
        "Se o prejuizo acumulado do dia chega a 20% do caixa minimo do ativo, fecha o "
        "que estiver aberto e nao opera mais ate' o proximo pregao.",
        "Nunca carrega posicao para o dia seguinte. O corte segue o calendario real da "
        "B3, que anda 1h com o horario de verao americano.",
    )
    sizing_rules = (
        "Sempre em lotes inteiros de 100 acoes — nunca fracionario, onde cada ordem "
        "custaria R$ 1,90 fixos de corretagem num robo de giro alto.",
        "A cada 4x o custo de 1 lote que o caixa acumulado tiver, a proxima entrada "
        "usa mais um lote — e encolhe de volta se o caixa cair.",
        "O teto de UMA entrada e' o negocio TIPICO recente (mediana dos ultimos "
        "negocios, nao a media -- media e' inflada por um negocio de bloco isolado) "
        "vezes 4, reavaliado a cada entrada nova.",
        "Alem do teto de entrada, existe um teto de CAPACIDADE: caixa acima do que a "
        "liquidez do ativo sustenta (medida como negocio tipico da sessao ANTERIOR "
        "inteira, um numero estavel que nao oscila no meio do dia) vira inerte -- nao "
        "aumenta posicao nem lucro, so' fica parado. Sem isto, mais caixa PIORAVA o "
        "resultado (medido na PMAM3: R$50 mil perdia mais que R$2.500) -- e' o robo "
        "sabendo sozinho ate' onde o mercado suporta, sem numero fixo. Cada ativo tem "
        "o proprio par (multiplo/fracao), medido separadamente (IS + confirmacao "
        "OOS) -- nao transfere entre simbolos, mesmo achado de alvo/stop.",
        "O caixa minimo para operar o ativo e' o dobro do custo de um lote de 100 "
        "acoes, no preco de hoje.",
        "Esse minimo nao fica congelado no valor do primeiro dia: se o ativo sobe "
        "de preco depois que o robo ja esta' rodando, o minimo sobe junto, e se o "
        "caixa acumulado nao tiver alcancado o novo valor, o robo PULA o pregao "
        "inteiro ate' o lucro guardado cobrir o minimo atual — mesma regra da "
        "gremah, medida na DASA3 (48 pregoes fora quando o preco subiu de R$ 2,60 "
        "para R$ 4,19).",
    )
    param_pct = ("profit_pct", "session_stop_pct_capital",
                 "realocacao_teto_pct_volume_minuto", "capacidade_fracao")
    # Mesmo motivo da `gremah`: alvo e stop sao POR ATIVO, e a tabela plana
    # mostra so' a instancia default. Quem carrega todos e' a tabela de ativos.
    param_hidden = ("symbol", "profit_pct", "stop_multiplier")
    param_utc_time = ("fixed_anchor_until",)
    param_docs = {
        "symbol": "Ativo que ele negocia.",
        "tick_size": "Variacao minima de preco do ativo.",
        "profit_pct": "Alvo de lucro por trade, em % do preco da ancora. Vazio = lookup por "
                      "simbolo em `_CALIBRATION_BY_SYMBOL_TICK`.",
        "spacing_multiplier": "Distancia da entrada, em multiplos do alvo.",
        "stop_multiplier": "Distancia do stop, em multiplos do alvo. Vazio = mesmo lookup de "
                           "`profit_pct`.",
        "max_trades_per_side": "Teto de preenchimentos por lado, por sessao.",
        "session_stop_pct_capital": "Percentual do caixa minimo do dia que define a "
                                    "perda-limite diaria.",
        "fixed_anchor_until": "Hora em que a ancora fixa vira rolante.",
        "rolling_reanchor_after_seconds": "Segundos que uma ordem rolante espera antes de "
                                          "rearmar. Na gremah isto e' contado em barras; aqui "
                                          "e' relogio, porque negocio nao chega em cadencia fixa.",
        "realocacao_limiar_caixa": "Quantas vezes o custo de 1 lote o caixa acumulado precisa "
                                   "ter para a proxima entrada usar mais um lote.",
        "realocacao_teto_pct_volume_minuto": "FALLBACK do teto de posicao (`capacidade_negocio_"
                                             "mult`, abaixo) para quando a janela ainda nao tem "
                                             "nenhum negocio -- % da media de volume por minuto "
                                             "na janela rolante (`realocacao_janela_minutos`).",
        "realocacao_janela_minutos": "Tamanho da janela (minutos) da media movel de volume que "
                                     "alimenta o teto acima. Reavaliada a cada entrada nova; na "
                                     "abertura, completa com a cauda do pregao anterior.",
        "dividir_entrada": "Divide ENTRADA (pedacos de 1 LOTE fixo, prefixo estavel -- ver "
                          "`_dividir_pecas`) e SAIDA (pedacos do tamanho do negocio tipico "
                          "recente, ver `_fatia_saida`; ate' 2026-08-24 usava `LOTE_PADRAO_B3` "
                          "fixo, gerando mais negocios no mercado do que precisava pra casar), "
                          "em vez de exigir tudo de uma vez. So' tem efeito com o motor rodando "
                          "`limit_fill_capped_by_volume=True` (padrao desde 2026-08-23). Padrao "
                          "`True` desde 2026-08-23 -- medido IS/OOS antes (inverte de sinal), "
                          "ligado mesmo assim por decisao do dono.",
        "dividir_max_pecas": "Teto de pedacos (1 lote cada, cauda absorve o excedente acima do "
                             "teto) que `dividir_entrada` cria para uma entrada.",
        "exit_ttl_bars": "Barras (negocios reais, aqui, nao minutos) que uma fatia de saida "
                         "espera antes de virar ordem a mercado pelo restante. Padrao 8 desde "
                         "2026-08-23 (varredura 1..10 em PMAM3, IS+OOS). Vazio = execucao real "
                         "recusa operar com `dividir_entrada` ligado; backtest/sombra esperam "
                         "sem prazo.",
        "alvo_por_volatilidade": "Alvo/espacamento/stop por fracao da volatilidade medida "
                                 "(mediana do range diario) em vez de percentual do preco. "
                                 "Desligado por padrao -- opt-in, pendente de medicao/decisao.",
        "alvo_vol_mult": "O 'k' da regra alvo = k x range diario mediano. So' usado com "
                        "`alvo_por_volatilidade` ligado -- sem default.",
        "vol_janela_dias": "Sessoes anteriores usadas para medir a mediana do range diario.",
        "stop_vol_mult": "Multiplicador GLOBAL do stop sobre o alvo por volatilidade. Vazio = "
                         "usa o `stop_multiplier` do simbolo.",
        "stop_frac_range": "Fracao do range diario mediano que substitui o stop, mantendo "
                           "alvo/espacamento no caminho de sempre. Independente de "
                           "`alvo_por_volatilidade`. Vazio = stop pelo `stop_multiplier`.",
        "capacidade_negocio_mult": "Teto de posicao (entrada) e de capacidade (caixa), em "
                                  "multiplos do negocio tipico recente. Vazio = lookup POR "
                                  "SIMBOLO em `_CAPACIDADE_BY_SYMBOL_TICK` (5 pontos de "
                                  "referencia testados no IS + confirmacao OOS -- ver a "
                                  "docstring de `CAPACIDADE_NEGOCIO_MULT_PADRAO` para o "
                                  "resultado por simbolo e a ressalva de rigor frente a M1).",
        "capacidade_fracao": "Fracao da capacidade deduzida que o robo de fato usa -- o "
                            "restante fica de caixa parado, disponivel pra saque. Vazio = "
                            "mesmo lookup por simbolo de `capacidade_negocio_mult`.",
        "capacidade_janela_dias": "Sessoes anteriores usadas pra medir a ancora ESTAVEL de "
                                 "capacidade (`JanelaNegocioTipicoDiaria`) -- diferente de "
                                 "`realocacao_janela_minutos`, que e' intradia e oscila.",
        "capacidade_min_eventos": "Minimo de negocios na janela intradia antes do teto de "
                                 "preenchimento confiar na mediana deles -- com poucos eventos "
                                 "a mediana e' refem de um bloco isolado, igual a media era.",
        "profit_ticks": "Alvo em TICKS inteiros, direto. Vazio = o alvo sai de `profit_pct` "
                        "como sempre. Existe porque o alvo percentual satura no piso de 1 tick "
                        "em 9 dos 10 símbolos calibrados: quem quer alvo de 2 ticks precisa "
                        "dizer 2, não torcer para o percentual arredondar para lá.",
        "spacing_ticks": "Distância da entrada em TICKS inteiros. Vazio = sai de "
                         "`spacing_multiplier` x `profit_pct`.",
        "stop_ticks": "Stop em TICKS inteiros. Vazio = sai de `stop_multiplier` x `profit_pct`. "
                      "Junto com `profit_ticks`, permite escolher alvo e stop de forma "
                      "INDEPENDENTE -- no caminho percentual eles estão amarrados, e subir um "
                      "sobe o outro na mesma proporção.",
    }

    @staticmethod
    def calibrated_setups() -> tuple[SymbolSetup, ...]:
        """Os ativos calibrados EM TICK, alcancaveis a partir da CLASSE —
        espelho fino do `calibrated_setups()` do modulo, pelo mesmo motivo do
        espelho equivalente na `gremah`: quem monta a ficha recebe a classe e
        procura este nome com `getattr`."""
        return calibrated_setups()

    def __init__(
        self,
        symbol: str = "PMAM3",
        tick_size: float = 0.01,
        profit_pct: float | None = None,
        spacing_multiplier: float = 2.0,
        stop_multiplier: float | None = None,
        max_trades_per_side: int = 15,
        session_stop_pct_capital: float = SESSION_STOP_FRACAO_PADRAO,
        fixed_anchor_until: time = time(14, 0),
        rolling_reanchor_after_seconds: float = ROLLING_REANCHOR_SEGUNDOS_PADRAO,
        realocacao_limiar_caixa: float = REALOCACAO_LIMIAR_CAIXA_PADRAO,
        realocacao_teto_pct_volume_minuto: float = REALOCACAO_TETO_PCT_VOLUME_MINUTO_PADRAO,
        realocacao_janela_minutos: float = REALOCACAO_JANELA_MINUTOS_PADRAO,
        dividir_entrada: bool = True,
        dividir_max_pecas: int = DIVIDIR_MAX_PECAS_PADRAO,
        exit_ttl_bars: int | None = EXIT_TTL_BARS_PADRAO,
        alvo_por_volatilidade: bool = False,
        alvo_vol_mult: float | None = None,
        vol_janela_dias: int = VOL_JANELA_DIAS_PADRAO,
        stop_vol_mult: float | None = None,
        stop_frac_range: float | None = None,
        profit_ticks: int | None = None,
        spacing_ticks: int | None = None,
        stop_ticks: int | None = None,
        capacidade_negocio_mult: float | None = None,
        capacidade_fracao: float | None = None,
        capacidade_janela_dias: int = CAPACIDADE_JANELA_DIAS_PADRAO,
        capacidade_min_eventos: int = CAPACIDADE_MIN_EVENTOS_PADRAO,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        # Capturado ANTES do lookup abaixo, que preenche os dois: quem passou
        # `profit_pct=`/`stop_multiplier=` escolheu geometria PERCENTUAL de
        # proposito, e `_GEOMETRIA_TICKS_BY_SYMBOL_TICK` nao pode atropelar isso.
        _pct_explicito = profit_pct is not None or stop_multiplier is not None
        if profit_pct is None or stop_multiplier is None:
            calib = _CALIBRATION_BY_SYMBOL_TICK.get(symbol)
            if calib is None:
                raise ValueError(
                    f"gremah_tick: sem calibracao para o simbolo {symbol!r} em "
                    "_CALIBRATION_BY_SYMBOL_TICK (strategy/daytrade/lab/gremah_tick.py). "
                    "Passe profit_pct= e stop_multiplier= explicitamente, ou meca "
                    "este simbolo em tick (IS + OOS, mesmos 4 passos de gremah.py) "
                    "e adicione-o a tabela antes de usar o default."
                )
            if profit_pct is None:
                profit_pct = calib.profit_pct
            if stop_multiplier is None:
                stop_multiplier = calib.stop_multiplier
        self.profit_pct = profit_pct
        self.spacing_multiplier = spacing_multiplier
        self.stop_multiplier = stop_multiplier
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_pct_capital = abs(session_stop_pct_capital)
        self.fixed_anchor_until = fixed_anchor_until
        self.rolling_reanchor_after_seconds = abs(rolling_reanchor_after_seconds)
        self.realocacao_limiar_caixa = abs(realocacao_limiar_caixa)
        self.realocacao_teto_pct_volume_minuto = abs(realocacao_teto_pct_volume_minuto)
        self.realocacao_janela_minutos = abs(realocacao_janela_minutos)
        self.dividir_entrada = dividir_entrada
        self.dividir_max_pecas = max(1, int(dividir_max_pecas))
        self.exit_ttl_bars = exit_ttl_bars
        # `None` (default) = lookup por SIMBOLO em `_CAPACIDADE_BY_SYMBOL_TICK`
        # -- mesmo padrao de `profit_pct`/`stop_multiplier` acima neste
        # `__init__`. Ver a docstring de `CAPACIDADE_NEGOCIO_MULT_PADRAO`
        # (topo do modulo) pro protocolo de medicao e o resultado por
        # simbolo (medido 2026-08-24 na PMAM3, 2026-08-25 nos outros 9).
        if capacidade_negocio_mult is None or capacidade_fracao is None:
            capacidade = _CAPACIDADE_BY_SYMBOL_TICK.get(symbol)
            if capacidade is None:
                raise ValueError(
                    f"gremah_tick: sem capacidade de caixa calibrada para o "
                    f"simbolo {symbol!r} em _CAPACIDADE_BY_SYMBOL_TICK "
                    "(strategy/daytrade/lab/gremah_tick.py). capacidade_"
                    "negocio_mult/capacidade_fracao NAO transferem entre "
                    "simbolos (medido 2026-08-25, mesmo achado de profit_pct/"
                    "stop_multiplier) -- passe capacidade_negocio_mult= e "
                    "capacidade_fracao= explicitamente, ou meca este simbolo "
                    "em tick (IS + confirmacao OOS) e adicione-o a tabela "
                    "antes de operar com o default."
                )
            if capacidade_negocio_mult is None:
                capacidade_negocio_mult = capacidade.mult
            if capacidade_fracao is None:
                capacidade_fracao = capacidade.fracao
        self.capacidade_negocio_mult = abs(capacidade_negocio_mult)
        self.capacidade_fracao = abs(capacidade_fracao)
        self.capacidade_janela_dias = max(1, int(capacidade_janela_dias))
        self.capacidade_min_eventos = max(1, int(capacidade_min_eventos))
        # Sobrevive a `on_session_start` de proposito -- mesmo motivo de
        # `_janela_volume` (mesma classe): a capacidade e' medida em dias
        # ANTERIORES, nao deve zerar entre sessoes.
        self._janela_negocio_tipico = JanelaNegocioTipicoDiaria(self.capacidade_janela_dias)
        # Mesmo mecanismo/motivo de `Gremah.__init__` (mesma classe) -- ver
        # a docstring la para a justificativa completa: simbolo com par
        # (k,s) CONFIRMADO no OOS (`_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK`)
        # liga isto AUTOMATICAMENTE, so' se o chamador nao decidiu nada por
        # conta propria.
        if not alvo_por_volatilidade and alvo_vol_mult is None:
            override = _VOLATILITY_OVERRIDE_BY_SYMBOL_TICK.get(symbol)
            if override is not None:
                alvo_por_volatilidade = True
                alvo_vol_mult, override_stop_vol_mult = override
                if stop_vol_mult is None:
                    stop_vol_mult = override_stop_vol_mult
        if alvo_por_volatilidade and alvo_vol_mult is None:
            raise ValueError(
                "gremah_tick: alvo_por_volatilidade=True exige alvo_vol_mult "
                "explicito (o 'k' da regra alvo = k x range_mediano) -- sem "
                "default, precisa ser medido (ver scripts/daytrade/"
                "sweep_gremah_vol.py)."
            )
        self.alvo_por_volatilidade = alvo_por_volatilidade
        self.alvo_vol_mult = alvo_vol_mult
        self.vol_janela_dias = max(1, int(vol_janela_dias))
        self.stop_vol_mult = stop_vol_mult
        # Mesmo mecanismo/motivo de `Gremah.__init__` (mesma classe) -- ver
        # a docstring la para a justificativa completa.
        self.stop_frac_range = stop_frac_range
        # GEOMETRIA EM TICKS (2026-08-26). Ate' aqui, alvo/espacamento/stop
        # saiam TODOS de `profit_pct` (x `spacing_multiplier`, x
        # `stop_multiplier`), o que torna impossivel mexer em um sem arrastar
        # os outros: subir o alvo para escapar do piso de 1 tick subia o stop
        # na mesma proporcao. A grade de calibracao nunca conseguiu perguntar
        # "alvo de 2 ticks com o stop onde esta" -- so' "tudo maior junto".
        #
        # Estes tres sobrescrevem o resultado final, em ticks inteiros,
        # independentes entre si. `None` (o default) = nada muda, o caminho
        # antigo decide sozinho. Aplicados por ULTIMO em `_session_ticks`,
        # depois inclusive de `stop_frac_range`: mais explicito vence menos
        # explicito, a mesma hierarquia que o resto do arquivo ja usa.
        if (not _pct_explicito
                and profit_ticks is None and spacing_ticks is None and stop_ticks is None):
            geometria = _GEOMETRIA_TICKS_BY_SYMBOL_TICK.get(symbol)
            if geometria is not None:
                profit_ticks, spacing_ticks, stop_ticks = geometria
        self.profit_ticks = None if profit_ticks is None else max(1, int(profit_ticks))
        self.spacing_ticks = None if spacing_ticks is None else max(1, int(spacing_ticks))
        self.stop_ticks = None if stop_ticks is None else max(1, int(stop_ticks))

        self.quantity: int | None = None
        self._state = _SessionState()
        self._cash_atual_brl = 0.0
        # Sobrevive a `on_session_start` de proposito -- ver o comentario
        # equivalente em `Gremah.__init__` (mesma classe, mesmo motivo).
        self._janela_volume = RollingVolumeWindow(self.realocacao_janela_minutos)
        self._janela_vol = JanelaVolatilidadeDiaria(self.vol_janela_dias)

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()
        self._janela_volume.iniciar_sessao()

    def on_capital_update(self, cash_brl: float) -> None:
        self._cash_atual_brl = cash_brl

    def seed_volume_window(self, previous_session_tail: list[Bar]) -> None:
        self._janela_volume.definir_cauda_anterior(previous_session_tail)

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        # Mesmo padrao de `Gremah.seed_daily_volatility` -- SUBSTITUI, nunca
        # acumula (ver a docstring la).
        self._janela_vol = JanelaVolatilidadeDiaria(self.vol_janela_dias)
        for dia in previous_daily_bars[-self.vol_janela_dias:]:
            self._janela_vol.registrar_dia(dia)

    def seed_typical_trade_size(self, previous_daily_medians: list[float]) -> None:
        # Mesmo padrao de `seed_daily_volatility` acima -- SUBSTITUI, nunca
        # acumula.
        self._janela_negocio_tipico = JanelaNegocioTipicoDiaria(self.capacidade_janela_dias)
        for mediana in previous_daily_medians[-self.capacidade_janela_dias:]:
            self._janela_negocio_tipico.registrar_dia(None, mediana)

    def _ticks_from_pct(self, price: float, pct: float) -> int:
        return max(1, round(price * pct / self.tick_size))

    def _ticks_from_vol(self, mult: float) -> int | None:
        range_mediano = self._janela_vol.range_mediano()
        if range_mediano is None:
            return None
        return max(1, round(range_mediano * mult / self.tick_size))

    def _session_ticks(self, price_ref: float) -> tuple[int, int, int]:
        """Mesmo mecanismo de `Gremah._session_ticks` (mesma classe) -- ver
        a docstring la para a justificativa completa, inclusive
        `stop_frac_range` (aplicado por ultimo, independente do resto)."""
        profit_ticks = spacing_ticks = stop_ticks = None
        if self.alvo_por_volatilidade:
            profit_ticks = self._ticks_from_vol(self.alvo_vol_mult)
            if profit_ticks is not None:
                stop_mult = self.stop_vol_mult if self.stop_vol_mult is not None else self.stop_multiplier
                spacing_ticks = self._ticks_from_vol(self.alvo_vol_mult * self.spacing_multiplier)
                stop_ticks = self._ticks_from_vol(self.alvo_vol_mult * stop_mult)
        if profit_ticks is None:
            profit_ticks = self._ticks_from_pct(price_ref, self.profit_pct)
            spacing_ticks = self._ticks_from_pct(price_ref, self.profit_pct * self.spacing_multiplier)
            stop_ticks = self._ticks_from_pct(price_ref, self.profit_pct * self.stop_multiplier)
        if self.stop_frac_range is not None:
            stop_vol = self._ticks_from_vol(self.stop_frac_range)
            if stop_vol is not None:
                stop_ticks = stop_vol
        # Override EXPLICITO em ticks, por ultimo (ver `__init__`): quem passou
        # um numero inteiro de ticks quis exatamente aquele numero, e nenhum
        # dos caminhos acima -- percentual, volatilidade, `stop_frac_range` --
        # tem por que opinar depois disso.
        if self.profit_ticks is not None:
            profit_ticks = self.profit_ticks
        if self.spacing_ticks is not None:
            spacing_ticks = self.spacing_ticks
        if self.stop_ticks is not None:
            stop_ticks = self.stop_ticks
        return profit_ticks, spacing_ticks, stop_ticks

    def _arm_fixed_session_params(self) -> None:
        price = self._state.open_price
        profit_ticks, spacing_ticks, stop_ticks = self._session_ticks(price)
        self._state.profit_ticks_today = profit_ticks
        self._state.spacing_ticks_today = spacing_ticks
        self._state.stop_ticks_today = stop_ticks

    def _fills_of(self, side: str) -> int:
        return self._state.long_fills if side == "long" else self._state.short_fills

    def _next_side_to_arm(self) -> str | None:
        """Repete o lado do ULTIMO trade fechado se ele deu LUCRO; troca de
        lado se deu prejuizo (ou empatou em 0) -- mudanca de politica
        2026-08-27, substituindo a alternancia cega que valia ate' entao
        (fechou, tenta o outro lado, SEMPRE, sem olhar o resultado).

        Achado (linha de pesquisa `linha_diaria`, memoria do projeto
        `gremah-repetir-ultimo-vencedor-2026-08-26`): confirmado primeiro no
        motor M1 (`Gremah`, nunca aplicado la' -- decisao pendente do dono) e
        DEPOIS medido neste motor tick, dedicado (`GremahTickRepetirUltimo
        Vencedor`, subclasse de pesquisa, nunca em `src/`) -- bate a
        alternancia em 8 de 9 simbolos calibrados sob capital REAL e portao
        de capital LIGADO (mediana +27,8%), passa o nulo (sign-flip, custo
        sempre subtraido) com p<=0,0025 em 7/9 simbolos, sem zeramento novo
        em nenhum. Ressalva (mesma dos dois motores): CSAN3 fica fraco/
        inconclusivo (p=0,38 aqui, p=0,92 no M1 -- o mesmo simbolo falha nos
        dois motores); LPSB3 e' o unico com diferenca negativa aqui (nao
        significativa, p=0,37) -- nao e' 9/9 "provado", e' maioria forte e
        estavel entre os dois motores.

        Sem "ultimo trade" ainda (1a decisao da SESSAO -- `last_closed_side`/
        `last_trade_won` moram em `_SessionState` e resetam em `on_session_
        start`, ver la') cai na alternancia de sempre: `last_closed_side` no
        FIM da fila de candidatos. O rastreamento de vitoria/derrota vive no
        `on_bar` JA EXISTENTE (snapshot de `session_pnl_brl` na abertura e no
        fechamento da posicao), nao aqui -- este metodo so' LE o resultado."""
        candidates = ["long", "short"]
        last = self._state.last_closed_side
        if last in candidates:
            candidates.remove(last)
            if self._state.last_trade_won:
                candidates.insert(0, last)  # ganhou -- repete o mesmo lado primeiro
            else:
                candidates.append(last)  # perdeu (ou 1a decisao da sessao) -- alterna
        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None

    def _lotes_por_realocacao(self, anchor: float, ts: pd.Timestamp) -> int:
        """Quantos lotes a proxima entrada usa -- duas travas independentes,
        as DUAS derivadas do mercado observado, nenhuma fixa (pedido do
        dono, 2026-08-24: "o robo deve ser capaz de saber quantos que o
        mercado suporta... isso nao deve ser fixo, pq o mercado pode
        mudar").

        1. TETO DE PREENCHIMENTO -- quantos lotes cabem no negocio TIPICO
        recente (mediana de `RollingVolumeWindow.volumes_por_evento`) vezes
        `capacidade_negocio_mult`. Ate' 2026-08-24 isto era 10% da MEDIA de
        volume por minuto (`realocacao_teto_pct_volume_minuto`) -- a media
        e' inflada por um unico negocio de bloco (13x a mediana, medido na
        PMAM3) e por isso quase nunca mordia. So' cai no fallback antigo
        (media/minuto) quando a janela ainda nao tem NENHUM evento (inicio
        do historico) -- mediana de zero evento nao existe.

        2. TETO DE CAPACIDADE -- separado do de cima porque usa uma ANCORA
        ESTAVEL (mediana de negocio da sessao ANTERIOR inteira,
        `JanelaNegocioTipicoDiaria`, nao a janela intradia que oscila) para
        limitar o CAIXA que a formula de realocacao enxerga. Sem isto, mais
        caixa PIORA o resultado acima de uma certa capacidade (a formula
        manda usar mais lotes do que a liquidez sustenta -- medido: R$50 mil
        perdendo R$8.527 no OOS da PMAM3 onde R$2.500 ganhava R$885). Com o
        teto, qualquer caixa ACIMA da capacidade produz o MESMO resultado --
        o excedente fica comprovadamente inerte, disponivel pra saque sem
        perder lucro. `None` (primeiro pregao do historico, ou feed falhou)
        = sem capacidade estavel medida ainda, usa o caixa cru.

        SEMPRE ao menos 1 lote -- quem barra caixa genuinamente insuficiente
        e' o freio em `backtest.intraday.engine.run_intraday_backtest`, nao
        aqui."""
        custo_do_lote = anchor * LOTE_PADRAO_B3
        passo = self.realocacao_limiar_caixa * custo_do_lote

        eventos = self._janela_volume.volumes_por_evento(ts)
        if len(eventos) >= self.capacidade_min_eventos:
            teto_lotes = max(1, int(median(eventos) * self.capacidade_negocio_mult) // LOTE_PADRAO_B3)
        else:
            media_volume_min = self._janela_volume.media_por_minuto(ts)
            teto_acoes = media_volume_min * self.realocacao_teto_pct_volume_minuto
            teto_lotes = max(1, int(teto_acoes) // LOTE_PADRAO_B3)

        caixa = self._cash_atual_brl
        tipico_estavel = self._janela_negocio_tipico.tipico_mediano()
        if tipico_estavel is not None:
            teto_estavel_lotes = max(1, int(tipico_estavel * self.capacidade_negocio_mult) // LOTE_PADRAO_B3)
            capacidade_brl = self.capacidade_fracao * (teto_estavel_lotes - 1) * passo
            caixa = min(caixa, capacidade_brl)

        lotes = 1 + math.floor(caixa / passo)
        return min(teto_lotes, max(1, lotes))

    def _fatia_saida(self, ts: pd.Timestamp) -> int:
        """Tamanho de UMA fatia de saida (`EnterLimit.exit_split_unit`) --
        negocio TIPICO recente (mediana), nao mais `LOTE_PADRAO_B3` fixo
        (2026-08-24; `_dividir_pecas` abaixo e' a fatia de ENTRADA, virou 1
        lote fixo no mesmo dia e nao usa mais esta mediana). Ate' entao a saida
        fatiava em 100 acoes MESMO quando o negocio tipico do papel era
        maior (300 na PMAM3) -- 3x mais negocios no mercado do que
        precisava pra casar, sem ganhar nada de preenchimento com isso.
        Corrigir sozinho: participacao da PMAM3 no fluxo do ativo caiu de
        9,70% para 3,45% em R$50 mil (medido, IS), com lucro MAIOR em toda
        a faixa de capital testada. Mesmo minimo de amostra de
        `_lotes_por_realocacao` (`capacidade_min_eventos`) -- com poucos
        eventos, a mediana e' refem de um negocio de bloco isolado do mesmo
        jeito que a media era. `LOTE_PADRAO_B3` (o minimo, nunca
        fracionario) abaixo do minimo de amostra."""
        eventos = self._janela_volume.volumes_por_evento(ts)
        if len(eventos) < self.capacidade_min_eventos:
            return LOTE_PADRAO_B3
        return max(LOTE_PADRAO_B3, int(median(eventos)) // LOTE_PADRAO_B3 * LOTE_PADRAO_B3)

    def _dividir_pecas(self, quantidade_total: int) -> tuple[int, ...] | None:
        """Fatia `quantidade_total` (acoes, multiplo de `LOTE_PADRAO_B3`) em
        pedacos de 1 LOTE fixo cada (2026-08-24) -- nao mais o tamanho do
        negocio tipico (isso ainda decide a fatia de SAIDA, `_fatia_saida`,
        so' deixou de fazer sentido pra entrada). Um pedaco de 1 lote e' o
        PREFIXO ESTAVEL: pedir 7 lotes ou 30 lotes, os primeiros N pedacos
        sao IDENTICOS -- e' o que o dono pediu 2026-08-24 ("os mesmos que
        sao pegos em 118 deveria ser pegos independente do capital
        disponivel"), o antigo fatiamento por negocio tipico nao garantia
        isso (o TAMANHO de cada pedaco mudava com o total: 7 lotes viravam
        [3,2,2], 12 lotes viravam [3,3,3,3] -- nenhum prefixo em comum).
        Acima de `dividir_max_pecas`, os primeiros `dividir_max_pecas - 1`
        pedacos continuam de 1 lote (prefixo intacto); o ULTIMO absorve o
        excedente, so' pra nao mandar mais ordens reais simultaneas do que
        a corretora aguenta. `None` = nao ha' o que dividir (1 lote ou
        menos)."""
        total_lotes = quantidade_total // LOTE_PADRAO_B3
        if total_lotes <= 1:
            return None
        if total_lotes <= self.dividir_max_pecas:
            return (LOTE_PADRAO_B3,) * total_lotes
        pecas_unitarias = self.dividir_max_pecas - 1
        cauda_lotes = total_lotes - pecas_unitarias
        return (LOTE_PADRAO_B3,) * pecas_unitarias + (cauda_lotes * LOTE_PADRAO_B3,)

    def _build_entry(self, side: str, anchor: float, spacing_ticks: int, profit_ticks: int, stop_ticks: int | None, ts: pd.Timestamp) -> EnterLimit:
        self.quantity = self._lotes_por_realocacao(anchor, ts) * LOTE_PADRAO_B3
        split = self._dividir_pecas(self.quantity) if self.dividir_entrada else None
        spacing_off = spacing_ticks * self.tick_size
        level_price = round(anchor - spacing_off, 2) if side == "long" else round(anchor + spacing_off, 2)
        profit_off = profit_ticks * self.tick_size
        target_price = level_price + profit_off if side == "long" else level_price - profit_off
        stop_price = None
        if stop_ticks is not None:
            stop_off = stop_ticks * self.tick_size
            stop_price = level_price - stop_off if side == "long" else level_price + stop_off
        return EnterLimit(
            side=side,
            limit_price=level_price,
            initial_target=target_price,
            initial_stop=stop_price,
            quantity=self.quantity,
            reason="gremah_tick_" + side,
            split_quantities=split,
            # Mesmo `dividir_entrada` tambem fatia a SAIDA (2026-08-22,
            # pedido do dono): o alvo tinha o MESMO problema tudo-ou-nada
            # que a entrada -- ver `EnterLimit.exit_split_unit`. Fatia do
            # tamanho do negocio TIPICO (`_fatia_saida`), nao mais
            # `LOTE_PADRAO_B3` fixo (2026-08-24) -- ver a docstring de
            # `_fatia_saida` para o motivo.
            exit_split_unit=self._fatia_saida(ts) if self.dividir_entrada else None,
            exit_ttl_bars=self.exit_ttl_bars if self.dividir_entrada else None,
        )

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []
        is_fixed_phase = ts.time() < self.fixed_anchor_until

        # Armado no PRIMEIRO tick da sessao -- equivalente ao bloco
        # `session_stop_armed` da `Gremah` M1, so' que a perda-limite usa o
        # preco desse primeiro tick (aproximadamente a abertura).
        if state.session_start_ts is None:
            state.session_start_ts = ts
            state.session_stop_armed = True
            state.session_stop_brl_hoje = capital_minimo_brl(bar.open) * self.session_stop_pct_capital

        # Alimenta a janela de volume rolante com TODO tick visto, mesmo
        # fora de sinal de entrada -- ver o comentario equivalente em
        # `Gremah.on_bar` (mesma classe `RollingVolumeWindow`).
        self._janela_volume.registrar(ts, bar.volume)

        if is_fixed_phase and state.open_price is None:
            state.open_price = bar.open
            self._arm_fixed_session_params()

        if not state.session_halted and session_pnl_brl <= -state.session_stop_brl_hoje:
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if positions:
            if state.pending_side is not None:
                # 1a fatia de uma entrada nova (`positions` acabou de virar
                # nao-vazio) -- snapshot do P&L do dia ANTES deste trade, pra
                # `_next_side_to_arm` medir o round-trip inteiro no fechamento
                # (ver a docstring dela). So' roda aqui: fatias seguintes da
                # MESMA entrada (`dividir_entrada=True`) tem `pending_side`
                # ja' None e nao re-entram neste bloco.
                state.entry_session_pnl_brl = session_pnl_brl
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
                state.pending_since_ts = None
            return []

        if state.open_side is not None:
            # Posicao acabou de fechar por completo (ultima fatia, se
            # `dividir_entrada=True`) -- compara o P&L do dia agora contra o
            # snapshot da entrada: mede o LUCRO/PREJUIZO do round-trip
            # inteiro, nao de uma fatia isolada. `_next_side_to_arm` le' isto.
            state.last_trade_won = (session_pnl_brl - state.entry_session_pnl_brl) > 0.0
            state.last_closed_side = state.open_side
            state.open_side = None

        stale_fixed_order = state.pending_side is not None and state.pending_mode == "fixed" and not is_fixed_phase
        stale_rolling_order = (
            state.pending_side is not None and state.pending_mode == "rolling"
            and state.pending_since_ts is not None
            and (ts - state.pending_since_ts).total_seconds() >= self.rolling_reanchor_after_seconds
        )
        stale_order = stale_fixed_order or stale_rolling_order
        if state.pending_side is not None and not stale_order:
            return actions

        next_side = state.pending_side if stale_order else self._next_side_to_arm()
        if next_side is None:
            return actions

        state.pending_side = next_side
        state.pending_since_ts = ts
        state.pending_mode = "fixed" if is_fixed_phase else "rolling"
        if is_fixed_phase:
            entry = self._build_entry(
                next_side, state.open_price,
                state.spacing_ticks_today, state.profit_ticks_today, state.stop_ticks_today,
                ts,
            )
        else:
            anchor = bar.close
            profit_ticks, spacing_ticks, stop_ticks = self._session_ticks(anchor)
            entry = self._build_entry(next_side, anchor, spacing_ticks, profit_ticks, stop_ticks, ts)
        return [entry]
