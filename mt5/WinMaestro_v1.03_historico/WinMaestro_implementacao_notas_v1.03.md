# WinMaestro v1.03: notas de implementação

Implementação da `WinMaestro_ESPECIFICACAO.md` (versão 1.0), com os 30 achados de `WinMaestro_revisao_codigo_1.md` (seção 3) e os 21 de `WinMaestro_revisao_codigo_2.md` mais os 3 parciais (seção 4) tratados. Compilação no MetaEditor da Rico: `WinMaestro.mq5` 0 erros, 0 avisos; `WinMaestro_Teste.mq5` 0 erros, 0 avisos. 87 testes unitários com a corretora falsa, que exercitam o código do maestro e os adaptadores dos módulos DM e RE.

## 1. Especificação → código

`F` = `WinMaestro/Fichas.mqh`, `R` = `WinMaestro/Recupera.mqh`, `EA` = `WinMaestro.mq5`.

| Seção | Onde |
|---|---|
| §0 princípios: ficha por robô, magic do robô | `F:Ficha_Calcula`, `F:Mae_Envia` (`req.magic = mzMagic[r]`) |
| §0 P4 toda entrada nasce com a S | `F:Mae_Entra` (S antes da E, em todos os robôs) |
| §0 P5 saída nunca tira o stop | `F:Mae_Saida` (A cancelado antes; S só depois do deal da saída) |
| §0 P7 SL/TP do dono nunca removido | nenhum código usa `TRADE_ACTION_SLTP`; SL/TP da líquida nunca é lido nem escrito |
| §1 porta única | `WinMaestro/Corretora.mqh:CCorretora`/`CCorretoraReal`; falsa em `WinMaestro/CorretoraFalsa.mqh` |
| §1 magics (constantes), inputs, liga/desliga | `F:mzMagic`; `EA` (inputs; `OnInit` preenche `mzAtivo`) |
| §1 grade embutida | `WinMaestro/Grade.mqh:Grade_Le`, `Grade_VencimentoDoSimbolo` |
| §1 constantes | `F` (`#define CM_RESERVA_PTS` … `MARGEM_CORTE`) |
| §1 `OnInit` reinicializa tudo (P17) | `EA:OnInit` → `F:Fichas_Reseta`, `Reseta()` de cada módulo |
| §2 papéis, validade, preenchimento | `F:Ficha_EntraLimite`, `Ficha_EntraMercado`, `Mae_EnviaS`, `Ficha_DefineAlvo`, `Mae_Saida`; `R:Recupera_Ambiente` (mercado RETURN/IOC) |
| §2 comentário `MAE|robo|papel|seq` | `F:Mae_Envia`, `F:Mae_ProxSeq`, `F:Mae_LeComent`, `R:Rec_SeqHistorico` |
| §2 uma operação por vez (`SEGUNDA_ENTRADA`) | `F:Mae_PodeEntrar` |
| §2 invariantes e órfãs | `F:Mae_Estado`, `F:Mae_Fase1` |
| §3.1 cálculo da ficha | `F:Ficha_Calcula`, `F:Ficha_Aplica`, `F:Mae_Mescla` (atribuição do deal) |
| §3.2 janela e verificação cruzada | `F:Mae_ReleituraCompleta`, `F:Leitura_Atualiza` |
| §3.3 interface com os módulos | `F:Ficha_Tem/Lado/Preco/Hora/Stop/Id`, `Ficha_Fecha`, `Ficha_DefineStop`, `Ficha_EntraMercado`, `Ficha_EntraLimite`, `Ficha_DefineAlvo`, `Ficha_Cancela`, `Ficha_Entrada`, `Ficha_TemAlvo`; eventos `EA:Robo_Evento` |
| §4.1 registro de trânsito | `F:Mae_Envia` (registro e memória antes do `OrderSend`) |
| §4.2 ordem de processamento | `F:Mae_Reconcilia` (fase 1 de todos, depois fase 2, ordem GB…C1) |
| §4.3 verificação D1 | `F:Mae_EstadoFecha`, `F:Mae_PodeEntrar`, `F:Mae_LeituraConfiavel`, `F:Mae_Autoneg` |
| §4.4 desfecho | `F:Mae_Prova`, `F:Transito_Resolve`, `EA:OnTradeTransaction` → `F:Mae_RequestVisto` |
| §4.5 retentativas | `F:Mae_Recusa` (timer próprio da proteção) |
| §5.1 cancelamento confirmado | `F:Mae_Cancela`, `F:Ficha_Cancela`, `F:Mae_EControle`, `F:Mae_Fase1` (cancelamento refeito) |
| §5.2 saída a mercado | `F:Mae_Saida` |
| §5.3 S: criar, mover, recriar | `F:Mae_Entra`, `F:Mae_EnviaS`, `F:Ficha_DefineStop`, `F:Mae_Modifica`, `F:Mae_Fase2`, `F:Mae_NivelStopFicha`, `F:Mae_NivelAtravessado` |
| §5.4 OCO | `F:Mae_Fase1` (irmã mais velha que o deal que zerou a ficha: cancelada na hora) |
| §6 reconciliação | `F:Mae_Reconcilia`; `EA:OnTimer` (1 s), `EA:OnTradeTransaction` (cada deal) |
| §7.1 externa e absorção | `F:Ficha_Calcula` (bloco externo, ajuste noturno), `F:Mae_NovosEventos` |
| §7.2 bloqueio e botão | `F:Mae_Bloqueia`, `F:Mae_Desbloqueia`, `F:Mae_BotaoClique`, `EA:OnChartEvent` |
| §8 trocada e duplicada | `F:Mae_Fase1` (correção por episódio), `F:Mae_Fase2` (S cobrindo \|ficha\|) |
| §9.1 relógio, grade, corte | `F:Mae_Horarios`, `Mae_JanelaTick`, `Mae_Continuo`, `Mae_JanelaOrdens` |
| §9.2 zeragem por robô | `F:Mae_Zr`, `EA:Robo_MinutoZerar`, `F:Mae_Fase1` |
| §9.3 corte e ficha da noite | `F:Mae_Fase1`, `F:Mae_Fase2`, `F:Mae_Corte`, `F:Mae_Noite`; corte com a cruzada aberta: `F:Mae_CorteConta` |
| §10.1 memória | `WinMaestro/Memoria.mqh` (`Mem_Grava`, `Mem_Carrega`, checksum FNV-1a, arquivo Unicode); `F:Mae_Exporta`, `F:Mae_Importa`, `F:Mae_GravaMemoria`; módulos `Exporta/Importa` |
| §10.2 partida | `R:Recupera_Passo` (passos 1–11), `R:Recupera_LogOrdens`, `R:Rec_SeqHistorico`, `R:Recupera_LogPronto` |
| §10.3 trava | `R:Trava_Toma`, `Trava_Heartbeat`, `Trava_Confere`, `Trava_Libera`; `EA:OnTimer` |
| §10.4 `OnDeinit` | `EA:OnDeinit` |
| §11 logs, painel, resumo | `WinMaestro/Log.mqh` (`Log`, `Log_Trans`, `Log_Cond`, `Log_CondEncerraPrefixo`); `R:Mae_Painel`; `F:Mae_Resumo` |
| §12 testes unitários (O15) | `WinMaestro_Teste.mq5` + `CorretoraFalsa.mqh` |
| Apêndice A | `WinMaestro/WinGapBarra1.mqh`, `WinCincoMedias.mqh`, `WinDeslocamentoMatinal.mqh`, `WinRetanguloEma34.mqh`, `Win_c1.mqh` (adaptações marcadas `WinMaestro:`) |

