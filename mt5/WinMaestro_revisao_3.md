# WinMaestro: revisão 3 da especificação 0.3

Escopo: `WinMaestro_ESPECIFICACAO.md` 0.3, conferida no corpo do texto (o Apêndice C não foi aceito como prova), contra a lista mínima e as lacunas N1–N27 da revisão 2, as 13 parciais da revisão 1 e o código em `WinSeletor/*.mqh`. Severidades como na revisão 2: **CRÍTICA** = pode perder dinheiro, deixar posição sem stop ou duplicar ordem; **ALTA** = trava o robô ou esconde estado perigoso.

---

## 1. Situação dos itens anteriores

### 1.1 Lista mínima de 14 (revisão 2)

| # | Item | Situação | Onde / por quê |
|---|---|---|---|
| 1 | N1 `DESCONHECIDA` | **PARCIAL** | 4.6 tem resolução em 30 s e S nunca bloqueada, mas a `NAO_EXECUTADA` pode ser concluída sem conexão (T1) e a `INDETERMINADA` não tem prazo e trava a saída (T2) |
| 2 | N2 E limite na ficha efetiva | FECHADA | 3.1 (E limite contribui 0), 4.6 (pendente listada sai do trânsito), 8.4 |
| 3 | N3 ordem estranha falsa | FECHADA | 4.4, 9.2, 9.5, 8.6. O falso positivo sumiu; a regra do prefixo criou um falso negativo entre máquinas (T3) |
| 4 | N4 R4 para sempre | **PARCIAL** | R4 tem prazo e protege, mas cai num `PROTEGENDO` do qual não há saída (T5) |
| 5 | N5 compensação da externa | FECHADA | 8.9 passo 1 |
| 6 | N6 desbloqueio | FECHADA | 8.6 (botão, eventos reconhecidos), R6, 9.1 |
| 7 | N7 releituras e cruzada | FECHADA | 8.1, 8.2 (`CRUZADA_MAX`) |
| 8 | N8 R2/R3 | FECHADA | 10.2: conexão (R2) antes do ambiente (R3), leitura zerada repetida 60 s, `RECUSADO` só sem fichas |
| 9 | N9 capital | FECHADA | 13.1, 13.2, B.10, B.11 |
| 10 | N10 quem retenta E | FECHADA | 3.4 (`Robo_Evento`), 4.8, Apêndice A |
| 11 | N11 ficha trocada | FECHADA | 3.1, 8.3, 8.4, 3.3 (ressalva: R9 não exclui a trocada ao recolocar o alvo do RE, cenário a) |
| 12 | N12/N13 | FECHADA | 5.1 passo 2, 5.2 passo 2, 4.7 itens 2–3, A.5 |
| 13 | N14 dono da zeragem | FECHADA | 12.1, 12.2, 2.1 |
| 14 | N16/N17 | FECHADA | R11 `Init` antes de R12, 10.4, `LOTE` = 1, 16 |

### 1.2 N1–N27

| Lacuna | Situação | Nota |
|---|---|---|
| N1 | **PARCIAL** | T1, T2 |
| N2 | FECHADA | |
| N3 | FECHADA | regressão em T3 |
| N4 | **PARCIAL** | T5 |
| N5 | FECHADA | |
| N6 | FECHADA | |
| N7 | FECHADA | |
| N8 | FECHADA | |
| N9 | FECHADA | |
| N10 | FECHADA | E cancelada pelo dono ou pela corretora não tem evento definido (7 diz "aviso ao módulo" sem nomear qual); MÉDIA |
| N11 | FECHADA | |
| N12 | FECHADA | |
| N13 | FECHADA | |
| N14 | FECHADA | |
| N15 | FECHADA | 6 (estado derivado) |
| N16 | FECHADA | |
| N17 | FECHADA | |
| N18 | FECHADA | 7, 9.1, 10.1, 10.2 |
| N19 | FECHADA | 11.2 |
| N20 | FECHADA | B.7 = 13.4 (R$4.504 / R$5.630); 13.5 = R$6.630 |
| N21 | FECHADA | 15.1 |
| N22 | FECHADA | 1, 15.2 |
| N23 | FECHADA | 5.2 passo 1 serial |
| N24 | FECHADA | 3.2 |
| N25 | FECHADA | 4.1 |
| N26 | FECHADA | 4.2 |
| N27 | **PARCIAL** | constantes ok (2.2); o grupo Maestro ficou **no topo** (2.1), contra a preferência "input novo no fim". BAIXA, não bloqueia |

