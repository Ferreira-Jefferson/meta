# WIN gap — rodada 4: V2 r0 como estratégia (stop × alvo, classe, EA_SPEC)

Entrada fixa V2 r0 (1ª barra M5 contínua fecha contra o gap; limite no close dela; ttl 6 barras M5). IS 2026-04-06..2026-10-05, 120 pregões, simulador a tick da rodada 2, R$1.000, sizing de produção (2 contratos no modo B; 1 a 5 no modo A), fills `toque` e `atrav+1t`. Critério de escolha escrito antes da tabela: `CRITERIO.md`. A IS é a janela onde a pista nasceu: nenhum número desta rodada é fora da amostra.
Reprodução: `run4.py` → `analise4.py` → `holdout4.py` → `crosscheck4.py` → `tabela_escolha.py` → `gera_resultado.py`.

## 1. Mapa stop × alvo (110 células)

Linhas = stop em pontos; colunas = alvo (R = distância do stop; P50@1R = metade em 1R, resto até o fim; BE1R = stop vai para a entrada depois de +1R, sem alvo).

```
LIQUIDO B (R$, 2 contratos, fill toque)
        none  T500  T1000  T1500  T2000    1R   1.5R     2R     3R  P50@1R   BE1R
S300   4,808 2,034  1,770  1,492  2,004 1,570  1,434  1,786  1,532   3,189  1,226
S400   7,142 2,926  4,506  4,500  5,038 2,130  3,160  3,872  4,660   4,636  3,522
S500   9,478 3,092  5,474  5,776  6,714 3,092  3,478  5,474  5,776   6,285  2,886
S600   8,500 3,056  4,992  4,710  5,736 3,250  3,752  5,174  5,462   5,875  4,940
S700   9,572 2,698  5,156  5,916  6,880 4,372  5,114  6,352  7,524   6,972  7,230
S800   9,964 2,420  4,758  5,518  6,642 3,322  5,742  5,556  7,846   6,643  7,244
S900  10,174 3,346  5,772  6,732  8,014 4,332  7,430  7,420  8,578   7,253  7,412
S1000 11,108 3,910  6,416  7,576  9,218 6,416  7,576  9,218 10,356   8,762 11,088
S1200 10,928 4,398  7,530  7,608  9,118 7,712  8,668 10,110 12,858   9,320 12,386
S1500 12,222 5,484  8,846  8,686 10,274 8,686 10,346 11,612 11,934  10,454 12,410

R$ POR TRADE (B, toque)
       none  T500  T1000  T1500  T2000  1R  1.5R  2R  3R  P50@1R  BE1R
S300     78    33     29     24     32  25    23  29  25      51    20
S400    115    47     73     73     81  34    51  62  75      75    57
S500    153    50     88     93    108  50    56  88  93     101    47
S600    137    49     81     76     93  52    61  83  88      95    80
S700    154    44     83     95    111  71    82 102 121     112   117
S800    161    39     77     89    107  54    93  90 127     107   117
S900    164    54     93    109    129  70   120 120 138     117   120
S1000   179    63    103    122    149 103   122 149 167     141   179
S1200   176    71    121    123    147 124   140 163 207     150   200
S1500   197    88    143    140    166 140   167 187 192     169   200

LIQUIDO A (conta continua R$1.000, toque)
        none  T500  T1000  T1500  T2000    1R   1.5R     2R     3R  P50@1R   BE1R
S300   5,960 1,746  1,935    976  1,338 1,447  1,205  1,440  1,482   3,230    939
S400  10,352 3,359  4,182  5,488  5,520 2,198  3,800  4,546  6,037   5,484  4,253
S500  12,872 2,883  6,128  5,142  6,770 2,883  2,906  6,128  5,142   6,464  1,154
S600   9,264 3,366  5,988  2,691  4,458 2,995  3,313  4,840  4,541   5,458  3,700
S700  13,120 2,205  4,746  6,944  9,815 4,748  4,668  8,958 10,839   9,139  9,624
S800  13,145 2,072  4,492  5,236  7,895 2,504  4,912  5,824 10,402   6,153  8,816
S900  14,476 2,737  5,914  7,688 10,029 3,175 10,507  9,209 10,505   7,173  8,868
S1000 16,951 4,398  6,779  9,358 12,698 6,779  9,358 12,698 13,812   8,346 17,306
S1200 15,104 4,476  8,482 10,970 13,614 9,528 12,944 15,315 21,288   6,363 20,143
S1500 18,456 6,692 12,251   -926 12,805  -926 12,264 16,056 18,232  -1,070 18,728

p do nulo de direcao aleatoria por celula (B, toque) 
       none  T500  T1000  T1500  T2000    1R  1.5R    2R    3R  P50@1R  BE1R
S300  0.010 0.030  0.025  0.035  0.056 0.040 0.044 0.046 0.030   0.006 0.065
S400  0.003 0.026  0.008  0.007  0.020 0.040 0.028 0.017 0.007   0.003 0.028
S500  0.001 0.023  0.009  0.004  0.011 0.023 0.036 0.009 0.004   0.001 0.025
S600  0.006 0.025  0.019  0.017  0.044 0.040 0.040 0.019 0.029   0.007 0.034
S700  0.003 0.024  0.010  0.006  0.017 0.022 0.010 0.010 0.015   0.003 0.010
S800  0.004 0.036  0.030  0.013  0.029 0.081 0.018 0.018 0.006   0.011 0.019
S900  0.004 0.019  0.028  0.011  0.022 0.051 0.014 0.017 0.007   0.010 0.018
S1000 0.002 0.009  0.015  0.005  0.011 0.015 0.005 0.011 0.003   0.003 0.002
S1200 0.002 0.006  0.007  0.009  0.010 0.013 0.010 0.002 0.001   0.004 0.002
S1500 0.004 0.003  0.005  0.016  0.016 0.016 0.010 0.005 0.004   0.007 0.004

 p AJUSTADO pelo maximo da grade de 110 celulas (t, B, toque) 
       none  T500  T1000  T1500  T2000    1R  1.5R    2R    3R  P50@1R  BE1R
S300  0.113 0.204  0.179  0.227  0.328 0.242 0.266 0.274 0.206   0.074 0.368
S400  0.046 0.174  0.064  0.075  0.171 0.252 0.186 0.138 0.063   0.044 0.211
S500  0.021 0.158  0.073  0.045  0.107 0.158 0.228 0.073 0.045   0.022 0.203
S600  0.078 0.171  0.149  0.147  0.283 0.250 0.264 0.147 0.215   0.080 0.253
S700  0.035 0.156  0.093  0.061  0.147 0.157 0.084 0.090 0.131   0.041 0.107
S800  0.052 0.220  0.213  0.118  0.215 0.414 0.144 0.147 0.067   0.108 0.162
S900  0.056 0.140  0.205  0.102  0.175 0.314 0.127 0.146 0.075   0.101 0.151
S1000 0.033 0.065  0.134  0.057  0.104 0.134 0.057 0.104 0.046   0.045 0.043
S1200 0.035 0.057  0.074  0.087  0.106 0.118 0.106 0.033 0.023   0.048 0.030
S1500 0.050 0.037  0.055  0.143  0.138 0.143 0.097 0.066 0.052   0.075 0.047

LIQUIDO B abr-jun (56 pregoes) 
       none  T500  T1000  T1500  T2000    1R  1.5R    2R    3R  P50@1R  BE1R
S300  3,116 1,310  2,544  1,588  1,822   432 1,030 1,870 2,104   1,774 3,226
S400  4,148 1,554  3,630  2,748  3,210   914 2,194 2,992 3,466   2,531 3,774
S500  4,118 1,556  3,752  2,658  3,120 1,556 2,754 3,752 2,658   2,837 3,488
S600  3,518 1,196  3,312  2,058  2,520 1,876 2,712 2,936 2,212   2,697 3,216
S700  5,010 1,318  3,554  3,222  4,084 2,758 3,172 4,218 4,328   3,884 3,942
S800  4,490   998  3,154  2,702  3,564 2,516 3,500 3,102 3,466   3,503 3,534
S900  4,930 1,240  3,516  3,144  4,004 2,836 4,802 3,536 4,150   3,883 3,772
S1000 5,120 1,562  3,958  3,666  4,726 3,958 3,666 4,726 4,104   4,539 4,414
S1200 5,382 2,008  4,444  4,112  4,988 4,870 4,744 4,358 4,888   5,126 6,448
S1500 4,652 1,528  4,074  3,382  4,258 3,382 3,328 3,636 4,550   4,017 4,754

 LIQUIDO B jul-out (64 pregoes) 
       none  T500  T1000  T1500  T2000    1R  1.5R    2R    3R  P50@1R   BE1R
S300  1,692   724   -774    -96    182 1,138   404   -84  -572   1,415 -2,000
S400  2,994 1,372    876  1,752  1,828 1,216   966   880 1,194   2,105   -252
S500  5,360 1,536  1,722  3,118  3,594 1,536   724 1,722 3,118   3,448   -602
S600  4,982 1,860  1,680  2,652  3,216 1,374 1,040 2,238 3,250   3,178  1,724
S700  4,562 1,380  1,602  2,694  2,796 1,614 1,942 2,134 3,196   3,088  3,288
S800  5,474 1,422  1,604  2,816  3,078   806 2,242 2,454 4,380   3,140  3,710
S900  5,244 2,106  2,256  3,588  4,010 1,496 2,628 3,884 4,428   3,370  3,640
S1000 5,988 2,348  2,458  3,910  4,492 2,458 3,910 4,492 6,252   4,223  6,674
S1200 5,546 2,390  3,086  3,496  4,130 2,842 3,924 5,752 7,970   4,194  5,938
S1500 7,570 3,956  4,772  5,304  6,016 5,304 7,018 7,976 7,384   6,437  7,656
```

