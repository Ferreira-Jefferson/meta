# WinMaestro v1.03 — revisão adversarial do código (3)

Escopo: `mt5/WinMaestro.mq5`, `mt5/WinMaestro/*.mqh`, `mt5/WinMaestro_Teste.mq5`, `WinMaestro/CorretoraFalsa.mqh`, contra `WinMaestro_ESPECIFICACAO.md`, as escolhas 1–34 de `WinMaestro_implementacao_notas.md`, os achados de `WinMaestro_revisao_codigo_2.md`, os módulos originais em `mt5/WinSeletor/*.mqh` e `LICOES_DE_PRODUCAO.md`. Abreviações: `F` = `WinMaestro/Fichas.mqh`, `R` = `WinMaestro/Recupera.mqh`, `C` = `WinMaestro/Corretora.mqh`, `EA` = `WinMaestro.mq5`, `T` = `WinMaestro_Teste.mq5`, `CF` = `CorretoraFalsa.mqh`; módulos por sigla (GB, CM, DM, RE, C1). Linhas são as dos arquivos atuais.

**Placar: 0 CRÍTICAS, 2 ALTAS, 6 MÉDIAS, 11 BAIXAS.** Dos 24 itens da revisão 2 (4 ALTAS, 8 MÉDIAS, 9 BAIXAS, 3 parciais da revisão 1): 24 fechados no cenário que descreviam; 4 deles deixam resíduo, listado como achado novo. **Dois dos 87 testes falham contra o código (T34 e T39, seção 6).**

---

## 1. Achados da revisão 2, conferidos no código

| # | Situação | Onde | Observação |
|---|---|---|---|
| A-1 corte ignorava trânsito, fichas velhas | FECHADO | `F:2416-2497` (espera todo o trânsito `F:2426`, cruzada aberta há 10 s `F:2425`, limites antes `F:2433-2451`, C pela líquida real `F:2453-2478`, S depois `F:2480-2496`); C registrado no mapa e nunca E (`F:827`) | O cenário do lag está resolvido. A espera de trânsito criou um impasse novo (A-1 abaixo) |
| A-2 saída `BLOQUEADA` perdida | FECHADO | `F:1807-1816` (pedido guardado), `F:2173-2180` (enviado quando fecha), `F:2584-2585`, `F:2677-2678` (memória) | Resíduos: pedido sem prazo (M-2), contrato do `Ficha_Fecha` mudou e quebrou T34/T39 (M-6), adiamento com "alvo executou antes" (B-10) |
| A-3 X depois do zero virava E | FECHADO | `F:827` (mapa vence), `F:829` (comentário), `F:757` (X/C sobre ficha 0 → `mzPorE` falso → trocada) | Dentro de uma execução. Depois de reinício com P3 negativo, volta a ser E (B-3) |
| A-4 memória que não grava barrava proteção | FECHADO | `F:1256`, `F:1459-1464`, `F:1699` | — |
| M-1 `EXECUTOU_ANTES` para qualquer K | FECHADO | `F:2021-2022` | `Ficha_Cancela(P_A)` ainda emite o evento em `D_ANTES` (`F:1898-1901`), hoje inalcançável (B-5) |
| M-2 externa desconhecida fora do passo 4 | FECHADO | `R:337-345` | — |
| M-3 nada saía depois de F | FECHADO | `F:400-408`; `F:1431`, `F:1521`, `F:1548`, `F:2122`, `F:2226` | — |
| M-4 indeterminada sem proteção | FECHADO | `F:2224` (Fase 2 não olha `mzIndet`), `F:977-979` (30 s → trocada) | A indeterminação ficou "grudenta" no dia (M-1 abaixo) |
| M-5 magic 0 virava externo na hora | FECHADO | `F:797-804`, `F:1933` | `mzMagic0Pend` é calculado e nunca lido: o corte não espera a carência (B-1) |
| M-6 `D_NAO` com E viva e comentário perdido | FECHADO | `F:1370-1378`, `F:559-566` | — |
| M-7 fallback DAY do GB | FECHADO | `F:1744-1750` (mesma S); `GB:` chamada com `ORDER_TIME_SPECIFIED` | Dispara em qualquer recusa, não só de validade; inofensivo (GB cancela em `g_exp`) |
| M-8 variável da trava apagada | FECHADO | `R:74-82` | A trava perdida para outro gráfico é permanente (M-5 abaixo) |
| B-1 eventos antes do `Init` | FECHADO | `F:264-278`, `R:436-438` | — |
| B-2 PROTEGENDO recriava alvo | FECHADO | `F:2303` | — |
| B-3 S complementar de \|f\| | FECHADO | `F:2274` | `Ficha_DefineStop` ainda manda `need − volS` numa ordem (`F:1838`); só alcança \|f\| = 1 |
| B-4 relog com memória perdida | FECHADO | `R:157-162` | Absorções vistas não são persistidas (B-9) |
| B-5 S contra limite própria | FECHADO (documentado) | `F:1249-1250` | — |
| B-6 código do `PositionSelect` | FECHADO | `C:100-110` | — |
| B-7 releitura por tick | FECHADO | `F:280-285`, `F:1443`, `F:1705` | — |
| B-8 prazos compartilhados | FECHADO | `F:191-197`, `F:1915` | Recusa contada para bloqueio e `D_SEM` (B-6) |
| B-9 cancelar e rearmar na mesma vela | FECHADO | `F:1199-1204`, `F:1255`, `F:1709` | — |
| Parcial A-1 (rev. 1) | FECHADO | via M-5 | — |
| Parcial M-5 (rev. 1) | FECHADO | via B-2 | — |
| Parcial B-3 (rev. 1) | FECHADO | via B-4 | — |
| T22 falhava | FECHADO | passa (seção 6) | — |

