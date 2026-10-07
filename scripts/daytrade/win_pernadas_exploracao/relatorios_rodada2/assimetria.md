# WIN set/2026 — assimetria: o que separa alta de baixa e o regime do dia (exploratório)

Base: WINV26 M1, 21 pregões (01-30/09/2026); WDO@D M1 até 29/09 (n=20 nos cruzamentos com dólar). Fechamento de 31/08 usado só como "fechamento anterior". Pernada = zigzag 750 pts sobre o caminho da vela; 1ª pernada do dia excluída das comparações alta×baixa (artefato da vela das 09:00) e pernada aberta no fim excluída. Scripts em `rodada2/assimetria/` (base, legs, a1-a4). Cerca de 110 comparações no total (a1 ~45, a2 ~40, a3 ~10, a4 ~12 + blocos); com n de 21 dias, p isolado vale pouco.

## 1. Alta e baixa são a mesma coisa (nenhuma assimetria)
Pernadas fechadas, k>0. IC90 por bootstrap de dias da diferença de medianas (alta menos baixa).

| TF | n alta/baixa | tamanho (alta / baixa) | IC90 dif | duração min | vel. pts/min | correção máx. (pts) | vol/min |
|---|---|---|---|---|---|---|---|
| M5 | 74/74 | 1.298 / 1.233 | [-110;+208] | 36 / 33,5 | 47,9 / 43,8 | 325 / 323 | 55,3k / 52,6k |
| M15 | 66/64 | 1.315 / 1.305 | [-218;+245] | 31 / 31 | 41,5 / 41,2 | 413 / 353 | 50,9k / 51,0k |
| H1 | 41/38 | 1.495 / 1.553 | [-290;+160] | 61 / 61 | 19,5 / 25,5 | 770 / 750 | 41,6k / 47,4k |

- Pontos totais por dia (mediana): M5 5.575 alta / 5.470 baixa; M15 5.255 / 4.580; H1 3.775 / 2.775 (dias com mais pontos de baixa: 9/21, 9/21, 6/21). Baixa mais rápida no dia: 11/21 (M5), 12/21 (M15), 10/19 (H1). O mercado NÃO cai mais rápido do que sobe neste mês.
- Por bloco de horário (início): <10:30 as baixas são maiores e mais rápidas (M5 1.553 vs 1.405; vel. 74 vs 60; M15 1.628 vs 1.405), 10:30-12 as altas são maiores (M15 1.563 vs 1.085; H1 1.965 vs 1.800), >12 igual. Inverte de bloco para bloco com n 15-30: ruído.
- Excursão adversa relativa (correção máx./tamanho) igual (0,2 em M5, 0,3 em M15). Fim de pernada: não medido por lado (fora do que se mostrou útil na rodada 1).

## 2. Regime do dia: o que se sabe cedo NÃO diz o lado do resto do dia (e tende a ser contra)
Alvo: sinal de (fechamento − preço em T), n=21. Contagem = dias em que o sinal da variável coincide com o do restante. p binomial bilateral, 36 testes: um p<0,05 por acaso é esperado.

| variável (em T) | T=10:00 | T=10:30 | T=11:00 |
|---|---|---|---|
| gap (abertura − fech. anterior) | 8/21 | 9/21 | 9/21 |
| retorno desde a abertura | 9/21 | 7/21 | 7/21 |
| preço − fech. anterior | 8/21 | 6/21 | 7/21 |
| preço − VWAP corrente | 9/21 | **3/21** (p<0,01) | 8/21 |
| retorno do WDO desde 09:00 | 12/20 | 14/20 | 13/20 |
| 1ª meia hora (09:00-09:30) | 10/21 | 11/21 | 11/21 |

