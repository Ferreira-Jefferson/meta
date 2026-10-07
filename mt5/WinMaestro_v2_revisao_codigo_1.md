# WinMaestro v2.00 — revisão adversarial do código (1)

Objeto: `WinMaestro.mq5`, `WinMaestro/*.mqh` (núcleo: Tipos, Snapshot, Mapa, Estado, Decide, Envia, Partida, Corretora), `WinMaestro_Teste.mq5`, `CorretoraFalsa.mqh`, contra o desenho `WinMaestro_ARQUITETURA_v2.md` (v2.2) e as 41 escolhas de `WinMaestro_implementacao_notas.md`. Os módulos foram comparados por `diff` com `WinSeletor/*.mqh`. Nenhum arquivo foi editado.

Abreviações de arquivo: `S` Snapshot.mqh, `M` Mapa.mqh, `E` Estado.mqh, `D` Decide.mqh, `V` Envia.mqh, `P` Partida.mqh, `C` Corretora.mqh, `T` WinMaestro_Teste.mq5, `CF` CorretoraFalsa.mqh.

## 0. Resumo

| Severidade | Quantidade |
|---|---|
| CRÍTICA | 0 |
| ALTA | 3 (2 do núcleo, 1 da suíte) |
| MÉDIA | 8 |
| BAIXA | 20 |

A tabela de decisão (§4.2) está implementada linha a linha como o desenho manda. As cinco divergências são escolhas documentadas, e só uma delas tem efeito ruim (M-3). Nenhum cenário (a)–(n) simulado contra o código deixa posição sem stop fora das exceções aceitas, nem produz duas saídas além das corridas que o próprio desenho aceita.

Os defeitos que sobram estão em duas bordas:
- o **ciclo de vida de estado persistido**: `externa_desconhecida` nunca expira (A-1);
- as **recusas que chegam depois do envio**: REJECTED no histórico, sem `RETENTA` (A-2).

---

## 1. Achados, em ordem de severidade

### ALTA

#### A-1. `externa_desconhecida` nunca é zerada: depois de um uso do botão, a diferença Δ fica permanente e congela os robôs

**Onde.**
- `P:417` soma Δ_resto em `mzExtDesc`.
- `E:177-178` usa `mzExtDesc` como ponto de partida de toda conta de fichas.
- Nenhuma linha do núcleo volta `mzExtDesc` a 0, salvo `Mae_Reseta`, e logo depois a memória o recarrega (`P:264`).
- A v1.03 zerava quando deixava de ser necessária (`v1.03 Fichas.mqh:684-687`). A v2 perdeu essa regra: é regressão.

**Cenário.**
1. O dono tem uma posição manual aberta antes da janela. Δ fica estável e ele aperta o botão: `mzExtDesc` = +1.
2. No mesmo dia o dono zera na mão. O deal entra na janela como externo e compensa: Δ = 0.
3. No dia seguinte a janela não contém mais esse deal: Δ = −1 desde o primeiro ciclo, para sempre.
4. O recuo da janela (`E:394-406`) não conserta. Se ele alcançar o deal de abertura, a abertura é contada duas vezes: uma em `mzExtDesc`, outra na janela.
5. O mesmo acontece quando o `C_CONTA` zera a posição do dono (decisão 2): o deal MAESTRO fecha o dia certo, e no dia seguinte `eExt` recomeça de `mzExtDesc`.

**Efeito.** Com Δ_resto ≠ 0 permanente, todo robô depende de "Δ externo estável". A estabilidade cai sempre que algum robô deixa de ser provado (M-1), o que acontece a cada ordem cuja linha ainda está pendente num snapshot. A partir daí:
- **todos** os robôs ficam RESTRITOS por 30 s depois de cada ordem de qualquer robô;
- a entrada que cai nesse intervalo vira `ENTRADA_PERDIDA` (`PRAZO_ENTRAR` = 10 s < 30 s);
- X3 atrasa 30 s;
- sequências de ordens podem acionar o bloqueio automático aos 60 s;
- há ALERTA `EXTERNA` diário e o recuo de 10 pregões roda todo dia.

Não deixa posição nua (P1 com lado inequívoco e o corte continuam), mas o EA deixa de operar como foi especificado. O gatilho é o procedimento de recuperação documentado, o botão.

**Correção.**
- Zerar `mzExtDesc` no encerramento do dia, quando o deal MAESTRO deixa líquida 0, ou quando `liquida` = 0 e Σ fichas = 0 com tudo provado.
- E/ou gravar junto o início da janela em que ela foi medida, e descartá-la quando a janela muda (dia novo, recuo).
- Teste: botão com Δ = +1, zeragem manual, dia novo → Δ = 0 e robôs confiáveis.

#### A-2. Recusa assíncrona (aceita no envio, REJECTED no histórico) não liga `em_espera`: rajada de reenvio de S, X e A

**Onde.**
- `M:145-149` transforma CANCELED/REJECTED/EXPIRED no histórico em `NAO_EXECUTADA`.
- Só o retcode do `OrderSend` grava `em_espera` e conta a recusa (`V:206-219`).

