# WinMaestro: revisão adversarial 2 da especificação 0.2

Escopo: `WinMaestro_ESPECIFICACAO.md` (0.2), conferida contra a revisão 1, o inventário dos módulos, o código de partida (`WinSeletor.mq5`, `WinSeletor/*.mqh`), `LICOES_DE_PRODUCAO.md` e as duas preferências registradas do dono sobre EAs (EA pronto no padrão, sem pedir ajuste de input nem saldo; nenhuma trava não pedida).

Severidades: **CRÍTICA** = pode perder dinheiro ou deixar posição real sem stop. **ALTA** = muda o resultado, trava o robô ou esconde um estado perigoso. **MÉDIA** = robustez, auditoria ou implementabilidade. **BAIXA** = detalhe.

---

## 1. Fechamento da revisão 1 (conferido no texto da 0.2)

| Lacuna | Situação | Justificativa |
|---|---|---|
| C1 trânsito / DONE sem deal | **PARCIAL** | 4.6 cria o registro e proíbe reenvio por inferência, mas `DESCONHECIDA` não tem saída e bloqueia stop e saída do robô (N1), e o volume de E limite na ficha efetiva cria stop fantasma (N2). |
| C2 cancelamento confirmado | FECHADA | 5.1 define confirmação pelo histórico; 5.2 não envia saída com desfecho FILLED ou "não sei"; 4.7.3 cancela a S antiga antes de sair. |
| C3 intervenção externa | **PARCIAL** | 8.7/8.9 corretos para o caso descrito, mas o fechamento manual de uma posição manual absorve fichas de robô (N5) e o desbloqueio é reaplicado na recuperação (N6). |
| C4 janela fill→stop | **PARCIAL** | Exceção declarada, mitigações e pior caso em 13.4; porém o Apêndice B.7, onde o dono decide, ainda cita R$1.600/R$2.000, que contradizem os R$4.504/R$5.630 de 13.4 (N20). |
| C5 sem OCO | FECHADA | Princípio 4(b), 5.3, R8 antes de qualquer ação, R11, B.9. |
| C6 duas instâncias | **PARCIAL** | Travas e prefixo existem, mas a regra "origem fora do registro de envios do dia" gera bloqueio total falso todo pregão seguinte a uma ficha que dormiu e a toda perda de memória (N3); a trava em `Common` quebra o Testador com vários agentes (N18). |
| C7 autonegociação | FECHADA | 4.9 nunca barra saída e cancela a limite do outro robô primeiro. (O aviso ao módulo não tem API: N10.) |
| C8 stop que abre para a conta | FECHADA | 13.1 calcula o pior estado com todas as S/A vivas; 13.2 alerta recusa de S/X/C. (A fonte do capital é problema de A7/N9.) |
| C9 ficha que atravessa a noite | **PARCIAL** | Janela desde o último zero, S GTC e pendência R11 resolvem o caso; mas a janela pode nunca fechar e prender a recuperação em R4 (N4), e o bloqueio total falso de N3 impede a saída da ficha de pregão anterior. |
| C10 divergência transitória | **PARCIAL** | 8.2 confirma antes de agir; porém verificação cruzada que nunca fecha deixa as entradas liberadas sem alerta, e o incremental de 60 s perde deals que chegam atrasados (N7). |
| C11 stop disparado sem execução | FECHADA | 5.4 com detecção, limite agressiva, cadência e leilão. |
| A1 relógio e fim do contínuo | **PARCIAL** | Os cortes do maestro usam `TimeTradeServer` e a grade, mas os módulos mantêm relógio e zeragem próprios (GB `GB_ServerGMTOffsetH`/`RegimeAutomatico`, CM `SymbolInfoSessionTrade`, DM `FimSessao`, C1 18:00) e a especificação não diz quem manda (N14). |
| A2 `DEAL_ENTRY`/`DEAL_PROFIT` | FECHADA | 3.1 regras explícitas; 11.5 usa `DEAL_PROFIT` só na conferência. |
| A3 papel pelo comentário / ticket | FECHADA | 3.3 papel por (magic, tipo, lado); invariantes; P3, P4. |
| A4 bloqueio sem cancelar E | FECHADA | 8.6 item 2. |
| A5 estado velho na volta | FECHADA | Instantes em vez de contagens (9.2), regra de entrada atrasada (10.4.3). A implementação do replay tem problema próprio (N16). |
| A6 `OnInit` e modo protegendo | FECHADA | 7 e 10.2. A ordem R2→R3 é problema novo (N8). |
| A7 margem livre como gatilho | **PARCIAL** | Troca o gatilho por `ACCOUNT_MARGIN` + `CapitalConta`, mas o capital é um input estático que só soma o realizado do dia, com padrão (R$5.000) abaixo do mínimo que a própria 13.5 calcula (R$6.630), e conflita com as preferências do dono (N9). |
| A8 equivalência | **PARCIAL** | Pré-condições e critérios escritos, mas o critério se contradiz (N21), o protocolo 5.2 assíncrono muda o preço de saída no Testador (N12) e o trailing do C1 colide com "nunca afrouxa" (N13). |
| A9 plano de testes | FECHADA | 15.2–15.5 cobrem os cenários pedidos, com escada no real. (15.2 exige uma camada que a especificação não manda criar: N22.) |
| A10 retentativas | **PARCIAL** | Cadência e escalada de S/X/C fechadas; para E há contradição sobre quem retenta (N10). |
| A11 DM em dois caminhos | FECHADA | 5.5 com reserva 20 ticks além; B.5. |
| M1 memória | FECHADA | 9.1, 9.4 (tamanho zero), 9.5. |
| M2 órfã recém-enviada | FECHADA | 8.5 (fora do trânsito, > 5 s, cruzada fechando). |
| M3 magic da correção | FECHADA | 4.4 e 8.3: sempre o magic do robô. |
| M4 logs | FECHADA | 11.1–11.5. |
| M5 rolagem e outros símbolos | FECHADA | 8.8, 12.4, R2. |
| M6 custo da reconciliação | **PARCIAL** | 1×/s e incremental definidos, mas a janela `último − 60 s` não enxerga deal que chega depois de reconexão com hora antiga (N7). |
| M7 modos de preenchimento/validade | FECHADA | 4.1 e R2 (com o problema de ordem de N8). |
| M8 mover stop | **PARCIAL** | 4.7 cobre `OrderModify`, piso e não afrouxar; mas "nunca afrouxa" contradiz o trailing do C1 e o piso usa "último negócio", que falta no Testador (N13). |
| B1 31 caracteres | FECHADA | 4.2 e P3. |
| B2 alarme 1.24 | FECHADA | Seção 16. |
| B3 limites da conta | FECHADA | 4.1 e P20. |
| B4 parcial com `Lote` > 1 | **PARCIAL** | 6.3 manda "`OrderModify` de volume", que não existe em MQL5 (N17). |
| B5 prioridade da ordem fixa | FECHADA | 4.5 e 15.1. |