- Padrão: a manhã reverte. Às 10:30, o restante do dia vai contra o retorno da manhã em 14/21 dias (mediana +600 pts contra; manhã grande ≥ mediana: 8/11, devolve ~50% do movimento, rem/ret mediana -0,49). Quando as 3 leituras (retorno abertura, VWAP, fech. anterior) concordam (n=14), o restante vai CONTRA o consenso em 12/14 às 10:30 (8/14 às 10:00; 10/14 às 11:00), mediana −1.093 pts a favor do consenso. O 3/21 do VWAP isolado é frágil: ao amostrar uma grade (a cada 15 min, horizontes 30/60 min, ver 4) o desvio ao VWAP prevê só 49-54%.
- WDO: o dólar na manhã tem correlação de postos -0,38 com o WIN (n=20); "WDO sobe até 10:30 → WIN sobe depois" 14/20 é a mesma reversão (a manhã do WIN caiu quando o WDO subiu e depois reverte), não informação nova. Não distingue.
- Caráter do dia: eficiência |fecha−abre|/range: mediana 0,35 (q 0,14-0,58). Dias de tendência (≥0,5): 8 (5 alta, 3 baixa); laterais (<0,25): 7. A eficiência da manhã não prevê a do dia (rho 0,02) nem a do restante (0,20). |retorno da manhã| vs |restante| rho 0,33; range da manhã vs range do resto 0,17. Nada separa cedo dia de tendência de lateral neste mês.
- Direção do dia (abertura→fechamento) igual ao retorno 09:00-10:00: 15/21 (p=0,08); com 10:30: 12/21; 11:00: 12/21. Ou seja, o sinal existe só enquanto a manhã ainda é curta e some. Gap: dia vai contra o gap em 15/21 (consistente com a rodada 1).

## 3. Pernadas a favor e contra o contexto
- Pernada M5/M15 vs pernada H1 já confirmada (reversão de 750 depois do pivô): a favor 70/140 (50%) em M5, 59/125 (47%) em M15. Tamanho mediano a favor 1.130 vs contra 1.403 (M15); duração 31 vs 61 min; 10:30-12: 1.045 vs 1.570 (n 15/27). Ressalva: o estado H1 confirmado está sempre "atrasado" 750 pts; a pernada contra é muitas vezes a reversão em curso. Tamanho maior contra o H1 é coerente com a reversão da manhã (item 2).
- Direção da pernada em direção ao VWAP/abertura/fech. anterior: 86-87% em direção ao VWAP, 71% à abertura, 66-68% ao fech. anterior. TRIVIAL: o pivô de uma pernada está longe do VWAP por construção. Não use.

## 4. Teste causal em grade (cada 15 min de 09:30 a 16:00, horizontes 30 e 60 min)
Fração de casos em que o retorno futuro tem sinal oposto ao desvio (dv=preço−VWAP, do=preço−abertura, dp=preço−fech. anterior), amostras sobrepostas (n efetivo ≈ 21 dias × poucos):

| variável | H | n | contra (todos) | <10:30 | 10:30-12:30 | >12:30 |
|---|---|---|---|---|---|---|
| dv, |x|>500 | 60 | 301 | 54% | 50% | 61% | 52% |
| do, |x|>500 | 60 | 437 | 57% | 49% | 66% | 54% |
| dp, |x|>500 | 60 | 429 | 58,5% | 57% | 73% | 50% |
| dp, |x|>500 | 30 | 429 | 54% | 46% | 65% | 50% |

Reversão de ~55-60%, concentrada em 10:30-12:30 (66-73% contra o fechamento anterior/abertura quando |desvio|>500), mediana de +135 pts em 60 min. Antes de 10:30 e depois de 12:30 ≈ acaso. Dias em que a maioria é contra: 14-15/21.

## O que NÃO apareceu
Alta×baixa em tamanho/velocidade/duração/correção/volume; gap como direção do resto; 1ª meia hora; WDO independente do WIN; caráter do dia pela manhã; tendência do dia pela posição vs VWAP.

## Hipóteses (nada validado)
Ver resposta final do agente; resumo: H-A reversão da manhã (rem contra o consenso em 10:30; DIREÇÃO/ACEITA), H-B janela 10:30-12:30 como a única em que o desvio > 500 pts do fech. anterior reverte (LIGA), H-C simetria alta/baixa (não ajustar parâmetros por lado), H-D pernada contra o H1 confirmado é maior (ALVO±), H-E dia não classificável pela manhã (não usar filtro de regime).
