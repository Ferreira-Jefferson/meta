# WIN — pré, pregão e pós: as seis lentes refeitas na tabela de fases corrigida

Mesma janela (127 pregões, 06/04/2026 a 05/10/2026), mesmos métodos, mesmas sementes e mesmos números de permutação das lentes originais. A única coisa que muda é o dado: `data/win_fases_pregao_6m.csv` corrigido (comparado com a versão `_v1`) e, onde a lente lê barras, a base M1/M5 sem os leilões. Saídas em `lente*/refeito_2026_10_06/`; as saídas originais ficam intactas.

## O que mudou no dado

Diferença célula a célula entre `win_fases_pregao_6m_v1.csv` e o CSV atual (nova coluna `fonte`: `ticks` em 124 dias, `ticks+M1` em 3):

| dia | células alteradas | efeito |
|---|---|---|
| 2026-05-06 | `pregao_volume` 18.257.670 → 18.629.107 (+371.437); `volume_total_dia`; `observacao` | 7 min sem ticks (09:16–09:23) completados pelo M1. Volume, máxima e mínima completados; negócios não |
| 2026-08-10 | `pregao_volume` 14.772.190 → 15.177.454 (+405.264); `volume_total_dia`; `observacao` | 8 min sem ticks (10:00–10:08) completados pelo M1. Mesmo critério |
| 2026-09-24 | `pre_hora_leilao` NaN → 09:02; `pre_preco_inicio`/`pre_preco_fechamento` NaN → 186.575; `pre_volume` 0 → 53.915 (estimado); `pregao_hora_inicio` 09:14:00.161 → 09:02; `pregao_preco_inicio` 185.965 → 186.575; `pregao_volume` 18,57 mi → 19,50 mi (+937.380); `volume_total_dia`; `observacao` | O leilão de abertura passa a existir (lido da 1ª barra M1) e o gap de 24/09 passa a valer −105 pts contra o call de 23/09. `pre_negocios` fica 0 e os negócios do pregão continuam subestimados |

Nenhuma outra célula das 127 × 26 colunas mudou. As alterações atingem volume (3 dias), máxima/mínima do pregão (2 dias) e o conjunto do leilão de abertura (1 dia). Nenhum preço de fechamento, nenhum call e nenhum dos três dias de rolagem mudou.

**Mudança de base de barras.** Cinco lentes liam `data/comparativo_win_2026/m1_WIN$N.parquet`, onde a 1ª barra do dia traz o leilão e a barra das 18:24 traz o call. Todas passaram para `data/win_sem_leiloes/m1_WIN$N.parquet`.

| lente | usava barras? | base trocada? | observação |
|---|---|---|---|
| 1 | sim (M5: 1ª barra, gap fechado, hora de cruzamento) | sim | |
| 2 | sim (M5 17:20, 17:50, 1ª–6ª barra) | sim | |
| 3 | sim (caminho M5, perfil de volume) | sim | removi a subtração de `pre_volume`/`pos_volume` das barras extremas, porque a base nova já vem limpa |
| 4 | não | não se aplica | só lê o CSV de fases |
| 5 | sim | sim | |
| 6 | sim | sim | |

Nas cinco lentes que leem barras, a troca de base e a correção do CSV mexem juntas no resultado. Na prática a troca de base quase não pesa: os alvos que dependem do preço de abertura ou de fechamento já vinham do CSV, e a barra das 18:20 contaminada pelo call só entra em poucos alvos (gap tocado, fechamento em M5).

Os métodos de exclusão foram mantidos como estavam. O dia 24/09 continua fora das amostras "limpa"/"sem flags" (lentes 1, 2, 5 e 6) e dentro das amostras "completa"/"todos" (lentes 1 e 3), agora com `pre_*` preenchido.

## Antes × depois, número a número

