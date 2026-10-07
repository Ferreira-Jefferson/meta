# Replicacao jan-ago/2026: regras de dia do WIN (R01-R12, R20-R24)

Base: WIN@D M1 (ajuste por diferenca, hora de Brasilia), somente 2026. 164 pregoes em jan-ago (+21 em set como referencia). O fechamento anterior de 02/01 vem de 30/12/2025; nenhum outro dado de 2025 foi usado. Definicoes e limiares congelados de `REGRAS.md`; nada foi otimizado. Nenhum lucro de estrategia foi calculado.

## Veredito

| Regra | O que diz | jan-ago/26 | set/26 | base / acaso | Veredito |
|---|---|---|---|---|---|
| R01 | hora<11 liga a pernada (250->750) | 13,2% x 4,7% | 20,0% x 4,6% | desligada 4,7%; nulo 13,2% x 4,7% | **replicou** |
| R02 | <11h captura as pernadas | 62,2% em 21,1% do tempo | 73,4% | proporcional 21,1% | **replicou (mais fraco no inverno)** |
| R03 | >=13h quase nao nasce pernada | 3,4% x 10,3% | 3,1% x 14,2% | ligada 10,3% | **replicou** |
| R04 | >=13h recuo 500 vira 750 | 64,6% | 75,4% | nulo 66,8%; manha 67,2% | **falhou** |
| R05 | consenso 10:30: resto contra | 50,0% (48/96) | 85,7% | 50% | **falhou** |
| R06 | 10:30-12:30, >500 do fech. ant. volta | 49,9% | 73,1% | fora 49,2% | **falhou** |
| R07 | idem, da abertura | 47,5% | 65,9% | fora 49,0% | **falhou** |
| R08 | idem, do VWAP | 48,4% | 61,3% | fora 47,5% | **falhou** |
| R09 | gap fecha no dia | 73,0% | 85,7% | excursao simetrica 70,6% | **parcial** |
| R10 | dia termina contra o gap | 53,4% | 71,4% | 50% | **falhou** |
| R11 | >=1 extremo nas 2 1as pernadas H1 | 92,1% | 95,2% | nulo 91,2% | **replicou (= nulo)** |
| R12 | max/min do dia ate ~10:30 (mediana) | 10:44 / 11:04 | 10:28 / 10:29 | nulo 10:52 / 11:12 | **parcial** |
| R20 | ondas de volatilidade (corr. 15 min) | 0,50 (sem regime do mes 0,36) | 0,28 | 0,00 +-0,07/mes | **replicou** |
| R21 | minuto :00 / :30 | 1,37x / 1,18x | 1,51x / 1,27x | 1,00x | **replicou** |
| R22 | VR5 das 9-10h | 0,81 | 0,69 | 1,00 (0,96-1,04) | **replicou (mais fraco)** |
| R23 | tarde: x mais lenta / x mais correcoes | 2,6x / 1,4x | 4,5x / 1,8x | nulo 2,4x / 1,5x | **parcial** |
| R24 | degrau 10:30 (amplitude 15/15 min) | 1,16x | 1,28x | outros cortes 0,95x | **replicou, com ressalva de horario** |

Resumo: replicaram R01, R02, R03, R11 (igual ao nulo), R20, R21, R22 (mais fraca), R24 (com ressalva de horario). Parciais: R09, R12, R23. Falharam: R04, R05, R06, R07, R08, R10. As regras de DIRECAO (R05-R10) e a virada da tarde (R04) sao justamente as que falharam; as que se mantiveram sao as de relogio de volatilidade (quando e quanto o preco anda), nao de para onde.

## Leitura de conjunto

- **Relogio x direcao.** Tudo o que replica descreve QUANDO e QUANTO o preco anda (R01-R03, R20-R24, e R11/R12 por consequencia). O nulo com horario (blocos de 30 min embaralhados, ou blocos sorteados de outros dias) reproduz R01, R02, R03, R11, R12 e R23 praticamente igual ao real: nesses casos o numero real nao tem excesso sobre um passeio aleatorio com a mesma volatilidade por horario. Em set a mesma comparacao dava excesso (R11 'ambos': 52% x nulo 27%); em jan-ago o excesso some (27% x 27%).
- **Direcao nao replica.** R04, R05, R06-R08, R10 ficam em ~50% (R04 em ~65% = nulo). Em set essas regras estavam em 60-86%: set foi um mes atipico de reversao da manha (R05 12/14, R06 73%), e jan-ago inverte de mes para mes sem padrao.
- **Horario de NY depende do DST americano.** O WIN opera 09:00-18:24 o ano todo, mas a abertura de NY cai as 10:30 BRT so quando os EUA estao no horario de verao (de 8/mar em diante); antes disso cai as 11:30. R24 mostra: jan-fev sem degrau as 10:30 (0,96 / 0,98) e degrau as 11:30 (1,26 / 1,55, primeiro entre 67 cortes), mar-ago degrau as 10:30. Qualquer regra amarrada ao 'marco das 10:30' (R05, R06-R08, R24, a janela 10:30-12:30) esta desalinhada em jan-6/mar. Nao troquei a definicao (replicacao): as tabelas de regime abaixo mostram a divisao.
- **Nivel de volatilidade.** Range diario medio: jan 3.116, fev 3.455, mar 4.183, abr 2.901, mai 2.895, jun 2.874, jul 2.750, ago 3.139, set 3.514. As regras de relogio enfraquecem com a volatilidade alta e dispersa (jan-mar: R02 39-53%, R12 as 11:40-12:40 na maxima, R22 0,76-0,83 ainda abaixo de 1) e se firmam de abr em diante (R02 64-84%, R12 ~10:30).
- **Janela de teste.** Por serem 8 meses de ~20 dias, cada percentual mensal tem erro padrao de 5-15 pp; o IC por bootstrap de dias esta ao lado de cada total.