### 1.3 As 13 parciais da revisão 1

| Lacuna | Situação | Nota |
|---|---|---|
| C1 trânsito | **PARCIAL** | T1, T2 |
| C3 intervenção externa | FECHADA | cenário (c) passa |
| C4 janela fill→stop | FECHADA | |
| C6 duas instâncias | **PARCIAL (regressão)** | T3 (PC + VPS não detectado), T4 (instância recusada estraga a viva) |
| C9 ficha que atravessa a noite | **PARCIAL** | noite coberta; a saída na abertura tem duas regras conflitantes e fica sem S se recusada em leilão (T6, T7) |
| C10 divergência transitória | FECHADA | |
| A1 relógio | FECHADA | |
| A7 margem | FECHADA | |
| A8 equivalência | FECHADA | |
| A10 retentativas | FECHADA | |
| M6 custo da reconciliação | FECHADA | |
| M8 mover stop | FECHADA | |
| B4 parcial com lote > 1 | FECHADA | |

---

## 2. Lacunas novas da 0.3 (só CRÍTICA e ALTA)

### T1. `NAO_EXECUTADA` pode ser concluída sem conexão, e o reenvio duplica a ordem — CRÍTICA
- **Seção:** 4.6, tabela de resolução, linha 1.
- **Defeito:** as três condições ("nenhum vestígio", "cruzada fechando", "líquida inalterada") são todas verdadeiras **por construção** com o terminal desconectado: não chega histórico, a líquida em cache não muda, e Σ deals local = líquida em cache. Nada no texto exige `TERMINAL_CONNECTED` durante o prazo nem releitura depois de reconectar. A ordem que de fato executou no servidor é declarada não executada e a 4.6 libera o reenvio. Na reconexão há uma janela em que a posição já sincronizou ou ainda não, e um reenvio nessa janela executa de verdade: X duplicada = ficha trocada (posição oposta sem stop até a 8.3); E duplicada = ficha ±2, estado que a 3.1 declara inválido e que nenhuma seção trata (S tem volume 1).
- **Agravante:** S com retorno "não sei" também não tem regra: a 4.6 diz que S nunca é bloqueada e a 4.8 manda retentar "recusada", mas erro de transporte não é recusa. Duas S podem ficar vivas até o invariante 1 cortar uma.
- **Correção (texto):** "Os 30 s de `PRAZO_DESCONHECIDA` só correm com `TERMINAL_CONNECTED` verdadeiro; desconexão zera a contagem. `NAO_EXECUTADA` exige, além das três condições, uma releitura completa (8.1) feita depois da última reconexão e pelo menos 10 s de conexão contínua depois dela. S com retorno 'não sei' entra no trânsito como qualquer ordem; a S seguinte só é enviada quando essa resolver. Ficha pelos deals com |ficha| > 1 = bloqueio que exige o dono, S com volume |ficha| e correção C até ±1, ALERTA com push."

