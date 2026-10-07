# f3 — Outros indicadores (entrada e saída) no WinCincoMedias v2.02, só 2026

Baseline confirmado: +R$8.377,14, 13/14 janelas, pior −117,00, PF 1,77, 248 trades, DD 781,50, sem setembro 7.785,61.

## Método
- 132 variantes testadas: 125 na grade principal (`f3_indicadores.py`: 101 filtros de entrada, 24 saídas) e 7 na etapa 2 (`f3_extra.py`: vizinhança e combo).
- Cada variante teve 10 sementes de controle aleatório (1.320 rodadas aleatórias).
  - Entrada: filtro aleatório que corta a mesma fração dos sinais alinhados.
  - Saída: saída aleatória com a mesma taxa de início do sinal real. É uma aproximação, porque a saída real é um estado persistente e a aleatória é iid.
- "pct" é o percentil do líquido real entre as 10 sementes. Seu piso é 0, e é 100 quando bate as 10.
- Sem look-ahead: todo indicador usa velas fechadas até a barra do sinal.
- O Supertrend em H1 só usa a barra H1 já fechada: na vela M30 xx:30 usa a H1 que acaba de fechar, na xx:00 usa a anterior.
- Para as saídas, `simula2` é uma cópia gerada por texto de `simula`. Sem `saida_extra` reproduz o baseline exatamente (8.377,14), e `win_cinco_medias.py` não foi editado.
- Williams %R é matematicamente o Estocástico rápido (%R = %K − 100), então não foi testado à parte.
- Aroon, VWAP e ATR relativo foram testados só como filtros.

## Resultado resumido
Filtros de entrada, em geral, PIORAM. Dos 101 filtros de entrada, só 4 superam o baseline em líquido. Os que cortam muito (>25% dos sinais) quase sempre perdem de 1 a 5 mil reais, e vários ficam abaixo do percentil 50 do aleatório.

| família | melhor variante | líquido | conclusão |
|---|---|---|---|
| RSI 2/7/14 (não esticado, força, recuo) | `rsi_nao_estica(7,90)` 8.664 | cai a 6.334 em (7,80) | sem platô; `sem_set` 7.648, abaixo do baseline; pct 90 |
| RSI recuo | — | de −215 a 5.147 | destrói (poucos trades, 5 a 91) |
| Estocástico | `stoch_nao_estica(5,90)` 8.142 | 11/14, DD 929 | pior |
| MACD / TRIX | `trix(9,sobe)` 7.985, 174 trades, PF 2,01 | 14/14, pior +20,5 | menos dinheiro, melhor regularidade; não melhora o conjunto; pct 100 só porque o aleatório é muito pior |
| Bollinger / Keltner | `boll_pos(20,0.9)` 7.370 | PF 2,12, DD 500 | corta 46% dos sinais; líquido menor |
| ATR(5)/ATR(20) | — | 2.474 a 7.398 | nenhum dos dois lados ajuda |
| ADX/DI/Aroon | `adx_di(di,0)` 8.607 | ver abaixo | único filtro que passa nos critérios (corta 3,6%) |
| Supertrend M30/H1 como filtro | `st_m30(7,2)` 8.447 | pior −192 | não melhora o conjunto |
| VWAP do dia | `vwap_lado` 7.373 | 13/14, pior −106,8 | menor líquido |

Saídas (todas somadas à saída atual, ou seja, saem mais cedo ou no mesmo ponto):
- RSI abaixo de X (6 variantes) ficou idêntico ao baseline em 5 delas. A EMA4 e o stop que aperta já saem antes.
- RSI virando a partir de sobrecomprado: 6.800–7.670, piora.
- PSAR como trailing: `psar(0.04,0.4)` 8.536, pct 80, e vai caindo com a aceleração menor (8.275 → 8.218 → 7.789). É uma tendência monótona, sem platô e abaixo de p90.
- MACD contra: 7.632 a 8.028, piora.
- Supertrend M30 contra: 8.311–8.501, mas com pior −167,5 em (7,2) e (10,2).
- **Supertrend H1 contra: o único que se destaca (tabela abaixo).**