- Líquido B (toque) varia de R$1.226 (S300|BE1R) a R$12.858 (S1200|3R); **110 de 110 células com líquido B > 0**, nos dois fills (`atrav+1t` idêntico: a ordem no close enche com ≥ 1 tick de folga).
- Por stop, a coluna "sem alvo" é a maior ou praticamente empatada com a maior em 8 dos 10 stops; os alvos fixos (500 a 2000 pts) rendem menos em todo stop (ex.: S700: sem alvo R$9.572; T2000 R$6.880; T500 R$2.698). Exceções: S1200 com 3R (R$12.858 contra R$10.928) e S1500 com BE1R (R$12.410 contra R$12.222), e S1000 com BE1R (R$11.088, empate com R$11.108).
- R$/trade da coluna "sem alvo": R$78 (S300), R$154 (S700), R$176 (S1200), R$197 (S1500).
- Sobe com o stop: a coluna "sem alvo" vai de R$4.808 (S300) a R$12.222 (S1500), com salto até S500 (R$9.478) e depois subida lenta (R$8.500 a R$12.222 de S600 a S1500).

## 2. Censura do modo A (conta contínua R$1.000)

```
CENSURA MODO A (R$1.000; 'C' = censurada em toque ou atrav+1t: ordens recusadas ou caixa minimo < R$100) 
      none T500 T1000 T1500 T2000 1R 1.5R 2R 3R P50@1R BE1R
S300     .    .     .     .     .  .    .  .  .      .    .
S400     .    .     .     .     .  .    .  .  .      .    .
S500     .    .     .     .     .  .    .  .  .      .    .
S600     .    .     .     .     .  .    .  .  .      .    .
S700     .    .     .     .     .  .    .  .  .      .    .
S800     .    .     .     .     .  .    .  .  .      .    .
S900     .    .     .     .     .  .    .  .  .      .    .
S1000    .    .     .     .     .  .    .  .  .      .    .
S1200    .    .     .     .     .  .    .  .  .      .    .
S1500    .    C     C     C     .  C    C  .  .      C    .
celulas censuradas: 6/110

ordens recusadas por capital (A, toque)
       none  T500  T1000  T1500  T2000  1R  1.5R  2R  3R  P50@1R  BE1R
S300      0     0      0      0      0   0     0   0   0       0     0
S400      0     0      0      0      0   0     0   0   0       0     0
S500      0     0      0      0      0   0     0   0   0       0     0
S600      0     0      0      0      0   0     0   0   0       0     0
S700      0     0      0      0      0   0     0   0   0       0     0
S800      0     0      0      0      0   0     0   0   0       0     0
S900      0     0      0      0      0   0     0   0   0       0     0
S1000     0     0      0      0      0   0     0   0   0       0     0
S1200     0     0      0      0      0   0     0   0   0       0     0
S1500     0     0      0     31      0  31     0   0   0      34     0

caixa minimo A (toque, MtM aprox.)
       none  T500  T1000  T1500  T2000  1R  1.5R  2R  3R  P50@1R  BE1R
S300    692   632    692    692    692 651   612 672 692     692   692
S400    692   611    596    692    692 556   651 632 692     692   692
S500    692   458    550    550    666 458   424 550 550     458   692
S600    644   318    468    206    468 358   412 470 450     358   644
S700    666   519    408    666    666 536   458 666 666     606   666
S800    620   220    346    620    620 426   388 620 620     507   620
S900    586   180    416    586    586 356   586 586 586     505   586
S1000   546   320    308    546    546 308   546 546 546     308   546
S1200   466   238    154    460    466 277   466 466 466     254   466
S1500   194    58     76      4    194   4    48 194 194     -96   194
```

