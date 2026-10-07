# WinMaestro v2: revisão adversarial do desenho do núcleo

Escopo: `WinMaestro_ARQUITETURA_v2.md` (citado como "desenho", linhas do arquivo atual), contra `WinMaestro_ESPECIFICACAO.md` 1.0 ("spec"), as revisões de código 1, 2 e 3 (R1, R2, R3) e a interface atual de `WinGapBarra1.mqh`, `WinCincoMedias.mqh`, `WinDeslocamentoMatinal.mqh`, `WinRetanguloEma34.mqh`, `Win_c1.mqh` e `Corretora.mqh`.

**Placar: 1 CRÍTICA, 8 ALTAS, 16 MÉDIAS, 15 BAIXAS.**

O núcleo conceitual se sustenta: snapshot único, ficha derivada dos deals, mapa com papel fixo, uma ação por robô e prova antes de concluir. Os defeitos estão em quatro lugares: nas guardas das linhas da tabela §3.2, na regra que pula linhas em `em_espera`, no casamento de ordens sem ticket e na fronteira de C + `PRAZO_CORTE`. Todos se corrigem na própria tabela e nas definições, sem mudar a arquitetura.

---

## 1. Integridade do arquivo

A estrutura está íntegra. As 249 linhas, os 20 títulos e todas as tabelas conferem: cada linha de tabela tem o número de colunas do seu cabeçalho, e os `\|` estão escapados. Não há texto duplicado, crase solta ou parêntese desbalanceado, e as referências § apontam para seções que existem. O que sobrou são trechos sem sentido ou que se contradizem:

| Linha | Trecho | Problema | Texto provável |
|---|---|---|---|
| 103 (P1) | "…ou E viva/pendente, **ou S de entrada recém-enviada**) e `cobertura` < …" | É um gatilho para *criar* S que depende de uma S já enviada, e é o único lugar do arquivo onde a expressão aparece. Parece resto de edição. | "ou ENTRAR cuja S de entrada (E2) foi provada NAO_EXECUTADA/RECUSADA", ou apagar o trecho |
| 104 (P2) | "`f` ≠ 0 e há S do lado que aumenta \|f\|, ou `cobertura` > \|f\|" | A precedência é ambígua. Lida como disjunção solta, a regra cancela a S de toda E viva com f = 0 (ver M-3). | "`f` ≠ 0 e (há S do lado que aumenta \|f\| ou `cobertura` > \|f\|)" |
| 23 × 81 × §4 | "`mapa[]` … só muda no passo 5 do ciclo" | O passo 6 grava ticket, `request_id` e retcode, e o §4 muda o desfecho a cada ciclo | "só ganha linhas no passo 5; ticket e desfecho são atualizados nos passos 1 e 6" |
| 123 | "TRANSITORIA vira TROCADA em 10 s" | I2 manda SAIR; a situação não muda de nome | "TRANSITORIA com mais de `PRAZO_TRANSITORIO` sai por I2" |
| 111 (L1) | "depois do K confirmado, P3 move a S e E1 manda a E nova no mesmo episódio" | L3 vem antes de E1 e cancela essa S (ver M-4) | depende da correção M-4 |
| 181 (CM) | "Cancelar e rearmar na mesma vela vira troca de preço da ENTRAR (L1 reaproveita a S)" | Contradiz a linha 97: "ENTRAR com `momento` já enviado não reenvia" | "rearmar = ENTRAR nova com `momento` novo" (ver M-4) |
| 94 × 111 | I6: "`f` = 0 → mantém a E viva" × L1: "intenção ≠ ENTRAR → CANCELA E" | Contradição direta (M-1) | — |
| 53–55 × 89–91, 110 | SAIR = {`motivo`, `desde`} | I1, I3 e X5 usam `SAIR(alvo)`, que não existe na tabela de tipos | acrescentar `alvo` (padrão 0) a SAIR |
| 5 × 24 × 237 | Três listas diferentes do estado que sobrevive entre ciclos | Faltam em todas: `conectado_desde`, início da PARCIAL (60 s / 10 min), início da INVALIDO (ALERTA aos 30 s) e anti-spam por objeto | uma lista só, completa |
| 7 × 75 | "Saem … `PRAZO_SEM_DESFECHO`" × "aos 10 min, bloqueio com botão" | O prazo de 10 min continua em uso, sem nome | constante com nome |

---

## 2. Completude da tabela de decisão

Produto montado: validade {INVALIDO, PARCIAL, COMPLETO} × situação {ZERO, LEGITIMA, TRANSITORIA, TROCADA, DUPLICADA; noite} × pendente {nada, S, E, X, A, K(E), K(A), K(S), M(S), M(A), S sumida} × intenção {NADA, ENTRAR, MANTER, SAIR, CONGELADA} × hora {pré-abertura, contínuo < C, [C, C+2 min), [C+2 min, F), [F, fim da sessão)}, com `em_espera` ligado ou desligado em cada linha.