**Totais:** 22 FECHADAS, 13 PARCIAIS, 0 ABERTAS.

---

## 2. Lacunas novas da 0.2, por severidade

### CRÍTICAS

#### N1. `TRANSITO_DESCONHECIDO` não tem saída, bloqueia stop e saída, e uma saída desconhecida zera a ficha efetiva enquanto a posição real continua aberta e sem stop
- **Severidade:** CRÍTICA
- **Seção:** 4.6 regras 2, 3 e 6; 5.2 passo 1; 6.1; 8.4; 12.3.
- **Cenário:** às 17:50 o C1 zera. O 5.2 cancela a S (confirmado) e envia a venda a mercado. O `OrderSend` volta `TIMEOUT` com ticket 0; a ordem nunca chegou ao servidor. A busca pelo comentário não acha nada, nem agora nem nunca, porque não há o que achar. Pela regra 6 a ordem vira `DESCONHECIDA` e a consulta continua "até o desfecho aparecer", ou seja, para sempre. Enquanto isso: (a) ficha efetiva = deals (+1) + trânsito (−1) = **0**, então a 8.4 não recria a S e a rede de segurança das 18:24:30 não vê nada para zerar; (b) a regra 6 proíbe "novas ordens de qualquer papel exceto cancelamentos", inclusive S e X. A posição real de 1 contrato atravessa a noite **sem stop**, com o EA convencido de que está zerado. A regra "sem nada em 10 s → `NAO_ENVIADA`" existe só no R6 da recuperação, não no pregão corrente.
- **Correção (texto):** "Uma ordem `DESCONHECIDA` é resolvida como **não executada** (`NAO_EXECUTADA`, ALERTA) quando, por 30 s seguidos: nenhuma ordem com o ticket, o `request_id` (via `TRADE_TRANSACTION_REQUEST`) ou o comentário dela existe nas pendentes nem no histórico; a verificação cruzada da janela fecha; e a líquida real não mudou desde o envio. Antes dessa resolução, `DESCONHECIDA` bloqueia só novas ordens **do mesmo papel ou que alterem a ficha** (E, X, C); **S nunca é bloqueada**. A necessidade de S é decidida pela ficha **pelos deals** (não a efetiva): ficha pelos deals ≠ 0 com X/C desconhecida há mais de 5 s → a S é recriada (se a X executar depois, a S vira órfã e cai na 8.5). A rede de segurança de 12.3 também olha a ficha pelos deals e a líquida real."

#### N2. O volume de uma entrada limite na ficha efetiva cria stop fantasma e faz o maestro cancelar a própria entrada
- **Severidade:** CRÍTICA
- **Seção:** 3.1 (`volume_transito`), 4.6 (tabela: "E … o volume da ordem"; estados `ENVIADA`/`VIVA`; regra 4), 3.3 (papéis e invariante 4), 8.4.
- **Cenário:** o CM envia uma BUY_LIMIT. Pela tabela de 4.6 o volume de E entra no trânsito, e a ficha efetiva vira +1. A regra 4 diz que a ordem "listada como pendente (`VIVA`)" sai do trânsito, mas a própria tabela tem `VIVA` como estado do registro; a especificação não decide. Nas duas leituras há falha: (a) se `VIVA` continua no trânsito, a ficha efetiva fica +1 por até 10 h; a 8.4 vê "ficha ≠ 0 há mais de 2 s sem S" e coloca uma SELL_STOP para uma posição que não existe, e se o preço cair ela **abre um vendido nu**; a 3.3 vê "limite do mesmo lado da ficha ≠ 0" (E fora de lugar) e cancela a entrada; (b) se `VIVA` sai do trânsito, ainda existe a fase `ENVIADA`, que pode durar até 5 s (`PrazoConfirmacaoS`), mais do que os 2 s da 8.4: a mesma S fantasma nasce sempre que a corretora demorar a confirmar o `PLACED`.
- **Correção (texto):** "Só ordens que executam no envio alteram a ficha efetiva: E a mercado (C1), X e C. Entrada limite contribui **0** para a ficha efetiva em qualquer estado; ela conta no pior estado da margem (13.1) e no invariante 4 (no máximo uma E com ficha 0). A 8.4 só age sobre ficha pelos deals ≠ 0. `VIVA` não é estado do registro de trânsito: ordem listada como pendente sai do trânsito e passa a ser reconhecida pelo papel (3.3)."

### ALTAS

