# WinMaestro v1.00 — revisão adversarial do código

Escopo: `mt5/WinMaestro.mq5`, `mt5/WinMaestro/*.mqh`, `mt5/WinMaestro_Teste.mq5`, contra `WinMaestro_ESPECIFICACAO.md` (1.0), as 25 escolhas de `WinMaestro_implementacao_notas.md`, os módulos originais em `mt5/WinSeletor/*.mqh` e `LICOES_DE_PRODUCAO.md`. Abreviações: `F` = `WinMaestro/Fichas.mqh`, `R` = `WinMaestro/Recupera.mqh`, `C` = `WinMaestro/Corretora.mqh`, `M` = `WinMaestro/Memoria.mqh`, `EA` = `WinMaestro.mq5`. Linhas citadas são as do arquivo atual.

Placar: **2 CRÍTICAS, 6 ALTAS, 10 MÉDIAS, 12 BAIXAS.** O EA de teste não tem caminho para a corretora real (seção 6).

---

## 1. Achados, por severidade

### CRÍTICA

#### C-1. Entrada limite: a S só sai depois da E, e qualquer ordem sem desfecho do robô impede a S — ficha aberta sem stop
- **Onde:** `F:1447-1467` (`Ficha_EntraLimite`), `F:999` (item 3 do D1 vale também para S), `F:1778` e `F:1852` (`Mae_Fase1`/`Mae_Fase2` saem cedo com trânsito).
- **Cenário 1 (E sem desfecho):** CM manda a E (limite marcável: `Entra` põe a limite em `MathMin(limite, ask)`, enche na hora). `OrderSend` volta `TIMEOUT`, ticket 0, e o comentário não aparece nas pendentes nem no histórico (P3 em aberto) e o `request_id` só chega depois, no `OnTradeTransaction` enfileirado. `Mae_Envia` devolve `ENVIADA` com `D_SEM` e `Ficha_EntraLimite` retorna em `F:1467` **sem mandar S**. A E encheu: a ficha é ±1. Enquanto a E estiver no trânsito, `Mae_EstadoFecha` recusa toda S (`"robo tem ordem sem desfecho"`, `F:999`) e `Mae_Fase2` nem tenta (`F:1852`). A posição fica sem stop até a prova: no melhor caso até o próximo evento de transação, no pior até `IDADE_PROVA` (30 s); sem leitura confiável (internet oscilando, que é justamente quando há `TIMEOUT`), indefinidamente.
- **Cenário 2 (S sem desfecho):** E viva, S volta `TIMEOUT` sem ter entrado no livro. A regra "sem S em 5 s → cancela a E" (`F:1804`) não roda, porque `Mae_Fase1` sai em `F:1778` com o trânsito da S. Se a E encher, mesma situação.
- É o mesmo mecanismo do item 1.25 das lições ("um portão de ordem em trânsito desligava a conferência por inteiro").
- **Correção:** (1) para todo robô, mandar a S **antes** da E, como já é feito no C1 (`Ficha_EntraMercado`). A infraestrutura existe: `Mae_EstadoFecha(..., s_da_entrada_mercado=true)` aceita S com ficha 0. Para a limite isso é seguro pela mesma razão que a spec aceita no gap (5.3): para a S disparar, o preço precisa atravessar o nível da E. (2) Tirar S e cancelamento de S do item 3 do D1 quando a S protege o lado de `e.lp` e não existe outra S viva; em `Mae_Fase2`, não sair por trânsito quando `e.f != 0 && e.iS < 0`.

#### C-2. Ficha trocada ou duplicada no contínuo pode ficar sem stop indefinidamente (escolhas 19 e 25)
- **Onde:** `F:1822-1838` (correção), `F:1825-1831` (trava da 2ª correção em 10 min), `F:1860` (`Mae_Fase2` não cria S para trocada no contínuo), `F:1371` (correção de duplicada com volume 1).
- **Cenário A (trocada):** RE com S e A; o OCO perde a corrida, as duas executam, ficha −1 (trocada). A correção C sai e volta `RECUSADA` (ou `BLOQUEADA` por leitura/cruzada). `Mae_Recusa` agenda a nova tentativa em 5 s, mas `Mae_Fase2` retorna em `F:1860`: nenhuma S. Se for a segunda correção do robô em 10 min, `mzCorrTravada` vira true, entra o bloqueio e **nem correção nem S** acontecem até o dono apertar o botão. É posição invertida e nua no contínuo.
- **Cenário B (duplicada |f| ≥ 3):** a primeira correção leva |f| de 3 para 2. Um segundo depois, `Mae_Fase1` vê duplicada de novo com `mzUltCorrecao` a menos de 600 s, trava e bloqueia. Ficam 2 contratos com uma S de volume 1: **1 contrato sem stop** até o dono agir. O resultado é determinístico para qualquer |f| ≥ 3. A mesma trava dispara quando uma correção C de volume 2 enche parcialmente (B3 com `RETURN`): a sobra vira órfã e é cancelada, a ficha fica trocada de novo dentro dos 10 min e trava.
- **Correção:** (1) trocada no contínuo sem correção executada em `RETENTA` s, ou com `mzCorrTravada`, recebe S de emergência (`STOP_EMERGENCIA_PTS`). O risco de a S executar junto com a correção é o mesmo B6 aceito no resto da spec, e a seção 8 já o corrige. (2) Duplicada: corrigir `|f| − 1` numa ordem só. Com a trava ativa, mandar S com volume `|f|` (ou uma S por contrato excedente). (3) A janela de 10 min deve contar correções **executadas**, não tentativas.