**Cenário.** Na bolsa (execução EXCHANGE), o `OrderSend` volta PLACED e a B3 rejeita depois: stop fora do túnel, banda de preço, margem. Por exemplo:
1. P1 envia a S e a S fica REJECTED. No ciclo seguinte ela já é `NAO_EXECUTADA` e não é mais pendente.
2. `cobertura` < 1 e P1 envia outra, sem esperar 5 s.
3. O mesmo vale para X3, para A1 e para `C_CONTA` (o motor da conta também só espera por retcode).
4. Até `RODADAS` = 4 por evento. Cada envio gera vários `OnTradeTransaction` e cada um roda outro `Mae_Ciclo`: dezenas de ordens por segundo.
5. Sem o ALERTA da 5ª recusa (`mzRecusaN` zera em cada envio "aceito", `V:219`).
6. A corretora pode responder `TOO_MANY_REQUESTS` ou bloquear a conta.

É a mesma classe da v1 (B-6/B-11: refazer sem `RETENTA`), num caminho que o desenho não nomeou.

**Correção.**
- No passo 2, quando uma linha E/S/A/X/C passa a `NAO_EXECUTADA` por histórico REJECTED (e, por prudência, também por ausência), gravar `mzEspera[dono][papel]` = agora + `RETENTA` e incrementar `mzRecusaN`.
- Teste com `CF.CancelaPorFora(tk, ORDER_STATE_REJECTED)`, que a falsa já tem e que nenhum teste usa.

#### A-3 (suíte). A suíte nunca rodou, uma verificação falha, e os invariantes de maior risco não são verificados

Achado da revisão independente da suíte, conferido nos trechos citados.

- **`T_P1_ForaDaJanela` (T:309-324) falha.**
  - O deal das 08:30:11 fica fora da janela, que começa às 08:50 (`S:189`; a falsa filtra por instante, `CF:234,241`).
  - Assim `sit` = ZERO, e o primeiro `Ok` exige TROCADA.
  - Logo, "106 verificações" não foi uma bateria executada, e "P1 antes da pré-abertura espera" não tem teste válido.
  - Correção: criar o deal entre 08:50 e 08:55.
- **A ordem do corte não é verificada.** "As S ficam vivas enquanto `liquida` ≠ 0" (§5.2) não tem teste.
  - T_K_Conta, T_K_Recusa, T_K_SemHistorico, T_Cen_j e T_Cen_l olham só o estado final.
  - Um `Dec_CorteConta` com o passo 3 antes do passo 2 passa em todos.
  - Correção: em T_K_Recusa, exigir `Vivo(sg)` em t1, t2 e t3; em T_K_Conta, exigir `DoneHist(sg)` > instante do deal do `C_CONTA`.
- **A corretora falsa nunca executa por preço** (`CF:91`, `CF:266-274`).
  - Stop do lado errado do mercado e limite marketable são aceitos e ficam parados.
  - T_X3_SCruzada monta um estado impossível: bid 118600 com a S de 118700 viva.
  - A corrida "S dispara junto com X3" nunca acontece.
  - REMOVE e MODIFY são síncronos (`CF:293-323`): as guardas "sem K/M pendente" quase não são exercitadas.
  - `OnTradeTransaction` nunca é entregue: `Mae_OnTradeTransaction` (`P:602-612`) não tem teste.
- **T_Cen_k passa por construção.** O SAIR chega depois do `Dispara`, e o stub só escreve a intenção no `Tick`, que não roda com o robô RESTRITO. Logo, X3 nunca é avaliada durante a restrição.

**Correção.** Rodar a suíte antes de qualquer outra coisa. Na falsa:
- modo de execução por preço;
- K e M assíncronos;
- entrega de `OnTradeTransaction`;
- recusa assíncrona (A-2).

Depois disso, acrescentar os testes de ordem (corte, k).

### MÉDIA

#### M-1. "Δ externo estável" se desfaz sempre que algum robô deixa de ser provado (E:332)

**Onde.** `if(!mzTodosProvados || ...) mzDeltaDesde = 0`. Uma linha PENDENTE de K, M, S ou X de qualquer robô zera o relógio. Depois que ela resolve, Δ_resto (o mesmo valor de antes) precisa de mais 30 s.

**Divergência.** Nenhuma: é o desenho literal (§2.2). Mas o desenho não previu Δ externo duradouro, por exemplo uma posição do dono anterior à janela e além do recuo de 10 pregões, ou o caso da A-1. Nesse caso, cada operação de qualquer robô congela todos por 30 s.

**Correção.** Depois de estável, guardar o valor V. Enquanto Δ_resto = V, a estabilidade continua, mesmo com robôs não provados (os não provados já não são confiáveis por conta própria). Zerar só quando Δ_resto muda ou a conexão cai.

#### M-2. `Est_Entrega` converte ENTRAR em MANTER em qualquer `ENTRADA_EXECUTADA`, sem conferir o `id_entrada` (E:593-594)

