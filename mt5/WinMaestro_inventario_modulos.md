# WinMaestro - inventário dos módulos do WinSeletor

Fonte lida por inteiro (sem editar nada): `mt5\WinSeletor.mq5` (351 linhas) e `mt5\WinSeletor\` com `Comum.mqh` (31), `WinGapBarra1.mqh` (410), `WinCincoMedias.mqh` (811), `WinDeslocamentoMatinal.mqh` (548), `WinRetanguloEma34.mqh` (1066), `Win_c1.mqh` (662). Os números de linha abaixo são do arquivo citado em cada seção.

Objetivo do inventário: trocar toda interação com posição/ordem real por uma camada de fichas (posição virtual por robô, com o maestro enviando as ordens com o magic de cada robô), e persistir em disco todo estado que hoje só existe em memória.

Siglas: WGB1 = WinGapBarra1 (M5, magic 80080601), WCM = WinCincoMedias (H2, magic 80080501), WDM = WinDeslocamentoMatinal (M1, magic 80080101), WRE = WinRetanguloEma34 (M15, magic 20261005), WC1 = Win_c1 (H1, magic 80080002).

---------------------------------------------------------------------

## 0. Camada comum e WinSeletor.mq5

### Comum.mqh
- L10-29 `WinTemPosOuOrdens(magic)`: varre `PositionsTotal()` (L12-19) e `OrdersTotal()` (L20-27) filtrando símbolo e magic. Pergunta: "este robô tem posição ou ordem pendente?". Só é usada pelo `Tem()` de cada módulo (e por `RoboTem` no .mq5). Na ficha vira "ficha != flat OU ordem virtual pendente".

### WinSeletor.mq5
- Nenhuma leitura direta de posição além de `Comum`. `OnInit` L303-349 usa `RoboTem(r)` (L325-328) para descobrir o "dono" da posição e recusar troca (L332-340); `OnTick` L357-381 conclui a troca pendente quando `!RoboTem(g_ativo)` (L360) chamando `RoboDeinit`/`RoboInit`.
- Único estado já persistido em disco/terminal: GlobalVariable `WinSeletor.<símbolo>.<MagicSeletor>` = robô ativo (`ChaveAtivo` L291-294, `GravaAtivo` L296-300; não grava no Testador). Todo o resto (ver seções por módulo) é perdido.
- Estado: `g_ativo` (L200), `g_troca_pendente` (L201). No maestro deixam de existir (5 robôs ao mesmo tempo; `SoGerir`/`DefineSoGerir` por módulo some).
- Inputs: L80-191, prefixos GB_/CM_/DM_/RE_/C1_, cada um com `*_MagicNumber` próprio (RE_ L162, GB_ L100, CM_ L116, DM_ L141, C1_ L188). Cada módulo recebe tudo em `Configura()`.
- Ciclo de vida de cada módulo: `Configura -> Init -> (Tick por tick) -> Deinit`; `Reseta()` zera TODO o estado em memória no `Init` (portanto "religar" = perder estado).
- Achados transversais (valem para os 5):
  - Bloco "Z8 NaoOperarGapATR" (`g_gap_dia_avaliado`, `g_gap_bloqueado`, `GapVencimentoWIN`, `GapSimboloContinuo`, `GapDiaDeRolagem`, `GapDiaBloqueado`) copiado 5 vezes: WGB1 NÃO tem (nem input de gap); WCM L100-221, WDM L78-200, WRE L286-408, WC1 L104-226. Não lê posição nem conta; só barras M1. Estado recalculável (ver (b)).
  - `CTrade trade` por módulo, com configurações de preenchimento diferentes: WGB1 `SetTypeFilling(ORDER_FILLING_RETURN)` + `SetDeviationInPoints(0)` (L210-211); WDM `SetTypeFillingBySymbol` (L207); WCM/WRE/WC1 só `SetExpertMagicNumber` (padrão do CTrade). O maestro tem de decidir um único jeito de enviar.
  - O `trade.SetExpertMagicNumber(MagicNumber)` é o que carimba o magic nas ordens: WGB1 L209, WCM L245, WDM L206, WRE L456, WC1 L272.
  - Macros globais (fora do namespace) em WRE: `CORTE_ENTRADA_MAX_MIN`, `TOQUES_MINIMOS`, `VISITAS_MINIMAS`, `CRUZAMENTOS_MINIMOS`, `CONTENCAO_MINIMA`, `CONTRACAO_MAXIMA`, `ESPALHAMENTO_MINIMO`, `DERIVA_MAXIMA`, `LARGURA_MINIMA_TICKS`, `MARGEM_MORTE`, `BARRAS_MORTE`, `OBJ_NOME_CAIXA/MEIO`, `VELAS_PRE_CARGA`, `FIM_SESSAO_FALLBACK_MIN` (L84-94, 114-115, 184, 691). Nomes únicos hoje; cuidado com colisões se o maestro definir macros parecidas.
  - Variáveis `static` locais que `Reseta()` não zera (irrelevantes, só cache de horário): WCM `MinutoZerarHoje` L689-690; WRE `FimSessaoMinutos` L187.
  - `HistorySelectByPosition` (WCM L425) muda o pool global de histórico do EA inteiro; se o maestro (ou outro módulo) usar `HistorySelect*` na mesma execução, não pode ser intercalado sem reselecionar.
  - Seleção de posição/ordem é global ao EA: após `PositionSelect`/`PositionGetTicket(i)`/`OrderGetTicket(i)`/`OrderSelect`, as chamadas `PositionGet*`/`OrderGet*` leem o "item selecionado". Vários módulos dependem desse efeito colateral (WCM L761-762, WDM L535, WRE L810/L856, WC1 L510 em diante). Uma camada de fichas precisa devolver os dados explicitamente.

---------------------------------------------------------------------

## 1. WinGapBarra1.mqh (WGB1)

### 1.1 Leituras de posição
| Linha | O quê | Quer saber |
|---|---|---|
| 166-181 `PosicaoNossa` | loop `PositionsTotal/PositionGetTicket`, filtra `POSITION_SYMBOL` e `POSITION_MAGIC == MagicNumber`; lê `POSITION_TYPE` (175), `POSITION_PRICE_OPEN` (176), `POSITION_VOLUME` (177), ticket (171) | tem posição minha? lado, preço de entrada, volume |
| 219 (`Zerar`), 354 (`Tick`) | chamadas de `PosicaoNossa` | idem |

- Não usa `PositionSelect(_Symbol)`: não bloqueia por posição de outro robô (só filtra por magic). Não existe nenhum "if(PositionSelect(_Symbol)) return".
- Fecha por ticket: L221 `trade.PositionClose(tk)`. Em netting o ticket é o da posição única do símbolo, então fecha a posição INTEIRA (de todos os robôs), mesmo com o filtro de magic na leitura.
- Não lê SL, TP, comentário, identificador nem hora da posição.
- `vol` e `entrada` lidos (preço médio da posição real) alimentam o alvo e o break-even (`GerirPosicao` L228-250): em netting ficam errados se outro robô somou/subtraiu.

### 1.2 Ordens enviadas/modificadas/canceladas
| Linha | Operação | Tipo / validade / comentário | Stop |
|---|---|---|---|
| 330 / 331 | `BuyLimit` / `SellLimit` (entrada), vol 1.0 fixo (L312) | `ORDER_TIME_SPECIFIED`, `exp = abertura + TtlBarras*300 s` (L270), comentário `"wgb1 E"` (L76) | **SL anexado na ordem** (L322-323, `sl = preço -/+ StopPts`), tp 0 -> stop no SERVIDOR |
| 336 / 337 | fallback se validade rejeitada | `ORDER_TIME_DAY`, mesmo comentário e SL; o EA cancela em `g_exp` (L364) | idem |
| 235 / 237 | alvo: `SellLimit` (compra) / `BuyLimit` (venda) em `entr +/- AlvoDist()`, volume = volume da posição | `ORDER_TIME_GTC`, comentário `"wgb1 A"` (L77); só existe se `AlvoPts>0` ou `AlvoR>0` (padrão 0 = desligado) e se não há `COM_ALVO` pendente (L232) | - |
| 247 | `PositionModify(tk, novo, 0.0)` break-even: SL = entrada +/- 5 pts, só se `BeR>0` (padrão 0) | SL no servidor; passa tp=0.0 | servidor |
| 195 | `OrderDelete(tk)` dentro de `PendentesNossas(com, apagar=true)` (L184-198); chamadas: L224 (Zerar, todas), L364 (validade, só `COM_ENT`), L372 (alvo órfão sem posição) | - | - |
| 221 | `PositionClose(tk)` (Zerar) | mercado | - |

- Stop = **servidor** (SL da posição, vindo da ordem de entrada). O EA não faz stop próprio. Padrão do input é 1200 pts.
- Identificação das ordens: magic + comentário (`PendentesNossas` filtra `ORDER_COMMENT`, L193).

### 1.3 Estado em memória
| Variável | Tipo | Significado | Quando muda | Classe |
|---|---|---|---|---|
| `g_dkey` (L71) | long | dia (chave BRT) em curso | 1º tick do dia (L347-350) | (b) |
| `g_decidido` (L72) | bool | sinal do dia já avaliado (com ou sem sinal) | `AvaliaSinal` L262; zera na virada (L349) | **(a)** |
| `g_be_feito` (L73) | bool | break-even já aplicado | L247; zera na virada | **(a)** (só se BeR>0; padrão desligado) |
| `g_exp` (L74) | datetime | validade da ordem de entrada (backup do prazo do servidor) | L328; zera na virada | **(a)** |
| `StopPts, AlvoPts, ... MagicNumber, SoGerir` (L22-41) | inputs copiados | config | `Configura()` | (c) |
| `trade` (L69) | CTrade | - | - | (c) |
- Não persiste ticket da ordem de entrada nem da ordem alvo: ambas são reencontradas por magic+comentário (`PendentesNossas`). Com fichas, esse reencontro por magic some e precisa virar ordem virtual com id.
- Para o maestro o robô precisa também (a): lado, preço de entrada, volume, nível do SL (virtual), flag BE, id/ticket da ordem alvo, data do pregão.

### 1.4 Reinício com posição/ordem aberta
- Tudo zera: `g_dkey=-1`, então o 1º tick considera "dia novo" e zera `g_decidido`, `g_be_feito`, `g_exp` (L347-350; `Reseta` L389).
- **Perde:** `g_decidido`: se o EA cai com a ordem de entrada viva e volta antes de `exp` (09:35) e depois de 09:05, `AvaliaSinal` roda de novo (L374-377) e **envia uma 2ª ordem de entrada** (nem a ordem existente é consultada). `g_exp`: some o backup de cancelamento por prazo (depende só da validade no servidor; se caiu no fallback `ORDER_TIME_DAY` a ordem fica viva até o flatten). `g_be_feito`: o BE é reavaliado (idempotente: o SL já está em entrada+5 no servidor, e só reaplica se excursão >= BeR*Stop de novo).
- **O que já trata:** posição e alvo reencontrados por magic/comentário; alvo recriado se faltar (L232); alvo órfão apagado sem posição (L372); flatten 18:20 cancela tudo (L357-361). O SL está no servidor, então sobrevive.

### 1.5 Horários / posição de outro dia
- `FlattenSec(key)` L137-142 = min(`FlattenHora:FlattenMinuto` = 18:20, abertura + (`FimContinuo(key)` - 5) min). `FimContinuo` L129-134 = 565 min (18:25) ou 535 (17:55) antes de 2024-03-11 em horário de verão dos EUA (`RegimeAutomatico`). Tempo local = servidor + `ServerGMTOffsetH` (L81-94).
- Tick L357-361: `sec >= FlattenSec` -> se tem posição OU pendente -> `Zerar()` (fecha posição + apaga todas as pendentes do magic) e `return` (nenhuma lógica depois do flatten no dia).
- Não existe regra "posição de outro dia": uma posição que sobrou (EA desligado às 18:20) fica sob o SL servidor até o flatten do dia seguinte (L357), sem zeragem na abertura.
- Entrada só entre 09:05 e `exp` (L271, 375); `GB_EvitarVencimento` (L280-298) bloqueia a 1ª sessão após vencimento.

### 1.6 Saldo/patrimônio
- Nenhum uso de `ACCOUNT_*`. Volume fixo 1.0 (L312).

### 1.7 Outros pontos que quebram em netting compartilhado
- Preço de entrada lido da posição (L176) = preço médio da posição líquida -> alvo e BE ficam errados com 2+ robôs; `vol` também (alvo dimensionado pelo volume líquido, L235/237).
- **SL anexado na ordem limite (L330-337)** vira SL da posição líquida inteira: afeta os outros robôs. Em netting o "stop no servidor" não pode ser por robô.
- `PositionClose(tk)` (L221) fecha a líquida inteira.
- Alvo `SellLimit/BuyLimit` GTC (L235/237) em netting reduz/inverte a posição líquida (se a líquida já foi zerada por outro robô, vira posição NOVA do sinal contrário). A atribuição do preenchimento pode ser feita por `DEAL_MAGIC`/`DEAL_ORDER`, mas o efeito sobre a líquida não é por robô.
- O alvo é recriado quando `PendentesNossas(COM_ALVO)==0` com `POSITION_VOLUME` da líquida.
- Zerar apaga TODAS as pendentes do magic (L224) mas o magic é só do robô: ok com maestro (magic por robô), desde que ordens virtuais sejam rastreadas.
- Comentários "wgb1 E/A" usados como identidade (L193): o maestro vai querer padronizar/prefixar.

---------------------------------------------------------------------

## 2. WinCincoMedias.mqh (WCM)

### 2.1 Leituras de posição
| Linha | O quê | Quer saber |
|---|---|---|
| 270-274 `SelecionaPosicao` | `PositionSelect(_Symbol)` + `POSITION_MAGIC == MagicNumber` | a posição do símbolo é minha? (se outro magic: devolve false, como "não tenho") |
| 719 | `tem_pos = SelecionaPosicao()` | tem posição? |
| 722 | `POSITION_TIME` | posição de outro dia (`de_outro_dia`) |
| 738 | `POSITION_TYPE` | lado |
| 739 -> 419-435 `AFavorDoMes` | `POSITION_COMMENT` (421), `POSITION_IDENTIFIER` (424), `HistorySelectByPosition(id)` + `HistoryOrderGetString(ORDER_COMMENT)` (425-431), `PositionSelect(_Symbol)` de novo (433) | a posição foi aberta "a favor do mês" (`"wcm F"`) ou neutra (`"wcm N"`); sobrevive a reinício por comentário |
| 580-581 `NivelStopAperta` | `POSITION_TIME`, `POSITION_PRICE_OPEN` | vela da entrada (para contar velas) e preço de entrada |
| 600, 609 `AjustaStopAperta` | `POSITION_SL`, `POSITION_TP` | stop atual (nunca afrouxa), TP a preservar |
| 761-762 | `ORDER_TYPE`, `ORDER_TIME_SETUP` da ordem selecionada por `OrdemPendente()` | lado e hora de colocação da limite (validade em velas) |
| 277-288 `OrdemPendente` | loop `OrdersTotal` por símbolo+magic, devolve o 1º ticket (deixa a ordem selecionada) | tem ordem pendente minha? |
- **BLOQUEIO por posição de outro robô:** L774 `if(PositionSelect(_Symbol)) return;` ("posição de outro robô no símbolo: não mexe") - impede sinal novo enquanto QUALQUER robô tiver posição no símbolo.
- **Fecha posição INTEIRA do símbolo:** L440 `trade.PositionClose(_Symbol)` dentro de `Fecha(motivo)` (L438-443). Chamadas: L606 (stop que aperta com preço já além do nível), L723 (zeragem de fim de pregão/outro dia), L752 (qualquer saída por sinal: horário, EMA, alinhamento, climax de volume, Supertrend).
- `SelecionaPosicao` retorna false se a posição do símbolo é de outro magic, mas a posição continua sendo "a do símbolo" em netting.

### 2.2 Ordens
| Linha | Operação | Tipo / validade / comentário | Stop |
|---|---|---|---|
| 677 / 678 `Entra` | `BuyLimit` / `SellLimit`, `Lote` (CM_Lote 1.0), preço = min(fechamento da H2 do sinal, ask) (compra) / max(..., bid) (venda) (L672-675) | `ORDER_TIME_DAY`, comentário `"wcm F"` (a favor do mês) ou `"wcm N"` (L96-97, 676) | sem SL/TP na entrada (L677-678: `0.0, 0.0`) |
| 447 `Cancela` | `OrderDelete(tk)` | chamadas L764 (dia novo), L765 (validade >= `ValidadeVelas`), L766 (alinhamento sumiu) | - |
| 440 `Fecha` | `PositionClose(_Symbol)` | mercado | - |
| 609 `AjustaStopAperta` | `PositionModify(_Symbol, nivel, PositionGetDouble(POSITION_TP))` | "stop que aperta" | **SL no servidor** |
- Stop: não há stop inicial. Só o "stop que aperta" (v2.02): depois de `StopApertaVelas` velas H2 fechadas desde a entrada, se alguma fechou no negativo, coloca SL no servidor em `entrada -/+ StopApertaATR * ATR(14 Wilder)` da vela do sinal (L577-594); nunca afrouxa (L601); se o preço já passou do nível, fecha a mercado (L604-607). É recalculado do zero a cada vela fechada (L552 comentário). Saídas reais por sinal (EMA de saída, alinhamento, climax de volume, Supertrend H4, horário) são controladas pelo EA, a mercado, na vela fechada (L742-752).

### 2.3 Estado em memória
| Variável | Tipo | Significado | Muda | Classe |
|---|---|---|---|---|
| `g_h[5]`, `g_h_saida` (L91-92) | int handles | iMA H2 | Init/Deinit | (c) |
| `g_ultima_barra` (L93) | datetime | última vela H2 processada (gate de "vela nova") | L727-728 | **(a)** (ver 2.4) |
| `g_a_favor` (L94) | bool | posição aberta é a favor do mês | L739 (a cada vela, vindo do comentário) | (a) -> vai para a ficha (hoje recuperado do comentário) |
| `g_hist_vrel[]` (L458) | double[] | histórico de volume relativo desde o início do contrato | `LimiteVolume` L511-538 | (b) (reconstrói do zero no 1º `LimiteVolume`, caro: itera todas as velas H2 do contrato, cada uma com `VolRel` que copia 800 barras) |
| `g_hist_inicio`, `g_hist_ultima` (L459-460) | datetime | marcos do histórico | idem | (b) |
| `g_usa_real` (L461) | bool | volume real vs tick | `InitBase` L242-244 | (b) |
| `g_gap_dia_avaliado`, `g_gap_bloqueado` (L122-123) | long/bool | Z8 | `GapDiaBloqueado` | (b) |
| `dia_cache`, `val_cache` (static, L689-690) | - | horário de zeragem do dia | `MinutoZerarHoje` | (c) |
| `trade`, `TempoGrafico`, `TempoSupertrend`, inputs | - | - | - | (c) |
- Nada além de `g_ultima_barra` precisa ir para disco para o robô "continuar igual"; o resto é recalculado. Para o maestro: ficha (lado, preço de entrada médio do robô, hora de entrada, volume, `a_favor`, SL virtual do stop que aperta) + ordem virtual pendente (id, lado, preço, hora de colocação, flag `a_favor`) + `g_ultima_barra`.

### 2.4 Reinício
- **Com posição:** `g_ultima_barra=0` => o 1º tick dispara a lógica de "vela nova" (L726-728) com a vela corrente. Saída: decidida de novo pela mesma vela fechada (equivalente). `g_a_favor` volta pelo comentário/histórico (L419-435). Stop que aperta é recalculado dos dados (L552). Zeragem por horário e `de_outro_dia` operam antes do gate de vela (L719-724), com a posição real.
- **Perde (risco):** a regra "a vela da saída não gera entrada nova" (L754 `return` depois da saída) depende de `g_ultima_barra`; se o EA reinicia na mesma vela depois de uma saída (ou depois de o SL do servidor ter sido atingido na vela), `g_ultima_barra=0` re-roda a vela e pode **reentrar na mesma vela** (passos 2 e 3, L757-778) se não há posição nem ordem e o alinhamento persiste. Também reavalia entrada se o robô tinha sido bloqueado pelo gap (recalculado igual).
- **Ordem pendente:** `OrdemPendente` acha por magic; validade usa `ORDER_TIME_SETUP` do servidor, então é restart-safe. `Deinit` não cancela nada (L803-807).
- **Reconstrução do histórico de volume** no 1º `LimiteVolume`: pesado e pode atrasar o tick (tarefa a distribuir/limitar no maestro).

### 2.5 Horários / outro dia
- `MinutoZerarHoje` L687-709 = min(`HoraZerar:MinutoZerar` = 18:24, fim da sessão do dia lido por `SymbolInfoSessionTrade` - 1 min); cache por dia.
- `ultima` = 18:20 (L717): vela cuja abertura >= 18:20 gera saída "horário" (L742) e proíbe entrada (L773). Observação: com H2 (velas abrindo em horas pares, última 18:00) esse teste de abertura nunca dispara; a zeragem real é o 18:24.
- Zeragem a mercado em todo tick: `agora >= zerar || de_outro_dia` (L720-724), antes do gate de vela. `de_outro_dia` = `Dia(TimeCurrent()) != Dia(POSITION_TIME)` (L722).
- Entradas pendentes: canceladas na virada (`!mesmo_dia || Dia(colocada) != Dia(barra)`, L764), por `ValidadeVelas`=5 velas H2 (L765) ou se o alinhamento sumir (L766). A ordem é `ORDER_TIME_DAY`.

### 2.6 Saldo/patrimônio
- Nenhum. Lote fixo `CM_Lote`.

### 2.7 Outros pontos
- `AFavorDoMes` depende de `POSITION_COMMENT`/`POSITION_IDENTIFIER`/histórico da posição: em netting o comentário/identificador são da posição líquida (não do robô); se o robô é adicionado por outro, devolve o comentário errado. Com ficha, `a_favor` passa a vir da ficha.
- `POSITION_TIME` (L580, 722) em netting é a hora de abertura da posição líquida, não da ficha do robô.
- `PositionClose(_Symbol)` e `PositionModify(_Symbol, ...)` agem na líquida inteira.
- `PositionSelect(_Symbol)` L774 e L272 e L433: três pontos que dependem de haver UMA posição por símbolo.
- `OrdemPendente` devolve só a 1ª ordem do magic: se o maestro permitir 2 ordens por robô, ela vê só uma.
- `HistorySelectByPosition` (L425) altera o pool global de histórico.

---------------------------------------------------------------------

## 3. WinDeslocamentoMatinal.mqh (WDM)

### 3.1 Leituras de posição
| Linha | O quê | Quer saber |
|---|---|---|
| 265-275 `MinhaPosicao` | `PositionSelect(_Symbol)`; magic == `MagicNumber`; `POSITION_PRICE_OPEN` (269), `POSITION_TYPE` (270), `POSITION_SL` (271), `POSITION_TP` (272), `POSITION_TICKET` (273) | posição minha, preço de entrada, lado, SL, TP, ticket |
| 428 `AjustarStop`, 445 `VerificarStop`, 462 `Zerar` | usam `MinhaPosicao` | idem |
| 535 (`Init`) | `PositionGetInteger(POSITION_TIME) >= d0` após `MinhaPosicao` | a posição foi aberta hoje? (evita zerá-la como "pregão anterior" ao religar) |
| 277-282 `OrdemPendenteViva` | `OrderSelect(g_ordem)` por TICKET guardado em memória (não varre por magic) | a ordem de entrada ainda está viva? |
- **BLOQUEIO por posição de outro robô:** L379 `if(PositionSelect(_Symbol)) { Print("Ja' existe posicao no simbolo: nao entra"); return; }` (executado na decisão das 10:30).
- Fechamentos: por TICKET (L453 `PositionClose(ticket)` em `VerificarStop`; L463 `PositionClose(ticket)` em `Zerar`). O ticket é o da posição líquida do símbolo -> em netting fecha a posição INTEIRA.

### 3.2 Ordens
| Linha | Operação | Tipo / validade / comentário | Stop |
|---|---|---|---|
| 410 / 411 | `BuyLimit` / `SellLimit` `Lote` (DM_Lote 1.0) em `limite` = último fechamento M1 ajustado ao livro (L385-388) | `ORDER_TIME_DAY`, comentários `"desloc_matinal_compra"` / `"desloc_matinal_venda"`; sem SL/TP (L410-411) | stop calculado só em memória (L390-407) |
| 417 | `g_ordem = trade.ResultOrder()` | ticket guardado | - |
| 287 `CancelarEntrada` | `OrderDelete(g_ordem)` | chamadas: `NovoDia` L296, TTL 15 min L486-487, fim do pregão L492, `DeinitBase` L506 ("EA removido") | - |
| 437 | `PositionModify(ticket, g_stopNivel, tp)` | **SL no servidor como reserva** (só fora do Testador, `!MQLInfoInteger(MQL_TESTER)`) | servidor (reserva) |
| 453 | `PositionClose(ticket)` | stop por último negócio | **stop controlado pelo EA** |
| 463 | `PositionClose(ticket)` | zeragem | - |
- **Stop real: controlado pelo EA** (`g_stopNivel`, `VerificarStop` L442-457, a cada tick: fecha a mercado quando `last` cruza o nível; sem `last`, usa bid/ask). O SL do servidor (L437) é só rede de segurança, no mesmo nível. Nível = preço executado -/+ `g_distStop` (L432), com `g_distStop` = distância limite->linha da abertura, apertada pelo teto de risco (L390-406).

### 3.3 Estado em memória
| Variável | Tipo | Significado | Muda | Classe |
|---|---|---|---|---|
| `g_dia` (L66) | datetime | D1 do pregão corrente | `NovoDia` L297; `Init` L535 | (b), mas ver 3.4 |
| `g_decidiu` (L67) | bool | decisão do dia já tomada | L347 (Decidir); zera `NovoDia` | **(a)** |
| `g_ordem` (L68) | ulong | ticket da limite de entrada | L417; zera L291/L299/L430 | **(a)** |
| `g_ordemHora` (L69) | datetime | hora de envio (TTL 15 min) | L418 | **(a)** |
| `g_ordemPreco` (L70) | double | preço da limite (só log) | L419 | (a) fraco (informativo) |
| `g_distStop` (L71) | double | distância limite->stop; reancora no preço executado | L390-406 | **(a) crítico** |
| `g_stopAjustado` (L72) | bool | stop já ancorado ao preço de fill | L429 | **(a)** |
| `g_stopNivel` (L73) | double | nível do stop controlado pelo EA | L432 | **(a) crítico** |
| `g_ultimaM1` (L74) | datetime | última M1 processada (gate de decisão) | L500 | (b) |
| `g_hEma10/100` (L75-76) | handles | iMA M5 (só se FiltroMM) | Init | (c) |
| `g_gap_*` (L101-102) | - | Z8 | - | (b) |
- Para o maestro (a) completo: ficha (lado, preço de fill do robô, volume), `g_stopNivel`, `g_distStop`, `g_stopAjustado`, `g_decidiu`, `g_dia`, ordem virtual (id, preço, hora de envio, lado).

### 3.4 Reinício
- `Reseta` (L515-521) zera tudo. `Init` (L529-536) só trata UM caso: posição deste magic aberta HOJE -> `g_dia = d0`, para o primeiro tick não cair no ramo "pregão novo" e zerar a posição (L476-479).
- **Perde com posição aberta:**
  - `g_stopNivel=0`, `g_distStop=0`, `g_stopAjustado=false`: no 1º tick `AjustarStop` (L425-439) vê posição, marca `g_stopAjustado=true`, e como `g_distStop<=0` dá `return` (L431) sem nunca criar `g_stopNivel`. `VerificarStop` exige `g_stopNivel>0` (L445), então **o stop controlado pelo EA deixa de existir**. Só sobrevive o SL do servidor (L437), e só se ele já tinha sido colocado (ou seja, se a queda foi depois do 1º tick pós-fill). Se a queda foi entre o fill e o 1º `AjustarStop`, a posição fica **sem stop nenhum**.
  - `g_decidiu=false`: dentro da janela 10:30-10:35, `Decidir` roda de novo e pode enviar 2ª ordem (a decisão depende só das barras, que são iguais); após a janela, `Decidir` marca `g_decidiu=true` e "dia em branco".
  - Ordem pendente: `g_ordem=0` -> a ordem viva fica ÓRFÃ (não é encontrada por magic; `CancelarEntrada` e TTL não a enxergam). Se a EA caiu sem `Deinit` (queda/crash), a órfã pode encher depois, sem `g_distStop` -> **posição sem stop**. Em `Deinit` normal (remoção, troca de parâmetro, fechamento do terminal) `DeinitBase` L506 cancela a ordem viva, mas aí `g_decidiu` volta a false (pode reentrar na janela).
  - Se só há ordem pendente (sem posição) ao religar: `g_dia=0`, o 1º tick faz `NovoDia`, que chama `CancelarEntrada` com `g_ordem=0` -> não cancela.
- O que já trata: posição de dia anterior é zerada (L476-479); stop de reserva no servidor (L437); `Init` L529-536.

### 3.5 Horários / outro dia
- Decisão: `MinutosDecisao`=90 min após a 1ª M1 do dia (10:30 com abertura 09:00); janela `JanelaDecisaoMin`=5 min (L346-352), depois "dia em branco".
- Fim: `FimSessao` L250-263 (fim da sessão lido de `SymbolInfoSessionTrade`, senão `HoraFimPregao:MinutoFimPregao` = 18:25); zera `MinutosZerar`=5 min antes (L490-495): cancela pendente, `Zerar`, e `return` (nada de decisão depois).
- Outro dia: `iTime(D1,0) != g_dia` -> `Zerar("posicao de pregao anterior")` + `NovoDia` (L476-480): "nunca carrega overnight". Sem posição de outro dia na ficha o maestro deve manter essa regra por data da ficha.
- TTL da entrada: `agora - g_ordemHora >= EntradaTTLMin*60` (L486-487).

### 3.6 Saldo/patrimônio
- **L396 `AccountInfoDouble(ACCOUNT_BALANCE)`**: `tetoRs = RiscoMaxPct/100 * saldo` (L397) define o teto do stop (L398-406). Em conta compartilhada o saldo é de todos os robôs; precisa virar o capital alocado ao robô (ou saldo virtual do robô). Mudou de significado: com 5 robôs, 10% de uma conta única é um teto diferente do original. Também L394-395 `SYMBOL_TRADE_TICK_VALUE` (R$ por ponto).

### 3.7 Outros pontos
- `PositionClose(ticket)` fecha a líquida inteira (L453, 463).
- `PositionModify(ticket, g_stopNivel, tp)` (L437) põe SL no servidor na posição líquida (afetaria os outros robôs).
- `MinhaPosicao` devolve `PRICE_OPEN` da líquida: `g_stopNivel` (L432) derivado do preço médio.
- Em netting, a ordem do WDM, quando preenche com outra posição no símbolo, se funde; o `PositionSelect(_Symbol)`+magic pode devolver false (magic do dono da posição) e o robô nunca vê o próprio fill -> `AjustarStop` nunca roda e `g_ordem` fica no ar.
- `OrderSelect(g_ordem)` (L280) usa o ticket guardado; se a ordem foi preenchida/cancelada, `g_ordem=0`.

---------------------------------------------------------------------

## 4. WinRetanguloEma34.mqh (WRE)

### 4.1 Leituras de posição
| Linha | O quê | Quer saber |
|---|---|---|
| 493-496 `TemPosicaoPropria` | `PositionSelect(_Symbol) && POSITION_MAGIC == MagicNumber` | tem posição minha? Chamada em L808 (fill), L848 (aproximar alvo), L873 (órfão), L883 (zerar), L947 (barra fechada) |
| 810 | `PositionGetDouble(POSITION_PRICE_OPEN)` | preço do fill, para reancorar stop e alvo (delta contra `g_meio_original`) |
| 856 | `PositionGetInteger(POSITION_TYPE)` | comprado? (direção do alvo que se aproxima) |
| 643, 854, 874, 881 | `OrderSelect(ticket)` | a ordem (entrada ou alvo) ainda existe? |
- Não tem o padrão "if(PositionSelect(_Symbol)) return" para bloquear sinal; `TemPosicaoPropria` falso quando há posição de outro robô, então o EA continua armando entradas. A consequência (fill nunca detectado) é mais grave que o bloqueio (ver 4.7).
- Fecha posição INTEIRA: L883 `trade.PositionClose(_Symbol)` (em `ZerarPregao`, protegido só por `TemPosicaoPropria()`).
- Não lê `POSITION_SL/TP/TIME/COMMENT/IDENTIFIER/TICKET`.

### 4.2 Ordens
| Linha | Operação | Tipo / validade / comentário | Stop |
|---|---|---|---|
| 788 / 789 `ArmarEntrada` | `SellLimit` / `BuyLimit` `Lote`=1.0 em `NoTick(meio)` (L990) | `ORDER_TIME_GTC`, `"win_retangulo_ema34 entrada"`; sem SL/TP; cancelada pelo EA por TTL = `TtlBarrasEntrada` (10) velas M15 | - |
| 796 | `g_ticket_entrada = trade.ResultOrder()` | ticket em memória | - |
| 815 | `PositionModify(_Symbol, stop_ancorado, 0.0)` ao detectar o fill | **SL nativo no servidor** (único stop); passa tp=0.0 | servidor |
| 820 / 821 | `SellLimit` / `BuyLimit` do alvo em `alvo_ancorado`, `Lote` | `ORDER_TIME_GTC`, `"win_retangulo_ema34 alvo"`; ticket em `g_ticket_alvo` (L822) | - |
| 863 | `OrderModify(g_ticket_alvo, preco, 0.0, 0.0, ORDER_TIME_GTC, 0)` | alvo que se aproxima (G37): a cada `AlvoAproximaBarras`=5 velas, `frac = max(0,90 - 0,10*passos, 0,50)` da largura; se o preço já passou, vai ao melhor preço do lado (bid/ask), continua limite | - |
| 644 `CancelarEntradaPendente` | `OrderDelete(g_ticket_entrada)` | chamadas: `ResetSessao` L657, retângulo morreu L937, TTL L953, `ZerarPregao` L880, `Deinit` L1060 | - |
| 874 (`LimparAlvoOrfao`), 881 (`ZerarPregao`) | `OrderDelete(g_ticket_alvo)` | alvo órfão (sem posição) e zeragem | - |
| 883 | `PositionClose(_Symbol)` | zeragem 17:00 | - |
- **Stop = servidor** (SL nativo, ancorado ao preço de fill). Nenhum stop próprio do EA.

### 4.3 Estado em memória
| Variável | Tipo | Significado | Muda | Classe |
|---|---|---|---|---|
| `g_dia_atual` (L100) | datetime | pregão corrente da vela processada | L907 | (b) |
| `g_handle_ema` (L101) | handle | iMA M15 | Init | (c) |
| `g_high_dia[]`, `g_low_dia[]`, `g_close_dia[]`, `g_time_dia[]` (L104-105) | arrays | histórico de velas válidas (até 3*Janela), atravessa pregões | `AcrescentarBarraDia` L661-686 | (b) (reconstruído por `CarregarHistorico`, 600 velas M15) |
| `g_tem_retangulo`, `g_topo`, `g_piso`, `g_largura`, `g_meio` (L108-109) | bool/double | retângulo ativo | `TentaDetectar` L763-766; zera L935/L655/L885 | **(a)** parcial (ver 4.4: redetecção não reproduz o mesmo retângulo/estado) |
| `g_retangulo_inicio_ts` (L110) | datetime | só desenho | L764 | (c) |
| `g_fora_seguidas` (L111) | int | velas seguidas fora da margem (morte aos 3) | `Morreu` L769-779 | **(a)** |
| `g_ordem_pendente` (L118) | bool | há entrada pendente | L797; zera L645/L833 | **(a)** |
| `g_ticket_entrada` (L119) | ulong | ticket da limite de entrada | L796 | **(a)** |
| `g_barras_esperando` (L120) | int | velas M15 esperando o fill (TTL) | L798/L951 | **(a)** |
| `g_lado_entrada` (L121) | enum | lado | L799 | **(a)** |
| `g_meio_original`, `g_stop_original`, `g_alvo_original` (L122) | double | referências para reancorar no fill (delta = fill - meio) | L800-802 | **(a)** |
| `g_ticket_alvo` (L125) | ulong | ticket da limite do alvo | L822 | **(a) crítico** |
| `g_preco_entrada` (L128) | double | preço de fill | L827 | **(a) crítico** |
| `g_largura_posicao` (L128) | double | largura do retângulo que originou a posição (passo do alvo) | L828 | **(a) crítico** |
| `g_frac_alvo_atual` (L128) | double | fração atual do alvo | L829, 864 | **(a) crítico** |
| `g_barra_do_fill` (L129) | datetime | vela do fill (conta velas depois dela) | L830 | **(a)** |
| `g_barras_posicao` (L130) | int | velas fechadas desde o fill (define o passo do alvo) | L831, 850 | **(a)** |
| `g_historico_carregado` (L133) | bool | pré-carga feita | L696 | (b) |
| `g_ultima_vela_processada` (L137) | datetime | última vela processada | L895 | (b)/(a) fraco |
| `g_atr_dia`, `g_atr_d1`, `g_atr_ok` (L138-140) | cache ATR14 D1 do filtro f3 | `AtrD1Anterior` | (c) |
| `g_nb_ultima` (L476) | datetime | última vela M15 (IsNewBar) | L482 | (b) |
| `g_gap_*` (L309-310) | - | Z8 | - | (b) |
| `static dia_semana_cache`, `fim_cache` (L187) | - | fim da sessão | - | (c) |
| objetos de gráfico `WinRetEma_Caixa/Meio` | - | desenho | - | (c) |

### 4.4 Reinício
- `Reseta` (L1032-1045) zera tudo. `Deinit` cancela a entrada pendente (L1060, comentário L1059: "o estado da entrada pendente não sobrevive a um reinício; sem cancelar, a ordem órfã encheria depois SEM stop nem alvo"). Em crash (sem `Deinit`) a ordem GTC fica órfã e pode encher sem stop/alvo.
- **Com posição aberta:** perde `g_ticket_alvo`, `g_preco_entrada`, `g_largura_posicao`, `g_frac_alvo_atual`, `g_barra_do_fill`, `g_barras_posicao`. Efeitos:
  - `AproximarAlvo` (L847) e `LimparAlvoOrfao` (L872) retornam logo (`g_ticket_alvo==0`): **o alvo deixa de se aproximar** (continua no preço da última modificação no servidor).
  - **A ordem do alvo fica órfã no livro (GTC)**: quando a posição fecha por stop do servidor, ela não é apagada (não é encontrada), podendo abrir posição NOVA oposta; e `ZerarPregao` (L881) também não a apaga, então **sobrevive à noite** (GTC).
  - O SL do servidor (L815) permanece.
  - Se a queda foi entre o envio da entrada e a detecção do fill: sem `g_ordem_pendente`, `DetectarPreenchimentoEntrada` (L807) nunca roda -> posição sem SL e sem alvo.
- Retângulo: `g_tem_retangulo=false` e `g_fora_seguidas=0` -> o 1º `ProcessarBarraFechada` recarrega o histórico (600 velas) e `TentaDetectar` pode achar outro retângulo (a janela mudou) ou nenhum; a "morte" do retângulo e o contador de fora-seguidas não são reproduzíveis do histórico.
- A reprocessagem da vela atual no 1º tick é segura (histórico só com velas anteriores, L702); `g_ultima_vela_processada` evita processar vela pós-pregão repetida.
- O que já trata: `Deinit` cancela entrada pendente; pré-carga de histórico (v1.05); sobrevive de graça o SL e o alvo no servidor.

### 4.5 Horários / outro dia
- Zeragem: `HoraZerar:MinutoZerar` = 17:00 (L1019-1023): **só é avaliada a cada vela M15 nova** (a checagem vem depois de `if(!IsNewBar()) return;`, L1016-1019). Se `PositionClose` falhar, só tenta de novo 15 min depois; se o EA começar depois das 17:00, no 1º tick novo zera.
- Corte de entrada: `CorteEntradaMinutos` = min((TTL+1)*15, 60) = 60 min antes da zeragem (L988) = 16:00.
- Começo: `HoraInicio:MinutoInicio` = 09:01; velas com abertura antes disso são descartadas (leilão, L919). Velas pós-pregão: `FimSessaoMinutos` (L185-207), `VelaParaProcessar` (L713-730).
- Posição de outro dia: **não há regra**. `ResetSessao` (virada de dia, L905-909) cancela só a entrada pendente (e apaga desenho); não cancela o alvo nem zera posição. Posição que sobreviveu à zeragem (EA desligado às 17:00) só é zerada às 17:00 do dia seguinte e fica com o SL servidor entre os dias; a ordem do alvo (GTC) sobrevive.
- A entrada GTC só é cancelada pelo EA (TTL L953, retângulo morto L937, virada L908 via `ResetSessao`, zeragem L880).

### 4.6 Saldo/patrimônio
- L1007 `AccountInfoDouble(ACCOUNT_EQUITY) <= LimiteEquity` apenas dentro de `MQLInfoInteger(MQL_TESTER)` (para o teste e `TesterStop()`). Em produção não é usado. `Lote` fixo (RE_Lote=1.0).

### 4.7 Outros pontos que quebram em netting compartilhado
- **Detecção de fill** (L805-836): considera "fill" quando `g_ordem_pendente && TemPosicaoPropria()`: não confere o ticket nem o deal. Com outra posição de magic diferente já aberta no símbolo, o fill do WRE funde na líquida e `POSITION_MAGIC` continua sendo o do dono -> `TemPosicaoPropria()` falso -> **o fill nunca é detectado (sem SL, sem alvo)**. Se a líquida for do próprio magic, o `PRICE_OPEN` lido (L810) é o preço médio, não o fill do robô, e o delta de reancoragem fica errado.
- `PositionModify(_Symbol, stop_ancorado, 0.0)` (L815): SL na líquida inteira (afeta os outros robôs; tp zerado).
- `PositionClose(_Symbol)` (L883): fecha tudo, não só a ficha.
- `Lote` e volume do alvo = `Lote`, não o volume da ficha.
- A ordem do alvo (limite oposta GTC) em netting também pode inverter/abrir líquida quando a posição do robô já foi fechada por outra via.
- Retângulo/histórico são por símbolo e independem de posição (ok).

---------------------------------------------------------------------

## 5. Win_c1.mqh (WC1)

### 5.1 Leituras de posição
| Linha | O quê | Quer saber |
|---|---|---|
| 301-305 `SelecionaPosicao` | `PositionSelect(_Symbol)` + magic == `MagicNumber` | posição minha? (chamada L586 e L607) |
| 510 | `POSITION_TYPE` | lado (`compra`) |
| 515 | `POSITION_TICKET` | identifica posição nova/reiniciada (`g_ticket_pos`) |
| 523 | `POSITION_TIME` | vela de entrada (rebuild do pico de afastamento via `iBarShift`) |
| 548 | `POSITION_SL` | SL atual (só move se mudou mais de meio tick) |
| 566 | `POSITION_TIME` | vela H1 de entrada para o prazo do break-even (`BreakEvenMinutos`=15) |
| 569, 571 | `POSITION_TYPE`, `POSITION_PRICE_OPEN` | lado e preço de entrada (pontos a favor) |
| 591 | `POSITION_TIME` | posição de outro dia: `(long)(TimeCurrent()/86400) != (long)(POSITION_TIME/86400)` |
- **BLOQUEIO por posição de outro robô:** L620 `if(PositionSelect(_Symbol)) return;  // posição de outro robô/magic no símbolo: não mexe`.
- **Fecha posição INTEIRA:** `trade.PositionClose(_Symbol)` em L505 (vela fechou entre roxa e verde), L530 (esticada), L543 (stop alcançado: preço já passou do novo stop), L575 (break-even a mercado), L594 (zeragem 17:50 / outro dia).