6 de 110 células censuradas, todas com stop 1500 e alvo (500, 1000, 1500, 1R, 1,5R, P50@1R): 3 por ordens recusadas por capital (31 em T1500, 31 em 1R, 34 em P50@1R; caixa mínimo R$4, R$4 e −R$96) e 3 só por caixa mínimo abaixo da margem de R$100 (T500 R$58, T1000 R$76, 1,5R R$48). Nenhuma célula com stop ≤ 1200 é censurada; a coluna "sem alvo" nunca é.

## 3. Platô (vizinhos = stops a ±1 e ±2 posições, mesmo alvo)

```
PLATO por alvo (vizinhos = stops a +-1 e +-2; 'acima do nulo' = p da celula <= 0,05; positivo = liquido B > 0) 
  alvo stops_positivos stops_pos_e_acima_nulo viz700_positivos viz700_acima_nulo  liq700  mediana_viz700  razao_700_sobre_mediana  pico700
  none           10/10                  10/10              4/4               4/4    9572            9721                     0.98    False
  T500           10/10                  10/10              4/4               4/4    2698            3074                     0.88    False
 T1000           10/10                  10/10              4/4               4/4    5156            5233                     0.99    False
 T1500           10/10                  10/10              4/4               4/4    5916            5647                     1.05    False
 T2000           10/10                   9/10              4/4               4/4    6880            6678                     1.03    False
    1R           10/10                   8/10              4/4               2/4    4372            3286                     1.33    False
  1.5R           10/10                  10/10              4/4               4/4    5114            4747                     1.08    False
    2R           10/10                  10/10              4/4               4/4    6352            5515                     1.15    False
    3R           10/10                  10/10              4/4               4/4    7524            6811                     1.10    False
P50@1R           10/10                  10/10              4/4               4/4    6972            6464                     1.08    False
  BE1R           10/10                   9/10              4/4               4/4    7230            6092                     1.19    False
```