**Cenário (CM ou RE).**
1. E1 é de COMPRA.
2. O módulo rearma ENTRAR(id2, VENDA, stop acima) e L1 manda o K de E1.
3. E1 enche antes do K.
4. A intenção vira MANTER(stop da VENDA) numa ficha comprada, e `Est_NivelDoModulo` grava esse nível do lado errado como "memória".

A cadeia §4.3 descarta o nível (lado errado) e cai na S viva, na regra ou na emergência, então a ficha fica protegida. Mas a intenção fica errada até o módulo reagir: no CM, até a próxima vela H2, porque `Evento` está vazio (`WinCincoMedias.mqh:788`).

**Correção.** Converter só se `mzInt[r].id_entrada == id`. Senão MANTER(0, 0) e o módulo decide no `Evento`. No CM, implementar `Evento(ENTRADA_EXECUTADA)` (ver M-7).

#### M-3. P3 não move S inválida em relação à E nova: o rearme perde a entrada e a S velha pode abrir posição (D:325, escolha 10)

**Cenário.**
1. Rearme para o mesmo lado (compra) com a limite nova L2 abaixo do nível X da S velha (X ≥ L2 − piso, X < bid).
2. L3 mantém a S, porque é do lado da entrada pedida.
3. P3 exige `Dec_Valido` da S viva, e ela é inválida para a base min(ref, L2). P3 não age.
4. E1 não acha a S no nível (`D:479`) e espera.
5. Aos 10 s chega `ENTRADA_PERDIDA` e L3 cancela a S.
6. Nesses 10 s, se o preço cair até X, a S vende 1 com ficha 0. A ficha fica TROCADA e I2 corrige com perda.

A escolha 10 foi pensada para não afrouxar a S de uma **ficha aberta**. Com f = 0 a S não protege nada.

**Correção.** Aplicar a restrição da escolha 10 só com f ≠ 0. Com f = 0, mover sempre para o nível da cadeia ou, se a S estiver inválida, cancelá-la (L3 deixa de poupá-la).

#### M-4. O relógio dos prazos não é monotônico e mistura o relógio local com o do servidor

**Onde.**
- `mzAgoraMsc` vem de `TimeTradeServer()` (`C:88-96`), que o terminal calcula a partir do relógio do PC.
- Com ele se medem `PROVA`, `CONEXAO`, `RETENTA` e a ausência provada (`S:150-156`).

**Efeito.**
- Um ajuste do relógio do Windows para frente de 30 s ou mais faz `Snap_AusenciaProvada` valer na hora. Uma X de ticket 0 ainda em trânsito vira `NAO_EXECUTADA` e é reenviada: inversão, que I2 corrige.
- `FOLGA_SETUP` compara `enviado_msc` (local) com `ORDER_TIME_SETUP_MSC` (servidor) em `M:89`. Um desvio do PC acima de 5 s impede o casamento de ticket 0, e o resultado é o mesmo da decisão C.
- `Mae_Pronto` (`P:501`) compara `TimeTradeServer` com `TimeGMT`, os dois derivados do PC: nunca detecta o desvio.

**Correção.**
- Medir intervalos com `GetTickCount64` (monotônico) e usar `TimeTradeServer` só para horário de grade.
- Comparar `TimeTradeServer` com o `time_msc` do último tick e dar ALERTA acima de 2 s.

#### M-5. X3 espera a S cruzada sem prazo próprio (D:364-369)

**Situação.** Depois de `PROVA` só sai ALERTA. Se a S cruzada não executa (stop que vira limite e fica para trás num movimento rápido, ou stop emulado que falha), a posição segue sem saída até C + 2 min, que pode estar horas adiante.

**Divergência.** Nenhuma: é o desenho (§4.2 X3, §4.3 abertura). É um risco residual do desenho.

**Correção.** Depois de N × `PROVA` com a S cruzada viva e sem deal, cancelar a S (K) e liberar X3 no ciclo em que o K provar. Ou levar a pergunta à corretora: o que acontece com o stop da B3 atravessado por um gap?

#### M-6. RE: o `ENTRADA_EXECUTADA` pode se perder, e só uma entrada anterior é lembrada (WinRetanguloEma34.mqh:790, 806, 1092-1101)

**Fill perdido.** O evento é entregue mesmo com a ficha TROCADA, DUPLICADA ou absorvida (`E:698`, antes do teste de suspenso), e o bit é gravado. O RE só adota o fill com `TemPosicaoPropria()`, então o perde: stop nunca reancorado, alvo G37 nunca criado. O DM se recupera porque refaz o ajuste no `Tick`; o RE não.

**Só uma entrada anterior.** Com um K sem desfecho atravessando duas reentradas, o fill da primeira cai no `return`.

**Correção.** Guardar um "fill pendente (id, preço)" para reprocessar no `Tick`, e um anel de 3 ou 4 ids com os níveis.

**Escolha 22 em si:** correta. Limpar a espera no pedido é o que o original faz e é o que permite o rearme na mesma vela; a leitura literal do desenho mudaria o sinal. E viva com id velho é impossível, porque E1 exige ZERO e nada pendente.

