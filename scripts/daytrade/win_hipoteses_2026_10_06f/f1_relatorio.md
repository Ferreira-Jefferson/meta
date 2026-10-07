# F1 — Padrões de candle como filtro/saída da WinCincoMedias v2.02 (WIN M30, só 2026)

Baseline reproduzido: +R$8.377,14 · 13/14 janelas · pior −117,00 · PF 1,77 · 248 trades · DD 781,50 · sem setembro 7.785,61.
A cópia de `simula` (gancho `saida_extra`) reproduz o baseline exato.

## Variantes testadas: 123
- 103 na grade principal: 74 filtros de entrada (marubozu, pavio de rejeição, engolfo, martelo/estrela, sequência de N velas, doji, inside, outside, vela grande/pequena vs ATR; modos exige/veta; janela de 1–3 velas) e 29 saídas por padrão contra.
- 20 na malha fina da melhor saída (pavio × range mínimo em ATR).
- Controle de acaso: 10 sementes por variante (30 na malha fina). Filtro de entrada aleatório corta a mesma fração dos sinais; saída aleatória dispara na mesma frequência por barra.

## Filtros de entrada: nenhum passa
Nenhum dos 74 filtros de entrada supera o baseline no conjunto. O melhor líquido é `veta_pequena0.75` (+141, mas pior −171, DD 815, 8 meses melhores contra 6 piores, 191 trades). `veta_pavio_contra0.5` em 3 velas dá PF 2,14 e DD 602, mas perde 4 janelas positivas e o líquido cai. A maioria empata com o aleatório ou fica abaixo. Padrões de candle como filtro só "operam menos".

## Saídas: pavio de rejeição contra a posição, em vela grande
Vela fechada com pavio contra >= X do range e range >= K·ATR(14 anterior) leva a saída na abertura seguinte.

| variante (X, K) | líquido | janelas+ | pior | trades | PF | DD | sem set | meses +/− | percentil vs aleatório |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 8.377,14 | 13/14 | −117,00 | 248 | 1,77 | 781,50 | 7.785,61 | — | — |
| **pavio 0,5 · 1,0** | **9.247,60** | 13/14 | **−3,50** | 262 | 1,90 | 781,50 | 8.438,60 | 9/3 | 100 (30 sem.) |
| pavio 0,6 · 0,75 | 9.053,78 | 13/14 | −46,80 | 261 | 1,88 | 781,50 | 8.249,75 | 10/3 | 100 |
| pavio 0,6 · 1,0 | 9.067,48 | 13/14 | −3,50 | 254 | 1,88 | 781,50 | 8.263,45 | 9/2 | 96,7 |
| pavio 0,4 · 1,0 | 8.929,56 | 13/14 | −61,00 | 276 | 1,83 | 781,50 | 8.120,56 | 9/3 | 96,7 |

Platô: X de 0,4 a 0,6 combinado com K de 0,75 a 1,5 dá +8.8k a +9.25k em quase todas as células (+5% a +10%). Acima de X=0,7 o efeito some (praticamente não dispara). Com K<=0,5 também some (opera a maioria das velas e perde edge). Resultado de aleatório de 30 sementes: percentil 96,7–100 nas células centrais.

Ressalvas:
- Ganho modesto (+R$870 do líquido, +10%), DD igual (781,50 é a janela de agosto, que a saída não mexe).
- Intensidade baixa: a saída dispara em ~2–7% das barras; poucas trades mudam. Em 14 janelas, 9 melhoram e 3 pioram.
- Os trades continuam em 262, acima do limite de 150.
- Efeito concentrado em poucos eventos por mês; vale confirmar nos blocos de validação antes de qualquer conclusão.
- Marubozu contra 0,7 (K=1) melhora +267 só em 3 meses (0 pioram): fragilidade de amostra, não congelado. Engolfo contra, martelo/estrela contra e sequência contra não melhoram (percentil ≤80).

## Candidatas congeladas (`f1_candidatas.py`)
1. `saida_pavio0.5_rng1.0` (centro do platô)
2. `saida_pavio0.6_rng0.75` (vizinho do platô)
Nenhum filtro de entrada por candle foi congelado.
