# Encaixe de médias entre tempos gráficos (EMA 9/21/50) no WIN — setup do dono

Janelas: descoberta jan–jun/2026, confirmação jul–ago/2026, set/2026 como terceira. Só 2026; nov–dez/2025 só aqueceu as médias. Todo número é pts/contrato; R$0,20/pt; custo 2 pts; stop a mercado +5 pts; limite conservadora (só enche se negociar 5 pts além); mesma vela: stop vence. Código e saídas: `scripts/daytrade/win_pernadas_exploracao/rodada7/medias_multitf/`.

## 1. Resposta curta

- O encaixe das médias (M5/M10 rompe, TF maior alinhado só tocando EMA9/21) **não mudou de forma sustentada a probabilidade de acerto** de uma entrada a favor. Na descoberta jan–jun achei uma região (pares M10×M30 e M5×M30, stop técnico de 5/15 velas, alinhamento estrito) com +34 a +60 pts/op em 9 regras, que passou no critério de platô e ficou 2,0–3,2 desvios acima do nulo embaralhado. **Na confirmação jul–ago as mesmas 9 regras juntas deram −20,7 pts/op (n=400) e em set −41,9 (n=263).** Só 1 de 9 (R7, M15×H1) ficou positivo nas duas janelas novas (+56 e +45 pts, IC cruza 0; na descoberta era ≈0).
- A definição literal do dono (M5 rompe as 3 médias, M15 alinhado, toque ≤0,5 ATR, stop das últimas 15 velas, alvo 5×): −17 pts/op na descoberta (n=156), −6 em jul–ago (n=55), +17 em set (n=25); todos os ICs cruzam zero. Acerto 16% contra breakeven empírico 18,5%.
- **Os períodos não importam** (achado): numa grade 3×3×3 em torno de 9/21/50 as regras mantêm o mesmo sinal em ~27/27 células na descoberta, e o resultado quase não depende do número (9/21/50 ≈ 5/17/34 ≈ 13/24/120). Só quebra com média 40 (colada à lenta 50). SMA no lugar de EMA inverte o sinal em 3 das 5 regras M10×M30 (R2, R4, R8) e reduz à metade o ganho nas outras 2 (R1, R3). Vale o par de tempos e o stop, não o número da média — e na confirmação nem isso sustentou.
- Contra a ruína do jogador e contra entradas aleatórias no mesmo horário, o encaixado fica dentro do ruído: acerto 16% × 20,5% do aleatório; esperança −17,4 × −22,1 (descoberta, referência).
- Ticks (mar–set, mesmos sinais): **idênticos ao M1** (19.114 trades, 10 diferem). O desenho exige stop ≥ 50 pts e alvo ≥ 150 pts, então a ordem dentro da vela quase nunca decide. O custo é descartar ~1/3 dos sinais (stop técnico fora de 50–500 pts).

## 2. Definições congeladas (antes de abrir jul–ago)

- EMA 9/21/50 do fechamento (pandas `ewm(span, adjust=False)`) em M5, M10, M15, M30, H1 e diário (diário só no par H1×D). Barras de TF maior agrupadas a partir de 09:00; "fechada" = última barra completa; "formando" = EMA recalculada com o preço do minuto (sem look-ahead). Testei as duas.
- Tendência do TF maior: **estrita** EMA9>EMA21>EMA50 e EMA21 subindo; **frouxa** só EMA21 subindo. Sempre exigido: preço do TF maior ≥ EMA50 dele (senão é "TF maior rompendo").
- Toque: mínima das 2 últimas barras do TF maior ≤ EMA(ref) + x·ATR14(TF maior), x ∈ {0; 0,1; 0,25; 0,5; 1}, ref = EMA9 ou EMA21.
- Gatilho (aresta): 1ª barra fechada do TF menor que fecha abaixo só da EMA9 (f), EMA9 e 21 (fm) ou das três (fms). Sinal entre 09:30 e 17:00. Venda = espelho.
- Entrada: limite no fechamento da vela-gatilho, prazo 10 min (5/15 testados: sem efeito, o preço cobre 5 pts abaixo no 1º minuto), conservadora. Entrada na EMA9/21 do TF maior também testada (coluna entrada).
- Stop: mínima das últimas N velas M1 −5 (N=5,10,15,30), ou 1 tick abaixo da EMA50 do TF maior, ou k·ATR14 do M15; só vale se 50 ≤ S ≤ 500 pts. Alvo: K × S, K ∈ {3; 5; 7,5; 10}, ou máxima das últimas 12 barras do TF maior (se ≥ 3×S). Um trade por vez (ordem pendente bloqueia); long e short simulados separadamente.
- Nulos: M1 de cada pregão embaralhado em blocos de 30 min e reencadeado; **40 sorteios** nas grades 1 e 2, 30 na grade de períodos, 60 nas regras congeladas (todas as janelas). IC95% por bootstrap de dias.

## 3. Contagem de testes e quantos passariam por acaso

| grade | células | passaram × passariam por acaso |
|---|---|---|
| Grade 1: eixos de 1 em 1 (períodos, SMA, toque, ruptura, tendência, variante, par, prazo, N, K, stop, entrada), mapa rápida×média (lenta 50) e grade conjunta f×m×s | 931 células (836 com n≥30) | t≥2: 0 reais · 1,5 no nulo (máx 17); t≥1,5: 5 reais · 15,8 no nulo |
| Grade 2: par(5) × ruptura(3) × toque x(4) × tendência(2) × variante(2) × stop(4) × K(3), períodos 9/21/50 | 2.880 células (1.677 com n≥60) | t≥2: 6 reais · 6,2 no nulo (máx 34); t≥1,5: 31 reais · 46,8 no nulo; fração com esperança>0: 50,3% real · 43,3% nulo |
| Famílias de 12 células (x×K) com ≥10/12 positivas, média ponderada>0, n≥30 | 240 famílias | 51 passam · 51,3 no nulo (min 22, máx 89): o critério de platô sozinho não discrimina. Com p≤0,05 contra o nulo da mesma família: 22 reais · ~12 esperadas por acaso |
| Sensibilidade a períodos das 10 regras congeladas (56 células cada) em 3 janelas | 560 × 3 | seção 7 |

Total de células avaliadas na descoberta: ~4.400. Nada com t≥2 além do que o nulo gera. O **nulo embaralhado não é zero**: com stop por ATR ou alvo grande ele dá esperança positiva (atr1,0: +91 pts; referência: +8,7), porque o WIN de 2026 tem tendência e volatilidade agrupada. Por isso toda célula é comparada com a MESMA célula no nulo (coluna z).

## 4. Comparações obrigatórias (mesma geometria: entrada no fechamento, stop 15 velas, alvo 5×)

Esperança em pts/op [IC95% bootstrap de dias]. 'reversão' = comprar contra o rompimento do TF menor (a favor de um TF maior de alta); 'continuação' = seguir o rompimento. Aleatório = mesmo horário (±15 min), mesmo lado, mesmo número de sinais, 20 repetições.

**R10: definição literal do dono (M5×M15, três médias, estrito)**

