# WinMaestro — especificação

Versão 0.5 (2026-10-07). EA MQL5 único para o WIN na B3, conta NETTING na Rico, dinheiro real. Aposenta o WinSeletor v1.00.

Convenções:
- "item X.Y" aponta para `LICOES_DE_PRODUCAO.md`; "P n" aponta para a pergunta n do Apêndice E; "O n" aponta para o item opcional n do Apêndice D (decisão do dono); D1–D3 são decisões já tomadas (Apêndice B).
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
4. **Todo robô posicionado tem a sua ordem stop (S) na corretora.** Exceções aceitas (a MT5 em netting não tem OCO nem OTO): (a) entre o preenchimento de uma entrada e o registro da S, e durante todo o tempo com o EA fora; (b) com o EA fora, S e alvo do mesmo robô podem executar os dois; (c) o CM não tem stop inicial pela regra dele (O11). Pior caso: Apêndice B, B4.
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

**Constantes:** `PRAZO_CONFIRMACAO` 5 s (consulta a cada 250 ms); `ALERTA_SEM_DESFECHO` 30 s; `PRAZO_SEM_DESFECHO` 10 min; `IDADE_PROVA` 30 s; `RETENTA` 5 s; `STOP_EMERGENCIA_PTS` 1.200; `DM_CAPITAL` R$1.000; `MARGEM_CORTE` 5 min.

## 2. Papel das ordens

| Papel | Ordem | Validade |
|---|---|---|
| E entrada | limite (C1: mercado), magic do robô | GB `SPECIFIED` até `g_exp` (recusada → DAY e cancelamento pelo EA em `g_exp`); CM, DM, RE DAY (B2) |
| S stop | `SELL_STOP` para ficha comprada, `BUY_STOP` para vendida, volume 1 | **GTC** (B1) |
| A alvo (só RE no padrão) | limite oposta, volume 1 | DAY |
| X saída / C correção | mercado oposta, volume = \|ficha\| | — |

Preenchimento: limite `ORDER_FILLING_RETURN`, desvio 0; mercado `RETURN` se `SYMBOL_FILLING_MODE` permitir, senão `IOC` (P15). O SL/TP da posição líquida nunca é usado.

**Comentário:** `MAE|<robo>|<papel>|<seq>` (ex.: `MAE|CM|E|0042`), `seq` por robô e por pregão, gravado na memória; memória perdida → maior `seq` do dia no histórico + 1. O comentário serve para achar ordem sem ticket (4.3) e para o log; o papel é decidido por (magic, tipo, lado em relação à ficha), nunca pelo comentário (P3).

**Invariantes por robô** (conferidos a cada reconciliação): no máximo uma S, só com ficha ≠ 0, do lado oposto; no máximo uma A, só com ficha ≠ 0; E só com ficha 0, no máximo uma. Ordem de magic de robô fora disso, com mais de 5 s de vida e sem ordem do robô sem desfecho, é **órfã**: cancelada (5.1), log `ORFA`. Entre duas S fica a de nível mais protetor. Ordem de magic desconhecido nunca é tocada.

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
4. a ordem pedida é coerente com a ficha e as ordens vivas de r (seção 2: S só com ficha ≠ 0 e sem S viva; E só com ficha 0 e sem E viva; X com volume = \|ficha\|).

Fecha → envia. Não fecha → não envia (`BLOQUEADA estado aberto`), loga o que não fecha e tenta explicar, nesta ordem: releitura completa do histórico de deals e de ordens; busca de cada ordem sem desfecho por ticket, `request_id` e comentário; com a memória perdida, as linhas `ORDEM` do log do dia. Com estado aberto as S já vivas continuam no servidor protegendo.

### 4.4 Desfecho de uma ordem

`DONE`/`PLACED` sem deal, `OrderSend` falso e retcode de transporte com ticket 0 significam **"não sei"**, nunca "não executou" (itens 1.6, 1.17, 1.24). O desfecho é procurado a cada 250 ms por 5 s e depois a cada reconciliação. Só se resolve por prova:

| Desfecho | Prova |
|---|---|
| executada | deal com `DEAL_ORDER` = ticket da ordem (ticket achado pelo retorno, pelo `request_id` ou pelo comentário) |
| viva | listada nas pendentes |
| não executada | ordem no histórico com `CANCELED`, `REJECTED` ou `EXPIRED`; ou, com leitura confiável, ordem com mais de `IDADE_PROVA` (30 s), ausente das pendentes e do histórico, sem deal, **e** verificação cruzada fechando (se ela tivesse executado, a líquida diferiria dos deals) |

