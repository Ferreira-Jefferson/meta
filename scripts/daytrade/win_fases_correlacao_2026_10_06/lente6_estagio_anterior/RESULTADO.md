# Lente 6 - cada fase contra a fase imediatamente anterior

Script `lente6.py` (reprodutivel, ~5 min). Saidas: `correlacoes.csv`, `cadeia.csv`, `cadeia_preco.csv`, `razao_vs_nivel.csv`, `vn_tercis.csv`, `stdout.txt`.

## Metodo
- Variaveis (log das razoes de volume, negocios, vol/neg; diferenca em pontos para preco), por estagio:
  - **A** = pre D / pos D-1 (leilao D - call D-1; razoes pre_D/pos_D-1). Operavel.
  - **B1** = pregao D-1 / pre D-1. Operavel (e D-1). **C1** = pos D-1 / pregao D-1. Operavel.
  - **B0** = pregao D / pre D (leilao D -> fechamento D) e **C0** = pos D / pregao D. **Contemporaneos, nao operaveis** (C0 so serve para D+1, e isso e exatamente C1 do dia seguinte).
- Alvos do pregao D (10): variacao (fech - 1o preco), direcao, |variacao|, amplitude, volume, negocios, variacao do 1o/3o/6o/12o fechamento M5 contra o 1o preco (barra 18:20 do call excluida; preco do CSV).
- Exclusoes (`dias_flag.csv`): 07-31 e 09-24 saem de tudo (e do D+1 que as usa como D-1). 04-15, 06-17, 08-12 saem de toda variavel com preco do pre (A_dp, B_dp). 10-05 com e sem. Volume nao afetado por rolagem. (Nao apliquei a exclusao de 08-03/09-25 porque elas so valem para delta contra a mesma fase de ontem, que nao e esta familia.)
- 12 preditores operaveis x 10 alvos = 120 testes por amostra (n efetivo 118-122); 8 contemporaneos x 10 = 80. Spearman; tres nulos: (1) permutacao simples (10.000), (2) bloco = todos os deslocamentos circulares do alvo (preserva autocorrelacao), (3) nulo da razao = desloca circularmente o denominador. p_cons = max dos tres; BH sobre p_perm (q_perm) e sobre p_cons (q_cons). Estavel = mesmo sinal de rho nas duas metades.
- Poder: so |rho| >= ~0,30 sobrevive a BH com ~100 testes (lente 4).

## (a) Operaveis x pregao de D
Placar (com 10-05 / sem): 120 testes, p<0,05 simples: 13 / 11 (acaso ~6); q_perm<0,05: 6 / 5; **q_cons<0,10: 1 / 1**.

Todos os q_perm<0,05 sao sobre **volume/negocios do pregao**, e todos desabam no nulo de bloco ou no nulo da razao (pregao_negocios tem rho1 = +0,79; pregao_volume +0,38):

| preditor -> alvo | n | rho | p perm | p bloco | p razao | q_perm | q_cons | estavel | leitura |
|---|---|---|---|---|---|---|---|---|---|
| B1_v (pregao/pre vol, D-1) -> negocios D | 122 | +0,40 | 0,0000 | 0,045 | 0,24 | 0,000 | 1,0 | sim | persistencia do nivel do pregao (beta num +0,75, den n.s.) |
| B1_vn -> negocios D | 122 | +0,35 | 0,0003 | 0,125 | 0,47 | 0,009 | 1,0 | sim | idem |
| C1_n -> negocios D | 122 | +0,33 | 0,0002 | 0,34 | 1,0 | 0,008 | 1,0 | nao | negocios do pregao D-1 no denominador (beta den +0,68) |
| C1_vn -> negocios D | 122 | -0,31 | 0,0007 | 0,30 | 1,0 | 0,017 | 1,0 | nao | idem |
| **C1_v (pos/pregao vol, D-1) -> volume D** | 122 | **-0,31** | 0,0002 | 0,000 | 0,000 | 0,008 | **0,024** | sim | unico que passa tudo, **mas** a decomposicao mostra que e o denominador: beta den (pregao vol D-1) = +0,36, p<0,001; beta num (pos vol D-1) = -0,13, p 0,35. E persistencia do volume do pregao, nao a razao |
| C1_v -> amplitude D | 122 | -0,25 | 0,006 | 0,000 | 0,21 | 0,098 | 1,0 | sim | fraco |
| A_v (pre D / pos D-1 vol) -> amplitude D | 122 | +0,22 (sem 10-05: +0,25) | 0,013 | 0,027 | 0,009 | 0,20 (0,07) | 1,0 (0,82) | sim | mesmo regime da lente 1 (leilao grande -> amplitude); num e o volume do leilao de D (beta num ~+0,09 n.s. controlando o den; p den 0,036) - a razao nao melhora o nivel |

