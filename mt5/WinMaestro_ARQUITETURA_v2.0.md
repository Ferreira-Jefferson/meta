# WinMaestro v2 — arquitetura do núcleo de execução

Desenho para implementar. Substitui `Fichas.mqh` e os passos 6–9 de `Recupera.mqh`. Continuam valendo as regras de negócio da especificação 1.0 (D1–D3, B1–B10, S antes de E, uma operação por robô, corte em F − 5 min, sem push, sem trava de saldo, proteção sem portão). "§n" aponta para este documento; "spec n" para a especificação; R1/R2/R3 são as revisões de código 1, 2 e 3.

**Ideia.** Os módulos declaram o estado que desejam (intenção). A cada ciclo o núcleo lê **um** snapshot da corretora, deriva dele o estado de cada robô, compara com a intenção e executa **no máximo uma ação por robô**, escolhida por uma tabela com prioridade fixa: proteção > saída > limpeza > alvo > entrada. Nada de estado do núcleo sobrevive entre ciclos, exceto o que vai para a memória: o mapa de ordens, os níveis pedidos e os bloqueios.

Constantes novas ou mudadas: `PROVA` 30 s · `CONEXAO` 10 s · `CARENCIA_DEAL` 10 s · `PRAZO_ENTRAR` 10 s · `PRAZO_SAIR` 60 s · `PRAZO_S_SEM_E` 10 s · `PRAZO_TRANSITORIO` 10 s · `PRAZO_CORTE` 2 min · `RETENTA` 5 s · `RODADAS` 4. Saem `PRAZO_CONFIRMACAO` e `PRAZO_SEM_DESFECHO`.

## 1. Tipos de dados

### 1.1 Snapshot (lido inteiro no início do ciclo; nada é lido depois)

| Campo | Fonte |
|---|---|
| `agora`, `agora_msc` | `TimeTradeServer()`; ms por `GetTickCount64` relativo ao último segundo |
| `conectado_desde` | `TERMINAL_CONNECTED`, instante da última transição para verdadeiro |
| `liquida` (volume assinado) | `PositionSelect`; erro ≠ `POSITION_NOT_FOUND` = falha de leitura |
| `vivas[]` (ticket, magic, tipo, preço, vol, setup_msc) | `OrdersTotal`/`OrderGetTicket`; ticket 0 no meio = falha |
| `deals[]`, `ordens_hist[]` da janela | `HistorySelect(janela_inicio, agora)`; ticket 0 = falha. Janela: spec 3.2, recuo persistido |
| `tick` (bid, ask, last) | `SymbolInfoTick` |
| `grade` (início, corte C, F, fim da sessão) | `Grade.mqh` pela data de `agora` |
| `trava_minha` | `GlobalVariableGet` = meu token (§1.6) |
| `mapa[]` | memória do dia (§1.2); não vem da corretora, mas é parte do snapshot e só muda no passo 5 do ciclo |
| `externa_desconhecida` (spec 3.2), `bloqueios`, `absorcoes_vistas`, `niveis[r]`, `momentos_enviados[r]` | memória |

### 1.2 Mapa (persistido; uma linha por ordem que o EA enviou)

`id` local · robô (ou MAESTRO) · papel ∈ {E, S, A, X, K (cancelar), M (modificar)} · `episodio` · `seq` · comentário · tipo, preço, volume · `alvo_ticket` (K e M) · `ficha_ao_enviar` · `enviado_msc` · `ticket`, `request_id` (preenchidos no retorno, podem ficar 0) · `desfecho` ∈ {PENDENTE, VIVA, EXECUTADA, NAO_EXECUTADA, RECUSADA} · `prova`.

O papel de uma ordem é **o do mapa e nunca muda**. Ordem de magic de robô fora do mapa (memória e log perdidos, ou ordem posta à mão com o magic) recebe papel pelo tipo: stop = S, qualquer outro = X. **Nunca E.** Episódio: número por robô, aberto pela S de uma entrada (ou por uma S de emergência), fechado quando a ficha é 0 e nenhuma ordem do episódio está viva ou pendente.

### 1.3 EstadoRobo (derivado do snapshot a cada ciclo; nunca guardado)