Sem prova, a ordem fica **sem desfecho** e o robô dono fica **pausado** (sem `Tick()`); as S vivas dele seguem no servidor. ALERTA aos 30 s; aos 10 min, bloqueio de entradas que exige o botão (7.2). O botão, apertado pelo dono depois de olhar o extrato, retira as ordens sem desfecho do trânsito; a ficha continua vindo dos deals. O log registra quanto tempo cada ordem ficou sem desfecho e qual prova a resolveu.

### 4.5 Retentativas

S, X, C e cancelamentos recusados: retentados pelo maestro a cada `RETENTA` (5 s); ALERTA na 5ª recusa seguida e a cada 5 min enquanto durar (item 1.13). E recusada volta ao módulo, que decide pela regra dele.

## 5. Stop, saída e cancelamento

### 5.1 Cancelamento confirmado

Confirmado = ordem no **histórico** com `CANCELED` ou `EXPIRED`; o retcode do `OrderDelete` não basta (item 1.5). Desfecho `FILLED` → `EXECUTOU_ANTES` a quem pediu. Sem desfecho, a ordem segue tratada como viva (4.4).

### 5.2 Saída a mercado

Vale para toda saída: regra do robô, nível atravessado, zeragem, corte, ficha da noite, correção. Só dentro do contínuo.
1. Cancela a A do robô, se houver (5.1). **A S fica.**
2. A executou → não envia; recalcula. Sem desfecho → espera (4.4).
3. Envia a mercado, lado oposto, volume = \|ficha\|.
4. **Saída executada (deal visto) → cancela a S** (5.1). Se a S executou antes, a ficha fica trocada → seção 8.
5. **Saída recusada → a S continua**; retenta a cada 5 s (horário, corte, ficha da noite) ou fica com o robô (saída por regra).

Risco residual aceito (B6): S no nível do preço executando junto com a saída → ficha trocada de 1 contrato, corrigida pela seção 8 (item 1.23).

### 5.3 A S: criar, mover, recriar

- **Criar: só com deal.** Entrada limite: na mesma chamada em que o deal de entrada é visto. Entrada a mercado (C1): logo depois do retorno do `OrderSend` com deal; sem deal no retorno, quando o desfecho chegar. O atraso deal→S é logado em toda abertura.
- **Nível:** o que o robô pede (GB, RE, C1, DM; Apêndice A). CM: sem S até o "stop que aperta" nascer (exceção c; O11).
- **Mover** = `OrderModify` da S existente, nunca cancelar e recriar. O nível é o que o robô pede, inclusive quando a regra afrouxa (trailing do C1). Nível 0 vindo de um módulo é ignorado com ERRO. `OrderModify` recusado: a S antiga continua e a retentativa segue 4.5.
- **Nível atravessado** (checado pelo módulo com a fonte de preço do avulso; piso `max(1 tick, SYMBOL_TRADE_STOPS_LEVEL)`, itens 1.25, 4.30) → saída 5.2.
- **Recriar:** a cada reconciliação, ficha ±1 (não trocada) sem S viva há mais de 2 s → S de novo, no nível da memória; sem ele, pela regra do robô; sem regra, `STOP_EMERGENCIA_PTS` do preço da ficha (ALERTA). Cobre S cancelada pela corretora, pelo dono ou disparada sem execução (se o nível já foi atravessado, 5.2).
- **Cancelar:** só em 5.2 passo 4, no OCO (5.4) e como S em excesso (invariante).

### 5.4 OCO

Deal de S ou A que leva a ficha a zero → cancela as demais ordens do robô (5.1) antes de qualquer outra ação. Com o EA fora não há OCO (exceção b); a recuperação cancela as irmãs (10, passo 7).

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
   - cancela, nesta ordem, as A, as E de todos os robôs e por último as S das fichas absorvidas (5.1) — tudo que aumentaria a exposição ao executar;
   - bloqueio de entradas que exige o botão; ALERTA.

### 7.2 Bloqueio de entradas e botão

Bloqueio = nenhuma E nova. Ao entrar: as E vivas são canceladas e os módulos recebem `ENTRADA_CANCELADA` (item 1.9). Nunca são barrados: S, cancelamentos, saídas por regra, zeragens, corte e correções.

