# WIN — gap e 1ª barra M5: estratégia e medição (2026-10-06)

Estratégia: `win_gap.py::WinGapReversao` (lab; não registrada em `registry.py`). Dados: WIN$N M5 sem leilões (`data/win_sem_leiloes`), preço cru. Motor de produção intocado.
Reprodução: `dados.py` (base, gap, rolagem) → `sweep_is.py` → `resumo_is.py` (escolha) → `valida.py` → `gera_resultado.py`. Saídas em `out/`.

## 1. Como foi medido

- **Desenho de execução:** entrada `EnterLimit` com `ttl_bars=6` (6 barras M5 = 30 min, sem conversão tick→barra); alvo, quando existe, em ordem-limite real fatiada sem prazo (`exit_split_unit`, `exit_ttl_bars=10**9`); `anchor_exits_at_fill=True`; stop a mercado. Sem alvo, segura até o fim do CONTÍNUO. Entrada a mercado: nenhuma.
- **Fim do dia:** `session_end_time=18:20` passado no script (base em BRT). A última barra de cada dia é a última do contínuo (o loader descarta o call). Dias de pregão que acabam 17:55 caem no fallback "última barra".
- **Capital:** R$250 (margem R$100 × 2 × 1,25; 1 contrato; 1 ponto = R$0,20). Dois modos, porque com R$250 a conta morre no meio da janela e a janela passa a medir caixa:
  - **A, conta contínua:** R$250 no início da janela, caixa arrastado. Mostra a censura (ordens recusadas por capital, pregões sem trade, caixa mínimo marcado a mercado).
  - **B, R$250 por pregão:** cada pregão é uma run nova com R$250 (capital mínimo real em toda operação, sem arrasto). Mede o resultado por operação sem a morte de caixa. Capital NOCIONAL na tabela (retorno, MaxDD %, capital final em branco). Como os pregões são independentes, o nulo de direção aleatória é exato: cada dia de gatilho roda forçando +1 e forçando −1; o nulo sorteia entre os dois (10.000 sorteios; p = fração de sorteios com líquido ≥ o observado).
- **Premissa de preenchimento (coluna `fill`):** `toque` = entrada e alvo enchem quando a barra toca o nível, fila 0/0 (`limit_fill_capped_by_volume=True`). **O WIN não tem fila calibrada em `fidelidade.py`; a premissa é otimista e não foi medida.** `atrav+1t` = só enche se a barra atravessa o nível em ≥ 1 tick (5 pts). A coluna `p nulo` é do modo B. A etiqueta `desliz.alvo 1,0t` vem da config; o alvo fatiado não paga esse deslize (`machine._close_position`), stop e flatten pagam 1 tick.
- **Base `BE emp%`:** `perda média / (ganho médio + perda média)` sobre o P&L líquido por operação. `win% > BE emp%` e `líquido > 0` são a mesma afirmação.
- **Exclusões:** dias de rolagem do WIN$N (quarta mais próxima do dia 15 dos meses pares; gap bruto mediano 2.158 a 3.600 pts nesses dias contra 315 a 448 nos outros), 2026-07-31 (abertura às 12:34), pregões parciais (começam depois de 09:10 ou < 80 barras M5) e dias sem pregão anterior em até 5 dias.
- **Gap:** `leilao_preco[D] − call_preco[D−1]`. Contexto causal por dia: o volume do call de D−1 é "alto" se acima da mediana dos ≤ 60 pregões anteriores do mesmo regime (proxy × medido), com ≥ 20 observações.

## 2. Variantes e grade (IS)

- **V1** fade do gap: direção contra o gap, decidida no fecho da 1ª barra M5; limite no close da barra ± `recuo` na direção do gap.
- **V2** 1ª barra M5 fecha contra o gap (`close − open` de sinal oposto ao gap): entra na direção da barra, limite em `close − sinal × recuo` (recuo = pullback). Sem fechar contra o gap: sem trade.
- **V3** = V2 + volume do call D−1 alto: `skip` ou alvo menor (350 pts).
- Eixo opcional |gap| ≥ 400 pts (V2).
- 28 células: recuo {0, 150} × stop {350, 700} × alvo {nenhum, 700} para V1 e V2 (16); V3: recuo × stop × {skip, alvo 350}, alvo base 700 (8); V2 com |gap| ≥ 400 (4). Eixos conferidos (seção 4).

