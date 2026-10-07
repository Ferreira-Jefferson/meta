
## 1. Direcao de D-1 -> direcao do GAP de abertura (gap==0 excluido)


| evento | cond | IS_n | IS_taxa | IS_ic | IS_base | IS_dif_pp | IS_p | OOS_n | OOS_taxa | OOS_ic | OOS_base | OOS_dif_pp | OOS_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P(gap alta) | D-1 alta (C>C-1) | 386 | 42,0 | [37,1;46,9] | 49,9 | -7,9 | 0,0019 | 215 | 44,7 | [38,2;51,3] | 52,0 | -7,3 | 0,0312 |
| P(gap baixa) | D-1 alta (C>C-1) | 386 | 58,0 | [53,1;62,9] | 50,1 | 7,9 | 0,0019 | 215 | 55,3 | [48,7;61,8] | 48,0 | 7,3 | 0,0312 |
| P(gap alta) | D-1 baixa (C<C-1) | 396 | 57,8 | [52,9;62,6] | 49,9 | 8,0 | 0,0015 | 211 | 59,7 | [53,0;66,1] | 52,0 | 7,7 | 0,0247 |
| P(gap baixa) | D-1 baixa (C<C-1) | 396 | 42,2 | [37,4;47,1] | 50,1 | -8,0 | 0,0015 | 211 | 40,3 | [33,9;47,0] | 48,0 | -7,7 | 0,0247 |
| P(gap alta) | D-1 candle alta (C>O) | 407 | 40,8 | [36,1;45,6] | 49,9 | -9,1 | 0,0002 | 218 | 47,2 | [40,7;53,9] | 52,0 | -4,7 | 0,1610 |
| P(gap baixa) | D-1 candle alta (C>O) | 407 | 59,2 | [54,4;63,9] | 50,1 | 9,1 | 0,0002 | 218 | 52,8 | [46,1;59,3] | 48,0 | 4,7 | 0,1610 |
| P(gap alta) | D-1 candle baixa (C<O) | 374 | 59,9 | [54,8;64,7] | 49,9 | 10,0 | 0,0001 | 208 | 57,2 | [50,4;63,7] | 52,0 | 5,2 | 0,1318 |
| P(gap baixa) | D-1 candle baixa (C<O) | 374 | 40,1 | [35,3;45,2] | 50,1 | -10,0 | 0,0001 | 208 | 42,8 | [36,3;49,6] | 48,0 | -5,2 | 0,1318 |


## 1b. Conjunta e gap medio


| janela | conjunta | n | valor | ic | unidade |
|---|---|---|---|---|---|
| IS | D-1 alta E gap baixa | 224 | 28,3 | [25,3;31,6] | % dos dias |
| IS | D-1 baixa E gap alta | 229 | 29,0 | [25,9;32,2] | % dos dias |
| IS | D-1 alta E gap alta | 162 | 20,5 | [17,8;23,4] | % dos dias |
| IS | D-1 baixa E gap baixa | 167 | 21,1 | [18,4;24,1] | % dos dias |
| IS | gap medio apos D-1 alta | 389 | -73,1 |  | pts |
| IS | gap medio apos D-1 baixa | 400 | 50,9 |  | pts |
| IS | |gap| medio (todos) | 791 | 430,8 |  | pts |
| OOS | D-1 alta E gap baixa | 119 | 27,4 | [23,4;31,8] | % dos dias |
| OOS | D-1 baixa E gap alta | 126 | 29,0 | [25,0;33,5] | % dos dias |
| OOS | D-1 alta E gap alta | 96 | 22,1 | [18,5;26,3] | % dos dias |
| OOS | D-1 baixa E gap baixa | 85 | 19,6 | [16,1;23,6] | % dos dias |
| OOS | gap medio apos D-1 alta | 220 | -37,8 |  | pts |
| OOS | gap medio apos D-1 baixa | 213 | 91,9 |  | pts |
| OOS | |gap| medio (todos) | 434 | 489,1 |  | pts |


## 2. Direcao D-1 -> direcao de D


