# Chave de pernadas do WIN: horário, volatilidade curta e pernada anterior são um sinal ou três?

Base: WINV26 M1, 21 pregões de setembro/2026 (agosto só aquece indicadores). Ferramenta: `rodada2/chave/kit_pernadas.py`; prova de causalidade: `test_kit.py` (passa). Saídas completas: `rodada2/chave/saida_analise_balanco.txt` e `saida_analise_extremo.txt`. Cerca de 590 células/modelos/chaves foram avaliados (294 por família), sem contar bootstraps.

## 1. Como o kit funciona

- `carregar_m1()` lê agosto+setembro; `reamostrar(m1, "M5"|"M15"|"H1")`.
- `estado_zigzag_m1(m1)` dá, para cada minuto, o estado do zigzag de 750 que um trader conheceria naquele minuto: direção, extremo corrente, recuo do extremo, tamanho da perna até o extremo, última perna completa, quanto o dia já andou.
- `features_m1(m1)` dá as features causais por minuto: hora, ATR5/ATR50 em M5 e M15 (`r_m5`, `r_m15`), vol M1 30/300, range do dia. Soma `rh_m5`/`rh_m15`: ATR5 dividido pela média do ATR5 no mesmo minuto dos 5 pregões anteriores, ou seja, a volatilidade curta sem o relógio.
- `eventos(...)` e `eventos_balanco(...)` geram os eventos "já andou X" com as features conhecidas ao abrir a vela TF. `rotular(...)` coloca o rótulo `y` olhando o futuro, em função separada.
- Dois tipos de evento:
  - **balanço** (igual à rodada 1): pivôs de zigzag de 100 pts; evento = o preço já andou X do último pivô; y = esse balanço chega a 750 antes de recuar 100 do seu extremo.
  - **extremo**: E é o extremo da pernada de 750 em curso; evento = o preço recuou X de E; y = o movimento contrário chega a 750 antes de E ser superado.
- `test_kit.py` prova a causalidade de quatro formas: truncar em t não muda a linha t (40 instantes); sobrescrever todo o futuro com lixo não muda a linha t (10 instantes); eventos e features são idênticos truncando no fim da vela do evento (25 por TF e tipo); o rótulo só existe em `rotular`.

## 2. Taxa-base P(750 | já andou X do último extremo) — tipo balanço

| TF | X | n | chegaram | taxa | IC95 (bootstrap por dia) |
|---|---|---|---|---|---|
| M5 | 150 | 2.184 | 157 | 7,2% | 6,1–8,3% |
| M5 | 250 | 1.486 | 157 | 10,6% | 8,9–12,2% |
| M5 | 375 | 861 | 157 | 18,2% | 15,6–20,8% |
| M5 | 500 | 482 | 157 | 32,6% | 28,6–36,6% |
| M15 | 150 | 958 | 208 | 21,7% | 19,0–24,5% |
| M15 | 250 | 783 | 208 | 26,6% | 23,8–29,3% |
| M15 | 375 | 567 | 208 | 36,7% | 33,7–40,0% |
| M15 | 500 | 409 | 208 | 50,9% | 46,3–55,3% |

Os valores de M5 reproduzem a rodada 1 (7,4 / 10,9 / 18,7 / 33,2%). Tipo extremo (recuo de X do extremo da pernada de 750): M5 27 / 33 / 45 / 60%; M15 30 / 35 / 42 / 50%. Esse número responde a outra pergunta: depois de recuar X do topo de uma pernada, ela vira de verdade?

## 3. Cada sinal sozinho e depois de fixar os outros — balanço, X=250

Sinais: P1 = hora; P2 = ATR5/ATR50 da própria TF (`r`); P3 = tamanho do balanço anterior (o que terminou no pivô).