#### M-7. CM: o rearme para o lado oposto sobrescreve `g_a_favor_ent` e `g_stop_aperta` no pedido (WinCincoMedias.mqh:659)

**Cenário.** A E velha enche durante o rearme. A posição herda o "a favor do mês" da entrada nova, e isso troca a regra de saída da vela seguinte.

**Correção.** Guardar esses valores por id e fixá-los no `Evento(ENTRADA_EXECUTADA)`.

#### M-8 (suíte). Testes que passam com o núcleo errado

Os testes abaixo também passam com um núcleo que nunca envia nada, ou com a guarda que pretendem testar removida:

| Teste | Por que passa com o núcleo errado |
|---|---|
| T_Z, T_E1_Consumido, T_X3_SCruzada, T_Amb_Parado, 2ª metade de T_I4 | um núcleo que nunca envia passa; a 2ª metade de T_I4 confere `mzBloqBotao` que o próprio teste pôs |
| T_P1_SemHistorico | passa sem `okR`, porque `pendS` da S SUMIDA já barra |
| T_I1 | mascarado por I3: zeragem = C |
| T_DeltaVirtual | não confere o A, logo não testa `!abs_virtual` de L2 |
| T_L3_Restrito | não cobre a prova "E CANCELED sem deal" |
| T_M_NaoGrava | para a E, a barreira de `V:187` nunca é alcançada (`pode_entrar` barra antes) |
| T_Cen_g(true) | o K que perde a corrida volta `INVALID_ORDER` na falsa, vira RECUSADA e põe `em_espera[P_K]` de 5 s; o teste não confere esse atraso |

Correção: um negativo isolado por guarda (seção 6).

### BAIXA

| # | Onde | Problema | Correção |
|---|---|---|---|
| B-1 | `M:129` | Linha de ticket 0 já `NAO_EXECUTADA` nunca é casada de novo. O "deal sempre vence" do §2.1 não vale para ela: a E atrasada vira deal de papel X (TROCADA, corrigida), em vez de LEGITIMA | Tentar `Mapa_Casa` também nas `NAO_EXECUTADA` por ausência, por algumas horas |
| B-2 | `V:205`, `V:219` | `OrderSend` falso com retcode 0 (pedido mal formado, cliente) não é recusa: a linha fica PENDENTE com ticket 0 por 30 s, o robô RESTRITO, e P1 reenvia a cada 30 s sem ALERTA | Tratar `!ok && retcode == 0` como recusa definitiva |
| B-3 | `D:172-176` | `cand[2]` pega a primeira S do lado, mesmo inválida. Com 2 S (duplicada), P3 pode calcular a emergência e mover a S válida para ela, afrouxando até 1.200 pts | Pegar a primeira S **válida** |
| B-4 | `E:397` | Com memória perdida, qualquer Δ transitório (deal atrasado) recua a janela 1 pregão a cada 10 s, até 10. Absorções antigas sem `mzAbsVistas` religam o bloqueio com botão | Exigir Δ estável também com memória perdida |
| B-5 | `E:174-241`, `M:227-233` | Laços O(linhas × deals × ordens) por ciclo, até 4 ciclos por evento e vários eventos por ordem. Com a janela recuada 10 pregões, dezenas de ms por ciclo | Índices por ticket (mapa ordenado) ou cache por ciclo |
| B-6 | `D:533-550` | Corrida aceita pelo desenho: S de robô que dispara junto com o `C_CONTA` inverte a líquida até o próximo `C_CONTA` (30 s) | Registrar como risco residual; a alternativa (cancelar antes) é pior |
| B-7 | `E:271-275` | Segunda E ou segundo A do mapa viva cai em `foraIdx` e é cancelada por L4 com o log "fora do mapa", que confunde | Texto do log |
| B-8 | `M:104-109` | O casamento aceita ordem do histórico em qualquer estado, inclusive REJECTED de outro envio do mesmo robô dentro de 5 s | Preferir candidatos vivos ou FILLED, desempatar pelo setup mais próximo |
| B-9 | `E:500-502` | `mzSFaltaDesde` não é zerado em INVALIDO: depois de uma queda longa, I3 pode valer por 1 ou 2 ciclos. P1 vem antes na tabela, então só pesa com P1 em espera | Zerar em `Mae_Invalido` |
| B-10 | DM `WinDeslocamentoMatinal.mqh:429-436` | O SAIR de "stop atravessado" é avaliado uma vez só (`VerificarStop` saiu). Depois de `SAIDA_EXPIRADA` o DM não pede SAIR de novo. A S pré-calculada (no nível reancorado ou mais apertada) continua: não há afrouxamento, porque P3 não move S inválida | Pedir SAIR no `Tick` se o last cruzar `g_stopNivel` |
| B-11 | DM `:434` | Sai com `last <= g_stopNivel + piso` (original: `<= g_stopNivel`) | Documentar |
| B-12 | DM `:391` | Teto de risco sobre `DM_CAPITAL` fixo em R$1.000 (B9), não sobre o saldo | Ciência do dono |
| B-13 | DM `:598` | `MinutoZerarRobo` ignora os inputs de fim de pregão do DM (o C1 respeita os seus) | Uniformizar |
| B-14 | GB `:243` | `DECISAO PERDIDA` impede a partida entre 09:05 e `g_exp`, que o original operava | Documentar (desenho §6) |
| B-15 | GB `:95`, `:310` | O fim do contínuo vem da grade, não de 565 + horário de verão dos EUA antes de 2024-03-11. `StopRegra` usa o preço da ficha e ignora o BE | Conferir no Testador |
| B-16 | CM `:667-668`, CM `AjustaStopAperta` | `static` não volta no `Reseta`; usa o piso no lugar do tick | Documentar |
| B-17 | RE `:837-855`, `:1081`, `:820` | Estado do alvo velho depois que a posição fecha (sem `LimparAlvoOrfao`); `g_barras_esperando` recontado no `Importa`; `g_barra_do_fill` = vela do evento | Zerar no `Tick` sem posição; usar `e.hora` |
| B-18 | C1 `:475` | O stop é validado contra o preço da decisão e a E sai 1 ou 2 ciclos depois. Se o preço entrar no piso, a entrada é recusada (escolha 33), onde o original mandava com SL | Documentar |
| B-19 | módulos (geral) | O `Tick` só roda com o robô confiável. A decisão de abertura de vela pode sair atrasada (C1 a mercado com a cotação de agora) | `DECISAO PERDIDA` também para decisão com mais de N s |
| B-20 | `P:417`, `P:414` | O botão grava Δ só se estável e transforma em `NAO_EXECUTADA` as linhas de mais de 10 min. Uma X de ticket 0 que executou depois pode ser reenviada | Aceito pela decisão C; registrar |