| janela | grupo | n | op/dia | acerto | BE emp. | esp pts | IC95% | ganho/perda | seq perdas máx |
|---|---|---|---|---|---|---|---|---|---|
| desc | ENCAIXADO (a favor) -> a favor | 156 | 1,28 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 4,4 | 19 |
| desc | ENCAIXADO (a favor) -> contra | 122 | 1,00 | 32,0% | 32,4% | -4,6 | [-98 ; 96] | 2,1 | 11 |
| desc | rompe, TF maior neutro -> reversao | 280 | 2,30 | 17,9% | 19,6% | -13,5 | [-53 ; 27] | 4,1 | 17 |
| desc | rompe, TF maior neutro -> continuacao | 225 | 1,84 | 27,1% | 27,0% | 0,9 | [-71 ; 90] | 2,7 | 12 |
| desc | rompe, TF maior alinhado oposto -> reversao | 373 | 3,06 | 19,0% | 19,6% | -4,3 | [-41 ; 36] | 4,1 | 23 |
| desc | rompe, TF maior alinhado oposto -> continuacao | 266 | 2,18 | 24,1% | 25,9% | -21,4 | [-93 ; 53] | 2,9 | 15 |
| desc | TF maior tambem rompendo -> reversao | 58 | 0,48 | 15,5% | 22,1% | -38,4 | [-104 ; 32] | 3,5 | 27 |
| desc | TF maior tambem rompendo -> continuacao | 56 | 0,46 | 23,2% | 26,8% | -49,4 | [-225 ; 134] | 2,7 | 16 |
| desc | ALEATORIO (mesmo horario, mesmo lado) | 186 | 1,52 | 20,1% | 22,6% | -22,1 | [-60 ; 17] | 3,4 | 25 |
| conf | ENCAIXADO (a favor) -> a favor | 55 | 1,25 | 21,8% | 22,7% | -5,6 | [-75 ; 78] | 3,4 | 14 |
| conf | ENCAIXADO (a favor) -> contra | 63 | 1,43 | 28,6% | 26,7% | 20,7 | [-117 ; 189] | 2,8 | 9 |
| conf | rompe, TF maior neutro -> reversao | 97 | 2,20 | 19,6% | 20,5% | -5,8 | [-49 ; 47] | 3,9 | 13 |
| conf | rompe, TF maior neutro -> continuacao | 78 | 1,77 | 24,4% | 31,8% | -63,9 | [-138 ; 25] | 2,1 | 8 |
| conf | rompe, TF maior alinhado oposto -> reversao | 126 | 2,86 | 12,7% | 25,9% | -72,5 | [-108 ; -28] | 2,9 | 30 |
| conf | rompe, TF maior alinhado oposto -> continuacao | 101 | 2,30 | 28,7% | 25,7% | 32,6 | [-79 ; 142] | 2,9 | 8 |
| conf | TF maior tambem rompendo -> reversao | 19 | 0,43 | 10,5% | 10,3% | 3,3 | [-133 ; 237] | 8,7 | 13 |
| conf | TF maior tambem rompendo -> continuacao | 22 | 0,50 | 27,3% | 40,9% | -87,5 | [-192 ; 33] | 1,4 | 5 |
| conf | ALEATORIO (mesmo horario, mesmo lado) | 74 | 1,68 | 23,6% | 22,0% | 14,6 | [-67 ; 77] | 3,5 | 21 |
| set | ENCAIXADO (a favor) -> a favor | 25 | 1,14 | 20,0% | 17,8% | 17,0 | [-87 ; 144] | 4,6 | 9 |
| set | ENCAIXADO (a favor) -> contra | 22 | 1,00 | 50,0% | 35,4% | 136,9 | [-71 ; 384] | 1,8 | 2 |
| set | rompe, TF maior neutro -> reversao | 57 | 2,59 | 22,8% | 15,4% | 66,8 | [-19 ; 170] | 5,5 | 13 |
| set | rompe, TF maior neutro -> continuacao | 41 | 1,86 | 29,3% | 30,7% | -12,7 | [-118 ; 117] | 2,3 | 8 |
| set | rompe, TF maior alinhado oposto -> reversao | 58 | 2,64 | 15,5% | 16,5% | -9,5 | [-106 ; 142] | 5,1 | 14 |
| set | rompe, TF maior alinhado oposto -> continuacao | 44 | 2,00 | 18,2% | 25,6% | -89,4 | [-218 ; 46] | 2,9 | 12 |
| set | TF maior tambem rompendo -> reversao | 13 | 0,59 | 38,5% | 15,5% | 165,7 | [-47 ; 499] | 5,4 | 5 |
| set | TF maior tambem rompendo -> continuacao | 11 | 0,50 | 9,1% | 50,3% | -243,4 | [-359 ; -94] | 1,0 | 5 |
| set | ALEATORIO (mesmo horario, mesmo lado) | 35 | 1,59 | 21,2% | 25,1% | -33,0 | [-144 ; 111] | 3,0 | 21 |

**R1: M10×M30, rompe EMA9 (melhor da descoberta)**

| janela | grupo | n | op/dia | acerto | BE emp. | esp pts | IC95% | ganho/perda | seq perdas máx |
|---|---|---|---|---|---|---|---|---|---|
| desc | ENCAIXADO (a favor) -> a favor | 117 | 0,96 | 28,2% | 20,8% | 55,8 | [-15 ; 145] | 3,8 | 10 |
| desc | ENCAIXADO (a favor) -> contra | 97 | 0,80 | 24,7% | 31,3% | -67,8 | [-170 ; 51] | 2,2 | 12 |
| desc | rompe, TF maior neutro -> reversao | 174 | 1,43 | 10,9% | 19,8% | -62,1 | [-101 ; -22] | 4,0 | 38 |
| desc | rompe, TF maior neutro -> continuacao | 127 | 1,04 | 29,9% | 29,4% | 5,0 | [-78 ; 97] | 2,4 | 9 |
| desc | rompe, TF maior alinhado oposto -> reversao | 196 | 1,61 | 16,3% | 19,3% | -22,5 | [-64 ; 28] | 4,2 | 25 |
| desc | rompe, TF maior alinhado oposto -> continuacao | 172 | 1,41 | 28,5% | 29,2% | -7,0 | [-86 ; 87] | 2,4 | 9 |
| desc | TF maior tambem rompendo -> reversao | 42 | 0,34 | 9,5% | 15,6% | -53,9 | [-132 ; 47] | 5,4 | 19 |
| desc | TF maior tambem rompendo -> continuacao | 41 | 0,34 | 34,1% | 27,4% | 72,5 | [-102 ; 263] | 2,6 | 5 |
| desc | ALEATORIO (mesmo horario, mesmo lado) | 144 | 1,18 | 20,6% | 22,7% | -18,8 | [-73 ; 40] | 3,4 | 34 |
| conf | ENCAIXADO (a favor) -> a favor | 44 | 1,00 | 9,1% | 13,8% | -43,9 | [-113 ; 42] | 6,3 | 17 |
| conf | ENCAIXADO (a favor) -> contra | 31 | 0,70 | 25,8% | 23,8% | 19,3 | [-144 ; 244] | 3,2 | 8 |
| conf | rompe, TF maior neutro -> reversao | 75 | 1,70 | 21,3% | 21,5% | -1,1 | [-57 ; 74] | 3,6 | 13 |
| conf | rompe, TF maior neutro -> continuacao | 70 | 1,59 | 28,6% | 28,0% | 5,4 | [-81 ; 94] | 2,6 | 8 |
| conf | rompe, TF maior alinhado oposto -> reversao | 68 | 1,55 | 20,6% | 20,7% | -0,6 | [-72 ; 85] | 3,8 | 13 |
| conf | rompe, TF maior alinhado oposto -> continuacao | 58 | 1,32 | 32,8% | 24,2% | 94,2 | [-59 ; 269] | 3,1 | 7 |
| conf | TF maior tambem rompendo -> reversao | 25 | 0,57 | 12,0% | 33,1% | -78,0 | [-134 ; 2] | 2,0 | 11 |
| conf | TF maior tambem rompendo -> continuacao | 28 | 0,64 | 32,1% | 31,0% | 9,8 | [-138 ; 248] | 2,2 | 5 |
| conf | ALEATORIO (mesmo horario, mesmo lado) | 44 | 1,00 | 23,2% | 22,7% | 5,0 | [-106 ; 123] | 3,4 | 20 |
| set | ENCAIXADO (a favor) -> a favor | 30 | 1,36 | 13,3% | 12,4% | 9,8 | [-118 ; 155] | 7,0 | 12 |
| set | ENCAIXADO (a favor) -> contra | 21 | 0,95 | 33,3% | 20,8% | 133,7 | [-129 ; 498] | 3,8 | 4 |
| set | rompe, TF maior neutro -> reversao | 43 | 1,95 | 11,6% | 15,2% | -37,2 | [-128 ; 76] | 5,6 | 15 |
| set | rompe, TF maior neutro -> continuacao | 32 | 1,45 | 31,2% | 24,6% | 76,6 | [-77 ; 280] | 3,1 | 8 |
| set | rompe, TF maior alinhado oposto -> reversao | 38 | 1,73 | 13,2% | 19,4% | -46,3 | [-126 ; 72] | 4,2 | 13 |
| set | rompe, TF maior alinhado oposto -> continuacao | 27 | 1,23 | 29,6% | 37,6% | -58,1 | [-179 ; 80] | 1,7 | 9 |
| set | TF maior tambem rompendo -> reversao | 8 | 0,36 | 12,5% | 5,9% | 112,4 | [-112 ; 628] | 16,0 | 6 |
| set | TF maior tambem rompendo -> continuacao | 7 | 0,32 | 57,1% | 22,3% | 488,0 | [-127 ; 1360] | 3,5 | 1 |
| set | ALEATORIO (mesmo horario, mesmo lado) | 32 | 1,45 | 20,1% | 21,5% | -13,0 | [-121 ; 128] | 3,7 | 26 |