## Tabelas por regra (n e % por mes)

### Regras de pernada: R01, R02, R03 (tipo 'balanco', M5, X=250)

Definicao usada: zigzag de 100 pts no caminho M5; evento = o preco ja andou 250 do ultimo pivo (1x por pivo); y=1 se chega a 750 do pivo antes de recuar 100 do extremo (`kit_pernadas.eventos_balanco` + `rotular`, a mesma de `chave.md`). Hora do evento = abertura da vela M5 onde o avanco ocorre. Os eventos de um mesmo dia se sobrepoem; o IC e por bootstrap de dias.

| R01 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P(750) hora<11 (ligada) | 8,4% | 11,4% | 20,3% | 10,6% | 11,4% | 13,1% | 11,4% | 16,2% | 13,2% | [12,0% ; 14,5%] | 20,0% |
| n eventos ligada | 371 | 412 | 581 | 463 | 455 | 505 | 507 | 480 | 3774 | - | 580 |
| P(750) hora>=11 (desligada) | 6,3% | 4,8% | 6,9% | 3,7% | 3,6% | 3,5% | 2,1% | 2,5% | 4,7% | [4,0% ; 5,3%] | 4,6% |
| n eventos desligada | 772 | 857 | 1584 | 760 | 687 | 680 | 513 | 591 | 6444 | - | 907 |
| nulo 30 min, ligada (p5-p95) | 9,9% (8,2%-11,7%) | 12,3% (10,3%-14,3%) | 19,2% (17,1%-21,4%) | 10,8% (8,9%-12,7%) | 10,8% (8,7%-12,7%) | 13,3% (11,4%-15,4%) | 11,9% (10,3%-13,8%) | 14,9% (12,8%-17,0%) | 13,2% (12,5%-13,9%) | - | 20,6% (18,5%-22,8%) |
| nulo 30 min, desligada (p5-p95) | 6,2% (5,1%-7,4%) | 5,0% (4,1%-5,9%) | 7,6% (6,6%-8,6%) | 3,2% (2,4%-4,2%) | 3,3% (2,4%-4,2%) | 3,1% (2,2%-4,1%) | 2,0% (1,1%-2,8%) | 2,6% (1,7%-3,7%) | 4,7% (4,3%-5,0%) | - | 4,0% (3,1%-4,9%) |

| R02 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pernadas capturadas com <11h | 38,8% | 53,4% | 51,8% | 63,6% | 67,5% | 73,3% | 84,1% | 83,9% | 62,2% | [58,4% ; 66,7%] | 73,4% |
| tempo ligado (fracao dos minutos) | 21,1% | 21,2% | 21,1% | 21,0% | 21,1% | 21,0% | 21,0% | 21,0% | 21,1% | - | 20,9% |
| n pernadas (eventos que chegam a 750) | 80 | 88 | 228 | 77 | 77 | 90 | 69 | 93 | 802 | - | 158 |
| nulo 30 min, capturadas (p5-p95) | 44,0% (38,0%-50,6%) | 53,1% (47,4%-58,9%) | 49,6% (45,9%-53,6%) | 67,4% (60,0%-74,3%) | 69,5% (62,0%-76,2%) | 75,7% (69,7%-81,6%) | 85,9% (80,7%-91,3%) | 82,8% (76,8%-88,2%) | 62,6% (60,6%-64,5%) | - | 76,1% (72,0%-80,7%) |

| R03 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P(750) hora>=13 | 3,7% | 2,6% | 5,8% | 1,9% | 3,0% | 2,3% | 1,6% | 1,4% | 3,4% | [2,7% ; 4,1%] | 3,1% |
| n eventos >=13h | 434 | 497 | 1032 | 421 | 366 | 347 | 247 | 286 | 3630 | - | 482 |
| P(750) hora<13 (ligada) | 9,0% | 9,7% | 14,8% | 8,6% | 8,5% | 9,8% | 8,4% | 11,3% | 10,3% | [9,4% ; 11,1%] | 14,2% |
| nulo 30 min, >=13h (p5-p95) | 3,7% (2,6%-5,0%) | 2,8% (1,8%-3,9%) | 5,9% (5,0%-6,9%) | 1,4% (0,7%-2,4%) | 2,7% (1,6%-3,8%) | 2,5% (1,6%-3,5%) | 1,4% (0,4%-2,4%) | 0,9% (0,0%-1,7%) | 3,3% (2,9%-3,8%) | - | 2,1% (1,3%-3,1%) |

### R04: recuo de 500 do extremo, depois das 13h

