# WinMaestro: revisão adversarial 1 da especificação 0.1

Escopo: `WinMaestro_ESPECIFICACAO.md` (0.1), conferida contra `WinMaestro_inventario_modulos.md`, o código de partida (`WinSeletor.mq5`, `WinSeletor/*.mqh`) e `LICOES_DE_PRODUCAO.md`, usado como checklist. Cada lacuna traz severidade, a seção da especificação onde ela está, um cenário concreto de falha e o texto que deveria entrar na especificação.

Severidades: **CRÍTICA** = pode perder dinheiro ou deixar posição sem stop. **ALTA** = muda o resultado, pode travar o robô ou esconder um estado perigoso. **MÉDIA** = problema de robustez ou de auditoria. **BAIXA** = detalhe.

Notação: "item X.Y" aponta para `LICOES_DE_PRODUCAO.md`, e "P8-n" para a pergunta n da Parte 8 desse arquivo.

---

## Resumo

| Severidade | Quantidade |
|---|---|
| CRÍTICA | 11 |
| ALTA | 11 |
| MÉDIA | 8 |
| BAIXA | 5 |
| **Total** | **35** |

A especificação acerta a arquitetura: fichas derivadas dos deals por magic, a corretora como verdade, cada ficha fechada pelo próprio volume e não pela posição líquida, persistência explícita e a remoção dos três bloqueios. Os furos que podem custar dinheiro estão todos no mesmo lugar: **o que acontece ENTRE o envio e a confirmação, e o que acontece com as ordens vivas quando alguém de fora (o dono, a mesa da corretora, um segundo EA) mexe na posição líquida**. Esses dois cenários já custaram dinheiro neste projeto (Parte 0, itens 1.23, 1.24 e 1.25).

---

## Lacunas CRÍTICAS

### C1. Não existe estado "ordem em trânsito": DONE sem deal leva a reenvio, e o reenvio inverte a posição
- **Onde:** 3.1 (`Ficha_Fecha`, `Ficha_EntraMercado`), 5, 6, 8.
- **Cenário:** às 12:00 o CM decide sair e `Ficha_Fecha` manda venda a mercado. O `OrderSend` volta `TRADE_RETCODE_DONE` com `deal=0` e `price=0`, o que já aconteceu nesta corretora (item 1.24). O deal ainda não chegou ao histórico e a ficha, recalculada dos deals, continua +1. No tick seguinte o `Tick()` do CM vê `Ficha_Tem(CM)` verdadeiro e manda **outra** venda. As duas executam e a ficha fica −1: um contrato nu do lado contrário. A reconciliação de 8.1 manda então uma correção a mercado. Se essa correção também voltar sem deal, o ciclo se repete. O mesmo mecanismo vale para a entrada (estado ABRINDO), para a criação do stop (8.2 vê "posicionado sem stop" enquanto o stop recém-enviado ainda não aparece em `OrdersTotal` e cria um segundo stop; dois stops depois executam juntos e invertem) e para a correção.
- **Correção (texto):** "Toda ordem enviada pelo maestro entra num **registro de ordens em trânsito** (robô, papel, volume assinado, ticket da ordem, hora de envio) **antes** do `OrderSend`. A ficha **efetiva** de um robô é `ficha pelos deals + volume em trânsito do robô`. Enquanto um robô tiver ordem em trânsito do mesmo papel, o maestro **não envia outra ordem desse papel** para esse robô, seja saída, entrada, stop, alvo ou correção. Uma ordem sai do trânsito só quando o histórico confirma o desfecho: deal(s) com `DEAL_ORDER` = ticket, ou a ordem no histórico com `ORDER_STATE_CANCELED/REJECTED/EXPIRED`. Resposta `DONE/PLACED` sem deal é **'não sei'**, nunca 'não executou' (itens 1.6, 1.24). A consulta ao histórico tem prazo: repete por até N s (input, padrão 5 s). Esgotado o prazo, a ordem continua 'em trânsito desconhecida', o robô fica bloqueado para novas ordens e o log registra ALERTA. Nada é reenviado por inferência."

### C2. "Cancelamento confirmado" não está definido; o retcode do cancelamento não confirma nada
- **Onde:** 5.3, 14.5, A.3 (reserva do DM).
- **Cenário:** o DM vê o último negócio cruzar `g_stopNivel` e cancela a reserva, que é um SELL_STOP no **mesmo nível**. O `OrderDelete` volta DONE e o EA envia a venda a mercado. Só que a reserva já tinha disparado no servidor: em ordem de bolsa o cancelamento é assíncrono (estado `ORDER_STATE_REQUEST_CANCEL`) e o desfecho pode ser FILLED. As duas vendas executam e a ficha fica −1. A especificação só cobre o caso em que o cancelamento **falha** porque a ordem executou. O caso pior é o cancelamento **aceito** que perde a corrida. O mesmo acontece em 14.5, "stop atravessado → sai a mercado": se o `OrderModify` do stop é recusado, o stop **antigo** continua vivo, e a especificação não manda cancelá-lo antes da saída (item 1.23).
- **Correção (texto):** "Cancelamento confirmado = a ordem aparece no **histórico** com `ORDER_STATE_CANCELED` (ou `EXPIRED`). O retcode do `OrderDelete` não basta. Antes de qualquer saída a mercado, o maestro cancela stop e alvo do robô e espera essa confirmação no histórico (prazo de C1). Se o histórico mostrar FILLED/PARTIAL, a saída não é enviada. Se o prazo esgotar sem desfecho, a saída também não é enviada: o robô fica em 'saída pendente de confirmação' e a reconciliação decide. Vale para toda saída a mercado, inclusive 'stop atravessado' (14.5), zeragem, rede de segurança de 12 e correção de 8.1."
- **Correção complementar (DM, ver também A11):** um caminho só de fechamento por posição (item 1.23). Se a reserva fica no **mesmo nível** do stop do EA, ela é o stop de fato, e o stop do EA só cria a corrida. Opções: (a) o stop do DM passa a ser só a ordem stop pendente; (b) o stop do EA fica e a reserva vai para K ticks além (input), disparando só se o EA não agiu. A especificação tem de escolher uma e justificar o efeito sobre a equivalência.