- **700 está num platô, não num pico.** Na coluna "sem alvo": 10 de 10 stops com líquido B > 0 e p do nulo de direção ≤ 0,05; os 4 vizinhos de 700 (500, 600, 800, 900) são positivos e acima do nulo; líquido de 700 = R$9.572 contra mediana dos vizinhos R$9.721 (razão 0,98). Nenhum dos 11 alvos tem 700 como pico (razão de 0,88 a 1,33; 1R é o mais alto, 1,33, ainda abaixo do limite de 1,5).
- Forma da curva "sem alvo" em R$: S300 4.808 · S400 7.142 · S500 9.478 · S600 8.500 · S700 9.572 · S800 9.964 · S900 10.174 · S1000 11.108 · S1200 10.928 · S1500 12.222. Cai abaixo de 500; de 500 a 1500 é uma faixa de R$8.500 a R$12.200 com inclinação positiva suave (não é um topo em 700).
- O líquido B cresce com o stop porque o stop largo chega perto de "segurar até o fim"; o risco por trade cresce junto: stop de 700 = R$140 por contrato (R$280 com 2 contratos), 1200 = R$240 (R$480), 1500 = R$300 (R$600). MaxDD B: S700 R$1.785, S1200 R$2.535; MaxDD A: S700 R$2.678 (16,9%), S1200 R$6.771 (29,6%); lucro/DD B 5,36 contra 4,31.

## 4. Seleção na grade (nulo de máximo) e metades

