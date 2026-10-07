# WinMaestro — especificação

Versão da especificação: 0.2 (2026-10-06). Substitui o WinSeletor v1.00.

Convenções deste documento:
- "item X.Y" aponta para `LICOES_DE_PRODUCAO.md`; "P n" aponta para a pergunta n da seção 14.2.
- **"a verificar"** = depende do comportamento da Rico, da B3 ou da MT5 e ainda não foi confirmado; cada ocorrência cita a pergunta que decide.
- Todo prazo, contagem ou nível aparece com número. Onde o número é input, o padrão está na seção 2.
- WIN: tick = 5 pontos = R$1,00 por contrato; 1 ponto = R$0,20 por contrato. O EA **lê** esses valores do símbolo (`SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_TRADE_TICK_VALUE`) e recusa iniciar se vierem zerados (item 5.22); os números deste texto são só para leitura.

## 0. O que é, em uma frase

Um EA único para o WIN que roda a lógica dos 5 robôs ao mesmo tempo, dá a cada um uma **ficha** (posição virtual própria) e envia à corretora as ordens de cada robô **com o magic do próprio robô**, de modo que a posição líquida da conta NETTING seja sempre a soma das fichas mais a exposição externa conhecida. Com um robô só ligado ele faz o que o WinSeletor fazia; com os cinco ligados cada robô opera como se estivesse sozinho numa conta própria.

### Princípios (valem acima de qualquer detalhe abaixo)

1. **Cada robô continua decidindo sozinho, com as regras dele.** O maestro não filtra, não combina, não prioriza sinais. Ele executa, contabiliza e protege.
2. **A verdade sobre o que foi executado é a corretora**, não a memória do EA. Fichas são reconstruídas a partir do histórico de negócios (deals) por magic (seção 3). A memória em disco guarda o que a corretora não sabe: o estado interno de cada robô e o registro de ordens em trânsito (seção 9).
3. **Invariante:** posição líquida da conta no símbolo = Σ fichas efetivas dos robôs + exposição externa não absorvida. Divergência confirmada (seção 8.2) bloqueia toda entrada nova e cancela as entradas pendentes (seção 8.6).
4. **Proteção mora no servidor.** Todo robô posicionado tem o stop dele como ordem stop pendente na corretora, com validade GTC (seção 4.3). **Exceções conhecidas e aceitas** (limitação da MT5 em conta netting, que não tem OCO nem OTO entre ordens independentes): (a) entre o preenchimento de uma entrada e o registro do stop dela, e durante todo o tempo em que o EA estiver fora do ar ou desconectado, a ficha recém-aberta fica sem stop no servidor; (b) com o EA fora do ar, uma ficha com stop e alvo vivos pode ter os dois executados e ficar com o sinal trocado, sem stop; (c) o WinCincoMedias não tem stop inicial pela regra dele e fica só com a reserva distante (Apêndice B.1). O pior caso numérico dessas exceções está na seção 13.4 e é decisão do dono (Apêndice B.7).
5. **Um caminho de fechamento por vez.** Antes de qualquer saída a mercado, o stop e o alvo do robô são cancelados **com confirmação no histórico** (seção 5.1). Nada é reenviado por inferência: resposta sem deal é "não sei", nunca "não executou" (seção 4.6; itens 1.5, 1.6, 1.23, 1.24).
6. **Nada de trava não pedida.** O maestro não adiciona filtro de perda diária, limite de operações, etc. Só existem as proteções técnicas desta especificação (consistência, margem que a corretora recusaria de qualquer forma, cadência de envio, fim de pregão).
7. **Proteção posta pelo dono nunca é apagada pelo robô** (seção 8.7).
8. **Tudo que o EA faz ou decide vira uma linha de log curta, com hora, robô, motivo e números** (seção 11). O que aconteceu com o EA fora do ar também vira linha, com a hora real do deal.

## 1. Arquivos, nomes e versão

| Item | Valor |
|---|---|
| EA | `mt5/WinMaestro.mq5` (+ `.ex5`, `_compile.log`) |
| Módulos | `mt5/WinMaestro/*.mqh`: `Fichas.mqh` (fichas, execução, trânsito, reconciliação), `Recupera.mqh` (máquina de estados da seção 10), `Memoria.mqh` (seção 9), `Log.mqh` (seção 11), `Grade.mqh` (horários da seção 12), um `.mqh` por robô (copiados do WinSeletor e adaptados conforme o Apêndice A) |
| Magic do maestro | `MagicMaestro = 80080900`. Só identifica a instância (pasta de memória, trava de exclusividade). **Nenhuma ordem sai com este magic.** |
| Magics dos robôs | GapBarra1 80080601, CincoMedias 80080501, Desloc 80080101, Retângulo 20261005, Win_c1 80080002 |
| Identificador de instância | `IdInstancia` (2 caracteres, padrão `i1`), vai no comentário de toda ordem (seção 4.2) |
| WinSeletor e EAs avulsos | aposentados (Apêndice B.4): o `.mq5` do Seletor fica como `.bak` no repo; o `.ex5` do Seletor e os `.ex5` avulsos saem da pasta Experts **e** são removidos de todo gráfico aberto antes da primeira partida do maestro (seção 10.1) |
| Grade de horários | `data/b3_grade_horaria_win.csv` copiado para `MQL5/Files/Common/WinMaestro/b3_grade_horaria_win.csv`, com a mesma tabela embutida no código como reserva (seção 12.1) |

## 2. Seleção de robôs e inputs do maestro

Grupo **Maestro**:

| Input | Padrão | Efeito |
|---|---|---|
| `Ativo_GapBarra1` … `Ativo_Win_c1` (5 bools) | todos `true` | Robô ligado gera entradas novas. Desligado: não abre nada novo; **se tiver ficha aberta ou ordem viva, continua gerindo até zerar** (saídas, stop, zeragem). Nunca é fechado por ter sido desligado. |
| `IdInstancia` | `i1` | 2 caracteres; distingue instâncias no comentário (seção 4.2). |
| `MagicMaestro` | 80080900 | Chave da pasta de memória e da trava (seções 9, 10.1). |
| `PastaMemoria` | `WinMaestro` | Subpasta de `MQL5/Files` (seção 9.1). |
| `CapitalConta` | 5000,00 | Capital declarado da conta para o portão de margem (seção 13.1). |
| `PrazoConfirmacaoS` | 5 | Prazo para o histórico confirmar o desfecho de uma ordem (seções 4.6, 5.1). |
| `CorrigirDivergencia` | `true` | Liga a única correção automática existente, a da ficha com sinal trocado por execução dupla (seção 8.3). Com `false`, ela também só bloqueia e alerta. |
| `ContadorDesbloqueio` | 0 | O dono incrementa para liberar um bloqueio que exige ação dele (seções 8.6, 8.7, 8.9). |
| `TetoEntradasMin` | 20 | Máximo de ordens de entrada (papel E) por minuto, somando os 5 robôs (seção 4.8). |
| `DisjuntorEnviosMin` | 100 | Máximo de envios de qualquer papel por minuto antes do disjuntor (seção 4.8). |
| `StopEmergenciaPts` | 1200 | Stop usado só quando a recuperação não consegue saber o stop de um robô posicionado (seção 10.3, caso C). |
| `FusoServidorH` | 0 | Horas a somar ao relógio do servidor para obter Brasília (a verificar, P22). |
| `NotificarPush` | `true` | ALERTA também chama `SendNotification` (seção 11.2). |

Inputs que pertencem a um robô mas são do maestro (ficam no grupo do robô):

| Input | Padrão | Efeito |
|---|---|---|
| `DM_ReservaTicks` | 20 (= 100 pts) | Distância da ordem stop de reserva do DM **além** do nível do stop controlado pelo EA (seção 5.5, Apêndice B.5). |
| `DM_CapitalRobo` | 1000,00 | Base do saldo virtual do DM (seção 13.3). |
| `DM_UsarSaldoDaConta` | `false` | `true` volta ao teto de 10% sobre o saldo da conta (Apêndice B.2). |
| `CM_ReservaPts` | 4.945 (Apêndice B.1) | Distância do stop de reserva do CM. Com B.1 na opção (b), o EA **recusa iniciar** com `Ativo_CincoMedias = true` e `CM_ReservaPts = 0` (item 3.8: parâmetro de segurança não nasce desligado). |

Os demais inputs de cada robô (grupos `WinGapBarra1`, `WinCincoMedias`, …, prefixos `GB_`, `CM_`, `DM_`, `RE_`, `C1_`) ficam como no WinSeletor.

Mudar inputs reinicia o EA (`OnDeinit` → `OnInit`) e passa pela recuperação completa (seção 10). Como as variáveis globais do EA podem sobreviver a `REASON_PARAMETERS` e `REASON_CHARTCHANGE` (a verificar, P17), o `OnInit` reinicializa explicitamente toda variável global do maestro e chama `Reseta()` de cada módulo antes de qualquer outra coisa (seção 7).

Com um robô só ligado, não existe "troca pendente": ligar outro robô não espera ninguém zerar, porque as fichas são independentes.

## 3. A ficha (posição virtual de cada robô)

### 3.1 Como a ficha é calculada

Uma ficha por robô, calculada por **uma única função** (`Ficha_Recalcula`), chamada tanto pelo caminho de evento (`OnTradeTransaction`) quanto pela reconciliação, para que os dois nunca divirjam.

| Campo | Cálculo |
|---|---|
| `volume_deals` (+ compra / − venda) | Σ do volume assinado dos deals `DEAL_TYPE_BUY`/`DEAL_TYPE_SELL` do símbolo com `DEAL_MAGIC` = magic do robô, dentro da janela de reconstrução (3.2), mais os volumes absorvidos de intervenção externa (seção 8.9) |
| `volume_transito` | Σ do volume assinado das ordens do robô em trânsito que alteram a ficha (seção 4.6) |
| **ficha efetiva** | `volume_deals + volume_transito` — é o que os módulos enxergam e o que decide qualquer novo envio |
| `preco_medio` | média ponderada pelo volume dos deals que **afastam** a ficha de zero, desde o último instante em que ela esteve em zero |
| `hora_abertura` | hora do primeiro deal da ficha atual (`DEAL_TIME_MSC`) |
| `resultado_realizado` | Σ, para cada deal que **aproxima** a ficha de zero, de (preço do deal − preço médio) × volume × lado × valor do ponto lido do símbolo, menos `DEAL_COMMISSION` e `DEAL_FEE` dos deals do robô |
| `stop`, `alvo` | níveis pedidos pelo robô: memória (seção 9) + ordens vivas do robô identificadas pela seção 3.3 |
| estado interno do robô | memória (seção 9), conferida pela seção 10 |

Regras:
- **`DEAL_ENTRY` e `DEAL_PROFIT` não são usados na ficha.** Em netting eles descrevem a posição líquida: um deal que abre a ficha do RE pode vir `DEAL_ENTRY_OUT` carregando o lucro do GB. `DEAL_PROFIT` só aparece na conferência do total da conta no resumo do dia (seção 11.5).
- Deals `BALANCE`, `CREDIT`, `CHARGE`, `CORRECTION`, ajustes e variação de margem (`DEAL_REASON_VMARGIN`) não entram no volume; cada um é logado uma vez (`AJUSTE`).
- Estados válidos de uma ficha: `0` ou `±Lote` do robô (todos operam 1 lote por vez; nenhum piramida). Valor intermediário durante preenchimento parcial é válido enquanto houver entrada viva do robô (seção 6.2). Qualquer outro valor é divergência de ficha (seção 8.2).
- Ficha cujo deal de abertura é anterior ao início do pregão de hoje é **ficha de pregão anterior** (seção 10.3, passo R11).

### 3.2 Janela de reconstrução

O histórico é lido desde o **último instante em que a posição líquida do símbolo foi zero**:
1. Começa no início do pregão de hoje (`negociacao_inicio` da grade − 10 min).
2. Calcula `S = Σ volume assinado de todos os deals BUY/SELL do símbolo, de todos os magics, desde o início da janela`.
3. Se `S` ≠ posição líquida real (`PositionSelect`), recua um pregão e repete, até 10 pregões.
4. A janela vale quando `S` = líquida **e** a líquida acumulada estava em zero no instante de início da janela.
5. Sem fechar em 10 pregões: a recuperação não sai de `AGUARDA_HISTORICO` (seção 10.2), log ALERTA a cada 5 min.

A mesma conta (`Σ deals da janela = líquida real`) é a **verificação cruzada** usada pela seção 8.2 para distinguir "ficha errada" de "histórico ainda incompleto". A API não tem indicador de "histórico carregado"; esta conta é o indicador.

Resultado acumulado de longo prazo (saldo virtual, seção 13.3) e `seq` não dependem desta janela: vêm do estado permanente (seção 9.1) e, se ele se perder, do histórico completo (seção 9.5).

### 3.3 Papel das ordens e invariantes por robô

O papel de uma ordem pendente é identificado por **(magic, tipo, lado em relação à ficha efetiva)**. O comentário (seção 4.2) é conferência, não fonte, porque a corretora pode trocá-lo ou truncá-lo (a verificar, P3).

