# Lente 5 - call de D-1 combinado com o leilao de abertura de D -> pregao de D

Script `lente5.py` (reprodutivel), saida completa em `stdout.txt`, tabelas `correlacoes.csv`, `grupos4.csv`, `dataset_lente5.csv`.
Tudo e **preditivo (operavel)**: so usa D-1 (fechamento continuo, call, volume do call) e o leilao de D.

## Dados e tratamento
- Fechamento continuo D-1 = `pregao_preco_fechamento`; call D-1 = `pos_preco_fechamento`; leilao D = `pre_preco_fechamento`. Volumes do CSV de fases (nada de volume das barras M1 extremas). M5 do M1 do WIN$N, barra do call (18:20) fora; base das variacoes = `pregao_preco_inicio`.
- Variaveis: `mov_call` = call D-1 - fech. continuo D-1; `gap` = leilao D - call D-1; `tot` = leilao D - fech. continuo D-1 = mov_call + gap; versoes normalizadas pela amplitude media dos 20 pregoes anteriores; |.|; razao |gap|/|call| (log, suavizada 25 pts); volume do call D-1, do leilao D, soma, log da razao; cada volume contra mediana dos 20 pregoes anteriores (so passado); "ambos acima da mediana"; concordancia de sinal call x gap.
- Alvos: variacao, direcao, |variacao|, amplitude, volume, negocios do pregao de D; variacao ate o fechamento da 1a/3a/6a/12a M5; toca o call D-1; toca o fech. continuo D-1.
- Dias fora: 04-15, 06-17, 08-12 (rolagem), 07-31, 09-24, mais 09-25 (D-1 = 09-24 com ticks faltando) e 08-03 (D-1 = pregao parcial). Resultado: n=120 com 10-05 e n=119 sem 10-05 (n efetivo por teste 110-120). Pos-feriado (04-22, 05-04, 06-05, 09-08) ficou dentro, nao tratado.
- 18 preditores x 13 alvos = 234 testes por base. Spearman, permutacao 10.000x, BH nos 234, metades abr-jun (H1) x jul-out (H2).

## 1. Movimento total x gap oficial
`tot` e `gap` tem rho = +0,99; o sinal difere em 7 de 119 dias. O trecho do call D-1 (mediana |mov_call| ~ 45-95 pts, contra |gap| mediano de centenas) quase nao muda o numero. **Usar o movimento total em vez do gap nao acrescenta informacao**; `tot` repete os resultados do gap (tot -> direcao do dia rho -0,21, p 0,024, q 0,40; gap -> direcao rho -0,22, p 0,015, q 0,31; mesma ordem de grandeza da lente 1).

## 2. Resultado dos 234 testes
| base | p<0,05 (esperado ~12) | q<0,05 | q<0,10 | \|rho\|>=0,30 |
|---|---|---|---|---|
| com 10-05 (n~119) | 17 | 4 | 7 | 4 |
| sem 10-05 (n~118) | 17 | 3 | 7 | 4 |

Os que passam por BH (q<0,05) sao todos o mesmo achado mecanico ja visto na lente 1:
| preditor -> alvo | n | rho | p perm | q BH | H1 / H2 | estavel | rotulo |
|---|---|---|---|---|---|---|---|
| \|gap\| -> toca o call D-1 | 119 | -0,35 | 0,0001 | 0,012 | -0,42 / -0,28 | sim | preditivo, mecanico (mais distancia, menos chance de tocar) |
| \|movimento total\| -> toca o fech. continuo D-1 | 119 | -0,35 | 0,0002 | 0,016 | -0,30 / -0,41 | sim | idem |
| \|gap\| -> toca o fech. continuo D-1 | 119 | -0,34 | 0,0003 | 0,018 | -0,28 / -0,41 | sim | idem |
| \|total\| -> toca o call D-1 | 119 | -0,32 | 0,0001 | 0,012 | -0,38 / -0,25 | sim | idem |
Sem 10-05 os mesmos quatro seguem com rho -0,30 a -0,34 (q 0,02-0,06).

Hipoteses (p<0,05, q>0,05, nao sustentam BH; |rho|<0,30):
- volume do call D-1 (ou sua razao a mediana de 20 dias) -> amplitude do pregao D: rho -0,24 a -0,28, p 0,002-0,009, q 0,09-0,22; sinal igual nas duas metades. Call grande, pregao seguinte de amplitude menor (sem 10-05 q=0,087).
- log(vol leilao D / vol call D-1) -> negocios do pregao: rho -0,27 a -0,29, **instavel** (H1 -0,02, H2 +0,07/+0,13); descartar.
- gap -> direcao do dia rho -0,22 (q 0,31); gap/tot -> variacao do pregao rho -0,21 (q 0,42): reversao do gap, ja vista nas lentes 1 e 3.
Nenhuma relacao com direcao ou variacao do pregao chega a |rho| 0,30.

