# Perguntas para decidir enquanto se opera

Perguntas para fazer antes, durante e depois de cada operação, e também ao pesquisar uma ideia nova. Servem para um operador e para uma IA que esteja decidindo.

## Como usar

- **As perguntas são abertas de propósito.** Não é "isto é um OCO?", e sim "existe alguma figura, nível ou comportamento aqui que mude a decisão?". A pergunta fechada faz olhar uma coisa só; a aberta obriga a varrer o gráfico inteiro antes de concluir.
- **Toda resposta precisa de evidência que se consiga apontar:** no gráfico, no livro, no extrato ou no histórico. "Parece que sim" não decide nada.
- **Toda resposta tem cinco usos possíveis:** entrar, não entrar, mudar a mão, mudar o stop ou mudar o alvo. Uma informação que piora o resultado também serve, como aviso.
- **Para cada resposta, pergunte também o contrário:** "e se for o oposto, o que eu faria?". Se a decisão seria a mesma nos dois casos, a pergunta não estava decidindo nada.
- **O que já foi medido** aparece em *itálico*, logo depois da pergunta. São resultados do WIN (escada M15 e os outros robôs). Use como ponto de partida, não como verdade eterna.

## Para uma IA responder a este arquivo

Regras práticas, tiradas das primeiras autópsias de dias ruins feitas por IA (10 dias da escada, 2026-10-09):

- **Momento.** Diga sempre se a resposta usa só o que se sabia até o instante da decisão (pode virar sinal) ou o dia inteiro (só explica). Numa autópsia, responda as duas versões separadas.
- **Sem dado, sem invenção.** Se o material não responde a pergunta (notícia, exterior, livro, plataforma, estado emocional), escreva "sem dado". Se a data sugerir um evento (Copom, FOMC, payroll, vencimento, fim de mês), escreva "suspeita" e o motivo.
- **Eventos pelo gráfico.** Em vez de adivinhar notícia, liste anomalias medidas, com a hora: volume acima de 2× a mediana daquele horário, vela acima de 2 ATR do tempo gráfico, ATR que dobra no dia.
- **Unidades.** Dê distâncias em pontos, em ATR do tempo gráfico e em ATR diário (média simples de 14 amplitudes verdadeiras diárias até a véspera). Um é cerca de 15 vezes o outro no M15; misturar os dois inverte conclusões.
- **Comparação precisa de referência.** Perguntas com "costuma", "se parece com as boas" ou "é normal" se respondem com o valor de hoje e o percentil dele numa tabela de referência (todas as operações, ou os dias bons). Sem a tabela, responda "sem referência".
- **Um dia não testa nada.** O bloco 0 e as comparações servem para cruzar vários dias, não para concluir a partir de um.
- **Stop.** Diga se o stop inicial foi o pivô ou o aperto, o resultado com cada um, e quantos R a mais teriam sobrevivido até o fim do dia.
- **"Dia ruim"** = pregão com resultado negativo da estratégia. Informe também o tamanho em R, porque −0,1R e −2R pedem leituras diferentes.
- **Material mínimo de uma autópsia:** operações com hora exata (M1) de entrada e saída e trajetória do stop; todos os sinais do dia com cada filtro; M15 dos dias anteriores com indicadores; M1 do dia com leilões; diário de 40 dias; H1 e H4; volume médio por horário dos 20 dias anteriores; calendário de eventos; o dólar no mesmo período; e uma tabela de referência das operações boas.


## Onde procurar: olhe para trás em todas as escalas

Uma decisão (ou uma autópsia) não olha só a vela do sinal. Antes de concluir, percorra o passado em camadas, da mais próxima à mais distante, e anote o que encontrar em cada uma. A lista é um ponto de partida, não um limite.

- **As velas imediatamente antes do sinal:** tamanho, corpo e sombras, velocidade, volume, se aceleraram ou perderam força, se houve uma vela fora do normal.
- **O próprio sinal:** como ele se formou, quanto tempo levou, o que os filtros e indicadores diziam naquele instante, se algum estava no limite.
- **O dia até ali:** abertura e leilão, gap, mini gaps (saltos entre o fechamento de uma vela e a abertura da seguinte), amplitude já feita, topos e fundos do dia, onde o preço está dentro da faixa do dia, que tipo de dia está se formando.
- **Os dias anteriores:** como fecharam (perto da máxima, da mínima, do meio), sequência de dias de alta e baixa, máxima e mínima de ontem, se hoje está dentro ou fora da faixa de ontem.
- **A semana e o mês:** onde o preço está em relação à abertura da semana e do mês, se a semana já andou muito, em que ponto do calendário estamos (vencimento, fim de mês, véspera de feriado).
- **Os tempos gráficos maiores:** tendência e estrutura no H1, H4 e diário, e se concordam com o sinal.
- **Outros mercados:** dólar, índice americano, as ações de maior peso, o que fizeram até a hora do sinal.
- **O histórico da própria estratégia:** como foram as últimas operações, em que condições ela costuma ganhar e perder.

