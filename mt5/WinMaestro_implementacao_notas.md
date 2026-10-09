# WinMaestro v2.03 — notas de implementação

Implementação do desenho `WinMaestro_ARQUITETURA_v2.md` (v2.2) sobre a especificação `WinMaestro_ESPECIFICACAO.md` (1.0), com as decisões do dono de 2026-10-07 marcadas no §11 do desenho (C, m, A, B, D, E; `ChartID` como pergunta à plataforma). O núcleo da v1.03 (`Fichas.mqh`, `Recupera.mqh`) foi substituído; a v1.03 saiu do repositório na limpeza de 2026-10-07 (recuperável pelo git: `git show 257b1e4:mt5/WinMaestro_v1.03_historico/...`).

**v2.03 (2026-10-08):** parada diária pedida pelo dono (spec 7.3): resultado líquido realizado do dia dos robôs ≤ −`Risco_PerdaDiaPct`% de `Risco_Capital` → nenhuma entrada nova até o pregão seguinte. Como entra no desenho, decisões e teste no §11. Compilação no MetaEditor da Rico: `WinMaestro.mq5` e `testes/WinMaestro_TesteParada.mq5`, 0 erros e 0 avisos cada. A v2.02 é recuperável pelo git (commit `cd96a56`); o terminal da Rico ficou com a v2.02 até a revisão da v2.03.

**v2.02 (2026-10-07):** todos os achados de `WinMaestro_v2_revisao_codigo_2.md` (0 críticos, 0 altos; B2-1 a B2-8) foram corrigidos; tabela achado → correção → teste no §10. As regras do desenho que mudaram (B2-1, B2-2, B2-3, B2-4, B2-5 e a leitura da memória da 2.01) estão no §11 do desenho, com data.

**v2.01 (2026-10-07):** todos os achados de `WinMaestro_v2_revisao_codigo_1.md` (0 críticos, 3 altos, 8 médios, 20 baixos) foram corrigidos ou registrados; tabela achado → correção → teste no §8, regra de saída de cada campo da memória no §7, testes reescritos no §9. As regras do desenho que mudaram (M-1, M-5, A-1, A-2) estão no §11 do desenho, com data.

Compilação no MetaEditor da Rico (v2.02): `WinMaestro.mq5` e o EA de teste da época, 0 erros e 0 avisos cada. Os testes não foram executados (o terminal não foi aberto); ver §5 e §10. O EA de teste e a corretora falsa foram removidos do repositório em 2026-10-07 (§5).

## 1. Arquivos

| Arquivo | Papel |
|---|---|
| `WinMaestro.mq5` | EA: inputs, ganchos núcleo → módulos, `OnInit`/`OnDeinit`/`OnTimer`/`OnTick`/`OnTradeTransaction`/`OnChartEvent` |
| `WinMaestro/Tipos.mqh` | constantes do desenho, tipos (`Intencao`, `VistaRobo`, `SEvento`, `SLinha`, `SEst`) e o estado global, separado em memória, RAM e derivado |
| `WinMaestro/Snapshot.mqh` | passo 1: leitura única do snapshot; base × histórico; janela; preço de referência; grade e horários |
| `WinMaestro/Mapa.mqh` | passo 2: casamento de ticket 0 e desfechos de E/S/A/X, K e M; retenção do mapa |
| `WinMaestro/Estado.mqh` | passo 3: fichas, absorção, encerramento, Δ, provado, confiável, lado inequívoco, prazos de restrição, episódios, correções, vista, eventos e `Tick` dos módulos |
| `WinMaestro/Decide.mqh` | passo 4: intenção efetiva (I1–I6), tabela (P1–Z), nível da S, O2, motor de corte |
| `WinMaestro/Envia.mqh` | passos 5 e 6: linha no mapa e no log antes do `OrderSend`, heartbeat em volta, retcodes, `em_espera` |
| `WinMaestro/Partida.mqh` | trava, memória (exporta/importa, mapa refeito do log), ambiente, `PRONTO`, botão, painel, o ciclo |
| `WinMaestro/Corretora.mqh` | porta única da corretora (interface + classe real; o `#ifndef WINMAESTRO_TESTE` é resto do EA de teste removido e não muda nada no EA) |
| `WinMaestro/Memoria.mqh`, `Log.mqh`, `Grade.mqh`, `Inputs.mqh` | memória em disco, log, grade B3, inputs |
| `WinMaestro/Risco.mqh` (v2.03) | passo 3: resultado do dia e parada diária (`Risco_Dia`, liga `mzBloqDia`) |
| `WinMaestro/RiscoRegra.mqh` (v2.03) | funções puras, sem dependência do núcleo: a conta das fichas por deal que `Est_Fichas` faz (`Risco_Aplica`, `Risco_Externo`, `Risco_Encerra`, `Risco_FechaDeal`, `Risco_ParAjuste`) e a regra da parada (`Risco_Acumula`, `Risco_ParadaDe`) |
| `testes/WinMaestro_TesteParada.mq5` (v2.03) | script de teste do resultado por robô e da regra da parada (37 verificações) |
| `WinMaestro/WinGapBarra1.mqh` … `Win_c1.mqh` | os 5 módulos na interface de intenção |

`Tipos.mqh` não está na lista do §10 do desenho: guarda as constantes e o estado que os seis arquivos do núcleo compartilham, para que nenhum deles dependa de outro só para ter um tipo.

Na corretora: `AgoraMsc()` entrou na interface (o ms vem do `GetTickCount64` relativo à mudança do segundo de `TimeTradeServer`, §1.1) e `LeOrdemHist()` saiu, porque `HistoryOrderSelect` troca a seleção global de histórico e o desenho exige um único `HistorySelect` por ciclo. **v2.01 (M-4):** `Mono()` entrou na interface: relógio monotônico (`GetTickCount64`; no Testador, `TimeCurrent` × 1000). Todo prazo (`PROVA`, `CONEXAO`, `RETENTA`, `PRAZO_*`, ausência provada, Δ estável, heartbeat da memória, painel) é medido em `mzMono`; `mzAgora`/`mzAgoraMsc` (servidor estimado) só dão o horário da grade, os instantes gravados e o `FOLGA_SETUP` contra o `ORDER_TIME_SETUP_MSC`. As linhas do mapa ganharam `enviado_mono` e `sumida_mono` (RAM; refeitos na carga da memória e do log por `Mae_MonoDe`, pela idade no relógio do servidor).

## 2. Desenho → código

### 2.1 Dados, ciclo e confiança

| Desenho | Arquivo: função |
|---|---|
| §1.1 snapshot, base, INVALIDO | `Snapshot.mqh: Snap_Le`; `Partida.mqh: Mae_Invalido` (ALERTA aos 30 s e a cada 5 min pelo anti-spam) |
| §1.1 `agora_msc` | `Corretora.mqh: CCorretoraReal::AgoraMsc` |
| §1.1 `conexao_ok` (`CONEXAO`) | `Snap_Le` (`mzConexaoDesde`) |
| §1.1 `req_tickets[]` | `Snapshot.mqh: Snap_RequestVisto`, `Snap_TicketDoRequest`; chamado por `Partida.mqh: Mae_OnTradeTransaction` |
| §1.1 `janela_inicio` | `Snapshot.mqh: Snap_JanelaInicio` |
| §1.1 recuo da janela (spec 3.2) | `Estado.mqh: Est_Recuo` |
| §1.1 preço de referência | `Snapshot.mqh: Snap_Ref`; piso: `Snap_Piso` |
| §1.2 mapa (linha, papel fixo, desfecho) | `Tipos.mqh: SLinha`; `Envia.mqh: Env_Executa` (única criação de linha) |
| §1.2 papel fora do mapa (stop = S, outro = X, nunca E) | `Estado.mqh: Est_Classifica`, `Est_Ordens` |
| §1.2 deal não classificado, sem prazo | `Est_Classifica` (`CL_NAOCLASS`), `Est_Fichas` |
| §1.2 deal MAESTRO = encerramento | `Est_Fichas` (ramo `CL_MAESTRO`) |
| §1.2 episódio | `Env_Executa` (abre na S), `Estado.mqh: Est_Episodios`, `Est_FechaEpisodio` |
| §1.2 memória e retenção | `Partida.mqh: Mae_Exporta`, `Mae_CarregaMemoria`, `Mae_DiaNovo`; `Mapa.mqh: Mapa_Retencao` |
| §1.3 `f`, preço, hora, id, situação, noite | `Estado.mqh: Est_Aplica`, `Est_Fichas`, `Est_Deriva` |
| §1.3 vivas × mapa, cobertura, `pend`, `reduz_pend` | `Estado.mqh: Est_Ordens`, `Est_Cob` |
| §1.3 absorção (spec 7.1), AJUSTE (P14) | `Estado.mqh: Est_Externo`, `Est_Fichas` |
| §1.4 intenção | `Tipos.mqh: Intencao`; `Estado.mqh: Int_Nada`, `Int_Entrar`, `Int_Manter`, `Int_Sair` |
| §1.5 ação | `Envia.mqh: SAcao`, `Env_Executa` |
| §1.6 trava | `Partida.mqh: Trava_Nomes`, `Trava_Tenta`, `Trava_Confere`, `Trava_Hb`, `Trava_Libera`; heartbeat antes e depois do `OrderSend` em `Env_Executa` |
| §2.1 casamento de ticket 0 | `Mapa.mqh: Mapa_Casa` |
| §2.1 desfechos E/S/A/X | `Mapa.mqh: Mapa_DesfechoOrdem` |
| §2.1 K | `Mapa.mqh: Mapa_DesfechoK` |
| §2.1 M e P4 | `Mapa.mqh: Mapa_DesfechoM` |
| §2.1 ausência provada (decisões 3 e C) | `Snapshot.mqh: Snap_AusenciaProvada` (relógio monotônico, v2.01) |
| §2.1 busca de deal/ordem do histórico por ticket | `Snapshot.mqh: Snap_Indexa`, `Snap_Busca` (índices ordenados, busca binária; v2.01, B-5) |
| §3 passo 6 + recusa pelo histórico (v2.01, A-2) e por ausência (v2.02, B2-1) | `Mapa.mqh: Rec_Registra` (único caminho de recusa), `Rec_Aceita` |
| §2.1 o deal sempre vence | `Mapa_DesfechoOrdem` (linha `NAO_EXECUTADA` reavaliada só por deal ou FILLED; a de ticket 0 é casada de novo com ordem criada até `PROVA` depois do envio, B-1) |
| §2.2 `provado` | `Estado.mqh: Est_Provado` |
| §2.2 Δ, Δ_resto | `Est_Fichas` (fim) |
| §2.2 Δ externo estável e deal virtual | `Estado.mqh: Est_Confianca`, `Est_Deriva` (`Est_Externo(..., true)`) |
| §2.2 `confiavel`, lado inequívoco | `Est_Deriva` |
| §2.3 `PRAZO_BLOQUEIO`, `PRAZO_BOTAO` | `Estado.mqh: Est_Prazos` |
| §2.4 bloqueio | `Estado.mqh: Mae_Bloqueio`; `Partida.mqh: Mae_Bloqueia`, `Mae_Desbloqueia`, `Mae_BotaoClique` |
| §3 ciclo, `RODADAS` | `Partida.mqh: Mae_CicloUm`, `Mae_Ciclo` |
| §3 passo 5 (registro antes; memória que não grava) | `Env_Executa` |
| §3 passo 6 (envio, RECUSADA, `em_espera`, ALERTA na 5ª) | `Env_Executa`, `Env_RecusaDefinitiva`, `Rec_Registra` |
| §1.2 regra de saída de `externa_desconhecida` (v2.01, A-1) | `Estado.mqh: Est_Deriva` (30 s de líquida e deals em 0), `Partida.mqh: Mae_DiaNovo` |
| relógio do PC × último tick (v2.01, M-4) | `Snapshot.mqh: Snap_Le` (`mzRelogioDesvio`, ALERTA `AMBIENTE`) |

