# WinMaestro — especificação

Versão da especificação: 0.4 (2026-10-07). Substitui o WinSeletor v1.00.

Convenções:
- "item X.Y" aponta para `LICOES_DE_PRODUCAO.md`; "P n" aponta para a pergunta n da seção 14.2.
- **"a verificar"** = depende da Rico, da B3 ou da MT5 e ainda não foi confirmado; cada ocorrência cita a pergunta que decide.
- Todo prazo, contagem ou nível tem número. Os números técnicos são constantes do código (tabela 2.2); o dono não ajusta nada além dos inputs da seção 2.1.
- WIN: tick = 5 pontos = R$1,00 por contrato; 1 ponto = R$0,20 por contrato. O EA **lê** esses valores do símbolo (`SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_TRADE_TICK_VALUE`); leitura zerada é repetida (10.2) e nunca é usada (item 5.22).
- **Ficha pelos deals** = o que a corretora executou com o magic do robô. **Ficha efetiva** = ficha pelos deals + ordens de execução imediata do robô ainda sem desfecho (4.6). **Volume de saída sempre vem da ficha pelos deals.**
- **Leitura confiável** = `TERMINAL_CONNECTED` verdadeiro há pelo menos `CONEXAO_MIN` (10 s) contínuos, releitura completa do histórico (8.1) feita depois da última reconexão, verificação cruzada fechando (3.2) e `PositionSelect` sem erro.
- **Resíduo real do robô r** = (líquida real − exposição externa) − Σ fichas pelos deals dos outros robôs.
- **Corte** = fim do pregão contínuo da data − 5 min (seção 12). Todas as estratégias estão zeradas até o corte.

## 0. O que é, em uma frase

Um EA único para o WIN que roda a lógica dos 5 robôs ao mesmo tempo, dá a cada um uma **ficha** (posição virtual própria) e envia à corretora as ordens de cada robô **com o magic do próprio robô**, de modo que a posição líquida da conta NETTING seja sempre a soma das fichas mais a exposição externa conhecida. Com um robô só ligado ele faz o que o WinSeletor fazia; com os cinco ligados cada robô opera como se estivesse sozinho numa conta própria. Roda em **uma instância só**, num único PC (Apêndice B, D3).

### Princípios (valem acima de qualquer detalhe abaixo)

1. **Cada robô decide sozinho, com as regras dele**, inclusive os níveis do próprio stop. O maestro não filtra, não combina, não prioriza sinais; executa, contabiliza e protege.
2. **A verdade sobre o que foi executado é a corretora.** Fichas saem do histórico de deals por magic (seção 3). A memória em disco guarda só o que a corretora não sabe: níveis e instantes de cada robô e o registro de ordens próprias (seção 9).
3. **Verificação antes de toda ordem** (Apêndice B, D1). Antes de enviar qualquer ordem, o maestro confere o estado real (líquida, ordens vivas, deals). Se algo aberto não é explicado pelas fichas confirmadas, ele consulta o histórico de deals e ordens e o próprio log até explicar, e só então envia. Nada é reenviado por inferência de tempo (seção 4.6).
4. **Proteção mora no servidor e segue a posição real.** Todo robô posicionado tem o stop dele como ordem stop pendente na corretora, com validade GTC (seção 4.3); volume real que nenhum stop cobre ganha um (seção 8.4). **Exceções conhecidas e aceitas** (a MT5 em netting não tem OCO nem OTO entre ordens independentes): (a) entre o preenchimento de uma entrada e o registro do stop dela, e durante todo o tempo em que o EA estiver fora do ar ou desconectado, a ficha recém-aberta fica sem stop no servidor; (b) com o EA fora do ar, uma ficha com stop e alvo vivos pode ter os dois executados e ficar com o sinal trocado, sem stop; (c) o CincoMedias não tem stop inicial pela regra dele e fica só com a reserva distante (Apêndice B.1). Pior caso na seção 13.4; decisão do dono no Apêndice B.7.
5. **A posição nunca perde o stop por causa de uma saída.** A S só é cancelada **depois** que a saída executou; saída recusada deixa a S intacta (seção 5.2). O risco residual (S e saída executando no mesmo instante) é corrigido pela 8.3 (B.12).
6. **Nenhum bloqueio impede saída por horário nem proteção.** Bloqueios e estados sem desfecho barram entradas e saídas por regra; stops, cancelamentos, saídas por horário e o corte sempre passam (seções 8.6, 12.3).
7. **Nada de trava não pedida.** Só existem as proteções técnicas desta especificação (consistência, margem que a corretora recusaria de qualquer forma, cadência de envio, corte de fim de dia).
8. **Proteção posta pelo dono nunca é apagada pelo robô** (seção 8.7).
9. **Tudo que o EA faz ou decide vira uma linha de log curta, com hora, robô, motivo e números** (seção 11), inclusive o que aconteceu com o EA fora do ar, com a hora real do deal.

## 1. Arquivos e nomes

| Item | Valor |
|---|---|
| EA | `mt5/WinMaestro.mq5` (+ `.ex5`, `_compile.log`) |
| Camada de corretora | `mt5/WinMaestro/Corretora.mqh`: única porta para `OrderSend`, `OrderDelete`, `OrderModify`, `PositionSelect`, `OrdersTotal`/`OrderGet*`, `HistorySelect`/`HistoryDeal*`/`HistoryOrder*`, `AccountInfo*`, `SymbolInfo*` de negociação. Duas implementações: real e falsa (seção 15.2) |
| Demais módulos | `mt5/WinMaestro/*.mqh`: `Fichas.mqh` (fichas, trânsito, execução, reconciliação), `Recupera.mqh` (10.2), `Memoria.mqh` (9), `Log.mqh` (11), `Grade.mqh` (12), um `.mqh` por robô (copiado do WinSeletor e adaptado conforme o Apêndice A) |
| Magics dos robôs | GapBarra1 80080601, CincoMedias 80080501, Desloc 80080101, Retângulo 20261005, Win_c1 80080002 |
| `MagicMaestro` | 80080900, constante: chave de pasta e de trava. Nenhuma ordem sai com ele |
| WinSeletor e EAs avulsos | aposentados (Apêndice B.4): `.mq5` do Seletor como `.bak` no repo; os `.ex5` do Seletor e dos avulsos saem da pasta Experts **e** de todo gráfico aberto antes da primeira partida do maestro |
| Grade de horários | `data/b3_grade_horaria_win.csv` embutida no código (`Grade.mqh`); atualizar a grade = recompilar |

## 2. Inputs e constantes

### 2.1 Inputs

Grupo **Maestro**, no topo da lista, por decisão explícita do dono (é ali que ele escolhe os robôs); os demais inputs novos vão no fim de cada grupo:

| Input | Padrão | Efeito |
|---|---|---|
| `Ativo_GapBarra1` … `Ativo_Win_c1` (5 bools) | todos `true` | Robô ligado gera entradas novas. Desligado: não abre nada novo; **se tiver ficha ou ordem viva, continua gerindo até zerar**. Nunca é fechado por ter sido desligado. |

Grupos dos robôs (`WinGapBarra1`, `WinCincoMedias`, …, prefixos `GB_`, `CM_`, `DM_`, `RE_`, `C1_`): como no WinSeletor, com quatro diferenças:
- os inputs de lote (`CM_Lote`, `DM_Lote`, `RE_Lote`, `C1_Lote`) saem: o lote é a constante 1 (todos os testes usam 1 contrato);
- `GB_ServerGMTOffsetH`, `GB_RegimeAutomatico` e `GB_FimContinuoMin` saem: fuso e fim do contínuo vêm da seção 12.1;
- `RE_LimiteEquity` sai: o `TesterStop` por equity do RE (L1007) é desligado, porque pararia o teste dos cinco pela equity da conta;
- acrescentam-se, no fim de cada grupo, `CM_ReservaPts` (padrão **4.945**, Apêndice B.1; 0 = sem reserva, aceito com AVISO no `PRONTO` de cada dia) e `DM_ReservaTicks` (padrão **20** = 100 pts, Apêndice B.5).

Os inputs de horário dos robôs continuam e alimentam a zeragem da seção 12.2 (sempre limitada ao corte) e os cortes de entrada de cada robô.

Mudar inputs reinicia o EA e passa pela recuperação completa (seção 10). O `OnInit` reinicializa explicitamente toda variável global do maestro e chama `Reseta()` de cada módulo, porque as variáveis globais podem sobreviver a `REASON_PARAMETERS` e `REASON_CHARTCHANGE` (a verificar, P17).

### 2.2 Constantes técnicas

| Constante | Valor | Seção |
|---|---|---|
| `LOTE` | 1 | 3.1 |
| `PRAZO_CONFIRMACAO` | 5 s (consulta a cada 250 ms) | 4.6, 5.1 |
| `CONEXAO_MIN` | 10 s de conexão contínua | convenções |
| `ALERTA_SEM_DESFECHO` | 30 s | 4.6 |
| `PRAZO_SEM_DESFECHO` | 10 min | 4.6 |
| `PRAZO_SEM_STOP` | 2 s | 8.4 |
| `COBERTURA_MIN` | 5 s | 8.4 |
| `IDADE_MIN_ORFA` | 5 s | 8.5 |
| `DIVERGENCIA_MIN` | 3 s e 3 leituras | 8.2 |
| `CRUZADA_MAX` | 60 s | 8.2 |
| `PRAZO_HISTORICO_R4` | 60 s | 10.2 |
| `MARGEM_CORTE` | 5 min antes do fim do contínuo | 12 |
| `TETO_ENTRADAS_MIN` | 20 entradas por minuto, somando os robôs | 4.8 |
| `DISJUNTOR_ENVIOS_MIN` | 100 envios por minuto | 4.8 |
| `ESPERA_RECUSA` | 1, 2, 4, 8, 16 s e depois 30 s | 4.8 |
| `STOP_EMERGENCIA_PTS` | 1.200 | 8.4, 10.3 |
| `CORRECAO_INTERVALO` | 1 correção por ficha a cada 10 min | 8.3 |
| `SALTO_SALDO_MAX` | 50% | 13.1 |
| `PUSH_INTERVALO` | 1 push a cada 10 s; mesmo evento e objeto no máximo 1 a cada 5 min | 11.2 |
| `DM_CAPITAL_ROBO` | R$1.000 | 13.3 |

## 3. A ficha

### 3.1 Cálculo

Uma função só (`Ficha_Recalcula`), chamada pelo evento (`OnTradeTransaction`) e pela reconciliação, para os dois caminhos nunca divergirem.

| Campo | Cálculo |
|---|---|
| ficha pelos deals (+ compra / − venda) | Σ do volume assinado dos deals `DEAL_TYPE_BUY`/`SELL` do símbolo com `DEAL_MAGIC` do robô dentro da janela (3.2), mais os volumes absorvidos de intervenção externa (8.9) |
| volume sem desfecho | Σ do volume assinado das ordens do robô sem desfecho **que executam no envio**: entrada a mercado (C1), saída X e correção C. **Entrada limite contribui 0 em qualquer estado**; S e A contribuem 0 |
| **ficha efetiva** | ficha pelos deals + volume sem desfecho. É o que os módulos enxergam (`Ficha_Tem`, `Ficha_Lado`) |
| preço médio | média ponderada dos deals que afastam a ficha de zero, desde o último zero da ficha |
| hora de abertura | `DEAL_TIME_MSC` do primeiro deal da ficha atual |
| resultado realizado | Σ, para cada deal que aproxima a ficha de zero, (preço do deal − preço médio) × volume × lado × valor do ponto lido do símbolo, menos `DEAL_COMMISSION` e `DEAL_FEE` |

Regras:
- `DEAL_ENTRY` e `DEAL_PROFIT` não entram na ficha: em netting descrevem a líquida. `DEAL_PROFIT` só aparece na conferência do resumo do dia (11.5).
- Deals `BALANCE`, `CREDIT`, `CHARGE`, `CORRECTION` e variação de margem (`DEAL_REASON_VMARGIN`) não entram no volume; cada um é logado uma vez (`AJUSTE`).
- Estados válidos da ficha pelos deals: 0 ou ±1. **Ficha duplicada** (|ficha| = 2, entrada executada duas vezes) e **ficha trocada** (sinal oposto ao do deal de abertura do ciclo atual: duas saídas da mesma ficha) são detectadas aqui, exigindo só a verificação cruzada fechando, e tratadas só pela 8.3. O módulo nunca as vê (`Ficha_Tem` = falso, módulo suspenso até a ficha voltar a 0 ou a ±1).
- Ficha cujo deal de abertura é anterior ao início do pregão de hoje é **ficha de pregão anterior** (12.4).

### 3.2 Janela de reconstrução e verificação cruzada

O histórico é lido desde o **último instante em que a líquida do símbolo foi zero**:
1. Início: `negociacao_inicio` de hoje − 10 min.
2. `S` = Σ do volume assinado de todos os deals BUY/SELL do símbolo, de todos os magics, desde o início.
3. `S` ≠ líquida real → recua um pregão e repete, até 10 pregões.

**Verificação cruzada** = `S` da janela vigente igual à líquida real. A API não tem indicador de "histórico carregado"; esta conta é o indicador. Se ela não fecha em 10 pregões, vale o prazo de R4 (10.2): a diferença vira **exposição externa de origem desconhecida**, gravada na memória, que só muda por deal novo; daí em diante a verificação cruzada é `S + externa de origem desconhecida = líquida real`.

### 3.3 Papel das ordens e invariantes

O papel de uma ordem é identificado por **(magic, tipo, lado em relação à ficha pelos deals)**. O comentário (4.2) é conferência, não fonte (a corretora pode trocá-lo, P3).