**Direcao e variacao do pregao (pontos):** nenhuma variavel nova passa. Maiores: A_dp (= gap, lente 1) -> direcao rho -0,22 (q 0,23), -> variacao -0,20 (q 0,36); C1_v -> variacao -0,13; B1_dp (pregao-leilao D-1) -> amplitude +0,19 (q 0,40). Primeiras 1/3/6/12 barras M5: |rho| <= 0,13 em todas, p>0,15 (a menos de B1_vn -> m5_1/m5_3 abaixo). Matriz completa em `correlacoes.csv`.

Unico sinal de caminho com cheiro: B1_vn (vol/neg pregao/pre de D-1) -> m5_1 e m5_3: na regressao em ranks beta num (+0,34/+0,29, q_num 0,018/0,011) e beta den (-0,24/-0,23); mas o rho simples da razao e so +0,08/+0,09 (nao entra na tabela de correlacao). Hipotese, nao achado (q_den 0,135, ~90 testes de componentes, efeito = 0,3 desvio de ranks em ~120 dias).

## (b) Persistencia na cadeia B(X) -> C(X) -> A(X+1) -> B(X+1)
Nulo: deslocamentos circulares independentes dos niveis pre/pregao/pos (3.000), que reproduz o acoplamento mecanico pelo denominador compartilhado.

| variavel | par | rho real | nulo medio [IC 95%] | real - nulo | p |
|---|---|---|---|---|---|
| volume | B->C (mesmo dia) | -0,34 | -0,33 [-0,59 ; -0,09] | -0,01 | 0,95 |
| volume | C->A (pos X -> pre X+1) | -0,52 | -0,51 [-0,68 ; -0,32] | -0,01 | 0,92 |
| volume | A->B (pre X+1 -> pregao X+1) | -0,46 | -0,56 [-0,71 ; -0,39] | +0,10 | 0,26 |
| negocios | B->C / C->A / A->B | -0,16 / -0,65 / -0,67 | -0,09 / -0,64 / -0,66 | -0,07 / -0,01 / -0,01 | 0,84 / 0,96 / 0,91 |
| vol/neg | B->C / C->A / A->B | -0,18 / -0,63 / -0,57 | -0,05 / -0,66 / -0,66 | -0,13 / +0,03 / +0,09 | 0,74 / 0,85 / 0,54 |

Os rhos de -0,5 a -0,67 sao quase inteiramente construcao (cada razao divide pelo mesmo nivel que a vizinha multiplica). **Nada acima do nulo**: a cadeia nao tem memoria alem da dos niveis. Precos (incrementos): B->C -0,13 (p 0,13), C->A(gap seguinte) -0,10 (p 0,33), gap D+1 -> (fech - leilao) D+1 -0,20 (p 0,03; e o "gap reverte no dia" da lente 1, nao novo).

## (c) Razao pre/pos D-1 vs nivel do pre (lente 1)
`razao_vs_nivel.csv`: regressao em ranks do alvo em [log numerador, log denominador] (90 combos estagio x medida x alvo; 3 estagios).
- Para A (pre D / pos D-1): o denominador (pos de ontem) acrescenta algo so em **negocios do pregao** (beta den +0,45, q 0,00) e isso e persistencia de negocios de ontem; para volume -> amplitude beta den -0,24 (p 0,036, q 0,40) e a razao (rho +0,22) nao supera o nivel do pre (rho +0,08 simples; o ganho vem do denominador, hipotese fraca). Para direcao, variacao, |variacao|, M5: nenhum denominador significativo (todos q>0,9).
- Resposta: **a razao pre/pos D-1 nao acrescenta ao nivel do leilao para o pregao alem de amplitude (hipotese, q 0,40) e do mecanico em negocios.** Em 90 componentes: 5 com q_num<0,10, 4 com q_den<0,10; todos sao persistencia de nivel (pregao_negocios/volume) ou o par B1_vn/M5 acima.