| Combinação | Defeito | Achado |
|---|---|---|
| SAIR + A viva + X3 em `em_espera` | X5 envia X com o A vivo: duas saídas | A-1 |
| SAIR + E viva + X4 em `em_espera` | X5 envia X com a E viva | A-1 |
| ENTRAR + E viva + L1 em `em_espera` | E1 envia a segunda E (E1 não exige "sem E viva") | A-1 |
| SAIR + S sumida das vivas, sem deal (COMPLETO) | X2 não olha S pendente, então X5 envia X junto com a S que executou; e a S sumida cai em NAO_EXECUTADA na hora, então P1 recria a S | A-2 |
| TROCADA / TRANSITORIA, qualquer hora | o nível da S vem do lado oposto e é recusado em laço; fora do contínuo a ficha fica sem stop | A-3 |
| ZERO + ENTRAR + bloqueio / desligado / pré-abertura / `momento` já enviado | E2 envia S sem E; com `momento` enviado vira laço E2 → L3 → E2 a cada 10 s | A-4 |
| [C+2 min, fim) + fichas opostas que sobram depois do `C_CONTA` | passo 2 cancela as S, P1 recria: laço sem fim | A-5 |
| INVALIDO em [C, F) | o motor de corte não roda | A-6 |
| bloqueio por zeragem manual + E viva de outro robô | a E fica viva, contra a spec 7.1/7.2 | A-7 |
| PARCIAL + nível atravessado | a ficha fica sem stop até C+2 min | A-8 |
| CONGELADA + `f` = 0 + E viva | duas linhas se contradizem | M-1 |
| TRANSITORIA < 10 s + E viva | L1 cancela a E, e a regra de 10 s de I2 nunca é usada | M-2 |
| `f` = 0 + E viva + S (leitura solta de P2) | P2 cancela e P1 recria: ciclo infinito | M-3 |
| MANTER + `f` ≠ 0 + X pendente (depois de `SAIDA_EXPIRADA`) | A1 envia A com o X em voo: duas saídas | M-12 |
| PARCIAL + intenção NADA + E viva | (c) cancela a E; a S fica sozinha durante toda a PARCIAL | M-8 |
| [C+2 min, F) + K de limite recusado em laço | o `C_CONTA` pode nunca sair (ordem interna do passo 2 indefinida) | M-13 |
| [F, fim) + `liquida` ≠ 0 | "K de S" pode tirar a proteção no call | M-13 |
| pré-abertura + noite + nível atravessado | P1 envia a S mesmo assim | M-14 |
| PENDENTE ticket 0 + queda de conexão | "conexão confiável o tempo todo" nunca se cumpre: impasse até o corte | M-9 |
| PENDENTE ticket 0 que executou | não há regra de prova; impasse permanente | C-1 |
| `f` ≠ 0 + NADA (módulo que ainda não adotou a ficha) | Z: NENHUMA. Seguro, porque a S cobre | — |

As linhas sem lacuna: INVALIDO em qualquer combinação (só espera); COMPLETO + ZERO + NADA sem ordens (Z); LEGITIMA + MANTER com S e A no nível (Z); DUPLICADA (P1 completa a cobertura, I3 + X5 corrige 1, P2 retira a S excedente).

---

## 3. Simulação dos cenários contra o desenho

**(a) MT5 morto com CM e RE comprados; a S do RE executa; o alvo enche com o EA fora; o EA volta.** Deals do RE: E +1, S −1, A −1, então f = −1 e `papel_abertura` = A, o que dá TROCADA. CM +1 LEGITIMA, líquida 0, cruzada fechando. Volta: INVALIDO por 10 s, depois COMPLETO. RE: I2 SAIR. P1 manda um BUY_STOP no nível "intenção → memória", e a memória guarda o stop da compra, abaixo do preço: recusa, `em_espera`. No ciclo seguinte P1 é pulada; no contínuo X5 manda a correção (compra 1) e a ficha vai a 0. Fora do contínuo, X1 dá NENHUMA, P1 é recusada a cada 5 s e o RE −1 fica sem stop até 09:00. A exposição real é 0, mas a S do CM pode disparar e deixar a conta vendida sem nenhum stop. **Resposta única. Segura no contínuo; fora dele não, por A-3.**

**(b) X do C1 com TIMEOUT e ticket 0; internet fora por 90 s.** A linha X fica PENDENTE com ticket 0; a S nunca é cancelada; sem conexão nada roda. Na volta:
- *X executou:* o deal chega com `DEAL_ORDER` fora do mapa, é atribuído pelo magic e recebe papel X pelo tipo; f = 0. A linha X não tem como virar EXECUTADA, porque a linha 149 exige `DEAL_ORDER` = ticket e o ticket é 0. Também não vira NAO_EXECUTADA, porque está no histórico. Fica PENDENTE para sempre e `reduz_pendente` nunca desliga. L3 não cancela a S órfã; se ela disparar, o C1 fica −1 TROCADA sem S (P1 espera `reduz_pendente`) e sem saída (X2) até C + 2 min.
- *X não chegou:* a regra do ticket 0 exige "conexão confiável o tempo todo". Depois de 90 s fora, ela nunca se cumpre: a X fica PENDENTE, X2 dá NENHUMA, `SAIDA_EXPIRADA` aos 60 s, e o C1 fica só com a S até o corte.

**Resposta única. Insegura (C-1); a saída se perde (M-9).**

**(c) O dono zera na mão com GB e DM posicionados.** Venda de 2 com magic 0. Se a ordem ainda não está no histórico, o deal fica não classificado: PARCIAL por até 10 s, com as S de GB e DM vivas na conta zerada (P1p não age, condição 4). Depois o deal é classificado externo e reduz abaixo de Σ fichas: absorve GB, depois DM, e liga o bloqueio. L2 cancela os A; L3 cancela as S (f = 0 e intenção ≠ ENTRAR). A E viva do CM **fica**, pelo modificador da linha 97, embora a spec 7.1/7.2 mande cancelá-la; se encher, abre posição depois de o dono ter zerado tudo. O botão libera; as absorções vistas estão na memória, então reiniciar não rebloqueia; `g_decidido`/`g_decidiu` impedem a reentrada. **Resposta única; viola a spec (A-7).**