| evento | cond | IS_n | IS_taxa | IS_ic | IS_base | IS_dif_pp | IS_p | OOS_n | OOS_taxa | OOS_ic | OOS_base | OOS_dif_pp | OOS_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P(D fecha acima de C-1) | D-1 alta cc | 389 | 47,0 | [42,1;52,0] | 49,3 | -2,3 | 0,3728 | 220 | 49,1 | [42,6;55,7] | 50,8 | -1,7 | 0,6104 |
| P(D candle alta, C>O) | D-1 alta cc | 388 | 52,1 | [47,1;57,0] | 52,0 | 0,0 | 0,9901 | 220 | 49,1 | [42,6;55,7] | 51,3 | -2,2 | 0,5178 |
| P(D fecha acima de C-1) | D-1 baixa cc | 398 | 51,3 | [46,4;56,1] | 49,3 | 2,0 | 0,4357 | 212 | 52,8 | [46,1;59,4] | 50,8 | 2,0 | 0,5560 |
| P(D candle alta, C>O) | D-1 baixa cc | 398 | 51,8 | [46,9;56,6] | 52,0 | -0,3 | 0,9136 | 213 | 53,5 | [46,8;60,1] | 51,3 | 2,3 | 0,5110 |
| P(D fecha acima de C-1) | D-1 candle alta | 410 | 46,6 | [41,8;51,4] | 49,3 | -2,7 | 0,2711 | 222 | 51,4 | [44,8;57,8] | 50,8 | 0,5 | 0,8714 |
| P(D candle alta, C>O) | D-1 candle alta | 409 | 51,3 | [46,5;56,2] | 52,0 | -0,7 | 0,7813 | 222 | 50,0 | [43,5;56,5] | 51,3 | -1,3 | 0,7050 |
| P(D fecha acima de C-1) | D-1 candle baixa | 376 | 52,1 | [47,1;57,1] | 49,3 | 2,8 | 0,2733 | 210 | 50,0 | [43,3;56,7] | 50,8 | -0,8 | 0,8148 |
| P(D candle alta, C>O) | D-1 candle baixa | 376 | 52,7 | [47,6;57,7] | 52,0 | 0,6 | 0,8071 | 210 | 52,4 | [45,6;59,0] | 51,3 | 1,1 | 0,7474 |


## 2b. Autocorrelacao dos retornos diarios (cc / ATR)

| janela | lag | autocorr | nulo 95% | n |
|---|---|---|---|---|
| IS | 1 | <bound method Series,autocorr of janela           IS
lag               1
autocorr     -0,041
nulo_95     +-0,070
n               791
Name: 0, dtype: object> | +-0,070 | 791 |
| IS | 2 | <bound method Series,autocorr of janela           IS
lag               2
autocorr     -0,038
nulo_95     +-0,070
n               791
Name: 1, dtype: object> | +-0,070 | 791 |
| IS | 3 | <bound method Series,autocorr of janela           IS
lag               3
autocorr      0,009
nulo_95     +-0,070
n               791
Name: 2, dtype: object> | +-0,070 | 791 |
| IS | 4 | <bound method Series,autocorr of janela           IS
lag               4
autocorr      0,062
nulo_95     +-0,070
n               791
Name: 3, dtype: object> | +-0,070 | 791 |
| IS | 5 | <bound method Series,autocorr of janela           IS
lag               5
autocorr     -0,044
nulo_95     +-0,070
n               791
Name: 4, dtype: object> | +-0,070 | 791 |
| OOS | 1 | <bound method Series,autocorr of janela          OOS
lag               1
autocorr     -0,057
nulo_95     +-0,094
n               434
Name: 5, dtype: object> | +-0,094 | 434 |
| OOS | 2 | <bound method Series,autocorr of janela          OOS
lag               2
autocorr      0,038
nulo_95     +-0,094
n               434
Name: 6, dtype: object> | +-0,094 | 434 |
| OOS | 3 | <bound method Series,autocorr of janela          OOS
lag               3
autocorr     -0,022
nulo_95     +-0,094
n               434
Name: 7, dtype: object> | +-0,094 | 434 |
| OOS | 4 | <bound method Series,autocorr of janela          OOS
lag               4
autocorr      0,099
nulo_95     +-0,095
n               434
Name: 8, dtype: object> | +-0,095 | 434 |
| OOS | 5 | <bound method Series,autocorr of janela          OOS
lag               5
autocorr      0,007
nulo_95     +-0,095
n               434
Name: 9, dtype: object> | +-0,095 | 434 |

