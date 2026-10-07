# Frente B - Nota / probabilidade de acerto

Veredito: a nota das outras estrategias nao preve o acerto da entrada (AUC fora da amostra 0,47-0,50), nenhum filtro walk-forward bate o sorteio, e a unica celula acima do p95 (alvo mais largo no RetEma34 pela nota) e' uma entre ~115 olhadas, em cima de uma re-simulacao que nao reproduz o original. Nao ha ganho a incorporar.

## Como foi feito
- Unidade: cada ENTRADA das 6 estrategias (`eventos.parquet`, 1.608). Acerto = `rs > 0` na saida original. Mes = mes da entrada.
- Walk-forward mensal expansivo: o mes m usa modelo e limiar treinados so' com os meses < m. **Janeiro nao tem passado e opera sem filtro. O filtro so' pode agir a partir de abril** (o limiar precisa de previsoes fora da amostra de pelo menos fev e mar); jan-mar operam sem filtro.
- Limiar: fracao a pular f em {0, 10, 20, 30, 40, 50}% escolhida pelo maior liquido R$2 do passado, medido nas previsoes fora da amostra de fev..m-1 (nao na amostra de treino). Empate vai para f menor.
- Features (so' dados fechados antes da entrada, sem Win_c1, sem WdoRetangulo): n de outras a favor, n contra, forca da propria, taxa de acerto da estrategia no treino, e a ORDEM DE CHEGADA (ideia 5: 2a a favor no lucro / 2a a favor no prejuizo). Win_c1 fica fora do treino e da escolha do limiar (e' gemea do Win) mas recebe o filtro.
- 3 modelos: (i) tabela por n de outras a favor com Laplace (k+1)/(n+2); (ii) logistica L2 com 6 features; (iii) nota = media dos voto x forca das 3 outras, calibrada por Platt.
- Controle: sorteio de 200 mantendo o MESMO numero de entradas por (mes, estrategia). Placebo: 200 execucoes de todo o walk-forward com os rotulos de acerto embaralhados dentro do mes.
- Capital R$1.000 corrido por ordem de saida, 1 contrato; quebra = saldo <= 0 (nenhuma versao quebrou). R$/ponto = 0,20.
- **Celulas olhadas: ~115** (filtro 3 modelos x 6 fracoes = 18; resize RetEma34 9 celulas x 3 modelos = 27; ideia 6 = 9; overlay de stop 4 x 3 modelos = 12; tabela descritiva de chegada 4 classes x 6 estrategias x 2 metades = 48; AUC por estrategia e fracoes forcadas nao contadas). A escolha das celulas e' sempre no passado; o que se olha depois e' o resultado.

## AUC e calibracao fora da amostra (meses 2-10, sem Win_c1)
| modelo | AUC geral | Win | Cinco | Desloc | RetEma34 | WdoRetangulo |
|---|---|---|---|---|---|---|
| tabela | 0.502 | 0.552 | 0.535 | 0.442 | 0.475 | 0.479 |
| logit | 0.479 | 0.445 | 0.503 | 0.529 | 0.452 | 0.464 |
| nota | 0.471 | 0.421 | 0.524 | 0.375 | 0.465 | 0.474 |

Calibracao por quintil de probabilidade prevista (prevista / acerto realizado / n):
- tabela: Q1 0.38/0.44/262; Q2 0.40/0.39/261; Q3 0.42/0.45/262; Q4 0.44/0.39/261; Q5 0.49/0.44/262
- logit: Q1 0.35/0.49/262; Q2 0.40/0.40/261; Q3 0.43/0.45/262; Q4 0.45/0.36/261; Q5 0.52/0.42/262
- nota: Q1 0.41/0.47/262; Q2 0.42/0.45/261; Q3 0.42/0.42/262; Q4 0.44/0.37/261; Q5 0.45/0.41/262

Leitura: AUC ~0,5 e quintis sem ordem. As probabilidades previstas variam de 0,35 a 0,52, mas o acerto realizado nao acompanha (a logistica chega a ter o quintil mais baixo acertando 49% e o mais alto 42%). Nao ha informacao nas outras estrategias para dizer se esta entrada acerta.

