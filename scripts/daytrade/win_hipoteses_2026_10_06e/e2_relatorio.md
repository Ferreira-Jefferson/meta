# E2 — volume do mesmo horario e dia da semana, e delta estimado (WIN M30, so' 2026)

**Conclusao: volume nao acrescenta. 0 candidatas em 294 variantes.**

Baseline v2.02 reproduzido: +R$8.377,14, 13/14 janelas, pior -117,00, PF 1,77, 248 trades, DD 781,50, sem setembro +7.785,61.

## Metodo
- Volume e delta so' de velas M30 fechadas (decisao na barra do sinal t usa ate' o fechamento de t). Quantis e medianas so' com o passado; sem historico suficiente o filtro e' neutro.
- Razao semanal (metodo WinVolumeRazao): v / mediana ponderada (meia-vida 4 semanas) das ultimas `Dias` ocorrencias validas (v>0) do mesmo dia da semana e horario; menos de `Dias` -> sem valor. Dias testados: 4, 8, 12 (20 nao cabe: so' ha' ~40 semanas em 2026).
- Delta por minuto no M1: v*(c-o)/(h-l) ("prop", zero se h=l) e sign(c-o)*v ("sinal"), somado por barra M30 fechada. Normalizado pelo volume das mesmas N barras. Janela de N barras atravessa dias.
- Controle de preco: volume -> range (h-l) ou |c-o|; no delta, v -> |c-o| nos dois estimadores.
- Criterio de melhora do conjunto: liquido > base, janelas+ >= 13, pior >= -117, DD <= 781,50, liquido sem setembro > 7.785,61, meses melhores > meses piores, trades >= 150.

## Variantes (294)
| familia | n | com volume | controle de preco |
|---|---|---|---|
| (a) entrada: razao semanal da vela do sinal / media das 3 anteriores, alto (q .5-.8) ou baixo (q .5-.2) | 144 | 48 | 96 |
| (b) saida por climax: normalizacao semanal (puro / com fallback p/ mesmo horario 20d) x Dias x quantil 0,85/0,90/0,95 | 54 | 18 | 36 |
| (b') saida: mesmo horario 20d, quantil variado | 8 | 2 | 6 |
| (c) delta como filtro: N 1/2/4/8 x L 0/.05/.1/.2 x 2 estimadores | 64 | 32 | 32 |
| (c') divergencia preco x delta: N 2/4/8 x L2 0/.05 x 2 estimadores | 24 | 12 | 12 |

## Resultado (numero primeiro)
Passaram no criterio de conjunto: **0 de 294** (0/144, 0/62, 0/88).

Acima do baseline em liquido, apenas 3:
| variante | liquido | janelas | pior | PF | trades | DD | sem set | meses melhor/pior |
|---|---|---|---|---|---|---|---|---|
| saida, **range** (controle), Dias 12, fb, Q .85 | 8.576,94 | 13/14 | -117 | 1,80 | 248 | 781,5 | 7.882,91 | 3/4 |
| saida, **range** (controle), Dias 8, fb, Q .85 | 8.571,08 | 12/14 | -117 | 1,80 | 246 | 781,5 | 7.877,05 | 3/3 |
| delta prop, N=4, L=0 | 8.444,24 | 13/14 | -117 | 1,86 | 227 | 862,5 | 7.942,21 | 6/7 |

O unico acima do baseline com volume real e o delta N=4 L=0: +67 (0,8%), DD pior (862 vs 781), mais meses piores que melhores, e o vizinho L=0,05 cai para +5.535 (13/14, 161 trades) e N=2/N=8 com L=0 para +7.953/+7.783: sem platô. Os dois melhores da lista sao controles de preco (range), nao volume.

### (3a) Entrada por volume semanal
- Real (48 linhas): liquido de 4.238 a 8.009 (mediana 6.433). Nenhuma passa o baseline.
- Controle range 96 linhas inclui range e |c-o|: faixa 3.433-8.184 / 3.369-7.591, comportamento igual.
- Filtros melhoram qualidade por trade e DD, as custas de volume de operacoes: ex. sinal Dias 4, alto q .8: PF 2,71, DD 602, pior -38, mas +7.722 (-8%), 12/14, 119 trades (fragil, <150). sinal Dias 4, baixo q .4: PF 2,35, DD 438, +7.819, 11/14, 157 trades, meses 4 melhor / 9 pior. Mesmo padrao do que o controle de preco faz (menos trades, mesmo ganho por trade): nao e informacao de volume.

### (3b) Saida por climax com normalizacao semanal
- Volume (18 + 4 em mesmo horario): 7.857 a 8.303; **todos abaixo do baseline** (+8.377). A normalizacao atual (mesmo horario, 20 pregoes) ja e a melhor ou equivalente. Quantil .90 e o ponto do baseline; .85/.95 oscilam +-100.
- Controle range com Q .85 sobe a 8.577 (ruido: contradiz a leitura de que volume importa — o range faz o mesmo ou mais).

### (4) Delta
- Filtro N,L: L>=0,05 destroi o conjunto (liquido cai a 0-7.500, trades 6-240); L=0 e o unico regime proximo do baseline e piora conforme N se afasta de 4 (N=1: 7.133 prop / 6.123 sinal). L=0,2 deixa 0-165 trades.
- O controle |c-o| se comporta igual (mesma ordem de grandeza e mesma queda com L): o filtro mexe em quantidade de trades, nao em qualidade.
- Divergencia (24 linhas): melhor real +8.274 (N=2,L2=0, 239 trades, 13/14, DD 781,5, 6 melhores/5 piores) — ainda abaixo do baseline, -R$103.

## Candidatas
Nenhuma. `e2_candidatas.py` tem `CANDIDATAS = {}`.

## Arquivos
`e2_volume_semana_delta.py` (+ `_stdout.log`), `e2_resultado.csv` (294 linhas, com mensal), `e2_res.pkl`.
