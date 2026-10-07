# WinMaestro — especificação

Versão 1.0 (2026-10-07), para implementar. EA MQL5 único para o WIN na B3, conta NETTING na Rico, dinheiro real. Aposenta o WinSeletor v1.00.

Convenções:
- "item X.Y" aponta para `LICOES_DE_PRODUCAO.md`; "P n" aponta para a pergunta n do Apêndice E; decisões do dono (D1–D3, B n, O n) estão no Apêndice B; os itens deixados de fora, no Apêndice D.
- WIN: tick = 5 pts = R$1,00 por contrato. O EA **lê** tamanho e valor do tick do símbolo; leitura zerada nunca é usada (item 5.22).
- **Ficha** = posição virtual de um robô = Σ do volume assinado dos deals com o magic dele (seção 3). Lote fixo: 1 contrato.
- **Leitura confiável** = `TERMINAL_CONNECTED` verdadeiro há ≥ 10 s contínuos, histórico relido por inteiro depois da última reconexão e `PositionSelect` sem erro.
- **Corte** = fim do pregão contínuo da data − 5 min (seção 9).

## 0. O que é

Um EA que roda a lógica dos 5 robôs (GB, CM, DM, RE, C1) ao mesmo tempo. Cada robô tem uma ficha e envia as ordens dele **com o magic dele**, de modo que a líquida da conta seja sempre Σ fichas + exposição externa. Com um robô ligado, faz o que o EA avulso fazia; com os cinco, cada um opera como se estivesse sozinho. Uma instância só, num PC só (D3).

### Princípios

1. **Cada robô decide sozinho**, com as regras e os níveis de stop dele. O maestro não filtra, não combina, não prioriza; executa, contabiliza e protege.
2. **A verdade sobre o que foi executado é a corretora.** Fichas saem dos deals. A memória em disco guarda só o que a corretora não sabe: níveis, instantes e ordens enviadas.
3. **Verificação antes de toda ordem** (D1, seção 4.3). Estado que não fecha não envia. Nada é reenviado por inferência de tempo.
4. **Toda entrada, de qualquer robô, nasce com o stop já na corretora** (B4). Netting não tem SL por robô, então o stop é uma ordem stop própria (S) com o magic do robô, enviada junto com a entrada (5.3). Toda S tem validade do dia (B10). Exceções aceitas pelo dono, todas só com o EA fora (a MT5 em netting não tem OCO): (a) S e alvo do RE executam os dois e a ficha fica invertida, sem stop; (b) a entrada vence sem encher e a S fica sozinha até o fim do pregão; se o preço chegar a ela, abre 1 contrato sem stop; (c) ficha aberta no corte com o EA fora passa a noite e o leilão de abertura **sem stop** (9.3). Pior caso: seção 13.
5. **Uma saída nunca tira o stop.** A S é cancelada **só depois** que a saída executou; saída recusada deixa a S intacta.
6. **Nada de trava não pedida.** Só existem as proteções desta especificação.
7. **Proteção posta pelo dono nunca é apagada pelo robô.** SL/TP que o dono puser na líquida não é removido.
8. **Tudo que o EA faz ou decide vira uma linha de log** (seção 11), inclusive o que aconteceu com ele fora do ar, com a hora real do deal.

## 1. Arquivos, magics e inputs

| Item | Valor |
|---|---|
| EA | `mt5/WinMaestro.mq5` |
| Porta única para a corretora | `mt5/WinMaestro/Corretora.mqh`: só ela chama `OrderSend`, `OrderDelete`, `OrderModify`, `PositionSelect`, `Order*`, `History*`, `AccountInfo*`, `SymbolInfo*` |
| Demais módulos | `Fichas.mqh`, `Recupera.mqh`, `Memoria.mqh`, `Log.mqh`, `Grade.mqh`, um `.mqh` por robô (copiado do WinSeletor e adaptado, Apêndice A) |
| Magics | GB 80080601, CM 80080501, DM 80080101, RE 20261005, C1 80080002 |
| Grade de horários | `data/b3_grade_horaria_win.csv` embutida em `Grade.mqh` (atualizar = recompilar) |

**Inputs.** Grupo **Maestro no topo**, com os 5 liga/desliga `Ativo_GB` … `Ativo_C1` (padrão `true`). Robô desligado não abre nada novo; se tiver ficha ou ordem viva, continua gerindo até zerar. Depois vêm os grupos dos robôs como no WinSeletor, sem: os inputs de lote (lote = 1), `GB_ServerGMTOffsetH`, `GB_RegimeAutomatico`, `GB_FimContinuoMin` (vêm da grade) e `RE_LimiteEquity` (o `TesterStop` por equity pararia os cinco).

Mudar input reinicia o EA e passa pela recuperação (seção 10). O `OnInit` reinicializa explicitamente toda variável global e chama `Reseta()` de cada módulo (P17).

**Constantes:** `CM_RESERVA_PTS` 4.945 (O11); `PRAZO_CONFIRMACAO` 5 s (consulta a cada 250 ms); `ALERTA_SEM_DESFECHO` 30 s; `PRAZO_SEM_DESFECHO` 10 min; `IDADE_PROVA` 30 s; `RETENTA` 5 s; `STOP_EMERGENCIA_PTS` 1.200; `DM_CAPITAL` R$1.000; `MARGEM_CORTE` 5 min.

## 2. Papel das ordens

| Papel | Ordem | Validade |
|---|---|---|
| E entrada | limite (C1: mercado), magic do robô, sempre com a sua S (5.3) | GB `SPECIFIED` até `g_exp` (recusada → DAY e cancelamento pelo EA em `g_exp`); CM, DM, RE DAY (B2) |
| S stop | `SELL_STOP` protege compra, `BUY_STOP` protege venda, volume 1; nasce com a E | **DAY** (B10, P1) |
| A alvo (só RE no padrão) | limite oposta, volume 1 | DAY |
| X saída / C correção | mercado oposta, volume = \|ficha\| | — |

Preenchimento: limite `ORDER_FILLING_RETURN`, desvio 0; mercado `RETURN` se `SYMBOL_FILLING_MODE` permitir, senão `IOC` (P15). O SL/TP da posição líquida nunca é usado.

**Comentário:** `MAE|<robo>|<papel>|<seq>` (ex.: `MAE|CM|E|0042`), `seq` por robô e por pregão, gravado na memória; memória perdida → maior `seq` do dia no histórico + 1. O comentário serve para achar ordem sem ticket (4.3) e para o log; o papel é decidido por (magic, tipo, lado em relação à ficha), nunca pelo comentário (P3).

