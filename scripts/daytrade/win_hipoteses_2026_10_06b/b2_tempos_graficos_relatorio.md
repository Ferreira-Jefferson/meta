# b2 — Tempos gráficos (WIN, só 2026)

Baseline (M5, 9/21/34/100/200, TTL 5): +R$7.490,10 · 11/14 · pior −272,30 · PF 1,54 · 413 trades · DD 794,70 · sem setembro 6.782,60 (reproduzido exatamente).

Variantes: 25 rodadas (24 + baseline M5 já incluso) (7 tempos × períodos (a) iguais / (b) mesmo horizonte do M5 × validade 5 barras / ~25 min, deduplicando as idênticas). Log completo em `b2_tempos_graficos_stdout.log`. TTL foi variado setando `win_cinco_medias.TTL_BARRAS` dentro do processo (arquivo base intacto). Em 2/3/10/15/30 min a validade 5 barras e a de ~25 min deram resultado idêntico (o fill acontece na barra seguinte); só o M1 muda (R$ −5 a +7).

| tempo | períodos | líquido | janelas+ | pior | PF | trades | DD | sem set | meses melhores |
|---|---|---|---|---|---|---|---|---|---|
| M5 base | 9/21/34/100/200 | 7.490,10 | 11/14 | −272,30 | 1,54 | 413 | 794,70 | 6.782,60 | — |
| M15 (b) | 3/7/11/33/67, saída EMA7 | 7.496,60 | 12/14 | −315,00 | 1,57 | 314 | 757,50 | 6.608,60 | 8/14 |
| M30 (b) | 2/4/6/17/33, saída EMA4 | 7.349,90 | 12/14 | −117,00 | 1,63 | 241 | 781,50 | 6.896,40 | 7/14 |
| M10 (a) | 9/21/34/100/200 | 7.424,70 | 10/14 | −301,20 | 1,63 | 251 | 947,50 | 6.735,20 | 8/14 |
| M10 (b) | 4/10/17/50/100 | 7.004,10 | 11/14 | −372,50 | 1,50 | 359 | 859,00 | 6.299,10 | 7/14 |
| M3 (a) | iguais | 7.067,40 | 10/14 | −328,10 | 1,39 | 702 | 1.270,00 | 6.527,40 | 5/14 |
| M3 (b) | 15/35/57/167/333 | 6.495,30 | 10/14 | −866,60 | 1,42 | 495 | 1.240,90 | 5.613,80 | 6/14 |
| M2 (a) | iguais | 5.864,30 | 9/14 | −238,80 | 1,26 | 1063 | 1.013,50 | 4.896,30 | 6/14 |
| M2 (b) | 22/52/85/250/500 | 6.197,90 | 10/14 | −667,30 | 1,39 | 543 | 1.013,70 | 5.412,90 | 6/14 |
| M1 (a) | iguais | 112,00 | 8/14 | −922,40 | 1,00 | 2110 | 1.478,60 | −152,50 | 2/14 |
| M1 (b) | 45/105/170/500/1000 | 5.869,20 | 9/14 | −630,80 | 1,34 | 662 | 1.002,50 | 5.419,20 | 4/14 |
| M15 (a) | iguais | 5.655,10 | 11/14 | −928,70 | 1,49 | 195 | 1.538,00 | 5.108,60 | 8/14 |
| M30 (a) | iguais | 6.068,00 | 9/14 | −1.061,30 | 1,55 | 134 | 1.470,20 | 5.656,00 | 8/14 |

## Leitura
- Nenhuma variante domina o M5 em todos os critérios. Tempos abaixo de 5 min pioram (M1 com períodos iguais zera: PF 1,00).
- Platô no eixo "mesmo horizonte de tempo": M5 7.490, M10 7.004, M15 7.497, M30 7.350 — vizinhos todos bons (10 a 30 min). Ou seja, o que importa é o horizonte das médias em minutos, não o tempo gráfico.
- Mantendo períodos fixos, tempo maior piora o pior mês e o DD (médias mais lentas no relógio), exceto M10 que fica quase igual no líquido.
- Ressalva: M15/M30 (b) usam períodos de 2-7 barras (EMA4, EMA7 de saída); a ordenação 9>21>... com 2/4/6 é frágil e a amostra de trades é menor (241-314). Escolhidos sobre os mesmos 9 meses, sem validação.

## Candidatas congeladas (não substituem a atual de forma clara; melhoram risco)
1. **C1 = M15 (b):** `rodar_janelas(2026, "15min", periodos=(3,7,11,33,67), ema_saida=7)`, TTL_BARRAS=5 (2 dá idêntico). Líquido +6,50 vs base, 12/14, DD −37, mas pior −315 (pior) e sem set −174.
2. **C2 = M30 (b):** `rodar_janelas(2026, "30min", periodos=(2,4,6,17,33), ema_saida=4)`, TTL_BARRAS=5 (1 idêntico). Pior mês −117 (vs −272), 12/14, PF 1,63, sem set +114, DD −13; líquido −140.
3. **C3 = M10 (a):** `rodar_janelas(2026, "10min")` (períodos 9/21/34/100/200, TTL 5). −65 de líquido, PF 1,63, 8/14 meses melhores, mas 10/14 e DD pior (947) — fraca, só como vizinha do platô.

Veredito: nenhuma supera a atual em todos os critérios; C2 e C1 são alternativas de menor risco/menos trades (menos custo de execução). Item 3 (médias em M15, execução em M5) não foi feito.
