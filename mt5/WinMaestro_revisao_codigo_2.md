# WinMaestro v1.02 — revisão adversarial do código (2)

Escopo: `mt5/WinMaestro.mq5`, `mt5/WinMaestro/*.mqh`, `mt5/WinMaestro_Teste.mq5`, contra `WinMaestro_ESPECIFICACAO.md` (1.0), as escolhas 1–29 de `WinMaestro_implementacao_notas.md`, os 30 achados de `WinMaestro_revisao_codigo_1.md`, os módulos originais em `mt5/WinSeletor/*.mqh` e `LICOES_DE_PRODUCAO.md`. Abreviações: `F` = `WinMaestro/Fichas.mqh`, `R` = `WinMaestro/Recupera.mqh`, `C` = `WinMaestro/Corretora.mqh`, `EA` = `WinMaestro.mq5`, `T` = `WinMaestro_Teste.mq5`; módulos por nome (`CM`, `C1`, `RE`, `DM`, `GB`). Linhas citadas são as do arquivo atual.

**Placar: 0 CRÍTICAS, 4 ALTAS, 8 MÉDIAS, 9 BAIXAS.** Dos 30 achados da revisão 1: 27 fechados, 3 parciais, nenhum aberto. Um dos 63 testes falha contra o código (T22, seção 5).

---

## 1. Achados da revisão 1, conferidos no código

| # | Situação | Onde (código atual) | Observação |
|---|---|---|---|
| C-1 | FECHADO | `F:1612-1648` (`Mae_Entra`: S antes da E para limite e mercado); `F:1144-1153` (S fora do item 3 do D1); `F:2093` (Fase 2 só espera S em trânsito) | — |
| C-2 | FECHADO | `F:2063-2064` (correção \|f\| ou \|f\|−1 numa ordem); `F:1963-1974` + `F:2093-2141` (S de emergência cobrindo \|f\|, inclusive trocada no contínuo); `F:1403`, `F:1901` (janela conta só correção executada) | Resíduo: S de volume \|f\| vira órfã depois da correção (B-3 abaixo) |
| A-1 | PARCIAL | `F:547-583` (robô pela ordem de origem) | Com magic 0 e a ordem ainda fora do histórico, o deal é classificado externo na mesma leitura (M-5 abaixo) |
| A-2 | FECHADO | `F:1755-1797` (ENVIADA só com `D_CANC`); `F:2026` (refeito pelo maestro); `DM:277-287`, `RE:630-641` | — |
| A-3 | FECHADO | `F:1262-1271` (magic do robô e `setup ≥ envio − 2 s`); `R:121-129`, `R:348` (seq do histórico em toda partida) | — |
| A-4 | FECHADO | `F:836` (`mzReleuOk = false` em falha de histórico) | — |
| A-5 | FECHADO | `F:2363-2366` (`Tick()` sempre depois do `PRONTO`) | Efeito colateral: A-2 abaixo |
| A-6 | FECHADO | `RE:1102-1109` (evento restaura a entrada); `F:2162-2183` (alvo recriado) | Efeito colateral: M-1 abaixo |
| M-1 | FECHADO | `F:759`, `F:979`, `F:1158` (ficha indeterminada) | A indeterminação desliga também a proteção (M-4 abaixo) |
| M-2 | FECHADO | `F:2348` (fases só com a lista lida); `F:2006-2011` (órfã reconferida) | — |
| M-3 | FECHADO | `F:1386-1391` (uma leitura, sem laço); `EA:314-319` (trava conferida a cada segundo) | Trava perdida por variável apagada paralisa tudo (M-8 abaixo) |
| M-4 | FECHADO | `F:1505-1510` (`MARKET_CLOSED` retentado com AVISO por objeto) | Sem lista de feriados, por decisão do dono |
| M-5 | PARCIAL | `F:2061`, `F:2074`, `R:309` | Em PROTEGENDO a Fase 2 ainda recria o alvo do RE (`F:2162` não confere `mzProtegendo`) |
| M-6 | FECHADO | `F:1064-1069` | — |
| M-7 | FECHADO | `F:737-748`, `F:1818-1823` | — |
| M-8 | FECHADO | `F:73` (constantes) | — |
| M-9 | FECHADO | `F:1309-1316` (ALERTA e `mzMemFalhou`) | O bloqueio alcança também cancelamentos e saídas (A-4 abaixo) |
| M-10 | FECHADO | `F:1144-1153`; `F:2343` (texto); `F:2262-2323` (`Mae_CorteConta`) | `Mae_CorteConta` tem defeito próprio (A-1 abaixo) |
| B-1 | FECHADO | `F:2162` (`Mae_Continuo` e `!Mae_Noite`) | — |
| B-2 | FECHADO | `F:2064` (`cancela_a = trocada`) | — |
| B-3 | PARCIAL | `F:482-487`, `F:1810-1813`, `F:1853-1860` | Com a memória perdida, `mzUltDealMsc = 0` e `mzLogTk` vazio: todos os deals da janela são relogados e o resumo dá ALERTA falso (B-4 abaixo) |
| B-4 | FECHADO | `F:1338`, `Log.mqh:161-165` | — |
| B-5 | FECHADO | `F:181`, `F:1503`, `F:2027` (S com retentativa própria; E cancelada só com 10 s sem S) | — |
| B-6 | FECHADO | `F:242-248` | Sem tick no segundo corrente volta à resolução de segundo; resíduo aceitável |
| B-7 | FECHADO | `F:862` (32 por robô) | — |
| B-8 | FECHADO | `Memoria.mqh:88`, `:104` (`FILE_UNICODE`) | — |
| B-9 | FECHADO | `C:76-225` | — |
| B-10 | FECHADO | `F:1207` | — |
| B-11 | FECHADO | `C:100-102` | Ver B-6 abaixo (confirmar o código de erro no Testador) |
| B-12 | FECHADO (documentado) | escolha 28 | — |