### C3. Intervenção externa na posição líquida (dono, mesa da corretora, stop-out, zeragem compulsória) deixa fichas fantasmas, e os stops e alvos vivos viram entradas nuas
- **Onde:** 4.4, 8.3, 14.6.
- **Cenário 1 (já aconteceu neste projeto, itens 1.25 e Parte 0):** GB e RE estão comprados, líquida +2. O dono vê algo estranho e zera **na mão** (magic 0). Pela regra 4.4 o deal é "externo": as fichas continuam +1 e +1, externa −2, Σ confere, e "o maestro não mexe". Ficam vivos o SELL_STOP do GB, o SELL_STOP e o SELL_LIMIT (alvo) do RE. Quando o preço tocar qualquer um deles, a ordem **abre** um vendido sem stop. Pior: a regra de saída do RE (zeragem 17:00) manda vender 1 a mercado, o que abre outro vendido. O resultado é exposição crescente exatamente depois de o dono ter zerado.
- **Cenário 2:** a Rico faz **zeragem compulsória** de day trade num horário próprio (a verificar: muitas corretoras zeram minicontratos antes do fim do pregão e cobram taxa). Os deals dela não têm magic de robô e o resultado é o cenário 1, todo dia em que algum robô estiver posicionado nesse horário. O mesmo vale para stop-out por margem (`DEAL_REASON_SO`).
- **Cenário 3:** 14.6 manda o maestro **remover** SL/TP que encontrar na posição. Mas o que encerrou o incidente de 2026-08-28 foi justamente "um stop anexado à mão". O maestro apagaria a proteção de emergência do dono.
- **Correção (texto):** "Deal de símbolo com magic fora do conjunto do maestro, ou com `DEAL_REASON` em {`CLIENT`, `MOBILE`, `WEB`, `SO`} sem magic de robô, que **reduz** |líquida| é **intervenção externa redutora**. Ação imediata: (1) bloqueio de entradas (8.5); (2) cancelar **todas** as ordens pendentes dos magics dos robôs cujo lado é o da redução, ou seja, stops, alvos e entradas que, executados agora, aumentariam a exposição; (3) absorver a redução nas fichas, na ordem fixa de 4.5 ou proporcionalmente (o dono decide), e registrar cada ficha absorvida como 'fechada por intervenção externa' com o preço do deal externo; (4) ALERTA com notificação push. Deal externo que **aumenta** |líquida| é só registrado (8.3 como está). SL/TP encontrado na posição líquida **não é removido**: o maestro entra em bloqueio, loga ALERTA e espera o dono. Proteção posta pelo dono nunca é apagada pelo robô." Acrescentar à seção 14: "A Rico faz zeragem compulsória de day trade? A que horas, com qual `DEAL_REASON`/magic, e ela cancela as ordens pendentes da conta?"

### C4. A janela sem stop entre o fill e a criação do stop é uma regressão em relação ao EA avulso, e a especificação não a declara
- **Onde:** Princípio 4, 4.3, 6, 7 (`OnDeinit` "não cancela nada"), A.4 (o RE deixa de cancelar a entrada no Deinit).
- **Fato:** hoje GB (`BuyLimit` com SL anexado, inventário 1.2) e C1 (`Buy` com SL) têm stop **atômico** com a entrada (item 1.2: "a proteção sai junto com a ordem, atomicamente, ou não é proteção"). No maestro, o stop só nasce depois que o EA recebe o deal. O Princípio 4 ("todo robô posicionado tem o stop dele na corretora") é **falso** durante essa janela, e a janela não tem limite enquanto o EA estiver fora.
- **Cenário:** o CM deixa uma BUY_LIMIT DAY viva por até 5 velas H2 (10 h), o RE por até 150 min, o GB das 09:05 às 09:35 e o DM por 15 min. A internet cai às 10:40 (o EA continua rodando, mas sem conexão, então o caso não é só "MT5 fechado") ou o PC trava (sem `OnDeinit`). As limites vivas enchem e as posições ficam **sem stop** até o EA voltar. Pior caso com os 4 robôs de entrada limite: 4 contratos nus no mesmo lado. Um dia de WIN de 2.000 pontos contra custa 4 × R$400 = **R$1.600**, mais o CM, que nem stop tem (B.1).
- **Correção (texto):** (a) declarar no Princípio 4: "Exceção conhecida: entre o preenchimento de uma entrada e o registro do stop dela, e enquanto o EA estiver fora do ar ou desconectado, a ficha recém-aberta não tem stop no servidor. A MT5 não tem OCO/OTO para ordens independentes em conta netting." (b) Stop do C1 (entrada a mercado): o stop é enviado **na mesma chamada** que recebe o resultado do `OrderSend` com deal, sem esperar `OnTradeTransaction`. (c) `OnDeinit` com `reason` ≠ `REASON_PARAMETERS`/`REASON_CHARTCHANGE`/`REASON_TEMPLATE` (remoção, fechamento do terminal, troca de conta, recompilação, gráfico fechado) **cancela todas as entradas pendentes** (papel E) e loga. (d) Entradas limite com validade `ORDER_TIME_SPECIFIED` curta, sempre que a regra do robô permitir: menos tempo viva sem vigia. (e) Documentar em 13 o pior caso numérico (contratos × pior movimento do dia) e levar ao dono como decisão do Apêndice B: "aceitar a janela, ou cancelar entradas com o EA desconectado por mais de X s (só funciona com o EA vivo)".

### C5. Sem OCO no servidor: alvo ou stop órfão que enche com o EA fora vira posição nova e nua
- **Onde:** 5.1–5.2, 4.1.
- **Cenário:** o RE está comprado com SELL_STOP (stop) e SELL_LIMIT (alvo). O EA cai às 14:00. Às 14:20 o stop executa e a ficha vai a 0, mas o alvo continua vivo (DAY). Às 15:10 o preço sobe até o alvo, a SELL_LIMIT enche e **abre um vendido sem stop**. A regra 5.2 só corrige "depois" e só com o EA vivo. Se o EA só volta às 17:30, o vendido ficou 2 h nu. É exatamente o item 1.24 (regra 2) e a P8-70.
- **Correção (texto):** "Com o EA fora do ar, toda ficha que tem stop e alvo vivos está exposta à execução dupla. Isso é limitação estrutural da MT5 em netting e entra no cálculo de pior caso de C4." Acrescentar à recuperação (10.5.B): "cancela as ordens irmãs **antes** de qualquer outra ação, e se a ficha ficou com sinal trocado aplica 8.1 já no passo 9." Avaliar com o dono: robô sem alvo obrigatório (GB padrão) não tem esse risco; para o RE, alvo e stop vivos sem EA é decisão consciente.

### C6. Nenhuma proteção contra duas instâncias: dois gráficos, WinSeletor ainda carregado, EAs avulsos com os mesmos magics, VPS mais PC local
- **Onde:** 1 (magics "os originais"), 4.4, 9, 10.1.
- **Cenário:** o dono carrega o maestro em dois gráficos de WINV26, ou migra para a VPS da MetaQuotes e esquece o terminal local ligado, ou deixa um `WinCincoMedias.ex5` avulso rodando noutro gráfico (os magics são os mesmos, 80080501). Cada instância vê os deals do CM como dela, e as duas mandam stop, alvo, saída e correção. Pela 4.4 os deals de um EA avulso com o magic do CM entram na ficha do CM e **não** aparecem como externos. O item 2.4 mostra que isso já aconteceu neste projeto (6 supervisores para 3 slots).
- **Correção (texto):** "Exclusividade: (1) no `OnInit`, o maestro tenta tomar a trava `GlobalVariableSetOnCondition("WinMaestro.lock.<conta>.<símbolo>", <chart_id>, 0)` (operação atômica do terminal). Se outra instância tem a trava com heartbeat de menos de 10 s, recusa iniciar com Alert. Além disso, um arquivo de trava em `FILE_COMMON` fica aberto sem `FILE_SHARE_WRITE` pela vida do EA (verificar na demo se um segundo `FileOpen` falha). (2) Toda ordem e deal com magic de robô cujo comentário de origem **não** comece por `MAE|` é sinal de outra instância ou de um EA avulso: BLOQUEIO total de entradas e ALERTA. (3) O comentário leva 2 caracteres de identificação da instância (`MAE|<inst>|<robo>|<papel>|<seq>`), para distinguir duas instâncias do próprio maestro, inclusive em terminais diferentes. (4) O LEIA-ME manda **remover** os EAs avulsos e o WinSeletor dos gráficos, além de tirá-los da pasta."