| Campo | Derivação |
|---|---|
| `f` | Σ volume assinado dos deals do robô na janela − absorções. Deal é do robô se `DEAL_ORDER` está no mapa com esse robô; senão se `DEAL_MAGIC` é dele; senão se `ORDER_MAGIC` da ordem no histórico é dele (P2) |
| `papel_abertura` | papel (mapa) do deal que tirou `f` de 0 pela última vez |
| `situacao` | ZERO (`f` = 0) · LEGITIMA (\|f\| = 1, aberta por E) · TRANSITORIA (`f` = −lado da E do episódio, E viva ou pendente) · TROCADA (\|f\| = 1 sem E na abertura) · DUPLICADA (\|f\| ≥ 2) |
| `noite` | deal de abertura de pregão anterior |
| `preco`, `hora`, `id` | deal de abertura (preço médio desde o último zero) |
| `S_vivas`, `E_viva`, `A_viva` | `vivas[]` ∩ mapa do robô, por papel; `cobertura` = Σ volume das S do lado que protege |
| `pendentes[papel]` | linhas do mapa do robô com desfecho PENDENTE, com idade |
| `reduz_pendente` | existe X, A, K de A, M de S ou S **pendente** (ordem que pode reduzir a ficha a qualquer instante) |
| `em_espera[papel]` | ação recusada há menos de `RETENTA` |

Deal de magic que não é de robô: externo, spec 7.1 (compensa a externa; o que reduz abaixo de Σ fichas é absorvido na ordem fixa GB, CM, DM, RE, C1, e liga o bloqueio). Absorções já vistas ficam na memória. Par fecha/reabre de mesmo volume e instante fora do contínuo = AJUSTE (P14), sem efeito. Deal C_CONTA do corte (§5) é absorvido do mesmo jeito, sem bloqueio.

### 1.4 Intencao (escrita pelo módulo a cada `Tick`)

| Tipo | Campos | Significado |
|---|---|---|
| NADA | — | sem posição e sem E; E viva deve ser cancelada |
| ENTRAR | lado, `limite` (0 = mercado, C1), `stop`, `momento` (vela da decisão) | quero esta E com esta S; uma E por `momento` |
| MANTER | `stop`, `alvo` (0 = sem A) | estou posicionado; S neste nível; A neste nível |
| SAIR | `motivo`, `desde` | quero a ficha em 0 agora; o módulo mantém até a ficha zerar ou receber `SAIDA_EXPIRADA` |

### 1.5 Acao (no máximo uma por robô por ciclo, mais as da conta no corte)

`ENVIA_S(nível, vol)` · `MOVE_S(ticket, nível)` · `ENVIA_E(lado, preço, validade)` · `ENVIA_A(nível)` · `MOVE_A(ticket, nível)` · `ENVIA_X(vol)` · `CANCELA(ticket)` · `NENHUMA`. Conta: `C_CONTA(vol)` com magic MAESTRO. Preenchimento e comentário: spec 2.

### 1.6 Trava como concessão (D3)

Variável `WinMaestro.lock` = token de quem detém; heartbeat a cada ciclo. Livre ou heartbeat alheio ≥ 10 s → toma e AVISO. Detida por outro vivo → snapshot INVALIDO para esta instância, sem `Tick` dos módulos, retentando a cada ciclo. Não há estado terminal.

## 2. Ciclo

Disparado por `OnTimer` (250 ms), `OnTick` e `OnTradeTransaction`. Depois de um envio, o mesmo evento roda outro ciclo, até `RODADAS` = 4: a S e a E de uma entrada saem no mesmo tick, cada uma com o seu snapshot.

1. **Leitura** do snapshot (§1.1). Releitura completa da janela só ao reconectar ou ao recuar a janela, no máximo 1 a cada 10 s.
2. **Validação.**

| Nível | Quando | O que se faz |
|---|---|---|
| INVALIDO | qualquer leitura falhou; `agora − conectado_desde` < `CONEXAO`; releitura pendente; trava não é minha; conta não NETTING | **nada**: nenhum envio, nenhum cancelamento, módulos sem `Tick`. As S seguem no servidor. ALERTA aos 30 s e a cada 5 min |
| PARCIAL | leitura boa, mas Σ deals da janela + externa desconhecida ≠ `liquida` (cruzada aberta), ou há deal não classificado (magic que não é de robô, ordem ainda fora do histórico, idade < `CARENCIA_DEAL`) | fichas não confiáveis. Módulos sem `Tick`. Só: (a) S de lado inequívoco (§3.3, P1p); (b) OCO por prova (§3.2, L3b); (c) cancelar E de robô cuja última intenção é NADA; (d) motor de corte (§5). **Nenhuma S é cancelada fora de (b).** Recua a janela (spec 3.2); bloqueio de entradas aos 60 s; aos 10 min, bloqueio com botão |
| COMPLETO | o resto | ciclo inteiro |