| | M5 | M15 |
|---|---|---|
| P(750) por hora: <10 / 10–11 / 11–13 / ≥13 | 21 / 19 / 6 / 3% | 50 / 55 / 29 / 8% |
| P(750) por r: <0,9 / 0,9–1,2 / ≥1,2 | 5 / 7 / 16% | 15 / 18 / 43% |
| P(750) por r sem relógio (rh) | 11 / 9 / 12% | 22 / 28 / 29% |
| P(750) por balanço anterior: <300 / 300–750 / 750–1.500 / ≥1.500 | 9 / 11 / 18 / 44% (n=9) | 19 / 23 / 42 / 55% (n=22) |
| Correlação de postos hora~r | −0,78 | −0,61 |
| Correlação hora~balanço anterior / r~balanço anterior | −0,37 / +0,46 | −0,37 / +0,50 |
| Efeito marginal → dentro dos estratos dos outros dois, hora<11 | +15 → +17 pp | +37 → +28 pp |
| Efeito marginal → dentro dos estratos dos outros dois, r≥1,2 | +10 → **−3 pp** | +27 → +14 pp |
| Efeito marginal → dentro dos estratos dos outros dois, r sem relógio ≥1,2 | +3 → +3 pp | +3 → +5 pp |
| Efeito marginal → dentro dos estratos dos outros dois, balanço anterior ≥750 | +10 → +6 pp | +22 → +5 a +10 pp |
| AUC deixando um dia de fora: hora / r / rh / balanço | 0,735 / 0,660 / 0,501 / 0,445 | 0,778 / 0,686 / 0,483 / 0,602 |
| AUC: hora+rh+balanço / hora+r+balanço | 0,733 / 0,719 | 0,782 / 0,777 |

Replicação em X=375: os efeitos são os mesmos (M5 hora +17 → +20 pp, r ≥1,2 +9 → −6 pp; M15 hora +35 → +28 pp, r +27 → +16 pp). Logloss deixando um dia de fora: M5 base 0,337, hora 0,305, as três juntas 0,302–0,306.

**Leitura:** é um sinal só, o relógio, visto por três ângulos.
- P2 em bruto é em boa parte o relógio. O ATR50 cobre cerca de 4 horas e, de manhã, olha para a tarde anterior; por isso r alto coincide com a manhã (rho −0,78 em M5). Em M5, r some depois de fixar hora e balanço (−3 pp). Tirando o relógio (rh), a volatilidade subindo vale +3 a +5 pp e não acrescenta AUC.
- O que r ainda traz em M15 (+14 pp) é parcialmente o relógio de novo (rh dá só +5 pp).
- P3 acrescenta um resto pequeno e instável: +5 a +10 pp, amostra pequena nas faixas altas (n=9 e n=22 em ≥1.500), e é parcialmente colinear com r (0,46–0,50). Hora+balanço fica igual ou pior que hora sozinha no AUC.
- Em M15, o modelo com as três tem AUC 0,78, igual ao de hora sozinha.

**Tipo extremo (a pernada de 750 vira depois de recuar X do topo?):** os três sinais ficam planos. M5 X=250: P(750) por hora 34 / 33 / 29 / 37%; por r 30 / 34 / 35%; por balanço <1.000 a ≥2.500: 31 a 37%. Ligada vs desligada ≈ 34% vs 33%. Horário e volatilidade dizem onde há pernada nascendo; não dizem se uma pernada em curso vai virar.

## 4. A chave — balanço, X=250

"Tempo ligado" = fração dos minutos de pregão em que a chave está ON. "Capturadas" = fração dos eventos que viraram pernada de 750 e ocorreram com a chave ON. Lift = capturadas / tempo ligado (o acaso dá 1,0). Limiares em grade; nenhum escolhido como "o melhor".

**M5** (157 pernadas; base 10,6%)