---

## 2. Conformidade com o desenho

### 2.1 Tabela de decisão (§4.2)

| Linha | Situação | Observação |
|---|---|---|
| P1 (R) | CONFORME | `D:269-285`. Lado inequívoco `E:386-387`; fora da janela de ordens `D:559`; não depende da espera de outro papel |
| P2 | CONFORME | `D:287-312`; "menos protetora" correta nos dois lados |
| P3 (R) | DIVERGE (escolha 10) | `D:315-345`: não move S inválida (cruzada ou no piso) nem S com K pendente. Efeito ruim com f = 0: M-3 |
| X1 | CONFORME | `D:347`; exige `confiavel` porque não é linha R |
| X2 | CONFORME | `D:353` |
| X3 | CONFORME | `D:361-379`; todas as guardas, inclusive S cruzada e `em_espera[P_X]` |
| L1 (R) | CONFORME | `D:381-391` |
| L2 | CONFORME (+ §2.2 ii) | `D:393`: `!abs_virtual` |
| L3 (R) | DIVERGE (escolha 35) | `D:402-418`: com ENTRAR ∧ `pode_entrar` cancela a S do lado oposto. Prova em RESTRITO em `D:224-242` |
| L4 | CONFORME | `D:420-433` |
| A1 | CONFORME | `D:435-445` |
| A2 | DIVERGE (escolha 41) | `D:447-458`: exige também `reduz_pend` falso |
| E1 | DIVERGE (escolha 33) | `D:462-493`: exige a S no nível pedido; stop pedido inválido → `ENTRADA_RECUSADA`, id consumido |
| Z | CONFORME | `D:495` |
| O2 | CONFORME (escolha 29) | `D:98-124`: vivas e mapa PENDENTE/VIVA, inclusive do mesmo ciclo |
| em_espera | CONFORME | as linhas de baixo seguem (`D:272`, `D:307`, `D:336`…) |

### 2.2 Intenção efetiva (§4.1)

| Linha | Situação | Observação |
|---|---|---|
| I1 | CONFORME | `D:40-45` |
| I2 | CONFORME | `D:47-48` |
| I3 | CONFORME | `D:50-56`: noite, zeragem, `PRAZO_S_RECUSADA` |
| I4 | CONFORME | `D:58` |
| I5 | CONFORME (+ Init que falhou) | `D:60-77` |
| I6 | CONFORME | `D:79-81` |
| `pode_entrar` | CONFORME | `D:85-91`; exige origem I6 |
| `ENTRADA_PERDIDA`, `SAIDA_EXPIRADA` | CONFORME | `E:649-673`; contados só em ciclos confiáveis |

### 2.3 Dados, validação e ciclo (§1, §2, §3)

