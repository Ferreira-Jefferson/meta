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