## Raciocine por conta própria

Este arquivo não é um formulário para preencher; é um lembrete do que vale olhar. Quem estiver respondendo deve:

- **Levantar hipóteses próprias.** Se notar algo que nenhuma pergunta cobre, anote e diga por que pode importar. Os melhores achados costumam vir do que ninguém pensou em perguntar.
- **Desconfiar da primeira explicação.** Para cada padrão encontrado, procure ao menos uma explicação alternativa (horário, volume, tendência, acaso) e diga qual dados separariam as duas.
- **Pensar no oposto.** Se algo aparece nos dias ruins, pergunte se aparece também nos bons; se aparece nos bons, se aparece também nos ruins. Só o que DIFERE entre eles pode virar sinal.
- **Dizer o grau de certeza.** Separe "vi uma vez", "vi em vários dias" e "testado em todas as operações". Um dia só não prova nada, mas pode sugerir o que testar.
- **Propor o teste.** Ao terminar, diga como transformaria o que viu numa regra mensurável e como testaria sem viés (em dias que não foram usados para ter a ideia).
- **Melhorar este arquivo.** Se uma pergunta foi inútil, ambígua ou faltou alguma, proponha a mudança.

## Perguntas de decisão: universais, com gabarito por estratégia

As perguntas abaixo valem para qualquer estratégia. O que muda de uma estratégia para outra é o **gabarito**: qual resposta libera a ação, e com que régua concreta (qual média, qual tempo gráfico, qual limite) a pergunta é respondida. A resposta certa pode ser **sim** ou **não**; uma resposta "não" é tão útil quanto um "sim" quando o gabarito diz o que fazer com ela.

O gabarito da escada WIN M15 (v4.1) foi conferido: respondendo estas perguntas com a régua da escada, o resultado é **idêntico** ao do robô nos três períodos (2022–25: 416 operações, +61.989 pts; out/25–out/26: 109, +52.605; out–dez/21: 23, +1.582; 2 contratos, custo incluído).

### Entrada

| # | pergunta universal | régua da escada | resposta que libera | sim × não nos sinais (2022–25 / fora da amostra, pts por operação) |
|---|---|---|---|---|
| D1 | A estrutura de topos e fundos já confirmou a virada a favor? | ZigZag de 1,5 ATR no M15; fundo acima do anterior (compra) ou topo abaixo (venda) | **sim** | é o próprio sinal |
| D2 | A tendência do tempo gráfico maior, com a vela fechada, está contra a operação ou indefinida? | H1: fechamento × MME34 e MME9 × MME21 | **não** | não +44 × sim −32 / não +155 × sim −106 |
| D3 | O preço está do lado contrário à abertura do dia? | fechamento da vela do sinal × abertura do pregão | **não** | não +22 × sim −34 / não +65 × sim −60 |
| D4 | As médias rápida e lenta do tempo da operação estão contra a operação, ou empatadas? | MMS17 × MMS34 do fechamento, M15 | **não** | não +26 × sim −22 / não +63 × sim −31 |
| D5 | A média longa está inclinada contra a operação, ou plana? | MMS72 da abertura das velas, agora × 3 velas atrás | **não** | não +52 × sim −51 / não +144 × sim −112 |
| D6 | O preço já está esticado a favor (oscilador perto do extremo na direção da operação)? | Estocástico 14 (suav. 3) ≥ 70 a favor | **não**, ou D7 = sim | ver D7 |
| D7 | O tempo gráfico ainda maior está sem tendência? | H4 (blocos 9–13, 13–17, 17–fim) neutro | **sim** libera mesmo com D6 = sim | (D6 não ou D7 sim) +30 × −46 / +76 × −89 |
| D8 | Já existe uma posição aberta desta estratégia? | uma posição por vez | **não** | regra de execução |
| D9 | Resta pregão suficiente para a operação? | a vela seguinte ainda é do pregão; zera 5 min antes do fim | **sim** | regra de execução |

Juntas, as respostas certas levam um sinal que é quase cara ou coroa (+8 pts por operação em 2022–25) a +140; fora da amostra, de +28 a +396.