3. **Derivação** de `EstadoRobo` para os cinco (§1.3) e da intenção efetiva (§3.1).
4. **Decisão:** motor de corte (§5), depois a tabela (§3.2) de cada robô na ordem fixa.
5. **Registro:** a linha do mapa (PENDENTE) é gravada na memória e a linha `ORDEM` no log (com `FileFlush`) **antes** do `OrderSend`. Memória que não grava: E e A não saem; S, K, M, X e C_CONTA saem com a linha do log (ALERTA).
6. **Envio** síncrono; ticket, `request_id` e retcode vão ao mapa. Recusa definitiva → RECUSADA, `em_espera` por `RETENTA`, ALERTA na 5ª seguida. Nenhuma espera dentro do ciclo: o desfecho é provado nos ciclos seguintes (§4).

## 3. Decisão por robô

### 3.1 Intenção efetiva (a primeira que se aplica)

| # | Condição | Intenção efetiva |
|---|---|---|
| I1 | `agora` ≥ C | `f` ≠ 0 → SAIR(alvo 0), qualquer `situacao`; `f` = 0 → NADA |
| I2 | TROCADA, ou TRANSITORIA há mais de `PRAZO_TRANSITORIO` | SAIR(alvo 0) |
| I3 | DUPLICADA | SAIR(alvo = sinal(f) · 1): correção de \|f\| − 1, S mantida. I2 e I3 **nunca travam**: a 2ª correção executada do robô em 10 min só liga o bloqueio de entradas com botão (decidido pelo dono 2026-10-07; muda spec 8) |
| I4 | `noite`, ou `agora` ≥ zeragem do robô (spec 9.2) | SAIR(alvo 0) |
| I5 | o nível de S pedido já foi atravessado (bid/ask, piso spec 5.3) | SAIR(alvo 0) |
| I6 | módulos ainda não prontos (partida), PROTEGENDO, ou `Init` do módulo falhou | CONGELADA: `f` ≠ 0 → MANTER(stop: memória → `StopRegra` → S viva → `STOP_EMERGENCIA_PTS`; alvo: só mantém A viva); `f` = 0 → mantém a E viva do mapa, nunca ENTRAR |
| I7 | — | a intenção do módulo |

Modificadores: com bloqueio, robô desligado, memória que não grava ou fora do contínuo, ENTRAR só sustenta uma E já viva; não envia E nova. SAIR do módulo com `desde` + `PRAZO_SAIR` vencido → evento `SAIDA_EXPIRADA` e NADA/MANTER pelo módulo no ciclo seguinte. ENTRAR com `momento` já enviado não reenvia; não enviado em `PRAZO_ENTRAR` → `ENTRADA_PERDIDA`.

### 3.2 Tabela (primeira linha que casa decide; linha em `em_espera` é pulada)

