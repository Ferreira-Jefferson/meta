# Catálogo de perguntas (WIN M15) — novas (N01–N50) e existentes medidas (C, T, D, Q)

Resposta esperada = a que, segundo a literatura/o arquivo, favorece a COMPRA (venda = espelho: preços invertidos). Só velas fechadas até a vela da pergunta; ATR diário até D-1. 'sem lado' = pergunta que descreve o regime e não a direção (no alvo simétrico não pode separar nada; serve só como modificador).

| # | origem | pergunta | família | régua (WIN M15) | tipo | esperada (compra) | fonte / justificativa | peso IS | classe |
|---|---|---|---|---|---|---|---|---|---|
| N01 | nova | O preço está acima do VWAP do dia? | VWAP/perfil | fechamento M15 > VWAP acumulado do dia (preço típico x volume) | sim/não | sim | VWAP é a referência institucional do dia; acima = compradores no controle do custo médio | +0.014 | INERTE |
| N02 | nova | O preço está esticado em relação ao VWAP (mais de 1,5 ATR acima)? | VWAP/perfil | (fechamento − VWAP)/ATR M15 > 1,5 | sim/não | não | esticamento em relação à média ponderada tende a devolver (reversão à média) | -0.027 | INERTE |
| N03 | nova | O VWAP está inclinado a favor? | VWAP/perfil | VWAP agora > VWAP 4 velas atrás (mesmo pregão) | sim/não | sim | VWAP subindo = fluxo comprador persistente (Dalton/Grimes) | +0.038 | INERTE |
| N04 | nova | O preço acabou de retomar o VWAP por cima (estava abaixo nas últimas 3 velas)? | VWAP/perfil | fechou > VWAP e alguma das 3 velas anteriores fechou <= VWAP | sim/não | sim | retomada de nível-chave com sustentação (Wyckoff/Brooks: failed breakdown) | -0.053 | FRACA |
| N05 | nova | O preço está acima do ponto de controle (POC) do dia? | VWAP/perfil | POC = faixa de 100 pts com mais volume acumulado no dia; fechamento > POC (a partir das 10:00) | sim/não | sim | Market Profile: preço acima do POC = aceitação em valores mais altos | +0.015 | FRACA |
| N06 | nova | Onde o preço está em relação à área de valor de ontem? | VWAP/perfil | área de valor = 70% do volume de ontem em torno do POC; 0 = abaixo, 1 = dentro, 2 = acima | categoria (3) | acima (2) | Dalton: aceitação acima do valor de ontem favorece continuidade de alta | +0.029 | FRACA |
| N07 | nova | A abertura do dia ficou dentro ou fora da faixa de ontem? | Níveis de ontem | abertura do pregão vs máxima/mínima de ontem; 0 = abaixo da mínima, 1 = dentro, 2 = acima da máxima | categoria (3) | acima (2) | Dalton: abertura fora da faixa anterior = convicção direcional | -0.016 | INERTE |
| N08 | nova | O preço rompeu a máxima de ontem e sustenta (2 fechamentos acima)? | Níveis de ontem | fechamento e fechamento anterior > máxima de ontem | sim/não | sim | Dow/Murphy: rompimento só vale com confirmação de fechamento | +0.060 | FRACA |
| N09 | nova | O preço perdeu a mínima de ontem (fechou abaixo)? | Níveis de ontem | fechamento < mínima de ontem | sim/não | não | perda de suporte do dia anterior sinaliza fraqueza (Murphy) | +0.018 | INERTE |
| N10 | nova | Houve rompimento falso para baixo da mínima de ontem (rompeu e voltou) nas últimas 8 velas? | Níveis de ontem | mínima das últimas 8 velas do dia < mínima de ontem e fechamento atual > mínima de ontem | sim/não | sim | Wyckoff (spring) e Brooks (failed breakout): armadilha de vendedores | -0.040 | FRACA |
| N11 | nova | Ontem o preço fechou no terço superior da própria faixa? | Dias anteriores | (fech. − mín.)/(máx. − mín.) de ontem ≥ 0,67 | sim/não | sim | fechamento perto da máxima tende a continuar no dia seguinte (Crabel, L. Williams) | +0.031 | FRACA |
| N12 | nova | Ontem foi dia de alta (fechou acima da abertura)? | Dias anteriores | fechamento de ontem > abertura de ontem | sim/não | sim | momentum diário (série temporal) persiste no curto prazo | +0.035 | INERTE |
| N13 | nova | O mercado fechou 3 dias seguidos contra a operação? | Dias anteriores | 3 fechamentos diários consecutivos de queda (compra) | sim/não | sim | Connors/Alvarez: série de 3 dias contra tende a reverter no curto prazo | +0.061 | INSTÁVEL |
| N14 | nova | Ontem foi um inside day (faixa dentro da faixa de anteontem)? (sem lado) | Volatilidade/regime | máx. de ontem < máx. de anteontem e mín. de ontem > mín. de anteontem | sim/não | sim | Crabel: contração diária precede expansão (sem direção) | +0.000 | INERTE |
| N15 | nova | Ontem foi o dia de menor faixa dos últimos 7 (NR7)? (sem lado) | Volatilidade/regime | faixa de ontem é a menor das 7 últimas faixas diárias | sim/não | sim | Crabel (NR7): dia estreito antecede expansão (sem direção) | +0.000 | INERTE |
| N16 | nova | O preço está acima da abertura da semana? | Níveis de referência | fechamento > primeira abertura da semana | sim/não | sim | referência semanal (Murphy/Grimes): lado do preço vs abertura do período | +0.014 | FRACA |
| N17 | nova | O preço está acima da abertura do mês? | Níveis de referência | fechamento > primeira abertura do mês | sim/não | sim | referência mensal; já apareceu como única pista de regime mensal no projeto | +0.032 | INERTE |
| N18 | nova | O preço superou a máxima dos últimos 10 dias? | Tendência/momentum | fechamento > máxima dos 10 pregões anteriores | sim/não | sim | Donchian/Turtle: rompimento de canal de 10 dias (Murphy) | +0.014 | FRACA |
| N19 | nova | O preço está acima da média simples de 20 dias? | Tendência/momentum | fechamento > média dos 20 fechamentos diários até ontem | sim/não | sim | Dow/Murphy: tendência primária pelo lado da média de 20 dias | +0.048 | FRACA |
| N20 | nova | O mercado subiu nos últimos 5 dias (momentum diário)? | Tendência/momentum | fechamento de ontem > fechamento de 6 dias atrás | sim/não | sim | Moskowitz-Ooi-Pedersen: momentum de série temporal | -0.001 | INERTE |
| N21 | nova | O preço está acima da média simples de 200 velas M15? | Tendência/momentum | fechamento > MMS200 do M15 (~7 pregões) | sim/não | sim | Murphy: média longa como filtro de tendência | +0.037 | FRACA |
| N22 | nova | Em que terço da faixa do dia o preço está? | Posição no dia | (fech. − mín. do dia)/(máx. − mín. do dia); 0 = inferior, 1 = meio, 2 = superior (faixa ≥ 0,25 ATR diário, após 10:00) | tercil (3) | superior (2) | Brooks/Grimes: fechar perto da máxima do dia = pressão compradora (trend day) | +0.048 | INSTÁVEL |
| N23 | nova | Quanto o preço se deslocou desde a abertura, em ATR diário? | Posição no dia | (fech. − abertura do dia)/ATR diário; 0 = contra (≤ −0,4), 1 = neutro, 2 = a favor (≥ +0,4) | faixa (3) | a favor (2) | Gao et al. 2018 / momentum intradiário: o dia tende a continuar na direção já feita | +0.111 | FRACA |
| N24 | nova | O preço fechou acima da faixa dos primeiros 60 minutos (ORB)? | Faixa inicial | fechamento > máxima de 09:00–10:00 (só após 10:00) | sim/não | sim | Crabel (Opening Range Breakout) | +0.076 | FRACA |
| N25 | nova | A faixa dos primeiros 60 minutos foi estreita (< 0,25 ATR diário)? (sem lado) | Faixa inicial | (máx. − mín. de 09:00–10:00)/ATR diário < 0,25 | sim/não | sim | Crabel: contração inicial antecede dia de tendência (sem direção) | +0.000 | INERTE |
| N26 | nova | As últimas 12 velas formam uma faixa lateral estreita? (sem lado) | Volatilidade/regime | máx. − mín. das 12 últimas velas ≤ 2,5 ATR M15 | sim/não | sim | lateralização/compressão (Wyckoff, Bollinger): precede expansão (sem direção) | +0.000 | INERTE |
| N27 | nova | A volatilidade está em contração (ATR atual < 0,8× a média das últimas 100 velas)? (sem lado) | Volatilidade/regime | ATR14 M15 < 0,8 × média de 100 valores | sim/não | sim | volatilidade é persistente e agrupa em regimes (Mandelbrot/Engle) | +0.000 | INERTE |
| N28 | nova | A volatilidade está em expansão (ATR atual > 1,2× a média das últimas 100 velas)? (sem lado) | Volatilidade/regime | ATR14 M15 > 1,2 × média de 100 valores | sim/não | sim | idem; expansão favorece rompimentos | +0.000 | INERTE |
| N29 | nova | As bandas de Bollinger estão em aperto (squeeze)? (sem lado) | Volatilidade/regime | largura das bandas (20,2) ≤ 1,1× a menor das últimas 100 velas | sim/não | sim | Bollinger: aperto antecede expansão (sem direção) | +0.000 | INERTE |
| N30 | nova | O volume desta vela está bem acima do normal do horário? (sem lado) | Volume | volume da vela ≥ 1,5× a média do mesmo horário nos 20 pregões anteriores | sim/não | sim | Wyckoff: esforço; volume anormal marca participação institucional (sem direção) | +0.000 | INERTE |
| N31 | nova | O volume acumulado do dia está acima do normal até este horário? (sem lado) | Volume | volume acumulado ≥ 1,2× a média do mesmo horário nos 20 pregões anteriores | sim/não | sim | dia ativo/informado (sem direção) | +0.000 | INERTE |
| N32 | nova | A vela fechou de alta com volume bem acima do normal? | Volume | fechamento > abertura e volume ≥ 1,5× o normal do horário | sim/não | sim | Wyckoff: esforço e resultado alinhados (demanda real) | +0.008 | FRACA |
| N33 | nova | Houve vela de baixa com volume alto que fechou na metade superior (absorção)? | Volume | fechamento < abertura, volume ≥ 1,5×, fechamento acima do ponto médio da vela | sim/não | sim | Wyckoff: esforço sem resultado = absorção por compradores | -0.041 | FRACA |
| N34 | nova | Houve clímax vendedor nas últimas 4 velas? | Volume | vela de baixa com faixa ≥ 2 ATR e volume ≥ 2× o normal, nas últimas 4 velas | sim/não | sim | Wyckoff (selling climax): exaustão vendedora marca fundo | -0.048 | FRACA |
| N35 | nova | Houve spring de Wyckoff (perdeu o suporte das 20 velas e voltou) nas últimas 10 velas? | Estrutura | mínima das 10 últimas < mínima das velas [-30,-10] e fechamento atual acima dela | sim/não | sim | Wyckoff: spring/teste do suporte | -0.024 | INSTÁVEL |
| N36 | nova | A tendência é forte e a favor (ADX ≥ 25 com +DI > −DI)? | Tendência/momentum | ADX(14) ≥ 25 e +DI > −DI no M15 | sim/não | sim | Wilder: ADX mede força, DI o lado | +0.080 | FRACA |
| N37 | nova | O índice direcional positivo está acima do negativo (+DI > −DI)? | Tendência/momentum | +DI(14) > −DI(14) no M15 | sim/não | sim | Wilder | +0.026 | INERTE |
| N38 | nova | A MME50 do M15 está subindo e o preço acima dela? | Tendência/momentum | MME50 agora > MME50 3 velas atrás e fechamento > MME50 | sim/não | sim | Murphy: média inclinada + preço do lado certo | +0.036 | INERTE |
| N39 | nova | Os últimos dois topos e os últimos dois fundos são ascendentes (Dow)? | Estrutura | fractais 2-2 confirmados: último topo > anterior e último fundo > anterior | sim/não | sim | Teoria de Dow: tendência de alta = topos e fundos ascendentes | +0.043 | INSTÁVEL |
| N40 | nova | O preço subiu pelo menos 1 ATR nas últimas 16 velas (4 horas)? | Tendência/momentum | (fech. − fech. 16 velas atrás)/ATR M15 ≥ 1 | sim/não | sim | momentum de curto prazo (Jegadeesh-Titman, versão intradiária) | +0.022 | INERTE |
| N41 | nova | Há divergência altista entre preço e RSI? | Momentum × reversão | mínima de preço das 12 últimas < das 12 anteriores e mínima do RSI14 das 12 últimas > das 12 anteriores | sim/não | sim | Murphy/Wilder: divergência de oscilador (já refutada no projeto) | -0.027 | FRACA |
| N42 | nova | O RSI está em sobrevenda (≤ 30)? | Momentum × reversão | RSI(14) M15 ≤ 30 | sim/não | sim | Wilder: extremo do oscilador contra o lado = reversão | -0.199 | FRACA |
| N43 | nova | O RSI está na zona de alta (acima de 50)? | Momentum × reversão | RSI(14) M15 > 50 | sim/não | sim | Cardwell/Brown: RSI > 50 = regime de alta (momentum, oposto da sobrevenda) | +0.009 | INERTE |
| N44 | nova | O preço fechou abaixo da banda inferior de Bollinger? | Momentum × reversão | fechamento < média 20 − 2 desvios (M15) | sim/não | sim | Bollinger: fora da banda contra = reversão à média | -0.033 | FRACA |
| N45 | nova | O histograma do MACD é positivo e crescente? | Tendência/momentum | MACD(12,26,9) histograma > 0 e > valor anterior | sim/não | sim | Appel: momentum positivo e acelerando | -0.028 | INERTE |
| N46 | nova | A última perna é a favor e mais forte que a anterior (aceleração)? | Força relativa | variação das últimas 6 velas > 0 e maior em módulo que a das 6 anteriores | sim/não | sim | Elliott/Dow: onda de impulso mais forte que a correção anterior | +0.017 | INERTE |
| N47 | nova | O retorno da primeira meia hora foi a favor? | Sazonalidade intradiária | fechamento das 2 primeiras velas (09:00–09:30) > abertura do dia (válido a partir das 09:30) | sim/não | sim | Gao-Han-Li-Zhou 2018: a 1ª meia hora prevê o resto do dia | -0.011 | INERTE |
| N48 | nova | O preço está acima do fechamento de ontem? | Níveis de referência | fechamento > fechamento do pregão anterior | sim/não | sim | referência clássica (Murphy); gap preenchido ou não | +0.007 | INERTE |
| N49 | nova | O preço está colado (< 0,5 ATR) abaixo de um número redondo (múltiplo de 1.000 pontos)? | Níveis de referência | (próximo múltiplo de 1.000 ≥ fechamento − fechamento)/ATR M15 < 0,5 | sim/não | não | números redondos atraem ordens e funcionam como resistência (Grimes) | -0.007 | INERTE |
| N50 | nova | O dólar (WDO) caiu nas últimas 4 velas? | Intermercado | WDO@D M15: fechamento < fechamento 4 velas atrás (mesmo pregão) | sim/não | sim | correlação inversa dólar × bolsa brasileira (Murphy, análise intermercados) | +0.002 | INERTE |
| C1 | existente | [D2] A tendência do tempo gráfico maior (H1) está a favor? | Existente D2 | H1 fechado: fechamento×MME34 e MME9×MME21 a favor | sim/não | sim | banco atual C1 | +0.058 | FRACA |
| C2 | existente | [D3] O preço está do lado a favor da abertura do dia? | Existente D3 | fechamento > abertura do pregão | sim/não | sim | banco atual C2 | +0.034 | FRACA |
| C3 | existente | [D4] As médias rápida e lenta estão a favor? (MMS17 > MMS34) | Existente D4 | MMS17 > MMS34 do fechamento M15 | sim/não | sim | banco atual C3 | +0.020 | INERTE |
| C4 | existente | [D5] A média longa está inclinada a favor? (MMS72 da abertura) | Existente D5 | MMS72(open) agora > 3 velas atrás | sim/não | sim | banco atual C4 | +0.060 | FRACA |
| C5 | existente | [D6∨D7] Preço não esticado (Estoc14<70) ou H4 neutro? | Existente D6/D7 | estocástico 14 (suav. 3) < 70 a favor OU H4 neutro | sim/não | sim | banco atual C5 | -0.011 | INERTE |
| C6 | existente | [D11] O gap de abertura é menor que 1 ATR diário? (sem lado) | Existente D11 | /abertura − fechamento de ontem//ATR diário < 1 | sim/não | sim | banco atual C6 | +0.000 | INERTE |
| C7 | existente | [Q16] O pregão já andou meio ATR diário? (sem lado) | Existente Q16 | (máx. − mín. do dia)/ATR diário ≥ 0,5 | sim/não | sim | banco atual C7 | +0.000 | INERTE |
| C8 | existente | [X1] O contexto virou no H1 (H1 não está mais a favor)? | Existente X1 | complemento de C1 | sim/não | sim | banco atual C8 (pergunta de saída) | -0.048 | FRACA |
| T1 | existente | [D1] A estrutura de topos e fundos confirmou a virada a favor AGORA? | Existente gatilho | ZigZag 1,5 ATR: fundo acima do anterior | sim/não | sim | banco atual T1 | +0.016 | INSTÁVEL |
| T2 | existente | [D12] A vela fechou fora da faixa das 20 anteriores (faixa ≤ 1,5 ATR diário) a favor AGORA? | Existente gatilho | fechamento fora da faixa de 20 velas | sim/não | sim | banco atual T2 | +0.068 | FRACA |
| T3 | existente | A 1ª vela do dia fechou contra o gap AGORA? | Existente gatilho | 1ª vela contra gap ≥ 5 pts | sim/não | sim | banco atual T3 | +0.000 | SEM AMOSTRA |
| T4 | existente | [D13] As médias 9/21/34 acabaram de se alinhar a favor? | Existente gatilho | MME9>21>34 e não na vela anterior | sim/não | sim | banco atual T4 | -0.056 | FRACA |
| D6 | existente | [D6] O oscilador está longe do extremo a favor (estocástico < 70)? | Existente D6 | estocástico 14 (suav. 3) < 70 | sim/não | sim | PERGUNTAS D6 | -0.013 | INERTE |
| D7 | existente | [D7] O H4 está sem tendência (neutro)? (sem lado) | Existente D7 | H4 MME9/21/34 neutro (fechados) | sim/não | sim | PERGUNTAS D7 | +0.000 | INERTE |
| D9 | existente | [D9/Q40] Resta pregão suficiente (≥ 8 velas até o fim)? (sem lado) | Existente D9/Q40 | velas restantes no pregão ≥ 8 | sim/não | sim | PERGUNTAS D9 | +0.000 | INERTE |
| D11 | existente | [D11] Há gap a favor (≥ 0,25 ATR diário) ainda não preenchido? | Existente D11 | (abertura − fech. ontem) ≥ 0,25 ATR diário e fechamento > fech. de ontem | sim/não | sim | PERGUNTAS D11 | -0.015 | INERTE |
| D13 | existente | [D13] As médias 9/21/34 do tempo próprio estão alinhadas a favor (estado)? | Existente D13 | MME9 > MME21 > MME34 no M15 | sim/não | sim | PERGUNTAS D13 | +0.035 | INERTE |
| Q13 | existente | [Q13] O mercado está em regime de tendência (ADX ≥ 25)? (sem lado) | Existente Q13 | ADX(14) M15 ≥ 25 | sim/não | sim | PERGUNTAS 13 | +0.000 | INERTE |
| Q14 | existente | [Q14] H1 e H4 concordam a favor? | Existente Q14 | H1 a favor e H4 a favor | sim/não | sim | PERGUNTAS 14 | +0.044 | FRACA |
| Q16 | existente | [Q16] O dia está esgotado (já andou ≥ 0,75 ATR diário)? (sem lado) | Existente Q16 | (máx. − mín. do dia)/ATR diário ≥ 0,75 | sim/não | não | PERGUNTAS 16 | +0.000 | INERTE |
| Q18 | existente | [Q18] O dólar confirma (WDO abaixo da abertura de hoje)? | Existente Q18 | WDO@D M15: fechamento < abertura do dia do WDO | sim/não | sim | PERGUNTAS 18 | +0.036 | INERTE |
| Q19 | existente | [Q19] Há algo anormal agora (vela ≥ 2 ATR ou volume ≥ 2× o normal, nas últimas 3 velas)? (sem lado) | Existente Q19 | faixa ≥ 2 ATR ou volume relativo ≥ 2 em alguma das 3 últimas velas | sim/não | não | PERGUNTAS 19 | +0.000 | INERTE |
| Q24 | existente | [Q24] O preço está esticado acima da MME38 (≥ 2 ATR)? | Existente Q24 | (fech. − MME38)/ATR M15 ≥ 2 | sim/não | não | PERGUNTAS 24 | -0.022 | INERTE |
| Q26 | existente | [Q26] A volatilidade está acima do normal (ATR > 1,2× a média de 500 velas)? (sem lado) | Existente Q26 | ATR14 M15 > 1,2 × média de 500 | sim/não | sim | PERGUNTAS 26 | +0.000 | INERTE |
| Q27 | existente | [Q27] O volume recente confirma o movimento (3 velas com volume ≥ 1,2× e preço a favor)? | Existente Q27 | média do volume relativo das 3 últimas ≥ 1,2 e fech. > fech. 3 velas atrás | sim/não | sim | PERGUNTAS 27 | +0.013 | FRACA |
| Q32 | existente | [Q32] O suporte das últimas 40 velas foi testado 3 ou mais vezes e o preço está a menos de 1 ATR dele? | Existente Q32 | velas com mínima ≤ mín.40 + 0,25 ATR ≥ 3 e fech. − mín.40 < 1 ATR | sim/não | sim | PERGUNTAS 32 | -0.084 | FRACA |
| Q33 | existente | [Q33] Qual a profundidade da correção atual dentro da faixa das últimas 20 velas? | Existente Q33 | (máx.20 − fech.)/(máx.20 − mín.20); 0 = rasa (<0,33), 1 = média, 2 = funda (>0,62) | faixa (3) | rasa (0) | PERGUNTAS 33 | +0.032 | INERTE |
| Q39 | existente | [Q39] O sinal acontece depois das 15h? (sem lado) | Existente Q39 | hora da vela ≥ 15:00 | sim/não | não | PERGUNTAS 39 | +0.000 | INERTE |
| Q42a | existente | [Q42] Hoje é sexta-feira? (sem lado) | Existente Q42 | dia da semana = sexta | sim/não | não | PERGUNTAS 42 | +0.000 | INERTE |
| Q42b | existente | [Q42] A data está nos 2 dias úteis até a quarta de vencimento do WIN? (sem lado) | Existente Q42 | dia ∈ {vencimento−2 dias, vencimento} | sim/não | não | PERGUNTAS 42 | +0.000 | INERTE |
| Q42c | existente | [Q42] Estamos nos 3 últimos pregões do mês? (sem lado) | Existente Q42 | dia entre os 3 últimos pregões do mês | sim/não | não | PERGUNTAS 42 | +0.000 | INERTE |