### Execução, stop e saída

| # | pergunta universal | gabarito da escada |
|---|---|---|
| E1 | Como entrar sem pagar a mais? | ordem limitada no fechamento da vela do sinal; nunca a mercado |
| E2 | Por quanto tempo a ordem vale, e o que acontece se o preço não voltar? | 3 velas M15; depois cancela |
| S1 | Onde fica o ponto que, se atingido, prova que a tese estava errada? | o fundo (compra) ou topo (venda) que gerou o sinal |
| S2 | Existe uma referência (média) entre esse ponto e a entrada, longe o bastante da entrada? | MME38 do M15 a mais de 0,25 ATR da entrada: **sim** → stop 0,2 ATR além dela |
| S3 | Desde a entrada, formou-se um novo fundo (topo) confirmado a favor? | **sim** → o stop sobe (desce) para ele; nunca recua |
| A1 | A estratégia precisa de alvo? | **não**: o ganho está nos dias que correm até o fim |
| X1 | O pregão está terminando? | **sim** (5 min antes do fim do contínuo) → zera |

### O que essas perguntas ensinam

- **Nenhuma sozinha basta;** cada uma separa pouco. O valor está na combinação.
- **As que funcionam olham o contexto, não a vela:** tempo maior, lado do dia, direção e inclinação das médias, quanto o preço já esticou. Perguntas só sobre a vela do sinal (padrões de vela, figuras, Fibonacci, médias curtas) não separaram nada na escada.
- **A régua e a resposta certa dependem da estratégia.** Exemplo medido: na escada, "o preço já está esticado a favor?" deve ser **não**; nos robôs de tendência do Maestro, as melhores entradas acontecem justamente com o oscilador esticado, e exigir "não" piorou todos eles.
- **Uma pergunta nova só acrescenta se separar os sinais que já passaram nas outras.** Quase tudo que mede tendência repete D2–D5.

### O que se mediu nos outros robôs (2026-10-09)

As mesmas perguntas D2–D7, com a mesma régua da escada, foram respondidas nas operações dos 5 robôs do Maestro (Cinco Médias, Deslocamento Matinal, Win_c1, Retângulo EMA34, GapBarra1). **Nenhuma separou de forma estável em nenhum deles.** Três situações apareceram, e o gabarito precisa distinguir as três:

- **Embutida:** a estratégia já só opera com uma das respostas (o Win_c1 só entra a favor do H1; o Deslocamento só de manhã e do lado da abertura). A pergunta está certa, mas já foi respondida pelo próprio sinal.
- **Não separa:** a resposta não muda o resultado daquela estratégia (para robôs de tendência e de horário fixo, o "preço esticado" e a média longa não importam). A pergunta continua valendo; a resposta dela, para essa estratégia, é "indiferente".
- **Libera com sim/não:** a resposta muda o resultado nos dois períodos (só aconteceu na escada: D2, D5 e o gap).

O que é universal, então, é a **lista de perguntas e o método**; a régua e a resposta certa são de cada estratégia. As perguntas D2–D7 descrevem bem estratégias de reversão como a escada. Para outros tipos, use também:

| # | pergunta universal | para que tipo de estratégia |
|---|---|---|
| D10 | O horário da entrada faz parte da tese (a estratégia só existe numa janela do dia)? | robôs de abertura e de horário fixo |
| D11 | O gap de abertura está a favor ou contra a operação, e já foi preenchido? | qualquer uma; na escada, gap a favor é **não** libera (pior com ele) |
| D12 | O padrão próprio da estratégia (retângulo, faixa, rompimento) está confirmado e com tamanho típico em ATR? | robôs de padrão |
| D13 | A tendência do tempo gráfico PRÓPRIO da estratégia está a favor? | robôs de tendência (costuma vir embutida) |

### Como montar o gabarito de outra estratégia

1. Liste os sinais brutos da estratégia (antes de qualquer filtro), cada um com o resultado de operá-lo sozinho.
2. Para cada pergunta D2–D7 (e outras que fizerem sentido), escolha uma régua concreta e responda sim/não em cada sinal, só com velas fechadas.
3. Meça o resultado médio com sim e com não no período de escolha. Fique com a resposta que separa e anote a régua.
4. Confira, sem mudar nada, num período que não foi usado, e compare com o acaso (sortear a mesma quantidade de sinais).
5. Escreva o gabarito numa tabela igual à de cima, marcando cada pergunta como **libera com sim**, **libera com não**, **embutida** ou **indiferente**. Se respondendo às perguntas com ele o resultado não for idêntico ao do robô, falta pergunta ou a régua está errada.

