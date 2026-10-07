# WinMaestro — especificação

Versão da especificação: 0.3 (2026-10-06). Substitui o WinSeletor v1.00.

Convenções:
- "item X.Y" aponta para `LICOES_DE_PRODUCAO.md`; "P n" aponta para a pergunta n da seção 14.2.
- **"a verificar"** = depende da Rico, da B3 ou da MT5 e ainda não foi confirmado; cada ocorrência cita a pergunta que decide.
- Todo prazo, contagem ou nível tem número. Os números técnicos são constantes do código (tabela 2.2); o dono não ajusta nada além dos inputs da seção 2.1.
- WIN: tick = 5 pontos = R$1,00 por contrato; 1 ponto = R$0,20 por contrato. O EA **lê** esses valores do símbolo (`SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_TRADE_TICK_VALUE`); leitura zerada é repetida (seção 10.2) e nunca é usada (item 5.22).
- Duas posições por robô: **ficha pelos deals** (o que a corretora executou com o magic do robô) e **ficha efetiva** (ficha pelos deals + ordens de execução imediata ainda em trânsito, seção 4.6).

## 0. O que é, em uma frase

Um EA único para o WIN que roda a lógica dos 5 robôs ao mesmo tempo, dá a cada um uma **ficha** (posição virtual própria) e envia à corretora as ordens de cada robô **com o magic do próprio robô**, de modo que a posição líquida da conta NETTING seja sempre a soma das fichas mais a exposição externa conhecida. Com um robô só ligado ele faz o que o WinSeletor fazia; com os cinco ligados cada robô opera como se estivesse sozinho numa conta própria.

### Princípios (valem acima de qualquer detalhe abaixo)

1. **Cada robô decide sozinho, com as regras dele**, inclusive os níveis do próprio stop. O maestro não filtra, não combina, não prioriza sinais; executa, contabiliza e protege.
2. **A verdade sobre o que foi executado é a corretora.** Fichas saem do histórico de deals por magic (seção 3). A memória em disco guarda só o que a corretora não sabe: níveis e instantes de cada robô e o registro de ordens próprias (seção 9).
3. **Invariante:** líquida real no símbolo = Σ fichas efetivas + exposição externa. Divergência confirmada bloqueia entradas novas e cancela as pendentes (seção 8.6).
4. **Proteção mora no servidor.** Todo robô posicionado tem o stop dele como ordem stop pendente na corretora, com validade GTC (seção 4.3). **Exceções conhecidas e aceitas** (a MT5 em netting não tem OCO nem OTO entre ordens independentes): (a) entre o preenchimento de uma entrada e o registro do stop dela, e durante todo o tempo em que o EA estiver fora do ar ou desconectado, a ficha recém-aberta fica sem stop no servidor; (b) com o EA fora do ar, uma ficha com stop e alvo vivos pode ter os dois executados e ficar com o sinal trocado, sem stop; (c) o CincoMedias não tem stop inicial pela regra dele e fica só com a reserva distante (Apêndice B.1). Pior caso numérico na seção 13.4; decisão do dono no Apêndice B.7.
5. **Um caminho de fechamento por vez.** Antes de qualquer saída a mercado, stop e alvo do robô são cancelados com confirmação no histórico (seção 5.1). Nada é enviado duas vezes sem o histórico confirmar o desfecho da primeira (seção 4.6; itens 1.5, 1.6, 1.23, 1.24).
6. **Nenhum bloqueio impede saída ou proteção.** Bloqueios barram entradas; stops, cancelamentos e saídas por horário sempre passam (seção 8.6).
7. **Nada de trava não pedida.** Só existem as proteções técnicas desta especificação (consistência, margem que a corretora recusaria de qualquer forma, cadência de envio, fim de pregão).
8. **Proteção posta pelo dono nunca é apagada pelo robô** (seção 8.7).
9. **Tudo que o EA faz ou decide vira uma linha de log curta, com hora, robô, motivo e números** (seção 11), inclusive o que aconteceu com o EA fora do ar, com a hora real do deal.

## 1. Arquivos e nomes

| Item | Valor |
|---|---|
| EA | `mt5/WinMaestro.mq5` (+ `.ex5`, `_compile.log`) |
| Camada de corretora | `mt5/WinMaestro/Corretora.mqh`: única porta para `OrderSend`, `OrderDelete`, `OrderModify`, `PositionSelect`, `OrdersTotal`/`OrderGet*`, `HistorySelect`/`HistoryDeal*`/`HistoryOrder*`, `AccountInfo*`, `SymbolInfo*` de negociação. Duas implementações: real e falsa (seção 15.2) |
| Demais módulos | `mt5/WinMaestro/*.mqh`: `Fichas.mqh` (fichas, trânsito, execução, reconciliação), `Recupera.mqh` (seção 10.2), `Memoria.mqh` (seção 9), `Log.mqh` (seção 11), `Grade.mqh` (seção 12), um `.mqh` por robô (copiado do WinSeletor e adaptado conforme o Apêndice A) |
| Magics dos robôs | GapBarra1 80080601, CincoMedias 80080501, Desloc 80080101, Retângulo 20261005, Win_c1 80080002 |
| Identificação da instância | `MagicMaestro` = 80080900 e `INST` = `i1` (constantes). Nenhuma ordem sai com `MagicMaestro`; ele é chave de pasta e de trava |
| WinSeletor e EAs avulsos | aposentados (Apêndice B.4): `.mq5` do Seletor como `.bak` no repo; os `.ex5` do Seletor e dos avulsos saem da pasta Experts **e** de todo gráfico aberto antes da primeira partida do maestro |
| Grade de horários | `data/b3_grade_horaria_win.csv` embutida no código (`Grade.mqh`); atualizar a grade = recompilar |

## 2. Inputs e constantes

### 2.1 Inputs

Grupo **Maestro**, no topo da lista:

| Input | Padrão | Efeito |
|---|---|---|
| `Ativo_GapBarra1` … `Ativo_Win_c1` (5 bools) | todos `true` | Robô ligado gera entradas novas. Desligado: não abre nada novo; **se tiver ficha ou ordem viva, continua gerindo até zerar**. Nunca é fechado por ter sido desligado. |

Grupos dos robôs (`WinGapBarra1`, `WinCincoMedias`, …, prefixos `GB_`, `CM_`, `DM_`, `RE_`, `C1_`): como no WinSeletor, com três diferenças:
- os inputs de lote (`CM_Lote`, `DM_Lote`, `RE_Lote`, `C1_Lote`) saem: o lote é a constante 1 (todos os testes usam 1 contrato);
- `GB_ServerGMTOffsetH`, `GB_RegimeAutomatico` e `GB_FimContinuoMin` saem: fuso e fim do contínuo vêm da seção 12.1;
- acrescentam-se, no fim de cada grupo, `CM_ReservaPts` (padrão **4.945**, Apêndice B.1; 0 = sem reserva, aceito com AVISO no `PRONTO` de cada dia) e `DM_ReservaTicks` (padrão **20** = 100 pts, Apêndice B.5).

Os inputs de horário dos robôs continuam e alimentam a tabela de zeragem da seção 12.2 e os cortes de entrada de cada robô.

Mudar inputs reinicia o EA e passa pela recuperação completa (seção 10). O `OnInit` reinicializa explicitamente toda variável global do maestro e chama `Reseta()` de cada módulo, porque as variáveis globais podem sobreviver a `REASON_PARAMETERS` e `REASON_CHARTCHANGE` (a verificar, P17).

### 2.2 Constantes técnicas

| Constante | Valor | Seção |
|---|---|---|
| `LOTE` | 1 | 3.1 |
| `PRAZO_CONFIRMACAO` | 5 s (consulta a cada 250 ms) | 4.6, 5.1 |
| `PRAZO_DESCONHECIDA` | 30 s | 4.6 |
| `PRAZO_SEM_STOP` | 2 s | 8.4 |
| `IDADE_MIN_ORFA` | 5 s | 8.5 |
| `DIVERGENCIA_MIN` | 3 s e 3 leituras | 8.2 |
| `CRUZADA_MAX` | 60 s | 8.2 |
| `PRAZO_HISTORICO_R4` | 60 s | 10.2 |
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
| volume em trânsito | Σ do volume assinado das ordens do robô em trânsito **que executam no envio**: entrada a mercado (C1), saída X e correção C. **Entrada limite contribui 0 em qualquer estado**; S e A contribuem 0 |
| **ficha efetiva** | ficha pelos deals + volume em trânsito. É o que os módulos enxergam (`Ficha_Tem`, `Ficha_Lado`) e o que decide novo envio de E, X ou C |
| preço médio | média ponderada dos deals que afastam a ficha de zero, desde o último zero da ficha |
| hora de abertura | `DEAL_TIME_MSC` do primeiro deal da ficha atual |
| resultado realizado | Σ, para cada deal que aproxima a ficha de zero, (preço do deal − preço médio) × volume × lado × valor do ponto lido do símbolo, menos `DEAL_COMMISSION` e `DEAL_FEE` |

Regras:
- `DEAL_ENTRY` e `DEAL_PROFIT` não entram na ficha: em netting descrevem a líquida. `DEAL_PROFIT` só aparece na conferência do resumo do dia (11.5).
- Deals `BALANCE`, `CREDIT`, `CHARGE`, `CORRECTION` e variação de margem (`DEAL_REASON_VMARGIN`) não entram no volume; cada um é logado uma vez (`AJUSTE`).
- Estados válidos da ficha pelos deals: 0 ou ±1.
- **Ficha trocada** = ficha pelos deals com sinal oposto ao do deal de abertura do ciclo atual (duas saídas da mesma ficha). É detectada aqui, na própria `Ficha_Recalcula`, exigindo só a verificação cruzada fechando (3.2). Ficha trocada **nunca é mostrada ao módulo** (`Ficha_Tem` = falso, módulo suspenso até a ficha voltar a 0) e é tratada só pela seção 8.3.
- Ficha cujo deal de abertura é anterior ao início do pregão de hoje é **ficha de pregão anterior** (seção 12.4).