## Entra ou nao: walk-forward contra sorteio e placebo (carteira = 5 estrategias sem Win_c1, R$2/op)
| modelo | fracoes escolhidas por mes (abr..out) | liquido R$2 | entradas | sorteio p50 / p5-p95 | percentil no sorteio | placebo p50 / p95 | percentil no placebo |
|---|---|---|---|---|---|---|---|
| sem filtro | - | 17377 | 1421 | - | - | - | - |
| tabela | 0.2 0.0 0.0 0.1 0.1 0.0 0.0 | 13890 | 1265 | 15134 / 12944-16679 | 16 | 17377 / 17377 | 4 |
| logit | 0.0 0.0 0.0 0.0 0.0 0.0 0.0 | 17377 | 1421 | 17377 / 17377-17377 | 0 | 17377 / 17512 | 40 |
| nota | 0.0 0.0 0.0 0.0 0.0 0.0 0.0 | 17377 | 1421 | 17377 / 17377-17377 | 0 | 17377 / 17377 | 34 |

A logistica e a nota nunca encontraram, no passado, um limiar que ganhasse do 'nao filtrar': operam sem filtro o ano todo (resultado = sem filtro; o sorteio e o placebo degeneram nesse valor). So' a tabela filtrou (f>0 em abr, jul, ago) e perdeu R$3.487 contra nao filtrar, no percentil 16 do sorteio.

Controle adicional, fracao FIXA a partir de abril (sem escolha de limiar) - liquido R$2 da carteira, entradas, sorteio p50/p95, percentil:
- tabela, pular 20%: 10558, 1050 entradas, sorteio 12298/14936, percentil 18  (sem filtro: 17377)
- tabela, pular 40%: 10134, 981 entradas, sorteio 9883/12264, percentil 57  (sem filtro: 17377)
- logit, pular 20%: 11950, 1310 entradas, sorteio 12196/13769, percentil 38  (sem filtro: 17377)
- logit, pular 40%: 10140, 1044 entradas, sorteio 9776/11833, percentil 60  (sem filtro: 17377)
- nota, pular 20%: 12238, 1114 entradas, sorteio 10698/13239, percentil 80  (sem filtro: 17377)
- nota, pular 40%: 8536, 883 entradas, sorteio 8273/10694, percentil 58  (sem filtro: 17377)

## Tabela mensal da carteira (5 estrategias, entrada no mes)
| versao | custo | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | trades | saldo min | quebrou |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sem filtro (original) | sem | 3606 | 2066 | 2492 | 2483 | 1879 | -12 | 1360 | 2286 | 4748 | -689 | 20219 | 1421 | 510 | nao |
| sem filtro (original) | R$2 | 3380 | 1736 | 2026 | 2167 | 1571 | -296 | 1152 | 1998 | 4414 | -771 | 17377 | 1421 | 510 | nao |
| filtro tabela (WF) | sem | 3606 | 2066 | 2492 | 1211 | 1879 | -12 | 632 | 487 | 4748 | -689 | 16420 | 1265 | 510 | nao |
| filtro tabela (WF) | R$2 | 3380 | 1736 | 2026 | 979 | 1571 | -296 | 476 | 375 | 4414 | -771 | 13890 | 1265 | 510 | nao |
| RetEma34 re-simulado (1,1) | sem | 3841 | 2031 | 3303 | 2399 | 1632 | 203 | 1398 | 2104 | 4650 | -639 | 20922 | 1421 | 574 | nao |
| RetEma34 re-simulado (1,1) | R$2 | 3615 | 1701 | 2837 | 2083 | 1324 | -81 | 1190 | 1816 | 4316 | -721 | 18080 | 1421 | 574 | nao |
| RetEma34 resize pela nota (WF) | sem | 3841 | 2031 | 3303 | 2908 | 1139 | 263 | 1423 | 2149 | 4531 | -439 | 21149 | 1421 | 574 | nao |
| RetEma34 resize pela nota (WF) | R$2 | 3615 | 1701 | 2837 | 2592 | 831 | -21 | 1215 | 1861 | 4197 | -521 | 18307 | 1421 | 574 | nao |