**Uma operação por vez por robô** (O4). Em cada instante o robô tem, no máximo, **uma** destas: (i) E viva ou sem desfecho + a S dela; (ii) ficha ±1 + a S + a A, se houver. Pedido de segunda entrada do mesmo robô volta `BLOQUEADA segunda entrada`, log `SEGUNDA_ENTRADA`; nenhum papel é reenviado enquanto o anterior do mesmo papel não tiver desfecho (4.4). É a proteção contra laço de defeito: não há teto de envios nem disjuntor.

**Invariantes por robô** (conferidos a cada reconciliação): no máximo uma S, só com ficha ≠ 0 ou com E viva/sem desfecho, do lado que protege; no máximo uma A, só com ficha ≠ 0; E só com ficha 0, no máximo uma. Ordem de magic de robô fora disso, com mais de 5 s de vida e sem ordem do robô sem desfecho, é **órfã**: cancelada (5.1), log `ORFA`. Entre duas S fica a de nível mais protetor. Ordem de magic desconhecido nunca é tocada.

## 3. A ficha

### 3.1 Cálculo

Uma função só, `Ficha_Recalcula()`, que relê a corretora e é chamada **antes de qualquer decisão**: a cada deal (`OnTradeTransaction`), a cada reconciliação (1 s) e imediatamente antes de cada envio.

| Campo | Cálculo |
|---|---|
| ficha | Σ volume assinado dos deals BUY/SELL do símbolo com `DEAL_MAGIC` do robô, na janela (3.2), menos os volumes absorvidos (7) |
| preço médio | média ponderada dos deals que afastam a ficha de zero, desde o último zero dela |
| hora de abertura | `DEAL_TIME_MSC` do primeiro deal da ficha atual |
| resultado | Σ (preço de saída − preço médio) × volume × lado × valor do ponto, menos `DEAL_COMMISSION` e `DEAL_FEE` |
| externa | Σ dos deals da janela com magic que não é de robô, mais os volumes absorvidos (7) |

- `DEAL_ENTRY` e `DEAL_PROFIT` não entram (descrevem a líquida). Deals de balanço, crédito, taxa e variação de margem não entram no volume; logados uma vez (`AJUSTE`).
- Estados válidos: 0 ou ±1. **Duplicada** (\|ficha\| = 2) e **trocada** (sinal oposto ao do deal que abriu o ciclo) vão para a seção 8; o módulo nunca as vê.
- Ficha cujo deal de abertura é de pregão anterior = **ficha que atravessou a noite** (9.3).

### 3.2 Janela e verificação cruzada

O histórico é lido desde o último instante em que a líquida do símbolo foi zero: começa em `negociacao_inicio` de hoje − 10 min; se Σ de todos os deals do símbolo (todos os magics) ≠ líquida real, recua um pregão, até 10.

**Verificação cruzada** = Σ dos deals da janela = líquida real. É ela que diz que o histórico está completo. Se não fecha em 10 pregões: bloqueio de entradas que exige o botão (7.2), ALERTA; ao apertar o botão a diferença é gravada como **externa de origem desconhecida** e passa a entrar na conta.

### 3.3 Interface com os módulos

Os módulos não tocam em `Position*`, `Order*`, `History*`, `trade.*`. Trocas:

- `PositionSelect` + magic → `Ficha_Tem(robo)`; os 3 "tem posição de outro robô, não entro" (CM L774, DM L379, C1 L620) saem.
- `POSITION_PRICE_OPEN/TYPE/TIME` → `Ficha_Preco`, `Ficha_Lado`, `Ficha_Hora`; `POSITION_SL` → `Ficha_Stop` (nível pedido pelo robô).
- `PositionClose` → `Ficha_Fecha(robo, motivo)` (5.2); `PositionModify(sl)` → `Ficha_DefineStop(robo, nivel, motivo)` (5.3).
- `trade.Buy/Sell` com SL → `Ficha_EntraMercado(robo, lado, stop, motivo)`; `BuyLimit/SellLimit` → `Ficha_EntraLimite(...)` ou `Ficha_DefineAlvo(...)`; `OrderDelete` → `Ficha_Cancela(robo, papel, motivo)`; `OrderSelect(g_ordem)` → `Ficha_Entrada(robo)`.

Toda função de envio devolve `ENVIADA`, `RECUSADA` (retcode) ou `BLOQUEADA` (motivo). O módulo trata as duas últimas como hoje trata falha de `OrderSend` (item 4.33).

Avisos ao módulo, por `Robo_Evento(robo, evento)`: `ENTRADA_CANCELADA` (a E sumiu sem deal: maestro, dono, corretora ou validade) e `EXECUTOU_ANTES` (o cancelamento perdeu a corrida). Para todos os robôs a resposta é **não rearmar**, como no avulso. O maestro nunca reenvia uma E; S, X, C e cancelamentos são retentados só por ele.

## 4. Envio e verificação D1

### 4.1 Registro de trânsito

Toda ordem (inclusive S e cancelamento) entra no registro **antes** do `OrderSend`: robô, papel, `seq`, comentário, volume, hora. O registro é gravado na memória antes do envio e cada envio vira uma linha `ORDEM` no log. Ticket e `request_id` são preenchidos no retorno (podem ficar 0).

### 4.2 Ordem de processamento

Envios seriais: o próximo só sai depois do retorno do anterior. Num ciclo, primeiro cancelamentos e saídas, depois entradas, sempre na ordem fixa GB, CM, DM, RE, C1.

### 4.3 Verificação antes de toda ordem (D1)

Antes de enviar qualquer ordem do robô r, `Ficha_Recalcula()` e conferência. **O estado fecha** quando:
1. a leitura é confiável;
2. a verificação cruzada fecha (3.2);
3. r não tem ordem sem desfecho;
4. a ordem pedida é coerente com a ficha e as ordens vivas de r (seção 2: uma operação por vez; S só para ficha ≠ 0 ou para a E do robô, e sem outra S viva; X com volume = \|ficha\|);
5. E ou A não cruza com limite própria viva do lado oposto, de outro robô (compra ≥ venda própria, venda ≤ compra própria): senão `BLOQUEADA autonegociacao` (O2; P12).

Fecha → envia. Não fecha → não envia (`BLOQUEADA estado aberto`), loga o que não fecha e tenta explicar, nesta ordem: releitura completa do histórico de deals e de ordens; busca de cada ordem sem desfecho por ticket, `request_id` e comentário; com a memória perdida, as linhas `ORDEM` do log do dia. Com estado aberto as S já vivas continuam no servidor protegendo.

### 4.4 Desfecho de uma ordem

`DONE`/`PLACED` sem deal, `OrderSend` falso e retcode de transporte com ticket 0 significam **"não sei"**, nunca "não executou" (itens 1.6, 1.17, 1.24). O desfecho é procurado a cada 250 ms por 5 s e depois a cada reconciliação. Só se resolve por prova:

| Desfecho | Prova |
|---|---|
| executada | deal com `DEAL_ORDER` = ticket da ordem (ticket achado pelo retorno, pelo `request_id` ou pelo comentário) |
| viva | listada nas pendentes |
| não executada | ordem no histórico com `CANCELED`, `REJECTED` ou `EXPIRED`; ou, com leitura confiável, ordem com mais de `IDADE_PROVA` (30 s), ausente das pendentes e do histórico, sem deal, **e** verificação cruzada fechando (se ela tivesse executado, a líquida diferiria dos deals) |

Sem prova, a ordem fica **sem desfecho** e o robô dono fica **pausado** (sem `Tick()`); as S vivas dele seguem no servidor. ALERTA aos 30 s; aos 10 min, bloqueio de entradas que exige o botão (7.2). O botão, apertado pelo dono depois de olhar o extrato, retira as ordens sem desfecho do trânsito; a ficha continua vindo dos deals. O log registra quanto tempo cada ordem ficou sem desfecho e qual prova a resolveu. Se P6 ou P18 mostrarem deal chegando mais de 5 s depois da execução, a prova pela posição passa a exigir 3 leituras iguais em ≥ 3 s (O6).

### 4.5 Retentativas

S, X, C e cancelamentos recusados: retentados pelo maestro a cada `RETENTA` (5 s); ALERTA na 5ª recusa seguida e a cada 5 min enquanto durar (item 1.13). E recusada volta ao módulo, que decide pela regra dele.

## 5. Stop, saída e cancelamento

### 5.1 Cancelamento confirmado

Confirmado = ordem no **histórico** com `CANCELED` ou `EXPIRED`; o retcode do `OrderDelete` não basta (item 1.5). Desfecho `FILLED` → `EXECUTOU_ANTES` a quem pediu. Sem desfecho, a ordem segue tratada como viva (4.4).

**Cancelar uma E** (prazo, regra do robô, bloqueio, corte): cancela a E, confirma no histórico e **só então** cancela a S dela. Se a E encheu nesse meio-tempo, a S fica e protege a ficha. A E que some sem deal por validade vencida segue o mesmo caminho: S cancelada depois da confirmação.

### 5.2 Saída a mercado

Vale para toda saída: regra do robô, nível atravessado, zeragem, corte, ficha da noite, correção. Só dentro do contínuo.
1. Cancela a A do robô, se houver (5.1). **A S fica.**
2. A executou → não envia; recalcula. Sem desfecho → espera (4.4).
3. Envia a mercado, lado oposto, volume = \|ficha\|.
4. **Saída executada (deal visto) → cancela a S** (5.1). Se a S executou antes, a ficha fica trocada → seção 8.
5. **Saída recusada → a S continua**; retenta a cada 5 s (horário, corte, ficha da noite) ou fica com o robô (saída por regra).

Risco residual aceito (B6): S no nível do preço executando junto com a saída → ficha trocada de 1 contrato, corrigida pela seção 8 (item 1.23).

### 5.3 A S: criar, mover, recriar

- **Entrada limite (GB, CM, DM, RE):** a S é enviada logo depois de a E ser aceita (viva), volume 1, no nível de stop do robô calculado a partir do preço da limite. Ela vive desde antes do preenchimento. S recusada → retenta (4.5); sem S em 5 s → cancela a E (5.1).
- **Entrada a mercado (C1):** a S é enviada **antes** da E; só com a S viva a E sai. E recusada ou provada não executada → cancela a S. E sem desfecho → a S fica (4.4).
- **Robôs que reancoram o stop no preenchimento** (RE pelo preço do fill, DM pela distância): a S nasce no nível pré-calculado e é **movida** no deal da E.
- **CM:** a S nasce a `CM_RESERVA_PTS` (4.945 pts) do preço da limite (O11: maior excursão adversa de 815 trades 2022–2026 + 20%, nunca teria disparado nos testes) e é movida para o "stop que aperta" quando ele nascer.
- **Gap que atravessa a E e a S de uma vez:** para a S disparar o preço precisa passar pelo nível da E, que nesse ponto é negociável. Executam as duas e a ficha fica 0, resultado aceito. Se a S executar primeiro, a ficha fica por instantes com o sinal oposto ao da E viva: isso é **transitório da entrada**, não ficha trocada; o D1 não corrige, nada é enviado para o robô e a E executa em seguida (ficha 0). Vale igual para o C1 enquanto a E a mercado está sem desfecho. Só se a E sumir sem deal (ou for provada não executada) com a ficha ainda invertida a seção 8 corrige.
- O atraso E aceita → S viva é logado em toda entrada.
- **Mover** = `OrderModify` da S existente, nunca cancelar e recriar. O nível é o que o robô pede, inclusive quando a regra afrouxa (trailing do C1). Nível 0 vindo de um módulo é ignorado com ERRO. `OrderModify` recusado: a S antiga continua e a retentativa segue 4.5.
- **Nível atravessado** (checado pelo módulo com a fonte de preço do avulso; piso `max(1 tick, SYMBOL_TRADE_STOPS_LEVEL)`, itens 1.25, 4.30) → saída 5.2.
- **Recriar:** a cada reconciliação, E viva ou ficha ±1 (não trocada) sem S viva há mais de 2 s → S de novo, no nível da memória; sem ele, pela regra do robô; sem regra, `STOP_EMERGENCIA_PTS` do preço da ficha (ALERTA). Cobre S cancelada pela corretora, pelo dono ou disparada sem execução (se o nível já foi atravessado, 5.2).
- **Cancelar:** só em 5.2 passo 4, depois da E confirmada cancelada (5.1), no OCO (5.4) e como S em excesso (invariante).

### 5.4 OCO

Deal de S ou A que leva a ficha a zero → cancela as demais ordens do robô (5.1) antes de qualquer outra ação. S executada antes da E (transitório, 5.3) não dispara OCO: a E fica. Com o EA fora não há OCO (Princípio 4); a recuperação cancela as irmãs (10, passo 7).

## 6. Reconciliação

A cada 1 s, e a cada deal: lê a líquida (`PositionSelect` falso com erro = leitura descartada, item 1.6); `Ficha_Recalcula()` com `HistorySelect(último instante − 60 s, agora)`, deduplicando por ticket; desfechos (4.4); invariantes e órfãs (2); recriação de S (5.3); OCO (5.4). **Releitura completa da janela** ao reconectar, quando a cruzada não fecha, quando chega deal com hora anterior à última processada, e a cada 10 min. Nenhum módulo chama `HistorySelect*`.

Cruzada sem fechar com leitura confiável → nenhum envio (4.3), releitura a cada 10 s, ALERTA após 30 s e a cada 5 min.

## 7. Zeragem manual e deal externo

### 7.1 Classificação