---

## 2. Achados novos, por severidade

### ALTA

#### A-1. `Mae_CorteConta` ignora X, E e S em trânsito e zera a líquida com o magic de um robô escolhido por fichas velhas
- **Onde:** `F:2277` (só espera trânsito de papel C e K), `F:2279-2283` (robô do C escolhido por `mzF`), `F:2296-2298`.
- **Cenário (o mais provável de todos: lag de deal no corte).** 18:20:00, GB +1, CM +1, DM +1, líquida +3. A Fase 1 manda a X do GB; ela executa, a posição vai a +2, o deal ainda não está no histórico (P6). `Mae_Prova` dá `D_SEM`, a X fica no trânsito. A cruzada abre (deals +3 × líquida +2); as X do CM e do DM voltam `BLOQUEADA`; a Fase 2 sai (`F:2090`). No mesmo `Mae_Reconcilia`, `Mae_CorteConta` não vê trânsito de C/K, lê a líquida +2 e manda **C de venda 2 com o magic do GB** (o primeiro com ficha do mesmo lado, pela ficha velha). Líquida real 0. Quando o deal da X aparece, os deals dão GB +1 −1 −2, e o C, colocado com a ficha do GB já em 0, é classificado como **E** (`F:757`): GB −2 "duplicada", CM +1, DM +1, cruzada fechando. Antes de F o maestro corrige o GB (compra 1), zera o GB (compra 1), zera o CM e o DM (vende 2): quatro negócios sem razão, exposição real de até +2 durante o caminho, e, se F chegar no meio da sequência, posição real aberta para a noite com S DAY vencendo.
- **Variante:** X sem desfecho ainda em voo na bolsa e cruzada aberta por outro motivo: o C zera a líquida que ainda contém a X; a X executa depois e inverte a conta; o ciclo seguinte manda outro C. A afirmação da escolha 29 ("a ordem não inverte a conta") não vale com ordem em voo.
- **Prova no próprio teste:** T22 (`T:396-412`) monta exatamente o caso (X `DONE_SEM_DEAL` no trânsito, corte 18:20:10) e espera "nada reenviado, S protegendo"; o código cancela a S do C1 e o teste falha (seção 5).
- **Correção:** `Mae_CorteConta` só age sem **nenhuma** ordem de robô em trânsito (9.3, item 5: "a saída espera a prova"), e só depois de a cruzada ficar aberta por um tempo mínimo (ex.: 10 s, o mesmo prazo de releitura), para não confundir lag de histórico com histórico incompleto. O C deve sair com um papel que `Ficha_Calcula` nunca classifique como E (ver A-3).

#### A-2. Saída por regra que volta `BLOQUEADA` é perdida até a próxima vela: CM 2 h, C1 1 h, só com a S
- **Onde:** `F:2363-2366` (módulo roda com ordem do robô sem desfecho); `CM:700-702` (portão de vela consumido antes da decisão) e `CM:726`; `C1:589-597` e `C1:493`, `:518`, `:531`; nenhum registro da intenção de sair no maestro.
- **Cenário:** 12:00:00, o RE aproxima o alvo até o preço (`RE:852-856`, limite que executa na hora) e o deal chega ao histórico alguns milissegundos depois da posição. No mesmo `OnTick`, o C1 (último na ordem fixa) fecha a H1 de 11:00 entre a roxa e a verde e chama `Ficha_Fecha`. A cruzada está aberta pelo lag: `BLOQUEADA verificacao cruzada`. `g_ultima_barra` já foi gravado (`C1:591`): a saída só volta a ser avaliada às 13:00. O CM, no mesmo cenário, fica 2 h com a S de reserva a 4.945 pts (R$989). Outras causas transitórias com o mesmo efeito: ordem do próprio robô sem desfecho (a spec manda pausar o robô sem `Tick()`, 4.4; o código mantém o `Tick()` e o portão de vela anda), os 10 s de leitura não confiável depois de reconexão, ficha indeterminada entre o `DEAL_ADD` e o `HISTORY_ADD` da ordem.
- **Por que é novo:** no avulso, o equivalente era falha de `OrderSend`, rara. No maestro o D1 recusa por estados que duram milissegundos e coincidem com as viradas de vela, quando vários robôs agem no mesmo segundo. É também divergência de equivalência que não aparece no Testador (histórico síncrono).
- **Correção:** o maestro guarda a intenção (`mzSaidaPedida[r]` com motivo e instante) quando `Ficha_Fecha` volta `BLOQUEADA` por estado aberto, e a reenvia a cada reconciliação até `ENVIADA` ou até a ficha zerar. Alternativa: devolver ao módulo um quarto código (`ADIADA`) e, nos módulos com portão de vela, só consumir o portão quando a decisão foi executada.