| Ordem viva do magic do robô | Ficha pelos deals | Papel |
|---|---|---|
| stop do lado oposto à ficha | ≠ 0 | S |
| limite do lado oposto à ficha | ≠ 0 | A ou X-limite (5.4); contam juntas como "saídas limite" |
| limite de qualquer lado | 0 | E |
| limite do mesmo lado da ficha | ≠ 0 | E fora de lugar (robôs não piramidam) |
| stop do mesmo lado da ficha, ou stop com ficha 0 | qualquer | órfã |

Invariantes conferidos a cada reconciliação, por robô: (1) no máximo uma S, volume 1, lado oposto; (2) no máximo uma saída limite; (3) nenhuma S ou saída limite com ficha 0; (4) nenhuma E com ficha ≠ 0 e no máximo uma E com ficha 0.

Violação: cancela o excedente pelo protocolo 5.1 (a mais nova primeiro; entre duas S fica a de nível mais protetor) e loga ALERTA `INVARIANTE`, sempre sob as condições de 8.5. Tickets na memória são pista; se o `OrderModify` trocar o ticket (P4), o papel continua reconhecido.

### 3.4 Interface com os módulos

Os módulos não tocam em `Position*`, `Order*`, `History*`, `trade.*`. Cada chamada vira uma função da camada, que devolve os dados explicitamente:

| Hoje no módulo | No maestro |
|---|---|
| `PositionSelect(_Symbol)` + magic | `Ficha_Tem(robo)` (ficha efetiva ≠ 0, nem trocada nem duplicada) |
| "tem posição de outro robô, não entro" (CM L774, DM L379, C1 L620) | removido |
| `POSITION_PRICE_OPEN/TYPE/TIME/VOLUME` | `Ficha_Preco`, `Ficha_Lado`, `Ficha_Hora`, `Ficha_Volume` |
| `POSITION_SL` | `Ficha_Stop(robo)` = **nível pedido pelo próprio robô** (0 se ele não pediu). A reserva do CM e do DM nunca aparece aqui, para a lógica do robô ficar igual à do avulso |
| `POSITION_COMMENT`, `HistorySelectByPosition` | `Ficha_Marca(robo)` (4.2) |
| `PositionClose` | `Ficha_Fecha(robo, motivo)`: protocolo 5.2, volume da ficha pelos deals, magic do robô |
| `PositionModify(sl)` | `Ficha_DefineStop(robo, nivel, motivo)` (4.7) |
| `trade.Buy/Sell` com SL | `Ficha_EntraMercado(robo, lado, stop, motivo)` |
| `BuyLimit/SellLimit` de entrada | `Ficha_EntraLimite(robo, lado, preco, stop, alvo, validade, expira, motivo)` |
| `BuyLimit/SellLimit` e `OrderModify` de alvo | `Ficha_DefineAlvo(robo, nivel, motivo)` |
| `OrderDelete` | `Ficha_CancelaOrdem(robo, papel, motivo)` |
| `OrdemPendente()`, `OrderSelect(g_ordem)` | `Ficha_Entrada(robo)` → {existe, lado, preço, hora de envio} |

Toda função de envio devolve `ENVIADA`, `RECUSADA` (retcode), `BLOQUEADA` (motivo, inclusive "estado aberto", 4.6) ou `JA_EM_TRANSITO`. O módulo trata `RECUSADA` e `BLOQUEADA` como hoje trata falha de `OrderSend` (item 4.33).

**Avisos ao módulo:** callback único `Robo_Evento(robo, evento, dados)`:

| Evento | Quando |
|---|---|
| `ENTRADA_CANCELADA` | a E do robô sumiu sem deal: cancelada pelo maestro (bloqueio 8.6, autonegociação 4.9, corte, `OnDeinit`), pelo dono, pela corretora, ou por validade vencida |
| `EXECUTOU_ANTES` | o cancelamento pedido pelo robô perdeu a corrida (5.1) |
| `ENTRADA_REENVIAVEL` | na recuperação, a decisão de entrada do robô ainda pode ser executada (10.4) |

**O maestro nunca reenvia uma E por conta própria.** Quem decide reenviar é o módulo, pela regra dele; o que cada robô faz com cada evento está no Apêndice A (padrão: não rearmar, que é o comportamento do avulso). S, X, C e cancelamentos são retentados só pelo maestro.

## 4. Execução

### 4.1 Tipos, validade e preenchimento

| Situação | Ordem real | Validade |
|---|---|---|
| Entrada a mercado (só C1) | mercado, magic do robô | — |
| Entrada limite | limite, magic do robô | GB `SPECIFIED` (abertura + `TtlBarras`×5 min; se a corretora recusar, DAY com cancelamento pelo EA em `g_exp`, como no avulso); CM, DM, RE DAY (Apêndice B.3) |
| Stop (S) | `SELL_STOP` para ficha comprada, `BUY_STOP` para vendida, volume 1 | **GTC** (Apêndice B.6) |
| Alvo (A) | limite oposta, volume 1 | DAY |
| Saída por regra, zeragem, correção (X, C) | mercado oposta, volume da ficha pelos deals, pelo protocolo 5.2 | — |
| Saída agressiva (5.4) | limite oposta agressiva | DAY |

Preenchimento: limite com `ORDER_FILLING_RETURN` e desvio 0; mercado com `RETURN` se `SYMBOL_FILLING_MODE` permitir, senão `IOC` (a verificar, P15). Stop-limit no lugar de stop e `SPECIFIED` no lugar de GTC para a S são implementados **só se P1/P15 mostrarem que a Rico não aceita** `*_STOP` ou GTC no WIN; nesse caso a S `SPECIFIED` vale até o fim do contínuo do pregão seguinte e o timer a renova na virada de cada pregão.

### 4.2 Comentário

`MAE|<robo>|<papel>|<seq>[|<marca>]` — `robo` = GB, CM, DM, RE, C1; `papel` = E, S, A, X, C; `seq` = 5 dígitos por robô, um por ordem, persistido no estado permanente (9.1), volta a 00001 depois de 99999; `marca` = 1 caractere do robô (CM: `F` a favor do mês, `N` neutra). Exemplo: `MAE|CM|E|00042|F` (16 caracteres). Busca pelo comentário sempre restrita às ordens com `ORDER_TIME_SETUP` desde o início da janela (3.2), para a volta do `seq` não colidir. Limite de comprimento e preservação pela corretora: a verificar (P3).

### 4.3 Stop no servidor

O SL/TP da posição líquida não é usado (vale para a soma). Cada robô posicionado tem a sua S.

- **Quando nasce: só com deal.** Entrada limite: na mesma chamada em que o deal de entrada é visto (`OnTradeTransaction` ou reconciliação). Entrada a mercado (C1): na mesma execução de `Ficha_EntraMercado`, logo depois do retorno do `OrderSend` com `deal ≠ 0`; sem deal no retorno, quando o desfecho aparecer (4.6). O atraso deal→S aceita é logado em toda abertura.
- **GB, RE, C1:** S no nível pedido pelo robô.
- **CM:** S de reserva a `CM_ReservaPts` do preço da ficha desde o preenchimento (B.1). Quando o "stop que aperta" nasce, a mesma S é movida para o nível dele. Com `CM_ReservaPts = 0` e sem stop que aperta, o CM fica sem S (exceção c).
- **DM:** stop controlado pelo EA + S de reserva `DM_ReservaTicks` além (5.5).
- **GTC** (B.6): ficha que atravessa a noite porque o EA estava fora no corte continua protegida. O risco oposto (S órfã sobreviver) é coberto pelo passo R7 da recuperação, que cancela órfãs antes de qualquer outra ordem, e pela reconciliação (8.5).
- Onde a S mora (servidor da Rico ou B3) e o que vira ao disparar em leilão ou banda: a verificar (P1, P13); o caso "disparou e não executou" está em 5.4.

### 4.4 Atribuição dos deals e ordens próprias

**Ordem própria** = ticket no **registro de ordens próprias** (9.2), que guarda cada ordem enviada enquanto ela, ou a ficha que ela abriu, existir, atravessando pregões; ou, com a memória perdida, comentário com prefixo `MAE|`.

| Deal ou ordem do símbolo | Tratamento |
|---|---|
| magic de robô, própria | ficha do robô |
| magic de robô, fora do registro e sem prefixo `MAE|`, criada (`ORDER_TIME_SETUP_MSC`) depois do primeiro heartbeat desta instância | **EA avulso esquecido** com magic de robô: bloqueio de entradas que exige o dono (8.6), ALERTA com push; os deals entram na ficha do robô (a posição na corretora é uma só) |
| magic de robô, fora do registro, anterior ao primeiro heartbeat | ficha do robô, AVISO `ORIGEM NAO CONFIRMADA` |
| outro magic (0 = manual, outros EAs) ou `DEAL_REASON` em {`CLIENT`, `MOBILE`, `WEB`, `SO`} sem magic de robô | deal externo, 8.9 |

Não existe ficha sem dono: toda ordem do maestro leva o magic de um robô.

### 4.5 Ordem de processamento

Num mesmo ciclo: primeiro cancelamentos e saídas, na ordem fixa GB, CM, DM, RE, C1; depois as entradas, na mesma ordem. Envios seriais: o próximo só sai depois do retorno do anterior; dentro de um robô, S antes de A. Diferença conhecida em relação ao avulso: em hora cheia a última entrada da fila sai centésimos de segundo depois da primeira e o GB tem prioridade de fila sistemática (relatório 15.1).

### 4.6 Verificação antes de toda ordem e ordens sem desfecho

**Registro de trânsito.** Toda ordem (inclusive S e cancelamentos) entra no registro antes do `OrderSend`: robô, papel, `seq`, comentário, volume que altera a ficha (só E a mercado, X, C), ticket e `request_id` (preenchidos no retorno, podem ficar 0), hora de envio. O registro é gravado na memória antes do envio (9.3) e cada envio vira uma linha `ORDEM` no log (11.2).

**Estado fechado** = leitura confiável; líquida real − exposição externa = Σ fichas pelos deals; nenhuma ordem própria sem desfecho; ordens vivas de acordo com os papéis (3.3). Fichas trocadas e duplicadas contam como explicadas (a 8.3 as trata).

**Antes de enviar qualquer ordem** (E, X, S, A, C), o maestro confere o estado. Fechado → envia. Aberto → não envia e tenta explicar o que está aberto, nesta ordem:
1. releitura completa do histórico de deals e de ordens (8.1);
2. busca de cada ordem sem desfecho por ticket, `request_id` (`TRADE_TRANSACTION_REQUEST`) e comentário nas pendentes e no histórico;
3. com a memória perdida, leitura do log do dia (`logs/AAAA-MM-DD.log`, linhas `ORDEM`) para saber o que foi enviado e procurar pelo comentário.

Enquanto o estado está aberto, só passam: **S** (pela 8.4, que segue a posição real), **cancelamentos**, as **saídas por horário e o corte** (pela 12.3, com volume pelo resíduo real) e a **correção** de ficha trocada ou duplicada. Entradas, alvos e saídas por regra voltam `BLOQUEADA estado aberto` e esperam.

**Desfecho de uma ordem.** `DONE`/`PLACED` sem deal, `OrderSend` falso e retcode de transporte com ticket 0 são **"não sei"**, nunca "não executou" (itens 1.6, 1.17, 1.24). O desfecho é procurado a cada 250 ms por `PRAZO_CONFIRMACAO` (5 s) e depois a cada reconciliação. Uma ordem só se resolve por prova:

| Desfecho | Prova |
|---|---|
| executada | deal(s) com `DEAL_ORDER` = ticket; ou, em leitura confiável, resíduo real do robô diferente da ficha pelos deals exatamente pelo volume e lado da ordem, sem outra ordem do robô que explique |
| viva | listada nas pendentes (E, S, A): passa a ser reconhecida pelo papel (3.3) |
| não executada | ordem no histórico com `CANCELED`, `REJECTED` ou `EXPIRED`; ou, em leitura confiável, ordem que não está nas pendentes e resíduo real do robô igual à ficha pelos deals (a posição prova que ela não mexeu na conta) |

Não existe resolução por prazo. Sem prova, a ordem fica **sem desfecho**: ALERTA após `ALERTA_SEM_DESFECHO` (30 s); depois de `PRAZO_SEM_DESFECHO` (10 min), bloqueio de entradas que exige o dono e push a cada 5 min. Nesse tempo a posição está protegida pela 8.4 e as saídas por horário e o corte funcionam pela 12.3. Uma S sem desfecho conta como cobertura na 8.4 enquanto o estado for de leitura confiável; a S seguinte do mesmo robô só sai quando ela se resolver.

O log registra quanto tempo cada ordem ficou sem desfecho e qual prova a resolveu.

### 4.7 Mover o stop

1. Mover = `OrderModify` da S existente; nunca cancelar e recriar.
2. **O nível é o que o robô pede.** Se a regra do robô afrouxa o stop (trailing do C1, que segue `wma ± K×ATR` nos dois sentidos), o maestro afrouxa igual. "Nunca afrouxa" vale só para as ações do próprio maestro (recriação de 8.4, recuperação, correção): nelas o nível nunca é menos protetor que o último registrado (item 1.10).
3. **Nível atravessado** é checado pelo módulo, com a fonte de preço dele no avulso (C1 e CM: bid na compra, ask na venda, 1 tick; DM: last, com bid/ask quando last = 0). O maestro, nas ações próprias, usa last com o mesmo fallback do DM, mais o piso `max(1 tick, SYMBOL_TRADE_STOPS_LEVEL)` (itens 1.25, 4.30).
4. Nível atravessado → saída pelo protocolo 5.2 (a S antiga continua viva até a saída executar).
5. `OrderModify` recusado: a S antiga continua viva, o log registra, e a retentativa segue 4.8. Nível 0 vindo de um módulo é ignorado com ERRO, nunca apaga a S.

### 4.8 Retentativas e teto de envios