### Candidatas (passam em líquido, 13/14, pior −117, DD ≤ 781,5, ≥150 trades, pct ≥ 90)

| linha | líquido | jan+ | pior | PF | trades | DD | sem set | meses melhores/piores | aleatório (média / máx) | pct |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 8.377,14 | 13/14 | −117,00 | 1,77 | 248 | 781,50 | 7.785,61 | — | — | — |
| S: ST H1 (10,3) vira contra | 8.859,71 | 13/14 | −117,00 | 1,83 | 262 | 781,50 | 7.883,71 | 4 / 4 | 8.230 / 8.676 | 100 |
| F: DI+>DI− a favor (ADX/DI 14, M30) | 8.607,04 | 13/14 | −117,00 | 1,83 | 243 | 781,50 | 8.015,51 | 3 / 2 | 8.350 / 8.575 | 100 |
| COMBO das duas | 9.228,31 | 13/14 | −117,00 | 1,91 | 256 | 781,50 | 8.252,31 | 7 / 2 | 8.469 / 9.031 | 100 |

Platô da saída Supertrend H1 (período, multiplicador):

| variante | líquido | jan+ | sem set | pct |
|---|---|---|---|---|
| (10,2) | 8.512 | 12/14 | 7.825 | 90 |
| (10,2.5) | 8.404 | 11/14 | 7.494 | 30 |
| (10,3) | 8.860 | 13/14 | 7.884 | 100 |
| (10,3.5) | 8.976 | 13/14 | 8.021 | 100 |
| (10,4) | 8.796 | 13/14 | 7.944 | 90 |
| (14,3) | 8.741 | 13/14 | 7.765 | 90 |
| (12,3) | 8.646 | 12/14 | 7.670 | 80 |
| (5,3) | 8.573 | 11/14 | 7.708 | 80 |
| (7,2) | 8.371 | 12/14 | 7.684 | 70 |

## Leitura honesta
- A saída ST H1 com multiplicador ≥3 forma um platô fraco: 8.740–8.976, +4% a +7% sobre o baseline, sem mudar pior nem DD. Com multiplicador ≤2,5 ou período curto o ganho some, e em (14,3) o `sem set` cai abaixo do baseline.
- O percentil só passa de 90 em (10,3) e (10,3.5). O máximo aleatório chega a 8.892, então o ganho está dentro do ruído do controle.
- A comparação de meses de (10,3) é 4/4, um empate.
- O ganho do DI+/DI− (+R$230) vem de cortar ~9 trades (3,6% dos sinais). Seu platô é frágil: com ADX>15 cai a 7.839, e com DI+ADX>15 a 8.250 (pior −362).
- O combo é a melhor linha (9.228, 7 meses melhores contra 2, aleatório máx. 9.031), mas só foi decidido depois de ver as duas peças. Isso é uma escolha pós-hoc sobre 132 variantes, então o ganho pode ser em parte seleção.
- Nenhuma candidata melhora pior janela ou DD. O ganho é só de líquido, PF e sem setembro.
- Todas as candidatas têm 243–262 trades, acima do limite de fragilidade de 150.

## Veredito
Nenhum indicador desta família supera a atual de forma robusta. Há um sinal modesto e consistente no Supertrend H1 (10, mult ≥3) como saída adicional, e um micro-ganho do DI+/DI− como filtro. Os dois valem só como candidatas para o bloco de validação, com expectativa de efeito pequeno. Congeladas em `f3_candidatas.py`: `ST_H1_SAIDA`, `ADX_DI_ENTRADA`, `COMBO`.

Arquivos: `f3_feat.py` (indicadores, `simula2`), `f3_indicadores.py` e `_stdout.log` (grade principal), `f3_resumo.csv`, `f3_res.pkl`, `f3_extra.py` e `f3_extra_stdout.log` (etapa 2), `f3_extra_resumo.csv`.