Excursão (MFE/MAE em 30/60 min após o preenchimento) está em `cmp_out.txt` e `finalA.pkl`. No R10 da descoberta, MFE30 372 × MAE30 327 pts e MFE60 529 × MAE60 481: o preço vai para os dois lados na mesma proporção; o aleatório dá 316/326 e 441/454.

**Pergunta direta do dono: P(nova máxima do TF maior antes de uma barra do TF maior fechar abaixo da EMA50 dele).**

| regra | janela | n eventos | volta (máx. antes) | falha (fecha < EMA50) | nenhum até o fim do dia | ruína dos mesmos níveis | padronizado: sobe × cai (encaixado) | aleatório | oposto (contra) |
|---|---|---|---|---|---|---|---|---|---|
| R10 | desc | 262 | 21,4% | 45,4% | 33,2% | 44,3% | 32,8% × 37,8% | 27,5% × 41,6% | 27,1% × 40,8% |
| R10 | conf | 105 | 23,8% | 47,6% | 28,6% | 46,3% | 21,9% × 36,2% | 28,6% × 34,3% | 33,3% × 22,9% |
| R10 | set | 49 | 12,2% | 55,1% | 32,7% | 36,5% | 22,4% × 55,1% | 16,3% × 55,1% | 22,4% × 44,9% |
| R1 | desc | 198 | 28,3% | 29,8% | 41,9% | 52,4% | 29,8% × 23,7% | 22,2% × 28,8% | 23,2% × 30,3% |
| R1 | conf | 60 | 30,0% | 20,0% | 50,0% | 58,6% | 31,7% × 11,7% | 18,3% × 16,7% | 23,3% × 16,7% |
| R1 | set | 45 | 15,6% | 33,3% | 51,1% | 48,5% | 20,0% × 37,8% | 15,6% × 31,1% | 26,7% × 31,1% |
| R7 | desc | 158 | 11,4% | 41,8% | 46,8% | 49,6% | 23,4% × 25,3% | 24,7% × 17,7% | 29,7% × 20,9% |
| R7 | conf | 55 | 14,5% | 27,3% | 58,2% | 49,8% | 14,5% × 16,4% | 12,7% × 21,8% | 16,4% × 14,5% |
| R7 | set | 45 | 6,7% | 35,6% | 57,8% | 41,5% | 13,3% × 42,2% | 11,1% × 33,3% | 20,0% × 28,9% |

Leitura: no R10 literal da descoberta, 21% voltam à máxima, 45% fecham abaixo da EMA50 do M15 antes e 33% nenhum dos dois; descontados os 'nenhum', a chance de voltar é 32% contra 44% de ruína, ou seja, **pior que o acaso**. Na versão padronizada em ATR (mesma distância para todos os grupos) o encaixado fica +2 pp acima da ruína, o aleatório −4 pp, o rompimento sem TF maior −6/+1, o encaixado 'contra' −4: diferenças menores que o erro (n≈250). Na confirmação os sinais trocam de lado (R10 conf: encaixado −11 pp, contra +11 pp).

## 5. Curvas de sensibilidade (referência: 9/21/50 EMA, M5×M15, três médias, estrito, fechada, x=0,5, stop 15 velas, K=5; descoberta jan–jun, n≈156)

Cada tabela mexe só um número. `nulo` = esperança da mesma célula nos 40 embaralhamentos; z = (real − nulo)/dp do nulo.

**EMA rápida**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| 5 | 152 | 16,4% | 19,0% | -17,8 | [-63 ; 33] | 2,2 | -0,86 |
| 6 | 154 | 16,2% | 18,8% | -17,5 | [-64 ; 34] | 1,7 | -0,83 |
| 7 | 156 | 15,4% | 18,7% | -23,1 | [-70 ; 28] | 1,4 | -1,09 |
| 8 | 158 | 15,8% | 18,6% | -19,8 | [-65 ; 32] | 0,4 | -0,89 |
| 9 | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| 10 | 156 | 15,4% | 19,3% | -27,1 | [-73 ; 21] | 1,1 | -1,26 |
| 11 | 157 | 15,9% | 18,8% | -20,6 | [-64 ; 25] | 2,0 | -1,04 |
| 12 | 156 | 16,7% | 19,1% | -16,8 | [-65 ; 30] | 1,2 | -0,83 |
| 13 | 156 | 16,7% | 19,1% | -16,8 | [-65 ; 30] | -0,0 | -0,75 |
| 15 | 157 | 15,9% | 19,3% | -24,3 | [-68 ; 21] | -1,6 | -0,96 |

**EMA média**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| 15 | 100 | 16,0% | 17,8% | -12,9 | [-63 ; 51] | 6,7 | -0,66 |
| 17 | 125 | 16,8% | 18,3% | -10,3 | [-55 ; 38] | 0,1 | -0,45 |
| 19 | 141 | 18,4% | 18,1% | 2,6 | [-52 ; 49] | 0,4 | 0,10 |
| 21 | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| 24 | 166 | 16,3% | 18,4% | -14,9 | [-55 ; 30] | -3,8 | -0,54 |
| 28 | 164 | 17,1% | 19,8% | -18,4 | [-63 ; 28] | -4,2 | -0,61 |
| 30 | 165 | 16,4% | 19,7% | -23,3 | [-66 ; 30] | -3,2 | -0,93 |
| 34 | 156 | 18,6% | 21,1% | -16,5 | [-62 ; 35] | 1,0 | -0,77 |
| 40 | 140 | 18,6% | 21,8% | -21,8 | [-76 ; 29] | -2,0 | -0,67 |