Causas: zeragem manual (7.1), cruzada que não fecha em 10 pregões (3.2), ordem sem desfecho há 10 min (4.4), correção repetida (8). Todas saem pelo **botão** `OBJ_BUTTON` "Desbloquear" (visível só com bloqueio; dois cliques em até 3 s; `OnChartEvent`): grava os tickets causadores como **reconhecidos** na memória, libera e loga `DESBLOQUEIO`. A recuperação só bloqueia de novo por evento não reconhecido. Depois do botão nenhum robô reenvia entrada cancelada.

## 8. Ficha trocada ou duplicada

As únicas correções automáticas.
- **Trocada** (duas saídas da mesma ficha: S + A, S + X, ficha de ±1 para ∓1): módulo suspenso; correção C pelo 5.2 com o magic do robô, até 0.
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

**No corte:** (1) cancela todas as E e A dos robôs; (2) toda ficha ainda aberta → 5.2, na ordem fixa, ALERTA (a zeragem do robô falhou); trocada ou duplicada → seção 8; (3) cada S é cancelada quando a saída da ficha dela executa; (4) saída recusada → S fica, retenta a cada 5 s até F; (5) robô com ordem sem desfecho → a saída espera a prova (D1), ALERTA a cada minuto; a S GTC protege. Depois de F nenhuma saída é enviada.

**Ficha que atravessou a noite** (só existe com o EA fora no corte, ou saídas recusadas até F): zerada pelo 5.2 **no primeiro momento de contínuo** — agora, se o EA volta durante o contínuo; senão em `negociacao_inicio`. Até lá a S GTC protege; o robô dono fica sem `Tick()` até a ficha zerar. Fora do contínuo só se criam, movem e cancelam S e se cancelam E e A. Corte perdido (EA volta entre o corte e F) → zera agora.

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
3. **Ambiente:** conta NETTING; símbolo negociável; valor e tamanho do tick ≠ 0 (repete por 60 s). Falha sem ficha nem ordem de robô → para com ALERTA; com elas → modo **PROTEGENDO** (só S, cancelamentos, corte; repete a checagem a cada 30 s).
4. **Histórico:** janela até a cruzada fechar (3.2), prazo 60 s; esgotado → bloqueio com botão e segue.
5. **Memória** (10.1); perdida → linhas `ORDEM` do log do dia para o trânsito.
6. **Reconstrói:** fichas, desfecho de cada ordem do trânsito (4.4), externas e absorção (7.1), bloqueios de eventos não reconhecidos.
7. **Órfãs, antes de qualquer outra ordem:** cancela S e A sem ficha (irmãs de fichas que zeraram com o EA fora), A de ficha trocada, E excedentes (2).
8. **Proteção:** toda ficha ≠ 0 com uma S: nível da memória; sem memória, pela regra do robô (Apêndice A); sem regra, nível da S viva; sem S, `STOP_EMERGENCIA_PTS` (ALERTA). Alvo do RE no nível da memória, salvo ficha trocada ou duplicada.
9. **Pendências:** trocada e duplicada (8); ficha da noite e corte perdido (9.3): executa se no contínuo, senão agenda.
10. **Módulos:** `Init()` de cada robô com o estado restaurado e o recálculo dele (Apêndice A). Decisão de entrada cujo momento passou com o EA fora = `DECISAO PERDIDA` (itens 2.1, 2.6, 4.17).
11. **PRONTO:** grava a memória; log `PRONTO` com as operações do dia por robô reconstruídas dos deals, marcando as feitas com o EA fora, e cada evento perdido com a hora real do deal.

### 10.3 Trava (D3)

Impede o maestro em dois gráficos do mesmo terminal. Variável global `WinMaestro.lock.<conta>.<símbolo>` tomada com `GlobalVariableSetOnCondition(nome, token, 0)`, `token` = `(uint)(ChartID() ^ (ChartID() >> 32))` (1 se der 0; cabe exato num `double`); heartbeat `WinMaestro.hb.<conta>.<símbolo>` = `TimeLocal()` a cada 1 s. Trava de outro gráfico com heartbeat < 10 s → recusa (`Alert`, `ExpertRemove`); ≥ 10 s → toma, AVISO. **`g_iniciou`** fica verdadeira só depois de tomar a trava; instância recusada não cancela ordem, não grava memória e não libera trava. No Testador a trava é pulada (P16).

### 10.4 `OnDeinit`