### C7. A regra de autonegociação bloqueia SAÍDAS e não cobre stops disparados no servidor
- **Onde:** 14.2.
- **Cenário 1:** o CM, vendido e **sem stop** (regra do robô), precisa sair (compra a mercado). O RE tem uma SELL_LIMIT de entrada viva. Pela regra "compra ≥ venda própria viva", a saída do CM é **bloqueada** e "reavaliada no tick seguinte". Enquanto a limite do RE viver (até 150 min), o CM não sai. É o item 1.22: "cota barra ABRIR, nunca barra SAIR".
- **Cenário 2:** o stop do GB (SELL_STOP 100) dispara no servidor e vira venda a mercado, que agride a melhor oferta de compra. Se a melhor compra for a BUY_LIMIT de entrada do DM em 100, há autonegociação. A regra pré-envio não vê isso, porque stop não fica no livro. Se a corretora ou a B3 tiver prevenção de autonegociação que **cancela a agressora**, o stop do GB é cancelado em silêncio e o GB fica sem stop no pior momento.
- **Correção (texto):** "Saídas, stops, zeragens e correções **nunca** são bloqueados pela regra de autonegociação. Quando uma saída a mercado de um robô puder cruzar com uma limite própria do lado oposto, o maestro **cancela primeiro a limite do outro robô** (confirmação como em C2), envia a saída e depois deixa o outro robô rearmar (log `AUTONEG cancelou entrada de X para saída de Y`). O efeito na equivalência (perda de fila) vai para o relatório de 15.1. Cancelamento ou recusa de uma ordem de papel S ou A detectada em `OnTradeTransaction` ou na reconciliação é **evento crítico**: se a ficha está posicionada, recria o stop na hora, e se o preço já passou do nível, sai seguindo C2." Pergunta nova à Rico: "existe Self-Trade Prevention para a conta? Qual lado é cancelado (agressor, passivo, ambos)? Vale para ordem stop disparada? Como chega na MT5 (retcode, `ORDER_STATE`, comentário)?"

### C8. Em netting, o stop de um robô pode ser ordem de ABERTURA para a conta, e a corretora pode recusá-lo por margem
- **Onde:** 4.3, 13 (a regra de margem cobre só a entrada).
- **Cenário:** o CM está comprado 1 e o RE e o DM vendidos 1 cada, líquida −1. O stop do CM (SELL_STOP) dispara e leva a líquida a −2. Para o risco da corretora isso é **aumento** de exposição: precisa de margem e, com margem esgotada, é recusado com o texto "para abrir novas posições" (item 1.1, Parte 0). O mesmo vale para `Ficha_Fecha` do CM a mercado. A especificação diz que "entrada que reduz a líquida não exige margem nova", mas a recíproca, **saída que aumenta a líquida exige margem**, não aparece em lugar nenhum. Se a Rico bloqueia margem para ordem pendente na **colocação**, até registrar o stop pode falhar.
- **Correção (texto):** "Pior caso de margem: o portão de entrada de 13 calcula a margem para a líquida **no pior estado alcançável depois desta ordem**, ou seja, todas as entradas pendentes e todos os stops e alvos vivos executando no sentido que mais aumenta |líquida|, e não só o volume da ordem atual. Capital mínimo da **conta** = margem × (contratos no pior caso) × folga (item 3.3: 'o portão tem de impedir o último passo que ainda cabia'), declarado nesta seção com número. Recusa por margem de uma ordem de papel S, X ou C é ALERTA imediato com notificação push." Perguntas à Rico: "ordem pendente bloqueia margem na colocação? Stop que dispara e aumenta a líquida passa por checagem de margem? Qual é a margem de day trade do WIN e o `OrderCalcMargin` a devolve, ou devolve a margem cheia da B3?"

### C9. Stops DAY com ficha que atravessa a noite deixam a posição sem stop durante a noite e na abertura; a reconstrução por "deals do dia" nem enxerga essa ficha
- **Onde:** 3 ("Σ dos deals do dia"), 4.1 (stop validade DAY), 10.2/10.4/10.6, 12.
- **Cenário:** o EA cai às 17:40 (PC desligado) com o CM e o DM posicionados. Nada zera, e às 18:30 as ordens stop **DAY expiram**. As posições passam a noite e o leilão de abertura **sem stop nenhum**. Na volta, às 09:10, a reconstrução usa "deals do dia" (`HistorySelect` do início do pregão): os deals de abertura são de ontem, então as fichas reconstruídas dão 0. A líquida +2 vira "**exposição externa**" pela 4.4, e a regra 8.3 manda **não mexer**. O passo 10.6 ("ficha aberta com deal de outro dia") **nunca dispara**, porque a ficha de ontem não é reconstruída. A especificação se contradiz aqui.
- **Correção (texto):** "Reconstrução: o histórico é lido desde o **último instante em que a líquida do símbolo foi zero** (andar para trás dia a dia até `Σ deals assinados de todos os magics desde T` = líquida real), com no mínimo o pregão de hoje e no máximo 10 pregões. Só entram deals `DEAL_TYPE_BUY/SELL` do símbolo. `BALANCE`, `CORRECTION`, `CHARGE`, ajustes e variação de margem (`DEAL_REASON_VMARGIN`) ficam fora do volume e são logados. Ficha com deal de abertura anterior ao pregão de hoje = **ficha de pregão anterior** (10.6)." Sobre a validade do stop, decisão do dono no Apêndice B: (a) **GTC** ou `SPECIFIED` até o fim do pregão seguinte para os stops (a posição esquecida fica protegida, mas um stop órfão de ficha já zerada sobrevive à noite e pode abrir posição no dia seguinte, o que exige o passo 8 da recuperação antes de qualquer outra coisa); ou (b) DAY, aceitando posição nua durante a noite quando o EA falha no fim do dia. A especificação tem de dizer qual escolheu e por quê.

