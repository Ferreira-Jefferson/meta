# Z4 — Diagnóstico: por que o WinRetanguloEma34 M15 ajustado quebra em 2024

Base: RetTF M15 (`port_ret_tf_v2.py`, tf=15, ajustes=True), 1 contrato, R$2/op, saldo recomeçando em R$1.000 a cada ano. As operações são reproduzidas pelo wrapper `port_z4.py`, que dá linhas iguais às de `y4b/trades/rettf_M15_*.csv` e acrescenta o contexto conhecido no instante em que a ordem-limite é armada (fim da vela M15 de decisão). As tabelas completas estão em `diag_tabelas.md` (gerado por `diagnostico.py`), e as operações enriquecidas em `trades/base_enriquecido.csv`.

## Onde está a perda

1. **A perda de 2024 está nas entradas decididas de manhã.** Com decisão antes das 12:00, 2024 tem 73 operações e −R$1.231. Com decisão a partir das 12:00, tem 62 operações e +R$170. Só as decisões das 9:30–9:59 somam 23 operações, −R$969 e 10% de acerto.
2. **O pior é a manhã em que o dia ainda não andou.** Com decisão antes das 12:00 e amplitude do pregão até a decisão abaixo de ~0,5 ATR D1, a soma é −R$1.147. O resto do ano soma +R$86.
3. **O tipo de perda é o stop rápido.** 2024 tem 69 stops e só 27 alvos (36% de acerto, contra 46% nos outros anos). Das 40 operações com stop em até 20 minutos, 34 foram decididas de manhã.
4. **2024 foi o ano de menor volatilidade da base:** faixa diária média de 1.599 pts, contra 1.835–2.194 em 2022–2025, e ATR D1 mediano de 1.676 pts. Os retângulos ficaram mais estreitos (mediana de 575 pts) e o stop também (mediana de 259 pts). O prejuízo vem de junho a agosto: −R$957 em três meses, dos quais julho sozinho dá −R$552 em 24 operações, com 25% de acerto e a menor faixa diária do ano (1.221 pts).
5. Na manhã, o retângulo usa velas do pregão anterior (ajuste A da Y4b). A janela de 20 velas M15 cobre 5 horas, então até ~14:15 ela atravessa a noite.

## Por ano

| ano | ops | líquido | acerto % | saldo mín | quebra |
|---|---|---|---|---|---|
| 2022 | 134 | +70 | 41,8 | 899 | não |
| 2023 | 137 | −98 | 45,3 | 357 | não |
| 2024 | 135 | −1.061 | 36,3 | −230 | **sim** |
| 2025 | 105 | +1.007 | 48,6 | 238 | não |
| 2026 | 83 | +1.470 | 48,2 | 217 | não |

## Cortes: 2024 contra os outros anos (n · R$/op · acerto %)

Os cortes contínuos usam quartis de todos os anos juntos.