### ALTA

#### A-1. Fill de pendente sem `DEAL_MAGIC` vira deal externo, e a S da ficha é cancelada como órfã (P2 em aberto)
- **Onde:** `F:473` (`c.robo = Mae_Robo(d[i].magic)`), `F:671-702`, `F:1723`, `F:1783-1796`.
- **Cenário:** se o deal de uma limite ou stop pendente vier com magic 0 (P2 ainda sem resposta), a E do GB enche, o deal cai na externa (+1, AVISO), a ficha do GB fica 0, `Mae_EControle` vê o deal da ordem e zera `mzETicket`, e a S do GB vira órfã: cancelada. A conta fica comprada 1, na "externa", **sem stop e sem zeragem** (o maestro não zera externa).
- **Correção:** quando `DEAL_MAGIC == 0` e a ordem do deal (`DEAL_ORDER`) está no histórico com magic de robô, usar `ORDER_MAGIC`. `mzHo` já tem esse campo; basta resolver o robô depois de `Mae_Mescla` ler a ordem. Logar `AVISO` uma vez se isso acontecer, porque responde P2.

#### A-2. Cancelamento de E que não confirma nunca é retentado, e DM/RE esquecem a E viva
- **Onde:** `F:1596` (`D_SEM` devolve `ENVIADA`), `F:1588` (`BLOQUEADA`), `F:1799-1818` (o maestro só cancela a E por bloqueio, zeragem ou falta de S); `WinDeslocamentoMatinal.mqh:277-285` (`g_ordem = 0` incondicional), `WinRetanguloEma34.mqh:631-645` (estado limpo incondicional).
- **Cenário:** às 10:45 o DM cancela pelo prazo de 15 min. O `OrderDelete` fica sem desfecho, ou volta `BLOQUEADA` porque a leitura deixou de ser confiável por alguns segundos depois de uma reconexão. O módulo zera `g_ordem` e nunca mais tenta. Se o cancelamento resolver `D_NAO` (ordem segue listada), ninguém o refaz: `mzECancelPedido` só silencia o aviso. A E fica no livro até a zeragem (18:20 no DM, 17:00 no RE) e pode encher horas depois. É o caso "ordem que ninguém está vigiando" (item 1.8), com o atraso já medido no projeto (269,7 min). No RE, o fill não é adotado (A-6): a posição fica sem alvo e com a S não reancorada.
- **Correção:** com `mzECancelPedido[r]` verdadeiro e a E ainda viva (`e.iE >= 0`) e sem trânsito, `Mae_Fase1` retenta o cancelamento a cada `RETENTA`, com ALERTA na 5ª tentativa (item 1.13). `Ficha_Cancela` deve devolver `BLOQUEADA` (não `ENVIADA`) enquanto não houver `D_CANC`, e DM/RE só devem limpar o estado ao receber `ENTRADA_CANCELADA` (ou com `Ficha_Entrada` falso).

#### A-3. Ticket achado pelo comentário sem filtro de tempo: prova errada quando o comentário se repete
- **Onde:** `F:1109-1115` (`Mae_Prova`: percorre `mzPend` e `mzHo` sem `break` e sem filtro), `F:391-401` (`seq` zera todo dia), `R:332` (`seq` só é refeito do histórico com a memória perdida), `M:88-94` (falha de gravação silenciosa, M-9).
- **Cenário 1:** ficha do C1 da noite (ou cruzada que não fecha) faz a janela cobrir ontem. Hoje a X `MAE|C1|X|0003` volta `TIMEOUT` sem ticket e ainda não está no histórico. A busca casa com a `MAE|C1|X|0003` **de ontem**, que executou: `D_EXEC` falso. O trânsito sai, o módulo volta a operar achando que saiu, e se a X verdadeira estiver em voo, a próxima saída do módulo inverte a ficha (item 1.23).
- **Cenário 2:** a memória válida está um envio atrás (gravação falhou em silêncio). Na partida, `mzSeq` vem da memória, e o próximo envio reusa um `seq` que já existe no histórico de hoje, com a mesma colisão.
- **Correção:** na busca por comentário, aceitar só ordens com o magic do robô e `setup_msc >= (hora_do_transito − 2 s) × 1000`, e parar no primeiro achado. Rodar `Rec_SeqMax` sobre `mzHo` e `mzPend` em **toda** partida (não só com `st >= 2`). Opcionalmente, pôr o dia no comentário: `MAE|CM|E|0704|0042` tem 19 caracteres, dentro do limite de 31.

