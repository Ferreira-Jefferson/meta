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
artefato de uma única premissa do simulador (6.21). Mais o
registro acumulado do projeto. Quando um item aqui contradisser o código, o
código ganha — e este
arquivo está desatualizado.*
