# WinMaestro — especificação

Versão da especificação: 0.1 (rascunho, 2026-10-06). Substitui o WinSeletor v1.00.

## 0. O que é, em uma frase

Um EA único para o WIN que roda a lógica dos 5 robôs ao mesmo tempo, dá a cada um uma **ficha** (posição virtual própria) e envia à corretora as ordens de cada robô **com o magic do próprio robô**, de modo que a posição líquida da conta NETTING seja sempre a soma das fichas. Com um robô só ligado ele é o WinSeletor; com os cinco ligados cada robô opera como se estivesse sozinho numa conta própria.

### Princípios (valem acima de qualquer detalhe abaixo)

1. **Cada robô continua decidindo sozinho, com as regras dele.** O maestro não filtra, não combina, não prioriza sinais. Ele só executa e contabiliza.
2. **A verdade sobre o que foi executado é a corretora**, não a memória do EA. Fichas são reconstruídas a partir do histórico de negócios (deals) do dia, pelo magic. O arquivo de memória guarda o que a corretora não sabe (o estado interno de cada robô: nível de stop controlado pelo EA, break-even feito, passo do alvo, decisão do dia já tomada...).
3. **Invariante:** posição líquida da conta no símbolo = Σ fichas dos robôs (+ exposição externa conhecida). Toda divergência é detectada, registrada e tratada por regra fixa (seção 8). Enquanto houver divergência não resolvida, **nenhuma entrada nova** é enviada.
4. **Proteção mora no servidor.** Todo robô posicionado tem o stop dele como ordem pendente na corretora, para que uma queda do PC/MT5 não deixe posição sem stop.
5. **Nada de trava não pedida.** O maestro não adiciona filtro de perda diária, limite de operações, etc. Só existem as proteções técnicas desta especificação (consistência, margem que a corretora recusaria de qualquer forma, fim de pregão).
6. **Tudo que o EA faz ou decide vira uma linha de log curta, com hora, robô e motivo.**

## 1. Arquivos, nomes e versão

| Item | Valor |
|---|---|
| EA | `mt5/WinMaestro.mq5` (+ `.ex5`, `_compile.log`) |
| Módulos | `mt5/WinMaestro/*.mqh`: `Fichas.mqh` (fichas, execução, reconciliação), `Memoria.mqh` (persistência), `Log.mqh`, um `.mqh` por robô (copiados do WinSeletor e adaptados) |
| Magic do maestro | `MagicMaestro = 80080900` (o do Seletor): chave de arquivos e ordens de correção sem dono |
| Magics dos robôs | os originais: GapBarra1 80080601, CincoMedias 80080501, Desloc 80080101, Retângulo 20261005, Win_c1 80080002 |
| WinSeletor | fica como `.bak` no repo e sai da pasta Experts depois que o maestro compilar |

## 2. Seleção de robôs (inputs)

Grupo **Maestro**:

| Input | Padrão | Efeito |
|---|---|---|
| `Ativo_GapBarra1` … `Ativo_Win_c1` (5 bools) | todos `true` | Robô ligado gera entradas novas. Desligado: não abre nada novo; **se tiver ficha aberta ou ordem viva, continua só gerindo até zerar** (saídas, stop, zeragem) — nunca é fechado por ter sido desligado. |
| `MagicMaestro` | 80080900 | Identificador desta instância (pasta de memória, ordens de correção). |
| `PastaMemoria` | `WinMaestro` | Subpasta de `MQL5/Files` (ver seção 9). |
| `CorrigirDivergencia` | `true` | Se `false`, divergência só é registrada e bloqueia entradas; não envia ordem de correção. |
| `LogArquivo` | `true` | Grava o log em arquivo além do Diário. |

Mudar inputs reinicia o EA (OnDeinit→OnInit): passa pela recuperação completa da seção 10, então mudar a seleção no meio do pregão é seguro.

Com **um robô só ligado** o comportamento é o do WinSeletor, com uma diferença: não existe "troca pendente". Ligar outro robô não espera ninguém zerar, porque as fichas são independentes.

Os inputs de cada robô (grupos `WinGapBarra1`, `WinCincoMedias`, …) ficam exatamente como no WinSeletor (prefixos `GB_`, `CM_`, `DM_`, `RE_`, `C1_`).

## 3. A ficha (posição virtual de cada robô)

Uma ficha por robô:

| Campo | Fonte de verdade |
|---|---|
| `volume_assinado` (+compra / −venda, em contratos) | Σ dos deals do dia com o magic do robô (compra +, venda −) |
| `preco_medio` | média ponderada dos deals de abertura da ficha atual (desde a última vez em que ela foi a zero) |
| `hora_abertura` | hora do primeiro deal da ficha atual |
| `stop`, `alvo` (níveis pedidos pelo robô) | memória (seção 9) + ordens pendentes vivas com o magic do robô |
| `ticket_stop`, `ticket_alvo`, `ticket_entrada` | ordens pendentes vivas com o magic do robô, identificadas pelo comentário (seção 4.2) |
| `resultado_realizado_dia` | calculado dos deals do robô |
| estado interno do robô | memória (seção 9) |

Estados permitidos de uma ficha: `0` ou `±Lote` do robô (todos os robôs operam 1 lote por vez; nenhum piramida). Qualquer outro valor é **divergência de ficha** (seção 8).

### 3.1 O que os módulos passam a usar (camada de fichas)

Os módulos deixam de tocar em `PositionSelect/PositionGet*/trade.Position*`. Cada chamada vira uma função da camada:

| Hoje no módulo | No maestro |
|---|---|
| `PositionSelect(_Symbol)` + magic == meu | `Ficha_Tem(robo)` |
| `PositionSelect(_Symbol)` → "tem posição de outro robô, não entro" | **removido** (é exatamente o bloqueio que o maestro elimina) |
| `POSITION_PRICE_OPEN / TYPE / TIME / VOLUME` | `Ficha_Preco(robo)`, `Ficha_Lado(robo)`, `Ficha_Hora(robo)`, `Ficha_Volume(robo)` |
| `POSITION_SL / POSITION_TP` | `Ficha_Stop(robo)`, `Ficha_Alvo(robo)` |
| `trade.PositionClose(_Symbol)` ou `(ticket)` | `Ficha_Fecha(robo, motivo)` — ordem a mercado oposta, volume da ficha, magic do robô. **Nunca** fecha a posição líquida inteira |
| `trade.PositionModify(sl, tp)` | `Ficha_DefineStop(robo, nivel, motivo)` / `Ficha_DefineAlvo(robo, nivel, motivo)` |
| `trade.Buy/Sell(lote, …, sl, …)` (entrada a mercado com stop) | `Ficha_EntraMercado(robo, lado, lote, stop, motivo)` — envia a mercado; o stop vira ordem pendente assim que o deal chegar |
| `trade.BuyLimit/SellLimit` de **entrada** | `Ficha_EntraLimite(robo, lado, lote, preco, stop, validade, expira, motivo)` — ordem limite real com magic do robô |
| `trade.BuyLimit/SellLimit` de **alvo** | `Ficha_DefineAlvo` (limite real oposta, com magic do robô) |
| `trade.OrderModify / OrderDelete` das próprias ordens | `Ficha_MoveOrdem` / `Ficha_CancelaOrdem` (só ordens do próprio magic) |
| `HistorySelectByPosition`, `POSITION_IDENTIFIER`, `POSITION_COMMENT` | dados da ficha (hora, comentário da entrada guardado na ficha) |

Regra: **toda ordem que sai do maestro carrega o magic do robô dono** (`trade.SetExpertMagicNumber` antes de cada envio). Ordens de correção sem dono identificável usam `MagicMaestro`.

## 4. Execução

### 4.1 Tipos de ordem

| Situação | Ordem real |
|---|---|
| Entrada a mercado | mercado, magic do robô |
| Entrada limite | limite, magic do robô, validade do robô (DAY / SPECIFIED / GTC tratada como DAY — ver 12) |
| Stop do robô | **ordem stop pendente** (SELL_STOP para ficha comprada, BUY_STOP para vendida), volume = ficha, validade DAY, magic do robô. Ver 4.3 |
| Alvo do robô | limite oposta, volume = ficha, magic do robô |
| Saída do robô por regra (EMA, esticada, break-even, zeragem…) | mercado oposta, volume = ficha, magic do robô; antes de enviar, cancela stop e alvo pendentes do robô (seção 5) |

### 4.2 Comentário padronizado (identifica a ordem mesmo depois de reinício)

`MAE|<robo>|<papel>|<seq>` — `robo` = GB, CM, DM, RE, C1; `papel` = `E` (entrada), `S` (stop), `A` (alvo), `X` (saída a mercado), `C` (correção); `seq` = contador da ficha (persistido) para distinguir operações do mesmo dia. Máximo 31 caracteres (limite do MT5). Em `C` (correção) acrescenta-se o motivo curto no log, não no comentário.