**(d) Ficha da noite com gap contra.** Partida antes das 09:00. A janela recua até ontem; a linha da E está no mapa, desde que o mapa guarde o pregão anterior (B-10); senão a ficha vira TROCADA. I4 dá SAIR. P1 espera a pré-abertura e manda a S DAY no nível da memória **mesmo atravessado**, porque P1 não tem essa guarda. Recusada: laço de 5 s sem efeito. Aceita: um SELL_STOP acima do bid dispara no leilão ou na abertura, enquanto X5 manda o X às 09:00 com a S viva (X2 não olha S viva), e as duas saídas invertem a ficha. Em PARCIAL, P1p não cria S e a ficha fica sem stop até o corte (A-8). **Resposta única; segura só no ramo "S recusada" (M-14, A-8).**

**(e) 5 robôs entrando no mesmo segundo, 2 deles opostos.** Ciclo 1: E2 manda cinco S. Ciclo 2: as S aparecem VIVA e E1 manda as E. O O2 confere só as `vivas[]` do snapshot, então uma E enviada no mesmo ciclo por um robô anterior na ordem fixa não aparece. Com CM comprando no ask e DM vendendo no ask (o ajuste de livro do DM), as duas podem se cruzar (M-7, P12). Se a E a mercado do C1 enche e o deal atrasa, os snapshots seguintes ficam PARCIAL; passados 10 s do `momento`, as outras E viram `ENTRADA_PERDIDA` (M-6). Nenhuma posição fica sem S. **Segura; não equivalente ao avulso; autonegociação possível.**

**(f) Corte com a cruzada aberta e uma X sem desfecho.** De C a C + 2 min o snapshot é PARCIAL, a tabela não roda (o texto do passo 1 não diz se ela roda em PARCIAL) e as S protegem. Em C + 2 min, o passo 2 cancela as limites, uma por ciclo. O X tem idade > `PROVA`, então não barra: sai `C_CONTA(|liquida|)`, a líquida vai a 0 e as S são canceladas. Se o X ainda estava em voo e executa depois, inverte a conta, e um segundo `C_CONTA` sai depois de `PROVA`, com as S já parcialmente canceladas: até 30 s sem stop, antes de F. Se o snapshot voltar a COMPLETO depois do `C_CONTA` com fichas opostas restantes, P1 e o passo 2 entram em laço (A-5). Se a leitura do histórico falhar, nada disso roda (A-6). **Resposta única só depois de A-5 e A-6.**

**(g) A E do DM enche enquanto o cancelamento por TTL está em voo.** Intenção NADA; L1 manda o K. A E enche: o deal tem `DEAL_ORDER` no mapa e f = +1 LEGITIMA; o K resolve "alvo EXECUTADA". Com NADA e f = +1, nenhuma linha age (Z) e a S cobre. No Tick seguinte, `AjustarStop` vê a ficha e passa a MANTER(stop reancorado); P3 move a S. Se o K vence, `ENTRADA_CANCELADA` e L3 cancela a S. Um K recusado cai em `em_espera`; as linhas seguintes não agem, porque f ≠ 0 ou a intenção não é ENTRAR. **Resposta única e segura.**

**(h) O MT5 reinicia às 18:19 com uma saída guardada e a cruzada aberta.** Não existe "saída guardada" na v2: a X que saiu antes da queda está no mapa como PENDENTE. Sequência: INVALIDO até 18:19:10; PARCIAL; recuo da janela, que pede releitura limitada a uma a cada 10 s e deixa o snapshot INVALIDO entre uma e outra, por até cerca de 100 s. Nenhum módulo recebe `Init`. A X PENDENTE barra P1p só desse robô (as S dele estão vivas). Às 18:22, passo 2: `C_CONTA` e S canceladas, antes de F. Reiniciando às 18:23:30 com a cruzada aberta, o recuo come a janela até F, e as fichas passam a noite com o EA no ar (A-6). **Segura só se o reinício deixar folga para o recuo.**

**(i) O dono desliga 2 robôs posicionados.** `REASON_PARAMETERS`: memória gravada, mesmo token. INVALIDO por 10 s (sem OCO; as S protegem), depois COMPLETO e CONGELADA até o `Init`. A E viva de qualquer robô é cancelada por L1 nesse intervalo (M-1). Os robôs desligados seguem gerindo: "ENTRAR só sustenta uma E já viva". `momentos_enviados` vem da memória, e nenhuma E é duplicada. **Resposta única e segura; perde as E vivas (M-1).**

**(j) Snapshot PARCIAL por 5 min com 3 fichas abertas.** Os módulos ficam sem Tick: nada de trailing do C1, aproximação de alvo do RE, stop que aperta do CM, saída por regra ou TTL de E (M-16). As S vivas protegem e nunca são canceladas fora de L3b. Se uma S ou um A executa, L3b cancela as irmãs. Se falta S, P1p cobre só quem passa nas 6 condições. Bloqueio de entradas aos 60 s. Nenhuma posição fica sem stop, salvo E cancelada por (c) cuja S dispare (M-8) e nível atravessado (A-8). **Resposta única; segura com M-8 e A-8; diverge do avulso.**

**(k) A S executa e o deal chega 3 s depois, enquanto o robô pede saída.**
- *Posição já atualizada:* cruzada aberta, PARCIAL, a tabela não roda, nada é enviado. O deal chega, f = 0 e SAIR se cumpre. Seguro.
- *Posição também atrasada:* snapshot COMPLETO com a S fora das `vivas[]`. Pela linha 154 a S volta a PENDENTE, mas a idade conta desde o envio, então já passa de `PROVA`, e a regra "ticket ≠ 0, ausente das duas listas, COMPLETO" a declara NAO_EXECUTADA na hora. P1 cria uma S nova, e X2 não olha S pendente, então X5 manda o X junto. Duas saídas, mais uma S numa conta já zerada.