#### A-4. Leitura do histórico que falha deixa o estado "confiável" com fichas velhas
- **Onde:** `F:740` (`if(!ok) { mzReler = true; return; }`), `F:747-752`.
- **Cenário:** `HistorySelect` ou `HistoryDealGetTicket` falha (`C:130`, `C:135`) no instante em que a S do GB acabou de executar. `mzCruzOk`, `mzReleuOk` e `mzF` ficam com os valores da leitura anterior (GB +1). O GB pede `Ficha_Fecha`, o D1 passa com o estado velho e a X de venda 1 sai: a conta, que estava flat, fica vendida 1, sem S. É uma ficha trocada criada pelo próprio maestro, e a correção pode cair em C-2.
- **Correção:** em falha de leitura, `mzReleuOk = false` (ou `mzCruzOk = false`), para que `Mae_LeituraConfiavel` recuse até uma releitura completa funcionar.

#### A-5. RE perde a última vela do pregão anterior: divergência de sinal contra o avulso
- **Onde:** `F:339-345` e `F:2054` (`Tick()` só a partir de `negociacao_inicio`); `WinRetanguloEma34.mqh:710-727` (`VelaParaProcessar`), `:1007-1023`.
- **Cenário:** no avulso, o primeiro tick do dia chega no leilão de abertura (08:55; o próprio módulo documenta as cotações indicativas desse intervalo). Nesse tick, a vela de shift 1 é a última do pregão anterior (18:15), que entra na janela do detector (`AcrescentarBarraDia`). No maestro, o primeiro `Tick()` do RE é às 09:00, quando a vela de shift 1 já é a de 08:45 (leilão), que zera a sessão e é descartada. A vela das 18:15 de ontem **nunca entra**. A janela de `3 × JanelaBarras` difere em uma vela, o que pode mudar topo, piso, contração e o retângulo detectado. Não está entre as diferenças permitidas da seção 12: quebra o teste de equivalência 1 do RE. Os outros quatro módulos não dependem disso: GB decide às 09:05; CM, C1 e DM leem barras com `Copy*` e o primeiro processamento cai na mesma vela.
- **Correção:** entregar ao RE os ticks desde `preabertura_inicio` (as entradas já são barradas por `Mae_PodeEntrar`, que exige `Mae_JanelaTick`), ou fazer o RE, no primeiro `Tick` do dia, processar as velas fechadas posteriores a `g_ultima_vela_processada` que o avulso teria processado. Confirmar no Testador comparando a janela `g_*_dia` dos dois EAs às 09:15.

#### A-6. RE: fill que chega depois de o módulo dar a E por cancelada não é adotado, e o alvo recusado nunca é recriado
- **Onde:** `WinRetanguloEma34.mqh:631-645` (só adota `EXECUTOU_ANTES` síncrono), `:803-806` (`DetectarPreenchimentoEntrada` exige `g_ordem_pendente`), `:818-821` (alvo `BLOQUEADA`/`RECUSADA` deixa `g_ticket_alvo = 0`), `:843` (`AproximarAlvo` sai com `g_ticket_alvo == 0`); `F:1926` (A só é recriado com `partida`).
- **Cenário 1:** o cancelamento da E fica sem desfecho, o módulo limpa o estado, e depois o trânsito resolve `D_ANTES` (`F:1687`). O evento liga `g_executou_antes`, mas nada o consome. O RE tem ficha +1 que não gere: sem alvo, S no nível pré-calculado (não reancorado), até a zeragem das 17:00.
- **Cenário 2:** `Ficha_DefineAlvo` no fill volta `BLOQUEADA` por autonegociação (limite própria de outro robô no preço) ou por leitura não confiável momentânea. O RE fica sem alvo para o resto da operação; o avulso tinha alvo.
- **Correção:** `Evento(EV_EXECUTOU_ANTES)` restaura `g_ordem_pendente` a partir do lado e dos níveis originais guardados (`g_lado_entrada`, `g_*_original`), para `DetectarPreenchimentoEntrada` adotar. Em `Mae_Fase2`, recriar a A sempre que `mzAlvoNivel[r] > 0`, `Ficha_Tem(r)` e `e.iA < 0` (não só na partida), respeitando `mzProxTent`.

### MÉDIA