### 3.2 Janela de reconstrução e verificação cruzada

O histórico é lido desde o **último instante em que a líquida do símbolo foi zero**:
1. Início: `negociacao_inicio` de hoje − 10 min.
2. `S` = Σ do volume assinado de todos os deals BUY/SELL do símbolo, de todos os magics, desde o início.
3. `S` ≠ líquida real → recua um pregão e repete, até 10 pregões.

**Verificação cruzada** = `S` da janela vigente igual à líquida real. A API não tem indicador de "histórico carregado"; esta conta é o indicador. Se ela não fecha em 10 pregões, vale o prazo de R4 (10.2): a diferença vira exposição externa de origem desconhecida.

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
| `PositionSelect(_Symbol)` + magic | `Ficha_Tem(robo)` (ficha efetiva ≠ 0 e não trocada) |
| "tem posição de outro robô, não entro" (CM L774, DM L379, C1 L620) | removido |
| `POSITION_PRICE_OPEN/TYPE/TIME/VOLUME` | `Ficha_Preco`, `Ficha_Lado`, `Ficha_Hora`, `Ficha_Volume` |
| `POSITION_SL` | `Ficha_Stop(robo)` = **nível pedido pelo próprio robô** (0 se ele não pediu). A reserva do CM e do DM nunca aparece aqui, para a lógica do robô ficar igual à do avulso |
| `POSITION_COMMENT`, `HistorySelectByPosition` | `Ficha_Marca(robo)` (4.2) |
| `PositionClose` | `Ficha_Fecha(robo, motivo)`: protocolo 5.2, volume da ficha, magic do robô |
| `PositionModify(sl)` | `Ficha_DefineStop(robo, nivel, motivo)` (4.7) |
| `trade.Buy/Sell` com SL | `Ficha_EntraMercado(robo, lado, stop, motivo)` |
| `BuyLimit/SellLimit` de entrada | `Ficha_EntraLimite(robo, lado, preco, stop, alvo, validade, expira, motivo)` |
| `BuyLimit/SellLimit` e `OrderModify` de alvo | `Ficha_DefineAlvo(robo, nivel, motivo)` |
| `OrderDelete` | `Ficha_CancelaOrdem(robo, papel, motivo)` |
| `OrdemPendente()`, `OrderSelect(g_ordem)` | `Ficha_Entrada(robo)` → {existe, lado, preço, hora de envio} |

Toda função de envio devolve `ENVIADA`, `RECUSADA` (retcode), `BLOQUEADA` (motivo) ou `JA_EM_TRANSITO`. O módulo trata `RECUSADA` e `BLOQUEADA` como hoje trata falha de `OrderSend` (item 4.33).

**Avisos ao módulo:** callback único `Robo_Evento(robo, evento, dados)`, com os eventos:

| Evento | Quando |
|---|---|
| `ENTRADA_CANCELADA` | o maestro cancelou a E do robô (bloqueio 8.6, autonegociação 4.9, rede de fim de dia, `OnDeinit`) |
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
| Saída por regra, zeragem, correção (X, C) | mercado oposta, volume 1, depois do protocolo 5.2 | — |
| Saída agressiva (5.4) | limite oposta agressiva | DAY |

Preenchimento: limite com `ORDER_FILLING_RETURN` e desvio 0; mercado com `RETURN` se `SYMBOL_FILLING_MODE` permitir, senão `IOC` (a verificar, P15). Stop-limit no lugar de stop e `SPECIFIED` no lugar de GTC para a S são implementados **só se P1/P15 mostrarem que a Rico não aceita** `*_STOP` ou GTC no WIN. Se a S precisar de `SPECIFIED`, a validade é o fim do contínuo do pregão seguinte e o timer a renova na virada de cada pregão.

### 4.2 Comentário

`MAE|i1|<robo>|<papel>|<seq>[|<marca>]` — `robo` = GB, CM, DM, RE, C1; `papel` = E, S, A, X, C; `seq` = 5 dígitos por robô, um por ordem, persistido no estado permanente (9.1), volta a 00001 depois de 99999; `marca` = 1 caractere do robô (CM: `F` a favor do mês, `N` neutra). Exemplo: `MAE|i1|CM|E|00042|F` (19 caracteres). Busca pelo comentário sempre restrita às ordens com `ORDER_TIME_SETUP` desde o início da janela (3.2), para a volta do `seq` não colidir. Limite de comprimento e preservação pela corretora: a verificar (P3).

### 4.3 Stop no servidor

O SL/TP da posição líquida não é usado (vale para a soma). Cada robô posicionado tem a sua S.

- **Quando nasce: só com deal.** Entrada limite: na mesma chamada em que o deal de entrada é visto (`OnTradeTransaction` ou reconciliação). Entrada a mercado (C1): na mesma execução de `Ficha_EntraMercado`, logo depois do retorno do `OrderSend` com `deal ≠ 0`; sem deal no retorno, quando 4.6 confirmar. O atraso deal→S aceita é logado em toda abertura.
- **GB, RE, C1:** S no nível pedido pelo robô.
- **CM:** S de reserva a `CM_ReservaPts` do preço da ficha desde o preenchimento (B.1). Quando o "stop que aperta" nasce, a mesma S é movida para o nível dele. Com `CM_ReservaPts = 0` e sem stop que aperta, o CM fica sem S (exceção c).
- **DM:** stop controlado pelo EA + S de reserva `DM_ReservaTicks` além (5.5).
- **GTC** (B.6): ficha que atravessa a noite por falha do EA continua protegida. O risco oposto (S órfã sobreviver) é coberto pelo passo R7 da recuperação, que cancela órfãs antes de qualquer outra ordem, e pela reconciliação (8.5).
- Onde a S mora (servidor da Rico ou B3) e o que vira ao disparar em leilão ou banda: a verificar (P1, P13); o caso "disparou e não executou" está em 5.4.

### 4.4 Atribuição dos deals e ordens próprias

**Ordem própria** = ticket presente no **registro de ordens próprias** (9.2) **ou** comentário com prefixo `MAE|i1|`. O registro guarda cada ordem enviada enquanto ela, ou a ficha que ela abriu, existir, atravessando pregões.

| Deal ou ordem do símbolo | Tratamento |
|---|---|
| magic de robô, própria | ficha desse robô |
| magic de robô, **não** própria, criada (`ORDER_TIME_SETUP_MSC`) depois do primeiro heartbeat desta instância | **estranha** (outra instância ou EA avulso): bloqueio total, 10.1 |
| magic de robô, não própria, anterior ao primeiro heartbeat (memória perdida) | ficha desse robô, AVISO `ORIGEM NAO CONFIRMADA` |
| outro magic (0 = manual, outros EAs) ou `DEAL_REASON` em {`CLIENT`, `MOBILE`, `WEB`, `SO`} sem magic de robô | deal externo, 8.9 |

Não existe ficha sem dono: toda ordem do maestro leva o magic de um robô.

### 4.5 Ordem de processamento

Num mesmo ciclo: primeiro cancelamentos e saídas, na ordem fixa GB, CM, DM, RE, C1; depois as entradas, na mesma ordem. Envios seriais: o próximo só sai depois do retorno do anterior; dentro de um robô, S antes de A. Diferença conhecida em relação ao avulso: em hora cheia a última entrada da fila sai centésimos de segundo depois da primeira e o GB tem prioridade de fila sistemática (relatório 15.1).

### 4.6 Ordens em trânsito

Toda ordem enviada entra no **registro de trânsito** antes do `OrderSend`: robô, papel, `seq`, comentário, volume que altera a ficha (só E a mercado, X, C), ticket e `request_id` (preenchidos no retorno, podem ficar 0), hora de envio. O registro é gravado na memória antes do envio (9.3).

**Saída do trânsito (desfecho confirmado):**
- deal(s) com `DEAL_ORDER` = ticket → executada;
- ordem no histórico com `CANCELED`, `REJECTED` ou `EXPIRED` → não executada;
- ordem pendente listada (E, S, A) → sai do trânsito e passa a ser reconhecida pelo papel (3.3).

`DONE`/`PLACED` sem deal, `OrderSend` falso e retcode de transporte (`TIMEOUT`, `CONNECTION`, `ERROR`) com ticket 0 são **"não sei"**, nunca "não executou" (itens 1.6, 1.17, 1.24). A ordem é procurada por ticket, `request_id` (`TRADE_TRANSACTION_REQUEST`) e comentário a cada 250 ms durante `PRAZO_CONFIRMACAO` (5 s). Sem desfecho, vira **`DESCONHECIDA`** (ALERTA) e segue as regras abaixo, que valem durante o pregão e na recuperação.

**Enquanto `DESCONHECIDA`:**
1. Bloqueia só novas ordens do robô que alterem a ficha ou repitam o papel: E, X e C (`JA_EM_TRANSITO`). **S e cancelamentos nunca são bloqueados.**
2. A necessidade de S é decidida pela **ficha pelos deals** e pela líquida real, não pela efetiva: ficha pelos deals ≠ 0, com X ou C desconhecida há mais de 5 s **e a líquida real inalterada desde o envio** → a S é recriada (pior caso: a ordem não executou e a posição real continua). Se a X executar depois, a S vira órfã e cai em 8.5.
3. A consulta continua a cada 1 s.

**Resolução obrigatória em `PRAZO_DESCONHECIDA` (30 s)** — nenhuma `DESCONHECIDA` dura mais que isso:

| Situação aos 30 s | Resolução |
|---|---|
| nenhum vestígio da ordem (ticket, `request_id`, comentário) nas pendentes nem no histórico, **verificação cruzada fechando** e líquida real inalterada desde o envio | `NAO_EXECUTADA` (ALERTA): sai do trânsito; a ficha efetiva volta a ser a pelos deals; a S existe (regra 2); o módulo ou o maestro pode enviar de novo, com `seq` novo |
| líquida real mudou exatamente o volume e o lado da ordem, sem outra ordem própria em trânsito que explique | `EXECUTADA_SEM_DEAL` (ALERTA): a ficha efetiva mantém o volume da ordem; nenhuma S é recriada; quando o deal aparecer, a ficha pelos deals o absorve |
| qualquer outra (cruzada não fecha, líquida mudou de forma diferente) | `INDETERMINADA` (ALERTA com push): a ordem continua bloqueando só E, X e C **desse robô**; a S fica garantida pela regra 2 enquanto a líquida real for compatível com a ficha pelos deals; a releitura completa (8.1) roda a cada 10 s; o caso se resolve sozinho quando a cruzada fechar (aí cai numa das duas linhas acima) |

Nada é reenviado por inferência: o único caminho para reenviar é `NAO_EXECUTADA`, que exige histórico completo (cruzada fechando) e nenhum vestígio da ordem. O log registra quanto tempo cada ordem ficou sem desfecho.

### 4.7 Mover o stop

1. Mover = `OrderModify` da S existente; nunca cancelar e recriar.
2. **O nível é o que o robô pede.** Se a regra do robô afrouxa o stop (trailing do C1, que segue `wma ± K×ATR` nos dois sentidos), o maestro afrouxa igual. "Nunca afrouxa" vale só para as ações do próprio maestro (recriação de 8.4, recuperação, correção): nelas o nível nunca é menos protetor que o último registrado (item 1.10).
3. **Nível atravessado** é checado pelo módulo, com a fonte de preço dele no avulso (C1 e CM: bid na compra, ask na venda, 1 tick; DM: last, com bid/ask quando last = 0). O maestro, nas ações próprias, usa last com o mesmo fallback do DM, mais o piso `max(1 tick, SYMBOL_TRADE_STOPS_LEVEL)` (itens 1.25, 4.30).
4. Nível atravessado → saída pelo protocolo 5.2 (a S antiga é cancelada com confirmação antes).
5. `OrderModify` recusado: a S antiga continua viva (proteção mantida), o log registra, e a retentativa segue 4.8. Nível 0 vindo de um módulo é ignorado com ERRO, nunca apaga a S.

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

## 5. Protocolo de cancelamento confirmado, saída e OCO

### 5.1 Cancelamento confirmado

Cancelamento confirmado = ordem no **histórico** com `CANCELED` ou `EXPIRED`. O retcode do `OrderDelete` não basta: em bolsa o cancelamento é assíncrono e o desfecho pode ser FILLED (item 1.5).

1. Envia `OrderDelete` (registrado no trânsito).
2. **Na mesma chamada**, logo após o retorno, consulta o histórico. No Testador o desfecho está sempre lá; no real, frequentemente.
3. Sem desfecho na mesma chamada: consulta a cada 250 ms por até `PRAZO_CONFIRMACAO` (5 s).
4. Desfechos: `CANCELED`/`EXPIRED` → confirmado; `FILLED`/`PARTIAL` → executou; quem pediu é avisado (`EXECUTOU_ANTES`); prazo esgotado → "não sei": a ordem segue tratada como viva (invariante e margem) e a reconciliação repete o passo 1 a cada 5 s.
5. O tempo até a confirmação é logado (P5).

### 5.2 Saída a mercado

Vale para toda saída a mercado: regra do robô, stop do EA do DM, nível atravessado, zeragem, rede de segurança, pregão anterior, horário perdido e correção.

1. Cancela, em série, S, depois A e X-limite do robô (5.1).
2. Todos confirmados → envia a mercado, volume = |ficha efetiva|, lado oposto, **no mesmo tick** se as confirmações vieram na mesma chamada.
3. Algum `FILLED` → **não envia**: recalcula a ficha; se ainda ≠ 0, recomeça.
4. Algum "não sei" → **não envia**; repete o passo 1 a cada 5 s até haver desfecho; ALERTA após 30 s. Enquanto isso a S (se o "não sei" for de outra ordem) segue protegendo.
5. Saída recusada por leilão, túnel ou banda → 5.4.

No Testador o atraso desta sequência é zero: qualquer saída em tick diferente do avulso é defeito (15.1). No real o atraso é logado em toda saída.

### 5.3 OCO

1. Deal de S ou A levando a ficha a zero → cancela as ordens restantes do robô (5.1) antes de qualquer outra ação do ciclo.
2. Com o EA fora do ar não há OCO (Princípio 4b). O RE é o único robô com alvo no padrão; é decisão consciente do dono (B.9).
3. Na recuperação, as irmãs são canceladas no R7 e a ficha trocada é tratada no R10 (8.3).

### 5.4 Stop disparado sem execução e saída recusada

**Detecção:** S que sai das pendentes sem deal com `DEAL_ORDER` = ticket em 2 s e com estado `REJECTED`/`CANCELED` sem pedido do maestro; ou saída X/C recusada pela corretora.

**Ação:** ALERTA com push e saída por **limite agressiva** a último ∓ 3 ticks, dentro da banda; reenviada a cada 5 s fora de leilão (cancelamento 5.1 antes de cada reenvio), no máximo 6 por minuto, ALERTA a cada 3 min sem preenchimento. Em leilão (fase da grade da data; leilão por variação detectado pela recusa), a ordem fica como limite no preço da proteção para participar do leilão, se a B3 aceitar (P13). As tentativas contam no disjuntor.

### 5.5 DM: stop do EA e reserva no servidor

- **Stop do EA** (fiel ao testado): quando o preço (last; bid/ask se last = 0) cruza `g_stopNivel`, o módulo pede `Ficha_Fecha` e o maestro executa 5.2.
- **Reserva**: S a `DM_ReservaTicks` (20 ticks = 100 pts) **além** de `g_stopNivel`. Os dois caminhos nunca ficam no mesmo nível (itens 1.4, 1.23). Ela só dispara se o EA não agiu ou se o preço saltou mais de 100 pts num só negócio. Custo com o EA fora: até R$20 por contrato além do stop testado.
- **No Testador a reserva existe.** O Testador executa as pendentes antes do `OnTick`; a reserva só executa num tick que atravessa `g_stopNivel` e a reserva de uma vez, e nesse tick o avulso sairia ao preço do mesmo tick. Esperado: mesmo preço de saída, caminho S em vez de X. O relatório 15.1 lista esses trades; diferença de preço neles é defeito.

## 6. Estado do ciclo de cada robô

O estado **não é armazenado**: é derivado a cada reconciliação de (ficha pelos deals, ordens vivas por papel, registro de trânsito, protocolo em curso). A memória guarda só níveis e instantes. Função de derivação, na ordem de precedência:

| Condição | Estado |
|---|---|
| ficha trocada | `TROCADA` (8.3) |
| ordem do robô `DESCONHECIDA` ou `INDETERMINADA` | `TRANSITO_DESCONHECIDO` |
| protocolo 5.2 em curso | `SAINDO` |
| ficha ≠ 0 sem S viva | `POSICIONADO_SEM_STOP` (ALERTA após `PRAZO_SEM_STOP`, 8.4) |
| ficha ≠ 0 com S viva | `POSICIONADO` |
| ficha 0 com E em trânsito | `ENTRADA_ENVIANDO` |
| ficha 0 com E viva | `ENTRADA_PENDENTE` |
| ficha 0, nada vivo | `LIVRE` |

Cada mudança do estado derivado gera uma linha de log.

## 7. Eventos do MT5

| Evento | Real | Testador |
|---|---|---|
| `OnInit` | Reinicializa toda variável global, `Reseta()` dos módulos, liga o timer, recuperação em R0, devolve `INIT_SUCCEEDED`. Não espera conexão, não lê histórico, não envia ordem | igual |
| `OnTimer` | 250 ms: máquina da recuperação, consultas de trânsito e cancelamento. A cada 1 s: reconciliação, cortes de horário (12), heartbeat da trava, gravação acumulada. A cada 60 s: varredura de outros símbolos (8.8) | 1 s, só cortes de horário |
| `OnTick` | marca a reconciliação "suja"; em `PRONTO`, `Tick()` de cada robô ligado ou com ficha/ordem viva, na ordem 4.5 | igual, mais reconciliação a cada M1 nova |
| `OnTradeTransaction` | linha bruta no log de transações; deal novo → `Ficha_Recalcula`, OCO, trânsito, memória; ordem cancelada/rejeitada → trânsito e aviso ao módulo; deal com hora anterior ao último instante processado → releitura completa (8.1) | igual (é o caminho principal) |
| `OnChartEvent` | botão de desbloqueio (8.6) | — |
| `OnDeinit` | Loga `FIM` e o `reason`. Se `reason` ∉ {`PARAMETERS`, `CHARTCHANGE`, `TEMPLATE`}: envia o cancelamento de todas as E (sem esperar confirmação; a recuperação seguinte confere; P24). Nunca cancela S nem A, nunca fecha posição. Grava memória, libera a trava | grava log |

`OnTradeTransaction` não é garantido; a reconciliação é o caminho seguro. O cancelamento de E no `OnDeinit` não cobre queda de energia, processo morto nem internet caída (Princípio 4a).

## 8. Reconciliação contínua

### 8.1 Cadência

- Recálculo no máximo 1× por segundo, mais um imediato a cada deal. Incremental: `HistorySelect(último instante − 60 s, agora)`, deduplicando por ticket de deal.
- **Releitura completa da janela** (3.2) imediatamente em: `TERMINAL_CONNECTED` falso→verdadeiro; verificação cruzada sem fechar; deal recebido com hora anterior ao último instante processado. Fora isso, a cada 10 min.
- Nenhum módulo chama `HistorySelect*`.