| Ordem viva do magic do robô | Ficha do robô | Papel |
|---|---|---|
| stop (`BUY_STOP`/`SELL_STOP`, ou `*_STOP_LIMIT`) do lado oposto à ficha | ≠ 0 | S (stop) |
| limite do lado oposto à ficha | ≠ 0 | A (alvo) ou X-limite (saída agressiva, seção 5.4); os dois contam juntos como "saídas limite" |
| limite de qualquer lado | 0 | E (entrada) |
| limite do mesmo lado da ficha | ≠ 0 | E fora de lugar (robôs não piramidam) |
| stop de qualquer lado | 0 | S sem ficha |

Invariantes conferidos a cada reconciliação (seção 8.1), por robô:
1. No máximo **uma** ordem S, com volume = |ficha| e lado oposto.
2. Σ volume das saídas limite (A e X-limite) ≤ |ficha|.
3. Nenhuma S, A ou X-limite com ficha 0.
4. Nenhuma E com ficha ≠ 0; no máximo uma E com ficha 0.

Violação: cancela o excedente pelo protocolo 5.1 (a ordem mais nova primeiro; a S de nível mais protetor é a que fica) e loga ALERTA `INVARIANTE`. A ação só é tomada depois de passar pelas condições da seção 8.5 (ordem fora do trânsito, com mais de 5 s de vida, e verificação cruzada da janela fechando). Tickets guardados na memória são pista para achar a ordem, não fonte do papel: se o `OrderModify` trocar o ticket (a verificar, P4), a ordem continua sendo reconhecida pelo papel.

### 3.4 O que os módulos passam a usar (camada de fichas)

Os módulos deixam de tocar em `PositionSelect/PositionGet*/trade.Position*/OrdersTotal/OrderSelect/HistorySelect*`. Cada chamada vira uma função da camada, que devolve os dados explicitamente (os módulos não dependem mais do "item selecionado" global):

| Hoje no módulo | No maestro |
|---|---|
| `PositionSelect(_Symbol)` + magic == meu | `Ficha_Tem(robo)` (ficha efetiva ≠ 0) |
| `PositionSelect(_Symbol)` → "tem posição de outro robô, não entro" | **removido** |
| `POSITION_PRICE_OPEN / TYPE / TIME / VOLUME` | `Ficha_Preco`, `Ficha_Lado`, `Ficha_Hora`, `Ficha_Volume` |
| `POSITION_SL / POSITION_TP` | `Ficha_Stop`, `Ficha_Alvo` |
| `POSITION_COMMENT`, `HistorySelectByPosition` (flag "a favor" do CM) | `Ficha_Marca(robo)` (seção 4.2) |
| `trade.PositionClose(_Symbol)` ou `(ticket)` | `Ficha_Fecha(robo, motivo)` — protocolo 5.2, volume da ficha, magic do robô. **Nunca** fecha a posição líquida inteira |
| `trade.PositionModify(sl, tp)` | `Ficha_DefineStop(robo, nivel, motivo)` (seção 4.7) / `Ficha_DefineAlvo(robo, nivel, motivo)` |
| `trade.Buy/Sell(lote, …, sl, …)` | `Ficha_EntraMercado(robo, lado, lote, stop, motivo)` (seção 4.3: stop enviado no mesmo fluxo) |
| `trade.BuyLimit/SellLimit` de entrada | `Ficha_EntraLimite(robo, lado, lote, preco, stop, alvo, validade, expira, motivo)` |
| `trade.BuyLimit/SellLimit` de alvo, `OrderModify` do alvo | `Ficha_DefineAlvo` |
| `OrderDelete` das próprias ordens | `Ficha_CancelaOrdem(robo, papel, motivo)` (protocolo 5.1) |
| `OrdemPendente()` / `OrderSelect(g_ordem)` | `Ficha_Entrada(robo)` → {existe, lado, preço, hora de envio, ticket} |

Toda função de envio devolve um de quatro resultados ao módulo: `ENVIADA` (em trânsito), `RECUSADA` (com motivo e retcode), `BLOQUEADA` (portão do maestro, com motivo) ou `JA_EM_TRANSITO`. O módulo trata `RECUSADA` e `BLOQUEADA` como hoje trata falha de `OrderSend` (item 4.33: a estratégia tem de saber que a ordem não saiu).

## 4. Execução

### 4.1 Tipos de ordem, validade e preenchimento

| Situação | Ordem real | Validade |
|---|---|---|
| Entrada a mercado (só C1) | mercado, magic do robô | — |
| Entrada limite | limite, magic do robô | a do robô: GB `SPECIFIED` (abertura + `TtlBarras`×5 min, fallback DAY com cancelamento pelo EA em `g_exp`); CM, DM, RE `DAY` (o RE era GTC, Apêndice B.3) |
| Stop do robô (papel S) | `SELL_STOP` para ficha comprada, `BUY_STOP` para vendida, volume = |ficha|, magic do robô | **GTC** (Apêndice B.6). Se o símbolo não aceitar GTC (`SYMBOL_EXPIRATION_MODE`, P1/P15): `SPECIFIED` até o fim do contínuo do pregão seguinte, renovada todo dia no passo R10 da recuperação |
| Alvo do robô (papel A) | limite oposta, volume = |ficha|, magic do robô | DAY (Apêndice B.3) |
| Saída por regra, zeragem, rede de segurança | mercado oposta, volume = |ficha|, magic do robô, depois do protocolo 5.2 | — |
| Saída agressiva (stop disparado sem execução, saída recusada em leilão ou banda) | limite oposta agressiva (seção 5.4) | DAY |
| Correção de ficha com sinal trocado (papel C) | mercado, magic do robô dono da ficha, depois do protocolo 5.2 | — |

Preenchimento: limite com `ORDER_FILLING_RETURN` e desvio 0. Ordem a mercado: `ORDER_FILLING_RETURN` se `SYMBOL_FILLING_MODE` e a corretora aceitarem; senão `ORDER_FILLING_IOC` (a verificar, P15). No `OnInit` o EA lê e loga `SYMBOL_FILLING_MODE`, `SYMBOL_EXPIRATION_MODE`, `SYMBOL_TRADE_MODE`, `SYMBOL_TRADE_STOPS_LEVEL`, `SYMBOL_VOLUME_LIMIT` e `ACCOUNT_LIMIT_ORDERS`, e **recusa iniciar** se faltar DAY, ou se faltarem ao mesmo tempo GTC e `SPECIFIED` (os stops precisam de um dos dois). Sem `SPECIFIED`, o GB usa o fallback DAY com cancelamento pelo EA e o log registra AVISO. `ACCOUNT_LIMIT_ORDERS` entre 1 e 14 gera AVISO (o maestro pode ter até 15 pendentes: 5 robôs × E/S/A).

### 4.2 Comentário padronizado

`MAE|<inst>|<robo>|<papel>|<seq>[|<marca>]`

- `inst` = `IdInstancia`; `robo` = GB, CM, DM, RE, C1; `papel` = E, S, A, X (saída: mercado ou limite agressiva), C (correção).
- `seq` = 5 dígitos, contador **por ordem** e por robô, persistido no estado permanente (seção 9.1). Cada envio tem `seq` próprio, então o comentário identifica uma ordem única mesmo depois de reinício (é a chave de busca da seção 4.6).
- `marca` = 1 caractere opcional do robô (CM: `F` a favor do mês, `N` neutra). Exemplo: `MAE|i1|CM|E|00042|F` = 19 caracteres.
- O limite de 31 caracteres não está garantido pela MT5 nem pela corretora (a verificar, P3). O formato cabe em 19.
- Ordem ou deal com magic de robô cujo comentário de origem (o da ordem que gerou o deal, via `DEAL_ORDER`) não comece por `MAE|<inst>|` é tratado pela seção 10.1 (outra instância ou EA avulso). Enquanto P3 não estiver respondida, essa regra vale como está; se a resposta for "a corretora troca o comentário", ela passa a usar só o registro de envios da seção 4.6 (toda ordem com magic de robô que não está no registro de envios é estranha).

### 4.3 Stop no servidor

Em NETTING a posição tem **um** SL/TP só, que não serve para 5 robôs. Por isso o maestro **não usa** o SL/TP da posição líquida. Cada robô posicionado tem a sua ordem stop pendente (papel S).

- **Quando nasce.** Entrada limite: no instante em que o deal de entrada do robô é visto (`OnTradeTransaction` ou reconciliação), na mesma chamada. Entrada a mercado (C1): na mesma execução de `Ficha_EntraMercado`, logo depois do retorno do `OrderSend` que traz `deal ≠ 0`, sem esperar `OnTradeTransaction`; se o retorno vier sem deal, a S nasce quando a seção 4.6 confirmar o deal. O intervalo medido entre o deal e a S aceita é logado em toda abertura (`STOP … atraso 180 ms`).
- **Robôs com stop no servidor** (GB, RE, C1, e o CM depois que o "stop que aperta" nasce): a S fica no nível pedido pelo robô.
- **DM (stop controlado pelo EA):** o EA continua fechando a mercado quando o último negócio cruza `g_stopNivel` (fiel ao testado), e a S é uma **reserva** a `DM_ReservaTicks` além do nível (seção 5.5).
- **CM antes do "stop que aperta":** S de reserva a `CM_ReservaPts` do preço da ficha (Apêndice B.1). Quando o "stop que aperta" nasce, a mesma S é movida para o nível dele (seção 4.7); nunca existem duas.
- **Validade GTC** (Apêndice B.6): uma ficha que atravessa a noite por falha do EA no fim do dia continua com stop durante a noite e na abertura. O risco oposto (S de ficha já zerada sobreviver) é tratado por duas regras: o passo R8 da recuperação cancela toda S sem ficha **antes** de qualquer outra ação, e a reconciliação cancela S sem ficha a cada ciclo (seção 8.5).
- **Fallback stop-limit:** se a Rico não aceitar `SELL_STOP/BUY_STOP` no WIN (P1), usar `*_STOP_LIMIT` com limite a 10 ticks além do gatilho, e a detecção de stop-limit atravessado da seção 5.4 passa a ser obrigatória.
- **Onde a S mora** (servidor da Rico ou stop nativo na B3) e o que ela vira ao disparar em leilão, túnel ou banda: a verificar (P1, P13). A seção 5.4 trata o caso "disparou e não executou".

### 4.4 Atribuição dos negócios

Todo deal do símbolo é atribuído pelo `DEAL_MAGIC`:
- magic de um robô, ordem de origem com comentário `MAE|<inst>|` → ficha desse robô;
- magic de um robô com comentário de origem diferente → seção 10.1 (estranho: bloqueio total);
- qualquer outro magic (0 = manual, outros EAs), ou `DEAL_REASON` em {`CLIENT`, `MOBILE`, `WEB`, `SO`} sem magic de robô → **deal externo**, tratado pela seção 8.9 (redutor ou aumentador).

Não existe ficha "sem dono": toda ordem enviada pelo maestro carrega o magic de um robô (`trade.SetExpertMagicNumber` antes de cada envio).

### 4.5 Ordem de processamento num mesmo instante

Quando vários robôs agem no mesmo ciclo: primeiro todos os **cancelamentos e saídas**, na ordem fixa GB, CM, DM, RE, C1; depois as **entradas**, na mesma ordem. Os envios são seriais: o próximo só sai depois do retorno do `OrderSend` anterior.

Diferença conhecida em relação aos EAs avulsos: em hora cheia várias velas fecham juntas (M5, M15, H1, H2) e a última entrada da fila sai alguns centésimos de segundo depois da primeira; a ordem fixa dá prioridade de fila sistemática ao GB. Isso entra no relatório de equivalência (seção 15.1) como diferença esperada.

### 4.6 Ordens em trânsito

Toda ordem enviada pelo maestro entra no **registro de ordens em trânsito** antes do `OrderSend`:

| Campo | Conteúdo |
|---|---|
| robô, papel, `seq`, comentário | identificação |
| volume assinado que altera a ficha | E e X/C: o volume da ordem; S e A: 0 enquanto não executam |
| ticket da ordem, `request_id` | preenchidos no retorno do `OrderSend` (podem ficar 0) |
| hora de envio (`TimeTradeServer`, ms) | prazo |
| estado | `ENVIADA`, `VIVA` (pendente no livro), `DESCONHECIDA` |

Regras:
1. O registro é gravado na memória (seção 9.4) **antes** do `OrderSend`. Uma queda entre a gravação e o envio deixa uma entrada sem ticket, resolvida pelo passo R6 da recuperação (busca pelo comentário; sem nada em 10 s, a entrada é descartada e logada `NAO_ENVIADA`).
2. **Ficha efetiva = ficha pelos deals + volume em trânsito** (seção 3.1). É ela que os módulos e o portão de margem enxergam.
3. Enquanto um robô tiver ordem em trânsito de um papel, o maestro **não envia outra ordem desse papel** para esse robô (retorno `JA_EM_TRANSITO`). Saída (X), correção (C) e entrada a mercado com trânsito aberto bloqueiam qualquer nova X, C ou E do mesmo robô.
4. Uma ordem sai do trânsito só quando o histórico confirma o desfecho: deal(s) com `DEAL_ORDER` = ticket somando o volume da ordem, ou a ordem no histórico com estado final (`FILLED`, `CANCELED`, `REJECTED`, `EXPIRED`), ou a ordem listada como pendente (`VIVA`, para E/S/A).
5. **`TRADE_RETCODE_DONE`/`PLACED` sem deal é "não sei"**, nunca "não executou" (itens 1.6, 1.17, 1.24). `OrderSend` que devolve `false` ou retcode de erro de transporte (`TIMEOUT`, `CONNECTION`, `ERROR`) também é "não sei" se o ticket veio 0: a ordem é procurada pelo comentário nas ordens vivas e no histórico.
6. A consulta tem prazo: a cada 250 ms durante `PrazoConfirmacaoS` (5 s). Esgotado o prazo, a ordem vira `DESCONHECIDA`: ALERTA, o robô fica sem novas ordens de qualquer papel exceto cancelamentos, e a consulta continua a cada 5 s por 2 min e depois a cada 30 s, até o desfecho aparecer. **Nada é reenviado por inferência.**
7. Ao resolver uma `DESCONHECIDA`, o log registra quanto tempo ela ficou sem desfecho (`TRANSITO resolvida em 47 s: FILLED @176850`).