Deal com magic que não é de robô (0 = manual, mesa, zeragem compulsória P11, stop-out, SL/TP do dono na líquida) é **externo**. No instante em que é visto:
1. **Compensa a externa existente** de sinal oposto (o dono fechando a posição manual dele): só altera a externa.
2. O que sobra e **aumenta** \|líquida\| → externa; fichas intactas; AVISO.
3. O que sobra e **reduz** a líquida abaixo de Σ fichas → **zeragem manual**:
   - absorção nas fichas do lado reduzido, na ordem fixa GB, CM, DM, RE, C1; cada ficha absorvida vai a 0 com o preço do deal externo, log `ABSORVIDA`. É função do histórico: a recuperação sem memória chega ao mesmo resultado;
   - cancela, nesta ordem, as A, as E de todos os robôs, e depois de confirmadas as S dessas E e as S das fichas absorvidas (5.1) — tudo que aumentaria a exposição ao executar;
   - bloqueio de entradas que exige o botão; ALERTA.

### 7.2 Bloqueio de entradas e botão

Bloqueio = nenhuma E nova. Ao entrar: as E vivas são canceladas (com as S delas, 5.1) e os módulos recebem `ENTRADA_CANCELADA` (item 1.9). Nunca são barrados: S, cancelamentos, saídas por regra, zeragens, corte e correções.

Causas: zeragem manual (7.1), cruzada que não fecha em 10 pregões (3.2), ordem sem desfecho há 10 min (4.4), correção repetida (8). Todas saem pelo **botão** `OBJ_BUTTON` "Desbloquear" (visível só com bloqueio; dois cliques em até 3 s; `OnChartEvent`): grava os tickets causadores como **reconhecidos** na memória, libera e loga `DESBLOQUEIO`. A recuperação só bloqueia de novo por evento não reconhecido. Depois do botão nenhum robô reenvia entrada cancelada.

## 8. Ficha trocada ou duplicada

As únicas correções automáticas.
- **Trocada** (duas saídas da mesma ficha: S + A, S + X, ficha de ±1 para ∓1; ou ficha invertida sem E viva, 5.3): módulo suspenso; correção C pelo 5.2 com o magic do robô, até 0.
- **Duplicada** (\|ficha\| = 2): correção C de volume 1 com o magic do robô, **sem cancelar a S** (com volume 1, ela passa a cobrir a ficha exata; se executar junto, a ficha vai a 0, nunca inverte).

Só no contínuo; fora dele, a ficha ganha S (5.3) e a correção é agendada para `negociacao_inicio`. No máximo uma correção por ficha a cada 10 min; a segunda vira bloqueio com botão, sem correção (item 1.13). ALERTA com os tickets.

## 9. Horários e corte (D2)

### 9.1 Relógio e grade

- O maestro é o **único dono das saídas por horário**. O código de zeragem e de "posição de outro dia" de cada módulo (GB L357, CM L720-724, DM L476/L490, RE L1019, C1 L591-594) é desligado por uma flag do módulo, sem apagar.
- Relógio: `TimeTradeServer()`, avaliado no timer mesmo sem tick (item 2.8). AVISO no `PRONTO` se `TimeTradeServer() − TimeGMT()` ≠ −3 h (P22).
- `F` = fim do contínuo da data (`negociacao_fim` da grade; no vencimento do contrato do gráfico, `vencimento_fim`), nunca a sessão da MT5 (item 5.35). Data sem linha: 17:55, AVISO.
- **Corte = F − 5 min**: 18:20 nos dias de contínuo até 18:25; 17:50 nos de 17:55.
- `Tick()` dos robôs só de `negociacao_inicio` ao corte.

### 9.2 Zeragem de cada robô

Zeragem = min(horário do robô, corte), pelo 5.2, pelo timer.

| Robô | Avulso | Dias de 18:25 | Dias de 17:55 |
|---|---|---|---|
| GB | 18:20 | 18:20 | 17:50 |
| CM | 18:24 | **18:20** (D2) | **17:50** (D2) |
| DM | sessão − 5 min | 18:20 | 17:50 |
| RE | 17:00 | 17:00 | 17:00 |
| C1 | 17:50 | 17:50 | 17:50 |

### 9.3 Corte e ficha que atravessou a noite

**No corte:** (1) cancela todas as E e A dos robôs e, confirmadas, as S dessas E (5.1); (2) toda ficha ainda aberta → 5.2, na ordem fixa, ALERTA (a zeragem do robô falhou); trocada ou duplicada → seção 8; (3) cada S é cancelada quando a saída da ficha dela executa; (4) saída recusada → S fica, retenta a cada 5 s até F; (5) robô com ordem sem desfecho → a saída espera a prova (D1), ALERTA a cada minuto; a S protege até F. Depois de F nenhuma saída é enviada.

**Ficha que atravessou a noite** (só existe com o EA fora no corte, ou saídas recusadas até F). A S dela venceu com o pregão: a ficha passa a noite e o leilão de abertura **sem stop**, risco aceito pelo dono (B10, seção 13). Na volta:
1. **Pré-abertura, EA vivo:** assim que a corretora aceitar ordens, cria uma S DAY nova para a ficha (nível da memória; sem ele, regra do robô; sem regra, `STOP_EMERGENCIA_PTS` do preço da ficha), log `NOITE` com o nível. Recusada → retenta a cada 5 s. Nível já atravessado pelo preço (gap) → nenhuma S; a zeragem do passo 2 resolve. É o caso "ficha ≠ 0 sem S" da 5.3 e passa pelo D1 como qualquer S: o robô continua com uma operação só (ficha + S).
2. **Primeiro momento de contínuo** — agora, se o EA volta durante o contínuo; senão em `negociacao_inicio`: zera pelo 5.2; a S é cancelada depois da saída executada. Se a S disparou no leilão (P13), a ficha já é 0 e não há o que zerar.

O robô dono fica sem `Tick()` até a ficha zerar. Fora do contínuo só se criam, movem e cancelam S e se cancelam E e A (com as S das E). Corte perdido (EA volta entre o corte e F) → zera agora.

**Rolagem:** o dono troca o gráfico para o contrato vigente; a memória é por símbolo e começa limpa.

## 10. Memória e recuperação na partida

### 10.1 Memória

`MQL5/Files/WinMaestro/<servidor>_<conta>_<símbolo>/estado.txt` (+ `.bak`), formato `chave=valor`. No Testador, `MQL5/Files/WinMaestro_teste/`, apagada no início de cada teste.
- **Guarda:** data do pregão; último ticket e instante de deal processados; heartbeat; registro de trânsito (4.1); `seq` de cada robô; bloqueios ativos e tickets reconhecidos; externa de origem desconhecida; por robô, níveis de stop e alvo pedidos e as variáveis do Apêndice A. **Instantes, nunca contagens.**
- **Grava** antes de cada `OrderSend`, a cada deal, a cada mudança de nível, bloqueio ou botão, e no `OnDeinit`; o resto no máximo 1× por segundo.
- **Como:** escreve `estado.tmp` inteiro com última linha `fim=<checksum>`, fecha, copia `.txt` → `.bak`, move `.tmp` → `.txt`. Ausente, vazio, sem `fim=` ou checksum errado → `.bak`; os dois ruins → memória perdida, ALERTA.
- Outra conta ou servidor → ignorada. Outro pregão → mantém trânsito não resolvido, bloqueios, externa desconhecida e o estado das fichas abertas.