#### N3. A detecção de "ordem estranha" pelo registro de envios do dia gera bloqueio total falso, e o bloqueio total prende a saída da ficha de pregão anterior
- **Severidade:** ALTA
- **Seção:** 10.1 item 3, 4.2 (último marcador), 4.4, 9.2, 9.5, 10.3 pendência 1.
- **Cenário 1:** o CM dorme comprado com a S GTC. Na manhã seguinte a 9.5 descarta o estado de outro pregão (fica só o trânsito não resolvido e os bloqueios); o registro de envios do dia está vazio. A S de ontem e o deal de abertura de ontem têm "origem fora do registro de envios desta instância" → **bloqueio total**. O bloqueio total só deixa passar S, cancelamentos e rede de segurança; a saída da ficha de pregão anterior (09:00:30) não está na lista. A ficha de ontem fica aberta o dia inteiro, protegida só pela reserva de 4.945 pts, até 18:24:30, e o dono tem de agir.
- **Cenário 2:** a memória se perde (caso C). Todas as ordens e deals do maestro na janela estão fora do registro → bloqueio total na partida.
- **Cenário 3:** a 4.2 diz que, enquanto P3 não for respondida, vale o prefixo `MAE|<inst>|`; a 10.1.3 aplica ao mesmo tempo o prefixo **e** o registro. As duas regras se contradizem. Se a Rico reescrever o comentário (P3), o primeiro preenchimento do dia já dispara o bloqueio total.
- **Correção (texto):** "Ordem própria = ticket presente no **registro persistente de ordens próprias** (mantido enquanto a ordem ou a ficha que ela abriu existir, atravessando pregões, e copiado para o `.bak`) **ou** comentário com prefixo `MAE|<inst>|`. Estranha = as duas condições falham **e** a ordem foi criada (`ORDER_TIME_SETUP_MSC`) depois do primeiro heartbeat desta instância. Com a memória perdida, ordens anteriores à partida sem prefixo são AVISO, não bloqueio. No bloqueio total continuam passando, além de S e cancelamentos, todas as saídas por **horário** do maestro (zeragem de cada robô, pregão anterior, horário perdido, rede), cada uma enviada só se a líquida real ainda tiver o lado e o volume da ficha (item 1.25)."

#### N4. A recuperação fica em `R4_AGUARDA_HISTORICO` para sempre, sem proteger nem zerar
- **Severidade:** ALTA
- **Seção:** 3.2 passo 5; 10.2 (R4: "nenhuma ordem"); 8.9 (aumentador: "robôs seguem").
- **Cenário:** o dono abre 1 contrato manual e o mantém por três semanas; a 8.9 permite ("exposição externa, as fichas continuam operando"). Numa reinicialização, a líquida não passou por zero nos últimos 10 pregões, a janela não fecha e o EA fica em R4 indefinidamente: sem 8.4, sem 5.4, sem zeragem, sem rede de segurança. O mesmo vale se o terminal tiver menos de 10 pregões de histórico carregado, ou se P14 revelar ajuste de posição sem deal BUY/SELL. A 8.9 e a 3.2 se contradizem.
- **Correção (texto):** "R4 tem prazo de 60 s. Esgotado: a janela passa a ser a mais longa disponível (até 10 pregões); a diferença entre a líquida real e o Σ dos deals da janela é registrada como **exposição externa de origem desconhecida**; ALERTA com push; a recuperação segue para `PROTEGENDO` (proteção e cortes de horário ativos, entradas bloqueadas até a verificação cruzada fechar ou o dono liberar)."

#### N5. O fechamento manual de uma posição manual é classificado como "redutor" e zera fichas de robô
- **Severidade:** ALTA
- **Seção:** 8.9.
- **Cenário:** o GB está comprado 1. O dono compra 1 manual (aumentador, externa +1, líquida +2) e mais tarde vende 1 manual para sair da posição dele. O deal reduz |líquida|, logo é "redutor": a 8.9 absorve a redução na ficha do GB (ordem fixa), cancela a S do GB e bloqueia tudo até o dono. A externa continua +1. Resultado: o GB perde a ficha, a S dele some, e a posição real de +1 (que é do GB) fica sem stop e contabilizada como "externa".
- **Correção (texto):** "Deal externo é primeiro compensado contra a exposição externa existente de sinal oposto; só o excedente que reduz |líquida| abaixo de Σ fichas é redutor e vai à absorção. Acrescentar a 15.3: 'abrir posição manual e depois fechá-la → externa volta a 0, fichas intactas, sem bloqueio'."

#### N6. O desbloqueio pelo dono é reaplicado pela própria recuperação, e o mecanismo de desbloqueio é um input
- **Severidade:** ALTA
- **Seção:** 2 (`ContadorDesbloqueio`), 8.6, 9.2, 10.2 R7 ("reativa os bloqueios que exigem o dono").
- **Cenário:** um deal externo redutor bloqueia o EA. O dono incrementa `ContadorDesbloqueio`; mudar input reinicia o EA (seção 2), que passa pela recuperação completa. No R7 a recuperação reclassifica o mesmo deal externo da janela e **reativa o bloqueio**. A especificação não amarra o desbloqueio ao evento que o causou; o dono fica preso num laço. Além disso, cada desbloqueio exige editar input, o que contraria a preferência do dono (não pedir ajuste de input). Se a Rico fizer zeragem compulsória diária (P11), o bloqueio que exige o dono vira rotina.
- **Correção (texto):** "Cada bloqueio que exige o dono é identificado pelo evento que o causou (ticket do deal ou da ordem). O desbloqueio grava esses tickets como **reconhecidos** no estado permanente; R7 só reativa bloqueio de evento não reconhecido. O desbloqueio é feito por um **botão no gráfico** (`OBJ_BUTTON` + `OnChartEvent`, com confirmação por duplo clique), sem reiniciar o EA; `ContadorDesbloqueio` sai dos inputs."

#### N7. Verificação cruzada que não fecha mantém as entradas liberadas sem alerta, e o incremental perde deals que chegam atrasados
- **Severidade:** ALTA
- **Seção:** 8.1 (incremental `último − 60 s`, janela completa só a cada 10 min), 8.2 item 3 ("espera, não corrige; loga uma vez").
- **Cenário:** a internet cai 2 min às 11:00 e um stop do RE executa nesse intervalo. Na reconexão, o deal chega com `DEAL_TIME` de 11:00:40, fora da janela incremental (`último − 60 s`). A ficha do RE continua +1, a líquida real já é 0, a verificação cruzada não fecha, e a 8.2 só "espera" e loga uma vez. Divergência não confirmada não bloqueia nada: os robôs continuam enviando entradas com a ficha do RE errada por até 10 min, até a releitura completa.
- **Correção (texto):** "Releitura completa da janela imediatamente em: transição de `TERMINAL_CONNECTED` falso→verdadeiro, falha da verificação cruzada e `OnTradeTransaction` de deal com hora anterior ao último instante processado. Verificação cruzada sem fechar por mais de 60 s → bloqueio de entradas (do tipo que sai sozinho, com E pendentes canceladas pela 8.6) e ALERTA, repetido a cada 5 min."