### 4.7 Mover o stop

1. Mover é sempre `OrderModify` da S existente; **nunca** cancelar e recriar (abre janela sem stop).
2. Antes de enviar, o nível novo é conferido contra o último negócio: para S de venda, nível ≤ último − max(1 tick, `SYMBOL_TRADE_STOPS_LEVEL`); para S de compra, nível ≥ último + o mesmo piso (item 1.25 regra 3, item 4.30).
3. Nível novo já atravessado pelo preço: a saída a mercado segue o protocolo 5.2 (cancela a S antiga com confirmação, depois sai). O `OrderModify` recusado deixa a S antiga viva, e é por isso que ela é cancelada antes.
4. O stop nunca afrouxa contra o nível registrado (compra: nível novo ≥ atual; venda: ≤ atual), salvo regra explícita do robô. Nível vazio ou zero vindo de um módulo é ignorado com ERRO, nunca apaga a S (item 1.10).
5. Se o `OrderModify` trocar o ticket da ordem (a verificar, P4), a seção 3.3 reconhece a S nova pelo papel; o ticket na memória é atualizado.

### 4.8 Retentativas e teto de envios

- **Espera crescente.** Ordem recusada entra em espera de 1 s, 2 s, 4 s, 8 s, 16 s e depois 30 s fixos entre tentativas da mesma operação (mesmo robô, mesmo papel).
- **Escalada.** Após 5 recusas seguidas da mesma operação: ALERTA com push. Entradas (E) só voltam a ser tentadas na próxima vela do robô (nova condição). S, X, C e cancelamentos continuam na cadência de 30 s, com ALERTA repetido a cada 5 min enquanto a recusa durar (item 1.13).
- **Teto de entradas.** No máximo `TetoEntradasMin` (20) ordens E por minuto, somando os 5 robôs; a excedente é recusada com `BLOQUEIO cadencia` (item 1.20).
- **Disjuntor.** Mais de `DisjuntorEnviosMin` (100) envios de qualquer papel num minuto: bloqueia E e A por 5 min, ALERTA com push (item 1.22: dois níveis).
- **Saídas, stops, correções e cancelamentos nunca são barrados pelo teto nem pelo disjuntor** (item 1.22). Eles contam no contador, para o disjuntor enxergar um laço.

### 4.9 Autonegociação

1. **Entradas (E) e alvos (A)** que possam cruzar com ordem própria viva do lado oposto (compra a preço ≥ venda própria viva, venda a preço ≤ compra própria viva) **não são enviados**: `BLOQUEIO autonegociacao`, reavaliados com a espera de 4.8.
2. **Saídas, stops, zeragens e correções nunca são bloqueados pela autonegociação** (item 1.22). Quando uma saída a mercado de um robô puder cruzar com uma limite própria do lado oposto (compra a mercado com venda própria ≤ melhor oferta; venda a mercado com compra própria ≥ melhor demanda), o maestro **cancela primeiro a limite do outro robô** (protocolo 5.1), envia a saída e depois devolve ao outro robô o aviso `CANCELADA_AUTONEG`; o outro robô rearma pela regra dele se ainda estiver na janela (log `AUTONEG cancelou E de RE para saida de CM`). A perda de fila entra no relatório de equivalência (seção 15.1).
3. **Stop disparado no servidor** não fica no livro e não pode ser prevenido. Detecção: deal de compra e deal de venda próprios no mesmo preço e no mesmo segundo → ALERTA `AUTONEG`.
4. **S ou A cancelada ou recusada sem pedido do maestro** (visto em `OnTradeTransaction` ou na reconciliação) é evento crítico: se a ficha está posicionada, a S é recriada na hora; se o preço já passou do nível, a saída segue a seção 5.4.
5. A existência e o lado de Self-Trade Prevention na Rico/B3 são a verificar (P12).

## 5. Stop e alvo do mesmo robô: protocolo de cancelamento confirmado e OCO

### 5.1 Protocolo de cancelamento confirmado

**Cancelamento confirmado** = a ordem aparece no **histórico** com `ORDER_STATE_CANCELED` ou `ORDER_STATE_EXPIRED`. O retcode do `OrderDelete` não basta: em ordem de bolsa o cancelamento é assíncrono (`ORDER_STATE_REQUEST_CANCEL`) e o desfecho pode ser FILLED (item 1.5).

1. Envia `OrderDelete`; registra o cancelamento no trânsito (seção 4.6).
2. Consulta o histórico a cada 250 ms por até `PrazoConfirmacaoS` (5 s).
3. Desfechos:
   - `CANCELED`/`EXPIRED` → confirmado.
   - `FILLED` ou `PARTIAL` → **a ordem executou**. A ficha é recalculada; quem pediu o cancelamento é avisado com `EXECUTOU_ANTES`.
   - prazo esgotado sem desfecho → "não sei": a ordem continua tratada como viva para o invariante e para a margem; o robô fica em `SAIDA_PENDENTE` (seção 6) e a reconciliação decide.
4. O tempo até a confirmação é logado (P5 mede a distribuição real).

### 5.2 Saída a mercado

Vale para toda saída a mercado: saída por regra do robô, stop do EA do DM, "stop atravessado" (4.7), zeragem, rede de segurança (12.3), pregão anterior e horário perdido (10.3) e correção (8.3).

1. Cancela S e A (e X-limite, se houver) do robô pelo protocolo 5.1, em paralelo.
2. Todos confirmados `CANCELED` → envia a ordem a mercado com volume = |ficha efetiva| e lado oposto.
3. Algum desfecho `FILLED` → **não envia** a saída: a ficha já foi alterada pela ordem que executou. Recalcula; se a ficha ainda for ≠ 0 (execução parcial), recomeça do passo 1 com o volume restante.
4. Algum desfecho "não sei" → **não envia** a saída; robô em `SAIDA_PENDENTE`; a reconciliação repete o passo 1 a cada 5 s até haver desfecho. ALERTA após 30 s.
5. Saída recusada por leilão, túnel ou banda (retcode logado): segue a seção 5.4.

Consequência aceita: a saída por regra sai entre 0,2 s e 5 s depois da decisão, conforme a corretora confirmar o cancelamento. Esse atraso é medido (log) e entra no relatório de equivalência.

### 5.3 OCO (stop e alvo do mesmo robô)

Stop e alvo são duas ordens independentes na corretora; quando uma executa, a outra precisa morrer.

1. Deal de S ou A visto com a ficha indo a zero → cancela as ordens restantes do robô (S, A, X-limite, E) pelo protocolo 5.1, **antes** de qualquer outra ação do ciclo.
2. **Com o EA fora do ar não existe OCO.** Uma ficha com S e A vivos pode ter as duas executadas (ficha com sinal trocado, sem stop) ou, se só uma executar, a outra fica viva e pode abrir posição nova sem stop. É a exceção (b) do Princípio 4, entra no pior caso da seção 13.4 e é decisão consciente do dono para o RE (Apêndice B.9). Robô sem alvo (GB no padrão, CM, DM, C1) não tem esse risco.
3. Na recuperação, as ordens irmãs são canceladas no passo R8, antes de qualquer outra ação, e a ficha com sinal trocado é tratada no passo R11 pela seção 8.3.

### 5.4 Stop disparado sem execução e saída recusada

**Detecção** (a cada reconciliação):
- ordem S que sai da lista de pendentes sem deal com `DEAL_ORDER` = ticket em 2 s, e cujo estado no histórico é `REJECTED` ou `CANCELED` sem pedido do maestro; ou
- S do tipo stop-limit ativada (virou limite) cujo preço limite foi atravessado pelo último negócio há mais de 3 s; ou
- saída a mercado (X ou C) recusada pela corretora.

**Ação:** ALERTA `STOP SEM EXECUCAO` com push e saída por **limite agressiva**: preço = último ∓ 3 ticks (15 pts) no sentido de garantir o preenchimento, limitado à banda do símbolo; reenviada a cada 5 s fora de leilão (cancelamento pelo protocolo 5.1 antes de cada reenvio), no máximo 6 tentativas por minuto; ALERTA repetido a cada 3 min sem preenchimento. Durante leilão (fase lida da grade da data: pré-abertura e call de fechamento; leilão por variação detectado pela recusa com retcode de mercado fechado ou fase), a ordem fica como limite no preço da proteção para participar do leilão, se a B3 aceitar (a verificar, P13). Nunca em laço: as tentativas contam no disjuntor (4.8).

### 5.5 DM: stop do EA e reserva no servidor

O DM tem dois mecanismos para o mesmo stop, e eles não podem estar no mesmo nível (itens 1.4, 1.23): com a reserva no nível exato do stop do EA, a reserva dispararia no mesmo instante em que o EA manda a saída, e as duas vendas somariam.

- **Stop do EA** (fiel ao testado): quando o último negócio cruza `g_stopNivel`, o EA executa a saída pelo protocolo 5.2 (cancela a reserva com confirmação, depois sai a mercado).
- **Reserva no servidor**: S a `DM_ReservaTicks` (20 ticks = 100 pts) **além** de `g_stopNivel`. Só dispara se o EA não agiu (fora do ar, desconectado, travado) ou se o preço saltou mais de 100 pts num único negócio.
- **No Testador a reserva também existe**, para o teste exercitar o caminho real. Efeito esperado na equivalência: o Testador processa as pendentes antes do `OnTick` de cada tick; a reserva só executa num tick que atravessa `g_stopNivel` e a reserva de uma vez (salto ≥ 100 pts). Nesse tick o EA avulso sairia a mercado no preço do mesmo tick, então o preço de saída é o mesmo e muda só o caminho (deal de papel S em vez de X). O relatório 15.1 lista esses trades um a um; qualquer diferença de preço neles é defeito.
- Custo da reserva quando o EA está fora: até 20 ticks = R$20 por contrato além do stop testado.

## 6. Ciclo de vida de uma operação de um robô

### 6.1 Estados

| Estado | Significado |
|---|---|
| `LIVRE` | ficha 0, nenhuma ordem viva |
| `ENTRADA_ENVIANDO` | E em trânsito, sem desfecho |
| `ENTRADA_PENDENTE` | E viva no livro |
| `POSICIONADO_SEM_STOP` | deal de entrada visto, S ainda não aceita (janela do Princípio 4a) |
| `POSICIONADO` | ficha ≠ 0 com S aceita |
| `SAINDO` | protocolo 5.2 em curso |
| `SAIDA_PENDENTE` | cancelamento ou saída sem desfecho no prazo |
| `TRANSITO_DESCONHECIDO` | alguma ordem do robô em `DESCONHECIDA` (seção 4.6) |

### 6.2 Transições

```
LIVRE --(sinal, robô ativo, sem bloqueio, margem ok)--> ENTRADA_ENVIANDO
ENTRADA_ENVIANDO --(ordem limite aceita no livro)--> ENTRADA_PENDENTE
ENTRADA_ENVIANDO --(deal: entrada a mercado)--> POSICIONADO_SEM_STOP
ENTRADA_ENVIANDO --(recusada / cancelada)--> LIVRE
ENTRADA_ENVIANDO --(prazo 5 s sem desfecho)--> TRANSITO_DESCONHECIDO
ENTRADA_PENDENTE --(deal com DEAL_ORDER = ticket)--> POSICIONADO_SEM_STOP
ENTRADA_PENDENTE --(validade / cancelamento confirmado)--> LIVRE
POSICIONADO_SEM_STOP --(S aceita)--> POSICIONADO
POSICIONADO --(deal de S ou A zera a ficha)--> LIVRE (cancela as irmãs, 5.3)
POSICIONADO --(saída por regra / zeragem / correção)--> SAINDO
SAINDO --(deal da saída zera a ficha)--> LIVRE
SAINDO --(cancelamento ou saída sem desfecho)--> SAIDA_PENDENTE
SAIDA_PENDENTE --(desfecho visto)--> LIVRE ou SAINDO (volume restante)
TRANSITO_DESCONHECIDO --(desfecho visto)--> estado correspondente ao desfecho
```

Cada transição grava a memória na hora (seção 9.3) e gera uma linha de log (seção 11).

`POSICIONADO_SEM_STOP` com mais de 2 s de duração gera ALERTA; a S é reenviada pela regra de espera de 4.8.

### 6.3 Preenchimento parcial