### 10.2 Sequência de partida

Toda partida (primeira do dia, mudança de input, volta de queda) executa estes passos **antes de qualquer atividade**: nenhum `Tick()` e nenhuma entrada antes do passo 11. Cada passo loga início e fim; repetir um passo não reenvia o que já está vivo. O `OnInit` só reinicializa e liga o timer; a sequência anda pelo timer.

1. **Trava** (10.3). Falhou → `ExpertRemove`, sem tocar em nada.
2. **Conexão:** espera leitura confiável e tick válido; log a cada 30 s, ALERTA após 5 min. Nenhuma ordem.
3. **Ambiente:** conta NETTING; símbolo negociável; valor e tamanho do tick ≠ 0 (repete por 60 s); AVISO se houver ordem ou posição de magic de robô em outro símbolo (O16). Nada aqui depende de saldo (B7). Falha sem ficha nem ordem de robô → para com ALERTA; com elas → modo **PROTEGENDO** (só S, cancelamentos, corte; repete a checagem a cada 30 s).
4. **Histórico:** janela até a cruzada fechar (3.2), prazo 60 s; esgotado → bloqueio com botão e segue.
5. **Memória** (10.1); perdida → linhas `ORDEM` do log do dia para o trânsito.
6. **Reconstrói:** fichas, desfecho de cada ordem do trânsito (4.4), externas e absorção (7.1), bloqueios de eventos não reconhecidos.
7. **Órfãs, antes de qualquer outra ordem:** cancela S sem ficha e sem E viva (irmã de ficha que zerou, ou S de E que venceu com o EA fora), A sem ficha, A de ficha trocada, E excedentes (2).
8. **Proteção:** toda E viva com a sua S (sem S possível → cancela a E); toda ficha ≠ 0 com uma S DAY (ficha da noite: assim que a corretora aceitar ordens, 9.3): nível da memória; sem memória, pela regra do robô (Apêndice A); sem regra, nível da S viva; sem S, `STOP_EMERGENCIA_PTS` (ALERTA). Alvo do RE no nível da memória, salvo ficha trocada ou duplicada.
9. **Pendências:** trocada e duplicada (8); ficha da noite e corte perdido (9.3): executa se no contínuo, senão agenda.
10. **Módulos:** `Init()` de cada robô com o estado restaurado e o recálculo dele (Apêndice A). Decisão de entrada cujo momento passou com o EA fora = `DECISAO PERDIDA` (itens 2.1, 2.6, 4.17).
11. **PRONTO:** grava a memória; log `PRONTO` com as operações do dia por robô reconstruídas dos deals, marcando as feitas com o EA fora, e cada evento perdido com a hora real do deal.

### 10.3 Trava (D3)

Impede o maestro em dois gráficos do mesmo terminal. Variável global `WinMaestro.lock.<conta>.<símbolo>` tomada com `GlobalVariableSetOnCondition(nome, token, 0)`, `token` = `(uint)(ChartID() ^ (ChartID() >> 32))` (1 se der 0; cabe exato num `double`); heartbeat `WinMaestro.hb.<conta>.<símbolo>` = `TimeLocal()` a cada 1 s. Trava de outro gráfico com heartbeat < 10 s → recusa (`Alert`, `ExpertRemove`); ≥ 10 s → toma, AVISO. **`g_iniciou`** fica verdadeira só depois de tomar a trava; instância recusada não cancela ordem, não grava memória e não libera trava. No Testador a trava é pulada (P16).

### 10.4 `OnDeinit`

Loga `FIM` e o `reason`. Com `g_iniciou` falsa, só isso. Com `g_iniciou` verdadeira e `reason` fora de {`PARAMETERS`, `CHARTCHANGE`, `TEMPLATE`}: grava a memória e libera a trava. Não cancela nada nem fecha posição: toda E já tem a sua S, e cancelar a E sem poder confirmar deixaria a S sozinha.

## 11. Logs

- **Onde:** diário do MT5 e `logs/AAAA-MM-DD.log` (uma linha por evento, `FileFlush` a cada linha; é também fonte da recuperação); `logs/AAAA-MM-DD_trans.log` com uma linha bruta por `OnTradeTransaction` do símbolo (tipo, ordem, deal, estado, preço, volume, magic, `request_id`).
- **Formato:** `HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe | [tick HH:MM:SS.mmm loc HH:MM:SS]`. Hora = `TimeTradeServer()`. `NIVEL` ∈ {INFO, AVISO, ALERTA, ERRO}; `ROBO` ∈ {GB, CM, DM, RE, C1, MAESTRO}.
- **Linha de ordem:** ticket da ordem e do deal, `request_id`, `retcode`/`retcode_external`, comentário, preço pedido e executado lado a lado (item 4.15), líquida antes → depois.
- **Anti-spam por objeto** (ticket ou ficha, item 1.12): a mesma condição é logada ao começar, a cada 5 min com contador e ao terminar.
- **ALERTA** dispara também `Alert()`. Não há push (O3).
- **Painel** (O7): `Comment()` com estado, ficha e S de cada robô, líquida, externa, bloqueio e hora do corte; só leitura.
- **Resumo do dia** (O19), depois do corte: R$ por robô; total pelas fichas × `DEAL_PROFIT` + custos e contratos negociados × `ENTROU`/`SAIU`/`ABSORVIDA` do log, ALERTA se diferirem (item 1.21).
- **Eventos:** `INICIO`, `TRAVA`, `AMBIENTE`, `HISTORICO`, `MEMORIA`, `RECUPERA`, `PROTEGENDO`, `PRONTO`, `SINAL`, `ORDEM`, `DESFECHO` (com a prova), `ESTADO` (aberto, com o motivo), `SEGUNDA_ENTRADA`, `AUTONEG`, `ENTROU`, `STOP` (criado, movido, recriado), `ALVO`, `SAIDA`, `SAIU`, `CANCELA`, `EXECUTOU_ANTES`, `ORFA`, `ZERAGEM`, `CORTE`, `NOITE`, `TROCADA`, `DUPLICADA`, `CORRECAO`, `EXTERNA`, `ABSORVIDA`, `BLOQUEIO`, `DESBLOQUEIO`, `DECISAO PERDIDA`, `AJUSTE`, `RESUMO`, `FIM`.

