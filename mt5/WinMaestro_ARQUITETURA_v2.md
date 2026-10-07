# WinMaestro v2.2 — arquitetura do núcleo de execução

Desenho para implementar. Substitui `Fichas.mqh` e os passos 6–9 de `Recupera.mqh`. Continuam valendo as regras de negócio da especificação 1.0 (D1–D3, B1–B10, S antes de E, uma operação por robô, corte em F − 5 min, sem push, sem trava de saldo, proteção sem portão), com as mudanças do §11. "§n" aponta para este documento; "spec n" para a especificação; R1/R2/R3 para as revisões de código; RV e RV2 para as revisões deste desenho (`WinMaestro_ARQUITETURA_v2_revisao.md`, `_revisao_2.md`).

**Ideia.** Os módulos declaram o estado que desejam (intenção). A cada ciclo o núcleo lê **um** snapshot da corretora, casa as ordens enviadas com o que a corretora mostra, deriva o estado de cada robô e a **confiança** dele, compara com a intenção e executa **no máximo uma ação por robô**, por uma tabela de prioridade fixa: proteção > saída > limpeza > alvo > entrada. A partir de C + `PRAZO_CORTE` as fichas se encerram e só o motor da conta age.

**Constantes:** `PROVA` 30 s · `CONEXAO` 10 s · `FOLGA_SETUP` 5 s · `PRAZO_ENTRAR` 10 s · `PRAZO_SAIR` 60 s · `RETENTA` 5 s · `PRAZO_BLOQUEIO` 60 s · `PRAZO_BOTAO` 10 min · `PRAZO_CORTE` 2 min · `HB_TOMADA` 60 s · `RODADAS` 4 · `STOP_EMERGENCIA_PTS` 1.200 · `TICK_WIN` 5 pts · `IDADE_TICK` 10 s · `PRAZO_S_RECUSADA` 60 s (decisão m). Não existem mais `PRAZO_CONFIRMACAO`, `PRAZO_S_SEM_E`, `PRAZO_TRANSITORIO` nem `CARENCIA_DEAL`.

**Tick.** Nenhum cálculo divide pelo tamanho de tick lido do símbolo, que pode vir 0 (é uma das causas de PROTEGENDO). Arredondamento de preço, piso e emergência usam `TICK_WIN` = 5 pts; piso = max(`TICK_WIN`, `SYMBOL_TRADE_STOPS_LEVEL` em pontos do WIN).

## 1. Dados

### 1.1 Snapshot (lido no passo 1; nada é lido depois no mesmo ciclo)

| Campo | Fonte | Falha |
|---|---|---|
| `agora`, `agora_msc` | `TimeTradeServer()`; ms por `GetTickCount64` relativo ao último segundo | — |
| `conexao_ok` | `TERMINAL_CONNECTED` verdadeiro nos últimos `CONEXAO` s | base |
| `trava_ok` | `GlobalVariableGet(lock)` = meu token (§1.6) | base |
| `liquida` (volume assinado) | `PositionSelect`; erro ≠ `POSITION_NOT_FOUND` = falha | base |
| `vivas[]` (ticket, magic, tipo, preço, vol, setup_msc) | `OrdersTotal`/`OrderGetTicket`; ticket 0 no meio = falha | base |
| `deals[]`, `ordens_hist[]` | `HistorySelect(janela_inicio, agora + 1 dia)` (limite superior com folga: o relógio local não é o do servidor); ticket 0 = falha | histórico |
| `req_tickets[]` | pares `request_id` → ticket guardados por `OnTradeTransaction(TRADE_TRANSACTION_REQUEST)` desde o último ciclo | — |
| `tick` (bid, ask, last, hora) | `SymbolInfoTick`. **Preço de referência** do lado comprado = bid, do vendido = ask, só se bid > 0, ask ≥ bid e o tick tem menos de `IDADE_TICK`; senão, o último `last` > 0 visto (guardado em RAM); senão, o preço da ficha ou da E. Nunca 0 | — |
| `grade` (pré-abertura, início, C, F, fim da sessão) | `Grade.mqh` pela data de `agora` | — |
| memória (§1.2) | carregada no `OnInit`, mantida em RAM | — |

**Base** = conexão, trava, `liquida` e `vivas[]`. Falha de base = **INVALIDO**: nenhum envio, nenhum cancelamento, módulos sem `Tick`; ALERTA aos 30 s e a cada 5 min. Falha só de **histórico** não é INVALIDO: deixa todos os robôs RESTRITOS (§2.2) e o motor da conta (§5) segue.

`janela_inicio` = o mais antigo entre (`negociacao_inicio` de hoje − 10 min) e (envio da primeira ordem de qualquer episódio aberto − 1 min). Recuo da spec 3.2 só com memória perdida ou com Δ externo inexplicado (§2.2), no máximo 1 releitura a cada 10 s, até 10 pregões.

### 1.2 Memória (o único estado que sobrevive entre ciclos, além do que fica em RAM e está listado aqui)

- **Mapa**: uma linha por ordem que o EA enviou: `id` · robô (ou MAESTRO) · papel ∈ {E, S, A, X, K (cancelar), M (modificar)} · `episodio` · `id_entrada` (E e S de entrada) · `seq` · comentário · tipo, preço, volume · `alvo_ticket` (K, M) · `enviado_msc` · `ticket`, `request_id` · `desfecho` ∈ {PENDENTE, VIVA, SUMIDA, EXECUTADA, NAO_EXECUTADA, RECUSADA} · `sumida_msc` · `prova`. Retenção: linhas do dia e de todo episódio ainda aberto (a ficha da noite precisa da E e da S de ontem).
- Por robô: níveis pedidos de S e A; `emergencia[r]` (nível de emergência do episódio, gravado uma vez, §4.3); `id_entrada` já consumidos; `seq`; instante da última correção executada.
- Bloqueios com os tickets reconhecidos; `externa_desconhecida` (regra de saída em §11, 2026-10-07: zera no dia novo, e no mesmo dia quando `liquida` e os deals da janela somam 0 por `PROVA`); absorções vistas e deals já logados (por ticket); `janela_inicio`.
- Só em RAM (refeitos na partida): `conexao_desde`, `invalido_desde`, `restrito_desde[r]`, `delta_desde` (Δ_resto com o mesmo valor desde), `s_falta_desde[r]`, `em_espera[r][papel]` e `em_espera[MAESTRO][papel]`, último `last` válido, anti-spam de log, intenções dos módulos, relógios de `PRAZO_ENTRAR`/`PRAZO_SAIR`.

O mapa ganha linhas só no passo 5 (§3); ticket, desfecho e `sumida_msc` mudam nos passos 2 e 6.

**Papel.** O papel de uma ordem é o do mapa e nunca muda. Ordem de magic de robô fora do mapa (memória e log perdidos, ou posta à mão com o magic) recebe papel pelo tipo da ordem no histórico: stop = S, qualquer outro = X, **nunca E**. Deal cuja ordem não está no mapa nem no histórico é **não classificado** até a ordem aparecer, **sem prazo**: o deal nunca vira X nem externo por tempo (o tipo é da ordem, e o deal não o carrega). Enquanto houver deal não classificado, os robôs ficam RESTRITOS (§2.2) e valem os prazos do §2.3.

**Deal MAESTRO** (o `C_CONTA` do §5) é **encerramento**: no instante dele todas as fichas vão a 0 e a externa passa a ser a líquida que sobra depois dele; não há absorção, bloqueio nem ALERTA de zeragem manual, e os episódios abertos fecham. Uma janela que inclua esse deal nunca recria fichas anteriores a ele.

