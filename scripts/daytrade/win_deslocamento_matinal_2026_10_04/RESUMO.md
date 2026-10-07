# RESUMO — win_deslocamento_matinal (2026-10-04)

Estratégia: `src/strategy/daytrade/lab/win_deslocamento_matinal.py` (não registrada em produção). Teste: `tests/test_win_deslocamento_matinal.py` (11 testes, verdes).
Método: PRE_REGISTRO.md (antes de rodar) -> grade IS de 12 células x 3 premissas de fila -> CONGELADO.md (antes da OOS) -> OOS e WDO uma vez cada, sem retoque.

## A regra
Aos 90 min de pregão (10:30), se o preço está a >= 0,3 ATR14 da abertura e nunca fechou do outro lado dela (banda 0,05 ATR), entra A FAVOR com limite no último preço (prazo 15 min).
Stop = a linha da abertura (+/- 0,05 ATR), sem teto. Sem alvo: sai no achatamento do motor. 1 contrato, 1 operação/dia.
Mecanismo: dia que se afasta cedo da abertura é dia de fluxo direcional; a abertura é a linha de invalidação (78% dos dias assim não a cruzam mais; +0,10 ATR a favor até o fecho).

## Resultado (corrida NOMINAL = capital reposto por pregão; diagnóstico de edge). WIN, célula congelada
| janela | premissa de fila | sinais | trades | líquido R$ | R$/op | IC95% R$/op | win% | breakeven emp. | por ano |
|---|---|---|---|---|---|---|---|---|---|
| IS 2021-10..2024 | P0 (0/0) | 150 | 149 | +5.027,50 | +33,74 | [+3,4 ; +64,4] | 55,0% | 44,1% | 2022 +1.328 · 2023 +2.043 · 2024 +1.515 |
| IS | P1 (38.000/38.000) | 150 | 149 | +5.027,50 | +33,74 | [+3,4 ; +64,4] | 55,0% | 44,1% | idem |
| IS | **P2 (76.000/76.000)** | 150 | 143 | +4.144,50 | +28,98 | [−1,9 ; +60,4] | 53,8% | 44,5% | 2022 +751 · 2023 +1.959 · 2024 +1.293 |
| OOS 2025-01..2026-09 | P0 | 118 | 118 | +5.088,00 | +43,12 | [−5,8 ; +91,0] | 51,7% | 41,8% | 2025 +1.416 · 2026 +3.672 |
| OOS | P1 | 118 | 118 | +5.088,00 | +43,12 | [−5,8 ; +91,0] | 51,7% | 41,8% | idem |
| OOS | **P2** | 118 | 113 | **+4.897,50** | **+43,34** | [−7,2 ; +92,9] | 52,2% | 42,4% | 2025 +978 · 2026 +3.920 |
IS+OOS agregado em P2: 256 trades, +R$9.042, +R$35,32/op, IC95% [+6,7 ; +64,2]. Aviso: a OOS foi vista descritivamente no estudo, então o agregado não é independente.
Atraso realizado da entrada: 0 min (fill na barra seguinte) em p50/p90. Saídas: ~75% achatamento do motor (dispara de fato, última saída 18:20 BRT), ~25% stop.
Previsão do CONGELADO para a OOS (P2): R$/op central +15, faixa 80% [−12 ; +43]; saiu +43,3 (topo da faixa, n=113 contra 72-82 previstos, por isso o líquido ficou acima da faixa [−950 ; +3.350]).

## Os números que decidem se ganha no real
- A fila (P0 -> P2) custa pouco aqui porque a entrada é limite no último preço e enche na barra seguinte em ~95% dos sinais; P2 perde 5-6 fills e ~R$900 (IS) / ~R$190 (OOS). Positivo em P2 nas duas janelas.
- **Capital real R$250 (mínimo do WIN = 100 x 2,0 x 1,25): o stop da linha vale em média R$182 (0,35 a 0,5 ATR).** Na IS o motor com R$250 ZERA a conta em abril/2022 (24 trades em P2, −R$137). Na OOS ele sobrevive (+R$4.897, caixa mínimo R$153), mas com MaxDD de −67% e só por ordem de sorte: embaralhando os trades a probabilidade de travar abaixo da margem crua é ~68%. Capital que a sequência IS+OOS inteira teria exigido para nunca cair abaixo de R$100: **R$1.260,50**.
- Das 12 células da grade nenhuma é elegível COMPLETA (edge + não censurada em R$250). Desenhos de stop menor (0,15 ATR, ~R$58) exigem R$849 na IS e também travam (69%): o edge está no deslocamento até o fecho, e stop curto o transforma em loteria de stops (win 27%).
- Alvo em limite (0,30 ATR) PIORA tudo (corta a cauda que paga): negativo em P2 com stop 0,15/0,25.