---

## 2. Achados novos, por severidade

### ALTA

#### A-1. O corte com a cruzada aberta entra em impasse: espera um trânsito que só se resolve com a cruzada fechada
- **Onde:** `F:2426-2430` (qualquer item no trânsito suspende o corte); `F:1398` (`D_NAO` de ordem nova exige `mzCruzOk`); `F:1392-1396` (ordem com histórico `FILLED` e deal ausente nunca é resolvida); `F:2228` (Fase 2 sem S depois do corte com a cruzada aberta).
- **Cenário 1 (histórico incompleto, o caso para o qual o D2 existe).** 18:19:55, X do GB executa; o deal dela não chega ao histórico (P6/P18 no pior caso). A ordem está no histórico `FILLED`, mas `Mae_Prova` só aceita deal como prova de execução e só conclui `D_NAO` com a cruzada fechando. A cruzada não fecha porque falta exatamente esse deal. A X fica `D_SEM` para sempre; `Mae_CorteConta` retorna em `F:2426` a cada segundo; a Fase 1 do CM e do DM é barrada pela cruzada; a Fase 2 não recria S depois do corte. Em F: ALERTA, S DAY vencem, CM e DM atravessam a noite com o EA no ar.
- **Cenário 2 (reinício, cenário h).** O EA grava a memória com a X no trânsito (`F:1458`, ticket 0) e o MT5 cai antes de a ordem chegar à bolsa. Na volta, a X sem ticket e sem comentário a casar nunca prova `D_NAO` se a cruzada estiver aberta por outro motivo.
- O bloqueio de 10 min (`F:2038-2042`) chama o dono, e o botão tira do trânsito só o que tem mais de 10 min (`F:1144-1149`): uma ordem de 18:19 sai do trânsito às 18:29, depois de F.
- **Correção:** no `Mae_CorteConta`, dar o trânsito por assentado quando (i) a ordem está no histórico em estado final (`FILLED`, `CANCELED`, `REJECTED`, `EXPIRED`), ou (ii) o ticket é 0 e a idade passa de `IDADE_PROVA` com conexão confiável, sem exigir a cruzada; e dar ao corte um prazo absoluto (ex.: corte + 2 min) depois do qual ele age pela posição real lida na hora. O volume do C já sai da líquida real, então uma ordem que executou antes é absorvida na conta.

#### A-2. Ficha trocada ou duplicada com correção travada, ou em modo PROTEGENDO, nunca é zerada: nem no corte, nem na manhã seguinte
- **Onde:** `F:2185-2205` — todo caminho do bloco trocada/duplicada termina em `return`; `F:2199` (`mzCorrTravada || mzProtegendo` → `return`); o caminho do corte e da ficha da noite (`F:2206-2216`) nunca é alcançado.
- **Cenário:** RE com A + S na mesma vela (corrida 1.23) às 14:00, corrigida; às 14:07, outra trocada (ex.: S + X do mesmo robô). `mzCorrTravada[RE]` liga, bloqueio com botão. A ficha −1 recebe S de emergência (`F:2274`). 18:20: a Fase 1 entra no bloco de trocada e retorna; `Mae_CorteConta` só age com a cruzada aberta. A posição real atravessa a noite; a S DAY vence. Na pré-abertura nasce outra S de emergência; no contínuo a Fase 1 retorna de novo. A posição fica aberta todo dia até o dono apertar o botão. Mesmo efeito em PROTEGENDO, que pela escolha 23 e pela 10.2 deveria mandar "a saída do corte", e com duplicada (\|f\| = 2) inteira aberta.
- **Origem:** a especificação 9.3 manda trocada e duplicada para a seção 8 no corte, e a seção 8 trava a segunda correção. O código segue a especificação; o buraco é dos dois. T41, T55 e T75 fixam o comportamento sem olhar o corte.
- **Correção:** no corte, na zeragem do robô e na ficha da noite, trocada e duplicada saem por uma X de \|f\| (zeragem, não correção), sem olhar `mzCorrTravada` nem `mzProtegendo`; a trava continua valendo só para correções intradiárias.

