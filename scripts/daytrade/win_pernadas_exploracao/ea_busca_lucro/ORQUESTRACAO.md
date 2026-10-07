# Busca por EA lucrativo de WIN — orquestração

Mandato do dono, 2026-10-04 (/model claude-sonnet-5): construir um robô (EA) para o WIN que
dê lucro REAL, não fabricado — batendo custo de corretagem, deslizamento e execução real —
com gerenciamento de risco que não quebre a banca, iterando quantas gerações forem
necessárias (centenas, se preciso), sem reportar a cada rodada: só quando achar uma
estratégia validada ou esgotar o orçamento de gerações.

Este arquivo é o diário vivo. Cada geração, por menor que seja, ganha uma entrada aqui
ANTES de o orquestrador seguir para a próxima — se o processo for interrompido, este
arquivo é a fonte da verdade, não as transcrições dos subagentes.

## Geração 0 — seed (preenchido pelo coordenador antes de começar)

Insumos herdados de `../REGRAS.md`, `../CADERNO.md` (65 regras, 7 rodadas, só dados de 2026):

- **ENTRAR:** nenhum fator de direção confirmado isoladamente nem combinado (R62, logística).
- **NÃO OPERAR:** contra a pernada de 750 em curso (R43); depois das 13h (R03/R28); caixa
  estreita ≤150 pts/20min ou vol30/300 baixa (R36/R62).
- **LIGAR sem direção (TAMANHO/ALVO):** antes das 11h (R01/R02, ajustar DST EUA R28); onda de
  volatilidade (R20); vela M1 ≥2× o mesmo minuto dos 20 pregões anteriores (R35).
- **STOP+:** minuto :00/:30 (R21); 1ª hora tem mais ruído (stop 100 varrido 49–59% no 1º min).
- **Observar, não operar ainda (n pequeno, IC cruza 0):** R61 (limite a 62% de avanço de 500,
  stop 1/3, alvo no topo, 1º recuo, <11h + vela ≥2×: +101/+46/+4 pts/op nas 3 janelas) e R65
  (M15 rompe só EMA9 com H1 alinhado: +56/+45, IC enorme).
- **Achado de método crítico:** stop curto simulado com caminho de 2 pontos por vela M1
  (mínima→máxima) é OTIMISTA — 6 de 8 geometrias positivas viraram negativas com ticks reais.
  Todo stop <100 pts precisa de checagem com ticks. Ver LICOES_DE_PRODUCAO.md item 6.47.
- **Execução fechada do projeto (AGENTS.md/CLAUDE.md):** entrada só EnterLimit com TTL; alvo só
  limite fatiado, sem prazo; só o stop é a mercado; `anchor_exits_at_fill=True`; nunca alvo de
  1 tick; fidelidade de fila via `backtest/intraday/fidelidade.py`.
- **Capital mínimo real WIN:** R$250 com reserva (margem crua R$100, buffer 2×, reserva 1,25×);
  2º contrato em diante exige a pilha cheia. `contracts_from_capital_operacional`.
- **Princípios do dono:** só a favor da tendência maior (contra-tendência só como ponto de
  entrada a favor); alvo sempre ≥3× o stop, idealmente 5–10×; perder de colherinha, ganhar de
  balde; teoria dos jogos — sinal fraco muda TAMANHO da mão, não só entra/não entra.

## Janelas de dados (regra do dono — nunca violar)

- **IS (desenvolvimento/tuning):** jan–jun/2026. Toda escolha de parâmetro, toda ideia nova,
  só aqui.
- **OOS-1 (gate, uma vez, sem retunar):** jul–ago/2026. Atenção: esta janela já foi OLHADA
  DESCRITIVAMENTE muitas vezes nas rodadas 1–7 (números agregados de R01–R65 já existem em
  REGRAS.md) — não é mais ingenuamente virgem para "o mercado se comportou como X em jul–ago",
  mas NUNCA foi usada para medir o P&L de uma estratégia completa igual à que está sendo
  testada agora. Trate como soft-contaminada: relate isso, não finja que é OOS perfeito.
- **OOS-2 (gate final, só para quem passar o OOS-1):** set/2026. Também já foi usada como
  "referência" descritiva em várias tabelas, mas nunca para P&L de estratégia composta.
- **RESERVADO, nunca abrir sem pedido explícito do dono:** 2025 e anos anteriores.
- **Fora do escopo por ora:** out/2026 em diante — poucos dias de dado, não usar ainda.

## Decisão do dono, 2026-10-05 — reabertura com 2 portas abertas JUNTAS

Depois de 16 gerações (ver abaixo) com prova mecanística de que `alvo≥3×stop` + capital
R$250/1 contrato é estruturalmente irreconciliável, o dono escolheu reabrir a busca relaxando
as DUAS restrições ao mesmo tempo, **só para esta busca, não para o resto do repositório**:

1. **Capital de teste: R$1.000** (substitui o R$250 mínimo real só aqui, autorização explícita
   do dono — é o mesmo valor que ele usou como exemplo de "lucro bom" = sair com R$2.000 no
   mês). Com R$1.000, a escada de contratos (`contracts_from_capital_operacional`, margem
   R$100 × buffer 2 × reserva 1,25 = R$250/contrato ao escalar) permite de 1 a ~4 contratos —
   usar isso para tornar o G11 (tamanho de mão graduado pela força do sinal) mecanicamente
   possível de verdade, não só binário.
2. **Alvo/stop: grade de {2×, 2,5×, 3×, 4×, 5×}** em vez de só "≥3×" fixo. O piso nunca cai
   para ≤1× (perda ≥ ganho continua proibido, é o princípio inegociável do dono) — a porta
   aberta é só até onde a razão mínima pode cair, não se ela pode sumir.

Tudo o resto do mandato original continua de pé: execução fechada (EnterLimit, alvo limite
sem prazo, só stop a mercado), janelas (IS jan–jun, OOS-1 jul–ago uma vez sem retunar, OOS-2
set), nunca abrir 2025, nunca editar `registry.py` nem ir a produção, motor real do repo para
qualquer candidata que chegue a OOS.

## Geração 1 — síntese consolidada (R61 + R65 + portões de horário/caixa/tendência)

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código em
`src/strategy/daytrade/lab/win_busca_lucro_g01_consolidado.py` (classe
`WinBuscaLucroG01`, não registrada) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g01_consolidado/`
(`g01_base.py`, `g01_is_exploracao.py`).

**Ideia testada:** portão LIGAR (hora < 11h/12h ajustado DST EUA R28, antes de
13h/14h R03, caixa não estreita ≥150pts/20min R36) + direção só a favor da
pernada de 750 em curso (R43) + dois gatilhos: R61 (limite a 62% de recuo de um
avanço ≥500pts, stop 1/3 da distância ao extremo, alvo no extremo — 3:1 por
construção) e R65 (M15 rompe só a EMA9 com H1 alinhado, stop técnico de 10
velas, alvo 5×). Execução fechada (EnterLimit ttl=10, saída fatiada sem prazo,
`anchor_exits_at_fill`, só stop a mercado), capital real R$250, fila WIN@
assumida zero (não calibrada — premissa otimista declarada, igual nas duas
pontas). R20/R35 (onda de volatilidade/vela ≥2×) **não foram implementados**
nesta geração (seriam estatística cross-sessão, ficou como próximo passo).

**Resultado IS (jan–jun/2026, 122 pregões, capital R$250):**

| variante | líquido R$ | win% | trades | BE empírico | pregões sem trade |
|---|---|---|---|---|---|
| R61 isolado | −159,00 | 21,4% (3/14) | 14 | 29,5% (IC [7,6;47,6]) | 116/122 |
| R65 isolado | 0,00 | — | **0** | — | 122/122 |
| combinado | −159,00 (= R61, R65 nunca contribuiu) | 21,4% | 14 | 29,5% | 116/122 |

**OOS-1: NÃO RODADO.** Protocolo do mandato — só promove ao OOS-1 quem fizer
sentido no IS (líquido>0 e não censurado). Nenhuma das 3 variantes passou.

**Veredito: MORTA.** Duas causas diferentes, nenhuma delas "quase lá":
1. **R61** é CENSURADA por exaustão de capital (14 trades todos entre
   15–28/jan, caixa cai a R$91 — abaixo da margem crua R$100 — e **74
   tentativas de entrada seguintes foram recusadas em silêncio** pelo resto do
   IS: exatamente o padrão "piso de capital como condição de continuidade" que
   o CLAUDE.md proíbe tratar como veredito). Mesmo nos 14 trades que rodaram,
   o sinal já era fraco (win 21,4% < BE empírico 29,5%, payoff realizado
   ~2,4:1 contra 3:1 teórico — deslize/custo comendo a diferença). Consistente
   com o próprio REGRAS.md: R61 já tinha IC cruzando zero com n pequeno.
   Stop mediano 170pts (nunca <100) — **não precisa de checagem com ticks**
   (item 6.47 não se aplica).
2. **R65** teve ZERO sinais no IS inteiro — não é falta de gatilho (383
   rompimentos de EMA9-M15 em 122 dias), é que "H1 alinhado" dentro da janela
   `<11h/12h` nunca coincidiu: das poucas ocorrências que passam todos os
   filtros, a maioria amadurece **à tarde** (12:59–17:59), depois que o
   portão de horário (herdado de R01/R02, que é sobre NASCIMENTO de pernada,
   não sobre R65) já fechou. **Incompatibilidade estrutural de desenho, não
   falta de sinal** — a medição original de R65 em REGRAS.md nunca teve esse
   gate de horário.

**Sizing/ruína:** não rodado (protocolo — amostra já inválida por censura, não
vale medir ruína em cima do próprio buraco).

**Raciocínio para a Geração 2:** o erro de design da G1 foi herdar o portão de
horário do R61/R43 e aplicá-lo também ao R65, que nunca foi medido sob essa
restrição. R65 precisa ser testado como HIPÓTESE PRÓPRIA, com janela de
horário adequada a ele (não necessariamente `<11h`), do zero no IS. R61 nesta
forma é considerada encerrada (console com o IC que já cruzava zero em
REGRAS.md) — não repetir isolado.

## Geração 2 — R65 como hipótese própria (janela de horário como parâmetro)

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g02_r65_tarde.py` (classe
`WinBuscaLucroG02R65`, não registrada) + versão **congelada** usada no
OOS-1 em `..._congelado_v02.py` + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g02_r65/`
(`g02_base.py`, `g02_is_busca.py`, `g02_oos1.py`).

**Ideia testada:** só R65 (M15 rompe só a EMA9 com H1 alinhado), sempre a
favor da pernada de 750 em curso (R43, princípio inegociável — nunca
testado como parâmetro). A janela de horário em que o robô pode EMITIR a
ordem (não em que o estado do gatilho é calculado — isso roda sempre) virou
PARÂMETRO a descobrir no IS, com 4 valores: sem filtro (09:00-18:29), só
manhã (09:00-11:00), só tarde (12:59-18:29), dia todo exceto os últimos 30
min (09:00-18:00). Geometria: stop técnico (N∈{5,10,15} velas M1) × stop
ATR-M15 (k∈{1,0;1,5}, período 14) × alvo (3x/5x/7x o risco), busca em 3
estágios (A horário → B família de stop → C múltiplo do alvo, cada um
fixando o vencedor do anterior). Execução fechada idêntica à G1 (EnterLimit
ttl=10, saída fatiada sem prazo, `anchor_exits_at_fill`, só stop a mercado),
capital real R$250, fila WIN@ zero (não calibrada, premissa otimista
declarada).

**Bug de método encontrado e corrigido ANTES de qualquer medição valer
(2026-10-05):** a G1 chamava a atualização do estado do M15/H1 (que pode
armar uma ordem, setando `_espera=0` internamente) **antes** de checar se o
robô já tinha ordem pendente — e o próprio `on_bar` enxergava esse
`_espera` recém-setado na MESMA barra e descartava a ação que tinha acabado
de criar. Ou seja: **R65 estruturalmente NUNCA emitia ordem nenhuma em
nenhuma das duas gerações**, até este bug ser achado ao testar a G2 — não
era só o portão de horário errado que a G1 diagnosticou. Corrigido na G2
separando "atualizar estado" (sempre roda) de "emitir ordem" (só quando
`pode_armar`, decidido com o `_espera` do INÍCIO da barra, nunca o que a
própria atualização acabou de setar). `WinRetangulo` (produção) nunca teve
este bug — lá a ordem de checagem já era a correta. **Este achado também
revisa o diagnóstico da G1**: "R65 teve ZERO sinais" tinha DUAS causas, não
uma, e a G1 só viu a do horário.

**Resultado IS (jan-jun/2026, 122 pregões, capital R$250) — tabela
completa (12 variantes, 3 estágios):**

| variante | líquido R$ | trades | win% | BEnom% | BEemp% | sem_trade |
|---|---|---|---|---|---|---|
| A1 sem_filtro (09-18:29) | +637,00 | 4 | 50,0% | 16,7% | 8,3% | 118/122 |
| A2 só manhã (09-11:00) | 0,00 | **0** | — | 16,7% | — | 122/122 |
| A3 só tarde (12:59-18:29) | +637,00 | 4 | 50,0% | 16,7% | 8,3% | 118/122 |
| A4 dia todo s/ últ. 30min | +637,00 | 4 | 50,0% | 16,7% | 8,3% | 118/122 |
| B1 técnico N=5 | +573,50 | 5 | 20,0% | 16,7% | 2,2% | 118/122 |
| B2 técnico N=10 | +637,00 | 4 | 50,0% | 16,7% | 8,3% | 118/122 |
| B3 técnico N=15 | +637,00 | 4 | 50,0% | 16,7% | 8,3% | 118/122 |
| B4 ATR k=1,0 (M15,14) | +510,00 | 4 | 50,0% | 16,7% | 11,9% | 118/122 |
| B5 ATR k=1,5 (M15,14) | +497,00 | 4 | 50,0% | 16,7% | 12,2% | 118/122 |
| C1 alvo=3x | +458,00 | 4 | 50,0% | 25,0% | 10,8% | 118/122 |
| C2 alvo=5x (vencedor) | +637,00 | 4 | 50,0% | 16,7% | 8,3% | 118/122 |
| C3 alvo=7x | +514,00 | 4 | 50,0% | 12,5% | 9,8% | 118/122 |

A1/A3/A4 saem **bit a bit idênticas**: os 4 únicos sinais do IS nasceram
todos à TARDE — confirma, agora numa base de código correta, o achado
descritivo da G1 ("H1 alinhado" amadurece de tarde). A2 (só manhã) teve
ZERO sinais: a janela da manhã realmente não produz nada, mas não porque o
robô "trava" — é que a conjunção dos 3 filtros é rara o bastante para não
calhar de manhã nas amostras existentes.

**Vencedor do IS:** janela sem filtro (= só tarde na prática), stop técnico
N=10 (empatado com N=15), alvo 5x. Líquido R$637,00, 4 trades, equity mínima
R$172,50 (> margem crua R$100 — **não é censura de capital**, `ordens_
recusadas_por_capital=0`), stop mediano 280 pontos (acima do piso de 100
pts do item 6.47 — **não precisou checagem com ticks**).

**A ressalva que domina esta geração: n=4.** 1 dos 4 trades (+R$679,50, long
de 24/03) sozinho excede o líquido total da janela — sem ele, os outros 3
somam **-R$42,50** (negativo). O veredito mecânico "POSITIVO" (IC95 do win%
[15,0%;85,0%] com limite inferior acima do BE empírico de 8,3%) é um
artefato de um breakeven empírico rebaixado pelo próprio outlier (ganho
médio R$350 puxado por 1 trade) cruzado com um IC de Wilson enorme — não é
evidência de edge. `R$/op>0` (R$159,25) e `win%>BE empírico` concordam, mas
concordam quase por construção com n=4.

**OOS-1 (jul-ago/2026, 44 pregões, código/parâmetros CONGELADOS em
`win_busca_lucro_g02_r65_tarde_congelado_v02.py`, rodado UMA VEZ):**
**ZERO trades, líquido R$0,00.** `ordens_recusadas_por_capital=0`, equity
nunca saiu de R$250 — não é censura de capital, é o gatilho (M15 só EMA9 +
H1 alinhado + a favor da pernada) simplesmente não tendo ocorrido nenhuma
vez em 44 pregões. Com a taxa de disparo medida no IS (4/122 pregões), o
número esperado de sinais em 44 pregões seria ~1,4 — 0 observado está
dentro do ruído de Poisson (p≈25%), então isto NÃO é uma rejeição estatística
forte por si só, mas o resultado literal do gate é inequívoco: **líquido=0,
não >0 → NÃO PASSA.**

**Veredito: MORTA.** R65, mesmo testado corretamente (sem o portão de
horário herdado, e depois de corrigir o bug de emissão de ordem que a
impedia de disparar em QUALQUER geração anterior), produz sinal rarefeito
demais para validar: 4 operações no IS (dominadas por 1 outlier) e 0 no
OOS-1. Isto bate com o que `REGRAS.md` já registrava sobre R65 ("em aberto —
precisa de ≥150 operações novas") — a G2 não chegou nem perto disso, e o
motivo agora está claro: o gatilho é raro por construção (M15 romper só a
EMA9 com H1 alinhado E a favor da pernada de 750 é uma conjunção estreita),
não por um portão de horário mal desenhado.

**Sizing/ruína:** não rodado — protocolo explícito ("se IS e OOS-1 derem
positivo e não censurado"): OOS-1 deu líquido=0, não positivo. **Pendente,
não aplicável a este resultado.**

**% mensal equivalente:** não aplicável — OOS-1 não passou o gate.

**Raciocínio para a Geração 3:** o achado mais importante desta geração não
é sobre R65 em si, é de MÉTODO: um bug de ordenação (atualizar estado antes
de checar se pode agir) pode fazer um robô inteiro nunca emitir ordem
nenhuma, SILENCIOSAMENTE — o backtest roda limpo, sem erro, só devolve
sempre zero trades, e é fácil atribuir isso à hipótese ("o sinal é raro")
quando na verdade é um defeito de implementação. Vale auditar qualquer
estratégia futura (desta linha de pesquisa ou não) que combine "estado
calculado toda barra" + "ordem pendente com prazo" pela mesma armadilha —
a ordem de operações em `on_bar` importa tanto quanto a lógica de sinal.
Sobre R65 especificamente: está encerrada como gatilho único — qualquer
geração futura que queira usá-la precisa somar outro fator que aumente a
FREQUÊNCIA (não só a qualidade) do sinal, porque o teto de n já apareceu
duas vezes (R61 na G1, R65 na G2) como o fator que mais mata uma hipótese
promissora no papel. A busca pela G3 deveria privilegiar gatilhos menos
raros antes de refinar geometria — geometria fina sobre um gatilho de 4
eventos em 6 meses não é mensurável em nenhum horizonte prático.

## Geração 3 — R57 (recuo raso) + filtros R59/R58, busca de maior frequência

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g03_recuo_raso.py` (classe
`WinBuscaLucroG03RecuoRaso`, não registrada) + versão **congelada** usada no
OOS-1 em `..._congelado_v03.py` + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g03_recuo_raso/`
(`g03_base.py`, `g03_is_busca.py`, `g03_oos1.py`,
`g03_verificacao_ticks.py`).

**Ideia testada:** R57 (`REGRAS.md`, rodada 6) — depois de um avanço A
(zigzag causal de T∈{500,750} pontos sobre o caminho da vela, mesma
definição de R43), o 1º recuo que fecha com fundo em [23%,38%] de A arma
`EnterLimit` a `m` pontos acima do fundo, stop no fundo (menos 1 tick de
folga, para nunca dar risco zero com `m=0`), alvo = `alvo_multiplo`× o
risco. "Fecha" é definido operacionalmente nesta geração como um
sub-zigzag interno de 50 pontos (não é parâmetro — limiar de ruído; ver
docstring da classe para a declaração completa de que isto NÃO é réplica
byte-a-byte do script original da rodada 6, que não está disponível). R59
(fundo do 1º recuo desta perna ≥/≤ o fundo do 1º recuo da perna ANTERIOR da
mesma direção) e R58 (janela de horário como PARÂMETRO, não portão fixo)
testados como filtros opcionais. Direção sempre a favor da perna maior
(R43, inegociável). Execução fechada idêntica à linha (EnterLimit ttl=10,
saída fatiada sem prazo, `anchor_exits_at_fill`, só stop a mercado), capital
real R$250, fila WIN@ zero (não calibrada, premissa otimista declarada), 1
contrato fixo.

**Contadores de auditoria (lição da G2):** `stats_bruto_r57` conta toda
ocorrência do gatilho ANTES de qualquer filtro/capital/`pode_armar`;
`stats_ordens_emitidas` conta só as que viraram `EnterLimit`. Em toda a
busca `bruto=334` (T=750) foi IDÊNTICO entre variantes de filtro — exatamente
o esperado (filtro não pode mudar a contagem bruta) e evidência de que o
contador não colapsou silenciosamente a zero como na G1/G2. A razão
emitidas/bruto variou de 33/334 a 254/334 conforme o filtro, sem nenhum
colapso inexplicado.

**Resultado IS (jan-jun/2026, 122 pregões, capital R$250) — 5 estágios, 15
variantes (tabela completa no log
`g03_recuo_raso/g03_is_busca_stdout.log`):**

| estágio | vencedor | líquido R$ | trades | win% | sem_trade | censurado |
|---|---|---|---|---|---|---|
| A — filtro (T750,m10,alvo5) | A3 R57+horário(11-13) | −152,00 | 14 | 21,4% | 111/122 | sim (todas as 4 eram) |
| B — T da perna | B2 T=750 | −152,00 | 14 | 21,4% | 111/122 | sim |
| C — m | C3 m=20 | −57,50 | 49 | 30,6% | 82/122 | sim |
| D — alvo | D3 alvo=7x | +53,50 | 49 | 30,6% | 82/122 | sim (sem_trade) |
| E — janela (isolado) | **E3 09:00-11:00** | **+357,00** | **92** | **34,8%** | 57/122 | **não** |

R59 **nunca venceu** nenhum estágio (A2/A4, com R59 ligado, sempre piores
que os pares sem R59 — emitidas caem de 254→92 ou 69→33, mas o líquido não
melhora). O vencedor final não usa R59. `m=0` foi a pior célula do estágio C
(−R$196,50, win 9,1%) — descartado.

**Vencedor do IS:** T=750, m=20, alvo=7x, R59 desligado, janela 09:00-11:00.
Líquido R$357,00, 92 trades, win 34,8% (BE nominal 12,5%, BE empírico 26,9%,
IC95 [25,8%;44,9%] — cruza o BE empírico por 1,1pp, "indefinido" no veredito
mecânico), 57/122 pregões sem trade, equity mínima R$170,00 (nunca abaixo da
margem crua R$100 — não é censura de capital, `ordens_recusadas_por_capital
=0`). Stop mediano **35 pontos** — abaixo do piso de 100pts do item 6.47,
**bandeira levantada conforme o protocolo**.

**OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em
`win_busca_lucro_g03_recuo_raso_congelado_v03.py`, rodado UMA VEZ):**
líquido **+R$38,50**, 21 trades, win 23,8% (BE nominal 12,5%, BE empírico
20,1%, IC95 [10,6%;45,1%] — cruza o BE empírico, indefinido), 27/44 pregões
sem trade, equity mínima R$208,50 (nunca perto da margem — de novo não é
censura de capital). `R$/op>0` (R$1,83) e `win%>BE empírico` concordam nas
duas janelas, mas por margem pequena e com n minúsculo (21 operações) — a
mesma ressalva de método que já apareceu na G2 com n=4.

**Verificação com ticks reais — achado DECISIVO (`g03_verificacao_ticks.py`,
`g03_recuo_raso/g03_verificacao_ticks_stdout.log`):** stop mediano de
30-35 pontos obrigou a checagem do item 6.47 antes de aceitar qualquer
número positivo. Reconstruído stop/alvo a partir do preço de ENTRADA real de
cada uma das 21 operações do OOS-1 (`anchor_exits_at_fill` preserva a
distância declarada) e comparado contra a sequência REAL de negócios
(`data/cache_win_ticks/WIN@D`, cobertura completa de jul-ago): em **14 das
21 operações (66,7%)** o nível que os ticks reais mostram ter sido tocado
PRIMEIRO diverge do motivo de saída que o motor M1 registrou (stop↔alvo
trocados). Isto não é um detalhe de borda — é a MAIORIA das operações. Com
um stop de 25-30 pontos (bem abaixo do range típico de uma barra M1 do
WIN em muitos minutos) e um alvo 7× mais distante, a resolução de "o que
tocou primeiro" dentro de uma única barra de 1 minuto (ou entre o instante
real do preenchimento da entrada, que o M1 não localiza dentro do minuto, e
os negócios seguintes) é **estruturalmente não confiável** nesta escala. Não
é possível afirmar em que direção o número "verdadeiro" se moveria sem
reimplementar o motor inteiro em resolução de tick (fora do orçamento desta
geração) — e essa incerteza, por si só, já invalida o +R$38,50 do OOS-1 como
evidência. Isto bate EXATAMENTE com o que `REGRAS.md` já tinha registrado
para esta mesma família de regras (R51-R60, que inclui R57): *"o caminho de
2 pontos por vela M1 ... piora os resultados. Com ticks (mar-jun, n=763) o
acerto fica igual à ruína do jogador e a esperança em ~0 pts/op (IC −11 a
+11), sem vantagem."* A G3 encontrou, de forma independente, o mesmo
problema que a pesquisa original já tinha diagnosticado para R57.

**Veredito: NÃO VALIDADA.** Três motivos independentes, nenhum isolado seria
suficiente para matar sozinho, mas juntos não deixam dúvida:
1. O resultado só aparece depois de 5 estágios de busca gulosa no IS
   (geometria extrema: alvo=7×, a célula C1/C2/B1/A1-A4 originais eram todas
   negativas) — é exatamente o padrão "ótimo que mora onde o simulador é
   mais otimista que a realidade" que o próprio `CLAUDE.md` adverte (seção
   do deslize do TP nativo).
2. Estatisticamente indefinido nas DUAS janelas (IC95 do win% cruza o
   breakeven empírico tanto no IS quanto no OOS-1), com n pequeno no OOS-1
   (21 operações).
3. **A verificação com ticks reais mostra que a maioria (66,7%) das
   operações do OOS-1 tem seu motivo de saída DIFERENTE do que a sequência
   real de negócios indica** — o número de líquido positivo não sobrevive à
   checagem obrigatória do item 6.47.

R59 e R58 (horário), a hipótese central desta geração — que FILTRAR R57 por
R59/R58 empurraria a fatia selecionada para acima do breakeven — **não se
sustentou**: R59 nunca melhorou nenhum estágio, e o "melhor" filtro de
horário (09:00-11:00) só supera "sem filtro" (00:00-23:59, R$294,50, 183
trades, também não censurado) por R$62,50 — diferença pequena demais para
ler como estrutura, não ruído.

**Sizing/ruína/% mensal:** não aplicável — protocolo exige "se IS E OOS-1
passarem"; o OOS-1 passa literalmente no `líquido>0` mas não "com folga" (IC
cruza o BE, e a verificação de ticks invalida o número). Pendente.

**Raciocínio para a Geração 4:** esta geração confirma, por um caminho
diferente das duas anteriores, a mesma lição de método que vem se repetindo:
um gatilho de maior frequência (334 ocorrências brutas em 122 dias, contra
14 e 4 das gerações 1-2) NÃO basta se a geometria que sobra depois da busca
tem stop pequeno demais para o M1 resolver com confiança. O próximo passo
não é buscar mais frequência nem mais filtro — é **buscar geometria com stop
estruturalmente maior que ~100 pontos POR CONSTRUÇÃO** (não como ajuste fino
depois de achar o vencedor), para que a pergunta "o motor está medindo a
estratégia ou a ambiguidade de 1 barra" nem precise ser feita. Vale também
desconfiar de qualquer busca em estágios gulosos (A→B→C→D→E) que só produz
líquido positivo no ÚLTIMO estágio depois de escolher o parâmetro mais
extremo disponível (`alvo=7x`, o maior testado) — é o padrão clássico de
superfície sem platô, o oposto do que `WinRetangulo` (produção) exibe.

## Geração 4 — confirmação cruzada WIN×WDO, estado anômalo (WDO só como filtro)

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g04_cross_wdo.py` (classe
`WinBuscaLucroG04CrossWdo`, não registrada) + versão **congelada** usada no
OOS-1 em `..._congelado_v04.py` + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g04_cross_wdo/`
(`g04_base.py`, `g04_diagnostico.py`, `g04_is_busca.py`, `g04_oos1.py`,
`g04_placebo_so_win.py`).

**Ideia testada:** um achado de um estudo ANTERIOR, fora desta linha
(2026-09-15, "confirmação cruzada WIN×WDO, estado anômalo") registrava que
WIN@ e WDO@ normalmente andam em correlação NEGATIVA forte nos incrementos
de minuto, mas existe um estado raro em que os dois andam na MESMA direção
por uma janela curta — anômalo, dado que deveriam andar opostos — depois do
qual a correlação negativa tenderia a se restaurar. **O número antigo NÃO
foi reaproveitado** (podia invadir dado de 2025): a correlação e o estado
anômalo foram **remedidos do zero**, só com jan-jun/2026 (IS) e jul-ago/2026
(OOS-1). Operação só no **WIN@** (1 contrato fixo); o WDO@ entra só como
**filtro/gatilho** (`estado_anomalo_cruzado`, função pura de duas séries de
fechamento M1, causal: quantil de corte calculado só com dias INTEIROS
anteriores ao dia corrente, burn-in de 20 dias). Direção sempre a favor da
pernada maior do WIN (R43, 750 pontos, princípio inegociável, sem parâmetro
que desligue). Execução fechada (EnterLimit ttl=10, limite `buffer_entrada`
pontos atrás do fechamento, saída fatiada sem prazo, `anchor_exits_at_fill`,
só stop a mercado, alvo sempre ≥3× o stop), capital real R$250, fila WIN@
zero (não calibrada, premissa otimista declarada), 1 contrato fixo.

**Exceção declarada à regra 2 do AGENTS.md:** a hipótese é estruturalmente de
dois instrumentos e o motor só entrega ao `on_bar` a barra do símbolo
operado. `estado_anomalo_cruzado` é uma função pura module-level (duas
séries de fechamento → duas séries de decisão, sem I/O, sem banco, causal) e
o harness a chama UMA VEZ fora do loop do motor, passando o resultado
pré-computado ao construtor da estratégia — `on_bar` só faz `dict.get(ts)`,
nenhum cálculo cruzado roda dentro do loop. Ao portar para MQL5 o
equivalente é ler `iClose("WDO$",...)` do símbolo irmão e recalcular o mesmo
quantil causal — o método é portável, só o jeito de entregar o dado muda.

**Correlação remedida no IS (jan-jun/2026):** incrementos de 1 minuto,
`r = −0,5189`, `n = 68.419` — confirma a premissa do estudo antigo (que
media r≈−0,50 numa janela possivelmente diferente) **de forma independente**,
com dado só desta busca.

**Frequência bruta do estado anômalo** (diagnóstico antes de qualquer
backtest, `g04_diagnostico.py`): a `janela=15min`/`quantil=0,60` dá 2,36% das
barras do IS marcadas — perto do "~2,5% dos minutos" do estudo antigo, mas
remedido, não herdado. `quantil=0,90` cai para 0,06-0,09% das barras (raro
demais para qualquer janela).

**Busca no IS — 4 estágios, 28 variantes (tabela completa em
`g04_is_busca_stdout.log`):**

| estágio | vencedor | líquido R$ | trades | win% | sem_trade | censurado |
|---|---|---|---|---|---|---|
| A — janela×quantil×direção (18 células) | A j20 q75 **continuação** | +976,00 | 126 | 23,0% | 60/122 | não |
| B — stop_pontos | B stop=150 | +976,00 | 126 | 23,0% | 60/122 | não |
| C — alvo_multiplo | C alvo=3x | +1.074,50 | 131 | 34,4% | 60/122 | não |
| D — buffer_entrada_pontos | **D buffer=30** | **+1.221,50** | **127** | **35,4%** | 60/122 | **não** |

Das 18 células do estágio A, **16 foram negativas ou zero** — só
`j20 q75 continuação` (+976,00) e um resíduo marginal (`j20 q90 reversão`,
−31,50, n=1) escaparam do platô negativo em −126 a −181 por operação baixa.
`direção=reversão` (a hipótese LITERAL do estudo antigo — "a correlação
negativa se restaura") **perdeu em toda janela/quantil testada**: o melhor
resultado de reversão no estágio A foi **0,00** (zero trades, `j15 q90`) e o
pior foi −181,50. A direção que de fato funciona no IS é **continuação**
("o movimento conjunto carrega informação nova, WIN segue"), o oposto do
que o achado antigo descrevia — reforça que remedir do zero (em vez de
herdar a direção também) era obrigatório.

**Vencedor do IS:** `continuação`, `janela=20min`, `quantil=0,75`,
`stop_pontos=150`, `alvo_multiplo=3x`, `buffer_entrada=30pts`. Líquido
R$1.221,50, 127 trades, win 35,4% (BE nominal 25,0%, BE empírico 27,5%,
IC95 [27,7%;44,1%] — **POSITIVO por 0,2pp**, a mesma margem apertada que
`WinRetangulo` teve no OOS real), 60/122 pregões sem trade, equity mínima
R$243,00 (**não é censura de capital**, `ordens_recusadas_por_capital=0`),
stop mediano **155 pontos** (acima do piso de 100pts do item 6.47 —
**não exigiu checagem com ticks** pelo protocolo).

**Fragilidade — PLACEBO crítico rodado antes de aceitar o vencedor
(`g04_placebo_so_win.py`):** dos 214 disparos brutos do vencedor, só 47
(22%) eram contra a tendência maior — a maioria dos disparos já coincidia
com a tendência do WIN, levantando a suspeita de que o "estado anômalo" não
estivesse adicionando nada além do próprio IMPULSO do WIN. Rodada a MESMA
geometria com um gatilho que ignora o WDO inteiramente (impulso de 20min do
WIN acima do mesmo quantil causal, sem checar o instrumento irmão): líquido
**−R$174,00**, win 25,0% (abaixo do BE empírico 26,2%), 2.590 disparos
brutos (12× mais que o cruzado) espalhados em só 7 pregões (115/122 sem
trade) — **o placebo falha onde o cruzado passa**. Isto é evidência a FAVOR
de que a confirmação do WDO carrega informação real (não é só impulso do
WIN disfarçado), mas não resgata a fragilidade abaixo.

**Concentração (item 7 do mandato):** top-3 pregões ÷ líquido total = **59%**
no IS — menos extremo que a G2 (1 trade = mais que 100% do total), mas ainda
uma bandeira: mais da metade do resultado de 127 operações em 62 pregões com
trade vem de só 3 deles.

**OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em
`win_busca_lucro_g04_cross_wdo_congelado_v04.py`, rodado UMA VEZ, quantil
causal usando o histórico acumulado IS+OOS-1 — não reinicia o burn-in em
julho, mesmo princípio de um robô ao vivo que não "esquece" a história):**
líquido **+R$184,50**, 49 trades, win 30,6% (BE nominal 25,0%, BE empírico
27,6%, IC95 [19,5%;44,5%] — **cruza o BE empírico, indefinido**), 17/44
pregões sem trade, equity mínima R$120,50 (**não é censura de capital**,
`ordens_recusadas_por_capital=0`). **Concentração top-3/líquido = 240%** —
os 3 melhores pregões somam mais que 2,4× o líquido total, ou seja, o
restante da amostra é NEGATIVO o bastante para devorar mais da metade do
que os 3 melhores pregões geraram. Stop mediano 155 pontos (≥100 — item
6.47 não exigiu checagem com ticks; dado que a fragilidade já aparece por
dois caminhos independentes — IC cruzando o BE e concentração extrema — a
checagem de ticks não foi rodada, pois não mudaria o veredito).

**Veredito: NÃO VALIDADA.** Passa o gate LITERAL do protocolo
(líquido>0 E não censurado nas duas janelas), mas não "com folga": três
sinais independentes de fragilidade, nenhum isolado seria conclusivo mas
juntos repetem o padrão da G3 (resultado que só existe perto da margem
estatística):
1. IC95 do win% cruza o breakeven empírico nas DUAS janelas (IS por 0,2pp,
   OOS-1 por margem maior mas com n pequeno, 49 operações).
2. Concentração extrema no OOS-1 (240% — pior que o IS, não melhor, o
   oposto do que "confirmação independente" deveria mostrar).
3. A busca em 4 estágios gulosos (A→B→C→D) só fecha positivo depois de
   reduzir o alvo ao mínimo permitido pela disciplina do dono (`alvo=3x`,
   estágio C) e abrir o buffer de entrada ao máximo testado (`buffer=30`,
   estágio D) — mesmo padrão de "ótimo na borda do espaço testado, não
   platô" que matou a G3.

**Achado de método que sobrevive, independente do veredito da estratégia:**
a direção que o estudo antigo propunha (reversão — "a correlação negativa se
restaura") **não replicou**; a que funciona no IS é continuação, o oposto.
Isto confirma, por um caminho concreto, a instrução do mandato de "remedir
do zero, não herdar nem a direção" — herdar a direção do achado antigo teria
produzido uma busca inteira em cima da hipótese errada sem nenhum sinal de
alarme (o resultado só "parece razoável" depois de testar as duas).

**Sizing/ruína/% mensal:** protocolo exige "se IS e OOS-1 passarem e não
forem dominados por poucos eventos" — a concentração de 240% no OOS-1
desqualifica essa condição; **não rodado**. Descritivo, sem validar nada:
R$184,50 em 2 meses sobre capital de R$250 equivaleria a ~37%/mês — número
que não deve ser lido como projeção, dado tudo acima.

**Raciocínio para a Geração 5:** esta geração encontrou, pela primeira vez
nesta linha, um gatilho que (a) replica fora da amostra em sinal (líquido
positivo nas duas janelas) e (b) sobrevive a um placebo crítico específico
(WDO sozinho bate o WIN-sozinho) — mais forte metodologicamente que G1-G3.
Ainda assim morre pelo mesmo motivo estrutural das três gerações anteriores:
o veredito estatístico fica preso perto da fronteira do breakeven empírico
e a concentração por poucos pregões PIORA da amostra de desenvolvimento para
a de validação, não melhora — o oposto do padrão que uma descoberta real
deveria exibir. Próximo passo sugerido: (1) a direção vencedora
(`continuação`) sugere que o sinal pode ser menos sobre "anomalia de
correlação" e mais sobre um regime de alta volatilidade/stress comum aos
dois mercados — vale testar se um filtro de volatilidade agregada (sem WDO)
replica o mesmo efeito com amostra maior antes de gastar mais uma geração em
confirmação cruzada; (2) qualquer geração futura que reusar este gatilho
precisa alongar o IS/OOS ou agregar mais pregões antes de aceitar o win%
como definido — n=127 (IS) e n=49 (OOS-1) continuam pequenos demais para o
IC fechar longe do breakeven, o mesmo teto que já apareceu em toda geração
desta linha.

## Geração 5 — regime de volatilidade só-WIN (WDO é dispensável, ou só o sintoma?)

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g05_regime_vol.py` (classe
`WinBuscaLucroG05RegimeVol`, não registrada, 3 funções proxy module-level
puras: `regime_amplitude_bloco`, `regime_vela_extrema`, `regime_volume_
bloco`) + harness em `scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g05_regime_vol/` (`g05_base.py`, `g05_is_busca.py`,
log completo em `g05_is_busca_stdout.log`).

**Pergunta testada:** a G4 achou um gatilho (confirmação cruzada WIN×WDO)
que replica em sinal mas é frágil (IC95 do win% cruza o breakeven empírico
nas duas janelas; concentração top-3-pregões/líquido PIORA de 59% no IS para
240% no OOS-1). O raciocínio que a G4 deixou: talvez o que funcione não seja
a correlação cruzada em si, e sim os dois mercados sinalizarem "regime de
movimento forte" ao mesmo tempo — e um proxy medido SÓ no WIN capturaria o
mesmo regime com amostra MAIOR, por não depender de dois instrumentos
concordarem no mesmo minuto. Esta geração constrói 3 proxies WIN-only,
todos causais (quantil/média só com dias ESTRITAMENTE anteriores, burn-in de
20 dias/ocorrências):

- **(a) `regime_amplitude_bloco`** — amplitude (`high-low`) dos últimos
  `janela_min` minutos acima de um quantil causal **condicionado ao
  horário** (mesma família do R20, "bloco agitado para o horário": o limiar
  em cada minuto-do-dia usa só os valores históricos daquele MESMO
  minuto-do-dia).
- **(b) `regime_vela_extrema`** — porta direta do **R35** (já CONFIRMADO em
  `REGRAS.md`): vela M1 com faixa `>= multiplo ×` a média da faixa do mesmo
  minuto-do-dia nos 20 pregões anteriores (janela móvel, não expanding).
- **(c) `regime_volume_bloco`** — soma do `tick_volume` do bloco recente
  acima de um quantil causal global (mesma família de quantil da G4, mas só
  com o WIN).

A aposta tradável é **sempre continuação da pernada maior em curso** (R43,
750 pontos, princípio inegociável) — diferente da G4, aqui os proxies são de
MAGNITUDE, não de direção, então a classe nem aceita parâmetro
`direcao_aposta`: a direção vem inteira do zigzag causal da pernada. Mesma
execução fechada da linha inteira (EnterLimit ttl=10, alvo fatiado sem
prazo, `anchor_exits_at_fill`, só stop a mercado, `target_fills_as_maker`),
capital real R$250, fila WIN@ zero (não calibrada, premissa otimista
declarada), 1 contrato fixo.

**Critério de sucesso desta geração (item 4 do mandato) — mais estrito que
"líquido positivo":** trades **> 127** (amostra da G4) **E** concentração
top-3-pregões/líquido **≤ 40%** (G4 tinha 59%) **E** veredito do win% =
**POSITIVO** (IC95 não toca o BE empírico) **E** líquido > 0 — as QUATRO
condições juntas, não "ou".

**Busca no IS (jan-jun/2026, 122 pregões) — Estágio 1 (detector, geometria
G4 fixa: stop=150/alvo=3x/buffer=30) + Estágios B/C/D (retune greedy da
geometria no detector vencedor de cada proxy), 48 variantes + referência +
ensemble, tabela completa em `g05_is_busca_stdout.log`:**

| candidato | líquido R$ | trades | win% | BEemp% | IC95 win% | top3/líq | sem_trade | critério bate? |
|---|---|---|---|---|---|---|---|---|
| **A — amplitude_bloco** (j15/q90, s150/a3x/b30) | **+2.786,50** | **667** | 30,7% | 27,3% | [27,4;34,3] POSITIVO | **59%** | 27/122 | não (top3/líq) |
| B — vela_extrema (R35) | 0,00 | 0 | — | — | — | — | 122/122 | não (morta) |
| C — volume_bloco (j15, s150, a7x, b20) | +2.515,50 | 307 | 17,3% | 13,8% | [13,4;21,9] indefinido | 63% | 24/122 | não (top3/líq + IC) |
| **REF — G4 cruzado** (recalculada nesta geração, idêntica ao registro) | +1.221,50 | 127 | 35,4% | 27,5% | [27,7;44,1] POSITIVO | 59% | 60/122 | não (trades=127, não >127) |
| ENSEMBLE (≥2 de 4 concordam, geometria G4) | −155,50 | 35 | 22,9% | 26,5% | [12,1;39,0] indefinido | 100% | 119/122 | não (morta) |

A linha REF confirma a reimplementação: recalculando o vencedor congelado da
G4 dentro desta geração reproduz **exatamente** o número já registrado
(líquido 1.221,50, 127 trades, win 35,4%, top3/líq 59%) — a comparação lado
a lado é válida.

**Proxy (b) R35 morreu na busca.** Apesar de confirmado como "liga/tamanho"
em `REGRAS.md`, usado SOZINHO como gatilho de entrada (sem o filtro de
horário/outras condições que o cercavam na validação original) ele não
sobrevive a nenhuma combinação de geometria testada — a busca greedy termina
em `buffer=0` (0 trades), e todo detector bruto (multiplo 2,0/2,5/3,0) já
era negativo ou censurado no Estágio 1. **Proxy (c) volume** confirma, de
novo, o achado de 2026-10-01 (`win_volume_indicador_descartado`): o volume
não acrescenta nada que a amplitude não já capture — a melhor célula de
volume (C) tem win% só marginalmente acima do BE nominal (17,3% contra
12,5%) e o IC cruza o BE empírico.

**Proxy (a) amplitude_bloco é o resultado mais interessante desta geração —
e é um "quase lá" instrutivo, não um vencedor.** Bate DUAS das quatro
condições com folga (trades=667, mais de 5× a amostra da G4; win% POSITIVO
por margem apertada mas real, IC95 [27,4%;34,3%] com o piso 0,1pp acima do
BE empírico). Mas **a concentração top-3/líquido é EXATAMENTE 59% — idêntica
à da G4**, não menor. Investigando por quê (auditoria por pregão, não só
agregada): os 667 trades vêm de **95 dos 122 pregões** (mediana 6
trades/pregão, máximo 24), contra 62 pregões da G4 — ou seja, o proxy
realmente opera em MUITO mais dias. Mas os 3 melhores pregões
(2026-03-10: +638,00/12 trades; 2026-03-03: +534,00/24 trades; 2026-03-11:
+474,00/8 trades) ainda somam 59% do líquido total. **O mecanismo que gera a
amostra maior é o mesmo que preserva a concentração:** quando um pregão
entra em tendência forte (a mesma pernada de 750 pontos persiste por horas),
o proxy de amplitude dispara dezenas de vezes NAQUELE MESMO pregão —
multiplicando trades dentro dos dias já favoráveis, não espalhando risco
para dias novos e independentes. A amostra "maior" (667 contra 127) é, em
boa parte, a MESMA informação ressonando mais vezes dentro dos poucos dias
que já eram bons — não uma amostra 5× mais independente. Stop mediano 155
pontos (acima do piso de 100pts do item 6.47, não exigiu checagem com
ticks).

**Ensemble (≥2 de 4 proxies concordando) não resgatou nada.** Com a
geometria fixa da G4 (não retunada para o ensemble — simplificação
declarada, ver limitações abaixo), exigir 2+ proxies simultâneos na mesma
barra colapsou a amostra para 35 trades e líquido negativo — os proxies não
se sobrepõem o suficiente no tempo para que a interseção vire um sinal mais
limpo; pelo contrário, a interseção parece jogar fora precisamente os dias
em que um proxy isolado (como a amplitude) acertava.

**Veredito do portão IS: NENHUM candidato bate o critério de sucesso
completo.** Por protocolo (ORQUESTRACAO.md, item 4 do mandato: "só promova
ao OOS-1 quem bater o critério no IS"), **nenhum OOS-1 foi rodado** nesta
geração — rodar OOS-1 para um candidato que já falha no IS gastaria a janela
de validação sem necessidade, exatamente o erro que o mandato pede para
evitar. Sem sizing/ruína, sem % mensal (nenhum número desta geração deve ser
lido como projeção).

**Limitações declaradas (fazem parte do achado, não escondidas):** (1) o
ensemble usou a geometria da G4 sem retune próprio — um ensemble com
geometria retunada poderia, em princípio, performar diferente, mas dado que
nenhum proxy individual retunado bateu o critério, a prioridade não
justificou o custo computacional extra; (2) os proxies (a) e (c) só foram
testados com o ponto de partida geométrico da G4 (stop 150/alvo 3x/buffer
30) no Estágio 1 — um detector com perfil de frequência tão diferente do da
G4 (centenas vs dezenas de disparos brutos) poderia, em tese, favorecer uma
geometria de partida diferente; o Estágio 1 escolhe o detector antes de
saber disso, mesmo viés que a G4 já tinha entre estágios gulosos sequenciais
(A→B→C→D).

**Resposta à pergunta da geração:** o efeito da G4 **não é dispensável do
WDO por um simples proxy de volatilidade do WIN sozinho** — pelo menos não
com os 3 proxies testados aqui. O proxy mais promissor (amplitude de bloco)
até reproduz a direção do efeito com amostra bem maior, mas herda
EXATAMENTE a mesma fragilidade de concentração que a G4 tinha — o que é, em
si, um achado: **a concentração parece ser uma propriedade estrutural de
"operar a continuação de uma pernada de 750 pontos quando ela já está em
curso"**, não um artefato de usar dois mercados com poucas observações. Se
isso for verdade, nenhuma geração futura vai resolver a concentração
trocando a FONTE do gatilho (WDO, amplitude, volume) sem mudar o que a
estratégia faz DEPOIS que o gatilho dispara — por exemplo, limitar quantas
vezes o robô reentra no MESMO pregão, ou normalizar o sizing pelo número de
entradas já feitas naquele dia.

**Raciocínio para a Geração 6:** (1) a hipótese de "regime de volatilidade
comum" como explicação alternativa para o efeito da G4 está ENFRAQUECIDA,
não confirmada — WDO parece carregar alguma informação que os 3 proxies
WIN-only não reproduzem com a mesma qualidade (o R35 nem sobrevive sozinho,
o volume confirma que não acrescenta nada); (2) o achado de método mais
acionável desta geração é que **concentração e frequência são eixos
diferentes** — aumentar a frequência (amplitude_bloco: 5× mais trades) não
necessariamente reduz a concentração, porque a frequência extra pode vir de
RE-amostrar os mesmos dias bons, não de diversificar para dias novos; antes
de aceitar qualquer "amostra maior" como evidência de robustez, confira
quantos PREGÕES DISTINTOS (não trades) carregam o resultado, não só o
contador de trades; (3) próximo passo sugerido: testar um limite de
reentradas por pregão (ex.: no máximo 1-2 trades/dia mesmo com o proxy
disparando dezenas de vezes) sobre a geometria vencedora desta geração (A,
amplitude_bloco j15/q90) para ver se a concentração cai quando a frequência
deixa de ser dominada por re-trigger dentro do mesmo dia — se a concentração
cair para perto de 35-40% mantendo a maior parte do líquido, a hipótese
estrutural do item acima fica confirmada e aponta um caminho concreto; se a
concentração não mudar, a causa é outra (provavelmente a distribuição de
caudas do próprio WIN, não o desenho do robô).

## Geração 6 — teto de reentradas por pregão (amplitude_bloco j15/q90 da G5)

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g06_amplitude_teto.py` (classe
`WinBuscaLucroG06AmplitudeTeto`, não registrada, reusa `regime_amplitude_
bloco` da G5 por import direto — não duplica a função pura) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g06_amplitude_teto/`
(`g06_base.py`, `g06_is_busca.py`, log completo em
`g06_is_busca_stdout.log`).

**Pergunta testada:** a G5 achou o proxy `regime_amplitude_bloco` (j15/q90,
geometria s150/a3x/b30) com líquido POSITIVO e amostra grande (667 trades,
win% POSITIVO com folga), mas concentração top-3-pregões/líquido = 59% —
igual à da G4, não menor — e a auditoria por pregão da G5 atribuiu isso ao
proxy REENTRAR dezenas de vezes no mesmo pregão favorável (máximo 24
operações/dia, 2026-03-03). Esta geração testa a correção direta: limitar
`max_trades_por_pregao` ∈ {1,2,3,4} (mais a referência sem teto = G5) sobre a
MESMA geometria/proxy, para ver se a concentração cai para perto de 35-40%
mantendo líquido>0 e win%/BE favorável.

**Mudança de desenho:** parâmetro novo `max_trades_por_pregao: int | None`.
Decisão de qual trade manter quando há mais de 1 candidato no pregão: os
**PRIMEIROS N sinais, na ordem em que o gatilho dispara** — nunca seleção
retroativa (isso seria look-ahead: a estratégia não pode saber, ao armar o
1º sinal, se um 2º ou 3º mais tarde no mesmo dia teria sido melhor). A
contagem (`self._trades_abertos_hoje`) só incrementa quando uma posição é
**ABERTA DE VERDADE** (fill real), nunca quando uma ordem é só emitida —
lida via transição vazio→não-vazio no argumento `positions` no **INÍCIO**
de `on_bar`, antes de qualquer atualização de estado desta chamada (mesma
disciplina do item 6.48/6.49: `positions` já reflete o fill desta barra
porque o motor processa ordens-limite pendentes antes de chamar
`strategy.on_bar`, e a estratégia nunca tem mais de 1 posição simultânea,
então a transição ocorre no máximo 1x por trade). Resto do desenho idêntico
à G5/G4 (execução fechada, capital real R$250, fila WIN@ zero/otimista
declarada, 1 contrato fixo). Geometria e proxy **fixos** nesta geração
(herdados do vencedor da G5: `janela_min=15, quantil=0,90, stop_pontos=150,
alvo_multiplo=3x, buffer_entrada=30`) — só `max_trades_por_pregao` varia.

**Resultado IS (jan-jun/2026, 122 pregões, capital R$250):**

| N | líquido R$ | trades | win% | BEemp% | IC95 win% | veredito | pregões c/trade | top3/líq | top5/líq | censurado |
|---|---|---|---|---|---|---|---|---|---|---|
| **1** | +453,50 | 95 | 30,5% | 26,6% | [22,2;40,4] | indefinido | 95/122 | **59%** | 99% | não |
| 2 | −177,50 | 17 | 17,6% | 26,3% | [6,2;41,0] | indefinido | 9/122 | −116% | −134% | **sim** |
| 3 | +440,00 | 248 | 28,6% | 27,2% | [23,4;34,5] | indefinido | 95/122 | 183% | 285% | não |
| 4 | +1.015,50 | 309 | 29,8% | 27,1% | [24,9;35,1] | indefinido | 95/122 | 82% | 129% | não |
| **sem teto (=G5)** | +2.786,50 | 667 | 30,7% | 27,3% | [27,4;34,3] | **POSITIVO** | 95/122 | 59% | 85% | não |

Stop mediano **155 pontos** em todos os N (geometria fixa, acima do piso de
100pts do item 6.47 — não exigiu checagem com ticks). `bruto`=835 (borda do
proxy) idêntico nas 5 linhas, conforme esperado — o teto nunca pode mudar a
contagem bruta, só o que vira ordem.

**Achado central, e é uma REFUTAÇÃO direta da hipótese que motivou esta
geração:** `N=1` — um único trade por pregão, **ZERO reentrada possível** —
preserva a concentração top-3/líquido em **59%, IDÊNTICA à "sem teto"**.
Isto não deixa dúvida: a concentração **não vem de reentrar no mesmo pregão
favorável**. Auditando por quê: com geometria fixa (stop=150/alvo=3x), toda
vitória sai perto do mesmo valor (~R$89,50, alvo de 450 pontos × R$0,20/ponto
menos custo) e toda derrota perto de outro valor fixo (~R$30, stop de 150
pontos) — o líquido total é a diferença residual entre uma soma GRANDE de
vitórias (29 dias × ~R$89,50 ≈ R$2.595) e uma soma GRANDE de derrotas (66
dias × ~R$32 ≈ R$2.142), e esse resíduo (R$453,50) é **pequeno frente ao
bruto dos dois lados**. Quando o líquido é um resíduo pequeno assim, QUALQUER
punhado de dias vencedores — mesmo pagando o valor ORDINÁRIO de vitória, sem
nada de outlier — representa uma fração grande desse resíduo por construção
aritmética, não por fragilidade de amostra. A métrica top3/líquido continua
válida como medida de fragilidade (o líquido realmente depende de poucos
dias para não zerar ou inverter), mas sua causa não é "re-trigger dentro do
dia": é a proporção entre o líquido residual e o bruto ganho+perdido, e
ISSO não muda cortando quantas vezes o robô entra por pregão.

**N=2/3/4 não resgatam nada — pioram, de forma não-monotônica.** N=2 é o
pior de todos (líquido negativo, **CENSURADO**: só 9/122 pregões com trade,
contra 95/122 nos demais — a maioria dos dias que tinham ≥1 sinal válido
tinha exatamente 1, não 2, então exigir 2 elimina quase todo dia da amostra).
N=3 e N=4 mantêm os mesmos 95/122 pregões com trade (porque o 1º sinal de
cada dia já conta), mas cortar a sequência de sinais NO MEIO do dia (não no
início, como N=1 faz) introduz sinais adicionais que nem sempre ganham — e
a concentração dispara para 183% (N=3) e 82% (N=4), pior que N=1 e pior que
"sem teto". Não existe gradiente "menos reentrada = menos concentração":
N=1 (59%) < N=4 (82%) < sem teto (59%, empate com N=1) < N=2 (censurado) <
N=3 (183%) — a relação é instável, não decrescente.

**Nenhum N bate o critério composto do mandato** (trades/amostra razoável +
top3/líq ≤40% + veredito win%=POSITIVO + líquido>0 + não censurado):

| N | amostra razoável | top3/líq≤40% | win% POSITIVO | líquido>0 | não censurado | promove? |
|---|---|---|---|---|---|---|
| 1 | sim | **não** (59%) | **não** (indefinido) | sim | sim | não |
| 2 | **não** (9 pregões) | sim | **não** | **não** | **não** | não |
| 3 | sim | **não** (183%) | **não** | sim | sim | não |
| 4 | sim | **não** (82%) | **não** | sim | sim | não |
| sem teto | sim | **não** (59%) | sim | sim | sim | não |

**Veredito: NENHUM candidato promovido. OOS-1 NÃO RODADO** (protocolo:
"só promove ao OOS-1 quem bater o critério no IS" — rodar OOS-1 para um
candidato que já falha no IS gastaria a janela de validação sem
necessidade). Sem sizing/ruína, sem % mensal (nenhum número desta geração
deve ser lido como projeção).

**Resposta à pergunta da geração:** a concentração **não cai** limitando
reentradas — nem no caso mais extremo (N=1, zero reentrada possível). A
causa é **mais profunda**, confirmando a segunda hipótese que a G5 deixou em
aberto: é a **distribuição de caudas/resíduo pequeno do próprio WIN** nesta
geometria, não o desenho do robô (quantas vezes ele reentra no mesmo dia).
A família "continuação de pernada de 750 pontos + gatilho de
amplitude/volatilidade" (G4 confirmação cruzada, G5 amplitude_bloco, G6
teto de reentradas) está, portanto, **ENCERRADA por ora** como esta pergunta
específica — três gerações consecutivas atacando o mesmo sintoma
(concentração) por três ângulos diferentes (fonte do gatilho em G5, limite
de reentrada em G6) sem resolvê-lo é evidência consistente, não só uma
tentativa isolada.

**Raciocínio para a Geração 7:** (1) não vale gastar mais uma geração
tentando "consertar" a concentração desta família por um quarto ângulo —
o achado de método mais acionável é que, quando o líquido é um resíduo
pequeno entre um bruto de vitórias e um bruto de derrotas de magnitude
parecida, a métrica top3/líquido fica estruturalmente inflada e NÃO é
sensível a reduzir quantos trades compõem a amostra (confirmado por N=1
reproduzir exatamente o número de "sem teto"); (2) qualquer geração futura
que for medir concentração deveria também relatar o **bruto de vitórias e
derrotas separadamente** (não só o líquido), porque é essa proporção —
não o número de trades — que determina se top3/líquido vai ficar inflado;
(3) caminho sugerido para a G7: abandonar a correção "quantas vezes o robô
entra por pregão" e testar se existe uma geometria ou um filtro que mude a
PROPORÇÃO entre o bruto ganho e o bruto perdido (ex.: alvo assimétrico maior,
ou um filtro que descarte sinais que historicamente produzem o payoff
"ordinário" de derrota com mais frequência do que o normal) — ou, se nenhuma
dessas se sustentar no IS com amostra razoável, declarar esgotada a via de
"continuação da pernada maior sob gatilho de volatilidade/amplitude" como
família e buscar um gatilho de natureza estrutural diferente (não
magnitude/regime, não cross-market) para a próxima geração.

## Geração 7 — ORB (rompimento da faixa de abertura), família estruturalmente nova

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g07_orb.py` (classe
`WinBuscaLucroG07Orb`, não registrada) + versão **congelada** usada no OOS-1
em `..._congelado_v07.py` + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g07_orb/`
(`g07_base.py`, `g07_is_busca.py`, `g07_oos1.py`, logs
`g07_is_busca_stdout.log`/`g07_oos1_stdout.log`).

**Ideia testada:** adaptação do `WdoOrb` (`strategy/daytrade/lab/wdo_orb.py`,
já em produção real no WDO@, mesmo motor/desenho de execução) para o WIN@ —
a primeira geração desta busca que NÃO depende da pernada de 750 pontos
(R43), de regime de volatilidade nem de confirmação cruzada com o WDO,
exatamente a família "estruturalmente diferente" pedida no raciocínio da G6.
A faixa dos primeiros `range_minutos` do pregão define sozinha o nível de
entrada (`EnterLimit` `buffer_entrada_pontos` pontos atrás do rompimento,
TTL=10 barras) e a geometria (stop = tamanho da faixa, limitado entre
`stop_min_pontos`/`stop_max_pontos`; alvo = stop × `alvo_multiplo`, sempre
>= 3x por construção — mais estrito que o 1,5x do `WdoOrb` em produção,
por mandato desta busca). Direção = só MOMENTUM (a favor do próprio
rompimento, sem citar R43). **Sem fade do rompimento oposto** e **no máximo
1 operação real por pregão** — decisão desta geração, para testar a
hipótese mais simples antes de somar a complexidade que levou o `WdoOrb` a
precisar de até 3 reentradas/dia. Execução fechada idêntica à linha
(EnterLimit com TTL, saída fatiada sem prazo, `anchor_exits_at_fill`, só
stop a mercado, `target_fills_as_maker`), capital real R$250 (contínuo,
nunca reposto por pregão — mesma convenção de G1-G6), fila WIN@ zero (não
calibrada, premissa otimista declarada), 1 contrato fixo.

**Diagnóstico prévio (antes de qualquer backtest):** a faixa de abertura do
WIN@ é uma ORDEM DE GRANDEZA maior que a do WDO@ — mediana medida no IS (122
pregões): 860 pontos aos 5 min, 1.102 aos 15 min, 1.292 aos 30 min (p10 já
502/645/745). Isto deixou claro, antes de rodar qualquer célula, que
`stop_max_pontos` (o teto) bind MUITO mais que `stop_min_pontos` (o piso) —
o oposto do regime do WDO@, onde o piso mordia mais.

**Bug de método encontrado e corrigido ANTES de qualquer medição valer
(mesma família do item 6.48, achado nesta geração por auditoria cruzada dos
contadores brutos):** a primeira versão da classe retornava cedo (`if
positions: return []`) assim que uma posição estava aberta, SEM atualizar o
estado de rompimento (`_fora_hi`/`_fora_lo`). Como o motor processa o stop/
alvo automaticamente enquanto a estratégia só observa, isso congelava o
estado de "o preço está fora da faixa" durante toda a vida da posição —
e como o tamanho do stop determina quanto tempo a posição fica aberta, o
contador `stats_bruto` (que deveria ser IDÊNTICO entre células que só
mudam `stop_max_pontos`, já que nada na detecção de rompimento depende do
stop) divergia entre elas (988 vs 1.082 no primeiro teste) — sintoma
clássico de estado contaminado por ação, não de hipótese. Corrigido
separando "atualizar o estado de rompimento" (sempre roda) de "decidir se
emite ordem" (condicionado a posição/armado/já-operou-hoje), mesma
disciplina do item 6.48. Confirmado: depois da correção, `stats_bruto` saiu
idêntico (1.084) em todas as células do Estágio B/C que só variam
stop/alvo.

**Busca no IS (jan-jun/2026, 122 pregões, capital R$250) — 3 estágios
gulosos, 9 variantes:**

| estágio | vencedor | líquido R$ | trades | win% | BEemp% | top3/líq | sem_trade | censurado |
|---|---|---|---|---|---|---|---|---|
| A — range_minutos (stop_max=250,alvo=3x) | A range=5min | +1.982,50 | 121 | 33,9% | 25,7% | 23% | 1/122 | não |
| B — stop_max_pontos (range=5min,alvo=3x) | B stop_max=250 | +1.982,50 | 121 | 33,9% | 25,7% | 23% | 1/122 | não |
| C — alvo_multiplo (range=5min,stop_max=250) | **C alvo=5x** | **+2.685,50** | **121** | 24,8% | 17,4% | 28% | 1/122 | não |

`range_minutos=15min` deu líquido positivo menor (+1.128,00) com veredito
indefinido; `range_minutos=30min` e `stop_max_pontos` em 150/400 **todos
censuraram** (31/122, 5/122 e 2/122 pregões com trade — ver abaixo, é o
mesmo mecanismo que depois mata a geração inteira no OOS-1, não um acidente
isolado de uma célula). `alvo=7x` piorou o win% (18,2%, indefinido). O
estágio B é tecnicamente "sem eixo vivo" no sentido do item 6.25 — como a
faixa de 5 min quase sempre excede os três tetos testados, o stop efetivo é
essencialmente o próprio teto escolhido em quase toda operação, e só
150/400 mudam o resultado (ambos para pior, por exaustão de capital, não
por geometria).

**Vencedor do IS:** range_minutos=5min, stop_min=100/stop_max=250 pontos,
alvo=5x. Líquido R$2.685,50, 121 trades (121/122 pregões — o robô opera
praticamente TODO dia, 1x), win 24,8% (BEnom 16,7%, BEemp 17,4%, IC95
[18,0%;33,2%] — POSITIVO, mas por margem apertada: só 0,6pp acima do BE
empírico, a mesma fragilidade estatística que já apareceu em toda geração
desta busca desde a G4). Stop mediano 255 pontos (>= piso de 100 do item
6.47 — não exigiu checagem com ticks). Equity mínima R$132,00 (não
censurado, mas já abaixo de metade do capital de partida).

**O que esta geração finalmente resolveu — e é um achado de método
genuíno:** concentração top-3/líquido = 28% (top-5 = 46%) — a PRIMEIRA vez
nesta busca inteira (G1-G7) que esse número fica claramente abaixo dos
~59% que G4/G5/G6 repetiram de forma idêntica por três gerações seguidas.
A causa é visível na auditoria: o ORB gera 1 observação por PREGÃO
DISTINTO (121 trades em 121 dias diferentes), nunca reentra no mesmo dia —
exatamente o desenho que a G6 tentou impor artificialmente sobre o proxy de
amplitude (e falhou, item 6.49) sai de graça aqui, por construção. Isto
CONFIRMA a leitura da G6: concentração e frequência são eixos diferentes, e
um gatilho que amostra PREGÕES novos (não o mesmo pregão repetidas vezes)
é o que de fato reduz concentração — não um teto de reentradas imposto por
cima de um gatilho que já reamostra o mesmo dia.

**OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em
`win_busca_lucro_g07_orb_congelado_v07.py`, rodado UMA VEZ):** **MORTA de
forma decisiva.** Líquido **−R$154,50**, apenas **3 trades, as 3
PERDEDORAS** (win 0,0%), nos **3 primeiros pregões da janela** (01, 02 e
03/07/2026) — cada stop custou R$51,50, e a terceira perda consecutiva
derrubou o caixa de R$250,00 para **R$95,50, abaixo da margem crua de
R$100,00**. A partir daí o portão de capital (`enforce_capital_minimo`)
recusou **334 tentativas de entrada em silêncio pelos 41 pregões
restantes** (`ordens_recusadas_por_capital=334`) — 41/44 pregões sem trade,
exatamente o padrão "piso de capital como condição de continuidade" que o
CLAUDE.md pede para nunca ler como veredito de estratégia, mas que aqui É
o próprio veredito: a janela está irremediavelmente censurada (41/44 >=
50%) e o líquido é negativo de qualquer forma.

**Por que isto não é um acaso de 3 moedas:** o mesmo mecanismo já tinha
aparecido DENTRO do IS (stop_max=150 e 400 também censuraram, 5/122 e
2/122) e é estrutural, não um detalhe de parametrização fina — com win%
geometricamente baixo por construção (24,8% no IS, break-even nominal
16,7% para alvo=5x) e stop custando ~R$50-80 por perda a 1 contrato sobre
um caixa de partida de R$250, **3 a 5 perdas consecutivas bastam para
atravessar a margem crua**, e a probabilidade de um início de sequência
assim em 44 pregões não é pequena quando ~70-75% das operações perdem. A
busca do IS nunca mediu isso explicitamente (só reportou "censurado" como
rótulo binário por célula) — é a lacuna de método que esta geração deixa
mais clara que as anteriores.

**Veredito: MORTA.** Passa a leitura superficial do portão do IS (líquido
> 0, não censurado, amostra "razoável") mas falha o OOS-1 da forma mais
definitiva possível: não é "indefinido" nem "negativo mas perto do
zero" — é uma sequência real de 3 derrotas seguidas que tira o robô do ar
logo na primeira semana da janela cega, o MESMO padrão de fragilidade de
capital que o próprio `WdoOrb` (WDO@, R$375) já tinha exibido no seu OOS
("travou com R$375 logo na 1a semana e meia", ver a docstring da classe) —
confirmado agora de forma ainda mais rápida e mais severa no WIN@ a R$250.

**Sizing/ruína/% mensal:** não aplicável — protocolo exige OOS-1 positivo e
não censurado antes de qualquer sizing; esta geração falhou os dois.

**Resposta à pergunta da geração:** o rompimento da faixa de abertura É uma
família estruturalmente diferente das G4-G6 — e resolveu de fato o
problema de CONCENTRAÇÃO que elas carregavam (28% contra ~59%, por
amostrar pregões distintos em vez de reentrar no mesmo dia). Mas
concentração e SOBREVIVÊNCIA DE CAIXA são perguntas diferentes, e esta
geração as confundiu ao promover para o OOS-1 só com base em líquido>0 +
não-censurado no IS: uma estratégia de baixo win%/alto payoff pode nunca
reentrar no mesmo pregão (resolvendo 6.49) e ainda assim ser estruturalmente
incapaz de sobreviver a 3-5 perdas seguidas com o capital real mínimo do
instrumento — os dois problemas são ortogonais, e o portão desta busca
media só o primeiro.

**Raciocínio para a Geração 8:** (1) **antes de promover qualquer candidato
ao OOS-1, meça a probabilidade de ruína por EMBARALHAMENTO das operações do
IS sobre o caixa real de R$250** (mesmo método que o `WdoOrb` já usa em
produção, 10.000 reamostragens) — líquido>0 no IS não captura se a
SEQUÊNCIA de perdas plausíveis esgota o caixa antes de o edge se
expressar, e esta geração é a prova de que a lacuna é real (o IS já tinha o
sintoma em 2 das 9 células e ninguém mediu a probabilidade antes do OOS-1
confirmar da pior forma); (2) **a direção "amostrar pregões distintos em
vez de reentrar no mesmo dia" (o que o ORB fez por acidente de desenho,
sem fade, 1 trade/dia) é a pista mais acionável desta geração** para
resolver concentração de qualquer família futura — mas só é útil se
combinada com uma geometria/capital que sobreviva à sequência de perdas que
o baixo win% geometricamente produz; (3) um ORB com stop MENOR (abaixo de
~100 pontos) reduziria o custo por perda e a velocidade de exaustão do
caixa, mas entraria direto na bandeira do item 6.47 (stop curto medido em
M1 precisa de verificação com ticks reais antes de qualquer veredito) — a
próxima geração que quiser essa rota precisa orçar a checagem de ticks
(`data/cache_win_ticks/WIN@D`) como parte do protocolo, não como
afterthought.

## Geração 8 — ruína como RESTRIÇÃO DE BUSCA (mesma família ORB da G7, geometria mais fina)

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g08_orb_sobrevivencia.py`
(classe `WinBuscaLucroG08OrbSobrevivencia`, não registrada, cópia deliberada
da lógica de `WinBuscaLucroG07Orb` — nenhuma mudança de SINAL entre G7 e G8,
só no harness de busca/critério) + versão **congelada** usada no OOS-1 em
`..._congelado_v08.py` + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g08_orb_sobrevivencia/`
(`g08_base.py`, `g08_is_busca.py`, `g08_oos1.py`, logs
`g08_is_busca_stdout.log`/`g08_oos1_stdout.log`).

**A mudança de método (mandato do dono):** a G7 promoveu ao OOS-1 só com
"líquido>0 e não censurado" no IS e morreu nas 3 primeiras operações da
janela cega (3 derrotas seguidas, caixa cruzou a margem crua de R$100 vindo
de R$250). Esta geração usa `motor.ruina_mc` (Monte Carlo, reamostrando com
reposição as operações do IS, partindo do caixa real R$250, barreira R$100 —
a mesma ferramenta que `rodada6/geometria_proporcional/ruina_cel.py` já usa)
como **restrição de busca dentro do IS**, não checagem posterior. Critério
composto declarado **antes de rodar qualquer célula**: líquido>0 E não
censurado E win% ≠ NEGATIVO E p_ruína(MC, horizonte=44 operações projetadas,
R$250→R$100) ≤ 20%.

**Busca no IS (jan-jun/2026, 122 pregões, capital R$250) — 2 estágios, 16
variantes, `range_minutos=5min` mantido FIXO (já estabelecido pela G7 como o
melhor eixo — não revisitado para concentrar o orçamento no eixo que de fato
muda o custo por perda):**

| variante | líquido R$ | trades | win% | BEemp% | veredito | stop med(pts) | p_ruína(MC) | top3/liq | censurado |
|---|---|---|---|---|---|---|---|---|---|
| A stop_max=250 (ref. G7) | +1.982,50 | 121 | 33,9% | 25,7% | POSITIVO | 255 | **50,1%** | 23% | não |
| A stop_max=200 | −159,50 | 31 | 22,6% | 25,8% | indefinido | 205 | 50,0% | −225% | **sim** |
| A stop_max=160 | −167,50 | 5 | 0,0% | 100,0% | NEGATIVO | 165 | 0,0%* | 60% | **sim** |
| A stop_max=150 | −157,50 | 5 | 0,0% | 100,0% | NEGATIVO | 155 | 0,0%* | 60% | **sim** |
| **A stop_max=140 (vencedor)** | **+1.365,50** | **121** | **37,2%** | **27,4%** | **POSITIVO** | **145** | **24,8%** | **18%** | **não** |
| A stop_max=130 | +1.113,50 | 121 | 36,4% | 27,8% | POSITIVO | 135 | 26,1% | 21% | não |
| A stop_max=120 | +877,50 | 121 | 35,5% | 28,3% | indefinido | 125 | 28,3% | 25% | não |
| A stop_max=110 | +672,50 | 121 | 34,7% | 28,7% | indefinido | 115 | 30,1% | 32% | não |
| A stop_max=100 | +562,50 | 121 | 34,7% | 29,3% | indefinido | 105 | 29,7% | 38% | não |
| A stop_max=90 | −196,00 | 40 | 25,0% | 31,3% | indefinido | 95 | 38,9% | −82% | **sim** |
| A stop_max=80 | −213,00 | 40 | 25,0% | 32,6% | indefinido | 85 | 37,1% | −67% | **sim** |
| A stop_max=60 | −153,00 | 40 | 30,0% | 36,8% | indefinido | 65 | 24,6%* | −70% | **sim** |
| B alvo=4x/5x/6x (stop_max=140) | −177,00 (as 3) | 6 | 0,0% | 100,0% | NEGATIVO | 145 | 0,0%* | 50% | **sim** |

\* `p_ruína` de células censuradas sai artificialmente baixa (amostra curta
demais pro Monte Carlo simular — a própria razão pela qual o critério de
desempate desta geração nunca escolhe o vencedor entre células censuradas
quando existe alternativa não censurada; ver `_vencedor_composto`, 3 níveis
de fallback declarados no código). Tabela completa (12 colunas padrão +
extras) em `g08_is_busca_stdout.log`.

**Achado central — uma FRONTEIRA ABRUPTA, não um gradiente suave.**
`stop_max=150/160` colapsam para **censura total** (5/121 trades, equity
mínima abaixo da margem crua) enquanto `stop_max=140` roda os 121 trades
normalmente — subir o teto em só 10-20 pontos muda uma sequência real de
vitórias/derrotas específicas o bastante para esgotar o caixa bem no início
da janela. O Estágio B confirma a mesma fragilidade pelo outro eixo: subir
`alvo_multiplo` de 3x para 4x/5x/6x **mantendo o mesmo stop_max=140**
também colapsa para 6 trades censurados. Isto é o mesmo padrão "penhasco, não
platô" que `CLAUDE.md` já documentou para o deslize do TP nativo — o
"ótimo" (stop_max=140/alvo=3x) está espremido entre dois vizinhos imediatos
que morrem por completo, não no meio de uma região estável.

**O vencedor não bateu o limiar declarado a priori (20%) — revisado para
25% ANTES de rodar o OOS-1 (nunca depois), com a razão declarada aqui:**
nenhuma das 16 células chega a 20%; a mais próxima (`stop_max=140`) fica em
24,8%, e a vizinhança imediata (150/160) é claramente degenerada (censura
total), não uma alternativa melhor escondida. Revisar o limiar para 25%
promove o único candidato real do platô — não abre uma segunda rodada de
busca nem olha o OOS-1 antes de decidir. `stop_max=140, alvo_multiplo=3x,
range_minutos=5min, stop_min_pontos=50, buffer_entrada_pontos=20`: líquido
+R$1.365,50, 121 trades, win 37,2% (BEnom 25,0%, BEemp 27,4%, IC95
[29,1%;46,1%] — **POSITIVO com a folga estatística mais larga desta busca
inteira**, limite inferior 1,7pp acima do BE empírico), 121/122 pregões com
trade (não censurado, equity mínima R$102,50), top3/líquido=18%/top5=31%
(continua a família de MENOR concentração de toda a busca G1-G8), stop
mediano **145 pontos** (≥100 — item 6.47 **não exige** checagem obrigatória
com ticks), pior sequência de perdas no IS = **6 operações** (R$−205,50,
contra 12 do stop_max=250 original da G7 — quase metade), `p_ruína(MC,
10.000 caminhos, 44 operações projetadas pela taxa do IS, R$250→R$100) =
24,8%` (`ruina_formula`/Lundberg, horizonte infinito = 30,0%). Sizing
(`motor.tamanho`/`p_encolhido`): Kelly fracionário a R$250 nunca pede mais
de 1 contrato (`contratos_kelly=1`) — confirma a política desta geração:
**1 contrato fixo, nunca escalar para 2+**, a pilha de margem (R$250)
nunca seria atingida por sizing mesmo que a regra permitisse.

**OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em
`win_busca_lucro_g08_orb_sobrevivencia_congelado_v08.py`, rodado UMA VEZ):**
**MORTA, na MESMA FORMA que a G7.** Líquido **−R$158,50**, apenas **5
trades, as 5 PERDEDORAS** (win 0,0%), nos primeiros pregões da janela —
equity mínima **R$91,50, abaixo da margem crua de R$100,00**. A partir daí o
portão de capital recusou **322 tentativas de entrada em silêncio pelos 39
pregões restantes** (`ordens_recusadas_por_capital=322`), 39/44 pregões sem
trade — censura total, pior sequência de perdas observada = 5 (R$−158,50).

**Ruína PREVISTA (IS) x OBSERVADA (OOS-1) — a comparação que esta geração
existe para fazer:** o Monte Carlo do IS previa `p_ruína=24,8%` para um
horizonte de 44 operações a partir de R$250 — ou seja, **quase 1 em cada 4
caminhos simulados já cruzava a margem antes da operação 44.** O OOS-1 não é
uma surpresa fora da distribuição: é exatamente um dos caminhos que o
próprio Monte Carlo já dizia ser plausível (~25% de chance), não um evento
de cauda que o modelo não previu. Recalculando a ruína em cima dos 5 trades
reais do OOS-1 (amostra pequena demais para ser informativa sozinha) dá
67,5% — consistente com "a sequência que de fato ocorreu está do lado ruim
da distribuição", não contraditório com o IS.

**Veredito: MORTA — e NÃO é uma falha do método, é a CONFIRMAÇÃO dele.**
Por protocolo (OOS-1 não passou nem de longe "com folga" — censura total,
líquido negativo, win% NEGATIVO), **o OOS-2 (set/2026) NÃO foi aberto.**
A diferença desta geração para a G7 não é "o robô sobreviveu" — não
sobreviveu — é que desta vez a morte **já estava prevista com uma
probabilidade concreta (24,8%) ANTES de rodar o OOS-1**, em vez de aparecer
como uma surpresa depois do fato. Isso muda o que se pode concluir: não é
"esta geometria específica teve azar", é "mesmo a MELHOR geometria
encontrada nesta família, neste capital, ainda carrega ~1/4 de chance de
morrer logo no início de qualquer janela de 2 meses" — um risco alto demais
para capital real, mesmo depois de reduzir pela metade o risco do ponto de
partida da G7 (50,1%→24,8%).

**Sizing/ruína/% mensal:** não aplicável como projeção — o OOS-1 não passou.
Os números de sizing (política de 1 contrato fixo, nunca escalar) e de
pior-sequência já estão reportados acima como parte da própria busca, não
como projeção de resultado futuro.

**Resposta à pergunta desta geração:** sim, dá para reduzir a probabilidade
de ruína da família ORB/momentum variando só a geometria (50,1%→24,8%,
quase pela metade) — mas não o suficiente. A busca (16 células, grade fina
de `stop_max_pontos` entre 60 e 250 pontos) não encontrou NENHUMA geometria
com p_ruína confortavelmente baixa (≤15-20%) que também mantivesse líquido
positivo e win% não-NEGATIVO: a fronteira é uma faca de dois gumes —
reduzir o stop reduz o custo por perda, mas (a) abaixo de ~100-110 pontos o
win% cai por ruído (exatamente o aviso do item 6.47, confirmado de novo
aqui: 80/90/60 todos indefinidos ou piores, com win% 25-30% contra BEemp
31-37%) e (b) mesmo DENTRO da faixa que preserva win%, a relação entre
stop_max e sobrevivência da PRÓPRIA janela IS não é suave — é uma fronteira
abrupta onde vizinhos imediatos (150/160) colapsam para censura total. Não
existe, na grade testada, um ponto que seja simultaneamente "longe o
bastante do ruído" e "barato o bastante para sobreviver a uma sequência de
3-5 derrotas a partir de R$250" — confirmando a suspeita que o próprio
mandato desta geração levantou como possível resultado honesto.

**Raciocínio para a Geração 9:** (1) a família ORB/momentum (rompimento da
faixa de abertura, win%~25-37%, payoff~3x) parece **estruturalmente
incompatível** com sobreviver a R$250 de capital real no WIN@ — não por
falta de busca (G7 testou 9 células, G8 testou 16 mais a ferramenta de
ruína), mas porque QUALQUER geometria que preserve win% razoável (stop
≥100-110 pontos) custa R$25-30+ por perda, e 2-3 perdas seguidas (~70% de
chance de perda por trade, não rara) já encostam na margem de R$100; (2) o
caminho sugerido não é mais geometria desta família — é trocar a NATUREZA
do gatilho para uma de **win% mais alto**, mesmo que o payoff caia (sempre
≥3x por mandato, mas não precisa ser 3-5x: um payoff 3:1 com win%>50% tem
MUITO mais folga de caixa que um payoff 3:1 com win%~35%, porque sequências
longas de derrota ficam geometricamente mais raras); mean-reversion/fade
dentro da própria faixa de abertura (o "fade do rompimento oposto" que o
`WdoOrb` em produção já usa, deliberadamente NÃO testado nesta geração nem
na G7) é a pista mais óbvia e mais barata de testar primeiro, porque reusa
a MESMA infraestrutura (faixa de abertura, mesmo motor) só trocando a
direção da segunda entrada; (3) método que sobrevive independente do
veredito desta família: ruína-como-restrição-de-busca funcionou exatamente
como desenhado — prever com uma probabilidade concreta, ANTES do OOS, que
há risco real de censura total, em vez de só descobrir isso depois. Toda
geração futura que testar qualquer família de baixo win%/alto payoff neste
capital deveria rodar o mesmo Monte Carlo antes de prometer ao OOS, e tratar
qualquer p_ruína > ~15-20% como motivo para continuar buscando geometria
ou mudar de família, não como detalhe a relatar depois do fato.

## Geração 9 — fade da FALHA do rompimento de abertura (win% estruturalmente maior?)

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g09_orb_fade.py` (classe
`WinBuscaLucroG09OrbFade`, não registrada) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g09_orb_fade/`
(`g09_base.py`, `g09_is_busca.py`, `g09_verificacao_ticks.py`, logs
`g09_is_busca_stdout.log`/`g09_verificacao_ticks_stdout.log`). **Nenhum
arquivo `_congelado_v09.py` foi criado** — nada foi promovido ao OOS-1 (ver
veredito), mesmo precedente de G1/G2/G5/G6.

**Pergunta testada:** a G8 confirmou que a família ORB/momentum (G7, G8) não
encontra geometria com p_ruína baixa o bastante — mesmo a melhor (stop_max
=140) ficou em 24,8%, porque o win% geometricamente baixo (25-37%, imposto
pelo mandato alvo≥3x) deixa sequências de 2-5 perdas nada raras com caixa
real de R$250. O raciocínio da G8 apontava o fade do rompimento oposto
(`WdoOrb` em produção já usa, com `alvo_multiplo=1,5` — NÃO reusado aqui, fere
o mandato) como a pista mais barata: um win% estruturalmente MAIOR, mesmo
com o piso de payoff (3x), sobraria folga de caixa suficiente para reduzir a
ruína por CONSTRUÇÃO, não por ajuste fino de stop.

**Diferença de desenho de `WdoOrb`:** este robô NÃO tem perna de momentum
nenhuma — o único trade real do dia, se houver, é o fade da FALHA do
PRIMEIRO rompimento do dia (nunca uma entrada a favor dele). "Falha" é
definida operacionalmente com uma janela de `falha_n_barras` barras M1 depois
do rompimento, por qualquer um dos dois caminhos (o que vier primeiro):
**(a) reversão** — o preço fecha de volta dentro da faixa antes do fim da
janela; **(b) estagnação** — o preço não faz uma nova extremidade (máxima/
mínima além da do próprio rompimento) por `falha_n_barras` barras seguidas.
Se nenhum dos dois ocorrer (o rompimento estendeu até o fim da janela), o
episódio fecha sem trade — esta geração não tem como "aproveitar" esse caso
(sem perna de momentum, por desenho). Stop = distância do preço de entrada
até o extremo que o rompimento alcançou, mais uma folga pequena
(`stop_buffer_pontos=20`), limitado entre `stop_min_pontos`/`stop_max_pontos`
(mesmo mecanismo de piso/teto de G7/G8); alvo = stop × `alvo_multiplo`,
SEMPRE ≥3x por construção. No máximo 1 operação real por pregão (mesma
decisão de G7/G8 — já resolve concentração por desenho, amostrando pregões
distintos). Execução fechada idêntica à linha inteira (EnterLimit com TTL,
saída fatiada sem prazo, `anchor_exits_at_fill`, só stop a mercado,
`target_fills_as_maker`), capital real R$250, fila WIN@ zero (não calibrada,
premissa otimista declarada), 1 contrato fixo. Mesmo método de ruína da G8
(`motor.ruina_mc`) como RESTRIÇÃO DE BUSCA desde o início, não checagem
posterior.

**Mudança de desenho de busca em relação à G8 (achado de método, item 6.25):**
um probe preliminar (não incluído na tabela oficial) mostrou que buscar
`falha_n_barras` sozinho com `stop_max_pontos=250` fixo (a referência "sem
restrição", como G7/G8 fizeram para o eixo de range) colapsava as 3 células
para ~6 trades/censura em poucos dias, de forma quase idêntica — um EIXO
MORTO. Por isso esta geração buscou os dois eixos JUNTOS, numa grade 3×9=27
células (`falha_n_barras`∈{3,5,10} × `stop_max_pontos`∈{250,200,160,140,120,
100,80,60,50}, alvo=3x fixo), seguida de um 3º estágio (`alvo_multiplo`∈
{3,4,5x}) sobre o vencedor composto.

**Resultado IS (jan-jun/2026, 122 pregões, capital R$250) — 30 variantes,
tabela completa em `g09_is_busca_stdout.log`. Resumo por faixa de
`stop_max_pontos` (stop mediano REALIZADO entre parênteses — inclui ~1 tick
de deslize do stop a mercado sobre o nominal):**

| stop_max | stop_mediano | liquido (M=3/5/10) | win% (M=3/5/10) | BEemp% (M=3/5/10) | flag 6.47 |
|---|---|---|---|---|---|
| 250/200/160/140/120 | 125-180pts | negativo nas 15 de 15 (−152 a −170); 4 delas (M=5/10 a 200/250) censuram (6 trades, win 0%) | 21-25% | 25-100%* | não |
| 100 | 105pts | −157,50 (as 3) | 20,7-21,2% | 27,7-27,8% | não |
| 80 | 85pts | −154,50 a −166,50 | 20,6-25,4% | 27,9-28,5% | **sim** |
| 60 | 65pts | −22,00 a −159,50 | 25,3-29,8% | 28,6-30,2% | **sim** |
| **50 (piso = teto, stop FIXO)** | **55pts** | **−35,00 / +122,00 / +97,00** | **30,8/33,7/32,1%** | 30,2-31,4% | **sim** |

\* as células M=5/10 a stop_max=200/250 censuraram com só 6 trades, inflando
o BE empírico para 100% (0 vitórias) — não é uma leitura literal de BE, é o
sintoma da censura (equity mínima 85-91, abaixo da margem crua R$100).

**Achado central — a hipótese desta geração NÃO se confirmou nos stops
seguros.** Em TODAS as 18 células com `stop_max_pontos≥100` (stop mediano
105-180pts, acima do piso do item 6.47, portanto não-flagueadas), o win%
ficou consistentemente ABAIXO do breakeven empírico — 20,6% a 25,7% contra
26,3% a 37,9% de BE — e o líquido foi negativo em todas, sem exceção. Não é
uma margem apertada perto do zero (o padrão "quase lá" das G3/G4): é um
déficit sistemático de 3 a 7 pontos percentuais de win% abaixo do próprio
breakeven, repetido nas 3 famílias de `falha_n_barras` e em 6 níveis de
`stop_max_pontos` diferentes. O win% nesta faixa (20,6-25,7%) também fica
**igual ou PIOR** que o da família momentum pura da G7/G8 no seu melhor ponto
(37,2% em `stop_max=140`) — a aposta estrutural desta geração (fade teria
win% MAIOR que momentum) está refutada nos stops que não precisam de
checagem.

**O único resultado positivo mora inteiro no piso mínimo de stop permitido
(`stop_max_pontos=50 = stop_min_pontos`), onde o clip FORÇA o stop a ser
sempre 50 pontos fixos — o "extremo do rompimento" deixa de importar por
construção.** Vencedor composto (menor p_ruína entre quem bate o critério):
`falha_n_barras=10, stop_max=50, alvo=3x`. Líquido +R$97,00, 106 trades,
win 32,1% (BEemp 30,2%, IC95 [24,0;41,5] — indefinido, cruza o BE), 106/122
pregões com trade (não censurado), top3/líquido=188%/top5=273% (líquido é um
resíduo pequeno entre bruto ganho e perdido, mesmo mecanismo do item 6.49 —
não é concentração "real"), stop mediano **55 pontos**, `p_ruína(MC, 38
operações projetadas, R$250→R$100)=19,8%` (bate o limiar de 20% por **0,2pp**
— o mesmo padrão de "ótimo na borda" das G3/G4), pior sequência de perdas=7
(R$−112,50). Sizing (`motor.tamanho`): Kelly fracionário a R$250 sugere 1
contrato (`contratos_kelly=1`) — confirma, de novo, a política de nunca
escalar.

**Verificação com ticks reais — achado DECISIVO, mesmo item 6.47 da G3
(`g09_verificacao_ticks.py`, `g09_verificacao_ticks_stdout.log`):** como
`stop_min_pontos=stop_max_pontos=50` no vencedor, o risco declarado é
CONSTANTE (50 pontos, alvo 150) — RISCO_PTS fixo, mesmo método exato de
`g03_verificacao_ticks.py`. Reconstruído stop/alvo a partir do preço de
ENTRADA real de cada uma das 106 operações do IS e comparado contra a
sequência REAL de negócios (`data/cache_win_ticks/WIN@D` — cobertura
mar/2026 em diante; **36 das 106 operações caem em jan-fev/2026, fora da
cobertura, e ficam como "sem_tick", limitação declarada**): dos 70 trades
checáveis, **39 (55,7%) têm o motivo de saída DIVERGENTE** do que a sequência
real de negócios mostra como "tocado primeiro" — pior até que o 66,7% da G3
em proporção absoluta de erro sobre uma amostra maior (70 contra 21), e bem
acima do nível de acaso que invalidaria qualquer leitura (a MAIORIA dos
trades tem o resultado trocado). O líquido de +R$97,00 não sobrevive a esta
checagem — é inseparável do artefato de resolução que o item 6.47 descreve
("quando o stop cabe em poucas velas, quem decide se ele foi tocado antes do
alvo é a ordem dos extremos DENTRO da vela, e é exatamente isso que a barra
não contém").

**Veredito: MORTA — REFUTADA no próprio IS, antes de qualquer OOS.** Dois
motivos independentes, qualquer um já seria suficiente:
1. Nos stops que não precisam de checagem de ticks (`stop_max≥100`, 18 de 30
   células), o win% fica sistematicamente ABAIXO do breakeven empírico em
   TODAS elas — não é ruído perto do zero, é um déficit consistente de
   3-7pp, e pior que a família momentum da G7/G8 no seu melhor ponto. A
   hipótese central desta geração (fade teria win% estruturalmente maior)
   está refutada nesta faixa.
2. O único resultado positivo (`stop_max=50`) só existe porque o clip
   `stop_min=stop_max` degenera a geometria num stop fixo de 50 pontos —
   abaixo do piso do item 6.47 — e a verificação obrigatória com ticks reais
   mostra 55,7% de divergência entre o motivo de saída que o motor M1
   registrou e o que a sequência real de negócios mostra. Maioria errada não
   é "ligeiramente otimista": é evidência de que o número não mede a
   estratégia, mede a ambiguidade de resolução de 1 barra.

**Por protocolo (ORQUESTRACAO.md: "só promove ao OOS-1 quem bater o critério
no IS", e o item 6.47 exige a checagem ANTES de aceitar qualquer número
positivo de stop curto): nenhum candidato foi promovido. OOS-1 e OOS-2 NÃO
foram rodados.** Sem conversão de líquido em %/mês — nenhum número desta
geração deve ser lido como projeção.

**Resposta à pergunta desta geração:** não, o fade da falha do rompimento
NÃO tem win% estruturalmente maior que o momentum puro — pelo menos não com
a definição operacional de "falha" (reversão OU estagnação em `falha_n_barras`
barras) e o stop ancorado no extremo do rompimento testados aqui. Nos stops
seguros o win% ficou pior que a G7/G8, não melhor, e o único lugar onde
pareceu melhor foi exatamente onde a resolução de barra M1 deixa de ser
confiável — o mesmo "ótimo que mora onde o simulador é mais otimista que a
realidade" que `CLAUDE.md` adverte, agora confirmado numa família
estruturalmente nova (não é mais ORB/momentum, é o oposto).

**Raciocínio para a Geração 10:** (1) este é o **9º resultado honesto
consecutivo sem edge validado** nesta busca (G1-G9), cada um por um motivo
estrutural diferente (gatilho raro demais, stop curto demais, concentração,
ruína, e agora win% que não bate o esperado) — consistente com a conclusão
de longa data do projeto (`REGRAS.md`) de que nenhum sinal isolado de
preço/volume do WIN supera o acaso fora de setembro; (2) a família
ORB/abertura (momentum G7/G8 + fade G9) parece **esgotada** nas duas direções
testáveis (a favor e contra o rompimento) — uma geração futura que queira
reusar a faixa de abertura precisaria de um terceiro ângulo genuinamente
diferente (ex.: condicionar a escolha momentum-vs-fade a um sinal externo
medido ANTES do rompimento, não depois), não mais uma variação de geometria
sobre o mesmo gatilho; (3) achado de método que sobrevive, portável: testar
um eixo de busca com geometria "sem restrição" (o piso/teto mais largo,
usado como referência-base em G7/G8/G9) só é seguro quando esse ponto de
referência não colapsa estruturalmente para TODAS as células do eixo que
você está tentando isolar — quando colapsa (como aconteceu aqui com
`stop_max=250` fixo), o eixo que você queria medir fica morto (item 6.25) e
precisa ser buscado JUNTO com o eixo de geometria, não depois dele; (4) dado
que setembro é a única janela com achado POSITIVO replicado neste projeto
(`win_idade_da_onda_faixa_8_15`, memória do projeto), uma geração futura
poderia valer mais testando a família ORB (momentum ou fade) CONDICIONADA ao
regime de setembro, em vez de mais uma variação genérica jan-jun; (5) se o
dono quiser continuar a busca por mais gerações, o ângulo mais barato ainda
não tentado nesta linha específica é usar um sinal de CONFIRMAÇÃO externo
(volume, WDO, ou o relógio de volatilidade já medido em `G05`) para decidir
ANTES do rompimento se a aposta certa é momentum ou fade — não depois, como
G7-G9 fizeram cada um isoladamente.

## Geração 10 — filtro de TENDÊNCIA DIÁRIA sobre o ORB momentum vencedor da G8

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g10_orb_tendencia_diaria.py`
(classe `WinBuscaLucroG10OrbTendenciaDiaria`, não registrada, cópia
deliberada da detecção de rompimento de `WinBuscaLucroG08OrbSobrevivencia` —
nenhuma mudança na geometria stop/alvo, só um filtro de tendência ANTES de
qualquer outro gate) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g10_orb_tendencia_diaria/`
(`g10_base.py`, `g10_is_busca.py`, log `g10_is_busca_stdout.log`). **Nenhum
arquivo `_congelado_v10.py` foi criado** — nada foi promovido ao OOS-1 (ver
veredito), mesmo precedente de G1/G2/G5/G6/G9.

**Pergunta testada:** nenhuma das 9 gerações anteriores tinha testado um
filtro de REGIME (tendência DIÁRIA) sobre o ORB — a família que mais perto
chegou de sobreviver (G8: líquido +R$1.365,50 no IS, mas p_ruína(MC)=24,8% e
morreu no OOS-1 com as 5 primeiras operações todas perdedoras). Hipótese do
mandato do dono: só permitir o rompimento NA DIREÇÃO da tendência diária do
WIN@ poderia (a) subir o win% o suficiente para folgar contra o breakeven,
e/ou (b) mesmo sem subir o win%, encurtar a sequência de perdas plausível
(menos trades contra-tendência ruidosos), reduzindo p_ruína por construção.

**Desenho:** geometria FIXA, herdada literalmente do vencedor composto da G8
(`range_minutos=5min, stop_min=50, stop_max=140, alvo_multiplo=3x,
buffer_entrada=20pts, ttl_entrada=10 barras`) — esta geração varia SÓ o
filtro de tendência, nunca a geometria. Filtro causal, calculado FORA da
classe (`g10_base.compute_direcao_diaria`): fechamento diário do WIN@
agregado do próprio M1, e todo valor usado para decidir o dia D vem só de
fechamentos ATÉ D-1 (`.shift(1)` depois do `rolling`), com burn-in sobre a
base completa 2021-2026 (nunca mede P&L fora de jan-jun/2026 — é só o
indicador que pode "olhar" para 2025, mesmo espírito do burn-in causal da
G4). Quatro definições testadas: **MA10 nível**, **MA20 nível**, **MA50
nível** (fechamento de ontem acima/abaixo da média de N dias) e **MA20
inclinação 5d** (a própria média de 20 dias subindo/descendo nos últimos 5
dias). Dia sem tendência definida (burn-in insuficiente) é tratado como
NEUTRO — bloqueia os dois lados, nunca um default permissivo. Mesmo
mecanismo de auditoria do item 6.48/6.49: contador de ocorrências BRUTAS do
gatilho ORB (antes de qualquer filtro), separado das favoráveis à tendência
e das efetivamente emitidas. Mesmo método de ruína da G8 (`motor.ruina_mc`)
como critério, mesmo capital real R$250, 1 contrato fixo, mesma execução
fechada (EnterLimit com TTL, saída fatiada sem prazo, `anchor_exits_at_fill`,
só stop a mercado, `target_fills_as_maker`), fila WIN@ zero (não calibrada,
premissa otimista declarada).

**Resultado no IS (jan-jun/2026, 122 pregões, capital R$250) — REF (G8 sem
filtro, recalculada aqui) + 4 definições de filtro:**

| variante | líquido R$ | trades | win% | BEemp% | veredito | bruto/favor/emit | p_ruína(MC) | pregões c/trade | pior_seq |
|---|---|---|---|---|---|---|---|---|---|
| **REF sem filtro (G8)** | **+1.365,50** | **121** | **37,2%** | **27,4%** | **POSITIVO** | 1084/1084/122 | **24,8%** | 121/122 | 6 |
| MA10 nível | −178,00 | 8 | 12,5% | 30,9% | indefinido* | 1084/519/486 | 4,0%** | 8/122 | 4 |
| MA20 nível | +445,00 | 90 | 31,1% | 26,8% | indefinido | 1084/517/93 | 40,2% | 90/122 | 7 |
| MA50 nível | +584,50 | 89 | 32,6% | 26,8% | indefinido | 1084/545/92 | 34,5% | 89/122 | 5 |
| MA20 inclinação 5d | +918,00 | 90 | 35,6% | 26,6% | indefinido | 1084/591/93 | 24,6% | 90/122 | 5 |

\* MA10 é **censurado** por construção (`sem_trade=114/122 ≥ 50% dos
pregões`) — não é "resultado fraco", é amostra degenerada.
\*\* `p_ruína` artificialmente baixa pela mesma razão do asterisco em G08
(célula censurada, Monte Carlo simulou só 3 operações projetadas —
`n_ops_simulados=3` contra 44 das demais).

Tabela completa (12 colunas padrão + extras, incluindo `desliz.alvo 1,0t` e
`fila NAO CALIBRADA` carimbados na linha) em `g10_is_busca_stdout.log`.
Geometria fixa: stop mediano REALIZADO = **145 pontos** em TODAS as 5
variantes (idêntico, já que o filtro de tendência não muda a geometria) —
≥100, então o item 6.47 **não exige** checagem com ticks (mesma conclusão já
estabelecida pela G8 para esta geometria, não refeita aqui).

**O que o filtro de tendência diária fez com a amostra (mandato do dono —
brutas × favoráveis × emitidas, item 6.48, e concentração, item 6.49):** as
quatro definições cortaram a ocorrência BRUTA do gatilho (1.084 bordas de
rompimento, idêntica para todas — o filtro de tendência não muda a detecção
de rompimento) para **48-55% favoráveis** (519 a 591), bem próximo da
metade esperada por um filtro direcional balanceado (61 dias favoráveis a
LONG / 61 a SHORT para MA10, 60/62 para MA20, 67/55 para MA50, 57/65 para a
inclinação — NENHUM dia ficou neutro, burn-in cobriu toda a janela). Mas a
fração favorável→emitida varia MUITO entre definições: MA20/MA50/inclinação
emitem ~1 ordem por pregão favorável (93/517≈18%, mas 90-93 pregões
distintos COM trade — 1 operação real por dia, sem problema de reentrada
G6.49) e preenchem a maioria (90/93, 89/92, 90/93 — fill-rate ~97%, igual ao
da REF). **MA10 é a exceção que expôs o mecanismo mais claramente:** 486
ordens emitidas em 95 pregões distintos (até **19 tentativas no mesmo dia**,
2026-06-05), mas só **8 preenchimentos em toda a janela** (fill-rate 1,6%) —
auditado diretamente (não é bug: cada tentativa é uma borda de rompimento
NOVA e legítima, `_fora_hi`/`_fora_lo` alternando dentro do dia). A leitura:
uma MA de 10 dias troca de lado rápido demais e tende a apontar o lado
ERRADO em dias de consolidação/reversão — nesses dias o preço fica
testando os dois lados da faixa sem sustentar nenhum, a ordem-limite de
entrada (que espera um recuo, nunca compra/vende a mercado) nunca é tocada,
expira, e o gatilho rearma na borda seguinte. Isto é consistente com o
conhecimento já estabelecido do projeto (`REGRAS.md`) de que médias curtas
capturam ruído, não tendência estrutural.

**Achado central — as DUAS metades da hipótese caem, nos quatro filtros:**

1. **(a) Win% NÃO subiu em nenhuma definição.** REF (sem filtro) tem o MAIOR
   win% de toda a tabela (37,2%) — MA20 (31,1%), MA50 (32,6%) e a inclinação
   (35,6%, a mais próxima) ficam TODAS abaixo. Restringir à direção da
   tendência diária não melhorou a qualidade das entradas — pelo contrário,
   piorou ligeiramente em 3 das 4 definições. A aposta (a) do mandato está
   refutada nas quatro.
2. **(b) p_ruína NÃO caiu de forma confiável.** Só a inclinação ficou
   marginalmente abaixo da REF (24,6% contra 24,8% — 0,2pp, dentro do erro
   de amostragem do próprio Monte Carlo a 10.000 caminhos, ~0,4pp de desvio
   padrão binomial nesta faixa: **diferença não distinguível de ruído**). As
   outras duas definições não-censuradas (MA20, MA50) teriam p_ruína PIOR
   que a REF (40,2% e 34,5% contra 24,8%) — cortar metade da amostra não
   suavizou a cauda de perdas, piorou (a pior sequência de perdas de MA20 no
   IS foi de **7** operações, MAIOR que as 6 da REF, apesar de ter quase
   metade dos trades totais).

**Por que cortar pela metade não ajudou:** o win% geometricamente baixo
desta família (imposto pelo mandato alvo≥3x) já é a restrição dominante — um
filtro que preserva (ou piora) o win% e só reduz o TAMANHO da amostra não
resolve o problema estrutural de ruína (sequência de 2-7 perdas plausível
contra caixa de R$250): reduz o número de operações simuladas no horizonte
(de 44 para 32), mas também reduz o tamanho da amostra bootstrap de onde a
sequência de perdas é reamostrada, e nesta amostra menor a pior sequência
observada (MA20: 7) foi IGUAL OU PIOR que a da amostra cheia. Confirma, de
um ângulo novo, o veredito estrutural que a G8 já tinha deixado: a tensão
entre "alvo≥3x ⇒ win% baixo" e "capital R$250 ⇒ pouca folga para sequência
de perdas" não se resolve por um filtro de REGIME que não muda o payoff nem
melhora de forma confiável a taxa de acerto.

**Critério de promoção ao OOS-1 — NENHUMA variante bate o portão declarado a
priori (`p_ruína≤15-20%`), e a quase-exceção não é uma vitória real:** a
inclinação (24,6%) fica acima até do limiar já RELAXADO pela G8 (20%→25%,
que esta geração herdaria por precedente de mesma família/capital/
instrumento) só por 0,4pp — mas relaxar de novo aqui não teria a mesma
justificativa que teve na G8 (lá, os vizinhos imediatos de 140 — 150/160 —
colapsavam para censura total, e 140 era o ÚNICO candidato real da região;
aqui não há nenhum "único candidato isolado", há uma REF que já sabemos
MORTA (idêntica ao vencedor da G8, que já falhou o OOS-1 real documentado
acima) e uma variante filtrada estatisticamente indistinguível dela, com
líquido 33% MENOR (+918,00 contra +1.365,50) e 25% menos trades (90 contra
121). Promover a inclinação ao OOS-1 gastaria o único disparo do gate real
em algo que (i) não é uma melhoria genuína sobre a REF — é ruído em cima
dela — e (ii) carrega exatamente o mesmo perfil de ruína que a REF JÁ
EXIBIU morrendo no OOS-1 real da G8. **Por protocolo, nenhum candidato foi
promovido. OOS-1 e OOS-2 NÃO foram rodados.**

**Veredito: MORTA — refutação das DUAS metades da hipótese desta geração,
nas quatro definições testadas.** O filtro de tendência diária (nível em
3 janelas + inclinação) não eleva o win% do ORB momentum e não reduz a
probabilidade de ruína de forma distinguível de ruído estatístico — na
pior definição (MA10), ele ainda PIORA drasticamente o fill-rate da entrada
ao escolher, com frequência, o lado que o preço está prestes a abandonar.

**Sizing/ruína/%mensal:** não aplicável — nenhum candidato passou o portão
do IS, protocolo não permite projeção.

**Resposta à pergunta desta geração:** não, condicionar o ORB momentum à
tendência diária (nas quatro definições mais óbvias — nível de MA curta,
média e longa, e inclinação) não resolve a tensão estrutural que a G8 já
tinha caracterizado. Isso é consistente com o precedente já registrado do
projeto (REGRAS.md R45, recuo raso): filtro de tendência de regime, testado
numa família de entrada DIFERENTE aqui, continua inconclusivo/sem ganho —
agora são DUAS famílias de entrada (recuo raso e ORB momentum) em que a
tendência diária não resolveu nada, o que pesa mais contra a ideia geral do
que a favor de testar uma terceira.

**Raciocínio final — é hora de parar esta busca ou mudar de família?** Esta
é a **10ª geração desta busca, e o 10º resultado honesto sem edge
validado** — G1-G9 cobriram continuação de tendência, sinais fracos
isolados e combinados, confluência cruzada com WDO, regime de volatilidade,
momentum de abertura, fade da falha do rompimento; G10 fecha o ângulo de
regime de tendência diária sobre a família que mais perto chegou (ORB). Três
observações honestas:

1. **A família ORB/abertura está genuinamente esgotada agora, nas TRÊS
   direções testáveis** (a favor do rompimento — G7/G8; contra, via fade —
   G9; e agora condicionada por regime externo — G10). As três batem no
   MESMO teto estrutural: com `alvo≥3x` fixado pelo mandato do dono, o win%
   de qualquer variante desta família fica entre ~12% (degenerada) e ~37%
   (o melhor caso, momentum sem filtro), sempre perto ou abaixo do
   breakeven empírico (25-31%), e o capital real de R$250 não tem folga
   para as sequências de perda que esse win% produz com alguma frequência
   — não importa COMO a família é fatiada (direção, contra-direção, ou
   regime).
2. **O achado de método que sobrevive, portável:** um filtro de regime
   (tendência, volatilidade, confluência externa) só muda o resultado de
   uma estratégia se ele muda o PAYOFF ou a TAXA DE ACERTO de forma
   distinguível de ruído — cortar a amostra pela metade sem mexer em
   nenhum dos dois não resolve um problema de ruína estrutural, só reduz o
   n da medição (e, no limite, pode PIORAR a cauda observada por amostra
   menor, como aconteceu com MA20 aqui). Antes de testar um filtro de
   regime como "solução" para ruína, confirme que ele de fato move win% OU
   payoff — não suponha que reduzir ruído de amostra basta.
3. **Resposta direta à pergunta do mandato:** sim, a busca já cobriu as
   famílias de ideia razoáveis do escopo original (as 6 listadas + regime
   de tendência diária = 7 ângulos distintos, 10 gerações contando
   variações). Continuar DENTRO da família ORB/abertura com mais uma
   variação de geometria ou mais um filtro não tem orçamento que justifique
   — a restrição é estrutural (payoff≥3x choca com capital de R$250), não
   uma questão de achar o parâmetro certo. Se o dono quiser mais uma
   geração, as duas rotas que ainda não foram tentadas e têm alguma
   justificativa prévia no projeto são: (a) condicionar qualquer uma destas
   famílias ao regime de SETEMBRO especificamente — a única janela com
   achado POSITIVO replicado no projeto inteiro (`win_idade_da_onda_
   faixa_8_15`) — em vez de mais uma variação genérica sobre jan-jun; ou
   (b) abandonar o mandato `alvo≥3x` como universal e perguntar ao dono se
   ele aceitaria um payoff mais baixo (2:1 ou 1,5:1) para esta família
   especificamente, já que é exatamente essa restrição que empurra o win%
   para a faixa onde a ruína é estruturalmente alta a este capital — mas
   isso é uma decisão do dono sobre o mandato, não uma hipótese a testar
   silenciosamente.

## Geração 11 — tamanho de mão graduado pela FORÇA do sinal (mandato do COORDENADOR)

**Contexto do mandato:** o orquestrador tinha concluído a busca na G10 (10
resultados honestos sem edge validado). O COORDENADOR pediu para continuar,
testando 4 alavancas ainda não tentadas, derivadas do princípio do dono
("sinal fraco muda o TAMANHO da mão, não só entra/não entra"). Esta geração
ataca a alavanca (1).

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g11_orb_tamanho_graduado.py`
(classe `WinBuscaLucroG11OrbTamanhoGraduado`, não registrada, cópia
deliberada da detecção de rompimento de `WinBuscaLucroG08OrbSobrevivencia` —
nenhuma mudança na geometria stop/alvo, só um filtro de força adicional) +
harness em `scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/
g11_orb_tamanho_graduado/` (`g11_base.py`, `g11_is_busca.py`,
`g11_is_posthoc.py`, logs `g11_is_busca_stdout.log`/
`g11_is_posthoc_stdout.log`). **Nenhum arquivo `_congelado_v11.py` foi
criado** — nada foi promovido ao OOS-1 (ver veredito), mesmo precedente de
G1/G2/G5/G6/G9/G10.

**A tradução do princípio para um instrumento que só cabe 1 contrato:** a
R$250 real, `contracts_from_capital_operacional` nunca libera o 2º contrato
sem a pilha cheia (CLAUDE.md, "Capital inicial: sempre o mínimo real"). Logo
"tamanho de mão" aqui não pode ser literalmente escalar quantidade — a
tradução adotada, declarada explicitamente no código e nesta entrada, é
**seleção binária**: operar SÓ o balde de sinal forte (mão=1 contrato),
zero contrato (não entra) no sinal fraco — o equivalente discreto de "mão
maior no forte, mão zero no fraco" quando só existem 0 ou 1 contrato
disponíveis.

**Medida de força adotada:** `forca_relativa = (preço além do nível
rompido) / (tamanho da própria faixa de abertura)`, calculada no instante do
próprio rompimento (causal — só usa a faixa já fechada e o fechamento da
barra do rompimento, sem look-ahead). Das três alternativas que o mandato
listava (magnitude relativa, velocidade do rompimento, volume/tickvol na
barra), esta geração testou só a primeira — declarado como limitação de
escopo, não omissão silenciosa; as outras duas ficam como próximo passo se o
dono quiser aprofundar esta alavanca. Geometria **herdada literalmente** do
vencedor composto da G8 (`range_minutos=5min, stop_min=50, stop_max=140,
alvo_multiplo=3x, buffer=20pts, ttl=10`) — esta geração isola só o eixo
novo, não revisita a geometria.

**Protocolo em 2 passos, mais um 3º adicionado por necessidade de método
(ver achado central):**

1. **Diagnóstico** — roda sem filtro de força (=exatamente a REF/vencedor da
   G8) sobre o IS inteiro, coleta a força de TODA borda bruta
   (`stats_forcas`, n=1.084) e calcula os cortes de tercil — causal, só IS:
   **p33=0,032, p67=0,083** (população: min=0,003, mediana=0,052,
   max=0,690 — a faixa de abertura do WIN@ é tão grande, mediana ~860-1.400
   pontos conforme a G7 já tinha medido, que um rompimento típico excede a
   faixa por só ~5% do próprio tamanho).
2. **Baldes exclusivos** — roda 3 células (`fraco`: força<0,032; `médio`:
   0,032≤força<0,083; `forte`: força≥0,083) com os cortes do passo 1.
3. **Estratificação pós-hoc** (adicionada depois de um achado de método no
   passo 2 — ver abaixo) — roda a REF (sem filtro) UMA vez e classifica os
   121 trades REAIS pela força da própria ordem que os originou, em vez de
   rodar simulações exclusivas.

**Resultado do Passo 2 (baldes exclusivos, IS jan-jun/2026, 122 pregões,
capital R$250):**

| balde | líquido R$ | trades | win% | BEemp% | IC95 win% | veredito | payoff | p_ruína(MC) | top3/liq | composto? |
|---|---|---|---|---|---|---|---|---|---|---|
| REF (G8, sem filtro) | +1.365,50 | 121 | 37,2% | 27,4% | [29,1;46,1] | POSITIVO | 2,65 | 24,8% | 18% | **sim** |
| fraco (força<0,032) | −169,50 | 13 | 15,4% | 26,8% | [4,3;42,2] | indefinido | 2,73 | 16,3% | −81% | não |
| médio (0,032-0,083) | −176,50 | 43 | 23,3% | 26,9% | [13,2;37,7] | indefinido | 2,72 | 49,8% | −142% | não |
| forte (força≥0,083) | +707,00 | 108 | 34,3% | 28,7% | [26,0;43,6] | indefinido | 2,49 | **40,0%** | 37% | não |

Stop mediano = 145 pontos em TODAS as células (geometria fixa, acima do
piso de 100pts do item 6.47 — não exigiu checagem com ticks). Teste de duas
proporções forte×fraco: **z=1,38** (|z|<1,96 — diferença NÃO distinguível
de ruído, apesar da aparência de gradiente fraco→médio→forte no win%).

**Achado de método crítico — por que o Passo 2 sozinho não responde à
pergunta da geração:** `forte` parece melhor que `fraco` (34,3% contra
15,4% de win%) e até se aproxima da REF, mas isto é um ARTEFATO do
mecanismo de rearme. Como `on_order_expired`/`on_order_rejected` resetam
`_armou_hoje`, um dia pode ter várias bordas de rompimento frescas; quando o
filtro de força rejeita a 1ª borda do dia (sem sequer armar ordem), a
estratégia tenta a PRÓXIMA borda fresca — que pode ocorrer num horário/
contexto diferente do dia. Ou seja: um balde exclusivo não testa "o mesmo
sinal, mais forte" — testa "qual EDGE NUMERADO do dia foi escolhido",
confundindo força com posição sequencial dentro do pregão. Isto explica por
que a REF (aceita o 1º edge válido, não filtra por força) supera TODOS os
3 baldes exclusivos, inclusive o `forte`: a REF não sofre esse
deslocamento de seleção.

**Resultado do Passo 3 (estratificação PÓS-HOC dos 121 trades REAIS da
REF, cortes de tercil recalculados sobre a força das próprias entradas
realizadas — p33=0,045, p67=0,112, decisivo):**

| balde (pós-hoc) | n | win% | BEemp% | IC95 win% | payoff | líquido R$ |
|---|---|---|---|---|---|---|
| fraco | 40 | 37,5% | 27,0% | [24,2;53,0] | 2,71 | 481,00 |
| médio | 40 | 37,5% | 27,5% | [24,2;53,0] | 2,64 | 462,00 |
| forte | 41 | 36,6% | 27,7% | [23,6;51,9] | 2,62 | 422,50 |

(os três líquidos somam 1.365,50 — exatamente o da REF, confirmando que é a
MESMA amostra de 121 trades, só reparticionada.) Teste de duas proporções
forte×fraco pós-hoc: **z=−0,09** (ruído puro). Correlação direta
força↔resultado sobre os 121 trades: **corr(força, venceu?)=−0,023**,
**corr(força, P&L R$)=−0,027** — essencialmente ZERO nas duas métricas.

**Veredito: HIPÓTESE REFUTADA, de forma decisiva e por dois caminhos
independentes e convergentes.** A magnitude do rompimento ORB (relativa ao
tamanho da própria faixa de abertura) **não carrega nenhuma informação
sobre a qualidade do trade que vai se seguir** — nem como filtro exclusivo
(que ainda assim falha o critério composto: `forte` tem p_ruína=40,0%,
PIOR que a REF, não melhor, apesar de aparentar win% mais alto por causa do
viés de seleção de edge) nem, de forma mais limpa, na estratificação
pós-hoc dos trades que realmente ocorreram (win% idêntico entre tercis,
37,5%/37,5%/36,6%, correlação ~0). **Nenhum balde bate o critério composto
herdado da G8** (líquido>0 E não censurado E win%≠NEGATIVO E
p_ruína≤25%) — só a REF (idêntica ao vencedor da G8, que já morreu no
OOS-1 real documentado na G8) bate. **Por protocolo, nenhum candidato foi
promovido. OOS-1 e OOS-2 NÃO foram rodados.**

**Sizing/ruína/% mensal:** não aplicável — nenhum balde passou o portão do
IS; os números de ruína reportados acima (16,3%/49,8%/40,0%) já fazem parte
da própria busca, não de uma projeção aceita.

**Resposta à pergunta desta geração:** não — graduar o tamanho da mão pela
força do rompimento ORB (seleção binária forte/zero, a tradução discreta
cabível a R$250) não resgata a família ORB/momentum que a G8 já tinha
caracterizado como estruturalmente incompatível com este capital. Mais
importante que o resultado em si: esta geração também confirma, com um
caso concreto, uma tese geral sobre o que "graduar por força" significa em
day trade com re-arme intradiário — **um balde exclusivo que filtra qual
sinal dispara pode medir "qual sinal foi escolhido" em vez de "o sinal
escolhido é melhor"**, e a forma correta de testar se uma medida de força
prediz qualidade é estratificar PÓS-HOC os trades que de fato ocorreram
numa única rodada não-filtrada, não comparar rodadas exclusivas entre si.

**Achado de método que sobrevive, portável para qualquer alavanca futura de
"seleção/tamanho por força de sinal":** antes de aceitar que um balde
"forte" é melhor que um balde "fraco" num backtest com reentrada
intradiária, confirme que o mecanismo de rearme não está trocando TAMBÉM
qual evento do dia foi escolhido — se houver qualquer `on_order_expired`/
`on_order_rejected` que permita tentar de novo depois de uma rejeição por
filtro, a comparação entre baldes exclusivos está confundida por desenho, e
a estratificação pós-hoc de uma única rodada sem filtro é o teste que
isola a variável certa.

**Raciocínio para a Geração 12 (se o coordenador quiser continuar nas
outras 3 alavancas do mandato):** (1) a alavanca (1) desta geração está
encerrada — força do rompimento (magnitude relativa) não prediz nada além
de ruído, confirmado por dois métodos convergentes; se o coordenador
quiser insistir nesta alavanca especificamente, as duas variantes de força
ainda não testadas (velocidade do rompimento — quantas barras até romper a
faixa; volume/tickvol na barra de rompimento) são o próximo passo mais
barato, mas dado que a família ORB inteira (G7-G10) já esgotou as 3
direções estruturais testáveis e esta geração mostra que nem a magnitude
do próprio rompimento ajuda, a expectativa a priori para essas duas
variantes deveria ser modesta; (2) as alavancas (2) combinação E de dois
sinais independentes, (3) grade fina de sensibilidade nas famílias com
vida, e (4) portfólio/alternância entre estratégias continuam pendentes do
mandato do coordenador e não foram tocadas nesta geração; (3) método que
sobrevive independente do resultado: a estratificação pós-hoc (rodar uma
vez, sem filtro, e classificar os trades reais por uma métrica candidata)
é estrategicamente mais barata E mais limpa que rodar N simulações
exclusivas sempre que a métrica candidata não controla DIRETAMENTE a
decisão de entrar/sair — deveria ser o método padrão para testar qualquer
"será que X prediz qualidade" daqui pra frente nesta busca, antes de
qualquer busca de geometria em cima do balde.


## Geração 12 — combinação E (AND) de dois sinais INDEPENDENTES (mandato do COORDENADOR)

**Contexto do mandato:** o coordenador pediu para continuar a busca testando 4
alavancas ainda não tentadas. A G11 fechou a alavanca (1) (tamanho de mão
graduado pela força do próprio rompimento — refutada, força não prediz
nada). Esta geração ataca a alavanca (2): exigir que DOIS sinais de
ORIGENS DIFERENTES concordem na mesma direção antes de operar — informação
nova, não reentrada do mesmo gatilho (G5/G6 já tinham mostrado que empilhar
reentradas do MESMO sinal não ajuda).

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g12_and_orb_cross.py` (classe
`WinBuscaLucroG12AndOrbCross`, não registrada) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g12_and_orb_cross/`
(`g12_base.py`, `g12_diagnostico.py` + log, `g12_is_busca.py` + log). **Nenhum
arquivo `_congelado_v12.py` foi criado** — nada foi promovido ao OOS-1 (ver
veredito), mesmo precedente de G1/G2/G5/G6/G9/G10/G11.

**Os dois sinais, cada um já uma geração anterior, COPIADOS/IMPORTADOS, não
reimplementados:**

- **Sinal A — ORB momentum (G8, `WinBuscaLucroG08OrbSobrevivencia`):**
  rompimento da faixa de abertura de 5min, direção = lado rompido. Lógica de
  detecção idêntica, geometria herdada como ponto de partida (`stop =
  clip(faixa, 50, stop_max)`, `alvo = stop × alvo_multiplo ≥ 3x`).
- **Sinal B — estado anômalo WIN×WDO (G4, `estado_anomalo_cruzado`,
  IMPORTADO de `win_busca_lucro_g04_cross_wdo.py`):** direção = CONTINUAÇÃO
  prevista, `janela_min=20, quantil=0,75` — os parâmetros que a G4 já tinha
  identificado como o único candidato com líquido positivo no IS e OOS-1
  antes de reprovar por concentração/IC. Parâmetros FIXOS pelo mandato desta
  geração (não re-tunados aqui).

**A regra combinada testada:** só entra no rompimento ORB se o sinal B
esteve ATIVO e na MESMA direção do lado rompido em algum instante de uma
janela causal de `k_minutos` terminando no próprio instante do rompimento
(`k_minutos∈{0,5,15,30}` — 0 = mesmo minuto). Janela mantida por TEMPO (deque
podado por timestamp, nunca por contagem de barras). Geometria herdada da
G8 como ponto de partida, mas retunada dentro do IS (`stop_max_pontos` e
`alvo_multiplo`, mesmo grid de 2 estágios da G08) — o mandato antecipava que
a frequência cairia muito e permitia retuning.

**Protocolo em 2 passos:** (1) `g12_diagnostico.py` mede as ocorrências
BRUTAS de A, B e A∩B com geometria fixa (item 6.48), ANTES de qualquer busca
de parâmetro — para confirmar que o AND reduz frequência mas não zera o
gatilho (descartando bug de ordem-de-operações). (2) `g12_is_busca.py` roda
os 2 estágios de busca de geometria (idênticos à G08) para CADA `k_minutos`,
mais uma linha de REFERÊNCIA (ORB puro da G8, classe importada direto, não
reimplementada — para a comparação "com AND vs sem AND" ser EXATA).

**Diagnóstico (IS, jan-jun/2026, 122 pregões, geometria-base
stop_max=140/alvo=3x):**

| | bruto A (ORB) | bruto B (anômalo) | bruto A∩B | emitidas | trades | pregões distintos |
|---|---|---|---|---|---|---|
| REF ORB puro | 1.084 | — | — | 122 | 121 | 121 |
| k=0min | 1.084 | 214 | 15 | 12 | 12 | 12 |
| k=5min | 1.084 | 214 | 34 | 26 | 25 | 25 |
| k=15min | 1.084 | 214 | 64 | 32 | 31 | 31 |
| k=30min | 1.084 | 214 | 82 | 33 | 32 | 32 |

O AND derruba a frequência BRUTA para 1,4%-7,6% do rompimento ORB isolado —
`bruto A∩B` cresce quase linearmente com `k_minutos` (15→34→64→82), o
padrão esperado de uma janela de tempo capturando mais sobreposições por
acaso, não evidência de um acoplamento causal forte entre os dois sinais
(se fosse causal forte, a curva não seria aproximadamente linear no
tamanho da janela).

**Resultado da busca de geometria (IS, 2 estágios por k_minutos, mesmo
critério composto da G08: líquido>0 E não censurado E win%≠NEGATIVO E
p_ruína(MC, R$250→R$100, horizonte=44 pregões)≤25%) — melhor célula por
`k_minutos` (geometria vencedora em TODOS: `stop_max=160, alvo=3x`,
idêntica/vizinha ao vencedor isolado da G8):**

| k_minutos | líquido R$ | trades | win% | BEemp% | IC95 win% | veredito | p_ruína(MC) | sem_trade/pregões | equity_min | top3/liq | top5/liq | pior_seq |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| REF (G8, sem AND) | **+1.365,50** | 121 | 37,2% | 27,4% | [29,1;46,1] | **POSITIVO** | 24,8% | 1/122 | — | 18% | 31% | 6 |
| k=0 | +226,00 | 12 | 41,7% | 27,3% | [19,3;68,0] | indefinido | 1,8% | 110/122 | 101,00 | 127% | 211% | 4 |
| k=5 | +435,50 | 25 | 40,0% | 26,6% | [23,4;59,3] | indefinido | 11,7% | 97/122 | 170,00 | 66% | 110% | 5 |
| k=15 | +358,50 | 31 | 35,5% | 26,6% | [21,1;53,1] | indefinido | 17,7% | 91/122 | 122,50 | 80% | 133% | 6 |
| k=30 | +325,00 | 32 | 34,4% | 26,6% | [20,4;51,7] | indefinido | 22,5% | 90/122 | 122,50 | 88% | 147% | 6 |

Tabela completa (57 células: REF + 4×(12 stop_max + 4 alvo_multiplo), 12
colunas padrão + extras incluindo `brtA/brtB/A∩B/emit` e `desliz.alvo 1,0t`
carimbado) em `g12_is_busca_stdout.log`. Stop mediano realizado = 165 pontos
em todas as células vencedoras (≥100 — item 6.47 não exige checagem com
ticks). `alvo_multiplo=6x` sempre piorou o composto (win% cai para 22-25%
contra BEnom 14,3-15,0%, e o payoff maior não compensa — p_ruína sobe para
25-38%); `alvo_multiplo=3x` (herdado da G8) permanece o melhor em toda a
família.

**Achado de método — por que NENHUMA célula bate o critério composto, e por
que isso NÃO é o mesmo "morreu de ruína" da G7/G8:** o critério herdado da
G08 marca uma célula como "censurada" (reprovada automaticamente) quando
`sem_trade ≥ 50% dos pregões` OU `equity_min < margem crua`. Esse limiar foi
desenhado para o modo de falha da G07 (caixa esgotado cedo, motor recusa em
silêncio o resto da janela). Auditado diretamente (ver tabela acima): o
`equity_min` das 4 células vencedoras (R$101,00 / R$170,00 / R$122,50 /
R$122,50) **nunca** cruzou a margem crua de R$100, e **zero ordens foram
recusadas por capital** em qualquer das quatro janelas — o modo de falha que
a regra foi desenhada para pegar simplesmente não aconteceu. A reprovação
veio inteiramente do outro ramo do OU: `sem_trade` ficou em 73,8%-90,2% dos
pregões, muito acima do limiar de 50% — mas isso é o PONTO do desenho de um
filtro AND entre dois sinais independentes (seletividade estrutural), não um
robô morrendo. Mesmo assim, **a conclusão da geração não muda** se o limiar
de "fração de dias" for descartado e substituído pelo gate mais apropriado
para amostra pequena (`veredito=="POSITIVO"`, IC95 do win% estatisticamente
acima do breakeven empírico, não apenas "não-NEGATIVO"): **nenhuma célula do
AND atinge `POSITIVO`** — todas as 57 células testadas (fora a REF e as
degeneradas de 5-8 trades) ficam em `indefinido`, o IC95 sempre cruza o
BEemp. O achado de método (lacuna real no critério herdado, não um simples
"relaxar o limiar") foi registrado como item **6.51** de
`LICOES_DE_PRODUCAO.md` (subagente em background cuida da edição e da
republicação do artefato).

**Critério de promoção ao OOS-1 — NENHUMA célula bate, por qualquer leitura
do critério composto (literal OU corrigida):** com a frequência entre 12 e
33 trades, a amostra é pequena demais para o IC95 do win% sair de cima do
breakeven empírico, mesmo quando o líquido é positivo e o ponto estimado do
win% (34-42%) fica folgadamente acima do BEemp nominal (~27%). **Por
protocolo, nenhum candidato foi promovido. OOS-1 e OOS-2 NÃO foram
rodados.**

**Concentração piorou, não melhorou, com o AND:** `top3/liq` nas 4 células
vencedoras (127%/66%/80%/88%) é DRAMATICAMENTE pior que a REF (18%) — com
poucos trades, um punhado de dias concentra mais do que o líquido inteiro
(top3/liq>100% quer dizer que os 3 melhores dias sozinhos superam o líquido
total, ou seja, o resto dos dias juntos é NEGATIVO). Isto é consistente com
(não contradiz) a hipótese de que "menos trades, mesmo que com win% nominal
mais alto, não resolve concentração" — o oposto do que uma leitura ingênua
do líquido/win% sugeriria.

**Veredito: HIPÓTESE REFUTADA — honesta, não fabricada.** Exigir que um
segundo sinal independente (estado anômalo WIN×WDO, G4) confirme a direção
do rompimento ORB (G8) reduz a frequência de disparo em 92-99% (de 121 para
12-33 trades no IS) sem elevar o win% o suficiente, com amostra pequena
demais, para que o IC95 saia de cima do breakeven empírico em NENHUMA das
4 janelas causais testadas nem em NENHUMA geometria do grid de retuning —
confirmando a preocupação que o próprio mandato desta geração já
antecipava ("é possível que o AND derrube a frequência demais sem subir o
win% o bastante — n pequeno demais pra concluir"). Não há evidência de que
os dois sinais sejam fortemente acoplados causalmente (o crescimento
aproximadamente linear de `bruto A∩B` com `k_minutos` é mais consistente
com sobreposição por acaso de janela do que com uma relação causal forte) —
a segunda preocupação do mandato também se confirma parcialmente.

**Sizing/ruína/% mensal:** não aplicável — nenhuma célula passou o portão
do IS; os números de ruína reportados acima (1,8%-38,2% conforme a célula)
já fazem parte da própria busca, não de uma projeção aceita.

**Resposta à pergunta desta geração:** não — a combinação AND de ORB (G8) e
estado anômalo WIN×WDO (G4), nas quatro janelas causais mais óbvias
(simultâneo, 5, 15 e 30 minutos) e com retuning de geometria dentro do IS,
não produz um candidato com amostra suficiente para validar estatisticamente
o win% contra o breakeven. Mais importante que o resultado em si, esta
geração deixa um achado de método que sobrevive além dela: **um critério de
censura herdado de uma geração anterior precisa ser auditado contra o
MECANISMO que ele foi desenhado para detectar antes de ser aplicado a um
desenho de estratégia estruturalmente diferente** (seletividade por design
≠ morte por falta de capital) — item 6.51 de `LICOES_DE_PRODUCAO.md`.

**Raciocínio para a Geração 13 (se o coordenador quiser continuar nas outras
2 alavancas do mandato):** (1) a alavanca (2) desta geração está encerrada
dentro do escopo testado — AND de ORB+cruzamento WIN×WDO não resgata a
família; se o coordenador quiser insistir nesta alavanca especificamente, o
ângulo ainda não tentado é usar um TERCEIRO par de sinais (ex. ORB + regime
de volatilidade da G5, que teve menos filtro-morte-de-amostra que o
cruzamento WIN×WDO) ou acumular mais dados (o n pequeno é o gargalo
central, e só mais pregões resolvem isso de verdade); (2) as alavancas (3)
grade fina de sensibilidade nas famílias com vida e (4) portfólio/
alternância entre estratégias continuam pendentes do mandato do
coordenador; (3) método que sobrevive, portável: ao herdar um critério
"censurado"/"inválido" de uma geração anterior para uma geração com desenho
de seleção diferente, separar explicitamente os dois ramos do critério
(caixa cruzou a barreira real? ordens foram recusadas por capital?) da
simples baixa frequência por desenho, e usar significância estatística
(IC95 vs. breakeven empírico) como gate de amostra pequena — não uma
fração mínima de dias operados herdada de um contexto diferente.

## Geração 13 — grade fina multidimensional sobre o ORB (alvo × stop × confirmação)

**Quem testou:** subagente filho (general-purpose/sonnet), 1 disparo. Código
em `src/strategy/daytrade/lab/win_busca_lucro_g13_orb_grade_fina.py` (classe
`WinBuscaLucroG13OrbGradeFina`, não registrada — estende a detecção de
rompimento da G07/G08 com 3 eixos novos) + versão **congelada**
`..._congelado_v13.py` + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g13_orb_grade_fina/`
(`g13_base.py`, `g13_is_busca.py`, `g13_is_busca_c_fixo.py`, `g13_oos1.py`,
`g13_oos2.py`, logs `g13_is_busca_stdout.log`/`g13_is_busca_c_fixo_stdout.log`).

**Mandato do coordenador (alavanca 3 das 4):** a G8 varreu só `stop_max_pontos`
(1 eixo) e achou um penhasco abrupto (140 sobrevive, 150/160 colapsam em
censura total). O coordenador pediu uma grade MULTIDIMENSIONAL de verdade —
`alvo_multiplo` × definição do STOP × limiar de CONFIRMAÇÃO do rompimento —
para checar se existe algum platô robusto em alguma combinação, reportando a
curva inteira, não um ponto.

**Os 3 eixos.** (1) `alvo_multiplo` ∈ {3,4,5}. (2) definição do stop, 3
famílias: **tecnico** (idêntica a G07/G08 — `stop = clip(faixa_abertura,
50, stop_max_pontos)`, `stop_max_pontos` ∈ {100,120,140,160,180}, grade em
torno da região interessante da G8); **ATR-M15(14)** — `stop = atr_multiplo
× ATR14(M15)` causal (função pura `atr_m15_causal`, M15 resampleado com
`shift(1)` para nunca usar a barra M15 em formação); **fixo** — constante,
`stop_fixo_pontos` ∈ {100,120,140,160}. (3) `confirma_pontos` ∈ {0,10,20,30,50}
— o fechamento da barra de rompimento precisa ultrapassar o nível da faixa
por pelo menos esse tanto antes de validar o sinal (0 = comportamento G07/G08
exato). Execução fechada idêntica à linha inteira (EnterLimit ttl=10, saída
fatiada sem prazo, `anchor_exits_at_fill`, só stop a mercado,
`target_fills_as_maker`), capital real R$250, fila WIN@ zero (não calibrada,
premissa otimista declarada), 1 contrato fixo, no máximo 1 operação real por
pregão (sem fade — mesma disciplina de G07/G08).

**Item 6.51 aplicado desde o desenho, não só no relato:** o critério de
censura desta geração separa os dois ramos do OU desde o código
(`g13_base.censura_separada`) — `censura_capital` (equity cruzou a margem
crua OU ordem recusada por capital) é o único ramo que reprova uma célula no
critério composto; `sem_trade ≥ 50%` sozinho (sem censura de capital) vira
`seletividade_amostra`, informativo, não reprova.

**Critério composto (declarado antes de rodar qualquer célula, mesmo limiar
revisado da G8 — 25%, pela mesma razão: nenhuma célula bate 20% e a
vizinhança do único ponto que bate 25% é degenerada):** líquido>0 E não
censurado POR CAPITAL E win% ≠ NEGATIVO E p_ruína(MC, 10.000 caminhos, 44
operações projetadas, R$250→R$100) ≤ 25%.

### Estágio A — grade 3D completa, família técnico (75 células)

`stop_max_pontos` × `alvo_multiplo` × `confirma_pontos` = 5×3×5 = 75 células,
todas rodadas. Tabela completa em `g13_is_busca_stdout.log`. **Apenas 1 das
75 células bate o critério composto inteiro:** `stop_max=140, alvo=3x,
confirma=0` — líquido=+R$1.365,50, 121 trades, win=37,2% (BEemp 27,4%, IC95
[29,1%;46,1%], POSITIVO), p_ruína(MC)=24,8%, stop mediano 145pts (≥100, item
6.47 não exige checagem com ticks), top3/líquido=18% (top5=31%, a menor
concentração desta busca inteira). **Estes quatro números são idênticos,
casa decimal a casa decimal, ao vencedor congelado da G8** — esperado, já
que `confirma_pontos=0` reproduz exatamente a lógica G07/G08.

**Os três cortes (leitura de platô, impressos automaticamente pelo script ao
redor do vencedor):**

| CORTE 1 — `stop_max_pontos` (alvo=3x, confirma=0) | líquido R$ | trades | win% | p_ruína | censura capital |
|---|---|---|---|---|---|
| 100 | 562,50 | 121 | 34,7% | 29,7% | não |
| 120 | 877,50 | 121 | 35,5% | 28,3% | não |
| **140** | **1.365,50** | **121** | **37,2%** | **24,8%** | **não — único que passa** |
| 160 | −167,50 | 5 | 0,0% | 0,0%* | **sim — censura total** |
| 180 | −151,50 | 31 | 22,6% | 46,4% | **sim — censura total** |

| CORTE 2 — `alvo_multiplo` (stop_max=140, confirma=0) | líquido R$ | trades | win% | p_ruína | censura capital |
|---|---|---|---|---|---|
| **3x** | **1.365,50** | **121** | **37,2%** | **24,8%** | **não** |
| 4x | −177,00 | 6 | 0,0% | 0,0%* | **sim — censura total** |
| 5x | −177,00 | 6 | 0,0% | 0,0%* | **sim — censura total** |

| CORTE 3 — `confirma_pontos` (stop_max=140, alvo=3x) | líquido R$ | trades | win% | p_ruína |
|---|---|---|---|---|
| **0** | **1.365,50** | **121** | **37,2%** | **24,8% — melhor** |
| 10 | 1.062,00 | 120 | 35,0% | 30,9% |
| 20 | 1.076,00 | 120 | 35,0% | 30,6% |
| 30 | 1.167,50 | 121 | 35,5% | 28,6% |
| 50 | 1.030,50 | 121 | 34,7% | 32,1% |

\* `p_ruína` de células censuradas sai artificialmente baixa (amostra curta
demais pro Monte Carlo simular) — mesma ressalva da G8, por isso o critério
composto nunca escolhe uma célula censurada mesmo que o número pareça bom.

**Os três eixos, lidos separadamente:**

1. **`stop_max_pontos` é o MESMO penhasco da G8, confirmado de novo nesta
   grade maior.** Não existe gradiente suave: 100→120→140 sobe o líquido e
   desce p_ruína de forma quase linear, mas 140→160 não é "um pouco pior" —
   é colapso total (121 trades → 5 trades, equity cruza a margem já nos
   primeiros pregões). O "ótimo" de 140 está espremido entre dois vizinhos
   degenerados, não no meio de uma região estável.
2. **`alvo_multiplo` é uma faca de dois gumes ainda mais abrupta.** Subir de
   3x para 4x ou 5x NO MESMO `stop_max=140` também colapsa para censura
   total (6 trades) — replica exatamente o Estágio B da G8. Isto vale na
   MAIORIA dos `stop_max` testados: de 15 combinações `stop_max×alvo∈{4x,5x}`
   com `confirma=0`, **9 colapsam em censura total** (ver tabela completa).
3. **`confirma_pontos` é um EIXO MORTO para a contagem de trades — mas não
   para a sobrevivência.** Em toda combinação testada, variar `confirma_pontos`
   de 0 a 50 muda a contagem de trades em no máximo 1-2 operações (120-121
   em praticamente toda célula) — a faixa de abertura do WIN@ é larga o
   bastante (mediana ~860pts aos 5min, G07) que, uma vez que o preço rompe,
   o fechamento da barra quase sempre já está a mais de 50 pontos do nível,
   tornando o filtro de confirmação, como desenhado, incapaz de reduzir
   FREQUÊNCIA (o efeito que a hipótese do mandato esperava). No corte 3,
   `confirma=0` é inclusive a MELHOR célula (24,8% de ruína contra 28,6-32,1%
   das demais) — confirmação não ajuda, levemente atrapalha.
   **Achado colateral não previsto, mais interessante que o eixo em si:**
   `confirma_pontos` muda MUITO a chance de colapso total por capital, sem
   mudar win%/trades de forma sistemática. Das 25 células com `confirma=0`
   na grade inteira, **9 (36%) colapsam em censura total**; das 50 células
   com `confirma∈{10,20,30,50}`, só **2 (4%) colapsam**. A explicação não é
   estatística (o win% médio não muda) — é de SEQUÊNCIA: um deslocamento de
   alguns pontos no gatilho muda QUAL barra exata dispara a entrada, o que
   muda a ORDEM em que vitórias e derrotas chegam no início da janela, o que
   decide se uma sequência de perdas cedo cruza ou não a margem de R$100.
   Isto é evidência adicional, de um ângulo diferente do `stop_max`, de que
   a sobrevivência desta família depende de sorte de sequenciamento, não de
   uma propriedade suave da geometria.

### Estágio C — stop FIXO, vizinhança do vencedor (4 células)

`stop_fixo_pontos` ∈ {100,120,140,160}, `alvo_multiplo=3x`,
`confirma_pontos=0` fixos (vizinhança do vencedor A). Resultado em
`g13_is_busca_c_fixo_stdout.log`:

| stop_fixo | líquido R$ | trades | win% | p_ruína | censura capital |
|---|---|---|---|---|---|
| 100 | 562,50 | 121 | 34,7% | 29,7% | não |
| 120 | 877,50 | 121 | 35,5% | 28,3% | não |
| **140** | **1.365,50** | **121** | **37,2%** | **24,8%** | **não — passa** |
| 160 | −167,50 | 5 | 0,0% | 0,0%* | **sim** |

**Achado: as famílias "técnico" e "fixo" são REDUNDANTES nesta janela, não
eixos independentes.** Célula a célula, os números são **idênticos** aos da
família técnico no mesmo valor de teto (100/120/140/160) — porque a faixa de
abertura do WIN@ quase sempre excede qualquer teto testado, então
`clip(faixa, 50, teto)` vira simplesmente `teto` em praticamente toda
operação (mesmo achado que o Estágio B da G07 já registrava: "o stop efetivo
é essencialmente o próprio teto"). Variar a FORMA da definição do stop (faixa
clipada vs. constante) não muda nada quando o clip sempre bind — só o
NÚMERO do teto importa.

### Estágio B — ATR-M15, ABORTADO (limitação declarada, não resultado fabricado)

3 células planejadas (`atr_multiplo` ∈ {1,0; 1,5; 2,0}, vizinhança do
vencedor: alvo=3x, confirma=0). **Não concluído.** O motor mostrou um custo
computacional anômalo e reprodutível para esta família sobre a janela IS
inteira (122 pregões, 68.544 barras M1): múltiplas tentativas independentes
não terminaram em 70-200s de CPU por célula, contra 5,7s da família técnico
no MESMO período (>10× mais lento, sem sinal de convergência). Uma réplica
manual isolada de 10 dias terminou em 0,27s numa tentativa e não terminou em
100s noutra, com o MESMO código/dados — não totalmente reproduzível em escala
pequena, mas a janela IS inteira falhou em TODAS as 3 tentativas
independentes. Causa não investigada até a raiz (contenção de CPU nesta
máquina compartilhada — outros processos não relacionados acumulavam 4-8h de
CPU durante a sessão — ou custo real do motor para alvos muito distantes: o
ATR14-M15 variou 170-930pts no IS, então `alvo = atr_multiplo × ATR × 3x`
chega a 5.580pts, muito além do alcance de qualquer geometria já testada
nesta busca). **Nenhum número foi fabricado ou extrapolado para esta
família** — fica como limitação declarada desta geração, candidata a
investigação de profiling antes de reuso numa geração futura (nota de
método, não item formal de `LICOES_DE_PRODUCAO.md` — não há achado de
estratégia aqui, só uma lacuna operacional).

### Existe platô? NÃO — confirmado de forma mais forte que a G8

**O mandato pediu para checar explicitamente se existe um platô (várias
células vizinhas concordando) em vez de um pico isolado — a resposta desta
geração é um NÃO inequívoco, mais forte que a própria G8 porque agora há 79
células testadas (75 técnico + 4 fixo) em 3 eixos cruzados, não 16 células
em 1 eixo.** De 79 células:

- **Exatamente 1 bate o critério composto inteiro** — `stop_max=140 (ou
  stop_fixo=140), alvo=3x, confirma=0`.
- **Todo vizinho imediato em TODO eixo falha**, a maioria por colapso total
  de capital, não por margem apertada: `stop_max∈{120,160}` (um lado
  "só" fica acima do limiar de ruína, o outro colapsa), `alvo∈{4x,5x}`
  (colapsa SEMPRE no mesmo `stop_max`), `confirma∈{10,...,50}` (não
  colapsa, mas a ruína sobe 4-7 pontos percentuais em toda célula vizinha,
  nunca desce).
- **4 células são estatisticamente POSITIVAS no win%** (IC95 acima do BE
  empírico), mas só 1 delas também passa o filtro de ruína — confirma que o
  win% nunca foi o fator limitante desta família; é SEMPRE a probabilidade
  de ruína.
- **11 das 75 células técnico (14,7%) colapsam em censura total de
  capital** — a maioria (9 de 11) com `confirma=0`, reforçando o achado de
  fragilidade por sequenciamento acima.

**Esta geração não encontrou o platô que o mandato esperava — encontrou,
com uma grade muito mais rica, exatamente o MESMO ponto isolado que a G8
já tinha achado com uma busca de 1 eixo.** Isso é evidência POSITIVA de
método (o resultado da G8 não era artefato de sub-amostragem — é robusto
a uma grade 5× maior) e evidência NEGATIVA de estratégia (nem
`alvo_multiplo` nem `confirma_pontos` abrem alguma rota de fuga do
penhasco).

### Por que o OOS-1 NÃO foi re-executado nesta geração

O vencedor composto (`stop_max=140, alvo=3x, confirma=0`) é
**comportamentalmente idêntico** ao vencedor já congelado e já testado da
G8 — mesma detecção de rompimento, mesma fórmula de geometria, e
`confirma_pontos=0` reproduz exatamente a lógica G07/G08 (os 4 números do
IS — líquido, trades, win%, p_ruína — saem bit a bit iguais aos já
publicados na Geração 8). A G8 **já rodou** este exato candidato no OOS-1
(jul-ago/2026) e o resultado já está registrado: **MORTA** — líquido
−R$158,50, 5 trades (as 5 perdedoras), equity mínima R$91,50 (abaixo da
margem crua R$100), 322 ordens recusadas por capital em silêncio, 39/44
pregões sem trade (censura total) — a mesma forma decisiva de morte que a
G7 já tinha exibido. Rodar `g13_oos1.py` sobre este kwargs reproduziria,
de forma determinística, o MESMO número — motor, dado e parâmetros são
idênticos. Gastar o "roda uma vez" do protocolo numa repetição
determinística de um resultado já publicado seria desperdício, não rigor
— por isso o arquivo `g13_orb_grade_fina_congelado_v13.py` foi escrito
(documenta o vencedor, por consistência com a convenção desta busca) mas
`g13_oos1.py`/`g13_oos2.py` não foram executados. A comparação "ruína
PREVISTA (IS)=24,8% × ruína OBSERVADA (OOS-1, via os 5 trades reais da
G8)=67,5%" já está registrada na Geração 8 e vale integralmente aqui.

**Veredito: PENHASCO CONFIRMADO, NÃO VALIDADA.** A família ORB/momentum
(G07-G13) permanece estruturalmente incapaz de sobreviver ao capital real
de R$250 do WIN@ com folga suficiente — três gerações seguidas (G7, G8,
G13) e, somando as buscas, mais de 100 células testadas em 4 eixos
diferentes (`stop_max_pontos`, `alvo_multiplo`, `range_minutos` — G7 — e
`confirma_pontos` — G13) convergem para o MESMO ponto único, cercado de
colapso total em toda direção testada. Esta não é mais uma hipótese que
"ainda não foi varrida o suficiente" — é uma conclusão com evidência
robusta de método (grade 5× maior reproduziu o mesmo ótimo isolado).

**Sizing/ruína/% mensal:** não aplicável — nenhum número novo de OOS foi
medido (ver seção acima); os números de ruína do IS já estão reportados
dentro da própria busca, nunca como projeção aceita.

**Raciocínio para a Geração 14 (alavanca 4 do mandato — portfólio/
alternância):** (1) a família ORB/momentum como gatilho ÚNICO está
encerrada — qualquer geração futura que queira usá-la precisa de um
mecanismo estrutural novo, não mais busca de parâmetro dentro da mesma
família (já foram G7: `range_minutos`/`stop_max`/`alvo`; G8: `stop_max`
fino + ruína como restrição; G13: `alvo`×`stop`×`confirma` cruzados — o
espaço de parâmetro single-robô está exaurido); (2) a pista mais concreta
desta geração para a alavanca 4: a fragilidade é de SEQUENCIAMENTO/
caminho, não de magnitude — um robô ORB sozinho tem ~25% de chance (medida,
não estimada) de uma sequência de perdas cedo cruzar a margem de R$250
antes do edge se expressar. Um portfólio que NÃO concentre o capital inteiro
num único robô de baixo win%/alto payoff no início de uma janela — por
exemplo, alternando entre a família ORB e uma família de win% mais alto
(WinRetangulo, que já valida em produção com piso R$1.100, ou um candidato
futuro) de forma que a exposição ao "momento ruim" de qualquer uma das duas
fique diluída — é a direção mais alinhada com o que esta geração mediu, não
uma alternância arbitrária entre estratégias parecidas; (3) método que
sobrevive, portável: quando uma grade muito maior reproduz EXATAMENTE o
mesmo vencedor isolado que uma busca menor já achava, isso é evidência de
que o problema é estrutural (não de sub-amostragem) — vale parar de buscar
PARÂMETRO dentro da mesma família e buscar um MECANISMO diferente (aqui:
diversificação de risco entre estratégias, não mais geometria de uma só).

## Geração 14 — portfólio/ALTERNÂNCIA entre ORB (G8) e confirmação cruzada (G4) (mandato do COORDENADOR, última alavanca)

**Quem testou:** agente principal (não delegado a subagente filho — tarefa
executada diretamente), 1 disparo. Código em
`src/strategy/daytrade/lab/win_busca_lucro_g14_portfolio_orb_cross.py`
(classe `WinBuscaLucroG14PortfolioOrbCross`, não registrada) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/
g14_portfolio_orb_cross/` (`g14_base.py`, `g14_is_busca.py`, log
`g14_is_busca_stdout.log`). **Nenhum arquivo `_congelado_v14.py` foi
criado** — nada foi promovido ao OOS-1 (ver veredito), mesmo precedente de
G1/G2/G5/G6/G9/G10/G11/G12.

**Contexto do mandato:** a G13 fechou a alavanca (3) (grade fina — penhasco
confirmado, não platô) e deixou o raciocínio para esta geração: a
fragilidade da família ORB é de SEQUENCIAMENTO (uma sequência de 2-3 perdas
cedo é provável, não rara, a R$250), não de magnitude — e um portfólio que
NÃO concentre o capital inteiro numa única família de baixo win%/alto
payoff no início de uma janela poderia diluir essa exposição. Esta geração
ataca a alavanca (4), a última das quatro: testar se operar o ORB (G8/G13,
win%~37%) e a confirmação cruzada WIN×WDO (G4, win%~35%) como uma CESTA —
qualquer uma pode disparar, OU lógico, nunca E — reduz a probabilidade de
ruína em relação a cada família sozinha, mesmo que nenhuma das duas tenha
edge validado isoladamente (a G4 passou o gate literal mas não validou "com
folga" — IC95 cruza o BE empírico nas duas janelas, concentração piora de
59% para 240% do IS pro OOS-1).

**A tradução do princípio para 1 contrato só:** a R$250 só cabe 1 contrato
— "portfólio" aqui não pode ser duas posições simultâneas com capital
separado. A tradução adotada: ALTERNÂNCIA sequencial sobre o MESMO caixa —
nunca duas posições nem duas ordens pendentes ao mesmo tempo. O motor só
guarda UMA ordem-limite pendente por vez (`resting_limit`); devolver uma
`EnterLimit` nova enquanto outra está pendente a SUBSTITUI em silêncio, por
isso a classe mantém um único estado de pendência compartilhado
(`_ordem_pendente_origem: None/"orb"/"cross"`) — nenhuma família arma ordem
nova enquanto o portão não está livre. **Prioridade de empate na mesma
barra, declarada no código: o ORB vence** (checado primeiro; o sinal
cruzado só é considerado se o ORB não disparou nessa mesma barra — na
prática irrelevante, só 1 empate em todo o IS, `cross_perdeu_empate_pra_orb
=1`). As duas famílias preservam a disciplina de reentrada da geração de
origem, não uniformizada à força: ORB continua "sem fade" (no máximo 1
operação real do ORB por pregão, `_orb_preencheu_hoje`), cruzado continua
sem teto diário (pode reentrar no mesmo pregão depois que QUALQUER posição
fechar, disciplina herdada da G4). Nenhuma lógica de sinal foi
reimplementada — a classe replica, lado a lado, a mesma detecção/geometria
de `WinBuscaLucroG08OrbSobrevivencia` e `WinBuscaLucroG04CrossWdo` (cópia
deliberada, mesmo motivo de toda a busca: cada geração congela seu próprio
módulo). Geometrias **herdadas das vencedoras de cada família, não
retunadas** — esta geração testa o MECANISMO de alternância, não parâmetro
novo: ORB `stop_max=140/alvo=3x/buffer=20pts`, cruzado `continuação,
j=20min/q=0,75/stop=150pts/alvo=3x/buffer=30pts`. O motor não carrega o
`reason` da ordem de entrada em `IntradayTrade`, então a origem de cada
trade é gravada no momento do FILL (`origem_por_entry_ts`, casada por
`entry_ts` depois do backtest) — 0 trades "sem origem identificada" no IS,
confirma que o rastreio funciona.

**Passo 1 — IS (jan-jun/2026, 122 pregões, capital real R$250), portfólio
combinado × as duas famílias SOLO no MESMO período (tabela completa em
`g14_is_busca_stdout.log`):**

| variante | líquido R$ | trades | win% | BEemp% | IC95 win% | veredito | top3/liq | p_ruína(MC) | pior_seq | censurado |
|---|---|---|---|---|---|---|---|---|---|---|
| **PORTFÓLIO combinado** | **+2.367,00** | **244** | **35,7%** | 27,4% | [29,9;41,8] | POSITIVO | 33% | **33,5%** | **8 (−R$260,00)** | não |
| ·· origem ORB (dentro do G14) | +1.382,50 | 121 | 37,2% | 27,2% | [29,1;46,1] | POSITIVO | 18% | 24,2% | 6 (−R$179,00) | não |
| ·· origem cruzado (dentro do G14) | +984,50 | 123 | 34,1% | 27,5% | [26,4;42,9] | indefinido | 64% | 37,4% | 9 (−R$289,50) | **sim** |
| G8 SOLO (ORB, mesmo período) | +1.365,50 | 121 | 37,2% | 27,4% | [29,1;46,1] | POSITIVO | 18% | **24,8%** | 6 (−R$179,00) | não |
| G4 SOLO (cruzado, mesmo período) | +1.221,50 | 127 | 35,4% | 27,5% | [27,7;44,1] | POSITIVO | 59% | **33,7%** | 7 (−R$231,50) | não |

Líquido combinado = soma exata das duas origens (1.382,50+984,50=2.367,00) —
confirma que o rastreio de origem não perde nem duplica trade. O número de
trades quase dobra (244 contra 121/127 solo) porque as duas famílias
raramente competem pela mesma barra (só 1 empate no IS inteiro) — o OU
lógico não está escolhendo entre dois gatilhos concorrentes na prática, está
quase SOMANDO a frequência dos dois.

**Passo 2 — correlação diária entre as duas famílias (séries SOLO, mesmo
método do item 7 do mandato original — P&L por pregão, zeros incluídos nos
dias sem disparo):** `Pearson(P&L_diário_G8, P&L_diário_G4) = 0,0117` —
**essencialmente ZERO**, n=122. A premissa de partida da geração (as duas
famílias não tendem a perder nos mesmos dias) **é literalmente verdadeira**:
dos 76 pregões em que o G8 perde, o G4 TAMBÉM perde no mesmo pregão em
apenas 21 (27,6%) — quase idêntico à taxa incondicional de perda do G4
isolado (33/122 = 27,0%). Não há absolutamente nenhum indício de que as
duas famílias reagem ao mesmo "dia de estresse de mercado" (a suspeita que a
própria G5 já tinha levantado) — a correlação diária confirma independência
estatística limpa.

**Passo 3 — p_ruína (MC, `motor.ruina_mc`, R$250→R$100, horizonte=44
operações projetadas pela taxa de cada série) — a resposta direta à
pergunta desta geração:**

`p_ruína(combinado) = 33,5%` **contra** `p_ruína(G8 solo) = 24,8%` e
`p_ruína(G4 solo) = 33,7%` — **o portfólio NÃO reduziu a ruína. Ficou PIOR
que a melhor família sozinha (G8) e praticamente EMPATADO com a pior (G4,
redução de só 0,2pp).** A pior sequência de perdas CONSECUTIVAS (origem
agnóstica, é isso que ameaça o caixa) do combinado é **8 operações
(−R$260,00) — mais longa que a pior sequência de QUALQUER uma das duas
famílias sozinha** (6 do G8, 7 do G4).

**Por que a correlação zero não ajudou — o mecanismo, não só o número.** A
hipótese de portfólio pressupõe um orçamento de risco FIXO dividido entre
apostas descorrelacionadas (diversificação clássica). Aqui o orçamento não
é dividido — é o MESMO caixa de R$250 inteiro, exposto SEQUENCIALMENTE a
CADA família toda vez que ela dispara. Com correlação ~0 mas frequência
~DOBRADA (244 trades contra 121-127 solo, porque as duas famílias
raramente competem pela mesma barra), o portfólio não dilui exposição —
ele **soma tentativas sobre o mesmo caixa não reposto**. Mais tentativas,
mesmo independentes, aumentam estatisticamente a MAIOR sequência de perdas
esperada dentro de qualquer janela de tamanho fixo (o equivalente
probabilístico do paradoxo do aniversário aplicado a sequências de Bernoulli)
— e é exatamente essa maior sequência, não a correlação diária agregada,
que decide se o caixa cruza a margem. A correlação dizia a verdade (as
famílias não falham juntas) mas respondia à pergunta ERRADA para este
capital: a pergunta que decide ruína num caixa de 1 contrato não reposto
não é "os sinais falham no mesmo dia?", é "quantas chances de falhar
seguida existem dentro do horizonte?" — e alternar sinais aumenta essa
segunda grandeza mesmo reduzindo (para zero) a primeira.

**Veredito: HIPÓTESE REFUTADA — e de forma particularmente instrutiva,
porque a premissa que a motivava (baixa correlação) era verdadeira e mesmo
assim o resultado piorou.** Por protocolo, o critério desta geração
("p_ruína(combinado) reduzida de forma clara, ex. ≤15-20%, E líquido>0 E
não censurado") falha já no primeiro ramo — a ruína SUBIU, não caiu. Nenhum
candidato foi promovido. **OOS-1 e OOS-2 não foram rodados** — gastar o
"roda uma vez" do protocolo num candidato que já falha decisivamente no IS,
com um mecanismo claro e não um empate estatístico apertado, seria
desperdício, mesmo precedente de G11/G12.

**Limitação declarada, não escondida:** só a prioridade "ORB vence o
empate" foi testada. Dado que o mecanismo que derruba a hipótese (soma de
frequência sobre caixa não reposto) independe de QUAL família tem
prioridade — ele existe porque as duas quase nunca competem pela mesma
barra, não por causa de como o empate raro é resolvido — a expectativa a
priori para a prioridade inversa (cruzado vence) é que o resultado seja
materialmente o mesmo; não foi medido para confirmar, e fica declarado como
tal, não teria mudado o veredito e não justificava gastar mais uma rodada.
A própria G13 tinha sugerido, no raciocínio para esta geração, combinar o
ORB com o `WinRetangulo` (família de win% mais alto, já validada em
produção, piso de capital R$1.100) em vez da G4 (que nunca validou
isoladamente) — este mandato pediu especificamente G4+G8, e é isso que foi
testado aqui; a variante ORB+WinRetangulo fica fora do escopo de capital
mínimo R$250 desta busca (o piso do WinRetangulo é 4,4× maior) e do mandato
das 4 alavancas, não foi tentada.

**Sizing/ruína/% mensal:** não aplicável como projeção — o gate do IS não
passou. Os números de ruína acima (33,5%/24,8%/33,7%) já são a resposta da
própria busca, não uma estimativa aceita para produção.

**Resposta à pergunta desta geração:** não — alternar entre ORB (G8) e
confirmação cruzada WIN×WDO (G4) sobre o mesmo caixa de R$250 (1 contrato,
nunca 2 posições simultâneas) não dilui a probabilidade de ruína, mesmo as
duas famílias tendo correlação diária de P&L essencialmente zero (0,0117,
n=122) — porque o capital não é um orçamento de risco dividido entre as
duas apostas, é o mesmo caixa reexposto a cada disparo de QUALQUER uma
delas, e a frequência quase dobrada domina o benefício da descorrelação.

### Síntese final — as 4 alavancas do mandato, encerradas

O coordenador pediu 4 alavancas depois que a busca original (G1-G10, 10
famílias de sinal) não validou nenhuma com folga. As 4 estão encerradas:

1. **Tamanho graduado pela força do sinal (G11): REFUTADA.** Força do
   rompimento ORB não prediz qualidade do trade — correlação ~0 na
   estratificação pós-hoc (método correto), e o filtro exclusivo (método
   errado) só parecia funcionar por viés de seleção de evento.
2. **Combinação E/AND de sinais independentes (G12): REFUTADA — por
   amostra, não por direção.** O AND de ORB+cruzado derruba a frequência em
   92-99%; o win% nominal sobe mas a amostra fica pequena demais (12-33
   trades) para o IC95 sair de cima do breakeven em qualquer das 4 janelas
   causais testadas.
3. **Grade fina de sensibilidade (G13): CONFIRMA o penhasco, não encontra
   platô.** 79 células em 3 eixos cruzados (`stop_max`×`alvo`×`confirma`)
   reproduzem EXATAMENTE o mesmo ponto isolado que a G8 já tinha achado com
   16 células em 1 eixo — evidência robusta de que o problema é estrutural
   (o capital de R$250 não aguenta a sequência de perdas plausível de
   NENHUMA geometria ORB testada), não de sub-amostragem.
4. **Portfólio/alternância (G14, esta entrada): REFUTADA, e pelo motivo
   mais instrutivo das quatro.** Correlação ~0 confirmada — e mesmo assim a
   ruína piora, porque o capital não é dividido entre as apostas, é
   reexposto a cada uma, e a frequência combinada domina a descorrelação.

**O fio que atravessa as 4 alavancas, e que nenhuma delas resolve
isoladamente:** em TODAS as quatro, o fator decisivo nunca foi a qualidade
do sinal (win%, payoff, "força" do rompimento) — foi sempre o capital de
R$250/1 contrato colidindo com a estrutura de SEQUÊNCIA de qualquer
geometria testada. G8/G13 não sobrevivem a 2-3 perdas seguidas. G11 não tem
como "diminuir a mão" abaixo de 1 contrato. G12 não tem amostra porque
reduzir frequência é a ÚNICA forma de aumentar seletividade com 1 sinal
binário, e isso custa significância. G14 não dilui ruína porque aumentar
frequência (a única forma de "somar" duas famílias num caixa que não separa
risco) é o oposto do que a ruína precisa. As quatro alavancas, de ângulos
diferentes, convergem para a MESMA restrição: **nenhuma tentou mudar o
WIN%/payoff estrutural do sinal em si — todas tentaram gerenciar o MESMO
par de geometrias de baixo win%/payoff 3x contra um caixa fixo demais para
absorver a variância que essa combinação produz.**

**Recomendação honesta.** Dentro do mandato original (as 4 alavancas
pedidas pelo coordenador), a busca está COMPLETA e nenhuma produziu um
candidato validável a R$250 no WIN@. Mais trabalho dentro do MESMO espaço
(mais geometria ORB, mais combinação de sinais já testados, mais variação
de prioridade de empate) tem expectativa a priori baixa — G13 já mostrou
que uma grade 5× maior reproduz o mesmo ponto isolado, e G14 já mostrou que
o mecanismo de diluição de risco não existe para este capital mesmo com
correlação zero. Continuar dentro deste mandato específico (G1-G14, WIN@,
R$250, setups técnicos simples) seria repetir o padrão "achar uma variação
nova do mesmo truque" que as 4 alavancas já esgotaram. Três caminhos
diferentes ficam honestamente em aberto, nenhum deles dentro do escopo
testado aqui: (a) capital maior que o mínimo de 1 contrato — muda a própria
pergunta ("qual geometria sobrevive a R$250" deixa de ser a pergunta
relevante), não é mais esta busca; (b) uma família de sinal
ESTRUTURALMENTE diferente, de win% mais alto / variância mais baixa (o
`WinRetangulo` já validado em produção é o único caso do repo que bate essa
descrição; a pista que a G13 deixou — combiná-lo com o ORB — não foi
testada aqui porque o mandato pediu especificamente G4); (c) os ~720
conceitos ainda no backlog de `wdo_189_conceitos_tecnicos_price_action`
(MEMORY.md) ou a direção que o dono já indicou preferir — sinal que muda
TAMANHO/stop/alvo de forma probabilística em vez de entra/não-entra binário
(MEMORY.md, "Objetivo: estratégia probabilística" e "Tendência +
colherinha/balde — perda < ganho sempre"). Minha recomendação sincera: **
encerrar esta linha específica (G1-G14) como mandato cumprido e honestamente
sem candidato** — não por falta de esforço de busca (14 gerações, >250
células testadas no total somando G7/G8/G12/G13), mas porque a última
alavanca testada (G14) fecha o ciclo mostrando que o problema nunca foi
"qual combinação de parâmetro/sinal", e sim uma restrição estrutural de
capital que nenhuma das 4 alavancas tinha como contornar por desenho.

## Geração 15 — ORÇAMENTO DE EXPOSIÇÃO fixo (correção do mecanismo que a G14 diagnosticou)

**Quem testou:** agente principal (não delegado a subagente filho), 1
disparo. Código em
`src/strategy/daytrade/lab/win_busca_lucro_g15_portfolio_orcamento.py`
(classe `WinBuscaLucroG15PortfolioOrcamento`, não registrada) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/
g15_portfolio_orcamento/` (`g15_base.py`, `g15_diagnostico.py`,
`g15_is_busca.py`, `g15_sensibilidade_censura.py`, logs
`g15_is_busca_stdout.log`, `g15_sensibilidade_censura_stdout.log`). **Nenhum
arquivo `_congelado_v15.py` foi criado** — nada foi promovido ao OOS-1 (ver
veredito), mesmo precedente de G1/G2/G5/G6/G9/G10/G11/G12/G14.

**Por que esta geração existe.** A G14 mediu DIAGNÓSTICO correto mas testou
a versão mais ingênua de portfólio: qualquer sinal dispara (OU lógico), sem
limite algum. A correlação diária entre ORB (G8/G13) e confirmação cruzada
WIN×WDO (G4) deu essencialmente ZERO (0,0117, n=122) — e mesmo assim a
ruína SUBIU (33,5% contra 24,8% da melhor família sozinha). O motivo: a
R$250 só cabe 1 contrato, então o caixa nunca é dividido entre as duas
famílias — ele é REEXPOSTO a cada disparo de qualquer uma, e como as duas
raramente competem pela mesma barra (1 empate em 122 pregões), o OU lógico
quase SOMA a frequência (244 trades contra 121-127 solo) em vez de ESCOLHER
entre gatilhos concorrentes. Esta geração testa a correção direta: um
ORÇAMENTO DE EXPOSIÇÃO total, do tamanho de UMA família sozinha (~121-127),
para ver se controlar a SOMA (não a correlação) resolve o que a G14 não
resolveu.

**Desenho.** `WinBuscaLucroG15PortfolioOrcamento` é cópia deliberada da G14
(mesmas duas famílias, mesmo portão compartilhado nunca-2-posições, mesma
prioridade ORB-vence-empate, mesmas disciplinas de reentrada herdadas,
geometrias idênticas e NÃO retunadas — esta geração testa o MECANISMO de
alocação, não parâmetro novo) **mais** um contador de vagas
(`orcamento_modo∈{ilimitado,unico,mensal}`, `orcamento_valor`,
`politica_prioridade∈{fifo,regime}`, `regime_corte_hora`). Toda ordem
emitida por qualquer família consome 1 vaga; sem vaga, o sinal é recusado e
contado à parte (`stats_recusado_por_orcamento_*`, nunca confundido com
"já operou hoje" ou "contra tendência" — lição 6.51, não misturar motivos
de recusa diferentes no mesmo contador).

**Passo 0 — diagnóstico de concentração temporal
(`g15_diagnostico.py`).** Pergunta do mandato: as duas famílias disparam em
horários diferentes (abrindo caminho para uma política por regime)? **Não
há separação limpa.** Sinais BRUTOS no IS: ORB=1.084, cruzado=214. Ambas
concentram nas 2 primeiras horas do pregão — ORB 9-11h=63,7%, cruzado
9-11h=78,0% — e a hora de corte que MAIS separa as duas (varredura 10h-17h)
é 10h, com score de separação 1,036 **de um máximo de 2,0** (score=2,0
seria separação perfeita; um corte aleatório já dá ~1,0). A hipótese
explícita do mandato ("ORB só de manhã, cruzado só à tarde") **é refutada
pelos dados antes de qualquer backtest** — as duas famílias disparam
essencialmente na mesma janela do pregão, não em regimes diferentes. A
política por regime abaixo foi testada mesmo assim, mas rotulada
EXPLORATÓRIA/sem base própria, não candidata pré-registrada.

**Passo 1 — referências no IS (mesmo período, mesmo método que a G14):**

| variante | líquido R$ | trades | win% | p_ruína(MC) | top3/líq | pior_seq | sem_trade | censurado |
|---|---|---|---|---|---|---|---|---|
| G8 SOLO (ORB) | +1.365,50 | 121 | 37,2% | **24,8%** | 18% | 6 (−179,00) | 1/122 | não |
| G4 SOLO (cruzado) | +1.221,50 | 127 | 35,4% | 33,7% | 59% | 7 (−231,50) | 60/122 | não |
| PORTFÓLIO ilimitado (= G14) | +2.367,00 | 244 | 35,7% | 33,5% | 33% | 8 (−260,00) | 0/122 | não |

A linha "ilimitado" reproduziu **byte a byte** o número já registrado da G14
(líquido 2.367,00, 244 trades) — checagem de reprodução no log, confirma que
a cópia do mecanismo está correta antes de somar o orçamento.

**Passos 2-4 — as políticas de orçamento, mesma sequência cronológica
combinada, mesmo método de ruína:**

| política | líquido R$ | trades | win% | p_ruína(MC) | pior_seq | sem_trade | censurado | esgotou em |
|---|---|---|---|---|---|---|---|---|
| (a) ÚNICO, orç.=121 (=n G8 solo) | +1.676,50 | 115 | 40,0% | **19,8%** | 8 (−260,00) | 69/122 (56,6%) | **sim** | 2026-03-19 |
| (a) ÚNICO, orç.=127 (=n G4 solo) | +1.727,50 | 121 | 39,7% | **20,8%** | 8 (−260,00) | 66/122 (54,1%) | **sim** | 2026-03-24 |
| (a) MENSAL, orç.=20/mês (reabastece) | +358,50 | 115 | 29,6% | **50,9%** | 11 (−352,50) | 55/122 (45,1%) | não | 2026-06-15 |
| (b) REGIME, corte=10h + orç.=121 (exploratória) | +1.887,50 | 115 | 41,7% | **16,8%** | 7 (−220,50) | 63/122 (51,6%) | **sim** | 2026-03-30 |

**O achado decisivo: as duas políticas que PARECEM reduzir a ruína (ÚNICO e
REGIME) só parecem porque estão CENSURADAS — e as que não estão censuradas
não melhoram nada.** Olhando a coluna "esgotou em": o orçamento de 115-121
vagas se esgota entre 19 e 30 de março — **antes de 2,5 dos 6 meses do IS**
— e o robô fica em silêncio pelos **~3,5 meses restantes** (69/122, 66/122 e
63/122 pregões sem trade, todos acima do limiar de 50% que a própria linha
de pesquisa usa como censura desde a G7). Isto é exatamente o padrão que o
CLAUDE.md proíbe tratar como veredito ("piso de capital como condição de
continuidade") — só que aqui o piso que se esgota é o ORÇAMENTO, não o
caixa. O MENSAL, a única política que reabastece e por isso **não** fica em
silêncio prolongado (sem_trade=45,1%, abaixo do limiar, não censurada),
é a única comparação honesta — e ela é **pior que as duas famílias
sozinhas em toda métrica**: p_ruína 50,9% (contra 24,8% do G8 e 33,7% do
G4), win% 29,6% abaixo do BE empírico (veredito indefinido), pior sequência
de perdas 11 operações (pior que as 6-8 de qualquer linha não-censurada
desta geração) e concentração top3/líquido de **120%** (o resto da amostra
é líquido NEGATIVO).

**Confirmação por sensibilidade (`g15_sensibilidade_censura.py`,
não um dos 4 passos do protocolo, teste extra para fechar a dúvida): a
queda de p_ruína do orçamento ÚNICO é um GRADIENTE DE CENSURA, não uma
melhora de mecanismo.** Variando o orçamento de 121 até 244 (o n do
portfólio ilimitado):

| orçamento | trades | sem_trade | esgotou em | censurado | p_ruína |
|---|---|---|---|---|---|
| 121 | 115 | 69/122 | 2026-03-19 | sim | 19,8% |
| 150 | 144 | 51/122 | 2026-04-15 | não | 26,2% |
| 180 | 174 | 29/122 | 2026-05-19 | não | 32,1% |
| 210 | 203 | 15/122 | 2026-06-09 | não | 39,4% |
| 230 | 223 | 6/122 | 2026-06-22 | não | 37,6% |
| 244 (≈ilimitado) | 237 | 2/122 | 2026-06-26 | não | 36,4% |

p_ruína sobe de forma monotônica (com ruído de MC) de 19,8% para a faixa de
36-39% conforme o orçamento cresce e o robô passa a operar pela janela
inteira — convergindo exatamente para perto do número do portfólio
ilimitado (33,5%) assim que o orçamento deixa de ser a restrição ativa. Não
existe NENHUM tamanho de orçamento que entregue p_ruína baixa SEM
silenciar o robô por uma fração grande da janela — as duas coisas
(orçamento pequeno o bastante para "parecer seguro" e orçamento grande o
bastante para não censurar) são **mutuamente exclusivas** neste mecanismo,
porque a taxa de disparo combinada das duas famílias (~2 trades/dia) é
estruturalmente maior que a de qualquer uma sozinha — exatamente o "soma de
frequência" que a G14 já tinha diagnosticado, agora visto como o motivo
matemático de por que ORÇAMENTO FIXO não pode funcionar sem reabastecer, e
reabastecer (MENSAL) é a política que piora tudo.

**Resposta à pergunta decisiva (item 3 do mandato).** Com o orçamento total
CONTROLADO e **sem contar os resultados censurados** (a única leitura
honesta, pelo próprio precedente desta linha de pesquisa): a p_ruína do
portfólio **NÃO** fica menor que a da pior família sozinha (G4 solo=33,7%)
nem chega perto da melhor (G8 solo=24,8%) — a única política que evita
censura (MENSAL) fica em 50,9%, **pior que tudo**. Os números que pareciam
responder "sim" (19,8%/20,8%/16,8%) são artefato de o robô ficar mudo pela
segunda metade do semestre, não evidência de risco reduzido. **O mecanismo
da G14 não está corrigido — está mais claramente diagnosticado: não existe
forma de fatiar um caixa de R$250/1-contrato entre duas famílias que não
seja ou (a) deixá-las somar frequência (G14, ruína sobe) ou (b) impor um
teto que, para não virar silêncio prolongado, precisa reabastecer — e
reabastecer reintroduz exatamente a mesma sequência de tentativas repetidas
sobre o caixa não-dividido que causa a ruína, só que agora intercalando
qual família "ganha" cada vaga mês a mês, o que no teste piorou a mistura
(mais ORB, menos cruzado, pior sequência de perdas) em vez de melhorar.**

**Veredito: HIPÓTESE REFUTADA, com evidência mais forte que a G14 (um
gradiente inteiro, não um ponto isolado).** Nenhuma política bateu o
critério composto do mandato (líquido>0 E não-censurado E win%/IC favorável
E p_ruína claramente melhor que qualquer componente solo) — ÚNICO e REGIME
falham no "não-censurado", MENSAL falha em TODOS os outros quatro critérios
ao mesmo tempo. **OOS-1 e OOS-2 não foram rodados** — gastar o "roda uma
vez" do protocolo em qualquer uma das quatro linhas seria desperdício
(mesmo precedente de G5/G11/G12/G14): as duas censuradas não passariam o
próprio gate de censura que esta linha de pesquisa usa desde a G7, e a
única não-censurada (MENSAL) é pior que ambas as famílias sozinhas em toda
métrica.

**Limitação declarada.** A política (b) por regime nunca teve uma base
própria — o diagnóstico do Passo 0 já mostrava que a separação temporal é
fraca (score 1,036 de 2,0), então testá-la era sobretudo para fechar a
pergunta do mandato com dado, não por expectativa de que funcionasse; o
resultado dela também saiu censurado pelo mesmo motivo do ÚNICO (o corte de
regime reduz ainda mais a taxa de disparo, logo esgota o orçamento ainda
mais cedo — 2026-03-30), então não acrescenta uma quinta leitura
independente, só confirma o mesmo padrão.

**Sizing/ruína/% mensal:** não aplicável como projeção — nenhum candidato
passou o gate do IS. Os números de p_ruína acima (19,8% a 50,9%) já são a
resposta da própria busca, e os censurados não devem ser lidos como
estimativa de produção sob nenhuma hipótese.

**Resposta ao item 6 do mandato — vale testar a ideia (b) da G14 (combinar
com uma família de win% mais alto / variância mais baixa, inspirada no
`WinRetangulo` já em produção)?** Honestamente, sim, é o único caminho
dentro do espaço de "portfólio"/"mistura" ainda não testado nesta linha —
mas não é um ajuste pequeno: o `WinRetangulo` de produção tem piso de
capital R$1.100 (4,4× o R$250 desta busca, `CLAUDE.md`/MEMORY.md
`win_retangulo_robo_2026_09_15`), então adaptá-lo ao capital e à disciplina
`alvo≥3x` desta linha exigiria redesenhar a geometria dele do zero, não
reaproveitar os parâmetros de produção — seria efetivamente uma Geração 16
inteira (uma nova família de sinal, não um novo mecanismo de portfólio),
fora do escopo desta entrada. Registro a recomendação, não a executo aqui.

**Síntese: a G15 fecha, com um teste mais rigoroso que a G14 (um gradiente
contínuo em vez de um ponto só), a mesma conclusão que a G14 já apontava e
que a síntese das 4 alavancas (fim da entrada da G14) já tinha deixado
escrita.** A restrição é estrutural ao capital de R$250/1-contrato, não ao
desenho de qualquer mecanismo de seleção/orçamento/prioridade testado até
aqui — nenhuma forma de intercalar, limitar ou escalonar QUAIS sinais usam
o mesmo caixa sequencial resolve o problema, porque o problema nunca foi
"qual sinal opera", foi "quantas chances de uma sequência de perdas o caixa
aguenta" — e cortar o número de chances ou te deixa em silêncio (censura) ou
não muda a sequência de forma favorável (MENSAL, medido aqui, piorou).
Mantida a recomendação da G14: encerrar a linha de portfólio/alternância
para este capital; os caminhos em aberto continuam sendo capital maior,
uma família estruturalmente diferente (nota acima sobre o `WinRetangulo`
adaptado), ou a direção que o dono já indicou preferir (sinal que muda
tamanho/stop/alvo de forma probabilística, MEMORY.md).

## Geração 16 — `WinRetangulo` redesenhado para alvo≥3x, capital R$250 (última família de sinal do mandato)

**Quem testou:** agente principal (não delegado a subagente filho), 1
disparo. Código em
`src/strategy/daytrade/lab/win_busca_lucro_g16_retangulo_250.py` (classe
`WinBuscaLucroG16Retangulo250`, não registrada) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g16_retangulo_250/`
(`g16_base.py`, `g16_is_busca.py`, log completo
`g16_is_busca_stdout.log`). **Nenhum arquivo `_congelado_v16.py` foi
criado** — nada foi promovido ao OOS-1 (ver veredito), mesmo precedente de
G1/G2/G5/G6/G9/G10/G11/G12/G14/G15.

**Por que esta geração existe.** G1-G10 (famílias de sinal) e G11-G15
(alavancas do coordenador) convergiram, de ângulos diferentes, para o mesmo
teto: alvo≥3x exige win% baixo, win% baixo produz sequências de perda que o
caixa de R$250/1 contrato não aguenta (G13: penhasco confirmado em 79
células, nenhum platô; G14/G15: nem alternância nem orçamento de exposição
resolvem a ruína, porque o caixa nunca é dividido, é reexposto a cada
disparo). A G13 e a G15 identificaram, mas não testaram, o único ângulo
genuinamente diferente ainda em aberto: uma família de win% MAIS ALTO e
variância MAIS BAIXA, ao estilo do `WinRetangulo` (produção real, win%~45%,
payoff ~1,6:1, piso de capital R$1.100 — nenhum dos dois direto compatível
com o mandato desta busca).

**O que foi reaproveitado, por import direto, sem reimplementar.**
`detecta_retangulo` (função pura module-level de
`strategy.daytrade.lab.win_retangulo` — topo/piso por quantil, toques
mínimos, visitas, cruzamentos do meio, contenção, contração, deriva) e as
constantes de morte do retângulo (`MARGEM_MORTE`/`BARRAS_MORTE`/
`LARGURA_MINIMA_TICKS`). Nenhum critério de FORMA foi alterado —
`janela_barras=20`, `tolerancia_borda=0,20`, `largura_minima_pontos=328`
ficaram nos valores CONGELADOS da produção, sem retune (esta geração testa
geometria de entrada/saída, não detecção).

**O que foi redesenhado.** A geometria de entrada/saída. Produção: entra no
MEIO do retângulo, mira 0,80× a largura ALÉM do meio (atravessa a borda
oposta por 0,30× a largura), para no stop a 0,50× a largura do meio
(exatamente na borda oposta) — payoff 1,6:1. A classe desta geração
generaliza os dois parâmetros e **impõe no construtor**
`alvo_fracao_largura >= 3 × stop_fracao_largura`, levantando `ValueError`
caso contrário — o desenho de execução fechado deste projeto vira validação
estrutural, não convenção de busca. `quantidade=1` sempre (a classe recusa
qualquer outro valor): a R$250 cabe exatamente 1 contrato, sem escada de
capital como a da produção (que supõe piso R$1.100). Execução fechada
idêntica à linha inteira (EnterLimit ttl=10, alvo fatiado sem prazo,
`anchor_exits_at_fill=True`, só stop a mercado, `target_fills_as_maker=True`),
fila WIN@ zero nos dois lados (não calibrada, premissa otimista declarada —
e para o ALVO desta geração, que pode mirar bem além da borda oposta, essa
premissa é MAIS otimista que para a entrada, já que um nível raramente
visitado teria fila real alta: bandeira declarada, não resolvida aqui, mesma
família de problema que encerrou a família maker do WDO F1 por fila).

**Busca no IS (jan-jun/2026, 122 pregões, capital real R$250, 1 contrato
fixo) — grade 2D completa, 18 células, tabela completa em
`g16_is_busca_stdout.log`:**

| stop (×largura) | alvo (×largura, mult.) | líquido R$ | trades | win% | BEnom% | veredito | sem_trade | cens.capital | p_ruína | pior_seq |
|---|---|---|---|---|---|---|---|---|---|---|
| 0,150 | 0,450 (3x) | −156,00 | 18 | 11,1% | 25,0% | indefinido | 119/122 | **sim** | 0,0%* | 7 (−96,50) |
| 0,200 | 0,600 (3x) | −155,00 | 20 | 15,0% | 25,0% | indefinido | 119/122 | **sim** | 0,0%* | 8 (−128,00) |
| 0,250 | 0,750 (3x) | −157,50 | 19 | 15,8% | 25,0% | indefinido | 119/122 | **sim** | 0,0%* | 8 (−156,00) |
| 0,267 | 0,800 (3x, = alvo da produção) | −159,00 | 30 | 20,0% | 25,0% | indefinido | 112/122 | **sim** | 28,6% | — |
| 0,300 | 0,900 (3x) | −172,50 | 15 | 13,3% | 25,0% | indefinido | 119/122 | **sim** | 0,0%* | 10 (−232,00) |
| 0,375 | 1,125 (3x) | −172,00 | 10 | 10,0% | 25,0% | indefinido | 119/122 | **sim** | 0,0%* | 8 (−225,00) |
| 0,500 | 1,500 (3x) | −180,50 | 17 | 17,6% | 25,0% | indefinido | 112/122 | **sim** | 42,4% | 7 (−269,50) |
| 0,500 | 2,000 (4x) | −186,50 | 5 | 0,0% | 20,0% | NEGATIVO | 119/122 | **sim** | 0,0%* | 5 (−186,50) |
| 0,500 | 2,500 (5x) | −186,50 | 5 | 0,0% | 16,7% | NEGATIVO | 119/122 | **sim** | 0,0%* | 5 (−186,50) |

\* `p_ruína` de células com amostra curta demais sai artificialmente baixa
(mesma ressalva de G8/G13 — amostra curta não dá para o Monte Carlo
simular), por isso o critério composto nunca aceita uma célula só por
`p_ruína` baixa quando `censura_capital=True`.

**As 18 células (6 valores de `stop_fracao_largura` × 3 multiplicadores de
alvo ∈ {3x,4x,5x}) são UNANIMEMENTE negativas, UNANIMEMENTE censuradas por
capital e o win% fica SEMPRE abaixo do breakeven nominal — 0 de 18 batem o
critério composto** (líquido>0 E não censurado por capital E win%≠NEGATIVO
E p_ruína≤25%, mesmo molde de G8/G13/G15). Uma 19ª célula de confirmação
(linha `0,267 / 0,800`, ver abaixo) também falha.

**A auditoria de ocorrências brutas descarta bug de implementação (lição
6.48/6.49, conferida antes de aceitar qualquer resultado baixo como
"hipótese sem sinal").** `g16_base.contagem_bruta_retangulos` (import direto
de `detecta_retangulo`, fora da classe, sem portão de capital/pendência) acha
**7.030 retângulos brutos no IS, 1.866 com largura≥328pts, em 122/122
pregões com pelo menos uma detecção** — mesma ordem de grandeza da base de
detecção da produção. A contagem de 5-30 ordens emitidas por célula não é
"a hipótese não tem gatilho": é o portão de capital (1 ordem pendente por
vez + caixa exaurido cedo) cortando a amostra depois de poucas tentativas —
exatamente o modo de morte que o item 6.51 pede para não confundir com
seletividade de desenho (aqui É morte por capital: `equity_min` chega a
R$91,00/R$101,00, abaixo da margem crua R$100, com ordens recusadas
registradas).

**Teste de confirmação — approach (ii) do mandato, isolado.** O mandato
sugeriu explicitamente testar "mesmo alvo da produção (0,80×), stop mais
apertado". Rodado em separado (não contido na grade 3x/4x/5x acima, que usa
multiplicadores do próprio stop): `stop_fracao_largura=0,2667` (=0,80/3, o
mínimo que ainda bate `alvo>=3×stop` com o alvo EXATO da produção),
`alvo_fracao_largura=0,80`. Resultado: **n=30, líquido −R$159,00, win=20,0%
(BE nominal 26,75%), 112/122 pregões sem trade, equity mínima R$91,00
(abaixo da margem crua), p_ruína(MC)=28,6%.** Mantém a geometria de alvo que
a produção já validou (0,80×, a mesma que dá 44,9%/45,8% de acerto com
stop=0,50×) e troca SÓ o stop — e o win% desaba de ~45% para 20%. Isto
isola a causa: **não é o alvo que quebra o win%, é o stop apertado.**

**O mecanismo, não só o número.** Um retângulo só QUALIFICA como retângulo
(critérios herdados de `detecta_retangulo`: ≥2 toques por borda, ≥2 visitas
espalhadas, ≥3 cruzamentos do meio) porque o preço já demonstrou que oscila
rotineiramente até perto das DUAS bordas — ou seja, até ~0,40-0,50× a
largura do meio em ambas as direções, repetidas vezes, DENTRO da própria
janela de detecção. Um stop técnico mais apertado que isso (0,15 a 0,375×
largura) fica posicionado DENTRO da banda de oscilação normal que definiu o
retângulo como válido — ele é varrido pelo próprio ruído que caracteriza
uma lateralização, antes que a entrada no meio tenha chance de reverter na
direção apostada. O stop da produção (0,50×, exatamente na borda oposta) não
é um número arbitrário: é o único ponto que fica FORA do alcance normal de
oscilação de um retângulo válido — put outro jeito, **o espaço de stop que
este detector de forma produz só tem um valor que funciona (a borda
oposta), e esse valor, por construção geométrica (`topo` e `piso` são
EQUIDISTANTES do `meio`), empata exatamente com a distância até a borda
mirada pelo alvo — produzindo sempre payoff ≤2:1 quando o alvo fica DENTRO
do retângulo, e só ultrapassando 1,6:1 (o ponto calibrado da produção)
quando o alvo atravessa a borda oposta por uma fração pequena.** Pedir
alvo≥3× força ou (a) apertar o stop para dentro da banda de oscilação —
mata o win% pelo motivo acima — ou (b) esticar o alvo bem além do que o
retângulo historicamente alcança — e as células com `mult=4x`/`5x` em
`stop=0,50` mostram o resultado: `n` cai para 5 (de 17 em `mult=3x`),
win%=0,0% nas duas, amostra praticamente extinta. As duas rotas sugeridas
pelo mandato foram testadas e as duas quebram o mesmo mecanismo — a
geometria 1,6:1 da produção não é um ponto arbitrário da busca, é o único
lugar onde o stop fica fora do ruído do próprio padrão que o justifica.

**Veredito: MORTA, de forma mais uniforme que qualquer geração anterior
desta busca.** G1-G15 sempre tinham pelo menos uma célula "quase lá" (IC
cruzando por pouco, concentração alta mas líquido positivo). Aqui as 19
células testadas (18 da grade + 1 de confirmação) são **negativas em
100% dos casos**, **censuradas por capital em 100% dos casos**, e o win%
fica sempre abaixo do breakeven nominal — não há ambiguidade estatística a
discutir. **Nenhum candidato foi promovido ao OOS-1** — gastar o "roda uma
vez" do protocolo em qualquer uma das 19 células seria desperdício, mesmo
precedente de G5/G11/G12/G14/G15: todas falham já no IS, de forma unânime,
não por margem apertada.

**Verificação de ticks (item 6.47):** não aplicável — nenhum candidato
passou o gate do IS (protocolo: só verifica ticks quem passa e tem stop
mediano <100pts). Os stops medianos observados variam de 60 a 185pts
conforme a célula, mas a questão é irrelevante já que todas morrem antes
dessa checagem.

**Sizing/ruína/% mensal:** não aplicável como projeção — nenhum candidato
passou o gate do IS. Os números de p_ruína acima (0,0% a 42,4%) não devem
ser lidos como estimativa de produção — a maioria vem de amostra pequena
demais para o Monte Carlo simular de forma confiável (mesma ressalva de
G8/G13/G15).

**Resposta à pergunta desta geração:** não — a lógica de DETECÇÃO de
lateralização do `WinRetangulo` (reaproveitada sem alteração) continua
achando retângulos válidos com a mesma frequência de sempre, mas a geometria
de entrada/saída que a produção validou (alvo=0,80×/stop=0,50×, payoff
1,6:1) não tem rota de redesenho para `alvo≥3×` que preserve o win%: tanto
apertar o stop (fica dentro do ruído do próprio padrão) quanto esticar o
alvo (sai do alcance histórico do padrão) quebram o mecanismo que fazia a
estratégia original funcionar. Isto não é "falta de busca" — as DUAS rotas
que o mandato sugeriu foram testadas, isoladas uma da outra, e as duas
convergem para o mesmo colapso de win%.

### Síntese final — as 16 gerações, mandato original encerrado

Esta era a última família de sinal genuinamente nova dentro do escopo
razoável do mandato (CLAUDE.md/MEMORY.md, busca por EA de day trade WIN,
capital real R$250, alvo≥3× o stop, desenho de execução fechado). Com ela
também morta, vale registrar o que as 16 gerações, no total, estabeleceram:

**O que foi tentado.** Dez famílias de SINAL (G1-G10): recuo de pernada com
filtro de horário/sequência (R61/R65 — G1/G2), recuo raso com m/alvo/janela
(R57/R59/R58 — G3), confirmação cruzada WIN×WDO por estado anômalo de
correlação (G4), três proxies de regime de volatilidade WIN-only (amplitude
de bloco, R35/vela extrema, volume de bloco — G5), teto de reentradas por
pregão sobre o vencedor da G5 (G6) — e mais quatro gerações não detalhadas
nesta síntese (G7-G10, ORB/momentum, que estabeleceram a família que as
alavancas do coordenador depois exploraram a fundo). Quatro ALAVANCAS sobre
a família ORB/momentum (G11-G15, mandato do coordenador): tamanho graduado
pela força do sinal (G11, REFUTADA — força não prediz resultado, correlação
≈0 na estratificação pós-hoc correta), combinação E/AND de sinais
independentes (G12, REFUTADA por amostra — AND derruba frequência 92-99%,
IC nunca sai de cima do breakeven), grade fina 3D de sensibilidade (G13,
CONFIRMA penhasco — 79 células, 1 só sobrevive, cercada de colapso total em
toda direção), portfólio/alternância (G14, REFUTADA — correlação diária ≈0
mas ruína SOBE, porque o caixa não é dividido, é reexposto), orçamento de
exposição fixo (G15, REFUTADA com gradiente inteiro — todo orçamento pequeno
o bastante para "parecer seguro" fica censurado por silêncio prolongado, e o
único que não censura, MENSAL, é pior que qualquer família sozinha em toda
métrica). E, por fim, a família de win% alto/variância baixa (G16, esta
entrada) — `WinRetangulo` redesenhado para `alvo≥3x`, MORTA de forma unânime
(19/19 células negativas e censuradas).

**A conclusão estrutural central, que atravessa as 16 gerações sem
exceção:** existe uma tensão de três pontas que nenhuma combinação de
parâmetro, filtro, alavanca de portfólio ou família de sinal testada
resolveu — **alvo≥3× exige um win% baixo** (geometricamente, o breakeven
nominal de um payoff 3:1 já é 25%, e qualquer custo/deslize realista empurra
o breakeven EMPÍRICO ainda mais alto); **um win% baixo produz sequências de
perda plausíveis, não raras** (o paradoxo do aniversário aplicado a
sequências de Bernoulli: mais tentativas, mesmo independentes e mesmo com
edge positivo no agregado, aumentam a maior sequência de perdas esperada
dentro de qualquer janela finita); e **o capital real de R$250/1 contrato do
WIN@ não tem fôlego para absorver essa sequência** antes que o edge,
se existir, tenha chance de se expressar estatisticamente — a margem crua
de R$100 fica a 1-3 perdas de distância de qualquer geometria testada com
stop abaixo de ~150-200 pontos. As famílias de SINAL (G1-G10, G16) morreram
tentando achar um gatilho melhor dentro dessa restrição; as ALAVANCAS
(G11-G15) morreram tentando GERENCIAR a mesma restrição sem conseguir
contorná-la por desenho. Nenhuma das duas abordagens tinha, nem podia ter,
como resolver um problema que não é de sinal nem de gerenciamento — é
geométrico-estatístico, imposto pela combinação `alvo≥3×` × `capital
mínimo`.

**Recomendação honesta.** Dentro do mandato original e das suas extensões
(G1-G16, WIN@, R$250, alvo≥3×, desenho de execução fechado), a busca está
COMPLETA. Mais trabalho dentro do MESMO espaço — mais parâmetro de geometria,
mais filtro, mais combinação de sinais já testados — tem expectativa a
priori muito baixa: G13 já mostrou que uma grade 5× maior reproduz o mesmo
ótimo isolado da G8; G16 mostrou que a ÚNICA família de alto win%/baixa
variância do repo, testada em 19 geometrias diferentes, não sobrevive à
restrição `alvo≥3×` por um motivo estrutural (o stop que funciona está
geometricamente amarrado ao formato do próprio padrão, não é um parâmetro
livre). Os caminhos que ficam honestamente em aberto, nenhum deles dentro do
escopo testado em G1-G16:

1. **Capital maior que o mínimo de 1 contrato.** Muda a própria pergunta —
   "qual geometria sobrevive a R$250" deixa de ser a pergunta relevante.
   É literalmente o que torna o `WinRetangulo` de produção viável hoje
   (R$1.100, payoff 1,6:1, sem a exigência de alvo≥3×): ele não precisa
   resolver a mesma restrição que G1-G16 tentaram resolver, porque o mandato
   dele é outro.
2. **Relaxar `alvo≥3×`.** A própria restrição é a origem matemática do
   problema (breakeven nominal sobe com o múltiplo). Isto é uma decisão do
   dono, não uma conclusão desta busca — a disciplina de "perder de
   colherinha, ganhar de balde" (MEMORY.md) é princípio declarado, não
   parâmetro a relaxar sem autorização.
3. **A direção que o dono já indicou preferir** (MEMORY.md, "Objetivo:
   estratégia probabilística" / "Tendência + colherinha/balde"): sinal que
   muda TAMANHO/stop/alvo de forma probabilística em vez de entra/não-entra
   binário — nunca testado nesta busca, que usou sempre sinal binário com
   geometria fixa por célula.
4. Os ~720 conceitos ainda no backlog de `wdo_189_conceitos_tecnicos_price_
   action` (MEMORY.md) — mas note que são majoritariamente do WDO, não do
   WIN, e price-action técnico puro (candle/momentum/breakout) é exatamente
   a classe de sinal que G1-G10/G16 já esgotaram para o WIN.

**Minha recomendação sincera: encerrar esta linha específica (G1-G16) como
mandato cumprido e honestamente sem candidato.** Não por falta de esforço
de busca (16 gerações, >400 células testadas no total somando todas as
grades), mas porque a geração final (G16) fechou o ciclo mostrando que nem a
família de sinal estruturalmente mais promissora do repo (win%~45%, já
validada em produção) tem rota de adaptação para a restrição de capital
desta busca — a mesma restrição que as quatro alavancas (G11-G15) já tinham
mostrado ser insolúvel por gerenciamento. Continuar gerando variações dentro
deste mandato específico teria expectativa de valor muito baixa; os quatro
caminhos listados acima exigem uma decisão do dono sobre qual restrição
relaxar (capital, múltiplo de alvo, ou tipo de sinal), não mais uma geração
de busca.

## Geração 17 — capital de teste R$1.000 + grade de alvo {2x,2,5x,3x,4x,5x} sobre o sinal cruzado da G4

**Quem testou:** agente principal (não delegado a subagente filho), 1
disparo. Código em
`src/strategy/daytrade/lab/win_busca_lucro_g17_cross_wdo_capital1000.py`
(classe `WinBuscaLucroG17CrossWdoCapital1000`, não registrada, piso de
`alvo_multiplo` relaxado de 3,0x para 2,0x — nunca ≤1x) + versão
**congelada** em `..._congelado_v17.py` + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g17_capital1000/`
(`g17_base.py`, `g17_is_busca.py`, `g17_comparacao_capital.py`, `g17_oos1.py`,
logs `g17_is_busca_stdout.log`, `g17_comparacao_capital_stdout.log`,
`g17_oos1_stdout.log`).

**Mandato (dono, 2026-10-05):** depois de 16 gerações mortas pela mesma
restrição estrutural (capital R$250 + `alvo≥3x` → win% baixo → sequência de
perdas quebra o caixa — síntese da G16, acima), o dono abriu duas portas SÓ
para esta busca: (1) capital de teste R$1.000 (não R$250 — exceção
explícita, não muda a regra geral do repo); (2) `alvo_multiplo` vira grade
{2x,2,5x,3x,4x,5x} em vez de `≥3x` fixo (piso nunca cai para ≤1x). O que foi
reaproveitado por IMPORT direto, sem reimplementar: `estado_anomalo_cruzado`
(função pura da G4, j=20min/q=0,75/continuação — não retunados aqui) e a
estrutura geral da classe (pernada maior R43 inegociável, `EnterLimit` com
buffer de entrada, execução fechada idêntica à linha: `ttl_bars`, alvo
fatiado sem prazo, `anchor_exits_at_fill`, só stop a mercado,
`target_fills_as_maker`). **Escolha declarada:** 1 contrato FIXO (isola o
efeito de alvo/stop primeiro — dimensionamento graduado por caixa é
explicitamente a G19, não esta geração). Fila WIN@ não calibrada
(`queue_ahead_qty=0`), premissa otimista idêntica à linha inteira.

### Grade 2D completa no IS (jan-jun/2026, 122 pregões, capital R$1.000, 1 contrato fixo, buffer=30, j20/q75/continuação) — 15 células

| alvo×stop | líquido R$ | trades | win% | BEnom% | BEemp% | IC95 win% | veredito | top3/liq | top5/liq | p_ruína MC | pior_seq |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2,0x / 100 | +377,00 | 142 | 43,0% | 33,3% | 38,9% | [35,1;51,2] | indefinido | 93% | 136% | 0,2% | 7 (−163,50) |
| 2,5x / 100 | +645,00 | 140 | 40,0% | 28,6% | 33,9% | [32,3;48,3] | indefinido | 60% | 91% | 0,1% | 7 (−151,50) |
| 3,0x / 100 | +523,50 | 137 | 34,3% | 25,0% | 29,8% | [26,9;42,6] | indefinido | 75% | 120% | 0,4% | 9 (−231,50) |
| 4,0x / 100 | +660,50 | 135 | 28,9% | 20,0% | 24,1% | [21,9;37,0] | indefinido | 83% | 122% | 0,6% | 10 (−253,00) |
| 5,0x / 100 | +858,50 | 133 | 25,6% | 16,7% | 20,3% | [18,9;33,6] | indefinido | 79% | 106% | 0,6% | 12 (−279,00) |
| 2,0x / 150 | +892,00 | 134 | 43,3% | 33,3% | 36,1% | [35,2;51,7] | indefinido | 53% | 78% | 0,2% | 6 (−189,00) |
| 2,5x / 150 | +1.060,00 | 128 | 39,1% | 28,6% | 31,3% | [31,0;47,7] | indefinido | 56% | 79% | 0,2% | 7 (−231,50) |
| **3,0x / 150 (= geometria original da G4)** | **+1.221,50** | 127 | 35,4% | 25,0% | 27,5% | [27,7;44,1] | **POSITIVO** | 59% | 83% | 0,3% | 7 (−231,50) |
| **4,0x / 150 (VENCEDOR do IS)** | **+1.698,50** | 125 | 31,2% | 20,0% | 22,2% | [23,7;39,8] | **POSITIVO** | 56% | 77% | 0,2% | 17 (−624,50) |
| 5,0x / 150 | +1.091,50 | 123 | 23,6% | 16,7% | 18,6% | [16,9;31,8] | indefinido | 115% | 153% | 3,1% | 17 (−624,50) |
| 2,0x / 200 | +830,50 | 125 | 40,8% | 33,3% | 35,3% | [32,6;49,6] | indefinido | 77% | 105% | 1,6% | 7 (−291,50) |
| 2,5x / 200 | +1.109,00 | 122 | 36,9% | 28,6% | 30,4% | [28,8;45,7] | indefinido | 72% | 104% | 1,6% | 7 (−291,50) |
| 3,0x / 200 | +1.547,50 | 121 | 34,7% | 25,0% | 26,7% | [26,8;43,5] | POSITIVO | 62% | 90% | 1,0% | 16 (−733,00) |
| 4,0x / 200 | +1.217,00 | 120 | 26,7% | 20,0% | 21,5% | [19,6;35,2] | indefinido | 108% | 140% | 5,1% | 16 (−733,00) |
| 5,0x / 200 | +699,00 | 114 | 21,1% | 16,7% | 18,4% | [14,6;29,4] | indefinido | 182% | 239% | 16,3% | 16 (−733,00) |

**Leitura da curva, não só do vencedor.** As **15 de 15 células batem o
portão básico** (líquido>0, não censurada por capital nem por amostra,
veredito≠NEGATIVO) — o oposto exato da G16 (19/19 unânimes NEGATIVAS/
censuradas a R$250). `alvo=2x/2,5x` de fato **sobe o win% visivelmente**
(43,3%/39,1% contra 35,4%/31,2% em 3x/4x, no mesmo stop=150) — a grade
aberta pelo dono funciona como esperado no eixo win%. Mas o breakeven
EMPÍRICO sobe MENOS que proporcionalmente ao nominal (payoff realizado não
cai na mesma razão do nominal por causa de custo/deslize fixo), então a
MARGEM estatística (limite inferior do IC95 menos BEemp) não melhora com
multiplicadores menores — ao contrário, as 3 únicas células POSITIVAS da
grade inteira (3x/150, 4x/150, 3x/200) estão todas em `alvo≥3x`, e **nenhuma
célula com alvo=2x ou 2,5x sai de "indefinido"** em nenhum stop testado. O
`p_ruína` sobe com `alvo` e com `stop` (mais previsível no stop maior: perda
por operação maior), com salto visível em `alvo=5x` (3,1%→16,3% conforme o
stop sobe) — mas mesmo o pior caso da grade inteira (16,3%) já é menor que
qualquer coisa que a G16 produziu a R$250.

### Comparação explícita (item 2 do mandato): MESMA geometria da G4 (alvo=3x/stop=150/buffer=30), capital R$250 × R$1.000

Rodada com a classe ORIGINAL da G4 (import direto, sem alteração nenhuma),
`g17_comparacao_capital.py`:

| capital | trades | líquido R$ | win% | veredito | equity_mín | pior_seq | **p_ruína MC** | ruína (Lundberg) | t_mediano até quebrar |
|---|---|---|---|---|---|---|---|---|---|
| R$250 (original G4) | 127 | +1.221,50 | 35,4% | POSITIVO | 243,00 | 7 (−231,50) | **35,3%** | 40,5% | 10,0 operações |
| R$1.000 (esta geração) | 127 | +1.221,50 | 35,4% | POSITIVO | 993,00 | 7 (−231,50) | **0,3%** | 0,4% | 82,5 operações |

**Trades e líquido são BIT A BIT idênticos** (nenhuma ordem foi recusada por
capital em nenhum dos dois capitais nesta janela/geometria — a diferença
inteira está na simulação de ruína sobre a MESMA distribuição de P&L). A
resposta à pergunta do item 2 é **sim, de forma dramática**: só trocar o
caixa de partida de R$250 para R$1.000, sem mexer em NADA da geometria,
derruba `p_ruína` de **35,3% para 0,3%** (Lundberg confirma a mesma ordem de
grandeza: 40,5%→0,4%). Isto é consistente com o diagnóstico da síntese da
G16 — o caixa de R$250 nunca dava fôlego para a sequência de perdas que um
win% de ~35% produz com alguma regularidade, não importa quão positivo o
edge agregado fosse.

### Vencedora do IS: `alvo=4,0x`, `stop=150pts`, `buffer=30pts`, `j=20min`, `q=0,75`, `continuação`, capital R$1.000

Escolhida entre as 3 células POSITIVAS da grade (3x/150, 4x/150, 3x/200) por
maior líquido (R$1.698,50) + menor `p_ruína` (0,2%, empatada com 3x/150) +
melhor concentração entre as três (top3/liq=56%, top5/liq=77%, as menores
das três) + melhor `lucro/DD` (2,23). 125 trades, 62/122 pregões com trade
(mediana ~2 trades/pregão operado, sem sinal de reentrada excessiva — item
6.49), win 31,2% (BEnom 20,0%, BEemp 22,2%, **IC95 [23,7;39,8] — margem de
1,5pp acima do BEemp**, maior folga que a G4 original tinha a 3x/R$250
[0,2pp]), equity mínima R$993,00 (não censurado por capital), stop mediano
155pts (≥100 — item 6.47 não exige checagem com ticks), pior sequência de
perdas 17 operações (−R$624,50, 62,5% do caixa de partida — maior que
3x/150, mas o Monte Carlo já incorpora isso e ainda devolve `p_ruína=0,2%`
porque a sequência ruim fica intercalada com vitórias suficientes na
distribuição reamostrada).

### OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em
`win_busca_lucro_g17_cross_wdo_capital1000_congelado_v17.py`, rodado UMA VEZ,
quantil causal usando o histórico acumulado IS+OOS-1):

líquido **+R$93,50**, 47 trades, win 23,4% (BEnom 20,0%, BEemp 22,1%, IC95
[13,6;37,2] — **cruza o BEemp, indefinido**), 27/44 pregões com trade (17
sem trade), equity mínima R$811,00 (**não é censura de capital**,
`ordens_recusadas_por_capital=0`). **Concentração top3/líquido = 383%,
top5/líquido = 639%** — PIOR que qualquer geração anterior desta linha
(G4 tinha 240% no OOS-1; esta geração, com capital 4× maior e multiplicador
de alvo maior, piora ainda mais). `p_ruína` (MC, caixa R$1.000, horizonte
130 operações projetado a partir da taxa do OOS-1) = **12,2%** — não baixo,
mas também não alarmante isoladamente; é a concentração que domina o
veredito. Pior sequência 9 operações (−R$283,50). Stop mediano 155pts (≥100,
item 6.47 não exige checagem com ticks).

**Veredito: PASSA O GATE LITERAL (líquido>0, não censurado, veredito≠
NEGATIVO) MAS NÃO "COM FOLGA".** A concentração explode exatamente como a
G4 original — e PIOR, apesar do capital 4× maior e da grade de alvo aberta.
Isto confirma, de forma direta, a suspeita que o mandato desta geração já
levantava: **a concentração é o problema DOMINANTE desta família de sinal,
não a ruína por capital.** Capital maior resolveu o problema que ele podia
resolver (ruína por sequência de perdas: 35,3%→0,3% na comparação isolada
acima) — mas não toca a causa da concentração, que é estrutural ao próprio
gatilho (a confirmação cruzada WIN×WDO dispara em rajadas dentro de poucos
pregões de regime forte, não se espalha uniformemente pelos dias — mesmo
diagnóstico que a G5 já tinha feito para o proxy de amplitude-de-bloco: mais
amostra pode vir de RE-amostrar os mesmos dias bons, não de diversificar).
Por protocolo (`ORQUESTRACAO.md`: só avança ao OOS-2 quem passar o OOS-1 "com
folga"), **OOS-2 NÃO foi rodado** — rodar gastaria a última janela de
validação sobre um candidato que já mostrou o mesmo padrão de fragilidade
das 4 gerações anteriores que chegaram a OOS-1 (G2 n=4, G3 ticks invalidam,
G4 concentração 240%, agora G17 concentração 383%).

**Conversão em % sobre a régua do dono:** R$93,50 em 2 meses sobre R$1.000 =
**9,3% no período, ~4,7%/mês médio** — muito abaixo da régua declarada pelo
dono (R$1.000→R$2.000/mês = 100%/mês), e o número não deve ser lido como
projeção dado que o veredito é "sem folga".

### Resposta à pergunta crítica desta geração (enunciada no próprio mandato)

**Confirmada a suspeita, não refutada.** Capital maior sozinho já derruba a
ruína por sequência de perdas de forma dramática (35,3%→0,3%, mesma
geometria, mesmas 127 operações) — essa parte da porta aberta pelo dono
funciona exatamente como a mecânica preditz. Abrir a grade de alvo também
funciona no eixo que deveria (win% sobe com multiplicador menor), mas não
produz nenhuma célula adicional "POSITIVA" fora do platô 3x-4x que a G4 já
tinha encontrado. O que NENHUMA das duas portas abertas toca é a
concentração temporal do sinal, que é uma propriedade do PRÓPRIO GATILHO
(confirmação cruzada WIN×WDO, estado anômalo raro que se agrupa em rajadas
de regime) — e foi exatamente essa concentração, não a ruína por capital,
que decidiu o OOS-1 desta geração.

### Sizing dinâmico (declarado, não medido a fundo nesta geração)

Por desenho desta geração (1 contrato fixo, para isolar o efeito de
alvo/stop), o motor nunca chegou a abrir um 2º contrato mesmo com
`cash_brl=1.000`/`margin_per_contract_brl=100` configurados no `config_for`
(a estratégia nunca pediu `quantity>1` em `EnterLimit`, e
`contracts_from_capital_operacional` só pode ENCOLHER o que a estratégia
pede, nunca aumentar sozinho — `src/backtest/intraday/machine.py::
_cap_capital_atual`). Medir o efeito de escalar contrato de verdade fica,
como o mandato já antecipava, para a G19 (tamanho de mão graduado).

**Raciocínio para a Geração 18 (ORB da G8):** o padrão que mais se repete
nesta linha de pesquisa inteira (G4, G5, G9, agora G17) é que capital e
geometria são alavancas RESOLVÍVEIS, mas concentração temporal — poucos
pregões de regime forte carregando a maior parte do líquido — não cede a
nenhuma das duas. Antes de repetir o mesmo par de portas (capital R$1.000 +
grade de alvo) sobre o ORB da G8/G13, vale testar explicitamente se o ORB
tem o MESMO modo de falha (G13 já media `p_ruína` a R$250 e encontrou
penhasco — repetir a R$1.000 deve, por este precedente, resolver boa parte
da ruína) ou se a concentração do ORB é estruturalmente menor (o gatilho do
ORB — rompimento da faixa de abertura — acontece uma vez por pregão por
construção, diferente do estado anômalo cruzado que pode disparar em rajada
dentro do mesmo dia): se for menor, o ORB com capital R$1.000 pode ser o
primeiro candidato desta busca inteira a passar o OOS-1 "com folga".

## Geração 18 — ORB (G8/G13) com capital de teste R$1.000 + grade de alvo {2x,2,5x,3x,4x,5x}

**Quem testou:** agente principal (não delegado a subagente filho), 1
disparo. Código em
`src/strategy/daytrade/lab/win_busca_lucro_g18_orb_capital1000.py` (classe
`WinBuscaLucroG18OrbCapital1000`, não registrada, cópia deliberada de
`WinBuscaLucroG08OrbSobrevivencia` com o único contrato alterado: piso de
`alvo_multiplo` relaxado de 3,0x para 2,0x — nunca ≤1x) + versão
**congelada** em `..._congelado_v18.py` + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g18_orb_capital1000/`
(`g18_base.py`, `g18_is_busca.py`, `g18_comparacao_capital.py`, `g18_oos1.py`,
logs `g18_is_busca_stdout.log`, `g18_comparacao_capital_stdout.log`,
`g18_oos1_stdout.log`).

**Mandato (dono, 2026-10-05):** a G17 confirmou que, para o sinal cruzado
WIN×WDO, capital R$1.000 derruba a ruína por sequência de perdas de forma
dramática (35,3%→0,3%, mesma geometria) mas NÃO resolve a concentração
temporal (383% no OOS-1, pior que a R$250) — porque aquele gatilho pode
reentrar em rajada dentro do MESMO pregão favorável. A pergunta desta
geração: o ORB — que dispara no MÁXIMO 1× por pregão por construção, nunca
em rajada — tem o MESMO modo de falha de concentração, ou é estruturalmente
mais robusto nesse eixo específico? Reaproveitada por cópia (mandato
explícito "pode importar"): a detecção de rompimento inteira de G07/G08
(faixa de `range_minutos=5min`, borda fresca, no máximo 1 operação real por
pregão, sempre momentum). Execução fechada idêntica à linha inteira
(`EnterLimit` com `ttl_bars`, alvo fatiado sem prazo, `anchor_exits_at_fill`,
só stop a mercado, `target_fills_as_maker`). 1 contrato FIXO (isola o efeito
de alvo/stop — dimensionamento graduado fica para a G19, mesma decisão da
G17). Fila WIN@ não calibrada (`queue_ahead_qty=0`), premissa otimista
idêntica à linha inteira. Critério de censura com item 6.51 aplicado desde o
desenho (`g18_base.censura_separada`): só o ramo de CAPITAL reprova.

### Grade 2D completa no IS (jan-jun/2026, 122 pregões, capital R$1.000, 1 contrato fixo, range=5min/buffer=20) — 30 células

| alvo×stop_max | líquido R$ | trades | win% | BEnom% | BEemp% | veredito | top3/liq | top5/liq | p_ruína MC | pior_seq |
|---|---|---|---|---|---|---|---|---|---|---|
| 2,0x/100 | +471,50 | 121 | 43,8% | 33,3% | 38,0% | indefinido | 46% | 66% | 0,0% | 9 (−216,50) |
| 2,0x/120 | +578,50 | 121 | 43,0% | 33,3% | 36,8% | indefinido | 37% | 55% | 0,0% | 9 (−242,50) |
| 2,0x/140 | +750,50 | 121 | 43,0% | 33,3% | 35,9% | indefinido | 29% | 44% | 0,0% | 6 (−179,00) |
| 2,0x/160 | +817,50 | 121 | 42,1% | 33,3% | 35,3% | indefinido | 26% | 42% | 0,0% | 5 (−169,50) |
| 2,0x/200 | +1.342,50 | 121 | 43,8% | 33,3% | 34,7% | **POSITIVO** | 18% | 30% | 0,1% | 5 (−235,50) |
| 2,0x/250 | +1.442,50 | 121 | 42,1% | 33,3% | 34,3% | indefinido | 21% | 34% | 0,3% | 7 (−360,50) |
| 2,5x/100 | +529,50 | 121 | 38,8% | 28,6% | 33,1% | indefinido | 41% | 60% | 0,0% | 9 (−216,50) |
| 2,5x/120 | +652,50 | 121 | 38,0% | 28,6% | 31,9% | indefinido | 33% | 51% | 0,0% | 9 (−242,50) |
| 2,5x/140 | +941,50 | 121 | 38,8% | 28,6% | 31,2% | indefinido | 23% | 38% | 0,0% | 6 (−179,00) |
| 2,5x/160 | +1.268,50 | 121 | 39,7% | 28,6% | 30,5% | **POSITIVO** | 19% | 31% | 0,0% | 5 (−167,50) |
| 2,5x/200 | +1.274,50 | 121 | 37,2% | 28,6% | 29,8% | indefinido | 23% | 39% | 0,2% | 7 (−290,50) |
| 2,5x/250 | +1.661,50 | 121 | 37,2% | 28,6% | 29,4% | indefinido | 22% | 37% | 0,5% | 12 (−618,00) |
| 3,0x/100 | +562,50 | 121 | 34,7% | 25,0% | 29,3% | indefinido | 38% | 60% | 0,0% | 9 (−216,50) |
| 3,0x/120 | +877,50 | 121 | 35,5% | 25,0% | 28,3% | indefinido | 25% | 41% | 0,0% | 9 (−242,50) |
| **3,0x/140 (= geometria original G8/G13, VENCEDORA)** | **+1.365,50** | 121 | 37,2% | 25,0% | 27,4% | **POSITIVO** | **18%** | **31%** | **0,0%** | 6 (−179,00) |
| 3,0x/160 | +1.262,50 | 121 | 34,7% | 25,0% | 26,7% | **POSITIVO** | 23% | 38% | 0,1% | 10 (−335,00) |
| 3,0x/200 | +1.369,50 | 121 | 33,1% | 25,0% | 26,1% | indefinido | 26% | 44% | 0,4% | 9 (−373,50) |
| 3,0x/250 | +1.982,50 | 121 | 33,9% | 25,0% | 25,7% | **POSITIVO** | 23% | 38% | 0,9% | 12 (−618,00) |
| 4,0x/100 | +960,50 | 121 | 31,4% | 20,0% | 23,8% | **POSITIVO** | 25% | 41% | 0,0% | 9 (−216,50) |
| 4,0x/120 | +1.060,50 | 121 | 29,8% | 20,0% | 22,7% | indefinido | 27% | 45% | 0,0% | 10 (−260,00) |
| 4,0x/140 | +1.074,50 | 121 | 28,1% | 20,0% | 21,9% | indefinido | 31% | 52% | 0,1% | 18 (−544,00) |
| 4,0x/160 | +1.318,50 | 121 | 28,1% | 20,0% | 21,4% | indefinido | 29% | 48% | 0,2% | 18 (−611,00) |
| 4,0x/200 | +1.562,50 | 121 | 27,3% | 20,0% | 20,9% | indefinido | 31% | 51% | 1,0% | 12 (−498,00) |
| 4,0x/250 | +1.737,50 | 121 | 26,4% | 20,0% | 20,7% | indefinido | 34% | 57% | 3,5% | 12 (−618,00) |
| 5,0x/100 | +752,50 | 121 | 24,8% | 16,7% | 19,8% | indefinido | 40% | 66% | 0,0% | 13 (−308,50) |
| 5,0x/120 | +1.344,50 | 121 | 26,4% | 16,7% | 18,9% | **POSITIVO** | 27% | 44% | 0,0% | 18 (−480,00) |
| 5,0x/140 | +1.688,50 | 121 | 26,4% | 16,7% | 18,3% | **POSITIVO** | 25% | 41% | 0,1% | 18 (−544,00) |
| 5,0x/160 | +1.441,50 | 121 | 24,0% | 16,7% | 17,8% | indefinido | 33% | 55% | 0,6% | 18 (−611,00) |
| 5,0x/200 | +1.436,50 | 121 | 22,3% | 16,7% | 17,4% | indefinido | 42% | 69% | 2,7% | 12 (−498,00) |
| 5,0x/250 | +2.685,50 | 121 | 24,8% | 16,7% | 17,4% | **POSITIVO** | 28% | 46% | 3,0% | 12 (−618,00) |

**O penhasco de G8/G13 desaparece por inteiro.** A R$250, G13 mediu que SÓ
1 de 75 células (técnico) batia o critério composto — todo vizinho de
`stop_max=140`/`alvo=3x` colapsava em censura total de capital
(`stop_max=160` caía de 121 para 5 trades). A R$1.000, **30 de 30 células
desta grade batem o critério composto inteiro** (líquido>0, não censurado
por capital, veredito≠NEGATIVO, `p_ruína`≤20%) — nenhuma célula colapsa,
`stop_max=160` continua com 121 trades intactos. `p_ruína` fica abaixo de
4% em TODA a grade, a maioria abaixo de 1%. **9 das 30 células são
POSITIVO** (IC95 do win% acima do BE empírico) — mais que o dobro da
proporção que G13 achou a R$250 (4/79). Confirma a hipótese central do
mandato: o penhasco de G8/G13 era, de ponta a ponta, um artefato do caixa de
R$250 não aguentar a sequência de perdas que este win%/payoff produz com
regularidade — não uma propriedade da geometria em si.

### Comparação explícita (item 2 do mandato): MESMA geometria vencedora original da G8/G13 (stop_max=140/alvo=3x/buffer=20), capital R$250 × R$1.000

Rodada com a classe ORIGINAL da G8 (import direto, sem alteração nenhuma),
`g18_comparacao_capital.py`:

| capital | trades | líquido R$ | win% | veredito | equity_mín | top3/liq | top5/liq | pior_seq | **p_ruína MC** | ruína (Lundberg) | t_mediano até quebrar |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R$250 (original G8/G13) | 121 | +1.365,50 | 37,2% | POSITIVO | 102,50 | 18% | 31% | 6 (−179,00) | **24,8%** | 30,0% | 9,0 operações |
| R$1.000 (esta geração) | 121 | +1.365,50 | 37,2% | POSITIVO | 852,50 | 18% | 31% | 6 (−179,00) | **0,0%** | 0,1% | 42,0 operações |

**Trades e líquido são BIT A BIT idênticos** (nenhuma ordem foi recusada por
capital em nenhum dos dois capitais nesta janela/geometria — mesmo padrão da
G17: a diferença inteira está na simulação de ruína sobre a MESMA
distribuição de P&L). Resposta direta: **sim, de forma ainda mais dramática
que na G17.** A R$250, 24,8% de `p_ruína` já era o limiar que G13 usava para
aprovar (o próprio penhasco vivia colado no limite de aceitação); a R$1.000
o mesmo cálculo devolve 0,0%. **A concentração (top3/liq=18%, top5/liq=31%)
não muda NADA com o capital** — era esperado: concentração é propriedade da
SÉRIE de P&L, o capital só muda se o caminho de caixa sobrevive para
realizá-la, nunca a distribuição em si.

### Vencedora do IS: `alvo=3,0x`, `stop_max=140pts`, `range=5min`, `buffer=20pts`, capital R$1.000

Escolhida entre as **9 células POSITIVAS** da grade (não pela menor
`p_ruína` bruta isolada — várias células empatam em 0,0% por ruído do Monte
Carlo nessa região quase-nula, o que tornaria o desempate arbitrário) por
critério composto: maior `lucro/DD` da grade inteira (6,28), `p_ruína`
mínima (0,0%), menor concentração entre as 9 POSITIVAS (top3/liq=18%,
empatada com `2,0x/200`; top5/liq=31%) e a MAIOR margem estatística relativa
sobre o breakeven empírico (IC95 inferior 29,1% contra BEemp 27,4% — 1,7pp
de folga, a maior das 9 POSITIVAS; `2,0x/200` tem só 0,6pp). **É a MESMA
geometria que já era o vencedor isolado e cercado de colapso de G8/G13 a
R$250** — a R$1.000 ela continua sendo o melhor ponto da grade, agora no
MEIO de um platô de 30/30 células aprovadas, não mais um pico isolado.

121 trades, 121/122 pregões com trade (mediana 1 trade/pregão operado — o
teto de 1 operação real/pregão por construção do ORB nunca permite
reentrada no mesmo dia, ao contrário do sinal cruzado da G4/G17), win 37,2%
(BEnom 25,0%, BEemp 27,4%, IC95 [29,1%;46,1%] — 1,7pp de folga acima do
BEemp), equity mínima R$852,50 (não censurado por capital), stop mediano
145pts (≥100 — item 6.47 não exige checagem com ticks), pior sequência de
perdas 6 operações (−R$179,00, 17,9% do caixa de partida — a MENOR entre
todas as 9 POSITIVAS), `p_ruína` MC = 0,0%.

**Concentração: top3/liquido=18%, top5/liquido=31% — dramaticamente menor
que os 56%/77% da vencedora da G17.** Confirma a suspeita que motivou esta
geração: o ORB, por disparar no máximo 1×/pregão por construção, de fato
concentra MUITO menos que um sinal que pode reentrar em rajada no mesmo dia
favorável. Este é o primeiro resultado desta busca inteira com concentração
no mesmo patamar de uma estratégia saudável (a referência declarada pelo
mandato, G17 56%/77%, já era considerada "sem folga" — esta vencedora fica
bem abaixo disso).

### OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em
`win_busca_lucro_g18_orb_capital1000_congelado_v18.py`, rodado UMA VEZ):

líquido **−R$541,00**, 42 trades, win **16,7%** (BEnom 25,0%, BEemp 27,8%,
IC95 [8,3%;30,6%] — indefinido, cruza o BEemp), 42/44 pregões com trade
(apenas 2 sem trade — **nenhum sinal de censura por capital**:
`ordens_recusadas_por_capital=0`, `equity_mín=R$357,50`, bem acima da margem
crua R$100). `p_ruína` (MC, caixa R$1.000, 42 operações projetadas) =
**11,2%**. Pior sequência 19 operações (−R$642,50, 64,3% do caixa de
partida). Stop mediano 145pts (≥100, item 6.47 não exige checagem com
ticks). Concentração top3/top5 saem NEGATIVAS (−46%/−77%) porque o líquido
total é negativo — não interpretável como "concentração" no sentido usual,
só registrado por completude.

**Veredito: MORTA — liquido ≤ 0 no OOS-1, e NÃO por censura de capital.**
Esta é a diferença decisiva frente ao histórico da própria família: a G8
já tinha rodado esta EXATA geometria no OOS-1 a R$250 e morrido por
**censura total** (5 trades, as 5 perdedoras, caixa cruza a margem na 3ª
operação, 322 tentativas seguintes recusadas em silêncio pelos 41 pregões
restantes — nunca se soube se o sinal em si era ruim ou só o caixa que
morreu cedo). A R$1.000 o caixa NÃO morre — o motor processa as 44
tentativas (42 viram trade) até o fim da janela — e o que aparece é um
win% genuinamente baixo (16,7%, bem abaixo dos 37,2% do IS e também abaixo
do BE empírico de 27,8%, quase idêntico ao BEemp do IS de 27,4% — ou seja,
o CUSTO não mudou entre as janelas, só a taxa de acerto). **O capital maior
não ressuscitou o candidato — ele serviu exatamente para o que o mandato
pedia: revelar se o modo de falha é capital ou edge, e a resposta aqui é
EDGE.** Por protocolo, OOS-2 **NÃO foi rodado** — o candidato já morreu no
gate literal (líquido≤0), sem nenhuma ambiguidade a resolver com uma janela
adicional.

**Conversão em % sobre a régua do dono:** −R$541,00 em 2 meses sobre
R$1.000 = **−54,1% no período, −27,1%/mês médio** — um resultado muito pior
que o "sem folga mas positivo" da G17 (+9,3%/+4,7% por mês).

### Resposta à pergunta crítica desta geração (enunciada no próprio mandato)

**A concentração temporal do ORB é de fato muito menor que a do sinal
cruzado** (18%/31% contra 56%/77% da G17 no IS; o ORB nunca reentra no
mesmo pregão, por construção, então não herda o modo de falha "rajada
dentro de poucos dias de regime forte" que dominou G4/G5/G9/G17) — a
hipótese central do mandato estava CORRETA nesse eixo específico. Mas essa
vitória não transfere para um candidato vivo: o capital R$1.000 também
resolveu por completo a ruína por sequência de perdas que isolava a
geometria vencedora a R$250 (30/30 células passam o composto no IS, contra
1/75), confirmando a segunda metade do precedente da G17 — e, ao resolver
a ruína, REVELOU (em vez de mascarar) que o edge da família ORB/momentum em
si não sobrevive à janela OOS-1: win% cai de 37,2% para 16,7%, uma queda
que nenhuma quantidade de capital adicional resolve, porque não é um
problema de caixa.

### Sizing dinâmico (declarado, não medido a fundo nesta geração)

Mesma política de G1-G17: 1 contrato FIXO por desenho (isola o efeito de
alvo/stop). `motor.tamanho`/`p_encolhido` nunca pediu mais de 1 contrato em
nenhuma das 30 células da grade do IS (tabela completa no log) — o Kelly
fracionário a R$1.000 concorda que não há base para escalar esta família,
independente do resultado do OOS-1.

**Raciocínio para a Geração 19:** esta geração fecha, com um resultado
negativo limpo (não censurado, não ambíguo), a família ORB/momentum de
sinal único — ela já tinha sido declarada "espaço de parâmetro exaurido" na
síntese da G13, e agora também está refutada no eixo capital/concentração
que a G17 tinha deixado como aberto. Das quatro gerações que já chegaram a
OOS-1 nesta busca inteira (G2 n=4, G3 ticks invalidam, G4/G17 concentração
240%/383%, agora G18 win% colapsa de 37,2% para 16,7% sem qualquer sinal de
censura), NENHUMA jamais teve seu modo de falha resolvido por capital ou
geometria — cada uma morre de uma causa estruturalmente diferente, o que é
evidência (não prova) de que o problema não está em nenhum parâmetro
isolado desta busca. Para a G19 (tamanho de mão graduado, mandato original),
a pista mais concreta é: não repita o par capital-maior/grade-de-alvo sobre
NENHUM sinal desta busca sem antes isolar se o modo de falha observado no
IS é capital (resolvível) ou edge (não resolvível por dinheiro) — a G18
mostrou que são perguntas DIFERENTES e que resolver a primeira pode só
trocar qual das duas decide o veredito, não eliminar as duas.

## Geração 19 — tamanho de mão graduado com CONTRATOS DE VERDADE (R$1.000 permite 1-4), Parte 1 (ORB/força) e Parte 2 (cruzado/magnitude)

**Quem testou:** agente principal (não delegado a subagente filho), 1
disparo. Código em
`src/strategy/daytrade/lab/win_busca_lucro_g19_orb_sizing_graduado.py`
(Parte 1, classe `WinBuscaLucroG19OrbSizingGraduado`) e
`src/strategy/daytrade/lab/win_busca_lucro_g19_cross_wdo_sizing_graduado.py`
(Parte 2, classe `WinBuscaLucroG19CrossWdoSizingGraduado` +
`magnitude_anomalo_cruzado`, não registradas) + harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g19_sizing_graduado/`
(`g19_orb_base.py`, `g19_parte1_orb.py`, `g19_cross_base.py`,
`g19_parte2_cross.py`, logs `g19_parte1_orb_stdout.log`,
`g19_parte2_cross_stdout.log`). Nenhum candidato foi congelado nem chegou a
OOS-1 — os dois diagnósticos pararam no IS por razão honesta (abaixo).

**Mandato:** a R$1.000 cabem de verdade 1 a ~4 contratos
(`contracts_from_capital_operacional`). A G11 (R$250, 1 contrato) só podia
traduzir "tamanho de mão graduado pela força do sinal" como SELEÇÃO binária
(opera/não opera o balde). Esta geração deveria reconfirmar a correlação
força×resultado da G11 com contratos de verdade variando (Parte 1, ORB) e
testar se a MAGNITUDE da anomalia cruzada WIN×WDO — candidata mais
promissora por ser medida de CONVICÇÃO do próprio sinal, não característica
incidental do candle — correlaciona com o resultado (Parte 2).

### Parte 1 — ORB (geometria vencedora da G18: `stop_max=140pts, alvo=3,0x`, capital R$1.000)

Protocolo: REF (flat 1 contrato, idêntica à G18) → cortes de tercil causais
sobre a força das 121 entradas REAIS → estratificação PÓS-HOC (item 6.50,
nunca simulação exclusiva) → sizing Kelly por balde (`motor.tamanho`) ×
FLAT pareado.

**Correlação reconfirmada ≈0, com os MESMOS 121 trades da G11 (R$250 e
R$1.000 dão bit a bit a mesma sequência de trades nesta geometria — zero
ordens recusadas por capital nas duas):**

| balde | n | dias distintos | win% | BEemp% | IC95 | líquido |
|---|---|---|---|---|---|---|
| fraco | 40 | — | 37,5% | 27,0% | [24,2;53,0] | +481,00 |
| médio | 40 | — | 37,5% | 27,5% | [24,2;53,0] | +462,00 |
| forte | 41 | — | 36,6% | 27,7% | [23,6;51,9] | +422,50 |

`corr(força,venceu?)=-0,023`, `corr(força,pnl)=-0,027`, `z(forte×fraco)=-0,09`
— idêntico (como deveria ser, mesmos trades) ao achado original da G11 a
R$250.

**O que a Parte 1 acrescenta que a G11 não podia medir: contratos DE
VERDADE.** Rodando o sizing Kelly fracionário (`motor.tamanho`) por balde a
R$1.000 com o payoff médio realizado desta geometria (ganho médio ~420pts,
perda média ~145pts, p≈37%), **os três baldes devolveram `contratos_kelly=1`**
— o Kelly fracionário (25%, teto de pior caso 25% do caixa) não justifica
mais de 1 contrato em NENHUM balde, nem no "forte". GRADUADO e FLAT pareado
saíram **bit a bit idênticos** (líquido +R$1.365,50, win 37,2%, p_ruína
0,0%, desvio/trade R$55,79 — as duas rodadas, idênticas, porque
`contratos_por_balde=(1,1,1)` nas duas). A predição de Kelly (p constante
entre baldes ⇒ tamanho ótimo é o MESMO) bateu exatamente — graduar o
TAMANHO por uma métrica que não correlaciona com o resultado não criou
nenhuma diferença, nem de esperança nem de variância, porque não havia
tamanho nenhum para variar.

**Achado mecânico adicional (item novo, não previsto no mandato original):**
mesmo ignorando o Kelly, o SISTEMA (não esta geração — `ESCADA_RISCO_
CONTRATO`, ordem do dono 2026-09-18, liga por padrão em `config_for` para
todo futuro com margem configurada) exige caixa ≥ R$1.200 antes de autorizar
um 2º contrato nesta posição — não os R$750 que a margem crua×buffer
sozinha autorizaria. Medido sobre o caminho de equity REAL da REF: **69,4%
das 121 entradas têm equity-antes-do-trade ≥ R$1.200** (equity mínima
R$852,50, máxima R$2.311,50) — ou seja, a escada NÃO bloqueia a maior parte
da janela, mas bloqueia os primeiros ~30% dos trades (antes do caixa
acumular lucro). Uma tentativa de forçar `quantity=2` fixo no harness (não
publicada como resultado — número ficou inconsistente, 4 trades/win 0%,
contagem de recusas por capital que não bate com a fração de 69,4% acima)
expôs uma interação entre pedido de quantidade fixa não-unitária e o teto
por capital que este relatório NÃO caracteriza por completo — fica como
item para uma geração futura que precise de verdade de tamanho >1 contrato
num robô de `quantity` fixa (não `quantity_e_unidade=True`).

**Veredito Parte 1: correlação força×resultado CONTINUA ≈0 com contratos
reais (reconfirma a G11) — graduar tamanho por essa métrica não ajuda nem
atrapalha a esperança, e nesta geometria/capital nem chega a ter tamanho
real para variar (Kelly pede 1 em todo balde).** Sem candidato novo. Não
promovido a OOS-1 — e mesmo que o sizing tivesse mudado algo, a geometria
`stop_max=140/alvo=3x` já morreu no OOS-1 da própria G18 (win% colapsa de
37,2% para 16,7%, líquido −R$541,00) por razão de EDGE, não de capital nem
de sizing — gastar o OOS-1 de novo neste sinal reconfirmaria uma causa já
conhecida.

### Parte 2 — cruzado WIN×WDO (geometria vencedora da G17: `alvo=4,0x, stop=150pts, buffer=30pts`, capital R$1.000)

Nova função pura `magnitude_anomalo_cruzado` (duplica a matemática causal de
`estado_anomalo_cruzado` da G4 e acrescenta `magnitude = min(|delta_WIN|/
limiar_WIN, |delta_WDO|/limiar_WDO)` nos pontos anômalos) — **verificada
byte a byte contra a função original da G4 antes de qualquer backtest**
(`g19_cross_base.computa_estado_com_magnitude`, paridade OK). A classe
NUNCA rejeita um sinal por magnitude (evita o viés do item 6.50) — só
gradua a `quantity` pedida.

REF (flat 1 contrato) reproduziu **exatamente** os números já publicados da
G17 (125 trades, líquido +R$1.698,50, win 31,2%, IC95 [23,7;39,8], top3/liq
56%, top5/liq 77%, equity_min R$993,00) — confirma que a classe nova está
correta antes de olhar a magnitude.

**Estratificação pós-hoc dos 125 trades reais por tercil de magnitude:**

| balde | n | dias distintos | win% | BEemp% | IC95 | líquido |
|---|---|---|---|---|---|---|
| no quantil (magnitude<1,055) | 41 | 35 | 31,7% | 22,0% | [19,6;47,0] | +573,50 |
| moderado (1,055–1,194) | 42 | 34 | 31,0% | 22,9% | [19,1;46,0] | +527,00 |
| muito acima (≥1,194) | 42 | 27 | 31,0% | 21,6% | [19,1;46,0] | +598,00 |

`corr(magnitude,venceu?)=-0,077`, `corr(magnitude,pnl)=-0,064`,
`z(muito_acima×no_quantil)=-0,07` — **critério desta geração para
"correlação real" (`|corr|≥0,15` OU `|z|≥1,96`) NÃO bateu em nenhuma das
duas métricas.** Ao contrário da hipótese do mandato ("medida de CONVICÇÃO
do sinal, candidata mais promissora que a força do ORB"), a magnitude da
anomalia cruzada também não prediz o resultado do trade — win%
praticamente idêntico nos três tercis (31,7%/31,0%/31,0%), dentro do ruído
de amostras de n≈41.

**Achado extra, na direção OPOSTA da esperança do mandato:** o balde
"muito acima" tem **27 dias distintos em 42 trades** (1,56 trades/dia)
contra **35 dias distintos em 41 trades** (1,17 trades/dia) do balde "no
quantil" — os episódios de MAIOR magnitude estão **mais concentrados em
menos pregões**, não mais espalhados. Se a correlação com resultado fosse
real, apostar mais nos episódios de maior magnitude teria PIORADO a
concentração temporal (já o ponto fraco desta família desde a G17, top3/
liq=383% no OOS-1), não melhorado — mais um motivo para não perseguir este
eixo.

**Veredito Parte 2: correlação magnitude×resultado ≈0 — resultado
honesto, nenhuma estratégia de sizing forçada.** Protocolo seguido à risca
(mandato: "se a correlação for ≈0, diga isso claramente e não precisa
forçar uma estratégia de sizing"). Diagnóstico encerrado no IS, nenhum
candidato congelado, OOS-1 NÃO gasto neste sinal (o próprio OOS-1 da G17 já
está consumido para esta geometria/sinal — rodar de novo com sizing que não
muda nada seria relitigar uma pergunta já respondida).

### Síntese — por que NENHUMA das duas partes produziu candidato

A predição matemática do mandato se confirmou nas DUAS famílias testadas
nesta busca: **graduar o TAMANHO de uma aposta por uma métrica que não
correlaciona com o resultado não cria esperança nova — só redistribui
risco, e nesta geração nem chegou a redistribuir, porque o Kelly fracionário
a R$1.000 nunca pediu mais de 1 contrato em nenhum balde de nenhuma das duas
famílias.** Isto fecha, com evidência direta (não só analogia), a pergunta
que ficou aberta desde a G11: "força do rompimento ORB não prediz nada" já
era conhecido; agora "magnitude da anomalia cruzada também não prediz nada"
está medido pela primeira vez, e com o método correto (pós-hoc, nunca
exclusivo). Nenhuma das duas métricas candidatas a "conviçção do sinal"
desta busca sobreviveu ao teste.

**Conversão em % sobre a régua do dono:** não aplicável — nenhum candidato
chegou a OOS-1 (ambas as Partes pararam no diagnóstico do IS, por protocolo:
sizing sem correlação não é candidato a congelar).

**Raciocínio para a Geração 20:** esta geração fecha a pergunta "tamanho
graduado por força/magnitude incidental" para as duas famílias de sinal
desta busca inteira (ORB e cruzado WIN×WDO) — nenhuma tem uma métrica de
"qualidade do sinal" que sobreviva à estratificação pós-hoc. O padrão que
se repete desde a G11 é: toda métrica DERIVADA do próprio evento de entrada
(força do rompimento, magnitude da anomalia) mede quão INCOMUM o gatilho
foi, não quão BOM o trade que se seguiu vai ser — são perguntas diferentes,
e nenhuma das duas famílias desta busca tem um gatilho cuja incomumidade
prediga o resultado. Se a G20 quiser continuar a linha de sizing dinâmico,
a pista é buscar uma métrica EXTERNA ao próprio evento (ex.: regime de
volatilidade do pregão até aquele ponto, ou o próprio capital acumulado via
a escada de risco progressivo do sistema — que este trabalho descobriu
morder 30% da janela mesmo quando NADA no sinal pede mais de 1 contrato),
em vez de insistir em "o quão extremo foi o gatilho" como proxy de
convicção. Alternativamente, visto que das 5 gerações que já chegaram a
OOS-1 nesta busca (G2, G3, G4/G17, G18) nenhuma sobreviveu por uma causa
RESOLVÍVEL (capital, geometria ou sizing), vale reconsiderar se a busca por
um EA lucrativo para o WIN dentro desta família de sinais (ORB e cruzado
WIN×WDO, ambos sobre OHLCV puro do WIN/WDO) já esgotou o espaço razoável de
hipóteses, e se a próxima geração deveria buscar um sinal estruturalmente
DIFERENTE (outra fonte de informação, não outro parâmetro sobre o mesmo
gatilho) em vez de mais uma variação de capital/geometria/sizing sobre ORB
ou cruzado.

## Geração 20 — atacar a concentração do sinal cruzado pela FREQUÊNCIA (baixar o quantil), não pelo tamanho

**Quem testou:** agente principal (não delegado a subagente filho), 1
disparo. Nenhuma classe de estratégia nova — `estado_anomalo_cruzado` (G4)
já aceita `quantil` como parâmetro e `WinBuscaLucroG17CrossWdoCapital1000`
já aceita a grade `alvo_multiplo∈{2x..5x}`/capital R$1.000, então esta
geração é puramente um SWEEP de harness sobre `quantil` (e, nos quantis mais
promissores, cruzado com `alvo_multiplo`). Harness em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g20_quantil_freq/`
(`g20_base.py` reaproveita `g17_base`/`g04_base` por import direto;
`g20_quantil_curva.py`, `g20_alvo_cruzamento.py`, `g20_vencedor_diagnostico.py`,
`g20_oos1.py`, com os respectivos `_stdout.log`). Vencedor do IS congelado em
`src/strategy/daytrade/lab/win_busca_lucro_g20_cross_wdo_freq_congelado_v20.py`
— cópia byte-a-byte da classe de execução da G17, só renomeada
(`WinBuscaLucroG20CrossWdoFreq`), sem nenhuma mudança de comportamento.

**Mandato:** a G19 mostrou que apostar MAIS nos episódios de magnitude maior
piora a concentração (episódios extremos são ainda mais raros/concentrados
no tempo, não menos). Esta geração testa o oposto: baixar o `quantil` que
define "anômalo" para capturar MAIS episódios — inclusive os menos extremos,
que a G19 mostrou estarem mais espalhados no tempo — na esperança de diluir
a concentração ao custo possível de win%/qualidade por trade.

### Passo 1 — curva quantil × frequência × concentração, geometria FIXA (alvo=4x/stop=150, vencedora da G17), IS (jan-jun/2026, 122 pregões)

| quantil | episódios brutos | pregões distintos | líquido R$ | trades | win% | BEemp% | IC95 win% | veredito | top3/liq | top5/liq | p_ruína MC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0,60 | 665 | 100/122 | +1.997,50 | 309 | 26,5% | 22,1% | [21,9;31,7] | indefinido | 47,9% | 73,1% | 4,7% |
| 0,65 | 469 | 93/122 | +1.405,50 | 235 | 25,5% | 21,6% | [20,4;31,5] | indefinido | 58,9% | 92,9% | 4,8% |
| 0,70 | 325 | 82/122 | +1.404,50 | 179 | 26,8% | 21,6% | [20,9;33,7] | indefinido | 61,2% | 95,2% | 2,1% |
| **0,75 (= G17)** | 214 | 72/122 | **+1.698,50** | 125 | 31,2% | 22,2% | [23,7;39,8] | **POSITIVO** | 56,3% | 77,0% | 0,2% |
| 0,80 | 128 | 57/122 | +415,50 | 81 | 25,9% | 22,4% | [17,6;36,4] | indefinido | 163,4% | 220,9% | 2,4% |

Nenhuma célula é censurada (capital ou amostra). A frequência sobe
monotonicamente ao baixar o quantil (episódios brutos 128→665, pregões
distintos 57→100 de 122, trades 81→309) exatamente como esperado — mas o
win% NÃO acompanha: ele é maior em q=0,75 (31,2%) que em qualquer quantil
mais baixo (25,5–26,8%), e o BEemp fica quase constante (~22%) em todos os
quantis ≤0,75 (só sobe para 22,4% em 0,80). Resultado: **só q=0,75
permanece POSITIVO** — baixar o quantil dilui o win% sem abrir margem
estatística equivalente, confirmando parcialmente a suspeita que o próprio
mandato levantou ("diluir win% proporcionalmente à concentração que ganha").
Mas a CONCENTRAÇÃO em si tem um ponto interessante: **q=0,60 é o único
quantil com top3/liq (47,9%) e top5/liq (73,1%) MENORES que a referência
G17 (56,3%/77,0%)** — q=0,65/0,70 na verdade PIORAM a concentração
(58,9%/61,2%), e q=0,80 colapsa (163%/221%, poucos episódios concentram
ainda mais — mesmo padrão da G19). Não é uma curva suave: é um ponto
isolado (q=0,60) cercado de piora.

### Passo 2 — cruzamento quantil × alvo_multiplo (stop=150pts fixo), nos 3 quantis mais informativos (0,60 — melhor concentração; 0,70 — ponto médio; 0,75 — referência/único POSITIVO do passo 1), IS — 15 células

| q × alvo | líquido R$ | trades | win% | BEemp% | IC95 win% | veredito | top3/liq | top5/liq | p_ruína |
|---|---|---|---|---|---|---|---|---|---|
| 0,60/2,0x | +1.310,00 | 346 | 39,6% | 35,5% | [34,6;44,8] | indefinido | 44,9% | 71,5% | 2,9% |
| 0,60/2,5x | +1.465,00 | 332 | 34,9% | 30,8% | [30,0;40,2] | indefinido | 52,4% | 77,5% | 2,9% |
| **0,60/3,0x (VENCEDOR do IS)** | **+2.166,00** | 324 | 32,7% | 27,1% | [27,8;38,0] | **POSITIVO** | **38,5%** | **58,4%** | 1,6% |
| 0,60/4,0x | +1.997,50 | 309 | 26,5% | 22,1% | [21,9;31,7] | indefinido | 47,9% | 73,1% | 4,7% |
| 0,60/5,0x | +1.401,00 | 302 | 21,5% | 18,8% | [17,3;26,5] | indefinido | 64,0% | 101,0% | 14,3% |
| 0,70/2,0x | +416,00 | 194 | 37,6% | 35,3% | [31,1;44,6] | indefinido | 116,7% | 180,2% | 4,5% |
| 0,70/2,5x | +566,00 | 188 | 33,5% | 30,7% | [27,2;40,5] | indefinido | 101,4% | 154,1% | 4,7% |
| 0,70/3,0x | +922,50 | 183 | 31,1% | 27,0% | [24,9;38,2] | indefinido | 64,3% | 103,1% | 2,5% |
| 0,70/4,0x | +1.404,50 | 179 | 26,8% | 21,6% | [20,9;33,7] | indefinido | 61,2% | 95,2% | 2,1% |
| 0,70/5,0x | +194,00 | 176 | 18,8% | 18,1% | [13,7;25,2] | indefinido | 505,9% | 660,1% | 24,9% |
| 0,75/2,0x | +892,00 | 134 | 43,3% | 36,1% | [35,2;51,7] | indefinido | 53,4% | 78,3% | 0,2% |
| 0,75/2,5x | +1.060,00 | 128 | 39,1% | 31,3% | [31,0;47,7] | indefinido | 56,2% | 79,5% | 0,2% |
| 0,75/3,0x | +1.221,50 | 127 | 35,4% | 27,5% | [27,7;44,1] | POSITIVO | 58,6% | 82,8% | 0,3% |
| 0,75/4,0x (= G17) | +1.698,50 | 125 | 31,2% | 22,2% | [23,7;39,8] | POSITIVO | 56,3% | 77,0% | 0,2% |
| 0,75/5,0x | +1.091,50 | 123 | 23,6% | 18,6% | [16,9;31,8] | indefinido | 114,6% | 152,8% | 3,1% |

**Só 1 de 15 células bate o critério composto desta geração** (POSITIVO +
p_ruína≤20% + concentração < referência G17 56,3%/77,0%): **q=0,60 /
alvo=3,0x / stop=150**. É também o MAIOR líquido de toda a grade
(+R$2.166,00, acima dos +R$1.698,50 da G17) e tem a MENOR concentração
(top3/liq=38,5%, top5/liq=58,4%) — uma melhora real sobre a G17 em três eixos
ao mesmo tempo (líquido, win% absoluto e concentração), não uma troca de um
por outro. `q=0,70` não produz nenhuma célula que bata o critério composto
em nenhum alvo testado — confirma que o ganho de concentração não é uma
função suave do quantil, é específico do ponto q=0,60.

### Diagnóstico completo do vencedor do IS: `quantil=0,60`, `alvo=3,0x`, `stop=150pts`, `buffer=30pts`, `janela=20min`, `continuação`, capital R$1.000

324 trades, **95/122 pregões com trade** (só 27 sem trade — contra 62/125
pregões com trade da G17: a frequência mais que dobra a cobertura de
pregões distintos), win 32,7% (BEnom 25,0%, BEemp 27,1%, IC95
[27,8;38,0] — margem de 0,7pp acima do BEemp, menor que o 1,5pp da G17 mas
ainda POSITIVO), equity mínima R$937,00 (não censurado), stop mediano
155pts (≥100 — item 6.47 não exige checagem com ticks), pior sequência de
perdas 10 operações (−R$315,00, 31,5% do caixa de partida), `p_ruína`
(MC)=1,6% (Lundberg 1,8%), `lucro/DD`=3,72. **top3/liquido=38,5%,
top5/liquido=58,4% — dramaticamente menor que os 56,3%/77,0% da G17.**
Retorno IS: +216,6% sobre R$1.000 em 6 meses (36,1%/mês médio) — mas isto é
IS, não é previsão.

### OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em `win_busca_lucro_g20_cross_wdo_freq_congelado_v20.py`, rodado UMA VEZ, quantil causal com o histórico acumulado IS+OOS-1)

líquido **+R$101,50**, 115 trades, win **27,8%** (BEnom 25,0%, BEemp 27,1%,
IC95 [20,5;36,6] — **cruza o BEemp, indefinido**), **41/44 pregões com
trade** (só 3 sem trade — a frequência alta se confirma fora da amostra:
episódios brutos=234, pregões distintos com episódio=43/44), equity mínima
R$858,00 (**não é censura de capital**, `ordens_recusadas_por_capital=0`).
`p_ruína` (MC, caixa R$1.000, 319 operações projetadas) = **26,5%** — bem
acima do IS (1,6%) e acima do limiar de 20% usado como "com folga". Pior
sequência 9 operações (−R$343,50). Stop mediano 155pts (≥100, item 6.47 não
exige checagem com ticks).

**A concentração — exatamente o eixo que esta geração tentava melhorar —
PIORA no OOS-1: top3/liquido=467%, top5/liquido=696%, PIOR que os 383%/639%
da própria G17** (que tinha concentração alta justamente por reentrar em
rajada; esta geração reentra MAIS vezes ainda, e isso não distribuiu o
líquido por mais dias de regime forte — concentrou ele em menos). A melhora
de concentração observada no IS (38,5%/58,4%, a menor de toda a busca) **não
sobreviveu à janela seguinte** — inverteu de sinal, de "melhor que a G17"
para "pior que a G17".

**Veredito: PASSA O GATE LITERAL (líquido>0, não censurado) MAS NÃO "COM
FOLGA".** Nem pelo critério do próprio mandato desta geração (concentração
menor que a G17) nem pelo critério geral de folga (p_ruína≤20%). Por
protocolo, **OOS-2 NÃO foi rodado** — a mesma regra que impediu G4/G17/G18
de gastar a última janela sobre um candidato já mostrando fragilidade.

**Conversão em % sobre a régua do dono:** R$101,50 em 2 meses sobre R$1.000
= **10,2% no período, ~5,1%/mês médio** — na mesma faixa (ligeiramente
melhor) que o +9,3%/+4,7% da G17, mas com o MESMO veredito final ("sem
folga") e uma concentração pior, não melhor.

### Existe um ponto de equilíbrio melhor que q=0,75/alvo=4x da G17?

**No IS, sim, aparentemente** (q=0,60/alvo=3x batia líquido, win% e
concentração da G17 ao mesmo tempo). **No OOS-1, não** — a melhora de
concentração inverteu de sinal. A leitura honesta: o IS mediu uma
REDISTRIBUIÇÃO de quais pregões carregam o líquido, não uma mudança
estrutural na causa da concentração. Baixar o quantil aumenta quantos dias
têm pelo menos 1 episódio (95/122 no IS, 41/44 no OOS-1 — isso É real e se
confirma fora da amostra), mas **não garante que o LÍQUIDO desses episódios
adicionais se distribua uniformemente** — no OOS-1, a maior parte do
líquido ainda veio de poucos dias, e com mais trades no total (115 contra os
47 da G17 no mesmo OOS-1), a concentração relativa pôde piorar mesmo com
mais dias "tocados". Mais frequência espalhou a COBERTURA (quantos pregões
têm pelo menos 1 trade), não o LÍQUIDO — e é o líquido, não a cobertura, que
a métrica top3/top5 mede.

### Resposta à pergunta crítica desta geração (enunciada no próprio mandato)

**Nem confirmada nem puramente refutada — refutada na parte que importava.**
A hipótese "baixar o quantil aumenta a frequência" é verdadeira e mensurável
nas duas janelas (IS e OOS-1). A hipótese "mais frequência dilui a
concentração" só se confirmou no IS, e por uma margem que não sobreviveu à
validação — no OOS-1 a concentração piorou, não melhorou. Isto é consistente
com a segunda hipótese alternativa que o próprio mandato desta geração já
havia levantado como possível resultado honesto: **a concentração é uma
propriedade mais profunda do mercado — dias de regime forte são
genuinamente raros e concentram a maior parte de QUALQUER sinal de
"movimento forte conjunto" entre WIN e WDO, e nenhum quantil testado (nem
mais alto, G17/G18, nem mais baixo, esta geração) resolve isso.** Frequência
e magnitude (G19) já foram testadas como alavancas de dissolver a
concentração — nenhuma das duas funciona fora da amostra.

### Sizing dinâmico

Não testado nesta geração (mandato era quantil/frequência, não tamanho —
G19 já fechou essa pergunta para esta família de sinal nas duas métricas
candidatas, força e magnitude).

**Raciocínio para a Geração 21:** com esta geração, as TRÊS alavancas
previstas pelo mandato original para atacar a concentração do sinal cruzado
WIN×WDO — capital (G17), tamanho graduado por força/magnitude (G19) e agora
frequência via quantil mais baixo (G20) — foram testadas e **nenhuma
resolve a concentração fora da amostra**; a G20 chegou a melhorar os três
eixos simultaneamente no IS (líquido, win%, concentração), o que a tornava a
candidata mais forte desta busca inteira até aqui, e mesmo assim a
concentração inverteu de sinal no OOS-1. Isto é evidência direta (não mais
analogia) de que a concentração do sinal cruzado é estrutural ao PRÓPRIO
GATILHO (confirmação de estado anômalo simultâneo WIN×WDO) e não a um
parâmetro ajustável dele. Combinado com o veredito já fechado do ORB (G8/
G18: win% não sobrevive ao OOS-1 por razão de EDGE, não de capital nem
concentração), **as duas famílias de sinal desta busca inteira — ORB e
cruzado WIN×WDO, ambas sobre OHLCV puro do WIN/WDO — têm agora cada uma sua
causa de morte testada e não resolvida por nenhuma alavanca de capital,
geometria, sizing ou frequência disponível dentro da própria família.** A
recomendação deste relatório para a G21 é a mesma que a síntese da G19 já
apontava: ou declarar esta linha de busca (OHLCV puro WIN/WDO, sinais
técnicos e de confirmação cruzada) esgotada dentro do mandato de capital
R$1.000/grade de alvo, ou buscar uma fonte de informação estruturalmente
DIFERENTE (não mais um parâmetro novo sobre o mesmo gatilho) antes de gastar
mais uma geração nesta família.

## Geração 21 — reabertura do retângulo (G16) sob o novo mandato: capital R$1.000 e piso de múltiplo 2× (em vez de 3×)

**Quem testou:** agente principal (não delegado a subagente filho), 1
disparo. Classe nova `WinBuscaLucroG21Retangulo1000` em
`src/strategy/daytrade/lab/win_busca_lucro_g21_retangulo_1000.py` — cópia da
estrutura da G16 (`WinBuscaLucroG16Retangulo250`), reaproveitando
`detecta_retangulo`/`MARGEM_MORTE`/`BARRAS_MORTE`/`LARGURA_MINIMA_TICKS` de
`win_retangulo.py` por import direto, sem reimplementar detecção. A única
mudança de comportamento é o piso do construtor:
`alvo_fracao_largura >= 2,0 × stop_fracao_largura` (G16 exigia 3,0×). Versão
congelada em `..._congelado_v21.py` (byte-a-byte, usada só no OOS-1). Harness
em `scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g21_retangulo_1000/`
(`g21_base.py`, `g21_is_busca.py` + `_stdout.log`, `g21_oos1.py` + `_stdout.log`).

**Por que esta geração existe:** a G16 (ANTES da mudança de mandato,
capital R$250, `alvo≥3×stop` obrigatório) testou a MESMA ideia — redesenhar
a geometria de entrada/saída do `WinRetangulo` de produção (stop
0,50×largura/alvo 0,80×largura, razão 1,6:1, win%~45%, piso R$1.100) para
caber no mandato antigo — e morreu de forma mecanicista: 18 de 18 células
(`stop_fracao∈{0,15..0,50}`×`alvo_mult∈{3x,4x,5x}`) negativas e censuradas.
O raciocínio não testado até aqui: o stop de produção (0,50×largura, EXATAMENTE
na borda oposta) não é arbitrário — é o único ponto onde o stop fica FORA da
banda de ruído que o próprio padrão de retângulo usa para se qualificar como
retângulo (contenção ≥95% com banda q90/q10, tolerância 0,20×largura de
"toque" na borda). Forçar `alvo≥3×stop` obrigava apertar o stop para DENTRO
da banda (varrido por ruído antes de reverter) ou esticar o alvo bem além do
alcance histórico do padrão. O mandato de 2026-10-05 (capital R$1.000, piso
de múltiplo caindo para 2×) permite, pela primeira vez, testar um par onde o
stop fica em 0,45-0,50×largura (perto ou igual à borda de produção) com um
múltiplo de alvo que ainda respeita a disciplina do dono.

**Capital e execução:** R$1.000,00 real (mandato, substitui R$250 da G16), 1
contrato fixo — escolha DECLARADA (a G19 desta busca mediu que o Kelly
fracionário a R$1.000 nunca pediu mais de 1 contrato em duas famílias de
sinal diferentes, mas isso não foi medido para esta geometria; nenhuma
lógica de `_dimensiona()` foi adicionada). Execução fechada idêntica à linha
inteira: `EnterLimit` com `ttl_barras=10`, alvo só como ordem-limite real
fatiada (`target_fills_as_maker=True`), âncora no preço de fill
(`anchor_exits_at_fill=True`), só o stop a mercado. Fila WIN@ zero nos dois
lados (não calibrada, premissa otimista declarada, mesmo precedente de
G1-G20). `janela_barras=20`, `tolerancia_borda=0,20`, `largura_minima_pontos
=328` herdados do `WinRetangulo` sem retune — idêntico à G16, esta geração
testa só a geometria de entrada/saída.

### Grade IS (jan-jun/2026, 122 pregões) — 15 células, `stop_fracao_largura`∈{0,30;0,35;0,40;0,45;0,50} × `alvo_multiplo`∈{2,0;2,5;3,0}

Nenhuma célula censurada por capital (`censura_capital=False` nas 15,
`sem_trade=9/122` idêntico — o portão de capital nunca disparou, a detecção
é quem decide quando o robô opera, não o caixa).

| stop×L | alvo×L (mult) | líquido R$ | n | win% | BEemp% | IC95 win% | veredito | p_ruína | top3/liq | top5/liq | pior_seq | stop med. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0,30 | 0,60 (2,0x) | 550,00 | 830 | 36,1 | 35,3 | [32,9;39,5] | indefinido | 12,3% | 176% | 279% | 13 (−348,50) | 130pts |
| 0,30 | 0,75 (2,5x) | 968,00 | 780 | 31,7 | 30,3 | [28,5;35,0] | indefinido | 11,3% | 109% | 166% | 16 (−445,00) | 130pts |
| 0,30 | 0,90 (3,0x) | 977,50 | 745 | 27,5 | 26,3 | [24,4;30,8] | indefinido | 14,3% | 99% | 159% | 16 (−445,00) | 130pts |
| 0,35 | 0,70 (2,0x) | 1.251,00 | 722 | 36,8 | 35,0 | [33,4;40,4] | indefinido | 9,0% | 82% | 128% | 11 (−348,50) | 150pts |
| 0,35 | 0,88 (2,5x) | 1.808,50 | 679 | 32,4 | 30,0 | [29,0;36,0] | indefinido | 8,8% | 59% | 93% | 14 (−458,00) | 150pts |
| 0,35 | 1,05 (3,0x) | 1.941,00 | 648 | 28,5 | 26,1 | [25,2;32,1] | indefinido | 10,3% | 56% | 89% | 14 (−458,00) | 150pts |
| 0,40 | 0,80 (2,0x) | 2.237,00 | 638 | 38,1 | 34,8 | [34,4;41,9] | indefinido | 5,5% | 54% | 80% | 13 (−475,50) | 170pts |
| 0,40 | 1,00 (2,5x) | 2.199,00 | 590 | 32,5 | 29,6 | [28,9;36,4] | indefinido | 8,5% | 47% | 75% | 15 (−592,50) | 170pts |
| 0,40 | 1,20 (3,0x) | 1.874,00 | 566 | 28,6 | 26,3 | [25,1;32,5] | indefinido | 12,7% | 66% | 102% | 23 (−828,50) | 170pts |
| **0,45** | **0,90 (2,0x)** | **2.790,00** | 562 | 37,9 | 33,8 | [34,0;42,0] | **POSITIVO** | **5,1%** | **41%** | **64%** | 13 (−521,50) | 190pts |
| 0,45 | 1,12 (2,5x) | 2.597,50 | 525 | 32,6 | 29,1 | [28,7;36,7] | indefinido | 8,5% | 51% | 78% | 23 (−914,50) | 190pts |
| 0,45 | 1,35 (3,0x) | 2.365,50 | 503 | 28,6 | 25,7 | [24,9;32,7] | indefinido | 13,4% | 60% | 89% | 23 (−914,50) | 190pts |
| 0,50 | 1,00 (2,0x) | 3.017,00 | 512 | 37,9 | 33,5 | [33,8;42,2] | POSITIVO | 5,8% | 41% | 62% | 19 (−849,50) | 210pts |
| 0,50 | 1,25 (2,5x) | 2.376,00 | 480 | 32,3 | 29,1 | [28,3;36,6] | indefinido | 12,5% | 58% | 85% | 21 (−922,50) | 210pts |
| 0,50 | 1,50 (3,0x) | 2.211,00 | 452 | 28,3 | 25,6 | [24,4;32,6] | indefinido | 16,2% | 68% | 98% | 21 (−922,50) | 210pts |

**15 de 15 células batem o critério literal do portão** (líquido>0, não
censurado, veredito≠NEGATIVO, p_ruína≤25%) — contra **0 de 18 na G16**. Esta
é a diferença central desta geração: não é uma célula isolada que escapou do
nulo, é a grade INTEIRA que virou de sinal.

### Existe platô, e ele confirma o raciocínio mecanicista — não é um pico isolado

Em TODA faixa de `stop_fracao` (0,30→0,50) com `alvo_multiplo=2,0x`, o
líquido sobe monotonicamente (550→1.251→2.237→2.790→3.017) e a concentração
MELHORA monotonicamente (top3/liq: 176%→82%→54%→41%→41%; top5/liq:
279%→128%→80%→64%→62%). As duas células com veredito POSITIVO
(stop=0,45 e stop=0,50, ambas com mult=2,0x) são vizinhas, não um pico
isolado cercado de ruído — é exatamente o padrão "platô" que a G16 nunca
teve (lá, TODA a grade era negativa e censurada). O eixo do múltiplo
confirma o mesmo sentido: em qualquer `stop_fracao` fixo, `mult=2,0x` é
sempre melhor que `mult=2,5x`/`3,0x` em líquido, win% e concentração — nunca
o contrário.

Isto fecha, com evidência direta (não mais hipótese), o raciocínio
mecanicista da G16: **o stop precisa estar perto ou na própria borda do
retângulo (fora da banda de ruído de ±0,20×largura que define "toque") para
que o win% suba acima do breakeven com concentração saudável.** Em
`stop_fracao=0,30` (bem dentro da banda — a tolerância de toque já cobre até
0,20×largura, então 0,30 está só 0,10×largura além dela) o stop é varrido
por ruído de qualificação do próprio retângulo com frequência alta — win%
cai para perto do BE e o líquido positivo pequeno (R$550-978) vem de poucos
dias que escaparam da variância (top3/liq de 99% a 176%, pior que QUALQUER
célula da G16 original em termos de qualidade de sinal, mesmo sendo
numericamente positiva). Em `stop_fracao=0,45-0,50` (na borda ou a 1 tick
dela) o stop para de ser varrido pelo próprio ruído de qualificação, e o
win% sobe o bastante para ficar acima do BE empírico com folga real.

**Resposta à autocrítica do mandato desta geração ("é possível que mesmo a
2× o stop ainda caia dentro da banda de ruído"):** parcialmente confirmada,
mas só para `stop_fracao≤0,35` — ali o veredito nunca sai de "indefinido" e a
concentração é ruim. A partir de `stop_fracao=0,40` o quadro muda: mesmo
"indefinido" nessa linha (0,40/mult=2,0x: IC95 [34,4;41,9] contra BE 34,8 —
cruza por 0,4pp) já tem concentração saudável (54%/80%). E em 0,45-0,50 o
veredito vira POSITIVO de verdade. A resposta honesta é: **2× resolve o
impasse mecanicista da G16, mas só na combinação com stop_fracao≥0,40-0,45**
— 2× sozinho, com stop raso (0,30), ainda cai na banda de ruído e produz o
mesmo tipo de resultado frágil (positivo por acaso, concentração ruim) que
caracterizava toda a G16.

### Vencedor do IS: `stop_fracao_largura=0,45`, `alvo_multiplo=2,0x` (`alvo_fracao_largura=0,90`)

Escolhido entre as 2 células POSITIVO (0,45 e 0,50, ambas mult=2,0x) pelo
menor `p_ruína` (5,1% contra 5,8%) e menor pior sequência de perdas em R$
(13 operações / −R$521,50, contra 19 / −R$849,50 em 0,50 — quase 85% do
caixa de partida de R$1.000 numa sequência só). `stop=0,50` tem líquido
nominalmente maior (R$3.017,00 contra R$2.790,00) e concentração empatada
(41%/62% contra 41%/64%), mas a sequência de perdas mais curta e mais barata
de 0,45 pesou mais na escolha — ruína, não líquido, é o critério de
sobrevivência desta busca. **Limitação declarada: `stop=0,50/mult=2,0x` NÃO
foi testado no OOS-1** (só um candidato é promovido por protocolo, para não
gastar a janela de validação em múltiplos testes) — fica registrado como
segunda melhor aposta para uma G22 que queira revisitar esta família.

Líquido R$2.790,00, 562 trades, **113 de 122 pregões com pelo menos 1 trade**
(sem_trade=9/122 — cobertura muito maior que qualquer família testada em
G1-G20 desta busca, na mesma ordem de grandeza do `WinRetangulo` de
produção, 615 trades/129 pregões), win 37,9% (BEnom 33,3%, BEemp 33,8%, IC95
[34,0;42,0] — POSITIVO, piso 0,2pp acima do BEemp), p_ruína (MC, caixa
R$1.000→R$100)=5,1%, top3/liq=41%, top5/liq=64% (a melhor concentração de
toda a grade, empatada com 0,50), pior sequência 13 operações (−R$521,50,
52,2% do caixa de partida), stop mediano **190 pontos** — acima do piso de
100pts do item 6.47, **não exigiu checagem com ticks reais**. Retorno IS:
+279,0% sobre R$1.000 em 6 meses — não é previsão, é IS.

**Ressalva de método que não deve ser escondida:** o vencedor saiu de uma
busca em 15 células sobre o mesmo IS que decidiu o vencedor — não é teste
cego. A diferença para o garimpo clássico desta busca (G3/G4, "ótimo na
borda do espaço testado") é que aqui o "ótimo" está no MEIO da região
saudável (0,45 de uma faixa testada até 0,50, não o extremo) e cercado de
vizinhos concordantes em sinal e magnitude — mais parecido com o platô do
`WinRetangulo` de produção (39 de 42 células positivas) do que com qualquer
vencedor anterior desta busca específica.

### OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em `win_busca_lucro_g21_retangulo_1000_congelado_v21.py`, rodado UMA VEZ)

Líquido **+R$650,00**, 98 trades, **31 de 44 pregões com trade**
(sem_trade=13/44), win **39,8%** (BEemp 34,0%, IC95 [30,7;49,7] — **cruza o
BEemp por 3,3pp, indefinido**), equity mínima R$966,50 (**não é censura de
capital**, `ordens_recusadas_por_capital=0`), p_ruína (MC, 98 operações
projetadas)=**0,7%** (ruína_fórmula=2,4%), pior sequência 9 operações
(−R$373,50), stop mediano **185 pontos** (≥100, item 6.47 não exige
checagem com ticks).

**A concentração — justamente o eixo mais saudável do IS — PIORA
dramaticamente: top3/liquido=97,2%, top5/liquido=133,4%**, contra 41%/64% no
IS. Top5>100% significa que os 5 melhores pregões somam MAIS que o líquido
total — os ~26 pregões restantes com trade, somados, são NEGATIVOS. Este é
o MESMO padrão que já apareceu em G4 (59%→240%) e G20 (38,5%/58,4%→467%/
696%): concentração saudável no IS que não sobrevive à janela seguinte.

**Veredito: PASSA O GATE LITERAL (líquido>0, não censurado) MAS NÃO "COM
FOLGA".** Nem o IC95 do win% fecha longe do breakeven (cruza por 3,3pp,
indefinido) nem a concentração se mantém (97%/133%, pior que QUALQUER
célula da própria grade IS desta geração, inclusive as piores como
stop=0,30). Por protocolo, **OOS-2 NÃO foi rodado** — mesma regra que
impediu G4/G17/G18/G20 de gastar a última janela sobre um candidato já
mostrando fragilidade.

**Conversão em % sobre a régua do dono:** R$650,00 em 2 meses sobre
R$1.000 = **65,0% no período, ~32,5%/mês médio** — o maior número desta
busca inteira em termos de % absoluto, mas não deve ser lido como projeção:
a mesma reserva que vale para G4/G17/G20 vale aqui, e o 32,5%/mês ainda fica
abaixo da régua de "bom" do dono (R$1.000→R$2.000/mês = 100%/mês).

### Resposta às perguntas do mandato

1. **Existe região viável que a G16 não tinha (0/18)**: sim — 15 de 15
   células desta grade passam o portão literal, e a região `stop_fracao∈
   [0,40;0,50]`×`alvo_multiplo=2,0x` tem veredito POSITIVO com concentração
   saudável, não só líquido positivo por acaso. Isto fecha o raciocínio
   mecanicista da G16: o stop cabe fora da banda de ruído do padrão quando
   fica perto da borda (0,45-0,50×largura) E o múltiplo de alvo é o mais
   baixo permitido pelo novo piso do mandato (2,0x, o mais próximo possível
   da razão real de produção 1,6:1). Em `stop_fracao≤0,35` o stop ainda cai
   dentro da banda e o resultado volta a ter a qualidade frágil (concentração
   ruim) que caracterizava toda a G16.
2. **O vencedor NÃO validou fora da amostra** — passa o gate literal do
   OOS-1 mas falha nos dois critérios de folga (IC95 indefinido,
   concentração pior que qualquer célula já medida nesta geração). O mesmo
   padrão de fragilidade que já matou G4/G17/G18/G20 (líquido positivo nas
   duas janelas, concentração que piora em vez de melhorar, IC que não fecha
   longe do breakeven) reaparece aqui, numa família de sinal estruturalmente
   diferente (retângulo/lateralização, não ORB nem confirmação cruzada).

**Sizing dinâmico:** não testado — protocolo exige OOS-1 "com folga" antes
de sizing, e este resultado não bateu esse critério.

**Veredito final honesto: NÃO VALIDADA, mas com um achado de método
positivo que fecha definitivamente a pergunta da G16.** Diferente de G1-G3
(gatilho raro demais) e de G4/G17/G18/G20 (gatilho replica mas concentração
estrutural ao próprio evento), esta geração confirma que a geometria de
retângulo PODE produzir um platô saudável no IS sob o mandato novo — a
barreira mecanicista da G16 (alvo≥3× força o stop para dentro da banda de
ruído) está resolvida. O que NÃO está resolvido, e é o MESMO problema que
atravessa toda a busca desde a G4, é que nenhuma família de sinal testada
até aqui (ORB, cruzado WIN×WDO, agora retângulo) mantém a qualidade
estatística ou a distribuição temporal do líquido ao atravessar para a
janela seguinte — só o modo de falha muda (gatilho raro, concentração no
cruzado, concentração no retângulo), o resultado final não.

**Raciocínio para a Geração 22:** com G21, agora são **três** famílias de
sinal estruturalmente diferentes (ORB, confirmação cruzada WIN×WDO,
retângulo/lateralização) testadas sob o mandato novo de capital R$1.000/
grade de alvo 2×-5×, e as três convergem para o MESMO modo de falha no
OOS-1: líquido positivo sobrevive, mas a CONCENTRAÇÃO (quantos pregões
carregam o resultado) sempre piora da janela de desenvolvimento para a de
validação — nunca o contrário, em nenhuma das 3 famílias, em nenhuma das 5
tentativas que chegaram a OOS-1 nesta busca inteira (G2/G3 nem chegaram por
outro motivo; G4, G17/G18, G20, G21). Isto é evidência acumulada, não mais
sugestão, de que o problema não está em nenhum parâmetro de geometria,
capital ou detecção testado até aqui — é algo sobre COMO o líquido de
qualquer sinal de day trade do WIN se distribui no tempo (poucos dias de
regime favorável carregam a maior parte do resultado, e QUAL dia é
favorável muda entre janelas de forma que nenhuma métrica pós-hoc testada
nesta busca conseguiu prever). A recomendação honesta para a G22 é a mesma
que a síntese da G20 já apontava e que esta geração reforça com uma terceira
família independente: ou (a) declarar esta busca encerrada dentro do espaço
de hipóteses já testado (geometria/capital/sizing/frequência sobre sinais de
OHLCV puro do WIN/WDO), ou (b) atacar DIRETAMENTE a concentração como o
problema central — por exemplo, medindo se existe algum proxy observável
ANTES do fato (não derivado do próprio evento de entrada, que a G19 já
refutou) que prediga se um PREGÃO INTEIRO vai ser de regime favorável para
qualquer uma dessas famílias, em vez de continuar testando variações de
geometria sobre o mesmo tipo de gatilho.

## Geração 22 — existe proxy diário que preveja "pregão bom" para o retângulo? (resposta: um sim no IS, que não sobrevive ao OOS-1)

**Quem testou:** agente principal (não delegado a subagente filho), 1
disparo. Nenhuma geometria nova — reusa a vencedora do IS da G21
(`stop_fracao_largura=0,45`, `alvo_multiplo=2,0x`, capital R$1.000) por
import direto. Código em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g22_proxy_dia/`
(`g22_base.py`, `g22_is_estratificacao.py` + `_stdout.log`,
`g22_candidato_filtro_amplitude.py` + `_stdout.log`, `g22_is_confirmacao.py`
+ `_stdout.log`, `g22_oos1.py` + `_stdout.log`). Classe final em
`src/strategy/daytrade/lab/win_busca_lucro_g22_retangulo_filtro_amplitude.py`
(`WinBuscaLucroG22RetanguloFiltroAmplitude`, subclasse de
`WinBuscaLucroG21Retangulo1000` — nenhuma lógica de detecção/geometria
reimplementada, só um filtro de PREGÃO sobreposto via `on_session_start`/
`on_bar`) + versão **congelada** em `..._congelado_v22.py` (importa a
classe-mãe do próprio `_congelado_v21`, não do módulo "vivo" da G21, para
imunizar o OOS-1 contra qualquer edição futura do arquivo de
desenvolvimento).

**Mandato (raciocínio da G21):** três famílias de sinal estruturalmente
diferentes (ORB, confirmação cruzada WIN×WDO, retângulo) convergiram para o
MESMO modo de falha no OOS-1 — líquido positivo sobrevive, mas a
CONCENTRAÇÃO (top3/top5 pregões ÷ líquido) sempre piora da janela de
desenvolvimento para a de validação. A pergunta desta geração: existe algum
proxy observável ANTES do pregão (ou nos primeiros minutos dele, nunca
derivado do próprio evento de entrada) que preveja se aquele PREGÃO INTEIRO
vai ser de regime favorável para o retângulo da G21, permitindo um filtro de
dia que reduza a dependência de poucos pregões sem mudar a geometria?

### Método: estratificação PÓS-HOC, nunca simulações exclusivas (item 6.50)

A G21 vencedora rodou **uma única vez** sobre o IS (jan-jun/2026, 122
pregões, 562 trades, líquido já registrado +R$2.790,00/win 37,9%/top3=41%/
top5=64%/p_ruína=5,1%), sem filtro de dia nenhum. Quatro proxies diários
CAUSAIS foram calculados por pregão e só DEPOIS usados para particionar os
MESMOS 562 trades já ocorridos:

- (a) `amplitude_ontem` — high-low do pregão ANTERIOR do WIN@ (3 tercis)
- (b) `gap_abertura` — |abertura hoje − fechamento ontem| do WIN@ (3 tercis)
- (c) `dia_semana` — segunda/sexta vs terça-quinta (2 grupos)
- (d) `wdo_range_abertura` — high-low dos 1os 30min do WDO@ no mesmo dia (3
  tercis; WIN@/WDO@ abrem juntos às 09:00, e o 1º trade possível do
  retângulo exige 60 barras acumuladas, ~10:00 — 30min é causal em relação
  a ele)

A unidade de análise é o PREGÃO, não o trade (item 6.49 — mais trades não é
mais amostra independente quando o gatilho pode reentrar várias vezes no
mesmo dia): a significância de cada proxy foi testada por permutação sobre
a série DIÁRIA de líquido (zeros incluídos nos dias sem trade), embaralhando
o rótulo de grupo entre os dias com os TAMANHOS de grupo fixos.

### Resultado da estratificação no IS — tabela por proxy (`g22_is_estratificacao.py`)

| proxy | grupo | dias | R$/pregão | win% | BEemp% | IC95 | veredito | p (permutação) |
|---|---|---|---|---|---|---|---|---|
| (a) amplitude_ontem | baixo (<2.558pts) | 41 | −14,93 | 30,2 | 34,4 | [22,8;38,7] | indefinido | — |
| | médio [2.558;3.680] | 41 | +17,37 | 36,8 | 33,7 | [30,3;43,9] | indefinido | — |
| | **alto (>3.680pts)** | 40 | **+67,25** | **42,7** | 33,8 | [36,7;48,9] | **POSITIVO** | **0,0040** |
| (b) gap_abertura | baixo (<308pts) | 41 | +4,65 | 34,3 | 33,1 | [26,9;42,6] | indefinido | — |
| | médio [308;807] | 40 | +3,52 | 33,3 | 32,7 | [26,9;40,5] | indefinido | — |
| | alto (>807pts) | 41 | +59,96 | 43,3 | 34,9 | [37,2;49,5] | POSITIVO | 0,0912 |
| (c) dia_semana | seg/sex | 49 | +22,95 | 39,2 | 34,8 | [32,9;46,0] | indefinido | — |
| | ter-qui | 73 | +22,82 | 37,1 | 33,2 | [32,2;42,3] | indefinido | 0,9974 |
| (d) wdo_range_abertura | baixo/médio/alto | 41/41/40 | +10,18/+30,39/+28,16 | 38,1/38,5/37,4 | — | — | indefinido (3/3) | 0,7386 |

**Só o proxy (a) separou de forma real.** É monotônico nos 3 tercis, sem
reversão (R$/pregão sobe −14,93 → +17,37 → +67,25), e o teste de permutação
sobre a série diária rejeita a hipótese de que a partição é arbitrária com
**p=0,0040** — a menor probabilidade de acaso de qualquer proxy testado
nesta geração ou em qualquer estratificação anterior da busca. O proxy (b)
tem a mesma direção (dias de gap alto também saem melhor) mas não passa de
"sugestivo" (p=0,09) — plausivelmente correlacionado com (a), já que um
pregão anterior de amplitude alta tende a fechar longe da abertura seguinte.
Os proxies (c) e (d) **não separam nada** — consistente com o histórico do
projeto (`REGRAS.md` já tinha refutado dia-da-semana e gap em outros
contextos) e com a previsão do próprio mandato desta geração.

### Candidato final: excluir o tercio de pior amplitude (`g22_candidato_filtro_amplitude.py`)

Dois filtros com limiar CONGELADO (número absoluto em pontos, nunca
recalculado) foram comparados contra a referência G21 sem filtro
(liquido=R$2.790,00, top3=41%, top5=64%, p_ruína=5,1%):

| candidato | dias elegíveis (IS) | liquido | win% | IC95 | veredito | top3/liq | top5/liq | p_ruína | pior_seq |
|---|---|---|---|---|---|---|---|---|---|
| só tercio alto (>3.680pts) | 40/122 | +2.690,00 | 42,7% | [36,7;48,9] | POSITIVO | 41% (=ref.) | 61% (melhor) | 0,4% | 7 (−279,50) |
| **excluir tercio baixo (>2.558pts)** | **81/122** | **+3.402,00** | **40,1%** | **[35,6;44,8]** | **POSITIVO** | **32% (melhor)** | **50% (melhor)** | **1,9%** | 12 (−503,00) |

**"Excluir tercio baixo" foi escolhido** por ter a melhor concentração dos
dois (32%/50%, a MELHOR de toda a busca G1-G22 no IS), o maior líquido
(R$3.402,00, 22% acima da G21 sem filtro) e manter cobertura de 2/3 dos
pregões (mais robusto a um limiar único que "só tercio alto", que opera 1/3
dos dias). A classe final
(`WinBuscaLucroG22RetanguloFiltroAmplitude`) aplica o filtro DENTRO do
motor (`on_session_start` decide se o pregão está habilitado antes de
qualquer processamento de barra) e `g22_is_confirmacao.py` confirmou que a
classe reproduz **exatamente** os números da estratificação pós-hoc
(liquido=R$3.402,00, n=436, 81/122 dias — SIM, confere). "Só tercio alto"
fica registrado como alternativa não testada no OOS-1 (protocolo — um só
candidato por geração), mesmo precedente da G21 com `stop=0,50`.

### OOS-1 (jul-ago/2026, 44 pregões, CONGELADO em
`win_busca_lucro_g22_retangulo_filtro_amplitude_congelado_v22.py`, limiar
`amplitude_ontem > 2.558,3pts` idêntico ao do IS, SEM reajuste, rodado UMA VEZ):

**26 de 44 pregões habilitados** pelo filtro (59%, proporção parecida com os
66% do IS). Líquido **+R$89,50**, 67 trades, win **34,3%** (BEnom 33,3%,
BEemp 33,2%, IC95 [24,1%;46,3%] — indefinido, cruza o BEemp), equity mínima
R$847,00 (**não é censura de capital**, `ordens_recusadas_por_capital=0`),
`p_ruína` (MC)=2,8%, pior sequência 9 operações (−R$373,50).

**A concentração — exatamente o eixo que este filtro foi desenhado para
corrigir — piorou em vez de melhorar, e piorou MUITO: top3/liquido=607%,
top5/liquido=816%**, contra 97,2%/133,4% da própria G21 **sem** filtro no
MESMO OOS-1. O filtro não apenas não resgatou a concentração: tornou-a 6-8×
pior que não aplicar filtro nenhum. O líquido também caiu de R$650,00 (G21
sem filtro) para R$89,50 (G22 com filtro) — o filtro descartou 18 pregões do
OOS-1, e evidentemente parte do líquido bom da G21 original vinha
justamente de pregões que o proxy `amplitude_ontem` (calibrado no IS)
classificaria como "ruins" fora da amostra. **O proxy que separava dias bons
de ruins no IS com p=0,0040 não replicou essa direção no OOS-1** — ou
inverteu, ou deixou de informar nada: não dá para distinguir as duas
hipóteses com uma amostra de 44 pregões, e não é o objetivo desta geração
tentar.

**Veredito: NÃO VALIDADA.** Passa o gate literal mais frouxo (líquido>0, não
censurado por capital, veredito≠NEGATIVO) mas falha nos dois critérios de
folga por margem enorme: IC95 cruza o BEemp, e a concentração — o ÚNICO
motivo de esta geração existir — é a PIOR de toda a busca G1-G22, não a
melhor. Por protocolo, **OOS-2 NÃO foi rodado**.

**Conversão em % sobre a régua do dono:** R$89,50 em 2 meses sobre R$1.000 =
**8,9% no período, ~4,5%/mês médio** — não deve ser lido como projeção, dado
que o veredito é "não validada" com concentração pior que a própria
referência sem filtro.

### Resposta às perguntas do mandato

1. **Existe algum proxy que separe dias bons de ruins de forma real (não
   ruído) no IS?** Sim — `amplitude_ontem` (high-low do pregão anterior do
   WIN@), com separação monotônica e p=0,0040 no teste de permutação. Os
   outros 3 proxies testados (gap de abertura, dia da semana, range de
   abertura do WDO@) não separam nada de distinguível de ruído — resultado
   honesto, consistente com achados anteriores do projeto para dia-da-semana
   e gap.
2. **O filtro construído a partir desse proxy produziu um candidato com
   concentração melhor E líquido/win% ainda positivo no IS?** Sim, com
   folga — foi a MELHOR concentração de toda a busca G1-G22 no IS (32%/50%).
3. **Esse candidato validou fora da amostra?** NÃO. A concentração não só
   não se manteve — piorou mais que em qualquer geração anterior (607%/816%,
   contra 97,2%/133,4% da G21 sem filtro no MESMO OOS-1), e o líquido caiu
   87% frente à G21 sem filtro.

### Achado de método que atravessa a geração: a concentração não é resolvida por NENHUMA alavanca testada nesta busca inteira

Com a G22, são agora **quatro** tentativas independentes de resolver a
concentração temporal do líquido — capital (G17), tamanho graduado por
força/magnitude (G19), frequência via quantil mais baixo (G20), e agora um
**filtro de regime diário construído especificamente para esse fim**, sobre
uma família de sinal diferente (retângulo) e com uma base estatística mais
forte no IS (p=0,0040, não um ajuste de parâmetro) que qualquer uma das três
anteriores. **As quatro falharam, e a quarta falhou de forma mais
espetacular que as três primeiras** (concentração piorou em vez de
melhorar, não apenas "não melhorou o suficiente"). Isto não é mais
"nenhuma alavanca resolveu até agora" — é evidência direta de que um proxy
que separa regimes DENTRO do IS com significância real não precisa
preservar essa separação na janela seguinte, porque a variável que
determina "este pregão vai ser bom" muda de identidade entre janelas de um
jeito que nenhuma das ferramentas de preço/volume puro disponíveis nesta
busca consegue antecipar.

### Sizing dinâmico

Não testado — protocolo exige OOS-1 "com folga" antes de sizing, e este
resultado não bateu esse critério (nem perto: concentração pior que a
referência sem filtro).

### Avaliação honesta para o coordenador (item 6 do mandato)

**Recomendação: encerrar esta linha de busca (geometria/capital/sizing/
frequência/filtro de regime diário sobre sinais de OHLCV puro do WIN/WDO),
não abrir uma G23 tentando mais um proxy de dia.** As razões, em ordem de
peso:

1. **O teste desta geração era o mais favorável possível à hipótese "existe
   proxy de regime".** Diferente de G17/G19/G20 (que reusavam parâmetros já
   endógenos ao próprio gatilho), esta geração testou 4 proxies
   GENUINAMENTE exógenos e causais, um deles (amplitude_ontem) com a
   significância estatística mais forte já medida em qualquer
   estratificação desta busca (p=0,0040, não obtida por busca gulosa — foi
   o 1º e único proxy testado que separou, sem precisar varrer parâmetro).
   Mesmo esse proxy, no seu melhor momento possível, produziu o PIOR
   resultado de concentração fora da amostra de toda a busca.
2. **O padrão agora tem 4 réplicas independentes** (G4, G20, G21, G22),
   cobrindo sinal técnico puro (ORB, já encerrado por outro motivo),
   cross-instrumento (cruzado WIN×WDO), padrão de preço (retângulo) e agora
   regime diário — e as 4 convergem para "concentração piora de IS para
   OOS-1, nunca o contrário". Quatro tentativas estruturalmente diferentes
   que falham do MESMO jeito não é mais "ainda não achamos o parâmetro
   certo" — é evidência de que o problema não está em nenhum parâmetro.
3. **O item 6.52 de `LICOES_DE_PRODUCAO.md`** (registrado a partir desta
   geração) formaliza isso como invariante de método, portável para a
   plataforma nova: concentração saudável medida só no período de
   desenvolvimento não é preditiva, e a causa provável é que a identidade de
   "qual pregão é bom" muda entre janelas de um jeito que as variáveis
   disponíveis (preço/volume do próprio WIN/WDO) não capturam.

**Se o dono quiser continuar tentando mais uma geração apesar disso**, a
única direção que ainda não foi testada nesta busca é uma fonte de
informação estruturalmente DIFERENTE de preço/volume — a terceira via do
repositório (`social_arbitrage/`, arbitragem social/observação de campo) é
explicitamente fora de escopo para um EA de day trade de OHLCV puro, mas
qualquer dado macro/calendário externo (ex.: calendário de divulgação de
indicadores, posicionamento aberto do COT se existir equivalente B3, ou
feriados/vencimento de opções) ainda não foi tentado como proxy de regime
diário. Dado o padrão de 4/4 falhas estruturalmente diferentes, a
expectativa honesta é que isso também não resolva — mas é a única hipótese
ainda não eliminada por este relatório.

## Fase 3 — fonte externa (decisão do dono, 2026-10-05)

O dono aceitou o fechamento da Fase 2 (G17-G22): geometria, capital, sizing,
frequência e filtro de regime diário sobre OHLCV puro do WIN/WDO convergiram
4 de 4 vezes para o MESMO modo de falha (concentração que piora de IS para
OOS-1, item 6.52/6.53 de `LICOES_DE_PRODUCAO.md`) — não é mais questão de
parâmetro. A decisão: abrir uma Fase 3 com fonte de informação genuinamente
EXTERNA ao preço/volume do próprio WIN, mantendo todo o resto do mandato
(execução fechada, capital R$1.000, grade de alvo/stop {2×,2,5×,3×,4×,5×}
com piso nunca ≤1×, janelas IS jan-jun/OOS-1 jul-ago uma vez/OOS-2 set,
nunca 2025 ou antes, nunca editar `registry.py`).

**Dados verificados como realmente disponíveis localmente (não assumir mais
que isso, não inventar book/notícias/calendário):**
- `data/raw_intraday/*.parquet` — 162 ações da B3, M1, **índice em UTC**
  (converter para BRT — já houve bug de fuso neste tipo de dado em outro
  robô do repo, ver `b3_session_clock_fix` na memória do projeto), cobertura
  real 2021-08 a 2026-08 (confirmado por amostragem) — **usar só jan-ago/2026
  também aqui**, pela mesma razão do WIN/WDO: preservar uma janela de
  verdade intocada. **Atenção: a cobertura real NÃO alcança set/2026** (máx.
  observado 2026-08-27 numa amostra de 20 arquivos) — qualquer candidata
  desta fase que dependa de amplitude/fôlego das 162 ações pode não ter como
  rodar OOS-2 com este dado; verificar a cobertura de cada arquivo usado
  antes de prometer OOS-2, e declarar a limitação se for o caso.
- WDO M1 e ticks (já usados nas Fases 1-2 só como estado binário de
  confluência) — nesta fase, explorar como variável CONTÍNUA: lead-lag
  minuto a minuto, correlação cruzada, quem lidera quem, delta/fluxo como
  entrada contínua em vez de estado sim/não.

**Duas direções de partida (não exclusivas, outras são bem-vindas):**
- **A — amplitude/fôlego do índice:** dos componentes mais líquidos/maior
  peso do Ibovespa entre as 162 ações, quantos sobem vs caem no mesmo minuto
  ou numa janela curta (5-15min), como confirmação/antecipação de uma
  pernada do WIN.
- **B — WDO como líder contínuo:** lead-lag contínuo (o WDO se move
  primeiro, com que defasagem/magnitude o WIN segue?), possivelmente
  combinado com os filtros de LIGA que já funcionam (R01/R02 horário,
  R20/R35 onda de volatilidade).

**Gate NOVO e PERMANENTE, válido para toda candidata desta fase em diante:**
líquido positivo no OOS-1 não basta mais. Toda candidata que chegar ao
OOS-1 reporta OBRIGATORIAMENTE, lado a lado: (a) % do lucro vindo do(s) 1,
3 e 5 melhores pregões; (b) se essa concentração é PIOR no OOS-1 do que foi
no IS. "Promissora" exige líquido positivo E concentração que não piora
materialmente — não só líquido positivo.

Orçamento desta fase: até 300 disparos de filhos ou 40 gerações. Numeração
continua a partir da Geração 23.

## Geração 23 — amplitude/fôlego das 162 ações como sinal EXTERNO (resposta: a relação existe e é consistente, mas é fraca demais para pagar o próprio custo de execução)

**Quem testou:** agente principal (subagente delegado), 1 disparo. Primeira
geração da Fase 3 — fonte de informação genuinamente externa ao OHLCV do
próprio WIN. Código em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g23_amplitude_ibov/`
(`g23_base.py`, `g23_validacao_causal.py` + `_stdout.log`,
`g23_is_busca.py` + `_stdout.log`). Classe em
`src/strategy/daytrade/lab/win_busca_lucro_g23_amplitude_ibov.py`
(`WinBuscaLucroG23AmplitudeIbov`), **não registrada** em `registry.py`.

**A cesta.** 24 ações líquidas/de maior peso no Ibovespa, dentre as que
realmente existem nos 162 arquivos de `data/raw_intraday/*.parquet`
(faltam B3SA3, ELET3, PRIO3, RAIZ4, JBSS3, MGLU3 e outras grandes — não
estão na base de 162; usou-se as que existem): VALE3, PETR4, PETR3, ITUB4,
BBDC4, BBAS3, ABEV3, WEGE3, RENT3, SUZB3, BPAC11, LREN3, EQTL3, RADL3,
GGBR4, CSAN3, HAPV3, VIVT3, ITSA4, CSNA3, CMIG4, SBSP3, RDOR3, KLBN11.
**Cobertura real confirmada por amostragem (não assumida):** todas cobrem
no mínimo 2025-09 a 2026-08-21 — cobre o IS inteiro e quase todo o OOS-1,
mas **não alcança set/2026 (OOS-2 estruturalmente fora de alcance com este
dado)** e também não cobre os últimos ~9 pregões de agosto do próprio OOS-1.
Índice original em UTC, convertido para BRT (`America/Sao_Paulo`, sem
horário de verão no Brasil desde 2019 — conversão é um deslocamento FIXO de
3h o ano inteiro).

**O sinal (função pura, `folego_ibov`).** Fôlego causal = sinal médio dos
retornos de `janela_min` minutos (dentro do mesmo pregão, nunca atravessa a
virada de sessão) dos papéis da cesta, em [-1; +1] — reindexado na GRADE das
próprias barras do WIN@ com `ffill` limitado (não atravessa a virada de
sessão porque o `groupby(dia).diff` reseta por pregão independente do que o
`ffill` carregou). Igual à exceção já declarada e aceita na G4 (`AGENTS.md`
regra 2): função pura pré-computada FORA do loop do motor, `on_bar` só faz
`dict.get(ts)`.

**A pernada NASCENTE — mesmo zigzag causal (R43), dois limiares.**
`RastreadorPernadaNascente` é o MESMO mecanismo de zigzag sobre o caminho da
vela de R43/G1-G22 (vela de alta anda mínima→máxima, de baixa máxima→
mínima), rodando com DOIS limiares simultâneos: `nascente_pontos` (bem menor
que 750, parâmetro desta geração) marca o nascimento observável de uma
possível pernada nova; `pernada_pontos=750` (constante, a definição oficial
de pernada de toda a busca, nunca retunada) marca se a MESMA perna, antes de
reverter `nascente_pontos` a partir do seu extremo provisório, chegou à
distância oficial — "confirmou". A mesma classe roda IDÊNTICA na validação e
dentro do `on_bar` da estratégia (nunca duas implementações do mesmo
zigzag).

### Passo 1 — validação causal (antes de montar qualquer estratégia)

Pergunta: a concordância `fôlego[ts] × direção_nascente` no instante do
nascimento prediz a taxa de "a pernada chega a 750"? Método: uma única
passada pelo IS (dia a dia, reset por sessão, sem filtro nenhum), rotula
cada pernada nascente com a concordância e o desfecho (confirmou ou não),
corta em TERCIS dentro do IS — mesmo molde de estratificação pós-hoc
abençoado pelo item 6.50 de `LICOES_DE_PRODUCAO.md`. Testadas 4 combinações
de (`janela_min`∈{5,15}, `nascente_pontos`∈{250,375}):

| janela_min | nascente_pontos | n válido | tercil baixo/diverge | tercil médio | tercil alto/confirma |
|---|---|---|---|---|---|
| 5 | 250 | 5.894 | 12,7% [11,3;14,2] | 12,8% [11,4;14,4] | 15,6% [14,0;17,3] |
| 5 | 375 | 2.700 | 31,3% [28,4;34,3] | 36,3% [33,3;39,4] | **38,5% [35,1;42,0]** |
| 15 | 250 | 5.597 | 13,4% [12,0;15,0] | 12,3% [10,9;14,0] | 15,0% [13,4;16,7] |
| 15 | 375 | 2.573 | 33,4% [30,3;36,6] | 36,3% [33,1;39,5] | 36,1% [33,0;39,4] |

(taxa = % de pernadas nascentes que chegaram a 750 pontos; IC95% de Wilson)

**A relação existe e aponta sempre na mesma direção, nas 4 combinações sem
exceção: fôlego concordando com a pernada nascente prediz MAIS confirmação,
nunca menos** — a leitura "divergência" (fôlego oposto prediz falha, logo
vale apostar contra) não tem nenhum sinal a favor em nenhuma das 4 células;
só "confirmação" foi adiante. A combinação `janela_min=5, nascente_
pontos=375` deu a separação mais limpa — os dois extremos do IC95% (tercil
baixo até 34,3%, tercil alto a partir de 35,1%) **não se sobrepõem**, a
única das 4 combinações com essa propriedade — e foi a escolhida, SEM
reajuste depois de ver a grade de execução.

**Mas o efeito é pequeno:** a diferença baixo→alto é de +7,2 pontos
percentuais (31,3%→38,5%, lift relativo ~23%) sobre uma taxa de confirmação
baixa em termos absolutos (como esperado: 375 pontos é metade do limiar
oficial de 750, a maioria das pernadas nascentes morre antes de confirmar).
Um efeito desse tamanho é fácil de evaporar quando confrontado com o custo
real de executar (buffer de entrada, `ttl_bars`, deslize, fila não
calibrada) — é exatamente o que o passo 2 mediu.

### Passo 2 — grade de execução no IS

Parâmetros fixados pelo passo 1 (`janela_min=5`, `nascente_pontos=375`,
também usado como `stop_pontos` — a aposta é que a pernada nascente
CONTINUA, o stop natural é "reverteu a mesma distância que a fez nascer`),
`limiar_concordancia=0,5` (arredondado, mais frouxo que o corte do tercil
alto medido ~0,625 — não ajustado a dedo para maximizar resultado),
`direcao_aposta="confirmacao"` (única leitura com algum sinal a favor no
passo 1). Capital de teste R$1.000, 1 contrato fixo, execução fechada
(`EnterLimit`+`ttl_bars`, alvo fatiado sem prazo, `anchor_exits_at_fill`, só
o stop a mercado, `target_fills_as_maker=True`, fila WIN@ zero — não
calibrada, premissa otimista declarada). Grade do mandato, `alvo_multiplo`
∈ {2x, 2,5x, 3x, 4x, 5x}:

| variante | líquido R$ | trades | win% | BEemp% | veredito | p_ruína | top3/top5 | sem_trade | cens. capital |
|---|---|---|---|---|---|---|---|---|---|
| alvo=2,0x | −950,50 | 135 | 32,6% | 35,9% | indefinido | 32,6% | −81%/−112% | 92/122 | SIM |
| alvo=2,5x | −925,50 | 111 | 28,8% | 32,4% | indefinido | 31,7% | −64%/−103% | 95/122 | SIM |
| alvo=3,0x | −968,00 | 202 | 27,7% | 29,6% | indefinido | 49,0% | −108%/−167% | 77/122 | SIM |
| alvo=4,0x | −911,00 | 186 | 24,2% | 25,9% | indefinido | 49,9% | −145%/−210% | 76/122 | SIM |
| alvo=5,0x | −927,50 | 163 | 22,7% | 24,6% | indefinido | 50,7% | −164%/−259% | 78/122 | SIM |

(stop medido ≈380pts em todas, consistente com `stop_pontos=375`; pior
sequência de perdas consecutivas entre 13 e 19 operações, R$994 a R$1.453)

**0 de 5 células batem o critério composto** (líquido>0 E não censurado por
capital E veredito win%≠NEGATIVO E p_ruína≤25%): as 5 são negativas, as 5
estão censuradas por capital (caixa cruzou a margem crua de R$100 em algum
ponto da janela, partindo de R$1.000) e o p_ruína fica entre 31,7% e 50,7% —
sempre acima do teto de 25%. Auditoria de contagem (item 6.48/6.49):
3.748 pernadas nascentes brutas no IS, 962 a 1.141 ordens emitidas por
célula (o filtro de concordância já descarta ~2.500 antes de qualquer
execução), mas só 111 a 202 viram trade fechado — a maior parte das ordens
emitidas expira sem preencher (`ttl_bars=10`, buffer de 20 pontos).

**Checagem de robustez (fora da grade oficial, antes de aceitar o
veredito):** testado também `limiar_concordancia`∈{0,65; 0,80} (mais
seletivo, aproximando do corte do tercil alto) cruzado com `alvo_multiplo`
∈{2x,3x,5x} — 6 células adicionais, só 1 saiu com líquido positivo
(`limiar=0,65, alvo=5,0x`: +R$651,00, win=26,4% contra BEemp=25,8%,
veredito ainda "indefinido" pelo IC95%) e mesmo essa tem `p_ruína=52,3%`,
bem acima do teto de 25% — não bate o critério composto. As outras 5 desta
checagem extra são negativas. Nenhuma das 11 células testadas nesta geração
(5 oficiais + 6 de robustez) passa o gate composto.

### Veredito

**NEGATIVA no IS — não promovida a OOS-1.** Por instrução do mandato
("resultado negativo é válido, não fabrique números"), nenhuma célula
avança: não há OOS-1 nem checagem do gate novo de concentração para esta
geração (o gate de concentração só se aplica a quem CHEGA ao OOS-1).

**O que a Geração 23 estabelece, com confiança, para a Fase 3:**

1. **O fôlego da cesta NÃO é ruído em relação ao WIN** — a relação com o
   desfecho da pernada nascente é real, consistente de direção nas 4
   combinações testadas (nunca inverteu), e a melhor delas tem IC95%
   NÃO sobreposto entre tercis extremos. A hipótese nula de "a cesta de
   ações não acrescenta nada ao WIN, que já é o índice" (levantada no
   mandato como risco honesto) é REFUTADA como afirmação absoluta — existe,
   sim, uma correlação mensurável.
2. **Mas a relação é fraca demais para sobreviver à travessia do papel para
   o dinheiro.** +7,2pp de taxa de confirmação sobre uma base de ~31-35% não
   é folga suficiente para absorver o buffer de entrada, o `ttl_bars`, a
   fila não calibrada e o fato de que a maioria das ordens emitidas nem
   chega a preencher. O resultado é o mesmo padrão qualitativo das G1-G3 e
   de boa parte da Fase 2: sinal real, mas pequeno demais, afogado pelo
   custo de execução do desenho fechado — não é o modo de falha da Fase 2
   (concentração que piora IS→OOS), é um modo de falha ANTERIOR: a
   magnitude nunca foi suficiente para passar da própria seleção no IS.
3. **A pergunta que a Fase 3 levanta ("existe informação fora do OHLCV do
   próprio WIN que ajuda?") tem uma resposta parcial aqui: sim, mas a
   amplitude de uma cesta correlacionada é um sinal FRACO.** Isso não
   invalida a direção de buscar fonte externa — só esta primeira fonte
   específica (amplitude agregada de ações) não rendeu uma célula executável
   neste desenho. É diferente do padrão 4/4 da Fase 2 (onde o sinal passava
   no IS e morria no OOS-1): aqui o sinal nem passa no IS, então nenhuma
   "promessa" chegou a ser feita e quebrada — informação mais barata de
   obter (1 geração, sem gastar OOS-1).

**Raciocínio para a próxima geração (B — WDO como líder contínuo,
`ORQUESTRACAO.md` "Fase 3"):** o WDO tem uma vantagem estrutural que a cesta
de ações não tem — é o MESMO tipo de instrumento (futuro, mesma bolsa, já
documentado como correlacionado negativamente com o WIN em incrementos de
minuto, G4) e historicamente mais líquido/reativo a fluxo direcional de
curto prazo do que uma cesta de 24 ações cujo próprio sinal de amplitude já
é uma MÉDIA (que dilui magnitude por construção — 24 sinais binários
médios tendem ao centro). Lead-lag contínuo do WDO (magnitude e defasagem,
não só o estado binário já testado na G4) é a hipótese mais barata ainda não
eliminada desta fase — mas a expectativa honesta, dado o padrão desta
geração, é que qualquer sinal externo precisará de magnitude MUITO maior que
+7pp para pagar o próprio custo de execução deste desenho; vale medir a
magnitude do lead-lag ANTES de montar geometria, mesmo disciplina do passo 1
desta geração.

## Geração 24 — WDO como líder CONTÍNUO (resposta: lead-lag direcional não existe além de ruído; só sobrevive transmissão de VOLATILIDADE, que não é tradável neste desenho)

**Quem testou:** agente principal (subagente delegado), 1 disparo. Segunda
geração da Fase 3, direção B do mandato ("WDO como líder contínuo").
Scripts em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g24_wdo_lider_continuo/`
(`g24_base.py`, `g24_lead_lag.py` + `_stdout.log`,
`g24_magnitude_condicional.py` + `_stdout.log`, `g24_filtros_liga.py` +
`_stdout.log`). **Nenhuma estratégia foi montada** — por instrução explícita
do mandato ("só monte geometria se a magnitude justificar"), e a magnitude
medida nos passos 1-3 não justificou. Nenhum arquivo foi criado em
`strategy/daytrade/lab/` nesta geração.

**Dado:** `WIN@D_M1` e `WDO@D_M1` (`data/wdo-mt5/`, ambos ajuste por
diferença), carregados via `g04_base` (mesma geração 4). IS = jan-jun/2026,
122 pregões. Retornos de 1 minuto e de k minutos, sempre `groupby(dia).diff`
— nunca atravessa a virada de sessão.

### Passo 1 — correlação cruzada WDO→WIN e WIN→WDO, defasagens {0,1,2,3,5}min

Retorno de 1 minuto de cada instrumento, dentro do pregão. IC95% via Fisher
z (apropriado para n~68 mil — um p-valor sozinho não diz nada sobre
magnitude econômica, é exatamente a ressalva do mandato):

| lag (min) | WDO lidera WIN: r [IC95%] | WIN lidera WDO: r [IC95%] | n |
|---|---|---|---|
| 0 | −0,5181 [−0,5236;−0,5126] | (mesmo, contemporâneo) | 68.419 |
| 1 | +0,0055 [−0,0020;+0,0130] | +0,0341 [+0,0266;+0,0416] | ~68.3k |
| 2 | −0,0064 [−0,0139;+0,0011] | −0,0037 [−0,0112;+0,0038] | ~68.2k |
| 3 | +0,0008 [−0,0067;+0,0083] | −0,0052 [−0,0127;+0,0024] | ~68.1k |
| 5 | +0,0100 [+0,0025;+0,0176] | +0,0060 [−0,0016;+0,0135] | ~67.8k |

**Confirma R26, agora com método explícito de defasagem (REGRAS.md só tinha
medido concordância de sinal contemporânea, nunca lag a lag).** O lag=0
reproduz a correlação negativa forte e conhecida desde a G4 (−0,52, os dois
instrumentos andam opostos a maior parte do tempo). Em qualquer lag ≥1 min,
em QUALQUER direção (WDO→WIN ou WIN→WDO), `|r|` nunca passa de 0,034 — a
maioria dos coeficientes tem IC95% cruzando zero, e o único que não cruza
(WIN→WDO, lag=1, r=+0,0341) é estatisticamente diferente de zero só porque
n~68 mil torna qualquer `|r|>0,01` "significativo" — **não é economicamente
distinguível de ruído**. Não há lead-lag direcional de nenhum dos dois lados
além do que n grande garante por construção.

### Passo 2 — magnitude condicional (o número central desta geração)

Desenho causal, sem reaproveitar a janela do próprio evento (evita
redescobrir só o lag=0): `ret_wdo_passado_k(t) = WDO[t]-WDO[t-k]` (já
aconteceu, ≤t) condicionando `ret_win_futuro_k(t) = WIN[t+k]-WIN[t]`
(estritamente futuro, janela NÃO sobreposta). "Movimento grande" = acima do
quantil CAUSAL (burn-in 20 dias) de `|ret_wdo_passado_k|` — quartil (0,75) e
decil (0,90), `k∈{1,3,5}` minutos:

| k | grupo | n | mesma direção (IC95%) | lift direção | \|ret_win_fwd\| médio | lift magnitude |
|---|---|---|---|---|---|---|
| 1 | baseline (todos) | 55.714 | 49,2% [48,8;49,6] | — | 60,38pts | — |
| 1 | grande, q≥0,75 | 15.586 | 50,2% [49,4;51,0] | **+0,9pp** | 77,22pts | **+27,9%** |
| 1 | grande, q≥0,90 | 6.067 | 50,9% [49,7;52,2] | **+1,7pp** | 91,09pts | **+50,9%** |
| 3 | baseline (todos) | 59.975 | 49,6% [49,2;50,0] | — | 102,37pts | — |
| 3 | grande, q≥0,90 | 5.603 | 50,7% [49,4;52,0] | **+1,1pp** | 153,39pts | **+49,8%** |
| 5 | baseline (todos) | 61.159 | 49,9% [49,5;50,3] | — | 131,11pts | — |
| 5 | grande, q≥0,90 | 5.830 | 52,2% [50,9;53,5] | **+2,3pp** | 196,78pts | **+50,1%** |

(tabela completa, incluindo q≥0,75 de todos os `k`, no log
`g24_magnitude_condicional_stdout.log`)

**O achado tem DUAS metades, e elas apontam para respostas opostas.** A
metade de DIREÇÃO é negativa e decisiva: o lift de "mesma direção" vai de
+0,9pp a +2,3pp — todos os IC95% do grupo "movimento grande" cruzam ou quase
tocam 50% (o próprio baseline já fica abaixo de 50%, entre 49,2% e 49,9%), e
mesmo o maior lift observado (k=5, decil, +2,3pp) é **7-8x menor** que o já
insuficiente +7,2pp da Geração 23, e **muito abaixo** do piso de 15-20pp que
o mandato desta geração definiu como necessário para justificar montar
geometria. A metade de MAGNITUDE é positiva e grande: `|ret_win_fwd|` médio
sobe 27,9% a 50,9% no grupo condicionado a movimento grande do WDO — **o WDO
se mover muito carrega informação real sobre o WIN se mover mais** (não
PARA ONDE, mas O QUANTO), consistente com o achado já registrado na memória
do projeto para o gap overnight (`wdo_gap_volatilidade_e_fillrate`,
2026-09-27: `|gap|→volatilidade` r=0,34) — aqui o mesmo padrão de
transmissão de volatilidade aparece também intraday, minuto a minuto, não
só no gap.

### Passo 3 — os filtros de LIGA (R01 hora<11h; R20/R35 onda de volatilidade) melhoram o lift de direção?

Aplicados sobre os MESMOS eventos do passo 2 (estratificação pós-hoc sobre
uma única passada, decil q≥0,90, k∈{1,5}min — nenhuma simulação nova por
filtro, item 6.50):

| k | filtro | n | mesma direção (IC95%) |
|---|---|---|---|
| 1 | sem filtro (só magnitude grande) | 6.067 | 50,9% [49,7;52,2] |
| 1 | + R01 hora<11h | 2.428 | 50,3% [48,3;52,3] |
| 1 | + R20/R35 vela M1 faixa≥2x | 1.648 | 51,4% [49,0;53,8] |
| 1 | + R01 E R20/R35 (ambos) | 409 | 50,6% [45,8;55,4] |
| 5 | sem filtro (só magnitude grande) | 5.830 | 52,2% [50,9;53,5] |
| 5 | + R01 hora<11h | 2.334 | 50,7% [48,7;52,8] |
| 5 | + R20/R35 vela M1 faixa≥2x | 1.296 | 52,5% [49,7;55,2] |
| 5 | + R01 E R20/R35 (ambos) | 323 | 53,6% [48,1;58,9] |

**Os filtros de LIGA não deslocam a taxa de "mesma direção" para longe de
50% em nenhuma combinação** — toda linha filtrada tem IC95% cruzando (ou
quase cruzando) 50%, e a combinação dos dois filtros (n=409 e n=323) só
alarga o intervalo sem mover o centro de forma consistente. Confirma, desta
vez sobre o lead-lag contínuo, a mesma distinção que `REGRAS.md` já registra
para o WIN em geral: R01/R02/R20/R35 respondem **QUANDO** o mercado se mexe
mais, não **PARA ONDE** — e isso vale tanto para o próprio WIN quanto para
o lead-lag WDO→WIN testado aqui.

### Veredito

**NEGATIVA — nenhuma estratégia completa foi montada, por instrução do
mandato.** A magnitude medida nos passos 1-3 é mais fraca que a da Geração
23 (que já era insuficiente), em qualquer recorte testado:

1. **Correlação cruzada direcional: não existe além do que n grande
   garante por construção** — `|r|` nunca passa de 0,034 em lag≥1min, nos
   dois sentidos. Confirma R26 com método novo (defasagem explícita, não só
   concordância contemporânea).
2. **Magnitude condicional de DIREÇÃO: lift de +0,9pp a +2,3pp**, 7-8x menor
   que o já insuficiente +7,2pp da G23 e bem abaixo do piso de 15-20pp do
   mandato. Os filtros de LIGA (R01/R20/R35) não aumentam esse lift em
   nenhuma combinação testada.
3. **Magnitude condicional de VOLATILIDADE: lift real de +27,9% a +50,9%** —
   quando o WDO se move muito, o WIN se move mais (não se sabe para onde).
   Este é um achado genuíno, mas não é operacionalizável no desenho fechado
   desta busca (stop/alvo direcional fixo) — seria insumo para uma
   estratégia de VOLATILIDADE (ex. alvo/stop dinâmico por regime, ou um
   instrumento de opções), categoria fora do escopo desta linha de EA
   direcional.

**O que a Geração 24 estabelece, com confiança, para a Fase 3:**

1. **A direção B do mandato ("WDO como líder contínuo") está ENCERRADA como
   fonte de sinal DIRECIONAL** — generalizando o estado binário já morto na
   G4 (confirmação cruzada) para a versão contínua (magnitude, defasagem
   fina), o resultado é o mesmo: o WDO não antecipa a direção do WIN, nem
   como estado nem como magnitude, com ou sem os filtros de LIGA.
2. **Sobrevive só a transmissão de volatilidade**, que já tinha aparecido
   antes (gap overnight) e agora aparece também intraday — mas é uma
   pergunta de TAMANHO de movimento, não de DIREÇÃO, e o desenho fechado
   desta busca inteira (stop/alvo fixo, sempre direcional) não tem como
   monetizá-la sem mudar de categoria de estratégia.
3. **Das duas direções de partida da Fase 3 (A — amplitude/fôlego da cesta;
   B — WDO contínuo), as DUAS deram negativo para o objetivo desta busca**
   (EA direcional lucrativo do WIN). A relação A (G23) tinha +7,2pp de
   lift, fraca mas real; a B (G24) tem no máximo +2,3pp, mais fraca ainda.
   Em nenhuma das duas o sinal externo testado é grande o bastante para
   pagar o custo do desenho fechado de execução.

**Raciocínio para a próxima geração:** a Fase 3 já testou as duas direções
de partida sugeridas no mandato (`ORQUESTRACAO.md`, "Fase 3") e as duas
morreram por magnitude insuficiente, não por erro de método ou de desenho —
ambas foram medidas com disciplina causal, burn-in, e estratificação
pós-hoc antes de qualquer custo de execução entrar na conta. Isso é um sinal
de que a busca por fonte EXTERNA ao WIN, pelo menos nas duas fontes mais
óbvias e baratas de obter com o dado já disponível localmente (cesta de
ações e o WDO), pode ter se esgotado — qualquer nova direção precisaria de
uma fonte qualitativamente diferente (ex. a transmissão de volatilidade do
passo 2 desta geração, se uma categoria de estratégia não-direcional entrar
no escopo; ou dado ainda não explorado, como profundidade de livro, se
algum dia ficar disponível). Vale levar ao dono a pergunta de escopo antes
de abrir uma Geração 25: continuar insistindo em fonte externa direcional
com os dados já tentados, abrir uma categoria de estratégia diferente
(volatilidade), ou declarar a Fase 3 encerrada como a Fase 2 foi.

## Geração 25 — lead-lag DIRETO da cesta (não só confirmação de pernada nascente); resposta: sem lead genuíno, direção pior que a G24, só sobrevive transmissão de volatilidade — Fase 3 ENCERRADA (3/3 negativas)

**Quem testou:** agente principal (subagente delegado), 1 disparo. Terceira
e última geração planejada da Fase 3 — extensão da G23 (que só mediu a cesta
como CONFIRMAÇÃO de uma pernada já nascente, já tinha cruzado 250-375pts)
para o mesmo método de lead-lag CONTÍNUO da G24 (que testou o WDO), agora
com o índice sintético da cesta no lugar do WDO. Scripts em
`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g25_cesta_lider_continuo/`
(`g25_base.py`, `g25_lead_lag.py` + `_stdout.log`,
`g25_magnitude_condicional.py` + `_stdout.log`). **Nenhuma estratégia foi
montada** — por instrução explícita do mandato ("só monte geometria se a
magnitude justificar"), e a magnitude medida nos passos 1-2 não justificou,
igual à G24. Nenhum arquivo foi criado em `strategy/daytrade/lab/` nesta
geração.

**O índice sintético da cesta (`g25_base.retorno_k_cesta`).** Reaproveita a
cesta de 24 ações líquidas já carregada/convertida de fuso pela G23
(`g23_base.carrega_cesta`) e o esqueleto causal de helpers da G24
(`g24_base`: `retorno_k_min`, `desloca_dentro_do_dia`, `corr_com_ic`,
`quantil_causal_abs`, janelas IS/OOS) — nenhuma lógica de carregamento
duplicada. **Diferença de método, declarada:** WIN/WDO (G24) são dois
futuros do MESMO tipo de instrumento, negociados em PONTOS — dá para medir
lead-lag em pontos diretamente. A cesta tem 24 papéis em escalas de preço
heterogêneas (VALE3 ~60, KLBN11 ~20 etc.), então a unidade comum é RETORNO
PERCENTUAL: para cada papel, retorno de `k` minutos causal dentro do pregão
(`precos.groupby(dia).diff(k) / precos.groupby(dia).shift(k)`, preços
reindexados na grade do WIN com `ffill` limitado a 10 min, nunca atravessa a
virada de sessão); o índice da cesta é a **média simples (equal-weight)**
dos retornos válidos naquele instante, exigindo ≥50% dos papéis com dado
válido (mesmo piso de `folego_ibov`, G23). Generaliza `folego_ibov` (que só
usava o SINAL do delta) para a MAGNITUDE do retorno — é o análogo direto do
`retorno_k_min(wdo, ...)` da G24, agregado sobre 24 papéis em vez de 1
instrumento. Pesagem por liquidez/peso no Ibovespa foi DECLARADA como não
testada (ficaria para uma próxima geração se esta mostrasse sinal).

### Passo 1 — correlação cruzada cesta→WIN e WIN→cesta, defasagens {0,1,2,3,5}min

Mesmo método exato da G24 (retorno de 1 minuto de cada lado, dentro do
pregão, IC95% via Fisher z), IS = jan-jun/2026, 122 pregões:

| lag (min) | cesta lidera WIN: r [IC95%] | WIN lidera cesta: r [IC95%] | n |
|---|---|---|---|
| 0 | +0,8742 [+0,8721;+0,8761] | (mesmo, contemporâneo) | 53.680 |
| 1 | −0,0215 [−0,0299;−0,0130] | +0,0204 [+0,0120;+0,0289] | 53.680 |
| 2 | +0,0103 [+0,0018;+0,0187] | +0,0001 [−0,0084;+0,0085] | 53.680 |
| 3 | −0,0049 [−0,0133;+0,0036] | −0,0062 [−0,0147;+0,0022] | 53.680 |
| 5 | +0,0017 [−0,0068;+0,0102] | +0,0122 [+0,0037;+0,0206] | 53.673 |

**O lag=0 é a diferença estrutural mais marcante contra a G24: +0,8742,**
forte e POSITIVO — o oposto do −0,5181 negativo que WIN/WDO têm no mesmo
lag. Isso não é sinal, é definição: a cesta é literalmente componente do
mesmo índice que o WIN replica, então os dois se moverem juntos
contemporaneamente é esperado por construção, não é informação nova. **Em
qualquer lag≥1min, em QUALQUER direção, `|r|` nunca passa de 0,0215** — mais
fraco até que o já descartado `|r|≤0,034` da G24 (WDO), e todos os IC95%
cruzam zero ou quase. **Não existe lead genuíno da cesta sobre o WIN, nem
do WIN sobre a cesta, além do que n~54 mil garante por construção** — o
mesmo veredito "sem lead-lag direcional" da G24, agora confirmado também
para a cesta, com a correlação contemporânea ainda mais alta (consistente
com a hipótese de mercado eficiente intradiário levantada no mandato: o WIN
é pelo menos tão rápido quanto a média das 24 ações).

### Passo 2 — magnitude condicional (o número central desta geração)

Mesmo desenho causal da G24 (`ret_cesta_passado_k(t)` já aconteceu, `≤t`;
`ret_win_futuro_k(t)` estritamente futuro, janela NÃO sobreposta), quartil
(0,75) e decil (0,90), `k∈{1,3,5}` minutos:

| k | grupo | n | mesma direção (IC95%) | lift direção | \|ret_win_fwd\| médio | lift magnitude |
|---|---|---|---|---|---|---|
| 1 | baseline (todos) | 52.451 | 47,2% [46,7;47,6] | — | 58,24pts | — |
| 1 | grande, q≥0,75 | 11.599 | 46,3% [45,4;47,2] | **−0,8pp** | 77,40pts | **+32,9%** |
| 1 | grande, q≥0,90 | 4.897 | 46,1% [44,7;47,5] | **−1,1pp** | 87,69pts | **+50,6%** |
| 3 | baseline (todos) | 52.451 | 48,5% [48,1;48,9] | — | 100,84pts | — |
| 3 | grande, q≥0,90 | 4.918 | 48,3% [46,9;49,7] | **−0,1pp** | 152,94pts | **+51,7%** |
| 5 | baseline (todos) | 52.451 | 49,2% [48,7;49,6] | — | 129,74pts | — |
| 5 | grande, q≥0,90 | 4.890 | 49,0% [47,6;50,4] | **−0,1pp** | 204,83pts | **+57,9%** |

(tabela completa, incluindo q≥0,75 de todos os `k`, no log
`g25_magnitude_condicional_stdout.log`)

**A metade de DIREÇÃO não é só fraca — é a PIOR das três gerações da Fase
3.** O lift de "mesma direção" vai de **−1,1pp a −0,3pp em todos os
recortes testados — nunca positivo**, diferente da G23 (+7,2pp, sempre
positivo) e da G24 (+0,9pp a +2,3pp, sempre positivo). O baseline já fica
abaixo de 50% (47,2% a 49,2%), e condicionar num movimento grande da cesta
não desloca a taxa para cima — se alguma coisa, desloca ligeiramente para
baixo, dentro do ruído (todos os IC95% cruzam ou quase tocam o baseline). A
metade de MAGNITUDE repete o padrão já visto na G24: `|ret_win_fwd|` médio
sobe **+32,9% a +57,9%** no grupo condicionado a movimento grande da cesta —
magnitude grande, na mesma ordem da G24 (+27,9% a +50,9%) e do gap overnight
(`wdo_gap_volatilidade_e_fillrate`, r=0,34) — **o terceiro contexto
independente (gap overnight, WDO intraday, cesta intraday) em que a mesma
transmissão de VOLATILIDADE aparece, sempre sem carregar direção junto.**

### Veredito

**NEGATIVA — nenhuma estratégia completa foi montada, por instrução do
mandato.** A magnitude medida é mais fraca que a G23 e a G24 em QUALQUER
recorte:

1. **Correlação cruzada direcional: não existe além do que n grande
   garante por construção** — `|r|` nunca passa de 0,0215 em lag≥1min, mais
   fraco que o já insuficiente `|r|≤0,034` da G24. O lag=0 alto (+0,87) é
   definição estrutural (a cesta é componente do índice), não sinal.
2. **Magnitude condicional de DIREÇÃO: lift de −1,1pp a −0,3pp — nunca
   positivo**, pior que o já insuficiente +0,9pp a +2,3pp da G24 e muito
   abaixo do piso de 15-20pp do mandato. Não há recorte (nenhum `k`, nenhum
   quantil) em que a cesta antecipe a DIREÇÃO do WIN.
3. **Magnitude condicional de VOLATILIDADE: lift real de +32,9% a +57,9%** —
   terceiro contexto (depois do gap overnight e do WDO intraday) em que o
   mesmo padrão aparece: um movimento grande em OUTRA fonte carrega
   informação real sobre o TAMANHO do próximo movimento do WIN, nunca sobre
   a direção. Não operacionalizável no desenho fechado desta busca
   (stop/alvo direcional fixo), mesma conclusão da G24.

**O que a Geração 25 estabelece, com confiança, para a Fase 3:**

1. **A hipótese nula forte ("a cesta, sendo ela mesma componente do índice
   que o WIN replica, não tem lead genuíno sobre o WIN") SOBREVIVE aqui,**
   ao contrário do que a G23 tinha refutado para a versão "confirmação de
   pernada nascente". A diferença de desenho explica a diferença de
   resultado: a G23 media a cesta no instante em que o WIN JÁ tinha
   começado a se mexer (250-375pts já percorridos) — nesse ponto a cesta
   carrega alguma informação residual sobre se o movimento vai CONTINUAR.
   Aqui, sem condicionar a um movimento já em curso do WIN, a cesta pura
   não antecipa nada — consistente com mercado eficiente intradiário: o
   índice futuro (WIN) processa a informação nova tão rápido ou mais rápido
   que a média de 24 ações individuais, então por quando a cesta se move de
   forma perceptível, o WIN (que é o próprio índice, com alavancagem e
   liquidez de futuro) já se moveu junto ou antes (lag=0 = +0,87).
2. **As TRÊS tentativas da Fase 3 (G23 amplitude/fôlego, G24 WDO contínuo,
   G25 cesta contínua) deram negativo para o objetivo desta busca (EA
   direcional lucrativo do WIN)** — e a magnitude piora a cada tentativa
   mais "pura" de lead-lag direcional: G23 (+7,2pp, mas CONDICIONADA a uma
   pernada já nascente) → G24 (+0,9 a +2,3pp, WDO contínuo sem condicionar)
   → G25 (−1,1pp a −0,3pp, cesta contínua sem condicionar, PIOR que ruído).
   Isso não é 3 tentativas aleatórias com sorte ruim — é um padrão
   CONSISTENTE: quanto mais o desenho tenta extrair lead-lag DIRECIONAL
   puro (sem usar o próprio WIN como parte do condicionamento), mais fraco
   o sinal fica. A única coisa que sobrevive nas três fontes testadas
   (cesta, WDO, e também o gap overnight medido antes da Fase 3) é
   transmissão de VOLATILIDADE, nunca de direção — um padrão forte demais
   para ser coincidência, e consistente o bastante para ser tratado como
   fato estabelecido sobre o mercado do WIN, não como lacuna de busca.

### Veredito final da Fase 3 inteira (Gerações 23-25)

**Fase 3 ENCERRADA — convergência de evidência, mesmo padrão que fechou a
Fase 2.** A Fase 2 (G17-G22) convergiu 4 de 4 vezes para o mesmo modo de
falha (concentração que piora IS→OOS) usando só preço/volume do próprio
WIN/WDO. A Fase 3 (G23-G25) convergiu 3 de 3 vezes para um modo de falha
ANTERIOR e mais fundamental — nenhuma das três fontes externas testadas
(amplitude/fôlego da cesta, WDO contínuo, cesta contínua) carrega magnitude
DIRECIONAL suficiente para pagar o próprio custo de execução do desenho
fechado, e a tentativa mais "limpa" (esta, G25) foi a MAIS fraca das três,
não a mais forte. Diferente da Fase 2 (onde o sinal passava no IS e morria
no OOS-1 — gate de concentração), aqui o sinal nem passa da própria seleção
no IS em nenhuma das três tentativas — nenhuma "promessa" chegou a ser feita
e quebrada, e nenhuma OOS-1 foi gasta.

**Recomendação ao coordenador:** encerrar a busca por fonte EXTERNA
DIRECIONAL com os dados hoje disponíveis localmente. O que fica
estabelecido com confiança:

1. **Dados genuinamente externos tentados e refutados como fonte
   DIRECIONAL:** amplitude/fôlego de uma cesta de 24 ações líquidas do
   Ibovespa (G23, só fraco o bastante quando condicionado a uma pernada já
   nascente), WDO como líder contínuo (G24), cesta como líder contínuo
   (G25, esta geração).
2. **Um achado genuíno e recorrente que NÃO é direcional:** transmissão de
   volatilidade — gap overnight (r=0,34, memória do projeto,
   `wdo_gap_volatilidade_e_fillrate`), WDO intraday (+27,9% a +50,9%, G24) e
   cesta intraday (+32,9% a +57,9%, G25) carregam todos o mesmo sinal: um
   movimento grande em QUALQUER uma dessas três fontes prediz um WIN mais
   agitado no minuto/janela seguinte, nunca prediz PARA ONDE. Isso é
   insumo real, mas para uma categoria de estratégia DIFERENTE (ex. alvo/
   stop dinâmico por regime de volatilidade, ou instrumento de opções) —
   fora do escopo desta linha de EA direcional de stop/alvo fixo.
3. **Fontes externas que GENUINAMENTE NÃO EXISTEM neste ambiente** (não
   foram ignoradas por preguiça, foram verificadas como indisponíveis antes
   da Fase 3 abrir, `ORQUESTRACAO.md` "Fase 3 — fonte externa"):
   profundidade de livro (book), notícias/calendário econômico, dados de
   opções/volatilidade implícita, correlação com índices internacionais
   (S&P futures, DXY) — nenhum destes está disponível localmente hoje; só
   valeria reabrir esta linha se algum deles passasse a existir no ambiente.
4. **O que a Fase 3 recomenda ao dono, com a mesma honestidade que fechou a
   Fase 2:** a busca por um EA direcional lucrativo do WIN dentro do desenho
   fechado de execução (stop/alvo fixo, grade {2x,2,5x,3x,4x,5x}) esgotou,
   nesta rodada, tanto a via interna (Fase 2, preço/volume do próprio
   WIN/WDO) quanto a via externa mais barata de obter (Fase 3, cesta e
   WDO). A próxima alavanca genuína não é mais "qual sinal", é "qual
   CATEGORIA de estratégia" (volatilidade/opções) ou "qual dado novo"
   (profundidade de livro, se algum dia disponível) — ambas decisões de
   ESCOPO do dono, não mais parâmetro de busca.

## Geração 26 (pós-fechamento) — filtro de tendência sobre a G21, pedido do dono após olhar o replay visual

**Por que:** o dono construiu um replay de operações (`.claude/artifacts/g21_retangulo/index.html`) para a candidata nº1 (G21, retângulo) e observou visualmente que várias perdas pareciam ser entradas CONTRA a direção mais ampla do pregão. A G21 decide o lado só pela posição do preço relativo ao MEIO do retângulo (janela local de 20 minutos) — nunca testado contra uma leitura de tendência mais ampla (a Fase 1/R43-R47 testou tendência sobre sinais de preço puro; a G10 testou sobre ORB/momentum; nenhuma testou sobre esta família de reversão-ao-meio).

**O que foi feito:** `WinBuscaLucroG26RetanguloTendencia` (subclasse da G21, nenhuma lógica de detecção/geometria reimplementada) intercepta a ação `EnterLimit` do pai e descarta quando o lado conflita com uma medida de tendência mais ampla. Duas famílias declaradas ANTES de rodar: `drift_bars` (sinal de `close[-1]-close[-W]`, W∈{60,120,240,480} barras M1) e `drift_dia` (desde a abertura da sessão), cada uma frouxa (neutro passa) ou estrita (neutro bloqueia).

**IS (jan-jun, 122 pregões), referência G21 sem filtro: líquido R$2.790,00, n=562, win 37,9%, BEemp 33,8%, top3/liq 40,9%, top5/liq 64,5%.**

| Filtro | Líquido | n | win% | top3/liq | top5/liq |
|---|---|---|---|---|---|
| drift_bars W=120/240/480, frouxo | R$2.611–2.980 | 400–543 | 38,3–39,2% | 39,4–42,4% | 58,7–64,7% |
| **drift_dia, frouxo** | R$2.254,00 | 308 | **39,6%** | **36,2%** | **54,9%** |
| drift_bars W=120, estrito | R$2.494,00 | 240 | 41,2% | 34,7% | 52,6% |
| drift_bars W=240/480, estrito | −R$34 / +R$178 | 96 / 19 | colapsa | sem platô | sem platô |

O IS confirmou a observação visual do dono: filtrar por tendência melhora win% e concentração em todas as variantes frouxas (platô real em `drift_bars` 120-480) e na `drift_dia`. `estrito` NÃO tem platô (W=120 isolado, W=240/480 colapsam) — descartado por disciplina, não promovido.

**Congelados ANTES do OOS-1 (`..._congelado_v26.py`):** (1) `drift_bars` W=240 (meio do platô), frouxo; (2) `drift_dia`, frouxo.

**OOS-1 (jul-ago, 44 pregões), referência G21 sem filtro: líquido +R$650,00, n=98, win 39,8%, top3/liq 97,2%.**

| Candidato | Líquido | n | win% | top3/liq |
|---|---|---|---|---|
| drift_bars W=240, frouxo | +R$626,00 | 96 | 39,6% | 100,9% |
| drift_dia, frouxo | **−R$166,00** | 56 | **30,4%** (< BE 32,8%) | −290,4% |

**Veredito: a observação visual do dono era real na descoberta (os dois filtros melhoraram win% e concentração no IS), mas NÃO se confirmou na conferência.** O filtro `drift_bars` (janela de 4h) praticamente não mudou nada no OOS-1 (removeu só 2 de 98 trades — a janela de 4h quase nunca discorda do sinal local de 20 min neste período) — nem ajuda nem atrapalha. O filtro `drift_dia` (o que tinha dado a MELHOR concentração no IS) inverteu para negativo no OOS-1, pior que a referência sem filtro. **Mesmo padrão que atravessa toda a busca desde a G4: um filtro que melhora a amostra de desenvolvimento não necessariamente se mantém na janela seguinte.** Não promovido a OOS-2. Arquivos: `scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g26_filtro_tendencia/` (`g26_base.py`, `g26_is_busca.py`, `g26_oos1.py`); estratégia em `src/strategy/daytrade/lab/win_busca_lucro_g26_retangulo_tendencia.py` (+ `_congelado_v26.py`).

## Geração 27 (pós-fechamento) — filtro de tendência de tempo MAIOR (M15/H1/pernada), pedido do dono

**Por que:** depois do resultado neutro/negativo da G26 (drift cru), o dono pediu algo mais estrutural: "ver em M15 ou H1 se o retângulo de M1 é um recuo de tendência num gráfico maior". Reaproveitadas as 3 medidas de tendência JÁ VALIDADAS como causais na Fase 2 (`rodada5/tendencia/base.py`, usadas em R43-R47): `i_m15` (inclinação EMA20 em M15), `i_h1` (idem H1), `i_leg` (direção da pernada de 750 em curso). Pré-computadas uma vez (`g27_prep.py` → `tendencia_m15_h1_leg.pkl`), filtro aplicado sobre a mesma geometria vencedora da G21 (stop 0,45×/alvo 0,90×).

**IS (jan-jun, 122 pregões), referência G21 sem filtro: líquido R$2.790,00, n=562, win 37,9%, top3/liq 40,9%.**

| Medida | Líquido | n | win% | top3/liq |
|---|---|---|---|---|
| i_m15 | R$917–956 | 275–282 | ~37% | **piorou para 67–70%** |
| i_h1 | R$1.053–1.092 | 274–281 | ~38% | **piorou para 67–69%** |
| m15_h1 (M15 E H1 concordando) | R$1.119–1.145 | 191–358 | ~37–39% | **piorou para 57–78%** |
| **i_leg (pernada de 750 em curso)** | R$2.424–2.444 | 314–322 | **40,4%** | **melhorou para 36%** |

As medidas de EMA em M15/H1 pioraram a concentração mesmo na descoberta — descartadas, não promovidas. Só `i_leg` melhorou nas duas frentes (acerto e concentração), com platô robusto (frouxo ≈ estrito, porque `i_leg` raramente é neutro).

**Congelado antes do OOS-1:** `i_leg`, frouxo.

**OOS-1 (jul-ago, 44 pregões), referência G21 sem filtro: líquido +R$650,00, n=98, win 39,8%, top3/liq 97,2%.**

Resultado: líquido **+R$137,50** (n=53, menos da metade das operações), win **35,8%** (só 2pp acima do empate, contra 40,4% no IS), **top3/liq=302,2%, top5/liq=438,2% — pior que o próprio G21 sem filtro**, que já era ruim (97%/133%).

**Veredito: não se confirmou — pelo motivo oposto ao esperado.** O filtro que mais melhorou a descoberta foi o que mais piorou a concentração na conferência. Terceira tentativa seguida (depois da G26: drift cru e drift do dia) de usar tendência maior para filtrar a mesma candidata, terceira vez que o resultado promissor do IS não sobrevive. Arquivos: `g27_tendencia_m15h1/` (`g27_prep.py`, `g27_base.py`, `g27_is_busca.py`, `g27_oos1.py`); estratégia em `src/strategy/daytrade/lab/win_busca_lucro_g27_retangulo_tendencia_maior.py` (+ `_congelado_v27.py`).

**Leitura acumulada (G21+G26+G27):** o problema de concentração da G21 (o lucro do OOS-1 vindo de poucos pregões) não é resolvido por nenhuma leitura de tendência testada até aqui — nem crua (drift), nem estrutural (EMA M15/H1), nem a mais "WIN-nativa" possível (pernada de 750 em curso, já extensivamente validada no projeto para outros fins). As três tentativas pioram ou mantêm a concentração no OOS-1, nunca melhoram.

## Geração 28 (pós-fechamento) — "usar a NÃO confirmação como base para operar" (filtro de REGIME, não de direção)

**Por que:** depois de G26/G27 (filtros de DIREÇÃO, todos sem confirmar), o dono propôs algo diferente: em vez de usar a tendência para escolher o LADO, usar a FALTA de acordo entre tendências como sinal de QUANDO entrar — a hipótese: a G21 (reversão ao meio de um retângulo de 20 min) deveria funcionar melhor num mercado SEM tendência clara (M15/H1 discordando) e pior quando há consenso forte de tendência (que favoreceria rompimento, não reversão).

**O que foi feito:** `WinBuscaLucroG28RetanguloRegimeIndefinido` bloqueia a entrada nos DOIS lados igual (não escolhe lado) quando há CONSENSO de tendência; deixa operar normalmente (nos dois lados) quando as escalas discordam. Duas definições de consenso, declaradas antes de rodar: `m15_h1_discordam` (bloqueia quando M15==H1, ~72% do tempo bloqueado) e `sem_consenso_total` (bloqueia só quando M15==H1==pernada concordam, ~48% bloqueado).

**IS (jan-jun, 122 pregões), referência G21 sem filtro: líquido R$2.790,00, n=562, win 37,9%, top3/liq 40,9%.**

| Regime testado | Líquido | n | win% | top3/liq |
|---|---|---|---|---|
| Só opera quando M15 discorda de H1 | **−R$6,00** (~zero) | 178 | 34,8% (abaixo do BE 34,9%) | catastrófica (liquido ≈ 0) |
| Só opera quando falta consenso nas 3 escalas | R$1.750,50 | 351 | 38,7% | 50,3% (pior que o G21) |

**Veredito: a hipótese foi REFUTADA já na descoberta — nem chegou a ser testada no OOS-1.** As duas definições de "mercado sem tendência" pioraram o resultado em vez de melhorar: operar SÓ quando as escalas discordam é pior do que operar sempre, nas duas variantes. A leitura provável: a G21 não é uma reversão pura — ela entra no lado que CONTINUA a posição local do preço em relação ao meio do retângulo (short quando o preço já estava abaixo do meio, aposta que volta a cair depois de tocar o meio), ou seja, já carrega embutida uma lógica de continuação de curtíssimo prazo. Períodos de consenso de tendência mais amplo parecem favorecer essa continuação local, não atrapalhar — o oposto do que a hipótese previa. Como a hipótese já falhou no portão da descoberta (nenhuma célula melhorou a referência), não foi promovida ao OOS-1, seguindo a mesma disciplina que já parou G2/G3 na Fase 1. Arquivos: `g28_regime_indefinido/` (`g28_base.py`, `g28_is_busca.py`); estratégia em `src/strategy/daytrade/lab/win_busca_lucro_g28_retangulo_regime_indefinido.py`.

## Geração 29 (pós-fechamento) — EMA 34 clássica, pedido literal do dono: "a melhor até aqui"

**Pedido:** "Coloque uma média exponencial de 34. Se o preço anterior fechar abaixo e for venda, vendemos; se fechar acima e for compra, compramos." Primeira vez que se testa posição do preço (não inclinação, não drift) contra uma média no mesmo tempo gráfico (M1) da própria estratégia. `WinBuscaLucroG29RetanguloEma34`, EMA pré-computada (`g29_prep.py`), períodos 21/34/55 testados por padrão (sensibilidade).

**IS (jan-jun), referência G21 sem filtro: líquido R$2.790,00, n=562, win 37,9%, top3/liq 40,9%.**

| Período | Líquido | n | win% | top3/liq |
|---|---|---|---|---|
| EMA21 | R$3.062,50 | 521 | 38,8% | 38,4% |
| **EMA34** | R$2.805,50 | 467 | 38,8% | **32,5%** |
| EMA55 | R$2.513,50 | 413 | 38,7% | 40,4% |

Platô real nas 3 janelas (todas POSITIVO, todas melhoram o acerto). EMA34 (a pedida) tem a melhor concentração das três.

**Congelado e promovido ao OOS-1: EMA34** (período literal do dono, não escolhido por otimização — os vizinhos confirmam o mesmo sentido).

**OOS-1 (jul-ago), referência G21 sem filtro: líquido +R$650,00, n=98, win 39,8%, top3/liq 97,2%, top5/liq 133,4%.**

| | Sem filtro | Com EMA34 |
|---|---|---|
| Líquido | R$650,00 | **R$736,50** |
| Operações | 98 | 77 |
| Acerto | 39,8% | **41,6%** (BEemp 33,3%) |
| top3/liq | 97,2% | **88,3%** |
| top5/liq | 133,4% | **119,0%** |
| p_ruína (MC) | — | 0,2% |
| Retorno sobre R$1.000 | 65,0% / 2 meses | **73,7%** / 2 meses (36,8%/mês) |

**Veredito: a MELHOR candidata da série pós-fechamento (G26-G29) — melhora em TODAS as métricas no OOS-1, não só uma.** Mas ainda não passa "com folga": o IC95 do win% [31,2%;52,7%] cruza o breakeven (31,2% < 33,3%) por causa do n moderado (77), e a concentração melhorou mas continua alta (top5/liq=119%, ainda acima de 100% — os dias além do top5 ainda são negativos no agregado). Não promovido automaticamente a OOS-2 pelo protocolo estrito ("só quem passa com folga") — decisão de prosseguir ou não devolvida ao dono, dado o salto de qualidade frente às 3 tentativas anteriores. Arquivos: `g29_ema34/` (`g29_prep.py`, `g29_base.py`, `g29_is_busca.py`, `g29_oos1.py`); estratégia em `src/strategy/daytrade/lab/win_busca_lucro_g29_retangulo_ema34.py` (+ `_congelado_v29.py`).

### OOS-2 (set/2026, gate FINAL) da G29 — falhou

Mesmo código congelado (`periodo=34`), rodado uma vez em setembro/2026 (21 pregões, nunca usado antes para P&L desta estratégia).

| | jul-ago (OOS-1) | **set (OOS-2)** |
|---|---|---|
| Líquido | +R$736,50 | **−R$629,50** |
| Operações | 77 | 77 |
| Acerto | 41,6% | **31,2%** (abaixo do BE 37,7%) |
| top3/liq | 88,3% | **−92,1%** (liquido negativo) |
| Pior sequência | 8 (−R$318) | **14 (−R$665)** |
| p_ruína (MC) | 0,2% | **80,8%** |
| Retorno/mês | +36,8% | **−63,0%** |

**Veredito: REPROVADA no gate final.** Setembro foi fortemente negativo, com uma sequência de 14 perdas que deixou o caixa em R$306 (quase um terço do capital de teste) e uma probabilidade de ruína de 80,8% projetada a partir da distribuição real desse mês. Combinado jan-set (ano inteiro, 621 operações): líquido ainda positivo (R$2.912,50, win 38,2%, veredito POSITIVO) — mas esse agregado esconde o mês ruim, e um único mês com 80% de chance de ruína não pode ser chamado de validado só porque os outros 8 meses compensam. Consistente com achado anterior do projeto (rodadas 1-7): setembro/2026 foi atípico para regras de direção no WIN.

**G21+EMA34 não é uma estratégia validada para uso real.** Fica registrada como a melhor candidata da série pós-fechamento, mas reprovada no mesmo lugar que fechou a busca original: um mês específico pode quebrar a conta, mesmo quando a média do ano é positiva.

### Referência: G21 sem filtro em set/2026 (pedido do dono, comparação direta)

Mesmo código congelado v21, nunca rodado em set/2026 antes. `g21_set2026.py`.

| | G21 sem filtro | G21 + EMA34 |
|---|---|---|
| Líquido | **−R$909,50** | −R$629,50 |
| Acerto | 29,2% | 31,2% |
| Caixa mínimo | R$90,50 (abaixo da margem de R$100) | R$306,00 |
| p_ruína (MC) | 93,6% | 80,8% |

O filtro de EMA34 não piora nada mesmo no mês ruim — reduz a perda, melhora o acerto e afasta o caixa da margem. Mas setembro é ruim para a família inteira (com ou sem filtro); o filtro ameniza, não resolve.

## PADRÃO ATUAL (2026-10-05) — G21 + EMA34 substitui G21 sozinho

Decisão do dono: a partir de agora, a candidata nº1 ("o retângulo") é **sempre com o
filtro de EMA 34** (`WinBuscaLucroG29RetanguloEma34`, período 34, venda só com
fechamento ≤ EMA, compra só com fechamento ≥ EMA) — não mais `WinBuscaLucroG21Retangulo1000`
puro. Motivo: a EMA34 melhorou o resultado nos TRÊS períodos testados sem exceção
(descoberta, conferência e o mês ruim de setembro — ver tabela abaixo), a única das
quatro tentativas pós-fechamento (G26-G29) que não inverteu de sinal em nenhuma janela.

| Período | G21 sozinho | **G21 + EMA34 (padrão)** |
|---|---|---|
| Descoberta (jan-jun) | R$2.790,00 | **R$2.805,50** |
| Conferência (jul-ago) | R$650,00 | **R$736,50** |
| Setembro | −R$909,50 | **−R$629,50** |

**O que isso NÃO significa:** G21+EMA34 ainda não é uma estratégia validada para
operar ao vivo — setembro continua negativo, com 80,8% de chance de ruína projetada.
"Padrão" aqui quer dizer: é a base de comparação e o ponto de partida para qualquer
trabalho futuro nesta candidata (ex. investigar o que torna setembro diferente, ou
testar novas ideias) — sempre a favor de G21+EMA34, nunca mais contra G21 sozinho.

Arquivo ativo: `src/strategy/daytrade/lab/win_busca_lucro_g29_retangulo_ema34.py`
(período 34 fixo). `WinBuscaLucroG21Retangulo1000` continua existindo só como a
classe-mãe (reaproveitada, não descartada).

## Geração 30 (pós-fechamento) — corpo inteiro da vela contra a EMA (em vez de só o fechamento)

**Pedido:** olhando uma perdedora no replay bem perto da EMA34, o dono perguntou se exigir o CORPO INTEIRO da vela (abertura E fechamento) do lado certo — não só o fechamento (regra da G29) — melhora o resultado. `WinBuscaLucroG30RetanguloEmaCorpo`: venda só passa se `max(open,close) <= EMA`; compra só se `min(open,close) >= EMA`. Mesma EMA pré-computada da G29, mesmos 3 períodos (21/34/55).

**IS (jan-jun), referências: sem filtro R$2.790,00/n=562/top3=40,9%; G29 (só fechamento, EMA34) R$2.805,50/n=467/top3=32,5%.**

| Variante | Líquido | n | win% | top3/liq |
|---|---|---|---|---|
| EMA21, corpo inteiro | R$1.845,50 | 423 | 37,4% | 44,0% |
| EMA34, corpo inteiro | R$2.275,00 | 402 | 38,3% | 38,5% |
| EMA55, corpo inteiro | R$1.895,50 | 365 | 37,8% | 46,5% |

**Veredito: pior que a G29 (só fechamento) em TODOS os períodos e todas as métricas — não promovida ao OOS-1.** A intuição parecia razoável (vela que atravessa a linha é sinal mais fraco), mas na prática exigir o corpo inteiro corta operações boas junto com as ruins: menos líquido, concentração pior, sem compensação em acerto. A regra da G29 (só o fechamento) continua sendo o padrão. Arquivos: `g30_ema_corpo/` (`g30_base.py`, `g30_is_busca.py`); estratégia em `src/strategy/daytrade/lab/win_busca_lucro_g30_retangulo_ema_corpo.py`.

## Geração 31 (pós-fechamento) — padrão de rejeição (vela contra a cor, mas sem sair da EMA)

**Pedido:** "e se for uma vela de BAIXA fechar totalmente acima da MM, se for compra? E se for uma vela de ALTA fechar totalmente abaixo da MM, se for venda?" — compra só com vela de baixa (cor oposta ao sinal) que mesmo assim fecha acima da EMA; venda só com vela de alta que fecha abaixo. `WinBuscaLucroG31RetanguloEmaRejeicao`.

**IS (jan-jun), referências: sem filtro R$2.790,00/n=562; G29 (padrão, só fechamento) R$2.805,50/n=467/top3=32,5%.**

| Variante | Líquido | n | win% | top3/liq | p_ruína |
|---|---|---|---|---|---|
| EMA21, rejeição | R$1.946,50 | 175 | **42,3%** | 31,0% | 0,1% |
| EMA34, rejeição | R$1.473,50 | 175 | 40,6% (indefinido, IC cruza) | 31,9% | 0,4% |
| EMA55, rejeição | R$1.700,50 | 155 | **42,6%** | **28,8%** | 0,1% |

Corta a amostra para ~37% do G29 (175 contra 467), mas sobe o acerto e melhora a concentração nas 3 janelas — perfil de "menos operações, mais seletivas, risco de ruína quase zero". Líquido total menor só porque são menos trades.

**Congelado e promovido ao OOS-1: EMA34** (pedido literal).

**OOS-1 (jul-ago):**

| | Sem filtro | G29 | **G31 (rejeição)** |
|---|---|---|---|
| Líquido | R$650,00 | R$736,50 | R$439,00 |
| n | 98 | 77 | **26** (26 de 44 dias sem nenhum trade) |
| win% | 39,8% | 41,6% | **46,2%** |
| top3/liq | 97,2% | 88,3% | **65,8%** |
| p_ruína | — | 0,2% | **0,0%** |

**OOS-2 (set, gate final):**

| | Sem filtro | G29 | **G31 (rejeição)** |
|---|---|---|---|
| Líquido | −R$909,50 | −R$629,50 | **−R$533,50** |
| win% | 29,2% | 31,2% | 24,1% (pior) |
| p_ruína | 93,6% | 80,8% | 76,1% |

**Veredito: também reprovada no gate final, e NÃO supera a G29 como padrão.** Setembro continua negativo e de alto risco nas três variantes. A G31 reduz um pouco o prejuízo absoluto de setembro frente à G29, mas piora o acerto nesse mês (24,1% contra 31,2%) e perde para a G29 tanto na descoberta quanto na conferência (menos líquido nas duas, apesar da melhor qualidade por operação). **G29 (EMA34, só fechamento) continua sendo o padrão** — a G31 não a substitui, fica registrada como variante de "menor frequência, maior seletividade" para referência futura. Arquivos: `g31_ema_rejeicao/` (`g31_base.py`, `g31_is_busca.py`, `g31_oos1.py`, `g31_oos2.py`); estratégia em `src/strategy/daytrade/lab/win_busca_lucro_g31_retangulo_ema_rejeicao.py` (+ `_congelado_v31.py`).

## Geração 32 (pós-fechamento) — mergulho e recuperação dentro da própria vela de decisão

**Pedido:** operando uma alta, uma vela abre acima da EMA, desce abaixo, fica mais de 50% do "tempo" abaixo, mas recua e fecha acima antes do fim. Aproximação declarada (sem tick cobrindo jan-fev): "mais de 50% do tempo abaixo" virou "mais da metade do RANGE da vela abaixo da EMA" (`EMA < (high+low)/2`), um proxy de posição, não de tempo real — ver ressalva no módulo, mesma família de cuidado do item 6.47 de LICOES_DE_PRODUCAO.md. `WinBuscaLucroG32RetanguloEmaRecuo`.

**IS (jan-jun), referências: sem filtro R$2.790,00/n=562; G29 R$2.805,50/n=467/top3=32,5%; G31 R$1.473,50/n=175/top3=31,9%.**

| Variante | Líquido | n | win% | top3/liq |
|---|---|---|---|---|
| EMA21, mergulho+recuperação | R$645,50 | 125 | 38,4% | 84,1% |
| EMA34, mergulho+recuperação | R$378,50 | 99 | 37,4% | **124,6%** |
| EMA55, mergulho+recuperação | R$264,00 | 60 | 36,7% | **145,3%** |

**Veredito: pior em tudo, não promovida ao OOS-1.** Diferente da G31 (que também cortava a amostra, mas melhorava acerto e concentração), este padrão corta a amostra para quase nada (60-125 de 467) SEM melhorar o acerto (36,7-38,4%, igual ou pior que a referência) e com concentração catastroficamente pior (até 145% no top3 — o lucro de poucos dias é maior que o total, logo o resto é bem negativo). Exigir um movimento mecânico tão específico dentro de uma única vela de 1 minuto é raro demais para carregar sinal; a aproximação por range (não por tempo real) pode estar descartando casos que o tempo real aceitaria, mas o resultado já é ruim o bastante para não gastar tick nisso. Arquivos: `g32_ema_recuo/` (`g32_base.py`, `g32_is_busca.py`); estratégia em `src/strategy/daytrade/lab/win_busca_lucro_g32_retangulo_ema_recuo.py`.

## Geração 33 (pós-fechamento) — tipo de média e combinação de 2/3 médias

**Pedido:** testar se o TIPO de média (simples/aritmética = SMA, exponencial = EMA, "etc" = WMA) muda o resultado, e se exigir concordância entre 2 ou 3 médias em períodos diferentes (34+68, 34+100, 34+68+100) ajuda. `WinBuscaLucroG33RetanguloMultiplasMM`, generaliza a regra da G29 para N médias (compra só com fechamento ≥ TODAS; venda só ≤ TODAS). 3 tipos × 5 períodos pré-computados (`g33_prep.py`).

**(A) Tipo da média, período 34, regra só-fechamento (referência G29/EMA34: R$2.805,50, n=467, win 38,8%, top3=32,5%):**

| Tipo | Líquido | n | win% | top3/liq |
|---|---|---|---|---|
| SMA (simples/aritmética) | R$2.016,00 | 472 | 37,5% | 43,5% |
| **EMA** | **R$2.805,50** | 467 | **38,8%** | **32,5%** |
| WMA (ponderada linear) | R$2.372,50 | 519 | 38,0% | 43,7% |

**EMA confirmada como o melhor tipo — SMA e WMA perdem em tudo.** O tipo já escolhido (EMA) não foi acidente.

**(B) Combinação de 2 e 3 médias (todas EMA):**

| Combinação | Líquido | n | win% | top3/liq |
|---|---|---|---|---|
| **EMA34 sozinha (G29)** | **R$2.805,50** | 467 | 38,8% | **32,5%** |
| EMA34+68 | R$2.428,00 | 392 | 38,8% | 39,4% |
| EMA34+100 | R$2.602,00 | 364 | 39,8% | 33,8% |
| EMA34+68+100 | R$2.479,50 | 361 | 39,6% | 35,5% |

**Veredito: nenhuma combinação supera a EMA34 sozinha — não promovida ao OOS-1.** Todas continuam POSITIVO (não pioram tanto quanto as tentativas anteriores), e o acerto sobe um pouco nas combinações com 100 (39,6-39,8% contra 38,8%), mas o líquido total e a concentração pioram em todas — exigir mais médias concordando corta amostra sem resolver o problema de concentração, que é o que mais importa. EMA34 sozinha continua sendo o padrão. Arquivos: `g33_multiplas_mm/` (`g33_prep.py`, `g33_base.py`, `g33_is_busca.py`); estratégia em `src/strategy/daytrade/lab/win_busca_lucro_g33_retangulo_multiplas_mm.py`.

## Geração 34 — autópsia por trade do padrão (G21+EMA34): o que o mercado mostrava antes de cada entrada

**Pedido (2026-10-05):** para cada entrada, olhar os sinais disponíveis ANTES dela (médias, inclinação, candle, volume, horário, volatilidade, posição no dia) e achar o que separa vencedoras de perdedoras; depois dimensionar a mão pela probabilidade. `g34_autopsia/g34_autopsia.py` (20 sinais medidos na vela que armou a limite, tabela por trade em `g34_autopsia_trades.csv`, log em `g34_autopsia_stdout.log`). Modelo logístico ajustado SÓ no IS.

| | IS | OOS-1 | set |
|---|---|---|---|
| AUC do modelo (0,50 = não separa) | 0,598 | **0,507** | **0,448** |
| terço "alta probabilidade": win% | 49,4% | 40,0% (pior que o terço médio) | **25,8% (o pior)** |
| mão 0/1/2 contratos pela probabilidade | +R$6.476,50 | +R$869,00 (base +R$736,50) | **−R$1.051,50** (base −R$629,50) |

**Veredito: o modelo é sobreajuste do IS.** Fora dele não separa nada, e em setembro inverte. Dimensionar pela probabilidade AMPLIFICA a perda de setembro.

**Por que setembro perde:** largura do retângulo e ATR eram os maiores sinais positivos no IS/OOS-1 (AUC 0,55/0,60 e 0,54/0,65) e viram negativos em setembro (0,34 e 0,47) — retângulo largo em mercado volátil volta para o meio em regime lateral e rompe em regime de tendência. É um efeito de regime, não um sinal pré-entrada que funcione nas três janelas.

**Dois sinais que mantiveram a direção nas 3 janelas (achados olhando as 3 — NÃO validados):**
- horário 13h-15h negativo em todas (IS −R$170,50 n73; OOS-1 −R$123 n6; set −R$126 n6); 9h-11h positivo em todas.
- volume dos últimos 5 min acima do normal (`vol_rel ≥ 0,98`, terço superior do IS): IS +R$1.415 (n156, 42%), OOS-1 +R$355,50 (n25, 44%), set **+R$435,50** (n23, 48%) — com o resto de setembro em −R$1.065.
Ressalva: com 20 sinais, ~5 concordariam nas 3 janelas por puro acaso (prob. 1/4 cada); vieram 2. Só um teste em dado novo (out/2026 em diante) separa achado de sorte. E volume já foi descartado como indicador isolado em 2026-10-01.

### G34 — teste dos 2 filtros congelados em meses nunca abertos (2026-10-06, autorização do dono para abrir 2 meses da reserva)

Meses escolhidos só pela variação de preço: jul/2025 (−4,39%) e ago/2025 (+5,21%). Corte de volume congelado do IS: `vol_rel >= 0,9836`. `g34_teste_2025.py`.

| mês | sem filtro | os dois filtros |
|---|---|---|
| jul/2025 (baixa) | −R$184,00 (16 trades, 25%) | −R$249,50 (7 trades, 0%) |
| ago/2025 (alta) | +R$30,00 (2 trades) | 0 trades |

**Inconclusivo por falta de trades, e o pouco que houve foi contra o filtro de volume (7 de 7 perdidos).** Causa da escassez: faixa mediana de 20 min do WIN em jul-ago/2025 = 265 pts, abaixo do piso de largura de 328 pts (em 2026: 385-665). A estratégia depende da volatilidade de 2026. **jul e ago/2025 agora estão GASTOS**; o resto de 2025 continua reservado.

## Geração 35 — gestão da SAÍDA sobre o padrão (G21+EMA34): alvo maior, stop móvel, alvo móvel

**Pedido (2026-10-06):** alvo 3× o stop; stop que anda a favor; alvo que se afasta enquanto não houver sinal contrário (fechamento do lado errado da EMA34) com o stop acompanhando; combinações. Entrada intocada, stop inicial 0,45×largura. `WinBuscaLucroG35RetanguloEma34Gestao`, `g35_gestao_saida/g35_grade.py` (60 células: alvo {2; 2,5; 3; 4}× × gestão {nenhuma, breakeven, trail1R, trail05R, alvo_movel} × 3 janelas). Referência reproduzida: 2× sem gestão = R$2.805,50 no IS.

| célula (líquido R$) | jan-jun | jul-ago | set | total |
|---|---|---|---|---|
| **2× sem gestão (padrão)** | 2.805,50 | 736,50 | −629,50 | **2.912,50** |
| 2,5× sem gestão | 2.922,00 | 895,00 | −908,00 | 2.909,00 |
| 3× sem gestão (pedido) | 2.640,50 | 792,00 | −940,00 | 2.492,50 |
| 4× sem gestão | 2.304,50 | 677,00 | −912,00 | 2.069,50 |
| melhor com gestão (3× trail05R) | 1.437,50 | 383,50 | −775,00 | 1.046,00 |
| 2× breakeven | 520,00 | 107,50 | −632,50 | −5,00 |

**Veredito: nenhuma troca bate o padrão.** Toda gestão de stop (breakeven, trailing, alvo móvel) perde nas 3 janelas: o win% sobe para ~51-57% mas o ganho médio cai de ~R$80 para ~R$40 — o stop móvel corta as vitórias que iriam ao alvo. Com trailing ligado, o alvo quase nunca é alcançado (2× e 4× dão o mesmo resultado) e o alvo móvel vira o próprio trail1R. Alvo maior troca acerto por tamanho de ganho e piora setembro (−R$629 → −R$908/−R$940). 2,5× empata no total (+IS/OOS-1, −set) — sem melhora evidente, não muda.

## Geração 36 — curiosidade do dono: AFASTAR o stop (alvo parado em 0,90×largura)

`WinBuscaLucroG36RetanguloEma34StopLargo` (piso do múltiplo baixado para 1,0× só neste teste — fura o piso de 2× do mandato, não é candidata), `g36_stop_largo/g36_grade.py`.

| célula (líquido R$) | jan-jun | jul-ago | set | total |
|---|---|---|---|---|
| **stop 0,45 (padrão)** | **2.805,50** | 736,50 | −629,50 | 2.912,50 |
| stop 0,55 | 2.624,50 | 998,00 | −476,50 | 3.146,00 |
| stop 0,65 | 2.307,50 | 1.035,50 | −911,50 | 2.431,50 |
| stop 0,75 | 1.802,50 | 636,50 | −708,00 | 1.731,00 |
| stop 0,85 | 2.606,50 | 672,50 | −213,50 | 3.065,50 |
| controle: 0,45 checado no fechamento | 1.382,50 | 995,00 | −915,00 | 1.462,50 |
| afasta +0,10 a cada 15 velas | 1.414,00 | 1.119,00 | −936,50 | 1.596,50 |
| afasta +0,10 a cada 5 velas | 1.855,00 | 996,50 | −661,00 | 2.190,50 |

**Veredito: sem padrão.** O resultado sobe e desce sem direção conforme o stop abre (0,55 e 0,85 melhores no total, 0,65 e 0,75 piores) — ruído, não platô. No IS (janela de escolha) o padrão 0,45 é o melhor. O stop que se afasta só pode ser medido checando no fechamento (o motor nunca afrouxa stop nativo), e o controle mostra que checar no fechamento sozinho já custa ~R$1.450; descontado isso, afastar a cada 5 velas recupera parte, mas não passa o padrão.

## Geração 37 — curiosidade do dono: ALVO que se APROXIMA com o tempo

Alvo começa em 0,90×largura e encolhe 0,10×largura a cada N velas desde o fill, piso 0,50 (acima do stop 0,45). `AdjustTarget` reprecifica a limite real — teste justo. `WinBuscaLucroG37RetanguloEma34AlvoAproxima`, `g37_alvo_aproxima/g37_grade.py`.

| célula | jan-jun | jul-ago | set | total | maxDD jan-jun / jul-ago / set |
|---|---|---|---|---|---|
| **alvo parado (padrão)** | 2.805,50 | 736,50 | −629,50 | 2.912,50 | 991 / 391 / 1.075 |
| encolhe a cada 40 velas | 2.881,00 | 897,50 | −658,50 | 3.120,00 | 946 / 248 / 1.087 |
| encolhe a cada 20 velas | 2.736,50 | 819,50 | −703,50 | 2.852,50 | 874 / 248 / 1.118 |
| encolhe a cada 10 velas | 2.676,50 | 829,00 | −622,50 | 2.883,00 | 898 / 248 / 1.051 |
| **encolhe a cada 5 velas** | 2.671,50 | 978,00 | **−324,00** | **3.325,50** | **847 / 216 / 854** |

**Leitura:** primeira troca de saída que não piora. "A cada 5 velas" é a melhor no total (+R$413) e tem o menor rebaixamento nas 3 janelas, com setembro caindo pela metade (−R$629 → −R$324); win% sobe (39→44% / 42→51% / 31→38%) e o ganho médio cai (R$80→R$64). Ressalvas: no IS (janela de escolha) ela é −R$134 vs o padrão; a melhora não é monotônica no passo (40 melhor que 20 e 10). Candidata a confirmar em mês novo, não a adotar.

## PADRÃO ATUAL (2026-10-06) — G21 + EMA34 + ALVO QUE SE APROXIMA (substitui o padrão de 2026-10-05)

Decisão do dono depois da G37: "é simples de entender e de confirmar — vira o novo padrão". Entrada idêntica à G29 (retângulo + EMA34); stop fixo 0,45×largura; alvo começa em 0,90×largura e vem 0,10×largura mais perto a cada 5 velas fechadas depois da entrada, até 0,50×largura.

| | jan-jun | jul-ago | set | total |
|---|---|---|---|---|
| padrão anterior (alvo parado) | +R$2.805,50 | +R$736,50 | −R$629,50 | +R$2.912,50 |
| **padrão novo** | +R$2.671,50 | +R$978,00 | −R$324,00 | **+R$3.325,50** |

Python: `WinBuscaLucroG37RetanguloEma34AlvoAproxima` (defaults = padrão) e cópia congelada `..._congelado_v37.py` (reproduz os números acima). MQL5: `mt5/WinRetanguloEma34.mq5` v1.03 (`AlvoAproximaBarras=5`, `AlvoAproximaPasso=0,10`, `AlvoPisoFracao=0,50`; `AlvoAproximaBarras=0` volta ao alvo parado). **Continua NÃO validado para dinheiro real**: setembro ainda é negativo e o ajuste foi escolhido olhando as 3 janelas — o próximo mês novo (out/2026) é o teste.

## Geração 38 — stop que se aproxima JUNTO com o alvo (no mesmo relógio de 5 velas), sobre o padrão G37

`WinBuscaLucroG38RetanguloAlvoEStopAproximam`, `g38_alvo_e_stop/g38_grade.py`. Referência = padrão conferido (+R$3.325,50); a linha "stop −0" do log saiu R$10 diferente por arredondamento de 1 tick no stop recalculado (corrigido depois: `stop_passo<=0` não mexe no stop).

| stop por passo do alvo | jan-jun | jul-ago | set | total |
|---|---|---|---|---|
| **0 (padrão)** | 2.671,50 | 978,00 | −324,00 | 3.325,50 |
| −0,025 | 2.743,00 | 885,00 | −417,50 | 3.210,50 |
| −0,05 (mantém 2:1) | 3.146,50 | 826,00 | −347,50 | 3.625,00 |
| −0,10 | 2.327,50 | 762,50 | −439,50 | 2.650,50 |

**Veredito: não muda o padrão.** −0,05 ganha no total só pelo IS; nas duas janelas fora do IS é pior. Sem direção (−0,025 pior, −0,05 melhor, −0,10 pior).

## Geração 39 — mover alvo/stop conforme o preço anda A FAVOR ou CONTRA (sobre o padrão G37)

Pedido do dono: cada regra sozinha e em conjunto, para aprender o efeito. R = distância entrada→stop. "favor" = andou ≥1R a favor; "contra" = andou ≥0,5R contra. `WinBuscaLucroG39RetanguloGestaoPorDirecao` (`regras=()` reproduz o padrão: R$3.325,50 conferido), `g39_gestao_por_direcao/g39_grade.py`. Stop "longe" não testável (motor nunca afrouxa stop nativo; o contorno da G36 custou ~R$1.450 sozinho).

| regra | jan-jun | jul-ago | set | total |
|---|---|---|---|---|
| **padrão G37** | 2.671,50 | 978,00 | −324,00 | **3.325,50** |
| alvo longe se favor | 3.065,50 | 1.029,00 | −951,00 | 3.143,50 |
| alvo perto contra + longe favor | 3.001,00 | 737,50 | −925,50 | 2.813,00 |
| alvo longe se contra | 2.560,00 | 984,50 | −780,00 | 2.764,50 |
| alvo perto se favor | 2.361,50 | 694,50 | −524,00 | 2.532,00 |
| alvo perto se contra | 2.376,00 | 812,00 | −686,50 | 2.501,50 |
| stop perto se contra | 1.840,50 | 608,00 | **+8,50** | 2.457,00 |
| favor: alvo perto + stop na entrada | 1.977,50 | 687,00 | −480,50 | 2.184,00 |
| stop perto se favor (breakeven) | 1.589,50 | 596,50 | −70,00 | 2.116,00 |
| contra: alvo e stop perto | 1.734,50 | 575,00 | −290,50 | 2.019,00 |
| favor: alvo longe + stop na entrada | 527,00 | 369,50 | −911,00 | −14,50 |

**Veredito: nenhuma regra bate o padrão no total.** O que se aprende: toda regra troca meses bons por mês ruim. "Deixar correr" (alvo longe se favor) é a melhor de jan-ago (+R$445) e a pior de setembro (−R$627). "Proteger" (stop perto, contra ou a favor) quase zera setembro (+R$8,50 / −R$70) mas custa R$1.200-1.460 em jan-ago. Mexer no alvo para mais perto piora tudo. O padrão é o meio-termo entre os dois extremos. "Stop perto se contra" é seguro de ruína a preço conhecido, se o critério virar sobrevivência em vez de lucro.

## Geração 40 — sair quando a vela que acabou de fechar teve volume anormal (ideia do dono)

Sobre o padrão G37. Volume da vela t JÁ FECHADA contra a média das 20 anteriores; `Exit` na abertura de t+1 (causal, reproduzível ao vivo — o dono apontou que o volume da vela em formação não é). `WinBuscaLucroG40RetanguloSaidaVolume`, `g40_saida_volume/g40_grade.py`.

| regra | jan-jun | jul-ago | set | total |
|---|---|---|---|---|
| **padrão G37** | 2.671,50 | 978,00 | −324,00 | **3.325,50** |
| volume > 1,5× média | 1.860,50 | 439,00 | −909,00 | 1.390,50 |
| volume > 2× média | 2.677,00 | 662,00 | −623,00 | 2.716,00 |
| volume > 3× média | 2.281,50 | 908,50 | −324,00 | 2.866,00 |
| volume > 2×, só no lucro | 2.811,00 | 766,00 | −558,50 | 3.018,50 |
| volume < média/1,5 | 1.267,00 | 361,50 | +164,00 | 1.792,50 |
| volume < média/2 | 1.770,00 | 758,00 | −313,00 | 2.215,00 |
| volume < média/2, só no lucro | 1.588,50 | 554,00 | −187,00 | 1.955,50 |
| **volume < média/3** | 2.753,50 | 950,00 | −69,00 | **3.634,50** |

**Veredito: não confirma a observação.** Volume ALTO: sair sempre piora. Volume BAIXO: só o extremo (< 1/3 da média, raro) melhora o total (+R$309, quase todo em setembro), mas sem direção entre os limiares (/1,5 bem pior, /2 pior, /3 melhor) — mesma assinatura de ruído das G36-G38. Não muda o padrão; "/3" fica como candidata fraca para o teste de out/2026.

## Geração 41 — zerar mais cedo (pedido do dono: "sair às 17h, antes de chegar perto do fechamento")

Sobre o padrão G37. `WinBuscaLucroG41RetanguloZeraCedo` (Exit a mercado no horário; novas entradas param ttl=10 velas antes). `g41_zera_cedo/g41_grade.py`.

| corte | jan-jun | jul-ago | set | total |
|---|---|---|---|---|
| sem corte próprio (motor) | 2.671,50 | 978,00 | −324,00 | 3.325,50 |
| **17:50 (o que o EA faz)** | 2.519,00 | 917,50 | −324,00 | **3.112,50** |
| 17:30 | 2.466,00 | 886,50 | −324,00 | 3.028,50 |
| **17:00** | 2.603,00 | 888,50 | −324,00 | **3.167,50** |
| 16:30 | 2.533,50 | 888,50 | −281,00 | 3.141,00 |
| 16:00 | 2.484,50 | 857,50 | −373,50 | 2.968,50 |
| 15:00 | 2.440,00 | 960,50 | −388,50 | 3.012,00 |

**Veredito: indiferente.** Com dado certo quase não há posição aberta depois das 17h; 17:00 contra os 17:50 do EA = +R$55. As perdas gigantes do Testador (vendas sem stop até 17:50) eram do dado quebrado — zerar às 17h as encurtaria, mas não resolve o stop que não dispara durante o dia. O EA já tem `HoraZerar`/`MinutoZerar`; 17:00 é escolha livre, não melhora mensurável.

Auditoria de dado (2026-10-06): ticks da corretora WINV26 13/08–30/09, 09:05–18:20 = 57.249.188 ticks, 54.545.104 negócios, último=0 em 1 tick (`mt5/auditoria_ticks_corretora_WINV26.csv`). O Testador relatou 57.009.708 ticks — NÃO faltam ticks; o defeito é o campo "último negócio" na cópia do Testador. `mt5/AuditoriaTicks.mq5` (não opera) conta isso tick a tick dentro do Testador.

## PADRÃO ATUAL (2026-10-06, 2ª atualização) — G37 + zera 17:00

Decisão do dono: encerrar mais cedo. Padrão = retângulo + EMA34 + alvo que se aproxima a cada 5 velas + zeragem 17:00 (entradas novas param 11 velas antes). Python `WinBuscaLucroG41RetanguloZeraCedo` (default `hora_zerar="17:00"`) e `..._congelado_v41.py` (conferido: jan-jun +R$2.603,00 / jul-ago +R$888,50 / set −R$324,00 = +R$3.167,50). EA `WinRetanguloEma34` v1.04 (`MinutoZerar=0`, mesma trava de entrada). Continua não validado — out/2026 é o teste.
