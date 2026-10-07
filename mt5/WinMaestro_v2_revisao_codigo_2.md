# WinMaestro v2.01 — revisão do código (2)

Objeto: `WinMaestro.mq5`, `WinMaestro/*.mqh` e `WinMaestro_Teste.mq5` (v2.01), conferidos contra os achados de `WinMaestro_v2_revisao_codigo_1.md` e contra o §11 de `WinMaestro_ARQUITETURA_v2.md`. Nenhum arquivo foi editado. Os dois `.ex5` compilam com 0 erros e 0 avisos (logs de 11:44 e 11:45). A suíte não foi executada.

Abreviações: `S` Snapshot.mqh, `M` Mapa.mqh, `E` Estado.mqh, `D` Decide.mqh, `V` Envia.mqh, `P` Partida.mqh, `C` Corretora.mqh, `T` WinMaestro_Teste.mq5, `RE` WinRetanguloEma34.mqh, `CM` WinCincoMedias.mqh.

**Resultado:** nenhum achado novo CRÍTICO ou ALTO. Os 2 altos do núcleo e os 8 médios estão fechados no código. A A-3 fica PARCIAL: a suíte nunca rodou, e um teste reescrito (T_X3_SCruzada) falha contra o código atual por erro na própria verificação.

## 1. Altos e médios da revisão 1

| ID | Situação | Onde | Observação |
|---|---|---|---|
| A-1 | FECHADO | `E:357-368`, `P:292-297`, `P:567` | Zera no dia novo; no mesmo dia, com `liquida` = 0 e Σ deals da janela = 0 por 30 s com histórico lido. O relógio volta a 0 em INVALIDO e com histórico ilegível (`E:398`). Com o deal de fechamento dentro da janela, a externa fica até o dia novo, que é o certo: é ela que explica esse deal |
| A-2 | FECHADO | `M:40-60`, `M:196-201`, `V:208-214` | Caminho único `Rec_Registra`. REJECTED no histórico gera espera e contagem, inclusive para o `C_CONTA` (dono `R_MAE`, lido em `D:558`). A contagem só zera com aceite provado (`M:101`, `M:207`). Cada linha transita para NAO_EXECUTADA uma vez (`M:195`), então não há contagem dupla |
| A-3 | PARCIAL | `T:329-345`, `CF` | Corrigidos: T_P1_ForaDaJanela (o deal das 08:50:11 cai na janela, que começa às 08:50:00), a falsa (preço, recusa assíncrona, K/M assíncronos, transações) e a ordem do corte (T_K_Conta, T_K_Recusa, T_K_SVivas). Em aberto: a suíte nunca rodou, e T_X3_SCruzada falha (§4) |
| M-1 | FECHADO | `E:334-336` | Estabilidade pelo valor de Δ_resto. Zera quando o valor muda, quando o histórico falha ou quando a conexão cai, e também em `P:566` |
| M-2 | FECHADO | `E:625-630` | Só o ENTRAR do mesmo `id_entrada` herda o stop. Outro id vira MANTER(0, 0) |
| M-3 | FECHADO | `D:329`, `D:339`, `D:432` | Com f = 0, P3 move a S inválida. L3 só poupa a S da entrada pedida se ela for válida para essa entrada |
| M-4 | FECHADO | `C:99`, `S:169-175`, `S:265-272`, `P:55-62` | Todo prazo é medido em `mzMono`. Há ALERTA quando o relógio do servidor estimado difere em mais de 2 s do último tick. O `FOLGA_SETUP` continua no relógio do PC, coberto pelo ALERTA |
| M-5 | FECHADO | `D:368-387` | Uma S cruzada e viva há 30 s recebe K, com linha `X3`. A X3 continua exigindo `!pendK` e nenhuma S cruzada |
| M-6 | FECHADO | `RE:799-805`, `RE:1008-1012`, `RE:1126-1150` | Anel de 4 entradas. O fill que chega sem a posição fica pendente e é adotado no primeiro `Tick` com a posição, ou descartado no primeiro `Tick` sem ela |
| M-7 | FECHADO | `CM:665-666`, `CM:803-808` | O "a favor do mês" fica guardado por id e só é aplicado no `ENTRADA_EXECUTADA` |
| M-8 | FECHADO, com ressalva | `T`, §9 das notas | As guardas citadas na revisão 1 têm agora um negativo isolado. Ressalva: T_X3_SCruzada falha contra o código correto (§4) |