Loga `FIM` e o `reason`. Com `g_iniciou` falsa, só isso. Com `g_iniciou` verdadeira e `reason` fora de {`PARAMETERS`, `CHARTCHANGE`, `TEMPLATE`}: envia o cancelamento das E próprias sem esperar confirmação (P24); nunca cancela S nem A, nunca fecha posição; grava a memória; libera a trava. Não cobre queda de energia, processo morto nem internet caída.

## 11. Logs

- **Onde:** diário do MT5 e `logs/AAAA-MM-DD.log` (uma linha por evento, `FileFlush` a cada linha; é também fonte da recuperação); `logs/AAAA-MM-DD_trans.log` com uma linha bruta por `OnTradeTransaction` do símbolo (tipo, ordem, deal, estado, preço, volume, magic, `request_id`).
- **Formato:** `HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe | [tick HH:MM:SS.mmm loc HH:MM:SS]`. Hora = `TimeTradeServer()`. `NIVEL` ∈ {INFO, AVISO, ALERTA, ERRO}; `ROBO` ∈ {GB, CM, DM, RE, C1, MAESTRO}.
- **Linha de ordem:** ticket da ordem e do deal, `request_id`, `retcode`/`retcode_external`, comentário, preço pedido e executado lado a lado (item 4.15), líquida antes → depois.
- **Anti-spam por objeto** (ticket ou ficha, item 1.12): a mesma condição é logada ao começar, a cada 5 min com contador e ao terminar.
- **ALERTA** dispara também `Alert()`.
- **Eventos:** `INICIO`, `TRAVA`, `AMBIENTE`, `HISTORICO`, `MEMORIA`, `RECUPERA`, `PROTEGENDO`, `PRONTO`, `SINAL`, `ORDEM`, `DESFECHO` (com a prova), `ESTADO` (aberto, com o motivo), `ENTROU`, `STOP` (criado, movido, recriado), `ALVO`, `SAIDA`, `SAIU`, `CANCELA`, `EXECUTOU_ANTES`, `ORFA`, `ZERAGEM`, `CORTE`, `NOITE`, `TROCADA`, `DUPLICADA`, `CORRECAO`, `EXTERNA`, `ABSORVIDA`, `BLOQUEIO`, `DESBLOQUEIO`, `DECISAO PERDIDA`, `AJUSTE`, `FIM`.

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

Diferenças permitidas, listadas trade a trade com a causa: CM zerado às 18:20 (D2); stop do DM como S no servidor (B8); teto do DM por `DM_CAPITAL` fixo (B9); zeragem pelo timer em vez do primeiro tick; ordem fixa (só no teste 2); stop como S criada após o deal em vez de SL anexado. Qualquer outra diferença é defeito. Relatório: ordens recusadas (> 0 = linha censurada), pior trade em múltiplos do stop (item 6.56).

**Falhas** (conta demo, pregão real; cada linha precisa de evidência no log antes do real, item 4.28):
1. Matar o MT5 com 2 robôs posicionados; deixar o stop de um executar; reabrir: S no servidor, irmã cancelada no passo 7, `RECUPERA` com a hora real.
2. Stop e alvo do RE executando com o EA fora: trocada corrigida no passo 9.
3. Saída a mercado com a internet caindo logo depois (as duas versões: executou / não chegou): S viva o tempo todo, nada duplicado (cenário b).
4. Apagar `estado.txt`; apagar também o `.bak`: `.bak` usado; depois memória perdida com nenhuma ficha sem S.
5. Zerar a líquida na mão com 2 robôs posicionados e ordens vivas: absorção, cancelamentos, bloqueio; botão libera; reiniciar não rebloqueia.
6. Abrir e fechar posição manual: externa volta a 0, fichas intactas, sem bloqueio.
7. Maestro em dois gráficos do mesmo terminal: o segundo recusa; o primeiro intacto.
8. Trocar o timeframe com robôs posicionados: nada cancelado, nada duplicado.
9. EA fechado 18:15 e aberto 18:22 com ficha: zera na hora. EA fechado das 17:00 às 08:50: S GTC protegeu, ficha zerada no primeiro contínuo.
10. Forçar a falha da zeragem de um robô: o corte zera em F − 5 min.
11. Entrada executada duas vezes (forçada no Testador por ordem manual com o magic): correção de 1, S mantida.
12. Dia de 17:55: todos zerados até 17:50.