## 3a. Quintis (cortes do IS) do retorno de D-1 / ATR
Cortes IS (ret/ATR): [-0.58, -0.16, 0.16, 0.54]

| evento | cond | IS_n | IS_taxa | IS_ic | IS_base | IS_dif_pp | IS_p | OOS_n | OOS_taxa | OOS_ic | OOS_base | OOS_dif_pp | OOS_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P(D alta cc) | Q1 | 157 | 52,9 | [45,1;60,5] | 49,3 | 3,6 | 0,3718 | 56 | 57,1 | [44,1;69,2] | 50,8 | 6,3 | 0,3430 |
| P(D candle alta) | Q1 | 156 | 49,4 | [41,6;57,1] | 52,0 | -2,7 | 0,5042 | 56 | 58,9 | [45,9;70,8] | 51,3 | 7,7 | 0,2516 |
| P(gap alta) | Q1 | 158 | 62,7 | [54,9;69,8] | 49,9 | 12,8 | 0,0013 | 54 | 64,8 | [51,5;76,2] | 52,0 | 12,8 | 0,0593 |
| P(D alta cc) | Q2 | 157 | 47,1 | [39,5;54,9] | 49,3 | -2,2 | 0,5867 | 109 | 53,2 | [43,9;62,3] | 50,8 | 2,4 | 0,6158 |
| P(D candle alta) | Q2 | 158 | 51,3 | [43,5;58,9] | 52,0 | -0,8 | 0,8474 | 110 | 55,5 | [46,1;64,4] | 51,3 | 4,2 | 0,3799 |
| P(gap alta) | Q2 | 154 | 57,1 | [49,2;64,7] | 49,9 | 7,3 | 0,0712 | 110 | 56,4 | [47,0;65,3] | 52,0 | 4,4 | 0,3586 |
| P(D alta cc) | Q3 | 158 | 53,8 | [46,0;61,4] | 49,3 | 4,5 | 0,2585 | 92 | 45,7 | [35,9;55,8] | 50,8 | -5,2 | 0,3225 |
| P(D candle alta) | Q3 | 158 | 58,2 | [50,4;65,6] | 52,0 | 6,2 | 0,1189 | 91 | 41,8 | [32,2;52,0] | 51,3 | -9,5 | 0,0695 |
| P(gap alta) | Q3 | 158 | 49,4 | [41,7;57,1] | 49,9 | -0,5 | 0,8989 | 91 | 53,8 | [43,7;63,7] | 52,0 | 1,9 | 0,7231 |
| P(D alta cc) | Q4 | 158 | 42,4 | [35,0;50,2] | 49,3 | -6,9 | 0,0829 | 90 | 51,1 | [41,0;61,2] | 50,8 | 0,3 | 0,9542 |
| P(D candle alta) | Q4 | 158 | 46,8 | [39,2;54,6] | 52,0 | -5,2 | 0,1912 | 90 | 52,2 | [42,0;62,2] | 51,3 | 1,0 | 0,8566 |
| P(gap alta) | Q4 | 156 | 41,0 | [33,6;48,9] | 49,9 | -8,8 | 0,0271 | 89 | 46,1 | [36,1;56,4] | 52,0 | -5,9 | 0,2634 |
| P(D alta cc) | Q5 | 159 | 50,3 | [42,6;58,0] | 49,3 | 1,0 | 0,7986 | 86 | 48,8 | [38,6;59,2] | 50,8 | -2,0 | 0,7146 |
| P(D candle alta) | Q5 | 158 | 54,4 | [46,7;62,0] | 52,0 | 2,4 | 0,5460 | 86 | 50,0 | [39,7;60,3] | 51,3 | -1,3 | 0,8137 |
| P(gap alta) | Q5 | 158 | 39,2 | [32,0;47,0] | 49,9 | -10,6 | 0,0075 | 83 | 42,2 | [32,1;52,9] | 52,0 | -9,8 | 0,0733 |