---

## 0. Antes de aceitar qualquer conclusão: em que condições ela foi tirada?

Este é o bloco mais importante. Uma conclusão ("isso funciona", "isso não funciona", "isso piora") vale só para as condições em que foi medida. Antes de usá-la, ou de descartá-la, liste o que foi fixado sem ninguém questionar, e pergunte se o resultado mudaria se cada item fosse diferente. *Exemplo real: as figuras e as velas foram testadas só no M15 e sozinhas; ninguém tinha perguntado se elas mudam quando aparecem em outro tempo gráfico ou junto de outros sinais.*

0.1. Em que tempo gráfico isso foi visto ou testado? O mesmo vale num tempo menor, num maior, ou quando aparece em vários ao mesmo tempo?
0.2. Em que período e em que regime de mercado? Vale em outro ano, em tendência e em lateral, em volatilidade alta e baixa?
0.3. Em que horário do pregão? O efeito é o mesmo na abertura, no meio do dia e no fim?
0.4. Em que ativo, contrato e série de dados (contínua, ajustada, sem leilão)? A conclusão sobrevive à troca da série?
0.5. Com que definição exata? Uma definição mais rígida ou mais solta do mesmo conceito dá o mesmo resultado?
0.6. Com que parâmetros e janelas? Os vizinhos dão o mesmo resultado, ou o número depende de um valor escolhido?
0.7. Sozinho ou combinado? A informação foi vista isolada; e junto de outras, ela soma, repete ou se anula?
0.8. Em qual uso? Foi testada como entrada; e como aviso, mão, stop ou alvo?
0.9. Em qual lado? Compra e venda se comportam igual, ou a média esconde dois comportamentos opostos?
0.10. Com que execução e custo? O teste assumiu um preço, uma fila e um custo que a corretora entrega de verdade?
0.11. Com que amostra? Quantos casos sustentam a conclusão, e quem escolheu esses casos?
0.12. Medida por qual régua? Acerto, lucro, queda, lucro/queda? A conclusão muda se a régua mudar?
0.13. Contra o quê? Comparada com o acaso, com a versão atual, ou com nada?
0.14. O que mais estava acontecendo naqueles casos (hora, volume, tendência) que pode ser a causa real, e a informação estudada só um disfarce dela?
0.15. Quais destas perguntas eu ainda não fiz sobre a conclusão que estou prestes a usar?

## 1. Antes do pregão

1. O que aconteceu desde o último fechamento (noite, exterior, notícias) que pode mudar o comportamento de hoje?
2. Como o mercado vai abrir em relação a ontem, e qual o tamanho desse salto em ATR? *Gap grande muda o dia; os robôs com filtro de gap deixam de operar acima de 1 ATR diário.*
3. Quais níveis de preço dos últimos dias o mercado provavelmente vai visitar hoje, e por quê?
4. Existe algum evento programado hoje (economia, BC, vencimento, leilão, feriado lá fora) que mude a liquidez ou a volatilidade? Em que horário?
5. Que tipo de dia os sinais da abertura sugerem: tendência, lateral, reversão do gap? O que me faria mudar essa leitura?
6. Qual é o contrato vigente, e existe alguma rolagem ou vencimento perto que distorça preço, volume ou a série histórica?
7. Qual é a grade horária da B3 que vale hoje? *O fim do contínuo muda com o horário de verão americano; horário fixo no código já fez o robô zerar na hora errada.*
8. Quanto caixa existe de verdade, e quanto dele está comprometido com margem, outros robôs e posições abertas?
9. O caixa aguenta a pior sequência de perdas já medida para a estratégia e para o tamanho de mão de hoje, com folga para uma pior ainda?
10. Qual é a perda máxima aceitável hoje, e o que acontece quando eu chegar nela?
11. O que deu errado nas últimas sessões que pode se repetir hoje, e o que mudou desde então?
12. Existe algum robô ou ordem esquecida da sessão anterior que ainda esteja viva na conta?

## 2. Leitura do contexto

