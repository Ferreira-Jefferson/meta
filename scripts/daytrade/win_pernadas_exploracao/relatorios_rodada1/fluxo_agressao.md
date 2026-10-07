# Fluxo de agressão antes de pernadas — WIN, setembro/2026 (exploratório)

Scripts e dados intermediários em `explora/fluxo/` (ext, build, build2, ev, burst, an1..an7).

## 1. Dados e validação
- 21 pregões (WINV26), ~1,5–1,95 mi negócios/pregão. Fuso: `time_msc` lido como horário de Brasília sem conversão; primeiro negócio 09:02–09:03 (09-24: 09:14, buraco de ticks), último 18:24:59. Máx/mín de cada pregão dos ticks == máx/mín do M1 (21/21 iguais).
- Lado: 100% dos negócios têm flag 32 ou 64; ~2–3,8% trazem as duas (ambíguo, tratado como neutro). Sem lado nenhum: 0%.
- Ordem agregada: negócios consecutivos do mesmo lado e mesmo ms foram somados (varredura de book). Ordens >=100 contratos = ~32–34% do volume.
- Volume mediano por negócio 3; p99 121; spread bid/ask: moda 5 pts (campo ruidoso, usado só como controle).

## 2. Método
- Pernada = zigzag de 750 pts sobre a sequência de TICKS (média 9,1 pernadas/pregão, 5–13).
- Pivôs candidatos: zigzag de X = 150/250/375/500 pts nos ticks; o pivô só existe (tempo real) na confirmação (preço andou X). Rótulo: o preço chega a +/-750 do pivô antes de romper o pivô? Classes: `start` (é pivô do zigzag 750), `cont` (recuo dentro de pernada que continua), `fail` (não chega a 750). n (X=250): 136 / 309 / 971; (X=500): 134 / 77 / 98.
- Taxa-base de sucesso por X: 18,8% / 31,4% / 51,1% / 68,3% (150/250/375/500). n eventos: 3.833 / 1.416 / 556 / 309.
- Todas as variáveis alinhadas à direção da pernada candidata (positivo = fluxo a favor da nova pernada). Janelas terminando no pivô (`pre_`), na confirmação (`conf_`) e entre ambos (`rev_`).
- Teste: AUC univariado (0,5 = nada) com bootstrap por dia; AUC dentro de estratos hora x volatilidade; logística com controles (hora, vol 15m, tamanho do movimento anterior, ritmo) leave-one-day-out.

## 3. Resultados
### 3.1 Fluxo antes do pivô: igual em início e em falha (AUC y=sucesso)
| variável | X=150 | 250 | 375 | 500 |
|---|---|---|---|---|
| pre imbV300 (saldo vol 5m) | .493 | .475 | .461 | .448 |
| pre imbBig300 (lotes>=30) | .491 | .474 | .459 | .445 |
| pre sizeratio (tam. médio compra/venda) | .487 | .474 | .457 | .438 |
| pre corr30 (corr preço x delta, 30 min) | .498 | .481 | .459 | .437 |
| prevleg (tamanho do movimento anterior) | .516 | .503 | .466 | .442 |
| conf imbV900 | .510 | .506 | .547 | .508 |
| conf pace300 (ritmo vs normal) | .490 | .478 | .493 | .554 |
| pre absorb | .536 | .521 | .509 | .509 |
IC95 por dia (bootstrap) de quase todos cruza 0,5 (ex.: X=375 pre_corr30 [.416;.497], pre_imbV300 [.413;.508]; X=500 [.391;.493], [.390;.517]).
Direção constante: antes de fundos que viram pernada houve MAIS agressão vendedora e movimento anterior maior (clímax), mas o efeito é pequeno e os X aninhados não são independentes.

### 3.2 Mediana [IQR] do fluxo antes do pivô, por classe (X=250, alinhado)
| variável | start | cont | fail |
|---|---|---|---|
| pre_imbV60 | -0,254 | -0,263 | -0,262 |
| pre_imbV300 | -0,135 | -0,056 | -0,081 |
| pre_imbV900 | -0,073 | -0,008 | -0,031 |
| pre_imbBig300 | -0,196 | -0,076 | -0,109 |
| pre_imbOrd300 (ordens>=100) | -0,279 | -0,124 | -0,152 |
| prevleg (pts) | 605 | 360 | 405 |
Em TODO pivô (inicia pernada ou não) o último minuto tem ~63/37 contra o novo sentido (pre_imbV60 -0,25): é a agressão que fez o preço chegar ali, não sinal.
Start x fail (X=250) AUC 0,32 em imbV300 e 0,25 em imbV900, mas prevleg AUC 0,75 e Spearman(prevleg, imbV300) = -0,45: início de pernada vem depois de movimentos maiores, que têm fluxo mais extremo. Estratificando por prevleg, AUC start x fail de imbV300: <350 .318 (6 starts), 350-500 .316 (38 starts), 500-750 .451, >750 .509. Efeito some onde há amostra.