#### N8. O ambiente é checado antes da conexão, e `RECUSADO` remove o EA mesmo com fichas vivas
- **Severidade:** ALTA
- **Seção:** 10.2 (R2 antes de R3), 4.1 ("recusa iniciar se faltar DAY…"), convenções (tick zerado → recusa).
- **Cenário:** o terminal reinicia às 10:00 com 3 robôs posicionados. R2 lê `SYMBOL_EXPIRATION_MODE`, `SYMBOL_FILLING_MODE` e `SYMBOL_TRADE_TICK_VALUE` antes de o símbolo sincronizar (R3); os valores vêm 0, e R2 manda `RECUSADO` → `ExpertRemove()`. O EA sai do gráfico com 3 fichas abertas, sem zeragem nem rede de segurança, e a S DAY/GTC é a única coisa protegendo.
- **Correção (texto):** "R2 roda depois de R3. Leituras zeradas são repetidas por 60 s antes de concluir falha. `RECUSADO` com `ExpertRemove` só quando não há ficha nem ordem viva de magic de robô; com elas, o EA fica em `PROTEGENDO` com ALERTA, sem entradas."

#### N9. O portão de margem com `CapitalConta` conflita com as preferências do dono e não descreve a conta real
- **Severidade:** ALTA
- **Seção:** 2 (`CapitalConta` = 5.000), 13.1, 13.5, Apêndice B.10; preferências `feedback_ea_padrao_pronto` e `feedback_ea_sem_travas_nao_pedidas`.
- **Fatos:** (1) o dono pediu explicitamente que o EA leia o saldo da conta (no Testador, o Depósito) e que não precise informar saldo por input; `CapitalConta` é exatamente isso. (2) Ele reclamou duas vezes de portão de capital não pedido, um deles bloqueou o teste inteiro. (3) O capital efetivo soma só o realizado **do dia**: depois de um mês de perdas o portão continua achando que há R$5.000. (4) O padrão (R$5.000) fica abaixo do mínimo que a 13.5 calcula (R$6.630) e da recomendação de B.10 (R$7.000), então o dono teria de editar o input para seguir a própria especificação. (5) No Testador, com Depósito de R$1.000 (o capital dos comparativos), o portão libera o que a corretora recusaria; com Depósito alto e perdas, pode recusar o que ela aceitaria. Nos dois casos fere o item 3.7 ("o portão recusa o que a corretora recusaria").
- **Cenário:** teste de equivalência do DM sozinho com Depósito R$1.000: o portão usa R$5.000 e nunca age, enquanto o avulso foi testado com R$1.000; em conta real com R$3.000 após perdas, o portão aceita entradas que a Rico recusa por margem e o robô passa a receber `RECUSADA` em vez de `BLOQUEADA`.
- **Correção (texto):** "Sem input de capital. **Capital de referência** = `ACCOUNT_BALANCE` lido uma vez no `PRONTO` de cada pregão (no Testador, o Depósito mais o resultado acumulado), com proteção contra o item 1.19: leitura ≤ 0 ou variação > 50% contra a leitura anterior sem deal que a explique → mantém a leitura anterior e loga AVISO. O portão de 13.1 compara a margem do pior estado com esse capital e só recusa o que a corretora também recusaria. No Testador o portão só **loga** (`MARGEM`), não recusa, para o teste reproduzir o avulso. O AVISO de capital abaixo do mínimo (13.5) continua, só como log." Com isso, B.10 deixa de ser decisão sobre input e vira só recomendação de depósito.

#### N10. Quem retenta uma entrada bloqueada ou recusada não está definido, e os avisos ao módulo não têm API
- **Severidade:** ALTA
- **Seção:** 3.4 ("o módulo trata `RECUSADA` e `BLOQUEADA` como falha de `OrderSend`"), 4.8 ("entradas só voltam na próxima vela"), 4.9.1 ("reavaliados com a espera de 4.8"), 4.9.2 (`CANCELADA_AUTONEG`, "o outro robô rearma"), 5.1 (`EXECUTOU_ANTES`), 8.6 ("cada robô rearma"), 10.4 itens 3 e 5.
- **Cenário:** o GB envia a entrada às 09:05; a 4.9.1 a bloqueia por autonegociação. O módulo GB recebe `BLOQUEADA`, trata como falha e marca `g_decidido = true` (não tenta de novo). A 4.9.1 diz que o maestro "reavalia com a espera de 4.8"; se o maestro reenviar por conta própria, sai uma ordem que o módulo acha que não existe. No CM, `OrdemPendente` acha a ordem pelo magic e o módulo segue; no DM (`OrdemPendenteViva` por ticket guardado) a ordem fica órfã do ponto de vista do robô, e o TTL de 15 min não a cancela. "Rearma pela regra dele" também não existe: nenhum dos 5 módulos tem regra de rearme depois de cancelamento externo.
- **Correção (texto):** "O maestro **nunca** retenta E por conta própria; quem decide reenviar é o módulo, na regra dele. S, X, C e cancelamentos são retentados só pelo maestro. A interface de cada módulo ganha um único callback, `Robo_Evento(robo, evento, dados)`, com eventos `ENTRADA_CANCELADA` (autonegociação, bloqueio, `OnDeinit`), `EXECUTOU_ANTES` e `ENTRADA_REENVIAVEL` (10.4); o Apêndice A diz, para cada robô, o que ele faz com cada evento (para GB, CM, DM e RE o padrão é **não rearmar**, que é o comportamento do avulso)."