#### A-3. Saída que executa depois de a ficha já ter zerado vira "entrada": a ficha invertida é tratada como legítima, não como trocada
- **Onde:** `F:757` (papel pela ficha no instante de colocação tem precedência sobre o papel registrado no envio), `F:699` (`mzPorE` vem desse papel), `F:898` (`Mae_Trocada` exige `!mzPorE`).
- **Cenário (item 1.23, risco B6):** C1 comprado, S a 118.700. O módulo lê a ficha +1 e chama `Ficha_Fecha`; a S dispara no intervalo entre a leitura e a chegada da X à bolsa. Deals: S (+1→0) às t1, X (0→−1) com `ORDER_TIME_SETUP` > t1. `Mae_FichaEm(C1, setup)` = 0 → papel **E**, `mzPorE = true`. A spec (§8) diz "S + X = trocada → correção C"; o código entrega ao módulo uma ficha −1 que ele nunca abriu (`Ficha_Tem` verdadeiro, lado −1). Se o preço já se afastou do nível da memória, a Fase 2 cria uma S de compra nesse nível (`F:1966`) e o C1 passa a gerir a operação fantasma (trailing, break-even, saída). A contagem de correções (trava de 10 min, item 1.13) é contornada. Mesmo efeito com A + X no RE e com o C do A-1. Enquanto a ordem não é lida (`ord_ok` falso) o papel vem do mapa (X) e a ficha é trocada; quando a ordem aparece, ela passa a ser legítima: a classificação muda entre dois ciclos.
- **Correção:** ordem com papel conhecido pelo envio (`papel_mapa` ∈ {X, C, A}) nunca vira E; usar o mapa antes da inferência. Sem mapa (EA reiniciado), ordem a mercado colocada com ficha 0 cujo comentário diz `|X|` ou `|C|` também não é E.

#### A-4. Falha persistente de gravação da memória bloqueia cancelamentos, OCO, saídas, zeragens e o corte
- **Onde:** `F:1157` (D1 recusa todo papel ≠ S), `F:1351-1356` (envio ≠ S barrado), `F:1592`.
- **Cenário:** disco cheio, permissão perdida ou `FileMove` falhando de forma contínua. A partir daí: o A do RE enche e a S irmã não é cancelada (exceção (a) do Princípio 4 com o EA no ar); nenhuma E é cancelada por prazo, bloqueio ou zeragem; nenhuma ficha é zerada; às 18:20 nem o corte nem `Mae_CorteConta` saem. As fichas atravessam a noite com o EA ligado e as S DAY vencem. A spec só barra o que aumenta exposição; o bloqueio de entradas (7.2) lista explicitamente que "S, cancelamentos, saídas por regra, zeragens, corte e correções" nunca são barrados.
- **Correção:** com `mzMemFalhou`, barrar só E e A; K, X e C saem, com a linha `ORDEM` no log (que é fonte de recuperação, `R:132-188`) gravada antes do envio e ALERTA por objeto.

### MÉDIA

#### M-1. `EXECUTOU_ANTES` é emitido para qualquer cancelamento que perdeu a corrida, e o RE o lê como "a minha E encheu"
- **Onde:** `F:1895` (todo papel K resolvido `D_ANTES` no trânsito), `F:1777`, `F:2038`; `RE:1102-1109`.
- **Cenário:** o alvo do RE enche; o OCO cancela a S, o cancelamento fica sem desfecho e resolve `D_ANTES` (a S executou junto). O RE recebe `EXECUTOU_ANTES`, religa `g_ordem_pendente` com o lado e os níveis da operação **anterior**, e deixa de armar entrada nova até estourar o TTL (10 velas M15 = 2,5 h). Se nesse instante houver ficha do RE visível, `DetectarPreenchimentoEntrada` reancora S e alvo a partir de níveis de outra operação.
- **Correção:** emitir `EXECUTOU_ANTES` só quando a ordem cancelada era a E do robô (`ticket == mzETicket[r]` ou papel E no mapa); no RE, conferir também o ticket.