### T2. `INDETERMINADA` não tem prazo, trava zeragem e rede, e a S depende de uma condição que falha com 5 robôs — CRÍTICA
- **Seções:** 4.6 regra 1, regra 2, linha 3 da tabela; 5.2 passo 2; 8.4; 12.3.
- **Defeito 1 (sem saída):** a `INDETERMINADA` "se resolve quando a cruzada fechar", sem prazo. Enquanto isso bloqueia X e C do robô (regra 1). Zeragem e rede são X/C pelo 5.2; a 8.6 diz que saídas por horário nunca são barradas, mas fala de **bloqueios**, não do `JA_EM_TRANSITO` da 4.6. E mesmo que passassem, o 5.2 envia `volume = |ficha efetiva|`, que é 0 com a X em trânsito (+1 − 1). A rede de 12.3 detecta a ficha pelos deals aberta e manda zerar volume 0.
- **Defeito 2 (sem stop):** a S só é recriada com "líquida real **inalterada desde o envio**" (regra 2), e a 8.4 usa "líquida compatível (regra 2)" sem definir compatível. Qualquer deal de outro robô entre o envio e os 30 s (stop do RE, entrada do CM) muda a líquida: a regra 2 deixa de valer, a ordem cai em `INDETERMINADA` (linha 3: "líquida mudou de forma diferente") e o robô fica com posição possível sem S, sem saída e sem prazo, atravessando a noite.
- **Correção (texto):** "**Resíduo real do robô** = líquida real − Σ fichas pelos deals dos outros robôs − exposição externa. Compatível = resíduo real com o mesmo sinal e volume da ficha pelos deals do robô. A regra 2 e a 8.4 usam o resíduo, não 'líquida inalterada'. Saída por horário e rede com ordem do robô `INDETERMINADA` enviam volume = |resíduo real| (0 → nada), ignorando `JA_EM_TRANSITO`. `INDETERMINADA` com mais de 10 min → bloqueio que exige o dono, ALERTA com push repetido."

### T3. Duas instâncias em máquinas diferentes não são detectadas: o prefixo `MAE|i1|` é o mesmo nas duas — CRÍTICA
- **Seções:** 1 (`INST` = `i1` constante), 4.2, 4.4, 10.1.
- **Defeito:** 4.4 define ordem própria = ticket no registro **ou** comentário com prefixo `MAE|i1|`. PC e VPS usam o mesmo `i1`; cada uma reconhece as ordens da outra como próprias pelo prefixo. A "ordem estranha" da 10.1, que é a única defesa entre máquinas, nunca dispara (só dispararia se a Rico reescrevesse o comentário, P3).
- **Efeito:** detalhado no cenário (e): entradas em dobro, fichas ±2, saídas em dobro, cancelamentos cruzados como violação de invariante.
- **Correção (texto):** "Ordem própria = ticket no registro de ordens próprias. O prefixo só serve para a linha 'anterior ao primeiro heartbeat' (memória perdida) e para a busca do trânsito. `INST` deixa de ser constante: 2 caracteres gerados na primeira partida, gravados no estado permanente da máquina (`FILE_COMMON`), diferentes entre PC e VPS." (Com `INST` próprio, o prefixo também passa a separar as duas.)

### T4. A instância recusada estraga a instância viva no `OnDeinit` — ALTA
- **Seções:** 7 (`OnDeinit`), 10.1, 10.2 R1, 9.1.
- **Defeito:** a segunda instância no mesmo terminal falha no R1 e faz `ExpertRemove` → `OnDeinit` com `REASON_REMOVE`, que pela seção 7 (a) cancela **todas as E dos magics dos robôs**, que são as da instância viva (os módulos dela não recebem evento e, pelo Apêndice A, não rearmam); (b) grava memória no mesmo caminho `<servidor>_<conta>_<símbolo>_i1`, sobrescrevendo o estado da viva com um estado vazio; (c) "libera a trava", que é da outra. É exatamente o teste "Maestro em dois gráficos do mesmo símbolo" de 15.3.
- **Correção (texto):** "`OnDeinit` só cancela E, grava memória e libera a trava se esta instância passou do R1 (detém a trava). Recusada no R1: só loga `FIM`."