**Episódio.** Número por robô, aberto pela S de uma entrada ou por uma S de proteção, fechado quando a ficha é 0 e nenhuma ordem do episódio está viva ou pendente, ou pelo corte (§5).

### 1.3 Estado do robô (derivado a cada ciclo, nunca guardado)

| Campo | Derivação |
|---|---|
| `f` | Σ volume assinado dos deals do robô na janela − absorções. Deal é do robô pela linha do mapa da sua ordem; sem linha, pelo `DEAL_MAGIC`; sem ele, pelo `ORDER_MAGIC` no histórico (P2) |
| `situacao` | ZERO (`f` = 0) · LEGITIMA (\|f\| = 1, aberta por deal de papel E) · TROCADA (\|f\| = 1, aberta por outro papel) · DUPLICADA (\|f\| ≥ 2) |
| `noite` | deal de abertura de pregão anterior |
| `preco`, `hora`, `id` | do deal de abertura (preço médio desde o último zero) |
| `S_vivas`, `E_viva`, `A_viva` | `vivas[]` × mapa, por papel; `cobertura` = Σ volume das S do lado que protege `f` |
| `pend[papel]` | linhas PENDENTE ou SUMIDA do robô; `pend_K(t)` = K pendente sobre o ticket t |
| `reduz_pend` | existe S, A ou X PENDENTE ou SUMIDA (ordem que pode reduzir a ficha agora) |
| `provado` | §2.2 |
| `confiavel` | §2.2 |

Deal de magic que não é de robô: externo, spec 7.1: compensa a externa; o que reduz abaixo de Σ fichas é absorvido na ordem fixa GB, CM, DM, RE, C1 e liga o bloqueio (§2.4). Par fecha/reabre de mesmo volume e instante fora do contínuo = AJUSTE (P14), sem efeito; ALERTA até P14 ter resposta.

### 1.4 Intenção (escrita pelo módulo no `Tick`)

| Tipo | Campos | Significado |
|---|---|---|
| NADA | — | sem posição e sem E; a E viva deve ser cancelada |
| ENTRAR | `id_entrada`, lado, `limite` (0 = mercado, C1), `stop`, `expira` (0 = DAY; GB: `g_exp`) | quero esta E com esta S; uma E por `id_entrada`; rearmar = `id_entrada` novo |
| MANTER | `stop`, `alvo` (0 = sem A) | posicionado; S e A nestes níveis |
| SAIR | `alvo` (0, ou ±1 na correção de duplicada), `motivo` | quero a ficha em `alvo`; o módulo mantém até a ficha mudar ou receber `SAIDA_EXPIRADA` |

### 1.5 Ação

Por robô, no máximo uma por ciclo: `ENVIA_S(nível)` (sempre volume 1) · `MOVE_S(ticket, nível)` · `ENVIA_E(lado, preço, validade)` · `ENVIA_A(nível)` · `MOVE_A(ticket, nível)` · `ENVIA_X(vol)` · `CANCELA(ticket)` · `NENHUMA`. Da conta (§5): `C_CONTA(vol)` com magic MAESTRO e `CANCELA`. Preenchimento e comentário: spec 2.

### 1.6 Trava

`OnInit` com a trava de outro token e heartbeat recente: o EA fica **inerte** (nenhuma ordem, não grava memória, não toca a trava) e tenta de novo a cada 1 s. Heartbeat alheio parado ≥ `HB_TOMADA` → toma (é o caso normal depois de um crash ou reinício do MT5, quando o `OnDeinit` não rodou). Heartbeat alheio **avançando** por mais de `HB_TOMADA` = segunda instância viva → `Alert` e `ExpertRemove` (spec 10.3). Em execução: heartbeat gravado a cada ciclo e **imediatamente antes e depois de cada `OrderSend`**; `HB_TOMADA` = 60 s fica acima do maior bloqueio de um `OrderSend` síncrono numa queda de rede. Trava tomada por outro → base falha (INVALIDO). Retomada só pela operação atômica `GlobalVariableSetOnCondition(lock, meu, valor_lido)` com heartbeat parado ≥ `HB_TOMADA`, e então a memória é **recarregada do disco** antes do ciclo seguinte.

## 2. Validação e confiança

### 2.1 Casamento (antes de calcular qualquer ficha)

Toda linha PENDENTE ou SUMIDA do mapa é casada contra a corretora, nesta ordem:
1. **Ticket 0:** `req_tickets[]` pelo `request_id`; senão, ordem única em `vivas[]` ∪ `ordens_hist[]` (**qualquer estado**) com o magic do robô, o tipo, o volume e `setup_msc ≥ enviado_msc − FOLGA_SETUP`, o preço só para limite e stop (preço de ordem a mercado não é chave), e **cujo ticket não está gravado em outra linha do mapa**. Casou: o ticket é gravado na linha. Mais de um candidato: segue PENDENTE (ALERTA).
2. **Com ticket**, desfecho:

| Desfecho | Prova |
|---|---|
| EXECUTADA | deal com `DEAL_ORDER` = ticket, ou ordem no histórico `FILLED`/`PARTIAL` (deal a caminho) |
| VIVA | ticket em `vivas[]` |
| NAO_EXECUTADA | histórico `CANCELED`/`REJECTED`/`EXPIRED`; ou ausente de `vivas[]` e do histórico, com histórico lido e conexão ok nos **últimos** `PROVA` s, há mais de `PROVA` s contados de `max(enviado_msc, sumida_msc)` |
| SUMIDA | estava VIVA e saiu de `vivas[]` sem estado final no histórico; `sumida_msc` = agora. Conta como pendente |
| K | alvo `CANCELED`/`EXPIRED` = feito; alvo EXECUTADA = executou antes; alvo ainda VIVA após `PROVA` = K não executado |
| M | ordem no preço novo = feito. Ticket que some e outra ordem do mesmo magic, tipo e volume, preço novo, `setup` posterior ao M aparece (P4): a linha da S passa ao ticket novo. Preço antigo após `PROVA` = M não executado |

Logo depois de um `OrderSend` aceito a ordem pode ainda não estar em `vivas[]`: até `PROVA` ela é PENDENTE, não SUMIDA.

**O deal sempre vence.** Uma linha NAO_EXECUTADA (por ausência) que depois ganha deal com `DEAL_ORDER` = ticket, ou ordem `FILLED`, passa a EXECUTADA. Como `f` sai dos deals, um desfecho errado nunca muda a ficha; muda só as guardas, e a correção (I2) cobre o efeito.

### 2.2 Confiança por robô

- **`provado(r)`**: histórico lido; nenhuma linha de r PENDENTE ou SUMIDA; toda linha EXECUTADA do episódio aberto tem os seus deals na janela; nenhum deal de r não classificado. Com isso a ficha de r é exata, porque só ordens de r movem a ficha de r.
- **Δ** = `liquida` − Σ deals da janela − `externa_desconhecida`; **Δ_resto** = Δ − Σ (volume assinado das linhas EXECUTADA ainda sem deal).
- **`confiavel(r)`** = `provado(r)` ∧ nenhum deal não classificado ∧ (Δ_resto = 0 ∨ **Δ externo estável**).
- **Δ externo estável** = Δ_resto com o mesmo valor há `PROVA` s, com histórico lido e conexão ok o tempo todo (regra de 2026-10-07, §11: não exige mais todos os robôs provados). Antes disso (o caso normal de deal que chega antes da posição, ou posição antes do deal), **todos os robôs ficam RESTRITOS**. Estável, a diferença só pode ser externa: entra como **deal externo virtual** na regra 7.1 e dispara o recuo da janela. A absorção virtual (i) liga só o bloqueio de entradas automático, nunca o com botão; (ii) **nunca alimenta L2 nem L3**: a ficha absorvida virtualmente conserva S e A até o deal real aparecer e a conta ser refeita; (iii) vai primeiro à ficha do robô cuja ordem explica o Δ, e só sem atribuição única segue a ordem fixa da regra 7.1 (§11, B2-4).
- **RESTRITO** = não confiável. O robô não recebe `Tick` (a intenção fica a última declarada) e só pode: P1–P3 com **lado inequívoco** = `provado(r)` ∧ nenhum deal não classificado ∧ (`f` = 0 com E viva, ou sinal(`liquida`) = sinal(`f`)); L1 (cancelar E); L3 por prova de execução (§4.2). Nunca X, A nem E.

