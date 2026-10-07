# Z4 — WinRetanguloEma34 M15 ajustado: a quebra de 2024 e os filtros de entrada

**Veredito: os quatro filtros foram REFUTADOS.** Todos evitam a quebra de 2024, mas cada um melhora só 2 dos 4 anos de conferência: sempre 2022 e 2023, nunca 2025 e 2026. Nenhum total ficou acima do p95 do sorteio. O mais perto foi o f3, no percentil 94,6.

## Onde está a perda de 2024

Detalhes em `diagnostico.md`.

- **Entradas decididas de manhã.** Antes das 12:00, 2024 tem 73 operações e −R$1.231. A partir das 12:00, tem 62 operações e +R$170. A faixa das 9:30–9:59 sozinha dá 23 operações, −R$969 e 10% de acerto.
- **O pior é a manhã com o dia parado.** Com amplitude do pregão abaixo de 0,5 ATR D1 até a decisão, a soma é −R$1.147.
- **A perda vem de stop rápido.** São 69 stops contra 27 alvos. Dos 40 stops em até 20 minutos, 34 foram decididos de manhã.
- **2024 foi o ano mais calmo da base** (faixa diária de 1.599 pts, contra 1.835–2.194). A conta quebra em agosto; a perda se forma em julho, com 24 operações e −R$552 no mês de menor faixa.
- **O padrão da manhã não se repete nos outros anos.** O resultado da manhã é −1.541 em 2022, −1.152 em 2023, −1.231 em 2024, **+1.205 em 2025** e **+2.137 em 2026**.

## Filtros pré-registrados

Arquivo `filtros.py`, SHA-256 `c339089992cbf87bb7af0302360b0ab5349a02d2cac4c7fb4b86f9857aa3e081`. Os valores foram escolhidos só em 2024.

| filtro | regra (ao armar a entrada) |
|---|---|
| f1 | não arma com decisão antes das 10:00 |
| f2 | não arma com decisão antes das 12:00 |
| f3 | só arma se a amplitude do pregão até a decisão for ≥ 0,5 × ATR14 D1 |
| f4 | bloqueia só quando a decisão é antes das 12:00 **e** a amplitude é < 0,5 ATR D1 |

## Conferência: líquido com custo por ano (base oficial, com o tick das 18:30 em 2026)

| | 2022 | 2023 | 2024 (criou) | 2025 | 2026 | total dos 4 de conferência | melhora | percentil | veredito |
|---|---|---|---|---|---|---|---|---|---|
| base | +70 (134) | −98 (137) | −1.061 (135), mín −230 QUEBRA | +1.007 (105) | +1.470 (83) | +2.449 | — | — | — |
| f1 | +235 (127) | −359 (134) | −159 (128), mín 668 | +1.204 (100) | +790 (74) | +1.870 | 2/4 | 23,6 | REFUTADO |
| f2 | +1.111 (92) | +1.356 (87) | +272 (73), mín 927 | −13 (60) | −1.032 (47), mín −129 **QUEBRA** | +1.422 | 2/4 | 52,2 | REFUTADO |
| f3 | +1.024 (76) | +140 (88) | −23 (79), mín 723 | +507 (55) | +1.196 (50) | +2.867 | 2/4 | 94,6 (p95 +2.897) | REFUTADO |
| f4 | +1.028 (104) | +277 (105) | −148 (97), mín 622 | +328 (75) | +692 (63) | +2.325 | 2/4 | 72,8 | REFUTADO |

Os saldos mínimos e a tabela completa de cada filtro estão em `conferencia.md` e `conferencia.csv`.

Com a base sem o tick das 18:30, 2026 fica assim:

| | 2026 | total dos 4 | percentil |
|---|---|---|---|
| base | +1.954 (84) | +2.933 | — |
| f1 | +1.057 | +2.137 | 12,7 |
| f2 | −1.139, quebra | +1.315 | 37,2 |
| f3 | +1.170 | +2.841 | 88,5 |
| f4 | +560 | +2.193 | 53,2 |

O veredito é o mesmo nas duas versões.

## Leitura

- **Os filtros cortam um regime, não um defeito.** Em 2022–2024 a manhã e o dia parado perdem dinheiro; em 2025–2026 é justamente a manhã que paga. Por isso todos os filtros melhoram 2022 e 2023 e pioram 2025 e 2026.
- **O f3 é o único que melhora o total contra a base.** O ganho foi de +418 com o tick das 18:30 e de −92 sem ele. Mesmo assim falha no critério de ≥ 3 anos, e o percentil cai de 94,6 para 88,5 sem o tick das 18:30.
- **Evitar a quebra de 2024 sai barato com qualquer corte de operações.** Ao cortar 40–45% das entradas, a perda de 2024 encolhe por si só.

## Método

- `port_z4.py` é um wrapper com monkeypatch, sem editar o port da Y4b. Ele calcula o contexto no instante de armar a ordem (fim da vela M15 de decisão, só com barras já fechadas e pregões anteriores). Com filtro, a ordem não é armada e o EA tenta de novo na vela seguinte, então uma entrada removida pode liberar outra. Sem filtro, as linhas saem iguais às de `y4b/trades/rettf_M15_*.csv`.
- **Vela pós-pregão.** O WIN$N de 2026 tem 1 tick às 18:30 em 157 de 157 dias de tick real, e isso gera 156 velas M15 no histórico do detector. Em 2022–25 não há nenhuma, porque o M1 termina às 18:24. Em 2026, 60 das 83 operações vêm de retângulo com essa vela na janela ou na amplitude. Sem ela (`roda_z4.py <per> <filtro> sempos`), 2026 vai de +1.470 (83 operações) para +1.954 (84 operações), e 2022–2025 ficam idênticos. A quebra de 2024 não muda.
- **Sorteio aleatório:** feito sobre as linhas do CSV da base. Em cada ano, mantém ao acaso o mesmo número de operações que o filtro teve; 1.000 sorteios, semente 20261006; o total é a soma de 2022, 2023, 2025 e 2026.
- R$2/op e saldo recomeçando em R$1.000 a cada ano, sem parar a conta por saldo. 2025 vai de janeiro a setembro; 2026, de 02/01 a 05/10.
- Arquivos: `port_z4.py`, `roda_z4.py`, `comum.py`, `diagnostico.py`, `diagnostico.md`, `diag_tabelas.md`, `filtros.py`, `conferencia.py`, `conferencia.md`, `conferencia.csv`, `conferencia.log` e `trades/`.