```
SELECAO NA GRADE  melhor t: S500 | none t=2.91 p celula=0.0011 p ajustado=0.0210; celulas com p<0,05: 106/110; p ajustado<0,05: 19
escolhida: t=2.74 p celula=0.0020 p ajustado=0.0346; abr-jun 5,382 | jul-out 5,546
metades: correlacao de postos entre as 110 celulas = 0.68; positivas nas duas: 103/110; so' numa: 7; nenhuma: 0
top 10 abr-jun: ['S1200 | BE1R', 'S1200 | none', 'S1200 | P50@1R', 'S1000 | none', 'S700 | none', 'S1200 | T2000', 'S900 | none', 'S1200 | 3R', 'S1200 | 1R', 'S900 | 1.5R']
top 10 jul-out: ['S1500 | 2R', 'S1200 | 3R', 'S1500 | BE1R', 'S1500 | none', 'S1500 | 3R', 'S1500 | 1.5R', 'S1000 | BE1R', 'S1500 | P50@1R', 'S1000 | 3R', 'S1500 | T2000']
```

p ajustado pelo máximo de 110 células (mesmo sorteio de direção para todas as células, estatística t = excesso sobre o nulo da própria célula): 19 de 110 células com p ajustado < 0,05; melhor t em S500|sem alvo (p ajustado 0,021); S700|sem alvo 0,035; célula escolhida 0,035. Metades abr–jun (56 pregões) × jul–out (64): 103 de 110 células positivas nas duas; correlação de postos 0,68; o top 10 de abr–jun é dominado por S1000-S1200 e sem alvo/BE1R, o de jul–out por S1500 (stops largos cada vez melhor).

## 5. Escolha (CRITERIO.md)

```
ESCOLHA (CRITERIO.md) 
candidatas com >= 3 vizinhos: 88; elegiveis: 72
           id  ok_censura  ok_positivo  ok_p  ok_nao_pico    score   minimo      liq  elegivel
 S1200 | none        True         True  True         True 11,108.0 10,174.0 10,928.0      True
 S1200 | BE1R        True         True  True         True 11,088.0  7,412.0 12,386.0      True
 S1000 | none        True         True  True         True 10,551.0  9,964.0 11,108.0      True
  S900 | none        True         True  True         True 10,446.0  9,572.0 10,174.0      True
   S1200 | 3R        True         True  True         True 10,356.0  8,578.0 12,858.0      True
   S1000 | 3R        True         True  True         True 10,256.0  7,846.0 10,356.0      True
 S1000 | BE1R        True         True  True         True  9,899.0  7,244.0 11,088.0      True
  S800 | none        True         True  True         True  9,873.0  8,500.0  9,964.0      True
  S700 | none        True         True  True         True  9,721.0  8,500.0  9,572.0      True
  S600 | none        True         True  True         True  9,525.0  7,142.0  8,500.0      True
S1200 | T2000        True         True  True         True  9,218.0  8,014.0  9,118.0      True
   S1200 | 2R        True         True  True         True  9,218.0  7,420.0 10,110.0      True

reprovacoes por criterio (candidatas): {'ok_censura': 12, 'ok_positivo': 2, 'ok_p': 2, 'ok_nao_pico': 0}

CELULA ESCOLHIDA: S1200 | none | pontuacao (mediana dos vizinhos) R$ 11108 | liquido da celula R$ 10928 | minimo celula+vizinhos R$ 10174
```

**Célula escolhida: stop 1200 pts, sem alvo (segura até o fim do contínuo).** Pontuação (mediana do líquido B dos 3 vizinhos 900, 1000 e 1500; o stop 1200 só tem 3 dentro de ±2 posições) R$11.108; líquido B da célula R$10.928 (razão 0,98 sobre os vizinhos: não é pico); mínimo célula+vizinhos R$10.174; p da célula 0,002, ajustado 0,035; abr–jun R$5.382, jul–out R$5.546; modo A não censurado nos dois fills (caixa mínimo R$466), 100% dos vizinhos não censurados. O melhor platô é "sem alvo" (os 3 primeiros colocados da lista elegível: S1200|sem alvo, S1200|BE1R e S1000|sem alvo).

