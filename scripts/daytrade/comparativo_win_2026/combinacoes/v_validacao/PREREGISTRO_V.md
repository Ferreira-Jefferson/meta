# Validação das candidatas fora de 2026 — PRÉ-REGISTRO (escrito em 2026-10-06, ANTES de qualquer rodada fora de 2026)

Pedido do dono: "teste o que merece ser validado". As candidatas vêm da seção "Candidatas" (ranking.py) pelo critério do dono, sem o WdoRetangulo, que foi excluído de tudo.

## Bloco
**VAL = 2024-07-01 → 2025-09-30**, WIN$N M1 cru (`data/comparativo_win_2026/m1_WIN$N_2022_2025.parquet`), ticks sintéticos 4/M1 (`n_nova/dados_dev.py`), regras do Testador, custo R$2/op, R$1.000.
- **Aquecimento e treino:** os indicadores usam as barras anteriores ao VAL. Os filtros walk-forward treinam com os meses anteriores ao mês aplicado. O 1º mês do VAL usa jan–jun/2024 como passado; esse trecho já foi usado pela N1/RDT no DEV, mas nunca por estas regras.
- **Uso do bloco:** já foi usado uma vez, pela RDT. Esta é uma rodada ÚNICA, para a lista inteira, com correção de multiplicidade (Holm) no lugar do limite de 3 candidatas.

## Ajuste obrigatório antes de congelar (não é ajuste de parâmetro)
O WdoRetangulo foi excluído pelo dono, então nenhuma regra pode usar o voto ou a posição dele.
1. Cada candidata é refeita em 2026 SEM o WdoRetangulo. É a mesma regra com um votante a menos, sem mexer em parâmetro.
2. A candidata só segue para o VAL se, em 2026, continuar passando no critério: variante com Δ > 0 contra o próprio original, com custo; nova com líquido com custo > o pior original em 2026 (R$841).
3. As regras que seguem são congeladas, com o hash dos scripts, em `v_validacao/CONGELADAS.md`, ANTES do VAL.

## Lista (13)
| id | robô | regra (script da frente, versão walk-forward quando houver) |
|---|---|---|
| C1 | Win_c1 | B — filtro "entra ou não" pela tabela de frequência (b_nota) |
| C2 | WinCincoMedias | A1 — filtro de consenso, variante comum ao conjunto (a_consenso) |
| C3 | WinDeslocamentoMatinal | A1 — filtro de consenso, escolha individual (a_consenso) |
| C4 | WinDeslocamentoMatinal | A1 — filtro de consenso, variante comum (a_consenso) |
| C5 | Win | E V2b — sai se qualquer um da outra família vira contra, só no lucro |
| C6 | Win | E V1a — sai se a outra família inteira vira contra |
| C7 | Win | E V1b — V1a só no lucro |
| C8 | WinCincoMedias | E V3b — sai se outro da própria família vira contra, só no lucro |
| C9 | WinCincoMedias | E V3a — V3b sem exigir lucro |
| C10 | WinDeslocamentoMatinal | E V3a |
| C11 | WinDeslocamentoMatinal | E V3b |
| C12 | WinRetanguloEma34 | B — alvo e stop redimensionados pela nota (b_nota, resize) |
| C13 | ConsensoGatilho (nova) | A2 — gatilho de consenso, walk-forward de stop/alvo (a_consenso) |

## Critérios no VAL (fixos)
**Variante (C1–C12):**
- **Primário:** Δ = líquido da variante − líquido do original do mesmo robô, com custo, no VAL. Teste unilateral contra um filtro ou saída aleatória de mesma intensidade: mesma fração cortada para filtros; para saídas, o mesmo nº de saídas antecipadas, em instante sorteado com a mesma distribuição de tempo desde a entrada; 2.000 sorteios. Aplica-se Holm sobre as 13 candidatas, com α = 0,05.
  - **APROVADA:** Δ > 0 e p corrigido < 0,05.
  - **PROMISSORA:** Δ > 0, fator de recuperação maior que o do original e p bruto < 0,10, sem passar no Holm. Vira observação e vai para o forward de outubro.
  - **REFUTADA:** o resto.

**Nova (C13):**
- **APROVADA**, se cumprir todos:
  - líquido com custo > o do pior original no VAL;
  - não quebrar com R$1.000;
  - fator de lucro ≥ 1,2;
  - ≥ 3 de 5 trimestres positivos;
  - percentil ≥ 95 contra o sorteio de lado no mesmo horário, com o p entrando no Holm.

**Relatório:** tabela por mês e por trimestre, com e sem custo, para cada candidata e seu original. Colunas: acerto, payoff, fator de lucro, maior queda, fator de recuperação, quebra.