A cada reconciliação: lê a líquida real (`PositionSelect` falso com erro é leitura descartada, item 1.6); recalcula fichas e trânsito; compara líquida com Σ fichas efetivas + externa; confere invariantes (3.3); loga a margem para diagnóstico (13.2).

### 8.2 Confirmação de divergência

Uma diferença só é **divergência confirmada** quando, ao mesmo tempo: persiste por ≥ 3 s e em ≥ 3 leituras com histórico refeito; nenhuma ordem em trânsito a explica em quantidade e lado (lado nunca é explicado por trânsito, item 1.25); e a verificação cruzada fecha.

- Divergência confirmada → bloqueio de entradas (8.6) e ALERTA. Correção só para a ficha trocada (8.3); qualquer outra fica bloqueada até o dono (item 1.7).
- **Verificação cruzada sem fechar por mais de `CRUZADA_MAX` (60 s)** → bloqueio de entradas (do tipo que sai sozinho, com E canceladas) e ALERTA repetido a cada 5 min; releitura completa a cada 10 s; nenhuma correção.

### 8.3 Ficha trocada (única correção automática)

Causa: duas saídas da mesma ficha (S + A, S + X, A + X, X duplicada), ficha pelos deals de ±1 para ∓1.
1. Módulo suspenso (3.1); a 8.4 não age sobre a ficha trocada.
2. Protocolo 5.2 com o **magic do robô** e papel C: cancela o que restar do robô e leva a ficha a 0.
3. No máximo uma correção por ficha a cada 10 min. Segunda ficha trocada no prazo → bloqueio que exige o dono (item 1.13), sem correção.
4. ALERTA com os tickets das duas saídas e o resultado da correção.

### 8.4 Ficha posicionada sem stop

Ficha **pelos deals** ≠ 0 (não trocada) há mais de `PRAZO_SEM_STOP` (2 s), sem S viva nem S em trânsito, com a líquida real compatível (regra 2 de 4.6):
1. recria a S no nível da memória;
2. sem nível: recalcula pela regra do robô (Apêndice A);
3. sem regra possível: `STOP_EMERGENCIA_PTS` do preço da ficha, ALERTA;
4. nível já atravessado: 4.7 item 4.

Entrada limite viva não gera S: a S só nasce com deal. Recusas seguem 4.8.

### 8.5 Ordem órfã

Ordem com magic de robô é órfã (sem papel válido por 3.3) só se: está fora do trânsito; tem mais de `IDADE_MIN_ORFA` (5 s) de vida; e a verificação cruzada fecha. Ação: cancela (5.1), loga `ORFA`. Ordem de magic desconhecido: não toca, loga uma vez.

### 8.6 Bloqueio

Dois tipos:

| Tipo | Causas | O que barra | Como sai |
|---|---|---|---|
| **de entradas** | divergência confirmada (8.2), cruzada sem fechar (8.2), ficha trocada repetida (8.3), intervenção externa redutora (8.9), SL/TP na líquida (8.7), ordem em outro símbolo (8.8), recuperação em `PROTEGENDO` | E | sozinho quando a causa some, ou pelo botão quando a causa exige o dono |
| **total** | ordem estranha (4.4, 10.1) | E e saídas por regra dos robôs (a outra instância também as enviaria) | só pelo botão |

**Nunca são barrados**, em nenhum tipo: S (criar, mover, recriar), cancelamentos, saída agressiva (5.4) e todas as saídas por horário do maestro (zeragem de cada robô, ficha de pregão anterior, horário perdido, rede de segurança). No bloqueio total, cada saída por horário só é enviada se a líquida real ainda tiver o lado e o volume da ficha (item 1.25).

Ao entrar em qualquer bloqueio: todas as E são canceladas (5.1) e os módulos recebem `ENTRADA_CANCELADA` (item 1.9); log ALERTA uma vez, com a causa.

**Bloqueio que exige o dono** é identificado pelo evento que o causou (ticket do deal ou da ordem). **Botão no gráfico** (`OBJ_BUTTON` "Desbloquear", visível só com bloqueio desse tipo ativo; confirmação por dois cliques em até 3 s; tratado em `OnChartEvent`): grava os tickets como **reconhecidos** no estado permanente (9.1), libera o bloqueio sem reiniciar o EA e loga `DESBLOQUEIO` com os tickets. A recuperação só reativa bloqueio de evento não reconhecido. Depois do desbloqueio nenhum robô reenvia entrada cancelada (padrão do Apêndice A).

### 8.7 SL/TP na posição líquida

O maestro nunca põe SL/TP na líquida. Encontrou: **não remove** (foi um stop anexado à mão que encerrou o incidente de 2026-08-28, Parte 0); bloqueio de entradas que exige o dono; ALERTA com push. Se esse SL/TP executar, o deal é intervenção externa redutora (8.9).

### 8.8 Ordens e posições em outros símbolos

No R2 e a cada 60 s: varre posições e ordens de todos os símbolos com magic de robô. Fora do símbolo do gráfico (ex.: contrato velho): bloqueio de entradas que exige o dono, ALERTA. O maestro não mexe no outro símbolo.

### 8.9 Intervenção externa

Deal externo (4.4) é classificado no instante em que é visto, nesta ordem:
1. **Compensa a exposição externa existente** de sinal oposto (o dono fechando a posição manual dele). Essa parte só altera a externa, sem bloqueio.
2. O que sobrar e **aumentar** |líquida| → exposição externa (ALERTA uma vez por mudança); as fichas seguem; a externa entra no cálculo de margem.
3. O que sobrar e **reduzir** |líquida| abaixo de Σ fichas → **intervenção externa redutora** (zeragem manual, mesa da corretora, zeragem compulsória P11, stop-out `DEAL_REASON_SO`, SL/TP do dono):
   - absorção nas fichas do lado reduzido, na ordem fixa GB, CM, DM, RE, C1 (B.8); cada ficha absorvida vai a 0 com o preço do deal externo, log `ABSORVIDA`. A absorção é função determinística do histórico: a recuperação sem memória chega ao mesmo resultado;
   - cancelamento imediato (5.1), primeiro das S e A das fichas absorvidas (viram entradas nuas), depois de todas as E;
   - bloqueio de entradas que exige o dono; ALERTA com push.

## 9. Memória

### 9.1 Onde

- **Estado de pregão**: `MQL5/Files/WinMaestro/<servidor>_<conta>_<símbolo>_i1/estado.txt` (+ `.bak`, `.tmp`) e `logs/`.
- **Estado permanente**: `MQL5/Files/Common/WinMaestro/permanente/<servidor>_<conta>_i1.txt` (`FILE_COMMON`, não depende do símbolo, sobrevive à rolagem): `seq` de cada robô, resultado acumulado do DM (13.3), tickets de eventos reconhecidos pelo botão (8.6).
- **Testador**: tudo em `MQL5/Files/WinMaestro_teste/` do agente, **nunca** em `FILE_COMMON` (no Testador `FILE_COMMON` é a pasta comum real da máquina). Apagado no início de cada teste.

### 9.2 O que guarda

Formato `chave=valor`, legível no Bloco de Notas.
- Cabeçalho: versão do formato e do EA, servidor, conta, símbolo, data do pregão, último ticket de deal e último instante processados, heartbeat (`TimeTradeServer` e `TimeLocal`), hora do primeiro heartbeat desta instância.
- Registro de trânsito (4.6).
- **Registro de ordens próprias** (4.4): ticket, comentário, papel, robô, hora. Uma ordem sai do registro quando ela está fechada **e** a ficha que ela abriu voltou a 0. Atravessa pregões.
- Bloqueios ativos com o evento causador.
- Por robô: níveis de stop e alvo pedidos, marca da entrada e as variáveis do Apêndice A. **Instantes, nunca contagens.**

### 9.3 Quando grava

Na hora: antes de cada `OrderSend`, a cada deal, a cada mudança de nível de stop ou alvo, a cada bloqueio e desbloqueio, no `OnDeinit`. Demais mudanças: no máximo 1× por segundo. Heartbeat: a cada 10 s.

### 9.4 Como grava

Escreve `estado.tmp` inteiro, última linha `fim=<checksum>`, `FileFlush`, `FileClose`; copia `estado.txt` → `estado.bak`; move `.tmp` → `.txt` com `FILE_REWRITE`. Leitura: ausente, tamanho zero, sem `fim=` ou checksum errado = corrompido → `.bak`; os dois corrompidos → caso C (10.3), ALERTA.

### 9.5 Validade

- Outro servidor ou outra conta → ignorada; caso C; ALERTA.
- Outro pregão → mantém o registro de ordens próprias, o trânsito não resolvido, os bloqueios e o estado de fichas que continuam abertas; descarta o resto.
- Estado permanente perdido: `seq` = maior `seq` nos comentários `MAE|i1|<robo>|` do histórico completo; resultado do DM = soma de 3.1 sobre todos os deals do magic do DM com comentário de origem `MAE|i1|`. Log `MEMORIA reconstruida`.

## 10. Recuperação na partida

Toda partida (primeira do dia, mudança de input, volta de queda) passa por aqui **antes de qualquer atividade**: nenhum `Tick()` de robô e nenhuma entrada antes de `PRONTO`.

### 10.1 Exclusividade de instância

- **Trava**: variável global do terminal `WinMaestro.lock.<conta>.<símbolo>`, tomada com `GlobalVariableSetOnCondition(nome, <chart_id>, 0)`; heartbeat `WinMaestro.hb.<conta>.<símbolo>` = `TimeLocal()` a cada 1 s. Trava de outro gráfico com heartbeat < 10 s → recusa iniciar (`Alert`, push, `ExpertRemove`). Heartbeat ≥ 10 s → toma a trava (`SetOnCondition` com o valor antigo), AVISO.
- **Entre terminais ou máquinas** (PC + VPS, EA avulso esquecido): nenhuma trava alcança; a detecção é a da ordem estranha (4.4) → bloqueio total, ALERTA com push.
- No Testador a trava é pulada.