### Apêndice A, por robô

| Robô | Persistido | Recálculo sem memória | Particularidades implementadas |
|---|---|---|---|
| GB | `g_dkey`, `g_decidido`, `g_exp`, `g_be_feito` | `StopRegra`: preço da ficha ∓ `StopPts` | E `SPECIFIED` até `g_exp`; recusada → DAY; cancelamento pelo módulo em `g_exp`; BE = `Ficha_DefineStop`; fim do contínuo pela grade |
| CM | `g_ultima_barra`, a favor do mês, nível do stop que aperta | `StopRegra`: stop que aperta das barras desde a hora da ficha; senão reserva | S de reserva a 4.945 pts; zeragem 18:24 desligada (o maestro zera em min(18:24, corte)); bloqueio L774 removido |
| DM | `g_stopNivel`, `g_distStop`, `g_stopAjustado`, `g_decidiu`, `g_dia`, `g_ordemHora`, `g_ordemPreco`, `g_ordem` | `DistStopDaDecisao` (decisão das 10:30 refeita das barras M1) | S em `g_stopNivel` movida no fill (B8); teto sobre `DM_CAPITAL` (B9); bloqueio L379 removido; a E só é esquecida com o cancelamento confirmado; `Deinit` não cancela |
| RE | entrada pendente (vela, lado, meio/stop/alvo originais), posição (preço, largura, fração, vela do fill), retângulo, gates de vela | contagens de velas refeitas dos instantes (`ContaVelas`); sem regra de stop | S reancorada no fill; alvo DAY (o maestro o recria se faltar); fill tardio (`EXECUTOU_ANTES`) adotado; `TesterStop` removido; `Deinit` não cancela |
| C1 | `g_ultima_barra` (nível do stop na memória do maestro) | `StopRegra`: LWMA(34) das barras H1 ± K × ATR | entrada a mercado com a S antes; trailing pode afrouxar; bloqueio L620 removido |