### 2.2 Intenção efetiva e tabela (§4)

Cada linha é um bloco de `Decide.mqh` com o identificador do desenho no comentário (`//--- P1 (R): ...`, `//--- X3: ...`).

| Desenho | Arquivo: função |
|---|---|
| I1, I2, I3, I4, I5, I6 | `Decide.mqh: Dec_Efetiva` (um bloco por linha); zeragem do robo: `Dec_Zeragem` |
| `pode_entrar` | `Decide.mqh: Dec_PodeEntrar` |
| `ENTRADA_PERDIDA` (`PRAZO_ENTRAR`), `SAIDA_EXPIRADA` (`PRAZO_SAIR`) | `Estado.mqh: Est_PrazosIntencao` |
| P1, P2, P3, X1, X2, X3, L1, L2, L3, L4, A1, A2, E1, Z | `Decide.mqh: Dec_Tabela` (um bloco por linha, na ordem do desenho) |
| `em_espera` por papel | `Decide.mqh: Dec_Espera`; gravado em `Env_Executa` |
| L3 em RESTRITO só com prova | `Decide.mqh: Dec_ProvaL3` |
| X3 "nenhuma S em nível cruzado" | `Decide.mqh: Dec_SCruzada`, `Dec_SCruzadaPreco`; prazo próprio (v2.01, M-5) no bloco X3 de `Dec_Tabela`; relógio da S cruzada em todo ciclo (v2.02, B2-2): `Dec_SCruzRelogio`, chamado por `Partida.mqh: Mae_CicloUm` |
| O2 (vivas e mapa PENDENTE/VIVA) | `Decide.mqh: Dec_O2`, `Dec_Cruza` |
| §4.3 cadeia, validade, emergência | `Decide.mqh: Dec_Base`, `Dec_Valido`, `Dec_NivelS` |
| E1 `ENTRADA_RECUSADA(autoneg)` | `Dec_Tabela` (`AC_RECUSA_E`) e `Dec_Passo4` |

### 2.3 Corte, partida e módulos

| Desenho | Arquivo: função |
|---|---|
| §5.1 [C, C + 2 min) com I1 | `Dec_Efetiva` (I1) e `Dec_Tabela` |
| §5.2 passos 1, 2 e 3 | `Decide.mqh: Dec_CorteConta` (blocos `5.2 passo 1/2/3`); `Dec_MercadoRecente`, `Dec_MercadoViva` |
| §5.2 episódios fechados com líquida 0 | `Est_Episodios` |
| §5.3 depois de F | `Dec_CorteConta` (`antesF`) e `Mae_JanelaOrdens` (até F + 15 min) |
| §6 `OnInit` e partida | `WinMaestro.mq5: OnInit`; `Partida.mqh: Mae_Reseta`, `Mae_Partida` |
| §6 ambiente (NETTING, tick, PROTEGENDO, parado) | `Partida.mqh: Mae_Ambiente` |
| §6 `Init(vista)` no primeiro ciclo confiável; intenção inicial | `Estado.mqh: Est_Modulos`, `Est_IntencaoInicial` |
| §6 `PRONTO`, deals com o EA fora | `Partida.mqh: Mae_Pronto`; `Estado.mqh: Est_LogDeals` |
| §6 `DECISAO PERDIDA` | `Estado.mqh: Ficha_DecisaoPerdida`, chamada pelos módulos no momento da decisão |
| §6 memória perdida → linhas `ORDEM` do log | `Partida.mqh: Mae_MapaDoLog`; formato em `Envia.mqh: Env_LinhaLog` |
| §7 `Tick(vista, intenção)` | ganchos `Robo_Tick` em `WinMaestro.mq5`; `Est_Modulos` |
| §7 eventos | `Estado.mqh: Est_EventosLinhas`, `Est_Entrega` |
| §7 getters `Ficha_*`, `StopRegra(r, lado)` | `Estado.mqh: Ficha_Tem` … `Ficha_PisoStop`, `Ficha_NovoId`; `StopRegra(lado)` em cada módulo |

| Módulo | Intenção (desenho §7) |
|---|---|
| GB | `AvaliaSinal` → ENTRAR(`expira` = `g_exp`); `GerirPosicao` → MANTER(stop pedido ou BE, alvo); depois de `g_exp` → NADA; `PendentesNossas` e `Zerar` saíram |
| CM | `Entra` → ENTRAR(limite, reserva a 4.945 pts, id novo); `AjustaStopAperta` → MANTER(stop que aperta); `Fecha` → SAIR; `Cancela` → NADA |
| DM | `Decidir` → ENTRAR; `AjustarStop` (no `ENTRADA_EXECUTADA`) → MANTER(stop reancorado), SAIR se atravessado; TTL → NADA; `g_ordem` limpo só no evento; `VerificarStop` saiu |
| RE | `ArmarEntrada` → ENTRAR; `ENTRADA_EXECUTADA` → MANTER(stop reancorado, alvo); `AproximarAlvo` → MANTER(alvo novo); `LimparAlvoOrfao` saiu; `ZerarPregao` só arruma o estado |
| C1 | `Entra` → ENTRAR(limite 0, stop); `AtualizaPosicao` → MANTER(trailing) ou SAIR; `VerificaBreakEven` → SAIR |

Nos cinco módulos, `TimeCurrent()` virou `Agora()` (o `v.agora` da vista) e nenhum chama `Position*`, `Order*`, `History*`, `AccountInfo*` nem `CTrade`. O resto do código de sinal é o de `mt5/WinSeletor/*.mqh`, com as adaptações marcadas `WinMaestro:`.

## 3. Escolhas em ambiguidades