13. Em que regime o mercado está agora (tendência, lateral, alta volatilidade, baixa liquidez), e o que mostra isso?
14. Os tempos gráficos maiores concordam com o menor? Onde há divergência, qual deles costuma mandar nesta estratégia? *Na escada, a tendência do H1 a favor é filtro obrigatório; o H4 neutro também libera.*
15. Onde o preço está em relação às referências do dia (abertura, máxima, mínima, fechamento anterior), da semana e do mês? *O lado da abertura do dia é filtro da escada; o preço contra a abertura do mês foi a única pista de regime mensal que melhorou alguma coisa.*
16. Quanto o mercado já andou hoje (máxima − mínima desde a abertura) em ATR diário, e em que percentil isso fica entre os dias do histórico na mesma hora? Que fração da amplitude típica de um dia ainda sobra? *Nas autópsias de 10 dias ruins da escada, 8 entraram com o dia já tendo feito ≥ 0,75 ATR diário ("dia esgotado"); em teste nos dias bons e fora da amostra.*
17. A estrutura de topos e fundos está ficando mais forte ou mais fraca? Liste os últimos pivôs (hora, preço, tamanho da perna em ATR, número de velas, volume) e compare as duas últimas pernas com a média das pernas do dia.
18. Os ativos que costumam andar junto (dólar, índice americano, ações de maior peso) confirmam ou contradizem o movimento? *A confirmação cruzada WIN×WDO só apareceu como "estado anômalo", não como sinal.*
19. Existe algo fora do normal hoje (volume, amplitude, velocidade, spread, buracos no gráfico) que torne o histórico menos parecido com o presente?
20. Que informação eu estou ignorando porque ela não está no meu gráfico de costume?
21. Se eu olhasse só o diário, o que concluiria? E só o M1? Onde as duas leituras se chocam?

## 3. Médias, indicadores e osciladores

22. Existe alguma média ou indicador que eu use dizendo algo diferente dos outros? Qual deles tem teste que o sustente?
23. Os indicadores que estão "confirmando" medem coisas diferentes, ou são a mesma informação repetida (todas médias, todos osciladores)? *Roxa×verde e médias curtas foram redundantes com os filtros que a escada já tem.*
24. O preço está esticado em relação a alguma média ou banda? Em que medida isso costumou importar nesta estratégia? *Distância grande da MME38 não mudou o resultado da escada.*
25. Algum oscilador está em extremo? O extremo está a favor ou contra a operação? *Estocástico abaixo de 70 a favor é o "sinal bom" da escada: o acerto sobe de ~40% para 51–62%. Nos robôs de tendência, ao contrário, as entradas acontecem justamente com o estocástico esticado, e filtrar por ele piorou todos.*
26. A volatilidade (ATR, amplitude) está acima ou abaixo do normal, e o stop e o alvo foram dimensionados para a volatilidade de agora ou a de outro dia?
27. O volume recente confirma o movimento ou o movimento está acontecendo sem participação? *Volume alto nas últimas velas foi a pista mais forte na escada, mas em grande parte é o efeito "manhã".*
28. Existe divergência entre preço e algum indicador? Ela já foi testada como sinal ou é só aparência? *Divergência de oscilador foi refutada (0 de 48).*
29. Que indicador eu estou usando por hábito, sem ter medido se ele muda o resultado?
30. Se eu tirasse todos os indicadores da tela, o que o preço sozinho estaria mostrando?

## 4. Estrutura, figuras e padrões

31. Existe alguma estrutura de preço recente (figura, canal, retângulo, falha de rompimento) que mude a decisão? Ela favorece ou contraria a operação? *Figuras gráficas contra o sinal não pioraram a escada; as nítidas são raras. O retângulo tem estudo próprio (padrão G37).*
32. Existe algum nível onde o preço já reagiu várias vezes, e onde ele está em relação à entrada, ao stop e ao alvo?
33. A correção atual tem algo de diferente das correções que funcionaram (profundidade, duração, velocidade, volume)? *Profundidade em Fibonacci, número de velas e razão entre pernas não separaram boas de ruins.*
34. Existe algum padrão de velas ou de sequência que eu esteja vendo como sinal? Ele tem teste? *Candles, cor das velas, sequência de cor e volume: todos refutados no WIN.*
35. A última perna mostra força ou cansaço comparada com as anteriores?
36. Existe algum padrão que, quando aparece, costuma marcar operações piores? Eu o uso para reduzir a exposição?
37. O que no gráfico contradiz a minha tese? Procurei ativamente?
38. Se o padrão que eu estou vendo falhar, o que isso diria sobre o mercado? Existe operação na falha? *O OCO tinha 33% de acerto operando o rompimento; operar ao contrário apareceu como candidato fraco, não confirmado.*

## 5. Horário, calendário e eventos