## 2. Escolhas em ambiguidades

1. **Retcode que prova recusa.** Retcodes em que o servidor responde "não" (REJECT, INVALID*, MARKET_CLOSED, NO_MONEY, LIMIT_*, TOO_MANY_REQUESTS, LOCKED etc.; lista em `Mae_RecusaDefinitiva`) viram `RECUSADA` na hora. Os demais (TIMEOUT, CONNECTION, ERROR, retcode 0, ticket 0, DONE sem deal) são "não sei" e a ordem vai para o trânsito.
2. **Atribuição e papel do deal (P2, P3).** O robô do deal é o `DEAL_MAGIC`; com magic 0, o magic da ordem de origem (mapa das ordens que o maestro mandou ou viu vivas, depois o histórico de ordens). Deal com magic 0 sem ordem localizada fica 10 s sem efeito nas fichas (carência); depois, é externo. O papel é o **registrado no envio** (o registro é a verdade); sem registro, o comentário `MAE|robô|papel|seq` da ordem; sem ele, tipo da ordem e ficha no instante da colocação. Uma X ou C que executa sobre ficha 0 abre ficha **trocada**. Deal de robô cuja ordem não foi identificada deixa a ficha **indeterminada**: o módulo não a vê e nada além da proteção é decidido; ela recebe S; 30 s depois sem a ordem, é tratada como trocada (correção e corte).
3. **Ficha trocada** = ficha aberta por deal que não foi de uma E (qualquer volume). **Duplicada** = aberta por E com \|ficha\| ≥ 2. Ficha invertida com a E do robô viva (ou E a mercado sem desfecho) no sentido oposto é o transitório da entrada (5.3).
4. **Absorção (7.1) e alvos.** Cancelam-se as A das fichas absorvidas (viram órfãs). A de robô não absorvido fica: executar reduz a própria ficha.
5. **Janelas.** Entradas, alvos, saídas e correções só no contínuo (entradas até a zeragem do robô). S e cancelamentos de `preabertura_inicio` até F + 15 min (o call de fechamento), para cancelar órfã e proteger ficha que sobrou depois de F. Dias úteis.
6. **Data sem linha na grade:** F = 17:55 (spec); início 09:00 e pré-abertura 08:55.
7. **Vencimento do contrato do gráfico:** não muda o corte. Vale o fim do contínuo da grade do dia (decisão do dono). O vencimento é calculado só para o log (`WIN` + letra + 2 dígitos).
8. **Preenchimento a mercado (P15):** `RETURN` com execução de bolsa; senão `IOC` se permitido, senão `FOK`.
9. **DM, stop pelo último negócio.** Com a S no servidor no próprio nível (B8, O9 excluído), a saída do módulo pelo último negócio fica desligada por flag (evita saída dupla, item 1.23). No preenchimento, nível já atravessado → saída.
10. **GB, validade com horário recusada:** o maestro tenta na hora a validade do dia **com a mesma S** (não cancela e recria), e o GB cancela a E em `g_exp` como antes.
11. **RE, fill depois do cancelamento.** O aviso `EXECUTOU_ANTES`, síncrono ou resolvido depois pelo trânsito, restaura o estado da entrada a partir do lado e dos níveis originais, e `DetectarPreenchimentoEntrada` adota o fill. O módulo não esquece a E enquanto o cancelamento não for confirmado.
12. **CM, stop que aperta.** "Nunca afrouxa" compara com o último stop que aperta pedido pelo módulo, não com a S de reserva.
13. **`OnDeinit`.** Grava a memória sempre que `g_iniciou`; libera a trava só fora de `PARAMETERS`/`CHARTCHANGE`/`TEMPLATE`.
14. **Magics constantes**, os da §1. Não há input de magic: trocar o magic com o robô posicionado deixaria a ficha e a S antigas fora do alcance do maestro.
15. **Verificação cruzada em operação.** Com leitura confiável e a cruzada aberta, nada além da proteção sai; releitura completa a cada 10 s; ALERTA aos 30 s; bloqueio com botão aos 60 s de falha contínua, com o texto "verificação cruzada não fecha há 60 s: deals × líquida (diferença na janela de 10 pregões)".
16. **Custos no resultado:** `DEAL_COMMISSION` e `DEAL_FEE` somados como vêm do MT5 (negativos = cobrança).
17. **`OrderModify` fora do trânsito.** Mover S ou A não cria ordem: o resultado aparece no preço da ordem viva; recusado, o maestro retenta a cada 5 s.
18. **OCO.** Irmã colocada antes do deal que zerou a ficha é cancelada na hora; qualquer outra órfã espera 5 s de vida. Toda órfã é reconferida com a lista de pendentes relida antes do cancelamento.
19. **A proteção não tem portão.** Criar ou mover a S só exige a lista de ordens lida, nenhuma outra S do robô em trânsito e o lado/volume coerente. Leitura não confiável, cruzada aberta, memória não gravada, ficha indeterminada, trava em outro gráfico e ordem de outro papel em trânsito não barram a S. Exceção única: com uma X ou C do robô sem desfecho e a cruzada aberta (sinal de que a saída já executou e o deal não chegou), nenhuma S **nova** é criada para a ficha, para não abrir posição ao disparar. A S que cruzaria com limite própria de outro robô sai mesmo assim, com AVISO `AUTONEG` (P12).
20. **`DECISAO PERDIDA`.** Cada módulo informa o instante da decisão (GB 09:05; CM, C1 e RE abertura da vela; DM a M1 da decisão). Decisão anterior ao `PRONTO` não envia. No Testador a sequência de partida roda inteira no primeiro evento, antes do primeiro `Tick()` dos módulos, e nenhuma decisão é dada como perdida (o EA nunca esteve fora).
21. **Leitura de mercado nos módulos.** Os módulos seguem lendo cotação, sessão e barras (`SymbolInfoDouble`, `SymbolInfoSessionTrade`, `CopyRates`, `iMA`) direto: é dado de sinal. Posição, ordem, histórico e conta passam pela `Corretora.mqh`.
22. **Envio sem espera.** `OrderSend` síncrono, uma leitura do desfecho logo depois e, sem prova, a ordem fica no trânsito; o desfecho chega nos ciclos seguintes (`OnTradeTransaction` a cada deal e timer de 1 s). A interface da corretora não tem pausa: nenhuma chamada dorme.
23. **Modo PROTEGENDO.** Disparado por líquida ≠ 0 ou ordem viva com magic de robô. Nele saem só S, cancelamentos e a saída do corte (sem correções, zeragens por horário de robô nem alvos). Com a falha "conta não é NETTING", nenhuma ordem sai (só ALERTA).
24. **Memória no Testador:** sem heartbeat, para gravar só quando algo muda.
25. **Correção de trocada e duplicada.** Numa ordem só, com o volume que leva a ficha ao estado válido: \|ficha\| na trocada (com o A cancelado antes e a S depois), \|ficha\| − 1 na duplicada (A e S mantidos). A ficha errada recebe S cobrindo \|ficha\| a qualquer hora em que a corretora aceite ordens: nível da memória (duplicada), da regra do robô, ou de emergência (trocada). Uma correção por **episódio** (período contínuo com a ficha errada, com retentativas a cada 5 s); um episódio novo a menos de 10 min de uma correção **executada** trava as correções do robô e bloqueia as entradas, e a ficha segue protegida pela S.
26. **E sem S.** Toda entrada nasce com a S; se ela sumir, é recriada (retentativa a cada 5 s) e a E só é cancelada depois de 10 s sem S.
27. **Módulos calculam sempre.** `Tick()` dos robôs roda a qualquer hora depois do `PRONTO`, inclusive no leilão e fora do pregão, como no avulso. Só o envio é condicionado (horário, D1, bloqueio, uma operação por vez). Isso substitui a janela de `Tick()` da §9.1 por decisão do dono.
28. **Relógios.** Os módulos decidem com `TimeCurrent()` (como o avulso) e o maestro com `TimeTradeServer()`; nas fronteiras (corte, última entrada) os dois podem discordar por segundos. No Testador são iguais.
29. **Corte com a verificação cruzada aberta (D2, decisão do dono).** Se a cruzada não fecha no corte, as fichas não descrevem a conta e `Mae_CorteConta` decide só pela posição real e pelas ordens reais vivas: (0) espera **toda** ordem de robô em trânsito ter desfecho e a cruzada estar aberta há 10 s (lag de deal não é histórico incompleto); (1) cancela as limites vivas dos robôs (E, A); (2) com a líquida real ≠ 0, uma C a mercado de −líquida, com o magic do primeiro robô (ordem fixa) que tem S viva do lado que protege a líquida (sem nenhum, GB), registrada como C (nunca vira entrada); (3) com a líquida real 0, cancela as S. Sem ordem em voo, sem limite viva e com volume igual a −líquida, a exposição nunca passa da líquida inicial. Posição ilegível: nada sai, ALERTA por minuto. Em F com algo aberto ou ordem sem desfecho: as S DAY ficam, ALERTA por minuto. Depois do corte com a cruzada aberta nenhuma S nova é criada.