## 3b. Posicao do fechamento de D-1 no range de D-1


| evento | cond | IS_n | IS_taxa | IS_ic | IS_base | IS_dif_pp | IS_p | OOS_n | OOS_taxa | OOS_ic | OOS_base | OOS_dif_pp | OOS_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P(D alta cc) | fechou <20% do range (perto da minima) | 179 | 55,9 | [48,5;62,9] | 49,3 | 6,6 | 0,0790 | 86 | 50,0 | [39,7;60,3] | 50,8 | -0,8 | 0,8808 |
| P(D candle alta) | fechou <20% do range (perto da minima) | 181 | 54,1 | [46,9;61,2] | 52,0 | 2,1 | 0,5693 | 86 | 52,3 | [41,9;62,6] | 51,3 | 1,1 | 0,8448 |
| P(gap alta) | fechou <20% do range (perto da minima) | 179 | 62,0 | [54,7;68,8] | 49,9 | 12,1 | 0,0012 | 85 | 68,2 | [57,7;77,2] | 52,0 | 16,2 | 0,0027 |
| P(D alta cc) | 20-80% (meio) | 396 | 47,7 | [42,9;52,6] | 49,3 | -1,6 | 0,5306 | 257 | 50,2 | [44,1;56,3] | 50,8 | -0,6 | 0,8440 |
| P(D candle alta) | 20-80% (meio) | 394 | 51,0 | [46,1;55,9] | 52,0 | -1,0 | 0,6867 | 257 | 50,6 | [44,5;56,6] | 51,3 | -0,7 | 0,8257 |
| P(gap alta) | 20-80% (meio) | 393 | 53,2 | [48,2;58,1] | 49,9 | 3,3 | 0,1896 | 255 | 49,8 | [43,7;55,9] | 52,0 | -2,2 | 0,4846 |
| P(D alta cc) | fechou >80% (perto da maxima) | 214 | 46,7 | [40,2;53,4] | 49,3 | -2,6 | 0,4514 | 90 | 53,3 | [43,1;63,3] | 50,8 | 2,5 | 0,6318 |
| P(D candle alta) | fechou >80% (perto da maxima) | 213 | 52,1 | [45,4;58,7] | 52,0 | 0,1 | 0,9808 | 90 | 52,2 | [42,0;62,2] | 51,3 | 1,0 | 0,8566 |
| P(gap alta) | fechou >80% (perto da maxima) | 212 | 33,5 | [27,5;40,1] | 49,9 | -16,4 | 0,0000 | 87 | 42,5 | [32,7;53,0] | 52,0 | -9,5 | 0,0773 |


## 3c. Retorno medio de D (pontos) por quintil de D-1


| quintil | janela | n | cc_D_medio_pts | ic95_pts | media_geral_pts | oc_D_medio_pts |
|---|---|---|---|---|---|---|
| 1 | IS | 158 | -23,8 | +-200 | -33,1 | -101,6 |
| 1 | OOS | 56 | 333,5 | +-398 | 78,5 | 229,9 |
| 2 | IS | 158 | -9,3 | +-216 | -33,1 | -65,0 |
| 2 | OOS | 110 | 164,3 | +-281 | 78,5 | 122,5 |
| 3 | IS | 158 | 184,5 | +-202 | -33,1 | 204,8 |
| 3 | OOS | 92 | 12,8 | +-349 | 78,5 | -119,9 |
| 4 | IS | 158 | -276,6 | +-220 | -33,1 | -143,5 |
| 4 | OOS | 90 | -8,5 | +-386 | 78,5 | 36,8 |
| 5 | IS | 159 | -40,3 | +-228 | -33,1 | -4,5 |
| 5 | OOS | 86 | -35,8 | +-468 | 78,5 | 52,5 |