39. Em que fase do pregão estamos, e como esta estratégia costuma se comportar nela? *A escada vai pior com sinal depois das 15h (−33 contra +187 pts por operação em 2024–25): pista, ainda não regra.*
40. Quanto tempo resta até o fim do contínuo, e esse tempo é suficiente para a operação se desenvolver?
41. Existe algum evento nos próximos minutos ou horas que possa mudar o mercado de repente?
42. O dia de hoje tem alguma característica de calendário (vencimento, véspera, início/fim de mês, dia da semana) que costume mudar o comportamento? *Dia da semana, quarta de vencimento e calendário foram testados e não viraram regra.*
43. A primeira barra do dia ou o leilão estão contaminando a leitura? *O M1 do WIN contém os leilões (1ª barra e 18:24); estudos que não os removem leem preço que não é negociação contínua.*
44. Quais são os dias do histórico mais parecidos com hoje (gap, amplitude até agora, volatilidade, calendário), e como a estratégia se saiu neles?

## 6. O sinal e a decisão de entrar

45. O sinal está completo pela regra, ou estou antecipando algo que ainda não se confirmou?
46. Quais condições da regra estão a favor e quais estão contra? Se alguma está contra, por que estou considerando entrar?
47. Existe algum motivo além da regra me empurrando para entrar (recuperar perda, medo de ficar de fora, tédio)?
48. Este sinal se parece com os que deram certo ou com os que deram errado no histórico? Em que exatamente?
49. Se eu não entrar e o preço for a favor, o que eu perco? Se eu entrar e for contra, o que eu perco? A conta é a mesma da regra?
50. Existe outra operação aberta (minha ou de outro robô) que mude o risco desta entrada?
51. Esta entrada depende de alguma informação que eu só teria depois, ou de algo que não aparece no gráfico em tempo real?
52. Existe algum sinal de aviso (horário, volume, estrutura, notícia) que mande não entrar ou entrar menor?
53. Se outra pessoa me mostrasse este gráfico sem me dizer o lado, eu escolheria o mesmo lado?

## 7. Execução da entrada

54. Como vou entrar, e esse modo de entrada tem caminho real na corretora? *Nunca a mercado na entrada: só ordem limitada. A entrada a mercado simulada pelo preço de abertura da barra descreve um robô que não existe.*
55. Por quanto tempo a ordem fica viva, e o que acontece se ela não encher? *Sem prazo, a limitada já encheu 270 minutos depois do sinal, com o preço passando por acaso.*
56. Quantos contratos estão na frente da minha ordem no livro, e quanto tempo a fila costuma levar para chegar a mim? *Tocar o preço não é encher: a fila medida foi de ~440 contratos na entrada e ~490 na saída (WDO).*
57. O preço já passou do meu limite? Eu persigo, espero ou desisto, e qual dessas a regra manda?
58. A ordem foi aceita, e o stop foi registrado junto, no servidor?
59. O preço de entrada real ficou igual ao planejado? Se não, por quê, e quanto isso custa por operação?
60. Existe alguma diferença entre o que o backtest assume sobre a entrada e o que a corretora faz de verdade?

## 8. Stop

61. Onde o stop precisa estar para só ser atingido se a tese estiver errada, e não pelo ruído normal? Quantos R de stop teriam sobrevivido em dias parecidos, e esse stop cabe dentro da faixa já feita no dia? *Em 2 dos 10 dias ruins analisados, o aperto do stop pela MME38 transformou ganho em perda; nos outros, um stop maior só trocaria uma perda por outra.*
62. Quanto o stop custa em reais com a mão de hoje, e isso cabe na perda aceitável?
63. O stop está registrado na corretora? Se o computador ou a internet caírem agora, o que acontece?
64. O que faz o stop se mover, e a regra de movimento é a mesma do backtest? *Na escada, o stop sobe a cada novo topo/fundo confirmado a favor e nunca recua.*
65. Existe alguma vontade de mudar o stop sem regra (afastar porque chegou perto, apertar por medo)? *Afastar é proibido. Apertar piorou a escada em todos os testes: média curta, Fibonacci, zero a zero, stop pela metade.*
66. Existe algum nível ou informação nova que justifique um stop diferente? Isso foi testado como regra?
67. Quando o stop for executado, a que preço ele sai? O stop desliza como o alvo? *Stop a mercado é a única exceção à regra da limitada; medido, ele não deslizou contra (5 de 5).*

## 9. Alvo e saída