- S, X, C e cancelamentos recusados: retentados pelo maestro com `ESPERA_RECUSA` (1, 2, 4, 8, 16 s, depois 30 s); após 5 recusas seguidas, ALERTA com push, repetido a cada 5 min enquanto durar (item 1.13).
- E recusada ou bloqueada: volta ao módulo (3.4), que decide pela regra dele. O maestro não retenta E.
- Teto: no máximo `TETO_ENTRADAS_MIN` (20) E por minuto; a excedente volta `BLOQUEADA cadencia` (item 1.20).
- Disjuntor: mais de `DISJUNTOR_ENVIOS_MIN` (100) envios de qualquer papel em um minuto → E e A bloqueadas por 5 min, ALERTA (item 1.22).
- S, X, C e cancelamentos nunca são barrados pelo teto nem pelo disjuntor; eles contam no contador para o disjuntor enxergar um laço.

### 4.9 Autonegociação

1. E ou A que possa cruzar com ordem própria viva do lado oposto (compra ≥ venda própria, venda ≤ compra própria) não é enviada: `BLOQUEADA autonegociacao` (E volta ao módulo; A é retentada pelo maestro com 4.8).
2. Saídas, stops, zeragens e correções nunca são bloqueados. Se uma saída a mercado puder cruzar com limite própria do lado oposto (compra a mercado com venda própria ≤ melhor oferta; venda com compra própria ≥ melhor demanda), o maestro **cancela primeiro a limite do outro robô** (5.1), avisa o dono dela (`ENTRADA_CANCELADA` para E; A é recriada pelo maestro depois) e envia a saída. Log `AUTONEG`.
3. Stop disparado no servidor não pode ser prevenido. Deal de compra e de venda próprios no mesmo preço e segundo → ALERTA `AUTONEG`.
4. S ou A cancelada ou recusada sem pedido do maestro é evento crítico: ficha posicionada → S recriada na hora; preço já além do nível → 5.4.
5. Self-Trade Prevention na Rico/B3: a verificar (P12). No Testador não há autonegociação (o Testador não casa ordens do mesmo EA entre si).

## 5. Cancelamento, saída e OCO

### 5.1 Cancelamento confirmado

Cancelamento confirmado = ordem no **histórico** com `CANCELED` ou `EXPIRED`; o retcode do `OrderDelete` não basta (item 1.5). Logo após o `OrderDelete`, o histórico é consultado **na mesma chamada** (no Testador o desfecho está sempre lá); sem desfecho, segue a 4.6. Desfecho `FILLED`/`PARTIAL` → quem pediu é avisado (`EXECUTOU_ANTES`). Sem desfecho, a ordem segue tratada como viva (invariante e margem). O tempo até a confirmação é logado (P5).

### 5.2 Saída a mercado

Vale para toda saída a mercado: regra do robô, stop do EA do DM, nível atravessado, zeragem, corte, pregão anterior e correção. Só dentro do contínuo (12.4).

1. Cancela, em série, A e X-limite do robô (5.1). **A S fica viva.**
2. Algum `FILLED` → não envia; recalcula. Algum sem desfecho → não envia; repete a cada 5 s.
3. Envia a mercado, lado oposto, volume = |ficha pelos deals| (saídas por horário e corte com ordem do robô sem desfecho: volume da 12.3), no mesmo tick se as confirmações vieram na mesma chamada.
4. **Saída executada (deal visto) → cancela a S** (5.1). Se a S executou antes do cancelamento, a ficha fica trocada e a 8.3 corrige.
5. **Saída recusada → a S continua**; fora de leilão segue 5.4; em leilão nada mais é enviado.

Risco residual aceito (B.12): entre o deal da saída e o cancelamento da S, uma S no nível do preço pode executar também; com 1 contrato, o resultado é ficha trocada de volume 1, corrigida pela 8.3 (item 1.23). No Testador o atraso desta sequência é zero: saída em tick diferente do avulso é defeito (15.1).

### 5.3 OCO

1. Deal de S ou A levando a ficha a zero → cancela as ordens restantes do robô (5.1) antes de qualquer outra ação do ciclo.
2. Com o EA fora do ar não há OCO (Princípio 4b). O RE é o único robô com alvo no padrão; é decisão consciente do dono (B.9).
3. Na recuperação, as irmãs são canceladas no R7 e a ficha trocada é tratada no R10 (8.3).

### 5.4 Stop disparado sem execução e saída recusada

**Detecção:** S que sai das pendentes sem deal com `DEAL_ORDER` = ticket em 2 s, com estado `REJECTED`/`CANCELED` sem pedido do maestro; ou saída X/C recusada pela corretora.

**Ação:** ALERTA com push e, dentro do contínuo e fora de leilão, saída por **limite agressiva** a último ∓ 3 ticks, dentro da banda, **sem cancelar a S**; reenviada a cada 5 s (a limite anterior cancelada pela 5.1 antes de cada reenvio), no máximo 6 por minuto, ALERTA a cada 3 min sem preenchimento. Em leilão (fase da grade; leilão por variação detectado pela recusa) nada é enviado além da S. As tentativas contam no disjuntor. Limite agressiva e S executando juntas → ficha trocada → 8.3.

**Prioridade:** 8.4 vem antes de 5.4. A 5.4 nunca cancela S. As únicas rotinas que cancelam a S de uma ficha aberta são: 5.2 passo 4 (depois da saída executada), invariante 1 (S em excesso) e 8.4 nível 2 (cobertura em excesso).

### 5.5 DM: stop do EA e reserva no servidor

- **Stop do EA** (fiel ao testado): quando o preço (last; bid/ask se last = 0) cruza `g_stopNivel`, o módulo pede `Ficha_Fecha` e o maestro executa 5.2 (a reserva é cancelada depois da saída executada).
- **Reserva**: S a `DM_ReservaTicks` (20 ticks = 100 pts) **além** de `g_stopNivel`. Os dois caminhos nunca ficam no mesmo nível (itens 1.4, 1.23). Ela só dispara se o EA não agiu ou se o preço saltou mais de 100 pts num só negócio. Custo com o EA fora: até R$20 por contrato além do stop testado.
- **No Testador a reserva existe.** O Testador executa as pendentes antes do `OnTick`; a reserva só executa num tick que atravessa `g_stopNivel` e a reserva de uma vez, e nesse tick o avulso sairia ao preço do mesmo tick. Esperado: mesmo preço de saída, caminho S em vez de X. O relatório 15.1 lista esses trades; diferença de preço neles é defeito.

## 6. Estado do ciclo de cada robô

O estado **não é armazenado**: é derivado a cada reconciliação de (ficha pelos deals, ordens vivas por papel, registro de trânsito, protocolo em curso). A memória guarda só níveis e instantes. Função de derivação, na ordem de precedência:

| Condição | Estado |
|---|---|
| ficha trocada | `TROCADA` (8.3) |
| |ficha pelos deals| = 2 | `DUPLICADA` (8.3) |
| ficha de pregão anterior | `PREGAO_ANTERIOR` (12.4) |
| ordem do robô sem desfecho | `SEM_DESFECHO` (4.6) |
| saída recusada, 5.4 em curso | `SAIDA_RECUSADA` |
| protocolo 5.2 em curso | `SAINDO` |
| ficha ≠ 0 sem S viva | `POSICIONADO_SEM_STOP` (ALERTA após `PRAZO_SEM_STOP`, 8.4) |
| ficha ≠ 0 com S viva | `POSICIONADO` |
| ficha 0 com E sem desfecho | `ENTRADA_ENVIANDO` |
| ficha 0 com E viva | `ENTRADA_PENDENTE` |
| ficha 0, nada vivo | `LIVRE` |

Cada mudança do estado derivado gera uma linha de log.

## 7. Eventos do MT5

| Evento | Real | Testador |
|---|---|---|
| `OnInit` | Reinicializa toda variável global (`g_iniciou` = falso), `Reseta()` dos módulos, liga o timer, recuperação em R0, devolve `INIT_SUCCEEDED`. Não espera conexão, não lê histórico, não envia ordem | igual |
| `OnTimer` | 250 ms: máquina da recuperação, consultas de desfecho e cancelamento. A cada 1 s: reconciliação, horários e corte (12), heartbeat da trava, gravação acumulada. A cada 60 s: varredura de outros símbolos (8.8) | 1 s, só horários e corte |
| `OnTick` | marca a reconciliação "suja"; em `PRONTO`, **de `negociacao_inicio` até o corte**, `Tick()` de cada robô ligado ou com ficha/ordem viva, na ordem 4.5; nunca para robô com ficha de pregão anterior, trocada ou duplicada | igual, mais reconciliação a cada M1 nova |
| `OnTradeTransaction` | linha bruta no log de transações; deal novo → `Ficha_Recalcula`, OCO, desfechos, memória; ordem cancelada/rejeitada → desfecho e aviso ao módulo; deal com hora anterior ao último instante processado → releitura completa (8.1) | igual (é o caminho principal) |
| `OnChartEvent` | botão de desbloqueio (8.6) | — |
| `OnDeinit` | Loga `FIM` e o `reason`. **Com `g_iniciou` falsa** (instância recusada no R1): só isso. Com `g_iniciou` verdadeira: se `reason` ∉ {`PARAMETERS`, `CHARTCHANGE`, `TEMPLATE`}, envia o cancelamento das E próprias, sem esperar confirmação (a recuperação confere; P24); nunca cancela S nem A, nunca fecha posição; grava memória; libera a trava | grava log |

`OnTradeTransaction` não é garantido; a reconciliação é o caminho seguro. O cancelamento de E no `OnDeinit` não cobre queda de energia, processo morto nem internet caída (Princípio 4a).

## 8. Reconciliação contínua

### 8.1 Cadência

- Recálculo no máximo 1× por segundo, mais um imediato a cada deal. Incremental: `HistorySelect(último instante − 60 s, agora)`, deduplicando por ticket de deal.
- **Releitura completa da janela** (3.2) imediatamente em: `TERMINAL_CONNECTED` falso→verdadeiro; verificação cruzada sem fechar; deal recebido com hora anterior ao último instante processado; estado aberto antes de um envio (4.6). Fora isso, a cada 10 min.
- Nenhum módulo chama `HistorySelect*`.

A cada reconciliação: lê a líquida real (`PositionSelect` falso com erro é leitura descartada, item 1.6); recalcula fichas e desfechos; confere invariantes (3.3); aplica a 8.4; loga a margem para diagnóstico (13.2).

### 8.2 Confirmação de divergência

Uma diferença só é **divergência confirmada** quando, ao mesmo tempo: persiste por ≥ 3 s e em ≥ 3 leituras com histórico refeito; nenhuma ordem sem desfecho a explica em quantidade e lado (lado nunca é explicado por ordem em trânsito, item 1.25); e a verificação cruzada fecha.

- Divergência confirmada → bloqueio de entradas (8.6) e ALERTA. Correção só para ficha trocada ou duplicada (8.3); qualquer outra fica bloqueada até o dono (item 1.7).
- **Verificação cruzada sem fechar por mais de `CRUZADA_MAX` (60 s)** → bloqueio de entradas (do tipo que sai sozinho, com E canceladas) e ALERTA repetido a cada 5 min; releitura completa a cada 10 s; nenhuma correção.

### 8.3 Ficha trocada e ficha duplicada (únicas correções automáticas)

**Ficha trocada** (duas saídas da mesma ficha: S + A, S + X, A + X, X duplicada; ficha de ±1 para ∓1): módulo suspenso; correção pelo protocolo 5.2 com o **magic do robô** e papel C, levando a ficha a 0.

**Ficha duplicada** (|ficha| = 2, entrada executada duas vezes): correção C de volume 1 a mercado, com o magic do robô, **sem cancelar a S**: a S tem volume 1 e passa a cobrir a ficha exata; se a S executar junto, a ficha vai a 0, nunca inverte. Bloqueio de entradas que exige o dono.

Para as duas: só dentro do contínuo (fora dele, agendada para `negociacao_inicio`); no máximo uma correção por ficha a cada 10 min; a segunda no prazo vira bloqueio que exige o dono, sem correção (item 1.13); ALERTA com push e os tickets envolvidos.

### 8.4 Proteção pela posição real

Roda em toda reconciliação, em qualquer modo (inclusive `PROTEGENDO`, bloqueios e estado aberto), e tem prioridade sobre 5.4 e sobre qualquer saída em curso.

**Nível 1, por robô.** Ficha pelos deals = ±1 (não trocada), sem S viva e sem S sem desfecho há mais de `PRAZO_SEM_STOP` (2 s), com resíduo real do robô do mesmo sinal da ficha → recria a S: nível da memória; sem ele, regra do robô (Apêndice A); sem regra, `STOP_EMERGENCIA_PTS` do preço da ficha (ALERTA). Nível já atravessado → 4.7 item 4. Entrada limite viva não gera S: a S só nasce com deal. Recusas seguem 4.8.

**Nível 2, pela conta.** Só quando o nível 1 não tem nada pendente, nenhuma S foi enviada nos últimos 5 s, há leitura confiável, e a diferença persiste por `COBERTURA_MIN` (5 s):
- necessidade N = líquida real − exposição externa − Σ fichas que estão sem S por regra (CM com `CM_ReservaPts = 0` antes do stop que aperta);
- cobertura K = Σ das S vivas de magic de robô e das S sem desfecho, cada uma com o sinal da posição que protege (`SELL_STOP` = +1);
- **N − K com o sinal de uma posição sem stop** → cria uma S de volume |N − K|, atribuída ao **robô suspeito** (o que tem ordem sem desfecho cujo efeito explica a diferença; sem ele, o último robô com deal naquele lado), no nível da memória dele ou a `STOP_EMERGENCIA_PTS` do preço; log `COBERTURA criada` com N, K e o motivo da atribuição;
- **cobertura em excesso** (S protegendo volume que não existe, ex.: saída executada sem deal visível) → cancela (5.1) o excesso, começando pela S do robô suspeito; log `COBERTURA excesso`.