### C10. Divergência transitória dispara correção a mercado e dobra a posição
- **Onde:** 8.1, 8 (passo 3 a cada tick), 10.2 ("histórico de deals carregado").
- **Cenário:** a MT5 atualiza a lista de posições e o histórico de deals por caminhos separados, e a ordem dos eventos em `OnTradeTransaction` não é garantida. Num tick, `PositionSelect` já mostra a líquida nova e o `HistorySelect` ainda não traz o deal: "posição real ≠ Σ fichas" e, conforme o caso, ficha fora de {0, ±Lote}. A 8.1 manda a correção a mercado **na hora**. Depois de uma reconexão, o histórico do terminal chega aos poucos e por alguns segundos as fichas "zeram". A correção é exatamente o "fechar às cegas uma exposição cuja origem ninguém entendeu" que o item 1.7 proíbe, e em netting ela inverte (item 1.4).
- **Correção (texto):** "Uma divergência só é **confirmada** se persistir por ≥ 3 s **e** em ≥ 3 leituras independentes (`HistorySelect` refeito) **e** se não houver ordem em trânsito (C1) que a explique em quantidade. Lado divergente nunca é explicado por trânsito (item 1.25, regra 2). Antes de confirmar: verificação cruzada `Σ deals de todos os magics desde o último zero = líquida real`. Se ela falha, o problema é histórico incompleto, não ficha errada: **espera, não corrige**. Correção automática só para a causa conhecida, ficha com sinal trocado por execução dupla identificada pelos deals de S e A do mesmo robô. Qualquer outra divergência bloqueia e alerta, sem enviar ordem. No máximo uma correção por ficha a cada 10 min; uma segunda exige o dono (item 1.13, escalar)." Para 10.2: "histórico carregado" = a verificação cruzada acima fecha. Não existe flag da API para isso.

### C11. Stop disparado durante leilão, túnel ou banda é recusado, ou o stop-limit não enche, e o robô fica sem stop sem detecção
- **Onde:** 4.3 (fallback stop-limit), 14.4 (só trata ordem a mercado **enviada pelo EA**).
- **Cenário:** queda forte, a B3 abre leilão por variação e o SELL_STOP do GB dispara. A ordem a mercado gerada é recusada pela bolsa em leilão, ou pelo túnel de rejeição (a verificar). Ou, no fallback stop-limit, o limite N ticks abaixo é atravessado num gap e a ordem limite fica parada **acima** do mercado sem encher. Em todos os casos a ficha continua posicionada e a ordem S some ou deixa de proteger. A especificação não prevê detectar "stop disparou e não executou".
- **Correção (texto):** "Estado 'stop disparado sem execução': ordem S que sai do livro de pendentes sem deal correspondente (rejeitada ou cancelada pela corretora) **ou** stop-limit ativado cujo limite já foi atravessado pelo último negócio há mais de X s. Ação: ALERTA e saída por ordem limitada **agressiva** (preço = último ∓ K ticks, dentro da banda), reenviada a cada Y s fora de leilão. Durante leilão (fase lida pela grade da B3 na data, ou detectada pela recusa), a ordem fica como limite no preço de proteção para participar do leilão, se a B3 aceitar. Nunca em laço: no máximo M tentativas por minuto, com escalada." Pergunta à Rico (amplia a 14.1): "o SELL_STOP do WIN fica no servidor MT5 da Rico ou é enviado à B3 como stop nativo? Dispara pelo último negócio? Ao disparar vira ordem a mercado, limitada com proteção, ou stop-limit? O que acontece se disparar em leilão de abertura, leilão por variação ou call de fechamento?"

---

## Lacunas ALTAS

### A1. O relógio dos cortes é `TimeCurrent()`, que congela sem ticks; e "fim do pregão" precisa ser o fim do contínuo da data, não a sessão do símbolo
- **Onde:** 7 (`OnTimer`), 12, A.1–A.5.
- **Fato:** todos os módulos usam `TimeCurrent()` (CM L715–722, DM L473, GB L345, RE L1018, C1 L584–591), que é a hora do **último tick recebido** e não anda sem cotação. A rede de segurança em `OnTimer` herdaria isso. O item 2.8 (regra 5) exige piso por relógio de parede, e a P8-110 pergunta exatamente isso. Além disso, "fim do pregão − 3 min (lido da sessão do símbolo)" pode cair dentro do call de fechamento (18:25–18:30, item 5.35) se `SymbolInfoSessionTrade` devolver a sessão com o leilão incluído. Em dias de pregão até 17:55 (horário de verão nos EUA), cortes fixos como GB 18:20 e C1 17:50 ficam depois do fim, ou colados nele.
- **Correção (texto):** "Todo corte de horário do maestro (rede de segurança, zeragem de pregão anterior, horário perdido, cancelamento das pendentes de fim de dia) usa `TimeTradeServer()` e roda em `OnTimer`, mesmo sem tick. O fim de referência é o **fim do pregão contínuo da data** (grade oficial da B3 vigente naquele dia, em tabela no código ou em CSV), e não a sessão da MT5. Rede de segurança = fim do contínuo − 3 min. Log `RELOGIO` quando `TimeCurrent()` e `TimeTradeServer()` divergirem por mais de 60 s durante o pregão (feed parado, item 5.17)." E conferir cada zeragem dos robôs contra o dia de 17:55.

### A2. `DEAL_ENTRY` e `DEAL_PROFIT` pertencem à posição LÍQUIDA, não à ficha; o resultado por robô (e o saldo virtual do DM) sai errado se vier deles
- **Onde:** 3 (`preco_medio` = "deals de abertura", `resultado_realizado_dia`), 13 (saldo virtual), 11.4.
- **Cenário:** o GB está comprado 1 e o RE vende 1 (abertura da ficha do RE). O deal do RE sai `DEAL_ENTRY_OUT` (fecha a líquida) e carrega o `DEAL_PROFIT` do GB. Se a ficha usar `DEAL_ENTRY_IN` para "abertura" e `DEAL_PROFIT` para resultado, o preço médio do RE fica vazio e o lucro do GB vai para o RE. Na inversão (`DEAL_ENTRY_INOUT`) o volume do deal é o total. O saldo virtual do DM (teto de 10% do stop) passa a ser calculado sobre lucro de outro robô, e o **tamanho do stop real** muda.
- **Correção (texto):** "A ficha é calculada só por volume assinado e preço de cada deal do magic do robô, ignorando `DEAL_ENTRY` e `DEAL_PROFIT`. Abertura da ficha = deals que afastam a ficha de zero; resultado = Σ (preço de saída − preço médio) × volume × valor do ponto lido do símbolo (`SYMBOL_TRADE_TICK_VALUE`/`TICK_SIZE`, nunca digitado; item 6.55) − custos do deal (`DEAL_COMMISSION`, `DEAL_FEE`). `DEAL_PROFIT` só entra como conferência do total da conta no resumo do dia."

