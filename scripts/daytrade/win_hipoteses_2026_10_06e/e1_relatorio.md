# e1 — volume de alta x baixa e volume do recuo x impulso (WIN M30, só 2026)

Baseline v2.02 reproduzido: +R$8.377,14, 13/14, pior −117,00, PF 1,77, 248 trades, DD 781,50, sem setembro +7.785,61.

Variantes rodadas: 168 (56 com volume + 112 controles de preço: range h−l e |c−o|, mesmo N/L).
- Ideia 1 (alta×baixa): N∈{3,5,8,13} × L∈{0,5;0,55;0,6;0,65} × {simples, ponderada pelo corpo} = 32 por base.
- Ideia 2 (recuo×impulso): N∈{3,5,8,13} × L∈{0,6;0,8;1,0} × {recuo baixo entra, recuo alto entra} = 24 por base.
Só velas fechadas até a barra do sinal (inclusive). Tabela completa: `e1_resumo.csv`; log: `e1_volume_alta_baixa_recuo_stdout.log`.

## Resultado com volume (melhores por líquido; baseline 8.377 / 13/14 / −117 / 248 tr / DD 781 / s.set 7.786)
| variante | líquido | jan+ | pior | PF | trades | DD | s.set | meses melhor/pior |
|---|---|---|---|---|---|---|---|---|
| RC_v_N13_L0,6_alto | 8.528 | 12/14 | −196,5 | 1,87 | 234 | 694 | 7.775 | 5/4 |
| AB_v_N3_L0,65_pond | 8.124 | 13/14 | −192 | 1,99 | 193 | 888 | 7.884 | 8/6 |
| RC_v_N8_L0,6_alto | 8.093 | 13/14 | −100,8 | 1,92 | 224 | 615 | 7.314 | 7/5 |
| AB_v_N3_L0,6_simples | 7.890 | 12/14 | −192 | 1,92 | 204 | 789 | 7.550 | 8/6 |
| AB_v_N5_L0,5_simples | 7.860 | 12/14 | −300 | 1,89 | 213 | 759 | 7.492 | 6/7 |

- Só 1 de 56 variantes com volume supera o líquido do baseline (+151, +1,8%), e perde em janelas+ (12 vs 13), pior mês, e sem setembro (7.775 < 7.786). É um pico isolado: vizinhos N8 = 8.093 (queda), N5 = 6.069. Sem platô.
- Filtrar quase sempre REDUZ o líquido: o baseline já é bom e cada filtro corta trades bons (248 → 190-230) sem separar os maus. Mediana das 56 variantes com volume bem abaixo do baseline; nenhuma fica acima no conjunto (líquido + janelas + pior + DD + s.set + meses).
- Recuo com volume BAIXO entrando ("tendência saudável"): piora forte e monotônica (N13 L0,6: 1.511, 42 trades; PF alto só porque são poucos trades). A hipótese do dono não se sustenta; o inverso (recuo com volume ALTO entra) é menos ruim em N8/N13 L0,6 mas é o pico isolado acima.
- Ideia 1: em N=3 há melhoras marginais de PF (1,9–2,0) com −45 trades, mas líquido cai e DD sobe; N≥8 piora em tudo.

## Controle de preço
Range e |c−o| no lugar do volume dão resultados da mesma ordem (ex.: AB_rng_N3_L0,5_simples 7.844 vs AB_v 7.732; RC_rng_N5_L0,6_alto 7.759 com pior −43,7 e DD 467, melhor que o volume equivalente, 6.069). A nuvem do volume não se separa da do preço; em vários pares o controle iguala ou supera. Em N=3 simples, |c−o| e range são idênticos entre si e ao ponderado (a ponderação por corpo/range torna base=corpo ≡ range). O volume não acrescenta.

## Candidatas
Nenhuma. `e1_candidatas.py` tem `CANDIDATAS = {}` (as funções `feat_alta_baixa` e `feat_recuo` ficam disponíveis para 2025, não rodadas).

## Conclusão
Volume de alta×baixa e volume do recuo×impulso não acrescentam como filtro de entrada ao WinCincoMedias: 0/56 melhoram o conjunto; 1/56 melhora só o líquido, sem platô e sem superar o controle de preço.