A regra decide pela posição real; não depende de saber se uma ordem sem desfecho executou.

### 8.5 Ordem órfã

Ordem com magic de robô é órfã (sem papel válido por 3.3) só se: não tem ordem sem desfecho do robô; tem mais de `IDADE_MIN_ORFA` (5 s) de vida; e a verificação cruzada fecha. Ação: cancela (5.1), loga `ORFA`. Ordem de magic desconhecido: não toca, loga uma vez.

### 8.6 Bloqueio de entradas e botão

Há um tipo só de bloqueio: **de entradas** (E; com disjuntor, também A).

| Causa | Como sai |
|---|---|
| divergência confirmada, cruzada sem fechar (8.2) | sozinho, quando a causa some |
| `PROTEGENDO` por falha de R3 (10.2) | sozinho |
| ordem sem desfecho há mais de 10 min (4.6), ficha duplicada, correção repetida (8.3), intervenção externa redutora (8.9), SL/TP na líquida (8.7), ordem em outro símbolo (8.8), EA avulso (4.4), `PROTEGENDO` causado pelo prazo de R4 (10.2) | **pelo botão** (exige o dono) |

**Nunca são barrados:** S (criar, mover, recriar), cancelamentos, saída agressiva (5.4), saídas por horário, corte e as correções da 8.3 (dentro dos limites dela). Saídas por regra dos robôs continuam funcionando durante o bloqueio.

Ao entrar em qualquer bloqueio: todas as E próprias são canceladas (5.1) e os módulos recebem `ENTRADA_CANCELADA` (item 1.9); log ALERTA uma vez, com a causa.

**Botão no gráfico** (`OBJ_BUTTON` "Desbloquear", visível só com bloqueio que exige o dono; confirmação por dois cliques em até 3 s; tratado em `OnChartEvent`): grava o evento causador (ticket do deal ou da ordem) como **reconhecido** no estado permanente (9.1), libera o bloqueio sem reiniciar o EA e loga `DESBLOQUEIO` com os tickets. A recuperação só reativa bloqueio de evento não reconhecido. Depois do desbloqueio nenhum robô reenvia entrada cancelada (padrão do Apêndice A).

### 8.7 SL/TP na posição líquida

O maestro nunca põe SL/TP na líquida. Encontrou: **não remove** (foi um stop anexado à mão que encerrou o incidente de 2026-08-28, Parte 0); bloqueio que exige o dono; ALERTA com push. Se esse SL/TP executar, o deal é intervenção externa redutora (8.9).

### 8.8 Ordens e posições em outros símbolos

No R3 e a cada 60 s: varre posições e ordens de todos os símbolos com magic de robô. Fora do símbolo do gráfico (ex.: contrato velho): bloqueio que exige o dono, ALERTA. O maestro não mexe no outro símbolo.

### 8.9 Intervenção externa

Deal externo (4.4) é classificado no instante em que é visto, nesta ordem:
1. **Compensa a exposição externa existente** de sinal oposto (o dono fechando a posição manual dele). Essa parte só altera a externa, sem bloqueio.
2. O que sobrar e **aumentar** |líquida| → exposição externa (ALERTA uma vez por mudança); as fichas seguem; a externa entra no cálculo de margem.
3. O que sobrar e **reduzir** |líquida| abaixo de Σ fichas → **intervenção externa redutora** (zeragem manual, mesa da corretora, zeragem compulsória P11, stop-out `DEAL_REASON_SO`, SL/TP do dono):
   - absorção nas fichas do lado reduzido, na ordem fixa GB, CM, DM, RE, C1 (B.8); cada ficha absorvida vai a 0 com o preço do deal externo, log `ABSORVIDA`. A absorção é função determinística do histórico: a recuperação sem memória chega ao mesmo resultado;
   - cancelamento imediato (5.1), primeiro das S e A das fichas absorvidas (viram entradas nuas), depois de todas as E próprias;
   - bloqueio que exige o dono; ALERTA com push.

## 9. Memória

### 9.1 Onde

- **Estado de pregão**: `MQL5/Files/WinMaestro/<servidor>_<conta>_<símbolo>/estado.txt` (+ `.bak`, `.tmp`) e `logs/`.
- **Estado permanente**: `MQL5/Files/Common/WinMaestro/permanente/<servidor>_<conta>.txt` (`FILE_COMMON`, não depende do símbolo, sobrevive à rolagem): `seq` de cada robô, resultado acumulado do DM (13.3), tickets de eventos reconhecidos pelo botão (8.6).
- **Testador**: tudo em `MQL5/Files/WinMaestro_teste/` do agente, **nunca** em `FILE_COMMON` (no Testador `FILE_COMMON` é a pasta comum real da máquina). Apagado no início de cada teste.

### 9.2 O que guarda

Formato `chave=valor`, legível no Bloco de Notas.
- Cabeçalho: versão do formato e do EA, servidor, conta, símbolo, data do pregão, último ticket de deal e último instante processados, heartbeat (`TimeTradeServer` e `TimeLocal`), hora do primeiro heartbeat desta instância.
- Registro de trânsito (4.6).
- **Registro de ordens próprias** (4.4): ticket, comentário, papel, robô, hora. Uma ordem sai do registro quando ela está fechada **e** a ficha que ela abriu voltou a 0. Atravessa pregões.
- Bloqueios ativos com o evento causador; exposição externa de origem desconhecida (3.2).
- Por robô: níveis de stop e alvo pedidos, marca da entrada e as variáveis do Apêndice A. **Instantes, nunca contagens.**

### 9.3 Quando grava

Na hora: antes de cada `OrderSend`, a cada deal, a cada mudança de nível de stop ou alvo, a cada bloqueio e desbloqueio, no `OnDeinit` (só com `g_iniciou`). Demais mudanças: no máximo 1× por segundo. Heartbeat: a cada 10 s.

### 9.4 Como grava

Escreve `estado.tmp` inteiro, última linha `fim=<checksum>`, `FileFlush`, `FileClose`; copia `estado.txt` → `estado.bak`; move `.tmp` → `.txt` com `FILE_REWRITE`. Leitura: ausente, tamanho zero, sem `fim=` ou checksum errado = corrompido → `.bak`; os dois corrompidos → caso C (10.3), ALERTA, e o registro de envios do dia é refeito a partir das linhas `ORDEM` do log do dia (4.6).

### 9.5 Validade

- Outro servidor ou outra conta → ignorada; caso C; ALERTA.
- Outro pregão → mantém o registro de ordens próprias, o trânsito não resolvido, os bloqueios, a externa de origem desconhecida e o estado das fichas que continuam abertas; descarta o resto.
- Estado permanente perdido: `seq` = maior `seq` nos comentários `MAE|<robo>|` do histórico completo; resultado do DM = soma de 3.1 sobre todos os deals do magic do DM com comentário de origem `MAE|`. Log `MEMORIA reconstruida`.

## 10. Recuperação na partida

Toda partida (primeira do dia, mudança de input, volta de queda) passa por aqui **antes de qualquer atividade**: nenhum `Tick()` de robô e nenhuma entrada antes de `PRONTO`.

### 10.1 Trava no terminal

O maestro roda em uma instância só (D3). A trava impede ligá-lo em dois gráficos do mesmo terminal:
- variável global `WinMaestro.lock.<conta>.<símbolo>`, tomada com `GlobalVariableSetOnCondition(nome, <token>, 0)`. `token` = hash de 32 bits do gráfico, `(uint)(ChartID() ^ (ChartID() >> 32))`, trocado por 1 se der 0: cabe exato num `double` (o `ChartID()` inteiro passa de 2^53 e perderia dígitos);
- heartbeat `WinMaestro.hb.<conta>.<símbolo>` = `TimeLocal()` a cada 1 s. Trava de outro gráfico com heartbeat < 10 s → recusa iniciar (`Alert`, push, `ExpertRemove`). Heartbeat ≥ 10 s → toma a trava (`SetOnCondition` com o valor antigo), AVISO;
- **`g_iniciou`** fica verdadeira só depois de tomar a trava; instância recusada não cancela ordem, não grava memória e não libera trava (seção 7);
- no Testador a trava é pulada.

### 10.2 Máquina de estados

Avançada pelo timer e pelo `OnTick`. Cada passo loga início, fim e números. Todo passo é reentrante: repeti-lo não envia nada que já esteja vivo.

| Estado | O que faz | Prazo / falha |
|---|---|---|
| `R0` | `OnInit` terminou | — |
| `R1_TRAVA` | 10.1 (pulado no Testador) | falha → `RECUSADO` (`g_iniciou` falsa) |
| `R2_CONEXAO` | `TERMINAL_CONNECTED` e tick válido (pulado no Testador) | log a cada 30 s; ALERTA após 5 min; nenhuma ordem |
| `R3_AMBIENTE` | conta NETTING; símbolo negociável (`SYMBOL_TRADE_MODE_FULL`; `WIN$N`/`WIN@` só no Testador); modos de validade e preenchimento; valor do tick; limites (`ACCOUNT_LIMIT_ORDERS`, `SYMBOL_VOLUME_LIMIT`, AVISO se < 15 pendentes); notificações habilitadas (senão AVISO diário); outros símbolos (8.8). Leitura zerada é repetida por 60 s antes de concluir falha | falha → `RECUSADO` se não houver ficha nem ordem viva de magic de robô; com elas, `PROTEGENDO` |
| `R4_HISTORICO` | janela de reconstrução fecha (3.2) | prazo `PRAZO_HISTORICO_R4` (60 s): esgotado, usa a janela mais longa disponível, grava a diferença como **exposição externa de origem desconhecida** (a cruzada passa a incluí-la, 3.2), ALERTA com push e segue para R5 marcando `PROTEGENDO` com bloqueio que exige o dono |
| `R5_MEMORIA` | lê estado de pregão e permanente (9.4, 9.5); memória perdida → log do dia (9.4) | corrompida → caso C |
| `R6_RECONSTROI` | fichas (3.1), desfecho das ordens do trânsito gravado (4.6), deals externos e absorção (8.9), bloqueios de eventos não reconhecidos | — |
| `R7_ORFAS` | **antes de qualquer outra ordem**: cancela toda S/A/X-limite sem ficha, irmãs de fichas que zeraram com o EA fora, E que nenhum robô reconhece (8.5, 5.1) | sem desfecho → segue; a reconciliação repete |
| `R8_COMPARA` | memória × corretora por robô: casos A, B, C (10.3) | — |
| `R9_PROTEGE` | toda ficha ≠ 0 com exatamente uma S (8.4); alvo do RE no nível da memória, **salvo ficha trocada ou duplicada** | S recusada → cadência 4.8, segue |
| `R10_PENDENCIAS` | ficha trocada e duplicada (8.3); ficha de pregão anterior e corte perdido (12.4): executa se estiver no contínuo, senão agenda para `negociacao_inicio` — agendar, não esperar | — |
| `R11_INICIA` | `Init()` de cada robô com o estado restaurado (handles, pré-carga do RE, histórico de volume do CM) | — |
| `R12_RECALCULA` | recálculo específico de cada robô (10.4) | — |
| `R13_PRONTO` | grava memória; lê o capital de referência (13.1); log `PRONTO` com resumo e histórico do dia (11.4) | — |

**`PROTEGENDO`** é um modo explícito: módulos parados, entradas bloqueadas; o maestro mantém as S (8.4), detecta stop sem execução (5.4), cancela órfãs (8.5), executa o corte (12.3) e repete a causa a cada 30 s. Sai para R11 quando a causa some; o `PROTEGENDO` causado pelo prazo de R4 sai só pelo botão (8.6), e daí em diante os robôs operam com a externa de origem desconhecida contada. Log ALERTA ao entrar, AVISO a cada 5 min, INFO ao sair.

### 10.3 Casos por robô (R8)

- **A. Confere** (ficha e ordens batem com a memória): restaura níveis e instantes.
- **B. A corretora andou com o EA fora** (stop ou alvo executou, entrada encheu, validade venceu, intervenção externa): a corretora vence; cada evento perdido é logado com a hora real do deal. Entrada que encheu fora ganha a S no R9 com o nível da memória.
- **C. Sem memória utilizável:** ficha pela corretora; níveis recalculados das barras (Apêndice A); sem como recalcular o stop, nível da S viva; sem S viva, `STOP_EMERGENCIA_PTS`. ALERTA.

### 10.4 Recálculo específico e decisão atrasada (R12)

Sem replay genérico de velas: cada robô faz o recálculo que o avulso já fazia ao reiniciar, com os instantes persistidos (Apêndice A). A persistência corrige os defeitos de reinício conhecidos (GB não duplica a entrada; CM e C1 não reentram na mesma vela; DM não perde o stop do EA; RE não perde o alvo que se aproxima). Ficha de pregão anterior não é recalculada (12.4).

Decisão de entrada cujo momento de envio passou com o EA fora:
- o maestro avisa o módulo com `ENTRADA_REENVIAVEL` **só** se a validade da regra não venceu e o preço limite **não é executável agora** (compra: preço < melhor oferta; venda: preço > melhor demanda); o módulo decide pela regra dele (Apêndice A);
- caso contrário: `DECISAO PERDIDA` (itens 2.1, 2.6, 4.17);
- entrada a mercado (C1) mais de 60 s depois da abertura da vela de sinal: sempre `DECISAO PERDIDA`.

## 11. Logs

### 11.1 Onde

- Diário do MT5 e `logs/AAAA-MM-DD.log`: uma linha por evento (11.3).
- `logs/AAAA-MM-DD_trans.log`: uma linha bruta por evento de `OnTradeTransaction` do símbolo (tipo, ordem, deal, estado, preço, volume, magic, `request_id`).
- Arquivo em acréscimo, `FileFlush` a cada linha. O log do dia também é fonte de recuperação (4.6, 9.4).

### 11.2 Formato, níveis e notificações

`HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe | [tick HH:MM:SS.mmm loc HH:MM:SS]`

- Hora principal = `TimeTradeServer()` com ms; depois, hora do último tick e hora local.
- `NIVEL`: `INFO`, `AVISO`, `ALERTA`, `ERRO`. `ROBO`: `GB`, `CM`, `DM`, `RE`, `C1`, `MAESTRO`.
- Linha de ordem traz: ticket da ordem e do deal, `request_id`, `retcode` e `retcode_external`, comentário, **preço pedido e preço executado** lado a lado (item 4.15), líquida antes → depois.
- Anti-spam por **objeto** (ticket ou ficha), não por processo (item 1.12): a mesma condição sobre o mesmo objeto é logada ao começar, a cada 5 min com contador e ao terminar.
- **ALERTA** dispara `Alert()` e entra na **fila de push**: dedupe por (evento, objeto) — o mesmo par no máximo 1 push a cada 5 min; frequência — no máximo 1 `SendNotification` a cada 10 s (dentro do limite da MT5, a verificar, P25); alertas que chegam durante a espera são agregados numa mensagem (`3 alertas: CM STOP SEM EXECUCAO; RE ABSORVIDA; BLOQUEIO externa`). Falha de `SendNotification` é logada como ERRO.

Exemplos:
```
10:00:00.140 | INFO   | CM | ORDEM    | E sell limit 1 @176855 ord #48211 req 37 rc 10008/0 MAE|CM|E|00042|F
10:03:12.501 | INFO   | CM | ENTROU   | vendido 1; pedido 176855 exec 176855 deal #9912; liquida +1 -> 0
10:03:12.690 | INFO   | CM | STOP     | S buy stop 1 @181800 ord #48230 (reserva); atraso 189 ms
12:00:00.560 | INFO   | CM | SAIU     | EMA; compra 1 deal #9987 exec 176210; +129,00; liquida 0 -> +1
12:00:00.610 | INFO   | CM | CANCELA  | S #48230 CANCELED confirmado em 50 ms
09:00:02.300 | ALERTA | MAESTRO | RECUPERA | EA fora 09:41-10:12; DM: S executou 09:58 @190165 (-68,00)
```

### 11.3 Catálogo de eventos

`INICIO`, `TRAVA`, `AMBIENTE`, `ESPERA`, `HISTORICO`, `MEMORIA`, `RECUPERA`, `PROTEGENDO`, `PRONTO`, `RECUSADO`, `LIGADO`/`DESLIGADO`, `SINAL`, `BLOQUEIO` (sempre com motivo), `DESBLOQUEIO`, `ESTADO` (aberto, explicado, fechado), `ORDEM`, `REJEITADA`, `DESFECHO` (executada, viva, não executada, com a prova; sem desfecho), `ENTROU`, `STOP`/`ALVO` (criado, movido, recriado), `STOP SEM EXECUCAO`, `SAIDA`, `SAIU`, `SAIDA_RECUSADA`, `DECISAO PERDIDA`, `CANCELA`, `EXECUTOU_ANTES`, `ZERAGEM`, `CORTE`, `PREGAO_ANTERIOR`, `AGENDADA`, `DIVERGENCIA`, `TROCADA`, `DUPLICADA`, `CORRECAO`, `COBERTURA`, `INVARIANTE`, `EXTERNA`, `ABSORVIDA`, `ORFA`, `AVULSO`, `ORIGEM NAO CONFIRMADA`, `AUTONEG`, `AJUSTE`, `RELOGIO`, `MARGEM`, `CAPITAL`, `PUSH`, `FIM`, `HISTORICO_DIA`, `RESUMO`.

### 11.4 O que já foi feito

No `PRONTO` de toda partida e no `RESUMO`: por robô, a lista das operações do dia reconstruída dos deals (hora, lado, entrada, saída, motivo quando conhecido, R$), marcando as que ocorreram com o EA fora (`HISTORICO_DIA`). O `RECUPERA` lista cada evento perdido com a hora real do deal.

### 11.5 Resumo do dia e conciliação

Depois do corte e no `OnDeinit`: por robô, operações, acertos, R$ bruto e líquido, maior perda; total da conta pelas fichas **e** por `DEAL_PROFIT` + custos (diferença > R$1,00 → ALERTA); **conciliação de contagem** (item 1.21): contratos negociados no símbolo contra `ENTROU`/`SAIU`/`ABSORVIDA` do log (diferença ≠ 0 → ALERTA); contagem de AVISO, ALERTA e ERRO.

### 11.6 Painel no gráfico

`Comment()` com: estado (`PRONTO`/`PROTEGENDO`/…), ficha de cada robô (lado, preço, stop, alvo, resultado aberto, estado derivado), líquida real, externa, status (`OK` / `BLOQUEADO: motivo` / `ESTADO ABERTO: motivo`), capital de referência, hora do corte do dia, hora da última gravação e do último tick. Botão "Desbloquear" quando aplicável (8.6).

## 12. Horários, corte e fim de pregão

### 12.1 Relógio, grade e corte

- **O maestro é o único dono das saídas por horário.** O código de zeragem e de "posição de outro dia" de cada módulo (GB L357, CM L720-724, DM L476/L490, RE L1019, C1 L591-594) é desligado por uma flag de configuração do módulo, sem apagar, para o teste do módulo isolado continuar possível.
- Relógio: `TimeTradeServer()` + fuso, no timer, mesmo sem tick (item 2.8). **Fuso calculado**: no real, `fuso = −3 − round((TimeTradeServer() − TimeGMT()) / 3600)` horas, AVISO se ≠ 0 (confirmar com P22); no Testador, 0.
- `F` = **fim do pregão contínuo da data** (`negociacao_fim` da grade; no dia de vencimento do próprio contrato do gráfico, `vencimento_fim`), nunca a sessão da MT5, que pode incluir o call (item 5.35). Data sem linha preenchida na grade: usa 17:55 (o fim mais cedo registrado), AVISO diário.
- **Corte = F − 5 min** (Apêndice B, D2): 18:20 nos dias de contínuo até 18:25; 17:50 nos dias até 17:55.
- `RELOGIO`: `TimeCurrent()` e `TimeTradeServer()` divergindo > 60 s durante o contínuo (feed parado, item 5.17).

### 12.2 Zeragem de cada robô

Cada robô zera no horário dele, **nunca depois do corte**: zeragem = min(horário do robô, corte). Executada pelo maestro (protocolo 5.2, volume de 12.3), pelo timer.

| Robô | Zeragem do avulso | Dias de 18:25 (corte 18:20) | Dias de 17:55 (corte 17:50) |
|---|---|---|---|
| GB | 18:20, limitada a F − 5 min | 18:20 | 17:50 |
| CM | 18:24 (ou sessão − 1 min) | **18:20** (mudança, D2) | **17:50** (mudança, D2) |
| DM | sessão − 5 min | 18:20 | 17:50 |
| RE | 17:00, avaliada a cada vela M15 | 17:00 | 17:00 |
| C1 | 17:50 (fim 18:00 − 10 min) | 17:50 | 17:50 (= corte) |

Diferenças contra o avulso, listadas no relatório 15.1: o CM zera 4 min mais cedo (D2); o avulso fecha no primeiro tick depois do horário e o maestro no instante do timer; o RE deixa de esperar a vela M15; antes de 2024-03-11 o GB usava regra própria de 17:55 e o maestro usa a grade.

### 12.3 Corte e volume das saídas por horário

**Volume de uma saída por horário** (zeragem de 12.2, corte, ficha que passou a noite) do robô r: |ficha pelos deals de r|. Se r tem ordem sem desfecho ou o estado está aberto: exige leitura confiável e o volume é min(|ficha pelos deals|, |resíduo real de r|) quando o resíduo tem o sinal da ficha, 0 caso contrário (0 → nada é enviado); a espera de 4.6 e o `JA_EM_TRANSITO` não se aplicam. Sem leitura confiável (desconectado) nada pode ser enviado: ALERTA; a S GTC protege.

**No corte (F − 5 min), em qualquer modo:**
1. Toda ficha pelos deals ainda aberta → saída pelo protocolo 5.2 com o volume acima, na ordem fixa GB, CM, DM, RE, C1, ALERTA (a zeragem do robô falhou). Ficha trocada ou duplicada → 8.3.
2. Depois, com leitura confiável: diferença U = líquida real − exposição externa − Σ fichas pelos deals ≠ 0 → zera U com uma ordem C do **robô suspeito** (o que tem ordem sem desfecho que explica U; senão o último robô com deal naquele lado), log com os números.
3. Cancela todas as pendentes dos magics dos robôs (E, A, X-limite), **exceto as S das fichas que ainda não saíram**. Cada saída executada cancela a S correspondente (5.2 passo 4).
4. Saída recusada → a S fica; fora de leilão, 5.4 até F.

Nada da 4.6 prende o corte. Depois de F nenhuma saída é enviada.

### 12.4 Ficha que passa a noite

Uma ficha só atravessa a noite se o EA estava fora no corte (ou se todas as saídas foram recusadas até F). A regra é única (D2):
- na volta, a ficha é zerada **no primeiro momento de pregão contínuo**: se o EA volta durante o contínuo, agora; se volta fora dele, em `negociacao_inicio`, pelo protocolo 5.2, com a S GTC protegendo até a saída executar; recusa (leilão prorrogado) → retenta a cada 5 s com a S intacta;
- o robô dono fica sem `Tick()` até a ficha zerar, e o recálculo do Apêndice A não gera saída para ela;
- fora do contínuo nenhuma saída é enviada e nenhum robô roda `Tick()`; só se criam, movem e cancelam S e se cancelam E e A. Se a S disparar no leilão de abertura (P13), a ficha zera e nada mais é enviado;
- o mesmo vale para o corte perdido: EA de volta depois do corte e antes de F → zera agora; depois de F → ficha que passa a noite.

**Rolagem**: o dono troca o gráfico para o contrato vigente; o estado de pregão é por símbolo e começa limpo; o permanente continua. Ordem ou posição esquecida no contrato velho: 8.8.

## 13. Capital, margem e saldo

### 13.1 Capital de referência

Não há input de capital. **Capital de referência** = `ACCOUNT_BALANCE` lido uma vez por pregão, no `PRONTO` (no Testador, o Depósito mais o resultado acumulado). Proteção contra leitura absurda (item 1.19): leitura ≤ 0, ou diferença entre a leitura nova e (leitura anterior + Σ dos deals da conta desde ela, inclusive depósitos e retiradas) maior que `SALTO_SALDO_MAX` (50%) da leitura anterior → mantém a leitura anterior e loga AVISO `CAPITAL`. Sem leitura anterior boa: o portão de 13.2 fica só em log até haver uma, AVISO.

### 13.2 Portão de margem

- **No Testador:** só registra (`MARGEM`), nunca recusa, para o teste reproduzir o avulso.
- **No real:** recusa **somente a entrada que a corretora também recusaria** (item 3.7), sem folga extra: `OrderCalcMargin(1) × |líquida depois da entrada|` (mais as pendentes, se P8 mostrar que a Rico bloqueia margem para elas) > capital de referência + resultado do dia (3.1). Recusa = `BLOQUEADA margem` com os números; o módulo é avisado como falha de envio.
- **Diagnóstico do pior estado** (log, não recusa — Apêndice B.11): `pior = max(|L + P+|, |L − P−|)` com L = líquida, P+ e P− = volumes de todas as ordens próprias vivas de compra e de venda (com o EA fora não há OCO). `OrderCalcMargin(1) × pior` acima do capital de referência → AVISO `MARGEM pior estado` uma vez por mudança. Em netting a saída de uma ficha pode ser abertura para a conta (item 1.1): um stop que leva a líquida de −1 a −2 exige margem.
- Saídas nunca passam pelo portão. Recusa por margem de S, X ou C: ALERTA com push, e segue 5.4 e 4.8.
- `ACCOUNT_MARGIN_FREE` é só diagnóstico (log a cada 5 min).

### 13.3 Saldo virtual do DM

O DM limita o stop a 10% do saldo. Saldo virtual (B.2) = `DM_CAPITAL_ROBO` (R$1.000) + resultado acumulado do DM (3.1, só deals do maestro), no estado permanente (9.1) e reconstruível (9.5). Com R$1.000, teto de R$100 por contrato = 500 pts.

### 13.4 Pior caso numérico das exceções do Princípio 4

Referência de movimento: **5.630 pts** contra num dia (R$1.126 por contrato) = percentil 99 de (máxima − mínima) diária do WIN$N, 2022-01 a 2026-10 (medido no replay em 2026-10-06; mediana 1.865, p95 4.081, máximo 8.320 pts). É um teto conservador: a amplitude do dia inteiro, não a excursão a partir da entrada.

| Exceção | Contratos sem stop no pior caso | Perda a 5.630 pts |
|---|---|---|
| (a) entradas limite que enchem com o EA fora ou desconectado: GB, CM, DM, RE | 4 | R$4.504 |
| (b) S e A executando juntas com o EA fora (RE; GB se o alvo for ligado) | 1 por robô com alvo; não soma com (a) para o mesmo robô | R$1.126 por robô |
| (c) CM só com a reserva distante | dentro de (a); limitado por `CM_ReservaPts` | R$0,20 × 4.945 = R$989 |
| Teto teórico (5 fichas no mesmo lado sem stop) | 5 | R$5.630 |
| Janela deal→S com o EA vivo (medida em toda abertura, 4.3) | 1 por abertura, por centenas de ms | desprezível salvo salto no mesmo instante |

O cancelamento das E no `OnDeinit` reduz (a) nos fechamentos ordenados do terminal; não reduz em queda de energia, travamento ou internet caída.

### 13.5 Capital mínimo da conta