Definicao usada (`transicoes/an.py`): zigzag de 750 no caminho M1 de 4 pontos por vela; evento = recuo de 500 do maximo (minimo) corrente da perna, 1x por extremo, so com alta acumulada >= 750; y=1 se o recuo chega a 750 antes de novo extremo. Eventos sem desfecho (fim do dia) descartados. 'Manha' = antes das 13h.

| R04 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P(vira 750) tarde (>=13h) | 70,8% | 69,0% | 59,0% | 68,2% | 73,0% | 70,3% | 73,3% | 39,1% | 64,6% | [59,8% ; 68,9%] | 75,4% |
| n eventos tarde | 48 | 58 | 139 | 44 | 37 | 37 | 15 | 23 | 401 | - | 61 |
| P(vira 750) manha (<13h) | 71,7% | 72,3% | 66,4% | 63,2% | 68,1% | 73,0% | 59,5% | 64,8% | 67,2% | [64,7% ; 69,7%] | 62,1% |
| n eventos manha | 120 | 130 | 250 | 133 | 113 | 141 | 131 | 142 | 1160 | - | 198 |
| nulo 30 min, tarde (p5-p95) | 65,2% (55,6%-75,5%) | 69,6% (61,1%-78,6%) | 66,1% (60,8%-71,5%) | 68,7% (58,5%-77,8%) | 68,7% (57,6%-78,4%) | 66,0% (55,6%-76,5%) | 73,5% (60,0%-87,5%) | 58,2% (45,4%-72,2%) | 66,8% (63,9%-70,3%) | - | 70,2% (61,1%-78,7%) |
| nulo 30 min, manha (p5-p95) | 64,6% (58,3%-71,1%) | 66,4% (60,8%-72,6%) | 65,5% (60,4%-70,2%) | 64,7% (58,0%-71,4%) | 66,4% (60,3%-73,5%) | 68,3% (63,1%-74,1%) | 65,8% (59,7%-71,7%) | 65,5% (59,6%-71,7%) | 65,9% (64,0%-67,8%) | - | 63,7% (58,6%-68,8%) |

### R05: consenso das 3 leituras as 10:30 (`a2.py`)

Consenso = retorno desde a abertura, preco - VWAP (ponderada por close x volume) e preco - fechamento anterior com o mesmo sinal as 10:30; 'contra' = o fechamento do dia fica do lado oposto do preco das 10:30. Base: 50% (binomial). O nulo por blocos de 30 min nao se aplica: preserva o preco as 10:30 e o fechamento.

| R05 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dias contra o consenso | 21,4% | 50,0% | 69,2% | 60,0% | 54,5% | 41,7% | 20,0% | 78,6% | 50,0% | [39,0% ; 60,2%] | 85,7% |
| n dias com consenso | 14 | 12 | 13 | 10 | 11 | 12 | 10 | 14 | 96 | - | 14 |
| dias contra o consenso (k) | 3 | 6 | 9 | 6 | 6 | 5 | 2 | 11 | 48 | - | 12 |
| mediana do restante a favor do consenso, pts | 695 | 98 | -1020 | -250 | -395 | 105 | 1418 | -798 | -12 | [-340 ; 295] | -1092 |
| extra: so retorno desde a abertura, contra | 33,3% | 35,3% | 59,1% | 50,0% | 60,0% | 47,6% | 40,9% | 71,4% | 50,0% | [42,1% ; 57,9%] | 66,7% |

### R06-R08: desvio >500 pts, janela 10:30-12:30, horizonte 60 min (`a4.py`)

Grade a cada 15 min de 09:30 a 16:00; desvio dv = preco - VWAP (tipico x volume acumulada), do = preco - abertura, dp = preco - fechamento anterior; 'contra' = o retorno dos 60 min seguintes tem sinal oposto ao do desvio. Janela = tempos de 10:30 a 12:15 (a 12:30 e 'depois'); fora = antes de 10:30 + de 12:30 em diante. Amostras sobrepostas dentro do dia (IC por dias). Base: 50% / 'fora da janela'.

| R06 (fech. anterior) | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| contra, dentro 10:30-12:30 | 37,5% | 58,2% | 59,5% | 50,8% | 40,3% | 52,5% | 40,1% | 60,3% | 49,9% | [44,8% ; 54,9%] | 73,1% |
| n dentro | 112 | 98 | 153 | 118 | 124 | 120 | 137 | 116 | 978 | - | 134 |
| contra, fora da janela | 50,3% | 41,6% | 48,5% | 47,6% | 53,0% | 56,8% | 41,2% | 55,2% | 49,2% | [45,4% ; 53,1%] | 51,9% |
| n fora | 320 | 238 | 336 | 290 | 315 | 278 | 313 | 230 | 2320 | - | 295 |

| R07 (abertura) | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| contra, dentro 10:30-12:30 | 32,2% | 52,3% | 59,2% | 44,8% | 47,6% | 47,6% | 43,2% | 52,5% | 47,5% | [42,5% ; 52,7%] | 65,9% |
| n dentro | 118 | 107 | 125 | 105 | 124 | 126 | 111 | 118 | 934 | - | 126 |
| contra, fora da janela | 50,8% | 44,4% | 49,2% | 42,5% | 54,1% | 51,9% | 43,2% | 55,7% | 49,0% | [45,5% ; 52,7%] | 53,4% |
| n fora | 301 | 277 | 311 | 261 | 290 | 297 | 287 | 262 | 2286 | - | 311 |