## 2. As duas regras que o implementador acrescentou

**P2: entre duas S no mesmo preço, cancela a que está fora do mapa (`D:304-307`).** A regra está correta. Ela só age quando `cobertura` > |f|, e no empate as duas S protegem igual. Manter a S do mapa preserva a linha cujo desfecho o maestro acompanha (EXECUTADA, provado, episódio). Simulei as duas ordens de varredura: nas duas, a S fora do mapa é a cancelada. O alvo continua guardado por `!Mapa_KPend` e por `reduz_pend`. Não há laço, porque depois do K a cobertura fica igual a |f| e P2 para.

**Prova por ausência espera 5 s antes de reenviar (`M:183`, `M:222`).** A regra está correta e é conservadora: ela só soma `RETENTA` a uma ausência que já tem 30 s.
- Custo para S com ficha aberta: até 5 s a mais sem S, depois de 30 s de ausência. A decisão m (60 s) continua contando por `mzSFaltaDesde`.
- Custo para a X de ticket 0 (decisão C): o reenvio sai 5 s mais tarde, o que diminui a chance de saída dupla.
- Efeito colateral (baixo): a ausência não conta na sequência de recusas. Uma corretora que descarta ordens em silêncio gera um reenvio a cada ~35 s, sem o ALERTA da 5ª recusa (B2-1).

## 3. Achados novos críticos ou altos

**Nenhum.** Procurei nos caminhos novos (A-1, A-2, M-1, M-3, M-5, B-1, B-2, B-8, P2) seis tipos de defeito: posição sem stop, duas saídas, ordem duplicada, laço ou rajada de envio, impasse, e estado persistido sem regra de saída.

Os cenários do desenho, simulados ciclo a ciclo contra o código:

| | Resultado |
|---|---|
| b | **Executou:** `Mapa_Casa` casa a ordem FILLED → EXECUTADA → `Rec_Aceita`. Δ_resto = 0, e só o C1 fica RESTRITO até o deal. Depois o C1 fica com f 0 e L3 cancela a S. **Não chegou:** INVALIDO durante a queda; 40 s depois da volta, a ausência é provada (`S:171-174`) → NAO_EXECUTADA + espera X de 5 s → a X3 reenvia. Se o deal da 1ª X aparecer depois, ela é casada de novo (`M:175`, setup ≤ envio + 30 s; o reenvio sai a ≥ 35 s, fora da faixa) → EXECUTADA → a I2 corrige a inversão. A S nunca sai antes: `pendX` barra o P1. **Seguro** |
| f | De C a C+2 vale I1. O robô da X pendente fica RESTRITO; os outros saem pela X3, já que Δ_resto = 0 ou estável pelo valor. Em C+2: K das limites → `C_CONTA` quando nenhuma ordem a mercado tem menos de 30 s (`D:523-529`, relógio monotônico). Recusa por retcode ou REJECTED assíncrono → `em_espera[MAE][X]` de 5 s. Com `liquida` = 0, uma S cancelada por ciclo. **Seguro** |
| k | **Posição já em 0:** S SUMIDA → Δ_resto = −1, o robô não provado e sem lado inequívoco → nada sai. O deal chega e a ficha vai a 0. Se o deal passar de 30 s: a S vira NAO_EXECUTADA e, ao mesmo tempo, Δ estável → absorção virtual. A ficha fica em 0 com `abs_virtual` → P1 não age (nada a proteger) e não há X3. **FILLED sem deal:** Δ_resto = 0 e só esse robô fica RESTRITO. **Seguro** |
| l | P1 põe a S → X3 recusada (retcode ou histórico) → espera 5 s → ALERTA na 5ª → `C_CONTA` em C+2, também com espera. Sem rajada. **Seguro** |
| m | Recusa assíncrona: a linha fica PENDENTE até o REJECTED, o que barra P1 e X3 → depois, espera de 5 s. A linha RECUSADA ou NAO_EXECUTADA de um robô não toca `provado` nem Δ dos outros. Com a S faltando 60 s → I3 → X3 a cada 5 s, alternando com o P1. **Seguro** |

Pontos conferidos à parte:
- **M-5 sem S de reposição:** se a emergência gravada já estiver atravessada (`D:185-190`) e a X3 for recusada, a posição fica sem S até a X sair ou até C+2. Antes do K, a S cruzada que não executa também não protegia. Risco residual, baixo (B2-3).
- **M-1 e a ordem fixa de absorção:** com um deal atrasado mais de 30 s, a absorção virtual pode zerar a ficha de outro robô do mesmo lado. Esse robô fica com a S intacta (L2 e L3 barradas por `abs_virtual`), e o bloqueio automático segura as entradas. A janela é a mesma da decisão C. Registrar (B2-4).