### 4.3 Stop no servidor

Em NETTING a posição tem **um** SL/TP só, que não serve para 5 robôs. Por isso o SL/TP da posição **não é usado** (fica 0). Cada robô posicionado tem a sua ordem stop pendente.

- Robôs com stop **no servidor** hoje (SL da posição): a ordem stop pendente substitui o SL com o mesmo nível.
- Robôs com stop **controlado pelo EA** (fecha a mercado quando o preço passa): continuam controlando pelo EA **e** ganham uma ordem stop pendente de **reserva** no mesmo nível, que só importa se o EA estiver fora do ar (o Desloc já faz isso hoje com o SL da posição na conta real). Quando o EA fecha a mercado, cancela a reserva antes.
- Se o robô não tem stop (ex.: ficha sem stop definido pelas regras), não há ordem stop; o log registra "sem stop" na abertura.
- **A verificar na conta antes de ligar em real** (pergunta 1 da seção 14): a Rico aceita `ORDER_TYPE_SELL_STOP/BUY_STOP` no WIN com magic e validade DAY, e ela fica no servidor do MT5 com o terminal desligado? Se não aceitar, usar `SELL_STOP_LIMIT/BUY_STOP_LIMIT` com limite a N ticks (input) além do gatilho.

### 4.4 Atribuição dos negócios

Todo deal do símbolo é atribuído pelo `DEAL_MAGIC`:
- magic de um robô → ficha desse robô;
- `MagicMaestro` → correção (pertence à ficha que o comentário indicar, ou "sem dono");
- qualquer outro magic (0 = manual, outros EAs) → **exposição externa** (seção 8.3).

### 4.5 Ordem de processamento num mesmo instante

Quando vários robôs agem no mesmo tick: primeiro todas as **saídas** (dos robôs na ordem fixa GB, CM, DM, RE, C1), depois as **entradas** (mesma ordem). Saídas primeiro evitam inflar a posição líquida à toa e reduzem margem exigida.

## 5. Stop e alvo do mesmo robô (OCO)

Stop e alvo são duas ordens pendentes independentes na corretora. Quando uma executa, a outra precisa morrer:

1. Ao receber o deal de saída do robô (via `OnTradeTransaction` ou na reconciliação), se a ficha foi a zero → cancela **todas** as ordens pendentes de papel `S`, `A` e `E` daquele robô.
2. Se as duas executarem antes do cancelamento (gap, EA fora do ar), a ficha fica com volume oposto (ex.: −1 numa ficha que era +1) → **divergência de ficha** → correção a mercado com o magic do robô até a ficha voltar a 0 (seção 8.1). Log nível ALERTA.
3. Saída a mercado por regra: **primeiro** cancela stop e alvo, confirma o cancelamento, **depois** envia a saída. Se o cancelamento falhar porque a ordem acabou de executar, não envia a saída (a ficha já zerou) — a reconciliação confirma.

## 6. Ciclo de vida de uma operação de um robô

```
LIVRE --(sinal, robô ativo, sem divergência, margem ok)--> ENTRADA_PENDENTE (limite viva)  ou  ABRINDO (mercado enviada)
ENTRADA_PENDENTE --(deal com magic do robô)--> POSICIONADO (cria stop/alvo pendentes)
ENTRADA_PENDENTE --(validade/cancelamento do robô)--> LIVRE
POSICIONADO --(stop/alvo executou | saída por regra | zeragem)--> LIVRE (cancela pendentes restantes)
```

Cada transição: grava memória (seção 9) e log (seção 11). Preenchimento **parcial** de entrada limite: a ficha fica com o volume parcial, o stop/alvo são criados com esse volume e ajustados se o resto preencher; ao vencer a validade, o resto é cancelado e a ficha segue com o parcial (com WIN e 1 contrato isso não acontece, mas o código não pode quebrar se acontecer).

## 7. Eventos do MT5

| Evento | O que faz |
|---|---|
| `OnInit` | Recuperação completa (seção 10) **antes** de iniciar os módulos. Só então `EventSetTimer(1)`. |
| `OnTradeTransaction` | Deal novo do símbolo → atualiza a ficha do magic, trata OCO, grava memória, loga. Ordem rejeitada/cancelada → loga e informa o módulo. |
| `OnTick` | Reconciliação rápida (seção 8) → `Tick()` de cada robô ligado ou com ficha/ordem viva, na ordem 4.5. |
| `OnTimer` (1 s) | Reconciliação mesmo sem tick; checa horário de zeragem; grava memória se houver mudança pendente; heartbeat em memória (hora do último ciclo vivo). |
| `OnDeinit` | Grava memória e loga o motivo (`reason`). **Não cancela nem fecha nada** (stops ficam no servidor protegendo). Exceção herdada: entrada do Retângulo não preenchida é cancelada (estado não sobreviveria) — ver apêndice. |