### A3. Identificar o papel pelo comentário não foi verificado; o ticket pode mudar no `OrderModify`; falta o invariante "no máximo uma ordem S por robô"
- **Onde:** 4.2, 3 (`ticket_*`), 8.2/8.4.
- **Cenário:** corretoras de bolsa às vezes trocam ou truncam `ORDER_COMMENT`. Se a Rico fizer isso, a recuperação não sabe qual ordem é stop, alvo ou entrada, e a 8.4 cancela tudo como órfão (inclusive os stops) ou não reconhece nada. Se o `OrderModify` de um stop gerar ordem nova na bolsa com ticket novo, o `ticket_stop` da memória fica velho, a 8.2 conclui "posicionado sem stop" e cria um **segundo** stop. Os dois executam juntos e a posição inverte.
- **Correção (texto):** "Papel identificado por (magic, tipo, lado relativo à ficha): ordem stop do lado oposto = S, limite do lado oposto = A, limite do mesmo lado com ficha zero = E. O comentário é conferência, não fonte. Invariantes verificados a cada ciclo, por robô: Σ volume das S ≤ |ficha| e do lado oposto; Σ volume das A ≤ |ficha|; nenhuma S/A com ficha zero; nenhuma E com ficha ≠ 0 (robôs não piramidam). Excesso = cancela o excedente e loga ALERTA. Tickets na memória são só pista." Perguntas para a demo: "o comentário sobrevive na ordem e no deal? O `OrderModify` de ordem pendente mantém o ticket?"

### A4. O bloqueio por divergência não cancela entradas já pendentes
- **Onde:** 8.5.
- **Cenário:** existe uma divergência (externa mudando, correção recusada) e a 8.5 bloqueia "entrada nova". A BUY_LIMIT do CM, colocada antes, continua viva e enche durante o bloqueio. A exposição cresce exatamente quando o estado está indefinido (item 1.9: "o freio tem de enxergar a ordem parada").
- **Correção (texto):** "Entrar em bloqueio cancela as entradas pendentes (papel E) de todos os robôs, com log. Ao sair do bloqueio, cada robô rearma pela regra dele se ainda estiver na janela."

### A5. O estado restaurado no caso "A. Confere" está velho se o EA ficou fora; contadores de barras e decisões com preço defasado
- **Onde:** 10.5.A, A.2, A.4, A.1.
- **Cenário:** o RE persiste `g_barras_esperando` e `g_barras_posicao`. Com o EA fora por 2 h, essas contagens não andaram. Na volta, o TTL da entrada fica 8 velas maior que o testado e o alvo que se aproxima volta 8 passos atrasado. O CM persiste `g_ultima_barra`: as velas H2 que fecharam com o EA fora (onde as saídas por sinal acontecem) não são processadas, só a última. O GB volta às 09:20, dentro da janela, e envia a limite com o preço da decisão das 09:05: uma limite já negociável vira taker (item 4.17).
- **Correção (texto):** "Persistir **instantes**, nunca contagens: hora da vela do fill e hora do envio. Contagens são recalculadas das barras na volta. Recuperação com lacuna (heartbeat da memória mais velho que 1 vela do robô): cada robô **reprocessa as velas fechadas desde o heartbeat**, na ordem, sem enviar ordem nas velas passadas, e aplica na vela atual a ação que resultar (por exemplo, a saída por sinal que deveria ter acontecido vira saída agora, logada como 'atrasada'). Decisão de entrada cuja janela já foi parcialmente perdida é refeita com o preço atual **só** se a regra do robô aceitar. Senão o dia fica em branco para o robô, com log `DECISAO PERDIDA` (item 2.1: decisão não se restaura; fato sim; janela se repõe por replay, item 2.6)."

### A6. O `OnInit` não pode esperar conexão; o modo "só protegendo" depende do timer; variáveis globais no reinício por input
- **Onde:** 7 ("Só então `EventSetTimer(1)`"), 10.2 ("fica em espera com log a cada 30 s"), 10 (falha: "fica só protegendo").
- **Fato:** esperar dentro do `OnInit` trava a thread do EA, segura `OnTradeTransaction` e `OnTimer`, e impede justamente o "protegendo". O texto diz para ligar o timer só depois da recuperação, mas a espera e a proteção precisam dele. A verificar: em `REASON_PARAMETERS` e `REASON_CHARTCHANGE` o EA pode não ser descarregado, e variáveis globais podem manter o valor (cache de último ticket, flags de trânsito).
- **Correção (texto):** "`OnInit` só configura, liga `EventSetTimer(1)` e devolve `INIT_SUCCEEDED`. A recuperação é uma máquina de estados (`AGUARDA_CONEXAO → LE_MEMORIA → RECONSTROI → COMPARA → … → PRONTO`) avançada em `OnTimer` e `OnTick`. Enquanto não chega a PRONTO, o `Tick()` dos robôs não roda. Os modos `PROTEGENDO` (stops e reconciliação, sem entrada) e `PRONTO` são explícitos. `OnInit` reinicializa **explicitamente** toda variável global do maestro e chama `Reseta()` de cada módulo."

### A7. Portão de margem baseado na margem livre da Rico, que o projeto já sabe que não é confiável; capital mínimo da conta não especificado
- **Onde:** 13.
- **Fato:** o item 1.19 registra que `margin_free`/`equity`/`balance` da Rico na MT5 já travaram um pregão inteiro com número errado (−R$3,60 com R$30 em caixa). A especificação usa "margem livre" como gatilho de recusa. O item 3.3 pede o contrário (margem livre como verdade agregada). Há conflito entre os dois itens, e a especificação não escolhe nem explica.
- **Correção (texto):** "Gatilho de recusa = `ACCOUNT_MARGIN` (margem comprometida, que não passa pelo saldo) + `OrderCalcMargin` da ordem, comparado a um **capital declarado** em input (`CapitalConta`). `ACCOUNT_MARGIN_FREE` é logado como diagnóstico e só gera ALERTA se discordar do cálculo em mais de X%. Capital mínimo da conta para os 5 robôs: [número], derivado do pior caso de C4/C8." E conferir na demo se o `OrderCalcMargin` do WIN devolve a margem de day trade da Rico.

### A8. Equivalência com o testado: o critério "lista idêntica" sem tolerância, dados de tick e mudanças silenciosas de execução
- **Onde:** 15.1, A (preenchimento único `RETURN`), 4.3.
- **Pontos:** (1) no Testador, stop pendente e SL de posição podem disparar por campos diferentes, e o cache de ticks pode vir **sem o último negócio** (item 5.33: 235 de 357 ordens sem `last`, compras com stop no mesmo segundo e vendas sem stop nunca disparado; P8-129/132). (2) O DM tem a reserva só fora do Testador (inventário 3.2, L437). Se o maestro colocar a reserva também no Testador, no mesmo nível, ela executa antes do stop do EA e muda o preço de saída. (3) O C1 entra a mercado com o preenchimento padrão do CTrade. Trocar para `ORDER_FILLING_RETURN` em ordem a mercado pode ser recusado ou se comportar diferente (conferir `SYMBOL_FILLING_MODE`). (4) "Diferença aceitável só onde o stop virou ordem pendente" não tem número.
- **Correção (texto):** "Antes de cada teste de equivalência: conferir que o cache de ticks do Testador tem `last` em ≥ 99% dos ticks do período (EA `AuditoriaTicks`) e tamanho igual ao do terminal. Critério: mesmas entradas (hora e lado) em 100%; preço de saída por stop até 1 tick; resultado total até 2% ou R$X; e toda diferença listada trade a trade com causa. Relatório com contagem de ordens recusadas (item 6.55: recusa > 0 = linha censurada) e pior trade em múltiplos do stop (item 6.56)."