- Exposição máxima alcançável: |líquida| = 5 contratos (5 fichas de 1; com execução dupla cada ficha vai no máximo a ∓1).
- Margem do pior estado = `OrderCalcMargin(1)` × 5 × 2,0 (buffer de margem do projeto). Com R$100 por contrato (a verificar na Rico, P8): R$1.000.
- **Capital mínimo = margem do pior estado + perda do teto teórico = R$1.000 + R$5.630 = R$6.630.** Recomendação de depósito: R$7.000 (B.10). Capital de referência abaixo de R$6.630 → AVISO no `PRONTO`, só log.
- Contratos simultâneos medidos no replay 2022–2026: no máximo 4.

## 14. Riscos de bolsa e perguntas

### 14.1 Riscos e onde estão tratados

| Risco | Tratamento |
|---|---|
| Ordem stop pendente na Rico/B3 | 4.3, 5.4; P1, P2, P13 |
| Autonegociação | 4.9; P12 |
| Limite de ordens por segundo | envio serial (4.5), teto e disjuntor (4.8) |
| Leilão | 5.4, 12.4; P13 |
| Stop recusado por preço atravessado | 4.7 com 5.2 |
| SL/TP na líquida | 8.7 |
| Reconexão e histórico incompleto | 4.6, 8.1, 8.2; P18 |
| Zeragem compulsória e stop-out | 8.9; P10, P11 |
| Margem de saída que aumenta a líquida | 13.2; P7, P8 |

### 14.2 Perguntas (demo ou envio mínimo no real)

**(real)** = a demo da Rico provavelmente não reproduz (casamento simulado, item 4.7): pede resposta escrita da Rico ou teste com 1 contrato no real.

| # | Pergunta | Decide |
|---|---|---|
| P1 | `SELL_STOP`/`BUY_STOP` no WINV26: aceita? Com DAY, GTC e SPECIFIED? Continua listada com o terminal fechado? Que `ORDER_TYPE`/`ORDER_STATE` assume ao disparar? Fica na Rico ou vai à B3 como stop nativo? Dispara pelo último negócio? Vira mercado, limite com proteção ou stop-limit? | 4.1, 4.3, 5.4, B.6 |
| P2 | O deal gerado por stop ou limite pendente carrega `DEAL_MAGIC` e o comentário da ordem? Qual `DEAL_REASON`? | 3.1, 4.4, 8.9 |
| P3 | O `ORDER_COMMENT` sobrevive igual na ordem, no histórico e depois de `OrderModify`? Até quantos caracteres? | 3.3, 4.2, 4.4 |
| P4 | `OrderModify` de stop pendente mantém o ticket? A ordem sai do ar durante a modificação? | 3.3, 4.7 |
| P5 | `OrderDelete` de ordem que acabou de disparar: retcode, `ORDER_STATE` no histórico, tempo até o desfecho? | 5.1 |
| P6 | Atraso entre o retorno do `OrderSend` (mercado) e o deal em `HistorySelect`, p50 e máximo em 50 envios. Alguma vez `DONE` com `deal=0`? | 4.6 |
| P7 | Líquida −1 (dois vendidos, um comprado), o stop do comprado leva a −2: passa por checagem de margem? Com margem justa, é recusado? **(real)** | 13.2 |
| P8 | Pendente bloqueia margem na colocação? `OrderCalcMargin(WIN, 1)` devolve a margem de day trade da Rico ou a da B3? Qual é a margem de day trade do WIN na Rico? | 13.2, 13.5 |
| P9 | `ACCOUNT_MARGIN_FREE`, `ACCOUNT_MARGIN` e `ACCOUNT_BALANCE` batem com o extrato no mesmo instante, em 5 dias diferentes? | 13.1, 13.2 |
| P10 | Zerar a líquida na mão pelo terminal: qual `DEAL_REASON` e magic? E pela mesa da corretora? **(real)** | 4.4, 8.9 |
| P11 | A Rico faz zeragem compulsória de day trade no WIN? A que horas, com que `DEAL_REASON`/magic, e cancela as pendentes? **(real)** | 8.9, 12.2 |
| P12 | Existe Self-Trade Prevention na conta? SELL_STOP disparando contra a própria BUY_LIMIT: executa, cancela a agressora ou a passiva? Como chega na MT5? **(real)** | 4.9 |
| P13 | Stop disparado em leilão (abertura, call, por variação): vira o quê? Mercado enviado em leilão: qual retcode? **(real)** | 5.4, 12.4 |
| P14 | Posição que passa a noite: `POSITION_PRICE_OPEN` muda para o ajuste? Aparecem deals de ajuste ou variação de margem? Tipo e volume? | 3.1, 3.2 |
| P15 | `SYMBOL_FILLING_MODE` e `SYMBOL_EXPIRATION_MODE` do WINV26? Mercado com `RETURN` é aceito? | 4.1 |
| P16 | `GlobalVariableSetOnCondition` funciona como trava entre dois gráficos do mesmo terminal? | 10.1 |
| P17 | Em `REASON_PARAMETERS` e `REASON_CHARTCHANGE` as variáveis globais do EA sobrevivem? | 2.1, 7 |
| P18 | Depois de 2 min sem internet: o histórico volta completo de uma vez? Quanto tempo até `Σ deals = líquida`? Deals chegam com hora antiga? | 3.2, 4.6, 8.1 |
| P19 | `TimeTradeServer()` anda com o feed parado? Diferença para `TimeCurrent()` no leilão de abertura? | 12.1 |
| P20 | `ACCOUNT_LIMIT_ORDERS` e `SYMBOL_VOLUME_LIMIT` para o WIN; limite de contratos de WIN por cliente em day trade na Rico | 4.1, 13.5 |
| P21 | A demo da Rico casa contra o livro real da B3 ou contra simulação? | 15.3, 15.5 |
| P22 | O relógio do servidor da Rico está em Brasília? O fuso calculado (12.1) dá 0? | 12.1 |
| P23 | Stop pendente GTC num contrato que vence é cancelado pela corretora no vencimento? | 4.3, 12.4 |
| P24 | O `OrderDelete` enviado no `OnDeinit` ao fechar o terminal chega ao servidor? | 7, 13.4 |
| P25 | Qual o limite atual de `SendNotification` (por segundo e por minuto) e o retorno quando ele é excedido? | 11.2 |

## 15. Testes antes de usar com dinheiro

### 15.1 Equivalência (Testador, WIN$N, ticks reais)

**Pré-condições:** cache de ticks com `last` em ≥ 99% dos ticks do período (EA `AuditoriaTicks`) e tamanho igual ao do terminal (itens 5.33, 6.54); valor do tick lido do símbolo (item 6.55); Depósito = R$1.000 no teste do DM (o capital dos comparativos, igual a `DM_CAPITAL_ROBO`).

| Teste | Comparação | Critério |
|---|---|---|
| 1 | cada robô sozinho no maestro × EA avulso, mesmo período | **entradas (hora e lado) 100% iguais, sem exceção**; saída no **mesmo tick** do avulso, salvo as causas listadas abaixo; resultado total ≤ max(2%; R$1,00 × trades) |
| 2 | os 5 ligados × replay T6 (`combinacoes/z9_netting/t6_maestro`) | entradas iguais **exceto** as marcadas com evento `AUTONEG` no log (4.9), contadas no relatório, meta ≤ 1% das entradas; resultado por robô igual ao do teste 1 do mesmo robô, salvo essas entradas |

Diferenças de saída permitidas, **listadas trade a trade com a causa**: zeragem do CM limitada ao corte (D2, 12.2); reserva do DM (5.5; mesmo preço, caminho S); zeragem pelo timer em vez do primeiro tick (12.2); prioridade da ordem fixa (4.5, só no teste 2); stop como ordem pendente criada após o deal em vez de SL anexado (GB, RE, C1: contar os trades com stop estourado no tick do fill). Qualquer outra diferença é defeito. No Testador o protocolo 5.2 tem atraso zero.

Relatório: ordens recusadas (> 0 = linha censurada, item 6.55), pior trade em múltiplos do stop (item 6.56), contagem de cada diferença permitida.

### 15.2 Camada de corretora e testes unitários

`Corretora.mqh` define uma interface (`Envia`, `Cancela`, `Modifica`, `Liquida`, `Pendentes`, `Historico`, `Conta`, `Simbolo`) usada por todo o maestro. Duas implementações:
- **`CorretoraReal`**: chama a API do MQL5. É a única que existe no `.ex5` de produção.
- **`CorretoraFalsa`**: segue um roteiro programado de respostas (retcode, atraso do deal, desfecho do cancelamento, estado do histórico, comentário devolvido, conexão) e registra cada chamada. Compilada só no EA de teste `WinMaestro_Teste.mq5`, que roda os casos abaixo no Testador e imprime OK/FALHA por caso.

Casos:
1. `DONE` sem deal: deal em 3 s; em 8 s; nunca, com a posição provando que não executou (4.6: resolve só pela prova; nada reenviado antes; S mantida).
2. `TIMEOUT` com ticket 0 e desconexão de 90 s logo depois, nas duas versões (a venda executou / nunca chegou): nenhuma resolução enquanto desconectado; depois da leitura confiável, a posição prova o desfecho; S viva o tempo todo; nenhuma venda duplicada (4.6, 8.4).
3. Execução sem deal visível: S em excesso cancelada pela 8.4 nível 2; entrada a mercado sem deal: S criada pela 8.4 nível 2; ordem sem desfecho por 10 min: bloqueio e botão; corte com ordem sem desfecho: volume pelo resíduo.
4. Estado aberto antes de um envio: E bloqueada até o estado fechar; S, corte e saídas por horário passam.
5. Entrada limite viva por 10 h: nenhuma S criada, nenhuma E cancelada como fora de lugar.
6. `OrderDelete` aceito com desfecho FILLED (5.1, 5.2).
7. Histórico chegando aos poucos após reconexão, com deal de hora antiga (8.1, 8.2: nenhuma correção).
8. S e A executando juntas; S e saída a mercado executando juntas (8.3; R9 não recoloca alvo em ficha trocada); entrada executada duas vezes (ficha +2: correção de 1, S mantida, bloqueio).
9. Saída recusada (leilão, banda): S viva; limite agressiva só no contínuo fora de leilão, sem cancelar a S.
10. Comentário truncado e ticket trocado no `OrderModify` (3.3, 4.4).
11. Externa: posição manual aberta e fechada (fichas intactas, sem bloqueio); zeragem manual com 2 fichas do mesmo lado; com fichas dos dois lados (8.9).
12. Bloqueio por externa, botão, reinício: bloqueio não volta (8.6).
13. Queda entre a gravação do trânsito e o `OrderSend`, com memória perdida: o log do dia mostra o envio; a ordem se resolve pela prova (4.6, 9.4).
14. Instância recusada no R1: `OnDeinit` não cancela E nem grava memória da instância viva (7).
15. Prazo de R4 esgotado com posição manual antiga: externa de origem desconhecida gravada, cruzada fecha com ela, `PROTEGENDO` sai pelo botão.
16. Partida às 08:50 com ficha que passou a noite: nenhum `Tick()`, nenhuma saída antes de `negociacao_inicio`; M1 de after-market não geram saída (12.4, A.3).
17. Recusa repetida de S (4.8: cadência, nunca por tick).
18. Saldo absurdo (zero, negativo, salto de 60% sem deal) (13.1).
19. Corte em dia de 17:55: todos zerados até 17:50; pendentes canceladas exceto S de fichas abertas (12.3).

### 15.3 Falhas (conta demo, pregão real)

| Cenário | Esperado |
|---|---|
| Fechar o MT5 com 2 robôs posicionados e reabrir 5 min depois | E canceladas no `OnDeinit`; S no servidor; `RECUPERA` com o que mudou; `HISTORICO_DIA` |
| Matar `terminal64.exe` (sem `OnDeinit`) com entrada pendente viva | E viva; se encher fora, ganha S no R9; caso B logado |
| Reabrir o terminal sem internet com 3 robôs posicionados | R2 espera; nada é removido; ao conectar, recuperação completa |
| Fechar o MT5 e deixar o stop de um robô executar | Ficha zerada, alvo cancelado no R7, evento com a hora real |
| Stop e alvo executando juntos com o EA fora | Ficha trocada corrigida no R10, ALERTA |
| Apagar `estado.txt`; apagar também o `.bak`; arquivo cortado; arquivo de tamanho zero | `.bak`; caso C com log do dia e nenhum robô sem stop; `.bak`; `.bak` |
| Memória de outra conta | Ignorada, caso C |
| Apagar o estado permanente | `seq` e saldo do DM reconstruídos |
| Desligar a internet 2 min; e durante o preenchimento de uma entrada limite | Nenhum envio que dependa de estado fechado enquanto fora; na volta, releitura completa antes de qualquer envio; deal visto, S criada |
| Fechar o MT5 logo após um sinal (reinício durante o `OrderSend`) | Desfecho resolvido pela prova, nada duplicado |
| Abrir posição manual e depois fechá-la | Externa volta a 0, fichas intactas, sem bloqueio |
| Zerar a líquida na mão com 2 robôs posicionados | Absorção GB→C1, S/A canceladas, bloqueio; botão libera; reiniciar não rebloqueia |
| SL na líquida pela tela | Bloqueio, ALERTA; SL não removido |
| Maestro em dois gráficos do mesmo terminal | O segundo recusa iniciar; E, memória e trava do primeiro intactas |
| EA avulso com magic do CM em outro gráfico | `AVULSO`, bloqueio de entradas, ALERTA |
| Trocar o timeframe com robôs posicionados | E não canceladas; caso A; nada duplicado |
| Trocar de conta com o EA rodando | E canceladas; memória da outra conta ignorada |
| Desligar um robô com ficha aberta | Só gere até zerar |
| EA fechado às 18:15, aberto 18:22 com ficha aberta | Zera na hora (corte perdido, antes de F) |
| EA fechado das 17:00 às 08:50 com ficha aberta | S GTC protegeu; nada enviado antes de `negociacao_inicio`; ficha zerada no primeiro momento de contínuo, ALERTA |
| Dia de vencimento do WIN | Cortes pela grade; nada no contrato velho (8.8) |
| Leilão por variação, quando ocorrer | Saídas recusadas seguem 5.4 com a S intacta |
| Forçar a falha da zeragem de um robô | `CORTE` zera em F − 5 min |
| Rajada de alertas (intervenção externa com 2 fichas) | Push agregado, no máximo 1 a cada 10 s |