Com `Lote` > 1 uma entrada limite pode encher em partes:
- A S nasce com o volume preenchido e é ajustada (`OrderModify` de volume, ou cancelamento confirmado e recriação se a corretora não aceitar modificar volume — a verificar, P4) a cada novo preenchimento.
- Se o resto encher depois de a S ter sido movida pelo robô, a S ajustada mantém o **nível atual** (nunca volta ao inicial) e passa a ter o volume total.
- O alvo segue a mesma regra de volume.
- Ao vencer a validade, o resto é cancelado (protocolo 5.1) e a ficha segue com o parcial.
- Com WIN e 1 contrato isso não acontece; o código não pode quebrar se acontecer.

## 7. Eventos do MT5

| Evento | O que faz |
|---|---|
| `OnInit` | Reinicializa explicitamente toda variável global do maestro, chama `Reseta()` de cada módulo, liga `EventSetMillisecondTimer(250)`, coloca a recuperação no estado `R0_CONFIGURADO` e devolve `INIT_SUCCEEDED`. **Não espera conexão, não lê histórico, não envia ordem.** Única recusa no `OnInit`: inputs inválidos (ex.: `IdInstancia` com tamanho ≠ 2, `CM_ReservaPts = 0` com o CM ligado). |
| `OnTimer` (250 ms) | Avança a máquina de estados da recuperação (seção 10.2); consultas de trânsito e de cancelamento (4.6, 5.1); a cada 1 s: reconciliação (seção 8), cortes de horário pelo relógio de parede (seção 12), heartbeat da trava (10.1), gravação de mudanças acumuladas (9.3); a cada 60 s: varredura de outros símbolos (8.8). |
| `OnTick` | Marca a reconciliação como "suja"; se a recuperação está em `PRONTO`, roda o `Tick()` de cada robô ligado ou com ficha/ordem viva, na ordem 4.5. Antes de `PRONTO`, o `Tick()` dos robôs não roda. |
| `OnTradeTransaction` | Grava uma linha bruta (seção 11.1) de cada transação do símbolo; deal novo → recalcula a ficha do magic (mesma função da reconciliação), trata OCO (5.3), atualiza o trânsito, grava a memória; ordem cancelada ou rejeitada → atualiza o trânsito e avisa o módulo. É o caminho rápido; não é garantido (pode perder evento em reconexão), e a reconciliação é o caminho seguro. |
| `OnDeinit` | Loga `FIM` com o `reason`. Se `reason` ∉ {`REASON_PARAMETERS`, `REASON_CHARTCHANGE`, `REASON_TEMPLATE`} (remoção, fechamento do terminal, gráfico fechado, troca de conta, recompilação, falha de init), **envia o cancelamento de todas as entradas pendentes (papel E)** dos 5 robôs e loga cada retcode; não espera confirmação (o terminal dá poucos segundos ao `OnDeinit`); a recuperação seguinte confere. **Nunca cancela S nem A, nunca fecha posição.** Grava a memória, libera a trava (10.1), `EventKillTimer`. |

O cancelamento das entradas no `OnDeinit` não cobre queda de energia, travamento ou processo morto (sem `OnDeinit`) nem a internet caída; esses casos ficam na exceção (a) do Princípio 4. Se o cancelamento enviado no `OnDeinit` chega ao servidor quando o terminal está fechando é a verificar (P24).

## 8. Reconciliação contínua

### 8.1 Cadência e custo

- `OnTick`, `OnTradeTransaction` e o timer marcam a reconciliação como "suja". O recálculo roda no máximo 1 vez por segundo, mais um recálculo imediato quando chega um deal.
- Incremental: `HistorySelect(último instante processado − 60 s, agora)`, deduplicando por ticket de deal (cada ticket processado uma vez só; o último ticket e o último instante ficam na memória). A janela completa (3.2) é relida na recuperação e uma vez a cada 10 min.
- Nenhum módulo chama `HistorySelect*` (o pool de histórico é global ao EA).

A cada reconciliação:
1. Lê a posição líquida real do símbolo. `PositionSelect` falso pode ser "sem posição" ou erro: distingue pelo `GetLastError` e, em erro, a leitura é descartada (item 1.6).
2. Recalcula as fichas (3.1) e o trânsito (4.6).
3. Compara `líquida real` com `Σ fichas efetivas + externa`.
4. Confere as ordens vivas contra os invariantes de 3.3.
5. Confere `ACCOUNT_MARGIN_FREE` contra o cálculo de 13.1 (diagnóstico).

### 8.2 Confirmação de divergência

Uma diferença só é **divergência confirmada** quando, ao mesmo tempo:
1. persiste por ≥ 3 s **e** em ≥ 3 leituras com `HistorySelect` refeito;
2. não há ordem em trânsito que a explique **em quantidade e lado** (diferença de lado nunca é explicada por trânsito; item 1.25 regra 2);
3. a verificação cruzada da janela (3.2: `Σ deals de todos os magics desde o último zero = líquida real`) **fecha**. Se ela não fecha, o problema é histórico incompleto, não ficha errada: **espera, não corrige** e loga `HISTORICO incompleto` uma vez.

Divergência confirmada → bloqueio (8.6) e ALERTA. Ação de correção só para a causa conhecida da seção 8.3; qualquer outra divergência fica bloqueada até o dono (item 1.7: não fechar às cegas uma exposição cuja origem ninguém entendeu).

### 8.3 Ficha com sinal trocado por execução dupla (única correção automática)

Causa: os deals do robô mostram **duas saídas da mesma ficha** (S + A, S + X, A + X, ou X duplicada), levando a ficha de ±Lote a ∓Lote. Ação, se `CorrigirDivergencia = true`:
1. Protocolo 5.2 com o **magic do robô dono da ficha** e papel C: cancela o que restar do robô, confirma, envia a ordem a mercado que leva a ficha a 0.
2. No máximo **uma** correção por ficha a cada 10 min. Uma segunda execução dupla na mesma ficha dentro desse prazo bloqueia o robô e exige o dono (`ContadorDesbloqueio`; item 1.13).
3. Log ALERTA com os tickets dos dois deals de saída e o resultado da correção.

Correção nunca usa `MagicMaestro`; a ficha fecha pelos próprios deals do robô.

### 8.4 Ficha posicionada sem stop no servidor

Ficha ≠ 0 há mais de 2 s sem S viva e sem S em trânsito:
1. Recria a S no nível da memória.
2. Sem nível na memória: recalcula pela regra do robô (Apêndice A).
3. Sem regra possível: `StopEmergenciaPts` do preço da ficha, ALERTA.
4. Nível já atravessado: seção 4.7 item 3.
Recusas seguem 4.8 (cadência de 30 s, nunca a cada tick).

### 8.5 Ordem órfã

Uma ordem com magic de robô só é tratada como órfã (sem papel válido pela 3.3, ou S/A/X-limite sem ficha) se, ao mesmo tempo: não está no registro de trânsito; tem mais de 5 s de vida (`ORDER_TIME_SETUP_MSC`); e a verificação cruzada da janela fecha. Ação: cancela pelo protocolo 5.1 e loga `ORFA`. Ordem pendente de magic desconhecido: não toca, loga uma vez (`EXTERNA ordem`).

### 8.6 Bloqueio

Causas: divergência confirmada (8.2), intervenção externa redutora (8.9), SL/TP na posição líquida (8.7), ordem estranha (10.1), ordem/posição em outro símbolo (8.8), segunda execução dupla (8.3).

Ao **entrar** em bloqueio:
1. Nenhum robô envia E.
2. **Todas as entradas pendentes (papel E) dos 5 robôs são canceladas** (protocolo 5.1), porque uma entrada colocada antes do bloqueio pode encher com o estado indefinido (item 1.9).
3. Saídas, stops, zeragens e cancelamentos continuam funcionando.
4. Log ALERTA uma vez, com a causa.

Ao **sair** do bloqueio (causa resolvida, ou `ContadorDesbloqueio` incrementado quando a causa exige o dono): log uma vez; cada robô rearma pela regra dele se ainda estiver na janela, com a regra de decisão atrasada da seção 10.4.

Bloqueios que exigem o dono: 8.3 item 2, 8.7, 8.8, 8.9, 10.1. Os demais saem sozinhos quando a condição some.

### 8.7 SL/TP na posição líquida

O maestro nunca põe SL/TP na posição líquida. Se encontrar SL ou TP nela, foi o dono (ou outra ferramenta):
- **não remove** (é a proteção de emergência do dono; foi um stop anexado à mão que encerrou o incidente de 2026-08-28, Parte 0);
- entra em bloqueio, ALERTA com push, e espera o dono;
- se esse SL/TP executar, o deal é intervenção externa redutora (8.9).

### 8.8 Ordens e posições fora do símbolo do gráfico

No `OnInit` (passo R2) e a cada 60 s: varre posições e ordens de **todos** os símbolos com magic de robô. Encontrou fora do símbolo do gráfico (ex.: contrato velho depois da rolagem): ALERTA e bloqueio de entradas até o dono resolver. O maestro não mexe no outro símbolo.

### 8.9 Intervenção externa

Deal externo (4.4) é classificado no instante em que é visto:

**Redutor** (diminui |líquida|): zeragem manual do dono, mesa da corretora, zeragem compulsória de day trade da Rico (a verificar, P11), stop-out (`DEAL_REASON_SO`), SL/TP do dono (8.7).
1. **Bloqueio** de entradas (8.6) — exige o dono.
2. **Absorção nas fichas do lado reduzido**, na ordem fixa GB, CM, DM, RE, C1 (Apêndice B.8): o volume externo é atribuído ficha a ficha até se esgotar; cada ficha absorvida vai a 0 com o preço do deal externo e é logada `FECHADA POR INTERVENCAO EXTERNA`. A absorção é função determinística do histórico (mesmos deals → mesma atribuição), então a recuperação sem memória chega ao mesmo resultado.
3. **Cancelamento imediato** das ordens que agora aumentariam a exposição: S, A e X-limite das fichas absorvidas, e todas as E. Cancelamento pelo protocolo 5.1, nesta ordem de prioridade: S e A das fichas absorvidas primeiro (são as que viram entradas nuas: um SELL_STOP de uma ficha comprada que já foi zerada abre um vendido).
4. ALERTA com push.
5. Deal externo que inverte a líquida (reduz até zero e passa do outro lado) é dividido: a parte que vai a zero é redutora; o excedente é aumentador.

**Aumentador** (aumenta |líquida|): registrado como exposição externa, ALERTA uma vez por mudança, mostrado no painel; as fichas continuam operando e a soma passa a incluir a externa; a externa entra no portão de margem (13.1). O maestro não mexe nela.

## 9. Memória (persistência em disco)

### 9.1 Onde

**Estado de pregão** (por conta, símbolo e instância), em `MQL5/Files/<PastaMemoria>/<servidor>_<conta>_<símbolo>_<inst>/`:
- `estado.txt` — estado atual; `estado.bak` — cópia do anterior; `estado.tmp` — escrita em curso;
- `logs/AAAA-MM-DD.log` e `logs/AAAA-MM-DD_trans.log` (seção 11).

**Estado permanente por robô** (não depende do símbolo, sobrevive à rolagem), em `MQL5/Files/Common/<PastaMemoria>/permanente/<servidor>_<conta>_<inst>_<robo>.txt` (`FILE_COMMON`): `seq`, resultado acumulado do robô (saldo virtual, 13.3), data do primeiro deal do robô sob o maestro, último ticket de deal contabilizado. Mesmo esquema de escrita (9.4), com `.bak`.

**Testador:** a memória fica em `MQL5/Files/<PastaMemoria>_teste/` do agente de teste, **nunca** em `FILE_COMMON` (no Testador `FILE_COMMON` é a pasta comum real da máquina e um teste sobrescreveria o estado permanente da conta real). Apagada no início de cada teste.

### 9.2 O que guarda

Formato texto `chave=valor`, uma por linha, legível no Bloco de Notas.

- Cabeçalho: versão do formato, versão do EA, servidor, conta, símbolo, `IdInstancia`, `MagicMaestro`, hora da gravação (servidor e local), data do pregão a que o estado se refere, último ticket de deal processado, último instante processado, heartbeat (último ciclo vivo, `TimeTradeServer` e `TimeLocal`).
- Registro de ordens em trânsito (4.6) e registro de envios do dia (comentário, ticket, hora, papel) — usado para reconhecer ordens próprias (4.2, 10.1).
- Bloqueios ativos com causa e o valor de `ContadorDesbloqueio` já visto.
- Por robô: ligado/desligado, estado do ciclo (6.1), níveis de stop e alvo pedidos, tickets (pista), marca da entrada, e as variáveis internas listadas no Apêndice A. **Guarda instantes, nunca contagens** (hora da vela do fill, hora do envio; as contagens de velas são recalculadas das barras na volta).

### 9.3 Quando grava

- Na hora: antes de cada `OrderSend` (registro de trânsito), a cada transição do ciclo (6.2), a cada mudança de nível de stop/alvo, a cada entrada ou saída de bloqueio, no `OnDeinit`.
- Demais mudanças de estado interno: acumuladas e gravadas no máximo 1 vez por segundo pelo timer.
- Heartbeat: gravado a cada 10 s mesmo sem mudança (é ele que mede a lacuna da seção 10.4).

### 9.4 Como grava (sem corromper se o PC desligar no meio)

