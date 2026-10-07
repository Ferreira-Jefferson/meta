# Lente 1 - o leilao de abertura de D impacta o pregao de D?

Script: `lente1.py` (reprodutivel). Saidas: `correlacoes.csv` (192 testes x 2 amostras, com rho, p_perm, rho nas metades, q_BH), `condicionais.csv`, `gap_fechado_por_faixa.csv`, `hora_cruzamento.csv`, `dataset_lente1.csv`.

## Metodo
- Preditores (todos conhecidos ao fim do leilao de D, portanto candidatos a **preditivo/operavel**): gap (leilao D - call D-1), gap/amplitude media dos 20 pregoes anteriores (so passado), |gap|, volume, negocios, volume/negocio do leilao, Delta% contra o leilao anterior (vol, neg, vol/neg), volume do leilao / mediana dos 20 leiloes anteriores, hora do cruzamento (segundos apos 09:00). 12 preditores.
- Alvos no pregao de D: variacao (fech - 1o preco do pregao), direcao, |variacao|, amplitude, volume, negocios, variacao do 1o/3o/6o/12o fechamento M5 contra o 1o preco do pregao, gap fechado no dia (M5 toca o call de D-1), minutos ate fechar, maxima/minima do dia na 1a hora (antes das 10:00). 16 alvos. M5 derivado do M1 do WIN$N (barra do call 18:20 excluida).
- 192 testes por amostra. Spearman rho, nulo por permutacao (10.000 embaralhamentos da variavel-alvo), BH nos 192. Estabilidade = sinal de rho igual em abr-jun (H1) e jul-out (H2) (500 permutacoes nas metades, so sinal usado).
- Amostra "completa" = 127 pregoes (n efetivo 83-125 conforme faltas). Amostra "limpa" exclui 2026-07-31, 2026-09-24 (sem leilao), 2026-10-05, 2026-04-15, 2026-06-17, 2026-08-12 (gaps de +17.775, +4.415, +3.350, +3.960 pts: provaveis trocas de contrato do WIN$N, nao verificado). 2026-04-08 (+4.875) ficou nas duas amostras - tambem suspeito.
- Resultado dos 192 testes: completa 19 com p<0,05 (esperado ao acaso ~10), 6 com q<0,05. Limpa 20 com p<0,05, 6 com q<0,05 (7 com q<0,10).

## Achados que sobrevivem a BH (limpa; n, rho, p perm, q, estavel, tipo)

| preditor -> alvo | n | rho | p perm | q BH | estavel H1/H2 | rotulo | leitura |
|---|---|---|---|---|---|---|---|
| \|gap\| -> minutos ate fechar o gap | 88 | +0,55 | 0,0001 | 0,005 | sim (0,58/0,51) | preditivo | gap maior demora mais - quase mecanico (mais distancia a percorrer) |
| \|gap\|/amp20 -> minutos ate fechar | 83 | +0,56 | 0,0001 | 0,005 | sim | preditivo | idem |
| \|gap\| -> gap fechado no dia | 119 | -0,33 | 0,0008 | 0,026 | sim | preditivo | idem; tambem mecanico |
| \|gap\|/amp20 -> gap fechado | 111 | -0,31 | 0,0008 | 0,026 | sim | preditivo | idem |
| negocios do leilao -> negocios do pregao | 121 | +0,51 | 0,0001 | 0,005 | sim, fraco em H1 (0,21/0,43) | preditivo | provavel efeito de regime de negociacao (nivel de atividade do mes), nao do leilao em si |
| volume/negocio do leilao -> negocios do pregao | 121 | -0,60 | 0,0001 | 0,005 | sim | preditivo | mesmo regime (lote medio menor = mais negocios) |

Todos medem tamanho/atividade ou geometria do gap. **Nenhuma relacao com a DIRECAO ou a variacao do pregao sobrevive a BH na amostra limpa.** Na completa, gap -> direcao do dia (rho -0,26, p 0,004, q 0,10) fica no limite e perde forca ao excluir os dias de rolagem (rho -0,22, p 0,016, q 0,27).

## Candidatos que NAO sobrevivem a BH, mas sao estaveis nas duas metades (hipoteses, nao achados)

| par | n | rho | p perm | q | H1 / H2 |
|---|---|---|---|---|---|
| gap -> variacao do pregao | 120 | -0,18 | 0,045 | 0,44 | -0,22 / -0,18 |
| gap -> direcao do dia | 120 | -0,22 | 0,016 | 0,27 | -0,14 / -0,31 |
| atraso do cruzamento (s) -> direcao do dia | 121 | -0,25 | 0,006 | 0,15 | -0,23 / -0,25 |
| atraso do cruzamento -> variacao | 121 | -0,20 | 0,027 | 0,35 | -0,12 / -0,25 |