| Regra | Situação | Observação |
|---|---|---|
| §1.1 snapshot, base × histórico, INVALIDO | CONFORME | `S:221-258`; `P:544-559` |
| §1.1 preço de referência | CONFORME | `S:118-123` |
| §1.1 janela | DIVERGE (escolha 31) | `S:187-198`: todas as linhas retidas, não só as de episódio aberto. Justificada |
| §1.1 recuo | CONFORME, com ressalva | `E:394-406`: com memória perdida, recua em qualquer Δ (B-4) |
| §1.2 papel fixo; fora do mapa stop = S, outro = X, nunca E | CONFORME | `E:80-114`, `E:269` |
| §1.2 deal não classificado sem prazo | CONFORME | `E:101`, `E:113` |
| §1.2 deal MAESTRO = encerramento | CONFORME | `E:208-213` |
| §1.2 episódio, retenção | CONFORME | `V:152-157`, `E:465-480`, `M:238-252` |
| §1.2 memória | CONFORME, com ressalva | `P:77-109`, `P:204-272`. `externa_desconhecida` não tem regra de saída (A-1) |
| §1.3 fichas, situação, noite, cobertura, `pend`, `reduz_pend` | CONFORME | `E:132-139`, `E:258-305`, `E:357-370` |
| §1.3 absorção e AJUSTE | CONFORME | `E:142-171`, `E:189-205` |
| §1.6 trava | CONFORME (escolha 25) | `P:288-368` |
| §2.1 casamento de ticket 0 | CONFORME | `M:78-118` |
| §2.1 desfechos | CONFORME | `M:123-161` |
| §2.1 K, M, P4 | CONFORME (escolhas 18, 19) | `M:166-221` |
| §2.1 "o deal sempre vence" | DIVERGE (menor) | Não vale para ticket 0 já `NAO_EXECUTADA` (B-1) |
| §2.2 `provado` | CONFORME | `E:310-321`: mais estrito, todas as linhas e não só as do episódio aberto |
| §2.2 Δ estável e absorção virtual | CONFORME | `E:323-353`. O próprio desenho é frágil aqui: M-1 |
| §2.2 lado inequívoco | CONFORME | `E:386-387` |
| §2.3 prazos de restrição | DIVERGE (escolha 14) | Só contam no pregão |
| §2.4 bloqueio | CONFORME | `D:58` + L1/L3; nunca barra S, K, saída ou corte |
| §3 ciclo, RODADAS, passos 5 e 6 | CONFORME | `P:562-600`, `V:87-225`. Mas a recusa assíncrona fica fora do passo 6 (A-2) |
| §4.3 cadeia, validade, emergência única por lado | CONFORME (escolhas 7, 8, 34) | `D:143-201` |
| §5.1 [C, C+2) com I1 | CONFORME | — |
| §5.2 passos 1–3, só com a base | CONFORME (escolha 32) | `D:516-552`; episódios fechados com líquida 0 em `E:471` |
| §5.3 depois de F | CONFORME | `D:519`, `D:535` |
| §6 partida | CONFORME (escolhas 26, 27) | O ambiente "parado" não faz `ExpertRemove` |
| §7 interface dos módulos | CONFORME, com ressalva | M-2: `Est_Entrega` sem id |

---

## 3. Bugs reais, por classe

- **Posição sem stop.** Nenhum caminho fora das exceções aceitas: E sem S viva no nível, RESTRITO sem lado inequívoco, emergência atravessada até os 60 s da decisão m, noite antes da pré-abertura.
  - E1 exige S viva no nível; P2 só corta excesso ou lado errado; L3 só com f = 0 provado; o corte só cancela S com líquida 0.
  - A troca de ticket do P4 tem um instante sem S: inerente ao `OrderModify` da corretora.
- **Duas saídas.** Todas as guardas do §4.4 estão no código. Restam as corridas aceitas pelo desenho:
  - S × X3 com a S não cruzada;
  - S × `C_CONTA` (B-6);
  - X que executou e ficou mais de 30 s fora do histórico (decisão C), agravada por M-4.
- **Ordem duplicada.** Coberta para E (id consumido antes do envio, persistido), S (`pendS` + cobertura), X (`reduz_pend` + não provado), A (`iA`/`pendA` + L4), K e M (`KPend`/`MPend`), `C_CONTA` (`MercadoRecente`). Exceção: a A-2, uma recusa assíncrona por vez, em rajada.
- **Laço criar–cancelar.** P1 × L3 e P1 × P2 fecham como o §4.4 diz. Os módulos decidem por vela, então não há rearme por tick depois de `ENTRADA_RECUSADA`. O laço real que sobra é a rajada de reenvio da A-2.
- **Impasse.** Ticket 0 com 2 candidatos fica PENDENTE até o botão (10 min), como o desenho prevê. O corte só depende da base. Impasse de operação, não de proteção: A-1 e M-1.
- **Armadilhas de MQL5.**
  - **Seleção global:** um `HistorySelect` por ciclo, só em `LeHistorico`; os módulos não chamam `History*`.
  - **Ordem ausente logo após o envio:** a linha fica PENDENTE, nunca SUMIDA, porque SUMIDA exige ter sido VIVA (`M:152`).
  - **double/long:** volumes por `MathRound`, token `uint` exato num double, heartbeat em segundos inteiros. OK.
  - **Arrays:** índices de `mzViva` refeitos a cada ciclo e zerados em INVALIDO (`P:549-554`). OK.
  - **Comparação de double:** `Mae_Igual` com ½ tick. OK.
  - **Tempo:** ver M-4.
- **Persistência e recuperação.**
  - Gravação atômica com checksum e `.bak`.
  - Linha gravada antes do `OrderSend`.
  - Mapa refeito do log com tokens consistentes (`V:78-84` × `P:145-201`).
  - Defeito: `externa_desconhecida` sem expiração (A-1).