### MÉDIA

#### M-1. A indeterminação da ficha fica para o resto do dia: toda operação seguinte do robô é cega para o módulo e é fechada como trocada aos 30 s
- **Onde:** `F:831` (`mzIndet[r] = true` para qualquer deal do robô sem ordem identificada na janela); `F:878` (só limpa se a ficha **final** for 0).
- **Cenário:** 10:00, deal do GB cuja ordem não aparece (P2/P3, `DealSemOrdem`); corrigido às 10:00:30, ficha 0. 11:00, GB não opera, mas o CM tem um deal assim às 10:00 e entra de novo às 13:00 (E legítima, no mapa). Ao recalcular, o deal de 10:00 ainda tem `ord_ok` falso: `mzIndet[CM]` volta a verdadeiro com a ficha +1. `Ficha_Tem` falso: o CM não vê a posição (sem stop que aperta, sem saída por regra). 30 s depois, `Mae_IndetVelha` → trocada → correção fecha a posição legítima. A segunda em menos de 10 min trava as correções, e a ficha cai em A-2.
- **Correção:** zerar `mzIndet[r]` dentro do laço de `Ficha_Calcula` toda vez que `mzF[r]` passa por 0; a indeterminação vale só para o episódio da ficha atual.

#### M-2. A saída adiada não tem prazo: executa uma decisão velha horas depois
- **Onde:** `F:1807-1816`, `F:2173-2180`; memória `F:2584`, `F:2677`.
- **Cenário:** 11:01, C1 manda sair por break-even (≤ 7 pts a favor). A cruzada está aberta por uma diferença real; bloqueio aos 60 s. O dono aperta o botão às 14:30; a cruzada fecha e o maestro manda a saída do C1 de 11:01, com o preço 400 pts a favor. O módulo, que recebeu `ENVIADA`, não reavaliou nada desde então (`Ficha_Fecha` devolve "já pedida", `F:1807`). Igual depois de reinício no mesmo dia (`F:2677`). É divergência do avulso, que perdia a ordem e reavaliava na M1 ou na vela seguinte.
- **Correção:** guardar o instante do pedido e descartá-lo (volta ao módulo) se não sair em N segundos (ex.: 60 s) ou se mudar a vela de decisão do robô.

#### M-3. Com a cruzada aberta o OCO não acontece: a S órfã de uma ficha zerada fica viva e pode abrir posição nova
- **Onde:** `F:1253-1254` (cruzada barra todo papel, inclusive K); `F:2141-2142`.
- **Cenário:** a cruzada está aberta por uma diferença real (bloqueio esperando o botão). O alvo do RE enche; o deal aparece, a ficha vai a 0. A S de venda vira órfã com prova de OCO (`F:2130`), mas o cancelamento volta `BLOQUEADA` a cada segundo. O preço cai até a S: abre venda de 1 sem E, ficha −1 trocada, S de emergência a 1.200 pts, correção barrada pela cruzada. Posição real indesejada pelo resto do bloqueio.
- **Correção:** liberar K de órfã quando a irmã é mais velha que um deal visível que zerou a ficha do robô (a mesma prova do OCO imediato); cancelar nunca aumenta a exposição.

#### M-4. A S que acabou de disparar é recriada se o deal dela atrasa mais de 2 s
- **Onde:** `F:2253-2257` (a exceção da escolha 19 cobre só X e C em trânsito).
- **Cenário:** a S do DM dispara a 119.000; a posição muda, o deal atrasa 3 s. A ficha segue +1 pelos deals, a S sumiu das pendentes, nada em trânsito. Aos 2 s, `Mae_NivelAtravessado` só barra se o bid está a 1 tick do nível; o preço voltou 15 pts. Nova S de venda a 119.000 numa conta já zerada: se o preço voltar ao nível antes de o deal chegar e o OCO cancelá-la (mais 5 s, `F:2131`), abre venda de 1.
- **Correção:** tratar "S do robô que saiu das pendentes sem `CANCELED` no histórico, com a cruzada aberta" como a X em trânsito: nenhuma S nova até a cruzada fechar.