1. Escreve `estado.tmp` inteiro; última linha `fim=<checksum>` (soma simples dos bytes anteriores); `FileFlush`; `FileClose`.
2. Copia `estado.txt` → `estado.bak`.
3. Move `estado.tmp` → `estado.txt` (`FileMove` com `FILE_REWRITE`).

Leitura: arquivo ausente, de **tamanho zero**, sem a linha `fim=` ou com checksum errado = corrompido → usa `estado.bak`; os dois corrompidos → recuperação pelo caso C (10.3), ALERTA.

### 9.5 Regras de validade

- Memória de **outro servidor ou outra conta** (cabeçalho) → ignorada inteira; caso C; ALERTA.
- Memória de **outro pregão** → guarda só o registro de trânsito não resolvido e os bloqueios que exigem o dono; descarta o estado de ciclo e o estado interno dos robôs (exceto o de uma ficha de pregão anterior, usado no passo R11).
- **Estado permanente perdido** (as duas cópias): `seq` reconstruído como o maior `seq` encontrado nos comentários `MAE|<inst>|<robo>|` das ordens do histórico completo (`HistorySelect(0, agora)`); resultado acumulado reconstruído pela soma de 3.1 sobre todos os deals do magic cuja ordem de origem tem comentário `MAE|<inst>|`. Log `MEMORIA reconstruida` com os dois números.

## 10. Recuperação na partida

Toda partida (inclusive a primeira do dia, a mudança de input e a volta depois de queda) passa por aqui **antes de qualquer atividade**: nenhum robô roda e nenhuma ordem nova de entrada sai até `PRONTO`.

### 10.1 Exclusividade de instância

1. **Trava no terminal:** no passo R1, o maestro cria (se não existir) a variável global `WinMaestro.lock.<conta>.<símbolo>` com valor 0 e tenta tomá-la com `GlobalVariableSetOnCondition(nome, <chart_id>, 0)`. Mantém `WinMaestro.hb.<conta>.<símbolo>` = `TimeLocal()` a cada 1 s. Trava de outro gráfico com heartbeat de menos de 10 s → recusa iniciar: `Alert`, push, log, `ExpertRemove()`. Heartbeat mais velho que 10 s (instância morta) → toma a trava com `GlobalVariableSetOnCondition(nome, <chart_id>, <valor antigo>)` e loga AVISO.
2. **Trava na máquina:** arquivo `Common/<PastaMemoria>/lock_<conta>_<símbolo>.lck` aberto sem `FILE_SHARE_WRITE` pela vida do EA; segundo `FileOpen` falhando → recusa iniciar (o comportamento entre terminais da mesma máquina é a verificar, P16).
3. **Entre máquinas** (PC local + VPS, ou dois terminais): nenhuma trava alcança. Detecção pela corretora: ordem ou deal com magic de robô cuja origem não está no registro de envios desta instância (9.2), ou com `inst` diferente, ou sem prefixo `MAE|` → **bloqueio total**: sem entradas e sem saídas por regra dos robôs (a outra instância também as enviaria); continuam só as S, os cancelamentos das próprias ordens e a rede de segurança (12.3), que sempre passam pelo protocolo 5.2 e pela ficha calculada dos deals. ALERTA com push, exige o dono.
4. EAs avulsos e WinSeletor: removidos dos gráficos e da pasta (seção 1). Um avulso esquecido aparece pela regra 3 (magic de robô sem prefixo `MAE|`).

### 10.2 Máquina de estados da recuperação

Avançada pelo timer de 250 ms e pelo `OnTick`. Cada passo loga início e fim com os números que encontrou.

| Estado | O que faz | Sai para | Prazo / falha |
|---|---|---|---|
| `R0_CONFIGURADO` | `OnInit` terminou | R1 | — |
| `R1_TRAVA` | exclusividade (10.1 itens 1 e 2) | R2 | falha → `RECUSADO` (`ExpertRemove`) |
| `R2_AMBIENTE` | Testador ou real; conta NETTING (HEDGING → recusa); símbolo negociável (`SYMBOL_TRADE_MODE_FULL`; `WIN$N`/`WIN@` fora do Testador → recusa); modos de preenchimento e validade (4.1); limites (4.1); valor do tick ≠ 0; notificações push habilitadas (senão AVISO diário); varredura de outros símbolos (8.8) | R3 | falha de configuração → `RECUSADO` com mensagem clara |
| `R3_AGUARDA_CONEXAO` | `TERMINAL_CONNECTED`, `SymbolInfoTick` válido, símbolo sincronizado | R4 | log `ESPERA` a cada 30 s; ALERTA após 5 min; nenhuma ordem |
| `R4_AGUARDA_HISTORICO` | janela de reconstrução (3.2) fecha | R5 | log a cada 30 s; ALERTA após 60 s; nenhuma ordem |
| `R5_LE_MEMORIA` | lê estado de pregão e permanente (9.4, 9.5) | R6 | corrompida → caso C, segue |
| `R6_RECONSTROI` | fichas pela corretora (3.1); resolve o trânsito gravado (4.6: busca pelo comentário; sem nada em 10 s → `NAO_ENVIADA`) | R7 | falha → `PROTEGENDO` |
| `R7_EXTERNA` | classifica os deals externos da janela (8.9), aplica a absorção determinística e reativa os bloqueios que exigem o dono | R8 | — |
| `R8_CANCELA_ORFAS` | **antes de qualquer outra ação com ordem:** cancela toda S, A, X-limite sem ficha e toda E que nenhum robô reconhece (com as condições de 8.5 e protocolo 5.1); cancela as irmãs de fichas que zeraram com o EA fora (5.3) | R9 | cancelamento sem desfecho → `PROTEGENDO` |
| `R9_COMPARA` | memória × corretora por robô: casos A, B, C (10.3) | R10 | — |
| `R10_PROTEGE` | toda ficha ≠ 0 com exatamente uma S (8.4); alvos do RE e do GB recriados no nível da memória; S com validade `SPECIFIED` renovada | R11 | S recusada → `PROTEGENDO` (cadência 4.8) |
| `R11_PENDENCIAS` | ficha de pregão anterior; horário perdido; ficha com sinal trocado (8.3); divergência (8.2) | R12 | divergência não corrigível → bloqueio, segue |
| `R12_REPLAY` | reprocessa as velas perdidas de cada robô (10.4) | R13 | — |
| `R13_INICIA` | `Init()` de cada robô com o estado restaurado; carga pesada (histórico de volume do CM, histórico do RE) feita aqui, nunca no primeiro tick que precisa gerir stop | R14 | — |
| `R14_PRONTO` | grava memória; log `PRONTO` com o resumo (fichas, ordens vivas, robôs ligados, bloqueios, o que aconteceu com o EA fora) e o histórico do dia (11.5) | — | — |

`PROTEGENDO` é um modo explícito: os módulos não rodam; o maestro mantém as S (8.4), detecta stop sem execução (5.4), cancela órfãs (8.5), aplica a rede de segurança e os cortes de horário (12.3) e tenta de novo o passo que falhou a cada 30 s. Log ALERTA ao entrar, AVISO a cada 5 min, INFO ao sair.

### 10.3 Classificação de cada robô (passo R9) e pendências (passo R11)

- **A. Confere** (ficha e ordens batem com a memória): restaura o estado interno; segue para o replay se houver lacuna (10.4).
- **B. A corretora andou com o EA fora** (stop ou alvo executou, entrada encheu, validade venceu, intervenção externa): **a corretora vence**. A ficha é a da corretora; as irmãs já foram canceladas no R8; cada evento perdido é logado com a hora real do deal (`ocorreu as 11:42 com o EA fora`). Entrada que encheu com o EA fora ganha a S no R10 com o nível da memória.
- **C. Sem memória utilizável:** ficha pela corretora; estado interno recalculado das barras quando possível (Apêndice A); se o robô está posicionado e não dá para recalcular o stop, usa o nível da S viva; sem S viva, `StopEmergenciaPts`. ALERTA.

Pendências do R11:
1. **Ficha de pregão anterior** (deal de abertura antes do pregão de hoje): saída pelo protocolo 5.2, com magic do robô, papel X, no primeiro instante do contínuo de hoje (`negociacao_inicio` da grade + 30 s), nunca durante a pré-abertura; ALERTA. Até lá a S GTC protege.
2. **Horário perdido:** se o horário de zeragem de um robô passou com a ficha aberta e o contínuo ainda não acabou, zera agora (protocolo 5.2); se o contínuo já acabou, a ficha fica com a S GTC, ALERTA, e vira ficha de pregão anterior no dia seguinte.

### 10.4 Lacuna: reprocessamento de velas perdidas

Lacuna = heartbeat da memória mais velho que 1 vela do tempo do robô (GB M5, CM H2, DM M1, RE M15, C1 H1).

1. Cada robô **reprocessa, em ordem, as velas fechadas desde o heartbeat**, sem enviar ordem nas velas passadas, atualizando o estado interno (contagens, alvo que se aproxima, stop que aperta, pico de afastamento, retângulo).
2. Se o replay produz uma **saída** (por sinal, por stop do EA do DM, por horário), ela é executada agora, pelo protocolo 5.2, logada `SAIDA ATRASADA` com a vela em que deveria ter ocorrido.
3. Se o replay produz uma **entrada** cuja janela ainda está aberta, ela só é enviada se o preço limite **não for executável agora** (compra: preço < melhor oferta; venda: preço > melhor demanda) e a validade da regra ainda não venceu; log `ENTRADA ATRASADA`. Caso contrário o dia fica em branco para aquela entrada: `DECISAO PERDIDA` (itens 2.1, 2.6, 4.17: limite com preço defasado é ordem a mercado disfarçada).
4. Entrada a mercado (C1) nunca é atrasada: mais de 60 s depois da abertura da vela de sinal → `DECISAO PERDIDA`.
5. Entrada cancelada pelo `OnDeinit` (seção 7) segue a mesma regra do item 3.

## 11. Logs

### 11.1 Onde

- Diário do MT5 (aba Experts) e `logs/AAAA-MM-DD.log`: uma linha por evento de negócio (catálogo 11.3).
- `logs/AAAA-MM-DD_trans.log`: uma linha bruta por evento de `OnTradeTransaction` do símbolo (tipo, ordem, deal, estado, preço, volume, magic, `request_id`). Fica separado para o log principal continuar legível.
- Escrita: o arquivo é aberto em modo de acréscimo e recebe `FileFlush` a cada linha (só se loga mudança de estado, então o custo é pequeno).

### 11.2 Formato e níveis

`HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe | [tick HH:MM:SS.mmm loc HH:MM:SS]`

- Hora principal = `TimeTradeServer()` com ms; ao fim, hora do último tick (`TimeCurrent`) e hora local.
- `NIVEL`: `INFO`, `AVISO`, `ALERTA` (exige atenção do dono: dispara `Alert()` uma vez e, com `NotificarPush`, `SendNotification`, porque `Alert()` só funciona com alguém olhando a tela), `ERRO`.
- `ROBO`: `GB`, `CM`, `DM`, `RE`, `C1` ou `MAESTRO`.
- Toda linha de ordem traz: ticket da ordem, ticket do deal (quando houver), `request_id`, `retcode` e `retcode_external`, **preço pedido e preço executado** (`DEAL_PRICE`) lado a lado (item 4.15), volume, e a líquida antes → depois.
- Anti-spam por **objeto** (ticket ou ficha), não por processo (item 1.12): a mesma condição sobre o mesmo objeto é logada na entrada, a cada 5 min enquanto durar (com contador) e na saída.

Exemplos:
```
10:00:00.012 | INFO   | CM | SINAL       | venda a favor do mes; limite 176855; validade 5 velas H2
10:00:00.140 | INFO   | CM | ORDEM       | E sell limit 1 @176855 ord #48211 req 37 rc 10008/0 MAE|i1|CM|E|00042|F
10:03:12.501 | INFO   | CM | ENTROU      | vendido 1; pedido 176855 exec 176855 deal #9912; liquida +1 -> 0
10:03:12.690 | INFO   | CM | STOP        | S buy stop 1 @178055 ord #48230 (reserva CM); atraso 189 ms
12:00:00.008 | INFO   | CM | SAIDA       | fechou do outro lado da EMA; cancela S #48230 ...
12:00:00.410 | INFO   | CM | CANCELA     | S #48230 CANCELED confirmado em 402 ms
12:00:00.560 | INFO   | CM | SAIU        | compra 1 mercado deal #9987 exec 176210; +129,00; liquida 0 -> +1
09:00:02.300 | ALERTA | MAESTRO | RECUPERA | EA fora 09:41-10:12 (heartbeat); DM: S executou 09:58 @190165 (-68,00)
```

### 11.3 Catálogo de eventos