#### M-2. A externa de origem desconhecida não entra no passo 4: toda partida espera 60 s e rebloqueia
- **Onde:** `R:319-336` (passo 4 antes da memória), `F:623` (usa `mzExtDesc`, ainda 0), `R:349` (bloqueio do passo 4 mantido depois do passo 5), `F:2460`.
- **Cenário:** o dono já apertou o botão e gravou a externa desconhecida. Em qualquer reinício (inclusive troca de input) o passo 4 não fecha a cruzada, espera 60 s, cria `verificacao cruzada nao fecha em 10 pregoes` e o passo 5 mantém o bloqueio mesmo com a cruzada fechando no passo 6. Contraria 7.2 ("a recuperação só bloqueia de novo por evento não reconhecido") e a escada (o dono precisa apertar o botão em toda partida).
- **Correção:** ler `ext_desc` da memória antes do passo 4, ou refazer a conferência no passo 6 e retirar o bloqueio do passo 4 quando a cruzada fechar com a externa gravada.

#### M-3. Nada sai depois de F: S órfã e E não podem ser canceladas no leilão de fechamento
- **Onde:** `F:355-361` (`Mae_JanelaOrdens` termina em F), usada em `F:1324`, `F:1413`, `F:1440`, `F:1994`, `F:2088`.
- **Cenário:** a zeragem do CM sai recusada às 18:20 e é retentada; executa às 18:24:58. O OCO da S só roda no ciclo seguinte, já depois de 18:25: o cancelamento é barrado e a S DAY fica viva no call. Se o call cruzar o nível, ela abre 1 contrato que atravessa a noite sem stop, com o EA no ar. O mesmo vale para ficha trocada por corrida às 18:24:59: nem S de emergência nem correção. A spec (9.3) permite fora do contínuo criar, mover e cancelar S e cancelar E e A.
- **Correção:** cancelamentos (K) e criação de S liberados até o fim da sessão de negociação da data (call incluído); saídas continuam só no contínuo.

#### M-4. Ficha indeterminada desliga toda a proteção do robô
- **Onde:** `F:1992` e `F:2086` (Fase 1 e Fase 2 saem), `F:1158` (D1 recusa K, X, C); `T:613-622` (T37 exige que nada seja enviado).
- **Cenário:** deal com o magic do robô cuja ordem não aparece no mapa nem no histórico (ordem posta por outra ferramenta com o mesmo magic, histórico da ordem que não carrega). Ficha +1 sem S: nenhuma S é criada, nenhuma órfã é cancelada, a zeragem e o corte não acontecem para o robô, e a cruzada pode estar fechando, então `Mae_CorteConta` também não age. A posição atravessa a noite com o EA no ar, com um ALERTA.
- **Correção:** a indeterminação barra decisões do módulo e entradas, não a proteção: Fase 2 cria S de emergência para `mzF[r] ≠ 0`; depois de N segundos indeterminada, a ficha é tratada como trocada (correção e corte).

#### M-5. Deal sem `DEAL_MAGIC` cuja ordem ainda não chegou ao histórico é classificado externo na hora (P2)
- **Onde:** `F:546` e `F:557-583` (sem ordem achada, `robo` fica −1), `F:767-799` (absorção na mesma leitura).
- **Cenário (se P2 responder "o deal de pendente vem sem magic"):** `OnTradeTransaction(DEAL_ADD)` dispara `Mae_Reconcilia` antes do `HISTORY_ADD` da ordem. A S do RE executa com magic 0; a ordem ainda não está em `mzHo` e `LeOrdemHist` falha; o deal reduz a líquida e absorve a ficha do **GB** (primeiro da ordem fixa), o OCO cancela a S do GB, o bloqueio é gravado na memória. No ciclo seguinte a ordem aparece e o deal volta ao RE, mas o bloqueio fica até o botão e a S do GB é recriada com outro nível (`mzStopNivel` zerado por `Mae_Limpeza`).
- **Correção:** deal de magic 0 sem ordem localizada fica pendente (sem efeito em ficha e externa) até a ordem ser lida ou até alguns segundos; só então vira externo.