## 4a. Gap e o dia (nulo do 'gap fecha' = mistura dos dois sinais)


| evento | cond | IS_n | IS_taxa | IS_ic | IS_base | IS_dif_pp | IS_p | OOS_n | OOS_taxa | OOS_ic | OOS_base | OOS_dif_pp | OOS_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P(C>O) | gap alta | 390 | 49,2 | [44,3;54,2] | 52,0 | -2,8 | 0,2684 | 222 | 48,2 | [41,7;54,7] | 51,3 | -3,1 | 0,3598 |
| P(C<O) | gap alta | 390 | 50,8 | [45,8;55,7] | 48,0 | 2,8 | 0,2684 | 222 | 51,8 | [45,3;58,3] | 48,7 | 3,1 | 0,3598 |
| P(gap fecha no dia) | gap alta | 391 | 73,4 | [68,8;77,5] | 73,5 | -0,1 | 0,9758 | 222 | 75,7 | [69,6;80,9] | 76,1 | -0,4 | 0,8787 |
| P(C>O) | gap baixa | 391 | 54,5 | [49,5;59,3] | 52,0 | 2,4 | 0,3331 | 204 | 53,9 | [47,1;60,6] | 51,3 | 2,7 | 0,4487 |
| P(C<O) | gap baixa | 391 | 45,5 | [40,7;50,5] | 48,0 | -2,4 | 0,3331 | 204 | 46,1 | [39,4;52,9] | 48,7 | -2,7 | 0,4487 |
| P(gap fecha no dia) | gap baixa | 393 | 73,5 | [69,0;77,7] | 73,5 | 0,1 | 0,9758 | 205 | 76,6 | [70,3;81,9] | 76,1 | 0,5 | 0,8738 |


## 4b. Por tamanho do gap (quintis |gap|/ATR do IS)
Cortes IS |gap|/ATR: [0.081, 0.137, 0.205, 0.318]