## 3. Quatro grupos por sinal (call D-1 x gap D); com 10-05 / sem 10-05 so muda call-/gap+ (n 30 / 29)
| grupo | n | var. media do pregao (pts) | mediana | % dias de alta | amplitude media | M5 ate 3a barra | toca call D-1 | toca fech. cont. D-1 |
|---|---|---|---|---|---|---|---|---|
| call+/gap+ | 31 | -516 | -590 | 42% | 2.893 | -90 | 81% | 77% |
| call+/gap- | 34 | +294 | +343 | 59% | 3.249 | +10 | 68% | 76% |
| call-/gap+ | 30 (29) | -659 (-579) | -968 | 23% (24%) | 3.234 | -128 | 73% (76%) | 73% |
| call-/gap- | 20 | +98 | -188 | 45% | 2.803 | -106 | 75% | 70% |
Permutacao entre grupos (4 grupos): variacao p=0,19 (sem 10-05 0,24); % alta p=0,040 (0,051); amplitude p=0,32; M5 3a/12a p>0,9; toca call p=0,70. O que separa os grupos e o **sinal do gap, nao o do call**: gap+ -> pregao cai (-516/-659), gap- -> sobe ou fica (+294/+98), qualquer que seja o call. Com n=20-34 por grupo e dp da variacao ~2.020 pts, a diferenca de ~800 pts entre call+/gap+ e call+/gap- (R$160 por contrato, 0,4 dp) nao e distinguivel de ruido apos 4 grupos x varios alvos. Instabilidade entre metades: call+/gap- passa de -491 (H1, n 16) para +992 (H2, n 18); call-/gap+ de -1.414 para -81; nenhum grupo tem n>=20 por metade. So call-/gap- tem n=20 no total.

## 4. Concordancia (gap desfaz o call?)
| grupo | n | var. media | % alta | amplitude | \|var\| | toca call D-1 | continuacao do movimento total (media / mediana) |
|---|---|---|---|---|---|---|---|
| mesmo sentido | 51 | -275 | 43% | 2.857 | 1.310 | 78% | -352 / -120 |
| gap desfaz call | 63-64 | -108 a -153 | 42-43% | 3.217-3.242 | 1.683-1.703 | 70-71% | -593 a -630 / -450 |
p perm: variacao 0,67-0,75; amplitude 0,063-0,078; |var| 0,12-0,15; continuacao 0,44-0,50; toca call 0,40-0,52. Sem diferenca. O pregao tende a reverter o movimento total nos dois grupos (media -352 / -630 pts), em linha com a lente 1. Em 56% dos dias o gap vai contra o call de ontem, o que e frequente.

## 5. Tamanho relativo |gap| / |call| (tercis)
| tercil | n | var. media | amplitude | toca call D-1 | toca fech. cont. |
|---|---|---|---|---|---|
| gap << call | 40 | -102 | 3.225 | 82% | 82% |
| meio | 39 | -2 | 2.870 | 77% | 79% |
| gap >> call | 39-40 | -299 a -365 | 3.120-3.163 | 60-62% | 60-62% |
Reflete so o tamanho de |gap| (rho com toca_call -0,27 / -0,25, q 0,08-0,15); nao e efeito proprio do call.

## 6. Volumes combinados
- Call D-1 e leilao D ambos acima da mediana dos 20 dias anteriores (n=36) contra o resto (n=74-75): amplitude 2.777 contra 3.226-3.247 pts (p perm 0,033 / 0,045), |variacao| 1.332 contra 1.617-1.635 (p 0,27-0,30), volume do pregao 16,8 contra 17,1-17,2 mi (p 0,30-0,36). Um unico teste com p<0,05, em familia de 3 alvos (e dos 234 gerais fica com q>0,4: rho -0,21 a -0,22, estavel so em H2). Hipotese.
- Volume combinado (call+leilao) nao explica volume nem amplitude do pregao de D (|rho|<0,20).

## Conclusao em numeros
Nada da combinacao pos-D-1 + pre-D vence o gap sozinho. 4 achados q<0,05, todos "gap maior, menos chance de fechar o gap" (mecanico); nenhum para direcao, variacao ou amplitude. Melhor candidata nao mecanica: volume do call de D-1 alto -> amplitude de D menor (rho ~ -0,25, q ~ 0,09-0,22, efeito = amplitude ~450 pts menor, R$90 por contrato, quando ambos volumes sao altos). Custo e deslize nao descontados.

## Problemas de dado
- O trecho continuo D-1 -> call e pequeno (mediana ~50-90 pts), logo `tot` e `gap` quase identicos; a lente nao tem poder para separar os dois.
- 09-25 e 08-03 saem por D-1 contaminado (lacuna de ticks, pregao parcial), alem dos flags da lente 4; os pos-feriados ficaram dentro (gap de 2-3 noites).
- Spearman de niveis de volume com tendencia de regime (lente 3) infla rho; as correlacoes de volume podem ser regime.
- 234 testes, 17 com p<0,05 (12 esperados ao acaso): excesso pequeno e concentrado no bloco mecanico dos gaps.