#### M-6. Prova "não executada" aos 30 s ignora ordem viva do robô quando o ticket é 0 e o comentário não sobrevive (P3)
- **Onde:** `F:1260-1272` (busca só por comentário), `F:1291-1295`, `F:1890-1894`; `DM:603-606`.
- **Cenário:** a E do DM volta `TIMEOUT` com ticket 0 e entrou no livro; a corretora não preserva o comentário. Aos 30 s, com leitura confiável e cruzada fechando, o trânsito resolve `D_NAO` e o DM recebe `ENTRADA_CANCELADA` (`g_ordem = 0`). A E está viva (o maestro a adota por magic, `F:1925-1929`), mas o DM não a cancela mais pelo prazo de 15 min: ela fica no livro até 18:20 (item 1.8). Mesmo erro de prova para S e X, sem efeito na ficha.
- **Correção:** antes de concluir `D_NAO`, procurar ordem viva ou histórica do robô com o mesmo tipo, preço e volume e `setup ≥ envio − 2 s`.

#### M-7. O fallback DAY do GB falha sempre que o cancelamento da primeira S não se prova na primeira leitura
- **Onde:** `GB:290-296`, `F:1641` (S cancelada depois da E recusada), `F:1602` (`Mae_TemTransito` → `SEGUNDA_ENTRADA`).
- **Cenário:** se a B3 recusa validade `SPECIFIED` com horário (P15), a primeira E volta `RECUSADA`, o maestro cancela a S; se o cancelamento sair sem desfecho (histórico ainda sem a ordem), a segunda chamada é barrada por "segunda entrada" e `g_decidido` já está verdadeiro: o GB não opera no dia. No Testador o histórico é síncrono e o problema não aparece.
- **Correção:** para o fallback, reaproveitar a S viva (não cancelar e recriar) ou aguardar o desfecho do cancelamento antes de devolver ao módulo.

#### M-8. Variável global da trava apagada paralisa o maestro inteiro, inclusive as S
- **Onde:** `R:71-75` (`GlobalVariableCheck` falso = trava perdida), `EA:314-318`, `F:1133` (D1 recusa até a S), `F:1992`, `F:2086`.
- **Cenário:** o dono apaga variáveis globais pela janela F3, ou outro programa no terminal chama `GlobalVariablesDeleteAll`. A partir do segundo seguinte nenhuma S é recriada, nenhuma órfã é cancelada, nada é zerado no corte, até o EA ser reiniciado. Um único ALERTA.
- **Correção:** variável ausente (ninguém a detém) → retomar com `GlobalVariableSetOnCondition` e AVISO; só valor de outro token significa trava perdida.

### BAIXA

| # | Onde | Achado | Correção |
|---|---|---|---|
| B-1 | `R:361-393` × `R:411` | Eventos `Robo_Evento` emitidos nos passos 6–9 (E sumida, `D_NAO`, `D_ANTES`) chegam a módulos ainda não iniciados; o `Init` do passo 10 importa o estado anterior por cima (item 4.33). DM e RE se recompõem por consulta ou TTL; o RE fica até 10 velas sem armar. | Enfileirar os eventos e entregá-los depois de `Robo_InitTodos`. |
| B-2 | `F:2162` | Em PROTEGENDO a Fase 2 recria e move o alvo do RE (M-5 da revisão 1, parte restante). | Exigir `!mzProtegendo` para A. |
| B-3 | `F:954`, `F:2115` | S de volume \|f\| criada para ficha duplicada vira órfã depois da correção (volume > necessidade), é cancelada, e a S de volume 1 só nasce 2 s depois: 2–3 s sem stop. | Criar a S complementar sempre com volume 1 por contrato excedente. |
| B-4 | `F:530`, `F:1810-1814` | Com a memória perdida, todos os deals da janela são relogados como `ENTROU`/`SAIU`: o resumo dá ALERTA de contagem falso (item 1.21). | Na partida sem memória, marcar como já logados os deals cujas linhas existem no log do dia. |
| B-5 | `F:1105-1116` | A autonegociação só confere limites; uma S de um robô que dispara contra a limite de outro no mesmo nível casa com a própria conta (P12). | Até P12, conferir também S contra limites opostas de outros robôs. |
| B-6 | `C:100-102` | Se `PositionSelect` sem posição devolver erro diferente de 4753 neste build, `mzLiqOk` fica sempre falso com a conta zerada e o EA nunca opera. | Confirmar no primeiro dia de Testador (log `HISTORICO` no passo 4). |
| B-7 | `F:1335`, `F:1598`, `F:832` | Todo `BLOQUEADA` liga `mzReler`; um módulo que repete a chamada a cada tick (GB depois de `g_exp`, `GB:322`) provoca releitura completa de até 10 pregões por tick enquanto a cruzada estiver aberta. | Limitar a releitura por estado aberto a uma a cada 10 s (como `F:832` já faz para a cruzada). |
| B-8 | `F:1896-1900`, `F:1937`, `F:1503-1504` | `mzECancelPedido` nunca é desligado depois de o cancelamento ser confirmado (só na E seguinte), e `mzProxTent`/`mzRecusas` são compartilhados por alvo, correção, zeragem e cancelamento: uma recriação de alvo recusada atrasa a zeragem do RE em até 5 s e soma recusas de papéis diferentes no mesmo ALERTA. | Contadores e prazos por papel. |
| B-9 | `F:1602`, `F:1641`, `F:1793` | Cancelar a E e armar outra na mesma vela (CM `:738-751`, RE `:951-1000`) é barrado no real sempre que o cancelamento da S anterior fica sem desfecho; no Testador funciona. Entrada perdida, sem risco. | Mesma correção de M-7 (reaproveitar a S). |