| R08 (VWAP) | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| contra, dentro 10:30-12:30 | 33,8% | 57,1% | 55,9% | 48,7% | 52,1% | 45,6% | 50,0% | 44,2% | 48,4% | [43,0% ; 54,1%] | 61,3% |
| n dentro | 77 | 49 | 111 | 78 | 73 | 68 | 70 | 86 | 612 | - | 80 |
| contra, fora da janela | 53,4% | 49,7% | 49,4% | 44,3% | 49,7% | 47,9% | 37,6% | 48,2% | 47,5% | [43,5% ; 51,7%] | 51,6% |
| n fora | 193 | 161 | 243 | 176 | 181 | 167 | 197 | 199 | 1517 | - | 221 |

### R09, R10: gap

Gap = abertura do dia - fechamento anterior (qualquer valor diferente de zero; n = dias com gap). R09: o dia toca o fechamento anterior. Base para R09 (nova, `-` no original): o preco percorre a mesma distancia |gap| no sentido OPOSTO ao gap a partir da abertura ('excursao simetrica'). R10: fechamento do dia - abertura contra o sinal do gap (leitura mais proxima do relatorio: 'dia termina na direcao do gap', direcao do dia = abertura->fechamento); a coluna alternativa mede o fechamento contra o fechamento anterior.

| R09 / R10 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R09 gap fecha no dia | 81,0% | 70,6% | 68,2% | 70,0% | 63,2% | 76,2% | 63,6% | 90,5% | 73,0% | [66,3% ; 79,6%] | 85,7% |
| base: excursao simetrica | 81,0% | 64,7% | 63,6% | 65,0% | 57,9% | 76,2% | 77,3% | 76,2% | 70,6% | [63,2% ; 76,8%] | 47,6% |
| n dias com gap | 21 | 17 | 22 | 20 | 19 | 21 | 22 | 21 | 163 | - | 21 |
| R10 dia termina contra o gap (fech. - abertura) | 47,6% | 47,1% | 45,5% | 80,0% | 47,4% | 52,4% | 31,8% | 76,2% | 53,4% | [45,7% ; 60,7%] | 71,4% |
| R10 alt.: fechamento do lado oposto do fech. anterior | 42,9% | 29,4% | 36,4% | 55,0% | 31,6% | 52,4% | 13,6% | 57,1% | 39,9% | [32,7% ; 47,8%] | 52,4% |

### R11, R12: extremos do dia

R11 (`sequencia.md`): zigzag de 750 sobre o caminho H1; extremo do dia (max ou min) cai ate o fim da 2a pernada (se ha menos de 2 pernadas, conta como sim). Nulos: (a) blocos de 30 min embaralhados e (b) cada bloco de 30 min do dia sorteado de outro dia (preserva o relogio de volatilidade, destroi a estrutura do dia). 300 simulacoes cada. R12: horario da vela M1 da maxima/minima do dia (1a ocorrencia), mediana dos dias.

| R11 / R12 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R11 >=1 extremo nas 2 1as pernadas H1 | 90,5% | 94,1% | 86,4% | 95,0% | 95,0% | 85,7% | 100,0% | 90,5% | 92,1% | [87,8% ; 95,7%] | 95,2% |
| R11 ambos os extremos | 33,3% | 5,9% | 22,7% | 20,0% | 30,0% | 28,6% | 36,4% | 38,1% | 27,4% | [20,7% ; 34,1%] | 52,4% |
| n dias | 21 | 17 | 22 | 20 | 20 | 21 | 22 | 21 | 164 | - | 21 |
| nulo blocos 30 min, >=1 extremo (p5-p95) | 93,0% (85,7%-100,0%) | 92,8% (82,4%-100,0%) | 83,6% (77,3%-90,9%) | 91,3% (85,0%-95,0%) | 92,9% (90,0%-100,0%) | 85,2% (81,0%-90,5%) | 97,0% (90,9%-100,0%) | 91,8% (85,7%-100,0%) | 90,9% (88,4%-93,3%) | - | 95,8% (90,5%-100,0%) |
| nulo dias sorteados, >=1 extremo (p5-p95) | 91,2% (81,0%-100,0%) | 91,5% (76,5%-100,0%) | 91,4% (81,8%-100,0%) | 90,6% (80,0%-100,0%) | 91,0% (80,0%-100,0%) | 91,5% (80,7%-100,0%) | 91,6% (81,8%-100,0%) | 90,9% (81,0%-100,0%) | 91,2% (87,8%-94,5%) | - | 91,8% (81,0%-100,0%) |
| nulo dias sorteados, ambos (p5-p95) | 26,3% (9,5%-42,9%) | 27,2% (11,8%-47,1%) | 26,6% (13,6%-40,9%) | 26,7% (10,0%-45,0%) | 25,7% (10,0%-45,0%) | 26,2% (9,5%-42,9%) | 27,1% (13,6%-40,9%) | 25,6% (9,5%-42,9%) | 26,4% (20,7%-32,9%) | - | 26,9% (9,5%-42,9%) |
| R12 mediana horario da maxima | 12:39 | 11:50 | 11:43 | 10:38 | 09:28 | 10:32 | 10:26 | 10:27 | 10:44 | [10:22 ; 11:14] | 10:28 |
| R12 mediana horario da minima | 11:10 | 11:40 | 11:06 | 11:21 | 12:12 | 10:43 | 10:22 | 11:04 | 11:04 | [10:30 ; 11:33] | 10:29 |
| nulo dias sorteados, maxima | 10:56 (09:50-12:14) | 10:58 (09:23-12:51) | 11:02 (09:39-12:47) | 11:00 (09:48-12:44) | 11:09 (09:54-12:55) | 11:01 (09:56-12:35) | 10:58 (09:43-12:51) | 11:01 (09:42-12:51) | 10:52 (10:30-11:25) | - | 11:03 (09:52-12:33) |
| nulo dias sorteados, minima | 11:22 (10:05-13:39) | 11:26 (09:40-14:31) | 11:23 (10:04-13:21) | 11:29 (09:59-13:53) | 11:20 (09:59-13:26) | 11:16 (10:01-13:40) | 11:19 (10:04-13:13) | 11:29 (10:08-13:33) | 11:12 (10:40-11:44) | - | 11:21 (10:02-13:29) |