| # | Estado real | Intenção | Ação |
|---|---|---|---|
| **P1** | (`f` ≠ 0, qualquer situação, ou E viva/pendente, ou S de entrada recém-enviada) e `cobertura` < max(\|f\|, 1) e nenhuma S pendente e não `reduz_pendente` | qualquer | `ENVIA_S(nível pedido, vol = max(\|f\|,1) − cobertura)`; nível: intenção → memória → `StopRegra` → emergência. Fora da janela de ordens: espera a pré-abertura. **S faltando** |
| P2 | `f` ≠ 0 e há S do lado que aumenta \|f\|, ou `cobertura` > \|f\|; não `reduz_pendente` | qualquer | `CANCELA` a S errada (ou a menos protetora do excesso). **S sobrando com ficha** |
| P3 | S viva fora do nível pedido (> ½ tick); sem M pendente | MANTER, ENTRAR, CONGELADA | `MOVE_S` |
| X1 | fora do contínuo, ou depois de F | SAIR | `NENHUMA` (a S protege; I3/I4 voltam no contínuo) |
| X2 | `reduz_pendente` com X, A ou K de A | SAIR | `NENHUMA` — **nunca duas saídas**; prazo §4 |
| X3 | A viva | SAIR | `CANCELA` A (a S fica) |
| X4 | TRANSITORIA ou E viva | SAIR | `CANCELA` E (a S fica) |
| X5 | `f` ≠ alvo | SAIR | `ENVIA_X(\|f − alvo\|)` com o magic do robô (saída, correção ou corte) |
| L1 | E viva e (intenção ≠ ENTRAR, ou preço/lado ≠ intenção, ou `f` ≠ 0) | qualquer | `CANCELA` E; a S fica por P1 enquanto a E ou o K dela existir; depois do K confirmado, P3 move a S e E1 manda a E nova no mesmo episódio |
| L2 | A viva e (`situacao` ≠ LEGITIMA ou alvo pedido 0 ou lado errado) | qualquer | `CANCELA` A |
| L3 | S viva, `f` = 0 provado, sem E viva/pendente, sem nada pendente do robô, e (intenção ≠ ENTRAR ou S com mais de `PRAZO_S_SEM_E`) | qualquer | `CANCELA` S. **S sobrando sem ficha / OCO.** L3b (vale em PARCIAL): A, X ou S do episódio LEGITIMA de volume 1 com prova de execução → `CANCELA` as irmãs vivas do episódio |
| L4 | limite de magic do robô fora do mapa | qualquer | `CANCELA` (stop fora do mapa é S, entra em P1–P3) |
| A1 | LEGITIMA, contínuo, não `noite`, sem A, sem A pendente | MANTER com alvo > 0 | `ENVIA_A`; cruzaria limite própria oposta (O2) → `NENHUMA` neste ciclo |
| A2 | A viva fora do nível | MANTER com alvo > 0 | `MOVE_A` (mesma checagem O2) |
| E1 | ZERO, nada pendente, sem bloqueio, contínuo, `momento` não enviado, S do lado que protege a E viva no nível | ENTRAR | `ENVIA_E`; O2 → `ENTRADA_RECUSADA(autoneg)` e o `momento` é consumido |
| E2 | ZERO, nada pendente, sem S | ENTRAR | `ENVIA_S` do episódio novo (S antes de E, todos os robôs) |
| Z | qualquer outro | qualquer | `NENHUMA` |

**Linhas que o pedido exige, onde estão:** ordem enviada sem desfecho → P1/X2/E1 (`reduz_pendente` e "nada pendente"), §4; ficha trocada ou duplicada → I2/I3 → P1 (S para \|f\| inteiro) e X5; S faltando → P1 (e P1p em PARCIAL, §3.3); S sobrando → P2 (com ficha) e L3 (sem ficha); ficha indeterminada → **não existe**: deal do robô sem ordem no mapa ganha papel pelo tipo (nunca E), então a ficha cai em TROCADA (I2); deal ainda sem ordem legível é "não classificado" e torna o snapshot PARCIAL por no máximo `CARENCIA_DEAL`; deal externo que reduz → absorção (§1.3), a ficha vai a 0, o bloqueio entra, L1–L3 limpam as ordens dela.

**Completude.** A última linha é `NENHUMA`, então todo estado tem ação. Todo `NENHUMA` que não é repouso tem prazo: X1 termina no contínuo ou em F (vira `noite`); X2 e "nada pendente" terminam em `PROVA` (§4); TRANSITORIA vira TROCADA em 10 s; S recusada volta em `RETENTA`. P1 só espera quando há ordem que reduz pendente, isto é, quando criar uma S poderia abrir posição numa conta já zerada (R3 M-4).

### 3.3 S em snapshot PARCIAL: lado inequívoco (decidido pelo dono 2026-10-07)

Em PARCIAL a tabela não roda; só esta linha cria S. **Lado inequívoco** L do robô r = as seis condições juntas, todas lidas do snapshot e do mapa, nenhuma da soma das fichas:
1. a E do episódio atual de r tem prova de execução (deal ou `FILLED`), lado L, volume 1;
2. toda S, A e X do episódio tem desfecho VIVA, NAO_EXECUTADA ou RECUSADA (nenhuma PENDENTE, nenhuma EXECUTADA, nenhuma sumida sem prova);
3. nenhum outro deal de r no episódio, e nenhuma ordem de magic de r fora do mapa nas vivas ou no histórico da janela;
4. nenhum deal não classificado no snapshot (a PARCIAL é só de cruzada);
5. sinal(`liquida`) = L;
6. o episódio não tem K, M nem E pendente.

Como as ordens de r são as únicas que movem a ficha de r e todas estão provadas, a ficha de r é L · 1 qualquer que seja o deal que falta. Ficha da noite cuja S venceu (`EXPIRED` = prova) passa por aqui.