#### N11. A ficha com sinal trocado tem detecção ambígua, o módulo a vê como posição legítima, e a 8.4 corrige mesmo com `CorrigirDivergencia = false`
- **Severidade:** ALTA
- **Seção:** 3.1 (estados válidos incluem −Lote), 3.3 (tabela de papéis), 8.2, 8.3, 8.4.
- **Cenário:** o RE está comprado; o alvo executa e a saída por regra (X) também. A ficha vai a −1, que é "estado válido" pela 3.1, e Σ fichas continua igual à líquida, então a 8.2 não acusa divergência. Quem dispara a 8.3 não está escrito. Enquanto isso o módulo vê `Ficha_Lado = venda` e gere um vendido que nunca abriu (alvo que se aproxima no sentido errado). A S de compra do RE não existe; a 8.4 vê ficha ≠ 0 sem S, recria a S no nível da memória (uma SELL_STOP abaixo do preço é do lado errado para um vendido), conclui "nível atravessado" e sai a mercado pela 4.7.3. Ou seja, a correção acontece por outro caminho mesmo com `CorrigirDivergencia = false`. A S antiga de venda (se viva) fica "do mesmo lado da ficha", papel que a tabela da 3.3 não lista.
- **Correção (texto):** "Ficha **trocada** = ficha pelos deals com sinal oposto ao do deal de abertura do ciclo atual do robô. Ela é detectada na própria `Ficha_Recalcula`, sem esperar a 8.2, e só exige a verificação cruzada fechando. Ficha trocada nunca é mostrada ao módulo (`Ficha_Tem` = falso, módulo suspenso até a ficha voltar a 0) e não passa pela 8.4. Com `CorrigirDivergencia = true`, 8.3; com `false`, bloqueio e ALERTA, e a 8.4 não age sobre ela. Acrescentar à 3.3: 'stop do mesmo lado da ficha ≠ 0' = órfã."

#### N12. O protocolo 5.2 assíncrono muda o preço de saída no Testador
- **Severidade:** ALTA (equivalência)
- **Seção:** 5.1 passo 2 (consulta a cada 250 ms), 5.2 ("sai entre 0,2 s e 5 s depois"), 5.5, 15.1.
- **Cenário:** no Testador o `OrderDelete` é síncrono e o histórico já mostra `CANCELED` no retorno. Se o código seguir a 5.1 ao pé da letra (consultar na próxima volta do timer), toda saída por regra, todo stop do EA do DM e toda zeragem saem num tick posterior ao do avulso. O critério "preço de saída por stop ≤ 1 tick" falha em massa, ou o critério é afrouxado e deixa de detectar defeito.
- **Correção (texto):** "Logo após o `OrderDelete`, o maestro consulta o histórico **na mesma chamada**; se o desfecho já está lá (sempre no Testador, frequentemente no real), segue para a saída no mesmo tick. A consulta pelo timer só existe quando o desfecho não veio no retorno. No Testador o atraso esperado de 5.2 é zero, e qualquer saída em tick diferente do avulso é defeito."

#### N13. "O stop nunca afrouxa" contradiz o trailing do C1, e o piso de 4.7 usa uma fonte de preço diferente da dos módulos
- **Severidade:** ALTA (equivalência)
- **Seção:** 4.7 itens 2 e 4, A.5, 5.5.
- **Fatos do código:** `Win_c1.mqh` recalcula o stop a cada H1 como `wma ± KFechamentoATR × ATR` e o move sempre que difere mais de meio tick, **nos dois sentidos** (L536-550): o stop do C1 pode afrouxar. A checagem "preço já passou" do C1 usa **bid/ask** e 1 tick; a do DM usa **last**, com bid/ask quando `last` = 0 (L446-448, por causa do cache do Testador sem `last`, item 5.33). A 4.7 manda conferir contra "o último negócio" e proíbe afrouxar "salvo regra explícita do robô", e o A.5 não declara o afrouxamento do C1.
- **Cenário:** o ATR H1 sobe e o novo stop do C1 fica mais longe. O maestro recusa (não afrouxa) e o C1 passa a sair mais cedo que o testado. Em ticks sem `last` no Testador, a checagem de 4.7.2 não tem preço.
- **Correção (texto):** "A.5: o trailing do C1 é **regra explícita que pode afrouxar**. 4.7.2: a checagem usa a mesma fonte de preço do módulo que pediu (C1: bid na compra, ask na venda; DM: last, com bid/ask se last = 0); para os demais, last com o mesmo fallback. A 4.7.4 vale para GB (BE), CM (stop que aperta) e RE."

### MÉDIAS

#### N14. A zeragem tem dois donos e dois relógios
- **Severidade:** MÉDIA
- **Seção:** 12.1, 12.2, 10.3 pendência 1; A.1–A.5; inputs dos módulos.
- **Cenário:** o GB continua com `GB_ServerGMTOffsetH` e `RegimeAutomatico` (17:55 antes de 2024-03-11 por regra própria), o CM com `SymbolInfoSessionTrade`, o DM com `FimSessao`, o C1 com 18:00 fixo, e o maestro com `FusoServidorH` e a grade. Se o código dos módulos ficar, cada robô tem duas zeragens; se `GB_ServerGMTOffsetH` ≠ `FusoServidorH`, as duas discordam. As regras "de outro dia" do CM (L722), do DM (L476) e do C1 (L591) mandam fechar no **primeiro tick** do dia, que pode cair no leilão de pré-abertura, competindo com a pendência R11 (09:00:30).
- **Correção (texto):** "O maestro é o **único** dono das saídas por horário e por 'outro dia'. O código de zeragem e de 'outro dia' de cada módulo é desligado por uma flag de configuração (não apagado, para o teste do módulo isolado continuar possível). `FusoServidorH` é o único fuso: no real é calculado (`TimeTradeServer` − (`TimeGMT` − 3 h), arredondado à hora, AVISO se ≠ 0); no Testador é 0. `GB_ServerGMTOffsetH` passa a ser ignorado."