### R20: ondas de volatilidade

Faixa (max-min) de blocos de 15 min (37 por dia, 09:00-18:15), em log, menos a media do mesmo horario; correlacao entre bloco e o seguinte no mesmo dia. A media do horario e tirada dentro de cada coluna (mes) e, em jan-ago, sobre os 164 dias; a linha 'sem regime do mes' tira a media de cada mes, a linha 'sem regime do dia' tira tambem a media de cada dia. Nulo: permutar os dias dentro de cada horario (300 sorteios), p5-p95.

| R20 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| corr. bloco t x t+1 | 0,67 | 0,19 | 0,25 | 0,33 | 0,22 | 0,33 | 0,24 | 0,25 | 0,50 | [0,46 ; 0,54] | 0,28 |
| sem regime do mes | 0,67 | 0,19 | 0,25 | 0,33 | 0,22 | 0,33 | 0,24 | 0,25 | 0,36 | [0,29 ; 0,42] | 0,28 |
| sem regime do dia | 0,29 | 0,07 | 0,14 | 0,12 | 0,15 | 0,25 | 0,12 | 0,15 | 0,23 | [0,19 ; 0,27] | 0,21 |
| nulo (p5 ; p95) | -0,06 ; 0,07 | -0,07 ; 0,07 | -0,07 ; 0,06 | -0,06 ; 0,06 | -0,06 ; 0,08 | -0,07 ; 0,06 | -0,06 ; 0,06 | -0,07 ; 0,06 | -0,02 ; 0,02 | - | -0,06 ; 0,07 |
| range diario medio, pts | 3116 | 3455 | 4183 | 2901 | 2895 | 2874 | 2750 | 3139 | 3164 | - | 3514 |

### R21: minuto cheio

Faixa M1 / media da faixa da hora, 10h-17h sem 10:30-10:32; media sobre as horas-dia. Nulo: permutar os minutos dentro de cada hora-dia (200 sorteios), p5-p95.

| R21 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| :00 | 1,25 | 1,20 | 1,22 | 1,43 | 1,46 | 1,35 | 1,59 | 1,47 | 1,37 | [1,34 ; 1,41] | 1,51 |
| nulo :00 (p5 ; p95) | 0,95 ; 1,05 | 0,95 ; 1,06 | 0,95 ; 1,05 | 0,94 ; 1,05 | 0,93 ; 1,07 | 0,94 ; 1,05 | 0,95 ; 1,06 | 0,95 ; 1,06 | 0,98 ; 1,02 | - | 0,95 ; 1,08 |
| :30 | 1,22 | 1,13 | 1,06 | 1,13 | 1,15 | 1,24 | 1,21 | 1,28 | 1,18 | [1,14 ; 1,21] | 1,27 |
| nulo :30 (p5 ; p95) | 0,94 ; 1,07 | 0,94 ; 1,06 | 0,95 ; 1,05 | 0,94 ; 1,06 | 0,94 ; 1,06 | 0,95 ; 1,07 | 0,94 ; 1,07 | 0,95 ; 1,07 | 0,98 ; 1,02 | - | 0,94 ; 1,07 |
| minutos sem destaque (media) | 0,98 | 0,99 | 0,99 | 0,98 | 0,98 | 0,98 | 0,98 | 0,98 | 0,98 | - | 0,97 |

### R22: razao de variancia em 5 min, 09:00-10:00

VR5 = var(retorno de 5 min, janelas sobrepostas) / (5 x var(retorno de 1 min)), so velas consecutivas dentro de 09:00-10:00, pooled nos dias. Nulo (do relatorio original): permutar os retornos de 1 min dentro de cada dia (100 sorteios), p5-p95.

| R22 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VR5 9-10h | 0,76 | 0,80 | 0,83 | 0,85 | 1,01 | 0,87 | 0,71 | 0,73 | 0,81 | [0,76 ; 0,87] | 0,69 |
| nulo (p5 ; p95) | 0,87 ; 1,15 | 0,88 ; 1,12 | 0,89 ; 1,10 | 0,89 ; 1,12 | 0,90 ; 1,09 | 0,91 ; 1,13 | 0,89 ; 1,14 | 0,88 ; 1,11 | 0,96 ; 1,04 | - | 0,90 ; 1,11 |