---

## 3. Áreas de maior risco: resumo do que foi conferido

| Área | Situação |
|---|---|
| S antes de E | Correta nos cinco robôs (`F:1612-1648`). O caminho reverso (E recusada → cancela S) cria os efeitos M-7 e B-9. |
| Envio sem espera; tick × timer × transação | O MQL5 serializa os eventos: não há reentrância. A leitura não é atômica (posição, pendentes e histórico em três chamadas); os dois casos de leitura no meio de uma atualização (E listada e deal já visível; E fora da lista e deal ainda não) estão cobertos pela reconferência da órfã (`F:2006-2011`) e por `mzETicket` (`F:928`). O custo dessa não atomicidade é a cruzada aberta por milissegundos, que alimenta A-1 e A-2. |
| Correção numa ordem só | Correta (`F:2063-2064`); a classificação do C como E (A-3) e B-3 são os resíduos. |
| Ficha indeterminada | M-4 (desliga a proteção) e M-5 (magic 0 não entra na indeterminação). |
| `Mae_CorteConta` | A-1. |
| Cancelamento de E refeito a cada 5 s | Correto: só depois de o cancelamento anterior ter prova (`F:1992`, `F:2026`), sem rajada. B-8. |
| Trava a cada segundo | Correta contra outro gráfico; M-8 contra variável apagada. |
| Leitura não confiável | Correta (`F:852-857`); a S passa sem portão (escolha 19), o que em T28 cria S para ficha cuja X já executou e cujo deal ainda não chegou (S órfã cancelada depois). |
| Módulos calculando sempre | A-2 e B-1. |

---

## 4. Cenários simulados contra o código

**(a) MT5 morto com CM e RE comprados; a S do RE executa; o alvo do RE enche com o EA fora; o EA volta.** Deals: RE +1 (E), −1 (S, papel S), −1 (alvo, `SELL_LIMIT` colocado com ficha +1 → papel X, `F:757`); `Ficha_Aplica` abre −1 sem E → trocada. Passo 4: Σ deals de hoje = 0 = líquida (CM +1, RE −1). Passo 6: `RECUPERA`/`SAIU` com "(EA fora)" e a hora real (`F:1816-1838`). Passo 7: nada vivo do RE. Passo 8: S do CM conferida e movida ao nível da memória; o RE trocado recebe S de compra de emergência a `mzPm + 1.200` (`F:2093-2141`); nenhum alvo (`Ficha_Tem` falso). Passo 9: correção C de compra 1 com o magic do RE (se a S do passo 8 ficou sem desfecho, a correção espera o ciclo seguinte); executada, a S de emergência é cancelada. O módulo RE importa "em posição" e `LimparAlvoOrfao` desfaz no primeiro tick. **Resposta única e segura.**

**(b) Saída a mercado do C1 com `TIMEOUT`, internet fora 90 s.** A X entra no trânsito (`F:1386-1402`), a S fica. Desconectado: `Mae_LeituraConfiavel` falso, nada se prova; a Fase 1 do C1 sai pelo trânsito; a Fase 2 só age se faltar S. Na volta: releitura completa (`F:810-816`), 10 s até leitura confiável. Executou: o deal aparece, a ficha vai a 0, a S é cancelada pelo OCO. Não chegou: aos 30 s de idade, com leitura confiável e cruzada fechando, `D_NAO`; a S continua e o C1 repete a saída pela regra dele (próxima H1 ou próxima M1 do break-even). **Única e segura**, com duas ressalvas: a S pode executar junto com a X (B6 aceito), e então a ficha invertida é classificada como E em vez de trocada (A-3); e se a posição e o histórico voltarem defasados juntos na reconexão, `D_NAO` sai sem a X ter falhado (O6 continua condicional a P6/P18).

**(c) O dono zera tudo na mão com GB e DM posicionados.** Venda manual de 2, magic 0, ordem no histórico com magic 0 → externa (`F:546-583`). Reduz a líquida abaixo de Σ fichas: absorve GB e depois DM (`F:785-795`); `ABSORVIDA` por ficha e um bloqueio por deal (`F:1846-1870`). OCO imediato das S e dos alvos das fichas absorvidas (`F:2002`); E de todos cancelada pelo bloqueio (`F:2024`), S delas canceladas depois. O botão grava os deals como reconhecidos; reinício não rebloqueia (`F:1853-1860`); GB e DM não reentram (`g_decidido`, `g_decidiu`). **Única e segura.** Ordem dos cancelamentos por robô (S do GB antes da E do CM), não "A, E, depois S" da 7.1: sem efeito na exposição. CM, RE e C1 podem armar entrada nova numa vela seguinte depois do botão (sinal novo, não reenvio).

