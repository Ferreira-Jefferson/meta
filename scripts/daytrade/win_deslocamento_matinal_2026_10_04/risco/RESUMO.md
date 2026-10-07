# Teto de stop em R$ ligado ao caixa -- win_deslocamento_matinal (WIN@, P2, capital R$1.000 continuo, 1 contrato)

Teto lido de `on_capital_update` (capital + PnL realizado) e do caixa na 1a barra do pregao anterior (lucro do pregao anterior = caixa hoje - caixa no inicio do pregao anterior; 0 se nao operou). Sem look-ahead; log por sinal em `saida_risco.json` conferido (ex.: 2021-11-04 caixa 1000 -> teto 50; 2021-11-17 caixa 1364,5 -> teto 68,23; 2022-02-03 prev 246,5, caixa 1096 -> MAX 123,25 / MIN 54,8).
APERTAR: stop = floor(teto/0,20/5)*5 pts (min 10 pts). PULAR: nao opera se o stop da linha > teto. Script `run_risco.py`, tabela completa `risco.csv`.

Janelas: IS 2021-10..2024-12 (150 sinais), OOS 2025-01..2026-09 (118 sinais). Baseline de capital reposto (nominal): IS 143 / +4.144,50; OOS 113 / +4.897,50.

| IS | trades | pulados | liq R$ | cap final | R$/op | acerto | ganho | perda | payoff | stops | MaxDD R$ | MaxDD % | FR | seq perdas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BASE (sem teto) | 30 | 0 | -955 | 45 | -31,8 | 40,0 | 148 | 152 | 1,0 | 10 | 1.479 | 97,0 | -0,6 | 5 |
| T5 APERTAR | 143 | 0 | +2.944 | 3.944 | 20,6 | 39,9 | 184 | 88 | 2,1 | 77 | 1.215 | 53,8 | 2,4 | 10 |
| T5_MAX APERTAR | 143 | 0 | +2.939 | 3.939 | 20,5 | 39,9 | 184 | 88 | 2,1 | 77 | 1.206 | 57,1 | 2,4 | 10 |
| T5_MIN APERTAR | 143 | 0 | +2.942 | 3.942 | 20,6 | 39,2 | 185 | 85 | 2,2 | 79 | 1.062 | 53,8 | 2,8 | 10 |
| T3 APERTAR | 143 | 0 | +2.428 | 3.428 | 17,0 | 26,6 | 199 | 49 | 4,1 | 103 | 784 | 60,4 | 3,1 | 25 |
| T10 APERTAR | 143 | 0 | +3.022 | 4.022 | 21,1 | 46,9 | 174 | 113 | 1,5 | 57 | 1.181 | 74,2 | 2,6 | 10 |
| T15 APERTAR | 143 | 0 | +4.741 | 5.741 | 33,2 | 53,1 | 175 | 127 | 1,4 | 43 | 1.235 | 72,9 | 3,8 | 5 |
| T20 APERTAR | 143 | 0 | +4.671 | 5.671 | 32,7 | 53,1 | 175 | 128 | 1,4 | 39 | 1.203 | 75,6 | 3,9 | 5 |
| T5 / T5_MAX / T5_MIN / T3 PULAR | 0 | 150 | 0 | 1.000 | - | - | - | - | - | - | - | - | - | - |
| T10 PULAR | 1 | 149 | -102 | 899 | -101,5 | 0 | - | 102 | - | 1 | 102 | 10,2 | - | 1 |
| T15 PULAR | 3 | 146 | -361 | 640 | -120 | 0 | - | 120 | - | 3 | 361 | 36,0 | - | 3 |
| T20 PULAR | 11 | 138 | -552 | 449 | -50 | 45,5 | 66 | 147 | 0,5 | 6 | 642 | 58,9 | -0,9 | 3 |

BASE IS: o caixa de R$1.000 morre em 2022-05 (cap final R$45); 113 sinais recusados por capital (censurada) -- mede o portao de capital, nao a estrategia.