**Insegura (A-2).**

**(l) Uma correção é recusada repetidas vezes.** X5 recusado, `em_espera` de 5 s; as linhas seguintes não se aplicam a TROCADA. Retenta a cada 5 s com ALERTA na 5ª recusa (sem o "a cada 5 min" da spec, B-13). A proteção depende de P1 colocar a S: com o nível do lado errado (A-3), a ficha trocada fica sem stop enquanto a correção é recusada. A recusa não liga a trava. Em C + 2 min, `C_CONTA`. **Resposta única; segura só depois de A-3.**

---

## 4. Achados, por severidade

### CRÍTICA

#### C-1. Ordem com ticket 0 que executou não tem prova de execução, e o deal dela ganha papel pelo tipo
- **Onde:** §4, linha 149 (EXECUTADA só por `DEAL_ORDER` = ticket ou pela ordem do ticket no histórico); linha 150 (casamento só para VIVA); linha 151 (casamento só como prova de ausência); §1.2, linha 30 e §1.3, linha 36 (deal com `DEAL_ORDER` fora do mapa recebe papel pelo tipo, nunca E).
- **Cenário 1 (b).** X do C1 com TIMEOUT, ticket 0, que executou: a linha fica PENDENTE para sempre, `reduz_pendente` nunca desliga, L3 nunca cancela a S órfã e P1 nunca cria S. A S dispara, e o C1 fica −1 TROCADA sem stop e sem saída (X2) até C + `PRAZO_CORTE`, com o EA no ar.
- **Cenário 2.** E a mercado do C1, ou limite marcável do CM/DM (que enche antes de aparecer nas `vivas[]`), com TIMEOUT e ticket 0: o deal da entrada recebe papel X, a ficha legítima vira TROCADA e é zerada (I2). A linha E PENDENTE bloqueia E1, E2 e L3 desse robô o resto do dia.
- **Correção:** antes de derivar as fichas, casar toda linha com ticket 0 contra `vivas[]`, `ordens_hist[]` em **qualquer** estado e os deals. A chave é magic, tipo, volume e `setup_msc ≥ enviado − 2 s`; o preço só entra para limite e stop. Usar também o par `request_id` → ordem de `TRADE_TRANSACTION_REQUEST`. Casou: gravar o ticket na linha e seguir pelo estado (FILLED = EXECUTADA, CANCELED = NAO_EXECUTADA). Acrescentar o casamento à linha EXECUTADA de §4.

### ALTA

#### A-1. "Linha em `em_espera` é pulada" deixa passar a linha seguinte com a pré-condição da pulada ainda verdadeira
- **Onde:** §3.2, cabeçalho da linha 99; X3/X4 (108–109) → X5 (110); L1 (111) → E1 (117).
- **Cenário:** RE às 17:00 (I4 SAIR). O K do A é recusado: o A está com M pendente, porque A2 não tem guarda (M-12). X3 entra em `em_espera`, X5 manda X com o A vivo, os dois executam e a ficha fica −1 TROCADA. "Nunca duas saídas" cai. O mesmo vale para X4 com a E viva e para L1: com o K da E recusado e o `momento` novo, E1 manda a segunda E com a antiga viva e as duas podem encher (DUPLICADA). Repete o padrão da cadeia de `return` da v1 em forma de tabela.
- **Correção:** `em_espera` numa linha X ou L leva o robô a NENHUMA até `RETENTA`, e P1 nunca é barrada pela espera de outra linha. Acrescentar guardas explícitas: X5 exige sem A viva, sem E viva ou pendente e sem K pendente; E1 e E2 exigem sem E viva.

#### A-2. A S que some das `vivas[]` volta a PENDENTE com a idade desde o envio e é dada por não executada na hora; X2 não espera S pendente
- **Onde:** §4, linha 154 × linha 151 (ticket ≠ 0, idade ≥ `PROVA`, ausente, COMPLETO); X2, linha 107.
- **Cenário (k):** a S dispara; ordem, posição e deal chegam fora de ordem, com a posição ainda igual: COMPLETO. A S, enviada há horas, é NAO_EXECUTADA no mesmo ciclo. P1 cria uma S nova numa conta que vai a 0 (R3 M-4 de volta), e X5 manda a saída do módulo junto com a S que executou.
- **Correção:** a prova por ausência conta a partir de `sumida_msc`, o instante em que a ordem saiu das `vivas[]`, não do envio. X2 passa a incluir "S pendente ou sumida".

#### A-3. O nível da S não tem lado: TROCADA e TRANSITORIA recebem nível do lado oposto e ficam sem stop
- **Onde:** P1 (103: "intenção → memória → `StopRegra` → emergência"), I6 (94), P3 (105).
- **Cenário (a), (l):** o RE trocado (−1) recebe como nível o stop da compra (memória), abaixo do preço: o BUY_STOP é recusado, cai em `em_espera` e é recusado de novo a cada 5 s. Fora do contínuo, X1 não corrige, e a ficha fica sem stop até 09:00 com o EA no ar. É exatamente o caso que R1 C-2 fechou com a S de emergência. Na TRANSITORIA (E de compra viva, f = −1), P1 e P3 usam o stop da intenção ENTRAR, que é do lado da compra.
- **Correção:** um nível da cadeia só vale se protege o lado de `f` e está do lado certo do preço com o piso; senão, `STOP_EMERGENCIA_PTS` a partir do bid/ask atual. `StopRegra` recebe o lado como parâmetro.