`INICIO`, `TRAVA`, `AMBIENTE`, `ESPERA`, `HISTORICO`, `MEMORIA` (lida/gravada/corrompida/reconstruída), `RECUPERA`, `PROTEGENDO`, `PRONTO`, `RECUSADO`, `LIGADO`/`DESLIGADO`, `SINAL`, `BLOQUEIO` (sempre com motivo: gap, filtro do robô, margem, cadência, autonegociação, divergência, externa, estranha), `DESBLOQUEIO`, `ORDEM`, `REJEITADA`, `TRANSITO` (desconhecida/resolvida), `NAO_ENVIADA`, `ENTROU`, `PARCIAL`, `STOP`/`ALVO` (criado/movido/recriado), `STOP SEM EXECUCAO`, `SAIDA`, `SAIU`, `SAIDA ATRASADA`, `ENTRADA ATRASADA`, `DECISAO PERDIDA`, `CANCELA`, `EXECUTOU_ANTES`, `ZERAGEM`, `REDE` (rede de segurança), `DIVERGENCIA`, `CORRECAO`, `INVARIANTE`, `EXTERNA` (redutora/aumentadora/ordem), `ABSORVIDA`, `ORFA`, `ESTRANHA` (outra instância/avulso), `AUTONEG`, `AJUSTE`, `RELOGIO`, `MARGEM` (diagnóstico), `FIM`, `HISTORICO_DIA`, `RESUMO`.

### 11.4 O que já foi feito

- No `PRONTO` (toda partida) e no `RESUMO`: o EA imprime, por robô, a lista das operações do dia reconstruída dos deals (hora, lado, entrada, saída, motivo quando conhecido, R$), marcando as que aconteceram com o EA fora (`HISTORICO_DIA`).
- O `RECUPERA` lista cada evento perdido com a hora real do deal.

### 11.5 Resumo do dia e conciliação

No fim do pregão (após a rede de segurança) e no `OnDeinit`:
- uma linha por robô: operações, acertos, R$ bruto e líquido (3.1), maior perda;
- total da conta pelo cálculo das fichas **e** pela soma de `DEAL_PROFIT` + custos dos deals do símbolo; diferença > R$1,00 → ALERTA;
- **conciliação de contagem** (item 1.21): número de contratos negociados e Σ dos deals do símbolo contra o número de `ENTROU`/`SAIU`/`ABSORVIDA` do log; diferença ≠ 0 → ALERTA;
- contagem de AVISO, ALERTA e ERRO do dia.

### 11.6 Painel no gráfico

`Comment()` com: estado da recuperação (`PRONTO`/`PROTEGENDO`/…), robôs ligados, ficha de cada um (lado, preço, stop, alvo, resultado aberto, estado do ciclo), posição líquida real, externa, status (`OK` / `BLOQUEADO: motivo`), hora da última gravação da memória, hora do último tick.

## 12. Horários e fim de pregão

### 12.1 Relógio e grade

- Todo corte de horário do maestro (zeragem de cada robô, rede de segurança, pregão anterior, horário perdido, cancelamento de fim de dia) usa `TimeTradeServer()` + `FusoServidorH` e roda no timer, **mesmo sem tick** (item 2.8). `TimeCurrent()` congela sem cotação.
- O fim de referência é o **fim do pregão contínuo da data** (`negociacao_fim` da grade oficial da B3 vigente no dia; item 5.35), nunca a sessão do símbolo na MT5, que pode incluir o call de fechamento. No dia de vencimento do próprio contrato do gráfico, vale `vencimento_fim`.
- Data sem linha preenchida na grade (ex.: a linha de 2026-11-02 ainda vazia): usa o fim mais cedo já registrado (17:55), AVISO diário até a grade ser atualizada.
- Log `RELOGIO` quando `TimeCurrent()` e `TimeTradeServer()` divergirem por mais de 60 s durante o contínuo (feed parado, item 5.17).

### 12.2 Zeragem de cada robô

Cada robô zera no horário dele, limitado ao fim do contínuo da data:

| Robô | Zeragem testada | No maestro (`F` = fim do contínuo da data) |
|---|---|---|
| GB | 18:20 (limitado a F − 5 min) | min(18:20, F − 5 min) |
| CM | 18:24 (ou sessão − 1 min) | min(18:24, F − 1 min) |
| DM | sessão − 5 min (18:20) | F − 5 min |
| RE | 17:00, avaliada a cada vela M15 | 17:00, avaliada pelo timer (não espera vela nova) |
| C1 | 17:50 (fim 18:00 − 10 min) | min(17:50, F − 10 min) |

Em dias de contínuo até 17:55, todos os robôs zeram até 17:54. A diferença de horário do RE (timer em vez de vela) só muda algo quando a vela das 17:00 não teve tick; entra no relatório 15.1.

### 12.3 Rede de segurança e fim de dia

- Em **F − 30 s** (18:24:30 com F = 18:25): ficha ainda aberta → zera pelo protocolo 5.2 com o magic do robô, ALERTA (significa que a zeragem do robô falhou). Se a saída for recusada (call já em curso), segue 5.4.
- No mesmo instante: cancela todas as E e A dos magics dos robôs; S só sobrevive em ficha ainda aberta.
- Funciona em `PRONTO` e em `PROTEGENDO`.

### 12.4 Rolagem

O EA roda no contrato vigente (ex.: WINV26). Na troca de contrato o dono troca o gráfico; o estado de pregão é por símbolo e começa limpo no contrato novo; o estado permanente (seq, saldo virtual) é por robô e continua (9.1). Ordem ou posição esquecida no contrato velho é achada pela varredura da seção 8.8.

## 13. Capital, margem e saldo

### 13.1 Portão de margem (entradas)

O portão não usa `ACCOUNT_MARGIN_FREE`, `ACCOUNT_EQUITY` nem `ACCOUNT_BALANCE` como gatilho: o número de saldo da Rico na MT5 já travou um pregão inteiro com valor errado (item 1.19).

- **Capital efetivo** = `CapitalConta` + resultado realizado do dia de todos os robôs (3.1) + resultado aberto das fichas.
- **Pior estado alcançável depois da ordem**: com L = líquida real, P+ = Σ volumes de todas as ordens próprias vivas de compra (E, S e A, inclusive as de fichas que não poderiam executar juntas, porque com o EA fora não há OCO) mais a ordem atual se for compra, P− o mesmo para vendas, e X a exposição externa: `pior = max(|L + P+|, |L − P−|)`.
- **Margem exigida** = max(`ACCOUNT_MARGIN` + `OrderCalcMargin` da ordem atual; `OrderCalcMargin(1 contrato)` × `pior`).
- **Recusa** se margem exigida > capital efetivo: não envia, `BLOQUEIO margem` com os números (item 3.7: o portão recusa o que a corretora recusaria).
- `ACCOUNT_MARGIN_FREE` é logado (`MARGEM`) a cada 5 min e quando discordar em mais de 20% de (capital efetivo − margem exigida atual): AVISO, sem efeito no portão.
- Se `OrderCalcMargin` devolve a margem de day trade da Rico ou a margem cheia da B3: a verificar (P8).

### 13.2 Saídas e stops que aumentam a líquida

Em netting a saída de uma ficha pode ser **abertura** para a conta: com CM comprado 1, RE e DM vendidos 1 (líquida −1), o stop do CM (venda) leva a líquida a −2 e exige margem (item 1.1). O portão de 13.1 existe para que isso nunca falte: ao calcular `pior` com todas as S e A vivas, ele recusa a **entrada** que tornaria inalcançável a margem de uma saída futura (item 3.3). Saídas nunca passam pelo portão. Recusa por margem de ordem de papel S, X ou C é ALERTA imediato com push e segue 5.4 (limite agressiva) e 4.8. Se a Rico checa margem na colocação de pendente e no disparo de stop: a verificar (P7, P8).

### 13.3 Saldo virtual do DM

O DM limita o stop a 10% do saldo. Numa conta compartilhada o saldo da conta não é o capital do robô. Regra (Apêndice B.2): saldo virtual do DM = `DM_CapitalRobo` (R$1.000) + resultado acumulado do DM (3.1, só deals sob o maestro), guardado no estado permanente (9.1) e reconstruível pelo histórico (9.5). Com R$1.000, o teto é R$100 por contrato = 500 pts de stop. `DM_UsarSaldoDaConta = true` volta ao saldo da conta.

### 13.4 Pior caso numérico das exceções do Princípio 4

Referência de movimento: **5.630 pts** contra num dia (R$1.126 por contrato) = percentil 99 de (máxima − mínima) diária do WIN$N, 2022-01 a 2026-10 (medido no replay em 2026-10-06; mediana 1.865, p95 4.081, máximo 8.320 pts). É um teto conservador: a amplitude do dia inteiro, não a excursão a partir da entrada.

| Exceção | Contratos sem stop no pior caso | Perda a 5.630 pts |
|---|---|---|
| (a) entradas limite que enchem com o EA fora ou desconectado: GB, CM, DM, RE | 4 | R$4.504 |
| (b) S e A executando juntas com o EA fora (RE; GB se o alvo for ligado) | 1 por robô com alvo; não soma com (a) para o mesmo robô | R$1.126 por robô |
| (c) CM só com a reserva distante | dentro de (a); limitado por `CM_ReservaPts` | R$0,20 × 4.945 = R$989 |
| Teto teórico (5 fichas no mesmo lado sem stop) | 5 | R$5.630 |
| Janela fill→stop com o EA vivo (medida em toda abertura, 4.3) | 1 por abertura, por centenas de ms | desprezível salvo salto no mesmo instante |

O cancelamento das entradas pendentes no `OnDeinit` (seção 7) reduz (a) nos fechamentos ordenados do terminal; não reduz em queda de energia, travamento ou internet caída.

### 13.5 Capital mínimo da conta

- Exposição máxima alcançável: |líquida| = 5 contratos (5 fichas de 1 lote; com execução dupla cada ficha vai no máximo a ∓1).
- Margem do pior estado = `OrderCalcMargin(1)` × 5 × 2,0 (buffer de margem do projeto). Com a referência de R$100 por contrato (a verificar na Rico, P8): R$1.000.
- **Capital mínimo da conta = max(Σ `CapitalRobo` dos robôs ligados = 5 × R$1.000 = R$5.000; margem do pior estado + perda do teto teórico = R$1.000 + R$5.630 = R$6.630) = R$6.630** (Apêndice B.10). O EA loga AVISO na partida se `CapitalConta` for menor que esse número.
- Contratos simultâneos medidos no replay 2022–2026: no máximo 4.

## 14. Riscos de bolsa e perguntas a verificar antes do real

### 14.1 Riscos e onde estão tratados

| Risco | Tratamento |
|---|---|
| Ordem stop pendente na Rico/B3 (aceitação, onde mora, o que vira ao disparar) | 4.3, 5.4; P1, P2, P13 |
| Autonegociação | 4.9; P12 |
| Limite de ordens por segundo da corretora | envio serial (4.5) + teto e disjuntor (4.8) |
| Leilão (abertura, call, por variação) | 5.4, 12.3; P13 |
| Stop recusado por preço já atravessado | 4.7 item 3 com protocolo 5.2 |
| SL/TP na posição líquida | 8.7 (nunca removido) |
| Reconexão e histórico incompleto | 8.2 (verificação cruzada), 4.6; P18 |
| Zeragem compulsória e stop-out | 8.9; P10, P11 |
| Margem de saída que aumenta a líquida | 13.2; P7, P8 |

### 14.2 Perguntas (demo ou envio mínimo no real)

Marcadas **(real)** as que a demo da Rico provavelmente não reproduz (casamento simulado, item 4.7): pedem resposta escrita da Rico ou um teste com 1 contrato no real.