### 10.2 Máquina de estados

Avançada pelo timer e pelo `OnTick`. Cada passo loga início, fim e números. Todo passo é reentrante: repeti-lo não envia nada que já esteja vivo.

| Estado | O que faz | Prazo / falha |
|---|---|---|
| `R0` | `OnInit` terminou | — |
| `R1_TRAVA` | 10.1 (pulado no Testador) | falha → `RECUSADO` |
| `R2_CONEXAO` | `TERMINAL_CONNECTED` e tick válido (pulado no Testador) | log a cada 30 s; ALERTA após 5 min; nenhuma ordem |
| `R3_AMBIENTE` | conta NETTING; símbolo negociável (`SYMBOL_TRADE_MODE_FULL`; `WIN$N`/`WIN@` só no Testador); modos de validade e preenchimento; valor do tick; limites (`ACCOUNT_LIMIT_ORDERS`, `SYMBOL_VOLUME_LIMIT`, AVISO se < 15 pendentes); notificações habilitadas (senão AVISO diário); outros símbolos (8.8). Leitura zerada é repetida por 60 s antes de concluir falha | falha → `RECUSADO` se não houver ficha nem ordem viva de magic de robô; com elas, `PROTEGENDO` |
| `R4_HISTORICO` | janela de reconstrução fecha (3.2) | prazo `PRAZO_HISTORICO_R4` (60 s): esgotado, usa a janela mais longa disponível, registra a diferença como **exposição externa de origem desconhecida**, ALERTA com push e segue para R5 marcando `PROTEGENDO` ao fim |
| `R5_MEMORIA` | lê estado de pregão e permanente (9.4, 9.5) | corrompida → caso C |
| `R6_RECONSTROI` | fichas (3.1), trânsito gravado (4.6: as regras de `DESCONHECIDA` valem aqui também), deals externos e absorção (8.9), bloqueios de eventos não reconhecidos | — |
| `R7_ORFAS` | **antes de qualquer outra ordem**: cancela toda S/A/X-limite sem ficha, irmãs de fichas que zeraram com o EA fora, E que nenhum robô reconhece (8.5, 5.1) | cancelamento sem desfecho → segue; a reconciliação repete |
| `R8_COMPARA` | memória × corretora por robô: casos A, B, C (10.3) | — |
| `R9_PROTEGE` | toda ficha ≠ 0 com exatamente uma S (8.4); alvo do RE no nível da memória | S recusada → cadência 4.8, segue |
| `R10_PENDENCIAS` | ficha trocada (8.3); agenda ficha de pregão anterior e horário perdido (12.4) — agendar, não esperar | — |
| `R11_INICIA` | `Init()` de cada robô com o estado restaurado (handles, pré-carga do RE, histórico de volume do CM) | — |
| `R12_RECALCULA` | recálculo específico de cada robô (10.4) | — |
| `R13_PRONTO` | grava memória; lê o capital de referência (13.1); log `PRONTO` com resumo e histórico do dia (11.4) | — |

**`PROTEGENDO`** é um modo explícito, não um passo: módulos parados, entradas bloqueadas; o maestro mantém as S (8.4), detecta stop sem execução (5.4), cancela órfãs (8.5), executa as saídas por horário (12) e a rede de segurança, e repete a causa (R3 que falhou, cruzada que não fechou) a cada 30 s. Sai para R11 quando a causa some. Log ALERTA ao entrar, AVISO a cada 5 min, INFO ao sair.

### 10.3 Casos por robô (R8)

- **A. Confere** (ficha e ordens batem com a memória): restaura níveis e instantes.
- **B. A corretora andou com o EA fora** (stop ou alvo executou, entrada encheu, validade venceu, intervenção externa): a corretora vence; cada evento perdido é logado com a hora real do deal. Entrada que encheu fora ganha a S no R9 com o nível da memória.
- **C. Sem memória utilizável:** ficha pela corretora; níveis recalculados das barras (Apêndice A); sem como recalcular o stop, nível da S viva; sem S viva, `STOP_EMERGENCIA_PTS`. ALERTA.

### 10.4 Recálculo específico e decisão atrasada (R12)

Sem replay genérico de velas: cada robô faz o recálculo que o avulso já fazia ao reiniciar, agora com os instantes persistidos (Apêndice A). Os defeitos de reinício conhecidos continuam corrigidos pela persistência (GB não duplica a entrada; CM e C1 não reentram na mesma vela; DM não perde o stop do EA; RE não perde o alvo que se aproxima).

Decisão de entrada cujo momento de envio passou com o EA fora:
- o maestro avisa o módulo com `ENTRADA_REENVIAVEL` **só** se a validade da regra não venceu e o preço limite **não é executável agora** (compra: preço < melhor oferta; venda: preço > melhor demanda); o módulo decide pela regra dele (Apêndice A);
- caso contrário: `DECISAO PERDIDA` (itens 2.1, 2.6, 4.17);
- entrada a mercado (C1) mais de 60 s depois da abertura da vela de sinal: sempre `DECISAO PERDIDA`.

## 11. Logs

### 11.1 Onde

- Diário do MT5 e `logs/AAAA-MM-DD.log`: uma linha por evento (11.3).
- `logs/AAAA-MM-DD_trans.log`: uma linha bruta por evento de `OnTradeTransaction` do símbolo (tipo, ordem, deal, estado, preço, volume, magic, `request_id`).
- Arquivo em acréscimo, `FileFlush` a cada linha.

### 11.2 Formato, níveis e notificações

`HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe | [tick HH:MM:SS.mmm loc HH:MM:SS]`

- Hora principal = `TimeTradeServer()` com ms; depois, hora do último tick e hora local.
- `NIVEL`: `INFO`, `AVISO`, `ALERTA`, `ERRO`. `ROBO`: `GB`, `CM`, `DM`, `RE`, `C1`, `MAESTRO`.
- Linha de ordem traz: ticket da ordem e do deal, `request_id`, `retcode` e `retcode_external`, **preço pedido e preço executado** lado a lado (item 4.15), líquida antes → depois.
- Anti-spam por **objeto** (ticket ou ficha), não por processo (item 1.12): a mesma condição sobre o mesmo objeto é logada ao começar, a cada 5 min com contador e ao terminar.
- **ALERTA** dispara `Alert()` e entra na **fila de push**: dedupe por (evento, objeto) — o mesmo par no máximo 1 push a cada 5 min; frequência — no máximo 1 `SendNotification` a cada 10 s (dentro do limite da MT5, a verificar na documentação vigente, P25); alertas que chegam durante a espera são agregados numa mensagem (`3 alertas: CM STOP SEM EXECUCAO; RE ABSORVIDA; BLOQUEIO externa`). Falha de `SendNotification` é logada como ERRO.

Exemplos:
```
10:00:00.140 | INFO   | CM | ORDEM    | E sell limit 1 @176855 ord #48211 req 37 rc 10008/0 MAE|i1|CM|E|00042|F
10:03:12.501 | INFO   | CM | ENTROU   | vendido 1; pedido 176855 exec 176855 deal #9912; liquida +1 -> 0
10:03:12.690 | INFO   | CM | STOP     | S buy stop 1 @181800 ord #48230 (reserva); atraso 189 ms
12:00:00.410 | INFO   | CM | CANCELA  | S #48230 CANCELED confirmado em 402 ms
12:00:00.560 | INFO   | CM | SAIU     | EMA; compra 1 deal #9987 exec 176210; +129,00; liquida 0 -> +1
09:00:02.300 | ALERTA | MAESTRO | RECUPERA | EA fora 09:41-10:12; DM: S executou 09:58 @190165 (-68,00)
```

### 11.3 Catálogo de eventos

`INICIO`, `TRAVA`, `AMBIENTE`, `ESPERA`, `HISTORICO`, `MEMORIA`, `RECUPERA`, `PROTEGENDO`, `PRONTO`, `RECUSADO`, `LIGADO`/`DESLIGADO`, `SINAL`, `BLOQUEIO` (sempre com motivo), `DESBLOQUEIO`, `ORDEM`, `REJEITADA`, `TRANSITO` (desconhecida, não executada, executada sem deal, indeterminada, resolvida), `ENTROU`, `STOP`/`ALVO` (criado, movido, recriado), `STOP SEM EXECUCAO`, `SAIDA`, `SAIU`, `DECISAO PERDIDA`, `CANCELA`, `EXECUTOU_ANTES`, `ZERAGEM`, `REDE`, `PREGAO_ANTERIOR`, `DIVERGENCIA`, `TROCADA`, `CORRECAO`, `INVARIANTE`, `EXTERNA`, `ABSORVIDA`, `ORFA`, `ESTRANHA`, `ORIGEM NAO CONFIRMADA`, `AUTONEG`, `AJUSTE`, `RELOGIO`, `MARGEM`, `CAPITAL`, `PUSH`, `FIM`, `HISTORICO_DIA`, `RESUMO`.

### 11.4 O que já foi feito

No `PRONTO` de toda partida e no `RESUMO`: por robô, a lista das operações do dia reconstruída dos deals (hora, lado, entrada, saída, motivo quando conhecido, R$), marcando as que ocorreram com o EA fora (`HISTORICO_DIA`). O `RECUPERA` lista cada evento perdido com a hora real do deal.

### 11.5 Resumo do dia e conciliação

Depois da rede de segurança e no `OnDeinit`: por robô, operações, acertos, R$ bruto e líquido, maior perda; total da conta pelas fichas **e** por `DEAL_PROFIT` + custos (diferença > R$1,00 → ALERTA); **conciliação de contagem** (item 1.21): contratos negociados no símbolo contra `ENTROU`/`SAIU`/`ABSORVIDA` do log (diferença ≠ 0 → ALERTA); contagem de AVISO, ALERTA e ERRO.

### 11.6 Painel no gráfico