## Perguntas do arquivo PERGUNTAS_DE_OPERACAO.md sem régua de preço/volume (marcadas 'sem dado' ou sem resposta objetiva)

| # | motivo |
|---|---|
| Q20, Q22, Q29, Q30, Q36, Q37, Q47–Q53 | introspecção do operador / hábito / emoção: sem dado |
| Q41 | calendário de eventos e notícias: sem dado (substituto medido: Q19, vela/volume anormais) |
| Q44 | dias parecidos com hoje: é um método (vizinhança), não uma pergunta de resposta única |
| Q21 | diário × M1: coberta por N19/N20/N21 |
| Q17, Q35 | força da perna: coberta por N46 |
| Q15 | referências do dia/semana/mês: cobertas por C2, N16, N17, N48 |
| Q25, Q28 | oscilador extremo / divergência: D6, N41, N42 |
| Q31, Q38 | figura/falha de rompimento: N10, N35, T2 (figuras já refutadas no projeto) |
| Q34 | padrão de vela: refutado no projeto, não remedido |
| Q43 | leilões: já removidos da base |
| Q39/Q40/D9/D10 | horário: Q39, D9 (sem lado), e o bloco 0 por hora |
| D1 | = T1; D2–D5 = C1–C4; D6/D7 = D6, D7; D8 (posição aberta) e D9 são regras de execução; D10 = Q39 / hora; D12 = T2; D13 = D13 |