Duas observações sobre a escolha, fora do critério:
- A pontuação do critério (líquido) cresce com o stop; por lucro/DD, S700|sem alvo é melhor (B 5,36 contra 4,31; A 4,90 contra 2,23) e tem p ajustado igual (0,035). S700|sem alvo também é elegível (nona da lista) e é mudar um parâmetro da classe (`stop_pts=700`).
- Com 2 contratos a R$1.000, S1200 arrisca R$480 por stop (48% do capital inicial); o modo A escalona os contratos com o caixa (média 3,6; faixa 1–5).

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes        fill        modo         ctr     BE emp%   sem fill%  atraso min    seq perdsaidas s/a/tr/te/f      p nulo       p adj   sem trade
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
S1200 | none                          —    10.928,00        —    2.535,00     4,31  50,0%     62      91,07     0,5              —     120       toque    B pregao           2        34,8         1,6         0,0           6 24/0/0/0/38       0,002       0,035      58/120  fila NAO CALIBRADA (WIN); fill toque
S1200 | none                   1.510,3%    15.103,50    29,6%    6.770,50     2,23  50,0%     62     125,86     0,5      16.103,50     120       toque     A conta   3.6 [1-5]        38,1         1,6         0,0           6 24/0/0/0/38           —           —      58/120  fila NAO CALIBRADA (WIN)
S1200 | none                          —    10.928,00        —    2.535,00     4,31  50,0%     62      91,07     0,5              —     120    atrav+1t    B pregao           2        34,8         1,6         0,0           6 24/0/0/0/38       0,002       0,035      58/120  fila NAO CALIBRADA (WIN); fill atrav+1t
S1200 | none                   1.510,3%    15.103,50    29,6%    6.770,50     2,23  50,0%     62     125,86     0,5      16.103,50     120    atrav+1t     A conta   3.6 [1-5]        38,1         1,6         0,0           6 24/0/0/0/38           —           —      58/120  fila NAO CALIBRADA (WIN)
S700 | none                           —     9.572,00        —    1.785,00     5,36  40,3%     62      79,77     0,5              —     120       toque    B pregao           2        25,6         1,6         0,0           7 34/0/0/0/28       0,003       0,035      58/120  fila NAO CALIBRADA (WIN); fill toque
S700 | none                    1.312,0%    13.120,00    16,9%    2.677,50     4,90  40,3%     62     109,33     0,5      14.120,00     120       toque     A conta   3.3 [1-4]        27,4         1,6         0,0           7 34/0/0/0/28           —           —      58/120  fila NAO CALIBRADA (WIN)
S700 | none                           —     9.572,00        —    1.785,00     5,36  40,3%     62      79,77     0,5              —     120    atrav+1t    B pregao           2        25,6         1,6         0,0           7 34/0/0/0/28       0,003       0,035      58/120  fila NAO CALIBRADA (WIN); fill atrav+1t
S700 | none                    1.312,0%    13.120,00    16,9%    2.677,50     4,90  40,3%     62     109,33     0,5      14.120,00     120    atrav+1t     A conta   3.3 [1-4]        27,4         1,6         0,0           7 34/0/0/0/28           —           —      58/120  fila NAO CALIBRADA (WIN)
csv 126
```

## 6. Holdout 2025-12-19..2026-02-19 — DESCRITIVO, JÁ GASTO (rodada 3)

Mesma grade, regra M1 conservadora, 38 pregões, 19 trades por célula. Não é validação e não entrou na escolha.

```
HOLDOUT 2025-12-19..2026-02-19 (JA GASTO na rodada 3; descritivo; M1 conservador; 38 pregoes, entrada V2 r0, 2 contratos)

 LIQUIDO B (R$) 
       none  T500  T1000  T1500  T2000    1R  1.5R    2R    3R  P50@1R  BE1R
S300  3,181   239    273  1,273  2,015  -159    79   197    73   1,511 2,221
S400  2,843   161    275    935  1,677  -199   119   277   335   1,322 3,269
S500  2,733  -239    165    825  1,567  -239   159   165   825   1,247 2,869
S600  3,601   245  1,611  1,575  2,517   203 1,403 1,911 2,295   1,902 2,711
S700  3,201   889  2,615  2,057  3,199 1,367 2,835 1,777 2,167   2,284 2,915
S800  3,441 1,171  2,607  1,969  3,111 2,209 3,067 2,249 2,767   2,825 3,165
S900  3,121   971  2,367  1,649  2,791 2,489 1,229 2,489 2,445   2,805 3,643
S1000 2,801   771  2,127  1,329  2,471 2,127 1,329 2,471 2,365   2,464 3,353
S1200 3,327 1,053  2,529  1,771  3,113 3,069 2,731 2,653 3,371   3,198 4,099
S1500 3,007   573  2,449  1,451  2,793 1,451 2,153 2,571 3,771   2,229 2,961

 R$ POR TRADE 
       none  T500  T1000  T1500  T2000  1R  1.5R  2R  3R  P50@1R  BE1R