## (d) vol/neg relativo ao estagio anterior (proxy de lote grande)
Tercis (41 dias baixo vs 41 alto), `vn_tercis.csv`:
| preditor | alvo | media baixo | media alto | dif | p | sd do alvo |
|---|---|---|---|---|---|---|
| A_vn (leilao D vs call D-1) | variacao | -541 pts | +293 pts | +834 pts (R$167/contrato) | 0,06 | 2.015 |
| A_vn | amplitude | 2.900 | 3.193 | +293 | 0,22 | 1.078 |
| B1_vn | amplitude | 3.403 | 2.965 | -439 | 0,07 | 1.078 |
| C1_vn | volume pregao | 17,3 mi | 16,8 mi | -0,5 mi | 0,25 | 1,9 mi |
| demais | | | | | >0,3 | |

Correlacoes de postos: A_vn |rho| <= 0,11 com qualquer alvo, C1_vn |rho| <= 0,06 (exceto negocios, mecanico), B1_vn -> amplitude -0,19 (q 0,36). Vol/neg relativo nao diz nada sustentavel sobre direcao ou amplitude; os tercis de A_vn -> variacao (+834 pts, p 0,06) e B1_vn -> amplitude (p 0,07) sao hipoteses (2 de 12 comparacoes com p<0,10, ~1,2 esperados).

## Contemporaneos (pregao D / pre D; pos D / pregao D) - NAO operaveis
- **B0_dp (fech. pregao - leilao) -> variacao: rho 0,9999.** Identico por definicao (leilao ~ 1o preco do pregao). Os rhos de B0_dp com direcao (0,86) e M5 (0,44-0,47) tambem sao o proprio pregao. Nao e achado.
- **B0_v = log(pregao_vol/pre_vol) e circular:** rho(B0_v, log pre_vol) = -0,74 (a razao e ~ 1/leilao) e rho(B0_v, log pregao_vol) = +0,50 (e o numerador). Sua correlacao com volume/negocios/amplitude (+0,50/+0,61/+0,34) e com |variacao| (+0,36) e puramente mecanica: contra o nulo da razao (p_razao) so |variacao| sobra (0,009), nao confirma em q_cons (0,09). **Nao tratar como achado.**
- C0_v (pos/pregao) -> volume do pregao -0,51: mesma circularidade (denominador = pregao_vol, rho(C0_v, pregao_vol) = -0,51).
- Contemporaneo/nao operavel: C0 so tem uso operacional como C1 de D+1 (acima, nada).

## Resumo
1. Operavel x pregao: 240 testes (2 amostras), nenhum achado de direcao/variacao/amplitude sobrevive; unico q_cons<0,10 (C1_v -> volume do pregao, -0,31) e persistencia do volume do pregao de ontem no denominador.
2. Cadeia B->C->A->B: rhos de -0,3 a -0,67 ficam todos dentro do nulo mecanico; sem memoria entre razoes de estagios.
3. Razao pre/pos D-1 nao acrescenta ao nivel do leilao (lente 1); vol/neg relativo nao mostra relacao sustentavel.
4. Contemporaneos: B0_dp = variacao do proprio pregao; razoes volume pregao/pre e pos/pregao sao circulares.

## Problemas/ressalvas
- p_bloco/p_razao tem resolucao ~0,01 (so ~112 deslocamentos). q_cons usa o max dos nulos: e conservador (p_razao deslocando o denominador remove tambem o vinculo denominador-alvo; por isso para C1/B1 a leitura final foi feita pela decomposicao em componentes).
- Os rhos H1/H2 com n~60 tem pouco poder (~47% para rho 0,25).