30. **Saída por regra barrada por estado aberto.** Se `Ficha_Fecha` encontra o estado aberto (cruzada aberta por um instante, ordem do robô sem desfecho, leitura não confiável), o pedido fica no maestro (`mzSaidaPedida`, na memória) e o módulo recebe `ENVIADA`: o maestro manda a saída assim que o estado fechar, no ciclo seguinte. O pedido some se a ficha zerar ou mudar; se a saída for recusada pela corretora, volta à regra do robô. Igual para os cinco módulos, sem tocar no portão de vela deles.
31. **Memória que não grava** barra só entradas novas; S, cancelamentos, OCO, saídas, zeragens, correções e o corte saem (a linha `ORDEM` do log, fonte da recuperação, é gravada antes de todo envio).
32. **Trava.** Variável da trava apagada: retomada com AVISO. Só o valor de outro gráfico é trava perdida, e então desta instância só sai proteção (S).
33. **Avisos aos módulos** (`ENTRADA_CANCELADA`, `EXECUTOU_ANTES`) emitidos antes do `Init` dos módulos (passos 6–9 da partida) ficam na fila e são entregues depois do `Init`. `EXECUTOU_ANTES` só quando a ordem cancelada era a E do robô.
34. **Retentativas por papel:** saídas/correções, S, alvo e cancelamento da E têm prazo e contador de recusas próprios. Recusa `MARKET_CLOSED` (feriado, leilão prorrogado) é retentada a cada 5 s com AVISO por objeto, sem contar para o ALERTA.