1. **Magic do MAESTRO** = 80089999 (`C_CONTA` e os K da conta).
2. **Fim da sessão** (janela de ordens, §4.2 P1, §5.3) = F + 15 min, o call de fechamento. A grade não tem essa coluna.
3. **Janela de ordens**: nenhuma ordem fora de [pré-abertura, F + 15 min) num dia útil. A tabela inteira espera fora dela.
4. **Tick dos módulos** só com ficha ZERO ou LEGITIMA de hoje e fora de PROTEGENDO. Ficha trocada, duplicada ou da noite deixa o módulo suspenso (spec 3.1, 8 e 9.3: "o módulo nunca as vê", "sem `Tick()` até a ficha zerar").
5. **A intenção mora no maestro** (`mzInt[r]`, RAM) e o módulo a altera por referência no `Tick` e nos eventos. O maestro a ajusta em quatro pontos: `ENTRADA_EXECUTADA` com ENTRAR do **mesmo** `id_entrada` → MANTER(stop do ENTRAR, sem alvo), de outro id (rearme) → MANTER(0, 0), e o módulo decide no `Evento` (v2.01, M-2); `ENTRADA_CANCELADA/RECUSADA/PERDIDA` do mesmo `id_entrada` → NADA; `SAIDA_EXPIRADA` → MANTER(stop 0 = cadeia, sem alvo); ficha que volta a 0 com MANTER/SAIR → NADA. No `Init` a intenção inicial é a da CONGELADA (MANTER nos níveis da memória; ENTRAR da E viva; senão NADA).
6. **Nível pedido da memória** muda só quando o módulo pede um nível novo (diferente do último que pediu). Assim a emergência gravada continua sendo o "nível da memória" até o módulo pedir outro (§4.3, RV2 N-2).
7. **Emergência**: base = min(referência, preço da E) na compra e max na venda, distância max(1.200, piso + 5), arredondada para fora (floor na compra, ceil na venda). Garante que ela é sempre válida no instante do cálculo, inclusive para a S de uma E longe do preço.
8. **Emergência já atravessada** e nenhum candidato válido: não se recalcula (§4.3 "nunca movida"). **v2.02 (B2-3):** com a ficha aberta a S vai ao primeiro nível válido além da referência (ALERTA `STOP`) e a saída segue com `RETENTA`; com ficha 0 P1 não age, registra ALERTA, e as linhas de baixo seguem.
9. **P1 sem nível colocável** (sem referência; ou emergência atravessada com ficha 0) não bloqueia as linhas de baixo.
10. **P3 não move S cruzada nem S dentro do piso** do preço de referência **quando a ficha está aberta**: ela é a saída, e movê-la afrouxaria um stop prestes a executar. Com ficha 0 a S não protege nada e vai ao nível da cadeia; e L3 só poupa a S da entrada pedida se ela estiver válida para essa entrada (v2.01, M-3). Nunca move S com K ou M pendente.
11. **P3 e a regra do robô**: `StopRegra` só é consultada quando intenção, memória e S viva falham, para não ler barras e indicadores a cada 250 ms.
12. **Absorção parcial**: uma ficha de \|f\| = 2 absorvida por um deal de volume 1 vai a \|f\| = 1 (a conta Σ fichas + externa = líquida fecha); a spec só trata fichas de 1 contrato.
13. **Bloqueio automático** = algum robô RESTRITO há 60 s ou absorção virtual ativa; sai sozinho. **Bloqueio com botão** = zeragem manual absorvida (ticket não reconhecido), RESTRITO há 10 min, 2ª correção em 10 min. Persistido.
14. **Prazos de restrição** só contam no pregão (pré-abertura até C + 2 min de dia útil). Fora dele um histórico ilegível à noite não liga bloqueio para o dia seguinte.
15. **Botão**: reconhece as absorções vistas e os deals ainda não classificados (passam a externos); linhas sem desfecho há 10 min viram `NAO_EXECUTADA` (o deal ainda vence); Δ_resto vira externa desconhecida só se estiver estável há 30 s, para não gravar um atraso normal de deal como posição externa. Os relógios de RESTRITO recomeçam.
16. **Correção** = X enviada com a intenção efetiva I2 (linha com motivo `I2`). Conta a correção executada (deal visto).
17. **Ausência provada** exige histórico lido e conexão ok nos últimos 30 s, no relógio monotônico. Como o histórico só é lido com a base firme, depois de uma queda a primeira prova por ausência sai 40 s depois da volta da internet (10 s de `CONEXAO` + 30 s). Desde a v2.01 a ausência liga a `em_espera` do papel (`RETENTA`): o reenvio sai 5 s depois. Desde a v2.02 ela também conta como recusa (B2-1).
18. **K** com o alvo ausente das vivas e do histórico há 30 s vira `NAO_EXECUTADA`, para o K não segurar o robô; a linha do próprio alvo decide o resto.
19. **M** cujo alvo executou ou foi cancelado vira `NAO_EXECUTADA` na hora.
20. **`id_entrada`** é gerado pelo maestro (`Ficha_NovoId`: crescente, ≥ o instante em ms, persistido). Os módulos pedem um id novo a cada pedido de entrada.
21. **`DECISAO PERDIDA`**: decisão com momento anterior ao `OnInit` desta execução. O momento é o de cada robô: GB 09:05, CM e C1 abertura da vela, DM a M1 da decisão, RE o fechamento da vela M15.
22. **RE, estado de espera da entrada**: o desenho diz "`g_ordem_pendente` limpo só no evento". Ao pé da letra isso impede o rearme na mesma vela que o original faz (o retângulo morre, outro é detectado e a entrada nova é armada no mesmo `ProcessarBarraFechada`). A implementação limpa a espera como o original e guarda os níveis da entrada atual e das **4 anteriores** (anel, v2.01 M-6) por `id_entrada`; um `ENTRADA_EXECUTADA` de qualquer delas é adotado com os níveis dela. Fill que chega sem a posição própria (ficha trocada, duplicada, absorvida) fica pendente e é adotado no primeiro `Tick` com a posição; um `Tick` sem a posição o descarta.
23. **C1, break-even depois de `AtualizaPosicao`**: o original só checava o BE se a posição ainda existia depois do `PositionClose` síncrono; aqui, se `AtualizaPosicao` não pediu SAIR naquela vela.
24. **GB e o alvo**: `GerirPosicao` declara o alvo a cada `Tick` (constante, calculado do preço da ficha); A1 cria o A se faltar, A2 não age porque o nível não muda.
25. **Trava**: a remoção por "segunda instância viva" exige ver o heartbeat alheio mudar ao longo de mais de 60 s (primeira e última mudança vistas). Token = `(uint)(ChartID ^ (ChartID >> 32))`, nunca 0. A variável apagada é recriada e tomada pela operação atômica a partir de 0.
26. **Memória** inválida quando a versão gravada não é a 2.02 nem a 2.01 (mesmo formato; a da v1.03 e a da v2.00 são ignoradas) ou é de outra conta, servidor ou símbolo. As chaves dos módulos só valem no mesmo dia (`Car_*`).
27. **Ambiente "parado"** (falha sem ficha nem ordem de robô): o EA não manda nada e reconfere a cada 30 s, em vez de `ExpertRemove`.
28. **Retenção do mapa**: no dia novo saem as linhas de dias anteriores que não são do episódio aberto do robô; as do MAESTRO e sem episódio saem sempre. Listas de tickets (absorções, deals logados, reconhecidos) guardam os 500 mais recentes.
29. **O2 de E a mercado** usa o ask/bid válido como preço; sem livro válido, qualquer limite oposta de outro robô conta como cruzamento.
30. **Preço da E a mercado e do `C_CONTA`** no pedido: ask na compra, bid na venda; preenchimento `RETURN` com execução de bolsa, senão IOC/FOK (P15).
31. **Janela do histórico** (§1.1): o mais antigo entre o início de hoje − 10 min, o primeiro envio de **qualquer** linha retida no mapa − 1 min e o recuo de hoje. O desenho fala em "episódio aberto"; com essa leitura literal a janela encolheria no meio do dia quando o episódio da noite fecha, a linha E de ontem ficaria sem o deal na janela e o robô ficaria não provado o resto do dia (com bloqueio de entradas aos 60 s). Como a retenção só guarda linhas de hoje e de episódios abertos no dia novo, as duas leituras coincidem na virada do dia.
32. **Motor de corte, passo 2**: "ordem a mercado PENDENTE com menos de `PROVA`" inclui também a executada e a sumida com menos de 30 s. Um `C_CONTA` executado cuja posição ainda não atualizou não gera um segundo `C_CONTA` (a tabela tem essa proteção pelo Δ; o motor da conta lê só a líquida).
33. **E1 exige a S no nível pedido pela intenção**, e um stop pedido inválido (atravessado ou dentro do piso em relação a min/max(referência, E)) recusa a entrada (`ENTRADA_RECUSADA`, id consumido) em vez de entrar com a S de emergência, que seria um risco que o robô não pediu. A S de emergência que P1 já tiver posto sai por L3.
34. **Emergência por lado**: a emergência gravada vale só para o lado que protegia (`mzEmergLado`). Ficha que inverte no mesmo episódio ganha a emergência do outro lado.
35. **L3 com ENTRAR e `pode_entrar`**: a S do lado que não protege a entrada pedida (rearme para o lado oposto) também é cancelada; a S da entrada pedida fica.
36. **`id_entrada` consumido antes do envio** da E e devolvido se o envio nem sai (memória que não grava): o módulo recebe `ENTRADA_PERDIDA` pelo `PRAZO_ENTRAR`. Consumir antes evita reaproveitar o id depois de um reinício entre o envio e a gravação.
37. **E a mercado listada nas vivas** conta como E pendente, não como E viva: L1 e X2 nunca mandam cancelar uma ordem a mercado.
38. **`PRAZO_SAIR`** zera a contagem em ciclo INVALIDO; o tempo sem conexão não conta.
39. **Absorção virtual** não volta a intenção do módulo a NADA (a ficha absorvida conserva S, A e a intenção até o deal real, §2.2 ii).
40. **Memória** não é gravada sem a trava (inclusive pelo botão e pela gravação periódica).
41. **A2** exige `reduz_pend` falso (RV M-12), como A1.

Escolhas novas da v2.01:

42. **Regra de saída de `externa_desconhecida`** (A-1): zera no dia novo e, no mesmo dia, quando `liquida` = 0 e a soma dos deals da janela é 0 por `PROVA` seguidos, com o histórico lido (o relógio volta a 0 em INVALIDO e com histórico ilegível). **Não** zera só porque a líquida chegou a 0: com o deal de fechamento dentro da janela (zeragem manual, ou o `C_CONTA`), é ela que explica esse deal, e tirá-la criaria um Δ até o dia seguinte. Os 30 s seguram o deal de fechamento atrasado.
43. **Recusa, um caminho só** (A-2): `Rec_Registra(dono, papel, motivo)` é chamada pelo retcode de recusa (`Env_Executa`), pelo REJECTED no histórico (`Mapa_DesfechoOrdem`) e pela prova por ausência (até a v2.01 esta só ligava a espera; desde a v2.02 conta também, B2-1). `OrderSend` falso com retcode 0 também é recusa (B-2). A contagem só zera com aceite provado (`Rec_Aceita`): a ordem executou, ou está VIVA há `RETENTA`, e foi enviada depois da última recusa do mesmo dono e papel. "Viva há `RETENTA`", e não "viva", porque a recusa assíncrona pode listar a ordem por um instante antes do REJECTED; "enviada depois da última recusa", para uma ordem velha que segue viva não zerar a sequência de recusas das novas.
44. **Δ externo estável pelo valor** (M-1, §11 do desenho): `delta_desde` só volta a 0 quando Δ_resto muda de valor, o histórico falha ou a conexão cai.
45. **Prazo próprio da X3** (M-5, §11 do desenho): S cruzada e viva há `PROVA` → K dela, com a linha `X3`. Desde a v2.02 (B2-2) o relógio (`mzSCruzDesde`) é atualizado em todo ciclo com a base, com qualquer intenção: conta desde que a S ficou cruzada e volta a 0 quando ela deixa de estar. Um SAIR que chega com a S cruzada há 30 s ou mais manda o K no mesmo ciclo; com menos, espera o resto. `PROVA` e não 2 × `PROVA`, porque o `SAIR` do módulo expira em `PRAZO_SAIR` (60 s) e o prazo da X3 vence antes. Provado o K, P1 repõe a S no nível válido da cadeia (emergência, se preciso) e a X sai no ciclo seguinte.
46. **P2, empate na "menos protetora"**: entre S do mesmo nível, cancela a que está fora do mapa e mantém a do robô. Apareceu no teste do casamento por `request_id`, onde uma S idêntica fora do mapa competia com a S casada.
47. **Casamento de ticket 0** (B-8): candidatos vivos ou executados primeiro; CANCELED/REJECTED/EXPIRED só sem nenhum deles; mais de um na classe escolhida = ambíguo. A linha de ticket 0 já `NAO_EXECUTADA` (do dia) é casada de novo só com ordem criada até `PROVA` depois do envio dela, para não pegar o reenvio (B-1).
48. **Recuo da janela só com Δ estável**, com ou sem memória (B-4).
49. **`DECISAO PERDIDA` também por atraso** (B-19): decisão que chega mais de 120 s depois do seu momento.
50. **Externa e `s_falta_desde` em INVALIDO** (B-9): os relógios de S faltando e da regra de saída da externa voltam a 0 em INVALIDO; contam de novo com a base firme.

Escolhas novas da v2.02:

51. **Nível da S com a emergência atravessada** (B2-3): compra → `floor((ref − piso) / 5) × 5`, menos 5 se não ficar estritamente abaixo de `ref − piso`; venda simétrica. É o nível válido mais perto do preço, e não um novo `ref − 1.200`, porque a emergência é única por episódio (§4.3) e a ficha nessa situação já pede a saída. Nada é gravado: nos ciclos seguintes a S viva é o candidato da cadeia, e um nível válido pedido pelo módulo a move (P3).
52. **Atribuição da absorção virtual** (B2-4): uma linha "explica" o Δ se o robô dela tem ficha do lado que o Δ reduz, ela é do lado do Δ, não tem deal na janela, estava sem desfecho quando o Δ apareceu e foi enviada (ou sumiu) no máximo `PROVA` antes do início do Δ (`mzDeltaDesde`). O limite de tempo deixa de fora uma NAO_EXECUTADA antiga do dia, e o teste dá o mesmo resultado antes e depois da prova por ausência (PENDENTE → NAO_EXECUTADA), para o robô absorvido não trocar de um ciclo para o outro. O robô atribuído absorve até a própria ficha; o resto vai pela ordem fixa.
53. **Portão do recasamento** (B2-6): a linha de ticket 0 já NAO_EXECUTADA só chama `Mapa_Casa` quando o snapshot tem ordem do magic do dono cujo ticket não está em nenhuma linha (`Mapa_PortaoRecasa`, uma vez por passo 2, depois de M e K, com os tickets do mapa ordenados e busca binária; a lista só é montada se houver linha assim). O `request_id` que chegar tarde só casa quando a ordem aparece no snapshot, que é quando o desfecho dela pode ser lido.
54. **Memória da 2.01** lida pela 2.02 (`WM_VERSAO_MEM_COMPAT`): o formato não mudou, e recusá-la apagaria na troca de versão o bloqueio com botão, os episódios abertos e a externa desconhecida.
55. **`mzCasaChamadas`**: contador em RAM das chamadas de `Mapa_Casa`, só diagnóstico (o teste do B2-6 o lê). Zerado no `Mae_Reseta`.

## 4. Achados das revisões anteriores → onde estão tratados

### 4.1 Revisão do código 3 (R3)

| Achado | Onde |
|---|---|
| A-1 corte em impasse com a cruzada aberta | `Dec_CorteConta`: só a base, espera só ordem a mercado com menos de 30 s, sem histórico (§5.2) |
| A-2 trocada/duplicada travada ou PROTEGENDO nunca zerada | I1–I3 vêm antes de I5 em `Dec_Efetiva`; correção nunca trava (`Est_Correcoes` só bloqueia entradas); `Dec_CorteConta` |
| M-1 indeterminação grudenta | não existe: deal sem ordem é não classificado só enquanto a ordem não aparece (`Est_Classifica`) |
| M-2 saída adiada sem prazo | `Est_PrazosIntencao` (`SAIDA_EXPIRADA` aos 60 s de ciclos confiáveis) |
| M-3 OCO com a cruzada aberta | L3 em RESTRITO com prova (`Dec_ProvaL3`) |
| M-4 S recriada com deal atrasado | linha SUMIDA conta como pendente (`Mapa_DesfechoOrdem`); P1 exige nenhuma S pendente/sumida |
| M-5 trava perdida permanente | `Trava_Confere` + `Trava_Tenta`: retomada atômica com heartbeat parado; INVALIDO enquanto isso (sem `Tick`) |
| M-6 código ao módulo contradito depois | não há código de retorno: o módulo escreve a intenção |
| B-1 corrida carência × corte | não há carência; `Dec_CorteConta` não olha deals |
| B-2 robô do C escolhido errado | o `C_CONTA` é da conta (magic MAESTRO), deal = encerramento |
| B-3 mapa não persistido | `Mae_Exporta` grava o mapa inteiro; `T_M_Reinicio` |
| B-4 K sem regra de idade | `Mapa_DesfechoK` (ausência provada e "alvo ainda viva após 30 s") |
| B-5 `EXECUTOU_ANTES` para o A | o evento não existe; só a linha E gera `ENTRADA_*` |
| B-6 recusa contada errada | `mzRecusaN` conta só retcode de recusa, por dono e papel |
| B-7 FILLED sem deal virava não executada | FILLED/PARTIAL = EXECUTADA (`Mapa_DesfechoOrdem`) |
| B-8 pedido adiado em PROTEGENDO | não há pedido adiado; PROTEGENDO = I5 com I1–I3 acima |
| B-9 absorções não persistidas | `mzAbsVistas`, `mzReconh` na memória |
| B-10 "alvo executou antes" adiado | X3 exige `reduz_pend` falso e sem A viva |
| B-11 órfã que falha tapa o resto | uma ação por robô por ciclo; `em_espera` por papel; as linhas de baixo seguem |
| §6 testes que passam por construção, T66/T70/T58/T73 | `WinMaestro_Teste.mq5`: casamento sem `request_id` por padrão (`m_req_no_timeout = false`), Init pelo ciclo real, prova por ausência pelo relógio da falsa (§5 abaixo) |
| §5 complexidade (duas portas de envio, classificação mutável, dois cortes, cadeia de `return`, trava sem volta) | uma porta (`Env_Executa`); papel fixo do mapa; um motor de corte; tabela de prioridade; trava com retomada |

### 4.2 Revisões do desenho (RV, RV2) e das revisões de código 1 e 2

O §9 do desenho lista cada achado contra o mecanismo. A implementação de cada mecanismo:

| Mecanismo do §9 | Onde |
|---|---|
| [S] base e confiança por robô | `Snap_Le`, `Est_Provado`, `Est_Confianca`, `Est_Deriva` |
| [M] mapa persistido, papel fixo, casamento antes das fichas | `Mapa.mqh` inteiro; `Mae_CicloUm` roda `Mapa_Passo2` antes de `Est_Deriva`; `Mae_Exporta` |
| [T] tabela com guardas e espera por papel | `Dec_Tabela`, `Dec_Espera` |
| [N] nível com lado, emergência única, referência validada | `Dec_Base`, `Dec_Valido`, `Dec_NivelS`, `Snap_Ref` |
| [I] intenção e eventos | `Est_Modulos`, `Est_EventosLinhas`, `Est_Entrega`, `Est_PrazosIntencao`, módulos |
| [C] motor de corte | `Dec_CorteConta`, `Est_Episodios` |
| [K] trava | `Trava_*` |
| [P] memória, ALERTA, logs por ticket | `Mae_GravaMemoria`, `Log_Cond`, `mzDealsLog`, `mzAbsVistas` |
| RV2 N-1 (Δ virtual só estável) | `Est_Confianca` (30 s, conexão ok), absorção virtual sem botão e sem L2/L3 (`abs_virtual`) |
| RV2 N-2 (emergência não persegue) | `Dec_NivelS`, escolha 6 |
| RV2 N-3 (referência validada; X3 espera S cruzada) | `Snap_Ref`, `Dec_SCruzada` |
| RV2 N-4 (deal MAESTRO = encerramento) | `Est_Fichas` |
| RV2 N-5 (trava inerte) | `Trava_Tenta`, escolha 25 |
| RV2 N-6 (`C_CONTA` com `RETENTA`) | `Env_Executa` (`mzEspera[R_MAE][P_X]`), `Dec_CorteConta` |
| RV2 C-1 residuais | `Mapa_Casa` exclui tickets gravados; deal sem ordem espera; `NAO_EXECUTADA` → EXECUTADA |
| RV M-10 (`HistorySelect` até agora + 1 dia) | `Snap_Le` |
| RV B-10 (retenção por episódio) | `Mapa_Retencao` |
| R1/R2 armadilhas de MQL5 | seleção global de histórico: só `LeHistorico`, uma vez por ciclo; ordem fora das vivas logo após o envio: PENDENTE até 30 s, nunca SUMIDA; deal atrasado: FILLED = EXECUTADA, `provado` exige o deal, Δ_resto; double em GlobalVariable: token `uint` e heartbeat em segundos inteiros |