| chave | tempo ligado | capturadas | lift | P(pernada) ON | P(pernada) OFF |
|---|---|---|---|---|---|
| hora<9:30 | 5% | 29% | 5,8 | 32% | 8% |
| hora<10 | 10% | 36% | 3,5 | 21% | 8% |
| hora<10:30 | 16% | 53% | 3,4 | 20% | 7% |
| hora<11 | 21% | 73% | 3,5 | 20% | 5% |
| hora<12 | 32% | 86% | 2,7 | 16% | 3% |
| hora<13 | 42% | 90% | 2,1 | 14% | 3% |
| hora<15 | 64% | 96% | 1,5 | 12% | 2% |
| r≥2,0 | 8% | 24% | 3,1 | 17% | 9% |
| r≥1,6 | 16% | 48% | 3,0 | 17% | 8% |
| r≥1,2 | 27% | 71% | 2,6 | 16% | 6% |
| r≥1,0 | 35% | 79% | 2,2 | 14% | 5% |
| rh≥1,4 (sem relógio) | 10% | 15% | 1,6 | 14% | 10% |
| rh≥1,2 (sem relógio) | 22% | 31% | 1,4 | 12% | 10% |
| rh≥1,0 (sem relógio) | 48% | 52% | 1,1 | 11% | 11% |
| OR hora<10 ou r≥2,0 | 13% | 47% | 3,6 | 21% | 7% |
| OR hora<11 ou r≥1,2 | 28% | 83% | 3,0 | 17% | 4% |
| AND hora<11 e r≥1,2 | 20% | 61% | 3,1 | 17% | 7% |

**M15** (208 pernadas; base 26,6%)

| chave | tempo ligado | capturadas | lift | P(pernada) ON | P(pernada) OFF |
|---|---|---|---|---|---|
| hora<9:30 | 5% | 17% | 3,4 | 65% | 24% |
| hora<10 | 10% | 26% | 2,6 | 50% | 23% |
| hora<11 | 21% | 58% | 2,8 | 52% | 16% |
| hora<12 | 32% | 77% | 2,5 | 48% | 11% |
| hora<13 | 42% | 87% | 2,1 | 41% | 8% |
| hora<15 | 64% | 95% | 1,5 | 34% | 6% |
| r≥2,0 | 3% | 7% | 2,8 | 58% | 25% |
| r≥1,4 | 19% | 46% | 2,5 | 49% | 19% |
| r≥1,2 | 28% | 62% | 2,2 | 43% | 16% |
| r≥1,0 | 41% | 73% | 1,8 | 36% | 15% |
| rh≥1,2 (sem relógio) | 23% | 27% | 1,2 | 29% | 26% |
| OR hora<10 ou r≥1,6 | 20% | 50% | 2,5 | 48% | 18% |
| OR hora<11 ou r≥1,2 | 35% | 83% | 2,3 | 46% | 9% |
| AND hora<11 e r≥1,2 | 14% | 37% | 2,7 | 51% | 21% |

A curva de troca é suave: cada ponto de tempo extra ligado compra menos pernadas (M5: 5% do tempo → 29%, 21% → 73%, 42% → 90%, 64% → 96%). O OR com volatilidade bruta não ultrapassa a chave de hora com o mesmo tempo ligado (M5 hora<11: 21% do tempo, 73% capturado; OR hora<11 ou r≥1,2: 28%, 83%; hora<12: 32%, 86%). A volatilidade sem relógio fica perto de 1,1–1,6 de lift. Os ICs não foram calculados para cada ponto da curva; os limiares são todos em amostra.

## 5. Limites

- 21 pregões: o tamanho efetivo é de dias, não de eventos (eventos de X diferentes e de TFs diferentes sobrepõem-se). O bootstrap por dia foi aplicado só às taxas-base.
- Faixas altas de P3 têm n=9 a 22.
- "Pernadas" aqui = eventos de balanço que chegam a 750 (157 em M5, 208 em M15); o número difere das 195/177 do zigzag direto por causa da definição de pivô.
- O tipo extremo mostra planicidade com n pequeno (261–417 eventos); não prova ausência de efeito.
- Os eventos usam features conhecidas na abertura da vela TF onde o recuo/avanço ocorre (conservador); um trader no minuto exato do evento teria mais informação do que a usada.
