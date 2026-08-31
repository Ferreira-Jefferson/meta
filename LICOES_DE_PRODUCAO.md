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

**Sobre o estado**
6. Dá para listar as ordens vivas do meu robô ao iniciar? (1.8)
7. A leitura de posição distingue "não há" de "não consegui perguntar"? (1.6)
8. O que sobrevive a um reinício da plataforma, e o que eu preciso persistir por fora? (2.1)
9. Como impedir duas instâncias do mesmo robô? A plataforma impede? (2.4)
10. Dá para gravar de forma durável no meio de uma sequência de ordens, sem
    perder a sessão e sem um segundo escritor travar a operação em andamento? Se
    não, qual é o menor lote que pode ser gravado atomicamente? (2.5)
11. O modelo de erro permite carregar dado junto da exceção — ou recuperar o
    resultado parcial de uma chamada que abortou no meio? Se não, nada de
    acumular efeito confirmado em variável local: cada um é emitido assim que
    confirma. (2.5)
12. O evento de rejeição de uma ordem chega de volta pra quem decidiu, ou fica
    só no log do motor de execução? (1.14)

**Sobre o dinheiro**
13. Dá para consultar a margem exigida por uma ordem e a margem livre da conta? (3.3)
14. A conta é netting ou hedging? (1.4)
15. Existe algum limite de perda diária imposto pela plataforma, ou preciso construí-lo? (Parte 0, falha 5)
16. O capital mínimo que abre 1 posição foi testado rodando o histórico
    INTEIRO com esse capital, ou só calculado pela fórmula de margem? Os
    dois números costumam divergir por uma ordem de grandeza. (3.10)
17. Se o capital de sobrevivência estiver acima do capital real disponível,
    isso já foi confirmado como estrutural (parede em TODO ponto do
    parâmetro já mapeado), ou ainda pode ser um parâmetro mal escolhido?
    Varrer o espaço inteiro contra capital baixo responde em uma tarde. (3.11)
18. O stop desta estratégia é fixo (ticks/pontos) ou varia com a
    barra/dia (volatilidade)? Um teto por % de risco emprestado de outro
    robô com o tipo OPOSTO de stop pode reproduzir o problema que ele foi
    criado pra evitar, só que noutro capital. (3.12)
19. Abrir uma posição vendida credita caixa (venda a descoberto) ou debita
    margem/garantia (compromete capital, igual à compra)? O valor-a-mercado
    da posição na tela tem de inverter exatamente o débito/crédito real da
    abertura — não uma convenção genérica de "venda é negativo". (5.8)

**Sobre a medida**
20. O simulador modela posição na fila? Se não, o que ele está respondendo? (4.1)
21. O horário de sessão que ele usa é fixo ou segue o instrumento? (5.2)
22. Qual é o edge da estratégia **em ticks** neste instrumento? (4.5)
23. Uma sequência de stops cabe no capital real? Se o tamanho da posição
    escala com o caixa, existe um teto de RISCO por trade separado do teto
    de MARGEM? (3.5, 3.9)
24. O preço que a API devolve para este instrumento já é reais por unidade,
    ou é cotação (pontos de índice, pontos de dólar, ticks) que exige um
    multiplicador para virar dinheiro? Se exige, o débito/crédito de caixa
    lê esse multiplicador do MESMO lugar que o cálculo de P&L, ou é uma
    segunda cópia da fórmula? (5.7)

---

## O resumo, se sobrar só um parágrafo

**Backtest positivo é evidência sobre o sinal e sobre nada mais.** Toda a
diferença entre o número do backtest e o extrato da corretora mora em quatro
lugares: a fila (sua ordem não preenche só porque o preço tocou), o
dimensionamento (o stop cabe no capital?), o estado (o que acontece quando o
processo morre no pior instante?) e a proteção (ela existe na corretora ou só no
seu laço?). O robô que zerou a conta era TOP-1 do pódio, com 89% de retenção fora
da amostra, e morreu no primeiro dia sem nunca ter errado um sinal.

---

*Fonte deste arquivo: incidente de 2026-08-28 e a auditoria adversarial que o
seguiu (27 lacunas, todas fechadas), mais os três defeitos que os próprios
relatórios de correção deixaram anotados como "risco residual" e que, verificados
depois, eram reais e reproduzíveis. Mais o registro acumulado do projeto. Quando
um item aqui contradisser o código, o código ganha — e este arquivo está
desatualizado.*