**EMA lenta**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| 34 | 203 | 18,2% | 17,6% | 4,9 | [-47 ; 63] | -8,2 | 0,62 |
| 40 | 191 | 18,3% | 15,9% | 20,0 | [-34 ; 78] | -5,4 | 1,14 |
| 45 | 175 | 16,6% | 17,1% | -4,2 | [-44 ; 45] | -3,2 | -0,05 |
| 50 | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| 60 | 130 | 15,4% | 17,3% | -13,6 | [-60 ; 36] | 7,0 | -0,86 |
| 72 | 79 | 17,7% | 15,6% | 16,2 | [-46 ; 94] | 2,1 | 0,56 |
| 89 | 42 | 28,6% | 17,7% | 75,1 | [-25 ; 173] | 2,5 | 1,59 |
| 100 | 30 | 16,7% | 15,5% | 8,7 | [-88 ; 103] | 8,9 | -0,00 |
| 120 | 19 | 26,3% | 12,8% | 108,5 | [-36 ; 295] | 15,8 | 1,32 |

**tipo de média**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| sma | 131 | 17,6% | 18,5% | -6,5 | [-56 ; 55] | 9,5 | -0,60 |

**toque x·ATR**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| 0.0 | 113 | 15,9% | 18,9% | -21,3 | [-71 ; 36] | 2,9 | -0,79 |
| 0.1 | 127 | 15,7% | 17,9% | -15,7 | [-65 ; 39] | 1,0 | -0,61 |
| 0.25 | 142 | 15,5% | 17,8% | -17,4 | [-61 ; 29] | -0,7 | -0,72 |
| 0.5 | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| 1.0 | 164 | 15,9% | 18,1% | -16,1 | [-63 ; 33] | -0,1 | -0,76 |

**EMAs do TF menor que precisam ser rompidas (f=só a rápida, fm=rápida+média, fms=as três)**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| fm | 186 | 19,9% | 17,4% | 21,5 | [-30 ; 88] | -9,1 | 1,31 |
| fms | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| f | 208 | 21,6% | 18,0% | 30,8 | [-24 ; 86] | -9,8 | 2,02 |

**EMA do toque (f=rápida, m=média)**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| m | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| f | 166 | 16,3% | 18,2% | -14,0 | [-57 ; 32] | -0,1 | -0,69 |

**alinhamento do TF maior**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| loose | 190 | 16,8% | 17,9% | -7,5 | [-52 ; 33] | -1,4 | -0,30 |
| strict | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |

**TF maior fechado (c) ou formando (f)**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| c | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| f | 94 | 12,8% | 18,7% | -42,5 | [-91 ; 8] | -6,8 | -1,25 |

**encaixe triplo (M5, M15 e H1)**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| M5/M15+H1 | 98 | 16,3% | 17,8% | -10,8 | [-68 ; 57] | 18,9 | -1,01 |

**par menor/maior em minutos (0 = diário)**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| 15/60 | 51 | 21,6% | 21,7% | -0,9 | [-89 ; 111] | -13,5 | 0,31 |
| 60/0 | 10 | 10,0% | 14,7% | -66,0 | [-252 ; 182] | -0,0 | -0,41 |
| 5/60 | 101 | 17,8% | 16,8% | 8,2 | [-69 ; 101] | 0,5 | 0,26 |
| 5/15 | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| 5/30 | 146 | 22,6% | 18,6% | 29,8 | [-26 ; 107] | -0,6 | 1,24 |
| 10/30 | 82 | 23,2% | 21,8% | 10,1 | [-71 ; 84] | -10,1 | 0,73 |

**N velas do stop técnico**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| 5 | 136 | 13,2% | 19,0% | -35,9 | [-71 ; 6] | -4,9 | -1,54 |
| 10 | 149 | 14,8% | 18,5% | -24,6 | [-64 ; 15] | -2,1 | -1,01 |
| 15 | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| 30 | 165 | 17,0% | 20,7% | -28,9 | [-81 ; 29] | 7,2 | -1,39 |

**alvo K × stop**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| 7.5 | 153 | 13,1% | 13,7% | -5,6 | [-66 ; 61] | 5,4 | -0,44 |
| hh | 153 | 13,1% | 14,9% | -15,7 | [-65 ; 32] | -0,6 | -0,55 |
| 10 | 150 | 11,3% | 12,6% | -12,6 | [-77 ; 67] | 8,4 | -0,72 |
| 3 | 160 | 20,6% | 26,4% | -28,7 | [-61 ; 5] | -6,6 | -1,30 |
| 5 | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |

**tipo de stop**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| e50h | 81 | 25,9% | 25,9% | 0,4 | [-110 ; 122] | -5,6 | 0,13 |
| atr1.5 | 19 | 36,8% | 56,8% | -115,4 | [-258 ; 44] | -74,0 | -0,65 |
| atr1.0 | 84 | 39,3% | 30,6% | 104,0 | [-52 ; 274] | 79,9 | 0,49 |
| x15 | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |

**entrada (cl = fechamento, f = EMA rápida do TF maior, m = EMA média do TF maior)**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| cl | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0,5 | -0,82 |
| m | 116 | 17,2% | 18,4% | -7,8 | [-59 ; 49] | 2,2 | -0,32 |
| f | 156 | 16,0% | 18,5% | -17,3 | [-63 ; 30] | 0,8 | -0,83 |

**preenchimento**

| valor | n | acerto | BE emp. | esp pts | IC95% | nulo | z |
|---|---|---|---|---|---|---|---|
| otimista | 157 | 17,2% | 18,6% | -9,8 | [-54 ; 39] | 2,8 | -0,59 |

Leitura: (i) a rápida (5 a 15) não mexe em nada, esperança entre −27 e −17, acerto 15–17%; (ii) a média vai de −17 (21) a ≈0 (19) e volta a −10…−23 até 40, tudo dentro do ruído (IC ±50); (iii) a lenta só 'melhora' de 89 a 120, mas com n=19–42 (poucos sinais com lenta tão longa), efeito de amostra pequena; (iv) toque de 0 a 1 ATR não muda; (v) romper só a EMA9 ou a 9+21 dá mais operações e esperança positiva não significativa (+31/+21) contra as três (−17): **exigir mais médias rompidas piora**; (vi) TF maior 'formando' piora (−43); (vii) M5×M30 e M10×M30 são os melhores pares na descoberta (+30/+10), M15×H1 e M5×H1 ficam em ≈0; (viii) stop de 5 velas piora (−36) contra 15 (−17); stop ATR 1,0 dá +104 mas o nulo também dá +91 (z 0,3); (ix) prazo de 5/10/15 min é irrelevante com entrada no fechamento (n idêntico: todas enchem no 1º minuto).

**Mapa de calor rápida × média (lenta = 50): esperança em pts/op (descoberta; n de 99 a 176 por célula)**

|   | média 15 | média 17 | média 19 | média 21 | média 24 | média 28 | média 30 | média 34 | média 40 |
|---|---|---|---|---|---|---|---|---|---|
| rápida 5 | -18 | -9 | +6 | -18 | -20 | -14 | -18 | -23 | +3 |
| rápida 6 | -20 | -12 | +4 | -18 | -27 | -24 | -28 | -28 | +3 |
| rápida 7 | -17 | -13 | +5 | -23 | -26 | -25 | -27 | -20 | -10 |
| rápida 8 | -19 | -13 | -0 | -20 | -18 | -21 | -25 | -20 | -10 |
| rápida 9 | -13 | -10 | +3 | -17 | -15 | -18 | -23 | -17 | -22 |
| rápida 10 | -15 | -17 | -7 | -27 | -21 | -28 | -32 | -19 | -23 |
| rápida 11 | -15 | -17 | -8 | -21 | -21 | -29 | -31 | -20 | -20 |
| rápida 12 | -11 | -19 | -5 | -17 | -23 | -31 | -29 | -20 | -23 |
| rápida 13 | -12 | -20 | -0 | -17 | -24 | -22 | -24 | -14 | -15 |
| rápida 15 |  | -15 | -4 | -24 | -31 | -28 | -28 | -23 | -28 |