Totais por estrategia (sem custo / R$2), sem filtro e com o filtro da tabela:
| estrategia | sem filtro | filtro tabela | trades sem -> com |
|---|---|---|---|
| Win | 3997 / 3635 | 3896 / 3612 | 181 -> 142 |
| Win_c1 | 3799 / 3425 | 3949 / 3657 | 187 -> 146 |
| WinCincoMedias | 8859 / 8243 | 7825 / 7353 | 308 -> 236 |
| WinDeslocamentoMatinal | 2219 / 2089 | 767 / 653 | 65 -> 57 |
| WinRetanguloEma34 | 2307 / 841 | 1891 / 467 | 733 -> 712 |
| WdoRetangulo | 2837 / 2569 | 2041 / 1805 | 134 -> 118 |

## Tamanho de alvo e stop pela nota (re-simulacao nos ticks, mesma entrada)
RetEma34 tem stop (0,45L) e alvo (0,90L) proprios, fixos. A re-simulacao com `saida.py` em (1,1) NAO reproduz o CSV original: so' 69% dos trades saem iguais e o bruto sobe de R$2.307 para R$3.010 (liquido R$2: 841 -> 1.544), porque o EA aproxima o alvo com o tempo (AproximarAlvo) e a re-simulacao usa alvo fixo. Por isso o comparador do resize e' a re-simulacao (1,1), nao o CSV. De passagem, isso sugere que a aproximacao do alvo custa dinheiro, mas e' achado lateral, nao testado aqui.
Grade (9 celulas): alvo x{1; 1,25; 1,5} nas entradas de nota alta (>= mediana das previsoes passadas) e stop x{1; 0,75; 0,5} nas de nota baixa; a celula do mes m e' a melhor no passado.
| score usado | base re-sim R$2 | walk-forward R$2 | celulas escolhidas abr..out (alvo x, stop x) | sorteio de score p50 / p95 | percentil |
|---|---|---|---|---|---|
| logit | 1544 | 1002 | 1.5/1 1.5/1 1.5/1 1.25/1 1.25/1 1.25/1 1.25/1 | 912 / 1639 | 56 |
| nota | 1544 | 1771 | 1.5/1 1.5/1 1.25/1 1.25/1 1.5/1 1.25/1 1.25/1 | 1008 / 1760 | 95 |
| tabela | 1544 | 1444 | 1.5/1 1.5/1 1.25/1 1.25/1 1.25/1 1/1 1/1 | 1012 / 1644 | 86 |

Leitura: com a logistica e a tabela a regra nao supera o sorteio (percentil 56 e 86); com a nota chega a +R$227 sobre a base e percentil 95 do sorteio. E' 1 de 3 modelos, a diferenca vem sempre de alargar o alvo (stop mais curto perde em toda celula: todas as celulas com stop x0,75 ou x0,5 ficam abaixo da base), e a melhoria de alvo mais largo existe tambem fora da nota. Nao e' evidencia de que a NOTA ajude; e' evidencia de que, na re-simulacao sem a aproximacao do alvo, alvo maior rende um pouco mais em 2026.

Estrategias de tendencia (Win, Win_c1, Cinco, Desloc) tem saida dinamica (canal, esticada, stop que persegue a media, zera 18:20): nao da' para alargar alvo/stop sem reescrever a estrategia. Teste possivel: stop-teto extra de s x ATR M5 nas entradas de nota baixa (sai no teto se ele disparar antes da saida original; dispara antes em 22-62% das entradas conforme s):
| score | base R$2 (4 estrategias, sem Win_c1) | walk-forward | percentil no sorteio |
|---|---|---|---|
| logit | 13967 | 13839 | 84 |
| nota | 13967 | 13155 | 44 |
| tabela | 13967 | 12803 | 27 |
Nenhum ganho: o teto de stop so' tira operacoes que depois recuperariam, o mesmo achado de 'stop curto' ja' refutado em outras frentes.