`OnTradeTransaction` não é garantido (pode perder evento em reconexão). Por isso a reconciliação por histórico roda a cada tick e a cada segundo: o evento é o caminho rápido, a reconciliação é o caminho seguro.

## 8. Reconciliação contínua

A cada ciclo:

1. Lê a posição líquida real do símbolo (`PositionSelect`).
2. Recalcula as fichas a partir dos deals do dia por magic (com cache incremental: só deals novos desde o último ticket visto).
3. Compara: `posição real == Σ fichas + externa`.
4. Confere ordens pendentes: cada ficha posicionada tem o stop dela? cada ordem pendente com magic de robô corresponde a algo que o robô espera?

### 8.1 Divergência de ficha (volume fora de 0/±Lote, ou sinal trocado)
Causa típica: stop e alvo executaram juntos; ordem duplicada após reconexão. Ação (se `CorrigirDivergencia`): ordem a mercado com o **magic do robô** e papel `C` levando a ficha a 0. Log ALERTA. O robô volta a LIVRE.

### 8.2 Ficha posicionada sem stop no servidor
Recria a ordem stop no nível guardado na memória. Se a memória não tem o nível: recalcula pela regra do robô se possível (apêndice), senão usa o stop de emergência do robô (apêndice) e loga ALERTA.

### 8.3 Exposição externa (deals de magic desconhecido: operação manual, outro EA)
O maestro **não mexe** nela. Registra ALERTA uma vez por mudança, mostra no painel/comentário do gráfico, e continua operando as fichas normalmente (a soma passa a incluir a externa). Alerta de que outros EAs no mesmo símbolo devem ser desligados.

### 8.4 Ordem órfã
Ordem pendente com magic de robô que o robô não espera (ex.: entrada de antes do reinício cujo estado não foi recuperado): cancela e loga. Ordem pendente de magic desconhecido: não toca, loga.

### 8.5 Bloqueio por divergência
Enquanto houver divergência não resolvida (correção recusada pela corretora, mercado fechado, externa mudando…), **nenhum robô abre entrada nova**; saídas e stops continuam funcionando. Log uma vez ao entrar e uma vez ao sair do bloqueio.

## 9. Memória (persistência em disco)

### 9.1 Onde
`MQL5/Files/<PastaMemoria>/<simbolo>_<MagicMaestro>/`:
- `estado.txt` — estado atual (sobrescrito a cada mudança);
- `estado.bak` — cópia do anterior;
- `logs/AAAA-MM-DD.log` — log do dia (seção 11).

No Testador a pasta é a do agente de teste; a memória começa vazia a cada teste (apaga ao iniciar no Testador).

### 9.2 O que guarda
Formato texto `chave=valor`, uma por linha, legível no Bloco de Notas:
- cabeçalho: versão do formato, versão do EA, símbolo, conta, `MagicMaestro`, hora da gravação, último ticket de deal processado, heartbeat;
- por robô: ligado/desligado, estado do ciclo (seção 6), `seq`, níveis de stop e alvo pedidos, tickets das ordens dele, comentário da entrada, e **todas as variáveis internas que o robô precisa para continuar igual depois de reiniciar** (lista por robô no apêndice);
- data do pregão a que o estado se refere.

### 9.3 Quando grava
A cada transição do ciclo, a cada mudança de nível de stop/alvo, a cada mudança de estado interno relevante do robô, e no `OnDeinit`. Nunca mais de uma vez por segundo por mudança acumulada (o timer junta as mudanças), exceto transições de ciclo, que gravam na hora.

### 9.4 Como grava (sem corromper se o PC desligar no meio)
Escreve `estado.tmp`, fecha, copia o atual para `estado.bak`, move `estado.tmp` → `estado.txt` (`FileMove` com `FILE_REWRITE`). A última linha do arquivo é `fim=<checksum simples>`; arquivo sem essa linha ou com checksum errado é considerado corrompido → usa `estado.bak`; se os dois falharem → recuperação só pela corretora (seção 10, caso C).

## 10. Recuperação na partida (antes de qualquer atividade)

Ordem fixa, sempre, inclusive na primeira vez do dia:

1. **Identifica o ambiente**: Testador ou real; símbolo; conta; tipo de conta = NETTING (se HEDGING → recusa iniciar com mensagem clara). Loga `INICIO`.
2. **Espera dados**: conexão com o servidor, histórico de deals carregado (`HistorySelect` do início do pregão até agora), símbolo sincronizado. Se não houver conexão, fica em espera com log a cada 30 s, sem enviar nada.
3. **Lê a memória** (`estado.txt` → `estado.bak`). Se for de outro pregão: guarda só o que é permanente (seq, configurações) e descarta o estado de ciclo.
4. **Reconstrói as fichas pela corretora**: deals do dia por magic; posição líquida real; ordens pendentes por magic e comentário.
5. **Compara memória × corretora** e classifica cada robô:
   - **A. Confere** (ficha e ordens batem com a memória): restaura o estado interno do robô e segue.
   - **B. A corretora andou enquanto o EA estava fora** (stop ou alvo executou, entrada encheu, validade venceu): a corretora vence. Atualiza a ficha, cancela a ordem irmã (OCO), registra no log cada evento perdido com a hora real do deal ("ocorreu às 11:42 com o EA fora").
   - **C. Sem memória utilizável**: ficha pela corretora; estado interno recalculado das barras quando possível (apêndice); se o robô está posicionado e não dá para recalcular algo essencial (ex.: nível do stop controlado pelo EA), usa o stop da ordem pendente viva; se nem isso existe, aplica o stop de emergência do robô. Log ALERTA.
6. **Posição de pregão anterior** (ficha aberta com deal de abertura de outro dia — só acontece se a zeragem falhou ou o EA ficou fora no fim do pregão): fecha a mercado na primeira oportunidade do pregão de hoje (depois do leilão de abertura), com o magic do robô, papel `X`, log ALERTA.
7. **Horário perdido**: se o horário de zeragem de algum robô passou com a ficha aberta, zera agora.
8. **Ordens órfãs**: cancela as do próprio conjunto de magics que nenhum robô reconhece.
9. **Confere o invariante** (seção 8). Se houver divergência → corrige (se permitido) ou entra em bloqueio.
10. **Só então** inicia os módulos (`Init()` de cada robô com o estado restaurado), grava a memória, loga `PRONTO` com o resumo: fichas, ordens vivas, robôs ligados, divergências.

Qualquer falha num passo → log ERRO com o passo, e o EA **não inicia os robôs** (fica só protegendo: mantém stops e reconcilia).

## 11. Logs

### 11.1 Onde
Diário do MT5 (aba Experts) **e** `logs/AAAA-MM-DD.log`. Uma linha por evento.

### 11.2 Formato
`HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe curto`

- `NIVEL`: `INFO`, `AVISO`, `ALERTA` (exige atenção do dono; também dispara `Alert()` uma vez), `ERRO`.
- `ROBO`: `GB`, `CM`, `DM`, `RE`, `C1` ou `MAESTRO`.
- Detalhe com números: preços, níveis, tickets, posição líquida antes→depois.

Exemplos:
```
10:00:00.012 | INFO   | CM | SINAL       | venda; limite 176855; validade 5 velas H2
10:00:00.140 | INFO   | CM | ORDEM       | sell limit 1 @176855 #48211 aceita
10:03:12.501 | INFO   | CM | ENTROU      | vendido 1 @176855; liquida +1 -> 0
10:03:12.620 | INFO   | CM | STOP        | buy stop 1 @177900 #48230 (servidor)
12:00:00.008 | INFO   | CM | SAIDA       | fechou do outro lado da EMA; compra 1 mercado @176210; +129,00
12:00:00.010 | INFO   | CM | CANCELA     | stop #48230
09:00:02.300 | ALERTA | MAESTRO | RECUPERA | EA ficou fora 09:41-10:12; DM: stop executou 09:58 @190165 (-68,00)
```

### 11.3 Catálogo de eventos
`INICIO`, `ESPERA`, `MEMORIA` (lida/gravada/corrompida), `RECUPERA`, `PRONTO`, `LIGADO`/`DESLIGADO` (robô), `SINAL`, `BLOQUEIO` (regra do gap, filtro do robô, margem, divergência — sempre com o motivo), `ORDEM` (enviada/aceita), `REJEITADA` (com retcode e descrição), `ENTROU`, `PARCIAL`, `STOP`/`ALVO` (criado/movido), `SAIDA` (com motivo e R$), `CANCELA`, `ZERAGEM`, `DIVERGENCIA`, `CORRECAO`, `EXTERNA`, `ORFA`, `FIM` (OnDeinit com motivo), `RESUMO`.

