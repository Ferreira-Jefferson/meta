# Base F0 — estatística descritiva (WIN$N, 02/01–05/10/2026, sem custo, 1 contrato)

Leitura dos votos na última M1 fechada antes de cada entrada (`eventos.parquet`). `favor`/`contra`/`neutro` = quantas das OUTRAS 5 estratégias votam o lado da entrada / o lado oposto / 0. Acerto = fração de operações com R$ > 0. Cada célula traz o seu n.

**Atenção à gêmea:** Win e Win_c1 têm a mesma lógica de entrada, portanto o mesmo voto. Para essas duas, uma das 5 "outras" é sempre a gêmea (que vota igual ao próprio voto). A segunda tabela de cada uma conta só as 4 independentes.

**Atenção ao próprio voto nos retângulos:** a entrada é uma limite no meio do retângulo que enche quando o preço VOLTA ao meio; na última M1 antes do preenchimento o fechamento muitas vezes já cruzou o meio, e o próprio voto aparece contra (WinRetanguloEma34 vota o lado da entrada em 80,5% das entradas; WdoRetangulo em 97,8%; as outras 4 em 100%).

## 1. Resultado condicionado ao voto das outras

### Win — 181 entradas, acerto 43,6%, R$/op 22,08

| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | — | — | 167 | 45,5% | 22,68 | 1 | 0,0% | -24,00 |
| 1 | 3 | 0,0% | -14,33 | 14 | 21,4% | 15,00 | 17 | 58,8% | 48,47 |
| 2 | 85 | 34,1% | 10,39 | 0 | — | — | 85 | 50,6% | 30,94 |
| 3 | 76 | 52,6% | 30,75 | 0 | — | — | 78 | 33,3% | 7,27 |
| 4 | 16 | 62,5% | 52,75 | 0 | — | — | 0 | — | — |
| 5 | 1 | 0,0% | -24,00 | 0 | — | — | 0 | — | — |

Sem a gêmea (4 outras):

| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 3 | 0,0% | -14,33 | 167 | 45,5% | 22,68 | 1 | 0,0% | -24,00 |
| 1 | 85 | 34,1% | 10,39 | 14 | 21,4% | 15,00 | 17 | 58,8% | 48,47 |
| 2 | 76 | 52,6% | 30,75 | 0 | — | — | 85 | 50,6% | 30,94 |
| 3 | 16 | 62,5% | 52,75 | 0 | — | — | 78 | 33,3% | 7,27 |
| 4 | 1 | 0,0% | -24,00 | 0 | — | — | 0 | — | — |

### Win_c1 — 187 entradas, acerto 40,1%, R$/op 20,32

| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | — | — | 171 | 41,5% | 20,98 | 2 | 0,0% | -26,00 |
| 1 | 3 | 0,0% | -12,00 | 16 | 25,0% | 13,25 | 17 | 52,9% | 46,88 |
| 2 | 88 | 33,0% | 7,00 | 0 | — | — | 89 | 46,1% | 30,81 |
| 3 | 78 | 47,4% | 31,46 | 0 | — | — | 79 | 31,6% | 3,95 |
| 4 | 16 | 56,2% | 51,06 | 0 | — | — | 0 | — | — |
| 5 | 2 | 0,0% | -26,00 | 0 | — | — | 0 | — | — |

Sem a gêmea (4 outras):

| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 3 | 0,0% | -12,00 | 171 | 41,5% | 20,98 | 2 | 0,0% | -26,00 |
| 1 | 88 | 33,0% | 7,00 | 16 | 25,0% | 13,25 | 17 | 52,9% | 46,88 |
| 2 | 78 | 47,4% | 31,46 | 0 | — | — | 89 | 46,1% | 30,81 |
| 3 | 16 | 56,2% | 51,06 | 0 | — | — | 79 | 31,6% | 3,95 |
| 4 | 2 | 0,0% | -26,00 | 0 | — | — | 0 | — | — |

### WinCincoMedias — 308 entradas, acerto 40,6%, R$/op 28,76

| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 8 | 25,0% | 5,25 | 263 | 43,0% | 32,25 | 4 | 25,0% | -34,00 |
| 1 | 97 | 39,2% | 18,46 | 35 | 25,7% | 10,09 | 42 | 50,0% | 19,10 |
| 2 | 72 | 43,1% | 36,51 | 10 | 30,0% | 2,50 | 108 | 36,1% | 38,67 |
| 3 | 94 | 38,3% | 42,88 | 0 | — | — | 63 | 41,3% | 29,57 |
| 4 | 34 | 50,0% | 12,91 | 0 | — | — | 91 | 41,8% | 23,67 |
| 5 | 3 | 33,3% | -24,33 | 0 | — | — | 0 | — | — |

