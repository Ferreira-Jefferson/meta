# Ciclo de retroalimentação das regras (protocolo do dono, 2026-10-09)

1. **Juntar** todas as regras FAZER e NAO_FAZER num robô só (`robo.py`):
   - FAZER entra;
   - NAO_FAZER veta entradas do mesmo lado.
2. **Operar** em 20 dias NOVOS: 10 bons e 10 ruins.
   - **Bom** = dia direcional (eficiência do dia ≥ 0,30).
   - **Ruim** = dia de rotação (eficiência < 0,15).
   - A classificação usa o dia inteiro e serve só para escolher os dias. O robô não a vê.
3. **Ver o que funcionou:** quais regras entraram, quais vetos agiram e o resultado por dia.
4. **Analisar cada dia que fechou negativo.** Um agente por dia, com `INSTRUCOES_CICLO.md`, responde:
   - o que nas regras levou ao prejuízo;
   - 5 maneiras de ter deixado o dia positivo;
   - 5 coisas a não fazer.
5. **Ajustar e criar regras.** Cada mudança é conferida:
   - no dia negativo;
   - em TODOS os dias já usados nos ciclos anteriores. Não pode quebrar o que funcionava.
6. **Próximo ciclo:** 20 dias NOVOS. Repete.

## Regras de dados

- **Os últimos 6 meses (abr–out/2026) ficam reservados** para a confirmação final.
- **Cada ciclo usa só 20 dias novos.** Nunca rodar dezenas ou centenas de dias, nem o período inteiro, sem o dono pedir.
- **Registro de dias usados:** `dias_usados.json`. Dia usado não volta como dia novo.

## Registro dos ciclos