```
10:00:00.140 | INFO   | CM | ORDEM   | E sell limit 1 @176855 ord #48211 req 37 rc 10008/0 MAE|CM|E|0042
10:03:12.501 | INFO   | CM | ENTROU  | vendido 1; pedido 176855 exec 176855 deal #9912; liquida +1 -> 0
12:00:00.560 | INFO   | CM | SAIU    | EMA; compra 1 deal #9987 exec 176210; +129,00; liquida 0 -> +1
09:00:02.300 | ALERTA | MAESTRO | RECUPERA | EA fora 09:41-10:12; DM: S executou 09:58 @190165 (-68,00)
```

## 12. Testes antes do dinheiro real

**Equivalência** (Testador, WIN$N, ticks reais; cache com `last` em ≥ 99% dos ticks, itens 5.33, 6.54; valor do tick lido do símbolo, item 6.55):
1. Cada robô sozinho no maestro × EA avulso: **entradas 100% iguais em hora e lado**; saídas no mesmo tick, salvo as diferenças abaixo; resultado ≤ max(2%; R$1,00 × trades).
2. Os 5 ligados × replay T6 (`combinacoes/z9_netting/t6_maestro`): resultado por robô igual ao do teste 1 do mesmo robô.

Diferenças permitidas, listadas trade a trade com a causa: CM zerado às 18:20 (D2); stop do DM como S no servidor (B8); teto do DM por `DM_CAPITAL` fixo (B9); zeragem pelo timer em vez do primeiro tick; ordem fixa (só no teste 2); stop como S viva desde a E em vez de SL anexado no fill (gap que atravessa E e S no mesmo tick: ficha 0, contar esses trades); reserva do CM (nunca dispara no período: qualquer disparo é defeito). Qualquer outra diferença é defeito. Relatório: ordens recusadas (> 0 = linha censurada), pior trade em múltiplos do stop (item 6.56).

**Testes unitários** (O15): `Corretora.mqh` tem uma segunda implementação, falsa, com respostas roteirizadas (DONE sem deal, timeout com ticket 0, recusa, histórico atrasado, S executando antes da E), compilada só no EA de teste `WinMaestro_Teste.mq5`, nunca no `.ex5` de produção.

**Falhas** (conta demo, pregão real; cada linha precisa de evidência no log antes do real, item 4.28):
1. Matar o MT5 com 2 robôs posicionados; deixar o stop de um executar; reabrir: S no servidor, irmã cancelada no passo 7, `RECUPERA` com a hora real.
2. Stop e alvo do RE executando com o EA fora: trocada corrigida no passo 9.
3. Saída a mercado com a internet caindo logo depois (as duas versões: executou / não chegou): S viva o tempo todo, nada duplicado (cenário b).
4. Apagar `estado.txt`; apagar também o `.bak`: `.bak` usado; depois memória perdida com nenhuma ficha sem S.
5. Zerar a líquida na mão com 2 robôs posicionados e ordens vivas: absorção, cancelamentos, bloqueio; botão libera; reiniciar não rebloqueia.
6. Abrir e fechar posição manual: externa volta a 0, fichas intactas, sem bloqueio.
7. Maestro em dois gráficos do mesmo terminal: o segundo recusa; o primeiro intacto.
8. Trocar o timeframe com robôs posicionados: nada cancelado, nada duplicado.
9. EA fechado 18:15 e aberto 18:22 com ficha: zera na hora. EA fechado das 17:00 às 08:50: ficha passou a noite sem S; S DAY nova criada na pré-abertura (`NOITE`); ficha zerada no primeiro contínuo.
10. Forçar a falha da zeragem de um robô: o corte zera em F − 5 min.
11. Entrada executada duas vezes (forçada no Testador por ordem manual com o magic): correção de 1, S mantida.
12. Dia de 17:55: todos zerados até 17:50.
13. Toda entrada nasce com a S: E limite viva com a S ao lado; E cancelada → S cancelada depois; C1 com a S antes da E; S recusada ao lado da E → E cancelada; segunda entrada do mesmo robô recusada (`SEGUNDA_ENTRADA`).
14. Matar o MT5 com uma E viva que enche fora: ficha protegida pela S desde o início; com uma E que vence fora: S cancelada no passo 7.

**Escada no real** (a demo não mede fila nem stop na B3, item 4.7): 1 robô por 5 pregões → 2 robôs que podem ficar em lados opostos (CM e RE) por 5 pregões → os 5. Avança com zero divergência não explicada e extrato igual ao log em contratos e preço. Antes do degrau 1: P1–P6, P15, P18, P22 respondidas.

## 13. Pior caso (informativo)

Referências no WIN$N, 2022 a 2026: amplitude diária p99 = 5.630 pts (R$1.126 por contrato; mediana 1.865, máximo 8.320); gap de abertura \|abertura − fechamento anterior\| mediana 340, p95 1.517, p99 2.978 pts (máximo bruto de 17.775 é salto de rolagem do contínuo, não gap).

| Caso | Contratos sem stop | Perda a 5.630 pts |
|---|---|---|
| Princípio 4 (a): S e A do RE executam com o EA fora | 1 (RE) | R$1.126 |
| Princípio 4 (b): E vence com o EA fora e a S sozinha dispara antes da volta (GB no mesmo dia; CM, DM, RE só com o EA fora também no pregão seguinte) | até 4 (GB, CM, DM, RE; não soma com (a) para o RE) | até R$4.504 |
| Princípio 4 (c): ficha aberta no corte com o EA fora passa a noite e o leilão de abertura sem stop | até 5 (uma por robô) | gap de abertura p99 = 2.978 pts (2,22%) = R$596 por contrato, até R$2.980 a 5; cauda já observada: +9,2% na abertura de 05/10/2026 (≈ 4× o p99) |
| CM com a S na reserva (não é exceção: tem stop) | — | R$989 por contrato no pior disparo |

Com o EA no ar, nenhum robô fica sem S além dos instantes entre a E aceita e a S aceita. Nota: margem do pior estado (5 contratos × R$100 × 2, P8) + R$4.504 = R$5.504; um depósito de R$7.000 cobre os dois. É só referência: nada no EA depende de saldo (B7).

## 14. Fora do escopo

Combinar sinais ou priorizar robôs; limites de perda, de operações ou de horário não pedidos; hedging; mais de uma instância na mesma conta e símbolo (D3); lote > 1; alarme do item 1.24 (preço médio da líquida fora da grade é normal com várias fichas).

## Apêndice A — o que muda em cada módulo