Das 81 células, nenhuma passa de +6 pts e 77 são ≤0; z contra o nulo entre −1,3 e +0,2; acerto 14,4–18,9% (BE 17–22%). A coluna da média 19 é a menos negativa (≈0), mas é uma coluna isolada, sem platô.

**Grade conjunta rápida × média × lenta (771 células válidas com rápida<média<lenta), agregada pela lenta**

| lenta | células | n mediano | esp média pts | nulo | z médio | % positivas |
|---|---|---|---|---|---|---|
| 34 | 69 | 203 | -0,9 | -7,0 | 0,29 | 51% |
| 40 | 79 | 175 | 13,9 | -5,8 | 0,91 | 94% |
| 45 | 89 | 166 | -10,4 | -3,4 | -0,30 | 19% |
| 50 | 89 | 154 | -17,7 | -0,7 | -0,72 | 7% |
| 60 | 89 | 134 | -0,5 | 4,0 | -0,19 | 40% |
| 72 | 89 | 100 | -6,1 | -4,6 | -0,01 | 30% |
| 89 | 89 | 55 | 30,7 | -4,5 | 0,81 | 69% |
| 100 | 89 | 41 | 19,5 | -0,3 | 0,42 | 92% |
| 120 | 89 | 24 | 93,0 | 9,6 | 1,30 | 100% |

Lenta ≥ 89 fica positiva, mas com n mediano 24–55 (a pilha EMA9>21>lenta tão longa quase não ocorre) e z ≤ 1,3. A melhor célula isolada da grade conjunta tem t=1,92 (n=17); nenhuma das 771 chega a t≥2 (esperado ao acaso: 1,5–2,8). A lenta 40 (+14, 94% positivas) é vizinha de 34 (−1) e 45 (−10): não é platô.

## 6. As 10 regras congeladas (platô da descoberta): resultado nas 3 janelas

Congelado em `congelado_ANTES_da_confirmacao.json` (2026-10-04 23:12:55) **antes** de qualquer leitura de jul–ago. Seleção: famílias de 12 células (x × K) com ≥10/12 positivas, média ponderada > 0, n ≥ 30 em todas e z da família contra o nulo ≥ 1,3; famílias de stop ATR foram excluídas (o nulo delas também é positivo). R10 é o controle literal do dono. Célula central: x=0,5 ATR, K=5, EMA 9/21/50.

| regra | definição | janela | n | acerto | BE emp. | esp pts (M1) | IC95% | família + | família esp | nulo (60) | z | esp pts (ticks) | n ticks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | M10×M30 · rompe EMA9 · estrito · stop 15v | desc | 117 | 28,2% | 20,8% | 55,8 | [-13 ; 153] | 12/12 | 45,5 | -18,3 ± 28 | 2,65 | 62,7 | 85 |
|  |  | conf | 44 | 9,1% | 13,8% | -43,9 | [-115 ; 42] | 0/12 | -44,7 | 4,3 ± 62 | -0,78 | -43,9 | 44 |
|  |  | set | 30 | 13,3% | 12,4% | 9,8 | [-109 ; 158] | 5/12 | -18,1 | -25,5 ± 64 | 0,55 | 12,3 | 29 |
| R2 | M10×M30 · rompe 9+21 · estrito · stop 5v | desc | 91 | 30,8% | 22,2% | 58,8 | [-14 ; 135] | 12/12 | 65,1 | -11,8 ± 30 | 2,35 | 71,3 | 70 |
|  |  | conf | 37 | 16,2% | 14,1% | 16,2 | [-73 ; 121] | 8/12 | 11,6 | -7,5 ± 50 | 0,48 | 16,2 | 37 |
|  |  | set | 26 | 11,5% | 12,7% | -11,8 | [-123 ; 170] | 1/12 | -48,2 | -2,6 ± 58 | -0,16 | -39,2 | 25 |
| R3 | M10×M30 · rompe EMA9 · estrito · stop 5v | desc | 108 | 28,7% | 20,4% | 60,1 | [-14 ; 137] | 12/12 | 54,4 | -17,6 ± 25 | 3,11 | 75,0 | 81 |
|  |  | conf | 41 | 12,2% | 12,7% | -4,1 | [-74 ; 97] | 5/12 | -8,5 | 6,1 ± 61 | -0,17 | -4,1 | 41 |
|  |  | set | 29 | 10,3% | 9,9% | 5,9 | [-119 ; 145] | 4/12 | -19,1 | -20,5 ± 61 | 0,43 | 8,4 | 28 |
| R4 | M10×M30 · rompe 9+21 · frouxo · stop 5v | desc | 121 | 26,4% | 21,5% | 34,5 | [-26 ; 98] | 12/12 | 49,0 | -12,1 ± 27 | 1,74 | 44,8 | 92 |
|  |  | conf | 46 | 17,4% | 14,8% | 18,4 | [-71 ; 110] | 9/12 | 12,9 | -16,8 ± 41 | 0,86 | 18,4 | 46 |
|  |  | set | 31 | 9,7% | 12,9% | -32,3 | [-122 ; 133] | 0/12 | -62,5 | -3,7 ± 48 | -0,60 | -55,8 | 30 |
| R5 | M5×M30 · rompe 9+21 · estrito · stop 15v | desc | 168 | 23,2% | 17,8% | 43,8 | [-18 ; 104] | 8/12 | 13,5 | -8,9 ± 23 | 2,26 | 34,1 | 118 |
|  |  | conf | 59 | 11,9% | 23,1% | -68,9 | [-116 ; -8] | 0/12 | -67,2 | 0,0 ± 40 | -1,74 | -68,9 | 59 |
|  |  | set | 38 | 7,9% | 19,1% | -82,4 | [-157 ; -3] | 0/12 | -100,2 | -32,7 ± 39 | -1,28 | -110,9 | 35 |
| R6 | M5×M30 · rompe EMA9 · estrito · stop 15v | desc | 203 | 23,2% | 17,1% | 49,6 | [-4 ; 106] | 7/12 | 17,5 | -11,4 ± 19 | 3,16 | 43,8 | 144 |
|  |  | conf | 78 | 16,7% | 20,9% | -27,2 | [-90 ; 50] | 0/12 | -51,5 | -4,7 ± 31 | -0,74 | -27,2 | 78 |
|  |  | set | 51 | 11,8% | 18,2% | -45,0 | [-99 ; 19] | 3/12 | -37,2 | -42,0 ± 36 | -0,08 | -60,2 | 45 |
| R7 | M15×H1 · rompe EMA9 · frouxo · stop 15v | desc | 104 | 18,3% | 18,4% | -1,3 | [-73 ; 80] | 11/12 | 29,3 | -20,1 ± 37 | 0,50 | -2,9 | 76 |
|  |  | conf | 34 | 20,6% | 14,1% | 56,4 | [-64 ; 228] | 11/12 | 42,0 | -10,7 ± 44 | 1,51 | 56,4 | 34 |
|  |  | set | 28 | 25,0% | 19,5% | 45,3 | [-112 ; 205] | 12/12 | 75,0 | 3,3 ± 63 | 0,67 | 59,7 | 26 |
| R8 | M10×M30 · rompe 9+21 · estrito · stop 15v | desc | 100 | 28,0% | 21,6% | 45,6 | [-32 ; 132] | 12/12 | 37,7 | -11,8 ± 31 | 1,88 | 46,3 | 76 |
|  |  | conf | 41 | 12,2% | 15,5% | -28,2 | [-107 ; 56] | 2/12 | -22,0 | -9,9 ± 53 | -0,35 | -28,2 | 41 |
|  |  | set | 27 | 14,8% | 16,0% | -10,9 | [-134 ; 164] | 1/12 | -43,7 | -2,7 ± 58 | -0,14 | -37,2 | 26 |
| R9 | M5×M30 · rompe EMA9 · frouxo · stop = EMA50 do M30 | desc | 97 | 24,7% | 21,3% | 38,2 | [-68 ; 180] | 12/12 | 115,9 | -7,7 ± 46 | 1,00 | 105,7 | 62 |
|  |  | conf | 20 | 20,0% | 34,6% | -109,8 | [-226 ; 64] | 0/12 | -90,4 | 17,6 ± 74 | -1,72 | -109,8 | 20 |
|  |  | set | 22 | 22,7% | 29,0% | -58,1 | [-230 ; 173] | 0/12 | -158,6 | -41,3 ± 84 | -0,20 | -155,9 | 19 |
| R10 | M5×M15 · rompe 9+21+50 · estrito · stop 15v (literal) | desc | 156 | 16,0% | 18,5% | -17,4 | [-63 ; 29] | 0/12 | -32,6 | -6,3 ± 24 | -0,46 | -27,8 | 104 |
|  |  | conf | 55 | 21,8% | 22,7% | -5,6 | [-77 ; 78] | 5/12 | -4,9 | -19,3 ± 30 | 0,45 | -5,6 | 55 |
|  |  | set | 25 | 20,0% | 17,8% | 17,0 | [-93 ; 142] | 3/12 | -16,8 | -18,6 ± 52 | 0,68 | 17,0 | 25 |