É a mesma garantia do modo PARCIAL global da v2.0, decidida robô a robô: um deal atrasado de um robô não congela os outros quando a diferença é explicada pelas linhas dele (Δ_resto = 0); diferença inexplicada congela todos por até `PROVA`, como na v2.0. É também a forma mais direta da decisão 6 do dono: a S é criada sempre que o lado do robô é provado.

### 2.3 Prazos de restrição

RESTRITO de qualquer robô há `PRAZO_BLOQUEIO` → bloqueio de entradas (sai sozinho quando todos voltam a confiáveis). Há `PRAZO_BOTAO` → bloqueio com botão; o botão grava Δ_resto como `externa_desconhecida` e os tickets causadores como reconhecidos.

### 2.4 Bloqueio

Qualquer bloqueio (zeragem manual, `PRAZO_BLOQUEIO`, `PRAZO_BOTAO`, 2ª correção em 10 min) tira a entrada de todos os robôs: robô com `f` = 0 tem intenção efetiva NADA, e as E vivas de **todos** são canceladas (spec 7.1/7.2), com as S delas depois, e com `ENTRADA_CANCELADA` ao módulo pela prova. Nunca barra S, cancelamento, saída, correção ou corte.

## 3. Ciclo

Disparado por `OnTimer` (250 ms), `OnTick` e `OnTradeTransaction`; enquanto a trava não é minha no `OnInit` (§1.6), o ciclo só tenta a trava. Depois de um envio o mesmo evento roda outro ciclo, até `RODADAS`; se a S ainda não está listada, a E sai num ciclo seguinte.

1. **Leitura** (§1.1). Base falhou → INVALIDO, fim do ciclo.
2. **Casamento e desfechos** (§2.1).
3. **Derivação:** fichas, absorção, situação, `provado`, Δ, `confiavel` (§1.3, §2.2); eventos aos módulos (§7); `Tick` dos módulos confiáveis entre a pré-abertura e o corte, depois de os módulos terem `Init`.
4. **Decisão:** motor de corte (§5); antes de C + `PRAZO_CORTE`, a tabela (§4) de cada robô na ordem fixa.
5. **Registro** da linha nova (PENDENTE) na memória e da linha `ORDEM` no log com `FileFlush`, **antes** do `OrderSend`. Memória que não grava: E e A não saem; S, K, M, X e `C_CONTA` saem com a linha do log (ALERTA).
6. **Envio** síncrono; ticket, `request_id` e retcode vão à linha. Recusa definitiva → RECUSADA e `em_espera[r][papel]` até `RETENTA` (para as ordens da conta, `em_espera[MAESTRO][papel]`, inclusive o `C_CONTA`); ALERTA na 5ª recusa seguida e a cada 5 min enquanto durar. A recusa que chega pelo histórico (aceita no envio, REJECTED depois) passa pelo mesmo caminho, com a mesma espera e a mesma contagem; a prova por ausência também, com a mesma espera e a mesma contagem (§11, B2-1).

## 4. Decisão por robô

### 4.1 Intenção efetiva (a primeira que se aplica)

| # | Condição | Intenção efetiva |
|---|---|---|
| I1 | `agora` ≥ C | `f` ≠ 0 → SAIR(0); `f` = 0 → NADA |
| I2 | TROCADA ou DUPLICADA | TROCADA → SAIR(0); DUPLICADA → SAIR(sinal(f) · 1). Correção que nunca trava (decisão 1) |
| I3 | `noite`, ou `agora` ≥ zeragem do robô (spec 9.2), ou **S recusada com a ficha aberta** (decisão m): `f` ≠ 0 e `cobertura` < \|f\| sem interrupção há `PRAZO_S_RECUSADA` (`s_falta_desde[r]`, zerado quando uma S fica VIVA cobrindo) | SAIR(0). A saída é a X3 de sempre, com o magic do robô e todas as guardas de "nunca duas saídas": sem A viva, sem E viva/pendente, sem S/A/X **pendente ou sumida** (uma S sem desfecho pode existir e barra a X), sem K pendente, sem S cruzada. X3 recusada → `RETENTA`; P1 continua tentando a S em paralelo; em C + `PRAZO_CORTE` o `C_CONTA` resolve |
| I4 | bloqueio e `f` = 0 | NADA |
| I5 | módulo sem `Init`, ou PROTEGENDO | CONGELADA: `f` ≠ 0 → MANTER(stop pela cadeia §4.3, alvo = A viva); `f` = 0 com E viva → ENTRAR com os parâmetros e o `id_entrada` dela; senão NADA |
| I6 | — | a do módulo |

`pode_entrar` = contínuo ∧ `confiavel` ∧ robô ligado ∧ memória gravando ∧ sem bloqueio ∧ `id_entrada` não consumido ∧ ENTRAR há menos de `PRAZO_ENTRAR` (contado do primeiro ciclo confiável em que apareceu). ENTRAR que vence sem E enviada → `ENTRADA_PERDIDA`. SAIR do módulo que não executou em `PRAZO_SAIR` (contado só em ciclos confiáveis) → `SAIDA_EXPIRADA`; o módulo reavalia na sua próxima decisão, com a S protegendo.

### 4.2 Tabela

Avaliada de cima para baixo; age a primeira linha cuja condição é verdadeira **por conta própria**. Linha cujo papel está em `em_espera[r]` não age até `RETENTA`; as linhas abaixo são avaliadas normalmente, e as guardas delas (sem A/E viva, sem K pendente) as impedem de agir no lugar da que espera. P1 nunca depende da espera de outro papel. Robô RESTRITO só avalia as linhas marcadas com R.