#### M-5. A trava perdida é permanente, e a instância que a perdeu continua com os módulos rodando
- **Onde:** `R:475-479` (`mzTravaPerdida` nunca volta a falso); `F:2120` (Fase 1 inteira desligada); `EA:213-214` e `F:2537-2540` (`Tick()` não olha a trava).
- **Cenário:** o terminal trava 12 s; outro gráfico com o EA toma a trava (`R:44-55`). O primeiro volta só com S. O ALERTA diz "remova uma das duas"; o dono remove a que tem a trava. A que sobra nunca mais cancela órfã, zera, corrige nem corta; às 18:20 nada sai e as posições atravessam a noite. Enquanto as duas rodam, as duas movem as S pelos próprios módulos.
- **Correção:** em `Trava_Confere`, com a variável em 0 (livre) retomar com `GlobalVariableSetOnCondition` e limpar `mzTravaPerdida`; com a trava perdida, não chamar `Tick()` dos módulos.

#### M-6. `Ficha_Fecha` passou a devolver `ENVIADA` quando ninguém vai enviar; T34 e T39 falham
- **Onde:** `F:1809` (adia qualquer `BLOQUEADA` com `Ficha_Tem` e contínuo, inclusive trava perdida, leitura não confiável e conta não NETTING); `F:2120` (com trava perdida a Fase 1 nunca chega ao pedido).
- **Cenário:** T39 (`T:647-659`) põe `mzTravaPerdida` e espera `rf != FICHA_ENVIADA`; o código devolve `ENVIADA`. T34 (`T:546-563`) quebra a leitura do histórico e espera `BLOQUEADA` com nenhum envio; o código devolve `ENVIADA` e guarda o pedido. Os dois falham (seção 6). No real, o módulo acredita numa saída que esta instância nunca manda.
- **Correção:** adiar só os motivos transitórios que a reconciliação desta instância resolve (cruzada, trânsito do robô, leitura não confiável); trava perdida, conta não NETTING e "alvo executou antes" devolvem `BLOQUEADA`. Atualizar T34 e T39 ao contrato que ficar.

### BAIXA

| # | Onde | Achado | Correção |
|---|---|---|---|
| B-1 | `F:2425` × `F:798`; `F:170` nunca lido | O corte age aos 10 s de cruzada aberta e a carência do magic 0 também dura 10 s, medidas em bases diferentes (segundo × ms). Na fronteira, uma zeragem manual com a ordem ainda fora do histórico faz `Mae_CorteConta` zerar a líquida real, posição do dono incluída | `Mae_CorteConta` espera `!mzMagic0Pend` |
| B-2 | `F:2457-2460` | O robô do C é o primeiro com S do lado da líquida, e pode ser a S de entrada de um robô com ficha 0 (a E foi cancelada no passo 1). A ficha desse robô fica invertida; se a cruzada fecha depois, a correção dele e as zeragens dos outros fazem negócios de ida e volta. Com a cruzada aberta o C zera também a posição externa do dono (D2) | Escolher o robô pela ficha do mesmo lado e com S de saída; registrar no log a externa conhecida que o C fecha |
| B-3 | `F:543-556`, `F:827-831` | O mapa ticket → papel não é persistido. Depois de reinício, com o comentário perdido (P3), a X colocada depois do zero volta a ser E pela ficha na colocação (`F:830`): o RE ou o C1 passam a gerir uma operação fantasma se a correção ainda não tinha executado | Persistir o mapa do dia na memória |
| B-4 | `F:1333-1356` | K cujo alvo some das pendentes sem deal e sem histórico legível fica `D_SEM` para sempre (não há a regra dos 30 s do K): o robô fica pausado, sem saída nem corte, até o botão | Aplicar a mesma regra de idade com leitura confiável |
| B-5 | `F:1898-1901` | `Ficha_Cancela(P_A)` com `D_ANTES` manda `EXECUTOU_ANTES`; o RE o lê como "a minha E encheu" (`RE:1102-1109`). Hoje só é chamado sem ficha (`Ficha_TemAlvo` falso), mas é a mesma armadilha da M-1 da revisão 2 | Emitir só para `papel == P_E` |
| B-6 | `F:2168`, `F:2281`, `F:2317` | `Mae_Recusa` conta `BLOQUEADA` e `D_SEM` como recusa: "5 recusas seguidas" falso com a cruzada aberta; o cancelamento da E por bloqueio ou zeragem é refeito a cada segundo sem `RETENTA` | Contar só `FICHA_RECUSADA`; respeitar `mzRecProx[r][RC_K]` nos motivos bloqueio e zeragem |
| B-7 | `F:1392-1401` | Ordem nova com histórico `FILLED` e deal ausente vira `D_NAO` aos 30 s se a posição também ainda não mudou: a saída é reenviada e pode inverter | `FILLED`/`PARTIAL` no histórico → `D_SEM` (executada, deal a caminho) |
| B-8 | `F:2174` | O pedido adiado sai em PROTEGENDO (a escolha 23 permite só S, cancelamentos e corte). Reduz exposição, mas foge do contrato | Exigir `!mzProtegendo` ou documentar |
| B-9 | `F:1971-1995`, `F:2545-2588` | `mzAbsVistas` não vai à memória: depois de reinício, absorção ainda não reconhecida é relogada (`ABSORVIDA` duplicada) e o resumo dá ALERTA de contagem falso | Persistir as absorções vistas do dia |
| B-10 | `F:1643` → `F:1809` | "alvo executou antes" (prova `FILLED` no histórico) é adiado como estado transitório: se no ciclo seguinte a posição e o deal ainda não mudaram, o pedido manda a X sobre uma ficha que o alvo já zerou | Não adiar esse motivo |
| B-11 | `F:2141-2142` | Órfã cujo cancelamento é recusado (`d != D_CANC`) faz a Fase 1 retornar antes da E, do pedido, da correção e do corte do robô, e o cancelamento é refeito a cada segundo, sem `RETENTA` | Seguir para as etapas seguintes depois de uma órfã que falhou e retentar a órfã a cada 5 s |