#### M-1. Deal cuja ordem ainda não foi lida é classificado como E (escolha 2)
- **Onde:** `F:663`, `F:616`, `F:816`, `F:820`.
- **Cenário:** a S do GB executa antes da E (transitório, 5.3), mas a ordem da S ainda não está no histórico (`ord_ok` falso). O papel vira `P_E`, então `mzPorE` fica verdadeiro e a ficha −1 passa a ser "legítima", não transitória. A E viva vira órfã e é cancelada. `Mae_Fase2` cria uma S de compra no nível de venda, que já está atravessado, e manda saída a mercado. O resultado econômico acaba flat, mas com ordens que a spec não prevê, aviso errado ao módulo e alguns segundos de ficha invertida sem stop. Com o alvo do RE a situação é análoga.
- **Correção:** deal de robô com `ord_ok` falso deixa a ficha "indeterminada": `Ficha_Tem` falso, nenhuma órfã, saída ou S nova para esse robô, até a ordem ser lida (ou até 30 s; aí ALERTA). Alternativa: usar `trans.order_type` do `OnTradeTransaction(DEAL_ADD)` como fonte do tipo.

#### M-2. Órfãs decididas sobre lista de pendentes parcial, e o cancelamento não revalida
- **Onde:** `C:111` (lista parcial quando a ordem some no meio da iteração), `F:2024` (`Mae_Reconcilia` só confere `mzLiqOk`), `F:1783-1796`, `F:1026-1028` (o D1 do papel K só pergunta se a ordem está viva).
- **Cenário:** logo após uma partida, com `mzETicket` = 0, a E do DM não está na lista parcial. A S dela é dada por órfã (`lp = 0`) e o cancelamento sai: `Mae_Cancela` relê, a lista completa volta, mas o papel K não confere se a ordem continua órfã. A S é cancelada. A E pode encher na janela até `Mae_Fase2` recriar a S.
- **Correção:** `Mae_Reconcilia` não roda as fases 1 e 2 com `!mzPendOk`. No papel K, refazer `Mae_Estado` e conferir que o alvo continua em `e.orfas` (ou é a E/A pedida pelo módulo).

#### M-3. Espera bloqueante de até 5 s por envio (escolha 22)
- **Onde:** `F:1218-1230`, `C:81`, `R:46`, `R:64-68`, `EA:318-329`.
- **Efeitos:** (a) durante a espera não há `OnTimer`: o heartbeat para. Num corte com 5 robôs e ordens sem desfecho, a espera passa de 10 s, e um segundo maestro anexado nesse intervalo **toma a trava** (`R:46`). A primeira instância nunca reconfere a trava: duas instâncias mandam ordens. (b) O OCO de outro robô espera na fila. O RE pode ter a S e o A executados na janela, gerando ficha trocada. (c) No Testador a espera é inútil: o histórico é síncrono e só gasta tempo de CPU com 21 releituras por ordem. As S de todos os robôs, que estão no servidor, não são afetadas.
- **Correção:** chamar `Trava_Heartbeat` dentro de `Espera`. Em cada reconciliação, conferir `GlobalVariableGet(trava) == mzToken`; se não for, ALERTA e parar de enviar. Pular o laço quando `Testador()`. A forma definitiva é tirar a espera: enviar, devolver `D_SEM` e deixar `Transito_Resolve` provar.

#### M-4. Feriados da B3 não existem para o maestro
- **Onde:** `Grade.mqh:33-45`, `F:296-300`, `F:516-521`.
- **Cenário:** feriado em dia útil. Com uma ficha da noite, `Mae_Continuo` é verdadeiro a partir das 09:00, e a saída e a S DAY são tentadas a cada 5 s com `MARKET_CLOSED`: ALERTA a cada 5 min o dia inteiro. `Mae_PregaoAnterior` conta o feriado como um dos 10 pregões da janela.
- **Correção:** lista de feriados B3 embutida em `Grade.mqh`, que é a mesma regra de "atualizar = recompilar"; `Mae_DiaUtil` passa a consultá-la.

#### M-5. Modo PROTEGENDO manda mais do que a spec permite, e em conta não-NETTING é perigoso
- **Onde:** `R:183`, `R:291-297`, `EA:327` (`Mae_Reconcilia` roda inteira no passo 10).
- **Cenário:** a spec limita PROTEGENDO a S, cancelamentos e corte. O código roda `Mae_Fase1` completa: correções de trocada e duplicada e zeragens por horário do robô. Se a falha do ambiente for "conta não é NETTING" (EA anexado por engano numa conta hedging com ordens de robô), cada X ou C **abre uma posição nova** em vez de fechar, e cada S também.
- **Correção:** em PROTEGENDO, só S, cancelamentos e saídas de corte; com a falha "conta não é NETTING", nenhuma ordem (só ALERTA).