| # | Condição (todas) | Ação |
|---|---|---|
| **P1** R | precisa de S (`f` ≠ 0, ou E viva/pendente, ou ENTRAR com `pode_entrar` e sem S); `cobertura` < max(\|f\|, 1); nenhuma S pendente ou sumida; sem X ou A pendente/sumida; RESTRITO só com lado inequívoco | `ENVIA_S(nível §4.3)`, volume 1, do lado que protege `f` (ou a E/ENTRAR com `f` = 0). Fora da janela de ordens (antes da pré-abertura ou depois do fim da sessão): espera. **S faltando** |
| P2 | `confiavel`; `f` ≠ 0 e (há S do lado que aumenta \|f\| ou `cobertura` > \|f\|); `reduz_pend` falso; sem K pendente sobre essa S | `CANCELA` a S errada, ou a menos protetora até `cobertura` = \|f\|. **S sobrando com ficha** |
| P3 R | S viva fora do nível da §4.3 por > ½ `TICK_WIN`; sem M pendente. A emergência gravada nunca é recalculada: P3 só tira a S da emergência quando a intenção pede um nível válido | `MOVE_S` |
| X1 | SAIR; A viva; sem K pendente sobre ela | `CANCELA` A (a S fica) |
| X2 | SAIR; E viva; sem K pendente sobre ela | `CANCELA` E (a S fica) |
| X3 | SAIR; `confiavel`; contínuo e antes de F; `f` ≠ `alvo`; sem A viva; sem E viva ou pendente; `reduz_pend` falso; sem K pendente; **nenhuma S do robô em nível já cruzado pelo preço de referência** (essa S é a saída: espera ela executar; ALERTA após `PROVA`; **prazo próprio** de `PROVA`: cruzada e viva há `PROVA` sem executar → `CANCELA` dela, e a X sai no ciclo em que o K provar, §11 2026-10-07; o prazo conta desde que a S ficou cruzada, medido em todo ciclo com qualquer intenção, §11 B2-2) | `ENVIA_X(\|f − alvo\|)`, magic do robô |
| L1 R | E viva; sem K pendente sobre ela; (intenção ≠ ENTRAR, ou lado/preço ≠ ENTRAR, ou `id_entrada` ≠ o da E, ou `f` ≠ 0) | `CANCELA` E; a S fica (P1) até o K provar |
| L2 | `confiavel`; A viva; sem K pendente sobre ela; (`situacao` ≠ LEGITIMA, ou intenção ≠ MANTER, ou alvo 0) | `CANCELA` A |
| L3 R | S viva sem K pendente; `f` = 0 provado; sem E viva, pendente ou sumida; nada mais pendente do robô; não (ENTRAR ∧ `pode_entrar`) | `CANCELA` S. **S sobrando sem ficha, OCO.** Em RESTRITO só com prova: a irmã A/X/S do episódio LEGITIMA executou, ou a E do episódio está `CANCELED`/`EXPIRED` sem nenhum deal no episódio |
| L4 | limite de magic do robô fora do mapa; sem K pendente | `CANCELA` (stop fora do mapa é S: P1–P3) |
| A1 | `confiavel`; LEGITIMA; contínuo; não `noite`; MANTER com alvo > 0; sem A viva ou pendente; `reduz_pend` falso; sem O2 | `ENVIA_A` |
| A2 | `confiavel`; A viva fora do alvo; sem M pendente; sem O2 | `MOVE_A` |
| E1 | ENTRAR; `pode_entrar`; ZERO; sem E viva ou pendente; S do lado que protege a E, VIVA; nada pendente; sem O2 | `ENVIA_E` (validade: `SPECIFIED` até `expira` se o símbolo aceita, decidido na partida; senão DAY) e consome `id_entrada`. O2 → `ENTRADA_RECUSADA(autoneg)`, `id_entrada` consumido |
| Z | o resto | `NENHUMA` |

A S de uma entrada nova sai por P1 (cláusula "ENTRAR com `pode_entrar` e sem S"); E1 só age depois de ela estar VIVA. Não existe linha de entrada própria para a S.

**O2** (autonegociação): a E ou o A cruzaria uma limite oposta de outro robô **em `vivas[]` ou no mapa como PENDENTE/VIVA**, inclusive enviada neste ciclo.

### 4.3 Nível da S

Cadeia: nível da intenção → nível da memória → nível da S viva → `StopRegra(r, lado)` → `emergencia[r]`. Um candidato só vale se **protege o lado certo** e está do lado certo do preço de referência (§1.1): compra protegida → nível < min(referência, preço da E) − piso; venda → nível > max(referência, preço da E) + piso. Nenhum válido → **emergência**: calculada **uma vez** por episódio, referência − `STOP_EMERGENCIA_PTS` (compra) ou + (venda), arredondada a `TICK_WIN`, gravada em `emergencia[r]` e como nível pedido, e **nunca movida**: nos ciclos seguintes ela é o candidato "nível da memória", não se recalcula. Nível pedido pelo módulo já atravessado → a S vai na emergência e o módulo, que lê o mesmo preço, pede SAIR. Emergência gravada também já atravessada com a ficha aberta → a S vai ao primeiro nível válido além da referência (a emergência não muda) e a saída segue com `RETENTA`; com `f` = 0 não sai S (§11, B2-3).

**Abertura.** Uma S posta fora do contínuo (ficha da noite) pode ser cruzada pelo preço de abertura. Nesse caso ela é a saída: X3 não envia enquanto houver S do robô em nível cruzado, e não há duas saídas às 09:00.

### 4.4 Verificação da tabela

Produto conferido: confiança {confiável, RESTRITO com lado inequívoco, RESTRITO sem} × situação {ZERO, LEGITIMA, TROCADA, DUPLICADA; noite} × pendente {nada, S, S sumida, E, A, X, K de E/A/S, M de S/A} × intenção {NADA, ENTRAR (pode/não pode), MANTER, SAIR} × hora {antes da pré-abertura, pré-abertura, contínuo < C, [C, C + 2 min), [C + 2 min, F), [F, fim)} × `em_espera` por papel.
- **Toda combinação tem linha:** a última é Z. Combinações de [C + 2 min, fim) não chegam à tabela (§5).
- **Uma linha só:** a primeira verdadeira age; cada ação mexe num papel só, e as guardas "sem K pendente", "sem M pendente", "sem S pendente ou sumida" impedem a mesma ordem de ser pedida de novo enquanto a anterior não tem desfecho.
- **Sem laço:** P1 cria S com `f` = 0 só com E viva/pendente ou ENTRAR ∧ `pode_entrar`; L3 cancela só quando nenhuma das duas vale. P2 só age com `f` ≠ 0 e só até `cobertura` = \|f\|, e P1 só cria até max(\|f\|, 1). ENTRAR com `id_entrada` consumido não tem `pode_entrar`: nem P1 nem E1 agem e L3 limpa uma vez. Recusa vira espera de `RETENTA`, não repetição no mesmo estado.
- **Nunca duas saídas:** X3 exige sem A viva, sem E viva/pendente, sem S/A/X pendente ou sumida, sem K pendente e sem S em nível cruzado; A1 exige `reduz_pend` falso. A S nunca é cancelada com ordem que reduz em aberto (P2 e L3 exigem `reduz_pend` falso).
- **Espera sem prazo:** só INVALIDO (externa ao EA) e RESTRITO com histórico ilegível; os dois são cobertos pelo motor de corte (§5), que só precisa da base.

## 5. Motor de corte

1. **[C, C + `PRAZO_CORTE`):** a tabela roda com I1. Robô confiável sai por X3 em qualquer situação; o RESTRITO fica com P1/P3/L1/L3.
2. **A partir de C + `PRAZO_CORTE`** as fichas se encerram: os episódios abertos são fechados no mapa quando `liquida` chega a 0, e a tabela não roda mais. Só a conta age, com a **base** (sem histórico), uma ação por ciclo, nesta prioridade:
   1. limite de magic de robô viva, sem K pendente e fora de `em_espera` → `CANCELA` (não espera a prova para seguir);
   2. `liquida` ≠ 0, antes de F, nenhuma ordem a mercado (robô ou MAESTRO) PENDENTE com menos de `PROVA` de envio, nenhuma ordem a mercado em `vivas[]` e fora de `em_espera[MAESTRO][C]` → `C_CONTA(|liquida|)`; recusado → espera `RETENTA`, ALERTA na 5ª e a cada 5 min;
   3. `liquida` = 0 → `CANCELA` as S de robô, uma por ciclo.

   As S de robô ficam vivas enquanto `liquida` ≠ 0. A posição manual do dono entra no `C_CONTA` (decisão 2); ordens pendentes de magic que não é de robô não são tocadas (ALERTA se existirem).