#### N15. A máquina de estados do ciclo (6.1/6.2) está incompleta
- **Severidade:** MÉDIA
- **Seção:** 6.1, 6.2.
- **Faltam transições:** `POSICIONADO_SEM_STOP` → `SAINDO` (zeragem ou stop do EA do DM antes de a S ser aceita); `ENTRADA_PENDENTE` → cancelamento por bloqueio, autonegociação ou rede; `SAIDA_PENDENTE` → `POSICIONADO` (cancelamento confirmado e saída não enviada); saída agressiva de 5.4 (X-limite) sem estado; ficha absorvida por intervenção externa; ficha trocada (N11); `TRANSITO_DESCONHECIDO` sem saída (N1).
- **Correção (texto):** "O estado do ciclo **não é armazenado**: é derivado a cada reconciliação de (ficha pelos deals, ordens vivas por papel, trânsito). A tabela 6.1 vira a função de derivação, e a memória guarda só os níveis e instantes. Isso elimina transições faltantes e estados guardados que divergem da corretora."

#### N16. O replay (R12) roda antes do `Init` dos robôs (R13) e exige reescrever os cinco módulos
- **Severidade:** MÉDIA
- **Seção:** 10.2 (R12 antes de R13), 10.4, Apêndice A.
- **Fato:** os handles de indicador (`iMA`, ATR) e a pré-carga do RE nascem no `Init`; o replay precisa deles. E reprocessar "velas fechadas desde o heartbeat, sem enviar ordem" exige que cada `Tick()` aceite um índice de vela em vez de `shift 1` relativo ao agora, o que é refatoração profunda dos cinco módulos testados, com risco direto de equivalência.
- **Correção (texto):** "R13 (`Init`) antes de R12. O replay genérico é substituído por recomputação específica, que é o que o avulso já fazia ao reiniciar: RE recalcula as contagens a partir dos instantes; DM verifica se a mínima/máxima M1 desde o heartbeat cruzou `g_stopNivel` (`SAIDA ATRASADA`); CM e C1 avaliam a última vela fechada (comportamento do avulso, com o gate de vela persistido); GB e DM aplicam a regra de entrada atrasada de 10.4.3. Sem modo replay nos módulos."

#### N17. "`OrderModify` de volume" não existe em MQL5
- **Severidade:** MÉDIA
- **Seção:** 6.3.
- **Fato:** `TRADE_ACTION_MODIFY` altera preço, SL/TP e validade de ordem pendente, não o volume. A alternativa da 6.3 (cancelar e recriar) abre a janela sem stop que a 4.7.1 proíbe; uma segunda S viola o invariante 1 da 3.3.
- **Correção (texto):** "O lote de cada robô é 1 no maestro (constante, como em todos os testes). A 6.3 sai da especificação. Se um dia houver lote > 1, o invariante 1 passa a 'Σ volume das S = |ficha|', com uma S por incremento preenchido."

#### N18. O Testador não está tratado: trava em `Common`, passos de conexão e custo do timer
- **Severidade:** MÉDIA
- **Seção:** 10.1 item 2 (arquivo de trava em `Common`), 10.2 R1/R3, 7 (timer 250 ms), 8.1.
- **Cenário:** numa otimização, vários agentes na mesma máquina abrem `Common/WinMaestro/lock_<conta>_<símbolo>.lck`; o segundo falha e recusa iniciar. R3 espera `TERMINAL_CONNECTED`, cujo valor no Testador a especificação não define. Um teste de 4 anos com timer de 250 ms e reconciliação a cada segundo gera dezenas de milhões de eventos e de `HistorySelect`.
- **Correção (texto):** "No Testador: R1 e R3 são pulados; a reconciliação roda em `OnTradeTransaction` e a cada M1 nova, não por timer; o timer é de 1 s e serve só aos cortes de horário. A 9.1 já isola a memória; a trava segue a mesma regra."

#### N19. `SendNotification` tem limite de frequência e alertas vão se perder em rajada
- **Severidade:** MÉDIA
- **Seção:** 11.2, 4.8, 5.4, 8.9.
- **Fato:** a MT5 limita push a poucas mensagens por minuto (a verificar o número exato na documentação vigente); acima disso a chamada falha. Uma intervenção externa com duas fichas gera ALERTA de bloqueio, de absorção, de cancelamento e de `STOP SEM EXECUCAO` no mesmo segundo.
- **Correção (texto):** "Push passa por uma fila com no máximo 1 envio a cada 10 s; alertas da mesma janela são agregados numa mensagem ('3 alertas: …'). Falha de `SendNotification` é logada como ERRO."

#### N20. Os números do pior caso e do capital não batem entre as seções
- **Severidade:** MÉDIA
- **Seção:** 13.4, 13.5, Apêndice B.7, B.10, seção 2.
- **Fatos:** B.7 pede ao dono que aceite "R$1.600 a 4 contratos; teto R$2.000", números da referência antiga de 2.000 pts; a 13.4 usa 5.630 pts (R$4.504 e R$5.630). A 13.5 soma "Σ `CapitalRobo` dos robôs ligados = 5 × R$1.000", mas só o DM tem `CapitalRobo`. O padrão de `CapitalConta` (R$5.000) é menor que o mínimo de 13.5 e que a recomendação de B.10.
- **Correção (texto):** "B.7 com os números de 13.4. 13.5 sem o termo Σ `CapitalRobo`. B.10 reescrito conforme N9 (recomendação de depósito, não input)."

#### N21. O critério de equivalência se contradiz, e a autonegociação não existe no Testador
- **Severidade:** MÉDIA
- **Seção:** 15.1, 4.9.
- **Fatos:** "Entradas: 100% iguais" convive com "causas permitidas: autonegociação", que remove entradas. O Testador não casa ordens do mesmo EA entre si, então os bloqueios e cancelamentos da 4.9 no Testador são diferença pura contra o replay T6, que também não os tem.
- **Correção (texto):** "Teste 1 (um robô): entradas 100% iguais, sem exceção. Teste 2 (os cinco): entradas iguais exceto as listadas com evento `AUTONEG`, contadas e mostradas no relatório; meta: contagem ≤ 1% das entradas."