---

## 3. Mecanismos da v1.03, um a um

| Mecanismo | Veredito |
|---|---|
| Corte esperando trânsito e decidindo pela posição real | Correto quando o trânsito se resolve; impasse quando não se resolve (A-1); escolha do robô do C (B-2); corrida com a carência (B-1) |
| Saída guardada no maestro e persistida | Fecha o A-2 da revisão 2; sem prazo (M-2); devolve `ENVIADA` sem dono (M-6); adia "alvo executou antes" (B-10). Não gera ordem duplicada: o pedido some quando a ficha zera ou muda (`F:2173`), e o envio respeita o trânsito |
| Papel registrado no envio | Correto dentro da execução; perdido no reinício (B-3) |
| Falha de memória que só bloqueia entrada | Correta |
| S e cancelamentos até F + 15 | Corretos |
| Indeterminada vira trocada aos 30 s | Correta para o episódio; a marca contamina o resto do dia (M-1) |
| Carência de 10 s para magic 0 | Correta; não conversa com o corte (B-1) |
| Casamento por tipo/preço/volume/tempo | Correto; `Mae_OmLivre` impede casar ordem de outro papel |
| Fallback DAY do GB | Correto (mesma S). Vale para qualquer recusa, não só de validade |
| Trava retomada | Retoma a variável apagada; nunca retoma a trava liberada pelo outro gráfico (M-5) |
| Eventos enfileirados antes do `Init` | Corretos |
| S de volume 1 por contrato | Correta; a cobertura de \|f\| = 3 leva ~6 s (2 s por S, `mzSemSDesde` zerado a cada criação, `F:2277`) |
| Temporizadores por papel | Corretos; contagem de recusa inclui bloqueio (B-6) |
| Releitura no máximo a cada 10 s | Correta (T78) |
| `Inputs.mqh` | Padrões idênticos aos do WinSeletor; `Configura()` dos cinco módulos liga cada input ao campo certo; magics fora dos inputs |

**Interações procuradas especificamente.** Saída adiada + corte + trânsito: não há envio duplo — a saída adiada, a zeragem e a correção do mesmo robô passam pela mesma Fase 1 com um `return` por ciclo, e todas exigem a cruzada fechada, enquanto `Mae_CorteConta` exige a cruzada aberta; o C do corte muda a ficha do robô escolhido e o pedido dele some pela troca de `mzFid` (`F:2173`). Estados que nunca terminam: A-1 (trânsito com a cruzada aberta), M-5 (trava), B-4 (K), A-2 (trocada travada). Proteção que falta: A-2 e A-1 (posição sem saída no corte), M-3 e M-4 (S que pode abrir posição), Fase 2 congelada depois do corte com a cruzada aberta (`F:2228`).

---

## 4. Cenários simulados contra o código

**(a) MT5 morto com CM e RE comprados; a S do RE executa; o alvo do RE enche com o EA fora; o EA volta.** Deals do RE: +1 (E), −1 (S, tipo stop → S), −1 (alvo; sem o mapa, comentário `|A|` → X, `F:829`; sem comentário, ficha +1 na colocação → X, `F:830`). A X sobre ficha 0 abre −1 com `mzPorE` falso: trocada. Passo 4 fecha; passo 7 sem órfãs do RE; passo 8 S do CM no nível da memória e S de compra de emergência para o RE a `pm + 1.200`; passo 9 correção C de compra 1 (no contínuo; senão agendada). Executada, a S de emergência é cancelada. **Única e segura.**