---

## 4. Cenários (a)–(n), simulados contra o código

| | Resultado contra o código |
|---|---|
| a | RE −1 aberto por A: TROCADA. P1 calcula a emergência de compra: cand[1] é do lado errado, cand[3] sem posição dá 0. No contínuo, X3 compra 1 (I2), f = 0, L3. CM intacto. **Conforme** |
| b | Executou: `Mapa_Casa` casa a FILLED por magic/tipo/volume/setup (`M:101-110`) → EXECUTADA; Δ_resto = 0 pela linha; só o C1 RESTRITO. Não chegou: `NAO_EXECUTADA` 30 s depois de o histórico firmar (40 s depois da volta), sem `PRAZO_SAIR` correndo, e X3 reenvia. Se o deal da 1ª X aparecer depois, ele **não** volta à linha (B-1), mas `f` é corrigido pelo `DEAL_MAGIC`, e I2 corrige a inversão. **Seguro** |
| c | Deal sem ordem: `CL_NAOCLASS`, todos RESTRITOS. A ordem aparece: externo, absorção GB e DM, `Mae_Bloqueia`. Depois I4: L1 cancela a E do CM, L2 os A, L3 as S. **Conforme** |
| d | S de ontem EXPIRED no histórico (a janela cobre a linha de ontem) → confiável, noite → I3. Na pré-abertura, P1: memória atravessada → emergência gravada. No contínuo, X3 espera a S cruzada (`D:364`), ou envia se a S estiver do lado certo. **Conforme**; risco residual M-5 |
| e | Cinco P1 no mesmo ciclo; E1 no ciclo em que a S aparece. O2 lê o mapa PENDENTE (`D:116-122`) → `ENTRADA_RECUSADA`. **Conforme** |
| f | [C, C+2): o robô da X fica RESTRITO; os outros saem se Δ_resto = 0 (se a X executou sem deal nem FILLED, todos esperam). C+2: K das limites, `C_CONTA` depois de 30 s da X, K das S com líquida 0. **Conforme** |
| g | "Executou antes": K `NAO_EXECUTADA`, E EXECUTADA, `ENTRADA_EXECUTADA`. A intenção NADA não é convertida e o DM põe MANTER no `Evento`. K vence: `ENTRADA_CANCELADA`, L3. **Conforme** |
| h | INVALIDO 10 s, I1 nos confiáveis, motor da conta em C+2 com a base. **Conforme** |
| i | `REASON_PARAMETERS`: trava mantida, memória gravada. I5 mantém a E (L1 compara com os parâmetros da própria E). Init → `pode_entrar` falso para os desligados. **Conforme** |
| j | Conforme. Com histórico ilegível as fichas ficam congeladas no último cálculo (`E:372-379`) e P1 não age (lado inequívoco exige provado). Com externa duradoura vale M-1 |
| k | Posição já em 0: S SUMIDA, Δ_resto ≠ 0, todos RESTRITOS, lado inequívoco falso → nada sai. Deal → f 0. **Conforme** (o teste não prova isso: A-3) |
| l | P1 → X3 recusada → espera 5 s → ALERTA na 5ª → `C_CONTA` em C+2 com `RETENTA`. **Conforme**, se a recusa vier no retcode. Se vier no histórico: A-2 |
| m | Recusa no retcode: conforme. P1 e X3 se alternam a cada 5 s depois dos 60 s. Recusa assíncrona: rajada (A-2) |
| n | Deal antes da posição: Δ_resto = −1, não estável, todos RESTRITOS, sem absorção nem L3. No ciclo seguinte, Δ = 0. **Conforme** |

---

## 5. Lógica de sinal dos módulos

O `diff` contra `WinSeletor/*.mqh` mostra condições, indicadores, fórmulas de stop e alvo, BE e trailing copiados literalmente. Os defaults dos inputs são idênticos. Nenhum módulo chama `Position*`, `Order*`, `History*`, `AccountInfo*`, `CTrade` nem `TimeCurrent`.

Diferenças:
- **De execução**, com efeito no trade: M-2, M-6, M-7, B-10 e B-17 a B-19.
- **De sinal pequenas:** B-11 (piso no DM), B-12 (capital do DM, por B9), B-14 e B-15 (GB).

**Escolha 22 (RE):** correta e melhor que a leitura literal do desenho, com os defeitos de borda da M-6.

**Escolha 23 (C1):** equivalente ao original.

---

## 6. As 41 escolhas: quais são arriscadas