#### N22. Os testes com corretora falsa (15.2) exigem uma camada que a especificação não manda criar
- **Severidade:** MÉDIA
- **Seção:** 15.2, 3.4, 1.
- **Fato:** MQL5 não substitui `OrderSend`/`HistorySelect` por script. Sem uma interface de corretora no desenho, os 8 casos de 15.2 não são testáveis.
- **Correção (texto):** "Todo acesso a `OrderSend`, `OrderDelete`, `OrderModify`, `PositionSelect`, `OrdersTotal`, `HistorySelect*` passa por uma classe `Corretora` (arquivo `Corretora.mqh`) com duas implementações: real e falsa (roteiro de respostas programado). Os módulos de robô nunca chamam a API diretamente (já é a regra 3.4)."

### BAIXAS

- **N23.** 5.2.1 manda cancelar S e A "em paralelo"; 4.5 diz que os envios são seriais. Escolher serial (S primeiro).
- **N24.** 3.2 passo 4 é consequência do passo 3 (`líquida(agora) = líquida(T) + S`); pode sair.
- **N25.** A S com validade `SPECIFIED` é renovada só no R10; com o EA rodando dias seguidos ela expira e só é recriada pela 8.4 depois de 2 s. Renovar também na virada do pregão pelo timer.
- **N26.** `seq` de 5 dígitos sem regra de volta. Definir: ao passar de 99999 volta a 1, e a busca pelo comentário usa também a data.
- **N27.** Inputs: pela preferência do dono, o grupo Maestro vai no **fim** da lista (não desloca presets); `IdInstancia`, `TetoEntradasMin`, `DisjuntorEnviosMin`, `PrazoConfirmacaoS`, `StopEmergenciaPts` e `NotificarPush` podem ser constantes (ver seção 4).

---

## 3. Implementabilidade: decisões que hoje ficariam com o programador

1. Se E limite conta na ficha efetiva, e se `VIVA` é estado do trânsito (N2).
2. Quando uma `DESCONHECIDA` deixa de bloquear e o que ela bloqueia (N1).
3. Quem retenta uma E bloqueada e como o módulo fica sabendo de cancelamentos feitos pelo maestro (N10).
4. Quem executa a zeragem e o "outro dia": o módulo, o maestro ou os dois; qual fuso vale (N14).
5. Que gatilho dispara a 8.3 e o que o módulo enxerga com a ficha trocada (N11).
6. Como o replay chama o módulo para velas passadas (N16).
7. Que preço usar nas checagens de 4.7 e 5.5 quando `last` = 0 (N13).
8. O que é "falha" no R6 e quais passos são reentrantes quando o `PROTEGENDO` "tenta de novo o passo que falhou".
9. Se a pendência de pregão anterior (R11) espera dentro da recuperação até 09:00:30 ou é agendada e a recuperação segue.
10. Onde vive o registro de ordens próprias entre pregões e por quanto tempo (N3).
11. Volume de S em preenchimento parcial (N17).
12. Comportamento no Testador de R1, R3, timer e push (N18).
13. Como a confirmação de cancelamento convive com o envio no mesmo tick (N12).
14. Se o bloqueio total (10.1.3) deixa passar as saídas por horário (N3).

---

## 4. Simplificação sem perder segurança

| O quê | Como | Por que não perde segurança |
|---|---|---|
| Estado do ciclo armazenado (6.1/6.2) | Derivar de ficha + ordens + trânsito a cada reconciliação | O estado derivado nunca diverge da corretora; elimina as transições faltantes de N15 |
| Replay genérico de velas (10.4, R12) | Recomputação específica por robô (N16) | É o que os avulsos já faziam no reinício; o risco de afastar os módulos do testado cai |
| Preenchimento parcial (6.3) | Lote constante 1 | Todos os testes usam 1 contrato; tira uma API inexistente |
| Fallback stop-limit (4.3) e fallback `SPECIFIED` para S (4.1) | Implementar só se P1/P15 mostrarem que são necessários | Código que nunca roda não é testado; o EA recusa iniciar se faltar o que precisa (R2) |
| Duas travas locais (variável global + arquivo) | Só a variável global, mais a detecção pela corretora | A trava por arquivo só acrescenta P16 e quebra o Testador; a detecção da 10.1.3 cobre o resto |
| `IdInstancia` | Constante `i1` | Duas instâncias do maestro já são proibidas pela trava; entre máquinas, o registro de ordens próprias detecta |
| `CapitalConta` e portão por input | Saldo lido da conta, portão diagnóstico no Testador (N9) | O portão continua recusando no real o que a corretora recusaria |
| `TetoEntradasMin`, `DisjuntorEnviosMin`, `PrazoConfirmacaoS`, `StopEmergenciaPts`, `NotificarPush`, `ContadorDesbloqueio` | Constantes; desbloqueio por botão | Mesmos valores; o dono não mexe em nada (preferência registrada) |
| 3.2 passo 4 | Remover | É implicado pelo passo 3 |

Mantido de propósito: 4.6 (com N1/N2), 5.1/5.2, 8.2, 8.9, S GTC, R8 antes de tudo, 4.9.2 e os testes de 15.3; cada um corresponde a um item de `LICOES_DE_PRODUCAO.md` que já custou dinheiro.

---

## 5. Equivalência com os EAs avulsos testados: o que ainda muda o resultado