68. A estratégia precisa de alvo, ou o ganho dela vem dos dias que correm até o fim? *A escada não tem alvo; todo alvo testado (Fibonacci, sobrevivência, 1R, parcial) cortou os dias grandes e perdeu.*
69. Se há alvo, ele é ordem limitada parada no livro? *O alvo nativo da plataforma é varrido a mercado: 10 de 11 saídas deslizaram contra, 58% do lucro teórico.*
70. Um alvo de poucos ticks vai encher na prática, considerando a fila? *Alvo de 1 tick é proibido: o nível mais disputado do livro.*
71. Existe algum motivo, além da regra, me empurrando para sair agora (garantir lucro, medo de devolver)?
72. Se eu sair agora e o preço continuar a favor, a regra me deixa entrar de novo? Com que critério?
73. Qual saída o histórico mostra que funciona melhor para esta estratégia: stop pela estrutura, tempo, alvo, fim do dia? Eu estou usando essa?
74. Até que horas a posição pode ficar aberta, e o que garante que ela será zerada no horário? *Já houve robô cujo "zerar no fim do dia" nunca disparou.*

## 10. Tamanho da mão e exposição

75. Quantos contratos a regra manda, e quantos cabem no caixa de hoje com margem e reserva?
76. Somando todos os robôs e operações manuais na mesma conta, qual é a exposição total no mesmo ativo? *Conta NETTING soma tudo; exposição agregada de dois robôs zerou uma conta.*
77. Se tudo der errado ao mesmo tempo, quanto do caixa vai embora?
78. Existe alguma informação (aviso, regime, horário) que justifique mão menor ou maior agora? Ela foi testada? *Nenhum aviso passou ainda; os mais perto foram "tarde" e "cruzamento curto contra", com mão de 1 contrato.*
79. Estou mudando a mão por causa do resultado recente? *Na escada, depois de uma sequência ruim a operação seguinte costuma ser melhor; reduzir a mão por isso não se sustenta.*
80. O caixa mínimo que eu uso é o de começar ou o de continuar? Estou confundindo os dois? *O piso de capital indica a partida; continuar exige só a margem.*

## 11. Durante a operação

81. O cenário que justificou a entrada ainda existe? O que mudou?
82. Se eu estivesse fora agora, entraria? Se não, por que continuo?
83. A operação está se comportando como as boas ou como as ruins do histórico? Em quê?
84. O que o robô acha que tem (posição, ordens, stop) bate com o que a corretora mostra?
85. Existe alguma ordem viva que eu não reconheço, ou alguma que eu cancelei e continua lá? *Cancelamentos silenciosos já deixaram ordens órfãs.*
86. Apareceu algum alerta (rejeição, desconexão, margem, dado parado)?
87. Estou olhando o gráfico ou o resultado em reais?

## 12. Risco do dia e da conta

88. Quanto já ganhei ou perdi hoje, e quanto ainda posso perder antes de parar?
89. A sequência atual de perdas está dentro do que o histórico mostra, ou já é maior que a pior medida?
90. A estratégia está operando com a frequência normal, ou parou de operar por algum motivo (caixa, trava, erro)? *Robô que para de operar em silêncio parece "sem sinal" quando na verdade está bloqueado.*
91. Existe alguma trava ou limite no robô que eu não pedi e que esteja mudando o comportamento?
92. Se o robô reiniciar agora, ele recupera o estado (posição, stop, ordem pendente)? *Já houve "memória perdida" na reinicialização.*

## 13. Dados e plataforma

93. Os dados que estou vendo estão atualizados, completos e no fuso certo?
94. A série que estou analisando é a mesma que a estratégia foi testada? *WIN@ é ajustado; o histórico usa WIN$N sem leilões. Séries diferentes dão sinais diferentes.*
95. Existe buraco de dados hoje ou nos dias usados para calcular os indicadores?
96. O gráfico está no contrato que aceita ordem, e não na série contínua?
97. A plataforma e o robô estão na versão que foi testada? O que mudou desde o último teste?
98. O log mostra o motivo de cada decisão? Eu conseguiria reconstruir esta operação só pelo log?

## 14. Depois da operação

99. A operação seguiu a regra do começo ao fim? Onde saiu dela, e por quê?
100. O resultado real bate com o que o backtest daria para o mesmo momento? Se não, onde está a diferença: entrada, saída, fila, custo?
101. Quanto custou a execução (deslize, fila, taxas) comparado com o que o modelo assume?
102. Em que condições a operação aconteceu (hora, volume, regime, distância das médias)? Ela se parece com as boas ou com as ruins?
103. Quanto a operação andou a favor e contra antes de sair? O stop e o alvo estavam no lugar certo?
104. A regra foi seguida (sim/não)? Havia alguma condição contra no momento da entrada (qual)? *Perda dentro da regra não é erro e não pede mudança.*
105. O que uma linha no diário diria sobre esta operação?