### 5.2 Ordens
| Linha | Operação | Tipo / validade / comentário | Stop |
|---|---|---|---|
| 489 / 490 `Entra` | `trade.Buy(Lote, _Symbol, 0.0, sl, 0.0, "win")` / `trade.Sell(...)` | **ORDEM A MERCADO** (preço 0.0 = mercado; sem validade), comentário `"win"` | **SL anexado na ordem** = `roxa +/- K*ATR` (L480) -> servidor |
| 549 | `PositionModify(_Symbol, novo, 0.0)` a cada vela H1 fechada | SL na roxa +/- K*ATR (trailing no servidor); passa tp=0.0 | servidor |
| 505, 530, 543, 575, 594 | `PositionClose(_Symbol)` | mercado | - |
- Não envia nenhuma ordem pendente.
- Stop = **servidor** (SL anexado na entrada e re-posicionado por `PositionModify` a cada H1). O EA fecha a mercado só quando o preço já passou do nível novo (L541-546) ou por saídas de sinal (canal, esticada, break-even).

### 5.3 Estado em memória
| Variável | Tipo | Significado | Muda | Classe |
|---|---|---|---|---|
| `g_h_smma/wma/smma15/wma15` (L91-94) | handles | iMA H1/H3 | Init | (c) |
| `g_ultima_barra` (L95) | datetime | última vela H1 vista (gate de vela nova) | L601-602 | (b)/(a) (mesmo efeito de WCM, ver 5.4) |
| `g_ultima_m1` (L96) | datetime | última M1 checada pelo break-even | L562-563 | (b) |
| `g_hora_bloqueada[24]` (L97) | bool[] | horas sem entrada (do input `HorasSemEntrada`) | `InitBase` L239-256 | (c) |
| `g_ticket_pos` (L100) | ulong | ticket da posição cujo estado de esticada está em memória | L516-519 | (b) (reconstruído) |
| `g_esticada_armada` (L101) | bool | saída por esticada armada | L344, 520 | (b) (reconstruído desde a entrada, L516-526) |
| `g_pico_afastamento` (L102) | double | maior afastamento da roxa desde a entrada | L345, 521 | (b) (reconstruído) |
| `g_gap_*` (L127-128) | - | Z8 | - | (b) |
- A esticada e o pico são recalculados das barras desde `POSITION_TIME`; a premissa do código: "estado recalculado do zero a cada vela, um reinício não perde nada" (L496-497, 555-557). Na ficha, o `ticket` passa a ser id da ficha e `POSITION_TIME` o horário de abertura da ficha (necessários para a reconstrução).