### 11.4 Resumo do dia
No fim do pregão (após a última zeragem) e no `OnDeinit`: uma linha por robô com operações, acertos, R$ bruto, e a linha do total da conta; e a contagem de alertas/erros do dia.

### 11.5 Painel no gráfico
`Comment()` com: robôs ligados, ficha de cada um (lado, preço, stop, alvo, resultado aberto), posição líquida real, status (`OK` / `BLOQUEADO: motivo`), hora da última gravação da memória.

## 12. Horários e fim de pregão

- Cada robô mantém os seus horários (entrada, última entrada, zeragem), como no EA avulso.
- **Rede de segurança do maestro**: em `fim do pregão − 3 min` (lido da sessão do símbolo; fallback 18:22), se ainda houver ficha aberta, o maestro zera a ficha com o magic do robô e loga ALERTA (significa que a zeragem do próprio robô falhou).
- Ordens GTC dos robôs (Retângulo, alvo do GapBarra1) passam a ser DAY no maestro; no fim do pregão o maestro cancela qualquer pendente sobrando dos seus magics.
- Dia de vencimento e rolagem: o EA roda no contrato vigente (ex.: WINV26). Na troca de contrato o dono troca o gráfico; a memória é por símbolo, então o contrato novo começa limpo. Ficha aberta no contrato velho não existe (todos zeram no dia).

## 13. Capital, margem e saldo

- **Margem**: antes de cada entrada, `OrderCalcMargin` para o volume que a posição líquida vai **aumentar** (entrada que reduz a líquida não exige margem nova). Se a margem livre não cobre → não envia, log `BLOQUEIO margem` (é o que a corretora faria; aqui fica registrado com motivo).
- **Saldo usado pelos robôs**: o WinDeslocamentoMatinal limita o stop a 10% do **saldo**. Numa conta compartilhada o saldo da conta não é o capital do robô. Regra: cada robô que usa saldo usa o **saldo virtual do robô** = `CapitalRobo` (input por robô, padrão R$1.000) + resultado realizado acumulado do robô desde o início (persistido). Isso reproduz o comportamento testado (cada robô com o seu R$1.000). Input `UsarSaldoDaConta` (padrão `false`) volta ao comportamento antigo.
- Contratos: cada robô usa o `Lote` dele (padrão 1). Máximo de contratos simultâneos medido no replay 2022–2026: 4.

## 14. Riscos de bolsa e perguntas a verificar na conta antes do real

1. **Ordem stop pendente na Rico/B3** (seção 4.3): aceita? fica no servidor com o terminal desligado? dispara a mercado ou vira limite?
2. **Autonegociação (self-trade)**: duas ordens da mesma conta em lados opostos podem se cruzar (ex.: limite de compra do robô A em 100 e limite de venda do robô B em 100; ou o stop de A disparando contra a limite de B). A B3 monitora autonegociação. Regra do maestro: antes de enviar uma ordem, se ela puder cruzar com uma ordem própria de lado oposto (compra ≥ venda própria viva, ou venda ≤ compra própria viva), **não envia** e loga `BLOQUEIO autonegociacao`; a ordem é reavaliada no tick seguinte. Para stops (que disparam no servidor), registrar no log quando um deal de compra e um de venda próprios saem no mesmo preço e segundo. Pergunta à corretora: há prevenção de autonegociação (cancela a agressora)? Como aparece no retorno?
3. **Limite de ordens por segundo / mensagens** da corretora: o maestro envia no máximo uma ordem por vez e espera o retorno antes da próxima.
4. **Leilão** (abertura, fechamento, leilão por variação): ordens a mercado enviadas em leilão são rejeitadas ou ficam pendentes. Tratar retcode, logar e tentar de novo depois do leilão (zeragem) ou desistir (entrada, conforme a regra do robô).
5. **Rejeição de stop** por preço já atravessado (stop acima do último numa venda etc.): se o preço já passou do stop, o robô sai a mercado na hora, log `STOP atravessado`.
6. **Netting e SL/TP da posição**: confirmar que nenhum módulo ou ação do dono põe SL/TP na posição líquida (ele valeria para a soma e zeraria todo mundo). O maestro zera SL/TP da posição se encontrar e loga ALERTA.
7. **Reconexão**: depois de uma reconexão, a corretora pode reenviar transações. A atribuição por ticket de deal (cada ticket processado uma vez só, último ticket na memória) evita contar duas vezes.