### T5. Depois do prazo de R4 o EA fica em `PROTEGENDO` para sempre — ALTA
- **Seções:** 3.2, 10.2 R4 e `PROTEGENDO`, 8.2, 8.5, 8.3, 4.6.
- **Defeito:** esgotado o R4, a diferença vira "exposição externa de origem desconhecida" e o EA vai a `PROTEGENDO`, que "sai quando a causa some". A causa é a cruzada não fechar, e a cruzada (3.2) é `S = líquida real`, sem a externa desconhecida: nunca fecha. O caso que motivou o N4 (posição manual do dono de semanas) deixa os 5 robôs parados para sempre, e o bloqueio de `PROTEGENDO` é do tipo "sai sozinho", então o botão nem aparece. Pior: tudo que exige cruzada fechando também morre (órfã 8.5, correção 8.3, `NAO_EXECUTADA`).
- **Correção (texto):** "Depois do prazo de R4, a cruzada passa a ser `S + externa de origem desconhecida = líquida real`; a externa desconhecida é gravada e só muda por deal novo. O `PROTEGENDO` causado por R4 é bloqueio que exige o dono (botão), não automático."

### T6. Saída recusada em leilão deixa a ficha sem S, e a 8.4 briga com a 5.4 — ALTA
- **Seções:** 5.2 passos 1 e 5, 5.4, 8.4, 6.
- **Defeito:** o 5.2 cancela a S antes da saída a mercado. Se a saída for recusada (leilão de abertura, leilão por variação, banda, margem), a 5.4 põe uma limite "no preço da proteção para participar do leilão" e a S não volta. Com gap contra, essa limite fica do lado errado do preço do leilão e não executa; a posição abre o contínuo **sem stop** até o reenvio agressivo 5 s depois, em pleno movimento. Fora do leilão, a 8.4 (ficha pelos deals ≠ 0 sem S há 2 s) não exclui o estado `SAINDO`: recria a S, a 5.4 a cancela antes de cada reenvio (5 s), a 8.4 recria, e o texto não diz qual vence.
- **Correção (texto):** "Saída a mercado recusada → a S é recriada na hora no nível da proteção (8.4) e o robô fica em `SAIDA_RECUSADA`. Em leilão, a proteção é a S (que dispara na abertura do contínuo), sem limite. Fora de leilão, a limite agressiva de 5.4 só é enviada depois de cancelar a S com confirmação, e a 8.4 não age sobre robô em `SAINDO` ou `SAIDA_RECUSADA` por até 5 s por tentativa."

### T7. Duas regras para a ficha de pregão anterior antes da abertura — ALTA (bloqueia resposta única)
- **Seções:** 12.4 ("nunca na pré-abertura", às `negociacao_inicio` + 30 s); A.3 (DM: "se a mínima/máxima das M1 desde o heartbeat cruzou `g_stopNivel`, sai agora"); 7 (`OnTick` chama `Tick()` de robô com ficha, em `PRONTO`, sem restrição de fase).
- **Defeito:** com o EA ligado antes das 09:00, as M1 desde o heartbeat incluem o after-market de ontem; o recálculo do DM manda sair "agora", em pré-abertura. O stop do EA do DM no `Tick()` também pode disparar em pré-abertura (bid/ask do leilão). Cada caminho cai no T6.
- **Correção (texto):** "Nenhuma saída de robô ou do maestro é enviada fora do contínuo da grade, exceto a S. Saída decidida fora do contínuo (recálculo, `Tick()` de módulo, horário perdido) é agendada para `negociacao_inicio` + 30 s, como a ficha de pregão anterior."

### Notas que não chegam a ALTA mas mudam o código (uma linha cada)
- **R9 e ficha trocada:** "alvo do RE no nível da memória" precisa de "salvo ficha trocada"; hoje o R9 roda antes do R10 e pode pôr uma limite do lado errado (cenário a).
- **Trava (10.1):** `GlobalVariableSetOnCondition` guarda `double`; `ChartID()` tem ~1,3×10^17, acima de 2^53, e perde os últimos dígitos. Dois gráficos podem cair no mesmo valor. Usar um token < 2^53 (ex.: `ChartID() % 2^52` ou um sorteio gravado).
- **RE no Testador:** `WinRetanguloEma34.mqh` L1007 chama `TesterStop()` se `ACCOUNT_EQUITY <= RE_LimiteEquity`. No teste 2 (os 5 juntos) isso para o teste de todos pela equity da conta. Desligar no maestro.