**(b) Saída do C1 com `TIMEOUT`, internet fora 90 s.** X no trânsito com ticket 0; a S fica. Desconectado nada se prova. Se o C1 pedir a saída de novo nesse intervalo (break-even a cada M1), o pedido é guardado (trânsito do robô, `F:1809`). Na volta, releitura e 10 s. Executou: deal achado por comentário ou por tipo/volume, `D_EXEC`, OCO, pedido limpo pela ficha zero. Não chegou: aos 30 s, cruzada fechando, `D_NAO`; o pedido guardado sai na hora (melhor que a revisão 2, onde a saída ficava com a regra do robô). Se executou junto com a S, a ficha invertida é trocada pelo mapa (`F:827`). **Única e segura.**

**(c) O dono zera na mão com GB e DM posicionados.** A ordem manual está no histórico com magic 0: verificada, sem carência. Absorve GB e DM, bloqueio, OCO imediato das S (irmãs mais velhas que o deal), E do CM cancelada pelo bloqueio. Se a ordem manual atrasa no histórico, 10 s de carência com a cruzada aberta: as S de GB e DM continuam vivas sobre conta zerada nesse intervalo, e nada sai até a absorção. Às 18:20, a mesma carência pode disparar `Mae_CorteConta` (B-1). **Única e segura fora da fronteira do corte.**

**(d) Ficha da noite com gap contra.** Janela recua; S DAY nova a partir das 08:55 (`F:2226`, janela do call); nível atravessado → ALERTA e nenhuma S; contínuo → X; `MARKET_CLOSED` retentado com AVISO (T84). Se a ficha da noite for trocada com a correção travada, ela nunca é zerada (A-2). **Única; segura dentro do risco aceito, exceto A-2.**

**(e) Cinco robôs entrando no mesmo segundo às 10:00, dois opostos.** Serial na ordem fixa; S antes de cada E; `AUTONEG` para E contra limite própria; S passa com AVISO. Se a E a mercado do C1 enche e o deal atrasa, as entradas seguintes do mesmo segundo voltam `BLOQUEADA` (T85) e **não são adiadas**: o CM perde a entrada da vela H2, o C1 a da H1. Divergência de equivalência que só a escada mostra. **Segura; não equivalente ao avulso no real.**

**(f) Corte às 18:20 com a cruzada aberta.** Fase 1 barrada; Fase 2 congelada; `Mae_CorteConta` espera 10 s e trânsito vazio, cancela as limites, manda C de −líquida, depois cancela as S. **Segura se o trânsito se resolve; impasse até F se não se resolve (A-1).**

**(g) E do DM enchendo com o cancelamento por TTL em voo.** `D_ANTES` síncrono → `EXECUTOU_ANTES` (o DM ignora; `AjustarStop` reancora a S no tick seguinte). `D_SEM` → resolvido depois em `Transito_Resolve` com `era_e` verdadeiro. A S está viva desde antes da E. `mzECancelPedido` fica ligado até a E seguinte, sem efeito. **Única e segura.**

**(h) MT5 reinicia às 18:19 com uma saída guardada e a cruzada aberta.** Passo 2 espera 10 s de conexão (18:19:10); o passo 4 relê a cada 250 ms até 60 s; com a cruzada aberta, às 18:20:10 grava bloqueio e segue. Até o passo 10 não há reconciliação: nenhuma S recriada, nenhum corte entre 18:19 e ~18:20:12. Passo 5 restaura o pedido (mesmo dia). Passo 8: Fase 2 retorna (cruzada aberta depois do corte). Passo 9: o pedido esbarra na cruzada. PRONTO às ~18:20:12; `Mae_CorteConta` já tem 60 s de cruzada aberta. Dois desfechos:
- trânsito vazio ou resolvível: limites canceladas, C de −líquida, S canceladas. Real zerada antes de F. O pedido do robô do C some com a troca de `mzFid`; os pedidos dos outros ficam esbarrando na cruzada e morrem com o contínuo. Depois da meia-noite a janela de hoje fecha com líquida 0 e as fichas fantasmas somem. **Segura.**
- trânsito com a ordem que o pedido mandou antes da queda (memória gravada antes do `OrderSend`, `F:1458`), ticket 0 e nunca casada, ou executada sem deal: **impasse de A-1**; as posições atravessam a noite com o EA no ar.