3. **Depois de F:** nenhuma ordem a mercado; `CANCELA` de E e A até o fim da sessão; de S só com `liquida` = 0. `liquida` ≠ 0 em F → ALERTA, e as S ficam.

O passo 2 não depende de histórico, de fichas, de desfechos de limite ou de bloqueio: ficha trocada nunca corrigida, PROTEGENDO, trânsito sem desfecho e histórico ilegível não o travam (R3 A-1, A-2; RV A-5, A-6). Nunca há duas saídas: ele espera toda ordem a mercado ter `PROVA` de idade (ordem a mercado não fica viva) e a tabela já não roda. O deal do `C_CONTA` é encerramento (§1.2): não liga bloqueio nem cria fichas fantasma no pregão seguinte. Corte perdido (EA volta depois de C + `PRAZO_CORTE`) é o mesmo caso. A janela do pregão seguinte começa com líquida 0 e sem episódios abertos.

## 6. Partida

`OnInit`: zera as globais, toma a trava (§1.6), carrega a memória e liga o timer. Os ciclos começam no primeiro timer com I5 (CONGELADA). INVALIDO até a base firmar. No primeiro snapshot com histórico lido: conferência do ambiente (spec 10.2 passo 3: NETTING, tick ≠ 0; falha com ficha ou ordem de robô = PROTEGENDO; falha sem elas = para com ALERTA; conta não NETTING = INVALIDO permanente). A tabela, com I5, faz órfãs (L1–L4), proteção (P1–P3), trocada, duplicada, ficha da noite e corte perdido (I1–I3). Cada módulo recebe `Init(vista)` no primeiro ciclo em que o seu robô está confiável; a partir daí, I6. O log `PRONTO` traz os deals feitos com o EA fora, com a hora real. Decisão cujo momento passou = `DECISAO PERDIDA` no módulo. Memória perdida: mapa refeito das linhas `ORDEM` do log do dia; sem log, papel pelo tipo (decisão 5).

## 7. Interface dos módulos

**`Tick(const VistaRobo &v, Intencao &i)`**, chamado só com o robô confiável, da pré-abertura ao corte (ENTRAR fora do contínuo não envia). `VistaRobo` = {`agora`, `tem` (só LEGITIMA), `lado`, `preco`, `hora`, `id`, `stop_pedido`, `alvo_vivo`, `entrada_viva` (lado, preço, `id_entrada`), `continuo`}. Os módulos usam `v.agora` nas decisões de horário; continuam lendo barras e tick direto.

**Eventos** (`Evento(ev, dado)`, entregues no passo 3, só depois do `Init`): `ENTRADA_EXECUTADA(id_entrada, preço, hora)`, `ENTRADA_CANCELADA(id_entrada)` (E sumiu sem deal, provado), `ENTRADA_RECUSADA(id_entrada, motivo)`, `ENTRADA_PERDIDA(id_entrada)`, `SAIDA_EXPIRADA`. O módulo limpa o estado de uma entrada só num desses eventos, nunca ao pedir o cancelamento.

**Continuam**, como leitura da vista do ciclo: `Ficha_Tem`, `Ficha_Lado`, `Ficha_Preco`, `Ficha_Hora`, `Ficha_Id`, `Ficha_Stop`, `Ficha_TemAlvo`, `Ficha_Entrada`, e o utilitário `Ficha_PisoStop`. `StopRegra(r, lado)` passa a receber o lado e lê a vista; 0 = sem regra. Também ficam `Exporta`/`Importa`, `MinutoZerar`, `Reseta`. **Saem:** `Ficha_EntraLimite`, `Ficha_EntraMercado`, `Ficha_Fecha`, `Ficha_DefineStop`, `Ficha_DefineAlvo`, `Ficha_Cancela`, `Ficha_Motivo`, os códigos `ENVIADA`/`RECUSADA`/`BLOQUEADA` e `EXECUTOU_ANTES`.

| Robô | Muda |
|---|---|
| GB | `AvaliaSinal` → ENTRAR(`expira` = `g_exp`); `GerirPosicao` → MANTER(stop ou BE, alvo); depois de `g_exp` → NADA; `PendentesNossas`/`Zerar` saem |
| CM | `Entra` → ENTRAR(limite, S de reserva); `AjustaStopAperta` → MANTER(stop que aperta); `Fecha` → SAIR mantido; `Cancela` → NADA; rearme na mesma vela = `id_entrada` novo (L1 cancela a E velha, e L3 não cancela a S porque há ENTRAR com `pode_entrar`: P3 a move e E1 envia) |
| DM | `Decidir` → ENTRAR; `AjustarStop` (no `ENTRADA_EXECUTADA`) → MANTER(stop reancorado), SAIR se atravessado; TTL de 15 min → NADA; `g_ordem` limpo só no evento; `VerificarStop` sai |
| RE | `ArmarEntrada` → ENTRAR; `ENTRADA_EXECUTADA` → MANTER(stop reancorado, alvo); `AproximarAlvo` → MANTER(alvo novo); `LimparAlvoOrfao` e `ZerarPregao` saem (L2 e corte), o reset de `g_ticket_alvo` fica; `g_ordem_pendente` limpo só no evento |
| C1 | `Entra` → ENTRAR(limite 0, stop); `AtualizaPosicao` → MANTER(trailing) ou SAIR; `VerificaBreakEven` → SAIR; zeragem sai |

## 8. Cenários, ciclo a ciclo