### 15.4 Caminhos de saída obrigatórios

Antes do real, cada caminho precisa de evidência no log de ter disparado ao menos uma vez (item 4.28): zeragem de cada um dos 5 robôs; corte; ficha que passou a noite; corte perdido; correção de ficha trocada; correção de ficha duplicada; saída agressiva (5.4); cancelamento de E no `OnDeinit`; absorção externa; desfecho resolvido pela posição; S criada pela 8.4 nível 2; saída recusada com S mantida.

### 15.5 Escada no real

A demo da Rico não mede fila, autonegociação nem stop na B3 (item 4.7, P21).

| Degrau | Configuração | Duração mínima |
|---|---|---|
| 1 | 1 robô | 5 pregões |
| 2 | 2 robôs que podem ficar em lados opostos (ex.: CM e RE) | 5 pregões |
| 3 | os 5 robôs | — |

Cada degrau avança com: zero divergência não explicada; extrato da corretora igual ao log em contagem de contratos e preço; perguntas **(real)** alcançáveis respondidas; caminhos de 15.4 alcançáveis observados. Antes do degrau 1: 15.1, 15.2 e 15.3 aprovados; P1–P6, P8, P9, P15–P20, P22–P25 respondidas.

## 16. Fora do escopo

- Combinar sinais, prioridade entre robôs, consenso (testados na Z9, piores que fichas independentes).
- Limite de perda diária, de operações, de horário extra: não pedidos.
- Hedging: só NETTING.
- **Mais de uma instância** na mesma conta e no mesmo símbolo, em outro PC ou VPS (D3). Uma instância em outro lugar será independente, com outra conta ou outro símbolo.
- Lote > 1. Se um dia existir, o invariante 1 passa a "Σ volume das S = |ficha|", com uma S por incremento preenchido (`OrderModify` não altera volume em MQL5).
- O alarme do item 1.24 (`POSITION_PRICE_OPEN` fora da grade de preço) não se aplica: com várias fichas, preço médio da líquida fora da grade é normal.

## Apêndice A — por robô

Regras comuns: os 3 bloqueios por posição de outro robô saem; os 14 fechamentos da líquida inteira viram `Ficha_Fecha`; `PositionModify` vira `Ficha_DefineStop`; SL anexado vira S criada no deal; zeragem e "outro dia" do módulo desligados (12.1); `Tick()` só de `negociacao_inicio` ao corte; gate de vela nova persistido; instantes, nunca contagens. Para todos, `ENTRADA_CANCELADA` e `EXECUTOU_ANTES` = **não rearmar** (comportamento do avulso diante de uma ordem que sumiu).

### A.1 WinGapBarra1 (GB, 80080601, M5)
- Entrada limite 09:05 `SPECIFIED` até 09:35; S de 1.200 pts no deal; alvo e BE desligados no padrão (se ligados: A do robô; BE = `OrderModify` da S, nunca afrouxa).
- Persistir: `g_decidido`, `g_exp`, `g_be_feito`, data do pregão.
- Recálculo: stop = preço da ficha ∓ `StopPts`. A entrada viva é reconhecida pelo papel; não sai segunda entrada.
- `ENTRADA_REENVIAVEL`: reenvia (era a regra do avulso: uma ordem até `g_exp`).
- Zeragem: 18:20 (17:50 nos dias de 17:55).

### A.2 WinCincoMedias (CM, 80080501, H2)
- `a_favor` = marca `F`/`N` do comentário, memória; sem as duas, recalculado das barras da vela de sinal.
- Entrada limite DAY, validade 5 velas H2 contada pela hora de envio; saídas por sinal via `Ficha_Fecha`.
- S de reserva a `CM_ReservaPts` (B.1); `Ficha_Stop` devolve 0 até o "stop que aperta" nascer, que move a mesma S (nunca afrouxa, regra do robô). Checagem de nível: bid na compra, ask na venda, 1 tick (L603-604).
- Persistir: `g_ultima_barra`, `a_favor`, nível do stop que aperta, hora de envio e lado da entrada.
- Recálculo: stop que aperta das barras desde a hora da ficha; avalia a última H2 fechada (comportamento do avulso, com o gate persistido); histórico de volume no R11.
- `ENTRADA_REENVIAVEL`: reenvia se a validade de 5 velas não venceu.
- **Zeragem: 18:20 em vez de 18:24 (17:50 nos dias de 17:55)**, limitada ao corte (D2).

### A.3 WinDeslocamentoMatinal (DM, 80080101, M1)
- Stop do EA por last (bid/ask se last = 0, L446-448) + reserva `DM_ReservaTicks` além (5.5, B.5).
- Persistir: `g_stopNivel`, `g_distStop`, `g_stopAjustado`, `g_decidiu`, `g_dia`, `g_ordemHora`, `g_ordemPreco`. A entrada viva é reconhecida pelo papel, não pelo ticket.
- Recálculo: se a mínima (compra) ou máxima (venda) das M1 **do contínuo de hoje** desde o heartbeat cruzou `g_stopNivel`, sai pelo 5.2 (`SAIDA ATRASADA`). M1 de after-market e de pré-abertura nunca contam; ficha que passou a noite não é recalculada (12.4). Sem memória: `g_distStop` pela decisão das 10:30 refeita das barras com o saldo virtual; sem isso, nível da reserva menos `DM_ReservaTicks`.
- `ENTRADA_REENVIAVEL`: reenvia se dentro do TTL de 15 min.
- Zeragem: corte (18:20 / 17:50).

### A.4 WinRetanguloEma34 (RE, 20261005, M15)
- Preenchimento pelo deal com `DEAL_ORDER` = entrada. S = stop do robô; A = limite que se aproxima (`OrderModify`), DAY. Stop nunca afrouxa (regra do robô).
- Persistir: entrada pendente (hora de envio, lado, `g_meio_original`, `g_stop_original`, `g_alvo_original`), posição (`g_preco_entrada`, `g_largura_posicao`, `g_frac_alvo_atual`, hora da vela do fill) e retângulo vivo (`g_tem_retangulo`, `g_topo`, `g_piso`, `g_largura`, `g_meio`, `g_fora_seguidas`).
- Recálculo: `g_barras_esperando` e `g_barras_posicao` a partir dos instantes; o alvo vai ao passo correspondente (`OrderModify`), salvo ficha trocada ou duplicada.
- `ENTRADA_REENVIAVEL`: reenvia se dentro do TTL de 10 velas.
- O módulo não cancela a entrada no próprio `Deinit`; vale a regra do `OnDeinit` do maestro (7).
- `TesterStop` por `RE_LimiteEquity` (L1007) desligado; o input sai.
- Zeragem: 17:00.

### A.5 Win_c1 (C1, 80080002, H1)
- Entrada a mercado: preço da ficha = deal; S no mesmo fluxo do `OrderSend`.
- **Trailing por vela H1 pode afrouxar**: o stop segue `wma ± KFechamentoATR × ATR` nos dois sentidos, movido quando difere mais de meio tick (L536-550). O maestro move igual.
- Checagem de nível: bid na compra, ask na venda, 1 tick (L538-541).
- Break-even e esticada usam preço e hora da ficha.
- Persistir: `g_ultima_barra`, nível do stop. Recálculo: pico de afastamento e esticada desde a hora da ficha; stop da última H1 fechada.
- Entrada atrasada mais de 60 s: `DECISAO PERDIDA` (não recebe `ENTRADA_REENVIAVEL`).
- Zeragem: 17:50 (igual ao corte nos dias de 17:55).

## Apêndice B — decisões do dono

### Decididas pelo dono em 2026-10-07

- **D1. Verificação antes de toda ordem.** Antes de enviar qualquer ordem, o maestro confere posição, ordens vivas e deals; se algo aberto não é explicado pelas fichas confirmadas, consulta o histórico e o log até explicar, e só então envia. Nada é reenviado por inferência de tempo; ordem sem confirmação só se resolve pelo histórico ou pela prova da posição real e das ordens vivas. Proteção, saídas por horário e corte nunca ficam presos (4.6, 8.4, 12.3).
- **D2. Corte global = fim do contínuo da data − 5 min.** Todas as estratégias zeradas até o corte; horário próprio de cada robô pode ser mais cedo, nunca depois. O CM passa de 18:24 para 18:20 (mudança em relação ao avulso). No corte o maestro zera o que restar e cancela todas as pendentes dos magics, exceto as S das fichas que ainda não saíram. Ficha que passa a noite só existe com o EA fora no corte e é zerada no primeiro momento de contínuo, com a S GTC protegendo até lá; robôs sem `Tick()` fora do contínuo (seção 12).
- **D3. Uma instância só.** O maestro roda num único PC. Em outro lugar, será independente, com outra conta ou outro símbolo. Sem detecção entre máquinas e sem identificador de instância no comentário; fica só a trava no mesmo terminal e a flag `g_iniciou` (10.1, 16).
- **Grupo Maestro no topo dos inputs**, com os 5 liga/desliga: decisão explícita do dono, que escolhe os robôs ali (2.1).

### Aguardam o dono

Cada item traz a recomendação adotada no texto acima.

1. **Stop de reserva do CM.** O robô não tem stop inicial; com o EA fora a ficha fica sem proteção. Opções: (a) sem reserva (fiel ao testado; `CM_ReservaPts = 0`, aceito com AVISO diário); (b) S de reserva distante, que nunca dispararia nos testes 2022–2026 e só protege em queda: `CM_ReservaPts` = maior excursão adversa de um trade do CM no replay 2022–2026 + 20%, arredondada para cima em ticks. **Medido em 2026-10-06: 815 trades, maior excursão 4.120 pts (2,18% do preço, 02/10/2026), p99 2.241, mediana 400 → `CM_ReservaPts` = 4.945.** Nunca teria disparado nos testes. **Recomendação: (b)**, padrão 4.945.
2. **Saldo do DM:** saldo virtual (R$1.000 + resultado dele, 13.3) ou saldo da conta. **Recomendação: saldo virtual** (com 5 robôs, 10% da conta é outro teto, e o saldo da Rico já mentiu, item 1.19).
3. **Entradas e alvos DAY** (Retângulo e alvo do GapBarra1 eram GTC). **Recomendação: DAY.**
4. **WinSeletor e EAs avulsos aposentados.** **Recomendação: aposentar.**
5. **Stop do DM em dois caminhos de níveis diferentes** (5.5): (a) só a S no servidor no nível do stop (muda o mecanismo testado); (b) stop do EA no nível testado + reserva 20 ticks além. **Recomendação: (b)**; custo com o EA fora: até R$20 por contrato além do stop.
6. **Validade dos stops:** (a) GTC (ficha esquecida protegida à noite; S órfã tratada pelo R7 e por 8.5); (b) DAY (posição nua à noite quando o EA falha no corte). **Recomendação: (a) GTC.**
7. **Janela sem stop (Princípio 4, exceções a e b).** Aceitar, com as mitigações adotadas (S do C1 no mesmo fluxo do envio; S na mesma chamada que vê o deal; E canceladas no `OnDeinit`) e o pior caso de 13.4: **R$4.504 a 4 contratos, teto teórico R$5.630** num dia de amplitude p99 (5.630 pts). Cancelar entradas quando o EA perde a conexão não protege: o cancelamento precisa da conexão que falta. **Recomendação: aceitar.**
8. **Absorção de intervenção externa redutora** (8.9): ordem fixa GB, CM, DM, RE, C1 ou proporcional. **Recomendação: ordem fixa** (determinística, reproduzível sem memória).
9. **RE com stop e alvo vivos sem o EA** (5.3): aceitar o risco de execução dupla, ou RE sem alvo no servidor (muda o robô). **Recomendação: aceitar**, com a correção de 8.3.
10. **Depósito da conta** (não é input: o EA lê o saldo, 13.1). Mínimo calculado R$6.630 (13.5: 5 contratos sem stop com o EA fora num dia de amplitude p99, mais a margem do pior estado). **Recomendação: depositar R$7.000.** R$5.000 cobre a margem e o uso normal, mas não o pior caso de queda do EA.
11. **Portão de margem.** No real recusa só o que a corretora recusaria (margem da líquida depois da entrada contra o capital de referência); no Testador só loga. O pior estado alcançável (todas as pendentes executando, item 3.3: "o portão tem de impedir o último passo que ainda cabia") fica só como AVISO. Consequência aceita: uma entrada pode ser aceita mesmo que, depois dela, um stop de outro robô fique sem margem para executar; nesse caso a recusa do stop gera ALERTA e a saída agressiva de 5.4 (item 1.1, incidente de 2026-08-28). Alternativa: recusar também pelo pior estado. **Recomendação: só o que a corretora recusaria**, conforme a preferência registrada do dono.
12. **Ordem entre saída a mercado e cancelamento da S** (5.2). (a) Saída primeiro, S cancelada depois de a saída executar: a posição nunca fica sem stop por causa de uma saída recusada (leilão, banda, margem); custo: se a S estiver no nível do preço no mesmo instante, as duas executam e a ficha fica trocada por alguns segundos, até a correção da 8.3 (item 1.23). (b) Cancelar a S com confirmação e só então sair: sem saída dupla; custo: saída recusada deixa a ficha sem stop até a 8.4 recriá-la, e em leilão com gap contra isso pode durar até a abertura do contínuo. **Recomendação: (a).**

## Apêndice C — rastreabilidade