## WDO (replicação, mesmas regras em ATR, capital 375)
| janela | premissa | trades | líquido R$ | R$/op | IC95% | win% | BE emp. |
|---|---|---|---|---|---|---|---|
| IS | P0=CAL(329/494)=P1 | 161 | +6.999,50 | +43,5 | [−9,9 ; +98,4] | 51,6% | 43,6% |
| IS | P2 (13.400) | 152 | +5.969,00 | +39,3 | [−12,3 ; +94,2] | 51,3% | 44,0% |
| OOS | P0=CAL | 74 | −1.207,00 | −16,3 | [−82,1 ; +55,7] | 43,2% | 46,7% |
| OOS | P2 | 69 | **−1.714,50** | −24,8 | [−91,6 ; +46,4] | 42,0% | 47,6% |
Por ano (P2): IS 2022 +3.610, 2023 −185, 2024 +2.660; OOS 2025 −2.390, 2026 +676. **A replicação no WDO NÃO se sustenta na OOS (2025 forte negativo).** Com R$375 o WDO trava na 1ª operação (stop ~R$200+). Isto enfraquece a tese de "fluxo direcional geral" e deixa o resultado do WIN como específico do instrumento/período.

## Veredito honesto
1. **O edge existe depois de custo e fila no WIN?** Sim nas duas janelas e em P2 (IS +R$29/op, OOS +R$43/op), consistente por ano (todos os anos positivos, 2022 o mais fraco) e coerente com o estudo (~+0,10 ATR). Mas o IC95% de R$/op inclui 0 em P2 nas duas janelas separadas (z ~1,8 na IS e ~1,7 na OOS); só o agregado exclui 0, e o agregado não é independente. É evidência moderada, não prova.
2. **Replicou no WDO?** Não: IS positivo, OOS negativo. Maior ressalva da tese.
3. **É censurado pelo capital?** SIM, no caixa mínimo de R$250. O stop na linha (R$182 médio, ~73% do caixa) torna a ruína provável (~68% de travar; a IS real zerou). Operar com segurança pede em torno de R$1.300 ou mais para 1 contrato, ou seja >5x o mínimo. Por isso o critério de ACEITE completo do pré-registro (positivo em P2 e não censurado) NÃO é atendido: o veredito é **"edge detectado no WIN, censurado pelo capital real do mínimo; não aceito para operar com R$250"**.

## Limitações
- Fila do WIN NÃO calibrada (`fidelidade.py` só tem WDO@; não emprestei). P1/P2 são múltiplos de V̄ (volume M1) por argumento, não medição; o motor com M1 desconta o volume da barra inteira. "Atravessar 1 tick" não suportado pelo motor sem modificá-lo. Como a entrada enche quase sempre na barra seguinte, o resultado é pouco sensível à fila, mas isso também significa que o modelo M1 pode ser otimista sobre quem está na frente de uma limite no último preço (fill de 95%) -- só o extrato real aferiria.
- Base M1 (resolução de 1 minuto): stop e flatten sem trajetória intrabarra; deslize do stop = 1 tick do motor. Série @D com ajuste por diferença.
- A OOS é semi-cega (a pista nasceu parcialmente nela). A previsão foi escrita antes e saiu no topo da faixa (acima em líquido por mais trades).
- n pequeno (~50 sinais/ano), IC por janela inclui 0; 3 parâmetros livres e 12 células testadas na IS (platô exigido, canônica mantida).
- Adendo ao pré-registro (declarado): depois de UM teste de fumaça (célula X0,3/stop 0,25) vi a censura de capital e acrescentei, antes da grade, a corrida nominal e a caminhada de caixa. A escolha final (canônica) não mudou por isso.
- Sessões em horário de verão dos EUA fecham 17:55 e a última barra é 17:54; o achatamento ali ocorre na última barra do dado (o robô real precisaria do corte de `core.b3_session`).
- 2 testes de `tests/test_run_live_cli.py` falham na máquina (também isolados); não têm relação com este trabalho.

## Arquivos
`PRE_REGISTRO.md`, `CONGELADO.md`, `comum.py`, `run_is.py` (grade IS; `volume` = ablação), `analisa_is.py`, `confere_motor_real.py` (motor com R$250; `IS`/`OOS`), `run_final.py` (OOS WIN + WDO), `analisa_final.py`, logs `*_stdout.log`/`confere_motor_real_*.log`/`analisa_final.log`, CSVs `analise_is_grade.csv`/`analise_final.csv`, `saidas/*.json` (trades).