**Escada no real** (a demo não mede fila nem stop na B3, item 4.7): 1 robô por 5 pregões → 2 robôs que podem ficar em lados opostos (CM e RE) por 5 pregões → os 5. Avança com zero divergência não explicada e extrato igual ao log em contratos e preço. Antes do degrau 1: P1–P6, P15, P18, P22–P24 respondidas.

## 13. Fora do escopo

Combinar sinais ou priorizar robôs; limites de perda, de operações ou de horário não pedidos; hedging; mais de uma instância na mesma conta e símbolo (D3); lote > 1; alarme do item 1.24 (preço médio da líquida fora da grade é normal com várias fichas).

## Apêndice A — o que muda em cada módulo

Comum: os 3 bloqueios por posição de outro robô saem; os fechamentos da líquida viram `Ficha_Fecha`; `PositionModify` vira `Ficha_DefineStop`; SL anexado vira S criada no deal; zeragem e "outro dia" do módulo desligados por flag; `Tick()` só de `negociacao_inicio` ao corte; gate de vela nova persistido como instante; eventos do maestro = não rearmar.

| Robô | Persistir | Recálculo na partida | Particularidade |
|---|---|---|---|
| GB (M5) | `g_decidido`, `g_exp`, `g_be_feito`, data | stop = preço da ficha ∓ `StopPts` | E `SPECIFIED` 09:05–09:35; S 1.200 pts; BE = `OrderModify` da S |
| CM (H2) | `g_ultima_barra`, `a_favor`, nível do stop que aperta, hora e lado da entrada | stop que aperta das barras desde a hora da ficha; avalia a última H2 fechada | sem S até o stop que aperta (O11); zeragem 18:20/17:50 (D2) |
| DM (M1) | `g_stopNivel`, `g_distStop`, `g_stopAjustado`, `g_decidiu`, `g_dia`, `g_ordemHora`, `g_ordemPreco` | sem memória: `g_distStop` da decisão das 10:30 refeita das barras | stop = S no servidor em `g_stopNivel` (B8); teto de risco = 10% de `DM_CAPITAL` (B9) no lugar de `ACCOUNT_BALANCE` (L396) |
| RE (M15) | entrada pendente (hora, lado, meio, stop e alvo originais), posição (preço, largura, fração do alvo, hora da vela do fill), retângulo vivo | barras esperando e em posição a partir dos instantes; A movido ao passo correspondente | A = limite que se aproxima (`OrderModify`), DAY; não cancela a E no próprio `Deinit`; `TesterStop` (L1007) desligado |
| C1 (H1) | `g_ultima_barra`, nível do stop | pico, esticada e stop da última H1 fechada desde a hora da ficha | entrada a mercado; trailing pode afrouxar (L536-550), o maestro move igual; checagem bid/ask, 1 tick |

## Apêndice B — decisões

### Tomadas pelo dono em 2026-10-07

- **D1.** Antes de toda ordem, conferir posição líquida, ordens vivas e histórico (com o log se preciso); só envia se o estado fecha; nada reenviado por inferência de tempo (4.3, 4.4).
- **D2.** Corte global = fim do contínuo − 5 min; todos zerados até lá; CM limitado ao corte (9).
- **D3.** Uma instância só, no PC; só a trava contra dois gráficos no mesmo terminal (10.3).
- **Inputs.** Os 5 liga/desliga no topo (1).

### Aguardam o dono

| # | Decisão | Recomendação |
|---|---|---|
| B1 | Validade da S: GTC (ficha esquecida protegida à noite; órfã cancelada no passo 7) ou DAY (nua à noite se o EA falhar no corte) | **GTC**, se P1 confirmar que a Rico aceita |
| B2 | Entradas e alvos com validade DAY (RE e alvo do GB eram GTC no avulso) | **DAY** |
| B3 | Aposentar o WinSeletor e os EAs avulsos (`.ex5` fora da pasta Experts e de todo gráfico antes da primeira partida) | **aposentar** |
| B4 | Aceitar a janela sem stop (exceções a, b, c) com pior caso de 4 contratos × 5.630 pts (amplitude diária p99 do WIN$N 2022–2026) = R$4.504; teto teórico 5 contratos = R$5.630 | **aceitar** |
| B5 | RE com S e A vivos com o EA fora (pode executar os dois e ficar trocado até a volta) | **aceitar**, com a correção da seção 8 |
| B6 | Saída antes de cancelar a S (custo: S no nível do preço pode executar junto → trocada por segundos) em vez de cancelar a S antes (custo: saída recusada deixa a ficha nua) | **saída antes** (5.2) |
| B7 | Depósito mínimo: margem do pior estado (5 × R$100 × 2) + teto de B4 = R$6.630 | **depositar R$7.000** |
| B8 | Stop do DM como S no servidor no próprio `g_stopNivel` (um caminho só; dispara pela corretora em vez do EA por last) | **aceitar**; alternativa em O9 |
| B9 | Teto de risco do DM sobre capital fixo `DM_CAPITAL` = R$1.000 (teto R$100 = 500 pts), em vez do saldo da conta com 5 robôs | **aceitar**; alternativa em O10 |

