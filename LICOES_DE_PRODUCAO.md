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
> significa — e num caso o erro é silencioso.

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

---

## Parte 7 — Disciplina de trabalho

### 7.1 Ao corrigir um bug, varra todas as instâncias do padrão

O mesmo defeito de cancelamento existia em 5 pontos; o lado da saída escapou da
primeira varredura porque a busca procurou o método direto e não os chamadores de
cada método de cancelamento.

> **Regra:** depois de achar a causa raiz, pergunte "que outros lugares leem o
> mesmo campo / fazem a mesma coisa da mesma forma errada?" e corrija todos antes
> de declarar terminado.

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
24. O simulador modela posição na fila? Se não, o que ele está respondendo? (4.1)
25. O horário de sessão que ele usa é fixo ou segue o instrumento? (5.2)
26. Qual é o edge da estratégia **em ticks** neste instrumento? (4.5)
27. Uma sequência de stops cabe no capital real? Se o tamanho da posição
    escala com o caixa, existe um teto de RISCO por trade separado do teto
    de MARGEM? (3.5, 3.9)
28. O preço que a API devolve para este instrumento já é reais por unidade,
    ou é cotação (pontos de índice, pontos de dólar, ticks) que exige um
    multiplicador para virar dinheiro? Se exige, o débito/crédito de caixa
    lê esse multiplicador do MESMO lugar que o cálculo de P&L, ou é uma
    segunda cópia da fórmula? (5.7)
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
    executou vira número inventado no diário. (1.17)
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
refeita (6.18). Mais o registro acumulado do projeto. Quando um item aqui contradisser o código, o código ganha — e este
arquivo está desatualizado.*