#### M-6. O botão Desbloquear apaga o trânsito inteiro, inclusive ordens recém-enviadas
- **Onde:** `F:939-942`.
- **Cenário:** o dono aperta o botão por causa de uma zeragem manual enquanto a S do CM está em voo há 1 s. O trânsito some, `Mae_Fase2` vê o CM sem S e manda outra. Ficam duas S (uma é cancelada como excedente) ou uma S nenhuma, se a primeira for recusada depois de o rastro ter sido apagado.
- **Correção:** retirar do trânsito só as ordens com idade ≥ `PRAZO_SEM_DESFECHO` ou listadas como causa do bloqueio.

#### M-7. Ajuste noturno lançado como deals de compra/venda (P14) absorve a ficha da noite e a torna externa
- **Onde:** `F:671-702`.
- **Cenário:** se a corretora registrar o ajuste como fechamento e reabertura (deal de venda e de compra com magic 0), o primeiro reduz a líquida, absorve a ficha do DM e bloqueia; o segundo aumenta a externa. A posição continua aberta, mas agora é "externa": sem S DAY nova na pré-abertura e sem zeragem no primeiro contínuo (cenário d deixa de valer).
- **Correção:** reconhecer o par fecha/reabre do mesmo volume, mesmo instante e preço de ajuste (`DEAL_REASON`) como `AJUSTE`, sem efeito nas fichas; até P14 ser respondida, ALERTA quando houver deal externo fora do contínuo.

#### M-8. Magics continuam como inputs (escolha 14)
- **Onde:** `EA:47`, `EA:62`, `EA:86`, `EA:106`, `EA:130`, `EA:271-278`.
- **Cenário:** o dono troca um magic com o robô posicionado. A ficha e as ordens antigas passam a ter "magic desconhecido nunca tocado": a S antiga nunca é cancelada, a posição vira externa sem zeragem, e o robô novo pode abrir outra entrada.
- **Correção:** magics como constantes (como a spec lista), ou recusar a partida se houver ordem viva ou deal do dia com um magic de robô que não está entre os cinco atuais.

#### M-9. Falha de gravação da memória é silenciosa
- **Onde:** `M:88-94`; o retorno de `Mem_Grava` é ignorado em `F:1156`.
- **Efeito:** a memória fica velha sem ninguém saber. Isso alimenta A-3 (`seq` repetido) e faz a partida restaurar níveis de stop e o trânsito errados.
- **Correção:** falha de `FileOpen`, `FileWriteString` ou `FileMove` vira `Log_Cond` ALERTA, e o envio seguinte (que exige memória gravada antes, 10.1) é barrado enquanto ela não gravar.

#### M-10. Cruzada que não fecha paralisa também a proteção (D1 com a escolha 15)
- **Onde:** `F:998`, `F:2030-2039`.
- **Efeito:** com a cruzada aberta não sai nenhuma ordem: nem S recriada, nem saída de corte. Se isso durar até F (deal que não chega ao histórico, P18), as S DAY vencem e as fichas passam a noite sem stop, mesmo com o EA no ar. É conforme a spec, mas é risco não listado na seção 13. A mensagem do bloqueio aos 60 s diz "não fecha em 10 pregões", o que não é o que aconteceu.
- **Proposta (decisão do dono):** liberar do D1, com a cruzada aberta, a S de ficha cujo lado é inequívoco e a saída de corte; corrigir o texto do bloqueio.

### BAIXA

| # | Onde | Achado | Correção |
|---|---|---|---|
| B-1 | `F:1924-1939` | Na partida antes do contínuo, o A do RE é recriado para a ficha da noite na pré-abertura; 9.3 só permite S fora do contínuo. | Exigir `Mae_Continuo` e `!Mae_Noite(r)` para recriar A. |
| B-2 | `F:1361` | A correção de duplicada (`vol1`) cancela o A antes; o RE fica sem alvo. | Não cancelar o A na correção de volume 1. |
| B-3 | `F:475`, `F:1646-1661`, `F:2002-2011` | O resumo dá ALERTA falso: deals relogados depois de memória perdida, absorções relogadas a cada partida, dois deals no mesmo ms (o segundo nunca é logado). | Marcar `novo` por ticket (lista de tickets logados), não por instante. |
| B-4 | `F:1172`, `F:1294` | `Log_Cond` de `BLOQUEADA` nunca é encerrado; as próximas recusas iguais só aparecem a cada 5 min (a spec pede linha por decisão). | Encerrar a condição quando o envio seguinte do robô passar. |
| B-5 | `F:1804`, `F:1340` | A S recusada ao lado da E nunca é retentada: `RETENTA` = 5 s coincide com "sem S em 5 s → cancela a E", e a fase 1 roda antes da 2 (T04 confirma). | Retentar a S em 1-2 s ou cancelar a E com 10 s. |
| B-6 | `F:223`, `F:1789` | `Mae_AgoraMsc` tem resolução de segundo; a idade de órfã pode sair até 1 s menor. | Usar o `time_msc` do último tick ou `GetTickCount` relativo. |
| B-7 | `F:767`, `F:798` | Vetores fixos de 16: ordens além da 16ª de um robô contam em `nVivas` mas nunca viram órfãs. | Vetores dinâmicos. |
| B-8 | `M:86-88`, `M:104-123` | Checksum calculado sobre o texto Unicode e arquivo gravado em `FILE_ANSI`: qualquer caractere fora do ANSI invalida a memória. | `FILE_UNICODE` ou checksum sobre o texto relido. |
| B-9 | `WinMaestro_Teste.mq5:14` | `CCorretoraReal` (com `OrderSend`) é compilada no `.ex5` de teste, inalcançável. | `#ifndef WINMAESTRO_TESTE` em volta da classe real. |
| B-10 | `F:1043-1060` | `TOO_MANY_REQUESTS` e `LOCKED` ficam como "não sei": robô pausado 30 s sem necessidade. | Incluir na lista de recusa definitiva. |
| B-11 | `C:100` | `PositionSelect` falso com erro 0 é lido como "zerado". | Só `ERR_TRADE_POSITION_NOT_FOUND` vale "zerado". |
| B-12 | módulos × `F:220` | Módulos decidem com `TimeCurrent`, maestro com `TimeTradeServer`; nas fronteiras (corte, última entrada) os dois discordam por segundos. | Aceitável; documentar. No Testador são iguais. |

