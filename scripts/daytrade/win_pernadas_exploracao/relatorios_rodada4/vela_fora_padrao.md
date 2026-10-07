# Vela fora do padrão e lateralização antes de pernada de 750 pts — WIN, 2026

## Método
- Dados: WIN@D M1, só 2026. Descoberta jan–jun (122 pregões), confirmação jul–ago (44 pregões). Set/26 não usado.
- Sinal avaliado no fechamento da vela (M1, M5 ou M15), só com informação até ali. Resultado a partir desse fechamento, janelas de 15/30/60 min:
  - `any`: o preço anda 750+ em alguma direção;
  - `same`/`contra`: anda 750 na direção da vela-sinal / contra a ela antes de andar 250 contra (empate dentro da mesma barra conta como adverso);
  - MFE: máximo a favor antes de 250 contra.
- Base 1 = mesma faixa de 30 min do relógio. Base 2 (mais dura) = mesma faixa de 30 min × quartil da amplitude da última hora (controla o "dia agitado"). Z por razão com erro agrupado por dia (as velas de um mesmo dia se sobrepõem). A base do nulo embaralhado foi substituída por esta estratificação por faixa; a permutação dentro da faixa daria o mesmo valor esperado.
- Testes: 90 variantes (tamanho relativo, volume, negócio médio, forma, 1ª vela do dia, isolada × saindo de compressão, rompimento de caixa, compressão, NR4/NR7, inside, aceleração, lateralização M1 e rompimento dela) × 3 janelas ≈ 263 linhas de descoberta, ≈ 600 testes contando os 3 desfechos. Limiar de congelamento: |z|≥3 (base 2) em ≥2 das 3 janelas, mesmo sinal → 23 regras congeladas (`congelado_ANTES_da_confirmacao.json`, gravado antes de rodar jul–ago).

## Descoberta (jan–jun), janela 30 min, base 2 — destaques
| variante | n | P(750) | base | z |
|---|---|---|---|---|
| range ≥3× o do mesmo horário nos 20 dias anteriores (M1) | 1567 | 32,0% | 18,5% | 4,9 |
| range ≥2× o do mesmo horário (M1) | 5897 | 26,9% | 20,0% | 4,3 |
| volume ≥3× o do mesmo horário (M1) | 1209 | 24,0% | 14,3% | 3,7 |
| range ≥3× média das 50 anteriores (M1) | 310 | 34,5% | 20,2% | 3,9 |
| M5 range ≥2× média 20 | 214 | 29,4% | 18,2% | 3,4 |
| lateral M1 (20 min, caixa ≤150 pts) | 1322 | 0,1% | 1,5% | −9,1 |
| compressão M5 k4 ≤0,5 | 941 | 13,9% | 20,0% | −4,9 |
| direção: vela grande ≥3× → pernada contra a vela | 1561 | 13,3% | 7,7% | 6,3 |
| direção: vela grande ≥3× → pernada a favor da vela | 1561 | 11,8% | 7,7% | 2,8 |

Sem efeito (|z|<3 nas três janelas): corpo×pavio, marubozu (só ruído), absorção (volume alto/range pequeno), negócio médio (VOL/TICKVOL), 1ª vela grande do dia vs seguintes, NR4/NR7, inside bar, 3 velas de mesma cor, aceleração (média3/média20), vela grande após compressão vs isolada (as duas sobem igual).

## Confirmação (jul–ago), regras congeladas, N=30, base 2
| regra | desc n / P / base | conf n / P / base | z conf |
|---|---|---|---|
| range ≥2× mesmo horário (M1) | 5897 / 26,9 / 20,0 | 1868 / 13,5 / 9,3 | 2,4 |
| range ≥3× mesmo horário (M1) | 1567 / 32,0 / 18,5 | 359 / 14,2 / 8,2 | 1,6 |
| range ≥2× mesmo horário (M15) | 319 / 30,1 / 22,2 | 61 / 23,0 / 13,6 | 2,0 |
| range ≥2× mesmo horário (M5) | 993 / 28,5 / 21,3 | 246 / 12,6 / 9,3 | 1,0 |
| volume ≥3× mesmo horário (M1) | 1209 / 24,0 / 14,3 | 648 / 8,6 / 5,0 | 1,2 |
| range ≥3× média 50 (M1) | 310 / 34,5 / 20,2 | 99 / 22,2 / 18,1 | 1,4 |
| contra-vela, range ≥2× (M1) | 5853 / 10,6 / 8,2 | 1860 / 4,9 / 3,7 | 2,1 |
| contra-vela, range ≥3× (M1) | 1561 / 13,3 / 7,7 | 359 / 5,6 / 3,1 | 2,5 |
| lateral M1 (qualquer caixa) | P≈0–1% | P≈0,2–0,6% | ~0 (base já ~0,3%: sem poder) |
| rompimento de lateral | P≈0–2% | P≈0,6–3% | ~0 (idem) |
| vela M5 grande isolada / 2ª em diante / tam&vol | n pequeno | n 51 / <30 / <30 | 0,9 / — / — |

Estabilidade mensal (≥3× mesmo horário, M1, N=30, P/base): jan .34/.18, fev .21/.19, mar .43/.20, abr .27/.23, mai .28/.17, jun .24/.16, jul .18/.07, ago .11/.09 — positivo em 8/8 meses, mas fev, abr e ago quase no zero.
Jul–ago teve volatilidade menor (base 9% contra 20% na descoberta), então os percentuais absolutos caem; a razão (lift) é o que se mantém.

## Leitura
- A vela fora do padrão em relação ao MESMO HORÁRIO dos dias anteriores (tamanho ou volume) marca "volatilidade viva": o lift da chance de 750 em 15/30/60 min é ~1,3–2,5× sobre a base horário×agitação. Replicou em sentido e em 8/8 meses, mas com significância fraca na confirmação (n pequeno) — parcial.
- Não indica DIREÇÃO: a pernada vem tanto a favor quanto contra a vela (contra um pouco mais frequente, ~1,2–1,4×, sem diferença estável entre same e contra). MFE a favor antes de 250 contra sobe (≈330 vs 245 pts na descoberta; 231 vs 198 na confirmação).
- Tamanho relativo às últimas k velas, sem referência de horário, vale pouco; o volume sozinho é mais fraco que o tamanho; não há ganho em combinar os dois.
- Lateralização: a chance de nascer pernada em 30 min cai a perto de zero (1,5% base 2 → 0,1%; z −9 na descoberta); rompimento da caixa também não gera pernada (≤2%). Na confirmação a base já era ~0,3%, então não há como distinguir — consistente, não testável. Atenção: lateral é o estado de baixa volatilidade, o efeito é em boa parte o mesmo que "a volatilidade persiste".
- Pico de volume com range pequeno (absorção) e negócio médio: nada.