### 5.4 Reinício
- Com posição: `g_ultima_barra=0` -> no 1º tick `nova_barra` é true e `AtualizaPosicao` roda (L606), reconstruindo o pico (ticket != g_ticket_pos). O break-even sem estado roda por M1 (L561-577). Tudo reproduz com a posição real.
- O que se perde: o gate de vela nova (mesmo problema do WCM): se a posição foi encerrada nesta vela e o EA reinicia na mesma vela, no ramo sem posição `nova_barra` é true e `Sinal()` (vela 1 igual) pode **reentrar na mesma vela H1** (L610-629). Sem posição no momento da queda, nada mais é perdido.
- O SL do servidor persiste. O que já trata: zera outro dia (L591-597); estado reconstruído.

### 5.5 Horários / outro dia
- Fim do pregão `HoraFimPregao:MinutoFimPregao` = 18:00 (L583). Zera a partir de `fim - MinutosZerar` = 17:50 (L592); sem entrada nos últimos `MinutosSemEntrada` = 30 min (17:30, L618); horas bloqueadas "11,15,16,17" (L182, 619).
- Posição de outro dia: `de_outro_dia` L591 (por data do `POSITION_TIME`) -> fecha a mercado, e `return`.
- Sinal velho: se a vela fechada (shift 1) é de outro dia, não opera (L614).