| # | Estado | Ação |
|---|---|---|
| **P1p** | lado inequívoco L, `cobertura` = 0, nenhuma S de r PENDENTE, não `em_espera` | `ENVIA_S(vol 1)` do lado que protege L; nível: memória → `StopRegra` → emergência; nível já atravessado → nada (ALERTA; o corte resolve) |

**Nunca em duplicata.** Cabe **uma** S por robô em PARCIAL, de volume 1. A linha só dispara com `cobertura` = 0 e sem S pendente; a S nova entra no mapa como PENDENTE **antes** do `OrderSend` (§2 passo 5), então no ciclo seguinte ela já impede outra. Ela só deixa de impedir quando é provada VIVA (cobre) ou NAO_EXECUTADA (então pode ser refeita, depois de `RETENTA`). Ticket ≠ 0 sem prova continua PENDENTE enquanto durar a PARCIAL, porque a prova por ausência exige COMPLETO (§4): o lado seguro é ficar sem uma segunda S, com a S que talvez exista. P1p não move nem cancela S.

## 4. Ordem sem desfecho

O desfecho de cada linha PENDENTE do mapa é procurado em todo ciclo, com prova:

| Desfecho | Prova |
|---|---|
| EXECUTADA | deal com `DEAL_ORDER` = ticket, **ou** ordem no histórico `FILLED`/`PARTIAL` (deal a caminho) |
| VIVA | listada em `vivas[]` (ticket, ou casamento para ticket 0: magic do robô, tipo, preço, volume, `setup ≥ enviado − 2 s`) |
| NAO_EXECUTADA | histórico `CANCELED`/`REJECTED`/`EXPIRED`; ou ticket 0, idade ≥ `PROVA` com conexão confiável o tempo todo, e ausente de `vivas[]` e do histórico pelo casamento (**sem exigir a cruzada**); ou ticket ≠ 0, idade ≥ `PROVA`, ausente das duas listas, snapshot COMPLETO |
| K / M | K: alvo `CANCELED` = feito; alvo EXECUTADA = executou antes (a ficha mostra); alvo ainda viva após `PROVA` = K não executado, refeito depois de `RETENTA`. M: preço da ordem em `vivas[]` = feito; diferente após `PROVA` = refeito |

Ordem que some de `vivas[]` sem `CANCELED` no histórico volta a PENDENTE: é assim que a S que disparou com deal atrasado bloqueia uma S nova (P1).

**Por que não há impasse.** Em snapshot COMPLETO toda PENDENTE se resolve em até `PROVA`: ordem a mercado não fica viva, então ou mudou a líquida (e o deal ou o `FILLED` aparece) ou não existe. A única espera sem prazo próprio é PARCIAL (deal que não chega), e ela tem três saídas: a cruzada fechar, o bloqueio com botão aos 10 min e o motor de corte (§5), que não depende de fichas nem de desfechos. Durante qualquer espera: a S nunca é cancelada (P2 e L3 exigem nada pendente) e nenhuma segunda saída sai (X2).

## 5. Motor de corte

Uma regra, avaliada em todo ciclo não INVALIDO com `agora` ∈ [C, fim da sessão):

1. **De C a C + `PRAZO_CORTE`:** a tabela roda com I1 (todo robô com `f` ≠ 0 sai por X5, qualquer situação; o resto cancela E e A e, com `f` = 0, a S). Nada da tabela é barrado por bloqueio, PROTEGENDO, robô desligado, correção repetida ou memória.
2. **A partir de C + `PRAZO_CORTE`** o alvo é **líquida real = 0 no símbolo**, posição manual do dono incluída (decidido pelo dono 2026-10-07). As linhas X da tabela deixam de rodar e só a conta age, uma ação por ciclo: cancela toda limite de magic de robô viva; com `liquida` ≠ 0, nenhuma ordem a mercado de robô ou do maestro PENDENTE com idade < `PROVA` e nenhum deal não classificado → `C_CONTA(|liquida|)`; com `liquida` = 0 → cancela toda S de robô. Ordens pendentes de magic que não é de robô (do dono) não são tocadas (spec 2); se existirem no corte, ALERTA.
3. **Depois de F:** nenhuma ordem a mercado; K de S, E e A até o fim da sessão (call incluído). `liquida` ≠ 0 em F → ALERTA.

