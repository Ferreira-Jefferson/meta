# B1 - Mais médias (WIN M5, só 2026)

Baseline (9/21/34/100/200): +7.490,10 | 11/14 | pior -272,30 | PF 1,54 | 413 trades | DD 794,70 | sem set 6.782,60.

18 conjuntos de períodos x até 4 modos de inclinação = 50 variantes rodadas (todas em `b1_mais_medias_stdout.log`).
Achado: o modo de inclinação (todas / só as 5 originais / só 3 mais rápidas / 5 mais rápidas) deu resultado IDÊNTICO ao centavo em todos os conjuntos; inclinação das médias lentas é redundante dado o alinhamento. Há portanto 18 resultados distintos, não 50.

| conjunto | líquido | jan+ | pior | PF | trades | DD | sem set | meses melhor/pior |
|---|---|---|---|---|---|---|---|---|
| base | 7.490 | 11/14 | -272 | 1,54 | 413 | 795 | 6.783 | - |
| +300 | 7.327 | 11/14 | -444 | 1,59 | 368 | 964 | 6.676 | 4/6 |
| +300,400 | 6.883 | 11/14 | -337 | 1,58 | 352 | 857 | 6.111 | 6/4 |
| +300,400,500 | 6.613 | 10/14 | -337 | 1,56 | 346 | 885 | 5.863 | 6/4 |
| +300,500,800 | 6.884 | 11/14 | -337 | 1,60 | 341 | 862 | 6.127 | 7/4 |
| +250 | 6.719 | 11/14 | -447 | 1,51 | 375 | 987 | 6.280 | 5/5 |
| +400 | 7.873 | 10/14 | -375 | 1,65 | 363 | 895 | 6.952 | 6/4 |
| +600 | 7.744 | 11/14 | -443 | 1,64 | 362 | 963 | 7.048 | 5/4 |
| +500 | 7.603 | 11/14 | -375 | 1,63 | 361 | 895 | 6.755 | 5/4 |
| +800 | 6.824 | 11/14 | -516 | 1,53 | 368 | 1.036 | 6.564 | 5/3 |
| 9/21/34/55/100/200 | 7.884 | 11/14 | -282 | 1,60 | 402 | 783 | 7.112 | 6/7 |
| 9/21/34/100/150/200/300 | 7.715 | 11/14 | -325 | 1,65 | 362 | 836 | 7.064 | 4/6 |
| 9/21/34/55/100/200/300 | 7.734 | 11/14 | -494 | 1,66 | 357 | 953 | 7.019 | 7/6 |
| 9/21/34/55/100/150/200/300 | 8.012 | 11/14 | -355 | 1,71 | 353 | 804 | 7.297 | 7/6 |
| 9/21/34/55/100/150/200/300/400 | 7.460 | 11/14 | -248 | 1,69 | 338 | 697 | 6.623 | 6/7 |
| 9/21/34/100/200/300/400/500/600 | 6.981 | 11/14 | -337 | 1,61 | 340 | 888 | 6.190 | 7/4 |
| 9/21/34/100/200/250/300 | 7.377 | 11/14 | -337 | 1,61 | 361 | 857 | 6.540 | 6/4 |

## Leitura
- Acrescentar só médias lentas ao fim (300, 400, 500...) NÃO melhora o conjunto: líquido cai ou fica igual, pior janela e DD pioram. Ideia do dono "200, 300, mais" não se sustenta nessa forma.
- O que melhora é inserir 55 (e 150) no meio: 9/21/34/55/100/200 e 9/21/34/55/100/150/200/300 (platô: vizinhos 7.4k-8.0k, PF 1,6-1,7, sem set 7.0k-7.3k).
- Melhora de líquido pequena (+5% a +7%) e consistente só no PF; meses que melhoram vs pioram ~ 6-7 / 6-7, ou seja moeda ao ar mês a mês. Mesmos 9 meses de seleção, sem validação fora.

## Candidatas congeladas (kwargs exatos de rodar_janelas)
1. `periodos=(9,21,34,55,100,150,200,300)` -> +8.012,30; 11/14; pior -355,10; PF 1,71; DD 804,30; sem set 7.297,30; 7 melhor/6 pior.
2. `periodos=(9,21,34,55,100,200)` -> +7.883,80; 11/14; pior -282,20; PF 1,60; DD 783,00; sem set 7.112,30; 6/7. (único com pior e DD ≈ ou melhor que a base)
3. `periodos=(9,21,34,55,100,150,200,300,400)` -> +7.459,60; 11/14; pior -247,90; PF 1,69; DD 697,10; sem set 6.623,10; 6/7. (perfil de risco: menor pior e DD, líquido ~ igual)
Sem passar `inclina` (todas inclinadas); os modos de inclinação são equivalentes.