### 3.3 Tempo real: conf nao melhora a previsão
Logística leave-one-day-out, AUC: controles apenas / controles+fluxo / só fluxo
150: .476 / .472 / .465 | 250: .449 / .480 / .489 | 375: .536 / .530 / .512 | 500: .518 / .534 / .512. Fluxo nao acrescenta nada acima do ruído.
Dentro de estratos hora x vol15, X=250: imbV300 .484, imbBig300 .483, sizeratio .487, rev_imbV .530, conf_imbV60 .500.

### 3.4 Pergunta literal do dono: "50/50 -> 80/20"
Fração de compra por minuto (volume agressor): quantis 1/5/25/50/75/95/99% = .254/.316/.416/.504/.590/.687/.744 (um minuto 80/20 praticamente nao existe; 62/38 ocorre em ~10%). Em 5 min: .368/.405/.461/.503/.544/.598/.639.
Surto (alinhado ao lado do surto, retorno dos próximos 15/30 min, desagrupado 10 min):
- 1 min, z>=2,5 (n=953, 21 dias): mediana +0 a +10 pts, 50% positivos, nulo.
- 1 min, "estável -> surto" estrito (prior std<.03, z>=3): n=16 — insuficiente.
- 5 min, fluxo >=62/38 (n=460): mediana f30 -65 pts, 39% positivos, IC95 da mediana a15 [-55;-10] — parece reversão, MAS é artefato: corr(fluxo, retorno 5m)=.70 e o fluxo extremo concentra-se à tarde (volume baixo -> fração ruidosa). Controlando a hora, P(750 em 60m a favor da agressão) vs contra: 12h .22/.17, 13h .12/.18, 14h .12/.11, 15h .03/.05 — sem diferença. P(750 em 60 min) cai de ~80% (9–10h) a ~1% (17h): hora do dia é a maior variável do problema.
- Absorção (fluxo extremo no minuto e preço sem acompanhar, 1 min, z>=2: n=97): a15 +75 pts, 71% positivos, IC [+30;+130]; com z>=2,5 (n=39) IC [-100;+120]; em outras definições (>=58/42, n=265) o sinal inverte (-30, 38%). Instável.

### 3.5 Outros
- Início de pernada 750 por hora (X=500, n=134): 9h:2 10h:53 11h:24 12h:10 13h:15 14h:15 15h:10 16h:3 17h:2.
- Divergência preço x delta acumulado (novo extremo com delta oposto): X=500 n=19 (79% sucesso) vs 132 sem divergência (66%): amostra minúscula.
- corr30 (relação preço-delta nos 30 min antes do pivô): quartil mais baixo -> P(sucesso) X=375 57,6%, X=500 77,9% contra 47–49% / 64% nos demais; AUC .437–.459 (IC cruza .5). Sugere: relação frouxa antes do fundo = mais chance. Fraco.

## 4. Variações testadas
~46 variáveis x 4 X (184 AUC) + 25x2 start x fail + 33 estratos + 12 logísticas + ~60 células de surto/subgrupo/janela + tabelas por hora ≈ 350 comparações em 21 dias. Com SE do AUC ~0,03-0,05 por célula, desvios de até 0,06 são esperados ao acaso entre ~46 variáveis.

## 5. Hipóteses (para dado novo; fora de setembro)
H1. Fluxo vendedor/lote grande antes de fundo de 500 pts não é preditor após descontar o tamanho do movimento anterior. Medir: AUC start x fail estratificado por prevleg em outro mês. Derruba: AUC 0,45–0,55 nos estratos com >=40 starts.
H2. Quando a correlação preço x delta (30 min) está no quartil inferior antes de um fundo de 375-500 pts, P(750) sobe ~10 pp. Medir em outros meses, IC por dia. Derruba: diferença <3 pp ou IC cruza 0.
H3. Absorção (fluxo extremo de 1 min sem avanço de preço) antecede reversão de ~75 pts em 15 min. Medir com definição congelada (z>=2, rw<=0, 1 min). Derruba: mediana <=+20 ou % positivos <55% fora da amostra.
H4. Surtos de agressão de 5 min nao anunciam pernada nem reequilíbrio depois de controlar hora; P(750 a favor) = P(750 contra). Medir por hora em novos meses. Derruba: diferença consistente de P(750) por hora >5 pp.
H5. A distribuição por hora do início de pernada (40% das 750 começam entre 10h-11h) e a P(750 em 60 min) por hora explicam mais que qualquer fluxo; calcular o ganho de AUC de "hora" sozinha em novos meses.
H6. Ritmo (pace300) acima do normal na confirmação de recuo de 500 pts eleva sucesso (AUC .554, IC [.488;.619]). Derruba: IC cruzar 0,5 em novo mês.

Nada aqui é lucro de estratégia.