## 3. Critério de escolha (declarado antes de ver os números)

1. Eliminatório: conta contínua de R$250 sem ordem recusada por capital e com caixa mínimo ≥ R$100 (margem crua).
2. Se ninguém sobrevive ao 1, segue só com o modo B, dizendo isso na primeira linha.
3. Entre os elegíveis: n ≥ 30, líquido > 0, win% > BE emp; ordena por lucro/DD (modo B, `toque`). A primeira é congelada.

## 4. IS (2026-04-06 a 2026-10-05) — NÃO é evidência: os indícios nasceram aqui

123 pregões elegíveis (4 excluídos: 3 rolagens + 07-31).

### Modo A, conta contínua R$250, fill=toque (28 células)

```
{{IS_A}}
```

### Modo B, R$250 por pregão, fill=toque (28 células)

```
{{IS_B}}
```

### Modo B, fill=atrav+1t

```
{{IS_B2}}
```

### Sobrevivência de caixa e eixos

```
{{CRIT}}
```

```
{{EIXOS}}
```

Escolha congelada: **V2, recuo 150 pts, stop 350 pts, sem alvo, ttl 6 barras (30 min), sem filtro de gap nem de volume**. Era uma das 3 células que sobreviveram ao critério 1 e a de maior lucro/DD entre elas (7,55; as outras: V2 r150 s700 sem alvo 5,63; V1 r150 s700 sem alvo 2,24). Sobreviver ao critério 1 depende do caminho (ordem das primeiras operações): em 25 das 28 células a conta de R$250 foi censurada.

## 5. Validação — rodada uma vez, célula congelada, sem reajuste

Gasta estas janelas para estas hipóteses: 2022-01 a 2025-09 (por ano) e 2026-02-20 a 2026-04-03. Preços de leilão e de call são PROXY nas duas (o open da barra do leilão não é corrigido; o volume do call é estimado). 2025-10 a 2026-02-19 ficou sem uso.
Em cada janela: A com R$250 novos; B por pregão. Por ano, A reinicia em R$250.

```
{{VALIDA}}
```

## 6. Limitações que mudam a leitura

- O motor só avalia stop/alvo a partir da barra seguinte à do fill. Com M5 logo após a abertura, o stop de 350 pts foi tocado dentro da própria barra do fill em 9 das 48 operações do IS (e 4 de 247 nas janelas de validação em B); essas saem na abertura da barra seguinte, pior que o nível. Pior operação do IS: −R$242,50 (stop de 350 pts = R$70).
- Fila do WIN não calibrada. A sensibilidade `atrav+1t` muda pouco o resultado (entrada no último preço da barra, o próximo open costuma já estar ≥ 1 tick abaixo), então ela não mede fila: um nível a 150 pts do close tem fila própria que não foi estimada.
- Grade de 28 células com escolha do melhor: o p do IS não é corrigido para a escolha. Só a validação é fora da amostra.
- V1 e V3 não foram congeladas e portanto não foram rodadas na validação como estratégia; as premissas delas (gap reverte; volume do call vs amplitude) estão no bloco `INDICIO CRU` de cada janela.
- A morte de caixa do modo A é função do caminho: a mesma célula sobrevive ou morre conforme as primeiras operações da janela.

## 7. O indício sobrevive fora da amostra?

Célula congelada (V2, recuo 150, stop 350, sem alvo), modo B, fill=toque; p do nulo de direção aleatória nos mesmos dias:

| janela | sinais | fills | sem fill | líquido R$ | win% | BE emp% | nulo médio R$ [p5 ; p95] | p |
|---|---|---|---|---|---|---|---|---|
| IS 2026-04 a 10 | 63 | 48 | 23,8% | +3.784,00 | 31,2 | 15,7 | +979 [−1.095 ; +3.083] | 0,013 |
| VAL2 2026-02-20 a 04-03 | 12 | 9 | 25,0% | −710,50 | 0,0 | — | −188 [−794 ; +420] | 0,904 |
| 2022 | 113 | 67 | 40,7% | +1.404,50 | 23,9 | 18,4 | +925 [−1.023 ; +2.865] | 0,347 |
| 2023 | 108 | 75 | 30,6% | +1.103,50 | 28,0 | 23,2 | +1.422 [−280 ; +3.093] | 0,620 |
| 2024 | 97 | 50 | 48,5% | +1.305,00 | 34,0 | 24,5 | +358 [−988 ; +1.683] | 0,124 |
| 2025 jan-set | 84 | 55 | 34,5% | +466,50 | 30,9 | 27,6 | +206 [−1.190 ; +1.587] | 0,380 |
| 2022-2025 junto | 402 | 247 | 38,6% | +4.279,50 | 28,7 | 23,1 | +2.917 [−282 ; +6.179] | 0,242 |

- Líquido acima de zero em 4 dos 5 recortes de validação (2022, 2023, 2024, 2025); VAL2 negativo (9 operações, 9 stops). Win% acima do BE empírico nos 4 anos. O líquido observado fica dentro da faixa p5-p95 do nulo em todos os recortes de validação; p ≥ 0,124.
- O nulo de direção aleatória tem média positiva nas janelas longas (+2.917 em 2022-25): stop de 350 pts, sem alvo e segurando até o fim do dia ganha nos dois lados nos dias de tendência.
- Conta contínua R$250 (modo A, fill=toque): censurada em 3 de 6 janelas (2022: 7 trades, 60 ordens recusadas, caixa mín R$31,50; 2025: 3 trades, 52 recusadas, R$35,50; VAL2: 3 trades, 6 recusadas, R$35,50). Não censurada em 2023 (+R$1.103,50, caixa mín R$159,50, 75 trades) e 2024 (+R$1.021,50, caixa mín R$169,50, 51 trades); em 2024 com `atrav+1t` a conta é censurada (32 trades, 16 recusadas, caixa mín R$86,00, −R$164,00).
- Indício cru, sem geometria e sem custo (resto do dia depois da 1ª barra, na direção dela, dias em que ela fechou contra o gap): IS +696 pts, 60% dos dias positivos, n=63 (p 0,002); 2022 +37 pts (52%, n=113, p 0,40); 2023 +84 (53%, n=108, p 0,23); 2024 +140 (57%, n=97, p 0,067); 2025 jan-set +248 (57%, n=84, p 0,031); VAL2 +294 (58%, n=12, p 0,27); 2022-25 junto +118 pts (54%, n=402, p 0,028). Mesmo sinal em todos os recortes, magnitude de 1/6 a 1/20 da do IS nos anos longos.
- Fade do gap (hipótese 1), cru: IS gap de alta −564 pts (32% de pregões de alta, n=66), gap de baixa +263 (54%, n=57), ρ(gap, mov) = −0,20. 2022-25: gap de alta −20 pts (51% de alta, n=447), gap de baixa +47 (52%, n=461), ρ = −0,00; fade médio +34 pts, p 0,21. Por ano, ρ: −0,02; −0,02; −0,02; +0,07.
- Volume do call de D−1 vs amplitude de D (hipótese 3), ρ de Spearman: IS −0,24; 2022 −0,17; 2023 −0,07; 2024 −0,23; 2025 −0,05; VAL2 +0,25 (n=30); 2022-25 junto −0,19 (n=908; volume do call estimado nesses anos).

**Resposta:** o sinal da pista 2 se repete nos 5 recortes fora da amostra, com magnitude muito menor que no IS (+118 pts contra +696 pts, n=402 contra n=63), p 0,028 sem correção para as três hipóteses nem para as janelas. Como estratégia com R$250, a célula congelada não se distingue do nulo de direção aleatória em nenhuma janela de validação (p 0,124 a 0,904; pooled 0,242) e a conta contínua é censurada em 3 de 6 janelas. A pista 1 (fade do gap) não se repete fora da amostra (ρ −0,00 em 908 dias). A pista 3 (volume do call) mantém o sinal negativo em 4 dos 5 recortes de validação (VAL2, n=30, é +0,25), com volume estimado.