## 15. Testes antes de usar com dinheiro

### 15.1 Equivalência (Testador, WIN$N, ticks reais)
1. Cada robô sozinho no maestro × EA avulso no mesmo período: lista de negócios idêntica (hora, lado, preço, resultado). Diferença aceitável só onde o stop virou ordem pendente em vez de SL (registrar).
2. Os 5 ligados × replay T6 (`combinacoes/z9_netting/t6_maestro`): resultado por robô igual ao isolado; posição líquida máxima 4.

### 15.2 Falhas (conta demo, pregão real)
| Cenário | Esperado |
|---|---|
| Fechar o MT5 com 2 robôs posicionados e reabrir 5 min depois | Fichas recuperadas, stops continuam no servidor, log `RECUPERA` com o que mudou |
| Fechar o MT5 e deixar o stop de um robô executar | Na volta: ficha zerada, alvo dele cancelado, evento logado com a hora real |
| Apagar `estado.txt` com robôs posicionados | Recuperação pelo caso C com ALERTA; nenhum robô sem stop |
| Corromper `estado.txt` (cortar o arquivo) | Usa `estado.bak` |
| Desligar a internet 2 min | `ESPERA`, sem ordens; na volta, reconcilia |
| Abrir uma posição manual no símbolo | `EXTERNA` ALERTA; robôs seguem |
| Desligar um robô (input) com ficha aberta | Ele só gere até zerar; não abre nova |
| Deixar posição aberta passar da zeragem (EA fechado às 18:20, aberto 18:23) | Zera na hora |
| Abrir no dia seguinte com ficha de ontem | Zera depois do leilão, ALERTA |

### 15.3 Critério para ir ao real
Todos os cenários acima passando na demo, 5 pregões seguidos na demo sem `DIVERGENCIA` não explicada, e as perguntas da seção 14 respondidas.

## 16. Fora do escopo (de propósito)

- Combinar sinais, prioridade entre robôs, consenso (testados na Z9, piores que fichas independentes).
- Limite de perda diária, de operações, de horário extra: não pedidos.
- Hedging: o maestro só roda em NETTING.

## Apêndice A — por robô

Fonte: `WinMaestro_inventario_modulos.md` (linhas citadas lá). Regras que valem para os cinco:
- Os 3 bloqueios por "posição de outro robô" (CM L774, DM L379, C1 L620) são **removidos**.
- Os 9 fechamentos que hoje fecham a posição INTEIRA (`PositionClose(_Symbol)` ou pelo ticket da posição líquida) viram `Ficha_Fecha(robo)`.
- Todo `PositionModify` de SL vira `Ficha_DefineStop` (ordem stop pendente do robô); todo SL anexado na entrada vira stop pendente criado no preenchimento.
- Ordens GTC viram DAY (seção 12). Preenchimento das ordens: um jeito só no maestro (`ORDER_FILLING_RETURN`, desvio 0, o que o GapBarra1 usa e a B3 exige em limite).
- `StopEmergenciaPts` (input único, padrão 1.200 pts): só usado quando a recuperação não consegue saber o stop de um robô posicionado (seção 10, caso C). Sempre com ALERTA.
- O "gate de vela nova" (`g_ultima_barra` e equivalentes) passa a ser **persistido**: corrige o defeito atual de reentrar na mesma vela depois de um reinício (CM, C1).

### A.1 WinGapBarra1 (GB, magic 80080601)
- Ficha: entrada limite 09:05 com stop 1.200 (era SL anexado → stop pendente criado no preenchimento); alvo e break-even desligados no padrão (se ligados: alvo = limite oposta do robô; BE = move o stop pendente).
- Persistir: `g_decidido`, `g_exp`, `g_be_feito`, dia, ticket da entrada. **Corrige** o defeito atual: reinício entre 09:05 e 09:35 com a ordem viva enviava uma 2ª entrada.
- Recalculável: stop = preço da ficha ∓ `StopPts`.
- Zeragem 18:20 (17:50 no regime antigo). **Novo**: posição de pregão anterior zera na abertura (regra geral 10.6; hoje não existe).