### A9. O plano de testes não exercita os modos de falha que já custaram dinheiro, e a demo não reproduz a B3
- **Onde:** 15.2, 15.3.
- **Faltam:** matar o processo `terminal64.exe` pelo Gerenciador de Tarefas, que é crash **sem** `OnDeinit`, diferente de "fechar o MT5"; desconectar a internet **enquanto** uma entrada limite enche; stop e alvo executando juntos; zerar a líquida na mão com 2 robôs posicionados (C3); duas instâncias (C6); EA avulso com o mesmo magic; trocar o timeframe do gráfico; trocar de conta com o EA rodando; reinício durante o `OrderSend`; dia com pregão até 17:55; dia de vencimento; leilão por variação (quando houver); `DONE` sem deal (não dá para forçar na demo, então precisa de teste unitário com um broker falso). Item 4.28: **todo caminho de saída obrigatório precisa de evidência de ter disparado ao menos uma vez** (zeragem de cada robô, rede de segurança, zeragem de pregão anterior, horário perdido, correção). E a demo da Rico é casamento simulado: não mede fila, autonegociação nem comportamento de stop na B3 (item 4.7).
- **Correção (texto):** acrescentar os cenários acima à tabela 15.2, com "esperado" escrito, e trocar 15.3 por uma escada no real: 1 robô e 1 contrato por 5 pregões; depois 2 robôs em lados que podem se opor; depois os 5. Cada degrau exige: zero divergência não explicada, extrato da corretora (deals) igual ao log do maestro em contagem e preço, e cada caminho de saída obrigatório observado ao menos uma vez.

### A10. Retentativas sem cadência nem escalada
- **Onde:** 14.2 ("reavaliada no tick seguinte"), 14.4 ("tentar de novo depois do leilão"), 8.2 (recriar stop).
- **Cenário:** o stop é recusado (preço inválido, banda) e a 8.2 tenta recriar a cada tick. No WIN isso dá centenas de envios por minuto (itens 1.13, 1.18, 3.16), com risco de bloqueio da conta pela corretora.
- **Correção (texto):** "Toda ordem recusada entra em espera crescente (1 s, 2 s, 4 s, até 30 s). Após 5 recusas seguidas da mesma operação: ALERTA com push, e a operação só volta a ser tentada com nova condição de mercado. Teto de envios do maestro: N por minuto para entradas (recusa só a entrada excedente) e um disjuntor 5× acima que contabiliza tentativas. Saídas, stops e cancelamentos nunca são barrados pelo teto (item 1.22)."

### A11. DM: stop do EA e reserva no servidor no mesmo nível são dois caminhos de fechamento para a mesma ficha
- **Onde:** 4.3 (segundo marcador), A.3.
- Em C2 está o efeito da corrida. Aqui fica a decisão de desenho: o item 1.23 diz "fechar é sempre UM caminho por posição". Hoje, na conta real, o DM avulso já roda assim (SL da posição + stop do EA), e o risco de saída dupla não existia porque o SL da posição e o `PositionClose` atuam sobre a mesma posição (o fechamento duplo é recusado ou fica sem efeito). No maestro, a reserva é uma ordem independente e as duas saídas **somam**. A troca de mecanismo cria a corrida. Correção: ver C2, opções (a) ou (b), e a escolha entra no Apêndice B.

---

## Lacunas MÉDIAS

### M1. Memória: durabilidade, escopo e o que se perde de forma permanente
- **Onde:** 9, 13, 12.
- (a) `FileClose` não garante gravação física. O par checksum + `.bak` cobre isso, mas o teste "corromper `estado.txt`" deve incluir arquivo de **tamanho zero**. (b) Sem regra para memória de **outra conta ou servidor**: o cabeçalho guarda a conta, mas o texto não diz "conta diferente → ignora a memória, recuperação caso C, ALERTA". (c) `seq` e o resultado acumulado de cada robô (saldo virtual de 13) são permanentes. Se as duas cópias se perdem, o saldo virtual volta a R$1.000 sem aviso, e o `seq` reinicia e colide com comentários de hoje. Correção: "reconstruir `seq` como o máximo visto nos comentários do histórico; reconstruir o resultado acumulado pelo histórico completo de deals do magic (`HistorySelect(0, agora)`), logando a reconstrução." (d) 12 diz que "o contrato novo começa limpo" (memória por símbolo), e isso zera o saldo virtual do DM a cada rolagem, o que contradiz 13. Correção: separar o estado **permanente por robô** (em `FILE_COMMON`, sem símbolo na chave) do estado **de pregão** (por símbolo).

### M2. Cancelamento de órfã corre contra ordens recém-enviadas
- **Onde:** 8.4.
- **Cenário:** o robô acabou de enviar a entrada e o estado dele ainda não registrou o ticket (ou a ordem já está na lista e o registro não). A reconciliação vê ordem com magic de robô "que o robô não espera" e cancela.
- **Correção:** "Ordem só é órfã se não estiver no registro de trânsito (C1) e tiver mais de 5 s de vida (`ORDER_TIME_SETUP_MSC`)."

### M3. Correção de divergência: magic inconsistente e sem limite de repetição
- **Onde:** 4.4 ("`MagicMaestro` → correção") contra 8.1 ("correção com o magic do robô").
- **Correção:** decidir um único magic (o do robô, para a ficha fechar pelos deals) e retirar "sem dono" de 4.4, ou definir uma ficha MAESTRO que entra no Σ. Limite e escalada como em C10.

### M4. Logs insuficientes para auditar contra o extrato
- **Onde:** 11.
- **Faltam:** ticket da ordem **e** do deal, `request_id`, retcode **e** `retcode_external`, preço **pedido** e preço **executado** (`DEAL_PRICE`) na mesma linha (item 4.15: o diário gravava o pedido como se fosse o executado), hora do servidor (`TimeTradeServer`), hora do tick (`TimeCurrent`) e hora local, e uma linha bruta por evento de `OnTradeTransaction` (tipo, ordem, deal, estado). Política de escrita: abrir em append e fechar a cada linha, ou `FileFlush` a cada linha de nível ≥ AVISO (custo aceitável, porque só se loga mudança de estado). Política anti-spam: deduplicar por objeto (ticket, ficha), não por processo (item 1.12). `Alert()` só funciona com alguém olhando a tela, então ALERTA também chama `SendNotification` (push no celular). Conciliação diária obrigatória no `RESUMO`: contagem de contratos e Σ dos deals do símbolo contra o log (item 1.21).