| OOS | trades | pulados | liq R$ | cap final | R$/op | acerto | ganho | perda | payoff | stops | MaxDD R$ | MaxDD % | FR | seq perdas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BASE (sem teto) | 113 | 0 | +4.898 | 5.898 | 43,3 | 52,2 | 254 | 187 | 1,4 | 25 | 1.294 | 40,9 | 3,8 | 5 |
| T5 APERTAR | 113 | 0 | +3.451 | 4.451 | 30,5 | 35,4 | 266 | 98 | 2,7 | 69 | 961 | 45,5 | 3,6 | 8 |
| T5_MAX APERTAR | 113 | 0 | +3.435 | 4.435 | 30,4 | 35,4 | 266 | 98 | 2,7 | 68 | 961 | 45,5 | 3,6 | 8 |
| T5_MIN APERTAR | 113 | 0 | +3.503 | 4.503 | 31,0 | 35,4 | 266 | 98 | 2,7 | 69 | 961 | 45,5 | 3,6 | 8 |
| T3 APERTAR | 113 | 0 | +3.571 | 4.571 | 31,6 | 25,7 | 309 | 64 | 4,8 | 84 | 980 | 34,1 | 3,6 | 11 |
| T10 APERTAR | 113 | 0 | +5.268 | 6.268 | 46,6 | 52,2 | 254 | 180 | 1,4 | 29 | 1.268 | 41,0 | 4,2 | 5 |
| T15 APERTAR | 113 | 0 | +4.750 | 5.750 | 42,0 | 52,2 | 254 | 189 | 1,3 | 27 | 1.492 | 41,6 | 3,2 | 5 |
| T20 APERTAR | 113 | 0 | +4.898 | 5.898 | 43,3 | 52,2 | 254 | 187 | 1,4 | 25 | 1.294 | 40,9 | 3,8 | 5 |
| T5 / T5_MAX / T5_MIN / T3 / T10 PULAR | 0 | 118 | 0 | 1.000 | - | - | - | - | - | - | - | - | - | - |
| T15 PULAR | 1 | 117 | -150 | 851 | -149,5 | 0 | - | 150 | - | 1 | 150 | 15,0 | - | 1 |
| T20 PULAR | 65 | 50 | +106 | 1.106 | 1,6 | 47,7 | 175 | 157 | 1,1 | 18 | 1.358 | 55,1 | 0,1 | 6 |

Liquido por ano (P2): ver coluna `anos` em `risco.csv` (ex. IS T5 APERTAR: 2021 -2 / 2022 +512 / 2023 +1.444 / 2024 +991; OOS: 2025 +608 / 2026 +2.842; BASE OOS: 2025 +978 / 2026 +3.920).
Nenhuma celula teve pregao parado por caixa (apenas BASE IS, por ordens recusadas) e nenhuma quebrou (wiped=False).

## Por que cada forma ganha ou perde
- PULAR: o stop da linha custa R$140-360 (mediana ~R$190); um teto de 3-10% de R$1.000 (R$30-100) nunca o comporta -> o robo nunca opera. So' com 20% (R$200+) opera algo, e as operacoes que passam sao so' as de stop curto (linha perto), que no IS/OOS dao R$/op ~ 0 ou negativo.
- APERTAR: o stop vira R$50-130 (3-5x mais curto que a linha): vira "loteria de stops" (acerto 40% IS / 35% OOS contra 52% da base, 69-77 stops contra 25), mas o payoff sobe (2,1-2,7) e como e' R$/op menor que a base (OOS 30,5 vs 43,3) o que ele compra e' sobrevivencia: no IS e' a unica forma de nao zerar o caixa de R$1.000 (BASE morre; 143 trades +R$2.944). Quando o teto cresce com o caixa (T10-T20) volta a ser quase a base (T20 OOS == BASE).
- T5_MAX / T5_MIN: igual a T5 (diferenca < 1%): a metade do lucro anterior raramente passa de 5% do caixa por tanto tempo para mexer no teto; a regra de "50% do lucro de ontem" e' praticamente inerte.
- Sensibilidade: IS melhora com % maior (R$/op 17 -> 21 -> 33); OOS o ponto otimo e' T10 (R$/op 46,6 > base 43,3); sem tendencia monotona, e a diferenca T10 vs BASE no OOS e' pequena e dentro do ruido.

## Veredito
Com R$1.000 e 1 contrato a regra literal do dono (5%, R$50) so' e' executavel como APERTAR; PULAR zera a estrategia (nunca opera). APERTAR T5 e' a unica forma de sobreviver no IS (BASE perde 95% do caixa e fica sem operar em 2022), ao custo de ~30% do R$/op e acerto de 35-40% (stops de R$50 ~ 250 pts, o robo e' parado por ruido de minutos); as variantes MAX/MIN com a metade do lucro do dia anterior nao mudam nada. Cuidado: IS compoe a partir de um 1o trade +R$364 (sorte de trajetoria) e MaxDD de 54%/45% do caixa continua alto -- os 5% por operacao nao limitam o drawdown, so' a perda unitaria.
