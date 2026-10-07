# CONGELADO — win_deslocamento_matinal (escrito DEPOIS da IS e ANTES de abrir a OOS)

## Configuração final (a canônica do PRE_REGISTRO — foi elegível de edge e de platô, então fica)
- WIN@, decisão aos 90 min de pregão (10:30 BRT), ATR14 diário (média de 14 true ranges até D-1)
- `desloc_min_atr = 0,3`, banda 0,05 ATR, **stop = linha da abertura (± banda), sem teto**, **sem alvo** (sai no achatamento do motor)
- entrada `EnterLimit` no último preço, `ttl_bars=15` (M1), 1 contrato, `anchor_exits_at_fill=True`, `target_fills_as_maker=True`
- `escala_volume = False` (a ablação NÃO foi adotada: na célula canônica o efeito é 0,0% — sem alvo e com stop na linha não há distância a escalar —; melhorou em 5 de 12 células, em nenhuma das exigidas: +20% E 2 de 3 anos E 60% das células)
- premissas de fila P0 = 0/0, P1 = 38.000/38.000, P2 = 76.000/76.000 (múltiplos de V̄ = 38.152 de volume M1; WIN NÃO calibrado). Aceitação decidida em P2.
- Capital real: R$250 (= 100 × 2,0 × 1,25). Corrida nominal (capital reposto) só como diagnóstico de edge.

## Resultado na IS (2021-10-01..2024-12-31; 804 pregões, os 15 primeiros sem ATR) — corrida NOMINAL
| premissa | sinais | trades | líquido R$ | R$/op | IC95% R$/op (bootstrap por pregão) | win% | breakeven empírico | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|---|---|---|
| P0 | 150 | 149 | +5.027,50 | +33,74 | [+3,4 ; +64,4] | 55,0% | 44,1% | +1.327,50 | +2.043,00 | +1.514,50 |
| P1 | 150 | 149 | +5.027,50 | +33,74 | [+3,4 ; +64,4] | 55,0% | 44,1% | idem | idem | idem |
| **P2** | 150 | 143 | **+4.144,50** | **+28,98** | **[−1,9 ; +60,4]** | 53,8% | 44,5% | +750,50 | +1.958,50 | +1.293,00 |
Saídas (P2): 105 achatamento do motor (disparou: última saída 18:20 BRT, nenhuma posição ficou aberta), 38 stops. Atraso realizado da entrada: 0 min (fill na barra seguinte) em p50 e p90.
Platô de P2: vizinhos X0,5/stop linha/sem alvo +2.152,50; stop 0,25 ATR/sem alvo +2.289,50; stop linha/alvo 0,30 +1.266,50 — 3 de 3 positivos.
Sinais por ano: ~46/ano (estudo: 35–55) — a implementação reproduz o achado.

## Censura pelo caixa real (a parte que decide o veredito de "ganha no real")
- Caminhada de caixa R$250 sobre os trades de P2: 25 operações executadas de 143; 118 sinais perdidos; caixa mínimo R$57,50; **probabilidade de travar embaralhando os trades: 66%**; capital que a IS CRONOLÓGICA teria exigido para nunca cair abaixo da margem crua: **R$1.260,50**.
- **Motor com capital REAL R$250** (conferência, célula canônica): P0 31 trades, **ZERADO em 2022-04-29** (líquido −R$141,50); P1 idem; P2 24 trades, **ZERADO em 2022-04-19** (−R$137,00). O stop da linha vale em média R$182 (0,35–0,5 ATR) num caixa de R$250.
- Nenhuma das 12 células da grade é elegível COMPLETA (nenhuma passa o critério (c) de censura). A menos exigente em capital que ainda é elegível de edge é X0,3/stop 0,15 ATR/sem alvo (exigiria R$849 na IS cronológica, trava 69%).

## Previsão de faixa para a OOS (2025-01-01..2026-09-30, escrita ANTES de rodar)
- Sinais ≈ 46/ano × 1,75 ano ≈ **75–85**; trades ≈ 72–82 (P2).
- R$/op em P2: valor central **+R$15** (metade do +R$29 da IS: encolho pela seleção e porque a pista veio em parte da OOS visto o descritivo); faixa plausível 80% **[−R$12 ; +R$43]** por operação (sd por trade ≈ R$190, erro-padrão ≈ R$21).
- Líquido P2 na corrida nominal: central ≈ +R$1.200; faixa 80% **[−R$950 ; +R$3.350]**. Chance de OOS negativa em P2: ~25–30%. Esperado: positiva em P0 e P1 com mais folga que em P2 (diferença P0→P2 na IS: −R$883).
- Capital real R$250: espero ZERADO de novo (probabilidade de travar ≈ 66% só pela sequência); a OOS com capital real não é veredito de edge.
- Critério de ACEITE (PRE_REGISTRO): positiva em P2 na OOS **e** não censurada. Pelo desenho acima, o aceite "completo" já não é esperado; o que a OOS responde é se o EDGE persiste.