S300    167    13     14     67    106  -8     4  10   4      80   117
S400    150     8     14     49     88 -10     6  15  18      70   172
S500    144   -13      9     43     82 -13     8   9  43      66   151
S600    190    13     85     83    132  11    74 101 121     100   143
S700    168    47    138    108    168  72   149  94 114     120   153
S800    181    62    137    104    164 116   161 118 146     149   167
S900    164    51    125     87    147 131    65 131 129     148   192
S1000   147    41    112     70    130 112    70 130 124     130   176
S1200   175    55    133     93    164 162   144 140 177     168   216
S1500   158    30    129     76    147  76   113 135 198     117   156

 trades 
       none  T500  T1000  T1500  T2000  1R  1.5R  2R  3R  P50@1R  BE1R
S300     19    19     19     19     19  19    19  19  19      19    19
S400     19    19     19     19     19  19    19  19  19      19    19
S500     19    19     19     19     19  19    19  19  19      19    19
S600     19    19     19     19     19  19    19  19  19      19    19
S700     19    19     19     19     19  19    19  19  19      19    19
S800     19    19     19     19     19  19    19  19  19      19    19
S900     19    19     19     19     19  19    19  19  19      19    19
S1000    19    19     19     19     19  19    19  19  19      19    19
S1200    19    19     19     19     19  19    19  19  19      19    19
S1500    19    19     19     19     19  19    19  19  19      19    19

 por alvo: stops positivos / 10 e vizinhos de 700 (500,600,800,900) positivos / 4 
none     positivos 10/10 | viz700 4/4 | liquido S700 3,201 | mediana viz 3,281
T500     positivos 9/10 | viz700 3/4 | liquido S700 889 | mediana viz 608
T1000    positivos 10/10 | viz700 4/4 | liquido S700 2,615 | mediana viz 1,989
T1500    positivos 10/10 | viz700 4/4 | liquido S700 2,057 | mediana viz 1,612
T2000    positivos 10/10 | viz700 4/4 | liquido S700 3,199 | mediana viz 2,654
1R       positivos 7/10 | viz700 3/4 | liquido S700 1,367 | mediana viz 1,206
1.5R     positivos 10/10 | viz700 4/4 | liquido S700 2,835 | mediana viz 1,316
2R       positivos 10/10 | viz700 4/4 | liquido S700 1,777 | mediana viz 2,080
3R       positivos 10/10 | viz700 4/4 | liquido S700 2,167 | mediana viz 2,370
P50@1R   positivos 10/10 | viz700 4/4 | liquido S700 2,284 | mediana viz 2,354
BE1R     positivos 10/10 | viz700 4/4 | liquido S700 2,915 | mediana viz 3,017
```

- A forma não se repete: no holdout a coluna "sem alvo" é plana, R$2.733 a R$3.601 para os 10 stops (S300 R$3.181; S700 R$3.201; S1200 R$3.327; S1500 R$3.007), sem a subida com o stop da IS; as colunas "sem alvo", T1000, T1500, T2000, 1,5R, 2R, 3R, P50@1R e BE1R têm 10 de 10 stops positivos; as colunas T500 (9/10) e 1R (7/10) têm negativos (S500|T500 −R$239; S300, S400 e S500|1R −R$159, −R$199 e −R$239).
- O melhor alvo no holdout é BE1R (R$4.099 em S1200; R$2.915 em S700), a coluna "sem alvo" fica no meio (S1200 R$3.327).
- Com 19 trades por célula o holdout não tem poder para distinguir células vizinhas (rodada 3: efeito mínimo detectável R$337 por trade).

## 7. Classe, testes e cruzamento com o motor

- Classe: `src/strategy/daytrade/lab/win_gap_barra1.py::WinGapBarra1` (`name = "win_gap_barra1"`), defaults `stop_pts=1200`, sem alvo, `recuo_pts=0`, `ttl_barras=6`. Pura (OHLCV): o gap vem de barras (open da 1ª barra do dia = leilão; close da última barra do dia anterior = call). Não está em `registry.py` (teste `test_nao_esta_no_registry`).
- Testes `tests/test_win_gap_barra1.py`: 17 passando (sinal do gap, só opera com a barra 1 contra o gap, ordem a limite com prazo e alvo fatiado, sem look-ahead, dia sem call anterior / abertura atrasada, vencimento e filtro de rolagem, flatten às 18:10 (17:40 no regime antigo) e nunca na barra do call, fuso do feed, breakeven, call lido de `initialize`).
- **Suíte inteira** (`.\.venv\Scripts\python.exe -m pytest`, paralelo): **2.404 passaram, 1 pulado, 0 falhas** (64,6 s). O pulado é `test_live_broker_mt5.py` (pacote MetaTrader5 real instalado nesta máquina).

Cruzamento (`crosscheck4.py`, motor real, M5, R$1.000, `config_for`, `session_end_time=18:20`, celula S1200|sem alvo):

```
celula: V2 r0, stop 1200, sem alvo; config_for R$1.000: max_open_contracts=5, session_end_time=18:20:00
dias excluidos (sem operar na classe): ['2026-04-15', '2026-05-06', '2026-06-17', '2026-07-31', '2026-08-10', '2026-08-12', '2026-09-24']