A coluna ticks usa só os dias com arquivo de ticks (a descoberta perde jan–fev, por isso n menor). **Agregado das 9 regras (R1–R9, centro), M1 × ticks nos dias com ticks:** descoberta +50,2 × +50,6 (n=804, com forte sobreposição entre regras, não são 804 eventos independentes); confirmação **−20,7 × −20,7** (n=400); set **−41,9 × −41,9** (n=263).

**Platôs que replicaram: 0 de 9.** R2 e R4 ficaram positivas em 8/12 e 9/12 células da família em jul–ago (esp +16 e +18), mas caíram a 1/12 e 0/12 em set. R7 foi a única com 11/12 e 12/12 nas duas janelas novas (+56 e +45 no centro), com IC [−64 ; +228] e [−112 ; +205] e z contra o nulo de 1,5 e 0,7; na descoberta era −1 (família 11/12, média +29).

### Regras (SE … ENTÃO …)

| regra | papel | descoberta | confirmação jul–ago | set | status |
|---|---|---|---|---|---|
| SE o TF maior (M30; M10 ou M5 como menor) está alinhado de alta (EMA9>21>50, EMA21 subindo), o preço dele não fechou abaixo da EMA50 e o TF menor acaba de fechar abaixo da EMA9 (ou 9+21) pela 1ª vez ENTÃO comprar com limite no fechamento (prazo 10 min), stop = mínima das últimas 5–15 velas −5, alvo 5× | LIGA (entrada a favor), STOP, ALVO | +34 a +60 pts/op em 9 regras; famílias 12/12 | −20,7 pts/op (n=400); 0/9 platôs; só R7 positivo | −41,9 (n=263) | **falhou**: era seleção sobre ruído; z de 2–3 na descoberta não sobreviveu |
| SE o par é M15×H1, ruptura só da EMA9, alinhamento frouxo (só EMA21 subindo) ENTÃO mesma entrada | LIGA | −1 (z 0,5) | +56 (IC −64 ; +228) | +45 (IC −112 ; +205) | **pista**: 11/12 e 12/12 células positivas nas 2 janelas novas, mas n=34 e 28 e z de 1,5 e 0,7; não confirma, não recusa |
| SE a definição literal do dono (M5×M15, 3 médias, toque ≤0,5 ATR) ENTÃO entrar a favor | LIGA? | −17 (n=156); 2/12 células + | −6 (n=55) | +17 (n=25) | **negativa/ruído** |
| SE exigir que o TF menor rompa as TRÊS médias (em vez de só a EMA9 ou 9+21) ENTÃO | ACEITA/REJEITA | pior: −17 contra +31/+21 (n 156–208) | não testado isoladamente | — | tendência na descoberta; se usar, só EMA9 ou 9+21 |
| SE usar SMA em vez de EMA ENTÃO | parâmetro | SMA inverte R2 (−30), R4 (−29), R8 (−40) contra +45 a +59 com EMA; em R1/R3 cai de +56/+60 a +22/+24 | — | — | EMA ≥ SMA na descoberta; sem regra |
| SE variar rápida (5–15), média (15–34), lenta (34–120) ENTÃO o resultado | parâmetro | 27/27 positivas em R1–R6 e R8: insensível; quebra só com média 40 colada à lenta | mesmas grades com sinal médio −69 a +38 conforme a regra | idem | **insensível ao número**; o período não decide |
| SE o stop é técnico (≥50 pts) ENTÃO conferir com ticks | STOP | ticks = M1 (10 de 19.114 divergem) | idem | idem | **replicou** porque S ≥ 50 |
| SE horário < 11h ou vela M1 ≥ 2× ENTÃO o encaixe melhora | LIGA | R1: <11h +133, v2x +280 (n=28 e 14) | R1 conf+set: <11h +3 (n=23), v2x −16 (n=10) | (junto) | **falhou**: o efeito da descoberta some |
| SE a pernada de 750 em curso é a favor / contra do trade ENTÃO | DIREÇÃO | R6: a favor +85 × contra +26 (n=84/118) | R6 conf+set: −35 × −34 | (junto) | **falhou** |

## 7. Sensibilidade a períodos das regras congeladas

Grade 3×3×3 (rápida 7/9/11 × média 19/21/24 × lenta 40/50/60, EMA) por regra e janela; `nulo` é a esperança média da mesma grade nos 30 embaralhamentos da descoberta.

| regra | desc: positivas | desc: esp média | nulo | desc: min a max | conf: positivas | conf: esp média | set: positivas | set: esp média |
|---|---|---|---|---|---|---|---|---|
| R1 | 27/27 | 33,7 | -12,1 | 4 a 56 | 9/27 | -25,8 | 6/27 | -30,2 |
| R2 | 27/27 | 47,9 | -11,0 | 33 a 65 | 24/27 | 22,0 | 0/27 | -29,8 |
| R3 | 27/27 | 28,8 | -11,5 | 0 a 61 | 18/27 | 13,7 | 8/27 | -32,1 |
| R4 | 27/27 | 21,1 | -9,0 | 4 a 43 | 26/27 | 28,9 | 0/27 | -42,7 |
| R5 | 27/27 | 26,7 | -11,0 | 11 a 51 | 0/27 | -69,0 | 3/27 | -47,9 |
| R6 | 27/27 | 27,5 | -8,7 | 0 a 55 | 0/27 | -39,0 | 3/27 | -45,4 |
| R7 | 12/27 | 0,9 | -21,7 | -33 a 56 | 18/27 | 38,1 | 18/27 | 19,4 |
| R8 | 27/27 | 34,9 | -10,7 | 8 a 50 | 0/27 | -23,2 | 0/27 | -32,4 |
| R9 | 23/27 | 47,7 | 1,5 | -17 a 122 | 4/27 | -56,2 | 3/27 | -93,0 |
| R10 | 14/27 | 2,0 | -9,3 | -26 a 32 | 12/27 | 1,1 | 7/27 | -14,6 |