#### A-4. E2 não tem as guardas de E1, e falta um evento de entrada consumida
- **Onde:** E2, linha 118; modificadores, linha 97; §7, linha 174 (`Tick` desde a pré-abertura) e linha 176 (o módulo só limpa a entrada em CANCELADA, RECUSADA ou PERDIDA).
- **Cenário 1:** com bloqueio, robô desligado, pré-abertura ou memória que não grava, a ENTRAR do módulo faz E2 mandar uma S sem E. Ela fica até L3 ou `ENTRADA_PERDIDA`. Com os cinco módulos pedindo o mesmo lado, são até 5 stops abertos numa conta sem posição.
- **Cenário 2:** E e S executam dentro de uma PARCIAL (lag de deal, gap). O módulo nunca vê `tem` e nunca recebe evento, porque E executada não é evento, e fica em ENTRAR com o `momento` já enviado. Daí o laço: E2 manda a S, L3 cancela 10 s depois, E2 manda de novo, pelo resto do dia. No RE, `g_ordem_pendente` nunca é limpo.
- **Correção:** um predicado `pode_entrar` único (sem bloqueio, ligado, contínuo, memória gravando, `momento` não enviado, sem E viva) para E1 e E2. Evento `ENTRADA_EXECUTADA`, ou campo `momento_consumido` na vista; ENTRAR com `momento` consumido = NADA.

#### A-5. Depois de C + `PRAZO_CORTE` o desenho não diz se P e L rodam; com fichas opostas, isso vira laço de S
- **Onde:** §5, passo 2 (linha 163: "As linhas X da tabela deixam de rodar e só a conta age"); passo 3 (164); absorção do `C_CONTA` (166).
- **Cenário:** GB +1, CM +1, RE −1, líquida +1. O `C_CONTA` vende 1 e é absorvido no GB. Sobram CM +1 e RE −1 com a líquida 0. O passo 2 cancela todas as S; se P1 roda, recria (f ≠ 0, cobertura 0); o passo 2 cancela de novo, e assim até o fim da sessão, com stops vivos no call numa conta zerada.
- **Correção:** a partir de C + `PRAZO_CORTE` só o motor da conta age, e as fichas dos robôs são dadas por encerradas até o pregão seguinte, que já começa com a janela zerada. O passo 3 cancela S de robô só com `liquida` = 0.

#### A-6. O passo 2 do corte "lê só a posição e o tempo", mas só roda fora de INVALIDO, e INVALIDO inclui o histórico
- **Onde:** linha 160 ("todo ciclo não INVALIDO") × linha 166 ("lê só a posição real e o tempo"); INVALIDO, linha 74 (qualquer leitura falhou; releitura pendente); linha 69 (no máximo uma releitura a cada 10 s).
- **Cenário:** `HistorySelect` falhando de forma persistente, ou reinício perto do corte com a cruzada aberta, com até 10 recuos × 10 s de INVALIDO (h). O corte não roda e as fichas passam a noite com o EA no ar: é a garantia D2 que R3 A-1 queria fechar.
- **Correção:** o passo 2 exige só `liquida` lida, `vivas[]` lidas, conexão e trava. Histórico ilegível não o impede, e ele não espera deal não classificado quando o histórico está ilegível.

#### A-7. Bloqueio por zeragem manual não cancela as E vivas dos outros robôs
- **Onde:** modificador da linha 97 ("ENTRAR só sustenta uma E já viva"); §1.3, linha 46 e linha 121 ("L1–L3 limpam as ordens **dela**"). A spec 7.1 manda cancelar "as A, as E de todos os robôs" e a 7.2 diz "ao entrar, as E vivas são canceladas". A mudança não está no §10.
- **Cenário (c):** o dono zera tudo às 11:00. A E do CM continua no livro e enche às 11:20, abrindo posição nova depois da ação de emergência do dono.
- **Correção:** ao ligar o bloqueio, a intenção efetiva de todo robô com `f` = 0 e E viva passa a NADA; os módulos recebem `ENTRADA_CANCELADA` pela prova.

#### A-8. P1p com nível atravessado não cria S: ficha sem stop em PARCIAL até o corte
- **Onde:** §3.3, linha 139 ("nível já atravessado → nada (ALERTA; o corte resolve)").
- **Cenário (d), (j):** ficha da noite com gap contra e PARCIAL por um deal que não chega. Nenhuma S, nenhuma saída (a tabela não roda) até C + 2 min: um pregão inteiro sem stop com o EA no ar. Isso está fora das exceções do Princípio 4, que são todas com o EA fora.
- **Correção:** com o nível atravessado, `STOP_EMERGENCIA_PTS` a partir do bid/ask atual, que é sempre colocável. Fora da janela de ordens, espera a pré-abertura.

### MÉDIA