| # | Pergunta | Decide |
|---|---|---|
| P1 | `ORDER_TYPE_SELL_STOP`/`BUY_STOP` no WINV26: aceita? Com validade DAY, GTC e SPECIFIED? Continua listada com o terminal fechado? Que `ORDER_TYPE` e `ORDER_STATE` assume ao disparar? Fica no servidor MT5 da Rico ou vai à B3 como stop nativo? Dispara pelo último negócio? Ao disparar vira mercado, limite com proteção ou stop-limit? | 4.1, 4.3, 5.4, B.6 |
| P2 | O deal gerado por uma ordem stop ou limite pendente carrega o `DEAL_MAGIC` e o comentário da ordem? E qual `DEAL_REASON`? | 3.1, 4.4, 8.9 |
| P3 | O `ORDER_COMMENT` sobrevive igual (sem truncar nem trocar) na ordem, no histórico e depois de `OrderModify`? Até quantos caracteres? | 3.3, 4.2, 10.1 |
| P4 | O `OrderModify` de uma ordem stop pendente mantém o mesmo ticket? A ordem fica fora do ar durante a modificação? Aceita modificar o volume? | 3.3, 4.7, 6.3 |
| P5 | `OrderDelete` de uma ordem que acabou de disparar: qual retcode, qual `ORDER_STATE` no histórico, e quanto tempo até o histórico mostrar o desfecho? | 5.1, `PrazoConfirmacaoS` |
| P6 | Atraso entre o retorno do `OrderSend` (mercado) e o deal aparecer em `HistorySelect`, com p50 e máximo em 50 envios. Alguma vez volta `DONE` com `deal=0`? | 4.6, `PrazoConfirmacaoS` |
| P7 | Com a líquida em −1 (dois robôs vendidos, um comprado), o stop do comprado dispara e leva a líquida a −2: passa pela checagem de margem? Com margem justa, é recusado? **(real)** | 13.2 |
| P8 | Ordem pendente bloqueia margem na colocação? `OrderCalcMargin(WIN, 1)` devolve a margem de day trade da Rico ou a da B3? Qual é a margem de day trade do WIN na Rico? | 13.1, 13.5 |
| P9 | `ACCOUNT_MARGIN_FREE` e `ACCOUNT_MARGIN` batem com o extrato da corretora no mesmo instante, em pelo menos 5 dias diferentes? | 13.1 |
| P10 | Zerar a líquida na mão pelo terminal: qual `DEAL_REASON` e qual magic aparecem? E pela mesa da corretora, por telefone? **(real)** | 4.4, 8.9 |
| P11 | A Rico faz zeragem compulsória de day trade no WIN? A que horas, com que `DEAL_REASON`/magic, e cancela as ordens pendentes? **(real)** | 8.9, 12.2 |
| P12 | Autonegociação: existe Self-Trade Prevention na conta? Um SELL_STOP disparando contra a própria BUY_LIMIT na melhor oferta executa, é cancelado, ou cancela a passiva? Qual lado é cancelado e como chega na MT5 (retcode, `ORDER_STATE`, comentário)? **(real)** | 4.9 |
| P13 | Stop disparado durante leilão (abertura, call de fechamento, leilão por variação): vira o quê? Ordem a mercado enviada pelo EA em leilão: qual retcode? Limite agressiva participa do leilão? **(real)** | 5.4, 12.3 |
| P14 | Uma ficha (posição) que passa a noite: o `POSITION_PRICE_OPEN` muda para o ajuste no dia seguinte? Aparecem deals de ajuste ou variação de margem? Com que tipo e volume? | 3.1, 3.2 |
| P15 | Que modos de preenchimento (`SYMBOL_FILLING_MODE`) e de validade (`SYMBOL_EXPIRATION_MODE`) o WINV26 aceita? Ordem a mercado com `RETURN` é aceita? | 4.1 |
| P16 | Duas instâncias: um segundo `FileOpen` sem `FILE_SHARE_*` no mesmo arquivo de trava falha (mesmo terminal e dois terminais na mesma máquina)? `GlobalVariableSetOnCondition` funciona como trava entre dois gráficos? | 10.1 |
| P17 | `REASON_PARAMETERS` e `REASON_CHARTCHANGE`: as variáveis globais do EA sobrevivem ao reinício? | 2, 7 |
| P18 | Depois de 2 min sem internet: o histórico de deals volta completo de uma vez? Quanto tempo leva até `Σ deals = líquida`? | 3.2, 8.2 |
| P19 | `TimeTradeServer()` continua andando com o feed parado? Qual a diferença para `TimeCurrent()` no leilão de abertura? | 12.1 |
| P20 | `ACCOUNT_LIMIT_ORDERS` e `SYMBOL_VOLUME_LIMIT` da conta para o WIN. Qual o limite de contratos de WIN por cliente em day trade na Rico? | 4.1, 13.5 |
| P21 | A demo da Rico casa ordens contra o livro real da B3 ou contra simulação? Essa resposta define o que a etapa da demo prova. | 15.3, 15.5 |
| P22 | O relógio do servidor da Rico está em horário de Brasília (`FusoServidorH = 0`)? | 12.1 |
| P23 | Um stop pendente GTC num contrato que vence é cancelado pela corretora no vencimento? | 4.3, 12.4 |
| P24 | O `OrderDelete` enviado dentro do `OnDeinit` no fechamento do terminal chega ao servidor? | 7, 13.4 |

## 15. Testes antes de usar com dinheiro

### 15.1 Equivalência (Testador, WIN$N, ticks reais)

**Pré-condições de cada teste:**
- Cache de ticks do Testador com `last` em ≥ 99% dos ticks do período (EA `AuditoriaTicks`) e tamanho igual ao do terminal (itens 5.33, 6.54). Abaixo disso o teste não vale.
- Valor do tick lido do símbolo, não digitado (item 6.55).

**Testes:**
1. Cada robô sozinho no maestro × EA avulso no mesmo período.
2. Os 5 ligados × replay T6 (`combinacoes/z9_netting/t6_maestro`): resultado por robô igual ao isolado; posição líquida máxima registrada.

**Critério de aceitação:**
- Entradas (hora e lado): 100% iguais.
- Preço de saída por stop: diferença ≤ 1 tick por trade.
- Resultado total por robô: diferença ≤ max(2%; R$1,00 × número de trades).
- **Toda** diferença listada trade a trade com a causa. Causas esperadas e permitidas: reserva do DM (5.5; mesmo preço, caminho S), atraso da saída pelo protocolo 5.2, prioridade da ordem fixa (4.5), autonegociação (4.9), zeragem do RE pelo timer (12.2).
- Relatório com: contagem de ordens recusadas (recusa > 0 = linha censurada, item 6.55), pior trade em múltiplos do stop (item 6.56), número de trades com stop estourado na vela do fill.

### 15.2 Testes unitários com corretora falsa

Casos que a demo não reproduz sob demanda, testados com uma camada de envio falsa (script de teste que substitui `OrderSend`/histórico):
1. `DONE` com `deal=0`, deal aparecendo 3 s depois e 8 s depois (4.6).
2. `OrderDelete` aceito com desfecho FILLED (5.1, 5.2).
3. Histórico chegando aos poucos depois da reconexão (8.2: nenhuma correção enviada).
4. S e A executando juntas (8.3: uma correção; a segunda em 10 min bloqueia).
5. Comentário truncado e ticket trocado no `OrderModify` (3.3).
6. Deal externo redutor com 2 fichas do mesmo lado e com fichas dos dois lados (8.9).
7. Queda entre a gravação do trânsito e o `OrderSend` (4.6 item 1).
8. Recusa repetida de S (4.8: cadência, nunca por tick).

### 15.3 Falhas (conta demo, pregão real)

| Cenário | Esperado |
|---|---|
| Fechar o MT5 com 2 robôs posicionados e reabrir 5 min depois | E canceladas no `OnDeinit`; S continuam no servidor; fichas recuperadas; `RECUPERA` com o que mudou; `HISTORICO_DIA` impresso |
| Matar `terminal64.exe` pelo Gerenciador de Tarefas (sem `OnDeinit`) com entrada pendente viva | E continua viva; se encher com o EA fora, na volta a ficha ganha S no R10 com o nível da memória; caso B logado |
| Fechar o MT5 e deixar o stop de um robô executar | Na volta: ficha zerada, alvo cancelado no R8, evento logado com a hora real |
| Stop e alvo executando juntos com o EA fora | Na volta: ficha com sinal trocado corrigida no R11 (8.3), ALERTA |
| Apagar `estado.txt` com robôs posicionados | Usa `estado.bak` |
| Apagar `estado.txt` e `estado.bak` | Caso C, ALERTA; nenhum robô sem stop |
| `estado.txt` cortado ao meio e `estado.txt` de tamanho zero | Usa `estado.bak` |
| Memória copiada de outra conta | Ignorada, caso C, ALERTA |
| Apagar o estado permanente | `seq` e saldo virtual reconstruídos do histórico, log `MEMORIA reconstruida` |
| Desligar a internet 2 min | `ESPERA`/`HISTORICO`, sem ordens; na volta, nenhuma correção antes de a verificação cruzada fechar |
| Desligar a internet enquanto uma entrada limite enche | Na volta: deal visto, S criada, atraso fill→stop logado |
| Reinício durante o `OrderSend` (fechar o MT5 logo após um sinal) | Trânsito resolvido pelo comentário no R6, nada duplicado |
| Zerar a líquida na mão com 2 robôs posicionados | `EXTERNA redutora`, absorção GB→C1, S/A das fichas absorvidas canceladas, bloqueio até `ContadorDesbloqueio` |
| Pôr SL na posição líquida pela tela | Bloqueio, ALERTA; SL **não** removido |
| Abrir posição manual no símbolo | `EXTERNA aumentadora` ALERTA; robôs seguem |
| Maestro em dois gráficos do mesmo símbolo | O segundo recusa iniciar (`TRAVA`) |
| EA avulso com magic do CM em outro gráfico | `ESTRANHA`, bloqueio total, ALERTA |
| Trocar o timeframe do gráfico com robôs posicionados | `REASON_CHARTCHANGE`: entradas não canceladas; recuperação A; nada duplicado |
| Trocar de conta com o EA rodando | `REASON_ACCOUNT`: entradas canceladas; na conta nova a memória da outra conta é ignorada |
| Desligar um robô (input) com ficha aberta | Ele só gere até zerar; não abre nova |
| Deixar a ficha passar da zeragem (EA fechado às 18:19, aberto 18:23) | Zera na hora (horário perdido) |
| EA fechado das 18:00 às 09:10 do dia seguinte com ficha aberta | S GTC protegeu a noite; ficha de pregão anterior zerada em 09:00:30; ALERTA |
| Dia de vencimento do WIN | Cortes pela grade da data; nenhuma ordem no contrato velho (8.8) |
| Dia com contínuo até 17:55 (se a grade tiver) | Todos zeram até 17:54; rede às 17:54:30 |
| Leilão por variação, quando ocorrer | Saídas recusadas seguem 5.4; log com retcode |
| Rede de segurança: impedir a zeragem de um robô (ex.: forçar recusa) | `REDE` zera em F − 30 s |

### 15.4 Caminhos de saída obrigatórios

Antes do real, cada caminho abaixo precisa de evidência no log de ter disparado ao menos uma vez (item 4.28): zeragem de cada um dos 5 robôs; rede de segurança; ficha de pregão anterior; horário perdido; correção de sinal trocado; saída agressiva de 5.4; cancelamento de E no `OnDeinit`; absorção externa.

### 15.5 Escada no real

A demo da Rico não mede fila, autonegociação nem comportamento de stop na B3 (item 4.7, P21). A ida ao real é em degraus:

| Degrau | Configuração | Duração mínima |
|---|---|---|
| 1 | 1 robô, 1 contrato | 5 pregões |
| 2 | 2 robôs que podem ficar em lados opostos (ex.: CM e RE) | 5 pregões |
| 3 | os 5 robôs | — |

Cada degrau só avança com: zero `DIVERGENCIA` não explicada; extrato da corretora (deals) igual ao log do maestro em contagem de contratos e preço; perguntas **(real)** que o degrau alcança respondidas; e os caminhos de saída de 15.4 alcançáveis no degrau observados. Antes do degrau 1: todos os cenários de 15.3 passando na demo, 15.1 e 15.2 aprovados, e as perguntas P1–P6, P8, P15–P20, P22–P24 respondidas.

## 16. Fora do escopo (de propósito)

- Combinar sinais, prioridade entre robôs, consenso (testados na Z9, piores que fichas independentes).
- Limite de perda diária, de operações, de horário extra: não pedidos.
- Hedging: o maestro só roda em NETTING.
- O alarme do item 1.24 (`POSITION_PRICE_OPEN` fora da grade de preço = duas pernas fundidas) **não se aplica** aqui: com várias fichas, preço médio da líquida fora da grade é normal. Não portar.

## Apêndice A — por robô

Fonte: `WinMaestro_inventario_modulos.md`. Regras que valem para os cinco:
- Os 3 bloqueios por "posição de outro robô" (CM L774, DM L379, C1 L620) são removidos.
- Os fechamentos que fecham a posição INTEIRA (`PositionClose(_Symbol)` ou pelo ticket da líquida; 14 call sites) viram `Ficha_Fecha(robo)` (protocolo 5.2).
- Todo `PositionModify` de SL vira `Ficha_DefineStop` (seção 4.7); todo SL anexado na entrada vira S criada no preenchimento (4.3).
- Validades: entradas e alvos DAY (GB entrada `SPECIFIED`), stops GTC (4.1).
- O "gate de vela nova" (`g_ultima_barra` e equivalentes) é persistido: um reinício não reentra na mesma vela (CM, C1).
- Persistem-se instantes, nunca contagens (9.2); lacuna → replay (10.4).

### A.1 WinGapBarra1 (GB, magic 80080601, M5)
- Entrada limite 09:05 `SPECIFIED` até 09:35 (fallback DAY + cancelamento em `g_exp`); S de 1.200 pts criada no preenchimento; alvo e break-even desligados no padrão (se ligados: alvo = A do robô; BE = `OrderModify` da S).
- Persistir: `g_decidido`, `g_exp` (instante), `g_be_feito`, data do pregão, `seq` da entrada viva.
- Reinício entre 09:05 e 09:35 com a entrada viva: a entrada é reconhecida pelo papel (3.3); não sai segunda entrada.
- Recalculável: stop = preço da ficha ∓ `StopPts`.
- Entrada atrasada (10.4): só se o preço limite não for executável agora e antes de `g_exp`.
- Zeragem: 12.2. Ficha de pregão anterior: 10.3.

### A.2 WinCincoMedias (CM, magic 80080501, H2)
- `a_favor` vem da marca da entrada (`F`/`N` no comentário, 4.2) e da memória; sem as duas, recalculado das barras da vela de sinal.
- Entrada limite DAY, validade 5 velas H2 contada pela hora de envio (instante); saídas a mercado pelo EA (protocolo 5.2).
- Sem stop inicial pela regra do robô: S de **reserva** a `CM_ReservaPts` do preço da ficha desde o preenchimento (Apêndice B.1). Quando o "stop que aperta" nasce, a mesma S é movida para o nível dele (nunca afrouxa).
- Persistir: `g_ultima_barra`, `a_favor`, nível do stop que aperta, hora e lado da entrada viva.
- Recalculável: stop que aperta (das barras desde a hora da ficha); histórico de volume relativo (no passo R13, nunca no primeiro tick que precisa gerir stop).
- Replay (10.4): velas H2 fechadas com o EA fora são reprocessadas; saída por sinal que deveria ter ocorrido vira `SAIDA ATRASADA`.
- Zeragem: 12.2.