### 5.6 Saldo/patrimônio
- Nenhum uso de `ACCOUNT_*` (comentário L285 diz que o diagnóstico de equity do .mq5 original não foi portado). `Lote` fixo.

### 5.7 Outros pontos
- Único robô que entra **a mercado** (L489-490): slippage, preço de fill real; o preço de entrada da ficha deve vir do deal.
- `PositionModify(_Symbol, ...)` por vela mexe no SL da posição líquida inteira; `PositionClose(_Symbol)` (5 pontos) fecha tudo; `POSITION_TIME`/`PRICE_OPEN`/`POSITION_TICKET`/`POSITION_SL` da líquida em netting = dados misturados (break-even, esticada, trailing, outro dia, todos baseados neles).
- Break-even a mercado usa `PRICE_OPEN` e `POSITION_TIME` (L566-571).
- `L620` bloqueia entrada se QUALQUER posição (de qualquer robô) existe.

---------------------------------------------------------------------

## 6. Mapa transversal das APIs a trocar

| API real hoje | Onde | Substituto na camada de fichas |
|---|---|---|
| `PositionSelect(_Symbol)` + magic | WCM 272, 433, 774; WDM 267, 379; WRE 495; WC1 303, 620 | `Ficha(robo).Existe()`; os 3 bloqueios (WCM 774, WDM 379, WC1 620) passam a olhar só a ficha do robô |
| `PositionsTotal/PositionGetTicket` por magic | Comum 12-19; WGB1 168-179 | ficha |
| `PositionGet{Type,PriceOpen,Volume,Time,Sl,Tp,Ticket,Comment,Identifier}` | WGB1 175-177; WCM 421-424, 580-581, 600, 609, 722, 738; WDM 269-273, 535; WRE 810, 856; WC1 510, 515, 523, 548, 566-571, 591 | campos da ficha (lado, preço médio do robô, volume do robô, hora de abertura, SL virtual, TP virtual, id, flag do comentário) |
| `HistorySelectByPosition` + `HistoryOrderGetString` | WCM 425-431 | flag `a_favor` guardada na ficha |
| `trade.PositionClose(_Symbol)` / `(ticket)` | WCM 440; WDM 453, 463; WRE 883; WC1 505, 530, 543, 575, 594; WGB1 221 | ordem a mercado de fechamento só da ficha (volume da ficha, lado contrário, magic do robô) |
| `trade.PositionModify` (SL no servidor) | WGB1 247; WCM 609; WDM 437; WRE 815; WC1 549 | atualizar SL virtual na ficha (e o maestro faz o stop; stop no servidor por robô não existe em netting) |
| SL anexado em ordem de entrada | WGB1 330-337; WC1 489-490 | SL virtual na ficha |
| `trade.Buy/Sell` a mercado | WC1 489-490 | envio do maestro com magic do robô |
| `trade.BuyLimit/SellLimit` entrada | WGB1 330/331/336/337; WCM 677/678; WDM 410/411; WRE 788/789 | ordem virtual + envio com magic do robô; mapear fill por `DEAL_ORDER`/`DEAL_MAGIC` |
| `trade.BuyLimit/SellLimit` alvo | WGB1 235/237; WRE 820/821 | idem (ordem de alvo do robô) |
| `trade.OrderModify` | WRE 863 | modificar ordem virtual/real |
| `trade.OrderDelete` | WGB1 195; WCM 447; WDM 287; WRE 644, 874, 881 | cancelar ordem virtual/real |
| `OrderSelect(ticket)` / loop `OrdersTotal` por magic | WCM 277-288; WDM 280; WRE 643, 854, 874, 881; WGB1 187-197 | consulta à ordem virtual |
| `ACCOUNT_BALANCE` | WDM 396 | capital do robô |