| # | Onde | Achado | Correção |
|---|---|---|---|
| M-1 | I6 (94) × L1 (111) | CONGELADA "mantém a E viva", mas L1 cancela toda E com intenção ≠ ENTRAR. Em toda partida e mudança de input (i), as E vivas são canceladas antes do `Init` | CONGELADA conta para L1 como ENTRAR com os parâmetros da E viva |
| M-2 | I2 (90) × L1 (111) × P1 (103) | TRANSITORIA: L1 cancela a E na hora (f ≠ 0), contra a spec 5.3 ("a E executa em seguida"), e `PRAZO_TRANSITORIO` nunca é usado; P1 tenta S do lado oposto (A-3) | L1, P1 e P3 excluem TRANSITORIA dentro do prazo; ou eliminar TRANSITORIA e tratar como TROCADA. Decidir um dos dois |
| M-3 | P2 (104) | Lida como disjunção solta, cancela a S de toda E viva com f = 0, e P1 recria: ciclo infinito. Com \|f\| ≥ 3, P1 cria uma S de volume \|f\| − cobertura numa ordem só; depois da correção, P2 pode cancelar a de volume 1 e depois a de volume 2, e a ficha fica segundos sem S (R2 B-3) | parênteses explícitos; S complementar sempre de volume 1; P2 cancela só até cobertura = \|f\| |
| M-4 | L3 (113), L1 (111), §7 CM (181) | "S com mais de `PRAZO_S_SEM_E`" não diz contado de quando. Contado do envio, toda S de uma E antiga é cancelada logo depois do K e recriada por E2: "L1 reaproveita a S" é falso, e há uma S a mais por rearme. Se o CM rearmar como "troca de preço" mantendo o `momento`, E1 nunca envia a E nova | contar desde que a E sumiu com f = 0; rearme = ENTRAR com `momento` novo; ou chave de unicidade = id de entrada do módulo |
| M-5 | §1.4 (53) × §1.5 (59) × §7 GB (180) | `ENVIA_E(…, validade)`, mas ENTRAR não leva a expiração; com `SPECIFIED` o GB precisa de `g_exp` | campo `expira` em ENTRAR |
| M-6 | modificador (97) | `PRAZO_ENTRAR` contado do `momento` (abertura da vela). Uma PARCIAL de mais de 10 s na virada, comum quando vários robôs agem juntos (e), ou a janela de decisão do DM (`JanelaDecisaoMin`), viram `ENTRADA_PERDIDA` com o EA no ar | contar do primeiro ciclo COMPLETO com a ENTRAR, ou do primeiro Tick do módulo depois do `momento` |
| M-7 | E1 (117), A1 (115), §2 | O O2 usa o snapshot do início do ciclo: E e A enviadas no mesmo ciclo por robôs anteriores na ordem fixa não aparecem, e a E seguinte pode cruzar com elas (P12) | O2 confere também as linhas E e A do mapa PENDENTE ou VIVA |
| M-8 | PARCIAL (c), linha 75 | Cancela a E, mas a S dela fica durante toda a PARCIAL, que pode durar até o botão. Se a S disparar, a ficha fica sem stop, porque P1p exige a E executada | estender L3b: E provada CANCELED/EXPIRED e nenhum deal no episódio → K das S do episódio |
| M-9 | linha 151 | "conexão confiável **o tempo todo**": contada desde o envio, depois de qualquer queda a prova nunca chega (b, h), e o robô fica com X2 em NENHUMA até o corte | "nos últimos `PROVA` segundos" |
| M-10 | linha 19 | `HistorySelect(janela_inicio, agora)` com `agora` = `TimeTradeServer()`, que é estimativa local: deal com hora de servidor um pouco maior fica de fora, e a cruzada abre sem motivo (PARCIAL, recuo) | limite superior folgado (agora + 1 dia) |
| M-11 | §1.6 (63), §6 (170) | A instância detida fica INVALIDO com a memória do seu `OnInit`. Se toma a trava (heartbeat parado ≥ 10 s; um `OrderSend` síncrono numa queda de rede para o laço desse tempo), opera com mapa velho: as E da outra caem em L4, e os deals delas viram X → TROCADA → zeradas. A tomada não é dita atômica | recarregar a memória ao tomar a trava; `GlobalVariableSetOnCondition`; limiar do heartbeat maior que o timeout do `OrderSend` |
| M-12 | A1 (115), A2 (116) | A1 não exige "não `reduz_pendente`": depois de `SAIDA_EXPIRADA` com X em voo, o módulo volta a MANTER(alvo) e A1 envia um A, o que dá duas saídas. A2 não exige "sem M pendente" (P3 exige): `OrderModify` a cada ciclo | as duas guardas |
| M-13 | §5, passos 2 e 3 | "Uma ação por ciclo" não diz se o `C_CONTA` espera as limites canceladas: um K recusado em laço (l) pode segurar o `C_CONTA` até F. Depois de F, "K de S" sem condição tira a proteção de posição ainda aberta no call | o `C_CONTA` não depende dos K; K de S depois de F só com `liquida` = 0 |
| M-14 | P1 (103) | Sem guarda de nível atravessado: na pré-abertura com gap (d), a S vai num nível já cruzado; se aceita, dispara na abertura junto com o X5 (duas saídas). A spec 9.3: "nenhuma S" | P1 com nível atravessado → nível de emergência a partir do preço (A-8) ou nada fora da PARCIAL, conforme a spec |
| M-15 | §7 (174–176) | Os módulos e o `StopRegra` usam `Ficha_Tem`/`Lado`/`Preco`/`Hora`/`Stop`/`Id`/`Entrada`/`TemAlvo`/`PisoStop`; o §7 não diz se ficam ou se a vista os substitui. `StopRegra` é chamado por I6 antes do `Init` e por P1 em TROCADA | assinatura `StopRegra(const VistaRobo&, lado)` e a lista do que sai |
| M-16 | PARCIAL (75) | Os módulos ficam sem Tick: o TTL da E (DM 15 min, RE 10 velas, validade do CM) não roda e a E pode encher horas depois (item 1.8); trailing, stop que aperta, aproximação do alvo e saída por regra ficam parados (j) | ver §6 desta revisão (confiança por robô) |

### BAIXA

