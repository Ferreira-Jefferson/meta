# Estratégia semanal B3: registro de versões

Cada versão é a anterior mais uma mudança. Cada mudança só fica se a versão nova for melhor que a anterior, **medindo só a estratégia**.

## Régua (dono, 2026-10-08)

**Estratégia pura.** Caixa parado a 0%, sem CDI nem Ibovespa em lugar nenhum.

**Todos os sinais, não a carteira.** O sorteio da seleção (`semanal_sorteio_2026_10_08.py`) mostrou o problema da carteira de R$1.000 com 3–5 vagas:
- a mesma regra termina entre R$777 e R$2.300 só pelo acaso de quais sinais cabem;
- a versão nova fica acima da anterior em 17% a 100% dos sorteios, conforme a fonte.

Por isso a decisão usa todas as operações da regra.

**Nível 1 (a mudança fica?):**
- o resultado médio por operação **e** o rendimento anual enquanto posicionada melhoram no **MT5 IS e no MT5 OOS**;
- com pelo menos **10 operações em cada um**;
- 14×2 e 21×3 juntas.

**O yfinance (2011–21) é contexto, não decide** (dono, 2026-10-08). O diferencial dele é o passado mais longo, mas o mercado mudou muito desde então. Uma divergência dele pode ser só reflexo dessa mudança: aparece sempre ao lado e vira observação, nunca veto.

**Fontes:**
- MT5 IS e MT5 OOS (por papel, entradas out/22–set/25, `base_mt5.py`; validação travada);
- yfinance com entradas de 2011-01 a 2021-09, sem dias de volume zero.

**Carteira de R$1.000** (caixa a 0%, R$1,90/ordem + 0,21%/perna, 3 e 5 posições): só checagem de viabilidade (cabe no capital? qual a queda?), nunca critério de escolha.

Script da régua: `semanal_versoes_puro_2026_10_08.py`.

## Versões

Formato das células: por operação / rendimento anual enquanto posicionada.

| versão | regra | MT5 IS | MT5 OOS | yfinance 2011–21 | nível 1 |
|---|---|---|---|---|---|
| v1 | setup do vídeo: recuo à MME9 com as MMEs 9/21/50 semanais subindo, compra no rompimento da máxima, stop na mínima do candle do sinal, saída por linha ATR (14×2 ou 21×3) | — | — | — | ponto de partida |
| v2 | v1 só nas grandes (financeiro ≥ R$100 mi/dia, mediana de 63 pregões no sinal) | +1,82% / −0,5% | +0,95% / +0,4% | +3,44% / +4,0% | decisão de escopo do dono |
| v3 | v2 + força relativa: razão papel/IBOV semanal acima da MME21 dela | +1,93% / −0,5% | +1,28% / +1,3% | +4,71% / +7,0% | **fica** (melhora no IS por pouco e no OOS; yf também sobe) |
| v4 | v3 + estrutura (ideia do dono): ZigZag de 3 ATR semanais, 2 últimos topos e 2 últimos fundos ascendentes | +3,00% / +5,1% | +2,61% / +6,8% | +3,89% / +5,1% | **fica** (melhora no IS e no OOS; yf cai, possível efeito da mudança de mercado) |
| v5 | v4 + prazo: se no fechamento da 8ª semana o papel não está acima da entrada, sai na abertura seguinte | +3,21% / +5,9% | +2,78% / +7,5% | +3,44% / +4,6% | **fica** (melhora no IS e no OOS; yf cai, possível efeito da mudança de mercado) |
| **v6 (atual)** | v5 + volume: a semana do sinal (o recuo) com volume abaixo da média de 20 semanas | +3,72% / +8,3% | +3,32% / +9,3% | +2,49% / +2,2% | **fica** por pouco (melhora ~0,5 ponto no IS e no OOS; yf cai). Apoio: o lado oposto, recuo com volume ALTO, é pior nas 3 fontes |

Todas as diferenças por operação ficam dentro do intervalo de confiança (±3 a ±4 pontos). São indícios na mesma direção nas duas fontes do MT5, não certezas.

Viabilidade com R$1.000 (v4, média das 4 carteiras): IS R$978 (queda −26%), OOS R$1.057 (−19%), yfinance R$1.244 (−36%).

