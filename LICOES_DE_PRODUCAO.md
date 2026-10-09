# Lições de produção — o que já custou, e a regra que sobrou

> **Registro vivo.** Este arquivo é a FONTE; a versão publicada para leitura está
> em <https://claude.ai/code/artifact/9a682e56-04b6-4b70-8da3-c5d410076b9d>.
> Todo bug que custar dinheiro real, todo erro de método que invalidar uma
> medição e toda lacuna que uma auditoria achar viram item novo aqui — e a
> página é republicada NA MESMA URL. Ver `CLAUDE.md` § "O Que Já Custou" para a
> forma de um item e o procedimento.

Este arquivo existe por um motivo específico: **portar a estratégia para outra
linguagem/plataforma não porta o aprendizado.** O código vai embora; os modos de
falha ficam. Cada item aqui é um erro que já aconteceu neste projeto, o número
que ele custou, e o invariante que impede a repetição — escrito de forma que
sobreviva à troca de Python/MT5 por qualquer outra coisa.

**Como ler.** Cada item tem a mesma forma: o que aconteceu → **a regra**. Onde a
regra depende da plataforma, ela vira uma **pergunta a fazer à plataforma nova**
antes da primeira ordem real. Não copie o mecanismo; responda a pergunta.

**O que NÃO está aqui.** Hipóteses de estratégia refutadas (isso é resultado de
pesquisa, não lição de engenharia) e detalhes de API do MT5 que não generalizam.
O que está aqui é o que continua verdadeiro em qualquer corretora, qualquer
linguagem, qualquer book.

Um aviso sobre a origem destes itens: quase todos foram descobertos **depois** de
já estarem em produção, e vários só apareceram porque alguém foi procurar. A
lista não é a garantia de que o próximo sistema estará certo. É o piso.

---

## Parte 0 — O incidente que ancora quase tudo

2026-08-28, primeiro dia em que um robô de futuro conseguiu de fato mandar
ordem: **conta zerada, saldo final −R$298,60, patrimônio NEGATIVO.**

A reconstrução, número a número, a partir do extrato do terminal:

| Hora | Negócio |
|---|---|
| 11:58:53 | compra 1 @ 5204,00, fecha @ 5203,50 — −R$5,00 |
| 11:58:59 | vende 1 @ 5203,50 |
| 11:59:04 | vende **mais 1** @ 5204,00 → vendido em 2 |
| 12:59:46 | compra 2 @ **5218,50** → **−R$295,00** |

Cinco falhas encadeadas, todas independentes, todas presentes ao mesmo tempo:

1. **Abriu 2 contratos numa conta dimensionada para 1.** As duas entradas saíram
   com 5 segundos de diferença — um passo do laço. O teto de capital era
   aplicado por ordem, nunca contra a exposição agregada, então cada uma passou
   sozinha.
2. **Ficou preso: tentou fechar ~24 vezes e a corretora recusou todas.** A ordem
   de fechamento não levava o identificador da posição, então o motor de risco da
   corretora a tratou como abertura nova — e com a margem esgotada, recusou.
   A mensagem de erro dizia literalmente *"Para abrir novas posições"* numa ordem
   de FECHAR.
3. **A posição ficou sem stop nem alvo registrados na corretora por uma hora**,
   atravessando 3 reinícios do processo. O stop era lógica no laço, não ordem
   registrada. Processo morto = posição nua.
4. **A detecção de contrato escolheu um símbolo sem book** (critério "maior
   volume" lendo o volume do ÚLTIMO TICK, ruidoso).
5. **Nenhum freio.** O único existente disparava em patrimônio ≤ 0 — quando já
   não há o que salvar.

Duas coisas ficaram **provadas**, não deduzidas: as duas entradas saíram com 5
segundos de diferença, e **o robô nunca fechou nada** — quem encerrou às 12:59:46
foi um stop anexado à mão. Sem aquela intervenção, a posição continuaria.

> **A regra que resume o incidente inteiro:** o robô era TOP-1 do pódio, com 89%
> de retenção fora da amostra, e zerou a conta no primeiro dia — **por execução,
> não por sinal.** Backtest positivo não é evidência sobre execução. São duas
> perguntas diferentes e só uma delas tinha sido feita.

---

## Parte 1 — Execução: as que custam dinheiro no mesmo dia

### 1.1 Fechar e abrir são operações diferentes para o risco da corretora

A ordem de fechamento não levava o identificador da posição. Sem ele, o motor de
risco não sabe que a ordem ABATE exposição existente e a trata como abertura
nova. Com margem esgotada, recusa — exatamente quando fechar é mais necessário.

> **Regra:** toda ordem de fechamento identifica explicitamente o que está
> fechando. **Pergunte à plataforma nova:** existe uma primitiva de "fechar
> posição" distinta de "enviar ordem no sentido contrário"? Se existir, use-a
> sempre. Se não existir, descubra como a corretora distingue as duas coisas
> antes de precisar disso com margem no limite.

### 1.2 Proteção tem de morar na CORRETORA, não no laço do processo

Stop que depende do processo estar vivo não é stop — é intenção. O processo
morreu 3 vezes e a posição atravessou tudo nua.

A correção não foi "reenviar o stop mais rápido". Foi mandar stop e alvo **no
mesmo request que registra a ordem de entrada**, para a corretora amarrar a
proteção no instante do preenchimento: zero janela, nenhum processo no meio. O
reenvio periódico continua existindo, mas rebaixado a **rede** — repõe proteção
que sumiu, acompanha stop que a estratégia moveu, cobre posição herdada de
reinício.

> **Regra:** a proteção sai junto com a ordem, atomicamente, ou não é proteção.
> **Pergunte à plataforma nova:** dá para enviar stop e alvo no mesmo comando da
> entrada? Se sim, é o caminho padrão, não uma otimização. Se não, qual é a menor
> janela possível — e ela é aceitável para o tamanho da sua posição?

### 1.3 Recusar a entrada é melhor que abrir posição nua

Se a corretora recusar a ordem porque não gostou do stop/alvo embutido, a entrada
simplesmente não acontece. Perder uma entrada é barato. Abrir sem proteção não.

### 1.4 Em conta consolidada, ordem maior que a posição INVERTE — não "fecha demais"

O fechamento parcial foi o caso: a máquina só descontava a quantidade depois do
sucesso, então uma tentativa seguinte mandava o total antigo contra o que sobrou.
Numa conta que consolida posição por símbolo (netting), o excedente não é
rejeitado — vira posição nova no lado oposto, sem stop, sem alvo, sem ninguém
saber.

> **Regra:** toda ordem de fechamento é limitada por `min(o que eu acho que
> tenho, o que a corretora diz que eu tenho)`. **Pergunte à plataforma nova:** a
> conta é netting ou hedging? A resposta muda o que "ordem grande demais"
> significa — e num caso o erro é silencioso. **O item 1.23 é a MESMA inversão
> por outro caminho:** duas ordens do tamanho CERTO, chegando pelo mesmo
> fechamento (a do robô e o `sl` que a corretora já tinha registrado), somam
> exatamente como uma ordem grande demais.

### 1.5 "Cancelei" só vale se a corretora confirmou

O bug mais caro do projeto, e o mais invisível. A função de cancelamento marcava
a ordem como CANCELADA nos **dois** ramos — sucesso e falha — com a justificativa
de "não virar tentativa infinita". Como CANCELADA é estado terminal e todo o
rastreamento de ordem órfã filtrava por "não terminal", o efeito real era que
**nenhuma ordem órfã era rastreada. Nunca.** Um mecanismo inteiro, com testes
verdes, que não funcionava.

Consequência mais grave: a rotina de "remover robô" dava a corretora por limpa e
apagava a conta **com ordem viva no book** — que depois preenche sozinha, sem
robô, sem stop e sem painel.

> **Regra:** só marque terminal o que a contraparte confirmou. "Não consegui
> perguntar" é tratado como VIVO, sempre. Um estado terminal errado não é um
> retry perdido — é um mecanismo de segurança inteiro desligado em silêncio.

### 1.6 Falha de CONSULTA nunca vira "não aconteceu"

A leitura de posição devolvia o mesmo valor para "perguntei e não há posição" e
"não consegui perguntar". Um terminal fora do ar virava conta zerada: o sistema
registrava uma saída **inventada** no diário e a máquina ficava sem posição — o
que, de quebra, desarmava o freio de emergência (ele só agia sobre posições que a
máquina conhecia).

> **Regra:** toda consulta ao mundo externo tem TRÊS respostas: sim, não, e **não
> sei**. Achatar as duas últimas numa só é como este sistema inventa fatos. "Não
> sei" nunca autoriza uma ação e nunca fecha um registro.

### 1.7 Pergunte à corretora o que existe, mesmo quando você acha que não há nada

Nenhuma rotina consultava a exposição real a menos que a máquina **já
acreditasse** ter alguma coisa. Posição que a máquina perdeu de vista — reinício
que não reidratou, preenchimento que chegou depois do processo morrer — ficava
estruturalmente invisível.

É a forma exata do incidente: a máquina achava 1 contrato, a corretora tinha 2, e
ninguém comparava os dois números.

> **Regra:** a cada passo, compare a exposição que você acha que tem com a que a
> corretora reporta. Divergência é alarme alto e trava a abertura de ordem nova.
> **Não feche automaticamente:** fechar às cegas uma exposição cuja origem
> ninguém entendeu troca um problema conhecido por um desconhecido — e nesta
> conta já houve fechamento recusado 24 vezes seguidas.

### 1.8 Ordem que ninguém está vigiando tem de morrer

A ordem real sai no meio do passo; o registro dela só vira linha durável no fim.
Processo morto nessa janela e o reinício não sabe do ticket, redecide do zero e
manda uma **segunda** ordem no mesmo nível. É o "2 contratos numa conta de 1"
pelo lado da entrada.

Nenhum arquivo escrito "mais cedo" resolve isso de verdade. Quem sabe é a
corretora.

> **Regra:** **a corretora é a única memória durável de uma ordem enviada.** No
> início de cada sessão e depois de qualquer buraco, pergunte quais ordens suas
> estão vivas, adote as que você não conhecia, e cancele toda que a máquina não
> está vigiando.

### 1.9 O freio tem de enxergar a ordem parada, não só a posição aberta

O freio de emergência saía na primeira linha quando não havia posição — e deixava
intacta a ordem-limite parada no book. Resultado: robô em "não abro mais nada"
com uma ordem que abre sozinha, e já cego (freio acionado = não consome mais
dados, não redecide).

> **Regra:** "estou zerado" inclui ordem pendente. Uma ordem viva é exposição
> futura contratada.

### 1.10 Zerar proteção por omissão

Ao atualizar stop e alvo, mandar zero no campo do alvo não significa "deixa como
está" — significa **remover**. Uma estratégia sem alvo apagava a proteção
existente a cada reforço.

> **Regra:** ao atualizar proteção, o lado sem pedido PRESERVA o que já está
> registrado, e o stop nunca afrouxa contra o que já existe. Descubra qual é a
> semântica de "campo vazio" na sua plataforma antes de escrever a rotina.

### 1.11 O nível recalculado contra o preço vivo foge do preço

A rotina que afastava o stop da distância mínima exigida pela corretora
recalculava contra o preço **do instante da chamada**. E a chamada acontecia a
cada barra, porque a comparação era "o que pedi" contra "o que está registrado" —
que diferem legitimamente pela distância mínima. Resultado: conforme o preço se
aproximava do stop, o stop **fugia dele**.

> **Regra:** guarde o par (pedido, registrado) e só reenvie quando algo de fato
> mudou. Um nível de proteção é uma decisão da estratégia, não uma função do
> preço corrente.

### 1.12 Alarme por processo silencia todas as posições seguintes

O aviso de "não consegui proteger" era um booleano do processo. Uma falha
silenciava o alerta de TODAS as posições posteriores.

> **Regra:** deduplicação de alerta é por objeto (posição, ticket), nunca por
> processo.

### 1.13 Recusa repetida tem de escalar

As ~24 recusas de fechamento nunca escalaram além de linha de log repetida por
minutos. Ninguém viu.

> **Regra:** N recusas seguidas da mesma operação mudam o comportamento, não só o
> log. E há um teto de envios por janela de tempo: operação normal decide no
> máximo uma entrada por barra — qualquer coisa muito acima disso é laço, não
> operação.

### 1.14 Recusa de preenchimento sem aviso de volta trava a máquina de estados inteira — CORRIGIDO 2026-08-29

Medido rodando a WDO F1 com caixa real (R$300 a R$3.000) nos 177 pregões
completos de WDO@ disponíveis (2025-12-09 a 2026-08-28): 136 ordens recusadas
por capital insuficiente no instante do preenchimento (teto dinâmico por caixa,
a própria correção do incidente da Parte 0) — e nas 20 primeiras verificadas,
**20 de 20** o robô nunca mais operou pelo resto daquele pregão, quase sempre
recusado ainda nos primeiros minutos da sessão (~12:01 UTC). Causa: a
estratégia marca "aguardando confirmação de preenchimento" ao enviar a ordem e
só limpa essa marca quando vê posição aberta de volta. A recusa descarta a
ordem inteira no motor sem passar por esse caminho — a estratégia nunca sabe
que o pedido morreu, e o "aguardando" fica para sempre, mesmo que o caixa se
recupere no minuto seguinte. Contaminou também a MEDIÇÃO: comparar o líquido
"com caixa real" contra o líquido "com caixa nocional" estava comparando sinal
contra sinal-mais-mudez, não sinal contra sizing.

**Correção aplicada:** novo hook `IntradayStrategy.on_order_rejected(ts)`
(default no-op), chamado pelo motor (`backtest/intraday/machine.py`) nos dois
pontos onde uma ordem morre sem preencher — `Enter` a mercado recusado, e o
ÚLTIMO filho de uma `EnterLimit` recusado sem nenhum filho aceito (uma ordem
fatiada com pelo menos 1 filho aceito não dispara isto — `positions` deixa de
estar vazia e o caminho normal já resolve). Implementado nos 3 robôs do pódio
que guardam esse estado próprio fora de `positions` — `WdoGridReloadMaker`,
`Gremah`, `GremahTick` — zerando `pending_side` (e equivalentes) no aviso.
`CopaWin` não precisou: seu `_espera` já era um contador com TTL próprio,
autocurativo por desenho. Suíte inteira (1.566 testes) verde depois da mudança.

**Achado ao VERIFICAR a correção, mais importante que o fix em si:** rodar de
novo os mesmos testes de caixa real (T1/S4 e T1/S16, R$300/R$375/R$3.000) deu
os MESMOS números, trade a trade — o fix não mudou nenhum resultado histórico
da WDO F1. Motivo: este robô nunca piramida e sempre pede 1 contrato
(`motor_nao_piramida_2026_08_26`), então TODA recusa por capital dela é
`cap_capital_atual() == 0` (caixa abaixo do piso de margem), nunca "cabe mas
`open_contracts` já ocupa a vaga". E `cap_capital_atual` só muda quando um
trade fecha e altera `realized_pnl` — que não pode acontecer sem caixa. É a
mesma catraca de ruína da Parte 1.13/`dois_pisos_censuram_backtest_2026_08_26`,
vista de outro ângulo: uma vez abaixo do piso, nem uma correção de bug tira o
robô de lá. O estado "aguardando" agora fica CORRETO (deixa de mentir que uma
ordem morta ainda existe), mas só passa a mudar resultado de verdade num robô
que PODE ter `open_contracts` ocupando a vaga com caixa disponível — o caso de
`Gremah`/`GremahTick` com entrada fatiada (`dividir_entrada`), onde uma posição
existente fechar libera vaga para uma nova ordem AINDA no mesmo pregão.

> **Regra:** toda decisão "aguardando confirmação" precisa de caminho de volta
> para os DOIS desfechos — confirmado E recusado — não só o feliz. Um estado
> que só uma trilha limpa é um estado que trava para sempre na outra. Mas medir
> o EFEITO do conserto importa tanto quanto o conserto: um estado incorreto
> pode ser genuinamente inofensivo se a causa-raiz da rejeição (aqui, caixa
> abaixo do piso) já é irrecuperável por outro motivo — corrigir a mentira no
> estado não é o mesmo que destravar o robô.
> **Pergunte à plataforma nova:** o evento de rejeição de uma ordem chega de
> volta pra quem decidiu, ou fica só no log do motor de execução? Se só fica no
> motor, a estratégia precisa de outro sinal (timeout, checagem de vida) para
> saber que aquele pedido morreu — do contrário qualquer rejeição isolada
> aposenta o robô pelo resto do pregão, em silêncio.

### 1.15 A correção do campo `position` (item 1.1, MG51) não cobriu ordem PENDENTE de fechamento — CORRIGIDO 2026-09-03

Achado de auditoria adversarial em 2026-09-03, ainda NÃO confirmado contra
terminal real — registrado porque é a mesma classe estrutural de bug que já
custou dinheiro uma vez (item 1.1), num caminho que toca robô ao vivo hoje.
Depois do incidente, `close_position()`/`_send()` (ordem de fechamento A
MERCADO) passaram a enviar sempre `request["position"]=<ticket>`. Mas
`MT5Broker.place_pending()` — usado por `place_exit_limit()` para a fatia de
SAÍDA por alvo quando a estratégia declara `exit_split_unit` — nunca ganhou
esse campo; não existe nem parâmetro pra ele na assinatura do método. Esse
caminho está ativo em produção: `gremah`/`gremah_tick` (os robôs campeões de
day trade) usam `exit_split_unit` sempre que `dividir_entrada=True` — o
default —, e `dt-gremah_tick-pmam3-live` operava com dinheiro real no
momento deste achado. Não foi possível confirmar sem terminal MT5 real se
uma ordem `TRADE_ACTION_PENDING` de fechamento sofre a mesma rejeição de
margem que a ordem a mercado sofreu (MG51) — o comportamento do MT5 para
pendente pode ser diferente do comportamento pra ordem a mercado — mas
ninguém verificou, e é exatamente o tipo de lacuna que só aparece no
primeiro pregão em que as condições batem, como da última vez.

> **Regra:** quando um incidente revela que um campo faltava num caminho de
> ordem, procurar TODOS os métodos irmãos que montam o MESMO tipo de
> request (mercado, pendente, parcial) antes de declarar corrigido — o bug
> tende a estar duplicado em qualquer lugar que reimplementou a mesma
> lógica de request separadamente.
> **Pergunte à plataforma nova:** ordem PENDENTE de fechamento (limite, não
> a mercado) tem a mesma exigência de "amarrar à posição" que ordem a
> mercado de fechamento? Testar antes de confiar no caminho de saída
> fatiada com posição real — não assumir que a correção de um caminho
> cobriu o irmão.

**Correção aplicada:** o identificador da posição passou a viajar no request
da ordem pendente de fechamento, e é lido da corretora no instante em que a
ordem é armada — não de um campo em memória preenchido pelo processo
anterior, que um reinício no meio do pregão deixaria vazio para sempre.
`sl`/`tp` deixaram de viajar quando a ordem está fechando (ordem que fecha
não abre nada pra proteger); na prática era no-op, porque a fatia de saída
nunca preenchia esses campos, mas a exclusão agora é explícita como já era no
caminho a mercado. Como a aceitação do campo em ordem pendente **continua não
confirmada** contra terminal real, o envio nunca assume que ela existe: se a
recusa tiver código de "request inválido", reenvia UMA vez sem o campo, com
alarme no log do processo — nunca um laço, e recusa por preço/margem/mercado
fechado não aciona o reenvio (o motivo real da recusa não pode ficar
escondido atrás de um fallback que não tem relação com ele).

Fica um risco residual honesto: o conjunto de códigos de recusa que dispara o
reenvio é suposição documentada, não fato medido. Se a plataforma recusar com
um código fora desse conjunto, a ordem fica recusada — sem regressão, mas sem
rede. A pergunta 6 da Parte 8 continua valendo integralmente.

### 1.16 Um desfecho, duas causas: alarme com a causa errada ensina a desconfiar do diário

Achado em revisão de código em 2026-09-03, antes de chegar à produção — e o
alarme falso foi introduzido justamente pela correção do item 3.15, que é
como esse tipo de defeito costuma nascer. A rotina de retomada passou a
avisar no diário quando o teto agregado encolhe ou descarta a ordem que o
robô pediu (item 3.15). Só que a função que planta a ordem devolve "não
plantei" por DOIS motivos diferentes: o teto não comportar nada, e já existir
posição aberta — caso em que ela recusa plantar **de propósito**, porque uma
ordem plantada por cima de uma posição viva fica órfã quando a posição
fechar. O aviso novo atribuía os dois ao teto, em nível de erro. Reinício no
meio do pregão segurando posição não é caso raro: é o cenário comum de
reinício. O diário ia acumular alarme de erro com a causa errada exatamente
no momento em que o dono mais precisa confiar nele.

> **Regra:** quando um mesmo desfecho observável tem mais de uma causa, o
> registro tem de dizer QUAL — e o nível do alarme segue a causa, não o
> desfecho. Desenho funcionando como planejado é informação (nível baixo);
> portão estourado é alarme. Misturar os dois treina o operador a ignorar a
> categoria inteira, e aí o alarme verdadeiro também é perdido. Mesma
> distinção que o item 1.6 faz entre "não sei" e "não há", e o item 3.13
> entre "não consegui verificar a margem" e "a margem não cobre".

### 1.17 Preenchimento que só existe ENTRE dois polls é invisível para quem só pergunta "o que eu tenho agora" — CORRIGIDO 2026-09-04

Medido ao vivo no slot `dt-wdo_grid_reload_maker-wdo@-live` (WDO@, R$375
reais), dois casos no mesmo pregão, reconstruídos pelo histórico da
corretora (autoritativo, MT5):

1. **Ciclo inteiro dentro de um poll.** 14:18:23 ordem armada; 14:18:31
   preenchida; 14:18:32 fechada pelo alvo ATÔMICO da própria corretora — 1
   segundo entre fill e fechamento, contra um poll de 5s do supervisor. A
   leitura de posição nunca mostrou nada aberto: no poll seguinte já
   estava zerada de novo. A detecção por CRESCIMENTO de posição (0 → N →
   0 entre duas leituras) nunca via nada crescer, então o robô ficou
   vigiando um ticket que a corretora já tinha resolvido — 6+ minutos
   depois ainda achava que tinha ordem pendente, e não arma nova enquanto
   acredita nisso.
2. **Fechamento "recusado" que na verdade executou.** Uma ordem de
   fechamento voltou com `retcode=DONE` mas sem `price`/`deal`
   (corretamente tratado como "não confirmo fill", gap de 2026-08-28) e o
   robô tentou de novo na barra seguinte. No meio-tempo, a tentativa
   ANTERIOR tinha executado de verdade, a 5.151,50 (−R$5,00). Como a
   leitura de posição já mostrava zero, o código caiu no ramo "a
   corretora já não tem nada" e usou o ALVO TEÓRICO (5.152,50) como preço
   de saída — registrando **+R$4,50 no lugar de −R$5,00**, erro de R$9,50
   num único trade, na direção que MENOS chamaria atenção (o painel fica
   bonito em vez de feio).

Os dois têm a mesma causa raiz: o código só perguntava "o que eu tenho
AGORA" (posição/ordens correntes), nunca "o que já ACONTECEU" — e um
evento que nasce e morre inteiro dentro do intervalo entre duas perguntas
é invisível para quem só faz a primeira.

> **Regra:** quando uma ordem que a máquina vigia deixa de existir no
> book, "não está mais lá" tem TRÊS causas possíveis (preencheu e ainda
> está aberta; preencheu E já fechou; morreu sem preencher) — e só o
> HISTÓRICO da corretora (ordem + deals, não a foto do momento) distingue
> as três. Nunca aproximar o preço de um fechamento por um nível teórico
> (stop/alvo) nem pelo último preço negociado: só um deal CONFIRMADO no
> histórico vale como preço real. Sem esse deal, a resposta certa é
> "ainda não sei" — mantém a vigilância e tenta de novo, nunca inventa um
> resultado (mesma família do item 1.6, aplicada ao RESULTADO, não só ao
> estado).
> **Pergunte à plataforma nova:** existe uma consulta de HISTÓRICO (não
> só o estado corrente) que devolve o desfecho definitivo de uma ordem —
> e os deals (preço, quantidade, lucro) de uma posição já fechada,
> buscável por um identificador estável? Sem ela, todo desfecho
> comprimido entre dois polls é invisível, e todo fechamento "recusado"
> que na verdade executou vira número inventado no diário.

**Correção aplicada:** `MT5Broker` ganhou dois métodos de consulta
tri-estado (nunca decidem, só traduzem) — `order_history_state` (o que
aconteceu com um ticket que saiu do book: ainda pendente, preenchida,
cancelada/recusada/expirada, com o `position_id` para o passo seguinte) e
`deals_for_position` (os deals reais — entrada e saída — de uma posição,
pelo `position_id`). `MT5IntradayExecution.resolve_orphaned_entry` usa o
primeiro caso para reconciliar uma entrada cujo ciclo de vida terminou sem
a máquina perceber: sem preenchimento vira "morta" (libera a vigilância,
nenhum trade inventado); preenchida e fechada por inteiro vira os dois
eventos (abertura + fechamento) com os números REAIS dos deals; preenchida
e ainda aberta é deixada para o caminho normal (crescimento de posição)
resolver — nunca antecipado. `exit_market`, quando descobre que a posição
já não existe na corretora, agora consulta `deals_for_position` pelo
ticket da entrada em vez de aproximar por stop/alvo/último preço — sem
deal confirmado, levanta e tenta de novo, com a posição continuando
aberta na máquina.

### 1.18 O freio de segurança tem escala de tempo embutida — calibrado pra barra, dispara no primeiro minuto de tick

Medido rodando a WDO F1 com tick real em pregões inteiros (09:00–18:29
BRT). `src/live/intraday_runtime.py` tem `MAX_ENVIOS_POR_MINUTO = 30`
(linha 227), janela rolante de 60s, verificado em
`_check_cadencia_de_ordens` (linha 1979) — o próprio comentário do código
diz que o número foi calibrado supondo "1 entrada por barra fechada (1/min
em M1)". O WDO F1 roda com `feed_kind="tick"`: "a cada barra" virou "a
cada NEGÓCIO", ~130 mil por pregão. 2026-03-09: 75.933 envios no pregão e
**3.446 na pior janela de 60s** — 115x o teto. Em 5 de 5 pregões medidos, o
freio trava — sempre no primeiro minuto de negociação (09:01 BRT).

Dois agravantes que fazem isso pior que uma simples recusa:

1. Estourar o teto NÃO recusa a ordem — seta `disaster_halt = True`, loga
   erro, chama `machine.discard_resting_limit()` e o robô fica MUDO o
   resto do pregão (só reseta no pregão seguinte). O cancelamento da ordem
   substituída acontece na linha 3073, ANTES da checagem — travar numa
   substituição deixa o robô sem ordem E travado ao mesmo tempo.
2. O modo sombra não avisa: em shadow, `executor is None` e
   `_on_limit_placed` retorna na linha 3067, antes da checagem de
   cadência. O slot sombra do WDO rodava desde 04/09 e daria zero aviso
   prévio do que ia acontecer em modo real.

> **Regra:** um freio de segurança tem uma escala de tempo embutida na
> calibração. Quando o robô muda de escala (barra fechada → negócio), o
> freio não muda junto e passa de proteção a mecanismo de morte. Todo
> limite numérico de segurança precisa dizer, no próprio código, contra
> QUAL cadência de decisão ele foi calibrado — e quem trocar a cadência do
> robô tem de re-medir todos eles. Corolário: um caminho de proteção que só
> existe no modo real (e retorna cedo no modo sombra) não é testado pelo
> modo sombra; a sombra não é ensaio geral de nada que ela pula.
> **Pergunte à plataforma nova:** que limites de taxa/cadência a
> plataforma impõe, e o meu robô tem algum freio interno calibrado para
> uma frequência de decisão diferente da que ele vai rodar? Ao estourar, o
> comportamento é recusar a ação ou parar o robô — e esse caminho é
> exercitado pelo modo sombra, ou só pelo real?

Mitigado como efeito colateral, não corrigido na origem: a correção do
item 4.14 (reancoragem com espera mínima) baixou a cadência de envios da
WDO F1 o bastante para nunca mais tocar este teto nos 126 pregões testados
(pior minuto medido: 26, contra o teto de 30) — mas isso é consequência de
outra correção. O freio em si continua sem declarar no código contra qual
cadência foi calibrado, e o caminho de shadow continua sem exercitá-lo.

**Atualização (2026-09-08, commit `da6f89c`):** o teto único
`MAX_ENVIOS_POR_MINUTO = 30` foi aposentado. Virou dois níveis —
`COTA_ENVIOS_POR_MINUTO = 120` (recusa só a ordem excedente, robô segue
vivo) e `MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO = 600` (o disjuntor que ainda
liga `disaster_halt`, agora contando TENTATIVA, não envio). Ver item 1.22.

### 1.19 O freio de ruína não pode confiar num número que a própria fonte já disse não sincronizar — travou o pregão com o caixa do painel positivo — CORRIGIDO 2026-09-08

Medido ao vivo em 2026-09-08, 10:06:34 BRT: robô PMAM3 (day trade, slot
real), segunda barra do pregão, ZERO ordens enviadas.
`IntradayLiveRuntime._check_freio_duro` — escrito depois do incidente da
Parte 0, especificamente para impedir ruína — disparou:

> `ERROR daytrade: FREIO DURO em PMAM3: equity R$ -3.60 / margem livre R$ -3.60 -- conta em risco de ruina. Parando de abrir ordem nova e tentando zerar o que estiver aberto. Nao volta sozinho -- precisa de intervencao (ver incidente 2026-08-28).`

O número veio de `MetaTrader5.account_info()` (equity/margin_free). Às
09:19:36 do MESMO dia o dono tinha digitado o caixa no painel: `caixa
definido manualmente: 0.00 → 30.00`. O robô travou o pregão inteiro por
causa de −R$3,60 reportados pelo terminal, numa conta cujo ledger
declarado tinha R$30,00 — e o freio, uma vez disparado, é persistido na
sessão e não volta sozinho (só reseta no pregão seguinte). Custo: 100% do
pregão perdido, robô intacto.

O agravante é que isso já era sabido e estava escrito. O `CLAUDE.md` do
projeto já dizia, textualmente, que o saldo do MT5 (Rico) "não é confiável
como fonte de capital" e que `equity`/`balance`/`margin_free` baixos não
são "sinal de conta zerada ou motivo para o robô não entrar" — achado
anterior a este incidente. O freio de ruína e o portão de envio por margem
foram escritos DEPOIS dessa descoberta e mesmo assim leram esses campos,
porque eram o único lugar do sistema que enxergava a conta AGREGADA (todos
os slots, mesmo login MT5) — e essa qualidade real fez esquecer que a base
do número era podre.

> **Regra:** um número que a própria fonte declara não confiável não pode
> ser GATILHO de nada — nem de freio, nem de recusa de ordem, nem de
> dimensionamento. Ele só serve para DIAGNÓSTICO (virar linha no diário
> dizendo que está sendo ignorado). Ao herdar um estado de conta de uma
> plataforma, separe os campos em dois grupos ANTES de escrever qualquer
> regra em cima deles: os que DERIVAM DO SALDO (equity, balance, margem
> livre — herdam qualquer dessincronização com a corretora) e os que saem
> das POSIÇÕES REAIS (margem comprometida, posições abertas, permissões de
> negociação — não passam pelo saldo). Só o segundo grupo pode decidir.
> "Quanto eu tenho" vem do ledger declarado pelo dono; "quanto já está
> comprometido" vem da corretora. Corolário que vale para qualquer freio:
> um freio de segurança que se alimenta de um número não confiável não é
> conservador — é uma forma NOVA de falha, e uma que falha em silêncio para
> o lado de não operar (o mesmo modo de falha do piso de capital calando o
> robô, item 3.10).
> **Pergunte à plataforma nova:** quais campos do estado de conta desta
> plataforma derivam do SALDO (e portanto herdam qualquer dessincronização
> com a corretora) e quais saem das posições/margem reais? A corretora
> garante que o saldo exibido na plataforma é o saldo de verdade?

**Correção aplicada:** `src/live/intraday_runtime.py` — o gatilho de
ruína do freio duro passou a ser `_caixa_operacional_brl()` (o
`initial_capital` digitado no painel + realizado + posição marcada a
mercado — a MESMA conta que já dimensiona lote), e o portão de envio
`_check_margem_da_conta` passou a somar a margem COMPROMETIDA da conta
(`account_info().margin`, que não passa pelo saldo) com o que a ordem
exige, comparando o total contra o caixa do painel, em vez de olhar
`margin_free`. O saldo do MT5 virou uma linha `warn` de diário, uma por
pregão: "IGNORANDO o número do terminal". Suíte inteira verde (1.721
testes).

### 1.20 Freio de cadência que cobre a reprecificação mas não o rearme pós-preenchimento não é freio — 125 ordens para 22 trades

Auditoria do pregão real de 2026-09-08 (WDO F1, slot
`dt-wdo_grid_reload_maker-wdo@-live`, tick, caixa R$375): **125 ordens-limite
de entrada enviadas para produzir 22 idas-e-voltas**. Dos 124 intervalos entre
envios consecutivos, **82 ficaram abaixo de 0,5 segundo** e só 21 respeitaram
os ~10s que o freio promete. O pior trecho: **45 ordens de venda enviadas e
canceladas em 13 segundos**, entre 09:00:09 e 09:00:22, perseguindo o preço de
5.117,5 até 5.107,0.

O freio funciona — e é essa a parte instrutiva. Na janela calma do MESMO
pregão (07:41–07:51) os intervalos medidos foram 10,198s / 10,471s / 10,203s /
10,265s, colados no default `reancora_min_segundos = 10,0`; e é exatamente
essa janela que gerou os 8 alvos positivos do dia (item 4.8). O freio cobre
dois caminhos de envio — substituição por deriva de preço e rearme pós-recusa
(itens 4.14 e 3.16) — e deixa de fora o terceiro, o rearme depois de um
preenchimento, "porque é a mecânica normal de reload". A docstring do próprio
módulo já dizia, por escrito, que "a rajada de rearme pós-fill (que este freio
não toca) é o que sobra no pico". A lacuna estava nomeada, medida e
documentada. E aberta.

> **Regra:** um freio de cadência protege pelo pior caminho, não pelo caminho
> médio. Se existem N fontes de envio de ordem (reprecificar por deriva,
> rearmar depois de recusa, rearmar depois de preenchimento), TODAS passam
> pelo mesmo teto — senão o robô opera no regime rápido justamente depois de
> cada preenchimento, que é quando ele mais manda ordem. Uma isenção
> justificada por "esse caminho é a mecânica normal" é a que vai dominar o
> pico, porque é a mais frequente. Corolário de medição: conferir um freio não
> é ler o parâmetro nem contar quantas vezes ele barrou — é medir a
> DISTRIBUIÇÃO dos intervalos reais entre envios num pregão inteiro. Aqui o
> parâmetro estava certo, a janela calma o respeitava tick a tick, e ainda
> assim 66% dos intervalos do dia ficaram abaixo de meio segundo.
> **Pergunte à plataforma nova:** existe teto de cadência de envio/cancelamento
> de ordens imposto pela plataforma, e o freio do meu robô conta o rearme
> pós-preenchimento junto com a reprecificação, ou só a segunda? (ver 1.18)

### 1.21 Dois preenchimentos com 83 ms de diferença viraram UM contrato no diário — divergência de contagem é evento de ruína, não de contabilidade

Mesmo pregão de 2026-09-08, 09:00:52: duas ordens de venda limitadas
preencheram com **83 milissegundos de diferença** na MESMA posição — **2
contratos vendidos numa conta de R$375**, dimensionada para 1. Foram fechadas
separadamente, a −R$5,00 e −R$15,00. O diário registrou **um** contrato e
−R$15,50. No fim do dia o bruto da corretora era **−R$110,00** contra
**−R$105,00** do diário: os R$5,00 de diferença são o contrato que o robô
nunca soube que tinha. No total do pregão, **23 contratos negociados contra 22
registrados**.

É o mecanismo do incidente da Parte 0 em miniatura — exposição AGREGADA que
nenhuma checagem por ordem enxerga —, e vale reparar no que NÃO o impediu: o
teto agregado existe desde então (item 3.2), mas ele decide sobre o que a
máquina acredita ter, e aqui os dois preenchimentos couberam inteiros dentro
do mesmo intervalo entre duas leituras (o cego do item 1.17). O que salvou o
dia foi o tamanho da perda, não o desenho.

> **Regra:** o número de contratos que a corretora tem é a VERDADE; o número
> que o diário tem é uma crença. Divergência entre os dois é evento de RUÍNA
> em potencial — a exposição real pode ser o dobro da acreditada, e todo teto
> de risco a jusante está calculado sobre o número errado —, não uma diferença
> de contabilidade para conciliar depois do pregão. A conciliação é por
> CONTAGEM DE CONTRATOS e por SOMA DOS DEALS do histórico, feita DURANTE o
> pregão, e a divergência trava a abertura de ordem nova (item 1.7) em vez de
> virar linha de log. Corolário: quando duas ordens do mesmo lado podem
> preencher dentro do mesmo intervalo de leitura, esse intervalo não é uma
> escolha de desempenho — é o tamanho da exposição que você aceitou não
> enxergar. A pergunta 32 da Parte 8 é a que dá a ferramenta (consulta de
> histórico, não foto do momento); esta regra é o uso obrigatório dela.

### 1.22 Teto de vazão de execução precisa de DOIS níveis — disjuntor sozinho mata pregão legítimo

Medido em `src/live/intraday_runtime.py` (commit `da6f89c`, 2026-09-08).
`MAX_ENVIOS_POR_MINUTO = 30` (item 1.18) era um DISJUNTOR único: ao ser
atingido ligava `disaster_halt` e o robô ficava mudo o pregão inteiro. Dois
fatos medidos no mesmo dia mostraram que isso mata pregão legítimo, não só
laço:

1. O 30 foi calibrado no relógio ERRADO. Até o commit `75f6b48` o contador
   recebia `evento.ts` (tempo de TICK); a docstring dizia "pior minuto 26 de
   30" — tempo de tick, que não descreve nada no relógio de PAREDE, o único
   que a corretora enxerga.
2. A cadência LEGÍTIMA já passava de 30. Medição IS/OOS do mesmo dia
   (commit `e8f88fe`, config de produção T2/S16 com histerese): pior minuto
   do OOS = **42 envios**, com e sem a histerese — saturação de
   `max_trades_per_side` (rearme pós-fill), não laço.

Distribuição medida do **pior minuto por pregão**
(`scripts/daytrade/wdof1_cadencia_envios_distribuicao_2026_09_08.py`, motor
tick, IS/OOS congelado, config de produção T2/S16 com histerese, base
`WDO_A_f1` regenerada em 07/09, capital real R$375):

| fonte | n | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| backtest IS (relógio de mercado) | 72 | 12 | 19 | 20 | 22 | 23 |
| backtest OOS (relógio de mercado) | 51 | 10 | 19 | 24 | 34 | 42 |
| ao vivo 08/09 (relógio de parede, slot SOMBRA WDO@, conta 476, pregão inteiro, 173 envios) | 1 | 3 | 12 | 15 | 18 | 19 |

**Nota de 2026-09-08, mais tarde (commit `4eb3e4a`):** as duas linhas de
backtest desta tabela vêm do motor que ainda fechava o alvo maker de graça
(item 4.8). No motor corrigido a MESMA config trava por capital em 71 de 72
pregões (item 6.18), e a distribuição de cadência ficaria censurada junto —
quem quase não opera não acumula rajada (a armadilha que o item 6.16 já
nomeia). Isto **não afrouxa** a decisão de dois níveis: a linha do pregão AO
VIVO (relógio de parede, 173 envios reais) não depende de motor nenhum, e a
cadência que o teto precisa suportar é a do robô operando, não a do robô
calado. É a tabela que fica datada, não o teto.

1 dos 123 pregões (0,8%) passaria do teto antigo de 30; NENHUM passa de 50.
(O slot REAL do mesmo dia, conta 474, deu máximo 64 — mas naquele pregão o
feed tinha ficado cego 45 minutos e a histerese ainda não existia, as duas
causas já corrigidas nos itens 5.17 e 4.19 — então esse número mede um
pregão patológico já resolvido, não a cadência normal do robô.) Regime
PATOLÓGICO conhecido do mesmo robô, antes do freio `reancora_min_segundos`
(item 4.14): **1.020 a 3.446 envios no pior minuto** (item 1.18).

> **Regra:** um teto de vazão de execução tem DOIS níveis, nunca um. O
> **teto operacional** recusa a AÇÃO individual e o robô segue vivo; o
> **teto de patologia**, uma ordem de grandeza acima, é que derruba o robô.
> Um teto único é sempre errado nos dois sentidos: baixo demais mata pregão
> legítimo, alto demais deixa laço passar batido.
>
> O teto de patologia tem de contar TENTATIVAS, não ações executadas — se
> contar só o que passou, o teto operacional o prende abaixo dele por
> construção e o disjuntor nunca dispara. Sem isso, um laço infinito vira
> "robô rate-limited para sempre, parecendo saudável".
>
> Cota barra ABRIR, nunca barra SAIR: cancelamento, fechamento e ordem de
> proteção jamais podem ser recusados por cota de vazão — uma cota que
> atrase um fechamento inverte um freio de execução em risco de posição
> aberta, exatamente o que o incidente da Parte 0 (2026-08-28) custou.
>
> Todo limite de execução tem de ser calibrado no MESMO relógio que a
> contraparte sofre. A corretora vive em relógio de parede; medir a proteção
> no relógio do dado é não ter proteção nenhuma (o furo corrigido em
> `75f6b48`).
>
> Quando um envio é recusado, a máquina tem de ESQUECER a ordem
> (`discard_resting_limit`), senão fica vigiando um fill impossível — e
> recusa silenciosa é o modo de falha do item 6.15: toda recusa por cota
> escreve linha `warn` no diário, com contagem, uma por LOTE (uma por ordem
> reproduziria a rajada dentro do próprio diário).
>
> **Pergunte à plataforma nova:** qual é o limite REAL de requisições por
> unidade de tempo que esta corretora/plataforma impõe (envio, cancelamento
> e alteração contam igual?), e o que ela devolve ao estourar — recusa da
> requisição, desconexão, ou bloqueio da conta? Hoje os dois tetos deste
> projeto são calibrados pela cadência do ROBÔ, não pelo limite da
> corretora, porque esse limite nunca foi documentado pela Rico/Clear.

**Números novos em produção:** `COTA_ENVIOS_POR_MINUTO = 120` (~2,9x o
maior pior-minuto legítimo, ~3,5x o p99 do OOS, ~6x o pior minuto de parede
de um pregão inteiro ao vivo) e `MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO = 600`
(5x a cota, ainda abaixo do piso do regime patológico medido).

**Risco residual, registrado e aceito sem mudança:** um laço LENTO (um arme
por passo do supervisor, ~12/min) não dispara nem a cota nem o disjuntor —
não é regressão (o teto de 30 também não pegava esse caso) e não é risco de
corretora nessa taxa, mas fica anotado para quem for portar o freio.

### 1.23 Proteção já registrada na corretora MAIS ordem a mercado por cima é saída DUPLA — e em conta netting a segunda não zera, INVERTE — CORRIGIDO 2026-09-08

**Honestidade primeiro: isto é lacuna achada por auditoria, não incidente
reconstruído. Não custou nenhum dinheiro que a gente tenha conseguido
identificar.** O que dá para afirmar com número é a exposição, mais abaixo.

Em `backtest/intraday/machine.py::_close_position`, a condição que decide
"fechar pela proteção JÁ REGISTRADA na corretora em vez de mandar ordem a
mercado" era `reason in (TARGET, STOP) and position.exit_split_unit is None`.
A cláusula `exit_split_unit is None` existe **por causa do ALVO**:
`live.intraday_runtime._alvo_atomico` recusa de propósito amarrar TP numa
posição fatiada (dois fechamentos do tamanho total numa conta NETTING
inverteriam o lado), então para o alvo fatiado realmente NÃO há nível
registrado na corretora para esperar. **O STOP nunca teve esse problema** —
`_on_limit_placed` manda `stop=order.initial_stop` em TODA ordem, fatiada ou
não, e a docstring do próprio `_alvo_atomico` já dizia isso por escrito: *"o
STOP não tem esse problema e vai sempre: fatia de saída só existe no alvo"*.
A guarda era larga demais: cobria os dois motivos quando a justificativa dela
valia só para um.

Efeito: posição fatiada COM stop registrado na corretora, a barra toca o
stop, e o motor mandava ordem **a mercado** por cima. Dois danos, de
gravidades muito diferentes:

1. **Pagava o spread em todo stop de posição fatiada** — dinheiro,
   mensurável, pequeno, e exatamente o que o dono tinha mandado parar de
   pagar.
2. **Risco de saída DUPLA** — a ordem a mercado e o `sl` da corretora podem
   executar as **duas**. Em conta NETTING o excedente não vira zero: vira
   **posição aberta no lado contrário**, sem stop e sem alvo. É o mesmo
   desfecho do incidente da Parte 0 (mecanismo do item 1.4), por um caminho
   diferente — e este é o dano que justifica o item, não o spread.

**A exposição, com o número que existe.** Quem roda `dividir_entrada=True`
por padrão é a `Gremah` (ação B3), que teve slot REAL ligado; o WDO F1 nunca
esteve exposto, porque não fatia a saída. O log do slot
`dt-gremah-pmam3-live` cobre **5 pregões** (2026-08-28, 08-31, 09-02, 09-04 e
09-08) e em **todos** os passos registra `entradas=0 saidas=0` — o robô nunca
chegou a abrir posição em modo real nessa janela, então o caminho nunca foi
exercitado com dinheiro. O registro anterior mais próximo (PMAM3, 2026-08-25)
são 12 ordens reais com **0 preenchimentos** — de novo, sem posição aberta. O
`db/live.sqlite` atual só guarda 2026-09-08, então não dá para varrer mais
para trás: **a exposição era de configuração, não de evento observado.**

**Correção aplicada (commit `4eb3e4a`, com teste):** `fecha_pela_protecao`
passou a ser `(exit_split_unit is None or reason == STOP)`. A fatia-limite
pendente já é cancelada antes desse ponto (`_resolve_live_split_exit`, ramo
`stop_hit`), então a sequência fica correta: cancela a limite → confirma pelo
`sl` que a corretora já tem registrado.

> **Regra:** enquanto a corretora tem uma proteção REGISTRADA para uma
> posição, o robô nunca manda uma segunda ordem para fechar a mesma
> exposição — não importa se a posição foi montada inteira ou em fatias, e
> não importa que a segunda ordem "provavelmente chegue primeiro". As duas
> podem executar, e em conta de netting o excedente não vira zero: vira
> posição invertida (item 1.4). Fechar é sempre UM caminho por posição, e
> quando já existe nível registrado na corretora, o caminho é ESPERAR esse
> nível — cancelando antes qualquer ordem própria que dispute o mesmo
> fechamento.
> **Corolário sobre a FORMA do bug, que é o que generaliza:** quando uma
> condição de guarda junta dois casos numa cláusula só (aqui, alvo e stop),
> confira se a JUSTIFICATIVA dela vale para os dois. Aqui a razão estava
> escrita, correta e explicitamente restrita ao alvo, na docstring da função
> vizinha — e mesmo assim a guarda cobria os dois. Guarda larga demais não
> falha ruidosamente: ela só age onde não devia, e só num caminho raro.
> **Pergunte à plataforma nova:** como ela resolve uma ordem de fechamento
> que chega enquanto já existe stop/alvo REGISTRADO para a MESMA posição —
> recusa, cancela a proteção sozinha, ou executa as duas? E se as duas
> executarem, o excedente vira zero ou vira lado contrário?

### 1.24 "A corretora não confirmou" tratado como "a corretora não executou" — o robô seguiu se achando comprado depois de já ter sido zerado, e a ordem-limite órfã virou o segundo contrato

Primeiro dia do `wdo_grid_reload_maker` ao vivo com `fatiar_saida_alvo=True` —
a saída de lucro deixou de ser `tp` nativo e virou ordem-limite real parada no
livro (a troca de MECANISMO do item 6.19). Conta NETTING, capital real R$375,
1 contrato, WDO@. Sequência reconstruída do histórico de DEALS do terminal,
todos com o magic do robô (862399285):

| hora | evento | efeito na CORRETORA | o que o ROBÔ achava |
|---|---|---|---|
| 06:44:51 | BUY IN 1 @ 5113,0 (posição 5938815446) | long 1 | long 1 — correto |
| 06:45:44 | arma limite de saída @ 5114,0 (ticket 5938817623) | long 1 + limite viva | idem |
| 06:45:46 | manda fechamento A MERCADO (prazo `exit_ttl_bars=8` estourado) | — | — |
| **06:45:48** | **corretora EXECUTA o fechamento @ 5113,5** | **zerado, +R$5,00** | **long 1** ← divergiu |
| 06:46:11 | "reverte" para short: vende 1 @ 5113,5 | **abre short 1** | acha que está zerando |
| **06:46:14** | **a limite órfã de 5114,0 preenche** | **short 2** | short 1 |
| 06:53:16 | stop @ 5121,5 | fecha os 2 | — |

A geometria estava certa (alvo 2 ticks, stop 16 ticks) e o sinal nunca errou.
O que quebrou foi uma linha de resposta da API: o `order_send` do fechamento
voltou com `retcode=TRADE_RETCODE_DONE` — **sucesso** — mas com `price=0.0` e
`deal=0`. A proteção adicionada em 2026-08-28 (`MT5Broker._send`, o bloco "Gap
fechado 2026-08-28") existe justamente para não inventar preço de execução a
partir de resposta sem os campos preenchidos, e classificou aquilo como
**REJECTED**. Rejeitado, para o robô, quer dizer "não aconteceu" — então ele
seguiu se achando comprado depois de já ter sido zerado pela corretora.

**A assinatura visível do erro**, e ela é reproduzível em qualquer conta
netting: o `price_open` da posição virou **5113,75** — a média de 5113,5 e
5114,0. Um preço FORA da grade de 0,5 do WDO, impossível para um preenchimento
único. Preço de abertura que não existe na grade do instrumento é prova de que
duas pernas viraram uma posição só.

**O número.** A posição de 2 contratos morreu no stop: **−R$80,00** (−2,50 na
fatia já fechada + −77,50 no stop). Resultado real do pregão: **−R$65,00**
(+5,00 − 80,00 + 15,00 − 5,00).

**Dano colateral, e este é o pior.** O diário do robô registrou o primeiro
trade como **"+R$9,50 @ 5114,00"** — o alvo cheio, deslize zero. O real foi
**+R$5,00 @ 5113,50**, metade, e saiu **A MERCADO**. O robô journaliza o preço
que ELE acha que conseguiu, não o que a corretora executou, então o diário
afirmou exatamente o contrário do que aconteceu — no evento que estava sendo
vigiado, com a saída maker sob teste justamente para medir deslize (itens 4.8,
4.15 e 6.19). Uma medição que o próprio instrumento inverte não é medição
ruim: é medição ao contrário.

> **Regra 1 — "não confirmou" e "não executou" são estados DIFERENTES, e
> tratar o primeiro como o segundo é o que abre exposição dobrada.** Uma
> resposta de SUCESSO com os campos de confirmação vazios significa RESPOSTA
> INCOMPLETA, nunca ausência de execução. O caminho correto é ir perguntar à
> corretora qual é a posição e quais são os deals reais — reconciliar — antes
> de concluir qualquer coisa. Nenhuma decisão de exposição sai do conteúdo de
> uma única resposta lida sozinha. É o item 1.6 ("não sei" nunca vira "não
> há") aplicado ao ENVIO, e não à consulta: lá o perigo era inventar uma saída
> que não houve; aqui é negar uma saída que houve.
> **Regra 2 — toda ordem que o robô perde de vista continua VIVA no livro.**
> Em conta NETTING, uma ordem-limite de SAÍDA órfã não é inofensiva: quando a
> posição que ela deveria fechar já não existe, ela vira ENTRADA nova, no lado
> contrário, sem stop e sem alvo. Antes de mandar qualquer ordem nova, cancele
> o que ficou pendurado e reconcilie contra a lista de ordens vivas da
> corretora (item 1.8, agora com o caso concreto que faltava).
> **Regra 3 — proteção defensiva escrita para evitar um estado ruim pode
> CRIAR outro, e o custo dela precisa ser medido junto.** A regra de
> 2026-08-28 tinha objetivo correto (não inventar preço de execução), mas
> ninguém mediu o que ela deixa para trás: uma visão de posição divergente da
> corretora, que é o estado mais perigoso que existe para um robô que decide
> sozinho. Uma proteção que ALTERA a visão de estado tem de vir acompanhada da
> reconciliação; sem isso ela não remove o modo de falha, só troca de modo de
> falha — e trocou "número errado no diário" por "2 contratos numa conta de 1".
> **O padrão, pelo terceiro ângulo.** Junte este item ao 1.23 e ao incidente
> da Parte 0: é sempre ordem que o robô não sabe que tem, em conta NETTING,
> somando onde ele achava que ia zerar. Em 08-28 foram duas entradas dentro do
> mesmo passo do laço; no 1.23 era a proteção registrada mais uma ordem própria
> pelo mesmo fechamento; aqui é o fechamento executado que o robô negou mais a
> limite de saída que ele esqueceu no livro. Três causas, um desfecho.
> **Pergunte à plataforma nova:** perguntas 68, 69 e 70 da Parte 8.

### 1.25 A conferência de exposição era cega ao pior estado: comparava só a MAGNITUDE da posição, e um portão de "ordem em trânsito" a desligava por inteiro — 2 contratos NUS numa conta de R$375 — CORRIGIDO 2026-09-09

Segundo dia do `wdo_grid_reload_maker` ao vivo com `fatiar_saida_alvo=True`,
slot `dt-wdo_grid_reload_maker-wdo@-live`, conta real Rico (11724331),
NETTING, capital R$375, WDO@ (WDOV26). É a MESMA família do item 1.24, um dia
depois, por **três mecanismos novos**. Tudo abaixo foi reconstruído do
histórico de DEALS+ORDENS do terminal (magic 862399285) cruzado com os
`live_events` do `db/live.sqlite`. Horas do terminal (= BRT−3); entre
parênteses, a hora que aparece no diário.

| hora | evento | efeito na CORRETORA | o que o ROBÔ achava |
|---|---|---|---|
| 07:53:07 | BUY_LIMIT 5939226225 preenche @5122,0 | long 1 (pos 5939226225) | long 1 — correto |
| 07:53:28 | SELL_LIMIT 5939228267 @5123,5 preenche | zerado, +R$15,00 bruto | idem — correto |
| 07:53:30 | SELL_LIMIT 5939228272 @5124,0 (sl 5132,0) preenche | short 1 | short 1 — correto |
| **07:53:33** | manda fechamento A MERCADO; `order_send` volta `DONE` com `price=0.0, deal=0` | **BUY 5939228664, deal 475959377, @5124,50, −R$5,00 → ZERADO** | **short 1** ← divergiu |
| 07:54:05 | arma a limite de saída da SHORT #02 (BUY_LIMIT **5939230468** @5123,0) **e** a entrada LONG #03 (BUY_LIMIT **5939230472** @5122,5) | 2 limites vivas, conta zerada | short 1 + 1 entrada armada |
| **07:54:17** | **5939230468 preenche @5123,0** | **ABRE long 1** — não fecha nada | conta o MESMO fill DUAS vezes: "TARGET SHORT #02" e "LONG #03" |
| 07:54:25 | SELL_LIMIT 5939231337 @5123,5 fecha o long; SELL_LIMIT 5939231615 @5123,5 (sl 5131,5) abre short | short 1 | short 1 — concordam por um instante |
| **07:55:07** | **5939230472**, a entrada órfã de 07:54:05 que ninguém cancelou, preenche @5122,5 e **fecha o short**; no MESMO segundo a fatia de saída da SHORT #04 (BUY_LIMIT 5939234311 @5122,5) preenche num book já zerado | **long 1** | short 1 |
| 07:55:18 | re-arma a fatia de saída (BUY_LIMIT 5939236131 @5122,5), que preenche na hora | **long 2, SL=0, TP=0** | short 1 |
| 07:55:09 em diante | a cada passo: `NAO CONSEGUI proteger a posicao de WDO@ ... MT5 recusou SL/TP (retcode=10016): Invalid stops` | `WDOV26 BUY vol=2.0 open=5122,5 SL=0.0 TP=0.0`, bid 5124,0 / ask 5124,5 | — |
| 07:58:10 | **o DONO zera na mão**: SELL 2,0 @5122,5, magic=0 | zerado | — |

**~3 minutos, 2 contratos, R$0 de proteção registrada na corretora, numa
conta cujo teto por caixa é 1 contrato** (R$375 / margem R$150). Quem
encerrou foi o dono, não o robô — de novo.

**(A) O SL recusado era do LADO ERRADO, e `trade_stops_level = 0` desligou a
única checagem que existia.** A máquina se achava SHORT #04 e mandava
`current_stop = 5131,50` — o stop de uma posição VENDIDA — para uma posição
COMPRADA com bid em 5124,00. SL acima do mercado num long é ordem a mercado
disfarçada, e o servidor recusa. Não era proximidade: o WDOV26 na Rico
reporta `trade_stops_level = 0`, isto é "sem distância mínima", e o código
lia isso como `distancia_min = 0,0` e **pulava o afastamento inteiro**. Pior:
`TRADE_ACTION_SLTP` é ATÔMICO — a perna inválida derrubava a válida junto, e
a posição ficava sem NADA. Não foi "ficou sem alvo": foi ficar sem stop, que
é o modo de morte da Parte 0.

**(B) A conferência de exposição era cega ao pior estado, por dois motivos
independentes.** `IntradayLiveRuntime._check_posicao_desconhecida` existe
justamente para pegar o que o item 1.7 descreve, e não pegou:

1. **Comparava só a MAGNITUDE.** `_Position.quantity` é magnitude — o sinal
   mora em `.side`. Máquina SHORT 1 contra corretora LONG 1 dava `1 == 1` e
   passava como "tudo certo". A **inversão PERFEITA**, que é exatamente o
   desfecho do item 1.4, era o único caso que a checagem não conseguia ver.
2. **Saía na PRIMEIRA linha quando `_tem_ordem_em_transito()` era `True`** — e
   com uma fatia de saída pendurada isso é `True` o tempo todo. Durante os ~3
   minutos do incidente ela **nunca comparou nada**.

**(C) O diário gravou a crença, não o MT5, porque "a posição encolheu" era
tratado como "minha fatia preencheu".** `MT5IntradayExecution.exit_fill`
inferia o preenchimento do ENCOLHIMENTO da posição e carimbava o preço do
LIMITE pedido, sem consultar deal nenhum. O número medido: gravou **"TARGET
SHORT #02 @5123,00 — R$ +9,50"** para uma saída que a corretora executou a
**5124,50 por −R$5,00** — **R$14,50 de erro num único trade, com o SINAL
trocado**, no evento que estava sob observação. O balanço do diário na janela
10:53–10:58 é **+R$14,50 +R$9,50 +R$4,50 = +R$28,50**; os deals reais da
mesma janela somam **+R$25,00 bruto**, e a distribuição por trade não bate em
nada: real foi **+15,00 / −5,00 / +5,00 / +10,00** — este último, o fill da
órfã, nunca foi journalizado. Terceira vez seguida (1.17, 1.24, aqui) que o
diário afirma o contrário do extrato, sempre para o lado bonito.

**Correções aplicadas (cada uma com teste que falha no código antigo; suíte
1820 passed / 1 skipped):**

1. `MT5Broker._niveis_protecao`: **piso de 1 tick** na distância mínima,
   sempre — `trade_stops_level = 0` significa "sem distância mínima", nunca
   "aceita nível de qualquer lado".
2. `MT5Broker.set_protection`: quando o pedido com as DUAS pernas é recusado,
   **reenvia só com o stop** (`tp = tp_atual`). Ficar sem alvo custa um alvo;
   ficar sem stop foi o que zerou a conta em 2026-08-28.
3. `MT5Broker._desfecho_de_done_sem_fill`: pergunta ao histórico **4x ao longo
   de 1,75s** (`ESPERAS_CONFIRMACAO_S`) em vez de 1x no mesmo instante — a
   própria docstring já registrava que "no incidente o fill só apareceu 2
   segundos depois".
4. `IntradayLiveRuntime._check_posicao_desconhecida`: compara **LADO**, e a
   comparação de lado **não passa pelo portão de trânsito**. Ordem em trânsito
   explica quantidade diferente; nunca explica a corretora estar do lado
   contrário.
5. Mesma função: confere a quantidade da corretora contra o **teto por caixa**
   (`_cap_capital_atual`) — R$375 / R$150 = 1 contrato, a corretora tinha 2 —
   também **sem** portão, porque a máquina nunca MANDA além do teto, então
   excedente não pode estar "a caminho".
6. `_tenta_zerar_por_freio_duro`: com lado divergente, **não** tenta fechar a
   posição sozinho (fechar às cegas em NETTING sai do lado e do tamanho
   errados e INVERTE — item 1.4); cancela só as ordens vivas, que é
   inequivocamente seguro.
7. `MT5IntradayExecution.exit_fill`: a fatia só é dada como preenchida quando
   os DEALS do NOSSO ticket de saída confirmam, e o preço é o do deal.

> **Regra 1 — conferir posição contra a corretora é comparar LADO *e*
> tamanho.** Comparar só tamanho deixa passar a inversão perfeita, que é o
> pior estado que existe: exposição do dobro do tamanho aparente (a sua mais
> a dela), proteção calculada para o lado errado, e todo teto de risco a
> jusante rodando sobre o número errado. Uma checagem de divergência que não
> consegue ver o pior caso não é uma checagem fraca — é ausência de checagem
> no único caso que importa.
> **Regra 2 — um filtro de "isso pode ser atraso normal" tem de ser aplicado
> à grandeza que o atraso de fato explica.** Atraso explica QUANTIDADE.
> **Nunca explica LADO**, e nunca explica quantidade ACIMA do que a máquina é
> capaz de pedir. Colocar todas as comparações atrás do portão que só vale
> para uma delas desliga o mecanismo inteiro pelo caminho mais comum — aqui,
> uma fatia de saída pendurada, que é o estado NORMAL do robô. É o corolário
> do 1.23 pelo outro lado: **guarda larga demais não falha ruidosamente; ela
> só deixa de agir exatamente onde precisava.**
> **Regra 3 — "sem distância mínima" nunca quer dizer "de qualquer lado".**
> Todo nível de proteção tem um LADO obrigatório em relação ao mercado (stop
> de long abaixo, stop de short acima), e esse lado não depende de nenhum
> parâmetro da corretora. Parâmetro zerado é ausência de restrição
> ADICIONAL, jamais permissão para violar a restrição estrutural.
> **Regra 4 — pedido de proteção com duas pernas é atômico: se pode ser
> recusado por uma, tem de existir caminho de degradar para a perna que
> impede a RUÍNA.** Sem esse caminho, um alvo mal calculado apaga o stop e um
> erro barato vira o erro caro. A ordem de prioridade é fixa: stop primeiro,
> alvo se sobrar.
> **Regra 5 — encolher não é preencher.** Atribuir a uma ordem NOSSA qualquer
> redução da posição é inventar quem fechou e a que preço; em conta NETTING
> quem "fechou" pode ter sido alguém que também ABRIU o lado contrário — foi
> literalmente o caso, com o mesmo `broker_ref` 5939230468 gravado em duas
> linhas de `live_orders` (id 964, `saida day trade (target)`, e id 965,
> `entrada day trade`). Preenchimento de uma ordem só é confirmado pelos
> DEALS daquele ticket, e o preço é o do deal (item 1.17, agora aplicado à
> fatia de saída).
> **Regra 6 — consulta a histórico assíncrono precisa de PRAZO, não de uma
> pergunta.** Perguntar uma única vez no instante da resposta é não
> perguntar: o histórico do terminal chega depois. Um "não achei" sem prazo é
> o mesmo "não sei" virando "não há" do item 1.6, com o agravante de ser
> autoinfligido.
> **Pergunte à plataforma nova:** perguntas 71 a 75 da Parte 8.

### 1.26 Cinco robôs independentes no mesmo instrumento numa conta NETTING se bloqueiam: o backtest de cada um sozinho não descreve a conta — +R$14.079 isolados viraram +R$5.131 juntos

Medido em 2026-10-06 (medição de método; ainda não custou dinheiro real, mas
invalida uma suposição de operação). Cinco EAs do WIN — `WinGapBarra1`,
`WinCincoMedias`, `WinDeslocamentoMatinal`, `WinRetanguloEma34`, `Win_c1` —, cada
um com o seu `magic`, ligados juntos numa conta NETTING (uma posição líquida por
símbolo). Cada EA pula a entrada se já existe posição no símbolo, e vários fecham
com `PositionClose(_Symbol)`, que em netting fecha a posição de **TODOS**. Um
robô, portanto, é bloqueado pela posição de outro e, quando fecha, zera a do outro.

Replay de 2026 (R$1.000 por ano, custo R$2/op): cada robô sozinho somaria
**+R$14.079**; juntos, com o bloqueio, **+R$5.131**. **154 de 361 entradas
(42,7%) foram bloqueadas, e as bloqueadas somavam +R$9.006.** Em 2022-2025 o
bloqueio custou menos (somas de 16.944 contra 19.466 isolados), mas em 2025 foi
3.123 contra 5.208. O backtest de cada robô sozinho é verdadeiro e não descreve
a conta onde eles vão rodar juntos.

**Regras de convivência com 1 contrato — nenhuma resolveu.** Testadas em
2022-2025 (`scripts/daytrade/comparativo_win_2026/combinacoes/z9_netting/`, t0 a
t6, `resultado.md` de cada): preempção, mesmo lado mantém / lado oposto inverte,
consenso de 2 ou mais, conflito zera, prioridade fixa. **Nenhuma bateu o
bloqueio.** A única que preserva o resultado é um EA "maestro" com uma **posição
virtual (ficha) por robô**, enviando as ordens com o `magic` de cada robô: a
posição líquida é a soma das fichas (até 4 contratos simultâneos medidos), e o
resultado bate com a soma isolada em todos os anos.

**O que a revisão adversarial da especificação do maestro
(`mt5/WinMaestro_ESPECIFICACAO.md`) achou — riscos próprios de netting
multi-robô:**

1. **SL/TP da posição líquida não serve a nenhum robô** — vale para a SOMA.
2. **`PositionGet*` (preço, hora, comentário, magic) são da líquida**, não do
   robô: o preço de abertura é uma média, o magic é o do último que mexeu.
3. **O stop de um robô pode AUMENTAR a líquida** (um robô comprado fechando
   dentro de uma líquida vendida vira abertura para a corretora) — e pode ser
   recusado por margem exatamente quando era a saída (ecoa o 1.1).
4. **Ordens pendentes de robôs diferentes podem se cruzar** (autonegociação).
5. **Stop e alvo independentes, sem OCO no servidor, podem executar os dois**
   com o EA fora do ar — em netting o segundo inverte (a mesma mecânica do 1.23).
6. **`DEAL_ENTRY` e `DEAL_PROFIT` são da líquida**: o resultado "do robô" não
   sai direto do extrato.

> **A regra (portável).** Vários robôs no mesmo instrumento numa conta de
> posição líquida: **a posição de cada robô é contabilidade do SISTEMA, nunca da
> corretora.** Toda leitura, fechamento ou stop "por posição do símbolo" age
> sobre a SOMA. Ou **um único processo** mantém uma ficha por robô —
> reconstruível do histórico de negócios pelo identificador do robô — e envia as
> ordens com esse identificador; ou **cada robô tem conta própria**. Robôs
> independentes que se bloqueiam por "já há posição" **não descrevem nenhum
> backtest isolado**: medir cada um sozinho e somar é uma medição de uma conta
> que não existe.
> **Pergunte à plataforma nova:** perguntas 140 a 145 da Parte 8.

---

## Parte 2 — Estado, reinício e duplicidade

### 2.1 O que sobrevive ao reinício tem de ser decidido de propósito

Duas categorias, tratadas de forma oposta:

- **Decisão** (qual ordem armar, em que nível): NÃO se restaura. O robô redecide
  do zero com o dado real, senão herda uma decisão velha contra preços que já
  passaram.
- **Fato** (ticket enviado, posição aberta, P&L da sessão, freio acionado): tem
  de sobreviver, senão o processo novo opera achando que o dia começou agora.

O acumulado da sessão sobrevivendo importa mais do que parece: o stop agregado do
dia lê esse número, e zerá-lo num reinício **dá ao robô uma folga de risco que
ele não tem**.

### 2.2 Reinício assimétrico: entrada reconcilia, saída falha alto

Ordem de ENTRADA órfã é risco baixo (nenhuma posição está exposta esperando por
ela) — dá para cancelar sozinho pelo identificador. Ordem de SAÍDA órfã é risco
alto: há posição exposta, e rearmar por cima pode duplicar a venda ou inverter a
posição. Ali o sistema **falha alto** e exige conferência humana.

> **Regra:** a política de reconciliação segue o risco, não a simetria do código.

### 2.3 Reinício não pode mandar ordem que a máquina recusou vigiar

A rotina de recalibração recusava plantar a ordem quando já havia posição aberta
— e o ambiente mandava a ordem real para a corretora assim mesmo. Uma entrada
extra, sobre posição existente, que ninguém contabilizava.

> **Regra:** quem envia confere que quem decide de fato adotou a decisão. Não
> presuma pelo tipo do objeto.

### 2.4 Dois processos no mesmo slot é pior do que parece

Já aconteceu: **6 supervisores vivos para 3 slots**, inclusive no slot que
operava dinheiro real, enquanto o painel mostrava "parado" nos três. Dois
processos compartilham o mesmo identificador de robô, então cada um enxerga a
ordem e a posição do outro **como suas**. Nenhum detector de "atividade estranha"
acusa nada, porque o identificador bate. E cada um passa no próprio teto de
capital, sozinho.

A guarda contra isso existia só no botão do painel. A linha de comando e o
serviço do sistema passavam livres.

> **Regra:** exclusividade por slot é imposta pelo SISTEMA OPERACIONAL, no ponto
> onde o processo sobe — não pela interface. **Prefira uma trava que morre com o
> processo** (lock de arquivo/mutex) a um arquivo com PID: o arquivo exige
> verificar se aquele PID ainda vive, e essa verificação falha de forma ambígua.
> Trava do SO não deixa lixo.

Corolário barato: **cartão dizendo "parado" não é evidência de que não há robô
operando.** Confira o SO antes de explicar qualquer comportamento ao vivo.

**Recorreu em 31/08/2026, maior:** os mesmos sintomas, agora em **7 slots**
(a contagem de robôs de day trade cresceu desde 26/08), de novo incluindo o
robô REAL. Desta vez sem duplicação — 1 processo por slot, todos vivos — mas
`db/live_process.json` com `pid: null` ou a linha inteira ausente para os 7,
sobrevivendo a reinícios do próprio dashboard (`uvicorn --reload`) que
deixam o `Popen` órfão de pé sem levar o registro do PID novo junto. O
arquivo-com-PID continuou sendo a causa, exatamente como a Regra já previa.

**O que foi feito agora é mitigação, não a correção que a Regra pede.**
`dashboard.live_control.status()`/`status_all()` ganharam reconciliação
opt-in (`reconciliar=True`): perguntam ao SO se existe, mesmo assim, um
processo vivo deste slot e o readotam — nunca escolhendo entre dois
candidatos (isso continua incidente, não divergência de painel, ver acima).
Opt-in porque a varredura custa ~3s e a carga de `/operacao` tem contrato de
nunca pagar esse custo — só o poll periódico do cartão (20s) liga a
reconciliação, então o auto-reparo acontece dentro desse intervalo, não
instantaneamente. Isso fecha o SINTOMA (painel mentindo, risco de um clique
em "Iniciar" matar um robô real achando que ele estava parado) mas o arquivo
com PID continua sendo a fonte da verdade — a Regra desta seção (trava do SO
que morre com o processo) segue pendente. Pergunta 9 da Parte 8 continua sem
resposta implementada nesta plataforma.

### 2.5 A transação do diário não é atômica com o efeito externo

Todo o passo roda dentro de uma transação. Qualquer exceção posterior a um envio
real desfaz o registro daquele envio junto — o dinheiro já se moveu e o diário
finge que não.

O erro custa a ser visto porque a leitura ingênua do código diz o contrário:
"grava antes de enviar" existia, escrito nessa ordem. Só que gravar dentro de uma
transação que ainda não fechou **não é durabilidade nenhuma** — era verdade na
ordem do código-fonte e falso na ordem do disco. Um `rollback` posterior apaga o
registro exatamente como se ele nunca tivesse sido escrito.

Ao ser perseguido até o fim, o defeito apareceu em **três escalas diferentes**, e
só a primeira era óbvia:

1. **Entre passos.** A exceção no fim do passo desfaz o envio do começo dele.
2. **Entre barras do mesmo passo.** O feed devolve tudo que fechou desde a última
   consulta — não uma barra por chamada. Preenchimento confirmado na barra 1,
   falha de consulta na barra 2 do mesmo lote, e o diário nega a entrada inteira.
3. **Dentro de uma única chamada.** Aqui a correção anterior não alcança: uma
   função que já confirmou um fechamento parcial e levanta antes do `return`
   perde os eventos acumulados numa variável local — eles morrem com a pilha. No
   caso medido, `quantity` voltava de 1 para 2: o **dobro** do que a corretora
   tinha de verdade.

> **Regra:** confirmação de efeito externo (ticket recebido, preenchimento
> confirmado) vira registro durável **antes** de continuar processando o resto do
> lote — e uma função que pode levantar depois de já ter confirmado algo real
> nunca devolve o que confirmou apenas pelo caminho de sucesso. Ou o resultado
> parcial viaja com o erro, ou é persistido antes de o erro subir. Se a
> plataforma nova não permitir isso, a reconciliação contra a corretora (1.8) é a
> rede — mas é rede, não solução.

A escala 3 não é hipótese de laboratório: ela exige entrada dividida **e** saída
dividida ao mesmo tempo, que é a configuração padrão dos robôs em produção aqui.
Vale a pena procurar a combinação equivalente na plataforma nova antes de assumir
que o caso não existe.

### 2.6 Reinício no meio do pregão não é só "que ordem/posição sobrevive" — é também "que JANELA de dado sobrevive"

Confirmado ao vivo em 2026-08-31, `copa_win` no slot WIN@ (day trade, sombra): o
processo reiniciou **5 vezes** durante o mesmo pregão (13:00:05, 15:02:46,
15:02:55, 16:33:24, 19:31:42 UTC), e todo restart caiu no ramo FRIO
(`on_session_start()`), que zera `_faixa`/`_barras_hoje`/`_entradas_hoje` — o
robô esquece as barras já vistas do dia.

Reproduzido byte a byte (replay de `on_bar` fora de produção): rodar a
estratégia contínua desde a abertura real (12:03 UTC) dá sinal **LONG** às
12:48 (nível rompido 179900). Rodar a partir de 12:59 — a primeira barra que o
processo real de fato consumiu, por causa do restart das 13:00:05 — dá
**SHORT** às 13:45 no nível 180705, stop 183500, alvo 176280: os MESMOS três
números que `live_events` registrou como a ordem REAL enviada. O robô não
teve um dia ruim — teve um dia **diferente** do que a calibração OOS mediu,
porque a janela de rompimento de 10 barras nasceu de um ponto de partida que
não é o do pregão.

A causa: `IntradayLiveRuntime._needs_warm_start()` só devolve `True` quando a
estratégia declara `fixed_anchor_until` — atributo que só `Gremah`/`GremahTick`
têm. A máquina de repor estado por replay (`warm_start_calibration()` +
`resume_session()`, que já funciona via `on_bar` genérico para QUALQUER
estratégia) existe no código desde antes, mas o portão que decide chamá-la
enxerga só duas das quatro estratégias do catálogo. As outras duas —
incluindo o TOP-2 do pódio — cold-restart sempre, em silêncio, sem erro
nenhum no caminho.

> **Regra:** "o que sobrevive ao reinício" (2.1) tem uma TERCEIRA categoria
> além de decisão/fato: **janela de indicador que depende do histórico
> intra-sessão** (nível de rompimento, faixa do dia, o que for). Essa
> categoria não se restaura como fato (não é "reabrir o ticket") nem se
> redecide do zero como decisão (zero aqui não é neutro — é um pregão
> diferente, com metade das barras faltando). Ela se REPÕE por replay das
> barras reais já fechadas hoje. E o gatilho para repor não pode ser "esta
> estratégia específica declarou um atributo" — vira orfão automático em
> toda estratégia nova que ninguém lembrar de marcar. Um restart no meio do
> pregão deveria tentar warm start por PADRÃO, não por opt-in nomeado.

Correção não aplicada (decisão de arquitetura em `live/intraday_runtime.py`,
fica para o dono decidir): trocar o gatilho de `_needs_warm_start()` de "tem
`fixed_anchor_until`?" para algo que valha para qualquer estratégia com
sessão em andamento.

### 2.7 Um portão de segurança pensado para forçar inspeção humana morava no caminho de LEITURA — a tela que diria o que conferir foi a que caiu, exatamente com dinheiro exposto e o robô morto — CORRIGIDO 2026-09-10 (parcial)

Achado pelo dono ao subir o `dev.bat` em 2026-09-10: `GET /operacao`
respondia **HTTP 500 em toda renderização**, traceback terminando em
`RuntimeError` de `IntradaySessionMachine.restore` ("reinicio encontrou uma
FATIA DE SAIDA posicionada ... em execucao REAL"). Situação real no momento:
o slot `dt-wdo_grid_reload_maker-wdo@-live` tinha **1 contrato long aberto em
WDO@ @5144,0** (stop 5136,0 / alvo 5145,0), com fatia de saída de 1 contrato
registrada como posicionada no book (`exit_resting_qty=1`,
`exit_resting_bars_waited=2352`, `exit_ttl_bars=1e9` — o desenho "sem prazo"
adotado em 2026-09-09), e o **processo do robô estava morto** (pid null,
heartbeat parado às 09:03). O painel caiu justamente no instante em que havia
dinheiro exposto e o robô fora do ar — a tela que diria o que conferir no
terminal era a que não abria. E o estrago não era parcial:
`dashboard/app.py::_operacao_ctx` monta os slots numa list comprehension, e
**um slot nesse estado derrubava TODOS os cartões da página**, inclusive os
saudáveis.

Causa: o runtime de LEITURA do painel
(`dashboard/live_service.py::_build_intraday_runtime`) instanciava
`MT5IntradayExecution` sempre que a última config do slot dizia
`execution_mode="live"` — apesar da própria docstring do builder já afirmar
"Não conecta em nada" e "este runtime nunca posiciona nenhuma". Com
`machine.execution` setada, o portão de segurança do `restore` — que está
CERTO para quem vai voltar a OPERAR, porque o ticket da ordem-limite de saída
só vive na memória do processo do robô e resumir arriscaria mandar uma
segunda saída por cima numa conta NETTING — disparava também no caminho de
quem só queria MOSTRAR a tela. A ponte de execução no painel era acidente de
implementação, não desenho.

**Correção aplicada:** `IntradayLiveRuntime(..., somente_leitura=True)` no
painel — reporta o modo real na tela, mas não instancia a ponte de execução e
recusa `run_once`. O portão do `restore` agora vira **IMPEDIMENTO** carimbado
na conta (`policy_state["impedimento"]`, o mecanismo criado em 2026-08-25
exatamente para "robô parado e painel verde" — item 1.9) em vez de exceção
nua que só aparecia no log do processo. O robô continua PARADO; só passou a
dizer por quê, na tela onde o dono olha. Testes:
`tests/test_dashboard_daytrade_robot.py` (3 novos) e
`tests/test_intraday_live_runtime.py` (2 novos + o antigo `..._falha_alto`
reescrito como `..._para_o_robo`).

**Lacuna que fica em aberto (NÃO corrigida):** o portão não tem caminho de
saída no MESMO pregão. A mensagem manda "cancele a ordem-limite no MT5 antes
de religar este slot", mas religar reencontra o mesmo `exit_resting_qty`
persistido em `policy_state` — nada no repo limpa esse marcador, e ele só
some na virada do pregão (o snapshot de outro dia é descartado). Some-se a
isso uma assimetria já registrada no item 2.2: o lado da ENTRADA reconcilia
com a corretora depois de um restart (`resolve_orphaned_entry`,
`cancel_stale_refs`), o lado da SAÍDA não tem equivalente — ninguém pergunta
à corretora se aquela ordem-limite de saída ainda está no book. Um aviso sem
caminho de saída é uma parada permanente disfarçada de aviso.

> **Regra 1 — um portão de segurança que existe para obrigar inspeção humana
> não pode morar no caminho de LEITURA.** Reconstruir estado para EXIBIR e
> reconstruir estado para OPERAR são duas operações com regras diferentes:
> quem só exibe não pode carregar a camada que manda ordem, nem herdar as
> recusas dela.
> **Regra 2 — uma tela de operação nunca pode ter um slot capaz de derrubar
> os outros.** Renderização de N robôs é N falhas independentes, não uma; uma
> `list comprehension` sem isolamento por item transforma qualquer exceção
> local em apagão total, no pior momento possível para o apagão acontecer.
> **Regra 3 — um aviso que exige ação humana precisa de caminho de saída no
> MESMO ciclo em que apareceu**, ou ele é uma parada permanente com nome de
> aviso. E a reconciliação pós-restart tem de cobrir os DOIS lados da ordem —
> só a entrada reconciliar sozinha (2.2) deixa a saída, que é o lado de maior
> risco, sem ninguém perguntando à corretora o que sobrou.
> **Pergunte à plataforma nova:** pergunta 83 da Parte 8.

### 2.8 O achatamento de fim de pregão dispara por BARRA, não por relógio — um processo congelado e um pregão que acaba antes do corte apagam do MESMO jeito o trade ruim, e o ledger fica otimista para sempre

Em 2026-09-14 às 10:31 BRT o `copa_win` rodando em SOMBRA (conta 545, slot
`dt-copa_win-win@-shadow`, caixa sombra de R$3.000,00 definido na véspera)
abriu um SHORT de 1 contrato de WIN@ a 186.200 (stop 189.600 / alvo 184.045).
A partir daquele instante **o processo não produziu mais nenhum evento de
decisão até o fim do pregão** — nenhuma saída, e nenhum achatamento às 18:20.
O watchdog só percebeu às 21:09 BRT ("heartbeat parado há 91 min com o
processo ainda de pé") e **recusou-se a reiniciar** porque não conseguiu
consultar a posição no terminal (`Authorization failed` — o modo de falha do
item 5.25). No pregão seguinte o processo subiu a frio e a posição
simplesmente deixou de existir.

**O que é FATO, do diário.** A posição ficou aberta, não houve evento de
saída, e a margem da posição órfã (**R$100,00**) ficou presa no caixa e
nunca voltou. A aritmética do caixa fecha exatamente nesse desenho, e isso
é medido, não estimado:

| passo | R$ |
|---|---|
| caixa sombra em 14/09 | 3.000,00 |
| + único trade contabilizado em 14/09 | +231,50 |
| − margem da posição órfã, nunca liberada | −100,00 |
| = capital com que o processo subiu em 15/09 | **3.131,50** |
| − os 7 trades de 15/09 | −900,50 |
| = `cash_sombra` atual da conta | **2.231,00** |

**O que é ESTIMATIVA, do backtest — não fato medido.** Quanto aquela perda
teria valido é reconstrução, não extrato. O backtest do MESMO pregão, com a
MESMA config de produção, fecha esse short no achatamento das 18:20 a
187.390: **−R$238,50** — e é esse número que sustenta o "ledger R$138,50
otimista" a seguir. Mas o robô ao vivo, se tivesse achatado, teria achatado
pelo **último preço que ele CONHECIA**, e o feed dele estava morto desde
10:31 BRT — quase certamente um preço diferente de 187.390. **A direção do
viés é certa e é o que o item ensina** (o trade que fica aberto é
justamente o que está indo mal); **a magnitude exata em reais é estimada,
não medida.**

Ou seja: **o ledger da sombra está R$138,50 OTIMISTA (estimado)** em relação
ao que o robô realmente teria feito — R$100,00 de margem presa (fato) mais
≈R$238,50 do trade que sumiu (estimativa de backtest). A sombra não
registrou "um trade a menos": ela SUMIU com o trade perdedor e ainda
encolheu o caixa em silêncio — isso é fato; o TAMANHO do trade que sumiu é
a melhor estimativa disponível, porque o dado real que o mediria (o preço
que o robô veria) nunca existiu.

**O contraste que dá força ao item:** no MESMO 15/09, backtest e sombra
bateram **centavo a centavo** — 7 de 7 operações, mesmos preços, mesmos
minutos, mesmos motivos de saída, **−R$900,50 nos dois**. O motor não diverge
da sombra. O que diverge é o pregão em que alguma coisa impede o achatamento
de acontecer. A única diferença observada entre backtest e sombra em dois
pregões veio de INFRAESTRUTURA, não de modelo — e ela apontou toda para o
mesmo lado.

**O mecanismo — e por que "processo congelado" era só metade dele.** O
achatamento forçado de fim de pregão, em `src/backtest/intraday/machine.py`,
bloco "(2) flatten forcado", dispara assim:

```python
if not self.flattened and (ts.time() >= self.session_end_time_for(ts) or is_last_bar):
```

`ts` é o horário DA BARRA QUE CHEGOU — não existe temporizador de parede.
Se nenhuma barra chega depois do corte, essa linha nunca é avaliada de novo:
o achatamento não falha, simplesmente não é chamado. A rede de segurança
`or is_last_bar` só é alimentada em `src/backtest/intraday/engine.py:299`
(`is_last_bar=(ts == last_ts)`); `src/live/intraday_runtime.py` não passa
esse argumento em lugar nenhum, então ao vivo ele é sempre `False`. **O
backtest tem DOIS caminhos para achatar a posição; a produção tem UM SÓ — e
o que a produção não tem é justamente a rede.**

**O segundo gatilho, medido no MESMO dia em que o primeiro foi descoberto —
e que NÃO precisa de processo doente.** Em 15/09 os slots
`dt-wdo_grid_reload_maker-wdo@-shadow` (conta 548, último evento 17:15 BRT,
LONG #61 a 5.172,50) e `dt-wdo_grid_fade_off_t3-wdo@-shadow` (conta 550,
SHORT a 5.168,50) fecharam o pregão com posição aberta e **zero eventos de
FLATTEN**. A causa não foi travamento: a última barra de WDO@ do dia chegou
às **17:53 BRT**, **32 minutos antes** do corte das 18:25 BRT. Nenhum
processo saudável — travado ou não — teria achatado, porque não existiu
barra depois do corte para avaliar a condição acima. As duas posições
seguem registradas como abertas em `live_positions`. Isto é EXCEÇÃO — em 189
de 191 pregões o WDO@ negocia até 18:29 BRT e alcança o corte —, mas uma
exceção que ACONTECE prova que o desenho não tem PISO.

**Correção de leitura, registrada porque ela mesma foi cometida nesta
investigação.** O silêncio dos dois slots de WDO NÃO era o modo de falha do
`copa_win` de cima. São robôs maker **sem prazo**, e o motor **não
piramida**: enquanto a ordem-limite de saída espera no livro, não há nada a
registrar — ficar calado com posição aberta é o DESENHO, não sintoma. Os
dois alvos (5.173,50 e 5.167,00) foram tocados na marca exata depois do
silêncio, o que, com a fila calibrada (438/489 — ver
`backtest/intraday/fidelidade.py`), é justamente o caso em que a limite
toca mas não preenche a tempo. **O defeito não foi o robô parar — foi o
achatamento não chegar.** Confundir "parou de logar" com "travou" é um erro
de leitura, e ele foi cometido nesta mesma apuração antes de o dado corrigir.

O travamento de verdade em 2026-09-14 existiu, e é outro, já bem separado
deste: nos CINCO slots ao mesmo tempo, heartbeat parado às 19:38 BRT (o
watchdog mediu 91,0/91,1 min para os cinco no mesmo segundo) — evento de
máquina, não de robô.

> **Regra 1 — um processo de sombra que morre ou congela com posição aberta
> não produz um resultado "incompleto"; produz um resultado ENVIESADO PARA
> CIMA, e sempre para o mesmo lado.** O trade que não foi fechado é o trade
> que não entrou na conta, e trades ficam abertos por tempo demais
> justamente quando estão indo mal: o vencedor sai pelo alvo, o perdedor
> fica. O viés não é aleatório — ele seleciona a perda.
> **Regra 2 — quando o dado real falta, o backtest é a MELHOR ESTIMATIVA
> disponível do que teria acontecido, não um FATO medido, e o registro tem
> de rotular qual é qual.** Aqui, que a posição ficou aberta, que não houve
> saída e que a margem ficou presa são fatos do diário; QUANTO aquela saída
> teria custado é reconstrução — o backtest fecha no preço que o MERCADO
> tinha, não no preço que o ROBÔ VIVO teria enxergado com o feed morto. A
> direção do viés (ele seleciona a perda) é a lição que sobrevive; a
> magnitude em reais é estimada. Misturar número medido e número simulado
> na mesma frase sem marcar qual é qual faz o item nascer mais confiante do
> que a evidência permite.
> **Regra 3 — toda sessão que termina com posição aberta e sem evento de
> saída é uma sessão INVÁLIDA, não uma sessão com um trade a menos.** O
> ledger precisa RECONCILIAR posição aberta contra o fechamento do pregão
> antes de ser lido como medição; e o caixa precisa liberar a margem da
> posição órfã, senão ele encolhe em silêncio a cada incidente (R$100,00 por
> ocorrência neste caso).
> **Regra 4 (corolário de leitura, o que mais vale) — antes de comparar
> sombra com backtest, conte as SAÍDAS, não as entradas.** Se a sombra tem N
> entradas e menos de N saídas, a diferença entre os dois números não mede o
> motor: mede o que impediu o achatamento — que pode ser um processo morto
> OU um pregão que terminou antes do corte. As duas causas exigem a mesma
> reconciliação, mas só uma delas é incidente; a outra é o desenho batendo
> no próprio piso que não tem.
> **Regra 5 (a que generaliza) — toda proteção de fim de pregão precisa de
> um piso por RELÓGIO DE PAREDE, independente do fluxo de dados que ela
> observa.** Uma proteção acionada pelo próprio dado que pode faltar não é
> proteção — é uma aposta de que o dado vai chegar. Vale para achatamento,
> para corte de horário, para qualquer coisa que precise acontecer "até tal
> hora": se o único gatilho é um evento do feed, a ausência do feed desliga
> a proteção em silêncio, exatamente no cenário em que ela é mais
> necessária.
> **Corolário — quando o backtest tem uma rede que a produção não tem, a
> produção é mais frágil que a validação que a aprovou, e nada no número do
> backtest denuncia isso.** Procure, em qualquer motor, os parâmetros e
> caminhos que só o arnês de teste alimenta (aqui, `is_last_bar`).

**Estado (2026-09-15):** um piso por relógio de parede está sendo
implementado agora, por ordem do dono ("tem que funcionar para todo e
qualquer robô do sistema"), com a decisão morando no MOTOR e o `live/`
apenas chamando — `live/` não decide nada (AGENTS.md). O que este item
ensina não é o estado do conserto, é o modo de falha e a Regra 5: elas
continuam verdadeiras depois de a correção entrar, e continuam valendo para
qualquer proteção futura de "até tal hora" que alguém adicionar ao motor.

> **Pergunte à plataforma nova:** perguntas 109 e 110 da Parte 8.

---

## Parte 3 — Dimensionamento e capital

### 3.1 Capital inicial nunca é um número redondo de conveniência

Todo teste começa do caixa mínimo REAL para operar o instrumento, nunca de "R$50
mil para não zerar". Um capital genérico muda silenciosamente quantos lotes cabem
e se o portão de capital deixa a sessão operar — o que inverte qual geometria
"ganha".

### 3.2 O teto tem de valer sobre a exposição AGREGADA

O teto era aplicado por ordem. Duas entradas independentes passaram, cada uma
sozinha, contra uma conta que comportava uma. Um desenho de posições
independentes é **incompatível** com portão por entrada.

### 3.3 O único número que enxerga a conta inteira é a margem livre da corretora

Todo teto calculado a partir de "capital inicial + lucro realizado" é cego para
duas coisas ao mesmo tempo:

1. **Os outros robôs.** Se rodam na mesma conta, dividem a mesma margem física.
   Dois slots com R$400 digitados em cada comprometem margem contra uma conta que
   tem R$400 no total — e cada um passa no próprio teto.
2. **A perda ainda ABERTA.** O lucro realizado só anda quando a posição fecha.
   Uma posição sangrando deixa o teto otimista exatamente sob stress.

> **Regra:** pergunte à corretora a margem exigida pela ordem e compare com a
> margem livre da CONTA, antes de cada envio. É o único número que já desconta o
> que todo mundo (inclusive você, na mão) tem aberto.

**E o fator de folga é o que decide.** No incidente, depois do 1º contrato a
margem livre era ~R$150 e o 2º exigia R$150. Com folga de 1x o envio passa e a
conta zera igual. **Um portão que só impede o impossível não é portão — ele tem
de impedir o último passo que ainda cabia.**

### 3.4 Reserva de caixa: o mínimo documentado nunca foi suficiente

Depois do incidente, o dimensionamento passou a reservar 20% do caixa fora da
conta de quantos contratos cabem. Consequência imediata e desconfortável: os
robôs ficaram **inertes** no capital mínimo "de tabela".

Isso é informação, não bug: na medição anterior os dois já zeravam sozinhos. A
reserva só tornou visível no backtest o que antes só aparecia no extrato.

### 3.5 Quem mata é o TAMANHO DO STOP contra o capital, não o número de contratos

Cinco candidatos positivos com capital nocional folgado, rerodados com o capital
real: **3 zeraram a conta**. Nenhuma foi derrubada por atrito de fila — todas
rodaram com preenchimento otimista. O motivo é puro dimensionamento: o stop, em
reais, era próximo ou maior que o capital inicial inteiro (um deles: 27% do
capital por perda). **O teto de contratos nunca foi o gargalo** — zero recusas por
capital nas três quebras.

> **Regra:** o portão de admissão não é "o sinal é positivo?", é "uma sequência
> de stops cabe no capital?". Rode com o capital real antes de chamar qualquer
> coisa de candidato viável.

### 3.6 O capital do robô tem de ser relido, não congelado na inicialização

O processo roda contínuo por dias. O caixa era lido uma vez, na construção. O dono
podia sacar metade e corrigir o número na interface, e quem dimensiona barra a
barra continuava usando o valor antigo, mais alto.

### 3.7 Um portão que libera o que a camada seguinte recusa é pior que portão nenhum

O portão de entrada liberava com R$300 enquanto o dimensionamento real exigia
R$375. O robô subia, aparecia operando no painel, e tinha **toda** ordem recusada
em silêncio, para sempre.

> **Regra:** os limites de todas as camadas são o mesmo número, derivado do mesmo
> lugar. Se divergirem, a camada de cima mente.

### 3.8 Parâmetro de segurança opcional é parâmetro desligado

A margem por contrato era um campo opcional. Ausente, o teto por caixa ficava
desligado e sobrava só o limite **regulatório** da competição — sem nenhuma
relação com o dinheiro do dono. Era exatamente esse o estado do robô no dia em
que zerou a conta.

> **Regra:** parâmetro de segurança é obrigatório e falha ruidosamente quando
> falta. Um default silencioso reproduz o incidente num instrumento novo, sem
> nenhum erro no caminho.

### 3.9 Buffer de margem protege a corretora, não o dono — dimensionamento dinâmico pode crescer o risco por trade junto com o capital — CORRIGIDO 2026-08-29

Medido rodando `CopaWin` (WIN@, TOP-2 do pódio) com caixa real R$3.000 no
histórico salvo inteiro (182 pregões, 2025-12-01 a 2026-08-27, defaults de
produção do `registry.py`, dimensionamento via `contracts_from_capital_
com_reserva` — a versão SEGURA, adotada justamente por causa do incidente da
Parte 0): **5 trades, equity caiu de R$3.000,00 para R$68,50 (−97,7%)**, sem
nunca ficar negativa. Um único trade — 15 contratos, parado pelo `stop_vol`
— perdeu R$3.457,50 sozinho. Causa: a entrada anterior tinha lucrado, o
caixa cresceu (R$3.000 → R$4.290), e `quantidade_por_entrada` recalculou o
teto por caixa PARA CIMA (12 → 15 contratos) antes da entrada seguinte — o
mesmo `stop_vol` de sempre, agora sobre 15 contratos em vez de 12, é uma
perda em reais 25% maior. `RESERVA_CAIXA_SEGURANCA`/`MARGIN_BUFFER_FUTUROS`
fizeram exatamente o que foram desenhados pra fazer (nenhuma ordem foi
recusada por margem insuficiente nesses 5 trades) — e mesmo assim a conta
quase zerou, porque os dois calibram quantos contratos a MARGEM aguenta sem
chamada, não quanto de EQUITY um stop pode consumir. É a mesma regra do item
3.5 (stop contra capital, não contra número de contratos), medida aqui num
mecanismo diferente: dimensionamento dinâmico que ESCALA o risco por trade
para cima junto com o capital, em vez de um capital estático subdimensionado
desde o início.

> **Regra:** um teto de posição calibrado por MARGEM (ou por qualquer medida
> de alavancagem) não é um teto de RISCO — os dois só coincidem por acidente
> no tamanho em que foram medidos. Dimensionamento que cresce com o capital
> precisa de um segundo teto, independente do primeiro, sobre quanto de
> equity um único stop pode consumir (ex.: `contratos × stop_em_reais ≤ X%
> do caixa atual`) — sem ele, um robô que vem GANHANDO fica proporcionalmente
> mais exposto ao próximo stop, não menos.
> **Pergunte à plataforma nova:** o dimensionamento por capital desta
> estratégia tem algum teto que não seja margem/alavancagem? Se a resposta é
> só "quantos contratos a corretora deixa abrir", ainda falta o teto que
> protege o DONO, não a corretora.

**Correção aplicada:** novo teto independente, `strategy.daytrade.base.
contracts_from_risk` — `floor(caixa_atual × risco_% / stop_em_reais_por_
contrato)`, recalculado a CADA entrada com o stop DESSA entrada (nunca
ancorado num caixa antigo). A entrada usa o MENOR entre o teto oficial, o
teto por margem e este novo teto por risco (nenhum substitui o outro).
Adotado em `CopaWin` (`risco_pct_por_trade=0.05` no default de produção,
`registry.py`) — PROVISÓRIO: testado 2%-10% no mesmo histórico (todos
positivos, nenhum perto de zerar), mas sem varredura própria nem
confirmação OOS ainda. Reverificado com o mesmo teste de caixa real
(R$3.000, 182 pregões de WIN@): **274 trades, R$3.000,00 → R$12.498,00**,
equity mínima R$2.545,90 — nunca chegou perto de zerar.

> **Correção de escopo, 2026-09-11 (itens 3.17/6.21):** "nenhum perto de
> zerar" vale só no capital testado aqui (R$3.000). No capital REAL do slot
> de produção do `copa_win` (R$250,00), os mesmos 5% de `risco_pct_por_
> trade` são aritmeticamente INERTES — `quantidade_por_entrada` floor em
> `max(1, ...)` sempre devolve 1 contrato, e a conta chegou a equity
> NEGATIVA. O teto por risco deste item protege a partir de algum capital
> intermediário; não protege no capital em que o robô roda hoje.

Antes de chegar nessa correção, uma ideia intermediária (do dono) foi
testada e REFUTADA: "separar" uma fatia do caixa a cada marco de
crescimento (ex.: +60%) e parar de contá-la como caixa operacional. No
parâmetro pedido nunca chegou a disparar nesta janela (o salto fatal foi só
+43% de crescimento); forçando o disparo mais cedo, a conta foi a **equity
NEGATIVA** — pior que não fazer nada. Causa: a fatia "separada" é só
contábil (nunca sai da mesma posição/mesma conta) e fica CONGELADA em
reais — quando o caixa recupera de uma perda, ela vira uma fração cada vez
menor do caixa atual, e o tamanho da entrada reinfla sem nenhum novo
gatilho. Fica registrado aqui porque é o mesmo tipo de erro do resto deste
item, só que na tentativa de conserto: proteção que não é recalculada
contra o RISCO atual (só contra um marco do passado) não é proteção.

### 3.10 Capital mínimo de TABELA abre 1 posição; capital mínimo de VERDADE sobrevive ao histórico inteiro

Motivado por um resultado negativo (`WdoGridReloadMaker`, item anterior a
este de 2026-08-29) que "não podia existir": rodando o histórico salvo
INTEIRO (177 pregões de WDO@) com caixa real, a config em produção então
(T1 S4) **nunca sobrevivia** em nenhum capital testado até R$20.000 — cada
nível trava (cai abaixo do piso de margem pra abrir 1 contrato) em algum
ponto e **nunca mais recupera dali em diante** (mesmo mecanismo do item
1.14/3.9: sem trade, o caixa não muda, e sem caixa não há trade — catraca
de mão única). Só sobreviveu com R$30.000, 80x o "mínimo de tabela"
documentado (R$375 — margem × buffer × reserva, o bastante pra abrir 1
contrato UMA VEZ). Trocando só o STOP (T1 S16, sem nenhuma outra mudança),
o piso de sobrevivência caiu de R$30.000 para R$5.000 — uma diferença de
6x que a fórmula de margem sozinha nunca revelaria, porque margem mede
QUANTO CABE agora, não quanto a estratégia PERDE ao longo do tempo antes
de eventualmente lucrar.

> **Regra:** "capital mínimo" tem duas respostas diferentes e as duas
> importam. A de MARGEM (`margem × buffer × reserva`) responde "cabe 1
> posição?" — é rápida, analítica, e é o que a tabela documenta. A de
> SOBREVIVÊNCIA responde "esse capital atravessa a variância normal da
> estratégia no histórico inteiro sem cair no piso e travar pra sempre?" —
> só sai rodando o backtest CONTÍNUO (nunca dia-a-dia reiniciado) com cada
> nível de capital candidato, e é a única resposta que decide se o robô
> ainda vai estar vivo daqui a 6 meses. Nunca aumentar capital real de um
> robô usando só a fórmula de margem — ela sistematicamente SUBESTIMA o
> mínimo verdadeiro, às vezes por uma ordem de grandeza.
> **Pergunte à plataforma nova:** o capital que valida a abertura de uma
> posição na plataforma é o mesmo número usado pra decidir "quanto capital
> real este robô precisa"? Se for, falta rodar o histórico inteiro pra
> descobrir a diferença antes que o mercado descubra por você.

### 3.11 Piso de capital pode ser do DESENHO, não do parâmetro — varrer o parâmetro inteiro pra confirmar antes de tunar mais

Pergunta direta do dono depois do item anterior: "se só tenho o capital
mínimo inicial (R$375), do que me adianta saber que ele não trava a partir
de R$5.000? Eu quero que a partir do capital mínimo ele já tenha lucros e
lucros consistentes." Resposta que exigiu medir, não supor: varri **todo**
o espaço de `stop_ticks` já mapeado por varreduras anteriores (1 a 20, o
mesmo robô, `profit_ticks` e `level_spacing_ticks` fixos) contra 8 níveis de
capital real (R$375 a R$5.000), rodando o histórico INTEIRO (177 pregões)
pelo caminho de produção em cada uma das 88 combinações.

**Resultado: as 11 configurações de `stop_ticks` fazem a MESMA coisa em
R$375** — perdem um valor pequeno (de −R$3,40 a −R$93,40) nos primeiros dias
e depois praticamente param de negociar (10 a 169 trades no total, contra
milhares que a mesma config produz com capital adequado). Nenhuma lucra.
Nenhuma lucra até R$1.000. O salto de atividade (de centenas para milhares
de trades) só aparece entre R$3.000 e R$5.000, em TODA configuração
testada — não é uma característica de um `stop_ticks` específico, é uma
parede na mesma altura pra qualquer ponto do parâmetro.

> **Regra:** quando o capital mínimo de sobrevivência (3.10) está muito
> acima do capital que você de fato tem, a primeira pergunta não é "qual
> configuração resolve" — é "o piso é do PARÂMETRO ou do DESENHO". Varrer o
> espaço de parâmetro inteiro já mapeado contra o capital baixo responde
> isso em uma tarde: se a parede aparece em TODO ponto testado (como aqui),
> tunar mais parâmetro dentro da mesma família é tempo perdido — o problema
> é estrutural (aqui: contrato indivisível de 1 unidade + gate de margem
> tudo-ou-nada, que transforma qualquer sequência de perdas normal da
> própria estratégia em bloqueio permanente quando o caixa começa exatamente
> no piso, sem nenhuma folga). A saída correta é ou (a) acumular capital até
> o piso de sobrevivência medido, ou (b) mudar de instrumento/mecanismo de
> forma que o próprio piso caia — nunca insistir no mesmo parâmetro.
> **Pergunte à plataforma nova:** o instrumento que você vai operar tem
> unidade mínima indivisível (contrato, lote)? Se sim, o piso de capital
> real não é "preço × unidade mínima" — é esse número MULTIPLICADO pela
> folga necessária pra sobreviver à variância normal da estratégia sem
> nunca tocar o piso (3.10) — e nenhum ajuste de parâmetro dentro da mesma
> família de estratégia costuma mudar isso, porque o gate é do
> **dimensionamento**, não do sinal.

**Confirmado num SEGUNDO robô, mecanismo totalmente diferente (2026-08-29,
mesma tarde):** rodando `CopaWin` (rompimento direcional com stop por
volatilidade, não grid-maker) no piso real do WIN@ com reserva (R$250,
`margin_per_contract_brl=100`, `risco_pct_por_trade=0.05` já em produção)
no histórico salvo inteiro (182 pregões) — **2 trades em 182 pregões,
líquido −R$123,00, e trava** (1.575 de 1.577 tentativas recusadas por
capital). Mesma assinatura exata do item 3.10/3.11 na WDO F1: primeira
perda no piso zero de folga tira o caixa de baixo do limiar de 1 contrato
(margem × 2 × reserva) e nenhum trade mais abre pelo resto do histórico.
Confirma que a parede não é do grid-maker especificamente — é de QUALQUER
estratégia com dimensionamento dinâmico por caixa rodando exatamente no piso
de margem, sem nenhuma folga acima dele. Instrumento com unidade
FRACIONÁVEL (ação via execução fracionária, ver Parte 6) não tem esse
piso-parede: o mesmo teste em `Gremah` (PMAM3, lote de 100 ações) deu
**lucro em ambos os capitais testados** (R$30 → +R$15,69; R$1.000 →
+R$621,63, nunca zerou), com a ressalva de que R$30 só cobriu 8 dos 842
pregões salvos (o preço da PMAM3 precisa estar MUITO baixo pra R$30 caber —
ver `pmam3_colapso_de_preco_2026_08_26` — não é um piso estável, é uma
coincidência de o papel estar em colapso de preço agora).

**Piso exato do CopaWin, depois de uma varredura fina (R$250 a R$3.000):**
trava até R$500 (21 trades, −R$386,90, final R$113,10) e sobrevive de forma
limpa a partir de **R$750** (274 trades, +R$10.548,30, idêntico de R$750 a
R$3.000). Múltiplo sobre o piso de tabela (R$250): **3x** — bem menor que o
13,3x da WDO F1 (R$375→R$5.000). Confirma que o múltiplo em si também é do
mecanismo/calibração de cada robô, não uma constante universal — vale medir
caso a caso, nunca supor.

**Confirmado de novo em 2026-09-08, agora em TICK real e na geometria de
produção ATUAL (T2/S16, base já corrigida 5.12-5.14):** a mesma catraca de
ruína bateu de novo, desta vez dentro de uma janela OOS de validação inteira
(2 trades e trava por 50 dos 51 pregões) em vez de um backtest contínuo — e
o achado adicional é que isso também invalida a comparação IS/OOS nesse
capital, não só o número isolado. Ver item 6.15 para os dois números e a
regra de método.

> **Nota de 2026-09-08, mais tarde no mesmo dia (commit `4eb3e4a`):** a
> catraca continua valendo — é sobre CAPITAL e independe do custo — mas a
> geometria citada aqui como "produção ATUAL" (T2/S16) foi condenada horas
> depois, quando o motor passou a cobrar o deslize do alvo nativo: ela não
> tem edge (item 6.18). No motor corrigido a catraca fecha MUITO mais cedo,
> em 71 de 72 pregões do IS. O que este item afirma sobre o mecanismo segue
> de pé; o rótulo "produção atual" na frente do T2/S16, não.

### 3.12 O % de risco não atravessa de um robô pro outro — o tipo de stop muda o que o % vira em contratos

Pedido do dono depois do item 3.11: já que o CopaWin escala contratos com o
caixa e a WDO F1 não, ligar o MESMO mecanismo (`contracts_from_risk`, item
3.9) na WDO F1 também, "prezando pelo controle de risco". Liguei copiando o
valor já em produção no CopaWin (`risco_pct_por_trade=0.05`) — e o capital
de R$5.000, que era o piso de sobrevivência LIMPO da WDO F1 (item 3.10/3.11,
sempre 1 contrato fixo até então), **quase zerou**: líquido −R$4.753,12,
equity mínima R$246,88, contra +R$2.671,80 que o dimensionamento estático
sempre deu ali.

Causa: o stop do CopaWin varia com a volatilidade do dia (`stop_vol x
volatilidade`), então o mesmo % de caixa se traduz num número de contratos
que muda dia a dia, amortecendo naturalmente dias de stop caro. O stop da
WDO F1 é FIXO em ticks (16 x R$0,50 x R$10/ponto = **R$80 por contrato,
sempre o mesmo número**) — 5% de R$5.000 já libera 2-3 contratos enquanto o
caixa ainda está exatamente no ponto onde a variância normal da estratégia
mais dói, amplificando a sequência de perdas em vez de esperar existir
folga de verdade. Uma varredura de {1%, 2%, 3%, 5%} achou que **1%** é o
único valor que nunca regride nenhum capital já medido (R$3.000/R$5.000
saem idênticos ao estático de antes) e ainda ganha de verdade em capital
alto (R$50.000: +R$13.095,09 contra os +R$2.671,80 fixos de sempre).

> **Regra:** um teto por risco (%) não é uma constante universal — é
> calibrado contra o MECANISMO do stop daquele robô específico. Copiar o
> número de um robô com stop VARIÁVEL (por volatilidade) para um robô com
> stop FIXO (em ticks/pontos) pode reproduzir o EXATO problema que o teto
> por risco foi criado pra evitar (item 3.9), só que num capital diferente.
> Todo `risco_pct_por_trade` novo precisa da mesma varredura de segurança
> (múltiplos capitais, incluindo os que já eram limpos ANTES da mudança)
> antes de ir pra produção — "o mecanismo já existe e funciona noutro robô"
> não é evidência de que o NÚMERO funciona aqui.
> **Pergunte à plataforma nova:** o stop desta estratégia é fixo ou varia
> com a barra/dia? Se variar, um teto por % de risco se adapta sozinho; se
> for fixo, o % precisa ser calibrado para o pior caso (capital mínimo de
> sobrevivência, item 3.10), não emprestado de outro robô.

### 3.13 Corrida entre "consultar margem" e "enviar ordem" não tem trava entre processos — CORRIGIDO 2026-09-03

Achado de auditoria adversarial em 2026-09-03 (não é incidente medido —
ninguém viu isso acontecer ainda). `_check_margem_da_conta` lê `margin_free`
fresco a cada chamada, sem cache — mas cada slot de day trade roda como
processo do SO separado (`subprocess.Popen`), todos no mesmo login MT5, ou
seja, na MESMA margem física. Não existe lock (arquivo, mutex, transação)
entre a leitura da margem e o envio da ordem. Duas ordens de abertura de
dois processos distintos que caiam dentro da janela de latência de um
`order_send` (round-trip até o terminal) cada uma leria `margin_free`
otimista e passaria — reproduzindo o padrão exato do incidente da Parte 0
(item 3.2), agora ENTRE processos em vez de dentro de um. O próprio repo já
documenta um caso real de "Popen órfão" (dois processos pro mesmo slot) em
`dashboard/live_control.py` — o gatilho de duplicação já existe; falta só
coincidir no tempo com uma checagem de margem.

> **Regra:** quando várias estratégias/processos compartilham UMA margem
> física na mesma corretora, o portão de margem tem de ser serializado ENTRE
> processos, não só correto dentro de cada processo. "Cada robô confere
> sozinho antes de mandar" não basta quando o recurso conferido é
> compartilhado por todos.
> **Pergunte à plataforma nova:** múltiplas estratégias/processos operam a
> mesma conta e compartilham margem física? Se sim, existe alguma trava
> entre "consultar quanto sobra" e "gastar", ou cada processo confia só na
> própria última leitura?

**Correção aplicada:** o par "consultar margem → enviar a ordem" virou seção
crítica serializada por uma trava de ARQUIVO do sistema operacional,
compartilhada por todos os processos que usam o mesmo login. Trava de
processo, não de thread — thread não resolve nada aqui, porque cada robô é um
processo separado. Escrita no diário e I/O de banco ficam FORA da trava, pra
seção crítica não durar mais do que precisa.

Dois cuidados que fazem a diferença entre trava e robô travado. Primeiro: a
trava é mantida pelo núcleo do sistema contra o descritor de arquivo do
processo, então ela é liberada no instante em que o processo termina, por
qualquer motivo — sem arquivo de PID, sem heurística de "trava velha", sem
ninguém precisar rodar limpeza. Segundo: quem espera desiste por tempo, e
desistir é tratado como **consulta que falhou**, nunca como recusa por margem
insuficiente (item 1.6: "não sei" nunca autoriza; e são fatos diferentes pra
quem opera — ver item 1.16). A ordem não sai, e o robô re-arma pelo critério
dele no ciclo seguinte.

Os DOIS pontos de envio do robô ficaram cobertos — a decisão por barra e a
retomada depois de reinício. O segundo quase ficou de fora, e vale registrar
por quê: a correção foi feita em paralelo com a do item 3.14, que estava
editando exatamente aquele trecho. Correção que para na fronteira de outra
correção precisa de alguém conferindo a costura depois; foi só isso que
impediu de sobrar metade da lacuna aberta com o item marcado como resolvido.

### 3.14 Restart no meio do pregão reseta o teto por risco pra zero — silenciosamente — CORRIGIDO 2026-09-03

Achado de auditoria adversarial em 2026-09-03. `warm_start_calibration`
(recalibração ao reconectar no meio do pregão) chama `on_session_start` +
`on_bar`, mas nunca `on_capital_update` — o caixa dinâmico
(`_cash_atual_brl`) fica em `0.0` até a próxima atualização normal do
mecanismo. Com `risco_pct_por_trade` setado (WDO F1 desde o item 3.12),
`teto_por_risco` calcula 0 e o `max(1, teto)` do item 3.9 força sempre 1
contrato — nunca o número que o caixa atual de verdade permitiria. A direção
do erro é conservadora (subdimensiona, nunca superdimensiona), mas o efeito
prático é: **todo restart no meio do pregão desliga o dimensionamento
dinâmico até a próxima resincronização**, sem nenhum log ou alerta que diga
isso — e o log `"sessao a fria"` já mostrado no painel não distingue esse
caso de um restart qualquer.

> **Regra:** todo caminho de (re)inicialização que alimenta um cálculo de
> risco tem de popular as MESMAS variáveis que o caminho normal popula,
> antes do primeiro cálculo que depende delas — "warm start" que pula um
> passo de setup vira bug silencioso, não atalho inofensivo.
> **Pergunte à plataforma nova:** toda rotina de reconexão/retomada
> recalcula o mesmo estado que a inicialização normal calcula, ou herda um
> campo zerado/default até o próximo ciclo regular?

**Correção aplicada:** o caixa corrente passa a ser injetado na recalibração
de reconexão, e é atualizado antes de cada barra do replay — a mesma sequência
que o motor já roda em cada barra de produção. O número vem de fora (quem tem
acesso ao estado da conta calcula e passa), não de uma consulta dentro da
lógica de sinal: a lógica de sinal tem de continuar recebendo dado e
devolvendo decisão, sem ir buscar nada, porque ela vai ser portada. E se o
caixa vier inválido, isso agora vira alarme no diário em vez de degradação
muda.

**A correção revelou um problema pior, que ela estava mascarando** — virou o
item 3.15, e é a parte mais importante deste item. Vale a leitura antes de
aplicar esta mesma correção em qualquer outra plataforma: com o caixa
corrigido, o robô voltou a pedir o tamanho de verdade, e foi aí que apareceu
que o tamanho pedido nunca passava pelo teto da camada seguinte.

### 3.15 Consertar um subdimensionamento silencioso pode entregar um robô inerte — a camada que ARMA a ordem tem de aplicar o teto da camada que PREENCHE

Achado em 2026-09-03, ao verificar a correção do item 3.14 — não por
hipótese: dois testes já existentes começaram a falhar, e a falha era
`resultado do dia = 0`, robô que não operou nada.

Encadeamento. Enquanto o caixa ficava zerado na retomada (o bug do 3.14), o
teto dinâmico degradava pra 1 unidade — que cabia, e portanto operava.
Corrigido o caixa, o robô voltou a pedir o tamanho real: **26 contratos**,
contra um teto agregado de **~4** naquele cenário (caixa de R$1.000, margem de
R$100 por contrato). O pedido de 26 não é absurdo do ponto de vista de quem o
fez — o dimensionamento por caixa daquele robô não conhece margem nem futuro,
e essa ignorância é deliberada: ela mora na lógica de sinal, que precisa
continuar portável. O problema é o que acontecia depois: a ordem da retomada é
plantada direto, sem passar pelo caminho normal de decisão, então o teto
agregado só era conferido no PREENCHIMENTO — e lá a recusa é por inteiro. Sem
trade fechado, o caixa não muda; sem caixa novo, o pedido continua 26. Robô
inerte pelo resto do pregão, com uma ordem no book que nunca poderia
preencher, e o painel mostrando um robô com ordem armada.

Ou seja: a correção conservadora trocou "opera pequeno demais, em silêncio"
por "não opera, em silêncio". A segunda é pior, e uma correção que troca um
modo de falha pelo outro sem ninguém medir passa por melhoria.

> **Regra:** nenhuma camada arma uma ordem que a camada seguinte vai recusar
> por inteiro. O teto que o preenchimento aplica tem de ser aplicado no
> momento de ARMAR — encolhendo o pedido pro que cabe, ou não armando nada
> quando não cabe nem uma unidade. Não armar é um desfecho legítimo e
> informativo; armar tamanho que não passa é uma ordem morta que se disfarça
> de robô operando. O corolário de método: ao corrigir um subdimensionamento
> silencioso, medir o que o sistema passa a PEDIR antes de comemorar — o
> valor errado podia estar escondendo que ninguém validava o pedido.
> **Pergunte à plataforma nova:** a plataforma recusa no momento do REGISTRO
> uma ordem cujo tamanho não cabe na margem livre, ou aceita registrar e só
> recusa no preenchimento? Se recusa só no preenchimento, a recusa é parcial
> (preenche o que cabe) ou total? Recusa total no preenchimento é o caminho
> mais curto para um robô inerte com ordem viva no book.

### 3.16 Recusa por capital sem espera vira laço de milhares de tentativas idênticas

O WDO F1 opera com R$375, exatamente o piso de 1 contrato (margem R$150 ×
buffer 2,0 × reserva 1,25). Uma oscilação que leve o caixa abaixo disso faz
o motor recusar toda entrada; `on_order_rejected` (item 1.14) zera
`pending_side`; o robô arma ordem NOVA no tick seguinte; recusa de novo.
Medido em 2026-03-04: **25.556 recusas por capital num único pregão** —
a segunda fonte de enxurrada de envios que tropeça no freio do item 1.18
(a primeira é a reancoragem do item 4.14), e ninguém tinha visto porque não
aparece em pregão nenhum onde o robô tem folga de caixa.

> **Regra:** operar no piso exato de capital não é "cabe justo" — é ficar
> do lado errado de uma catraca binária, onde cada tick é um novo sorteio
> entre "opera" e "recusa". Recusa por capital tem de ter espera antes do
> rearme, pelo mesmo motivo que reancoragem (4.14) tem: sem espera, uma
> condição estável de mercado vira um laço de milhares de tentativas
> idênticas por pregão. Um contador de recusas por motivo, por pregão, com
> teto, é o instrumento que torna isso visível — a ausência dele é o que
> deixou o laço passar despercebido.
> **Pergunte à plataforma nova:** quando a plataforma recusa uma ordem, o
> meu robô espera antes de tentar de novo? Existe contador de recusas por
> motivo e por pregão, com teto?

**Correção aplicada:** o mesmo portão do item 4.14 (`reancora_min_
segundos`, via `_pode_armar_apos_recusa`) passou a valer também para o
rearme pós-recusa por capital — calibrado e verificado junto com a
reancoragem, nos mesmos 126 pregões (ver 4.14 para os números completos de
calibração e o risco residual sobre `max_trades_per_side`).

### 3.17 O portão de capital só sabe checar MARGEM de abertura — o `copa_win` foi à conta NEGATIVA rodando exatamente a config e o capital de produção

Confirma e AGRAVA o item 3.11 ("piso exato do CopaWin"). Medido em
2026-09-11 (`scripts/daytrade/copawin_escada_perda_sweep_2026_09_11.py` e
`scripts/daytrade/copawin_teto_perda_diagnostico_2026_09_11.py`), rodando o
`copa_win` (WIN@, TOP-2 do pódio) com os kwargs REAIS de produção
(`_KWARGS_PADRAO`, alvo_vol=19/stop_vol=12) no capital REAL do slot sombra
que roda hoje (`dt-copa_win-win@-shadow`, R$250,00) sobre o histórico IS
congelado (129 pregões, 2025-12-01 → 2026-06-12): a conta foi a **equity
NEGATIVA** — `wiped_out_at = 2025-12-18 15:07`, mínimo **−R$7,10**. Pior
operação: **−R$446,50 em 1 contrato** (178% do capital inicial), saída por
STOP; as 5 piores foram −446,50 / −397,50 / −324,50 / −292,50 / −252,50,
todas 1 contrato. 25 trades em 129 pregões, 116 sem trade — janela também
censurada (item 6.1/6.15).

O item 3.11 já tinha medido "trava" neste mesmo robô a R$250 (21 trades,
−R$386,90, final R$113,10) — mas parava aí: caixa baixo, sem trade, sem
nunca cruzar zero. Esta medição, na config de produção ATUAL e na janela
IS, mostra que "trava" não é o pior desfecho possível: o mesmo mecanismo
pode entregar conta **negativa** antes de travar, porque o portão de
entrada só verifica se cabe abrir 1 contrato (margem R$100 × buffer ×
reserva) — nunca quanto esse contrato pode PERDER. O stop do `copa_win` é
por volatilidade (`stop_vol=12 × vol do dia`), e a distribuição medida em
182 pregões salvos é: média R$309,97/contrato, mediana R$293,00, p95
R$455,60, máximo R$728,50 (`copawin_teto_perda_diagnostico_2026_09_11.py`).
A perda MEDIANA de um único stop já é 117% do capital de R$250.

> **Regra (portável):** margem para ABRIR e perda máxima do STOP são dois
> números independentes, calculados de formas diferentes, e checar só o
> primeiro não é uma aproximação do segundo — é medir outra pergunta. Antes
> de pôr em produção (ou em capital real) qualquer robô cujo stop varie com
> a volatilidade do dia (em vez de ser fixo em ticks/pontos), compare a
> distribuição do stop EM DINHEIRO — p95 e máximo, nunca só a média — contra
> o caixa disponível. Se o p95 já passa do caixa, a conta fica negativa com
> o azar COMUM da própria estratégia, não com um evento raro. Um piso de
> capital derivado só de MARGEM (3.10) responde "cabe abrir?"; nunca
> responde "sobrevive ao stop?" — são a mesma lacuna do item 3.5/3.9, agora
> com a distribuição medida e o desfecho batendo negativo, não só travando.
> **Pergunte à plataforma nova (pergunta 91):** a plataforma recusa a ordem
> quando o STOP declarado excede o caixa disponível, ou só valida a margem
> de abertura? Se só a segunda, o robô precisa construir o teto por perda
> máxima do stop por fora — checar margem nunca é suficiente para stop
> variável por volatilidade.

### 3.18 O portão de caixa mínimo é para o dinheiro real — não para o robô de teste — CORRIGIDO 2026-09-17

O gate de "caixa mínimo para operar" (day trade) estava sendo aplicado por
igual a robôs REAIS (`execution_mode="live"`) e a robôs de SIMULAÇÃO/sombra
(`execution_mode="shadow"`), em dois lugares independentes: (1)
`live.intraday_runtime.IntradayLiveRuntime._check_capital` — o gate diário
(1x o lote no preço de hoje) já LIA `cash_sombra` para robôs em sombra, mas
continuava RECUSANDO o pregão se esse saldo (de teste) fosse baixo; (2)
`dashboard.live_control.start()` — o piso de entrada (2x o lote + reserva)
recusava subir um robô em sombra se o `cash_sombra` do slot não cobrisse o
piso. Nenhum dos dois protegia dinheiro nenhum: um robô sombra nunca manda
ordem para a corretora. Corrigido por pedido do dono, 2026-09-17: "os robôs
de simulação precisam ter a quantidade de caixa inicial pra operar, mas isso
está errado, essa regra só deve ser aplicada para robôs reais, os sombra
podem executar com qualquer valor, afinal são robôs de teste mesmo."

**A correção:** `_check_capital` retorna `None` (sem alarme, sem
impedimento, sem sequer calcular o mínimo) sempre que
`execution_mode == "shadow"`; `live_control.start()` só roda o bloco de
checagem de piso (`min_cash_for` + `available_cash` + comparação) quando o
modo do gate é `"live"` — o swing continua sempre `"live"` (não tem conceito
de sombra) e por isso mantém o piso de sempre.

**O efeito colateral no teste, que vale registrar:** 6 testes de
`tests/test_intraday_live_runtime.py` verificavam o gate chamando
`run_once()` em modo sombra (o default do arquivo) — e tiveram de ser
convertidos para chamar `_check_capital`/`_gravar_impedimento` DIRETO com
`execution_mode="live"` explícito, porque em modo live de verdade o
warm-start (`_start_session`) manda ordem-limite para a corretora ANTES do
gate de caixa ser consultado — rodar esses testes via `run_once()` completo
em modo live explodiria contra o dublê `_ExplodingBroker` do arquivo. Um
teste que corrige o modo errado de um gate pode continuar "passando" por
caminho errado se a chamada de mais alto nível também mudou de
comportamento. Foram adicionados 2 testes novos provando o comportamento
correto: `test_sombra_opera_mesmo_com_caixa_abaixo_do_minimo_do_dia`
(test_intraday_live_runtime.py) e
`test_start_daytrade_em_sombra_ignora_o_piso_de_caixa` (test_live_control.py)
— sombra opera com qualquer caixa, inclusive R$1,00 contra um piso de R$200.

> **Regra (portável):** todo gate cujo motivo é "a corretora vai recusar por
> falta de fundos" só faz sentido quando dinheiro real está em jogo. Um robô
> de simulação/sombra/paper-trading nunca manda ordem para lugar nenhum —
> aplicar o mesmo piso a ele não previne perda alguma, só impede o dono de
> rodar deliberadamente um teste com capital pequeno (ou zero). Antes de
> portar ou reusar um gate de capital/margem, pergunte qual das duas coisas
> ele protege: "a corretora vai recusar" (condicione ao modo REAL) ou "o
> resultado simulado é realista" (esse sim se aplica à simulação — é a
> fidelidade de execução da Parte 4, outra pergunta).
> **Pergunte à plataforma nova (pergunta 113):** cada gate de
> capital/margem/caixa mínimo desta plataforma foi auditado com a pergunta
> "isto protege dinheiro real, ou só bloqueia um teste?" Se a plataforma
> tiver um modo sombra/paper equivalente, o mesmo gate não pode ser aplicado
> a ele sem essa mesma ressalva — senão o robô de teste herda um piso de
> capital que só faz sentido para o robô real.

---

## Parte 4 — Preenchimento: onde o backtest e o book divergem

Esta é a parte que mais custou tempo e a que menos se percebe olhando o resultado.

### 4.1 Toque no preço não é preenchimento

O motor preenchia ordem-limite no primeiro toque, no preço exato, sem fila. Mas o
preço ter negociado no seu nível significa que alguém negociou ali —
provavelmente com quem estava **na frente** da fila.

Medição no real: **12 ordens enviadas, ZERO preenchimentos**, contra 7 trades do
gêmeo em simulação, no mesmo ativo, no mesmo dia, nos mesmos preços.

Modelado depois: a estratégia morre entre 20x e 200x o volume mediano por negócio
à frente da ordem. **A fila real observada era ~7.300x.** Ou seja, de 4x a 36x
além do ponto de morte.

E o modo de falha que o modelo produz é exatamente o observado: não é sangria, é
**parada de preenchimento**. O robô real não perde dinheiro; ele não negocia.

> **Regra:** um backtest de estratégia passiva (maker) sem modelo de fila é
> otimista por construção. **Pergunte à plataforma nova:** o simulador dela
> modela posição na fila? Se não modelar, o número dela responde uma pergunta
> diferente da que você está fazendo.

### 4.2 Rearmar a ordem devolve você ao fim da fila

O rearme por tempo cancelava e reenviava a ordem a cada 30 minutos parada. Em
ativo de centavos o nível recalculado dá **no mesmo preço** — 9 de 11
substituições foram de R$0,1300 para R$0,1300. Cada substituição devolvia a ordem
ao fim da fila, exatamente quando a espera começaria a valer.

> **Regra:** rearme que recalcula lado, nível e tamanho IDÊNTICOS não deve
> reenviar nada — mantenha o ticket. E qualquer comparação de parâmetro que mude
> a **frequência de rearme** não é confiável com fila desligada.

### 4.3 Trocar limite por mercado troca um modo de falha por outro

Teste real: ordem a mercado resolve a fila, sempre entra. E cobra por isso
**deslize no mesmo intervalo que a estratégia tenta capturar** — dois deslizes de
1 tick em menos de 100ms, R$1,00 de prejuízo real num teste que deveria ser
neutro. Com alvo de 1 tick, não sobra margem nenhuma para absorver isso.

### 4.4 Divida em fatias do tamanho do piso do mercado

Dividir a ordem em fatias de 1 lote funciona (o menor negócio real observado já é
1 lote). Dividir em **percentual do volume** não funciona — o pedaço fica maior
que o negócio típico de novo.

### 4.5 Meça o edge em TICKS, não em reais

Medido em 18 pares (robô, ativo): edge médio de **0,458 tick por trade**, com
**18 de 18 abaixo de 1 tick**. Cruzar o spread para garantir execução custa ≥1
tick. O edge inteiro do TOP-1 era menor que 1 tick de derrapagem nos trades que
batiam stop.

> **Regra:** antes de promover qualquer ativo, meça o edge por trade em ticks. Em
> reais, o número esconde se você está tentando capturar menos do que a menor
> unidade que o mercado sabe mover.

### 4.6 O piso de 1 tick pode estar decidindo o seu alvo

A geometria usava `max(1, round(preço × percentual / tick))`. Nos preços
correntes, o alvo nominal valia 0,04 a 0,87 tick em **9 de 10 ativos**. Ou seja:
o percentual calibrado não era o que decidia o alvo — **o piso decidia**. A
família inteira operava no piso, não na calibração, e ninguém tinha medido isso.

Pior: alvo, espaçamento e stop saíam todos do MESMO parâmetro, então subir o alvo
para tirá-lo do piso **arrastava o stop junto**. A grade percentual nunca testou
"alvo maior com o stop onde está" — só testou "tudo maior junto". Isso é
resultado sobre a ESCALA da geometria, não sobre a FORMA dela.

> **Regra:** parâmetros de geometria são independentes, e você mede o que a
> produção de fato ARMOU, não o que a configuração diz.

### 4.7 O gêmeo em simulação não é estimativa do real

Antes de comparar simulado com real, olhe o volume que preencheu no nível na
simulação. Um único negócio de 100 ações bastando para dar a ordem por
preenchida é evidência fraquíssima de que a fila teria chegado.

### 4.8 Alvo NATIVO amarrado na própria ordem (`sl`/`tp` atômico) também desliza — 10 de 11 saíram PIOR que o nível pedido, ZERO a favor; e o STOP, medido separado, anda na direção OPOSTA

Primeira operação real do WDO F1 (`dt-wdo_grid_reload_maker-wdo@-live`, WDO@,
2026-09-04): entrada preenchida a 5.150,000, alvo amarrado nativamente na
MESMA ordem de abertura (`broker_mt5.py::place_pending`, campo `tp` no
`request`, exatamente o desenho que fecha o incidente de 2026-08-28 — posição
nunca fica nua) em 5.150,500 (entrada + 1 tick, `profit_ticks=1`). O deal de
saída, reconstruído pelo histórico da corretora (item 1.17), fechou a
5.150,000 — **o mesmo preço da entrada, um tick abaixo do alvo registrado**.
Resultado: R$0,00 bruto − R$0,50 de corretagem = **-R$0,50**, contra os
+R$4,50 líquidos que a MESMA estratégia fechou em 11 de 11 operações do gêmeo
em sombra no mesmo pregão (preenchimento simulado, sem deslize nenhum).

`sl`/`tp` atômico resolve "a posição nunca fica sem proteção registrada na
corretora" — não resolve "o preço de saída é o preço registrado". Na prática
esse alvo executa como gatilho convertido a mercado, não como limite
resting: o mesmo modo de falha do item 4.3 ("trocar limite por mercado troca
um modo de falha por outro"), só que aqui ninguém escolheu mercado — o
código pediu um nível, a corretora entregou outro.

**Não era evento — é a regra da corretora. Medido de novo em 2026-09-08, com
n=8.** Auditoria do pregão inteiro do mesmo slot (WDO F1, T2/S16, caixa R$375,
1 contrato), cruzando o histórico de ORDENS e de DEALS do terminal contra
`db/live.sqlite`: das 22 idas-e-voltas do dia, **8 saíram pelo alvo nativo — e
8 de 8 executaram PIOR que o nível pedido**, 7 delas por 1 tick e 1 por 2
ticks. Três exemplos, nível pedido → preço executado: 5.112,500 → 5.112,0;
5.111,000 → 5.111,5; 5.109,500 → 5.108,5. Se as 8 tivessem pago o nível
registrado, o bruto delas seria **+R$80,00**; foi **+R$35,00**. O deslize
cobrou **R$45,00** — 56% do bruto dos trades vencedores do dia.

**A população COMPLETA, no fim do mesmo 2026-09-08: n=11, e ela virou número
no motor.** Reconstruídos os TRÊS pregões em que este robô já mandou ordem
real (2026-08-28, 2026-09-04, 2026-09-08) a partir do histórico de DEALS e de
ORDENS do terminal — não de `db/live.sqlite`, que **não serve para esta
medição**: ali a ordem de saída grava `limit_price == avg_price` (o nível
PEDIDO simplesmente some) e o rótulo `target` é INFERIDO pelo robô, o que dá
19 saídas rotuladas "alvo" no dia contra as 8 que a corretora de fato executou
por TP nativo (2,4x, item 4.15). O pareamento correto é outro: a ordem de
ENTRADA carrega o `tp` no próprio request, e o deal de saída disparado por ele
volta com `reason=5` e o nível no `comment` — `entry_order.tp == nível do
comment` em 11 de 11 casos.

| deslize | 0 tick | −1 tick | −2 ticks |
|---|---|---|---|
| n | 1 | 9 | 1 |

Média **−1,000 tick**, mediana −1,0, desvio 0,447, mín −2,0, máx 0,0 — **10
contra a posição, 1 neutro, ZERO a favor** (sob moeda justa, p ≈ 0,001). Em
dinheiro: 11 ticks × R$5,00 = **R$55,00 de deslize**, contra um bruto teórico
de R$95,00 se as 11 tivessem pago o nível pedido — **57,9% do bruto foi
embora antes da corretagem**.

**O STOP foi medido SEPARADO, e é por isso que ele não foi tocado.** Na mesma
reconstrução: n=2 saídas por `sl` do robô (0 tick e **+1 tick A FAVOR**) mais
3 saídas manuais por stop no mesmo contrato (0 tick nas 3) — **5 de 5 nunca
executaram PIOR que o nível pedido**, direção oposta à do alvo. É consistente
com o mecanismo: o stop vira ordem a mercado no toque (e já paga
`slippage_ticks` no motor), o alvo é gatilho varrido. Somar os dois num
"deslize de saída" único teria cobrado duas vezes de um e nada do outro.

**Consequência de engenharia (commit `4eb3e4a`):** o motor passou a COBRAR
esse tick. `IntradayCostModel.target_slippage_ticks` +
`apply_deslize_alvo_nativo()`, aplicado em `_close_position` **só no alvo NÃO
fatiado** — a saída fatiada continua a zero, porque ali existem ordens-limite
reais no book, que de fato ficam resting. Ligado por default em `config_for`
(item 3.8: parâmetro de segurança opcional é parâmetro desligado), que é o
caminho de `run_live.py::build_intraday`, do painel e de todo backtest. **O
que isso revelou sobre a geometria de produção está no item 6.18, e é o
achado mais caro do projeto até aqui.**

Duas coisas que o caso de n=1 não conseguia mostrar. Primeira: o deslize é
**direcional**, não ruído em torno do nível — em 8 de 8 ele foi contra a
posição, então nenhuma média o compensa. Segunda: ele muda o parâmetro de
produção. Depois do caso acima, T1 foi proibido e a produção passou a rodar
**T2** (alvo de 2 ticks = R$10,00 por contrato). Com 1 tick de deslize
sistemático, **T2 é pago como T1** — metade do alvo desaparece antes de a
corretagem entrar na conta. Alvo pequeno não é "agressivo demais": é
inexequível, porque a menor unidade que a corretora erra é a mesma unidade em
que o alvo está escrito.

> **Regra:** `sl`/`tp` nativos da corretora garantem que existe proteção, não
> que o preço de saída é o nível pedido — e o erro é sistemático e contra
> você, não aleatório. Meça o preço EXECUTADO contra o nível PEDIDO em pelo
> menos 10 saídas antes de aceitar qualquer alvo pequeno; o alvo mínimo viável
> é o deslize observado mais o custo por ida-e-volta, nunca 1 tick. Com alvo
> de 1 tick o deslize consome o lucro inteiro do trade antes da corretagem;
> com 2 ticks, metade dele. **Meça o alvo e o stop SEPARADAMENTE** — aqui os
> dois andaram em direções opostas (10 de 11 contra no alvo, 5 de 5 nunca pior
> no stop), e um número médio de "deslize de saída" teria escondido as duas
> coisas. E a fonte da medição é o histórico da CORRETORA, não o diário do
> robô: o diário grava a intenção, e a intenção nunca desliza.
> **Pergunte à plataforma nova:** o alvo/stop que ela amarra na posição fica
> RESTING no livro como limite de verdade (entra na fila, só preenche naquele
> preço ou melhor) ou é gatilho varrido a mercado no toque? A resposta muda se
> um alvo pequeno sobrevive fora do backtest — o backtest mede o nível pedido,
> não o que a corretora de fato entrega no gatilho.

### 4.9 Reancoragem que só acontece ao ARMAR deixa o robô mudo pelo resto do pregão — expõe a uma FATIA do dia, não ao dia inteiro

Analisado a semana de 2026-08-31 a 2026-09-04 (tick real MT5, WDO@), robô
`wdo_grid_reload_maker` (WDO F1, `dt-wdo_grid_reload_maker-wdo@-live`/
`-shadow`): o robô fica ATIVO (da 1ª entrada até a última saída) só numa
fração pequena de cada pregão de ~569 minutos.

| Pregão | % do pregão ativo | Trades | Pontos que o mercado andou |
|---|---|---|---|
| 2026-08-31 | 0,0% | 1 | 24,0 |
| 2026-09-01 | 8,0% (45,6 min) | 41 | 64,5 |
| 2026-09-02 | 14,3% (81,6 min) | 63 | 83,5 |
| 2026-09-03 | 11,1% (63,4 min) | 72 | 44,0 |
| 2026-09-04 | 0,0% | 0 | 41,5 |

As 177 entradas da semana couberam em apenas 11 níveis de preço distintos
(≤3 por dia). Em 2 dos 5 pregões (31/08 e 04/09) o robô praticamente não
operou, mesmo o mercado tendo se movido dezenas de pontos nesses dias.
Causa raiz, em `src/strategy/daytrade/lab/wdo_grid_reload_maker.py::on_bar`
(~linha 707-730): no modo `rolling_last_price`, `state.anchor_price` só é
atualizado no INSTANTE em que uma nova ordem-limite é armada — enquanto
existe ordem pendente (`state.pending_side is not None`), o robô só espera,
sem cancelar nem reprecificar. Se o preço se afasta do nível armado e não
volta a tocá-lo, a ordem fica parada indefinidamente e o robô fica mudo
pelo resto do pregão: não existe timeout nem gatilho de deriva de preço
que cancele e rearme a ordem mais perto do preço atual.

Achado ao investigar a mesma semana de dados que motivou o item 4.8
(MFE/MAE por trade) — é um achado NOVO e independente, sobre
atividade/exposição do robô, não sobre deslize de preço.

> **Regra:** um robô do tipo "ordem-limite parada com reancoragem" só
> reflete exposição ao pregão INTEIRO se a reancoragem for CONTÍNUA (a
> cada rearme necessário) — reancorar só uma vez, no momento de armar, faz
> o robô se expor a uma FATIA estreita e arbitrária do range do dia, não
> ao dia inteiro. Backtests que rodam sobre o histórico completo sem
> perceber isso medem um número real, mas não avisam que ele vem de
> pouquíssimos níveis de preço tocados — o robô pode passar pregões
> inteiros inerte sem que nenhuma métrica agregada (líquido, MaxDD, win%)
> denuncie isso.
> **Pergunte à plataforma nova:** a ordem-limite da plataforma reprecifica
> sozinha (ou permite configurar cancelamento por timeout / distância de
> deriva do preço) quando o nível armado não é tocado, ou ela fica parada
> indefinidamente esperando um preço que pode nunca voltar?

### 4.10 Trocar saída MAKER por saída decidida pela estratégia troca o TIPO de execução, não só a regra de preço — 4/4 candidatos de trailing zeraram o capital de teste

Medido no `WdoGridReloadMaker` (WDO F1,
`src/strategy/daytrade/lab/wdo_grid_reload_maker.py`), testando um mecanismo
novo OPT-IN (`trailing_ativo`/`trailing_recuo_ticks`, default desligado,
nunca ativado em produção): em vez do alvo estático de 2 ticks
(`profit_ticks=2`) fechado pelo próprio motor como ordem MAKER
(`target_fills_as_maker=True`, zero deslize), a posição continua aberta e
monitorada tick a tick, fechando via `Exit()` da estratégia quando o preço
recua N ticks do melhor preço alcançado desde que o piso foi batido.
Testados 4 candidatos (recuo tolerado de N=0, 1, 2 e 4 ticks) contra o
baseline estático já em produção (T2/S16), no motor tick completo, com o
capital de teste REAL do WDO@ (R$375,00, mínimo com reserva — nunca um valor
nocional), em DUAS janelas: o IS salvo inteiro (`data/raw_ticks/
WDO_A_f1.parquet`, 72 pregões, 2.832.170 ticks, 2026-02-27 a 2026-06-12) e
uma semana fresca de tick real MT5 (2026-08-31 a 2026-09-04, 552.860 ticks).

Baseline (produção atual, nada mudou aqui): líquido **R$23.954,00** no IS
(93,4% win, 6.322 trades) e **R$4.592,00** na semana fresca (93,8% win,
1.156 trades) — robusto nas duas janelas. Os QUATRO candidatos de trailing
(N=0, 1, 2 e 4) **zeraram a conta de teste de R$375,00 nas DUAS janelas**,
em 1 a 3 pregões dos 72/5 disponíveis (o motor interrompeu cada run ao
detectar patrimônio ≤ 0). Win rate dos 4 candidatos ficou entre **13,6% e
38,9%**, muito abaixo do breakeven de ~88,9% que a razão risco:retorno 1:8
(T2 de lucro / S16 de stop) exige para não perder dinheiro.

Causa mecânica (não é bug de código — é característica estrutural do motor,
`backtest/intraday/machine.py::_close_position`): `is_maker_target = reason
== IntradayExitReason.TARGET and cfg.target_fills_as_maker` — SÓ o
fechamento por alvo ESTÁTICO é isento de slippage. QUALQUER saída decidida
pela própria estratégia via `Exit()` (reason SIGNAL) é SEMPRE executada a
MERCADO, pagando o `slippage_ticks` configurado (1 tick) — a MESMA
penalidade que stop e flatten forçado já pagavam. Substituir um alvo maker
por uma saída dinâmica troca o TIPO de execução (maker, zero custo →
mercado, paga o tick de slippage) mesmo quando a REGRA de preço é idêntica
ou aparentemente melhor — um custo estrutural, não um detalhe, e ainda mais
relevante nesta família porque o lucro por trade já é de só 1-2 ticks.
Contribuiu também o atraso de 1 tick entre decisão e execução (anti-
look-ahead: decisão no tick N só executa na abertura do tick N+1) — medido
explicitamente no candidato N=0 no IS: **47 de 48 trades não-stop fecharam
ABAIXO do piso de 2 ticks** apesar do preço TER alcançado o piso, só 1 além
dele. Esse atraso, somado à autocorrelação lag-1 negativa do tape do WDO@
(-0,44, achado de outra investigação na mesma sessão), devolve mais do que
ganhou na maioria das vezes.

Nenhum dos 4 candidatos foi escolhido (decisão do dono, em aberto) e o
mecanismo continua OPT-IN, desligado por padrão no código — isto não é uma
estratégia refutada e encerrada, é um achado de método sobre custo de
execução que generaliza além deste candidato. Também não testado: se um
capital de teste maior que R$375 mudaria o veredito — a inviabilidade medida
vale para o capital de teste ATUAL.

> **Regra:** antes de trocar uma saída MAKER (ordem parada, sem custo de
> fila) por uma saída dinâmica decidida pela estratégia, verifique que tipo
> de execução essa saída nova vai usar — se ela virar ordem A MERCADO (o
> comportamento mais comum para "saída decidida agora", por ser urgência),
> o custo extra (spread/slippage) tem de entrar na conta do breakeven ANTES
> de comparar os dois desenhos, nunca depois: um mecanismo mais "esperto"
> sobre o PREÇO pode ainda assim perder dinheiro se ele mudar o CUSTO de
> execução por baixo. Vale para qualquer estratégia cujo lucro por trade
> seja pequeno o bastante (poucos ticks) para o custo de execução dominar
> o resultado.
> **Pergunte à plataforma nova:** a saída dinâmica/trailing que esta
> plataforma oferece fecha como ordem PARADA (maker, sem pagar o spread)
> ou A MERCADO (paga o spread/slippage a cada fechamento)? Se a saída
> original que ela substitui era maker, o custo extra por trade precisa
> ser medido e somado ao breakeven antes de decidir se o trailing vale a
> pena.

> **Nota de 2026-09-08 (commit `4eb3e4a`), sobre os números acima:** este item
> foi medido no motor que fechava o alvo maker **de graça**, e a frase
> "`target_fills_as_maker=True`, zero deslize" que aparece na descrição do
> baseline era falsa na corretora — o alvo NÃO fatiado é o `tp` nativo, e ele
> desliza 1 tick contra a posição (item 4.8). O motor agora cobra esse tick, e
> com ele o baseline "R$23.954,00 no IS / R$4.592,00 na semana fresca" some:
> T2/S16 não tem edge (item 6.18). **Duas coisas a preservar deste item mesmo
> assim, e elas ficam MAIS fortes, não menos:** (1) a lição de método —
> "trocar uma saída maker por uma saída a mercado muda o TIPO de execução, e o
> custo entra no breakeven ANTES da comparação" — é exatamente o mesmo
> mecanismo que derrubou o baseline; (2) a comparação trailing-vs-baseline
> tinha um viés que agora é nomeável: ela cobrava do trailing um custo de
> execução que NÃO cobrava do alvo estático. O veredito "4/4 zeraram" não muda
> (win 13,6%–38,9% contra um breakeven que só SOBE quando o deslize é
> cobrado — em dinheiro, de 90,00% para 95,00%, item 6.18), mas o baseline
> contra o qual eles perderam também perde.

### 4.11 Um gate de atividade/liquidez pré-entrada que acelera o preenchimento não virou lucro melhor — medir velocidade não é medir P&L

Testado no `WdoGridReloadMaker` (WDO F1,
`src/strategy/daytrade/lab/wdo_grid_reload_maker.py`), mecanismo novo
OPT-IN (`gate_atividade_ativo: bool = False`, `gate_volume_min: float |
None = None`, `gate_janela_segundos: int = 15`, nunca ligado em produção):
quando ativo, o robô só arma uma NOVA `EnterLimit` (nunca a reancoragem de
uma ordem já pendente) se o volume negociado nos últimos
`gate_janela_segundos` segundos estiver ACIMA de `gate_volume_min`; senão
espera o próximo `on_bar`. Nasceu de uma correlação REAL (Spearman,
sobrevive correção por múltiplos testes, rho≈−0,33, p<0,002, achada por
análise sobre `scripts/daytrade/wdof1_mfe_mae_semana_2026_09_04.py`, 177
trades da semana 2026-08-31 a 2026-09-04): mais volume/volatilidade ANTES
de uma entrada prevê preenchimento MAIS RÁPIDO da ordem-limite — com a
ressalva já conhecida então de que a amostra tinha 0 stops nos 177 trades,
ou seja a correlação era sobre VELOCIDADE de preenchimento, não sobre
QUALIDADE do trade.

Medido agora (`scripts/daytrade/wdof1_gate_atividade_sweep_2026_09_07.py`,
motor tick completo, config de produção T2/S16/x1, capital real de teste
R$375,00) em DUAS janelas, com 3 limiares por janela (percentil 25/50/75
do volume observado NA PRÓPRIA janela, em janelas rolantes de 15s — nunca
chutado):

**IS completo** (`data/raw_ticks/WDO_A_f1.parquet`, 72 pregões — amostra
GRANDE e mais confiável): baseline (sem gate) líquido R$23.954,00, MaxDD
R$1.135,50, win 93,4%, 6.322 trades, lucro/DD 21,10, duração mediana
9,0s. Os 3 limiares testados **pioraram o líquido e o lucro/DD nos TRÊS**,
de forma monotonicamente pior quanto mais alto o limiar: p25 (volume_min
373,0) R$22.661,50 (−5,4%), MaxDD pior (R$1.249,50), lucro/DD 18,14,
6.127 trades (−195); p50 (874,0) R$21.737,00 (−9,3%), lucro/DD 16,17,
5.856 trades (−466); p75 (1.956,0) R$14.889,50 (−37,8%), lucro/DD 11,68,
4.291 trades (−2.031).

**Semana fresca** (tick MT5 real, 2026-08-31 a 2026-09-04, 5 pregões —
amostra PEQUENA, 1.156 trades no baseline): baseline líquido R$4.632,00,
MaxDD R$296,50, win 93,8%, duração mediana 7,9s. p25 (volume_min 559,0)
R$4.826,50 (**+4,2%, único ponto positivo de todo o teste**), win 94,3%,
1.117 trades (−39); p50 (1.362,0) R$4.182,00 (−9,7%), 996 trades (−160);
p75 (2.785,0) R$3.121,50 (−32,6%), 837 trades (−319).

O mecanismo em si FUNCIONA exatamente como a correlação original previa —
filtra por velocidade de preenchimento: na semana fresca a duração
mediana caiu monotonicamente (7,9s→6,9s→5,1s→4,5s) e a fração de trades
rápidos subiu (50,0%→52,5%→57,2%→60,9%) conforme o limiar sobe; no IS o
efeito é mais fraco e não-monotônico (50,0%→51,1%→50,3%→55,3%). Mas
acertar o eixo que a correlação media (velocidade) não fez o outro eixo
(P&L) melhorar — na amostra grande e confiável piorou nos 3 limiares, e o
único ponto positivo veio da amostra pequena e não sobrevive nem ao
segundo limiar (p50) da MESMA janela pequena, então não pode pesar mais
que o resultado do IS. Nota à parte sobre o contador `self.gate_bloqueios`
(soma 1 a cada `on_bar` em que o robô queria armar e foi bloqueado): como
o mesmo sinal represado é reavaliado em TODO tick seguinte até o volume
cruzar o limiar, esse número (28.889/176.079/737.987 no IS para
p25/p50/p75) é muito maior que a redução real de trades executados
(−195/−466/−2.031) — são duas coisas diferentes, não confundir uma pela
outra.

Decisão de produção: o gate continua OPT-IN e DESLIGADO por padrão
(`gate_atividade_ativo=False`) — nenhum limiar foi promovido a vencedor;
ativar (ou não, e com qual limiar) fica com o dono, com estes números na
mão.

> **Regra:** um filtro de atividade/liquidez pré-entrada precisa ter os
> dois eixos medidos SEPARADAMENTE — velocidade de preenchimento E
> resultado financeiro — antes de virar produção. Um filtro pode acertar
> por completo o eixo que a correlação original mediu e ainda assim piorar
> o eixo que importa. E uma amostra pequena pode mostrar o efeito OPOSTO
> de uma amostra grande no mesmo teste: o veredito é o da amostra grande e
> confiável, nunca o da pequena só porque ela bateu positivo primeiro.
> **Pergunte à plataforma nova:** o filtro de atividade/liquidez
> pré-entrada que ela oferece (ou que você vai construir sobre o feed
> dela) foi medido nos dois eixos — velocidade de preenchimento E P&L —
> separadamente, em pelo menos duas janelas de tamanhos diferentes? Se só
> foi medido num eixo, ou só numa janela pequena, ele não está validado
> pra produção.

> **Nota de 2026-09-08 (commit `4eb3e4a`):** os líquidos deste item (baseline
> R$23.954,00 no IS, R$4.632,00 na semana fresca, e os três limiares) saíram
> do motor que fechava o alvo maker **de graça** — a geometria de fundo
> (T2/S16) não tem edge quando o deslize do alvo nativo é cobrado (itens
> 4.8/6.18). O veredito do item, que é RELATIVO (os três limiares pioram o
> líquido e o lucro/DD monotonicamente, e o único ponto positivo veio da
> amostra pequena), não depende do nível do baseline; os valores absolutos,
> sim, e não devem ser citados como resultado do robô.

### 4.12 Contar preenchimento de conta SOMBRA junto com conta REAL inverte o veredito — o filtro por conta vem ANTES de qualquer soma

Investigação de 2026-09-07 sobre por que o backtest divergia da corretora no
pregão de 2026-09-04. Cruzando `live_fills` com `live_orders.account_id`
naquele pregão, os dois lados aparecem separados:

| Conta | Preenchimentos | Idas-e-voltas | Líquido |
|---|---|---|---|
| REAL (`dt-wdo_grid_reload_maker-wdo@-live`) | 2 | 1 | **−R$0,50** |
| SOMBRA (`…-shadow`, toda ordem marcada `"SHADOW — não enviada ao MT5"`) | 34 | 17 | +R$76,50 |

Somados sem filtrar, os mesmos registros diziam **"R$85 bruto, 18
idas-e-voltas, 0 perdedores"** — uma leitura que inverte o veredito por
completo, porque a única operação que envolveu dinheiro de verdade foi
**perdedora** (é a mesma operação do item 4.8, o alvo nativo que deslizou).
Nada estava corrompido no diário: as duas contas estão corretamente
identificadas em `live_orders`, e a soma é que nunca perguntou de quem era
cada linha.

O erro é atraente porque anda na direção que ninguém audita: misturar as
contas **infla** a atividade e **melhora** a taxa de acerto, então o número
resultante parece confirmar o backtest em vez de contradizê-lo. Um erro que
piorasse o número teria sido investigado no mesmo dia.

> **Regra:** qualquer comparação entre backtest e realidade filtra por
> CONTA/MODO antes de contar um único preenchimento — real, sombra e papel
> nunca entram na mesma soma, nem "só pra ter volume de amostra". E a
> conferência é pelo campo de identidade do registro, nunca por sufixo de
> nome ou por convenção de quem escreveu o script: nome é documentação,
> `account_id` é fato.
> **Pergunte à plataforma nova:** cada ordem e cada preenchimento carregam,
> no próprio registro, a conta e o MODO (real / simulado / papel) em que
> foram gerados, de forma que uma consulta separe os dois sem depender de
> convenção de nomenclatura? Se a separação só existe no nome, ela vai ser
> perdida na primeira agregação que alguém escrever com pressa.

### 4.13 O gêmeo em sombra não mede fila — mede sinal. A DIFERENÇA entre ele e o real É a medida da fila

O achado que a separação do item 4.12 revelou, e o mais valioso dos três da
investigação de 2026-09-07. No **mesmo pregão** (2026-09-04), com o **mesmo
sinal**, o mesmo instrumento e a mesma geometria, os dois gêmeos do WDO F1
divergiram em uma ordem de grandeza no que importa: a sombra — que preenche
no toque, sem fila real — fez **17 preenchimentos**; a conta real, que
enfrenta fila de verdade no book, fez **1**.

Essa é a primeira medida REAL da lacuna que a ficha desse robô sempre
declarou faltar medir: a **taxa de preenchimento passivo real**. Até aqui o
projeto só tinha o modelo teórico de fila (item 4.1) e a observação em outro
ativo (12 ordens reais, 0 preenchimentos na PMAM3). Agora existe um número
observado no instrumento que opera hoje — e ele diz que, se a proporção se
sustentar, **todo número de backtest deste robô superestima a atividade real
por cerca de uma ordem de grandeza**, porque o motor preenche no toque.

A honestidade sobre o tamanho da amostra é parte do achado: **n = 1 pregão**.
Isso não calibra um fator de correção; estabelece que a lacuna é grande e
mensurável, e que ela se mede assim. O caminho pra transformar isso em número
confiável é acumular pregões do par real/sombra rodando lado a lado — não
rodar mais backtest.

> **Regra:** um gêmeo em simulação/sombra **não mede fila** — ele mede o
> sinal, com a fila desligada. Por isso ele nunca serve como estimativa do
> real (4.7). O que ele serve, e é a única forma barata de obter isso, é
> **medir a fila por diferença**: mesmo sinal, mesmo pregão, mesmo
> instrumento, dois registros separáveis — e a razão entre os
> preenchimentos dos dois É a taxa de preenchimento passivo que nenhum
> backtest sabe estimar. Rodar o par lado a lado deixa de ser redundância e
> vira instrumento de medida.
> **Pergunte à plataforma nova:** dá para rodar o MESMO sinal
> simultaneamente em conta real e em conta sombra/papel, com os registros
> separáveis por conta (4.12)? Se der, essa diferença é a sua medida de
> fila e ela deve começar a ser acumulada no primeiro dia — não depois de
> alguém desconfiar do backtest.

### 4.14 Reancoragem sem espera mínima persegue o preço e nunca é tocada

A correção do item 4.9 (reancorar a ordem parada quando o preço anda, em
vez de deixá-la parada pra sempre) foi medida como um salto de 10x. Ao
instrumentar o mecanismo em pregão inteiro descobriu-se o contrário do
esperado: reprecificar a cada tick mantém a ordem SEMPRE a 1 tick do
preço, então ela persegue o mercado e quase nunca é tocada. Pregão
2026-03-02, mesma geometria: **5 trades / −R$47,50 sem freio, contra 264
trades / +R$1.078,00 com freio de 10s**. O freio não é custo pago por
segurança — ele RESTAURA a mecânica de ordem parada, que é o robô.

> **Regra:** numa estratégia maker, o que dá o preenchimento é a ordem
> ficar PARADA enquanto o preço vem até ela. Reancorar é para o caso em
> que o preço foi embora de vez, não para acompanhar o passo dele. Uma
> reancoragem sem espera mínima converte silenciosamente uma estratégia
> passiva numa que nunca executa — e o sintoma é "poucos trades", não erro
> nenhum. Toda reancoragem por evento precisa de uma cadência mínima
> explícita, MEDIDA contra a contagem de trades, não só contra o limite de
> taxa (1.18).
> **Pergunte à plataforma nova:** minha ordem em repouso é reancorada por
> evento (a cada negócio) ou por tempo? Se for por evento, qual a cadência
> mínima entre duas reancoragens — e ela foi medida contra a contagem de
> trades, não só contra o limite de taxa?

**Correção aplicada:** `reancora_min_segundos = 10.0` (ligado por padrão)
em `src/strategy/daytrade/lab/wdo_grid_reload_maker.py`, portão duplo em
`_pode_reprecar` (substituição por deriva de preço) e
`_pode_armar_apos_recusa` (rearme pós-recusa, item 3.16); rearme pós-FILL
não é freado, porque é a mecânica normal de reload. Calibrado rodando os
126 pregões inteiros disponíveis: pior minuto máximo de envios = 26 contra
o teto de 30 do item 1.18 (0 pregões travam o freio de cadência); 6s e 15s
travam 2 pregões cada — a relação não é monotônica, porque mudar a
cadência muda QUAIS pregões saturam, não quantos. Risco residual nomeado:
a folga contra o teto do item 1.18 é de só 4 ordens (87% do teto usado), e
`max_trades_per_side` deixou de ser um parâmetro folgado para virar
load-bearing — subi-lo empurra o pico de novo acima de 30. Travado com o
teste `test_max_trades_per_side_continua_em_200`.

**A isenção do rearme pós-fill cobrou em 2026-09-08:** a frase acima ("rearme
pós-FILL não é freado, porque é a mecânica normal de reload") é uma decisão de
desenho que o pregão real desmentiu — 125 ordens para 22 trades, 82 de 124
intervalos abaixo de meio segundo, com o freio de 10s funcionando tick a tick
na janela calma do mesmo dia. Ver item 1.20.

### 4.15 O diário chamava de "alvo" o que a máquina PEDIU, não o que o book ENTREGOU — rótulo por intenção esconde o deslize

Ainda no pregão de 2026-09-08, das 22 saídas do WDO F1: **8 pelo alvo nativo
da corretora** (item 4.8) e **13 fechadas pelo próprio robô a mercado**
(`exit_market` — o desenho adotado depois do incidente de 2026-08-28, que
fecha a mercado inclusive quando o gatilho é o alvo, para nunca depender de
uma ordem que talvez não exista mais). As 13 somaram **−R$70,00** de bruto.
As 22 foram gravadas no diário com o mesmo rótulo: `exit_reason: "target"`.

O rótulo é honesto sobre a INTENÇÃO e mudo sobre o RESULTADO — e nenhuma das
saídas rotuladas "alvo" pagou o nível do alvo: 8 deslizaram (4.8) e 13 saíram
a mercado num preço que ninguém comparou com nada. Enquanto o diário chama
tudo de alvo, a taxa de acerto sobe, o custo de execução some, e o único
número que denunciaria o problema — quanto o preço executado difere do nível
pedido — nunca chega a ser calculado, porque não existe campo onde ele
caberia.

> **Regra:** uma saída só é "alvo" se o preço executado for o nível pedido.
> Todo registro de saída guarda os DOIS — o motivo pretendido e o preço
> realizado contra o nível —, e a diferença tem contagem própria no relatório
> do dia: quantas de quantas saídas deslizaram, quantos ticks cada uma, quanto
> somou em dinheiro. Rotular pelo motivo pretendido em vez do resultado
> observado não é imprecisão de nomenclatura: é o mecanismo pelo qual um custo
> de execução recorrente fica invisível para sempre, porque nenhuma soma o
> procura. Vale igual para o stop — "stop" que executou 3 ticks além do nível
> é stop MAIS deslize, e o segundo pedaço é seu, não do mercado.

### 4.16 Metade das posições reais do robô viveu menos de 1 segundo — round-trip de execução não é trade, e só o relógio da CORRETORA enxerga isso

Das 13 saídas a mercado do item anterior, **11 fecharam em menos de 1 segundo
depois de abrir**: 58 ms, 62 ms, 64 ms, 66 ms, 100 ms, 109 ms, 127 ms, 288 ms,
319 ms, 342 ms e 561 ms. Juntas somaram **−R$40,50** — 34,9% do prejuízo do
pregão (−R$116,00). Todas rotuladas `exit_reason: "target"` (item 4.15): o
diário chama de "alvo atingido" um ciclo de 58 milissegundos que nunca chegou
perto do alvo.

Uma sondagem read-only sobre o histórico de deals da corretora
(`history_deals_get`, campo `time_msc`) mostrou que 2026-09-08 não é um pregão
fora da curva — é o comportamento do robô. Nos três pregões reais que o slot
`dt-wdo_grid_reload_maker-wdo@-live` tem:

| pregão | posições | vida < 1 s | líquido dos < 1 s | líquido do dia |
|---|---|---|---|---|
| 2026-08-28 | 2 | 1 | −R$5,50 | −R$301,00 |
| 2026-09-04 | 4 | 2 | **+R$4,00** | −R$2,00 |
| 2026-09-08 | 22 | 11 | −R$40,50 | −R$116,00 |
| **TOTAL** | **28** | **14 (50%)** | **−R$42,00** | **−R$419,00** |

**Metade de tudo que este robô já fez com dinheiro real — 14 de 28 posições —
nunca foi trade.** E o piso tem de ser de TEMPO, nunca de resultado: a posição
de 288 ms deu **+R$5,00**, e o conjunto dos < 1 s de 2026-09-04 deu **+R$4,00**.
Um round-trip lucrativo continua sendo round-trip. Filtrar por resultado
guardaria os que deram certo e descartaria só os que doeram, que é a definição
de contaminar a amostra.

Uma posição que abre e fecha em 58 ms não expressou tese nenhuma sobre preço —
o preço não teve tempo de andar. O que ela mede é a distância entre o preço que
a máquina achava ter e o preço que o book tinha: é **round-trip de execução**, e
o resultado dela é o custo de estar errado sobre o book, não o resultado de um
trade. Somada junto com os trades de verdade, contamina tudo o que se olha
depois. O tamanho da contaminação em 2026-09-08: com os 11 round-trips dentro, o
pregão mostra **31,8% de acerto (7/22)**; só com os trades de verdade, **54,5%
(6/11)** — **22,7 pontos percentuais** de distorção vindos de objetos que nunca
expressaram tese sobre preço.

**E nem todo relógio serve.** Os três relógios disponíveis foram medidos contra
os MESMOS 11 casos de 2026-09-08:

| relógio | acha quantos dos 11 | patologia |
|---|---|---|
| carimbo de TICK (`entry_ts`/`exit_ts` do trade) | **4 (36%)**, e ainda inventa **1 falso positivo** | anda com a defasagem do feed (24 min naquele pregão): um round-trip de 62 ms aparece como 51,5 s. Deixa passar −R$28,50 |
| relógio de PAREDE do processo (`_on_opened` → `_on_closed`) | **1 (9%)** | abertura e fechamento caem no mesmo passo do poll e a conta dá ~0; e quando o poll trava, dá 3.184 s para uma posição que viveu 456 s |
| relógio da CORRETORA (`time_msc` dos deals) | **11 (100%)** | — |

> **Regra:** todo diário registra a DURAÇÃO da posição (abertura →
> fechamento), e existe um piso abaixo do qual ela não é contada como trade, e
> sim como round-trip de execução — reportado em linha separada, com o custo
> próprio somado. **Essa duração vem do carimbo da CORRETORA, não de nenhum
> relógio do processo.** Relógio de dado (tick/barra) mede a defasagem do feed;
> relógio de parede do laço mede a latência do próprio laço — os dois medem o
> OBSERVADOR, não o observado. Um piso de tempo montado sobre qualquer um dos
> dois erra de 64% a 91% dos casos e ainda produz falso positivo. Onde fica o
> piso é da estratégia (aqui, qualquer coisa muito abaixo do tempo típico entre
> dois negócios do instrumento), mas ele precisa EXISTIR: sem a duração no
> registro, a métrica que denuncia o problema nem pode ser calculada, e o
> sintoma chega disfarçado de "a taxa de acerto caiu um pouco". Um pico de
> posições ultracurtas é alarme de execução, nunca resultado de estratégia.
>
> **Corolário — registrar não é alarmar.** O campo entra no diário como
> OBSERVAÇÃO: carimbo copiado da corretora, que não filtra entrada, não
> dimensiona e não interrompe nada — `live/` continua sem decidir. Onde fica o
> piso do que conta como round-trip é decisão de estratégia/dono, tomada depois,
> com o relógio já validado ao vivo. Alarme montado sobre relógio ainda não
> validado foi exatamente o erro do freio de cadência no mesmo pregão.
>
> **Pergunte à plataforma nova — RESPONDIDA no MetaTrader5:**
> `history_deals_get` devolve `time_msc` em milissegundos e o `position_id`
> amarra entrada e saída, então a vida da posição é a diferença entre o primeiro
> deal de entrada e o último de saída. A pergunta que a medição refinou, e que
> continua aberta para a plataforma da Copa: **quais relógios a plataforma
> oferece, e qual deles é o da CONTRAPARTE?** Um relógio de dado e um relógio do
> meu próprio laço vão parecer plausíveis e medir a coisa errada — 36% e 9% de
> acerto, respectivamente, no único caso em que isso foi medido.

**Implementado (commit `a278447`):** `MT5Broker.deals_for_position` expõe
`time_msc`; `MT5IntradayExecution.vida_da_posicao_ms()` fecha a conta (primeiro
deal de entrada → último de saída, nunca levanta, `None` = "não sei"); e
`IntradayLiveRuntime._on_closed` grava `duracao_corretora_ms` no evento de
fechamento. Só existe em execução REAL — em sombra e em backtest o campo é
`None`, porque não há corretora para carimbar.

### 4.17 Ordem-limite ancorada em preço defasado é ordem a mercado disfarçada — o maker virou taker na ENTRADA

09:00:02 do pregão de 2026-09-08: o robô mandou uma compra LIMITADA a 5.116,0
com o mercado em 5.107 — um limite ACIMA do mercado não fica no livro
esperando, executa na hora como agressor. Preencheu a 5.107,0. A máquina
estava rodando atrasada: a última barra consumida tinha carimbo 14:36:21 UTC
contra um último poll às 15:00:57 — **24 minutos de defasagem** — e ancorou a
ordem num preço que já não existia.

O estrago é maior que a diferença de preço da entrada. Este robô é maker: o
edge inteiro dele, medido em ticks (4.5), é ser preenchido passivamente no
toque enquanto o outro lado cruza o spread. Uma entrada que cruza o spread não
é o mesmo robô com um preço um pouco pior — é o robô SEM o edge, pagando na
entrada exatamente aquilo que a estratégia existe para capturar. E não sobra
sintoma: a ordem foi registrada como limitada, preencheu, e nenhum campo do
diário diz que ela executou como agressora.

> **Regra:** antes de enviar uma ordem-limite, compare o nível dela com o topo
> de livro ATUAL — compra acima da melhor oferta e venda abaixo do melhor
> lance são marketable, e a plataforma vai executá-las a mercado sem
> reclamar. Ordem marketable é recusada ou reancorada, nunca enviada em
> silêncio. E a âncora tem prazo de validade: preço lido minutos atrás não
> ancora ordem nenhuma. Corolário para qualquer estratégia passiva: "fui
> preenchido" não é sucesso — o sucesso é ter sido preenchido SEM cruzar o
> spread, e isso se verifica no registro, não se presume pelo tipo da ordem.
> **Pergunte à plataforma nova:** dá para consultar o topo de livro no
> instante do envio, para recusar um limite marketable antes que ele vire
> ordem a mercado? E o registro do preenchimento diz se a minha ordem foi
> AGRESSORA ou PASSIVA? Sem essa marca, contar preenchimentos conta os dois
> tipos juntos e a taxa de preenchimento passivo real (4.13) não é medível.

### 4.18 Mesmo sinal, mesmo minuto: sombra +R$171,00, real −R$116,00 — R$430,00 de gap de execução num pregão só

Fechamento do pregão de 2026-09-08, WDO F1, os dois gêmeos rodando lado a lado
no mesmo instrumento e nos mesmos minutos:

| Conta | Trades | Líquido |
|---|---|---|
| SOMBRA (preenche NO nível, modelo do backtest) | 48 | **+R$171,00** |
| REAL (fila, deslize e spread de verdade) | 22 | **−R$116,00** |

E o contrafactual sobre os MESMOS 22 trades reais, refeito saída a saída com o
preço que a máquina PEDIU em cada uma: **+R$314,00**, no lugar de −R$116,00.
**R$430,00 de diferença num único pregão, com o sinal idêntico.** O dia bateu
o freio duro de perda (teto R$112,50) e parou.

E não foi um dia ruim isolado. O histórico REAL completo do WDO no terminal
são três pregões, **3 de 3 negativos**: 2026-08-28 −R$300,00 (o incidente da
Parte 0), 2026-09-04 −R$25,00 e 2026-09-08 −R$110,00 de bruto — **−R$435,00**.
No mesmo período, o backtest e a sombra desse robô nunca deixaram de ser
positivos.

Isto fecha com número o que o item 4.13 tinha aberto com n=1 pregão e uma
dimensão só (contagem de preenchimentos). Agora são duas: a sombra preenche
MAIS (48 contra 22) **e** preenche MELHOR (no nível, contra 1 a 2 ticks pior).
A segunda dimensão é a que o projeto não estava medindo, e é a maior das duas
em dinheiro.

> **Regra:** uma estratégia cujo edge É a execução passiva não pode ser
> validada por um backtest que preenche no nível — ele responde uma pergunta
> diferente da que está sendo feita (4.1, 4.7). O único teste que separa
> estratégia de execução é rodar real e sombra com o MESMO sinal, no mesmo
> instrumento e no mesmo minuto, com os registros separáveis por conta (4.12),
> medindo a diferença em DUAS dimensões: quantos preenchimentos cada um teve,
> e a que preço cada preenchimento saiu contra o nível pedido. Enquanto essa
> diferença for da ordem do lucro bruto esperado, nenhum número de backtest é
> evidência sobre o robô — é evidência sobre o sinal, e o sinal não é o que
> está perdendo dinheiro. Corolário de decisão, o mais caro de aprender aqui:
> quando o gêmeo simulado é positivo e o real é negativo pregão após pregão, o
> que precisa mudar é a EXECUÇÃO (ou o instrumento), nunca o parâmetro da
> estratégia — recalibrar geometria contra um backtest que ignora o custo que
> está matando o robô só produz uma geometria mais bem adaptada a um mundo que
> não existe.

### 4.19 Histerese de nível: substituir a ordem sem olhar PARA ONDE ela vai gasta a mesma fila que ela acabou de conquistar

Mesmo pregão de 2026-09-08, mesmo slot `dt-wdo_grid_reload_maker-wdo@-live` do
item 1.20 (que já cobre o RELÓGIO do freio de cadência — este item não repete
aquele, é sobre o DESTINO das ordens que aquele freio deixa passar): o robô
emitiu **125 linhas `LIMITE` para 22 rodadas de entrada — 103 delas
`(substitui)`**. Dessas 103: **65 moveram a ordem exatamente 1 tick**, e **49
devolveram a ordem a um nível que a MESMA rodada já tinha ocupado**. A rodada
#21 é o retrato, tudo no MESMO segundo de parede (15:00:44 UTC):

5105,0 → 5105,5 → 5105,0 → 5105,5 → 5106,5 (preencheu só na 5ª tentativa, com
prejuízo de R$5,50).

Nenhuma dessas substituições era idêntica à IMEDIATAMENTE anterior — a guarda
de no-op do motor (`backtest.intraday.machine._reancoragem_no_mesmo_nivel`)
não tinha o que pegar; o desperdício era voltar a um nível recém-abandonado,
não repetir o nível atual. E o custo não é CPU: cada substituição é um
cancela-e-reenvia REAL na corretora que joga fora a fila já acumulada naquele
nível — num robô maker a fila é o produto. No pior minuto de RELÓGIO DE PAREDE
(item 1.20) essas idas e vindas somaram **64 envios**, mais que o dobro do
teto de 30 de `MAX_ENVIOS_POR_MINUTO`, que não recusa só a ordem — liga
`disaster_halt` e cala o robô pelo resto do pregão (nota 2026-09-08, commit
`da6f89c`: este teto único virou dois níveis — ver item 1.22). Veredito do dono:
"substituiu 3 vezes para o mesmo preço, mesmo stop e mesmo alvo, isso é uso de
recurso desnecessário, neste caso não deve substituir".

> **Regra:** robô que reposiciona ordem-limite precisa de HISTERESE com DOIS
> pontos de referência, não um: o nível novo só vale se estiver a pelo menos N
> ticks do nível PARADO **e** do último nível ABANDONADO na mesma rodada. Sem
> a banda, deriva de 1 tick não é preço andando — é troca de ponta do book
> (bid↔ask), e a ordem persegue o próprio spread. Sem a memória do nível
> abandonado, a banda sozinha não basta: a ordem sai de A, anda a banda
> inteira até B e volta para A, cada perna passando no portão, e o par se
> repete para sempre. A memória é POR RODADA — morre no fill/na recusa, senão
> proíbe o rearme pós-fechamento de voltar ao mesmo nível, que é exatamente a
> mecânica de reload que dá nome a esse robô. Corolário: um freio de CADÊNCIA
> (1.20, 4.14) limita QUANTAS substituições saem por minuto; a histerese de
> NÍVEL limita PARA ONDE elas vão — são portões ortogonais, e um sem o outro
> deixa passar exatamente o padrão que o outro não enxerga.

**Correção aplicada** (2026-09-08, mesmo dia): `WdoGridReloadMaker.
reancora_min_ticks` passou de 1 (histerese desligada) para 2, e
`_pode_reprecar` passou a comparar o nível candidato contra os dois pontos de
referência (nível parado e último nível abandonado na rodada). Mora em
`strategy/` — vale idêntica no backtest e ao vivo, por construção. No replay
da sequência de níveis registrada nesse pregão: **125 envios → 53**, e o pior
minuto de parede **64 → 21** (30% de folga abaixo do teto de 30).
`reancora_min_ticks=1` continua existindo só como baseline de medição, nunca
como configuração de operação.

**Risco residual nomeado dentro do próprio item:** a histerese é MITIGAÇÃO do
problema do relógio (1.20), não fechamento — um mercado que ande em linha reta
gera substituições legítimas na mesma velocidade do reprocessamento de fila
atrasada, e pode reencontrar o teto de 30. As duas saídas conhecidas estão
documentadas na docstring de `live.intraday_runtime._check_cadencia_de_ordens`:
(a) o runtime entregar à estratégia um carimbo de parede (o que faria a
decisão deixar de ser função só do OHLCV, exigindo relógio também do lado que
vai ser portado para MQL5); (b) coalescer, dentro de um passo do supervisor,
as `LimitPlaced` que a própria máquina já superou (o que muda o que a
corretora PODE executar, porque uma ordem intermediária poderia ter preenchido
antes de ser cancelada — isso é `live/` decidindo, não só relendo relógio).
Nenhuma foi implementada — as duas mexem em regra estrutural e esperam decisão
do dono.

> **Pergunte à plataforma nova:** cancelar e reenviar uma ordem-limite faz
> perder a posição na fila do book? Existe modificação de preço IN-PLACE que
> preserve prioridade? E qual é o teto de ordens por minuto da plataforma —
> medido em que relógio? (1.20)

### 4.20 A ENTRADA por ordem-limite NÃO desliza — 0 de 28 contra a posição, e é esse contraste que valida a medição da saída

Mesma metodologia do item 4.8 (reconstrução de `history_orders_get` +
`history_deals_get` do terminal, pareando `deal.order` → `order.price_open` =
nível PEDIDO contra `deal.price` = preço EXECUTADO), aplicada agora ao lado da
ENTRADA. População: janela 2026-08-20 a 2026-09-09, símbolos WDOU26 e WDOV26,
magic 862399285, robô `wdo_grid_reload_maker` — os 3 pregões em que ele mandou
ordem real (2026-08-28, 2026-09-04, 2026-09-08), **30 entradas, 28 delas por
ordem-limite pendente** (17 BUY_LIMIT + 11 SELL_LIMIT).

| deslize da ENTRADA (ticks, **+ = A FAVOR**) | 0 | +1 | +2 | +6 | +18 |
|---|---|---|---|---|---|
| n | 23 | 2 | 1 | 1 | 1 |

**A favor 5 · exato 23 · CONTRA 0.** Excluindo os dois casos de causa conhecida
(+6 e +18 são ordem-limite armada em preço morto — item 4.17, não deslize de
execução): **n=26, média +0,154 tick, mediana 0,0, desvio 0,464, 25 de 26
exatas (96,2%), ZERO contra.** Duas dessas ordens ficaram **240 s e 1.453 s
(~24 min) paradas na fila** e ainda assim preencheram exatamente no nível
pedido — o *resting* real não degradou o preço.

O contraste com a SAÍDA pelo alvo nativo é o ponto do item. Mesma população,
mesma metodologia, mesmo instrumento, mesmos pregões:

| lado | mecanismo | n | a favor | exato | contra |
|---|---|---|---|---|---|
| ENTRADA | ordem-limite pendente, *resting* no livro | 28 | 5 | 23 | **0** |
| SAÍDA | `tp` nativo, gatilho varrido a mercado (4.8) | 11 | 0 | 1 | **10** |

Fisher exato bilateral: **p ≈ 1,7 × 10⁻⁸**. Não são duas amostras do mesmo
fenômeno com sorte diferente — são dois mecanismos.

**Ressalva honesta, que faz parte do achado:** 3 pregões, 1 contrato, 28
entradas, 23 delas de um único dia. A DIREÇÃO (0 contra em 28) é forte;
**"nunca desliza" NÃO está provado** — pela regra dos três, o limite superior
de 95% para a taxa de preenchimento adverso ainda é **10,2%**.

**Consequência de desenho, que é por que isto virou item.** A pergunta do dono
no mesmo dia: valeria ancorar alvo e stop no preço REALMENTE preenchido, em vez
do nível pedido, como é hoje? A resposta é não, e o motivo é este número.
(a) Não existe deslize de entrada para corrigir. (b) Nos ~15% de fills
FAVORÁVEIS a mudança PIORA a geometria nas duas pontas: com âncora no nível, um
fill 1 tick melhor deixa o alvo a 3 ticks efetivos (pedido: 2) e o stop a 15
(pedido: 16) — ganha mais quando ganha e perde menos quando perde. Ancorar no
fill devolve exatamente esse ganho ao mercado. Houve UM caso (2026-09-08
12:00:02, fill 18 ticks melhor) em que a âncora no nível fez o stop nascer JÁ
VIOLADO, do lado errado do preço — mas a causa é a ordem armada em preço morto
(4.17), tratada na raiz pelo `MAX_ATRASO_PARA_ORDEM_SEGUNDOS` (commit
`60034e3`), não pela escolha de âncora.

**E o fill favorável não é presente.** As 5 posições com entrada melhor que o
nível foram fechadas pelo próprio robô NO MESMO SEGUNDO, por saída a mercado
(`reason=EXPERT`) — **todas negativas**. O ganho nominal de R$20,00 da
população limpa virou prejuízo por reversão imediata. O mecanismo é direto: ser
preenchido MELHOR que o nível significa que o mercado já passou do nível — o
estado da grade estava velho (4.17 em versão branda), e o que se ganha em
preço de entrada se perde na tese. São os round-trips de execução do item 4.16,
vistos pelo outro lado.

> **Regra:** ordem-limite parada no livro e gatilho varrido a mercado são
> mecanismos DIFERENTES de preenchimento e não podem herdar a mesma premissa
> num modelo de custo. Quem FORNECE liquidez preenche no nível ou melhor; o
> alvo/stop nativo, que a corretora executa como gatilho, preenche pior. Meça
> cada lado separadamente, contra a MESMA população — foi essa separação que
> mostrou que o motor dava o alvo de graça (6.18) sem estar errado na entrada,
> e um número único de "deslize" teria diluído os dois. Um modelo que trata
> "limite" como uma coisa só erra num dos dois lados por construção, e o erro
> tem o tamanho do edge inteiro. Corolário de desenho: enquanto o lado que não
> desliza tiver fills FAVORÁVEIS, reancorar a geometria no preço executado
> devolve esse ganho — a âncora certa é o nível PEDIDO. Stop que nasce violado
> é sintoma de âncora defasada (4.17), nunca argumento contra a âncora no
> nível. E o corolário de amostra: 0 em 28 estabelece DIREÇÃO, não ausência —
> escreva o limite superior junto do zero, sempre.
> **Pergunte à plataforma nova:** a ordem-limite dela, quando fica de fato
> parada no livro, preenche no nível pedido ou melhor — e isso foi medido
> SEPARADAMENTE do alvo/stop nativo, na mesma população? (pergunta 63)

### 4.21 O motor não tinha fila do lado da SAÍDA, e o estouro de prazo (TTL) saía a mercado mas era precificado como maker — dia real: backtest previa +R$36,00, saiu −R$14,00; 1 de 7 preenchimentos (14%) contra 92,8% calibrado

2026-09-09, primeiro dia do WDO F1 T2/S6 ao vivo com dinheiro real, saída
fatiada (item 6.19): **7 saídas por alvo no pregão, UMA preencheu como
ordem-limite, seis estouraram `exit_ttl_bars=60` e saíram a mercado.** O
backtest da mesma geometria previa **+R$36,00** no dia; o dia deu **−R$14,00**.
A tabela que calibrou `exit_ttl_bars=60` (item 6.20, DESFECHO) dizia **92,8%**
de preenchimento; o real deu **14% (1/7)**.

Dois defeitos, não um:

**(a) `IntradaySessionMachine` não tinha NENHUM modelo de fila do lado da
SAÍDA.** Bastava o preço TOCAR o nível e haver volume na barra para a fatia
preencher. O lado da ENTRADA já tinha esse modelo (`queue_ahead_qty`, item
4.1, criado em 2026-08-26 depois do achado da PMAM3: 12 ordens reais, 0
fills, contra 7 trades do gêmeo em sombra no mesmo pregão). Ninguém varreu o
outro lado da mesma operação — um mês inteiro entre corrigir um lado e
descobrir o outro. É o item 7.1 cobrando de novo, e cobrando da MESMA
operação (entrada e saída de um round-trip), não de um módulo qualquer
lembrado por analogia.

**(b) A fatia que ESTOURAVA o prazo era fechada a mercado mas caía no ramo
`is_maker_target` e saía exatamente no preço de fechamento da barra, sem
pagar `slippage_ticks`.** O motor dava de graça justamente a saída que, ao
vivo, acontece em 6 de 7 casos. Mesma família do item 5.20 (o desmonte de
robô que creditava BRUTO pela rota administrativa): o custo de fechar a
mercado existe nas duas rotas ou em nenhuma — aqui as duas rotas eram a mesma
função, e uma delas se disfarçava de maker por causa do rótulo herdado
(`is_maker_target`), não do mecanismo real de preenchimento.

**O que a medição deu depois de corrigir os dois** (IS 72 pregões + OOS 51,
capital real R$375, T2/S6, 12 células, 149 min de máquina):

| motor | IS (72 pregões) | OOS (51 pregões) |
|---|---|---|
| SEM fila de saída (o que vinha decidindo tudo) | **+R$244.429** · 0/72 sem trade | **+R$148.760** · 0/51 sem trade |
| COM fila de saída (400 contratos) | **−R$226 a −R$250 em TODAS as células** · 71/72 sem trade, caixa mín. R$124–148 | **idem** · 50/51 sem trade |

O caixa mínimo (R$124–148) fica **abaixo da margem crua de R$150** — o robô
morre de caixa, a mesma catraca de ruína do item 6.15.

As duas células com n grande o bastante para dizer algo (IS, `ttl=240`,
n=2.741 e n=4.920): R$/trade = **−R$0,086** e **−R$0,050**. Somando de volta a
corretagem de R$0,50/round-trip, o BRUTO por trade é **+R$0,41** e **+R$0,45**
— **o edge existe e é menor que a corretagem**, a mesma assinatura do item 4.5
(edge sub-tick) vista em reais.

Aumentar o prazo de 60 para 240 barras subiu a taxa de fill de ~48% para ~77%
— a suspeita do dono sobre o prazo ser curto estava certa — **mas os fills a
mais não viraram dinheiro.** Posicionar a saída no FILL da entrada em vez de
no toque não resgatou: sem diferença consistente de sinal entre as duas
mecânicas.

**A profundidade real do livro do WDO@**, coletada no mesmo dia (4.393 fotos,
16h05–18h32, regime dominante de spread 1 tick):

| nível | venda | compra |
|---|---|---|
| 1º | 338 | 320 |
| 2º | 596 | 627 |
| 3º | 646 | 683 |

Com alvo de 2 ticks, no instante do fill da entrada o alvo é o **2º NÍVEL** —
~596 na frente, quase o dobro do 1º nível. A hipótese de que chegar cedo pega
uma fila menor é **FALSA**; o que chegar cedo compra é estar na fila enquanto
ela encolhe de 596 para 338, e uma foto estática não distingue "cancelaram na
minha frente" de "chegou gente nova depois".

Isso fecha, com resposta ruim, o risco 3 deixado aberto pelo item 6.19 ("a
fila REAL de saída nunca foi medida... é a mesma classe de suposição que o
item 6.18 pegou do outro lado") — e **invalida a tabela de calibração do item
6.20**: as taxas de fill de 84,1%/88,9%/92,8%/93,6% que escolheram
`exit_ttl_bars=60` saíram do motor SEM fila de saída, o mesmo motor que este
item mostrou dar de graça o preenchimento. A calibração de `exit_ttl_bars`
precisa ser refeita sobre o motor COM fila — e o resultado acima já antecipa
que ela não vai salvar a geometria: mais prazo compra taxa de fill, não
compra sobrevivência de caixa nem edge acima da corretagem.

> **Regra:** um simulador de execução tem DOIS lados, e corrigir o realismo
> de UM deles não corrige o outro — toda premissa de preenchimento tem de ser
> auditada na ENTRADA e na SAÍDA, com a mesma severidade, mesmo quando as duas
> pertencem à mesma posição e ao mesmo commit de correção. Corolário, que é o
> que mais custou aqui: quando um mesmo `motivo de saída` esconde dois
> caminhos que pagam custos diferentes (preencheu no nível × desistiu e foi a
> mercado), o simulador precisa DISTINGUI-LOS — a mistura entre eles não é
> constante, ela depende exatamente do parâmetro que se está calibrando
> (aqui, o prazo). Calibrar um prazo com um modelo que dá o fill de graça mede
> o modelo, não o mercado.
>
> **Nota de método:** uma taxa de fill medida num simulador sem fila NÃO é uma
> previsão — é uma tautologia: ela só repete a regra de preenchimento que o
> próprio simulador usa. A única medição que vale é a do extrato.
> **Pergunte à plataforma nova:** pergunta 24 (estendida) e pergunta 32
> (estendida). (4.1, 4.8, 5.20, 6.15, 6.19, 6.20, 7.1)

### 4.22 A fila da ENTRADA existia no motor havia um mês e nunca foi LIGADA — ficou no default `0.0`, e o motor previa **+R$3,82 por operação** num pregão real que deu **−R$3,00**

Irmão do item 4.21, e a outra metade da mesma história. Lá o defeito era uma
fila que **nunca foi escrita** (lado da SAÍDA). Aqui é pior de uma forma
específica: a fila do lado da ENTRADA **foi escrita, tem docstring, tem
parâmetro — e nunca foi ligada em lugar nenhum**.

`IntradayBacktestConfig.queue_ahead_qty` nasceu em 2026-08-26, logo depois do
caso PMAM3 do item 4.1 (12 ordens reais, ZERO preenchimentos, contra 7 trades
do gêmeo em sombra no mesmo pregão, mesmo ativo, mesmos preços). Em 2026-09-09
descobriu-se que **nenhum ponto do repositório jamais atribuiu valor a ele**:
ficou no default `0.0` por um mês inteiro. Toda medição de robô maker feita
nesse período encheu ordem de entrada no **primeiro toque do nível, de graça** —
exatamente o defeito que o parâmetro foi criado para consertar.

**Um parâmetro de realismo desligado é pior do que a ausência dele**, porque a
existência do parâmetro (com nome, docstring e teste) dá a impressão de que o
risco está coberto. Ninguém volta a perguntar sobre uma pergunta que parece
respondida.

**A aferição contra o extrato.** WDO@ / WDOV26, pregão de 2026-09-09, magic
862399285, robô rodando continuamente das 14:47 às 18:03: **34 operações,
líquido −R$102,00, −R$3,00 por operação, 33,3% de preenchimento, 7 stops.**
Simulando o mesmo trecho com T2/S6 e prazo 60:

| configuração do motor | trades | R$/trade | fill% |
|---|---|---|---|
| **REAL (extrato da corretora)** | 34 | **−3,00** | 33,3 |
| sem fila nenhuma — o motor que decidia tudo até 2026-09-08 | — | **+3,82** | 97,8 |
| só fila da SAÍDA, Q=400 chutado (item 4.21) | 63 | −0,50 | 44,4 |
| **as duas filas calibradas (438 entrada / 489 saída)** | 42 | **−3,48** | 44,1 |

O motor sem fila não errava a magnitude: **errava o SINAL.** Previa
+R$3,82/operação num dia que deu −R$3,00.

**O efeito numa decisão desta mesma sessão.** Com a fila de entrada em zero, a
varredura "sem prazo" dava **+R$506,50** para o T2/S6 no pregão de hoje. Com a
fila ligada, a MESMA célula dá **−R$239,00**. O lucro inteiro vinha de entradas
que a vida real não teria preenchido.

#### O viés de sobrevivência na estimativa da fila

Esta é a lição de método do item, e ela vale muito além do caso. A primeira
estimativa de Q usou só as ordens-limite que **preencheram**: mediana 374 na
saída, 346 na entrada. Está errada, e erra **sempre para o mesmo lado**: ordem
que preencheu é ordem que **ganhou** a fila. As que não preencheram tinham fila
maior e foram jogadas fora — censura à direita clássica, o mesmo erro de quem
estima a vida média de um equipamento olhando só os que já quebraram.

Refeito com **Kaplan-Meier**, no eixo "volume acumulado negociado no nível":

| lado | esperaram | preencheram (evento) | canceladas (censuradas) | **KM mediana** | ingênua | quartil 1 |
|---|---|---|---|---|---|---|
| ENTRADA | 67 (de 186 ordens) | 30 | 37 | **438** | 346 | 194 |
| SAÍDA | 25 (de 34 ordens) | 8 | 17 | **489** | 374 | 207 |

A estimativa ingênua subestima a fila em **21% na entrada e 31% na saída** — e
subestimar fila é exatamente o erro que faz o backtest preencher o que a vida
real não preenche.

**O método da medição, escrito para ser refeito em qualquer plataforma:** a
corretora informa o instante em que a ordem-limite entrou no livro e o instante
em que preencheu ou foi cancelada; a série de negócios informa preço e volume.
`Q_frente` = volume que negociou **no preço da ordem** entre esses dois
instantes. Ordem que preencheu em menos de 0,5 s é descartada — já estava
agressiva ao postar e nunca entrou em fila (item 4.17).

#### Um refinamento MEDIDO E REFUTADO — não refaça

Hipótese plausível: só o volume do **agressor do lado contrário** consome a
nossa fila (uma limite de venda parada na oferta só é executada por quem compra
agredindo). Se fosse verdade, o motor estaria descontando fila **duas vezes**
mais rápido do que deveria, e a calibração inteira estaria pessimista.

Medido: no dia inteiro o fluxo é 50,1% comprador / 50,1% vendedor, mas **no
nível da nossa própria ordem 99,3% do volume é do lado que executa contra nós**.
Faz sentido a posteriori — a nossa limite está na melhor oferta, então negócio
naquele preço é, por definição, alguém agredindo a nossa ponta. **O motor já
está certo ao descontar o volume inteiro da barra.** Refutado em 2 minutos,
nenhuma mudança de motor necessária.

#### As limitações, que fazem parte do achado

**Um pregão só.** A contagem de operações simuladas ainda fica ~30% acima da
real (42 contra 34). E o par que melhor encaixou no dia (`Q_saída=600`) foi
escolhido **depois** de ver o resultado — isso é ajuste, não validação; por isso
o valor adotado é o **489 do Kaplan-Meier**, estimativa com método, e não o que
melhor encaixa em n=34. Cada pregão real novo quase dobra a amostra da saída.

#### E a produção mudou no MESMO dia: a fatia de saída passou a rodar SEM PRAZO

Ordem do dono, ainda em 2026-09-09 (`EXIT_TTL_BARS_SEM_PRAZO`). Duas
consequências sobre a própria medição acima, e as duas são lição de método.

**A calibração do LIVRO sobrevive à troca de mecanismo; a do MECANISMO morre
junto.** Q é propriedade do livro — quantos contratos estão na frente da nossa
ordem naquele preço não muda porque *nós* desistimos depois de 22 segundos.
Os 438/489 continuam valendo. Já a derrapagem do estouro de prazo (as 18 saídas
a mercado de 2026-09-09, única observação com dinheiro real daquele caminho)
deixa de ser medível — **e deixa de importar, porque o robô parou de pagá-la.**
Antes de lamentar a perda de uma amostra, pergunte se o custo que ela media
ainda existe.

**O prazo curto era o que ESTRAGAVA a medição, não o que a permitia.** Das 25
ordens de saída do pregão, **17 saíram censuradas** — canceladas pelo prazo
(~22 s) antes de sabermos a fila delas. Foi exatamente isso que obrigou ao
Kaplan-Meier. Sem prazo, essas observações correm até o preenchimento e viram
**eventos**: a mesma quantidade de operações passa a dar uma estimativa muito
mais firme.

> **Regras** (quatro, e as quatro valem em qualquer corretora e qualquer
> linguagem):
>
> **1. Parâmetro de realismo que nasce desligado é dívida, não proteção.** Ao
> criar um, ou ele já entra ligado com um valor MEDIDO, ou existe um teste que
> FALHA enquanto ele estiver no default neutro. Um default neutro silencioso é
> um subsídio do simulador com aparência de rigor (item 3.8, "parâmetro de
> segurança opcional é parâmetro desligado", agora do lado da MEDIÇÃO em vez do
> lado da execução).
>
> **2. Fila estimada só com as ordens que preencheram é viés de sobrevivência.**
> As que NÃO preencheram são observações **censuradas**, não lixo: entram na
> estimativa pelo tempo/volume que esperaram sem completar. Kaplan-Meier (ou
> qualquer estimador que aceite censura) em vez de mediana das completas. Vale
> para qualquer coisa que se estime a partir de tentativas com desfecho
> incompleto — tempo até preencher, tempo até tocar, tempo até quebrar.
>
> **3. Backtest maker nunca aferido contra o extrato é hipótese, não previsão.**
> E a aferição mínima é **por operação** — R$/operação e taxa de
> preenchimento —, nunca pelo líquido agregado: o líquido esconde compensação
> entre preço e quantidade, e foi justamente onde o motor errou o sinal
> enquanto acertava a ordem de grandeza.
>
> **4. Um mecanismo que desiste cedo CENSURA a própria medição.** Quem mede
> fila precisa saber se o número pequeno que observou é *fila pequena* ou
> *paciência pequena* — as duas produzem a mesma observação curta e significam
> o oposto. Corolário prático: curvas de sobrevivência de pregões COM prazo e
> SEM prazo não se misturam numa estimativa só sem declarar o regime, porque a
> natureza da censura é diferente. E, ao trocar o mecanismo, separe o que a
> medição dizia sobre o MERCADO (sobrevive: a fila é do livro) do que ela dizia
> sobre o CAMINHO escolhido (morre junto, e não faz falta — ninguém mais paga
> aquele custo). É o item 6.19 outra vez, agora aplicado à AMOSTRA em vez de ao
> custo.
>
> **Pergunte à plataforma nova:** pergunta 80 (nova) e pergunta 24 (estendida).
> (3.8, 4.1, 4.17, 4.21, 6.19, 6.20, 7.1)

**A terceira reincidência do item 7.1, na mesma operação.** O padrão "modelo de
fila ausente/desligado" foi corrigido na ENTRADA em agosto (4.1), descoberto na
SAÍDA na manhã de 2026-09-09 (4.21), e descoberto **de novo na ENTRADA — que já
estava "corrigida" — na noite do mesmo dia** (este item). Não são três módulos
distantes lembrados por analogia: são as duas pontas do MESMO round-trip do
MESMO robô. Corrigir uma instância de um padrão sem varrer todas as outras não
corrige o padrão; e "já corrigimos isso" precisa significar *"medi que está
LIGADO"*, não *"o código existe"*. Isso também invalida, pela segunda vez, a
tabela de calibração de taxa de preenchimento do item 6.20 — que o 4.21 já tinha
invalidado pelo lado da saída.

### 4.23 `anchor_exits_at_fill` é silenciosamente inerte para entrada a mercado

Em 2026-09-10, um teste rodou uma estratégia de entrada A MERCADO com
`anchor_exits_at_fill=True` e com `False`. As 16 células saíram byte a byte
idênticas. A causa mora no motor: a flag só é lida num único ponto
(`machine.py`, dentro de `_niveis_da_entrada`), e essa função tem um único
chamador — o caminho de preenchimento de `EnterLimit`. `_entrar_a_mercado`
abre a posição com `initial_stop`/`initial_target` direto e nunca passa por
ali. Ligar a flag numa estratégia que entra a mercado não dá erro, não avisa
e não muda nada.

Reimplementando a ancoragem à mão no caminho de mercado (translação de stop e
alvo pelo delta fill − sinal), o breakeven empírico das células saiu de
39,6%–43,9% para 71,2%–82,2% (perto do 80% nominal, sem o ruído do gap) e o
R$/operação caiu de +R$20,14 para +R$8,59 numa célula e de +R$16,69 para
−R$2,74 na outra: metade do "edge" aparente numa célula, e a totalidade dele
na outra, era só o descasamento entre o preço do sinal e o preço do fill.

> **Regra.** Parâmetro de realismo tem de valer em TODOS os caminhos de
> execução, ou recusar explicitamente os que não cobre. Um flag que é no-op
> silencioso para uma classe de ordem é um default zero disfarçado — mesma
> família do item 3.8 e do item 4.22, agora achada num terceiro lugar do
> mesmo motor. Ao adicionar ou revisar qualquer parâmetro de fidelidade,
> enumere os caminhos de execução (ordem a mercado, ordem-limite, saída por
> prazo, achatamento de fim de pregão) e confirme, um a um, que o parâmetro é
> consultado — ou que o motor levanta erro quando pedem para ligá-lo onde ele
> não vale.
>
> **Pergunte à plataforma nova:** pergunta 84 (nova).
> (3.8, 4.22)

### 4.24 Nunca entrar a mercado, nunca sair no alvo a mercado — ordem do dono, e toda medição obedece

**Este item vem de ordem direta do dono (2026-09-10), não de uma observação —
e é o mais importante desta leva.** Ele constatou que uma rodada inteira de
pesquisa — cinco setups públicos (Wyckoff/SMC, IFR2 do Stormer, pullback na
VWAP, Setup 123/Ross, Ondas de Wolfe), ~50 células ao longo de dias — foi
medida com `Enter` (entrada A MERCADO) e `target_fills_as_maker=False` (alvo a
mercado). **Esse desenho não tem caminho de execução real neste projeto.** O
motor recusa de propósito: `EntradaAMercadoNaoSuportada` (`machine.py`, no
caminho de `_entrar_a_mercado`), cujo comentário diz que falhar alto ali é
melhor que simular o fill a mercado com o open da barra e mandar dinheiro real
contra um preço inventado. Só `EnterLimit` tem caminho confirmado pela
corretora.

A mesma falha atingiu a ORB, a única candidata viva da rodada e a que produziu
o primeiro veredito POSITIVO da investigação — ela também entra a mercado:
mesmo se tivesse sobrevivido à validação, não teria como operar.

**Por que a proibição existe, com os números que a sustentam.** O alvo a
mercado (`tp` nativo, gatilho varrido) foi medido em execução real: n=11
saídas, média **−1,000 tick**, **10 contra a posição e ZERO a favor** (sob
moeda justa, p ≈ 0,001), R$ 55,00 de deslize contra R$ 95,00 de bruto teórico
— **57,9% do lucro** (item 4.8). Com alvo de 2 ticks o breakeven sobe de
90,00% para 95,00% e o robô sai do ar em poucos pregões partindo do capital
real (item 6.18). Trocar o alvo nativo por ordem-limite real parada no livro
(saída fatiada) faz o custo sumir por construção — derrapagem é "executou pior
do que pedi", e ordem-limite recusa pior (item 6.19).

> **Regra — quatro pontos; o 1º e o 4º são o que este item acrescenta:**
>
> **1. Entrada por ordem-limite, nunca a mercado.** Uma estratégia que só faz
> sentido entrando a mercado é uma estratégia que este projeto não pode
> operar — medi-la é tempo de máquina gasto respondendo a uma pergunta que
> ninguém tem.
>
> **2. Alvo por ordem-limite parada no livro (saída fatiada), nunca gatilho a
> mercado.** Sair no alvo a mercado consome o lucro inteiro e aumenta a
> incerteza da medição ao mesmo tempo (itens 4.8, 6.18, 6.19).
>
> **3. Níveis ancorados no FILL, não no sinal.** Se o preço deslizou entre a
> decisão e o preenchimento, stop e alvo acompanham o preço realmente obtido —
> é o item 4.23 do outro lado: a mesma ancoragem precisa valer em TODO caminho
> de execução.
>
> **4. Exceção única: o STOP continua a mercado.** Proteção não espera fila, e
> ele não desliza como o alvo — medido em 5 de 5 saídas reais, nunca pior que
> o nível pedido (item 4.8).
>
> **A lição de método, que é o que sobrevive à troca de plataforma:** o custo
> de execução não é um detalhe a acertar depois que a estratégia "funcionar"
> — ele determina QUAIS desenhos existem. Semanas de pesquisa foram gastas
> varrendo parâmetro de um desenho de execução que a corretora não aceita, e
> nenhum resultado daquela varredura — positivo ou negativo — respondia à
> pergunta que importava. Antes de varrer parâmetro de estratégia, congele o
> desenho de execução e confirme que ele tem caminho real confirmado. Se o
> motor recusa aquele caminho em produção, ele tem de recusar no backtest
> também, ou no mínimo carimbar a linha — um backtest capaz de simular o que
> a produção proíbe é uma máquina de gastar tempo.
>
> **Pergunte à plataforma nova:** pergunta 85 (nova).
> (4.8, 4.23, 6.18, 6.19)

### 4.25 O motor avisa quando RECUSA uma ordem e não avisa quando ela EXPIRA — 14 de 72 pregões em silêncio, e a defesa certa já existia no repo — CORRIGIDO 2026-09-10

Medido em 2026-09-10 numa estratégia ORB de laboratório: **14 dos 72 pregões
do IS (19,4%) passaram inteiros sem nenhuma operação**. Não por falta de sinal
— o sinal estava lá. A ordem-limite de ENTRADA dela expirava por prazo
(`ttl_bars`), o motor a retirava do livro, e **a estratégia nunca era
avisada**. Ela guardava `_armou_hoje = True`, seguia acreditando ter ordem
parada no livro, e não agia mais até o fim da sessão.

A causa é uma assimetria no contrato motor↔estratégia
(`src/backtest/intraday/machine.py`):

| evento | onde | avisa a estratégia? |
|---|---|---|
| ordem morre por **recusa** (teto de contratos / capital) | linhas 1210 e 1620 | **SIM** — `strategy.on_order_rejected(ts)` |
| ordem-limite morre por **prazo** (`ttl_bars`) | linhas 1623-1628 | **NÃO** — `resting_limit = None` e `events.append(LimitCancelled(..., reason="ttl"))` |

O ramo do prazo registra o evento no log do motor e segue adiante. São os dois
únicos pontos em que `on_order_rejected` é chamado no repositório inteiro, e os
dois são recusa. **O motor avisa quando recusa e não avisa quando expira.**

**O que o conserto valeu.** Fazendo a estratégia detectar sozinha — contando as
barras desde que armou e concluindo por conta própria que a ordem morreu quando
passa do prazo:

| | antes | depois |
|---|---|---|
| operações em 72 pregões | 58 | **72** (todo pregão opera) |
| líquido | +R$1.236,00 | **+R$1.649,00** (+R$413,00, **+33%**) |
| win% dos trades recuperados | — | **57,1%** (contra 56,9% dos 58 que já existiam) |

O win% dos 14 recuperados praticamente igual ao dos 58 antigos é o número que
fecha o argumento: **não havia seleção adversa.** Os dias em que a primeira
ordem morria não eram dias ruins — o robô simplesmente não estava lá.

**Por que é pior ao vivo do que no backtest.** Um robô que cala não gera erro,
não gera alerta e não muda nada no painel: a tela mostra ele rodando
normalmente. Falha que se parece com inatividade é a mais difícil de notar. No
backtest custa um trade; ao vivo custa um pregão inteiro ocioso com o dono
achando que tem ordem no livro.

**É a TERCEIRA aparição desta família.** O item **1.14** (incidente WDO F1,
2026-08-28) é o primeiro: 20 de 20 recusas por capital amostradas deixavam o
robô mudo pelo resto do pregão — foi exatamente para isso que o hook
`on_order_rejected` nasceu. O hook fechou o caminho da recusa e deixou aberto o
caminho do prazo, que ninguém tinha percebido ser um caminho separado.

**A varredura do repo — e ela é metade da lição.** Dos 9 robôs que armam ordem
de entrada:

| robô | prazo na entrada | o que trava o rearme | exposto |
|---|---|---|---|
| `CopaWin` (produção) | SIM (`entrada_ttl_barras=5`) | `self._espera` | **NÃO — imune** |
| `WdoGridReloadMaker` (produção) | não | `pending_side` | não hoje, **latente** |
| `Gremah` (produção) | não | — | não |
| 6 outros de laboratório | não | — | não |

O ponto que importa: **a `CopaWin` já se defendia sozinha**, e ninguém tinha
copiado a defesa. Em `copa_win.py` (linhas ~712-718) ela incrementa
`self._espera` a cada barra e, ao chegar em `entrada_ttl_barras`, zera o
contador e libera o rearme — **sem depender de aviso nenhum do motor**. A
solução certa já estava escrita no repositório, num robô de produção, e a ORB
foi construída sem ela. E a `WdoGridReloadMaker` está a um parâmetro de
distância do mesmo bug: o `pending_side` dela só é limpo por recusa confirmada
ou por preenchimento, então basta alguém ligar `ttl_bars` na entrada dela para
o robô ficar mudo pelo mesmo mecanismo.

**Correção aplicada (2026-09-10):** a assimetria foi fechada na raiz, não só
no robô. Nasceu um hook novo, `IntradayStrategy.on_order_expired(ts)`
(`src/strategy/daytrade/base.py`, default no-op), chamado pelo motor na MESMA
barra em que ele emite `LimitCancelled(reason="ttl")`. É irmão de
`on_order_rejected`, e **são dois hooks de propósito**: recusa e prazo são duas
causas diferentes, e um robô pode querer reagir diferente a cada uma —
juntá-los num aviso só obrigaria toda estratégia a adivinhar por que a ordem
morreu. Nenhum robô do pódio mudou de comportamento (hoje nenhum outro usa
`ttl_bars` na entrada; a `WdoGridReloadMaker` continua sendo o caso latente da
tabela acima, agora com a defesa pronta para quando alguém ligar o prazo).
Coberto por `tests/test_intraday_alvo_alterado.py`. A regra abaixo continua
valendo inteira — ter o aviso não dispensa a estratégia de contar o próprio
prazo, porque a plataforma NOVA pode não ter aviso nenhum.

> **Regra.** **Quem coloca uma ordem parada COM PRAZO conta o prazo sozinho e
> conclui por conta própria que a ordem morreu. Nunca confie em ser avisado.**
> Num motor de execução, "ordem recusada" e "ordem expirada" são eventos
> DIFERENTES, e uma plataforma pode notificar um e não o outro — registrar no
> log não é notificar. Estado do tipo "já mandei minha ordem" que só é limpo
> por preenchimento ou por recusa é uma armadilha: ele fica permanentemente
> ligado no caminho que ninguém notifica, e o sintoma é silêncio, não erro.
>
> Corolário de auditoria, que é o que economiza a próxima descoberta: ao achar
> um caminho de notificação faltando, **enumere TODAS as formas pelas quais
> uma ordem pode morrer** (recusa, prazo, cancelamento pedido, cancelamento
> pela corretora, achatamento de fim de pregão) e confirme, uma a uma, que
> cada uma tem caminho de volta. O item 1.14 fechou uma delas e a ausência das
> outras passou despercebida por 13 dias. Corolário de reuso: antes de escrever
> a defesa, procure quem no repositório já resolveu isso — aqui ela existia,
> pronta e em produção, num robô que ninguém consultou.
>
> **Pergunte à plataforma nova:** pergunta 89 (nova).
> (1.14, 3.8, 4.23)

### 4.26 Mudar o alvo mudava o nível do BACKTEST e não mexia na ordem que já estava no livro da corretora — o mecanismo que responde por 81% do líquido da ORB não existia ao vivo — CORRIGIDO 2026-09-10

Achado em 2026-09-10, ao portar a ORB do WDO@ para produção. `AdjustTarget` é
aplicado no motor (`src/backtest/intraday/machine.py`) escrevendo
`pos.current_target` na hora: a partir da barra seguinte o backtest já mede o
nível novo. Só que, com a saída fatiada (`exit_split_unit` — o desenho de
execução obrigatório deste projeto desde 2026-09-09), a ordem-limite REAL foi
mandada para a corretora **uma vez só**, pelo bloco que arma a fatia no
primeiro toque do alvo, e **ninguém a reprecificava**. Ela ficava parada no
preço VELHO para sempre.

O robô ao vivo ficava esperando um alvo que o robô medido já tinha abandonado.
A posição não sairia no nível novo: sairia no achatamento de fim de pregão, **a
mercado** — exatamente o custo que este desenho de execução existe para não
pagar (4.24, 4.8).

**O número, e por que ele não é um detalhe.** O mecanismo de saída é o que
responde por **+81% do líquido** da ORB. Trocar o corte de tempo a mercado por
`AdjustTarget(preço corrente)` aos 60 minutos, nos mesmos 72 pregões:

| | corte de tempo a mercado | `AdjustTarget` aos 60 min |
|---|---|---|
| deslize pago em 72 pregões | R$265,00 | **R$70,00** |
| R$/operação | +15,71 | **+21,31** |

Dos **+R$5,60 por operação** de ganho, **R$3,36 são mecanicamente o deslize que
deixou de ser pago**. E nada disso existiria ao vivo: ao vivo a ordem continuava
no preço velho, então o robô real pagaria o achatamento a mercado enquanto a
planilha mostrava o ganho.

**A segunda metade do defeito ia para o outro lado — no simulado.** Quando o
alvo mudava, a fatia simulada **herdava a fila já consumida do nível velho**.
Uma ordem-limite parada num preço não vira outro preço sozinha: ela é
cancelada, outra é mandada, e a nova entra no **FIM** da fila daquele nível. O
backtest media um robô mais rápido do que a corretora executa — a MESMA família
de erro que `backtest/intraday/fidelidade.py` (fila 438/489, Kaplan-Meier)
existe para fechar (4.21, 4.22). Um defeito otimista no preço ao vivo e outro
otimista na velocidade no simulado, na mesma linha de código.

**Correção aplicada (2026-09-10):** `_Position` ganhou `exit_resting_price` — o
preço com que a fatia foi **de fato** posicionada. Quando ele diverge de
`current_target`, os dois motores reagem, cada um pagando o seu custo:

| motor | o que faz quando o alvo muda |
|---|---|
| REAL | cancela (`reason="alvo_alterado"`) e remanda no nível novo, com a MESMA cautela de cancelamento-não-confirmado do estouro de prazo |
| SIMULADO | desarma e rearma a fatia com a fila do nível **CHEIA** |

A cautela do cancelamento não é zelo: **cancelamento não confirmado significa
ordem possivelmente viva** (1.24), e duas ordens-limite pela mesma posição numa
conta NETTING não zeram — invertem o lado (1.23). Coberto por
`tests/test_intraday_alvo_alterado.py`.

> **Regra.** **Mudar um nível no estado interno do motor não move a ordem que
> já está no livro.** Toda vez que o robô puder ALTERAR um nível que já virou
> ordem parada na corretora, a alteração precisa de um caminho EXPLÍCITO de
> cancelar-e-remandar — e o **custo** desse caminho (perder a fila do nível,
> ficar exposto entre o cancelamento e o novo envio) tem de aparecer no
> backtest. Sem isso o simulador mede uma reprecificação de graça que a
> corretora não dá, e o robô ao vivo fica esperando um preço que o robô medido
> já abandonou.
>
> **Corolário que amarra este item ao 4.25, e é o que vale levar para um motor
> novo: o contrato motor↔estratégia é assimétrico por omissão, e a omissão é
> sempre do mesmo lado — o motor age e não conta.** Duas vezes no mesmo dia, no
> mesmo arquivo: a ordem de entrada morreu e ninguém avisou o robô (4.25); o
> robô mudou o alvo e ninguém avisou a corretora (este item). Ao auditar um
> motor de execução, enumere os **dois sentidos**: (a) toda forma de uma ordem
> MORRER tem hook de volta para a estratégia? (b) toda decisão da estratégia
> que altera uma ordem JÁ ENVIADA tem caminho até a corretora? Auditar só um
> sentido fecha metade dos buracos e dá a sensação de ter fechado todos.
>
> **Pergunte à plataforma nova:** pergunta 90 (nova).
> (4.25, 4.21, 4.22, 4.24, 1.23, 1.24)

### 4.27 Trailing/breakeven-stop com trava de 1 tick é economicamente idêntico a NÃO travar — o deslize fixo do stop consome a trava inteira antes de virar lucro

Testado em 2026-09-11 (`scripts/daytrade/wdof1_saida_assimetrica_2026_09_11.py`),
WDO F1, T2/S16: uma variante de saída assimétrica ("breakeven+1 tick" — arma
quando o preço anda 2 ticks a favor e move o STOP para `entry_price + 1 tick`
a favor, via `AdjustStop`) deu **0% de acerto nos dois únicos pregões reais
disponíveis** — 2026-09-10 (n=11, líquido **−R$263,50**) e 2026-09-11 (n=17,
líquido **−R$265,50**) — pior que o baseline T2/S16 sem trava nos mesmos dois
pregões (−R$256,50 e −R$240,00).

Rastreado trade a trade (prints de debug temporários, não incorporados ao
código): toda saída pelo trailing, **incluindo as que armaram exatamente como
pedido**, fechou em pnl = **−R$0,50** — só a corretagem, lucro líquido zero.
Exemplo: entrada long a 5.144,0; preço subiu a 5.145,0 (2 ticks a favor); o
código moveu o stop pra 5.144,5 = entry+1 tick, corretamente. A saída por esse
stop ainda assim rendeu zero.

A causa é o mesmo mecanismo do item 4.8, só que do lado do STOP: o motor
(`IntradayCostModel.slippage_ticks`, `backtest/intraday/machine.py`) cobra um
deslize FIXO de **1 tick ADVERSO em toda saída por stop**, sempre — é o mesmo
pedágio já embutido no baseline ("perda por stop = 16 ticks + 1 tick de
deslize + R$0,50 de corretagem"). Uma trava de exatamente 1 tick de lucro
coincide, em magnitude, com esse deslize: o tick que a trava reservava é
exatamente o tick que o deslize consome, e o resultado colapsa para "só a
corretagem" — nunca o lucro nominal que a trava pretendia proteger. Uma trava
de 2+ ticks sobrevive (sobra 1+ tick líquido depois do deslize); uma trava de
1 tick ou menos é teatro: mesmo formalmente correta no código, produz o mesmo
dinheiro de não ter trava nenhuma, só que via mais eventos de stop.

> **Regra (portável — vale para qualquer trailing/breakeven-stop, nesta
> linguagem ou na de destino da portabilidade):** uma trava de lucro só é
> real se for **estritamente MAIOR** que o deslize fixo cobrado na execução
> do stop nesta plataforma/simulador. Antes de aceitar qualquer geometria de
> trailing ou breakeven-stop, confira a distância entre o nível travado e o
> preço de entrada contra esse deslize — não contra zero. Trava ≤ deslize
> não é "trava pequena": é ausência de trava disfarçada de proteção, e ela
> ainda gasta um evento de stop (e a corretagem dele) para entregar o mesmo
> resultado de não ter travado nada.
> **Pergunte à plataforma nova:** pergunta 93 (nova).
> (4.8)

---

### 4.28 O flatten de fim de pregão NUNCA disparou ao vivo para robô de futuro — dois cortes derivados do MESMO campo se anulam, e o diário mostra ZERO eventos FLATTEN em toda a história

O único caminho de saída obrigatório do desenho ("day trade nunca carrega
overnight") é inalcançável em produção/sombra para futuro desde sempre —
verificado no código e nos dados, não é hipótese.

Mecanismo: dois cortes colidem, ambos derivados do mesmo campo
`SymbolProfile.session_end_time`.

1. `backtest/intraday/machine.py::on_closed_bar` achata a posição quando
   `ts.time() >= session_end_time_for(ts)` — para futuro,
   `backtest/intraday/profiles.py::_futures_profile` fixa esse horário no
   FECHAMENTO nominal: WIN@ 21:25 UTC (18:25 BRT), WDO@ 21:30 UTC (18:30 BRT).
2. O MESMO campo é o fim da janela em que o robô tem permissão para agir:
   `live/intraday_runtime.py::_fase_do_instrumento` → `live/clock.py::phase_em_janela`
   só devolve `OPEN` enquanto `agora < fim`; fora disso `run_once` devolve
   `idle` — o futuro nunca alcança a fase `CLOSING_AUCTION`.

Somado a `live/bar_feed.py::_MIN_BAR_AGE_SECONDS = 60` (a barra M1 só fica
elegível 60s depois de rotulada), a última barra que um robô de futuro
processa ao vivo é a **21:23 UTC (18:23 BRT)**: às 21:25:00 a fase já virou
`POST_CLOSE` e a barra 21:24 (que acabou de ficar elegível) não tem mais
quem a consuma. A condição de flatten (`ts.time() >= 21:25`/`21:30`) é
logicamente inalcançável.

Os números:

- `data/raw_intraday/WIN_A_.parquet`: em **190 de 194 pregões** a última
  barra M1 é 21:24 — a barra do corte quase nunca chega a existir.
  `WDO_A_.parquet`: **180 de 180 pregões** terminam em 21:29.
- `db/live.sqlite`, tabela `live_events`: **zero** eventos `FLATTEN` em toda
  a história, em todas as contas.
- `strategy/daytrade/registry.py` registra que **39,1%** das saídas do
  `copa_win` no backtest são por achatamento — essas saídas simplesmente não
  ocorrem ao vivo. Caso concreto, 2026-09-14, slot `dt-copa_win-win@-shadow`:
  SHORT 1 contrato WIN@ @186.200 aberto às 10:30 BRT, ainda aberto às 18:00
  BRT, ia atravessar o corte das 18:25 sem fechar.
- `live/intraday_runtime.py::_restore` descarta snapshot de pregão anterior
  ("estado de ontem não é estado, é lixo"): em sombra a posição só some, sem
  nunca ser realizada — o P&L da sombra fica incompleto justamente nas
  saídas pelo sino; em execução real a posição ficaria órfã, aberta
  overnight, sem stop nem alvo vigiados por ninguém.

O contraste prova que é bug e não escolha de design: o caminho de AÇÃO faz
certo. `core/b3_session.py::closing_bar_minute_utc` usa
`continuous_end − 1min`, com docstring explícita sobre o porquê ("um corte
no fechamento cheio nunca casaria com barra nenhuma"), e a fase de ação
ainda aceita `CLOSING_AUCTION` depois do corte — a barra 19:54 é consumida
às 19:55. `_futures_profile` fez exatamente o que aquela docstring documenta
como erro.

> **Regra (portável).** O corte de um achatamento obrigatório tem de ser o
> RÓTULO de uma barra que existe de verdade no dado (medido, não o horário
> nominal do regulamento), e a janela em que o robô tem permissão para agir
> tem de terminar DEPOIS desse corte — nunca no mesmo instante. Corte de
> saída e portão de atividade derivados do MESMO campo se anulam em
> silêncio: são dois empregos diferentes, e cada um precisa do seu próprio
> valor.
>
> Corolário de método: todo caminho de saída OBRIGATÓRIO exige evidência de
> que já disparou pelo menos uma vez em produção. Zero ocorrências no diário
> de um evento que o backtest atribui a ~39% das saídas é alarme, não
> normalidade — um caminho de saída nunca observado ao vivo é hipótese,
> igual a backtest não aferido contra extrato.
>
> Corolário de medição: enquanto isto não for corrigido, nenhum número de
> SOMBRA de robô de futuro que dependa do achatamento descreve o backtest —
> a sombra perde exatamente as operações que o backtest fecha pelo sino.
>
> **Pergunte à plataforma nova:** pergunta 105 (nova).
> (5.2)

---

### 4.29 A suíte estava verde sobre as três camadas do bug do 4.28 — porque nenhum teste perguntava se o corte era ALCANÇÁVEL, só se ele estava CERTO

Irmão direto do item 4.28: aquele documentou O QUE quebrou (dois cortes do
mesmo campo se anulando); este documenta por que uma suíte com milhares de
testes, todos verdes, nunca acusou.

Corrigir a primeira camada não resolveu nada — só depois de rodar é que a
segunda e a terceira apareceram, e as duas últimas só foram encontradas
porque alguém foi LER O LOG DE PRODUÇÃO em vez de confiar na suíte:

| camada | o que fazia | onde | como foi corrigida |
|---|---|---|---|
| motor | corte de achatamento igual ao fim nominal do pregão (21:25 WIN@ / 21:30 WDO@ UTC) | `backtest/intraday/profiles.py` | `SymbolProfile.flatten_cut_time`, campo novo, = fim − 5min (`core/b3_session.py::FOLGA_ACHATAMENTO_MINUTOS=5`, `flatten_cut_utc`) |
| runtime | `live/clock.py::phase_em_janela` desligava o robô no MESMO instante do corte de achatamento | `live/clock.py`, `live/intraday_runtime.py` | `session_end_time` passou a significar só "fim do pregão / até quando o robô age" |
| **supervisor** | `live/clock.py::_active_window` dormia pelo calendário da AÇÃO: o slot `dt-copa_win-win@-shadow` imprimiu "[fora do horario de pregao] proximo passo em 15.0h" às **18:00 BRT** com posição SHORT aberta e o pregão do WIN correndo até 18:25 | `live/clock.py` | `_active_window` passa a terminar no fechamento MAIS TARDE do dia entre os instrumentos do slot, mais 1h de folga |

Se a correção tivesse parado na primeira camada, o achatamento continuaria
não acontecendo — com dois testes novos passando e dando a impressão de
coberto.

**A suíte não só deixou passar, ela CONGELOU o valor errado.**
`tests/test_intraday_live_runtime.py::test_status_reporta_fuso_corte_e_ordem_em_pe`
afirmava `corte_flatten_utc == "19:54:00"` e passava havia meses. O teste
estava certo sobre o que o código FAZIA e cego sobre o que o código
PRECISAVA fazer: conferia o rótulo exibido no painel, nunca que o corte
fosse alcançável. Nenhum teste do repo relacionava os dois números (corte de
achatamento × janela em que o robô pode agir) — eles moram em módulos
diferentes (`backtest/intraday/profiles.py` e `live/clock.py`), cada um com
cobertura própria, todos verdes. O bug morava exatamente na JUNTA entre eles,
que é onde nenhum teste de unidade olha.

Corolário concreto: a correção **quebrou** 2 testes — o acima e
`tests/test_live_clock.py::test_in_active_window_uma_hora_depois_do_leilao_de_fechamento`
— os dois estavam congelando o comportamento defeituoso. Teste que quebra
quando um bug é corrigido não é rede de proteção, é cimento.

> **Regra (portável, sobrevive à troca de linguagem e de corretora).**
>
> 1. Todo caminho de saída OBRIGATÓRIO precisa de um teste de
>    ALCANÇABILIDADE, não só de correção. "Dado o relógio real e as latências
>    reais, existe algum instante em que esta condição pode ser avaliada?" é
>    pergunta diferente de "a condição está certa", e só a primeira pega este
>    bug. O teste que agora trava isso é
>    `tests/test_intraday_profiles.py::test_a_barra_do_corte_ainda_cabe_na_janela_em_que_o_robo_pode_agir`
>    — reprova com os valores antigos (conferido).
> 2. Quando um valor atravessa a fronteira de dois módulos, o teste tem de
>    morar na JUNTA. Dois módulos com cobertura própria e nenhum teste do PAR
>    é o desenho exato em que este bug sobreviveu.
> 3. Ao corrigir um bug, conte quantas camadas do sistema repetem a mesma
>    suposição errada — aqui foram três, em três módulos, e as duas últimas
>    só apareceram ao ler o log de produção depois da primeira correção.
>    Suíte verde depois de corrigir a camada 1 não é evidência de que o
>    caminho funciona.
> 4. Teste que precisa ser EDITADO para um bug ser corrigido merece revisão,
>    não atualização automática. Ele estava afirmando um comportamento, e
>    ninguém tinha perguntado se aquele comportamento era desejado.

Suíte final depois da correção completa: 2029 passed, 1 skipped.

> **Pergunte à plataforma nova:** pergunta 106 (nova). (4.28)

---

### 4.30 Um ratchet de stop de UM passo se auto-dispara — o nível novo nasceu do lado errado do preço, no pior instante possível

Testado em 2026-09-15 (`scripts/daytrade/wdo_orb_ratchet_stop_2026_09_15.py`),
`wdo_orb`. A primeira versão de um "ratchet" de stop armava em UM passo só:
quando o preço andava 70% da distância até o stop (contra a posição), o stop
era movido para 50% dessa distância. No instante em que a regra arma, o preço
JÁ está a −70%; o stop novo em −50% nasce **atrás** do preço na direção
errada — do lado que ele já ultrapassou — e dispara na barra seguinte. Não é
proteção: é uma ordem a mercado disfarçada de proteção, executada no pior
momento possível (o fundo da excursão adversa).

**O número**, medido no pregão de 2026-09-11 (2 operações do `wdo_orb`): a
regra que simplesmente FECHAVA a posição nesse ponto (70% da distância) dava
**−R$80,50 por operação**; o ratchet de um passo dava **−R$110,50**,
executando a −21 ticks em vez de −15. A "proteção" custou **R$30,00 a MAIS
por operação** do que não ter proteção nenhuma naquele ponto — e teria
passado despercebida, porque o número continua parecendo um stop normal no
relatório: a operação sai por `stop`, com o valor do stop, e nada na tabela
denuncia que o stop foi movido para um lugar que o preço já tinha visitado.

O erro foi pego por um smoke test de 4 pregões ANTES da varredura completa.
Se tivesse ido direto para os 134 pregões, o resultado teria sido lido como
"o ratchet piora o robô" — refutando a hipótese pelo motivo ERRADO, um bug de
implementação com roupa de veredito de estratégia.

A correção: gatilho de DOIS passos (foi a −70% **e** voltou a −50%) com o
stop novo indo para **−70%** — o pior ponto JÁ VISITADO pelo preço, que por
definição está atrás do preço atual e portanto não pode se auto-disparar.

Vale amarrar ao que o motor já garante: `strategy/daytrade/base.py` só aceita
um `AdjustStop` quando o nível novo é **mais protetor** que o atual — essa
checagem impede AFROUXAR o stop (item 1.10), mas não impede APERTÁ-LO para um
ponto que o preço já ultrapassou, que é exatamente o buraco deste item. Um
stop pode ficar mais apertado (mais protetor, na métrica que o motor confere)
e ainda assim nascer do lado errado do preço corrente.

> **Regra (portável — vale para qualquer regra de movimentação de stop, nesta
> linguagem ou na de destino da portabilidade):** um nível de stop novo tem
> de ficar num ponto que o preço já visitou e do qual já se afastou — nunca à
> frente do preço atual na direção adversa. Antes de aceitar qualquer ordem
> de movimentação de stop, compare o nível novo com o preço corrente: se ele
> já foi ultrapassado, o efeito real não é proteger, é emitir uma ordem a
> mercado no pior preço da excursão. E a consequência de método, que é o que
> generaliza: **uma regra de proteção mal desenhada não aparece como erro no
> relatório — aparece como uma saída de stop normal**, então ela não se
> denuncia sozinha; a única defesa é o teste pequeno com inspeção das
> operações individuais (preço de execução, instante do disparo) antes de
> rodar a base inteira.
> **Pergunte à plataforma nova:** pergunta 108 (nova).

---

### 4.31 O alarme de deslize de SAÍDA compara contra o alvo DECLARADO na entrada — quando a própria estratégia move o alvo, ele dispara em 5 de 6 saídas normais

Achado na auditoria da semana de sombra 2026-09-14 a 2026-09-18 (318
operações fechadas, 6 slots). `live/intraday_runtime.py` grava
`self._alvo_declarado = evento.target` no instante da ENTRADA (linha 4859) e
compara contra esse MESMO valor no fechamento (linha 5079, condicionado a
`trade.exit_reason == IntradayExitReason.TARGET`). O alarme nunca é
atualizado por uma reprecificação de alvo em vida: `grep AdjustTarget` em
`intraday_runtime.py` não devolve nenhuma ocorrência — o único lugar que trata
`AdjustTarget` é o motor (`backtest/intraday/machine.py`).

O `wdo_orb` (TOP-1 do pódio, em sombra) tem `saida_limite_minutos=60.0`: por
DESENHO, 60 minutos depois da entrada ele manda `AdjustTarget(preço corrente)`
e passa a esperar a ordem-limite encher no nível NOVO (item 4.26, o mecanismo
que responde por 81% do líquido da ORB). O alarme de deslize nunca soube disso
— ele continua comparando o preço de saída contra o alvo do minuto zero.

**O número.** Das 6 operações do `wdo_orb` na semana, **5 dispararam "DESLIZE
DE SAIDA"**, somando **R$705,00** de deslize (R$275,00 + R$35,00 + R$125,00 +
R$90,00 + R$180,00) — fantasma nas cinco: o preço executado era o alvo
REANCORADO, não o declarado na entrada. O resultado líquido real das 6 foi
**+R$377,00** — o alarme reportou deslize de quase o DOBRO do lucro do robô,
sem nenhum real perdido de verdade. A única saída que não disparou (17/09) foi
a que fechou além do alvo original, sem passar pelo corte de 60 minutos.

**Por que não é cosmético.** O comentário no próprio código (junto da linha
5079) documenta que este alarme é "o ÚNICO jeito de descobrir que o alvo
fatiado estourou `exit_ttl_bars` e saiu a MERCADO" — o caminho de execução
mais caro do robô (item 4.21). Um alarme que dispara em 5 de 6 saídas normais
soterra exatamente o evento que ele existe para achar: quando o estouro de
prazo REAL acontecer, ele vai chegar misturado a um lote de falsos positivos
que ninguém mais confere, um por um. É o MESMO modo de falha já corrigido uma
vez: até 2026-09-09 este alarme disparava em todo STOP (o mesmo comentário
registra o caso real — short entrada 5107,50/alvo 5106,50 fechado no stop a
5116,00, "DESLIZE DE SAIDA — R$ +95,00" que era só a distância normal entre
stop e alvo). Aquela correção fechou a porta do STOP e deixou a porta do ALVO
MOVIDO aberta — é o item 4.15 ("rótulo por intenção esconde o deslize") de
novo, num campo que já tinha sido corrigido uma vez para o motivo errado de
disparo e continua sem tratar o motivo certo.

> **Regra (portável — vale em qualquer linguagem/plataforma, e para qualquer
> alarme de execução, não só este).** Um alarme que compara "o que a
> estratégia pediu" contra "o que foi executado" tem de comparar contra o
> nível VIGENTE no momento da saída, nunca contra o nível declarado na
> entrada — porque qualquer direito que a estratégia tenha de mover o próprio
> nível (alvo, stop, o que for) transforma o alarme numa fonte de falso
> positivo proporcional a QUANTO ela move, e não a nenhuma execução ruim.
> Corolário de auditoria: quando um alarme passa a disparar na MAIORIA dos
> eventos que deveria vigiar, ele parou de ser alarme e virou ruído — a taxa
> de disparo é métrica de saúde do PRÓPRIO ALARME, não só do robô que ele
> vigia, e merece a mesma suspeita que uma suíte de testes sempre verde
> (7.3) ou um teste que nunca reprova.
> (4.15, 4.21, 4.26)

### 4.32 A cadência de reancoragem reseta a fila a cada nível novo — a mesma estratégia armou 1.012 níveis num pregão e preencheu ZERO

Achado na mesma auditoria da semana de sombra 2026-09-14 a 2026-09-18. O motor
reseta `_queue_ahead_remaining = cfg.queue_ahead_qty` toda vez que um nível
NOVO é armado (`backtest/intraday/machine.py`, linha ~1966) — por desenho,
documentado de propósito no comentário de `queue_ahead_qty` (linhas ~355-363):
"um REARME que recalcula o MESMO nível... NÃO reseta... Um rearme que muda de
nível de verdade... reseta... É exatamente o custo que o motor antigo cobrava
ZERO e este parâmetro passa a cobrar." O que ninguém tinha medido é a
consequência de uma estratégia que reancora RÁPIDO DEMAIS: ela nunca deixa a
fila do nível novo drenar antes de trocar de nível de novo, e a taxa de
preenchimento vai a zero por CONSTRUÇÃO, não por falta de sinal.

**O número**, `wdo_grid_reload_maker` (TOP-2 do pódio), fila calibrada em
329 (entrada) / 494 (saída) contratos:

| pregão | níveis armados (novos + reprecificações) | preenchimentos |
|---|---|---|
| 2026-09-14 | 76 (53 + 23) | 49 |
| 2026-09-15 | 96 (61 + 35) | 61 |
| **2026-09-16** | **1.012 (587 + 425)** | **0** |
| **2026-09-17** | **73 (44 + 29)** | **0** |
| 2026-09-18 | 2 (1 + 1) | 1 |

Em 16/09 o robô armou **1.012** ordens-limite e preencheu **ZERO**. No mesmo
símbolo, no mesmo dia, o `wdo_grid_fade_off_t3` armou 101 e preencheu 64 — não
foi o mercado que fechou, foi a CADÊNCIA: uma estratégia que reprecifica antes
de a fila anterior drenar paga a fila cheia a cada troca, para sempre, e nunca
acumula tempo suficiente parada num nível para preenchê-lo.

O que isso esconde numa tabela padrão: "0 trades" e "1.012 tentativas, 0
preenchimentos" são diagnósticos OPOSTOS — o primeiro diz que não houve sinal
para operar; o segundo diz que o desenho de execução é inviável independente
de a estratégia estar certa sobre a direção. A tabela de saída hoje (`backtest/
intraday/report.py`) não distingue os dois: as 12 colunas fixas mostram
`trades` (contagem de round-trips fechados), não níveis armados.

> **Regra (portável).** Numa estratégia que entra por ordem-limite, a
> CADÊNCIA de reancoragem é parâmetro de EXECUÇÃO tão decisivo quanto o alvo e
> o stop — se ela reprecifica mais rápido que o tempo de drenagem da fila do
> nível, a taxa de preenchimento vai a zero por construção, e nenhuma
> auditoria de geometria (alvo, stop, filtro de entrada) vai explicar o motivo
> porque o motivo não está na geometria. Medição obrigatória para qualquer
> robô maker que reancora: reportar **níveis armados por preenchimento** ao
> lado do número de trades — "0 trades" sozinho não diz se foi ausência de
> sinal ou cadência inviável, e são decisões de conserto completamente
> diferentes (a primeira pede outra estratégia; a segunda pede outro
> intervalo mínimo entre reancoragens).
> **Pergunte à plataforma nova:** pergunta 114 (nova). (4.9, 4.14, 4.19, 6.21)

Complemento (2026-09-19, item 6.44): o mecanismo acima é real — reancorar
rápido demais pode zerar o preenchimento num pregão isolado. Mas a mesma
cadência varrida AGREGADA em 72 pregões (10s a 180s) não move a variável que
decide o resultado (o payoff, que fixa o breakeven) — não leia este item como
"calibre o freio e ganhe": a medição agregada diz que, uma vez fora da faixa
patológica, não há gradiente utilizável.

### 4.33 Quando `live/` recusa enviar a ordem, a ESTRATÉGIA não fica sabendo — a notificação que o item 4.25 corrigiu no MOTOR não cobria o caminho novo da camada de execução — CORRIGIDO 2026-09-21

> **DESFECHO, 2026-09-21 — corrigido no mesmo dia.** O aviso saiu dos
> chamadores e foi para o ÚNICO ponto de esquecimento:
> `IntradaySessionMachine.discard_resting_limit` (em
> `src/backtest/intraday/machine.py`) passou a receber `ts` OBRIGATÓRIO e a
> chamar `strategy.on_order_rejected(ts)` quando de fato havia ordem
> vigiada. Os cinco chamadores em `src/live/intraday_runtime.py` foram
> atualizados (`_reconcilia_entrada_orfa`, `_descarta_arme_de_barra_velha`,
> `_recusa_por_cota_de_envio`, o disjuntor de cadência dentro de
> `_on_limit_placed`, e `_recusa_de_envio`).
>
> O invariante que sustenta a correção: **enquanto avisar era
> responsabilidade de quem chama, cinco chamadores independentes
> concordaram em não avisar.** Com `ts` obrigatório e o aviso dentro da
> função, um sexto caminho não tem como esquecer — ou ele avisa, ou não
> compila. Regra geral: quando o mesmo esquecimento aparece em N pontos, o
> conserto não é lembrar N vezes, é mover a obrigação para o ponto único
> por onde todos passam e torná-la impossível de omitir pela assinatura.
>
> Vale registrar que o comentário que existia em `_recusa_de_envio`
> argumentava o CONTRÁRIO — dizia que avisar seria `live/` decidindo por
> conta própria (regra 6 do `AGENTS.md`) porque "recusa de corretora não
> existe no backtest". O argumento estava invertido: a regra 7 do mesmo
> `AGENTS.md` diz que o buraco é REPORTADO à estratégia, que decide se
> ainda deve algo — "interpretar o buraco é da estratégia, nunca de
> `live/`". **Não avisar também é uma decisão, tomada por omissão, e é a
> pior das duas**: no backtest não existe estado em que a estratégia tenha
> armado uma ordem, a ordem tenha deixado de existir e ninguém a avise —
> ela sempre preenche, expira ou é recusada. O silêncio produzia um estado
> que o backtest não sabe reproduzir, que é exatamente o que a regra 6
> existe para impedir.
>
> Testes que travam a regressão, em `tests/test_intraday_live_runtime.py`:
> `test_barra_velha_AVISA_a_estrategia_que_a_ordem_dela_morreu`,
> `test_robo_REARMA_no_mesmo_pregao_depois_da_recusa_por_barra_velha` e
> `test_esquecer_a_ordem_SEMPRE_avisa_a_estrategia_seja_qual_for_o_caminho`
> (checagem estática da assinatura: falha se `ts` ganhar default ou se o
> aviso sair da função).

Mesmo pregão de 2026-09-21 (item 5.27, abaixo), e reincidência de 2026-09-14
e 2026-09-15, slot de sombra `dt-wdo_orb-wdo@-shadow`. O feed de tick do
`WDO@` congelou por **36 minutos** (09:06:54 até ~09:43 BRT) — três robôs de
WDO@ pararam no mesmo `ultima_barra=2026-09-21 12:06:54.934+00:00`, 437
passos `daytrade_espera` seguidos, enquanto um processo NOVO lendo o mesmo
terminal recebia tick normal em `WDOV26` até 12:43. `falha_de_leitura` ficou
`None` o tempo todo — a leitura "deu certo" e devolveu lista vazia, então o
vigia de cegueira criado depois do item 5.17 não dispara para este modo de
falha.

Quando o feed voltou, o robô consumiu 17.981 barras de uma vez, a estratégia
armou a entrada do dia, e `live/` recusou o envio CORRETAMENTE por BARRA
VELHA (atraso 2.177,6s = 36 min, teto 120s); o diário registrou o `warn`
direitinho. **O defeito:** `IntradayLiveRuntime._descarta_arme_de_barra_velha`
chama só `machine.discard_resting_limit()` — limpa a ordem vigiada no MOTOR,
mas não avisa a ESTRATÉGIA, porque `on_order_rejected`/`on_order_expired` só
são chamados de dentro de `backtest/intraday/machine.py`, nunca deste
caminho. No `wdo_orb`, `_armou_hoje` fica `True` para sempre: o robô passa o
resto do pregão em silêncio achando que tem ordem no livro. Mesmo defeito em
`_recusa_por_cota_de_envio` (cota de vazão). Reproduzido fora do motor:
depois do arme recusado, quatro rompimentos seguidos devolvem `[]`; uma
única chamada a `on_order_rejected` devolve o robô ao ar imediatamente.

Frequência medida no log do slot de sombra: recusa por barra velha em
2026-09-14, 2026-09-15 e 2026-09-21 — **3 dos 7 pregões** desde 11/09. Em
15/09 e 21/09 o robô fechou o pregão com ZERO entradas.

É a MESMA família do bug que o item 4.25 corrigiu em 2026-09-10 (o motor
cancelava por prazo sem avisar, `_armou_hoje` ficava ligado — custou 14 dos
72 pregões do IS, +R$1.236 contra +R$1.649). A correção de então cobriu o
caminho do MOTOR e deixou descoberto o caminho do `live/`.

> **Regra (portável).** Todo caminho que mata uma ordem tem de avisar QUEM A
> PEDIU, não só quem a vigiava. Esquecer a ordem na camada de execução e não
> notificar a camada de decisão produz um robô que acha que está posicionado
> e fica mudo — e mudo é indistinguível, no fim do dia, de "não houve
> sinal". A notificação de morte de ordem é obrigação do PONTO onde a ordem
> morre, seja qual for a camada; se uma camada nova puder recusar envio, ela
> herda a obrigação junto. Corolário de auditoria (7.1): ao corrigir uma
> notificação faltante, varra TODOS os pontos que matam ordem, não só o que
> apareceu — o padrão certo já existia no repo (4.25) e mesmo assim não foi
> replicado para o segundo caminho.
> **Pergunte à plataforma nova:** pergunta 116 (nova). (4.25, 7.1, 5.17)

### 4.34 O número do backtest da entrada limitada do WIN era condicional a uma premissa de fila de 2 ticks que nunca foi calibrada — exigir 3-4 ticks tirou 22,5% a 29,5% do lucro

Robô escada WIN M15 v4.1 (ainda em pesquisa, sem dinheiro real), 2026-10-09.
A entrada é uma ordem limitada no `close` da barra de confirmação, e o backtest
só a enche se o preço passar **10 pts (2 ticks) ALÉM do limite**. Esse "passar
X pts" é todo o modelo de fila do WIN: o equivalente do `queue_ahead_qty` do
WDO@ (itens 4.20 a 4.22), só que **o do WDO foi calibrado contra extrato real
(`fidelidade.py`, Kaplan-Meier) e o do WIN nunca foi**. Os 10 pts foram
escolhidos, não medidos.

Teste de robustez nos **338 pregões de teste do IS** (base **+72.960 pts,
DD 5.173**), variando só a premissa de preenchimento:

| premissa | total (pts) | variação | DD |
|---|---|---|---|
| passar 10 pts (base, 2 ticks) | +72.960 | — | 5.173 |
| passar 15 pts (3 ticks) | +56.560 | **−22,5%** | 7.030 |
| passar 20 pts (4 ticks) | +51.450 | **−29,5%** | — |
| limite 0,1 ATR mais FAVORÁVEL | — | **−33,6%** | — |
| validade da ordem 2 / 4 / 6 barras | — | dentro de ±2% | — |
| limite 1 tick PIOR | — | dentro de ±2% | — |

Dois resultados, de natureza oposta. A validade da ordem e o limite um tick
pior formam **platô** (±2%): o desenho não depende deles. A fila **não** é
platô: um tick a mais de exigência custa ~22% e dois custam ~30%, e o DD sobe
36% (5.173 para 7.030) no mesmo movimento. O limite 0,1 ATR mais favorável
parece uma melhoria (preço de entrada melhor) e custa 33,6%, por **seleção
adversa**: os dias de tendência, que carregam o lucro, são exatamente os que
não voltam ao preço da ordem — pedir preço melhor troca os melhores pregões
por pregões sem fill.

**Diferença para o item 6.30.** Lá a fila do WIN@ não mordia, porque o alvo era
longo, a posição durava horas e o giro era de 25 mil contratos por minuto.
Aqui o que está em jogo é a ENTRADA colada no preço (limite no `close`, enche
com 2 ticks de passagem) e o número morde em 3 a 4 ticks. "A fila não
generaliza" também vale ao contrário: não generaliza nem de um lado da mesma
ordem para o outro, nem de um robô para outro no mesmo instrumento.

> **Regra (portável).** Quando o resultado de uma estratégia com entrada
> limitada cai 20% a 30% ao mudar a premissa de fila de 2 para 3 ou 4 ticks, o
> número do backtest é **condicional à fila** — descreve a premissa, não o
> robô. Antes de dinheiro real, a fila tem de ser MEDIDA na plataforma (extrato
> de ordens reais, com correção de censura, itens 4.20 a 4.22), por
> instrumento, sem reaproveitar a calibração de outro ativo. Em toda medição
> maker, **estresse a premissa de fila PARA CIMA** (3, 4 ticks) e reporte a
> queda ao lado do número base. **Nunca otimize a fila para baixo**: a
> premissa que maximiza o backtest é, por construção, a mais otimista, e a
> otimização a escolheria. Corolário: um robô que passa em "10 pts" e perde um
> quarto do lucro em "15 pts" não tem edge validado, tem edge CONDICIONAL.
> **Pergunte à plataforma nova:** pergunta 146 (nova). (4.20, 4.22, 6.30, 6.38)

---

## Parte 5 — Dados, relógio e instrumento

### 5.1 Fuso errado desliga proteção em silêncio

O feed tratava a hora do servidor como UTC quando ela vinha em horário local.
Toda cotação parecia ter **10.800 segundos** de idade, e o sistema suprimia todo
stop por dado velho. O mecanismo existia e estava correto — só nunca chegava a
rodar.

A primeira correção foi pior que o problema: autocalibração pela idade do tick
mais novo, que é **ambígua por construção** (um tick de 1h atrás num papel
ilíquido e um servidor 1h fora do fuso produzem o mesmo número). Ela adotou +4h
onde o certo era +3h.

> **Regra:** fuso é DECLARADO e depois CONFERIDO contra referência líquida.
> Nunca inferido de dado ruidoso. A conferência **impede operar** quando acusa, e
> nunca reescreve o valor sozinha.

### 5.2 O horário do pregão pode não ser fixo — e varia por instrumento

O pregão à vista da B3 desloca 1 hora com o horário de verão **dos EUA**;
o futuro NÃO desloca. O código tinha um horário fixo, que era só o regime de
inverno americano — cortando ~36% das sessões uma hora antes do fechamento real.
Corrigir isso mudou o resultado fora da amostra de R$621 para R$679.

> **Regra:** horário de sessão é regra POR INSTRUMENTO, medida contra o dado
> real, nunca uma constante única.

### 5.3 Janela de consulta estreita pode devolver dado incompleto sem erro

O terminal devolvia negócios incompletos ou zero para janelas estreitas dentro do
pregão do dia — 75 de 139 negócios reais numa janela de 4,5h; **zero** em janelas
de até 2,5h. Sem levantar exceção nenhuma. O robô rodou o pregão inteiro, ~800
linhas de log, através de 5 reinícios, **sem nunca ver uma barra** — parecia "sem
sinal", era feed cego.

> **Regra:** quando um robô fica muito tempo sem sinal, confirme que o feed está
> recebendo dado ANTES de suspeitar da lógica. E prefira pedir janela larga e
> filtrar localmente a confiar que a fonte trata janela estreita corretamente.

**Re-confirmado ao vivo em 2026-09-04**, 11 dias depois e em outro instrumento:
uma janela de **2 minutos** pedida ao mesmo terminal, com o WDO negociando sem
parar às 10h4x, devolveu **0 negócios** — enquanto a janela de 24h do mesmo
instante devolveu 85.307. Não é bug de um dia nem de um papel ilíquido: o piso
de janela larga continua sustentando peso, e quem for estreitá-lo tem de
re-medir contra o instrumento real e no horário real antes (7.8).

### 5.4 Símbolo de cotação não é símbolo de negociação

O contrato contínuo existe para dar cotação e histórico; o servidor recusa ordem
nele. O contrato que negocia tem código de vencimento explícito. A ordem foi
recusada ao vivo com "Trade disabled" — e o preço usado para montá-la estava
certo, o que torna o erro mais difícil de enxergar.

> **Regra:** detecte o contrato negociável a cada início (o corrente é sempre o
> mais líquido — não precisa de calendário fixo), e nunca deixe a rolagem virar
> tarefa manual mensal.

### 5.5 O preço do ativo pode sair da faixa em que ele foi calibrado

O papel que o TOP-1 operava com dinheiro real caiu de **R$4,53 para R$0,13 dentro
da própria janela de backtest**. O tick passou de 0,22% para **7,7%** do preço —
um fator de 35x. O lucro médio por trade que julgava o robô era a média de dois
jogos diferentes somados. Hoje, ida e volta custa ~15% só de spread.

> **Regra:** nunca julgue por média agregada sem quebrar por regime de preço.
> Antes de manter dinheiro real num ativo, confira se o preço de hoje ainda está
> na faixa em que ele foi calibrado.

### 5.6 Um ativo pode simplesmente não ter mercado

Um dos ativos "calibrados" imprimia preço em **18 dos ~500 minutos** do pregão
(os outros: 217 a 427). E, por ser caro, exigia 22x o caixa dos demais. Era
negativo em todas as 48 células de geometria — não porque a calibração estivesse
errada, mas porque não havia mercado. Com 1 e 4 trades no histórico inteiro, não
havia amostra para dizer nada.

> **Regra:** barras por pregão é o portão de admissão de ativo mais direto e mais
> barato que existe. Aplique antes de calibrar, não depois.

### 5.7 Preço de futuro vem em PONTOS, não em reais — CORRIGIDO 2026-08-31

Achado no painel: a conta sombra do robô WIN@ (COPA_WIN) mostrava caixa de
**-R$180.455,00** com 1 único contrato (venda) aberto, e o card de posição
mostrava **R$180.705,00** de valor para essa mesma unidade. `evento.price`
de um futuro de índice/dólar é a COTAÇÃO em pontos (~180.000 no Ibovespa),
não reais por unidade — a contabilidade ao vivo (abertura/fechamento de
posição, cards do painel) fazia `preço × quantidade` para debitar/creditar
caixa, fórmula certa só para AÇÃO (onde não há alavancagem e o preço já é
R$/unidade). O multiplicador certo (MARGEM por contrato: R$100 WIN@/R$150
WDO@) já existia — mas só dentro do motor de backtest, usado para calcular
P&L de trade FECHADO, nunca ligado à contabilidade de caixa nem ao valor
exibido de posição/ordem em ABERTO: um caminho de código inteiramente
separado, que não consultava a config do motor.

O bug não depende de lado (compra/venda) nem de qual futuro — só não
aparecia nas outras contas porque abertura e fechamento usavam a MESMA
fórmula errada simetricamente: um round-trip completo (abre + fecha) se
CANCELA sozinho (debita o nocional errado, credita de volta o MESMO
nocional errado mais o P&L, que esse já vinha certo). Só uma posição ainda
ABERTA no momento da correção expõe o excesso: fechar com a fórmula nova
devolve apenas a margem certa, nunca desfaz o nocional errado que a
abertura tirou — sem reconciliar o dado já gravado, o caixa fica torto
para sempre. A reconciliação pontual foi feita com o robô PARADO (comparar-
e-trocar condicionado ao valor exato observado), nunca com o processo que
escreve a mesma conta ainda rodando — o painel e o robô são processos
SEPARADOS lendo a mesma conta, e uma correção automática "na leitura"
correria o risco de ser aplicada em dobro por cada um.

> **Regra:** todo valor que sai da corretora/feed em UNIDADE PRÓPRIA do
> instrumento (pontos de índice, pontos de dólar, ticks) exige um
> multiplicador explícito para virar reais — nunca assuma "preço × 1" só
> porque funcionou para ação. E o cálculo de custo/débito de caixa tem de
> usar o MESMO multiplicador que o cálculo de P&L já usa, lido da MESMA
> fonte — dois caminhos de código calculando "quanto isso vale em reais" de
> formas diferentes é o padrão que produz esse tipo de bug silencioso.
> **Pergunte à plataforma nova:** o preço que a API devolve para um
> derivativo é cotação (precisa de multiplicador) ou já vem em reais por
> unidade? Existe UM lugar só de onde todo código lê esse multiplicador, ou
> cada tela/função tem sua própria cópia da fórmula?
> **Reapareceu em 5.19** (2026-09-09), num terceiro caminho de código — a
> rotina de REMOÇÃO do robô, que nenhuma das correções de 2026-08-31 tinha
> visitado: R$375,00 de caixa simulado viraram −R$4.706,00.
> **E em 5.21** (2026-09-09), num QUARTO — `build_runtime` do painel, afirmando
> "1 ponto = R$1,00" para qualquer símbolo. A causa comum dos quatro está lá: o
> multiplicador morava no catálogo de ROBÔS, não no do INSTRUMENTO, então cada
> caminho novo o buscava onde desse.
> **Um QUINTO e um SEXTO no mesmo dia**: **5.22** — a economia lida do
> terminal podia chegar zerada (`trade_tick_value=0`) e nada validava isso
> antes de dividir; **5.23** — o `tick_size`, o terceiro número da mesma
> família, estava redigitado como default de construtor de robô, com um
> comentário afirmando que produção nunca usava aquele default.

### 5.8 Quantidade com sinal marca o LADO, não o valor do ativo — CORRIGIDO 2026-08-31

Achado no painel: 1 contrato WIN@ vendido (short) aparecia como **+R$100,00**
no card "Posições · Short" e como **-R$100,00** na linha equivalente da
tabela "Posições abertas" — o MESMO contrato, dois números com sinais
opostos. `LivePosition.quantity` já vinha negativa para short desde
2026-08-21 (marca o lado, e isso está certo — o card com sinal na tela usa
essa convenção). O bug estava em `LivePosition.market_value()`, que
multiplicava essa quantidade COM sinal pelo valor por unidade
(`unit_value_brl * quantity`), assumindo implicitamente um modelo de venda a
descoberto (vende primeiro, recebe caixa, a posição fica negativa como
passivo). Não é o modelo que o robô ao vivo usa: `_on_opened` debita o MESMO
`custo` positivo do caixa em QUALQUER lado — comprado ou vendido, é capital
COMPROMETIDO (margem de futuro, preço cheio de ação), nunca um crédito. Com
`market_value` invertendo o sinal só no short, `equity() = caixa +
investido` levava um prejuízo FANTASMA de 2× o custo assim que a posição
abria — uma vez no débito do caixa (certo), outra na inversão de sinal do
"ativo" que deveria compensar esse débito (errado) — sem nenhum preço ter se
mexido e sem nenhuma perda real. Existia havia dez dias sem ninguém notar
porque os números vigiados de perto (caixa, ganhos/perdas do dia) usam um
caminho de código DIFERENTE (`_custo_posicao`, sempre positivo) que nunca
teve esse bug; só "Carteira"/"Patrimônio" e a tabela de posições liam
`market_value`.

> **Regra:** o sinal da quantidade serve para identificar o LADO da posição
> (metadado, rótulo "compra"/"venda" na tela) — nunca para inverter o sinal
> de um valor que representa capital comprometido. Se abrir E fechar uma
> posição sem nenhum movimento de preço tem de deixar o patrimônio
> INALTERADO (a única afirmação que vale para compra e venda ao mesmo
> tempo), teste exatamente isso: `equity()` antes de abrir == `equity()`
> logo depois de abrir, com a posição marcada no próprio preço de entrada.
> **Pergunte à plataforma nova:** abrir uma posição vendida credita caixa
> (modelo "vende primeiro") ou debita margem/garantia (modelo "compromete
> capital", igual à compra)? A fórmula de valor-a-mercado da posição tem de
> ser a INVERSA exata de qual dos dois débitos/créditos a abertura realmente
> fez — não uma convenção genérica de "venda é negativo" copiada de outro
> instrumento.
>
> **Reapareceu em 5.19** (2026-09-09): o mesmo sinal de quantidade, agora
> multiplicado por um delta que o código JÁ tinha invertido por ser short —
> dupla inversão, prejuízo de 52 pontos gravado como lucro.
> **E em 5.21** (2026-09-09): a quarta aparição da família fecha o ciclo pela
> causa, não pelo sintoma — constante do instrumento guardada fora do
> instrumento.
> **5.22 e 5.23 (2026-09-09) fecham mais dois ângulos da mesma causa**: a
> economia nunca validada na fronteira (o terminal podia devolver zero) e a
> constante de instrumento redigitada como default de construtor de robô,
> com um comentário que afirmava o contrário.

### 5.9 O custo de uma chamada escala com a GRANULARIDADE do feed — a mesma constante é barata em barra e ruinosa em tick

2026-09-04, 10h: os dois slots do robô de mini-dólar (um com **R$375 reais**,
um em sombra) ficaram fora do pregão desde o sino. Nenhum erro no log, nenhuma
posição aberta, nenhuma ordem: o robô simplesmente não existia no pregão.

A inicialização de sessão dispara **32 buscas de histórico** num único passo —
1 da janela de volume, 15 de um laço de agregado diário, 15 de OUTRO laço
percorrendo **as mesmas 15 sessões** de novo, e 1 do warm start. Esse número
foi dimensionado quando o consumidor lia barra de 1 minuto: **~570 barras por
sessão**. O robô novo lê **negócio a negócio**, e uma sessão de mini-dólar tem
**~140.000** — 250x mais dado pela mesma linha de código. Medido: **~14s por
busca, ~447s de inicialização**, com dois processos disputando o mesmo
terminal.

O que transforma "início lento" em robô morto é o sinal de vida: o supervisor
toca o heartbeat **uma vez, no topo do laço**, antes de tudo isso. Quem vigia
de fora lê "parado há 15min com o processo de pé", mata no meio do trabalho —
e o reinício paga o custo inteiro outra vez, agora com mais sessão acumulada
para reprocessar. Espiral: mesma assinatura já vista em 2026-09-02 com este
mesmo robô, tratada na época como "conectividade degradada".

> **Regra:** toda constante escrita "por sessão" ou "por barra" é uma medida em
> unidades do FEED, não do código. Quando o mesmo código passa a servir uma
> granularidade mais fina, o produto *(número de chamadas × custo por chamada)*
> tem de ser re-medido no feed mais fino ANTES de ligar — e o mesmo vale para
> qualquer laço que construa um objeto por barra. Duas consequências que valem
> em qualquer plataforma: (a) trabalho de inicialização sobre **sessão
> encerrada** é história imutável e tem de ser reaproveitado entre reinícios,
> senão cada morte do vigia cobra o custo de novo, mais caro, e o robô nunca
> chega a operar; (b) um sinal de vida que só cobre o TOPO do laço não
> distingue "travado" de "trabalhando" — ou o sinal alcança o interior do
> passo, ou o limiar do vigia tem de ser maior que o pior passo legítimo.

> **Pergunte à plataforma nova:** quantas chamadas de histórico a inicialização
> faz, e quanto custa cada uma **no feed mais fino que algum robô usa**? O
> sinal de vida do supervisor cobre o interior de um passo ou só o topo do
> laço? (5.9)

### 5.10 Script de pesquisa que reimplementa a chamada ao terminal reintroduz o bug de fuso que a produção já corrigiu

Investigação de 2026-09-07 sobre por que o backtest divergia da corretora no
pregão de 2026-09-04. `scripts/daytrade/wdof1_mfe_mae_semana_2026_09_04.py`
chamava `mt5.copy_ticks_range` direto e rotulava o `time_msc` cru como UTC
(`tz_localize("UTC")`), sem o **+3h** que a rota compartilhada do projeto
(`market_data_intraday/mt5_ticks_source.py::_ticks_to_df`, a mesma que
`live/tick_feed.py` usa em produção) já aplica — porque o `time_msc` do
terminal é **hora de parede do servidor**, não UTC. Resultado: os preços de
preenchimento gravados no diário ao vivo pareciam não bater com o tape, com
desvios de vários pontos. Com a conversão correta, **os 36 preenchimentos do
pregão batem no mesmo milissegundo, sem uma exceção**.

É a MESMA classe de bug do item 5.1 — que já custou um mecanismo de stop
inteiro rodando desligado —, reintroduzida num script novo, não por
regressão do código corrigido, mas por **reimplementação ao lado dele**. A
correção de 5.1 continua intacta na rota compartilhada; o script simplesmente
não passava por ela.

Vale registrar o sinal de diagnóstico, porque ele economiza a investigação
inteira da próxima vez: o **SINAL do desvio invertia dentro do mesmo
pregão** — 14:08 dava preenchimento a 5.156,0 contra um "tape" de 5.151,5
(desvio +4,5), e 16:10 dava 5.148,5 contra 5.157,5 (desvio −9,0). Deslize de
execução tem sinal consistente: ele sempre cobra de você, nunca paga. Desvio
que troca de sinal ao longo do dia não é execução — é **comparação contra o
instante errado**, e o tamanho dele só acompanha o quanto o preço andou
naquele intervalo.

> **Regra:** nenhuma rotina — de pesquisa, análise ad-hoc ou produção —
> chama a fonte de dados na mão. A conversão de fuso mora em UMA função
> compartilhada, e todo consumidor passa por ela. **Um número de fuso
> declarado em dois lugares é um número que vai divergir**, e a divergência
> aparece como um bug de estratégia, nunca como um erro de relógio. E ao
> comparar um preenchimento gravado contra o tape, o sinal do desvio é o
> primeiro diagnóstico: sinal consistente aponta para execução, sinal que
> inverte aponta para relógio.
> **Pergunte à plataforma nova:** a hora que a API devolve é UTC ou hora de
> parede do servidor — e existe UMA rota compartilhada que faz essa
> conversão, pela qual todo script novo é obrigado a passar? Antes de
> confiar em qualquer análise, confira se a ferramenta que a produziu usa
> essa rota ou reimplementou a chamada.

### 5.11 Rotina de pesquisa sem a defesa de janela da produção transforma "zero dado" em "zero resultado" — e isso vira a caça a um bug que não existe

Mesmo script, mesma investigação, defeito independente do anterior.
`copy_ticks_range` com `date_from` dentro do pregão do próprio dia devolve
negócio incompleto ou **ZERO, sem levantar exceção nenhuma** — o fato já
medido duas vezes e registrado no item 5.3. A rota de produção se defende
disso: `live/tick_feed.py` recua o pedido para pelo menos
`_SAFE_FETCH_LOOKBACK` (1 dia) e filtra localmente. O script de pesquisa não
tinha defesa nenhuma.

O custo não foi um número errado — foi uma investigação inteira. O CSV
gerado em 04/09 parou em **03/09 10:04** e reportou **"zero trades em
04/09"** num dia que teve atividade real. Esse "zero" foi tratado como
sintoma de estratégia/motor e investigado como tal. Rodando o **mesmo
script, sem mudar uma linha**, 3 dias depois — com o terminal já
sincronizado —, o mesmo dia passou a mostrar **400 trades**.

> **Regra:** dado vindo de terminal só é confiável depois que o pregão
> **fechou E sincronizou** — o de hoje, durante o pregão, é resposta
> provisória mesmo quando volta sem erro. Toda rotina de pesquisa precisa
> da mesma defesa de piso que a rota de produção; sem ela, **"zero
> resultado" é indistinguível de "zero dado"**, e essa ambiguidade custa
> dias procurando um bug que não existe. Corolário barato e obrigatório:
> toda extração confere o ÚLTIMO carimbo de tempo que voltou contra o fim
> da janela pedida, e falha ruidosamente quando o dado para antes — é a
> forma mais barata de nunca mais confundir os dois. Mesma família do item
> 1.6: "não sei" nunca pode se apresentar como "não há".
> **Pergunte à plataforma nova:** a consulta de histórico avisa quando
> devolve MENOS do que a janela pedida, ou entrega um resultado curto em
> silêncio? E a partir de quanto tempo depois do fechamento o dado do
> pregão de hoje fica completo? Enquanto essas duas respostas não
> existirem, nenhuma análise sobre o pregão corrente é conclusão — é
> rascunho.

### 5.12 Um cursor de paginação sem rótulo de fuso apagou 19,3% da base canônica de tick — em silêncio, por meses

`market_data_intraday/mt5_ticks_source.py::fetch_ticks_full_history` paginava o
histórico usando o carimbo do ÚLTIMO tick da página como cursor da página
seguinte, convertido para um `datetime` **sem fuso** (naive). O pacote do
terminal chama `.timestamp()` nesse limite, e um horário sem fuso é resolvido
no fuso da MÁQUINA que executa (BRT, −3h): cada troca de página passou a pedir
a partir de **cursor + 3 horas** em vez de cursor. Com **200.000 ticks por
página**, cada borda engoliu até 3h de negócios — sem exceção, sem log, sem
nada.

Estrago medido na base canônica `data/raw_ticks/WDO_A_.parquet` (16.624.744
ticks, 126 pregões, 2026-02-27→2026-08-31):

- **63 lacunas de exatamente 180,00 minutos**, espaçadas por ~198.500 linhas —
  uma por borda de página (200.000 menos o tick de sobreposição que o dedupe
  come).
- **13.786 de 71.316 minutos de pregão sem um único tick = 19,3% da base.**
- **84 dos 126 pregões afetados** (42 intactos).
- Pior pregão (2026-08-19): **75.710 ticks no parquet contra 134.439** pela
  rota por intervalo — **43,7% do dia ausente**, faixa contínua 10:11–13:09.

A prova de que é o bug e não buraco de mercado veio do confronto contra a rota
por INTERVALO (`fetch_ticks_range`, sem paginação, portanto sem o defeito) em 6
pregões: a rota por intervalo é superconjunto **estrito** (nunca existe minuto
só no parquet), e nos 2 pregões de controle sem lacuna as duas rotas batem
**exatamente** (delta 0) depois do mesmo dedupe. A assinatura de 180,00 min ao
milissegundo, uma vez por página, fecha o caso.

Dois agravantes que valem tanto quanto o número:

1. **A recuperação não é rodar de novo.** A junção do backfill é UNIÃO, então
   reexecutar por cima **preserva** os buracos em vez de corrigi-los — e como o
   backfill parte sempre do mesmo genesis com os mesmos dados, ele reproduz
   exatamente os mesmos buracos. Só apagar o arquivo e regenerar com o código
   corrigido recupera, e só enquanto a retenção do terminal ainda cobrir
   aqueles pregões.
2. **A régua também estava torta.** Esse parquet é a base canônica de tick do
   projeto e foi usado como REFERÊNCIA DE CORREÇÃO numa investigação da mesma
   rodada, para provar que outro cache estava truncado. Uma base com 19,3% de
   ausência silenciosa serviu de padrão-ouro, e ninguém tinha como saber.

> **Regra:** todo limite de tempo entregue a uma API de dados de mercado carrega
> **fuso explícito**. Um horário "sem fuso" não é neutro — ele é reinterpretado
> no fuso de quem executa, e o mesmo código muda de comportamento ao mudar de
> máquina. Numa chamada **PAGINADA** esse deslocamento deixa de ser um erro de
> borda e vira **perda de dado a cada página, proporcional ao tamanho da
> página**. Daí o corolário que é a única defesa real: toda coleta paginada
> confere a **CONTINUIDADE entre páginas** — o começo da página N+1 encosta no
> fim da página N? — e falha ruidosamente quando não encosta. Sem essa
> conferência, a única evidência do defeito é uma lacuna que exceção nenhuma
> anuncia. E quando a junção do armazenamento é união, o dado perdido não volta
> por reexecução: a correção obriga a REGERAR do zero, dentro da janela de
> retenção da fonte.
> **Pergunte à plataforma nova:** a coleta paginada confere que uma página
> encosta na seguinte, ou confia que o cursor caiu no lugar certo? Todo limite
> de tempo que sai daqui carrega fuso explícito, ou algum deles é resolvido no
> fuso da máquina? (5.12)

### 5.13 União por linha inteira quase duplicou 639 negócios reais — a chave certa é IDENTIDADE do evento, não igualdade de linha

Regeneração do parquet canônico de tick do WDO@, fechando de fato o item
5.12 (cursor de paginação sem fuso apagando 19,3% dos minutos de pregão).
Procedimento seguro por desenho: backup primeiro, baixar para arquivo NOVO
em separado, comparar as duas versões, e UNIR — nunca substituir pelo novo,
porque a retenção do terminal MT5 é limitada e irregular e o novo pode não
ter dias que o antigo tinha. Resultado, que deu certo: 63 lacunas de ~180
min → 0; minutos de pregão faltando 13.868 de 71.820 (19,3%) → 342 de
74.100 (0,5%); 16.624.744 → 21.524.225 ticks; 83 pregões reparados,
mediana de 179 min recuperados cada, maior recuperação em 2026-03-03
(208.151 → 398.881 ticks). Zero pregões existiam só no antigo.

O que quase deu errado, e é o item: a comparação apontou **639 linhas**
que existiam "só no antigo" pelo critério de linha inteira — a união
ingênua as teria acrescentado ao novo. Inspecionadas uma a uma, eram os
MESMOS negócios (mesmo timestamp, mesmo preço, mesmo volume), diferindo
APENAS no bit 256 do campo `flags` (1080 no antigo, 1336 no novo): o
terminal revisou um metadado. Unir por linha inteira teria **duplicado
639 negócios reais**, inflando volume e criando negócio fantasma no
backtest — de forma invisível, sem erro nenhum, só um backtest passando a
medir um mercado que não existiu.

A união correta foi feita por **identidade de negócio** (`time, bid, ask,
last, volume, volume_real`) com multiplicidade `count_final =
max(count_antigo, count_novo)` — nunca soma, porque o mesmo negócio pode
legitimamente repetir no mesmo milissegundo. Verificado relendo o arquivo
do disco pelo caminho de PRODUÇÃO (`load_ticks("WDO@")`): 0 negócios do
antigo ausentes ou sub-representados, 0 pregões só no antigo, 0
duplicados por linha inteira.

Resíduo honesto, não escondido: 2026-08-03 e 2026-08-04 continuam vazios
(ausentes nas duas versões — retenção real do terminal, não perda desta
operação); 285 dos 342 minutos residuais são de 2026-07-31, dia em que o
terminal só tem 3.847 ticks a partir de 15:32, idêntico nas duas versões.
Nenhuma estratégia lê `flags` (usam `last`/`volume`), então o achado em
si é cosmético — o perigo estava só no critério de comparação.

> **Regra:** unir duas versões do mesmo dado histórico exige uma CHAVE DE
> IDENTIDADE do evento — o que faz um negócio ser aquele negócio — nunca
> igualdade de linha inteira. A fonte revisa metadado (flags, ids
> internos, campo derivado) sem avisar, e comparação por linha inteira
> transforma cada revisão dessas em duplicata silenciosa. A união também
> precisa de multiplicidade EXPLÍCITA (`max` das contagens, nunca soma),
> porque o mesmo evento pode aparecer legitimamente mais de uma vez no
> mesmo instante. E toda regeneração de base histórica termina com uma
> verificação lida do DISCO pelo caminho de PRODUÇÃO — nunca das
> estruturas em memória recém-montadas: as duas podem concordar e as duas
> podem estar erradas.
>
> Vale registrar junto o procedimento que funcionou, porque ele vai ser
> repetido: backup verificado antes de qualquer coisa → baixar para
> arquivo NOVO em separado → comparar as duas versões e imprimir o que
> cada uma tem de exclusivo → unir por identidade → reler do disco pelo
> caminho de produção → só então trocar o canônico, com o backup
> permanecendo no disco. E a rota de download escolhida importa: por
> INTERVALO (uma chamada por dia civil, meia-noite a meia-noite no
> relógio de parede do servidor) em vez de paginada — não porque a
> paginada esteja errada hoje (foi corrigida no 5.12), mas porque a rota
> por intervalo não tem borda de página onde errar. A classe de bug do
> 5.12 não pode reincidir numa rota que não tem cursor.
> **Pergunte à plataforma nova:** qual é a chave que identifica um evento
> na fonte, e ela sobrevive quando a fonte revisa metadado (flags, ids
> internos, campo derivado)? A verificação final de uma regeneração lê do
> disco pelo caminho de produção, ou confere as estruturas que acabaram
> de ser montadas em memória? (5.13)

### 5.14 O recorte carregava um SEGUNDO bug de fuso, próprio, além do herdado do canônico

Regenerar o canônico (5.12/5.13) obrigou a olhar de novo para
`data/raw_ticks/WDO_A_f1.parquet` — o recorte que a linha F1-tick usa,
gerado por um caminho TOTALMENTE separado (`wdo_grid_reload_f1_tick_probe.
py::buscar_ticks`, que chamava o terminal direto em vez de usar a rota
compartilhada — a mesma classe de defeito do item 5.10). O recorte não
estava só truncado: o índice vinha rotulado **3 horas mais cedo** que o
UTC verdadeiro. A prova veio de bater a MESMA amostra nos dois arquivos: o
tick rotulado `14:58:00.257` no recorte antigo é, no canônico, o mesmo
negócio (mesmo preço, mesmo volume) em `17:58:00.257`. Os dois defeitos se
somaram sem se cancelar — o recorte cobria 212 de 570 minutos de pregão
(38,2%), e os 4.011.197 ticks que tinha estavam TODOS com hora de parede
errada. Um aviso antigo no repositório descrevia isso como "cobre a tarde
inteira do pregão"; era uma janela deslocada 3h que por acidente caía
dentro do horário de pregão, não a tarde. Toda medição feita sobre esse
recorte que dependesse de HORA DO DIA (filtro dia/hora, padrão de
cadência, "o pico mora na primeira hora") leu o horário errado, em
silêncio. Regenerado em 2026-09-07 pela rota corrigida: 4.011.197 →
20.646.379 ticks, cobertura de minutos de pregão 212/570 → 570/570
(38,2% → 100,0%), IS/OOS intactos (72 + 51 dias) — números completos no
AVISO de `wdof1_tick_cache_2026_08_27.py`.

> **Regra:** um dado DERIVADO herda os bugs de fuso do caminho que o
> gerou — e pode acrescentar os seus próprios, independentes. Corrigir a
> fonte não corrige o derivado: o derivado se repara REGERANDO a partir da
> fonte corrigida, nunca sendo "consertado" no lugar. E a verificação de
> que o reparo funcionou tem de casar o MESMO NEGÓCIO (instante + preço +
> volume) nos dois arquivos — foi exatamente esse cruzamento que revelou o
> deslocamento de 3h; comparar contagem de linhas ou intervalo de datas não
> o teria revelado, porque os dois números "batiam" mesmo com o índice
> inteiro deslocado.
> **Pergunte à plataforma nova:** a pergunta 37 (5.10) já cobre a causa —
> script novo reimplementando a chamada em vez de usar a rota compartilhada
> que converte fuso. Este item mostra que o MESMO defeito reincide em
> arquivos diferentes do mesmo projeto quando um deles tem caminho de
> geração próprio (5.14).

### 5.15 Medição feita durante uma regeneração de dado lê a base velha, e não reclama

A calibração do freio de cadência do WDO F1 (`reancora_min_segundos`, que
escolheu o default `10,0`s — ver a docstring do parâmetro em
`WdoGridReloadMaker`) rodou às 21:59 de 2026-09-07 e gravou
`cadencia_sweep.csv` sobre um cache de sessão de 20:55; o canônico
corrigido (5.12/5.13) só substituiu o arquivo em disco às 22:03 — quatro
minutos DEPOIS. A varredura inteira mediu, portanto, sobre a base com
19,3% dos minutos de pregão faltando, sem nenhum sintoma: o argumento de
sanidade usado antes de confiar no resultado ("a base cobre 09:00–18:29 em
125 de 126 pregões") era verdadeiro sobre o PRIMEIRO e o ÚLTIMO registro
de cada dia e falso sobre o MEIO — e a primeira hora do pregão, exatamente
onde mora o pico de envios que a calibração existe para medir, tinha 9,6%
menos ticks na base velha que na corrigida (4.177.643 contra 4.619.105).

> **Regra:** enquanto uma regeneração de dado estiver em curso, NENHUMA
> medição sobre esse dado vale — não importa se o script "leu o arquivo
> certo", o que importa é QUAL VERSÃO daquele arquivo existia no instante
> em que ele rodou. Antes de confiar num número, confira o mtime de TODO
> artefato de medição contra o horário exato da troca do arquivo fonte;
> dizer "o script leu X.parquet" não diz QUAL X.parquet. Corolário: um
> argumento de cobertura que olha só o primeiro e o último registro do dia
> não detecta buraco no MEIO — a checagem tem de contar minutos (ou
> unidades de tempo) distintos cobertos, nunca só os extremos.
> **Pergunte à plataforma nova:** a plataforma nova permite saber se o
> histórico que ela devolve está completo, ou só dá para inferir pelos
> extremos (primeiro/último registro do dia)? (5.15)

**Desfecho:** a varredura foi refeita depois que o canônico corrigido
substituiu o arquivo em disco. O valor escolhido (10s) sobreviveu — mas o
conjunto de pregões que travam mudou por completo, e vale a leitura de por
quê antes de confiar em qualquer "mesmo número, então nada mudou". Ver item
5.16.

### 5.16 Recalibração do freio de cadência na base corrigida: o número sobreviveu, os pregões que travam não

A calibração do `reancora_min_segundos` do WDO F1 (item 4.14) foi refeita
sobre a base de tick regenerada (5.12/5.13), depois que o item 5.15 registrou
que a varredura original tinha rodado, por 4 minutos, sobre a base velha —
19,3% dos minutos de pregão faltando. O default de produção (10s)
**sobreviveu** — mas o conjunto de pregões que travam mudou por completo, e a
vizinhança do parâmetro ficou mais hostil. Grade de 6 valores, 130 pregões,
teto interno `MAX_ENVIOS_POR_MINUTO = 30` (`src/live/intraday_runtime.py`,
item 1.18) — estourar não recusa a ordem, liga `disaster_halt` e cala o robô
o resto do pregão:

| config | pregões travados | pior janela de 60s | trades | líquido R$ |
|---|---|---|---|---|
| 6s | 2/130 | 33 | 16.977 | 84.236,50 |
| 8s | 2/130 | 35 | 16.405 | 82.057,50 |
| **10s (produção)** | **0/130** | **26** | 16.490 | 83.430,00 |
| 12s | 0/130 | 28 | 14.705 | 77.262,50 |
| 15s | 2/130 | 36 | 17.872 | 94.329,00 |
| 20s | 1/130 | 31 | 14.767 | 75.821,50 |

Quem trava e onde: 6s em 2026-06-10 e 2026-06-29; 8s em 2026-03-03 e
2026-06-10; 15s em 2026-08-07 e 2026-08-12; 20s em 2026-06-10. Na base velha
(item 4.14), quem travava eram 6s e 15s — os mesmos DOIS valores da grade,
mas em pregões diferentes; agora 8s e 20s travam também, e 2026-03-03 é
justamente o pregão de MAIOR reparo da regeneração (208.151 → 398.881 ticks,
item 5.13).

Três fatos, não um, fazem o item valer:

1. **Coincidência de número não é reprodução de medição.** 10s continua
   sendo o único valor com 0 travadas e pior minuto 26 — idêntico ao número
   medido na base furada. Mas se o critério de escolha fosse "menor pior
   minuto" em vez de "0 travadas", a base furada dava empate entre
   10s/15s/20s, e a corrigida separa os três. Quando uma medição é refeita
   numa base reparada e devolve o MESMO número, isso não dispensa olhar
   QUAIS casos mudaram de lado — o valor pode estar certo por um motivo
   diferente do que se acreditava, e é o motivo que se leva para a
   plataforma nova, não o número.
2. **A relação é não monotônica, e agora mais do que antes.** 6s trava, 8s
   trava, 10s limpo, 12s limpo, 15s trava, 20s trava — não existe "quanto
   mais freio, mais seguro". Um freio maior concentra os envios que
   sobraram em rajadas piores. Escolher o parâmetro por intuição de direção
   ou por busca em gradiente falha aqui: é preciso varrer a grade inteira
   já mapeada e contar travadas, não olhar a média nem extrapolar de um
   ponto vizinho.
3. **A escolha custa lucro de propósito, e é o certo.** 15s rende
   R$94.329,00 contra R$83.430,00 do 10s — 13% a mais — e trava 2 pregões em
   130. Travar não é perder o lucro daquele dia: é o robô ficar MUDO o
   resto do pregão, com posição possivelmente aberta. Trocar 13% de lucro
   medido por não ter 2 eventos de robô morto só aparece como a escolha
   certa se o critério de decisão for CONTAGEM de travadas — não retorno,
   que sistematicamente recompensa o valor mais arriscado da grade.

Folga residual nomeada e aceita, sem mudança: 4 ordens no pior minuto (26 de
30 do teto), e o pico de envios continua morando na primeira hora do pregão.

**Atualização (2026-09-08, commit `da6f89c`):** o teto único de 30 citado
nesta medição (e no `MAX_ENVIOS_POR_MINUTO` de `src/live/intraday_runtime.py`,
item 1.18) foi substituído por dois níveis —
`COTA_ENVIOS_POR_MINUTO = 120` (recusa só a ordem, robô segue vivo) e
`MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO = 600` (o disjuntor). A folga de 4 sobre
30 media segurança contra o disjuntor antigo; a medição do item 1.22 (mesmo
robô, config de produção) achou pior minuto legítimo de até 42 — acima do
30 antigo e dentro do 120 atual. Ver item 1.22.

**Nota de 2026-09-08, mais tarde (commit `4eb3e4a`):** a coluna `líquido R$`
desta grade saiu do motor que fechava o alvo maker de graça (item 4.8) —
nenhum daqueles valores descreve resultado real, e a geometria de fundo
(T2/S16) não tem edge no motor corrigido (item 6.18). A escolha do parâmetro
**não muda**, e a razão é o fato 3 acima: o critério foi CONTAGEM de travadas,
não retorno. É o exemplo de por que escolher pelo critério certo protege a
decisão de uma correção posterior no modelo de custo — se o critério tivesse
sido "maior líquido", a grade inteira precisaria ser refeita agora.

> **Regra:** re-medir um parâmetro de segurança numa base de dado corrigida
> e obter o MESMO valor não é confirmação — é o ponto de partida de uma
> segunda pergunta: quais casos mudaram de lado, e o critério de escolha
> ainda apontaria para o mesmo valor se olhasse outra estatística (pior
> janela em vez de contagem de travadas, por exemplo)? Além disso, um freio
> de cadência não tem relação monotônica com "mais seguro": ele redistribui
> os envios que sobram em vez de eliminá-los, então a grade tem de ser
> varrida INTEIRA, nunca buscada por gradiente nem por intuição de direção.
> E quando o parâmetro protege contra o robô ficar MUDO (não contra perder
> dinheiro num trade), o critério de escolha certo é a CONTAGEM de eventos
> de trava — nunca o retorno médio, que recompensa sistematicamente o valor
> mais arriscado da grade.
> **Pergunte à plataforma nova:** as perguntas 42 (limite de cadência
> interno vs. imposto pela plataforma, e o que acontece ao estourar) e 43
> (cadência mínima de reancoragem medida contra contagem de trades, não só
> contra o limite de taxa) já cobrem o desenho do freio em si — não
> duplicar. O que este item acrescenta: ao recalibrar esse freio numa base
> de dado corrigida, o critério de escolha foi "menor contagem de travadas"
> ou "maior retorno médio"? E o valor escolhido antes e depois da correção
> teve os MESMOS casos por trás, ou só coincidiu no número? (5.16)

### 5.17 O feed de tick cegou por 44,8 minutos sem levantar erro, e o robô mandou 45 ordens reais contra preços de até 45 minutos atrás — CORRIGIDO 2026-09-08

Pregão de 2026-09-08, slot real `dt-wdo_grid_reload_maker-wdo@-live` (WDO@,
conta 474 em `db/live.sqlite`): **−R$116,00**. O terminal parou de entregar
tick NOVO por **44,8 minutos**, sem levantar erro nenhum. A leitura de barras
fechadas devolveu **lista vazia em 538 passos seguidos** (supervisor a cada
5 s), com a marca d'água congelada em `2026-09-08 14:14:20.804`; no passo
seguinte devolveu **13.644 barras de uma vez**. Não foi evento único: houve um
travamento igual de 8,8 min antes (marca em 13:50:57) e mais dois no slot
sombra (16,2 min e 37,1 min).

Às 15:00:57 UTC o estado da conta mostrava `last_bar_ts = 14:36:21` contra
`last_poll_at = 15:00:57` — o robô estava processando barra de **24 minutos
atrás** e armando ordem-limite no preço daquela barra. O laço de consumo
tratava cada barra atrasada como se fosse tempo real: **45 ordens-limite REAIS
na corretora contra preços de até 45 minutos atrás.** A prova está no diário de
ordens: a ordem 736 (STOP) tem `sent_at=14:14:32` e `created_at=15:00:01` — 45
min e 29 s de atraso; a 771 tem `sent_at=14:36:13` e `created_at=15:00:52`.

A mecânica da perda é o item 4.17 em escala: um limite num preço que já morreu
chega ao book **marketable** e executa na hora como agressor, no pior preço; o
alvo, calculado a partir do mesmo nível morto, já nasce violado. A sequência
real no diário é −R$5,50 por ida e volta, repetida até o freio de perda do dia
(R$112,50) disparar às 15:01:04.

**O que foi descartado como causa, com evidência** — cada um parecia plausível,
e é por terem sido eliminados que a regra abaixo não fala de processo nem de
máquina:

| Suspeita | Evidência que a derruba |
|---|---|
| Processo, lock do banco, CPU, supervisor duplicado | O slot SOMBRA — outro processo do sistema operacional — congelou no **mesmo tick** (`14:14:20.804`, ao milissegundo) pelo **mesmo número de passos** (538) |
| O mercado parou | Pedindo hoje ao terminal os ticks daquela janela: 1.000 a 2.900 ticks por 5 minutos, **zero minutos sem um único negócio** |
| Máquina ou conexão | O slot `dt-copa_win-win@-shadow` (feed de barra M1, outro símbolo) avançou 1 barra por minuto sem falhar durante toda a janela; e o log do próprio terminal não registra perda de conexão nenhuma no período |
| Feed lento | Sondando o mesmo terminal, a chamada exata que o feed faz devolve **109.255 ticks em 109 ms** |

**O despejo cai na HORA CHEIA, e é preciso ao segundo** — rodada de 2026-09-08,
noite, que CORRIGE a versão anterior deste item (ela falava em "fronteira de
meia hora"). Reconstruído de `db/live.sqlite`, tabela `live_orders`, comparando
`sent_at` (hora de MERCADO da barra que gerou a ordem) com `created_at` (hora de
ESCRITA no banco, isto é, quando o despejo chegou): todo travamento aparece como
um bloco de ordens com `sent_at` espalhado e `created_at` IDÊNTICO — o instante
em que o feed voltou a enxergar.

| Feed cegou às (UTC) | Despejou às (UTC) | Cegueira | Slot |
|---|---|---|---|
| 13:51:04 | **14:00:04** | 9,0 min | 474 (real) + 476 (sombra) |
| 14:14:24 | **15:00:01** | 45,6 min | 474 (real) + 476 (sombra) |
| 15:39:50 | **16:00:04** | 20,2 min | 476 (sombra; o real já parado pelo freio de perda) |
| 19:44:02 | **20:00:01** | 16,0 min | 476 (sombra) |

**4 de 4 liberações caem dentro de 5 segundos do topo da HORA.** O passo do
supervisor é 5 s, então o terminal voltou a servir essencialmente em
`hh:00:00.000`. Sob liberação uniforme ao acaso, quatro acertos numa janela de
5 s em 3.600 é ~4·10⁻¹⁰ — não é coincidência. Os INÍCIOS, ao contrário, não têm
padrão nenhum: 13:51, 14:14, 15:39, 19:44. Nenhum outro pregão do banco (30/08
em diante) tem ordem com atraso >5 min, e os travamentos de 31/08 citados na
versão anterior vieram de lacuna no fluxo de eventos, não desse carimbo — a
evidência cravada ao segundo é só a de 08/09.

**O que a segunda rodada descartou**, esvaziando o resto da lista de suspeitos:

| Suspeita | Evidência que a derruba |
|---|---|
| Queda de conexão do terminal | O log do MT5 (`...\logs\20260908.log`, UTF-16) não tem UMA linha de `Network` entre 13:07 e 15:33 UTC — nem perda, nem reautorização. **Cuidado, a leitura ingênua é circular:** a última linha antes do silêncio de 44,8 min é `Trades deal #475853438 buy 1 WDOV26 at 5116.000` (14:14:31 UTC) e a próxima é 15:00 UTC, mas o terminal só loga ORDEM — e o robô parou de mandar ordem porque estava cego. Serve para descartar queda de conexão, não para dizer nada sobre o feed |
| O dado nunca existiu | Sonda read-only hoje (Rico-PRD, build 6182): `copy_ticks_range(WDOV26, 14:14→15:00 UTC de 08/09, COPY_TICKS_TRADE)` devolve **13.864 ticks em UMA chamada**. O histórico EXISTE; o terminal simplesmente não conseguiu servi-lo naquele momento |
| A atualização do terminal (build 6182) | Entrou às 09:08 UTC de 08/09, e o travamento de 31/08 é anterior |

**A causa raiz continua DESCONHECIDA — mas a hipótese que sobrou agora tem
forma.** Não provada: *o terminal serve `copy_ticks_range` a partir de um
instantâneo do histórico de tick que ele só renova no topo da hora.* Isso
explicaria exatamente o que se vê — a cegueira COMEÇA num instante arbitrário
(quando o instantâneo fica velho) e TERMINA cravada na hora cheia (quando um
novo é tirado), com o stream de cotação vivo o tempo todo em paralelo. E tem
parentesco direto com o bug de 2026-08-24 (5.11, a constante
`_SAFE_FETCH_LOOKBACK` em `live/tick_feed.py`): nos dois casos o caminho de
HISTÓRICO de tick devolve dado incompleto ou zero **sem levantar erro nenhum**.
Mesma família de falha, gatilhos diferentes.

**Próximo passo para quem retomar** — não foi feito, orçamento de tempo: sonda
que roda por cima de pelo menos uma virada de hora chamando, no MESMO passo de
5 s, DUAS versões de `copy_ticks_range` para o mesmo símbolo — a janela LARGA
que o feed usa (`agora−24h → agora+2min`) e uma ESTREITA (`agora−60s →
agora+2min`) — e compara o timestamp do último tick das duas. Se a larga
envelhecer e a estreita não, a causa está achada e o conserto é do FORMATO DA
JANELA. Cuidado: estreitar a janela em produção é justamente o que o bug de
2026-08-24 proíbe, então o conserto teria de ser híbrido — janela larga para o
dado, estreita só como sonda de vivacidade.

Não saber a causa **não** impede fechar o buraco: a defesa é contra o SINTOMA
(dado velho), não contra o mecanismo.

> **Regra**, em cinco partes, todas necessárias:
>
> 1. **Feed que devolve "nada" não pode ser indistinguível de feed que devolve
>    "nada de novo".** Aqui a falha era engolida por construção: zero ticks
>    virava resultado vazio sem erro, e a documentação da própria função
>    declarava lista vazia como "o caso NORMAL". Um robô precisa de um relógio
>    de **STALENESS DE DADO**, separado do relógio de "há quanto tempo não
>    rodo". E antes de construir esse vigia: **a distinção quase sempre EXISTE
>    na API e está sendo DESCARTADA pelo código.** Aqui ela estava a uma chamada
>    de `last_error()` de distância e ninguém olhava (correção `6092d4a`,
>    abaixo). Olhe primeiro se a plataforma já não está dizendo "falhei" num
>    canal lateral que o seu código ignora. Corolário do alarme: **vazio com
>    erro OK NÃO pode virar alarme.** Se o robô gritar em todo passo de papel
>    parado, o dono para de ler o diário — e é exatamente assim que o PRÓXIMO
>    sintoma passa despercebido (6.15).
> 2. **Todo detector de buraco tem de medir a idade do DADO, não a do
>    PROCESSO.** O freio que já existia media tempo sem rodar (15 min) e por
>    isso não viu absolutamente nada: o supervisor rodou de 5 em 5 segundos o
>    tempo inteiro. Vigia de vivacidade de processo não é vigia de dado.
> 3. **Barra atrasada pode atualizar estado, nunca virar ordem.** Percorrer
>    barras velhas para manter indicador, âncora e contador quentes é correto;
>    mandar ordem com o preço delas não é. E a recusa vale só para EXPOSIÇÃO
>    NOVA: stop, alvo, cancelamento e fechamento passam sempre, porque não são
>    decisão nova e sim constatação de fato — engolir um fechamento cria
>    posição fantasma (1.6, 2.2).
> 4. **O teto de idade tem de somar o atraso ESTRUTURAL do feed.** Um número
>    fixo mata o feed de barra por construção: uma barra M1 só é legível depois
>    de fechar e seu carimbo é a ABERTURA do minuto, então ela chega com ≥60 s
>    de idade num robô perfeitamente saudável. O teto é *tolerância +
>    atraso nominal do feed*, declarado pelo feed, nunca uma constante única.
> 5. **Descarte nunca é silencioso.** Robô que para de mandar ordem sem dizer
>    nada é exatamente o modo de falha do item 6.15 — a janela censurada que
>    depois é lida como edge negativo.

**A correção**, commit `60034e3` (*"barra velha nao vira ordem"*):
`MAX_ATRASO_PARA_ORDEM_SEGUNDOS = 120,0` somado ao atraso nominal declarado
pelo feed (120 s no tick, 180 s no M1), portão por barra nos três pontos que
podem gerar exposição nova, arme velho tratado como "não enviei" (devolvido à
máquina de estados em vez de ficar órfão), e uma linha de aviso por lote com a
contagem de barras recusadas. Os 120 s **não** são chute: saíram de sonda no
próprio terminal repetindo a chamada exata do feed de 5 em 5 s, 260 passos —
p50 0,14 s, p99 4,17 s, máximo 4,27 s (o máximo é limitado pelo passo do
supervisor). 120 s é ~29× o p99, folga suficiente para que o portão só dispare
em cegueira de verdade, não em latência.

**A segunda correção**, commit `6092d4a`: o `60034e3` atacava o SINTOMA (barra
velha não vira ordem); este ataca a INVISIBILIDADE.

- **Medido no terminal real, read-only:** o pacote `MetaTrader5` DÁ a distinção,
  e ela estava sendo jogada fora. Símbolo inexistente → `copy_ticks_range`
  devolve `None` com `last_error() == (-4, 'Terminal: Not found')`. Janela de
  madrugada, sem negócio nenhum → array **vazio** com
  `last_error() == (1, 'Success')`. Ou seja: `None`, ou vazio com código
  NEGATIVO, é falha de leitura; vazio com código OK é papel parado.
- O código antigo fazia `if resultado is None or len(resultado) == 0: return
  DataFrame()` — os dois casos no MESMO `return`, sem chamar `on_error`. Foi
  assim que 538 chamadas seguidas de cegueira ficaram idênticas a um papel
  parado.
- Corrigidos os QUATRO caminhos de leitura (`copy_ticks_range`,
  `copy_ticks_from`, `copy_rates_range`, `copy_rates_from_pos`) em
  `market_data_intraday/mt5_ticks_source.py` e `mt5_source.py` — inclusive o M1,
  que nunca foi visto cegar, porque o `return` que engolia era idêntico (7.1: ao
  corrigir um bug, varra todas as instâncias do padrão).
- **A segunda metade do buraco, que ninguém tinha visto: o `on_error` dos feeds
  nunca era ligado a nada.** `scripts/run_live.py` chama
  `live.intraday_feed.feed_for(...)` SEM callback, então até o erro que já era
  reportado (falha de conexão ao terminal) morria no caminho. O novo
  `live/feed_health.py::RegistroDeLeitura` faz a falha viajar POR FORA do valor
  de retorno, porque o contrato "lista vazia, nunca exceção" não pode mudar: um
  passo que levanta derruba o robô em vez de deixá-lo esperar o terminal voltar.
- `IntradayLiveRuntime._vigia_leitura_do_feed` grava UMA linha no diário por
  TRANSIÇÃO (cegou / voltou, com a contagem de passos), nunca uma por passo: a
  5 s por passo, 45 min de cegueira viraria 538 linhas iguais e o diário ficaria
  ilegível justamente no pregão em que o dono mais precisa lê-lo.
- 7 testes novos, todos falhando no código antigo. Suíte inteira verde (1.790
  passed).

> **Pergunte à plataforma nova:** (a) a API de dado distingue "não há negócio
> novo" de "não consegui ler o histórico"? Em MT5 a resposta é **SIM**, mas por
> um canal LATERAL (`last_error()`) que é fácil de ignorar — confira se a
> plataforma nova tem equivalente, e **qual é o valor dele quando a leitura foi
> legitimamente vazia**, senão o portão vira alarme em todo papel parado. Se não
> distingue de jeito nenhum, qual é o sintoma observável de um feed cego e em
> quanto tempo ele aparece? (b) existe alguma
> garantia de que o histórico de tick/barra que ela devolve está sincronizado
> com o stream de cotação em tempo real, ou os dois podem divergir por dezenas
> de minutos sem erro? (c) qual é o atraso ESTRUTURAL de cada granularidade (o
> equivalente a "barra M1 só existe depois que o minuto acaba")? É esse número
> que entra no teto de idade de barra — sem ele, o portão ou é frouxo demais
> para servir ou recusa o feed saudável. (d) o histórico que a plataforma serve
> é renovado por EVENTO ou por RELÓGIO? Se por relógio, com que cadência? No
> MT5, 4 de 4 travamentos de 08/09 liberaram dentro de 5 s do topo da hora.
> (5.17)

### 5.18 Um `@` no símbolo do instrumento congelou o painel de dinheiro — a tela mostrou os números do instante em que a página abriu, sem erro e sem aviso, por tempo indeterminado — CORRIGIDO 2026-09-09

O painel `/operacao` parou de se atualizar sozinho para o robô do WDO. O dono
precisava dar **F5 na mão** para ver caixa, contagem de ordens (x/y), posições e
diário mudarem — e operou assim sem saber por quanto tempo. Medido com navegador
instrumentado contra o servidor real: o poll de 20 s do cartão disparava certo, o
servidor respondia **HTTP 200 com o HTML novo e correto**, e a camada de troca no
navegador **descartava a resposta inteira, 100% das vezes**. Nenhuma tela de erro,
nenhum aviso, nenhuma cor diferente: o cartão simplesmente exibia os números do
instante em que a página havia sido carregada.

**A causa.** O resumo do cabeçalho do cartão (o `<summary>`, que mostra o caixa e
"operando/parado") fica FORA do nó que carrega o gatilho de poll
(`hx-trigger="every 20s"`), então ele viaja como troca fora-de-banda
(`hx-swap-oob`). A biblioteca monta o alvo dessa troca como `"#" + id` **CRU**
(`oobSwap`, htmx 1.9.12). O id era derivado do id do slot, o slot carrega o
símbolo, e o símbolo do mini-dólar contínuo é `WDO@` — então a tela pedia
`querySelectorAll('#ops-sum-dt-wdo_grid_reload_maker-wdo@-shadow')` e recebia
`SyntaxError: ... is not a valid selector`, porque `@` não é caractere de
identificador na linguagem de seleção. A exceção sobe como `htmx:swapError`
DENTRO de um poll de fundo: ninguém escuta, e o navegador não tem por que
reclamar. Um caractere do símbolo de mercado congelou o painel de dinheiro.

É o item 5.17 do outro lado do sistema — lá o FEED cegou sem levantar erro, aqui
a TELA cegou sem levantar erro — e nos dois casos o sintoma que o dono vê é o
mesmo: "nada está acontecendo".

**O agravante, que é a parte mais importante.** O sufixo `.SA` das ações seria a
MESMA falha, mas em silêncio total e sem nem exceção:
`#ops-sum-dt-gremah-pmam3.sa-shadow` é seletor **VÁLIDO** — só que significa "id
`ops-sum-dt-gremah-pmam3` COM a classe `sa-shadow`", que não existe. Zero match,
zero erro, zero atualização. A falha ruidosa do futuro foi sorte; a versão
silenciosa já estava no mesmo código, esperando o próximo robô de ação.

**A correção.** Um filtro `dom_id` em `src/dashboard/app.py`: todo id de HTML
derivado de dado (slot, símbolo, robô) passa por uma tradução **injetiva** para o
conjunto `[A-Za-z0-9_-]` — `_` é o escape, `_` literal vira `__`, qualquer outro
caractere vira `_` + hexa (`@` vira `_40`) —, aplicada nos DOIS lados: no `id=` e
em todo seletor `#...` que aponta para ele. Dois testes novos: um monta o cartão
do slot `dt-wdo_grid_reload_maker-wdo@-shadow` e varre TODO `id=` e todo
`hx-target="#..."` da página e do fragmento contra o conjunto aceitável; o outro
fixa a **injetividade**, porque dois slots diferentes que virassem o mesmo id
fariam a troca escrever o caixa de um robô no cartão de outro. Verificado no
navegador real depois da correção: os 4 swaps por ciclo passam, `htmx:swapError`
sumiu.

> **Regra, em duas metades — e a segunda vale mais que a primeira:**
> (a) nenhum identificador de TELA derivado de dado de mercado (símbolo, robô,
> conta) pode carregar caractere que a camada de seleção da plataforma não saiba
> ler. Símbolo de mercado tem `@`, `.`, `/`, `=`; o namespace da tela quase nunca
> tem. E a tradução tem de ser **injetiva**, porque identificador colidido
> escreve número de dinheiro no lugar errado — pior que não atualizar.
> (b) **atualização automática de tela que falha em silêncio é pior que
> atualização que não existe**: o dono não tem como distinguir "nada mudou no
> robô" de "a tela parou de receber". Toda tela que se atualiza sozinha precisa
> dizer QUANDO se atualizou com sucesso pela última vez, ou marcar visualmente o
> congelamento — senão o painel mente sobre dinheiro por tempo indeterminado e
> ninguém percebe. Vale igual em qualquer stack: web, terminal, ou o painel
> nativo da plataforma nova. (5.18)

### 5.19 Encerrar um contrato de futuro devolvendo o NOCIONAL ao caixa: R$375,00 viraram −R$4.706,00 numa única remoção de robô — e numa posição COMPRADA o mesmo código teria INFLADO o caixa em ~R$5.100

2026-09-09. O dono removeu pelo painel o robô de SOMBRA do mini-dólar
(`dt-wdo_grid_reload_maker-wdo@-shadow`), com a intenção de guardar os dados e
religar depois. A rotina de remoção fecha localmente a posição simulada que
estava aberta — short de **1 contrato de WDO@, entrada 5133,0**, gravada com
`quantity = -1`. O caixa simulado, que estava em **R$375,00**, foi para
**−R$4.706,00**. A aritmética inteira cabe numa linha:

```
375,00  +  (5133,00 × -1)  +  52,00  =  -4.706,00
```

São **três defeitos empilhados, todos da mesma raiz: conta de AÇÃO aplicada a
FUTURO**.

1. **O crédito de fechamento devolvia o NOCIONAL** (`preço de entrada ×
   quantidade`). Para 100 ações a preço em reais isso está certo — o dinheiro
   preso na posição É o preço cheio. Para 1 contrato de futuro, **nada do
   nocional foi caixa em momento nenhum**: o que ficou preso foi a MARGEM
   (R$150 no WDO@). Como a quantidade era negativa (short), o crédito virou um
   **débito de R$5.133,00**.
2. **O sinal foi aplicado duas vezes.** O código inverte o delta de preço
   porque o lado é short E multiplica por uma quantidade que já carrega o
   sinal. Uma **perda de 52 pontos virou "lucro de R$52,00"**. E faltava ainda
   o valor do ponto: 52 pontos de WDO são **R$520,00**, não R$52,00 — o mesmo
   multiplicador ausente do item 5.7, num terceiro caminho de código.
3. **O preço de saída veio de um cache.** A rotina pediu "o último preço do
   WDO@" e recebeu **5185,0 de 2026-08-28** — fechamento de minuto salvo em
   arquivo, **12 dias velho**, enquanto o mercado negociava a ~5133. Nenhum
   erro, nenhum aviso: um preço antigo tem exatamente a mesma forma de um
   preço atual.

**O que salva e o que assusta.** O estrago ficou no ledger SIMULADO
(`cash_sombra`), nunca no caixa real: o caminho do robô de dinheiro de verdade
não faz essa conta de "liberado", então nenhum real foi contabilizado errado.
Mas o sinal do erro **depende do lado da posição**. Numa posição COMPRADA
(`quantity = +1`) a mesma expressão **credita ~R$5.100 de nocional inexistente**
em vez de debitar. **Caixa inflado é pior que caixa negativo**, porque não chama
atenção — o negativo pelo menos parou o dono e gerou esta investigação — e o
caixa é justamente o número que dimensiona quantos contratos o robô abre no
pregão seguinte. O bug simétrico de 5.7 já tinha ensinado isso: erro que se
cancela no round-trip só aparece na posição AINDA ABERTA.

É a terceira aparição da mesma família em dois lugares diferentes do sistema —
5.7 (nocional em vez de multiplicador), 5.8 (sinal da quantidade invertendo
capital comprometido) — agora num caminho que nenhuma das duas correções tinha
visitado: o **desmonte**. Rotina de encerramento/limpeza é onde a contabilidade
menos é olhada e onde o erro fica gravado.

> **Regra, em três partes:**
> **(a) Encerrar posição de DERIVATIVO não devolve nocional ao caixa: devolve
> MARGEM.** Nocional de contrato futuro nunca foi caixa, então nunca pode
> voltar como caixa. Toda rotina de contabilidade que multiplica preço por
> quantidade tem de saber, no ponto do cálculo, se o instrumento é ação
> (nocional = capital comprometido) ou contrato (margem = capital
> comprometido) — e o **valor do ponto entra na conta**, não é detalhe de
> exibição. Se existir mais de um lugar no sistema capaz de creditar caixa por
> fechamento, todos leem a mesma função; um deles esquecido é este item.
> **(b) Quantidade com sinal (negativo = vendido) e um campo de lado separado
> ("short") são DUAS representações da mesma informação.** Usar as duas na
> mesma expressão inverte o sinal duas vezes e devolve lucro onde houve
> prejuízo. Escolha UMA convenção e **afirme a escolha no ponto de leitura**
> (normalize a quantidade para magnitude, ou ignore o campo de lado) — nunca
> deixe as duas vivas na mesma linha de aritmética.
> **(c) Preço "salvo" não é preço "atual".** Toda rotina que fecha, avalia ou
> dimensiona posição a partir de um preço em cache precisa carregar a **IDADE**
> desse preço junto com o valor, e **recusar ou avisar** quando ele for velho
> demais para a decisão que está tomando. Um cache sem carimbo de tempo é uma
> afirmação sobre o mercado que ninguém pode auditar — o mesmo modo de falha do
> feed cego de 5.17 e da ordem-limite ancorada em preço defasado de 4.17, aqui
> com 12 dias de defasagem.
> **Pergunte à plataforma nova:** ao encerrar um contrato futuro, o que
> exatamente volta para o saldo disponível — e a plataforma distingue margem de
> nocional em algum lugar, ou isso é responsabilidade nossa? (5.19)
>
> **Rendeu dois itens no mesmo dia**, os dois achados varrendo o padrão em vez
> de só consertar esta rotina: **5.20** (a mesma rota de desmonte também não
> cobrava corretagem nem emolumentos — duas contabilidades para o mesmo
> fechamento) e **5.21** (a causa comum: o valor do ponto morava no catálogo de
> ROBÔS, não no do INSTRUMENTO — quarta aparição da família).
> **E mais dois, ainda 2026-09-09**: **5.22** (o mesmo `trade_tick_value` podia
> chegar zerado do terminal, sem validação nenhuma antes da primeira divisão)
> e **5.24** (o defeito nº 3 desta lista — o preço de saída veio de um cache —
> fechado por RECUSA em vez de aviso: a mesma barra de 28/08 era, além de
> velha, anterior à própria abertura da posição).

### 5.20 Fechar pelo caminho do robô cobrava corretagem; fechar removendo o robô pelo painel não cobrava nada — R$0,50 de diferença num contrato de WDO@, e o número pequeno é justamente o problema

2026-09-09, achado na mesma varredura que produziu o item 5.19. O mesmo evento
econômico — encerrar uma posição aberta — tinha **duas rotas** no sistema, com
contabilidades diferentes:

- **Rota operacional** (o robô fecha a posição): `IntradayTrade.pnl_brl`
  subtrai `fees_total`, e `_on_closed` credita no caixa o resultado
  **LÍQUIDO** de corretagem e emolumentos.
- **Rota administrativa** (o dono remove o robô pelo painel com posição
  aberta): a rotina de desmonte marcava a mercado, calculava o resultado
  **BRUTO** e creditava isso no caixa. Nenhuma taxa.

A diferença por remoção, medida:

| instrumento | posição | crédito a mais |
|---|---|---|
| WDO@ | 1 contrato | **R$0,50** (corretagem fixa de futuro, R$0,25 por perna) |
| PMAM3 | 100 ações | **R$0,01** (emolumentos percentuais sobre o nocional) |

Corrigido fazendo as **três** rotas chamarem a mesma função de custo do motor
(`backtest.intraday.costs.fees_round_trip_brl`, montada a partir do perfil do
símbolo): o desmonte da conta sombra, a limpeza da conta do robô real, e a
**estimativa mostrada no popup de confirmação** — que é a terceira e a mais
fácil de esquecer, porque ela não move dinheiro, só promete um número que o
passo seguinte tem de honrar.

**Por que um item por R$0,01.** O valor é ridículo de propósito, e é isso que
torna o caso instrutivo: o dano nunca foi o centavo. O dano é o caixa do painel
**divergir em silêncio** do que a mesma operação teria custado — e neste sistema
o caixa não é um relatório, é uma **variável de realimentação**: é ele que
dimensiona quantos contratos o robô abre no pregão seguinte
(`contracts_from_capital_operacional`). Um erro pequeno, sistemático e sempre no
mesmo sentido (a rota manual é a generosa) alimenta a entrada do
dimensionamento. Erro pequeno numa malha fechada não fica pequeno: ele integra.
E, diferente do erro de 5.19, este não estoura a tela — R$0,50 nunca faz o dono
estranhar nada, então ele só apareceria por conferência de extrato contra
extrato, que é exatamente a conferência que ninguém faz.

Vale registrar o que ficou de fora **por decisão declarada, não por
esquecimento**: a *slippage*. No motor ela é um ajuste no PREÇO de execução de
uma saída a mercado, e no desmonte não há execução nenhuma — o preço é marcação
a mercado pelo melhor preço conhecido. Piorá-lo em 1 tick seria inventar um
preenchimento que ninguém observou. A diferença entre "custo que a rota omitia"
e "custo que a rota não pode conhecer" tem de estar escrita no ponto do
cálculo; senão a próxima varredura fecha a lacuna errada.

> **Regra:** **todo caminho que encerra posição — normal, de emergência,
> manual, ou de desmonte — passa pela MESMA função de custo.** Se existir mais
> de uma rota para o mesmo evento econômico, elas convergem no ponto em que o
> dinheiro é contado, nunca em cópias paralelas que "fazem a mesma conta". Uma
> rota **administrativa** que não cobra o que a rota **operacional** cobra é um
> vazamento estrutural: só aparece quando alguém compara os dois extratos, e
> ninguém compara os dois extratos. Corolário de desenho: quando um caminho
> precisar omitir uma parcela do custo por impossibilidade física (aqui, o
> deslize de um preenchimento que não existe), a omissão é **declarada no ponto
> do cálculo** — custo ausente sem justificativa escrita é indistinguível de
> bug. É a família de 5.7/5.19 vista pelo lado do CUSTO: lá eram duas fórmulas
> de "quanto voltou ao caixa", aqui são duas fórmulas de "quanto custou para
> sair".
> **Pergunte à plataforma nova:** pergunta 78. (5.19, 5.7)

### 5.21 O valor do ponto morava no catálogo de ROBÔS, não no do INSTRUMENTO — e um quarto caminho de código afirmava "1 ponto = R$1,00" para qualquer símbolo, WDO@ incluído

2026-09-09. O valor do ponto de cada futuro (**R$10,00** no WDO@, **R$0,20** no
WIN@) estava declarado no registro de **robôs** (`strategy/daytrade/registry.py`),
ao lado de parâmetros que de fato pertencem a um robô — alvo, stop, risco por
trade. Duas consequências reais, encontradas no mesmo dia:

1. **A contabilidade de remoção não conseguia apurar o resultado de uma conta
   cujo robô saísse do catálogo.** Para converter pontos em reais ela precisava
   perguntar ao robô — e conta órfã (robô renomeado, aposentado ou removido) é
   exatamente o caso em que alguém remove o slot. O dado necessário para fechar
   a conta dependia de um objeto que já não existia.
2. **Um QUARTO caminho de código montava a config de qualquer símbolo com
   "1 ponto = R$1,00".** `dashboard/live_service.py::build_runtime` passava
   `trade_tick_value=0.01, trade_tick_size=0.01` — verdade em ação, **erro de
   10×** num WDO@ e de 5× num WIN@. Inofensivo **hoje** apenas porque nada
   naquele runtime lia `config.costs`: basta alguém passar a ler, e o erro vira
   número na tela sem nenhuma mudança na linha errada. Lacuna que só é
   inofensiva por acidente de leitura é lacuna aberta.

Corrigido movendo o valor do ponto para o **perfil do símbolo**
(`SymbolProfile.point_value_brl`), onde já moravam o tamanho do tick e a margem,
e tornando-o **obrigatório** em perfil de futuro — perfil de futuro sem valor do
ponto passou a levantar erro em vez de assumir 1,0. `config_for` confere o valor
declarado contra o `trade_tick_value/trade_tick_size` lido do terminal e
**recusa a config** se os dois divergirem: é a amarração que faz a duplicação
inevitável (nosso perfil × o que a corretora reporta) falhar alto em vez de
divergir em silêncio.

**Esta é a QUARTA aparição da mesma família neste documento**, sempre num
caminho de código que a correção anterior não tinha visitado:

| item | data | onde | o que estava errado |
|---|---|---|---|
| 5.7 | 2026-08-31 | contabilidade de caixa ao vivo e cards do painel | nocional em vez de multiplicador (preço de futuro tratado como reais) |
| 5.8 | 2026-08-31 | `LivePosition.market_value` | quantidade com sinal invertendo capital comprometido |
| 5.19 | 2026-09-09 | rotina de REMOÇÃO do robô | nocional devolvido ao caixa + sinal duplo + valor do ponto ausente |
| **5.21** | **2026-09-09** | **catálogo de robôs e `build_runtime`** | **a constante do instrumento não morava no instrumento** |

5.7 e 5.8 foram corrigidos como bugs de dois caminhos. 5.19 achou um terceiro.
Este achou o quarto — e, mais importante, achou a **causa comum** aos quatro:
enquanto o valor do ponto for um número que cada caminho busca onde der, cada
caminho novo tem chance de buscá-lo errado.

> **Regra:** **valor do ponto, tamanho do tick e margem são propriedades do
> INSTRUMENTO, não do robô.** Dois robôs no mesmo símbolo têm obrigatoriamente
> os mesmos três números — logo esses números não podem morar em nenhum lugar
> que pertença a um robô, a uma tela, a um script ou a uma sessão. Onde a
> arquitetura obrigar a duplicar, tem de existir **teste ou checagem em runtime
> que FALHE quando as cópias divergirem** — duplicação sem amarração é
> divergência agendada, não risco hipotético. E o corolário mais caro, agora
> provado quatro vezes neste arquivo: **corrigir uma instância de um padrão sem
> varrer todas as outras não corrige o padrão — só move a data da próxima
> ocorrência.** Depois de achar a causa raiz, a pergunta não é "onde estava o
> bug?", é "que outros lugares respondem a mesma pergunta por conta própria?"
> (7.1, 5.7, 5.8, 5.19)

**Rendeu mais dois itens no mesmo dia**, fechando o rollout de
`core.instruments` para além da contabilidade de caixa: **5.22** (a leitura
CRUA do terminal nunca era validada antes da primeira divisão — o mesmo
número podia chegar zerado e ninguém percebia) e **5.23** (o `tick_size`, o
terceiro número da mesma família, estava redigitado como default de
construtor de robô, com um comentário afirmando o contrário havia 13 dias).

### 5.22 O terminal pode devolver economia inválida, e ninguém conferia — `trade_tick_value=0` zera o P&L inteiro em silêncio

2026-09-09, achado durante o mesmo fechamento do rollout de
`core.instruments`. `market_data_intraday.mt5_source.symbol_economics`
devolvia `float(info.trade_tick_value)` e `float(info.trade_tick_size)` direto
do MT5, sem validar nada. O MT5 reporta **`trade_tick_value = 0`** para um
símbolo que ainda não foi selecionado/sincronizado no Market Watch do
terminal — situação comum (terminal recém-aberto, símbolo novo, reconexão),
não hipotética.

Num perfil de **AÇÃO** — onde `_confere_valor_do_ponto` (item 5.21) nem roda,
por ser checagem só-para-futuro — o zero passava direto para dentro de
`config_for` e zerava o P&L da rodada inteira, **em silêncio**: nenhuma
exceção, nenhum aviso, todo trade valendo R$0,00. Num **futuro**, a mesma
divisão `trade_tick_value / trade_tick_size` — usada tanto por
`_confere_valor_do_ponto` quanto por `IntradayCostModel.from_symbol_info` —
estourava um `ZeroDivisionError` cru, sem dizer o símbolo nem a causa.

O que faz isto pertencer à mesma família dos itens 5.7/5.19/5.21: o mesmo
número que zera alimenta **três proteções ao mesmo tempo** — P&L, portão de
capital (quantos contratos cabem no caixa) e disjuntor (quanto de perda é
tolerável antes de parar). Zerar `point_value_brl` desliga as três de uma vez,
e a tela continua mostrando uma rodada plausível: nada pisca vermelho porque
nada excedeu limite nenhum — o limite em si é que ficou mudo.

Corrigido em 2026-09-09 por `_checa_economia_do_terminal`
(`backtest/intraday/profiles.py`), chamada dentro de `config_for` ANTES de
qualquer divisão: recusa `trade_tick_value`/`trade_tick_size` não-finito ou
≤0 para **todo** perfil — ação incluída, não só futuro, que é a diferença
para `_confere_valor_do_ponto` — com mensagem nomeando a causa mais comum
(símbolo fora do Market Watch) em vez de deixar o `ZeroDivisionError` explicar
sozinho.

> **Regra:** todo dado numérico que sai da corretora/feed e vai alimentar
> dinheiro é validado na FRONTEIRA, antes de virar conta — não no ponto de
> uso, três chamadas depois. E trate **"0" como o valor mais perigoso que
> existe**, não o mais inofensivo: ele não levanta exceção, não aparece
> esquisito em tela nenhuma, e ainda assim silencia toda proteção que
> dependa dele. Prefira falhar alto com mensagem que nomeia a causa comum a
> deixar um `ZeroDivisionError` cru explicar o problema para quem estiver de
> plantão.
> **Pergunte à plataforma nova:** o que exatamente a API devolve para um
> instrumento que existe mas não está "carregado"/selecionado no terminal —
> zero, `None`, um erro explícito, ou o valor do último símbolo consultado?
> Dá para distinguir, na resposta, "este instrumento vale zero" de "eu não
> sei o valor deste instrumento"? Se não der, todo número lido de lá exige um
> guard de sanidade ANTES do primeiro uso — validado por VALOR (finito e
> maior que zero), nunca só por tipo. (5.21, pergunta 79)

### 5.23 O `tick_size` que a produção realmente usava vinha do default do construtor — e um comentário afirmava o contrário havia 13 dias

2026-09-09, mesma investigação que produziu o item 5.21. O `tick_size` (passo
de preço) do WDO F1 (`wdo_grid_reload_maker.WDO_TICK_SIZE`) e do CopaWin
(`tick_size=5.0` no construtor) estava duplicado em relação à fonte real do
motor (`SymbolProfile.price_tick_size`), e nada amarrava as duas cópias — o
mesmo padrão de 5.21, agora no PARÂMETRO DE CONSTRUÇÃO do robô, não na
contabilidade de caixa.

O detalhe que torna este item mais grave do que "só mais uma constante
redigitada": **ninguém passa `tick_size=` explícito ao construtor de nenhum
robô de produção** — nem `strategy.daytrade.registry._KWARGS_PADRAO`, nem
`scripts/run_live.py::build_intraday`. Logo a grade de ordens que o robô AO
VIVO efetivamente usa vinha do **DEFAULT da classe** (`WDO_TICK_SIZE = 0.5`,
`CopaWin.__init__(tick_size=5.0)`), nunca de uma config lida do perfil. E o
comentário ao lado do default de `WDO_TICK_SIZE`, escrito em 2026-08-28 e
sem mudar por **13 dias**, afirmava exatamente o contrário: *"só um DEFAULT
de conveniência para quem instancia sem passar o valor do perfil — rodar de
verdade sempre passa `tick_size=` explícito, vindo de
`profile_for("WDO@").price_tick_size`"*. Era falso, e nenhum teste checava a
afirmação — só o comentário garantia que ela fosse verdade.

Nenhum teste ligava esse default ao `SymbolProfile.price_tick_size` que o
MOTOR (backtest e execução real) usa para avaliar a MESMA ordem. Se as duas
cópias divergissem — a corretora republicando a especificação do contrato de
forma diferente, por exemplo — o robô posicionaria a ordem numa grade e o
motor a avaliaria em outra, sem nada quebrar: só um preenchimento fora da
grade real, silencioso, a mesma classe de defeito do item 5.7.

Corrigido em 2026-09-09 pela criação de `src/core/instruments.py`
(`InstrumentEconomics`, tabela `FUTUROS`, `economics_for()`), que virou fonte
única de `point_value_brl`, `price_tick_size` e `margin_per_contract_brl`
para as duas pontas — `backtest.intraday.profiles.SymbolProfile` de um lado,
`strategy.daytrade.registry`/os construtores dos robôs do outro. O default de
`WDO_TICK_SIZE` e de `CopaWin.tick_size` passou a ler
`economics_for(...).price_tick_size` em vez de um número digitado, e o
comentário foi reescrito para dizer a verdade: é ESTE número que posiciona a
grade em produção.

> **Regra:** um comentário que afirma COMO o código é chamado ("isto nunca
> roda sem X explícito") **não é verificação** — é uma alegação sem teste, e
> alegação sem teste tem a mesma taxa de erro que qualquer outro código não
> testado. Ou existe um teste que amarra as duas pontas (o valor que o robô
> de fato usa == o valor que o perfil do motor declara), ou as duas pontas
> leem a MESMA fonte — nunca duas cópias com um comentário prometendo que
> elas nunca vão divergir. Corolário mais caro: **um default de construtor
> que a produção efetivamente usa não é "default de conveniência" — é a
> configuração de produção, escondida no lugar onde ninguém procura
> configuração.** Antes de descrever qualquer parâmetro como "default para
> quem não passar o valor certo", confira quem de fato chama o construtor e
> o que cada chamador passa.
> Não gera pergunta nova na Parte 8 — é regra de arquitetura do NOSSO código
> (onde mora a constante, quem lê o quê), não uma pergunta sobre o
> comportamento da plataforma nova. Reforça a pergunta 28 (5.7, 5.21): valor
> do instrumento vem de UM lugar indexado pelo INSTRUMENTO, nunca redigitado
> por robô, tela ou script.
> **Quinta aparição da mesma família** — 5.7, 5.8, 5.19, 5.21 e esta.

### 5.24 Aviso não substitui recusa: uma barra anterior à própria abertura da posição quase virou caixa simulado

2026-09-09, mesmo dia e mesma rotina do item 5.19. O desmonte de robô
encerrava a posição simulada contra a barra mais recente salva em parquet,
sem julgar a idade dela — e o caso real que abriu o item 5.19 é exatamente
essa barra: **5185,0 de 28/08 marcando uma posição de WDO@ aberta em
09/09**. Trocar só a FONTE do preço (item 5.19 — cotação ao vivo do terminal
primeiro, parquet como retaguarda) não fecha a lacuna: a retaguarda CONTINUA
existindo, e o código, ao cair nela, emitia um **aviso** e creditava o
resultado do mesmo jeito. Aviso não serve para isto: quando ele aparece na
tela, o número **já entrou** no `cash_sombra` — e o caixa não é relatório, é
a variável que dimensiona quantos contratos o robô abre no pregão seguinte
(mesmo argumento do item 5.20). Uma barra de 28/08 marcando uma posição
aberta em 09/09 não é só "velha": é uma barra **ANTERIOR à própria abertura
da posição**, uma impossibilidade lógica — não existe preço de saída que
anteceda a entrada.

A correção (`_preco_velho_demais`, `src/dashboard/live_teardown.py`) não
escolheu entre as duas saídas que pareciam ser as únicas — "encerrar com o
preço velho mesmo assim" ou "travar a remoção e pedir intervenção do dono"
(essa segunda também é modo de falha caro: o robô fica preso no painel, com o
ativo bloqueado para qualquer outro robô, por causa de um terminal que o
dono talvez nem consiga abrir agora). Existe uma terceira que domina as
duas, e o módulo já a tinha escrita para o caso vizinho ("não veio preço
nenhum"): **encerra pelo PRÓPRIO preço de entrada**, credita só o custo
conhecido (corretagem + valor do ponto), e diz por quê. Resultado bruto zero
erra, no máximo, pelo que a posição realmente andou; um preço de outra
quinzena erra pelo que o MERCADO andou em duas semanas — e no caso real
aquele único número decidia R$520,00 num caixa simulado de R$375,00.

Dois critérios de recusa, e só o segundo tem constante para discutir: **(1)**
a barra salva é anterior à data de abertura da própria posição —
impossibilidade lógica, dispensa qualquer julgamento sobre "quão velho é
demais";
**(2)** mais de `_IDADE_MAXIMA_DO_PRECO_DIAS = 5` dias corridos — cobre a
maior distância NORMAL entre dois pregões da B3 (feriado emendado num fim de
semana, quinta a terça), de modo que "o terminal estava fechado no fim de
semana" nunca cai na recusa, e "o parquet não é atualizado há mais de uma
semana" sempre cai.

Duas ressalvas registradas por serem honestas, não por serem confortáveis:
os 5 dias são **escolha** de calendário, não medição de defasagem — um WDO@
anda mais que a conta inteira num ÚNICO pregão, então um preço dentro do
limite ainda pode estar materialmente errado; ele só deixa de ser absurdo. E
a recusa não cobre a rota REAL de propósito: lá o preço vem de
`broker.last_price`, que é "agora" ou `None` — não existe "velho" nesse
caminho, então não há o que recusar.

> **Regra:** dado externo que vai virar um LANÇAMENTO no ledger tem
> VALIDADE, e a validade é checada ANTES do lançamento — nunca avisada
> depois. Quando o dado falhar a checagem, a saída correta raramente é o par
> binário "usar mesmo assim" × "travar a operação inteira": procure primeiro
> o fallback que o código já escreveu para o caso vizinho de "dado ausente"
> — ele costuma ser conservador por desenho (aqui, "sem preço" já caía no
> preço de entrada), e a mesma saída geralmente serve para "preço presente,
> mas inválido".
> **Pergunte à plataforma nova:** ver pergunta 77, estendida — a API expõe a
> IDADE do dado que devolve, distinguindo "última cotação conhecida" de
> "cotação de agora"? (5.19, 5.20)

### 5.25 O feed reautenticava a CADA leitura em vez de uma vez por processo — 16 alarmes de "cegueira" em 4 episódios, e nenhum era cegueira de verdade — CORRIGIDO 2026-09-14

Pregão de 2026-09-14: os 5 slots de day trade ao vivo (contas 545, 547, 548,
549, 550 — WIN@, WDO@ ×3, PMAM3) gravaram no diário, em **4 episódios**, **16**
eventos `error`: `feed nao conseguiu LER o terminal (<símbolo>): connect:
falha ao conectar ao terminal MT5 (last_error=(-6, 'Terminal: Authorization
failed'))`, cada um seguido de "feed voltou a ler o terminal apos 1 a 3
passo(s) de falha" — 5 a 15 s de cegueira DECLARADA por episódio. Episódios às
12:13, 12:44, 13:30 e 13:31 UTC (09:13, 09:44, 10:30 e 10:31 BRT).

**A evidência que achou a causa** mora em duas observações do mesmo diário,
nenhuma delas isolada bastaria:

1. Os CINCO processos falharam na MESMA janela de 1 a 4 s e voltaram juntos.
   Cinco processos independentes não erram em união por acaso — a falha é do
   terminal, não do robô.
2. No MESMO processo e no MESMO segundo, `MT5Feed` (relógio) e `MT5Broker`
   (ordens) não reclamaram de nada — as ordens continuaram sendo enviadas
   normalmente durante a janela.

A diferença entre quem falhou e quem não falhou não era o terminal: era que
`MT5Broker.connect()` e `MT5Feed._connect()` guardam `_connected` e chamam
`mt5.initialize()` **uma vez por processo**, enquanto
`market_data_intraday/mt5_source.py::_connect` e `mt5_ticks_source.py::_connect`
chamavam **a cada leitura** — de 5 em 5 s, vezes 5 processos, ≈1 pedido de
autorização por segundo contra o terminal, o pregão inteiro. E
`mt5.initialize(login=..., password=..., server=...)` com credenciais não é
consulta barata: repete AUTORIZAÇÃO ao servidor da corretora (Rico-PRD).
Enquanto o terminal está reconectando ou ocupado, essa autorização volta `-6
RES_E_AUTH_FAILED` — com a sessão IPC já existente perfeitamente viva e capaz
de entregar tick. **O robô declarava cegueira por causa de uma pergunta que
não precisava ter feito.** Nenhum dos 16 eventos era cegueira de verdade.

**O agravante de método, que tem de sobreviver à troca de plataforma.** As
DUAS funções `_connect` já diziam na própria docstring: *"Idempotente — mesmo
padrão de `MT5Feed._connect`/`MT5Broker.connect`"*. Não eram. A promessa
estava no comentário e o cache não estava no código. É a mesma família do
item 3.8 (`queue_ahead_qty` nasceu em 2026-08-26 com default `0.0` e viciou um
mês de medição justamente por PARECER implementado): **um invariante afirmado
em docstring e não implementado é pior que um invariante ausente, porque
encerra a pergunta de quem for conferir.** Ninguém procura o que já achou.
Quem abrisse o arquivo leria "idempotente" e iria embora.

**O agravante 2 — o alarme que grita sem motivo treina o dono a ignorar o
alarme.** Esta linha de diário existe por causa do item 5.17 (2026-09-08: o
terminal parou de entregar tick de WDO@ por 44,8 minutos, `closed_bars_since`
devolveu lista vazia em 538 passos seguidos sem UMA linha em lugar nenhum, e o
robô mandou 45 ordens-limite reais contra preços de até 45 min atrás,
−R$116). O alarme foi construído justamente para aquela cegueira. Um alarme
que dispara 16 vezes num pregão por falso positivo corrói exatamente a única
defesa que existe contra a cegueira real.

> **Regra**, portável — vale em qualquer corretora e qualquer linguagem:
>
> 1. **Handshake de sessão é uma vez por processo, nunca por leitura.**
>    Reautenticar a cada ciclo transforma um blip do lado do servidor em
>    cegueira declarada do lado do robô. O que decide se o robô está cego é o
>    RESULTADO da leitura, nunca o sucesso do handshake — testar o handshake
>    para decidir sobre o dado é trocar o termômetro pelo termostato.
> 2. **Invariante afirmado em docstring e não implementado é pior que
>    invariante ausente** (mesma família do 3.8). Quando um comentário promete
>    uma propriedade, ou existe teste que a prende, ou a promessa sai do
>    comentário.
> 3. **Todo falso positivo de alarme é dívida contra o alarme verdadeiro.**
>    Antes de aceitar um alarme ruidoso como "chato mas inofensivo", conte
>    quantas vezes ele dispara por pregão e contra o que ele foi construído
>    para proteger.

**A correção**, novo módulo `src/market_data_intraday/mt5_connection.py`: uma
sessão IPC por PROCESSO, com cache invalidado por `terminal_info() is not
None` — liveness do IPC, deliberadamente **não** `terminal_info().connected`,
que é o handshake com o servidor de negociação: quando ele cai, reinicializar
não conserta nada — e 3 tentativas espaçadas de 0,35 s só no caminho em que a
sessão precisa nascer. `mt5.shutdown()` nunca é chamado, de propósito: o IPC
do pacote `MetaTrader5` é GLOBAL do processo e o mesmo processo tem um
`MT5Broker` com `_connected=True` em memória — derrubar a sessão para "limpar"
trocaria um alarme falso por uma ordem que não sai. Os dois `_connect`
passaram a delegar para o módulo novo. Coberto por `tests/test_mt5_connection.py`
(10 testes; o central prende que 50 leituras seguidas produzem 1
`initialize`, e outro prende que a sessão cacheada sobrevive a um
`initialize` que passou a falhar).

**Risco residual, registrado e não tocado nesta correção:**
`MT5Broker._connected` e `MT5Feed._connected` cacheiam para sempre, sem
NENHUMA revalidação. Se o terminal reiniciar de verdade, esses dois seguem
achando que estão conectados — falha OPOSTA à corrigida aqui.

> **Pergunte à plataforma nova:** perguntas 100 a 102 da Parte 8. (5.25)

### 5.26 Série de contrato CONTÍNUO é re-encadeada a cada rolagem — unir um fetch novo por carimbo de tempo quase reescreveu oito meses de histórico do WDO@

Uma auditoria da base M1 canônica (2026-09-16) achou três pregões truncados
no `WDO@`: 11/09 com 371 barras de 570, 14/09 com **67 barras de 570**
(faltava o pregão inteiro até 17:23 BRT) e 15/09 com 534. O terminal MT5
tinha os três completos, então o conserto parecia trivial: baixar tudo de
novo e unir — o mesmo padrão que já tinha funcionado na regeneração do
canônico de tick (5.12/5.13).

**Unir a base inteira quase destruiu oito meses de histórico.** Ao comparar
o fetch novo com o parquet existente antes de gravar, apareceu: **93.159 das
107.242 barras comuns divergiam**, com deslocamento de preço de **~37 a ~42
pontos**. Causa: `WDO@` é um contrato **CONTÍNUO** — uma série sintética que
a corretora **RE-ENCADEIA a cada rolagem**. O mesmo carimbo de tempo tem
preço diferente dependendo de QUANDO foi baixado. A fronteira era nítida: da
rolagem de 28/08 para cá a divergência é **0,000**; antes dela, ~37,4,
crescendo para ~42 em dezembro.

O `merge_m1` do repo tem a regra "em carimbo sobreposto o fetch NOVO vence"
— correta para correção legítima de provedor (o caso que 5.12/5.13
resolveram), catastrófica aqui: ela reescreveria oito meses com outro
encadeamento e deixaria o arquivo EMENDADO — barras antes de 30/12 no
ajuste antigo, porque estão fora da janela de 100.000 barras do servidor, e
o resto no novo. Isso é pior que o buraco original: um buraco você enxerga,
uma emenda de encadeamento não.

A primeira execução chegou a gravar a união completa. Foi detectada pela
linha de comparação do próprio script, **restaurada do backup**, e refeita
cirurgicamente: só as barras dos três dias furados (todos posteriores à
fronteira de 28/08, logo no mesmo encadeamento dos vizinhos). Resultado
final: 738 barras adicionadas, 2 alteradas (ambas dentro dos três dias,
mudança máxima de 1,0 = dois ticks, a barra que ainda se formava na
captura), nenhuma barra perdida.

**O que salvou:** o procedimento BACKUP → fetch → **COMPARA** → união →
confere, o mesmo herdado da rodada de 2026-09-07 (5.12/5.13). O passo
COMPARA não é burocracia: foi ele que transformou um desastre silencioso num
aviso. Sem ele, a união teria sido gravada e o repo carregaria oito meses de
preço deslocado ~37-42 pontos sem nenhum sintoma — nenhuma exceção, nenhuma
lacuna nova para uma auditoria futura encontrar.

De brinde, a mesma auditoria confirmou que o `WIN@` está íntegro: 17 minutos
ausentes em 110.014 barras, maior buraco de 6 minutos, zero violação de
OHLC, zero duplicata, e os 11 dias úteis sem barra são todos feriado de B3 —
o contraste mostra que o defeito é do WDO@ ser contínuo, não de método de
coleta.

> **Regra**, portável — vale em qualquer corretora e qualquer linguagem:
>
> 1. **Série de contrato CONTÍNUO/sintético não é histórico imutável: ela é
>    RECALCULADA a cada rolagem.** Re-baixar e unir por carimbo de tempo
>    reescreve o passado em silêncio — o dado antigo e o dado novo podem
>    concordar em timestamp e discordar em preço, e nenhum dos dois está
>    "errado": são dois encadeamentos diferentes da mesma série sintética.
> 2. **Antes de unir qualquer fetch novo a uma base histórica, MEÇA a
>    divergência nas barras que existem nos dois lados.** Divergência
>    sistemática (mesmo sinal, crescendo com a distância no tempo) não é
>    correção do provedor: é outro encadeamento, e unir mistura duas séries
>    incompatíveis num arquivo só. Divergência zero de um lado da fronteira e
>    diferente de zero do outro é a assinatura de uma rolagem no meio.
> 3. **Conserto de base é CIRÚRGICO.** Só o trecho comprovadamente furado, e
>    só depois de confirmar que aquele trecho está do mesmo lado da última
>    rolagem que os dados vizinhos — nunca a base inteira "por segurança".
> 4. **Backup antes, comparação no meio, conferência depois — nessa ordem,
>    sempre.** É a mesma disciplina do 5.12/5.13 aplicada a uma classe de bug
>    diferente (encadeamento de contrato contínuo, não fuso de paginação); o
>    procedimento generaliza porque ataca o sintoma comum — fetch novo
>    substituindo dado antigo sem prova de que os dois descrevem a mesma
>    coisa —, não a causa específica.
>
> **Pergunte à plataforma nova:** pergunta 111 da Parte 8. (5.26)

### 5.27 O mapa de contrato de futuro nasce VAZIO quando o robô sobe antes da abertura — e vazio não é "nada a mapear" — CORRIGIDO 2026-09-21

> **DESFECHO, 2026-09-21 — corrigido no mesmo dia, em DUAS camadas**, porque
> a hora em que o dono clica em "Iniciar operação" não é controlável:
>
> 1. **`dashboard/live_control.start()`**: a condição de redetecção passou
>    de `if config.mt5_symbol_map is None:` para
>    `if not config.mt5_symbol_map:`. Um mapa `{}` é detecção que NÃO
>    RESOLVEU, nunca "nada a mapear". Redetectar sobre `{}` custa uma
>    consulta que para ação devolve `{}` de novo em milissegundos (a
>    detecção só olha ticker terminado em `@`); deixar o vazio grudado
>    custa um pregão. Testes:
>    `test_start_com_mapa_de_futuro_VAZIO_REDETECTA_o_contrato` e
>    `test_start_com_mapa_de_futuro_PREENCHIDO_nao_redetecta` em
>    `tests/test_live_control.py`.
> 2. **`IntradayLiveRuntime._check_simbolo_negociavel`** (novo portão de
>    início de pregão, ao lado dos de relógio/AutoTrading/caixa): no
>    primeiro passo do pregão — que por definição acontece com o mercado
>    ABERTO, portanto com book — o robô pergunta se o símbolo de DESTINO
>    aceita ordem (`MT5Broker.aceita_ordem`, que lê `trade_mode` do
>    símbolo que `symbol_for` resolve). Se não aceita, ele REDETECTA o
>    contrato e instala no broker em memória
>    (`MT5Broker.adota_symbol_map`), sem reiniciar o processo — reiniciar
>    recalibraria a sessão a frio, e um robô intradiário recalibrado no
>    meio do pregão é outro robô (a "faixa de abertura" do `wdo_orb`
>    viraria o horário do restart). Se ainda não aceita, grava IMPEDIMENTO
>    e não opera. Só em execução real (`executor is not None`): sombra não
>    manda ordem, então `trade_mode` do destino não muda nada para ela.
>    Testes:
>    `test_simbolo_continuo_sem_mapa_se_AUTOCORRIGE_no_primeiro_passo`,
>    `test_simbolo_que_nao_negocia_e_nao_tem_conserto_vira_IMPEDIMENTO`,
>    `test_simbolo_negociavel_nao_paga_deteccao_nenhuma`,
>    `test_sombra_nao_e_barrada_por_simbolo_que_nao_negocia`.
>
> O invariante que sustenta as duas camadas: **detecção automática de
> ambiente que só roda no momento de SUBIR o robô herda a hora em que
> alguém clicou.** Se a detecção depende do mercado estar aberto, ela
> precisa de uma segunda chance no primeiro instante em que o mercado está
> aberto — e, falhando as duas, o robô declara que não pode operar em vez
> de ficar verde.
>
> A camada (1) existe por causa de um TERCEIRO defeito, só visível ao ir
> reiniciar o slot: a config salva em `db/live_process.json` guardava
> `mt5_symbol_map: {}`, então reiniciar o slot reproduziria o bug de novo.
> Aviso de método: um valor degradado que é PERSISTIDO deixa de ser um
> acidente de um dia e passa a ser o default de todos os dias seguintes.

2026-09-21, slot `dt-wdo_orb-wdo@-live`, dinheiro real, robô `wdo_orb`,
capital R$375. O slot foi iniciado às 08:54 BRT, **6 minutos antes** da
abertura do pregão (09:00). `dashboard/live_control.detect_futures_symbol_map`
roda a cada "Iniciar operação" e devolve o ticker mapeado para ELE MESMO
quando nenhum contrato candidato tem BOOK DE DOIS LADOS (`bid>0` e `ask>0`)
— regra documentada em `MT5Broker.detect_futures_symbol_map`, criada de
propósito para não escolher contrato morto. Às 08:54 nenhum contrato de WDO
tinha book (mercado fechado): a detecção degradou para `WDO@ -> WDO@`, e o
filtro `simbolo != broker.symbol_for(ticker)` removeu a entrada — o mapa
salvo foi `{}`.

`live_control.start()` só detecta quando `config.mt5_symbol_map is None`;
`{}` não é `None`, e `if config.mt5_symbol_map:` é falso, então
`--mt5-symbol-map` NÃO foi passado na linha de comando. Confirmado no argv
do processo (pid 8724): `run_live.py ... --slot dt-wdo_orb-wdo@-live
--execution-mode live ... loop --seconds 5`, sem a flag. O slot irmão
`wdo_grid_reload_maker`, iniciado às 09:25 (mercado já aberto), recebeu
`--mt5-symbol-map "{\"WDO@\": \"WDOV26\"}"` corretamente.

Consequência medida no terminal: `mt5.symbol_info("WDO@").trade_mode == 0`
(SYMBOL_TRADE_MODE_DISABLED), `bid=0.0`, `ask=0.0`; `WDOV26` tinha
`trade_mode == 4` e book cheio (bid 5131,5 / ask 5132,0). `MT5IntradayExecution`
passa `ticker=self.symbol` = `"WDO@"` para o broker, e
`MT5Broker.symbol_for("WDO@")` sem mapa devolve `"WDO@"` — toda ordem real do
dia seria recusada pelo servidor com retcode 10017 TRADE_DISABLED, o mesmo
incidente de 2026-08-28 voltando por uma porta nova. Agravante:
`position_state("WDO@")` e o `_ensure_protecao` também consultam `WDO@`,
cegando a conferência de posição/proteção para qualquer posição que
existisse no contrato real. Custo do dia: zero intents, zero orders no
`db/live.sqlite` (conta 574) — o robô passou o pregão inteiro incapaz de
executar uma única ordem. Em SOMBRA o defeito é invisível (não manda ordem),
o que torna a armadilha pior: o cartão do painel fica verde.

> **Regra (portável).** Detecção automática de contrato/símbolo tem de
> rodar — ou ser reconferida — com o MERCADO ABERTO, e um mapa VAZIO num
> robô de futuro é estado INVÁLIDO, não "nada a mapear". Um ticker
> contínuo/sintético (`WDO@`, `WIN@`) sem entrada no mapa significa que a
> ordem vai para um símbolo que a corretora não aceita. O invariante: antes
> do primeiro envio real do pregão, o robô confirma que o símbolo de destino
> aceita ordem (`trade_mode` habilitado e book de dois lados); se não
> aceita, ele grava IMPEDIMENTO e não finge estar operando. Degradar em
> silêncio para o sintoma (ordem recusada mais tarde) só é aceitável se
> alguém for VER a recusa — e num dia sem sinal ninguém vê.
> **Pergunte à plataforma nova:** pergunta 117 (nova). (5.4, 1.24, 3.18)

---

### 5.28 O vigia de cegueira criado depois do item 5.17 não pega o modo de falha em que o feed devolve lista VAZIA "com sucesso" — 36 minutos cego, zero linha no diário — CORRIGIDO 2026-09-21

Mesmo pregão de 2026-09-21 dos itens 4.33 e 5.27. O feed de tick do `WDO@`
parou de entregar negócio novo às 09:06:54 BRT e só voltou às ~09:43 —
**36 minutos**, **437 passos `daytrade_espera` seguidos**, **três robôs de
WDO@ travados na MESMA marca d'água**
(`ultima_barra=2026-09-21 12:06:54.934+00:00`), e **ZERO linha em qualquer
diário**. Um processo NOVO lendo o mesmo terminal no meio do apagão também
recebia truncado (`WDO@` parava em 12:06 enquanto `WDOV26` entregava até
12:43) — o defeito era do TERMINAL, não do processo: não havia
autocorreção possível, só detecção.

O vigia que já existia (`_vigia_leitura_do_feed`, criado depois do item
5.17) não pega este modo de falha: ele olha `falha_de_leitura`, e a leitura
"deu certo" o tempo todo — devolveu lista VAZIA. Lista vazia é o caso
NORMAL de um papel sem negócio (está no próprio contrato de
`closed_bars_since`), então o feed não tem como acusar por conta própria.
**Quem pode distinguir "papel parado" de "terminal não entregando" é quem
tem o RELÓGIO na mão** — e isso é o runtime, não o feed.

**A correção** (`IntradayLiveRuntime._vigia_cegueira_do_feed`): mede tempo
de PAREDE sem barra e, passado o limite, grava `warn` no diário + IMPEDIMENTO
no painel; quando o dado volta, grava a linha de volta com quantos minutos
ficou cego e o impedimento sai sozinho. Uma linha por TRANSIÇÃO, nunca uma
por passo — a 5s por passo, os 36 minutos daquele dia virariam 437 linhas
iguais e o diário ficaria ilegível justamente no pregão que mais precisava
ser lido. A marca zero é a ABERTURA DA SESSÃO (`_start_session`), não a
criação do objeto: o slot subiu às 08:54 e os 6 minutos de mercado fechado
não podem contar como cegueira.

O limite vem do FEED, não do runtime (`minutos_sem_barra_para_alarme`, na
mesma forma de `nominal_delay_seconds`) — e é DIFERENTE por tipo de feed,
decisão do dono, 2026-09-21:

| tipo de feed | limite | por quê |
|---|---|---|
| tick (futuro líquido) | 5 min | `WDO@` mede mediana de ~336 negócios por MINUTO — cinco minutos secos não é mercado parado, é o terminal |
| M1 (ação) | 30 min | `PMAM3` foi medida em ~18 barras num pregão INTEIRO; 5 minutos ali é terça-feira normal |

A razão de não ser um número único é a lição: **um alarme que dispara em
situação normal treina o dono a ignorá-lo, e isso é pior do que não ter
alarme** — o mesmo corolário do item 5.17 ("vazio com erro OK NÃO pode
virar alarme").

Testes: `test_feed_de_TICK_sem_barra_por_minutos_vira_warn_e_impedimento`,
`test_feed_cego_escreve_UMA_linha_e_outra_quando_volta`,
`test_feed_M1_de_acao_iliquida_NAO_alarma_em_5_min`,
`test_limite_de_cegueira_vem_do_FEED_nunca_do_runtime`,
`test_robo_que_subiu_antes_da_abertura_nao_nasce_cego`.

**O que o vigia NÃO faz, e precisa estar escrito:** ele avisa e impede, não
conserta — o dado não está na nossa mão. Quem cuida de não operar contra
preço morto quando o feed volta continua sendo
`MAX_ATRASO_PARA_ORDEM_SEGUNDOS` (item 5.17); quem cuida de não virar o dia
com posição aberta continua sendo `_aplicar_piso_de_relogio`. O que faltava
era o dono SABER.

> **Regra (portável).** Um detector de falha que só reage a "a leitura deu
> erro" está cego para o modo de falha em que a plataforma devolve sucesso
> vazio — e vazio-de-sucesso é, por construção, indistinguível de "não
> aconteceu nada hoje". Quem decide se um vazio prolongado é normal ou é
> apagão é quem conhece o RITMO esperado daquele instrumento, não o feed
> (que só sabe se a chamada teve erro). O limite de alarme não pode ser uma
> constante única do sistema: tem de vir do próprio feed/instrumento, e ser
> medido contra o ritmo real de negociação — um limite calibrado para um
> papel líquido dispara em falso em qualquer papel ilíquido, e a
> consequência de um falso alarme é o dono aprender a ignorar o alarme
> verdadeiro.
> **Pergunte à plataforma nova:** pergunta 118 (nova). (5.17, 4.33, 5.27)

---

### 5.29 Restart no meio do pregão entregava OUTRO robô, porque o warm start nascia DESLIGADO — CORRIGIDO 2026-09-21

Mesmo pregão de 2026-09-21 dos itens 4.33 e 5.27/5.28 — o quinto conserto do
dia. O slot `dt-wdo_orb-wdo@-live` (dinheiro real) foi reiniciado às 11:19
BRT, com o pregão em curso. O robô voltou a operar com `_open_ts` = a
primeira barra que ele VIU, ou seja 11:19 — e a "faixa de abertura dos 15
primeiros minutos do pregão", de onde o `WdoOrb` tira stop E alvo, passou a
ser **11:19..11:34** em vez de **09:00..09:15**. Geometria que nenhum
backtest descreve, operando dinheiro de verdade.

**A causa: um default que nunca foi decisão sobre esses robôs.**
`IntradayLiveRuntime._needs_warm_start` era:

```
corte = self._fixed_anchor_until
if corte is None:
    return False          # <- aqui
return now < corte
```

O `return False` para `corte is None` (robô SEM conceito de âncora fixa) era
o valor de queda de uma política escrita em 2026-08-21 para a `Gremah`, que
era o único robô com âncora fixa na época. A política dela está certa e
continua valendo (ligar warm start depois de `fixed_anchor_until` carregaria
uma ordem fixa já obsoleta, só detectável dentro de `on_bar` — uma barra de
defasagem amplificada pela dependência de caminho). Mas ela nunca disse nada
sobre robôs sem âncora fixa — e todos eles herdaram "nunca faz warm start"
por acidente de escrita: `wdo_orb`, `wdo_grid_reload_maker`,
`wdo_grid_fade_off_t3`, `copa_win`, `win_retangulo`, `wdo_retangulo`,
`wdo_evo`.

**A correção:** o default foi INVERTIDO. Warm start passou a ser o padrão; a
exceção é a janela de âncora fixa ainda vigente (a da `Gremah`, preservada e
coberta por teste). Razão de fundo, que é o invariante do projeto: **no
backtest a estratégia SEMPRE viu o pregão inteiro, da abertura até a barra
corrente.** Não existe lá um robô que acorda às 11h sem saber o que
aconteceu às 9h. Começar a frio no meio do pregão produz estado interno que
nenhum backtest descreve — e para a família de robôs cuja geometria sai da
ABERTURA do dia isso não é "menos calibrado", é OUTRA ESTRATÉGIA.

**Provado no caso real, no mesmo pregão.** Depois da correção, o restart do
mesmo slot registrou no diário: `warm start, 66700 barra(s), ordem em pe @
5128.5000 (stop 5143.5000 / alvo 5106.0000)`, com `_open_ts` reconstruído em
09:00:45 e faixa 5128,0..5149,0 (21 pontos = 42 ticks, teto do stop mordendo
em 30). A ordem foi confirmada na corretora: ticket 5963781017, SELL LIMIT 1
contrato @ 5128,50, SL 5143,50, sem TP nativo (o alvo vai como limite
fatiada depois do fill, item 4.24). Antes da correção o mesmo restart dava
faixa 11:19..11:34.

**As duas objeções que pareciam impedir a correção, e por que não impedem**
— esta é a parte que precisa sobreviver, porque as duas eram plausíveis e as
duas estavam erradas:

1. *"Warm start pode mandar ordem contra preço morto"* — NÃO pode. A
   semente vai até `now` (`session_bars_until(session, now)`), então a
   ordem que o warm start arma foi decidida na barra MAIS RECENTE. O replay
   reconstrói ESTADO; a decisão é fresca. É por isso que o portão de barra
   velha de `_on_limit_placed` (item 4.33, que este caminho não atravessa)
   não faz falta ali. **Esta objeção foi levantada sem verificar o código, e
   custou uma rodada inteira de hesitação.**
2. *"O custo reabre o incidente do item 5.9"* (as 31 buscas de histórico
   que derrubaram dois slots pelo watchdog de heartbeat) — NÃO reabre, e a
   diferença é de duas ordens de grandeza. Medido contra o terminal real em
   2026-09-21, pior caso do repo (feed de TICK do `WDO@`, pregão INTEIRO):
   **6,9s** (18/09, 113.615 barras) a **14,4s** (17/09, 127.215 barras),
   somando busca + replay, UMA vez por processo por pregão. O piso do
   watchdog é **900s** (`live_control._HEARTBEAT_FLOOR_SECONDS`), e a
   docstring desse piso já registra que o catch-up do próprio robô passa de
   180s numa única chamada de `run_once`. 31 × ~14s = ~430s era o problema;
   1 × 14s não é.

O teste que guardava o item 5.9
(`test_robo_sem_hooks_de_seed_sobrescritos_nao_busca_historico_nenhum`)
afirmava "ZERO buscas" e passou a falhar. **A asserção estava medindo a
coisa errada, e isso também é lição:** o invariante do 5.9 é "nenhuma busca
para alimentar hook NO-OP" — e as 31 buscas dele eram todas de pregões
ANTERIORES, alimentando `seed_volume_window`/`seed_daily_volatility`/
`seed_typical_trade_size`. Essas continuam em zero. O teste foi reescrito
para medir exatamente isso (nenhuma busca de pregão anterior) e travar a
busca do pregão de HOJE em exatamente 1 — mais que 1 é regressão do 5.9,
nenhuma é o robô perdendo a abertura.

> **Regra (portável).** Reiniciar o processo não pode trocar a estratégia.
> Se o estado interno do robô depende do começo da sessão, um processo que
> sobe no meio dela tem de RECONSTRUIR a sessão desde a abertura, não
> começar do zero — porque o backtest que validou o robô sempre viu o
> pregão inteiro. E o invariante mais geral, que vale além deste caso: **um
> default que nasceu como valor de queda de uma política escrita para OUTRO
> caso não é uma decisão** — quando uma política nova cobre um subconjunto
> (aqui: robôs COM âncora fixa), verifique explicitamente o que acontece com
> o complemento, em vez de deixá-lo herdar o `else`.

Testes novos que travam a regressão, em `tests/test_intraday_live_runtime.py`:
`test_restart_no_meio_do_pregao_RECONSTROI_desde_a_abertura`,
`test_robo_com_ancora_fixa_VENCIDA_continua_comecando_a_frio` (a exceção da
Gremah, preservada), `test_robo_com_ancora_fixa_VIGENTE_faz_warm_start_como_sempre`
e `test_partida_na_abertura_sem_barra_nenhuma_ainda_cai_no_frio` (a partida
normal das 09:00, que continua caindo no caminho a frio porque a semente vem
vazia). Suíte inteira depois do conserto: 2.215 testes, 1 skip (o skip é o
de sempre, do pacote MetaTrader5 real instalado nesta máquina).

> **Pergunte à plataforma nova:** pergunta 119 (nova). (3.14, 4.33, 5.9, 5.27)

---

### 5.30 Leilão de abertura publica cotação INDICATIVA que o backtest trata como preço real — inflou a largura de um retângulo em até 17.335 pontos e quase zerou um EA portado para MQL5

2026-10-05, porte do `win_retangulo` + EMA34 para MQL5
(`mt5/WinRetanguloEma34.mq5`), testado no Testador de Estratégias (WINV26,
modelagem "cada tick é baseado em um tick real", jan-ago/2026). A curva de
patrimônio subiu a um pico de ~R$36.000 e caiu quase a zero sem nenhuma
negociação correspondente na lista de deals do teste — as 238 negociações
reais do teste tinham preços sãos, entre 168.200 e 190.915 pontos.
Investigado puxando ticks reais direto da corretora via API Python do MT5
(`MetaTrader5.copy_ticks_range`), não só os avisos do log do Testador:
confirmado que o **leilão de ABERTURA da B3, entre 08:55 e 09:01 BRT,
publica cotações INDICATIVAS (não negociáveis)** que oscilam violentamente
antes da abertura de verdade — medido num único pregão (2026-08-12): bid
variando de 171.305 a 188.640 e ask de 154.345 a 172.180, uma oscilação de
até **17.335 pontos**, tudo dentro da janela de 6 minutos antes da
abertura. Uma vela M1 construída com essas cotações entra na janela de
detecção de um retângulo (que calcula topo/piso por quantis de máxima/
mínima) e infla a LARGURA calculada em dezenas de milhares de pontos — como
o stop e o alvo desse robô são frações dessa largura, a posição fica sem
gerenciamento de risco nenhum, só acompanhando o preço real por semanas.
Dois outros EAs testados na mesma sessão (`Win.ex5`, `Win_c1.ex5`, que não
calculam largura/amplitude a partir de extremos de uma janela) não
mostraram esse sintoma.

> **A regra (portável).** Qualquer estratégia que calcule uma distância
> (largura de canal, amplitude, faixa, ATR simplificado) a partir de
> máximas/mínimas de velas de 1 minuto precisa excluir explicitamente a
> janela do leilão de abertura (e, por simetria, a de fechamento/leilão de
> encerramento) do cálculo — ou aplicar um teto de sanidade na própria
> vela (faixa máxima plausível; aqui 2.000 pontos) antes de deixá-la
> entrar em qualquer cálculo de amplitude. Cotação PUBLICADA não é o mesmo
> que cotação NEGOCIÁVEL: um leilão por chamada pode publicar lances e
> ofertas muito distantes do preço de equilíbrio até o encontro final, e
> um backtest/EA que trata toda cotação como preço de mercado real herda
> esse ruído como se fosse volatilidade genuína. A correção aplicada foi
> dupla: um horário de início configurável (pula 08:55-09:01) e um teto
> de sanidade (`RangeMaximoBarraPontos`, default 2000 pontos) que descarta
> qualquer vela, a qualquer hora, com faixa maior que isso.

> **Pergunte à plataforma nova:** pergunta 128 (nova). (5.2, 5.7, 6.47)

Cruza com **5.2** (horário de sessão por instrumento), **5.7** (preço de
futuro em pontos, não em reais) e **6.47** (dado real revela artefato que
a base agregada não contém) — mesma família: dado PUBLICADO não é o mesmo
que dado NEGOCIÁVEL, e só a checagem contra o book/tick real expõe a
diferença.

### 5.31 Uma grandeza ancorada no calendário, em futuro com vencimento, tem de dizer EM QUAL CONTRATO é medida — a abertura do mês do contrato de trás marcou "mês de baixa" numa alta de 6%: −R$545 no testador contra +R$1.466 na simulação

Medido em 2026-10-06 no EA novo `mt5/WinCincoMedias.mq5` (WIN, Testador de Estratégias do MT5, WINV26 M5, 12/08 a 01/10/2026, capital R$ 1.000). A estratégia tem um filtro de lado pela **abertura do mês**: preço acima da abertura do mês, só compra; abaixo, só venda. A simulação Python media o mês em séries segmentadas por contrato, **começando na rolagem** — o mês só contava a partir do dia em que o contrato virou o principal. O EA v1.00 usou a abertura do mês do **próprio contrato do gráfico** (a barra mensal do WINV26), que em agosto/2026 começava em 03/08 — quando o WINV26 ainda era o contrato de trás, pouco negociado (volume ~1000× menor) e com preço **2 a 3 mil pontos acima** do mercado da época.

Resultado: o filtro marcou "mês de baixa" de 12/08 a 08/09, durante uma alta de 6%. O robô só vendeu e depois ficou parado. No testador: **−R$ 545** (41 trades, 26,8% de acerto), contra **+R$ 1.466** que a simulação mostrava para o mesmo período.

O que impediu a leitura errada ("a estratégia não funciona") foi reproduzir o EA em Python **com o histórico inteiro do contrato**: bateu **39 de 41 trades** (−R$ 641,50). O EA estava fiel ao código; o que divergia era a **definição do dado**. Corrigido na v1.01: âncora = `max(início do mês, dia seguinte ao vencimento do contrato anterior)`; esperado **+R$ 1.547 / 80 trades** em 13/08–01/10.

> **A regra.** Toda grandeza "ancorada no calendário" (abertura do mês/semana, VWAP ancorada, máxima/mínima do mês...) em futuro com vencimento precisa declarar **EM QUAL CONTRATO** ela é medida, e o robô e o backtest têm de usar a mesma definição. Medir no histórico do contrato antes de ele virar o principal mistura o preço de um mercado ilíquido com o mercado real.
>
> E quando backtest e robô divergem, **primeiro reproduza o robô no backtest com os mesmos dados, trade a trade**: isso separa "bug no robô" de "dado definido diferente" — aqui, 39 de 41 trades batendo provou que não havia bug de código algum.
>
> **Pergunte à plataforma nova:** pergunta 130 (nova) — como a plataforma expõe a data de rolagem / qual é o contrato principal em cada dia, e se as barras de período longo (mensal/semanal) do contrato incluem o período em que ele não era o principal. (5.26, 6.46)

Cruza com **5.26** (contínuo re-encadeado: a mesma raiz — a definição de "qual contrato" muda o número), **6.46** (contrato de pouco volume quase virou produção) e **6.54** (concordância trade a trade com a referência é o que separa defeito de execução/dado de defeito de estratégia).

### 5.32 Nome de símbolo não é definição de dado: a série "sem ajuste" só era crua no contrato VIGENTE — os contratos anteriores vinham ajustados, e a conferência de 100% de igualdade foi feita justamente no único trecho em que ela passaria

Medido em 2026-10-06, ao simular o WIN de jan–set/2026. Baixei do MT5 (Rico) o símbolo `WIN@`, tratei como "série contínua SEM ajuste = preço real negociado do contrato principal de cada dia" e conferi **100% de igualdade minuto a minuto** com o WINV26 — mas só no trecho de 13/08 em diante, o contrato vigente. Depois, ao ler negócios do Testador em 2025 com preços como 146.576 (fora da grade de 5 pontos do WIN), medi a fração de fechamentos múltiplos de 5 por mês: **~20% em jan–jul/2026, 73% em ago/2026, 100% em set–out/2026**. Ou seja: o `WIN@` só é cru no contrato VIGENTE; os anteriores vêm AJUSTADOS pela plataforma. O Testador já avisava — "Qualidade do histórico 0%" no `WIN@`.

Efeito: todos os resultados de jan–jul/2026 e de 2025 carregam erro de escala de alguns % nos pontos (o sinal se preserva), e a frase "preço real" dita ao dono estava errada para esses meses. O erro de método é o desenho da conferência: ela foi feita **só no trecho em que passaria por construção** (a série coincide com o contrato vigente), então não provava nada sobre o passado.

> **A regra.** Nome de símbolo não é definição de dado. Antes de chamar uma série de "sem ajuste" ou "preço real", verifique em **TODA a janela usada**, não só no trecho recente: (a) preços na grade de tick do contrato real, mês a mês; (b) igualdade contra o contrato real em mais de um contrato, inclusive os antigos. Uma conferência feita só no período em que a série coincide por construção com o contrato vigente não prova nada sobre o passado.
>
> **Pergunte à plataforma nova:** pergunta 131 (nova) — a série contínua que a plataforma oferece é crua ou ajustada nos contratos passados (e por diferença ou proporção)? A "sem ajuste" continua sem ajuste para trás, ou só no contrato vigente? (5.26, 5.31)

Cruza com **5.26** (contínuo re-encadeado) e **5.31** (a mesma raiz: a definição de "qual contrato" e de qual ajuste muda o número), e com **6.54** (concordância com a referência só vale se a conferência puder falhar).

### 5.33 O cache de ticks do Testador era uma CÓPIA incompleta do histórico: sem o preço do último negócio, o stop nativo da B3 não disparava — compras acertando 12,9% contra vendas 64,1%, e seis vendas que nunca tiveram stop somaram −R$1.854

Medido em 2026-10-06 com o EA `WinRetanguloEma34` (retângulo + EMA34 no WIN, capital de teste R$1.000) no Testador de Estratégias do MT5 (WINV26, M1, 13/08 a 30/09/2026, "cada tick baseado em tick real"): **−R$275**, com compras acertando **12,9%** (62 trades) e vendas **64,1%** (64 trades). O backtest Python da mesma lógica dava compra e venda empatadas em ~38%. Lógica igual, assimetria impossível: o defeito estava no dado.

Causa, medida no log do Testador: o cache de ticks **do próprio Testador** para WINV26 estava incompleto — agosto com 64,5 MB contra 79,8 MB do mesmo arquivo no terminal (setembro, 107,6 contra 110,4 MB). **235 das 357 ordens** foram enviadas quando o tick do Testador não tinha o preço do **último negócio** (o log mostra só "(compra / venda)" em vez de "(compra / venda / último)"); em 13/08 o "último" ficou travado em 170.430 o dia inteiro, 350 pontos abaixo do bid/ask reais. Os ticks da corretora puxados direto pela API estavam sãos, com o último colado no bid/ask.

Em instrumento de bolsa o stop nativo dispara pelo **último negócio**, não pelo bid/ask. Com o último ausente ou travado abaixo do preço: **42 compras** levaram stop no MESMO segundo da entrada (o bid estava acima do stop); e **6 vendas NUNCA** tiveram o stop disparado — o preço andou de 900 a 2.980 pontos contra (stop de ~200) e elas só fecharam na zeragem das 17:50, somando **−R$1.854** (inclui uma perda única de −R$596 e outra de −R$487). O defeito de dado criou uma assimetria compra×venda artificial e perdas impossíveis para a geometria. O relatório do Testador mostrava "qualidade do histórico 100%" — e não avisou de nada.

Correção aplicada: a pasta de ticks do Testador (`...\Tester\<id>\bases\Rico-PRD\ticks\WINV26`) foi renomeada para `WINV26_incompleto_20261006`, para o Testador recopiar do terminal no próximo teste.

> **A regra (portável).** Um resultado de testador só vale depois de conferir que o dado de preço que **DISPARA** as ordens (em bolsa: o último negócio) está presente e coerente com bid/ask em todo o período testado. Sintomas que denunciam o defeito: stop que dispara no mesmo segundo da entrada; perda muito maior que o stop; assimetria grande entre compra e venda que o backtest não tem. E o cache do testador é uma **CÓPIA** do histórico: pode estar incompleta mesmo com o terminal são, e "qualidade do histórico 100%" no relatório não garante isso.

> **Pergunte à plataforma nova:** pergunta 132 (nova). (5.30, 5.32, 6.54)

Cruza com **6.54** (mesmo sintoma: `last` zerado e stop nativo disparando no segundo da entrada), **5.30** (dado publicado não é dado negociável) e **5.32** (nome ou relatório de qualidade não é definição de dado: confira em toda a janela).

### 5.34 Barra e tick do MESMO símbolo contínuo vieram em escalas de preço diferentes: o M1 do `WIN@` era ajustado por diferença e os ticks eram crus — ~6.900 pontos de distância num único minuto, e um CSV batizado de "sem ajuste" que herdava o ajuste

Medido em 2026-10-06, ao montar o comparativo dos EAs no WIN de 2026 (sinal na barra, execução e conferência em tick e em contrato real). No MT5 da Rico, o símbolo contínuo `WIN@` entrega barras M1 **AJUSTADAS por diferença**: ~80% dos preços ficam fora da grade de 5 pontos antes da última rolagem, e em 10/06/2026 09:02 a M1 do `WIN@` abre em **176.154** enquanto o negócio real foi a **169.265** — ~6.900 pontos de diferença. Já os **ticks** do mesmo `WIN@` vêm **crus**. Barra e tick do mesmo símbolo descrevem preços diferentes. O `WIN$N` é cru nos dois (barra e tick batem em 169.265).

O arquivo `data/wdo-mt5/WIN@_M1_202601020900_202610051831.csv`, que a memória do projeto descrevia como "sem ajuste", herda o ajuste: **9.502 de 11.837 barras de janeiro** fora da grade (set/out: 0). Dois fatos de contorno limitam o que dá para conferir: os ticks de WIN só existem na corretora a partir de **2026-02-20**, e só com `last` (bid=ask=0) — então, antes dessa data, não há como validar a barra contra tick.

Custo: qualquer simulação que gere sinal na M1 do `WIN@` e execute ou compare em tick, ou em contrato real, mistura duas escalas de preço; stops e alvos em pontos absolutos ficam errados em até milhares de pontos. Foi pego antes de custar dinheiro, mas teria invalidado o comparativo inteiro — e é o terceiro ângulo da mesma família do 5.26 (re-encadeamento) e do 5.32 (o nome do símbolo não diz se é ajustado), agora entre dois produtos de dado do MESMO símbolo.

> **A regra (portável).** Antes de usar uma série contínua, confirme que barras e ticks do MESMO símbolo estão na mesma escala: (a) preços na grade de tick do instrumento, mês a mês, para a barra E para o tick; (b) um ponto de checagem barra×tick (o mesmo minuto, os dois produtos, comparando o preço de abertura). O nome do símbolo não diz se é ajustado, e dois produtos do mesmo símbolo não herdam a mesma definição.
>
> **Pergunte à plataforma nova:** pergunta 134 (nova) — a série contínua do futuro é ajustada? Barras e ticks do MESMO símbolo usam o mesmo ajuste? Qual símbolo dá o preço cru do contrato principal? (5.26, 5.32)

Cruza com **5.26** (contínuo re-encadeado), **5.32** (nome de símbolo não é definição de dado) e **6.54** (concordância com a referência só vale se a conferência puder falhar).

### 5.35 A última barra M1 do dia contém o leilão de fechamento (e a primeira, o de abertura): o "preço de saída" de 127 de 127 dias do WIN era o preço do call — |média| de 86 pontos contra o último negócio contínuo, e três mecanismos diferentes empurravam as zeragens para lá

Medido em 2026-10-06, auditando as bases M1 do WIN usadas em todos os estudos (`WIN$N`, `WIN@`, `WIN@D`, `WIN_A_`; abr–out/2026, 127 pregões). A última barra do dia (18:24, ou 17:54 quando o pregão acabava 17:55) **contém o call de fechamento**, um leilão que começa 18:25 e cruza ~18:31: o close dela é o preço do call em **127 de 127 dias** e o último negócio contínuo em só **3**. O volume dela é ~23 mil contra ~1,5–3 mil das barras normais do fim do dia; a 1ª barra contém o leilão de abertura (volume ~89 mil contra ~24 mil). Nenhum dos dois leilões é negociável como o contínuo. A diferença call − último negócio contínuo é ~0 em média (+5,6 pts) — por isso ninguém viu —, mas tem **|média| de 86 pontos (~R$17 por contrato)**, p90 de 176 e máximo de 480.

Como isso entrou nas medições, por três caminhos independentes: (a) o motor intradiário compara o corte de zeragem com o relógio cru do dado, e o perfil `WIN@` tinha o corte em UTC (21:20) aplicado a uma base em BRT: o corte nunca chegava e a zeragem caía no fallback "última barra do dia" — o call; (b) "zera ≥18:20" em tempo gráfico ≥5 min nunca dispara, porque a última barra M5/M30 começa antes e contém o call; (c) zeragem em hora fixa numa sessão curta (dias de pregão até 17:55) leva a posição ao leilão do dia seguinte.

Auditoria dos estudos: **6 classe A, 21 B, 8 C**. `copa_win` antes de 14/09: zeragem no call em 33–56% dos trades, líquido muda entre −1,4% e +10%. Continuidade diária: 100% das saídas no call. Lib Cinco Médias M30: 11–20% dos trades saem no call e levam a maior parte do P&L — o 2022–24 da v2.02 cai de +1.405 para ~+750. Gap contra D−1: −7,8pp → −5,2pp sem os leilões. Nenhum veredito reproduzido inverteu, mas os números absolutos mudaram. Fonte: `scripts/daytrade/win_fases_correlacao_2026_10_06/auditoria_leiloes/AUDITORIA.md`.

> **A regra (portável).** Uma barra OHLCV não sabe em que fase do pregão está. Antes de usar qualquer base intradiária, **marque as fases de negociação** (leilão de abertura, contínuo, leilão de fechamento) pela grade oficial do mercado **vigente NA DATA**, e meça saída, sinal e volume só com negócios do contínuo. Toda zeragem "no fim do dia" é um horário **relativo ao fim real do contínuo daquele dia**, comparado **no mesmo fuso do dado** — nunca "a última barra".
>
> **Pergunte à plataforma nova:** perguntas 135 a 138 (novas). (5.2, 5.30, 5.34)

Cruza com **5.30** (o leilão de abertura publica cotação indicativa: lá o dano foi amplitude inflada, aqui é preço de saída e volume), **5.2** (horário de sessão por instrumento) e **5.34** (nome de dado não diz o que ele contém) — mesma família: a barra agrega fases que o negócio não trata como iguais.
---

## Parte 6 — Método: os erros que custam meses, não reais

Estes não quebram a conta no mesmo dia. Eles fazem você acreditar em algo por
semanas.

### 6.1 Dois pisos censuram todo backtest, e invalidam comparação

Descobertos depois de invalidarem três rodadas inteiras:

- **Portão de capital = catraca de ruína.** Ele compara o caixa CORRENTE, não o
  inicial. O robô perde, cai abaixo do mínimo, e dali em diante **todo** pregão é
  pulado — nunca volta, porque sem operar não recupera caixa. Medido: numa
  varredura de 130 ações, **mediana de 95,1% das sessões puladas**. Numa
  comparação de políticas de lado, uma pulou 1,6% e outra 96,5% — a comparação
  mediu quem tinha caixa sobrando, não qual sinal era melhor.
- **Zeramento interrompe a série.** Toda variante que quebra reporta ~menos o
  capital inicial e para ali. Três políticas OPOSTAS ficaram dentro de R$2,50
  entre si porque as três zeraram. A região ruim de qualquer superfície fica
  ACHATADA num patamar constante — e aí qualquer célula sobrevivente vira pico
  artificial, destruindo o diagnóstico de platô-vs-pico.

> **Regra:** para comparar qualquer coisa com qualquer coisa, desarme os dois
> pisos (capital folgado, portão desligado, tamanho travado) e **confirme no
> resultado** que nenhuma sessão foi pulada e ninguém zerou. Depois rode o
> cenário com portão LIGADO como medição SEPARADA — ele responde "aguenta meu
> capital?", não "tem edge?", e as duas perguntas importam.

### 6.2 Capital não é parâmetro neutro

Mais caixa = mais lotes por entrada. Variantes com P&L diferente acumulam caixa
diferente e passam a operar TAMANHOS diferentes — misturando o efeito que se quer
medir com dimensionamento. Não adianta só "subir o capital para fugir dos pisos".

### 6.3 Concentração: poucas trades sustentando o resultado inteiro

O campeão tinha **26 trades em 16 anos**. As 5 maiores somavam mais de 100% do
lucro (as outras 21 se cancelavam). A maior isolada era **53,7% de todo o lucro**
— e nem era saída de estratégia, era marcação a mercado no último dia de dados.
Metade do "retorno de 16 anos" dependia de onde a janela terminava.

> **Regra:** cheque concentração antes de aceitar qualquer métrica de retorno.

### 6.4 Sobreviver a 110 hipóteses contra o mesmo histórico é o cenário onde
overfitting é mais provável, não menos

Toda avaliação usava as MESMAS janelas fixas repetidamente. Isso é data snooping
clássico, e o fato de muitas hipóteses terem sido "refutadas honestamente" não
protege — protege a hipótese individual, não a escolha do vencedor.

Quando o walk-forward finalmente rodou: CAGR de 36% no histórico completo virou
**17,1% / −4,2% / 18,3%** às cegas. Uma das janelas **perdeu dinheiro**, com
drawdown de −78,6%.

E: **tunar parâmetro no in-sample piorou.** O melhor combo do IS caiu para a
posição mediana 55 de 108 no OOS, e perdeu para os defaults do repositório em 4
de 6 comparações.

### 6.5 Um portão pode ser artefato do conjunto que o escolheu

"Zero janelas negativas" era o portão de aprovação. No holdout de 48 janelas
virou 8/48 e 3/48. E o ranking entre os dois robôs **inverteu**: a preferência
tinha sido ruído.

O que sobreviveu não foi o nível de retorno (que caiu junto com o índice), foi o
**excesso sobre o índice** — ~+4,6 p.p., estável.

### 6.6 Olhar o out-of-sample uma vez já queima o recurso

Uma varredura diagnóstica de ~12.500 células gastou a janela cega de 18 famílias
de uma vez. Foi decisão consciente, com a linha já encerrada — mas é
irreversível.

> **Regra:** se alguém propuser "confirmar no OOS", a primeira pergunta é se ele
> já foi lido. Confirmação exige dado NOVO ou um corte congelado declarado antes
> de olhar.

E o escopo da disciplina: IS/OOS existe para impedir que a **escolha** de
parâmetro espie o trecho reservado. Ler o placar de uma estratégia já fixada não
tem esse risco — ali a base toda pode ser usada.

### 6.7 Número sem dispersão não é resultado

Uma medição quase virou conclusão comparando UM valor real contra distribuições
sintéticas cujo espalhamento cobria uma faixa 11x maior que a diferença alegada.

> **Regra:** todo número-manchete sai com média entre sementes, intervalo, desvio
> e n. Ponto estimado sem incerteza não é resultado.
>
> **Sinal de alerta barato:** se um efeito deveria ser simétrico por construção
> (sem deriva, comprado e vendido têm a mesma esperança) e os dois lados vêm bem
> diferentes, a diferença está medindo ruído.

### 6.8 Calibração nula é obrigatória em teste múltiplo

Rode o screen inteiro sobre série sintética sem estrutura e conte quantas células
passam os mesmos filtros. Se o sintético entrega o mesmo tanto, o resultado real
é o que ruído produz.

E o nulo tem de ser construído certo: ao inverter o sinal do P&L diário, inverta
só o **bruto** e mantenha o custo sempre negativo. Inverter o líquido faz a série
sintética **ganhar** a corretagem em vez de pagá-la, e todo resultado real parece
ficar abaixo do ruído. Medido: o real saiu do percentil 35,4 (nulo errado) para
54,9 (nulo correto).

> **Corolário prático:** guarde sempre bruto e número de round-trips SEPARADOS no
> arquivo de resultado. Sem isso o nulo correto não é construível depois.

### 6.9 Correlação de ordenação não é evidência de edge

A família mais morta do projeto (0 de 560 células positivas) teve a **maior**
correlação de posto entre in-sample e out-of-sample. Motivo: quem perde de forma
previsível se ordena igual nas duas janelas. Perder consistentemente produz
correlação alta.

> **Regra:** a estatística que responde é a **mediana da grade** (a célula típica
> ganha ou perde?) mais o teste de metade dentro da própria janela.

### 6.10 A convenção de direção pode inverter o sinal do resultado

Mesma célula, mesmo dado: **−102,22 pontos por pregão** medindo direção
fechamento-a-fechamento, **+133,38** medindo pela cor do candle. 235 pontos de
diferença, sinal oposto. A divergência cresce com a agregação.

> **Regra:** declare a convenção canônica e reporte qualquer resultado positivo
> nas duas antes de chamá-lo de resultado. Célula que só é positiva numa das duas
> não é achado, é escolha de convenção.

### 6.11 Mesmo período para todos, sempre

Comparar um ativo com 3 anos de base contra outros com 9 meses mistura "este
ativo é melhor" com "este ativo pegou um período melhor" — inseparável depois de
rodado. Calcule a interseção real das bases e use a janela comum para todos.

Vale por extensão para qualquer parâmetro que não seja o que está sendo
deliberadamente testado: capital, custo, quantidade.

### 6.12 Anualizar janela curta amplifica em vez de estimar

Um retorno de 3x numa janela de 67 dias vira "39.805% ao ano". Em janela abaixo
de um ano, reporte o retorno **do período**.

### 6.13 Um viés escondido pode não ser neutro entre as variantes

O motor nunca remunerou caixa parado. O viés caiu inteiro sobre as variantes
DEFENSIVAS, que por definição seguram mais caixa — **6 de 11 variantes mudaram de
veredito** depois da correção, e a conclusão registrada ("todo filtro defensivo é
refutado") era falsa.

> **Regra:** ao achar um viés, pergunte sobre quem ele cai. Viés uniforme
> desloca o nível; viés correlacionado com a variante **inverte rankings**.

### 6.14 Custo de execução: teste a sensibilidade, não só o cenário base

A estratégia era robusta a taxa percentual e morria com R$0,30 fixos por ordem em
7 de 9 ativos. Taxa fixa força concentração: com capital pequeno, diversificar
foi catastrófico (1 posição: +1.268%; 3 posições: −80%, com 48 de 48 janelas
negativas).

> **Regra:** concentração e dependência de sorte podem ser a MESMA restrição.
> Nesse regime, todo mecanismo que reduz a cauda de risco corta exatamente a
> cauda que sustenta o resultado.

### 6.15 Janela censurada perto do piso de capital não é resultado negativo — e IS/OOS vira sorteio, não validação

Medido em `scripts/daytrade/wdof1_producao_is_oos_2026_09_07.py` (commit
`80c1f2f`, 2026-09-08), rodando a config REAL de produção do WDO F1 (T2/S16,
via `strategy.daytrade.registry.get_daytrade_robot` — o mesmo caminho que
`run_live.py` usa, nunca uma reconstrução manual dos parâmetros) no capital
mínimo real (R$375,00, item 3.4/3.11) sobre a base de tick já corrigida
(5.12-5.14):

| janela | líquido R$ | win% | trades | pregões sem trade | qtd_max |
|---|---|---|---|---|---|
| IS (72 pregões) | +344.855,00 | 94,2% | 19.835 | 0 | 5 |
| OOS (51 pregões) | −76,00 | 50,0% | 2 | 50 | 1 |

> **Nota de 2026-09-08, mais tarde no mesmo dia (commit `4eb3e4a`):** os dois
> números desta tabela vieram do motor que fechava o alvo maker **de graça**.
> Com o deslize do alvo nativo cobrado (item 4.8), a mesma config faz
> **−R$242,50 no IS com 71 de 72 pregões sem trade** — a geometria T2/S16 não
> tem edge (item 6.18). Isso **reforça** a regra deste item em vez de
> contradizê-la: o "+344.855,00" era um número censurado ao contrário — não
> pelo capital, pelo motor. E a leitura de método continua exata: nem o
> +344.855,00 nem o −76,00 mediam edge, e ninguém saberia disso olhando o
> líquido.

À primeira vista, "degradou de +344 mil pra −76 fora da amostra" seria a
leitura padrão de overfitting IS/OOS (item 6.4). É a leitura ERRADA aqui, por
dois motivos que só aparecem nas colunas EXTRAS, não no líquido:

1. **A linha OOS está CENSURADA, não é um resultado negativo.** Ela fez
   exatamente 2 trades — 1 alvo, 1 stop — e parou; `pregoes_sem_trade=50` de
   51 e `qtd_max` preso em 1 confirmam que o caixa nunca destravou 2
   contratos. Aritmética fechada: piso de 1 contrato = `150 × 2,0 × 1,25 =
   R$375,00` (item 3.4), capital de partida = EXATAMENTE R$375,00, um stop
   custa `16 × 0,5 × R$10 = R$80,00`. R$375 − R$76 ≈ R$299 < R$375 → toda
   entrada seguinte é recusada por `capital_insuficiente` e o robô fica
   inerte pelos 50 pregões restantes — a mesma catraca de ruína do item
   6.1/3.10, agora vista pelo lado de uma janela OOS inteira, não de um
   backtest contínuo com portão ligado.
2. **Partindo do piso exato, IS e OOS não são duas medidas da mesma coisa —
   são duas amostras de UMA moeda.** O robô precisa acumular R$80 de lucro
   antes do primeiro stop pra sobreviver; a ~R$9,50 líquidos por alvo (2
   ticks × R$5 menos corretagem), isso são ~9 alvos seguidos, e ao win rate
   de 94,2% medido no IS isso dá `0,942^9 ≈ 58%` de chance de sobreviver até
   lá. O IS ganhou esse sorteio e compôs até o teto de 5 contratos; o OOS
   perdeu no segundo trade. A diferença entre as duas linhas não mede
   degradação de edge fora da amostra — mede o resultado de um Bernoulli em
   cada janela. Os retornos de 4-5 dígitos (91.961%/113.899%/74.331%) são o
   mesmo artefato por outro ângulo: compor tudo sobre um caixa minúsculo faz
   a mesma moeda virar duas ordens de grandeza de diferença dependendo só de
   QUANDO a sequência ruim chega.

De brinde, uma confirmação independente do item 4.8: a mesma medição rodou
T1/S16 como referência (mesmo motivo pelo qual a produção trocou pra T2 foi
deslize do TP nativo, nunca backtest) e deu pior janela de 60s = 36 (IS) e 39
(OOS), acima do teto de 30 de `MAX_ENVIOS_POR_MINUTO` (item 1.18/5.16) — T1 é
INEXEQUÍVEL ao vivo apesar de parecer melhor na tabela bruta (retorno maior,
win% maior, líquido maior). T2 fica em 23 e 6, dentro do teto.

**Atualização (2026-09-08, commit `da6f89c`):** este mesmo teto de 30 foi
substituído por dois níveis (`COTA_ENVIOS_POR_MINUTO = 120` /
`MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO = 600`) depois que outra medição do
mesmo dia (item 6.16, T2/OOS = 42) mostrou que a cadência LEGÍTIMA de T2
também passa de 30 — o veredito "T1 inexequível, T2 dentro do teto" acima
mede o teto ANTIGO; contra o teto atual, os dois só param no disjuntor de
600. Ver item 1.22.

> **Regra:** antes de interpretar qualquer diferença entre janelas de
> backtest, confira se a janela mais fraca foi CENSURADA — conte pregões sem
> trade e o total de trades daquela janela. Um robô que parou de operar não
> produz veredito sobre a estratégia; produz veredito sobre a restrição que o
> parou. E quando o capital de partida é EXATAMENTE o piso de 1 unidade do
> instrumento (item 3.10/3.11), IS-vs-OOS deixa de validar generalização: o
> resultado da janela inteira pode depender de um único Bernoulli early (a
> estratégia sobrevive ou não à primeira sequência ruim antes de compor), e
> comparar duas janelas nesse regime é comparar dois sorteios, não duas
> medidas de edge. A saída correta é dar folga de capital acima do piso de
> sobrevivência já medido (3.10) antes de comparar IS/OOS, ou medir por
> sessão com caixa reposto a cada pregão — nunca reinvestir sobre um caixa
> mínimo contínuo e depois ler a diferença como sinal. Retorno percentual
> sobre caixa mínimo com reinvestimento também não é comparável a nada nesse
> regime (o mesmo edge, com sorte diferente na largada, produz ordens de
> grandeza de diferença) — use valor absoluto por pregão e contagem de trades
> como métricas primárias.
> **Pergunte à plataforma nova:** meu BACKTEST expõe, como coluna de saída,
> quantos pregões de uma janela ficaram sem nenhum trade e por qual motivo a
> última tentativa de entrada foi recusada — ou só o líquido agregado? Sem
> essa contagem, uma janela fraca perto do piso de capital (3.10/3.11) é lida
> como falha de sinal quando pode ser só a restrição de capital calada, e
> ninguém percebe que IS e OOS deixaram de ser comparáveis. (Pergunta 20/23
> já cobrem, respectivamente, varrer o piso de sobrevivência contra a
> estratégia e a plataforma AO VIVO recusar total/parcial no preenchimento —
> esta acrescenta que o próprio BACKTEST precisa expor a contagem, não só a
> operação real.)

### 6.16 Varrer um parâmetro de geometria (não só janela IS/OOS) também atravessa o penhasco de censura do item 6.15 — confirmado em DUAS janelas independentes

Medido em `scripts/daytrade/wdof1_producao_t3_t4_t5_2026_09_08.py`, 2026-09-08,
rodando a config REAL de produção do WDO F1 via
`strategy.daytrade.registry.get_daytrade_robot("wdo_grid_reload_maker")` — só
`profit_ticks` variado (T2 produção, T3, T4, T5), `stop_ticks=16` fixo — no
capital mínimo real (R$375,00, item 3.4/3.11) sobre as janelas IS (72
pregões, 2026-02-27–2026-06-12) e OOS (51 pregões, 2026-06-15–2026-08-25) já
congeladas de `WDO_A_f1.parquet`:

| janela/geometria | líquido R$ | win% | trades | pregões sem trade | caixa_min R$ |
|---|---|---|---|---|---|
| IS T2/S16 (produção) | 344.855,00 | 94,2% | 19.835 | 0/72 | 370,00 |
| IS T3/S16 | 218.788,50 | 89,8% | 12.891 | 0/72 | 299,50 |
| IS T4/S16 | **−250,50** | 76,5% | **51** | **71/72** | **124,50** |
| IS T5/S16 | **−261,00** | 73,6% | **72** | **70/72** | **114,00** |
| OOS T2/S16 | 135.618,50 | 94,4% | 9.446 | 0/51 | 290,00 |
| OOS T3/S16 | 45.366,00 | 89,9% | 5.076 | 0/51 | 299,00 |
| OOS T4/S16 | **−270,00** | 75,0% | **40** | **50/51** | **105,00** |
| OOS T5/S16 | 6.864,50 | 79,2% | 2.511 | **49/51** | 259,00 |

> **Nota de 2026-09-08, mais tarde no mesmo dia (commit `4eb3e4a`):** esta
> varredura inteira rodou no motor que fechava o alvo maker **de graça** —
> ela mede a diferença ENTRE as geometrias corretamente (o penhasco de
> censura é real e é o achado do item), mas o NÍVEL de todas as linhas está
> inflado, e mais para os alvos pequenos: quanto menor o alvo, maior a fração
> do bruto que o motor regalava. Com o deslize cobrado, T2/S16 vai a
> −R$242,50 (IS) e −R$273,50 (OOS) e trava em 71/72 e 49/51 pregões; T4/S16 a
> −R$244,00 com 70/72. Ou seja: as duas linhas "vencedoras" (T2 e T3) e as
> duas "censuradas" (T4 e T5) acabam na mesma família de resultado, e o
> ordenamento por `profit_ticks` que esta tabela sugere não é confiável. Ver
> item 6.18 — inclusive para a razão de método: um ótimo que mora no ponto de
> maior otimismo do simulador não é um ótimo.

Entre T3 e T4 o número de trades não desce numa reta — desce um DEGRAU, de
5-13 mil por janela para 40-72. E o caixa mínimo atingido nos dois T4 (R$124,50
e R$105,00) cai ABAIXO da margem crua da corretora (R$150,00, item 3.3/3.4):
não é um robô operando pouco por falta de sinal, é um robô que caiu no regime
"abaixo do piso de reabertura" (item 1.19/3.10) logo cedo e nunca mais saiu de
lá pelo resto da janela — em silêncio, sem erro. Isso se repete em DUAS
janelas com sequências de dias diferentes (IS e OOS), o que descarta a
explicação de "sorteio de primeira operação" do item 6.15: ali a censura
aparecia comparando duas JANELAS da MESMA geometria; aqui a mesma assinatura
(líquido caindo, `pregões sem trade` dominando, `caixa_min` sob a margem)
aparece varrendo a GEOMETRIA (`profit_ticks`) com capital e janela mantidos
fixos — é a mudança de alvo em si que empurra o caixa cedo o bastante para
travar, não o acaso de qual sequência de trades calhou primeiro.

> **Regra:** o invariante do item 6.15 ("líquido sem `pregões sem trade`
> ao lado não é resultado, é a restrição que parou o robô") generaliza para
> QUALQUER eixo de varredura, não só IS-vs-OOS. Ao varrer um parâmetro de
> geometria (alvo, stop, tamanho) com capital fixo no piso mínimo real, o
> gráfico de "líquido × parâmetro" não é confiável sem o gráfico irmão
> "pregões sem trade × parâmetro" (e o caixa mínimo atingido) ao lado — uma
> queda abrupta no primeiro pode ser inteiramente explicada por uma subida
> abrupta no segundo, e nesse caso o parâmetro não foi testado além do
> ponto onde ele derruba o caixa para baixo do piso de reabertura. Qualquer
> eixo que interage com o tamanho do stop em reais (perda por trade) contra
> um capital fixo no mínimo pode produzir o mesmo penhasco — a defesa é a
> mesma: nunca aceitar `líquido` sem `pregões sem trade`, `trades` e
> `caixa_min`/`qtd_max` ao lado, em qualquer eixo, não só em IS vs OOS.
>
> **Achado secundário, para não confundir os dois:** o `pior_janela_60s` de
> envios de ordem (item 1.18/1.20, teto `MAX_ENVIOS_POR_MINUTO=30`) muda de
> verdade por geometria dentro do regime que opera de fato — T2/OOS estoura
> (42), T3/OOS fica dentro (19), T3/IS fica perto (28). Já os números baixos
> de T4/T5 (6, 6, 6, 24) são ARTEFATO da mesma censura, não evidência de
> geometria mais segura: quem quase não opera não acumula rajada. Ler um
> `pior_janela_60s` baixo como "essa geometria respeita melhor o freio de
> cadência" sem antes checar `pregões sem trade` repete o mesmo erro de
> método, só que na métrica de cadência em vez da métrica de lucro.
>
> **Atualização (2026-09-08, commit `da6f89c`):** foi exatamente este
> T2/OOS=42 "estourando" o teto de 30 que motivou substituir o disjuntor
> único por dois níveis — `COTA_ENVIOS_POR_MINUTO = 120` (recusa só a
> ordem) e `MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO = 600` (o disjuntor). 42 é
> cadência LEGÍTIMA, não laço; ver item 1.22.
>
> **Pergunte à plataforma nova:** o meu backtest expõe, POR CÉLULA de uma
> varredura de parâmetro (não só por janela IS/OOS), quantos pregões
> ficaram sem trade e o caixa mínimo atingido — ou só o líquido agregado da
> célula? Sem essa contagem por célula, uma varredura de alvo/stop pode
> escolher (ou descartar) uma geometria inteira pelo mesmo motivo errado do
> item 6.15, só que ao longo do eixo do PARÂMETRO em vez do eixo da JANELA.
> (6.16, generaliza 6.15/pergunta 47)

### 6.17 T4 travado por capital (6.16) tinha causa raiz diferente: edge negativo por trade, não undercapitalização — mais caixa PIORA o resultado

O item 6.16 achou que T4/S16 travava no capital real (R$375) do WDO F1. A
pergunta óbvia depois disso foi do dono: "pra T4 funcionar, qual seria o
capital mínimo pro caixa não ficar zerado?" Medido em
`scripts/daytrade/wdof1_t4_capital_minimo_2026_09_08.py`, 2026-09-08, escada
de capital de R$375 a R$5.000 no histórico M1 completo do WDO@ (177 pregões),
mesmo método de `wdof1_sobrevivencia_capital_baixo_2026_08_29.py`:

| Capital | trades | líquido R$ | pregões sem trade (de 177) | caixa_min |
|---|---|---|---|---|
| R$375 | 27 | −264,33 | 176 | 110,67 |
| R$500 | 29 | −435,33 | 176 | 64,67 |
| R$750 | 49 | −601,16 | 176 | 148,84 |
| R$1.000 | 57 | −860,55 | 176 | 139,45 |
| R$1.500 | 171 | −1.416,35 | 174 | 83,65 |
| R$2.000 | 252 | −1.879,19 | 173 | 120,81 |
| R$3.000 | 1.091 | −2.914,80 | 161 | 85,20 |
| R$5.000 | 4.882 | **−4.905,87** | 110 | 94,13 |

Nenhum nível destrava T4 — `pregões sem trade` nunca cai perto de zero como
acontece com T2/T3 no item 6.16 — e o líquido **piora monotonicamente** com
mais capital: R$5.000 (13x o capital real do slot) dá o PIOR resultado da
escada, não o melhor. `qtd_max` fica em 1 em todos os níveis (o
dimensionamento dinâmico por risco só libera o 2º contrato perto de R$8.000
com esse stop). `zerou` nunca dispara — não é ruína, é a armadilha silenciosa
do item 1.19/3.9: o caixa cai abaixo da margem crua de R$150 e nunca mais
reabre.

> **Nota de 2026-09-08, mais tarde no mesmo dia (commit `4eb3e4a`):** a escada
> desta tabela rodou no motor que fechava o alvo maker de graça, então o
> breakeven usado abaixo (80,0%) está SUBESTIMADO — com 1 tick de deslize
> cobrado no alvo nativo (item 4.8), o T4 entrega 3 ticks líquidos e não 4, e
> o breakeven verdadeiro é `16/19 = 84,2%`. O win% medido (76,5% / 75,0%)
> ficou ainda MAIS abaixo dele, então o veredito do item — "é edge negativo
> por trade, não undercapitalização" — só fica mais forte. O que mudou é o
> alcance: pelo mesmo teste, **o T2 de PRODUÇÃO também está abaixo do
> breakeven** quando o deslize entra (94,5% medido contra 95,00%), o que este
> item não tinha como ver (item 6.18).

O breakeven teórico de T4/S16 (`stop_ticks/(profit_ticks+stop_ticks)` =
16/20 = 80,0%) já constava do item 6.16. O win% medido nas janelas IS/OOS
daquele item foi 76,5% e 75,0% — **abaixo do breakeven nas duas.** T4 não é
"boa geometria mal capitalizada": é uma geometria com edge negativo por
trade. Mais capital não resolve edge negativo — só adia o mesmo resultado e
deixa o robô rodar mais trades perdedores antes de esbarrar de novo no piso
de caixa, aumentando o prejuízo absoluto no caminho. O travamento por
capital que o item 6.16 documentou era só o que mascarava esse tamanho de
prejuízo — não era a causa raiz.

> **Regra:** antes de tratar qualquer travamento por capital (item 6.16)
> como "precisa de mais caixa", confira se o win% já medido está ABAIXO do
> breakeven teórico da geometria (`stop/(profit+stop)`). Se estiver, nenhum
> capital resolve — o problema é edge negativo por trade, não
> undercapitalização, e subir o capital só compra mais trades perdedores. A
> assinatura desse caso é uma escada de capital que **piora
> monotonicamente** em vez de estabilizar acima de algum piso; distinga dos
> casos onde subir capital destrava e o resultado estabiliza — esses SIM
> são undercapitalização de verdade, e aí sim vale procurar o capital
> mínimo. O item 6.16 achou o travamento; este item (6.17) é o que
> descobre, por trás dele, se travar é sintoma de pouco caixa ou de edge
> negativo disfarçado de pouco caixa.
>
> **Pergunte à plataforma nova:** o meu backtest reporta o win% observado e
> o breakeven teórico (derivado de alvo/stop) lado a lado, para qualquer
> geometria testada, ANTES de eu decidir se um travamento por capital
> merece mais caixa ou se é edge negativo disfarçado? Sem essa comparação
> ao lado do resultado, uma escada de capital pode rodar do início ao fim
> perseguindo undercapitalização que não existe — o número que resolveria
> em uma linha (win% vs breakeven) só aparece depois de já ter gastado a
> escada inteira. (6.17, decorre de 6.16/pergunta 52)

### 6.18 O motor dava o alvo de graça: a geometria de PRODUÇÃO não tem edge, e a varredura de 250 células que a escolheu estava medindo a lacuna do próprio simulador

Este é o item mais caro do arquivo em resultado de pesquisa — não custou
dinheiro num pregão, custou a validade de **toda** a calibração deste robô.

Até 2026-09-08, `IntradaySessionMachine._close_position` fechava a saída por
alvo maker EXATAMENTE no nível pedido, de graça
(`target_fills_as_maker=True` ⇒ `exec_px = exit_ref_price`). O item 4.8 mediu
no extrato que isso é falso: o alvo deste robô não é limite resting, é o `tp`
NATIVO amarrado no request da entrada, e a corretora o varre a mercado —
**10 de 11 saídas piores que o nível pedido, zero a favor, média −1,000
tick**. O commit `4eb3e4a` fez o motor cobrar esse tick. O que apareceu
embaixo são TRÊS achados distintos, e confundi-los é perder dois deles.

Medido em `scripts/daytrade/wdof1_deslize_alvo_is_oos_2026_09_08.py`, config
REAL de produção via `get_daytrade_robot("wdo_grid_reload_maker")` (o mesmo
caminho de `run_live.py`), capital R$375,00, nas janelas congeladas de
`WDO_A_f1.parquet` (IS: 72 pregões, 2026-02-27..2026-06-12; OOS: 51 pregões,
2026-06-15..2026-08-25). A tabela do veredito usa o OOS:

| geometria | ganho líq/vitória | breakeven | win% medido (n) | IC 95% | E[R$]/trade | z |
|---|---|---|---|---|---|---|
| T2/S16 **sem** deslize (motor antigo) | R$9,50 | 90,00% | 94,5% (9.635) | [94,04 ; 94,96] | +4,27 | +19,4 |
| **T2/S16 com deslize 1t (PRODUÇÃO)** | **R$4,50** | **95,00%** | 94,5% (9.635) | [94,04 ; 94,96] | **−0,45** | **−2,15** |
| T3/S16 sem deslize | R$14,50 | 85,50% | 89,9% (5.076) | [89,07 ; 90,73] | +4,40 | +10,4 |
| T3/S16 com deslize (compensação do dono) | R$9,50 | **90,00%** | 89,9% (5.076) | [89,07 ; 90,73] | **−0,09** | −0,24 |

**(a) O veredito: T2/S16 não tem edge.** Cobrar 1 tick corta o ganho por
vitória de R$9,50 para R$4,50 e move o breakeven de 90,00% para **95,00%**. O
win% medido do T2 é 94,5% sobre n=9.635, e o breakeven novo cai **FORA** do IC
95% [94,04% ; 94,96%], **acima** dele — z = −2,15, expectativa −R$0,45 por
trade. Não é empate nem "margem apertada": é negativo com significância
estatística, pela mesma conta do item 6.17 (win% contra
`stop/(profit+stop)`), só que agora com o breakeven no lugar certo.

**(b) Compensar movendo o gatilho não resgata — leva a ZERO.** A ideia do
dono, na hora: "sabendo que ele escorrega 1 ponto, pedir 1 ponto a mais para
receber o pretendido". Testada literalmente (T3 pedindo 3 para receber 2). Ela
devolve o payoff — R$9,50 líquidos por vitória, exatamente o do T2 sem
deslize — mas **o gatilho anda 1 tick junto**: o preço precisa andar 3 ticks
para disparar, contra 2. O win% cai de 94,5% para 89,9% e o breakeven cai para
90,00% — agora **DENTRO** do IC [89,07 ; 90,73], z = −0,24: indistinguível de
zero. A perda por trade melhora 80% (−R$0,672 → −R$0,133) e os trades sobem
4,4×, e nenhuma das duas coisas cruza o zero. O mesmo desenho aparece no IS
(T2 com deslize −R$242,50, T3 −R$229,00): a compensação melhora o número e não
o sinal.

> A regra portável: **compensar deslize deslocando o gatilho REDISTRIBUI a
> geometria, não cria margem.** O que se ganha em payoff por vitória se perde
> em probabilidade de tocar o alvo, e a troca é aproximadamente justa — porque
> as duas pontas saem do MESMO preço. Só o P&L medido diz qual das duas perdas
> é menor; raciocinar "peço 3 e recebo 2, logo é igual ao T2 de antes" está
> errado por omitir o lado do gatilho.

**(c) A lição de método, que é a que mais vale.** O motor **regalava um tick
em cada saída por alvo: 18.742 saídas no IS + 9.104 no OOS, × R$5,00 =
R$93.710,00 + R$45.520,00**. A mesma geometria, nas mesmas duas janelas, com
o mesmo sinal e os mesmos instantes de entrada:

| janela | T2/S16 sem deslize (motor antigo) | T2/S16 com deslize (motor honesto) |
|---|---|---|
| IS (72 pregões) | **+R$347.548,50** · 19.893 trades · 0/72 sem trade · caixa mín. R$370,00 | **−R$242,50** · 165 trades · **71/72 sem trade** · caixa mín. R$132,50 |
| OOS (51 pregões) | **+R$143.214,50** · 9.635 trades · 0/51 sem trade · caixa mín. R$290,00 | **−R$273,50** · 407 trades · **49/51 sem trade** · caixa mín. R$101,50 |

(O +R$135.618,50 da tabela do item 6.16 é a mesma linha OOS medida algumas
horas antes, sem a histerese de nível do item 4.19 — a diferença entre as duas
é irrelevante ao lado disto. O T3 da compensação do dono dá −R$229,00 no IS e
−R$237,00 no OOS; o T4/S16, o "edge negativo" do item 6.17, dá −R$244,00 com
win 83,3% em 70/72 pregões sem trade: **todas as linhas com deslize cobrado
caem na mesma família de resultado**, a geometria vencedora e a já condenada.)

E a varredura de **250 células de `profit_ticks × stop_ticks`** que ESCOLHEU
esta geometria rodou nesse mesmo motor. Ela não escolheu a melhor geometria: escolheu **a que melhor explora a
otimização que faltava no modelo de preenchimento** — quanto menor o alvo,
maior a fração do trade que o simulador dava de graça.

> **Um ótimo que mora exatamente no ponto onde o simulador é mais otimista que
> a realidade não é um ótimo. É o sintoma de um modelo incompleto.**

**Toda a calibração deste robô precisa ser refeita** — e "refeita" inclui os
itens deste arquivo que citam número dele: 6.15, 6.16, 6.17, 4.10 e 4.11
mediram no motor sem deslize (ver as notas datadas em cada um).

**(d) O veredito vira em 0,1 tick — e a incerteza que decide já não é a do
backtest.** Rodada a sensibilidade ao PRÓPRIO deslize, no mesmo script, mesma
config de produção, capital real R$375,00, janela IS de 72 pregões:

| variante (IS, R$375,00) | líquido R$ | win% | trades | pregões s/ trade | censurada? |
|---|---|---|---|---|---|
| T2/S16 deslize **0,0t** (motor antigo) | +347.548,50 | 94,2% | 19.893 | 0/72 | não |
| T2/S16 deslize **0,5t** | **+137.618,50** | 94,5% | 19.921 | **0/72** | **não** |
| T2/S16 deslize **1,0t** (o medido) | **−242,50** | 93,3% | 165 | **71/72** | sim |
| T2/S16 deslize **2,0t** | −293,00 | **0,0%** | 76 | 71/72 | sim |

A meio tick o robô sobrevive a janela inteira e é fortemente positivo; a um
tick ele morre no primeiro pregão. **Não é gradiente, é penhasco.** (A linha
de 2,0t é também a verificação de sanidade da implementação: com alvo de 2
ticks e deslize de 2 ticks o bruto por vitória é exatamente R$0,00, menos
R$0,50 de corretagem — então o win% TEM de dar 0,0%. E deu.)

O penhasco tem endereço exato: o **deslize crítico**, o valor de deslize em
que a expectativa por trade cruza zero.

| geometria | ganho de breakeven | deslize crítico |
|---|---|---|
| T2/S16 (win 94,5%) | R$4,98 | **0,905 tick** |
| T3/S16, a compensação do dono (win 89,9%) | R$9,61 | **0,979 tick** |

**E o deslize medido tem incerteza que ATRAVESSA esse ponto.** A amostra é a
mesma do item 4.8 — n=11, média 1,000 tick, desvio 0,447, erro-padrão 0,135,
**IC 95% (t de Student, gl=10) = [0,700 ; 1,300] ticks**:

| deslize | ganho/vitória | breakeven | margem sobre win% 94,5% | E[R$]/trade |
|---|---|---|---|---|
| 0,700 (limite otimista do IC) | R$6,00 | 93,44% | +1,06pp | **+0,98** |
| 0,905 (**crítico**) | R$4,98 | 94,50% | 0,00pp | 0,00 |
| 1,000 (**medido**) | R$4,50 | 95,00% | −0,50pp | **−0,45** |
| 1,300 (limite pessimista do IC) | R$3,00 | 96,61% | −2,11pp | −1,84 |

O ponto estimado (1,000) está ACIMA do crítico (0,905), e é por isso que o
veredito de (a) continua de pé — ele é o melhor estimador que existe, e é o
único medido em dinheiro real. Mas o IC do deslize contém valores dos dois
lados do crítico.

E é isso que sobra do achado como método: **mais backtest não move mais essa
resposta.** O win% já está medido com n de 5 dígitos e IC de ±0,5pp; a
incerteza inteira mudou de lado — ela mora num n=11 com IC de ±0,3 tick que
atravessa o ponto de virada. A medição que decide é **acumular saídas por alvo
nativo no extrato da corretora**: ~40 a 50 saídas levariam o IC do deslize
para ≈±0,14 tick e tirariam o 0,905 de dentro dele, para um lado ou para o
outro.

Isso também recontextualiza a compensação do dono de (b): pedir 1 tick a mais
no alvo move o ponto de virada de 0,905 para 0,979 tick — ou seja, compra
~0,07 tick de margem contra o deslize. É melhora real e pequena: não resgata o
robô (E = −R$0,09 por trade, indistinguível de zero), mas é a direção certa.

> **Regra:** quando o resultado de uma estratégia depende de um parâmetro de
> CUSTO medido com amostra pequena, calcule o **valor crítico** desse
> parâmetro — aquele em que a expectativa cruza zero — e compare-o com o
> **intervalo de confiança da medição do parâmetro**, não só com o ponto
> estimado. Se o crítico cair DENTRO do IC, o veredito não está decidido pela
> estratégia: está decidido pela precisão da medição de custo, e a próxima
> medição útil é ampliar a amostra do CUSTO, não rodar mais backtest. Um
> backtest com n de 5 dígitos ao lado de um custo com n=11 dá ilusão de
> precisão, porque só o primeiro n aparece na tabela.

**A armadilha de leitura, que estava dentro desta própria medição.** As duas
linhas com deslize cobrado ficaram **CENSURADAS** pelos itens 6.15/6.16: 49 de
51 e 37 de 51 pregões sem NENHUM trade no OOS (71 de 72 e 70 de 72 no IS),
`qtd_max` preso em 1, caixa mínimo de R$101,50 e R$121,00 — abaixo da margem
crua de R$150,00. Os líquidos de
−R$273,50 e −R$237,00 **não medem edge**; medem o robô batendo no portão de
capital e emudecendo. O que salva o teste é uma propriedade específica deste
custo: **o deslize não muda QUAIS trades acontecem.** O gatilho continua no
mesmo nível, o motor entra e sai nos mesmos instantes; só o PREÇO de saída
muda. Logo o win% de 94,5% medido nas 9.635 operações da linha não-censurada
(motor antigo) é o win% verdadeiro do T2, e o teste correto é ele contra o
breakeven NOVO. É isso que permite condenar a geometria **sem depender de
nenhum líquido censurado**.

**Risco residual nomeado, e ele é o item 3.8 de novo:** o custo novo é ligado
por `config_for` — a rota que produção, painel e backtest usam. **7 scripts
antigos de laboratório montam o modelo de custo NA MÃO**, não passam por essa
rota, e continuam com o alvo de graça (a lista está no `CLAUDE.md`). Rodar um
deles hoje produz o número otimista outra vez, sem nenhum aviso. Um default
seguro só protege quem passa pela porta onde ele mora; quem monta o objeto na
mão herda o default do DATACLASSE, que aqui é `0.0` de propósito (para não
cobrar em silêncio de um instrumento cuja economia ninguém mediu). As duas
escolhas estão certas e mesmo assim deixam uma fresta — a defesa é a linha da
tabela padrão carimbar a premissa (`desliz.alvo 1,0t`), porque duas linhas com
o mesmo `líquido R$` e premissas de custo diferentes não são comparáveis e
nada no número denuncia isso.

> **Regra:** todo custo que o simulador não cobra é uma otimização disponível
> para o otimizador, e ele vai achá-la. Antes de aceitar o vencedor de
> qualquer varredura, pergunte onde o modelo é mais otimista que a realidade e
> confira se o vencedor não mora exatamente ali — se o parâmetro campeão for o
> que maximiza a exposição ao pedaço não-modelado (aqui: alvo mínimo, porque o
> tick regalado é fração fixa de um bruto cada vez menor), o resultado é sobre
> o motor, não sobre o mercado. Um custo que o motor não cobra também precisa
> ser medido no EXTRATO, não estimado: a diferença entre 0 e 1 tick por saída
> inverteu o sinal de uma estratégia inteira. E quando a correção censurar a
> janela por capital (6.15/6.16), pergunte se o custo novo muda QUAIS trades
> acontecem ou só o preço deles — se muda só o preço, o win% da linha
> não-censurada continua válido e o veredito sai do par (win% × breakeven
> novo), sem precisar do líquido.
> **Pergunte à plataforma nova:** qual é a lista dos custos de execução que o
> simulador dela cobra, e onde cada número dessa lista foi MEDIDO? Todo item
> que não estiver na lista é um subsídio que a varredura de parâmetros vai
> encontrar e explorar sozinha.

### 6.19 O custo que apagou o edge não era constante da natureza — era o MECANISMO de execução, e trocá-lo levou o robô de −R$242,50 CENSURADO para +R$239.936,50 operante

> **SUPERADO EM PARTE, 2026-09-09 (noite) — leia o item 6.21 antes desta
> tabela.** A troca de mecanismo descrita aqui está correta e continua
> valendo: o alvo nativo desliza, a ordem-limite *resting* não. O que **não**
> vale mais são os números da coluna "alvo FATIADO" — +R$239.936,50 (IS) e
> +R$77.833,50 (OOS) —, medidos num motor que enchia ordem-limite no primeiro
> toque, **de graça, nos dois lados** (itens 4.21 e 4.22). O risco 3 da lista
> abaixo ("a fila REAL de saída nunca foi medida") era, ele mesmo, o que
> sustentava o resultado: medida a fila, o T2 fatiado dá **0 de 21 pregões
> positivos** (6.21).

O item 6.18 fechou com um veredito e uma conta de amostra: T2/S16 não tem edge
depois de cobrar 1 tick de deslize no alvo, o ponto de virada está em 0,905
tick, o IC 95% do deslize medido (n=11) é [0,700 ; 1,300] e **atravessa** esse
ponto — logo "rodar mais janela, mais geometria ou mais capital não move a
resposta; a incerteza inteira está do lado do custo, num n=11". As três
alternativas listadas eram mesmo inúteis, e mesmo assim a conclusão estava
errada: **a lista estava incompleta.** Existia uma quarta — trocar o
MECANISMO de execução que GERA o custo.

**O que é o mecanismo.** O `tp` nativo (o que viaja amarrado no request da
entrada) não fica *resting* no livro: a corretora o executa como **gatilho
varrido a mercado** (item 4.8 — n=11, 10 saídas piores que o nível pedido, 0
melhores, média −1,000 tick). Com alvo de 2 ticks, 1 tick de deslize é
**metade do bruto do trade**: foi isso que levou o breakeven de 90,00% para
95,00% e condenou o T2/S16. Mas derrapagem é, por definição, "executou pior do
que eu pedi" — e uma ordem-limite parada no livro **recusa** preço pior. O
custo não era propriedade do instrumento nem da corretora: era consequência de
ter escolhido o tipo de ordem que aceita preço pior.

**A correção** foi declarar `EnterLimit.exit_split_unit` (parâmetro novo
`fatiar_saida_alvo=True` em `WdoGridReloadMaker`), que troca o gatilho por
ordem-limite REAL parada no livro — exatamente o caminho que o motor já não
cobrava deslize, porque ali ele não estava sendo otimista: a saída fatiada
posiciona limite de verdade. O custo some **por construção**, não por
otimismo de modelo.

Medido em `scripts/daytrade/wdof1_fatiar_saida_alvo_is_oos_2026_09_08.py`
(commit `317e839`), config real de produção, capital R$375,00, T2/S16, nas
mesmas duas janelas congeladas do item 6.18:

| janela | alvo NATIVO (gatilho) | alvo FATIADO (limite no livro) |
|---|---|---|
| IS (72 pregões) | −R$242,50 · **71/72 pregões sem trade** | **+R$239.936,50** · **0/72 sem trade** |
| OOS (51 pregões) | −R$273,50 · **49/51 pregões sem trade** | **+R$77.833,50** · **0/51 sem trade** |

A janela sai de **CENSURADA** (itens 6.15/6.16 — o robô morria de caixa em
poucos pregões e o líquido media o portão de capital, não o edge) para
operante nas duas. E a troca não é indiferente à geometria: **T3 fatiado NÃO
acompanha** (−R$248,50 no IS, 70/72 pregões sem trade). É o T2 que sustenta.

**O que se paga pela troca — três riscos abertos, registrados de propósito:**

1. **O alvo perde a proteção registrada na corretora.** `_alvo_atomico` recusa
   amarrar `tp` em posição fatiada de propósito: em conta NETTING, dois
   fechamentos do tamanho total INVERTEM o lado (itens 1.4 e 1.23 — é o
   desfecho do incidente de 2026-08-28). Só o **stop** continua no broker; o
   alvo passa a depender do processo do robô vivo reenviando a limite a cada
   barra. Trocou-se um custo de execução por uma dependência de disponibilidade.
2. **Ordem-limite pode não preencher.** É para isso que existe o
   `exit_ttl_bars` (prazo; estourado, o restante sai a mercado) — e o prazo
   tem preço próprio, medido no item 6.20.
3. **A fila REAL de saída nunca foi medida.** O backtest assume que a limite
   preenche quando o volume da barra cobre a fatia. Medida existe só do lado da
   ENTRADA (item 4.20: n=26, 0 contra a posição). Esta é a aposta que fica
   aberta, e ela é exatamente a mesma classe de suposição que o item 6.18
   pegou do outro lado.

> **Regra:** antes de aceitar um custo de execução como dado do problema,
> pergunte **por que** ele custa, não só **quanto**. Todo custo medido tem um
> mecanismo por trás, e mecanismo é escolha de implementação — o tipo de ordem,
> quem fornece e quem consome liquidez, o que a corretora faz com uma proteção
> registrada. Um número medido com rigor (n, IC, direção, significância) engana
> mais que um chute, porque o rigor da MEDIÇÃO se confunde com a
> inevitabilidade do FENÔMENO. O sintoma de que isto está acontecendo é uma
> frase da forma "a incerteza inteira está do lado do custo, e só dinheiro real
> a resolve": ela declara o custo exógeno sem nunca ter examinado o mecanismo.
> Quando a lista de próximos passos só contém variações do MESMO experimento
> (mais janela, mais parâmetro, mais capital), a lista está incompleta —
> falta o passo que muda o experimento. Corolário operacional: preferir
> FORNECER liquidez na saída a consumi-la é uma decisão de risco, não de custo
> puro — ela troca deslize garantido por risco de não-preenchimento e por
> proteção que sai da corretora e volta para o processo; registre as duas
> pontas.
> **Pergunte à plataforma nova:** o take-profit dela é ordem-limite *resting*
> ou gatilho varrido a mercado; dá para posicionar a saída de lucro como limite
> real e reposicioná-la a cada barra; e, com essa limite em pé, o STOP continua
> registrado na corretora sem risco de execução dupla? (perguntas 64, 65 e 66)

### 6.20 Parâmetro emprestado não é só um número fora de contexto — pode ser uma UNIDADE diferente com o mesmo nome: o literal `8` vale 8 MINUTOS num robô e meio SEGUNDO no outro

> **DESFECHO, 2026-09-09 — leia isto antes do resto do item.** O valor de
> produção **mudou de 8 para 60** depois deste item ter sido escrito
> (`EXIT_TTL_BARS_PADRAO_FATIA` em `wdo_grid_reload_maker.py`). A pergunta do
> dono não era sobre o erro de unidade abaixo (que continua correto e é o que
> o item documenta) — era sobre esperar mais antes de sair a mercado: *"não
> seria melhor trocar de 8 para 20 para aguardar mais e só então sair a
> mercado? isso não aumentaria as chances de sair com limite?"*. A resposta
> certa não morava no P&L ruidoso medido abaixo (10 pregões, curva
> serrilhada) — morava na **TAXA DE FILL**, que sai monotônica
> (`scripts/daytrade/wdof1_ttl_taxa_de_fill_2026_09_09.py`, T2 fatiado, 10
> pregões do IS, capital real):
>
> | `exit_ttl_bars` | ~tempo de relógio | % preenche na limite | deslize R$ |
> |---|---|---|---|
> | 8 | 0,5s | 84,1% | 2.375,00 |
> | 20 | 1,2s | 88,9% | 1.875,00 |
> | 60 | 3,7s | 92,8% | 1.040,00 |
> | 130 | 8,1s | 93,6% | 1.510,00 |
>
> O dono estava certo na direção (8→20 já sobe 4,8pp de preenchimento).
> Ficou em **60** porque o trecho 20→60 rende MAIS que 8→20 (+3,9pp) e
> derruba o deslize de R$1.875,00 para R$1.040,00 — menos da metade do que
> o 8 pagava; depois de 60 a curva achata (130 só acrescenta 0,8pp e o
> deslize volta a subir). Ou seja: **o `exit_ttl_bars` do WDO F1 não é mais
> um empréstimo não calibrado da `gremah`** — é calibrado para o próprio
> instrumento, com critério de TAXA DE FILL (não de P&L, que é onde a
> varredura de 10 pregões abaixo mostrou ruído). O resto desta seção — a
> descoberta do erro de unidade e a decisão antiga de "manter 8" — é
> histórico e continua valendo como registro de COMO o bug foi achado; não
> leia a decisão "manter 8" logo abaixo como o valor atual.

Ao ligar a saída fatiada (item 6.19), o WDO F1 herdou `exit_ttl_bars=8`, o
prazo de vida da ordem-limite de saída. Esse 8 foi calibrado na `gremah`, que
opera **PMAM3 — ação de centavos, fila lenta, book raso**. O WDO F1 opera
**futuro líquido**. Não era detalhe de configuração: trocar `None` (sem prazo)
por 8 virou o T3 fatiado de **+R$12.928,50 para −R$248,50** — inverteu o sinal
do resultado.

**E a troca foi maior do que "outro instrumento" — foi de UNIDADE.** O
`wdo_grid_reload_maker` declara `feed_kind="tick"`: uma "barra" dele é CADA
NEGÓCIO, não um minuto. Medido na base canônica do WDO@: **159.440 barras num
pregão, mediana de 62 ms entre elas.** A `gremah` não declara nada e herda o
default `feed_kind="m1"` de `strategy/daytrade/base.py`.

| robô | `feed_kind` | uma "barra" é | quanto vale `exit_ttl_bars=8` |
|---|---|---|---|
| `gremah` (origem do 8) | `m1` (default herdado) | 1 minuto | **8 minutos** = 480 s |
| `wdo_grid_reload_maker` | `tick` (declarado) | 1 negócio (mediana 62 ms) | **~0,5 segundo** |

**O mesmo literal, quase 1000x de diferença em tempo de relógio.** Ninguém
percebeu porque os dois parâmetros têm o mesmo NOME, o mesmo TIPO (`int`) e o
mesmo CAMPO de destino (`EnterLimit.exit_ttl_bars`) — o que muda é a
granularidade do feed, que mora em OUTRO atributo da estratégia e não viaja
junto com o número copiado. A única coisa no projeto inteiro que carregava a
unidade era um texto de tela da própria `gremah`: *"Barras (minutos, aqui)"* —
e o "aqui" não atravessa cópia nenhuma.

**O que isto NÃO invalida, dito antes de qualquer outra coisa:** nenhuma
medição. Backtest e produção do WDO F1 leem a MESMA base de tick, então o `8`
quer dizer 8 negócios nos dois lados, e a varredura abaixo continua valendo
inteira. O que estava errado era a DESCRIÇÃO — "8 barras de 1 minuto",
documentado no commit `317e839` e corrigido em `f340b37`. Um erro de unidade
que não move número nenhum ainda é caro, e é por isso que ele virou item: ele
decide o que a próxima pessoa acha que pode mexer, e em que ordem de grandeza
ela acha que está mexendo.

Varredura própria depois (11 valores de `exit_ttl_bars`, em NEGÓCIOS, T2, 10
pregões do IS):
`ttl=1` é claramente ruim (**R$9,6 mil** contra R$13–16 mil de todo o resto);
de 2 para cima a curva é **SERRILHADA** — 5: R$13,7 mil · 6: R$14,8 mil · 10:
R$16,5 mil · 12: R$14,7 mil. Vizinhos diferem entre si mais do que a tendência
da faixa inteira, que é a assinatura de ruído: **10 pregões não separam este
parâmetro.** Decisão do dono NA ÉPOCA: manter 8 — não porque venceu, mas
porque nada venceu neste critério. **Revista em 2026-09-09 com outro
critério — ver o DESFECHO no topo do item: o valor de produção é 60,
calibrado por taxa de fill, não por P&L.**

O que a varredura mediu com clareza foi o **preço da válvula**, não o valor
ótimo dela: `ttl=8` dá **R$14,9 mil** contra **R$21,0 mil** do "sem prazo".
Cerca de **30% do lucro é o que se paga** para que uma ordem-limite de saída
não fique pendurada indefinidamente. "Sem prazo" não é alternativa — é
referência não-operável (item 6.19, risco 2: sem prazo, a saída depende
eternamente de a fila andar).

> **Regra:** parâmetro que atravessa de um robô para outro é **hipótese**, não
> default — e a distância que importa não é a de código: é a de INSTRUMENTO e,
> antes dela, a de **UNIDADE**. O sintoma a procurar é preciso: dois robôs que
> compartilham o NOME do parâmetro e o CAMPO de destino, mas não a
> granularidade do FEED. Um `int` chamado `bars` não diz de que barra fala — a
> unidade dele mora em outro atributo, e nome de campo não carrega unidade.
> Antes de copiar qualquer prazo ou contador, pergunte **"8 do quê?"** e
> responda com um tempo de RELÓGIO medido no feed de destino (aqui: mediana de
> 62 ms entre barras), nunca com o nome do campo — comparar os dois literais
> compara duas coisas que só têm a grafia em comum.
> Um prazo, um teto de fila, um número de barras foram calibrados contra a
> velocidade do book onde nasceram; num book com outra liquidez o mesmo número
> pode inverter o sinal do resultado, e vai fazer isso em silêncio, porque
> herdar um default não gera evento nenhum. Ao transplantar: varra o parâmetro
> no instrumento NOVO antes de ele virar produção. E quando a varredura sair
> serrilhada — vizinhos diferindo mais que a tendência da faixa —, a leitura
> correta é "a janela não separa este parâmetro", jamais "o pico é o ótimo":
> escolher o máximo de uma curva de ruído é o item 6.5 outra vez. O que a
> varredura ainda entrega nesse caso é o **preço da restrição** (aqui: ~30% do
> lucro pela válvula de segurança), e esse número é decisão do dono, não do
> otimizador. O mesmo erro já apareceu no eixo do risco (item 3.12: o % de
> risco por trade não atravessa de um robô para outro).
> **Pergunte à plataforma nova:** os prazos e contadores dela são medidos em
> tempo de relógio, em barras de tempo fixo, ou em eventos/negócios — e o mesmo
> campo muda de unidade conforme a granularidade do feed? (pergunta 67)

### 6.21 Todo o lucro que a família maker já mostrou morava na suposição de fila zero — com a fila real medida, 0 de 21 pregões positivos

> **Este é o DESFECHO da cadeia 4.20 → 4.21 → 4.22.** Aqueles três acharam o
> modelo de fila que faltava (saída), o que existia e nunca foi ligado
> (entrada), e o viés de sobrevivência que subestimava os dois. Este responde
> a pergunta que o conserto abriu e que ninguém tinha feito ainda: **com o
> motor corrigido, o robô ganha?** Não ganha — e o que não ganha não é uma
> célula, é a família inteira.

Depois de calibrar a fila dos dois lados contra execução real (entrada **438**,
saída **489**, Kaplan-Meier — itens 4.21/4.22), rodou-se a medição que nunca
tinha sido feita com o motor corrigido: **1 mês do IS — 21 pregões,
2026-02-27 a 2026-03-27 —, caixa de R$375,00 REPOSTO a cada pregão**, saída
fatiada sem prazo, T2 contra quatro stops.

**Repor o caixa a cada pregão é o que torna esta medição diferente de todas as
anteriores.** Com o caixa correndo, o robô quebra o piso logo no primeiro dia e
a janela inteira vira uma amostra de UM pregão repetida 21 vezes — é a censura
dos itens 6.15/6.16, e é exatamente o que vinha impedindo qualquer leitura de
edge perto do capital real. Com o caixa reposto, cada pregão é uma observação
independente da geometria, e a ruína deixa de mascarar a expectativa.

O veredito usa o IC 95% de **Wilson** do win% contra o **breakeven
aritmético** — ganho e perda são fixos em ticks mais corretagem, então o
breakeven não é estimado, é conta:

| stop | n ops | win% | IC 95% | breakeven | veredito | R$/op | pregões positivos |
|---|---|---|---|---|---|---|---|
| S6  | 584 | 55,99% | [51,94 ; 59,97] | 78,89% | **NEGATIVA** | −8,86 | **0/21** |
| S10 | 918 | 73,75% | [70,81 ; 76,49] | 85,38% | **NEGATIVA** | −5,71 | **0/21** |
| S16 | 998 | 82,16% | [79,67 ; 84,41] | 90,00% | **NEGATIVA** | −5,34 | **0/21** |
| S21 | 949 | 85,88% | [83,52 ; 87,95] | 92,08% | **NEGATIVA** | −5,18 | **1/21** |

Os quatro intervalos ficam **inteiros abaixo** do breakeven. **1 pregão
positivo em 84.** E o `R$/op` converge para ≈ **−R$5,00** conforme o stop
alarga (−8,86 → −5,71 → −5,34 → −5,18), **não para zero**: alargar o stop não
é o caminho, porque o limite não é o stop.

#### A sensibilidade que fecha o argumento

O veredito acima poderia ser acusado de depender de uma calibração com n=25 do
lado da saída — a limitação que o próprio item 4.22 registrou. Mesma janela,
mesmas 21 sessões, mesmos sinais, variando **só a fila assumida**:

| fila assumida | S16: win% / R$/op / pregões+ | S21: win% / R$/op / pregões+ | veredito |
|---|---|---|---|
| **0 / 0** — o motor de até 2026-09-08 | 94,46% / **+4,46** / **19/21** | 95,87% / **+4,80** / **21/21** | **POSITIVA** |
| 200 / 200 | 87,83% / −0,94 / 4/21 | 90,34% / −0,41 / 6/21 | NEGATIVA |
| **438 / 489** — medida (4.22) | 82,16% / **−5,34** / **0/21** | 85,88% / **−5,18** / **1/21** | NEGATIVA |

O ponto de virada fica em torno de **170 contratos de fila**. O livro real tem
438/489 — **2,6 a 2,9 vezes** isso. **O veredito não depende da precisão da
calibração:** ela poderia estar errada por um fator de dois e a conclusão seria
a mesma. A resposta útil não foi "a fila é 489"; foi **"o ponto de virada é 170
e a realidade é 438"** — a segunda sobrevive a estar errado sobre a primeira.

#### A leitura inversa é o achado de verdade

**Com fila zero o robô ganha em 21 de 21 pregões.** Não em 12, não em 15: em
todos. Todo resultado positivo que esta família já produziu saiu desse motor —
inclusive os **+R$239.936,50 (IS)** e **+R$77.833,50 (OOS)** da tabela do item
6.19, e os pregões que escolheram o T2/S6 para produção em 2026-09-09.

Não era uma estratégia boa com um erro de custo na margem. **Era um artefato do
simulador do começo ao fim** — o lucro inteiro vinha de ordens que a vida real
não teria preenchido, dos dois lados do mesmo round-trip.

> **Registrado de propósito, porque é fonte viva de erro:** a seção "O motor
> COBRA o deslize do TP nativo" do `CLAUDE.md` cita esses mesmos
> +R$239.936,50 / +R$77.833,50 como o DESFECHO que salvava o T2. Aqueles
> números foram medidos com fila 0/0 nos dois lados, e **este item os
> invalida**. Corrigir o `CLAUDE.md` é tarefa separada; o registro fica aqui
> para que ninguém os cite de novo achando que continuam de pé.

#### Por que ninguém percebeu antes: a morte parecia falta de caixa

Uma autópsia operação a operação (primeiros pregões do IS, capital real) já
tinha mostrado que a morte do caixa **não era sequência de stops**: o T2/S17
nunca teve dois stops seguidos e mesmo assim foi de **R$375,00 a R$111,00 num
único pregão**, com **93 vitórias contra 14 derrotas**. Não era azar
concentrado — era **desgaste**: cada stop apaga de 9 a 12 vitórias, e o robô
ganha ~7 seguidas entre stops.

Enquanto isso era lido como "censura por falta de caixa" (6.15/6.16), a
conclusão que se tirava era **"falta capital"** — quando o problema era
expectativa negativa por operação, que capital nenhum conserta. É o item 6.17
outra vez (T4: mais caixa PIORA o resultado), agora atingindo a geometria de
PRODUÇÃO em vez de uma célula já descartada. **Um win% de 87% contra um
breakeven de 90% mata devagar e parece pouco dinheiro.**

#### O limitador de risco que era letra morta

Achado lateral da mesma rodada, e ele pertence à família do item 3.8.
`risco_pct_por_trade=0,01` — 1% do caixa por operação, o parâmetro adotado em
produção pelo item 3.9 — **não fazia nada a R$375,00**: a conta
`caixa × pct ÷ risco_por_contrato` dava **zero** contratos, e o `max(1, ...)`
que existe para nunca devolver tamanho nulo assumia. O robô arriscava de **9% a
30% por operação achando que arriscava 1%**, sem nenhum aviso — porque o
parâmetro estava lá, tinha nome, e o resultado (1 contrato) era idêntico ao que
ele devolveria se estivesse funcionando.

> **Regras** (quatro; as quatro valem em qualquer corretora e qualquer
> linguagem):
>
> **1. Antes de atribuir a morte de um backtest à falta de capital, meça a
> expectativa POR OPERAÇÃO com o caixa REPOSTO.** Ruína e expectativa negativa
> produzem a mesma curva descendente e pedem decisões OPOSTAS — uma pede mais
> caixa, a outra pede abandonar a estratégia. Repor o caixa a cada sessão
> separa as duas em uma rodada, e é mais barato que qualquer escada de capital
> (6.17). Corolário: enquanto a janela estiver censurada, ela não responde nem
> "sim" nem "não" — ela não responde.
>
> **2. Quando um resultado depende de um parâmetro que você não observa, meça
> o resultado AO LONGO desse parâmetro antes de defender o resultado.** O
> entregável não é o valor calibrado: é o **ponto de virada** e a distância
> dele até a realidade medida. Uma conclusão que sobrevive à calibração estar
> errada por um fator de dois é robusta; uma que precisa do número exato é
> aposta com aparência de medição. Aqui: virada em 170, realidade em 438.
>
> **3. Uma família inteira de estratégias pode ser artefato de UMA premissa do
> simulador.** Ao encerrar uma linha por erro de modelo, o que se encerra não é
> a célula medida — é **tudo o que aquele modelo aprovou**. E também o que ele
> REPROVOU: hipóteses refutadas pelo mesmo motor foram descartadas com o mesmo
> viés e podem ter morrido por motivo errado. Refazer a lista do que aquele
> motor tocou faz parte do conserto, não é zelo extra (7.1).
>
> **4. Percentual de risco tem PISO implícito, e o piso pode engolir o
> percentual inteiro.** `caixa × pct ÷ risco_unitário` truncado para baixo dá
> zero em capital pequeno, e o `max(1, ...)` que impede tamanho nulo troca
> silenciosamente o limite pedido pelo MAIOR risco possível. Um limitador que
> pode ser substituído por um piso sem avisar não é limitador: ou ele **recusa
> operar** quando o próprio limite não cabe, ou ele **declara** qual risco
> efetivo está sendo assumido. Mesma família do 3.8 (parâmetro opcional é
> parâmetro desligado) e do 3.12 (o % de risco não atravessa de um robô para
> outro), agora no eixo do CAPITAL em vez do eixo do robô.
>
> **Pergunte à plataforma nova:** perguntas 81 e 82 (novas).
> (3.8, 3.9, 3.12, 4.20, 4.21, 4.22, 6.15, 6.16, 6.17, 6.18, 6.19, 7.1)

**Confirmado num SEGUNDO robô, 2026-09-11 (mesma tarefa que gerou o item
3.17):** o pedido do dono era limitar a perda por trade a "até 50% da
carteira, diminuindo até no máximo 5% conforme a carteira cresce" no
`copa_win`. O caminho óbvio — apertar `risco_pct_por_trade` (o mesmo teto
por risco do item 3.9, já LIGADO em produção a 5%) — é aritmeticamente
inerte no capital real do slot (R$250,00): `quantidade_por_entrada` termina
em `max(1, round(...))`, e 5% de R$250 = R$12,50 de orçamento contra um
stop mediano de R$293,00 (item 3.17) pede 0 contratos, que o piso devolve
como 1. O teto por risco estava LIGADO, nomeado, documentado — e nunca
reduziu um centavo de risco no único capital em que o robô roda de verdade;
a tabela de produção mostra "risco 5%" e o risco real do trade mediano é
117% da conta. Diferente da regra 4 acima (medida a R$375,00/1% no WDO F1):
aqui o mesmo mecanismo aparece a R$250,00/5% num robô com stop por
VOLATILIDADE em vez de fixo em ticks — confirma que o piso implícito não é
peculiaridade de um robô, um capital ou um percentual: é propriedade de
`max(1, round(...))` sempre que o orçamento de risco cai abaixo de 1
unidade indivisível, e quanto MAIOR o percentual pedido (5% aqui contra 1%
no WDO F1), mais enganosa a tabela de produção fica — o número parece mais
seguro e é igualmente inerte.

> **Corolário sobre onde o risco pode de fato ser cortado:** num regime em
> que a quantidade já está no piso indivisível (1 contrato, 1 lote), o único
> lugar onde reduzir risco por trade é possível é a GEOMETRIA — a distância
> do stop —, nunca a quantidade. Apertar `risco_pct_por_trade` nesse regime
> muda a tabela sem mudar o robô; encurtar o stop muda o robô, mas mede uma
> estratégia DIFERENTE e pede validação própria, não é "o mesmo robô mais
> seguro".
> (3.9, 3.17)

### 6.22 O nulo geométrico: win% alto em alvo pequeno não é evidência de nada

Num teste de pullback na VWAP no WDO@, a primeira rodada reportou "o gatilho
acerta a direção — win% 74–82%" e isso motivou um follow-up inteiro (rodar a
mesma VWAP com alvo grande, 16–40 ticks). O follow-up era desnecessário: com
geometria T4/S16, um passeio aleatório SEM DRIFT acerta `stop/(alvo+stop)` =
16/20 = **80,00%** das vezes. O 81,58% observado era +1,58pp sobre o acaso,
dentro de um IC de ±9pp. Somando as 24 células das duas rodadas, o setup
ficou em média **2,4pp ABAIXO** do passeio aleatório.

`stop/(alvo+stop)` é ao mesmo tempo o win% de um passeio aleatório sem drift
com aquela geometria e o breakeven a custo zero — coincidem porque é isso que
"expectativa zero" significa. Se o win% observado não bate esse nulo, não
existe edge nem a atrito zero, e não adianta atacar o custo depois (foi assim
que um teste de Wyckoff/SMC ficou refutado de forma independente de custo:
máx |z| = 1,23 em 16 células, desvio médio +0,21pp do passeio aleatório).

> **Regra.** Nunca reporte win% de uma geometria alvo/stop sem reportar
> `stop/(alvo+stop)` ao lado, e a diferença win% − nulo. Um win% de 90% num
> alvo de 2 ticks contra stop de 16 é 1,1pp ABAIXO do acaso. Antes de investir
> em reduzir atrito, verifique se sobra alguma coisa depois de subtrair o
> nulo — reduzir custo de uma estratégia que não bate o nulo é otimizar o
> preço de uma coisa que não vale nada. Mesma família do item 6.9 (correlação
> de ordenação também engana perto do zero) e do item 6.8 (calibração nula).

### 6.23 Quando o payoff foge do nominal, o nulo certo é o breakeven EMPÍRICO

Continuação direta do item 6.22, e a armadilha do nível seguinte. Num teste de
Ondas de Wolfe no WDO@ (geometria nominal T4/S16, nulo nominal 80,00%), o
relatório concluiu "as quatro células ficam ABAIXO do nulo, reforça o prior de
que reversão não funciona". Estava errado: o payoff REALIZADO não era 4:16 —
o breakeven empírico das mesmas células era **39,6% e 43,9%** (ganho médio
~1,5× a perda média), porque o gap entre o fechamento do sinal e a abertura
do fill, mais o achatamento de fim de pregão, mudaram a geometria efetiva.
Contra o nulo certo, as células estavam **+33,7pp e +26,3pp ACIMA**, não
abaixo. O veredito inverteu.

Para um processo sem drift, expectativa zero exige `win% · ganho_médio =
(1−win%) · perda_média`, ou seja `win% = perda_média / (ganho_médio +
perda_média)` — a fórmula do breakeven empírico. Vale qualquer que seja a
regra de saída, inclusive corte de tempo e gap de entrada: o breakeven
empírico É o nulo geométrico casado com a execução real. O nulo nominal só é
o nulo certo quando o payoff realizado bate com o nominal.

Corolário de conferência: `R$/operação > 0` e `win% > breakeven empírico` são
a MESMA afirmação. Um relatório em que as duas discordam não tem uma "tensão
a explicar" — tem um nulo no lugar errado.

> **Regra.** Reporte sempre as duas colunas: o nulo nominal (a geometria
> PEDIDA) e o breakeven empírico (a geometria RECEBIDA). O veredito sai
> contra o empírico. Quando os dois divergem muito, a divergência é o
> achado — mede o quanto a execução real deformou a geometria pedida, e essa
> deformação costuma ser artefato de modelo, não edge.

Complemento do item 6.27, que é o caso simétrico: aqui o breakeven empírico
divergiu do nominal por causa da EXECUÇÃO e o veredito inverteu para melhor;
lá ele acompanha o acerto por causa da própria CONDIÇÃO DE SELEÇÃO — quando
o filtro que aumenta a acurácia também aumenta a magnitude, ganho e perda
crescem juntos, a razão não se move e o ganho aparente evapora.

### 6.24 O controle-oráculo: meça o look-ahead em vez de jurar que não tem

Setups baseados em pivô só confirmam o pivô N barras depois de ele acontecer;
marcar o pivô na barra em que ocorreu usa o futuro e o resultado é ficção. Em
vez de só declarar "não tem look-ahead", passou a se rodar um gêmeo
deliberadamente trapaceiro — idêntico em tudo, exceto que marca o pivô na
barra do evento — só para quantificar quanto de edge um bug de look-ahead
FABRICARIA.

Dois testes, dois resultados opostos: no Setup 123/Ross, o oráculo dobrou o
número de sinais, subiu o win% em 15–20pp e moveu o R$/operação em +R$20 a
+R$34, virando duas células de negativo para positivo — uma implementação
descuidada teria reportado "quase empata". Nas Ondas de Wolfe, o mesmo
controle deu apenas +0,9pp e +2,8pp de win%.

O ponto que faz o método valer: o controle responde nos DOIS sentidos. Um
oráculo muito acima do honesto diz "esta família é uma armadilha de
look-ahead, qualquer descuido fabrica edge"; um oráculo colado no honesto diz
"esta família é robusta nesse eixo, pode confiar no número". Sem rodar o
controle não se sabe em qual dos dois casos se está — e a intuição erra: os
dois casos acima vieram de setups de pivô parecidos.

> **Regra.** Sempre que a decisão depender de um evento só confirmado depois
> de acontecer (pivô, topo/fundo de zigzag, rompimento validado, padrão de N
> barras), rode um controle-oráculo e publique a diferença como número. O
> oráculo nunca é o resultado; é a régua de quanto o resultado honesto
> custaria se você tivesse errado. Rode o controle ANTES de comemorar um
> resultado positivo, não depois de alguém desconfiar.

E rode o controle — qualquer controle, oráculo ou placebo — na janela CEGA
junto com o tratamento, não só no IS: ver item 6.42, onde um placebo que
perdia R$2.949,40 no IS virou o VENCEDOR em R$ no OOS.

### 6.25 Antes de ler o veredito de uma grade, confirme que cada eixo mexeu em alguma coisa

Numa rodada de cinco setups públicos, três grades tinham eixo morto — um
parâmetro varrido que não mudava nada:

- **Setup 123/Ross**: o eixo "correção mínima ≥25%" nunca rejeitou um único
  trio em toda a amostra (razão correção/perna anterior: mediana 1,18–1,30,
  p05 0,39–0,60), porque pivôs de zigzag têm pernas de tamanho comparável por
  construção. Grade anunciada de 6 células era de 3.
- **Ondas de Wolfe**: o eixo "tolerância de contenção do canal" (estrita vs.
  folga de 20%) deu números idênticos nas duas larguras de pivô — o teste ou
  passava folgado ou violava muito, nunca caía na zona intermediária. Grade
  de 4 era de 2.
- **ORB no WDO@**: o eixo "múltiplo do alvo" ({1,5×, 2,0×, 3,0×}) produziu
  exatamente o mesmo win% de 48,61% — os mesmos 35 acertos em 72 trades — nas
  três células, porque o alvo quase nunca é atingido (21%, 10% e 2,8% das
  saídas). Subir o múltiplo só troca "alvo" por corte de tempo. Grade de 6
  era de ~3.

A regra deste projeto para ler grade é "o veredito é da grade, não da melhor
célula: com 6 células, uma positiva por acaso é esperada" (itens 6.4/6.8).
Essa aritmética assume 6 tentativas independentes. Com um eixo morto, 6
células são 3 tentativas duplicadas — o que muda a conta nas duas direções:
por um lado houve menos tentativas do que se pensa (uma positiva isolada é
MAIS surpreendente); por outro, a "concordância entre células" que parecia
confirmar o resultado era só a mesma célula contada duas vezes.

> **Regra.** Ao varrer uma grade, instrumente cada eixo com uma contagem que
> prove que ele agiu: quantos sinais o filtro rejeitou, quantas saídas
> mudaram de motivo, quantos trades trocaram de resultado. Se um eixo não
> moveu nada, declare a grade pelo número de células EFETIVAS, não pelo
> número de combinações. Um eixo morto não é neutro: ele consome orçamento de
> teste e infla a aparência de robustez.

### 6.26 Sinal num timeframe, execução supervisionada no menor disponível

Um teste de pullback na VWAP alimentou o motor com barras M5 e M15 enquanto
media uma geometria de alvo de 4 ticks. Stop e alvo só eram checados a cada 5
ou 15 minutos, então dentro de uma barra o preço passeava muito além dos dois
níveis antes de qualquer saída ser avaliada. Efeito medido: as DUAS caudas
infladas — ganho médio chegou a **R$63** e perda média a **R$112**, contra os
R$19,50 e R$85,50 que a geometria nominal comporta. O erro foi detectado e a
grade inteira refeita com execução supervisionada em M1; o veredito não
mudou, mas os números confiáveis passaram a ser os outros.

> **Regra.** O timeframe do SINAL e o timeframe da EXECUÇÃO são decisões
> separadas. Gere o sinal na barra que a estratégia pede, mas supervisione
> stop, alvo e achatamento na menor barra disponível. Regra de bolso: se a
> geometria alvo/stop for menor que a amplitude típica da barra de execução,
> o resultado é ficção nas duas pontas — infla ganho e perda ao mesmo tempo,
> então nem o líquido nem o win% denunciam sozinhos. Mesma preocupação de
> fidelidade do item 4.7 (o gêmeo em simulação não é estimativa do real),
> agora no eixo do TIMEFRAME em vez do eixo da fila.

### 6.27 Acurácia direcional isolada não é evidência — e quando a condição que seleciona ACERTO também seleciona TAMANHO, os dois sobem juntos e se anulam

**Este item não custou dinheiro real. Custou direção de pesquisa**, e o erro
é do agente principal, cometido na mesma conversa em que foi descoberto — o
registro só vale se essa distinção ficar explícita, porque um item de método
lido como incidente de execução manda procurar o bug no lugar errado.

**O que aconteceu.** Uma análise inteira foi conduzida e apresentada ao dono
medindo **acurácia direcional** — o relatório falava em frequência de acerto
("depois de três ocorrências seguidas, 43,8% das vezes vem outra, contra
baseline de 39,1%"), e a conclusão saiu daí. Ela só ficou correta quando
alguém, depois, mediu a **razão ganho/perda**. Nada no relatório original
estava aritmeticamente errado; faltava a segunda coluna, e sem ela a primeira
não tem significado econômico nenhum.

**Os números** (100.704 barras M1, 177 pregões, script
`scripts/daytrade/wdo_cor_magnitude_mae_2026_09_10.py`, verificado de forma
independente). A condição testada prevê **tamanho** com força quase 6× maior
do que prevê **direção**:

| grandeza prevista | maior \|z\| entre as células |
|---|---:|
| **tamanho** do movimento | **52,64** |
| **direção** (acerto%) | 8,40 |

E a razão ganho/perda fica praticamente colada em 1: **mediana 1,017**, faixa
0,957–1,073 nas 16 células com n ≥ 1.000.

| estado | acerto | ganho médio | perda média | razão |
|---|---:|---:|---:|---:|
| BASELINE | 40,61% | R$13,00 | R$13,17 | 0,987 |
| condição, seq ≥ 3 | 40,91% | R$15,19 | R$14,78 | 1,028 |
| condição, seq ≥ 6 | 43,69% | R$16,35 | R$17,31 | 0,945 |

**O mecanismo, que é o coração do item.** A condição que aumenta a acurácia é
a MESMA que aumenta a magnitude do movimento. Então o tamanho entra no ganho
**e** na perda ao mesmo tempo: os dois crescem juntos, a razão não se move, e
o breakeven empírico (item 6.23) sobe junto com o acerto. Na célula `seq ≥ 3`
o acerto sobe **0,30pp** (40,61% → 40,91%) enquanto o breakeven sobe
**1,06pp** (40,50% → 41,56%) — ou seja, **acertar mais deixou a célula pior**.
Resultado final: **0 de 21 células** têm EV líquido excluindo o zero depois da
correção de Bonferroni, e **18 de 21** não pagam a corretagem em nenhum dos
dois lados.

Isto é o item 6.23 visto pelo outro lado. Lá o breakeven empírico divergia do
nominal por causa da execução, e o veredito INVERTEU para melhor. Aqui ele
acompanha o acerto por causa da própria condição de seleção, e o ganho
aparente EVAPORA. Nos dois casos a lição é a mesma: o win% não é uma
grandeza interpretável sozinha, é metade de um par.

**Segundo achado do mesmo trabalho: a intuição de ruína apontava para a cauda,
e quem mata é a acumulação.** A hipótese do dono era que uma conta de R$375
morreria por um movimento grande demais para o caixa. É falso, e o número é
claro: só **7 das 100.704 barras (0,007%)** têm excursão adversa acima dos
**R$225** de folga que a conta tem até bater a margem crua de R$150. A conta
morre de pedágio somado — a regra `seq ≥ 3` perde **R$244,48 em 229 trades**,
e **R$114,50 disso (47%) é corretagem pura**. Num robô de muitas operações
pequenas, a cauda da distribuição de excursão adversa é a suspeita errada; o
custo por operação é a certa.

> **Regra 1.** Acurácia direcional só é evidência acompanhada da razão
> ganho/perda. Uma taxa de acerto isolada não tem significado econômico,
> porque o breakeven depende da razão — acerto e breakeven podem subir juntos
> e se cancelar. Relatório que traz win% sem `ganho médio / perda média` ao
> lado não está incompleto: está potencialmente invertido. (Casa com 6.22 e
> 6.23; a régua é sempre o breakeven empírico.)

> **Regra 2.** Desconfie especialmente quando a condição que seleciona acerto
> também seleciona **magnitude** — volatilidade, tamanho de corpo, horário
> agitado, sequência de barras "fortes". Nesses casos os dois efeitos são o
> mesmo efeito, e a melhora aparente é contábil, não econômica. O teste é
> barato e cabe numa coluna: **a razão ganho/perda mudou junto com o acerto?**
> Se ela ficou em ~1,0, o ganho de acurácia foi anulado, e não há o que
> otimizar depois.

> **Regra 3.** Ao avaliar ruína, separe **cauda** de **acumulação**, e meça as
> duas: (a) que fração dos eventos individualmente estoura a folga da conta;
> (b) quanto o custo por operação drena ao longo da amostra inteira. Num robô
> de muitos trades pequenos a segunda domina com folga, e a intuição —
> inclusive a de quem conhece o robô — aponta para a primeira. Mais caixa
> resolve cauda; só menos operações ou menos custo por operação resolvem
> acumulação, e tratar uma pela outra gasta uma escada de capital inteira
> (mesma armadilha do item 6.17).

Perguntas 86 e 87 da Parte 8 carregam a parte que depende de plataforma.

### 6.28 Um efeito de microestrutura pode ser estatisticamente gigantesco e ainda assim INEXEQUÍVEL como entrada nova — três mecanismos alternativos testados contra a fila, nenhum abre um caminho que o desenho já em produção não tivesse

**Este item também não custou dinheiro real — é resposta a uma pergunta do
dono.** A conclusão registrada era que o efeito de reversão do WDO@ depois de
uma corrida de 3+ ticks na mesma direção "não dá para monetizar porque resolve
mais rápido do que a fila real pode ser vencida", testado contra **um único**
mecanismo: ordem nova colocada no instante exato da confirmação do sinal. O
dono questionou a generalização — um mecanismo não testar não prova que
nenhum mecanismo funciona — e pediu que se investigassem alternativas de
execução antes de aceitar "inexequível" como veredito.

**Reprodução do zero** (não a partir da memória do projeto), base
`scripts/daytrade/wdo_tick_direcao_1semana_2026_09_10.csv`, 664.107 ticks, 5
pregões, WDO@: **n=77.556 confirmações de corrida de 3 ticks, 60.437
resultaram em reversão real**. O baseline (ordem nova no instante da
confirmação) resolve com **mediana 298 ms / média 816,6 ms** até o próximo
movimento real de preço, com volume mediano de apenas **7 contratos**
negociados nesse intervalo (média 40,8, p90 100) — muito abaixo dos **330 a
440 contratos** que `backtest/intraday/fidelidade.py` calibrou (Kaplan-Meier,
item 4.22/pergunta 80) como fila real necessária para uma ordem nova alcançar
o topo do book. Isso já era conhecido. O que faltava era testar se MUDAR o
mecanismo — não só o timing reativo — abria algum caminho.

**Três mecanismos alternativos, três resultados:**

| # | mecanismo | resultado |
|---|---|---|
| 1 | Alvo mirando 2-3 ticks ALÉM do ponto de reversão (não o 1º tick de volta) | **não ajuda.** Mesmo em K=3 movimentos reais após a reversão, mediana ainda é só 40 contratos em 1,16 s; só 10,2% cruza 330, 7,0% cruza 440. O volume não cresce rápido o bastante nesta granularidade de tick — dar mais tempo ao sinal não dá mais fila |
| 2 | Ordem repousando desde a PRIMEIRA visita do nível na sessão (não desde a confirmação do sinal) | **cruzaria a fila em 97,5%-98,3% dos casos** (volume pré-acumulado mediano 11.110 contratos, dwell mediano 2.134,8 s ≈ 35,6 min) — MAS 99,9% dos "topos" de corrida de 3 ticks já tinham negociado antes na mesma sessão (só 0,1% são extremos genuinamente novos). Uma ordem assim já teria preenchido numa visita ANTERIOR, sem relação com o sinal específico de reversão. Não é "explorar o sinal de reversão": é virar formador de mercado passivo na faixa de preço inteira da sessão — família já testada e ENCERRADA neste projeto pela mesma fila (item 6.21) |
| 3 | Ordem de SAÍDA de uma posição JÁ aberta por outro motivo, repousando T segundos antes do evento de reversão | **único com chance real**, e cresce com o tempo de repouso |

Mecanismo 3, detalhado — probabilidade de já ter cruzado a fila calibrada, por
tempo de repouso T antes do evento:

| T (repouso) | cruza 330 contratos | cruza 440 contratos |
|---|---:|---:|
| 5 s | 28,2% | 21,3% |
| 15 s | 51,7% | 43,4% |
| 30 s | 66,1% | 58,5% |
| 60 s | 77,7% | 71,6% |
| 120 s | 85,7% | 81,5% |

Mas o mecanismo 3 **não é uma estratégia nova**: é exatamente o desenho de
saída que o projeto já roda em produção (alvo fatiado, `exit_split_unit`, sem
prazo — item 4.24). O efeito de reversão explica PARTE de por que um alvo
assim às vezes enche; não cria caminho de ENTRADA nova executável.

> **A regra (invariante portável).** Um efeito de microestrutura pode ser
> estatisticamente enorme — aqui, reversão em ~78% das corridas de 3 ticks
> confirmadas, n de dezenas de milhares — e mesmo assim inexequível como sinal
> de ENTRADA nova sob QUALQUER mecanismo de fila reativa. Mudar o instante de
> colocação da ordem para "mais cedo" (mecanismo 2) ou mudar o alvo para "mais
> longe" (mecanismo 1) não resolve, se o volume que passa pelo nível no
> intervalo relevante continua sendo dezenas de contratos, não centenas. A
> ÚNICA forma de vencer uma fila calibrada em centenas de contratos é já estar
> posicionado ali há dezenas de segundos a minutos — o que dilui a ideia em
> "formador de mercado full-time na faixa inteira" (outra família, outro
> risco, já refutada) ou em "isso já está coberto pelo desenho de saída
> atual" (não é exploração nova do sinal). Antes de testar variações de
> TIMING de colocação de ordem para vencer uma fila, meça se o volume/tempo
> disponível de fato muda com a variação — se não muda (aqui, K=1→2→3 ticks
> de alvo não moveu a agulha), pare de variar o timing e pergunte se o
> problema é outro: aqui era "isto exige posição já aberta antes", não
> "entrada nova".

Pergunta 88 da Parte 8 carrega a parte que depende de plataforma.

### 6.29 Uma escada de teto absoluto de perda no piso de capital também vira penhasco NÃO-monotônico — célula boa entre duas catástrofes, confirmado num TERCEIRO robô e num TERCEIRO eixo de parâmetro

Generaliza os itens 6.15 (janela IS/OOS) e 6.16 (geometria de alvo/stop em
ticks): a mesma catraca de ruína perto do piso de capital também derruba a
leitura de uma varredura de TETO ABSOLUTO em reais, e desta vez o padrão não
é sequer degradação em degrau — é penhasco em ZIGUEZAGUE.

Medido em `scripts/daytrade/copawin_escada_perda_sweep_2026_09_11.py`
(2026-09-11): 10 tetos de perda por trade × 3 capitais × 2 janelas (IS 129
pregões, OOS), passada cronológica contínua, `copa_win` em capital REAL.
Mesmo capital (R$3.000,00), mesma janela (IS), só variando o teto absoluto
da escada:

| teto | líquido R$ | trades | pregões sem trade |
|---|---|---|---|
| R$200 | **+7.590,30** | 278 | 0/129 |
| R$150 | **−2.949,80** | 146 | **78/129** |
| R$125 | **+7.589,70** | 310 | 0/129 |

Uma célula RUIM (R$150) sanduichada entre duas boas (R$200 e R$125) que dão
o MESMO líquido dentro de R$0,60 de diferença uma da outra. No OOS a
R$750,00: R$125 → −R$668,10 (46/55 sem trade), R$100 → **+R$2.766,60** (166
trades, 0/55 sem trade), R$75 → −R$683,10 (48/55 sem trade) — a mesma
assinatura, célula boa isolada entre duas ruins, agora num eixo (teto
absoluto de perda) e num robô (`copa_win`, stop por volatilidade) diferentes
dos dois itens anteriores (WDO F1, alvo em ticks fixos).

**O mecanismo é o mesmo dos itens 6.15/6.16, só que mais visível aqui
porque o eixo é contínuo em vez de discreto:** com o caixa perto do piso,
o resultado da janela inteira é decidido por se as PRIMEIRAS operações
ganham ou perdem — uma perda cedo derruba o caixa abaixo do portão de
capital e o robô cala pelo resto da janela (coluna `pregões sem trade`
salta de 0 para 60-90%); uma vitória cedo destrava e o robô compõe até o
fim. O parâmetro entra pouco nessa conta: mudar o teto de R$200 para R$150
não piora a estratégia, muda QUAL sequência de trades early cabe no orçamento
antes da primeira perda, e essa mudança pode cair para qualquer lado.

> **Regra (portável, especializa 6.15/6.16):** em varredura de QUALQUER
> parâmetro (janela, geometria em ticks, ou teto absoluto em reais) com
> caixa perto do piso, célula vizinha discordando por ordem de grandeza —
> e, principal sinal deste item, uma célula boa isolada entre duas más ou
> vice-versa, sem gradiente — é assinatura de dependência de CAMINHO, não
> de sensibilidade a parâmetro. O teste continua sendo a coluna `pregões sem
> trade`: se as células boas têm 0 e as ruins têm dezenas de por cento,
> a grade mediu quem sobreviveu ao começo da janela, não qual parâmetro é
> melhor. Escolher a célula "campeã" nesse regime é ajustar ao sorteio da
> largada, não à estratégia — e a defesa é a mesma dos dois itens
> anteriores: nunca ler `líquido` de uma varredura no piso de capital sem
> `trades` e `pregões sem trade` ao lado, e preferir repor o caixa por
> sessão (pergunta 81) a escalar o capital só para "resolver" o zigue-zague.
> (6.15, 6.16, 3.11, 3.17)

Pergunta a plataforma nova: nenhuma nova — perguntas 47/52 (6.16) e 81
(6.21) já cobrem expor `pregões sem trade`/`caixa_min` por célula e rodar
com caixa reposto por sessão; este item é confirmação em terceiro
robô/eixo, não pergunta nova.

### 6.30 "Fila mata robô maker" não generaliza entre instrumentos — no WIN@, a mesma fila que matou o WDO@ não morde em nenhum nível plausível

O item 6.21 encerrou a família maker do WDO@ em 2026-09-10: com a fila real
calibrada contra extrato (438 contratos na entrada / 489 na saída,
Kaplan-Meier — itens 4.20/4.21/4.22), o lucro só existia com fila zero. Ficava
a tentação de generalizar "fila mata robô maker" para qualquer estratégia
maker do projeto. Em 2026-09-11, ao converter o alvo do `copa_win` (WIN@) de
`tp` nativo para ordem-limite REAL fatiada (`fatiar_saida_alvo=True`) e
varrer a sensibilidade a fila na saída, a generalização foi REFUTADA.

Medido em `scripts/daytrade/copawin_alvo_fatiado_fila_sensibilidade_2026_09_11.py`
(56 células, IS 129 pregões + OOS 55, capitais R$250 e R$3.000, alvo a 100% e
a 50% do pedido). Fila varrida na SAÍDA, em frações do volume da barra M1
mediana, capital R$3.000, alvo 50%:

| fila na frente da nossa ordem de alvo | líquido IS |
|---|---|
| 0 contratos | +R$ 7.351 |
| 2.496 (0,10x barra) | +R$ 7.351 |
| 6.240 (0,25x) | +R$ 7.350 |
| 12.481 (0,50x) | +R$ 7.349 |
| 24.962 (1,00x) | +R$ 7.581 |
| 49.924 (2,00x) | +R$ 7.429 |

Nada. A fila só começa a morder a **250.000 contratos** (acerto do alvo cai
de 17,1% para 13,7%) e só zera o acerto do alvo a **25.000.000** — teste de
sanidade que PROVA que o modelo de fila está de fato ligado (sem ele, o
achado seria indistinguível de wiring quebrado).

**A explicação mecânica, medida:** volume mediano por barra M1, mesma regra
que o motor usa (`engine._bar_volume`) — **WIN@ 24.962 contratos/minuto
contra WDO@ 2.935, ou seja 8,5x mais giro**. Some o tempo de exposição: a
WDO F1 tinha alvo de 1-2 ticks e posição de minutos; o `copa_win` tem alvo de
centenas de pontos e posição de HORAS (medido ao vivo em 2026-09-11: 184
barras M1 numa posição só). Uma ordem de 1 contrato parada num nível que o
preço visita por horas, num instrumento que gira 25 mil contratos por
minuto, não tem problema de fila.

> **A regra (portável, é o que precisa sobreviver à troca de plataforma):**
> fila não é propriedade do robô nem do instrumento isoladamente — é a razão
> entre o TAMANHO da sua ordem e o GIRO no nível, multiplicada pelo TEMPO que
> a ordem espera. Um mesmo número de fila é fatal para alvo curto num
> instrumento de pouco giro (WDO@, item 6.21) e irrelevante para alvo longo
> num instrumento de muito giro (WIN@, este item). Antes de transferir um
> veredito de fila de um robô para outro, compare os três: tamanho da ordem,
> giro por unidade de tempo no instrumento, e tempo esperado de espera.
> Transferir "fila mata maker" do WDO@ para o WIN@ sem medir teria matado por
> engano a melhor configuração já medida do WIN@.

**Corolário, generaliza os itens 4.20/4.21/4.22:** um parâmetro de realismo
pode estar corretamente implementado, corretamente ligado, e ainda assim NÃO
MOVER NADA — e isso não é o mesmo que estar desligado (o erro do item 4.22
era `queue_ahead_qty` no default `0.0`, nunca setado). A diferença entre
"não morde" e "não está ligado" só é observável com um teste de sanidade em
valor absurdo (aqui, 25.000.000 contratos). Toda varredura de parâmetro de
realismo que devolver resultado chapado precisa desse teste antes de virar
achado — sem ele, "não morde" e "está quebrado" são a mesma linha na tabela.

**Achado secundário, custo do MECANISMO (separado da fila, fila mantida em
zero nos dois lados):** trocar o `tp` nativo pela ordem-limite real fatiada
custou ~25% do líquido no IS e ganhou ~7% no OOS — IS R$3.000/alvo 50%:
R$9.900 (nativo) → R$7.351 (limite); OOS R$3.000/alvo 50%: R$4.921 →
R$5.254. O acerto do alvo caiu de 23,1% para 17,1% no IS (a limite exige
orçamento de volume; o nativo preenchia no toque, de graça — mesmo
mecanismo do item 6.19). Perder no IS e ganhar no OOS é a assinatura
esperada de um mecanismo que REMOVE um otimismo que a amostra de dentro
estava explorando, e não motivo para reverter a troca.

Pergunta 92 da Parte 8 carrega a parte que depende de plataforma.

### 6.31 Um teto de perda por trade que corta a DISTÂNCIA DO STOP não é trava de segurança gratuita — é mudar de estratégia, e a estratégia nova perde

Continua o corolário do item 6.21 ("no regime de piso indivisível, o único
lugar para reduzir risco é a geometria, nunca a quantidade") e o item 3.17
(pedido do dono para limitar a perda por trade do `copa_win`). A escada foi
implementada como `teto_perda_brl = min(50%×caixa, max(ABS, 5%×caixa))`, e
como a quantidade já mora no piso de 1 contrato, ela corta a DISTÂNCIA do
stop. Medida sozinha ela cumpre a promessa — no capital real acaba com o
zeramento do `copa_win` (pior operação −R$446,50 → −R$159,50, caixa nunca
fica negativo). Cruzada com a mudança de alvo da mesma rodada (alvo a 50%
do pedido, saindo por ordem-limite real em vez do `tp` nativo), ela é
DOMINADA.

Medido em `scripts/daytrade/copawin_escada_x_alvo_cruzado_2026_09_11.py`: 4
frações de alvo × 4 tetos × 3 capitais × 2 janelas (IS 129 pregões, OOS 55).
**No capital SEM censura (R$3.000,00, todas as células operando), a escada
DESLIGADA venceu em 8 de 8 combinações de alvo × janela** — monotônico e
consistente nas duas janelas, ao contrário do zigue-zague de caminho do
item 6.29 (que é sobre o eixo do teto perto do PISO de capital; este item é
sobre o mesmo eixo longe do piso, onde a censura já não explica nada).

IS a R$3.000,00, alvo em 9,5 (50% do pedido):

| teto | líquido R$ |
|---|---|
| escada DESLIGADA | +7.351,00 |
| ABS R$200 | +1.386,60 |
| ABS R$125 | −2.936,80 |
| ABS R$75 | −2.944,00 |

Mesmo IS a R$3.000,00, alvo em 19,0 (100% do pedido):

| teto | líquido R$ |
|---|---|
| escada DESLIGADA | +8.311,00 |
| ABS R$200 | +7.120,20 |
| ABS R$125 | +5.880,70 |
| ABS R$75 | +6.341,70 |

**O mecanismo, e é ele que precisa sobreviver à troca de plataforma: o stop
largo não é só risco — é o TEMPO que o trade tem para resolver.** Neste
robô 56,1% das saídas eram por achatamento de fim de pregão, e carregavam
114,1% do lucro líquido: trades que sofreram excursão adversa, respiraram e
voltaram. Encurtar o stop converte esses perdedores-pequenos-que-viravam-
ganhadores em stops CHEIOS. É o mesmo mecanismo que `strategy/daytrade/lab/wdo_orb.py`
já documenta no campo `alvo_multiplo`, em sentido inverso, sobre o instrumento
oposto: "com stop largo o perdedor sai pelo relógio com perda PEQUENA; com
stop apertado o mesmo trade sai no stop CHEIO" — geometria fixa perdeu de
+R$2,34/op para +R$15,71/op da faixa adaptativa na mesma janela. Dois robôs
diferentes, dois instrumentos diferentes, mesmo mecanismo.

E há um segundo efeito que o nome "teto de perda" esconde: ele limita a
perda de UM trade, nunca de uma SEQUÊNCIA. Apertar o stop também PIOROU o
MaxDD (de −51,0% para −85,8% no IS a R$3.000,00), porque com stop curto o
robô opera mais vezes e a soma dos golpes pequenos passou o golpe grande
que o teto evitou.

O que foi para produção no lugar (desfecho registrado aqui): `copa_win`
passou a rodar `alvo_vol=9.5` (metade da calibração de 2026-08-28) e
`fatiar_saida_alvo=True` (alvo por ordem-limite real, não pelo `tp` nativo
que o CLAUDE.md proíbe). No capital REAL de R$250,00, o IS sai de "ZEROU,
caixa −R$7,10, 116 de 129 pregões sem trade" (item 3.17) para "+R$7.191,10,
0 de 129 sem trade", e o OOS de "−R$247,50 com 1 trade" para "+R$5.111,00
com 130 trades". A escada fica implementada, testada e DESLIGADA.

Risco que fica aberto, e precisa constar: (1) no capital real de R$250,00 o
caixa marcado a mercado desce a R$23,10 no IS (MaxDD −96,3%) — abaixo da
margem crua de R$100,00; o robô sobreviveu, mas sem folga; (2) com saída
fatiada não existe TP registrado na corretora (`live.intraday_runtime._alvo_atomico`
recusa amarrar TP em posição fatiada, de propósito) — só o STOP fica
protegido no broker, o alvo depende do processo do robô mandando a
ordem-limite a cada barra; (3) o WIN@ segue SEM fidelidade de execução
calibrada (ver item 6.30 — ainda não medida a fila de ENTRADA do WIN@,
que preenche de graça em todas as linhas acima).

> **Regra (portável):** um teto de perda por trade que morde na distância
> do stop não é uma trava de segurança gratuita — é uma mudança de
> estratégia, e ela cobra na taxa de acerto. Antes de aceitar qualquer
> limitador de perda que aperte o stop, meça-o no capital SEM censura e
> contra a alternativa de não ter limitador nenhum — a mesma defesa do
> item 6.29, aplicada fora do regime de piso. E meça o MaxDD junto com o
> líquido: um teto por trade pode reduzir a pior operação e ainda assim
> piorar a pior SEQUÊNCIA, porque o número de trades muda junto com a
> geometria.
> **Pergunte à plataforma nova:** nenhuma pergunta nova — é a mesma
> pergunta 81/82 (6.21) e a defesa do item 6.29; este item é confirmação em
> quarto robô/eixo (WDO F1 alvo-ticks, `copa_win` teto-absoluto-no-piso,
> agora `copa_win` teto-absoluto-longe-do-piso), não pergunta nova.
> (3.17, 6.15, 6.16, 6.17, 6.21, 6.29)

---

### 6.32 Três formas de errar um piso de capital, e a única que funciona — o erro mais perigoso é circular

Ao definir o caixa mínimo do `copa_win` (WIN@) em 2026-09-11, o número foi
errado DUAS vezes antes de acertar, e os dois erros são repetíveis por
qualquer um.

**Erro 1 — piso derivado de janela CENSURADA (o mais perigoso).** A conta
foi "margem crua (R$100) + pior queda medida (R$226,90) = R$326,90",
arredondado para R$600 por decisão do dono. Os R$226,90 saíram de rodar o
robô com capital de R$250 e ler `capital − equity_mínima`. Mas uma conta de
R$250 não consegue sofrer a queda desta estratégia: ela quebra antes, o
portão de capital passa a recusar entradas, e o que se mediu foi a queda de
uma conta que morreu cedo. É o erro de janela censurada que este documento
já descreve (ver 6.15) — só que aplicado ao número que dimensiona o próprio
capital, onde ele é circular e auto-confirmatório: o número censurado
justifica exatamente o capital pequeno que causou a censura.

**Erro 2 — medir a queda num tamanho de posição que a produção não roda.**
A correção seguinte foi medir com 1 contrato fixo e sem portão: deu queda
máxima de R$2.892,70 por contrato em 191 pregões. Melhor, mas ainda errado
como piso: a produção ESCALA contratos com o caixa (`margin_per_contract_brl`
+ `risco_pct_por_trade`). Piso não se deriva de uma queda medida num
tamanho fixo, porque o tamanho é função do próprio capital — uma conta
maior não enfrenta a mesma queda em reais, ela abre mais contratos e a
queda cresce junto.

**Erro 3 — rodar a config de produção no histórico inteiro e achar que
respondeu.** A R$600, começando em 2025-12-01, o robô atravessa os 191
pregões com 0 pregões sem trade e +R$12.709,10. A R$600 começando em
2026-09-08, ZERA em dois pregões (medido, `wiped_out_at` 2026-09-09
21:01). As duas medições estão certas: quem começa cedo acumula caixa
antes de encontrar a sequência ruim; quem começa na véspera dela não tem
com o que pagá-la. Um piso tirado de UMA data de início mede o sorteio
daquela data.

**O método que funciona.** A pergunta não é "R$X sobrevive?", é "com R$X,
que FRAÇÃO das datas de início possíveis sobrevive?". Medido em
`scripts/daytrade/copawin_piso_por_data_de_inicio_2026_09_11.py`: 76 datas
de início, horizonte FIXO de 40 pregões para cada uma (horizonte fixo é
essencial — comparar uma começada que teve 150 pregões para se provar com
outra que teve 10 favorece a primeira por construção), morte = ZERAR ou
CALAR por capital (os dois são absorventes na prática: o robô que trava no
portão costuma nunca mais voltar):

| capital | sobrevivem | líquido mediano |
|---|---|---|
| R$ 600 | 42,1% | −R$ 314,80 |
| R$ 1.000 | 60,5% | +R$ 1.410,95 |
| R$ 1.500 | 86,8% | +R$ 2.722,00 |
| R$ 2.000 | 93,4% | +R$ 2.722,00 |
| R$ 3.000 | 100,0% | +R$ 2.812,45 |
| R$ 5.000 | 100,0% | +R$ 3.022,35 |

A R$600 o resultado MEDIANO é negativo, porque a conta normalmente quebra
antes de a estratégia se pagar. O piso foi fixado em R$3.000
(`CopaWin.capital_minimo_recomendado_brl`), primeiro nível com 100% de
sobrevivência.

**Confirmação independente, e é o que dá confiança no número:** o "erro 2"
corrigido pela margem crua (R$2.892,70 + R$100 = R$2.992,70) cai
praticamente em cima do primeiro nível com 100% de sobrevivência. Dois
métodos que erram de formas diferentes convergindo no mesmo número vale
mais que qualquer um deles sozinho.

> **Regra (portável, é o que sobrevive à troca de plataforma):**
> 1. Nunca derive piso de capital de uma medição feita NO capital
>    candidato — se ele for insuficiente, a censura encolhe a queda medida
>    e o número se auto-confirma.
> 2. Nunca derive piso de uma queda medida num tamanho de posição fixo se
>    o robô dimensiona pelo caixa: tamanho é função do capital, então a
>    queda também é.
> 3. Piso é uma afirmação sobre a DISTRIBUIÇÃO de datas de início, não
>    sobre uma trajetória. Meça a fração de datas de início que sobrevive
>    um horizonte FIXO, e conte "calar por capital" como morte, não só
>    zerar.
> 4. Se o piso resultante não couber no capital disponível, a conclusão é
>    que o robô não cabe — baixar o piso não torna a estratégia mais
>    segura, só move a quebra para dentro da conta do dono.
>
> Referência cruzada: mesma família de erro do item 6.15 (janela censurada
> perto do piso de capital), aplicado desta vez ao próprio processo de
> FIXAR o piso, não a uma medição de resultado.

### 6.33 Uma lição já escrita neste registro não se aplica sozinha às outras estratégias — o prazo da ordem de ENTRADA do `copa_win` nunca tinha sido medido, e mexer nele valeu mais que uma grade de 152 células

A lição já estava escrita, em dois lugares, com número real: **a ordem-limite
de entrada precisa de prazo CURTO, senão ela espera até o fim do pregão e
preenche horas depois do sinal** — medido no `wdo_orb` um preenchimento
**269,7 minutos** depois do rompimento (rompeu 14:08, encheu 18:37), e os
fills atrasados foram justamente os piores resultados. Estava no `AGENTS.md`,
estava no `CLAUDE.md`, estava na lista de "o que NÃO fazer".

E não tinha sido aplicada ao `copa_win`, que rodava com
`entrada_ttl_barras=15` **desde sempre**, herdado do default do construtor,
**sem nunca ter sido medido**. Ninguém escolheu 15. Ninguém comparou 15 com
nada. Quem lesse o `registry.py` veria um número explícito ao lado dos outros
parâmetros e concluiria (errado) que aquilo tinha sido decidido.

**O número.** Numa varredura de constância pedida pelo dono em 2026-09-11,
baixar esse prazo de **15 para 5 barras** produziu, sozinho, efeito MAIOR que
a grade inteira de geometria — 4 alvos × 5 stops × 3 trailings = **120
células**, mais **32** de extensão do eixo do stop. Combinado com `alvo_vol`
9,5 → 7,6, no histórico de 191 pregões:

| métrica | produção (a9,5 · ttl15) | candidato (a7,6 · ttl5) |
|---|---|---|
| líquido | +R$ 13.533,30 | **+R$ 18.322,40** |
| MaxDD | 50,3% | **28,9%** |
| lucro/DD | 2,68 | **6,70** |
| blocos rolantes de 20 pregões positivos | 84% | **97%** |
| meses positivos | 80% | **100%** |
| datas de início que terminam positivas (76 datas, horizonte fixo de 40 pregões) | 89,5% | **100,0%** |
| PIOR data de início | −R$ 888,40 | **+R$ 725,30** |

A grade de geometria, que consumiu muito mais tempo de máquina, **refutou os
dois ajustes "óbvios"** (trailing e stop mais curto) e não produziu nenhum
ganho comparável. Scripts: `scripts/daytrade/copawin_grade_constancia_2026_09_11.py`
(+ `..._extensao`), `copawin_filtro_entrada_2026_09_11`,
`copawin_finalistas_robustez_2026_09_11.py`,
`copawin_robustez_por_data_de_inicio_2026_09_11.py`.

**Por que isso é um erro de MÉTODO e não uma sorte de parâmetro.** Um item
deste registro descreve um **modo de falha**, não um robô. Quando um item
entra aqui, ele passa a valer para **toda instância do mesmo padrão que já
existe no repo** — e aplicar-se sozinho é justamente o que ele NÃO faz.
Escrever a lição e seguir em frente deixa o repo num estado pior que o de
antes de medir: agora existe a ilusão de cobertura. É o mesmo mecanismo do
item 3.8 (parâmetro de realismo que existe mas nasce desligado é pior que não
existir) e o mesmo do item 4.22 (a fila da entrada existia havia um mês e
nunca foi ligada), só que num degrau acima: aqui o que não foi propagado não
é um campo de código, é uma **lição já paga**.

> **Regra (portável, vale em qualquer corretora e qualquer linguagem):**
>
> 1. **Ao adicionar — ou ao reler — um item que prescreve um parâmetro de
>    EXECUÇÃO, varra as outras estratégias em busca do mesmo parâmetro e
>    confirme que cada uma foi MEDIDA, ou registre explicitamente que não
>    foi.** O item só está terminado quando a varredura está feita. É o item
>    7.1 ("ao corrigir um bug, varra todas as instâncias do padrão") aplicado
>    a lições em vez de a bugs.
> 2. **Um parâmetro de execução herdado de um default que ninguém mediu é
>    indistinguível de uma escolha deliberada quando alguém lê o código
>    depois.** Um valor explícito no registro de estratégias não carrega a
>    informação "isto nunca foi comparado com nada". Ou ele foi medido, ou o
>    fato de não ter sido fica anotado junto dele.
> 3. **Corolário de ordem de trabalho: antes de varrer geometria de
>    estratégia (alvo, stop, trailing), confira que todo parâmetro de
>    EXECUÇÃO já foi medido.** Eles são poucos, são baratos de varrer, e
>    neste caso um deles valeu mais que a grade inteira de 152 células.
>
> Referência cruzada: itens 7.1 (varrer todas as instâncias do padrão), 3.8
> (parâmetro opcional é parâmetro desligado), 4.22 (a fila da entrada nasceu
> desligada e viciou um mês) e 6.20 (prazo em BARRAS não é prazo em tempo —
> antes de copiar o prazo de um robô para outro, converta os dois para tempo
> de relógio MEDIDO no feed de destino).

### 6.34 Um parâmetro de execução herdado pode não ser ponto cego nenhum — quando a economia por trade já está decidida por outro motivo, cadência só redistribui QUAIS perdas acontecem

O item 6.33 (acima) mostrou que um parâmetro de execução herdado e nunca
medido — o prazo da ordem de entrada do `copa_win` — valia sozinho mais que
uma grade inteira de 152 células, e fechou com uma regra geral: "varra as
outras estratégias em busca do mesmo parâmetro". Isso levantou a pergunta
natural sobre o `wdo_grid_reload_maker` (WDO@, família maker ENCERRADA pelo
item 6.21 em 2026-09-10, quando a fila real calibrada por Kaplan-Meier — 438
contratos na entrada / 489 na saída — mostrou que o lucro só existia com fila
zero): ele tem um parâmetro análogo, `reancora_min_segundos` (freio de
cadência que throttla reprecificação de ordem pendente e rearme após recusa
por capital, default 10 s), também nunca varrido sistematicamente contra P&L
— só escolhido pra não estourar o teto de envios de ordem da corretora.

**O número.** Varredura de 6 valores (2s, 5s, 10s — controle de produção,
20s, 30s, 60s) × 88 pregões reais do IS (2026-02-27 a 2026-07-06), motor de
produção completo: T2/S16, fila calibrada Kaplan-Meier (329 entrada / 494
saída), sem prazo na saída, capital real R$375. TODOS os 6 valores deram
**negativo**, com o win% preso numa faixa de apenas **0,53 ponto percentual**
(85,76%–86,29%) contra um breakeven empírico travado perto de 88% — o
parâmetro moveu QUANTOS trades aconteceram (trd/dia variou de 55,3 a 64,5)
mas não moveu a economia por trade em nenhuma direção mensurável.

**A regra (portável, vale em qualquer corretora e qualquer linguagem).** Nem
todo parâmetro de execução "herdado, nunca medido contra resultado" é um
ponto cego que muda o veredito de uma estratégia — antes de gastar uma
varredura nele, pergunte se a economia por trade JÁ está estruturalmente
negativa por outro motivo independente. Aqui: a fila real do livro, medida
por Kaplan-Meier (item 6.21, itens 4.20/4.21/4.22), já deixa o bruto por
operação abaixo do custo fixo de corretagem. Se a resposta é sim, um
parâmetro de CADÊNCIA de reenvio de ordem só redistribui QUAIS trades
perdedores acontecem — não pode resgatar uma economia negativa que vem de
outro lugar.

A diferença para o item 6.33 é o que importa reter: lá o parâmetro
(`entrada_ttl_barras`) mudava QUAIS SINAIS a estratégia chegava a executar —
filtrava sinais velhos/atrasados de um robô de rompimento com edge
direcional e espaço para operar. Aqui o parâmetro só governa a velocidade de
reenvio de uma ordem de grid que já reancora a cada barra — nenhum dos dois
lados possíveis desse parâmetro toca a fila real que já matou o edge da
família (item 6.21).

> Vale medir mesmo assim quando a dúvida aparecer — foi medido aqui, com o
> mesmo rigor de IC95%/breakeven das hipóteses anteriores desta família (item
> 6.21) — mas o item 6.33 NÃO deve virar heurística geral de "todo parâmetro
> de execução esquecido é candidato a virar veredito". Primeiro descarte que
> a economia por trade já esteja decidida por outro motivo independente; só
> então a varredura vale o tempo de máquina.

Referência cruzada: item 6.33 (mesmo TIPO de busca, resultado oposto —
robô com edge direcional vivo, parâmetro que filtra sinais), item 6.21 (a
fila real, calibrada por Kaplan-Meier, que encerrou a família maker do WDO@
em 2026-09-10) e itens 4.20/4.21/4.22 (a calibração de fila que produz o
número usado aqui).

### 6.35 Nenhuma calibração de geometria tira o robô do penhasco de ruína quando o capital já está no piso — em TODAS as 5 combinações testadas, mais da metade dos reordenamentos das mesmas operações trava o caixa

O `wdo_orb` (ORB do WDO@, `src/strategy/daytrade/lab/wdo_orb.py`) tinha sido
promovido em 2026-09-11 para produção com `max_fades_por_dia=3` e
`stop_max_ticks=40`. No mesmo dia, depois de viver ao vivo o pior streak já
registrado na base (4 semanas seguidas de resultado negativo no extrato
real), o dono pediu uma versão "ganhadora mesmo que pouco, mas constante".

**O número.** Varredura de `max_fades_por_dia` (1, 2, 3) × `stop_max_ticks`
(30, 40) — 5 combinações válidas — nos 123 pregões (IS+OOS), capital real
R$375. Para cada combinação, o risco de ruína foi medido embaralhando as
operações REALIZADAS 10.000 vezes e contando em quantos sorteios o caixa de
R$375 chega a recusar uma entrada por falta de margem. **O risco de ruína
ficou entre 52,4% e 55,2% nas 5 combinações** — uma faixa de só 3 pontos
percentuais entre a melhor (teto1+stop30, 52,4%) e a pior (teto3+stop30,
55,2%). A combinação escolhida tem o melhor R$/operação (+18,18 contra
+14,92 da que rodava antes) e a menor trava, mas isso é uma melhora
marginal, não uma solução: **mais da metade dos reordenamentos possíveis das
mesmas operações levam o caixa mínimo a travar em algum ponto, não importa
qual combinação de teto de fade ou teto de stop se escolha.**

Confirmação fora do backtest, com os 2 últimos pregões reais antes desta
decisão (2026-09-10 e 11), caixa contínuo partindo de R$375: a geometria
antiga (teto3/stop40) fechava o período com **caixa NEGATIVO (−R$2,50)** —
no mundo real isso é a corretora fazendo um chamado de margem. A geometria
nova (teto1/stop30) fechava em **+R$68,00**, positivo — mas nenhuma das duas
ficou confortavelmente acima da margem crua de R$150.

**A regra (portável para qualquer corretora e qualquer linguagem).**
Parâmetros de geometria de entrada/saída (teto de operações por dia, tamanho
do stop) mudam o tamanho médio e a frequência de cada perda, mas **não
mudam a probabilidade estrutural de uma sequência de perdas ocorrer** — essa
probabilidade é dominada pelo TAMANHO DO CAPITAL relativo ao tamanho típico
de uma perda, não pela calibração fina da estratégia. Testar "qual ajuste de
parâmetro reduz o risco de travar o caixa" quando o capital já está no piso
mínimo tende a devolver melhorias de poucos pontos percentuais, não a
resolver o problema — e isso deveria ser o resultado ESPERADO, não motivo
para continuar testando parâmetros novos à procura de uma solução que não
existe nesse espaço de busca.

> Mesma família de erro do item 6.15 (piso de capital censura o backtest) e
> do item 6.29 (escada de teto vira penhasco não-monotônico), num terceiro
> eixo: aqui o próprio risco de ruína embaralhado — não só o líquido — foi
> medido, e ficou preso a um patamar que a geometria não move. Quando a
> parede aparece em toda combinação já mapeada de DOIS parâmetros
> independentes, o próximo passo não é uma terceira varredura de parâmetro —
> é levar a decisão para o dono como pergunta de CAPITAL, não de estratégia.

Referência cruzada: item 6.15 (piso de capital censura backtest e IS/OOS),
item 6.29 (escada de teto de perda também é penhasco não-monotônico),
`capital_minimo_brl` / `contracts_from_capital_operacional`
(`strategy/daytrade/base.py`) e a seção "Capital inicial: sempre o mínimo
real do instrumento" do `CLAUDE.md`.

### 6.36 Saída fatiada + posição que escala viram um viés de contagem: cada fatia de um trade VENCEDOR conta como um "trade" novo, cada STOP conta como um só — o win%/IC medido por registro fica contaminado exatamente quando a estratégia mais precisa ser julgada

Ao testar realocação dinâmica de contratos no `wdo_orb` (subclasse
experimental `WdoOrbDinamico`, nunca tocou o arquivo de produção
`strategy/daytrade/lab/wdo_orb.py` nem o registry), usando o mesmo padrão
opt-in `on_capital_update` + `contracts_from_capital_com_reserva` que
`CopaWin`/`WdoGridReloadMaker` já usam, apareceu um artefato de CONTAGEM na
forma como o motor registra trades quando a posição escala além de 1
contrato: `exit_split_unit=1` faz uma entrada VENCEDORA de N contratos virar
N REGISTROS de "trade ganho" na tabela de resultado (cada fatia do alvo
fatiado conta como um trade separado), enquanto um STOP fecha a posição
inteira ATOMICAMENTE em 1 registro só (confirmado em
`machine.py::_close_position`), mesmo quando a posição tinha N contratos. Ao
escalar de 1 para 5 contratos (teto oficial do WDO@), todo trade vencedor se
multiplica em registros e todo trade perdedor continua contando como 1 só —
o win% e o intervalo de confiança calculados POR REGISTRO DE TRADE ficam
artificialmente inflados/estreitados conforme a posição cresce, sem isso
refletir nenhuma melhora real de segurança ou edge.

**O número.** Teste pequeno (16 pregões reais, 2026-02-27 a 2026-03-20,
motor de produção completo, fila calibrada, capital real R$375, desenho de
execução fechado) comparando ESTÁTICO (1 contrato fixo) contra DINÂMICO
(escala 1→5 contratos pelo mesmo caixa):

| métrica | ESTÁTICO | DINÂMICO |
|---|---|---|
| trades (registros) | 22 | 75 |
| stops (eventos, não fragmentados) | 4 | 4 |
| win% por registro | 72,7% | 86,7% (contaminado pelo artefato) |
| breakeven empírico | 35,5% | 61,7% (também contaminado — a fórmula usa ganho/perda médios por registro) |
| líquido R$ | 2.459,00 | 9.190,00 |
| MaxDD | R$473,00 (126,1% do capital de partida) | R$2.350,00 (626,7% do capital de partida) |

O que é ROBUSTO ao artefato (soma de R$ e curva de caixa não dependem de como
o motor fragmenta o registro) mostra o OPOSTO do que o win%/IC contaminados
sugeririam: sob rejeição i.i.d. (mesmo método de
`capital_dinamico_rerun_2026_08_27.py`, 30 sementes embaralhando a mesma
sequência de trades), o ESTÁTICO NUNCA zerou (0/30) enquanto o DINÂMICO
zerou em 2 de 30 sementes — mesmos 4 stops nas duas variantes, mas ao
escalar, o mesmo stop custa proporcionalmente muito mais.

**A regra (invariante portável).** Ao calcular win%/IC de confiança de
qualquer estratégia que fatia a saída (`exit_split_unit`) E escala
quantidade de posição (realocação dinâmica de contratos/lotes), NUNCA meça
win%/breakeven por REGISTRO DE TRADE bruto da tabela de resultado — meça por
EVENTO DE FECHAMENTO DE POSIÇÃO (agrupando as fatias de uma mesma entrada
como 1 resultado só, ponderado pelo tamanho real da posição), ou use
métricas robustas à fragmentação (líquido em R$, MaxDD em R$/%, taxa de
ruína sob rejeição i.i.d.) como critério decisivo sempre que a granularidade
de registro puder variar entre as variantes comparadas. Combinar (a) saída
fatiada e (b) tamanho de posição variável no tempo é o gatilho específico
deste viés — qualquer estratégia do repo com essa combinação deve ter seu
win%/IC históricos tratados com suspeita até serem recalculados por evento
em vez de por registro.

> A família maker do WDO F1/`wdo_grid_reload_maker`, quando ainda usava
> realocação dinâmica antes de ser encerrada por fila real (item 6.21), tinha
> exatamente essa combinação — saída fatiada + escala de contratos. Os
> números de win%/IC publicados ANTES do encerramento por fila podem ter
> somado os dois vieses (fila zero E fragmentação de registro), na mesma
> direção: os dois inflam o resultado aparente.

Referência cruzada: item 6.21 (família maker ENCERRADA pela fila real —
mesma combinação saída-fatiada + realocação dinâmica), item 6.22 (o nulo
geométrico), item 6.23 (breakeven empírico quando o payoff foge do nominal)
e `machine.py::_close_position` (onde o STOP fecha atômico e o alvo fatiado
não).

---

### 6.37 Um veredito POSITIVO foi RETIRADO horas depois de publicado: 9 de 9 símbolos calibrados da `Gremah` resolviam alvo/espaçamento em 1 tick, e em 9 dias de operação real a PMAM3 teve 1 round-trip completo, resultado −R$1,00

O dono, olhando o veredito recém-publicado de uma cesta `Gremah`
(PMAM3+DASA3+KLBN3, win% 89-92%, IC95% de Wilson acima do breakeven nas duas
janelas IS/OOS — POSITIVA), levantou dois pontos de cabeça em vez de aceitar
o número: "alvo de 1 tick não funciona" e "PMAM3... desde que a gremah foi
feita, até agora ela não comprou ou vendeu nada no real". Os dois pontos
verificaram, e o segundo derrubou o primeiro veredito no mesmo dia em que
saiu.

**O número, contra o terminal MT5 real** (magic `862226953`, único símbolo
com histórico real no período, 25/08 a 03/09/2026 — 9 dias de operação): **49
ordens enviadas pelo robô em PMAM3, 41 CANCELADAS sem nunca serem tocadas
(84%)**, 8 preenchidas — dessas, só **1** carregava o magic do robô de
verdade (as outras 7 eram 1 teste manual do dono e ordens sem magic,
prováveis SL/TP da corretora). **1 round-trip completo do robô em 9 dias de
operação real, resultado −R$1,00.**

Checagem mecânica direta, não estatística: peguei uma das ordens canceladas
(compra parada em R$0,13, ativa das 08:00 às 08:30 de 25/08) e busquei TODO
negócio real da PMAM3 naquela janela de 30 minutos via `copy_ticks_range` — o
preço **nunca saiu de R$0,14-0,15** durante a meia hora inteira em que a
ordem ficou parada. Este não é o modo de falha do WDO@ (perder a disputa de
fila no nível, item 6.21/4.21) — aqui o nível simplesmente **nunca foi
visitado** pelo mercado.

**O achado generaliza muito além da PMAM3, e isso é o ponto mais
importante.** Rodando `Gremah._session_ticks()` (o método real de produção,
não um proxy) para os 9 símbolos de `_CALIBRATION_BY_SYMBOL`
(`strategy/daytrade/lab/gremah.py`) no preço mais recente disponível de cada
um: **9 de 9 resolvem para alvo=1 tick, espaçamento=1 tick.** Quatro deles
(PMAM3, CSAN3, KLBN3, BMGB4) têm isso HARDCODED em
`_GEOMETRIA_TICKS_BY_SYMBOL` — "confirmado" via grid search de backtest sem
nunca checar execução real, e não muda com o preço; os outros cinco (KLBN4,
DASA3, PCAR3, GRND3, LPSB3) saturam no piso `max(1, round(...))` do cálculo
percentual/por-volatilidade nos preços atuais. Nenhum símbolo da tabela
inteira escapa.

**A regra (invariante portátil — generaliza o T1 proibido do WDO F1, item
4.6/4.8, com evidência ainda mais direta).** Um alvo — OU espaçamento, OU
stop — de 1 tick não é "geometria pequena calibrada com sucesso": é geometria
que a corretora não executa de forma confiável. Aqui a evidência é mais
direta que a do WDO@ porque não é disputa de fila — é o nível **não sendo
tocado** pelo mercado real na janela em que a ordem fica parada. Um backtest
que conta "toque" a partir do high/low agregado de uma barra (M1, no caso da
Gremah) pode registrar dezenas de "toques" que nunca correspondem a um
negócio real print ado naquele preço exato — o mesmo otimismo "toque=preenche"
já corrigido para o WDO@ (itens 4.20-4.22) nunca tinha sido auditado para
ações, e o motor de ações (`Gremah`) não tem fila calibrada nenhuma
(`backtest/intraday/fidelidade.py` só cobre WDO@) — o gap ficou invisível até
ter dado real pra comparar.

**A correção aplicada (2026-09-13, código, não parâmetro de backtest):** em
`strategy/daytrade/lab/gremah.py`, constante nova `PROFIT_TICKS_MINIMO = 2` +
método `_geometria_e_segura(profit_ticks, spacing_ticks, stop_ticks) -> bool`,
chamado nos dois pontos onde uma entrada é armada (fase fixa via
`_arm_fixed_session_params`, fase rolante dentro de `on_bar`). Se QUALQUER
uma das três dimensões resolver abaixo de 2 ticks, a estratégia RECUSA a
sessão inteira (nenhuma entrada armada) — nunca clampa/substitui pelo piso em
silêncio, porque um número que nunca passou pelo protocolo de calibração
(regime → varredura IS → confirmação OOS) não pode entrar em produção só por
parecer "mais seguro" na superfície; é a mesma lição que o T1 do WDO F1 já
tinha ensinado, agora reaplicada a um motor diferente. 4 testes novos em
`tests/test_gremah.py` cobrem o gate (fase fixa recusa, fase rolante recusa,
geometria válida em 2 ticks continua armando, a função de checagem isolada
rejeitando cada uma das três dimensões). Suíte inteira: 2014 passed, 1
skipped — sem regressão.

**Consequência prática que fica registrada: o veredito POSITIVO foi
RETIRADO.** Com a correção, a `Gremah` não arma NENHUMA entrada em NENHUM dos
9 símbolos calibrados hoje, porque todos saturam no piso de 1 tick — isso
inclui a cesta PMAM3+DASA3+KLBN3 reportada como POSITIVA momentos antes desta
descoberta. É o resultado correto e intencional (parar de operar geometria
inexequível é melhor que continuar operando um robô que não é tocado), mas
nenhuma perna da cesta está operável até recalibração acima do novo piso.

> **Achado relacionado, EM ABERTO — não corrigido aqui.**
> `rolling_reanchor_after_bars` (default 30 barras M1 = 30 minutos) é a
> explicação mecânica mais provável de a ordem nunca ter sido tocada de
> verdade: ela fica parada 30 minutos inteiros antes de ser reancorada para o
> preço atual — o mesmo anti-padrão que `wdo_grid_reload_maker` já teve e
> corrigiu no item 4.9 ("reancorar em TODA barra, não só no instante de
> armar"; antes disso o robô ficava ativo só 0-14% do pregão). A `Gremah`
> nunca recebeu essa mesma correção. Consertar só o piso de tamanho (este
> item) não resolve isso — mesmo depois de recalibrar um símbolo com alvo≥2,
> uma ordem que só reancora a cada 30 minutos pode continuar não sendo tocada
> pelo MESMO motivo mecânico observado aqui. Candidato a PRÓXIMO item, não
> resolvido agora.

Referência cruzada: item 4.6 (piso de 1 tick decidindo o alvo — mesma
saturação, achada primeiro no WDO@), item 4.8 (T1 proibido no WDO F1 — mesma
proibição, agora com evidência de "nível nunca visitado" em vez de "perde a
fila"), item 4.9 (reancoragem só ao armar — o achado em aberto acima) e item
6.21 (família maker WDO encerrada pela fila real — modo de falha irmão, não
idêntico).

### 6.38 Um eixo de fila varrido de 0 a 2.000 contratos devolveu a MESMA linha em 36 células — não era robustez, era escala emprestada de outro instrumento

2026-09-13, `scripts/daytrade/copawin_300_alvo_fino_sensibilidade_fila_2026_09_13.py`.
Para checar se uma geometria de alvo muito curto do `copa_win` (WIN@, barra M1)
sobrevivia à fila do livro, a varredura de `queue_ahead_qty`/
`exit_queue_ahead_qty` foi montada de 0 a 2.000 contratos — a escala escolhida
por analogia com a calibração REAL do WDO@ (438 na entrada / 489 na saída,
Kaplan-Meier, item 6.21/4.21). As 36 células devolveram **números idênticos**:
mesmo líquido, mesmo win%, mesmo número de operações, mesmo caixa mínimo, do
zero até 2.000. Lido de forma ingênua isso pareceria robustez espetacular ("o
resultado não depende da fila"); era **eixo morto** (mesma família do item
6.25, agora no próprio parâmetro de fila, não num filtro de entrada). O motor
consome a fila com o `bar.volume` da barra (`engine._volume_da_barra`, que usa
`real_volume`), e a barra M1 do WIN@ tem volume MEDIANO de **24.955 contratos**
(p10 8.063, p90 63.511) — uma fila de 2.000 é engolida pelo primeiro toque de
qualquer barra, então o parâmetro estava ligado, com valor, e era inerte.
Refeita a varredura em MÚLTIPLOS do volume mediano da barra (0x / 0,25x / 0,5x
/ 1x / 2x / 4x), o eixo acordou: a 1x o líquido retém 92-95% e o win% cai de
88,6% para 88,3%; a 2x e 4x as células colapsam em janela censurada.

**A regra (invariante portável).** Fila é medida na moeda do INSTRUMENTO,
nunca na de outro. Antes de varrer um parâmetro de atrito, confirme que a
escala varrida é comparável à grandeza que o motor usa para consumi-lo — e o
teste de que ela é comparável é o eixo MEXER. Um eixo que devolve a mesma
linha em todas as células não é robustez: até prova em contrário é um
parâmetro que não está sendo exercido, e a prova é mostrar a célula onde ele
finalmente muda o resultado. Transferir um número calibrado de um instrumento
para outro (438/489 do WDO@ para o WIN@) é o mesmo erro de escala que a
tabela de margem do CLAUDE.md já pagou uma vez ao trocar WIN e WDO.

**Limitação que fica registrada, não corrigida aqui.** Mesmo a varredura
corrigida (múltiplos do volume da barra) continua otimista, porque
`bar.volume` é o volume do minuto inteiro em TODOS os preços, não o volume NO
NÍVEL da própria ordem — a grandeza certa é volume-ao-preço, medida no tape
(`scripts/daytrade/win_fila_real_por_tape_2026_09_11.py`), e o motor M1 não
enxerga essa coluna. O WIN@ continua SEM fidelidade de execução calibrada em
`backtest/intraday/fidelidade.py`.

Referência cruzada: item 6.25 (eixo morto num filtro — mesma checagem
aplicada aqui a um parâmetro de fila), item 6.21/4.21 (a calibração 438/489 do
WDO@ que foi emprestada na escala errada), item 6.30 (fila não generaliza
entre instrumentos — aqui o erro é a UNIDADE de medida da fila, não só o
efeito dela).

### 6.39 Ordens muito acima de trades é assinatura de caixa travado, e ela aparece como ruído, não como erro

2026-09-14, `scripts/daytrade/wdo_orb_4semanas_coleta_2026_09_14.py` /
`wdo_orb_4semanas_analise_2026_09_14.py`, `wdo_orb` (WDO@, tick a tick real,
4 semanas fechadas 2026-08-17→2026-09-11, capital real R$375 por semana
isolada). Na semana S1 (17–21/08) o motor registrou **177 ordens para apenas
2 trades** — 149 delas recusadas por capital (`ordens_recusadas_por_capital`).
A semana S3 (31/08–04/09) teve 92 ordens para 5 trades, 77 recusas. Nas
semanas em que o caixa não travou (S2, e a corrida contínua de R$1.000 sem
reposição) a razão fica quase 1:1 — 7 ordens para 7 trades, 32 ordens para 28
trades. O mecanismo: quando o caixa cai abaixo do que sustenta o contrato, o
motor recusa a ordem e chama `on_order_rejected`, que na `WdoOrb` zera
`_armou_hoje`; o robô rearma na barra seguinte, é recusado de novo, e o ciclo
se repete centenas de vezes até o fim do pregão. Nada disso levanta erro nem
aparece no líquido — a janela simplesmente devolve poucos trades, exatamente
como uma janela em que o mercado não deu sinal.

**A regra (invariante portável).** A razão ordens/trades é um termômetro de
censura de leitura barata. Quando ela dispara (dezenas de ordens por trade) a
janela está medindo o portão de capital, não a estratégia — isso já era
sabido (item 6.15, censura), mas faltava o SINTOMA que denuncia a censura sem
precisar reconstruir a caminhada de caixa. Um backtest que devolve poucos
trades pode ser "não houve sinal" ou "o robô estava amordaçado"; ordens/trades
separa os dois casos, e é a leitura mais barata das duas. Corolário para a
operação real: o mesmo loop acontece ao vivo e enche o diário de tentativas
silenciosas, sem nunca soar como falha.

Referência cruzada: item 6.15 (censura perto do piso de capital).

### 6.40 O motivo de saída carimbado na operação pode conter duas saídas com economias opostas

2026-09-14, mesma coleta do item 6.39, corrida contínua de R$1.000 (28
operações). 16 delas saíram carimbadas com `exit_reason=target`. Só **3
(10,7% do total)** eram alvo de verdade — o preço pagou os ticks pedidos,
R$/op **+229,50**. As outras **13 (46,4%)** eram o corte de relógio: 60
minutos depois da entrada a `WdoOrb` troca o alvo pelo preço corrente
(`saida_limite_minutos=60`, via `AdjustTarget`) e a saída continua carimbada
`target`, com R$/op de apenas **+28,73** — algumas negativas (pior: −R$70,50).
Somado sem separar, "saiu no alvo" parecia responder por 57% das operações
com resultado bom; na verdade o alvo pleno acontece em 1 a cada 9, e o alvo
pedido (média 53 ticks) nunca é atingido em 89% das operações. Sem separar os
dois, a distribuição de payoff do robô fica irreconhecível — o ganho médio
"do alvo" mistura +229,50 com +28,73.

**A regra (invariante portável).** Um `exit_reason` só descreve a operação
quando existe UM caminho de código capaz de produzi-lo. Toda vez que uma
estratégia altera dinamicamente o nível do alvo (trailing, corte por tempo,
re-âncora), o carimbo de saída passa a ser um agregado de duas economias
diferentes e precisa de um sub-motivo. O repo já tinha resolvido exatamente
isso uma vez, para outro caso: o campo `exit_detail` existe em
`IntradayTrade` (`backtest/intraday/machine.py`) e carrega `"target_timeout"`
quando a fatia de saída estoura o prazo — mas a saída por AJUSTE de alvo não
preenche `exit_detail` nenhum, então ela é indistinguível do alvo cheio no
dado bruto. Quando o nível de saída puder ser movido depois de armado,
registre no trade QUAL nível foi pago, não só que "o alvo" foi pago.

Referência cruzada: item 4.21 (a mesma confusão entre "preencheu no nível" e
"estourou o prazo e saiu a mercado", carimbada com o mesmo `motivo=alvo` —
pergunta 32 da Parte 8).

### 6.41 Teste de permutação unilateral é cego para metade da resposta — perder de forma sistemática É prever, só que com o sinal trocado

2026-09-15, sonda de estágio 1 (`scripts/daytrade/cross_asset_confirmacao_probe_2026_09_15.py`,
144 células) testando se o WIN@ confirma o WDO@ direcionalmente. O teste de
permutação foi codado com **p unilateral** — `p = P(nulo >= real)`, isto é, "o
real ganha mais dinheiro que o nulo?". A célula de fumaça devolveu
**−R$2,18/operação, acerto 45,38% (n=7.333), p=0,33** — aposta perdedora, e
uma sonda de uma cauda só teria fechado a linha ali: "0 sobreviventes de 144
células".

Ao pontuar as DUAS caudas do MESMO vetor de permutações já computado
(`p = P(nulo >= real)` e `p_rev = P(nulo <= real)`, **custo zero em
permutação extra**), a rodada completa achou **7 sobreviventes ao
Bonferroni**, e o efeito que segurou no OOS estava na cauda oposta: **+R$4,04
por operação no IS (n=1.719, acerto 50,38% contra breakeven empírico de
47,48%)** e **+R$4,18 no OOS (n=582, 51,72% contra 48,58%)**, p de permutação
no piso (2e-4) no IS. A cauda descartada pela primeira leitura era onde o
sinal vivia — invertido.

O único preço real de medir as duas caudas é de contabilidade, não de
computação: a família de testes **dobra** (144 células × 2 caudas = 288
testes), então o α de Bonferroni cai de 3,47e-4 para 1,74e-4 — e o número de
permutações precisa subir junto para que o **p mínimo atingível**
(`1/(N_perm+1)`) continue abaixo do novo α. Nesta rodada, 4.000 → 6.000
permutações (p mínimo 1,67e-4 < 1,74e-4 do α dobrado).

**A regra (invariante portável).** Toda sonda que pergunta "este estado
prevê o movimento seguinte?" deve pontuar as DUAS caudas do mesmo conjunto de
permutações. Medir só "o real ganha mais que o nulo" deixa a sonda **cega
para metade da resposta**, porque perder de forma sistemática É prever — só
que com o sinal trocado. As duas caudas não custam permutação extra; o que
custam é dobrar a família de testes declarada, e a correção de múltiplos
testes precisa refletir isso. **Corolário operacional:** ao dobrar a família,
confira que o p MÍNIMO ATINGÍVEL pelo número de permutações continua abaixo
do α corrigido — senão nenhuma célula pode sobreviver por construção, e a
sonda vira um gerador de zeros que parece rigoroso.

### 6.42 Um controle que nunca atravessou a janela cega não é controle — o placebo do detector de retângulo INVERTEU no OOS e ganhou em R$

2026-09-15, `copa_win` / WIN@ M1, linha de pesquisa do "retângulo de
lateralização". A estratégia nova — entrada por ordem-limite na linha do MEIO
de um retângulo detectado, alvo além da borda oposta — foi validada contra um
CONTROLE construído do jeito certo: mesmo motor, mesma geometria, mesmo piso
de largura, mesma política, com os testes de FORMA do detector removidos (a
banda vira o q90/q10 cru das últimas 20 barras). No IS o placebo deu
**−2.949,40** e, numa segunda passada, **−2.315,60**, contra **+2.834,10** do
detector completo. A conclusão registrada — "o detector é load-bearing" —
ficou de pé **uma semana inteira**.

O controle nunca tinha sido rodado na janela cega. Quando finalmente foi, o
resultado inverteu:

| janela | detector completo | controle (placebo) |
|---|---|---|
| IS, líquido R$ | **+2.834,10** | −2.949,40 / −2.315,60 |
| OOS, líquido R$ | +737,70 (101 trades) | **+1.306,70 (373 trades)** |
| IS, R$/operação | **+35,16** | −12,29 |
| OOS, R$/operação | **+36,52** | +17,52 |

O placebo GANHA em R$ na janela cega. O que sobrou de verdade é bem menor do
que a conclusão original: por OPERAÇÃO o detector paga nas duas janelas
(35,16 contra −12,29 no IS; 36,52 contra 17,52 no OOS) e o sinal dele **não
inverte**, enquanto o do placebo inverte — isso é real e é o que resta. Mas a
vantagem em R$ TOTAL era artefato do IS, e era ela que estava sendo citada.

Os dois erros são independentes e os dois estavam no mesmo relatório.

O primeiro é de desenho do experimento. Um controle rodado só na janela de
desenvolvimento mede se o filtro separa **exatamente no lugar onde o filtro
foi ajustado** — que é a única pergunta que ele não pode responder. Enquanto
o placebo fica no IS, a diferença entre tratamento e controle é só mais um
parâmetro livre escolhido no IS, com a agravante de parecer o oposto disso:
ter um controle dá a sensação de rigor que dispensa a checagem seguinte
(mesma família do item 3.8 — um mecanismo presente e desligado encerra a
pergunta que a ausência dele teria provocado).

O segundo é de leitura. O detector corta **3,7× as operações** (101 contra
373 no OOS). Um filtro assim pode ter edge melhor por trade e ainda assim
render menos dinheiro: R$/operação e líquido TOTAL respondem a perguntas
diferentes — qualidade do sinal contra quanto ele produz — e um relatório que
só cita uma das duas escolhe o veredito sem dizer que escolheu.

> **Regra (invariante portável).** Controle e tratamento atravessam a janela
> cega JUNTOS, na mesma passada. Um placebo que só existe no IS não é
> controle, é decoração: ele confirma a separação no ponto onde ela foi
> ajustada. E ao comparar os dois, separe SEMPRE o ganho POR OPERAÇÃO do
> ganho TOTAL, e diga qual dos dois está decidindo — filtro que corta
> operação move as duas colunas em direções opostas por construção.

Mesma família do item 6.24 (controle-oráculo) do lado do experimento e do
item 6.23 (breakeven empírico) do lado da leitura: o nulo certo não é só a
fórmula certa, é o nulo medido na janela certa e lido na unidade certa.

### 6.43 O piso de capital ficou órfão: o robô ganhou dimensionamento dinâmico DEPOIS de o piso ter sido medido com quantidade fixa

2026-09-16, `win_retangulo` (WIN@), achado de passagem numa investigação sobre
outra coisa (revivência de retângulo pós-rompimento) — não era a pergunta do
dia, apareceu no caminho.

O piso publicado do robô (`PISO_UM_CONTRATO_BRL = R$1.100`, em
`strategy/daytrade/lab/win_retangulo.py`) veio de um rebaixamento por operação
de **R$989,50**, medido no IS (129 pregões, capital de partida R$1.100). Essa
medição rodou **antes** de o robô ganhar `escala_por_caixa` — o dimensionamento
que abre um 2º contrato quando o caixa cresce o suficiente dentro da própria
janela — que virou o **default da classe** nos commits `4806636`/`ca252a7`
(2026-09-15 21:40, **depois** da medição que gerou o R$1.100). Rodando hoje o
robô de PRODUÇÃO, sem nenhuma modificação
(`strategy.daytrade.registry.get_daytrade_robot("win_retangulo")`), na MESMA
janela e MESMO capital de partida, o rebaixamento por operação é
**R$1.979,00** — quase o DOBRO do número que sustenta o piso publicado. O piso
real seria ~R$2.079,00 (rebaixamento + margem crua de R$100), quase o dobro do
R$1.100 que o painel (`capital_minimo_recomendado_brl`) mostra e usa hoje. A
causa mecânica: a escalada libera um 2º contrato quando o caixa ultrapassa
R$2.933 dentro da própria janela IS, e uma operação de 2 contratos tem
oscilação em reais maior — isso empurra o rebaixamento pico-a-vale acumulado
da curva de patrimônio para cima, mesmo começando de 1 contrato.

Esta é uma QUARTA forma de errar um piso de capital, distinta das três já
catalogadas no item 6.32 (janela censurada, tamanho fixo que a produção não
roda, data de início única) — lá as três eram erros no MÉTODO de medir; aqui o
método de medir estava certo no dia em que mediu, e o robô mudou de
comportamento por baixo dele depois. Nenhuma das quatro precisa de má-fé:
basta o código evoluir e ninguém voltar para reconferir um número que já foi
tratado como resolvido.

> **Regra (portável, é o que sobrevive à troca de plataforma):** um piso de
> capital publicado é uma afirmação sobre uma VERSÃO específica do robô, não
> sobre o robô para sempre. Toda vez que um robô ganha — ou tem alterado — um
> mecanismo de dimensionamento DINÂMICO de posição (escala pelo caixa,
> realocação por capital, risco-%-por-trade que muda contrato conforme o
> saldo), o piso precisa ser REMEDIDO sob o novo comportamento antes de
> continuar em uso. Um piso calculado sob "quantidade fixa" não protege contra
> o rebaixamento maior que aparece quando o próprio robô passa a escalar a
> posição. Mesma família do item 3.8 (parâmetro de segurança opcional é
> parâmetro desligado) e do item 4.22 (parâmetro presente e nunca ligado): aqui
> o número não estava desligado, estava CORRETO no passado — e um piso correto
> no passado que ninguém revisita depois de uma mudança de sizing é o mesmo
> risco silencioso, só que com uma data de validade que não está escrita em
> lugar nenhum.
>
> Referência cruzada: item 6.32 (três formas de errar o processo de FIXAR um
> piso) — esta é a quarta forma, e a única das quatro em que a medição
> original estava certa quando foi feita.

### 6.44 Um parâmetro pode mexer no resultado aparente sem tocar na variável que decide — e uma boa história causal em cima de dados parciais é o sintoma mais perigoso, não a defesa

2026-09-19, varredura do freio de reancoragem (`reancora_min_segundos`) do
`wdo_grid_reload_maker`, 8 valores (10s a 180s), cada célula sobre o IS
congelado inteiro (72 pregões, ~4.200–5.000 operações por célula, 0/72
pregões sem trade em todas — sem censura), motor de produção (`config_for`,
fila calibrada 329/494 de `fidelidade.py`, capital real R$375 reposto por
pregão):

| freio | R$/op | win% | trades | ganho médio | perda média |
|---|---|---|---|---|---|
| 10s (produção) | −2,18 | 85,80% | 4.291 | — | — |
| 20s | −1,23 | 86,70% | 4.548 | — | — |
| 30s | −1,02 | 86,85% | 4.958 | +11,38 | −82,91 |
| 45s | −1,08 | 86,74% | 4.887 | +11,49 | −83,32 |
| 60s | −1,74 | 86,22% | 4.195 | +11,33 | −83,54 |
| 90s | −0,94 | 86,95% | 4.775 | +11,37 | −82,98 |
| 120s | −0,90 | 86,99% | 4.949 | +11,46 | −83,49 |
| 180s | −1,18 | 86,47% | 4.805 | +11,69 | −83,49 |

As duas últimas colunas são o achado. Em toda a grade o ganho médio ficou em
[+11,33; +11,69] e a perda média em [−83,54; −82,91] — o payoff é INVARIANTE
ao freio, e é o payoff que fixa o breakeven empírico em ~87,9% (fórmula do
item 6.23). O freio só mexe na taxa de acerto, e mexe 0,77pp (86,22% a
86,99%) contra um buraco de ~1,1pp entre win% e breakeven. O parâmetro não
tem como fechar essa distância porque não toca na grandeza que a define.

A conferência que separa curva de ruído: desvio por operação ≈
√(w(1−w)(ganho+perda)²) ≈ R$31 com w≈0,87 e ganho+perda≈R$94; sobre ~4.800
operações, o erro padrão do R$/op de UMA célula é ±R$0,44. A dispersão ENTRE
as seis células de 30s a 180s tem desvio R$0,31 — MENOR que o ruído de uma
célula sozinha. A grade inteira é uma reta plana com ruído desenhado em cima.

O que isso custou nesta própria sessão: a varredura imprime uma célula por
vez (o padrão correto do repo — resultado sai quando fica pronto), e a
leitura em cima de dados parciais errou DUAS vezes antes de a grade fechar.
Com 3 pontos (10s/20s/30s): "está saturando", extrapolando uma assíntota em
−R$0,85/op. Com 5 pontos (até 60s): "é um U invertido com pico nítido em
30s", atribuído a uma seleção adversa do maker — mecanismo plausível e
inteiramente inventado — e quantificado como a produção jogando fora
R$1,16/operação por estar em 10s em vez de 30s. O ponto de 90s (−R$0,94,
melhor que o "pico" de 30s) derrubou as duas leituras, inclusive a que já
tinha explicação mecânica pronta. Uma história causal boa sobre dados
parciais é o sintoma mais perigoso de leitura prematura, não a defesa contra
ela.

> **Regra (portável).** Antes de ler uma varredura de parâmetro como curva,
> faça duas perguntas, nesta ordem: **(1) o parâmetro consegue mexer na
> variável que DECIDE?** Aqui a variável é o payoff (ganho médio e perda
> média), que fixa o breakeven (6.23). Se essas colunas saem constantes na
> grade inteira, o parâmetro não tem como virar o sinal do resultado, e
> qualquer "melhora" que apareça é remanejamento de ruído — carregue ganho
> médio e perda média em TODA tabela de varredura, não só líquido e win%.
> **(2) A dispersão ENTRE células é maior que o erro amostral de UMA
> célula?** Para resultado binário com payoff assimétrico, o erro padrão por
> célula é √(w(1−w)(ganho+perda)²/n). Se o desvio entre as células for menor
> que esse número, não há curva — há espalhamento, inclusive quando um pico
> vem com explicação mecânica pronta. **Corolário operacional:** em
> varredura que imprime em streaming (o padrão certo deste repo), não
> declare forma nem mecanismo antes da última célula — streaming existe para
> VER sem esperar o fim, não para CONCLUIR sem esperar o fim.

Cruza com **4.32**: a cadência de reancoragem É um mecanismo real, capaz de
zerar o preenchimento num pregão isolado (1.012 níveis armados, 0
preenchimentos) — mas agregada em 72 pregões, entre 20s e 180s ela não move a
variável que decide o resultado. Leia os dois juntos: não use este item para
negar 4.32, nem 4.32 para prometer ganho de calibrar o freio. Cruza com
**6.25** (eixo morto): lá o eixo não mexia em NADA; aqui o eixo mexe no
resultado aparente sem mexer na variável que decide — é a mesma armadilha um
degrau mais sutil. Cruza com **4.22** (escolher o parâmetro que "melhor
encaixa" na janela já vista é ajuste, não calibração): o mesmo risco existiria
aqui se a grade fosse lida célula a célula perseguindo o menor número, em vez
de esperar a forma completa.

---

### 6.45 O arreio de treino evolutivo criava um robô novo por pregão, zerava o estado semeado, e 11 de 33 features viraram ZERO CONSTANTE em toda a busca — 12h de CPU descartadas

2026-09-20, IA evolutiva do WDO@ (`wdo_evo`). O arreio de treino
(`scripts/daytrade/evo/avaliacao.py`, função `avalia`) roda UM backtest por
pregão, criando um robô NOVO a cada dia e entregando ao motor só as barras
daquele dia. Em cadeia: `previous_daily_bars` do motor sai vazio →
`strategy.seed_daily_volatility([])` deixa `range_diario_mediano = None` →
`features._razao(x, None)` devolve `0.0` — comportamento CORRETO e documentado
do módulo ("uma feature em 0 não empurra a decisão para lado nenhum"). Logo,
toda feature normalizada pela escala diária vale ZERO CONSTANTE, em todo
pregão, em toda geração.

**O número.** 11 das 33 features do banco são zero constante no caminho real
de avaliação (`larg_faixa`, `amplit_rel`, `dist_vwap`, `dist_abert`,
`gap_abertura`, `em_retangulo`, `pos_retangulo`, `ret_1`, `ret_15`,
`dist_max_sessao`, `dist_min_sessao` — verificado em 5 pregões,
`range_diario_mediano=None` nos 5). A busca tinha 20 features úteis, não 33.
Cada genoma tem 6 encaixes: apontar um para uma feature morta queima 1/6 da
capacidade de representação. Rodada perdida: 10 espécies × 60 indivíduos × 65
gerações, ~12h de CPU, mais ~4h de confirmação em tick descartadas. Duas
espécies tinham a premissa INTEIRAMENTE oca — `retangulo` (2 de 2 features do
núcleo mortas) e `vwap` (1 de 1 morta) — e o único finalista aprovado,
`extremos`, tinha 2 dos 3 núcleos mortos.

**A agravante.** No dia anterior (2026-09-19) foi corrigido um defeito da
MESMA família: o núcleo da espécie garantia que a feature estivesse PRESENTE
no genoma mas não que ela PESASSE — a correção impôs `PESO_MINIMO_NUCLEO =
0.15`, comentário gravado: "restringir a FORMA sem restringir o EFEITO não
restringe nada". Mas `peso 0,15 × feature 0,0 = 0,0`: verificou-se o peso e
não se verificou se a feature carregava informação. A mesma vacuidade uma
camada abaixo, encontrada só ao escrever a lição sobre a de cima.

**O que não estava errado.** A bancada padrão
(`scripts/daytrade/evo_wdo_bancada_2026_09_18.py`) carrega a janela INTEIRA
num backtest só, então os dias anteriores acumulam e a escala existe. O furo é
do arreio de TREINO, não do motor nem da bancada — um mesmo robô medido pelos
dois caminhos dá números diferentes por este motivo.

> **Regra (portável).** Uma feature que depende de estado semeado (escala,
> volatilidade, histórico de sessões anteriores) tem de ser VERIFICADA como
> viva no caminho de avaliação que a busca REALMENTE usa, não no caminho "de
> referência" — meça a variância de cada feature dentro do arreio de
> otimização e rejeite as constantes antes de gastar CPU. Default seguro para
> dado ausente ("devolve 0 quando não sei") é correto para uma DECISÃO e é
> veneno para uma BUSCA: ele transforma informação faltante em feature
> silenciosamente inerte, e um otimizador não reclama — ele só usa o resto do
> genoma. Degradação silenciosa seguríssima em produção vira falha invisível
> em otimização. Corolário do par de erros (peso mínimo em 2026-09-19, feature
> morta em 2026-09-20): ao corrigir uma vacuidade, siga a cadeia INTEIRA até o
> valor final entregue à decisão — não pare no elo que você acabou de achar.

> **Pergunte à plataforma nova:** quais features/indicadores dependem de
> estado semeado de sessões anteriores, e o arreio de otimização usado nesta
> plataforma entrega esse estado? Como isso é verificado — existe um teste que
> falha se uma feature ficar constante? (pergunta 115)

Cruza com **6.25** (eixo morto numa grade de parâmetro): aqui o "eixo morto"
não é um parâmetro varrido, é uma FEATURE inteira do espaço de busca, e a
causa não é o parâmetro não mexer em nada — é o dado de entrada já chegar
zerado antes da busca começar.

---

### 6.46 Um IS/OOS de dois meses num único contrato quase virou produção — o mês de "confirmação" era o 2º melhor de 60, e o contrato tinha 300× menos volume que o principal

2026-09-29, robô discricionário `wdo_ribbon_mm34` (WDO M1, ribbon de 4 médias
móveis de 34 períodos). Uma configuração ("onda ≤ 3 entradas/dia, range do
dia < 65 pontos, alvo = 25× a largura do ribbon") foi encontrada por
otimização real no MT5 e dada como "confirmada fora da amostra" comparando
agosto/2026 (+79,5 pts) contra setembro/2026 (+133,5 pts) no contrato
WDOV26. Rodando a MESMA classe — mesmo motor de simulação, aferido
operação-a-operação contra o Testador real — sobre a base contínua ajustada
por diferença de 5 anos (`WDO@D`, 698 mil barras M1), dividida em duas
metades:

**O número.** 3.372 operações, **−1.940,5 pontos**, **−0,575 ± 0,264
pt/operação**, win 26,2% contra breakeven empírico de 30,8%, **5 de 6 anos
calendário negativos**, **16 de 60 meses positivos**. Com o custo médio do
Testador (~0,33pt/operação) o resultado vai a ~−0,9pt/operação — ~−R$30 mil
em 5 anos a 1 contrato (1pt = R$10). Nenhum prejuízo real ocorreu (o robô
está em laboratório, nunca foi a produção) — o custo aqui é 100% de MÉTODO:
uma configuração quase foi promovida com base numa validação inválida.

**A causa raiz, em duas partes independentes.** (a) Setembro/2026 — o mês
usado para calibrar/confirmar — é o **2º melhor mês entre os 60 meses** da
base de 5 anos: a "confirmação fora da amostra" comparou contra um mês de
sorte, não contra o mês típico. (b) O contrato WDOV26 usado na janela de
"confirmação" de agosto negociava **~300 vezes menos volume** que o
contrato principal daquele mês — só ganhou liquidez perto do fim da janela
testada. As duas falhas se somam: a janela era curta E o contrato dentro
dela não representava o mercado real na maior parte do tempo.

> **A regra (portável).** Um IS/OOS de 1-2 meses num único contrato
> específico de futuro NUNCA valida sozinho a geometria de um robô
> intradiário. São necessárias DUAS confirmações independentes: (a) o
> resultado se sustenta numa série contínua/ajustada de longo prazo (anos,
> não meses), dividida em pelo menos duas metades temporais; e (b) o
> contrato específico usado em qualquer janela curta de validação tinha
> liquidez real (volume comparável ao contrato principal da época) durante
> TODO o período testado, não um contrato ainda em transição de rolagem.
> Sem as duas, uma "confirmação fora da amostra" pode estar confirmando
> contra um mês de sorte medido num mercado que não existia de verdade.

> **Pergunte à plataforma nova:** a plataforma oferece uma série
> contínua/ajustada de longo prazo (anos) pro instrumento, e como se
> confirma que um contrato específico usado numa janela curta de validação
> tinha volume/liquidez real (comparável ao contrato principal) durante todo
> o período testado, e não um contrato ainda em transição de rolagem?
> (pergunta 120, item 6.46)

Cruza com **6.15** (janela censurada perto do piso de capital não é
resultado — e IS/OOS vira sorteio) e com **6.6** (olhar o out-of-sample uma
vez já queima o recurso): aqui o sorteio não veio da censura por capital,
veio da janela em si ser curta demais e o instrumento por trás dela não ser
o mesmo mercado o tempo todo.

### 6.47 Stop curto medido em barras M1 com caminho de 2 pontos por vela deu "pista viva"; refeito nos ticks reais, 6 de 8 células congeladas viraram negativas

2026-10-04, estudo de pernadas do WIN (só dados de 2026). As simulações de
stop curto/técnico supunham um caminho intra-vela de 2 pontos por vela M1:
vela de alta vai da mínima à máxima, vela de baixa da máxima à mínima (confere
com os ticks em 86-88% das velas). Com esse caminho, geometrias de stop técnico
de 5-10 velas M1 com alvo de 5 a 7,5x o stop deram positivo na descoberta
(+117 a +242 pts/op), e uma delas ficou positiva nas três janelas — era a
"única pista viva" do estudo.

**O número.** Refeitas com ticks reais (mar-jun/2026, 83 pregões, os mesmos
dias), **6 de 8 células congeladas viraram negativas**: de +30/+160 para
-7/-67 pts/op. O stop técnico de 5 velas em T=750 foi de **+45 para -136
pts/op**; uma célula foi a **0% de acerto (n=9)**. Em escala pequena (recuos
< ~100 pts) o caminho de 2 pontos também gera ~5x mais (ou, conforme a escala,
metade dos) eventos de recuo que os ticks, e distorce métricas como "supera de
primeira" (0,43-0,46 no M1 contra 0,54-0,59 nos ticks). Para recuos >= 100 pts
M1 e ticks concordam. Nenhum prejuízo real: o custo foi de método — uma pista
quase virou próxima rodada de pesquisa (e candidata) sobre um artefato de
resolução.

**A regra (portável).** Resultado de stop curto — da ordem do range de 1-5
velas da base — medido em barras não é evidência até ser refeito no caminho
real (ticks) nos MESMOS dias; se divergirem, vale o tick. A suposição de
caminho intra-barra é uma premissa de execução tão decisiva quanto fila e
deslize, e deve ser declarada na linha do resultado. A resolução da base tem
de ser bem menor que o stop: quando o stop cabe em poucas velas, quem decide
se ele foi tocado antes do alvo é a ordem dos extremos DENTRO da vela, e é
exatamente isso que a barra não contém.

**Detalhe técnico.** O M1 contínuo do WIN é ajustado por diferença (`WIN@D`) e
os ticks são do contrato cru; alinhar por deslocamento diário, senão a
comparação mede o ajuste e não o caminho.

> **Pergunte à plataforma nova:** o histórico de ticks (negócios) está
> disponível para o período do backtest, com timestamp e preço por negócio, e
> alinhável à série de barras usada (atenção a séries ajustadas por diferença
> contra contrato cru)? (pergunta 121, item 6.47)

Cruza com **4.21/4.22** (premissa de fila declarada na linha), **6.22** (nulo
geométrico) e **6.46** (janela curta e série ajustada): mesma família de
"premissa de execução implícita decide o veredito".

### 6.48 Zero trades em toda a base não era "hipótese sem gatilho" — era ordem de operações dentro do `on_bar`: o estado recalculado apagava, na MESMA chamada, a precondição que tinha acabado de criar

No estudo de EA de day trade do WIN
(`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`), uma
`IntradayStrategy` combinava estado recalculado TODA barra (alinhamento de
EMAs M15/H1, armar ordem quando as condições batem) com uma ordem-limite
pendente controlada por prazo (`ttl_bars`). O `on_bar` atualizava esse
estado PRIMEIRO — o que podia armar uma nova ordem e, dentro do mesmo
passo, zerar o contador de espera que sinalizava "ordem pendente" — e SÓ
DEPOIS checava se já havia ordem pendente para decidir se emitia a ação.
Rodando na mesma chamada, essa checagem enxergava o contador que a própria
atualização de estado tinha acabado de zerar, e por isso descartava a ação
que tinha acabado de ser criada.

**O número.** A estratégia emitiu **ZERO ordens em toda a base testada**
(dois ciclos de teste, ~128 pregões, jan-jun e um rascunho de jul-ago/2026),
apesar de a condição de gatilho (rompimento de EMA9 no M15 com H1 alinhado)
ter ocorrido **383 vezes em 122 pregões** quando medida isoladamente, fora
do caminho de emissão. O silêncio total foi inicialmente atribuído — no
primeiro ciclo de teste — a uma causa real mas SECUNDÁRIA (um filtro de
horário rodando numa janela errada); o bug de ordem de operações só foi
achado ao auditar o código num segundo ciclo, depois de um ciclo inteiro de
medição gasto em cima do resultado errado.

> **A regra (portável, qualquer linguagem/plataforma).** Quando a lógica de
> uma estratégia bar-a-bar combina (a) estado recalculado a cada barra —
> indicadores, alinhamento, contadores de espera/armação — com (b) uma ação
> condicionada a "não há ordem pendente", a checagem de "ordem pendente" tem
> que ler o estado como ele estava no INÍCIO da barra, antes de qualquer
> atualização feita na MESMA chamada. Senão uma ordem armada nesta barra
> pode apagar a própria precondição que a criou, e a estratégia passa a não
> emitir NENHUMA ordem, de forma silenciosa e indistinguível de "a hipótese
> não tem gatilho" — o backtest roda limpo, sem exceção nenhuma, sempre
> devolvendo zero trades. Não é erro de lógica de sinal, é erro de ORDEM DE
> OPERAÇÕES dentro do handler de barra. **Corolário de verificação:** ao
> aceitar "zero trades" como resultado de uma hipótese, conte também as
> ocorrências BRUTAS do gatilho (sem o filtro de ordem pendente) e desconfie
> se a razão ordens-emitidas/ocorrências-brutas for anormalmente baixa ou
> zero — isso aponta para bug de implementação antes de apontar para
> "hipótese sem sinal".

> **Pergunte à plataforma nova:** o framework de backtest/execução da
> plataforma nova tem alguma forma de auditar/assegurar que uma estratégia
> bar-a-bar não está "silenciosamente nunca agindo" — por exemplo, contando
> ocorrências brutas da condição de gatilho versus ordens de fato emitidas,
> e alertando se a razão cair muito abaixo do esperado — antes de aceitar
> "zero trades" como veredito de uma hipótese? (pergunta 122, item 6.48)

Cruza com **6.25** (confirme que cada eixo de uma grade mexeu em alguma
coisa antes de ler o veredito) e com **7.1** (ao corrigir um bug, varra
todas as instâncias do padrão — aqui o padrão é "estado mutável lido depois
de atualizado na mesma passada").

### 6.49 Mais operações não é mais amostra: um gatilho que reentra 24 vezes no MESMO pregão multiplicou o contador sem multiplicar a independência

Na mesma busca de EA de day trade do WIN
(`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`, Geração 5), um
candidato com gatilho de "regime de alta amplitude por bloco de 15min"
disparou **667 operações em 95 dos 122 pregões** do período de
desenvolvimento — quase 5× mais operações que um candidato anterior da
mesma busca (127 operações). Isso foi lido, de início, como "amostra maior,
logo mais robusto". Medir a concentração (líquido dos 3 melhores pregões ÷
líquido total) desfez a leitura: o número deu **59% — IDÊNTICO ao do
candidato de amostra 5× menor**, não melhor. Auditando por pregão em vez de
só no agregado, a causa apareceu: o mesmo pregão em tendência forte gerava
DEZENAS de disparos do mesmo gatilho NAQUELE MESMO dia (máximo observado:
**24 operações num único pregão**, 2026-03-03) — a estratégia reentrava
repetidamente dentro dos dias já favoráveis, em vez de espalhar o sinal
para dias novos e independentes. O contador de "trades" tinha subido 5×; o
número de PREGÕES DISTINTOS que carregavam o resultado, não.

> **A regra (portável, qualquer linguagem/plataforma).** Contagem de
> operações não é o mesmo que contagem de amostra INDEPENDENTE. Antes de
> tratar "mais trades" como evidência de que um sinal é mais robusto ou
> menos frágil, meça também quantos PREGÕES (sessões) DISTINTOS carregam o
> resultado, e a fração do líquido concentrada nos top-N pregões — uma
> estratégia que reentra várias vezes dentro do MESMO pregão já favorável
> pode multiplicar o contador de operações sem acrescentar nenhuma
> observação nova e independente, e a concentração não vai melhorar só
> porque a frequência melhorou. Os dois eixos (frequência de operações e
> número de sessões independentes) precisam ser reportados separadamente
> sempre que "mais amostra" for usado como argumento de robustez.

> **Pergunte à plataforma nova:** o relatório de backtest da plataforma
> nova distingue contagem de OPERAÇÕES de contagem de SESSÕES/PREGÕES
> distintos, e sinaliza quando uma fração alta das operações se concentra
> dentro de poucas sessões (reentradas no mesmo dia já favorável), antes de
> aceitar "amostra grande" como evidência de robustez? (pergunta 123, item
> 6.49)

Cruza com **6.25** (confirme que cada eixo de uma grade mexeu em alguma
coisa antes de ler o veredito): um contador que sobe sozinho, sem o eixo de
independência ao lado, é o mesmo tipo de ilusão.

### 6.50 Filtro exclusivo muda qual EVENTO a estratégia encontra, não só qual sinal ela aceita — e isso fabrica gradiente onde não há nenhum

Numa busca de EA de day trade do WIN (`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`,
Geração 11), testou-se se a FORÇA de um gatilho de rompimento (magnitude do
rompimento além do nível, relativa ao tamanho da faixa) predizia a qualidade
do trade seguinte. Método inicial: rodar 3 simulações SEPARADAS e
EXCLUSIVAS — uma operando só sinais "fracos", outra só "médios", outra só
"fortes" — cada uma com o filtro ativo o pregão inteiro. O resultado pareceu
confirmar a hipótese: um gradiente limpo, win% e líquido crescendo do balde
fraco pro forte (**37,2% × 23,3% × 15,4%** de win rate). Mas o gradiente era
um ARTEFATO. Numa estratégia que REARMA — tenta de novo no mesmo pregão
depois que uma ordem expira ou é rejeitada — um filtro exclusivo que
descarta a primeira borda "fraca" do dia não elimina um trade: ele faz a
estratégia esperar a PRÓXIMA borda, que pode cair num horário e contexto de
mercado inteiramente diferente. Os três baldes não estavam comparando
"sinal fraco vs. forte no MESMO evento" — estavam comparando "qual edge
numerado do dia cada filtro deixou passar", uma variável confundida com
hora do dia e regime. A correção — estratificar PÓS-HOC os mesmos 121
trades de UMA ÚNICA rodada sem filtro, pela força de CADA trade real já
ocorrido — mostrou que a força não prediz nada: win% praticamente idêntico
nos três tercis (**37,5% / 37,5% / 36,6%**), correlação força×resultado
≈ zero (**−0,02 a −0,03**). O gradiente do método exclusivo tinha sumido
por inteiro.

> **A regra (portável, qualquer linguagem/plataforma).** Para testar se uma
> métrica candidata de "força/qualidade do sinal" prediz o resultado de um
> trade, numa estratégia que pode REARMAR (tentar de novo no mesmo pregão
> depois de um sinal rejeitado/expirado), nunca compare simulações rodadas
> com filtros EXCLUSIVOS diferentes (uma só aceitando sinais fracos, outra
> só fortes) — a rejeição de um sinal muda qual EVENTO SEGUINTE a estratégia
> vai encontrar, confundindo "força do sinal escolhido" com "qual outro
> sinal sobrou no lugar dele" (horário, contexto de mercado diferente). O
> teste correto é ESTRATIFICAÇÃO PÓS-HOC: rodar UMA ÚNICA simulação sem
> filtro nenhum, registrar a métrica candidata em cada trade real que
> ocorreu, e só DEPOIS separar os trades já ocorridos em grupos por essa
> métrica — isso preserva "mesmo conjunto de eventos, agrupado de formas
> diferentes" em vez de "conjuntos de eventos diferentes por construção".

> **Pergunte à plataforma nova:** o framework de backtest da plataforma
> nova oferece uma forma padrão de estratificação PÓS-HOC de trades já
> simulados por uma métrica candidata (sem precisar rodar uma simulação
> nova por grupo), para evitar o viés de comparar filtros exclusivos numa
> estratégia que rearma dentro da mesma sessão? (pergunta 124, item 6.50)

Cruza com **6.49** (contagem de operações não é contagem de amostra
independente) e com a família de itens sobre nulo/controle que atravessa a
janela cega (**6.42**): em ambos, o desenho do teste — não o dado — é quem
fabrica o efeito que parecia estar ali.

### 6.51 Critério de censura herdado de outra geração mediu o modo de falha ERRADO: seletividade por desenho foi lida como morte por capital

Numa busca de EA de day trade do WIN (Geração 12,
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g12_and_orb_cross/`),
testou-se combinar dois sinais independentes via AND — rompimento ORB
confirmado pelo estado anômalo WIN×WDO. O critério de "censura" dessa linha
de busca (criado na Geração 8, `g08_is_busca.py`) reprova automaticamente
qualquer célula com `sem_trade >= 50% dos pregões` OU `equity_min < margem
crua`. A regra foi desenhada para o modo de falha real da G07 — o robô
ficava sem caixa cedo na janela e o motor recusava em silêncio todas as
tentativas seguintes. Herdada sem revisão para a G12, a MESMA regra reprovou
TODAS as células "boas" (geometria vencedora herdada, stop_max=160pts/
alvo=3x, nas 4 janelas causais k_minutos∈{0,5,15,30}): `sem_trade` ficou em
110/122 (90,2%), 97/122 (79,5%), 91/122 (74,6%) e 90/122 (73,8%) dos
pregões — todas muito acima do limiar de 50% — enquanto `equity_min` foi
R$101,00, R$170,00, R$122,50 e R$122,50, **sempre acima** da margem crua de
R$100, com **zero** ordens recusadas por capital nas quatro janelas. O
mecanismo que a regra foi desenhada para detectar nunca aconteceu; a
reprovação veio inteiramente do outro ramo do OU — fração de dias sem
trade — que mede a coisa errada para um filtro AND que é seletivo por
desenho, não por falta de caixa.

> **A regra (portável, qualquer linguagem/plataforma).** Um critério de
> "censura" que combina, com OU, (a) o caixa ter cruzado uma barreira real
> E (b) uma fração mínima de dias/períodos com atividade, está testando
> DOIS modos de falha DIFERENTES com o MESMO limiar — e um filtro de
> confirmação AND entre sinais independentes (ou qualquer desenho
> deliberadamente seletivo) vai disparar o ramo (b) sempre, não importa a
> qualidade do resultado, porque baixa frequência é o PONTO do desenho, não
> um sintoma de morte. Antes de aplicar um critério de censura herdado de
> uma geração/estratégia anterior a uma estratégia com mecanismo de seleção
> estruturalmente diferente (mais sinais exigidos em AND, filtro mais
> restrito), separe os dois ramos e confirme qual deles de fato disparou:
> se foi só a fração de dias sem trade, E o caixa nunca encostou na
> barreira real, E nenhuma ordem foi recusada por capital, a célula não
> está censurada por falta de caixa — está apenas sendo avaliada com
> amostra pequena, e o gate correto para amostra pequena é a SIGNIFICÂNCIA
> ESTATÍSTICA do resultado (o IC95 do win% ultrapassar o breakeven
> empírico, não uma contagem mínima de dias operados).

> **Pergunte à plataforma nova:** o critério de "censura"/invalidação de
> uma célula de backtest da plataforma nova distingue explicitamente morte
> por falta de capital (caixa cruzou a barreira, ordens recusadas) de
> seletividade intencional de um filtro combinado (frequência baixa por
> desenho, ex. AND de sinais independentes), ou aplica o mesmo limiar fixo
> de "fração mínima de dias com atividade" às duas situações? (pergunta
> 125, item 6.51)

Cruza com **6.25** (confirme que cada eixo de uma grade mexeu em alguma
coisa antes de ler o veredito) e **6.49** (contagem de operações não é
contagem de amostra independente): nos três casos, um limiar ou contador
pensado para UM desenho de estratégia produz leitura errada quando
aplicado sem revisão a um desenho diferente.

### 6.52 Concentração medida só no período de desenvolvimento subestima a concentração fora da amostra — confirmado em TRÊS famílias de sinal sem relação entre si

Numa busca de EA de day trade do WIN
(`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`, Gerações 4, 17,
20 e 21), três famílias de sinal estruturalmente diferentes — confluência
cruzada WIN×WDO (estado anômalo de correlação), rompimento de abertura (ORB
momentum) e lateralização (retângulo, estilo `WinRetangulo`) — foram
medidas pela métrica de concentração (fração do líquido total vinda dos 3 e
dos 5 melhores pregões). Nas três, a concentração no período de
desenvolvimento (IS, jan-jun/2026) era moderada a boa: retângulo 41%/64%
top3/top5; cruzado, na melhor variante, 38,5%/58,4% top3/top5. Nas três, a
concentração **piorou de forma sistemática e grande** ao passar para o
período de validação (OOS-1, jul-ago/2026, nunca visto antes pela busca):
cruzado 56%→383% (G17) e depois 38,5%→467% (G20, variante diferente);
retângulo 41%→97,2% top3 e 64%→133,4% top5 (G21). Em nenhum caso geometria,
capital (testado de R$250 a R$1.000) ou sizing explicavam a piora — ela
apareceu em três mecanismos de geração de sinal sem relação entre si
(correlação entre dois instrumentos, rompimento de faixa, forma geométrica
de preço).

> **A regra (portável, qualquer linguagem/plataforma).** Quando uma
> estratégia tem frequência moderada a baixa (poucas dezenas a poucas
> centenas de operações por semestre), a concentração (fração do líquido
> vinda dos top-N pregões) medida SÓ no período de desenvolvimento não é
> uma boa estimativa pontual da concentração que a estratégia terá num
> período novo — ela tende a estar OTIMISTA (mais baixa que a real), e esse
> viés apareceu de forma consistente em três mecanismos de geração de sinal
> sem relação entre si. Trate a concentração do IS como um PISO plausível,
> não uma previsão — ao decidir se uma estratégia está robusta o bastante
> para ir a produção, exija folga bem maior na concentração do IS do que
> pareceria necessário (ex.: se o IS já mostra 40%, espere que o real possa
> chegar a 100% ou mais), e prefira olhar o gate do OOS real antes de
> confiar no número do IS como projeção de fragilidade.

> **Pergunte à plataforma nova:** o framework de validação da plataforma
> nova reporta a concentração (top-N pregões / líquido total) tanto no
> período de desenvolvimento quanto no de validação cega, lado a lado, e
> alerta quando a segunda for sistematicamente pior que a primeira — em vez
> de tratar o número do desenvolvimento como estimativa confiável da
> robustez real? (pergunta 126, item 6.52)

Cruza com **6.15** (janela censurada perto do piso de capital faz IS/OOS
virar sorteio) e com a auditoria original de overfitting (1 trade = 53,7%
do lucro): nos três, uma leitura de robustez feita só com o número do
desenvolvimento escondia uma fragilidade que só aparece fora da amostra.

### 6.53 Concentração medida no IS subestima a concentração fora da amostra — confirmado em QUATRO famílias de sinal independentes, incluindo um filtro desenhado especificamente para corrigi-la

O item 6.52 registrou o padrão em três famílias de sinal (G4/G17, G20,
G21) na mesma busca de EA de day trade do WIN
(`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`, ver
`ORQUESTRACAO.md`). Uma quarta tentativa (Geração 22) foi desenhada
**especificamente para corrigir** o modo de falha das gerações anteriores
— e reproduziu o mesmo padrão, de forma mais forte:

| geração / família de sinal | top3%/top5% no IS | top3%/top5% no OOS-1 |
|---|---|---|
| G4 (confirmação cruzada WIN×WDO) | 59% / — | 240% / — |
| G20 (cruzado, quantil mais baixo) | 38,5% / 58,4% | 467% / 696% |
| G21 (retângulo/lateralização) | 41% / 64% | 97,2% / 133,4% |
| G22 (retângulo + filtro de regime diário) | 32% / 50% (a MELHOR de toda a busca) | 607% / 816% (a PIOR de toda a busca) |

A G22 é o caso mais informativo porque o filtro não era um palpite: um
proxy diário causal (`amplitude_ontem`, a amplitude high-low do pregão
ANTERIOR do WIN@) separou "dias bons" de "dias ruins" no IS de forma
estatisticamente real — teste de permutação sobre a série diária de
líquido (não sobre trade), monotônico nos 3 tercis, sem reversão,
**p=0,0040**, a maior significância já medida em qualquer estratificação
desta busca inteira. Não era ruído. Mesmo assim, excluir o terço "ruim" do
IS e aplicar o MESMO limiar absoluto (congelado, sem reajuste nenhum) ao
OOS-1 **piorou** a concentração em vez de melhorar — de 97,2%/133,4%
top3/top5 que a estratégia-base já tinha SEM filtro no mesmo OOS-1, para
607%/816% COM o filtro — e derrubou o líquido do mesmo OOS-1 de 44
pregões de **R$650,00 (sem filtro) para R$89,50 (com filtro)**. O proxy
que previa regime favorável no IS perdeu ou inverteu o poder preditivo na
janela seguinte.

> **A regra (portável, qualquer linguagem/plataforma).** Quando o MESMO
> modo de falha (concentração temporal do líquido em poucos pregões)
> reaparece em múltiplas famílias de sinal estruturalmente diferentes —
> incluindo uma tentativa de correção desenhada especificamente para ele,
> construída sobre um efeito estatisticamente real no desenvolvimento — o
> diagnóstico correto deixa de ser "este parâmetro está errado" e passa a
> ser "a métrica de concentração medida só no desenvolvimento não é
> preditiva de estabilidade fora da amostra". Significância real no IS
> (um p baixo, um efeito monotônico, sem reversão) não é garantia de que o
> mesmo efeito sobreviva na janela seguinte quando o único insumo é
> preço/volume do próprio instrumento — o histórico acumulado (4 de 4
> tentativas, sempre piorando, nunca melhorando) é a evidência de que essa
> transferência tende a falhar. Antes de aceitar concentração saudável no
> IS — com ou sem filtro — como evidência de robustez, confirme que ela se
> mantém, não necessariamente idêntica mas na mesma ordem de grandeza, em
> pelo menos uma janela nunca vista.

> **Pergunte à plataforma nova:** existe, na plataforma nova, uma forma
> padrão de medir se uma métrica de concentração/robustez é ESTÁVEL entre
> janelas (não apenas "boa" numa única janela) antes de promover um
> candidato — por exemplo exigindo a métrica dentro de uma faixa aceitável
> em pelo menos 2 janelas fora da amostra, em vez de confiar no número de
> uma única janela de desenvolvimento? (pergunta 127, item 6.53)

Cruza com **6.49**, **6.50**, **6.51** e **6.52** (mesma família: o
desenho do teste, não o dado, fabrica ou esconde o efeito) — aqui o
desenho que falhou era, ele próprio, uma tentativa de correção, o que
descarta a leitura de que bastaria "desenhar melhor o filtro" para
resolver o problema.

### 6.54 Sinais idênticos, saídas diferentes: o testador novo deu −R$ 1.043 contra −R$ 64 do motor — o defeito era de execução, e o campo de preço que disparava o stop vinha ZERADO em quase todo tick

Medido em 2026-10-06 no EA `mt5/WinDeslocamentoMatinal.mq5`, rodado no Strategy Tester do MT5 da Rico (WINV26, 12/08/2026 a 01/10/2026, "cada tick baseado em tick real"). **12 operações, com sinais idênticos aos do motor Python** — a estratégia estava certa; só a saída divergia. Três versões do EA, três resultados:

| versão | como o stop era controlado | resultado | motor Python |
|---|---|---|---|
| v1.0 | SL nativo anexado à ordem-limite de entrada | **−R$ 1.043** | −R$ 64 |
| v1.20 | stop no EA, lendo `SYMBOL_LAST` | **−R$ 535** | −R$ 64 |
| v1.21 | `last` com fallback para bid (compra) / ask (venda); SL ao servidor só FORA do testador | **−R$ 78** | −R$ 64 |

**v1.0.** O SL das COMPRAS disparou no mesmo segundo da entrada (**5 de 5**, saída no próprio preço de entrada) e o das VENDAS **nunca** disparou: em 24/08 a posição saiu no fim do dia com −R$ 528 onde o stop teria dado ~−R$ 312. Dois comportamentos opostos do mesmo stop nativo, ambos errados, ambos longe do que a corretora real faria.

**v1.20.** Para fugir do SL nativo, o stop passou a ser controlado no EA pelo `SYMBOL_LAST`. No testador o `last` vem **0 na maioria dos ticks** (registrado no Diário: `last=0`), então a condição do stop nunca era verdadeira: o stop nunca disparou, −R$ 535. A causa só apareceu porque o valor lido foi escrito no log.

**v1.21.** Fallback para bid (compra) / ask (venda) quando `last` é 0, e SL enviado ao servidor só fora do testador: −R$ 78, alinhado ao motor (−R$ 64). Os R$ 14 restantes não foram explicados e ficam como diferença conhecida.

O que torna o caso perigoso é que −R$ 1.043 parecia um veredito sobre a estratégia. Só a comparação operação a operação com o motor — sinais iguais, saídas diferentes — mostrou que a estratégia não tinha nada a ver com o número.

> **A regra.** Antes de ler o resultado de um testador ou plataforma nova, confira OPERAÇÃO A OPERAÇÃO contra a referência (o motor próprio): sinais iguais e saídas diferentes significam defeito de execução, não da estratégia. E nunca confie que o campo de preço que dispara o stop (último negócio, bid, ask) existe em todo tick do histórico simulado: registre no log o valor que o stop está lendo.
>
> **Pergunte à plataforma nova:** No simulador/testador da plataforma, quais campos de preço vêm preenchidos em cada tick do histórico (last, bid, ask) e qual deles dispara o stop nativo? O SL anexado a uma ordem pendente é avaliado do mesmo jeito que o SL de uma posição? (pergunta 129, item 6.54)

Cruza com **1.2** (o stop nativo anexado à ordem é o desenho correto na corretora real — o que falhou foi o simulador avaliá-lo), **4.20** a **4.22** (o mesmo erro de modelo do outro lado: o motor próprio dando o que a plataforma não dá) e **6.18** (concordância com o motor é o que separa hipótese de previsão).

---

### 6.55 Um EA com o tamanho do tick digitado na mão rodou num instrumento de grade diferente: a corretora recusou as ordens, o que sobrou deu +R$1.042, e a recusa foi lida como edge

Medido em 2026-10-06 no EA `mt5/WdoRetangulo.mq5`, escrito para o WDO (tick 0,5) com o tamanho do tick **digitado**: `input TickSizeWdo = 0.5`, piso de largura de 4,4 ticks e `NormalizeDouble` com `_Digits`. Rodado no Testador sobre o WINV26 (tick de 5 pontos), gerou preços de entrada, stop e alvo inteiros fora da grade, e a corretora recusou toda ordem cujo preço não fosse múltiplo de 5 (retcodes `10015` *invalid price* e `10016` *invalid stops*). O que não foi recusado virou trade: **+R$1.042, 22 trades em 36 pregões (12/08 a 01/10/2026)** — e foi lido como edge.

| leitura | resultado |
|---|---|
| Testador, EA com defeito (ordens recusadas filtrando) | **+R$1.042** · 22 trades · 36 pregões |
| Réplica com o tick correto, agosto | **−R$1.451 a −R$1.728** |
| Holdout jan–jul/2026, versão com defeito | **−R$689** |
| Holdout, melhor regra derivada do "acidente" (fade contra a abertura às 11:00) | **−R$4.264** — percentil **13,6** de um sorteio de lado |
| Candidatos que passaram o percentil 95 | **0** |

A recusa aleatória funcionava como um filtro de horário que ninguém desenhou: só entravam as ordens cujo preço, por sorte, caía numa grade válida. O lucro era propriedade desse filtro acidental, não do sinal. Custo: **uma rodada de pesquisa inteira (~1.200 células em 3 agentes)** gasta para refutar um resultado gerado por ordens que a corretora nunca aceitou.

> **A regra.** Um EA nunca digita tick, dígitos ou valor do ponto: lê do símbolo em tempo de execução (tamanho do tick, dígitos, volume mínimo) e arredonda todo preço — entrada, stop e alvo — na grade do símbolo. E, antes de ler o resultado de qualquer teste, **conte as ordens recusadas pela corretora ou pelo testador**: recusa > 0 torna a linha censurada. Ela mede o filtro acidental, não a estratégia.
>
> **Pergunte à plataforma nova:** Na plataforma nova, como obtenho o tamanho do tick e a grade de preço válida do instrumento em tempo de execução, e onde o simulador/teste reporta as ordens recusadas por preço inválido? (pergunta 133, item 6.55)

Cruza com **5.33** (o simulador devolvendo ordem sem o campo que o stop lê — outro caso de número lido sem conferir o que o gerou), **6.51** (censura medida pelo critério errado). O tick é propriedade do INSTRUMENTO, não do robô.

### 6.56 O motor em barras só avaliava stop e alvo a partir da barra SEGUINTE ao preenchimento: 13,9% dos trades tinham um stop estourado dentro da barra do fill, e o pior trade perdeu 3,9× o stop nominal

Medido em 2026-10-06 no estudo de gap do WIN (`scripts/daytrade/win_gap_estrategia_2026_10_06/rodada2_2026_10_06/RESULTADO.md`). O motor intradiário em barras (`src/backtest/intraday/machine.py`) só avalia stop e alvo **a partir da barra depois do preenchimento da entrada**. Quando a ordem-limite de entrada enche numa barra e o nível do stop é cruzado DENTRO dessa mesma barra, o backtest ignora o cruzamento e deixa a posição correr até a barra seguinte, onde a saída acontece num preço muito pior que o stop. Em 60 células de saída, 3.283 trades, WIN M5, 2 contratos:

| medida | resultado |
|---|---|
| trades com stop atingido DENTRO da barra do fill, ignorado pelo motor | **457 (13,9%)** |
| trades com alvo atingido DENTRO da barra do fill, ignorado pelo motor | **111 (3,4%)** |
| pior trade, stop de 350 pontos, motor em barras | **−1.210 a −1.360 pontos (3,5× a 3,9× o stop)** |
| pior trade, mesma regra, simulador em ticks | **−355 pontos (1,01× o stop)** |
| rodada 1, 1 contrato: pior trade contra stop nominal de R$70 | **−R$242,50** |
| soma das 60 células | **R$323.440 (barras) → R$304.863 (ticks)** |

O erro tem duas direções, e a de perda é a que esconde risco: o relatório mostrava um robô cujo pior trade era mais de 3× o stop que ele jurava ter — e, na outra ponta, 111 alvos que o motor não viu. A soma encolheu **R$18.577 (5,7%)** quando a barra do fill passou a ser resolvida em ticks.

**Segunda discrepância, da mesma família.** Com `exit_ttl_bars=10**9` (a saída sem prazo de produção) o motor **arma** a fatia do alvo no primeiro toque do nível e só a preenche numa barra POSTERIOR. Isso difere de uma ordem-limite que já estava parada no livro desde o preenchimento da entrada, que pode encher dentro da própria barra do fill. Na mesma célula: **+R$4.067 no motor contra +R$2.676 no simulador em ticks.** É o mesmo defeito visto do lado do alvo: o motor trata "a barra do fill" como se nada pudesse acontecer nela.

> **A regra.** Um backtest em resolução de barra tem de **decidir o que acontece dentro da barra do preenchimento, depois do fill** — deixar isso sem avaliação não é neutro: esconde perdas maiores que o stop e relata um risco que a estratégia nunca teve. Duas saídas honestas: (1) resolver a barra do fill com dado mais fino (ticks); ou (2) adotar a premissa conservadora — **se o nível do stop está dentro da faixa restante da barra do fill, assuma que o stop foi atingido.** E **reporte sempre o pior trade em múltiplos do stop nominal**: valor bem acima de 1× é o sintoma, e é barato de checar.
>
> **Pergunte à plataforma nova:** Como a plataforma nova trata stop/alvo atingidos na mesma barra/tick em que a entrada preencheu? O backtest dela avalia a saída dentro da barra do fill? (pergunta 139, item 6.56)

Cruza com **6.47** (stop curto medido em M1 com caminho de 2 pontos por vela: mesma família de erro, resolução de barra escondendo o que acontece dentro dela), **6.54** (campo de preço que dispara o stop) e **4.8** (o alvo que o simulador dá de graça). A premissa embutida em "decido na barra" precisa ser lida contra o pior trade, não contra a média.

---

## Parte 7 — Disciplina de trabalho

### 7.1 Ao corrigir um bug, varra todas as instâncias do padrão

O mesmo defeito de cancelamento existia em 5 pontos; o lado da saída escapou da
primeira varredura porque a busca procurou o método direto e não os chamadores de
cada método de cancelamento.

> **Regra:** depois de achar a causa raiz, pergunte "que outros lugares leem o
> mesmo campo / fazem a mesma coisa da mesma forma errada?" e corrija todos antes
> de declarar terminado.

A família 5.7 → 5.8 → 5.19 → **5.21** é a prova mais cara disto no arquivo: o
mesmo defeito (constante do instrumento buscada onde der) foi corrigido três
vezes em três caminhos diferentes antes de alguém perguntar por que ele
reaparecia. **Corrigir uma instância de um padrão sem varrer todas as outras não
corrige o padrão — só move a data da próxima ocorrência.**

### 7.2 Verifique contra a instância viva, não contra a documentação

Um texto de tela escrito a partir de docstrings **inverteu uma regra de saída** e
citou um número que não existia como parâmetro. Comentário e docstring descrevem
o que alguém pretendia; a instância descreve o que roda.

Este arquivo não é exceção: se um item aqui contradiz o código, o código ganha.

### 7.3 Suíte vermelha treina a ignorar suíte vermelha

Três testes ficaram vermelhos por dias porque tinham ficado para trás de uma
mudança de comportamento — não eram bugs. Enquanto estavam vermelhos, ninguém
olhava os outros.

E o inverso: rodar a suíte com robôs operando gera falha e erro **falsos** (os
testes leem o estado real da operação). Saber distinguir o ruído ambiental da
regressão é parte da disciplina, não um detalhe.

### 7.4 Validação contra ambiente real usa dry-run

Ao testar um caso contra o terminal real, uma chamada de envio foi usada no lugar
da de verificação — a ordem só não executou porque o pregão estava fechado.

> **Regra:** validação contra ambiente real usa a primitiva de simulação
> (`order_check` e equivalentes) SEMPRE, a menos que o teste seja
> deliberadamente um envio real.

### 7.5 Pergunte antes de escrever a "regra oficial" a partir de inferência

Uma reconstrução de regra de negócio feita por evidência indireta (código +
memórias antigas) saiu quase toda errada.

### 7.6 Agentes adversariais geram as perguntas que você não fez

Os 27 defeitos desta lista não apareceram sozinhos. Apareceram quando quatro
revisões independentes, com lentes disjuntas e instruídas a **não confiar em
docstring**, foram soltas sobre o mesmo código.

E a primeira rodada fechou 13 e declarou o resto "de severidade menor" — releitura
mostrou que 3 dos que sobraram eram CRÍTICOS. **Antes de declarar uma auditoria
fechada, releia a lista inteira — e grave a lista em disco.**

Corolário do corolário: o próprio relatório de quem corrige carrega a lista
seguinte. Três achados que os agentes reportaram como "risco residual, não
corrigi" viraram, cada um, um defeito real e reproduzível quando alguém foi
verificar. **"Fora de escopo" no relatório de um agente é uma tarefa, não uma
nota de rodapé.**

### 7.7 A suíte não pode ler nem travar o que a produção usa

Dois testes de painel piscavam conforme os robôs reais estivessem rodando ou não.
A varredura do padrão achou **seis arquivos** afetados — em um deles, 59 de 60
testes liam o arquivo de estado real da operação. Os dois que "falhavam" eram só
os que tinham asserção sensível ao conteúdo; o resto lia em silêncio. Pior: a
rotina que o painel chama para montar a tela **reescreve** esse arquivo quando
encontra um processo morto — um teste podia sobrescrever o estado que comanda os
robôs de verdade.

O mesmo padrão tem uma forma pior, que a detecção não pega. A suíte chamava o
caminho de linha de comando de verdade e, com ele, **tomava a trava de
exclusividade do slot na pasta real**. Enquanto a suíte rodava, um robô de
produção tentando subir naquele slot era recusado: o teste ganhou poder de veto
sobre a operação. Nenhum guard baseado em assinatura de arquivo veria isso —
tomar uma trava que já existe não muda tamanho nem data do arquivo.

E a forma mais cara é a terceira, medida no mesmo dia em que as outras duas foram
corrigidas. A suíte roda em paralelo contra o **banco que a operação escreve**, e
enquanto rodava seis robôs ficaram **22 minutos sem conseguir gravar**:
`database is locked`, **1.100 ocorrências**, todas na mesma janela de 30 minutos —
contra 3 em toda a semana anterior. Não é lentidão. Com espera de 5s por lock e
passo de 5s, cada passo falhava inteiro: os robôs ficaram cegos, não lentos. Ao
voltar, os seis declararam buraco de pregão — **81 barras puladas** somadas — e um
deles **achatou a posição aberta** pelo protocolo de buraco. Uma decisão de saída
causada pela suíte de testes, não pelo mercado. Naquele dia era sombra; o mesmo
minuto em modo real é uma saída forçada sem sinal, e o robô que ficou cego não
viu o próprio stop.

> **Regra:** teste nunca alcança caminho de produção — nem para ler, nem para
> disputar lock de banco. Onde der
> para **impedir** (apontar a constante para um diretório temporário em toda a
> suíte), impedir vale mais que detectar depois; onde só der para detectar, falhe
> o teste que sujou, no instante em que sujou. E a mensagem de falha tem de
> perguntar **quem** escreveu antes de acusar o teste: o robô ao vivo escreve nos
> mesmos arquivos, de outro processo, e diagnosticar suíte contaminada como bug
> de código já custou tempo aqui (7.3).

### 7.8 Hipótese de custo lida no código é hipótese — meça a chamada antes de corrigi-la

2026-09-04, diagnosticando o travamento do item 5.9. A leitura do código dava
uma explicação convincente: o laço quente aplicava um piso de janela de 24h em
**toda** volta de 5s, então cada passo pedia um dia inteiro de negócios do
mini-dólar. Escrevi a correção (estreitar a janela quando a marca d'água está
fresca), com testes cobrindo os três regimes, suíte verde — e só ENTÃO medi.

Duas coisas caíram de uma vez. A busca é **instantânea**: 0,05s, 0,20s e 0,07s,
inclusive a de 196.712 negócios — o custo não estava ali, a hipótese estava
errada e o fix não corrigia nada. E, pior, a janela estreita de 2 minutos
devolveu **0 negócios** com o mini-dólar negociando sem parar (5.3): a
"correção" teria deixado o robô cego em silêncio, que é o modo de falha mais
caro deste arquivo. O código foi revertido antes de qualquer processo subir com
ele; o custo real (32 buscas de ~14s na inicialização) só apareceu ao cronometrar
chamada por chamada.

> **Regra:** custo lido no código é hipótese, não medida — cronometre a chamada
> suspeita isolada, no instrumento real e no horário real, antes de escrever
> correção. E quando a correção for **estreitar uma guarda de segurança**,
> re-meça primeiro se a guarda ainda sustenta peso: a justificativa dela pode
> continuar viva muito depois de o incidente que a criou sair de vista. Um fix
> que passa a suíte inteira e mede zero ganho está corrigindo a coisa errada.

---

## Parte 8 — Perguntas a responder antes da primeira ordem real na plataforma nova

Nenhuma destas é opcional. Cada uma corresponde a um item acima que já custou
dinheiro ou meses.

> Nota de manutenção: a contagem de perguntas (aqui e no rótulo da página
> publicada) é DIGITADA, não derivada da lista — já nasceu defasada uma vez.
> Ao adicionar ou remover uma pergunta, atualize o número à mão nos dois
> lugares (este arquivo e o artefato) em vez de assumir que algum contador
> automático cobre isso.

**Sobre a ordem**
1. Dá para enviar stop e alvo no MESMO comando da entrada? (1.2)
2. Existe primitiva de "fechar posição" distinta de "ordem no sentido oposto"? (1.1)
3. O que acontece quando a ordem de fechamento é maior que a posição — rejeita ou inverte? (1.4)
4. Como a plataforma reporta um cancelamento que falhou? Dá para distinguir de sucesso? (1.5)
5. Ao atualizar proteção, campo vazio significa "manter" ou "remover"? (1.10)
6. Ordem PENDENTE de fechamento (limite, não a mercado) tem a mesma
   exigência de "amarrar à posição" que ordem a mercado de fechamento?
   Testar antes de confiar no caminho de saída fatiada com posição real —
   não assumir que a correção de um caminho cobriu o irmão. (1.15)

**Sobre o estado**
7. Dá para listar as ordens vivas do meu robô ao iniciar? (1.8)
8. A leitura de posição distingue "não há" de "não consegui perguntar"? (1.6)
9. O que sobrevive a um reinício da plataforma, e o que eu preciso persistir por fora? (2.1)
10. Como impedir duas instâncias do mesmo robô? A plataforma impede? (2.4)
11. Dá para gravar de forma durável no meio de uma sequência de ordens, sem
    perder a sessão e sem um segundo escritor travar a operação em andamento? Se
    não, qual é o menor lote que pode ser gravado atomicamente? (2.5)
12. O modelo de erro permite carregar dado junto da exceção — ou recuperar o
    resultado parcial de uma chamada que abortou no meio? Se não, nada de
    acumular efeito confirmado em variável local: cada um é emitido assim que
    confirma. (2.5)
13. O evento de rejeição de uma ordem chega de volta pra quem decidiu, ou fica
    só no log do motor de execução? (1.14)
14. Toda rotina de reconexão/retomada recalcula o mesmo estado (caixa
    dinâmico, indicadores) que a inicialização normal calcula, ou herda um
    campo zerado/default até o próximo ciclo regular? Um "warm start" que
    pula um passo de setup vira bug silencioso, não atalho inofensivo. (3.14)

**Sobre o dinheiro**
15. Dá para consultar a margem exigida por uma ordem e a margem livre da conta? (3.3)
16. Múltiplas estratégias/processos operam a mesma conta e compartilham
    margem física? Se sim, existe alguma trava entre "consultar quanto
    sobra" e "gastar", ou cada processo confia só na própria última
    leitura? (3.13)
17. A conta é netting ou hedging? (1.4)
18. Existe algum limite de perda diária imposto pela plataforma, ou preciso construí-lo? (Parte 0, falha 5)
19. O capital mínimo que abre 1 posição foi testado rodando o histórico
    INTEIRO com esse capital, ou só calculado pela fórmula de margem? Os
    dois números costumam divergir por uma ordem de grandeza. (3.10)
20. Se o capital de sobrevivência estiver acima do capital real disponível,
    isso já foi confirmado como estrutural (parede em TODO ponto do
    parâmetro já mapeado), ou ainda pode ser um parâmetro mal escolhido?
    Varrer o espaço inteiro contra capital baixo responde em uma tarde. (3.11)
21. O stop desta estratégia é fixo (ticks/pontos) ou varia com a
    barra/dia (volatilidade)? Um teto por % de risco emprestado de outro
    robô com o tipo OPOSTO de stop pode reproduzir o problema que ele foi
    criado pra evitar, só que noutro capital. (3.12)
22. Abrir uma posição vendida credita caixa (venda a descoberto) ou debita
    margem/garantia (compromete capital, igual à compra)? O valor-a-mercado
    da posição na tela tem de inverter exatamente o débito/crédito real da
    abertura — não uma convenção genérica de "venda é negativo". (5.8)

23. A plataforma recusa no momento do REGISTRO uma ordem cujo tamanho não
    cabe na margem livre, ou aceita registrar e só recusa no preenchimento?
    Se recusa só no preenchimento, a recusa é parcial (preenche o que cabe)
    ou total? Recusa total no preenchimento é o caminho mais curto para um
    robô inerte com ordem viva no book. (3.15)

**Sobre a medida**
24. O simulador modela posição na fila? Se não, o que ele está respondendo? E
    ele modela ENTRADA e SAÍDA com o MESMO rigor, ou só um dos dois lados?
    Aqui a entrada tinha modelo de fila desde 2026-08-26 e a saída não tinha
    nenhum até 2026-09-09 — a mesma pergunta feita de um lado só deixou
    passar 43 pregões de calibração otimista do outro. **Estendida:** a
    plataforma expõe profundidade de book (não só volume agregado por
    barra), de forma que dá para estimar a posição da MINHA ordem
    especificamente — quantos contratos/ações estão na frente dela, não só
    quantos negociaram no nível? Sem isso, todo modelo de fila é calibrado
    por proxy (volume da barra), nunca pela fila real observada.
    **Estendida (2026-09-09, noite):** e o modelo de fila que existe está
    LIGADO? Aqui o parâmetro do lado da ENTRADA existia desde 2026-08-26, com
    nome e docstring, e nunca foi atribuído em lugar nenhum — ficou no default
    neutro `0.0` por um mês. "O simulador modela fila?" tem de ser respondida
    medindo o valor EFETIVO em uso na rodada, nunca lendo o código que declara
    o parâmetro. (4.1, 4.21, 4.22)
25. O horário de sessão que ele usa é fixo ou segue o instrumento? (5.2)
26. Qual é o edge da estratégia **em ticks** neste instrumento? (4.5)
27. Uma sequência de stops cabe no capital real? Se o tamanho da posição
    escala com o caixa, existe um teto de RISCO por trade separado do teto
    de MARGEM? (3.5, 3.9)
28. O preço que a API devolve para este instrumento já é reais por unidade,
    ou é cotação (pontos de índice, pontos de dólar, ticks) que exige um
    multiplicador para virar dinheiro? Se exige, o débito/crédito de caixa
    lê esse multiplicador do MESMO lugar que o cálculo de P&L, ou é uma
    segunda cópia da fórmula? E esse lugar é indexado pelo INSTRUMENTO — não
    pelo robô, pela tela nem pelo script? Dois robôs no mesmo símbolo têm
    obrigatoriamente o mesmo multiplicador; se ele puder ser declarado por
    robô, ele vai divergir. (5.7, 5.21)
29. Um reinício no meio do pregão detecta e repõe (por replay) o estado de
    JANELA/indicador intra-sessão de QUALQUER estratégia, ou só das que
    alguém lembrou de marcar com um atributo especial? Um portão de warm
    start por allowlist nomeada é um cold-restart silencioso pra toda
    estratégia nova. (2.6)
30. Quantas chamadas de histórico a inicialização de sessão faz, e quanto
    custa CADA uma no feed mais fino que algum robô consome? Toda constante
    escrita "por sessão"/"por barra" está em unidades do feed: 15 sessões
    podem ser 570 barras num feed e 140.000 no outro, pela mesma linha de
    código. Meça o produto *(chamadas × custo)* no feed mais fino antes de
    ligar. (5.9)
31. O sinal de vida que o vigia externo lê cobre o INTERIOR de um passo, ou
    só o topo do laço? Se só o topo, o limiar dele tem de ser maior que o
    pior passo legítimo — senão o vigia mata trabalho que ia terminar e cada
    reinício cobra o custo de novo, mais caro. E trabalho de inicialização
    sobre sessão ENCERRADA é reaproveitado entre reinícios, ou refeito do
    zero a cada vez? (5.9)
32. Existe uma consulta de HISTÓRICO (distinta da leitura de estado
    corrente) que devolve o desfecho definitivo de uma ordem que saiu do
    book — pendente, preenchida, cancelada/recusada/expirada — e os deals
    reais (preço, quantidade, lucro) de uma posição já fechada, buscável
    por um identificador estável? Sem ela, um ciclo inteiro (preenche +
    fecha) que aconteça dentro do intervalo entre duas consultas fica
    invisível para sempre, e todo fechamento "recusado" que na verdade
    executou vira número inventado no diário. **Estendida (2026-09-09):** essa
    consulta — ou o meu próprio diário — distingue "a ordem-limite de saída
    preencheu no nível" de "a ordem-limite estourou o prazo e o RESTANTE saiu
    a mercado"? As duas coisas podem chegar com o MESMO `motivo de saída`
    (aqui, "alvo") e pagam custos diferentes — 1 de 7 preencheu por limite,
    6 saíram a mercado no mesmo pregão, e um simulador que rotula as duas do
    mesmo jeito mede o modelo, não o mercado. (1.17, 4.21)
33. A ordem de take-profit fica RESTING no livro como limite de verdade
    (preço pedido ou melhor) ou é gatilho varrido a mercado no toque (pode
    deslizar)? Meça o preço EXECUTADO contra o nível PEDIDO em pelo menos 10
    saídas antes de confiar em qualquer alvo pequeno — aqui foram **10 de 11
    pior que o nível, ZERO a favor** (média −1,000 tick, desvio 0,447), e o
    erro foi sempre CONTRA a posição, o que faz um alvo de 2 ticks ser pago
    como 1. O alvo mínimo viável é o deslize observado mais o custo por
    ida-e-volta. Meça o STOP **separadamente**: aqui ele andou na direção
    OPOSTA (5 de 5 nunca pior que o nível pedido), e um único número de
    "deslize de saída" teria escondido as duas coisas. A fonte da medição é o
    histórico da CORRETORA (o par nível-PEDIDO × preço-EXECUTADO), nunca o
    diário do robô — o diário grava a intenção, e intenção não desliza. (4.8,
    4.15)
34. A ordem-limite da plataforma reprecifica sozinha (ou permite configurar
    cancelamento por timeout / distância de deriva do preço) quando o
    nível armado não é tocado, ou ela fica parada indefinidamente esperando
    um preço que pode nunca voltar? Reancoragem que só acontece ao ARMAR
    expõe a uma fatia estreita do pregão, não ao pregão inteiro, e nenhuma
    métrica agregada denuncia isso sozinha. (4.9)
35. A saída dinâmica/trailing que esta plataforma oferece fecha como ordem
    PARADA (maker, sem pagar o spread) ou A MERCADO (paga o spread/slippage
    a cada fechamento)? Se a saída original que ela substitui era maker, o
    custo extra por trade precisa ser medido e somado ao breakeven antes de
    decidir se o trailing vale a pena. (4.10)
36. O filtro de atividade/liquidez pré-entrada que esta plataforma oferece
    (ou que você vai construir sobre o feed dela) foi medido nos dois
    eixos — velocidade de preenchimento E P&L — separadamente, em pelo
    menos duas janelas de tamanhos diferentes? Um filtro que acelera o
    preenchimento não necessariamente melhora o resultado, e uma amostra
    pequena pode mostrar o efeito OPOSTO de uma amostra grande no mesmo
    teste — o veredito é sempre o da amostra grande, nunca o da pequena só
    porque bateu positivo primeiro. (4.11)
37. O script/ferramenta nova reimplementa a chamada ao terminal, ou usa a
    rota compartilhada que já converte fuso? A hora que a API devolve é UTC
    ou hora de parede do servidor? Um número de fuso declarado em dois
    lugares é um número que vai divergir — e a divergência se apresenta
    como bug de estratégia, nunca como erro de relógio. Reincide em
    qualquer arquivo derivado que tenha caminho de geração próprio, mesmo
    depois de corrigida na rota principal. (5.10, 5.14)
38. A consulta de histórico avisa quando devolve MENOS do que a janela
    pedida, ou entrega um resultado curto em silêncio? A partir de quanto
    tempo depois do fechamento o dado do pregão de hoje fica completo? Sem
    essas duas respostas, "zero resultado" é indistinguível de "zero
    dado" — e toda rotina de pesquisa precisa da mesma defesa de piso que
    a rota de produção. (5.11)
39. Cada ordem e cada preenchimento carregam, no próprio registro, a conta
    e o MODO (real / simulado / papel) em que foram gerados, de forma que
    uma consulta separe os dois sem depender de convenção de nomenclatura?
    Misturar as contas numa soma infla a atividade e melhora a taxa de
    acerto — o erro anda na direção que ninguém audita. (4.12)
40. Dá para rodar o MESMO sinal simultaneamente em conta real e em conta
    sombra/papel, com os registros separáveis por conta? Se der, a razão
    entre os preenchimentos das duas É a taxa de preenchimento passivo
    real, que nenhum backtest sabe estimar — e ela deve começar a ser
    acumulada no primeiro dia, não depois de alguém desconfiar do
    backtest. (4.13)
41. A coleta PAGINADA de histórico confere que uma página encosta na
    seguinte, ou confia que o cursor caiu no lugar certo? E todo limite de
    tempo entregue à API carrega fuso explícito, ou algum deles é
    resolvido no fuso da máquina que executa? Um cursor sem fuso desloca
    cada borda de página e apaga dado proporcional ao TAMANHO da página,
    sem exceção nenhuma — e se a junção do armazenamento for união,
    reexecutar preserva os buracos em vez de corrigi-los. (5.12)
42. Que limites de taxa/cadência a plataforma impõe, e o meu robô tem
    algum freio interno calibrado para uma frequência de decisão diferente
    da que ele vai rodar? Ao estourar, o comportamento é recusar a ação ou
    parar o robô — e esse caminho é exercitado pelo modo sombra, ou só
    pelo real? (1.18, 5.16)
43. A ordem em repouso é reancorada por evento (a cada negócio) ou por
    tempo? Se for por evento, qual a cadência mínima entre duas
    reancoragens — e ela foi medida contra a contagem de trades, não só
    contra o limite de taxa? A relação entre essa cadência e o número de
    travadas do freio de segurança é monotônica, ou preciso varrer a grade
    inteira (nunca por gradiente) e escolher pela CONTAGEM de travadas, não
    pelo retorno médio? (4.14, 5.16)
44. Quando a plataforma recusa uma ordem, o meu robô espera antes de
    tentar de novo? Existe contador de recusas por motivo e por pregão,
    com teto? (3.16)
45. Quando eu regenerar uma base histórica, qual é a chave que identifica
    um evento na fonte — e ela sobrevive quando a fonte revisa metadado
    (flags, ids internos, campo derivado)? A minha verificação final lê
    do disco pelo caminho de produção, ou confere as estruturas que
    acabei de montar em memória? (5.13)
46. A plataforma nova permite saber se o histórico que ela devolve está
    completo, ou só dá para inferir pelos extremos (primeiro/último
    registro do dia)? Um argumento de cobertura que olha só os extremos
    não detecta buraco no meio — e uma medição rodada enquanto uma
    regeneração de dado está em curso lê a versão velha do arquivo sem
    nenhum sintoma; confira sempre o mtime do artefato de medição contra o
    horário exato da troca do arquivo fonte. Mesmo depois de corrigida, uma
    remedição que devolve o MESMO valor não dispensa checar quais casos
    individuais mudaram de lado — coincidência de número não é reprodução
    de medição. (5.15, 5.16)
47. Meu BACKTEST expõe, como coluna de saída, quantos pregões de uma janela
    ficaram sem nenhum trade e por qual motivo a última tentativa de entrada
    foi recusada — ou só o líquido agregado? As perguntas 20 (3.11, varrer o
    piso de sobrevivência contra o parâmetro) e 23 (3.15, a plataforma AO
    VIVO recusar total ou parcial no preenchimento) já cobrem a lacuna do
    lado do capital e da execução real; esta acrescenta que o próprio
    BACKTEST precisa expor a contagem de pregões sem trade e o motivo da
    recusa, senão uma janela OOS censurada perto do piso de capital é lida
    como degradação de edge, e ninguém percebe que IS e OOS deixaram de ser
    comparáveis — viraram duas amostras de um mesmo sorteio, não duas
    medidas de generalização. (6.15)
48. Quais campos do estado de conta que a plataforma expõe derivam do
    SALDO (e portanto herdam qualquer dessincronização entre ela e a
    corretora) e quais saem das posições/margem reais? A corretora garante
    que o saldo exibido na plataforma é o saldo de verdade? Um freio de
    segurança ou portão de margem alimentado por um campo do primeiro
    grupo não é conservador — é um modo de falha novo, que trava a
    operação em silêncio mesmo com o caixa do dono positivo. As perguntas
    15 (3.3, margem exigida x margem livre) e 16 (3.13, trava entre
    processos) já assumem que o número consultado é confiável; esta
    pergunta vem ANTES das duas — descobre se ele é. (1.19)
49. **RESPONDIDA no MetaTrader5** — o histórico expõe o TEMPO DE VIDA da
    posição (abertura → fechamento, em milissegundos), ou só deals soltos com
    carimbo de tempo? No MT5, `history_deals_get` devolve `time_msc` em
    milissegundos e o `position_id` amarra entrada e saída, então a vida da
    posição é a diferença entre o primeiro deal de entrada e o último de
    saída. Sem essa medida não dá para separar um trade de um round-trip de
    execução: 14 das 28 posições reais do robô (50%) viveram menos de 1
    segundo, entraram no diário como trades rotulados "alvo", e num único
    pregão isso distorceu a taxa de acerto em 22,7 pontos percentuais (31,8%
    com os round-trips dentro, 54,5% só com os trades de verdade). A pergunta
    que a medição refinou, e que continua aberta para a plataforma da Copa:
    **quais relógios a plataforma oferece, e qual deles é o da CONTRAPARTE?**
    Um relógio de dado e um relógio do meu próprio laço vão parecer plausíveis
    e medir a coisa errada — 36% e 9% de acerto, respectivamente, no único
    caso em que isso foi medido. (4.16)
50. Existe teto de cadência de envio/cancelamento de ordens — imposto pela
    plataforma e/ou construído por mim — e ele conta o rearme pós-PREENCHIMENTO
    junto com a reprecificação por deriva de preço? Um freio com uma fonte de
    envio isenta deixa o robô no regime rápido exatamente depois de cada
    preenchimento: 125 ordens para 22 trades, 82 de 124 intervalos abaixo de
    meio segundo, com o freio funcionando tick a tick na janela calma do mesmo
    pregão. A conferência é a DISTRIBUIÇÃO dos intervalos reais num pregão
    inteiro, nunca o valor do parâmetro. (1.20, 1.18, 4.14)
51. Dá para consultar o topo de livro no instante do envio, para recusar uma
    ordem-limite marketable (compra acima da melhor oferta, venda abaixo do
    melhor lance) antes que a plataforma a execute a mercado sem avisar? E o
    registro do preenchimento diz se a minha ordem foi AGRESSORA ou PASSIVA?
    Sem a primeira resposta, uma âncora defasada converte a estratégia maker
    em taker na entrada; sem a segunda, a taxa de preenchimento passivo real
    (pergunta 40) não é medível. (4.17, 4.13)
52. O meu backtest expõe, POR CÉLULA de uma varredura de parâmetro de
    geometria (alvo, stop, tamanho) — não só por janela IS/OOS —, quantos
    pregões ficaram sem trade e o caixa mínimo atingido, ou só o líquido
    agregado da célula? Sem essa contagem por célula, alargar um alvo
    mantendo o stop fixo pode atravessar um penhasco onde o caixa cai abaixo
    do piso de reabertura cedo na janela — trades caindo de milhares para
    dezenas, líquido negativo — e isso se lê como "geometria pior" quando é
    censura por capital, confirmada em duas janelas independentes (IS e
    OOS) na mesma varredura. O `pior_janela_60s` de cadência (pergunta 42)
    sofre o mesmo viés: um número baixo pode ser a geometria censurada não
    acumulando rajada, não uma geometria mais segura. (6.16, generaliza
    6.15/pergunta 47)
53. O meu backtest reporta o win% observado e o breakeven teórico (derivado
    de alvo/stop: `stop/(profit+stop)`) lado a lado, para qualquer geometria
    testada, ANTES de eu decidir se um travamento por capital merece mais
    caixa ou se é edge negativo disfarçado? Uma escada de capital de R$375 a
    R$5.000 rodou inteira atrás de undercapitalização que não existia: o
    líquido piorou monotonicamente em vez de estabilizar, e o win% medido já
    estava abaixo do breakeven antes da escada começar — a linha que
    resolveria a pergunta em uma conta só apareceu depois de gastar a escada
    inteira. (6.17, decorre de 6.16/pergunta 52)
54. Cancelar e reenviar uma ordem-limite faz perder a posição na fila do
    book? Existe modificação de preço IN-PLACE que preserve prioridade? E
    qual é o teto de ordens por minuto da plataforma — medido em que
    relógio? Reposicionar uma ordem sem histerese de DOIS pontos (contra o
    nível PARADO e contra o último nível ABANDONADO na mesma rodada) faz o
    robô voltar a um nível que ele mesmo acabou de abandonar: 65 de 103
    substituições moveram 1 tick, 49 devolveram a ordem a um nível já
    ocupado na mesma rodada, e cada uma foi um cancela-e-reenvia real que
    jogou fora a fila já conquistada — a pergunta 42 (freio de CADÊNCIA,
    1.20/1.18) e esta são portões ortogonais: uma limita QUANTAS
    substituições saem, a outra PARA ONDE elas vão. (4.19, 1.20)
55. A API de dado da plataforma distingue **"não há negócio novo"** de **"não
    consegui ler o histórico"**? Em MT5 a resposta é **SIM**, mas por um canal
    LATERAL fácil de ignorar: `copy_ticks_range` devolve `None` com
    `last_error() == (-4, 'Terminal: Not found')` quando falha, e array vazio com
    `last_error() == (1, 'Success')` quando o papel só está parado — a distinção
    existia e o código a jogava fora nos dois casos no mesmo `return`. Confira se
    a plataforma nova tem equivalente, e **qual é o valor dele quando a leitura
    foi legitimamente vazia**: sem essa segunda metade o portão vira alarme em
    todo passo de papel parado, o dono para de ler o diário, e o próximo sintoma
    passa despercebido (6.15). Se não distingue, qual é o sintoma observável
    de um feed cego e em quanto tempo ele aparece? E existe alguma garantia de
    que o histórico de tick/barra que ela devolve está sincronizado com o
    stream de cotação em tempo real, ou os dois podem divergir por dezenas de
    minutos sem erro? Aqui divergiram por 44,8 minutos com o mercado
    negociando 1.000 a 2.900 ticks por 5 minutos, sem nenhuma exceção e sem
    perda de conexão — e o robô mandou 45 ordens reais contra preços de até
    45 minutos atrás. A pergunta 38 (5.11) cobre a consulta que devolve MENOS
    do que a janela pedida; esta cobre a que devolve ZERO e chama isso de
    normal. (5.17, 5.3)
56. Qual é o atraso **ESTRUTURAL** de cada granularidade de dado da plataforma
    — o equivalente a "barra M1 só existe depois que o minuto acaba, e seu
    carimbo é a abertura do minuto"? É esse número que entra no teto de idade
    de barra: o teto é *tolerância medida + atraso nominal do feed*, declarado
    pelo próprio feed, nunca uma constante única. Sem ele, o portão que impede
    barra velha de virar ordem ou é frouxo demais para servir ou recusa o feed
    saudável por construção. E o meu robô tem um relógio de idade do DADO
    separado do relógio de idade do PROCESSO? O segundo rodou de 5 em 5
    segundos durante a cegueira inteira e por isso o freio de 15 minutos não
    viu nada. (5.17)
57. O histórico que a plataforma serve é renovado por **EVENTO** ou por
    **RELÓGIO**? Se por relógio, com que cadência? No MT5, 4 de 4 travamentos de
    08/09 liberaram **dentro de 5 s do topo da hora** (14:00:04, 15:00:01,
    16:00:04 e 20:00:01), enquanto os INÍCIOS não têm padrão nenhum (13:51,
    14:14, 15:39, 19:44) — o que aponta para um instantâneo de histórico
    renovado na hora cheia, servido em paralelo a um stream de cotação que
    continua vivo. Causa raiz ainda NÃO provada. A sonda que responde: por cima
    de uma virada de hora, no mesmo passo, pedir a janela LARGA que o feed usa e
    uma ESTREITA de 60 s, e comparar o timestamp do último tick das duas.
    (5.17, 5.11)
58. Qual é o limite REAL de requisições por unidade de tempo que esta
    corretora/plataforma impõe (envio, cancelamento e alteração contam
    igual?), e o que ela devolve ao estourar — recusa da requisição,
    desconexão, ou bloqueio da conta? As perguntas 42 e 50 já cobrem o
    freio que o PRÓPRIO robô constrói; esta vem ANTES das duas — sem o
    limite real da corretora, os dois níveis de teto deste projeto (vazão e
    patologia) são calibrados pela cadência do ROBÔ, nunca pelo limite
    verdadeiro, porque a Rico/Clear nunca documentou esse número. Um teto
    único de execução é sempre errado nos dois sentidos: baixo demais mata
    pregão legítimo (42 envios/min medidos como cadência normal, contra um
    teto antigo de 30), alto demais deixa laço passar batido — por isso o
    disjuntor de patologia tem de contar TENTATIVAS, não envios executados,
    senão o próprio teto operacional o mantém sempre abaixo do gatilho.
    (1.22)
59. Qual é a LISTA dos custos de execução que o simulador desta plataforma
    cobra — e, para cada item da lista, o número saiu de uma MEDIÇÃO no
    extrato ou de uma suposição? Tudo que não estiver na lista é um subsídio
    silencioso, e uma varredura de parâmetros vai encontrá-lo e explorá-lo
    sozinha: aqui o motor entregava a saída por alvo EXATAMENTE no nível
    pedido, e por isso a varredura de 250 células escolheu o menor alvo
    possível — que é onde o tick regalado é a maior fração do bruto. Antes de
    aceitar qualquer vencedor de varredura, pergunte **onde este simulador é
    mais otimista que a realidade** e confira se o vencedor não mora
    exatamente ali. O sintoma é um ótimo colado na borda de um parâmetro cujo
    custo dominante o modelo não cobra. (6.18, 4.8)
60. Quando um custo novo é adicionado ao simulador e a janela passa a ficar
    CENSURADA por capital (6.15/6.16), esse custo muda **quais** trades
    acontecem ou só o **preço** deles? Se muda só o preço — como um deslize
    de saída, que não move o gatilho —, o win% medido na linha não-censurada
    continua válido, e o veredito sai do par (win% observado × breakeven
    RECALCULADO com o custo novo), sem depender de nenhum líquido. Sem essa
    distinção, uma correção de modelo que censura a janela vira "não dá pra
    concluir nada" quando na verdade ela permite concluir tudo. (6.18,
    6.15, 6.17)
61. Como a plataforma resolve uma ordem de fechamento que chega enquanto já
    existe stop/alvo REGISTRADO para a MESMA posição — recusa a segunda,
    cancela a proteção sozinha, ou executa as duas? E se as duas executarem,
    o excedente vira ZERO ou vira posição no lado CONTRÁRIO? A pergunta 3
    (1.4) cobre uma ordem única maior que a posição; esta cobre duas ordens
    do tamanho certo chegando pelo mesmo motivo — o caso que aparece quando
    a posição é montada ou desmontada em FATIAS e cada caminho de saída acha
    que é o único. Enquanto a resposta não existir, a regra é uma só: com
    proteção registrada na corretora, o robô espera esse nível e não manda
    ordem própria pelo mesmo fechamento. (1.23, 1.4)
62. Quantas saídas por proteção NATIVA (alvo/stop amarrados no request da
    entrada) eu preciso acumular nesta plataforma antes de o intervalo de
    confiança do deslize ficar mais estreito que a distância até o **deslize
    crítico** da minha geometria — o valor de deslize em que a expectativa
    por trade cruza zero? E a plataforma me dá o par (nível PEDIDO, preço
    EXECUTADO) por saída, ou só o preço executado? A segunda metade decide se
    a amostra chega a existir: aqui o banco do próprio robô
    (`db/live.sqlite`) gravava `limit_price == avg_price` na saída — o nível
    pedido sumia —, e os n=11 só existiram porque o histórico de ORDENS do
    terminal ainda guardava o `tp` do request de entrada. Com o crítico em
    0,905 tick e o IC de n=11 em [0,700 ; 1,300], são ~40 a 50 saídas para
    tirar o crítico de dentro do intervalo. (6.18, 4.8)

63. A ordem-limite desta plataforma, quando fica de fato parada no livro,
    preenche no nível PEDIDO ou melhor — e isso foi medido SEPARADAMENTE do
    alvo/stop nativo, na mesma população? As duas coisas costumam ser
    chamadas de "minha ordem" e são mecanismos diferentes: aqui a ENTRADA
    (limite de verdade no livro) deu 0 de 28 contra a posição, enquanto a
    SAÍDA por alvo nativo (gatilho varrido a mercado) deu 10 de 11 contra —
    a mesma conta, o mesmo dia, o mesmo robô. Medir os dois juntos teria
    dado uma média sem sentido e escondido qual dos dois lados custa. E ao
    escrever o resultado: 0 em N estabelece DIREÇÃO, não ausência — anote o
    limite superior junto do zero (regra de três: 3/N). (4.20)

64. A corretora executa o take-profit REGISTRADO como ordem-limite *resting*
    no livro, ou como GATILHO varrido a mercado? Se for gatilho, todo alvo
    curto está pagando deslize invisível, e a fração que ele come é
    (deslize / alvo) — num alvo de 2 ticks, 1 tick é metade do bruto. Esta
    pergunta vem antes da 62 (quantas saídas acumular para estreitar o IC do
    deslize): se a resposta for "gatilho", a medição pode ser desnecessária,
    porque o custo pode ser eliminado em vez de estimado. (6.19, 4.8)
65. Dá para posicionar a saída de LUCRO como ordem-limite real parada no
    livro — e a plataforma aceita cancelar/reposicionar essa ordem a cada
    barra, na cadência que o robô precisa? As perguntas 42, 50 e 54 (teto de
    cadência e perda de posição na fila ao reenviar) definem se essa saída é
    operável na prática; sem elas a resposta "sim, dá" é teórica. (6.19, 4.2)
66. Com uma ordem-limite de saída em pé, a plataforma ainda permite manter o
    STOP registrado na corretora ao mesmo tempo, sem risco de dupla
    execução? Em conta NETTING, dois fechamentos do tamanho total não zeram:
    INVERTEM o lado. Enquanto a resposta não existir, trocar o alvo nativo
    por limite no livro significa que o alvo deixa de ter proteção do lado da
    corretora e passa a depender do processo do robô estar vivo — é troca de
    custo de execução por dependência de disponibilidade, e ela precisa ser
    declarada, não descoberta. (6.19, 1.23, 1.4)
67. Os prazos e contadores desta plataforma — validade de ordem, prazo de
    uma fatia de saída, janela de indicador, teto "por barra" — são medidos em
    TEMPO DE RELÓGIO, em BARRAS DE TEMPO FIXO, ou em EVENTOS/negócios? O mesmo
    campo pode mudar de unidade conforme a granularidade do feed que o robô
    consome, e nome de campo não carrega unidade: aqui `exit_ttl_bars=8`
    significa 8 minutos num robô de barra M1 e ~0,5 segundo (8 negócios,
    mediana de 62 ms entre eles) num robô de tick — quase 1000x, com o mesmo
    nome, o mesmo tipo e o mesmo campo de destino. Antes de copiar qualquer
    prazo entre robôs, converta os dois para tempo de relógio MEDIDO no feed de
    destino e compare os números, nunca os literais. (6.20)

68. Quando esta plataforma devolve **sucesso** num envio de ordem sem os
    campos de confirmação preenchidos (preço executado, identificador do
    negócio), o que aconteceu de VERDADE? Existe uma consulta que devolve o
    estado REAL da posição e dos deals daquele request, e o robô a executa
    ANTES de decidir qualquer coisa? "Não confirmou" e "não executou" são
    estados diferentes, e o segundo nunca pode ser inferido do primeiro: aqui
    a inferência custou um short de 2 contratos numa conta de 1 e um trade
    registrado no diário com o sinal e o preço errados. A pergunta 32 (1.17)
    pede a consulta de histórico; esta acrescenta QUANDO ela é obrigatória —
    em toda resposta incompleta, antes da próxima decisão. (1.24, 1.6)
69. Como listo TODAS as ordens vivas deste robô na corretora — e o robô
    reconcilia essa lista contra o que ele acredita ter, a cada passo, ou só
    na inicialização? A pergunta 7 (1.8) pergunta se dá para listar ao
    INICIAR; esta pergunta se a reconciliação acontece no laço, que é onde a
    ordem órfã nasce: uma limite de saída armada 4 segundos antes de a posição
    morrer por outro caminho não aparece em nenhuma reconciliação de abertura
    de sessão. Antes de enviar qualquer ordem nova, o pendurado é cancelado e
    a lista é conferida. (1.24, 1.8)
70. Nesta plataforma, uma ordem-limite de SAÍDA cuja posição já foi fechada
    por outro caminho é cancelada sozinha pela corretora, ou fica viva e vira
    posição NOVA no lado contrário quando preencher? Em conta netting a
    resposta observada foi a segunda, e a assinatura dela é um `price_open`
    fora da grade de preço do instrumento (a média das duas pernas) — vale
    programar essa checagem como alarme, porque ela detecta o estado em uma
    leitura. As perguntas 3 (1.4) e 61 (1.23) cobrem duas ordens que somam no
    fechamento; esta cobre a ordem que sobrevive à posição. (1.24, 1.4)

71. Esta plataforma aceita stop/alvo do LADO ERRADO do mercado (stop de
    compra acima do bid, stop de venda abaixo do ask), ou recusa? E, se
    recusa, ela recusa o pedido INTEIRO — derrubando junto a perna válida — ou
    só a perna inválida? A resposta define se o robô precisa de um caminho de
    degradar o pedido de proteção: quando o pedido é atômico, um alvo mal
    calculado apaga o STOP, e a prioridade tem de ser codificada (reenviar só
    o stop, aceitar ficar sem alvo). Aqui foram ~3 minutos com 2 contratos e
    `SL=0.0 TP=0.0` porque as duas pernas caíram juntas em `retcode=10016`.
    (1.25, 1.2)
72. Existe "distância mínima de stop" nesta plataforma, e quando ela vem
    **0**, o servidor ainda exige que o nível esteja do LADO correto do
    mercado? Zero é ausência de restrição ADICIONAL, nunca permissão para
    violar a restrição estrutural — e um código que lê `distancia_min = 0` e
    pula o afastamento inteiro só falha quando o nível já está do lado errado,
    que é exatamente o momento em que a proteção era necessária. O piso é 1
    tick, sempre. (1.25, 1.11)
73. O histórico de execuções é SÍNCRONO com a resposta da ordem? Se não, qual
    é o atraso típico e qual é o máximo observado? Consulta a histórico
    assíncrono precisa de PRAZO (várias tentativas ao longo de N segundos),
    não de uma pergunta única no instante da resposta — perguntar uma vez e
    não achar nada é indistinguível de não perguntar, e vira "não executou"
    aplicado a uma ordem que executou. A pergunta 32 (1.17) pede a consulta;
    a 68 (1.24) diz QUANDO ela é obrigatória; esta diz que ela precisa de
    JANELA. (1.25, 1.24, 1.17)
74. Dá para marcar uma ordem como **"só reduz posição"** (reduce-only)? Sem
    isso, toda ordem de saída que sobrevive à posição que ela deveria fechar é
    uma ENTRADA nova em conta netting — e, pior, um mesmo preenchimento pode
    ser contabilizado como saída de uma posição e entrada de outra (aqui o
    mesmo `broker_ref` apareceu em duas linhas do banco, como alvo e como
    entrada). Se a plataforma não tiver reduce-only, o cancelamento das órfãs
    antes de qualquer ordem nova deixa de ser boa prática e vira invariante.
    (1.25, 1.24, 1.8)
75. A API deixa consultar quais DEALS foram gerados por UM ticket de ordem
    específico, ou só por posição? Sem o vínculo ticket → deals, a única
    forma de saber se "a minha fatia preencheu" é inferir do ENCOLHIMENTO da
    posição — e encolher não é preencher: em conta netting quem reduziu pode
    ter sido outra ordem, inclusive uma que ABRIU o lado contrário. A
    inferência por encolhimento gravou +R$9,50 num trade que a corretora
    executou por −R$5,00, com o sinal trocado. (1.25, 1.17)

76. Como a plataforma nova identifica cada robô/instrumento no PAINEL, e esse
    identificador passa por alguma camada que proíbe caracteres do símbolo
    (seletor de tela, chave de dicionário, nome de arquivo, nome de objeto
    gráfico)? O símbolo do contínuo (`WDO@`) e o sufixo de ação (`.SA`) cabem
    nele? E a tela mostra o horário da última atualização BEM-SUCEDIDA, ou um
    congelamento é invisível? Aqui o `@` derrubou a troca de conteúdo do cartão
    em 100% dos ciclos com o servidor respondendo HTTP 200, e o `.SA` teria feito
    o mesmo sem nem levantar exceção — o dono só descobriu porque estranhou os
    números parados. (5.18)

77. Ao ENCERRAR um contrato futuro nesta plataforma, o que exatamente volta
    para o saldo disponível — a margem que estava bloqueada, o nocional, ou só
    o resultado da operação? E a plataforma distingue margem de nocional em
    algum campo consultável, ou essa distinção é responsabilidade nossa em
    cada rotina que credita caixa? A resposta define se pode existir mais de
    um lugar no sistema calculando "quanto voltou": aqui existiam três
    (abertura, fechamento normal, remoção do robô) e o terceiro devolveu o
    nocional de um contrato ao caixa, levando R$375,00 a −R$4.706,00. Vale
    perguntar junto: existe uma consulta que devolva a margem BLOQUEADA por
    posição, para o robô nunca precisar recalculá-la de memória? **Estendida
    (2026-09-09):** o preço usado para marcar essa posição a mercado antes de
    encerrar carrega a IDADE junto com o valor — dá para distinguir "última
    cotação conhecida" de "cotação de agora"? Uma rotina de encerramento que
    cai num preço em cache sem carimbo de tempo pode creditar o movimento de
    MERCADO de duas semanas como se fosse desta posição; aqui uma barra de
    12 dias sozinha decidia R$520,00 num caixa de R$375,00, e uma segunda
    dessas barras chegou a ser anterior à própria abertura da posição — uma
    impossibilidade lógica que dispensa até medir "quão velho é demais".
    (5.19, 5.7, 5.24)
78. Quantas rotas de FECHAMENTO esta plataforma oferece — ordem do robô,
    botão de "fechar posição" do terminal, encerramento manual pela mesa,
    liquidação compulsória no fim do dia — e **todas custam o mesmo e chegam
    ao robô do mesmo jeito**? Especificamente: um fechamento que NÃO partiu do
    robô aparece no histórico com corretagem e emolumentos discriminados, ou
    só como um deal sem custo? A resposta define se dá para ter um único ponto
    de contabilização no nosso lado, ou se cada rota precisa de tradução
    própria — e rota com tradução própria é o lugar onde a conta diverge. Aqui
    a rota administrativa (remover o robô pelo painel) creditava o resultado
    BRUTO enquanto a operacional creditava o LÍQUIDO: **R$0,50 por contrato de
    WDO@, R$0,01 em 100 ações**, sempre a favor de quem removeu. O tamanho não
    é o ponto — o caixa é o que dimensiona a próxima posição, então erro
    pequeno e sistemático entra numa malha fechada e integra. A pergunta 77
    (5.19) cobre o CRÉDITO devolvido ao saldo; esta cobre o CUSTO cobrado na
    saída. (5.20, 5.19)
79. O que exatamente a API devolve para um instrumento que existe mas ainda
    não está "carregado"/selecionado no terminal — zero, `None`, um erro
    explícito, ou o valor do último símbolo consultado? Dá para distinguir,
    na resposta, "este instrumento vale zero" de "eu não sei o valor deste
    instrumento"? Se não der, todo número lido de lá que alimenta P&L, portão
    de capital ou disjuntor precisa de um guard de sanidade — finito e maior
    que zero, validado por VALOR e não por tipo — ANTES da primeira divisão
    ou uso. Aqui o terminal reportava `trade_tick_value=0` para símbolo fora
    do Market Watch, e o zero silenciava as três proteções ao mesmo tempo sem
    levantar exceção nenhuma em ação, e explodia um `ZeroDivisionError` sem
    contexto em futuro. (5.21, 5.22)

80. Esta plataforma informa **o instante em que a minha ordem-limite entrou no
    livro** e **o instante em que ela preencheu ou foi cancelada**, com
    resolução suficiente para eu somar o volume negociado NAQUELE PREÇO entre
    os dois? Sem esse par de carimbos, a fila não é calibrável a partir do
    extrato, e todo backtest maker fica sem aferição possível — o número dele
    passa a ser hipótese, não previsão. Três exigências que só aparecem na hora
    de medir: (a) o carimbo tem de existir também para a ordem que **NÃO**
    preencheu (foi cancelada/expirou), senão a amostra vira só de vencedoras e
    a fila sai subestimada por viés de sobrevivência — 346 contra os 438 do
    Kaplan-Meier na entrada, 374 contra 489 na saída; (b) a série de negócios
    tem de dar preço e volume no mesmo relógio dos carimbos da ordem, senão não
    dá para recortar a janela; (c) a ordem que preenche em menos de ~0,5 s tem
    de ser identificável e descartada — ela já estava agressiva ao postar e
    nunca entrou em fila (4.17); e **(d)** a amostra tem de declarar o REGIME em
    que foi colhida, porque um prazo curto de cancelamento censura a própria
    medição (17 das 25 saídas de 2026-09-09 foram canceladas antes de revelarem
    a fila) — observações COM prazo e SEM prazo não entram na mesma curva de
    sobrevivência. A pergunta 24 pergunta se o SIMULADOR modela
    fila; a 51 pergunta se o preenchimento diz se fui agressor ou passivo; esta
    pergunta se o extrato permite ESTIMAR o número que alimenta o simulador.
    (4.22, 4.1, 4.21)

81. Dá para rodar uma janela de backtest com o caixa **REPOSTO ao valor
    inicial a cada sessão** (pregões isolados), além da corrida contínua? Sem
    isso, toda janela com capital no piso mistura duas coisas que pedem
    decisões opostas — **ruína por capital** (pede mais caixa) e **expectativa
    negativa por operação** (pede abandonar a estratégia) — e as duas produzem
    exatamente a mesma curva descendente. Exigências mínimas para a resposta
    servir: (a) a saída tem de trazer **R$ por operação** e **quantos pregões
    foram positivos**, não só o líquido agregado da janela; (b) o win% observado
    e o breakeven aritmético da geometria, lado a lado, com intervalo de
    confiança (pergunta 53). Sem o caixa reposto, gasta-se uma escada de
    capital inteira (6.17) perseguindo subcapitalização que não existe.
    (6.21, decorre de 6.15/6.16/6.17)

82. O dimensionamento por **percentual de risco** desta plataforma tem PISO
    implícito — isto é, quando `caixa × pct ÷ risco_unitário` trunca para zero,
    ele **recusa operar**, **avisa** qual risco efetivo está sendo assumido, ou
    silenciosamente devolve o tamanho mínimo? A terceira resposta é a comum, e
    é a que transforma um limite de 1% em 9% a 30% por operação sem nenhum
    evento no caminho. Corolário a exigir do próprio robô, independente da
    plataforma: o tamanho efetivamente enviado carrega, no diário, o risco em
    % que ele representa — o parâmetro pedido não é evidência do risco corrido.
    (6.21, 3.8, 3.9, 3.12)

83. A plataforma permite perguntar à corretora QUAIS ordens pendentes existem
    por símbolo+magic, para reconciliar uma ordem de SAÍDA órfã depois de um
    restart (como já se faz com a de entrada)? E o painel de leitura consegue
    reconstruir o estado do robô sem instanciar a camada que manda ordem? Sem
    a primeira resposta, um portão de segurança pós-restart não tem caminho de
    saída no mesmo pregão; sem a segunda, uma exceção de segurança pensada
    para quem vai OPERAR pode derrubar a tela de quem só quer OLHAR — no pior
    momento possível, que é justamente quando há dinheiro exposto e o robô
    está fora do ar. (2.7)

84. Um parâmetro de fidelidade de execução (ancoragem de saída no preço do
    fill, fila, deslize) é consultado em TODOS os caminhos de ordem que este
    robô usa nesta plataforma — a mercado e a limite —, ou existe caminho que
    ignora o parâmetro em silêncio, sem erro e sem aviso? Ligar a flag e ver
    o número mudar não prova cobertura: prove rodando o MESMO teste nos dois
    caminhos e conferindo que os dois reagem. Foi assim que se descobriu que
    `anchor_exits_at_fill` nunca era lido no caminho de entrada a mercado —
    16 células saíram byte a byte idênticas com a flag ligada e desligada.
    (4.23, 3.8, 4.22)

85. Quais tipos de ordem desta plataforma nova têm caminho de execução
    CONFIRMADO — não documentado, confirmado contra extrato real — e o
    simulador dela recusa ou pelo menos MARCA a linha de resultado que usa um
    tipo sem esse caminho? Aqui uma rodada inteira de pesquisa (cinco setups,
    ~50 células) foi medida com entrada a mercado e alvo a mercado, dois
    desenhos que o motor de produção recusa de propósito
    (`EntradaAMercadoNaoSuportada`) — dinheiro de máquina inteiro gasto
    respondendo a uma pergunta que a corretora nunca deixaria virar pergunta
    real. Congelar o desenho de execução (que tipo de ordem entra, que tipo de
    ordem sai) ANTES de varrer parâmetro de estratégia evita a mesma perda de
    tempo em qualquer plataforma nova. (4.24, 4.8, 6.18, 6.19)

86. O relatório de backtest desta plataforma traz **ganho médio** e **perda
    média** (ou o breakeven empírico derivado deles) na MESMA linha em que
    traz o win%, por célula — ou o win% sai sozinho e a razão precisa ser
    reconstruída à mão depois? Se sair sozinho, o número é inutilizável como
    veredito e tem de ser tratado como intermediário. Exigência adicional
    quando a estratégia usa um FILTRO de entrada: dá para comparar a
    distribuição de magnitude dos movimentos **com** e **sem** o filtro? É a
    única forma de detectar que a condição escolhida seleciona tamanho junto
    com direção — e quando ela seleciona, acerto e breakeven sobem juntos e a
    melhora aparente é contábil (acerto +0,30pp contra breakeven +1,06pp:
    acertar mais piorou a célula). (6.27, 6.23, 6.22, pergunta 53)

87. Dá para extrair, por operação, a **excursão adversa máxima** (o pior ponto
    contra a posição enquanto ela esteve aberta) e o **custo total cobrado**,
    em colunas separadas do resultado? Sem as duas, não é possível separar as
    duas causas de ruína, que pedem decisões opostas: **cauda** (um evento
    individual estoura a folga da conta — pede mais caixa ou stop mais curto)
    e **acumulação** (o pedágio somado drena o caixa — pede menos operações ou
    menos custo por operação). Aqui só 0,007% dos eventos estouravam a folga,
    enquanto 47% da perda total era corretagem pura: a intuição apontou para a
    cauda e quem matava era a acumulação. (6.27, 6.17, 4.5)

88. Antes de aceitar "este sinal não dá para monetizar por causa da fila" como
    veredito final, quantos mecanismos de execução DIFERENTES do "ordem nova
    no instante do sinal" foram testados — e cada um mediu se o volume
    disponível no intervalo relevante de fato muda com a variação, ou só
    testou timing diferente sobre a mesma fila? Esta plataforma permite
    calcular, por sinal candidato, o volume acumulado desde ANTES do instante
    de confirmação (para testar entrada preexistente) e o volume necessário
    para variações do alvo (para testar entrada mais longe)? Aqui um efeito
    de reversão com n de dezenas de milhares resistiu a três mecanismos
    alternativos — mirar mais longe, repousar desde o primeiro toque do
    nível, sair de uma posição já aberta — e só o terceiro tinha chance real,
    mas era exatamente o desenho de saída que já estava em produção, não uma
    entrada nova. Um efeito estatisticamente enorme e uma fila estruturalmente
    maior que o volume disponível não se resolvem testando mais variações de
    TIMING sobre o mesmo mecanismo reativo. (6.28, 6.21, 4.22)

89. Quando uma ordem parada minha **expira por prazo**, a plataforma AVISA o
    robô ou só registra no log? E quando ela é **recusada**? Se os dois
    eventos não notificam igual, o robô tem de contar o prazo sozinho — e a
    lista completa a percorrer não são dois eventos, são cinco: recusa, prazo,
    cancelamento que eu pedi, cancelamento que a corretora fez, e achatamento
    de fim de pregão. Cada um que não tiver caminho de volta deixa ligado para
    sempre o estado "já mandei minha ordem", e o sintoma é SILÊNCIO, não erro:
    aqui foram 14 de 72 pregões (19,4%) sem nenhuma operação, +R$413,00 (+33%)
    de líquido esperando do outro lado, e nenhum alerta em lugar nenhum.
    (4.25, 1.14, 3.8)

90. Esta plataforma deixa **ALTERAR o preço de uma ordem-limite que já está no
    livro**, ou só cancelar e mandar outra? E quando ela deixa alterar, a ordem
    **mantém a posição na fila** daquele nível ou vai para o FIM? As duas
    respostas mudam código e mudam backtest: se só existe cancelar-e-remandar,
    o robô fica exposto no intervalo entre as duas ordens e precisa tratar
    cancelamento não confirmado (1.24, 1.23); e se a ordem nova entra no fim da
    fila, o simulador tem de cobrar a fila CHEIA do nível a cada
    reprecificação, senão mede um robô mais rápido do que a corretora executa.
    Aqui o motor mudava o alvo no estado interno e a ordem real continuava
    parada no preço velho para sempre, enquanto a fatia simulada herdava a fila
    já consumida — otimista ao vivo e otimista no papel, no mesmo ponto do
    código. A pergunta 54 cobre perder a fila ao cancelar-e-reenviar; esta
    cobre o caso em que é o próprio robô que decide mudar o nível de uma
    ordem JÁ ENVIADA. (4.26, 4.21, 4.22, 1.24)

91. Esta plataforma recusa o REGISTRO de uma ordem quando o STOP declarado
    excede o caixa disponível, ou só valida a margem exigida para ABRIR a
    posição? Margem e perda máxima do stop são números independentes — um
    robô com stop que varia por volatilidade (não fixo em ticks/pontos) pode
    passar em todo portão de margem e ainda assim ir a equity negativa no
    primeiro stop caro. Se a resposta for só a segunda, o teto por perda
    máxima do stop tem de ser construído por fora, comparando a distribuição
    do stop em dinheiro (p95 e máximo, nunca só a média) contra o caixa antes
    de operar capital real. (3.17)

92. Ao ler um veredito de fila (robô maker enche ou não enche) medido num
    instrumento, esta plataforma me deixa medir, para o instrumento NOVO, os
    três números que decidem se o veredito transfere: o giro médio (volume
    por unidade de tempo) NO NÍVEL da minha ordem, o tamanho da minha ordem
    relativo a esse giro, e o tempo esperado de espera até o preço voltar ao
    nível? Sem os três, "fila mata este robô" vira "fila mata todo robô
    maker" por generalização indevida — e a generalização pode ir para os
    dois lados: matar por engano uma configuração saudável (aqui, o WIN@) ou
    salvar por engano uma que a fila real mataria. Testar a sensibilidade com
    um valor absurdo de fila (ordens de grandeza acima do plausível) antes de
    aceitar "não morde" como resultado — sem esse teste de sanidade, "não
    morde" e "o modelo de fila está desligado" são indistinguíveis. (6.30,
    4.20, 4.21, 4.22, 6.21)

93. Esta plataforma (ou o simulador que a representa) cobra algum deslize
    fixo na execução de um STOP que foi MOVIDO por trailing/breakeven, e
    qual é o tamanho dele em ticks? Antes de aceitar qualquer geometria de
    trailing ou breakeven-stop, compare a distância entre o nível travado e
    o preço de entrada contra esse deslize — não contra zero. Uma trava
    menor ou igual ao deslize é economicamente idêntica a não ter trava
    nenhuma: o deslize consome o tick reservado antes de virar lucro, e o
    resultado colapsa para "só a corretagem", mesmo quando o código moveu o
    stop exatamente como pedido. (4.27, 4.8)

94. Esta plataforma permite dar **prazo à ordem-limite de ENTRADA**, e o prazo
    é contado em QUÊ — tempo de relógio, barras, ou negócios? Sem prazo, a
    ordem espera até o fim do pregão e preenche horas depois do sinal (medido:
    **269,7 minutos** entre o rompimento e o fill, e os fills atrasados foram
    os piores resultados). Com prazo, a unidade decide o resto: "15" pode ser
    15 minutos, 15 segundos ou 45 milissegundos conforme o feed, então o
    número tem de ser convertido para tempo de relógio MEDIDO no feed de
    destino antes de qualquer comparação (pergunta 67). E a pergunta que vem
    junto, que é a que custou aqui: **para CADA estratégia que manda ordem-limite
    de entrada, esse prazo já foi medido, ou é o default do construtor?** No
    `copa_win` era o default (`entrada_ttl_barras=15`, nunca comparado com
    nada); baixá-lo para 5 valeu mais que uma grade de 152 células de
    geometria. (6.33, 6.20, 4.24)

95. Depois que a fila real do livro (medida por Kaplan-Meier ou equivalente,
    pergunta 80) já mostrar que o bruto por operação fica ABAIXO do custo
    fixo por ordem desta plataforma, ainda vale a pena varrer um parâmetro de
    CADÊNCIA de reenvio/reancoragem de ordem — ou a resposta já está decidida
    pela economia? Varrer 6 valores de cadência (2s a 60s) sobre uma família
    cuja fila real já mostrava expectativa negativa por trade produziu 6
    resultados negativos, com o win% preso numa faixa de 0,53 ponto
    percentual contra um breakeven bem acima — a cadência redistribuiu
    QUANTOS trades aconteciam (trd/dia variou), nunca a economia por trade em
    nenhuma direção mensurável. Compare com a pergunta 94 (prazo de entrada do
    `copa_win`): lá o parâmetro análogo mudava QUAIS SINAIS a estratégia
    chegava a executar, e por isso resgatou uma economia positiva que já
    existia; aqui o parâmetro só reordena o reenvio de uma ordem que já
    reancora a cada barra, sem tocar a fila que matou o edge da família.
    Antes de varrer, confirme se a economia por trade já está
    estruturalmente decidida por um motivo independente do parâmetro em
    questão — só a resposta "não" justifica a varredura. (6.34, 6.33, 6.21)

96. Ao portar uma estratégia com portão de capital mínimo, qual é a
    probabilidade de o capital mínimo oficial travar o robô numa sequência
    de perdas COMUM (não rara) — medida embaralhando o histórico real de
    operações 10.000 vezes e contando em quantos sorteios o caixa recusa uma
    entrada por falta de margem, não só olhando o líquido agregado? Se essa
    probabilidade for alta (aqui, 52,4%-55,2% em 5 combinações de geometria
    diferentes) e não se mover com a calibração de parâmetro de
    entrada/saída, o problema é de DIMENSIONAMENTO DE CAPITAL, não de
    parâmetro de estratégia — trate como decisão do dono, não como algo a
    "otimizar" testando mais combinações. (6.35, 6.15)

97. Quando a saída é fatiada E a quantidade de posição escala dinamicamente,
    como a plataforma nova conta "um trade" para fins de win%/IC — por
    REGISTRO de preenchimento ou por EVENTO de fechamento de posição? Se for
    por registro, o win% de qualquer variante que escale contratos está
    contaminado do mesmo jeito: cada fatia de um trade vencedor infla a
    contagem, cada stop (fechamento atômico) não. Cruze com a família maker
    do WDO F1 (item 6.21) — ela combinava saída fatiada com realocação
    dinâmica de contratos antes de ser encerrada pela fila real, e pode ter
    reportado win%/IC otimistas demais por este mesmo motivo, ANTES de ter
    sido encerrada pelo motivo da fila. (6.36, 6.21)

98. Quando uma estratégia maker resolve geometria (alvo, espaçamento OU
    stop) abaixo de um piso mínimo de ticks, a plataforma nova RECUSA a
    sessão automaticamente, ou esse gate precisa ser implementado à mão em
    cada estratégia? E existe uma forma de auditar TODAS as estratégias de
    uma vez contra esse piso — rodando o método real de calibração de cada
    uma nos preços correntes, não lendo o parâmetro configurado — em vez de
    descobrir símbolo por símbolo depois que dinheiro real já foi arriscado?
    Aqui **9 de 9** símbolos calibrados de um único robô (`Gremah`)
    resolviam para alvo=1 tick sem que ninguém tivesse rodado essa auditoria
    antes de publicar um veredito POSITIVO; a checagem contra o extrato real
    (84% das ordens canceladas sem nunca serem tocadas, 1 round-trip
    completo em 9 dias) é que forçou a retirada do veredito no mesmo dia.
    (4.6, 4.8, 6.37)
99. Qual é a grandeza que a plataforma nova me dá para estimar fila — volume
    da barra (todos os preços) ou volume ao preço do meu nível? E qual é a
    escala típica dela NESTE instrumento? Varrer fila numa escala emprestada
    de outro contrato produz eixo morto que se parece com robustez: uma
    varredura de 0 a 2.000 contratos no WIN@, usando a escala calibrada do
    WDO@ (438/489), devolveu a MESMA linha nas 36 células porque o volume
    mediano da barra M1 do WIN@ é 24.955 contratos. (6.38)

100. Conectar/autenticar na plataforma nova é operação barata e idempotente,
     ou ela repede autorização ao servidor da corretora a cada chamada? No
     MT5, `initialize(login=..., password=..., server=...)` repete
     autorização todo santo dia — a diferença entre um robô saudável e um
     que declarava cegueira falsa 16 vezes por pregão era só chamá-la uma
     vez por processo em vez de uma vez por leitura. (5.25)
101. Existe uma consulta barata e LOCAL que responda "minha sessão ainda
     está de pé?" sem reautenticar — o equivalente de `terminal_info()`? No
     MT5 essa consulta existe e tem DOIS sinais diferentes empilhados no
     mesmo objeto: liveness do IPC local (não cai com blip do servidor) e o
     handshake com o servidor de negociação (`.connected`) — confundir os
     dois faz reinicializar a sessão exatamente quando reinicializar não
     resolve nada. (5.25)
102. A falha de autenticação é distinguível da falha de leitura de dado, ou
     as duas voltam pelo mesmo código de erro? No MT5 as duas podem chegar
     como o mesmo `last_error()` (-6, "Authorization failed") mesmo quando o
     dado em si estava perfeitamente disponível pela sessão já aberta — sem
     separar as duas, todo blip de autenticação vira alarme de cegueira de
     dado. (5.25)
103. A plataforma expõe a CONTAGEM de ordens recusadas por falta de margem,
     separada das recusadas por outros motivos? Se não expuser, como se
     distingue "o robô não viu sinal" de "o robô viu e foi recusado"? Aqui a
     razão ordens/trades disparou para 177:2 e 92:5 nas semanas em que o
     caixa travou, contra quase 1:1 nas semanas livres — sem essa contagem
     separada, as duas leituras ("sem sinal" e "amordaçado") ficam
     indistinguíveis no líquido. (6.39)
104. A plataforma nova permite carimbar um sub-motivo na saída, ou o motivo
     é um enum fechado da corretora? Se for fechado, onde fica registrado o
     nível PEDIDO no momento do preenchimento, para separar "alvo cheio" de
     "alvo ajustado por corte de tempo/trailing" depois? Aqui as duas
     saíam com o mesmo `exit_reason=target` e tinham R$/op de +229,50 contra
     +28,73 — uma diferença de 8x escondida atrás do mesmo rótulo. (6.40)
105. O corte de um achatamento/saída obrigatória de fim de pregão e o fim da
     janela em que o robô tem permissão para agir vêm do MESMO campo de
     configuração, ou de dois valores independentes? Qual é o RÓTULO da
     última barra que o feed desta plataforma realmente entrega no fim do
     pregão deste instrumento (medido no dado, não no horário nominal do
     regulamento), e a janela de atividade se estende além dele? Aqui os
     dois vinham do mesmo campo (`session_end_time`) e o corte de futuro
     nunca disparou ao vivo — zero eventos FLATTEN no diário inteiro, apesar
     de o backtest atribuir 39,1% das saídas a esse caminho. (4.28)
106. Para cada caminho de saída obrigatório (achatamento, disjuntor, freio
     de perda): existe teste que prove que a condição é ALCANÇÁVEL com os
     relógios e atrasos reais da plataforma nova — e não apenas que ela está
     escrita corretamente? Quantas camadas (motor, runtime,
     agendador/supervisor) precisam concordar para ele disparar, e existe
     um teste que morde a JUNTA entre elas, não só cada uma isolada? Aqui
     foram três camadas concordando por acidente e nenhum teste no par
     entre `profiles.py` e `clock.py` — a suíte inteira ficou verde sobre um
     caminho de saída que nunca disparou. (4.29)
107. A ferramenta de teste estatístico usada nesta plataforma reporta p
     unilateral ou bicaudal por padrão? Se unilateral, a sonda pontua as DUAS
     caudas do mesmo conjunto de permutações (perder de forma sistemática É
     prever, com o sinal trocado), e o número de reamostragens é suficiente
     para que o p mínimo atingível (`1/(N_perm+1)`) fique abaixo do α já
     corrigido pela família DOBRADA que as duas caudas declaram? (6.41)
108. A plataforma rejeita, ou aceita silenciosamente, uma modificação de stop
     para um nível que o preço corrente já ultrapassou? Se aceita, ela
     executa a mercado imediatamente ou deixa a ordem parada até o próximo
     toque? Um ratchet/trailing de um passo só que arma depois do preço já
     ter passado do nível novo se auto-dispara no pior instante possível — e
     o resultado sai do robô com a MESMA aparência de um stop normal, sem se
     denunciar no relatório. (4.30)
109. Como eu detecto, no fim de cada pregão, que uma posição ficou aberta sem
     evento de saída — e a plataforma me deixa reconciliar isso
     automaticamente contra o fechamento (ou contra o extrato do dia
     seguinte), em vez de eu descobrir dias depois lendo o extrato na mão?
     Existe um evento de fim de sessão que eu possa assinar, ou só dá para
     perguntar "o que eu tenho agora"? E a margem alocada por uma posição
     órfã volta sozinha para o caixa quando a posição deixa de existir, ou
     fica presa até alguém reconciliar? Aqui a resposta foi "nenhum dos
     dois": o trade sumiu (−R$238,50 que a sombra nunca contabilizou) e a
     margem ficou presa (R$100,00 por ocorrência). (2.8)
110. A plataforma nova me dá um achatamento de fim de pregão acionado por
     RELÓGIO, garantido mesmo sem cotação nenhuma chegando depois do corte —
     ou o gatilho depende do próximo evento do fluxo de dados? Se depender,
     onde eu ponho o piso por relógio de parede, e ele roda no mesmo
     processo que decide, ou precisa de um vigia externo? Aqui a resposta
     foi "depende do dado": o backtest tem uma rede extra que só o teste
     alimenta (`is_last_bar`), a produção não tem nenhuma, e um pregão que
     encerrou 32 minutos antes do corte (WDO@, 2026-09-15) bastou para
     provar que o desenho não tem piso, sem nenhum processo ter travado. (2.8)
111. Os símbolos contínuos desta plataforma são re-encadeados na rolagem? Se
     sim, com que regra de ajuste, e existe um símbolo por vencimento (não
     ajustado) que sirva de base imutável? Sem essa resposta, unir um fetch
     novo à base histórica por carimbo de tempo pode trocar o encadeamento
     do passado inteiro sem erro nenhum — só compare a divergência nas
     barras comuns antes de gravar. (5.26)
112. Existe, para cada robô com piso de capital publicado, um registro de QUAL
     versão do dimensionamento de posição estava ativa quando o piso foi
     medido — e um processo (checklist de release, teste, ou revisão) que
     force remedir o piso sempre que esse dimensionamento mudar? Sem isso, um
     piso publicado vira órfão em silêncio: aqui um robô ganhou escala
     dinâmica de contrato DEPOIS de o piso ter sido medido com quantidade
     fixa, e o rebaixamento real sob o comportamento novo saiu **quase o
     dobro** do número que o painel ainda mostrava (R$1.979,00 medido contra
     R$989,50 publicado, mesma janela, mesmo capital de partida). Um piso é
     uma alegação sobre uma VERSÃO do robô, não sobre o robô para sempre.
     (6.43, 3.8, 4.22)
113. Cada gate de capital/margem/caixa mínimo desta plataforma foi auditado
     com a pergunta "isto protege dinheiro real, ou só bloqueia um teste?"
     Se a plataforma tiver um modo sombra/paper equivalente, o mesmo gate
     não pode ser aplicado a ele sem essa ressalva. Aqui dois gates
     independentes (o diário em `_check_capital` e o piso de entrada em
     `live_control.start()`) recusavam pregão/subida de um robô em SOMBRA
     por falta de caixa — sem nunca proteger dinheiro nenhum, porque sombra
     nunca manda ordem para a corretora. (3.18)
114. A cadência de reancoragem da minha estratégia — com que frequência ela
     cancela e rearma um nível quando o preço não veio — foi medida contra o
     TEMPO DE DRENAGEM da fila deste nível nesta plataforma, ou só contra o
     preenchimento agregado do dia inteiro? A pergunta 90 cobre se a
     plataforma preserva a posição na fila ao alterar o preço; esta cobre a
     consequência de reancorar RÁPIDO DEMAIS mesmo quando a resposta à 90 é
     "perde a fila sempre": aqui a mesma estratégia, no mesmo símbolo e no
     mesmo pregão, armou 1.012 níveis novos e preencheu ZERO, contra 101
     armados e 64 preenchidos de uma irmã mais lenta — a cadência, não o
     mercado, decidiu a taxa de preenchimento, e "0 trades" sozinho não
     distingue essa causa de ausência de sinal. (4.32, 90)
115. Ao portar uma busca/otimização automática (evolutiva, grid ou outra) para
     a plataforma nova, o arreio de TREINO entrega o mesmo estado semeado
     (escala/volatilidade/histórico de sessões anteriores) que o motor de
     referência entrega? Existe um teste que meça a variância de cada
     feature/indicador DENTRO do arreio real e falhe se alguma ficar
     constante? Aqui o arreio de treino avaliava um robô novo por pregão,
     zerando o estado semeado, e 11 de 33 features viraram zero constante em
     toda a busca sem que nada acusasse — 12h de CPU perdidas. (6.45)
116. Quando a camada que ENVIA a ordem para a plataforma (não o motor de
     simulação) decide recusar o envio — dado velho, cota de cadência
     estourada, qualquer defesa nova adicionada depois do motor — essa
     recusa chega de volta até quem decidiu o sinal, ou só limpa a ordem
     vigiada por dentro? Aqui a defesa que o item 4.25 corrigiu cobria só o
     caminho do MOTOR; a camada de envio (`live/`) ganhou o mesmo poder de
     matar ordem meses depois e herdou o mesmo bug — 3 dos 7 pregões desde
     11/09 tiveram o robô mudo pelo resto do dia, 2 deles com ZERO entradas,
     achando que tinha ordem no livro. Regra de auditoria: toda vez que uma
     camada nova ganha poder de recusar/cancelar, confira se ela também
     ganhou o dever de notificar — não assuma que a correção anterior cobre
     o caminho novo. (4.33, 4.25, 7.1)
117. A detecção automática de qual contrato/símbolo negociar foi exercitada
     com o MERCADO FECHADO, ou só depois da abertura? Um mapa de símbolo
     VAZIO (nenhuma entrada) para um robô de futuro é tratado como "nada a
     mapear" em algum ponto do código de subida (`if mapa:` é falso para
     `{}` igual para `None`), ou como estado inválido que impede a primeira
     ordem? Existe uma consulta que confirme, antes do primeiro envio real
     do pregão, que o símbolo de destino aceita ordem (equivalente a
     `trade_mode` habilitado) e tem book de dois lados? Aqui subir o robô 6
     minutos antes da abertura fez a detecção degradar para "ticker mapeado
     para ele mesmo", o filtro de mapa trivial removeu a única entrada, e o
     robô operou o pregão inteiro contra um símbolo que a corretora recusa
     — zero ordens enviadas, defeito invisível em sombra. (5.27, 5.4, 1.24)
118. Na plataforma nova, como se distingue "o papel não negociou" de "a
     plataforma parou de me entregar dado"? A API devolve alguma coisa
     diferente nos dois casos, ou as duas situações chegam como lista
     vazia — e, se chegam iguais, qual é o ritmo NORMAL de negócio de cada
     instrumento, para o limite de alarme não ser arbitrário? Aqui o feed
     do `WDO@` cegou 36 minutos devolvendo lista vazia "com sucesso", e o
     vigia que só olhava erro de leitura não tinha como acusar — só um
     limite calibrado contra o ritmo do instrumento (5 min em futuro
     líquido, 30 min em ação ilíquida) distingue as duas situações. (5.28,
     5.17)
119. Na plataforma nova, o que acontece com o estado interno da estratégia
     quando o processo reinicia no meio da sessão? Existe como reprocessar
     a sessão desde a abertura, quanto custa fazer isso, e o robô
     reconstruído fica idêntico ao que nunca caiu? Aqui um default herdado
     por acidente ("robô sem âncora fixa nunca faz warm start", valor de
     queda de uma política escrita só para OUTRO robô) fazia todo robô sem
     esse conceito começar a frio no meio do pregão — um robô cuja
     geometria sai da faixa de abertura virava, ao reiniciar às 11:19,
     outra estratégia (faixa 11:19..11:34 em vez de 09:00..09:15). O
     conserto reconstrói o estado desde a abertura em ~7 a ~14s de replay,
     uma vez por processo — contra um piso de watchdog de 900s. (5.29,
     3.14, 5.9)
120. A plataforma nova oferece uma série contínua/ajustada de longo prazo
     (anos) pro instrumento? E como se confirma que um contrato específico
     usado numa janela curta de validação (IS/OOS de 1-2 meses) tinha
     volume/liquidez real — comparável ao contrato principal da época —
     durante TODO o período testado, e não um contrato ainda em transição de
     rolagem? Aqui uma configuração quase foi promovida comparando um mês
     que era o 2º melhor entre 60 (sorte) contra um contrato que negociava
     ~300× menos volume que o principal durante boa parte da janela — as
     duas confirmações (série longa dividida em metades + liquidez do
     contrato da janela curta) são exigidas juntas, nenhuma sozinha basta.
     (6.46)

121. O histórico de ticks (negócios) está disponível para o período do
     backtest, com timestamp e preço por negócio, e alinhável à série de
     barras usada (atenção a séries ajustadas por diferença contra contrato
     cru, que exigem deslocamento diário)? Sem ele não há como refazer no
     caminho real um resultado de stop curto (da ordem do range de 1-5
     velas): aqui o caminho de 2 pontos por vela M1 deu +117 a +242 pts/op e
     uma "pista viva" em 3 janelas; nos ticks reais (83 pregões, mesmos
     dias) 6 de 8 células congeladas viraram negativas, uma com 0% de
     acerto (n=9). A premissa de caminho intra-barra vai declarada na linha
     do resultado. (6.47)
122. O framework de backtest/execução da plataforma nova tem alguma forma
     de auditar/assegurar que uma estratégia bar-a-bar não está
     "silenciosamente nunca agindo" — por exemplo, contando ocorrências
     BRUTAS da condição de gatilho versus ordens de fato emitidas, e
     alertando se a razão cair muito abaixo do esperado — antes de aceitar
     "zero trades" como veredito de uma hipótese? Aqui uma estratégia que
     combinava estado recalculado a cada barra com uma checagem de "ordem
     pendente" lida DEPOIS da atualização do mesmo estado, na mesma
     chamada, emitiu ZERO ordens em ~128 pregões apesar de o gatilho ter
     ocorrido 383 vezes em 122 pregões medido isoladamente — bug de ORDEM
     DE OPERAÇÕES dentro do handler de barra, não de lógica de sinal.
     (6.48)
123. O relatório de backtest da plataforma nova distingue contagem de
     OPERAÇÕES de contagem de SESSÕES/PREGÕES distintos, e sinaliza quando
     uma fração alta das operações se concentra dentro de poucas sessões
     (reentradas no mesmo dia já favorável), antes de aceitar "amostra
     grande" como evidência de robustez? Aqui um candidato com 667
     operações (5× mais que outro candidato da mesma busca) tinha a MESMA
     concentração nos top-3 pregões (59%) do candidato 5× menor — o
     contador de trades tinha subido, o número de pregões independentes
     que carregavam o resultado, não; o gatilho chegou a reentrar 24 vezes
     num único pregão. (6.49)
124. O framework de backtest/execução da plataforma nova oferece uma forma
     padrão de estratificação PÓS-HOC de trades já simulados por uma
     métrica candidata (sem precisar rodar uma simulação nova por grupo),
     para evitar o viés de comparar filtros exclusivos numa estratégia que
     rearma dentro da mesma sessão? Aqui, comparar 3 simulações exclusivas
     por força de gatilho (fraco/médio/forte) deu um gradiente limpo de
     win% (37,2%/23,3%/15,4%) que sumiu por inteiro (37,5%/37,5%/36,6%,
     correlação ≈ 0) ao reavaliar os MESMOS 121 trades de uma única rodada
     sem filtro, estratificados depois pela força de cada trade real. (6.50)
125. O critério de "censura"/invalidação de uma célula de backtest da
     plataforma nova distingue explicitamente morte por falta de capital
     (caixa cruzou a barreira, ordens recusadas) de seletividade
     intencional de um filtro combinado (frequência baixa por desenho, ex.
     AND de sinais independentes), ou aplica o mesmo limiar fixo de
     "fração mínima de dias com atividade" às duas situações? Aqui um
     filtro AND (ORB + estado anômalo WIN×WDO) foi reprovado nas 4 janelas
     testadas por `sem_trade` entre 73,8% e 90,2% dos pregões, com
     `equity_min` SEMPRE acima da margem crua e ZERO ordens recusadas por
     capital — a regra herdada de outra geração mediu seletividade por
     desenho como se fosse morte por caixa. (6.51)
126. O framework de validação da plataforma nova reporta a concentração
     (top-N pregões / líquido total) tanto no período de desenvolvimento
     quanto no de validação cega, lado a lado, e alerta quando a segunda
     for sistematicamente pior que a primeira — em vez de tratar o número
     do desenvolvimento como estimativa confiável da robustez real? Em
     três famílias de sinal sem relação entre si (confluência cruzada
     WIN×WDO, rompimento ORB, lateralização em retângulo) a concentração
     do IS (ex.: 41%/64% top3/top5) subestimou de forma sistemática e
     grande a do OOS (ex.: 97,2%/133,4%). (6.52)
127. Existe, na plataforma nova, uma forma padrão de medir se uma métrica
     de concentração/robustez é ESTÁVEL entre janelas (não apenas "boa"
     numa única janela) antes de promover um candidato — por exemplo
     exigindo a métrica dentro de uma faixa aceitável em pelo menos 2
     janelas fora da amostra? Aqui uma quarta família de sinal (G22,
     filtro de regime diário com p=0,0040 no IS, o mais significativo da
     busca) foi desenhada especificamente para corrigir o padrão de 6.52
     e o piorou — de 97,2%/133,4% (sem filtro) para 607%/816% (com
     filtro) no MESMO OOS-1, líquido caindo de R$ 650,00 para R$ 89,50.
     (6.53)
128. Esta plataforma marca de alguma forma (flag, campo ou API separada)
     quais cotações vêm de um LEILÃO (abertura/fechamento/circuit breaker)
     e quais vêm de negociação contínua — ou só dá para inferir pela
     janela de horário, como foi feito aqui? Sem essa marca, qualquer
     cálculo de amplitude/largura a partir de máximas e mínimas de vela de
     1 minuto (canal, retângulo, ATR simplificado) pode inflar dezenas de
     milhares de pontos com cotação INDICATIVA e não-negociável publicada
     no leilão, derrubando o patrimônio simulado sem nenhuma negociação
     real correspondente — medido na B3 (WINV26, 2026-08-12): oscilação
     de até 17.335 pontos em 6 minutos antes da abertura. Dois consertos
     mínimos: excluir a janela do leilão do cálculo, e aplicar um teto de
     sanidade por vela (aqui 2.000 pontos) antes de qualquer amplitude
     entrar na estratégia. (5.30)
129. No simulador/testador da plataforma, quais campos de preço vêm preenchidos em cada tick do histórico (last, bid, ask) e qual deles dispara o stop nativo? O SL anexado a uma ordem pendente é avaliado do mesmo jeito que o SL de uma posição? Aqui o SL nativo anexado a uma ordem-limite disparou no segundo da entrada em 5 de 5 compras e nunca nas vendas, e o `last` vinha 0 na maioria dos ticks — o EA passou de −R$ 1.043 para −R$ 78 (motor: −R$ 64) só ao tratar o campo de preço e a origem do stop. (6.54)
130. No contrato de futuro com vencimento da plataforma nova, como se obtém a data de rolagem (qual é o contrato PRINCIPAL em cada dia)? As barras de período longo (mensal/semanal) do contrato individual incluem o período em que ele ainda não era o principal — e, se incluem, o preço delas é de um mercado ilíquido e distante do real? Toda grandeza ancorada no calendário (abertura do mês/semana, VWAP ancorada, máxima do mês) do robô e do backtest usa a MESMA definição de contrato? Aqui a abertura do mês do WINV26 começava em 03/08, com o contrato ainda de trás (volume ~1000× menor, preço 2–3 mil pontos acima do mercado): o filtro leu "mês de baixa" de 12/08 a 08/09 durante uma alta de 6% e o EA, fiel ao código, só vendeu. (5.31)
131. A série contínua que a plataforma oferece é crua ou ajustada nos contratos passados — e, se ajustada, por diferença ou por proporção? A série "sem ajuste" continua sem ajuste para trás, ou só no contrato vigente? Aqui o `WIN@` do MT5 bateu 100% minuto a minuto com o WINV26, mas só de 13/08 em diante: a fração de fechamentos na grade de 5 pontos foi ~20% em jan–jul/2026, 73% em ago e 100% em set–out, e o Testador marcava "Qualidade do histórico 0%" — resultados de 2025 e jan–jul/2026 têm erro de escala de alguns % nos pontos. Confira em toda a janela, mês a mês, a grade de tick e a igualdade contra mais de um contrato real. (5.32)
132. Na plataforma nova, qual preço dispara o stop de um instrumento de
     bolsa, no simulador e no real (último negócio, bid ou ask)? E o
     simulador guarda uma cópia própria do histórico de ticks — como
     conferir que ela está completa (tamanho do arquivo, contagem de
     negócios por dia, campo de último preenchido e coerente com bid/ask)
     antes de confiar num resultado? Aqui o cache do Testador do MT5 tinha
     64,5 MB em agosto contra 79,8 MB no terminal; 235 de 357 ordens saíram
     sem o último negócio, 42 compras tomaram stop no segundo da entrada e
     6 vendas nunca tiveram stop (−R$1.854), com o relatório marcando
     "qualidade do histórico 100%". (5.33)
133. Na plataforma nova, como obtenho o tamanho do tick e a grade de preço
     válida do instrumento em tempo de execução, e onde o simulador/teste
     reporta as ordens recusadas por preço inválido? Aqui o EA do WDO com o
     tick 0,5 digitado rodou no WIN (tick 5): a corretora recusou toda
     ordem fora da grade (retcodes 10015/10016), o que sobrou deu +R$1.042
     em 22 trades e foi lido como edge; com o tick certo o mesmo robô deu
     −R$1.451 a −R$1.728 e nenhum candidato passou o percentil 95. (6.55)
134. A série contínua do futuro na plataforma nova é ajustada (por diferença
     ou por proporção) ou crua? Barras e ticks do MESMO símbolo usam o mesmo
     ajuste — e qual símbolo dá o preço cru do contrato principal? Aqui o
     `WIN@` do MT5 entregava barras M1 ajustadas por diferença (~80% dos
     preços fora da grade de 5 pontos antes da última rolagem; em 10/06/2026
     09:02 a barra abria 176.154 contra 169.265 do negócio real, ~6.900
     pontos) e ticks crus, e o CSV batizado "sem ajuste" herdava o ajuste
     (9.502 de 11.837 barras de janeiro fora da grade); o `WIN$N` era cru
     nos dois. Confirme a grade de tick e um ponto de checagem barra×tick
     antes de misturar sinal em barra com execução em tick. (5.34)
135. A base histórica da plataforma nova separa os leilões (abertura e
     fechamento) em barras próprias, mistura com a 1ª/última barra do dia,
     ou os omite? Aqui o close da última barra M1 do WIN era o preço do call
     em 127 de 127 dias (e o último negócio contínuo em 3), com volume ~23
     mil contra ~1,5–3 mil das barras vizinhas. (5.35)
136. Em que fuso vêm os horários da base e do perfil do instrumento, e o
     motor compara o corte de zeragem no MESMO fuso do dado? Aqui o corte
     estava em UTC (21:20) sobre dado em BRT, nunca chegava, e a zeragem
     caía na última barra do dia — o call. (5.35)
137. A plataforma/testador preenche ordens durante os leilões? A que preço, e
     como o testador trata uma ordem a mercado enviada na janela do call?
     (5.35, 5.30)
138. Qual é a grade oficial de fases do pregão e como ela muda ao longo do
     ano — inclusive com o horário de verão de outros países, que desloca o
     fim do contínuo de instrumentos atrelados a eles? Em tempo gráfico ≥5
     min, uma regra "zera às HH:MM" ainda dispara antes do call, ou a barra
     que a contém já o inclui? (5.35)
139. Como a plataforma nova trata stop/alvo atingidos na mesma barra/tick em
     que a entrada preencheu? O backtest dela avalia a saída dentro da barra
     do fill? Aqui o motor em barras só avaliava a partir da barra seguinte:
     457 de 3.283 trades (13,9%) tinham o stop estourado dentro da barra do
     fill, o pior trade com stop de 350 pontos perdeu −1.210 a −1.360 (3,5×
     a 3,9× o stop) contra −355 (1,01×) em ticks, e a soma das 60 células
     caiu de R$323.440 para R$304.863. (6.56)
140. A conta é netting ou hedging POR INSTRUMENTO? Se for netting e mais de um
     robô operar o mesmo instrumento, quem mantém a posição de cada um — a
     plataforma ou o meu sistema? Aqui cinco EAs com `magic` próprio se
     bloqueavam por "já há posição" (154 de 361 entradas, +R$9.006 bloqueados) e
     `PositionClose(_Symbol)` fechava a posição de todos: +R$14.079 isolados
     viraram +R$5.131 juntos. (1.26, 1.4)
141. O negócio (deal) carrega o identificador da ordem/robô (`magic`) também
     quando vem de uma ordem stop/limite PENDENTE que disparou, e não só de
     ordem a mercado? Sem isso não dá para reconstruir a ficha de cada robô do
     histórico. (1.26)
142. Existe OCO (uma-cancela-a-outra) nativo no SERVIDOR entre stop e alvo?
     Sem ele, stop e alvo independentes podem executar os dois com o robô fora
     do ar — em netting o segundo inverte a posição. (1.26, 1.23)
143. Uma ordem stop pendente fica viva no servidor da corretora com o terminal
     desligado, ou morre junto com a sessão? (1.26, 1.2)
144. Existe prevenção de autonegociação (self-trade) entre ordens pendentes da
     mesma conta e, se existir, qual lado ela cancela — a nova ou a antiga? (1.26)
145. Um stop que AUMENTA a posição líquida (o robô A fecha dentro de uma líquida
     do robô B no sentido contrário) passa por checagem de margem como abertura
     e pode ser recusado? O comentário da ordem sobrevive até o negócio — dá
     para marcar de qual robô veio sem depender do `magic`? (1.26, 1.1)
146. Quantos contratos negociam no preço da minha ordem limitada, entre a
     entrada no livro e o preenchimento, para ESTE instrumento? Calibrar por
     instrumento (extrato de ordens reais, Kaplan-Meier para a censura); não
     reaproveitar a calibração de outro ativo. Enquanto não houver número, a
     premissa de fila do backtest tem de ser estressada PARA CIMA, e o
     resultado reportado ao lado da queda: aqui, exigir 3 e 4 ticks em vez de 2
     tirou 22,5% e 29,5% do lucro do IS. (4.34, 4.22)

---

## O resumo, se sobrar só um parágrafo

**Backtest positivo é evidência sobre o sinal e sobre nada mais.** Toda a
diferença entre o número do backtest e o extrato da corretora mora em cinco
lugares: a fila (sua ordem não preenche só porque o preço tocou), o PREÇO (o
preenchimento saiu no nível que você pediu, ou um tick pior, sempre contra
você?), o dimensionamento (o stop cabe no capital?), o estado (o que acontece
quando o processo morre no pior instante?) e a proteção (ela existe na corretora
ou só no seu laço?). O robô que zerou a conta era TOP-1 do pódio, com 89% de
retenção fora da amostra, e morreu no primeiro dia sem nunca ter errado um
sinal. O robô seguinte também não errou sinal nenhum: no mesmo pregão em que o
gêmeo em sombra fez +R$171,00, ele fez −R$116,00 — e a diferença inteira era
execução.

E há um sexto lugar, que é o mais difícil de ver porque não aparece em lugar
nenhum: **o custo que o simulador não cobra.** Um tick de deslize na saída por
alvo — R$5,00 por trade, medido no extrato — separava **+R$347.548,50** de
**−R$242,50** na MESMA geometria, na mesma janela, com os mesmos trades. A
varredura de 250 células que escolheu essa geometria estava, sem que ninguém
percebesse, procurando o ponto onde o motor era mais generoso.
**Um ótimo que mora exatamente onde o simulador é mais otimista que a
realidade não é um ótimo: é o sintoma de um modelo incompleto.**

---

*Fonte deste arquivo: incidente de 2026-08-28 e a auditoria adversarial que o
seguiu (27 lacunas, todas fechadas), mais os três defeitos que os próprios
relatórios de correção deixaram anotados como "risco residual" e que, verificados
depois, eram reais e reproduzíveis. Mais uma segunda rodada de auditoria
adversarial em 2026-09-03, focada no dimensionamento dinâmico adicionado depois
da primeira: 3 lacunas novas (1.15, 3.13, 3.14), todas corrigidas no mesmo dia —
e a correção de uma delas revelou outras duas que ninguém tinha procurado (1.16
e 3.15, a segunda mais grave que a lacuna original). Mais a investigação de
2026-09-07 sobre por que o backtest divergia da corretora no pregão de
2026-09-04, que rendeu 5 itens (4.12, 4.13, 5.10, 5.11, 5.12): a divergência
não era do robô — eram duas defesas que a rota de produção tem e o script de
pesquisa não tinha, mais uma soma que misturava conta real com conta sombra,
mais um cursor de paginação sem fuso que já tinha apagado 19,3% da base
canônica de tick usada como referência da própria investigação. Mais uma
rodada, mesma janela de 2026-09-07, sobre o WDO F1 perseguindo o preço e
travando o próprio freio de segurança: 3 itens (1.18, 3.16, 4.14) — um
freio de cadência calibrado pra barra que dispara no primeiro minuto de
tick, uma reancoragem sem espera mínima que persegue o preço e nunca é
tocada, e uma recusa por capital sem espera que virou 25.556 tentativas
idênticas num único pregão. Mais uma última rodada no mesmo dia, fechando
a regeneração do canônico: 2 itens (5.14, 5.15) — o recorte `WDO_A_f1.
parquet` da linha F1-tick carregava um SEGUNDO bug de fuso próprio (índice
rotulado 3h cedo, além de truncado), achado batendo o MESMO negócio nos
dois arquivos; e a calibração do freio de cadência que escolheu o default
de produção (`reancora_min_segundos=10,0`) rodou 4 minutos antes do
canônico corrigido substituir o arquivo em disco, medindo sobre uma base
com 19,3% dos minutos de pregão faltando sem nenhum sintoma. Mais 1 item
fechando o desfecho daquela rodada, em 2026-09-07: a calibração foi refeita
sobre a base já corrigida (5.16) — o valor de produção sobreviveu (10s,
0/130 pregões travados), mas o conjunto de pregões que travam mudou por
completo e a relação com o parâmetro se confirmou não monotônica, o que
por si só derruba a ideia de que "mesmo número" bastasse como confirmação.
Mais 6 itens e 1 reescrita em 2026-09-08, da auditoria do pregão real inteiro
do WDO F1 (−R$116,00 líquidos, freio duro disparado), lida do histórico de
DEALS e de ORDENS do terminal e cruzada com `db/live.sqlite`: o item 4.8 saiu
de n=1 para n=8 (8 de 8 alvos nativos pior que o nível pedido, sempre contra a
posição, R$45,00 de deslize num dia), mais 1.20 (o freio de cadência não cobre
o rearme pós-fill: 125 ordens para 22 trades), 1.21 (2 contratos preenchidos
com 83 ms de diferença viraram 1 no diário), 4.15 (21 saídas rotuladas "alvo"
sem que nenhuma tenha pago o alvo), 4.16 (11 posições de menos de 1 segundo
contadas como trades, metade de tudo que o robô já fez com dinheiro real), 4.17 (limite ancorado em preço de 24 minutos atrás
executando como agressor) e 4.18 (sombra +R$171,00 contra real −R$116,00 no
mesmo minuto; R$430,00 de gap de execução, e 3 de 3 pregões reais negativos,
−R$435,00 acumulados). Mais 1 item em 2026-09-08, fechando a primeira medição IS/OOS da config REAL
de produção (T2/S16) sobre a base de tick já corrigida: a janela OOS fez 2
trades e travou por 50 dos 51 pregões — à primeira vista overfitting
clássico, mas é censura pelo mesmo piso de capital dos itens 3.10/3.11, e o
achado de método é que perto desse piso IS-vs-OOS deixa de validar
generalização e passa a comparar dois sorteios (6.15). Mais 1 item no mesmo 2026-09-08, da investigação sobre POR QUE aquele
pregão real acumulou ordens contra preços defasados (4.17): o feed de tick do
terminal cegou por 44,8 minutos sem levantar erro nenhum — lista vazia em 538
passos seguidos e depois 13.644 barras de uma vez, com o mercado negociando o
tempo todo e o slot SOMBRA congelando no mesmo tick ao milissegundo — e o freio
que existia media a idade do PROCESSO, não a do DADO, então não viu nada (5.17).
Mais 1 item e 1 extensão no fim do mesmo 2026-09-08, o achado mais caro do
arquivo em resultado de pesquisa: o item 4.8 saiu de n=8 (um pregão) para
**n=11, a população COMPLETA** de operação real deste robô — média −1,000
tick, desvio 0,447, **10 contra e ZERO a favor**, R$55,00 sobre R$95,00 de
bruto teórico (57,9%) — com o STOP medido em separado andando na direção
oposta (5 de 5 nunca pior que o pedido); e o motor passou a COBRAR esse tick
(commit `4eb3e4a`), o que derrubou a geometria de PRODUÇÃO: T2/S16 tem
breakeven de 95,00% contra win% medido de 94,5% (IC 95% [94,04 ; 94,96],
z = −2,15) — **não tem edge**, e a compensação intuitiva de pedir 1 tick a
mais leva a zero, não a lucro, porque o gatilho anda junto. O motor regalava
R$93.710,00 no IS e R$45.520,00 no OOS, e a varredura de 250 células que
escolheu essa geometria rodou nele: toda a calibração deste robô precisa ser
refeita (6.18). Mais 1 item da auditoria do mesmo commit, e este NÃO custou
dinheiro identificado — é lacuna, não incidente: o motor mandava ordem a
mercado por cima do STOP de uma posição FATIADA que já tinha `sl` registrado
na corretora, porque uma guarda que existia só por causa do alvo cobria os
dois motivos. Além do spread pago à toa, o risco era saída DUPLA, que em
conta netting não zera — inverte o lado, o desfecho do incidente de
2026-08-28 por outro caminho. Exposta era a `gremah` (`dividir_entrada=True`
por padrão, ação B3, slot real ligado), mas os 5 pregões de log do slot real
registram `entradas=0 saidas=0` em todos os passos: exposição de
configuração, nunca exercitada (1.23). Mais 1 item em 2026-09-09, primeiro
pregão da saída maker fatiada ao vivo e o terceiro ângulo do mesmo padrão de
08-28: um fechamento a mercado que a corretora EXECUTOU voltou com sucesso mas
sem preço nem deal, a proteção de 08-28 classificou como recusado, e o robô
seguiu se achando comprado — reverteu para short em cima do zerado enquanto a
ordem-limite de saída ficou órfã no livro e preencheu 3 segundos depois: short
de 2 contratos numa conta de R$375 dimensionada para 1, `price_open` em
5113,75 (fora da grade de 0,5 do WDO), stop de −R$80,00, pregão de −R$65,00, e
o diário registrando o trade que estava sob medição como "+R$9,50 no alvo"
quando o real foi +R$5,00 a mercado (1.24). Mais 3 itens em 2026-09-09,
fechando o rollout de `core.instruments` além da contabilidade de caixa e a
lacuna deixada em aberto pelo item 5.19: 5.22 (o terminal podia devolver
`trade_tick_value=0` para símbolo fora do Market Watch, e nada validava isso
antes de dividir — zero silencioso em ação, `ZeroDivisionError` mudo em
futuro), 5.23 (o `tick_size` que o robô ao vivo de fato usava vinha do
default do construtor, não do perfil, e um comentário afirmava o contrário
havia 13 dias sem nenhum teste checar a afirmação) e 5.24 (a rotina de
desmonte fechada em 5.19 ainda avisava-e-creditava um preço em cache velho
demais em vez de recusar — a mesma barra de 12 dias era, além de velha,
anterior à própria abertura da posição, e a correção passou a fechar pelo
preço de entrada nesse caso, como já fazia para "sem preço nenhum"). Mais 1
item no mesmo 2026-09-09, do primeiro dia real da saída fatiada (6.19): o
motor não tinha modelo de fila do lado da SAÍDA (só a entrada tinha, desde
2026-08-26) e o estouro de prazo saía a mercado precificado como maker —
7 saídas por alvo no pregão, 1 preencheu por limite, 6 saíram a mercado; o
backtest previa +R$36,00, o dia deu −R$14,00, e a taxa de fill calibrada em
92,8% (item 6.20) deu 14% real. Corrigidos os dois defeitos e medido em duas
janelas com capital real (R$375): o motor sem fila de saída, que vinha
decidindo tudo, dava +R$244.429 (IS) e +R$148.760 (OOS); com fila de 400
contratos, TODAS as células viraram −R$226 a −R$250, censuradas por caixa
(6.15) — e as duas células com n grande o bastante (n=2.741 e n=4.920) deram
edge bruto de +R$0,41 e +R$0,45 por trade, menor que a corretagem de R$0,50
(4.21). Mais 1 item na noite do mesmo 2026-09-09, que é o DESFECHO daquela
cadeia e o segundo mais caro do arquivo em resultado de pesquisa: com as duas
filas calibradas (438/489), 1 mês do IS rodado com o **caixa reposto a cada
pregão** — para separar ruína de expectativa — devolve **0 de 21 pregões
positivos** em T2 contra quatro stops, os quatro intervalos de confiança do
win% inteiros ABAIXO do breakeven, e R$/operação convergindo para −R$5,00 (não
para zero) conforme o stop alarga. A sensibilidade fecha o argumento: a MESMA
janela com fila 0/0 dá **21 de 21 pregões positivos**, o ponto de virada fica
em ~170 contratos e o livro real tem 438. Todo lucro que esta família já
mostrou — os +R$239.936,50 e +R$77.833,50 do item 6.19 incluídos — era
artefato de uma única premissa do simulador (6.21). Mais 1 item em
2026-09-10, a terceira aparição da família do item 1.14: o motor avisa a
estratégia quando RECUSA uma ordem e não avisa quando ela EXPIRA por prazo
— uma ORB de laboratório passou 14 de 72 pregões (19,4%) em silêncio
acreditando ter ordem no livro, +R$413,00 (+33%) de líquido do outro lado,
e a defesa correta já existia pronta na `CopaWin` sem nunca ter sido
copiada (4.25). Mais 2 itens em 2026-09-14: o único caminho de saída
obrigatório do desenho ("day trade nunca carrega overnight") nunca tinha
disparado ao vivo para futuro — dois cortes derivados do MESMO campo se
anulando em silêncio, zero eventos FLATTEN em toda a história do diário
(4.28); e, ao corrigir aquele bug, o motivo pelo qual milhares de testes
verdes nunca acusaram — três camadas repetindo a mesma suposição errada
(motor, runtime, supervisor), um teste que CONGELAVA o valor defeituoso
havia meses, e nenhum teste morando na junta entre os dois módulos onde o
bug de fato vivia (4.29). Mais 2 itens em 2026-09-21, do primeiro pregão
real do `wdo_orb` em produção: o slot subiu 6 minutos antes da abertura, a
detecção automática de contrato degradou para "mapeado pra ele mesmo" por
falta de book, e o mapa salvo ficou vazio — o robô operou o pregão inteiro
contra um símbolo (`WDO@`) que a corretora recusa, zero ordens enviadas
(5.27); e, no mesmo pregão, um congelamento de 36 minutos no feed de tick
levou a estratégia a armar entrada sobre dado velho, `live/` recusou o envio
corretamente mas não avisou a estratégia — a mesma família do item 4.25,
agora no caminho da camada de execução em vez do motor, achado em 3 dos 7
pregões de sombra desde 11/09 (4.33). Mais 1 item no mesmo 2026-09-21, o
quinto conserto do dia: o warm start ao reiniciar no meio do pregão nascia
DESLIGADO por default para todo robô sem âncora fixa — valor de queda de
uma política escrita só para a `Gremah` — e um restart às 11:19 fez o
`wdo_orb` tirar stop e alvo da faixa 11:19..11:34 em vez de 09:00..09:15,
outra estratégia rodando dinheiro real; invertido o default, o mesmo
restart reconstruiu o estado desde a abertura em segundos (5.29). Mais o
registro acumulado do projeto. Quando um item aqui contradisser o código, o
código ganha — e este
arquivo está desatualizado.*