**(i) Cinco robôs posicionados; o dono desliga dois pelo input.** `REASON_PARAMETERS`: `OnDeinit` grava a memória com os módulos (`EA:191-196`), não libera a trava; `OnInit` reseta tudo e refaz a partida. Janela de ~12 s (10 s do passo 2) sem reconciliação: OCO e recriação de S suspensos, S do servidor protegendo. Os dois desligados continuam com `Tick()` (`F:2537` não olha `mzAtivo`) e gerem as fichas até zerar, como pede a seção 1; só `Mae_PodeEntrar` os barra (`F:1684`). E viva de robô desligado continua e pode encher. Decisões de vela aberta antes do PRONTO viram `DECISAO PERDIDA` para os ligados. Pedidos adiados, níveis de S e alvo voltam da memória. **Única e segura.**

---

## 5. Complexidade

`Fichas.mqh` tem 2.722 linhas, 102 variáveis globais de estado (16 por robô), 18 chamadas a `Leitura_Atualiza` e 21 a `Mae_Estado`; a Fase 1 tem 14 saídas antecipadas. Quatro dos achados desta revisão (A-2, M-1, M-6, B-11) e o impasse A-1 nasceram de interações entre mecanismos que, isolados, estão corretos. Os trechos em que a forma do código é o risco:

1. **Dois caminhos de envio com portões duplicados.** Os módulos enviam síncronos (`Ficha_Fecha`, `Ficha_DefineStop`, `Ficha_DefineAlvo`, `Ficha_Cancela`, `Ficha_Entra*`) e a reconciliação envia de novo (Fase 1, Fase 2, pedido adiado, alvo recriado, cancelamento refeito). Cada um tem sua lista de condições: `Mae_EstadoFecha` (`F:1224`), `Mae_PodeEntrar` (`F:1680`), o portão próprio de `Mae_Modifica` (`F:1553-1561`), o da recriação do alvo (`F:2302-2303`), o do nível atravessado (`F:2261`). O A-2 da revisão 2 e o M-6 desta são a mesma família: o módulo recebe um código que o maestro depois contradiz. **Simplificação:** os módulos só escrevem intenção por robô (sair, nível de S, nível de A, entrar com tal limite/stop, cancelar E); uma função por robô, por ciclo, compara intenção × ficha × ordens vivas × trânsito e faz **uma** ação, com prioridade explícita (corte/zeragem > OCO > proteção > saída > correção > entrada) e **um** portão. Somem `BLOQUEADA`/adiamento/"já pedida", `mzSaidaPedida`, `mzECancelPedido`, a recriação do alvo como caso especial e a duplicação de portões.

2. **Classificação do papel do deal por cinco fontes que mudam com o tempo** (mapa, tipo stop, comentário, ficha na colocação, palpite com indeterminação; mais carência e ajuste noturno), recalculada do zero a cada leitura. A mesma ficha pode ser legítima num ciclo e trocada no seguinte (mapa perdido, ordem que aparece, comentário que some). Daí saem B-3, M-1 e a dependência de P3. **Simplificação:** mapa ticket → (robô, papel) persistido na memória do dia; sem mapa, papel só pelo tipo da ordem (stop = S, resto = X, nunca E); deal de robô sem ordem conhecida = trocada na hora (S de emergência e zeragem). Somem `mzIndet`, `mzIndetDesde`, `Mae_FichaEm`/`mzCk`, a leitura de comentário na classificação.

3. **Dois motores de corte.** Fase 1 por ficha, `Mae_CorteConta` pela posição real com um sinalizador global (`mzCorteConta`) que desliga o D1 inteiro (`F:1231-1238`), e a Fase 2 congelada no meio (`F:2228`). As regras de um não enxergam as do outro (A-1, A-2, B-1, B-2). **Simplificação:** um corte só, com prazo: cancela limites; zera por ficha se a cruzada fecha, pela líquida real se não fecha ou se o prazo venceu; trocada, duplicada e travada entram como qualquer ficha.

4. **Fase 1 como cadeia de `return`.** A ordem dos blocos decide quem nunca roda: órfã que falha tapa o corte (B-11); trocada travada tapa o corte (A-2); pedido adiado tapa a correção. **Simplificação:** com o item 1, a prioridade é uma tabela, não a posição de um `return`.

5. **Trava por variável global com sinalizador sem volta** (M-5). Uma concessão com heartbeat que qualquer instância retoma quando o dono some é menor e não tem estado terminal.

Os itens 1 a 3 sozinhos devem tirar perto de 40% de `Fichas.mqh` e as classes de bug "código ao módulo contradito depois", "classificação que muda entre ciclos" e "corte que espera para sempre".

---

## 6. Testes