`Comment()` com: estado (`PRONTO`/`PROTEGENDO`/…), ficha de cada robô (lado, preço, stop, alvo, resultado aberto, estado derivado), líquida real, externa, status (`OK` / `BLOQUEADO: motivo`), capital de referência, hora da última gravação e do último tick. Botão "Desbloquear" quando aplicável (8.6).

## 12. Horários e fim de pregão

### 12.1 Relógio e grade

- **O maestro é o único dono das saídas por horário e por "outro dia".** O código de zeragem e de "posição de outro dia" de cada módulo (GB L357, CM L720-724, DM L476/L490, RE L1019, C1 L591-594) é desligado por uma flag de configuração do módulo, sem apagar, para o teste do módulo isolado continuar possível.
- Relógio: `TimeTradeServer()` + fuso, no timer, mesmo sem tick (item 2.8). **Fuso calculado**: no real, `fuso = −3 − round((TimeTradeServer() − TimeGMT()) / 3600)` horas, AVISO se ≠ 0 (confirmar com P22); no Testador, 0.
- Referência `F` = **fim do pregão contínuo da data** (`negociacao_fim` da grade; no dia de vencimento do próprio contrato do gráfico, `vencimento_fim`), nunca a sessão da MT5, que pode incluir o call (item 5.35). Data sem linha preenchida na grade: usa 17:55 (o fim mais cedo registrado), AVISO diário.
- `RELOGIO`: `TimeCurrent()` e `TimeTradeServer()` divergindo > 60 s durante o contínuo (feed parado, item 5.17).

### 12.2 Zeragem de cada robô

Executada pelo maestro (protocolo 5.2), pelo timer:

| Robô | Zeragem do avulso | No maestro |
|---|---|---|
| GB | 18:20, limitada a F − 5 min | min(`GB_FlattenHora:Minuto`, F − 5 min) |
| CM | 18:24 ou sessão − 1 min | min(`CM_HoraZerar:Minuto`, F − 1 min) |
| DM | sessão − 5 min | F − `DM_MinutosZerar` |
| RE | 17:00, avaliada a cada vela M15 | `RE_HoraZerar:Minuto` |
| C1 | 17:50 (fim 18:00 − 10 min) | min(`C1_HoraFimPregao:Minuto` − `C1_MinutosZerar`, F − 10 min) |

Diferenças contra o avulso, listadas no relatório 15.1: o avulso fecha no primeiro tick depois do horário e o maestro no instante do timer; o RE deixa de esperar a vela M15; antes de 2024-03-11 o GB usava regra própria de 17:55 e o maestro usa a grade.

### 12.3 Rede de segurança e fim de dia

Em **F − 30 s**: ficha **pelos deals** ainda aberta, ou líquida real ≠ 0 com fichas efetivas 0 (ordem `EXECUTADA_SEM_DEAL` ou `INDETERMINADA`), → zera ficha a ficha pelo protocolo 5.2, com o magic do robô, ALERTA. Recusa (call em curso) → 5.4. No mesmo instante, cancela todas as E e A dos magics dos robôs. Funciona em `PRONTO`, em `PROTEGENDO` e em bloqueio total (8.6).

### 12.4 Pregão anterior, horário perdido e rolagem

- **Ficha de pregão anterior** (deal de abertura antes do pregão de hoje, vista na recuperação ou na virada do dia com o EA rodando): saída pelo protocolo 5.2 em `negociacao_inicio` + 30 s, nunca na pré-abertura; ALERTA. Até lá a S GTC protege. É agendada; a recuperação não espera por ela.
- **Horário perdido**: zeragem de um robô passou com ficha aberta e o contínuo não acabou → zera agora. Contínuo já acabou → a ficha fica com a S GTC, ALERTA, e vira ficha de pregão anterior.
- **Rolagem**: o dono troca o gráfico para o contrato vigente; o estado de pregão é por símbolo e começa limpo; o permanente continua. Ordem ou posição esquecida no contrato velho: 8.8.

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
| Leilão | 5.4, 12.3; P13 |
| Stop recusado por preço atravessado | 4.7 com 5.2 |
| SL/TP na líquida | 8.7 |
| Reconexão e histórico incompleto | 8.1, 8.2, 4.6; P18 |
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
| P13 | Stop disparado em leilão (abertura, call, por variação): vira o quê? Mercado enviado em leilão: qual retcode? Limite agressiva participa do leilão? **(real)** | 5.4, 12.3 |
| P14 | Posição que passa a noite: `POSITION_PRICE_OPEN` muda para o ajuste? Aparecem deals de ajuste ou variação de margem? Tipo e volume? | 3.1, 3.2 |
| P15 | `SYMBOL_FILLING_MODE` e `SYMBOL_EXPIRATION_MODE` do WINV26? Mercado com `RETURN` é aceito? | 4.1 |
| P16 | `GlobalVariableSetOnCondition` funciona como trava entre dois gráficos do mesmo terminal? | 10.1 |
| P17 | Em `REASON_PARAMETERS` e `REASON_CHARTCHANGE` as variáveis globais do EA sobrevivem? | 2.1, 7 |
| P18 | Depois de 2 min sem internet: o histórico volta completo de uma vez? Quanto tempo até `Σ deals = líquida`? Deals chegam com hora antiga? | 3.2, 8.1, 8.2 |
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

Diferenças de saída permitidas, **listadas trade a trade com a causa**: reserva do DM (5.5; mesmo preço, caminho S); zeragem pelo timer em vez do primeiro tick (12.2); prioridade da ordem fixa (4.5, só no teste 2); stop como ordem pendente criada após o deal em vez de SL anexado (GB, RE, C1: contar os trades com stop estourado no tick do fill). Qualquer outra diferença é defeito. No Testador o protocolo 5.2 tem atraso zero (5.1 passo 2).

Relatório: ordens recusadas (> 0 = linha censurada, item 6.55), pior trade em múltiplos do stop (item 6.56), contagem de cada diferença permitida.

### 15.2 Camada de corretora e testes unitários

`Corretora.mqh` define uma interface (`Envia`, `Cancela`, `Modifica`, `Liquida`, `Pendentes`, `Historico`, `Conta`, `Simbolo`) usada por todo o maestro. Duas implementações:
- **`CorretoraReal`**: chama a API do MQL5. É a única que existe no `.ex5` de produção.
- **`CorretoraFalsa`**: segue um roteiro programado de respostas (retcode, atraso do deal, desfecho do cancelamento, estado do histórico, comentário devolvido) e registra cada chamada. Compilada só no EA de teste `WinMaestro_Teste.mq5`, que roda os casos abaixo no Testador e imprime OK/FALHA por caso.

Casos:
1. `DONE` sem deal; deal em 3 s; deal em 8 s; nunca (4.6: `NAO_EXECUTADA` em 30 s, S mantida, nada duplicado).
2. `TIMEOUT` com ticket 0 e ordem que nunca chegou (4.6, cenário do C1 às 17:50).
3. Líquida muda sem deal no histórico (`EXECUTADA_SEM_DEAL`) e cruzada que não fecha (`INDETERMINADA`).
4. Entrada limite viva por 10 h: nenhuma S criada, nenhuma E cancelada como fora de lugar (N2).
5. `OrderDelete` aceito com desfecho FILLED (5.1, 5.2).
6. Histórico chegando aos poucos após reconexão, com deal de hora antiga (8.1, 8.2: nenhuma correção).
7. S e A executando juntas (8.3: uma correção; a segunda em 10 min bloqueia; módulo nunca vê a ficha trocada).
8. Comentário truncado e ticket trocado no `OrderModify` (3.3, 4.4).
9. Externa: posição manual aberta e fechada (fichas intactas, sem bloqueio); zeragem manual com 2 fichas do mesmo lado; com fichas dos dois lados (8.9).
10. Bloqueio por externa, desbloqueio pelo botão, reinício: bloqueio não volta (8.6).
11. Queda entre a gravação do trânsito e o `OrderSend` (4.6).
12. Recusa repetida de S (4.8: cadência, nunca por tick).
13. Saldo absurdo (zero, negativo, salto de 60% sem deal) (13.1).

### 15.3 Falhas (conta demo, pregão real)

| Cenário | Esperado |
|---|---|
| Fechar o MT5 com 2 robôs posicionados e reabrir 5 min depois | E canceladas no `OnDeinit`; S no servidor; `RECUPERA` com o que mudou; `HISTORICO_DIA` |
| Matar `terminal64.exe` (sem `OnDeinit`) com entrada pendente viva | E viva; se encher fora, ganha S no R9; caso B logado |
| Reabrir o terminal sem internet com 3 robôs posicionados | R2 espera; nada é removido; ao conectar, recuperação completa |
| Fechar o MT5 e deixar o stop de um robô executar | Ficha zerada, alvo cancelado no R7, evento com a hora real |
| Stop e alvo executando juntos com o EA fora | Ficha trocada corrigida no R10, ALERTA |
| Apagar `estado.txt`; apagar também o `.bak`; arquivo cortado; arquivo de tamanho zero | `.bak`; caso C com ALERTA e nenhum robô sem stop; `.bak`; `.bak` |
| Memória de outra conta | Ignorada, caso C |
| Apagar o estado permanente | `seq` e saldo do DM reconstruídos |
| Desligar a internet 2 min; e durante o preenchimento de uma entrada limite | Sem ordens enquanto fora; na volta, releitura completa antes de qualquer correção; deal visto, S criada |
| Fechar o MT5 logo após um sinal (reinício durante o `OrderSend`) | Trânsito resolvido, nada duplicado |
| Abrir posição manual e depois fechá-la | Externa volta a 0, fichas intactas, sem bloqueio |
| Zerar a líquida na mão com 2 robôs posicionados | Absorção GB→C1, S/A canceladas, bloqueio; botão libera; reiniciar não rebloqueia |
| SL na líquida pela tela | Bloqueio, ALERTA; SL não removido |
| Maestro em dois gráficos do mesmo símbolo | O segundo recusa iniciar |
| EA avulso com magic do CM em outro gráfico | `ESTRANHA`, bloqueio total; saídas por horário continuam |
| Trocar o timeframe com robôs posicionados | E não canceladas; caso A; nada duplicado |
| Trocar de conta com o EA rodando | E canceladas; memória da outra conta ignorada |
| Desligar um robô com ficha aberta | Só gere até zerar |
| EA fechado às 18:19, aberto 18:23 com ficha aberta | Zera na hora |
| EA fechado das 18:00 às 09:10 com ficha aberta | S GTC protegeu; ficha de pregão anterior zerada às 09:00:30 (ou na partida, se já passou), ALERTA |
| Dia de vencimento do WIN | Cortes pela grade; nada no contrato velho (8.8) |
| Leilão por variação, quando ocorrer | Saídas recusadas seguem 5.4 |
| Forçar a falha da zeragem de um robô | `REDE` zera em F − 30 s |
| Rajada de alertas (intervenção externa com 2 fichas) | Push agregado, no máximo 1 a cada 10 s |