## Candidatas avaliadas

| mudança | sobre | resultado | situação |
|---|---|---|---|
| ordem 21 > 9 > 50 (recuo em que a MME9 já cruzou a MME21) | v4 | IS +10,29% / +15,4%, OOS −3,13% / −13,9%, yf +14,07% / +25,6% | **não fica**: só 5 operações em cada fonte do MT5 (mínimo 10) e o OOS piora. Hipótese em observação: no yf foram 29 operações a +14% cada |
| ordem 9 > 21 > 50 | v4 | melhora só no IS; OOS e yf pioram | não fica |
| empate: stop vai para a entrada depois de 1 risco | v4 | melhora no IS; no OOS o resultado por operação piora | não fica |
| confirmação mensal (4): fechamento acima da MME9 mensal, MME9 mensal subindo, acima de 6 meses antes, último mês positivo | v5 | melhoram no IS (até +4,69% / +10,7%); no OOS caem para cerca de 0% (exceto 6m, que cai pouco); no yf as 4 pioram | não fica (`semanal_multitempo_2026_10_08.py`) |
| volume (5 outras): volume do recuo acima da média, 3 semanas secas, interesse 10×50 semanas, pressão compradora, OBV | v5 | todas pioram no IS; volume alto no recuo piora nas 3 fontes | não ficam (`semanal_volume_2026_10_08.py`) |
| confirmação diária (4): MME9 > MME21, acima da MME21, MME21 subindo, acima da MME200 | v5 | 9>21 e MME21 subindo pioram no IS e no OOS; acima da MME21 e acima da MME200 são eixo morto (os sinais da v5 já estão acima) | não fica |

## Testadas e descartadas antes da régua atual

- Dave Landry e Inside Bar como gatilho, e alvo 3R: cortam entradas sem melhorar a expectativa.
- Filtro de regime pelo BOVA11 ou IBOV: atrasa a entrada sem tirar operações.
- Regime do SMLL; força relativa SMLL/IBOV: pior nas grandes.
- Inclinação das MMEs na entrada e na saída, trio 9/21/34, MMEs diárias de 100/200/300 (a de 100 é eixo morto).
- Saídas por sinal de mercado (IBOV ou força relativa virando): chicote, até −52% de queda.
- Stop máximo de 5% ou 8%; estrutura por pivô de 2 semanas; ADX.

Esses descartes foram feitos com régua antiga (carteira, às vezes com CDI no caixa). Nenhum chegou perto de passar, mas não foram refeitos na régua de todos os sinais.

Detalhes de cada teste: memória do projeto (`swing_semanal_base_mt5_is_oos_validacao_2026_10_08.md`) e scripts `semanal_*_2026_10_08.py` nesta pasta.

## Validação (conjunto travado, out/25 em diante, todos os 187 papéis) — usada em 2026-10-08

Autorizada pelo dono ("sim, tudo"). As regras v2..v6 foram congeladas antes de olhar (`semanal_validacao_v6_2026_10_08.py`, log `semanal_mmes_video/validacao_v6.log`). Operações ainda abertas entram marcadas no último fechamento.

| versão | operações | por operação | posicionada/ano | melhora a anterior? | carteira R$1.000 (caixa 0%) |
|---|---|---|---|---|---|
| v2 | 100 | +2,51% | +8,8% | — | R$964 (queda −32%) |
| v3 | 70 | +4,07% | +18,6% | **sim** | R$1.034 (−29%) |
| v4 | 38 | +2,75% | +10,9% | não | R$917 (−25%) |
| v5 | 40 | +2,44% | +9,5% | não | R$918 (−24%) |
| v6 | 29 | +1,53% | +4,1% | não | R$960 (−28%) |

No mesmo período: BOVA11 +42,5%, CDI +14,1%.

**Leitura:**
- Só a força relativa (v3) se confirma.
- Estrutura ZigZag, prazo de 8 semanas e volume do recuo pioram aqui. Cada um tinha passado no IS e no OOS por margens bem menores que o intervalo de confiança.
- Nenhuma versão passa no portão final.
- O conjunto de validação está gasto para essas regras. Qualquer regra nova escolhida depois de ver isto não pode ser validada nele.
