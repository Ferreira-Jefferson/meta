# WinMaestro v2.03

v2.03 (2026-10-08): **parada diária**. Quando o resultado líquido realizado do dia dos robôs chega a −`Risco_PerdaDiaPct`% de `Risco_Capital` (padrão −10% de R$1.000 = −R$100), nenhuma entrada nova sai até o pregão seguinte; as posições abertas seguem normalmente. Ver "Parada diária" abaixo.

v2.02 (2026-10-07): todos os achados da revisão de código 2 corrigidos (`WinMaestro_v2_revisao_codigo_2.md`; achado por achado em `WinMaestro_implementacao_notas.md` §10).

v2.01 (2026-10-07): todos os achados da revisão de código 1 corrigidos (`WinMaestro_v2_revisao_codigo_1.md`; o que mudou, achado por achado, em `WinMaestro_implementacao_notas.md` §8).

EA único para o mini índice (WIN) em conta NETTING. Roda os 5 robôs ao mesmo tempo. Cada robô tem a sua **ficha** (posição virtual = soma dos deals com o magic dele) e manda as ordens dele com o magic dele, de modo que a posição líquida da conta é sempre a soma das fichas mais a exposição externa (manual).

| Robô | Origem | Tempo | Magic | Stop na corretora |
|---|---|---|---|---|
| GB | WinGapBarra1 v1.01 | M5 | 80080601 | S a `GB_StopPts` da limite |
| CM | WinCincoMedias v2.05 | H2 | 80080501 | S de reserva a 4.945 pts, movida ao "stop que aperta" |
| DM | WinDeslocamentoMatinal v1.31 | M1 | 80080101 | S no nível do stop, pré-calculada na entrada e reancorada no preenchimento |
| RE | WinRetanguloEma34 v1.07 | M15 | 20261005 | S pré-calculada, reancorada no preenchimento; alvo limite que se aproxima |
| C1 | Win_c1 v2.07 | H1 | 80080002 | S enviada antes da entrada a mercado; trailing por H1 |

O corte da conta usa o magic 80089999 (MAESTRO).

## Como funciona

A lógica de sinal de cada robô é a do EA avulso. Cada robô **declara o que quer** (entrar, manter com tal stop e alvo, sair, nada) e o maestro executa:

- A cada ciclo (250 ms, cada tick e cada transação) o maestro lê **um** retrato da corretora: posição, ordens vivas e histórico do dia. Casa cada ordem que mandou com o que a corretora mostra, calcula as fichas pelos deals e decide se confia no que leu.
- Faz **no máximo uma ação por robô por ciclo**, por prioridade fixa: proteção (a S) > saída > limpeza > alvo > entrada.
- **Toda entrada nasce com o stop na corretora**: a S sai primeiro, e a entrada só sai com a S viva.
- **A S só é cancelada depois** que a saída executou. Nunca sai uma segunda saída enquanto a primeira não tem desfecho.
- Um robô cujo estado o maestro não consegue provar fica **RESTRITO**: só protege (cria ou move a S) e só cancela o que é seguro. Os outros seguem.
- Se a corretora recusar a S de um robô posicionado por 60 s, ele sai a mercado. Recusa que chega depois do envio (a ordem é aceita e a bolsa rejeita) e ordem que some sem resposta por 30 s são tratadas como a recusa imediata: espera de 5 s e ALERTA na 5ª seguida. Entrada rejeitada depois do envio chega ao robô como entrada recusada.
- Um stop que o preço já atravessou é a saída do robô: o maestro espera ele executar. Se em 30 s (contados desde que o preço o atravessou) ele não executar, o maestro cancela esse stop, põe outro válido e sai a mercado. Se até o stop de emergência já foi atravessado, o stop novo vai ao primeiro nível válido junto do preço; com a saída recusada, ela é tentada de novo a cada 5 s e esse stop fica protegendo.
- A partir de **C + 2 min** (C = fim do contínuo − 5 min) só o motor da conta age: cancela as limites dos robôs, zera a posição líquida do símbolo (inclusive a manual) e depois cancela os stops.