Comum: os 3 bloqueios por posição de outro robô saem; os fechamentos da líquida viram `Ficha_Fecha`; `PositionModify` vira `Ficha_DefineStop`; SL anexado vira S enviada com a E (5.3); zeragem e "outro dia" do módulo desligados por flag; `Tick()` só de `negociacao_inicio` ao corte; gate de vela nova persistido como instante; eventos do maestro = não rearmar.

| Robô | Persistir | Recálculo na partida | Particularidade |
|---|---|---|---|
| GB (M5) | `g_decidido`, `g_exp`, `g_be_feito`, data | stop = preço da ficha ∓ `StopPts` | E `SPECIFIED` 09:05–09:35; S 1.200 pts; BE = `OrderModify` da S |
| CM (H2) | `g_ultima_barra`, `a_favor`, nível do stop que aperta, hora e lado da entrada | stop que aperta das barras desde a hora da ficha; avalia a última H2 fechada | S de reserva a 4.945 pts desde a E, movida ao stop que aperta (O11); zeragem 18:20/17:50 (D2) |
| DM (M1) | `g_stopNivel`, `g_distStop`, `g_stopAjustado`, `g_decidiu`, `g_dia`, `g_ordemHora`, `g_ordemPreco` | sem memória: `g_distStop` da decisão das 10:30 refeita das barras | stop = S no servidor em `g_stopNivel`, pré-calculada na E e movida no fill (B8); teto de risco = 10% de `DM_CAPITAL` (B9) no lugar de `ACCOUNT_BALANCE` (L396) |
| RE (M15) | entrada pendente (hora, lado, meio, stop e alvo originais), posição (preço, largura, fração do alvo, hora da vela do fill), retângulo vivo | barras esperando e em posição a partir dos instantes; A movido ao passo correspondente | S pré-calculada na E e reancorada no fill; A = limite que se aproxima (`OrderModify`), DAY; não cancela a E no próprio `Deinit`; `TesterStop` (L1007) desligado |
| C1 (H1) | `g_ultima_barra`, nível do stop | pico, esticada e stop da última H1 fechada desde a hora da ficha | entrada a mercado com a S enviada antes; trailing pode afrouxar (L536-550), o maestro move igual; checagem bid/ask, 1 tick |

## Apêndice B — decisões

### Tomadas pelo dono em 2026-10-07

- **D1.** Antes de toda ordem, conferir posição líquida, ordens vivas e histórico (com o log se preciso); só envia se o estado fecha; nada reenviado por inferência de tempo (4.3, 4.4).
- **D2.** Corte global = fim do contínuo − 5 min; todos zerados até lá; CM limitado ao corte (9).
- **D3.** Uma instância só, no PC; só a trava contra dois gráficos no mesmo terminal (10.3).
- **Inputs.** Os 5 liga/desliga no topo (1).
- **B1 e B10.** Toda S, E e A com validade do dia (DAY; GB `SPECIFIED`). A S sozinha de uma E vencida dura no máximo até o fim do pregão. Ficha aberta no corte com o EA fora passa a noite e o leilão de abertura sem stop; na volta, S DAY nova na pré-abertura e zeragem no primeiro contínuo (9.3).
- **B3.** WinSeletor e EAs avulsos aposentados; checklist antes da primeira partida: nenhum `.ex5` deles na pasta Experts nem em gráfico aberto (no lugar da detecção automática, O12).
- **B4.** Toda entrada nasce com o stop na corretora: S junto com a E limite, antes da E a mercado; cancelamento da E antes da S; reancoragem no fill; CM com reserva obrigatória (5.3).
- **B5.** RE com S e A vivos com o EA fora: aceito, com a correção da seção 8.
- **B6.** Saída primeiro; a S só é cancelada depois de a saída executar (5.2).
- **B7.** Nenhuma recusa, bloqueio ou aviso de partida ligado a saldo ou capital mínimo; o depósito é só nota (13).
- **B8.** Stop do DM como S no servidor no próprio `g_stopNivel` (Apêndice A).
- **B9.** Teto de risco do DM sobre `DM_CAPITAL` fixo de R$1.000; é regra do robô, não trava (Apêndice A).
- **Opcionais incluídos:** O2 só a metade "não enviar E/A que cruze com limite própria" (4.3); O4 trocado por "uma operação por vez por robô" (2); O6 condicional a P6/P18 (4.4); O7 painel (11); O11 reserva do CM, obrigatória (5.3); O15 corretora falsa (12); O16 aviso de outros símbolos na partida (10.2); O19 resumo do dia (11).
- **Opcionais excluídos:** Apêndice D.

### Aguardam a corretora

Só P1: confirmar que a S DAY é aceita no WIN e continua listada com o terminal fechado.

## Apêndice C — rastreabilidade das revisões

| Lacunas | Onde |
|---|---|
| Rev. 1 C1, N1, N2, T1, T2 (trânsito, DONE sem deal, reenvio duplicado, ordem sem desfecho) | corpo 2 (uma operação por vez), 4.1–4.4; D1 |
| Rev. 1 C2, A10, N10, N12, N23 (cancelamento confirmado, retentativas, avisos ao módulo) | corpo 3.3, 4.2, 4.5, 5.1 |
| Rev. 1 C3, N5, N6 (intervenção externa, botão) | corpo 7; O13 excluído |
| Rev. 1 C4, N20 (janela fill→stop, pior caso) | Princípio 4; 5.3 (S nasce com a E); 13; B4, B10 |
| Rev. 1 C5, N11, T6, R9 (sem OCO, ficha trocada, saída × S) | corpo 5.2, 5.4, 8, 10.2 passos 7–9; B5, B6 |
| Rev. 1 C6, N3, N18, T3, T4, trava em `double` | D3; corpo 10.3, 10.4; B3 (checklist no lugar de O12) |
| Rev. 1 C7 (autonegociação) | corpo 4.3 item 5 (O2) |
| Rev. 1 C8, A7, N9 (margem, stop que abre para a conta) | B7; O1 excluído |
| Rev. 1 C9, N4, T5, T7 (ficha da noite, R4 eterno, regra única) | D2; corpo 3.2, 9.3, 10.2 passos 4 e 8; B10 |
| Rev. 1 C10, N7, N24 (divergência transitória, cruzada) | corpo 3.2, 4.4 (O6 condicional), 6; O14 excluído |
| Rev. 1 C11 (stop disparado sem execução) | corpo 5.3 (recriar); O5 excluído |
| Rev. 1 A1, N14 (relógio, dono da zeragem) | corpo 9.1, 9.2 |
| Rev. 1 A2–A6, M1–M3, M5, M7, M8, B1–B5, N8, N13, N15–N17, N25–N27 (papel, estado, memória, órfãs, inputs, preenchimento, mover stop, `seq`, lote) | corpo 1, 2, 3, 5.3, 9.3, 10, 14; Apêndice A |
| Rev. 1 A8, A9, N21, N22 (equivalência, testes, camada de corretora) | corpo 1 (porta única), 12 (O15) |
| Rev. 1 A11 (DM em dois caminhos) | B8; O9 excluído |
| Rev. 1 M4, N19 (logs, push) | corpo 11 (O7, O19); O3 excluído |
| Rev. 2 N10/N27 (notas da rev. 3), `TesterStop` do RE | corpo 1, 3.3; Apêndice A |
| Afirmações erradas da rev. 1 (stop "no servidor com o terminal desligado", SL/TP da líquida, comentário identifica a ordem, `RETURN` exigido) | P1, P3, P15; Princípio 7; corpo 2 |