simulador a tick, modo A: 62 trades, liquido R$15,103.50
simulador em modo barra (semantica do motor), modo A: 63 trades, liquido R$17,446.50

(A) motor + classe, M5 BRUTO (gap das barras, flatten 18:15): 63 trades, liquido R$17,783.50; sinais da classe 63
gap calculado das barras brutas == gap do CSV de fases em 120/120 dias; diferentes: []
dias com trade: motor 63, simulador 62; so' no motor ['2026-09-11']; so' no simulador []
trades em comum: 62; mesmo lado 62; mesma entrada 62; mesma quantidade 59
P&L por contrato (motor - simulador a tick): mediana 0.0, media -1.1, min -49.0, max 60.0
motivos de saida motor: {'signal': 39, 'stop': 24} | simulador: {'flatten': 38, 'stop': 24}
trades com stop na barra do fill no simulador a tick (o motor nao ve): 1

(B) motor + classe, M5 sem leilao + gap externo, flatten do motor: 63 trades, liquido R$17,446.50
(B) x simulador em modo barra: IGUAIS = True (63 x 63 trades)
```

- **(B)** classe no motor, barras sem leilão + gap externo (o do CSV) + flatten do motor: **63 trades, +R$17.446,50, idêntico trade a trade** (lado, contratos, entrada, saída, motivo, P&L) ao simulador em modo barra (a semântica do motor). A classe reproduz o simulador.
- **(A)** classe no motor, barras M5 BRUTAS (com leilão e call; gap calculado pela classe, igual ao gap do CSV de fases em 120/120 dias): 63 trades, +R$17.783,50, contra o simulador a tick 62 trades, +R$15.103,50 (modo A). Diferenças, explicadas:
  1. **Barra do fill:** o motor só avalia o stop da barra seguinte à do fill; o tick vê o stop dentro da barra do fill em 1 trade (2026-09-10: −R$272,50 no motor, −R$241,50 por contrato no tick).
  2. **Fonte da barra × tick:** em 2026-09-11 a máxima M5 (vinda de M1) toca o limite de venda (190.610) e o motor enche (+R$1.852,50, 5 contratos); nos ticks esse preço não é negociado depois das 09:05, sem fill. É a diferença de 5 pts entre as duas fontes (rodada 2, CHECAGEM_DADOS). Esse trade é ~R$1,85 mil dos R$2,68 mil de diferença.
  3. **Fim do dia:** a classe zera às 18:15 (abertura da barra das 18:15) para a saída não cair na barra do call; o simulador zera no último tick (18:24:59). Nos 62 trades comuns, soma da diferença por contrato −R$67.
  4. **Caixa:** os contratos seguem o caixa e o caixa diverge depois dos itens acima: 59 de 62 trades com a mesma quantidade.
  5. **Sinal:** o open da barra 1 em feed bruto é o preço do leilão; o simulador usa o 1º negócio contínuo. Muda o sinal em 1 dia de 120 (2026-05-20, que a classe opera e o simulador não).
- Descoberta de integração: o motor **não entrega a última barra do dia a `on_bar`** (o flatten roda antes e `on_bar` não roda depois dele), então o call de D−1 não chega pelo caminho normal; a classe lê o call do DataFrame em `initialize` (só datas anteriores a hoje) e cai no close da última barra vista quando não há tabela (ao vivo). Sem isso, no 1º cruzamento 4 dias saíram só no motor e 5 só no simulador (gaps pequenos).

## 8. EA

`EA_SPEC.md` (mesma pasta) e `EA_referencia_trades.csv` (trades esperados por pregão, 1 contrato, S1200 e S700, simulador a tick).