## Apêndice C — rastreabilidade das revisões

| Lacunas | Onde |
|---|---|
| Rev. 1 C1, N1, N2, T1, T2 (trânsito, DONE sem deal, reenvio duplicado, ordem sem desfecho) | corpo 4.1–4.4; D1 |
| Rev. 1 C2, A10, N10, N12, N23 (cancelamento confirmado, retentativas, avisos ao módulo) | corpo 3.3, 4.2, 4.5, 5.1 |
| Rev. 1 C3, N5, N6 (intervenção externa, botão) | corpo 7; O13 (absorção proporcional) |
| Rev. 1 C4, N20 (janela fill→stop, pior caso) | Princípio 4; 5.3; 10.4; B4, B7 |
| Rev. 1 C5, N11, T6, R9 (sem OCO, ficha trocada, saída × S) | corpo 5.2, 5.4, 8, 10.2 passos 7–9; B5, B6 |
| Rev. 1 C6, N3, N18, T3, T4, trava em `double` | decisão D3; corpo 10.3, 10.4; O12 (EA avulso) |
| Rev. 1 C7 (autonegociação) | O2 |
| Rev. 1 C8, A7, N9 (margem, stop que abre para a conta) | O1 |
| Rev. 1 C9, N4, T5, T7 (ficha da noite, R4 eterno, regra única) | decisão D2; corpo 3.2, 9.3, 10.2 passo 4; B1 |
| Rev. 1 C10, N7, N24 (divergência transitória, cruzada) | corpo 3.2, 6; O6 (várias leituras), O14 (cobertura pela conta) |
| Rev. 1 C11 (stop disparado sem execução) | corpo 5.3 (recriar); O5 (limite agressiva) |
| Rev. 1 A1, N14 (relógio, dono da zeragem) | corpo 9.1, 9.2 |
| Rev. 1 A2–A6, M1–M3, M5, M7, M8, B1–B5, N8, N13, N15–N17, N25–N27 (papel, estado, memória, órfãs, inputs, preenchimento, mover stop, `seq`, lote) | corpo 1, 2, 3, 5.3, 9.3, 10, 13; Apêndice A |
| Rev. 1 A8, A9, N21, N22 (equivalência, testes, camada de corretora) | corpo 1 (porta única), 12; O15 (corretora falsa) |
| Rev. 1 A11 (DM em dois caminhos) | B8; O9 |
| Rev. 1 M4, N19 (logs, push) | corpo 11; O3, O7 |
| Rev. 2 N10/N27 (notas da rev. 3), `TesterStop` do RE | corpo 1, 3.3; Apêndice A |
| Afirmações erradas da rev. 1 (stop "no servidor com o terminal desligado", SL/TP da líquida, comentário identifica a ordem, `RETURN` exigido) | P1, P3, P15; Princípio 7; corpo 2 |

## Apêndice D — itens opcionais, decisão do dono

Fora do corpo. Cada um diz o que faz, o risco de não ter, o custo e a recomendação.