O passo 2 lê só a posição real e o tempo: ficha trocada nunca corrigida, PROTEGENDO, trânsito sem desfecho ou cruzada aberta não o bloqueiam (R3 A-1, A-2), e ele não depende de saber quanto da líquida é do dono. Nunca manda duas saídas porque espera toda ordem a mercado ter `PROVA` de idade e porque as linhas X da tabela já não rodam. O deal do `C_CONTA` (magic MAESTRO) é absorvido nas fichas pela ordem fixa e o que sobra reduz a externa (§1.3); a janela do pregão seguinte começa com líquida 0, e fichas fantasmas não atravessam. Corte perdido (EA volta depois de C) é o mesmo caso.

## 6. Partida

Não há sequência própria. `OnInit`: zera as globais, toma a trava (§1.6), carrega a memória (mapa, níveis, `externa_desconhecida`, bloqueios, absorções, momentos), confere o ambiente (spec 10.2 passo 3; falha com ficha ou ordem de robô = PROTEGENDO) e liga o timer. Os ciclos começam no primeiro timer, com I6 (CONGELADA): snapshot INVALIDO até a conexão firmar (passo 2 da spec); PARCIAL enquanto a janela recua (passo 4); COMPLETO → a tabela faz órfãs (L1–L4), proteção (P1–P3), trocada, duplicada, ficha da noite e corte perdido (I1–I4). No **primeiro** snapshot COMPLETO os módulos recebem `Init(vista)` e o log `PRONTO` traz os deals feitos com o EA fora, com a hora real. Decisão cujo momento passou = `DECISAO PERDIDA` no módulo. Memória perdida: mapa refeito das linhas `ORDEM` do log do dia; sem log, papel pelo tipo (§1.2).

## 7. Interface dos módulos

**Recebe:** `Tick(const VistaRobo &v, Intencao &i)`, chamado com snapshot COMPLETO de `preabertura_inicio` ao corte. `VistaRobo` = {`agora`, `tem` (só LEGITIMA), `lado`, `preco`, `hora`, `id`, `stop_pedido`, `alvo_vivo`, `entrada_viva` (lado, preço), `continuo`}. Os módulos param de chamar `TimeCurrent` para decisões de horário; continuam lendo barras e tick direto. `Evento(ev, dado)`: `ENTRADA_RECUSADA(motivo)`, `ENTRADA_PERDIDA`, `ENTRADA_CANCELADA` (E sumiu sem deal, provado), `SAIDA_EXPIRADA`. Mantidos: `Exporta`/`Importa`, `StopRegra`, `MinutoZerar`, `Reseta`.

**Sai:** `Ficha_EntraLimite`, `Ficha_EntraMercado`, `Ficha_Fecha`, `Ficha_DefineStop`, `Ficha_DefineAlvo`, `Ficha_Cancela`, os códigos `ENVIADA`/`RECUSADA`/`BLOQUEADA`, `Ficha_Motivo` e `EXECUTOU_ANTES`. Regra comum: **o módulo só limpa o estado de uma entrada ao receber `ENTRADA_CANCELADA`/`RECUSADA`/`PERDIDA`, nunca ao pedir o cancelamento**; se a ficha aparece, ele a adota pela vista.

| Robô | Muda |
|---|---|
| GB | `AvaliaSinal` → ENTRAR; `GerirPosicao` → MANTER(stop, ou BE; alvo); `g_exp` → NADA; `PendentesNossas`/`Zerar` saem. Validade `SPECIFIED` ou `DAY` decidida uma vez na partida por `SYMBOL_EXPIRATION_MODE` (sem fallback por recusa) |
| CM | `Entra` → ENTRAR(limite, S de reserva); `AjustaStopAperta` → MANTER(stop que aperta); `Fecha` → SAIR mantido; `Cancela` → NADA. Cancelar e rearmar na mesma vela vira troca de preço da ENTRAR (L1 reaproveita a S) |
| DM | `Decidir` → ENTRAR; `AjustarStop` → MANTER(stop reancorado) e SAIR se já atravessado; `CancelarEntrada` (15 min) → NADA; `g_ordem` limpo só no evento; `VerificarStop` sai |
| RE | `ArmarEntrada` → ENTRAR; fill visto na vista → MANTER(stop reancorado, alvo); `AproximarAlvo` → MANTER(alvo novo); `LimparAlvoOrfao` e `ZerarPregao` saem (L2 e corte); `Evento(EXECUTOU_ANTES)` sai; níveis da entrada guardados até o evento |
| C1 | `Entra` → ENTRAR(limite 0, stop); `AtualizaPosicao` → MANTER(trailing) ou SAIR; `VerificaBreakEven` → SAIR; zeragem sai |