### A.3 WinDeslocamentoMatinal (DM, magic 80080101, M1)
- Stop controlado pelo EA (fecha pelo protocolo 5.2 quando o último negócio cruza `g_stopNivel`) + S de reserva a `DM_ReservaTicks` além (5.5, Apêndice B.5).
- Persistir (crítico): `g_stopNivel`, `g_distStop`, `g_stopAjustado`, `g_decidiu`, `g_dia`, `seq` da entrada, `g_ordemHora` (instante), `g_ordemPreco`. A entrada viva é reconhecida pelo papel (3.3), não pelo ticket guardado.
- Recalculável se a memória falhar: `g_distStop` pela decisão das 10:30 refeita das barras (distância até a linha da abertura apertada pelo teto de risco com o saldo virtual do robô); sem isso, nível da S de reserva menos `DM_ReservaTicks`.
- Replay (10.4): M1 fechadas desde o heartbeat; se alguma cruzou `g_stopNivel`, `SAIDA ATRASADA` agora.
- Saldo: saldo virtual (13.3).
- Zeragem: 12.2.

### A.4 WinRetanguloEma34 (RE, magic 20261005, M15)
- Preenchimento detectado pelo deal com o magic do robô e `DEAL_ORDER` = entrada.
- S = stop do robô (era SL da posição); A = limite do robô que se aproxima (`OrderModify`), DAY.
- Persistir: entrada pendente (`seq`, hora de envio, lado, `g_meio_original`, `g_stop_original`, `g_alvo_original`), posição (`g_preco_entrada`, `g_largura_posicao`, `g_frac_alvo_atual`, hora da vela do fill) e retângulo vivo (`g_tem_retangulo`, `g_topo`, `g_piso`, `g_largura`, `g_meio`, `g_fora_seguidas`). `g_barras_esperando` e `g_barras_posicao` são recalculados a partir dos instantes.
- O `Deinit` do módulo não cancela a entrada por conta própria; quem cancela é a regra do `OnDeinit` do maestro (seção 7), pelo motivo de encerramento.
- Stop e alvo vivos com o EA fora: exceção (b) do Princípio 4 (Apêndice B.9).
- Zeragem 17:00 pelo timer (12.2).

### A.5 Win_c1 (C1, magic 80080002, H1)
- Único que entra a mercado: preço da ficha = preço do deal; S enviada no mesmo fluxo do `OrderSend` (4.3); trailing por vela H1 = `OrderModify` da S.
- Break-even e esticada usam preço e hora **da ficha**.
- Persistir: `g_ultima_barra`, nível do stop.
- Recalculável: pico de afastamento e esticada armada (das barras desde a hora da ficha), stop (roxa ∓ K×ATR da última H1 fechada).
- Entrada nunca atrasada mais de 60 s (10.4 item 4).
- Zeragem: 12.2.

## Apêndice B — decisões do dono antes de implementar

Cada item traz a recomendação adotada no texto acima; todos **aguardam o dono**.

1. **Stop de reserva do CM.** O robô não tem stop inicial; com o EA fora a ficha fica sem proteção. Opções: (a) sem reserva (fiel ao testado); (b) S de reserva distante, que nunca dispararia nos testes 2022–2026 e só protege em queda: `CM_ReservaPts` = maior excursão adversa de um trade do CM no replay 2022–2026 + 20%, arredondada para cima em ticks. **Medido em 2026-10-06: 815 trades, maior excursão 4.120 pts (2,18% do preço, 02/10/2026), p99 2.241, mediana 400 → `CM_ReservaPts` = 4.945.** Nunca teria disparado nos testes. **Recomendação: (b).**
2. **Saldo do DM:** saldo virtual do robô (R$1.000 + resultado dele, 13.3) ou saldo da conta. **Recomendação: saldo virtual** (o saldo da Rico não é confiável, item 1.19, e com 5 robôs 10% da conta é outro teto).
3. **Entradas e alvos DAY** (Retângulo e alvo do GapBarra1 eram GTC): todos são day trade e nenhuma entrada ou alvo deve passar a noite. **Recomendação: DAY.**
4. **WinSeletor e EAs avulsos aposentados**: o maestro com um robô ligado faz o que o Seletor fazia; remover dos gráficos e da pasta (10.1). **Recomendação: aposentar.**
5. **Stop do DM: dois caminhos em níveis diferentes** (5.5). Opções: (a) só a S no servidor, no nível do stop (muda o mecanismo testado: o stop passa a disparar no servidor, sujeito ao comportamento de P1/P13); (b) stop do EA no nível testado + reserva `DM_ReservaTicks` = 20 ticks além, só para o EA ausente. **Recomendação: (b)**, fiel ao testado; custo da reserva com o EA fora: até R$20 por contrato além do stop.
6. **Validade dos stops GTC.** Opções: (a) GTC (ou `SPECIFIED` até o fim do pregão seguinte): a ficha esquecida no fim do dia fica protegida durante a noite e na abertura; o risco é uma S órfã sobreviver, tratado pelo passo R8 e pela reconciliação (8.5); (b) DAY: posição nua durante a noite quando o EA falha no fim do dia. **Recomendação: (a) GTC.**
7. **Janela sem stop (Princípio 4, exceções a e b).** Aceitar a janela fill→stop e a ausência de OCO com o EA fora, com as mitigações adotadas (S do C1 no mesmo fluxo do envio; cancelamento das E no `OnDeinit`; S criada na mesma chamada que vê o deal) e o pior caso de 13.4 (R$1.600 a 4 contratos; teto R$2.000). A alternativa de cancelar entradas quando o EA perde a conexão não protege: o cancelamento precisa da conexão que está faltando. **Recomendação: aceitar.**
8. **Absorção de intervenção externa redutora** (8.9): ordem fixa GB, CM, DM, RE, C1 ou proporcional. **Recomendação: ordem fixa** (determinística, reproduzível pela recuperação sem memória).
9. **RE com stop e alvo vivos sem o EA** (5.3): aceitar o risco de execução dupla com o EA fora, ou rodar o RE sem alvo no servidor (muda o robô). **Recomendação: aceitar**, com a correção do passo R11.
10. **`CapitalConta`**: R$6.630 pelo cálculo de 13.5 (5 contratos sem stop com o EA fora num dia de amplitude p99). **Recomendação: R$7.000.** R$5.000 (o capital com que cada robô foi testado) cobre a margem e o uso normal, mas não o pior caso de queda do EA.

## Apêndice C — rastreabilidade da revisão adversarial 1

### C.1 Lacunas

| Lacuna | Resolvida em |
|---|---|
| C1 ordem em trânsito / DONE sem deal | 4.6; 3.1 (ficha efetiva); 6.1 `TRANSITO_DESCONHECIDO`; 9.3 (gravação antes do envio); 15.2 casos 1 e 7 |
| C2 cancelamento confirmado | 5.1, 5.2; 4.7 item 3; 5.5 (DM); decisão do DM no Apêndice B.5 |
| C3 intervenção externa | 8.9, 8.7, 4.4; P10, P11; Apêndice B.8 |
| C4 janela fill→stop | Princípio 4 (a); 4.3 (S do C1 no mesmo fluxo; atraso logado); 7 (`OnDeinit` cancela E); 13.4; Apêndice B.7 |
| C5 sem OCO no servidor | Princípio 4 (b); 5.3; 10.2 R8 e R11; 13.4; Apêndice B.9 |
| C6 duas instâncias | 10.1; 4.2 (`inst`); 1 (aposentar avulsos); P16; 15.3 |
| C7 autonegociação | 4.9; P12 |
| C8 stop que é abertura para a conta / margem | 13.1 (pior estado), 13.2; P7, P8 |
| C9 stops DAY e ficha que atravessa a noite | 3.2 (janela desde o último zero); 4.1 e 4.3 (GTC); 10.3 pendência 1; Apêndice B.6; P14, P23 |
| C10 divergência transitória | 8.2; 8.3 (única correção, limite de 1 a cada 10 min); 3.2 (verificação cruzada); 10.2 R4 |
| C11 stop disparado sem execução | 5.4; 4.3 (fallback stop-limit); P1, P13 |
| A1 relógio e fim do contínuo | 12.1, 12.2, 12.3; P19, P22 |
| A2 `DEAL_ENTRY`/`DEAL_PROFIT` | 3.1; 11.5 |
| A3 papel pelo comentário, ticket no `OrderModify` | 3.3; 4.7 item 5; P3, P4 |
| A4 bloqueio não cancelava entradas | 8.6 |
| A5 estado restaurado velho | 9.2 (instantes); 10.4; Apêndice A |
| A6 `OnInit` e modo protegendo | 7; 10.2 (máquina de estados, `PROTEGENDO`); 2 (reinicialização explícita); P17 |
| A7 margem livre como gatilho | 13.1, 13.5; P8, P9; Apêndice B.10 |
| A8 equivalência | 15.1; 5.5 (efeito da reserva do DM); 4.1 (preenchimento a mercado) |
| A9 plano de testes | 15.2, 15.3, 15.4, 15.5; P21 |
| A10 retentativas | 4.8; 8.4; 5.4 |
| A11 DM com dois caminhos no mesmo nível | 5.5; Apêndice B.5 |
| M1 memória | 9.1 (permanente em `FILE_COMMON`, Testador isolado), 9.4 (tamanho zero), 9.5 (outra conta, reconstrução de `seq` e saldo) |
| M2 órfã contra ordem recém-enviada | 8.5 |
| M3 magic da correção | 4.4, 8.3 (sempre o magic do robô; `MagicMaestro` não envia ordem) |
| M4 logs | 11.1, 11.2, 11.3, 11.4, 11.5 |
| M5 rolagem e outros símbolos | 8.8, 12.4, 10.2 R2 |
| M6 custo da reconciliação | 8.1; 3.1 (função única) |
| M7 modos de preenchimento e validade | 4.1; 10.2 R2; P15 |
| M8 mover stop | 4.7 |
| B1 limite de 31 caracteres | 4.2; P3 |
| B2 alarme do item 1.24 | 16 |
| B3 limites da conta e do símbolo | 4.1; P20 |
| B4 parcial com `Lote` > 1 | 6.3 |
| B5 prioridade da ordem fixa | 4.5; 15.1 |

### C.2 Afirmações apontadas como erradas ou não verificáveis

| Seção / afirmação | Resolvida em |
|---|---|
| Princípio 4: "todo robô posicionado tem o stop dele como ordem pendente" | Princípio 4 com as exceções declaradas; 13.4; Apêndice B.7 |
| 3 / 10.6: ficha = deals do dia × ficha de pregão anterior | 3.2 (janela desde o último zero); 3.1; 10.3 pendência 1 |
| 4.4: magic desconhecido = externa e "não mexe" | 8.9 (redutora × aumentadora) |
| 4.3: a ordem stop "fica no servidor com o terminal desligado" | 4.3 (a verificar); P1, P13 |
| 13: "entrada que reduz a líquida não exige margem nova" | 13.2 |
| 13: portão por "margem livre" | 13.1 |
| 14.2: bloquear ordem que cruza com ordem própria | 4.9 |
| 14.6: zerar SL/TP da posição | 8.7 |
| 14.7: ticket processado uma vez evita contar duas vezes | 8.1 (deduplicação) + 8.2 (verificação cruzada); P18 |
| 2: "mudar inputs reinicia o EA … recuperação completa" | 2; 7 (reinicialização explícita); P17 |
| A: "`ORDER_FILLING_RETURN` … o que a B3 exige em limite" | 4.1 (limite RETURN; mercado conforme P15) |
| 4.2: comentário identifica a ordem depois do reinício | 3.3 (papel por tipo e lado; comentário é conferência); P3 |

### C.3 Checklist de `LICOES_DE_PRODUCAO.md`

| Item | Onde está coberto |
|---|---|
| 1.1 | 13.2 |
| 1.2 | Princípio 4 (exceção declarada); 4.3; 13.4; B.7 |
| 1.4 / 1.23 | Princípio 5; 5.2; 5.5 |
| 1.5 | 5.1 |
| 1.6 | 4.6; 8.1 item 1 |
| 1.7 | 8.2 |
| 1.8 / P8-69 | 8.5 (com a condição de M2) |
| 1.9 | 8.6 |
| 1.10 | 4.7 item 4 |
| 1.12 / 1.13 | 11.2 (anti-spam por objeto); 4.8 (escalada) |
| 1.17 / 1.24 / 1.25 | 4.6; 8.2 |
| 1.19 | 13.1 |
| 1.21 | 11.5 |
| 1.22 | 4.8; 4.9 |
| 2.1 / 2.6 | 10.4 |
| 2.4 | 10.1 |
| 2.8 / 4.28 | 12.1; 15.4 |
| 3.2 / 3.3 | 13.1 |
| 4.17 | 10.4 item 3 |
| 4.30 | 4.7 item 2 |
| 5.33 / 6.54 / 6.55 / 6.56 | 15.1 |
| 5.35 | 12.1 |