**Os 87 casos nunca foram executados. Dois falham contra o código:**
- **T39** (`T:647-659`): com `mzTravaPerdida`, espera `Ficha_Fecha` ≠ `ENVIADA`; `F:1809` adia e devolve `ENVIADA`.
- **T34** (`T:546-563`): com o histórico ilegível, espera `BLOQUEADA`; `F:1809` adia e devolve `ENVIADA`.

Os demais passam na simulação contra o código (T22, T28, T37, T61, T62, T63, T64, T65, T68, T69, T70, T71, T84 e T85 conferidos passo a passo).

**Falso positivo ou teste que não exercita o que diz:**
- **T66** (M-1 da revisão 2): o cancelamento da S se resolve síncrono dentro de `Mae_Envia` e nunca passa por `Transito_Resolve`, onde está a correção (`F:2021`). Passaria com o código antigo. Para testar, o K tem de ficar `D_SEM` (timeout) e a ordem executar depois.
- **T70** (M-6): a E é casada por tipo/preço/volume já no envio; os 30 s e a prova `D_NAO` não são exercitados.
- **T58** (primeira metade): o teste injeta o `request_id` que a falsa preenche até em `TIMEOUT` (`CF:235`); o MT5 real não garante.
- **T73**: liga `mzModulosIniciados` à mão; a ordem real (passos 6–9 → `Robo_InitTodos` → entrega) não roda, porque `Robo_InitTodos` é stub.
- **T71**: `FM_RECUSA` é recusa genérica; o teste não distingue recusa de validade.
- **T75**: termina em `ContaPendTipo >= 1`; não mede o intervalo sem S nem o cancelamento das S excedentes.
- Quase todos rodam com `m_testador = true`, que torna `Mae_LeituraConfiavel` verdadeiro sem os 10 s de conexão (`F:933`); `Robo_StopRegra` é stub que devolve 0.

**Testes que fixam comportamento inseguro:** T41 e T75 (duplicada em PROTEGENDO sem correção) e T55 (segunda trocada travada) nunca levam o relógio ao corte; com ele, a ficha não é zerada (A-2).

**Caminhos sem teste:** corte com trânsito que não se resolve (A-1); trocada travada ou PROTEGENDO no corte (A-2); indeterminação de um episódio anterior (M-1); pedido adiado velho (M-2); OCO com a cruzada aberta (M-3); S disparada com deal atrasado (M-4); trava liberada pelo outro gráfico (M-5); os módulos GB, CM e C1 com `Ficha_Fecha` adiado; reinício com mapa perdido (B-3).

---

## 7. Resposta

**Contagem:** CRÍTICA 0 · ALTA 2 · MÉDIA 6 · BAIXA 11. Revisão 2: 24 de 24 fechados no cenário descrito; testes: 85 passam, 2 falham.

**ALTAS:**
- A-1: `Mae_CorteConta` espera o trânsito vazio, mas com a cruzada aberta uma ordem nova sem deal nunca prova desfecho; o corte trava até F e as posições atravessam a noite com o EA no ar.
- A-2: ficha trocada ou duplicada com correção travada, ou em PROTEGENDO, retorna antes do caminho do corte e da ficha da noite: nunca é zerada.

**Veredito: pronto para o Testador** (equivalência 1 e 2: nenhum achado ALTO ou MÉDIO se manifesta com histórico síncrono, e T34/T39 não afetam o Testador). **Não pronto para a demo:** A-1 e A-2 quebram a garantia D2 em caminhos que os testes de falha 3, 10 e 13 exercitam, e a suíte unitária precisa rodar inteira, verde, antes de valer como evidência.

**Opinião franca.** A severidade está convergindo — nenhuma CRÍTICA, e as duas ALTAS moram em cantos raros — mas a contagem não: cada rodada fechou o que foi apontado e abriu interações novas no mesmo número de pontos, e pela segunda vez seguida a nota de implementação declara a suíte conferida com testes que falham. Isso é o sintoma de um núcleo cujo comportamento depende da ordem de blocos com `return`, de 16 marcadores por robô e de duas portas de envio com portões diferentes. Corrigir A-1, A-2 e as MÉDIAS à mão é possível e provavelmente produz uma v1.04 sem ALTAS; mas "sem bugs" não sai desse formato, porque cada correção é mais um marcador e mais um ramo. Antes da demo, a recomendação é a simplificação estrutural da seção 5 (intenção por robô reconciliada por um laço com prioridade explícita, mapa de ordens persistido, um motor de corte com prazo). O núcleo conceitual — ficha pela soma dos deals, S no servidor antes da E, prova antes de concluir — está certo e sobrevive inteiro à troca.