| # | Conclusão da SINTESE original | Antes | Depois | Veredito |
|---|---|---|---|---|
| 1 | Reversão do gap: ρ gap → retorno do pregão | −0,18 (limpa) a −0,23 (todos); q 0,23–0,44 (lente 1), 0,040 (lente 3, todos) | −0,18 (limpa, inalterado, q 0,20–0,42) a −0,22 (todos, n 124→125); lente 1 completa: −0,228 → −0,224, q 0,17 → 0,23; lente 3 matriz todos: q 0,040 → 0,059; lente 3 família operável: q 0,045 → 0,067 | **Mantém** o tamanho e o sinal. Perde o único q < 0,05 que existia (lente 3, amostra "todos"): ver nota 1 |
| 2 | Gap ↑: −491 pts, 34% de dias de alta; gap ↓: +264 pts, 54% | amostra limpa: gap ≥ 0 n=65, −490,5, 34%; gap < 0 n=55, +264,5, 55%; p da diferença 0,037 | amostra limpa idêntica (as médias não mudam; p 0,042 por ruído de permutação). Na amostra completa o gap < 0 passa a n=56, +231 pts, 54% (entra 24/09), e gap ≥ 0 segue −567, 32% | **Mantém** |
| 3 | Gap → direção do dia (estável nas metades) | ρ −0,22 (limpa) / −0,26 (completa); H1/H2 −0,14/−0,31 | −0,22 / −0,25; H1/H2 −0,14/−0,31 (limpa); q 0,27 / 0,12 (era 0,27 / 0,10) | **Mantém** |
| 4 | 1ª M5 contra o gap → o resto do pregão continua: +707 pts, 62%, n=66, q ≈ 0,03, estável nas metades | todos: n=66, +706,8, 62,1%, p 0,0016, q 0,024; H1/H2 +748/+676. Limpo: n=58, +774, 62,1%, q 0,030 | todos: n=66, +706,8, 62,1%, p 0,0022, q 0,033; H1/H2 +748/+676 (iguais). Limpo: n=58, +774, 62,1%, q 0,030 (igual) | **Mantém** (a lente 3 compara 15 recortes por base) |
| 4b | Contraste contra − a favor (k=1) | +744 (q 0,053) todos; +785 (q 0,075) limpo | +720 (q 0,065) todos; +785 (q 0,073) limpo | Mantém. Segue sem passar por BH |
| 4c | 1ª M5 a favor do gap: sem continuação, reverte por volta da 6ª barra (−445 pts) | k=6: −444,8, 43%, q 0,092 | k=6: −444,8, 43%, q 0,101 | Mantém, continua fraco |
| 5 | Volume do call D−1 alto → amplitude de D menor: ρ −0,23 a −0,28 | lente 3: todos −0,227 (q 0,040), limpo −0,280 (q 0,007); lente 2: −0,239 (q 0,148) / −0,267 (q 0,051); lente 5: −0,24 a −0,28 (q 0,09–0,22) | lente 3: todos −0,227 (q 0,046), limpo −0,280 (q 0,011); lente 2: iguais; lente 5: iguais | **Mantém** (ρ idêntico; q oscila só por ruído de permutação) |
| 6 | Pós D−1 + pré D não acrescenta nada além do gap (lente 5) | 234 testes por base; q < 0,05: 4 (com 10-05) e 3 (sem); todos mecânicos ("gap grande, menos chance de fechar o gap"); nenhum para direção, variação ou amplitude | os mesmos 234 testes, q < 0,05: 4 e 3; ρ, n e q idênticos nas 14 relações com q < 0,10 | **Mantém**: lente 5 não mudou (os dias alterados já estavam fora dessa amostra) |
| 7 | Razões contra o estágio anterior não acrescentam nada (lente 6) | 400 testes; q_perm < 0,05: 41 (21 + 20); q_cons < 0,10: 18 (9 + 9); único não-contemporâneo que passa tudo: C1_v → volume (ρ −0,31, q_cons 0,024), que a decomposição mostra ser o denominador | idêntico: 41 (21 + 20), 18 (9 + 9); C1_v → volume ρ −0,31, q_cons 0,024; maior mudança de ρ em qualquer das 400 linhas: 0,005; cadeia B→C→A→B igual dentro de ±0,005 | **Mantém** |
| 8 | Contagem de testes que passam BH (q < 0,05) | L1: 6 / 6 (completa / limpa); L2: 0 com q_cons < 0,10; L3: matriz 101 / 99, família operável 30 / 27, intradia M5: 0, continuidade: 2 / 2; L4: não é teste; L5: 4 / 3; L6: 41 com q_perm, 1 por base com q_cons < 0,10 | L1: 6 / 6; L2: 0; L3: matriz **99 / 97**, família operável **27 / 26**, intradia M5: 0, continuidade 2 / 2; L5: 4 / 3; L6: 41, 1 por base | Praticamente igual. As únicas mudanças são na lente 3, todas na fronteira de 0,05 (nota 1) |
| 9 | Lente 4 (poder: só |ρ| ≥ ~0,30 sobrevive a BH com ~100 testes) | n=126: 0,25 / 0,31 / 0,34 / 0,38 | idêntico | **Mantém** |