| # | Onde | Achado | Correção |
|---|---|---|---|
| B-1 | 23 × 81 × §4 | Mapa "só muda no passo 5" | ver §1 |
| B-2 | 123 | "TRANSITORIA vira TROCADA" | ver §1 |
| B-3 | 5, 24, 237 | Listas divergentes do estado persistente; faltam `conectado_desde` e os inícios de PARCIAL e INVALIDO | uma lista |
| B-4 | 53–55 | SAIR sem `alvo` | acrescentar |
| B-5 | 103 | "ou S de entrada recém-enviada" | ver §1 |
| B-6 | §6 (170), §1.6 | Conferência do ambiente "com ficha" no `OnInit`, antes de existir snapshot, e "repete por 60 s" no `OnInit`. A trava recusada não faz mais `ExpertRemove` (spec 10.2/10.3), e a mudança não está no §10 | mover para o primeiro COMPLETO; registrar a decisão |
| B-7 | 7 × 75 | O prazo de 10 min sem nome | constante |
| B-8 | 150 | O casamento usa o preço: `ORDER_PRICE_OPEN` de ordem a mercado não é confiável. `setup_msc` (relógio do servidor) × `enviado_msc` (`TimeTradeServer` + `GetTickCount64`): a folga de 2 s é apertada | sem preço para ordem a mercado; folga maior |
| B-9 | 67 | "a S e a E saem no mesmo tick": `OrdersTotal` pode ainda não listar a S logo depois do retorno síncrono; E1 cai no ciclo seguinte. Sem risco | corrigir a afirmação |
| B-10 | 23 ("memória do dia") × 135 | Ficha da noite e "`EXPIRED` = prova" exigem o mapa do pregão anterior | retenção do mapa = janela (até 10 pregões) |
| B-11 | 121 | Deal de magic de robô cuja ordem nunca chega ao histórico depois de `CARENCIA_DEAL`: o papel pelo tipo é impossível (o tipo é da ordem) | definir X, ou usar `trans.order_type` de `DEAL_ADD` |
| B-12 | P3, A2, §4 M | Se o `OrderModify` trocar o ticket na B3/Rico (P4), o M nunca prova "feito" e a S nova vira "fora do mapa" | depende de P4; tratar ticket novo do mesmo magic/tipo como a mesma linha |
| B-13 | 81 | "ALERTA na 5ª seguida", sem "a cada 5 min enquanto durar" (spec 4.5) | acrescentar |
| B-14 | I2–I4 antes de I6 | Em PROTEGENDO saem correção e zeragem do robô; a spec e R1 M-5 limitam a S, cancelamentos e corte | registrar como decisão (é o que fecha R3 A-2) |
| B-15 | X4, L1, L2, L3, passo 2 | Nenhum exige "sem K pendente do mesmo alvo": o cancelamento é reenviado a cada ciclo enquanto o primeiro não prova; o segundo é recusado, cai em `em_espera` e alimenta A-1 | guarda "sem K pendente" |

---

## 5. Os módulos

| Robô | Comportamento | Coberto pela interface? | Falta |
|---|---|---|---|
| GB | entrada `SPECIFIED` até `g_exp`; BE = mover a S; alvo (o GB também usa A, `WinGapBarra1.mqh:194`) | sim: ENTRAR, MANTER(stop/BE, alvo), NADA em `g_exp` | a expiração em ENTRAR (M-5) |
| CM | entrada limite marcável; S de reserva; stop que aperta (nunca afrouxa, conta do módulo); saída na vela H2 | sim: ENTRAR(limite, reserva), MANTER(stop) | rearme na mesma vela (M-4); a saída de uma vela vale 60 s e depois se perde (decisão 4) |
| DM | decisão das 10:30 com `JanelaDecisaoMin`; limite ajustada ao livro; stop reancorado no fill; TTL 15 min | sim: ENTRAR, MANTER(stop reancorado), SAIR se atravessado, NADA no TTL | `PRAZO_ENTRAR` contado do `momento` corta a janela de decisão (M-6); TTL parado em PARCIAL (M-16) |
| RE | E com stop e alvo originais; reancora no fill; alvo que se aproxima, inclusive marcável | sim: MANTER(stop, alvo novo) por vela; A2 move | sem evento de entrada executada, `g_ordem_pendente` não é limpo se o episódio acontece dentro de uma PARCIAL (A-4); `LimparAlvoOrfao` sai, mas o reset de `g_ticket_alvo` tem de ficar |
| C1 | entrada a mercado com a S antes; trailing que pode afrouxar; esticada e canal na H1; BE por M1 | sim: ENTRAR(limite 0, stop), MANTER(stop qualquer, P3 move nos dois sentidos), SAIR | ticket 0 na E a mercado (C-1) |

**A lógica de sinal fica preservada** nos cinco: os cálculos de barra não mudam e o portão de vela não é consumido em PARCIAL, porque o módulo não recebe Tick. Muda a execução:
- (i) a E limite sai pelo menos um ciclo depois da S (S antes de E). Indiferente no Testador; no real, um round-trip a mais nas limites marcáveis do CM e do DM;
- (ii) `PRAZO_ENTRAR` e `PRAZO_SAIR` transformam atrasos de estado em entradas e saídas perdidas (M-6);
- (iii) PARCIAL congela as regras dos cinco robôs (M-16);
- (iv) na TRANSITORIA, L1 cancela a E em vez de deixá-la encher (M-2).

A regra "o módulo só limpa com evento" precisa do evento de entrada executada (A-4). Sem ele, a vista não distingue "E ainda não listada" de "E consumida".

---

## 6. Implementabilidade em MQL5