## 8. Achados das revisões × mecanismo da v2

Mecanismos: **[S]** snapshot único com validação (§2) · **[M]** mapa persistido, papel fixo, nunca E sem mapa (§1.2) · **[T]** tabela com uma ação e prioridade (§3) · **[I]** intenção sem código de retorno (§1.4, §7) · **[D]** desfecho com prova e prazo (§4) · **[C]** motor de corte (§5) · **[K]** trava como concessão (§1.6) · **[P]** persistência na memória.

| Achados | Mecanismo |
|---|---|
| R1 C-1, B-5; R2 B-9, M-7 | [T] E2→E1 (S antes de E); P1 não espera E pendente; L1 reaproveita a S; GB sem fallback |
| R1 C-2; R2 B-3; R3 A-2 | [T] P1 cobre \|f\| em qualquer situação; I1–I3 + X5, correção nunca trava (decisão 1); [C] passo 2 pela posição real |
| R1 A-1; R2 M-5; R3 B-1 | [M] robô pelo `DEAL_ORDER`/`ORDER_MAGIC`; [S] deal não classificado = PARCIAL; [C] espera a carência |
| R1 A-2, A-6; R2 M-1; R3 B-5 | [I] intenção NADA repete o cancelamento; módulo limpa só no evento e adota a ficha; A recriada por A1; `EXECUTOU_ANTES` não existe |
| R1 A-3; R2 M-6 | [M]+[D] ticket pelo mapa; casamento por magic/tipo/preço/volume/`setup`, sem comentário |
| R1 A-4, M-2, B-11; R2 B-7 | [S] leitura que falha ou lista parcial = INVALIDO; nada é decidido sobre dado velho; releitura completa no máximo a cada 10 s |
| R1 A-5; R1 B-12 | [I] `Tick` desde a pré-abertura; hora de decisão vem da vista |
| R1 M-1; R2 A-3, M-4; R3 M-1, B-3 | [M] papel fixo no envio e persistido; indeterminada não existe |
| R1 M-3; R2 B-8; R3 B-4, B-6, B-7 | [D] sem espera no ciclo; prazo por linha do mapa; mesma regra para todo papel; `FILLED` = executada; só recusa real conta |
| R1 M-5; R3 B-8 | [S] não NETTING = INVALIDO; PROTEGENDO = I6 (sem A nova, sem E) |
| R1 M-6 | [D] o botão só libera bloqueio; o mapa não é apagado |
| R1 M-9; R2 A-4 | [P] ALERTA; só E e A barradas (§2 passo 5) |
| R1 M-10; R3 M-3 | [S] PARCIAL cria S de lado inequívoco (§3.3, P1p) e nunca cancela S fora de L3b; L3b faz o OCO por prova; [C] |
| R2 A-1; R3 A-1 | [C] passo 2 espera só ordens a mercado < `PROVA`; [D] sem cruzada para ticket 0 |
| R2 A-2; R3 M-2, M-6; R1 B-4 | [I] SAIR mantido pelo módulo com `PRAZO_SAIR`; módulos só rodam em COMPLETO (portão de vela não se perde); sem `BLOQUEADA` |
| R2 M-2 | [P]+§6 `externa_desconhecida` carregada antes do primeiro snapshot |
| R2 M-3 | [C] passo 3: K e S até o fim da sessão |
| R3 M-4 | [D] S sumida sem `CANCELED` = PENDENTE; P1 espera |
| R2 M-8; R3 M-5 | [K] |
| R2 B-1; R1 B-1; R2 B-2 | §6: módulos só existem no ciclo depois do `Init`; A só em A1 (contínuo, não noite) |
| R1 B-2 | [T] X3 cancela a A na correção; A1 a recria com a ficha LEGITIMA |
| R1 B-3; R2 B-4; R3 B-9 | [P] deals logados por ticket e absorções vistas na memória |
| R3 B-2 | [C] `C_CONTA` com magic MAESTRO, absorvido pela ordem fixa; zerar a externa no corte é regra (decisão 2), não efeito colateral |
| R3 B-10 | [D] A `FILLED` → X2 espera |
| R3 B-11 | [T] linha em `em_espera` é pulada; a seguinte roda |
| R3 §6 testes (T34, T39, T66, T70 e os sem cobertura) | continua: suíte refeita como tabela estado × intenção → ação sobre a `CorretoraFalsa` (spec 12), um teste por linha de §3.2 e de §4 |
| R1 M-4 (feriados) | continua: `MARKET_CLOSED` retentado com AVISO (decisão anterior do dono) |
| R1 M-7 | continua: AJUSTE em §1.3; ALERTA até P14 |
| R1 M-8, B-6, B-7, B-8, B-9, B-10; R2 B-5, B-6 | continuam fechados como estão (constantes, ms, arrays, `FILE_UNICODE`, classe real fora do teste, retcodes, P12 documentado, código do `PositionSelect`) |