## 3. Achados da revisão de código 1

| Achado | Situação | Onde | Teste |
|---|---|---|---|
| C-1 S só depois da E; trânsito barrava a S | Corrigido: S antes da E em todos os robôs; a S não espera ordem de outro papel | `F:Mae_Entra`, `F:Mae_EstadoFecha`, `F:Mae_Fase2` | T01, T08, T27, T28 |
| C-2 trocada/duplicada sem S; 1 contrato por 10 min | Corrigido: S cobrindo \|ficha\| sempre; correção numa ordem; trava por episódio | `F:Mae_Fase1`, `F:Mae_Fase2`, `F:Mae_Estado` | T11, T29, T30, T55 |
| A-1 deal sem `DEAL_MAGIC` virava externo | Corrigido: magic da ordem de origem | `F:Mae_Mescla`, `F:Mae_OmAdd` | T31 |
| A-2 cancelamento de E sem confirmação esquecido | Corrigido: refeito a cada 5 s; `Ficha_Cancela` só devolve `ENVIADA` com o cancelamento confirmado; DM e RE não esquecem a E | `F:Ficha_Cancela`, `F:Mae_Fase1`; módulos DM e RE | T32 |
| A-3 comentário repetido casava ordem errada | Corrigido: busca só do robô, desde o envio − 2 s; seq do dia conferido com o histórico em toda partida | `F:Mae_Prova`, `R:Rec_SeqHistorico` | T33, T60 |
| A-4 histórico ilegível mantinha estado "confiável" | Corrigido: falha de leitura deixa o estado não confiável até releitura completa | `F:Leitura_Atualiza` | T34 |
| A-5 RE perdia a última vela do pregão anterior | Corrigido: os módulos calculam sempre; só o envio é condicionado | `F:Mae_PodeTick` | sem teste unitário: o efeito é do módulo RE com barras reais (equivalência no Testador) |
| A-6 RE sem adoção de fill tardio e sem alvo recriado | Corrigido: evento restaura a entrada; o maestro recria o alvo | módulo RE `Evento`; `F:Mae_Fase2` | T24, T36 |
| M-1 deal de ordem não lida virava E | Corrigido: ficha indeterminada até a ordem aparecer (com S) | `F:Ficha_Calcula`, `F:Ficha_Tem` | T37 |
| M-2 órfã decidida sobre lista parcial | Corrigido: fases só com a lista lida; órfã reconferida antes do cancelamento | `F:Mae_Reconcilia`, `F:Mae_Fase1` | T38 |
| M-3 espera bloqueante de 5 s; trava nunca reconferida | Corrigido: envio sem espera (a interface não tem pausa); trava conferida a cada segundo | `F:Mae_Envia`, `R:Trava_Confere`, `R:Mae_OnTimer` | T06, T22, T39, T72 |
| M-4 feriados | Corrigido pela corretora: recusa `MARKET_CLOSED` é retentada com AVISO por objeto, sem escalar; sem lista de feriados (aprovado pelo dono) | `F:Mae_Recusa` | T40, T84 |
| M-5 PROTEGENDO mandava correções; hedging perigoso | Corrigido: só S, cancelamentos e corte; conta não NETTING: nada | `F:Mae_Fase1`, `F:Mae_Fase2`, `R:Recupera_Passo` | T41 |
| M-6 botão apagava todo o trânsito | Corrigido: só ordens sem desfecho há 10 min | `F:Mae_Desbloqueia` | T42 |
| M-7 ajuste noturno como fecha/reabre | Corrigido: par externo oposto, mesmo volume, no mesmo segundo e fora do contínuo = `AJUSTE`; deal externo fora do contínuo = ALERTA | `F:Ficha_Calcula`, `F:Mae_NovosEventos` | T43 |
| M-8 magics como input | Corrigido: constantes | `F:mzMagic`, `EA` | compilação (sem input de magic) |
| M-9 falha de gravação silenciosa | Corrigido: ALERTA por objeto; só a proteção sai até gravar | `F:Mae_GravaMemoria`, `F:Mae_Envia`, `F:Mae_PodeEntrar` | T44 |
| M-10 cruzada aberta paralisava a proteção | Corrigido: a S passa; texto do bloqueio corrigido; no corte, a líquida real é zerada (escolha 29) | `F:Mae_EstadoFecha`, `F:Mae_Reconcilia`, `F:Mae_CorteConta` | T45, T61 |
| B-1 alvo recriado na ficha da noite fora do contínuo | Corrigido | `F:Mae_Fase2`, `F:Ficha_DefineAlvo` | T46 |
| B-2 correção de duplicada cancelava o alvo | Corrigido | `F:Mae_Fase1` | T47 |
| B-3 log por instante (deal no mesmo ms, absorção relogada) | Corrigido: marca por ticket; absorção reconhecida não reloga | `F:Mae_Mescla`, `F:Mae_NovosEventos` | T48, T12 |
| B-4 `ESTADO` nunca encerrado | Corrigido: encerrado quando o envio seguinte do robô passa | `Log:Log_CondEncerraPrefixo`, `F:Mae_Envia` | T49 |
| B-5 S ao lado da E nunca retentada | Corrigido: S retentada em 5 s; E cancelada só com 10 s sem S | `F:Mae_Fase1`, `F:Mae_Fase2` | T50 |
| B-6 idade de órfã com resolução de segundo | Corrigido: ms do último tick | `F:Mae_AgoraMsc` | T51 |
| B-7 vetores de 16 | Corrigido: 32 por robô (o máximo real é 3) | `F:Mae_Estado` | T52 |
| B-8 checksum Unicode × arquivo ANSI | Corrigido: arquivo Unicode | `Memoria.mqh` | T53, T17 |
| B-9 classe real compilada no teste | Corrigido: `#ifndef WINMAESTRO_TESTE` | `Corretora.mqh` | compilação do EA de teste |
| B-10 TOO_MANY_REQUESTS/LOCKED como "não sei" | Corrigido | `F:Mae_RecusaDefinitiva` | T54 |
| B-11 `PositionSelect` falso com erro 0 = zerado | Corrigido: `ERR_TRADE_POSITION_NOT_FOUND`, ou a lista de posições lida inteira e sem o símbolo | `Corretora.mqh:LeLiquida` | sem teste unitário: a classe real não é compilada no EA de teste (B-9) |
| B-12 `TimeCurrent` × `TimeTradeServer` | Documentado (escolha 28), como o relatório propõe | — | — |