### M5. Rolagem e outros símbolos: ordens dos magics fora do gráfico atual
- **Onde:** 12.
- **Cenário:** no dia da troca, o dono muda o gráfico para o contrato novo. Uma ordem DAY ou uma posição esquecida no contrato velho com magic de robô deixa de ser vista.
- **Correção:** "No `OnInit` e a cada minuto: varrer posições e ordens de **todos** os símbolos com magic de robô. Encontrou fora do símbolo do gráfico: ALERTA e bloqueio de entradas." E recusar operar símbolo não negociável (`SYMBOL_TRADE_MODE` ≠ `FULL`, por exemplo `WIN$N`/`WIN@` em conta real).

### M6. Custo da reconciliação a cada tick
- **Onde:** 8 ("a cada ciclo"), 7 (`OnTick`).
- `HistorySelect` do pregão inteiro em cada tick de WIN é caro. Recomendação: o `OnTradeTransaction` e o timer de 1 s marcam "suja"; o recálculo completo roda no máximo 1× por segundo, mais um recálculo imediato quando chega um deal. O incremental usa `HistorySelect(último_instante − 60 s, agora)` e deduplica por ticket. A ficha sai sempre de **uma** função só, para que evento e reconciliação nunca divirjam (14.7).

### M7. Modos de preenchimento e validade aceitos pelo símbolo não verificados
- **Onde:** 4.1, A ("`RETURN`, o que a B3 exige").
- Ler `SYMBOL_FILLING_MODE` e `SYMBOL_EXPIRATION_MODE` no `OnInit`, logar, e recusar iniciar se o necessário não existir (`SPECIFIED` para o GB, `DAY` para os stops, `GTC` se C9(a) for o escolhido). A frase "o que a B3 exige em limite" está correta para limite, mas não cobre ordem a mercado (C1, saídas): conferir na demo.

### M8. Mover stop: lado obrigatório, auto-disparo e janela de cancelar e recriar
- **Onde:** 3.1 (`Ficha_DefineStop`), A.5 (trailing por H1), A.2 (stop que aperta), A.1 (BE).
- (a) Mover com `OrderModify`, nunca cancelar e recriar (a janela sem stop). (b) Antes de enviar, conferir o lado em relação ao último negócio, com piso de 1 tick mesmo quando `SYMBOL_TRADE_STOPS_LEVEL` = 0 (item 1.25, regra 3). (c) Nível novo já atravessado: aplica 14.5 **com C2** (cancela o stop antigo e confirma antes da saída). (d) Nunca afrouxar o stop contra o que está registrado, salvo regra explícita do robô (item 1.10).

---

## Lacunas BAIXAS

- **B1.** "Máximo 31 caracteres (limite do MT5)" não está verificado: a documentação da MT5 não garante esse número e a corretora pode truncar. Confirmar na demo. Com o identificador de instância de C6, o formato `MAE|i1|CM|S|9999` ainda cabe.
- **B2.** O alarme do item 1.24 (`POSITION_PRICE_OPEN` fora da grade = duas pernas fundidas) **não serve** aqui: com várias fichas, preço médio fora da grade é normal. Registrar para ninguém portá-lo por engano.
- **B3.** Limites da conta e do símbolo: ler `ACCOUNT_LIMIT_ORDERS` e `SYMBOL_VOLUME_LIMIT` no `OnInit` (até 15 pendentes: 5 robôs × E/S/A) e logar. Perguntar à Rico qual é o limite de contratos de WIN por cliente em day trade.
- **B4.** Preenchimento parcial com `Lote > 1`: a regra de 6 está boa, mas falta o stop **parcial** (volume do stop = volume preenchido) e o que fazer quando o resto enche com o stop já movido.
- **B5.** 4.5 junto com 14.3: em hora cheia, várias velas fecham juntas (M5, M15, H1, H2) e o envio serial com espera do retorno atrasa a última entrada em alguns centenos de ms. É aceitável, mas a ordem fixa GB→C1 dá prioridade de fila sistemática ao GB. Registrar como diferença em relação ao avulso.

---

## Afirmações da especificação que estão erradas ou não são verificáveis como escritas

| Seção | Afirmação | Situação | Como verificar |
|---|---|---|---|
| Princípio 4 | "todo robô posicionado tem o stop dele como ordem pendente" | **Falsa** entre o fill e o registro do stop, e com o EA fora ou desconectado (C4) | Óbvio pelo desenho; medir na demo o atraso fill→stop |
| 3 / 10.6 | ficha = deals do dia; 10.6 detecta ficha de pregão anterior | **Contraditórias** (C9) | Abrir posição, fechar o MT5, reabrir no dia seguinte na demo |
| 4.4 | magic desconhecido = externa e "não mexe" | Correta para deal externo que aumenta a líquida; **perigosa** para deal externo que reduz (C3) | Zerar na mão na demo com 2 robôs posicionados |
| 4.3 | a ordem stop "fica no servidor com o terminal desligado" | Não verificada; e "no servidor" pode ser o da Rico ou a B3, com comportamentos diferentes em leilão e banda (C11) | Pergunta à Rico; teste com terminal fechado na demo (a demo não prova o comportamento em leilão real) |
| 13 | "entrada que reduz a líquida não exige margem nova" | Correta, mas a recíproca (saída ou stop que **aumenta** a líquida exige margem) está ausente (C8) | Demo com robôs em lados opostos e margem justa |
| 13 | portão por "margem livre" | Conflita com o item 1.19 (margem livre da Rico já mentiu) (A7) | Comparar `ACCOUNT_MARGIN_FREE` com o extrato da corretora em vários dias |
| 14.2 | bloquear ordem que cruza com ordem própria | Bloqueia saídas (C7) | Óbvio pelo texto |
| 14.6 | zerar SL/TP da posição se encontrar | Apaga a proteção de emergência do dono (C3) | Óbvio pelo texto |
| 14.7 | ticket processado uma vez evita contar duas vezes | Correto para eventos, mas não cobre o histórico ainda incompleto depois da reconexão (C10) | Desligar a internet com um deal acontecendo |
| 2 | "mudar inputs reinicia o EA … recuperação completa" | Parcial: em `REASON_PARAMETERS` as variáveis globais podem sobreviver (A6) | Teste na demo com um contador global logado no `OnInit` |
| A | "`ORDER_FILLING_RETURN` … o que a B3 exige em limite" | Correto para limite; não verificado para mercado (M7) | `SYMBOL_FILLING_MODE` e envio a mercado na demo |
| 4.2 | comentário identifica a ordem depois do reinício | Não verificado (A3) | Ver o comentário em ordem, deal e após `OrderModify` na demo |

---

## Checklist de `LICOES_DE_PRODUCAO.md` contra a especificação