Observações sobre a lente 4: o ρ de Spearman gap × variação do pregão (todos os 127) vai de −0,228 para −0,224; sem rolagens e sem 10-05, 07-31 e 09-24 fica em −0,184 nas duas versões. O desvio-padrão do gap cai de 1.889 para 1.882 pts. A reversão mecânica de Δ% (ρ ≈ −0,47 no nulo) continua igual, com mudanças de ±0,03 nas séries que contêm os dias corrigidos (`pre_volume` ρ de Δ% −0,399 → −0,416, `pregao_vn` −0,325 → −0,296). Esses valores continuam dentro do IC do nulo.

## Notas

1. **Quem cruza 0,05.** Cinco pares da lente 3 trocam de lado, e nenhum envolve preço de execução:
   - `gap → retorno do pregão` (q 0,040 → 0,059 na matriz de 425 pares; 0,045 → 0,067 na família operável): ρ praticamente igual, mas n passa de 124 para 125 porque 24/09 ganha um gap (−105 pts) e a nova observação enfraquece levemente a relação.
   - `volume do call D−1 → amplitude de D` (0,045 → 0,053, só na família operável): ρ e n idênticos. A mudança é puramente o ruído de Monte Carlo da permutação (resolução de ~0,004 em p com 10.000 sorteios, e o fluxo de números aleatórios se desloca quando outro par muda).
   - `volume pregão D−1 → vol/negócio D` (0,043 → 0,068, ρ −0,226 → −0,217): efeito do volume completado nos dias com lacuna de ticks.
   - `preg_neg[D−1] → Δ vol pregão D` (limpo, 0,040 → 0,052) e `pre_vol[D] × pre_neg[D]` (limpo, 0,048 → 0,056): ρ e n iguais ou quase, de novo ruído de permutação.
   
   Leitura: a distância entre "q = 0,04" e "q = 0,06" fica dentro do erro numérico dessas permutações e do tamanho da amostra. Isso não é evidência a favor nem contra. Na lente 1, onde a variação do pregão fica sempre em q 0,17–0,44, essa pista nunca passou por BH.
2. A lente 2 troca uma linha da tabela "top 15" (`d1_vpn → vol`, p 0,051, sai; `d1_l30 → m5_12`, p 0,052, entra), duas linhas na fronteira de p = 0,05. Não muda o placar (14 p < 0,05 com 10-05, 19 sem; q < 0,10: 2 e 3; q_cons < 0,10: 0).
3. 24/09 passou a ter leilão estimado: `pre_volume` é excesso sobre a mediana das 5 barras vizinhas e `pre_negocios` é 0 (desconhecido). Os testes que usam o volume do leilão de D, ou o Δ% contra o leilão anterior, tratam esse dia como observação válida na amostra "completa/todos". Os testes de negócios e de volume por negócio do leilão tratam `pre_negocios = 0` como ausente (`> 0`), então não usam o dia.
4. O CSV `lente4_cetica_integridade/refeito_2026_10_06/dias_flag.csv` atualiza os 6 dias afetados (24/09, 25/09, 06/05, 07/05, 10/08, 11/08). Os negócios dos três dias corrigidos continuam subestimados, e as sensibilidades de negócios ainda devem excluí-los.

## Resumo

- Nenhuma das conclusões da SINTESE original muda de direção ou de ordem de grandeza.
- A pista 1 (reversão do gap: ρ ≈ −0,18 a −0,23) e a pista 4 (1ª M5 contra o gap → continuação: +707 pts, 62%, n=66, q 0,024 → 0,033) seguem como as duas pistas que se repetem, e ambas continuam estáveis nas duas metades (H1/H2: −0,24/−0,23 e +748/+676).
- Mudam só números na fronteira do corte: o gap deixa de ter q < 0,05 na lente 3 (0,040 → 0,059); a contagem total de testes com q < 0,05 cai de 101 para 99 (matriz) e de 30 para 27 (família operável), todos eles em pares de volume e negócios.
- O mesmo vale para a amplitude após o call: ρ −0,23 a −0,28 idêntico, q 0,04 ± 0,01.
- Os poderes e as ressalvas da lente 4 continuam: n ≈ 120 e ~100 testes só detectam |ρ| ≥ ~0,30.

## Onde estão os arquivos

`scripts/daytrade/win_fases_correlacao_2026_10_06/lente{1..6}_*/refeito_2026_10_06/`:
- scripts `*_v2.py` (alteram só o caminho da base de barras, o caminho de saída e, na lente 3, a retirada da subtração de volume);
- `stdout.txt` e as tabelas CSV de cada lente (lente 2: `RESULTADO.md` gerado; lente 3: `out/`; lente 4: `auditoria_stdout.txt`, `A_reversao_mecanica.csv` e `dias_flag.csv` novo).

Os `RESULTADO.md` escritos à mão das lentes 1, 3, 4, 5 e 6 não foram regerados: a comparação está acima.