---

## 2. Cenários (a)–(d) contra o código

| Cenário | Resultado | Ressalvas |
|---|---|---|
| (a) CM e RE comprados, S do RE 14:20, A 15:10, volta 15:30 | **Conforme.** Passo 4: janela fecha com a líquida; RE −1 com `mzPorE` falso → trocada. Passo 7: nada vivo do RE. Passo 8: S do CM conferida; RE trocada no contínuo sem S (`F:1860`) e sem A (`Ficha_Tem` falso). Passo 9: C de compra 1, magic do RE. | Se a correção for recusada ou travar: C-2. O RE importa estado "em posição", que `LimparAlvoOrfao` desfaz no 1º tick. |
| (b) Saída do C1 com `TIMEOUT` sem ticket, 90 s sem internet | **Conforme.** S nunca é cancelada antes do deal (`F:1384-1393`). Sem conexão nada se prova. Na volta, ticket pelo comentário ou `request_id`; se executou, a S vira órfã com OCO imediato; se não chegou, `D_NAO` com leitura confiável e cruzada fechando aos 30 s. | O C1 só manda a saída de novo na próxima vela H1 ou no próximo minuto de break-even (`Win_c1.mqh:493`, `:563`): "pela regra dele" pode significar até 1 h com a S como única proteção. Colisão de comentário: A-3. |
| (c) Dono zera 2 na mão com GB e DM posicionados | **Conforme.** Absorção GB → DM (`F:689-699`); bloqueio uma vez por deal; E de todos canceladas pelo bloqueio; S e A das fichas absorvidas por OCO imediato; botão grava reconhecidos; GB e DM não reentram (`g_decidido`, `g_decidiu`). | A ordem por robô cancela a S antes do A do mesmo robô (a spec pede A, E, S); sem efeito prático. |
| (d) PC desligado desde 17:00 com DM, gap na abertura | **Conforme.** Janela recua um pregão; DM +1 da noite; nível de stop mantido (`guarda`). Antes das 08:55 nada é enviado; na pré-abertura a fase 2 cria a S DAY, ou não cria se o nível foi atravessado; às 09:00 saída a mercado; a S é cancelada depois. Sem `Tick()` do DM. | Em feriado: M-4. "Atravessado" usa bid/ask do leilão (indicativos). Ficha da noite do RE recebe A na pré-abertura: B-1. |

---

## 3. Lógica de sinal contra o WinSeletor

Diferenças linha a linha em todos os módulos, por `diff`. Fora da camada de execução e do corte D2, há **uma** diferença que altera sinal (A-5, RE, causada pela janela de `Tick`, não pelo módulo). O resto:

- **GB:** fim do contínuo pela grade no lugar de `FimContinuoMin`/`RegimeAutomatico`: só alimenta `FlattenSec`, que está desligado por flag. Lógica de sinal idêntica.
- **CM:** `a_favor` da memória no lugar do comentário da posição (sem memória vale `false`, como o original sem comentário); "nunca afrouxa" contra o último stop pedido, equivalente ao `POSITION_SL` do original, que nascia em 0; piso `Ficha_PisoStop` igual ao tick quando `STOPS_LEVEL` = 0.
- **DM:** teto sobre `DM_CAPITAL` (B9) e `VerificarStop` desligado (B8), ambos permitidos. `DistStopDaDecisao` só entra na recuperação sem memória.
- **RE:** entrada e alvo DAY no lugar de GTC (sem efeito: zera às 17:00); S pré-calculada desde a E (permitido). `TesterStop` removido (permitido).
- **C1:** trailing pelo nível pedido no lugar de `POSITION_SL`; idêntico enquanto os `OrderModify` são aceitos.