### WinDeslocamentoMatinal — 65 entradas, acerto 38,5%, R$/op 34,14

| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 6 | 33,3% | -61,83 | 48 | 39,6% | 68,12 | 4 | 50,0% | 52,25 |
| 1 | 22 | 31,8% | -2,64 | 11 | 36,4% | -32,18 | 20 | 50,0% | 108,55 |
| 2 | 12 | 41,7% | 57,08 | 5 | 40,0% | -68,00 | 8 | 0,0% | -204,38 |
| 3 | 8 | 37,5% | -37,25 | 1 | 0,0% | -357,00 | 8 | 50,0% | 149,75 |
| 4 | 14 | 50,0% | 151,57 | 0 | — | — | 25 | 36,0% | 11,04 |
| 5 | 3 | 33,3% | 46,33 | 0 | — | — | 0 | — | — |

### WinRetanguloEma34 — 733 entradas, acerto 42,2%, R$/op 3,15

| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 253 | 40,7% | 2,72 | 566 | 40,3% | 1,38 | 15 | 53,3% | 16,20 |
| 1 | 328 | 45,4% | 5,76 | 97 | 48,5% | 8,47 | 49 | 44,9% | 6,31 |
| 2 | 59 | 45,8% | 5,75 | 37 | 40,5% | 1,03 | 93 | 34,4% | -5,75 |
| 3 | 55 | 25,5% | -13,69 | 23 | 56,5% | 18,74 | 104 | 48,1% | 9,89 |
| 4 | 31 | 41,9% | 3,42 | 8 | 50,0% | 15,00 | 294 | 44,2% | 4,28 |
| 5 | 7 | 42,9% | 5,57 | 2 | 100,0% | 56,50 | 178 | 37,6% | 0,01 |

### WdoRetangulo — 134 entradas, acerto 51,5%, R$/op 21,17

| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 29 | 44,8% | -40,00 | 86 | 50,0% | 20,06 | 4 | 75,0% | 20,50 |
| 1 | 69 | 49,3% | 50,59 | 27 | 59,3% | 77,19 | 17 | 58,8% | 25,65 |
| 2 | 17 | 52,9% | -29,82 | 7 | 57,1% | 41,86 | 17 | 52,9% | -39,00 |
| 3 | 8 | 62,5% | 20,75 | 6 | 33,3% | -164,67 | 37 | 54,1% | 28,35 |
| 4 | 10 | 70,0% | 80,30 | 6 | 50,0% | -49,83 | 52 | 48,1% | 53,15 |
| 5 | 1 | 100,0% | 44,00 | 2 | 50,0% | 11,00 | 7 | 28,6% | -118,71 |

### Resumo: mais outras a favor do que contra / empate / mais contra (Win e Win_c1 sem a gêmea)

| estratégia | favor>contra: n | R$/op | acerto | empate: n | R$/op | acerto | contra>favor: n | R$/op | acerto |
|---|---|---|---|---|---|---|---|---|---|
| Win | 168 | 22,42 | 45,2% | 10 | 27,30 | 30,0% | 3 | -14,33 | 0,0% |
| Win_c1 | 172 | 20,74 | 41,3% | 12 | 22,33 | 33,3% | 3 | -12,00 | 0,0% |
| WinCincoMedias | 285 | 32,35 | 42,1% | 12 | -18,33 | 25,0% | 11 | -12,91 | 18,2% |
| WinDeslocamentoMatinal | 56 | 52,36 | 39,3% | 2 | -31,00 | 50,0% | 7 | -93,00 | 28,6% |
| WinRetanguloEma34 | 397 | 1,99 | 41,6% | 217 | 2,83 | 40,6% | 119 | 7,58 | 47,1% |
| WdoRetangulo | 81 | 33,38 | 53,1% | 25 | 21,56 | 48,0% | 28 | -14,50 | 50,0% |

## 2. Correlação diária de resultado (R$ por dia de saída)

Pearson sobre os 190 pregões do período, dia sem operação = 0. Pregões com operação: Win 99, Win_c1 99, Cinco 131, Desloc 65, RetEma34 163, WdoRet 131.