## Ideia 5 - ordem de chegada
Classe da entrada pela posicao da OUTRA familia (tendencia x retangulo) aberta no instante: 1a (nenhuma), 2a a favor no lucro, 2a a favor no prejuizo, contra. Contagem total: {0: 1158, 1: 181, 2: 65, 3: 204} (0=1a, 1=lucro, 2=prejuizo, 3=contra). R$/op bruto por metade (jan-mai | jun-out), n entre parenteses; descritivo, nao escolhe nada:
| estrategia | 1a | 2a lucro | 2a prejuizo | contra |
|---|---|---|---|---|
| Win | 2 (84) ; 47 (69) | 5 (10) ; 29 (3) | 107 (2) ; 10 (1) | -3 (7) ; 53 (5) |
| WinCincoMedias | 43 (101) ; 13 (110) | 28 (25) ; 42 (19) | 131 (5) ; -18 (4) | 41 (26) ; 0 (18) |
| WinDeslocamentoMatinal | 29 (28) ; 16 (30) | 45 (4) ; 225 (1) | - (0) ; - (0) | 264 (2) ; - (0) |
| WinRetanguloEma34 | 3 (326) ; 0 (174) | -12 (49) ; 10 (39) | 5 (20) ; 20 (20) | 16 (59) ; -3 (46) |
| WdoRetangulo | 7 (49) ; -4 (30) | 168 (10) ; 2 (8) | -21 (2) ; 30 (7) | 22 (14) ; 32 (14) |
| Win_c1 | 5 (87) ; 41 (70) | 6 (10) ; 26 (3) | 72 (3) ; 10 (1) | -3 (7) ; 38 (6) |

Leitura: nenhuma classe mantem o mesmo sinal nas duas metades em mais de uma estrategia; os numeros grandes (ex.: +168 no WdoRet 2a no lucro, +225 no Desloc) sao n de 1 a 10. Como feature da logistica (cheg_lucro, cheg_prej) o AUC fora da amostra continuou em 0,479.

## Ideia 6 - stop e alvo pela volatilidade esperada do horario (RetEma34)
Volatilidade esperada = mediana da amplitude (max-min das M1) da janela de 30 min do horario da entrada nos pregoes ANTERIORES (>= 10 pregoes de historico; antes disso razao 1), dividida pela mediana de todas as janelas 09-17h anteriores, limitada a [0,5; 2]. Stop e alvo multiplicados por razao^gs e razao^ga, (gs, ga) em {0; 0,5; 1}^2 = 9 celulas, a do mes m escolhida no passado (base = (0,0) = re-simulacao).
R$2 de cada celula fixa no ano todo (so' orientacao, olha o futuro): (0,0) 1544, (0,0.5) 889, (0,1) -182, (0.5,0) 2322, (0.5,0.5) 1581, (0.5,1) 1512, (1,0) 1232, (1,0.5) 969, (1,1) 1500
Walk-forward: base 1544 -> 1389; celulas escolhidas abr..out: {4: (0.5, 0.0), 5: (0.5, 1.0), 6: (0.5, 1.0), 7: (0.5, 0.0), 8: (0.5, 0.0), 9: (0.5, 0.0), 10: (0.5, 0.0)}; razao embaralhada entre trades do mesmo mes (30 sorteios) p50 554, p95 1908, percentil 83.
Correlacao da razao com o tamanho do movimento original |pontos|: 0,14 (fraca). A celula (0,5; 0) (so stop escalado) foi a escolhida quase todo mes e ganha no ano fixo (+778), mas esse ganho esta em jan-mar, que o walk-forward nao usa: de abril a outubro ela da -652 contra -497 da base. Sem ganho.

## Melhor versao walk-forward e arquivos
Melhor por liquido, escolhida DEPOIS de ver o resultado (portanto otimista): RetEma34 com resize pela nota (score 'nota'): carteira R$2 18307 contra 17377 sem filtro, mas contra 18080 com o RetEma34 re-simulado (1,1); a diferenca entre esses dois e' efeito da re-simulacao, nao da nota. Nenhuma versao quebrou com R$1.000.
- `resultado.csv`: liquido sem custo e R$2, trades, saldo minimo e quebra por versao e escopo.
- `trades/`: no formato de `resultados/*.csv` - `*_filtro_tabela.csv` (entradas mantidas pelo filtro walk-forward da tabela; unico filtro que agiu) e `WinRetanguloEma34_resize_nota.csv` (saidas re-simuladas com o alvo/stop da celula escolhida; meses jan-mar em (1,1)).
- Codigo: `comum.py`, `run_filtro.py`, `run_saida.py`, `extrai_retema34.py`, `relatorio.py`.