## 15. Pesquisa: antes de acreditar numa ideia

106. De onde veio a ideia, e os dados que a geraram vão entrar no teste? *Um filtro escolhido num funil de 30 dias só parecia bom por causa desses dias.*
107. A ideia foi testada em dados que não foram usados para criá-la?
108. Testei em dias ruins e em dias bons, sorteados, e não só nos que me chamaram atenção? *Começar pelos piores dias premia quem só opera menos.*
109. Quantas variantes eu testei, e quantas passariam por puro acaso? *Com 30–50 variantes, 1 ou 2 "passam" sozinhas; corrija para múltiplas comparações.*
110. Comparei com o acaso: cortar ao sorteio a mesma quantidade de operações dá resultado parecido?
111. O parâmetro vizinho também funciona, ou é um pico isolado?
112. O resultado depende de poucos dias ou de poucas operações? Sem eles, continua de pé? *Uma única operação já respondia por 54% do resultado de uma carteira.*
113. O resultado se mantém em outro período, outro ano, outro tempo gráfico, outro ativo?
114. A melhora vem de a estratégia operar melhor, ou de cortar operações num período que já era fraco?
115. A ideia é nova, ou é um efeito já conhecido visto por outro ângulo (horário, volume, tendência)?
116. O modelo de execução do teste é o mesmo da produção: ordem limitada, fila, deslize, custo, horário de zeragem?
117. A janela de teste ficou censurada (o robô parou de operar por caixa ou trava)? *Um "−R$76" que parecia falta de edge eram 2 operações em 51 pregões.*
118. O número pode ter vindo de olhar o futuro sem querer (indicador calculado com a vela ainda aberta, dado de fechamento usado antes da hora)?
119. A estimativa de espera ou de fila usou só os casos que deram certo? *Contar só as ordens que encheram subestima a fila, sempre para o mesmo lado.*
120. Um parâmetro de realismo (fila, deslize, custo) está ligado e calibrado, ou existe com valor zero e parece coberto?
121. O custo medido é do mercado, ou do caminho que eu escolhi para executar? Existe outro caminho que não pague esse custo?

## 16. Pesquisa: os cinco usos de cada informação

122. Esta informação melhora a escolha de quando entrar?
123. Ela marca operações piores que a média? Então serve como aviso para não entrar?
124. Ela sugere usar mais ou menos contratos?
125. Ela muda onde o stop deveria estar ou como ele deveria andar?
126. Ela muda onde o alvo deveria estar, ou se deveria haver alvo?
127. Quando a ideia piora muito o resultado, o que exatamente piorou: ela cortou operações boas (então o contrário já é a regra atual) ou as operações com ela são piores (então é um aviso)?
128. O efeito da informação é o mesmo de manhã e à tarde, com volume alto e baixo, em tendência e em lateral?

## 17. Pesquisa: decidir se muda

129. A mudança melhora a versão atual nos dois períodos (o de escolha e o de fora), ou só numa delas?
130. O que ela troca: lucro por menos queda, ou lucro por lucro? A troca vale para o meu caixa?
131. Quanto dinheiro de caixa mínimo a mudança exige a mais ou a menos?
132. A regra nova é simples o bastante para ser executada igual no robô, na plataforma e no papel?
133. O que eu faria se a mudança não estivesse disponível? A estratégia atual já não resolve?
134. Se a mudança for adotada e der errado, como eu vou perceber, e em quanto tempo?
135. Anotei o resultado, inclusive o negativo, para ninguém testar a mesma coisa de novo?
136. A ideia que falhou aqui pode servir em outra estratégia, outro ativo ou outro uso (aviso, mão, stop, alvo)?

## 18. Para a IA que estiver decidindo

137. Que informação eu ainda não olhei, e que poderia inverter a minha conclusão?
138. Estou ancorado numa explicação só? Quais outras duas explicações cabem nos mesmos dados?
139. A minha resposta depende de algum número que eu não verifiquei nesta sessão?
140. O que o operador sabe e eu não sei (contexto, notícia, plataforma, decisões anteriores)? Devo perguntar antes de agir?
141. Estou repetindo uma conclusão antiga sem conferir se ela ainda vale para os dados de agora?
142. Esta decisão tem volta? Se não tiver, já confirmei com o dono?
143. Se eu estiver errado, qual é o pior resultado possível, e ele está protegido?
