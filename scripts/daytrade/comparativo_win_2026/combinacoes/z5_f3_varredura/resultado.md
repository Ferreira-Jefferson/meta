# Z5 — Varredura do limite k do f3 (WinRetanguloEma34 M15 ajustado)

f3 parametrizado: só arma se a amplitude do pregão até a decisão ≥ k × ATR14 D1. `roda_z5.py` reaproveita `port_z4.py` da Z4 sem editá-lo. R$2/op; saldo recomeça em R$1.000 a cada ano (Q = quebra). Sorteio: mesma fração por ano sobre as linhas da base, 1.000 sorteios, semente 20261006. "Percentil (4 anos)" é o método da Z4 (sem 2024); o da Z4 deu 94,6 para k=0,5 na base oficial e aqui 94,2, só por outra sequência de sorteios.

## Leitura (regra pré-definida)

**Curva total dos 5 anos × k, base oficial:** k0 +1.388 · 0,2 +1.964 · 0,3 +1.547 · 0,4 +2.164 · **0,5 +2.844** · 0,6 +2.185 · 0,7 +1.076 · 0,8 +220 · 1,0 +697. Sem velas pós-pregão: +1.872 · +2.448 · +2.102 · +2.402 · **+2.818** · +2.178 · +1.076 · +220 · +697.

- **Platô ou pico?** É um morro largo com um degrau: k de 0,4 a 0,6 fica entre +2.164 e +2.844 (oficial) e +2.178 e +2.818 (sem pós), sempre acima da base; a partir de 0,7 a curva desaba (poucas operações: 109, 58, 21). Não é pico isolado, mas também não é plano: o 0,5 é ~30% acima dos vizinhos 0,4 e 0,6, e o 0,3 cai abaixo do 0,2 (curva não monótona). O PF sobe com k (1,07 → 1,35 em 0,7) porque o filtro corta operações.
- **Centro do platô:** k = 0,5 (centro de 0,4–0,6). Aqui o centro coincide com o pico; vale como centro, não como pico escolhido.
- **Percentil:** 0,5 é o único k da faixa 0,4–0,6 perto de p95 (oficial 97,7 nos 5 anos / 94,2 nos 4; sem pós 95,3 / 88,3). 0,4 e 0,6 ficam em 84–97 nos 5 anos e 81–92 nos 4. O 0,2 dá 100, mas corta só 4 operações: artefato (o filtro quase não corta nada e o sorteio de 4 operações é ruído).
- **A melhora é constante entre os anos? Não.** Todos os k de 0,2 a 0,6 melhoram 3 dos 5 anos (2022, 2023 e 2024 na maioria) e pioram 2025 e 2026. Variação por ano de k=0,5 contra k=0 (oficial): 2022 +954, 2023 +238, 2024 +1.038, 2025 −500, 2026 −274. Em k=0,4: +732, +61, +395, −166, −246; em k=0,6: +404, +137, +1.230, −21, −953. A melhora vem de 2022–2024 (anos em que o dia parado perde) e o filtro custa em 2025–26, como a Z4 já tinha visto. Só 2024 (a quebra) melhora em todos os k de 0,2 a 1,0. A 2023 só vira positiva a partir de k=0,5.
- **Quebra:** nenhum k > 0 quebra nenhum ano (a quebra de 2024 da base some já em k=0,2, com saldo mínimo 27; k≥0,3 mantém ≥ 180).

**k sugerido: 0,5** (centro do platô 0,4–0,6). Ressalvas: o ganho sobre a base (+1,4 mil nos 5 anos) vem de 2022–24 e é negativo em 2025–26; 2026 é o ano de ticks reais e o filtro rende menos ali que a base; nenhum k passa do p95 de forma robusta nas duas bases e nas duas contagens de anos.


Prova: k=0 reproduz a base e k=0,5 reproduz o f3 da Z4, nas duas bases (operações idênticas).

## Base oficial (com tick 18:30 em 2026)