| corte | faixa | 2024 | outros anos |
|---|---|---|---|
| hora do preenchimento | 9h | 11 · −49,6 · 9 | 38 · +1,5 · 39 |
| | 10h | 39 · −10,3 · 31 | 100 · +3,5 · 37 |
| | 11h | 16 · −12,0 · 31 | 73 · −1,3 · 41 |
| | 12–16h | 69 · +1,1 · 45 | 248 · +8,6 · 51 |
| lado | compra | 67 · −5,7 · 37 | 218 · +7,3 · 47 |
| | venda | 68 · −10,0 · 35 | 241 · +3,5 · 44 |
| largura (pts) | ≤546 | 56 · −7,0 · 34 | 96 · −9,2 · 33 |
| | 546–686 | 46 · −10,6 · 33 | 99 · +4,5 · 44 |
| | 686–870 | 28 · −11,2 · 36 | 120 · +4,3 · 48 |
| | >870 | 5 · +25,8 · 100 | 144 · +16,5 · 53 |
| largura / ATR M15 | quartis 1→4 | −9,7 · −2,4 · −8,4 · −10,7 | +7,5 · +11,4 · +6,1 · −3,5 |
| largura / ATR D1 | quartis 1→4 | −18,4 · +7,2 · −21,8 · +4,5 | −6,3 · +8,6 · +2,3 · +17,3 |
| ATR D1 | ≤1.774 | 101 · −5,5 · 37 | 50 · −12,3 · 36 |
| | >1.774 | 34 · −14,8 · 35 | 409 · +7,5 · 46 |
| entrada vs variação do dia | a favor | 99 · −8,8 · 36 | 340 · +10,3 · 48 |
| | contra | 36 · −5,2 · 36 | 119 · −9,0 · 39 |
| entrada vs EMA34 H1 | a favor | 84 · −7,4 · 38 | 312 · +10,1 · 49 |
| | contra | 51 · −8,6 · 33 | 147 · −4,7 · 38 |
| distância à EMA34 M15 (ATR M15) | quartis 1→4 | −6,9 · −14,5 · −3,3 · −6,4 | +10,0 · −4,4 · +22,8 · −5,7 |
| amplitude do dia até a decisão (ATR D1) | quartis 1→4 | −16,4 · −18,3 · −4,0 · +5,1 | −6,4 · +1,6 · +7,1 · +19,4 |
| gap de abertura (ATR D1) | quartis 1→4 | −4,9 · −6,6 · −6,1 · −13,4 | +4,1 · +15,4 · −6,5 · +6,9 |
| motivo de saída | alvo / stop / zera | 27 · 91,1 / 69 · −57,9 / 39 · 12,2 | 122 · 129,2 / 201 · −77,6 / 136 · 16,7 |
| duração (min, conhecida só no fim) | ≤20 / 20–47 / 47–99 / >99 | −33,8 / −18,2 / +6,5 / +31,8 | −42,2 / +5,0 / +17,0 / +35,4 |

## Manhã contra tarde, ano a ano (decisão antes das 12:00 · a partir das 12:00; n, líquido)

| ano | manhã | tarde |
|---|---|---|
| 2022 | 57 · −1.541 | 77 · +1.611 |
| 2023 | 64 · −1.152 | 73 · +1.054 |
| 2024 | 73 · −1.231 | 62 · +170 |
| 2025 | 59 · +1.205 | 46 · −198 |
| 2026 | 47 · +2.137 | 36 · −667 |

O corte por hora **inverte de sinal em 2025 e 2026**. Ele aparece aqui porque a etapa 1 pede a comparação com os outros anos, e foi visto antes de escolher os filtros. Fica registrado para que a conferência não seja lida como surpresa.

O corte por amplitude do dia até a decisão é monotônico nos dois grupos. Os cortes por tendência do dia e por EMA34 H1 são negativos em 2024 dos dois lados e invertem entre os anos: no ano a ano, "a favor do dia" vale +6,5, −4,4, −8,8, +16,5 e +34,8. É o mesmo padrão da memória `win_retangulo_tendencia_elliott_borda_refutadas` (alinhamento com a tendência refutado por troca de sinal), por isso não vira filtro.

## Curva mensal de 2024

| mês | ops | líquido | acerto % | saldo no fim | faixa diária média | variação do mês (pts) |
|---|---|---|---|---|---|---|
| jan | 13 | −63 | 38 | 937 | 1.706 | −7.260 |
| fev | 13 | −175 | 31 | 762 | 1.573 | +2.315 |
| mar | 5 | −27 | 60 | 735 | 1.326 | −2.230 |
| abr | 11 | +62 | 45 | 797 | 1.788 | −1.540 |
| mai | 8 | +34 | 38 | 831 | 1.454 | −5.455 |
| jun | 12 | −190 | 25 | 641 | 1.647 | +2.390 |
| jul | 24 | −552 | 25 | 89 | **1.221** | +2.505 |
| ago | 7 | −215 | 14 | **−126** | 1.651 | +10.045 |
| set | 7 | +215 | 57 | 89 | 1.629 | −4.575 |
| out | 16 | −166 | 38 | −77 | 1.447 | −1.305 |
| nov | 8 | +34 | 63 | −43 | 1.868 | −5.450 |
| dez | 11 | −18 | 36 | −61 | 1.956 | −4.690 |

A conta quebra em agosto. A perda se forma em julho, o mês de menor faixa diária do ano, que teve o dobro das operações de um mês normal (24) e, só na manhã, −R$696. Agosto foi o mês de tendência mais forte (+10.045 pts, eficiência de 0,53) e teve só 1 acerto em 7.