**(d) Ficha da noite com gap contra.** Janela recua um pregão (`F:614-639`); `Mae_Noite` verdadeiro; nível de stop da memória mantido para ficha aberta (`F:2490-2492`). Antes de 08:55 nada sai. Na pré-abertura, S DAY nova; se bid/ask indicativos já estão além do nível, nenhuma S e ALERTA por objeto (`F:2118-2128`). Primeiro segundo de contínuo: X pela Fase 1 (`F:2071`); a S só cai depois do deal. Os módulos rodam no leilão (CM pode mover a S nova para o stop que aperta; nenhum envio de saída fora do contínuo). **Única; segura dentro do risco aceito (B10).** Em feriado: retentativa com AVISO.

**(e) Cinco robôs entrando no mesmo segundo às 10:00, dois em lados opostos.** Processamento serial na ordem fixa dentro do mesmo `OnTick`; cada entrada relê tudo (`F:1586`, `F:1131`) e manda S antes da E. Limite de um robô que cruze limite oposta viva de outro volta `AUTONEG` (`F:1105-1116`); a mercado do C1 contra limite própria no topo do livro também. S de lados opostos coexistem. **Segura** (nenhuma posição sem S, nenhuma autonegociação por limite), **mas não equivalente ao avulso no real:** se a E marcável do primeiro robô enche e o deal chega depois da posição, a cruzada abre por milissegundos e as entradas seguintes do mesmo segundo voltam `BLOQUEADA`; o C1 só reavalia na H1 seguinte (A-2). No Testador o histórico é síncrono e isso não acontece; os `AUTONEG` do teste 2 têm de ser listados.

**(f) Corte às 18:20 com a cruzada aberta.** Fase 1: órfãs, E e saídas `BLOQUEADA`; Fase 2 sai sem criar S (`F:2090`). `Mae_CorteConta`: posição ilegível → nada, ALERTA por minuto; legível → C de −líquida com o magic do primeiro robô com ficha do mesmo lado; líquida real 0 → cancela todas as pendentes dos robôs. **Não é única nem segura** quando há qualquer X, E ou S em trânsito, que é o caso típico de cruzada aberta às 18:20 (lag do deal da primeira zeragem): A-1. Sem trânsito e com histórico de fato incompleto, o resultado é a líquida real zerada e as fichas daquele robô deslocadas pelo C (correções e zeragens adicionais quando a cruzada voltar a fechar antes de F).

**(g) E do DM enchendo enquanto o cancelamento por TTL está em voo.** `Ficha_Cancela` → `Mae_Cancela`: a corretora responde ordem inexistente (recusa definitiva) ou fica sem resposta. Com o deal visível, `Mae_Prova` dá `D_ANTES` (`F:1244`, `F:1255`), `EXECUTOU_ANTES` ao DM, `BLOQUEADA` ao módulo; com o deal atrasado, `D_SEM`, o trânsito resolve depois. A S está no servidor desde antes da E (`F:1625`), protege a ficha +1 o tempo todo. No tick seguinte com `Ficha_Tem`, `AjustarStop` reancora a S e zera `g_ordem` (`DM:420-444`). `mzECancelPedido` fica ligado sem efeito. **Única e segura.**

---

## 5. Testes

**Os 63 casos nunca foram executados, e um deles falha contra o código.** T22 (`T:396-412`): X do C1 com `FM_DONE_SEM_DEAL` às 17:49:50; às 18:20:10 a cruzada está aberta (líquida 0, deals +1) e `Mae_CorteConta` (`F:2277`) não espera a X: com a líquida real 0, cancela a S do C1. `p2` exige `F.m_envios == n0` e a S viva; os dois falham. O teste descreve a regra da spec (9.3, item 5); o código está errado (A-1).

**Passam por construção ou testam a falsa:**
- T35: `Mae_PodeTick` é sempre verdadeiro com `mzPronto`; o achado A-5 da revisão 1 (o RE processar a vela das 18:15 no leilão) não é exercitado, porque os módulos não são compilados no EA de teste.
- T51: o relógio da falsa e o `time_msc` do tick são o mesmo número.
- T39 (segunda metade): a falsa não tem `Sleep`; `F.Agora() == 10:00:00` é verdadeiro sempre.
- T58: chama `Mae_RequestVisto` direto; depende de a falsa preencher `request_id` também em `TIMEOUT`, o que o MT5 real não garante.
- T26: a falsa aceita `MODIFY` em qualquer preço, inclusive do lado errado do mercado.
- T21, T34, T45, T46: chamam `Mae_Fase2(r, true)` direto, pulando a espera de 2 s e a ordem Fase 1 → Fase 2 da reconciliação.