### R23: tarde x manha

Pernadas de zigzag 750 em M5 (todas, inclusive a 1a do dia e a aberta no fim, como no original). Manha = inicio antes de 12:00; tarde = inicio a partir de 13:00 (a faixa 12-13h fica fora). Velocidade = tamanho / duracao (duracao = fim - inicio, minimo 5 min = uma vela M5). Correcao = recuo >= 5 pts seguido de novo extremo dentro da pernada. Razoes tarde/manha: velocidade invertida (manha/tarde = 'x mais lenta').

| R23 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| n pernadas manha | 87 | 97 | 152 | 91 | 89 | 111 | 92 | 101 | 820 | - | 135 |
| n pernadas tarde | 33 | 40 | 80 | 29 | 24 | 25 | 8 | 9 | 248 | - | 45 |
| tamanho mediano manha, pts | 1240 | 1235 | 1360 | 1250 | 1455 | 1240 | 1322 | 1315 | 1295 | [1245 ; 1350] | 1350 |
| tamanho mediano tarde, pts | 1240 | 1102 | 1350 | 1075 | 1115 | 985 | 950 | 1125 | 1142 | [1110 ; 1232] | 1120 |
| velocidade mediana manha, pts/min | 36,7 | 39,4 | 67,7 | 44,2 | 38,6 | 39,1 | 32,4 | 47,0 | 44,2 | [40,5 ; 47,4] | 64,3 |
| velocidade mediana tarde, pts/min | 22,8 | 14,1 | 30,7 | 13,2 | 11,0 | 10,3 | 14,4 | 9,3 | 17,2 | [14,5 ; 20,6] | 14,5 |
| manha/tarde: velocidade (x mais lenta) | 1,6 | 2,8 | 2,2 | 3,4 | 3,5 | 3,8 | 2,3 | 5,1 | 2,6 | [2,1 ; 3,0] | 4,5 |
| nulo 30 min (p5-p95) | 1,5 (1,1-1,9) | 2,9 (2,3-3,5) | 2,1 (1,8-2,5) | 3,3 (2,6-4,4) | 3,5 (2,8-4,2) | 4,3 (2,7-5,8) | 4,7 (2,7-6,6) | 5,5 (4,1-7,9) | 2,4 (2,1-2,7) | - | 5,6 (4,4-6,9) |
| correcoes por pernada manha / tarde | 5,3 / 5,2 | 3,7 / 6,8 | 3,0 / 4,6 | 4,7 / 7,0 | 4,8 / 8,3 | 4,2 / 7,1 | 5,5 / 7,0 | 5,1 / 10,1 | 4,4 / 6,2 | - | 3,7 / 6,5 |
| tarde/manha: correcoes por pernada | 1,0 | 1,8 | 1,5 | 1,5 | 1,7 | 1,7 | 1,3 | 2,0 | 1,4 | [1,3 ; 1,6] | 1,8 |
| nulo 30 min (p5-p95) | 1,1 (0,9-1,3) | 1,9 (1,6-2,2) | 1,5 (1,3-1,7) | 1,7 (1,4-1,9) | 1,8 (1,5-2,2) | 1,9 (1,6-2,2) | 1,8 (1,4-2,3) | 1,9 (1,5-2,3) | 1,5 (1,4-1,6) | - | 2,1 (1,8-2,4) |
| tarde/manha: correcoes por 1.000 pts | 1,1 | 2,1 | 1,6 | 1,9 | 2,1 | 1,9 | 1,7 | 2,4 | 1,6 | [1,5 ; 1,8] | 2,5 |
| tarde/manha: tamanho | 1,00 | 0,89 | 0,99 | 0,86 | 0,77 | 0,79 | 0,72 | 0,86 | 0,88 | [0,83 ; 0,96] | 0,83 |

### R24: degrau das 10:30

Razao entre a media por minuto dos 15 min depois do corte e dos 15 antes, mediana dos dias; controle = os outros 66 cortes de 5 em 5 min das 10:30 as 16:00. 'posto' = posicao do corte entre os 67 (1 = o maior). Volume = coluna VOL do M1.

| R24 | jan | fev | mar | abr | mai | jun | jul | ago | jan-ago | IC95 jan-ago | set (ref.) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| amplitude 10:30 | 0,96 | 0,98 | 1,23 | 1,21 | 1,13 | 1,19 | 1,27 | 1,21 | 1,16 | [1,11 ; 1,21] | 1,28 |
| posto 10:30 (de 67) | 31 | 24 | 1 | 1 | 2 | 1 | 1 | 1 | 1 | - | 1 |
| amplitude 11:30 | 1,26 | 1,55 | 1,07 | 1,04 | 0,91 | 0,94 | 0,88 | 0,93 | 1,02 | [0,96 ; 1,05] | 0,91 |
| posto 11:30 (de 67) | 1 | 1 | 4 | 9 | 46 | 35 | 54 | 33 | 9 | - | 47 |
| amplitude, mediana dos outros cortes | 0,95 | 0,94 | 0,97 | 0,93 | 0,94 | 0,94 | 0,94 | 0,93 | 0,95 | - | 0,94 |
| volume 10:30 | 0,91 | 0,97 | 1,31 | 1,29 | 1,19 | 1,09 | 1,23 | 1,25 | 1,16 | [1,10 ; 1,21] | 1,28 |
| posto volume 10:30 | 38 | 26 | 1 | 1 | 1 | 5 | 1 | 2 | 1 | - | 1 |
| volume 11:30 | 1,28 | 1,67 | 1,08 | 1,00 | 0,88 | 0,88 | 0,87 | 0,93 | 0,99 | [0,93 ; 1,06] | 0,92 |
| posto volume 11:30 | 1 | 1 | 4 | 20 | 46 | 47 | 49 | 29 | 19 | - | 38 |