| k | 2022: líq (ops) · saldo mín | 2023: líq (ops) · saldo mín | 2024: líq (ops) · saldo mín | 2025: líq (ops) · saldo mín | 2026: líq (ops) · saldo mín | total 5 anos | ops | PF | acerto % | anos que melhoram vs k=0 | quebra | percentil (5 anos) | percentil (4 anos, Z4) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | +70 (134) · 899 | -98 (137) · 357 | -1,061 (135) · -230 Q | +1,007 (105) · 238 | +1,470 (83) · 217 | +1,388 | 594 | 1.07 | 43.4 | 0/5 | 2024 | — | — |
| 0,2 | +393 (133) · 965 | -8 (136) · 447 | -804 (134) · 27 | +913 (104) · 238 | +1,470 (83) · 217 | +1,964 | 590 | 1.09 | 43.9 | 3/5 | não | 100.0 | 99.5 |
| 0,3 | +441 (126) · 965 | -221 (125) · 412 | -614 (127) · 217 | +1,069 (93) · 387 | +872 (79) · 263 | +1,547 | 550 | 1.08 | 44.2 | 3/5 | não | 68.2 | 40.5 |
| 0,4 | +802 (108) · 1,000 | -37 (109) · 665 | -666 (100) · 180 | +841 (80) · 334 | +1,224 (70) · 342 | +2,164 | 467 | 1.13 | 45.6 | 3/5 | não | 87.5 | 86.0 |
| 0,5 | +1,024 (76) · 1,000 | +140 (88) · 665 | -23 (79) · 723 | +507 (55) · 568 | +1,196 (50) · 385 | +2,844 | 348 | 1.25 | 47.7 | 3/5 | não | 97.7 | 94.2 |
| 0,6 | +474 (48) · 1,000 | +39 (52) · 758 | +169 (52) · 782 | +986 (37) · 826 | +517 (27) · 623 | +2,185 | 216 | 1.32 | 50.5 | 3/5 | não | 96.8 | 91.5 |
| 0,7 | -128 (25) · 858 | +462 (30) · 1,000 | +140 (17) · 868 | +642 (25) · 773 | -40 (12) · 601 | +1,076 | 109 | 1.35 | 53.2 | 2/5 | não | 81.5 | 72.9 |
| 0,8 | -261 (16) · 653 | +248 (15) · 961 | +68 (12) · 996 | +531 (9) · 1,000 | -366 (6) · 634 | +220 | 58 | 1.12 | 48.3 | 2/5 | não | 58.1 | 48.1 |
| 1,0 | +192 (4) · 1,000 | +175 (5) · 930 | +149 (5) · 996 | +331 (4) · 1,000 | -150 (3) · 796 | +697 | 21 | 2.92 | 66.7 | 3/5 | não | 95.6 | 87.8 |

## Base sem velas pós-pregão

| k | 2022: líq (ops) · saldo mín | 2023: líq (ops) · saldo mín | 2024: líq (ops) · saldo mín | 2025: líq (ops) · saldo mín | 2026: líq (ops) · saldo mín | total 5 anos | ops | PF | acerto % | anos que melhoram vs k=0 | quebra | percentil (5 anos) | percentil (4 anos, Z4) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | +70 (134) · 899 | -98 (137) · 357 | -1,061 (135) · -230 Q | +1,007 (105) · 238 | +1,954 (84) · 217 | +1,872 | 595 | 1.09 | 43.5 | 0/5 | 2024 | — | — |
| 0,2 | +393 (133) · 965 | -8 (136) · 447 | -804 (134) · 27 | +913 (104) · 238 | +1,954 (84) · 217 | +2,448 | 591 | 1.12 | 44.0 | 3/5 | não | 100.0 | 99.8 |
| 0,3 | +441 (126) · 965 | -221 (125) · 412 | -614 (127) · 217 | +1,069 (93) · 387 | +1,427 (79) · 263 | +2,102 | 550 | 1.11 | 44.4 | 3/5 | não | 73.7 | 47.9 |
| 0,4 | +802 (108) · 1,000 | -37 (109) · 665 | -666 (100) · 180 | +841 (80) · 334 | +1,462 (67) · 342 | +2,402 | 464 | 1.15 | 45.7 | 3/5 | não | 83.7 | 81.0 |
| 0,5 | +1,024 (76) · 1,000 | +140 (88) · 665 | -23 (79) · 723 | +507 (55) · 568 | +1,170 (48) · 385 | +2,818 | 346 | 1.25 | 47.4 | 3/5 | não | 95.3 | 88.3 |
| 0,6 | +474 (48) · 1,000 | +39 (52) · 758 | +169 (52) · 782 | +986 (37) · 826 | +510 (27) · 623 | +2,178 | 216 | 1.32 | 50.5 | 3/5 | não | 93.7 | 86.0 |
| 0,7 | -128 (25) · 858 | +462 (30) · 1,000 | +140 (17) · 868 | +642 (25) · 773 | -40 (12) · 601 | +1,076 | 109 | 1.35 | 53.2 | 2/5 | não | 80.7 | 72.6 |
| 0,8 | -261 (16) · 653 | +248 (15) · 961 | +68 (12) · 996 | +531 (9) · 1,000 | -366 (6) · 634 | +220 | 58 | 1.12 | 48.3 | 2/5 | não | 54.5 | 45.5 |
| 1,0 | +192 (4) · 1,000 | +175 (5) · 930 | +149 (5) · 996 | +331 (4) · 1,000 | -150 (3) · 796 | +697 | 21 | 2.92 | 66.7 | 3/5 | não | 95.3 | 88.8 |