| evento | cond | IS_n | IS_taxa | IS_ic | IS_base | IS_dif_pp | IS_p | OOS_n | OOS_taxa | OOS_ic | OOS_base | OOS_dif_pp | OOS_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P(dia a favor do gap) | gap alta Q1 | 70 | 54,3 | [42,7;65,4] | 52,0 | 2,3 | 0,7057 | 67 | 53,7 | [41,9;65,1] | 51,3 | 2,5 | 0,6869 |
| P(gap fecha) | gap alta Q1 | 70 | 94,3 | [86,2;97,8] | 73,5 | 20,8 | 0,0001 | 67 | 92,5 | [83,7;96,8] | 76,1 | 16,4 | 0,0016 |
| P(dia a favor do gap) | gap alta Q2 | 77 | 37,7 | [27,7;48,8] | 52,0 | -14,4 | 0,0116 | 39 | 46,2 | [31,6;61,4] | 51,3 | -5,1 | 0,5227 |
| P(gap fecha) | gap alta Q2 | 78 | 87,2 | [78,0;92,9] | 73,5 | 13,7 | 0,0061 | 39 | 82,1 | [67,3;91,0] | 76,1 | 5,9 | 0,3844 |
| P(dia a favor do gap) | gap alta Q3 | 81 | 53,1 | [42,3;63,6] | 52,0 | 1,1 | 0,8491 | 43 | 37,2 | [24,4;52,1] | 51,3 | -14,1 | 0,0651 |
| P(gap fecha) | gap alta Q3 | 81 | 74,1 | [63,6;82,4] | 73,5 | 0,6 | 0,9019 | 43 | 79,1 | [64,8;88,6] | 76,1 | 3,0 | 0,6493 |
| P(dia a favor do gap) | gap alta Q4 | 81 | 48,1 | [37,6;58,9] | 52,0 | -3,9 | 0,4843 | 40 | 50,0 | [35,2;64,8] | 51,3 | -1,3 | 0,8723 |
| P(gap fecha) | gap alta Q4 | 81 | 65,4 | [54,6;74,9] | 73,5 | -8,0 | 0,1013 | 40 | 62,5 | [47,0;75,8] | 76,1 | -13,6 | 0,0435 |
| P(dia a favor do gap) | gap alta Q5 | 81 | 53,1 | [42,3;63,6] | 52,0 | 1,1 | 0,8491 | 33 | 51,5 | [35,2;67,5] | 51,3 | 0,2 | 0,9775 |
| P(gap fecha) | gap alta Q5 | 81 | 49,4 | [38,8;60,0] | 73,5 | -24,1 | 0,0000 | 33 | 45,5 | [29,8;62,0] | 76,1 | -30,7 | 0,0000 |
| P(dia a favor do gap) | gap baixa Q1 | 87 | 48,3 | [38,1;58,6] | 48,0 | 0,3 | 0,9544 | 61 | 49,2 | [37,1;61,4] | 48,7 | 0,5 | 0,9439 |
| P(gap fecha) | gap baixa Q1 | 87 | 94,3 | [87,2;97,5] | 73,5 | 20,8 | 0,0000 | 61 | 95,1 | [86,5;98,3] | 76,1 | 19,0 | 0,0005 |
| P(dia a favor do gap) | gap baixa Q2 | 79 | 39,2 | [29,2;50,3] | 48,0 | -8,7 | 0,1204 | 39 | 46,2 | [31,6;61,4] | 48,7 | -2,6 | 0,7476 |
| P(gap fecha) | gap baixa Q2 | 79 | 87,3 | [78,2;93,0] | 73,5 | 13,9 | 0,0052 | 40 | 77,5 | [62,5;87,7] | 76,1 | 1,4 | 0,8369 |
| P(dia a favor do gap) | gap baixa Q3 | 74 | 51,4 | [40,2;62,4] | 48,0 | 3,4 | 0,5604 | 36 | 47,2 | [32,0;63,0] | 48,7 | -1,5 | 0,8564 |
| P(gap fecha) | gap baixa Q3 | 75 | 73,3 | [62,4;82,0] | 73,5 | -0,1 | 0,9787 | 36 | 77,8 | [61,9;88,3] | 76,1 | 1,7 | 0,8147 |
| P(dia a favor do gap) | gap baixa Q4 | 75 | 41,3 | [30,9;52,6] | 48,0 | -6,6 | 0,2500 | 32 | 53,1 | [36,4;69,1] | 48,7 | 4,4 | 0,6189 |
| P(gap fecha) | gap baixa Q4 | 76 | 69,7 | [58,7;78,9] | 73,5 | -3,7 | 0,4611 | 32 | 59,4 | [42,3;74,5] | 76,1 | -16,7 | 0,0264 |
| P(dia a favor do gap) | gap baixa Q5 | 76 | 47,4 | [36,5;58,4] | 48,0 | -0,6 | 0,9165 | 36 | 33,3 | [20,2;49,7] | 48,7 | -15,4 | 0,0646 |
| P(gap fecha) | gap baixa Q5 | 76 | 39,5 | [29,2;50,7] | 73,5 | -34,0 | 0,0000 | 36 | 58,3 | [42,2;72,9] | 76,1 | -17,8 | 0,0124 |


## 5. Sequencias de dias (cc) vs embaralhamento (2000 permutacoes)