## Divisao por regime do horario de NY

Inverno dos EUA: 2/jan a 6/mar (43 pregoes), abertura de NY as 11:30 BRT. Verao dos EUA: 9/mar a ago (121 pregoes), abertura as 10:30 BRT. Definicoes inalteradas (10:30).

| regra | inverno EUA (2/jan-6/mar, 43 dias) | verao EUA (9/mar-ago, 121 dias) | jan-ago |
|---|---:|---:|---:|
| R01 ligada | 10,9% | 14,0% | 13,2% |
| R01 desligada | 5,8% | 4,2% | 4,7% |
| R02 captura | 45,7% | 68,4% | 62,2% |
| R03 >=13h | 3,6% | 3,3% | 3,4% |
| R04 tarde | 66,0% | 63,8% | 64,6% |
| R05 contra consenso | 37,9% | 55,2% | 50,0% |
| R06 janela | 47,6% | 50,7% | 49,9% |
| R07 janela | 42,1% | 49,6% | 47,5% |
| R08 janela | 44,8% | 49,6% | 48,4% |
| R09 gap fecha | 74,4% | 72,5% | 73,0% |
| R10 contra o gap | 46,5% | 55,8% | 53,4% |
| R11 >=1 extremo | 90,7% | 92,6% | 92,1% |
| R12 max (mediana) | 11:47 | 10:41 | 10:44 |
| R12 min (mediana) | 11:10 | 11:03 | 11:04 |
| R20 corr. | 0,62 | 0,41 | 0,50 |
| R21 :00 | 1,22 | 1,43 | 1,37 |
| R21 :30 | 1,16 | 1,18 | 1,18 |
| R22 VR5 | 0,82 | 0,81 | 0,81 |
| R23 velocidade manha/tarde | 2,2 | 2,9 | 2,6 |
| R24 amplitude 10:30 | 0,96 | 1,21 | 1,16 |
| R24 amplitude 11:30 | 1,37 | 0,93 | 1,02 |

## Veredito e leitura por regra

- **R01: replicou.** ligada 13,2% x desligada 4,7% (2,8x); set 20,0% x 4,6% (4,3x). Razao >= 2x em 7 de 8 meses; jan quase sem efeito (8,4% x 6,3%). O nulo por blocos de 30 min da o mesmo (13,2% x 4,7%): e relogio de volatilidade, igual em set.
- **R02: replicou (mais fraco no inverno).** 62,2% das pernadas em 21,1% do tempo (set 73,4%); lift 2,9x. Mensal 39 / 53 / 52 / 64 / 68 / 73 / 84 / 84%: so a partir de jun chega a 73%. O nulo por blocos da 62,6%: relogio.
- **R03: replicou.** 3,4% tarde x 10,3% antes das 13h (set 3,1% x 14,2%). Todos os meses: tarde 1,4-5,8% x manha 8,4-14,8%. Nulo por blocos 3,3%: relogio.
- **R04: falhou.** tarde 64,6% x manha 67,2% (set 75,4%). Nulo por blocos 66,8% (tarde) / 65,9% (manha). A tarde nao destoa do acaso em jan-ago; set foi o mes de pico (n=61).
- **R05: falhou.** contra o consenso 50,0% (48/96) x 85,7% em set; meses 21 / 50 / 69 / 60 / 55 / 42 / 20 / 79%. Inverte de mes para mes; a mediana do restante do dia muda de sinal.
- **R06: falhou.** dentro da janela 49,9% x fora 49,2% (set 73,1% x 51,9%). Jan 37,5% (continuacao), set e o pico.
- **R07: falhou.** dentro 47,5% x fora 49,0% (set 65,9%).
- **R08: falhou.** dentro 48,4% x fora 47,5% (set 61,3%).
- **R09: parcial.** fecha 73,0% (set 85,7%) e em todos os meses >= 63%, mas a mesma distancia percorrida no sentido OPOSTO acontece em 70,6% dos dias: o excesso sobre o acaso e +2 pp (em set era +38 pp: 86% x 48%). E fato do tamanho do range, nao do gap.
- **R10: falhou.** dia termina contra o gap em 53,4% (IC 45,7-60,7%), set 71,4%. Meses 48 / 47 / 45 / 80 / 47 / 52 / 32 / 76%.
- **R11: replicou (= nulo).** 92,1% dos dias (set 95,2%); todos os meses 86-100%. Mas o nulo com horario (blocos de 30 min: 90,9%; blocos sorteados de outros dias: 91,2%) da o mesmo: nao e estrutura, e a pernada de H1 de 750 pts ser grande para o range do dia. 'Ambos os extremos' 27,4% = nulo (26,4%); os 52% de set foram excecao.
- **R12: parcial.** mediana jan-ago: maxima 10:44, minima 11:04 (set 10:28 / 10:29). Mensal da maxima: 12:39 / 11:50 / 11:43 / 10:38 / 09:28 / 10:32 / 10:26 / 10:27. So de abr em diante fica em ~10:30; jan-mar e em torno de 11:45-12:40. O nulo de relogio (blocos de outros dias) da 10:52 / 11:11: o horario segue o relogio de volatilidade, que muda com o mes.
- **R20: replicou.** corr. 0,19-0,67 por mes (set 0,28) x nulo +-0,07; todos os meses acima do p95. Tirando o regime do mes: 0,36 jan-ago; tirando o regime do dia: 0,23 (ainda positivo em todos os meses). Mais forte em jan (0,67) e no inverno (0,53 x 0,26 no verao, regime do mes removido).
- **R21: replicou.** :00 = 1,37x (set 1,51x), todos os meses 1,20-1,60 x nulo 1,00 (p95 ~1,06); :30 = 1,18x (set 1,27x), meses 1,06-1,28 (mar 1,06 fica na borda do nulo). O :00 e mais fraco em jan-mar (1,20-1,25) e mais forte em abr-ago (1,35-1,60).
- **R22: replicou (mais fraco).** VR5 0,81 (set 0,69; IC 0,76-0,87) x nulo 1,00 (0,96-1,04). 7 de 8 meses abaixo do p5 do nulo; mai 1,01 e o unico que nao. Fraco em abr-jun (0,85-1,01).
- **R23: parcial.** tarde/manha: velocidade 2,6x (IC 2,1-3,0; set 4,5x), correcoes por pernada 1,4x (set 1,8x), por 1.000 pts 1,6x (set 2,5x), tamanho 0,88x. Mesmo sentido, magnitude menor que '4x e 3x'. O nulo por blocos (relogio) da 2,4x / 1,5x / 1,7x: e relogio.
- **R24: replicou, com ressalva de horario.** razao de amplitude 10:30: 1,16 jan-ago (set 1,28). Mar-ago 1,13-1,27 e o 1o entre 67 cortes em 5 de 6 meses (mai: 2o); jan e fev NAO tem degrau as 10:30 (0,96 / 0,98) e sim as 11:30 (1,26 / 1,55, 1o corte). O degrau acompanha a abertura de NY: 10:30 BRT so quando os EUA estao no horario de verao (inicio 8/mar/2026).