---------------------------------------------------------------------

## 7. Tabela-resumo por módulo

| Módulo | Nº de pontos a trocar* | Estado a persistir | Riscos principais |
|---|---|---|---|
| WGB1 | 7 (leitura de posição, varredura de ordens por magic+comentário, entrada limite com SL anexado x2 (SPECIFIED e DAY), alvo limite, PositionModify do BE, PositionClose) | `g_decidido`, `g_exp`, `g_be_feito`, dia, ordem de entrada (id/preço/lado), ordem do alvo, ficha (lado/preço/volume/SL virtual) | duplicar entrada ao reiniciar (g_decidido zera e AvaliaSinal não vê a ordem viva); SL anexado vira SL da líquida; alvo/BE usam `PRICE_OPEN`/volume da líquida; sem regra de posição de outro dia |
| WCM | 11 (`SelecionaPosicao`, `OrdemPendente`, `AFavorDoMes` com comentário/identificador/histórico, `Fecha` x3 chamadas, `Cancela` x3, leituras de POSITION_TIME/PRICE_OPEN/SL/TP, bloqueio L774, `Entra`, `PositionModify`) | `g_ultima_barra`, ficha (lado, preço, hora de entrada, `a_favor`, SL do stop que aperta), ordem virtual (lado, preço, hora, `a_favor`) | reentrada na mesma vela após reinício; `a_favor` por comentário da líquida; `PositionClose(_Symbol)` fecha tudo; reconstrução pesada do histórico de volume; bloqueio L774 por posição de outro robô |
| WDM | 10 (`MinhaPosicao`, `OrdemPendenteViva`, bloqueio L379, `BuyLimit/SellLimit` L410-411, `ACCOUNT_BALANCE` L396, `PositionModify` L437, `PositionClose` x2, `CancelarEntrada`, `Init` L535) | `g_decidiu`, `g_dia`, `g_ordem`, `g_ordemHora`, `g_ordemPreco`, `g_distStop`, `g_stopAjustado`, `g_stopNivel`, ficha | stop controlado pelo EA perdido no reinício (só sobra o SL servidor, ou nada se a queda foi antes do 1º ajuste); ordem de entrada órfã que enche sem stop; `ACCOUNT_BALANCE` compartilhado; stop por último negócio precisa existir por robô |
| WRE | 11 (`TemPosicaoPropria`, leitura do fill `PRICE_OPEN`, `PositionModify` stop, alvo limite, entrada limite, `OrderModify`, `OrderDelete` x3, `PositionClose`, leitura `POSITION_TYPE`, equity no Testador) | todo o bloco de entrada pendente (ticket, barras esperando, lado, meio/stop/alvo originais), todo o bloco da posição (ticket alvo, preço de entrada, largura, fração do alvo, vela do fill, barras da posição), retângulo (topo/piso/largura/meio/fora seguidas/início) | fill nunca detectado quando há posição de outro magic; alvo órfão GTC sobrevive à noite; alvo deixa de se aproximar após reinício; entrada GTC órfã sem stop em crash; zeragem só a cada vela M15; sem regra de outro dia |
| WC1 | 10 (`SelecionaPosicao`, bloqueio L620, `Buy/Sell` a mercado com SL, `PositionModify` por H1, `PositionClose` x5, leituras de TIME/PRICE_OPEN/SL/TICKET) | `g_ultima_barra`, ficha (lado, preço, hora de abertura, id, SL virtual); `g_esticada_armada`/`g_pico_afastamento` reconstruíveis desde a hora da ficha | única entrada a mercado (preço de fill real); trailing de SL por vela vira stop virtual; reentrada na mesma vela após reinício; `PositionClose(_Symbol)` x5 fecha tudo; `POSITION_TIME` da líquida |
| Comum / Seletor | 1 (`WinTemPosOuOrdens`) + remoção de `g_ativo/g_troca_pendente/SoGerir` | GlobalVariable do ativo deixa de ser necessária | - |