Lacunas de cobertura: sequência de partida (T56, T67, T83), memória de ida e volta (T57), `OnTradeTransaction` (T58), `OnTimer` (T86), perda de conexão (T59), lista parcial de pendentes (T38), deal sem magic (T31, T69), colisão de comentário (T33, T60).

## 4. Achados da revisão de código 2

| Achado | Situação | Onde | Teste |
|---|---|---|---|
| A-1 corte ignorava ordens em trânsito e usava fichas velhas | Corrigido: espera toda ordem em trânsito e 10 s de cruzada aberta; decide pela posição e ordens reais; limites antes; C com o dono da S do lado; nunca passa da líquida inicial | `F:Mae_CorteConta` | T22, T61, T62 |
| A-2 saída por regra `BLOQUEADA` perdida até a próxima vela | Corrigido: pedido guardado no maestro e enviado quando o estado fechar (escolha 30) | `F:Ficha_Fecha`, `F:Mae_Fase1` | T63 |
| A-3 X depois do zero virava entrada | Corrigido: o papel do registro vence; sem registro, o comentário; X/C sobre ficha 0 = trocada | `F:Ficha_Calcula` | T64 |
| A-4 memória que não grava barrava proteção e saídas | Corrigido: barra só entradas novas | `F:Mae_EstadoFecha`, `F:Mae_Envia` | T44, T65 |
| M-1 `EXECUTOU_ANTES` para qualquer cancelamento | Corrigido: só quando a ordem cancelada era a E | `F:Transito_Resolve` | T66 |
| M-2 externa desconhecida fora do passo 4 | Corrigido: lida da memória antes do passo 4 | `R:Recupera_Passo` | T67 |
| M-3 nada saía depois de F | Corrigido: S e cancelamentos até F + 15 min | `F:Mae_JanelaCall` | T68 |
| M-4 ficha indeterminada sem proteção | Corrigido: recebe S; 30 s sem a ordem → trocada (corrigida) | `F:Mae_Fase2`, `F:Mae_IndetVelha` | T37 |
| M-5 deal sem magic com a ordem ainda fora do histórico virava externo na hora | Corrigido: 10 s de carência sem efeito | `F:Ficha_Calcula`, `F:Mae_NovosEventos` | T69 |
| M-6 prova `D_NAO` com a E viva e o comentário perdido | Corrigido: busca por tipo, preço, volume e instante | `F:Mae_Prova`, `F:Mae_OmLivre` | T70 |
| M-7 fallback DAY do GB falhava com o cancelamento da S sem prova | Corrigido: o maestro tenta DAY com a mesma S | `F:Mae_Entra`; módulo GB | T71 |
| M-8 variável da trava apagada parava tudo | Corrigido: retomada; trava perdida só deixa sair S | `R:Trava_Confere`, `F:Mae_EstadoFecha` | T39, T72 |
| B-1 avisos antes do `Init` dos módulos | Corrigido: fila entregue depois do `Init` | `F:Mae_Evento`, `R:Recupera_Passo` | T73 |
| B-2 PROTEGENDO recriava o alvo | Corrigido | `F:Mae_Fase2` | T74 |
| B-3 S complementar de volume \|f\| deixava 2–3 s sem stop | Corrigido: S de 1 por contrato que falta | `F:Mae_Fase2` | T75 |
| B-4 memória perdida relogava todos os deals | Corrigido: deals das linhas do log do dia ficam marcados | `R:Recupera_LogOrdens` | T76 |
| B-5 S contra limite própria (P12) | AVISO `AUTONEG`; a S sai assim mesmo (proteção sem portão, escolha 19) | `F:Mae_EstadoFecha` | T77 |
| B-6 código de erro do `PositionSelect` | Corrigido sem depender do código (lista de posições) | `Corretora.mqh:LeLiquida` | sem teste unitário (classe real, B-9) |
| B-7 releitura de 10 pregões por tick | Corrigido: no máximo uma a cada 10 s | `F:Mae_PedeReler` | T78 |
| B-8 prazos e contadores compartilhados; pedido de cancelamento nunca desligado | Corrigido | `F:Mae_Recusa`, `F:Ficha_Cancela` | T79 |
| B-9 cancelar e rearmar na mesma vela | Corrigido: cancelamento de S antiga em curso não barra a entrada | `F:Mae_PodeEntrar`, `F:Mae_EstadoFecha` | T80 |
| Parcial A-1 (rev. 1) ordem fora do histórico | Corrigido (M-5) | — | T69 |
| Parcial M-5 (rev. 1) alvo em PROTEGENDO | Corrigido (B-2) | — | T74 |
| Parcial B-3 (rev. 1) relog com memória perdida | Corrigido (B-4) | — | T76 |
| T22 falhava | Passa pelo código (A-1) | — | T22 |
| Testes por construção ou da falsa | T35 removido; T51 com o tick em outro instante; T39 sobre a trava; T58 pelo manipulador do maestro; T26 com a falsa recusando stop do lado errado; T21, T34, T45, T46 pela reconciliação | — | — |
| Testes de comportamento inseguro | T37 exige S e correção; T28 exige nenhuma S para a saída que já executou | — | T28, T37 |
| Equivalência: vencimento | O corte segue a grade do dia (escolha 7) | `F:Mae_Horarios` | T18 |
| Equivalência: decisões antes do `PRONTO` | No Testador a partida roda inteira no primeiro evento e nenhuma decisão é perdida (escolha 20) | `R:Recupera_Completa`, `EA:OnTick` | T67, T83 |
| Equivalência: fallback do GB | Escolha 10 | — | T71 |

