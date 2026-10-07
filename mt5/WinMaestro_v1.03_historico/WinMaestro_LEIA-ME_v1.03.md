# WinMaestro v1.03

EA único para o mini índice (WIN) em conta NETTING. Roda os 5 robôs ao mesmo tempo. Cada robô tem a sua **ficha** (posição virtual = soma dos deals com o magic dele) e manda as ordens dele com o magic dele. Assim, a posição líquida da conta é sempre a soma das fichas mais a exposição externa (manual).

| Robô | Origem | Tempo | Magic | Stop na corretora |
|---|---|---|---|---|
| GB | WinGapBarra1 v1.01 | M5 | 80080601 | S a `GB_StopPts` da limite |
| CM | WinCincoMedias v2.05 | H2 | 80080501 | S de reserva a 4.945 pts, movida ao "stop que aperta" |
| DM | WinDeslocamentoMatinal v1.31 | M1 | 80080101 | S no `g_stopNivel` (pré-calculada, movida no preenchimento) |
| RE | WinRetanguloEma34 v1.07 | M15 | 20261005 | S pré-calculada, reancorada no preenchimento; alvo limite que se aproxima |
| C1 | Win_c1 v2.07 | H1 | 80080002 | S enviada antes da entrada a mercado; trailing por H1 |

A lógica de sinal de cada robô é a do EA avulso, e o cálculo dela roda sempre, como no avulso. Mudou só a execução:
- toda entrada nasce com uma ordem stop (S) na corretora, com o magic do robô e validade do dia. A S vai **antes** da entrada, e a entrada só sai com a S viva;
- o maestro confere posição líquida, ordens vivas e histórico antes de toda ordem; a proteção (a S) nunca espera por isso;
- cada robô tem no máximo uma operação por vez;
- uma saída pedida por um robô num instante em que o estado não fecha não se perde: o maestro a envia no ciclo seguinte (log `SAIDA ... adiada`);
- o maestro é o único dono das zeragens por horário.

## Arquivos

- `mt5/WinMaestro.mq5` e a pasta `mt5/WinMaestro/` (`Corretora.mqh`, `Fichas.mqh`, `Recupera.mqh`, `Memoria.mqh`, `Log.mqh`, `Grade.mqh` e um `.mqh` por robô).
- `mt5/WinMaestro_Teste.mq5` + `WinMaestro/CorretoraFalsa.mqh`: testes unitários com corretora falsa. Não vão para o EA de produção.

## Instalação