- **O1. Portão de margem.** Recusa a entrada que deixaria a conta sem margem no pior estado (todas as pendentes executando). Sem ele: a corretora recusa o que não cabe; o risco é uma entrada aceita deixar um stop de outro robô sem margem (item 1.1), raro com depósito ≥ R$7.000. Custo: leitura de saldo com proteção contra valor absurdo, P7–P9 a responder. **Recomendação: não incluir.**
- **O2. Autonegociação.** Não envia E ou A que cruze com limite própria do lado oposto; cancela a limite do outro robô antes de uma saída que cruzaria. Sem ele: casamento entre dois robôs do próprio cliente, raro (< 1% das entradas no replay), com risco regulatório (P12). Custo: médio, mexe na sequência de saída. **Recomendação: incluir só a primeira metade (não enviar E/A que cruze).**
- **O3. Push com fila e dedupe.** `SendNotification` em todo ALERTA, agregando rajadas, 1 a cada 10 s. Sem ele: o dono só vê `Alert()` se estiver no PC; num incidente fora de casa, descobre tarde. Custo: baixo se for envio direto com intervalo mínimo (excesso só no log); a fila agregada é o que custa. **Recomendação: incluir só o envio direto com intervalo de 10 s.**
- **O4. Teto de envios e disjuntor.** Mais de 100 envios num minuto → entradas bloqueadas 5 min; no máximo 20 E por minuto. Sem ele: um defeito de laço do próprio EA pode mandar centenas de ordens (item 1.20, 1.22) — o D1 já impede E duplicada por construção. Custo: um contador. **Recomendação: incluir só o disjuntor.**
- **O5. Stop-limit e limite agressiva em leilão.** Saída por limite a último ∓ 3 ticks quando a S dispara sem executar ou a saída é recusada. Sem ele: a ficha espera a próxima retentativa a mercado (5 s), sem stop, em leilão ou banda. Custo: alto (outra ordem viva, corrida com a S, ficha trocada). **Recomendação: não incluir; reavaliar depois de P1 e P13.**
- **O6. Verificação cruzada com várias leituras.** Exige 3 leituras em ≥ 3 s antes de concluir divergência ou "não executada" pela posição. Sem ele: uma leitura no instante errado pode concluir "não executada" — mitigado pela idade mínima de 30 s da ordem (4.4). Custo: baixo-médio. **Recomendação: incluir se P6/P18 mostrarem atraso de deal acima de 5 s.**
- **O7. Painel no gráfico.** `Comment()` com estado, fichas, líquida, externa, bloqueio, corte do dia. Sem ele: o dono lê o log. Custo: baixo, só leitura, não toca em ordens. **Recomendação: incluir.**
- **O8. Rotação de log.** Apagar ou compactar logs antigos. Sem ele: um arquivo por dia cresce sem limite, ~MB por mês. Custo: baixo, mas apagar arquivo é risco à recuperação. **Recomendação: não incluir.**
- **O9. Reserva do DM 20 ticks além.** Mantém o stop do EA por last no nível testado e põe a S 100 pts além. Sem ele: o DM sai pela S da corretora no nível (B8), mecanismo levemente diferente do testado. Custo: dois caminhos de saída para o mesmo nível, corrida S × saída, regra especial no Testador. **Recomendação: não incluir.**
- **O10. Saldo virtual do DM.** Teto sobre R$1.000 + resultado acumulado do DM, em arquivo permanente reconstruível. Sem ele: teto fixo de R$100 (B9), difere do avulso só depois de lucro ou prejuízo acumulado relevante. Custo: arquivo permanente e reconstrução. **Recomendação: não incluir.**
- **O11. Stop de reserva do CM.** S a 4.945 pts (maior excursão adversa de 815 trades 2022–2026, 4.120 pts, + 20%) desde o preenchimento, movida para o stop que aperta. Sem ele: com o EA fora, o CM fica nu, perda limitada só pela amplitude do dia (p99 R$1.126). Custo: baixo, mesmo mecanismo da S dos outros; nunca teria disparado nos testes. **Recomendação: incluir.**
- **O12. Detecção de EA avulso esquecido.** Ordem com magic de robô que o maestro não enviou → bloqueio e ALERTA. Sem ele: um avulso esquecido num gráfico opera junto e o maestro conta os deals dele na ficha. Custo: registro persistente de ordens próprias. **Recomendação: não incluir; trocar por item de checklist em B3.**
- **O13. Absorção proporcional.** Zeragem manual parcial dividida entre as fichas na proporção, em vez da ordem fixa. Sem ele: a ordem fixa é determinística e reproduzível sem memória; zeragem parcial é rara. Custo: frações e arredondamento. **Recomendação: não incluir.**
- **O14. Cobertura pela conta (8.4 nível 2).** Cria ou cancela S pela diferença entre a líquida real e as S vivas, atribuída a um robô suspeito. Sem ele: execução sem deal visível deixa o robô pausado com a S dele até a prova chegar, e o dono é alertado. Custo: alto (atribuição por suspeita, S sem dono certo). **Recomendação: não incluir.**
- **O15. Corretora falsa para testes unitários.** Segunda implementação de `Corretora.mqh` com respostas roteirizadas (DONE sem deal, timeout, recusa, histórico atrasado). Sem ele: as falhas só são testadas na demo, sem controle do momento. Custo: médio, só no EA de teste; não entra no `.ex5` de produção. **Recomendação: incluir.**
- **O16. Varredura de outros símbolos.** Na partida, ALERTA se houver ordem ou posição de magic de robô em outro contrato (rolagem). Sem ele: S GTC esquecida no contrato velho passa despercebida. Custo: baixo, só log. **Recomendação: incluir só na partida, sem bloqueio.**
- **O17. Detecção de SL/TP na líquida.** Bloqueio e ALERTA quando o dono põe SL/TP na posição. Sem ele: se executar, o deal já é tratado como zeragem manual (7.1). Custo: baixo. **Recomendação: não incluir.**
- **O18. Entrada atrasada reenviável.** Na partida, devolve ao módulo a entrada cujo momento passou com o EA fora, se ainda não executável. Sem ele: `DECISAO PERDIDA` sempre (uma entrada a menos após queda). Custo: médio, regra por robô. **Recomendação: não incluir.**
- **O19. Resumo e conciliação do dia.** Após o corte: R$ por robô, total pelas fichas × `DEAL_PROFIT`, contratos negociados × `ENTROU`/`SAIU` do log, ALERTA se diferir. Sem ele: a conferência com o extrato é manual. Custo: baixo, só log. **Recomendação: incluir.**

