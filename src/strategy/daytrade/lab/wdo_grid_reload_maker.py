"""Grid RELOAD maker adaptado para MINI-FUTURO WDO@ (2026-08-26) -- Frente
F1-wdo-consolidacao ("robo lucrativo em day trade de futuro, fora das
amarras da Copa BTG", ver o cabecalho da missao desta rodada).

MESMA mecanica central de `grid_reload_maker.py::GridReloadMaker`
(calibrada para ACAO -- PMAM3): uma ordem-limite (maker) fica parada a
`level_spacing_ticks` do preco de ABERTURA da sessao; se tocada, carrega
alvo (`profit_ticks`, maker tambem) e stop de protecao
(`stop_ticks`, a mercado); assim que a posicao fecha -- por alvo OU por
stop --, REARMA no MESMO nivel (nao avanca para um nivel mais distante
que pode nunca ser tocado), alternando de lado pelo lado que NAO acabou
de fechar. Este arquivo REESCREVE essa logica em vez de importar
`GridReloadMaker` de proposito -- regra desta rodada: nenhuma frente edita
arquivo compartilhado, e um import cruzado entre duas frentes rodando ao
mesmo tempo no mesmo diretorio de trabalho e' o mesmo risco de colisao
que editar o arquivo direto.

O candidato ORIGINAL, medido fora deste repo (ver o cabecalho da missao) e'
apelidado "T1 S16 x1": alvo 1 tick, stop 16 ticks, nivel a 1 tick (x1) do
preco de abertura, com confirmacao OOS (R$148,89/pregao IS+OOS, 89% de
retencao, ver `wdo-grid-reload-maker-top1-promocao-2026-08-27`).

2026-08-28, decisao do dono: o default de `stop_ticks` abaixo MUDOU de 16
para 4 apos a varredura completa profit_ticks/stop_ticks 1..20 (250
celulas, `scripts/daytrade/wdof1_grid_1a5_2026_08_28.py` e
`_6a20_2026_08_28.py`) achar que T1 S4 domina T1 S16 em toda metrica no IS
(liquido R$11.563,00 vs R$11.233,50, MaxDD R$72,00 vs R$121,50, calmar
160,60 vs 92,46) -- ver a memoria `wdof1-grid-1a20-encerrada-2026-08-28`.
RESSALVA que nao mudou com a troca: T1 S4 nunca foi medido no OOS. A
confirmacao OOS citada acima (R$148,89/pregao etc.) descreve especifica-
mente T1 S16, nao o default de entao.

2026-08-29, REVERTIDO de volta para 16: a ressalva acima se confirmou.
Rodando o historico COMPLETO salvo (177 pregoes, 2025-12-09 a 2026-08-28)
com CAIXA REAL (nao nocional) nos dois candidatos, T1 S4 nunca sobrevive ao
proprio historico com capital realista -- trava (fica abaixo do piso de
capital pra abrir 1 contrato, ver `LICOES_DE_PRODUCAO.md` item 1.14/3.9, e
NUNCA recupera dai em diante) em TODO nivel testado ate R$20.000, e so'
sobrevive com R$30.000 -- e mesmo assim fecha em +R$4.586,87 (líquido
R$-25.413,13 sobre R$30.000, quase so' devolvendo o capital). T1 S16
sobrevive o historico inteiro com so' R$5.000 e fecha estavel em
+R$2.671,80 líquido a partir dai (mesmo resultado de R$5.000 a R$30.000 --
uma vez que o caixa nao aperta mais, o robo nao depende de mais capital).
Win rate no mesmo teste: 65,7% (S4) contra 90,3% (S16) -- S4 e' uma
configuracao estruturalmente pior (razao risco:retorno 1:4 exige >80% de
acerto pra empatar; 65,7% fica abaixo disso), nao so' "medida numa amostra
diferente". Ver `scripts/daytrade/wdof1_stress_capital_real_historico_
completo.py` (achou o travamento) e a memoria `wdof1-stop-ticks-4-
producao-2026-08-28` (atualizada com a reversao). A confirmacao OOS citada
no paragrafo anterior (R$148,89/pregao, 89% de retencao) descreve T1 S16 --
default de `stop_ticks` desde entao, mas ver a nota abaixo sobre
`profit_ticks`.

2026-09-04, decisao do dono: `profit_ticks` mudou de 1 (T1) para 2 (T2) em
producao, mantendo `stop_ticks=16`. Motivo (item 4.8 de
`LICOES_DE_PRODUCAO.md`): a 1a operacao real deste robo derrapou 1 tick na
saida do alvo nativo -- com `profit_ticks=1` isso zera o bruto do trade por
inteiro (1 tick de deslize sobre 1 tick de alvo). Com `profit_ticks=2` o
mesmo deslize de 1 tick ainda deixa lucro (2-1=1 tick), sem mudar o stop
nem a mecanica de rearme. Efeito colateral conhecido: a razao risco:retorno
piora de 1:16 (T1/S16, breakeven ~94,1%) para 2:16 = 1:8 (T2/S16, breakeven
~88,9%) -- exige menos acerto pra empatar, mas cada acerto individual
tambem so' compensa metade dos erros que compensava antes. Ver
`scripts/daytrade/wdof1_alvo2_stop16_2026_09_04.py` (T2/S16 vs baseline no
IS, motor tick) e `scripts/daytrade/wdof1_alvo2_caixa_real_2026_09_04.py`
(ponto mais baixo do caixa acumulado contra os caixas reais R$300/R$375)
para a medicao que acompanhou a decisao.

2026-09-09, decisao do dono: `stop_ticks` mudou de 16 para 6 (T2/S6), com
`profit_ticks=2` intacto. O que mede: varredura de `stop_ticks` com o alvo
FIXO em T2, sobre o motor CORRIGIDO (`fatiar_saida_alvo=True`, que e' o que
roda em producao desde `317e839` -- as varreduras de 2026-08-28 rodaram no
motor que dava o alvo de graca e estao invalidadas como seletor), capital
real R$375, janelas do IS sem sobreposicao. Scripts no scratchpad da sessao
(`bateria_wdof1_stop_2026_09_09.py`), tabelas em `mini.log`/`mes.log`.

O ARGUMENTO QUE DECIDIU e' de sobrevivencia, nao de lucro: a perda por stop
cai de R$85,50 (16 ticks + 1 tick de deslize do stop + R$0,50) para R$35,50,
e o numero de derrotas SEGUIDAS que R$375 aguenta sobe de **2 para 7**. Com
S16 o robo cala em duas derrotas seguidas -- e foi exatamente assim que ele
morreu na fatia de 13-26/03 (5 stops em 22 trades no primeiro pregao, caixa
em R$74,00, 22 trades no mes inteiro contra ~4.000 das celulas vivas).
Breakeven cai de 90,00% para 78,89%.

Medido em 21 pregoes (06/04 a 06/05, pregoes 26-46 do IS), caixa reposto por
pregao (desenho que isola geometria de composicao): win% 85,16%
[84,39;85,94] contra breakeven 78,89% -- IC inteiro ACIMA; EV/trade a 1
contrato +R$2,82; media R$1.393,52/dia com desvio R$292,64; **21 de 21
pregoes positivos**, pior dia +R$760,00; menor desvio de EV entre semanas
das tres finalistas (0,29 contra 0,46 do T2/S10 e 0,76 do T3/S6).

RESSALVAS que continuam abertas, todas informadas ao dono antes da decisao:
1. A vantagem sobre T2/S10 NAO e' estatisticamente separavel -- os IC do
   EV/trade se sobrepoem ([+2,47;+3,17] contra [+2,06;+3,04]). O que separa
   e' consistencia semanal, nao superioridade demonstrada.
2. T2/S6 PERDE no drawdown: pior queda 45,5% contra 18,8% do T2/S10.
3. A janela e' de 21 pregoes, nao os 72 do IS, e o OOS segue intocado. Uma
   recomendacao anterior (T3/S6) veio de 10 pregoes e NAO sobreviveu a 21 --
   o mesmo pode acontecer com esta.
4. O teto `max_trades_per_side` corta 35,9% dos trades do T2/S6 (15 de 21
   pregoes saturados; faria 624/dia contra os 388 medidos). E' o mais
   estrangulado dos tres candidatos, e o numero acima e' o estrangulado.
5. R$1.393/dia sobre R$375 NAO e' expectativa de retorno: sao 388
   round-trips/pregao apoiados numa suposicao de fila que nunca foi medida
   do lado da SAIDA (item 6.19), mais o otimismo do TTL (saida por estouro
   de prazo fecha a mercado com `reason=TARGET` e nao paga deslize). Os
   numeros comparam celulas entre si; nao descrevem retorno.

EFEITO COLATERAL no dimensionamento, consequencia direta e desejada: o teto
por RISCO (`risco_pct_por_trade=0,01`) e' `1% do caixa / risco em R$ por
contrato`, e o risco por contrato cai de R$80,00 (16 ticks) para R$30,00 (6
ticks). O marco do 2o contrato desce de R$16.000 para R$6.000 de caixa, o do
3o para R$9.000. O robo passa a escalar MUITO mais cedo -- coerente, porque
cada contrato agora arrisca menos, mas e' uma mudanca de exposicao que nao
foi medida separadamente. Ver `tests/test_wdo_grid_reload_maker.py::
test_marcos_de_escala_de_contrato_na_config_de_producao`.

2026-09-04, CORRIGIDO bug real (item 4.9 de `LICOES_DE_PRODUCAO.md`): no
modo `reanchor_mode="rolling_last_price"` (o DEFAULT), `on_bar` recalculava
a ancora SO' no instante em que a `EnterLimit` era armada -- depois disso,
enquanto a ordem ficava pendente (sem preencher), a funcao devolvia cedo
(`if state.pending_side is not None: return actions`) e a ordem ficava
ESTACIONADA pelo resto do pregao se o preco se afastasse e nao voltasse a
tocar nela: nunca era reprecificada, nunca era cancelada. Medido com dado
real de tick MT5 na semana de 2026-08-31 a 2026-09-04: o robo ficou
"ativo" (1a entrada ate' ultima saida) so' 0%/8,0%/14,3%/11,1%/0% de cada
um dos 5 pregoes -- em 2 desses 5 dias (31/08 e 04/09) operou 1 vez ou
NENHUMA vez, apesar do mercado andar 24 e 41,5 pontos nesses dias; as 177
entradas da semana inteira couberam em so' 11 niveis de preco. Pedido do
dono: "se nao bater no preco e surgir outro sinal, a [ordem] pendente deve
ser cancelada e a do novo sinal deve ser aberta" -- como este robo nao tem
logica direcional separada da ancora (o "sinal" E' o nivel derivado dela),
o fix e' reancorar em TODA barra (nao so' no instante de armar), MESMO com
ordem pendente, e reemitir a `EnterLimit` no nivel atualizado para o MESMO
lado que ja estava pendente (o lado nunca muda, so' o preco da ordem). O
motor (`backtest.intraday.machine.IntradaySessionMachine`) ja' trata isso
como cancela-e-substitui (`LimitPlaced(replaced=...)`/`LimitCancelled(...,
reason="superseded")`) quando o nivel recalculado difere do que esta'
parado, e como NO-OP (`_reancoragem_no_mesmo_nivel`, preserva fila/TTL
acumulados) quando bate no mesmo nivel -- MESMO mecanismo que o rearme por
tempo de `Gremah` (`rolling_reanchor_after_bars`) ja' usa, nenhum evento
novo foi criado. Escopo do fix e' so' o modo `rolling_last_price` --
`fixed_session_open` continua devolvendo cedo por desenho (ancora fixa a
vida toda da sessao). Sem timeout/limiar de distancia minima novo (nao foi
pedido) -- ver o relatorio desta rodada para a contagem de reprecificacoes
por pregao medida com dado tick, que e' a informacao que falta para o dono
decidir se um limiar faz sentido depois.

2026-09-07, FREIO DE CADENCIA (`reancora_min_segundos`, ver `__init__`): a
contagem que o paragrafo acima deixou pendente foi medida, e ela BLOQUEAVA o
deploy do item 4.9 como estava. Motor tick, capital real R$375, pregoes
INTEIROS (09:00-18:29 BRT, cache `data/raw_ticks/WDO_A_.parquet`):

    pregao      envios/pregao   pior janela de 60s   trava o robo?
    2026-03-02       45.309             1.406             SIM
    2026-03-04       51.142             1.020             SIM
    2026-03-06       72.852             1.458             SIM
    2026-03-09       75.933             3.446             SIM
    2026-08-28       38.260             1.162             SIM

Cada `LimitPlaced` e' um `place_limit` ao vivo, e o runtime tem teto de
envio por janela ROLANTE de 60s. ATENCAO ao ler os numeros acima: ate'
2026-09-08 o teto era um DISJUNTOR unico de 30 (`MAX_ENVIOS_POR_MINUTO`) --
estourar nao recusava so' a ordem, ligava `disaster_halt` e PARAVA o robo
pelo resto do pregao, e nos pregoes medidos isso acontecia no PRIMEIRO
minuto de negociacao (12:01 UTC = 09:01 BRT). Desde 2026-09-08 sao DOIS
tetos (`live.intraday_runtime.COTA_ENVIOS_POR_MINUTO` = 120, que recusa
so' a ordem excedente e deixa o robo vivo, e
`MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO` = 600, que continua sendo disjuntor).
As enxurradas da tabela acima (1.020 a 3.446 no pior minuto) atravessam os
DOIS -- continuam sendo motivo suficiente para o freio existir na
estrategia.

Sao DUAS fontes de enxurrada, nao uma, e o freio tapa as duas com a mesma
constante:

1. REPRECIFICACAO -- o item 4.9 reancora a ordem pendente a cada barra, e
   `feed_kind="tick"` faz "cada barra" ser CADA NEGOCIO. Metade dos envios
   acima sao substituicoes (`_pode_reprecar`).
2. REARME APOS RECUSA -- quando o caixa cai abaixo do piso de 1 contrato, o
   motor recusa toda entrada, `on_order_rejected` zera `pending_side`, e o
   robo arma ordem NOVA no tick seguinte. 2026-03-04: 25.556 recusas por
   capital num pregao so'. Esta metade NAO passa pela reprecificacao (nao
   ha' ordem pendente para reprecar) e por isso tem portao proprio
   (`_pode_armar_apos_recusa`).

   ATENCAO ao numero: esse piso e' a MARGEM CRUA (R$150 no WDO@), nao os
   R$375 da pilha cheia -- ver `strategy.daytrade.base.
   contracts_from_capital_operacional` (2026-09-08). Ate' aquela data o
   motor cobrava a pilha inteira a cada entrada, e um unico stop de R$80
   sobre um caixa que comecou nos R$375 de partida calava o robo para
   sempre. As contagens de recusa medidas ANTES de 2026-09-08 (inclusive as
   25.556 acima) foram tiradas sob a regra antiga.

Efeito colateral que NAO era esperado e importa mais que o freio: sem o
freio o robo quase nao NEGOCIA. Reprecar a cada tick mantem a ordem sempre a
1 tick do preco corrente, entao ela persegue o mercado e quase nunca e'
tocada -- 2026-03-02 fecha com 5 trades e R$-47,50 sem freio, contra 264
trades e R$+1.078,00 com o freio de 6s. O freio nao e' um custo pago pela
seguranca: ele RESTAURA a mecanica de ordem parada que da' nome ao robo.

2026-09-08, HISTERESE ANTI-PINGUE-PONGUE (`reancora_min_ticks`, default
1 -> 2): o freio de cadencia acima limita QUANTAS substituicoes saem por
minuto, mas nada olhava PARA ONDE elas iam. No 1o pregao com o item 4.9 ao
vivo (slot `dt-wdo_grid_reload_maker-wdo@-live`, `live_events`), o robo
emitiu 125 linhas `LIMITE` para 22 rodadas -- 103 delas `(substitui)`. A
rodada #21 e' o retrato:

    LIMITE LONG #21 ... @ 5105,0 (stop 5097,0 / alvo 5106,0)
    LIMITE LONG #21 ... @ 5105,5 ... (substitui)
    LIMITE LONG #21 ... @ 5105,0 ... (substitui)
    LIMITE LONG #21 ... @ 5105,5 ... (substitui)
    LIMITE LONG #21 ... @ 5106,5 ... (substitui)
    LONG #21 1 lote WDO@ @ 5106,5

Tudo isso no MESMO segundo de parede (15:00:44 UTC). O par 5105,0/5105,5 se
repete: a ordem volta para um nivel que ela mesma acabou de abandonar, e
cada volta e' um cancela+reenvia real que joga fora a fila ja' acumulada --
num robo MAKER a fila e' o produto (ver `queue_ahead_qty` em `backtest.
intraday.machine` e o comentario de `_reancoragem_no_mesmo_nivel`). Nenhuma
das 103 era identica a' IMEDIATAMENTE anterior, entao a guarda de no-op do
motor nao tinha o que pegar. Veredito do dono: "substituiu 3 vezes para o
mesmo preco, mesmo stop e mesmo alvo, isso e' uso de recurso desnecessario,
neste caso nao deve substituir".

Dois motivos, e o segundo e' o que a histerese conserta:
  1. o freio de 10s mede `bar.ts`, e a maquina estava reprocessando fila
     atrasada -- no relogio do TICK aquelas 4 substituicoes estavam a
     minutos uma da outra. Quem passou a ler o relogio de PAREDE foi o
     contador de envios do runtime (`live.intraday_runtime.
     _check_cadencia_de_ordens`, mesmo dia), que protege a corretora. O
     freio da estrategia segue em `bar.ts` de proposito -- e' regra de
     ESTRATEGIA e tem de valer identica no backtest.
  2. deriva de 1 tick nao e' preco andando, e' troca de ponta do book. 65
     das 103 substituicoes moveram a ordem exatamente 1 tick; 49 devolveram
     a ordem a um nivel que a MESMA rodada ja' tinha ocupado.

A regra nova (`_pode_reprecar`): o nivel candidato tem de estar a pelo menos
`reancora_min_ticks` ticks do nivel PARADO **e** do ultimo nivel ABANDONADO
na rodada. Sobre a sequencia registrada nesse pregao isso derruba 125 envios
para 53, e o pior minuto de PAREDE de 64 para 21 -- de mais que o dobro do
teto que vigorava naquele dia (30, disjuntor: parava o robo pelo pregao
inteiro) para 30% de folga. Desde 2026-09-08 os dois cabem na cota de vazao
de 120 (`live.intraday_runtime.COTA_ENVIOS_POR_MINUTO`). Nao mexe em geometria (T2/S16 intacto) nem no rearme
pos-fill. Vale nos DOIS motores por construcao: a regra e' da estrategia,
que e' o mesmo objeto no backtest e ao vivo.

`tick_size` NAO tem default de instrumento nenhum
embutido aqui (fica 0.5, o `price_tick_size` do WDO@ documentado em
`backtest.intraday.profiles`, so' como conveniencia) -- quem instancia
para rodar de verdade sempre passa o tick vindo do PERFIL
(`profile_for("WDO@").price_tick_size`), nunca hardcoded numa segunda vez
(mesmo argumento do modulo `profiles.py`: um numero declarado em dois
lugares e' um numero que vai divergir).

Tres diferencas deliberadas frente ao original de acao:

1. `reanchor_mode` (ver `ReanchorMode` abaixo) -- dimensao que
   `GridReloadMaker` (acao) NAO tem, porque nunca precisou dela: o robo de
   acao sempre foi medido com ancora FIXA (`open_price` da sessao, uma vez
   so'). ACHADO desta frente (checagem de sanidade em
   `wdo_grid_reload_f1_lab.py`): reproduzir essa MESMA ancora fixa em
   WDO@ da' liquido NEGATIVO no IS (win rate ~84%, abaixo do breakeven de
   ~94,1% que a razao risco:retorno 1:16 exige) -- fica LONGE do ballpark
   conhecido (+R$37.606,53). Reancorar de forma ROLANTE (ao FECHAMENTO da
   barra em que cada ordem e' armada, mesmo espirito do modo "rolling" de
   `Gremah`) melhora win rate para ~89% e chega perto do breakeven, mas
   TAMBEM nao reproduz o ballpark -- fica o DEFAULT por ser a leitura mais
   proxima das duas, NAO por ter sido validada como a mecanica correta.
   Ver o relatorio desta frente para o veredito completo (nenhuma das
   leituras tentadas reproduziu o numero conhecido; a diferenca continua
   sem explicacao e fica registrada para uma proxima rodada investigar).
2. `session_stop_brl` DEFAULT `None` (desligado), nao herdado do default
   de acao (30.0 -- calibrado para PMAM3, tick de R$0,01, onde 20-30
   ticks de stop custam uma fracao de real). No WDO@ o tick vale R$5,00
   (0,5 pt x R$10,00/pt): SOZINHO, um stop de 16 ticks custa ~R$80,00 por
   contrato -- um `session_stop_brl=30` herdado desligaria a sessao
   inteira depois da PRIMEIRA perda parcial, o que nao e' o desenho que
   esta sendo medido ("alvo 1 tick, stop 16 ticks, espacamento x1", sem
   mencao de teto agregado de sessao). Fica opcional: quem quiser testar
   um teto de sessao passa o valor explicito, e o proprio teste de
   sensibilidade a pedagio desta frente NUNCA precisa dele.
3. `max_trades_per_side` default bem mais alto (200 contra 15 na acao) --
   ATENCAO (2026-09-07): este teto DEIXOU DE SER FOLGADO. Ver a nota de
   2026-09-07 abaixo e a docstring de `reancora_min_segundos` -- depois do
   item 4.9 ele morde de verdade (6 de 43 pregoes medidos fecham exatamente
   200+200 = 400 trades) e, mais importante, e' ele que limita quantos
   REARMES pos-fill o robo manda por minuto. O pior minuto medido no
   default do freio (26 envios em tempo de TICK; 42 na medicao IS/OOS de
   2026-09-08) e' 100% rearme pos-fill num pregao saturado. Ate'
   2026-09-08 isso batia num teto de 30 que TRAVAVA o robo pelo pregao
   inteiro; hoje bate na cota de vazao de 120
   (`COTA_ENVIOS_POR_MINUTO`), que so' recusa a ordem excedente -- subir
   `max_trades_per_side` ainda empurra o pico e ainda custa ordem
   recusada, so' nao cala mais o robo. Nao suba sem re-medir o pior
   minuto. O texto original
   abaixo (calibrado quando o robo fazia ~41 trades/dia) fica por
   historico --
   o WDO@ tem ~570 barras M1/pregao (perfil medido) e, no modo rolante,
   rearma com muito mais frequencia que a acao (~41 trades/dia medidos
   contra ~14 na PMAM3) -- um teto baixo herdado apertaria essa frequencia
   de um jeito que nao foi o que se pretende medir aqui. Alto o bastante
   para nao morder em uso normal (o proprio script de medicao desta frente
   confere `ordens_recusadas_por_teto`/`max_trades_per_side` batido contra
   o numero de trades real, para o teto nunca decidir o resultado em
   silencio).

`quantity=None` (default) deixa o MOTOR decidir via
`IntradayBacktestConfig.default_quantity` -- 1 CONTRATO fixo por ordem, a
restricao real do dono nesta rodada (ver o cabecalho da missao: "so'
consegue operar 1 contrato no comeco"). A futura frente de escalonamento
por MARGEM antecipada aqui chegou em 2026-08-27 (`margin_per_contract_brl`,
ver abaixo) -- este paragrafo original fica registrado por historico, mas
o comportamento de 1 contrato fixo continua sendo o DEFAULT.

## Realocacao dinamica por CAPITAL (2026-08-27, ADITIVA e OPT-IN)

Equivalente, em FUTURO, do `_lotes_por_realocacao` de `Gremah` (caixa
acumulado -> mais contratos na proxima entrada, encolhe de volta se o
caixa cair) -- via `contracts_from_capital` (`strategy.daytrade.base`),
ja usado de forma ESTATICA (calculada 1x na config do backtest) em
`backtest.intraday.profiles.config_for`. Aqui vira DINAMICO: recalculado
a CADA `EnterLimit`, nao 1x por rodada.

Por default (`margin_per_contract_brl=None`) este modo nao existe e o
comportamento e' byte-a-byte o de antes: `quantity` (que pode ser `None`)
viaja direto para `EnterLimit`, exatamente como sempre foi. So' quem passa
`margin_per_contract_brl` explicito ativa a realocacao -- e nesse modo
`self.quantity` e' IGNORADO por completo: os dois parametros sao
MUTUAMENTE EXCLUSIVOS (capital dinamico OU quantidade fixa, nunca os dois
juntos disputando qual manda na mesma ordem). `hard_cap_contratos`
(opcional) e' o teto SUPERIOR do resultado de `contracts_from_capital` --
sem ele a formula cresce sem limite conforme o caixa sobe, o que nao faz
sentido para um instrumento com teto OFICIAL de contratos simultaneos
(ex.: 5 no WDO@, `profile_for("WDO@").max_open_contracts`).

`on_capital_update` segue o MESMO padrao ja usado por `Gremah`
(`_cash_atual_brl`, atualizado pelo motor logo antes de cada `on_bar`,
comeca em 0.0) -- ANTES da primeira barra real, ou quando o replay de
`warm_start_calibration` roda sem `cash_brl` (default `None`, comportamento
antigo), o hook nunca e' chamado: `contracts_from_capital(0.0, ...)` devolve
0, e o `max(1, ...)` aplicado no ponto de uso garante pelo menos 1 contrato
mesmo assim (mesmo espirito do piso ja existente em `Gremah._lotes_por_
realocacao`). Desde 2026-09-03 (LICOES_DE_PRODUCAO.md item 3.14),
`warm_start_calibration` TAMBEM chama `on_capital_update` a cada barra do
replay quando o CHAMADOR passa `cash_brl` -- `live/intraday_runtime.py::
_start_session` passa o caixa real (`initial_capital + realized_pnl`) num
restart no meio do pregao, entao o teto dinamico volta a valer desde a
PRIMEIRA entrada recalibrada, em vez de ficar preso no piso de 1 contrato
ate a proxima barra ao vivo.

## Incidente REAL de 2026-08-28 -- teto agregado passou a morar no MOTOR

Este robo (WDO@, capital real R$300, primeira operacao ao vivo) ZEROU a
conta: saldo final -R$298,60, equity NEGATIVA. Forense confirmado no MT5:
dois deals de ABERTURA (`475209192` 11:58:59, `475209197` 11:59:04, mesmo
magic, volume 1 cada) -- duas entradas INDEPENDENTES, consolidadas pela
conta NETTING numa posicao de -2 contratos. Com 2 contratos a margem
exigida dobrou, a margem livre ficou negativa, e a corretora recusou ate a
ordem de FECHAMENTO (`[MG51] Para abrir novas posicoes`) -- a conta ficou
presa numa posicao perdedora sem conseguir sair.

A causa NAO estava neste arquivo -- `_next_side_to_arm`/`state.pending_side`
ja impediam esta estrategia de pedir uma segunda entrada enquanto a primeira
ainda estivesse pendente ou aberta. A causa era a config REAL ao vivo
carregar `max_open_contracts=5` (o teto REGULATORIO da Copa BTG, sem
nenhuma relacao com o caixa real de R$300) como UNICO teto agregado do
motor -- duas entradas independentes (de QUALQUER origem: bug de execucao,
race, retomada de processo) passavam por ele sem problema.

O fechamento (2026-08-28): `backtest.intraday.machine.IntradaySessionMachine`
ganhou um teto DINAMICO por CAPITAL (`IntradayBacktestConfig.margin_per_
contract_brl`/`margin_buffer`), recalculado a cada barra contra o caixa DE
VERDADE, com uma reserva de seguranca adicional (`strategy.daytrade.base.
RESERVA_CAIXA_SEGURANCA`) -- e `backtest.intraday.profiles.config_for` liga
isso por PADRAO para todo perfil de futuro com margem conhecida, o mesmo
caminho que `scripts/run_live.py::build_intraday` usa para montar a config
real. `_quantidade_da_entrada` abaixo tambem passou a usar
`contracts_from_capital_com_reserva` (em vez da versao pura) no modo
dinamico opt-in, para o que este robo PEDE nunca ficar mais otimista do que
o motor de fato deixa abrir -- mas quem tem a palavra final sobre recusar
uma entrada por capital insuficiente e' sempre o MOTOR, nao esta classe."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    MARGIN_BUFFER_FUTUROS,
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    contracts_from_capital_com_reserva,
    contracts_from_risk,
    no_tick,
)

#: Tick de PRECO do WDO@ (contrato cheio WDOV26, 0,5 pt) -- a serie
#: continua do MT5 reporta 0,001, errado para posicionar ordem (ver
#: `backtest.intraday.profiles.SymbolProfile.price_tick_size`). So' um
#: DEFAULT de conveniencia para quem instancia sem passar o valor do
#: perfil -- rodar de verdade sempre passa `tick_size=` explicito, vindo
#: de `profile_for("WDO@").price_tick_size`.
WDO_TICK_SIZE = 0.5


@dataclass
class _SessionState:
    open_price: float | None = None
    anchor_price: float | None = None  # referencia ATUAL do nivel -- ver `ReanchorMode`
    session_halted: bool = False
    pending_side: str | None = None  # lado da EnterLimit pendente (ainda nao preenchida), ou None
    open_side: str | None = None  # lado da posicao CONFIRMADA aberta agora, ou None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None  # qual lado acabou de fechar (pra decidir o proximo a recarregar)
    # Freio de reprecificacao (2026-09-07) -- ver `reancora_min_segundos`/
    # `reancora_min_ticks` em `__init__`. `pending_level` e' o preco da
    # `EnterLimit` que esta' de fato parada no book agora (a ULTIMA emitida);
    # `pending_level_ts` e' quando ela foi emitida. Os dois so' fazem sentido
    # juntos com `pending_side` -- zerados no mesmo lugar que ele.
    pending_level: float | None = None
    pending_level_ts: pd.Timestamp | None = None
    # Nivel que a ULTIMA substituicao desta rodada TIROU do book (2026-09-08,
    # histerese anti-pingue-pongue -- ver `reancora_min_ticks` em `__init__`).
    # E' a memoria que impede a ordem de VOLTAR para um nivel que ela acabou
    # de abandonar: cada volta dessas e' um cancela+reenvia real que joga
    # fora a fila ja acumulada no nivel novo para reentrar no FIM da fila de
    # um nivel velho. `None` enquanto a rodada nunca substituiu nada --
    # zerado junto com `pending_level` (fill/recusa: rodada nova nao herda
    # memoria de rodada velha).
    nivel_abandonado: float | None = None
    # Quando a ULTIMA `EnterLimit` foi RECUSADA (motor: teto de capital;
    # ao vivo: margem/corretora). Existe para o freio segurar o REARME
    # depois de uma recusa -- ver `_pode_armar_apos_recusa`. `None` quando a
    # ultima coisa que aconteceu com uma ordem foi um FILL, nao uma recusa.
    ultima_recusa_ts: pd.Timestamp | None = None


#: Duas formas de ancorar o nivel do grid -- ver a checagem de sanidade em
#: `wdo_grid_reload_f1_lab.py` para o que cada uma mediu de fato:
#:   "fixed_session_open" -- a ancora e' o preco de ABERTURA da sessao, uma
#:       vez, nunca muda (mesma mecanica de `grid_reload_maker.py::
#:       GridReloadMaker`, calibrada para PMAM3). Medido: liquido NEGATIVO
#:       no IS do WDO@.
#:   "rolling_last_price" -- a ancora e' o FECHAMENTO da barra em que a nova
#:       ordem e' armada (rearma seguindo o preco, mesmo espirito do modo
#:       "rolling" de `Gremah`/`gremah.py::on_bar`). Medido: mais proximo do
#:       breakeven que o modo fixo, mas AINDA nao reproduz o ballpark
#:       conhecido (+R$37.606,53) -- fica o DEFAULT por ser a leitura menos
#:       ruim das duas testadas, nao por ter sido confirmada como a
#:       mecanica original.
#: Ver a docstring do modulo para o relato completo da investigacao.
ReanchorMode = Literal["fixed_session_open", "rolling_last_price"]

#: Prazo, EM BARRAS DESTE ROBO, que a fatia de SAIDA do alvo
#: (`fatiar_saida_alvo=True`) espera parada como ordem-limite antes do motor
#: cancelar e fechar o RESTANTE a mercado -- `EnterLimit.exit_ttl_bars`, so'
#: consumido quando `fatiar_saida_alvo=True`.
#:
#: **"BARRA" AQUI E' UM NEGOCIO, NAO UM MINUTO.** Este robo declara
#: `feed_kind="tick"` (ver o atributo na classe): cada barra e' CADA NEGOCIO,
#: e o motor conta o prazo em TODA barra desde que armou, tocando ou nao.
#: Medido na base canonica do WDO@: 159.440 barras num pregao, intervalo
#: MEDIANO de 62 ms entre elas. Ou seja, 8 barras aqui e' da ordem de MEIO
#: SEGUNDO -- nao 8 minutos. Quem ler "prazo 8" pensando em minutos erra a
#: escala por ~1000x, e foi exatamente esse o erro na primeira versao deste
#: comentario (2026-09-09).
#:
#: VALOR EMPRESTADO de `gremah.py::EXIT_TTL_BARS_PADRAO` (duplicado aqui em
#: vez de importado -- feature nao importa feature, mesmo padrao de
#: `strategy.daytrade.lab.gremah_tick.EXIT_TTL_BARS_PADRAO`). O emprestimo e'
#: pior do que parece e vale registrar: a `gremah` roda `feed_kind="m1"` (o
#: default), entao o 8 DELA e' 8 MINUTOS, varrido 1..10 em PMAM3 (acao de
#: centavos, fila lenta). Trazer o mesmo "8" para ca' nao trocou so' de
#: instrumento -- trocou de UNIDADE.
#:
#: Varrido depois no proprio WDO F1 (`scripts/daytrade/
#: wdof1_exit_ttl_bars_micro_2026_09_09.py`, T2 fatiado, 10 pregoes do IS,
#: capital real): ttl=1 e' claramente ruim (R$9,6k contra R$13-16k do resto)
#: e de 2 pra cima a curva e' SERRILHADA -- vizinhos diferem mais entre si
#: (5:R$13,7k, 6:R$14,8k, 10:R$16,5k, 12:R$14,7k) do que a tendencia da faixa
#: inteira, ou seja, 10 pregoes nao separam o parametro. Decisao do dono
#: (2026-09-09): MANTER 8. O que a varredura mede de verdade e' o PRECO da
#: valvula: ttl 8 da' R$14,9k contra R$21,0k do "sem prazo" (referencia
#: nao-operavel -- limite sem prazo e' exposicao indefinida), ~30% do lucro.
#:
#: **2026-09-09, de 8 para 60** (proposta do dono: "não seria melhor trocar de
#: 8 para 20 para aguardar mais e só então sair a mercado? isso não aumentaria
#: as chances de sair com limite?"). A pergunta dele e' sobre TAXA DE
#: PREENCHIMENTO, nao sobre P&L -- e taxa e' estavel onde o P&L era ruido.
#: Medida em `scripts/daytrade/wdof1_ttl_taxa_de_fill_2026_09_09.py` (T2
#: fatiado, 10 pregoes do IS, capital real), a curva sai MONOTONICA:
#:
#:     ttl |  ~tempo | % preenche na limite | saidas a mercado | deslize R$
#:       5 |    0,3s |                80,3% |              727 |   2.915,00
#:       8 |    0,5s |                84,1% |              586 |   2.375,00
#:      12 |    0,7s |                87,9% |              439 |   1.620,00
#:      20 |    1,2s |                88,9% |              412 |   1.875,00
#:      30 |    1,9s |                90,1% |              369 |   1.650,00
#:      60 |    3,7s |                92,8% |              264 |   1.040,00
#:     130 |    8,1s |                93,6% |              239 |   1.510,00
#:
#: O dono estava certo na direcao: 8 -> 20 sobe o preenchimento 4,8pp. Ficou
#: em 60 porque o trecho 20 -> 60 rende MAIS que o 8 -> 20 (+3,9pp) e derruba
#: o deslize de R$1.875 para R$1.040 -- menos da metade do que o 8 pagava.
#: Depois de 60 a curva achata (130 so' acrescenta 0,8pp e o deslize sobe de
#: novo), entao nao ha motivo para ir alem.
#:
#: Por que isto tambem e' SEGURANCA, e nao so' lucro: cada estouro de prazo
#: manda uma ordem A MERCADO enquanto a ordem-limite pode ainda estar viva no
#: livro. Foi essa colisao que abriu um short de 2 contratos numa conta de 1
#: em 2026-09-09 (item 1.24). Menos estouro e' menos exposicao a esse modo de
#: falha -- e o guard de `machine._resolve_live_split_exit` (nao manda mercado
#: sem cancelamento CONFIRMADO) e' a outra metade da correcao.
EXIT_TTL_BARS_PADRAO_FATIA = 60


class WdoGridReloadMaker(IntradayStrategy):
    """Grid maker com recarga do mesmo nivel apos cada fechamento (alvo ou
    stop largo), calibrado para o mini-futuro WDO@ -- ver a docstring do
    modulo para a mecanica completa e o porque de nao herdar/importar
    `GridReloadMaker` (acao)."""

    name = "wdo_grid_reload_maker"
    version = "0.1"
    symbol = "WDO@"
    is_futuro = True
    # A saida por alvo deste robo e' uma ordem-limite parada no nivel: e' o
    # centro do desenho (capturar o spread em vez de paga-lo), nao um
    # detalhe de modelagem. Ver `IntradayStrategy.target_fills_as_maker`.
    target_fills_as_maker = True
    # CORRIGIDO 2026-08-27 (era "m1", herdado de quando este modulo so'
    # tinha a checagem de sanidade em M1): a consolidacao F1 (leitura tick)
    # achou que o numero em M1 e' dominado por um artefato de
    # `machine.py::_exit_fill_price` (a barra de 1 minuto "melhora" o preco
    # de saida sempre que abre alem do alvo de 1 tick -- com alvo tao
    # apertado isso acontece o tempo todo). Em tick esse artefato cai para
    # 1,6% do lucro. O numero VALIDADO (R$148,89/pregao IS+OOS, 89% de
    # retencao no OOS, 30/30 blocos de 4 pregoes positivos) e' o de TICK --
    # rodar isto ao vivo ou no painel em M1 reproduziria o numero inflado,
    # nao o validado. Ver `scripts/daytrade/wdo_grid_reload_f1_tick_lab.py`
    # e a memoria `oos-split-sobreviventes-m5-2026-08-27`.
    feed_kind = "tick"

    # Promovido ao podio de day trade em 2026-08-27 (TOP-1, ver `strategy.
    # daytrade.registry`). Texto para humano, no mesmo espirito da
    # `gremah_tick`: o que o robo faz, com a ressalva que sustenta ou nao a
    # posicao -- nunca so' o numero bonito sem o que falta medir.
    tagline = (
        "Uma ordem parada 1 tick do preco de abertura, dos dois lados, no "
        "mini-dolar. Quando um lado toca, sai com alvo de 2 ticks e stop de "
        "16 -- e rearma no mesmo lugar. O lucro de cada ida e volta e' de "
        "centavos; o numero medido depende de quanto disso e' fila real, "
        "nao so' de o sinal existir."
    )
    plain_summary = (
        "Assim que o pregao abre, o robo deixa uma ordem de compra parada 1 "
        "tick abaixo do preco de abertura e uma de venda 1 tick acima -- as "
        "duas ao mesmo tempo, sem escolher lado. Quando uma delas e' tocada, "
        "ele sai com um alvo pequeno (2 ticks de lucro) ou um stop mais largo "
        "(16 ticks de perda) se o mercado virar contra. Fechada a posicao, "
        "rearma no MESMO nivel -- nunca persegue o preco para um nivel mais "
        "distante que pode nunca ser tocado.",
        "E' um robo de EXECUCAO, nao de previsao de direcao: ele nao aposta "
        "se o dolar vai subir ou cair, aposta que o preco vai oscilar de "
        "um lado para o outro do nivel dele repetidamente ao longo do "
        "pregao -- e' por isso que a mesma familia (chamada 'gremah' em "
        "acoes) sobrevive mesmo quando prever direcao no futuro nao "
        "funciona (ver a linha da Copa BTG, encerrada por refutacao "
        "direcional em 2026-08-26).",
        "2026-08-28: o stop foi trocado de 16 para 4 ticks apos varredura "
        "completa (1..20 x 1..20) mostrar T1 S4 dominando T1 S16 no IS. "
        "2026-08-29: REVERTIDO de volta para 16 -- a ressalva de entao se "
        "confirmou. Rodando o historico completo salvo (177 pregoes) com "
        "CAIXA REAL, T1 S4 nunca sobrevive ao proprio historico com capital "
        "realista (trava e nunca recupera em todo nivel testado ate "
        "R$20.000; so' sobrevive com R$30.000, e mesmo assim fecha quase so' "
        "devolvendo o capital). T1 S16 sobrevive com so' R$5.000 e fecha "
        "estavel em lucro a partir dai. Win rate no mesmo teste: 65,7% (S4) "
        "contra 90,3% (S16) -- S4 e' estruturalmente pior (1:4 de risco:"
        "retorno exige >80% de acerto pra empatar; 65,7% fica abaixo disso), "
        "nao so' uma amostra diferente.",
        "Os dois (S16 e S4) dependem do mesmo ponto cego: o numero so' "
        "existe se a ordem parada for de fato preenchida no toque -- e "
        "isso NUNCA foi medido com dado de livro real. O motor de teste "
        "preenche no toque; uma ordem parada real e' preenchida justamente "
        "quando o fluxo vem contra ela, o que o dado disponivel nao "
        "modela.",
        "Por isso ele entra no painel, mas o proximo passo antes de "
        "qualquer capital maior nao e' mais backtest -- e' medir a taxa de "
        "preenchimento passivo com 1 contrato ao vivo (T1 S16 ja tem "
        "confirmacao OOS de sinal -- R$148,89/pregao, 89% de retencao -- so' "
        "falta a taxa de fila real).",
    )
    plain_example = (
        "O dolar abre a R$ 5.079,00 (WDO@, tick de R$0,50). O robo deixa "
        "duas ordens paradas: compra a R$ 5.078,50 (1 tick abaixo) e venda "
        "a R$ 5.079,50 (1 tick acima).",
        "O preco cai e toca R$ 5.078,50 -- a compra e' preenchida. Na hora, "
        "o robo pendura a venda de saida em R$ 5.079,50 (alvo de 2 ticks de "
        "lucro) e um stop a mercado em R$ 5.070,50 (16 ticks abaixo).",
        "Se o preco sobe de volta a R$ 5.079,50 antes de cair mais, a venda "
        "de saida e' tocada: ganhou R$10,00 (2 ticks x R$5,00 x 1 contrato), "
        "menos a tarifa. O robo rearma IMEDIATAMENTE as duas ordens no "
        "mesmo nivel de antes (R$ 5.078,50 / R$ 5.079,50) -- nao persegue "
        "o novo preco.",
        "Se em vez disso o preco despenca 16 ticks sem voltar, o stop "
        "dispara: perde R$80,00 (16 x R$5,00), oito vezes o ganho de um "
        "acerto. E' por isso que a taxa de acerto tem de ficar perto de "
        "88,9% para o resultado ficar positivo -- uma unica perda apaga "
        "cerca de oito ganhos.",
    )

    #: Descricoes curtas para a ficha do robo (`dashboard/robot_view.py` via
    #: `strategy.registry.declared_params`/`_param_docs`) -- mesmo padrao ja
    #: usado por `Gremah`/`GremahTick` (`param_docs` de classe, mesclado pelo
    #: MRO). Este arquivo ainda nao tinha o dict (os parametros anteriores
    #: so' tem prosa no docstring do `__init__`) -- comeca aqui so' com os 3
    #: novos (2026-09-03), sem retrofitar os demais fora do escopo pedido.
    param_docs = {
        "reancora_min_segundos": "Espera minima (segundos) entre duas ordens "
                                 "que a corretora ve: reprecificar a pendente, "
                                 "ou rearmar depois de uma RECUSA. Ao vivo cada "
                                 "uma e' um cancela+reenvia, entao isto e' o "
                                 "teto duro de ordens por minuto (60/valor por "
                                 "cada um dos dois casos). Nao atrasa o rearme "
                                 "depois de um FILL (a mecanica de reload). "
                                 "0 desliga (indeployavel -- ver a docstring).",
        "reancora_min_ticks": "Histerese (em ticks): o nivel novo tem de "
                              "estar a esta distancia TANTO do nivel parado "
                              "QUANTO do ultimo nivel abandonado, senao a "
                              "substituicao nao sai. 2 (default) ignora o "
                              "vai-e-vem de 1 tick entre compra e venda e "
                              "impede a ordem de voltar para o nivel que "
                              "acabou de deixar; 1 desliga a histerese "
                              "inteira (baseline de medicao).",
        "defesa_ativa": "Liga a saida defensiva de recuo (default desligado -- "
                        "comportamento identico ao de antes).",
        "defesa_gatilho_stop_pct": "Fracao do stop (em ticks) que a posicao "
                                   "precisa sofrer CONTRA ela para a defesa ARMAR.",
        "defesa_alvo_proximidade_pct": "Depois de armada, fracao da distancia "
                                       "RESTANTE ate o alvo (0% = ainda longe, "
                                       "100% = ja bateria o alvo) abaixo da qual "
                                       "a posicao fecha antecipada.",
        "trailing_ativo": "Liga o alvo DINAMICO (trailing sobre o lucro): "
                          "profit_ticks vira PISO minimo, nao teto -- a posicao "
                          "continua monitorada tick a tick depois de bater o piso "
                          "(default desligado -- alvo estatico de sempre).",
        "trailing_recuo_ticks": "Quantos ticks o preco pode recuar do melhor "
                                "preco alcancado (depois do piso batido) antes "
                                "de fechar -- 0 fecha no primeiro tick contra, "
                                "sem folga nenhuma. So' importa com "
                                "trailing_ativo=True.",
        "gate_atividade_ativo": "Liga o gate de atividade pre-entrada: so' "
                                "arma uma NOVA ordem se o volume recente "
                                "(janela de gate_janela_segundos) estiver "
                                "acima de gate_volume_min (default desligado "
                                "-- arma sempre, como antes).",
        "gate_volume_min": "Limiar de volume (mesma unidade de Bar.volume) "
                           "abaixo do qual o robo NAO arma uma nova entrada. "
                           "Obrigatorio quando gate_atividade_ativo=True -- "
                           "sem default 'vencedor', decisao do dono depois "
                           "de medir.",
        "gate_janela_segundos": "Tamanho da janela (segundos) usada para "
                                "somar o volume recente e comparar contra "
                                "gate_volume_min.",
    }

    def __init__(
        self,
        symbol: str = "WDO@",
        tick_size: float = WDO_TICK_SIZE,
        level_spacing_ticks: int = 1,   # "x1"
        profit_ticks: int = 2,          # "T2" -- ver nota 2026-09-04 no topo do modulo (mudou de T1)
        stop_ticks: int | None = 6,     # "S6" -- ver nota 2026-09-09 no topo do modulo (era S16)
        reanchor_mode: ReanchorMode = "rolling_last_price",
        reancora_min_segundos: float = 10.0,
        reancora_min_ticks: int = 2,   # histerese anti-pingue-pongue -- ver 2026-09-08 no topo
        max_trades_per_side: int = 200,
        session_stop_brl: float | None = None,
        quantity: int | None = None,
        margin_per_contract_brl: float | None = None,
        margin_buffer: float = MARGIN_BUFFER_FUTUROS,
        hard_cap_contratos: int | None = None,
        risco_pct_por_trade: float | None = None,
        point_value_brl: float | None = None,
        defesa_ativa: bool = False,
        defesa_gatilho_stop_pct: float = 0.0,
        defesa_alvo_proximidade_pct: float = 0.0,
        trailing_ativo: bool = False,
        trailing_recuo_ticks: int | None = None,
        gate_atividade_ativo: bool = False,
        gate_volume_min: float | None = None,
        gate_janela_segundos: int = 15,
        fatiar_saida_alvo: bool = False,
        exit_ttl_bars: int | None = EXIT_TTL_BARS_PADRAO_FATIA,
    ):
        """Ver a docstring do modulo para a mecanica completa e para os
        parametros existentes acima (`tick_size`, `level_spacing_ticks`,
        `profit_ticks`, `stop_ticks`, `reanchor_mode`, `max_trades_per_side`,
        `session_stop_brl`, `quantity`). So' os quatro novos (2026-08-27/29)
        e os dois de 2026-09-08 (`fatiar_saida_alvo`, `exit_ttl_bars`,
        prosa junto da atribuicao em `__init__` e da constante `EXIT_TTL_
        BARS_PADRAO_FATIA` no topo do modulo) tem prosa aqui.

        `margin_per_contract_brl`: ATIVA a realocacao dinamica por capital
        (ver a secao do modulo). `None` (default) -- comportamento IDENTICO
        ao de antes: `quantity` viaja direto para cada `EnterLimit`. Setado,
        `quantity` e' IGNORADO e a quantidade de cada entrada vira `max(1,
        contracts_from_capital(caixa_atual, margin_per_contract_brl,
        margin_buffer, hard_cap=hard_cap_contratos))` -- os dois modos
        (capital dinamico OU quantidade fixa) sao MUTUAMENTE EXCLUSIVOS.

        `margin_buffer`: multiplicador de seguranca sobre a margem por
        contrato, mesmo parametro/mesmo default de `contracts_from_capital`
        (`MARGIN_BUFFER_FUTUROS=2.0`) -- so' importa quando
        `margin_per_contract_brl` esta setado.

        `hard_cap_contratos`: teto SUPERIOR opcional sobre o resultado de
        `contracts_from_capital` (ex.: o teto oficial do perfil, 5 no
        WDO@) -- sem ele a quantidade cresce sem limite conforme o caixa
        sobe. So' importa quando `margin_per_contract_brl` esta setado.

        `risco_pct_por_trade`/`point_value_brl` (2026-08-29, item 3.9 de
        LICOES_DE_PRODUCAO.md -- achado no `CopaWin`, nao ainda medido AQUI
        porque o modo dinamico deste robo e' OPT-IN e nao e' o default de
        producao hoje): SEGUNDO teto, independente do teto por margem acima
        -- a entrada usa o MENOR entre os dois (nenhum substitui o outro; ver
        `strategy.daytrade.base.contracts_from_risk`). Como o stop deste robo
        e' FIXO em ticks (`stop_ticks x tick_size`, nao por volatilidade do
        dia como no `CopaWin`), o risco em reais por contrato e' CONSTANTE:
        `stop_ticks x tick_size x point_value_brl`. Os dois precisam vir
        JUNTOS (um sem o outro nao computa nada) -- `None`/`None` (default)
        desliga, comportamento IDENTICO ao de antes.

        `defesa_ativa`/`defesa_gatilho_stop_pct`/`defesa_alvo_proximidade_pct`
        (2026-09-03, pedido do dono -- saida defensiva de RECUO): "chegou a
        80% do stop e depois o preco voltar a 1% do alvo, a posicao e'
        fechada", generalizado para os dois parametros abaixo. ADITIVO e
        OPT-IN -- `defesa_ativa=False` (default) preserva o comportamento
        BYTE A BYTE de antes; os dois `*_pct` so' importam com
        `defesa_ativa=True`.

        Mecanica, avaliada a CADA `on_bar` com posicao aberta (nunca na
        barra em que a `EnterLimit` ainda esta pendente -- so' depois do
        fill confirmado):

        1. ARMAR (uma vez por trade, NUNCA desarma depois): a posicao sofreu
           excursao ADVERSA (nao realizada) de pelo menos
           `defesa_gatilho_stop_pct x stop_ticks_da_posicao`, onde
           `stop_ticks_da_posicao = |entry_price - current_stop| / tick_size`
           (derivado do stop REAL da posicao, nao de `self.stop_ticks` --
           o stop pode ter sido ajustado por `AdjustStop`, embora este robo
           hoje nunca emita essa acao). A excursao usa o preco mais ADVERSO
           da barra (`bar.low` comprado, `bar.high` vendido), nao so' o
           `close` -- o pico de dor pode ter acontecido e revertido dentro
           da mesma barra (tick, aqui: `bar.high==bar.low==bar.close` quase
           sempre, ver `feed_kind`).
        2. FECHAR (so' depois de armada): a distancia RESTANTE ate o alvo,
           em FRACAO da distancia total entrada->alvo, cai a
           `defesa_alvo_proximidade_pct` ou abaixo -- formula exata:
           `dist_restante_ticks / dist_total_ticks <= defesa_alvo_
           proximidade_pct`, onde `dist_restante_ticks` usa o preco mais
           FAVORAVEL da barra (`bar.high` comprado, `bar.low` vendido,
           espelhando o preco mais adverso do passo 1) e nunca fica negativo
           (clampado em 0 -- bater o alvo de verdade fecha pelo caminho
           normal do motor ANTES deste `on_bar` rodar, ver a prioridade "(1)
           stop/target automatico" em `machine.py`, entao esta funcao nunca
           deveria ver `dist_restante_ticks<=0` na pratica). Esta e' a
           leitura mais direta do pedido do dono ("voltar a X% do alvo"):
           X% PEQUENO exige estar MUITO perto do alvo; X% GRANDE ja basta
           estar relativamente perto -- e' a fracao que FALTA percorrer, nao
           a fracao ja percorrida.
           Fecha via `Exit(reason="defesa_recuo")`, IGNORANDO qualquer outra
           acao que a logica normal geraria para a MESMA posicao nesta
           chamada (a defesa tem prioridade -- mesmo padrao ja usado por
           `session_stop_brl` acima, que tambem devolve `Exit` sozinho).

        DEGENERESCENCIA CONHECIDA quando `profit_ticks=1` (o default de
        producao ATE 2026-09-04, ver a nota no topo do modulo -- o default
        ATUAL e' `profit_ticks=2`): o preco so' se move em ticks inteiros,
        entao com alvo de 1 tick nao existe estado intermediario entre "0%
        do alvo" (nunca tocou) e "100% do alvo" (bateu, ja fechado pelo motor
        ANTES desta funcao rodar -- ver o passo 2 acima). Ou seja, para
        QUALQUER `defesa_alvo_proximidade_pct < 100%` com `profit_ticks=1`,
        a condicao de fechar so' poderia bater exatamente quando o alvo JA
        foi tocado -- o que este `on_bar` nunca chega a ver: a defesa
        NUNCA dispara antes da saida normal por alvo ja ter fechado a
        posicao. Com `profit_ticks=2` (producao atual) ja existe UM estado
        intermediario (50% do alvo, 1 de 2 ticks percorridos), entao a
        degenerescencia acima NAO se aplica mais por construcao -- mas se a
        defesa dispara de forma UTIL com essa unica leitura intermediaria e'
        pergunta empirica em aberto, nao assumida aqui (ver
        `scripts/daytrade/wdof1_defesa_recuo_sweep_2026_09_03.py`, medido
        com `profit_ticks=1`, precisa remedir se for reusar com o alvo
        novo). A mecanica em si e' implementada corretamente e independente
        de `profit_ticks` em qualquer caso.

        Estado de armada mora em `self._defesa_armada` (dict, chave
        `(side, entry_ts)`), NUNCA em `IntradayOpenPosition.metadata` --
        `metadata` e' um snapshot READ-ONLY reconstruido do zero a cada
        chamada (`machine.py::_position_view`, `metadata=dict(pos.metadata)`
        e' uma COPIA), a estrategia nao tem como escrever de volta um estado
        persistente por ali. `(side, entry_ts)` basta porque este robo nunca
        usa `EnterLimit.split_quantities` (uma unica posicao por vez) --
        resetado em `on_session_start`, mesmo lugar que ja reseta `self.
        _state` (sem memoria entre pregoes).

        `trailing_ativo`/`trailing_recuo_ticks` (2026-09-04, pedido do dono
        depois do item 4.8 de LICOES_DE_PRODUCAO.md -- a 1a operacao real
        derrapou 1 tick no alvo nativo de 1 tick e zerou o lucro do trade):
        "o target inicial deve ser de 2, depois tem que monitorar de um em
        um [tick] pra ver ate onde foi". ADITIVO e OPT-IN -- `trailing_
        ativo=False` (default) preserva o comportamento BYTE A BYTE de
        antes: `initial_target` continua sendo a ordem-limite ESTATICA de
        sempre (`profit_ticks` ticks do nivel), fechada pelo MOTOR no
        instante em que e' tocada (prioridade "(1) stop/target automatico"
        em `machine.py`), sem este `on_bar` nunca ser consultado sobre o
        alvo.

        Setado, `profit_ticks` muda de TETO para PISO: a posicao nunca
        fecha por lucro antes de alcancar `profit_ticks` ticks a favor, mas
        TAMBEM nao fecha automaticamente ao alcancar -- continua aberta,
        monitorada tick a tick (`feed_kind="tick"`, ver o atributo de
        classe: cada `on_bar` e' um NEGOCIO, nao um minuto), ate o preco
        RECUAR `trailing_recuo_ticks` ticks do MELHOR preco alcancado desde
        a entrada. Mecanicamente isto exige que a `EnterLimit` desta
        entrada NAO carregue mais um `initial_target` estatico (fica `None`
        -- ver o fim de `on_bar`): um alvo estatico no piso faria o MOTOR
        fechar a posicao no exato instante em que ele e' tocado, ANTES
        desta funcao rodar (mesmo mecanismo que fecha o alvo de sempre),
        impedindo por construcao qualquer monitoramento POSTERIOR ao piso.
        O STOP nao muda em nada -- `initial_stop`/`current_stop` continuam
        exatamente como sempre, geridos pelo motor; so' o ALVO vira
        dinamico. Investigado (nao so assumido) contra a alternativa de
        usar `AdjustTarget` (existe, `strategy.daytrade.base.AdjustTarget`,
        aplicado imediatamente pelo motor, sem restricao de direcao -- ver
        `machine.py::_on_closed_bar_core` passo 5): o toque automatico de
        alvo e' um teste de "preco SUBIU ate um nivel" (`bar.high >=
        current_target` para compra) -- a MESMA forma de teste de um STOP,
        nunca de "preco CAIU abaixo de um nivel que vinha subindo", que e' o
        que um recuo desde o pico precisa. Empurrar `current_target` para
        baixo do pico via `AdjustTarget` fecharia a posicao no PROXIMO
        toque (o preco ainda esta acima do novo alvo, mais baixo, entao
        "toca" de imediato) em vez de esperar uma reversao de verdade --
        directionally errado para este pedido. Por isso a saida usa `Exit`
        explicito desta classe (mesmo padrao ja usado por `session_stop_
        brl`/`defesa_ativa` acima), nunca `AdjustTarget`.

        Formula exata, avaliada a CADA `on_bar` com posicao aberta (mesma
        prioridade de `defesa_ativa`: roda DEPOIS da confirmacao de fill,
        ANTES do `return []` de sempre):
        1. `preco_favoravel = bar.high` (comprado) ou `bar.low` (vendido) --
           o melhor preco desta barra/tick. Pico (`self._trailing_pico`,
           por posicao, chave `(side, entry_ts)`, mesmo padrao de `self.
           _defesa_armada`) vira `max(pico_anterior, preco_favoravel)`
           (comprado) ou `min(...)` (vendido); comeca implicitamente em
           `entry_price` (nenhum pico registrado ainda).
        2. Se `abs(pico - entry_price) / tick_size < profit_ticks` (piso
           AINDA nao alcancado pelo pico): nunca fecha, `False` direto --
           e' o que garante "nunca fecha antes do piso a favor", mesmo se
           esta barra sozinha for desfavoravel.
        3. Piso ja alcancado (em QUALQUER barra anterior ou nesta): calcula
           `recuo_ticks = (pico - preco_adverso) / tick_size` (comprado) ou
           o espelho (vendido), com `preco_adverso = bar.low` (comprado) ou
           `bar.high` (vendido) -- pessimista de proposito, mesmo espirito
           de `_defesa_deve_fechar` (usa o lado ADVERSO da barra para
           decidir fechar, o lado FAVORAVEL para decidir se fez novo pico).
           Fecha (`Exit(reason="trailing_lucro")`) quando `recuo_ticks >
           trailing_recuo_ticks` -- estritamente MAIOR, nao >=: com
           `trailing_recuo_ticks=0` isto fecha no PRIMEIRO tick que nao fizer
           novo pico (recuo_ticks vira >0 assim que o preco nao acompanha o
           pico), nao no proprio tick que acabou de tocar o piso (ali
           `recuo_ticks=0`, ja que aquele preco VIROU o pico) -- "fecha no
           primeiro tick contra, sem folga nenhuma", nao "fecha exatamente
           no piso". Com `trailing_recuo_ticks=N>0`, tolera ate N ticks de
           recuo desde o pico antes de fechar.
        Como no' `feed_kind="tick"` `bar.high==bar.low==bar.close` quase
        sempre (ver a nota no atributo de classe), a distincao favoravel/
        adverso acima raramente muda o numero na pratica -- fica pela MESMA
        razao de robustez/consistencia que `_defesa_deve_fechar` ja usa (se
        este robo um dia rodar em M1, o calculo continua correto).

        `trailing_recuo_ticks` e' OBRIGATORIO (sem default "vencedor" --
        decisao de producao em aberto, o dono quer medir os candidatos
        antes) quando `trailing_ativo=True`: `ValueError` se vier `None`
        junto. Os DOIS sao independentes de `defesa_ativa` (podem, em tese,
        ligar ao mesmo tempo, mas com `trailing_ativo=True` o alvo vira
        `None` e `_defesa_deve_fechar` sempre devolve `False` no passo de
        proximidade-ao-alvo -- "armada, mas sem alvo declarado" -- entao
        combinar os dois nao foi medido e nao e' o caminho recomendado).

        Estado do pico mora em `self._trailing_pico`, resetado em
        `on_session_start` -- mesmo padrao/mesmo motivo de `self.
        _defesa_armada` (chave `(side, entry_ts)`, nunca desarma dentro do
        mesmo trade, sem memoria entre pregoes).

        `gate_atividade_ativo`/`gate_volume_min`/`gate_janela_segundos`
        (2026-09-07, pedido do dono -- gate de atividade PRE-entrada,
        ADITIVO e OPT-IN): `scripts/daytrade/wdof1_mfe_mae_semana_2026_09_
        04.py` gravou volume/volatilidade de 15s/60s ANTES de cada entrada
        da semana real (2026-08-31 a 2026-09-04, 177 trades T1/S16); uma
        analise (Opus 5) achou correlacao REAL (Spearman, sobrevive
        correcao por multiplos testes, rho~=-0,33, p<0,002) entre
        volume_15s_antes/volume_60s_antes/volatilidade_ticks_15s_antes/
        volatilidade_ticks_60s_antes e a DURACAO do trade que se seguiu --
        mais atividade ANTES da entrada prevê preenchimento MAIS RAPIDO da
        ordem-limite. RESSALVA que a propria analise levantou, e que este
        gate NAO resolve por conta propria: a correlacao e' sobre
        VELOCIDADE de preenchimento, nao QUALIDADE do trade -- a amostra
        tinha 0 stops em 177 trades, entao ninguem sabe se atividade alta
        tambem prevê MAIS risco (e' exatamente onde os stops poderiam morar,
        sem dado pra confirmar ou refutar). Este parametro so' MECANIZA a
        pergunta para poder ser MEDIDA (ver os scripts desta rodada) -- nao
        assume que o gate melhora o resultado.

        Por que so' VOLUME (nao volatilidade, nao um "score" combinando os
        dois): as duas variaveis tiveram forca de correlacao
        estatisticamente indistinguivel na mesma analise (rho~=-0,33 as
        duas) e sao naturalmente correlacionadas entre si (janela com mais
        negocios tende a ter mais range de preco tambem) -- combinar as
        duas num "score" exigiria calibrar um PESO relativo que ninguem
        pediu ainda, o que viola o espirito de nao criar mais parametro que
        o necessario para medir a pergunta em aberto. Volume tambem e' a
        MESMA grandeza que o motor ja usa para gatear PREENCHIMENTO
        (`IntradayBacktestConfig.limit_fill_capped_by_volume`) -- reusar o
        mesmo eixo para gatear ARMAMENTO mantem o modelo mental consistente
        com o resto do motor, em vez de introduzir uma segunda nocao de
        "atividade" so' para este robo.

        Mecanica, avaliada em TODA chamada de `on_bar` (nao so' quando ha'
        sinal de entrada):
        1. `self._historico_recente` (deque de `(ts, volume)`) acumula CADA
           barra/tick recebido, recortado para os ultimos
           `gate_janela_segundos` segundos a cada chamada (mesmo espirito de
           recorte de `RollingVolumeWindow.registrar`,
           `strategy.daytrade.base` -- reimplementado aqui, nao reusado,
           porque a granularidade e' outra -- segundos fixos, nao minutos
           medios -- e este gate nao precisa de cauda do pregao anterior:
           comeca do zero a cada sessao, mesmo padrao de `self.
           _defesa_armada`/`self._trailing_pico`). Resetado em
           `on_session_start`.
        2. So' quando o robo esta' decidindo o PRIMEIRO armamento de uma
           nova `EnterLimit` (`_next_side_to_arm()` devolveu um lado e NAO
           havia ordem pendente -- o ramo que REANCORA uma ordem ja'
           pendente, ver o fix do item 4.9 acima, NUNCA passa por este gate:
           reancorar nao e' "uma nova entrada", e' a MESMA ordem seguindo o
           preco): soma o volume em `self._historico_recente` (inclui a
           barra/tick ATUAL -- diferente da janela do script de medicao,
           que exclui o proprio tick de entrada, porque ali `entry_ts` e' o
           instante de PREENCHIMENTO, nao de ARMAMENTO; aqui o gate decide
           ANTES de a ordem sequer existir, entao o "agora" ja' faz parte do
           que aconteceu). Se a soma ficar `<= gate_volume_min`, esta
           chamada de `on_bar` NAO arma nada (devolve `[]`, mesmo espirito
           de "espera a proxima chamada" que `max_trades_per_side` esgotado
           ja' usa acima) -- tenta de novo na proxima barra/tick, com a
           janela recalculada.
        3. `self.gate_bloqueios` (contador simples, NUNCA resetado em
           `on_session_start` -- soma a vida INTEIRA do backtest/sessao ao
           vivo, nao por pregao) conta quantas vezes o passo 2 bloqueou um
           armamento que `_next_side_to_arm()` ja' tinha decidido -- e' o
           numero que os scripts de medicao desta rodada leem para reportar
           "quantas entradas o gate impediu".

        `gate_volume_min` e' OBRIGATORIO (sem default "vencedor", mesmo
        padrao de `trailing_recuo_ticks`) quando `gate_atividade_ativo=True`:
        `ValueError` se vier `None` junto -- e' justamente a decisao que os
        scripts de medicao desta rodada existem para informar, nao para
        assumir aqui.

        `reancora_min_segundos` / `reancora_min_ticks` (2026-09-07) -- FREIO
        DE CADENCIA DE ORDENS. Diferente de `defesa_ativa`/`trailing_ativo`/
        `gate_atividade_ativo`, este NAO e' opt-in: vem LIGADO por padrao,
        porque sem ele o comportamento default do robo e' indeployavel. Ver a
        nota datada de 2026-09-07 no topo do modulo para a medicao que
        motivou (dezenas de milhares de envios por pregao, ate' 3.446 numa
        unica janela de 60s, contra os tetos de
        `live.intraday_runtime.COTA_ENVIOS_POR_MINUTO` = 120 e
        `MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO` = 600).

        `reancora_min_segundos` e' a espera minima entre duas ordens que a
        CORRETORA ve, e vale para os dois caminhos que produziam enxurrada:
        reprecificar a pendente (`_pode_reprecar`) e rearmar depois de uma
        RECUSA (`_pode_armar_apos_recusa`). Nao vale para o rearme depois de
        um FILL -- a mecanica de reload (fecha -> rearma no mesmo nivel) e' o
        robo, e freia-la seria trocar o desenho, nao proteger a execucao.

        E' o portao que da' a GARANTIA, e por isso carrega o default: limita
        cada um dos dois caminhos a `60/valor` ordens por minuto por
        CONSTRUCAO, faca o mercado o que fizer. Um limiar de DERIVA sozinho
        nao garante nada -- reduz a frequencia media, mas numa arrancada o
        preco cruza o limiar quantas vezes quiser dentro do mesmo minuto
        (medido em 2026-08-31: `reancora_min_ticks=4` sem freio de tempo
        ainda deu 74 envios no pior minuto, e travaria o robo).

        Default `10.0`s escolhido por MEDICAO. Grade 6/10/15s no motor tick,
        capital real R$375, 126 pregoes INTEIROS de WDO@ (`WDO_A_.parquet`),
        distribuicao do PIOR minuto de cada pregao contra o teto de 30:

            valor    p50   p90   p95   p99   MAX   pregoes que TRAVAM
             6s       11    19    22    30    33        2 / 126
            10s        9    18    22    24    26        0 / 126
            15s        9    17    18    32    36        2 / 126

        `10s` e' o UNICO da grade que nunca trava em 126 pregoes -- e o
        criterio nao e' a media, e' o pior caso, porque UMA travada custa o
        pregao inteiro. Repare que a relacao NAO e' monotonica: 15s freia
        mais e mesmo assim trava (2026-08-07 e 2026-08-12, pico de 34 e 36),
        porque mudar a cadencia muda QUAIS pregoes saturam e a rajada de
        rearme pos-fill (que este freio nao toca) e' o que sobra no pico.
        Nao extrapole "mais freio = mais seguro" sem re-medir.

        LIQUIDO ficou FORA da escolha de proposito: com R$375 o robo opera no
        proprio piso de capital, e mudar o freio em 1 segundo flipa o pregao
        inteiro entre "opera 400 trades" e "cai no laco de recusa por caixa"
        (2026-04-02: R$+2.945 com 6s, R$-47,50 com 10s; 2026-04-01 inverte o
        sinal). Isso e' o piso de capital falando, nao o freio -- escolher
        default por esse numero seria ler ruido. Os totais dos 126 pregoes
        ficam dentro da mesma faixa nos tres (R$66k-79k), o que confirma que
        a diferenca e' ruido, nao sinal.

        RESIDUAL conhecido, e e' o numero que o dono precisa ver antes de
        subir isto: mesmo no default, o pior minuto medido chega a 26 de 30
        (~87% do teto) -- a folga e' de 4 ordens. Esse pico e' 100% rearme
        POS-FILL num pregao que satura `max_trades_per_side` (2026-03-23:
        400 trades, 400 armamentos, ZERO recusa por capital) -- nao ha'
        freio a aplicar ali sem mudar o robo.
        E' o motivo pelo qual `max_trades_per_side` deixou de ser um teto
        folgado e passou a ser LOAD-BEARING para a cadencia: subi-lo empurra
        esse pico por cima de 30. Ver a docstring daquele parametro.

        E o pico mora na PRIMEIRA HORA. Pior janela de 60s por hora BRT nos
        pregoes que saturam (default 10s): 2026-03-23 = 26 as 09:01 (contra
        13 na hora seguinte); 2026-03-26 = 18 as 09:00 (12 na seguinte);
        2026-03-12 = 17 as 11:46. Os numeros desta docstring vem de
        `WDO_A_.parquet`, que cobre 12:00-21:29 UTC = 09:00-18:29 BRT --
        nao de `WDO_A_f1.parquet`.
        AVISO (2026-09-07, resolvido em 2026-09-07 -- ver `LICOES_DE_
        PRODUCAO.md`): ate' esse dia, `WDO_A_f1.parquet` cobria so'
        ~14:58-18:29 de cada pregao (janela pedida ao MT5 saia deslocada +3h,
        ver o AVISO em `wdo_grid_reload_f1_tick_probe.py`) -- quem re-medisse
        isto usando aquele cache em vez do `WDO_A_.parquet` subestimaria o
        pico por construcao, faltando a manha inteira. O cache foi regerado
        no mesmo dia (4.011.197 -> 20.646.379 ticks, cobertura de minutos de
        pregao 212/570 -> 570/570) e cobre o pregao inteiro agora. Mas a
        grade 6/10/15s ACIMA em si foi medida ANTES da correcao do
        `WDO_A_.parquet` do proprio dia (fuso na paginacao do terminal
        comia 19,3% dos minutos) -- a varredura leu um cache de sessao de
        20:55 e o canonico corrigido so' substituiu o arquivo as 22:03; nao
        foi remedida sobre o canonico corrigido. Quem for re-medir isto,
        re-rode a grade sobre o `WDO_A_.parquet` atual antes de confiar no
        numero.

        `0.0` restaura o comportamento sem freio (so' para medir o baseline;
        nunca para operar).

        `reancora_min_ticks` -- HISTERESE. Ate' 2026-09-08 valia `1` (nao
        filtrava nada) "porque o portao de tempo ja' resolve". Nao resolve, e
        o pregao de 2026-09-08 mostrou as duas razoes de uma vez (slot
        `dt-wdo_grid_reload_maker-wdo@-live`, `live_events`, 22 rodadas):

        1. O portao de tempo mede `bar.ts`, e num passo do supervisor que
           reprocessa fila atrasada o tempo de TICK anda muito mais rapido
           que o de parede -- a rodada #21 emitiu 5 ordens (1 armamento + 4
           substituicoes) no MESMO segundo de parede, todas legitimas para o
           freio de 10s porque em tempo de tick estavam a minutos uma da
           outra. Ver a docstring de `live.intraday_runtime.
           _check_cadencia_de_ordens`.
        2. Mesmo com o relogio certo, a DERIVA de 1 tick nao e' preco
           andando: e' o vai-e-vem entre a ponta de compra e a de venda. Na
           rodada #21 a ordem foi 5105,0 -> 5105,5 -> 5105,0 -> 5105,5 ->
           5106,5 -- o par se repete, e cada volta e' um cancela+reenvia
           REAL que joga fora a fila ja acumulada. Veredito do dono no mesmo
           dia: "substituiu 3 vezes para o mesmo preco, mesmo stop e mesmo
           alvo, isso e' uso de recurso desnecessario, neste caso nao deve
           substituir".

        A regra passou a ter DOIS pontos de referencia, com a mesma
        constante (ver `_pode_reprecar`): o nivel novo tem de estar a pelo
        menos `reancora_min_ticks` ticks do nivel PARADO **e** do ultimo
        nivel ABANDONADO nesta rodada. O primeiro portao mata o vai-e-vem
        adjacente; o segundo mata o pingue-pongue mais largo, que uma banda
        sozinha deixa passar (sai de A, anda 2 ticks ate B, volta para A --
        cada perna passa na banda, e o par se repete indefinidamente).

        A histerese nao consegue PRENDER a ordem, e isso e' propriedade da
        forma, nao sorte de calibracao: com `N=2` ela proibe exatamente uma
        janela de 3 niveis em volta do parado e outra de 3 em volta do
        abandonado -- qualquer nivel a 2 ticks ou mais dos dois passa. Preco
        que anda de verdade sempre encontra nivel livre; no pior caso a
        ordem para 1 tick ao lado do ideal em vez de em cima dele. E' o
        contrapeso que impede esta correcao de reintroduzir a ordem
        ESTACIONADA que o item 4.9 corrigiu.

        Medido sobre o proprio pregao de 2026-09-08 (replay da sequencia de
        niveis registrada no diario, 125 `LIMITE` das quais 103
        `(substitui)`):

            regra                                envios   pior 60s de PAREDE
            hoje (`reancora_min_ticks=1`)          125            64
            so' memoria do abandonado (=1)         100            --
            so' banda de 2 ticks                    60            --
            banda 2 + memoria (DEFAULT novo)        53            21

        Duas leituras do numero. Primeira: 65 das 103 substituicoes moveram
        a ordem 1 tick e 49 devolveram a ordem a um nivel que a MESMA rodada
        ja' tinha ocupado -- e' desperdicio puro, sem contraparte. Segunda,
        e e' a que importa para o deploy: o pior minuto de PAREDE cai de 64
        para 21. Contra o teto que vigorava naquele dia (30, disjuntor: nao
        recusava so' a ordem, parava o robo pelo pregao inteiro) isso era
        sair de mais que o DOBRO do teto para 30% de folga. Desde
        2026-09-08 os dois numeros cabem na cota de vazao
        (`live.intraday_runtime.COTA_ENVIOS_POR_MINUTO` = 120) -- o ganho
        continua sendo real (menos cancela+reenvia, mais fila preservada),
        mas ja' nao e' a diferenca entre operar e ficar mudo.

        RESSALVA do numero: e' um replay das ordens que o diario REGISTROU,
        nao de todos os ticks do pregao. Quando a histerese recusa uma
        substituicao, o relogio de `pending_level_ts` nao e' reiniciado (o
        `return` sai antes), entao ticks que o freio de tempo tinha barrado
        podem virar candidatos -- 53 e' PISO, nao previsao exata.

        MEDIDO no IS/OOS congelado DEPOIS de aplicar (motor tick, base
        `WDO_A_f1.parquet` corrigida, capital real R$375, config de producao
        via `get_daytrade_robot` -- `scripts/daytrade/wdof1_histerese_pingue_
        pongue_2026_09_08.py`, 1.321s em 4 processos). A histerese nao custa
        resultado: ganha ou empata em toda coluna que importa, nas DUAS
        janelas.

            janela  hist   liquido R$   MaxDD R$  lucro/DD  trades   envios
            IS        1    344.855,00   2.905,00    118,71  19.835   33.984
            IS        2    347.548,50   2.547,50    136,43  19.893   27.979
            OOS       1    135.618,50   2.650,00     51,18   9.446   18.131
            OOS       2    143.214,50   2.540,00     56,38   9.635   14.020

        Envios caem 17,7% (IS) e 22,7% (OOS) com MAIS trades nas duas -- a
        leitura e' a mesma do freio de tempo: ordem que persegue o preco quase
        nao e' tocada, ordem parada e' preenchida. Win rate nao se mexe (94,2%
        no IS, 94,4% -> 94,5% no OOS). A unica coluna que piora e' `MaxDD %`
        no IS (-21,2% -> -27,5%) enquanto o `MaxDD R$` MELHORA (2.905,00 ->
        2.547,50): o recuo em reais e' MENOR, so' aconteceu num ponto mais
        baixo da curva.

        O que esta medicao NAO diz, e importa: `pior_janela_60s` sai IDENTICO
        nos dois (23 no IS, 42 no OOS), porque no backtest essa janela e' de
        tempo de TICK e o pico e' 100% rearme POS-FILL, que a histerese nao
        toca por desenho. O ganho de 64 -> 21 e' de relogio de PAREDE, que so'
        existe ao vivo. E repare de passagem que 42 > 30: a saturacao de
        `max_trades_per_side` ja' estoura o teto ao vivo por conta propria na
        janela OOS, com ou sem histerese -- residual ja' conhecido, ver a
        docstring de `max_trades_per_side`.

        `1` desliga a histerese inteira (banda E memoria) e restaura o
        comportamento anterior byte a byte -- serve de baseline de medicao,
        como `reancora_min_segundos=0.0`, nunca de configuracao de operacao.
        Valores maiores que 2 nao foram medidos: 2 e' o menor valor que
        distingue "o preco andou" de "trocou de ponta do book", e mexer nele
        muda quantas vezes a ordem persegue o mercado -- ver a nota do freio
        de tempo sobre reprecar demais fazer o robo quase nao NEGOCIAR."""
        if (risco_pct_por_trade is None) != (point_value_brl is None):
            raise ValueError(
                "wdo_grid_reload_maker: passe `risco_pct_por_trade` e "
                "`point_value_brl` JUNTOS (um sem o outro nao computa nada) "
                "ou nenhum dos dois."
            )
        if trailing_ativo and trailing_recuo_ticks is None:
            raise ValueError(
                "wdo_grid_reload_maker: trailing_ativo=True exige "
                "trailing_recuo_ticks explicito (quantos ticks de recuo desde "
                "o pico fecham a posicao) -- None nao e' uma regra, e' decisao "
                "que ainda falta tomar."
            )
        if trailing_recuo_ticks is not None and trailing_recuo_ticks < 0:
            raise ValueError(
                "wdo_grid_reload_maker: trailing_recuo_ticks nao pode ser "
                "negativo."
            )
        if gate_atividade_ativo and gate_volume_min is None:
            raise ValueError(
                "wdo_grid_reload_maker: gate_atividade_ativo=True exige "
                "gate_volume_min explicito (limiar de volume abaixo do qual "
                "o robo NAO arma uma nova entrada) -- None nao e' uma regra, "
                "e' decisao que ainda falta tomar (medir antes)."
            )
        if gate_volume_min is not None and gate_volume_min < 0:
            raise ValueError(
                "wdo_grid_reload_maker: gate_volume_min nao pode ser "
                "negativo."
            )
        if gate_janela_segundos <= 0:
            raise ValueError(
                "wdo_grid_reload_maker: gate_janela_segundos deve ser "
                "positivo."
            )
        if reancora_min_segundos < 0:
            raise ValueError(
                "wdo_grid_reload_maker: reancora_min_segundos nao pode ser "
                "negativo (0 desliga o freio -- ver a docstring)."
            )
        if reancora_min_ticks < 1:
            raise ValueError(
                "wdo_grid_reload_maker: reancora_min_ticks deve ser >= 1 -- "
                "abaixo de 1 tick nao existe nivel diferente para reprecar."
            )
        self.symbol = symbol
        self.tick_size = tick_size
        self.level_spacing_ticks = level_spacing_ticks
        self.profit_ticks = profit_ticks
        self.stop_ticks = stop_ticks
        self.reanchor_mode = reanchor_mode
        self.reancora_min_segundos = float(reancora_min_segundos)
        self.reancora_min_ticks = int(reancora_min_ticks)
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = None if session_stop_brl is None else abs(session_stop_brl)
        self.quantity = quantity
        self.margin_per_contract_brl = (
            None if margin_per_contract_brl is None else float(margin_per_contract_brl)
        )
        self.margin_buffer = float(margin_buffer)
        self.hard_cap_contratos = hard_cap_contratos
        self.risco_pct_por_trade = (
            None if risco_pct_por_trade is None else float(risco_pct_por_trade)
        )
        self.point_value_brl = None if point_value_brl is None else float(point_value_brl)
        self.defesa_ativa = bool(defesa_ativa)
        self.defesa_gatilho_stop_pct = float(defesa_gatilho_stop_pct)
        self.defesa_alvo_proximidade_pct = float(defesa_alvo_proximidade_pct)
        self.trailing_ativo = bool(trailing_ativo)
        self.trailing_recuo_ticks = (
            None if trailing_recuo_ticks is None else int(trailing_recuo_ticks)
        )
        self.gate_atividade_ativo = bool(gate_atividade_ativo)
        self.gate_volume_min = None if gate_volume_min is None else float(gate_volume_min)
        self.gate_janela_segundos = int(gate_janela_segundos)
        # `fatiar_saida_alvo` (2026-09-08, hipotese do dono): declara
        # `EnterLimit.exit_split_unit` no alvo, trocando o gatilho-a-mercado
        # (paga `costs.apply_deslize_alvo_nativo`) por ordem-limite REAL
        # fatiada no livro (`machine._close_position` pula o deslize quando
        # `exit_split_unit is not None` -- ver a condicao `is_maker_target`).
        # `False` (default): comportamento IDENTICO a antes.
        self.fatiar_saida_alvo = bool(fatiar_saida_alvo)
        # `exit_ttl_bars`: OBRIGATORIO para `fatiar_saida_alvo` funcionar em
        # EXECUCAO REAL -- sem prazo, `machine._resolve_live_split_exit`
        # levanta `AssertionError` na primeira posicao que tentar fechar
        # assim (a fatia REAL fica parada no livro para sempre sem isto).
        # So' vale enquanto `fatiar_saida_alvo=True` (linha do EnterLimit
        # abaixo); backtest/sombra funcionam sem ele (caminho sem prazo).
        # Valor default EMPRESTADO de `EXIT_TTL_BARS_PADRAO` da `gremah.py`
        # (8 barras de 1 min) -- NAO foi varrido para o WDO F1: e' ponto de
        # partida, nao calibracao. Antes de operar real, sweep proprio.
        #
        # `None` = SEM prazo: a fatia espera indefinidamente pelo fill. E'
        # outro CAMINHO no motor (`machine._resolve_target_partial_fill`, que
        # preenche na propria barra do toque) e nao so' outro numero -- o com
        # prazo (`_resolve_simulated_split_exit`) tem 1 barra de atraso
        # estrutural no arme e cai a MERCADO no estouro. Medido 2026-09-08:
        # trocar None por 8 virou o T3 fatiado de +R$12.928,50 para
        # -R$248,50. VALE SO' EM BACKTEST: em execucao real
        # `machine._resolve_live_split_exit` exige prazo (assert) -- uma
        # ordem-limite real sem prazo nenhum e' posicao exposta para sempre.
        self.exit_ttl_bars = None if exit_ttl_bars is None else int(exit_ttl_bars)

        self._state = _SessionState()
        # Estado de "ja armou a defesa de recuo" por POSICAO -- chave
        # `(side, entry_ts)`, mora no self por causa do snapshot read-only de
        # `IntradayOpenPosition` (ver a docstring do parametro `defesa_ativa`
        # acima). Resetado em `on_session_start`, mesmo espirito de `self.
        # _state`. So' cresce (nunca desarma dentro do mesmo trade) -- e' zerado
        # inteiro a cada pregao, entao nunca acumula alem do que a sessao usou.
        self._defesa_armada: dict[tuple[str, pd.Timestamp], bool] = {}
        # Melhor preco favoravel alcancado desde a entrada, por POSICAO --
        # mesma chave/mesmo motivo de `self._defesa_armada` (snapshot
        # read-only de `IntradayOpenPosition`, sem onde escrever de volta um
        # estado persistente). So' importa quando `self.trailing_ativo` e'
        # `True` -- ver a docstring do parametro `trailing_ativo` acima para
        # a formula exata. Resetado em `on_session_start`.
        self._trailing_pico: dict[tuple[str, pd.Timestamp], float] = {}
        # Buffer do gate de atividade (`gate_atividade_ativo`) -- deque de
        # `(ts, volume)` de CADA barra/tick recebido, recortado para os
        # ultimos `gate_janela_segundos` segundos a cada `on_bar`. Resetado
        # em `on_session_start`, mesmo padrao de `self._defesa_armada`/
        # `self._trailing_pico`. So' importa quando `self.gate_atividade_
        # ativo` e' `True`. Ver a docstring do parametro `gate_atividade_
        # ativo` em `__init__` para a mecanica completa.
        self._historico_recente: deque[tuple[pd.Timestamp, float]] = deque()
        # Contador de quantos armamentos o gate BLOQUEOU -- NUNCA resetado
        # em `on_session_start` (soma a vida INTEIRA do backtest/sessao ao
        # vivo, nao por pregao, diferente do resto do estado acima): e' o
        # numero que os scripts de medicao desta rodada leem para reportar
        # "quantas entradas o gate impediu". So' cresce quando `self.
        # gate_atividade_ativo` e' `True`.
        self.gate_bloqueios = 0
        # Atualizado por `on_capital_update`, chamado pelo motor logo antes
        # de cada `on_bar` -- 0.0 so' antes da primeira barra real. Desde
        # 2026-09-03 (LICOES_DE_PRODUCAO.md item 3.14) o warm start (replay
        # de `warm_start_calibration`) TAMBEM chama `on_capital_update`, uma
        # vez por barra do replay, quando o chamador passa `cash_brl` --
        # sem esse argumento (default `None`) o replay ainda nao chama o
        # hook, mesmo padrao antigo de `Gremah._cash_atual_brl`. So' importa
        # quando `margin_per_contract_brl` esta setado.
        self._cash_atual_brl = 0.0

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()
        self._defesa_armada = {}
        self._trailing_pico = {}
        self._historico_recente = deque()

    def on_capital_update(self, cash_brl: float) -> None:
        """Guarda o caixa acumulado para a proxima `EnterLimit` usar -- so'
        tem efeito quando `margin_per_contract_brl` esta setado."""
        self._cash_atual_brl = cash_brl

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        """Zera `pending_side` -- sem isto, uma `EnterLimit` recusada pelo
        teto de capital (`backtest.intraday.machine`) trava este robo pelo
        resto da sessao: `on_bar` (linha 476) so' rearma quando
        `pending_side is None`, e o unico outro lugar que zera isto e' o
        FILL confirmado (`if positions:`), que nunca acontece para uma ordem
        recusada. Bug real, incidente WDO F1 2026-08-28 (`LICOES_DE_
        PRODUCAO.md`, item 1.14): 20/20 recusas por capital amostradas
        deixavam o robo mudo pelo resto do pregao antes deste hook existir."""
        self._state.pending_side = None
        # Mesma razao do fill confirmado em `on_bar`: sem ordem parada o
        # freio de reprecificacao nao tem referencia, e uma recusa nao pode
        # herdar a espera da ordem que nao existe mais.
        self._state.pending_level = None
        self._state.pending_level_ts = None
        # Mesma razao: a memoria de histerese e' por RODADA, e uma ordem
        # recusada nao deixou nivel nenhum no book para "abandonar".
        self._state.nivel_abandonado = None
        # ... mas a RECUSA em si vira o relogio do freio de rearme (ver
        # `_pode_armar_apos_recusa`): zerar `pending_side` sem isto devolve o
        # robo ao ramo de ARMAR, que nao passa pelo freio de reprecificacao
        # -- e uma recusa que se repete a cada tick (capital abaixo do piso)
        # vira uma enxurrada de ordens NOVAS. Medido no motor tick,
        # 2026-03-04: 2.866 recusas por capital num pregao so', 2.874
        # armamentos, pico de 29 envios em 60s com o freio de
        # reprecificacao JA' ligado -- o teto ao vivo e' 30.
        self._state.ultima_recusa_ts = pd.Timestamp(ts)

    def _quantidade_da_entrada(self) -> int | None:
        """`self.quantity` intacto (pode ser `None`) por default -- o motor
        decide via `IntradayBacktestConfig.default_quantity`, exatamente
        como sempre foi. Com `margin_per_contract_brl` setado, ignora
        `self.quantity` e recalcula pelo caixa atual, com piso de 1 contrato
        (mesmo espirito de `Gremah._lotes_por_realocacao`: caixa
        genuinamente insuficiente ou ainda DESCONHECIDO -- `_cash_atual_brl`
        comeca em 0.0 -- nao pode virar uma entrada de zero contrato, que
        nao e' "menor", e' nenhuma).

        `contracts_from_capital_com_reserva` (nao a versao pura) desde
        2026-08-28 -- MESMA reserva de seguranca que o motor aplica no teto
        agregado (`backtest.intraday.machine.IntradaySessionMachine.
        _cap_capital_atual`), para o que esta estrategia PEDE nunca ficar
        mais otimista que o que o motor de fato deixa ABRIR (ver
        `strategy.daytrade.base.RESERVA_CAIXA_SEGURANCA`). O piso de 1
        continua por CIMA da reserva -- uma entrada calculada em 0 contratos
        (caixa insuficiente COM a reserva) ainda vira 1 aqui; e' o motor,
        nao a estrategia, quem tem a palavra final sobre recusar essa
        entrada por capital (`OrderRejected(reason="capital_insuficiente")`)
        -- ver a nota no proprio motor sobre porque a recusa mora la, nao
        aqui.

        `risco_pct_por_trade`/`point_value_brl` (2026-08-29, item 3.9),
        quando setados, aplicam um SEGUNDO teto por CIMA do de margem -- o
        stop deste robo e' fixo em ticks, entao o risco em reais por
        contrato tambem e': `stop_ticks x tick_size x point_value_brl`.
        Nunca cresce a entrada, so' pode encolhe-la mais ainda."""
        if self.margin_per_contract_brl is None:
            return self.quantity
        teto = contracts_from_capital_com_reserva(
            self._cash_atual_brl, self.margin_per_contract_brl, self.margin_buffer,
            hard_cap=self.hard_cap_contratos,
        )
        if self.risco_pct_por_trade is not None and self.stop_ticks is not None:
            stop_reais_por_contrato = self.stop_ticks * self.tick_size * self.point_value_brl
            if stop_reais_por_contrato > 0:
                teto_por_risco = contracts_from_risk(
                    self._cash_atual_brl, self.risco_pct_por_trade, stop_reais_por_contrato,
                )
                teto = min(teto, teto_por_risco)
        return max(1, teto)

    def _level_price(self, side: str) -> float:
        offset = self.level_spacing_ticks * self.tick_size
        anchor = self._state.anchor_price
        return (anchor - offset) if side == "long" else (anchor + offset)

    def _target_price(self, side: str, level_price: float) -> float:
        offset = self.profit_ticks * self.tick_size
        return level_price + offset if side == "long" else level_price - offset

    def _stop_price(self, side: str, level_price: float) -> float | None:
        if self.stop_ticks is None:
            return None
        offset = self.stop_ticks * self.tick_size
        return level_price - offset if side == "long" else level_price + offset

    def _pode_reprecar(self, bar: Bar, state: _SessionState) -> bool:
        """A ordem pendente pode ser SUBSTITUIDA nesta barra?

        Os dois portoes do freio de reprecificacao (ver `reancora_min_
        segundos`/`reancora_min_ticks` em `__init__`). Ambos precisam passar:
        o de TEMPO e' o que da' o teto duro de envios por minuto (no maximo
        `60/reancora_min_segundos` substituicoes por minuto, seja qual for o
        que o mercado faca); o de HISTERESE e' o que evita gastar essa cota
        indo e voltando entre dois niveis vizinhos.

        A HISTERESE (2026-09-08) tem DOIS pontos de referencia, nao um: o
        nivel candidato precisa estar a `reancora_min_ticks` ticks tanto do
        nivel PARADO quanto do ultimo nivel ABANDONADO nesta rodada. Sem o
        segundo, a ordem sai de A, anda a banda inteira ate B, e volta para A
        -- cada perna passa no portao e o par se repete para sempre, que e'
        exatamente o desperdicio que o dono apontou na rodada #21 de
        2026-09-08 (5105,0 -> 5105,5 -> 5105,0 -> 5105,5 -> 5106,5, tudo no
        mesmo segundo de parede). Ver a tabela de medicao em `__init__`.

        Estado ausente (`pending_level`/`pending_level_ts` em `None`) devolve
        `True` -- e' o caso de uma sessao restaurada por `warm_start_
        calibration` onde a ordem pendente veio de um processo anterior: sem
        saber quando ela foi armada, o freio nao tem contra o que medir, e
        travar a reancoragem por prudencia reintroduziria exatamente a ordem
        estacionada que o item 4.9 corrigiu. O teto de 30/60s do
        `live.intraday_runtime` continua valendo como rede.

        `bar.ts` (nao relogio de parede) de proposito: e' o unico carimbo
        que existe no backtest -- medir com dois relogios diferentes faria o
        numero calibrado aqui nao descrever o que acontece la'.

        CORRECAO 2026-09-08: ate' este dia a frase acima dizia tambem que
        `live.intraday_runtime._check_cadencia_de_ordens` usava o MESMO
        carimbo ao vivo (`evento.ts`). Usava, e era um furo -- nao um
        alinhamento. Um passo do supervisor processa todo o atraso do feed de
        uma vez, entao este portao pode estar corretamente segurando 10s de
        tempo de TICK enquanto a corretora recebe a rajada inteira em
        milissegundos de parede: 45 envios em 13s reais no pregao de
        2026-09-08, com a maquina 24 min atrasada. Este freio segue em
        `bar.ts` (e' regra de ESTRATEGIA, tem de valer identica no backtest);
        quem passou a ler o relogio de parede foi o contador de ENVIOS do
        runtime, que protege a corretora e por isso tem de viver no relogio
        dela. Os dois nao sao redundantes e nao medem a mesma coisa -- ver a
        docstring de `_check_cadencia_de_ordens`."""
        if state.pending_level_ts is not None and self.reancora_min_segundos > 0:
            espera = (bar.ts - state.pending_level_ts).total_seconds()
            if espera < self.reancora_min_segundos:
                return False
        if self.reancora_min_ticks <= 1:
            return True  # histerese desligada -- baseline de medicao, ver `__init__`
        # Nivel que ESTE tick produziria. Nao usa `_level_price` porque
        # `state.anchor_price` so' e' atualizado DEPOIS deste portao.
        offset = self.level_spacing_ticks * self.tick_size
        ancora_agora = no_tick(bar.close, self.tick_size)
        nivel_candidato = (ancora_agora - offset if state.pending_side == "long"
                           else ancora_agora + offset)
        for referencia in (state.pending_level, state.nivel_abandonado):
            if referencia is None:
                continue
            if abs(nivel_candidato - referencia) / self.tick_size < self.reancora_min_ticks - 1e-9:
                return False
        return True

    def _pode_armar_apos_recusa(self, bar: Bar, state: _SessionState) -> bool:
        """Ja' passou a espera desde a ULTIMA recusa? (`True` se nunca houve.)

        Simetrico de `_pode_reprecar`, com a mesma constante
        (`reancora_min_segundos`) e pelo mesmo motivo -- o que interessa e' o
        numero de ORDENS por minuto que chegam a' corretora, e tanto faz se
        cada uma e' substituicao ou ordem nova: `_check_cadencia_de_ordens`
        conta as duas no mesmo balde.

        NAO segura o rearme depois de um FILL: `ultima_recusa_ts` e' apagado
        quando a posicao abre (ver `on_bar`), entao a mecanica de reload
        (fecha -> rearma no mesmo nivel) continua saindo no tick seguinte,
        sem atraso. O freio so' morde a repeticao do que ACABOU DE FALHAR.

        Nao substitui `on_order_rejected` nem o desfaz (item 1.14): o robo
        continua rearmando sozinho depois de uma recusa -- so' que a cada
        `reancora_min_segundos`, em vez de a cada tick."""
        if state.ultima_recusa_ts is None or self.reancora_min_segundos <= 0:
            return True
        return ((bar.ts - state.ultima_recusa_ts).total_seconds()
                >= self.reancora_min_segundos)

    def _fills_of(self, side: str) -> int:
        return self._state.long_fills if side == "long" else self._state.short_fills

    def _next_side_to_arm(self) -> str | None:
        # Alterna comecando pelo lado que NAO acabou de fechar -- mesmo
        # espirito de `GridReloadMaker`: os dois lados rearmam de forma
        # independente, so' existe UMA ordem pendente por vez (o motor so'
        # permite uma posicao aberta simultanea, dado `quantity` fixo).
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)
        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None

    def _registrar_atividade(self, ts: pd.Timestamp, bar: Bar) -> None:
        """Empilha `(ts, bar.volume)` em `self._historico_recente` e
        descarta o que ja' saiu da janela de `gate_janela_segundos` -- mesmo
        padrao de recorte de `RollingVolumeWindow.registrar` (`strategy.
        daytrade.base`), reimplementado aqui (nao reusado) porque a
        granularidade e' outra (segundos fixos, nao minutos medios) e este
        gate nao precisa de cauda do pregao anterior. So' chamada quando
        `self.gate_atividade_ativo` ja e' `True`."""
        self._historico_recente.append((ts, bar.volume))
        limite = ts - pd.Timedelta(seconds=self.gate_janela_segundos)
        while self._historico_recente and self._historico_recente[0][0] <= limite:
            self._historico_recente.popleft()

    def _volume_recente(self) -> float:
        """Soma do volume em `self._historico_recente` -- ja' vem recortado
        para a janela de `gate_janela_segundos` por `_registrar_atividade`."""
        return sum(v for _, v in self._historico_recente)

    def _defesa_deve_fechar(self, pos: IntradayOpenPosition, bar: Bar) -> bool:
        """`True` se a defesa de recuo (`defesa_ativa`) manda fechar `pos`
        AGORA -- ver a docstring do parametro `defesa_ativa` em `__init__`
        para a mecanica completa e a formula exata. So' chamada quando
        `self.defesa_ativa` ja e' `True`."""
        if self.tick_size <= 0 or pos.current_stop is None:
            return False  # sem grade de preco ou sem stop, nada a derivar
        eps = 1e-9
        chave = (pos.side, pos.entry_ts)
        stop_ticks_pos = abs(pos.entry_price - pos.current_stop) / self.tick_size
        if stop_ticks_pos <= 0:
            return False

        if not self._defesa_armada.get(chave, False):
            preco_adverso = bar.low if pos.side == "long" else bar.high
            excursao_ticks = (
                (pos.entry_price - preco_adverso) if pos.side == "long"
                else (preco_adverso - pos.entry_price)
            ) / self.tick_size
            excursao_ticks = max(0.0, excursao_ticks)
            gatilho_ticks = self.defesa_gatilho_stop_pct * stop_ticks_pos
            if excursao_ticks + eps >= gatilho_ticks:
                self._defesa_armada[chave] = True
            else:
                return False  # ainda nao armou -- nao ha' o que checar de alvo

        if pos.current_target is None:
            return False  # armada, mas sem alvo declarado -- nao ha' proximidade a medir
        dist_total_ticks = abs(pos.current_target - pos.entry_price) / self.tick_size
        if dist_total_ticks <= 0:
            return False
        preco_favoravel = bar.high if pos.side == "long" else bar.low
        dist_restante_ticks = (
            (pos.current_target - preco_favoravel) if pos.side == "long"
            else (preco_favoravel - pos.current_target)
        ) / self.tick_size
        dist_restante_ticks = max(0.0, dist_restante_ticks)
        fracao_restante = dist_restante_ticks / dist_total_ticks
        return fracao_restante <= self.defesa_alvo_proximidade_pct + eps

    def _trailing_deve_fechar(self, pos: IntradayOpenPosition, bar: Bar) -> bool:
        """`True` se o trailing sobre o lucro (`trailing_ativo`) manda fechar
        `pos` AGORA -- ver a docstring do parametro `trailing_ativo` em
        `__init__` para a mecanica completa e a formula exata. So' chamada
        quando `self.trailing_ativo` ja e' `True` (e, por construcao de
        `on_bar`, `pos.current_target` e' sempre `None` neste caminho --
        quem carrega o piso e' `self.profit_ticks`, nao o alvo da posicao)."""
        if self.tick_size <= 0:
            return False  # sem grade de preco, nada a derivar
        eps = 1e-9
        chave = (pos.side, pos.entry_ts)
        preco_favoravel = bar.high if pos.side == "long" else bar.low
        pico_anterior = self._trailing_pico.get(chave, pos.entry_price)
        pico = (max(pico_anterior, preco_favoravel) if pos.side == "long"
                else min(pico_anterior, preco_favoravel))
        self._trailing_pico[chave] = pico

        ticks_do_pico = abs(pico - pos.entry_price) / self.tick_size
        if ticks_do_pico + eps < self.profit_ticks:
            return False  # piso ainda nao alcancado -- nunca fecha antes disso a favor

        preco_adverso = bar.low if pos.side == "long" else bar.high
        recuo_ticks = (
            (pico - preco_adverso) if pos.side == "long" else (preco_adverso - pico)
        ) / self.tick_size
        recuo_ticks = max(0.0, recuo_ticks)
        return recuo_ticks > (self.trailing_recuo_ticks or 0) + eps

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []

        if self.gate_atividade_ativo:
            # Atualiza o buffer de atividade em TODA chamada -- nao so'
            # quando ha' sinal de entrada -- para a janela de
            # `gate_janela_segundos` estar sempre corrente quando o robo
            # precisar consulta-la mais abaixo. Ver a docstring do
            # parametro `gate_atividade_ativo` em `__init__`.
            self._registrar_atividade(ts, bar)

        if state.open_price is None:
            # `no_tick`: a serie CONTINUA do MT5 (`WDO@`) reporta preco fora
            # da grade real de negociacao (ex.: 5769,053, quando o WDOV26
            # so' negocia em multiplos de 0,5) -- ancorar o grid num preco
            # assim faria TODOS os niveis derivados carem fora da grade
            # tambem (offset multiplo de `tick_size` somado a um preco ja
            # torto continua torto). Ver a armadilha medida documentada em
            # `backtest.intraday.profiles.SymbolProfile.price_tick_size`.
            state.open_price = no_tick(bar.open, self.tick_size)
            state.anchor_price = state.open_price

        if (self.session_stop_brl is not None and not state.session_halted
                and session_pnl_brl <= -self.session_stop_brl):
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if positions:
            # Confirma o preenchimento da EnterLimit pendente (a entrada),
            # se for o caso -- so' acontece na PRIMEIRA chamada com posicao
            # aberta apos a ordem ter sido emitida.
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
                # Nao ha' mais ordem parada: o freio de reprecificacao nao
                # tem contra o que medir, e deixar o rastro da anterior faria
                # o proximo armamento herdar uma espera que nao e' dele.
                state.pending_level = None
                state.pending_level_ts = None
                # A rodada acabou aqui: a memoria de histerese e' POR RODADA
                # (`nivel_abandonado`), senao o rearme pos-fechamento herdaria
                # a proibicao de um nivel que a rodada ANTERIOR abandonou --
                # e rearmar no mesmo nivel de antes e' justamente a mecanica
                # de reload que da' nome ao robo.
                state.nivel_abandonado = None
                # PREENCHEU -- o caminho normal do robo. Apaga o relogio de
                # recusa para o rearme pos-fechamento (a mecanica de reload,
                # o coracao desta estrategia) sair na hora, sem freio nenhum.
                state.ultima_recusa_ts = None
            if self.defesa_ativa:
                # Prioridade da defesa sobre a logica normal desta chamada
                # (que aqui e' so' "nao faca nada, alvo/stop ja sao geridos
                # pelo motor") -- ver a docstring do parametro `defesa_ativa`.
                for pos in positions:
                    if self._defesa_deve_fechar(pos, bar):
                        return [Exit(reason="defesa_recuo")]
            if self.trailing_ativo:
                # `initial_target=None` nesta entrada (ver o fim desta funcao)
                # -- o alvo estatico de sempre NUNCA existiu para esta
                # posicao, entao e' este `on_bar`, e so' ele, quem decide
                # quando o lucro fecha. Ver a docstring do parametro
                # `trailing_ativo` para a formula exata.
                for pos in positions:
                    if self._trailing_deve_fechar(pos, bar):
                        return [Exit(reason="trailing_lucro")]
                return []
            return []  # alvo e stop ja sao geridos pelo motor (initial_target/initial_stop)

        # Sem posicao. Se `open_side` ainda estava marcado, a posicao que
        # existia na chamada anterior fechou entre uma chamada e outra (via
        # alvo ou stop, geridos pelo motor sem passar por uma acao explicita
        # da estrategia) -- registra qual lado foi, pra decidir o proximo a
        # recarregar.
        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        if state.pending_side is not None:
            if self.reanchor_mode != "rolling_last_price":
                return actions  # "fixed_session_open": ancora nunca muda, nada a reprecar
            # 2026-09-04 (bug real, LICOES_DE_PRODUCAO.md item 4.9): ate' aqui
            # esta funcao devolvia cedo SEMPRE que ja havia uma EnterLimit
            # pendente, entao uma ordem que nao tocava ficava ESTACIONADA pelo
            # resto do pregao se o preco se afastasse e nao voltasse -- medido
            # em producao: 0%/8,0%/14,3%/11,1%/0% do pregao ATIVO (1a entrada
            # ate' ultima saida) na semana de 2026-08-31 a 2026-09-04, com o
            # robo chegando a NAO OPERAR em 2 dos 5 pregoes apesar do mercado
            # andar dezenas de pontos. Pedido do dono: "se nao bater no preco
            # e surgir outro sinal, a [ordem] pendente deve ser cancelada e a
            # do novo sinal deve ser aberta" -- este robo nao tem sinal
            # direcional separado da ancora, entao o "outro sinal" e' o
            # proprio nivel recalculado a cada barra. Reancora AQUI tambem
            # (mesmo com ordem pendente), para o MESMO lado que ja estava
            # pendente -- so' o preco da ordem pode mudar, nunca o lado.
            #
            # FREIO DE REPRECIFICACAO (2026-09-07) -- ver `reancora_min_
            # segundos`/`reancora_min_ticks` em `__init__`. Sem ele este ramo
            # emite uma `EnterLimit` nova a cada TICK em que o nivel muda, e
            # ao vivo cada uma delas vira cancelar+reenviar na corretora:
            # medido no motor tick, ate' 38.260 envios num unico pregao e
            # 1.162 numa unica janela de 60s -- contra a cota de 120/60s de
            # `live.intraday_runtime.COTA_ENVIOS_POR_MINUTO` (que recusa so'
            # a ordem excedente) e o teto de patologia de 600/60s
            # (`MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO`, que liga `disaster_halt`
            # e para o robo pelo resto do pregao -- e que 1.162 estoura).
            # O freio mora AQUI (na estrategia), nunca no `live/`:
            # regra do projeto e' que `live/` nao decide nada, e um freio que
            # so' existisse ao vivo faria o backtest deixar de descrever a
            # producao.
            if not self._pode_reprecar(bar, state):
                return actions
            next_side = state.pending_side
        else:
            # FREIO DE REARME APOS RECUSA (2026-09-07) -- o segundo lado do
            # mesmo problema. Uma `EnterLimit` recusada (motor: teto de
            # capital; ao vivo: margem) zera `pending_side`, e sem este
            # portao o robo cai AQUI e arma de novo no tick seguinte, com o
            # mesmo caixa que acabou de ser recusado -- laco que so' para
            # quando o pregao acaba. Nao passa pelo freio de reprecificacao
            # acima porque nao ha' ordem pendente para reprecar: sao ordens
            # NOVAS. Medido no motor tick (2026-03-04, capital real R$375):
            # 2.874 armamentos para 7 trades, 2.866 deles recusados por
            # capital, pico de 29 envios/60s com o freio de reprecificacao
            # ja' ligado -- o teto ao vivo e' 30.
            if not self._pode_armar_apos_recusa(bar, state):
                return actions
            next_side = self._next_side_to_arm()
            if next_side is None:
                return actions  # os dois lados esgotaram max_trades_per_side nesta sessao
            if self.gate_atividade_ativo and self._volume_recente() <= self.gate_volume_min:
                # Gate de atividade (`gate_atividade_ativo`): so' se aplica
                # ao PRIMEIRO armamento de uma entrada (este ramo -- nunca ao
                # ramo de REANCORAGEM de ordem ja' pendente, acima). Volume
                # recente insuficiente -- nao arma nada nesta chamada, mesmo
                # espirito de "espera a proxima" que `max_trades_per_side`
                # esgotado ja' usa. Ver a docstring do parametro em
                # `__init__` para a mecanica completa.
                self.gate_bloqueios += 1
                return actions

        if self.reanchor_mode == "rolling_last_price":
            # Rearma seguindo o preco -- a ancora vira o FECHAMENTO da barra
            # que acabou de fechar (`bar`, ja conhecida, sem look-ahead: a
            # ordem so' executa em barra FUTURA -- ver `_on_closed_bar_core`
            # em `backtest.intraday.machine`, passo (3b) resolve o fill da
            # ordem pendente ANTES de chamar `on_bar` da barra corrente,
            # entao a EnterLimit devolvida aqui so' pode ser tocada a partir
            # da PROXIMA barra). Mesmo espirito do modo "rolling" de `Gremah`
            # (`gremah.py::on_bar`, `anchor = bar.close`) -- ver
            # `ReanchorMode` para o porque de nao usar "fixed_session_open"
            # por default.
            state.anchor_price = no_tick(bar.close, self.tick_size)
        # "fixed_session_open": `state.anchor_price` ja' foi fixado em
        # `state.open_price` na primeira barra da sessao e nunca muda.

        state.pending_side = next_side
        level_price = self._level_price(next_side)
        # Marca a ordem que passa a estar parada no book: o freio de
        # reprecificacao mede DERIVA (contra `pending_level`) e ESPERA
        # (contra `pending_level_ts`) a partir da ULTIMA emissao -- tanto de
        # um armamento novo quanto de uma substituicao. Marcar so' nas
        # substituicoes deixaria a 1a reprecificacao de cada rodada passar
        # livre, que e' justamente o instante de maior rajada (logo apos o
        # fill anterior).
        #
        # ...e, quando o nivel MUDA de verdade, guarda o que esta' saindo do
        # book como `nivel_abandonado`: e' a memoria que impede a proxima
        # reancoragem de devolver a ordem para ca' (histerese, ver
        # `_pode_reprecar`). Nivel IGUAL nao abandona nada -- o motor trata
        # isso como no-op (`machine._reancoragem_no_mesmo_nivel`) e a ordem
        # nunca sai do book, entao a fila acumulada continua de pe'.
        if state.pending_level is not None and abs(state.pending_level - level_price) > 1e-9:
            state.nivel_abandonado = state.pending_level
        state.pending_level = level_price
        state.pending_level_ts = bar.ts
        return [EnterLimit(
            side=next_side,
            limit_price=level_price,
            # `trailing_ativo`: SEM alvo estatico -- o motor fecharia a
            # posicao no instante em que `profit_ticks` fosse tocado (mesma
            # prioridade "(1) stop/target automatico" de sempre), o que
            # impediria por construcao qualquer monitoramento POSTERIOR ao
            # piso. Ver a docstring do parametro `trailing_ativo` em
            # `__init__`. `False` (default): comportamento IDENTICO a antes.
            initial_target=(None if self.trailing_ativo
                             else self._target_price(next_side, level_price)),
            initial_stop=self._stop_price(next_side, level_price),
            quantity=self._quantidade_da_entrada(),
            exit_split_unit=(self._quantidade_da_entrada() if self.fatiar_saida_alvo else None),
            exit_ttl_bars=(self.exit_ttl_bars if self.fatiar_saida_alvo else None),
            reason="wdo_grid_reload_" + next_side,
        )]