| Diferença | Robô | Efeito | Tratamento proposto |
|---|---|---|---|
| Saída depois de cancelamento confirmado (5.2) | todos | Tick posterior se a confirmação for assíncrona | N12: confirmação síncrona; zero no Testador |
| "Nunca afrouxa" aplicado ao trailing | C1 | Stop mais curto que o testado | N13 |
| Fonte de preço das checagens (last × bid/ask) | C1, DM | Saída em tick diferente quando `last` = 0 | N13 |
| Zeragem pela grade e pelo timer em vez do tick | GB, CM, DM, RE, C1 | Avulso fecha no 1º tick após o horário; o maestro, no preço do instante do timer; RE deixa de esperar a vela M15; GB antes de 2024-03-11 usava a regra própria de 17:55 | Relatório 15.1 lista trade a trade; N14 define um só relógio |
| Saldo virtual do DM (R$1.000 + resultado) × `ACCOUNT_BALANCE` | DM | Teto de 10% diferente se o Depósito ≠ R$1.000 | No teste 1, Depósito = `DM_CapitalRobo` (R$1.000, o capital dos comparativos) |
| Reserva do DM no Testador | DM | Mesmo preço, caminho S (5.5) | Já listado |
| Stop como ordem pendente em vez de SL da posição; S criada após o fill | GB, RE, C1 | Stop que estoura no tick do fill pode diferir | Já listado (contagem "stop estourado na vela do fill") |
| Autonegociação (4.9) | todos, teste 2 | Entradas a menos | N21 |
| Portão de margem | todos | Pode recusar entradas que o avulso fez | N9: só log no Testador |
| Ordem fixa de envio (4.5) | todos, teste 2 | Prioridade de fila ao GB | Já listado |
| Modo de preenchimento único (RETURN; IOC a mercado) | CM, RE, C1 (avulsos usavam o padrão do `CTrade`) | Nenhum com 1 contrato | Nenhum |
| Validade DAY em vez de GTC (RE entrada) | RE | Nenhum (TTL ≤ 150 min e zeragem 17:00) | Nenhum |

---

## 6. Conciliação com as preferências do dono sobre EAs

| Item da 0.2 | Conflito | Proposta que mantém a segurança |
|---|---|---|
| `CapitalConta` (input obrigatório na prática, padrão abaixo do mínimo calculado) | "O EA deve saber o saldo pelo Depósito; não pedir para informar saldo" | Ler `ACCOUNT_BALANCE` no `PRONTO` de cada pregão, com a proteção de N9 contra leitura absurda |
| Portão de margem que recusa entradas | "Nunca adicionar portão de capital/margem sem ele pedir"; o portão do WinF2 bloqueou o teste inteiro | No Testador só loga; no real recusa apenas o que a corretora também recusaria (item 3.7). Apresentar ao dono como decisão explícita do Apêndice B, com o incidente de 2026-08-28 (item 1.1) como motivo |
| `ContadorDesbloqueio` como input (e cada desbloqueio reinicia o EA) | "Não pedir ajuste de input" | Botão no gráfico (N6) |
| `FusoServidorH` "a verificar" | O dono teria de descobrir e digitar | Cálculo automático no real; 0 no Testador (N14) |
| Recusa de iniciar com `CM_ReservaPts = 0` | Trava não pedida sobre uma decisão (B.1) que é do dono | Se B.1 = (a), 0 é legítimo: aceitar com AVISO diário; o padrão continua 4.945 |
| `TetoEntradasMin`, `DisjuntorEnviosMin` | Travas não pedidas, mas nunca atuam com 5 robôs de poucas ordens por dia e nunca barram saída | Manter como constantes (itens 1.20 e 1.22), fora dos inputs |
| Recusas de ambiente (HEDGING, `WIN$N` no real, falta de DAY/GTC) | Nenhum: são condições sem as quais a corretora recusaria tudo | Manter, com N8 (só depois da conexão e nunca com fichas vivas) |
| Grupo de inputs do maestro no topo | "Novo input vai no fim da lista" | Grupo Maestro no fim |

---

## 7. Fechamento

**Lacunas novas por severidade:**

| Severidade | Quantidade | Itens |
|---|---|---|
| CRÍTICA | 2 | N1, N2 |
| ALTA | 11 | N3–N13 |
| MÉDIA | 9 | N14–N22 |
| BAIXA | 5 | N23–N27 |
| **Total** | **27** | |

Revisão 1: 22 fechadas, 13 parciais, 0 abertas.

**Veredito: não pronta.** A arquitetura está certa e quase toda a revisão 1 foi absorvida, mas o núcleo novo (registro de trânsito e ficha efetiva) tem duas falhas que deixam posição real sem stop, e há quatro formas de o EA ficar preso (desconhecida sem saída, R4 sem prazo, bloqueio total falso, desbloqueio reaplicado). As correções são localizadas: nenhuma exige mudar o desenho.

**Lista mínima para ficar pronta (com ressalvas restantes = perguntas P à Rico):**
1. N1: `DESCONHECIDA` com resolução por oráculo em 30 s; S nunca bloqueada; necessidade de S e rede de segurança pela ficha pelos deals.
2. N2: só E a mercado, X e C alteram a ficha efetiva; `VIVA` sai do trânsito.
3. N3: registro persistente de ordens próprias entre pregões; estranha só quando ticket e prefixo falham; saídas por horário passam no bloqueio total.
4. N4: prazo de 60 s no R4, depois `PROTEGENDO` com a diferença como externa.
5. N5: deal externo compensa a externa antes de absorver fichas.
6. N6: bloqueio amarrado ao evento, desbloqueio por botão, R7 respeita o reconhecido.
7. N7: releitura completa na reconexão e na falha da cruzada; cruzada > 60 s sem fechar bloqueia entradas.
8. N8: R2 depois de R3; nunca `ExpertRemove` com fichas vivas.
9. N9: sem `CapitalConta`; saldo da conta; portão só loga no Testador.
10. N10: maestro nunca retenta E; callback `Robo_Evento` com o comportamento de cada robô no Apêndice A.
11. N11: ficha trocada escondida do módulo e fora da 8.4.
12. N12 e N13: confirmação síncrona no mesmo tick; trailing do C1 declarado como regra que afrouxa; fonte de preço igual à do módulo.
13. N14: maestro como único dono das saídas por horário, um só fuso.
14. N16 e N17: `Init` antes do replay e replay substituído por recomputação específica; lote constante 1.
