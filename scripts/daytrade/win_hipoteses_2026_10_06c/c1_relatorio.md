# C1 — Volume (velas fechadas) como filtro de entrada da WinCincoMedias v2 (WIN M30, 2026)

**Conclusão: o volume não acrescenta. Nenhuma candidata congelada** (`CANDIDATAS = {}`).

## Método
- 222 variantes (+ baseline reproduzido: +R$7.349,90, 12/14, pior −117,00, PF 1,63, 241 trades, DD 781,50, sem set 6.896,40).
- Só velas fechadas até a barra do sinal t (shift(1), rolling/expanding terminando em t ou t−1; "mesmo horário" = N pregões anteriores). Limiar por quantil calculado só com o passado (expanding). Sem histórico suficiente o filtro é neutro.
- Famílias: volume relativo vs N velas (N=10,20) e vs mesmo horário (N=10,20), alto (q≥.5/.6/.7/.8) e baixo (q≤.5/.4/.3/.2); volume crescente 2 e 3 velas; acumulado do dia vs mesmo horário; esforço×resultado |c−o|/v (cru e por horário); volume vs média das velas contra a tendência (N=6,12; razão 1,0/1,5 e 1,0/0,67).
- Controle de preço: mesma construção com range (h−l) e com |c−o| (esforço: |c−o|/(h−l)).
- Dados: `c1_resultado.csv` (inclui o líquido mensal de cada variante), log: `c1_volume_entrada_stdout.log`.

## Resultado
- **0 de 222 variantes superam o baseline em líquido** (máximo 7.243; mediana 4.677). 104 têm ≥150 trades.
- Melhores linhas de volume (v), todas com líquido menor que o baseline:

| variante | líquido | janelas+ | pior | PF | trades | DD | sem set | meses melhor/pior |
|---|---|---|---|---|---|---|---|---|
| BASELINE | 7.349,9 | 12/14 | −117,0 | 1,63 | 241 | 781,5 | 6.896 | – |
| rel_barras N20 alto q.5 | 7.128,7 | 11/14 | −117,0 | 1,77 | 165 | 851,0 | 6.651 | 5/8 |
| contra N6 alto 1,0 | 6.979,0 | 13/14 | −171,5 | 1,86 | 142* | 751,5 | 6.495 | 9/5 |
| esforco_hora N10 baixo q.4 | 6.562,5 | 14/14 | +11,0 | 1,99 | 173 | 640,6 | 6.176 | 6/7 |
| rel_hora N10 baixo q.4 | 5.914,0 | 10/14 | −139,4 | 1,88 | 170 | 572,7 | 5.970 | 4/7 |
| rel_hora N20 alto q.6 | 6.275,7 | 12/14 | −613,5 | 1,74 | 169 | 781,0 | 5.887 | 5/7 |
| crescente (2 velas) | máx 3.506 | – | – | – | – | – | – | – |

(*<150 trades = frágil.)
- Filtros de volume tiram trades (~25–40%) e, junto, líquido: o PF sobe um pouco (1,7–2,0) mas é só seleção de menos trades, sem ganho de conjunto. Volume crescente é claramente ruim (máx 3.506).
- Quase todas as variantes melhoram menos de metade dos meses vs baseline.

## Controle de preço
Pareando volume × controle (mesmo filtro/quantil): vs range, o volume tem líquido maior em 48/82 e PF maior em 49/82 (diferença média +R$153, ruído); vs |c−o|, em 30/58 (diferença média −R$265, o corpo é melhor). Os melhores casos "de volume" têm gêmeo de preço igual ou melhor: rel_hora N10 baixo q.5 com range = 7.243 (13/14, PF 2,01), com corpo = 6.655 (14/14, pior +11) contra 5.372 com volume. **O controle de preço reproduz ou supera o volume; volume não acrescenta além do range/corpo da vela.**
Único ponto onde o volume ficou à frente do controle: esforco_hora N10 baixo (v 6.562, 14/14, PF 1,99, DD 641 vs controle body/range 5.077, 13/14). Não é candidata: líquido < baseline, 6 meses melhor/7 pior, e o platô é uma rampa monotônica (q.5 6.369, q.4 6.562, q.3 5.628, q.2 4.802) que só mede "menos trades"; N=20 não sustenta (5.090 em q.4).

## Candidatas congeladas
Nenhuma. Reproduzir qualquer linha: `c1_volume_entrada.construir(d, (kind, N, modo, q, x))`.