## 4. Suíte: 10 testes simulados contra o código

| Teste | Contra o código | Falha se a linha coberta for removida? |
|---|---|---|
| T_P1_SemHistorico | passa | sim: sem `okR` (`D:270`), a S sai depois dos 5 s de espera |
| T_X3_SCruzada | **FALHA** | — (ver abaixo) |
| T_Cen_k(true) | passa | sim: sem `conf` na X3, sai uma X; sem `okR`, sai uma S |
| T_A1_ExtDescDia | passa | sim: sem `P:292-296`, Δ = −1 no dia 8 |
| T_A1_ExtDescZera | passa | sim: sem `E:357-368`, Δ = −1 permanente e robôs RESTRITOS |
| T_A2_RecusaAssinc | passa (n1 = 2, n2 = 2, n3 = 7, `mzRecusaN` = 6) | sim: sem `M:200`, reenvio a cada ciclo e n2 > 2 |
| T_K_SVivas | passa (2º `C_CONTA` aos ~35 s, S vivas até lá) | sim: sem `Dec_MercadoRecente`, o 2º `C_CONTA` sai no 1º segundo |
| T_M1_DeltaEstavel | passa | sim: com `mzTodosProvados` na regra, o CM fica RESTRITO e não entra |
| T_M3_RearmeMesmoLado | passa (P3 move 118600 → 118000, a E sai a 118500) | sim: sem a exceção f = 0 em `D:329`, a E não sai |
| T_B1_CasaTardia | passa | sim: sem `M:171-176`, o deal da E é papel X e a ficha fica TROCADA |

**T_X3_SCruzada falha contra o código atual (`T:443-447`).** O código faz o que o desenho manda. Em t ≈ 30,25 s, numa única chamada de `Mae_Ciclo`, as 4 RODADAS fazem:
1. o K da S cruzada (linha `X3`);
2. a S de emergência em 117400;
3. a X;
4. o K de L3 sobre a S de 117400, porque a ficha ficou em 0.

`Linha(R_GB, P_K)` devolve a última linha K, que é a de L3, com motivo `"L3"`. Assim, `LMot(lk) == "X3"` é falso. Correção do teste: procurar a linha K com motivo `X3`, ou guardar o índice da primeira K. As outras condições do `Ok` passam.

## 5. Médios e baixos novos

- **B2-1** (`M:183`, `M:222`): ausência sem contagem; uma corretora que descarta ordens em silêncio nunca gera o ALERTA da 5ª recusa. Sugestão: ALERTA a partir da 3ª ausência seguida do mesmo dono e papel.
- **B2-2** (`D:370`, `D:391`): `mzSCruzDesde` só zera quando a X3 vê a S não cruzada. Um SAIR posterior, ainda com S cruzada, manda o K na hora, sem os 30 s.
- **B2-3** (`D:378-386`): M-5 com a emergência já atravessada e X3 recusada deixa a ficha sem S até a X sair ou até C+2. Risco residual.
- **B2-4** (`E:334-336`, `E:159`): Δ estável com robô não provado absorve virtualmente pela ordem fixa GB…C1, possivelmente a ficha de outro robô. A S fica e as entradas bloqueiam. Registrar junto da decisão C.
- **B2-5** (`M:200`, `E:657-661`): uma E rejeitada de forma assíncrona chega ao módulo como `ENTRADA_CANCELADA`, não como `ENTRADA_RECUSADA`. O efeito no módulo é o mesmo.
- **B2-6** (`M:175`): toda linha de ticket 0 em NAO_EXECUTADA do dia roda `Mapa_Casa` a cada ciclo. Custo O(linhas × ordens).
- **B2-7** (`C:61`): comentário duplicado e desatualizado na declaração de `Mono()`.
- **B2-8** (suíte): T_X3_SCruzada falha (§4).

## 6. Veredito

**LIBERADO só para o Testador.** Antes da demo:
1. corrigir a verificação de T_X3_SCruzada (procurar a linha K com motivo `X3`);
2. rodar o `WinMaestro_Teste` inteiro e obter 130/130 PASSOU, com qualquer outra falha tratada antes.