## Apêndice E — perguntas à corretora

- P1. `SELL_STOP`/`BUY_STOP` no WIN: aceita com GTC? Fica listada com o terminal fechado? Fica na Rico ou vai à B3? Vira mercado ou limite?
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
- P23. Stop GTC num contrato que vence é cancelado no vencimento?
- P24. O `OrderDelete` enviado no `OnDeinit` ao fechar o terminal chega ao servidor?
- P25. Limite de `SendNotification` por segundo e por minuto?

## Cenários de referência

**(a) CM e RE comprados; MT5 morto às 14:00; a S do RE executa 14:20; o A do RE enche 15:10; volta 15:30.** A ficha do RE vai a −1 (trocada); líquida 0 desde 15:10. Na volta: passos 1–6 reconstroem CM +1 e RE trocada; passo 7 não tem o que cancelar; passo 8 garante a S do CM (se o stop que aperta existe) e não recoloca alvo no RE; passo 9 envia C de compra 1 com o magic do RE no contínuo, ficha → 0. Resposta única e segura.

**(b) Saída a mercado do C1 volta `TIMEOUT` sem ticket; a internet cai 90 s.** A S do C1 nunca foi cancelada (5.2). Desconectado nada se resolve e nada é enviado. Na volta, releitura completa: se executou, o deal aparece (achado pelo comentário), a ficha vai a 0 e só então a S é cancelada; se não chegou, com leitura confiável e a cruzada fechando a ordem é "não executada" e o C1 manda a saída de novo pela regra dele, com a S viva. Sem prova, o C1 fica pausado, com a S, e o dono é alertado. Resposta única e segura.

**(c) O dono zera tudo na mão às 11:00 com GB e DM posicionados e ordens vivas.** Venda manual de 2 (magic 0): nada a compensar na externa; reduz abaixo de Σ fichas → absorção GB, depois DM. Cancela A, E e as S das absorvidas; bloqueio de entradas. O botão libera; reiniciar não rebloqueia (tickets reconhecidos); GB e DM não reentram no dia (`g_decidido`, `g_decidiu`). Resposta única e segura.

**(d) PC desligado desde 17:00 de ontem com o DM posicionado e S GTC; gap contra na abertura.** Ficha que atravessou a noite. Partida antes das 09:00: passos 1–8 (S conferida), passo 9 agenda a saída para `negociacao_inicio`; nenhum `Tick()` fora do contínuo. Se a S disparar no leilão (P13), a ficha zera e a saída agendada não tem o que fazer; senão, saída a mercado no primeiro momento de contínuo com a S viva, que só é cancelada depois. Resposta única e segura.

**(e) Maestro no PC e na VPS ao mesmo tempo.** Fora do escopo (D3). Coberto: dois gráficos no mesmo terminal — o segundo falha na trava (10.3), sai com `g_iniciou` falsa e não toca em ordem, memória nem trava do primeiro.