| ciclo | dias (bons/ruins) | regras | resultado bons | resultado ruins | dias negativos | o que mudou |
|---|---|---|---|---|---|---|
| 0 | 10 sorteados (`dias.json`) | criação: 50 FAZER + 50 NAO_FAZER | — | — | — | — |
| 1 | 20 novos (`dias_usados.json`, seed 20261014): 10 bons / 10 ruins | `robo.py`: 50 FAZER + 50 NAO_FAZER (veto por lado, 2 lados = não entra, máx 3 ops) | +R$1.432,79 (16 ops, 8 positivos, 1 negativo de −R$2,00, 1 dia sem trade) | +R$431,45 (13 ops, 2 dias negativos, 1 dia sem trade) | 3 (`ciclo1_negativos.json`): 2023-07-27 (bom), 2023-12-18 e 2025-01-20 (ruins) | nada ainda (robô medido como criado). Total 29 ops, 24 ganhos, fator de lucro 8,6, pior dia −R$59,86. Vetos em conjunto custaram: as 157 entradas vetadas, simuladas, somam +R$6.057 (74 de 152 enchidas perderiam). Só 12 dias do IS têm eficiência ≥ 0,30: 10 dos 12 foram sorteados |
| 2 | 20 novos (`dias_usados.json`, seed 20261015): 10 bons (ef ≥ 0,25; só 2 dias do IS ≥ 0,30) / 10 ruins (< 0,15) | `robo_v2.py`: v1 + A1 (inclui F5 só se defendeu mínima), F2 alvo 1 ATR, veto #8 VWAP, A2 (veto só no rompimento raso), N1 spring raso; A3/A4/A5 no fim dos FAZER. Estrutura v1 mantida. Variante descritiva v2-estrutural (tenta a próxima candidata; 2 lados → o lado não vetado) | v1 +R$556,69 (20 ops, acerto 12/20, 3 neg) · v2 +R$1.267,70 (23 ops, 15/23, 1 neg) · v2e +R$1.333,29 | v1 −R$162,12 (18 ops, 8/18, 4 neg) · v2 −R$424,59 (23 ops, 9/23, 6 neg, pior dia −R$283,36) · v2e −R$483,11 | v2: 7 (`ciclo2_negativos.json`): 6 ruins; 1 bom (2024-11-04) | Total 20 novos: v1 +R$394,57 (FP 1,42) × v2 +R$843,11 (FP 1,66, acerto 24/46, 7 dias neg) × v2e +R$850,18. Nos 30 dias usados (dentro da amostra): v1 +R$2.866,75 × v2 +R$3.835,66 × v2e +R$3.862,66. Os ganhos da v2 vêm dos dias bons; nos ruins a v2 piorou (A2 libera F1 em rompimento raso: 2024-04-22, 2025-06-06). Vetos da v2 nos 20 novos: 120 entradas vetadas, 116 enchidas, soma simulada +R$2.270 (59 perderiam, 57 ganhariam) |
| 3 | 20 novos, SORTEIO ALEATORIO SIMPLES do IS (`dias_usados.json`, seed 20261016): 0 bons, 7 intermediarios, 13 ruins (calendario real). Pre-registro em `ciclo3/PREREGISTRO.md` | `robo_v3.py`: v2 + C8 (c2_2022_05_24 A1+A2+F2: afrouxa 2 vetos de compra e acrescenta expansao pos-compressao) + C7 (c2_2024_04_22 N5: nao vender minima nova com range/volume encolhendo) + C6 (c2_2025_04_07 N4+N1+F1) + C4 (c2_2023_09_04 P2: rompimento da 1a hora c/ volume >= 1,5x, alvo 1R). Escolhidas por selecao para frente nos 50 dias pelo R$/dia REPONDERADO (bom 3,8% / nao-direcional 96,2%). Ficaram de fora: gestao sem alvo (C2/C3: +R$184/dia nos bons, -R$41/dia no nao-direcional), alvo x1,5 (C1: reponderado -3,4), C5, C9, C10 e extras | v1 -R$694,66 (acerto 7/26, FP 0,47, 12 dias neg) · v2 +R$257,05 (18/43, FP 1,14, 12 neg, pior -R$254,71) · v3 +R$311,49 (18/42, FP 1,17, 12 neg, pior -R$253,09) | por estrato: ruins (13) v1 -994 / v2 -904 / v3 -873; intermediarios (7) v1 +300 / v2 +1.161 / v3 +1.184 | v3: 12 (`ciclo3_negativos.json`): 10 ruins e 2 intermediarios | v3-v2 +R$54,44 (IC95 por dia [0,04; 6,71], sign-flip p=0,125, 4 dias melhores/0 piores); v3-v1 +R$1.006 (IC [-6; 111], p=0,116); nulo de 200 sorteios com a geometria do v3: media -R$184, v3 acima de 82% (p=0,18). Nos 50 dias o v3 media R$87,9/dia reponderado (v2 R$55,1) e nos 20 reais R$15,6/dia: a diferenca e ajuste a amostra. Caixa R$2.000 (escada, 1-2 contratos): v3 termina R$2.198 (minimo R$1.156, nao parou). Pos-hoc informativo, nada adotado: desfazer o A2 piora (-R$663) |
| 4 | 20 novos, sorteio aleatorio simples (seed 20261017): 1 bom, 4 intermediarios, 15 ruins. Pre-registro em `ciclo4/PREREGISTRO.md` | `robo_v4.py`: v3 + D16 (alvo x2 a favor da perna, ef>=0,3) + D13 (nao vender no terco inferior em rotacao) + D1 (retomada da abertura a favor do gap, prioritaria) + D9 (nao comprar apos 1a vela de queda forte) + D2 (flip apos stop da gap_fade). Selecao para frente nos 70 dias com criterio novo leave-one-day-out; 16 candidatas D1-D16 das analises dos 12 negativos do v3 | v1 +42,81 · v2 +288,42 · v3 +525,32 · **v4 +677,54** (35 ops, 51,4%, FP 1,57, pior -190) | por estrato v4: bom (1) +73 (v3 +296: D16 cortou o unico dia direcional) · intermediarios (4) +888 · ruins (15) -284 | v4: 9, todos ruins (`ciclo4_negativos.json`) | v4-v3 +152 (IC [-30; +52]/dia, p=0,59); nulo p=0,05 (primeira vez no limite); dentro da amostra +24/dia, fora +7,6/dia. v3 em 40 dias aleatorios fora da amostra: +R$837 (R$20,9/dia). Caixa R$2.000: v4 termina 2.537 (min 1.549) |