## Apêndice D — itens deixados de fora (decisão do dono, 2026-10-07)

- **O1. Portão de margem:** a corretora recusa o que não cabe; nenhuma trava ligada a saldo (B7).
- **O3. Push (`SendNotification`):** só `Alert()` e log.
- **O5. Stop-limit e limite agressiva em leilão:** a saída recusada é retentada a mercado a cada 5 s; reavaliar depois de P1 e P13.
- **O8. Rotação de log:** um arquivo por dia, nada é apagado.
- **O9. Reserva do DM 20 ticks além:** o DM usa só a S no nível (B8).
- **O10. Saldo virtual do DM:** teto sobre R$1.000 fixos (B9).
- **O12. Detecção de EA avulso esquecido:** checklist (B3).
- **O13. Absorção proporcional:** ordem fixa GB, CM, DM, RE, C1 (7.1).
- **O14. Cobertura pela conta:** robô sem prova fica pausado com a S dele (4.4).
- **O17. Detecção de SL/TP na líquida:** se executar, é zeragem manual (7.1).
- **O18. Entrada atrasada reenviável:** sempre `DECISAO PERDIDA` (10.2 passo 10).

## Apêndice E — perguntas à corretora

- P1. `SELL_STOP`/`BUY_STOP` DAY no WIN: aceita? Fica listada com o terminal fechado? A partir de que hora da pré-abertura é aceita? Fica na Rico ou vai à B3? Vira mercado ou limite?
- P2. Deal de stop ou limite pendente carrega `DEAL_MAGIC` e comentário da ordem? Qual `DEAL_REASON`?
- P3. `ORDER_COMMENT` sobrevive igual na ordem, no histórico e após `OrderModify`? Quantos caracteres?
- P4. `OrderModify` de stop pendente mantém o ticket?
- P5. `OrderDelete` de ordem que acabou de disparar: retcode, estado no histórico, tempo até o desfecho?
- P6. Atraso entre o retorno do `OrderSend` a mercado e o deal no histórico (p50 e máximo em 50 envios); já houve `DONE` com `deal = 0`?
- P7. Stop que leva a líquida de −1 a −2 passa por checagem de margem? **(real)**
- P8. Pendente bloqueia margem? Qual a margem de day trade do WIN na Rico?
- P9. `ACCOUNT_BALANCE` e margem batem com o extrato?
- P10. Zeragem manual pelo terminal e pela mesa: qual `DEAL_REASON` e magic? **(real)**
- P11. A Rico faz zeragem compulsória de day trade no WIN? A que horas, e cancela as pendentes? **(real)**
- P12. Existe Self-Trade Prevention na conta? **(real)**
- P13. Stop disparado em leilão vira o quê? Mercado enviado em leilão: qual retcode? **(real)**
- P14. Posição que atravessa a noite gera deals de ajuste ou muda `POSITION_PRICE_OPEN`?
- P15. `SYMBOL_FILLING_MODE` e `SYMBOL_EXPIRATION_MODE` do WIN vigente? Mercado com `RETURN` é aceito?
- P16. `GlobalVariableSetOnCondition` funciona como trava entre dois gráficos do mesmo terminal?
- P17. Em `REASON_PARAMETERS` e `REASON_CHARTCHANGE` as variáveis globais do EA sobrevivem?
- P18. Após 2 min sem internet, o histórico volta completo? Em quanto tempo Σ deals = líquida?
- P19. `TimeTradeServer()` anda com o feed parado?
- P20. Limites de ordens pendentes e de contratos de WIN por cliente na Rico?
- P21. A demo da Rico casa contra o livro real?
- P22. O relógio do servidor da Rico está em Brasília?

## Cenários de referência

**(a) CM e RE comprados, cada um com a S viva desde a entrada; MT5 morto às 14:00; a S do RE executa 14:20; o A do RE enche 15:10; volta 15:30.** A ficha do RE fica −1 (trocada), líquida 0 desde 15:10; o CM nunca ficou sem stop (reserva ou stop que aperta). Na volta: passos 1–6 reconstroem CM +1 e RE trocada; passo 8 confere a S do CM e não recoloca alvo no RE; passo 9 envia C de compra 1 com o magic do RE no contínuo, ficha → 0. Resposta única e segura.

**(b) Saída a mercado do C1 volta `TIMEOUT` sem ticket; a internet cai 90 s.** A S do C1 nunca foi cancelada (5.2). Desconectado nada se resolve e nada é enviado. Na volta, releitura completa: se executou, o deal aparece, a ficha vai a 0 e só então a S é cancelada; se não chegou, com leitura confiável e a cruzada fechando a ordem é "não executada" e o C1 manda a saída de novo pela regra dele, com a S viva. Sem prova, o C1 fica pausado com a S e o dono é alertado. Resposta única e segura.

**(c) O dono zera tudo na mão às 11:00 com GB e DM posicionados e ordens vivas.** Venda manual de 2 (magic 0) reduz abaixo de Σ fichas → absorção GB, depois DM. Cancela as A e as E; confirmadas, cancela as S dessas E e as S das fichas absorvidas; bloqueio de entradas. O botão libera; reiniciar não rebloqueia (tickets reconhecidos); GB e DM não reentram no dia (`g_decidido`, `g_decidiu`). Resposta única e segura.

**(d) PC desligado desde 17:00 de ontem com o DM posicionado; gap contra na abertura.** A S DAY venceu ontem: a ficha passou a noite e o leilão de abertura sem stop (risco aceito, B10; p99 do gap R$596 por contrato). Partida antes das 09:00: passos 1–7; passo 8 cria a S DAY nova assim que a corretora aceitar ordens (nenhuma, se o gap já atravessou o nível); passo 9 agenda a saída para `negociacao_inicio`; nenhum `Tick()` fora do contínuo. Primeiro momento de contínuo: saída a mercado; a S, se existir, só é cancelada depois. Resposta única; segura dentro do risco aceito.

**(e) Maestro no PC e na VPS ao mesmo tempo.** Fora do escopo (D3). Coberto: dois gráficos no mesmo terminal — o segundo falha na trava (10.3), sai com `g_iniciou` falsa e não toca em ordem, memória nem trava do primeiro.