### C.1 Revisão adversarial 1

"Parcial" indica as lacunas que as revisões 2 e 3 acharam incompletas e o item que as completa.

| Lacuna | Parcial | Resolvida em |
|---|---|---|
| C1 trânsito / DONE sem deal | sim (N1, N2, T1, T2) | 4.6 (verificação antes de toda ordem; desfecho só por prova); 3.1; 8.4; 12.3 |
| C2 cancelamento confirmado | — | 5.1, 5.2; 4.7 item 4; 5.5 |
| C3 intervenção externa | sim (N5, N6) | 8.9 (compensação), 8.7, 8.6 (botão, eventos reconhecidos); B.8 |
| C4 janela fill→stop | sim (N20) | Princípio 4a; 4.3; 7; 13.4; B.7 |
| C5 sem OCO | — | Princípio 4b; 5.3; R7, R10; B.9 |
| C6 duas instâncias | sim (N3, N18, T3, T4) | 10.1 (trava no terminal, `g_iniciou`); outra máquina fora do escopo (D3, 16) |
| C7 autonegociação | — | 4.9; 3.4 (`ENTRADA_CANCELADA`) |
| C8 stop que abre para a conta | — | 13.2 (pior estado como diagnóstico); B.11 |
| C9 ficha que atravessa a noite | sim (N4, N3, T6, T7) | 3.2; 4.3 (GTC); 12.4 (regra única, D2); 5.2 (S mantida na saída); B.6 |
| C10 divergência transitória | sim (N7) | 8.1, 8.2, 8.3 |
| C11 stop disparado sem execução | — | 5.4 |
| A1 relógio e fim do contínuo | sim (N14) | 12.1 (maestro único dono, fuso calculado, corte), 12.2 |
| A2 `DEAL_ENTRY`/`DEAL_PROFIT` | — | 3.1; 11.5 |
| A3 papel pelo comentário | — | 3.3; 4.7; P3, P4 |
| A4 bloqueio sem cancelar E | — | 8.6 |
| A5 estado velho na volta | — | 9.2 (instantes); 10.4; Apêndice A |
| A6 `OnInit` e protegendo | — | 7; 10.2 |
| A7 margem livre como gatilho | sim (N9) | 13.1, 13.2; B.10, B.11 |
| A8 equivalência | sim (N12, N13, N21) | 15.1; 5.1 e 5.2 (mesmo tick); 4.7 |
| A9 plano de testes | — | 15.2–15.5 |
| A10 retentativas | sim (N10) | 4.8; 3.4 (`Robo_Evento`) |
| A11 DM em dois caminhos | — | 5.5; B.5 |
| M1 memória | — | 9 |
| M2 órfã recém-enviada | — | 8.5 |
| M3 magic da correção | — | 4.4, 8.3 |
| M4 logs | — | 11 |
| M5 rolagem e outros símbolos | — | 8.8, 12.4 |
| M6 custo da reconciliação | sim (N7) | 8.1 |
| M7 modos de preenchimento/validade | — | 4.1; R3 |
| M8 mover stop | sim (N13) | 4.7 |
| B1 31 caracteres | — | 4.2; P3 |
| B2 alarme do item 1.24 | — | 16 |
| B3 limites da conta | — | R3; P20 |
| B4 parcial com lote > 1 | sim (N17) | `LOTE` = 1 (2.2); 16 |
| B5 prioridade da ordem fixa | — | 4.5; 15.1 |

### C.2 Afirmações apontadas como erradas na revisão 1

| Afirmação | Resolvida em |
|---|---|
| "todo robô posicionado tem o stop dele como ordem pendente" | Princípio 4 com exceções; 13.4; B.7 |
| ficha = deals do dia × ficha de pregão anterior | 3.2; 12.4 |
| magic desconhecido = externa e "não mexe" | 8.9 |
| a ordem stop "fica no servidor com o terminal desligado" | 4.3 (a verificar); P1, P13 |
| "entrada que reduz a líquida não exige margem nova" | 13.2 |
| portão por "margem livre" | 13.1, 13.2 |
| bloquear ordem que cruza com ordem própria | 4.9 |
| zerar SL/TP da posição | 8.7 |
| ticket processado uma vez evita contar duas vezes | 8.1, 8.2; P18 |
| "mudar inputs reinicia o EA … recuperação completa" | 2.1; 7; P17 |
| "`ORDER_FILLING_RETURN` … o que a B3 exige em limite" | 4.1; P15 |
| comentário identifica a ordem depois do reinício | 3.3, 4.4; P3 |

### C.3 Revisão adversarial 2

| Lacuna | Resolvida em |
|---|---|
| N1 ordem sem desfecho sem saída | 4.6 (desfecho só por prova; prazo de 10 min com botão); 8.4; 12.3 |
| N2 E limite na ficha efetiva | 3.1 (E limite contribui 0); 4.3 e 8.4 (S só com deal); 4.6 (pendente listada = viva) |
| N3 ordem estranha falsa | 4.4 (registro persistente; corte pelo primeiro heartbeat); detecção entre instâncias fora do escopo (D3) |
| N4 R4 para sempre | 10.2 R4; 3.2 (cruzada com externa de origem desconhecida) |
| N5 fechamento de posição manual | 8.9 passo 1 |
| N6 desbloqueio reaplicado / input | 8.6 (botão, eventos reconhecidos); R6 |
| N7 cruzada sem fechar / deal atrasado | 8.1, 8.2 |
| N8 ambiente antes da conexão | 10.2 (R2 antes de R3; `RECUSADO` só sem fichas) |
| N9 `CapitalConta` | 13.1, 13.2; B.10, B.11 |
| N10 quem retenta E / avisos ao módulo | 3.4 (`Robo_Evento`, inclusive E cancelada pelo dono ou pela corretora); 4.8; Apêndice A |
| N11 ficha trocada | 3.1; 8.3; 8.4; 3.3 |
| N12 protocolo assíncrono no Testador | 5.1, 5.2; 15.1 |
| N13 nunca afrouxa × trailing do C1; fonte de preço | 4.7; A.2, A.3, A.5 |
| N14 dois donos da zeragem | 12.1, 12.2 |
| N15 máquina do ciclo incompleta | 6 (estado derivado) |
| N16 replay antes do `Init` | 10.2 (R11 antes de R12); 10.4 |
| N17 `OrderModify` de volume | 2.2 (`LOTE` = 1); 16 |
| N18 Testador | 7; 9.1; 10.1, 10.2 (R1, R2 pulados) |
| N19 limite de push | 11.2; P25 |
| N20 números inconsistentes | B.7 = 13.4; 13.5; B.10 |
| N21 critério de equivalência | 15.1 |
| N22 camada de corretora | 1; 15.2 |
| N23 cancelar em paralelo × serial | 4.5, 5.2 passo 1 |
| N24 passo redundante da janela | 3.2 |
| N25 renovação da S `SPECIFIED` | 4.1 |
| N26 volta do `seq` | 4.2 |
| N27 inputs | 2.1 (grupo Maestro no topo por decisão do dono), 2.2 |

### C.4 Revisão adversarial 3

| Item | Resolvido em |
|---|---|
| T1 resolução sem conexão / reenvio duplicado | 4.6 (D1: nenhuma resolução por prazo; desfecho só por histórico ou prova da posição em leitura confiável; S sem desfecho bloqueia só a próxima S); 8.3 (ficha duplicada → 1, S mantida) |
| T2 ordem sem desfecho sem prazo e sem stop | 4.6 (10 min → botão); convenções (resíduo real); 8.4 (proteção pela posição real, níveis 1 e 2); 12.3 (volume pelo resíduo; o corte nunca fica preso) |
| T3 duas instâncias entre máquinas | fora do escopo por decisão do dono (D3, 16); 10.1 cobre dois gráficos no mesmo terminal |
| T4 instância recusada estraga a viva | 7 (`OnDeinit` com `g_iniciou`); 10.1 |
| T5 `PROTEGENDO` eterno depois do R4 | 3.2; 10.2; 8.6 (sai pelo botão) |
| T6 saída recusada sem S; 8.4 × 5.4 | Princípio 5; 5.2 (S cancelada só depois da saída executada); 5.4 (nunca cancela S; prioridade da 8.4); B.12 |
| T7 duas regras para o pregão anterior | 12.4 (regra única, D2); 7 (`Tick()` só de `negociacao_inicio` ao corte); A.3 |
| Trava com `ChartID()` em `double` | 10.1 (token de 32 bits) |
| R9 recolocando alvo em ficha trocada | 10.2 R9; A.4 |
| `TesterStop` do RE | 2.1; A.4 |
| N10 (nota: E cancelada pelo dono ou pela corretora) | 3.4 |
| N27 (grupo no topo) | 2.1; Apêndice B (decidido pelo dono) |

### C.5 Checklist de `LICOES_DE_PRODUCAO.md`

| Item | Onde |
|---|---|
| 1.1 | 13.2; B.11 |
| 1.2 | Princípio 4; 4.3; 13.4; B.7 |
| 1.4 / 1.23 | Princípio 5; 5.2; 5.5; B.12 |
| 1.5 | 5.1 |
| 1.6 | 4.6; 8.1 |
| 1.7 | 8.2 |
| 1.8 | 8.5 |
| 1.9 | 8.6 |
| 1.10 | 4.7 item 2 (ações do maestro) |
| 1.12 / 1.13 | 11.2; 4.8 |
| 1.17 / 1.24 / 1.25 | 4.6; 8.2 |
| 1.19 | 13.1 |
| 1.21 | 11.5 |
| 1.22 | 4.8; 4.9 |
| 2.1 / 2.6 | 10.4 |
| 2.4 | 10.1 |
| 2.8 / 4.28 | 12.1; 15.4 |
| 3.2 / 3.3 / 3.7 | 13.2; B.11 |
| 4.17 | 10.4 |
| 4.30 | 4.7 item 3 |
| 4.33 | 3.4 |
| 5.33 / 6.54 / 6.55 / 6.56 | 15.1 |
| 5.35 | 12.1 |

### C.6 Checagem dos cenários da revisão 3

**(a) CM e RE comprados; MT5 morto às 14:00; stop do RE executa 14:20; alvo do RE enche 15:10; volta 15:30.**
1. 14:20: a S do RE executa; o A do RE fica vivo (sem OCO com o EA fora, Princípio 4b). 15:10: o A enche; ficha do RE −1 (trocada); líquida 0.
2. 15:30: R1 toma a trava (heartbeat velho); R2; R3; R4 fecha com os deals de hoje; R5; R6 (CM +1, RE trocada); R7 sem nada a cancelar; R8 (CM caso A, RE caso B com as horas reais); R9 confere a S do CM e não recoloca o alvo do RE; R10: correção C de compra 1 com o magic do RE, dentro do contínuo, ficha → 0; R11–R13.
3. Entre 15:10 e 15:30 a conta esteve com líquida 0.

**Resposta única e segura: sim.**

**(b) Saída a mercado do C1 volta `TIMEOUT` sem ticket; internet cai 90 s.**
1. 5.2: o C1 não tem A; a S continua viva; a venda é enviada; `TIMEOUT`, ticket 0 → sem desfecho.
2. Desconectado: nada se resolve e nada é enviado; a S protege.
3. Volta a conexão: releitura completa; 10 s depois há leitura confiável. Se a venda executou: o deal aparece, ou o resíduo do C1 prova a execução; a 8.4 nível 2 vê cobertura em excesso e cancela a S; nada é reenviado.
4. Se a venda não chegou: a ordem não está nas pendentes nem no histórico e o resíduo do C1 é igual à ficha → a posição prova "não executada"; o estado fecha; o C1 volta a ver a ficha +1 e a saída é enviada de novo pela regra dele (ou pela zeragem, se o horário passou), com a S viva; executada → S cancelada.
5. Se a cruzada não fechar, nada se resolve; a S segue e o corte de 18:20 zera pelo resíduo.

**Resposta única e segura: sim.**

**(c) Dono zera tudo na mão às 11:00 com GB e DM posicionados e ordens vivas.**
1. Venda manual de 2 (magic 0): nada a compensar na externa; reduz abaixo de Σ fichas → absorção GB, depois DM (8.9).
2. Cancela S e A das absorvidas, depois as E próprias (`ENTRADA_CANCELADA`); bloqueio que exige o dono; push agregado.
3. O botão libera; reinício não rebloqueia (evento reconhecido). GB e DM não reentram (`g_decidido`, `g_decidiu`).

**Resposta única e segura: sim.**

**(d) Primeiro pregão depois de PC desligado desde 17:00 de ontem, DM posicionado com S GTC; gap contra na abertura.**
1. O EA estava fora no corte, então a ficha passou a noite; a S de reserva do DM (GTC) protege.
2. Partida antes das 09:00: R4 recua um pregão e fecha; R8 caso A; R9 confere a S; R10 agenda a saída para `negociacao_inicio`. Nenhum `Tick()` fora do contínuo; o DM fica sem `Tick()` até a ficha zerar; o recálculo do A.3 ignora after-market e pré-abertura.
3. Leilão de abertura: nada é enviado além da S. Se a S disparar no leilão (P13), a ficha zera e a saída agendada não tem o que fazer.
4. Primeiro momento de contínuo: saída a mercado pelo 5.2 com a S viva; executada → S cancelada; recusada → S continua e a saída é retentada a cada 5 s.

**Resposta única e segura: sim.** O que a S faz no leilão depende de P13, mas nenhum caminho deixa a ficha sem S.

**(e) Maestro no PC e na VPS ao mesmo tempo.**
Fora do escopo por decisão do dono (D3): o maestro roda em uma instância só, num único PC. Coberto continua só o caso de dois gráficos no mesmo terminal: o segundo falha na trava (10.1), faz `ExpertRemove` com `g_iniciou` falsa e não cancela ordem, não grava memória nem libera a trava da instância viva.