Curvas de um eixo por vez (descoberta; esperança em pts/op e n entre parênteses):

**R1**

- rápida: 5: +31 (154) · 6: +17 (143) · 7: +19 (136) · 8: +35 (124) · 9: +56 (117) · 10: +43 (115) · 11: +47 (108) · 12: +40 (110) · 13: +38 (106) · 15: +39 (99)
- média: 15: +18 (146) · 17: +36 (135) · 19: +49 (118) · 21: +56 (117) · 24: +53 (101) · 28: +50 (94) · 30: +64 (88) · 34: +52 (75) · 40: -45 (58)
- lenta: 34: +47 (123) · 40: +52 (121) · 45: +56 (120) · 50: +56 (117) · 60: +53 (115) · 72: +46 (109) · 89: +53 (102) · 100: +56 (101) · 120: +63 (91)

**R2**

- rápida: 5: +54 (107) · 6: +47 (105) · 7: +63 (103) · 8: +64 (97) · 9: +59 (91) · 10: +40 (90) · 11: +45 (87) · 12: +31 (86) · 13: +34 (86) · 15: +40 (86)
- média: 15: +16 (118) · 17: +42 (108) · 19: +42 (92) · 21: +59 (91) · 24: +53 (80) · 28: +58 (82) · 30: +71 (82) · 34: +52 (71) · 40: -33 (52)
- lenta: 34: +53 (98) · 40: +61 (94) · 45: +57 (92) · 50: +59 (91) · 60: +62 (90) · 72: +52 (87) · 89: +53 (82) · 100: +58 (82) · 120: +56 (74)

**R5**

- rápida: 5: +41 (185) · 6: +43 (174) · 7: +39 (172) · 8: +53 (169) · 9: +44 (168) · 10: +17 (161) · 11: +23 (151) · 12: +20 (151) · 13: +20 (152) · 15: +11 (141)
- média: 15: +16 (219) · 17: +35 (198) · 19: +29 (167) · 21: +44 (168) · 24: +19 (151) · 28: -0 (132) · 30: +20 (124) · 34: +15 (114) · 40: +10 (98)
- lenta: 34: +44 (171) · 40: +51 (167) · 45: +42 (168) · 50: +44 (168) · 60: +46 (160) · 72: +52 (152) · 89: +62 (143) · 100: +71 (141) · 120: +85 (131)

Em R1, R2 e R5 a esperança é positiva em quase toda a faixa de rápida e de lenta (planalto na descoberta), mas o planalto não existe fora da amostra em que foi escolhido. Média = 40 (colada à lenta 50) é o único ponto que inverte (−45 e −33). Na confirmação (jul–ago), R2/R4 seguem positivas em 24/27 e 26/27 células; em set caem a 0/27: o sinal oscila com a janela, não com o período.

## 8. Filtros cruzados (horário, vela M1 ≥ 2×, pernada de 750)

| regra | janela | filtro | grupo | n | acerto | BE emp. | esp pts |
|---|---|---|---|---|---|---|---|
| R1 | desc | hora | 11-13h | 37 | 27,0% | 23,6% | 25,7 |
| R1 | desc | hora | <11h | 28 | 32,1% | 17,7% | 132,8 |
| R1 | desc | hora | >13h | 52 | 26,9% | 21,6% | 35,7 |
| R1 | desc | v2x | sem v2x | 103 | 26,2% | 22,4% | 25,3 |
| R1 | desc | v2x | v2x | 14 | 42,9% | 19,2% | 280,1 |
| R1 | desc | pernada750 | a favor | 40 | 27,5% | 21,0% | 42,2 |
| R1 | desc | pernada750 | contra | 77 | 28,6% | 20,8% | 62,8 |
| R1 | conf+set | hora | 11-13h | 15 | 0,0% | 100,0% | -136,0 |
| R1 | conf+set | hora | <11h | 23 | 17,4% | 17,1% | 2,8 |
| R1 | conf+set | hora | >13h | 36 | 11,1% | 10,2% | 9,4 |
| R1 | conf+set | v2x | sem v2x | 64 | 10,9% | 13,3% | -23,2 |
| R1 | conf+set | v2x | v2x | 10 | 10,0% | 11,3% | -15,5 |
| R1 | conf+set | pernada750 | a favor | 25 | 12,0% | 10,5% | 15,0 |
| R1 | conf+set | pernada750 | contra | 49 | 10,2% | 14,2% | -41,1 |
| R6 | desc | hora | 11-13h | 57 | 17,5% | 14,0% | 37,6 |
| R6 | desc | hora | <11h | 53 | 28,3% | 14,7% | 143,8 |
| R6 | desc | hora | >13h | 93 | 23,7% | 23,1% | 3,2 |
| R6 | desc | v2x | sem v2x | 179 | 22,9% | 16,8% | 49,4 |
| R6 | desc | v2x | v2x | 24 | 25,0% | 19,2% | 51,1 |
| R6 | desc | pernada750 | a favor | 84 | 25,0% | 15,2% | 85,0 |
| R6 | desc | pernada750 | contra | 118 | 22,0% | 18,8% | 25,5 |
| R6 | desc | pernada750 | sem | 1 | 0,0% | 100,0% | -92,0 |
| R6 | conf+set | hora | 11-13h | 32 | 9,4% | 21,8% | -73,2 |
| R6 | conf+set | hora | <11h | 50 | 18,0% | 20,9% | -22,7 |
| R6 | conf+set | hora | >13h | 47 | 14,9% | 18,5% | -20,0 |
| R6 | conf+set | v2x | sem v2x | 106 | 13,2% | 20,4% | -47,2 |
| R6 | conf+set | v2x | v2x | 23 | 21,7% | 17,9% | 25,6 |
| R6 | conf+set | pernada750 | a favor | 55 | 12,7% | 18,0% | -35,3 |
| R6 | conf+set | pernada750 | contra | 74 | 16,2% | 21,3% | -33,5 |
| R7 | desc | hora | 11-13h | 28 | 17,9% | 17,6% | 3,2 |
| R7 | desc | hora | <11h | 29 | 17,2% | 15,6% | 19,2 |
| R7 | desc | hora | >13h | 47 | 19,1% | 21,9% | -16,6 |
| R7 | desc | v2x | sem v2x | 91 | 13,2% | 19,1% | -48,3 |
| R7 | desc | v2x | v2x | 13 | 53,8% | 20,6% | 328,0 |
| R7 | desc | pernada750 | a favor | 33 | 21,2% | 19,8% | 8,8 |
| R7 | desc | pernada750 | contra | 71 | 16,9% | 17,5% | -5,9 |
| R7 | conf+set | hora | 11-13h | 20 | 20,0% | 16,1% | 37,2 |
| R7 | conf+set | hora | <11h | 17 | 17,6% | 9,0% | 135,1 |
| R7 | conf+set | hora | >13h | 25 | 28,0% | 26,8% | 5,8 |
| R7 | conf+set | v2x | sem v2x | 54 | 24,1% | 15,9% | 69,9 |
| R7 | conf+set | v2x | v2x | 8 | 12,5% | 23,7% | -73,9 |
| R7 | conf+set | pernada750 | a favor | 24 | 29,2% | 18,7% | 62,4 |
| R7 | conf+set | pernada750 | contra | 38 | 18,4% | 14,3% | 44,4 |
| R10 | desc | hora | 11-13h | 52 | 15,4% | 16,2% | -6,6 |
| R10 | desc | hora | <11h | 37 | 13,5% | 19,2% | -47,7 |
| R10 | desc | hora | >13h | 67 | 17,9% | 19,5% | -9,1 |
| R10 | desc | v2x | sem v2x | 140 | 17,1% | 18,1% | -6,5 |
| R10 | desc | v2x | v2x | 16 | 6,2% | 16,7% | -113,2 |
| R10 | desc | pernada750 | a favor | 42 | 16,7% | 26,1% | -43,1 |
| R10 | desc | pernada750 | contra | 112 | 16,1% | 16,9% | -6,5 |
| R10 | desc | pernada750 | sem | 2 | 0,0% | 100,0% | -89,5 |
| R10 | conf+set | hora | 11-13h | 30 | 20,0% | 24,0% | -25,2 |
| R10 | conf+set | hora | <11h | 21 | 28,6% | 22,2% | 52,8 |
| R10 | conf+set | hora | >13h | 29 | 17,2% | 18,9% | -8,2 |
| R10 | conf+set | v2x | sem v2x | 64 | 21,9% | 20,9% | 6,5 |
| R10 | conf+set | v2x | v2x | 16 | 18,8% | 22,3% | -18,9 |
| R10 | conf+set | pernada750 | a favor | 20 | 20,0% | 16,6% | 24,2 |
| R10 | conf+set | pernada750 | contra | 60 | 21,7% | 22,6% | -6,2 |