| | Cenário | Resultado |
|---|---|---|
| a | CM e RE comprados; com o EA fora a S do RE executa e o A dele enche; o EA volta | INVALIDO 10 s → RE provado, f −1 aberto por A = TROCADA, CM LEGITIMA, Δ 0 → ciclo 1: RE P1, S de compra na emergência (o nível da memória é do lado da compra, inválido) → ciclo 2+: S provada VIVA → X3 compra 1 (só no contínuo; antes disso a S protege) → f 0 → L3 cancela a S. CM intacto. **Seguro** |
| b | X do C1 com TIMEOUT e ticket 0; 90 s sem internet | INVALIDO durante a queda e por mais 10 s → **executou:** a ordem `FILLED` é casada (magic/tipo/volume/setup, ticket ainda livre) → EXECUTADA; se o deal atrasa em relação à posição, Δ_resto = 0 pela linha EXECUTADA e só o C1 fica RESTRITO até o deal → f 0 → L3 cancela a S. **Não chegou:** C1 RESTRITO (linha PENDENTE) por 30 s de conexão contínua → NAO_EXECUTADA → confiável → SAIR (o `PRAZO_SAIR` não correu enquanto RESTRITO) → X3 de novo. Se depois aparecer deal da primeira X, a linha vira EXECUTADA e a inversão de 1 contrato é corrigida por I2. A S nunca sai antes. **Seguro** |
| c | O dono zera tudo na mão com GB e DM posicionados e E do CM viva | deal sem ordem no histórico → não classificado → todos RESTRITOS até a ordem aparecer (S intactas) → classificado externo → absorve GB e DM, bloqueio → I4 NADA → L1 cancela a E do CM, L2 os A, L3 as S → botão libera. **Seguro e conforme a spec 7** |
| d | Ficha da noite do DM com gap contra | janela cobre o episódio aberto de ontem; S de ontem `EXPIRED` = prova → DM confiável, `noite` → pré-abertura: P1 com o nível da memória atravessado → emergência calculada uma vez do preço de referência válido (bid/ask válidos, senão último `last`, senão preço da ficha) e gravada → 09:00 I3 → abertura além da emergência: a S executa e X3 espera (S cruzada); abertura aquém: X3 (S viva ao lado, B6) → f 0 → L3. **Seguro** |
| e | Cinco robôs entram no mesmo segundo, dois opostos | ciclo 1: P1 manda as cinco S → ciclo seguinte (S listada): E1 de cada um; O2 enxerga as E do mesmo ciclo pelo mapa → a que cruzaria recebe `ENTRADA_RECUSADA(autoneg)`. Deal da E do C1 atrasado com a ordem já `FILLED`: Δ explicado pela linha do C1, os outros seguem confiáveis; sem o `FILLED`, todos RESTRITOS até o casamento (sem S nova duplicada, sem X). **Seguro; atraso ≤ alguns ciclos** |
| f | Corte com a cruzada aberta e uma X sem desfecho | [C, C+2): só o robô da X fica RESTRITO, os outros saem por X3 → C+2: fichas encerradas; K das limites; X com mais de 30 s → `C_CONTA(|liquida|)` → `liquida` 0 → K das S. **Seguro; sem depender do histórico** |
| g | A E do DM enche com o K do TTL em voo | K resolve "executou antes" → `ENTRADA_EXECUTADA` → DM MANTER(stop reancorado) → P3 move a S. K vence → `ENTRADA_CANCELADA` → L3 cancela a S. **Seguro** |
| h | O MT5 reinicia às 18:19 com uma X pendente e a cruzada aberta | INVALIDO 10 s → robôs provados confiáveis, o da X RESTRITO → 18:20 I1 nos confiáveis → 18:22 motor da conta só com a base → `C_CONTA`, S canceladas antes de F. Reinício depois das 18:22: o motor age no primeiro ciclo com base. **Seguro** |
| i | O dono desliga dois robôs posicionados | `REASON_PARAMETERS`, memória gravada → INVALIDO 10 s → I5 CONGELADA mantém E vivas e S → `Init` → os desligados sem `pode_entrar`, gerindo até zerar. **Seguro; nenhuma E perdida** |
| j | Cruzada aberta por 5 min com 3 fichas | todos provados → todos RESTRITOS por 30 s (Δ ainda não estável) → Δ externo virtual: os três confiáveis, módulos rodando, bloqueio automático de entradas, S e A preservadas; histórico ilegível → todos RESTRITOS, S vivas, P1 com lado inequívoco impossível (sem histórico) → 60 s bloqueio cancela E vivas → 10 min botão → corte pela conta. **Seguro** |
| k | A S executa, o deal chega 3 s depois, o robô pede saída | **posição já em 0:** S SUMIDA, Δ_resto ≠ 0 com robô não provado → todos RESTRITOS; lado inequívoco falha (sinal da líquida difere) → nada sai → deal em 3 s → EXECUTADA, f 0, SAIR cumprido. **Ordem `FILLED` sem deal:** Δ_resto = 0, só esse robô RESTRITO. **Posição também atrasada:** S SUMIDA, ausência contada de `sumida_msc`, o deal chega antes dos 30 s. **Seguro** |
| l | A correção é recusada repetidas vezes | P1 põe a S do lado certo (emergência gravada uma vez, sem perseguir o preço) → X3 recusada, espera 5 s, as linhas de baixo dão Z → ALERTA na 5ª e a cada 5 min → C + 2 min: `C_CONTA`, que se recusado também espera 5 s (sem rajada). **Seguro** |
| m | A corretora recusa por 20 min as ordens de um robô; os outros 4 operam | sem posição: S recusada → espera 5 s → `ENTRADA_PERDIDA` aos 10 s → sem `pode_entrar`, nada mais; S aceita e E recusada → `ENTRADA_RECUSADA`, `id_entrada` consumido → L3 cancela a S. Posicionado: X3 a cada 5 s, `SAIDA_EXPIRADA` aos 60 s; `MOVE_S` recusado mantém a S antiga. **S recusada com ficha aberta:** P1 a cada 5 s com ALERTA → aos 60 s sem S aceita, I3 SAIR → X3 a mercado com o magic do robô (guardas de nunca duas saídas) → recusada também → `RETENTA` a cada 5 s, P1 seguindo em paralelo → C + 2 min: `C_CONTA`. Os outros 4: linha RECUSADA não é pendente, não mexe em `provado`, Δ nem `confiavel`. **Seguro: no máximo 60 s sem stop, depois saída** |
| n | Deal da E de compra chega antes da posição (N-1) | ciclo 1: deal +1 visível, `liquida` 0 → todos provados, Δ_resto = −1, não estável → todos RESTRITOS: nenhuma absorção, nenhum bloqueio, L3 não age (S e A intactas) → ciclo 2 (ms depois): `liquida` +1, Δ_resto = 0 → todos confiáveis, f +1 LEGITIMA, S viva desde antes da E. Só se Δ persistir 30 s vira externo virtual, que mesmo assim não cancela S nem A. **Seguro** |

## 9. Achados × mecanismo

Mecanismos: **[S]** base e confiança por robô (§1.1, §2.2) · **[M]** mapa persistido, papel fixo, casamento antes das fichas (§1.2, §2.1) · **[T]** tabela com guardas próprias e espera por papel (§4) · **[N]** nível com lado (§4.3) · **[I]** intenção e eventos (§1.4, §7) · **[C]** motor de corte (§5) · **[K]** trava (§1.6) · **[P]** memória.