\* Pontos contados como grupos de chamadas que precisam passar pela camada de fichas (uma função com vários call sites conta 1).

### Riscos transversais
1. Netting: `PositionClose(_Symbol)`/`PositionClose(ticket)` fecha a posição líquida de todos os robôs (14 call sites: WGB1 1, WCM 1 função/3 chamadas, WDM 2, WRE 1, WC1 5).
2. SL no servidor: sempre da posição líquida (WGB1 247/330-337, WCM 609, WDM 437, WRE 815, WC1 489-490/549). Perde sentido por robô: vira stop virtual executado pelo maestro (para WDM já é assim, com o SL servidor só como reserva).
3. `POSITION_TIME`, `PRICE_OPEN`, `VOLUME`, `COMMENT`, `IDENTIFIER`, `TICKET`, `MAGIC` da líquida não pertencem a nenhum robô: a ficha tem que guardar os próprios.
4. `POSITION_MAGIC` em netting acompanha o dono da posição; fills de outro robô que fundem na líquida fazem `PositionSelect(_Symbol)+magic` dar false (WDM, WCM, WRE, WC1) -> fill/posição "invisíveis" ao robô.
5. Ordens limite de alvo (WGB1 235/237, WRE 820/821) reduzem a líquida; sem a ficha correspondente, podem abrir posição nova oposta.
6. Reinício: WDM perde stop e ordem; WRE perde alvo e passo; WGB1 duplica entrada; WCM/WC1 podem reentrar na mesma vela; WRE/WGB1 podem deixar ordens GTC/DAY órfãs.
7. Conta: só WDM L396 (`ACCOUNT_BALANCE`, teto de risco 10%); WRE L1007 `ACCOUNT_EQUITY` (só Testador).
8. Rodar 5 módulos no mesmo `OnTick`: cada `Tick()` faz `CopyRates` próprios (WCM carrega 800 barras por vela em `VolRel`; WRE `CarregarHistorico` 600 velas; Z8 copia 45 dias de M1 em 4 módulos); o 1º tick pode demorar.
9. Horário de zeragem por módulo (todos em horário de servidor): WGB1 18:20 (ou 17:50 no regime antigo), WCM 18:24 (ou fim da sessão - 1 min), WDM fim da sessão - 5 min (18:20 com sessão até 18:25), WRE 17:00 (checado por vela M15), WC1 17:50. Não há zeragem coordenada: com 5 robôs na líquida, a ordem de fechamento deixa a posição líquida passando por vários estados.