---

## 3. Cenários

### (a) CM e RE comprados; MT5 morto às 14:00; stop do RE executa 14:20; alvo do RE enche 15:10; volta 15:30
1. 14:00: sem `OnDeinit`. No servidor: S do CM (reserva), S e A do RE.
2. 14:20: S do RE executa; líquida +2 → +1. A do RE continua viva (sem OCO, Princípio 4b).
3. 15:10: A do RE enche; líquida 0; ficha do RE pelos deals = −1 (trocada).
4. 15:30: R1 (heartbeat velho, toma a trava), R2, R3, R4 (Σ deals de hoje = 0 = líquida; fecha), R5 (memória de 14:00), R6 (CM +1, RE −1 trocada), R7 (nada a cancelar: RE sem ordens), R8 (CM caso A; RE caso B, eventos logados com a hora real), R9 (CM já tem S), R10 (8.3: compra C a mercado com magic do RE, ficha → 0), R11–R13.
5. Entre 15:10 e 15:30 a conta estava líquida 0, sem risco.

**Resposta única e segura: sim**, com uma ambiguidade: o R9 manda recolocar "o alvo do RE no nível da memória" e não exclui a ficha trocada. Se o programador fizer isso, sai uma limite de venda numa ficha vendida (papel "E fora de lugar" pela 3.3, que a reconciliação cancela). Uma linha resolve.

### (b) Saída a mercado do C1 volta TIMEOUT sem ticket; internet cai 90 s
1. t0: 5.2 cancela a S (confirmada) e envia a venda; `TIMEOUT`, ticket 0.
2. t0+5 s: `DESCONHECIDA`. t0+5–10 s: a regra 2 manda recriar a S; o envio falha por falta de conexão. O texto não diz se a S "não sei" pode ser reenviada (T1).
3. t0+30 s, ainda offline: sem vestígio (offline), cruzada "fecha" (cache), líquida "inalterada" (cache) → **`NAO_EXECUTADA`**, reenvio liberado.
4. Se a venda original executou no servidor, qualquer reenvio que encontre conexão antes de a posição sincronizar vende de novo: C1 vendido 1 sem stop, até a 8.3 corrigir com uma terceira ordem a mercado.
5. Se outro robô tiver deal no intervalo, a ordem cai em `INDETERMINADA`: sem S (regra 2 exige líquida inalterada), sem saída (X bloqueada) e sem prazo (T2).

**Resposta única e segura: não.** T1 e T2.

### (c) Dono zera tudo na mão às 11:00 com GB e DM posicionados e ordens vivas
1. GB +1, DM +1 (líquida +2); o dono vende 2 (magic 0, `CLIENT`).
2. 8.9: nada a compensar; reduz |líquida| abaixo de Σ fichas → absorção GB, depois DM; ambas a 0 ao preço do deal (`ABSORVIDA`).
3. Cancela S e A das absorvidas, depois todas as E (`ENTRADA_CANCELADA`); bloqueio que exige o dono; push agregado.
4. Se o dono cancelar as ordens antes de fechar a posição, a 4.9.4 recria as S das fichas ainda abertas e a absorção as cancela em seguida: ruído, não risco.
5. Botão libera; reinício não rebloqueia (eventos reconhecidos). GB (`g_decidido`) e DM (`g_decidiu`) não reentram.

**Resposta única e segura: sim.** Ressalva MÉDIA: E cancelada pelo próprio dono não tem evento nomeado para o módulo (N10).