Nenhuma API citada é inexistente: `TimeTradeServer`, `GetTickCount64`, `TERMINAL_CONNECTED`, `ERR_TRADE_POSITION_NOT_FOUND`, `OrderGetTicket`, `ORDER_TIME_SETUP_MSC`, `ORDER_STATE_FILLED`/`PARTIAL`/`CANCELED`/`REJECTED`/`EXPIRED`, `SYMBOL_EXPIRATION_MODE`, `TRADE_ACTION_MODIFY`, `EventSetMillisecondTimer`, `GlobalVariableSetOnCondition`, `FileFlush` e `request_id` no `MqlTradeResult`. As premissas que não se sustentam:
1. **`HistorySelect(…, agora)` com `TimeTradeServer()`** pode excluir o deal mais recente (M-10).
2. **Ordem listada logo depois do `OrderSend` síncrono** não é garantida (B-9).
3. **Preço da ordem a mercado no histórico** não serve de chave (B-8, C-1).
4. **Heartbeat a cada ciclo:** o `OrderSend` síncrono bloqueia o laço durante o envio e, numa queda de rede, pode passar do limiar de 10 s (M-11).
5. **`OrderModify` mantém o ticket** depende de P4 (B-12).
6. **O papel pelo tipo** exige a ordem no histórico: o deal não carrega o tipo da ordem (B-11).

---

## 7. Simplicidade

O que ainda reproduz a complexidade da v1:
1. **Pular a linha em `em_espera`** é a cadeia de `return` com outra roupa: a ordem das linhas volta a decidir quem age quando uma falha (A-1). A regra "falhou → o robô fica em NENHUMA até `RETENTA`, P1 nunca barrada" é menor e não tem bypass.
2. **PARCIAL como modo global com mini-tabela própria** (P1p com 6 condições, L3b, (a)–(d)). Uma cruzada aberta por um deal de um robô congela os cinco. A alternativa é **confiança por robô**: a ficha de r é confiável quando todas as ordens do episódio de r têm prova (as condições 1–3 e 6 de P1p, que já são por robô). Os robôs confiáveis rodam a tabela inteira, inclusive saídas por regra e TTL; os outros só P1, P1p e L3b. Somem a PARCIAL como nível, a linha (c) e M-16, e A-8 e M-8 ficam no mesmo lugar.
3. **Dois regimes de corte com a fronteira em C + 2 min** (A-5, M-13). Sobrevive o achado de R3 ("dois motores de corte"). Basta declarar que em C + `PRAZO_CORTE` as fichas se encerram e só o motor da conta age.
4. **Quatro prazos de intenção** (`PRAZO_ENTRAR`, `PRAZO_SAIR`, `PRAZO_S_SEM_E`, `PRAZO_TRANSITORIO`) mais o `momento`. `PRAZO_TRANSITORIO` some se a TRANSITORIA for tratada como TROCADA (M-2). `PRAZO_S_SEM_E` some se E2 e E1 forem um passo só ("abrir episódio": S e, provada a S, E, com o mesmo predicado `pode_entrar`).
5. **I1–I7 com modificadores por cima** é uma segunda tabela antes da tabela. Bloqueio, robô desligado, memória e contínuo cabem no predicado `pode_entrar` de E1/E2, e o bloco de modificadores sai.

O tamanho estimado (~1.480 linhas no núcleo) é plausível com essas reduções.

---

## 8. Resposta

**Contagem:** CRÍTICA 1 · ALTA 8 · MÉDIA 16 · BAIXA 15.

**CRÍTICA e ALTAS:**
- **C-1:** ordem com ticket 0 que executou nunca prova EXECUTADA e o deal dela vira X: X executada deixa a S órfã viva o dia todo (se disparar, a ficha fica sem stop e sem saída até o corte), e E executada vira TROCADA e é zerada.
- **A-1:** a linha em `em_espera` é pulada e a seguinte age com a pré-condição da pulada ainda viva: X com A ou E viva (duas saídas), segunda E com a primeira viva.
- **A-2:** S sumida volta a PENDENTE com a idade desde o envio e é dada por não executada na hora; X2 não espera S pendente; cenário (k) inseguro.
- **A-3:** o nível da S não confere o lado: TROCADA e TRANSITORIA recebem nível do lado oposto, recusado em laço; fora do contínuo a ficha fica sem stop.
- **A-4:** E2 sem as guardas de E1 e sem evento de entrada consumida: S sem E com bloqueio ou na pré-abertura, e laço de S a cada 10 s quando o episódio termina dentro de uma PARCIAL.
- **A-5:** depois de C + `PRAZO_CORTE` não se diz se P e L rodam; fichas opostas que sobram depois do `C_CONTA` geram laço cancela/cria S até o fim da sessão.
- **A-6:** o passo 2 do corte só roda fora de INVALIDO, e INVALIDO inclui histórico ilegível e releitura pendente; a garantia D2 depende do histórico.
- **A-7:** o bloqueio por zeragem manual mantém as E vivas dos outros robôs, contra a spec 7.1/7.2 e sem decisão do dono.
- **A-8:** P1p com nível atravessado não cria S; em PARCIAL a ficha fica sem stop até o corte, com o EA no ar.

**Veredito: pronto com ajustes listados.** Os nove ajustes CRÍTICO e ALTOS são definições e guardas da própria tabela, não mudanças de arquitetura. Têm de entrar no desenho antes da primeira linha de código, junto com M-1, M-2, M-3, M-9 e M-13, que tocam as mesmas linhas. O ajuste estrutural de maior retorno é trocar o "pula a linha" de `em_espera` por "o robô espera" (§7 item 1). A confiança por robô no lugar da PARCIAL global (§7 item 2) é a simplificação que mais reduz casos; fica a critério do dono, porque mexe na decisão 6.