## Arquivos

- `mt5/WinMaestro.mq5` e a pasta `mt5/WinMaestro/` (núcleo: `Tipos`, `Snapshot`, `Mapa`, `Estado`, `Decide`, `Envia`, `Partida`, `Risco`; apoio: `Corretora`, `Memoria`, `Log`, `Grade`, `Inputs`, `RiscoRegra`; um `.mqh` por robô).
- Desenho: `WinMaestro_ARQUITETURA_v2.md`. Regras de negócio: `WinMaestro_ESPECIFICACAO.md`. Notas: `WinMaestro_implementacao_notas.md`.
- A v2.02 é recuperável pelo git (último commit com ela: `cd96a56`, ex.: `git show cd96a56:mt5/WinMaestro.mq5`). A v1.03 saiu do repositório na limpeza de 2026-10-07 (recuperável pelo git: `git show 257b1e4:mt5/WinMaestro_v1.03_historico/...`).

## Instalação

1. A pasta `MQL5\Experts\` do terminal já tem `WinMaestro.mq5`, `WinMaestro.ex5` e a pasta `WinMaestro\` (o `.ex5` já compilado serve).
2. Abra **um** gráfico do contrato vigente (ex.: WINV26). Qualquer tempo gráfico serve.
3. Arraste o WinMaestro para o gráfico, marque "Permitir Algo Trading" e confira os inputs.
4. Espere a linha `PRONTO` no log: a partida espera 10 s de conexão estável. Cada robô começa a operar no primeiro ciclo em que o estado dele está provado.

### Checklist antes da primeira partida

- [ ] **Nenhum outro EA rodando em nenhum gráfico** do terminal, só o WinMaestro. Vale para qualquer EA, inclusive o **WinSeletor**, a **v1.03**, os avulsos (WinGapBarra1, WinCincoMedias, WinDeslocamentoMatinal, WinRetanguloEma34, Win_c1) e o WinSimulador. Dois programas mandando ordens com os mesmos magics quebram as fichas.
- [ ] Os `.ex5` do WinSeletor e dos EAs avulsos fora da pasta `MQL5\Experts`, para não serem anexados por engano.
- [ ] O WinMaestro em **um gráfico só**, num terminal só, num PC só.
- [ ] Conta NETTING (conta hedging deixa o EA sem mandar nada).
- [ ] Sem SL/TP posto à mão na posição líquida, a não ser de propósito: se executar, o maestro trata como zeragem manual (bloqueia entradas até o botão).
- [ ] Na rolagem do contrato: troque o gráfico para o contrato novo. A memória é por símbolo e começa limpa.
- [ ] A memória gravada pela v2.02 e pela v2.01 é lida pela v2.03 (mesmo formato; a parada diária não grava nada, sai do histórico do dia): trocar a versão conserva o mapa das ordens, os níveis e o bloqueio. **O contrário não vale:** a v2.02 não lê a memória gravada pela v2.03 e parte sem ela; voltar para a v2.02 só com a conta zerada e sem ordens dos robôs. A memória da v1.03 e a da v2.00 não são lidas: na primeira partida, sem posição nem ordem dos robôs aberta é o caso limpo. Com posição aberta da v1.03, a partida reconstrói o que puder do histórico; entrada sem registro vira ficha trocada e é zerada.

## Inputs

O grupo **Maestro** fica no topo, com os 5 liga/desliga `Ativo_GB` … `Ativo_C1` (padrão: ligados). Desligado: o robô não abre nada novo; se tiver ficha ou ordem viva, continua gerindo até zerar.

No mesmo grupo, a parada diária:

| Input | Padrão | O que é |
|---|---|---|
| `Risco_Capital` | 1000 | Capital em R$ sobre o qual a parada é calculada. Fixo, digitado pelo dono; **não** é o saldo da corretora |
| `Risco_PerdaDiaPct` | 10.0 | Perda do dia, em % do capital, que liga a parada. **0 desliga** |

Depois vêm os grupos dos robôs, iguais aos do WinSeletor, sem os inputs de magic, de lote (lote fixo = 1), `GB_ServerGMTOffsetH`, `GB_RegimeAutomatico`, `GB_FimContinuoMin` (o fim do contínuo vem da grade B3 embutida) e `RE_LimiteEquity`. `DM_RiscoMaxPct` vale sobre R$1.000 fixos.

Mudar qualquer input reinicia o EA. Nada é cancelado nem fechado por isso: a memória guarda o mapa das ordens e os níveis pedidos.

## Parada diária

- **Resultado do dia** = soma do resultado realizado **hoje** por cada robô, calculado como se cada um tivesse conta própria: preço médio da ficha do robô; cada negócio que reduz a ficha realiza (preço de saída − preço médio) × lado × contratos × valor do ponto (`SYMBOL_TRADE_TICK_VALUE` / `SYMBOL_TRADE_TICK_SIZE`, R$0,20 no WIN), mais comissão + taxa + swap dos negócios do robô. Ficha aberta ontem e fechada hoje: o preço de entrada é o da ficha e só o realizado hoje conta. Posição aberta (flutuante) não entra. Ganhos compensam perdas.
- **Não usa o lucro que a corretora põe no negócio** (`DEAL_PROFIT`): em conta NETTING ele é o da posição LÍQUIDA que o negócio reduziu, que pode ser de outro robô ou sua. Caso real de 2026-10-08 na demo: com −3 vendidos à mão, a entrada do CM (compra 1) recebeu −R$543,67 de lucro da corretora, que eram o prejuízo da venda manual; para o maestro o resultado do CM nesse negócio é R$0.
- O valor do ponto que o EA usa aparece na linha `RISCO` do log na partida e no painel: confira que é R$0,20.
- **Zeragem manual de uma ficha de robô** (absorvida, spec 7.1) conta como saída do robô ao preço do negócio manual: o que o robô ganhou ou perdeu até ali entra no dia dele. **O corte da conta** (`C_CONTA`) também: cada ficha zerada por ele sai ao preço dele. A comissão do negócio manual e a do `C_CONTA` não são de nenhum robô e não entram. Negócio manual que não zera ficha de robô não entra.
- A parada **liga** quando o resultado acumulado do dia fica **menor ou igual** a −`Risco_PerdaDiaPct`% de `Risco_Capital` (com os padrões: −R$100,00 para; −R$99,90 não para).
- Ligada: as entradas vivas que ainda não executaram são canceladas e nenhuma entrada nova sai. **Nada é fechado**: stops, saídas, alvos, zeragens, correções e o corte seguem normalmente.
- Vale **até o pregão seguinte**, mesmo que um ganho depois traga o resultado de volta para cima do limite. Um negócio que zera várias fichas de uma vez conta uma vez só, pela soma. No dia seguinte sai sozinha (não precisa do botão).
- Não depende de memória: liga pelos negócios do dia e, ligada, fica presa até a data mudar. Reiniciar o EA no meio do dia refaz a conta pelos negócios do dia (com a perda no histórico, a parada volta). Funciona igual no Testador.
- **Saída de emergência:** pôr `Risco_PerdaDiaPct` = 0 no meio do dia reinicia o EA e desfaz a parada.
- O painel mostra o resultado do dia total e por robô; a linha `RISCO` do log, ao ligar, também.

## Horários

| Robô | Zeragem (dias de 18:25) | Zeragem (dias de 17:55) |
|---|---|---|
| GB | 18:20 | 17:50 |
| CM | 18:20 | 17:50 |
| DM | fim da sessão do símbolo − `DM_MinutosZerar` (sem sessão: `DM_HoraFimPregao:DM_MinutoFimPregao` − `DM_MinutosZerar`), limitado ao corte: 18:20 | 17:50 |
| RE | 17:00 | 17:00 |
| C1 | 17:50 | 17:50 |

- Ordens só saem da pré-abertura (08:55) até 15 min depois do fim do contínuo. Entradas, alvos e saídas a mercado só no contínuo.
- **C** (18:20 ou 17:50): toda ficha aberta sai a mercado.
- **C + 2 min**: motor da conta (acima). Depois do fim do contínuo nenhuma ordem a mercado sai; as limites são canceladas e os stops ficam enquanto houver posição.
- **Ficha que atravessou a noite** (EA fora no corte): na pré-abertura nasce uma S nova (se o nível pedido já foi atravessado pelo gap, uma S de emergência 1.200 pts além do preço); no primeiro momento do contínuo a ficha sai.
- Em feriado a corretora recusa as ordens com "mercado fechado": o maestro retenta a cada 5 s.
- Os prazos (30 s, 60 s, 10 min…) são medidos num relógio que não salta (`GetTickCount64`); o relógio do PC só dá o horário da grade. Se o horário do servidor que o terminal calcula divergir do instante do último tick em mais de 2 s, sai um ALERTA `AMBIENTE` ("confira o relógio do PC").

## Log

Pasta: `MQL5\Files\WinMaestro\<servidor>_<conta>_<símbolo>\` (no Testador, `MQL5\Files\WinMaestro_teste\`, apagada a cada teste).

- `logs\AAAA-MM-DD.log`: uma linha por evento, gravada na hora. Formato `HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe | [tick ... loc ...]`. As linhas `ORDEM` (envio e retorno) também servem para refazer o mapa se a memória se perder.
- `logs\AAAA-MM-DD_trans.log`: uma linha bruta por transação do símbolo.
- `estado.txt` / `estado.bak`: a memória. Não edite.

Níveis: `INFO`, `AVISO`, `ALERTA` (também abre a janela de `Alert()`), `ERRO`. Uma condição que se repete é logada ao começar, a cada 5 min e ao terminar.

| Evento | Significa |
|---|---|
| `PRONTO` | Primeira leitura completa; ficha e níveis de cada robô; cada módulo iniciado |
| `INTENCAO` | O que o robô quer, e de onde veio (I1 corte, I2 correção, I3 zeragem/noite/stop recusado, I4 bloqueio, I5 congelada, I6 módulo) |
| `ORDEM` | Envio (com a linha da tabela que pediu: P1, X3, E1…) e retorno de cada ordem |
| `DESFECHO` | Como cada ordem foi resolvida e a prova |
| `EVENTO` | Aviso ao módulo: entrada executada, cancelada, recusada, perdida; saída expirada |
| `ENTROU`, `SAIU`, `EXTERNA`, `ABSORVIDA` | Cada deal, com papel; deal manual; zeragem manual absorvida nas fichas |
| `STOP` | Nível pedido; S de emergência |
| `ESTADO` | INVALIDO (conexão, trava) ou robô RESTRITO há muito tempo |
| `RISCO` | Na partida, a configuração da parada diária; depois, a parada diária ligada (resultado, limite) e desligada (pregão novo) |
| `CORRECAO`, `BLOQUEIO`, `DESBLOQUEIO`, `CORTE`, `EPISODIO`, `TRAVA`, `MEMORIA`, `AMBIENTE`, `DECISAO PERDIDA`, `AUTONEG` | o que o nome diz |

## Painel e botão

O canto do gráfico mostra (só leitura): estado do EA (ok, INVALIDO, INERTE, PROTEGENDO, PARADO), líquida, externa, diferença entre a líquida e os deals, hora do corte, bloqueio (`parada diaria (perda do dia)` quando é ela; `<motivo> + parada diaria` com o botão e a parada juntos), o resultado do dia em R$, em % do capital e por robô, o valor do ponto, com a situação da parada (desligada, não atingida, ATIVA) e, por robô, ficha, situação, preço, S pedida, alvo, entrada viva e intenção.

**Diferença externa gravada pelo botão** (`externa` no painel): quando o botão é usado com uma diferença estável entre a líquida e os deals do dia (uma posição manual anterior ao dia, por exemplo), ela fica gravada para explicar essa posição. Ela deixa de valer sozinha no dia seguinte e, no mesmo dia, quando a líquida e os deals do dia ficam em 0 por 30 s.

Com **bloqueio de entradas que exige o botão** aparece o botão **Desbloquear** (canto superior direito), com dois cliques em até 3 s. Antes de clicar, olhe o extrato da corretora. Causas: zeragem manual da posição; robô RESTRITO há 10 min; segunda correção do mesmo robô em menos de 10 min. Durante o bloqueio as entradas vivas são canceladas e nenhuma entrada nova sai; stops, cancelamentos, saídas, zeragens e correções continuam. O bloqueio automático (robô RESTRITO há 60 s, diferença externa estável que absorveu ficha) sai sozinho.

## Comportamentos para ciência do dono

Diferenças pequenas em relação aos EAs avulsos, mantidas de propósito (detalhe nas notas):

- **DM**: o teto de risco (`DM_RiscoMaxPct`) é sobre R$1.000 fixos, não sobre o saldo. O stop é considerado atravessado com uma folga de 1 tick (o piso da corretora) e é reavaliado a cada tick: se uma saída expirou e o preço continua além do stop, o DM pede a saída de novo.
- **GB**: se o EA (re)partir entre 09:05 e a validade da entrada do GB, a entrada daquele dia é `DECISAO PERDIDA` (o avulso ainda mandaria).
- **C1**: o stop é validado contra o preço da decisão; se o preço entrar no piso do stop antes de a entrada sair, a entrada é recusada (o avulso mandaria com SL).
- **Todos**: decisão que chega mais de 120 s depois do seu momento (robô RESTRITO, sem tick) é `DECISAO PERDIDA`, para não entrar a mercado com uma cotação que não é a da decisão.
- **Corridas aceitas pelo desenho**: um stop de robô que dispara junto com o `C_CONTA` do corte inverte a líquida por até 30 s (o próximo `C_CONTA` corrige); uma saída de ticket 0 que executou e ficou mais de 30 s fora do histórico pode ser reenviada (a correção da ficha desfaz a inversão).

## Testes unitários

Parada diária (v2.03): `mt5/testes/WinMaestro_TesteParada.mq5`, script com 37 verificações sobre as mesmas funções que o EA usa deal a deal (`WinMaestro/RiscoRegra.mqh`). Regra da parada: fronteira (−10% para, −9,99% não para), dois ganhos e um stop grande, stop antes dos ganhos (fica parado no dia), capital R$7.000, input 0 e pregão seguinte. Resultado por robô: o caso real de 2026-10-08 (manual −3 + entrada do CM → CM R$0, não −R$543,67), dois robôs em lados opostos, inversão, ficha de ontem fechada hoje, preço médio, zeragem manual absorvida, `C_CONTA`, pior acumulado com dois robôs, um deal que realiza duas fichas (`C_CONTA` com lados opostos e absorção dupla: um evento só), absorção parcial, deal não classificado, absorção virtual, virada do dia e par AJUSTE. Para rodar: copie para `MQL5\Experts\testes\` com a pasta `WinMaestro\` da v2.03 ao lado, compile, arraste para qualquer gráfico e leia a aba Experts (`OK 37/37`). Não manda ordem nem lê a conta.

Removidos a pedido do dono em 2026-10-07 (`WinMaestro_Teste.mq5` + `WinMaestro/CorretoraFalsa.mqh`, 137 verificações com corretora falsa, nunca rodadas). Recuperar com `git show 988e8e4:mt5/WinMaestro_Teste.mq5` e `git show 988e8e4:mt5/WinMaestro/CorretoraFalsa.mqh`. O `#ifndef WINMAESTRO_TESTE` em `Corretora.mqh` ficou e não muda nada no EA de produção.