| Achados | Mecanismo |
|---|---|
| RV C-1; R1 A-3; R2 M-6 | [M] casamento de ticket 0 contra vivas, histórico em qualquer estado e `request_id`, antes das fichas; sem preço para mercado |
| RV A-1, B-15; R3 B-11 | [T] espera por papel, guardas "sem A/E viva", "sem K pendente" em X3, E1 e nas linhas de K |
| RV A-2, M-9; R3 M-4 | [M] SUMIDA com `sumida_msc`; `reduz_pend` inclui S; conexão "nos últimos `PROVA` s" |
| RV A-3, A-8, M-14; R1 C-2 | [N] cadeia com lado e preço; emergência sempre colocável; P1 em RESTRITO com lado inequívoco |
| RV A-4, M-4, M-6; R2 B-9 | [I] `pode_entrar` único; `id_entrada`; `ENTRADA_EXECUTADA`; prazo contado em ciclos confiáveis; rearme = id novo |
| RV A-5, A-6, M-13; R2 A-1; R3 A-1, A-2, B-1, B-2 | [C] fichas encerradas em C + 2 min; conta só com a base; `C_CONTA` não espera K; S só com líquida 0 |
| RV A-7 | §2.4 bloqueio cancela as E de todos |
| RV M-1 | I5: CONGELADA conta como ENTRAR com os parâmetros da E viva |
| RV M-2 | TRANSITORIA eliminada: é TROCADA (§11) |
| RV M-3; R2 B-3 | P2 com parênteses; S sempre de volume 1; P2 só até `cobertura` = \|f\| |
| RV M-5; R2 M-7 | ENTRAR com `expira`; validade decidida na partida |
| RV M-7 | O2 também contra o mapa |
| RV M-8, M-16; R1 M-10; R3 M-3 | [S] confiança por robô; L3 por prova inclui E `CANCELED` sem deal; bloqueio aos 60 s cancela E |
| RV M-10 | `HistorySelect` até agora + 1 dia |
| RV M-11; R2 M-8; R3 M-5 | [K] heartbeat em volta do `OrderSend`, `HB_TOMADA` 60 s, tomada atômica, memória recarregada |
| RV M-12 | A1/A2 com `reduz_pend` falso e sem M pendente |
| RV M-15 | §7: getters da vista ficam; `StopRegra(r, lado)` |
| RV B-1, B-2, B-3, B-4, B-5, B-7 | texto corrigido; uma lista de estado (§1.2); SAIR com `alvo`; `PRAZO_BOTAO` com nome |
| RV B-6 | ambiente no primeiro snapshot; trava recusada no `OnInit` fica inerte e só faz `ExpertRemove` com heartbeat alheio avançando (§1.6) |
| RV B-8, B-11, B-12 | [M] folga 5 s, sem preço para mercado; deal sem ordem = não classificado até a ordem aparecer, sem prazo; M acompanha ticket novo (P4) |
| RV2 N-1 | [S] Δ externo só depois de `PROVA` estável; antes, todos RESTRITOS; absorção virtual sem botão e sem L2/L3 |
| RV2 N-2 | [N] emergência calculada uma vez, gravada, nunca movida; cadeia inclui a S viva |
| RV2 N-3 | [N] preço de referência validado (bid/ask, depois `last`, depois a ficha); X3 espera S cruzada |
| RV2 N-4 | [M] deal MAESTRO = encerramento: fichas 0, sem absorção nem bloqueio |
| RV2 N-5 | [K] trava recusada = inerte e tenta de novo; remoção só com heartbeat alheio avançando |
| RV2 N-6 | [C] `em_espera[MAESTRO]` com `RETENTA` e ALERTA para `C_CONTA` e K da conta |
| RV2 C-1 residuais | [M] casamento exclui tickets já gravados; deal antes da ordem espera a ordem; NAO_EXECUTADA vira EXECUTADA se o deal aparece |
| RV2 mudança D | `TICK_WIN` constante; nenhuma divisão por tick lido |
| RV2 cenário m | I3 com `PRAZO_S_RECUSADA` → X3 (decisão m) |
| RV B-9 | §3: E pode sair no ciclo seguinte |
| RV B-10 | retenção do mapa por episódio aberto |
| RV B-13 | §3 passo 6: ALERTA a cada 5 min |
| RV B-14 | §11: PROTEGENDO faz correção e zeragem |
| R1 C-1, B-5 | [T] S de entrada por P1 antes de E1; S recusada retentada |
| R1 A-1; R2 M-5 | [M] robô pelo mapa/`ORDER_MAGIC`; não classificado = RESTRITO até a ordem aparecer |
| R1 A-2, A-6; R2 M-1; R3 B-5 | [I] NADA repete o cancelamento (L1); limpeza só por evento; A1 recria o alvo; `EXECUTOU_ANTES` não existe |
| R1 A-4, M-2, B-11; R2 B-6, B-7 | [S] falha de base = INVALIDO, de histórico = RESTRITO; releitura no máximo a cada 10 s |
| R1 A-5, B-12 | [I] `Tick` desde a pré-abertura; hora pela vista |
| R1 M-1; R2 A-3, M-4; R3 M-1, B-3 | [M] papel fixo, nunca E sem mapa; indeterminada não existe |
| R1 M-3; R2 B-8; R3 B-4, B-6, B-7 | [M] sem espera no ciclo; prazo por linha; `FILLED` = executada; só recusa real conta |
| R1 M-5; R3 B-8 | [S] não NETTING = INVALIDO; PROTEGENDO = I5 |
| R1 M-6 | o botão não apaga o mapa |
| R1 M-9; R2 A-4 | [P] ALERTA; só E e A barradas |
| R2 A-2; R3 M-2, M-6; R1 B-4 | [I] SAIR mantido com `PRAZO_SAIR`; sem códigos de retorno |
| R2 M-2 | [P] `externa_desconhecida` na memória antes do primeiro ciclo |
| R2 M-3 | [C] passo 3 |
| R2 B-1, B-2; R1 B-1 | eventos só depois do `Init`; A só em A1 (contínuo, não noite) |
| R1 B-2 | X1 cancela o A na correção; A1 recria |
| R1 B-3; R2 B-4; R3 B-9 | [P] deals logados e absorções por ticket |
| R3 B-10 | [M] A `FILLED` = EXECUTADA: `reduz_pend` barra X3 |
| R3 §6 (testes) | suíte refeita: um teste por linha de §4.2, §2.1 e §5, e os 14 cenários do §8, sobre a `CorretoraFalsa` |
| R1 M-4, M-7, M-8, B-6–B-10; R2 B-5 | continuam como estão (feriado = `MARKET_CLOSED` retentado; AJUSTE; constantes; ms; arrays; `FILE_UNICODE`; classe real fora do teste; retcodes; P12) |

## 10. Tamanho e remoções

| Arquivo | Hoje | v2.2 |
|---|---|---|
| `Snapshot.mqh` (leitura, base, janela) | — | ~200 |
| `Mapa.mqh` (linhas, casamento, desfecho) | — | ~300 |
| `Estado.mqh` (fichas, absorção, Δ, confiança) | — | ~300 |
| `Decide.mqh` (intenção efetiva, tabela, nível, corte) | — | ~380 |
| `Envia.mqh` (request, registro antes, retcodes) | — | ~180 |
| `Partida.mqh` (trava, ambiente, `PRONTO`), no lugar de `Recupera.mqh` | 528 | ~150 |
| `Fichas.mqh` | 2.722 | removido |
| `Corretora.mqh`, `CorretoraFalsa.mqh`, `Memoria.mqh`, `Log.mqh`, `Grade.mqh`, `Inputs.mqh` | 1.090 | ~1.120 |
| `WinMaestro.mq5` | 226 | ~180 |
| 5 módulos | 3.654 | ~3.400 |

Núcleo: 3.250 → ~1.510 linhas; nenhuma global de estado por robô.

**Removido:** `Mae_Fase1`/`Mae_Fase2` e a cadeia de `return`; `Mae_CorteConta`/`mzCorteConta`; `Mae_EstadoFecha`, `Mae_PodeEntrar` e os portões de `Mae_Modifica`, da recriação de alvo e do nível atravessado; as funções de envio `Ficha_*` e os códigos de retorno; `mzSaidaPedida`/`mzSaidaFid`, `mzECancelPedido`, `mzIndet`/`mzIndetDesde`, `Mae_FichaEm`/`mzCk`, a classificação por comentário, `mzMagic0Pend`, `mzCorrTravada`, `mzTravaPerdida`, `mzEpisodio`, `EV_EXECUTOU_ANTES`, os contadores compartilhados de `Mae_Recusa`, os passos 6–9 de `Recupera` e a espera de 5 s. Nos módulos: `VerificarStop` (DM), `LimparAlvoOrfao`/`ZerarPregao` (RE), `PendentesNossas`/`Zerar` (GB), `Evento(EXECUTOU_ANTES)` (RE).

## 11. Decisões