Módulos cobertos pelos testes: DM (T81, cancelamento não confirmado) e RE (T82, cancelamento e `EXECUTOU_ANTES`).

## 5. O que ficou fora e por quê

- **Equivalência no Testador (§12, testes 1 e 2) e testes de falha na demo (§12, 1–14):** pedem o Testador ou o terminal, que esta entrega não roda.
- **Execução dos testes unitários:** `WinMaestro_Teste.mq5` compila com 0 erros e 0 avisos, mas não foi executado (exige anexar a um gráfico). Os 87 casos foram conferidos linha a linha contra o código.
- **Lista de feriados da B3 (M-4):** não foi embutida (aprovado pelo dono).
- **Testes que dependem de barras ou da corretora real:** o cálculo do RE no leilão (A-5 da rev. 1), o tratamento de `BLOQUEADA` dentro dos módulos CM/C1 com portão de vela e `LeLiquida`/`LePendentes` reais (B-6) só se exercitam com barras e terminal reais: equivalência no Testador e demo. Um feriado marcado errado num dia de pregão desligaria naquele dia as S, o corte e as zeragens; a corretora já responde `MARKET_CLOSED` em feriado, e isso é tratado sem alarme. O recuo da janela de histórico conta o feriado como um dos 10 dias, o que só alonga a janela.
- **O6 (3 leituras iguais em ≥ 3 s):** condicional a P6/P18.
- **Milissegundos do log:** o `.mmm` vem do contador local; a coluna `tick` traz o `time_msc` do último tick.
- **Recálculo sem memória do RE e do DM:** o retângulo não é reconstruível das barras (sem memória, a S fica a viva ou a de emergência e o alvo não é recriado); no DM, o ajuste da limite ao livro no instante da decisão não é reproduzível.
- **Comparação fichas × `DEAL_PROFIT` no resumo:** só em dia sem deal externo, começado e terminado com a líquida zerada.
- **Mensagens próprias dos módulos** (`Print`) vão só ao Diário do MT5.
- **Trava entre PCs ou terminais diferentes:** fora do escopo (D3).