**Testes que fixam comportamento inseguro como correto:**
- T37: ficha indeterminada sem S e "nada enviado" é o resultado esperado (M-4).
- T28: S recriada para ficha cuja X já executou (deal oculto, posição já zerada); a S nasce para uma posição que não existe e só cai como órfã depois.

**Caminhos críticos sem teste:**
- `OnTradeTransaction` e `OnTimer` reais (o EA de teste não compila `WinMaestro.mq5`); a ordem `DEAL_ADD` antes de `HISTORY_ADD` (M-5).
- Os cinco módulos: tratamento de `BLOQUEADA` com portão de vela (A-2), `EXECUTOU_ANTES` no RE (M-1), fallback DAY do GB (M-7), cancelar e rearmar na mesma vela (B-9).
- `Mae_CorteConta` com X em trânsito (A-1; T22 cobre e falha).
- Corrida S + X e A + X com a segunda ordem colocada depois do zero (A-3).
- `mzMemFalhou` com ficha aberta no corte e OCO pendente (A-4; T44 só cobre a entrada).
- Trava com a variável apagada (M-8); `Trava_Toma` real (o Testador pula).
- Partida com externa desconhecida gravada (M-2); partida PROTEGENDO; passo 4 esgotando os 60 s.
- Cancelamento e S depois de F (M-3).
- Prova `D_NAO` com a E viva e comentário perdido (M-6).
- Ficha da noite com nível já atravessado na pré-abertura; saída da noite recusada no leilão prorrogado.
- Entradas simultâneas de vários robôs com cruzada transitória (cenário e).
- `LeLiquida`/`LePendentes` reais (B-6).

---

## 6. Equivalência com o Testador: o que diverge além da §12

1. **Primeiro dia do teste:** decisões anteriores ao `PRONTO` (11 passos de timer depois do primeiro tick válido) viram `DECISAO PERDIDA` (`F:1580-1585`). Excluir o primeiro dia ou contar esses trades.
2. **Teste 2:** `AUTONEG` em E e em alvo do RE (`F:1180-1185`, `F:1453`) muda trades e não está na lista permitida.
3. **Saídas e entradas `BLOQUEADA` com portão de vela (A-2):** no Testador não acontecem (histórico síncrono, nenhuma ordem sem desfecho); no real acontecem. A equivalência medida no Testador não cobre essa divergência; ela só aparece na escada (degrau de 2 robôs).
4. **Dia de vencimento com o gráfico no contrato específico:** corte 16:55 (`Grade.mqh`), entradas de C1 e CM barradas depois disso; o avulso entrava. Com `WIN$N` (como manda a §12) não ocorre.
5. **GB com `SPECIFIED` recusado:** o avulso tentava DAY em qualquer falha; o maestro só em `RECUSADA` (escolha 10). No Testador a recusa é definitiva, então coincide; no real não (M-7).
6. **Qualquer linha `ESTADO`, `CORTE_CONTA`, `TROCADA`, `DUPLICADA` ou `CORRECAO` no log do Testador** é divergência a contar: no Testador nenhuma delas deveria existir.

O resto (zeragem pelo timer, S viva desde a E, reserva do CM, CM às 18:20, teto do DM, stop do DM no servidor) está na lista permitida.

---

## 7. Resposta

**Contagem:** CRÍTICA 0 · ALTA 4 · MÉDIA 8 · BAIXA 9. Revisão 1: 27 fechados, 3 parciais (A-1, M-5, B-3), 0 abertos.

**ALTAS:**
- A-1: `Mae_CorteConta` não espera X/E/S em trânsito e zera a líquida com o magic de um robô escolhido por fichas velhas; no lag típico das 18:20 isso gera negócios extras, exposição transitória e risco de posição aberta em F (T22 falha por isso).
- A-2: saída por regra `BLOQUEADA` por estado aberto transitório é perdida até a próxima vela (CM 2 h, C1 1 h), com o robô protegido só pela S.
- A-3: saída que executa depois de a S zerar a ficha é classificada como E; a ficha invertida vira operação legítima do módulo, em vez de trocada corrigida (§8).
- A-4: falha persistente de gravação da memória bloqueia cancelamentos, OCO, zeragens e o corte; as fichas atravessam a noite com o EA no ar.

**Veredito:** **pronto para o Testador** (teste de equivalência 1 e 2): nenhum dos achados põe dinheiro em risco lá, e os itens da seção 6 dizem o que contar como divergência. **Não pronto para a demo:** A-1 está no caminho do teste de falha 10 e do corte de todo dia, A-2 e A-3 aparecem nos testes de falha 3 e 13, e T22 precisa passar antes de a suíte valer como evidência.