## 5. Testes

**Removidos em 2026-10-07, a pedido do dono:** o EA de teste e a corretora falsa descritos nesta seção (e citados no §4 e no §6) não existem mais no repositório; recuperar com `git show 988e8e4:mt5/WinMaestro_Teste.mq5` e `git show 988e8e4:mt5/WinMaestro/CorretoraFalsa.mqh`. O registro abaixo fica como histórico da v2.02. O teste atual é só o da parada diária (§11).

`WinMaestro_Teste.mq5` (v2.02) tem **137 verificações** (`Ok`) em **106 funções de teste** (109 chamadas: os cenários b, g e k rodam em duas variantes); a v2.01 tinha 130 em 99 e a v2.00, 106 em 81. Há uma ou mais por linha da tabela (P1–Z), por linha da intenção efetiva (I1–I5; I6 é o caminho de todos os outros), por regra de desfecho do §2.1, pela confiança (§2.2), pelo motor de corte (§5, inclusive a ordem dos passos), pela trava (§1.6), pela memória, pelo ambiente, pelos 14 cenários (a)–(n), 5 regressões das escolhas 31–38, 18 testes novos dos achados da revisão de código 1, 7 da revisão de código 2 (§10) e 22 verificações dos adaptadores dos 5 módulos.

- Cada teste liga o maestro sobre a corretora falsa pelo mesmo caminho do EA (`Mae_Reseta`, `Mae_Partida`, memória gravada e relida, 10 s de conexão) e roda `Mae_Ciclo`, que é o ciclo do EA real. O módulo é um stub que só escreve a intenção pedida pelo teste no `Tick` e registra os eventos.
- A falsa não decide nada: guarda ordens, deals, histórico e posição, e só falha quando o teste pede (recusa, timeout com ticket 0, deal ou histórico atrasado, posição atrasada, ordem fora da lista, `OrderModify` que troca o ticket, conexão, recusa por magic/tipo). As conclusões são conferidas no estado da falsa (ordens vivas, histórico, deals, posição) e no mapa.
- **Falsa da v2.01 (A-3):** (1) **execução por preço** (`m_por_preco`): `Move(bid, ask)` executa as pendentes atravessadas; no envio, stop do lado errado é recusado (`INVALID_PRICE`) e limite que cruza enche; `m_stop_falha` simula o stop atravessado que não executa; (2) **recusa assíncrona**: `FM_ACEITA_RECUSA` (um envio) ou `m_rej_magic/m_rej_tipo/m_rej_ms` (persistente): o envio volta PLACED e o histórico mostra REJECTED depois do atraso (pendente: some das vivas; a mercado: ordem REJECTED sem deal); (3) **K e M assíncronos** (`m_assinc_ms`): respondem DONE e o cancelamento/modificação só aparece depois do atraso; (4) **transações**: a falsa enfileira REQUEST (com o ticket real, inclusive no timeout de ticket 0), DEAL_ADD e HISTORY_ADD, e o teste as entrega ao `Mae_OnTradeTransaction` do maestro com `Entrega()`; (5) `FM_TK0_OCULTA`: timeout com ticket 0 e a ordem só aparece depois. Os efeitos assíncronos são aplicados na leitura seguinte do maestro (`Processa()` em `LeLiquida`/`LePendentes`/`LeHistorico`). A execução por preço vem desligada por padrão: os testes da v2.00 montam o mercado com `Precos()` e foram conferidos assim; os testes novos ligam o que precisam.
- O EA de teste não tem caminho para a corretora real: com `WINMAESTRO_TESTE` a classe `CCorretoraReal` não é compilada, os módulos não têm `CTrade`, painel e botão ficam desligados. Grava só em `MQL5\Files\WinMaestro_unit\` e em variáveis globais com o prefixo `WinMaestroTeste` (apagadas no fim de cada teste de trava).
- Os testes dos adaptadores chamam as funções dos módulos reais com uma vista montada pelo teste. O de entrada do C1 lê a cotação do gráfico: o EA de teste precisa estar num gráfico de símbolo com cotação.

## 6. O que não foi possível fazer

- **Executar os testes.** A instrução proíbe abrir o terminal e o Testador. As 137 verificações foram compiladas e rastreadas à mão contra o código (§9, §10), mas nunca rodaram; o primeiro uso é rodar o EA de teste num gráfico separado (LEIA-ME). A revisão de código 1 achou por leitura uma verificação da v2.00 que falharia (T_P1_ForaDaJanela); outras assim podem existir até a primeira execução.
- **B-15 (GB)**: o fim do contínuo do GB vem da grade B3 e não de 565 min + horário de verão dos EUA antes de 2024-03-11, e o `StopRegra` do GB usa o preço da ficha, sem o BE. A equivalência com o avulso nesses dias só se confere no Testador.
- **Testes dos módulos que leem o gráfico**: o de entrada do C1, o de stop atravessado do DM (B-10) e o de zeragem do DM (B-13, sessão do símbolo) dependem do gráfico em que o EA de teste roda (um gráfico do WIN com cotação).
- **Tamanho do núcleo.** Os sete arquivos do núcleo somam 3.046 linhas (o §10 do desenho estimava ~1.510); a diferença está em logs, comentários de rastreabilidade e nas proteções das escolhas 31–41. Nenhuma global de estado por robô fora das listadas em `Tipos.mqh`.
- **Equivalência com os EAs avulsos e com o replay T6** (spec 12) depende do Testador.
- **Perguntas à corretora** que o desenho deixa abertas: P1–P22 da spec e o `ChartID` no reinício do terminal. A implementação é segura para as duas respostas do `ChartID`; com token novo, até 60 s sem atividade depois de um reinício.
- **Módulos com dados de mercado nos testes**: `AvaliaSinal` (GB), `Tick` do CM, `Decidir` (DM), `ProcessarBarraFechada`/`AproximarAlvo` (RE) e `AtualizaPosicao`/`VerificaBreakEven` (C1) leem barras e indicadores do gráfico e não têm teste unitário; a lógica deles é a do WinSeletor, e a equivalência é medida no Testador.

## 7. Memória: a regra de saída de cada campo (v2.01, A-1)

A A-1 foi um campo persistido sem regra de saída. A varredura abaixo cobre todas as chaves que `Mae_Exporta` grava e o estado dos módulos.

| Campo (chave) | Para que serve | Regra de saída |
|---|---|---|
| `versao`, `servidor`, `conta`, `simbolo` | identidade da memória | reescritos a cada gravação; se não batem na carga, a memória inteira é ignorada (memória perdida). A versão vale 2.02 ou 2.01 (mesmo formato, v2.02) |
| `dia` (`mzMemDia`) | dia da memória | trocado no dia novo (`Mae_DiaNovo`) |
| `prox_linha` | id da próxima linha do mapa | contador só crescente (64 bits); ids únicos entre dias, não precisa voltar |
| `L.<id>` (linhas do mapa) | papel fixo, desfecho, envio | no dia novo (`Mapa_Retencao`): saem as de dias anteriores que não são do episódio aberto do robô; as do MAESTRO e sem episódio saem sempre |
| `R<r>.nivS`, `nivSInt`, `nivA`, `emerg`, `emergLado` | nível pedido, alvo, emergência gravada | zerados quando o episódio do robô fecha (`Est_FechaEpisodio`); o nível pedido muda quando o módulo pede outro |
| `R<r>.ep`, `R<r>.epAb` | episódio | `ep` só cresce; `epAb` fecha com ficha 0 provada e nada vivo/pendente do robô, ou no corte com a líquida 0 (`Est_Episodios`) |
| `R<r>.ultId` | último `id_entrada` do robô | só cresce (ids crescentes, ≥ instante em ms) |
| `R<r>.ultCorr` | instante da última correção | só é comparado dentro de 10 min (`Est_Correcoes`): perde efeito sozinho; sobrescrito na próxima correção |
| `seq<d>`, `seqDia` | sequência do comentário da ordem | zerados no primeiro envio de um dia novo (`Env_ProxSeq`) |
| `cons` (ids consumidos) | nenhuma E com id já usado | zerado no dia novo (`Mae_DiaNovo`); no máximo 200 (os mais antigos saem) |
| `bloq`, `bloqMotivo` | bloqueio de entradas com botão | só o botão (`Mae_Desbloqueia`); atravessa o dia de propósito (o dono precisa olhar) |
| `reconh` | tickets reconhecidos pelo botão | lista circular de 500 (o mais antigo sai); só vale para deals ainda na janela |
| `extDesc` | externa de origem desconhecida | **nova regra (A-1):** zera no dia novo (`Mae_DiaNovo`) e quando `liquida` = 0 e os deals da janela somam 0 por 30 s seguidos com histórico lido (`Est_Deriva`); escolha 42 |
| `absVistas`, `dealsLog` | efeitos colaterais uma vez por ticket | listas circulares de 500 |
| `janRecuo`, `janRecuoDia` | recuo da janela | só valem no próprio dia (`mzJanRecuoDia` = hoje); zerados no dia novo |
| chaves dos módulos (`GB.*` … `C1.*`) | estado dos módulos | só são lidas no mesmo dia (`Car_*` com `mzCarMesmoDia`); a cada gravação o módulo iniciado reescreve todas (`Exporta`), o não iniciado copia as lidas |
| RE `RE.anel*`, `RE.fill_*` (v2.01) | entradas anteriores e fill pendente | o anel é sobrescrito circularmente a cada `ArmarEntrada`; o fill pendente sai ao ser adotado ou no primeiro `Tick` sem a posição |
| CM `CM.ped_*` (v2.01) | "a favor do mês" por entrada pedida | sobrescritos a cada `Entra`; zerados no `Reseta` |

RAM com prazo, para conferência: `mzExtZeroDesde` (novo), `mzDeltaDesde`, `mzSFaltaDesde`, `mzRestritoDesde`, `mzInvalidoDesde`, `mzEspera` e os relógios de `PRAZO_ENTRAR`/`PRAZO_SAIR` voltam a 0 no `Mae_Reseta`; os quatro primeiros também em INVALIDO (`Mae_Invalido`) ou quando a condição deixa de valer.

## 8. Revisão de código 1 (v2.01): achado → correção → teste

| ID | Correção (arquivo: função) | Teste |
|---|---|---|
| A-1 | regra de saída de `externa_desconhecida`: `Estado.mqh: Est_Deriva` (líquida e deals em 0 por 30 s), `Partida.mqh: Mae_DiaNovo` (dia novo), relógio zerado em `Mae_Invalido`; tabela do §7 | T_A1_ExtDescDia, T_A1_ExtDescZera |
| A-2 | `Mapa.mqh: Rec_Registra` (caminho único: retcode em `Env_Executa`, REJECTED no histórico e ausência em `Mapa_DesfechoOrdem`), `Rec_Aceita` (escolha 43) | T_A2_RecusaAssinc; T_C_AusenciaTk0, T_C_Sumida, T_Cen_b(false) ajustados à espera da ausência |
| A-3 | T_P1_ForaDaJanela corrigido (o deal das 08:50:11 dentro da janela); falsa com execução por preço, recusa assíncrona, K/M assíncronos e transações (§5); a ordem do corte conferida; T_Cen_k reescrito | T_P1_ForaDaJanela, T_K_Conta, T_K_Recusa, T_K_SVivas, T_Cen_k, T_KM_Assinc, T_Trans, T_C_RequestId, T_Preco_Corrida, T_X3_SCruzada |
| M-1 | `Estado.mqh: Est_Confianca` (estável pelo valor); §11 do desenho | T_M1_DeltaEstavel; T_C_DealVence ajustado |
| M-2 | `Estado.mqh: Est_Entrega` (converte só o ENTRAR do mesmo id; senão MANTER(0, 0)) | T_M2_EntregaId |
| M-3 | `Decide.mqh: Dec_Tabela` P3 (a restrição da escolha 10 só com f ≠ 0) e L3 (poupa a S da entrada pedida só se válida) | T_M3_RearmeMesmoLado |
| M-4 | `Corretora.mqh: Mono()`; `mzMono` em todos os prazos; `enviado_mono`/`sumida_mono`; `Partida.mqh: Mae_MonoDe` na carga; ALERTA de relógio em `Snap_Le` | T_M4_Relogio |
| M-5 | `Decide.mqh: Dec_Tabela` X3 (K da S cruzada viva há `PROVA`); §11 do desenho | T_X3_SCruzada |
| M-6 | RE: anel de 4 entradas (`g_anel_*`, `AdotaNiveis`), fill pendente (`g_fill_*`) adotado no `Tick`, persistidos | T_Mod_RE |
| M-7 | CM: `g_ped_id/g_ped_favor` (+ anterior) gravados no `Entra`, aplicados no `Evento(ENTRADA_EXECUTADA)` pelo id | T_Mod_CM |
| M-8 | testes reescritos (§9) | §9 |
| B-1 | `Mapa_DesfechoOrdem`: ticket 0 `NAO_EXECUTADA` casada de novo (setup até envio + `PROVA`) | T_B1_CasaTardia |
| B-2 | `Env_Executa`: `!ok && retcode == 0` = recusa | T_B2_Retcode0 |
| B-3 | `Dec_NivelS`: `cand[2]` = primeira S viva **válida** | T_B3_SValida |
| B-4 | `Est_Recuo`: recua só com Δ estável, com ou sem memória | T_B4_RecuoEstavel |
| B-5 | `Snap_Indexa`/`Snap_Busca`: índices ordenados por ticket e busca binária para deal e ordem do histórico | todos os testes que leem deals (sem teste próprio: é desempenho) |
| B-6 | risco residual aceito pelo desenho (S × `C_CONTA`), registrado no LEIA-ME | — (corrida do desenho) |
| B-7 | `Dec_Tabela` L4: o log distingue "segunda E/A viva do robô (excedente)" de "limite do robô fora do mapa" | — (texto de log) |
| B-8 | `Mapa_Casa`: classes de preferência (escolha 47) | T_B8_PrefereViva |
| B-9 | `Mae_Invalido` zera `mzSFaltaDesde` | T_B9_SFaltaInvalido |
| B-10 | DM `StopAtravessado` a cada `Tick` | T_Mod_DM |
| B-11 | DM sai com `last <= g_stopNivel + piso` (o piso da corretora, spec 5.3): registrado no LEIA-ME | — (documentação) |
| B-12 | `DM_RiscoMaxPct` sobre R$1.000 fixos (B9): registrado no LEIA-ME para ciência do dono | — (documentação) |
| B-13 | DM `MinutoZerarRobo` pela `FimSessao` do módulo (sessão do símbolo; sem ela, os inputs) | T_Mod_DM, T_Mod_Zeragem |
| B-14 | GB `DECISAO PERDIDA` entre 09:05 e `g_exp` (desenho §6): registrado no LEIA-ME | — (documentação) |
| B-15 | fim do contínuo do GB pela grade; `StopRegra` do GB sem o BE: pendente de conferência no Testador (§6) | — (Testador) |
| B-16 | CM e RE: os `static` viraram globais do módulo e voltam no `Reseta`; o CM usa o piso da corretora (≥ 1 tick) onde o original usava o tick, como a S de toda a v2 | T_Mod_CM (cache) |
| B-17 | RE: sem posição no `Tick`, o estado do alvo volta ao inicial; `g_barra_do_fill` = vela de `e.hora`; no `Importa`, `g_barras_esperando` é recontado de `g_vela_entrada` (as velas com o EA fora contam para o TTL, como contariam no avulso que nunca reinicia) | T_Mod_RE |
| B-18 | C1: stop validado contra o preço da decisão (escolha 33): registrado no LEIA-ME | — (documentação) |
| B-19 | `Ficha_DecisaoPerdida`: atraso > 120 s | T_B19_DecisaoAtrasada |
| B-20 | o botão grava Δ só estável e retira linhas sem desfecho há 10 min (decisão C): registrado no LEIA-ME | — (aceito pela decisão C) |

## 9. Testes reescritos (M-8) e por que cada um agora falha sem a linha que cobre

Conferência feita à mão, removendo mentalmente a guarda ou a linha e seguindo o ciclo sobre a falsa.

| Teste | O que mudou | Sem a linha/guarda, falha em |
|---|---|---|
| T_P1_ForaDaJanela | começa às 08:50 (deal dentro da janela) | sem a janela de ordens, a S sai antes das 08:55 (`nada` falso) |
| T_P1_SemHistorico | a S nova é recusada (nada pendente, `em_espera` vencida) antes de o histórico falhar | sem `okR` no P1, a S sai depois dos 5 s (`parado` falso) |
| T_X3_SCruzada | execução por preço com o stop que não executa; espera e depois o prazo da M-5 | sem a guarda de S cruzada, a X sai em 0,25 s; sem a M-5, nunca sai |
| T_L3_Restrito | + a prova "E CANCELED sem deal" | sem o ramo `eCanc` de `Dec_ProvaL3`, a S do CM fica |
| T_E1_Consumido | + controle: id novo entra | um núcleo que nunca envia falha no controle |
| T_Z | + controle: o A pedido sai no mesmo estado | idem |
| T_I1 | zeragem do robô depois do corte; confere a origem I1 na linha da X | sem I1, a X sai com motivo I3 |
| T_I4 | 2ª metade: desbloqueio → a entrada sai | um núcleo que nunca envia, ou que não sai do bloqueio |
| T_I5 | + controle: outro robô entra | um núcleo que nunca envia |
| T_PrazoEntrar | exige 2 ou 3 tentativas recusadas da S | um núcleo que nunca envia |
| T_C_RequestId | a transação REQUEST é entregue ao `Mae_OnTradeTransaction`; P2 cancela a duplicada fora do mapa | sem o `Snap_RequestVisto` no `OnTradeTransaction`, a linha segue ambígua |
| T_C_DealVence | conferência da M-1: absorção virtual, S viva, nenhuma 2ª X | sem `!abs_virtual` em L3, a S sai; sem a absorção virtual, a 2ª X sai |
| T_DeltaVirtual | RE com A: S **e A** ficam durante a absorção virtual | sem `!abs_virtual` em L2, o A é cancelado (I4 dá NADA) |
| T_K_Conta | `DoneHist(ec) < deal < DoneHist(sg), DoneHist(sc)` | passo 3 antes do 2, ou passo 1 depois |
| T_K_Recusa | S viva em t1, t2 e t3; cancelada depois do deal | passo 3 antes do 2 |
| T_K_SVivas (novo) | S viva a cada segundo com o `C_CONTA` sem desfecho | passo 3 antes do 2; `MercadoRecente` removido (2º `C_CONTA` cedo) |
| T_M_Reinicio, T_M_MapaDoLog | + controle: o MANTER novo move a S | um núcleo que nunca envia |
| T_M_NaoGrava | a memória falha exatamente no registro da E (decidida com a memória gravando) | sem a barreira de `Env_Executa` para E/A, a E sai; sem `Est_DesConsome`, o id fica consumido |
| T_Amb_Hedging | + controle NETTING | um núcleo que nunca envia |
| T_Amb_Parado | o ambiente volta → a entrada sai | idem; e `mzParado` grudento |
| T_Cen_g(true) | confere o K RECUSADA e a `em_espera[DM][K]` | documenta o atraso de 5 s que a revisão apontou |
| T_Cen_k | SAIR já está na intenção quando a S executa; com `filled` só o `confiavel` segura a X3 (nada pendente que reduza) e só o lado inequívoco segura o P1 | sem `conf` na X3, sai uma 2ª saída; sem `okR` no P1, sai uma S |
| PRAZO_SAIR × INVALIDO (em T_Revisao_Regressoes) | exige X tentadas | um núcleo que nunca envia |

Testes novos da v2.01: T_A1_ExtDescDia, T_A1_ExtDescZera, T_A2_RecusaAssinc, T_K_SVivas, T_KM_Assinc (sem `Mapa_KPend`/`Mapa_MPend`, K e M se repetem), T_Trans (sem o `Mae_Ciclo` no `OnTradeTransaction`, o fill não vira evento; com transação de outro símbolo, nada roda), T_Preco_Corrida, T_M1_DeltaEstavel, T_M2_EntregaId, T_M3_RearmeMesmoLado, T_M4_Relogio, T_B1_CasaTardia, T_B2_Retcode0, T_B3_SValida, T_B4_RecuoEstavel, T_B8_PrefereViva, T_B9_SFaltaInvalido, T_B19_DecisaoAtrasada; e nos adaptadores: RE (anel, fill pendente, alvo sem posição), CM (M-7, cache), DM (B-10, B-13).

## 10. Revisão de código 2 (v2.02): achado → correção → teste

Cada teste novo foi seguido à mão ciclo a ciclo sobre a falsa, com e sem a correção (o código sem ela está em `mt5/WinMaestro_v2.01_historico/`). A última coluna diz onde ele falha sem a correção.

| ID | Correção (arquivo: função) | Teste | Sem a correção, falha em |
|---|---|---|---|
| B2-1 | `Mapa.mqh: Rec_Registra` sem o parâmetro `conta`: a prova por ausência (ticket 0 e com ticket) entra na contagem; espera de 5 s mantida | T_B2_1_AusenciaConta | `n1` = 0 depois da 1ª ausência e nenhum ALERTA (`mzRecusaAlerta` = 0) depois da 5ª |
| B2-2 | `Decide.mqh: Dec_SCruzRelogio` (relógio da S cruzada em todo ciclo, com qualquer intenção), chamado em `Partida.mqh: Mae_CicloUm` antes do passo 4; o bloco X3 só lê o relógio | T_B2_2_SCruzRelogio | o K sai no 1º ciclo do 2º SAIR, com o relógio de 42 s de um cruzamento anterior que já tinha terminado: `espera` falso |
| B2-3 | `Decide.mqh: Dec_NivelS`: emergência gravada atravessada com ficha aberta → primeiro nível válido além da referência (escolha 51); com ficha 0, sem S como antes | T_B2_3_EmergCruzada | depois do K da S cruzada nenhuma S nova sai (`s2` = 0) enquanto a X é recusada |
| B2-4 | `Estado.mqh: Est_RoboDoDelta` (atribuição, escolha 52), `Est_Absorve`, `Est_Externo(v, virtual, prior)`; chamada em `Est_Deriva`; regra no §11 do desenho | T_B2_4_AbsorveDono | a ficha do GB (primeira na ordem fixa) é absorvida no lugar da do CM, e o CM manda uma 2ª X aos 35 s |
| B2-5 | `Estado.mqh: Est_EventosLinhas`: E NAO_EXECUTADA com `estado_hist` = REJECTED → `ENTRADA_RECUSADA` | T_B2_5_ERecusadaAssinc | o módulo recebe `ENTRADA_CANCELADA` |
| B2-6 | `Mapa.mqh: Mapa_PortaoRecasa` e a guarda `mzOrdemSemLinha[dono]` no recasamento de `Mapa_DesfechoOrdem` (escolha 53) | T_B2_6_PortaoRecasa | `Mapa_Casa` roda a cada ciclo (8 chamadas em 2 s) sem nenhuma ordem fora do mapa |
| B2-7 | `Corretora.mqh`: o comentário de `Mono()` diz só o que ela é; o de `AgoraMsc()` foi para a linha dela | — (comentário) | — |
| B2-8 | T_X3_SCruzada procura a linha K com motivo `X3` (helper `LinhaMot(r, papel, motivo)` no teste) | T_X3_SCruzada | a verificação pegava a última K, que é a de L3 do mesmo ciclo |
| versão | `WM_VERSAO` 2.02; `Partida.mqh: Mae_CarregaMemoria` lê também a memória da 2.01 (escolha 54) | T_M_Versao201 | com a versão nova e sem a compatibilidade, a memória da 2.01 vira memória perdida |

**Testes cuja expectativa mudou:** só **T_X3_SCruzada**. Ela buscava `Linha(R_GB, P_K)`, a última linha K do GB, e exigia motivo `X3`. No ciclo em que o prazo vence, as 4 rodadas mandam o K da S cruzada (X3), a S nova, a X e o K da S nova (L3, porque a ficha zerou); a última K é a de L3. A verificação passou a procurar a linha K com motivo `X3`. O código estava certo; as outras condições do teste não mudaram.

**Suíte antiga contra as mudanças**, seguida à mão:
- B2-1 só muda `mzRecusaN`/`mzRecusaAlerta`, que nenhuma decisão lê. Os testes que leem a contagem usam `>=` (T_Cen_l `>= 5`, T_A2_RecusaAssinc `>= 4`) e não têm ausência no caminho.
- B2-2: as S cruzadas com ficha aberta da suíte antiga são as de T_X3_SCruzada (o relógio liga no mesmo ciclo do SAIR, como antes: K aos 30,25 s) e a S fora do mapa de T_B3_SValida (intenção MANTER, a X3 não age). Nos outros testes que mexem no preço (T_Nivel_Emergencia, T_Nivel_Referencia, T_Cen_d, T_Preco_Corrida) nenhuma S fica cruzada com ficha aberta.
- B2-3 só age em P1 com ficha aberta e emergência gravada atravessada; em P3 com ficha aberta, havendo S válida, a cadeia para na S viva antes de chegar à emergência. Nenhum teste antigo atravessa uma emergência gravada.
- B2-4: com uma linha candidata só do único robô que o Δ pode reduzir (T_C_DealVence: a X do GB) ou sem candidata (T_DeltaVirtual: o RE é o único comprado), o resultado é o da ordem fixa. Os outros testes com Δ estável têm Δ que aumenta a líquida (externa, sem absorção) ou fichas todas em 0.
- B2-5: nenhum teste antigo tem E recusada de forma assíncrona (`FM_ACEITA_RECUSA` e `m_rej_*` só aparecem com S, em T_A2_RecusaAssinc).
- B2-6: com o portão fechado, toda ordem do magic do dono já está no mapa e `Mapa_Casa` não acharia candidata (`Mapa_TicketUsado`); as linhas de ticket 0 da suíte antiga têm `request_id` 0. T_B1_CasaTardia abre o portão no ciclo em que a E aparece e casa como antes.
- Versão: todos os testes gravam e leem a memória da própria versão.

## 11. Parada diária (v2.03, 2026-10-08)

**Pedido do dono.** Capital fixo em input (`Risco_Capital`, padrão 1000); quando o resultado líquido do dia dos robôs chega a −`Risco_PerdaDiaPct`% dele (padrão 10; 0 desliga), só bloqueia entradas novas até o pregão seguinte; posições abertas seguem; ganhos compensam perdas. O limite de risco aberto por stop, pedido no mesmo dia, foi retirado pelo dono antes da entrega e não tem código.

**Como entra no desenho.** Nenhum módulo muda e a tabela (§4.2) não ganha linha: a parada é mais uma causa do bloqueio de entradas que já existia.

| Onde | O quê |
|---|---|
| `Estado.mqh: Est_Fichas` | além das fichas, o realizado de hoje por robô (`eResR`) e os eventos do dia em ordem (`eResEv`, **um por deal**: a soma do que o deal realizou em todas as fichas, `Risco_FechaDeal`). `Est_Aplica` (deal do robô, `Risco_Aplica`), `Est_Externo` (regra 7.1 inteira, `Risco_Externo`: absorção real ao preço do deal externo) e o encerramento pelo `C_CONTA` (`Risco_Encerra`, ao preço dele) acumulam o realizado do deal em `eRzDeal`; custo do deal do robô = `comissao + taxa + swap`; o par AJUSTE (P14) é reconhecido por `Risco_ParAjuste` |
| `Partida.mqh: Mae_CicloUm` | `Risco_Dia()` no passo 3, depois de `Est_Prazos`, com o mesmo snapshot |
| `Risco.mqh: Risco_Dia` | total e pior acumulado sobre `eResEv`; liga `mzBloqDia` e a **trava no dia** (`mzBloqDiaDia`); log `RISCO` na transição (com o resultado por robô; ao desligar, o motivo) |
| `RiscoRegra.mqh` | `Risco_Aplica` (ficha, preço médio e realizado de um deal; a única conta de preço médio do maestro), `Risco_Externo` (regra 7.1 sobre as fichas e a externa, real ou virtual), `Risco_Encerra` (`C_CONTA`), `Risco_FechaDeal` (só deal de hoje entra; um evento por deal), `Risco_ParAjuste` (par P14), `Risco_Acumula` (total e pior acumulado) e `Risco_ParadaDe` (pior ≤ −limite, com folga de 1e-6 só para o erro de ponto flutuante) |
| `Corretora.mqh` | `SDealInfo.swap` (`DEAL_SWAP`) |
| `Estado.mqh: Mae_Bloqueio` | `mzBloqBotao \|\| mzBloqAuto \|\| mzBloqDia`. Daí em diante é o caminho do bloqueio que já existia: I4 dá intenção NADA com ficha 0 (L1 cancela a E viva, o módulo recebe `ENTRADA_CANCELADA`) e `pode_entrar` barra E1. S, X, A, zeragem, correção e corte não olham o bloqueio |
| `Partida.mqh: Mae_Painel` | linha nova: resultado do dia (R$ e %), por robô, o valor do ponto usado e a situação da parada; no campo do bloqueio, `parada diaria (perda do dia)`, ou `<motivo do botão> + parada diaria` quando os dois valem |
| `WinMaestro.mq5: OnInit` | linha `RISCO` com a configuração e o valor do ponto (`TICK_VALUE`/`TICK_SIZE`; esperado R$0,20 no WIN) |

**Escolhas.**

1. **Pelo pior acumulado, não pelo resultado atual.** "Chega a −10%" é um instante; depois dele a parada vale até o pregão seguinte, mesmo que um ganho traga o resultado de volta (por exemplo, um stop de −R$210 seguido de dois ganhos de +R$60 e +R$50: total −R$100, mas a parada já ligou no −R$210). Cada deal é um evento só: um deal que realiza várias fichas (absorção de duas fichas, `C_CONTA` com fichas de lados opostos) entra com a soma, porque a conta nunca esteve no estado intermediário (por exemplo, GB −R$100 e CM +R$100 no mesmo `C_CONTA` é R$0, não um −R$100 que ligaria a parada).
2. **Liga pelo histórico, fica pela RAM; sem memória e sem botão.** O resultado é refeito a cada ciclo dos deals de hoje, e é isso que liga a parada (também depois de reinício e no Testador). Uma vez ligada, ela fica **travada em RAM** até o dia mudar (`mzBloqDiaDia` = `Mae_Dia(mzAgora)` do momento em que ligou): a re-derivação do histórico no meio do pregão pode mudar sem a conta ter mudado (o botão grava uma diferença externa e `Est_Externo` reinterpreta uma absorção; `Est_Recuo` muda a janela e o preço médio; a externa de origem desconhecida cai e `Est_Fichas` roda de novo; `HistorySelect` incompleto) e nada disso desfaz a parada. Ela só desliga no dia novo (log `parada diaria DESLIGADA (pregao novo AAAA.MM.DD)`). Ressalva: um reinício do EA (inclusive por mudança de input) limpa a RAM e a parada é re-derivada do histórico; se nesse momento o histórico não mostrar mais a perda, ela não volta. `Risco_PerdaDiaPct` = 0 no meio do dia é a saída de emergência do dono (reinicia o EA, desliga a parada). Nada novo é gravado em `estado.txt`; a memória da 2.02 e da 2.01 continua lida (`WM_VERSAO_MEM_COMPAT`, `WM_VERSAO_MEM_COMPAT2`). **Volta para a 2.02:** a 2.02 não aceita a memória com `versao=2.03` e parte sem ela (mapa das ordens, níveis, bloqueio e reconhecidos perdidos); voltar só com a conta zerada e sem ordens dos robôs.
3. **"Hoje" é a data do servidor** (`Mae_Dia(mzAgora)`), a mesma que separa os dias em todo o resto do maestro. A janela do histórico sempre começa antes da abertura de hoje (`Snap_JanelaInicio`), então todos os deals do dia estão no snapshot.
4. **Resultado por robô, como se cada robô tivesse conta própria — nunca o `DEAL_PROFIT`.** Em NETTING o `DEAL_PROFIT` é o da posição líquida que o deal reduziu. Caso real de 2026-10-08 na demo: líquida −3 por vendas manuais @204.591,67; a entrada do CM (compra 1 @207.310, magic 80080501) recebeu `DEAL_PROFIT` −543,67, o prejuízo da venda manual. Somar o `DEAL_PROFIT` dos deals de robô ligaria a parada (capital 1000) sem o robô ter perdido nada; com dois robôs em lados opostos o deal de um carrega o resultado do outro. Por isso o realizado sai da ficha: preço médio, e cada redução realiza (preço do deal − preço médio) × lado × contratos × valor do ponto. O valor do ponto é `SYMBOL_TRADE_TICK_VALUE / SYMBOL_TRADE_TICK_SIZE` (lido a cada cálculo; o ambiente já exige os dois > 0), não R$0,20 fixo.
5. **Uma conta de preço médio só.** `Est_Aplica` passou a chamar `Risco_Aplica`, que faz a mesma conta de ficha e preço médio que ele fazia (abre/inverte → preço do deal; aumenta → ponderado; reduz → mantém; zera → 0) e devolve o realizado; a regra 7.1 de `Est_Externo` passou para `Risco_Externo`, que usa a mesma conta. O resultado sai no mesmo passeio pelos deals que faz as fichas, então herda tudo o que a ficha já trata: ordem dos deals, classificação, deals de pregões anteriores na janela (o preço de entrada da ficha da noite vem de lá; `Risco_FechaDeal` só deixa entrar o realizado de deal de hoje), recálculo quando a externa gravada cai.
6. **Saídas que não são deal do robô.** (a) Absorção real de zeragem manual (spec 7.1): a spec já diz que a ficha absorvida vai a 0 "com o preço do deal externo"; isso é uma saída da ficha a esse preço e realiza (o robô perdeu ou ganhou até ali). (b) `C_CONTA` do corte: o encerramento zera todas as fichas; cada uma realiza ao preço do deal do `C_CONTA`, porque o objetivo é quanto os robôs ganharam ou perderam hoje e a posição deles fechou ali (fichas de lados opostos se compensam internamente a qualquer preço, então o mesmo preço para todas dá a soma certa). O `C_CONTA` só sai a partir de C + 2 min, sem entradas, então isso muda o número do fim do dia, não uma decisão. `C_CONTA` executado em vários deals: o primeiro já zera as fichas e todas saem ao preço dele (é como o encerramento já funcionava). (c) Os custos do deal externo e do `C_CONTA` não são de robô nenhum e não entram; deal externo que não absorve ficha não entra. (d) Absorção virtual (Delta sem deal, spec 2.2) não tem preço: não realiza nada; ela já bloqueia entradas pelo `mzAbsVirtual`. (e) Deal com magic de robô não classificado fica fora da ficha: entra só o custo dele (o robô fica não provado e não entra de qualquer forma).
7. **Sem histórico lido** fica o último cálculo e a trava do dia vale. Nesse estado nenhum robô é confiável, então nenhuma entrada sai de qualquer forma.
8. **Fronteira:** exatamente −10% liga (≤), pedido do dono.

**Teste.** `mt5/testes/WinMaestro_TesteParada.mq5` (script, só inclui `RiscoRegra.mqh`), 37 verificações. O replay chama, deal a deal, as **mesmas funções** que `Est_Fichas` chama (`Risco_Aplica` para deal de robô, `Risco_Externo` para deal externo e absorção virtual, `Risco_Encerra` para o `C_CONTA`, `Risco_FechaDeal` ao fim de cada deal, `Risco_ParAjuste` para o par P14); fica fora só a classificação do deal (cada deal do teste já vem com a classe). Regra da parada (11): exatamente −10% liga; −9,99% não liga; dois ganhos e um stop grande com total −9% (não liga), −10% (liga) e −12% (liga); stop antes dos ganhos (liga e fica); três perdas somando exatamente −R$100 em ponto flutuante (liga); capital R$7.000 com −R$700 (liga) e −R$699,30 (não liga); input 0 (desligada); dia sem deals (desfeita). Resultado por robô (26): o caso real de 08/10 (o manual −3 vira externa sem tocar ficha; a entrada do CM dá CM R$0, não −543,67; a saída 110 pts abaixo com R$1 de custo dá −R$23); GB e CM em lados opostos (GB R$0 ao abrir; CM +R$40, GB +R$10, dia +R$50 = a soma da conta); inversão; ficha de ontem fechada hoje (−R$100,50 hoje liga); preço médio ponderado; zeragem manual absorvida (−R$100, liga); `C_CONTA` (DM +R$10, dia +R$30); pior acumulado com dois robôs (−R$120 antes de +R$50: liga); **`C_CONTA` com fichas de lados opostos** (GB −R$100 e CM +R$100 no mesmo deal: um evento de R$0, não liga); **absorção de duas fichas num deal** (idem); **absorção parcial** (CM absorve 1 de −3, −R$100; a sobra −2 vira externa); **deal não classificado de robô** (ficha intacta, só o custo); **absorção virtual** (a ficha zera, nada realizado, nenhum evento); **virada do dia** (−R$100 de 23:59 de ontem fora, −R$50 de 00:00 de hoje dentro); **par AJUSTE** (a ficha do CM fica intacta, nada realizado; a 1,5 s ou com volume diferente não é par). A trava em RAM (escolha 2) não está no script: depende do relógio e das globais do EA. Compilado, 0 erros e 0 avisos; não executado (o terminal não foi aberto). Para rodar: copiar para `MQL5\Experts\testes\` com a pasta `WinMaestro\` da v2.03 ao lado.

**O que só se confere no terminal.** O caminho inteiro (bloqueio → I4 → L1 cancela a E viva → `ENTRADA_CANCELADA`) é o do bloqueio que já existia, sem código novo. O que é novo e só se vê rodando: o `DEAL_COMMISSION`/`DEAL_FEE`/`DEAL_SWAP` que a Rico preenche nos deals do WIN (se a corretagem vier fora do deal, ela não entra no resultado), o valor do ponto da Rico (`TICK_VALUE`/`TICK_SIZE`; esperado R$0,20) e a linha do painel. Conferência recomendada no primeiro pregão: o resultado por robô do painel contra o extrato, operação a operação, num dia com robôs em lados opostos ou com posição manual.