| | Win | Win_c1 | Cinco | Desloc | RetEma34 | WdoRet |
|---|---|---|---|---|---|---|
| Win | 1,00 | 0,97 | 0,32 | 0,13 | -0,04 | -0,06 |
| Win_c1 | 0,97 | 1,00 | 0,33 | 0,16 | -0,04 | -0,08 |
| Cinco | 0,32 | 0,33 | 1,00 | 0,36 | 0,10 | 0,02 |
| Desloc | 0,13 | 0,16 | 0,36 | 1,00 | 0,05 | 0,10 |
| RetEma34 | -0,04 | -0,04 | 0,10 | 0,05 | 1,00 | -0,08 |
| WdoRet | -0,06 | -0,08 | 0,02 | 0,10 | -0,08 | 1,00 |

Só nos dias em que as DUAS operaram (n de dias entre parênteses):

| | Win | Win_c1 | Cinco | Desloc | RetEma34 | WdoRet |
|---|---|---|---|---|---|---|
| Win | (99) | 0,97 (99) | 0,50 (74) | 0,26 (34) | -0,04 (86) | -0,10 (65) |
| Win_c1 | 0,97 (99) | (99) | 0,51 (74) | 0,30 (34) | -0,05 (86) | -0,15 (65) |
| Cinco | 0,50 (74) | 0,51 (74) | (131) | 0,56 (42) | 0,19 (110) | 0,00 (90) |
| Desloc | 0,26 (34) | 0,30 (34) | 0,56 (42) | (65) | 0,09 (52) | 0,20 (42) |
| RetEma34 | -0,04 (86) | -0,05 (86) | 0,19 (110) | 0,09 (52) | (163) | -0,10 (112) |
| WdoRet | -0,10 (65) | -0,15 (65) | 0,00 (90) | 0,20 (42) | -0,10 (112) | (131) |

## 3. Concordância de votos por par (todas as M1 do período)

106.615 barras M1. Em cada célula: % de barras no mesmo lado, sobre as barras em que as duas votam ≠ 0; entre parênteses, % das barras em que as duas votam ≠ 0 e o n dessas barras. Na diagonal, % das barras com voto ≠ 0.

| | Win | Win_c1 | Cinco | Desloc | RetEma34 | WdoRet |
|---|---|---|---|---|---|---|
| Win | ativo 22,8% | 100,0% (22,8%; 24261) | 99,9% (13,5%; 14380) | 95,6% (5,5%; 5905) | 76,3% (22,0%; 23504) | 63,9% (7,2%; 7672) |
| Win_c1 | 100,0% (22,8%; 24261) | ativo 22,8% | 99,9% (13,5%; 14380) | 95,6% (5,5%; 5905) | 76,3% (22,0%; 23504) | 63,9% (7,2%; 7672) |
| Cinco | 99,9% (13,5%; 14380) | 99,9% (13,5%; 14380) | ativo 26,7% | 94,4% (8,6%; 9134) | 66,6% (26,1%; 27778) | 58,9% (8,9%; 9502) |
| Desloc | 95,6% (5,5%; 5905) | 95,6% (5,5%; 5905) | 94,4% (8,6%; 9134) | ativo 24,9% | 60,0% (24,3%; 25897) | 52,8% (10,6%; 11250) |
| RetEma34 | 76,3% (22,0%; 23504) | 76,3% (22,0%; 23504) | 66,6% (26,1%; 27778) | 60,0% (24,3%; 25897) | ativo 97,4% | 86,2% (34,8%; 37110) |
| WdoRet | 63,9% (7,2%; 7672) | 63,9% (7,2%; 7672) | 58,9% (8,9%; 9502) | 52,8% (10,6%; 11250) | 86,2% (34,8%; 37110) | ativo 36,8% |

Fração de barras por voto:

| estratégia | +1 | −1 | 0 | forca média (voto ≠ 0) |
|---|---|---|---|---|
| Win | 11,2% | 11,6% | 77,2% | 0,74 |
| Win_c1 | 11,2% | 11,6% | 77,2% | 0,74 |
| WinCincoMedias | 15,3% | 11,5% | 73,3% | 0,89 |
| WinDeslocamentoMatinal | 10,9% | 14,0% | 75,1% | 0,67 |
| WinRetanguloEma34 | 48,5% | 48,9% | 2,6% | 0,37 |
| WdoRetangulo | 18,6% | 18,2% | 63,2% | 0,62 |