| janela | sequencia | n | P_continuar | ic | nulo_embaralhado | nulo_p2_5_p97_5 | p_perm |
|---|---|---|---|---|---|---|---|
| IS | 2 dias alta | 183 | 46,4 | [39,4;53,7] | 49,0 | [42,5;55,1] | 0,4093 |
| IS | 3 dias alta | 85 | 48,2 | [37,9;58,7] | 48,8 | [38,8;58,2] | 0,9235 |
| IS | 4 dias alta | 41 | 51,2 | [36,5;65,7] | 48,1 | [32,6;61,4] | 0,6537 |
| IS | 2 dias baixa | 194 | 47,9 | [41,0;54,9] | 50,3 | [44,3;56,4] | 0,4353 |
| IS | 3 dias baixa | 93 | 46,2 | [36,5;56,3] | 50,1 | [40,7;58,5] | 0,4223 |
| IS | 4 dias baixa | 43 | 48,8 | [34,6;63,2] | 49,7 | [35,1;61,7] | 0,8991 |
| OOS | 2 dias alta | 107 | 43,9 | [34,9;53,4] | 50,4 | [42,0;58,2] | 0,1164 |
| OOS | 3 dias alta | 47 | 46,8 | [33,3;60,8] | 49,9 | [36,2;61,7] | 0,6247 |
| OOS | 4 dias alta | 22 | 59,1 | [38,7;76,7] | 49,2 | [28,6;65,7] | 0,2934 |
| OOS | 2 dias baixa | 100 | 46,0 | [36,6;55,7] | 48,8 | [40,6;56,9] | 0,4998 |
| OOS | 3 dias baixa | 46 | 41,3 | [28,3;55,7] | 48,0 | [34,3;60,0] | 0,3128 |
| OOS | 4 dias baixa | 19 | 42,1 | [23,1;63,7] | 46,9 | [25,0;64,0] | 0,6577 |


## 6a. Rompimento da maxima/minima de D-1 (base = todos os dias)


| evento | cond | IS_n | IS_taxa | IS_ic | IS_base | IS_dif_pp | IS_p | OOS_n | OOS_taxa | OOS_ic | OOS_base | OOS_dif_pp | OOS_p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rompe maxima D-1 | D-1 alta | 389 | 63,8 | [58,9;68,4] | 49,1 | 14,7 | 0,0000 | 220 | 58,2 | [51,6;64,5] | 47,2 | 10,9 | 0,0011 |
| rompe minima D-1 | D-1 alta | 389 | 38,8 | [34,1;43,7] | 51,2 | -12,4 | 0,0000 | 220 | 35,5 | [29,4;42,0] | 48,4 | -12,9 | 0,0001 |
| rompe as duas | D-1 alta | 389 | 13,1 | [10,1;16,8] | 11,1 | 2,0 | 0,2130 | 220 | 8,2 | [5,2;12,6] | 9,9 | -1,7 | 0,3915 |
| rompe maxima D-1 | D-1 baixa | 400 | 34,5 | [30,0;39,3] | 49,1 | -14,6 | 0,0000 | 213 | 35,7 | [29,6;42,3] | 47,2 | -11,6 | 0,0007 |
| rompe minima D-1 | D-1 baixa | 400 | 63,5 | [58,7;68,1] | 51,2 | 12,3 | 0,0000 | 213 | 61,5 | [54,8;67,8] | 48,4 | 13,1 | 0,0001 |
| rompe as duas | D-1 baixa | 400 | 9,2 | [6,8;12,5] | 11,1 | -1,9 | 0,2330 | 213 | 11,3 | [7,7;16,2] | 9,9 | 1,4 | 0,5065 |


## 6b. Rompe o nivel de D-1 primeiro -> fecha alem dele
Se o gap ja abre alem do nivel, o rompimento conta na barra 0.

| janela | evento | n | taxa | ic | nulo_mesmos_dias_C_a_favor_da_abertura | nulo_geral_dia_a_favor |
|---|---|---|---|---|---|---|
| IS | rompe maxima primeiro -> fecha acima dela | 349 | 54,7 | [49,5;59,9] | 69,6 | 51,8 |
| IS | rompe minima primeiro -> fecha abaixo dela | 355 | 51,5 | [46,4;56,7] | 66,2 | 47,8 |
| IS | sem ordem definida (mesma barra) / nenhuma rompeu | 1 |  | nenhuma=86 |  |  |
| OOS | rompe maxima primeiro -> fecha acima dela | 178 | 55,6 | [48,3;62,7] | 73,6 | 51,2 |
| OOS | rompe minima primeiro -> fecha abaixo dela | 194 | 50,0 | [43,0;57,0] | 66,5 | 48,6 |
| OOS | sem ordem definida (mesma barra) / nenhuma rompeu | 0 |  | nenhuma=62 |  |  |

