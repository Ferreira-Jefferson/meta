# b3 - Posição do preço em relação às médias (WIN M5, só 2026)

Baseline reproduzido: +R$7.490,10 · 11/14 · pior -272,30 · PF 1,54 · 413 trades · DD 794,70 · sem set 6.782,60.
Variantes: 82 na grade principal + 20 de verificação de platô (102). Log: `b3_posicao_preco_stdout.log`.
Zonas novas (patch em memória de `zona_ok`, arquivo original intocado): `entre34_100`, `acima_todas`, `d9max/d9min<k>` (|c-EMA9| em ATR14), `d21max<k>`.

## Resumo
| variante | líquido | jan+ | pior | trades | PF | DD | sem set | meses melhores |
|---|---|---|---|---|---|---|---|---|
| baseline | 7490,10 | 11/14 | -272,30 | 413 | 1,54 | 794,70 | 6782,60 | - |
| corpo>m1, nenhuma incl. | 7460,00 | 12/14 | -165,90 | 324 | 1,61 | 769,50 | 7269,00 | 8 |
| corpo>m1, (2,3,4) | 7404,60 | 12/14 | -232,20 | 330 | 1,60 | 769,50 | 7213,60 | 7 |
| candle>m1, nenhuma | 7220,50 | 10/14 | -278,10 | 285 | 1,63 | 940,50 | 7250,50 | 9 |
| d9max0,5 todas | 7173,50 | 11/14 | -92,70 | 377 | 1,67 | 663,50 | 6285,50 | 8 |
| d9max0,25 todas | 6786,90 | 12/14 | -97,40 | 311 | 1,85 | 538,40 | 6095,90 | 5 |
| d9max2,0 todas | 8383,30 | 11/14 | -284,10 | 413 | 1,62 | 771,90 | 7441,80 | 10 |
| d21max3,0 todas | 8049,10 | 11/14 | -271,90 | 413 | 1,59 | 771,90 | 7252,60 | 10 |
| toque2 (qualquer incl.) | 5020-5194 | 10-11/14 | -496 a -646 | 272-368 | 1,5-1,7 | 650-690 | 4244-4452 | 4-5 |
| entre12 (incl. relaxada) | 3044-3558 | 10-11/14 | -926,50 | 292-306 | 1,4 | 926,50 | 3970-4485 | 5-6 |
| entre23 | 2127-2209 | 8-10/14 | -477,50 | 303-309 | 1,4 | 546 | 2605-2687 | 4 |
| entre34_100 (34,100,200 incl.) | 438,80 | 5/14 | -279,80 | 216 | 1,13 | 422 | -477,70 | 5 |

Zero trades (identidade matemática): entre12/entre23/entre34_100 com inclinação das rápidas; todas as combos com EMA que a inclinação torna impossível = 0/14, 0 trades.
`acima_todas` com todas inclinadas = baseline idêntico (confirma a identidade).

## Leitura
- "Preço acima de todas": já é implícito pela inclinação; não adiciona nada.
- "No meio das médias" (entre12/23, recuo à 34-100, toque na 21): todos PIORAM muito (de -2,0k a -7,0k vs baseline). O recuo é pior que a continuação. entre34_100 perde em 2026 sem setembro.
- "Corpo/candle além da EMA9": mantém líquido (~-30) com menos trades, pior janela melhor (-165,90, 12/14), sem set melhor (7.269 vs 6.783). É uma troca de risco, não ganho de retorno: líquido total não melhora.
- Anti-esticado (d9max k): pico 2,0 ATR dá +893, mas NÃO é platô: 1,75 -> 7.725, 2,0 -> 8.383, 2,25 -> 7.936, 2,5 -> 7.504, 3,0 -> 7.328, 4,0 -> 7.486, 1,5 -> 7.431 (pior -462), 1,0 -> 7.284. Os mesmos 413 trades com PnL diferente = o filtro bloqueia poucos sinais e o resto vira reentrada deslocada; diferença é ruído de poucos trades, não efeito. d21max segue o mesmo padrão (3,0 -> 8.049; 2,5 -> 7.569; 4,0 -> 7.455).
- Limiares apertados (d9max 0,25-0,5) melhoram PF (1,67-1,85), pior janela (-93/-97) e DD (539-664), mas cortam retorno e sem_set (6.286/6.096 < 6.783), e <150 não, mas trades 311-377. Alternativa defensiva, não candidata de retorno.

## Candidatas congeladas
Nenhuma supera a atual no conjunto. Observação opcional para quem prioriza risco sobre retorno (NÃO congeladas como melhores; se o dono quiser, apenas para a validação 2025 como "defensivas"):
1. `zona="corpo>m1", inclina=()` (324 trades): 7.460, 12/14, pior -165,90, DD 769,50, sem set 7.269, 8 meses melhores. Vizinhos (234, 34, 1234, todas) todos 7.257-7.460, 12/14 - platô real.
Nenhuma outra variante tem platô.

**Veredito: nenhuma supera a atual** (a defensiva corpo>m1 empata em líquido e melhora pior/DD/sem set, platô consistente).