1. Copie `WinMaestro.mq5` e a pasta `WinMaestro\` inteira para `MQL5\Experts\` do terminal (o `.ex5` já compilado também serve).
2. Abra **um** gráfico do contrato vigente (ex.: WINV26). Qualquer tempo gráfico serve; M1 é o recomendado.
3. Arraste o WinMaestro para o gráfico, marque "Permitir Algo Trading" e confira os inputs.
4. Espere a linha `PRONTO` no log (dezenas de segundos: a partida espera 10 s de conexão estável e relê o histórico).

### Checklist antes da primeira partida

- [ ] Nenhum gráfico aberto com o **WinSeletor** ou com qualquer EA avulso (WinGapBarra1, WinCincoMedias, WinDeslocamentoMatinal, WinRetanguloEma34, Win_c1). Dois programas mandando ordens com os mesmos magics quebram as fichas.
- [ ] Os `.ex5` do WinSeletor e dos EAs avulsos removidos da pasta `MQL5\Experts` (ou movidos para fora dela), para não serem anexados por engano.
- [ ] O WinMaestro em **um gráfico só**, num terminal só, num PC só. Um segundo gráfico do mesmo terminal é recusado pela trava; outro PC ou VPS na mesma conta não é detectado.
- [ ] Conta NETTING (a partida recusa conta hedging).
- [ ] Sem SL/TP posto à mão na posição líquida, a não ser de propósito: se executar, o maestro trata como zeragem manual (bloqueia entradas até o botão).
- [ ] Na rolagem do contrato: troque o gráfico para o contrato novo. A memória é por símbolo e começa limpa.

## Inputs

O grupo **Maestro** fica no topo, com os 5 liga/desliga (padrão: todos ligados):

| Input | Efeito |
|---|---|
| `Ativo_GB`, `Ativo_CM`, `Ativo_DM`, `Ativo_RE`, `Ativo_C1` | Desligado: o robô não abre nada novo. Se tiver ficha ou ordem viva, continua gerindo até zerar. |

Depois vêm os grupos dos robôs, iguais aos do WinSeletor, com estas diferenças:

- Não existem mais os inputs de magic (os magics são fixos, da tabela acima), os de lote (lote fixo = 1 contrato), `GB_ServerGMTOffsetH`, `GB_RegimeAutomatico`, `GB_FimContinuoMin` (o fim do contínuo vem da grade B3 embutida) e `RE_LimiteEquity` (o `TesterStop` pararia os cinco robôs).
- `DM_RiscoMaxPct` vale sobre R$1.000 fixos, não sobre o saldo da conta.
- Os horários de zeragem dos robôs ficam limitados ao **corte** (fim do contínuo − 5 min): 18:20 nos dias até 18:25, 17:50 nos dias de 17:55. O CM zera às 18:20 (e não 18:24).

Mudar qualquer input reinicia o EA e passa pela recuperação; nada é cancelado nem fechado por isso.

## Horários

| Robô | Zeragem (dias de 18:25) | Zeragem (dias de 17:55) |
|---|---|---|
| GB | 18:20 | 17:50 |
| CM | 18:20 | 17:50 |
| DM | 18:20 | 17:50 |
| RE | 17:00 | 17:00 |
| C1 | 17:50 | 17:50 |

O vencimento do contrato do gráfico não muda o corte: vale a grade da B3 do dia. Os robôs calculam a qualquer hora (leilão incluído), mas entradas só saem de `negociacao_inicio` (09:00) até a zeragem de cada robô. Depois do fim do contínuo nenhuma saída é enviada. Em feriado a corretora recusa as ordens com "mercado fechado": o maestro retenta a cada 5 s e registra um AVISO, sem alarme.

**Corte com a verificação cruzada aberta:** se no corte o histórico ainda não fecha com a posição, o maestro espera as ordens em voo terem desfecho, cancela as limites dos robôs, zera a posição real da conta no símbolo com uma ordem a mercado (log `CORTE_CONTA`) e só depois cancela os stops dos robôs. Sem conseguir ler a posição, não envia nada, mantém os stops e dá ALERTA a cada minuto.

**Ficha que atravessou a noite** (só acontece com o EA fora no corte): a S do dia venceu, então a ficha passa a noite e o leilão sem stop. Na volta, o maestro cria uma S nova a partir da pré-abertura (08:55) e zera a ficha no primeiro momento do contínuo.

## Log

Pasta: `MQL5\Files\WinMaestro\<servidor>_<conta>_<símbolo>\` (no Testador, `MQL5\Files\WinMaestro_teste\`, apagada a cada teste).

- `logs\AAAA-MM-DD.log`: uma linha por evento, gravada na hora. Formato:
  `HH:MM:SS.mmm | NIVEL | ROBO | EVENTO | detalhe | [tick HH:MM:SS.mmm loc HH:MM:SS]`
- `logs\AAAA-MM-DD_trans.log`: uma linha bruta por transação do símbolo.
- `estado.txt` / `estado.bak`: a memória (níveis pedidos, instantes, ordens em trânsito, bloqueios). Não edite.

Níveis: `INFO`, `AVISO`, `ALERTA` (também dispara a janela de `Alert()`), `ERRO`. Uma condição que se repete é logada ao começar, a cada 5 min com contador e ao terminar.

Eventos mais úteis no dia a dia:

| Evento | Significa |
|---|---|
| `PRONTO` | Partida concluída; resumo de cada robô (ficha, deals do dia, R$, stop e alvo pedidos). |
| `SINAL`, `ORDEM` | Pedido do robô e cada envio à corretora (`envio ...` e `retorno ...` com ticket, retcode, preço pedido e executado, líquida antes → depois). |
| `ENTROU`, `SAIU` | Cada deal de robô, com papel (E entrada, S stop, A alvo, X saída, C correção). |
| `STOP`, `ALVO` | S criada, movida ou recriada; alvo criado ou movido. |
| `DESFECHO` | Como cada ordem foi resolvida e qual prova resolveu (deal, listada nas pendentes, histórico). |
| `ESTADO` | Ordem não enviada porque o estado não fecha (leitura, verificação cruzada, ordem sem desfecho, memória não gravada, deal de ordem não identificada). A S nunca é barrada por isso. |
| `SEGUNDA_ENTRADA`, `AUTONEG`, `DECISAO PERDIDA` | Entrada não enviada: o robô já tem operação; cruzaria com limite de outro robô; decisão anterior à partida. |
| `ZERAGEM`, `CORTE`, `NOITE` | Saídas por horário. |
| `CORTE_CONTA` | Corte com a verificação cruzada aberta: zeragem da posição real e cancelamento das pendentes. |
| `TROCADA`, `DUPLICADA`, `CORRECAO` | Ficha fora de ±1 e a correção enviada com o magic do robô. |
| `EXTERNA`, `ABSORVIDA`, `BLOQUEIO`, `DESBLOQUEIO` | Deal manual; zeragem manual absorvida nas fichas; bloqueio de entradas e liberação. |
| `RECUPERA` | Partida passo a passo e o que aconteceu com o EA fora, com a hora real do deal. |
| `RESUMO` | Depois do corte: R$ por robô e conferência de contagem (deals × linhas do log). |

## Painel e botão

O canto do gráfico mostra (só leitura): passo da partida, líquida, externa, verificação cruzada, hora do corte, bloqueio e, por robô, ficha, preço, S, alvo, entrada viva, R$ do dia e estados especiais (pausado, trocada, duplicada, noite, desligado).

Quando há **bloqueio de entradas** aparece o botão **Desbloquear** (canto superior direito). Ele exige dois cliques em até 3 s. Antes de clicar, olhe o extrato da corretora. Causas: zeragem manual da posição; histórico que não fecha com a posição em 10 pregões; ordem sem desfecho há 10 min; correção repetida em menos de 10 min. Durante o bloqueio, as entradas vivas são canceladas e nenhuma entrada nova sai; stops, cancelamentos, saídas, zeragens e correções continuam.

## Testes unitários

`WinMaestro_Teste.mq5` roda 87 casos com a corretora falsa. Entre eles: DONE sem deal, timeout com ticket 0, recusa, histórico atrasado, stop executando antes da entrada, zeragem manual, ficha trocada e duplicada, corte, ficha da noite, memória corrompida, grade, sequência de partida, perda de conexão e deal sem magic.

**Anexe o EA de teste num gráfico DIFERENTE do que roda o WinMaestro.** Um gráfico só aceita um EA: anexar o teste por cima tira o maestro do gráfico, e ele para de gerir as posições.

O EA de teste não tem caminho para a corretora real (a classe que manda ordens nem é compilada nele). Ele imprime `PASSOU`/`FALHOU` por caso e o placar no Diário e sai sozinho. Grava só em `MQL5\Files\WinMaestro_unit*`.
