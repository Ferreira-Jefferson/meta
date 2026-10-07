# WIN — pré-pregão, pregão e pós-pregão: o que impacta o pregão

Janela: 127 pregões, 06/04/2026 a 05/10/2026 (`data/win_fases_pregao_6m.csv`, ticks do WIN$N). Seis lentes independentes, cada uma com nulo por permutação, correção de Benjamini-Hochberg e divisão em metades (abr–jun × jul–out). Detalhes e scripts em `lente1_*` … `lente6_*`.

Poder estatístico (lente 4): com n ≈ 120 e ~100 testes por lente, só |ρ| ≥ ~0,30 sobrevive à correção. Abaixo disso, o que aparece é hipótese.

## Direção e variação do pregão

Nenhuma variável operável sobreviveu à correção em nenhuma lente. A mesma pista apareceu em todas:

| Pista | Efeito | Status |
|---|---|---|
| Gap da noite (leilão D − call D−1) → pregão reverte o gap | ρ −0,18 a −0,23; gap ↑: pregão −491 pts em média, 34% de dias de alta; gap ↓: +264 pts, 54% de dias de alta | mesmo sinal nas duas metades; q 0,23–0,44 |
| 1ª barra M5 fechada CONTRA o gap → o resto do pregão continua nessa direção | +707 pts em média (~R$141/contrato), 62% dos dias, n = 66 | q 0,024–0,030, estável (lente 3) |
| 1ª barra M5 a favor do gap | sem continuação; tende a reverter por volta da 6ª barra (−445 pts) | q 0,09 |
| Últimos 30 min de D−1 → primeiras barras M5 de D | ρ −0,24 (reversão) | q_cons 0,27 |
| Pregão D−1 fechando perto da máxima → gap D negativo | ρ −0,26 | q_cons 0,27 |

O call de D−1 sozinho, o pregão de D−1, a concordância entre o call e o gap, e as razões contra o estágio anterior não acrescentam nada além do gap.

## Amplitude e volume do pregão

| Pista | Efeito | Status |
|---|---|---|
| Volume do call D−1 alto → amplitude de D menor | ρ −0,23 a −0,28; resiste a controlar pela amplitude de D−1 | estável; q 0,04–0,22 conforme a lente |
| Volume e negócios de D−1 → volume de D | ρ 0,3–0,8 | persistência de nível ou regime, não relação entre fases |
| Range/volume da 1ª hora → amplitude restante após 10:00 | ρ ~0,2–0,25 | q 0,08–0,15 |

## Mecânico (passa na correção, mas sai por construção)

- Gap grande demora mais a fechar e fecha menos vezes no dia. Por tercil do gap, fecha 86% / 81% / 57% dos dias. No tercil maior, a mediana até fechar é 35 min.
- Δ% contra o dia anterior gera reversão mecânica (ρ ≈ −0,47 no nulo).
- As razões pregão/pré e pós/pregão do mesmo dia são circulares.

## Dados

- Trocas de contrato no WIN$N em 15/04, 17/06 e 12/08 (degrau de ~3.500–4.200 pts no gap).
- O gap de 05/10 (+17.775 pts) é real: foi o dia seguinte ao 1º turno da eleição.
- 31/07 abriu às 12:34 (evento real).
- 24/09, 06/05 e 10/08 têm lacunas de ticks na fonte.
- Lista completa: `lente4_cetica_integridade/dias_flag.csv`.
- As bases M1 do WIN colocam os dois leilões nas barras extremas do dia: a 1ª barra traz o leilão de abertura e a barra das 18:24 traz o call. A auditoria dos estudos antigos afetados está em `auditoria_leiloes/`.

## Para dar o próximo passo

Gap e 1ª barra M5 são as duas pistas que se repetem. Confirmá-las exige dado que não foi usado aqui: ticks do WIN$N existem a partir de 20/02/2026, e as bases M1 cobrem 2022–2025. Usar esse dado gasta essa base como fora da amostra, e a decisão é do dono.