### (d) Primeiro pregão após PC desligado desde 17:00 de ontem, DM posicionado com S GTC; gap contra na abertura
1. Noite: a S de reserva do DM (GTC, 100 pts além do stop do EA) protege. O que ela faz no leilão de abertura depende de P1/P13.
2. Partida: R4 recua um pregão e fecha; R8 caso A; R10 agenda a saída da ficha de pregão anterior para 09:00:30.
3. Conflito: o recálculo do A.3 olha as M1 desde o heartbeat (inclui o after-market de ontem) e manda "sair agora"; o `Tick()` do DM roda em `PRONTO` e pode disparar o stop do EA em pré-abertura. A 12.4 proíbe saída em pré-abertura. Duas regras, respostas diferentes (T7).
4. Qualquer saída tentada no leilão cancela a S antes, é recusada e vira limite no preço da proteção, que com gap contra não executa: o DM abre o contínuo sem stop até o reenvio agressivo (T6).
5. Se a S disparar na abertura antes de tudo isso, a ficha zera e o resto não acontece; isso depende de P13.

**Resposta única e segura: não.** T6 e T7. Depois das duas correções, o caminho é único: S protege até o contínuo, saída agendada em 09:00:30.

### (e) Maestro no PC e na VPS ao mesmo tempo
1. As travas são variáveis globais de cada terminal: as duas instâncias passam o R1.
2. As duas enviam as mesmas entradas com o mesmo magic e o mesmo prefixo `MAE|i1|`; cada uma reconhece as ordens da outra como próprias (4.4, T3). Não há `ESTRANHA`.
3. Fichas são somadas por magic: duas E do mesmo robô → invariante 4 manda cancelar a mais nova (cada instância cancela a "mais nova" pela própria visão; podem cancelar ordens diferentes ou as duas). Se as duas encherem, ficha +2 (estado sem tratamento), duas S, depois duas saídas de volume |ficha| = 2 cada → −2 → ficha trocada corrigida pelas duas instâncias.
4. Memória e logs separados; nenhuma das duas sabe que a outra existe.

**Resposta única e segura: não.** T3 (e T1 para o estado ±2).

---

## 4. Veredito

**Não está pronta para implementar.** O desenho segue certo e 46 dos 54 itens conferidos estão fechados (8 parciais, 0 abertos), mas a 0.3 introduziu três defeitos CRÍTICOS em lugares que a revisão 2 mandou consertar: a resolução da `DESCONHECIDA` em 30 s vale offline e duplica ordem (T1); a `INDETERMINADA` herdou o "sem saída" da antiga `DESCONHECIDA` (T2); e o prefixo constante anula a única defesa entre máquinas (T3). As correções são de texto, localizadas, sem mudar arquitetura.

**Lista mínima para liberar:**
1. **T1:** prazo de 30 s só corre conectado; `NAO_EXECUTADA` exige releitura completa depois da última reconexão e 10 s de conexão contínua; S "não sei" entra no trânsito; tratamento de |ficha| > 1.
2. **T2:** definir "resíduo real do robô" e usá-lo na regra 2, na 8.4, na zeragem e na rede (volume = |resíduo|, ignorando `JA_EM_TRANSITO`); `INDETERMINADA` > 10 min → bloqueio que exige o dono.
3. **T3:** ordem própria = registro; `INST` gerado por máquina e persistido; prefixo só para memória perdida.
4. **T4:** `OnDeinit` só age se a instância detém a trava.
5. **T5:** cruzada inclui a externa desconhecida depois do prazo de R4; esse `PROTEGENDO` sai pelo botão.
6. **T6:** saída recusada recria a S na hora; em leilão a proteção é a S; 8.4 suspensa por até 5 s por tentativa da 5.4.
7. **T7:** nenhuma saída (exceto S) fora do contínuo; saída decidida fora dele é agendada para `negociacao_inicio` + 30 s.
8. Três linhas: R9 não recoloca alvo em ficha trocada; token da trava < 2^53; `TesterStop` do RE desligado no maestro.

Com esses oito itens a especificação pode ir para implementação; o que sobra é MÉDIA/BAIXA ou depende das perguntas P à Rico, que a escada de 15.5 já exige antes do real.