| Item | Invariante | Coberto? |
|---|---|---|
| 1.1 | fechamento identificado; recusa de fechamento por margem | **Não** (C8) |
| 1.2 | proteção atômica com a entrada | **Não**, e é regressão (C4) |
| 1.4 / 1.23 | um caminho de fechamento por posição; excesso inverte em netting | Parcial (5.3), falha no cancelamento aceito e no DM (C2, A11) |
| 1.5 | "cancelei" só vale com confirmação | **Não** (C2) |
| 1.6 | consulta tem três respostas (sim, não, não sei) | **Não**: `PositionSelect` falso pode ser erro (C10, A6) |
| 1.7 | divergência trava entrada; não fechar às cegas | Parcial: 8.1 fecha cedo demais (C10) |
| 1.8 / P8-69 | reconciliar ordens vivas a cada passo | Sim (8.4), com a corrida de M2 |
| 1.9 | freio enxerga ordem parada | **Não** (A4) |
| 1.10 | campo vazio não apaga proteção; stop não afrouxa | Não dito (M8) |
| 1.12 / 1.13 | alarme por objeto; recusa repetida escala | **Não** (A10, M4) |
| 1.17 / 1.24 / 1.25 | DONE sem deal = não sei; histórico com prazo; comparar lado e tamanho | **Não** (C1, C10) |
| 1.19 | número de saldo da Rico não é gatilho | **Não** (A7) |
| 1.21 | contagem de contratos conciliada durante o pregão | Parcial (8), sem conciliação no resumo (M4) |
| 1.22 | cota nunca barra saída | **Não** (C7, A10) |
| 2.1 / 2.6 | decisão não se restaura, fato sim, janela se repõe por replay | Parcial (A5) |
| 2.4 | exclusividade imposta pelo sistema | **Não** (C6) |
| 2.8 / 4.28 | corte por relógio de parede; caminho obrigatório já disparou | **Não** (A1, A9) |
| 3.2 / 3.3 | teto sobre a exposição agregada, incluindo pendentes | **Não** (C8) |
| 4.17 | limite com preço defasado é mercado disfarçado | **Não** (A5) |
| 4.30 | ratchet que nasce do lado errado | **Não** (M8) |
| 5.33 / 6.54 / 6.55 / 6.56 | `last` no testador, tick do símbolo, recusas, pior trade | **Não** (A8) |
| 5.35 | fim do contínuo, não o call | **Não** (A1) |

---

## Perguntas que só um teste na conta demo (ou um envio mínimo no real) responde

Marcadas com **(real)** as que a demo da Rico provavelmente não reproduz porque o casamento é simulado. Essas pedem resposta escrita da Rico ou um teste com 1 contrato no real.

1. `ORDER_TYPE_SELL_STOP`/`BUY_STOP` no WINV26: aceita? Com validade DAY, GTC e SPECIFIED? Continua listada com o terminal fechado? Que `ORDER_TYPE` e que `ORDER_STATE` assume ao disparar?
2. O deal gerado por uma ordem stop ou limite pendente carrega o `DEAL_MAGIC` e o comentário da ordem? E o `DEAL_REASON`?
3. O `ORDER_COMMENT` sobrevive igual (sem truncar nem trocar) na ordem, no histórico e depois de `OrderModify`? Até quantos caracteres?
4. O `OrderModify` de uma ordem stop pendente mantém o mesmo ticket? A ordem fica fora do ar durante a modificação?
5. `OrderDelete` de uma ordem que acabou de disparar: qual retcode, qual `ORDER_STATE` no histórico, e quanto tempo até o histórico mostrar o desfecho?
6. Atraso medido entre o retorno do `OrderSend` (mercado) e o deal aparecer em `HistorySelect`, com p50 e máximo em 50 envios. Alguma vez volta `DONE` com `deal=0`?
7. Com a líquida em −1 (dois robôs vendidos, um comprado), o stop do comprado dispara e leva a líquida a −2: passa pela checagem de margem? Com margem justa, é recusado? **(real)**
8. Ordem pendente bloqueia margem na colocação? `OrderCalcMargin(WIN, 1)` devolve a margem de day trade da Rico ou a da B3?
9. `ACCOUNT_MARGIN_FREE` e `ACCOUNT_MARGIN` batem com o extrato da corretora no mesmo instante, em pelo menos 5 dias diferentes?
10. Zerar a líquida na mão pelo terminal: qual `DEAL_REASON` e qual magic aparecem? E pela mesa da corretora, por telefone? **(real)**
11. A Rico faz zeragem compulsória de day trade no WIN? A que horas, com que `DEAL_REASON`, e cancela as ordens pendentes? **(real)**
12. Autonegociação: um SELL_STOP disparando contra a própria BUY_LIMIT na melhor oferta executa, é cancelado, ou cancela a passiva? **(real)**
13. Stop disparado durante leilão (abertura, call de fechamento, leilão por variação): vira o quê? Ordem a mercado enviada pelo EA em leilão: qual retcode? **(real)**
14. Uma ficha (posição) que passa a noite: o `POSITION_PRICE_OPEN` muda para o ajuste no dia seguinte? Aparecem deals de ajuste ou variação de margem? Com que tipo e volume?
15. Que modos de preenchimento (`SYMBOL_FILLING_MODE`) e de validade (`SYMBOL_EXPIRATION_MODE`) o WINV26 aceita? Ordem a mercado com `RETURN` é aceita?
16. Duas instâncias: um segundo `FileOpen` sem `FILE_SHARE_*` no mesmo arquivo de trava falha? `GlobalVariableSetOnCondition` funciona como trava entre dois gráficos?
17. `REASON_PARAMETERS` e `REASON_CHARTCHANGE`: as variáveis globais do EA sobrevivem ao reinício?
18. Depois de 2 min sem internet: o histórico de deals volta completo de uma vez? Quanto tempo leva até `Σ deals = líquida`?
19. `TimeTradeServer()` continua andando com o feed parado? Qual a diferença para `TimeCurrent()` no leilão de abertura?
20. `ACCOUNT_LIMIT_ORDERS` e `SYMBOL_VOLUME_LIMIT` da conta para o WIN.
21. A demo da Rico casa ordens contra o livro real da B3 ou contra simulação? Essa resposta define o que a etapa da demo prova.

---

## Fechamento

**Lacunas por severidade:** 11 CRÍTICAS, 11 ALTAS, 8 MÉDIAS, 5 BAIXAS (35 no total).

**As 5 mais graves:**
1. **C1:** sem estado "em trânsito", um `DONE` sem deal leva a ficha a reenviar a saída e inverter a posição (o mecanismo dos itens 1.24 e 1.25).
2. **C3:** a zeragem manual do dono, a da corretora ou um stop-out viram "externa"; as fichas continuam abertas e os stops e alvos vivos abrem posições nuas (e o 14.6 apaga o SL de emergência do dono).
3. **C2:** "cancelei" vale pelo retcode e não pelo histórico; stop e saída a mercado (e a reserva do DM no mesmo nível) executam os dois e invertem.
4. **C4/C9:** a especificação perde a atomicidade stop+entrada dos EAs avulsos (entradas que enchem com o EA fora ou desconectado ficam nuas), e com stops DAY uma ficha que atravessa a noite fica sem stop e nem é reconstruída pelos "deals do dia".
5. **C7/C8:** a regra de autonegociação bloqueia saídas (o CM sem stop fica preso), e em netting o stop de um robô pode ser abertura para a conta, recusável por margem exatamente como no incidente de 2026-08-28.