Sem estabilidade entre descoberta e confirmação (cada célula tem n ≤ 50 depois da divisão e nenhum filtro mantém o sinal). Não ligar nenhum.

## 9. Tamanho de mão e risco de ruína a partir de R$250 (1 contrato; `rodada4/decisao/motor.py`)

Esperança na janela (pts e R$ a R$0,20/pt), perda média por operação perdida, p encolhido (n0=100) para a base, mão = `motor.tamanho` (Kelly 1/4 com teto de pior caso 25%), ruína = Monte Carlo de 215 operações com piso R$100.

| regra | janela | n | esp pts | esp R$ | stop médio pts | perda R$/op | p encolhido | mão | ruína 215 ops | seq. perdas máx |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 | desc | 117 | 55,8 | 11,16 | 152 | 31,5 | 0,248 | 1 | 49% | 10 |
| R1 | conf+set | 74 | -22,1 | -4,43 | 134 | 26,5 | 0,121 | 0 | 100% | 17 |
| R2 | desc | 91 | 58,8 | 11,76 | 142 | 30,6 | 0,263 | 1 | 40% | 8 |
| R2 | conf+set | 63 | 4,7 | 0,93 | 115 | 23,3 | 0,139 | 1 | 84% | 16 |
| R3 | desc | 108 | 60,1 | 12,03 | 142 | 29,5 | 0,247 | 1 | 43% | 9 |
| R3 | conf+set | 70 | 0,1 | 0,01 | 114 | 22,6 | 0,114 | 1 | 88% | 12 |
| R4 | desc | 121 | 34,5 | 6,90 | 141 | 29,8 | 0,242 | 1 | 57% | 10 |
| R4 | conf+set | 77 | -2,0 | -0,40 | 113 | 23,2 | 0,144 | 0 | 100% | 17 |
| R5 | desc | 168 | 43,8 | 8,76 | 143 | 28,7 | 0,212 | 1 | 59% | 17 |
| R5 | conf+set | 97 | -74,2 | -14,83 | 136 | 28,2 | 0,161 | 0 | 100% | 22 |
| R6 | desc | 203 | 49,6 | 9,92 | 140 | 28,1 | 0,212 | 1 | 56% | 29 |
| R6 | conf+set | 129 | -34,2 | -6,85 | 126 | 26,3 | 0,170 | 0 | 100% | 17 |
| R7 | desc | 104 | -1,3 | -0,26 | 163 | 31,7 | 0,183 | 0 | 100% | 11 |
| R7 | conf+set | 62 | 51,4 | 10,28 | 141 | 28,0 | 0,188 | 1 | 56% | 13 |
| R8 | desc | 100 | 45,6 | 9,12 | 149 | 31,0 | 0,248 | 1 | 52% | 9 |
| R8 | conf+set | 68 | -21,3 | -4,27 | 136 | 27,6 | 0,147 | 0 | 100% | 18 |
| R9 | desc | 97 | 38,2 | 7,63 | 253 | 47,7 | 0,230 | 1 | 78% | 14 |
| R9 | conf+set | 42 | -82,7 | -16,54 | 284 | 52,9 | 0,283 | 0 | 100% | 9 |
| R10 | desc | 156 | -17,4 | -3,48 | 125 | 26,2 | 0,170 | 0 | 100% | 19 |
| R10 | conf+set | 80 | 1,4 | 0,29 | 127 | 27,4 | 0,211 | 1 | 83% | 14 |

Na confirmação+set agregada, 6 das 10 têm esperança ≤ 0 (mão 0, ruína 100%) e 3 têm ruína ≥ 83%; R7 é a única positiva com mão 1 e ainda 55% de ruína em 215 operações (acerto ~18–19%, 13 perdas seguidas). A R$250 só cabe 1 contrato e uma perda (R$23–53) já é 9–21% do caixa.

## 10. Veredito

1. **O encaixe muda a probabilidade de acerto de uma entrada a favor?** Na descoberta, em 9 regras, parecia (+34 a +60 pts/op, acerto 23–34% contra BE 17–22%, 2–3 desvios acima do nulo). Na confirmação e em set, **não**: juntas dão −21 e −42 pts/op, acerto 15% e 12%. A definição literal do dono nunca saiu do ruído (−17, −6, +17, ICs de ±70).
2. **Quanto?** Se existe, é menor do que a janela consegue ver: com ~1 operação/dia e 25–80 operações por janela, o IC95% é de ±70 a ±120 pts/op. Não é mensurável com os dados de 2026.
3. **Paga o custo?** Nenhuma célula confirmou esperança positiva estável. R7 (M15×H1, rompe EMA9, alinhamento frouxo) foi a única a não falhar nas duas janelas novas e merece ≥150 operações novas antes de qualquer decisão.
4. **Períodos:** o resultado é insensível ao número exato (9/21/50 ≈ 5/17/34 ≈ 13/24/120). Importam o par de tempos, o stop técnico e quantas médias o TF menor precisa romper (menos é melhor). SMA × EMA: sem efeito consistente.
5. **Tese do dono ("é só um recuo, não um rompimento")**: o rompimento do TF menor SEM o TF maior alinhado dá −13 a −4 pts em reversão e +1 a −21 em continuação; o TF maior também rompendo é o pior grupo na descoberta (−38 a −49). O TF maior alinhado não faz o recuo do M5 virar uma entrada melhor que o acaso.
6. **Em aberto:** R7. Qualquer uso exige pregões novos (após 01/10) e leitura sempre contra o nulo da MESMA célula (o nulo embaralhado do WIN-2026 é positivo para stops largos).

## 11. Limitações

- 1 a 1,7 operações/dia e 25–80 por janela de confirmação: ICs cruzam zero em quase tudo. O resultado negativo também tem IC largo (só R5 em conf [−116 ; −8] e set [−157 ; −3] exclui zero).
- Sinais com stop técnico fora de 50–500 pts são descartados (~34% na referência): a regra só vale na faixa aceita.
- Long e short simulados com posição independente por lado; R1–R9 compartilham sinais (não são independentes).
- Diário: ~40 barras de aquecimento (nov–dez/2025), EMA50 diária não convergida; par H1×D com 3–10 sinais, sem conclusão.
- WIN@D é série ajustada por diferença; ticks alinhados por deslocamento diário (desvio ≈0,6 pt).
- Fora dos mapas: o semanal não foi testado (opcional).