## 9. Tamanho e remoções

| Arquivo | Hoje | v2 |
|---|---|---|
| `Snapshot.mqh` (leitura, validação, janela, cruzada) | — | ~250 |
| `Mapa.mqh` (linhas, desfecho, casamento) | — | ~250 |
| `Estado.mqh` (fichas, situação, absorção, episódio) | — | ~300 |
| `Decide.mqh` (intenção efetiva, tabela, corte) | — | ~350 |
| `Envia.mqh` (request, registro antes, retcodes) | — | ~180 |
| `Fichas.mqh` | 2.722 | removido |
| `Recupera.mqh` → `Partida.mqh` (trava, ambiente, `PRONTO`) | 528 | ~150 |
| `Corretora.mqh`, `CorretoraFalsa.mqh`, `Memoria.mqh`, `Log.mqh`, `Grade.mqh`, `Inputs.mqh` | 1.090 | ~1.100 |
| `WinMaestro.mq5` | 226 | ~180 |
| 5 módulos | 3.654 | ~3.400 |

Núcleo: 3.250 → ~1.480 linhas. Globais de estado por robô: 16 → 0 (o estado do robô é derivado; persistem só mapa, níveis e momentos).

**Removido:** `Mae_Fase1`/`Mae_Fase2` e a cadeia de `return`; `Mae_CorteConta` e `mzCorteConta`; `Mae_EstadoFecha`, `Mae_PodeEntrar` e os portões próprios de `Mae_Modifica`, da recriação de alvo e do nível atravessado; `Ficha_Entra*`, `Ficha_Fecha`, `Ficha_DefineStop`, `Ficha_DefineAlvo`, `Ficha_Cancela`, `Ficha_Motivo` e os códigos de retorno; `mzSaidaPedida`/`mzSaidaFid`; `mzECancelPedido`; `mzIndet`/`mzIndetDesde`; `Mae_FichaEm`/`mzCk` (papel pela ficha na colocação) e a leitura de comentário na classificação; `mzMagic0Pend`; `mzCorrTravada`; `mzTravaPerdida`; `mzEpisodio`; `EV_EXECUTOU_ANTES`; contadores e prazos compartilhados de `Mae_Recusa`; passos 6–9 de `Recupera`; `PRAZO_CONFIRMACAO` e a espera de 5 s. Nos módulos: `VerificarStop` (DM), `LimparAlvoOrfao`/`ZerarPregao` (RE), `PendentesNossas`/`Zerar` (GB), `Evento(EXECUTOU_ANTES)` (RE) e os testes de código de retorno depois de cada chamada.

## 10. Decisões do dono

1. **Correção nunca travada** (muda spec 8): ficha trocada ou duplicada é sempre corrigida; a 2ª correção em 10 min bloqueia só entradas novas, com botão (I3). Decidido pelo dono 2026-10-07.
2. **Corte zera tudo:** depois de C + `PRAZO_CORTE` a líquida real do símbolo vai a 0, posição manual do dono incluída (§5). Decidido pelo dono 2026-10-07.
3. **Prova "não executada" de ordem sem ticket aos 30 s sem a cruzada** (muda spec 4.4); `PROVA` sobe se P6/P18 mostrarem atraso maior. Decidido pelo dono 2026-10-07.
4. **Prazos de intenção:** E até 10 s depois da decisão; SAIR expira em 60 s e o módulo reavalia, com a S protegendo. Decidido pelo dono 2026-10-07.
5. **Memória e log perdidos:** ficha aberta cujo deal de entrada não está no mapa vira TROCADA e é zerada na hora. Decidido pelo dono 2026-10-07.
6. **PARCIAL cria S de lado inequívoco** (proteção sem portão), uma por robô, sem duplicata (§3.3). Decidido pelo dono 2026-10-07.
7. **GB:** validade decidida na partida pelo modo de expiração do símbolo, sem fallback por recusa (§7). Decidido pelo dono 2026-10-07.