---

## 4. Equivalência no Testador (seção 12): o que diverge além do permitido

1. **RE, janela do detector** (A-5): diferença de sinal real, provável sempre que o histórico do Testador tiver ticks de leilão.
2. **Primeiro dia do teste:** decisões com momento anterior ao `PRONTO` (que leva ~11 eventos de timer depois do primeiro tick) viram `DECISAO PERDIDA`. Excluir o primeiro dia da comparação ou contar esses trades.
3. **`BLOQUEADA` do D1:** no Testador a leitura é confiável e síncrona, então não deve ocorrer, mas qualquer `ESTADO` no log do Testador é divergência e deve ser contado.
4. **Laço de espera** (M-3): no Testador não acrescenta informação. Se o `Sleep` do Testador avançar o relógio emulado, cada `D_SEM` desloca o tempo; se não avançar, só custa CPU. Pular o laço com `Testador()` elimina a dúvida.
5. **Teste 2 (os cinco juntos):** além da ordem fixa, a autonegociação (`AUTONEG`) e o alvo do RE bloqueado sem nova tentativa (A-6) mudam trades. Listar os `AUTONEG` do log como causa.

O resto (zeragem pelo timer, S viva desde a E, CM às 18:20, teto do DM) está na lista permitida.

---

## 5. Armadilhas do MQL5: o que foi conferido

| Tema | Situação |
|---|---|
| `HistorySelect` intercalado | Correto: `LeHistorico` copia tudo antes; `LeOrdemHist` (que troca a seleção) só é chamado depois da cópia. Nenhum módulo chama `History*`. |
| Seleção global de Position/Order | Correta em `LePendentes` e `RoboEmOutroSimbolo`; nenhum módulo usa `Position*`/`Order*`. |
| `PositionSelect` em netting | Por símbolo; erro de consulta vira "leitura descartada". Ver B-11. |
| `OrderSend` × `OrderSendAsync` | Só `OrderSend` síncrono. |
| `result.deal == 0` | Nunca usado como prova; a prova é o deal no histórico. |
| `Sleep` em `OnTick`/`OnTradeTransaction` | M-3. As S no servidor não são afetadas; o que para é heartbeat, OCO e timer. |
| Overflow, divisão por zero | `Ficha_Aplica` divide por `|b|` só com `b ≠ 0`; `Mae_ValorPonto` devolve 0 com tick zerado. Sem overflow plausível (`long` em ms). |
| Arrays | B-7; o resto com checagem de índice. |
| Arredondamento ao tick | `Mae_NoTick` em todo preço enviado. |
| Volume | Sempre 1 ou `|ficha|` inteiro. |
| `double ==` | Comparações de preço com meio tick; sem `==` em preço no núcleo. |
| Data/fuso | Maestro em `TimeTradeServer`; AVISO de P22 no `PRONTO`. B-12. |
| `FileOpen`/`FileMove`/sandbox | Atômico e dentro de `MQL5/Files`. M-9, B-8. |
| `GlobalVariableSetOnCondition` | Correto, inclusive no reinício pelo mesmo gráfico. A trava nunca é reconferida: M-3. |
| Comentário ≤ 31 | `MAE|CM|E|0042` tem 13 caracteres. |
| `static` em `REASON_PARAMETERS` | Só caches por dia (`CM:663`, `RE:177`), inofensivos. Globais reinicializadas em `OnInit`. |

---

## 6. EA de teste

**Não há caminho para a corretora real.** `WinMaestro_Teste.mq5` só instancia `CCorretoraFalsa` (`:76`); `mzCorr` nunca recebe `CCorretoraReal`; nenhum arquivo além de `Corretora.mqh` chama `OrderSend`. Os módulos de robô não são incluídos. Efeitos fora da memória do processo: arquivos em `MQL5/Files/WinMaestro_unit*` (apaga só essas pastas), `Print`. Nenhuma variável global, nenhum objeto no gráfico (o botão é suprimido porque a falsa responde `Testador()` verdadeiro), nenhum `Alert`.

**Única condição para anexar:** num gráfico **diferente** do que roda o WinMaestro. Um gráfico tem um EA só; anexar o de teste por cima remove o maestro de produção (com a trava liberada e a memória gravada, mas o robô para de gerir).