## 6. Pontos que só a demo ou a corretora respondem

| Pergunta | Onde o código depende dela |
|---|---|
| P1 S DAY aceita no WIN, listada com o terminal fechado, a partir de que hora | Princípio 4; S da ficha da noite tentada a partir das 08:55 (`Mae_JanelaOrdens`), retentada a cada 5 s |
| P2 deal de pendente carrega `DEAL_MAGIC` | `Mae_Mescla`: sem magic, vale o da ordem de origem (AVISO no log responde P2) |
| P3 comentário sobrevive | busca de ordem sem ticket por comentário (`Mae_Prova`); nada decide papel por comentário |
| P4 `OrderModify` mantém o ticket | `Mae_Modifica`, `Ficha_DefineStop/Alvo` |
| P5 `OrderDelete` de ordem que acabou de disparar | `Mae_Prova` (cancelamento: `D_ANTES`) |
| P6 / P18 atraso do deal no histórico | trânsito resolvido nos ciclos seguintes; O6 |
| P7 / P8 / P9 margem | nada no EA depende de saldo (B7) |
| P10 zeragem pela mesa: magic | classificação de externa e absorção (§7) |
| P11 zeragem compulsória | vira deal externo (absorção + bloqueio) |
| P12 Self-Trade Prevention | `Mae_Autoneg` (verificado antes da S, na entrada) |
| P13 stop e mercado em leilão | ficha da noite e saídas recusadas (retentativa a cada 5 s) |
| P14 ajuste noturno | par fecha/reabre fora do contínuo tratado como `AJUSTE`; deal externo fora do contínuo = ALERTA |
| P15 modos de preenchimento | `Recupera_Ambiente` |
| P16 `GlobalVariableSetOnCondition` como trava | `Trava_Toma`, `Trava_Confere` |
| P17 globais em `REASON_PARAMETERS` | `OnInit` reinicializa tudo explicitamente |
| P19 `TimeTradeServer` sem feed | relógio de corte e zeragem no timer |
| P20 limites de ordens | até 15 ordens vivas (5 robôs × E/S/A), mais S complementares de ficha duplicada |
| P21 demo casa no livro real | escada no real (§12) |
| P22 relógio em Brasília | AVISO no `PRONTO` se `TimeTradeServer − TimeGMT ≠ −3 h`; GB usa offset 0 |