**Do dono, 2026-10-07:**
1. Correção de ficha trocada ou duplicada nunca trava; a 2ª em 10 min só liga o bloqueio de entradas com botão (I2, §2.4). Decidido pelo dono 2026-10-07.
2. O corte zera a líquida real do símbolo, posição manual do dono incluída (§5). Decidido pelo dono 2026-10-07.
3. Ordem sem ticket ausente por 30 s com conexão ok é não executada, sem a cruzada; o prazo sobe se P6/P18 mostrarem atraso maior (§2.1). Decidido pelo dono 2026-10-07.
4. Entrada até 10 s, saída 60 s (§4.1). Decidido pelo dono 2026-10-07.
5. Sem memória e sem log, ficha cuja entrada não está no mapa é TROCADA e zerada (§1.2). Decidido pelo dono 2026-10-07.
6. Proteção sem portão: S sempre que o lado do robô é inequívoco (§2.2, P1), uma por vez. Decidido pelo dono 2026-10-07; nesta versão aplicada robô a robô, que é a forma equivalente e mais simples.
7. Validade da entrada do GB escolhida na partida (§4.2 E1). Decidido pelo dono 2026-10-07.
8. **C. Prova por ausência de 30 s também para ordem com ticket** (sem a cruzada), §2.1. Ressalva registrada: o pior caso é uma X que executou e ficou mais de 30 s fora do histórico ser reenviada, a ficha inverter 1 contrato e I2 corrigir; a linha vira EXECUTADA quando o deal aparece. Decidido pelo dono em 2026-10-07.
9. **m. S recusada com a ficha aberta:** depois de 60 s sem a S aceita, o robô sai a mercado com o próprio magic (I3 → X3, com as guardas de nunca duas saídas); se a saída também for recusada, segue a `RETENTA` e o corte resolve. Decidido pelo dono em 2026-10-07.

**Mudanças de spec que esta versão introduz, aceitas pelo dono:**
- A. Sem estado "transitório da entrada" (spec 5.3): S executada antes da E é TROCADA; cancela a E e corrige. Resultado econômico igual. Decidido pelo dono em 2026-10-07.
- B. Nível de S já atravessado → S de emergência a partir do preço de referência, gravada uma vez, em vez de "nenhuma S" (spec 9.3). Decidido pelo dono em 2026-10-07.
- D. PROTEGENDO faz correção e zeragem do robô, além de S, cancelamentos e corte (spec 10.2; R1 M-5). É o que fecha R3 A-2. Requisito: nenhuma divisão pelo tick lido (`TICK_WIN`). Decidido pelo dono em 2026-10-07.
- E. Trava (spec 10.3): heartbeat de 60 s; a recusa deixa o EA inerte tentando de novo, e só remove com outra instância comprovadamente viva. Decidido pelo dono em 2026-10-07.

**Da revisão de código 1 (v2.01), 2026-10-07.** O dono mandou corrigir todos os achados de `WinMaestro_v2_revisao_codigo_1.md`; as regras do desenho que mudaram com isso:
- **M-1. Δ externo estável conta pelo valor de Δ_resto** (§2.2): o mesmo valor há `PROVA`, com histórico lido e conexão ok, basta; não exige mais todos os robôs provados. Um robô não provado já não é confiável por conta própria, e uma diferença externa duradoura não pode congelar todos a cada ordem de qualquer um. Zera só quando o valor muda, o histórico falha ou a conexão cai. Decidido pelo dono em 2026-10-07.
- **M-5. X3 tem prazo próprio** (§4.2): a S em nível já cruzado e viva há `PROVA` sem executar é cancelada (K, linha X3); provado o K, P1 repõe a S no nível válido da cadeia e X3 sai. `PROVA` e não mais, porque o `SAIR` do módulo expira em `PRAZO_SAIR` (60 s). Nunca duas saídas: X3 continua exigindo nenhum K pendente e nenhuma S cruzada. Decidido pelo dono em 2026-10-07.
- **A-1. Regra de saída de `externa_desconhecida`** (§1.2): zera no dia novo (a janela recomeça e o corte da véspera deixou a líquida em 0) e, no mesmo dia, quando `liquida` = 0 e os deals da janela somam 0 por `PROVA` seguidos com o histórico lido. Com o deal de fechamento dentro da janela ela fica até o dia novo, porque é ela que explica esse deal. Decidido pelo dono em 2026-10-07.
- **A-2. Recusa assíncrona** (§3 passo 6): REJECTED no histórico depois de aceita = a mesma recusa do retcode (espera `RETENTA`, contagem, ALERTA na 5ª). A prova por ausência liga só a espera, sem contar como recusa. A contagem só zera com aceite provado: a ordem executou, ou está VIVA há `RETENTA`, e foi enviada depois da última recusa. Decidido pelo dono em 2026-10-07.

**Da revisão de código 2 (v2.02), 2026-10-07.** O dono mandou corrigir todos os achados de `WinMaestro_v2_revisao_codigo_2.md`; as regras do desenho que mudaram com isso:
- **B2-1. A prova por ausência conta como recusa** (§3 passo 6; muda a A-2): além da espera de `RETENTA`, entra na mesma contagem de recusas seguidas do dono e papel, e a 5ª dispara o ALERTA. Uma corretora que descarta ordens em silêncio passa a ser vista. A contagem continua zerando só com aceite provado. Decidido pelo dono em 2026-10-07.
- **B2-2. O prazo da X3 conta desde que a S ficou cruzada** (§4.2, M-5): o relógio é atualizado em todo ciclo com a base firme, com qualquer intenção, e volta a 0 quando a S deixa de estar cruzada. Um SAIR que chega com a S cruzada há menos de `PROVA` espera o resto; um SAIR posterior nunca herda o relógio de um cruzamento anterior que já terminou. Decidido pelo dono em 2026-10-07.
- **B2-3. Ficha aberta nunca fica sem S por emergência atravessada** (§4.3; muda a escolha "emergência atravessada → sem S nova"): com a emergência gravada já atravessada e nenhum candidato válido, a S vai ao primeiro nível válido além da referência (compra: o maior nível < referência − piso; venda: o menor > referência + piso), S DAY como toda S. A emergência gravada não é recalculada nem movida. A saída continua tentando com `RETENTA`. Com `f` = 0 (S de uma E) não sai S, porque uma S colada no preço abriria posição ao disparar. Decidido pelo dono em 2026-10-07.
- **B2-4. A absorção virtual vai ao robô cuja ordem explica o Δ** (§2.2; complementa a M-1 e a decisão C): candidata = linha E/S/A/X de robô, sem deal na janela, do lado de Δ, que estava sem desfecho quando o Δ apareceu (PENDENTE ou SUMIDA, ou NAO_EXECUTADA por ausência, nunca vista no histórico como CANCELED/REJECTED/EXPIRED), enviada ou sumida até `PROVA` antes do início do Δ e não depois dele, de robô com ficha do lado que Δ reduz. Um único robô com candidata absorve primeiro (até a ficha dele); o que sobrar, e todo Δ sem atribuição única (nenhum robô ou mais de um), segue a ordem fixa GB, CM, DM, RE, C1 da regra 7.1, como a revisão 2 registra: o robô absorvido por engano conserva a S (L2 e L3 barradas por `abs_virtual`) e o bloqueio automático segura as entradas, na mesma janela de risco da decisão C. Decidido pelo dono em 2026-10-07.
- **B2-5.** A E aceita no envio e REJECTED no histórico chega ao módulo como `ENTRADA_RECUSADA` (antes: `ENTRADA_CANCELADA`). Decidido pelo dono em 2026-10-07.
- **Memória.** A v2.02 lê a memória gravada pela v2.01 (formato igual); a de versões anteriores continua ignorada. Decidido na implementação da v2.02 (2026-10-07): sem isso a troca de versão no meio do dia apagaria o bloqueio com botão e os episódios abertos.

**Pergunta à corretora/plataforma (continua aberta):** o `ChartID` sobrevive a um reinício do terminal? Se não, o token muda e a retomada depende só do heartbeat parado (§1.6). A implementação é segura para as duas respostas: mesmo token → retoma na hora; token diferente → inerte até o heartbeat alheio ficar parado `HB_TOMADA` (até 60 s sem atividade do EA depois de um reinício do terminal). Decidido pelo dono em 2026-10-07 deixar como pergunta.