**Os 28 casos testam o que dizem.** Nenhum passa por construção. O que não cobrem:
- T04 confirma que a S recusada não é retentada antes de a E ser cancelada (B-5): o teste documenta o comportamento, não o que a spec pede.
- T12 simula o reinício só apagando `mzAbsVistas`; não passa por `Mae_Importa` nem pela sequência de partida.
- Nenhum teste roda `Recupera_Passo`, a memória de ponta a ponta (`Mae_Exporta`/`Mae_Importa`), `OnTradeTransaction`, conexão perdida (a falsa responde `Testador()` verdadeiro e pula a regra dos 10 s), lista de pendentes parcial, deal sem magic, `MODIFY` de stop do lado errado (a falsa aceita qualquer preço) ou colisão de comentário.
- Testes que pegariam os achados: C-1 (`TIMEOUT` na E limite seguido de `Dispara` da E), C-2 (duplicada de 3), A-2 (`Roteiro` de cancelamento sem desfecho), A-3 (mesmo comentário em dois dias), A-4 (`LeHistorico` falhando).

---

## 7. As 25 escolhas das notas

| # | Escolha | Avaliação | Alternativa |
|---|---|---|---|
| 1 | Retcodes de recusa definitiva | Segura (o lado errado é só pausa). | B-10. |
| 2 | Papel pela ficha na colocação; ordem não lida = E | **Risco** (M-1). | Ficha indeterminada até a ordem ser lida. |
| 3 | Trocada = ±1 não aberta por E | Segura, se a 2 for corrigida. | — |
| 4 | Absorção cancela só o A das absorvidas | Segura. | — |
| 5 | Janela de ordens da pré-abertura a F | Segura; B-1 a viola. | — |
| 6 | Data sem linha: 09:00 / 08:55 | Segura; feriado é outro problema (M-4). | — |
| 7 | Vencimento só para `WIN`+letra+2 dígitos | Segura. | — |
| 8 | `RETURN` para execução de bolsa | Segura (depende de P15). | — |
| 9 | `VerificarStop` do DM desligado | Segura (evita saída dupla, item 1.23). | — |
| 10 | Fallback DAY do GB só em `RECUSADA` | Segura. | — |
| 11 | RE adota o fill em `EXECUTOU_ANTES` | Segura no caso síncrono; **incompleta** no assíncrono (A-6). | Restaurar o estado no evento. |
| 12 | Stop que aperta contra o último pedido | Segura (equivalente ao avulso). | — |
| 13 | Grava memória também em `PARAMETERS` | Segura. | — |
| 14 | Magics como input | **Risco** (M-8). | Constantes, ou recusa com ordens do magic antigo. |
| 15 | Bloqueio da cruzada aos 60 s | Aceitável; texto errado; ver M-10. | Texto real; liberar S e corte. |
| 16 | Custos como vêm do MT5 | Segura. | — |
| 17 | `OrderModify` fora do trânsito | Segura. | — |
| 18 | OCO imediato para irmã anterior ao deal | Segura. | — |
| 19 | Trocada sem S no contínuo | **Risco crítico** (C-2). | S de emergência quando a correção não sai ou trava. |
| 20 | Momento de decisão por módulo | Segura. | — |
| 21 | Módulos leem mercado direto | Segura para o dinheiro; diverge da letra da seção 1 e impede testar os módulos com a falsa. | — |
| 22 | Espera bloqueante de 5 s | **Risco** (M-3). | Heartbeat na espera, reconferir trava, sem laço no Testador; ideal: assíncrono. |
| 23 | PROTEGENDO por líquida ou ordem de robô | Decisão segura; o modo em si manda mais que o permitido (M-5). | — |
| 24 | Memória no Testador sem heartbeat | Segura. | — |
| 25 | Duplicada > 2: 1 contrato por 10 min | **Risco crítico** (C-2): trava na hora e deixa contratos sem stop. | Corrigir `|f| − 1` de uma vez. |

---

## 8. Resposta

**Contagem:** CRÍTICA 2 · ALTA 6 · MÉDIA 10 · BAIXA 12.

**As 5 mais graves:**
1. C-1: entrada limite com E ou S sem desfecho deixa a ficha cheia sem stop, porque o trânsito barra a S (mandar a S antes da E).
2. C-2: ficha trocada no contínuo nunca ganha S, e duplicada de 3 trava após a 1ª correção com contrato nu.
3. A-1: se o deal de pendente vier sem magic (P2), o fill vira externo e a S é cancelada como órfã: posição sem stop e sem zeragem.
4. A-4: falha de leitura do histórico mantém o estado "confiável" com fichas velhas, e o D1 deixa sair saída que inverte a conta.
5. A-2: cancelamento de E que não confirma nunca é retentado, e DM/RE esquecem a E, que enche horas depois (no RE, sem alvo).

**Veredito:** pronto para o **teste de equivalência no Testador** (lá nenhum dos achados põe dinheiro em risco, e ele vai medir A-5); **não pronto para demo** enquanto C-1, C-2, A-1 (ou a resposta de P2), A-2, A-3 e A-4 estiverem abertos, porque os testes de falha 3, 5, 11 e 14 da seção 12 exercitam exatamente esses caminhos.

**EA de teste:** pode ser anexado com segurança, desde que num gráfico diferente do que roda o WinMaestro; não tem caminho para a corretora real.