### 15.4 Caminhos de saída obrigatórios

Antes do real, cada caminho precisa de evidência no log de ter disparado ao menos uma vez (item 4.28): zeragem de cada um dos 5 robôs; rede de segurança; ficha de pregão anterior; horário perdido; correção de ficha trocada; saída agressiva (5.4); cancelamento de E no `OnDeinit`; absorção externa; resolução `NAO_EXECUTADA`.

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
- Lote > 1. Se um dia existir, o invariante 1 passa a "Σ volume das S = |ficha|", com uma S por incremento preenchido (`OrderModify` não altera volume em MQL5).
- O alarme do item 1.24 (`POSITION_PRICE_OPEN` fora da grade de preço) não se aplica: com várias fichas, preço médio da líquida fora da grade é normal.

## Apêndice A — por robô

Regras comuns: os 3 bloqueios por posição de outro robô saem; os 14 fechamentos da líquida inteira viram `Ficha_Fecha`; `PositionModify` vira `Ficha_DefineStop`; SL anexado vira S criada no deal; zeragem e "outro dia" do módulo desligados (12.1); gate de vela nova persistido; instantes, nunca contagens. Para todos, `ENTRADA_CANCELADA` e `EXECUTOU_ANTES` = **não rearmar** (comportamento do avulso diante de uma ordem que sumiu).

### A.1 WinGapBarra1 (GB, 80080601, M5)
- Entrada limite 09:05 `SPECIFIED` até 09:35; S de 1.200 pts no deal; alvo e BE desligados no padrão (se ligados: A do robô; BE = `OrderModify` da S, nunca afrouxa).
- Persistir: `g_decidido`, `g_exp`, `g_be_feito`, data do pregão.
- Recálculo: stop = preço da ficha ∓ `StopPts`. A entrada viva é reconhecida pelo papel; não sai segunda entrada.
- `ENTRADA_REENVIAVEL`: reenvia (era a regra do avulso: uma ordem até `g_exp`).
- Checagem de nível: não há (stop fixo).

### A.2 WinCincoMedias (CM, 80080501, H2)
- `a_favor` = marca `F`/`N` do comentário, memória; sem as duas, recalculado das barras da vela de sinal.
- Entrada limite DAY, validade 5 velas H2 contada pela hora de envio; saídas por sinal via `Ficha_Fecha`.
- S de reserva a `CM_ReservaPts` (B.1); `Ficha_Stop` devolve 0 até o "stop que aperta" nascer, que move a mesma S (nunca afrouxa, regra do robô). Checagem de nível: bid na compra, ask na venda, 1 tick (L603-604).
- Persistir: `g_ultima_barra`, `a_favor`, nível do stop que aperta, hora de envio e lado da entrada.
- Recálculo: stop que aperta das barras desde a hora da ficha; avalia a última H2 fechada (comportamento do avulso, com o gate persistido); histórico de volume no R11.
- `ENTRADA_REENVIAVEL`: reenvia se a validade de 5 velas não venceu.

### A.3 WinDeslocamentoMatinal (DM, 80080101, M1)
- Stop do EA por last (bid/ask se last = 0, L446-448) + reserva `DM_ReservaTicks` além (5.5, B.5).
- Persistir: `g_stopNivel`, `g_distStop`, `g_stopAjustado`, `g_decidiu`, `g_dia`, `g_ordemHora`, `g_ordemPreco`. A entrada viva é reconhecida pelo papel, não pelo ticket.
- Recálculo: se a mínima (compra) ou máxima (venda) das M1 desde o heartbeat cruzou `g_stopNivel`, sai agora (`SAIDA ATRASADA`). Sem memória: `g_distStop` pela decisão das 10:30 refeita das barras com o saldo virtual; sem isso, nível da reserva menos `DM_ReservaTicks`.
- `ENTRADA_REENVIAVEL`: reenvia se dentro do TTL de 15 min.

### A.4 WinRetanguloEma34 (RE, 20261005, M15)
- Preenchimento pelo deal com `DEAL_ORDER` = entrada. S = stop do robô; A = limite que se aproxima (`OrderModify`), DAY. Stop nunca afrouxa (regra do robô).
- Persistir: entrada pendente (hora de envio, lado, `g_meio_original`, `g_stop_original`, `g_alvo_original`), posição (`g_preco_entrada`, `g_largura_posicao`, `g_frac_alvo_atual`, hora da vela do fill) e retângulo vivo (`g_tem_retangulo`, `g_topo`, `g_piso`, `g_largura`, `g_meio`, `g_fora_seguidas`).
- Recálculo: `g_barras_esperando` e `g_barras_posicao` a partir dos instantes; o alvo vai ao passo correspondente (`OrderModify`).
- `ENTRADA_REENVIAVEL`: reenvia se dentro do TTL de 10 velas.
- O módulo não cancela a entrada no próprio `Deinit`; vale a regra do `OnDeinit` do maestro (7).

### A.5 Win_c1 (C1, 80080002, H1)
- Entrada a mercado: preço da ficha = deal; S no mesmo fluxo do `OrderSend`.
- **Trailing por vela H1 pode afrouxar**: o stop segue `wma ± KFechamentoATR × ATR` nos dois sentidos, movido quando difere mais de meio tick (L536-550). O maestro move igual.
- Checagem de nível: bid na compra, ask na venda, 1 tick (L538-541).
- Break-even e esticada usam preço e hora da ficha.
- Persistir: `g_ultima_barra`, nível do stop. Recálculo: pico de afastamento e esticada desde a hora da ficha; stop da última H1 fechada.
- Entrada atrasada mais de 60 s: `DECISAO PERDIDA` (não recebe `ENTRADA_REENVIAVEL`).

## Apêndice B — decisões do dono antes de implementar

Cada item traz a recomendação adotada no texto acima; todos **aguardam o dono**.

1. **Stop de reserva do CM.** O robô não tem stop inicial; com o EA fora a ficha fica sem proteção. Opções: (a) sem reserva (fiel ao testado; `CM_ReservaPts = 0`, aceito com AVISO diário); (b) S de reserva distante, que nunca dispararia nos testes 2022–2026 e só protege em queda: `CM_ReservaPts` = maior excursão adversa de um trade do CM no replay 2022–2026 + 20%, arredondada para cima em ticks. **Medido em 2026-10-06: 815 trades, maior excursão 4.120 pts (2,18% do preço, 02/10/2026), p99 2.241, mediana 400 → `CM_ReservaPts` = 4.945.** Nunca teria disparado nos testes. **Recomendação: (b)**, padrão 4.945.
2. **Saldo do DM:** saldo virtual (R$1.000 + resultado dele, 13.3) ou saldo da conta. **Recomendação: saldo virtual** (com 5 robôs, 10% da conta é outro teto, e o saldo da Rico já mentiu, item 1.19).
3. **Entradas e alvos DAY** (Retângulo e alvo do GapBarra1 eram GTC). **Recomendação: DAY.**
4. **WinSeletor e EAs avulsos aposentados.** **Recomendação: aposentar.**
5. **Stop do DM em dois caminhos de níveis diferentes** (5.5): (a) só a S no servidor no nível do stop (muda o mecanismo testado); (b) stop do EA no nível testado + reserva 20 ticks além. **Recomendação: (b)**; custo com o EA fora: até R$20 por contrato além do stop.
6. **Validade dos stops:** (a) GTC (ficha esquecida protegida à noite; S órfã tratada pelo R7 e por 8.5); (b) DAY (posição nua à noite quando o EA falha no fim do dia). **Recomendação: (a) GTC.**
7. **Janela sem stop (Princípio 4, exceções a e b).** Aceitar, com as mitigações adotadas (S do C1 no mesmo fluxo do envio; S na mesma chamada que vê o deal; E canceladas no `OnDeinit`) e o pior caso de 13.4: **R$4.504 a 4 contratos, teto teórico R$5.630** num dia de amplitude p99 (5.630 pts). Cancelar entradas quando o EA perde a conexão não protege: o cancelamento precisa da conexão que falta. **Recomendação: aceitar.**
8. **Absorção de intervenção externa redutora** (8.9): ordem fixa GB, CM, DM, RE, C1 ou proporcional. **Recomendação: ordem fixa** (determinística, reproduzível sem memória).
9. **RE com stop e alvo vivos sem o EA** (5.3): aceitar o risco de execução dupla, ou RE sem alvo no servidor (muda o robô). **Recomendação: aceitar**, com a correção de 8.3.
10. **Depósito da conta** (não é input: o EA lê o saldo, 13.1). Mínimo calculado R$6.630 (13.5: 5 contratos sem stop com o EA fora num dia de amplitude p99, mais a margem do pior estado). **Recomendação: depositar R$7.000.** R$5.000 cobre a margem e o uso normal, mas não o pior caso de queda do EA.
11. **Portão de margem.** No real recusa só o que a corretora recusaria (margem da líquida depois da entrada contra o capital de referência); no Testador só loga. O pior estado alcançável (todas as pendentes executando, item 3.3: "o portão tem de impedir o último passo que ainda cabia") fica só como AVISO. Consequência aceita: uma entrada pode ser aceita mesmo que, depois dela, um stop de outro robô fique sem margem para executar; nesse caso a recusa do stop gera ALERTA e a saída agressiva de 5.4 (item 1.1, incidente de 2026-08-28). Alternativa: recusar também pelo pior estado. **Recomendação: só o que a corretora recusaria**, conforme a preferência registrada do dono.