### A.2 WinCincoMedias (CM, magic 80080501)
- Ficha guarda `a_favor` (hoje lido do comentário da posição/histórico — em netting o comentário é da posição líquida). Entrada limite DAY; saídas a mercado pelo EA; "stop que aperta" = stop pendente do robô.
- **Sem stop inicial** (é a regra do robô: só ganha stop depois de 2 velas H2 no negativo). Consequência: com o EA fora do ar, a ficha do CM fica sem proteção no servidor. **Decisão do dono** (ver B.1).
- Persistir: `g_ultima_barra`, `a_favor`, nível do stop que aperta, ticket/hora/lado da entrada pendente.
- Recalculável: stop que aperta (das barras desde a hora da ficha), histórico de volume relativo (pesado: calcular no OnInit depois da recuperação, nunca dentro do primeiro tick que precisa gerir stops).
- Zeragem 18:24 ou fim da sessão − 1 min.

### A.3 WinDeslocamentoMatinal (DM, magic 80080101)
- Stop **controlado pelo EA** (fecha a mercado quando o último negócio cruza `g_stopNivel`) + stop pendente de **reserva** no mesmo nível.
- Persistir (crítico): `g_stopNivel`, `g_distStop`, `g_stopAjustado`, `g_decidiu`, `g_dia`, `g_ordem`, `g_ordemHora`, `g_ordemPreco`. **Corrige** os defeitos atuais: reinício perdia o stop do EA (ficava só a reserva, ou nada se a queda foi entre o preenchimento e o 1º ajuste) e deixava a ordem de entrada órfã, que podia encher sem stop.
- Recalculável se a memória falhar: `g_distStop` pela decisão das 10:30 refeita das barras (mesma regra: distância até a linha da abertura apertada pelo teto de risco com o saldo virtual do robô).
- Saldo: usa o saldo virtual do robô (seção 13) no teto de 10%.
- Zeragem fim da sessão − 5 min.

### A.4 WinRetanguloEma34 (RE, magic 20261005)
- Detecção do preenchimento passa a ser pelo deal com o magic do robô (hoje depende de a posição líquida ter o magic dele — com outro robô posicionado, o preenchimento **nunca** era visto e a posição ficava sem stop nem alvo).
- Stop = stop pendente do robô (era SL da posição); alvo = limite do robô que se aproxima (OrderModify continua, na ordem do robô).
- Persistir: bloco da entrada pendente (`g_ordem_pendente`, `g_ticket_entrada`, `g_barras_esperando`, `g_lado_entrada`, `g_meio_original`, `g_stop_original`, `g_alvo_original`), bloco da posição (`g_ticket_alvo`, `g_preco_entrada`, `g_largura_posicao`, `g_frac_alvo_atual`, `g_barra_do_fill`, `g_barras_posicao`) e o retângulo vivo (`g_tem_retangulo`, `g_topo`, `g_piso`, `g_largura`, `g_meio`, `g_fora_seguidas`). **Corrige**: alvo parava de se aproximar e ficava órfão (GTC, sobrevivia à noite) depois de um reinício.
- Com a persistência, o `Deinit` **não** precisa mais cancelar a entrada pendente (o estado sobrevive). Em crash continua protegido: a reconciliação reconhece a entrada pelo comentário e o estado pela memória.
- Zeragem 17:00 (avaliada a cada vela M15, como hoje; a rede de segurança do maestro cobre falha).

### A.5 Win_c1 (C1, magic 80080002)
- Único que entra **a mercado**: preço da ficha = preço do deal. SL anexado → stop pendente criado no deal; trailing por vela H1 = move o stop pendente.
- Break-even e esticada usam preço e hora **da ficha** (hoje usam os da posição líquida).
- Persistir: `g_ultima_barra`, hora/preço da ficha (vêm da corretora), nível do stop.
- Recalculável: pico de afastamento e esticada armada (das barras desde a hora da ficha), stop (roxa ∓ K×ATR da última H1 fechada).
- Zeragem 17:50.

## Apêndice B — decisões do dono antes de implementar

1. **Stop de reserva do WinCincoMedias.** O robô não tem stop inicial; com o EA fora do ar a ficha dele fica sem proteção. Opções: (a) manter como está (fiel ao testado); (b) stop de reserva distante, que nunca dispararia nos testes 2022–2026 (a distância é medida no replay antes de fixar) e só protege em queda. Recomendação: (b).
2. **Saldo do WinDeslocamentoMatinal**: saldo virtual do robô (R$1.000 + resultado dele) — recomendado — ou saldo da conta.
3. **Ordens GTC → DAY** (Retângulo e alvo do GapBarra1): recomendado, porque todos são day trade e nenhuma ordem deve passar a noite.
4. **WinSeletor**: aposentado (vira `.bak`), já que o maestro com um robô ligado faz o mesmo.