| Escolha | Risco | Motivo |
|---|---|---|
| 10 | **Arriscada** | Com f = 0 deixa a S velha entre a E nova e o preço (M-3) |
| 5 / 39 | Moderada | Intenção mantida pelo maestro; com a conversão sem id vira M-2 |
| 15 / 13 | **Arriscada** | O botão gravando `externa_desconhecida` sem regra de saída (A-1) |
| 18 / 19 / 17 | Moderada | Ausência medida no relógio do PC (M-4) |
| 31 | Aceitável | Janela por todas as linhas retidas: correta e justificada |
| 32 | Boa | Conservadora |
| 33 | Moderada | Recusa entradas em que o original mandava a ordem com SL (B-18). Conservadora |
| 34, 35, 37 | Aceitáveis | 35 só cobre o lado oposto; o mesmo lado é a M-3 |
| 8 / 9 | Aceitáveis | Emergência atravessada → decisão m |
| 14 | Aceitável | Prazos só no pregão |
| 22 | Boa | — |
| 27 | Aceitável | Ambiente parado sem `ExpertRemove` |
| 36 | Boa | id consumido antes do envio |
| Demais | Sem risco identificado | — |

---

## 7. Testes

As 106 verificações rodam o ciclo real (`Mae_Ciclo`) sobre a falsa, com Init pelo caminho do EA. Isso corrige as falhas de construção da v1.

**Simuladas à mão contra o núcleo e que passam:** T_P1_E1, T_A1_X1_X3_L3, T_X3_Recusada, T_L3_OCO, T_L3_Restrito, T_E1_O2, T_K_Conta, T_K_Recusa, T_Cen_b (as duas variantes), T_Cen_n, T_Cen_m, T_Nivel_Emergencia.

**Que falha:** T_P1_ForaDaJanela, na primeira verificação (A-3).

**Que passam com um núcleo errado:**

| Teste | Núcleo errado que ele não pega |
|---|---|
| T_Cen_k | X3 sem `conf` / `reduz_pend` |
| T_K_Conta, T_K_Recusa, T_Cen_j, T_Cen_l | corte com o passo 3 antes do 2 |
| T_P1_SemHistorico | P1 sem `okR` |
| T_I1 | I1 removido (I3 cobre) |
| T_DeltaVirtual | L2 sem `!abs_virtual` |
| T_Z, T_E1_Consumido, T_X3_SCruzada, T_Amb_Parado, 2ª metade de T_I4 | núcleo que nunca envia |
| T_M_NaoGrava | sem a barreira da E em `V:187` |

**Ficam fora:**
- recusa assíncrona (A-2);
- `OnTradeTransaction`;
- execução por preço;
- K e M assíncronos;
- `IDADE_TICK`;
- SPECIFIED;
- piso acima de `TICK_WIN`;
- `externa_desconhecida` através da virada do dia (A-1);
- reinício depois de 18:22.

**Isolamento:** bom. `Mae_Reseta` zera o estado, pasta e GVs próprias, relógio por falsa. Única exceção: T_Mod_C1 depende do gráfico.

---

## 8. Convergência

**Contagem.** A v1.03, na 3ª revisão, tinha 2 ALTA e 6 MÉDIA, e as ALTAS eram de proteção: corte em impasse, ficha trocada nunca zerada. A v2.00, na 1ª revisão, tem 0 CRÍTICA e 3 ALTA, mas nenhuma delas deixa posição sem stop ou com saída dupla:
- A-1 trava a operação;
- A-2 é rajada de reenvio contra a corretora;
- A-3 é da suíte.

As MÉDIAS são, na maioria, de borda (módulos, relógio, um risco residual do desenho).

**Classes que desapareceram por construção:**
- duas portas de envio;
- papel que muda (classificação por comentário);
- saída adiada sem prazo;
- impasse do corte, que agora só depende da base;
- PROTEGENDO travado;
- trava perdida para sempre;
- indeterminação grudenta;
- códigos de retorno contraditos depois;
- cadeia de `return` que tapa as etapas seguintes.

A tabela de prioridade com uma ação por robô e guardas próprias de fato as eliminou: procurei cada uma e não achei.

**Classes que voltaram, em forma menor:**
- **Estado persistido sem regra de saída** (A-1). É a "indeterminação grudenta" da v1, agora em `externa_desconhecida`.
- **Refazer sem RETENTA** (A-2). É a B-6/B-11 da v1, num caminho de recusa que o desenho não nomeou.

As duas ficam **fora** da tabela (passo 2 e memória), e a tabela é justamente a parte que converge.

**Opinião franca.** A v2 converge. A lógica de decisão está certa e conforme ao desenho, e as falhas que restam são de ciclo de vida de dados e de fidelidade da corretora falsa, não de decisão. As correções são locais: algumas linhas cada em `Est_Fichas`/`Mae_DiaNovo`, `Mapa_DesfechoOrdem`, `Est_Confianca` e P3. Nenhuma pede redesenho.

O risco real agora é outro: **nada disso rodou**. A suíte tem uma falha detectável por simples leitura, e a falsa não reproduz as três coisas que mais quebram EA na B3: execução por preço, cancelamento e modificação assíncronos, rejeição assíncrona. O próximo salto de confiança vem de rodar a suíte, de uma falsa mais fiel e do Testador, não de outra revisão de papel.

**Veredito: pronto para o Testador; não pronto para a demo.**
- Para entrar no Testador: rodar a suíte e corrigir T_P1_ForaDaJanela.
- Para a demo: corrigir A-1, A-2, M-1, M-2 e M-3, e acrescentar à falsa a recusa assíncrona e a execução por preço, com os testes da seção 7.