## Apêndice C — rastreabilidade

### C.1 Revisão adversarial 1

"Parcial na revisão 2" indica as lacunas que a revisão 2 achou incompletas e o item N que as completa.

| Lacuna | Parcial na revisão 2 | Resolvida em |
|---|---|---|
| C1 trânsito / DONE sem deal | sim (N1, N2) | 4.6; 3.1; 6; 15.2 casos 1–4, 11 |
| C2 cancelamento confirmado | — | 5.1, 5.2; 4.7 item 4; 5.5 |
| C3 intervenção externa | sim (N5, N6) | 8.9 (compensação), 8.7, 8.6 (botão, eventos reconhecidos); B.8 |
| C4 janela fill→stop | sim (N20) | Princípio 4a; 4.3; 7; 13.4; B.7 com os números de 13.4 |
| C5 sem OCO | — | Princípio 4b; 5.3; R7, R10; B.9 |
| C6 duas instâncias | sim (N3, N18) | 10.1 (uma trava, pulada no Testador); 4.4 (ordem própria por registro persistente ou prefixo) |
| C7 autonegociação | — | 4.9; 3.4 (`ENTRADA_CANCELADA`) |
| C8 stop que abre para a conta | — | 13.2 (pior estado como diagnóstico); B.11 |
| C9 ficha que atravessa a noite | sim (N4, N3) | 3.2; 4.3 (GTC); 12.4; R4 com prazo; 8.6 (saídas por horário passam no bloqueio total); B.6 |
| C10 divergência transitória | sim (N7) | 8.1 (releituras), 8.2 (cruzada > 60 s bloqueia), 8.3 |
| C11 stop disparado sem execução | — | 5.4 |
| A1 relógio e fim do contínuo | sim (N14) | 12.1 (maestro único dono, fuso calculado), 12.2 |
| A2 `DEAL_ENTRY`/`DEAL_PROFIT` | — | 3.1; 11.5 |
| A3 papel pelo comentário | — | 3.3; 4.7; P3, P4 |
| A4 bloqueio sem cancelar E | — | 8.6 |
| A5 estado velho na volta | — | 9.2 (instantes); 10.4 (recálculo específico); Apêndice A |
| A6 `OnInit` e protegendo | — | 7; 10.2 |
| A7 margem livre como gatilho | sim (N9) | 13.1 (capital de referência pelo saldo protegido), 13.2; B.10, B.11 |
| A8 equivalência | sim (N12, N13, N21) | 15.1; 5.1 passo 2 (mesmo tick); 4.7 (nível do robô, fonte de preço do robô) |
| A9 plano de testes | — | 15.2–15.5 |
| A10 retentativas | sim (N10) | 4.8 (maestro só retenta S/X/C); 3.4 (`Robo_Evento`) |
| A11 DM em dois caminhos | — | 5.5; B.5 |
| M1 memória | — | 9 |
| M2 órfã recém-enviada | — | 8.5 |
| M3 magic da correção | — | 4.4, 8.3 |
| M4 logs | — | 11 |
| M5 rolagem e outros símbolos | — | 8.8, 12.4 |
| M6 custo da reconciliação | sim (N7) | 8.1 (releitura em deal com hora antiga e na reconexão) |
| M7 modos de preenchimento/validade | — | 4.1; R3 (depois da conexão) |
| M8 mover stop | sim (N13) | 4.7 |
| B1 31 caracteres | — | 4.2; P3 |
| B2 alarme do item 1.24 | — | 16 |
| B3 limites da conta | — | R3; P20 |
| B4 parcial com lote > 1 | sim (N17) | lote constante 1 (2.2); 16 |
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
| N1 `DESCONHECIDA` sem saída | 4.6 (S nunca bloqueada; resolução obrigatória em 30 s: `NAO_EXECUTADA`, `EXECUTADA_SEM_DEAL`, `INDETERMINADA`); 8.4 e 12.3 pela ficha pelos deals e pela líquida real |
| N2 E limite na ficha efetiva | 3.1 (E limite contribui 0); 4.3 e 8.4 (S só com deal); 4.6 (pendente listada sai do trânsito) |
| N3 ordem estranha falsa | 4.4 (registro persistente ou prefixo; corte pelo primeiro heartbeat; AVISO com memória perdida); 9.2; 8.6 (saídas por horário passam no bloqueio total) |
| N4 R4 para sempre | 10.2 R4 (60 s, externa de origem desconhecida, `PROTEGENDO`) |
| N5 fechamento de posição manual | 8.9 passo 1; 15.2 caso 9; 15.3 |
| N6 desbloqueio reaplicado / input | 8.6 (botão, eventos reconhecidos no estado permanente); R6 |
| N7 cruzada sem fechar / deal atrasado | 8.1 (releituras), 8.2 (`CRUZADA_MAX`) |
| N8 ambiente antes da conexão | 10.2 (R2 conexão antes de R3 ambiente; leitura zerada repetida 60 s; `RECUSADO` só sem fichas) |
| N9 `CapitalConta` | 13.1 (saldo lido por pregão, protegido), 13.2 (Testador só loga); B.10, B.11 |
| N10 quem retenta E / avisos ao módulo | 3.4 (`Robo_Evento`; maestro nunca reenvia E); 4.8; Apêndice A |
| N11 ficha trocada | 3.1 (detecção na `Ficha_Recalcula`, escondida do módulo); 8.3; 8.4; 3.3 (stop do mesmo lado = órfã) |
| N12 protocolo assíncrono no Testador | 5.1 passo 2, 5.2 passo 2; 15.1 |
| N13 nunca afrouxa × trailing do C1; fonte de preço | 4.7 itens 2 e 3; A.2, A.3, A.5 |
| N14 dois donos da zeragem | 12.1, 12.2; 2.1 (inputs de fuso do GB saem) |
| N15 máquina do ciclo incompleta | 6 (estado derivado) |
| N16 replay antes do `Init` | 10.2 (R11 `Init` antes de R12); 10.4 (recálculo específico) |
| N17 `OrderModify` de volume | 2.2 (`LOTE` = 1); 16 |
| N18 Testador | 7 (timer 1 s, reconciliação por transação e M1); 10.1 e 10.2 (R1, R2 pulados); 9.1 |
| N19 limite de push | 11.2 (fila, dedupe, agregação); P25 |
| N20 números inconsistentes | B.7 com 13.4; 13.5 sem Σ `CapitalRobo`; B.10 |
| N21 critério de equivalência | 15.1 (teste 1 sem exceção; teste 2 exceto `AUTONEG`) |
| N22 camada de corretora | 1; 15.2 |
| N23 cancelar em paralelo × serial | 4.5, 5.2 passo 1 (serial, S primeiro) |
| N24 passo 4 da janela redundante | 3.2 (removido) |
| N25 renovação da S `SPECIFIED` | 4.1 (`SPECIFIED` só se P1/P15 exigirem; nesse caso renovada na virada do pregão pelo timer) |
| N26 volta do `seq` | 4.2 |
| N27 inputs | 2.1 (grupo Maestro no topo só com os liga/desliga), 2.2 (constantes) |

### C.4 Lista mínima de 14 mudanças da revisão 2

| Item | Onde |
|---|---|
| 1 N1 | 4.6 |
| 2 N2 | 3.1, 4.6 |
| 3 N3 | 4.4, 9.2, 8.6 |
| 4 N4 | 10.2 R4 |
| 5 N5 | 8.9 |
| 6 N6 | 8.6, R6 |
| 7 N7 | 8.1, 8.2 |
| 8 N8 | 10.2 R2/R3 |
| 9 N9 | 13.1, 13.2 |
| 10 N10 | 3.4, 4.8, Apêndice A |
| 11 N11 | 3.1, 8.3, 8.4 |
| 12 N12, N13 | 5.1, 5.2, 4.7 |
| 13 N14 | 12.1, 12.2 |
| 14 N16, N17 | 10.2, 10.4, 2.2 |

### C.5 Checklist de `LICOES_DE_PRODUCAO.md`

| Item | Onde |
|---|---|
| 1.1 | 13.2; B.11 |
| 1.2 | Princípio 4; 4.3; 13.4; B.7 |
| 1.4 / 1.23 | Princípio 5; 5.2; 5.5 |
| 1.5 | 5.1 |
| 1.6 | 4.6; 8.1 |
| 1.7 | 8.2 |
| 1.8 | 8.5 |
| 1.9 | 8.6 |
| 1.10 | 4.7 item 2 (ações do maestro) |
| 1.12 / 1.13 | 11.2; 4.8 |
| 1.17 / 1.24 / 1.25 | 4.6; 8.2; 8.6 |
| 1.19 | 13.1 |
| 1.21 | 11.5 |
| 1.22 | 4.8; 4.9 |
| 2.1 / 2.6 | 10.4 |
| 2.4 | 10.1; 4.4 |
| 2.8 / 4.28 | 12.1; 15.4 |
| 3.2 / 3.3 / 3.7 | 13.2; B.11 |
| 4.17 | 10.4 |
| 4.30 | 4.7 item 3 |
| 4.33 | 3.4 |
| 5.33 / 6.54 / 6.55 / 6.56 | 15.1 |
| 5.35 | 12.1 |