## Condicionais (limpa; media / mediana em pontos; 1 pt = R$0,20; permutacao da diferenca de medias, 5.000)

Variacao do pregao (fech - abertura). Desvio-padrao da variacao ~2.007 pts, mediana da amplitude 2.850 pts, 43% dos dias fecham acima da abertura, media -146 pts.

| grupo | n | media var | mediana var | % dias de alta | p perm da dif. de medias |
|---|---|---|---|---|---|
| gap >= 0 | 65 | -491 | -710 | 34% | 0,037 |
| gap < 0 | 55 | +264 | +235 | 54% | |
| leilao cruzou 09:00-09:01 (atraso <90s) | 40 | +286 | +493 | 63% | 0,098 |
| leilao cruzou >= 09:01:30 | 81 | -359 | -420 | 33% | |
| \|gap\| alto (>= mediana, n=60) | 60 | -160 | -118 | - | 0,93 |
| \|gap\| baixo | 60 | -129 | -253 | - | |

- Amplitude do dia: \|gap\| alto 2.886 vs baixo 3.233 (p 0,07); gap grande **nao** gera pregao maior (se algo, menor).
- Volume do leilao, volume relativo a mediana dos 20 anteriores, Delta% vol/neg/vol-por-neg: nenhuma diferenca relevante em variacao, amplitude, gap fechado, caminho M5 (todos p > 0,2; unico significativo e negocios do pregao, ver regime acima).
- Hora do cruzamento (09:00 = 41 dias, 09:02 = 37, 09:03 = 46, 09:04 = 1): amplitude mediana 3.050 / 2.925 / 2.640 pts; volume e negocios do leilao crescem com o atraso (negocios medianos 27 / 43 / 57) - o cruzamento mais tardio e um leilao mais ativo. O atraso nao muda a probabilidade de fechar o gap (75% vs 72%).
- Gap fechado por faixa de \|gap\|/amp20 (limpa, tercis, n 38/37/37): fecha no dia 86% / 81% / 57%; fecha em 1h 84% / 62% / 30%; mediana de minutos 0 / 2,5 / 35. No tercil pequeno (mediana 168 pts) fechar e quase trivial, o preco ja abre encostado no call.
- Continuacao do gap: dia fecha na direcao do gap em 45% / 35% / 43% (pequeno/medio/grande); variacao media na direcao do gap -504 / -390 / -48 pts. Ou seja, nesta janela o pregao tendeu a **reverter** o gap, nao a continuar.
- Maxima ou minima do dia na 1a hora: 71% dos dias (max 42%, min 31%). Com gap grande cai de 82% para 62% (p 0,025).
- Caminho M5 (limpa): variacao ate o fechamento da 1a/3a/6a/12a barra M5: media -38/-78/-63/-50 pts, mediana -50/-65/-185/-210, desvio 639/813/948/1.082 pts. Efeito do gap (>=0 vs <0) na 6a barra M5: -112 vs -14 pts medias (p 0,59), isto e, o efeito do gap em var vem de depois da 1a hora ou e ruido.

## Traducao em pontos / R$ por contrato
Gap>=0 vs gap<0: diferenca de medias de 755 pts = R$151 por contrato, contra desvio de 2.007 pts (R$401) da variacao diaria: efeito ~0,4 desvio, n=120, q=0,44 apos correcao. Atraso: 645 pts = R$129, mesmo patamar. Custo e deslize existem e nao foram descontados.

## Problemas de dado
- Rolagens do WIN$N dentro dos dias de gap grande (04-08, 04-15, 06-17, 08-12, 10-05): tratados com a amostra limpa; 04-08 permanece na limpa.
- 07-31 e 09-24 sem leilao (pre_* = 0/NaN): saem dos preditores do leilao; Delta% do dia seguinte tambem fica NaN.
- Negocios e volume por negocio tem tendencia de regime ao longo dos 6 meses; correlacoes leilao-pregao em contagem sao principalmente regime comum, nao causalidade. Nao controlado.
- M5 reamostrado a partir do M1 do WIN$N; a primeira barra M5 contem o leilao (a abertura do M1 e o preco do leilao); usei o 1o preco do pregao (csv) como base das variacoes.
- Gap "fechado" via toque do M5 (high/low) no call de D-1; para gaps pequenos e quase automatico.
- n=127 (limpa 121), uma janela, mercado em tendencia de alta forte (WIN 169k -> 210k) com pregoes de media negativa: a "reversao do gap" pode ser caracteristica do periodo.