## Escolhas de definicao (onde o texto original era ambiguo)

- Dias parciais excluidos: 18/02 (abertura 13:00, quarta de cinzas) e 31/07 (abertura 12:34). Os demais 164 pregoes de jan-ago tem 09:00-18:24 (a vela das 09:00 as vezes so tem dado a partir de 09:02-09:04).
- R01-R03: familia 'balanco' (a que gerou 20% x 5% e 73% em `chave.md`), nao a 'extremo'. 'Hora' = abertura da vela M5 do evento. 'Tempo ligado' = fracao das velas M1 antes das 11:00.
- R04: caminho M1 de 4 pontos por vela e eventos de `transicoes/an.py` (tipo 'extremo', X=500, D=750). A tarde e >= 13:00 e a manha < 13:00.
- R05: VWAP ponderada por close x volume e T=10:30 como no `a2.py`; R06-R08 usam VWAP de preco tipico, como no `a4.py`. 'Dentro da janela' = instantes 10:30, 10:45, ..., 12:15.
- R10: 'termina contra o gap' = fechamento menor (maior) que a abertura quando houve gap de alta (baixa). A leitura contra o fechamento anterior aparece como alternativa.
- R11: se o dia tem menos de 2 pernadas H1 de 750, considera-se que os extremos estao nas 'duas primeiras' (todo o dia). Aconteceu em poucos dias e favorece o sim igualmente no nulo.
- R12: horario por vela M1 (abertura da vela), 1a ocorrencia do extremo.
- R20: 37 blocos por dia; media do horario tirada dentro do conjunto de dias analisado (mes ou jan-ago).
- R23: duracao minima 5 min; 'tarde' >= 13:00 (REGRAS.md), 'manha' < 12:00 (relatorio de set).
- Serie: WIN@D com ajuste por diferenca; setembro aqui sai dela e nao do WINV26 do original (R09 deu 18/21 em vez de 17/20 porque 01/09 tem gap contra 31/08; demais numeros de set batem com os originais: R01 20,0%, R02 73,4%, R03 3,1%, R05 12/14 com mediana -1.093, R06 73,1%, R07 65,9%, R08 61,3%, R11 95,2%, R12 10:28/10:29, R21 1,51x/1,27x, R22 0,69, R24 1,28x).
- Nulos: R01-R04 e R23 usam embaralhar velas M1 dentro de blocos de 30 min de cada pregao (300 sorteios; gaps entre velas ficam na posicao). R05, R06-R10: binomial/base real, porque o embaralho de blocos preserva os precos em :00 e :30, abertura e fechamento. R11/R12 recebem tambem o nulo de blocos sorteados de outros dias (300 sorteios), que preserva o relogio de volatilidade e destroi a estrutura do dia.
- Codigo: `lib.py`, `stats.py`, `run.py`, `relatorio.py` nesta pasta (rodada3/replica_dia); resultado bruto em `resultado.pkl`.